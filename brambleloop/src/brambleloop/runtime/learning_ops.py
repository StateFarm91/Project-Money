"""`learning.loops` (analyst): the pattern and commerce learning loops, daily (ENG-LEARN).

The steps:
- Harvest every finished engineering job (`cir.draft`, `cir.compile`, `gate.certify`) into
  pattern observations.
- Derive the measured parameter-region lessons and route them on the lesson bus, where
  `radar.score` and `cir.draft` read them.
- Fold real commerce readings into the same lesson store.

It reads this database only: no model, network or spend. On a run with nothing new it reports
`work_done: 0`, and the thrash breaker's backoff parks it. The backoff is lifted by its
upstream engineering jobs making progress (`swarm.orchestrate.UPSTREAM_INPUTS`).

The image loop runs in `creative.image_benchmark`, the job it superseded.
"""
from __future__ import annotations

from .worker import JobContext, handlers

JOB_TYPE = "learning.loops"


@handlers.register(JOB_TYPE)
def handle_learning_loops(ctx: JobContext) -> dict:
    from ..learning import commerce_lessons, pattern_lessons, progress

    pat = pattern_lessons.cycle(ctx.db)
    com = commerce_lessons.cycle(ctx.db)
    snap = progress.summary(ctx.db)
    ctx.audit(JOB_TYPE, detail={
        "pattern_observed": pat["harvest"]["observed"],
        "pattern_lessons": pat["lessons"]["lessons"],
        "pattern_new": pat["lessons"]["new"], "pattern_deactivated": pat["lessons"]["deactivated"],
        "commerce": {k: v for k, v in com.items() if k != "lessons_detail"},
        "first_pass_all": snap["pattern"]["all_time"]})
    return {"ran": True, "pattern": {"observed": pat["harvest"]["observed"],
                                     "lessons": pat["lessons"]["lessons"],
                                     "new": pat["lessons"]["new"],
                                     "deactivated": pat["lessons"]["deactivated"]},
            "commerce": {k: v for k, v in com.items() if k != "lessons_detail"},
            "work_done": pat["work_done"] + com["work_done"]}
