"""The customer deliverable, audited as the buyer rather than as the pipeline.

The product this company sells is a PDF. Everything upstream of it -- the compiler, the twin,
the reverse compiler, the gates -- is about whether the *pattern* is right, and every one of
those was passing while the document a customer downloads was missing the things a maker
needs to use it. These tests are about the document.

Each one below started as a defect found by reading a rendered PDF (2026-09-24 audit,
`research/DELIVERABLE_QA.md`), ranked by whether it stops somebody making the thing they
paid for:

  1. a UK-terms render printed `fpdc`, which in UK terms names a stitch half the height of
     the one the pattern was compiled against;
  2. a cabled throw worked in post stitches was sold, labelled and gated as *beginner*,
     because three copies of one stale stitch list agreed with each other;
  3. the document had no abbreviation key at all, and the only key in it was a picture built
     from the chart -- which cannot contain the turning chain or the skipped stitch, because
     neither makes a cell in the fabric;
  4. the stated row gauge and the pattern's own finished length implied two different
     fabrics, and the document printed only one of them.
"""
from __future__ import annotations

import hashlib
import io
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

import pypdf  # noqa: E402

from brambleloop.brand import bible  # noqa: E402
from brambleloop.cir import stitches  # noqa: E402
from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.cir.model import Op  # noqa: E402
from brambleloop.cir.twin import build_twin  # noqa: E402
from brambleloop.cir.writer import write_op, write_pattern  # noqa: E402
from brambleloop.products import nordic_forest as nf  # noqa: E402
from brambleloop.products.builder import CATALOGUE, build, for_slug  # noqa: E402
from brambleloop.products.texture import (  # noqa: E402
    build_bobble_pillow, build_cable_throw, build_ribbed_scarf,
)
from brambleloop.products.vessels import build_hexagon_coaster  # noqa: E402
from brambleloop.publish import abbreviations as ab  # noqa: E402
from brambleloop.publish import difficulty as diff  # noqa: E402
from brambleloop.publish import pdf as pdf_mod  # noqa: E402
from brambleloop.publish.pdf import build_pattern_pdf  # noqa: E402

RELEASED = date(2026, 9, 24)


def _designs() -> list:
    """Every design the pipeline can actually ship, not a convenient sample.

    The texture designs are the ones the defects were in, and they are exactly the ones a
    catalogue-only loop would have missed: `products.builder.CATALOGUE` does not contain
    them, `runtime.pipeline.ENGINEERED` does.
    """
    out = [nf.build()]
    out += [build(CATALOGUE[slug]) for slug in sorted(CATALOGUE)]
    out += [build_cable_throw(), build_bobble_pillow(), build_ribbed_scarf(),
            build_hexagon_coaster()]
    return out


def _twin_for(cir):
    result = compile_cir(cir)
    assert result.ok, [str(f) for f in result.errors]
    return result, build_twin(cir, result)


def _text_of(doc) -> str:
    reader = pypdf.PdfReader(io.BytesIO(doc.pdf_bytes))
    return "\n".join(page.extract_text() for page in reader.pages)


def _flat(doc) -> str:
    """The document's text with its line breaks closed up.

    A sentence in the PDF is wrapped to the column, so looking for one in the extracted text
    is looking for a string the document does not contain in that form. Every phrase check
    below runs against this, which is what a reader sees rather than what the layout did.
    """
    return " ".join(_text_of(doc).split())


# ---- 1. terminology -------------------------------------------------------


def test_the_key_declares_a_token_for_every_stitch_in_the_canonical_registry():
    """A stitch the key cannot name must not be able to reach a customer unnoticed.

    The registry is the authority on what a stitch is; this table is the authority on what it
    is *called on the page*, per terminology. Holding a second table at all is a risk, so it
    is pinned to the first: a stitch added to `cir.stitches` with no entry here fails now,
    rather than appearing in somebody's instructions as a bare code six products later --
    which is how `cable2x2` got printed at a customer.
    """
    assert set(ab.TOKENS) == set(stitches.known_codes()), (
        sorted(set(stitches.known_codes()) - set(ab.TOKENS)),
        sorted(set(ab.TOKENS) - set(stitches.known_codes())))
    for code in ab.TOKENS:
        assert ab.meaning(code, "US") and ab.meaning(code, "UK"), code


