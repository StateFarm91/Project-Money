"""W4-C09: SEO and listing language (F-016, F-017, F-018, F-038, F-047, F-050, F-051, F-053,
F-054, F-055). F-007 was already built (category.properties_for); see C09.md.

Fixtures only: no network, no Etsy call, no spend. Each test names its row.
Run: cd brambleloop && python3 tests/test_w4_c09_seo.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import os
import socket
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
_TMP = tempfile.mkdtemp(prefix="w4_c09_")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")


def _no_network(*_a, **_k):
    raise OSError("network refused by the C09 harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.commerce import intent, portfolio, search, search_discipline as sd, seo, trust  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import BenchmarkListing, Listing  # noqa: E402

_n = [0]


def _db():
    _n[0] += 1
    db = Database(f"sqlite:///{_TMP}/c09_{_n[0]}.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _copy(title="Nordic Forest Mosaic Throw Crochet Pattern", tags=None):
    tags = tags or [f"mosaic throw{i} pattern" for i in range(13)]
    return seo.ListingCopy(title=title, description="x " * 200, tags=tags, price_cad=9.0,
                           materials=["yarn"])


def _bench(db, rows):
    with db.session() as s:
        for i, (title, pod) in enumerate(rows):
            s.add(BenchmarkListing(benchmark_key="mjs", listing_ref=str(9000 + i), title=title,
                                   pod=pod))


# ---- F-017 No typo SEO -------------------------------------------------------------------

def test_f017_a_misspelt_title_or_tag_is_blocked():
    bad = seo.check_search_copy(_copy(title="Nordic Mosaic Throw Crochte Patern"))
    assert any(p.startswith("LISTING_TYPO") and "crochte" in p for p in bad["blocking"]), bad
    tags = [f"mosaic throw{i} pattern" for i in range(12)] + ["blankit pattern"]
    assert any(p.startswith("LISTING_TYPO") for p in seo.check_search_copy(
        _copy(tags=tags))["blocking"])
    ok = seo.check_search_copy(_copy(title="Hexie Coaster Set Crochet Pattern"))
    assert not any(p.startswith("LISTING_TYPO") for p in ok["blocking"]), ok["blocking"]
    assert sd.typos("cozy colour beanies stockings") == []        # variants and plurals


# ---- F-016 Regional phrases --------------------------------------------------------------

def test_f016_a_respelling_is_redundant_and_one_regional_slot_at_most():
    q = [search.Query(p, 0.5, 0.3, "product") for p in
         ("colour block blanket", "color block blanket", "jumper crochet pattern",
          "toque crochet pattern", "sweater crochet pattern")]
    tags = search.choose_tags(q)
    assert not ({"colour block blanket", "color block blanket"} <= set(tags)), tags
    assert sum(1 for t in tags if sd.regional_terms(t)) <= sd.MAX_REGIONAL_SLOTS, tags


# ---- F-018 Language discipline -----------------------------------------------------------

def test_f018_a_translation_needs_a_sufficient_quality_review_by_someone_else():
    tags = [f"tag{i} word{i}" for i in range(12)] + ["patron ganchillo"]
    rec = {"language": "es", "reason": "Spanish edition of the PDF ships with it",
           "translated_by": "t"}
    no_review = seo.check_search_copy(_copy(tags=tags), translation_record=rec)
    assert any("quality review" in p for p in no_review["blocking"]), no_review
    weak = seo.check_search_copy(_copy(tags=tags), translation_record={
        **rec, "quality": {"verdict": "rough", "reviewed_by": "r"}})
    assert any("not 'sufficient'" in p for p in weak["blocking"]), weak
    self_review = seo.check_search_copy(_copy(tags=tags), translation_record={
        **rec, "quality": {"verdict": "sufficient", "reviewed_by": "t"}})
    assert any("other than the translator" in p for p in self_review["blocking"])
    ok = seo.check_search_copy(_copy(tags=tags), translation_record={
        **rec, "quality": {"verdict": "sufficient", "reviewed_by": "native-reader"}})
    assert not any(p.startswith("LISTING_LANGUAGE") for p in ok["blocking"]), ok
    assert seo.SHOP_LANGUAGE == "en"


# ---- F-038 First-party priority ----------------------------------------------------------

def test_f038_etsy_recommendations_outrank_internal_heuristics_in_the_same_area():
    from brambleloop.commerce import search_visibility as sv

    db = _db()
    sv.ensure_tables(db)
    now = datetime(2026, 10, 27, tzinfo=timezone.utc)
    with db.session() as s:
        s.add(sv.SearchVisibilityItem(key="k1", scope="listing", listing_id="111",
                                      category="Tags", remediation="add more relevant tags",
                                      state=sv.OPEN, first_seen_at=now, last_seen_at=now,
                                      last_seen_reading_id=1))
    out = sv.precedence(db, listing_id="111", internal=[
        "LISTING_TAG_SLOTS_UNUSED: 11 of 13", "DESCRIPTION_KEYWORD_REPEAT: x"])
    assert out["ordered"][0]["source"] == "etsy_search_visibility"
    assert out["superseded"] == ["LISTING_TAG_SLOTS_UNUSED: 11 of 13"]
    assert all(o.get("finding") for o in out["ordered"][1:])      # nothing dropped
    assert sv.precedence(db, listing_id="222", internal=["LISTING_TAG_X"])["superseded"] == []


# ---- F-047 Star Seller framing -----------------------------------------------------------

def test_f047_star_seller_is_a_trust_signal_never_a_ranking_input():
    r = trust.star_seller_reading(awarded=None)
    assert r["kind"] == "trust_conversion" and r["ranking_input"] is False
    assert r["state"] == trust.UNMEASURED
    try:
        trust.refuse_star_seller_as_ranking(["relevance", "star_seller"])
    except trust.TrustRefused:
        pass
    else:
        raise AssertionError("Star Seller accepted as a ranking factor")
    trust.refuse_star_seller_as_ranking(["relevance", "recency"])


# ---- F-050 Strategic-reason exemption ----------------------------------------------------

def test_f050_a_recorded_strategic_reason_exempts_a_competing_pair():
    db = _db()
    with db.session() as s:
        for slug in ("hat-a", "hat-b"):
            s.add(Listing(product_slug=slug, version="1",
                          title="Christmas Beanie Hat Crochet Pattern",
                          description="christmas beanie hat crochet pattern",
                          tags=["christmas beanie", "beanie hat pattern"]))
    before = portfolio.diversification(db)
    assert before["competing_pairs"] and not before["exempted_pairs"], before
    try:
        portfolio.record_strategic_overlap(db, between=("hat-a", "hat-b"), reason="sizes",
                                           recorded_by="t")
    except portfolio.PortfolioRefused:
        pass
    else:
        raise AssertionError("a one-word reason was accepted")
    portfolio.record_strategic_overlap(
        db, between=("hat-a", "hat-b"), recorded_by="t",
        reason="the adult and child sizes of one design, listed separately on purpose")
    after = portfolio.diversification(db)
    assert after["competing_pairs"] == [] and after["exempted_pairs"][0]["strategic_reason"]


# ---- F-051 Expansion planner -------------------------------------------------------------

def test_f051_observed_demand_in_an_uncovered_pod_becomes_a_coverage_gap():
    from brambleloop.intel import coverage

    db = _db()
    assert portfolio.expansion_plan(db)["measurable"] is False
    _bench(db, [(f"Tote Bag Crochet Pattern {i}", "bags") for i in range(4)]
           + [("Beanie Crochet Pattern", "hats")])
    with db.session() as s:
        s.add(Listing(product_slug="hat-a", version="1", title="Beanie Hat Crochet Pattern",
                      description="", tags=[]))
    plan = portfolio.expansion_plan(db)
    assert [o["pod"] for o in plan["opportunities"]] == ["bags"], plan
    q = coverage.queue(db, portfolio.EXPANSION_BENCHMARK_KEY)
    assert [g["pod"] for g in q] == ["bags"], q
    assert portfolio.expansion_plan(db)["gaps"] == plan["gaps"]     # idempotent upsert


# ---- F-053 Evidence-backed gift intent ---------------------------------------------------

def test_f053_gift_phrases_need_an_observed_phrase_behind_them():
    assert not intent.gift_supported("diy gift crochet pattern", set())
    observed = {"christmas stocking crochet pattern gift for her"}
    assert intent.gift_supported("crochet christmas gift", observed)
    assert not intent.gift_supported("crochet halloween gift", observed)


# ---- F-054 Solution-oriented intent ------------------------------------------------------

def test_f054_problem_solved_is_a_modelled_facet_with_a_listing_test():
    from brambleloop.commerce import listing_tests

    m = intent.map_product(object="blanket", recipient_or_use="home decor",
                           season_event="christmas", problem_solved="stash buster")
    rows = intent.phrases(m)
    assert any(r["pattern"] == "problem_led" and r["phrase"].startswith("stash buster")
               for r in rows), rows
    try:
        intent.map_product(object="blanket", recipient_or_use="home decor",
                           season_event="christmas", problem_solved="cures boredom")
    except intent.IntentRefused:
        pass
    else:
        raise AssertionError("an unmodelled solution claim was accepted")
    e = intent.solution_experiment(product="fixture", problem="scrap yarn",
                                   today=date(2026, 10, 27))
    assert listing_tests.experiment_variables(e.key) == ("title", "tags")


# ---- F-055 Evidence-backed aesthetic -----------------------------------------------------

def test_f055_the_fallback_carries_an_aesthetic_only_when_the_name_and_market_agree():
    db = _db()
    assert intent.evidenced_aesthetic(db, "nordic-forest-mosaic-throw") == ""   # no evidence
    _bench(db, [("Nordic Star Ornament Crochet Pattern", "ornaments")])
    assert intent.evidenced_aesthetic(db, "nordic-forest-mosaic-throw") == "nordic"
    assert intent.evidenced_aesthetic(db, "hexie-coaster-set") == ""   # name carries none
    out = intent.listing_language(db, slug="nordic-forest-mosaic-throw",
                                  category="mosaic_blanket", season="Christmas",
                                  difficulty="intermediate")
    assert out["facets"].get("aesthetic") == "nordic", out


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
