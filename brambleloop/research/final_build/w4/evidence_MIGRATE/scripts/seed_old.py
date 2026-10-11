"""Seed realistic rows into the fcb982d schema using fcb982d's own code paths.

Run with PYTHONPATH=<OLD worktree>/brambleloop/src. Code-path seeding first (Registry.audit,
JobQueue enqueue/claim/complete/fail, gateway.routing.record), then fcb982d's own ORM metadata
fills every remaining table to >= 6 rows with every column populated (type-driven values).
"""
import datetime as dt
import enum
import json
import random
import sys

from sqlalchemy import (JSON, BigInteger, Boolean, Date, DateTime, Enum, Float, Integer,
                        LargeBinary, Numeric, String, Text, func, insert, select)

from brambleloop.core.db import Base, Database
from brambleloop.core import models  # noqa: F401
from brambleloop.agents.registry import Registry
from brambleloop.queue.durable import JobQueue
from brambleloop.gateway import routing

random.seed(20261011)
db = Database()
reg = Registry(db)
q = JobQueue(db)
now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)

# --- code paths -----------------------------------------------------------------------------
actors = ["orchestrator", "creative_director", "listing_manager", "cfo", "support", "release_guard"]
actions = ["job.completed", "listing.drafted", "gate.refused", "spend.reserved", "runtime.tick"]
for i in range(2500):
    reg.audit(random.choice(actors), random.choice(actions), artifact=f"seed/artefact-{i % 97}",
              detail={"seed": i, "note": "Café — unicode ✓", "n": i * 1.25})
agents = ["orchestrator", "creative_director", "listing_manager"]
for i in range(400):
    q.enqueue(random.choice(agents), random.choice(["seed.noop", "listing.refresh", "ops.tick"]),
              {"seed": i}, idempotency_key=f"seed-{i}", priority=50 + i % 100)
done = 0
while done < 250:
    job = q.claim("seed-worker")
    if job is None:
        break
    if done % 10 == 9:
        q.fail(job.id, "SeedError: synthetic failure", retry=False)
    else:
        q.complete(job.id, {"ok": True, "seed": done}, cost_cad=0.0012 * done)
    done += 1
task_keys = list(routing.TASKS)
for i in range(300):
    routing.record(db, task_keys[i % len(task_keys)], agent=random.choice(agents),
                   tokens_in=200 + i, tokens_out=50 + i, cached=(i % 7 == 0))

# --- every remaining table via fcb982d's ORM metadata ----------------------------------------
TARGET = 6


def value(col, i, conn):
    t = col.type
    if col.foreign_keys:
        fk = next(iter(col.foreign_keys))
        ref = fk.column
        v = conn.execute(select(ref).order_by(ref).limit(1).offset(i % 3)).scalar()
        if v is None:
            v = conn.execute(select(ref).limit(1)).scalar()
        return v
    if isinstance(t, Enum):
        opts = list(t.enum_class) if t.enum_class else list(t.enums)
        return opts[i % len(opts)]
    if isinstance(t, Boolean):
        return i % 2 == 0
    if isinstance(t, (Integer, BigInteger)):
        return 1000 + i
    if isinstance(t, (Float, Numeric)):
        return round(3.25 * (i + 1), 4)
    if isinstance(t, DateTime):
        v = now - dt.timedelta(hours=i)
        return v if t.timezone else v.replace(tzinfo=None)
    if isinstance(t, Date):
        return (now - dt.timedelta(days=i)).date()
    if isinstance(t, JSON):
        return {"seed": i, "col": col.name, "list": [1, 2, i]}
    if isinstance(t, LargeBinary):
        return bytes([i % 256]) * 16
    if isinstance(t, (String, Text)):
        s = f"seed-{col.table.name}-{col.name}-{i}"
        n = getattr(t, "length", None)
        return s[-n:] if n and len(s) > n else s
    return None


report = {}
with db.engine.begin() as conn:
    for table in Base.metadata.sorted_tables:
        have = conn.execute(select(func.count()).select_from(table)).scalar()
        added = 0
        for i in range(have, TARGET):
            row = {}
            for col in table.columns:
                if col.primary_key and col.autoincrement in (True, "auto") and isinstance(
                        col.type, (Integer, BigInteger)) and not col.foreign_keys:
                    continue
                v = value(col, i, conn)
                if v is not None:
                    row[col.name] = v
            sp = conn.begin_nested()
            try:
                conn.execute(insert(table).values(**row))
                sp.commit()
                added += 1
            except Exception as e:  # noqa: BLE001
                sp.rollback()
                report.setdefault("errors", {})[table.name] = f"{type(e).__name__}: {str(e)[:160]}"
        report[table.name] = have + added
print(json.dumps(report, indent=1, default=str))