def test_the_key_and_the_writer_agree_about_what_the_document_prints():
    """Measured against the writer's real output, not against a reading of its source.

    The two modules share no table on purpose -- the same reason the reverse compiler shares
    no parsing code with the writer -- so this is the only check that can catch the key and
    the document drifting apart.
    """
    for code in sorted(ab.TOKENS):
        printed = write_op(Op(code, 1), "US").lower()
        assert ab._contains(printed, ab.token(code, "US").lower()), (code, printed)
    assert ab.unlocalised("US") == (), ab.unlocalised("US")


def test_the_uk_render_still_prints_us_codes_for_the_stitches_the_writer_never_localised():
    """The defect, pinned where it is visible and owned by the module that must fix it.

    `cir.writer._term` maps sc, hdc, dc, tr and the shaping stitches into UK terms and has no
    entry for the post stitches; `write_op` short-circuits `sk` before it reaches the map at
    all. A UK maker reading `fpdc` works a front post *double* crochet -- which in UK terms
    is the stitch a US pattern calls single crochet, half the height of the stitch this
    pattern was compiled against, in a fabric whose whole point is the raised cable.

    Asserted as a subset so that fixing the writer (which this department may not edit --
    `cir/**` is owned elsewhere) makes this pass, not fail.
    """
    known_gap = {"fpdc", "bpdc", "sk"}
    assert set(ab.unlocalised("UK")) <= known_gap, ab.unlocalised("UK")
    assert "fpdc" in ab.unlocalised("UK"), (
        "the writer now localises fpdc -- delete it from the known gap and from the refusal "
        "note in publish/pdf.py")


def test_a_uk_document_that_would_instruct_the_wrong_stitch_is_refused():
    """Refused rather than rendered, on the same ground as a pattern that fails compilation.

    Nothing renders UK terms in the pipeline today, which is exactly why the rule can be set
    at full strength: a rule written after the first wrong UK document exists is a rule
    argued against a sunk cost.
    """
    cable = build_cable_throw()
    try:
        build_pattern_pdf(cable, terminology="UK", released_on=RELEASED)
    except ValueError as e:
        assert "fpdc" in str(e) and "UK" in str(e), str(e)
    else:
        raise AssertionError("a UK PDF was rendered containing an unlocalised post stitch")

    # And a pattern with no such stitch still renders in UK terms, so the guard is about the
    # stitches rather than about the terminology.
    plain = for_slug("cloudline-baby-blanket")
    uk = build_pattern_pdf(plain, terminology="UK", released_on=RELEASED)
    assert uk.pages > 1
    assert "UK terms" in _text_of(uk)


# ---- 2. difficulty --------------------------------------------------------


def test_every_registered_stitch_has_a_difficulty_and_none_defaults_to_easy():
    """The rung a new stitch arrives on decides who is told they can make the thing.

    Post stitches, bobbles and cable crossings entered the registry in B-080 and no
    difficulty list was updated, so the pattern containing all three was rated by the
    absence of `tr`.
    """
    assert diff.unrated() == (), diff.unrated()
    assert diff.ADVANCED_STITCHES >= {"fpdc", "bpdc", "bob", "cable2x2", "cable1x1"}
    assert not diff.ADVANCED_STITCHES & {"sc", "dc", "ch", "hdc", "slst", "sk"}


def test_a_cabled_throw_is_not_sold_as_beginner_work():
    """The live defect. The PDF cover said beginner over a fabric of crossed post stitches."""
    cable = build_cable_throw()
    _, twin = _twin_for(cable)
    assert diff.difficulty(cable, twin) == "intermediate", diff.difficulty(cable, twin)

    doc = build_pattern_pdf(cable, twin=twin, released_on=RELEASED)
    assert doc.difficulty == "intermediate"
    assert "beginner" not in _text_of(doc).lower()

    # The other two texture designs move with it, for the same reason and no other: a bobble
    # is closed over five loops and a rib is worked around the post.
    for design in (build_bobble_pillow(), build_ribbed_scarf()):
        _, t = _twin_for(design)
        assert diff.difficulty(design, t) == "intermediate", design.slug

    # And the ladder was raised where the fabric is hard, not everywhere: the mosaic
    # colourwork that is most of the catalogue is untouched by this change.
    plain = for_slug("cloudline-baby-blanket")
    _, plain_twin = _twin_for(plain)
    assert diff.difficulty(plain, plain_twin) == "confident beginner"
    assert not diff.ADVANCED_STITCHES & set(plain_twin.stitch_types_used)


