"""Review of 56f92eb9 H2: every A9 test file imports under `run_tests.sh`.

`run_tests.sh` runs each suite as `"$PY" tests/<file>.py` with no PYTHONPATH. Six A9 files
(defer_state, event_release, event_scope, owner_action_fence, parked_source_change,
sweep_isolation -- and source_binding, which they import) had no `sys.path` header, so each
crashed on import with `ModuleNotFoundError: brambleloop` and reported nothing. This loads
each A9 test module in a fresh interpreter, from an unrelated working directory, with
PYTHONPATH removed -- exactly the runner's conditions -- and requires the import to succeed.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS.parent / "src"))
sys.path.insert(0, str(TESTS))

# `python tests/<file>.py` puts the script's own directory first on sys.path and nothing else.
LOADER = ("import importlib.util as u, os, sys; p = sys.argv[1]; "
          "sys.path[0] = os.path.dirname(p); "
          "spec = u.spec_from_file_location('a9_probe', p); m = u.module_from_spec(spec); "
          "spec.loader.exec_module(m); print('IMPORTED')")


def _a9_files() -> list[Path]:
    files = sorted(p for p in TESTS.glob("test_*.py")
                   if ("_a9_" in p.name) and p.name != Path(__file__).name)
    assert len(files) >= 7, files
    return files


def test_every_a9_test_module_imports_without_pythonpath():
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    failed = {}
    with tempfile.TemporaryDirectory() as cwd:
        for path in _a9_files():
            run = subprocess.run([sys.executable, "-c", LOADER, str(path)], cwd=cwd, env=env,
                                 capture_output=True, text=True, timeout=300)
            if run.returncode != 0 or "IMPORTED" not in run.stdout:
                failed[path.name] = (run.stderr.strip().splitlines() or ["?"])[-1][:200]
    assert not failed, failed


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK   {name}")
            except Exception as exc:  # noqa: BLE001
                fails += 1
                print(f"FAIL {name} {exc!r}"[:2000])
    print(f"{fails} failure(s)")
    sys.exit(1 if fails else 0)
