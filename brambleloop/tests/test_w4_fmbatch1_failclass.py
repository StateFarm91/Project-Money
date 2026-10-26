"""W4-FMBATCH1: F-150 Failure Classification Before Revert.

F-150: "Classify ENOSPC/permissions/network/provider failures before reverting code."
The real run_tests.sh is run in a sandbox repository (tests/test_run_tests_script.py's
helpers) with one suite that fails on a full disk, one on an assertion and one that passes.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "tests")]

import classify_failure as CF  # noqa: E402

ENOSPC = '''import sys
print("OSError: [Errno 28] No space left on device: '/tmp/x'")
print("FAIL test_writes")
sys.exit(1)
'''
ASSERT = '''import sys
print("AssertionError: expected 3, got 4")
print("FAIL test_math")
sys.exit(1)
'''


def test_each_environment_class_is_named_and_a_code_failure_is_not():
    cases = {
        "OSError: [Errno 28] No space left on device": "ENOSPC",
        "PermissionError: [Errno 13] Permission denied: '/data'": "PERMISSION",
        "urllib.error.URLError: <urlopen error [Errno -3] Temporary failure in name "
        "resolution>": "NETWORK",
        "anthropic.APIStatusError: {'type': 'overloaded_error'}": "PROVIDER",
    }
    assert cases
    for text, cls in cases.items():
        got = CF.classify("Traceback...\n" + text + "\nFAIL x")
        assert got is not None and got[0] == cls, (text, got)
    assert CF.classify("AssertionError: expected 3, got 4\nFAIL test_math") is None
    assert CF.classify("") is None


def test_review_f6_an_assertion_quoting_an_environment_phrase_is_a_code_failure():
    for text in ('FAIL test_owner_route_refuses\nAssertionError: expected 401, '
                 'body={"error": "Permission denied"}',
                 'AssertionError: retry loop logged "Connection refused" 0 times, expected 3',
                 'Traceback (most recent call last):\n  File "t.py", line 3\n'
                 '    assert "No space left on device" not in log\nAssertionError',
                 'FAIL test_x Connection refused'):
        assert CF.classify(text) is None, text


def test_run_tests_names_the_environment_failure_and_not_the_assertion():
    import test_run_tests_script as RT

    repo = RT._sandbox()
    try:
        (repo / "scripts").mkdir()
        shutil.copy(ROOT / "scripts" / "classify_failure.py", repo / "scripts")
        (repo / "tests" / "test_disk.py").write_text(ENOSPC)
        (repo / "tests" / "test_math.py").write_text(ASSERT)
        RT._git(repo, "add", "-A")
        RT._git(repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit",
                "-q", "-m", "suites")
        r = RT._run(repo, "test_disk,test_math,test_pass")
        assert r.returncode == 2, r.stdout[-1500:]
        blocks = {b.split("\n", 1)[0].strip(): b
                  for b in re.split(r"^== ", r.stdout, flags=re.M)[1:]}
        assert "ENVIRONMENT FAILURE (ENOSPC)" in blocks["tests/test_disk.py"], blocks
        assert "check the environment before reverting" in blocks["tests/test_disk.py"]
        assert "ENVIRONMENT FAILURE (" not in blocks["tests/test_math.py"]
        assert "ENVIRONMENT FAILURE (" not in blocks["tests/test_pass.py"]
        assert re.search(r"^ENVIRONMENT FAILURES: 1 of the 2 failing suites", r.stdout, re.M), \
            r.stdout[-600:]
    finally:
        shutil.rmtree(repo, ignore_errors=True)


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print("OK  ", t.__name__)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            import traceback
            traceback.print_exc()
            print("FAIL", t.__name__, exc)
    print(f"{len(tests) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
