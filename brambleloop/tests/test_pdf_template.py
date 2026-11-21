"""The owner's master pattern template (D-OWNER-PDF-TEMPLATE; ENG-PDF-TEMPLATE).

Every assertion is about the BUILT bytes (`pdf_template.audit` reads them with pypdf) or about
a refusal: the page sequence, the canonical logo on the cover / every header / the thank-you
block, the seven certified gallery renditions, no template placeholder or marker, a stitch
count on every row, the family section variants, and the blocking rules (a missing required
fact or an incomplete gallery never yields a customer PDF).

Gallery images here are test doubles (`pdf_template.test_double_gallery`): a document built
with them is `proof_test_double`, marked NOT CUSTOMER-READY on every page.
"""
from __future__ import annotations

import dataclasses
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

from brambleloop.brand import bible  # noqa: E402
from brambleloop.intel import childrens as ch  # noqa: E402
from brambleloop.products import launch0  # noqa: E402
from brambleloop.publish import pdf as P  # noqa: E402
from brambleloop.publish import pdf_template as T  # noqa: E402

RELEASED = date(2026, 11, 20)


@lru_cache(maxsize=None)
def _cir(key: str):
    if key.startswith("garment:"):
        from brambleloop.products import garments as G

        _g, design, size = key.split(":")
        return G.DESIGNS[design]().build_all()[size]
    if key == "pillow":
        from brambleloop.products import texture

        return texture.build_bobble_pillow()
    return launch0.cir_for(key)


@lru_cache(maxsize=None)
def _gallery():
    return tuple(T.test_double_gallery())


@lru_cache(maxsize=None)
def _doc(key: str, terminology: str = "US", family: str | None = None):
    return T.build_template_pdf(_cir(key), terminology=terminology, released_on=RELEASED,
                                gallery=list(_gallery()), family=family)


def _text(doc) -> str:
    return "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(doc.pdf_bytes)).pages)


def _flat(doc) -> str:
    return re.sub(r"\s+", " ", _text(doc))


def _audit_passes(doc):
    a = T.audit(doc.pdf_bytes, expected_gallery=doc.gallery)
    assert a["verdict"] == "PASS", [c for c in a["checks"] if c["status"] != "PASS"]
    return a


# ---- the template itself -------------------------------------------------------------------

def test_the_template_is_the_owners_14_page_letter_master():
    reader = PdfReader(str(ROOT / T.TEMPLATE_PATH))
    assert len(reader.pages) == 14
    box = reader.pages[0].mediabox
    assert (float(box.width), float(box.height)) == (612.0, 792.0)
    # 13 sections, cover first, the gallery split over two pages, as the template draws them,
    # then the CIR-generated techniques appendix after them (ENG-PDF-DIAGRAMS)
    assert T.SECTION_ORDER[0] == "cover" and len(T.SECTION_ORDER) == 14
    assert T.SECTION_ORDER[12] == "copyright" and T.SECTION_ORDER[13] == "appendix"
    assert [label for _s, label in T.GALLERY_SLOTS] == [
        "FULL PRODUCT / HERO", "STITCH DETAIL", "LIFESTYLE", "BACK / ALTERNATE VIEW",
        "SCALE / FIT", "CONSTRUCTION / MATERIALS", "DOWNLOAD FACTS"]
    # the placeholders the audit forbids are read from the template, not typed here
    ph = T.template_placeholders()
    assert "[X sts]" in ph and "[COLLECTION NAME]" in ph and "[Skill level]" in ph


def test_the_template_faces_are_embedded_and_pinned():
    from brambleloop.brand import pdf_fonts

    for name in (T.SERIF, T.SERIF_SEMI, T.SANS, T.SANS_SEMI, T.SANS_BOLD):
        assert name in pdf_fonts.FACES
        pdf_fonts.verified_path(pdf_fonts.FACES[name])
    doc = _doc("hexagon_coasters")
    fonts = set()
    for page in PdfReader(io.BytesIO(doc.pdf_bytes)).pages:
        for f in ((page.get("/Resources") or {}).get("/Font") or {}).values():
            fonts.add(str(f.get_object().get("/BaseFont")).split("+")[-1])
    assert {"Lato-Regular", "Lato-Bold", "NotoSerifDisplay-Regular"} <= fonts, fonts


