"""Scheduled Learn source scanner. Cadence and authority wired by the integrator."""
from ..runtime.worker import handlers
from .service import scan

@handlers.register("learn.scan")
def handle_scan(ctx):
    result = scan(ctx.db)
    ctx.audit("learn.scanned", detail=result)
    return result
