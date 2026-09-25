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
from reportlab.lib.units import mm  # noqa: E402

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


# Rendered documents, reused across the checks below.
#
# Several of these read the whole catalogue in both terminologies -- which is the point, since
# the defects that reached customers were in the three designs a convenient fixture leaves out
# -- and rendering thirty-two multi-page documents once per check is the same document over and
# over. The render is deterministic for a fixed release date, which is a property this file
# proves separately, so caching it cannot hide a difference between two renders.
#
# Keyed on everything that changes the bytes. A cache keyed on less than that is how a check
# becomes a label.
_DOCS: dict[tuple, object] = {}


def _doc_for(cir, twin, terminology="US"):
    key = (cir.slug, cir.version, terminology, RELEASED)
    if key not in _DOCS:
        _DOCS[key] = build_pattern_pdf(cir, twin=twin, terminology=terminology,
                                       released_on=RELEASED)
    return _DOCS[key]


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


def test_the_uk_render_localises_every_stitch_the_document_can_contain():
    """Was a pinned defect; is now the property itself.

    When this was written, `cir.writer._term` carried its own terminology map covering only
    the basic stitches and their shaping variants, returned the US code unchanged for
    anything else, and `write_op` short-circuited `sk` before the map was consulted at all.
    A UK maker reading `fpdc` works a front post DOUBLE crochet -- in UK terms the stitch a
    US pattern calls single crochet, HALF the height of the one the pattern compiled
    against, in a fabric whose whole point is the raised cable.

    The department that found it could not fix it, because `cir/**` is owned elsewhere, so
    it pinned the gap as a subset and left a message saying what to do when the root was
    fixed. The root is now fixed: one table in `cir.stitches.UK_TERMS`, which both the writer
    and the key derive from, so they cannot disagree again. The assertion is therefore
    tightened from "no worse than this known gap" to "there is no gap".
    """
    assert ab.unlocalised("UK") == (), ab.unlocalised("UK")
    assert ab.unlocalised("US") == (), ab.unlocalised("US")


def test_an_unrenderable_code_is_refused_rather_than_printed_as_its_us_abbreviation():
    """The failure mode that produced the wrong-stitch document, at its source.

    Passing an unknown code through unchanged is precisely what let a UK document print a US
    abbreviation, so the table refuses instead of guessing. This is the check that keeps the
    next stitch someone adds from repeating it.
    """
    from brambleloop.cir import stitches as _st
    try:
        _st.term("no_such_stitch", "UK")
    except KeyError as e:
        assert "UK_TERMS" in str(e), str(e)
    else:
        raise AssertionError("an unknown code was given a UK rendering it does not have")
    # US is the canonical terminology, so a code passes through by definition there.
    assert _st.term("no_such_stitch", "US") == "no_such_stitch"


def test_a_uk_document_that_would_instruct_the_wrong_stitch_is_refused():
    """The guard stays at full strength now that the live gap it was written for is closed.

    Testing it against the real gap would mean the guard stopped being tested the moment the
    writer was fixed -- the check would pass forever by having nothing to catch, which is the
    exact failure this codebase keeps finding elsewhere. So the gap is injected instead: a
    stitch is given a UK rendering the writer cannot produce, and the document must refuse.
    """
    from brambleloop.cir import stitches as _st
    cable = build_cable_throw()

    original = dict(_st.UK_TERMS)
    try:
        _st.UK_TERMS["fpdc"] = "SOMETHING_THE_WRITER_CANNOT_PRINT"
        try:
            build_pattern_pdf(cable, terminology="UK", released_on=RELEASED)
        except ValueError as e:
            assert "fpdc" in str(e) and "UK" in str(e), str(e)
        else:
            raise AssertionError("a UK PDF was rendered containing an unlocalised stitch")
    finally:
        _st.UK_TERMS.clear()
        _st.UK_TERMS.update(original)

    # And with the table honest, the same cable pattern now renders in UK terms rather than
    # being refused -- which is the whole point of having fixed the writer.
    build_pattern_pdf(cable, terminology="UK", released_on=RELEASED)

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


