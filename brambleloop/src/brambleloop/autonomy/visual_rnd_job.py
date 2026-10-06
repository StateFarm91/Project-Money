"""`visual.rnd.cycle`: the Visual R&D loop as a runtime job (W3 lane D wiring for lane H).

Calls `brambleloop.visual.rnd.loop.cycle(db)`: generate -> monitor -> calibrate -> diagnose ->
propose -> deterministic experiment -> plan paid challengers. It runs on its own 6-hourly
cadence (`runtime.worker.CADENCES` "visual_rnd") and as Visual department work generated from
`visual.rnd.status.next_work` (autonomy.generators PROVIDERS["visual"]), so Laura and the COO
can delegate it when the department is idle.

GREEN: deterministic renders of the Launch-0 catalogue and rows in this database. No network,
no model, no spend. Paid challengers are only *planned* (an owner decision); a report that
claims a paid execution makes this handler refuse rather than record it as work.

Honest work count (`work_done`, read by `runtime.pipeline.did_no_work`): new production
galleries judged, deterministic experiments run, rollbacks, marketplace overturns and newly
planned paid challengers. A "retain"/"waiting"/"inconclusive" pass is a reading, not work.
"""
from __future__ import annotations

from ..runtime.worker import JobContext, handlers

JOB = "visual.rnd.cycle"


def summarise(report: dict) -> dict:
    classes = report.get("classes") or {}
    generated = sum(1 for e in classes.values() if e.get("generated"))
    experiments = sum(len(e.get("experiments") or []) for e in classes.values())
    rolled_back = sum(1 for e in classes.values()
                      if (e.get("monitor") or {}).get("action") == "rolled_back")
    overturned = sum(1 for e in classes.values()
                     if (e.get("calibration") or {}).get("verdict") == "overturned")
    paid_planned = sum(1 for e in classes.values() if (e.get("paid") or {}).get("new"))
    for cls, e in classes.items():
        state = str((e.get("paid") or {}).get("state") or "")
        if state in ("executed", "running", "spent"):
            raise RuntimeError(f"visual.rnd.cycle reported a paid execution for {cls} "
                               f"({state}); refusing -- paid challengers wait for the owner")
    return {"ran": True, "classes": len(classes), "generated": generated,
            "experiments": experiments, "rolled_back": rolled_back, "overturned": overturned,
            "paid_planned": paid_planned,
            "work_done": generated + experiments + rolled_back + overturned + paid_planned,
            "incumbents": {c: e.get("incumbent") for c, e in classes.items()},
            "spend_cad": 0.0}


@handlers.register(JOB)
def handle_visual_rnd_cycle(ctx: JobContext) -> dict:
    from ..visual.rnd import loop

    out = summarise(loop.cycle(ctx.db))
    ctx.audit(JOB, detail=out)
    return out
