"""The phase-aware publication checks of `/api/verify` (A3-10).

`/api/verify` asserted shadow mode only: `phase_is_shadow` read the raw environment variable,
`nothing_published` counted `store.published` audit rows and nothing else, and
`no_revenue_claimed` required an empty ledger. So a draft created in the live shop (an
incomplete publish, a stranded exercise draft, a durable create intent with a remote ID) left
the shadow-safety assertion green, and the first legitimate phase move turned three checks red
for ever -- a red light nobody can clear, which readers learn to ignore.

Now the checks read the *effective* phase (`core.phase.resolve`: the more restrictive of the
environment and the sealed recorded transition) and change meaning with it:

* shadow / staging -- nothing may exist on Etsy: no published or incomplete listing, no
  durable draft-create intent, no exercise draft left behind. The shadow check names stay
  exactly as they were (`phase_is_shadow`, `nothing_published`, `no_revenue_claimed`).
* limited_production / production -- the phase must be recorded and agree with the
  environment (`phase_is_recorded_and_agrees`), and everything on Etsy must be certified,
  covered by an owner publication grant and read back (`everything_published_is_certified_
  granted_and_read_back`); revenue may exist, but only with its order evidence
  (`revenue_only_with_order_evidence`).

Read-only. Each function returns `{"check", "ok", "evidence"}` dicts.
"""
from __future__ import annotations

PUBLISHING_PHASES = ("limited_production", "production")


def _phase(db, env) -> dict:
    from ..core import phase as phase_mod

    try:
        return phase_mod.resolve(db, env)
    except Exception as exc:  # noqa: BLE001 - unreadable fails closed
        return {"phase": "shadow", "env": None, "env_phase": None, "recorded_phase": None,
                "agree": False, "why": f"phase unreadable: {type(exc).__name__}"}


def etsy_writes(db) -> dict:
    """Every recorded write that could have left a listing or draft on Etsy."""
    from sqlalchemy import func, select

    from ..core.models import AuditLog, Listing

    out: dict = {}
    with db.session() as s:
        def count(action: str) -> int:
            return int(s.scalar(select(func.count()).select_from(AuditLog)
                                .where(AuditLog.action == action)) or 0)

        out["store.published"] = count("store.published")
        out["store.publish_incomplete"] = count("store.publish_incomplete")
        out["store.publish_refused"] = count("store.publish_refused")
        created: set[str] = set()
        removed: set[str] = set()
        for a in s.scalars(select(AuditLog).where(AuditLog.action.in_((
                "etsy.exercise_draft_created", "etsy.exercise_draft_removed")))):
            lid = str((a.detail or {}).get("listing_id") or "")
            if lid:
                (created if a.action == "etsy.exercise_draft_created" else removed).add(lid)
        out["exercise_drafts_created"] = len(created)
        out["exercise_drafts_left_on_etsy"] = sorted(created - removed)[:20]
        out["listings_with_etsy_id"] = int(s.scalar(
            select(func.count()).select_from(Listing).where(
                Listing.etsy_listing_id.is_not(None), Listing.etsy_listing_id != "")) or 0)
    try:
        from ..publish.draft_intent import DraftIntent

        with db.session() as s:
            intents = [(i.state, i.remote_id) for i in s.scalars(select(DraftIntent))]
        out["draft_create_intents"] = len(intents)
        out["draft_create_intents_by_state"] = {
            st: sum(1 for x, _ in intents if x == st) for st in sorted({x for x, _ in intents})}
    except Exception as exc:  # noqa: BLE001 - table absent on an old schema: report it
        out["draft_create_intents"] = None
        out["draft_create_intents_error"] = type(exc).__name__
    return out


