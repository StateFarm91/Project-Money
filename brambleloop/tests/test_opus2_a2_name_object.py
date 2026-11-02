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
          "\u041a\u043e\u0440\u0437\u0438\u043d\u0430 Blanket",
          # A2-3: words inside a parenthesis, a dash or colon clause or a for-phrase are read
          "Storage Basket (Lidded)", "Basket (with Lid)", "Basket [Lidded]", "Basket {XL}",
          "Storage Basket - Giant", "Basket \u2014 Giant", "Basket \u2013 with Lid",
          "Storage Basket: with Lid", "Storage Basket (Teddy Bear)", "Basket - Teddy Bear",
          "Basket: Teddy Bear Edition", "Storage Basket for Giant Dogs",
          # A2-4: every family has a modifier allowlist
          "Hooded Blanket", "Giant Blanket", "Zippered Cushion", "Zippered Pillow",
          "Sleepy Fox Pillow", "Teddy Bear Blanket", "Teddy Bear Hanging", "Teddy Bear Cover",
          "Teddy Bear Square", "Teddy Bear Mat", "Fox Wrap",
          # A2-6: the repros the first test did not pin
          "XL Basket", "Sunflower Basket", "Owl Basket", "Fox Basket", "Striped Basket",
          "Fox Tote", "\uff34eddy \uff22ear", "\U0001d413eddy Bear")

LEGITIMATE = (("basket", "Crochet Storage Basket", F.VESSEL),
              ("basket", "Nordic Forest Mosaic Storage Basket", F.VESSEL),
              ("basket", "Market Basket", F.VESSEL), ("basket", "Bread Basket", F.VESSEL),
              ("basket", "Storage Basket Pattern", F.VESSEL),
              ("basket", "Basket (Large) - Easy", F.VESSEL),
              ("basket", "Storage Basket - Cream Edition", F.VESSEL),
              # A2-5: what a basket is for, and the size it is drafted at
              ("basket", "Toy Basket", F.VESSEL), ("basket", "Laundry Basket", F.VESSEL),
              ("basket", "Fruit Basket", F.VESSEL), ("basket", "Yarn Basket", F.VESSEL),
              ("basket", "Small Basket", F.VESSEL), ("basket", "Large Basket", F.VESSEL),
              ("basket", "Storage Basket (Cream)", F.VESSEL),
              ("basket", "Diamond Tapestry Basket", F.TAPESTRY),
              ("bag", "Everyday Market Tote", F.TOTE), ("bag", "Small Tote", F.TOTE),
              ("bag", "Tote Bag", F.TOTE), ("bag", "Drawstring Pouch", F.POUCH),
              ("blanket", "Everyday Throw for Beginners", F.FLAT_PANEL),
              ("blanket", "Winter Village Graphghan", F.FLAT_PANEL),
              ("placemat", "Mosaic Placemat Pair", F.FLAT_PANEL),
              ("wedding", "Wedding Ring Cushion", F.PANEL_PAIR),
              ("shawl", "Everyday Triangle Shawl", F.TRIANGLE),
              ("seasonal_decor", "Easter Egg Cosy Set", F.COSY),
              ("pet", "Cat Bed", F.VESSEL),
              ("stocking", "Classic Christmas Stocking", F.STOCKING))


def test_every_review_repro_is_refused_in_every_category():
    assert len(REPROS) == 79 and CATEGORIES
    drafted = [(c, t, F.plan(category=c, title=t)["family"])
               for t in REPROS for c in CATEGORIES
               if F.plan(category=c, title=t)["family"] != F.REFUSED]
    assert drafted == [], drafted