# ---- home décor (coasters), US and UK: the full audit --------------------------------------

def test_home_decor_us_and_uk_pass_the_audit_and_are_not_customer_ready_with_test_doubles():
    for term in ("US", "UK"):
        doc = _doc("hexagon_coasters", term)
        assert doc.family == T.HOME
        a = _audit_passes(doc)
        assert a["sections"][0] == "meet_the_pattern"
        assert doc.status == "proof_test_double" and not doc.customer_ready
        text = _flat(doc)
        assert T.TEST_DOUBLE_MARKER.split("  ")[0] in text
        assert f"{term} TERMINOLOGY" in text
        # the only premium-standard finding a test-double proof may carry: its hero is
        # labelled TEST DOUBLE, not as a rendering or photograph (a real gallery clears it)
        assert doc.rows == 7 and doc.problems == [
            "PREMIUM_STANDARD cover: the cover hero is labelled neither as a rendering nor "
            "as a photograph"], doc.problems
    uk = _flat(_doc("hexagon_coasters", "UK"))
    us = _flat(_doc("hexagon_coasters", "US"))
    assert "in dc" in uk and "in sc" in us      # the gauge stitch, in each edition's terms


def test_every_body_page_has_the_template_header_footer_and_logo():
    doc = _doc("hexagon_coasters")
    reader = PdfReader(io.BytesIO(doc.pdf_bytes))
    for n, page in enumerate(reader.pages[1:], start=2):
        t = re.sub(r"\s+", " ", page.extract_text() or "")
        assert "BRAMBLELOOP" in t and "CROCHET PATTERNS" in t, n
        assert "BRAMBLELOOP STUDIO / PATTERNS FOR A MORE HANDMADE LIFE" in t, n
        assert f"{n:02d}" in t, n
        assert "HEXAGON COASTER SET" in t, n
    assert doc.logo_pages == list(range(1, doc.pages + 1))


def test_no_placeholder_bracket_or_template_marker_reaches_the_document():
    for key in ("hexagon_coasters", "cloudline_blanket"):
        text = _flat(_doc(key))
        assert "MASTER LAYOUT" not in text and "REQUIRES CERTIFIED PRODUCT DATA" not in text
        assert "ILLUSTRATIVE SLOT" not in text
        assert T.template_placeholders(), "the template's placeholder list was not read"
        for ph in T.template_placeholders():
            assert ph not in text, ph
        # the only brackets printed are crochet repeat notation: "[...] x N"
        for m in re.finditer(r"\[[^\]]*\]", text):
            tail = text[m.end():m.end() + 6]
            assert re.match(r"\s*x\s*\d", tail) or m.group(0) == "[ ... ]", (m.group(0), tail)


def test_the_audit_fails_what_it_should():
    # a text-only proof has no gallery: the audit FAILs it (UNKNOWN is never PASS either)
    proof = T.build_template_pdf(_cir("hexagon_coasters"), released_on=RELEASED, proof=True)
    a = T.audit(proof.pdf_bytes)
    assert a["verdict"] == "FAIL" and "gallery" in a["failed"]
    assert T.audit(b"not a pdf")["verdict"] == "UNKNOWN"
    # a placeholder and the marker are caught when present
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(72, 700, "Row 1: [X sts]")
    c.drawString(72, 680, T.TEMPLATE_MARKER.replace("•", "-"))
    c.save()
    a = T.audit(buf.getvalue())
    assert {"no_placeholders", "no_template_marker", "page_order", "logo_cover"} <= set(
        a["failed"]), a["failed"]


def test_deterministic_bytes():
    cir = _cir("hexagon_coasters")
    one = T.build_template_pdf(cir, terminology="US", released_on=RELEASED,
                               gallery=list(_gallery()))
    two = T.build_template_pdf(cir, terminology="US", released_on=RELEASED,
                               gallery=list(_gallery()))
    assert hashlib.sha256(one.pdf_bytes).digest() == hashlib.sha256(two.pdf_bytes).digest()


# ---- the gallery ----------------------------------------------------------------------------

