"""The culture engine, and the one way a culture radar destroys a company.

v1.4.3 requirements 133-147. A crochet business that watches pop culture is doing something
sensible and something dangerous, and the dangerous part does not arrive as a decision.

It arrives as a gradient. The radar optimises for demand; the strongest demand signals are all
somebody's property; each step downstream receives a slightly more abstract description of the
same protected thing; and it reaches production having been refused by nobody. So most of these
tests are about the protected element surviving a step it should not have survived, and the
rest are about the engine still being useful once it cannot use the obvious execution.
"""
from __future__ import annotations

import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.culture import radar, rapid, rights, score, translate  # noqa: E402


def _db() -> Database:
    tmp = tempfile.mkdtemp()
    db = Database(f"sqlite:///{tmp}/culture.sqlite")
    db.create_all()
    return db


def _token(text="Snugglepuff", cls=rights.CHARACTER_NAME) -> rights.ProtectedToken:
    return rights.ProtectedToken(text, cls, source="a streaming series")


# ---- the rights router ----------------------------------------------------


def test_a_protected_element_with_no_basis_goes_to_the_original_lane_not_to_a_refusal():
    """#135 is specific, and the specificity is the whole design.

    Killing the opportunity teaches the pipeline that the rights gate is an obstacle, and a
    gate people route around is worse than none. Sending it to the original lane teaches the
    pipeline that the gate is a turning — and the turning is where a product this company
    actually owns comes from.
    """
    routed = rights.route([_token()])
    assert routed.lane == rights.ORIGINAL
    assert routed.may_reach_customers is False
    assert "not a refusal of the opportunity" in routed.reason

    # Nothing protected declared: nothing to hold back.
    free = rights.route([])
    assert free.lane == rights.DIRECT
    assert free.may_reach_customers is True


def test_a_basis_must_record_something_behind_it():
    """'It seems fine' and 'everyone does it' are the two sentences before every takedown."""
    for kind, evidence in (
        ("licensed", "we have a licence"),
        ("permissioned", "they said yes"),
        ("generic", "common phrase"),
    ):
        try:
            rights.record_basis(kind, evidence=evidence, recorded_by="analyst")
        except rights.RightsRefused as e:
            assert "nothing behind it" in str(e)
        else:
            raise AssertionError(f"a {kind} basis passed with nothing behind it")

    try:
        rights.record_basis("vibes", evidence="x" * 40, recorded_by="analyst")
    except rights.RightsRefused as e:
        assert "not a clearance basis" in str(e)
    else:
        raise AssertionError("an invented basis was accepted")

    good = rights.record_basis(
        "permissioned",
        evidence="the designer gave written permission by email on 2026-09-10 for ornaments",
        recorded_by="owner", scope="ornaments only")
    assert good.kind == "permissioned"
    assert rights.route([_token()], basis=good).lane == rights.DIRECT


def test_the_public_domain_screen_refuses_to_do_arithmetic_it_should_not_do():
    """A system computing a term from a year is giving legal advice in the voice of a sum."""
    try:
        rights.record_basis("public_domain",
                            evidence="a well-known song that everybody assumes is free",
                            recorded_by="analyst", publication_year=1975)
    except rights.RightsRefused as e:
        assert "deliberately far earlier than any jurisdiction requires" in str(e)
        assert "legal advice while sounding like arithmetic" in str(e)
    else:
        raise AssertionError("a 1975 work passed a public-domain screen")

    try:
        rights.record_basis("public_domain", evidence="a traditional carol of unknown date",
                            recorded_by="analyst")
    except rights.RightsRefused as e:
        assert "publication year" in str(e)
    else:
        raise AssertionError("a public-domain claim passed with no year at all")

    old = rights.record_basis(
        "public_domain",
        evidence="a carol printed in an 1833 collection, verified against the British Library",
        recorded_by="analyst", publication_year=1833)
    assert "Passing this screen is not clearance" in old.evidence


