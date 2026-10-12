"""W4-CCMKTLAB: F-684 Marketing Laboratory in the Command Center.

Criterion (registry F-684, quoted): "organic/paid growth, Share & Save, Offsite Ads, social,
seasonal campaigns and experiments with hypothesis, baseline, budget, attribution and
stop/scale rules."

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_w4_ccmktlab.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
_TMP = tempfile.mkdtemp(prefix="w4_ccmktlab_")
SIX = ("hypothesis", "baseline", "budget", "attribution", "stop_rule", "scale_rule")


def _db():
    from brambleloop.core.db import Database

    db = Database(f"sqlite:///{_TMP}/v{len(os.listdir(_TMP))}.sqlite")
    db.create_all()
    return db


def test_every_named_channel_carries_the_six_fields_first():
    from brambleloop.app.command_center import marketing_lab as M

    env = M.channels(_db())
    rows = {r["channel"]: r for r in env["items"]}
    assert set(rows) == {"organic", "paid", "share_and_save", "offsite_ads", "social",
                         "seasonal"}, sorted(rows)
    for ch, r in rows.items():
        keys = list(r)
        assert keys[0] == "label" and tuple(keys[1:7]) == SIX, (ch, keys[:8])
        for f in SIX:
            assert r[f] not in (None, ""), (ch, f)
        assert not any(isinstance(v, dict) for v in r.values()), (ch, r)  # flat rows render
    assert env["can_spend"] is False


def test_no_traffic_means_unknown_baselines_never_zero_and_paid_is_gated():
    from brambleloop.app.command_center import marketing_lab as M
    from brambleloop.commerce import paid_media as pm

    rows = {r["channel"]: r for r in M.channels(_db())["items"]}
    for ch, r in rows.items():
        assert r["baseline"] == "UNKNOWN", (ch, r["baseline"])
        assert r["why"], ch
    paid = rows["paid"]
    assert paid["state"] == "GATED" and paid["spend_executed_cad"] == 0.0, paid
    caps = pm.CONSERVATIVE_CAPS
    assert f"CA${caps.daily_cad:.2f}/day" in paid["budget"], paid["budget"]
    assert f"CA${caps.max_cac_cad:.2f}" in paid["stop_rule"], paid["stop_rule"]
    assert str(caps.min_conversions_before_scaling) in paid["scale_rule"]
    terms = pm.offsite_ads_terms()
    assert f"{terms['attribution_window_days']} days" in rows["offsite_ads"]["attribution"]
    assert rows["share_and_save"]["state"] == "UNMEASURED"
    assert rows["organic"]["state"] == "NOT_LIVE"
    assert rows["seasonal"]["next_event"], rows["seasonal"]


def test_registered_experiments_show_rules_and_unmeasured_attribution():
    from brambleloop.app.command_center import marketing_lab as M
    from brambleloop.growth import experiments as E

    db = _db()
    assert M.experiments(db)["status"] == "UNKNOWN"
    e = E.Experiment(key="placemat.price", hypothesis="CA$6.50 converts no worse",
                     metric="conversion", design="pre_post", success_threshold=0.03,
                     failure_threshold=0.01, minimum_sample=100,
                     stop_on=date.today() + timedelta(days=30), owner="growth",
                     decision="keep or revert the price")
    E.persist(db, e, product_slug="placemat", gate_open=True)
    env = M.experiments(db)
    assert env["status"] == "OK", env
    row = env["items"][0]
    keys = list(row)
    assert keys[0] == "title" and tuple(keys[1:7]) == SIX, keys
    assert row["hypothesis"] == "CA$6.50 converts no worse"
    assert row["baseline"] == "UNKNOWN"
    assert row["attribution"].startswith("UNMEASURED"), row["attribution"]
    assert row["stop_rule"] == "stop when conversion <= 0.01 after 100 sample(s)", row
    assert row["scale_rule"] == "retain/scale when conversion >= 0.03 after 100 sample(s)", row


def test_insights_tab_carries_the_lab_and_the_view_orders_it():
    from brambleloop.app.command_center import tabs

    sec = tabs.insights(_db())["sections"]
    assert sec["marketing_lab_channels"]["provider"] == "command_center.marketing_lab.channels"
    assert "marketing_lab_experiments" in sec
    js = (ROOT / "src/brambleloop/app/command_center/static/js/views/insights.js").read_text()
    assert '["marketing_lab_channels", "Marketing lab: channels"]' in js
    assert '["marketing_lab_experiments", "Marketing lab: experiments"]' in js


def test_the_lab_calls_no_spend_or_scheduling_path():
    src = (ROOT / "src/brambleloop/app/command_center/marketing_lab.py").read_text()
    for forbidden in ("authorise_spend(", "propose(", "enqueue", "schedule(", "requests.",
                      "httpx", "EtsyClient"):
        assert forbidden not in src, forbidden


if __name__ == "__main__":
    import time

    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        t0 = time.time()
        try:
            t()
            print(f"OK   {t.__name__} {time.time() - t0:.1f}s")
        except Exception as exc:  # noqa: BLE001
            import traceback; traceback.print_exc()
            failed += 1
            print(f"FAIL {t.__name__} {type(exc).__name__} {str(exc)[:500]}")
    print(f"{len(tests) - failed}/{len(tests)} passing")
    sys.exit(1 if failed else 0)
