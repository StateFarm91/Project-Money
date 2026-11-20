"""W4-INTEG4: the owner-manual experiment records the runtime seeds from ship in the image.

`visual.image_production` seeds learning rows and wardrobe history (so no later listing reuses
an experiment's outfit) from `visual.repair_routes.experiment_records()`. Those records lived
only under research/, which the production image does not contain (Dockerfile copies src/,
release/, tests/), so in production the seed silently found nothing. They now ship under
src/brambleloop/visual/assets/owner_experiments/, byte-identical to the research records.

Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_w4_integ4_shipped_records.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.visual import repair_routes as RR  # noqa: E402

RESEARCH = ROOT / "research/final_build/w4/flux_experiments"


def test_every_research_record_ships_byte_identical_under_src():
    research = {p.parent.name: p.read_bytes() for p in RESEARCH.glob("*/RECORD.json")}
    shipped = {p.parent.name: p.read_bytes() for p in RR.experiment_records()}
    assert research, "the scan is not vacuous"
    assert shipped == research, (sorted(shipped), sorted(research))


def test_the_runtime_reads_inside_src_only():
    src = (ROOT / "src").resolve()
    assert src in RR.EXPERIMENTS_DIR.resolve().parents
    assert RR.EXPERIMENT_RECORD.exists() and RR._record() is not None
    assert len(RR.experiment_records()) >= 2


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    assert tests
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"OK   {name}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {name}: {type(exc).__name__}: {exc}"[:1500])
    print(f"{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
