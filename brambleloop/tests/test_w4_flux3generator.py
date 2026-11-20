"""W4-FLUXAPI: the FLUX 3 stages as W-OWNERIMG's `image_production.Generator` (their E1).

No network, no spend: `StubRenderer`, a CIR loader and an anchor lookup are injected, and the
default loader is exercised only against an empty database (refused).

Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_w4_flux3generator.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import hashlib
import importlib
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.creative import flux3_generator as FG  # noqa: E402
from brambleloop.creative import image_stages as S  # noqa: E402
from brambleloop.creative import pattern_refs as P  # noqa: E402
from brambleloop.gateway import images as I  # noqa: E402
from brambleloop.products import launch0  # noqa: E402
from brambleloop.visual import canonical, conditioning  # noqa: E402

_WORK = Path(tempfile.mkdtemp(prefix="w4-flux3gen-"))
CIR = launch0.cir_for("cloudline_blanket")
REL = P.release_hash_of(CIR)
SLUG, VER = CIR.slug, CIR.version
OUTFIT = {"outfit_id": "o-3", "description": "an oatmeal linen dress, tan sandals",
          "setting": "a sunlit nursery"}
# W-OWNERIMG `candidate_gates.REFERENCE_KINDS`, as of c387c27.
OWNERIMG_KINDS = ("laura_canonical", "pattern_derived", "physical_product_photo",
                  "prior_candidate", "other")


def _gen(anchor=None, renderer=None):
    stub = renderer or S.StubRenderer()
    g = FG.Flux3Generator(None, renderer=stub, cir_loader=lambda s, v: CIR,
                          anchor_lookup=(lambda s, v, r: anchor),
                          work_root=None)
    return g, stub


def _orchestrator_refs(prepared):
    """What image_production hands back: kind, sha256, label and the stored bytes."""
    return [{"kind": r["kind"], "sha256": hashlib.sha256(r["data"]).hexdigest(),
             "label": r.get("label", ""), "data": r["data"]} for r in prepared]


def _laura_refs():
    out = []
    for frame in conditioning.FRAME_ORDER:
        data = Path(canonical.reference_file(frame)).read_bytes()
        out.append({"kind": "laura_canonical", "sha256": hashlib.sha256(data).hexdigest(),
                    "frame": frame, "data": data})
    return out


def _refused(fn, exc):
    try:
        fn()
    except exc:
        return True
    raise AssertionError(f"expected {exc}")


def test_the_generator_has_the_protocol_attributes_and_a_2k_price():
    g, _ = _gen()
    assert g.name == "flux3-image-stages" and g.paid is False         # stub renderer
    assert FG.Flux3Generator(None, cir_loader=lambda s, v: CIR).paid is True
    assert abs(g.max_cost_cad_per_call - round(0.100 * I.USD_TO_CAD, 6)) < 1e-9
    assert S.meets_listing_floor(g.size) and S.expected_px(g.size) == (2048, 2048)


def test_prepare_references_returns_the_four_bound_product_references():
    g, _ = _gen()
    refs = g.prepare_references(slug=SLUG, version=VER, release=REL, cir_fingerprint=None)
    assert [r["kind"] for r in refs] == ["pattern_derived"] * 4
    assert all(r["kind"] in OWNERIMG_KINDS for r in refs)
    assert [r["label"].split("|")[0] for r in refs] == list(S.PRODUCT_ROLES)
    assert {r["label"].split("|", 1)[1] for r in refs} == {f"{SLUG}@{VER}|{REL}"}
    assert _refused(lambda: g.prepare_references(slug=SLUG, version=VER, release="0" * 64,
                                                 cir_fingerprint=None), FG.GeneratorRefused)


def test_anchor_then_lifestyle_with_all_references_and_the_receipt():
    g, stub = _gen()
    refs = _orchestrator_refs(g.prepare_references(slug=SLUG, version=VER, release=REL))
    out = g.generate(stage="product_generation", role=FG.ANCHOR_ROLE, brief="flat",
                     references=refs, outfit=None, attempt=1)
    assert out["data"].startswith(b"\x89PNG") and out["identity_evidence"]["role"] == \
        "product_flat_lay"
    anchor = {"data": out["data"], "sha256": hashlib.sha256(out["data"]).hexdigest(),
              "status": "PASS", "checker": "stub judge"}
    g.anchor_lookup = lambda s, v, r: anchor
    life = g.generate(stage="lifestyle_generation", role="lifestyle", brief="Laura on a sofa",
                      references=refs + _laura_refs(), outfit=OUTFIT, attempt=1)
    ev = life["identity_evidence"]
    assert ev["features_laura"] is True
    assert tuple(ev["input_sha256s"][:3]) == S.canonical_laura_hashes()
    assert ev["input_sha256s"][3:7] == [r["sha256"] for r in refs]
    assert OUTFIT["description"] in stub.calls[-1]["prompt"]
    for k in ("data", "provider", "model", "prompt", "cost_cad", "latency_s"):
        assert k in life, k


def test_lifestyle_is_refused_without_a_pass_anchor():
    for anchor in (None, {"data": b"\x89PNGx", "sha256": hashlib.sha256(b"\x89PNGx")
                          .hexdigest(), "status": "UNKNOWN"},
                   {"data": b"\x89PNGx", "sha256": hashlib.sha256(b"\x89PNGx").hexdigest(),
                    "status": "FAIL"}):
        g, stub = _gen(anchor=anchor)
        refs = _orchestrator_refs(g.prepare_references(slug=SLUG, version=VER, release=REL))
        assert _refused(lambda: g.generate(stage="lifestyle_generation", role="lifestyle",
                                           brief="b", references=refs + _laura_refs(),
                                           outfit=OUTFIT, attempt=1),
                        (FG.GeneratorRefused, S.StageRefused))
        assert stub.calls == []


def test_references_that_are_not_the_releases_bytes_are_refused():
    g, stub = _gen()
    refs = _orchestrator_refs(g.prepare_references(slug=SLUG, version=VER, release=REL))
    bad = [dict(r) for r in refs]
    bad[1]["sha256"] = "0" * 64
    assert _refused(lambda: g.generate(stage="product_generation", role=FG.ANCHOR_ROLE,
                                       brief="", references=bad, outfit=None, attempt=1),
                    FG.GeneratorRefused)
    other = [dict(r, label=r["label"].replace(REL, "f" * 64)) for r in refs]
    assert _refused(lambda: g.generate(stage="product_generation", role=FG.ANCHOR_ROLE,
                                       brief="", references=other, outfit=None, attempt=1),
                    FG.GeneratorRefused)
    laura = _laura_refs()
    laura[1] = dict(laura[1], data=laura[1]["data"] + b"x")             # altered torso
    anchor = {"data": b"\x89PNGa", "sha256": hashlib.sha256(b"\x89PNGa").hexdigest(),
              "status": "PASS"}
    g.anchor_lookup = lambda s, v, r: anchor
    assert _refused(lambda: g.generate(stage="lifestyle_generation", role="lifestyle",
                                       brief="b", references=refs + laura, outfit=OUTFIT,
                                       attempt=1), S.StageRefused)
    assert stub.calls == []


def test_repair_negatives_are_added_never_removed():
    g, stub = _gen()
    refs = _orchestrator_refs(g.prepare_references(slug=SLUG, version=VER, release=REL))
    repair = {"directives": [{"code": "INVENTED_EDGING", "kind": "prompt_negative",
                              "negatives": ["no edging", "no border"]}]}
    g.generate(stage="product_generation", role=FG.ANCHOR_ROLE, brief="", references=refs,
               outfit=None, attempt=2, repair=repair)
    text = stub.calls[-1]["prompt"]
    assert "no edging; no border" in text and "knitting of any kind" in text


def test_the_shared_failure_codes_resolve_where_ownerimg_looks():
    mod = importlib.import_module("brambleloop.creative.image_stages")
    for name in ("PRODUCT_TRUTH_FAILURE_CODES", "FAILURE_CODES"):
        assert set(getattr(mod, name)) == {"INVENTED_END_BAND_TREATMENT", "INVENTED_EDGING",
                                           "WRONG_CRAFT_TEXTURE", "UNVERIFIABLE_COUNT",
                                           # W4-WRAPTEST: W-FIDELITY's measured codes
                                           "WRONG_ASPECT_RATIO", "OFF_PALETTE_COLOUR",
                                           "WRONG_COLOUR_LAYOUT", "WRONG_REPEAT_COUNT",
                                           "WRONG_PIECE_COUNT"}


def test_sizes_below_the_listing_floor_are_refused_never_upscaled():
    rel = S.release_from_cir(CIR, release_hash=REL, out_dir=_WORK / "floor")
    stub = S.StubRenderer()
    for size in ("1024x1024", "912x1140", "1824x2280"):
        assert _refused(lambda: S.product_only(rel, size=size, renderer=stub,
                                               work_dir=str(_WORK / "f")), S.StageRefused)
    assert stub.calls == []
    c = S.product_only(rel, size=S.TALL_LIFESTYLE_SIZE, renderer=stub,
                       work_dir=str(_WORK / "f"))
    assert c.receipt["upscaled"] is False and c.receipt["expected_px"][0] >= 2000
    assert c.receipt["meets_listing_floor"] is False                 # the stub's tiny output


def test_the_default_loader_refuses_an_uncertified_or_unknown_product():
    db = Database("sqlite://")
    db.create_all()
    g = FG.Flux3Generator(db, renderer=S.StubRenderer(), work_root=str(_WORK / "db"))
    assert _refused(lambda: g.prepare_references(slug=SLUG, version=VER, release=REL),
                    FG.GeneratorRefused)


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
