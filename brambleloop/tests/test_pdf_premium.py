"""The premium customer edition (W4-PDF1): embedded brand faces, truthful pictures, intact text.

Each test pins a property of the *rendered bytes* of the two first customer editions
(hexagon-coaster-set and market-basket-small at their certified releases), not of the layout
code: what a buyer's reader draws, what a text extractor reads, and where every picture came
from.
"""
from __future__ import annotations

import hashlib
import io
import re
import sys
from datetime import date
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from pypdf import PdfReader  # noqa: E402

from brambleloop.brand import bible, pdf_fonts  # noqa: E402
from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.cir.twin import build_twin  # noqa: E402
from brambleloop.cir.writer import write_pattern  # noqa: E402
from brambleloop.products import launch0  # noqa: E402
from brambleloop.publish import abbreviations, charts, construction_diagrams, pdf, tips  # noqa: E402

RELEASED = date(2026, 10, 27)
KEYS = ("hexagon_coasters", "basket_small")


@lru_cache(maxsize=None)
def _doc(key: str, terminology: str = "US", proof: bool = False):
    cir = launch0.cir_for(key)
    return cir, pdf.build_pattern_pdf(cir, terminology=terminology, released_on=RELEASED,
                                      sample_photo_placeholders=proof)


def _flat(doc) -> str:
    return pdf.extracted_text(doc.pdf_bytes)


def test_the_releases_are_the_certified_ones():
    from brambleloop.gates.certificate import certify

    for key, slug in (("hexagon_coasters", "hexagon-coaster-set"),
                      ("basket_small", "market-basket-small")):
        cir = launch0.cir_for(key)
        assert (cir.slug, cir.version) == (slug, "1.2.1"), (cir.slug, cir.version)
        assert certify(cir).granted, slug


def test_every_font_is_embedded_and_none_is_a_base14_substitute():
    for key in KEYS:
        for term in ("US", "UK"):
            _cir, doc = _doc(key, term)
            reader = PdfReader(io.BytesIO(doc.pdf_bytes))
            seen = set()
            for page in reader.pages:
                fonts = (page.get("/Resources") or {}).get("/Font") or {}
                for ref in fonts.values():
                    font = ref.get_object()
                    base = str(font["/BaseFont"])
                    seen.add(base)
                    desc = font.get("/FontDescriptor")
                    assert desc is not None, (key, term, base, "no descriptor: not embedded")
                    desc = desc.get_object()
                    assert "/FontFile2" in desc, (key, term, base, "no embedded font program")
            assert seen and not any("Helvetica" in b for b in seen), seen
            faces = {b.split("+", 1)[-1] for b in seen}
            assert {"Lora-Regular", "CormorantGaramond-SemiBold", "WorkSans-Medium"} <= faces


def test_no_glyph_is_missing_and_no_type_is_below_the_brand_minimum():
    for key in KEYS:
        for term in ("US", "UK"):
            _cir, doc = _doc(key, term)
            assert doc.problems == [], (key, term, doc.problems)
    # The check can fail: an arrow is not in the bundled latin subset.
    d = pdf._Doc("probe")
    d.new_page()
    d.text(pdf.MARGIN, 400, "turn →", pdf.FONT_BODY, 10)
    d.text(pdf.MARGIN, 380, "tiny", pdf.FONT_BODY, 8)
    assert any(p.startswith("PDF_GLYPH_MISSING") and "→" in p for p in d.glyph_problems)
    assert any(p.startswith("PDF_TYPE_BELOW_BRAND_MINIMUM") for p in d.glyph_problems)


def test_the_bundled_faces_are_the_pinned_bytes():
    sums = dict(line.split()[::-1] for line in
                (pdf_fonts.FONT_DIR / "SHA256SUMS").read_text().splitlines() if line.strip())
    for file in pdf_fonts.FACES.values():
        assert hashlib.sha256((pdf_fonts.FONT_DIR / file).read_bytes()).hexdigest() == sums[file]
        assert (pdf_fonts.FONT_DIR.parent / (file.split("-")[0] + "-OFL.txt")).exists(), file


def test_same_inputs_same_bytes():
    for key in KEYS:
        cir = launch0.cir_for(key)
        a = pdf.build_pattern_pdf(cir, released_on=RELEASED).pdf_bytes
        b = pdf.build_pattern_pdf(launch0.cir_for(key), released_on=RELEASED).pdf_bytes
        assert a == b, key


