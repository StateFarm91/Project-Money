"""Collectors for the five first-sale Etsy surfaces that had none (W4-FIRSTSALE2).

W4-CLOSE6 §11: production's `etsy_first_sale_surfaces` listed messages, orders, legal_and_tax,
digital_files and taxonomy_and_attributes with `collector=None`. A surface with no collector is
NO_COLLECTOR forever, and the item is ready only when every surface is FRESH, so first-sale
readiness could never pass, even after every owner action.

Each collector returns a record in the shape `intel.etsy_surfaces.evidence_state` reads:

* `observed_at` (epoch seconds): when the underlying reading was taken, never "now" for a
  reading that is older;
* `satisfied` (bool): whether that reading MEASURED the requirement met. A current reading of a
  gap is FAILING, not FRESH;
* `why` and the evidence it was read from.

When there is no reading at all, the collector returns None, which is NO_EVIDENCE. UNKNOWN is
never made FRESH. Everything here reads only: no network call, no write.

| surface                 | collector              | reading                                     |
|-------------------------|------------------------|---------------------------------------------|
| orders                  | orders_ingest          | latest `commerce.orders_ingested` ran=true, gate open |
| taxonomy_and_attributes | taxonomy_match         | newest Etsy tree + every Launch-0 search profile CHOSEN with complete attributes |
| digital_files           | digital_deliverables   | every Launch-0 release's certified PDFs held + Etsy's digital-file rules |
| messages, legal_and_tax | shop_observation       | the owner's dated, complete reading (POST /api/etsy/shop-observation) |
"""
from __future__ import annotations

from datetime import datetime, timezone


