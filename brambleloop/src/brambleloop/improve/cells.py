"""The improvement cells, and the loop each one runs.

Requirements 90, 91, 92, 93, 94, 95, 99, 100, 101. An Improvement Department whose only job is
to make every other department measurably better — which means the word *measurably* has to be
load-bearing rather than decorative.

Each cell owns one metric that can be computed from rows. Not a rating somebody assigns: a
number the database already contains or can produce, so "this cell got better" is checkable by
somebody who does not trust the cell.

The loop is observe → hypothesise → sandbox → test → promote → monitor, and two properties
carry it:

**The baseline is captured before the change, or there is no baseline.** An improvement
measured against a number taken afterwards is measured against itself, and every promotion
looks like a success. `propose()` records the baseline at proposal time and `promote()` refuses
a hypothesis whose baseline was never taken.

**A promotion stores its way back before it is applied (#93).** Not afterwards, because the
moment something is degrading is the moment nobody has time to work out how to undo it.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from . import governance

PROPOSED = "proposed"
TESTING = "testing"
PROMOTED = "promoted"
REJECTED = "rejected"
REVERTED = "reverted"

STATES: tuple[str, ...] = (PROPOSED, TESTING, PROMOTED, REJECTED, REVERTED)

# A promoted change that degrades its own metric by more than this is reverted rather than
# discussed. Small enough to catch a real regression, wide enough not to fire on noise.
REGRESSION_TOLERANCE = 0.05


@dataclass(frozen=True)
class Cell:
    """One department's improvement cell, and the single number it answers for."""

    key: str
    department: str
    metric: str
    higher_is_better: bool
    what_it_means: str
    measure: str          # how the number is produced, in words a reader can check


CELLS: tuple[Cell, ...] = (
    Cell("product_creativity", "Creativity", "tournament_survival_with_spread", True,
         "concepts surviving the jury, read together with field spread",
         "creative/tournament.scorecard over recorded tournaments"),
    Cell("pattern_engineering", "Pattern Engineering", "certification_first_pass_rate", True,
         "patterns certified without a correction round",
         "certified PatternVersion rows against total compiled"),
    Cell("quality", "QA", "defects_found_after_release", False,
         "defects that reached a release instead of being caught before it",
         "Incident rows whose product had already certified"),
    Cell("market_radar", "Market Radar", "benchmark_evidence_freshness_hours", False,
         "how stale the newest benchmark evidence is",
         "age of the most recent BenchmarkObservation"),
    Cell("pricing", "Pricing", "contribution_margin", True,
         "contribution after platform fees",
         "LedgerEntry net against gross"),
    Cell("creative_assets", "Creative Assets", "asset_block_rate", False,
         "assets refused by Asset Truth or the thumbnail check",
         "ListingAsset rows not approved against total"),
    Cell("seo_search", "SEO / Search", "distinct_query_clusters", True,
         "how many genuinely different searches the catalogue answers",
         "Keyword rows grouped by cluster"),
    Cell("growth", "Growth", "acquisition_loops_with_evidence", True,
         "loops producing attributable traffic",
         "growth loop registry entries carrying measured traffic"),
    Cell("customer_experience", "Customer Experience", "support_cases_per_order", False,
         "how often a purchase produces a question",
         "SupportCase rows against orders"),
    Cell("portfolio", "Portfolio", "top_sku_revenue_share", False,
         "concentration: how much depends on the single best product",
         "LedgerEntry revenue grouped by product"),
    Cell("finance", "Finance", "forecast_error", False,
         "how far forecast revenue sat from actual",
         "forecast against LedgerEntry by month"),
    Cell("runtime", "Runtime", "dead_letters_per_day", False,
         "jobs that exhausted their retries",
         "Job rows in the dead state per day"),
)

BY_KEY: dict[str, Cell] = {c.key: c for c in CELLS}


class ImprovementRefused(ValueError):
    """A hypothesis that cannot be tested, or a promotion that cannot be trusted."""


