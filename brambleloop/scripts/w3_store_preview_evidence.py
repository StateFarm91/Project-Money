"""Wave 3 lane B: regenerate the Owner Store Preview v2 evidence.

Renders v1 and v2 at 390 and 1280 px plus the comparison page into a temporary directory,
measures and screenshots them in Chromium (scripts/w3_store_preview_measure.mjs, Playwright
from the global node install, browsers at $PLAYWRIGHT_BROWSERS_PATH), and writes
research/final_build/w3/evidence/B_metrics.json and B_*.jpg (small JPEGs). Offline.

Run: cd brambleloop && PYTHONPATH=src .venv/bin/python scripts/w3_store_preview_evidence.py
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.store_foundation import preview  # noqa: E402

OUT = ROOT / "research" / "final_build" / "w3" / "evidence"


def main() -> int:
    now = datetime.now(timezone.utc)
    tmp = Path(tempfile.mkdtemp(prefix="w3b_"))
    try:
        for vp in ("mobile", "desktop"):
            for variant, name in (("v2", "v2"), ("standard", "v1")):
                (tmp / f"{name}_{vp}.html").write_text(
                    preview.render_preview(None, vp, now=now, variant=variant))
        (tmp / "compare_desktop.html").write_text(
            preview.render_preview(None, "desktop", now=now, variant="compare"))
        env = dict(os.environ)
        env.setdefault("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers")
        shots = tmp / "shots"
        subprocess.run(["node", str(ROOT / "scripts" / "w3_store_preview_measure.mjs"), str(tmp),
                        str(shots), "--shots"], check=True, env=env, timeout=600)
        OUT.mkdir(parents=True, exist_ok=True)
        for old in OUT.glob("B_*"):
            old.unlink()
        for f in sorted(shots.iterdir()):
            shutil.copy(f, OUT / f.name)
        # second pass: the comparison page reads the metrics just measured
        two = tmp / "two"
        two.mkdir()
        (two / "compare_desktop.html").write_text(
            preview.render_preview(None, "desktop", now=now, variant="compare"))
        subprocess.run(["node", str(ROOT / "scripts" / "w3_store_preview_measure.mjs"), str(two),
                        str(two / "shots"), "--shots"], check=True, env=env, timeout=600)
        shutil.copy(two / "shots" / "B_compare_desktop.jpg", OUT / "B_compare_desktop.jpg")
        for f in sorted(OUT.glob("B_*")):
            print(f"{f.name}: {f.stat().st_size // 1024} KB")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