def test_every_place_that_renders_the_customer_pdf_pins_its_date():
    """The half of the fix that decides whether a customer is affected.

    Two handlers render the file the buyer receives: `assets.build`, which records its hash,
    and `store.publish`, which uploads the bytes. Fixing one and not the other would leave
    the recorded hash and the uploaded file disagreeing exactly as before.
    """
    from brambleloop.runtime import pipeline, release

    for module in (release, pipeline):
        source = Path(module.__file__).read_text()
        for number, line in enumerate(source.splitlines(), 1):
            if "build_pattern_pdf(" in line and "def " not in line and "import" not in line:
                window = "\n".join(source.splitlines()[number - 1:number + 3])
                assert "released_on=" in window, (module.__name__, number, line.strip())


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


# ---- 8. both terminologies ship, and the UK one is a UK document ----------


def test_both_terminologies_render_for_every_shippable_design():
    """The claim was live and the file was not.

    The listing title says "US and UK Terms", the description says "in US and in UK
    terminology", the shop FAQ says "Both" and a Pinterest pin says "US and UK terms". Until
    this change `assets.build` rendered `pattern-us.pdf` and nothing else, so every one of
    those was a claim about a file that did not exist.

    Run over every design the pipeline can ship rather than one fixture, because a UK render
    is where terminology defects live and a single-design check would have found none of the
    three that were there.
    """
    for cir in _designs():
        _, twin = _twin_for(cir)
        docs = {t: _doc_for(cir, twin, t) for t in pdf_mod.TERMINOLOGIES}
        assert set(docs) == {"US", "UK"}, sorted(docs)
        for terminology, doc in docs.items():
            assert doc.pages > 1, (cir.slug, terminology)
            assert doc.terminology == terminology
            assert f"{terminology} terms" in _flat(doc), (cir.slug, terminology)
            # Nothing but the crossing-direction gap, which is the CIR's and is reported.
            assert all(p.startswith("PDF_CABLE_DIRECTION_UNSPECIFIED")
                       for p in doc.problems), (cir.slug, terminology, doc.problems)
        # Two files, not one file labelled twice.
        assert docs["US"].pdf_bytes != docs["UK"].pdf_bytes, cir.slug


def test_the_two_documents_are_delivered_under_names_that_tell_them_apart():
    """A buyer with two PDFs in a downloads folder has to be able to tell which is which."""
    assert pdf_mod.pattern_filename("US") == "pattern-us.pdf"
    assert pdf_mod.pattern_filename("UK") == "pattern-uk.pdf"
    try:
        pdf_mod.pattern_filename("AU")
    except ValueError as e:
        assert "not a terminology" in str(e), str(e)
    else:
        raise AssertionError("a terminology this company does not publish was given a filename")


def test_every_place_that_ships_the_customer_pdf_ships_every_terminology():
    """Read off the sources, because a second render site is how one of them ships one file.

    Two handlers put the customer's document in front of a buyer: `assets.build`, which stores
    it and records its hash, and `store.publish`, which uploads it to the listing. Both held
    the literal `pattern-us.pdf`, so either could have gained the UK file without the other.
    Both now loop over `TERMINOLOGIES` and neither names a file directly.

    The same shape as the date-pinning walk below and for the same reason: the defect is the
    *absence* of a call, and no render proves an absence.
    """
    import inspect

    from brambleloop.runtime import pipeline as pipeline_mod
    from brambleloop.runtime import release as release_mod

    for module in (release_mod, pipeline_mod):
        source = inspect.getsource(module)
        # The closing quote is part of the pattern: the literal is what matters, and both
        # modules still describe in a comment what they used to do.
        assert 'pattern-us.pdf"' not in source, (
            module.__name__ + " names the US file directly, so a UK file can be forgotten "
            "in one place and not the other")
        assert "pattern_filename(" in source, module.__name__
        assert "for t in TERMINOLOGIES" in source, module.__name__


def test_a_uk_document_states_its_gauge_in_uk_terms_everywhere_it_states_it():
    """The defect a localised token cannot catch.

    `cir.gauge.stitch_type` is a canonical code, which is a US abbreviation. `cir.writer`
    localises it on the instructions page; `publish.pdf` printed it raw in three other places.
    So a UK document said "16 sts x 18 rows = 10 cm in sc" on its cover and "10cm in dc" on
    page 4 -- one gauge, two stitches, and `sc` is not a UK abbreviation at all, so it is also
    a word that document's own key never defines.

    A UK maker who resolves `sc` against their own vocabulary swatches a treble: three times
    the height the gauge was measured at, and every stated measurement wrong with it.
    """
    for cir in _designs():
        if not cir.gauge:
            continue
        _, twin = _twin_for(cir)
        us_token = ab.token(cir.gauge.stitch_type, "US")
        uk_token = ab.token(cir.gauge.stitch_type, "UK")
        uk = _flat(_doc_for(cir, twin, "UK"))
        gauge_lines = [line for line in uk.split(". ") if "rows = 10" in line]
        assert gauge_lines, cir.slug
        for line in gauge_lines:
            assert ab._contains(line.lower(), uk_token.lower()), (cir.slug, line)
            if us_token.lower() != uk_token.lower():
                assert not ab._contains(line.lower(), us_token.lower()), (cir.slug, line)