def test_the_seven_slots_are_the_certified_renditions_in_certificate_order():
    from brambleloop.publish import pdf_photos as PP

    doc = _doc("hexagon_coasters")
    assert [g["position"] for g in doc.gallery] == list(range(1, 8))
    frames = {f["position"]: f for f in _gallery()}
    for g in doc.gallery:
        f = frames[g["position"]]
        assert g["frame_sha256"] == f["sha256"]
        # the same bytes the sale-pipeline checker proves: pdf_photos.rendition of the frame
        assert g["rendition_sha256"] == hashlib.sha256(PP.rendition(f["data"])).hexdigest()
    pages = {g["page"] for g in doc.gallery}
    assert len(pages) == 2                              # gallery + continued gallery
    # the cover hero is slot 1's rendition
    cover = [f for f in doc.figures if f.get("slot") == "cover_hero"]
    assert cover and cover[0]["rendition_sha256"] == doc.gallery[0]["rendition_sha256"]
    # every image is labelled: a test double says so
    assert _flat(doc).count("TEST DOUBLE / NOT A PRODUCT IMAGE") >= 8


def test_no_complete_certified_gallery_is_awaiting_gallery_never_a_pdf_with_empty_slots():
    cir = _cir("hexagon_coasters")
    for gallery in (None, list(_gallery())[:6],
                    [dict(f, data=f["data"] + b"x") if f["position"] == 3 else f
                     for f in _gallery()]):
        try:
            T.build_template_pdf(cir, released_on=RELEASED, gallery=gallery)
        except T.GalleryAwaiting as e:
            assert "awaiting gallery" in str(e)
        else:
            raise AssertionError("a template PDF was built without a complete gallery")


def test_a_text_only_proof_is_marked_not_customer_ready_on_every_page():
    doc = T.build_template_pdf(_cir("hexagon_coasters"), released_on=RELEASED, proof=True)
    assert doc.status == "proof_text_only" and not doc.customer_ready and not doc.gallery
    for page in PdfReader(io.BytesIO(doc.pdf_bytes)).pages:
        assert "NOT CUSTOMER-READY" in re.sub(r"\s+", " ", page.extract_text() or "")


def test_certified_non_test_double_frames_make_a_customer_ready_document_with_no_marker():
    frames = [dict(f, test_double=False, kind="generated") for f in _gallery()]
    doc = T.build_template_pdf(_cir("hexagon_coasters"), released_on=RELEASED, gallery=frames)
    assert doc.status == "customer_ready" and doc.customer_ready
    text = _flat(doc)
    assert "NOT CUSTOMER-READY" not in text
    # generated images are labelled as renderings
    assert text.count("DIGITAL RENDERING / NOT A PHOTOGRAPH") >= 8
    assert T.GALLERY_DISCLOSURE.split(":")[0] in text


# ---- content rules --------------------------------------------------------------------------

def test_every_row_and_round_carries_its_stitch_count():
    for key in ("hexagon_coasters", "cloudline_blanket", "garment:harbour-drop-shoulder-pullover:M"):
        doc = _doc(key)
        a = _audit_passes(doc)
        counts = next(c for c in a["checks"] if c["check"] == "stitch_counts")
        assert counts["rows"] == doc.rows > 0, (key, counts, doc.rows)


def test_a_row_without_a_count_blocks_the_build_with_a_named_reason():
    real = T.write_pattern

    def drop(*a, **k):
        return real(*a, **k).replace("(18 sts)", "", 1)

    T.write_pattern = drop
    try:
        T.build_template_pdf(_cir("hexagon_coasters"), released_on=RELEASED,
                             gallery=list(_gallery()))
    except T.TemplateBlocked as e:
        assert "Rnd 3" in str(e) and "no stitch count" in str(e) and e.section == "pattern"
    else:
        raise AssertionError("a row without its count was printed")
    finally:
        T.write_pattern = real


def test_a_missing_required_fact_blocks_the_build_never_a_placeholder():
    from brambleloop.cir.compiler import compile_cir
    from brambleloop.cir.twin import build_twin

    cir = _cir("hexagon_coasters")
    twin = build_twin(cir, compile_cir(cir))
    for broken, word in ((dataclasses.replace(twin, yarn_metres_by_color={}), "yarn"),
                         (dataclasses.replace(twin, width_cm=None), "finished size")):
        try:
            T.build_template_pdf(cir, twin=broken, released_on=RELEASED,
                                 gallery=list(_gallery()))
        except T.TemplateBlocked as e:
            assert word in e.reason, e
        else:
            raise AssertionError(f"built without {word}")


