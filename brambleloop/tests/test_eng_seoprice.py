"""ENG-SEO-PRICE: research-shelf SEO, evidence-band pricing, the learning hook, the taxonomy path.

Pins:
- no competitor title is ever copied (verbatim, a long shared run, or rearranged);
- every product gets a taxonomy node once the stored snapshot can choose one -- including a
  profile computed before the schema was read, on a refresh that stores no new snapshot;
- prices fall inside the research band (Q1..Q3), with the evidence and reasons recorded;
- no deceptive discount (B-376), charm pricing allowed;
- the fold answers what / pattern-not-item / sizes / skill / US+UK PDFs (B-409);
- 13 tags, every one true of the product; materials and title rules;
- learning reads REAL outcomes only; bounded A/B arms (B-201);
- mutation checks on the overlap thresholds and the band.

Every Etsy tree here is ILLUSTRATIVE; every shelf listing is a fixture, never Etsy data.

Run: cd brambleloop && PYTHONPATH=src:tests .venv/bin/python tests/test_eng_seoprice.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

_ART = tempfile.TemporaryDirectory()
os.environ.setdefault("BRAMBLELOOP_ARTIFACT_DIR", _ART.name)

from brambleloop.commerce import market_fit as M  # noqa: E402

_TMP = tempfile.mkdtemp()


def _db(name: str):
    from brambleloop.agents.registry import Registry
    from brambleloop.core.db import Database

    db = Database(f"sqlite:///{_TMP}/{name}.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


SHOPS = ("MJsOffTheHookDesigns", "MadelineMaeCo", "IvyLoop", "HanJanCrochet")


def _shelf(db, rows, *, extra_shop: str | None = None):
    """rows: (shop, ref, title, tags, price, pod, sizes)."""
    from brambleloop.core.models import Benchmark, BenchmarkListing

    with db.session() as s:
        for shop in set(r[0] for r in rows) | ({extra_shop} if extra_shop else set()):
            s.add(Benchmark(key=f"bm_{shop.lower()}", shop_name=shop,
                            canonical_url=f"https://example.invalid/{shop}"))
        for shop, ref, title, tags, price, pod, sizes in rows:
            d = {"tags": list(tags)}
            if sizes is not None:
                d["size_range"] = {"sizes": sizes, "stated": True, "limited": sizes <= 3}
            s.add(BenchmarkListing(benchmark_key=f"bm_{shop.lower()}", listing_ref=ref,
                                   title=title, pod=pod, price_cad=price, detail=d))


def _facts(**kw):
    base = dict(slug="hex-basket", version="1.0.0", title="Hexagonal Bread Basket",
                category="basket", difficulty="confident beginner", sizes=[],
                size_label="22 x 9 cm", colours=2, rows=24, motifs=[],
                techniques=["texture"], materials=["Cotton DK yarn"])
    base.update(kw)
    return M.ProductFacts(**base)


POD = M.pod_for("basket", "Hexagonal Bread Basket")
BASKET_ROWS = [
    ("MJsOffTheHookDesigns", "1", "Fall for Granny Baskets Crochet Pattern Bundle",
     ["crochet basket", "basket pattern", "granny square", "storage basket"], 6.50, POD, None),
    ("MadelineMaeCo", "2", "Chunky Rope Basket Crochet Pattern Easy Beginner",
     ["crochet basket", "rope basket", "basket pattern", "home decor"], 5.00, POD, None),
    ("IvyLoop", "3", "Bread Basket Crochet Pattern Kitchen Decor",
     ["crochet basket", "bread basket", "kitchen decor"], 7.25, POD, None),
    ("HanJanCrochet", "4", "Nesting Baskets Set of Three Crochet Pattern",
     ["crochet basket", "nesting basket", "basket pattern"], 8.00, POD, None),
    ("IvyLoop", "5", "Market Tote Basket Crochet Pattern PDF",
     ["basket pattern", "crochet tote"], 6.00, POD, None),
    ("MadelineMaeCo", "6", "Mini Hexagon Basket Crochet Pattern",
     ["hexagon basket", "crochet basket"], 9.00, POD, None),
]


# ---- originality ----------------------------------------------------------------------------

def test_a_verbatim_competitor_title_is_refused():
    t = "Bread Basket Crochet Pattern Kitchen Decor"
    o = M.originality(t, [("IvyLoop", t)])
    assert not o["ok"] and o["copies"][0]["verbatim"], o
    # case and punctuation do not launder a copy
    assert not M.originality("bread basket - crochet pattern: kitchen decor!",
                             [("IvyLoop", t)])["ok"]


def test_a_long_shared_run_or_a_rearranged_title_is_refused():
    theirs = "Fall for Granny Baskets Crochet Pattern Bundle"
    run = M.originality("Cosy Fall for Granny Baskets Crochet Pattern | US and UK Terms",
                        [("MJ", theirs)])
    assert not run["ok"] and run["copies"][0]["run_len"] >= 5, run
    rearranged = M.originality("Granny Baskets Crochet Pattern Bundle Fall For",
                               [("MJ", theirs)])
    assert not rearranged["ok"], rearranged


def test_shared_generic_words_are_not_a_copy():
    ours = "Hexagonal Bread Basket Crochet Pattern | Written and Chart | US and UK Terms"
    o = M.originality(ours, [(r[0], r[2]) for r in BASKET_ROWS])
    assert o["ok"], o
    assert o["checked"] == len(BASKET_ROWS)


def test_mutation_overlap_thresholds_are_load_bearing():
    theirs = "Fall for Granny Baskets Crochet Pattern Bundle"
    ours = "Cosy Fall for Granny Baskets Crochet Pattern | US and UK Terms"
    old = M.MAX_SHARED_RUN, M.MAX_TRIGRAM_JACCARD
    try:
        M.MAX_SHARED_RUN, M.MAX_TRIGRAM_JACCARD = 99, 1.01   # mutant: checks disabled
        assert M.originality(ours, [("MJ", theirs)])["ok"]
    finally:
        M.MAX_SHARED_RUN, M.MAX_TRIGRAM_JACCARD = old
    assert not M.originality(ours, [("MJ", theirs)])["ok"]
    # mutant: generic words counted as distinctive -> a pure-generic run would be a copy
    generic_ours = "Hexagon Crochet Pattern PDF Digital Download US UK Terms"
    generic_theirs = "Rope Crochet Pattern PDF Digital Download US UK Terms"
    assert M.originality(generic_ours, [("X", generic_theirs)])["ok"]
    saved = M.GENERIC
    try:
        M.GENERIC = frozenset()
        assert not M.originality(generic_ours, [("X", generic_theirs)])["ok"]
    finally:
        M.GENERIC = saved


# ---- SEO package -----------------------------------------------------------------------------

def test_tags_are_thirteen_true_and_evidence_ranked():
    db = _db("tags")
    _shelf(db, BASKET_ROWS)
    facts = _facts()
    ev = M.keyword_evidence(M.research_listings(db, pod=POD))
    assert ev["tags"][0]["phrase"] == "crochet basket" and ev["tags"][0]["shops"] == 4
    tags, prov = M.choose_tags(facts, ev)
    assert len(tags) == M.TAG_COUNT and len(set(tags)) == M.TAG_COUNT, tags
    assert not M.tag_problems(tags), M.tag_problems(tags)
    assert all(M.is_true_of(t, facts) for t in tags), tags
    # shelf phrases that are not true of this basket never take a slot
    for untrue in ("rope basket", "granny square", "nesting basket", "crochet tote",
                   "kitchen decor"):
        assert untrue not in tags, (untrue, tags)
    assert tags[0] == "crochet basket" and prov[0]["source"] == "research_shelf"
    assert prov[0]["shops"] == 4
    assert any(p["source"] == "product_facts" for p in prov)


def test_finished_item_phrases_never_become_tags():
    facts = _facts()
    assert not M.is_true_of("handmade basket", facts)
    assert not M.is_true_of("crochet pattern", facts)       # nothing about this product
    assert M.is_true_of("bread basket", facts)


def test_title_rules_and_materials_attribute():
    assert M.title_problems("A" * 141 + " pattern")
    assert any("CHAR_REPEATED" in p for p in M.title_problems("Basket & Tray & Mat Pattern"))
    assert any("NOT_A_PATTERN" in p for p in M.title_problems("Hexagonal Bread Basket"))
    assert any("CAPS" in p for p in M.title_problems("BIG BOLD LOUD BASKET Pattern"))
    assert not M.title_problems("Hexagonal Bread Basket Crochet Pattern | US and UK Terms")
    mats = M.materials_attribute(_facts(materials=["100% Cotton DK yarn", "8/4 cotton"]))
    from brambleloop.publish import listing_schema

    assert not listing_schema.material_problems(mats), mats
    assert "yarn" in [m.lower() for m in mats] and len(mats) <= M.MATERIALS_MAX


def test_the_fold_answers_the_five_buyer_questions():
    from brambleloop.commerce import seo

    facts = _facts()
    desc = seo.build_description(
        facts.title, size_label=facts.size_label, yardage_lines=[], tolerance_pct=10,
        difficulty=facts.difficulty, colors=["cream", "sage"], terminology="US",
        gauge_line=None, stitches=["sc"], fold_facts=M.fold_sentence(facts),
        why_it_matters="Worked in 2 colours.")
    assert M.fold_problems(desc, facts) == [], (M.fold_problems(desc, facts), desc[:400])
    bare = seo.build_description(
        facts.title, size_label=facts.size_label, yardage_lines=[], tolerance_pct=10,
        difficulty=facts.difficulty, colors=["cream"], terminology="US",
        gauge_line=None, stitches=["sc"], why_it_matters="x " * 200)
    probs = M.fold_problems(bare, facts)
    assert any(p.startswith("FOLD_SKILL") for p in probs), probs
    assert any(p.startswith("FOLD_INCLUDED") for p in probs), probs
    graded = _facts(sizes=["S", "M", "L"], size_label=None)
    assert "3 sizes (S, M, L)" in M.fold_sentence(graded)


def test_seo_package_refuses_a_copied_title_and_an_unknown_category():
    from brambleloop.commerce import category as C

    db = _db("pkg")
    _shelf(db, BASKET_ROWS)
    facts = _facts()
    desc = (f"{facts.title} — a crochet pattern, not a finished item. You receive an instant "
            f"digital download. {M.fold_sentence(facts)}")
    chosen = C.CategoryChoice(C.CHOSEN, taxonomy_id=24, path_ids=[20, 21, 24],
                              path_names=["Craft Supplies & Tools", "Patterns & How To",
                                          "Patterns & Blueprints"])
    good = M.seo_package(db, facts, title="Hexagonal Bread Basket Crochet Pattern | US and "
                         "UK Terms", tags=[], description=desc, category_choice=chosen)
    assert good["ok"], good["problems"]
    assert good["taxonomy"]["taxonomy_id"] == 24 and len(good["tags"]) == 13
    copied = M.seo_package(db, facts, title="Bread Basket Crochet Pattern Kitchen Decor",
                           tags=[], description=desc, category_choice=chosen)
    assert any(p.startswith("TITLE_COPIES_COMPETITOR") for p in copied["problems"])
    unknown = M.seo_package(db, facts, title=good["title"], tags=[], description=desc,
                            category_choice=C.CategoryChoice(C.UNKNOWN))
    assert any(p.startswith("CATEGORY_UNKNOWN") for p in unknown["problems"])


def test_shops_outside_the_nine_are_not_research_evidence():
    db = _db("outsiders")
    _shelf(db, BASKET_ROWS + [("SomeOtherShop", "9", "Basket Pattern", ["x"], 99.0, POD,
                               None)])
    got = M.research_listings(db)
    assert len(got) == len(BASKET_ROWS) and all(r.shop != "SomeOtherShop" for r in got)


def test_search_certificate_carries_the_market_fit_check():
    from brambleloop.commerce import search

    base = dict(category={"status": "CHOSEN"}, properties={"complete": True},
                attribute_problems=[], copy_gate={"ok": True}, tag_problems=[],
                description_problems=[], hero={"ok": True})
    ok = search.search_certificate(**base, market_fit={"ok": True, "why": ""})
    assert ok["verdict"] == search.PASS and "market_fit" in ok["checks"]
    bad = search.search_certificate(**base, market_fit={"ok": False, "why": "TITLE_COPIES"})
    assert bad["verdict"] == search.REFUSED and "market_fit" in bad["failed"]


def test_a_rearranged_title_with_no_long_run_is_refused_by_the_trigram_rule():
    """Review b17-a B2: the trigram-Jaccard rule alone refuses this; mutating it out fails."""
    theirs, ours = "Chunky Granny Basket Tote", "Cosy Chunky Granny Basket Tote"
    o = M.overlap(ours, theirs)
    assert not o["verbatim"] and o["run_len"] <= M.MAX_SHARED_RUN, o
    assert o["trigram_jaccard"] >= M.MAX_TRIGRAM_JACCARD and o["copied"], o
    orig = M.originality(ours, [("MJ", theirs)])
    assert orig["ok"] is False and orig["copies"], orig
    old = M.MAX_TRIGRAM_JACCARD
    try:
        M.MAX_TRIGRAM_JACCARD = 1.01   # mutant: the trigram rule disabled
        assert M.originality(ours, [("MJ", theirs)])["ok"] is True
    finally:
        M.MAX_TRIGRAM_JACCARD = old


def test_an_empty_shelf_is_unknown_originality_and_fails_the_certificate():
    """Review b17-a B1: no competitor evidence is UNKNOWN, never a passing market_fit."""
    from brambleloop.commerce import category as C
    from brambleloop.commerce import search

    o = M.originality("Crochet Cat Hat Pattern", [])
    assert o["ok"] is None and o["status"] == "UNKNOWN" and o["checked"] == 0, o
    db = _db("emptyshelf")
    facts = _facts()
    desc = (f"{facts.title} — a crochet pattern, not a finished item. You receive an instant "
            f"digital download. {M.fold_sentence(facts)}")
    chosen = C.CategoryChoice(C.CHOSEN, taxonomy_id=24, path_ids=[20, 21, 24],
                              path_names=["Craft Supplies & Tools", "Patterns & How To",
                                          "Patterns & Blueprints"])
    pkg = M.seo_package(db, facts, title="Hexagonal Bread Basket Crochet Pattern | US and "
                        "UK Terms", tags=[], description=desc, category_choice=chosen)
    assert not pkg["ok"] and any(p.startswith("TITLE_ORIGINALITY_UNKNOWN")
                                 for p in pkg["problems"]), pkg["problems"]
    assert pkg["originality"]["scope"] == "all", pkg["originality"]
    blocking = [p for p in pkg["problems"] if p.startswith(("TITLE_", "FOLD_", "CATEGORY_"))]
    base = dict(category={"status": "CHOSEN"}, properties={"complete": True},
                attribute_problems=[], copy_gate={"ok": True}, tag_problems=[],
                description_problems=[], hero={"ok": True})
    cert = search.search_certificate(**base, market_fit={
        "ok": not blocking, "why": "; ".join(blocking),
        "originality": pkg["originality"]["ok"]})
    assert cert["checks"]["market_fit"]["ok"] is False and cert["verdict"] == search.REFUSED
    # even an `ok` the caller got wrong cannot pass unproven originality
    cert = search.search_certificate(**base, market_fit={"ok": True, "originality": None})
    assert cert["checks"]["market_fit"]["ok"] is False, cert


def test_the_pod_shelf_scope_is_recorded():
    """Review b17-a B4: the originality evidence says which shelf it was checked against."""
    db = _db("scope")
    _shelf(db, BASKET_ROWS)
    facts = _facts()
    pkg = M.seo_package(db, facts, title="Hexagonal Bread Basket Crochet Pattern", tags=[],
                        description="x", category_choice=None)
    assert pkg["originality"]["scope"] == "pod" and pkg["originality"]["checked"] > 0, pkg


def test_the_discount_rules_run_on_the_live_price_path():
    """Review b17-a B3: `discount_problems` is called from the price handlers, not shelf-ware."""
    import inspect

    from brambleloop.commerce import pricing
    from brambleloop.runtime import release

    src = inspect.getsource(release)
    assert src.count("_refuse_deceptive_discount(") >= 3, "both price paths call the rules"
    assert "check_no_fake_discount(decision.price_cad" not in src
    release._refuse_deceptive_discount(6.99, flagship=True)   # no was-price: nothing to refuse
    saved = M.discount_problems
    try:
        M.discount_problems = lambda **kw: ["FLAGSHIP_DISCOUNT: test"]
        try:
            release._refuse_deceptive_discount(6.99, flagship=True)
            raise AssertionError("a discount problem did not refuse the price")
        except pricing.DeceptivePricing as e:
            assert "FLAGSHIP_DISCOUNT" in str(e), e
    finally:
        M.discount_problems = saved


# ---- pricing ----------------------------------------------------------------------------------

def test_the_band_is_quartiles_of_the_research_shelf():
    db = _db("band")
    _shelf(db, BASKET_ROWS)
    b = M.price_band(db, category="basket", title="Hexagonal Bread Basket")
    assert b["status"] == M.MEASURED, b
    assert b["observations"] == 6 and len(b["shops"]) == 4
    assert b["low_cad"] == 5.00 and b["high_cad"] == 9.00
    assert b["q1_cad"] <= b["median_cad"] <= b["q3_cad"]
    assert b["median_cad"] == 6.88   # median of 5, 6, 6.5, 7.25, 8, 9


def test_a_thin_shelf_is_unknown_and_no_price_is_invented():
    db = _db("thin")
    _shelf(db, BASKET_ROWS[:3])
    b = M.price_band(db, category="basket", title="Hexagonal Bread Basket")
    assert b["status"] == M.UNKNOWN and "needs" in b["why"]
    try:
        M.decide(db, _facts(), b)
        raise AssertionError("a price was invented without an evidence band")
    except M.PriceRefused:
        pass


def test_mutation_band_minimums_are_load_bearing():
    db = _db("bandmut")
    _shelf(db, BASKET_ROWS[:3])
    old = M.MIN_BAND_OBSERVATIONS
    try:
        M.MIN_BAND_OBSERVATIONS = 1                    # mutant: any shelf is a market
        assert M.price_band(db, category="basket", title="x")["status"] == M.MEASURED
    finally:
        M.MIN_BAND_OBSERVATIONS = old
    db2 = _db("oneshop")
    _shelf(db2, [("IvyLoop", str(k), f"Basket {k} Crochet Pattern", [], 5.0 + k, POD, None)
                 for k in range(8)])
    assert M.price_band(db2, category="basket", title="x")["status"] == M.UNKNOWN
    oldshops = M.MIN_BAND_SHOPS
    try:
        M.MIN_BAND_SHOPS = 1                           # mutant: one shop is a market
        assert M.price_band(db2, category="basket", title="x")["status"] == M.MEASURED
    finally:
        M.MIN_BAND_SHOPS = oldshops


def test_the_price_is_inside_the_band_with_its_evidence_and_charm():
    db = _db("price")
    _shelf(db, BASKET_ROWS)
    band = M.price_band(db, category="basket", title="Hexagonal Bread Basket")
    simple = M.decide(db, _facts(rows=10, colours=1), band)
    rich = M.decide(db, _facts(rows=200, colours=5, sizes=["S", "M", "L", "XL", "2X"]), band)
    for d in (simple, rich):
        assert band["q1_cad"] <= d["price_cad"] <= band["q3_cad"], d
        assert d["within_band"] and d["was_price"] is None
        assert d["evidence"]["observations"] == 6 and d["evidence"]["listing_refs"]
        assert any("research band" in r for r in d["reasons"])
        assert any("complexity" in r for r in d["reasons"])
    assert rich["price_cad"] >= simple["price_cad"], (simple, rich)
    assert rich["complexity"]["score"] > simple["complexity"]["score"]
    assert f"{simple['price_cad']:.2f}".endswith("99") or "no x.99" in " ".join(
        simple["reasons"])


def test_mutation_the_band_clamp_is_load_bearing():
    """A target outside the band (complexity > 1) is still priced inside it."""
    db = _db("clamp")
    _shelf(db, BASKET_ROWS)
    band = M.price_band(db, category="basket", title="x")
    saved = M.complexity
    try:
        M.complexity = lambda f: {"score": 3.0, "parts": {"rows": 1, "sizes": 1,
                                                          "colourwork": 1}, "weights": {}}
        d = M.decide(db, _facts(), band)
        assert d["price_cad"] <= band["q3_cad"], d
    finally:
        M.complexity = saved
    # a forged band whose q3 is below every charm/net-clearing price is refused, not stretched
    tiny = dict(band, q1_cad=0.50, q3_cad=0.60, median_cad=0.55)
    try:
        M.decide(db, _facts(), tiny)
        raise AssertionError("priced outside the evidence band")
    except M.PriceRefused:
        pass


def test_charm_pricing_stays_in_band():
    assert M.charm(6.40, 5.5, 7.5)[0] == 5.99
    assert M.charm(6.80, 5.5, 7.5)[0] == 6.99
    assert M.charm(6.02, 6.01, 6.05)[0] == 6.02   # no x.99 inside: target kept


def test_no_deceptive_discount_b376():
    assert any("DECEPTIVE" in p for p in M.discount_problems(
        price_cad=6.99, was_price_cad=12.0, ever_charged=False, flagship=False))
    assert any("DECEPTIVE" in p for p in M.discount_problems(
        price_cad=6.99, was_price_cad=6.99, ever_charged=True, flagship=False))
    assert any("FLAGSHIP" in p for p in M.discount_problems(
        price_cad=6.99, was_price_cad=8.99, ever_charged=True, flagship=True))
    assert any("TOO_OFTEN" in p for p in M.discount_problems(
        price_cad=6.99, was_price_cad=8.99, ever_charged=True, flagship=False,
        discounted_days=10, live_days=30))
    assert M.discount_problems(price_cad=6.99, was_price_cad=None, ever_charged=False,
                               flagship=True) == []
    assert M.discount_problems(price_cad=6.99, was_price_cad=8.99, ever_charged=True,
                               flagship=False, discounted_days=2, live_days=30) == []


def test_graded_pods_narrow_to_the_same_size_range():
    db = _db("sized")
    hat = M.pod_for("hat", "Ribbed Beanie")
    rows = ([("IvyLoop", f"a{k}", f"Beanie {k} Crochet Pattern", [], 4.0 + k * 0.1, hat, 1)
             for k in range(3)]
            + [("MadelineMaeCo", f"b{k}", f"Graded Hat {k} Crochet Pattern", [], 9.0 + k, hat,
                6) for k in range(3)]
            + [("HanJanCrochet", f"c{k}", f"Family Hat {k} Crochet Pattern", [], 10.0 + k,
                hat, 7) for k in range(3)])
    _shelf(db, rows)
    many = M.price_band(db, category="hat", title="Ribbed Beanie", sizes=6)
    assert many["status"] == M.MEASURED and many["size_filter"].startswith("same size"), many
    assert many["low_cad"] >= 9.0
    one = M.price_band(db, category="hat", title="Ribbed Beanie", sizes=1)
    assert one["size_filter"].startswith("widened"), one


# ---- learning hook ----------------------------------------------------------------------------

def _outcome(db, slug, price, visits, orders, favs, provenance, start="2026-11-01",
             end="2026-11-07"):
    from brambleloop.commerce import evidence_provenance as EP
    from brambleloop.core.models import ListingOutcome

    with db.session() as s:
        s.add(ListingOutcome(product_slug=slug, version="1.0.0", period_start=start,
                             period_end=end, impressions=visits * 10, visits=visits,
                             favourites=favs, orders=orders, source="owner_export:test",
                             detail=EP.mark({"price_cad": price}, provenance)))


def test_choices_are_recorded_and_synthetic_outcomes_teach_nothing():
    db = _db("learn")
    M.record_choice(db, slug="hex-basket", version="1.0.0", kind="price",
                    choice={"price_cad": 6.99, "band_cad": [6.0, 8.0]})
    M.record_choice(db, slug="hex-basket", version="1.0.0", kind="seo",
                    choice={"tags": ["crochet basket", "bread basket"]})
    assert [c["kind"] for c in M.choices(db, "hex-basket")] == ["price", "seo"]
    _outcome(db, "hex-basket", 6.99, 500, 9, 30, "synthetic")
    _outcome(db, "hex-basket", 7.99, 500, 9, 30, "synthetic", "2026-11-08", "2026-11-14")
    got = M.learn(db, "hex-basket")
    assert got["state"] == "UNMEASURED" and got["lessons"] == [], got


def test_real_outcomes_publish_lessons_and_price_points():
    from brambleloop.core.models import Lesson
    from sqlalchemy import select

    db = _db("learnreal")
    M.record_choice(db, slug="hex-basket", version="1.0.0", kind="seo",
                    choice={"tags": ["crochet basket", "bread basket"]})
    _outcome(db, "hex-basket", 6.99, 400, 8, 20, "real")
    _outcome(db, "hex-basket", 7.99, 400, 8, 25, "real", "2026-11-08", "2026-11-14")
    got = M.learn(db, "hex-basket")
    assert got["state"] == "measured" and len(got["lessons"]) == 2, got
    assert got["best_price_cad"] == 7.99          # same orders, higher net per sale
    with db.session() as s:
        subjects = sorted(l.subject for l in s.scalars(select(Lesson)))
    assert subjects == ["pricing_response", "search_language"], subjects
    # idempotent on evidence: re-learning the same outcomes is one lesson each
    again = M.learn(db, "hex-basket")
    assert sorted(again["lessons"]) == sorted(got["lessons"])
    pts = M.outcome_points(db, "hex-basket")
    assert [p["price_cad"] for p in pts] == [6.99, 7.99] and all(p["visits"] == 400
                                                                 for p in pts)


def test_price_arms_are_bounded():
    arms = M.price_arms(6.99, (6.0, 8.0))
    assert len(arms) <= M.MAX_ARMS and arms[0]["arm"] == "control"
    for a in arms[1:]:
        assert 6.0 <= a["price_cad"] <= 8.0
        gap = abs(a["price_cad"] - 6.99) / 6.99
        assert M.MIN_ARM_GAP <= gap <= M.ARM_STEP + 1e-9, a
    # a band too narrow for a measurable variant has the control only
    assert M.price_arms(6.99, (6.90, 7.10)) == [{"arm": "control", "price_cad": 6.99}]


# ---- the taxonomy snapshot path ---------------------------------------------------------------

def test_an_unknown_profile_gets_a_category_on_a_refresh_that_stores_no_new_snapshot():
    """Production: the snapshot that could choose was stored once; every later refresh
    confirms it. The profile computed before it stayed UNKNOWN for ever."""
    import fixtures_etsy_taxonomy as FX
    from sqlalchemy import select

    from brambleloop.core.models import (AuditLog, EtsyTaxonomySnapshot, Job, JobStatus,
                                         ListingSearchProfile)
    from brambleloop.integrations import etsy_taxonomy as T
    from brambleloop.integrations import taxonomy_drift as D
    from brambleloop.products.vessels import build_hexagon_coaster
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime import pipeline  # noqa: F401
    from brambleloop.runtime.worker import Worker
    from brambleloop.core.models import Phase

    db = _db("taxpath")
    JobQueue(db).enqueue("quality_director", "gate.certify",
                         {"cir": build_hexagon_coaster().to_dict()})
    w = Worker(db, "seoprice-chain")
    for _ in range(100):
        if not w.run_once():
            break
    with db.session() as s:
        prof = s.scalar(select(ListingSearchProfile).where(
            ListingSearchProfile.product_slug == "hexagon-coaster-set"))
        assert prof is not None and prof.category_status == "UNKNOWN", prof
        slug, version = prof.product_slug, prof.version
        assert prof.snapshot_id is None
        s.add(AuditLog(actor="market_radar", action="etsy.probe", artifact="fixture",
                       detail={"ok": True, "application_id": "fixture"}))
    assert os.environ.get(D.REQUEUE_VAR) is None       # the owner switch stays off

    def refresh(key):
        T.client_factory = lambda _db: FX.RecordedTaxonomyClient()
        try:
            JobQueue(db).enqueue("listing", "listing.taxonomy_refresh", {}, priority=0,
                                 idempotency_key=key)
            ww = Worker(db, f"w-{key}", phase=Phase.SHADOW,
                        job_types=["listing.taxonomy_refresh"])
            for _ in range(5):
                if not ww.run_once():
                    break
        finally:
            T.client_factory = None
        with db.session() as s:
            return dict(s.scalar(select(Job).where(Job.idempotency_key == key)).outputs or {})

    # The production hole, reproduced: the first refresh that stored the deciding snapshot
    # ran under the code before this fix (no backfill), so the profiles stayed UNKNOWN.
    real = D.backfill_unknown
    D.backfill_unknown = lambda ctx, snapshot_id: {"state": "pre-fix", "queued": []}
    try:
        first = refresh("tx-1")
    finally:
        D.backfill_unknown = real
    assert first["ran"] and first["new_snapshot"] is True, first
    with db.session() as s:
        assert s.scalar(select(ListingSearchProfile).where(
            ListingSearchProfile.product_slug == slug)).category_status == "UNKNOWN"
    second = refresh("tx-2")
    assert second["ran"] and second["new_snapshot"] is False, second
    queued = second["category_backfill"]["queued"]
    assert slug in [q["slug"] for q in queued], second["category_backfill"]
    with db.session() as s:
        jobs = [j for j in s.scalars(select(Job).where(Job.job_type == "listing.seo"))
                if "catfill" in (j.idempotency_key or "")]
        assert jobs and all(j.inputs.get("fix_only") is True for j in jobs), jobs
    ww = Worker(db, "seoprice-seo", phase=Phase.SHADOW, job_types=["listing.seo"])
    for _ in range(40):
        if not ww.run_once():
            break
    with db.session() as s:
        prof = s.scalar(select(ListingSearchProfile).where(
            ListingSearchProfile.product_slug == slug))
        assert prof.category_status == "CHOSEN" and prof.taxonomy_id, prof.category_status
        snap = s.scalar(select(EtsyTaxonomySnapshot))
        assert prof.snapshot_id == snap.id
        # fix-only: never launch.plan or store.publish from the backfill
        assert not [j for j in s.scalars(select(Job).where(Job.job_type.in_(
            ("launch.plan", "store.publish")))) if "catfill" in (j.idempotency_key or "")]
    # once per snapshot: a third refresh queues nothing new
    third = refresh("tx-3")
    assert third["category_backfill"]["queued"] == [], third["category_backfill"]
    # and a re-run still pending is not re-reported as queued (no double count)
    fourth = refresh("tx-4")
    assert fourth["category_backfill"]["queued"] == [], fourth["category_backfill"]
    from brambleloop.commerce import category as C

    assert C.publish_inputs(db, slug=slug, version=version)["status"] == C.CHOSEN


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    assert tests
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"OK   {name}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            import traceback

            print(f"FAIL {name}: {type(exc).__name__}: {exc}"[:1500])
            traceback.print_exc(limit=3)
    print(f"{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
