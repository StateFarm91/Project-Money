"""Wave 3, cluster K1: search and listing truth residuals.

Rows F-001 F-002 F-013 F-022 F-028 F-030 F-058 F-060 F-242 F-251 F-254 F-255 F-257 F-291,
plus the lane G/I carry-overs: Etsy's "no leading ' or -" tag rule on the release chain's own
drafts, and the API-key-only seller-taxonomy read. No test makes a network call: the taxonomy
read answers from recorded shapes through an injected transport.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from brambleloop.commerce import search, seo  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402


def _db() -> Database:
    tmp = tempfile.mkdtemp()
    db = Database(f"sqlite:///{tmp}/k1.sqlite")
    db.create_all()
    return db


def _copy(**kw) -> seo.ListingCopy:
    base = dict(title="Market Basket Trio | Crochet Pattern PDF | 3 Sizes",
                tags=[f"tag{i} word{i}" for i in range(13)], description="d" * 400,
                materials=[], price_cad=9.0, supported_claims=[])
    base.update(kw)
    return seo.ListingCopy(**base)


# ---- F-001 two-stage search model -----------------------------------------------------------

def test_match_eligibility_and_rank_readiness_are_separate_stages():
    head = search.Query("crochet basket pattern", demand=0.9, competition=0.95)  # unreachable
    tail = search.Query("hexagon nesting basket", demand=0.2, competition=0.3)
    miss = search.Query("bread basket liner", demand=0.2, competition=0.3)
    report = search.score_coverage([head, tail, miss],
                                   title="Hexagon Nesting Basket | Crochet Basket Pattern",
                                   tags=[], description="")
    stages = report.to_dict()["stages"]
    # Stage 1 counts the head-term match even though a new shop cannot rank there.
    assert stages["match"]["matched"] == 2 and stages["match"]["match_rate"] == round(2 / 3, 4)
    assert "competition is not read" in stages["match"]["basis"]
    assert "bread basket liner" in stages["match"]["unmatched"]
    # Stage 2 reads only reachable value and carries the placement-weighted proxy.
    assert stages["rank"]["reachable_queries"] == 2
    assert stages["rank"]["placement_weighted_share"] == report.share


# ---- F-002 query coverage matrix, served ----------------------------------------------------

def _profile(db, slug="hexagon-coaster-set", version="1.0.0", verdict="PENDING"):
    from brambleloop.core.models import ListingSearchProfile

    matrix = [{"phrase": "hexagon coaster", "family": "motif", "intent": "product",
               "provenance": "assumed", "read_at": None, "reachable": True,
               "field": "tag_exact"},
              {"phrase": "coaster set pattern", "family": "core", "intent": "product",
               "provenance": "assumed", "read_at": None, "reachable": True, "field": None}]
    with db.session() as s:
        s.add(ListingSearchProfile(product_slug=slug, version=version, verdict=verdict,
                                   coverage_matrix=matrix, certificate={"verdict": verdict}))
    return matrix


def test_the_query_field_matrix_is_served_per_listing():
    from brambleloop.commerce import search_evidence as se

    db = _db()
    matrix = _profile(db)
    out = se.summary(db)
    assert out["items"], out
    item = out["items"][0]
    assert item["query_field_matrix"] == matrix
    assert item["match"]["by_field"] == {"tag_exact": 1}
    assert item["match"]["match_rate"] == 0.5


def test_the_search_evidence_route_is_registered():
    from brambleloop.app.storefront_api import make_router

    paths = {r.path for r in make_router(_db()).routes}
    assert "/api/search-evidence" in paths


# ---- F-013 tag diversity --------------------------------------------------------------------

def test_semantic_duplicates_are_found_where_lexical_comparison_sees_three_strings():
    tags = ["crochet afghan", "afghan crochet", "crochet blankets", "hexagon basket",
            "hexagonal basket", "baby shower diy"]
    groups = search.semantic_duplicates(tags)
    assert groups, "no duplicate group found"
    flat = {t for g in groups for t in g}
    assert {"crochet afghan", "afghan crochet", "crochet blankets"} <= flat
    assert {"hexagon basket", "hexagonal basket"} <= flat
    assert "baby shower diy" not in flat
    problems = search.tag_diversity_problems(tags)
    assert problems and all(p.startswith("TAG_SEMANTIC_DUPLICATE") for p in problems)


def test_chosen_tags_cover_distinct_intents_and_never_repeat_a_meaning():
    queries = search.build_query_set("mosaic_blanket", ["forest", "nordic"], "Christmas",
                                     ["mosaic"], difficulty="intermediate")
    tags = search.choose_tags(queries)
    assert tags, "no tags chosen"
    assert search.semantic_duplicates(tags) == []
    reading = search.intent_coverage(tags, queries)
    assert reading["available"], reading
    assert reading["missing"] == [], reading


# ---- the leading ' / - tag rule on the release chain's drafts (lanes G/I) -------------------

def test_a_tag_starting_with_a_hyphen_or_apostrophe_is_refused_on_the_draft_path():
    problems = seo.check_listing_limits(_copy(tags=["-mosaic blanket", "'twas crochet",
                                                    "fine tag"]))
    leading = [p for p in problems if "TAG_LEADING_PUNCTUATION" in p]
    assert len(leading) == 2, problems
    queries = [search.Query("forest mosaic", 0.5, 0.3)]
    assert "-forest mosaic" not in search.choose_tags(queries, must_include=["-forest mosaic"])


# ---- F-022 front-scan -----------------------------------------------------------------------

def test_the_strongest_differentiator_is_placed_early_on_every_seed_title():
    from brambleloop.radar.opportunity import POOL
    from brambleloop.runtime.release import _motifs_for

    assert POOL
    seasonal = 0
    for seed in POOL:
        motifs = _motifs_for(seed.slug)
        title = seo.build_title(seed.title, seed.category, motifs, seed.season)
        diff = seo.title_differentiator(seed.title, seed.category, motifs, seed.season)
        scan = seo.front_scan(title, differentiator=diff)
        assert scan["ok"], (title, scan["problems"])
        if seed.season and diff == seed.season.split(" (")[0]:
            seasonal += 1
            assert title.index(diff) < title.index("US and UK Terms"), title
    assert seasonal, "no seasonal seed exercised the move"


def test_the_copy_gate_blocks_a_late_differentiator_when_asked():
    late = _copy(title="Market Basket | Crochet Pattern PDF | Written Instructions and Chart "
                       "| US and UK Terms | 3 Sizes")
    gate = seo.check_search_copy(late, front_scan_differentiator="3 Sizes",
                                 check_front_scan=True)
    assert any(p.startswith("TITLE_FRONT_SCAN_DIFFERENTIATOR") for p in gate["blocking"])
    # Not asked: an ad-hoc check of someone else's copy is unchanged.
    assert not any("FRONT_SCAN" in p for p in seo.check_search_copy(late)["blocking"])


# ---- F-028 hero restraint with a measured exception -----------------------------------------

def _memory(db, *, test_key, exposure, outcome="supported", idea="hero_image"):
    from brambleloop.core.models import ListingMemory

    with db.session() as s:
        s.add(ListingMemory(idea=idea, context="home|10_to_15|evergreen|new",
                            outcome=outcome, test_key=test_key, exposure=exposure, note="",
                            on=datetime(2026, 10, 1, tzinfo=timezone.utc)))


def test_an_infographic_hero_is_excepted_only_by_a_remembered_measured_test():
    from brambleloop.publish import hero_exception as H

    problems = ["LISTING_HERO_IS_AN_INFOGRAPHIC: charts belong later",
                "LISTING_HERO_IS_A_CONCEPT: not evidence",
                "LISTING_HERO_FRAME_FLAT: blank"]
    db = _db()
    assert H.measured_exception(db) is None
    assert H.apply(problems, None)["blocking"] == problems
    _memory(db, test_key="hero-text:basket-1", exposure=50)          # under the floor
    _memory(db, test_key="price-test:basket-2", exposure=900)        # not a hero treatment
    _memory(db, test_key="hero-collage:basket-3", exposure=900, outcome="disproved")
    assert H.measured_exception(db) is None
    _memory(db, test_key="hero-text:basket-4", exposure=900)
    exc = H.measured_exception(db)
    assert exc and exc["test_key"] == "hero-text:basket-4"
    split = H.apply(problems, exc)
    assert split["excepted"] == [problems[0]]
    # A concept hero and a flat render are truth/legibility failures; no test excuses them.
    assert split["blocking"] == problems[1:]


# ---- F-030 / F-254 gallery information architecture -----------------------------------------

def test_gallery_jobs_apply_per_category_and_a_worn_view_must_be_real():
    from brambleloop.publish import eligibility as E
    from brambleloop.publish.eligibility import AssetClass

    basket = E.gallery_jobs_for("basket", sizes=3)
    for job in (E.ANGLE, E.CONSTRUCTION, E.LIFESTYLE, E.SIZING, E.DESIRE, E.DETAIL):
        assert job in basket, job
    assert E.FIT not in basket
    assert E.FIT in E.gallery_jobs_for("hat")
    coaster = E.gallery_jobs_for("coaster")
    assert E.COLOUR_CONTEXT in coaster and E.ANGLE not in coaster
    arch = E.gallery_architecture("basket", [E.DESIRE, E.SCALE, E.DETAIL], sizes=3)
    assert arch["complete"] is False
    assert {E.ANGLE, E.CONSTRUCTION, E.SIZING} <= set(arch["missing"])
    render = E.Candidate(asset_id="r", medium=AssetClass.DIGITAL_TWIN_RENDER,
                         purpose=E.ENGINEERING_EVIDENCE, job=E.FIT, position=3)
    assert E.may_serve(render)["may_serve"] is False


# ---- F-058 / F-060 dashboard and supremacy gate -----------------------------------------------

def test_the_dashboard_on_an_empty_shop_is_unknown_not_zero():
    from brambleloop.commerce import search_evidence as se

    out = se.summary(_db())
    for key in ("status", "as_of", "basis", "items", "sources"):
        assert key in out
    assert out["status"] == "UNKNOWN" and out["items"] == []


def test_a_listing_reads_ctr_and_conversion_as_unmeasured_without_periods():
    from brambleloop.commerce import search_evidence as se

    db = _db()
    _profile(db)
    item = se.summary(db)["items"][0]
    assert item["ctr"]["value"] == se.UNMEASURED
    assert item["conversion"]["value"] == se.UNMEASURED
    assert item["visibility_warnings"]["status"] == se.UNMEASURED
    assert item["rungs"]["truthful_query_coverage"]["verdict"] == se.UNMEASURED


def test_paid_traffic_is_blocked_by_search_rungs_when_trust_is_green():
    from brambleloop.commerce import search_evidence as se
    from brambleloop.commerce import trust

    db = _db()
    gate = se.supremacy_gate(db)
    assert gate["cleared"] is False and set(gate["unmeasured"]) == set(se.RUNGS)
    decision = trust.may_scale_ads(db, disclosure_ok=True, claims_ok=True,
                                   thumbnails_coherent=True, support_meets_target=True)
    assert decision["may_scale"] is False
    assert any(b.startswith("search:") for b in decision["blocking"]), decision["blocking"]
    failing = {"cleared": False, "failed": ["no_unresolved_first_party_warning"],
               "unmeasured": []}
    out = trust.may_scale_ads(db, search_gate=failing)
    assert "search:no_unresolved_first_party_warning" in out["blocking"]


# ---- F-242 / F-291 dated, watched search and ads guidance --------------------------------------

def test_search_limits_rest_on_a_dated_watched_reading_that_agrees_with_the_code():
    from brambleloop.commerce import search_policy as sp
    from brambleloop.gates import platform_policy as pp

    assert "search_guidance" in pp.POLICY_SOURCES
    assert "publishing" in pp.POLICY_SOURCES["search_guidance"][1]
    lim = sp.limits()
    assert lim["read_on"] and lim["limits"]
    assert lim["disagreements"] == [], lim
    assert {r["rule"] for r in lim["limits"]} >= {"tag_max_count", "tag_max_chars",
                                                  "title_max_chars", "tag_no_leading_symbol"}


def test_a_material_change_to_search_guidance_invalidates_earlier_certificates():
    from brambleloop.commerce import search_policy as sp
    from brambleloop.gates import platform_policy as pp

    db = _db()
    pp.record_snapshot(db, "search_guidance", text="reading one", checked_on="2026-10-06")
    stamp = sp.stamp(db)
    assert stamp["status"] == "READ"
    assert sp.certificate_problems(db, stamp) == []
    pp.record_snapshot(db, "search_guidance", text="reading one", checked_on="2026-10-07")
    assert sp.certificate_problems(db, stamp) == [], "an unchanged reading invalidated"
    pp.record_snapshot(db, "search_guidance", text="tags now 15", checked_on="2026-10-08")
    problems = sp.certificate_problems(db, stamp)
    assert problems and problems[0].startswith("SEARCH_POLICY_CHANGED")
    assert any(c["source"] == "search_guidance" for c in pp.unreviewed_changes(db))
    assert sp.watch(db)["sources"]["search_guidance"]["unreviewed_change"] is True


def test_onsite_ads_thresholds_are_read_from_the_watched_advertising_reading():
    from brambleloop.commerce import search_policy as sp

    terms = sp.onsite_ads_terms()
    assert terms["min_daily_usd"] == 3.0 and terms["recommended_daily_usd"] == 5.0
    assert terms["per_listing_controls_min_daily_usd"] == 25.0
    assert terms["status"]["controls"].startswith("UNVERIFIED")
    findings = sp.ads_plan_findings(daily_usd=2.2, per_listing_controls=True)
    assert any(f.startswith("ADS_BUDGET_BELOW_LEARNING_FLOOR") for f in findings)
    assert any(f.startswith("ADS_CONTROLS_UNAVAILABLE") for f in findings)
    assert sp.ads_plan_findings(daily_usd=30.0, per_listing_controls=True) == []


# ---- F-251 search language integrity ----------------------------------------------------------

def test_ascii_foreign_words_are_caught_and_bait_translations_refused():
    tags = [f"tag{i} word{i}" for i in range(12)] + ["patron ganchillo"]
    gate = seo.check_search_copy(_copy(tags=tags))
    assert any(p.startswith("LISTING_LANGUAGE") for p in gate["blocking"])
    bait = seo.check_search_copy(_copy(tags=tags),
                                 translation_record="added Spanish for more impressions")
    assert any("impression bait" in p for p in bait["blocking"]), bait["blocking"]
    ok = seo.check_search_copy(_copy(tags=tags), translation_record={
        "language": "es", "reason": "Spanish-language edition of the PDF ships with it"})
    assert not any(p.startswith("LISTING_LANGUAGE") for p in ok["blocking"])
    assert seo.language_findings(["crochet motif pattern", "patron schema"]) == []


# ---- F-255 description conversion architecture --------------------------------------------

class _Material:
    def __init__(self, name, weight=None, fibre=()):
        self.name, self.yarn_weight, self.fibre_content = name, weight, fibre


def test_the_description_leads_with_value_and_carries_yarn_and_fibre():
    why = seo.value_proposition(sizes=3, difficulty="Confident Beginner", colours=1)
    yarn = seo.yarn_lines([_Material("worsted cotton", "worsted")])
    desc = seo.build_description(
        "Hexagon Nesting Baskets", size_label="12 x 10 cm", yardage_lines=["A: about 90 m"],
        tolerance_pct=10, difficulty="Confident Beginner", colors=["cream"],
        terminology="US", gauge_line="16 sts x 18 rows = 10 cm in sc, 5 mm hook",
        stitches=["sc"], key_phrases=["crochet basket"], why_it_matters=why, yarn_lines=yarn)
    expect = {p for p, _ in seo.DESCRIPTION_PARTS}
    assert seo.description_architecture(desc, expect=expect) == []
    assert "3 sizes in one pattern" in desc.splitlines()[0]
    assert any(l.startswith("- Fibre:") and "does not specify" in l for l in desc.splitlines())
    bare = seo.build_description(
        "Hexagon Nesting Baskets", size_label=None, yardage_lines=[], tolerance_pct=10,
        difficulty="Confident Beginner", colors=[], terminology="US", gauge_line=None,
        stitches=[])
    missing = seo.description_architecture(bare, expect={"why_it_matters", "yarn"})
    assert len(missing) == 2 and all(p.startswith("DESCRIPTION_") for p in missing)
    stated = seo.yarn_lines([_Material("cotton linen dk", "dk", (("cotton", 55),
                                                                 ("linen", 45)))])
    assert "Fibre: 55% cotton, 45% linen" in stated


# ---- F-257 price / value coherence ---------------------------------------------------------

class _Ctx:
    def __init__(self, db):
        self.db, self.audits = db, []

    def audit(self, action, **kw):
        self.audits.append((action, kw))


def test_a_requested_sale_reaches_the_listing_only_through_the_promotion_rules():
    from brambleloop.commerce import promotion
    from brambleloop.core.models import Customer, Order
    from brambleloop.runtime.release import _vet_promotion

    db = _db()
    slug = "hexagon-coaster-set"
    forever = {"promo_price_cad": 6.0, "starts": "2026-10-01", "reason": "launch"}
    assert "permanent discount" in promotion.vet_requested(
        db, slug, forever, full_price_cad=8.0)["why"]
    long = dict(forever, ends="2027-01-30")
    assert promotion.vet_requested(db, slug, long, full_price_cad=8.0)["ok"] is False
    short = dict(forever, ends="2026-10-15")
    never = promotion.vet_requested(db, slug, short, full_price_cad=8.0)
    assert never["ok"] is False, "a was-price never charged was accepted"
    ctx = _Ctx(db)
    i = {"promotion": dict(short)}
    _vet_promotion(ctx, i, slug, 8.0)
    assert "promotion" not in i
    assert ctx.audits and ctx.audits[0][0] == "pricing.promotion_refused"
    with db.session() as s:
        c = Customer(customer_ref="k1-buyer")
        s.add(c)
        s.flush()
        s.add(Order(customer_id=c.id, external_ref="k1-order-1", product_slug=slug,
                    price_cad=8.0, revenue_cad=8.0))
    i = {"promotion": dict(short)}
    _vet_promotion(_Ctx(db), i, slug, 8.0)
    assert i["promotion"]["promo_price_cad"] == 6.0 and i["promotion"]["days"] == 14


# ---- the API-key-only seller-taxonomy read (lane G wiring request 2) -------------------------

class _Transport:
    def __init__(self):
        self.requests = []

    def request(self, method, url, *, headers, json=None, form=None, multipart=None,
                timeout=None):
        import fixtures_etsy_taxonomy as FX
        from brambleloop.integrations.etsy import Response

        self.requests.append((method, url, dict(headers)))
        if url.endswith("/seller-taxonomy/nodes"):
            return Response(200, FX.NODES_RESPONSE)
        node = int(url.rstrip("/").split("/")[-2])
        return Response(200, FX.properties_response(node))


def test_the_taxonomy_reads_with_the_app_keystring_alone_and_nothing_else():
    from brambleloop.integrations import etsy_taxonomy as T

    db = _db()
    assert T.gate(db, env={})["open"] is False
    g = T.gate(db, env={"ETSY_KEYSTRING": "k1testkey"})
    assert g["open"] and g["via"] == "api_key_only"
    transport = _Transport()
    saved = (T.api_key_transport_factory, os.environ.get("ETSY_KEYSTRING"))
    T.api_key_transport_factory = lambda: transport
    os.environ["ETSY_KEYSTRING"] = "k1testkey"
    try:
        got = T.refresh(db)
    finally:
        T.api_key_transport_factory = saved[0]
        if saved[1] is None:
            os.environ.pop("ETSY_KEYSTRING", None)
        else:
            os.environ["ETSY_KEYSTRING"] = saved[1]
    assert got["ran"] and got["reading"] == "measured" and got["snapshot_id"], got
    assert transport.requests
    for method, url, headers in transport.requests:
        assert method == "GET" and "/seller-taxonomy/" in url
        assert "Authorization" not in headers and headers["x-api-key"] == "k1testkey"
    client = T.ApiKeyTaxonomyClient(_Transport(), api_key="k1testkey")
    for method, path in (("POST", "/seller-taxonomy/nodes"), ("GET", "/shops/1")):
        try:
            client._call(method, path, operation="x")
        except PermissionError:
            pass
        else:
            raise AssertionError(f"{method} {path} was allowed on the API-key client")


def _run() -> int:
    failures = 0
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    assert tests
    for name, fn in tests:
        try:
            fn()
            print(f"OK   {name}")
        except Exception as exc:  # noqa: BLE001
            import traceback

            failures += 1
            print(f"FAIL {name}: {exc}")
            traceback.print_exc()
    return failures


if __name__ == "__main__":
    raise SystemExit(1 if _run() else 0)
