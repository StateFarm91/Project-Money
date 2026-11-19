"""ENG-CATALOGUE: the full product catalogue for Mission Control (GET /api/cc/catalogue).

The P0 board's `ROW_LIMIT` (25) is a preview. The catalogue is the inventory, uncapped:
every product/version the company is making, paginated, searchable and filterable, with
totals that are counted over every row.

**One source of truth.** Every row comes from `products.production_inventory.derive` (the
durable lifecycle, derived from the rows the release chain already keeps, in `recorded` gate
mode). Nothing here is stored. On each (TTL-cached) read the derived rows are loaded into a
private in-memory SQLite index -- a throwaway query structure, never persisted, never written
back, never read by anything else -- so filters, search, pagination and totals are SQL over
ALL rows (`GROUP BY` / `COUNT(*)`), never a sum over a capped list.

**Cross-check against the authoritative database.** Every read also counts, in SQL on the
real database, the `products` rows and the live/verified listings, and compares them with the
index. A mismatch makes the totals UNKNOWN with the reason; it is never shown as a pass.

**UNKNOWN is never 0.** A row whose state could not be derived is stage UNKNOWN (not
"revision required"), a family that cannot be read is UNKNOWN, and when the inventory itself
cannot be derived every total is `None` with `status: UNKNOWN`.

**The owner's 18-stage view** is a mapping of the inventory's states (`STAGE_OF_STATE`) plus
evidence the row itself carries (a listing live on Etsy vs. a read-back-verified draft; a
withdrawn listing). A stage the system has no evidence for is never inferred.

Owner session only (the `/api/cc` default-deny gate) and read-only: no row is written, no job
is queued, no provider is called (pinned by a statement probe in the tests).
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from datetime import datetime, timezone

TTL = 60.0
PAGE_DEFAULT = 50
PAGE_MAX = 200
UNKNOWN = "UNKNOWN"
_LOCK = threading.Lock()
_CACHE: dict = {"at": 0.0, "index": None}

# ---- the owner's 18-stage view -----------------------------------------------------------------

STAGES18: tuple[tuple[str, str], ...] = (
    ("research_candidate", "Research candidate"),
    ("research_approved", "Research approved"),
    ("pattern_in_development", "Pattern in development"),
    ("technical_validation", "Technical validation passed"),
    ("independent_review", "Independent review passed"),
    ("premium_pdf", "Premium PDF completed"),
    ("visual_package", "Visual package completed"),
    ("listing_package", "Listing package completed"),
    ("physical_sample_pending", "Physical sample pending"),
    ("physical_sample_passed", "Physical sample passed"),
    ("publication_gates_pending", "Publication gates pending"),
    ("owner_approval_pending", "Owner approval pending"),
    ("ready_for_publication", "Ready for publication"),
    ("etsy_draft_verified", "Etsy draft verified (read-back)"),
    ("live_on_etsy", "Live on Etsy"),
    ("sales_monitoring", "Sales monitoring"),
    ("revision_required", "Revision required"),
    ("withdrawn_or_rejected", "Withdrawn / rejected"),
)
STAGE18_KEYS = tuple(k for k, _ in STAGES18)
STAGE18_LABEL = dict(STAGES18)


def _pi():
    from ...products import production_inventory as pi

    return pi


def stage18(item: dict, listing: dict | None, sold: bool | None) -> str:
    """One row's stage in the owner's view, from the inventory state and the row's own
    evidence. UNKNOWN where the state could not be derived. Never a stage without evidence."""
    pi = _pi()
    if (item.get("evidence") or {}).get("derivation_error"):
        return UNKNOWN
    st = item.get("state")
    phys = (item.get("physical_sample") or {}).get("status")
    if st == pi.PUBLISHED:
        lstate = (listing or {}).get("state", "")
        from ...core import listing_state

        if lstate == "active" or lstate == listing_state.PUBLISHED_MANUALLY:
            # Sales monitoring needs a measured sale; otherwise the listing is live, no more.
            return "sales_monitoring" if sold else "live_on_etsy"
        if listing_state.is_live_on_etsy(lstate) and (listing or {}).get("etsy_listing_id"):
            # The gated store.publish path: a draft created on Etsy and read back.
            return "etsy_draft_verified"
        return UNKNOWN
    if st == pi.REJECTED:
        return "withdrawn_or_rejected"
    if st == pi.REVISION_REQUIRED:
        if (listing or {}).get("state") == "withdrawn":
            return "withdrawn_or_rejected"
        return "revision_required"
    if st == pi.LISTING_COMPLETED:
        # The physical sample is an attribute beside the furthest internal state; the owner's
        # view shows it as the step the row is waiting on.
        if phys == "pending":
            return "physical_sample_pending"
        if phys == "passed":
            return "physical_sample_passed"
        return "publication_gates_pending"
    direct = {pi.RESEARCH_CANDIDATE: "research_candidate",
              pi.RESEARCH_APPROVED: "research_approved",
              pi.PATTERN_IN_DEVELOPMENT: "pattern_in_development",
              pi.PATTERN_VALIDATED: "technical_validation",
              pi.REVIEW_PASSED: "independent_review",
              pi.PDF_COMPLETED: "premium_pdf",
              pi.VISUAL_COMPLETED: "visual_package",
              pi.OWNER_APPROVAL_PENDING: "owner_approval_pending",
              pi.READY: "ready_for_publication"}
    return direct.get(st, UNKNOWN)


# ---- next action and who owns it ---------------------------------------------------------------

# state -> (next action, the job type that carries it). The owning department is read from the
# department charters (`autonomy.charters.department_of`), never hard-coded here.
NEXT_ACTION: dict[str, tuple[str, str | None]] = {
    "research_candidate": ("research verdict (score and promotion gate)", "radar.score"),
    "research_approved": ("draft the CIR", "cir.draft"),
    "pattern_in_development": ("compile and validate the CIR", "cir.compile"),
    "pattern_technically_validated": ("independent certification", "gate.certify"),
    "independent_review_passed": ("build the premium PDF", "assets.build"),
    "premium_pdf_completed": ("verify the listing image set", "assets.build"),
    "visual_package_completed": ("draft listing copy and SEO", "listing.seo"),
    "listing_package_completed": ("pass the publication gates", "store.publish"),
    "owner_approval_pending": ("owner publication grant", None),
    "ready_for_publication": ("create the Etsy draft", "store.publish"),
    "published": ("monitor sales and listing health", "commerce.orders_ingest"),
    "revision_required": ("revise the CIR", "cir.revise"),
    "rejected": ("none (terminal)", None),
}
OWNER_HOLDS = ("owner", "physical", "paid_approval")


def next_action(item: dict) -> dict:
    """The row's next action and its owner: the owner for an owner/physical/paid hold or an
    owner grant, otherwise the department chartered for the job type. UNKNOWN when unread."""
    if (item.get("evidence") or {}).get("derivation_error"):
        return {"action": UNKNOWN, "owner": UNKNOWN, "job_type": None}
    holds = [h.get("kind") for h in item.get("holds") or []]
    for kind, action in (("paid_approval", "owner approval of a paid step"),
                         ("physical", "make and record the physical sample"),
                         ("owner", "owner publication grant")):
        if kind in holds:
            return {"action": action, "owner": "owner", "job_type": None}
    action, job_type = NEXT_ACTION.get(item.get("state"), (UNKNOWN, None))
    if item.get("state") in ("owner_approval_pending",):
        return {"action": action, "owner": "owner", "job_type": None}
    if job_type is None:
        return {"action": action, "owner": "none" if action.startswith("none") else UNKNOWN,
                "job_type": None}
    try:
        from ...autonomy.charters import department_of

        dept = department_of(job_type) or UNKNOWN
    except Exception:  # noqa: BLE001 - an unreadable charter is UNKNOWN, never a guess
        dept = UNKNOWN
    return {"action": action, "owner": dept, "job_type": job_type}


# ---- per-row evidence --------------------------------------------------------------------------

def _stage_ev(item: dict, name: str) -> dict:
    for st in (item.get("evidence") or {}).get("stages") or []:
        if st.get("stage") == name:
            return st
    return {}


def evidence(item: dict, version_row: dict | None, listing: dict | None,
             intent: dict | None) -> dict:
    """The links an owner can follow: certificate, PDF hash, gallery, listing package, Etsy
    draft/listing id and its read-back. Each is present only where its row exists."""
    slug = item["slug"]
    pv = version_row or {}
    cert = None
    if pv.get("certified") and pv.get("release_hash"):
        cert = {"release_hash": pv["release_hash"],
                "content_hash": (pv.get("certificate") or {}).get("content_hash"),
                "physical_test_required": bool((pv.get("certificate") or {})
                                               .get("physical_test_required"))}
    pdf = (_stage_ev(item, "premium_pdf_completed").get("digests") or {}).get("pdf") or None
    vis = _stage_ev(item, "visual_package_completed")
    lst = _stage_ev(item, "listing_package_completed")
    from ...core import listing_state

    etsy = None
    if listing is not None:
        lid = listing.get("etsy_listing_id") or None
        state = listing.get("state") or ""
        if lid and state == "active":
            readback = "live"
        elif lid and listing_state.is_live_on_etsy(state):
            readback = "verified"
        elif lid:
            readback = "not_verified"
        else:
            readback = "no_remote_listing"
        etsy = {"listing_row": listing.get("id"), "state": state, "etsy_listing_id": lid,
                "read_back": readback, "draft_intent": (intent or {}).get("state")}
    elif intent is not None:
        etsy = {"listing_row": None, "state": None, "etsy_listing_id": None,
                "read_back": "not_verified", "draft_intent": intent.get("state")}
    return {
        "certificate": cert,
        "pdf": ({"sha256": pdf, "href": f"/api/cc/store/pdf/{slug}"} if pdf else None),
        "gallery": ({"audit_id": vis.get("audit_id"), "frames": vis.get("frames"),
                     "href": f"/api/cc/visual/evidence/{slug}"} if vis else None),
        "listing_package": ({"listing_id": lst.get("listing_id"),
                             "audit_id": lst.get("audit_id")} if lst else None),
        "etsy": etsy,
    }


# ---- families ----------------------------------------------------------------------------------

def _families(db) -> dict[str, tuple[str, str | None]]:
    """slug -> (category, bundle family) from the concept pool and recorded radar concepts.
    Read-only: the radar table is never created here (it may not exist)."""
    from ...radar.opportunity import POOL

    out = {s.slug: (s.category, s.family) for s in POOL}
    try:
        from sqlalchemy import inspect, select

        from ...radar.intake import RadarConcept

        with db.session() as s:
            if inspect(s.get_bind()).has_table(RadarConcept.__tablename__):
                for slug, seed in s.execute(select(RadarConcept.slug, RadarConcept.seed)
                                            .order_by(RadarConcept.id)):
                    seed = seed or {}
                    if slug not in out and seed.get("category"):
                        out[slug] = (str(seed["category"]), seed.get("family"))
    except Exception:  # noqa: BLE001 - a concept we cannot read has an UNKNOWN family
        pass
    return out


# ---- the index ---------------------------------------------------------------------------------

_COLUMNS = ("slug", "version", "title", "head", "state", "state_label", "stage", "category",
            "family", "held", "next_action", "next_owner", "listing_state", "payload")


def _sold_slugs(db) -> set[str] | None:
    """Slugs with a countable Etsy order; None when the order source is not measured (a
    listing with no measured sale is live, never 'sales monitoring' with zero sales)."""
    from sqlalchemy import select

    from ...commerce import orders_ingest as OI
    from ...core.models import Order

    try:
        if not OI.source_state(db).get("measured"):
            return None
        with db.session() as s:
            rows = OI.countable_orders(s, select(Order).where(Order.source == "etsy_receipts"))
            return {str(getattr(o, "product_slug", "") or "") for o in rows} - {""}
    except Exception:  # noqa: BLE001
        return None


def build_index(db, *, now: datetime | None = None) -> dict:
    """Derive every row once and load it into a private in-memory SQLite index."""
    pi = _pi()
    now = now or datetime.now(timezone.utc)
    rec = pi.load_records(db)
    inv = pi.derive(db, records=rec, now=now)
    fams = _families(db)
    sold = _sold_slugs(db)
    versions = {}
    for pv in rec["versions"]:
        versions[(pv["slug"], pv["version"])] = pv
    con = sqlite3.connect(":memory:", check_same_thread=False)
    con.execute(f"CREATE TABLE cat ({', '.join(_COLUMNS)}, n INTEGER PRIMARY KEY)")
    rows = []
    for it in inv["items"]:
        key = (it["slug"], it["version"])
        listing = rec["listings"].get(key) if it["version"] else None
        intent = rec["intents"].get(key) if it["version"] else None
        stage = stage18(it, listing, (it["slug"] in sold) if sold is not None else None)
        cat, fam = fams.get(it["slug"], (UNKNOWN, None))
        nxt = next_action(it)
        held = sorted({h.get("kind") for h in it.get("holds") or [] if h.get("kind")})
        derr = bool((it.get("evidence") or {}).get("derivation_error"))
        payload = {
            "slug": it["slug"], "version": it["version"], "title": it.get("title"),
            "head": it.get("head"),
            "state": UNKNOWN if derr else it["state"],
            "state_label": UNKNOWN if derr else it.get("label"),
            "stage": stage, "stage_label": STAGE18_LABEL.get(stage, UNKNOWN),
            "category": cat, "family": fam or None, "why": it.get("why"),
            "held": held, "holds": [{"kind": h.get("kind"), "why": h.get("why")}
                                    for h in it.get("holds") or []],
            "next_action": nxt,
            "physical_sample": (it.get("physical_sample") or {}).get("status", UNKNOWN),
            "tiers": {k: bool(v.get("ready") if k != "internal" else v.get("complete"))
                      for k, v in (it.get("tiers") or {}).items()},
            "evidence": evidence(it, versions.get(key), listing, intent),
            "cost_to_date_cad": (it.get("evidence") or {}).get("cost_to_date_cad"),
        }
        rows.append((it["slug"], it["version"] or "", it.get("title") or "",
                     1 if it.get("head") else 0, payload["state"], payload["state_label"],
                     stage, cat, fam or "", ",".join(held), nxt["action"], nxt["owner"],
                     (listing or {}).get("state") or "", json.dumps(payload, default=str)))
    con.executemany(f"INSERT INTO cat ({', '.join(_COLUMNS)}) VALUES "
                    f"({', '.join('?' * len(_COLUMNS))})", rows)
    con.commit()
    return {"con": con, "as_of": now.isoformat(), "gate_mode": inv["gate_mode"],
            "derived_total": inv["total"], "crosscheck": crosscheck(db, con),
            "sales_measured": sold is not None}


def crosscheck(db, con) -> dict:
    """Counts on the authoritative database vs the index. Any mismatch is reported, and the
    catalogue's totals are then UNKNOWN (never a pass)."""
    from sqlalchemy import func, select

    from ...core import listing_state
    from ...core.models import Listing, Product

    with db.session() as s:
        products = s.scalar(select(func.count()).select_from(Product))
        product_slugs = set(s.scalars(select(Product.slug)))
        live = s.scalar(select(func.count()).select_from(Listing).where(
            Listing.state.in_(listing_state.LIVE_ON_ETSY + ("active",))))
    indexed = {r[0] for r in con.execute("SELECT DISTINCT slug FROM cat")}
    idx_live = con.execute("SELECT COUNT(*) FROM cat WHERE stage IN "
                           "('etsy_draft_verified','live_on_etsy','sales_monitoring')"
                           ).fetchone()[0]
    # A row whose stage is UNKNOWN but whose listing row is live is an honest UNKNOWN
    # (counted in the UNKNOWN bucket), not a missing listing.
    live_states = listing_state.LIVE_ON_ETSY + ("active",)
    idx_unknown_pub = con.execute(
        f"SELECT COUNT(*) FROM cat WHERE stage = 'UNKNOWN' AND listing_state IN "
        f"({', '.join('?' * len(live_states))})", live_states).fetchone()[0]
    missing = sorted(product_slugs - indexed)
    checks = {
        "every_product_row_indexed": {"ok": not missing, "products_table": products,
                                      "missing": missing[:10]},
        "published_listings_match": {"ok": idx_live + idx_unknown_pub == live,
                                     "listings_table": live, "index": idx_live,
                                     "index_unknown": idx_unknown_pub},
    }
    return {"ok": all(c["ok"] for c in checks.values()), "checks": checks}


