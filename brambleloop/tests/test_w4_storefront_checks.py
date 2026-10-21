"""W-LAUNCHPREP §B4 (E1-E7) and W-AGENTAUDIT E-6/E-8: storefront checks that told the owner
completed work was missing.

Every fix replaces "a blank field = missing" with an evidence path that exists; nothing
missing becomes PASS, and nothing is marked done that the evidence does not show.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
_TMP = tempfile.mkdtemp(prefix="w4_storefront_")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, Incident, OwnerAction  # noqa: E402
from brambleloop.intel import etsy_surfaces as es  # noqa: E402
from brambleloop.runtime import etsy_ops  # noqa: E402

NOW = time.time()
_N = [0]


def _db():
    _N[0] += 1
    db = Database(f"sqlite:///{_TMP}/sf{_N[0]}.db")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _shop(**over) -> dict:
    """Production's 2026-10-20 reading, as LAUNCHPREP §B1 records it."""
    body = {
        "icon_url_fullxfull": "https://i.etsystatic.com/icon.jpg",
        "image_url_760x100": "",                  # a Big Banner: getShop cannot show it
        "title": "Machine-checked crochet patterns",
        "announcement": "Every pattern is compiled and checked before release.",
        "sale_message": "Thank you for your order.",
        "digital_sale_message": "Your file is on your Purchases page.",
        "policy_payment": "Etsy handles payment.",
        "policy_shipping": "",                    # no editable box for a digital-only shop
        "policy_refunds": "Digital items cannot be returned; errors are corrected.",
        "policy_privacy": "Buying does not put you on a list.",
        "policy_additional": "Licence: you may sell the items you make.",   # Etsy holds one
        "is_etsy_payments_onboarded": True, "is_vacation": False, "currency_code": "CAD",
        "listing_active_count": 0, "digital_listing_count": 0,
    }
    body.update(over)
    return body