def test_the_pdf_the_listing_and_the_gate_read_one_difficulty_ladder():
    """Three copies of the same four lines agreed with each other and were all wrong.

    `publish/pdf`, `runtime/release` and `gates/asset_truth` each held their own literal set
    of advanced stitches. Corroboration between three readings of one stale list is not
    corroboration, so there is one list and these are the three places that must use it.
    """
    from brambleloop.gates import asset_truth
    from brambleloop.runtime import release

    for cir in _designs():
        _, twin = _twin_for(cir)
        doc_says = build_pattern_pdf(cir, twin=twin, released_on=RELEASED).difficulty
        listing_says = release._difficulty(twin, cir)
        assert doc_says == listing_says, (cir.slug, doc_says, listing_says)

    # And the gate can now see the stitch it exists to see. A beginner claim about the
    # cabled throw was passing this gate, which is the reason the listing could make it.
    cable = build_cable_throw()
    _, twin = _twin_for(cable)
    asset = asset_truth.Asset(
        asset_id="hero-1", asset_class=asset_truth.AssetClass.DIGITAL_TWIN_RENDER,
        provenance=asset_truth.Provenance(source="twin", created_by="deliverable-qa-test"),
        is_hero=True, claims=asset_truth.Claims(difficulty="beginner"))
    findings = asset_truth.check_asset(asset, cable, twin)
    assert any(f.code == "CLAIM_DIFFICULTY_UNSUPPORTED" for f in findings), \
        [f.code for f in findings]

    # And the honest claim passes, so the gate is measuring the pattern rather than refusing
    # every difficulty it is shown.
    asset.claims = asset_truth.Claims(difficulty="intermediate")
    assert not any(f.code == "CLAIM_DIFFICULTY_UNSUPPORTED"
                   for f in asset_truth.check_asset(asset, cable, twin))


# ---- 3. the key the document did not have ---------------------------------


def test_every_abbreviation_in_the_instructions_is_defined_in_the_document():
    """The buyer's test: nothing in the instructions is a word you have to look up elsewhere.

    Run over every shippable design rather than a fixture, because the stitches that were
    undefined were the ones only three designs use.
    """
    for cir in _designs():
        result, twin = _twin_for(cir)
        text = write_pattern(cir, result, terminology="US",
                             width_cm=twin.width_cm, height_cm=twin.height_cm)
        assert ab.undefined_tokens(text, "US") == [], (cir.slug,
                                                       ab.undefined_tokens(text, "US"))
        doc = build_pattern_pdf(cir, twin=twin, released_on=RELEASED)
        assert doc.problems == [] or all(
            p.startswith("PDF_CABLE_DIRECTION_UNSPECIFIED") for p in doc.problems), \
            (cir.slug, doc.problems)
        rendered = _text_of(doc)
        assert "Abbreviations" in rendered, cir.slug
        for entry in ab.stitch_key(text, "US"):
            assert entry.token in rendered, (cir.slug, entry.token)
            assert entry.means in rendered, (cir.slug, entry.means)


def test_the_key_covers_the_stitches_that_never_appear_in_the_chart():
    """Why the old key could not have been complete however carefully it was written.

    The rendered legend is built from `twin.stitch_types_used`, which is the stitches that
    produced a *cell*. A turning chain produces no cell and a skipped stitch produces no
    cell, so "Ch 1, turn" and "sk next st" could appear in instructions whose only key was
    structurally incapable of containing them. The key is driven by the document's own text
    for that reason.
    """
    cir = for_slug("cloudline-baby-blanket")
    result, twin = _twin_for(cir)
    text = write_pattern(cir, result, terminology="US")
    assert "ch" not in twin.stitch_types_used, \
        "this design now charts its chains; pick one that does not"
    assert "Ch 1" in text, "this design stopped turning with a chain"
    assert any(e.token == "ch" for e in ab.stitch_key(text, "US")), \
        "the turning chain is in the instructions and not in the key"

    # And the notation a row is written in, which no stitch registry can supply.
    labels = {e.token for e in ab.notation_key(text)}
    assert "(120 sts)" in labels and "[ ... ] x 4" in labels, labels
    # A convention the document does not use is not explained: a key padded with irrelevant
    # entries is a key nobody finishes reading.
    assert "magic ring" not in labels, labels


