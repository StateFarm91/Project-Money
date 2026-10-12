"""The Accountant cycle as a durable job (`finance.accounting.cycle`).

Registered on import with `runtime.worker.handlers`. Nothing imports this module yet: the
integrator adds the import, the cadence and the cfo agent's allowed job type (WIRING
REQUEST in research/final_build/v1_1/handoff_E.md). GREEN: reads and writes rows only,
spends nothing, messages nobody, makes no network call.
"""
from __future__ import annotations

import json

from ...runtime.worker import JobContext, handlers

JOB_TYPE = "finance.accounting.cycle"


@handlers.register(JOB_TYPE)
def handle_accounting_cycle(ctx: JobContext) -> dict:
    from .controller import run_cycle

    return json.loads(json.dumps(run_cycle(ctx.db), default=str))
