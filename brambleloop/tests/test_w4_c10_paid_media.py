"""W4-C10: paid-media planning and credits (F-264, F-265, F-266, F-269, F-270, F-271, F-274,
F-614, F-615, F-775). Fixtures only: no campaign is created, activated or funded, no Etsy Ads
or Offsite Ads setting is touched, no network, CA$0."""
import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import ast
import inspect
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brambleloop.commerce.paid_media import Caps  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402

NOW = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
LISTINGS = [{"slug": "a", "ready": True}, {"slug": "b", "ready": True},
            {"slug": "c", "ready": False, "why": "trust gate UNKNOWN"}]
GRANTED = {"granted": True, "daily_cap_cad": 40.0, "lifetime_cap_cad": 1500.0}
CAPS = Caps(daily_cad=50, campaign_cad=500, monthly_cad=1000, max_test_loss_cad=150,
            max_cac_cad=20)


def _db():
    db = Database("sqlite://")
    db.create_all()
    return db


def _refused(fn, needle):
    from brambleloop.growth.ads_plan import PlanRefused

    try:
        fn()
    except PlanRefused as exc:
        assert needle in str(exc), exc
        return
    raise AssertionError("plan accepted")


# ---- F-264 -----------------------------------------------------------------------------------

def test_f264_learning_test_meets_the_guidance_floor_and_promotes_every_ready_listing():
    from brambleloop.growth import ads_plan as P

    _refused(lambda: P.design_learning_test(listings=LISTINGS, daily_usd=2, days=30),
             "cannot learn")
    _refused(lambda: P.design_learning_test(listings=LISTINGS, daily_usd=4, days=14),
             "attribution window")
    _refused(lambda: P.design_learning_test(listings=[LISTINGS[2]], daily_usd=4, days=30),
             "no ready listing")
    _refused(lambda: P.design_learning_test(listings=LISTINGS, daily_usd=4, days=30,
                                            narrow_to=["a"]), "stated reason")
    # No owner authority: the floor is above the conservative CA$3/day cap, and the plan says
    # so instead of shrinking the test below the point where it learns.
    plan = P.design_learning_test(listings=LISTINGS, daily_usd=4, days=30)
    assert plan["state"] == "NEEDS_OWNER_AUTHORITY" and plan["executed"] is False
    assert plan["phase"] == "SHADOW" and plan["listings"] == ["a", "b"]
    assert plan["left_out"] == [{"slug": "c", "why": "trust gate UNKNOWN"}]
    assert plan["guidance"]["status"]["min"].startswith("UNVERIFIED")
    ok = P.design_learning_test(listings=LISTINGS, daily_usd=4, days=30, authority=GRANTED)
    assert ok["state"] == "DESIGNED" and ok["promotes_all_ready"]


# ---- F-265 -----------------------------------------------------------------------------------

def test_f265_per_listing_controls_only_at_the_threshold():
    from brambleloop.growth import ads_plan as P

    _refused(lambda: P.design_learning_test(listings=LISTINGS, daily_usd=10, days=30,
                                            strategy="per_listing", authority=GRANTED),
             "not available")
    below = P.design_learning_test(listings=LISTINGS, daily_usd=10, days=30, authority=GRANTED)
    assert below["strategy"] == "etsy_managed" and not below["per_listing_controls_available"]
    big = {"granted": True, "daily_cap_cad": 30.0, "lifetime_cap_cad": 2000.0}
    at = P.design_learning_test(listings=LISTINGS, daily_usd=25, days=30,
                                strategy="per_listing", authority=big)
    assert at["per_listing_controls_available"] and at["strategy"] == "per_listing"
    assert at["state"] == "OVER_CEILING"          # US$25/day = CA$35.39 > CA$30 cap: it binds


# ---- F-615 -----------------------------------------------------------------------------------

