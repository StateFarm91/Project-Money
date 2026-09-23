"""The named-shop mandate: its registry, its pods, its coverage queue and its refusals.

v1.4.3 requirements 205, 206, 210, 211, 217, 301, 305, 312, 314, 318, 319. The owner's mandate
is unusually emphatic -- one specific shop, not "watch proven sellers" -- and most of the ways
this goes wrong are ways of appearing to satisfy it: a redirect followed to a different
seller, a listing dropped into the nearest pod, a gap closed without a reason, a report that
says "scan complete". Each of those has a test here.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.intel import benchmarks, coverage, mission, pods  # noqa: E402


def _db() -> Database:
    tmp = tempfile.mkdtemp()
    db = Database(f"sqlite:///{tmp}/intel.sqlite")
    db.create_all()
    benchmarks.seed(db)
    return db


# ---- the registry ---------------------------------------------------------


def test_the_owner_supplied_url_survives_verbatim_and_the_shop_is_mandatory():
    """#301 requires the owner's own URL in the registry and in acceptance evidence.

    Tidying it into the short canonical route is the obvious, helpful, wrong thing: the
    acceptance evidence then quotes a URL the owner never supplied, and the one artefact that
    proves the system is watching the shop they named no longer contains what they said.
    """
    from sqlalchemy import select

    from brambleloop.core.models import Benchmark

    db = _db()
    with db.session() as s:
        row = s.scalar(select(Benchmark).where(Benchmark.key == benchmarks.MJS_KEY))

    assert row.mandatory is True
    assert row.shop_name == "MJsOffTheHookDesigns"
    assert row.owner_supplied_url == benchmarks.MJS_OWNER_SUPPLIED_URL
    assert "listing;_id=1825269747" in row.owner_supplied_url
    assert row.canonical_url == "https://www.etsy.com/ca/shop/MJsOffTheHookDesigns"
    assert benchmarks.mandatory() and benchmarks.mandatory()[0].key == benchmarks.MJS_KEY

    # And it is on the dashboard verbatim, which is where acceptance evidence is read from.
    report = mission.mission_report(db, env={})
    assert report["registry"]["owner_supplied_url"] == benchmarks.MJS_OWNER_SUPPLIED_URL


def test_a_redirect_to_a_different_seller_is_refused_not_followed():
    """#206, and the failure it is really about.

    A 404 and a redirect that lands somewhere plausible look identical to a naive follower,
    and the second one silently re-points the entire mission at a stranger. Everything a
    company then learns is about the wrong shop, and nothing in the record says so.
    """
    moved = benchmarks.resolve(
        benchmarks.MJS,
        lambda url: (200, "https://www.etsy.com/shop/MJsOffTheHookDesigns?ref=seller"))
    assert moved.state == benchmarks.MOVED
    assert moved.usable is True

    wrong = benchmarks.resolve(
        benchmarks.MJS, lambda url: (200, "https://www.etsy.com/ca/shop/SomeOtherSeller"))
    assert wrong.state == benchmarks.WRONG_SHOP
    assert wrong.usable is False
    assert "SomeOtherSeller" in wrong.problem

    # A redirect to a search or category page identifies no shop at all, which is the same
    # refusal for the same reason.
    nowhere = benchmarks.resolve(
        benchmarks.MJS, lambda url: (200, "https://www.etsy.com/ca/search?q=crochet"))
    assert nowhere.state == benchmarks.WRONG_SHOP
    assert nowhere.usable is False


def test_health_is_unverified_rather_than_healthy_when_nothing_checked_it():
    """A registry that reports health it never measured is worse than one reporting nothing.

    The mission dashboard is believed. `healthy` by default means the first thing the owner
    reads about a mission that has never run is that it is fine.
    """
    unchecked = benchmarks.resolve(benchmarks.MJS)
    assert unchecked.state == benchmarks.UNVERIFIED
    assert unchecked.usable is False
    assert unchecked.checked_at is None

    def explodes(url: str):
        raise TimeoutError("connection timed out")

    broken = benchmarks.resolve(benchmarks.MJS, explodes)
    assert broken.state == benchmarks.UNREACHABLE
    assert "TimeoutError" in broken.problem

    gone = benchmarks.resolve(benchmarks.MJS, lambda url: (404, url))
    assert gone.state == benchmarks.UNREACHABLE


def test_a_wrong_shop_resolution_never_re_points_the_registry():
    """The recording side of the same rule, which is where it would actually leak."""
    db = _db()
    from sqlalchemy import select

    from brambleloop.core.models import Benchmark

    benchmarks.record_resolution(db, benchmarks.resolve(
        benchmarks.MJS, lambda url: (200, "https://www.etsy.com/ca/shop/Impostor")))
    with db.session() as s:
        row = s.scalar(select(Benchmark).where(Benchmark.key == benchmarks.MJS_KEY))
        assert row.canonical_url == benchmarks.MJS_CANONICAL_URL
        assert row.scan_health["state"] == benchmarks.WRONG_SHOP

    benchmarks.record_resolution(db, benchmarks.resolve(
        benchmarks.MJS, lambda url: (200, "https://www.etsy.com/shop/MJsOffTheHookDesigns")))
    with db.session() as s:
        row = s.scalar(select(Benchmark).where(Benchmark.key == benchmarks.MJS_KEY))
        assert row.canonical_url == "https://www.etsy.com/shop/MJsOffTheHookDesigns"


# ---- pods -----------------------------------------------------------------


def test_every_mandated_pod_exists_and_a_stocking_reaches_the_stocking_specialist():
    """#312 names the pods that must exist permanently, and ordering decides who learns.

    A Christmas stocking matches both "stocking" and "christmas". If the seasonal pod wins,
    the stocking specialist -- the one who knows about heel construction and cuff turn --
    never sees a stocking, and the category rubric never develops.
    """
    required = {"garments", "blankets", "stockings", "ornaments", "home_decor", "bags",
                "hats", "seasonal_gift"}
    assert required <= set(pods.BY_KEY), sorted(required - set(pods.BY_KEY))
    for pod in pods.PODS:
        assert pod.rubric, f"{pod.key} owns no quality rubric"

    assert pods.route("Christmas Stocking Crochet Pattern") == "stockings"
    assert pods.route("Cropped Striped Button Cardigan") == "garments"
    assert pods.route("Chunky Bobble Throw Blanket") == "blankets"
    assert pods.route("Set of 4 Hexagon Coasters") == "home_decor"
    assert pods.route("Market Tote Bag") == "bags"
    assert pods.route("Slouchy Beanie") == "hats"
    assert pods.route("Christmas Tree Ornament Set") == "ornaments"
    assert pods.route("Easter Gift Set") == "seasonal_gift"


def test_a_listing_nobody_can_classify_goes_to_a_visible_queue_not_the_nearest_pod():
    """#207 wants coverage gaps explicit.

    Nudging an unrecognised listing into the closest pod makes the map look complete and
    hides the fact that a whole product family is unmodelled. The dashboard counts these.
    """
    assert pods.route("Whimsical Thingamabob") == pods.UNCLASSIFIED
    assert pods.UNCLASSIFIED in pods.POD_KEYS


def test_a_lesson_that_is_really_a_copied_pattern_is_refused():
    """#217 says store lessons at the mechanism level, and the standing constraint says why.

    An open text field accepts "their row 14 stitch count", and then a competitor's protected
    expression is in this company's database being read by agents that write patterns. The
    check runs at the point of writing, because a later review is one nobody schedules.
    """
    ok = pods.lesson("garments", "silhouette_strength",
                     "cropped boxy shape reads instantly at thumbnail size")
    assert ok.mechanism == "silhouette_strength"

    for bad_note in ("copy the pattern for the yoke",
                     "their chart for the motif, transcribed",
                     "row 1: ch 3, dc in each stitch across"):
        try:
            pods.lesson("garments", "fit_strategy", bad_note)
        except pods.MechanismRefused:
            pass
        else:
            raise AssertionError(f"stored a copied instruction: {bad_note!r}")

    for bad_mechanism in ("stitch_instructions", "their_pattern", "anything_i_like"):
        try:
            pods.lesson("garments", bad_mechanism, "a genuinely useful observation here")
        except pods.MechanismRefused:
            pass
        else:
            raise AssertionError(f"accepted {bad_mechanism!r} as a mechanism")


def test_a_dimension_with_no_evidence_is_unknown_and_never_parity():
    """The most comfortable wrong answer available.

    Defaulting an unmeasured dimension to parity means a company that has never looked at its
    benchmark reports itself level with it -- which reads as 'nothing to do' on exactly the
    dimensions nobody has examined.
    """
    d = pods.Director()
    assert d.position("photography_coverage", None, None) == pods.UNKNOWN
    assert d.position("photography_coverage", 6.0, None) == pods.UNKNOWN
    assert d.position("photography_coverage", None, 9.0) == pods.UNKNOWN

    assert d.position("photography_coverage", 9.0, 6.0) == pods.AHEAD
    assert d.position("photography_coverage", 6.0, 9.0) == pods.BEHIND
    assert d.position("photography_coverage", 6.0, 6.0) == pods.PARITY

    standing = d.standing({"catalogue_breadth": 19.0}, {})
    assert standing["catalogue_breadth"] == pods.UNKNOWN
    assert set(standing) == set(pods.DIMENSIONS)


def test_the_director_deduplicates_identical_content_and_finds_cross_category_mechanisms():
    """#211 and #212: two pods can be handed the same listing, and compute is not free."""
    d = pods.Director()
    payload = {"listing": "1825269747", "title": "Cropped Cardigan", "price": 8.5}
    assert d.is_duplicate(payload) is False
    assert d.is_duplicate(dict(payload)) is True
    assert d.is_duplicate({**payload, "price": 9.5}) is False

    lessons = [
        pods.lesson("garments", "seasonal_timing", "holiday colourways posted in September"),
        pods.lesson("stockings", "seasonal_timing", "stockings listed before the tree decor"),
        pods.lesson("blankets", "thumbnail_clarity", "single colour block reads at 170px"),
    ]
    cross = pods.Director.cross_category(lessons)
    assert cross and cross[0]["mechanism"] == "seasonal_timing"
    assert cross[0]["pods"] == ["garments", "stockings"]
    assert all(c["mechanism"] != "thumbnail_clarity" for c in cross)


