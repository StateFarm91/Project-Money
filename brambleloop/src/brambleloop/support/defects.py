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
released only when the incident is resolved (owner / quality director), by `release_resolved`
on the next triage.

Fail-closed and self-healing: the incident is committed first, then the hold and the jobs.
Every triage that finds the incident open re-asserts the hold and re-enqueues the checks
under the same idempotency keys, so a transient failure between those steps is repaired on
the next sweep instead of leaving an open incident with no hold.

Counted per buyer, on the release on sale: the threshold is distinct `customer_ref`s whose
cases name the currently certified version and cite the row. One buyer writing three times,
cases about another version, or cases naming no version never hold the release being sold;
an older version not on sale is never held.

How it is decided (delta review 05961fd0 N-1: a hold nothing can clear is a deadlock):
* the owner records `POST /api/owner/decision {kind: "support_defect", id, decision, why}`:
  `not_a_defect` resolves the incident and releases the hold; `confirmed` keeps the hold and
  records that a corrected version is required. An owner card names that exact call, and the
  incident's REMEDIATION entry names the same path.
* `confirmed` keeps the hold (`keep_hold`) until a corrected release exists.
* a strictly newer certified version with a CHANGED CIR supersedes the held one: the
  incident resolves as superseded and the old version stays held. A new version with an
  identical CIR inherits the hold instead (`supersede`).

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

    from ..core.models import SupportCase
    from ..runtime.quality_ops import certified_releases

    certified = {r["slug"]: r for r in certified_releases(db)}
    if slug not in certified:
        return None
    current = certified[slug]["version"]
    with db.session() as s:
        buyers = {c.customer_ref for c in s.scalars(select(SupportCase).where(
            SupportCase.product_slug == slug, SupportCase.version == current))
            if c.customer_ref
            and int(row) in [int(r) for r in (c.detail or {}).get("cited_rows") or []]}
    return {"slug": slug, "version": current,
            "release_hash": certified[slug].get("release_hash", ""), "buyers": len(buyers)}


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
                        "clears": ("owner decision (POST /api/owner/decision kind=support_defect) "
                                   "or a newer certified version superseding this one; passing "
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


def release_resolved(db) -> list[str]:
    """A support-defect incident resolved by anyone (the owner) releases its hold too."""
    from sqlalchemy import select

    from ..core.models import Incident, PatternVersion
    from ..publish import withholding

    released = []
    with db.session() as s:
        rows = [(i.signature, dict(i.detail or {})) for i in s.scalars(select(Incident).where(
            Incident.signature.like(f"{SIGNATURE}%"), Incident.resolved == True))  # noqa: E712
            if i.signature.startswith(SIGNATURE)]
        open_sigs = {i.signature for i in s.scalars(select(Incident).where(
            Incident.signature.like(f"{SIGNATURE}%"), Incident.resolved == False))}  # noqa: E712
    for sig, d in rows:
        slug, version, hold = d.get("slug"), d.get("version"), d.get("withholding_check")
        if not (slug and version and hold) or sig in open_sigs or d.get("keep_hold"):
            continue
        with db.session() as s:
            pv = withholding._release(s, slug, version)
            failed = dict((pv.certificate or {}).get(withholding.REVERIFY_FAILED) or {}) \
                if isinstance(pv, PatternVersion) else {}
        if hold in failed:
            withholding.record_reverification(db, slug, version, check=hold, problem=None)
            released.append(sig)
    return released


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
        consequence_of_delay=(f"{slug}@{version} stays withheld from publication; certifying "
                              f"a corrected version also ends the hold"))


class DecisionRefused(ValueError):
    pass


def record_owner_decision(db, incident_id: int, decision: str, why: str) -> dict:
    """The owner's decision on one open support-defect incident. Records only.

    * `not_a_defect`: the incident resolves and its hold is released (`release_resolved`).
    * `confirmed`: the incident stays open and its hold is kept (`keep_hold`) until a newer,
      changed certified version supersedes it; no later resolution path releases it.
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
        d["keep_hold"] = decision == "confirmed"
        inc.detail = d
        if decision == "not_a_defect":
            _resolve(s, inc, f"owner: not a pattern defect -- {why}")
        card = s.scalar(select(OwnerAction).where(
            OwnerAction.requirement_key == (CARD_PREFIX + inc.signature)[:200],
            OwnerAction.done == False))  # noqa: E712
        if card is not None:
            owner_queue.close(card, owner_queue.SATISFIED, f"owner decided: {decision}")
        sig = inc.signature
    released = release_resolved(db)
    return {"signature": sig, "decision": decision, "hold_released": sig in released}


def _vtuple(v: str):
    try:
        return tuple(int(x) for x in str(v).split("."))
    except ValueError:
        return None


def supersede(db) -> dict:
    """Reconcile open support-defect incidents with the release now on sale.

    * The current certified version is strictly newer AND its CIR differs from the held
      one: a corrected release exists. The incident resolves as superseded; the old version
      keeps its hold (`keep_hold`), and its card closes as SUPERSEDED.
    * The current version's CIR is identical to the held one (a re-certification or a
      version bump with no change): the defect is carried. The same hold is placed on the
      current version and the incident stays open (785849c0 F-1).
    * Anything else (an older, unparseable or unchanged-but-uncomparable version) changes
      nothing."""
    from ..core.models import Incident, OwnerAction
    from ..ops import owner_queue
    from ..publish import withholding
    from ..runtime.quality_ops import certified_releases
    from sqlalchemy import select

    current = {r["slug"]: r["version"] for r in certified_releases(db)}
    superseded, carried = [], []
    with db.session() as s:
        for inc in s.scalars(select(Incident).where(
                Incident.signature.like(f"{SIGNATURE}%"), Incident.resolved == False)):  # noqa: E712
            d = dict(inc.detail or {})
            slug, held = d.get("slug"), d.get("version")
            cur = current.get(slug)
            if not (slug and held and cur) or cur == held:
                continue
            held_pv, cur_pv = withholding._release(s, slug, held), withholding._release(s, slug, cur)
            if held_pv is None or cur_pv is None:
                continue
            same = (held_pv.cir_json or {}) == (cur_pv.cir_json or {})
            if same:
                if cur not in (d.get("carried_to") or []):
                    d["carried_to"] = list(d.get("carried_to") or []) + [cur]
                    inc.detail = d
                carried.append((slug, cur, d.get("withholding_check"), inc.signature))
                continue
            hv, cv = _vtuple(held), _vtuple(cur)
            if hv is None or cv is None or cv <= hv:
                continue
            d["keep_hold"] = True
            d["superseded_by"] = cur
            inc.detail = d
            _resolve(s, inc, f"superseded by certified {slug}@{cur} (changed CIR); "
                             f"{held} stays withheld")
            card = s.scalar(select(OwnerAction).where(
                OwnerAction.requirement_key == (CARD_PREFIX + inc.signature)[:200],
                OwnerAction.done == False))  # noqa: E712
            if card is not None:
                owner_queue.close(card, owner_queue.SUPERSEDED,
                                  f"superseded by certified {slug}@{cur}")
            superseded.append(inc.signature)
    for slug, cur, hold, sig in carried:
        if hold:
            withholding.record_reverification(
                db, slug, cur, check=hold,
                problem=(f"carried from {sig}: identical pattern to the held release; held "
                         f"until the support incident is decided"))
    return {"superseded": superseded, "carried": [c[3] for c in carried]}