def test_the_special_stitch_method_names_its_stitches_in_the_documents_terminology():
    """The same wrong-stitch harm as the terminology defect, arriving through prose.

    Every method paragraph said "double crochet". In UK terms that is the stitch a US pattern
    calls single crochet -- half the height of the one the pattern was compiled against -- so a
    UK document whose token was correctly localised to `fptr` went on, in the paragraph that
    actually teaches the stitch, to tell the maker to finish it as a double crochet. Every post
    stitch at half height, cables that do not stand up, a throw about half its stated length.

    `unlocalised()` cannot see this: it renders ops through the writer, and a method paragraph
    is not an op.
    """
    fpdc_us = ab.method("fpdc", "US")
    fpdc_uk = ab.method("fpdc", "UK")
    assert "double crochet" in fpdc_us and "treble crochet" in fpdc_uk, (fpdc_us, fpdc_uk)
    assert fpdc_us != fpdc_uk, "the method paragraph did not change with the terminology"

    # And in the rendered document, not only in the helper.
    cable = build_cable_throw()
    _, twin = _twin_for(cable)
    uk = _flat(build_pattern_pdf(cable, twin=twin, terminology="UK", released_on=RELEASED))
    us = _flat(build_pattern_pdf(cable, twin=twin, terminology="US", released_on=RELEASED))
    assert " ".join(fpdc_uk.split()) in uk
    assert " ".join(fpdc_us.split()) in us


def test_no_method_paragraph_spells_a_terminology_sensitive_stitch_name_out():
    """The guard, on the templates, because a UK render cannot be checked for this.

    "double crochet" is the US name of `dc` and the UK name of `sc` -- the same eleven
    characters whether it is right or wrong -- so looking for wrong words in a rendered UK
    document cannot distinguish the two. The checkable property is the stronger one: a method
    paragraph names no stitch except through the registry.
    """
    assert ab.method_names_no_stitch_literally() == (), \
        ab.method_names_no_stitch_literally()
    # And the guard fails on the defect it was written for, injected rather than waited for.
    original = dict(ab.METHOD)
    try:
        ab.METHOD["fpdc"] = "Finish as a double crochet."
        assert "fpdc" in ab.method_names_no_stitch_literally()
    finally:
        ab.METHOD.clear()
        ab.METHOD.update(original)


# ---- 9. the key check that could not come out badly -----------------------


