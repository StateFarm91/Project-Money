"""Test temporary-directory hygiene: nothing a test makes in TMPDIR survives the test (W3-HYG).

The defect (2026-10-06): /tmp held 16.7 GB in more than 7,000 entries -- about 900 new ones an
hour while suites ran -- left by roughly two hundred test files calling `tempfile.mkdtemp`
(which removes nothing), mkstemp / `NamedTemporaryFile(delete=False)` files, and the src code
they drive writing into `gettempdir()`. It filled the disk and invalidated a test run.

The fix has two layers, and this file pins both on the success AND the failure paths:

1. `tests/_tmp.py` -- every test file that creates temporary files installs a per-process
   sandbox (TMPDIR + `tempfile.tempdir`), removed at exit, on an uncaught exception, on
   SIGTERM and on Ctrl-C. Subprocesses inherit it.
2. `run_tests.sh` -- each run exports a fresh per-run TMPDIR (and each suite its own inside
   it), counts and reports what each suite left, removes it, and removes the whole run
   directory by trap; a later run removes the directory of a run that was SIGKILLed.

And a static guard: new code that calls mkdtemp/mkstemp/NamedTemporaryFile(delete=False)/
gettempdir without a cleanup path fails here.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit

import ast
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]          # brambleloop/
TESTS = ROOT / "tests"
REPO = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))
PY = sys.executable

# Formerly-leaking test files, run for real in (a). Chosen from the measured leakers in
# research/final_build/w3/handoff_HYG.md as the cheapest that each left entries in /tmp.
SAMPLE = ("test_waiter", "test_deploy_path", "test_cert_unique_value", "test_protected_bands")


def _private(tag: str) -> str:
    """A directory to hand a child as its TMPDIR; created inside our own sandbox."""
    return tempfile.mkdtemp(prefix=f"hyg-{tag}-")


def _left(d: str) -> list[str]:
    out = []
    for base, dirs, files in os.walk(d):
        out += [os.path.relpath(os.path.join(base, x), d) for x in dirs + files]
    return sorted(out)


def _child(code: str, tmpdir: str, **kw) -> subprocess.Popen:
    env = {**os.environ, "TMPDIR": tmpdir, "PYTHONPATH": str(ROOT / "src")}
    return subprocess.Popen([PY, "-c", f"import sys; sys.path.insert(0, {str(TESTS)!r})\n" + code],
                            env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, **kw)


# What a typical leaky test did, in one child: every creation API, plus a grandchild.
MAKE_EVERYTHING = r"""
import os, subprocess, sys, tempfile
import _tmp; root = _tmp.install()
d = tempfile.mkdtemp(prefix="v11a-kpi-")
open(os.path.join(d, "uv.sqlite"), "wb").write(b"x" * 4096)
fd, png = tempfile.mkstemp(suffix=".png"); os.write(fd, b"png"); os.close(fd)
with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
    fh.write("{}")
open(os.path.join(tempfile.gettempdir(), "fixed-name.txt"), "w").write("x")
subprocess.run([sys.executable, "-c",
                "import tempfile; open(tempfile.mkstemp()[1], 'w').write('grandchild')"],
               check=True)
