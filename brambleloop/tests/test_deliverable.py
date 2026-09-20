"""#2's last weakness: whether a competitor's listing says what a buyer will receive.

These tests are mostly about the two directions this measurement can lie in. It can
manufacture a competitor weakness out of our own unread backlog, and it can keep a
competitor's copy while claiming to keep only facts. Both are checked here directly.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import BenchmarkListing  # noqa: E402
from brambleloop.intel import benchmarks  # noqa: E402
from brambleloop.intel import deliverable as D  # noqa: E402
from brambleloop.radar import arbitrage  # noqa: E402

CLEAR = ("PDF crochet pattern, instant download. 14 pages of written instructions with "
         "stitch charts and step-by-step photos. Written in US terms. Finished size approx "
         "40 x 60 inches. Worsted weight yarn, 1200 yards. 5.0mm crochet hook.")
SILENT = "A lovely cosy throw to brighten any room. Make it in your favourite colours!"


def _db() -> Database:
    tmp = tempfile.mkdtemp()
    db = Database(f"sqlite:///{tmp}/deliverable.sqlite")
    db.create_all()
    return db


def _listing(ref: str, description: str | None, **detail):
    row = {"benchmark_key": benchmarks.MJS_KEY, "listing_ref": ref, "title": "t", "pod": "blankets",
           "media_count": 6}
    facts = D.read({"description": description, "is_digital": True})
    row["detail"] = {**detail, **({"deliverable": facts} if facts else {})}
    return BenchmarkListing(**row)


def test_a_listing_that_says_everything_and_one_that_says_nothing_are_told_apart():
    clear = D.read({"description": CLEAR, "is_digital": True})
    silent = D.read({"description": SILENT, "is_digital": True})
    assert clear["clarity"] == 1.0, clear
    assert silent["clarity"] == 0.0, silent
    assert D.unclear(clear) is False
    assert D.unclear(silent) is True


def test_an_unread_description_is_unknown_and_never_counted_as_a_weakness():
    """The failure this module is arranged against: our backlog wearing their weakness.

    Video learned this the expensive way -- counting unaudited galleries as "no video" would
    have reported 94% of a competitor's catalogue as missing something nobody had looked for.
    """
    assert D.read({"is_digital": True}) is None
    assert D.read({"description": "   ", "is_digital": True}) is None
    assert D.unclear(None) is None

    summary = D.summarise([None, None, None])
    assert summary["measurable"] is False
    assert "not the same as" in summary["reason"]

    mixed = D.summarise([None, D.read({"description": SILENT, "is_digital": True})])
    assert mixed["read"] == 1, mixed
    assert mixed["unclear"] == 1
    assert mixed["unclear_share"] == 1.0


def test_the_seller_s_words_are_read_and_not_kept():
    """A competitor's description is their copy. What is kept is which facts it states.

    The same rule the review reader follows: a complaint theme is a fact about a category and
    a review is somebody's words. Here the stored structure is walked in full and checked for
    any fragment of the source text.
    """
    facts = D.read({"description": CLEAR, "is_digital": True})
    blob = repr(facts).lower()
    for phrase in ("lovely", "cosy throw", "brighten any room", "14 pages", "1200 yards",
                   "5.0mm", "40 x 60"):
        assert phrase not in blob, f"stored facts contain the listing's own text: {phrase}"
    assert set(facts["stated"]) <= set(D.FACTS)
    assert all(isinstance(v, bool) for v in facts["stated"].values())


def test_a_physical_item_is_not_unclear_for_failing_to_say_pdf():
    """Etsy's own structured type answers this, so it is read rather than inferred."""
    physical = D.read({"description": "Hand crocheted blanket, finished size 40 x 60 inches. "
                                      "Worsted weight yarn.",
                       "is_digital": False, "listing_type": "physical"})
    assert physical["digital"] is False
    for fact in D.DIGITAL_ONLY:
        assert fact not in physical["applicable"], fact
    # And it is not punished for the facts that do not apply to it.
    assert physical["clarity"] > D.UNCLEAR_BELOW, physical


def test_the_hunt_reports_silence_per_fact_so_the_gap_is_actionable():
    """"Unclear" is not a finding. *Which* question the listing leaves unanswered is."""
    db = _db()
    with db.session() as s:
        s.add(_listing("1", CLEAR))
        s.add(_listing("2", SILENT))
        s.add(_listing("3", "PDF pattern, worsted weight yarn."))
        s.add(_listing("4", None))

    hunt = arbitrage.weakness_hunt(db)
    clarity = hunt["deliverable"]
    assert clarity["measurable"] is True
    assert clarity["read"] == 3, clarity
    assert clarity["unclear"] == 2, clarity
    # Every listing read is silent on terms except the clear one, and that is the kind of
    # statement a merchandiser can act on.
    assert clarity["silent_on"]["terms"] == 2, clarity["silent_on"]
    assert clarity["silent_on"]["format"] == 1, clarity["silent_on"]
    assert set(hunt["deliverable"]["refs"]) == {"2", "3"}


