"""An adversarial audit of the four pure-computation product modules.

`products/personalisation.py`, `products/motifs.py`, `products/texture.py` and
`products/vessels.py` generate customer-facing pattern text and construction, so a defect in
any of them reaches the buyer directly rather than being caught by somebody downstream.

Each test here reproduces one finding. They were written to fail against the code as it
stood, and the comment on each says what it saw. The defects are the five shapes this build
keeps finding:

  1. a verdict computed from the absence of evidence,
  2. a check that cannot see the thing it exists to measure,
  3. one value living in two places that can drift apart,
  4. a proof measured on a sample that cannot contain the broken case,
  5. a docstring asserting a property the code does not have.

The full write-up is `research/PRODUCTS_ADVERSARIAL.md`.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.cir import stitches  # noqa: E402
from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.cir.twin import build_twin  # noqa: E402
from brambleloop.cir.writer import write_pattern  # noqa: E402
from brambleloop.gates.certificate import CANONICAL_STAGES  # noqa: E402
from brambleloop.products import motifs as M  # noqa: E402
from brambleloop.products import personalisation as P  # noqa: E402
from brambleloop.products import texture as T  # noqa: E402
from brambleloop.products import vessels as V  # noqa: E402

CM = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*cm")

# Deliberately recomputed here from the gauge rather than imported from the modules under
# audit. These tests have to fail on the number the buyer reads when run against the code as
# it stood, not on an AttributeError for a helper that had not been written yet.
PAD_CM = 45.0


def _wide_cm(stitches: int, gauge) -> float:
    return stitches / gauge.stitches_per_10cm * 10.0


def _across_points_cm(stitches: int, gauge) -> float:
    import math

    return _wide_cm(stitches, gauge) / math.pi


def _twin(cir):
    result = compile_cir(cir)
    assert result.ok, [str(f) for f in result.errors]
    return result, build_twin(cir, result)


# ---- personalisation: the chain a custom design is routed to -------------------------------
#
# Shape 3, and shape 5 on top of it. `NEEDS_THE_CHAIN` was a hand-written tuple sitting under
# a comment that said "the chain's own stages, named rather than restated". It restated them,
# and the copy had gone stale.


def test_a_custom_design_is_routed_to_the_whole_chain_and_not_to_half_of_it():
    """The tuple named compile, twin, geometry, write, reverse, certificate.

    `certify` runs ten stages. Five of them -- originality, asset_truth, policy,
    physical_test and confidence -- were missing from what this module told a shop a
    customer's own design had to pass. Originality is the one that matters most here: it is
    the stage that exists to stop a customer-supplied arrangement shipping under our name,
    and a buyer's own motif layout is exactly the input it was built for.
    """
    needs = P.check(P.Offer("throw", "motif_arrangement", price_cad=8.0))["needs"]
    for stage in ("originality", "asset_truth", "policy", "physical_test", "confidence"):
        assert stage in needs, f"{stage} is in the chain and was not in what this module asks"
    assert list(P.NEEDS_THE_CHAIN) == list(CANONICAL_STAGES) + ["certificate"]


def test_a_subset_assertion_cannot_see_a_stage_that_went_missing():
    """Shape 4: the existing guard was `set(needs) <= set(CANONICAL_STAGES) | {certificate}`.

    A subset holds for every omission there is, so the check that was supposed to keep the
    two lists together passed all the way through the drift. This pins the direction the old
    assertion could not look in -- that nothing is *missing* -- by showing the stale tuple
    satisfying the old shape and failing this one.
    """
    stale = ("compile", "twin", "geometry", "write", "reverse", "certificate")
    assert set(stale) <= set(CANONICAL_STAGES) | {"certificate"}, \
        "the old assertion passed the stale tuple, which is the defect"
    assert set(stale) != set(P.NEEDS_THE_CHAIN)
    assert set(CANONICAL_STAGES) <= set(P.NEEDS_THE_CHAIN)


def test_an_option_on_neither_side_of_the_line_is_refused_rather_than_cleared():
    """Shape 1: every verdict was reached by two equality tests, and an option answering no
    to both collected no reasons -- so `ok` came back True because nothing had looked at it.

    A typo in a level, or a third level somebody invented, was a customisation cleared for
    sale by the absence of any rule that could see it.
    """
    P.OPTIONS["mystery_option"] = {"level": "Presentation",     # capital P: a plausible typo
                                   "what": "something nobody classified",
                                   "why": "a level that is neither of the two constants"}
    try:
        try:
            out = P.check(P.Offer("throw", "mystery_option"))
        except P.PersonalisationRefused as exc:
            assert "neither side of the line" in str(exc)
        else:
            raise AssertionError(
                f"an unclassified customisation was cleared for sale: ok={out['ok']}")
    finally:
        del P.OPTIONS["mystery_option"]


def test_the_catalogue_is_a_partition_and_not_two_filters_that_happen_to_cover_it():
    """Shape 1 again, with a quieter failure: `catalogue` built its two lists with
    `level == PRESENTATION` and `level == CONSTRUCTION`.

    An option matching neither appeared in neither list. It did not error and it did not show
    up anywhere a person would look -- the shop could not sell it and could not see that it
    was not selling it.
    """
    out = P.catalogue("throw")
    assert set(out["included"]) | set(out["needs_its_own_certificate"]) == set(P.OPTIONS)

    P.OPTIONS["mystery_option"] = {"level": None, "what": "unclassified", "why": "no level"}
    try:
        try:
            listed = P.catalogue("throw")
        except P.PersonalisationRefused:
            pass
        else:
            everything = set(listed["included"]) | set(listed["needs_its_own_certificate"])
            raise AssertionError(
                f"an unclassified option vanished from the catalogue silently: {everything}")
    finally:
        del P.OPTIONS["mystery_option"]


# ---- motifs: the library and what the checks can see ---------------------------------------


def test_the_library_holds_every_motif_this_module_defines():
    """Shape 3. `LIBRARY` was a hand-written tuple of the eight names above it -- a second
    copy of the set of motifs the file defines, which agrees only until somebody adds one."""
    defined = {m.slug for m in vars(M).values() if isinstance(m, M.Motif)}
    assert defined == set(M.LIBRARY), defined ^ set(M.LIBRARY)
    assert len(M.LIBRARY) >= 8


def test_a_motif_left_out_of_the_library_is_reported_rather_than_unseen():
    """Shape 1 and shape 4 together, and the reason the drift above was worth closing.

    `check_library` iterates `LIBRARY`. A motif that never reached it was validated by
    nothing, and `check_library()` returned `[]` -- which reads as "the library is sound" and
    meant "the broken motif was not in the sample I looked at". Here the stray motif is
    ragged *and* far outside the density band, and the old check saw neither.
    """
    stray = M.Motif("stray-motif", "Stray", ("1111", "111", "1111"))
    M.STRAY_MOTIF = stray
    try:
        problems = M.check_library()
        assert any(p.startswith("MOTIF_UNREGISTERED") and "stray-motif" in p
                   for p in problems), problems
    finally:
        del M.STRAY_MOTIF
    assert M.check_library() == [], M.check_library()


def test_two_motifs_sharing_a_slug_are_refused_rather_than_one_replacing_the_other():
    """The same disappearance reached another way: `{m.slug: m}` keeps the last of two
    motifs sharing a slug, and the first is in no product and past no check."""
    a = M.Motif("twin-slug", "First", ("1100", "0011"))
    b = M.Motif("twin-slug", "Second", ("1010", "0101"))

    # What the hand-written library did with a collision, spelled out: the first motif is
    # simply not there afterwards, and nothing said so.
    naive = {m.slug: m for m in (a, b)}
    assert len(naive) == 1 and naive["twin-slug"].name == "Second", \
        "keying by slug is what makes a collision silent"

    collect = getattr(M, "collect", None)
    assert collect is not None, \
        "the library is assembled by hand, so a slug collision has nothing to refuse it"
    try:
        collect({"A": a, "B": b})
    except M.MalformedMotif as exc:
        assert "twin-slug" in str(exc)
    else:
        raise AssertionError("one motif silently replaced another under the same slug")


def test_the_diamond_lattice_really_is_continuous():
    """A clean result, pinned because it is a claim in the shipped note.

    "a continuous lattice; every raised stitch touches another, so the fabric holds together"
    is a checkable statement about the grid, so it is checked rather than believed. It holds
    -- on its own and tiled -- which is why nothing in the module changed on its account.
    """
    motif = M.get("diamond-lattice")
    assert "every raised stitch touches another" in motif.note
    height, width = motif.height, motif.width
    lonely = []
    for y in range(height):
        for x in range(width):
            if motif.grid[y][x] != "1":
                continue
            neighbours = [motif.grid[(y + dy) % height][(x + dx) % width]
                          for dy in (-1, 0, 1) for dx in (-1, 0, 1) if (dy, dx) != (0, 0)]
            if "1" not in neighbours:
                lonely.append((y, x))
    assert lonely == [], lonely


# ---- texture: the size sentence the buyer reads --------------------------------------------


def test_the_bobble_panel_sits_the_way_round_its_own_sentence_says_it_does():
    """Shape 5, customer-facing. The note read: "Bobble fabric draws in, so the panel is
    worked slightly wider than the pad."

    The panel is 70 stitches at 16 sts/10cm, which is 43.8 cm. The pad is 45 cm. It is 1.2 cm
    *narrower*, and bobble fabric then draws it in further. The sentence stated the
    compensation backwards, and the buyer sizing a cover by it would have been reading the
    opposite of the arithmetic directly underneath.

    The arithmetic is the right one -- a cushion cover wants to be a little smaller than its
    pad so the pad fills it out -- so the sentence was made to follow it, and the direction
    word is now derived rather than typed.
    """
    cir = T.build_bobble_pillow()
    _, twin = _twin(cir)
    note = cir.finished_size_note or ""

    assert str(int(PAD_CM)) in note, "the pad the cover is sized for is still named"
    assert twin.width_cm < PAD_CM, (twin.width_cm, PAD_CM)
    assert "wider than the pad" not in note, \
        f"the panel is {PAD_CM - twin.width_cm:.1f} cm NARROWER than the pad: {note}"
    assert "narrower than the pad" in note, note

    stated = [float(n) for n in CM.findall(note)]
    assert any(abs(n - twin.width_cm) < 0.2 for n in stated), (stated, twin.width_cm)
    assert any(abs(n - (PAD_CM - twin.width_cm)) < 0.2 for n in stated), stated


def test_every_texture_width_sentence_is_the_width_the_twin_measures():
    """Shape 3: the numbers in these sentences were typed beside the stitch counts rather
    than computed from them, so each one was a second copy of a number in the same function.

    Nothing downstream reads `finished_size_note` -- the PDF takes its sizes from the twin --
    so there was no check anywhere that could have disagreed with a wrong one. This is that
    check.
    """
    for build, gauge in ((T.build_ribbed_scarf, T.CHUNKY),
                         (T.build_bobble_pillow, T.WORSTED),
                         (T.build_cable_throw, T.WORSTED)):
        cir = build()
        _, twin = _twin(cir)
        width = cir.components[0].foundation
        assert abs(_wide_cm(width, gauge) - twin.width_cm) < 0.5, cir.slug
        stated = [float(n) for n in CM.findall(cir.finished_size_note or "")]
        assert any(abs(n - twin.width_cm) < 0.6 for n in stated), \
            f"{cir.slug}: the sentence names {stated} and the piece is {twin.width_cm:.1f} cm"


def test_the_cable_column_count_is_counted_rather_than_spelled_out():
    """The designer note said "Eighteen cable columns" while the code computed the number
    from the width. True today, and a second copy of `across` -- wrong the first time
    anybody changes the width, with nothing to catch it."""
    cir = T.build_cable_throw()
    across = cir.components[0].foundation // 8
    assert f"{across} cable columns" in (cir.designer_notes or ""), cir.designer_notes
    assert "Eighteen" not in (cir.designer_notes or "")


# ---- vessels: the size on the listing ------------------------------------------------------


def test_the_coaster_listing_states_the_size_the_stitch_count_makes():
    """Shape 5, against the module's own docstring: "a target circumference becomes a stitch
    count the motif and the gauge both allow, and the stitch count becomes the diameter that
    goes on the listing".

    It did not. The note printed `across_cm` -- the size *asked for* -- while
    `base_stitches_for` rounds to a whole wedge and floors the count at twelve stitches. At
    the default 10 cm the listing said 10 and the coaster is 9.5. Below the floor the request
    is discarded outright: a 1 cm coaster is 1.9 cm and the listing said "About 1 cm".
    """
    for asked in (10.0, 1.0, 2.0, 7.0, 12.5):
        cir = V.build_hexagon_coaster(across_cm=asked)
        made = _across_points_cm(V.base_stitches_for(asked, V.COASTER_GAUGE),
                                 V.COASTER_GAUGE)
        stated = [float(n) for n in CM.findall(cir.finished_size_note or "")]
        assert any(abs(n - made) < 0.1 for n in stated), \
            f"asked {asked}, made {made:.2f} cm, listing says {stated}"

    # The floor is the case no existing test could reach, so it is named outright.
    tiny = V.build_hexagon_coaster(across_cm=1.0)
    assert "1.9 cm" in (tiny.finished_size_note or ""), tiny.finished_size_note


def test_the_basket_listing_states_the_size_the_stitch_count_makes():
    """The same substitution, in the product that does have a geometry test.

    That test measures only the three curated `BASKET_SIZES`, whose rounding error happens to
    be under half a centimetre -- shape 4, a sample that cannot contain the broken case. The
    listing figures are now the made sizes, and they are checked against the twin.
    """
    for spec in V.BASKET_SIZES:
        cir = V.build_basket(spec.key)
        _, twin = _twin(cir)
        stated = [float(n) for n in CM.findall(cir.finished_size_note or "")]
        made = _across_points_cm(V.base_stitches_for(spec.across_cm, V.COTTON_GAUGE),
                                 V.COTTON_GAUGE)
        assert any(abs(n - made) < 0.6 for n in stated), (spec.key, stated, made)
        assert abs(twin.width_cm - made) < 1.5, (spec.key, twin.width_cm, made)


def test_the_size_asked_for_is_not_the_size_made_and_the_gap_is_reachable():
    """The mechanism itself, so the finding above cannot be dismissed as a rounding quibble:
    `base_stitches_for` floors at two rounds' worth of stitches, and under that floor the
    number it returns has nothing to do with the number it was given."""
    assert V.base_stitches_for(1.0, V.COASTER_GAUGE) == V.base_stitches_for(2.0,
                                                                           V.COASTER_GAUGE)
    made = _across_points_cm(V.base_stitches_for(1.0, V.COASTER_GAUGE), V.COASTER_GAUGE)
    assert made > 1.8, made


# ---- left in place, and why ----------------------------------------------------------------


def test_the_written_cable_pattern_never_says_which_way_the_cable_crosses():
    """A finding whose fix is outside these four modules, pinned so it stays visible.

    `build_cable_throw`'s docstring says "which pair crosses in front is a property of the
    stitch instead of prose nobody checked". The stitch carries no such property:
    `cir/stitches.py` gives `cable2x2` a code, two names, consumes, produces and two heights,
    and nothing about direction. The only place the direction appears is `designer_notes`,
    which reaches neither the buyer's document nor any check -- so it is exactly the prose
    nobody checked that the docstring says it is not.

    What the buyer receives is "cable2x2 over next 4 sts", an abbreviation this system
    invented and the document never expands. A cable crossed the other way is a mirrored
    fabric, and nothing in the pattern tells them which one to make.

    Fixing it means a direction on `Stitch` and a special-stitch definition in
    `cir/writer.py`, both outside this audit's boundary. When that lands, this test should
    fail, and the right change is to assert the direction is in the written pattern.
    """
    assert "front" in (T.build_cable_throw().designer_notes or "").lower()

    cable = stitches.get("cable2x2")
    assert not any("front" in str(getattr(cable, f, "")).lower()
                   for f in ("code", "name_us", "name_uk")), \
        "the stitch now names a direction; move this assertion to the written pattern"

    cir = T.build_cable_throw()
    result, _ = _twin(cir)
    text = write_pattern(cir, result).lower()
    rows = "\n".join(l for l in text.splitlines() if l.startswith("row "))
    assert "cable2x2 over next 4 sts" in rows
    assert "front" not in rows and "held" not in rows and "cross" not in rows, \
        "the written pattern now carries the crossing direction -- update this test"


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