def test_the_licence_is_brambleloops_own_and_support_is_etsy_messages_only():
    text = _flat(_doc("hexagon_coasters"))
    assert P.licence_paragraphs()
    for para in P.licence_paragraphs():
        para = para[2:] if para.startswith("- ") else para
        if para.strip():
            assert re.sub(r"\s+", " ", para)[:60] in text, para
    assert "Etsy Messages" in text and "only support channel" in text
    assert "http" not in text.split("The small print, clearly")[-1].split("Source:")[0]


def test_no_type_below_the_brand_minimum_in_the_template_source_or_render():
    source = Path(T.__file__).read_text()
    minimum = bible.TYPOGRAPHY["min_body_pt"]
    offenders = []
    for n, line in enumerate(source.splitlines(), 1):
        for m in re.finditer(r"\b(?:SANS|SERIF)[A-Z_]*,\s*(\d+(?:\.\d+)?)\b", line):
            if float(m.group(1)) < minimum:
                offenders.append((n, line.strip()))
        for m in re.finditer(r"\bsize=(\d+(?:\.\d+)?)\b", line):
            if float(m.group(1)) < minimum:
                offenders.append((n, line.strip()))
    assert not offenders, offenders
    for key in ("hexagon_coasters", "cloudline_blanket"):
        assert not [p for p in _doc(key).problems if "BELOW_BRAND_MINIMUM" in p]


def test_text_colours_clear_the_brand_contrast_floor():
    for fg, bg in ((T.ROSE, T.PAPER), (T.ROSE_ON_CREAM, T.CREAM), (T.BROWN, T.PAPER),
                   (T.BROWN_ON_CREAM, T.CREAM), (T.GREY, T.CREAM), (T.INK, T.PAPER),
                   (T.INK, T.CREAM), (T.INK, T.SAGE), (T.ON_FOREST, T.FOREST)):
        assert P.contrast(fg, bg) >= P.MIN_CONTRAST, (fg, bg, P.contrast(fg, bg))


# ---- families -------------------------------------------------------------------------------

def test_family_garment_has_the_size_table_and_fit_and_ease():
    doc = _doc("garment:harbour-drop-shoulder-pullover:M")
    assert doc.family == T.GARMENT
    _audit_passes(doc)
    text = _flat(doc)
    assert "FIT + EASE" in text and "Intended fit: relaxed" in text
    cir = _cir("garment:harbour-drop-shoulder-pullover:M")
    assert cir.grading.sizes
    for e in cir.grading.sizes:
        assert f"chest {e['built_cm']['chest']:g} cm" in text, e["size"]
    assert "this edition" in text


def test_family_baby_carries_the_child_safety_gates_text():
    doc = _doc("cloudline_blanket")
    assert doc.family == T.BABY
    _audit_passes(doc)
    text = _flat(doc)
    assert "SAFETY / AGE / USE NOTES" in text
    audit = P.childrens_statements_in(doc.pdf_bytes, ("baby_blanket", ch.UNDER_3))
    assert audit["complete"], audit


def test_family_amigurumi_needs_the_child_safety_gate_or_it_blocks():
    from brambleloop.cir.model import Material
    from tests import fixtures

    sphere = fixtures.good_sphere()
    sphere.materials = [Material(name="worsted cotton", yarn_weight="worsted",
                                 color_id="cream")]
    assert T.template_family(sphere, ("amigurumi_toy", ch.UNDER_3)) == T.AMIGURUMI
    # without the gate's assignment an amigurumi document is never produced
    try:
        T.build_template_pdf(_cir("hexagon_coasters"), released_on=RELEASED,
                             gallery=list(_gallery()), family=T.AMIGURUMI)
    except T.TemplateBlocked as e:
        assert "child-safety" in e.reason
    else:
        raise AssertionError("an amigurumi PDF without child-safety text")
    # with it, a closed stuffed form states the circumference its twin derives (ENG-PLUSH,
    # base) in the child-safety text: the size is printed, never left empty
    doc = T.build_template_pdf(sphere, childrens=("amigurumi_toy", ch.UNDER_3),
                               released_on=RELEASED, gallery=list(_gallery()))
    text = P.extracted_text(doc.pdf_bytes)
    assert "intended for children under 3" in text, text[:400]
    assert "around its widest round" in text and "finishing at  at" not in text