def test_every_written_line_reaches_the_page_unchanged():
    """The layout restyles the writer's lines; it may not reword, drop or split one."""
    for key in KEYS:
        for term in ("US", "UK"):
            cir, doc = _doc(key, term)
            result = compile_cir(cir)
            twin = build_twin(cir, result)
            text = write_pattern(cir, result, terminology=term, width_cm=twin.width_cm,
                                 height_cm=twin.height_cm)
            flat = _flat(doc)
            lines = [ln for ln in text.split("\n")
                     if ln.strip() and not ln.startswith("#") and ln != cir.title]
            assert lines
            for ln in lines:
                assert " ".join(ln.split()) in flat, (key, term, ln)
            # Every round's count is printed, in order.
            counts = re.findall(r"\((\d+) sts\)", text)
            found = re.findall(r"\((\d+) sts\)", flat)
            assert counts and found[:len(counts)] == counts or \
                all(c in found for c in counts), (key, term)


def test_the_coaster_document_says_it_makes_four():
    cir, doc = _doc("hexagon_coasters")
    make = cir.components[0].make
    assert make == 4
    flat = _flat(doc)
    assert f"Makes {make} coasters" in flat
    assert "This pattern makes four hexagonal coasters" in flat
    assert f"for all {make}" in flat


def test_each_edition_states_its_own_terminology():
    for key in KEYS:
        for term in ("US", "UK"):
            _cir, doc = _doc(key, term)
            flat = _flat(doc)
            assert f"Instructions ({term} terms)" in flat
            assert f"Crochet pattern · {term} terms · version {_cir.version}" in flat
            other = "UK" if term == "US" else "US"
            assert f"Instructions ({other} terms)" not in flat


def test_every_picture_is_declared_and_none_is_a_photograph_in_the_sale_edition():
    allowed = {"brand_artwork", "disclosed_render", "construction_diagram", "chart",
               "chart_legend", "schematic"}
    for key in KEYS:
        cir, doc = _doc(key)
        kinds = [f["kind"] for f in doc.figures]
        assert set(kinds) <= allowed, kinds
        assert kinds[0] == "brand_artwork" and kinds[1] == "disclosed_render", kinds
        for f in doc.figures:
            if f["kind"] in ("disclosed_render", "construction_diagram"):
                assert re.fullmatch(r"[0-9a-f]{64}", f["png_sha256"]), f
        # The number of placed images equals the declared figures.
        placed = sum(len(p.images) for p in PdfReader(io.BytesIO(doc.pdf_bytes)).pages)
        assert placed == len(doc.figures), (key, placed, len(doc.figures))
        flat = _flat(doc)
        assert "not a photograph" in flat
        assert "PLACEHOLDER" not in flat
        assert "NOT FOR SALE" not in flat


def test_the_disclosed_renders_are_the_renderers_own_frames():
    from brambleloop.visual import disclosed_render as D

    for key in KEYS:
        cir, doc = _doc(key)
        for f in doc.figures:
            if f["kind"] == "disclosed_render":
                frame = D.render(cir, f["view"])
                assert hashlib.sha256(frame.png).hexdigest() == f["png_sha256"], f


def test_the_proof_variant_is_marked_and_the_sale_edition_is_not():
    _cir, proof = _doc("basket_small", "US", True)
    flat = _flat(proof)
    assert "NOT FOR SALE" in flat and "PLACEHOLDER" in flat
    assert any(f["kind"] == "photo_placeholder" for f in proof.figures)


def test_physical_status_is_stated_as_unverified_without_evidence():
    for key in KEYS:
        cir, doc = _doc(key)
        twin = build_twin(cir, compile_cir(cir))
        assert not twin.calibrated
        flat = _flat(doc)
        assert "physical testing: unverified in this edition" in flat.lower()
        assert "computed, not yet measured on a worked sample" in flat
        # Never a fixed claim about the world outside the edition.
        assert "no sample has been photographed" not in flat
        assert "none exists" not in flat