def test_a_special_stitch_is_explained_where_it_is_used_and_nowhere_else():
    """A name is not an instruction. `bob` and `fpdc` are stitches a buyer meets here first."""
    cable = build_cable_throw()
    _, twin = _twin_for(cable)
    rendered = _flat(build_pattern_pdf(cable, twin=twin, released_on=RELEASED))
    assert "Special stitches" in rendered
    assert "around the post" in rendered
    # The tool that method requires reached the shopping list, which is an earlier page.
    lowered = rendered.lower()
    assert lowered.index("cable needle") < lowered.index("special stitches"), \
        "the cable needle is explained before it is listed in Materials"

    plain = for_slug("cloudline-baby-blanket")
    _, plain_twin = _twin_for(plain)
    plain_text = _text_of(build_pattern_pdf(plain, twin=plain_twin, released_on=RELEASED))
    assert "Special stitches" not in plain_text, \
        "a plain sc/dc pattern is being given a special-stitch section it does not need"


def test_the_cable_crossing_direction_is_reported_rather_than_invented():
    """The one thing the document still cannot say, said out loud instead of guessed.

    `cir.stitches.CABLE_2X2`'s own comment says which two cross in front "is a property of
    the stitch rather than prose nobody validated" -- and the `Stitch` dataclass has no such
    property. A cable held at the front and one held at the back are mirror images and the
    same op to every check in this system, so the document names the gap and the release
    chain records it. Picking a side here would print a fact the compiler never checked.
    """
    assert not hasattr(stitches.CABLE_2X2, "crosses"), (
        "the CIR can now express a crossing direction -- state it in the document and drop "
        "PDF_CABLE_DIRECTION_UNSPECIFIED")
    cable = build_cable_throw()
    _, twin = _twin_for(cable)
    doc = build_pattern_pdf(cable, twin=twin, released_on=RELEASED)
    assert any(p.startswith("PDF_CABLE_DIRECTION_UNSPECIFIED") for p in doc.problems), \
        doc.problems
    assert " ".join(ab.CABLE_DIRECTION_NOTE.split()) in _flat(doc)


# ---- 4. the two gauges ----------------------------------------------------


def test_the_document_reconciles_its_stated_gauge_with_the_fabric_it_makes():
    """Both numbers were right and the document printed one of them.

    Cloudline states 18 rows = 10 cm in sc and its own progress table says 88 rows come to
    97 cm, which is 9 rows to 10 cm. Nothing is wrong with either: the swatch is plain sc and
    the blanket is mostly dc, which is twice as tall. But a maker checking their work at row
    22 measured 24 cm where the stated gauge implies 12, and the only conclusion available to
    them was that their gauge was catastrophically wrong.
    """
    cir = for_slug("cloudline-baby-blanket")
    _, twin = _twin_for(cir)
    fabric = pdf_mod._fabric_row_gauge(twin)
    assert fabric is not None
    drift = abs(fabric - cir.gauge.rows_per_10cm) / cir.gauge.rows_per_10cm
    assert drift > pdf_mod.ROW_GAUGE_DRIFT, (fabric, cir.gauge.rows_per_10cm)

    rendered = _text_of(build_pattern_pdf(cir, twin=twin, released_on=RELEASED))
    assert "SWATCH ROW GAUGE" in rendered.upper()
    assert f"about {fabric:.0f} rows = 10 cm" in rendered, fabric
    assert "both right and they are not the same number" in rendered


def test_a_pattern_whose_two_gauges_agree_is_not_given_a_paragraph_about_it():
    """A caveat printed on every pattern is a caveat nobody reads by the third one."""
    scarf = build_ribbed_scarf()
    _, twin = _twin_for(scarf)
    fabric = pdf_mod._fabric_row_gauge(twin)
    stated = scarf.gauge.rows_per_10cm
    drift = abs(fabric - stated) / stated
    rendered = _text_of(build_pattern_pdf(scarf, twin=twin, released_on=RELEASED))
    if drift < pdf_mod.ROW_GAUGE_DRIFT:
        assert "SWATCH ROW GAUGE" not in rendered.upper(), (fabric, stated)
    else:  # pragma: no cover - documents the alternative rather than asserting the fixture
        assert "SWATCH ROW GAUGE" in rendered.upper()


# ---- 5. download integrity and reproducibility ----------------------------