def test_the_token_check_is_word_boundary_rather_than_substring():
    """A check that fires on 'art' inside 'heart' is one everybody learns to work around."""
    tokens = [rights.ProtectedToken("art", rights.WORK_TITLE)]
    rights.check_free_of("a heart-shaped ornament in cream", tokens)
    try:
        rights.check_free_of("an art-deco ornament in cream", tokens)
    except rights.RightsRefused:
        pass
    else:
        raise AssertionError("the protected word passed as its own word")


def test_a_protected_element_cannot_reach_a_customer_through_the_original_lane():
    """The end-of-pipeline check, because the beginning-of-pipeline one is not enough.

    A concept can pick up the protected token anywhere in the middle — a listing title, an
    asset caption, a helpful clarification. Checking only at the start catches the honest
    mistake and misses the gradient.
    """
    routed = rights.route([_token()])
    rights.check_direct_use(routed, product_or_copy="a small green ornament for a gift")
    try:
        rights.check_direct_use(
            routed, product_or_copy="Snugglepuff-inspired ornament, crochet pattern")
    except rights.RightsRefused as e:
        assert "the infringement with an extra step" in str(e)
    else:
        raise AssertionError("a protected name reached customer-facing copy")


# ---- translation ----------------------------------------------------------


def test_decomposition_is_checked_rather_than_trusted():
    """#134's whole value is that the property does not survive, and models do not help.

    The protected element is the most salient thing in the input, so it is exactly what
    survives a paraphrase — which is what decomposition becomes when nobody checks.
    """
    tokens = [_token()]
    try:
        translate.decompose("sig", {"emotion": "the warmth of watching Snugglepuff"}, tokens)
    except rights.RightsRefused as e:
        assert "abbreviated rather than decomposed" in str(e)
    else:
        raise AssertionError("the protected name survived decomposition")

    clean = translate.decompose("sig", {
        "emotion": "protective tenderness toward something small",
        "character_archetype": "the tiny charge somebody reluctantly adopts",
        "era": "classic_storybook_winter",
        "gifting_context": "given to a new parent by somebody who is not family",
    }, tokens)
    assert clean.complete is False
    assert len(clean.primitives) == 4
    assert "humour_type" in clean.absent


def test_an_era_invented_per_signal_is_a_franchise_with_a_different_name():
    """#137's eras are reusable territories, and inventing one per signal loses the reuse."""
    try:
        translate.decompose("sig", {"era": "the snugglepuff aesthetic"}, [])
    except translate.TranslationRefused as e:
        assert "comes back next year without anybody's permission" in str(e)
    else:
        raise AssertionError("an invented era was accepted")

    assert "retro_halloween" in translate.ERAS
    assert "vintage_ski_lodge" in translate.ERAS


def test_breadth_is_families_and_distinct_premises_rather_than_a_count():
    """Fifteen ideas in two families is one idea in fifteen colours (#138).

    The jury cannot catch this: it reads concepts one at a time, and every one of the fifteen
    is individually fine. It is a property of the set.
    """
    narrow = [translate.Translation(f"throw-{i}", "blanket", f"a winter throw, variant {i}")
              for i in range(12)]
    result = translate.white_space("sig", narrow, [])
    assert result["translations"] == 12
    assert result["family_count"] == 1
    assert result["broad_enough"] is False

    families = ["blanket", "stocking", "ornament", "coaster", "wreath", "garland",
                "amigurumi", "pillow", "bag", "kitchen"]
    broad = [translate.Translation(f"p-{f}", f, f"a distinct premise about {f}")
             for f in families]
    assert translate.white_space("sig", broad, [])["broad_enough"] is True

    # Ten ideas restating each other is one idea typed ten times.
    same = [translate.Translation(f"p-{f}", f, "a cosy winter object") for f in families]
    assert translate.white_space("sig", same, [])["broad_enough"] is False


def test_a_territory_with_one_role_filled_is_not_a_collection():
    """#143. Six products that are all decor is a decor range, and the gift buyer leaves."""
    partial = translate.collection("cozy_movie_night", {"decor": "lap-blanket"})
    assert partial["is_a_collection"] is False
    assert "giftable_mini" in partial["roles_missing"]

    full = translate.collection("cozy_movie_night",
                                {r: f"{r}-product" for r in translate.COLLECTION_ROLES})
    assert full["is_a_collection"] is True

    try:
        translate.collection("snugglepuff_vibes", {})
    except translate.TranslationRefused as e:
        assert "somebody else's property with the name filed off" in str(e)
    else:
        raise AssertionError("an invented theme was accepted as a franchise-free territory")


