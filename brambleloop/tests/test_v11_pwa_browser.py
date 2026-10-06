"""Browser proof for the Owner Command Center PWA (v1.1 lane D) at phone size (390x844).

Runs tests/fixtures/cc_mock/check.mjs under Node with the preinstalled Playwright Chromium
(PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers; never installs anything). The check serves the
real static directory behind a local mock of lane C's API contract (the mock lives in
tests/fixtures/cc_mock and is never shipped) and asserts, per tab: no console errors (CSP
violations included), no horizontal scroll, tap-size floor; plus UNKNOWN money renders
"Unknown", approvals show evidence and require confirmation (+ step-up), CSRF/nonce headers
are sent, the service worker never caches /api, and offline is shown honestly.

Its OK/FAIL lines are passed through. If Node or Playwright is unavailable this prints a SKIP
line and no OK line, so the suite harness reports it as proving nothing rather than passing.
Set CC_SCREENS=<dir> to also write the evidence screenshots.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECK = ROOT / "tests" / "fixtures" / "cc_mock" / "check.mjs"


def main() -> int:
    node = shutil.which("node")
    if not node:
        print("SKIP browser check: node not found")
        return 0
    env = dict(os.environ)
    env.setdefault("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers")
    args = [node, str(CHECK)]
    if env.get("CC_SCREENS"):
        args += ["--screens", env["CC_SCREENS"]]
    proc = subprocess.run(args, cwd=ROOT, env=env, capture_output=True, text=True, timeout=600)
    out = proc.stdout + (("\n" + proc.stderr) if proc.stderr.strip() else "")
    print(out.rstrip())
    if proc.returncode == 3:
        print("SKIP browser check: playwright module not available")
        return 0
    if proc.returncode != 0 and "FAIL" not in proc.stdout:
        print(f"FAIL browser check exited {proc.returncode}")
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
