"""MISSION-CONTROL-2: the one-screen Mission Control home (GET /api/cc/mission).

Three things, nothing else:

1. **The six P0 conditions**, each a live verdict PASS / FAIL / UNKNOWN with the reason and the
   reader it came from. Every verdict is computed from a reader the system already trusts --
   the P0 board sections (`p0_board.SECTIONS`) and the `/api/verify` publication checks
   (`app.verify_checks.publication_checks`). No new evidence is invented here.
2. **Today's counts** (UTC day so far) from the daily ledger (`ops.daily_ledger.ledger`):
   scans, products started and advanced, certified, PDFs, images, listing packages, Etsy
   drafts, lessons and failures. UNKNOWN is never 0.
3. **The owner queue in one line**: how many rows "Approve all eligible" would approve now, and
   how many it never approves, by category (`approve_all.preview`).

UNKNOWN is never a pass: a reader that raises, or a section that reads UNKNOWN, gives UNKNOWN.
Read-only, owner session (the `/api/cc` default-deny gate).
"""
from __future__ import annotations

from datetime import datetime, timezone

PASS, FAIL, UNKNOWN = "PASS", "FAIL", "UNKNOWN"

#: (id, title, sources). The order is the order the owner reads them.
CONDITIONS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("running", "Production is running and healthy", ("p0_board.running",)),
    ("research", "All mandatory shops scanned on time", ("p0_board.shops",)),
    ("factory", "Products are advancing through the factory",
     ("p0_board.development", "ops.daily_ledger")),
    ("certified", "Certified releases with PDFs and images",
     ("p0_board.releases", "p0_board.assets")),
    ("etsy", "Etsy drafts exist for certified releases", ("p0_board.etsy",)),
    ("safety", "Publication safety (the /api/verify checks)",
     ("app.verify_checks.publication_checks",)),
)

#: Today's counts: (id, label, ledger metric keys summed). UNKNOWN when any part is UNKNOWN.
TODAY: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("scans", "Scans", ("scans_succeeded",)),
    ("products_started", "Products started", ("products_started",)),
    ("products_advanced", "Products advanced", ("advanced:*",)),
    ("certified", "Certified", ("certifications",)),
    ("pdfs", "PDFs (US + UK)", ("pdfs_us", "pdfs_uk")),
    ("images", "Images", ("images_generated",)),
    ("packages", "Listing packages", ("listing_packages",)),
    ("etsy_drafts", "Etsy drafts", ("etsy_drafts",)),
    ("lessons", "Lessons", ("lessons_learned",)),
    ("failures", "Failures", ("failures",)),
)


def _now(now=None) -> datetime:
    now = now or datetime.now(timezone.utc)
    return now if now.tzinfo else now.replace(tzinfo=timezone.utc)


def _sections(db, now, names) -> dict:
    from ...core import build
    from . import p0_board

    deployed = build.commit() not in ("", build.UNKNOWN)
    readers = dict(p0_board.SECTIONS)
    out = {}
    for n in names:
        try:
            out[n] = p0_board._section(n, readers[n](db, now), deployed)
        except Exception as exc:  # noqa: BLE001 - unreadable is UNKNOWN, never a pass
            out[n] = {"state": UNKNOWN, "why": f"could not be read: {type(exc).__name__}"}
    return out


def _v(verdict: str, why: str) -> dict:
    return {"verdict": verdict, "why": why}


def _running(sec) -> dict:
    h = sec.get("health") or {}
    if sec.get("state") == UNKNOWN or not h.get("fresh"):
        return _v(UNKNOWN, sec.get("why") or "no health sweep in the last 45 minutes")
    if h.get("state") == "healthy":
        return _v(PASS, f"healthy; commit {sec.get('commit') or 'unknown'}")
    return _v(FAIL, f"health {h.get('state')}: {', '.join(map(str, h.get('bad') or []))[:200]}")


def _research(sec) -> dict:
    st = sec.get("state")
    if st == "OK":
        return _v(PASS, f"{sec.get('fresh')}/{sec.get('required')} shops fresh, none failing")
    if st == "DEGRADED":
        return _v(FAIL, f"{sec.get('fresh')}/{sec.get('required')} fresh, {sec.get('failing')} "
                        f"failing, {sec.get('failures_unknown')} with failures unknown")
    return _v(UNKNOWN, sec.get("why") or "no shop reading")


def _factory(sec, advanced_2d) -> dict:
    if sec.get("state") != "OK":
        return _v(UNKNOWN, sec.get("why") or "the lifecycle could not be read")
    staged = sum(int(v or 0) for v in (sec.get("count_by_stage") or {}).values())
    if advanced_2d == UNKNOWN:
        return _v(UNKNOWN, f"{staged} products in stages; today's advances unknown")
    if not staged:
        return _v(FAIL, "no product is recorded in any lifecycle stage")
    if advanced_2d <= 0:
        return _v(FAIL, f"{staged} products in stages, none advanced today or yesterday")
    return _v(PASS, f"{staged} products in stages; {advanced_2d} advances today and yesterday")