def test_what_this_company_owns_is_countable():
    """#146. A dependence nobody measures is one nobody notices growing."""
    owned = translate.owned_territories()
    assert owned["count"] == len(translate.ERAS) + len(translate.THEMES)
    assert "rented" in owned["note"]


# ---- the opportunity score ------------------------------------------------


def test_rights_and_make_time_are_gates_rather_than_weights():
    """Five out of five everywhere and zero on rights is not a four (#136)."""
    strong = {k: 1.0 for k in score.WEIGHTS if k not in score.GATES}
    blocked = score.score("sig", {**strong, "make_time_window": 1.0,
                                  "rights_feasibility": 0.0})
    assert blocked.score == 0.0
    assert blocked.gate_failures == ["rights_feasibility"]
    assert blocked.actionable is False
    assert "cannot be strong enough elsewhere to compensate" in blocked.to_dict()["note"]

    closed = score.score("sig", {**strong, "make_time_window": 0.0,
                                 "rights_feasibility": 1.0})
    assert closed.gate_failures == ["make_time_window"]

    clear = score.score("sig", {**strong, "make_time_window": 1.0,
                                "rights_feasibility": 1.0})
    assert clear.score > 0.9
    assert clear.actionable is True


def test_an_unobserved_component_is_absent_rather_than_zero():
    """Zero and unknown produce different decisions and identical arithmetic."""
    thin = score.score("sig", {"search_momentum": 0.9, "recurrence": 0.9})
    assert thin.evidence_weight < score.MIN_EVIDENCE_WEIGHT
    assert thin.to_dict()["trustworthy"] is False
    # An unobserved gate fails: "we did not check whether we may sell this" is not better
    # than "we may not sell this". It is also the more serious thing to say, so it is the
    # note that gets reported.
    assert any("never observed" in g for g in thin.gate_failures)
    assert "gate rather than a weight" in thin.to_dict()["note"]

    # Thin evidence with both gates observed reports the evidence weakness instead.
    thin_but_gated = score.score("sig", {"search_momentum": 0.9, "recurrence": 0.9,
                                         "make_time_window": 1.0, "rights_feasibility": 1.0})
    assert thin_but_gated.gate_failures == []
    assert thin_but_gated.to_dict()["trustworthy"] is False
    assert "impression with a decimal point" in thin_but_gated.to_dict()["note"]
    assert thin_but_gated.actionable is False

    try:
        score.score("sig", {"vibe": 0.9})
    except score.ScoreRefused as e:
        assert "not opportunity components" in str(e)
    else:
        raise AssertionError("an invented component was scored")


def test_a_gate_failure_is_excluded_from_the_ranking_rather_than_ranked_last():
    """A ranked list is a thing people work down when they run out of items above."""
    strong = {k: 1.0 for k in score.WEIGHTS if k not in score.GATES}
    good = score.score("ok", {**strong, "make_time_window": 1.0, "rights_feasibility": 1.0})
    bad = score.score("no", {**strong, "make_time_window": 1.0, "rights_feasibility": 0.0})
    result = score.rank([bad, good])
    assert [r["signal"] for r in result["ranked"]] == ["ok"]
    assert [r["signal"] for r in result["gated_out"]] == ["no"]


# ---- the radar ------------------------------------------------------------


def test_a_signal_with_no_source_is_a_hunch():
    try:
        radar.Signal("x", "people like cosy things", "meme")
    except radar.RadarRefused as e:
        assert "a hunch" in str(e)
    else:
        raise AssertionError("a sourceless signal was recorded")

    try:
        radar.Signal("x", "t", "astrology", sources=("somewhere",))
    except radar.RadarRefused as e:
        assert "not a culture domain" in str(e)
    else:
        raise AssertionError("an invented domain was accepted")