def test_f615_expiring_credit_first_but_never_a_reason_to_advertise():
    from brambleloop.growth.ads_plan import fund

    none = fund(amount_cad=20, approved_experiment=False, credit_left_cad=7.1,
                credit_expires_before_end=True, billing_permits_credit=True)
    assert none["funded"] is False and none["credit_cad"] == 0
    first = fund(amount_cad=20, approved_experiment=True, credit_left_cad=7.1,
                 credit_expires_before_end=True, billing_permits_credit=True)
    assert first == {**first, "credit_cad": 7.1, "cash_cad": 12.9}
    assert "expiring" in first["why"]
    unknown = fund(amount_cad=20, approved_experiment=True, credit_left_cad=7.1,
                   credit_expires_before_end=True, billing_permits_credit=None)
    assert unknown["cash_cad"] == 20 and unknown["credit_basis"] == "UNKNOWN"


# ---- F-266 -----------------------------------------------------------------------------------

def test_f266_no_strategy_thrash_inside_the_learning_window():
    from brambleloop.growth import ads_decisions as D

    hist = [{"at": NOW - timedelta(days=3), "kind": "strategy"}]
    held = D.guard_change(hist, now=NOW, kind="strategy")
    assert held["allowed"] is False and "learning window" in held["why"]
    assert D.guard_change(hist, now=NOW, kind="budget", reason="boredom",
                          evidence_ref="x")["allowed"] is False
    assert D.guard_change(hist, now=NOW, kind="budget", reason="runaway_spend")["allowed"] \
        is False                                              # an override needs evidence
    assert D.guard_change(hist, now=NOW, kind="budget", reason="runaway_spend",
                          evidence_ref="report:2026-10-27")["allowed"]
    assert D.guard_change(hist, now=NOW + timedelta(days=12), kind="strategy")["allowed"]


# ---- F-269 -----------------------------------------------------------------------------------

def test_f269_per_listing_funnel_with_unknown_never_zero():
    from brambleloop.growth import ads_decisions as D

    rows = [{"slug": "a", "spend_cad": 4, "impressions": 800, "clicks": 20, "orders": 1,
             "revenue_cad": 9.5},
            {"slug": "a", "spend_cad": 4, "impressions": 700, "clicks": 10, "orders": 0,
             "revenue_cad": 0},
            {"slug": "b", "spend_cad": 3, "impressions": 500, "clicks": 6, "orders": None,
             "revenue_cad": None}]
    f = D.funnel(rows, contribution_per_order_cad={"a": 7.0, "b": 7.0})["listings"]
    a = f["a"]
    assert (a["spend_cad"], a["impressions"], a["clicks"], a["orders"]) == (8.0, 1500, 30, 1)
    assert a["ctr"] == 0.02 and a["cpc_cad"] == 0.27 and a["conversion"] == 0.0333
    assert a["contribution_after_ads_cad"] == -1.0 and a["evidence"]["report_days"] == 2
    b = f["b"]
    assert b["orders"] is None and b["conversion"] is None
    assert b["contribution_after_ads_cad"] is None and "orders" in b["unknown"]


# ---- F-270 -----------------------------------------------------------------------------------

def test_f270_stop_or_scale_only_on_adequate_exposure():
    from brambleloop.growth import ads_decisions as D

    thin = {"slug": "a", "spend_cad": 10, "impressions": 400, "clicks": 12, "orders": 0}
    assert D.decide(thin, CAPS)["decision"] == "CONTINUE"
    clicks_no_orders = {"slug": "a", "spend_cad": 60, "impressions": 9000, "clicks": 250,
                        "orders": 0}
    d = D.decide(clicks_no_orders, CAPS, contribution_cad=0.0)
    assert d["decision"] == "DIAGNOSE" and d["budget_change"] == "frozen"
    win = {"slug": "a", "spend_cad": 100, "impressions": 20000, "clicks": 400, "orders": 20}
    s = D.decide(win, CAPS, contribution_cad=200.0)
    assert s["decision"] == "SCALE_ELIGIBLE" and s["budget_change"] == "owner_decision"
    assert D.decide(win, CAPS, contribution_cad=110.0)["decision"] == "STOP"
    assert D.decide(win, CAPS, contribution_cad=200.0, tracking_healthy=False)["decision"] \
        == "STOP"
    assert D.decide({**win, "orders": None}, CAPS)["decision"] == "UNKNOWN"


# ---- F-271 -----------------------------------------------------------------------------------

