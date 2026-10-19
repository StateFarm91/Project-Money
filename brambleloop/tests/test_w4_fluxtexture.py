"""W4-FLUXAPI: the owner's reading-nook-cable-wrap FLUX 3 test, turned into rules that are tested.

The 2026-10-19 manual test (RECORD.json) passed identity and styling and failed Product Truth
four ways. Each failure now has a counter:

- WRONG_CRAFT_TEXTURE: a stitch-texture reference drawn from the stitch definitions, bound to the
  release and to the stitch set, placed before the symbolic chart;
- INVENTED_END_BAND_TREATMENT / INVENTED_EDGING: CIR-derived negatives in the prompt;
- UNVERIFIABLE_COUNT: a product-only flat lay first, whose PASS verdict gates lifestyle.

No network, no spend: stub renderer only.

Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_w4_fluxtexture.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PIL import Image  # noqa: E402

from brambleloop.creative import failure_codes as FC  # noqa: E402
from brambleloop.creative import flux_prompt as FP  # noqa: E402
from brambleloop.creative import image_stages as S  # noqa: E402
from brambleloop.creative import pattern_refs as P  # noqa: E402
from brambleloop.creative import stitch_texture as T  # noqa: E402
from brambleloop.products import launch0  # noqa: E402
from brambleloop.products.moment_candidates import reading_nook_cable_wrap  # noqa: E402

_WORK = Path(tempfile.mkdtemp(prefix="w4-fluxtexture-"))
WRAP = reading_nook_cable_wrap()
WRAP_HASH = P.release_hash_of(WRAP)
RECORD = (ROOT / "research/final_build/w4/flux_experiments/2026-10-19_reading_nook_cable_wrap"
          / "RECORD.json")
OUTFIT = {"id": "outfit-11", "description": "a brown fitted long-sleeve top, stone trousers"}
_M: list = []


def _wrap_manifest() -> dict:
    if not _M:
        _M.append(P.build(WRAP, release_hash=WRAP_HASH, out_dir=_WORK / "wrap"))
    return _M[0]


def _refused(fn, exc=S.StageRefused):
    try:
        fn()
    except exc:
        return True
    raise AssertionError(f"expected {exc.__name__}")


def _mean(im, box):
    px = list(im.crop(box).getdata())
    return tuple(sum(p[i] for p in px) / len(px) for i in range(3))


# -- (a) stitch-texture reference ------------------------------------------------------------
def test_texture_reference_binds_to_the_release_and_the_stitch_set():
    m = _wrap_manifest()
    assert m["cir_version"] == "0.1.0" and m["release_hash"] == WRAP_HASH
    roles = [r["role"] for r in m["references"]]
    assert roles == ["layout", "texture", "detail", "rules"]           # texture before chart
    tex = m["texture"]
    assert tex["stitches_drawn"] == ["cable2x2", "dc", "sc"] == sorted(
        {c.stitch for c in __import__("brambleloop.cir.twin", fromlist=["build_twin"])
         .build_twin(WRAP, __import__("brambleloop.cir.compiler", fromlist=["compile_cir"])
                     .compile_cir(WRAP)).cells})
    assert tex["crossing_side"].startswith("UNKNOWN")                 # CIR declares no side
    ref = m["references"][1]
    assert WRAP_HASH[:12] in Path(ref["path"]).name and P.verify(m)["ok"]
    again = P.build(WRAP, release_hash=WRAP_HASH, out_dir=_WORK / "wrap2")
    assert again["references"][1]["sha256"] == ref["sha256"]          # deterministic
    other = reading_nook_cable_wrap(version="0.2.0")
    assert _refused(lambda: P.build(other, release_hash=WRAP_HASH, out_dir=_WORK / "x"),
                    P.PatternRefsRefused)
    cloud = launch0.cir_for("cloudline_blanket")
    cm = P.build(cloud, release_hash=P.release_hash_of(cloud), out_dir=_WORK / "cloud")
    assert cm["texture"]["stitches_drawn"] == ["dc", "sc"]
    assert cm["references"][1]["sha256"] != ref["sha256"]


def test_texture_shows_the_plain_cream_end_band_and_whole_cable_groups():
    m = _wrap_manifest()
    tex = m["texture"]
    assert tex["rows"][0] == 1 and tex["rows"][1] >= 9                # band + two cable rows
    assert tex["columns"] == [0, 16]                                  # 3dc+C+3dc+C+3dc
    with Image.open(m["references"][1]["path"]) as im:
        im = im.convert("RGB")
        w, h = im.size
        bottom = _mean(im, (0, h - 20, w, h - 2))
        top = _mean(im, (0, 2, w, 40))
    assert min(bottom) > 150, bottom                                  # cream sc band
    assert top[1] > top[0] and max(top) < 140, top                    # forest body


def test_texture_crop_never_splits_a_cable_group():
    from brambleloop.cir.compiler import compile_cir
    from brambleloop.cir.twin import build_twin

    twin = build_twin(WRAP, compile_cir(WRAP))
    for cols in (5, 6, 9, 14, 18):
        _, _, _, c1 = T.choose_region(twin, max_cols=cols)
        row = twin.chart_grid()[4]                                    # a cable row
        width = c1 + 1
        i = 0
        while i < width:
            n = 4 if row[i] == "cable2x2" else 1
            assert i + n <= width, (cols, width)
            i += n


# -- (b) category-aware negatives ------------------------------------------------------------
def test_wrap_negatives_name_each_failure_the_owner_saw():
    neg = _wrap_manifest()["technical_rules"]["negatives"]
    text = " | ".join(neg)
    assert neg[0].startswith("knitting of any kind: this is crochet")
    assert "ribbing anywhere" in text
    assert "an edging, border, rib, fringe or trim along any edge" in text
    assert "rows 1-4: plain cream #FAF6EB sc, solid, no stripe" in text
    assert "rows 153-156: plain cream #FAF6EB sc, solid, no stripe" in text
    assert ("exactly 8 cable columns, each a 2-over-2 crochet crossing of dc stitches, "
            "separated by 3 dc, with 3 and 3 stitches at the edges, crossing every 4 rows"
            in text)
    assert "colour changes anywhere except rows 5, 153" in text
    cloud = launch0.cir_for("cloudline_blanket")
    cneg = " | ".join(P.negatives(P.fabric_facts(cloud)))
    assert "every 2 rows from row 7 to 93" in cneg and "rows 1-6: plain cream" in cneg


def test_declared_features_are_not_forbidden():
    facts = dict(P.fabric_facts(WRAP))
    facts.update(ribbing_declared=True, edging_declared=True, end_bands=[], cables=None,
                 colour_change_rows=[])
    out = P.negatives(facts)
    assert out == [out[0]] and out[0].startswith("knitting")         # only the craft rule


def test_prompt_carries_the_negatives_and_names_the_texture_reference():
    m = _wrap_manifest()
    rel = S.Release(slug=WRAP.slug, version=WRAP.version, release_hash=WRAP_HASH,
                    title=WRAP.title, rules=m["technical_rules"],
                    pattern_refs=tuple(r["path"] for r in m["references"]),
                    pattern_ref_sha256s=tuple(r["sha256"] for r in m["references"]))
    stub = S.StubRenderer()
    S.product_only(rel, renderer=stub, work_dir=str(_WORK / "p"))
    text = stub.calls[-1]["prompt"]
    assert "THIS FABRIC MUST NOT SHOW: knitting of any kind" in text
    assert "image 2 = certified crochet stitch texture close-up" in text
    assert "The fabric looks exactly like image 2" in text
    assert "exactly 8 cable columns" in text and "rows 153-156" in text
    assert "image.flux3.negatives@1" in [p.ref for p in FP.SECTIONS]
    bare = dict(m["technical_rules"], negatives=[])
    assert _refused(lambda: FP.build(rules=bare, roles=list(S.PRODUCT_ROLES), role="x"),
                    FP.PromptBuildRefused)


# -- (c) stage order: flat lay first, its fidelity gates lifestyle ---------------------------
def test_product_only_is_an_unfolded_countable_flat_lay():
    rel = S.release_from_cir(WRAP, release_hash=WRAP_HASH, out_dir=_WORK / "rel")
    stub = S.StubRenderer()
    c = S.product_only(rel, renderer=stub, work_dir=str(_WORK / "fl"))
    assert c.role == "product_flat_lay"
    text = stub.calls[-1]["prompt"]
    assert "laid completely flat and unfolded" in text and "no folds" in text
    assert "cable column and motif can be counted" in text


def test_lifestyle_is_gated_on_a_pass_verdict_for_that_exact_flat_lay():
    rel = S.release_from_cir(WRAP, release_hash=WRAP_HASH, out_dir=_WORK / "rel2")
    stub = S.StubRenderer()
    flat = S.product_only(rel, renderer=stub, work_dir=str(_WORK / "g"))
    flat2 = S.product_only(rel, renderer=stub, work_dir=str(_WORK / "g"), scene={
        "environment": "linen"})
    calls = len(stub.calls)
    for verdict in (None,
                    S.fidelity_verdict(flat, status="FAIL", checker="t",
                                       failures=[FC.UNVERIFIABLE_COUNT]),
                    S.fidelity_verdict(flat, status="UNKNOWN", checker="t"),
                    S.fidelity_verdict(flat2, status="PASS", checker="t")):   # other image
        assert _refused(lambda: S.lifestyle(rel, flat, None, OUTFIT, fidelity=verdict,
                                            renderer=stub, work_dir=str(_WORK / "g")))
    assert len(stub.calls) == calls                                    # nothing sent
    ok = S.lifestyle(rel, flat, None, OUTFIT,
                     fidelity=S.fidelity_verdict(flat, status="PASS", checker="t"),
                     renderer=stub, work_dir=str(_WORK / "g"))
    assert ok.features_laura and len(stub.calls) == calls + 1
    edited = S.variant(rel, flat, "detail_closeup", renderer=stub, work_dir=str(_WORK / "g"))
    assert _refused(lambda: S.lifestyle(rel, edited, None, OUTFIT,
                                        fidelity=S.fidelity_verdict(edited, status="PASS",
                                                                    checker="t"),
                                        renderer=stub, work_dir=str(_WORK / "g")))
    assert _refused(lambda: S.fidelity_verdict(flat, status="PASS", checker="t",
                                               failures=[FC.INVENTED_EDGING]))
    assert _refused(lambda: S.fidelity_verdict(flat, status="FAIL", checker="t",
                                               failures=["LOOKS_OFF"]))


# -- (d) shared failure taxonomy -------------------------------------------------------------
def test_the_four_owner_failure_codes_are_one_shared_constant():
    assert set(FC.PRODUCT_TRUTH_CODES) == {"INVENTED_END_BAND_TREATMENT", "INVENTED_EDGING",
                                           "WRONG_CRAFT_TEXTURE", "UNVERIFIABLE_COUNT"}
    assert set(FC.CATEGORY_OF.values()) == {"product_fidelity"}       # candidate_gates' name
    record = json.loads(RECORD.read_text())
    assert {f["code"] for f in record["failure_categories"]} == FC.ALL_CODES


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failures = 0
    for name, test in tests:
        started = time.time()
        try:
            test()
            print("OK  ", name, f"{time.time() - started:.1f}s")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            import traceback

            traceback.print_exc()
            print("FAIL", name, type(exc).__name__, str(exc)[:500])
    print(f"{len(tests) - failures}/{len(tests)} passing")
    shutil.rmtree(_WORK, ignore_errors=True)
    sys.exit(bool(failures))
