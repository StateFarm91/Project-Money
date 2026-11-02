"""A2 (P0-NAME-OBJECT): one shared, fail-closed name/object contract across every
construction route (OPUS2T-1/-2/-3, OPUS2U-1, OPUS2V-1, OPUS2V-2).

After routing, whatever branch chose the family, the title's head noun (read after trailing
filler) must be an object that family makes; a feature phrase is refused; the basket and tote
routes admit only allowlisted modifiers, plus motif and colourwork words, which the
publish-time name_truth judges (motif_promise is now part of it for every product the
catalogue does not engineer). The radar seeds route exactly as before.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_opus2_a2_name_object.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import itertools
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from brambleloop.creative import fallback_constructions as F  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402

CATEGORIES = ("basket", "blanket", "home_decor", "accessory", "pet", "seasonal_decor",
              "scarf", "runner", "pillow", "wedding", "shawl", "bag", "placemat")

# Every repro OPUS2T, OPUS2U and OPUS2V drafted under a name the construction does not make.
REPROS = ("Teddy Bear", "Teddy Bear Pattern", "Teddy Bear Crochet Pattern",
          "Crochet Teddy Bear Pattern", "Teddy Bear (Cream)", "Teddy Bear for Beginners",
          "Teddy Bear in Cream", "Teddy Bear - Easy", "Teddy Bear v2", "Bear Cub", "Bunny",
          "Drawstring Pouch Pattern", "Sleepy Fox", "Little Elephant", "Cat", "Owl", "Unicorn",
          "Puppy", "Kitten", "Dinosaur", "Octopus", "Teddies", "Bear Lovey", "Cowl", "Slippers",
          "Poncho", "Shrug", "Pencil Case", "Phone Case", "Wallet", "Cat Cave", "Dog Collar",
          "Lidded Basket", "Basket with Handles", "Giant Basket", "Sunflower Tote",
          "Coaster Pack", "Ornament Pack", "Scrunchie Pack", "Dishcloth Pack", "Tote Pack",
          "Poly Pack", "Blanket with Fringe", "Tote Bag with Zip Pocket and Lining",
          # a feature phrase before a valid head, and text no rule reads
          "Blanket and Throw", "Throw & Blanket", "Everyday Blanket \U0001f9fa",
          "\u041a\u043e\u0440\u0437\u0438\u043d\u0430 Blanket")

LEGITIMATE = (("basket", "Crochet Storage Basket", F.VESSEL),
              ("basket", "Nordic Forest Mosaic Storage Basket", F.VESSEL),
              ("basket", "Market Basket", F.VESSEL), ("basket", "Bread Basket", F.VESSEL),
              ("basket", "Storage Basket Pattern", F.VESSEL),
              ("basket", "Basket (Large) - Easy", F.VESSEL),
              ("basket", "Storage Basket - Cream Edition", F.VESSEL),
              ("basket", "Diamond Tapestry Basket", F.TAPESTRY),
              ("bag", "Everyday Market Tote", F.TOTE), ("bag", "Small Tote", F.TOTE),
              ("bag", "Tote Bag", F.TOTE), ("bag", "Drawstring Pouch", F.POUCH),
              ("blanket", "Polar Bear Blanket", F.FLAT_PANEL),
              ("blanket", "Bear Paw Blanket", F.FLAT_PANEL),
              ("blanket", "Basket Weave Blanket", F.FLAT_PANEL),
              ("blanket", "Everyday Throw for Beginners", F.FLAT_PANEL),
              ("blanket", "Winter Village Graphghan", F.FLAT_PANEL),
              ("placemat", "Mosaic Placemat Pair", F.FLAT_PANEL),
              ("pillow", "Bear Pillow", F.PANEL_PAIR),
              ("wedding", "Wedding Ring Cushion", F.PANEL_PAIR),
              ("shawl", "Everyday Triangle Shawl", F.TRIANGLE),
              ("seasonal_decor", "Easter Egg Cosy Set", F.COSY),
              ("pet", "Cat Bed", F.VESSEL),
              ("stocking", "Classic Christmas Stocking", F.STOCKING))


def test_every_review_repro_is_refused_in_every_category():
    assert len(REPROS) == 48 and CATEGORIES
    drafted = [(c, t, F.plan(category=c, title=t)["family"])
               for t in REPROS for c in CATEGORIES
               if F.plan(category=c, title=t)["family"] != F.REFUSED]
    assert drafted == [], drafted


def test_legitimate_titles_still_draft():
    assert len(LEGITIMATE) == 24
    for category, title, family in LEGITIMATE:
        got = F.plan(category=category, title=title)
        assert got["family"] == family, (category, title, got)


def test_a_generated_head_x_modifier_x_category_grid():
    """Every family head with a plain modifier drafts in that family's category; every head
    with an unmeasured modifier, a feature phrase or a foreign head is refused."""
    category_of = {F.VESSEL: "basket", F.TOTE: "bag", F.FLAT_PANEL: "blanket",
                   F.PANEL_PAIR: "pillow", F.TRIANGLE: "shawl"}
    plain = {F.VESSEL: "storage", F.TOTE: "everyday", F.FLAT_PANEL: "everyday",
             F.PANEL_PAIR: "everyday", F.TRIANGLE: "everyday"}
    unmeasured = ("lidded", "giant", "jumbo", "sleepy", "zippered", "padded")
    checked = refused = 0
    for family, category in category_of.items():
        for head in sorted(F.FAMILY_HEADS[family]):
            ok_title = f"{plain[family].title()} {head.title()}"
            got = F.plan(category=category, title=ok_title)
            if got["family"] == F.REFUSED:
                # a head another rule claims first (a "triangle scarf", a "bag" category
                # rule) is still never drafted as something else
                assert "head noun" not in got["why"], (ok_title, got)
            checked += 1
            for word, tail in itertools.product(unmeasured, ("", " with Handles")):
                if family in (F.FLAT_PANEL, F.PANEL_PAIR, F.TRIANGLE) and not tail:
                    continue                    # their modifiers are judged at publish
                title = f"{word.title()} {head.title()}{tail}"
                assert F.plan(category=category, title=title)["family"] == F.REFUSED, title
                refused += 1
            for foreign in ("Fox", "Teddy Bear", "Pouch Pattern"):
                title = f"{plain[family].title()} {foreign}"
                assert F.plan(category=category, title=title)["family"] == F.REFUSED, title
                refused += 1
    assert checked > 50 and refused > 300, (checked, refused)


def test_motif_promise_is_in_name_truth_for_every_non_catalogue_product():
    from brambleloop.products import inventory
    from brambleloop.publish.eligibility import name_truth

    seed = pipeline._seed_for("nordic-forest-basket")
    geo = pipeline.concept_geometry(seed)

    def basket(title):
        return F.vessel(pipeline.Concept(slug="a2-probe", title=title, category="basket",
                                         stitch_repeat=[tuple(x) for x in geo["stitch_repeat"]],
                                         width_stitches=10, rows=4, colors=geo["colors"]))

    for title in ("Heart Basket", "Diamond Basket", "Snowflake Basket", "Chevron Basket",
                  "Pumpkin Basket", "Fir Tree Basket"):
        assert F.plan(category="basket", title=title)["family"] == F.VESSEL, title
        assert any(f.startswith("motif:") for f in name_truth(basket(title))), title
    assert name_truth(basket("Crochet Storage Basket")) == []
    # the engineered catalogue keeps its own gates (an integrator decision is recorded): a
    # catalogue title motif_promise does not back is not newly failed by name_truth
    from brambleloop.products import launch0

    assert "a2-probe" not in set(inventory.universe())
    pillow = inventory._engineered("heart-row-ring-pillow")
    assert launch0.motif_promise(pillow)["backed"] is False
    assert not any(f.startswith("motif:") for f in name_truth(pillow))


def test_every_radar_seed_routes_as_before():
    from brambleloop.radar.opportunity import POOL

    before = {"nordic-forest-basket": F.VESSEL}
    assert POOL
    for seed in POOL:
        family = F.plan(category=seed.category, title=seed.title, is_bundle=seed.is_bundle,
                        slug=seed.slug, rationale=seed.rationale)["family"]
        if seed.slug in before:
            assert family == before[seed.slug], (seed.slug, family)
        allowed = F.FAMILY_HEADS.get(family)
        assert allowed is None or F.title_head(seed.title) in allowed, seed.slug


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK   {name}")
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print(f"FAIL {name} {exc!r}"[:700])
                import traceback
                traceback.print_exc()
    print(f"{failed} failed")
    sys.exit(1 if failed else 0)