def test_stage_diagrams_match_the_written_counts():
    for key in KEYS:
        cir = launch0.cir_for(key)
        result = compile_cir(cir)
        twin = build_twin(cir, result)
        text = write_pattern(cir, result, terminology="US", width_cm=twin.width_cm,
                             height_cm=twin.height_cm)
        written = {int(n): int(c) for n, c in
                   re.findall(r"^Rnd (\d+) \([^)]*\):.*\((\d+) sts\)$", text, re.M)}
        stages = construction_diagrams.stages(cir)
        assert stages and stages[-1].round == max(written), key
        covered = []
        for st in stages:
            assert st.stitches == written[st.round], (key, st.round)
            covered += list(range(st.first, st.round + 1))
        assert covered == sorted(written), (key, "every round is in exactly one card")
        _cir, doc = _doc(key)
        diagrams = [f for f in doc.figures if f["kind"] == "construction_diagram"]
        assert [f["round"] for f in diagrams] == [st.round for st in stages]


def test_tips_are_triggered_by_the_pattern_and_quote_its_numbers():
    cir = launch0.cir_for("basket_small")
    result = compile_cir(cir)
    twin = build_twin(cir, result)
    text = write_pattern(cir, result, terminology="US")
    got = {t.title: t for t in tips.tips(cir, result, twin, text, "US")}
    assert "Turning the base into the wall" in got
    assert "Rnd 11 is the first round with no increases" in got[
        "Turning the base into the wall"].text
    assert "Making a matching set" not in got          # one basket
    assert "from 6 sts at Rnd 1 to 60 sts at Rnd 22" in got["Count every round"].text
    coaster = launch0.cir_for("hexagon_coasters")
    r2 = compile_cir(coaster)
    t2 = build_twin(coaster, r2)
    got2 = {t.title for t in tips.tips(coaster, r2, t2, write_pattern(coaster, r2, "US"), "US")}
    assert "Making a matching set" in got2
    assert "Turning the base into the wall" not in got2


def test_technique_notes_name_no_stitch_literally_and_localise():
    assert abbreviations.method_names_no_stitch_literally() == ()
    cir = launch0.cir_for("hexagon_coasters")
    result = compile_cir(cir)
    uk = {e.token: e.means for e in abbreviations.techniques(
        write_pattern(cir, result, "UK"), "UK")}
    us = {e.token: e.means for e in abbreviations.techniques(
        write_pattern(cir, result, "US"), "US")}
    assert "single crochet" in us["increase"] and "double crochet" in uk["increase"]
    assert set(us) == set(uk) == {"magic ring", "joining a round", "changing colour at a join",
                                  "increase", "fastening off"}


def test_the_chart_legend_speaks_the_documents_terminology():
    """A UK edition's legend keys `dc inc`, as its instructions do, not `inc (UK ...)`."""
    cir = launch0.cir_for("hexagon_coasters")
    twin = build_twin(cir, compile_cir(cir))
    art = pdf._chart_art(cir, twin)
    kw = dict(marks=art["marks"], colours=art["charted_colours"], lettered=bool(art["cues"]))
    uk = charts.render_legend(cir, twin, terminology="UK", **kw)
    us = charts.render_legend(cir, twin, terminology="US", **kw)
    bilingual = charts.render_legend(cir, twin)
    assert uk.tobytes() != us.tobytes() != bilingual.tobytes()
    _cir, doc = _doc("hexagon_coasters", "UK")
    reader = PdfReader(io.BytesIO(doc.pdf_bytes))
    legend_page = next(f["page"] for f in doc.figures if f["kind"] == "chart_legend")
    images = reader.pages[legend_page - 1].images
    assert any(im.image.convert("RGB").tobytes() == uk.convert("RGB").tobytes()
               for im in images), "the UK document does not carry the UK legend"


def test_the_1_2_1_text_fixes_reach_the_documents():
    """F1, F2, F3, N3 and the colour-change wording, read off the rendered bytes."""
    coaster = _flat(_doc("hexagon_coasters")[1])
    basket = _flat(_doc("basket_small")[1])
    for flat in (coaster, basket):
        assert "The ch 1 does not count as a stitch." in flat                     # F3
        assert "an end to secure at every join" not in flat                      # F2
        assert "all 2 changes" not in flat and "all 4 changes" not in flat
    assert "Cut wine after Rnd 6 and fasten it off" in coaster
    assert "Ends to weave in: about 4 on each coaster." in coaster
    assert "up the inside" not in coaster          # a flat coaster has no inside
    assert "Cut wine after Rnd 19 and fasten it off" in basket
    assert "up the inside of the join" in basket
    assert "plus 15%" not in coaster               # F1: no substitution metres printed
    assert "1 x 100g ball)" in basket and "1-1 x" not in basket                 # N3
    assert basket.index("if you use light".upper()) < basket.index("plus 15%")
    assert "turn the basket so the line sits at the back" in basket            # N6
    assert "[ ... ] x 6" in coaster and "(42 sts)" in coaster                   # F8
    assert "(120 sts)" not in coaster and "(60 sts) the stitch count" in basket