def test_the_same_release_renders_the_same_bytes_on_a_different_day():
    """The existing determinism test could not have caught this, and said it had.

    `test_the_same_certified_pattern_renders_the_same_file_every_time` renders three times in
    one process on one day. The release date is printed on the cover, and it defaulted to
    `date.today()` -- so the proof was measured on a sample that cannot contain the broken
    case, and the docstring claiming the hash identifies the customer's file was wrong by a
    day. Artifact bytes are not durable, so a purchased file is re-rendered on demand and the
    store handler renders it again at upload.
    """
    cir = for_slug("cloudline-baby-blanket")

    class _Clock:
        @staticmethod
        def today():
            return date(2030, 1, 1)

    pinned = [hashlib.sha256(
        build_pattern_pdf(cir, released_on=RELEASED).pdf_bytes).hexdigest()]
    original = pdf_mod.date
    try:
        pdf_mod.date = _Clock
        pinned.append(hashlib.sha256(
            build_pattern_pdf(cir, released_on=RELEASED).pdf_bytes).hexdigest())
        drifted = hashlib.sha256(build_pattern_pdf(cir).pdf_bytes).hexdigest()
    finally:
        pdf_mod.date = original

    assert len(set(pinned)) == 1, "a pinned release date still renders two different files"
    assert drifted != pinned[0], (
        "the clock is no longer an input to the render -- if that is deliberate, this test "
        "and release._released_on can both go")


def test_the_release_chain_pins_the_date_rather_than_reading_the_clock():
    """The half of the fix that decides whether a customer is affected."""
    from brambleloop.runtime import release

    assert "released_on=_released_on(" in Path(
        release.__file__).read_text(), \
        "assets.build renders the customer PDF without pinning its release date"


def test_the_footer_tells_a_buyer_whether_their_download_finished():
    """The cheapest integrity check a customer can run, and it needs no software.

    "page 5" cannot tell anyone whether a file stopped early. "page 5 of 7" can.
    """
    cir = for_slug("cloudline-baby-blanket")
    doc = build_pattern_pdf(cir, released_on=RELEASED)
    rendered = _text_of(doc)
    assert f"page 1 of {doc.pages}" in rendered
    assert f"page {doc.pages} of {doc.pages}" in rendered
    assert f"This document is {doc.pages} pages" in rendered


def test_the_file_is_a_complete_readable_pdf_with_its_own_metadata():
    """A file in a downloads folder six months later, and what a screen reader gets."""
    cir = for_slug("cloudline-baby-blanket")
    doc = build_pattern_pdf(cir, released_on=RELEASED)
    assert doc.pdf_bytes.startswith(b"%PDF-")
    assert doc.pdf_bytes.rstrip().endswith(b"%%EOF")
    reader = pypdf.PdfReader(io.BytesIO(doc.pdf_bytes))
    assert len(reader.pages) == doc.pages
    meta = reader.metadata
    assert cir.title in (meta.title or "")
    assert meta.author, "the file has no author, so it is Untitled in any library"
    assert "US terms" in (meta.subject or "")
    assert reader.root_object.get("/Lang"), "no document language for assistive software"
    # Every page carries text. The chart pages carry only a running head and a footer, which
    # is the point of the line pointing at the text key -- a page with no text at all would
    # be a page a screen reader cannot announce.
    blank = [i for i, p in enumerate(reader.pages, 1) if not p.extract_text().strip()]
    assert not blank, blank


# ---- 6. what a maker has to be able to read -------------------------------


def test_every_tool_the_instructions_require_is_on_the_materials_list():
    """The page a buyer takes to the shop listed yarn, and the pattern told them to block it."""
    for cir in _designs():
        _, twin = _twin_for(cir)
        rendered = _text_of(build_pattern_pdf(cir, twin=twin, released_on=RELEASED)).lower()
        if "weave in" in rendered or "fasten off" in rendered:
            assert "tapestry needle" in rendered, cir.slug
        if "pin it out" in rendered:
            assert "blocking pins" in rendered, cir.slug
        if "cable needle" in rendered:
            assert rendered.count("cable needle") >= 2, (
                cir.slug, "the cable needle is used and never listed")


