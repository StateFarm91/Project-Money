"""A8 P0-CULTURE-TO-IDEATION: a rising culture signal opens a research task for ideation.

Before this, `culture.sweep` turned a signal into learning notes and lessons only (wiring #6,
P0_WIRING_50937469.md s5): no rising topic ever became a concept. This is the bridge, and
nothing else. A rising, non-sensitive, measurable signal whose topic names a pod the studio
already merchandises (`intel.pods.route`) becomes one coverage gap for that pod
(`benchmark_key` CULTURE_KEY, `arena` "culture:<signal>"), and the gap goes to A4(a)'s own
research-to-concept chain (`radar.ideation.open_briefs` -> `research.investigate` ->
`radar.concept_intake` -> `radar.score` -> `cir.draft`). That chain, not this module, decides
whether a concept is proposed, and it proposes only from recorded market observations, with
its own originality and children's checks, bounded by its MAX_IN_FLIGHT.

What it never does:

* route a sensitive topic, a topic with fewer than two readings, or a falling or flat one;
* put a culture topic's words, or any protected token, into a concept: the gap names only the
  pod, so the concept comes from the pod's recorded market, and the signal is evidence;
* invent a pod: a topic `pods.route` cannot place is recorded once, by name, and skipped;
* re-open: one gap per signal (the coverage unique key), and A4(a) gives a gap one brief.

Deterministic, CA$0, no model call, no network. Runs as `culture.ideate` (daily).
"""
from __future__ import annotations

from datetime import date

CULTURE_KEY = "culture_radar"
ARENA_PREFIX = "culture:"
OPENED = "culture.ideation_gap"
UNPLACED = "culture.ideation_unplaced"
SKIPPED = "culture.ideation_skipped"


def _topic(signal: str) -> str:
    return " ".join(str(signal or "").replace("_", " ").replace("-", " ").split())


def candidates(db, *, limit: int = 20) -> tuple[list[dict], list[dict]]:
    """(rising signals with their pod, skipped with why), from the radar's own findings."""
    from ..intel import pods
    from . import classify, radar

    found = radar.findings(db, limit=limit)        # measurable momentum only (two readings)
    out, skipped = [], []
    for f in found["findings"]:
        signal = f["signal"]
        moment = f.get("momentum") or {}
        if f.get("sensitive") or classify.sensitive(signal):
            skipped.append({"signal": signal, "why": "sensitive: never routed anywhere"})
            continue
        if moment.get("direction") != "rising":
            skipped.append({"signal": signal,
                            "why": f"{moment.get('direction') or 'unknown'}, not rising"})
            continue
        pod = pods.route(_topic(signal))
        if not pod or pod == pods.UNCLASSIFIED:
            skipped.append({"signal": signal, "why": "unplaced: no pod the studio merchandises",
                            "unplaced": True})
            continue
        out.append({"signal": signal, "pod": pod, "momentum": {
            k: moment.get(k) for k in ("direction", "latest", "peak", "observations")}})
    return out, skipped


def _gap_for(db, signal: str, pod: str, momentum: dict) -> int:
    """The signal's coverage gap: created once with its evidence, never re-written (A4(a)
    keeps its ideation record in the same evidence)."""
    from sqlalchemy import select

    from ..core.models import CoverageGap
    from ..intel import coverage

    arena = f"{ARENA_PREFIX}{signal}"[:80]
    with db.session() as s:
        row = s.scalar(select(CoverageGap).where(CoverageGap.benchmark_key == CULTURE_KEY,
                                                 CoverageGap.arena == arena))
        if row is not None:
            return row.id
    return coverage.upsert(db, benchmark_key=CULTURE_KEY, arena=arena, pod=pod,
                           evidence={"culture_signal": signal, "momentum": momentum,
                                     "source": "culture.radar.findings"})


def _already(db, action: str, artifact: str) -> bool:
    from sqlalchemy import select

    from ..core.models import AuditLog

    with db.session() as s:
        return s.scalar(select(AuditLog.id).where(AuditLog.action == action,
                                                  AuditLog.artifact == artifact)
                        .limit(1)) is not None


def run(ctx, *, today: date | None = None, limit: int = 20) -> dict:
    """Open an ideation brief (through A4(a)) for every rising, placeable culture signal."""
    from ..radar import ideation

    today = today or date.today()
    found, skipped = candidates(ctx.db, limit=limit)
    gaps = []
    for c in found:
        artifact = f"culture_signal:{c['signal']}"
        gid = _gap_for(ctx.db, c["signal"], c["pod"], c["momentum"])
        if not _already(ctx.db, OPENED, artifact):
            ctx.audit(OPENED, artifact=artifact,
                      detail={"gap": gid, "pod": c["pod"], "momentum": c["momentum"]})
        gaps.append({"gap": gid, "pod": c["pod"],
                     "arena": f"{ARENA_PREFIX}{c['signal']}"[:80]})
    for sk in skipped:
        if sk.get("unplaced"):
            artifact = f"culture_signal:{sk['signal']}"
            if not _already(ctx.db, UNPLACED, artifact):
                ctx.audit(UNPLACED, artifact=artifact, detail={"why": sk["why"]})
    briefs = ideation.open_briefs(ctx, gaps, today=today) if gaps else {
        "opened": [], "already": [], "waiting": [], "in_flight": [], "completed": []}
    return {"rising": [c["signal"] for c in found], "gaps": [g["gap"] for g in gaps],
            "opened": briefs["opened"], "already": briefs["already"],
            "waiting": briefs["waiting"], "skipped": skipped[:20],
            "work_done": len(briefs["opened"])}
