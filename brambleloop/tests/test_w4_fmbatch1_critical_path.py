"""F-465: the critical path and the downstream count are computed from the dependency graph."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.build2 import critical_path as cp  # noqa: E402
from brambleloop.build2 import executor  # noqa: E402
from brambleloop.build2 import requirements as reg  # noqa: E402


def _with(deps, gates, statuses):
    old_d, old_g = executor.DEPENDENCIES, executor.gate_for
    executor.DEPENDENCIES = deps
    executor.gate_for = lambda rid: gates.get(rid)
    try:
        return cp.analyse(statuses)
    finally:
        executor.DEPENDENCIES, executor.gate_for = old_d, old_g


def test_longest_chain_is_the_critical_path():
    # 1 -> 2 -> 3 -> 4 and 1 -> 5 ; gate "g" parks 1 ; 9 independent
    deps = {2: (1,), 3: (2,), 4: (3,), 5: (1,)}
    st = {i: "missing" for i in (1, 2, 3, 4, 5, 9)}
    r = _with(deps, {1: "g"}, st)
    assert r["critical_path"] == ["gate:g", "#1", "#2", "#3", "#4"], r["critical_path"]
    assert r["length"] == 4
    assert r["downstream"]["#1"] == 4 and r["downstream"]["#3"] == 1 and r["downstream"]["#9"] == 0
    assert r["gates_by_unblocked"][0] == {"gate": "g", "unblocks": 5}
    assert r["ranking"][0]["node"] == "gate:g"


def test_covered_prerequisites_do_not_count():
    deps = {2: (1,), 3: (2,)}
    st = {1: reg.COVERED, 2: "missing", 3: "missing"}
    r = _with(deps, {}, st)
    assert "#1" not in r["downstream"]
    assert r["critical_path"] == ["#2", "#3"]


def test_a_cycle_is_refused_not_looped():
    st = {1: "missing", 2: "missing"}
    try:
        _with({1: (2,), 2: (1,)}, {}, st)
    except ValueError as exc:
        assert "cycle" in str(exc)
    else:
        raise AssertionError("cycle accepted")


def test_queue_reading_degrades_to_unknown():
    old = cp.analyse
    cp.analyse = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
    try:
        out = executor._critical_path_reading([{"requirement_id": 1}])
    finally:
        cp.analyse = old
    assert out["state"] == "UNKNOWN" and "boom" in out["why"]


def test_real_registry_analyses():
    r = cp.analyse()
    assert isinstance(r["critical_path"], list) and r["gates_by_unblocked"]


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("ok", n)
