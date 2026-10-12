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
    # W4-LEARN: the routed lessons change the plan. A gap a defect lesson is about moves up
    # the review calendar, and that change -- only that change -- is recorded against the
    # lesson as acted on, so `bus.compounding` counts a decision that moved, not a read.
    from ..improve import consume
    from .metrics import calendar
    plan = calendar(ctx.db, metrics=m)
    acted = []
    for move in plan["_moves"]:
        ids = consume.act(ctx.db, "learn", move["lesson_objs"],
                          how=(f"learn calendar moved {move['topic']} from rank "
                               f"{move['from_rank']} to {move['to_rank']}"))
        acted.append({"topic": move["topic"], "from_rank": move["from_rank"],
                      "to_rank": move["to_rank"], "lessons": ids})
    result["lesson_moves"] = acted
    # W4-RESEARCH (F-403/F-433): unknowns on decision paths become research questions, and
    # answered research past its domain's freshness re-opens. Reads and writes rows only;
    # spends nothing. A failure here is reported beside the scan, never fatal to it.
    try:
        from ..intel import research

        found = research.detect_unknowns(ctx.db)
        result["research"] = {"opened": len(found["opened"]),
                              "already_open": len(found["already_open"]),
                              "expired_reopened": len(research.expire_due(ctx.db))}
    except Exception as exc:  # noqa: BLE001
        result["research"] = {"error": f"{type(exc).__name__}: {str(exc)[:160]}"}
    ctx.audit("learn.scanned", detail=result)
    return result
