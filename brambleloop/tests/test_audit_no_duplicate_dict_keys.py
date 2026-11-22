"""Audit F-09 / F-10 (2026-11-22): correctness-hygiene guards found by static scan.

F-09. A dict literal with a repeated constant key keeps only the LAST value, silently. Three
were found: `visual/drape.py` PROVENANCE["support_friction"] (two CONTRADICTORY disclosures --
"BOUNDED ASSUMPTION, OFF BY DEFAULT" and "NOT MODELLED" -- of which only the second survived,
although the code implements the term), and "improve.self_tune" twice in both
`runtime/pipeline.py` WORK_KEYS and `swarm/orchestrate.py`'s band map. This scans every module
under src/brambleloop with `ast` and fails naming file:line and key for any repeat.

F-10. `test_w4_firstsale_deliverables.test_on_postgres_when_available` returned without
running anything when BL_TEST_PG_URL was unset and was then printed as OK, so the runner
counted a pass and reported 0 skips. It must print a column-zero SKIP line and no OK line for
itself, the convention test_codex_v0_postgres and test_eng_stale_rebuild_loop follow.

Run: cd brambleloop && python tests/test_audit_no_duplicate_dict_keys.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import ast
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "brambleloop"
PG_TEST = "test_on_postgres_when_available"


def _duplicate_keys(source: str, label: str) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(source, filename=label)):
        if not isinstance(node, ast.Dict):
            continue
        seen: dict[object, int] = {}
        for key in node.keys:
            # `None` is a `**spread`; only constant keys are certainly identical. The type is
            # part of the identity so that 1 and True (equal, but distinct literals) are not
            # reported as a repeat.
            if not isinstance(key, ast.Constant):
                continue
            ident = (type(key.value).__name__, key.value)
            if ident in seen:
                found.append(f"{label}:{key.lineno}: key {key.value!r} repeats the one at "
                             f"line {seen[ident]}")
            else:
                seen[ident] = key.lineno
    return found


def test_no_dict_literal_repeats_a_constant_key():
    files = sorted(SRC.rglob("*.py"))
    assert len(files) > 50, f"scan found only {len(files)} modules under {SRC}"
    found = [d for f in files
             for d in _duplicate_keys(f.read_text(encoding="utf-8"), str(f.relative_to(ROOT)))]
    assert not found, "duplicate dict-literal keys (the later one silently wins):\n  " + \
        "\n  ".join(found)


def test_the_scan_detects_a_repeat():
    # The guard's own instrument on a known positive, so an empty result above means clean
    # rather than a scanner that matches nothing.
    hits = _duplicate_keys('D = {"a": 1, "b": 2,\n     "a": 3}\nE = {1: 0, True: 0, **D}\n',
                           "probe.py")
    assert len(hits) == 1 and hits[0].startswith("probe.py:2: key 'a'"), hits


def test_drape_states_the_support_friction_term_it_implements():
    sys.path.insert(0, str(ROOT / "src"))
    from dataclasses import fields

    from brambleloop.visual import drape as DR

    (setup,) = [f for f in fields(DR.DrapeSetup) if f.name == "support_friction"]
    assert setup.default is False
    text = DR.PROVENANCE["support_friction"]
    # The term exists in code and is off by default, so the disclosure must say both that it
    # is a bounded assumption off by default and that, off, friction is not modelled.
    assert "BOUNDED ASSUMPTION, OFF BY DEFAULT" in text, text
    assert "NOT MODELLED" in text, text


def test_postgres_conditional_test_reports_skip_not_ok_when_unset():
    env = {k: v for k, v in os.environ.items() if k != "BL_TEST_PG_URL"}
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT / "src"), str(ROOT / "tests")])
    r = subprocess.run([sys.executable, "tests/test_w4_firstsale_deliverables.py"],
                       cwd=ROOT, env=env, capture_output=True, text=True, timeout=1200)
    lines = r.stdout.splitlines()
    assert r.returncode == 0, (r.returncode, r.stdout[-2000:], r.stderr[-2000:])
    skips = [ln for ln in lines if ln.startswith("SKIP") and PG_TEST in ln]
    oks = [ln for ln in lines if ln.startswith("OK") and PG_TEST in ln]
    assert len(skips) == 1, f"expected one SKIP line for {PG_TEST}; stdout:\n{r.stdout[-2000:]}"
    assert not oks, f"{PG_TEST} did not run but was counted as a pass: {oks}"


if __name__ == "__main__":
    tests = [(n, f) for n, f in globals().items() if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"OK   {name}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {name}: {type(exc).__name__}: {exc}"[:4000])
    print(f"{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