def test_legitimate_titles_still_draft():
    assert len(LEGITIMATE) == 27
    for category, title, family in LEGITIMATE:
        got = F.plan(category=category, title=title)
        assert got["family"] == family, (category, title, got)
    # A2-5: a size word in the title is the size drafted, never silently medium
    seed = pipeline._seed_for("nordic-forest-basket")
    geo = pipeline.concept_geometry(seed)

    def base(title):
        cir = F.vessel(pipeline.Concept(slug="a2-size", title=title, category="basket",
                                        stitch_repeat=[tuple(x) for x in geo["stitch_repeat"]],
                                        width_stitches=10, rows=4, colors=geo["colors"]))
        return max(r.declared_count for r in cir.components[0].rows)
    assert base("Small Basket") < base("Storage Basket") < base("Large Basket")


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
            # A2-4: every family judges its modifiers (not only the basket and tote)
            for word, tail in itertools.product(unmeasured, ("", " with Handles",
                                                             " (Giant)", " - Lidded")):
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
    # A2-1: the gate reads the title as the route does -- a full-width or mathematical-letter
    # motif word is the word it renders as
    for title in ("\uff28eart Basket", "\U0001d407eart Basket", "\U0001d412nowflake Basket"):
        assert F.plan(category="basket", title=title)["family"] == F.VESSEL, title
        assert any(f.startswith("motif:") for f in name_truth(basket(title))), title
    # A2-2: fail-closed -- every CIR that is not an engineered design is held to it, whatever
    # its provenance says (the radar fallback with known lineage records concept_to_cir)
    import dataclasses

    from brambleloop.creative.prototype import source_provenance

    heart = basket("Heart Basket")
    for prims in (("creative.fallback_constructions.vessel",),
                  ("creative.construction_registry.build",),
                  ("runtime.pipeline.concept_to_cir", "creative.prototype.gauge_for:worsted"),
                  ("products.moment_candidates._disc",), ()):
        prov = source_provenance("a2-probe", {"provenance": "research:a2"}, {}, prims) \
            if prims else None
        assert any(f.startswith("motif:") for f in name_truth(
            dataclasses.replace(heart, provenance=prov))), prims
    # A2F-1: a SLUG is not an identity. A rule-drafted CIR under an engineered slug is held to
    # the motif check like any other; only the engineered builder's exact output is exempt.
    from brambleloop.products import pipeline_board
    from brambleloop.publish import eligibility

    for slug in ("heart-relief-table-runner", "first-christmas-stocking",
                 "teacher-chevron-pencil-roll"):
        posing = dataclasses.replace(heart, slug=slug)
        assert eligibility._drafted_by_a_rule(posing), slug
        assert any(f.startswith("motif:") for f in name_truth(posing)), slug
    runner = pipeline_board.proposal_cir(next(p for p in pipeline_board.PROPOSALS
                                              if p.slug == "heart-relief-table-runner"))
    assert not eligibility._drafted_by_a_rule(runner)
    assert not eligibility._drafted_by_a_rule(dataclasses.replace(runner, version="9.9.9"))
    assert eligibility._drafted_by_a_rule(dataclasses.replace(runner, title="Heart Blanket"))
    assert not hasattr(eligibility, "_engineered_designs")
    # the engineered catalogue keeps its own gates (an integrator decision is recorded): a
    # catalogue title motif_promise does not back is not newly failed by name_truth
    from brambleloop.products import launch0

    assert "a2-probe" not in set(inventory.universe())
    pillow = inventory._engineered("heart-row-ring-pillow")
    assert launch0.motif_promise(pillow)["backed"] is False
    assert not any(f.startswith("motif:") for f in name_truth(pillow))



# A2F-4: a figure or texture the plain builders do not make is refused, not drafted plain.
# (Moved from LEGITIMATE: "Polar Bear Blanket", "Bear Paw Blanket", "Basket Weave Blanket",
# "Bear Pillow" -- no bear, paw or weave is made by a plain panel, and none is a measured motif.)
UNMADE_TEXTURES = (("blanket", "Ribbed Blanket"), ("blanket", "Ribbed Throw"),
                   ("scarf", "Ribbed Scarf"), ("scarf", "\uff32ibbed Scarf"),
                   ("blanket", "\U0001d411ibbed Blanket"), ("blanket", "Basket Weave Blanket"),
                   ("blanket", "Weave Blanket"), ("blanket", "Bear Blanket"),
                   ("blanket", "Paw Blanket"), ("blanket", "Polar Blanket"),
                   ("blanket", "Polar Bear Blanket"), ("blanket", "Bear Paw Blanket"),
                   ("pillow", "Bear Cushion"), ("pillow", "Bear Pillow"),
                   ("basket", "Textured Basket"), ("baby", "Textured Baby Blanket"))