def test_the_routing_decision_is_made_once_at_observation_and_stored():
    """A token declared downstream is one no earlier step could have been checked against."""
    db = _db()
    signal = radar.Signal("snugglepuff-winter", "a small green character at christmas",
                          "television", tokens=(_token(),), sources=("a trends page",))
    recorded = radar.record(db, signal)
    assert recorded["routing"]["lane"] == rights.ORIGINAL

    mem = radar.memory(db)
    assert mem["signals"] == 1
    assert mem["by_lane"][rights.ORIGINAL] == 1
    assert mem["all"][0]["protected"] == 1


def test_one_reading_is_a_level_and_two_are_a_momentum():
    db = _db()
    radar.record(db, radar.Signal("retro-halloween", "die-cut cats", "nostalgia_era",
                                  sources=("trends",)))
    radar.observe(db, "retro-halloween", channel="search", interest=0.4,
                  observed_on="2026-08-01", competitor_listings=100)
    assert radar.momentum(db, "retro-halloween")["measurable"] is False

    radar.observe(db, "retro-halloween", channel="search", interest=0.9,
                  observed_on="2026-09-01", competitor_listings=180)
    radar.observe(db, "retro-halloween", channel="search", interest=0.5,
                  observed_on="2026-09-18", competitor_listings=400)
    m = radar.momentum(db, "retro-halloween")
    assert m["measurable"] is True
    assert m["peak"] == 0.9
    assert m["direction"] == "falling"
    assert m["from_peak"] < -0.4
    assert m["copycat_multiple"] == 4.0


def test_lead_lag_names_the_case_where_the_radar_is_reporting_the_news():
    """#140. If culture peaks after demand, entering on the signal is entering at saturation."""
    db = _db()
    radar.record(db, radar.Signal("cosy-gaming", "a soft aesthetic", "viral_aesthetic",
                                  sources=("trends",)))
    assert radar.lead_lag(db, "cosy-gaming")["measurable"] is False

    for on, interest in (("2026-06-01", 0.3), ("2026-07-01", 0.9)):
        radar.observe(db, "cosy-gaming", channel="search", interest=interest, observed_on=on)
    for on, interest in (("2026-08-01", 0.4), ("2026-09-01", 0.95)):
        radar.observe(db, "cosy-gaming", channel="etsy", interest=interest, observed_on=on)

    leading = radar.lead_lag(db, "cosy-gaming")
    assert leading["measurable"] is True
    assert leading["lead_days"] == 62
    assert leading["is_a_leading_indicator"] is True

    db2 = _db()
    radar.record(db2, radar.Signal("late", "t", "meme", sources=("trends",)))
    for on, interest in (("2026-08-01", 0.3), ("2026-09-01", 0.9)):
        radar.observe(db2, "late", channel="search", interest=interest, observed_on=on)
    for on, interest in (("2026-06-01", 0.4), ("2026-07-01", 0.95)):
        radar.observe(db2, "late", channel="etsy", interest=interest, observed_on=on)
    lagging = radar.lead_lag(db2, "late")
    assert lagging["is_a_leading_indicator"] is False
    assert "entering at saturation" in lagging["note"]


def test_any_one_exit_condition_is_sufficient_and_unmeasured_is_not_failure():
    """#145. A trend dies several ways; waiting for all of them is waiting."""
    db = _db()
    radar.record(db, radar.Signal("fad", "a one-week thing", "meme", sources=("trends",)))
    radar.observe(db, "fad", channel="search", interest=0.9, observed_on="2026-08-01",
                  competitor_listings=50)
    radar.observe(db, "fad", channel="search", interest=0.3, observed_on="2026-09-01",
                  competitor_listings=60)

    result = radar.exit_check(db, "fad")
    assert result["should_exit"] is True
    conditions = {r["condition"] for r in result["reasons"]}
    assert "declining_interest" in conditions
    # Conversion was never measured, and this company has none: reading that as failure would
    # exit every trend on its first day.
    assert "poor_conversion" not in conditions
    assert "conversion" in result["unmeasured"]

    # A closing make-time window is sufficient on its own, whatever the interest is doing.
    db2 = _db()
    radar.record(db2, radar.Signal("strong", "t", "meme", sources=("trends",)))
    radar.observe(db2, "strong", channel="search", interest=0.8, observed_on="2026-09-01")
    radar.observe(db2, "strong", channel="search", interest=0.9, observed_on="2026-09-18")
    late = radar.exit_check(db2, "strong", days_to_event=10)
    assert late["should_exit"] is True
    assert [r["condition"] for r in late["reasons"]] == ["insufficient_make_time"]