def test_a_new_reading_reaches_the_listings_that_did_not_change():
    """The gallery backlog's lesson, applied before it could repeat.

    A reading attached only to the new-or-changed branch describes the shop's recent edits
    and nothing else -- 25 of 438 listings, with no path to the rest. The description arrives
    with the catalogue page, so unchanged rows are filled on the next scan for no extra
    request, and the whole map closes at once.
    """
    from brambleloop.intel import observe
    from test_intel import _Reader, _listing as _payload

    db = _db()
    rows = [_payload(1, "Chunky Throw Crochet Pattern", description=SILENT),
            _payload(2, "Ribbed Beanie Crochet Pattern", description=CLEAR)]
    reader = _Reader(rows)

    # A first scan under the old behaviour: the rows exist with no description reading.
    first = observe.scan(db, reader, env={})
    assert len(first.new_listings) == 2
    with db.session() as s:
        for row in s.scalars(__import__("sqlalchemy").select(BenchmarkListing)):
            row.detail = {k: v for k, v in (row.detail or {}).items() if k != "deliverable"}

    # Nothing about the catalogue changed, so every listing takes the unchanged path.
    second = observe.scan(db, reader, env={})
    assert second.unchanged == 2, second.unchanged
    assert not second.changed_listings
    assert len(second.deliverable_backfilled) == 2, second.deliverable_backfilled
    assert second.to_report()["catalogue_coverage"][
        "descriptions_read_for_the_first_time"] == 2

    hunt = arbitrage.weakness_hunt(db)
    assert hunt["deliverable"]["read"] == 2, hunt["deliverable"]

    # And it is not paid for twice: a third quiet scan has nothing left to fill.
    third = observe.scan(db, reader, env={})
    assert third.deliverable_backfilled == []


def test_the_hunt_still_refuses_to_report_an_empty_catalogue_as_no_weaknesses():
    """The pre-existing rule, re-checked because a new signal is the easiest place to lose it."""
    hunt = arbitrage.weakness_hunt(_db())
    assert hunt["measurable"] is False
    assert "opposite of what is true" in hunt["reason"]


def test_a_size_range_is_only_asked_of_departments_that_have_one():
    """A blanket has dimensions, not sizes. Counting it as one size invents a weakness."""
    from brambleloop.intel import deliverable as d

    assert d.size_range({"description": "Finished size 40 x 60 inches."},
                        pod="blankets") is None
    graded = d.size_range({"description": "Sizes XS, S, M, L, XL, 2XL, 3XL."}, pod="garments")
    assert graded == {"sizes": 7, "stated": True, "limited": False}
    narrow = d.size_range({"description": "Written for size S and M."}, pod="hats")
    assert narrow["limited"] is True
    one = d.size_range({"description": "One size fits most."}, pod="garments")
    assert one == {"sizes": 1, "stated": True, "limited": True}


def test_a_size_letter_is_read_from_a_size_clause_and_not_from_the_whole_listing():
    """`s`, `m` and `l` are among the commonest characters in a pattern listing.

    "1200 m" of yarn and a "large hook" are not a size range, and a matcher that read them as
    one would report well-graded patterns as one-size about as often as it got it right --
    manufacturing exactly the weakness it was written to find.
    """
    from brambleloop.intel import deliverable as d

    noise = d.size_range(
        {"description": "Worsted weight yarn, 1200 m. Use a large hook. Colourway L."},
        pod="garments")
    assert noise == {"sizes": 0, "stated": False, "limited": None}, noise
    # And silence about size is reported as silence, not as one size.
    assert noise["stated"] is False
    assert noise["limited"] is None


def test_a_bundle_is_read_from_the_incumbent_s_own_title():
    db = _db()
    with db.session() as s:
        s.add(_listing("1", CLEAR))
        s.add(_listing("2", CLEAR))
        row = _listing("3", CLEAR)
        row.title = "Christmas Ornament Set - 6 Crochet Patterns"
        s.add(row)
    hunt = arbitrage.weakness_hunt(db)
    assert hunt["bundles"]["bundled"] == 1, hunt["bundles"]
    assert hunt["bundles"]["share"] == round(1 / 3, 3)