def test_the_small_print_is_legible_and_no_smaller_than_the_brand_allows():
    """Measured as a contrast ratio, not judged by eye.

    The brand's muted grey is 4.48:1 on the brand's cream -- a hair under the AA floor for
    text this size, and it is the colour of the yardage caveat, the substitution notes, the
    chart instructions and the page numbers. The palette is left alone; the document darkens
    its own ink until it passes.
    """
    assert pdf_mod.contrast(pdf_mod.INK, pdf_mod.CREAM) >= pdf_mod.MIN_CONTRAST
    assert pdf_mod.contrast(pdf_mod.PINE, pdf_mod.CREAM) >= pdf_mod.MIN_CONTRAST
    assert pdf_mod.contrast(pdf_mod.MUTED, pdf_mod.CREAM) >= pdf_mod.MIN_CONTRAST, \
        pdf_mod.contrast(pdf_mod.MUTED, pdf_mod.CREAM)
    assert pdf_mod.contrast(pdf_mod.GOLD_ON_PINE, pdf_mod.PINE) >= pdf_mod.MIN_CONTRAST

    # The brand colour is still the starting point rather than a colour invented here.
    brand = bible.PALETTE["muted"]
    assert pdf_mod.contrast(pdf_mod.MUTED, pdf_mod.CREAM) < 7.5, (
        "the muted grey has been darkened far past legibility and is now effectively body "
        "ink, which loses the hierarchy it exists to carry")
    assert brand == "#6B7280", "the brand palette moved; re-measure rather than assume"


def test_no_type_in_the_customer_document_is_set_below_the_brand_minimum():
    """Pinned in the source, because the defect is invisible in a passing render.

    The footer was 8pt against a brand rule of 9. Nothing failed; it just could not be read
    by the customer most likely to be printing the thing out.
    """
    import re

    source = Path(pdf_mod.__file__).read_text()
    minimum = bible.TYPOGRAPHY["min_body_pt"]
    offenders = []
    for number, line in enumerate(source.splitlines(), 1):
        for match in re.finditer(r'setFont\("Helvetica(?:-Bold)?",\s*(\d+)\)', line):
            if int(match.group(1)) < minimum:
                offenders.append((number, line.strip()))
        for match in re.finditer(r"\bsize=(\d+)\b", line):
            if int(match.group(1)) < minimum:
                offenders.append((number, line.strip()))
    assert not offenders, offenders


def test_the_chart_and_its_legend_are_pictures_and_the_document_says_where_the_text_is():
    """An image-only key is unreadable to the buyer who most needs a key.

    The legend is a rendered PNG: nothing in it is selectable, searchable or available to a
    screen reader. It stays, because it is good, and the same key is now in text with a line
    on the chart page pointing at it.
    """
    cir = for_slug("cloudline-baby-blanket")
    rendered = _text_of(build_pattern_pdf(cir, released_on=RELEASED))
    assert "also written out under Abbreviations" in rendered
    assert rendered.index("Abbreviations") < rendered.index("also written out under")


# ---- 7. the check that could not fail -------------------------------------


def test_a_terminology_note_is_not_a_stitch_key():
    """The audit's clearest instance of a verdict computed from the wrong evidence.

    `SECTION_CUES["abbreviations"]` counted the phrase "us terms", and this document's
    instructions heading reads "Instructions (US terms)" -- so `reader.self_test()` reported
    an abbreviations section in a PDF that had none, and the readiness verdict it feeds was
    computed from that. The same cue would have credited a competitor's purchased pattern
    with a key they had not written, on the one section our own product was missing.
    """
    from brambleloop.teardown import reader

    cues = reader.SECTION_CUES["abbreviations"]
    assert "us terms" not in cues and "uk terms" not in cues, cues
    assert "abbreviation" in cues

    heading = "instructions (us terms)"
    assert not any(cue in heading for cue in cues), heading
    assert any(cue in "abbreviations" for cue in cues)

    # And the document now earns the section it was being credited with.
    from brambleloop.teardown.library import LIBRARY_ENV

    cir = for_slug(reader.SELF_TEST_SLUG)
    doc = build_pattern_pdf(cir, released_on=RELEASED)
    with tempfile.TemporaryDirectory(prefix="deliverable-qa-") as tmp:
        root = Path(tmp)
        (root / "purchase").mkdir()
        (root / "purchase" / "pattern.pdf").write_bytes(doc.pdf_bytes)
        out = reader.read("purchase/pattern.pdf", env={LIBRARY_ENV: str(root)})
    assert "abbreviations" in out["sections"], sorted(out["sections"])


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
