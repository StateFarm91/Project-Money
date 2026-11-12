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
    "taxonomy_agrees": "category/taxonomy agreement reader (issue-time checks increment)",
    "deterministic_reverify": "independent recompile of the stored release (issue-time checks)",
    "owner_attested_physical": "owner-attested physical binding reader (issue-time checks)",
    "independent_vision_review": "independent reviewer identity per frame (issue-time checks)",
    "no_fake_discount": "pricing.check_no_fake_discount reader (issue-time checks)",
    "physical_held": "first_customer.physical_binding evidence classes (issue-time checks)",
    "sizes": "size count from the CIR (issue-time checks)",
    "colourwork": "colourwork flag from the CIR (issue-time checks)",
    "wearable": "wearable flag from the risk matrix features (issue-time checks)",
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