def test_the_key_completeness_check_is_measured_on_the_whole_document():
    """It was run on the instruction text against a key derived from the instruction text.

    That is a comparison with one possible answer: `stitch_key(text)` contains every token
    `text` contains, so `undefined_tokens(text)` was empty by construction. The unreachable
    branch carried a `pragma: no cover` saying so, under a docstring calling itself "the
    inverse check, and the one that matters".

    Meanwhile the document sets a cover, a gauge block, a materials list and a finishing
    section that the key has never been shown, and one of them named `sc` in a UK document.
    """
    cir = for_slug("cloudline-baby-blanket")
    result, twin = _twin_for(cir)
    text = write_pattern(cir, result, terminology="US")

    # Given the key that was printed, a token the document contains and the key does not is
    # reported. This is the branch that was unreachable.
    assert ab.undefined_tokens("Gauge: 10 cm in sc", "US", defined={"dc"}) == ["sc"]
    assert ab.undefined_tokens("Gauge: 10 cm in sc", "US", defined={"sc"}) == []
    # And the other terminology's abbreviations count, which is the case the real defect was.
    # `sc` is not a UK rendering of anything, so a UK-only scan had nothing to look for.
    assert ab.undefined_tokens("Gauge: 10 cm in sc", "UK", defined={"dc"}) == ["sc"]
    # A token that only ever appears inside a longer defined one is not undefined: the UK
    # rendering of `inc` is "dc inc", which contains the US rendering "inc".
    assert ab.undefined_tokens("[dc inc in next st] x 6", "UK",
                               defined={"dc", "dc inc"}) == []

    # And the real documents pass it, on their whole prose rather than on one section.
    for design in _designs():
        _, design_twin = _twin_for(design)
        for terminology in pdf_mod.TERMINOLOGIES:
            doc = _doc_for(design, design_twin, terminology)
            assert not any(p.startswith("PDF_ABBREVIATION_UNDEFINED")
                           for p in doc.problems), (design.slug, terminology, doc.problems)
            # The prose the check reads is the document's own words, and there is more of it
            # than the instructions.
            assert len(doc.prose) > len(text), (design.slug, terminology)

    # The document still refuses to be quiet about it if the defect returns: with the gauge
    # line un-localised, a UK render reports the undefined token rather than shipping it.
    original = pdf_mod._gauge_stitch
    try:
        pdf_mod._gauge_stitch = lambda c, t: c.gauge.stitch_type
        broken = build_pattern_pdf(cir, twin=twin, terminology="UK", released_on=RELEASED)
        assert any(p.startswith("PDF_ABBREVIATION_UNDEFINED") and "'sc'" in p
                   for p in broken.problems), broken.problems
    finally:
        pdf_mod._gauge_stitch = original


# ---- 10. one licence, and a check that can see the PDF --------------------


def test_the_licence_in_the_real_pdf_is_the_one_the_company_decided():
    """Requirement 40's check, run against the document instead of against itself.

    `terms.consistency(pdf_text, ...)` was called with `terms.render(terms, "pdf")` -- the
    decision rendered for the PDF surface, not the PDF. So it compared the decision with
    itself on the one surface that had actually diverged, and reported three surfaces
    consistent while the customer's own document granted an unlimited right to sell finished
    items and said nothing about teaching.

    This extracts the text from the rendered PDF and asks the same question of it.
    """
    from brambleloop.commerce import shop_package as package
    from brambleloop.commerce import terms as customer_terms

    cir = for_slug("cloudline-baby-blanket")
    doc = build_pattern_pdf(cir, released_on=RELEASED)
    verdict = customer_terms.consistency(
        _flat(doc), package.policies()["licence"], package.faq_text())
    assert verdict["consistent"] is True, verdict["divergences"]

    # And the check can fail on this surface, which is what it could not do before.
    hand_written = ("This pattern is for your personal use. You may sell finished items you "
                    "make from it.")
    broken = customer_terms.consistency(
        hand_written, package.policies()["licence"], package.faq_text())
    assert broken["consistent"] is False
    assert {d["surface"] for d in broken["divergences"]} == {"pdf"}, broken["divergences"]


def test_no_surface_holds_licence_prose_of_its_own():
    """Four surfaces, one source. Read off the sources, because prose does not announce itself.

    The old copies, in their own words: `commerce.terms` decided "by individual makers and
    small businesses, not manufactured at scale"; `brand.storefront` said "sell the items you
    make from it"; `commerce.seo` said "Sell what you make"; `publish.pdf` said "You may sell
    finished items you make from it". Three of those granted an unlimited commercial licence
    that was never decided.
    """
    import inspect

    from brambleloop.commerce import seo
    from brambleloop.commerce import terms as customer_terms

    decided = customer_terms.BRAMBLELOOP_TERMS.sentence(customer_terms.FINISHED_ITEM_SALE)
    # The constant is gone, not merely unused: a module-level licence paragraph is the thing
    # that gets printed by the next person who needs one.
    assert not hasattr(pdf_mod, "LICENCE"), \
        "publish.pdf holds a licence paragraph of its own again"
    for module in (pdf_mod, seo):
        source = inspect.getsource(module)
        assert "customer_terms" in source or "commerce import terms" in source, module.__name__

    # None of the old wordings reaches a buyer on either surface. Checked on the rendered
    # output rather than the source, because both modules quote the old copies in comments so
    # that the next reader knows what this was for.
    rendered = _flat(build_pattern_pdf(for_slug("cloudline-baby-blanket"),
                                       released_on=RELEASED))
    for phrase in ("sell finished items you make from it", "Sell what you make",
                   "sell the items you make from it"):
        assert phrase not in rendered, phrase
    assert decided in rendered, "the PDF does not state the licence that was decided"

    # The listing description renders it, so the two most-read surfaces say the same thing.
    listing = seo.build_description(
        "Cloudline Baby Blanket", size_label="97 x 97 cm", yardage_lines=[],
        tolerance_pct=20, difficulty="beginner", colors=["cream"], terminology="US",
        gauge_line="16 sts x 18 rows = 10 cm in sc", stitches=["sc", "dc"])
    assert decided in listing, listing


