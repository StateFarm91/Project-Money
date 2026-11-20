"""F-107: spend by value unit -- requirement and benchmark as first-class attribution.

The ledger already answers by purpose, model, provider, agent, department and product. This
module adds the two value units F-107 names: the **requirement** a call served and the
**benchmark** it was spent on.

* Write side: `scope(requirement_id=..., benchmark_key=...)` is a context manager. Every
  cost row written inside it carries `requirement_id` / `benchmark_key` in its detail
  (stamped by `spend_report.attribution`, which every model-gateway bill passes through).
* Read side: `resolve(row, job_inputs)` reads the row's detail first, then the job's inputs
  (`requirement_id` / `requirement` / `uid`, `benchmark_key` / `benchmark`), so spend from
  jobs enqueued with those inputs is attributed even when the writer did not stamp it.
  Anything else is `unattributed`, with its dollars kept -- never dropped.
"""
from __future__ import annotations

import contextlib
import contextvars

_SCOPE: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "brambleloop_value_unit", default=None)

REQ_KEYS = ("requirement_id", "requirement", "uid")
BENCH_KEYS = ("benchmark_key", "benchmark")


@contextlib.contextmanager
def scope(*, requirement_id: str = "", benchmark_key: str = ""):
    outer = _SCOPE.get() or {}
    inner = dict(outer)
    if requirement_id:
        inner["requirement_id"] = str(requirement_id)[:80]
    if benchmark_key:
        inner["benchmark_key"] = str(benchmark_key)[:80]
    token = _SCOPE.set(inner)
    try:
        yield inner
    finally:
        _SCOPE.reset(token)


def stamp(detail: dict) -> dict:
    """The running scope's units added to `detail`, never overwriting an explicit value."""
    for k, v in (_SCOPE.get() or {}).items():
        detail.setdefault(k, v)
    return detail


def _first(d: dict, keys) -> str:
    for k in keys:
        v = d.get(k)
        if isinstance(v, (str, int)) and str(v).strip():
            return str(v).strip()[:80]
    return ""


def resolve(detail, job_inputs) -> tuple[str, str]:
    d = detail if isinstance(detail, dict) else {}
    j = job_inputs if isinstance(job_inputs, dict) else {}
    req = _first(d, ("requirement_id",)) or _first(j, REQ_KEYS)
    bench = _first(d, ("benchmark_key",)) or _first(j, BENCH_KEYS)
    return req, bench


def buckets(db, rows_, unattributed: str = "unattributed") -> dict:
    """{"by_requirement": {...}, "by_benchmark": {...}} over `rows_`, dollars intact."""
    job_ids = {r.job_id for r in rows_ if getattr(r, "job_id", None)}
    inputs: dict = {}
    if job_ids:
        from sqlalchemy import select

        from ..core.models import Job

        with db.session() as s:
            for jid, inp in s.execute(select(Job.id, Job.inputs).where(Job.id.in_(job_ids))):
                inputs[jid] = inp
    out = {"by_requirement": {}, "by_benchmark": {}}
    for r in rows_:
        req, bench = resolve(r.detail, inputs.get(r.job_id))
        for name, key in (("by_requirement", req), ("by_benchmark", bench)):
            b = out[name].setdefault(key or unattributed, {"cad": 0.0, "calls": 0})
            b["cad"] = round(b["cad"] + float(r.amount_cad or 0.0), 6)
            b["calls"] += 1
    for name in out:
        out[name] = dict(sorted(out[name].items(), key=lambda kv: -kv[1]["cad"]))
    return out
