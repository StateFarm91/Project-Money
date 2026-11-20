"""W4-CLOSE6: test-scratch hygiene rows F-145..F-148. The two paths W3-HYG did not pin are
pinned here, and so is the single-trap rule.

  F-145  "Full-suite runs use scoped TMPDIR with cleanup on success/failure/INT/TERM."
  F-146  "One cleanup function/trap; lint/test against a second EXIT trap silently
          replacing it."
  F-147  "Green tests do not prove cleanup; verify leftover scratch count/size after run."
  F-148  "Direct/single-suite runs receive the same scratch isolation."

W3-HYG (`tests/_tmp.py`, `run_tests.sh`, `tests/test_w3_tmp_hygiene.py`) built all four. It
pinned the failure path, TERM, SIGKILL recovery, the leak census, TMP_LEAK_STRICT and the
direct-run sandbox. It did not pin:
- the SUCCESS path of the harness;
- the INT (Ctrl-C) path of the harness;
- F-146's rule. The mapping asked for "a test against a second EXIT trap", and none existed.

These are operator tooling: run_tests.sh and tests/_tmp.py can never be imported by a runtime
root, so their ceiling is TESTED (aggregate.structural_producer). Closing the rows therefore
needs an integrator-accepted `completion_target` override (F-867). The proposal is
research/final_build/w4/OVERRIDES_PROPOSED_CLOSE6.json.

Run: cd brambleloop && PYTHONPATH=src:tests $PY tests/test_w4_close6_hygiene.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import re
import shutil
import signal
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

import test_w3_tmp_hygiene as hyg  # noqa: E402

RUN_TESTS = ROOT / "run_tests.sh"


def _traps(text: str) -> list[tuple[str, list[str]]]:
    """Every `trap HANDLER SIGNAL...` command outside comments, as (handler, signals)."""
    out = []
    for line in text.splitlines():
        code = line.split("#", 1)[0] if not line.lstrip().startswith("#") else ""
        for m in re.finditer(r"(?:^|;|&&|\|\|)\s*trap\s+('[^']*'|\"[^\"]*\"|-|\S+)\s+([A-Z ]+)",
                             code):
            out.append((m.group(1), m.group(2).split()))
    return out


def _exit_traps(text: str) -> list[str]:
    return [h for h, sigs in _traps(text) if "EXIT" in sigs and h != "-"]


def test_f146_exactly_one_exit_trap_and_interrupts_only_exit():
    text = RUN_TESTS.read_text()
    traps = _traps(text)
    assert len(traps) >= 2, traps                         # the scan is not vacuous
    assert _exit_traps(text) == ["_brambleloop_cleanup"], (
        "run_tests.sh must have ONE EXIT trap: a second `trap ... EXIT` replaces the first "
        f"rather than adding to it, and the run's TMPDIR would silently survive: {traps}")
    assert text.count("_brambleloop_cleanup() {") == 1, "one cleanup function"
    interrupts = [(h, s) for h, s in traps if {"INT", "TERM"} & set(s)]
    assert interrupts == [("'exit 130'", ["INT", "TERM"])], (
        "INT/TERM only mark the run interrupted and exit; the one EXIT trap cleans up", traps)
    # the guard catches what it exists to catch
    planted = text + "\ntrap 'rm -rf \"$outdir\"' EXIT\n"
    assert len(_exit_traps(planted)) == 2


def test_f145_a_green_run_removes_its_run_tmpdir():
    RT, repo = hyg._harness_repo()
    tmp = hyg._private("green")
    try:
        r = RT._run(repo, "test_pass", TMPDIR=tmp)
        assert r.returncode == 0, r.stdout[-800:]
        # F-147: the census is printed on a green run too, and a clean suite reads zero
        assert re.search(r"^TMP LEAKED: 0 entries, 0 bytes across 0 suites", r.stdout, re.M), \
            r.stdout[-600:]
        assert "   TMP LEAK:" not in r.stdout
        assert hyg._left(tmp) == [], hyg._left(tmp)
    finally:
        shutil.rmtree(repo, ignore_errors=True)


def test_f145_an_interrupted_run_removes_its_run_tmpdir():
    RT, repo = hyg._harness_repo()
    tmp, gate = hyg._private("int"), repo / "gate"
    try:
        e = RT._env(SUITES="test_gate", GATE_FILE=str(gate), TMPDIR=tmp)
        p = subprocess.Popen(["bash", str(repo / "run_tests.sh")], stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, env=e)
        assert hyg._wait_for(lambda: Path(str(gate) + ".started").exists())
        assert hyg._left(tmp), "the run made no TMPDIR, so this would prove nothing"
        p.send_signal(signal.SIGINT)
        p.communicate(timeout=60)
        assert p.returncode == 130, p.returncode
        assert hyg._left(tmp) == [], hyg._left(tmp)
    finally:
        gate.write_text("go")
        shutil.rmtree(repo, ignore_errors=True)


if __name__ == "__main__":
    fails = 0
    ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            ran += 1
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    assert ran >= 3, "no tests collected"
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing of {ran}")
    sys.exit(1 if fails else 0)
