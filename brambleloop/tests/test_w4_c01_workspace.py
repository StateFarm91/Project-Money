"""F-716: one lane's proposer, implementer, reviewer, disagreement, evidence, tests, cost,
accepted/rejected approach and integration result, joined from their own durable records;
each element PRESENT with its source or MISSING, never inferred."""
import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import shutil
import sys
import tempfile
from pathlib import Path

OPS = Path(__file__).resolve().parents[2] / "ops"
sys.path.insert(0, str(OPS))
import disagreement as D  # noqa: E402
import handoff as H  # noqa: E402
import review as RV  # noqa: E402
import session_log as SL  # noqa: E402
import workspace as W  # noqa: E402


def _isolate(d):
    D.DIR = d / "dis"
    H.HANDOFF_DIR = d / "handoffs"
    RV.LOG = d / "REVIEWS.jsonl"
    SL.LOG = d / "SESSION_LOG.jsonl"


def test_an_unrecorded_lane_is_all_missing():
    d = Path(tempfile.mkdtemp(prefix="c01ws-"))
    try:
        _isolate(d)
        w = W.build("nobody", registry_data={"jobs": {}}, queue_data={"queue": [], "done": []})
        assert w["missing"] == list(W.ELEMENTS) and w["complete"] is False
        assert w["elements"]["integration"]["why"] == "NOT_INTEGRATED"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_every_element_joins_from_its_own_record():
    d = Path(tempfile.mkdtemp(prefix="c01ws-"))
    try:
        _isolate(d)
        D.open_("dg", question="hook or queue?", lane="L")
        D.propose("dg", "hook", by="w-c01", model="opus", approach="pre-push")
        D.propose("dg", "queue", by="w-c09", model="codex", approach="integrate only")
        D.evidence("dg", "queue", kind="primary_evidence", ref="push log", result="REFUTES")
        D.evidence("dg", "hook", kind="economics", ref="0 CAD", result="SUPPORTS")
        D.resolve("dg")
        RV.record(lane="L", head="abc1234", implementer="w-c01", implementer_model="opus",
                  reviewer="w-rev", reviewer_model="codex", verdict="NO_BLOCKERS",
                  findings="force push refused")
        SL.record(model="opus", lane="L", rows=["F-711"], commits=["abc1234"], cost_cad=1.5)
        SL.record(model="opus", lane="L", rows=[], commits=[])           # cost unknown
        q = {"queue": [], "done": [{"lane": "L", "tests": ["tests/t.py"], "commit": "f" * 40,
                                    "target": "claude/w4-INTEG9"}]}
        w = W.build("L", registry_data={"jobs": {}}, queue_data=q)
        assert w["complete"] is True, w["missing"]
        e = w["elements"]
        assert e["proposer"]["value"] == ["w-c01 (opus)", "w-c09 (codex)"]
        assert "w-c01 (opus)" in e["implementer"]["value"]
        assert e["reviewer"]["value"][0]["certifies"] is False
        assert e["approach"]["value"] == {"dg": {"hook": "ACCEPTED", "queue": "REJECTED"}}
        assert e["cost"]["value"] == {"sessions": 2, "cost_cad": 1.5, "sessions_unmeasured": 1}
        assert e["tests"]["value"] == ["tests/t.py"]
        assert e["integration"]["value"]["commit"] == "f" * 40
        assert "**approach** PRESENT" in W.to_markdown(w)
    finally:
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("OK  ", n)  # run_tests.sh counts lines beginning OK