def test_every_proof_page_says_not_for_sale_and_the_cover_has_no_tagline_lockup():
    _cir, proof = _doc("basket_small", "US", True)
    for n, page in enumerate(PdfReader(io.BytesIO(proof.pdf_bytes)).pages, 1):
        assert "NOT FOR SALE" in (page.extract_text() or ""), n                 # F9
    for key in KEYS:
        _cir, doc = _doc(key)
        cover = doc.figures[0]
        assert cover["kind"] == "brand_artwork" and "lockup_horizontal" in cover["source"]


def test_the_basket_key_lists_only_what_its_chart_draws():
    """N2/F4: rounds 1-10 are all cream and carry no letters, so the key has no wine and no
    letter note; the round chart draws V only, so no 'x' for sc."""
    cir, doc = _doc("basket_small")
    twin = build_twin(cir, compile_cir(cir))
    art = pdf._chart_art(cir, twin)
    assert art["charted_colours"] == ["cream"] and art["marks"] == ["inc"]
    assert not art["cues"]
    expected = charts.render_legend(cir, twin, terminology="US", marks=art["marks"],
                                    colours=art["charted_colours"], lettered=False)
    page = next(f["page"] for f in doc.figures if f["kind"] == "chart_legend")
    images = PdfReader(io.BytesIO(doc.pdf_bytes)).pages[page - 1].images
    assert any(im.image.convert("RGB").tobytes() == expected.convert("RGB").tobytes()
               for im in images)


def test_text_and_graphics_clear_their_contrast_floors():
    for fg, bg in ((pdf.INK, pdf.PAPER), (pdf.MUTED, pdf.PAPER), (pdf.ACCENT, pdf.PAPER),
                   (pdf.TAUPE, pdf.PAPER), (pdf.INK, pdf.SURFACE), (pdf.MUTED, pdf.SURFACE),
                   (pdf.TAUPE, pdf.SURFACE), (pdf.ACCENT, pdf.SURFACE),
                   (pdf.GOLD_ON_PINE, pdf.FOREST), (pdf.PAPER_ON_FOREST, pdf.FOREST)):
        assert pdf.contrast(fg, bg) >= pdf.MIN_CONTRAST, (fg, bg, pdf.contrast(fg, bg))
    as_unit = lambda rgb: tuple(c / 255 for c in rgb)  # noqa: E731
    assert bible.contrast_ratio(as_unit(charts.GRID), as_unit(charts.CREAM)) >= 3.0



def test_the_basket_does_not_promise_a_crease_its_instructions_do_not_make():
    """W4-CONSTRUCTREVIEW-basket F2/F3/F4: a both-loops first wall round makes a soft fold.

    No "rise straight up", no Rnd 11 height blamed on gauge, the height as a range that does
    not overstate the twin's upper bound, and every render captioned as idealised. The coaster
    (no wall) and a crisp back-loop fold keep the plain wording."""
    from brambleloop.publish import value_stack

    basket = _flat(_doc("basket_small")[1])
    assert "rise straight up" not in basket
    assert "turning upward over the first few rounds and then rising straight" in basket
    assert "the edge of the base beginning to turn up" in basket
    assert "judge the height from round 14 on" in basket
    assert "8.7 cm tall" not in basket and "about 8 to 9 cm tall" in basket
    assert "Idealised digital rendering" in basket
    assert basket.count("These pictures are idealised") >= 3       # about box, schematic, gallery
    coaster = _flat(_doc("hexagon_coasters")[1])
    assert "idealised" not in coaster.lower()

    cir = launch0.cir_for("basket_small")
    twin = build_twin(cir, compile_cir(cir))
    fold = value_stack.soft_fold(cir, twin)
    assert fold and fold["first_wall"] == 11 and fold["settled"] == 14
    assert fold["high_cm"] == twin.height_cm and fold["low_cm"] < fold["high_cm"]
    # Injected crisp fold: Rnd 11 through the back loop is the fold the twin models.
    for c in twin.cells:
        if c.row == 11:
            c.loop = "back"
    assert value_stack.soft_fold(cir, twin) is None
    assert value_stack.height_words(7.975, 8.7) == "about 8 to 9 cm"
    assert value_stack.height_words(3.625, 4.35) == "about 4 cm"