def test_an_exit_keeps_its_reason_because_the_reason_is_the_asset():
    db = _db()
    radar.record(db, radar.Signal("fad", "t", "meme", sources=("trends",)))
    try:
        radar.exit_signal(db, "fad", "over")
    except radar.RadarRefused as e:
        assert "teaches next year's agent nothing" in str(e)
    else:
        raise AssertionError("an exit was recorded with no reason")

    radar.exit_signal(db, "fad",
                      "interest fell 70% from peak within five weeks and never recurred",
                      lesson="meme-domain signals in this pod are one-week fads")
    mem = radar.memory(db)
    assert mem["by_state"][radar.EXITED] == 1
    assert mem["exited_with_a_lesson"] == ["fad"]
    assert mem["all"][0]["lesson"].startswith("meme-domain")


def test_a_radar_with_no_feed_says_so_rather_than_reporting_no_trends():
    """An empty trend list is indistinguishable from a world with no culture in it."""
    db = _db()
    swept = radar.sweep(db)
    assert swept["scanned"] is False
    assert "looks exactly like a radar with a source" in swept["reason"]
    assert swept["unmet_requirements"] == [133, 140]
    assert "two series rather than one" in swept["what_would_connect_it"]


def test_a_signal_seen_again_a_year_later_is_a_recurring_territory():
    """#144's compounding value: research retro Halloween once, not every autumn."""
    db = _db()
    last_year = (date.today() - timedelta(days=360)).isoformat()
    radar.record(db, radar.Signal("retro-halloween", "die-cut cats", "nostalgia_era",
                                  sources=("trends",), first_seen=last_year))
    radar.record(db, radar.Signal("this-week", "a meme", "meme", sources=("trends",)))
    mem = radar.memory(db)
    assert mem["recurring_annually"] == ["retro-halloween"]


# ---- the rapid-response cell ----------------------------------------------


def test_the_rapid_cell_buys_speed_with_parallelism_and_never_with_a_gate():
    """#141, and the reason the pressure runs exactly the wrong way.

    The cell exists because a window is closing, so the argument for skipping a gate is
    strongest precisely when the consequence is worst: a product rushed into a closing window
    has the least time left for a correction round.
    """
    assert rapid.check("draft the hero early", accelerates="asset_drafting")["permitted"]

    for gate in ("cir_validation", "product_truth", "creative_parity", "policy_gate",
                 "spend_ceilings", "release_gates", "shadow_mode"):
        try:
            rapid.check("ship it", accelerates="feasibility", bypasses=(gate,))
        except rapid.RapidRefused as e:
            assert gate in str(e)
            assert "not lower standards" in str(e)
        else:
            raise AssertionError(f"the rapid cell bypassed {gate}")

    # An unnamed gate is refused rather than silently permitted.
    try:
        rapid.check("ship it", accelerates="feasibility", bypasses=("some_check",))
    except rapid.RapidRefused as e:
        assert "already gone" in str(e)
    else:
        raise AssertionError("an unnamed gate was skippable")

    # And the cell's forbidden list covers the Improvement Department's protected gates, so
    # it cannot become a route around that boundary.
    assert rapid.describe()["covers_protected_gates"]


def test_culture_findings_are_routed_to_departments_that_can_act_on_them():
    """#147. A lesson that stays inside the culture engine changes nothing."""
    from brambleloop.improve import bus

    assert set(bus.route_for("cultural_territory")) == {
        "product_creativity", "market_radar", "seo_search", "portfolio"}
    assert "market_radar" in bus.route_for("cultural_timing")

    db = _db()
    lesson = bus.publish(
        db, origin_cell="market_radar", subject="cultural_territory",
        statement="retro ski lodge recurs every winter and translated well into throws",
        evidence_ref="culture:retro-halloween:2026")
    assert [x["id"] for x in bus.inbox(db, "product_creativity")] == [lesson]


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
