"""K9 (wave 4) continuation: the Product Truth rows the first pass left open.

Rows: F-779 listing conversion is not product truth (variant activation), F-784/F-795
similarity review incl. presentation, F-792 spec freeze before the instruction writer,
F-756 schematic cross-check, F-755 all-size parse, F-751 stitch semantics, F-753/F-754
region gauge and apparent stitch scale, F-363 children's physical plausibility.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import copy
import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from brambleloop.cir.model import CIR  # noqa: E402
from brambleloop.commerce import listing_tests as T  # noqa: E402
from brambleloop.growth.experiments import HOLDOUT, Experiment  # noqa: E402
from brambleloop.products import garments as G  # noqa: E402

_CACHE: dict = {}


def _graded(key: str | None = None, size: str | None = None) -> CIR:
    key = key or sorted(G.DESIGNS)[0]
    if key not in _CACHE:
        _CACHE[key] = G.DESIGNS[key]().build_all()
    fam = _CACHE[key]
    assert fam, key
    size = size or sorted(fam)[0]
    return CIR.from_dict(copy.deepcopy(fam[size].to_dict()))


# ---- F-779 -------------------------------------------------------------------------------

def _listing_test(variables=("title",)):
    plan = Experiment("v1", "a clearer title lifts click-through on ornament listings", "ctr", HOLDOUT, 0.05, 0.02,
                      200, date(2026, 11, 1))
    return T.ListingTest(key="v1", listing_ref="L1", plan=plan, variables=variables,
                         context=T.Context("ornaments", "under_6", "Christmas", "new"))


def test_a_listing_variant_may_not_distort_product_truth():
    cir = _graded()
    control = T.ListingVariant(
        test_key="v1", title=f"{cir.title} | Crochet Garment Pattern PDF",
        description="Written instructions with stitch counts for every row, worsted weight, "
                    "with charts. Intermediate.",
        tags=("crochet pattern", "sweater"), price_cad=9.0, thumbnail="frame-1.png")
    test = _listing_test()
    ok = T.activate_variant(test, T.ListingVariant(**{**control.__dict__,
                                                      "title": "Cosy Sweater Crochet Pattern PDF"}),
                            control=control, cir=cir)
    assert ok["activated"] and ok["changed"] == ["title"], ok
    bad_titles = {
        "Easy Beginner Sweater Pattern PDF": "difficulty",
        "Seamless Top-Down Sweater Pattern": "construction",
        "Bulky Sweater Crochet Pattern PDF": "materials",
        "Cable Sweater Crochet Pattern PDF": "stitch_appearance",
        "Sweater Crochet Kit, Yarn Included": "deliverables",
        "Oversized Fit Sweater Pattern PDF": "POLICY_FIT_CLAIM",
        "Sweater Pattern in 9 Sizes PDF": "POLICY_SIZE_COVERAGE",
        "Machine Washable Sweater Pattern": "POLICY_CLAIM_UNTRACEABLE",
    }
    assert bad_titles
    for title, why in bad_titles.items():
        out = T.activate_variant(test, T.ListingVariant(**{**control.__dict__, "title": title}),
                                 control=control, cir=cir)
        assert not out["activated"] and any(why in p for p in out["problems"]), (title, out)
    # A change the test did not declare, an uncertified thumbnail and a missing CIR refuse.
    out = T.activate_variant(test, T.ListingVariant(**{**control.__dict__, "price_cad": 7.0}),
                             control=control, cir=cir)
    assert any("VARIANT_UNDECLARED_CHANGE" in p for p in out["problems"]), out
    thumb = _listing_test(("thumbnail",))
    out = T.activate_variant(thumb, T.ListingVariant(**{**control.__dict__,
                                                        "thumbnail": "seller-photo.png"}),
                             control=control, cir=cir, certified_assets={"frame-1.png",
                                                                         "frame-2.png"})
    assert any("VARIANT_IMAGE_UNCERTIFIED" in p for p in out["problems"]), out
    out = T.activate_variant(thumb, T.ListingVariant(**{**control.__dict__,
                                                        "thumbnail": "frame-2.png"}),
                             control=control, cir=cir, certified_assets={"frame-1.png",
                                                                         "frame-2.png"})
    assert out["activated"], out
    out = T.activate_variant(test, control, control=control, cir=None)
    assert any("VARIANT_NO_PRODUCT_TRUTH" in p for p in out["problems"]), out


# ---- F-784 / F-795 -----------------------------------------------------------------------

def _photo(seed: int, size=(240, 180)) -> bytes:
    import io
    import random

    from PIL import Image, ImageDraw

    rnd = random.Random(seed)
    img = Image.new("RGB", size, (rnd.randrange(256), rnd.randrange(256), rnd.randrange(256)))
    d = ImageDraw.Draw(img)
    for _ in range(12):
        x, y = rnd.randrange(size[0]), rnd.randrange(size[1])
        d.ellipse((x, y, x + rnd.randrange(20, 90), y + rnd.randrange(20, 90)),
                  fill=(rnd.randrange(256), rnd.randrange(256), rnd.randrange(256)))
    out = io.BytesIO()
    img.save(out, "PNG")
    return out.getvalue()


def _reencoded(data: bytes) -> bytes:
    import io

    from PIL import Image

    img = Image.open(io.BytesIO(data)).convert("RGB").resize((480, 360))
    out = io.BytesIO()
    img.save(out, "JPEG", quality=70)
    return out.getvalue()


def test_presentation_is_a_similarity_dimension_read_from_the_library():
    import tempfile
    from pathlib import Path

    from brambleloop.core.db import Database
    from brambleloop.gates import originality as O
    from brambleloop.publish import release_gates
    from brambleloop.teardown import intake, library

    theirs = _photo(1)
    copy_of_theirs = _reencoded(theirs)
    ours = {f"frame-{i}": _photo(100 + i) for i in range(3)}
    assert ours
    assert O.presentation_compare(ours, {"b/photo.png": theirs})["verdict"] == "clear"
    hit = O.presentation_compare({**ours, "frame-9": copy_of_theirs}, {"b/photo.png": theirs})
    assert hit["verdict"] == "material" and hit["hits"][0]["frame"] == "frame-9", hit
    assert O.presentation_compare({}, {"b/photo.png": theirs})["verdict"] == "unmeasured"
    assert O.presentation_compare(ours, {})["verdict"] == "unmeasured"

    with tempfile.TemporaryDirectory() as tmp:
        db = Database("sqlite:///" + str(Path(tmp) / "k9.db"))
        db.create_all()
        try:
            env = {library.LIBRARY_ENV: str(Path(tmp) / "quarantine")}
            # Before any purchase: unmeasured, said aloud rather than read as clear.
            out = O.presentation_review(db, frames=ours, env=env)
            assert [f.code for f in out] == ["SIMILARITY_UNMEASURED"], out
            from brambleloop.core.models import BenchmarkListing
            from brambleloop.intel import benchmarks

            with db.session() as s:
                s.add(BenchmarkListing(benchmark_key=benchmarks.MJS_KEY, listing_ref="77",
                                       title="Synthetic purchased evidence", pod="blankets",
                                       product_type="pattern", price_cad=7,
                                       url="https://example.invalid/77", detail={}))
            intake.receive(db, "77", [("seller-photo.png", theirs)], env=env,
                           mirror_files=False)
            assert O.benchmark_images(db, env), "manifest image not readable for review"
            assert O.presentation_review(db, frames=ours, env=env) == []
            out = O.presentation_review(db, frames={**ours, "frame-9": copy_of_theirs},
                                        env=env)
            assert out and all(f.code == "SIMILARITY_ESCALATED" and f.is_error for f in out)
            # The store gate reads the release's own frames (none stored here).
            assert release_gates._frame_bytes(db, "nothing", "1.0.0") == {}
            assert "presentation_review" in __import__("inspect").getsource(
                release_gates.originality_gate)
        finally:
            db.engine.dispose()


# ---- F-792 -------------------------------------------------------------------------------

def test_a_competitor_informed_spec_is_frozen_before_the_writer_runs():
    import dataclasses
    import tempfile
    from pathlib import Path

    from brambleloop.cir.model import Provenance
    from brambleloop.core.db import Database
    from brambleloop.gates import spec_freeze as SF
    from brambleloop.gates.certificate import certify

    assert SF.writer_context_problems() == (), SF.writer_context_problems()
    base = _graded()
    informed = dataclasses.replace(base, provenance=Provenance(
        concept_key="k9-freeze", brief_digest="d", primitives_used=("cir.graded",),
        benchmarks_consulted=("benchmark-2-mini-star-stitch-cardigan",)))
    own = dataclasses.replace(base, provenance=None)
    assert SF.findings(own, None) == [] and SF.consulted(informed)
    with tempfile.TemporaryDirectory() as tmp:
        db = Database("sqlite:///" + str(Path(tmp) / "k9.db"))
        db.create_all()
        try:
            codes = [f.code for f in SF.findings(informed, db)]
            assert codes == ["SPEC_NOT_FROZEN"], codes
            # certify freezes before it writes, with the benchmark excluded from the writer.
            cert = certify(informed, db=db)
            assert "SPEC_NOT_FROZEN" not in {f.code for f in cert.findings}
            history = SF.frozen(db, informed)
            assert len(history) == 1 and history[0]["fingerprint"] == informed.fingerprint
            assert history[0]["excluded_from_writer"] == list(SF.consulted(informed))
            assert "cir" in history[0]["writer_inputs"]
            # Same slug@version, different design: changed after the instructions were drafted.
            moved = dataclasses.replace(informed, designer_notes="tweaked after the freeze")
            assert moved.fingerprint != informed.fingerprint
            cert2 = certify(moved, db=db)
            assert "SPEC_CHANGED_AFTER_FREEZE" in {f.code for f in cert2.findings}
            assert not cert2.granted
            # A new version is a new spec.
            bumped = dataclasses.replace(moved, version="9.9.9")
            SF.freeze(db, bumped)
            assert SF.findings(bumped, db) == []
        finally:
            db.engine.dispose()


# ---- F-755 / F-756 -----------------------------------------------------------------------

_TEN = "Row 1: ch 42(46,50,54,58,62,66,70,74,78), turn -- 41(45,49,53,57,61,65,69,73,77) sts."
_NINE = "Rows 4-9(9,9,11,11,11,11,14,16): rep rows 2 and 3."           # one size dropped


def test_the_whole_size_family_is_parsed_before_one_size_is_frozen():
    from brambleloop.teardown import size_family as SF

    good = SF.all_size_parse([_TEN, "Neck: 18(18,22,22,22,26,26,26,30,30) sts."])
    assert good["state"] == SF.AGREE and good["sizes"] == 10 and good["vectors"] == 3, good
    assert SF.freeze_render_size(good, 4)["of"] == 10
    bad = SF.all_size_parse([_TEN, _NINE, "Hood: 46(46,50,48,54,58,60,62,64,66 sts."])
    kinds = sorted({p["kind"] for p in bad["problems"]})
    assert bad["state"] == SF.CONFLICT and kinds == ["indexing", "parenthetical"], bad
    try:
        SF.freeze_render_size(bad, 4)
    except SF.SizeFamilyRefused:
        pass
    else:
        raise AssertionError("froze a size over an indexing error")
    resolved = {b: "size 8 value dropped; derived from the sleeve rows" for b in bad["blocking"]}
    assert SF.freeze_render_size(bad, 4, resolutions=resolved)["resolved"] == sorted(resolved)
    rev = SF.all_size_parse([_TEN, "Hood: 46(46,50,48,54,58,60,62,64,66) sts."])
    assert rev["state"] == SF.AGREE and rev["problems"][0]["kind"] == "grading_reversal"
    assert SF.freeze_render_size(rev, 0)["reviewed_reversals"]
    try:
        SF.freeze_render_size(SF.all_size_parse(["no vectors here"]), 0)
    except SF.SizeFamilyRefused:
        pass
    else:
        raise AssertionError("froze a size of a family never parsed")


def test_the_teardown_reader_reports_the_size_family():
    import io
    import tempfile
    from pathlib import Path

    from reportlab.pdfgen.canvas import Canvas

    from brambleloop.teardown import library, reader

    buf = io.BytesIO()
    c = Canvas(buf)
    for y, line in ((800, _TEN), (780, _NINE)):
        c.drawString(30, y, line)
    c.save()
    with tempfile.TemporaryDirectory() as tmp:
        env = {library.LIBRARY_ENV: str(Path(tmp) / "quarantine")}
        target = Path(env[library.LIBRARY_ENV]) / "ref1" / "pattern.pdf"
        target.parent.mkdir(parents=True)
        target.write_bytes(buf.getvalue())
        out = reader.read("ref1/pattern.pdf", env=env)
    fam = out["size_family"]
    assert fam["parsed"] and fam["consistent"] is False and fam["sizes"] == 10, fam
    assert fam["indexing_error_pages"] == [1] and not fam["parenthetical_error_pages"], fam


def test_a_schematic_disagreement_is_a_conflict_never_a_choice():
    from brambleloop.teardown import size_family as SF

    out = SF.schematic_cross_check({"width": [40, 44, 48], "length": [30, None, 34]},
                                   {"width": [40.5, 44.2, 55.0], "length": [30.4, 32.0, 34.1]})
    assert out["state"] == SF.CONFLICT and out["conflicts"] == [("width", 2)], out
    assert out["unknown"] == [("length", 1)], out
    assert out["per_measure"]["width"][2]["stated"] == 48 and \
        out["per_measure"]["width"][2]["derived"] == 55.0
    b1 = SF.benchmark1_cross_check()
    assert len(b1["sizes"]) == 9 and b1["per_measure"]["length_cm"], b1
    assert all(r["verdict"] == SF.AGREE for r in b1["per_measure"]["length_cm"])
    assert all(r["verdict"] == SF.AGREE for r in b1["per_measure"]["back_width_cm"])
    # The armhole needs a chain gauge the pattern never states: UNKNOWN, not a guess.
    assert all(r["verdict"] == SF.UNKNOWN for r in b1["per_measure"]["armhole_cm"])
    assert b1["state"] == SF.UNKNOWN


# ---- F-751 -------------------------------------------------------------------------------

def _star_panel() -> CIR:
    import dataclasses

    import fixtures
    from brambleloop.cir.model import Component, Op, Row

    base = fixtures.good_mosaic_panel()
    rows = [Row(index=1, ops=[Op("sc", 42)], declared_count=42, turning_chain=1),
            Row(index=2, ops=[Op("beg_star_st"), Op("star_st", 19), Op("end_star_st")],
                declared_count=22, turning_chain=3),
            Row(index=3, ops=[Op("hdc"), Op("hdc_inc", 20), Op("hdc")], declared_count=42,
                turning_chain=1)]
    return dataclasses.replace(base, slug="k9-star", title="Star Panel", colors={},
                               components=[Component(name="panel", construction="flat_rows",
                                                     rows=rows, foundation=42)])


def test_a_star_stitch_compiles_to_its_eyes_legs_and_bases():
    from brambleloop.cir import stitches as S
    from brambleloop.cir.compiler import compile_cir
    from brambleloop.cir.writer import write_pattern
    from brambleloop.gates.certificate import stitch_semantics_findings
    from brambleloop.publish import abbreviations as A

    assert S.structure_problems() == () and A.structure_method_problems() == ()
    assert A.method_names_no_stitch_literally() == ()
    star = S.anatomy("star_st")
    assert star.anchors[:3] == ("prev_eye", "prev_leg", "prev_base") and star.new_stitches == 2
    assert S.anatomy("sc") is None and S.anatomy("cable2x2").order == (3, 4, 1, 2)
    textured = [c for c in S.known_codes() if c not in S.CONVENTION_PRIMITIVES]
    assert textured and all(S.anatomy(c) is not None for c in textured), textured
    cir = _star_panel()
    result = compile_cir(cir)
    assert result.ok, [str(e) for e in result.errors][:3]
    assert stitch_semantics_findings(cir) == []
    text = write_pattern(cir, result)
    key = {e.token: e.method for e in A.stitch_key(text)}
    assert "eye" in key.get("star_st", "") and "leg" in key["star_st"], key
    for lang in ("US", "UK"):
        assert "base" in A.method("end_star_st", lang)
    # A structure that disagrees with the counts, or a method that stops teaching it, refuses.
    saved = dict(S.ANATOMY)
    try:
        S.ANATOMY["star_st"] = S.Anatomy("star", ("st", "st", "st"), loops_closed=6,
                                         makes=("eye",))
        codes = {f.code for f in stitch_semantics_findings(cir)}
        assert codes == {"STITCH_SEMANTICS_MISSING"}, codes
    finally:
        S.ANATOMY.clear()
        S.ANATOMY.update(saved)
    saved_m = dict(A.METHOD)
    try:
        A.METHOD["star_st"] = "Work a star."
        assert any("star_st" in f.message for f in stitch_semantics_findings(cir))
    finally:
        A.METHOD.clear()
        A.METHOD.update(saved_m)
    assert stitch_semantics_findings(cir) == []


# ---- F-753 -------------------------------------------------------------------------------

def _fabric(st_px: float) -> bytes:
    import io

    from brambleloop.visual.stitch_identity import draw_hdc_fabric

    out = io.BytesIO()
    draw_hdc_fabric(480, 240, st_px, st_px * 0.8).save(out, "PNG")
    return out.getvalue()


def test_a_generated_image_with_the_wrong_stitch_scale_is_not_certified():
    import fixtures
    from brambleloop.cir.compiler import compile_cir
    from brambleloop.cir.twin import build_twin
    from brambleloop.gates import asset_truth as AT
    from brambleloop.gates import stitch_scale as SS

    cir = fixtures.good_mosaic_panel()               # 16 sts / 10 cm: 0.625 cm per stitch
    twin = build_twin(cir, compile_cir(cir))
    px_per_cm = 20.0
    assert SS.expected_pitch_px(cir, px_per_cm) == 12.5
    # A star fabric's visible repeat is a star: two stitches of the row below.
    assert SS.expected_pitch_px(_star_panel(), px_per_cm) == 2 * 12.5
    right = SS.read(_fabric(12.5), px_per_cm=px_per_cm, expected_px=12.5)
    wrong = SS.read(_fabric(20.0), px_per_cm=px_per_cm, expected_px=12.5)
    assert SS.verdict(cir, right)["verdict"] == SS.PASS, (right, SS.verdict(cir, right))
    assert SS.verdict(cir, wrong)["verdict"] == SS.FAIL, (wrong, SS.verdict(cir, wrong))
    assert SS.verdict(cir, None)["verdict"] == SS.UNKNOWN

    def codes(reading):
        asset = AT.Asset(asset_id="g1", asset_class=list(AT.AssetClass)[0],
                         provenance=AT.Provenance(source="generator", created_by="visual",
                                                  tool="image-model", prompt_hash="h"),
                         depicts_stitches=["sc"], stitch_scale=reading)
        return {f.code for f in AT.check_asset(asset, cir, twin) if "STITCH_SCALE" in f.code}

    assert codes(right) == set()
    assert codes(wrong) == {"ASSET_STITCH_SCALE_WRONG"}
    assert codes(None) == {"ASSET_STITCH_SCALE_UNMEASURED"}
    # A component worked at its own gauge (F-754) is held to that gauge, not the main one.
    import copy

    from brambleloop.cir.model import Gauge
    banded = copy.deepcopy(cir)
    banded.components[0].gauge = Gauge(stitches_per_10cm=20, rows_per_10cm=14,
                                       stitch_type="sc", hook_mm=4.5, yarn_weight="dk")
    assert SS.expected_pitch_px(banded, px_per_cm, component="panel") == 10.0


if __name__ == "__main__":
    fails = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    assert tests
    for name, fn in tests:
        try:
            fn()
            print("OK  ", name)
        except Exception as exc:  # noqa: BLE001
            fails += 1
            print("FAIL", name, repr(exc)[:600])
    print(f"\n{len(tests) - fails} passing, {fails} failing")
    sys.exit(1 if fails else 0)
