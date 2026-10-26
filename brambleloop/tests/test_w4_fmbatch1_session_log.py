"""F-864/F-868/F-869: session outcomes, checkpoints and approval prompts are recorded in the
repository (never production) and summarised per model, UNMEASURED never zero."""
import subprocess
import sys
import tempfile
from pathlib import Path

OPS = Path(__file__).resolve().parents[2] / "ops"
sys.path.insert(0, str(OPS))
import session_log as L  # noqa: E402


def test_record_summary_and_checkpoint():
    d = Path(tempfile.mkdtemp(prefix="fmb1sl_"))
    L.LOG = d / "SESSION_LOG.jsonl"
    L.record(model="opus", lane="a", rows=["F-1", "F-2"], commits=["x"], cost_cad=2.0,
             approvals=4)
    L.record(model="opus", lane="b", rows=["F-3"], commits=["y"])
    L.record(model="other", lane="c", rows=[], commits=[])
    s = L.summary()["models"]
    assert s["opus"] == {"sessions": 2, "rows_per_session": 1.5, "cost_per_row_cad": 0.6667,
                         "approval_prompts_per_session": 4.0}
    assert s["other"]["cost_per_row_cad"] == L.UNMEASURED
    assert s["other"]["approval_prompts_per_session"] == L.UNMEASURED
    for bad in ({"model": "", "lane": "a"}, {"model": "m", "lane": "a", "approvals": -1}):
        try:
            L.record(rows=[], commits=[], **bad)
        except ValueError:
            pass
        else:
            raise AssertionError(bad)
    repo = d / "r"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "f.txt").write_text("x")
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@e.invalid",
                    "commit", "-q", "--allow-empty", "-m", "c"], check=True)
    cp = L.checkpoint(lane="a", repo=repo)
    assert cp["head"] and cp["pushed"] is False and cp["uncommitted"] == ["f.txt"]


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("ok", n)
