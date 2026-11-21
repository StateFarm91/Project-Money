"""D-OWNER-ETSY-EXERCISE: the owner's one-time exercise runs once, inside its window, audited."""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import ast
import sys
import tempfile
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.ops import owner_etsy_exercise as E  # noqa: E402

_TMP = tempfile.mkdtemp()
_N = [0]
IN = E.GIVEN_AT + timedelta(hours=1)


def _db():
    _N[0] += 1
    db = Database(f"sqlite:///{_TMP}/e{_N[0]}.db")
    db.create_all()
    return db


def test_a_clean_run_happens_once_and_never_again():
    db = _db()
    calls = []
    ok = lambda: calls.append(1) or {"ok": True, "status": "clean", "shop_is_clean": True}  # noqa: E731
    out = E.maybe_run(db, now=IN, runner=ok)
    assert out["ran"] and out["ok"] is True and calls == [1], out
    again = E.maybe_run(db, now=IN, runner=ok)
    assert again["ran"] is False and calls == [1], again


def test_a_refusal_is_recorded_and_attempts_are_capped():
    db = _db()
    calls = []

    def refuse():
        calls.append(1)
        raise RuntimeError("Etsy grant expired: re-authorise")

    for _ in range(5):
        E.maybe_run(db, now=IN, runner=refuse)
    assert len(calls) == E.MAX_ATTEMPTS, calls
    rows = E._attempts(db)
    assert len(rows) == E.MAX_ATTEMPTS and all(r["ok"] is False and r["refused"] for r in rows)


def test_outside_the_window_nothing_runs():
    db = _db()
    calls = []
    for when in (E.GIVEN_AT - timedelta(minutes=1), E.SUNSET + timedelta(minutes=1)):
        out = E.maybe_run(db, now=when, runner=lambda: calls.append(1) or {"ok": True})
        assert out["ran"] is False, out
    assert calls == []


def test_the_default_runner_is_the_unchanged_full_exercise():
    src = Path(E.__file__).read_text()
    tree = ast.parse(src)
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Attribute) and n.func.attr == "run"
             and getattr(n.func.value, "id", "") == "etsy_exercise"]
    assert calls, "maybe_run must call integrations.etsy_exercise.run"
    kw = {k.arg: getattr(k.value, "value", None) for k in calls[0].keywords}
    assert kw.get("mode") == "full", kw


def test_boot_starts_it_only_when_due():
    src = (Path(__file__).resolve().parents[1] / "src/brambleloop/app/main.py").read_text()
    start = next(n for n in ast.walk(ast.parse(src))
                 if isinstance(n, ast.FunctionDef) and n.name == "_startup")
    text = ast.get_source_segment(src, start)
    assert "_oee.due(db)" in text and "_oee.maybe_run(db" in text
    assert "RAILWAY_DEPLOYMENT_ID" in text  # never from a test run or a laptop


def test_boot_asks_for_one_listing_package_sweep_per_commit():
    src = (Path(__file__).resolve().parents[1] / "src/brambleloop/app/main.py").read_text()
    start = next(n for n in ast.walk(ast.parse(src))
                 if isinstance(n, ast.FunctionDef) and n.name == "_startup")
    text = ast.get_source_segment(src, start)
    assert 'job_type="listing.package"' in text and "boot-listing-package-" in text
    assert '"retry_for_commit": _commit' in text


def test_boot_runs_the_sentinel_and_the_health_sweep_once_per_commit():
    src = (Path(__file__).resolve().parents[1] / "src/brambleloop/app/main.py").read_text()
    start = next(n for n in ast.walk(ast.parse(src))
                 if isinstance(n, ast.FunctionDef) and n.name == "_startup")
    text = ast.get_source_segment(src, start)
    assert '"ops.sentinel"' in text and '"ops.health"' in text and "boot-{_name}-" in text


def test_second_directive_recovers_then_exercises_bounded():
    db = _db()
    at = E.GIVEN_AT_2 + timedelta(hours=1)
    order = []
    rec = lambda: order.append("recover") or {"ok": True, "cleaned": 1}  # noqa: E731
    bad = lambda: order.append("run") or {"ok": False, "status": "not clean"}  # noqa: E731
    for _ in range(5):
        E.maybe_run_2(db, now=at, recoverer=rec, runner=bad)
    assert order == ["recover", "run"] * E.MAX_ATTEMPTS_2, order
    db2 = _db()
    good = lambda: {"ok": True, "status": "clean", "shop_is_clean": True}  # noqa: E731
    assert E.maybe_run_2(db2, now=at, recoverer=rec, runner=good)["ok"] is True
    assert E.maybe_run_2(db2, now=at, recoverer=rec, runner=good)["ran"] is False
    assert E.maybe_run_2(_db(), now=E.SUNSET_2 + timedelta(minutes=1),
                         recoverer=rec, runner=good)["ran"] is False


if __name__ == "__main__":
    import traceback
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as exc:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(exc))
                traceback.print_exc()
    print(f"{fails} failed")
    sys.exit(1 if fails else 0)
