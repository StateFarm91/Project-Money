"""WS4-5 (design §3.3, §4.1, §9 M6 increment 5): the standing-policy issuer, in SHADOW only.

For every certified release that has no Etsy listing yet, the issuer reads the facts the
design's sixteen issue-time checks need, classifies the release against the owner's newest
approved policy (`standing_boundary.classify`, pure) and records what it WOULD have done as a
`standing_policy.shadow_decision` row. It SIGNS NOTHING and issues nothing: there is no grant
store, no signing key is touched, and nothing here can create or authorise a listing. The
shadow rows are what the owner reads before activating (`standing_policy.activation_refusals`
requires at least one) and what Stage D's shadow gate is measured on.

Facts. Each reader is guarded: an exception reads UNKNOWN, and UNKNOWN holds. Readers that the
next increment (issue-time checks) builds read UNKNOWN today with that reason, so every shadow
decision is honestly HOLD until they exist -- never a would-issue resting on an unread fact.

Activation-time facts. The kill switch, the enable switch, Mode T and the publishing phase are
facts about the moment of issue, and in shadow they are false by construction (the shadow
period runs before activation, in SHADOW). Shadow evaluates "would this release be in policy if
the policy were active", so those four are recorded as ASSUMED for shadow -- named in the row,
never silently -- and every other fact is read for real.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

from . import standing_boundary as SB
from . import standing_policy as SP

JOB_TYPE = "policy.issuer_shadow"
ACTOR = "standing_issuer"
# Facts about the moment of issue: assumed (and named) in shadow, read for real at issue.
ASSUMED_IN_SHADOW = ("kill_switch", "policy_enabled", "mode_t", "phase_may_publish")
# Readers the next increment (issue-time checks, design §3.3 6/9/10/11/12) builds; until then
# they read UNKNOWN and every decision holds.
NOT_BUILT_YET = {
    "independent_vision_review": "reviewer-vs-generator model identity per frame (later)",
    "stop_conditions_clear": "the stop watch (WS4 stop-watch increment)",
    "stop_watch_fresh": "the stop watch's last reading (WS4 stop-watch increment)",
}
DEDUPE_HOURS = 24


def _now(now=None) -> datetime:
    now = now or datetime.now(timezone.utc)
    return now if now.tzinfo else now.replace(tzinfo=timezone.utc)


def _fact(state: str, value=None, why: str | None = None) -> dict:
    return {"state": state, "value": value, "why": why}


def _guard(fn):
    """A reader that raises is UNKNOWN (never a pass, never a crash that skips the release)."""
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001
        return _fact(SB.UNKNOWN, None, f"reader raised {type(exc).__name__}")


# ---------------------------------------------------------------------------------------------
# The policy shadow evaluates against
# ---------------------------------------------------------------------------------------------

def shadow_policy(db, *, now: datetime | None = None) -> dict | None:
    """The owner's newest approved policy that a shadow run evaluates: a verified approval in
    the current chain segment, not revoked, passing the code ceilings and not expired. It
    need not be activated -- the shadow period comes before activation. None when there is
    none (then the issuer records nothing)."""
    now = _now(now)
    c, rows = SP._segment(db)
    if not c["valid"]:
        return None
    revoked = {d.get("approval_id") for _rid, d in rows if d.get("event") == SP.REVOKED}
    for rid, d in reversed(rows):
        if d.get("event") != SP.APPROVED or rid in revoked:
            continue
        content = d.get("content") or {}
        if SP.ceiling_refusals(content):
            continue
        expires = SP._when((content.get("validity") or {}).get("expires_at"))
        if expires is None or now >= expires:
            continue
        return {"approval_id": rid, "content": content, "seal": d.get("seal")}
    return None


# ---------------------------------------------------------------------------------------------
# Candidates and facts
# ---------------------------------------------------------------------------------------------

def candidates(db) -> list[tuple[str, str, str]]:
    """(slug, version, release) of every certified release with a draft listing not on Etsy."""
    from sqlalchemy import select

    from ..core.models import Listing, PatternVersion, Product

    out = []
    with db.session() as s:
        for pv, product in s.execute(select(PatternVersion, Product).join(
                Product, Product.id == PatternVersion.product_id).where(
                PatternVersion.certified.is_(True))):
            listing = s.scalar(select(Listing).where(Listing.product_slug == product.slug,
                                                     Listing.version == pv.version))
            if listing is None or listing.etsy_listing_id or not pv.release_hash:
                continue
            out.append((product.slug, pv.version, pv.release_hash))
    return sorted(out)


def read_facts(db, slug: str, version: str, release: str, content: dict, *,
               shadow: bool = True) -> dict:
    """The facts `standing_boundary.classify` needs, each guarded. In shadow the four
    activation-time facts are assumed and marked so."""
    facts: dict[str, dict] = {}
    for name in ASSUMED_IN_SHADOW:
        facts[name] = (_fact(SB.PASS, True, "assumed for shadow: checked at issue only")
                       if shadow else _fact(SB.UNKNOWN, None, "issue-time reader not built"))
    for name, why in NOT_BUILT_YET.items():
        facts[name] = _fact(SB.UNKNOWN, None, f"not built yet: {why}")

    facts["slug"] = _fact(SB.PASS, slug)
    facts["category"] = _guard(lambda: _category(db, slug))
    risk = _guard(lambda: _risk(db, slug, version))
    if risk.get("state") == SB.PASS:
        facts["risk_declared"] = _fact(SB.PASS, risk["value"]["declared"])
        facts["risk_derived"] = _fact(SB.PASS, risk["value"]["derived"])
    else:
        facts["risk_declared"] = facts["risk_derived"] = risk
    facts["price_cad"] = _guard(lambda: _listing_field(db, slug, version, "price_cad"))
    facts["not_on_etsy"] = _guard(lambda: _not_on_etsy(db, slug, version))
    facts["no_publish_incomplete"] = _guard(lambda: _no_publish_incomplete(db, slug, version))
    facts["not_experiment"] = _guard(lambda: _not_experiment(db, slug, version))
    facts["publication_evidence"] = _guard(
        lambda: _publication_evidence(db, slug, version, release))
    facts["release_gates"] = _guard(lambda: _release_gates(db, slug, version))
    # WS4-6 (design §3.3 checks 6, 9, 10, 12): the issue-time readers.
    cir = _guard(lambda: _stored_cir(db, slug, version))
    if cir.get("state") == SB.PASS:
        c = cir["value"]
        facts["deterministic_reverify"] = _guard(lambda: _reverify(c, release))
        physical = _guard(lambda: _physical(db, c))
        facts["physical_held"] = physical.pop("held", physical)
        facts["owner_attested_physical"] = physical
        facts["sizes"] = _guard(lambda: _sizes(c))
        facts["colourwork"] = _guard(lambda: _fact(SB.PASS, len(c.colors or {}) > 1))
        facts["wearable"] = _guard(lambda: _wearable(c))
    else:
        for name in ("deterministic_reverify", "physical_held", "owner_attested_physical",
                     "sizes", "colourwork", "wearable"):
            facts[name] = cir
    facts["taxonomy_agrees"] = _guard(lambda: _taxonomy_agrees(db, slug, version))
    facts["no_fake_discount"] = _guard(lambda: _no_fake_discount(db, slug, version))
    facts["shop_id"] = _guard(lambda: _shop_id(db))
    facts["shop_name"] = _guard(_shop_name)
    # No standing grant has ever been issued (there is no grant store until the Mode T
    # increment), so every count is exactly zero -- a fact, not an assumption.
    zero = {"consumed": 0, "outstanding": 0}
    facts["grants_today"] = _fact(SB.PASS, dict(zero), "no standing grant has been issued")
    facts["grants_7d"] = _fact(SB.PASS, dict(zero), "no standing grant has been issued")
    facts["outstanding"] = _fact(SB.PASS, 0, "no standing grant has been issued")
    facts["minutes_since_last"] = _fact(SB.PASS, None, "no earlier standing grant")
    facts["ads_jobs_queued"] = _fact(SB.PASS, 0, "no job carries a standing-policy lineage")
    return facts


def _category(db, slug):
    from ..runtime import release

    record = release._product_record(slug, db=db)
    if not record or not record.get("category"):
        return _fact(SB.UNKNOWN, None, "nobody has said what this product is")
    return _fact(SB.PASS, str(record["category"]))


def _risk(db, slug, version):
    from sqlalchemy import select

    from ..cir.model import CIR
    from ..core.models import PatternVersion, Product
    from ..gates import risk_matrix

    with db.session() as s:
        pv = s.scalar(select(PatternVersion).join(Product).where(
            Product.slug == slug, PatternVersion.version == version))
        cir_json = dict(pv.cir_json or {}) if pv is not None else None
    if not cir_json:
        return _fact(SB.UNKNOWN, None, "no stored CIR")
    matrix = risk_matrix.assess(CIR.from_dict(cir_json), twin_summary=None)
    return _fact(SB.PASS, {"declared": matrix["declared"], "derived": matrix["derived"]})


def _listing(db, slug, version):
    from sqlalchemy import select

    from ..core.models import Listing

    with db.session() as s:
        row = s.scalar(select(Listing).where(Listing.product_slug == slug,
                                             Listing.version == version))
        if row is not None:
            s.expunge(row)
        return row


def _listing_field(db, slug, version, name):
    row = _listing(db, slug, version)
    if row is None:
        return _fact(SB.UNKNOWN, None, "no listing")
    return _fact(SB.PASS, getattr(row, name))


def _not_on_etsy(db, slug, version):
    row = _listing(db, slug, version)
    if row is None:
        return _fact(SB.UNKNOWN, None, "no listing")
    return (_fact(SB.PASS, True) if not row.etsy_listing_id
            else _fact(SB.FAIL, False, "already on Etsy"))


def _no_publish_incomplete(db, slug, version):
    from sqlalchemy import select

    from ..core.models import AuditLog

    with db.session() as s:
        hit = s.scalar(select(AuditLog.id).where(
            AuditLog.action == "store.publish_incomplete",
            AuditLog.artifact == f"{slug}@{version}").limit(1))
    return (_fact(SB.PASS, True) if hit is None
            else _fact(SB.FAIL, False, "a publish of this release is incomplete"))


def _not_experiment(db, slug, version):
    from ..visual import experiment

    try:
        experiment.refuse_if_experiment(db, slug, version, action="standing policy")
    except experiment.ExperimentRefused as exc:
        return _fact(SB.FAIL, False, str(exc)[:200])
    return _fact(SB.PASS, True)


def _publication_evidence(db, slug, version, release):
    from . import publication_authority as pub

    ev = pub.evidence(db, slug, version, release)
    summary = ev.get("summary") or {}
    if summary.get("all_gated_sections_pass") is True:
        return _fact(SB.PASS, True)
    return _fact(SB.FAIL, False, "not passing: " + ", ".join(
        summary.get("not_passing") or ["UNKNOWN"])[:300])


def _release_gates(db, slug, version):
    from ..publish import release_gates

    verdict = release_gates.for_publish(db, slug=slug, version=version, read_only=True)
    if verdict.get("blocks_release") is False:
        return _fact(SB.PASS, True)
    return _fact(SB.FAIL, False, "; ".join(str(r) for r in (verdict.get("reasons")
                                                             or ["blocks"]))[:300])


def _stored_cir(db, slug, version):
    from sqlalchemy import select

    from ..cir.model import CIR
    from ..core.models import PatternVersion, Product

    with db.session() as s:
        pv = s.scalar(select(PatternVersion).join(Product).where(
            Product.slug == slug, PatternVersion.version == version))
        cir_json = dict(pv.cir_json or {}) if pv is not None else None
    if not cir_json:
        return _fact(SB.UNKNOWN, None, "no stored CIR")
    return _fact(SB.PASS, CIR.from_dict(cir_json))


def _reverify(cir, release):
    """Check 9: recompile the stored CIR, re-render the US text and recompute the release
    hash with the certificate's own function. A stored `certified=True` that this code cannot
    reproduce is refused ("deterministic validation wins")."""
    from ..cir.compiler import compile_cir
    from ..cir.writer import write_pattern
    from ..gates.certificate import _release_hash

    result = compile_cir(cir)
    if getattr(result, "errors", None):
        return _fact(SB.FAIL, False, f"the stored CIR no longer compiles: "
                                     f"{str(result.errors[0])[:120]}")
    recomputed = _release_hash(cir, write_pattern(cir, result, "US"))
    if recomputed != release:
        return _fact(SB.FAIL, False, f"recompiled release hash {recomputed[:12]} is not the "
                                     f"stored {str(release)[:12]}")
    return _fact(SB.PASS, True)


def _physical(db, cir):
    """Check 10: the physical samples bound to exactly this content
    (`first_customer.physical_binding`), and an owner attestation on every bound test's
    photograph -- an operator-token intake alone is not enough. Returns the attestation fact
    with the held classes attached under "held"."""
    from sqlalchemy import select

    from ..core.models import PhysicalPhoto
    from ..gates import first_customer

    binding = first_customer.physical_binding(db, cir)
    # `bound_classes` maps each bound test id to its evidence class (gates.certificate).
    raw = binding.get("bound_classes") or {}
    classes = sorted(set(raw.values() if isinstance(raw, dict) else raw))
    held = _fact(SB.PASS, classes)
    bound = [int(b.get("id")) if isinstance(b, dict) else int(b)
             for b in (binding.get("bound") or [])
             if (b.get("id") if isinstance(b, dict) else b) is not None]
    if not bound:
        return {**_fact(SB.PASS, True, "no physical sample is bound (nothing to attest)"),
                "held": held}
    with db.session() as s:
        # The owner's Command Center attestation (`physical_upgrade.attest_unedited`): by an
        # owner session, bound to this exact file's sha.
        attested = set()
        for p in s.scalars(select(PhysicalPhoto).where(
                PhysicalPhoto.physical_test_id.in_(bound))):
            att = (p.detail or {}).get("owner_attestation") or {}
            if str(att.get("by") or "").startswith("owner:cc:") and att.get("sha256") == p.sha256:
                attested.add(p.physical_test_id)
    missing = sorted(set(bound) - attested)
    if missing:
        return {**_fact(SB.FAIL, False, f"bound physical tests without an owner attestation: "
                                        f"{missing}"), "held": held}
    return {**_fact(SB.PASS, True), "held": held}


def _sizes(cir):
    """Each size of a graded design is its own release; a graded release offers the family."""
    grading = getattr(cir, "grading", None)
    sizes = list(getattr(grading, "sizes", None) or []) if grading is not None else []
    return _fact(SB.PASS, max(1, len(sizes)))


def _wearable(cir):
    from ..gates import risk_matrix

    return _fact(SB.PASS, bool(risk_matrix._is_wearable(cir)))


def _taxonomy_agrees(db, slug, version):
    """Check 6: the node the listing will be filed in is the one the category matcher
    chooses for this product's own category on the newest taxonomy snapshot, and its
    search profile is certified PASS."""
    from ..commerce import category as cat
    from ..integrations import etsy_taxonomy
    from ..runtime import release

    selected = cat.publish_inputs(db, slug=slug, version=version)
    if selected.get("status") != cat.CHOSEN or not selected.get("taxonomy_id"):
        return _fact(SB.FAIL, False, "the listing's category node is UNKNOWN")
    if selected.get("certified") != "PASS":
        return _fact(SB.FAIL, False, f"search profile {selected.get('certified')}")
    record = release._product_record(slug, db=db)
    snapshot = etsy_taxonomy.latest(db)
    if not record or not record.get("category") or snapshot is None:
        return _fact(SB.UNKNOWN, None, "product category or taxonomy snapshot unavailable")
    choice = cat.choose(snapshot, str(record["category"]))
    if getattr(choice, "status", None) != cat.CHOSEN or str(
            getattr(choice, "taxonomy_id", None)) != str(selected["taxonomy_id"]):
        return _fact(SB.FAIL, False, f"category {record['category']} chooses node "
                                     f"{getattr(choice, 'taxonomy_id', None)}, the listing "
                                     f"is filed in {selected['taxonomy_id']}")
    return _fact(SB.PASS, True)


def _no_fake_discount(db, slug, version):
    """Check 12: no reference ("was") price is sent. The certified payload carries none
    (`etsy_ops.certified_payload`); a promotion would, and none may run under the policy."""
    from ..runtime import etsy_ops

    payload = etsy_ops.certified_payload(db, slug, version)
    sent = etsy_ops.sent_fields(payload)
    reference = [k for k in sent if "reference" in k or "was_price" in k or "compare" in k]
    if reference:
        return _fact(SB.FAIL, False, f"the payload carries a reference price: {reference}")
    return _fact(SB.PASS, True)


def _shop_id(db):
    from ..integrations import etsy_shop_binding

    value = etsy_shop_binding.bound_shop_id(db)
    return (_fact(SB.PASS, str(value)) if value
            else _fact(SB.UNKNOWN, None, "no shop is bound"))


def _shop_name():
    from ..integrations import etsy_shop_binding

    return _fact(SB.PASS, etsy_shop_binding.expected_shop_name())


# ---------------------------------------------------------------------------------------------
# Shadow run
# ---------------------------------------------------------------------------------------------

def evaluate(db, slug, version, release, content, *, shadow: bool = True) -> dict:
    facts = read_facts(db, slug, version, release, content, shadow=shadow)
    verdict = SB.classify(content, facts)
    return {"decision": "ISSUE" if verdict["in_policy"] else "HOLD",
            "reasons": verdict["reasons"], "class_id": verdict["class_id"],
            "effective_risk": verdict["effective_risk"],
            "assumed": list(ASSUMED_IN_SHADOW) if shadow else [],
            "fact_states": {k: v.get("state") for k, v in sorted(facts.items())}}


def _digest(body: dict) -> str:
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()


def shadow_run(db, *, now: datetime | None = None) -> dict:
    """Evaluate every candidate against the shadow policy and record each decision. One row
    per (approval, release, decision, reasons) per DEDUPE_HOURS. Never signs, never issues."""
    from sqlalchemy import select

    from ..core.models import AuditLog

    now = _now(now)
    policy = shadow_policy(db, now=now)
    if policy is None:
        return {"policy": None, "evaluated": 0, "recorded": 0, "would_issue": 0,
                "signed": 0, "issued": 0}
    content = policy["content"]
    evaluated = recorded = would = 0
    since = now - timedelta(hours=DEDUPE_HOURS)
    for slug, version, release in candidates(db):
        evaluated += 1
        try:
            out = evaluate(db, slug, version, release, content, shadow=True)
        except Exception as exc:  # noqa: BLE001 - one release never stops the run
            out = {"decision": "HOLD", "reasons": [f"evaluation raised {type(exc).__name__}"],
                   "class_id": None, "effective_risk": None, "assumed": [],
                   "fact_states": {}}
        would += out["decision"] == "ISSUE"
        key = _digest({"approval_id": policy["approval_id"], "release": release,
                       "decision": out["decision"], "reasons": out["reasons"]})
        with db.session() as s:
            # Deduplicated on the decision's own time (`decided_at`), the run's clock.
            dup = any((d or {}).get("decision_key") == key
                      and (SP._when((d or {}).get("decided_at")) or since) > since
                      for d in s.scalars(select(AuditLog.detail).where(
                          AuditLog.action == SP.SHADOW_DECISION,
                          AuditLog.artifact == content["policy_id"])))
            if dup:
                continue
            s.add(AuditLog(actor=ACTOR, action=SP.SHADOW_DECISION,
                           artifact=content["policy_id"], detail={
                               "decision_key": key, "approval_id": policy["approval_id"],
                               "policy_version": content["version"], "slug": slug,
                               "version": version, "release": release,
                               "decided_at": now.isoformat(), "shadow": True,
                               "signed": False, **out}))
            recorded += 1
    return {"policy": content["policy_id"], "approval_id": policy["approval_id"],
            "evaluated": evaluated, "recorded": recorded, "would_issue": would,
            "signed": 0, "issued": 0}