# ---- the coverage gap queue ----------------------------------------------


def test_a_gap_cannot_leave_the_queue_without_saying_why():
    """#314 lists 'not pursuing + reason' as a state, and the reason is the whole point.

    A queue whose items can be closed silently shrinks by forgetting and then reports good
    coverage. This is the only exit that needs an argument, so it is the only one guarded.
    """
    db = _db()
    gap = coverage.upsert(db, benchmark_key=benchmarks.MJS_KEY, arena="christmas stocking",
                          pod="stockings", components={"apparent_demand": 0.9})

    try:
        coverage.advance(db, gap, coverage.NOT_PURSUING)
    except coverage.GapRefused as e:
        assert "reason" in str(e)
    else:
        raise AssertionError("a gap was closed with no reason")

    assert coverage.advance(db, gap, coverage.NOT_PURSUING,
                            reason="personalised names need embroidery we do not do") \
        == coverage.NOT_PURSUING


def test_the_lifecycle_refuses_a_state_it_did_not_pass_through():
    """The states are the record of what was done. Skipping one makes the record fiction."""
    db = _db()
    gap = coverage.upsert(db, benchmark_key=benchmarks.MJS_KEY, arena="cropped cardigan",
                          pod="garments", components={"apparent_demand": 0.8})

    for straight_to in (coverage.LAUNCHED, coverage.CERTIFIED, coverage.VALIDATED_WINNER):
        try:
            coverage.advance(db, gap, straight_to)
        except coverage.GapRefused:
            pass
        else:
            raise AssertionError(f"jumped straight to {straight_to}")

    for step in (coverage.CONCEPTING, coverage.ENGINEERING, coverage.CERTIFIED,
                 coverage.LAUNCHED, coverage.VALIDATED_WINNER):
        assert coverage.advance(db, gap, step) == step