def _certified(rel, assets) -> dict:
    if rel.get("state") == UNKNOWN:
        return _v(UNKNOWN, rel.get("why") or "releases unreadable")
    if not rel.get("certified"):
        return _v(FAIL, "no certified release")
    n = len(rel["certified"])
    if assets.get("state") == UNKNOWN or not assets.get("counts"):
        return _v(UNKNOWN, f"{n}+ certified; PDF and gallery readiness unknown")
    pending = len(assets.get("not_proven") or [])
    if assets.get("state") == "OK" and not pending:
        return _v(PASS, f"{n}+ certified; every PDF and gallery item proven")
    return _v(FAIL, f"{n}+ certified; {pending} PDF/gallery items not proven "
                    f"(store readiness {assets.get('state')})")


def _etsy(sec) -> dict:
    if sec.get("state") == UNKNOWN:
        return _v(UNKNOWN, sec.get("why") or "listings unreadable")
    drafts, total = sec.get("drafts_on_etsy"), sec.get("remote_total")
    if total:
        return _v(PASS, f"{total} listings on Etsy ({drafts} drafts, "
                        f"{sec.get('live_on_etsy')} live)")
    return _v(FAIL, "no listing has an Etsy listing id yet")


def _safety(db) -> dict:
    try:
        from .. import verify_checks

        checks = verify_checks.publication_checks(db)
    except Exception as exc:  # noqa: BLE001
        return _v(UNKNOWN, f"verify checks unreadable: {type(exc).__name__}")
    parts = [checks.get(k) or {} for k in ("phase", "published", "revenue")]
    bad = [p.get("check") or "?" for p in parts if p.get("ok") is not True]
    if not bad:
        return _v(PASS, "; ".join(p["check"] for p in parts))
    return _v(FAIL, "failing: " + ", ".join(bad))


def _today(db, now) -> tuple[list[dict], object, dict]:
    from ...ops import daily_ledger

    try:
        led = daily_ledger.ledger(db, now=now)
    except Exception as exc:  # noqa: BLE001
        why = f"daily ledger unreadable: {type(exc).__name__}"
        return ([{"id": i, "label": lbl, "value": UNKNOWN} for i, lbl, _k in TODAY], UNKNOWN,
                {"error": why})
    metrics, days = led.get("metrics") or {}, led.get("days") or []
    today = led.get("today")

    def keys(spec):
        if spec == ("advanced:*",):
            return tuple(k for k in metrics if k.startswith("advanced:")) or ("advanced:",)
        return spec

    def value(spec, day):
        total = 0
        for k in keys(spec):
            v = ((metrics.get(k) or {}).get("days") or {}).get(day, UNKNOWN)
            if not isinstance(v, (int, float)) or isinstance(v, bool):
                return UNKNOWN
            total += v
        return total

    rows = [{"id": i, "label": lbl, "value": value(spec, today)} for i, lbl, spec in TODAY]
    adv = [value(("advanced:*",), d) for d in days[-2:]]
    adv2 = UNKNOWN if not adv or UNKNOWN in adv else sum(adv)
    return rows, adv2, {"day": today, "partial": True, "as_of": led.get("as_of")}


def view(db, *, now: datetime | None = None) -> dict:
    """The Mission Control home. Read-only."""
    now = _now(now)
    secs = _sections(db, now, ("running", "shops", "development", "releases", "assets",
                               "etsy"))
    today, advanced_2d, today_meta = _today(db, now)
    verdicts = {
        "running": _running(secs["running"]),
        "research": _research(secs["shops"]),
        "factory": _factory(secs["development"], advanced_2d),
        "certified": _certified(secs["releases"], secs["assets"]),
        "etsy": _etsy(secs["etsy"]),
        "safety": _safety(db),
    }
    conditions = [{"id": cid, "title": title, "sources": list(src), **verdicts[cid]}
                  for cid, title, src in CONDITIONS]
    try:
        from . import approve_all

        pv = approve_all.preview(db, now=now, include_cards=False)
        queue = {"eligible": pv["eligible_count"], "never_bulk": pv["excluded_count"],
                 "never_bulk_by_category": pv["excluded_by_category"],
                 "href": "#/approvals"}
    except Exception as exc:  # noqa: BLE001
        queue = {"eligible": None, "never_bulk": None,
                 "why": f"owner queue unreadable: {type(exc).__name__}", "href": "#/approvals"}
    tally = {k: sum(1 for c in conditions if c["verdict"] == k) for k in (PASS, FAIL, UNKNOWN)}
    return {"tab": "MISSION", "read_only": True, "generated_at": now.isoformat(),
            "conditions": conditions, "tally": tally,
            "overall": (PASS if tally[PASS] == len(conditions) else
                        FAIL if tally[FAIL] else UNKNOWN),
            "today": today, "today_meta": today_meta, "owner_queue": queue,
            "inventory_href": "#/catalogue",
            "rule": "UNKNOWN is never a pass and never 0"}