def record_capability(db, cell: str, value: float, *, sample: int = 0,
                      detail: dict | None = None) -> int:
    """One measurement of one cell. The history that makes 'better' checkable (#94)."""
    from ..core.models import CapabilityPoint

    if cell not in BY_KEY:
        raise ImprovementRefused(f"unknown cell {cell!r}")
    with db.session() as s:
        row = CapabilityPoint(cell=cell, metric=BY_KEY[cell].metric, value=float(value),
                              sample=int(sample), detail=dict(detail or {}))
        s.add(row)
        s.flush()
        return row.id


def capability_history(db, cell: str, *, limit: int = 50) -> list[dict]:
    from sqlalchemy import select

    from ..core.models import CapabilityPoint

    with db.session() as s:
        rows = list(s.scalars(
            select(CapabilityPoint).where(CapabilityPoint.cell == cell)
            .order_by(CapabilityPoint.id).limit(limit)))
    return [{"at": r.at.isoformat(), "value": r.value, "sample": r.sample} for r in rows]


def latest_capability(db, cell: str) -> float | None:
    history = capability_history(db, cell)
    return history[-1]["value"] if history else None


def propose(db, *, cell: str, hypothesis: str, expected_effect: str,
            rollback_ref: str, touches: tuple[str, ...] = (), reversible: bool = True,
            spend_cad: float = 0.0, spend_authorised_cad: float = 5.0) -> int:
    """Record a hypothesis, with its baseline taken now.

    The baseline is captured at proposal time on purpose. Taking it after the change means
    comparing the new behaviour against itself, which makes every promotion a success and the
    whole loop decorative.
    """
    from ..core.models import Improvement

    if cell not in BY_KEY:
        raise ImprovementRefused(f"unknown cell {cell!r}")
    if len(hypothesis.split()) < 8:
        raise ImprovementRefused(
            "a hypothesis has to say what it expects to change and why; this is a title")
    if not rollback_ref:
        raise ImprovementRefused(
            "no rollback reference. #93 requires the way back to exist before the change "
            "does, because the moment something is degrading is the moment nobody has time "
            "to work out how to undo it")

    governance.check(hypothesis, touches=touches, reversible=reversible,
                     spend_cad=spend_cad,
                     spend_authorised_cad=spend_authorised_cad).raise_if_refused()

    baseline = latest_capability(db, cell)
    with db.session() as s:
        row = Improvement(cell=cell, metric=BY_KEY[cell].metric, hypothesis=hypothesis,
                          state=PROPOSED, baseline_value=baseline,
                          baseline_ref=f"capability:{cell}:{len(capability_history(db, cell))}",
                          expected_effect=expected_effect, rollback_ref=rollback_ref,
                          cost_cad=spend_cad,
                          evidence={"touches": list(touches)})
        s.add(row)
        s.flush()
        return row.id


def test_result(db, improvement_id: int, value: float, *, evidence: dict | None = None) -> str:
    """Record what the sandbox produced, and decide whether it earned promotion."""
    from ..core.models import Improvement

    with db.session() as s:
        row = s.get(Improvement, improvement_id)
        if row is None:
            raise ImprovementRefused(f"no improvement {improvement_id}")
        if row.state not in (PROPOSED, TESTING):
            raise ImprovementRefused(
                f"improvement {improvement_id} is {row.state}, not awaiting a result")
        row.result_value = float(value)
        row.evidence = {**(row.evidence or {}), **(evidence or {})}

        cell = BY_KEY[row.cell]
        if row.baseline_value is None:
            # No baseline is not a pass. A first measurement is a baseline, not a result.
            row.state = REJECTED
            row.evidence = {**row.evidence,
                            "why": ("no baseline existed, so there is nothing this result is "
                                    "better than. The measurement becomes the baseline")}
            record_capability(db, row.cell, value, detail={"from": "first measurement"})
            return REJECTED

        better = (value > row.baseline_value if cell.higher_is_better
                  else value < row.baseline_value)
        row.state = TESTING if better else REJECTED
        if not better:
            row.evidence = {**row.evidence,
                            "why": (f"{value} is not better than the baseline "
                                    f"{row.baseline_value} for a metric where "
                                    f"{'higher' if cell.higher_is_better else 'lower'} is "
                                    f"better")}
        return row.state


