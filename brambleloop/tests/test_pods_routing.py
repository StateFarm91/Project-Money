"""What a benchmark router gets wrong, and how both kinds of error hide.

The first full observation of the MJs catalogue routed 58 of 438 listings to `unclassified`.
Reading the 58 titles showed three separate defects, and only one of them was the obvious one.

  1. **Substring matching, in both directions.** "slippers" did not match "Crochet Slipper
     Boot Pattern" and "mittens" did not match "Cable Mitten Pattern" -- two listings a human
     routes without thinking. And in the other direction "vest" is inside "harvest", "hat" is
     inside "what", "top" is inside "tree topper". The missed listing is visible in the
     unclassified count; the wrongly-routed one is invisible forever, because a wrong pod
     looks exactly like a right one from outside.

  2. **A vocabulary too narrow for the catalogue it watches.** Dishcloths, amigurumi and
     multi-pattern ebooks are three real departments this shop sells and no pod owned.

  3. **Stored routing never updated.** The scanner routes on discovery and skips unchanged
     listings, so widening the vocabulary reaches only listings the shop later edits.

The third is the one that would have made the other two fixes look like they worked while
changing nothing, so it gets the most tests.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import BenchmarkListing  # noqa: E402
from brambleloop.intel import benchmarks, market_map, observe, pods  # noqa: E402


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/pods.sqlite")
    db.create_all()
    return db


# ---- matching on words rather than substrings -----------------------------


def test_a_singular_title_reaches_the_pod_whose_keyword_is_plural():
    """Both of these were observed in the live catalogue and both went unclassified."""
    assert pods.route("Crochet Slipper Boot Pattern with Soles") == "hats"
    assert pods.route("Winter Wonder Cable Mitten Pattern") == "hats"


def test_a_substring_is_not_a_match_because_a_wrong_pod_is_invisible():
    """`vest` in `harvest` routes a fall decor listing to the garment specialist, silently."""
    assert pods.route("Rustic Harvest Table Decor") != "garments"
    assert pods.route("What To Crochet This Winter") != "hats"
    assert pods.route("Christmas Tree Topper Pattern") != "garments"


def test_the_words_it_should_match_still_match():
    """A stricter rule that also stops matching the true positives is not stricter, it is broken."""
    assert pods.route("Chunky Cable Vest Pattern") == "garments"
    assert pods.route("Slouchy Beanie Hat") == "hats"
    assert pods.route("Crochet Tote Bag") == "bags"
    assert pods.route("Granny Square Blanket") == "blankets"


# ---- the departments the live catalogue showed -----------------------------


def test_kitchen_textiles_reach_a_specialist_of_their_own():
    """Thirteen observed listings, and "home decor" answers for none of them usefully."""
    for title in ("The Honey Weave Dishcloth Pattern, Easy Textured Cotton Washcloth",
                  "Seaside Dish Scrubby Crochet Pattern, Reusable Scrubbies",
                  "The Winterberry Mug Cozy, Crochet Mug Cozy Pattern",
                  "Star Stitch Towel Holder Pattern"):
        assert pods.route(title) == "kitchen_bath", title


def test_soft_sculpture_is_one_department_however_the_title_dresses_it_up():
    """A pumpkin, a gnome and a snowman are made and graded the same way a fox plush is."""
    for title in ("Jumbo Amigurumi Snowman, 3 sizes, Winter Decor",
                  "Rustic Farmhouse Crochet Gnome Pattern",
                  "Chunky Herringbone Pumpkins, Crochet Pumpkin Stack",
                  "Crochet Pattern / Baby Owl Lovey"):
        assert pods.route(title) == "amigurumi", title


def test_a_multi_pattern_ebook_is_a_bundle_before_it_is_a_garment():
    """Routing it to the product its title mentions first hides the mechanism being used."""
    assert pods.route("CROCHET PATTERN EBOOK/ Falling For Suzette Collection, Fall & "
                      "Winter Crochet Accessories and Garments") == "collections"
    assert pods.route("Salt + Sol Crochet Pattern Ebook | 9 Summer Garment & Accessory "
                      "Patterns | XS to 5X") == "collections"


def test_a_title_that_counts_its_own_patterns_is_a_bundle_even_with_no_ebook_word():
    """"Mountainscapes Collection, 6 Granny Stitch Patterns" names no product and no format."""
    assert pods.route("Mountainscapes Collection, 6 Granny Stitch Patterns") == "collections"
    assert pods.counts_its_own_patterns("10 Pattern Ebook")
    # A count of something else is not a count of patterns.
    assert not pods.counts_its_own_patterns("Jumbo Amigurumi Snowman, 3 sizes")


def test_a_guidebook_is_education_rather_than_the_ebook_it_is_delivered_as():
    """Both observed guidebooks carry the word "Ebook", and neither contains a pattern."""
    assert pods.route("The Understanding Gauge Guidebook: Mastering Crochet Stitch "
                      "Consistency / PDF Digital Download Ebook") == "education"


def test_a_listing_naming_no_product_stays_unclassified():
    """Two of the 58 genuinely cannot be routed from the title, and guessing is the worse answer."""
    assert pods.route("CROCHET PATTERN / Dusty Rose Baby Set") == pods.UNCLASSIFIED


def test_every_benchmark_category_has_a_pod_that_answers_for_it():
    assert set(benchmarks.MJS_CATEGORIES) <= set(pods.POD_KEYS)


# ---- a motif is not a form -------------------------------------------------


def test_a_form_word_beats_a_motif_word_wherever_both_appear():
    """The fault the first version of this fix introduced, caught by production drift.

    Adding "pumpkin" to the soft-sculpture pod sent a cardigan and a cushion to the
    specialist in stuffing firmness -- the same invisible misrouting the substring fix was
    written to stop, reintroduced by the fix itself.
    """
    assert pods.route("Hello Pumpkin Mosaic Cardigan, inset crochet cardigan") == "garments"
    assert pods.route("PUMPKIN PILLOW CROCHET Pattern / Hello Harvest Pumpkin Pillow") \
        == "home_decor"
    assert pods.route("Hello Harvest Chunky Throw Blanket") == "blankets"
    assert pods.route("Harvest Twist Ear Warmer, crochet headband pattern") == "hats"


def test_a_motif_word_used_as_a_colour_does_not_decide_the_pod():
    """"Plush and Blush Crop Top ... easy crochet sweater" is a sweater, observed live."""
    assert pods.route("Plush and Blush Crop Top, sizes Xs-5X, easy crochet sweater") \
        == "garments"


def test_a_motif_still_decides_when_nothing_says_what_the_object_is():
    """The motif pass is the fallback, not a dead letter."""
    assert pods.route("Chunky Harvest Pumpkins, Easy Crochet Pumpkin Pattern") == "amigurumi"
    assert pods.route("Country Harvest Crochet Pumpkin Stack in 6 sizes") == "amigurumi"


def test_a_season_says_when_a_product_sells_not_what_it_is():
    """True before by pod ordering alone; now true by construction."""
    assert pods.route("Crochet Christmas Stocking, Personalised") == "stockings"
    assert pods.route("Christmas Blanket Crochet Pattern") == "blankets"
    assert pods.route("Festive Crochet Decor Bundle") == "seasonal_gift"


# ---- the three faults production found after the first two fixes ------------


def test_an_html_escaped_possessive_is_not_a_count_of_thirty_nine_patterns():
    """Etsy returns titles escaped, and "Men&#39;s" tokenised to a bare 39.

    Seventeen cardigans and four blankets moved to the bundle pod on that alone, and the
    120-character display truncation is why it took a second look to see it.
    """
    assert pods.route("Cobblestone Men&#39;s Cardigan, Cardigan Pattern, Sizes Xs-5X") \
        == "garments"
    assert pods.route("Mj&#39;s Signature Blanket Pattern, Afghan pattern") == "blankets"
    assert not pods.counts_its_own_patterns("Children&#39;s Crochet Cardigan Pattern")


def test_a_number_in_front_of_a_unit_counts_the_unit():
    """"3 sizes, Pdf pattern" and "2 Piece Sweater Pattern" are not bundles."""
    assert not pods.counts_its_own_patterns("Textured Blanket, 3 sizes, Pdf pattern")
    assert not pods.counts_its_own_patterns("Snowy Season Sweater, 2 Piece Sweater Pattern")
    assert pods.counts_its_own_patterns("Hooded Crochet Blanket 10 PATTERN Bundle")
    assert pods.counts_its_own_patterns("Mountainscapes Collection, 6 Granny Stitch Patterns")


def test_a_plural_stem_never_costs_a_pod_its_own_keyword():
    """An "es" rule that made "boxes" into "box" made "purses" into "purs"."""
    assert pods._singular("sizes") == "size"
    assert pods.route("Crochet Purses and Bags Pattern") == "bags"


def test_a_title_naming_two_products_is_routed_by_the_one_it_names_first():
    """"Beach Bag Pattern and Hair Tie" is a bag; "Ear Warmer / Head wrap" is a headband."""
    assert pods.route("Salt + Sand Beach Bag Pattern and Hair Tie, Crochet Bag, Purse") \
        == "bags"
    assert pods.route("Pumpkin Spice Ear Warmer & Keychain / Head wrap / Headband") == "hats"
    assert pods.route("The Winterberry Wine Bottle Cozy, Crochet Bottle Cozy, Wine Gift Bag") \
        == "kitchen_bath"
    assert pods.route("Crochet Baby Koala Lovey / Crochet Toy / Security Blanket") \
        == "amigurumi"


def test_a_guidebook_sold_as_an_ebook_is_still_education():
    """Position settles it: the title says what it is before it says how it ships."""
    assert pods.route("The Perfect Fit Guidebook: Unlocking Pattern Sizing and Body "
                      "Measurements / PDF Digital Download Ebook") == "education"


# ---- modifiers, stitches and characters ------------------------------------


def test_a_modifier_in_front_of_the_head_noun_does_not_take_the_listing():
    """"Blanket Scarf" is a scarf. Both terms start in the same place; the longer one wins."""
    assert pods.route("Fall For You Blanket Scarf, Easy Scarf Crochet Pattern") == "hats"
    assert pods.route("Unicorn blanket and Cowl - Crochet Pattern") == "blankets"


def test_a_stitch_name_is_not_a_product():
    """"Seabreeze Basket Weave Blanket" reached the bag specialist. A basket weave is a stitch."""
    assert pods.route("Seabreeze Basket Weave Blanket, Crochet Throw Blanket Pattern") \
        == "blankets"


def test_a_character_name_is_not_the_thing_it_is_named_after():
    """"Adult Sock Monkey Set, crochet cardigan" reached the hat specialist, via "sock"."""
    assert pods.route("Adult Sock Monkey Set, crochet cardigan, easy crochet cardigan") \
        == "garments"
    # And the word still works when it means the garment.
    assert pods.route("Crochet Sock Pattern, Cozy Wool Socks") == "hats"


def test_a_number_behind_a_unit_counts_the_unit_too():
    """"0-6months to child size 12, Pdf pattern" read as a set of twelve patterns."""
    assert not pods.counts_its_own_patterns("Hoodie Pattern, 0-6months to child size 12, "
                                            "Pdf pattern")
    assert pods.counts_its_own_patterns("Collection Ebook | 7 Crochet Patterns")


# ---- reclassification ------------------------------------------------------


def _store(db, rows):
    with db.session() as s:
        for ref, title, pod in rows:
            s.add(BenchmarkListing(benchmark_key=benchmarks.MJS_KEY, listing_ref=ref,
                                   title=title, pod=pod))


def test_a_widened_vocabulary_reaches_listings_already_in_the_table():
    """The defect that would make every other fix here look like it worked and change nothing."""
    db = _db()
    _store(db, [("1", "Crochet Slipper Boot Pattern", pods.UNCLASSIFIED)])
    assert observe.reclassify(db)["moved"] == 1
    with db.session() as s:
        assert s.query(BenchmarkListing).one().pod == "hats"


def test_a_dry_run_reports_the_move_and_writes_nothing():
    """A vocabulary change should be inspectable before it rewrites the benchmark's map."""
    db = _db()
    _store(db, [("1", "Crochet Slipper Boot Pattern", pods.UNCLASSIFIED)])
    report = observe.reclassify(db, dry_run=True)
    assert report["moved"] == 1 and report["dry_run"]
    with db.session() as s:
        assert s.query(BenchmarkListing).one().pod == pods.UNCLASSIFIED


def test_reclassifying_twice_moves_nothing_the_second_time():
    db = _db()
    _store(db, [("1", "Crochet Slipper Boot Pattern", pods.UNCLASSIFIED),
                ("2", "Granny Square Blanket", "blankets")])
    assert observe.reclassify(db)["moved"] == 1
    assert observe.reclassify(db)["moved"] == 0


def test_the_gap_report_shows_stored_routing_that_the_vocabulary_has_outgrown():
    """Drift is reported before anybody asks, because nobody would think to ask."""
    db = _db()
    _store(db, [("1", "Crochet Slipper Boot Pattern", pods.UNCLASSIFIED)])
    drift = market_map.gaps(db)["stored_routing_drift"]
    assert drift["listings"] == 1
    assert drift["moves"][0]["from"] == pods.UNCLASSIFIED
    assert drift["moves"][0]["to"] == "hats"


def test_a_scan_that_reads_nothing_new_still_keeps_the_catalogue_on_the_vocabulary():
    """The scan short-circuits on an unchanged fingerprint; reclassification must not."""
    db = _db()
    _store(db, [("1", "The Honey Weave Dishcloth Pattern", "home_decor")])
    assert observe.reclassify(db)["by_move"] == {"home_decor -> kitchen_bath": 1}


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
