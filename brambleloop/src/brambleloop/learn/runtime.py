"""Scheduled Learn source scanner. Cadence and authority wired by the integrator."""
from ..runtime.worker import handlers
from .service import scan

@handlers.register("learn.scan")
def handle_scan(ctx):
    result = scan(ctx.db)
    # F-799: every scan also takes the department's operating reading (queue, coverage, age
    # of the oldest queued gap, lessons by state), so RUN produces a metric each hour.
    from .metrics import department_metrics
    m = department_metrics(ctx.db)
    result = {**result, "metrics": {k: v for k, v in m.items() if k != "queued"}}
    ctx.audit("learn.scanned", detail=result)
    return result