def test_f271_creative_and_listing_before_budget():
    from brambleloop.growth import ads_decisions as D

    weak_clicks = {"impressions": 10000, "clicks": 50, "orders": 1}
    r = D.route(weak_clicks, baseline_ctr=0.02, baseline_conversion=0.03)
    assert r["route"] == "CREATIVE" and "hero image" in r["fix"]
    weak_conv = {"impressions": 10000, "clicks": 220, "orders": 1}
    r2 = D.route(weak_conv, baseline_ctr=0.02, baseline_conversion=0.03)
    assert r2["route"] == "LISTING" and "price" in r2["fix"]
    assert D.route(weak_conv, baseline_ctr=None, baseline_conversion=0.03)["route"] == "UNKNOWN"
    assert all(x["budget_is_remedy"] is False for x in (r, r2))


# ---- F-274 -----------------------------------------------------------------------------------

def test_f274_every_paid_change_is_ledgered_with_authorization_and_verdict():
    from brambleloop.core.models import OwnerAction
    from brambleloop.growth import ads_ledger as L

    db = _db()
    entry = {"objective": "learn CTR for the baby blanket", "listings": ["a", "b"],
             "authorization": {"type": "none"},
             "budget": {"daily_cad": 5.66, "total_cad": 169.8, "funding": "owner_cash"},
             "settings": {"strategy": "etsy_managed"},
             "window": {"start": "2026-11-01", "days": 30},
             "next_action": "read the funnel at day 30"}
    try:
        L.open_entry(db, "learn-1", {k: v for k, v in entry.items() if k != "window"})
        raise AssertionError("an entry without a window was opened")
    except L.LedgerRefused:
        pass
    e1 = L.open_entry(db, "learn-1", entry)
    assert L.entries(db)[0]["authorization_check"]["state"] == "UNAUTHORISED"
    with db.session() as s:
        act = OwnerAction(requirement_key="ads.proposal:x", action="decide", reason="r",
                          max_cost_cad=169.8, minutes=5, consequence_of_delay="none",
                          blocks="F-267", done=True)
        s.add(act)
        s.flush()
        aid = act.id
    e2 = L.open_entry(db, "learn-2", {**entry, "authorization": {"type": "owner_action",
                                                                  "ref": aid}}, replaces=e1)
    rows = {r["id"]: r for r in L.entries(db)}
    assert rows[e2]["authorization_check"]["state"] == "AUTHORISED"
    assert rows[e2]["executed"] is False and rows[e2]["phase"] == "SHADOW"
    try:
        L.close(db, e2, verdict="WIN", next_action="scale request to owner")
        raise AssertionError("a WIN without evidence was recorded")
    except L.LedgerRefused:
        pass
    L.record_evidence(db, e2, {"funnel": {"clicks": 300, "orders": 9}})
    rec = L.close(db, e2, verdict="INCONCLUSIVE", next_action="extend 30 days",
                  rollback="return to organic only")
    assert rec["verdict"] == "INCONCLUSIVE" and rec["history"][-1]["event"] == "closed"
    try:
        L.record_evidence(db, e2, {"late": True})
        raise AssertionError("a closed entry was rewritten")
    except L.LedgerRefused:
        pass


# ---- F-614 -----------------------------------------------------------------------------------

def test_f614_plus_credit_kept_apart_from_cash_and_never_rolls_over():
    from brambleloop.growth import plus_credit as W

    c1 = W.cycle(date(2026, 9, 1), date(2026, 10, 1), displayed_ads_credit_cad=7.10)
    c2 = W.cycle(date(2026, 10, 1), date(2026, 11, 1))
    assert c1["ads_credit_usd"] == 5.0 and c1["listing_credits"] == 15
    assert c1["cad_basis"] == "owner_reported" and c2["cad_basis"].startswith("ESTIMATED")
    w = W.wallet([c1, c2], ad_spend=[(date(2026, 9, 10), 3.0), (date(2026, 10, 5), 9.0),
                                     (date(2026, 8, 20), 2.0)],
                 listing_uses=[date(2026, 9, 2)] * 16, today=date(2026, 10, 20))
    sep, octo = w["cycles"]
    assert sep["ads_credit_drawn_cad"] == 3.0 and sep["ads_credit_expired_cad"] == 4.1
    assert sep["listing_uses_paid_in_cash"] == 1 and sep["state"] == "ENDED"
    assert octo["ads_credit_drawn_cad"] == c2["ads_credit_cad"]       # no rollover from Sept
    assert octo["ads_cash_cad"] == round(9.0 - c2["ads_credit_cad"], 2)
    assert octo["days_until_lapse"] == 12 and octo["ads_credit_expired_cad"] == 0
    assert w["ads_spend_outside_any_cycle_cad"] == 2.0 and w["rollover"] is False
    assert w["ceilings_changed"] == 0


