"""A repeated customer defect on one row acts: incident, re-verification, withholding (W6).

P0-SUPPORT-DEFECT-INCIDENT. Spec §10: "repeated questions about the same row create a
potential defect incident"; §32: "a repeated customer defect simulation ... creates a
correlated incident". `CustomerExperience.mine_cases` already finds the hotspot (three or
more support cases citing the same product row) and `support.triage` wrote one
`support.defect_candidate` audit row for it -- nothing else. Buyers kept being sold the release
the cases were about.

`escalate` (called by `support.triage` for every hotspot at the threshold) does three things,
once per release+row:

1. **Correlated incident** `support.defect:<slug>:<version>:row<N>`, P1, scoped to the product,
   `halts_publication` False -- the hold is per release (below), so no other product and no
   other version of this one is touched.
2. **Deterministic re-verification** of that release through the existing quality path: one
   `cir.twin` and one `cir.reverse` job (validator), the same handlers `gate.quality` queues
   daily, keyed `support.defect:<check>:<slug>@<version>:row<N>` so a repeat enqueues nothing.
   Confirmation runs through the compiler, not through a vote of customers.
3. **Withholding** of that release's publication through `publish.withholding` -- the existing
   `quality_reverify` kind, under the per-check entry `support.defect:row<N>`. Publish
   (`release_gates.for_publish`) already refuses on it, it is durable on the stored release, and
   it survives re-certification (`carry_reverification`), exactly like a failed daily check.

**How the hold clears: only by a decision, never by a re-run of checks it already passed.**
A certified release passed `cir.twin` and `cir.reverse` to be certified, so a second pass
cannot refute what buyers report (independent review W6 2026-11-07, HIGH). `on_reverified`
therefore records each pass on the incident as evidence ("the compiler does not reproduce
it") and leaves the hold in place. A failing check confirms the defect: the existing
re-verification path additionally withholds and opens its own incident. The support hold is
released only when the incident stops being active (see "How it is decided" below), by `reconcile_holds`
on the next triage.

Fail-closed and self-healing: the incident is committed first, then the hold and the jobs.
Every triage that finds the incident open re-asserts the hold and re-enqueues the checks
under the same idempotency keys, so a transient failure between those steps is repaired on
the next sweep instead of leaving an open incident with no hold.

Counted per buyer, on the release on sale: the threshold is distinct `customer_ref`s whose
cases name the currently certified version and cite the row. One buyer writing three times,
cases about another version, or cases naming no version never hold the release being sold;
an older version not on sale is never held.

How it is decided, and which versions are held (delta reviews 05961fd0 .. c5cad183: every
event-driven carry / supersede / release rule had an ordering hole, so holds are now
reconciled declaratively from the incidents on every triage and every decision):
* An incident is ACTIVE while it is open, or while the owner's standing decision on it is
  `confirmed` (even if something else later marks it resolved).
* An active incident holds its own version and, if the release now on sale has the same
  INSTRUCTIONS (`instruction_hash`: construction, components, gauge, materials, colors,
  assembly -- an allowlist, so a title or notes change is the same pattern and an unknown new
  field errs toward holding), the release on sale too.
* `reconcile_holds` places every hold that should exist and releases every support-defect hold
  (check `support.defect:row<N>`, which only this module writes) that should not. A hold is
  therefore never orphaned, never released while any active incident needs it, and comes back
  if a held pattern returns to sale.
* The owner decides with `POST /api/owner/decision {kind: "support_defect", id, decision,
  why}`: `not_a_defect` resolves the incident (inactive: its holds go); `confirmed` keeps it
  active until re-decided. An undecided open incident carries an owner card naming that call.
  A corrected release (changed instructions) is simply not held; the defective one stays
  held, visible and decidable, for as long as its incident is active. Nothing supersedes
  automatically.

Idempotent: a release+row whose incident was resolved is never re-escalated; a further case
only refreshes the open incident's mention count in place.
"""
from __future__ import annotations

from datetime import datetime, timezone

THRESHOLD = 3
SIGNATURE = "support.defect:"
CHECKS: tuple[str, ...] = ("cir.twin", "cir.reverse")


