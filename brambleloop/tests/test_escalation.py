"""finance.escalation_check: the four-fifths escalation is a job that queues one owner action a
month, not a number that exists only when somebody opens /api/spend-report (Build 2 closeout,
cost governance). No ceiling is changed here; the CA$100 figure is the owner's."""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import sys
import tempfile
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from sqlalchemy import select  # noqa: E402

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, CostEntry, OwnerAction  # noqa: E402
from brambleloop.finance import spend_policy  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402

NOW = datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)
PASSED = FAILED = 0


def check(name, ok, detail=""):
    global PASSED, FAILED
    PASSED += bool(ok); FAILED += (not ok)
    print(("OK   " if ok else "FAIL ") + name + ("" if ok else f"  -- {detail}"))


class _Job:
    def __init__(self, inputs): self.inputs = inputs; self.id = 1


class _Ctx:
    def __init__(self, db, inputs): self.db = db; self.job = _Job(inputs); self.audits = []
    def audit(self, action, detail=None, **kw): self.audits.append((action, detail))


def _db(share: float) -> Database:
    d = tempfile.mkdtemp()
    db = Database(f"sqlite:///{d}/t.db"); db.create_all()
    with db.session() as s:
        s.add(CostEntry(agent="gateway", amount_cad=round(spend_policy.CEILING_CAD * share, 2),
                        kind="llm", purpose="test", at=NOW))
    return db


def _run(db):
    ctx = _Ctx(db, {"as_of": NOW.isoformat()})
    return pipeline.handle_finance_escalation_check(ctx), ctx


def _actions(db):
    with db.session() as s:
        return [(a.requirement_key, a.done) for a in s.scalars(select(OwnerAction))]


db = _db(0.81)
out, ctx = _run(db)
key = spend_policy.escalation_key(NOW)
check("at 81% of the ceiling one owner action is queued, keyed by the month",
      out["required"] and out["owner_action"] == "queued" and _actions(db) == [(key, False)],
      str((out, _actions(db))))
check("the key names the calendar month", key.endswith("2026-09"), key)
out2, _ = _run(db)
check("a rerun in the same month restates the open action instead of adding a second",
      out2["owner_action"] == "restated" and len(_actions(db)) == 1, str(out2))
with db.session() as s:
    s.scalar(select(OwnerAction)).done = True
out3, _ = _run(db)
check("an action the owner has closed stays closed", out3["owner_action"] == "already_decided"
      and _actions(db) == [(key, True)], str(out3))
check("every run audits that it looked", all(a == "finance.escalation_checked" for a, _ in ctx.audits))

db70 = _db(0.70)
out70, ctx70 = _run(db70)
check("at 70% nothing is queued and the look is still audited",
      not out70["required"] and out70["owner_action"] is None and _actions(db70) == []
      and ctx70.audits and ctx70.audits[0][0] == "finance.escalation_checked", str(out70))
check("the ceiling is the owner's CA$100 and this job does not change it", spend_policy.CEILING_CAD == 100.0)
fields = spend_policy.owner_action_fields(spend_policy.escalation(db, now=NOW))
check("the owner action carries the fields a decision needs, not only a bill",
      all(fields.get(k) not in (None, "") for k in fields), str(sorted(fields)))

print(f"\n  {PASSED} passing, {FAILED} failing")
sys.exit(1 if FAILED else 0)