def test_a_score_says_how_much_of_itself_is_evidence():
    """An unknown component is left out, not filled with a midpoint.

    A midpoint is an opinion wearing a number's clothes, and once it is in the table it is
    indistinguishable from a measurement. So a confident-looking 0.8 computed from one
    component out of seven has to be visibly that.
    """
    thin = coverage.score({"apparent_demand": 0.8})
    assert thin.value == 0.8
    assert thin.evidence_weight == coverage.WEIGHTS["apparent_demand"]
    assert len(thin.missing) == len(coverage.COMPONENTS) - 1

    full = coverage.score({k: 0.5 for k in coverage.COMPONENTS})
    assert full.value == 0.5
    assert full.evidence_weight == 1.0
    assert full.missing == ()

    for bad in ({"apparent_demand": 1.4}, {"not_a_component": 0.5}):
        try:
            coverage.score(bad)
        except coverage.GapRefused:
            pass
        else:
            raise AssertionError(f"accepted {bad}")


def test_re_scoring_a_gap_does_not_reset_the_work_done_on_it():
    """Evidence changing is not the same event as work happening.

    Conflating them drops a half-engineered product back to uncovered every time the
    benchmark posts something, which is both wrong and demoralising to watch.
    """
    db = _db()
    gap = coverage.upsert(db, benchmark_key=benchmarks.MJS_KEY, arena="throw blanket",
                          pod="blankets", components={"apparent_demand": 0.5})
    coverage.advance(db, gap, coverage.CONCEPTING)
    coverage.advance(db, gap, coverage.ENGINEERING)

    again = coverage.upsert(db, benchmark_key=benchmarks.MJS_KEY, arena="throw blanket",
                            pod="blankets", components={"apparent_demand": 0.9})
    assert again == gap
    row = [g for g in coverage.queue(db) if g["id"] == gap][0]
    assert row["state"] == coverage.ENGINEERING
    assert row["score"] == 0.9

    # The summary counts certified products, never intentions.
    s = coverage.summary(db, benchmarks.MJS_KEY)
    assert s["answered_with_a_certified_product"] == 0
    assert s["by_state"][coverage.ENGINEERING] == 1


# ---- evidence and the report ---------------------------------------------


def test_a_report_that_says_only_scan_complete_is_refused():
    """#319, quoting the failure it expects almost verbatim.

    Autonomous systems report job status instead of findings because job status is what the
    job knows. So the report is validated the way a release is.
    """
    try:
        mission.check_report({"benchmark": "MJsOffTheHookDesigns",
                              "summary": "competitor scan complete"})
    except mission.ReportRefused as e:
        assert "must name" in str(e)
    else:
        raise AssertionError("a bare status line passed as a mission report")

    complete = {
        "benchmark": "MJsOffTheHookDesigns",
        "observed_at": "2026-09-18T14:00:00Z",
        "catalogue_coverage": {"listings_known": 120, "listings_inspected": 12},
        "changes": [{"listing_ref": "1825269747", "what": "new gallery image"}],
        "listings_inspected": ["1825269747"],
        "images_inspected": 9,
        "pods_notified": ["garments"],
        "actions": ["opened a coverage gap for cropped cardigan"],
    }
    mission.check_report(complete)

    # A report about somebody else is not this mandate, however thorough it is.
    try:
        mission.check_report({**complete, "benchmark": "SomeOtherProvenSeller"})
    except mission.ReportRefused as e:
        assert "one specific shop" in str(e)
    else:
        raise AssertionError("a report about a different shop satisfied the MJs mandate")


def test_evidence_recorded_without_the_capability_cannot_satisfy_the_mandate():
    """The join between #224 and this mission.

    Recording is the only way into the observations table precisely so that the grade is
    decided by whether the capability existed, not by what the caller named the evidence.
    """
    db = _db()
    got = mission.record(db, benchmark_key=benchmarks.MJS_KEY, kind="browser_traversal",
                         detail={"listings": 3}, pods_notified=("garments",), env={})
    assert got.satisfies_mandate is False
    assert got.grade == "supporting"

    granted = mission.record(db, benchmark_key=benchmarks.MJS_KEY,
                             kind="gallery_image_observation", detail={"images": 9},
                             pods_notified=("garments",), env={"ETSY_API_KEY": "k", "ETSY_SHARED_SECRET": "s"})
    assert granted.satisfies_mandate is True

    # Evidence routed to a pod that does not exist is a routing bug, not a silent no-op.
    try:
        mission.record(db, benchmark_key=benchmarks.MJS_KEY, kind="search_snippet",
                       detail={}, pods_notified=("imaginary_pod",), env={})
    except mission.ReportRefused:
        pass
    else:
        raise AssertionError("evidence was routed to a pod that does not exist")


def test_the_dashboard_leads_with_whether_the_mission_can_see_anything():
    """#318, and the ordering is the point.

    A dashboard whose top line is coverage, computed from an empty table, reads as a healthy
    mission with nothing in it. This one says the mission is blocked, and says why.
    """
    db = _db()
    report = mission.mission_report(db, env={})

    assert report["capability_available"] is False
    assert report["observation_state"].startswith("blocked")
    assert "No mandated observation has been performed" in report["honest_statement"]
    assert report["catalogue_coverage"]["listings_known"] == 0
    assert report["last_mandated_evidence_at"] is None
    assert len(report["pods"]) == len(pods.PODS)
    assert "MJsOffTheHookDesigns" in report["mandate"]
    assert report["gap_queue"]["total"] == 0