def signature(slug: str, version: str, row: int) -> str:
    return f"{SIGNATURE}{slug}:{version}:row{int(row)}"[:200]


def hold_check(row: int) -> str:
    """The per-check entry this hold occupies in the release's re-verification record."""
    return f"support.defect:row{int(row)}"


def _release_for(db, slug: str, row: int) -> dict | None:
    """The release on sale (the currently certified version) and the distinct buyers whose
    cases cite this row OF THAT VERSION. Cases naming another version, or none, are not
    evidence about this release (delta reviews N-2, 785849c0 F-3) and an older version that is
    not on sale is never held (785849c0 F-1/R2). None when the product has no certified
    release."""
    from sqlalchemy import select

    from ..core.models import PatternVersion, Product, SupportCase
    from ..runtime.quality_ops import certified_releases

    certified = {r["slug"]: r for r in certified_releases(db)}
    if slug not in certified:
        return None
    # Review a66ae0b0 #1: "on sale" is the version the publish gate lets through -- the
    # highest certified version (`release_gates.superseded_release`), not the last row
    # inserted. Unorderable versions: no release is named (the publication guard refuses).
    current = _on_sale_version(db, slug)
    if current is None:
        return {"slug": slug, "version": None, "unorderable": True, "buyers": 0}
    with db.session() as s:
        buyers = {c.customer_ref for c in s.scalars(select(SupportCase).where(
            SupportCase.product_slug == slug, SupportCase.version == current))
            if c.customer_ref
            and int(row) in [int(r) for r in (c.detail or {}).get("cited_rows") or []]}
        rh = s.scalar(select(PatternVersion.release_hash)
                      .join(Product, PatternVersion.product_id == Product.id)
                      .where(Product.slug == slug, PatternVersion.version == current))
    return {"slug": slug, "version": current, "release_hash": rh or "", "buyers": len(buyers)}


def _on_sale_version(db, slug: str) -> str | None:
    """The highest certified version of `slug` (`ops.artefacts.newest_version`), or None."""
    from sqlalchemy import select

    from ..core.models import PatternVersion, Product
    from ..ops.artefacts import newest_version

    with db.session() as s:
        vs = list(s.scalars(select(PatternVersion.version)
                            .join(Product, PatternVersion.product_id == Product.id)
                            .where(Product.slug == slug,
                                   PatternVersion.certified == True)))  # noqa: E712
    return newest_version(vs) if vs else None