def reset() -> None:
    with _LOCK:
        old = _CACHE.get("index")
        _CACHE.update(at=0.0, index=None)
    if old is not None:
        old["con"].close()


def _index(db) -> dict:
    with _LOCK:
        if _CACHE["index"] is not None and time.monotonic() - _CACHE["at"] < TTL:
            return _CACHE["index"]
    idx = build_index(db)
    with _LOCK:
        old = _CACHE.get("index")
        _CACHE.update(at=time.monotonic(), index=idx)
    if old is not None and old is not idx:
        old["con"].close()
    return idx


# ---- query -------------------------------------------------------------------------------------

FILTERS = ("state", "stage", "category", "family", "held", "owner", "next_action")


def _int(v, default: int, lo: int, hi: int) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def _where(params: dict) -> tuple[str, list]:
    clauses, args = [], []
    for col, key in (("state", "state"), ("stage", "stage"), ("category", "category"),
                     ("family", "family"), ("next_owner", "owner"),
                     ("next_action", "next_action")):
        v = params.get(key)
        if v not in (None, ""):
            clauses.append(f"{col} = ?")
            args.append(str(v)[:120])
    held = params.get("held")
    if held == "none":
        clauses.append("held = ''")
    elif held == "any":
        clauses.append("held != ''")
    elif held not in (None, ""):
        clauses.append("(',' || held || ',') LIKE ?")
        args.append(f"%,{str(held)[:40]},%")
    q = str(params.get("q") or "").strip()[:120]
    if q:
        like = "%" + q.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        clauses.append("(lower(slug) LIKE ? ESCAPE '\\' OR lower(title) LIKE ? ESCAPE '\\')")
        args += [like, like]
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", args


