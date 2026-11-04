"""The job that runs `culture.ideation_bridge.run` (market_radar), A8.

Daily, after the culture sweep has recorded the day's readings. A rising culture signal becomes
a coverage gap that A4(a)'s research-to-concept chain answers from recorded evidence. CA$0,
deterministic, never drafts or publishes by itself.
"""
from __future__ import annotations

from .worker import JobContext, handlers


@handlers.register("culture.ideate")
def handle_culture_ideate(ctx: JobContext) -> dict:
    from ..culture import ideation_bridge

    return ideation_bridge.run(ctx)