# ---- F-775 -----------------------------------------------------------------------------------

def test_f775_attach_rate_reorders_legitimate_edges_and_copy_cannot_mislead():
    from brambleloop.growth import attach as A

    graph = {"nodes": [{"product": "blanket", "related": ["pillow"], "bundles": [],
                        "next_projects": {"in_catalogue": ["basket"]},
                        "tutorials": ["sc-dc"]}]}
    orders, opens = [], []
    for i in range(25):
        orders.append({"buyer": f"b{i}", "product": "blanket", "at": NOW})
        if i < 10:
            orders.append({"buyer": f"b{i}", "product": "basket",
                           "at": NOW + timedelta(days=3)})
        if i < 2:
            orders.append({"buyer": f"b{i}", "product": "pillow",
                           "at": NOW + timedelta(days=60)})        # outside the window
    rates = A.attach_rates(graph, orders, tutorial_opens=opens)
    assert rates[("blanket", "next_projects", "basket")]["rate"] == 0.4
    assert rates[("blanket", "related", "pillow")]["rate"] == 0.0
    ranked = A.rank(graph, rates)["recommendations"]["blanket"]
    assert [r["target"] for r in ranked] == ["basket", "pillow", "sc-dc"]
    assert {r["target"] for r in ranked} == {"pillow", "basket", "sc-dc"}   # nothing added
    thin = A.attach_rates(graph, orders[:5])
    assert thin[("blanket", "related", "pillow")]["rate"] == "UNMEASURED"

    assert A.check_copy("You'll need the matching pillow - only 3 left!",
                        {"kind": "next_projects", "rate": 0.4}) == [
        "claims the item is required: a recommendation is optional",
        "claims a matching set without a recorded bundle or family edge",
        "invents urgency or scarcity: digital patterns do not run out"]
    assert A.check_copy("Customers also bought", {"kind": "related", "rate": "UNMEASURED"})
    assert A.check_copy("A next project in the same yarn weight",
                        {"kind": "next_projects", "rate": "UNMEASURED"}) == []


# ---- the hard limit: nothing in C10 can execute ----------------------------------------------

def test_c10_modules_cannot_spend_or_reach_the_network():
    from brambleloop.growth import ads_decisions, ads_ledger, ads_plan, attach, plus_credit

    bad_imports = ("socket", "requests", "httpx", "urllib", "http", "aiohttp",
                   "brambleloop.integrations", "integrations", "publish")
    bad_calls = {"authorise_spend", "enqueue", "reserve", "reserve_in", "urlopen", "request",
                 "post", "put"}
    bad_names = ("activate", "launch", "execute", "spend_now", "start_campaign",
                 "create_campaign")
    for mod in (ads_plan, ads_decisions, ads_ledger, plus_credit, attach):
        tree = ast.parse(inspect.getsource(mod))
        for n in ast.walk(tree):
            if isinstance(n, ast.ImportFrom):
                name = (n.module or "")
                assert not any(name.lstrip(".").startswith(b) for b in bad_imports), \
                    (mod.__name__, name)
            elif isinstance(n, ast.Import):
                assert not any(a.name.split(".")[0] in bad_imports for a in n.names)
            elif isinstance(n, ast.Call):
                f = n.func
                called = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
                assert called not in bad_calls, (mod.__name__, called)
            elif isinstance(n, ast.FunctionDef):
                assert not any(w in n.name.lower() for w in bad_names), (mod.__name__, n.name)


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("OK  ", n)  # run_tests.sh counts lines beginning OK
