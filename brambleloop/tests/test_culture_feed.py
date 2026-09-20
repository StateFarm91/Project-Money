"""A radar with a source, and the ways a source makes it easy to say more than it knows.

The radar refused to report trends for as long as it had no feed, correctly: a source-less
radar reporting nothing looks exactly like a radar with a quiet week. Connecting one removes
that excuse and introduces three new ways to be wrong -- calling reference reading "search
interest", treating one shop's shelf as a marketplace, and carrying the day's most-read
article forward as an opportunity when it is a disaster.
"""
from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import BenchmarkListing  # noqa: E402
from brambleloop.culture import classify as C  # noqa: E402
from brambleloop.culture import demand as D  # noqa: E402
from brambleloop.culture import feeds as F  # noqa: E402
from brambleloop.culture import radar as R  # noqa: E402

TODAY = date(2026, 9, 20)


def _db() -> Database:
    db = Database("sqlite://")
    db.create_all()
    return db


def _days(views):
    return lambda url: {"items": [{"timestamp": f"2026{m:02d}{d:02d}00", "views": v}
                                  for (m, d, v) in views]}


def _flat(n=28, base=100):
    rows = [(8, i + 1, base + i) for i in range(n)]
    return lambda url: {"items": [{"timestamp": f"2026{m:02d}{d:02d}00", "views": v}
                                  for (m, d, v) in rows]}


# ---- what the feed measures, and what it must never be called ---------------


def test_the_channel_is_reference_and_never_search():
    """#140 measures the gap between looking something up and buying it.

    A feed that recorded pageviews under the name `search` would make the lead-lag model
    compare a series against a mislabelled copy of itself, and the comparison would look
    like it worked.
    """
    assert F.CHANNEL == "reference"
    state = F.state(_db())
    assert "search volume" in state["does_not_measure"]
    assert state["requires_a_key"] is False
    assert state["cost_cad_per_month"] == 0.0


def test_the_pipeline_lag_is_carried_rather_than_hidden():
    """A reading dated today from a pipeline that cannot know today is a phantom collapse."""
    start, end = F.window(TODAY)
    assert (TODAY - end).days == F.PIPELINE_LAG_DAYS
    got = F.reading("Crochet", today=TODAY, get=_flat())
    assert got.observed_on == end.isoformat()
    assert got.observed_on < TODAY.isoformat()


def test_an_empty_series_refuses_rather_than_recording_zero_interest():
    """A topic nobody reads about and a topic the API has no data for are opposite facts."""
    raised = None
    try:
        F.reading("Nothing", today=TODAY, get=lambda url: {"items": []})
    except F.FeedRefused as exc:
        raised = exc
    assert raised is not None and "empty series" in str(raised)


def test_a_holed_series_fails_the_probe():
    """Holes in a momentum reading do not announce themselves downstream."""
    db = _db()
    record = F.probe(db, today=TODAY, get=_flat(n=4))
    assert record["ok"] is False
    assert "days of a" in record["reason"]
    assert F.usable(db) is False


def test_a_real_series_opens_the_feed():
    db = _db()
    assert F.probe(db, today=TODAY, get=_flat())["ok"] is True
    assert F.usable(db) is True


def test_every_recorded_reading_names_where_it_came_from():
    """The culture_feed gate counts observations that name a source, and this is why."""
    db = _db()
    out = F.sweep(db, ["Crochet"], today=TODAY, get=_flat())
    assert out["recorded"] == 1
    assert out["readings"][0]["source"].startswith(F.SOURCE_KEY)
    assert F.state(db)["sourced_observations"] == 1


def test_a_sweep_that_recorded_nothing_says_why():
    db = _db()
    out = F.sweep(db, ["Bad"], today=TODAY, get=lambda url: {"items": []})
    assert out["recorded"] == 0
    assert out["failures"] and "empty series" in out["failures"][0]["why"]


def test_the_courtesy_limit_is_here_rather_than_in_configuration():
    """A limit somebody can raise without this repository recording it is not a limit."""
    raised = None
    try:
        F.sweep(_db(), [f"t{i}" for i in range(F.MAX_ARTICLES_PER_SWEEP + 1)],
                today=TODAY, get=_flat())
    except F.FeedRefused as exc:
        raised = exc
    assert raised is not None and "courtesy limit" in str(raised)


