"""W4-C13: Etsy operations, part 2 -- cases, standards, change budget, cross-surface audit,
feature discovery, UI drift, the autopilot contract and the launch non-delay rule.

Rows (Final Master, quoted):
- F-045 "Any Etsy-counted case triggers root-cause and corrective action."
- F-567 "Track Etsy minimum customer-service standards separately from Star Seller targets.
  Never report meeting the minimum as earning or approaching Star Seller without the required
  evidence."
- F-597 "Limit simultaneous storefront/listing experiments so causal attribution remains
  possible. Emergency policy/safety fixes bypass the experiment budget but are separately
  tagged."
- F-598 "Weekly compare Dashboard, Listings, Search Visibility, Stats, Marketing, Finances, Apps
  and Settings for contradictions: active counts, fees, traffic, state, policies, credentials
  and warnings."
- F-546 "Continuously audit new/changed Shop Manager capabilities, API fields, Seller Handbook
  guidance and Etsy Plus features. Classify each as useful, irrelevant, owner-only, unsupported
  or research-needed before adoption."
- F-599 "Quarterly and after material Etsy announcements, compare the observed Shop Manager
  navigation/surfaces with the maintained surface inventory. New, renamed or removed tabs
  create review tasks."
- F-600 "Brambleloop's Etsy department is never 'done'. It must observe, diagnose, prioritize,
  research, test, prove, deploy, verify remotely, monitor and learn across every supported shop
  surface ..."
- F-515@v0.15 "Once launch-critical quality floors pass, non-blocking improvements cannot
  indefinitely delay launch."
Fixtures only; no Etsy call, nothing written to Etsy.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy import select  # noqa: E402

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import Customer, Incident, Listing, Order, OwnerAction  # noqa: E402

NOW = datetime.now(timezone.utc)


def _db() -> Database:
    db = Database("sqlite://", scratch=True)
    db.create_all()
    return db


def _order(db, ref):
    with db.session() as s:
        c = Customer(customer_ref=f"b-{ref}")
        s.add(c)
        s.flush()
        s.add(Order(customer_id=c.id, external_ref=ref, product_slug="moss"))


def _refused(fn, exc):
    try:
        fn()
    except exc as e:
        return str(e)
    raise AssertionError("expected a refusal")


# ---- F-045 ----------------------------------------------------------------------------------

def test_f045_a_counted_case_is_an_incident_that_needs_a_root_cause():
    from brambleloop.commerce import orders_ingest as O

    db = _db()
    _order(db, "r-1")
    assert "not an order" in _refused(lambda: O.record_case(
        db, case_ref="c-0", order_ref="nope", opened_on="2026-10-01", reason="not received",
        etsy_counted=True), O.CaseRefused)
    quiet = O.record_case(db, case_ref="c-1", order_ref="r-1", opened_on="2026-10-01",
                          reason="question", etsy_counted=False)
    assert quiet["incident"] is None
    out = O.record_case(db, case_ref="c-2", order_ref="r-1", opened_on="2026-10-02",
                        reason="file would not open", etsy_counted=True)
    with db.session() as s:
        inc = s.scalar(select(Incident).where(Incident.signature == out["incident"]))
        assert inc.severity == "P1" and not inc.resolved
    _refused(lambda: O.record_root_cause(db, "c-2", cause="bad", corrective_action="fix",
                                         evidence="x", by="support"), O.CaseRefused)
    O.record_root_cause(db, "c-2", cause="the PDF was saved with an unsupported font",
                        corrective_action="re-export every PDF with embedded fonts and resend",
                        evidence="release 1.0.1 certificate", by="support")
    with db.session() as s:
        inc = s.scalar(select(Incident).where(Incident.signature == out["incident"]))
        assert inc.resolved and inc.detail["root_cause"]["corrective_action"]


# ---- F-567 ----------------------------------------------------------------------------------

def test_f567_meeting_the_minimum_is_never_star_seller():
    from brambleloop.commerce import orders_ingest as O

    r = O.service_standards(open_counted_cases=0, unanswered_overdue_messages=0)
    assert r["minimum_standards"]["state"] == "MET"
    assert r["star_seller"]["state"] == "NOT_EVIDENCED"
    part = O.service_standards(open_counted_cases=0, unanswered_overdue_messages=0,
                               star={"message_response_rate": 1.0, "average_rating": 5.0})
    assert part["star_seller"]["state"] == "NOT_EVIDENCED"
    full = {"message_response_rate": 0.97, "average_rating": 4.9, "orders": 8,
            "sales_usd": 320.0}
    assert O.service_standards(open_counted_cases=0, unanswered_overdue_messages=0,
                               star=full)["star_seller"]["state"] == "APPROACHING"
    short = O.service_standards(open_counted_cases=None, unanswered_overdue_messages=0,
                                star={**full, "average_rating": 4.6})
    assert short["minimum_standards"]["state"] == "UNKNOWN"
    assert short["star_seller"] == {"state": "NOT_MET", "short_of": ["average_rating"]}
    assert O.service_standards(open_counted_cases=1, unanswered_overdue_messages=0,
                               etsy_badge=True)["star_seller"]["state"] == "EARNED"


# ---- F-597 ----------------------------------------------------------------------------------

def test_f597_the_budget_limits_experiments_and_emergencies_bypass_it_tagged():
    from brambleloop.commerce import first_ten as F

    db = _db()
    F.open_change(db, key="e1", surface="listing:1", kind="experiment",
                  reason="hero image test", by="growth")
    assert "already carries" in _refused(lambda: F.open_change(
        db, key="e1b", surface="listing:1", kind="experiment", reason="title test now",
        by="growth"), F.ChangeRefused)
    F.open_change(db, key="e2", surface="listing:2", kind="experiment",
                  reason="tag set test", by="seo")
    assert "budget" in _refused(lambda: F.open_change(
        db, key="e3", surface="listing:3", kind="experiment", reason="price test here",
        by="pricing"), F.ChangeRefused)
    em = F.open_change(db, key="fix1", surface="listing:1", kind="emergency",
                       emergency_kind="policy", reason="remove a non-compliant claim",
                       by="truth")
    assert em["kind"] == "emergency" and em["confounds"] == ["e1"]
    b = F.change_budget(db)
    assert b["experiments_open"] == 2 and len(b["emergencies"]) == 1
    _refused(lambda: F.open_change(db, key="x", surface="shop", kind="emergency",
                                   emergency_kind="nice-to-have", reason="refresh the banner",
                                   by="growth"), F.ChangeRefused)
    F.close_change(db, "e2", outcome="concluded", by="seo")
    F.open_change(db, key="e3", surface="listing:3", kind="experiment",
                  reason="price test here", by="pricing")


# ---- F-598 ----------------------------------------------------------------------------------

def test_f598_cross_surface_contradictions_are_named_and_unread_pairs_are_unobserved():
    from brambleloop.commerce import policy_consistency as P
    from brambleloop.runtime.etsy_ops import (CENSUS_READING, CREDENTIAL_READING, SHOP_READING,
                                              store_reading)

    db = _db()
    first = P.cross_surface(db, now=NOW)
    assert first["contradictions"] == 0
    assert {"active_counts", "policies", "credentials", "fees", "traffic"} <= set(
        first["unobserved"])
    with db.session() as s:
        s.add(Listing(product_slug="p", version="1", title="t", description="d", tags=[],
                      price_cad=8.0, etsy_listing_id="111"))
        s.add(Listing(product_slug="q", version="1", title="t", description="d", tags=[],
                      price_cad=8.0, etsy_listing_id="222"))
    store_reading(db, SHOP_READING, {"observed_at": NOW.isoformat(),
                                     "shop": {"listing_active_count": 2},
                                     "policy_consistency": {"consistent": True, "differs": []}})
    store_reading(db, CENSUS_READING, {"observed_at": NOW.isoformat(),
                                       "estate": [{"listing_id": "111", "state": "active"}]})
    store_reading(db, CREDENTIAL_READING, {"status": "UNHEALTHY"})
    out = P.cross_surface(db, now=NOW)
    by = {c["check"]: c for c in out["comparisons"]}
    assert by["active_counts"]["state"] == "CONTRADICTION"
    assert by["listing_state"]["state"] == "CONTRADICTION" and "222" in by["listing_state"]["detail"]
    assert by["credentials"]["state"] == "CONTRADICTION"
    assert by["policies"]["state"] == "CONSISTENT"
    with db.session() as s:
        assert s.scalar(select(Incident).where(Incident.signature == P.AUDIT_SIGNATURE,
                                               Incident.resolved.is_(False))) is not None


# ---- F-546 ----------------------------------------------------------------------------------

def test_f546_nothing_is_adopted_before_it_is_classified():
    from brambleloop.commerce import surface_inventory as S

    db = _db()
    out = S.discover(db, observed_at=NOW.isoformat(), items=[
        {"source": "openapi", "name": "createShopAd", "description": "an Ads API appeared"},
        {"source": "etsy_plus", "name": "Custom web address", "description": "Plus perk"}])
    assert len(out["filed"]) == 2 and len(out["unclassified"]) == 2
    key = S._feature_key("openapi", "createShopAd")
    assert S.may_adopt(db, key)["may_adopt"] is False
    _refused(lambda: S.classify(db, key, cls="great", reason="looks good to me here",
                                by="etsy"), S.FeatureRefused)
    S.classify(db, key, cls="useful", reason="lets the ads department read spend directly",
               by="etsy_department")
    assert S.may_adopt(db, key)["may_adopt"] is True
    again = S.discover(db, observed_at=NOW.isoformat(), items=[
        {"source": "openapi", "name": "createShopAd", "description": "an Ads API appeared"}])
    assert again["filed"] == []                                     # unchanged: not re-filed
    S.discover(db, observed_at=NOW.isoformat(), items=[
        {"source": "openapi", "name": "createShopAd", "description": "now requires ads_w"}])
    assert S.may_adopt(db, key)["may_adopt"] is False               # changed: re-classify


# ---- F-599 ----------------------------------------------------------------------------------

def test_f599_navigation_drift_creates_one_batched_review_card():
    from brambleloop.commerce import surface_inventory as S

    db = _db()
    assert S.ui_drift_due(db, now=NOW)["due"] is True
    paths = sorted(S._nav_paths())
    assert len(paths) >= 3, paths
    same = S.ui_drift(db, observed=paths, observed_at=NOW - timedelta(hours=1),
                      trigger="quarterly")
    assert same["new"] == [] and same["removed"] == [] and same["review_card"] is None
    assert S.ui_drift_due(db, now=NOW)["due"] is False
    assert S.ui_drift_due(db, now=NOW + timedelta(days=95))["due"] is True
    moved = paths[1:] + ["shop manager > marketing > a brand new tab"]
    out = S.ui_drift(db, observed=moved, observed_at=NOW, trigger="announcement")
    assert out["new"] == ["shop manager > marketing > a brand new tab"]
    assert out["removed"] == [S._nav_paths()[paths[0]]] and out["review_card"] == S.UI_REVIEW_KEY
    S.ui_drift(db, observed=moved, observed_at=NOW, trigger="announcement")
    with db.session() as s:
        cards = list(s.scalars(select(OwnerAction).where(
            OwnerAction.requirement_key == S.UI_REVIEW_KEY)))
        assert len(cards) == 1 and cards[0].max_cost_cad == 0.0


# ---- F-600 ----------------------------------------------------------------------------------

def test_f600_the_contract_lists_every_surface_and_is_never_done():
    from brambleloop.commerce import surface_inventory as S
    from brambleloop.intel import etsy_surfaces as es

    c = S.contract(_db())
    assert len(c["surfaces"]) == len(es.surfaces()) and c["done"] is False
    in_scope = [r for r in c["surfaces"] if r["in_scope"]]
    assert in_scope and all(set(r["stages"]) == set(S.AUTOPILOT_STAGES) for r in in_scope)
    assert c["gaps"] == sum(len(r["missing"]) for r in in_scope) and c["gaps"] > 0


# ---- F-515@v0.15 ----------------------------------------------------------------------------

def test_f515_after_the_freeze_a_new_non_critical_requirement_does_not_delay_launch():
    from brambleloop.launch import non_delay as N
    from brambleloop.launch.readiness import BLOCKED_BUILD, BLOCKED_OWNER, Readiness, Requirement

    db = _db()
    building = Readiness(requirements=[
        Requirement("floor_a", "a", False, BLOCKED_BUILD),
        Requirement("etsy_shop", "shop", False, BLOCKED_OWNER)])
    assert "floors" in _refused(lambda: N.freeze(db, building, by="launch"), N.NonDelayRefused)
    floors = Readiness(requirements=[
        Requirement("floor_a", "a", True),
        Requirement("etsy_shop", "shop", False, BLOCKED_OWNER)])
    f = N.freeze(db, floors, by="launch")
    assert f["new"] and f["keys"] == ["etsy_shop", "floor_a"]
    later = Readiness(requirements=[
        Requirement("floor_a", "a", True),
        Requirement("etsy_shop", "shop", True),
        Requirement("nicer_thumbnails", "polish", False, BLOCKED_BUILD)])
    out = N.check(db, later)
    assert out["deferred_after_launch"] == ["nicer_thumbnails"] and out["effective_ready"]
    _refused(lambda: N.admit(db, "nicer_thumbnails", category="polish",
                             reason="they would look better", by="visual"), N.NonDelayRefused)
    N.admit(db, "nicer_thumbnails", category="product_truth",
            reason="the thumbnail misstates the finished size", by="truth")
    assert N.check(db, later)["effective_ready"] is False
    regressed = Readiness(requirements=[Requirement("floor_a", "a", False, BLOCKED_BUILD),
                                        Requirement("etsy_shop", "shop", True)])
    assert N.check(db, regressed)["blocking"] == ["floor_a"]       # a broken floor still blocks


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print("OK  ", t.__name__)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            import traceback
            traceback.print_exc()
            print("FAIL", t.__name__, exc)
    print(f"{len(tests) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
