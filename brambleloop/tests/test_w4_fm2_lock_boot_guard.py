"""F-416 (W4-FM2): the hash-locked dependency set is enforced inside the running service.

`scripts/supply_chain.py verify --strict` proves the committed lock and the Dockerfile
(digest-pinned base, versioned apt font, `pip --require-hashes --no-deps -r requirements.lock`)
at build time. The runtime consumer is the boot guard `ops/release_record.py`, run at import of
`app/main.py`: `requirements.lock` is part of the deployable tree digest the tracked release
record must name, so an image whose lock differs from the one the release-eligible suite ran on
is forced to SHADOW on the platform (or refused). These tests prove that leg on a throwaway
build directory -- no network, no deploy.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from brambleloop.ops import release_record as R  # noqa: E402

SHA = "d" * 40
LOCK = "x==1 --hash=sha256:" + "a" * 64 + "\n"


def _build(lock: str = LOCK) -> Path:
    root = Path(tempfile.mkdtemp(prefix="fm2-lockguard-"))
    for rel, text in (("src/brambleloop/app.py", "VERSION = 1\n"), ("requirements.lock", lock)):
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    suite = {"run_id": "run1", "git_sha": SHA, "release_eligible": True, "status": "passed",
             "scope": "full", "suites_failing": 0, "failing_suites": []}
    sb = json.dumps(suite).encode()
    lb = f"RUN ID: run1\nGIT SHA: {SHA}\nTOTAL PASSING: 9 ; suites failing: 0\n".encode()
    runs = root / "release" / "suite_runs"
    runs.mkdir(parents=True)
    (runs / "run1.json").write_bytes(sb)
    (runs / "run1.log").write_bytes(lb)
    rec = {"sha": SHA, "release_eligible": True,
           "source_tree_sha256": R.filesystem_digest(root),
           "suite_record": {"path": "suite_runs/run1.json", "sha256": hashlib.sha256(sb).hexdigest()},
           "suite_log": {"path": "suite_runs/run1.log", "sha256": hashlib.sha256(lb).hexdigest()}}
    (root / "release" / f"RELEASE_{SHA}.json").write_text(json.dumps(rec))
    return root


def test_the_lock_is_part_of_the_digest_the_boot_guard_checks():
    assert "requirements.lock" in R.DEPLOYABLE_FILES and R.deployable("requirements.lock")
    a, b = _build(), _build(LOCK.replace("x==1", "x==2"))
    try:
        assert R.filesystem_digest(a) != R.filesystem_digest(b)
    finally:
        shutil.rmtree(a, ignore_errors=True)
        shutil.rmtree(b, ignore_errors=True)


def test_a_rebuilt_image_with_an_unrecorded_lock_is_forced_to_shadow():
    root = _build()
    try:
        env = {"RAILWAY_ENVIRONMENT": "production", "BRAMBLELOOP_PHASE": "limited_production"}
        ok = R.apply_at_import(env, root=root)
        assert ok["ok"] and ok["action"] == "none", ok
        # A rebuild that resolved a different (or unhashed) dependency set: same code, new lock.
        (root / "requirements.lock").write_text("x==1\n")
        bad = R.apply_at_import(env, root=root)
        assert not bad["ok"] and bad["action"] == "forced_shadow", bad
        assert env["BRAMBLELOOP_PHASE"] == "shadow"
        try:
            R.apply_at_import({"RAILWAY_SERVICE_ID": "s", R.MODE_ENV: "refuse"}, root=root)
        except SystemExit:
            pass
        else:
            raise AssertionError("refuse mode started an image whose lock was not recorded")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_the_image_installs_only_the_hashed_lock_and_main_runs_the_guard_first():
    import supply_chain as SC

    docker = (ROOT / "Dockerfile").read_text()
    v = SC.verify(lock_text=(ROOT / "requirements.lock").read_text(),
                  reqs_text=(ROOT / "requirements.txt").read_text(), docker_text=docker)
    assert not v["problems"], v["problems"]
    assert not v.get("findings"), v.get("findings")   # strict: digest base, versioned apt
    assert "COPY release ./release" in docker and "requirements.lock" in docker
    main = (ROOT / "src" / "brambleloop" / "app" / "main.py").read_text()
    assert main.index("apply_at_import()") < main.index("db = Database()")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    assert tests
    failed = 0
    for t in tests:
        try:
            t()
            print(f"OK {t.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__} {type(exc).__name__} {exc}")
    print(f"{len(tests) - failed}/{len(tests)} passing")
    sys.exit(1 if failed else 0)