def test_the_support_route_the_terms_promise_is_the_one_the_document_names():
    """A term that names a channel this company does not have.

    The licence block said "questions are answered by email" directly above the PDF's own
    paragraph telling buyers to ask through the shop they bought it from. There is no support
    mailbox; the shop's message thread is the route, and it is the route the document has
    always named. Printing the two side by side is what made it visible.
    """
    from brambleloop.commerce import terms as customer_terms

    sentence = customer_terms.BRAMBLELOOP_TERMS.sentence(customer_terms.SUPPORT_POLICY)
    assert "shop" in sentence and "email" not in sentence, sentence
    rendered = _flat(build_pattern_pdf(for_slug("cloudline-baby-blanket"),
                                       released_on=RELEASED))
    assert sentence in rendered
    assert "tell us through the shop you bought it from" in rendered


# ---- 11. the chart's own text -------------------------------------------


def test_the_chart_reads_the_brand_palette_rather_than_a_second_copy_of_it():
    """The last asset where the brand was not actually locked.

    `brand/bible.py` says "anything that renders an asset reads from here". `publish.charts`
    held six of those hex codes as RGB triples -- which is how a duplicate survives a search
    for the hex string that would have found it. The PDF was corrected on 2026-09-24 and the
    chart inside it was not.
    """
    import inspect

    from brambleloop.publish import charts

    source = inspect.getsource(charts)
    assert "(26, 43, 60)" not in source and "(250, 246, 235)" not in source, \
        "the chart renderer still holds its own copy of the palette"
    for name, value in (("ink", charts.INK), ("pine", charts.PINE), ("cream", charts.CREAM),
                        ("gold", charts.GOLD), ("line", charts.LINE)):
        assert value == bible.rgb255(name), (name, value)


def test_the_charts_own_small_type_clears_the_contrast_floor():
    """Half the type in the document was measured and half was not.

    The PDF darkens its own prose until it clears WCAG AA; the chart and legend images inside
    that same PDF kept the raw palette, and `muted` on `cream` is 4.48:1. Those are the row
    numbers and stitch numbers a maker reads with the work in their hands.
    """
    from brambleloop.publish import charts

    def as_unit(rgb):
        return tuple(c / 255 for c in rgb)

    assert bible.contrast_ratio(as_unit(bible.rgb255("muted")),
                                as_unit(charts.CREAM)) < bible.MIN_TEXT_CONTRAST, \
        "the brand palette now passes on its own; this guard can be simplified"
    assert bible.contrast_ratio(as_unit(charts.MUTED),
                                as_unit(charts.CREAM)) >= bible.MIN_TEXT_CONTRAST
    # One implementation of the rule, not two.
    assert pdf_mod.MIN_CONTRAST == bible.MIN_TEXT_CONTRAST


def test_the_letter_on_a_chart_square_is_legible_on_any_yarn_colour():
    """The accessibility feature failing in the case it exists for.

    `_readable_on` claimed to pick the colour "a human can actually read" and decided from a
    weighted-average lightness against a hand-set threshold of 0.55, which is not a contrast
    measurement and does not have to agree with one. What it draws is the per-colour letter --
    the thing that makes a mosaic chart readable by a maker who cannot tell the yarns apart by
    hue -- and yarn colourways arrive from the CIR as arbitrary hex, so a threshold standing in
    for the measurement will eventually meet the colour it is wrong about. On the brand's own
    `muted` it chose cream at 4.48:1.
    """
    from brambleloop.publish import charts

    for name in bible.PALETTE:
        bg = bible.rgb255(name)
        fg = charts._readable_on(bg)
        ratio = bible.contrast_ratio(tuple(c / 255 for c in fg), tuple(c / 255 for c in bg))
        assert ratio >= bible.MIN_TEXT_CONTRAST, (name, fg, ratio)
    # And on a colourway that is neither brand nor convenient.
    for hexv in ("#808080", "#7F7F7F", "#00FF00", "#FFFF00", "#123456"):
        bg = tuple(int(hexv[i:i + 2], 16) for i in (1, 3, 5))
        fg = charts._readable_on(bg)
        ratio = bible.contrast_ratio(tuple(c / 255 for c in fg), tuple(c / 255 for c in bg))
        assert ratio >= bible.MIN_TEXT_CONTRAST, (hexv, fg, ratio)


