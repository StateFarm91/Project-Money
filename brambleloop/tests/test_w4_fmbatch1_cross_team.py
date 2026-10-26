"""F-690: a recurring customer confusion creates one pattern-team task with its evidence; a
task enqueues only a GREEN job the recipient may run; tasks show in the recipient workspace."""
import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
_T = tempfile.mkdtemp(prefix="fmb1xt_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{_T}/x.db"

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.autonomy import cross_team as X, department_workspace as W  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import Job, SupportCase  # noqa: E402
from brambleloop.improve import readings_bus as RB  # noqa: E402

db = Database(os.environ["BRAMBLELOOP_DATABASE_URL"])
db.create_all()
Registry(db).seed_defaults()


def _refused(fn):
    try:
        fn()
    except X.CrossTeamRefused as exc:
        return str(exc)
    raise AssertionError("accepted")


def test_recurring_confusion_creates_one_pattern_team_task():
    with db.session() as s:
        for i in range(RB.REPEAT_QUESTIONS):
            s.add(SupportCase(customer_ref=f"c{i}", product_slug="hex-blanket",
                              question="which round does the border start on?"))
    RB.publish_all(db, now=datetime.now(timezone.utc))
    RB.publish_all(db, now=datetime.now(timezone.utc))
    tasks = X.inbox(db, "product_catalogue")
    assert len(tasks) == 1 and tasks[0]["from_dept"] == "customer_experience"
    assert "hex-blanket" in tasks[0]["request"]
    assert tasks[0]["evidence_ref"].startswith("support_cases:hex-blanket:")
    w = W.workspace(db, "product_catalogue")
    assert w["inbound_tasks"] and w["inbound_tasks"][0]["task"] == tasks[0]["task"]
    X.close(db, tasks[0]["task"], resolution="clarified the border start in v1.1")
    assert X.inbox(db, "product_catalogue") == []


def test_validation_and_job_enqueue_rules():
    assert "another department" in _refused(lambda: X.create(
        db, from_dept="finance_accounting", to_dept="finance_accounting", request="a b c d e", evidence_ref="r"))
    assert "names its evidence" in _refused(lambda: X.create(
        db, from_dept="finance_accounting", to_dept="product_catalogue", request="fix", evidence_ref=""))
    out = X.create(db, from_dept="finance_accounting", to_dept="product_catalogue",
                   request="publish the corrected pattern listing now", evidence_ref="r1",
                   job_type="store.publish")
    assert "refused" in out["enqueued"]
    with db.session() as s:
        assert s.query(Job).filter(Job.job_type == "store.publish").count() == 0


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("ok", n)