def test_every_round_chart_increase_mark_reads_on_its_own_cell():
    """SECREVIEW-PDF1 M1: the coaster's Rnd 6 "V" marks were ink on wine, 1.3:1.

    Every mark the round chart draws is paired with the colour of the cell it sits on (the
    renderer asks `_readable_on` for that cell immediately before drawing it) and must reach
    the 4.5:1 text floor. A renderer that goes back to one fixed ink stops asking, the pairing
    breaks, and this fails -- as it does on the injected defect below."""
    from PIL import ImageDraw

    marks = set(charts.GLYPHS[c] for c in charts.ROUND_MARKED_CODES)

    def measure(key):
        cir = launch0.cir_for(key)
        twin = build_twin(cir, compile_cir(cir))
        seen, pending, in_key = [], [], [False]
        real_readable, real_text = charts._readable_on, ImageDraw.ImageDraw.text
        real_legend = charts.render_legend

        def legend(*a, **k):                # the key draws its sample mark on cream; not a cell
            in_key[0] = True
            try:
                return real_legend(*a, **k)
            finally:
                in_key[0] = False

        def readable(bg):
            out = real_readable(bg)
            pending.append((out, bg))
            return out

        def text(self, xy, t, *a, **k):
            if (t in marks and not in_key[0] and k.get("anchor") == "mm"
                    and k.get("stroke_width") is None):
                fill = k.get("fill")
                bg = next((b for f, b in reversed(pending) if f == fill), None)
                seen.append((fill, bg))
            pending.clear()
            return real_text(self, xy, t, *a, **k)

        charts._readable_on, ImageDraw.ImageDraw.text = readable, text
        charts.render_legend = pdf.render_legend = legend
        try:
            pdf._chart_art(cir, twin)
        finally:
            charts._readable_on, ImageDraw.ImageDraw.text = real_readable, real_text
            charts.render_legend = pdf.render_legend = real_legend
        return seen

    norm = lambda c: tuple(v / 255 for v in c)  # noqa: E731
    for key in KEYS:
        seen = measure(key)
        assert seen, key
        for fill, bg in seen:
            assert bg is not None, (key, fill)
            assert bible.contrast_ratio(norm(fill), norm(bg)) >= 4.5, (key, fill, bg)
    coaster_bgs = {bg for _f, bg in measure("hexagon_coasters")}
    assert len(coaster_bgs) >= 2       # cream rounds and the wine Rnd 6 both carry marks

    original = charts._readable_on
    try:
        charts._readable_on = lambda bg: charts.INK      # the shipped 1.2.1 defect
        injected = measure("hexagon_coasters")
        assert any(bible.contrast_ratio(norm(f), norm(b)) < 4.5 for f, b in injected if b)
    finally:
        charts._readable_on = original


def test_the_soft_fold_disclosure_fails_closed():
    """SECREVIEW-PDF1 L1: if the fold cannot be derived the basket document is refused."""
    from brambleloop.publish import value_stack

    original = value_stack.soft_fold
    try:
        def broken(cir, twin):
            raise RuntimeError("injected")
        value_stack.soft_fold = broken
        try:
            cir = launch0.cir_for("basket_small")
            pdf._fold(cir, build_twin(cir, compile_cir(cir)))
        except pdf.FoldDisclosureRefused:
            pass
        else:
            raise AssertionError("a broken soft_fold was swallowed")
    finally:
        value_stack.soft_fold = original


def test_the_chart_font_is_sha_pinned():
    """SECREVIEW-PDF1 L2: the PIL chart face is loaded through the same pin as the PDF."""
    path = pdf_fonts.verified_path("WorkSans-Medium.ttf")
    assert path.name == "WorkSans-Medium.ttf"
    sums = pdf_fonts._pinned()
    pdf_fonts.verified_path.cache_clear()
    real = pdf_fonts._pinned
    try:
        pdf_fonts._pinned = lambda: {**sums, "WorkSans-Medium.ttf": "0" * 64}
        try:
            pdf_fonts.verified_path("WorkSans-Medium.ttf")
        except pdf_fonts.FontIntegrityError:
            pass
        else:
            raise AssertionError("a face off its pin was loaded")
    finally:
        pdf_fonts._pinned = real
        pdf_fonts.verified_path.cache_clear()

if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc()
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