def _group(con, col: str, where: str = "", args=()) -> dict:
    return {str(k): int(n) for k, n in con.execute(
        f"SELECT {col}, COUNT(*) FROM cat{where} GROUP BY {col}", list(args))}


def query(idx: dict, params: dict | None = None) -> dict:
    params = dict(params or {})
    con = idx["con"]
    size = _int(params.get("page_size"), PAGE_DEFAULT, 1, PAGE_MAX)
    where, args = _where(params)
    matching = con.execute(f"SELECT COUNT(*) FROM cat{where}", args).fetchone()[0]
    pages = max(1, -(-matching // size))
    page = _int(params.get("page"), 1, 1, pages)
    rows = [json.loads(r[0]) for r in con.execute(
        f"SELECT payload FROM cat{where} ORDER BY slug, version, n LIMIT ? OFFSET ?",
        args + [size, (page - 1) * size])]
    total = con.execute("SELECT COUNT(*) FROM cat").fetchone()[0]
    trusted = idx["crosscheck"]["ok"] and total == idx["derived_total"]
    by_stage = _group(con, "stage")
    held_counts = {}
    for kind in ("owner", "physical", "paid_approval", "policy"):
        held_counts[kind] = con.execute(
            "SELECT COUNT(*) FROM cat WHERE (',' || held || ',') LIKE ?",
            [f"%,{kind},%"]).fetchone()[0]
    totals = {
        "products": total,
        "by_state": {**{k: 0 for k in _pi().PRIMARY_STATES}, **_group(con, "state")},
        "by_stage": {**{k: 0 for k in STAGE18_KEYS}, **by_stage},
        "by_category": _group(con, "category"),
        "by_held": held_counts,
        "by_owner": _group(con, "next_owner"),
        "unknown": by_stage.get(UNKNOWN, 0),
    }
    out = {"tab": "CATALOGUE", "read_only": True, "as_of": idx["as_of"],
           "gate_mode": idx["gate_mode"], "status": "OK" if trusted else UNKNOWN,
           "stages": [{"key": k, "label": lbl} for k, lbl in STAGES18],
           "filters": {k: params.get(k) for k in FILTERS + ("q",) if params.get(k)},
           "page": page, "page_size": size, "pages": pages, "matching": matching,
           "items": rows, "crosscheck": idx["crosscheck"],
           "sales_measured": idx["sales_measured"],
           "totals": totals if trusted else {k: None for k in totals}}
    if not trusted:
        out["reason"] = ("the catalogue index does not match the authoritative database "
                         "(see crosscheck); totals are UNKNOWN")
    return out


def view(db, params: dict | None = None) -> dict:
    try:
        idx = _index(db)
    except Exception as exc:  # noqa: BLE001 - an underivable inventory is UNKNOWN, never empty
        return {"tab": "CATALOGUE", "read_only": True, "status": UNKNOWN,
                "reason": f"catalogue could not be built: {type(exc).__name__}: "
                          f"{str(exc)[:160]}",
                "items": [], "matching": None, "page": 1, "pages": None,
                "totals": {"products": None, "by_state": None, "by_stage": None,
                           "by_category": None, "by_held": None, "by_owner": None,
                           "unknown": None}}
    return query(idx, params)
