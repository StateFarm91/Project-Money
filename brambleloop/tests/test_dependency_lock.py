"""The dependency lock: the image installs exactly what the suite ran on (F-158, F-416).

`requirements.txt` carried only `>=` lower bounds, so every rebuild of the production image was
free to pull a major version the suite had never executed. These tests pin the three things
that make that impossible, and each is checked against the real files rather than a fixture:

  * the lock covers every requirement, at a version that satisfies it, with hashes;
  * the lock is the installed closure of this interpreter -- same names, same versions -- so a
    venv upgraded without regenerating the lock fails here instead of drifting silently;
  * the Dockerfile installs the lock with `--require-hashes` and never the unpinned file.

Nothing here touches the network; hashes were fetched once by `scripts/lock_requirements.py`.
"""
from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import lock_requirements as L  # noqa: E402


def test_every_requirements_txt_entry_is_pinned_in_the_lock_at_a_satisfying_version():
    reqs = L.read_requirements()
    lock = L.read_lock()
    assert len(reqs) >= 10, "requirements.txt parsed to almost nothing; the check is vacuous"
    for req in reqs:
        key = L.canonicalize_name(req.name)
        assert key in lock, f"{req.name} is required but not in requirements.lock"
        version = lock[key][1]
        assert version in req.specifier, f"lock pins {req.name}=={version}, outside `{req}`"


def test_every_lock_entry_is_an_exact_pin_carrying_at_least_one_sha256():
    lock = L.read_lock()
    assert len(lock) >= 20
    for key, (name, version, hashes) in lock.items():
        assert re.fullmatch(r"[0-9A-Za-z.+!-]+", version), f"{name} pin {version!r} is not exact"
        assert hashes, f"{name}=={version} has no hash; --require-hashes would refuse the build"
        assert all(len(h) == 64 for h in hashes)


def test_the_lock_is_exactly_the_installed_closure_of_the_interpreter_running_the_suite():
    # The whole point of the lock: behaviour in the image matches what this suite ran on. If
    # somebody upgrades the venv, or adds a requirement, without regenerating the lock, this is
    # where it fails -- not in production.
    found = L.closure(L.read_requirements())
    lock = L.read_lock()
    drift = L.change_record({k: (v[0], v[1]) for k, v in lock.items()}, found)
    assert not drift, "lock and installed venv disagree: " + "; ".join(drift)


def test_uvicorn_standard_extras_are_followed_into_the_lock():
    # A closure walk that ignored extras would lock uvicorn but not what `[standard]` pulls in,
    # and --require-hashes would then refuse the build on the first unlisted dependency.
    lock = L.read_lock()
    for dep in ("uvloop", "httptools", "websockets", "watchfiles"):
        assert dep in lock, f"uvicorn[standard] dependency {dep} missing from the lock"


def test_the_dockerfile_installs_the_lock_with_require_hashes_and_never_the_unpinned_file():
    text = (ROOT / "Dockerfile").read_text()
    runs = [ln for ln in text.splitlines() if ln.strip().startswith("RUN") and "pip install" in ln]
    assert runs, "no pip install in the Dockerfile"
    for ln in runs:
        assert "-r requirements.lock" in ln and "--require-hashes" in ln, ln
        assert "requirements.txt" not in ln, ln
    assert re.search(r"^COPY .*requirements\.lock", text, re.M), "lock is not copied into image"


def test_a_lock_line_that_is_not_an_exact_pin_or_a_hash_is_refused_rather_than_skipped():
    with tempfile.TemporaryDirectory() as tmp:
        bad = Path(tmp) / "requirements.lock"
        bad.write_text("fastapi>=0.115 \\\n    --hash=sha256:" + "0" * 64 + "\n")
        try:
            L.read_lock(bad)
        except SystemExit as e:
            assert "unrecognised" in str(e)
        else:
            raise AssertionError("a range pin was accepted as a lock entry")


def test_the_change_record_names_added_removed_and_changed_distributions():
    old = {"a": ("a", "1.0"), "b": ("b", "1.0")}
    new = {"a": ("a", "2.0"), "c": ("c", "1.0")}
    rec = L.change_record(old, new)
    assert rec == ["CHANGED  a 1.0 -> 2.0", "REMOVED  b==1.0", "ADDED    c==1.0"], rec


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