def promote(db, improvement_id: int, *,
            evidence: tuple[str, ...] = ()) -> str:
    """Apply a tested improvement. Refuses anything that was not actually shown to be better.

    Also refuses anything that outruns its risk tier (#178). Learning may happen as fast as
    evidence arrives; promotion may not, and the tier reads what the change *touches* rather
    than what it was called -- so a change to a spend limit cannot take the scoring lane by
    being described as one.
    """
    from ..core.models import Improvement

    from . import tiers

    with db.session() as s:
        row = s.get(Improvement, improvement_id)
        if row is None:
            raise ImprovementRefused(f"no improvement {improvement_id}")
        if row.state != TESTING:
            raise ImprovementRefused(
                f"improvement {improvement_id} is {row.state!r}. Only a change that beat a "
                f"baseline recorded before it may be promoted (#92)")
        if not row.rollback_ref:
            raise ImprovementRefused("cannot promote without a rollback path (#93)")
        touches = tuple((row.evidence or {}).get("touches") or ())
        carried = _evidence_kinds(row, extra=evidence)

    if not touches:
        raise ImprovementRefused(
            f"improvement {improvement_id} does not say what it touches, so its risk tier "
            f"cannot be graded and an ungraded change takes whichever lane its author felt "
            f"like (#178). Declare `touches` at proposal time")
    try:
        graded = tiers.check_promotion(db, touches=touches, evidence=carried)
    except tiers.TierRefused as exc:
        raise ImprovementRefused(str(exc)) from exc

    with db.session() as s:
        row = s.get(Improvement, improvement_id)
        row.state = PROMOTED
        row.promoted_at = datetime.now(timezone.utc)
        row.evidence = {**(row.evidence or {}), "tier": graded["tier"],
                        "tier_evidence": graded["satisfied"]}
        cell, result_value = row.cell, row.result_value

    tiers.record_promotion(db, tier=graded["tier"],
                           summary=f"improvement {improvement_id} on {cell}",
                           detail={"improvement_id": improvement_id, "cell": cell})
    record_capability(db, cell, result_value,
                      detail={"from": f"improvement:{improvement_id}"})
    return PROMOTED


def _evidence_kinds(row, *, extra: tuple[str, ...] = ()) -> tuple[str, ...]:
    """What this improvement actually carries, read off the row rather than asserted.

    A caller may add the kinds only it knows about -- that a regression test was written, that
    the owner approved -- and may not add the ones the row can be asked about directly.
    """
    from . import tiers

    carried = set(extra)
    carried.discard(tiers.BASELINE)
    carried.discard(tiers.SANDBOX_RESULT)
    carried.discard(tiers.ROLLBACK)
    if row.baseline_value is not None:
        carried.add(tiers.BASELINE)
    if row.result_value is not None:
        carried.add(tiers.SANDBOX_RESULT)
    if row.rollback_ref:
        carried.add(tiers.ROLLBACK)
    return tuple(sorted(carried))