def test_a_competitor_photograph_can_never_be_published_as_brambleloop_creative():
    """#305, enforced where the origin is actually stated.

    By the time an image is in a gallery it looks like any other image, so the rule lives at
    provenance. 'We would never do that' is not a control.
    """
    from brambleloop.cir.compiler import compile_cir
    from brambleloop.cir.twin import build_twin
    from brambleloop.gates.asset_truth import Asset, AssetClass, Provenance, check_asset
    from tests import fixtures

    cir = fixtures.good_mosaic_panel()
    twin = build_twin(cir, compile_cir(cir))

    stolen = Asset(
        asset_id="hero", asset_class=AssetClass.PHYSICAL_PRODUCT_PHOTO,
        provenance=Provenance(source="camera", created_by="publishing",
                              notes="downloaded from the benchmark listing and recoloured"))
    codes = {f.code for f in check_asset(stolen, cir, twin)}
    assert "ASSET_COMPETITOR_SOURCE" in codes

    unknown_origin = Asset(
        asset_id="hero2", asset_class=AssetClass.PHYSICAL_PRODUCT_PHOTO,
        provenance=Provenance(source="benchmark", created_by="publishing"))
    codes = {f.code for f in check_asset(unknown_origin, cir, twin)}
    assert "ASSET_SOURCE_UNRECOGNISED" in codes

    ours = Asset(asset_id="hero3", asset_class=AssetClass.INFOGRAPHIC,
                 provenance=Provenance(source="twin", created_by="publishing",
                                       notes="rendered from the certified CIR"))
    codes = {f.code for f in check_asset(ours, cir, twin)}
    assert "ASSET_COMPETITOR_SOURCE" not in codes
    assert "ASSET_SOURCE_UNRECOGNISED" not in codes


# ---- the scan -------------------------------------------------------------


class _Reader:
    """A benchmark catalogue under test control.

    Counts the calls, because the whole point of fingerprinting is that an unchanged
    catalogue costs nothing: a test that only checked the rows would pass while the scan
    re-read every gallery every six hours.
    """

    def __init__(self, listings, images=None, shop_name="MJsOffTheHookDesigns"):
        self.listings = listings
        self._images = images if images is not None else [
            {"rank": 1, "hex_code": "1F3A2E", "hue": 150, "saturation": 30,
             "brightness": 22, "is_black_and_white": False,
             "url_fullxfull": "https://i.etsystatic.com/x_fullxfull.jpg"},
            {"rank": 2, "hex_code": "C9A227", "hue": 45, "saturation": 70,
             "brightness": 79, "is_black_and_white": False,
             "url_fullxfull": "https://i.etsystatic.com/y_fullxfull.jpg"},
        ]
        self.shop_name = shop_name
        self.image_calls = 0
        self.catalogue_calls = 0

    def resolve_shop(self, name):
        return {"shop_id": 4242, "shop_name": self.shop_name}

    def catalogue(self, shop_id, **kwargs):
        self.catalogue_calls += 1
        return list(self.listings)

    def images(self, listing_ref):
        self.image_calls += 1
        return list(self._images)

    def videos(self, listing_ref):
        # Video presence is one of #2's three weakness signals. A reader that cannot answer
        # is not the same as a listing with no video, so this double answers "none" rather
        # than being absent -- an absent method would make the scanner raise, which is the
        # right behaviour for a real reader that lost the capability.
        self.video_calls = getattr(self, "video_calls", 0) + 1
        return list(getattr(self, "_videos", []))


def _listing(listing_id, title, price=8.5, favourites=120, modified=1000, **extra):
    return {"listing_id": listing_id, "title": title,
            "price": {"amount": int(price * 100), "divisor": 100, "currency_code": "CAD"},
            "tags": ["crochet pattern", "cardigan"], "materials": ["yarn"],
            "state": "active", "last_modified_timestamp": modified,
            "num_favorers": favourites, "taxonomy_id": 66,
            "url": f"https://www.etsy.com/listing/{listing_id}", **extra}


def test_a_first_scan_is_a_baseline_and_the_second_pays_for_nothing():
    """#207 then #212, in that order and for a reason.

    A full catalogue re-read every six hours is the expensive way to learn nothing. The
    fingerprint makes an unchanged listing free, so the second scan must open no galleries at
    all — and asserting on the call count is the only way to see that, because the rows look
    identical either way.
    """
    from brambleloop.intel import observe

    db = _db()
    reader = _Reader([_listing(1, "Cropped Striped Cardigan"),
                      _listing(2, "Chunky Throw Blanket"),
                      _listing(3, "Christmas Stocking")])

    first = observe.scan(db, reader, env={})
    assert first.baseline is True
    assert first.listings_known == 3
    assert sorted(first.new_listings) == ["1", "2", "3"]
    assert len(first.deep_audited) == 3
    assert reader.image_calls == 3
    assert first.images_inspected == 6

    reader.image_calls = 0
    second = observe.scan(db, reader, env={})
    assert second.baseline is False
    assert second.unchanged == 3
    assert second.new_listings == [] and second.changed_listings == []
    assert reader.image_calls == 0, "an unchanged catalogue re-opened galleries"


def test_a_changed_listing_is_re_audited_and_an_untouched_one_is_not():
    """Change detection has to be selective or it is just a slower full scan."""
    from brambleloop.intel import observe

    db = _db()
    listings = [_listing(1, "Cropped Striped Cardigan"),
                _listing(2, "Chunky Throw Blanket")]
    reader = _Reader(listings)
    observe.scan(db, reader, env={})

    # One price move, one new listing, one untouched.
    reader.listings = [_listing(1, "Cropped Striped Cardigan", price=9.5, modified=2000),
                       _listing(2, "Chunky Throw Blanket"),
                       _listing(3, "Nordic Star Ornament Set")]
    reader.image_calls = 0
    third = observe.scan(db, reader, env={})

    assert third.changed_listings == ["1"]
    assert third.new_listings == ["3"]
    assert third.unchanged == 1
    assert sorted(third.deep_audited) == ["1", "3"]
    assert reader.image_calls == 2


