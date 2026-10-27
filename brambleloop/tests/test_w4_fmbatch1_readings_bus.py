"""F-694: finance refusals, unreviewed policy changes and repeated customer questions are
published as routed lessons with provenance, once per reading; the mine stage runs it."""
import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
_T = tempfile.mkdtemp(prefix="fmb1rb_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{_T}/r.db"

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, Lesson, SupportCase  # noqa: E402
from brambleloop.finance import spend_report  # noqa: E402
from brambleloop.gates import platform_policy  # noqa: E402
from brambleloop.improve import bus, readings_bus as RB  # noqa: E402

db = Database(os.environ["BRAMBLELOOP_DATABASE_URL"])
db.create_all()
NOW = datetime.now(timezone.utc)


def _lessons():
    with db.session() as s:
        return [(l.subject, l.origin_cell, l.evidence_ref, list(l.routed_to))
                for l in s.query(Lesson).order_by(Lesson.id)]


def test_nothing_to_publish_publishes_nothing():
    out = RB.publish_all(db, now=NOW)
    assert out == {"finance": [], "policy": [], "customer": []}, out


def test_each_reading_becomes_a_routed_lesson_once():
    with db.session() as s:
        s.add(AuditLog(actor="g", action=spend_report.REFUSED_ACTION, at=NOW,
                       detail={"which": "monthly", "agent": "market_radar"}))
        for i in range(RB.REPEAT_QUESTIONS):
            s.add(SupportCase(customer_ref=f"c{i}", product_slug="hex-blanket",
                              question="which row starts the border?"))
    src = sorted(platform_policy.POLICY_SOURCES)[0]
    platform_policy.record_snapshot(db, src, text="first version of the policy page " * 5)
    platform_policy.record_snapshot(db, src, text="a materially different policy text " * 5)
    out = RB.publish_all(db, now=NOW)
    assert len(out["finance"]) == 1 and len(out["customer"]) == 1, out
    assert len(out["policy"]) == len(platform_policy.unreviewed_changes(db)) >= 1, out
    rows = {r[0]: r for r in _lessons()}
    assert rows["cost"][3] == [c for c in bus.route_for("cost") if c != "finance"]
    assert rows["instruction_clarity"][2].startswith("support_cases:hex-blanket:")
    assert rows["platform_policy"][2].startswith("policy_snapshot:")
    before = len(_lessons())
    RB.publish_all(db, now=NOW)
    assert len(_lessons()) == before, "the same readings publish nothing new"


def test_the_mine_stage_runs_it():
    from brambleloop.improve import mine

    out = mine.mine(db, now=NOW, fixture_dir=Path(_T) / "fx")
    assert set(out["readings_published"]) == {"finance", "policy", "customer"}


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("OK  ", n)  # run_tests.sh counts lines beginning OK