def _iso(days_ago: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


def _assess(body, **context):
    return es.assess_shop({"observed_at": NOW, "shop": body}, now=NOW, context=context)


def _result(status, key):
    return next(c for c in status.checks if c.key == key).result


# ---- E1: the banner ---------------------------------------------------------------------

def test_e1_a_blank_banner_is_missing_evidence_not_a_failure():
    st = _assess(_shop())
    assert _result(st, "banner_set") == es.UNEVIDENCED
    assert "banner_set" not in {c.key for c in st.failures}
    assert st.green is False                                   # never a pass


def test_e1_the_owners_fresh_banner_confirmation_is_the_evidence():
    conf = {"banner": {"confirmed_at": _iso(3), "statement": "Big Banner set on 2026-10-11"}}
    assert _result(_assess(_shop(), owner_confirmed=conf), "banner_set") == es.PASS
    stale = {"banner": {"confirmed_at": _iso(120), "statement": "old"}}
    assert _result(_assess(_shop(), owner_confirmed=stale), "banner_set") == es.UNEVIDENCED
    other = {"about": {"confirmed_at": _iso(1)}}
    assert _result(_assess(_shop(), owner_confirmed=other), "banner_set") == es.UNEVIDENCED
    assert _result(_assess(_shop(image_url_760x100="https://x/b.jpg")), "banner_set") == es.PASS


def test_e1_live_drift_resolves_the_blank_banner_finding_on_the_confirmation():
    from brambleloop.runtime.worker import JobContext
    from brambleloop.queue.durable import JobQueue
    from brambleloop.store_foundation import shop_sync

    db = _db()
    etsy_ops.store_reading(db, etsy_ops.SHOP_READING, {"observed_at": NOW, "shop": _shop()})

    def run(key):
        job = JobQueue(db).enqueue("store_operator", "store.live_drift", {},
                                   idempotency_key=key)
        return etsy_ops.handle_store_live_drift(JobContext(job=job, db=db, queue=JobQueue(db),
                                                           registry=Registry(db), phase=None))

    sig = f"{etsy_ops.LIVE_OWNER_FIELD_BLANK}shop_banner"
    run("d1")
    with db.session() as s:
        opened = s.scalar(select(Incident).where(Incident.signature == sig,
                                                 Incident.resolved.is_(False)))
    assert opened is not None, "the fixture should reproduce the blank-banner finding"
    shop_sync.confirm(db, "banner", actor="owner:test")
    run("d2")
    with db.session() as s:
        assert s.scalar(select(Incident).where(Incident.signature == sig,
                                               Incident.resolved.is_(False))) is None


# ---- E2: the delivery policy ------------------------------------------------------------

def _delivery(box: bool, days_ago: float = 1, complete: bool = True) -> dict:
    return {"observed_at": _iso(days_ago), "complete": complete,
            "values": {"editable_delivery_box": box}}


def test_e2_a_digital_only_shop_with_no_delivery_box_reads_not_applicable_on_evidence():
    st = _assess(_shop(), delivery_policy=_delivery(False))
    assert _result(st, "policy_shipping_set") == es.NOT_APPLICABLE_HERE


def test_e2_without_that_evidence_a_blank_delivery_policy_still_fails():
    for ctx in ({}, {"delivery_policy": _delivery(True)},                 # a box exists
                {"delivery_policy": _delivery(False, days_ago=120)},      # stale reading
                {"delivery_policy": _delivery(False, complete=False)}):   # incomplete
        assert _result(_assess(_shop(), **ctx), "policy_shipping_set") == es.FAIL, ctx
    # a physical listing exists, or nothing else tells the buyer: it applies
    assert _result(_assess(_shop(listing_active_count=3, digital_listing_count=2),
                           delivery_policy=_delivery(False)), "policy_shipping_set") == es.FAIL
    assert _result(_assess(_shop(digital_sale_message=""), delivery_policy=_delivery(False)),
                   "policy_shipping_set") == es.FAIL
    assert _result(_assess({k: v for k, v in _shop().items() if k != "listing_active_count"},
                           delivery_policy=_delivery(False)), "policy_shipping_set") == es.FAIL


def test_e2_the_delivery_policy_reading_is_validated():
    from brambleloop.commerce import shop_observations as SO

    db = _db()
    try:
        SO.record(db, page="delivery_policy", observed_at=_iso(0.01), complete=True,
                  values={"editable_delivery_box": "no"}, statement="x")
        raise AssertionError("a non-boolean reading was accepted")
    except SO.ObservationRefused:
        pass
    SO.record(db, page="delivery_policy", observed_at=_iso(0.01), complete=True,
              values={"editable_delivery_box": False}, statement="Policy settings")
    ctx = etsy_ops.shop_check_context(db)
    assert ctx["delivery_policy"]["values"] == {"editable_delivery_box": False}


# ---- E3: policy_additional ----------------------------------------------------------------

def test_e3_policy_additional_is_not_a_readiness_check_and_its_content_is_checked():
    from brambleloop.commerce import policy_consistency

    st = _assess(_shop())
    assert "policy_additional_unset" not in {c.key for c in st.checks}
    assert "policy_additional_unset" not in etsy_ops.CLOSES_ON_SHOP_CHECKS[
        "policy_settings_paste"]
    bad = policy_consistency.check(_shop(policy_additional="Personal use only."))
    assert any(c["field"] == "policy_additional" and c["fact"] == "sell_what_you_make"
               for c in bad["contradictions"]), bad["contradictions"]
    # the write-side refusal stays: the company never sends policy_additional for this shop
    from brambleloop.commerce import shop_package
    assert not str(shop_package.shop_text()["policy_additional"] or "").strip()


# ---- E4: only the failing checks' owner actions ---------------------------------------------

def test_e4_a_failing_check_opens_only_its_own_owner_action():
    from brambleloop.launch import readiness as R

    db = _db()
    st = _assess(_shop(image_url_760x100="https://x/b.jpg"), delivery_policy=_delivery(False))
    etsy_ops.store_reading(db, etsy_ops.SHOP_READING,
                           {"observed_at": NOW, "shop": _shop(), "status": st.to_dict()})
    req = R.etsy_first_sale_surfaces(db, now=NOW)
    assert req.evidence["shop_checks_failing"] == ["has_a_digital_listing"]
    opened = set(req.evidence["owner_actions_open"])
    assert "publication_grant" in opened
    assert "payment_settings_setup" not in opened              # onboarding passes
    assert "info_and_appearance_setup" not in opened and "policy_settings_paste" not in opened
    assert req.ready is False


# ---- E6: snapshot spacing and a bounded 429 retry -------------------------------------------

class _Client:
    def __init__(self, fails: int):
        self.fails, self.calls = fails, 0

    def get_shop(self):
        self.calls += 1
        if self.calls <= self.fails:
            raise RuntimeError("Etsy returned 429 for getShop: per-second rate limit")
        return {"shop_id": 1}


def test_e6_the_snapshot_waits_after_the_shop_sync_and_retries_a_429_a_bounded_number_of_times():
    db = _db()
    slept: list = []
    old = (etsy_ops._sleep, etsy_ops.SNAPSHOT_429_DELAYS)
    etsy_ops._sleep = slept.append
    try:
        with db.session() as s:
            s.add(AuditLog(actor="orchestrator", action="store.shop_sync", detail={}))
        body, how = etsy_ops._get_shop_spaced(db, _Client(fails=2))
        assert body == {"shop_id": 1} and how["retries"] == 2
        assert 0 < how["waited_s"] <= etsy_ops.SNAPSHOT_GAP_SECONDS
        assert slept[1:] == list(etsy_ops.SNAPSHOT_429_DELAYS)
        try:
            etsy_ops._get_shop_spaced(db, _Client(fails=9))
            raise AssertionError("retried without bound")
        except RuntimeError as exc:
            assert "429" in str(exc)
        c = _Client(fails=0)
        c.get_shop = lambda: (_ for _ in ()).throw(ValueError("500 server error"))
        try:
            etsy_ops._get_shop_spaced(db, c)
            raise AssertionError("a non-429 error was retried or swallowed")
        except ValueError:
            pass
    finally:
        etsy_ops._sleep, etsy_ops.SNAPSHOT_429_DELAYS = old


# ---- E7: the policy rows -----------------------------------------------------------------

def test_e7_the_store_tab_shows_what_the_three_policy_fields_hold():
    from brambleloop.store_foundation import shop_sync

    db = _db()
    etsy_ops.store_reading(db, shop_sync.SYNC_READING, {"observed_at": NOW, "shop": _shop()})
    rows = {r["key"]: r for r in shop_sync.status(db)["settings"]}
    for key in ("policy_shipping", "policy_payment", "policy_additional"):
        assert rows[key]["state"] == shop_sync.CONFIRMED_LIVE, rows[key]
    assert rows["policy_additional"]["value_present"] is True
    assert rows["policy_additional"]["values"]["getShop.policy_additional"].startswith("Licence")
    assert rows["policy_shipping"]["value_present"] is False          # shown blank, not hidden
    try:
        shop_sync.confirm(db, "policy_additional", actor="owner:test")
        raise AssertionError("an API-read field was confirmed by a statement")
    except shop_sync.ConfirmRefused:
        pass


# ---- W-AGENTAUDIT E-6: store cards close on evidence; duplicates merged ---------------------

def _card(db, key, done=False):
    with db.session() as s:
        s.add(OwnerAction(requirement_key=key, action="x", reason="r", max_cost_cad=0,
                          minutes=1, consequence_of_delay="c", blocks="b", done=done))


def _open(db) -> set:
    with db.session() as s:
        return {r.requirement_key for r in s.scalars(select(OwnerAction).where(
            OwnerAction.done.is_(False)))}


def test_store_cards_close_on_the_reading_and_duplicates_are_merged():
    from brambleloop.store_foundation import store_readiness as SR

    db = _db()
    _card(db, "store:OA-E")
    _card(db, "store:OA-F")
    _card(db, "etsy_surface:policy_settings_paste")
    out = SR.sync_owner_actions(db, {})                  # no fresh reading yet
    assert "store:OA-E" in _open(db)                      # nothing closes without evidence
    assert "store:OA-F" not in _open(db)                  # merged: asked once
    assert out["closed"]["store:OA-F"].startswith("merged into etsy_surface:")
    etsy_ops.store_reading(db, etsy_ops.SHOP_READING, {"observed_at": NOW, "shop": _shop()})
    out = SR.sync_owner_actions(db, {})
    assert "store:OA-E" not in _open(db) and "store:OA-E" in out["closed"]
    texts = {it["id"]: it["action"] for it in SR.owner_actions({}, shop=_shop())}
    assert "announcement (C5)" not in texts["OA-C"]       # shown set live
    assert "announcement (C5)" in {it["id"]: it["action"] for it in SR.owner_actions({})}["OA-C"]


def test_oa_f_is_not_merged_into_a_target_card_that_is_already_done():
    """Final review R3: the FAQ and cancellations stay asked while unevidenced."""
    from brambleloop.store_foundation import store_readiness as SR

    db = _db()
    _card(db, "store:OA-F")
    _card(db, "etsy_surface:policy_settings_paste", done=True)
    out = SR.sync_owner_actions(db, {})
    assert "store:OA-F" in _open(db) and "store:OA-F" not in out["closed"]


def test_a_blank_or_stale_reading_closes_no_store_card():
    from brambleloop.store_foundation import store_readiness as SR

    db = _db()
    _card(db, "store:OA-E")
    etsy_ops.store_reading(db, etsy_ops.SHOP_READING,
                           {"observed_at": NOW, "shop": _shop(sale_message="")})
    SR.sync_owner_actions(db, {})
    assert "store:OA-E" in _open(db)
    db2 = _db()
    _card(db2, "store:OA-E")
    etsy_ops.store_reading(db2, etsy_ops.SHOP_READING,
                           {"observed_at": NOW - 10 * 86400, "shop": _shop()})
    SR.sync_owner_actions(db2, {})
    assert "store:OA-E" in _open(db2)


def test_the_banner_card_no_longer_asks_for_the_about_story_twice():
    action = es.SURFACES["info_and_appearance"].owner_action
    assert "About story" not in action.action.split("(")[0]
    assert "store:OA-OBS" in action.action and "getShop" in action.evidence_required


# ---- W-AGENTAUDIT E-8: the payout card -------------------------------------------------------

def test_payout_has_an_evidence_path_and_no_add_a_bank_account_wording_once_onboarded():
    from brambleloop.commerce import shop_observations as SO
    from brambleloop.launch import readiness as R
    from brambleloop.store_foundation import shop_sync

    db = _db()
    ev = R.payout_evidence(db)
    assert ev["ready"] is False and ev["onboarded"] is None          # no reading: unknown
    etsy_ops.store_reading(db, etsy_ops.SHOP_READING, {"observed_at": NOW, "shop": _shop()})
    ev = R.payout_evidence(db)
    assert ev["onboarded"] is True and ev["ready"] is False
    assert len(ev["missing"]) == 2
    assert "Add the payout bank account" not in R.ETSY_PAYOUT_CONFIRM_ONBOARDED.action
    assert "onboarded" in R.ETSY_PAYOUT_CONFIRM_ONBOARDED.action
    shop_sync.confirm(db, "payout_details", actor="owner:test")
    assert R.payout_evidence(db)["ready"] is False                   # tax not yet recorded
    SO.record(db, page="legal_and_tax", observed_at=_iso(0.01), complete=True,
              values={"identity_verified": True, "tax_position": "small supplier",
                      "decided_on": _iso(1)[:10]}, statement="Legal and tax", recorded_by="o")
    ev = R.payout_evidence(db)
    assert ev["ready"] is True and ev["missing"] == []
    etsy_ops.store_reading(db, etsy_ops.SHOP_READING,
                           {"observed_at": NOW, "shop": _shop(is_etsy_payments_onboarded=False)})
    assert R.payout_evidence(db)["ready"] is False                   # Etsy says otherwise


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback
                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
