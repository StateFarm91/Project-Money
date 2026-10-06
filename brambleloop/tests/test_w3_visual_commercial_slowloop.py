"""Slow-loop commercial calibration of hero imagery (wave 3, lane H2; owner D-FB-16 item 5).

Free deterministic hero challengers run and are promoted on PROXY judges; lane K3's
ListingOutcome rows (impressions -> CTR -> favourites -> carts -> purchases -> conversion ->
refunds/feedback) then confirm or OVERTURN that promotion; UNKNOWN is never 0; the
three-month evolution report says what is measured and what is only internal.
Local, deterministic, no network, no provider, no spend.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
_TMP = tempfile.mkdtemp(prefix="w3_visual_commercial_slow_")
os.environ["BRAMBLELOOP_PHASE"] = "shadow"
os.environ.setdefault("BRAMBLELOOP_ARTIFACT_DIR", os.path.join(_TMP, "artifacts"))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import ListingOutcome  # noqa: E402
from brambleloop.visual.rnd import commercial as C  # noqa: E402
from brambleloop.visual.rnd import evolution as E  # noqa: E402
from brambleloop.visual.rnd import hero as H  # noqa: E402
from brambleloop.visual.rnd import loop as L  # noqa: E402
from brambleloop.visual.rnd import status as S  # noqa: E402

CLS = "coasters_tabletop"
_N = [0]
_CIRS = []
_TEMPLATE: list = []


def cirs():
    if not _CIRS:
        _CIRS.extend(L.catalogue(["hexagon_coasters"])[CLS])
    return _CIRS


def fresh_db():
    _N[0] += 1
    db = Database(f"sqlite:///{_TMP}/t{_N[0]}.sqlite")
    db.create_all()
    return db


def promoted_db():
    """A database in which a free hero challenger was promoted on PROXY evidence."""
    db = fresh_db()
    out = H.challenge(db, CLS, cirs=cirs())
    if not _TEMPLATE:
        _TEMPLATE.append(out)
    return db, out


def outcome(db, style, slug, start, *, impressions, visits, favourites=None, orders=None,
            detail=None):
    end = (date.fromisoformat(start) + timedelta(days=6)).isoformat()
    with db.session() as s:
        s.add(ListingOutcome(product_slug=slug, period_start=start, period_end=end,
                             impressions=impressions, visits=visits, favourites=favourites,
                             orders=orders, hero_style=style, styles=[style],
                             source=f"etsy-stats-export:test:{slug}:{start}",
                             detail=detail or {}))


def test_free_hero_challengers_run_through_gates_and_promote_on_proxy():
    db, out = promoted_db()
    assert {e["treatment"] for e in out["evaluated"]} == {
        "disclosed_finished_render_close", "disclosed_finished_render_airy"}, out
    assert all(e["accepted"] for e in out["evaluated"]), out
    assert set(out["queued"]) == {"lifestyle_scene", "styled_flatlay"}
    assert out["unavailable"] == ["owned_photo_hero"]
    promo = out["promotion"]
    assert promo["promoted"] and promo["basis"] == "proxy", promo
    inc = H.incumbent(db, CLS)
    assert inc["basis"] == "proxy" and inc["parent_id"] is not None
    for name in ("product_truth", "structure", "disclosure", "mobile_thumbnail"):
        assert inc["gates"][name]["status"] == "PASS", inc["gates"]
    used = inc["objective"]["used"]
    assert used and all(u["basis"] == "PROXY" for u in used.values()), used
    assert inc["objective"]["components"]["commercial"]["value"] is None
    assert any(les["kind"] == "hero_promoted" for les in L.lessons(db, CLS))
    st = H.status(db, CLS)
    assert st["incumbent_reading"].startswith("PROXY"), st


def test_marketplace_evidence_overturns_a_proxy_promotion():
    db, _ = promoted_db()
    inc = H.incumbent(db, CLS)
    parent = next(v for v in H.variants(db, CLS) if v["id"] == inc["parent_id"])
    # Before the floors are met the slow loop says UNKNOWN, and changes nothing.
    outcome(db, parent["style_key"], "hexagon-coaster-set", "2026-07-01",
            impressions=50, visits=2)
    outcome(db, inc["style_key"], "hexagon-coaster-set", "2026-08-01",
            impressions=40, visits=1)
    early = H.calibrate(db, CLS)
    assert early["verdict"] == "insufficient_evidence", early
    assert H.incumbent(db, CLS)["id"] == inc["id"]
    # Then the proxy-promoted hero is clearly worse where it matters: buyers.
    outcome(db, parent["style_key"], "hexagon-coaster-set", "2026-07-08",
            impressions=6000, visits=180, favourites=30, orders=9)
    outcome(db, inc["style_key"], "hexagon-coaster-set", "2026-08-08",
            impressions=6000, visits=60, favourites=6, orders=2)
    assert any(w["kind"] == "visual.rnd.hero_calibrate" for w in S.next_work(db))
    before = H.trust(db, CLS)
    res = H.calibrate(db, CLS)
    assert res["verdict"] == "overturned", res
    assert any(c["metric"] == "ctr" for c in res["checks"])
    now = H.incumbent(db, CLS)
    assert now["id"] == parent["id"] and now["basis"] == "market", now
    gone = next(v for v in H.variants(db, CLS) if v["id"] == inc["id"])
    assert gone["state"] == H.OVERTURNED and gone["basis"] == "market"
    after = H.trust(db, CLS)
    assert after["desirability"] == before["desirability"] / 2, (before, after)
    assert after["required_margin"] > before["required_margin"]
    # The overturned treatment is not re-promoted on proxy evidence.
    assert inc["treatment"] in H.overturned_treatments(db, CLS)
    again = H.challenge(db, CLS, cirs=cirs())
    assert any(r["treatment"] == inc["treatment"] for r in again["refused"]), again
    assert H.incumbent(db, CLS)["id"] == parent["id"]


def test_funnel_unknown_is_never_zero():
    empty = C.funnel([])
    for k in C.STAGES:
        assert empty[k]["value"] is None and empty[k]["reading"] == "UNKNOWN", (k, empty[k])
    db = fresh_db()
    outcome(db, f"{CLS}:x:1", "a", "2026-09-01", impressions=1000, visits=20)
    f = C.funnel(C.outcome_rows(db, style_key=f"{CLS}:x:1"))
    assert f["ctr"]["value"] == 0.02 and f["ctr"]["reading"] == "MEASURED"
    for k in ("favourites", "carts", "purchases", "conversion", "refunds", "feedback"):
        assert f[k]["value"] is None and f[k]["reading"] == "UNKNOWN", (k, f[k])
    outcome(db, f"{CLS}:x:1", "a", "2026-09-08", impressions=1000, visits=10, orders=0,
            detail={"carts": 3})
    f = C.funnel(C.outcome_rows(db, style_key=f"{CLS}:x:1"))
    assert f["purchases"]["value"] == 0 and f["purchases"]["reading"] == "MEASURED"
    assert f["carts"]["value"] == 3
    assert C.commercial_component([])["value"] is None


def test_summary_and_three_month_evolution_report():
    db, _ = promoted_db()
    summ = S.summary(db)
    json.dumps(summ)
    com = summ["commercial"]
    assert com["objective"]["non_tradeable"] and com["sequence_policy"]["slots"][0] == "hero_aspiration"
    assert com["judges"]["basis"] == "PROXY"
    assert com["heroes"][CLS]["incumbent"]["basis"] == "proxy"
    evo = summ["evolution"]["classes"][CLS]
    assert evo["verdict"] == "IMPROVING_INTERNALLY", evo
    assert evo["ctr_trend"]["value"] is None and evo["ctr_trend"]["reading"] == "UNKNOWN"
    assert evo["promoted_techniques"] and evo["paid_challengers_waiting"]
    for b in evo["ctr_conversion_by_month"]:
        assert b["ctr"]["value"] is None and b["ctr"]["reading"] == "UNKNOWN"
    # With measured months, the verdict comes from the marketplace, not from the proxies.
    now = datetime(2026, 10, 6, tzinfo=timezone.utc)
    style = H.incumbent(db, CLS)["style_key"]
    outcome(db, style, "m1", "2026-07-10", impressions=5000, visits=50)
    outcome(db, style, "m3", "2026-09-20", impressions=5000, visits=120)
    rep = E.report(db, now=now)
    c = rep["classes"][CLS]
    assert c["verdict"] == "MATERIALLY_BETTER" and c["ctr_trend"]["reading"] == "MEASURED", c
    assert rep["status"] == "MATERIALLY_BETTER"
    assert E.report(object())["status"] == "UNKNOWN"


if __name__ == "__main__":
    import time

    failures = 0
    tests = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
    for name, test in tests:
        started = time.time()
        try:
            test()
            print("OK  ", name, f"{time.time() - started:.1f}s")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            import traceback

            traceback.print_exc()
            print("FAIL", name, type(exc).__name__, str(exc)[:500])
    print(f"{len(tests) - failures}/{len(tests)} passing")
    shutil.rmtree(_TMP, ignore_errors=True)
    sys.exit(bool(failures))
