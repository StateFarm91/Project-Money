"""The nightly sweep, and the word it is not allowed to say.

Requirement 193. At least once a day, run a broad improvement cycle across departments:
ingest new evidence, mine failures, update candidate lessons, run challenger evaluations,
identify bottlenecks, queue safe improvements, and produce a machine-readable delta. Critical
learning may happen sooner; nightly is the minimum comprehensive sweep, not the only one.

The whole risk in a scheduled sweep is the word *completed*. A nightly job that finishes
without raising and writes "ok" is indistinguishable from one whose every stage was skipped,
and it is the more comfortable of the two readings, so it is the one that gets believed. This
build has met that shape in a funnel stage that killed nothing, an artefact with no provenance
row, and a buyer journey nobody walked; here it would be a company reporting a year of nightly
improvement cycles during which nothing was read.

So a stage has three outcomes and never two. It **ran and found things**, carrying the count
of what it read. It **ran and found nothing**, which is a real and common result and says so.
Or it **did not run**, carrying why — and a delta containing any of those is `incomplete`,
whatever the others did. There is no path by which a sweep that skipped six of seven stages
reports success, because the verdict is computed from what each stage returned rather than
from the absence of an exception.

The second rule is narrower and comes from the requirement's own last sentence. *Nightly is
the minimum comprehensive sweep* — so this must not become the only way learning happens. It
queues improvements; it does not promote them, it holds no lock on the evidence any other
cadence writes, and a stage finding something urgent says so in the delta rather than waiting
for tomorrow. A sweep that owned the learning would make every other path wait a day.

The delta is machine-readable because it is read by the next night's sweep: a stage that
found nothing twenty nights running is a different finding from a stage that found nothing
last night, and the only way to see the first is for the record to be comparable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

# The seven stages the requirement names, in the order it names them. Closed: a sweep that
# grows a stage per release cannot be compared with last month's.
INGEST = "ingest_evidence"
MINE = "mine_failures"
LESSONS = "update_lessons"
CHALLENGERS = "run_challengers"
BOTTLENECKS = "identify_bottlenecks"
QUEUE = "queue_safe_improvements"
DELTA = "produce_delta"

STAGES: tuple[str, ...] = (INGEST, MINE, LESSONS, CHALLENGERS, BOTTLENECKS, QUEUE, DELTA)

STAGE_MEANS: dict[str, str] = {
    INGEST: "read evidence recorded since the last sweep",
    MINE: "read incidents, dead letters and refusals for the pattern behind them",
    LESSONS: "route what was learned to the departments it applies to",
    CHALLENGERS: "compare challenger configurations against their incumbents",
    BOTTLENECKS: "read the freshness sweep and the capability curves for what is stuck",
    QUEUE: "open bounded proposals for what can be safely improved",
    DELTA: "write the comparable record this sweep produced",
}

FOUND = "ran_and_found"
NOTHING = "ran_and_found_nothing"
SKIPPED = "did_not_run"

COMPLETE = "complete"
INCOMPLETE = "incomplete"


class NightlyRefused(ValueError):
    """A stage reporting an outcome the vocabulary does not have, or a sweep overstating."""


@dataclass(frozen=True)
class StageResult:
    """One stage's outcome, which is never simply true."""

    stage: str
    outcome: str
    read: int = 0
    found: int = 0
    why: str = ""
    detail: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.stage not in STAGES:
            raise NightlyRefused(f"{self.stage!r} is not a sweep stage: {list(STAGES)}")
        if self.outcome not in (FOUND, NOTHING, SKIPPED):
            raise NightlyRefused(
                f"{self.outcome!r} is not an outcome: {[FOUND, NOTHING, SKIPPED]}. A boolean "
                f"here would collapse 'found nothing' into 'did not run', which is the one "
                f"distinction this sweep exists to keep")
        if self.outcome == SKIPPED and not self.why.strip():
            raise NightlyRefused(
                f"{self.stage} did not run and did not say why. A skipped stage with no "
                f"reason is indistinguishable from one nobody implemented")
        if self.outcome == FOUND and self.found <= 0:
            raise NightlyRefused(
                f"{self.stage} reports {FOUND} with nothing found. That is {NOTHING}, and "
                f"the difference is the whole point of having both")
        if self.outcome != SKIPPED and self.read < 0:
            raise NightlyRefused(f"{self.stage}: a negative read count is not a measurement")
        if self.outcome == NOTHING and self.read == 0:
            raise NightlyRefused(
                f"{self.stage} found nothing in nothing. A stage that read zero rows has not "
                f"established that there was nothing to find -- that is {SKIPPED}")

    @property
    def ran(self) -> bool:
        return self.outcome != SKIPPED

    def to_dict(self) -> dict:
        return {"stage": self.stage, "means": STAGE_MEANS[self.stage],
                "outcome": self.outcome, "read": self.read, "found": self.found,
                "why": self.why, "detail": dict(self.detail)}


def stage_ran(stage: str, *, read: int, found: int = 0, **detail) -> StageResult:
    """Build a result from what a stage actually saw, picking the outcome from the counts."""
    if read <= 0:
        return StageResult(stage=stage, outcome=SKIPPED, read=0,
                           why=("read nothing, so it cannot report that there was nothing to "
                                "find"), detail=detail)
    if found > 0:
        return StageResult(stage=stage, outcome=FOUND, read=read, found=found, detail=detail)
    return StageResult(stage=stage, outcome=NOTHING, read=read, detail=detail)