def test_the_gallery_audit_keeps_etsys_colour_statistics_and_calls_it_an_inventory():
    """The honest name for what the API can give without a vision model.

    Etsy publishes per-image hex, hue, saturation and brightness, which answers palette
    questions outright. It does not answer whether the shot is any good — so the record says
    `gallery_audited` and stores the palette, and nothing in it claims a judgement was made.
    """
    from sqlalchemy import select

    from brambleloop.core.models import BenchmarkListing
    from brambleloop.intel import observe

    db = _db()
    observe.scan(db, _Reader([_listing(1, "Cropped Striped Cardigan")]), env={})

    with db.session() as s:
        row = s.scalar(select(BenchmarkListing))
    assert row.audit_state == "audited"
    assert row.media_count == 2
    assert row.detail["gallery_audited"] is True
    assert row.detail["palette"][0]["hex"] == "1F3A2E"
    assert row.detail["image_urls"][0].startswith("https://i.etsystatic.com/")
    assert row.pod == "garments"


def test_a_scan_records_evidence_that_cannot_close_the_mandate_without_the_capability():
    """The join between the scan and #224.

    An API read is a mandated evidence kind. It only satisfies the mandate when the
    credential that produced it actually exists, and `mission.record` is the only way in.
    """
    from sqlalchemy import select

    from brambleloop.core.models import BenchmarkObservation
    from brambleloop.intel import observe

    db = _db()
    observe.scan(db, _Reader([_listing(1, "Cropped Striped Cardigan")]), env={})
    with db.session() as s:
        blocked = list(s.scalars(select(BenchmarkObservation)))
    assert blocked[-1].kind == "official_api_read"
    assert blocked[-1].satisfies_mandate is False

    db2 = _db()
    observe.scan(db2, _Reader([_listing(1, "Cropped Striped Cardigan")]),
                 env={"ETSY_API_KEY": "k", "ETSY_SHARED_SECRET": "s"})
    with db2.session() as s:
        granted = list(s.scalars(select(BenchmarkObservation)))
    assert granted[-1].satisfies_mandate is True


def test_a_scan_report_would_survive_the_no_generic_substitution_check():
    """#319 is the output contract, so the scan is written against it rather than beside it."""
    from brambleloop.intel import observe

    db = _db()
    result = observe.scan(db, _Reader([_listing(1, "Cropped Striped Cardigan"),
                                       _listing(2, "Christmas Stocking")]), env={})
    report = result.to_report()

    mission.check_report(report)  # raises if it is a status line wearing a report's name
    assert report["benchmark"] == "MJsOffTheHookDesigns"
    assert report["catalogue_coverage"]["listings_known"] == 2
    assert report["images_inspected"] == 4
    assert set(report["pods_notified"]) == {"garments", "stockings"}
    assert report["actions"] and report["actions"] != []


def test_an_arena_the_benchmark_sells_and_we_do_not_becomes_queued_work():
    """#314: the scan's purpose is not a report, it is a queue.

    An observation that produces no candidate work is a newsletter.
    """
    from brambleloop.intel import observe
    from brambleloop.core.models import Product

    db = _db()
    with db.session() as s:
        s.add(Product(slug="chunky-throw-blanket", title="Throw", status="certified"))

    result = observe.scan(db, _Reader([
        _listing(1, "Cropped Striped Cardigan", favourites=900),
        _listing(2, "Chunky Throw Blanket", favourites=800),
        _listing(3, "Christmas Stocking", favourites=400),
    ]), env={})

    # We already sell a blanket, so no gap for blankets. We sell no garment and no stocking.
    assert "Blankets and throws" not in result.gaps_opened
    assert "Garments and clothing" in result.gaps_opened
    assert "Christmas stockings" in result.gaps_opened

    queue = coverage.queue(db, benchmarks.MJS_KEY)
    assert queue and all(g["state"] == coverage.UNCOVERED for g in queue)
    top = queue[0]
    # Scored only on observable evidence, and the score says how little of itself is evidence.
    assert set(top["components"]["components"]) == {"apparent_demand", "portfolio_fit"}
    assert top["components"]["evidence_weight"] < 0.4


def test_a_scan_with_no_credential_explains_itself_instead_of_pretending():
    """#224 again, at the one place it is most tempting to fudge.

    The easy implementation returns an empty result and lets the dashboard read zero
    listings, which is indistinguishable from a shop that has none. This says no observation
    was performed, names the requirements that stay unmet, and states that nothing was
    substituted.
    """
    from brambleloop.intel import observe

    db = _db()
    outcome = observe.scan_or_explain(db, env={})

    assert outcome["ran"] is False
    assert outcome["substituted"] is False
    assert 207 in outcome["requirements_unmet"]
    assert "ETSY_API_KEY" in outcome["reason"]
    assert "nothing was approximated" in outcome["note"]


# ---- resilience, reconciliation, cadence, vision --------------------------