def _published_rows_proven(db) -> dict:
    """For live phases: is every listing on Etsy certified, granted and read back?"""
    from sqlalchemy import select

    from ..core.models import AuditLog, Listing, PatternVersion, Product

    unproven: list[dict] = []
    with db.session() as s:
        granted = {a.artifact for a in s.scalars(select(AuditLog).where(
            AuditLog.action == "store.execution_revalidated"))
            if (a.detail or {}).get("owner_publication_grant")}
        read_back = {a.artifact for a in s.scalars(select(AuditLog).where(
            AuditLog.action == "store.published"))
            if ((a.detail or {}).get("read_back") or {}).get("verified")}
        listings = list(s.scalars(select(Listing).where(
            Listing.etsy_listing_id.is_not(None), Listing.etsy_listing_id != "")))
        for li in listings:
            art = f"{li.product_slug}@{li.version}"
            product = s.scalar(select(Product).where(Product.slug == li.product_slug))
            pv = None if product is None else s.scalar(select(PatternVersion).where(
                PatternVersion.product_id == product.id,
                PatternVersion.version == li.version))
            reasons = []
            if pv is None or not pv.certified:
                reasons.append("not certified")
            if art not in granted:
                reasons.append("no owner publication grant recorded")
            if art not in read_back:
                reasons.append("not read back verified")
            if li.state == "incomplete_on_etsy":
                reasons.append("incomplete on Etsy")
            if reasons and li.state != "withdrawn":
                unproven.append({"listing": art, "etsy_listing_id": li.etsy_listing_id,
                                 "state": li.state, "reasons": reasons})
    return {"listings_on_etsy": len(listings), "unproven": unproven[:20]}


def publication_checks(db, env: dict | None = None) -> dict:
    """The three phase-dependent checks, keyed by their position in /api/verify."""
    from sqlalchemy import func, select

    from ..core.models import LedgerEntry

    ph = _phase(db, env)
    effective = ph.get("phase") or "shadow"
    writes = etsy_writes(db)
    phase_ev = {"effective_phase": effective, "BRAMBLELOOP_PHASE": ph.get("env"),
                "recorded_phase": ph.get("recorded_phase"), "agree": ph.get("agree"),
                "why": ph.get("why")}
    with db.session() as s:
        revenue = float(s.scalar(select(func.sum(LedgerEntry.gross_cad))) or 0.0)
        entries = int(s.scalar(select(func.count()).select_from(LedgerEntry)) or 0)
        unevidenced = int(s.scalar(select(func.count()).select_from(LedgerEntry).where(
            LedgerEntry.gross_cad > 0,
            (LedgerEntry.evidence_ref.is_(None)) | (func.trim(LedgerEntry.evidence_ref) == "")))
            or 0)

    if effective in PUBLISHING_PHASES:
        proven = _published_rows_proven(db)
        stranded = writes["exercise_drafts_left_on_etsy"]
        phase_check = {"check": "phase_is_recorded_and_agrees",
                       "ok": bool(ph.get("agree")) and ph.get("recorded_phase") == effective,
                       "evidence": phase_ev}
        pub = {"check": "everything_published_is_certified_granted_and_read_back",
               "ok": not proven["unproven"] and not stranded,
               "evidence": {**writes, **proven}}
        rev = {"check": "revenue_only_with_order_evidence", "ok": unevidenced == 0,
               "evidence": {"revenue_cad": revenue, "ledger_entries": entries,
                            "revenue_rows_without_evidence": unevidenced}}
    else:
        phase_check = {"check": "phase_is_shadow" if effective == "shadow"
                       else "phase_is_recorded_and_agrees",
                       "ok": (effective == "shadow" and ph.get("env_phase") in (None, "shadow"))
                       if effective == "shadow" else bool(ph.get("agree")),
                       "evidence": phase_ev}
        intents = writes.get("draft_create_intents")
        nothing = (writes["store.published"] == 0 and writes["store.publish_incomplete"] == 0
                   and not writes["exercise_drafts_left_on_etsy"]
                   and writes["listings_with_etsy_id"] == 0
                   and intents == 0)
        pub = {"check": "nothing_published", "ok": nothing, "evidence": writes}
        rev = {"check": "no_revenue_claimed", "ok": revenue == 0.0 and entries == 0,
               "evidence": {"revenue_cad": revenue, "ledger_entries": entries}}
    return {"phase": phase_check, "published": pub, "revenue": rev,
            "store.publish_refused": writes["store.publish_refused"]}