def stage_skipped(stage: str, why: str, **detail) -> StageResult:
    return StageResult(stage=stage, outcome=SKIPPED, why=why, detail=detail)


def delta(results: list[StageResult], *, at: datetime | None = None,
          previous: dict | None = None) -> dict:
    """The machine-readable record, whose verdict is computed rather than asserted."""
    at = at or datetime.now(timezone.utc)
    by_stage = {r.stage: r for r in results}

    duplicated = sorted({r.stage for r in results if
                         sum(1 for other in results if other.stage == r.stage) > 1})
    if duplicated:
        raise NightlyRefused(
            f"{duplicated} reported twice in one sweep. Two results for one stage means the "
            f"delta cannot be compared with any other night's")

    missing = [s for s in STAGES if s not in by_stage]
    skipped = [s for s in STAGES if s in by_stage and by_stage[s].outcome == SKIPPED]
    found = [s for s in STAGES if s in by_stage and by_stage[s].outcome == FOUND]
    quiet = [s for s in STAGES if s in by_stage and by_stage[s].outcome == NOTHING]

    verdict = COMPLETE if not missing and not skipped else INCOMPLETE
    blocked = sorted(set(missing) | set(skipped))

    out = {
        "at": at.isoformat(),
        "verdict": verdict,
        "stages": {s: (by_stage[s].to_dict() if s in by_stage else
                       {"stage": s, "means": STAGE_MEANS[s], "outcome": SKIPPED,
                        "why": "no result was reported for this stage at all"})
                   for s in STAGES},
        "found_something": found,
        "found_nothing": quiet,
        "did_not_run": blocked,
        "total_read": sum(r.read for r in results),
        "total_found": sum(r.found for r in results),
        "why": (f"every stage ran; {len(found)} found something and {len(quiet)} found "
                f"nothing" if verdict == COMPLETE else
                f"{len(blocked)} of {len(STAGES)} stages did not run: "
                f"{', '.join(blocked)}. A sweep is complete when its stages ran, not when it "
                f"finished without raising"),
    }

    if previous is not None:
        out["since_previous"] = _compare(previous, out)
    return out


def _compare(previous: dict, current: dict) -> dict:
    """What changed between two nights, which is the reason the delta is machine-readable.

    A stage quiet for twenty nights and a stage quiet since yesterday are different findings,
    and only a comparable record can tell them apart.
    """
    prev_stages = previous.get("stages", {})
    newly_quiet, newly_active, still_blocked = [], [], []
    for stage in STAGES:
        was = prev_stages.get(stage, {}).get("outcome")
        now = current["stages"][stage]["outcome"]
        if was == FOUND and now == NOTHING:
            newly_quiet.append(stage)
        elif was == NOTHING and now == FOUND:
            newly_active.append(stage)
        if was == SKIPPED and now == SKIPPED:
            still_blocked.append(stage)
    return {
        "read_delta": current["total_read"] - previous.get("total_read", 0),
        "found_delta": current["total_found"] - previous.get("total_found", 0),
        "newly_quiet": newly_quiet,
        "newly_active": newly_active,
        "still_blocked": still_blocked,
        "why": ("a stage blocked two nights running is a defect rather than a bad night, "
                "and the only way to see that is to compare"),
    }


def quiet_run(deltas: list[dict], stage: str) -> dict:
    """How many consecutive recent sweeps found nothing at this stage.

    A stage that has found nothing for a long time is either genuinely clean or quietly
    broken, and the two are the same reading -- so this reports the run length and refuses to
    say which.
    """
    if stage not in STAGES:
        raise NightlyRefused(f"{stage!r} is not a sweep stage: {list(STAGES)}")
    run = 0
    for d in reversed(deltas):
        outcome = d.get("stages", {}).get(stage, {}).get("outcome")
        if outcome == NOTHING:
            run += 1
        else:
            break
    return {
        "stage": stage, "quiet_nights": run, "of_sweeps": len(deltas),
        "why": ("a long quiet run is either a clean stage or a broken one, and this cannot "
                "tell which. It reports the run so somebody can go and look"),
    }


def state() -> dict:
    """What the sweep does, and the one word it is structurally unable to say."""
    return {
        "requirement": 193,
        "stages": [{"stage": s, "means": STAGE_MEANS[s]} for s in STAGES],
        "outcomes": {FOUND: "ran, and read this many rows to find this many things",
                     NOTHING: "ran, read rows, and there was nothing to find",
                     SKIPPED: "did not run, and says why"},
        "refuses": [
            "a stage reporting found with nothing found",
            "a stage reporting nothing after reading zero rows -- that is did_not_run",
            "a skipped stage with no reason",
            "two results for one stage, which makes the night incomparable",
            "a complete verdict while any stage did not run",
        ],
        "is_a_minimum_not_a_monopoly": (
            "nightly is the minimum comprehensive sweep, so this queues improvements rather "
            "than promoting them, holds no lock on evidence any other cadence writes, and "
            "reports urgency in the delta rather than deferring it to tomorrow. A sweep that "
            "owned the learning would make every other path wait a day"),
        "note": ("the verdict is computed from what each stage returned, never from the "
                 "absence of an exception. A job that finishes without raising and writes "
                 "'ok' reads identically whether it did the work or skipped all of it"),
    }