def monitor(db, improvement_id: int, observed: float) -> dict:
    """Watch a promotion in the wild, and revert it automatically if it degrades (#93).

    Automatic rather than escalated. A regression that waits for somebody to agree it is a
    regression is a regression that stays deployed over a weekend.
    """
    from ..core.models import Improvement

    with db.session() as s:
        row = s.get(Improvement, improvement_id)
        if row is None:
            raise ImprovementRefused(f"no improvement {improvement_id}")
        if row.state != PROMOTED:
            return {"improvement": improvement_id, "state": row.state, "action": "none"}

        cell = BY_KEY[row.cell]
        expected = row.result_value or 0.0
        if cell.higher_is_better:
            degraded = observed < expected * (1 - REGRESSION_TOLERANCE)
        else:
            degraded = observed > expected * (1 + REGRESSION_TOLERANCE)

        if degraded:
            row.state = REVERTED
            row.reverted_at = datetime.now(timezone.utc)
            row.evidence = {**(row.evidence or {}),
                            "reverted_because": (
                                f"observed {observed} against {expected} at promotion, "
                                f"outside the {REGRESSION_TOLERANCE:.0%} tolerance"),
                            "rollback_ref": row.rollback_ref}
            outcome = {"improvement": improvement_id, "state": REVERTED,
                       "action": "reverted", "rollback_ref": row.rollback_ref,
                       "observed": observed, "expected": expected}
        else:
            outcome = {"improvement": improvement_id, "state": PROMOTED, "action": "held",
                       "observed": observed, "expected": expected}

    record_capability(db, row.cell, observed, detail={"from": "post-promotion monitoring"})
    return outcome


def retrospective(db, *, days: int = 7) -> dict:
    """The weekly machine-readable retrospective (#100).

    Reports what regressed as prominently as what improved, and names the bottleneck. A
    retrospective that lists only wins is a newsletter.
    """
    from sqlalchemy import select

    from ..core.models import CapabilityPoint, Improvement, Lesson

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    def _aware(value):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    with db.session() as s:
        improvements = [r for r in s.scalars(select(Improvement))
                        if _aware(r.at) >= cutoff]
        points = list(s.scalars(select(CapabilityPoint)))
        lessons = [r for r in s.scalars(select(Lesson)) if _aware(r.at) >= cutoff]

    by_state: dict[str, int] = {}
    for row in improvements:
        by_state[row.state] = by_state.get(row.state, 0) + 1

    moved: dict[str, dict] = {}
    for cell in CELLS:
        series = [p for p in points if p.cell == cell.key]
        if len(series) < 2:
            continue
        first, last = series[0].value, series[-1].value
        direction = "improved" if (
            (last > first) == cell.higher_is_better and last != first) else (
            "flat" if last == first else "regressed")
        moved[cell.key] = {"from": first, "to": last, "direction": direction,
                           "metric": cell.metric}

    regressed = [k for k, v in moved.items() if v["direction"] == "regressed"]
    unmeasured = [c.key for c in CELLS if not any(p.cell == c.key for p in points)]

    return {
        "window_days": days,
        "improvements_by_state": by_state,
        "promoted": [r.id for r in improvements if r.state == PROMOTED],
        "reverted": [r.id for r in improvements if r.state == REVERTED],
        "capability_movement": moved,
        "regressed_cells": regressed,
        "unmeasured_cells": unmeasured,
        "lessons_recorded": len(lessons),
        # #104's clause, run rather than described. A retrospective is where a plateau has
        # to arrive: it is the weekly moment somebody reads, and a defect that only exists
        # when queried does not exist.
        "creative_plateau": capability_plateau(db, cell=CREATIVE_CELL),
        "bottleneck": (regressed[0] if regressed else
                       (unmeasured[0] if unmeasured else None)),
        "honest_note": (
            f"{len(unmeasured)} of {len(CELLS)} cells have no capability measurement at all, "
            f"so improvement in them is unclaimable rather than unproven."
            if unmeasured else
            "Every cell has a measured history, so movement in any of them is checkable."),
    }


# ---------------------------------------------------------------------------
# #104: a plateau is a defect, not a disappointing quarter
#
# The requirement is explicit that the Improvement Department *treats* a creative plateau as
# a top-level business defect. Computing one and leaving it in a report is not treating it as
# anything -- the whole point of the wording is that it has to arrive where defects arrive,
# unprompted, and be as awkward as any other defect.

PLATEAU_SIGNATURE = "creative-capability-plateau"

# The cell #104 is about. Named rather than parameterised, because "which capability" is the
# requirement's answer and not a caller's choice.
CREATIVE_CELL = "product_creativity"