def test_the_standing_topics_are_article_titles_rather_than_this_builds_vocabulary():
    """Found by reading a production sweep: 7 of 12 recorded, 5 named as failures.

    The list was derived from the radar's domain keys -- "Viral Aesthetic", "Nostalgia Era",
    "Seasonal Tradition", "Celebrity Aesthetic" -- which are filing categories this build
    invented, not things anybody has written an encyclopaedia article about. It was visible
    only because a missing article refuses rather than returning zero; a feed that returned
    zero would have recorded five topics as having no cultural interest at all.
    """
    from brambleloop.culture.radar import DOMAINS

    invented = {d.replace("_", " ").title() for d in DOMAINS}
    overlap = invented & set(F.STANDING_TOPICS)
    assert overlap == set(), f"{sorted(overlap)} are this build's words, not article titles"
    assert "Crochet" in F.STANDING_TOPICS
    assert len(F.STANDING_TOPICS) >= 8


# ---- discovery --------------------------------------------------------------


def test_discovery_drops_meta_pages():
    """A radar reporting that Main Page is trending is ignored by the second week."""
    got = F.discover(today=TODAY, get=lambda url: {"items": [{"articles": [
        {"article": "Main_Page", "views": 9, "rank": 1},
        {"article": "Special:Search", "views": 8, "rank": 2},
        {"article": "Wednesday_(TV_series)", "views": 7, "rank": 3}]}]})
    assert [t["article"] for t in got["topics"]] == ["Wednesday_(TV_series)"]
    assert got["considered"] == 3


def test_an_empty_ranking_refuses():
    raised = None
    try:
        F.discover(today=TODAY, get=lambda url: {"items": [{"articles": []}]})
    except F.FeedRefused as exc:
        raised = exc
    assert raised is not None and "different facts" in str(raised)


def test_discovery_exists_because_a_hand_written_list_finds_only_what_its_author_knew():
    got = F.discover(today=TODAY, get=lambda url: {"items": [{"articles": [
        {"article": "A", "views": 1, "rank": 1}]}]})
    assert "already knew" in got["note"]


# ---- filing -----------------------------------------------------------------


def test_a_topic_outside_the_domain_vocabulary_is_refused():
    """An open vocabulary accepts 'culture', and a radar whose finding is 'culture' has
    found nothing."""
    raised = None
    try:
        C.parse('{"A": "culture"}', ["A"])
    except C.ClassificationRefused as exc:
        raised = exc
    assert raised is not None and "vocabulary is closed" in str(raised)


def test_a_filing_about_a_topic_nobody_raised_is_refused():
    """It would enter the radar as an observation of something the model invented."""
    raised = None
    try:
        C.parse('{"B": "film"}', ["A"])
    except C.ClassificationRefused as exc:
        raised = exc
    assert raised is not None and "was not asked about" in str(raised)


def test_deaths_and_disasters_are_flagged_whatever_domain_they_file_under():
    """The most-read article on a given day is frequently one of those."""
    assert C.sensitive("2026_Nepal_earthquake") is True
    assert C.sensitive("Death_of_a_public_figure") is True
    assert C.sensitive("Wednesday_(TV_series)") is False


def test_filing_is_never_permission():
    """A domain is a filing decision and rights are a legal one; collapsing them is how a
    protected character becomes a product because it was filed under `film`."""
    assert C.classify([], db=None)["filed"] == {}
    filed = C.classify(["Wednesday_(TV_series)"],
                       provider=_FilingProvider('{"Wednesday_(TV_series)": "television"}'))
    assert filed["placed"] == {"Wednesday_(TV_series)": "television"}
    assert "filing is not permission" in filed["note"]
    assert "culture.rights" in filed["note"]
    assert "never become products" in filed["sensitive_note"]


class _FilingProvider:
    model = C.CLASSIFY_MODEL
    cost_per_1k_input_cad = 0.0
    cost_per_1k_output_cad = 0.0

    def __init__(self, text):
        self.text = text

    @staticmethod
    def key():
        return "k"

    def complete(self, system, user, *, max_tokens):
        from brambleloop.gateway.model_gateway import ModelResponse

        return ModelResponse(text=self.text, provider="anthropic", model=self.model,
                             input_tokens=10, output_tokens=10, latency_ms=1.0)