def test_every_weakness_the_requirement_names_is_measured_or_named_as_needing_vision():
    """#2 names eight. A list quietly shortened to what is measurable is how a requirement
    gets reported as met.

    Five are read from first-party observation today. Two -- branding coherence and whether
    the styling looks like this year -- are judgements about rendered pages and photographs,
    and stay in the vocabulary as vision-gated rather than being dropped. The eighth,
    "confusing instructions", is what deliverable clarity measures the visible half of: what
    is inside the PDF cannot be known without buying it, which is the benchmark_purchases
    gate, and the listing's own silence about its contents is the part that can.
    """
    db = _db()
    with db.session() as s:
        s.add(_listing("1", CLEAR, gallery_audited=True, has_video=True))
    hunt = arbitrage.weakness_hunt(db)

    measured = {
        "thin_media": "thin_media_share" in hunt,
        "no_video": hunt["video"]["measurable"] or bool(hunt["video"]["reason"]),
        "unclear_deliverable": (hunt["deliverable"]["measurable"]
                                or bool(hunt["deliverable"].get("reason"))),
        "complaints": (hunt["complaints"]["measurable"]
                       or bool(hunt["complaints"].get("reason"))),
        "limited_sizes": (hunt["sizes"]["measurable"] or bool(hunt["sizes"]["reason"])),
        "no_bundle": hunt["bundles"]["measurable"],
    }
    assert set(measured) == set(arbitrage.WEAKNESS_SIGNALS), measured
    assert all(measured.values()), measured

    # The two that cannot be read from text are still named, with what they would need.
    assert set(hunt["needs_vision"]) == {"weak_branding", "stale_aesthetics"}
    assert not set(hunt["needs_vision"]) & set(arbitrage.WEAKNESS_SIGNALS)


# ---- the scorer, actually fed ---------------------------------------------


def _catalogue(db, pod: str, n: int, *, price: float, favourites: int,
               description: str, title: str):
    with db.session() as s:
        for i in range(n):
            row = _listing(f"{pod}-{i}", description)
            row.pod = pod
            row.title = title
            row.price_cad = price
            row.detail = {**(row.detail or {}), "num_favorers": favourites}
            s.add(row)


def test_the_scorer_was_a_pure_function_nobody_fed():
    """#2's scoring half, run rather than available.

    score_market() is correct arithmetic that had never produced a number about this
    business. A scorer nobody calls is the same defect as a credential nobody has used: the
    capability is present and has never once been exercised.
    """
    db = _db()
    _catalogue(db, "blankets", 8, price=9.0, favourites=400, description=SILENT,
               title="Chunky Throw Crochet Pattern")
    _catalogue(db, "garments", 6, price=12.0, favourites=120, description=CLEAR,
               title="Ribbed Cardigan Crochet Pattern")

    out = arbitrage.score_observed(db)
    assert out["measurable"] is True, out
    assert {c["market"] for c in out["scored"]} == {"blankets", "garments"}
    for card in out["scored"]:
        assert card["score"] is not None, card
        assert set(card["measured"]) <= set(arbitrage.OBSERVED_DIMENSIONS), card["measured"]
        # The five that observation cannot fill stay named and empty rather than defaulted.
        assert set(card["unmeasured"]) >= {"listing_density", "support_burden",
                                           "expected_contribution"}, card["unmeasured"]

    # Scored from one source, so every department carries the same confidence and the
    # ranking is allowed rather than refused.
    confidences = {c["confidence"] for c in out["scored"]}
    assert len(confidences) == 1, confidences
    assert out["ranking_refused"] == "", out["ranking_refused"]
    assert out["ranking"]["ranked"], out["ranking"]

    # The department whose incumbents say nothing about what arrives is the better opening.
    opening = {c["market"]: c["observed"]["opportunity"] for c in out["scored"]}
    assert opening["blankets"] > opening["garments"], opening


def test_a_department_nobody_has_observed_enough_of_is_not_scored():
    """Two listings' medians are two sellers' decisions, not a department."""
    db = _db()
    _catalogue(db, "bags", 2, price=7.0, favourites=50, description=CLEAR, title="Tote Bag")
    out = arbitrage.score_observed(db)
    assert out["measurable"] is False, out
    assert out["departments_too_thin_to_score"] == ["bags"]
    assert out["scored"] == []


def test_an_unreadable_weakness_leaves_the_opening_rather_than_entering_it_as_zero():
    """A signal nobody could read is not a strong incumbent.

    Averaging an unmeasurable signal in as zero weakness makes every department look better
    defended the less we know about it, which inverts the whole point of the hunt.
    """
    hunt = {"listings": 10, "thin_media_share": 0.8,
            "deliverable": {"measurable": False},
            "video": {"measurable": False, "share": None},
            "sizes": {"measurable": False, "stated": 0},
            "bundles": {"measurable": True, "share": 0.0}}
    assert arbitrage._opportunity(hunt) == round((0.8 + 1.0) / 2, 4)
    assert arbitrage._opportunity({}) is None


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