def capability_plateau(db, *, cell: str = CREATIVE_CELL, readings: int = 3) -> dict:
    """Has this cell's own measured capability stopped moving?

    Reads the capability history the cell already records, and applies the rules from
    `creative.standard.plateau`: a move below the meaningful threshold is not a move, and a
    cell with too few readings is `unmeasured` rather than flat. A company that stopped
    measuring looks exactly like one that stopped improving.
    """
    from ..creative.standard import MEANINGFUL_MOVE

    if cell not in BY_KEY:
        raise ImprovementRefused(f"unknown cell {cell!r}")
    # `capability_history` is ordered oldest-first and its `limit` takes the *earliest*
    # rows, so a small limit here would read the cell's first readings forever. Take the
    # whole history and then the tail, which is the window "has it stopped moving" is about.
    history = capability_history(db, cell, limit=1000)
    values = [row["value"] for row in history if row.get("value") is not None]
    window = values[-readings:]

    if len(window) < readings:
        return {
            "cell": cell, "verdict": "unmeasured", "is_defect": False,
            "readings": len(window), "needs": readings,
            "reason": (f"{len(window)} capability reading(s) against {readings}. A cell that "
                       f"stopped being measured is not a cell that stopped improving, and "
                       f"reporting one as the other sends the remedy in the wrong direction"),
        }

    moves = [round(window[i + 1] - window[i], 6) for i in range(len(window) - 1)]
    higher_is_better = BY_KEY[cell].higher_is_better
    meaningful = [m for m in moves if abs(m) >= MEANINGFUL_MOVE]
    flat = not meaningful
    backwards = bool(meaningful) and all(
        (m <= 0 if higher_is_better else m >= 0) for m in moves)

    return {
        "cell": cell,
        "metric": BY_KEY[cell].metric,
        "values": window,
        "moves": moves,
        "threshold": MEANINGFUL_MOVE,
        "verdict": "plateau" if flat else "declining" if backwards else "moving",
        "is_defect": flat or backwards,
        "reason": (
            f"{readings} consecutive readings of {BY_KEY[cell].metric!r} moved by less than "
            f"{MEANINGFUL_MOVE}. #104 makes that a top-level business defect rather than a "
            f"disappointing quarter" if flat else
            f"{BY_KEY[cell].metric!r} has moved backwards across {readings} readings"
            if backwards else
            f"{BY_KEY[cell].metric!r} moved by {max(moves, key=abs)}"),
    }


def raise_plateau_defect(db, *, cell: str = CREATIVE_CELL, readings: int = 3) -> dict:
    """Open an incident when capability has stopped moving, and close it when it starts.

    Both halves, because a defect that never closes becomes furniture and a company learns to
    read past it. Idempotent: an open incident with this signature is updated rather than
    duplicated, so a plateau lasting six weeks is one defect six weeks old and not six.

    It does not halt publication. A plateau is a business defect, not a safety one, and a
    gate that stops the company shipping because its ideas are not improving fast enough
    would be the wrong remedy applied with real force.
    """
    from sqlalchemy import select

    from ..core.models import Incident

    state = capability_plateau(db, cell=cell, readings=readings)
    signature = f"{PLATEAU_SIGNATURE}:{cell}"

    with db.session() as s:
        existing = s.scalar(select(Incident).where(
            Incident.signature == signature, Incident.resolved.is_(False)))

        if state["is_defect"]:
            if existing is None:
                s.add(Incident(
                    severity="P2", signature=signature,
                    summary=(f"Creative capability has stopped moving: {state['reason']}"),
                    halts_publication=False, detail=state))
                return {**state, "incident": "opened"}
            existing.report_count += 1
            existing.detail = state
            return {**state, "incident": "still_open",
                    "reported": existing.report_count}

        if existing is not None:
            existing.resolved = True
            existing.detail = state
            return {**state, "incident": "resolved"}
    return {**state, "incident": "none"}