assert d.startswith(root) and png.startswith(root) and fh.name.startswith(root)
print("SANDBOX", root, flush=True)
"""


# --- (a) success path -----------------------------------------------------------------------

def test_a_child_that_uses_every_temp_api_and_exits_cleanly_leaves_nothing():
    tmp = _private("ok")
    p = _child(MAKE_EVERYTHING + "print('done')\n", tmp)
    out, err = p.communicate(timeout=60)
    assert p.returncode == 0, err
    assert "SANDBOX" in out and "done" in out
    assert _left(tmp) == [], _left(tmp)


def test_formerly_leaking_test_files_leave_their_tmpdir_empty_when_they_pass():
    assert SAMPLE, "the sample of formerly-leaking tests is empty"
    for name in SAMPLE:
        tmp = _private(name)
        env = {**os.environ, "TMPDIR": tmp, "PYTHONPATH": "src"}
        r = subprocess.run([PY, f"tests/{name}.py"], cwd=ROOT, env=env, capture_output=True,
                           text=True, timeout=900)
        assert r.returncode == 0, (name, r.stdout[-800:], r.stderr[-800:])
        assert re.search(r"^OK", r.stdout, re.M), name
        assert _left(tmp) == [], (name, _left(tmp)[:20])


# --- (b) failure / exception paths ---------------------------------------------------------

def test_a_child_that_raises_half_way_leaves_nothing():
    tmp = _private("raise")
    p = _child(MAKE_EVERYTHING + "raise RuntimeError('boom half way')\n", tmp)
    out, err = p.communicate(timeout=60)
    assert p.returncode != 0 and "boom half way" in err, (p.returncode, err[-400:])
    assert "SANDBOX" in out
    assert _left(tmp) == [], _left(tmp)


def test_a_child_that_fails_an_assertion_and_sys_exits_nonzero_leaves_nothing():
    tmp = _private("exit")
    p = _child(MAKE_EVERYTHING + "print('FAIL test_x'); sys.exit(1)\n", tmp)
    out, err = p.communicate(timeout=60)
    assert p.returncode == 1, err
    assert _left(tmp) == [], _left(tmp)


def test_a_child_terminated_by_sigterm_or_interrupted_leaves_nothing():
    for sig in (signal.SIGTERM, signal.SIGINT):
        tmp = _private(f"sig{int(sig)}")
        p = _child(MAKE_EVERYTHING + "import time; time.sleep(60)\n", tmp)
        line = p.stdout.readline()
        assert line.startswith("SANDBOX"), line
        assert _left(tmp), "the child made nothing, so this would prove nothing"
        p.send_signal(sig)
        p.communicate(timeout=30)
        assert p.returncode != 0, sig
        assert _left(tmp) == [], (sig, _left(tmp))


def test_a_forked_child_does_not_remove_its_parents_sandbox():
    tmp = _private("fork")
    code = ("import os, tempfile, _tmp\nroot = _tmp.install()\n"
            "pid = os.fork()\nif pid == 0:\n    raise SystemExit(0)\n"
            "os.waitpid(pid, 0)\nassert os.path.isdir(root), 'child removed the parent sandbox'\n"
            "tempfile.mkdtemp(); print('parent-ok')\n")
    p = _child(code, tmp)
    out, err = p.communicate(timeout=60)
    assert p.returncode == 0 and "parent-ok" in out, err
    assert _left(tmp) == [], _left(tmp)


def test_scoped_removes_its_directory_when_the_block_raises():
    seen = []
    try:
        with _tmp.scoped("hyg-scoped-") as d:
            seen.append(d)
            Path(d, "f").write_text("x")
            raise ValueError("inside")
    except ValueError:
        pass
    assert seen and not os.path.exists(seen[0])


def test_install_is_idempotent_and_points_tempfile_and_the_environment_at_the_sandbox():
    root = _tmp.install()
    assert _tmp.install() == root == _tmp.root()
    assert tempfile.gettempdir() == root and os.environ["TMPDIR"] == root
    assert os.path.basename(root).startswith(_tmp.PREFIX)


# --- (c) the harness ------------------------------------------------------------------------

LEAK = ('import tempfile\nd = tempfile.mkdtemp(prefix="leaky-")\nopen(d + "/x", "w").write("y" * 100)\n'
        'open(tempfile.mkstemp()[1], "w").write("z")\nprint("OK   test_leaks")\n')
LEAK_AND_FAIL = LEAK + 'print("FAIL test_after_leak")\nraise SystemExit(1)\n'


def _harness_repo():
    import test_run_tests_script as RT
    repo = RT._sandbox()
    (repo / "tests" / "test_leak.py").write_text(LEAK)
    (repo / "tests" / "test_leakfail.py").write_text(LEAK_AND_FAIL)
    RT._git(repo, "add", "-A")
    RT._git(repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q",
            "-m", "leaky suites")
    return RT, repo


def test_the_harness_reports_each_suites_leak_and_removes_its_run_tmpdir_on_failure():
    RT, repo = _harness_repo()
    tmp = _private("harness")
    try:
        r = RT._run(repo, "test_leak,test_leakfail,test_pass", TMPDIR=tmp)
        assert r.returncode == 1, r.stdout[-1500:]          # test_leakfail fails
        assert "== tests/test_leak.py" in r.stdout
        blocks = re.split(r"^== ", r.stdout, flags=re.M)
        by = {b.split("\n", 1)[0].strip(): b for b in blocks[1:]}
        assert set(by) == {"tests/test_leak.py", "tests/test_leakfail.py", "tests/test_pass.py"}
        assert "TMP LEAK: 2 entries" in by["tests/test_leak.py"], by["tests/test_leak.py"]
        assert "TMP LEAK: 2 entries" in by["tests/test_leakfail.py"]
        assert "TMP LEAK:" not in by["tests/test_pass.py"]
        m = re.search(r"^TMP LEAKED: (\d+) entries, (\d+) bytes across (\d+) suites", r.stdout, re.M)
        assert m and m.group(1) == "4" and int(m.group(2)) >= 202 and m.group(3) == "2", r.stdout[-600:]
        [rec] = RT._records(repo)
        assert rec["tmp_leak_entries"] == 4 and rec["tmp_leak_bytes"] >= 202, rec
        assert rec["tmp_leaking_suites"] == ["tests/test_leak.py", "tests/test_leakfail.py"]
        assert _left(tmp) == [], _left(tmp)           # the run's TMPDIR went with the run
    finally:
        shutil.rmtree(repo, ignore_errors=True)


def test_tmp_leak_strict_makes_a_passing_but_leaking_suite_fail():
    RT, repo = _harness_repo()
    tmp = _private("strict")
    try:
        r = RT._run(repo, "test_leak", TMPDIR=tmp, TMP_LEAK_STRICT="1")
        assert r.returncode == 1 and "TMP_LEAK_STRICT=1" in r.stdout, r.stdout[-800:]
        [rec] = RT._records(repo)
        assert rec["failing_suites"] == ["tests/test_leak.py"], rec
        assert _left(tmp) == []
    finally:
        shutil.rmtree(repo, ignore_errors=True)


def _wait_for(pred, timeout=30.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pred():
            return True
        time.sleep(0.05)
    return False


def test_the_harness_removes_its_run_tmpdir_when_it_is_terminated():
    RT, repo = _harness_repo()
    tmp, gate = _private("term"), repo / "gate"
    try:
        e = RT._env(SUITES="test_gate", GATE_FILE=str(gate), TMPDIR=tmp)
        p = subprocess.Popen(["bash", str(repo / "run_tests.sh")], stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, env=e)
        assert _wait_for(lambda: Path(str(gate) + ".started").exists())
        assert _left(tmp), "the run made no TMPDIR, so this would prove nothing"
        p.terminate()
        p.communicate(timeout=60)
        assert p.returncode == 130, p.returncode
        assert _left(tmp) == [], _left(tmp)
    finally:
        gate.write_text("go")
        shutil.rmtree(repo, ignore_errors=True)


def test_a_run_killed_with_sigkill_is_swept_by_the_next_run():
    RT, repo = _harness_repo()
    tmp, gate = _private("kill"), repo / "gate"
    try:
        e = RT._env(SUITES="test_gate", GATE_FILE=str(gate), TMPDIR=tmp)
        p = subprocess.Popen(["bash", str(repo / "run_tests.sh")], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, env=e)
        assert _wait_for(lambda: Path(str(gate) + ".started").exists())
        p.kill()                                          # no trap can run
        p.wait(timeout=30)
        runs = [x for x in os.listdir(tmp) if x.startswith("brambleloop-run-")]
        assert len(runs) == 1, os.listdir(tmp)
        assert os.path.exists(os.path.join(tmp, runs[0], ".owner"))
        gate.write_text("go")                             # let the orphaned suite finish
        assert _wait_for(lambda: any(n.endswith(".leak") for _b, _d, f in
                                     os.walk(os.path.join(tmp, runs[0])) for n in f))
        time.sleep(0.3)
        r = RT._run(repo, "test_pass", TMPDIR=tmp)
        assert r.returncode == 0, r.stdout[-800:]
        assert "removing the run directory of a dead run" in r.stdout
        assert _left(tmp) == [], _left(tmp)
    finally:
        gate.write_text("go")
        shutil.rmtree(repo, ignore_errors=True)


# --- (d) static guard -----------------------------------------------------------------------

CREATORS = {"mkdtemp", "mkstemp", "gettempdir"}

# Call sites outside tests/ that may create temp files without a cleanup call in the same
# function. Each needs a reason; empty is the goal.
ALLOWED: dict[str, str] = {}

SCANNED_OUTSIDE_TESTS = [ROOT / "src", ROOT / "scripts", REPO / "ops"]
CLEANUP = re.compile(r"rmtree|atexit\.register|\.unlink\(|os\.remove\(|TemporaryDirectory|"
                     r"BackgroundTask\(shutil\.rmtree")


def _creator_calls(tree: ast.AST) -> list[ast.Call]:
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)
        if name in CREATORS:
            out.append(node)
        elif name == "NamedTemporaryFile" and any(
                k.arg == "delete" and isinstance(k.value, ast.Constant) and k.value.value is False
                for k in node.keywords):
            out.append(node)
    return out


def _installs_at(tree: ast.Module) -> int | None:
    for st in tree.body:
        if (isinstance(st, ast.Expr) and isinstance(st.value, ast.Call)
                and isinstance(st.value.func, ast.Attribute) and st.value.func.attr == "install"
                and getattr(st.value.func.value, "id", None) == "_tmp"):
            return st.lineno
    return None


def test_every_test_file_that_creates_temp_files_installs_the_sandbox_first():
    files = sorted(p for p in TESTS.glob("*.py") if p.name not in ("_tmp.py", "__init__.py"))
    assert len(files) > 400, len(files)
    creators, missing = [], []
    for p in files:
        tree = ast.parse(p.read_text(), filename=str(p))
        calls = _creator_calls(tree)
        if not calls:
            continue
        creators.append(p.name)
        at = _installs_at(tree)
        first = min(c.lineno for c in calls)
        if at is None or at > first:
            missing.append(f"{p.name}:{first}")
    assert len(creators) > 150, len(creators)            # the guard is looking at real files
    assert not missing, ("these test files create temporary files without "
                         "`import _tmp; _tmp.install()` at the top (tests/_tmp.py): "
                         + ", ".join(missing))


def test_code_outside_tests_that_creates_temp_files_has_a_cleanup_path():
    offenders, seen = [], 0
    roots = [r for r in SCANNED_OUTSIDE_TESTS if r.is_dir()]
    assert roots, SCANNED_OUTSIDE_TESTS
    for base in roots:
        for p in sorted(base.rglob("*.py")):
            if ".venv" in p.parts:
                continue
            src = p.read_text()
            tree = ast.parse(src, filename=str(p))
            calls = _creator_calls(tree)
            if not calls:
                continue
            funcs = [n for n in ast.walk(tree)
                     if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            for c in calls:
                seen += 1
                enclosing = [f for f in funcs if f.lineno <= c.lineno <= (f.end_lineno or 0)]
                scope = min(enclosing, key=lambda f: f.end_lineno - f.lineno) if enclosing else tree
                text = ast.get_source_segment(src, scope) if enclosing else src
                name = getattr(c.func, "attr", getattr(c.func, "id", ""))
                if name == "gettempdir":
                    continue                         # reading the location creates nothing
                key = f"{p.relative_to(REPO)}:{c.lineno}"
                if not CLEANUP.search(text or "") and key not in ALLOWED:
                    offenders.append(key)
    assert seen > 0, "the scan found no temp creation at all, which means it is not scanning"
    assert not offenders, ("temp files created with no cleanup path (rmtree/atexit/unlink/"
                           "TemporaryDirectory) in the same function: " + ", ".join(offenders))


def test_the_guard_itself_catches_a_bare_mkdtemp_and_a_delete_false_tempfile():
    bad = ast.parse("import tempfile\nd = tempfile.mkdtemp()\n"
                    "f = tempfile.NamedTemporaryFile(delete=False)\n")
    good = ast.parse("import tempfile\nwith tempfile.TemporaryDirectory() as d: pass\n"
                     "f = tempfile.NamedTemporaryFile()\n")
    assert len(_creator_calls(bad)) == 2 and _creator_calls(good) == []
    assert _installs_at(ast.parse("import _tmp; _tmp.install()\n")) == 1
    assert _installs_at(bad) is None


def test_the_production_temp_census_and_the_test_sandbox_agree():
    from brambleloop.ops import health as H
    assert H.TEMP_PREFIXES, "the production census lists no prefixes"
    harness = (ROOT / "run_tests.sh").read_text()
    assert "brambleloop-run-" in H.TEMP_PREFIXES and 'brambleloop-run-XXXXXXXX' in harness
    # The test sandbox is not a production directory: it must neither be counted as one nor
    # hide one, so no production prefix may be a prefix of it or start with it.
    for pre in H.TEMP_PREFIXES:
        assert not _tmp.PREFIX.startswith(pre) and not pre.startswith(_tmp.PREFIX), pre


if __name__ == "__main__":
    fails = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    assert tests
    for name, fn in tests:
        try:
            fn()
            print("OK  ", name)
        except Exception as e:  # noqa: BLE001
            fails += 1
            print("FAIL", name, repr(e)[:2000])
    sys.exit(1 if fails else 0)