def test_a_provider_failure_leaves_the_list_unfiled_rather_than_empty():
    """An unfiled topic list is not an empty culture."""
    from brambleloop.core.resilience import TransientError

    class _Broken(_FilingProvider):
        def complete(self, system, user, *, max_tokens):
            raise TransientError("provider said no")

    out = C.classify(["A"], provider=_Broken(""))
    assert out["filed"] == {}
    assert "provider said no" in out["reason"]
    assert "not an empty culture" in out["note"]


# ---- the marketplace half of the lead-lag model -----------------------------


def _listing(db, ref, title, *, first_seen):
    with db.session() as s:
        s.add(BenchmarkListing(benchmark_key="mjs_off_the_hook_designs", listing_ref=ref,
                               title=title, pod="hats", first_seen=first_seen))


def test_a_topic_with_too_few_listings_is_unmeasured_and_not_zero():
    """A benchmark that never published into a topic and a topic with no demand are the
    same empty list and opposite facts."""
    db = _db()
    _listing(db, "1", "Wednesday inspired hat",
             first_seen=datetime(2026, 8, 1, tzinfo=timezone.utc))
    got = D.series(db, "Wednesday", today=TODAY)
    assert got["measurable"] is False
    assert "opposite facts" in got["unmeasured_is_not_zero"]


def test_the_series_says_it_is_one_shop_publishing_rather_than_a_market_buying():
    db = _db()
    for i in range(6):
        _listing(db, f"w{i}", "Wednesday inspired hat",
                 first_seen=datetime(2026, 7, 1, tzinfo=timezone.utc) + timedelta(weeks=i))
    got = D.series(db, "Wednesday", today=TODAY)
    assert got["measurable"] is True
    assert got["shops"] == 1
    assert "not how often buyers bought" in got["measures"]
    assert "sample of one" in got["width"]


def test_short_and_common_words_never_match_a_listing():
    """"the" in a title is not evidence about "The Last of Us"."""
    assert D.terms("The_Last_of_Us") == ["last"]
    assert D.terms("A_TV_Series") == []


def test_a_topic_with_no_distinguishing_word_refuses_to_match_everything():
    db = _db()
    got = D.series(db, "The_TV", today=TODAY)
    assert got["measurable"] is False
    assert "matches everything" in got["reason"]


# ---- the two series together ------------------------------------------------


def test_lead_lag_reads_the_channel_the_feed_actually_writes():
    """It defaulted to `search` while unreachable, and would have found zero readings on
    the day a feed arrived -- reporting 'not measurable' against a database of measurements.
    """
    db = _db()
    for i, interest in enumerate((0.2, 0.9, 0.5)):
        R.observe(db, "wednesday", channel=F.CHANNEL, interest=interest,
                  observed_on=f"2026-08-0{i + 1}", source="test")
    for i, interest in enumerate((0.1, 0.4, 1.0)):
        R.observe(db, "wednesday", channel=D.CHANNEL, interest=interest,
                  observed_on=f"2026-09-0{i + 1}", source="test")
    out = R.lead_lag(db, "wednesday")
    assert out["measurable"] is True
    assert out["lead_days"] > 0
    assert out["is_a_leading_indicator"] is True


def test_the_weights_half_of_147_is_named_unmeasured_rather_than_approximated():
    """A weight that moved for no reason looks exactly like a weight that learned."""
    out = R.findings(_db())
    assert out["weights_measurable"] is False
    assert "Nothing has launched" in out["why_weights_are_unmeasured"]
    assert set(out["routes"]) >= {"market_radar", "seo", "seasonal", "improvement"}


def test_a_sensitive_signal_is_routed_nowhere():
    db = _db()
    for i, interest in enumerate((0.2, 0.9)):
        R.observe(db, "2026_earthquake", channel=F.CHANNEL, interest=interest,
                  observed_on=f"2026-08-0{i + 1}", source="test")
    out = R.findings(db)
    found = [f for f in out["findings"] if f["signal"] == "2026_earthquake"]
    if found:
        assert found[0]["sensitive"] is True
        assert found[0]["routes_to"] == []


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