def test_a2f4_textures_and_figures_the_plain_builders_do_not_make_are_refused():
    for category, title in UNMADE_TEXTURES:
        assert F.plan(category=category, title=title)["family"] == F.REFUSED, (category, title)


def test_a2f3_an_explicit_size_word_decides_and_conflicting_sizes_are_refused():
    for title in ("Small Market Basket", "Large Bread Basket", "Medium Bread Basket",
                  "Market Basket (Small)", "Basket - Small - Large", "Small Large Basket"):
        assert F.plan(category="basket", title=title)["family"] == F.REFUSED, title
    for title, size in (("Small Basket", "small"), ("Large Basket", "large"),
                        ("\uff2carge Basket", "large"), ("Market Basket", "large"),
                        ("Bread Basket", "small"), ("Medium Basket", "medium"),
                        ("Storage Basket", None), ("Basket - Cream - Large", "large")):
        assert F.plan(category="basket", title=title)["family"] == F.VESSEL, title
        assert F.basket_size_key(title) == (size, None), (title, F.basket_size_key(title))


def test_a2f5_other_objects_are_never_vessels_and_every_clause_is_read():
    # M14: a blanket or a cushion is never drafted as a basket
    for title in ("Blanket", "Cushion", "Storage Blanket", "Everyday Cushion", "Throw"):
        assert F.plan(category="basket", title=title)["family"] == F.REFUSED, title
    # M32: every dash clause is read, not only the first
    for title in ("Basket - Cream - Giant", "Basket - Cream - Teddy Bear"):
        assert F.plan(category="basket", title=title)["family"] == F.REFUSED, title
    # M21: the motif reader drops zero-width and format characters (one shared fold)
    from brambleloop.products import launch0 as L

    assert L._motif_fold("He\u200bart") == "heart" and L._motif_fold("\u041dеart") == "heart"
    assert L._motif_fold("\u0397eart") == "heart"


def test_a2f2_every_title_reader_is_the_one_fold():
    from brambleloop.gates import asset_truth
    from brambleloop.products import launch0 as L
    from brambleloop.products.text_fold import fold

    for t in ("\u041dеart Runner", "\u0397eart Runner", "\uff32ibbed Scarf",
              "He\u3164art Basket"):
        assert F.fold_title(t) == " ".join(fold(t).split()), t
        assert L._motif_fold(t) == fold(t), t
    import inspect

    for fn in (asset_truth.check_technique_claims, asset_truth.check_shape_claims):
        assert "fold(text)" in inspect.getsource(fn), fn.__name__

def test_every_radar_seed_routes_as_before():
    from brambleloop.radar.opportunity import POOL

    # A2-4: two seeds now refuse, fail-closed: "Bobble Floor Pillow" (a bobble texture and a
    # floor size the plain panel pair does not make) and "Chunky Ribbed Scarf" (a yarn-weight
    # claim no gate measures). Every other seed routes as at INTEG1.
    before = {"nordic-forest-basket": F.VESSEL, "bobble-floor-pillow": F.REFUSED,
              "chunky-ribbed-scarf": F.REFUSED, "heirloom-cable-blanket": F.FLAT_PANEL,
              # A2F-4: "Cloudline Textured Baby Blanket" has no engineered builder, so the
              # fallback would draft it as a plain panel with no texture: refused.
              "cloudline-baby-blanket": F.REFUSED, "pet-snuggle-mat": F.FLAT_PANEL}
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
