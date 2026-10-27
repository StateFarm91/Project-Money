"""W4-CLOSE6: Etsy Ads eligibility, recheck and Ads-credit accounting (F-685, F-686, F-688).

  F-685  "persist etsy_ads_status, eligible_from/next_check, evidence_source and
          last_verified_at. ... do not hard-code a derived date as authoritative."
  F-686  "automatically re-verify Etsy eligibility at/near the expected unlock; countdown
          reaching zero alone cannot change state to ELIGIBLE."
  F-688  "Etsy Plus included Ads credit is separate from owner cash; record official
          entitlement, locally displayed CAD value, cycle, used/expired credit and incremental
          cash spend."

The mapping called all three MISSING. F-685 and the recheck half of F-686 were deployed on
b931d17 (`growth/ads_readiness.py`, hourly cadence `marketing.ads_readiness`): production
raised OwnerAction #32 on 2026-10-11 when the countdown came due, without setting ELIGIBLE.
But the re-verification could never finish. The owner action asks the owner to record Etsy's
eligibility message, and no route accepted that reading, so `record_evidence` had no caller.
F-688 had only a generic credit wallet: no cycle, no displayed CAD value, no used or expired
credit, no incremental cash. This branch adds POST /api/ads/eligibility,
`finance.credits.ads_credit` (with POST /api/finance/ads-credit), and these tests.

Local, deterministic; no network, no spend.
Run: cd brambleloop && PYTHONPATH=src:tests $PY tests/test_w4_close6_ads.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import socket
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

_TMP = tempfile.mkdtemp(prefix="w4_close6_ads_")
for _k in list(os.environ):
    if _k.startswith(("ANTHROPIC_API", "ETSY", "OPENAI")):
        os.environ.pop(_k)


def _no_network(*_a, **_k):
    raise OSError("network refused by the CLOSE6 harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from sqlalchemy import select  # noqa: E402

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import CostEntry, OwnerAction, SpendLimit  # noqa: E402
from brambleloop.finance import credits  # noqa: E402
from brambleloop.growth import ads_readiness as ads  # noqa: E402

TOKEN = "close6-operator-token-0123456789abcdef"


def _db(name: str) -> Database:
    db = Database(f"sqlite:///{_TMP}/{name}.sqlite")
    db.create_all()
    return db


_APP: dict = {}


def _app():
    if "c" not in _APP:
        os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{_TMP}/route.sqlite"
        os.environ["BRAMBLELOOP_EMBEDDED_WORKER"] = "0"
        from fastapi.testclient import TestClient

        from brambleloop.agents.registry import Registry
        from brambleloop.app import main

        main.db.create_all()
        Registry(main.db).seed_defaults()
        _APP.update(c=TestClient(main.app), main=main)
    os.environ["BRAMBLELOOP_OPS_TOKEN"] = TOKEN
    return _APP["c"], _APP["main"]


AUTH = {"authorization": f"Bearer {TOKEN}"}


# ---- F-685 -----------------------------------------------------------------------------------

def test_f685_the_four_fields_are_persisted_and_the_reported_date_is_not_authoritative():
    path = "persist"
    db = _db(path)
    now = datetime(2026, 10, 1, tzinfo=timezone.utc)
    ads.tick(db, now=now)
    again = Database(f"sqlite:///{_TMP}/{path}.sqlite")      # a fresh process's view
    snap = ads.state(again, now=now)
    for field in ("etsy_ads_status", "eligible_from", "evidence_source", "last_verified_at"):
        assert field in snap, (field, snap)
    assert snap["etsy_ads_status"] == "WAITING_REPORTED", snap
    assert snap["eligible_from"].startswith("2026-10-04"), "the reported recheck date persists"
    assert snap["date_is_estimate"] is True and snap["last_verified_at"] is None
    gate = ads._eligibility_gate(again, now)
    assert gate["status"] == ads.UNKNOWN and "countdown is not eligibility" in gate["why"]


# ---- F-686 -----------------------------------------------------------------------------------

def test_f686_the_countdown_reaching_zero_raises_a_recheck_and_never_eligible():
    db = _db("recheck")
    due = ads.REPORTED_RECHECK
    ads.tick(db, now=due - timedelta(days=1))
    assert ads.state(db, now=due)["etsy_ads_status"] == "WAITING_REPORTED"
    for h in range(3):                                      # hourly, past the countdown
        snap = ads.tick(db, now=due + timedelta(hours=h))
        assert snap["etsy_ads_status"] == "RECHECK_REQUIRED", snap
        assert snap["activation_authorised"] is False
    with db.session() as s:
        acts = list(s.scalars(select(OwnerAction).where(
            OwnerAction.requirement_key == ads.REFRESH_KEY, OwnerAction.done == False)))  # noqa: E712
    assert len(acts) == 1, "one recheck request, deduplicated across hourly ticks"
    assert "record the current eligibility message" in acts[0].action


def test_f686_the_owner_reading_completes_the_recheck_through_the_route():
    c, main = _app()
    now = datetime.now(timezone.utc)
    ads.tick(main.db, now=ads.REPORTED_RECHECK + timedelta(hours=1))   # the recheck is due
    url = "/api/ads/eligibility"
    reading = {"status": "WAITING", "verified_at": (now - timedelta(minutes=5)).isoformat(),
               "eligible_from": (now + timedelta(days=3)).isoformat(),
               "evidence": "Shop Manager > Marketing > Etsy Ads: '3 days left' read 2026-10-20"}
    assert c.post(url, json=reading).status_code in (401, 403, 503), "operator credential"
    stale = {**reading, "verified_at": (now - timedelta(days=2)).isoformat()}
    r = c.post(url, json=stale, headers=AUTH)
    assert r.status_code == 400 and "24 hours" in r.json()["error"], r.text
    r = c.post(url, json={**reading, "eligible_from": None}, headers=AUTH)
    assert r.status_code == 400, "WAITING without a future recheck date is refused"
    r = c.post(url, json=reading, headers=AUTH)
    assert r.status_code == 200, r.text
    snap = r.json()
    assert snap["etsy_ads_status"] == "WAITING" and snap["last_verified_at"]
    assert snap["evidence_source"].startswith("Shop Manager")
    with main.db.session() as s:
        open_acts = list(s.scalars(select(OwnerAction).where(
            OwnerAction.requirement_key == ads.REFRESH_KEY, OwnerAction.done == False)))  # noqa: E712
    assert open_acts == [], "the owner's reading satisfies the recheck request"
    # a later tick at the new countdown again asks; it does not promote itself to ELIGIBLE
    later = ads.tick(main.db, now=now + timedelta(days=3, hours=1))
    assert later["etsy_ads_status"] == "RECHECK_REQUIRED"
    # ELIGIBLE comes only from a reading, and authorises nothing
    r = c.post(url, json={"status": "ELIGIBLE", "verified_at": now.isoformat(),
                          "evidence": "Shop Manager: 'You can now advertise' read 2026-10-20"},
               headers=AUTH)
    assert r.status_code == 200 and r.json()["etsy_ads_status"] == "ELIGIBLE", r.text
    assert r.json()["activation_authorised"] is False


# ---- F-688 -----------------------------------------------------------------------------------

def test_f688_a_cycle_records_entitlement_displayed_value_use_expiry_and_cash():
    db = _db("credit")
    now = datetime(2026, 11, 20, tzinfo=timezone.utc)
    credits.record_ads_credit_cycle(
        db, cycle_start="2026-10-01", cycle_end="2026-11-01", entitlement_usd=5.0,
        displayed_cad=6.93, used_displayed_cad=4.10,
        evidence_ref="Shop Manager > Settings > Billing: Etsy Plus credit, October")
    credits.record_ads_credit_cycle(
        db, cycle_start="2026-11-01", cycle_end="2026-12-01", entitlement_usd=5.0,
        displayed_cad=6.93, evidence_ref="Shop Manager: November credit")
    with db.session() as s:
        s.add(CostEntry(agent="ads", kind="ads", amount_cad=9.00, provider="etsy",
                        at=datetime(2026, 10, 15, tzinfo=timezone.utc)))
        s.add(CostEntry(agent="ads", kind="ads", amount_cad=2.00, provider="etsy",
                        at=datetime(2026, 11, 10, tzinfo=timezone.utc)))
        s.add(SpendLimit(scope="ads", daily_cap_cad=0.0, lifetime_cap_cad=0.0))
    out = credits.ads_credit(db, now=now)
    oct_, nov = out["cycles"]
    assert oct_["official_entitlement_usd"] == 5.0 and oct_["displayed_cad"] == 6.93
    assert "converted_cad_at_assumed_rate" in oct_, "our conversion is labelled, not the display"
    assert (oct_["cycle_start"], oct_["cycle_end"]) == ("2026-10-01", "2026-11-01")
    assert oct_["used_cad"] == 4.10 and oct_["used_basis"] == "etsy_reported"
    assert oct_["cycle_ended"] and oct_["expired_cad"] == round(6.93 - 4.10, 6)
    assert oct_["recorded_ad_spend_cad"] == 9.0
    assert oct_["incremental_cash_spend_cad"] == round(9.0 - 4.10, 6)
    # an unreported use is UNKNOWN, never 0, and so is the cash beyond it
    assert nov["used_cad"] is None and nov["used_basis"] == "UNKNOWN"
    assert nov["expired_cad"] is None and nov["incremental_cash_spend_cad"] is None
    assert out["owner_cash_is_separate"] is True and out["ceilings_changed"] == 0
    with db.session() as s:
        lim = s.scalar(select(SpendLimit).where(SpendLimit.scope == "ads"))
        assert (lim.daily_cap_cad, lim.lifetime_cap_cad) == (0.0, 0.0), "a credit is no budget"
    assert credits.wallet(db, now=now)["ads_credit"]["cycles"] == out["cycles"]
    for bad in ({"used_displayed_cad": 7.0}, {"evidence_ref": ""},
                {"cycle_end": "2026-09-01"}, {"displayed_cad": 0}):
        args = dict(cycle_start="2026-12-01", cycle_end="2027-01-01", entitlement_usd=5.0,
                    displayed_cad=6.93, evidence_ref="x")
        args.update(bad)
        try:
            credits.record_ads_credit_cycle(db, **args)
            raise AssertionError(f"accepted {bad}")
        except credits.CreditRefused:
            pass


def test_f688_the_route_records_a_cycle_and_the_spend_report_carries_it():
    c, main = _app()
    body = {"cycle_start": "2026-10-01", "cycle_end": "2026-11-01", "entitlement_usd": 5,
            "displayed_cad": 6.93, "evidence": "Shop Manager billing, read 2026-10-20"}
    url = "/api/finance/ads-credit"
    assert c.post(url, json=body).status_code in (401, 403, 503)
    assert c.post(url, json={**body, "evidence": ""}, headers=AUTH).status_code == 400
    r = c.post(url, json=body, headers=AUTH)
    assert r.status_code == 200, r.text
    assert r.json()["ads_credit"]["cycles"][0]["displayed_cad"] == 6.93
    from brambleloop.finance import spend_report

    gov = spend_report.governance(main.db)
    assert gov["credits"]["ads_credit"]["cycles"][0]["official_entitlement_usd"] == 5.0


if __name__ == "__main__":
    fails = 0
    ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            ran += 1
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    assert ran >= 5, "no tests collected"
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing of {ran}")
    sys.exit(1 if fails else 0)