def escalate(ctx, hotspot: dict) -> dict:
    """Incident + re-verification + withholding for one hotspot, once per release+row."""
    from sqlalchemy import select

    from ..core.models import Incident
    from ..ops import incident_lifecycle
    from ..publish import withholding

    slug, row, mentions = str(hotspot["product"]), int(hotspot["row"]), int(hotspot["mentions"])
    if mentions < THRESHOLD or slug == "?":
        return {"escalated": False, "why": "below threshold or no product"}
    release = _release_for(ctx.db, slug, row)
    if release is None:
        return {"escalated": False, "slug": slug, "row": row,
                "why": "no stored release of this product to re-verify or withhold"}
    if release.get("unorderable"):
        # Review 5494fc71 #1: say why. Publication of every version is already refused
        # (release_gates.superseded_release fails closed on unorderable versions).
        ctx.audit("support.defect_unorderable_versions", artifact=slug, detail={
            "row": row, "mentions": mentions,
            "why": "certified versions cannot be ordered, so no release is on sale; "
                   "publication of every version is refused until they can be"})
        return {"escalated": False, "slug": slug, "row": row, "mentions": mentions,
                "why": "certified versions cannot be ordered; no release is on sale"}
    if int(release.get("buyers") or 0) < THRESHOLD:
        return {"escalated": False, "slug": slug, "row": row, "mentions": mentions,
                "buyers": int(release.get("buyers") or 0),
                "why": f"fewer than {THRESHOLD} distinct buyers cite this row"}
    version = release["version"]
    sig = signature(slug, version, row)
    check = hold_check(row)
    with ctx.db.session() as s:
        seen = list(s.scalars(select(Incident).where(Incident.signature == sig)))
        open_row = next((i for i in seen if not i.resolved), None)
        if open_row is not None:
            if (open_row.detail or {}).get("mentions") != mentions:
                open_row.detail = {**(open_row.detail or {}), "mentions": mentions,
                                   "last_seen": datetime.now(timezone.utc).isoformat()}
            new = False
        elif seen:
            return {"escalated": False, "signature": sig, "mentions": mentions,
                    "why": "this release+row was escalated before and resolved"}
        else:
            new = True
    if new:
        with ctx.db.session() as s:
            incident_lifecycle.open_or_restate(
                s, signature=sig, severity="P1", product_slug=slug, halts_publication=False,
                summary=(f"{mentions} support cases cite row {row} of {slug}@{version}: "
                         f"publication withheld pending re-verification and a decision"),
                detail={"slug": slug, "version": version, "row": row, "mentions": mentions,
                        "withholding_check": check, "pending_checks": list(CHECKS),
                        "passed_checks": [], "held_at": datetime.now(timezone.utc).isoformat(),
                        "source": "support.triage",
                        # review dd05e389 F-2: the instructions buyers reported on, fixed at
                        # open, so re-certifying the held version in place cannot change
                        # what counts as "the same pattern" while the incident is active.
                        "instruction_hash": _stored_instruction_hash(ctx.db, slug, version),
                        "clears": ("owner decision (POST /api/owner/decision kind=support_defect) "
                                   "only; a corrected release with changed instructions is not "
                                   "held, but this version stays held until decided; passing "
                                   "checks are recorded as evidence, not a release")})
    with ctx.db.session() as s:
        _owner_card(s, sig, slug, version, row, mentions)
    # Hold and checks are (re-)asserted on every triage while the incident is open: idempotent,
    # and it repairs a sweep that committed the incident but failed before the hold.
    held = withholding.record_reverification(
        ctx.db, slug, version, check=check,
        problem=(f"support cases from {THRESHOLD}+ buyers cite row {row}; held until the "
                 f"support incident is decided"))
    inputs = {"slug": slug, "version": version, "release_hash": release.get("release_hash", ""),
              "support_defect": sig, "row": row}
    key = f"{slug}@{version}:row{row}"
    # Literal job types, so the autonomy map sees each wake edge (AST, literals only).
    jobs = (ctx.enqueue("validator", "cir.twin", dict(inputs),
                        idempotency_key=f"support.defect:cir.twin:{key}"),
            ctx.enqueue("validator", "cir.reverse", dict(inputs),
                        idempotency_key=f"support.defect:cir.reverse:{key}"))
    return {"escalated": new, "reasserted": not new, "signature": sig,
            "slug": slug, "version": version,
            "row": row, "mentions": mentions, "withheld": bool(held.get("recorded")),
            "reverify_jobs": [j.id for j in jobs if j is not None]}


def _resolve(s, incident, resolution: str) -> None:
    d = dict(incident.detail or {})
    d["resolution"] = resolution
    d["resolved_at"] = datetime.now(timezone.utc).isoformat()
    incident.detail = d
    incident.resolved = True
    s.flush()


def on_reverified(db, slug: str, version: str, check: str, ok: bool | None) -> list[str]:
    """After one re-verification check of slug@version: clear the holds it completes."""
    from sqlalchemy import select

    from ..core.models import Incident
    from ..publish import withholding

    if check not in CHECKS or ok is not True:
        return []
    # A pass is evidence, not a release: the hold waits for a decision (module docstring).
    prefix = f"{SIGNATURE}{slug}:{version}:row"
    cleared: list[tuple[str, str]] = []
    with db.session() as s:
        for inc in s.scalars(select(Incident).where(
                Incident.signature.like(f"{prefix}%"), Incident.resolved == False)):  # noqa: E712
            if not inc.signature.startswith(prefix):
                continue
            d = dict(inc.detail or {})
            passed = sorted(set(d.get("passed_checks") or []) | {check})
            d["passed_checks"] = passed
            inc.detail = d
            if set(d.get("pending_checks") or CHECKS) <= set(passed):
                d["reverification"] = (
                    f"{', '.join(passed)} passed on {slug}@{version}: the compiler does not "
                    "reproduce the reported defect; held for an owner / quality decision")
                inc.detail = d
                cleared.append((inc.signature, ""))
    return [sig for sig, _ in cleared]


