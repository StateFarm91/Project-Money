"""W4-IMGFIX: two regressions from the image branches, fixed at the root.

1. The disclosed hero review and the grid identification wrote into `mkdtemp` directories;
   both now use `core.workspace.work_dir` (scoped, prefixes counted by `ops.health`), and a
   supplied work_dir is never deleted.
2. MULTIPIECE draws every piece of a flat set (ornaments x6, placemat pair) on the hero, but
   the 340 px legibility check still expected 1 piece for a flat form. The expectation now
   reads the CIR's `make`; the legibility thresholds are unchanged.

Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_w4_imgfix.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
_TMP = tempfile.mkdtemp(prefix="w4_imgfix_")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")

from PIL import Image  # noqa: E402

from brambleloop.ops import health  # noqa: E402
from brambleloop.publish import disclosed_listing as DL  # noqa: E402
from brambleloop.visual import inspect as I  # noqa: E402
from brambleloop.visual.render_verification import authoritative_cir  # noqa: E402


def test_the_new_prefixes_are_counted_and_no_mkdtemp_remains():
    assert {"hero-review-", "grid-identify-"} <= set(health.TEMP_PREFIXES)
    for rel in ("visual/hero_review.py", "visual/inspect.py"):
        src = (ROOT / "src" / "brambleloop" / rel).read_text()
        assert "mkdtemp(" not in src, rel


def test_the_grid_check_leaves_nothing_and_never_deletes_a_supplied_dir():
    img = os.path.join(_TMP, "hero.png")
    Image.new("RGB", (400, 400), (200, 190, 180)).save(img)

    class P:
        model, cost_per_1k_input_cad, cost_per_1k_output_cad = "m", 0.0, 0.0

        def see(self, *a, **k):
            raise OSError("stub refuses")

    before = set(os.listdir(tempfile.gettempdir()))
    I.identify_at_grid(img, families=["coaster"], provider=P())
    after = {d for d in os.listdir(tempfile.gettempdir()) if d.startswith("grid-identify-")}
    assert not (after - before), after - before
    keep = tempfile.mkdtemp(dir=_TMP)
    Path(keep, "mine").write_text("x")
    I.identify_at_grid(img, families=["coaster"], provider=P(), work_dir=keep)
    assert Path(keep, "mine").exists()


def test_a_flat_set_hero_reads_as_every_piece_at_340_px():
    cases = {"nordic-star-ornaments": 6, "mosaic-placemat-pair": 2}
    assert cases
    for slug, n in cases.items():
        rec = DL.build(authoritative_cir(slug))
        leg = rec["qa"]["frames"]["hero"]["legibility_340"]
        assert leg["expected_pieces"] == n and leg["pieces"] == n, (slug, leg)
        assert rec["usable_as_listing_asset"], rec["launch_blocked"]


if __name__ == "__main__":
    failures = 0
    tests = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
    assert tests
    for name, test in tests:
        try:
            test()
            print("OK  ", name)
        except Exception as exc:  # noqa: BLE001
            failures += 1
            import traceback

            traceback.print_exc()
            print("FAIL", name, type(exc).__name__, str(exc)[:400])
    print(f"{len(tests) - failures}/{len(tests)} passing")
    shutil.rmtree(_TMP, ignore_errors=True)
    sys.exit(bool(failures))
