"""F-452 / F-466: Final Master rows join the dependency graph (gate and next-action edges),
the critical path counts them, and an open gate fans out to the rows it releases."""
import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
_T = tempfile.mkdtemp(prefix="fmb1fg_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{_T}/g.db"

from brambleloop.build2 import critical_path as C, executor, fm_graph as F  # noqa: E402


def _row(uid, completion, gate=None, nxt=""):
    return {"uid": uid, "completion": completion, "launch_class": "POST-LAUNCH",
            "gate": gate or {"kind": "none", "key": None}, "next_action": nxt}


SNAP = {"rows": [
    _row("F-001", "COMPLETE"),
    _row("F-002", "GATED", {"kind": "owner", "key": "g_open"}, "wire the reading"),
    _row("F-003", "OPEN", nxt="after F-002, build the consumer; see F-001"),
    _row("F-004", "OPEN", nxt="extend F-003 to every department"),
    _row("F-005", "GATED", {"kind": "data", "key": "g_closed"}),
    _row("F-006", "GATED", {"kind": "owner", "key": "not_a_live_gate"}),
    _row("F-007", "NOT-APPLICABLE"),
]}


class _Gate:
    def __init__(self, key, is_open):
        self.key, self._o = key, is_open

    def open(self, db, env):
        return self._o


def test_nodes_and_edges():
    g = F.nodes_and_edges(SNAP)
    assert set(g["nodes"]) == {"F-002", "F-003", "F-004", "F-005", "F-006"}
    assert ("gate:g_open", "F-002") in g["edges"] and ("F-002", "F-003") in g["edges"]
    assert ("F-003", "F-004") in g["edges"]
    assert not any(a == "F-001" for a, _ in g["edges"]), "a complete row is not a prerequisite"


def test_critical_path_counts_final_master_rows():
    r = C.analyse({}, include_fm=True, fm_snapshot=SNAP)
    assert r["critical_path"] == ["gate:g_open", "F-002", "F-003", "F-004"], r["critical_path"]
    assert r["length"] == 3 and r["downstream"]["F-002"] == 2
    assert {"gate": "g_open", "unblocks": 3} in r["gates_by_unblocked"]


def test_fanout_names_rows_released_by_open_gates_and_never_guesses():
    real = executor.GATES
    executor.GATES = (_Gate("g_open", True), _Gate("g_closed", False))
    try:
        out = F.fanout(None, snapshot=SNAP)
    finally:
        executor.GATES = real
    assert out["unblocked"] == {"g_open": ["F-002"]}
    assert out["still_gated"] == {"g_closed": ["F-005"]}
    assert out["unevaluable"] == {"not_a_live_gate": ["F-006"]}
    assert out["unblocked_rows"] == ["F-002"]


def test_sync_records_the_fanout_once_per_change():
    from sqlalchemy import func, select

    from brambleloop.core.db import Database
    from brambleloop.core.models import BuildEvent

    db = Database(os.environ["BRAMBLELOOP_DATABASE_URL"])
    db.create_all()
    real = F.fanout
    F.fanout = lambda db, env=None, snapshot=None: {
        "unblocked": {"g": ["F-002"]}, "still_gated": {}, "unevaluable": {},
        "unblocked_rows": ["F-002"]}
    try:
        a = executor._fm_fanout(db, None)
        executor._fm_fanout(db, None)
    finally:
        F.fanout = real
    assert a["unblocked_rows"] == ["F-002"]
    with db.session() as s:
        n = s.scalar(select(func.count()).select_from(BuildEvent)
                     .where(BuildEvent.kind == "fm_unblocked"))
    assert n == 1


def test_real_snapshot_builds_a_graph():
    g = F.nodes_and_edges()
    assert len(g["nodes"]) > 100 and g["edges"]


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("OK  ", n)  # run_tests.sh counts lines beginning OK