INSTRUCTION_KEYS = ("construction", "components", "gauge", "materials", "colors", "assembly")
HOLD_PREFIX = "support.defect:row"


def instruction_hash(cir_json: dict | None) -> str | None:
    """Identity of a pattern's instructions (not its title, version, notes or provenance)."""
    import hashlib
    import json

    if not isinstance(cir_json, dict) or not cir_json:
        return None
    body = {k: cir_json.get(k) for k in INSTRUCTION_KEYS}
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()


def _stored_instruction_hash(db, slug: str, version: str) -> str | None:
    from ..publish import withholding

    with db.session() as s:
        pv = withholding._release(s, slug, version)
        return instruction_hash(pv.cir_json) if pv is not None else None


def _active(inc) -> bool:
    d = inc.detail or {}
    decided = (d.get("owner_decision") or {}).get("decision")
    if decided == "not_a_defect":
        return False      # belt and braces: not_a_defect always resolves the incident too
    return (not inc.resolved) or decided == "confirmed"


def reconcile_holds(db) -> dict:
    """Make the support-defect holds exactly what the active incidents require."""
    from sqlalchemy import select

    from ..core.models import Incident, PatternVersion, Product
    from ..publish import withholding

    with db.session() as s:
        certified = {(slug, v) for slug, v in s.execute(
            select(Product.slug, PatternVersion.version)
            .join(Product, PatternVersion.product_id == Product.id)
            .where(PatternVersion.certified == True)).all()}  # noqa: E712
        versions = {(slug, v): (pv.cir_json or {}, dict(pv.certificate or {}))
                    for pv, slug, v in s.execute(
                        select(PatternVersion, Product.slug, PatternVersion.version)
                        .join(Product, PatternVersion.product_id == Product.id)).all()}
        incidents = [(i.signature, dict(i.detail or {}), _active(i)) for i in s.scalars(
            select(Incident).where(Incident.signature.like(f"{SIGNATURE}%")))
            if i.signature.startswith(SIGNATURE)]
    want: dict[tuple[str, str, str], str] = {}
    for sig, d, active in incidents:
        slug, held, check = d.get("slug"), d.get("version"), d.get("withholding_check")
        if not (active and slug and held and check):
            continue
        if (slug, held) in versions:
            want.setdefault((slug, held, check), sig)
        # Review a66ae0b0 #1/#6: every certified version of the product with the held
        # instructions is held -- not only the one some reader calls "current", which could
        # differ from the version the publish gate actually lets through. The instructions
        # are those stored when the incident opened (F-2); a legacy incident falls back to
        # the held row. A corrected release (changed instructions) is not held.
        h_old = d.get("instruction_hash")
        # Review 5494fc71 #2: a legacy incident (no stored hash) whose held row is gone has
        # instructions nobody can know; it holds every certified version -- fail closed. A
        # held row that exists but stores no pattern is a known "no instructions" and matches
        # nothing (test_two_versions_with_no_stored_pattern_are_not_the_same_instructions).
        unknown = h_old is None and (slug, held) not in versions
        if h_old is None and not unknown:
            h_old = instruction_hash(versions[(slug, held)][0])
        if h_old is None and not unknown:
            continue
        for (cslug, cv) in sorted(certified):
            if cslug != slug or cv == held or (cslug, cv) not in versions:
                continue
            if unknown or instruction_hash(versions[(cslug, cv)][0]) == h_old:
                want.setdefault((slug, cv, check), sig)
    have = {(slug, v, check) for (slug, v), (_cir, cert) in versions.items()
            for check in (cert.get(withholding.REVERIFY_FAILED) or {})
            if str(check).startswith(HOLD_PREFIX)}
    placed, released = [], []
    for key in sorted(set(want) - have):
        slug, v, check = key
        withholding.record_reverification(
            db, slug, v, check=check,
            problem=(f"support cases from {THRESHOLD}+ buyers cite row "
                     f"{check[len(HOLD_PREFIX):]} ({want[key]}); held until the support "
                     f"incident is decided"))
        placed.append(f"{slug}@{v}:{check}")
    for key in sorted(have - set(want)):
        slug, v, check = key
        withholding.record_reverification(db, slug, v, check=check, problem=None)
        released.append(f"{slug}@{v}:{check}")
    return {"placed": placed, "released": released}