def test_the_colour_key_the_document_tells_a_maker_to_use_exists_in_text():
    """The document instructed a maker to rely on a key it had only drawn.

    The chart marks every square with its yarn's letter and the printing note says in so many
    words "follow the letters rather than the shading". The letter-to-yarn mapping existed in
    one place: the rendered legend image -- unsearchable, unselectable, invisible to a screen
    reader, and gone entirely on a reader that dropped the images.

    And the note that says where to look has to match the chart in front of the reader: a round
    chart has no squares, and carries its letter on the round number.
    """
    from brambleloop.publish import charts

    flat = for_slug("cloudline-baby-blanket")
    _, flat_twin = _twin_for(flat)
    rendered = _flat(build_pattern_pdf(flat, twin=flat_twin, released_on=RELEASED))
    assert "Colour key" in rendered
    assert charts.COLOUR_CUE_NOTE_FLAT in rendered
    for name, cue in charts.color_letters(flat).items():
        assert f"{cue} {name}" in rendered, (cue, name, "letter and yarn are not paired")
        assert flat.colors[name] in rendered, name

    round_cir = build_hexagon_coaster()
    _, round_twin = _twin_for(round_cir)
    round_text = _flat(build_pattern_pdf(round_cir, twin=round_twin, released_on=RELEASED))
    assert charts.COLOUR_CUE_NOTE_ROUND in round_text
    assert charts.COLOUR_CUE_NOTE_FLAT not in round_text, \
        "a round chart is being described as a grid of squares"

    # A one-colour pattern gets no colour key, because there is nothing to tell apart.
    plain = build_cable_throw()
    _, plain_twin = _twin_for(plain)
    assert "Colour key" not in _flat(build_pattern_pdf(plain, twin=plain_twin,
                                                       released_on=RELEASED))


def test_the_greyscale_warning_names_the_colours_that_merge():
    """The one sentence in the document nobody has ever read had the arithmetic wrong in it.

    It said "two of these colours are close in lightness" however many pairs merged. No pattern
    in the catalogue fails the greyscale check, so the claim's only sample could not contain the
    broken case -- and on a four-colour pattern where three merge, "two" sends a maker looking
    for a pair that is not the problem.
    """
    from brambleloop.publish import value_stack

    # Nothing in the catalogue triggers it, which is why this is constructed.
    for cir in _designs():
        reading = value_stack.print_safety(cir)
        if reading.get("measurable"):
            assert reading.get("prints") is not False, (cir.slug, reading["weakest_pair"])

    merged = for_slug("cloudline-baby-blanket")
    original = dict(merged.colors)
    try:
        merged.colors.update({name: "#6B7280" for name in original})
        reading = value_stack.print_safety(merged)
        assert reading["prints"] is False, reading
        assert reading["merging_pairs"], reading
        _, twin = _twin_for(merged)
        rendered = _flat(build_pattern_pdf(merged, twin=twin, released_on=RELEASED))
        assert "two of these colours" not in rendered
        for pair in reading["merging_pairs"]:
            assert " / ".join(pair["between"]) in rendered, (pair, "the pair is not named")
    finally:
        merged.colors.clear()
        merged.colors.update(original)


# ---- 12. the chart page ---------------------------------------------------