def _epoch(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def launch0_releases() -> list[tuple[str, str]]:
    from ..products import launch0 as l0

    out = []
    for slug in l0.LAUNCH0_SLUGS:
        for v in l0.candidate(slug).variants:
            cir = l0.cir_for(v.build)
            out.append((cir.slug, cir.version))
    return out


# ---- orders -------------------------------------------------------------------------------

def orders_reading(db) -> dict | None:
    """The latest completed receipt read, and whether the order source is open now."""
    from sqlalchemy import select

    from ..commerce import orders_ingest
    from ..core.models import AuditLog

    with db.session() as s:
        row = next((r for r in s.scalars(
            select(AuditLog).where(AuditLog.action == orders_ingest.INGEST_AUDIT)
            .order_by(AuditLog.id.desc()).limit(50)) if (r.detail or {}).get("ran") is True),
            None)
        at = row.at if row is not None else None
        detail = dict(row.detail or {}) if row is not None else {}
    if at is None:
        return None
    gate = orders_ingest.gate(db)
    ok = bool(gate["open"]) and not detail.get("gate_missing")
    return {"observed_at": _epoch(at), "satisfied": ok,
            "receipts": detail.get("receipts"), "gate_missing": list(gate["missing"]),
            "owner_action": None if gate["open"] else orders_ingest.OWNER_ACTION_KEY,
            "why": ("receipts read with transactions_r granted" if ok else
                    "the last receipt read is on record but the order source is not open now: "
                    + "; ".join(gate["missing"]))[:300],
            "source": "audit_log:commerce.orders_ingested + commerce.orders_ingest.gate"}


# ---- taxonomy and attributes ---------------------------------------------------------------

def taxonomy_reading(db, releases: list[tuple[str, str]] | None = None) -> dict | None:
    """The newest Etsy tree, and every Launch-0 release's profile CHOSEN on a node of it with
    its attributes complete (the search certificate's own `attributes` check)."""
    from sqlalchemy import select

    from ..core.models import ListingSearchProfile
    from ..integrations import etsy_taxonomy

    snap = etsy_taxonomy.latest(db)
    if snap is None:
        return None
    ids = {int(n["id"]) for n in snap.get("nodes") or []}
    releases = releases if releases is not None else launch0_releases()
    gaps = []
    with db.session() as s:
        for slug, version in releases:
            row = s.scalar(select(ListingSearchProfile).where(
                ListingSearchProfile.product_slug == slug,
                ListingSearchProfile.version == version))
            if row is None:
                gaps.append(f"{slug}@{version}: no search profile")
                continue
            if row.category_status != "CHOSEN" or row.taxonomy_id is None:
                gaps.append(f"{slug}@{version}: category {row.category_status}")
                continue
            if int(row.taxonomy_id) not in ids:
                gaps.append(f"{slug}@{version}: taxonomy {row.taxonomy_id} is not in the "
                            f"newest Etsy tree")
                continue
            attrs = ((row.certificate or {}).get("checks") or {}).get("attributes") or {}
            if attrs.get("ok") is not True:
                gaps.append(f"{slug}@{version}: attributes not complete")
    return {"observed_at": _epoch(snap.get("confirmed_at") or snap.get("fetched_at")),
            "satisfied": bool(releases) and not gaps, "releases": len(releases),
            "gaps": gaps[:12], "snapshot_id": snap.get("id"),
            "why": ("every Launch-0 release is filed on a node of Etsy's tree with complete "
                    "attributes" if not gaps and releases else
                    f"{len(gaps)} release(s) not filed: {gaps[:2]}")[:300],
            "source": "etsy_taxonomy_snapshots + listing_search_profiles"}


# ---- digital files --------------------------------------------------------------------------

def digital_files_reading(db, releases: list[tuple[str, str]] | None = None,
                          *, now: float | None = None) -> dict | None:
    """Every Launch-0 release's certified PDFs held durably (re-hashed from Postgres now) and
    within Etsy's published digital-file rules, under the names the buyer downloads."""
    from ..commerce import deliverables
    from ..core.models import DurableArtifact
    from ..integrations.etsy_constraints import digital_file_problems
    from ..publish.pdf import pattern_filename

    releases = releases if releases is not None else launch0_releases()
    gaps, read_any = [], False
    for slug, version in releases:
        st = deliverables.durable_state(db, slug, version)
        if st["state"] == deliverables.UNKNOWN:
            gaps.append(f"{slug}@{version}: {st['why']}")
            continue
        read_any = True
        if st["state"] != deliverables.PASS:
            gaps.append(f"{slug}@{version}: {st['why']}")
            continue
        files = []
        with db.session() as s:
            for t, sha in sorted((st.get("pdfs") or {}).items()):
                row = s.get(DurableArtifact, sha)
                files.append((pattern_filename(t), int(row.bytes_len or 0) if row else 0))
        fails = [f["detail"] for f in digital_file_problems(files) if f["severity"] == "fail"]
        if fails:
            gaps.append(f"{slug}@{version}: {fails[0]}")
    if not read_any:
        return None              # nothing certified anywhere: no reading, not a FAILING one
    when = now if now is not None else datetime.now(timezone.utc).timestamp()
    return {"observed_at": when, "satisfied": bool(releases) and not gaps,
            "releases": len(releases), "gaps": gaps[:12],
            "why": ("every Launch-0 release's certified PDFs are held and within Etsy's "
                    "digital-file rules" if not gaps else
                    f"{len(gaps)} release(s) not deliverable: {gaps[:2]}")[:300],
            "source": "durable_artifacts (re-hashed) + etsy_constraints.digital_file_problems"}


# ---- owner observations ---------------------------------------------------------------------

def observation_reading(db, page: str) -> dict | None:
    """The owner's newest dated reading of a page. Incomplete or unmet is FAILING."""
    from ..commerce import shop_observations

    got = shop_observations.latest(db, page)
    obs = got.get("observation")
    if not obs:
        return None
    ok = shop_observations.satisfied(page, obs)
    return {"observed_at": _epoch(obs.get("observed_at")), "satisfied": ok is True,
            "observation_id": obs.get("id"), "state": got.get("state"),
            "why": ("owner's dated reading: the requirement is met" if ok else
                    "owner's dated reading is incomplete" if not obs.get("complete") else
                    "owner's dated reading says the requirement is not met"),
            "source": f"audit_log:etsy.shop_observation page={page}"}


SURFACE_PAGES = {"messages": "messages", "legal_and_tax": "legal_and_tax"}


def readings(db, *, now: float | None = None) -> dict:
    """{(collector, surface_key): record or None} for every new collector, guarded: an
    unreadable collector is None (NO_EVIDENCE), never a pass."""
    def guard(fn):
        try:
            return fn()
        except Exception:  # noqa: BLE001 - unreadable is no evidence
            return None

    out = {("orders_ingest", "orders"): guard(lambda: orders_reading(db)),
           ("taxonomy_match", "taxonomy_and_attributes"): guard(lambda: taxonomy_reading(db)),
           ("digital_deliverables", "digital_files"): guard(lambda: digital_files_reading(db, now=now))}
    for surface, page in SURFACE_PAGES.items():
        out[("shop_observation", surface)] = guard(
            lambda page=page: observation_reading(db, page))
    return out