CARD_PREFIX = "support_defect_decision:"


def _owner_card(s, sig: str, slug: str, version: str, row: int, mentions: int):
    from ..core.models import Incident
    from ..ops import owner_queue
    from sqlalchemy import select

    inc = s.scalar(select(Incident).where(Incident.signature == sig,
                                          Incident.resolved == False))  # noqa: E712
    if inc is None or (inc.detail or {}).get("owner_decision"):
        return None                  # decided: the card is closed for good (785849c0 F-2)
    return owner_queue.ensure(
        s, (CARD_PREFIX + sig)[:200],
        action=(f"Decide the reported defect on row {row} of {slug}@{version}: read the "
                f"buyers' questions in the Command Center, then record "
                f"POST /api/owner/decision {{\"kind\": \"support_defect\", \"id\": {inc.id}, "
                f"\"decision\": \"not_a_defect\" | \"confirmed\", \"why\": \"...\"}}."),
        reason=(f"{mentions} support cases from distinct buyers cite the same row. The "
                f"compiler checks (cir.twin, cir.reverse) re-run on this release; a pass cannot "
                f"refute a reader-reported problem, so publication of this release is held "
                f"until it is decided."),
        max_cost_cad=0.0, minutes=10,
        consequence_of_delay=(f"{slug}@{version}, and any release on sale with the same "
                              f"instructions, stays withheld from publication; a corrected "
                              f"release with changed instructions is not held"))


class DecisionRefused(ValueError):
    pass


def record_owner_decision(db, incident_id: int, decision: str, why: str) -> dict:
    """The owner's decision on one open support-defect incident. Records only.

    * `not_a_defect`: the incident resolves and becomes inactive; `reconcile_holds` releases
      its holds unless another active incident needs the same one.
    * `confirmed`: the incident stays active (its holds stay) until re-decided, whatever else
      later marks it resolved.
    A `confirmed` incident may still be re-decided `not_a_defect` (the owner correcting it);
    a resolved incident cannot be decided again."""
    from ..core.models import Incident, OwnerAction
    from ..ops import owner_queue
    from sqlalchemy import select

    why = (why or "").strip()
    if decision not in ("not_a_defect", "confirmed"):
        raise DecisionRefused("decision must be not_a_defect or confirmed")
    if len(why) < 10:
        raise DecisionRefused("why must be a sentence")
    if len(why) > 1000:
        raise DecisionRefused("why must be at most 1000 characters")
    with db.session() as s:
        inc = s.get(Incident, int(incident_id))
        if inc is None or not str(inc.signature).startswith(SIGNATURE):
            raise DecisionRefused("no support-defect incident with that id")
        if inc.resolved:
            raise DecisionRefused("that incident is already resolved")
        d = dict(inc.detail or {})
        d["owner_decision"] = {"decision": decision, "why": why,
                               "at": datetime.now(timezone.utc).isoformat()}
        inc.detail = d
        if decision == "not_a_defect":
            _resolve(s, inc, f"owner: not a pattern defect -- {why}")
        card = s.scalar(select(OwnerAction).where(
            OwnerAction.requirement_key == (CARD_PREFIX + inc.signature)[:200],
            OwnerAction.done == False))  # noqa: E712
        if card is not None:
            owner_queue.close(card, owner_queue.SATISFIED, f"owner decided: {decision}")
        sig = inc.signature
    out = reconcile_holds(db)
    return {"signature": sig, "decision": decision, "holds": out,
            "hold_released": bool(out["released"])}


def _vtuple(v: str):
    try:
        return tuple(int(x) for x in str(v).split("."))
    except ValueError:
        return None