class _Flaky:
    """A transport that throttles, then faults, then answers."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = 0

    def request(self, method, url, *, headers, body=None, timeout=20.0):
        from dataclasses import dataclass

        @dataclass
        class R:
            status: int
            body: dict
            headers: dict

        self.calls += 1
        status, payload, hdrs = self.script[min(self.calls - 1, len(self.script) - 1)]
        return R(status, payload, hdrs)


def test_a_rate_limit_is_waited_out_and_a_bad_request_is_not_retried():
    """Ignoring Retry-After is how a client turns a throttle into a ban.

    And a ban on the one shop the owner named by name is the worst outcome available to this
    mission. The mirror case matters as much: a 404 retried four times is four identical
    requests, which is exactly the behaviour that gets a key noticed.
    """
    from brambleloop.intel import etsy_public as ep

    waits = []
    transport = _Flaky([
        (429, {}, {"Retry-After": "7"}),
        (500, {}, {}),
        (200, {"results": [{"listing_id": 1}]}, {}),
    ])
    reader = ep.PublicReader(transport, env={ep.KEYSTRING_VAR: "k", ep.SECRET_VAR: "s"},
                             sleep=waits.append)
    body = reader.get("ping")

    assert body["results"][0]["listing_id"] == 1
    assert transport.calls == 3
    assert waits[0] == 7.0, "the server's own Retry-After was ignored"
    assert reader.throttled == 1

    # A permanent error is our mistake; repeating it cannot fix it.
    bad = _Flaky([(404, {}, {})])
    reader = ep.PublicReader(bad, env={ep.KEYSTRING_VAR: "k", ep.SECRET_VAR: "s"},
                             sleep=waits.append)
    try:
        reader.get("ping")
    except ep.ReadFailed as e:
        assert "404" in str(e)
    else:
        raise AssertionError("a 404 was treated as retryable")
    assert bad.calls == 1

    # And a transport that never recovers stops rather than knocking forever.
    forever = _Flaky([(429, {}, {"Retry-After": "1"})])
    reader = ep.PublicReader(forever, env={ep.KEYSTRING_VAR: "k", ep.SECRET_VAR: "s"},
                             max_attempts=3, sleep=lambda _s: None)
    try:
        reader.get("ping")
    except ep.ReadFailed as e:
        assert "kept refusing" in str(e)
    else:
        raise AssertionError("an endless throttle was not given up on")
    assert forever.calls == 3


def test_a_listing_that_vanishes_is_marked_withdrawn_rather_than_deleted():
    """A disappearance is a commercial event, and a deleted row says nothing at all.

    "We saw this listing for six weeks and then it stopped" is a finding. An absent row is
    indistinguishable from a listing that never existed.
    """
    from sqlalchemy import select

    from brambleloop.core.models import BenchmarkListing
    from brambleloop.intel import observe

    db = _db()
    reader = _Reader([_listing(1, "Cropped Striped Cardigan"),
                      _listing(2, "Christmas Stocking")])
    observe.scan(db, reader, env={})

    reader.listings = [_listing(1, "Cropped Striped Cardigan")]
    second = observe.scan(db, reader, env={})

    assert second.withdrawn == ["2"]
    with db.session() as s:
        gone = s.scalar(select(BenchmarkListing).where(
            BenchmarkListing.listing_ref == "2"))
    assert gone is not None, "the row was deleted, destroying the longitudinal evidence"
    assert gone.audit_state == "withdrawn"
    assert gone.detail["withdrawn_first_noticed"]

    # Reported as a change, so the scan's own report carries it (#319).
    assert {"listing_ref": "2", "what": "no longer listed"} in second.to_report()["changes"]

    # And it is only announced once: the third scan does not re-report it.
    third = observe.scan(db, reader, env={})
    assert third.withdrawn == []


def test_the_cadence_speeds_up_faster_than_it_slows_down():
    """#213, and the asymmetry is the design.

    Too slow during a release run means missing the event the mission exists to catch. Too
    fast during a quiet week costs a few calls against a catalogue the fingerprint already
    makes nearly free. Those are not symmetric risks, so the response is not symmetric.
    """
    from datetime import date

    from brambleloop.intel import cadence

    quiet_period = date(2026, 6, 1)   # no event inside the planning window

    busy = cadence.decide(changes_last_window=4, today=quiet_period)
    assert busy.interval_seconds < cadence.INTERVALS_SECONDS[cadence.DEFAULT_INDEX]
    assert "releasing" in busy.reason

    steady = cadence.decide(consecutive_quiet_scans=1, today=quiet_period)
    assert steady.index == cadence.DEFAULT_INDEX

    quiet = cadence.decide(consecutive_quiet_scans=5, today=quiet_period)
    assert quiet.interval_seconds > cadence.INTERVALS_SECONDS[cadence.DEFAULT_INDEX]

    # It moves one step at a time: a cadence that oscillates is its own problem.
    assert abs(busy.index - cadence.DEFAULT_INDEX) == 1
    assert abs(quiet.index - cadence.DEFAULT_INDEX) == 1

    # A near event pulls a backed-off cadence forward, and stops it backing off further.
    christmas_near = date(2026, 12, 1)
    assert cadence.seasonal_pressure(christmas_near) is True
    held = cadence.decide(current_index=4, consecutive_quiet_scans=9, today=christmas_near)
    assert held.index < 4
    assert held.seasonal_pressure is True


def test_the_cadence_reads_its_history_from_recorded_scans():
    """Held in the audit log rather than in memory, so a restart does not reset it."""
    from brambleloop.intel import cadence, observe

    db = _db()
    reader = _Reader([_listing(1, "Cropped Striped Cardigan")])
    observe.scan(db, reader, env={})          # baseline: one change
    observe.scan(db, reader, env={})          # quiet
    observe.scan(db, reader, env={})          # quiet

    state = cadence.observed_state(db, benchmarks.MJS_KEY)
    assert state["scans_in_window"] == 3
    assert state["consecutive_quiet_scans"] == 2
    assert state["changes_last_window"] == 1

    decision = cadence.next_interval(db, benchmarks.MJS_KEY)
    assert decision.interval_seconds in cadence.INTERVALS_SECONDS


def test_an_image_observation_cannot_be_recorded_without_looking_at_the_image():
    """The backlog is real work waiting, not a gap being papered over.

    The tempting implementation writes plausible observations from the listing title. This
    refuses, because an observation nobody made is the silent downgrade #224 exists to stop.
    """
    from brambleloop.intel import observe, vision

    db = _db()
    observe.scan(db, _Reader([_listing(1, "Cropped Striped Cardigan")]), env={})

    queued = vision.pending(db, benchmarks.MJS_KEY)
    assert queued, "an audited gallery produced no analysis work"
    assert queued[0].key.endswith(":1")
    assert queued[0].image_url.startswith("https://i.etsystatic.com/")

    report = vision.plan(db, benchmarks.MJS_KEY, env={})
    assert report["state"] == vision.BLOCKED
    assert report["pending_images"] == len(queued)
    assert report["estimated_cad_total"] > 0
    assert "none has been guessed" in report["note"]

    try:
        vision.record(db, queued[0], {"shot_type": "hero_styled"}, env={})
    except vision.AnalysisRefused as e:
        assert "not produced by looking" in str(e)
    else:
        raise AssertionError("an observation was recorded with nothing to look with")

    # With the capability, the vocabulary is still closed.
    granted = {"ANTHROPIC_API_KEY": "k"}
    for bad in ({"vibes": "great"}, {"shot_type": "artsy"}, {}):
        try:
            vision.record(db, queued[0], bad, env=granted)
        except vision.AnalysisRefused:
            pass
        else:
            raise AssertionError(f"accepted {bad}")

    ok = vision.record(db, queued[0],
                       {"shot_type": "hero_styled", "thumbnail_readability": "strong",
                        "scale_communication": "hand for scale in frame three"},
                       env=granted)
    assert ok > 0


def test_the_acceptance_test_walks_every_step_the_mandate_names():
    """#222 and #320, end to end against a fixture.

    The point is not that a fixture proves the mandate met -- it explicitly does not, and the
    evidence records that. The point is that tomorrow's first real scan is an integration
    verification rather than the first time this path has ever run.
    """
    from sqlalchemy import select

    from brambleloop.core.models import BenchmarkListing, BenchmarkObservation
    from brambleloop.intel import observe, vision

    db = _db()
    reader = _Reader([
        _listing(1, "Cropped Striped Cardigan", favourites=900),
        _listing(2, "Christmas Stocking Personalised", favourites=500),
        _listing(3, "Chunky Throw Blanket", favourites=300),
    ])

    # 1. resolve the named shop  2. enumerate  3. open listings  4. traverse galleries
    first = observe.scan(db, reader, env={})
    assert first.listings_known == 3
    assert len(first.deep_audited) == 3
    assert first.images_inspected == 6

    # 5. capture listing text and commerce metadata
    with db.session() as s:
        row = s.scalar(select(BenchmarkListing).where(
            BenchmarkListing.listing_ref == "1"))
    assert row.price_cad == 8.5 and row.detail["num_favorers"] == 900

    # 6. produce image-level observations -> queued, and honestly blocked
    assert vision.plan(db, benchmarks.MJS_KEY, env={})["state"] == vision.BLOCKED

    # 7. classify into specialist pods
    assert {"garments", "stockings", "blankets"} <= first.pods_notified

    # 8. persist evidence  9. detect a change  10. trigger a re-audit
    reader.listings[0] = _listing(1, "Cropped Striped Cardigan", price=11.0, modified=9999)
    reader.image_calls = 0
    second = observe.scan(db, reader, env={})
    assert second.changed_listings == ["1"]
    assert reader.image_calls == 1, "a changed listing did not trigger a re-audit"

    # 11. record the action in the coverage matrix
    assert coverage.queue(db, benchmarks.MJS_KEY)

    # And the evidence says what it is: a fixture, not the mandate met.
    with db.session() as s:
        observations = list(s.scalars(select(BenchmarkObservation)))
    assert observations and all(o.satisfies_mandate is False for o in observations), \
        "a fixture run was recorded as satisfying the observation mandate"



def test_a_judged_image_is_never_offered_again():
    """The defect that was spending about CA$8.50 a day to learn nothing.

    `gallery_analysed` was read in `pending` and written nowhere, so every two-hourly run
    took the same twenty-five images off the same newest listings, judged them, paid for
    them and left them pending. Eight hours and four paid batches moved the backlog from
    475 to 476. It looked like progress from outside, because `judged: 25` is exactly what
    a draining queue reports too.
    """
    from brambleloop.core.db import Database
    from brambleloop.core.models import BenchmarkListing
    from brambleloop.intel import benchmarks, vision

    db = Database("sqlite://")
    db.create_all()
    with db.session() as s:
        s.add(BenchmarkListing(
            benchmark_key=benchmarks.MJS_KEY, listing_ref="1", title="t",
            audit_state="audited", detail={"image_urls": ["a.jpg", "b.jpg"]}))

    assert [p.rank for p in vision.pending(db, benchmarks.MJS_KEY)] == [1, 2]
    vision._mark_judged(db, vision.PendingAnalysis(benchmarks.MJS_KEY, "1", "a.jpg", 1))
    assert [p.rank for p in vision.pending(db, benchmarks.MJS_KEY)] == [2], \
        "a judged image came back around to be paid for again"


def test_a_listing_is_analysed_only_when_every_image_of_it_has_been():
    """Per image rather than per listing, because a batch limit lands mid-gallery.

    Marking whole listings would re-offer every image of a gallery whose last image
    failed, and would abandon the rest of one the batch limit cut short.
    """
    from brambleloop.core.db import Database
    from brambleloop.core.models import BenchmarkListing
    from brambleloop.intel import benchmarks, vision

    db = Database("sqlite://")
    db.create_all()
    with db.session() as s:
        s.add(BenchmarkListing(
            benchmark_key=benchmarks.MJS_KEY, listing_ref="1", title="t",
            audit_state="audited", detail={"image_urls": ["a.jpg", "b.jpg"]}))

    vision._mark_judged(db, vision.PendingAnalysis(benchmarks.MJS_KEY, "1", "a.jpg", 1))
    with db.session() as s:
        assert not (s.query(BenchmarkListing).first().detail or {}).get("gallery_analysed")

    vision._mark_judged(db, vision.PendingAnalysis(benchmarks.MJS_KEY, "1", "b.jpg", 2))
    with db.session() as s:
        assert (s.query(BenchmarkListing).first().detail or {})["gallery_analysed"] is True
    assert vision.pending(db, benchmarks.MJS_KEY) == []


def test_the_remaining_count_is_counted_rather_than_computed_to_fall():
    """A backlog that stood still reported as one that was draining.

    `remaining` read the real backlog and then subtracted this run's `judged` from it, so
    the number fell by twenty-five every time whether or not anything had been recorded.
    That is a progress figure computed to look like progress, and it is what made a
    stalled queue legible as a healthy one -- including in a report to the owner.
    """
    import ast
    from pathlib import Path as _Path

    source = (_Path(__file__).resolve().parents[1]
              / "src/brambleloop/intel/vision.py").read_text()
    tree = ast.parse(source)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "analyse")
    for node in ast.walk(fn):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Sub):
            names = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
            assert "judged" not in names, \
                "the remaining count is subtracting this run's judged again"


def _one_listing(images=("a.jpg", "b.jpg")):
    from brambleloop.core.db import Database
    from brambleloop.core.models import BenchmarkListing
    from brambleloop.intel import benchmarks

    db = Database("sqlite://")
    db.create_all()
    with db.session() as s:
        s.add(BenchmarkListing(
            benchmark_key=benchmarks.MJS_KEY, listing_ref="1", title="t",
            audit_state="audited", detail={"image_urls": list(images)}))
    return db


def test_the_backlog_is_counted_rather_than_capped_by_the_query_limit():
    """The replacement for one unmeasurable number must not be another.

    B-647 replaced a `remaining` that subtracted its own run's work with one that read
    `len(pending(..., limit=limit * 20))` -- which saturates at five hundred. With 438
    listings carrying several images each the true backlog is thousands, so the figure
    read 500 whether the queue drained or not, and would have hidden whether the fix
    worked for weeks. Counted over the whole catalogue now, and not through `pending`.
    """
    import ast
    from pathlib import Path as _Path

    from brambleloop.intel import benchmarks, vision

    db = _one_listing(tuple(f"{i}.jpg" for i in range(30)))
    assert vision.pending_count(db, benchmarks.MJS_KEY)["unjudged"] == 30
    assert len(vision.pending(db, benchmarks.MJS_KEY, limit=5)) == 5, "pending still pages"

    source = (_Path(__file__).resolve().parents[1]
              / "src/brambleloop/intel/vision.py").read_text()
    fn = next(n for n in ast.walk(ast.parse(source))
              if isinstance(n, ast.FunctionDef) and n.name == "analyse")
    for node in ast.walk(fn):
        if isinstance(node, ast.keyword) and node.arg == "remaining":
            raise AssertionError("remaining is being computed inline again")


def test_an_image_that_keeps_failing_is_not_retried_for_ever():
    """Every live batch since the drain began carried `failures: 1`.

    A failing image is never marked judged, so it came back on every run, taking a slot
    and a little money with it indefinitely. Bounded, then named as given up on -- an
    image the provider refuses four times is not one more attempt away.
    """
    from brambleloop.intel import benchmarks, vision

    db = _one_listing()
    failing = vision.PendingAnalysis(benchmarks.MJS_KEY, "1", "a.jpg", 1)
    for _ in range(vision.FAILED_ATTEMPTS):
        vision._mark_failed(db, failing)

    assert [p.rank for p in vision.pending(db, benchmarks.MJS_KEY)] == [2]
    count = vision.pending_count(db, benchmarks.MJS_KEY)
    assert count["given_up_on"] == 1
    assert count["unjudged"] == 1, "a given-up image is not outstanding work"


def test_an_image_nobody_will_retry_does_not_hold_a_gallery_open():
    """Otherwise one refused image keeps its whole listing pending for ever."""
    from brambleloop.core.models import BenchmarkListing
    from brambleloop.intel import benchmarks, vision

    db = _one_listing()
    for _ in range(vision.FAILED_ATTEMPTS):
        vision._mark_failed(db, vision.PendingAnalysis(benchmarks.MJS_KEY, "1", "a.jpg", 1))
    vision._mark_judged(db, vision.PendingAnalysis(benchmarks.MJS_KEY, "1", "b.jpg", 2))

    with db.session() as s:
        assert (s.query(BenchmarkListing).first().detail or {})["gallery_analysed"] is True
    assert vision.pending_count(db, benchmarks.MJS_KEY)["unjudged"] == 0


def test_vision_coverage_is_counted_rather_than_asserted_absent():
    """The report that says whether the gallery spend buys anything could not move.

    `gaps()` reported the vision columns as `absent_on: len(observed), share: 1.0` -- a
    constant asserting total absence however many galleries had been judged and paid for.
    On 2026-09-23 it still read "absent on all 438" while a listing in the table carried
    twenty recorded observations from a single run. Paid evidence existed and the coverage
    report said we knew nothing: stale state presented as current, and the reason nobody
    could tell whether the drain was working.

    It named the wrong blocker too -- `capability: browser/vision` -- when the vision
    capability is open and the analysis cadence had been running for days.
    """
    from brambleloop.core.db import Database
    from brambleloop.core.models import BenchmarkListing, BenchmarkObservation
    from brambleloop.intel import benchmarks, market_map, vision

    db = Database("sqlite://")
    db.create_all()
    with db.session() as s:
        for i in range(3):
            s.add(BenchmarkListing(
                benchmark_key=benchmarks.MJS_KEY, listing_ref=str(i),
                title="Crochet Blanket Pattern", product_type="6343", detail={}))
        for _ in range(vision.MIN_IMAGES_FOR_ATTRIBUTES):
            s.add(BenchmarkObservation(
                benchmark_key=benchmarks.MJS_KEY, listing_ref="0",
                kind="gallery_image_observation", grade="mandated",
                satisfies_mandate=True,
                detail={"observation": {"shot_type": "hero_styled",
                                        "composition": "centred"}}))

    attributes = market_map.gaps(db)["attributes"]
    for key in market_map.VISION_ATTRIBUTES:
        entry = attributes[key]
        assert entry["absent_on"] == 2, (key, entry)
        assert entry["share"] < 1.0, "a measured column reported total absence"
        assert "browser/vision" not in entry["capability"], \
            "the coverage report still names a capability that is already open"


def test_a_listing_below_the_image_floor_still_counts_as_absent():
    """One image is one photographer's decision about one frame. Two is the floor, and a
    coverage number that counted a single judged image would overstate what the map knows."""
    from brambleloop.core.db import Database
    from brambleloop.core.models import BenchmarkListing, BenchmarkObservation
    from brambleloop.intel import benchmarks, market_map

    db = Database("sqlite://")
    db.create_all()
    with db.session() as s:
        s.add(BenchmarkListing(benchmark_key=benchmarks.MJS_KEY, listing_ref="0",
                               title="Crochet Blanket Pattern", product_type="6343",
                               detail={}))
        s.add(BenchmarkObservation(
            benchmark_key=benchmarks.MJS_KEY, listing_ref="0",
            kind="gallery_image_observation", grade="mandated", satisfies_mandate=True,
            detail={"observation": {"shot_type": "hero_styled"}}))

    attributes = market_map.gaps(db)["attributes"]
    assert attributes["silhouette"]["absent_on"] == 1

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