def test_the_chart_shows_the_repeat_the_written_instructions_use():
    """Two repeat detectors, one fabric, two answers -- and the chart printed the wrong one.

    `charts.detect_repeat` searches for a row period that divides the row count and starts at
    row 1. Eight of the sixteen shippable designs satisfy neither: they open with setup rows and
    then repeat a block whose period is not a divisor of the total. So it answered "the repeat
    is the whole fabric", and the cabled throw's chart page said "this chart shows one repeat:
    8 stitches wide and 121 rows tall" three pages after written instructions saying "Repeat
    rows 2-5 29 more times".

    `cir.rowcycle` is the canonical detector: the written pattern collapses to it and the
    reverse compiler expands it back, which is the property the validation chain rests on. The
    chart asks it rather than keeping a second opinion.
    """
    from brambleloop.cir.rowcycle import detect_cycle
    from brambleloop.publish import charts

    disagreed = []
    for cir in _designs():
        _, twin = _twin_for(cir)
        if len(cir.components) != 1:
            continue
        grid = twin.chart_grid()
        if len(cir.components[0].rows) != len(grid):
            continue
        _, rep_rows = charts.detect_repeat(grid, twin.color_grid())
        cycle = detect_cycle(cir.components[0].rows)
        if cycle and cycle.end < rep_rows:
            disagreed.append(cir.slug)
            assert charts.row_block(cir, twin) == (cycle.start, cycle.end, cycle.repeats)
    assert len(disagreed) >= 6, (
        "the two detectors now agree everywhere, which would make this check vacuous: "
        + str(disagreed))

    # And the caption says the same thing the instructions say, in the same numbers.
    cable = build_cable_throw()
    result, twin = _twin_for(cable)
    art = pdf_mod._chart_art(cable, twin)
    assert "rows 2 to 5 29 times more" in art["caption"], art["caption"]
    assert "Repeat rows 2-5 29 more times" in write_pattern(cable, result), \
        "the written instructions no longer say what the caption was matched against"
    assert "121 rows tall" not in art["caption"]


def test_no_chart_cell_is_smaller_than_the_brand_allows_type_to_be():
    """The chart's type is pixels in an image, so nothing was measuring it.

    The source-level check above holds every `size=` and `setFont` in this module to the brand's
    9pt minimum. The chart's glyphs escaped it entirely: they are drawn into a PNG at some
    pixel size and then scaled by `_Doc.image` to fit the page, so how large they end up is a
    property of neither the renderer nor the document on its own.

    Measured, the cabled throw's chart was 1.9 mm per cell -- a 16 mm wide ribbon down a 216 mm
    page -- and the gate meant to prevent that was `full_cols > 48`, a proxy for legibility that
    the 48-stitch harvest table runner failed by one stitch.
    """
    for cir in _designs():
        _, twin = _twin_for(cir)
        art = pdf_mod._chart_art(cir, twin)
        assert art["problems"] == [], (cir.slug, art["problems"])
        if art["cell_mm"] is not None:
            assert art["cell_mm"] >= pdf_mod.CHART_MIN_CELL_MM, (cir.slug, art["cell_mm"])

    # The floor is the brand's own minimum type size, converted through the ratio the chart
    # renderer sets its glyphs at -- not a number chosen to pass.
    assert pdf_mod.CHART_MIN_CELL_MM == pdf_mod.MIN_BODY_PT / pdf_mod.CHART_GLYPH_RATIO / mm

    # And the check reports rather than passing quietly when a chart cannot be made legible.
    tall = for_slug("cloudline-baby-blanket")
    _, tall_twin = _twin_for(tall)
    original = pdf_mod.CHART_MIN_CELL_MM
    try:
        pdf_mod.CHART_MIN_CELL_MM = 50.0
        art = pdf_mod._chart_art(tall, tall_twin)
        assert any(p.startswith("PDF_CHART_CELL_BELOW_BRAND_MINIMUM")
                   for p in art["problems"]), art["problems"]
        assert "mm on the page" in art["problems"][0]
    finally:
        pdf_mod.CHART_MIN_CELL_MM = original


def test_no_two_stitches_share_a_chart_glyph():
    """One mark, one stitch. `sc` and `cable1x1` were both "x".

    Nothing in the catalogue uses `cable1x1`, so the two had never appeared in one chart and the
    collision was invisible -- a defect whose only sample could not contain it. A chart drawing
    two different stitches with one mark, above a legend listing that mark twice, is a maker
    working the wrong stitch off the chart this product is sold on.
    """
    from brambleloop.publish import charts

    seen: dict[str, str] = {}
    for code, glyph in sorted(charts.GLYPHS.items()):
        assert glyph not in seen, (glyph, seen[glyph], code)
        seen[glyph] = code
    # Every registered stitch has one, so none falls back to the first letter of its code --
    # which drew both post stitches and the bobble as "b" before they were given marks.
    assert set(charts.GLYPHS) == set(stitches.known_codes()), (
        sorted(set(stitches.known_codes()) - set(charts.GLYPHS)))


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
