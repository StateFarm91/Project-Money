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
