"""Shipped copies of the committed W4 JSONs the Command Center reads (the image has no research/).

`python -m brambleloop.app.command_center.snapshots` refreshes them from research/final_build/w4/;
tests/test_w4_cc_snapshots.py fails when a copy differs from its source.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parents[4] / "research" / "final_build" / "w4"
NAMES = ("COMPLETION_BOARD.json", "VISUAL_STATUS.json", "OWNER_ACTIONS.json")


def refresh() -> list[str]:
    done = []
    for name in NAMES:
        src = SOURCE / name
        if src.exists():
            shutil.copyfile(src, HERE / name)
            done.append(name)
    return done


if __name__ == "__main__":  # pragma: no cover
    print("refreshed", refresh())
    sys.exit(0)