def test_family_pillow_has_its_cover_variant():
    doc = _doc("pillow")
    assert doc.family == T.PILLOW
    _audit_passes(doc)
    assert "FINISHED COVER" in _flat(doc) and "PILLOWS + CUSHIONS" in _flat(doc)


def test_family_blanket_has_its_drape_variant_and_chart():
    doc = _doc("snowfall_throw")
    assert doc.family == T.BLANKET
    _audit_passes(doc)
    text = _flat(doc)
    assert "FINISHED SIZE + DRAPE" in text and "CHART" in text
    assert any(f["kind"] == "chart" for f in doc.figures)


def test_family_home_decor_is_concise_and_complete():
    doc = _doc("hexagon_coasters")
    text = _flat(doc)
    assert "HOME DÉCOR" in text and "FINISHED SIZE + USE" in text
    assert "SAFETY / AGE / USE NOTES" not in text      # no safety block it has no reason for


def test_family_colourwork_has_its_variant_and_chart():
    doc = _doc("placemat_pair", family=T.COLOURWORK)
    assert doc.family == T.COLOURWORK
    _audit_passes(doc)
    text = _flat(doc)
    assert "FINISHED SIZE + COLOURWORK" in text and "COLOURWORK / DIGITAL DOWNLOAD" in text
    assert any(f["kind"] == "chart" for f in doc.figures)


def test_inline_diagrams_and_progress_slot_sit_at_the_tricky_steps():
    rounds = _doc("hexagon_coasters")
    assert [f for f in rounds.figures if f["kind"] == "construction_diagram"]
    rows = _doc("cloudline_blanket")
    assert [f for f in rows.figures if f["kind"] == "mini_diagram"]
    # two pieces (front, back): the twin draws the front, so its diagram sits only there
    pillow = _doc("pillow")
    assert len([f for f in pillow.figures if f["kind"] == "mini_diagram"]) == 1
    for doc in (rounds, rows, pillow):
        prog = [f for f in doc.figures if f.get("slot") == "progress"]
        assert len(prog) == 1
        assert prog[0]["rendition_sha256"] == doc.gallery[5]["rendition_sha256"]


# ---- the build switch -----------------------------------------------------------------------

def test_the_layout_switch():
    from brambleloop.runtime import release

    assert release.PDF_LAYOUT in ("engine", "template")
    cir = _cir("hexagon_coasters")
    eng = T.build_customer_pdf(cir, layout="engine", released_on=RELEASED)
    assert isinstance(eng, P.PatternDocument)
    tpl = T.build_customer_pdf(cir, layout="template", released_on=RELEASED,
                               gallery=list(_gallery()))
    assert isinstance(tpl, T.TemplateDocument) and tpl.layout == "template"
    try:
        T.build_customer_pdf(cir, layout="template", released_on=RELEASED)
    except T.GalleryAwaiting:
        pass
    else:
        raise AssertionError("the template built without a gallery")
    try:
        T.build_customer_pdf(cir, layout="bogus")
    except ValueError:
        pass
    else:
        raise AssertionError("an unknown layout was accepted")


# ---- amigurumi variant (teardown lessons: TEARDOWN_HIGHLAND_COW_AMIGURUMI, _CAPYBARA) ------

def _ami():
    sys.path.insert(0, str(ROOT / "tests"))
    import fixture_amigurumi as F

    return F


def test_the_amigurumi_hook_range_is_the_stated_hook_and_half_a_millimetre_below():
    assert T.hook_range(4.0) == (3.5, 4.0)
    assert T.hook_range(5.0) == (4.5, 5.0)
    lo, hi = T.hook_range(2.0)
    assert hi == 2.0 and lo <= hi


def test_yarn_is_every_pieces_not_the_first_components():
    from brambleloop.cir.compiler import compile_cir
    from brambleloop.cir.twin import build_twin

    cir = _cir("garment:harbour-drop-shoulder-pullover:M")
    r = compile_cir(cir)
    first = sum(build_twin(cir, r).yarn_metres_by_color.values())
    every = sum(sum(build_twin(cir, r, component=c.name).yarn_metres_by_color.values())
                for c in cir.components)
    total = sum(T._pattern_yardage(cir, r, build_twin(cir, r)).values())
    assert abs(total - every) < 0.5 and total > first * 1.2, (first, every, total)


