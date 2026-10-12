"""W4-SETCONSIST: F-746 listing-set consistency, read pairwise in parity GALLERY.

A listing set must show one product. Parity GALLERY now fails when, across the frames:
* the product, release, CIR fingerprint or configuration differs;
* any deterministic frame draws a colour the certified product does not have;
* model frames are conditioned on different identity packs.
These are facts each frame carries; the pictures are not re-judged. Frames with no manifest
add nothing to this check.

Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_w4_setconsist.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.products import launch0 as L  # noqa: E402
from brambleloop.visual import parity  # noqa: E402

CIR = L.cir_for("hexagon_coasters")


def _frame(view, role, job, colours=("cream", "wine"), **over):
    manifest = {"slug": CIR.slug, "version": CIR.version, "cir_fingerprint": CIR.fingerprint,
                "represented_variant": {"key": CIR.variant_key, "features": {}},
                "view": view, "role": role, "job": job,
                "layout": {"rounds": [{"round": i + 1, "colour": c}
                                      for i, c in enumerate(colours)]}}
    manifest.update(over)
    return {"kind": "disclosed_render", "role": role, "view": view, "position": 1,
            "disclosed_render": manifest}


def _set():
    return [_frame("hero", "hero", "DESIRE"), _frame("scale", "scale", "SCALE"),
            _frame("detail", "detail", "DETAIL")]


def _gallery(frames):
    return parity.assess(frames)["dimensions"][parity.GALLERY]


def test_a_consistent_set_has_no_mismatch():
    out = parity.set_consistency(_set())
    assert out["compared"] == 3 and out["colour_authority"] is True
    assert out["mismatches"] == [], out


def test_a_set_with_one_mismatched_colour_is_refused():
    frames = _set()
    frames[2] = _frame("detail", "detail", "DETAIL", colours=("cream", "forest"))
    out = parity.set_consistency(frames)
    assert any("forest" in m for m in out["mismatches"]), out
    g = _gallery(frames)
    if g["verdict"] != parity.UNJUDGED:     # roles may leave GALLERY unjudged; never pass
        assert g["verdict"] == parity.FAIL and "one product" in g["why"], g


def test_a_frame_from_another_release_or_configuration_is_a_mismatch():
    frames = _set()
    frames[1]["disclosed_render"]["cir_fingerprint"] = "0" * 16
    assert any("cir_fingerprint" in m for m in parity.set_consistency(frames)["mismatches"])
    frames = _set()
    frames[0]["disclosed_render"]["represented_variant"] = {"key": "other"}
    assert any("configurations" in m for m in parity.set_consistency(frames)["mismatches"])
    frames = _set()
    frames[0]["disclosed_render"]["slug"] = "market-basket-small"
    assert parity.set_consistency(frames)["mismatches"]


def test_model_frames_on_different_identities_are_a_mismatch():
    frames = [{"role": "hero", "carries_model": True,
               "conditioned_on": {"pack_version": "v15"}},
              {"role": "hero", "carries_model": True,
               "conditioned_on": {"pack_version": "v16"}}]
    assert any("identities" in m for m in parity.set_consistency(frames)["mismatches"])


def test_frames_without_manifests_add_nothing():
    frames = [{"role": "hero"}, {"role": "chart"}]
    out = parity.set_consistency(frames)
    assert out == {"mismatches": [], "compared": 0, "colour_authority": False}


def test_the_gallery_verdict_reads_the_mismatch_when_roles_are_complete():
    from brambleloop.visual.gallery import JOBS

    evidence = next(r for r, j in JOBS.items() if j == "engineering_evidence")
    hero = next(r for r, j in JOBS.items() if j != "engineering_evidence")
    frames = [_frame("hero", hero, "DESIRE"), _frame("detail", evidence, "DETAIL")]
    assert _gallery(copy.deepcopy(frames))["verdict"] == parity.PASS
    frames[1] = _frame("detail", evidence, "DETAIL", colours=("cream", "forest"))
    g = _gallery(frames)
    assert g["verdict"] == parity.FAIL and "forest" in g["why"], g


if __name__ == "__main__":
    import time

    failures = 0
    tests = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
    assert tests
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
    sys.exit(bool(failures))
