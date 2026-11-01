"""Regenerate both tester kits through the one kit builder, and prove the rebuild reproducible.

W-PHYSFIX: `quality.tester_kit.build(out_dir, key)` now builds every kit from its own table
(`tester_kit.KITS`): the small basket (`basket_small`) and the hexagon coaster set
(`hexagon_coasters`). This script no longer swaps the module's constants. It builds each kit
twice into scratch directories, refuses to write if the two builds differ, then writes the kit
into research/final_build/w4/tester_kit/ and prints the digests.

Usage (from brambleloop/):  nice -n 19 python3 research/final_build/w4/tester_kit_coaster.py
                            [--check]   (compare with the committed kits; write nothing)
Nothing is sent, published, purchased or recorded; no database is touched.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]                                  # brambleloop/
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.quality import tester_kit  # noqa: E402

KIT_DIR = HERE / "tester_kit"


def main(check_only: bool = False) -> dict:
    out: dict = {}
    for key, spec in tester_kit.KITS.items():
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            first = tester_kit.build(Path(a), key)
            second = tester_kit.build(Path(b), key)
            if first["files"] != second["files"]:
                raise SystemExit(f"{key}: two builds differ: {first['files']} vs "
                                 f"{second['files']}")
            committed_path = KIT_DIR / spec["manifest"]
            committed = (json.loads(committed_path.read_text())
                         if committed_path.exists() else {})
            out[key] = {"slug": first["slug"], "version": first["version"],
                        "content_hash": first["content_hash"], "files": first["files"],
                        "manifest": spec["manifest"],
                        "matches_committed": committed == json.loads(
                            json.dumps(first, default=str))}
            if not check_only:
                for name in [*first["files"], spec["manifest"]]:
                    shutil.copyfile(Path(a) / name, KIT_DIR / name)
    return out


if __name__ == "__main__":
    print(json.dumps(main(check_only="--check" in sys.argv), indent=1))