def test_a_stuffed_toy_states_the_size_it_can_or_blocks_never_an_empty_size():
    """ENG-PLUSH (base): a closed stuffed toy states its circumference, the size its twin can
    derive, in place of a width x height it refuses. The child-safety text must carry that
    size; it is never rendered with an empty one (FIX-B18)."""
    F = _ami()
    doc = T.build_template_pdf(F.pebble_friend(), released_on=RELEASED,
                               gallery=T.test_double_gallery(), childrens=F.CHILDRENS)
    text = P.extracted_text(doc.pdf_bytes)
    assert "The age band is stated here" in text
    assert "finishing at about" in text and "around its widest round" in text, text[:400]
    assert "finishing at  at" not in text and "finishing at at" not in text
    # With no size the twin can state at all, it still blocks in notes.
    orig = P.childrens_facts

    def no_size(cir, twin, audience):
        import dataclasses as _dc
        return _dc.replace(orig(cir, twin, audience), finished_size_cm=None, size_text="")
    P.childrens_facts = no_size
    try:
        T.build_template_pdf(F.pebble_friend(), released_on=RELEASED,
                             gallery=T.test_double_gallery(), childrens=F.CHILDRENS)
    except T.TemplateBlocked as e:
        assert e.section == "notes" and "finished_size_cm" in str(e), e
    else:
        raise AssertionError("a stuffed toy rendered child-safety text with no size at all")
    finally:
        P.childrens_facts = orig


def _ami_doc():
    """LAYOUT-ONLY: the child-safety facts' missing size is stubbed so the amigurumi pages
    can be inspected. Never a product path; the real path blocks (test above)."""
    F = _ami()
    orig = P.childrens_facts

    def stub(cir, twin, audience):
        fx = orig(cir, twin, audience)
        return dataclasses.replace(fx, finished_size_cm=(11.0, 16.0),
                                   fibres=fx.fibres or ("cotton",),
                                   fibre_read_from=fx.fibre_read_from or "test stub")
    P.childrens_facts = stub
    try:
        return T.build_template_pdf(F.pebble_friend(), released_on=RELEASED,
                                    gallery=T.test_double_gallery(), childrens=F.CHILDRENS)
    finally:
        P.childrens_facts = orig


def test_the_amigurumi_variant_has_component_diagrams_placed_assembly_and_eye_options():
    F = _ami()
    cir = F.pebble_friend()
    doc = _ami_doc()
    assert doc.family == T.AMIGURUMI and doc.status == "proof_test_double"
    kinds = [f["kind"] for f in doc.figures]
    drawn = {f["component"] for f in doc.figures if f["kind"] == "component_diagram"}
    assert drawn == {c.name for c in cir.components}, drawn
    placed = [f for f in doc.figures if f["kind"] == "placement_diagram"]
    assert [p["rounds"] for p in placed] == [[12, 12], [5, 7]], placed
    assert kinds.count("certified_frame") >= 7
    text = doc.prose
    assert "not a photograph" in text and "stuff here" in text
    assert "across rounds 5-7, 6 sts either side of centre" in text
    assert "Embroidered eyes (as written)" in text and "between rounds 6 and 12 of the head" in text
    assert "Safety eyes are not part of this pattern" in text
    assert "Hook range: US E-4 / 3.5 mm to US G-6 / 4 mm" in text, text[:0]
    assert "Step 1:" not in text
    assert "head 20.0 cm around" in text
    assert sum(doc.yardage_by_color.values()) > 40
    assert T.audit(doc.pdf_bytes, expected_gallery=doc.gallery)["verdict"] == "PASS"
    assert [p for p in doc.problems if "cover hero" not in p] == [], doc.problems


def test_every_proof_family_meets_the_premium_standard_with_a_rendered_gallery():
    rendered = [dict(f, test_double=False, kind="generated") for f in _gallery()]
    for key in ("hexagon_coasters", "cloudline_blanket",
                "garment:harbour-drop-shoulder-pullover:M", "pillow", "snowfall_throw"):
        for term in ("US", "UK"):
            doc = T.build_template_pdf(_cir(key), terminology=term, released_on=RELEASED,
                                       gallery=rendered)
            assert doc.customer_ready and not doc.problems, (key, term, doc.problems)


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
