"""Where a number came from, and what this company stands on.

v1.4.3 requirements 38 and 50. Both are about a fact that travels without its context until
somebody needs the context urgently.

A trend figure is a measurement of a population over a window, and both get dropped the moment
it is quoted. Nobody lies: a US figure from last December is a perfectly good number, and
reading it as current Canadian demand is a decision nobody consciously makes. And a dependency
map written by hand is a snapshot of what somebody remembered on a Tuesday, with the three
"critical" items being the three they were already worried about.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.ops import dependencies as D  # noqa: E402
from brambleloop.radar import provenance as P  # noqa: E402

TODAY = date(2026, 9, 19)


def _us_last_christmas() -> P.TrendDatum:
    return P.TrendDatum("cropped cardigan", 40.0, "etsy trend report", "US",
                        "2025-11-01", "2025-12-01", shape=P.SEASONAL)


# ---- trend provenance (#38) -----------------------------------------------


def test_a_number_that_cannot_say_who_it_measured_is_refused_rather_than_discounted():
    """Discounting would imply it was weak evidence rather than none."""
    try:
        P.TrendDatum("x", 40.0, "a report", "UNKNOWN", "2026-08-01", "2026-09-01")
    except P.ProvenanceRefused as e:
        assert "weak evidence rather than none" in str(e)
    else:
        raise AssertionError("an unpopulated datum was accepted")

    try:
        P.TrendDatum("x", 40.0, "a report", "CA", "", "")
    except P.ProvenanceRefused as e:
        assert "no evidence about any time at all" in str(e)
    else:
        raise AssertionError("a datum with no window was accepted")

    try:
        P.TrendDatum("x", 40.0, "  ", "CA", "2026-08-01", "2026-09-01")
    except P.ProvenanceRefused as e:
        assert "a number somebody remembers" in str(e)
    else:
        raise AssertionError("a sourceless datum was accepted")


def test_a_neighbouring_population_is_weaker_evidence_rather_than_worthless():
    """Calling a US crochet trend worthless is as wrong as calling it equivalent."""
    us = _us_last_christmas().discounted(TODAY)
    assert 0 < us["relevance_to_ca"] < 1.0
    assert us["usable_value"] < us["raw_value"]
    assert "real evidence about Canadian demand and weaker" in us["why_discounted"]

    local = P.TrendDatum("chunky throw", 22.0, "google trends CA", "CA",
                         "2026-08-15", "2026-09-15").discounted(TODAY)
    assert local["weight"] == 1.0
    assert local["usable_value"] == local["raw_value"]


def test_staleness_is_measured_against_the_topics_own_seasonality():
    """Last January's Christmas figure is one cycle old; last January's meme is archaeology."""
    seasonal = P.TrendDatum("stockings", 50.0, "src", "CA", "2025-12-01", "2026-01-01",
                            shape=P.SEASONAL)
    fad = P.TrendDatum("a meme", 50.0, "src", "CA", "2025-12-01", "2026-01-01", shape=P.FAD)
    assert seasonal.freshness(TODAY) > 0.0
    assert fad.freshness(TODAY) == 0.0
    assert seasonal.age_days(TODAY) == fad.age_days(TODAY)


def test_the_discount_is_baked_into_the_number_rather_than_offered_beside_it():
    """A caveat beside a figure is read once and the figure travels on alone."""
    used = _us_last_christmas().discounted(TODAY)
    assert used["usable_value"] == round(40.0 * used["weight"], 4)
    assert used["usable_value"] != used["raw_value"]


def test_presenting_a_foreign_or_stale_figure_as_current_canadian_demand_is_refused():
    us = _us_last_christmas()
    try:
        P.check_presentable_as_current(us, claim="current Canadian demand is up 40%",
                                       today=TODAY)
    except P.ProvenanceRefused as e:
        assert "measured United States" in str(e)
    else:
        raise AssertionError("a US figure was presented as Canadian demand")

    stale_fad = P.TrendDatum("a meme", 50.0, "src", "CA", "2025-12-01", "2026-01-01",
                             shape=P.FAD)
    try:
        P.check_presentable_as_current(stale_fad, claim="this is trending right now",
                                       today=TODAY)
    except P.ProvenanceRefused as e:
        assert "window closed" in str(e)
    else:
        raise AssertionError("an expired fad was presented as current")

    # Saying what it actually measured is fine, and is the whole point of keeping it.
    P.check_presentable_as_current(us, claim="US demand over last December was up 40%",
                                   today=TODAY)


def test_ranking_on_usable_evidence_disagrees_with_the_headline_and_that_is_the_point():
    result = P.rank([_us_last_christmas(),
                     P.TrendDatum("chunky throw", 22.0, "google trends CA", "CA",
                                  "2026-08-15", "2026-09-15")], today=TODAY)
    assert [r["topic"] for r in result["ranked"]][0] == "chunky throw"
    assert result["raw_ranking_disagrees"] is True
    assert "routinely outranks" in result["note"]


# ---- the dependency map (#50) ---------------------------------------------


def test_a_dependency_with_no_recovery_strategy_is_refused():
    """The natural map marks three things critical, and those are the three somebody feared."""
    try:
        D.Dependency("x", "a thing", D.FATAL, "everything would stop working", "we would cope",
                     recovery_minutes=10)
    except D.DependencyRefused as e:
        assert "a dependency nobody has thought about" in str(e)
    else:
        raise AssertionError("a dependency with no recovery was accepted")


def test_impact_is_graded_by_what_stops_not_by_vendor_prestige():
    """Postgres holds the company's memory; GitHub holds a copy of code that is also on disk."""
    assert D.BY_KEY["postgres"].impact == D.FATAL
    assert D.BY_KEY["github"].impact == D.DEGRADING
    assert D.BY_KEY["railway"].impact == D.HALTING

    state = D.map_state(env={})
    assert set(state["single_points_of_failure"]) == {"postgres", "etsy_account",
                                                      "payment_rails"}
    assert "github" not in state["single_points_of_failure"]


def test_the_map_knows_which_recoveries_the_system_cannot_perform_itself():
    state = D.map_state(env={})
    assert set(state["owner_only_to_recover"]) == {
        "etsy_account", "domain_email", "payment_rails", "tester_network"}
    assert D.drill("payment_rails")["owner_only"] is True
    assert "needs the account holder" in D.drill("payment_rails")["note"]
    assert D.drill("postgres")["owner_only"] is False


def test_the_map_probes_configuration_where_it_can_and_says_nothing_where_it_cannot():
    state = D.map_state(env={"DATABASE_URL": "postgres://x"})
    configured = {d["key"]: d["configured"] for d in state["dependencies"]}
    assert configured["postgres"] is True
    assert configured["etsy_account"] is False
    # No probe exists for a tester network, and inventing one would be worse than None.
    assert configured["tester_network"] is None
    assert configured["traffic_channels"] is None


def test_every_mapped_dependency_names_what_stops_and_how_it_returns():
    for dependency in D.DEPENDENCIES:
        assert len(dependency.if_it_fails.split()) >= 5, dependency.key
        assert len(dependency.recovery.split()) >= 6, dependency.key
        assert dependency.impact in D.IMPACTS
    assert len(D.DEPENDENCIES) >= 9


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
