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
    # F-799: Learn runs under the same RUN/GROW/IMPROVE contract as every other department.
    Cell("learn", "Learn", "lesson_gap_coverage", True,
         "share of source-backed learner needs an approved lesson covers",
         "LearnGap rows COVERED against total LearnGap rows"),
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


def trial_direction(row) -> bool:
    """Whether higher is better for this improvement row's metric.

    A row proposed against a registered sandbox trial (`trial_metric` in its evidence) is
    judged on that trial's own metric and direction -- a replay's on-time share, a self-audit
    score -- and every other row on its cell's metric. One helper so the sandbox, promotion
    and the monitor can never disagree about which way is up.
    """
    declared = ((getattr(row, "evidence", None) or {}).get("trial_metric") or {})
    if "higher_is_better" in declared:
        return bool(declared["higher_is_better"])
    return BY_KEY[row.cell].higher_is_better


def is_trial_metric(row) -> bool:
    return bool(((getattr(row, "evidence", None) or {}).get("trial_metric") or {}).get("metric"))


def propose(db, *, cell: str, hypothesis: str, expected_effect: str,
            rollback_ref: str, touches: tuple[str, ...] = (), reversible: bool = True,
            spend_cad: float = 0.0, spend_authorised_cad: float = 5.0,
            proposed_by: str = "", trial: str = "", trial_metric: str = "",
            higher_is_better: bool | None = None, baseline: float | None = None,
            baseline_ref: str = "", change: dict | None = None) -> int:
    """Record a hypothesis, with its baseline taken now.

    The baseline is captured at proposal time on purpose. Taking it after the change means
    comparing the new behaviour against itself, which makes every promotion a success and the
    whole loop decorative.

    A proposal may instead name a registered sandbox `trial` and the metric that trial
    measures (`trial_metric`, `higher_is_better`). Its baseline is then the trial's own
    reading of the incumbent *now* (`baseline`, `baseline_ref`), taken by the proposer before
    anything changes -- or None when the trial has nothing to read yet, in which case the
    trial's first reading becomes the baseline and never a result. `change` names what the
    promotion executes (a configuration version, a standard floor).
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
                     spend_cad=spend_cad, spend_authorised_cad=spend_authorised_cad,
                     cell=cell).raise_if_refused()

    # Surfaces and the proposer are stored normalised, so every later comparison -- the
    # tier, the Director's shared-surface check, separation of duties -- compares like with
    # like (C-19, C-22). An unattributed proposal is recorded as such: it can be tested and
    # judged, and it can never be promoted, because nobody can be shown not to be its author
    # (C-18).
    proposer = governance.normalise_actor(proposed_by)
    extra: dict = {}
    if trial:
        if not trial_metric or higher_is_better is None:
            raise ImprovementRefused(
                "a proposal judged by a sandbox trial names the metric the trial measures and "
                "which way is better; otherwise its result is compared against nothing")
        metric = trial_metric[:60]
        ref = (baseline_ref or f"trial:{trial}:unanchored")[:80]
        extra = {"sandbox_trial": trial,
                 "trial_metric": {"metric": metric, "higher_is_better": bool(higher_is_better)},
                 **({"change": dict(change)} if change else {})}
    else:
        metric = BY_KEY[cell].metric
        baseline = latest_capability(db, cell)
        ref = f"capability:{cell}:{len(capability_history(db, cell))}"
    with db.session() as s:
        row = Improvement(cell=cell, metric=metric, hypothesis=hypothesis,
                          state=PROPOSED, baseline_value=baseline,
                          baseline_ref=ref,
                          expected_effect=expected_effect, rollback_ref=rollback_ref,
                          cost_cad=spend_cad,
                          evidence={"touches": list(governance.normalise_touches(touches)),
                                    **({"proposed_by": proposer} if proposer
                                       else {"unattributed": True}), **extra})
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
        row.evidence = {**(row.evidence or {}), **(evidence or {}),
                        "decided_at": datetime.now(timezone.utc).isoformat()}

        up = trial_direction(row)
        trial_row = is_trial_metric(row)
        if row.baseline_value is None:
            # No baseline is not a pass. A first measurement is a baseline, not a result.
            row.state = REJECTED
            row.evidence = {**row.evidence,
                            "why": ("no baseline existed, so there is nothing this result is "
                                    "better than. The measurement becomes the baseline")}
            if not trial_row:
                record_capability(db, row.cell, value, detail={"from": "first measurement"})
            return REJECTED

        better = (value > row.baseline_value if up else value < row.baseline_value)
        row.state = TESTING if better else REJECTED
        if not better:
            row.evidence = {**row.evidence,
                            "why": (f"{value} is not better than the baseline "
                                    f"{row.baseline_value} for a metric where "
                                    f"{'higher' if up else 'lower'} is "
                                    f"better")}
        return row.state


def anchor_baseline(db, improvement_id: int, value: float, *, ref: str) -> dict:
    """Record a trial's first reading as the baseline of a proposal that had none.

    Only for a PROPOSED row judged by a sandbox trial, and only once: a first measurement is
    a baseline and never a result, so the row stays PROPOSED and waits for a later reading.
    """
    from ..core.models import Improvement

    with db.session() as s:
        row = s.get(Improvement, improvement_id)
        if row is None:
            raise ImprovementRefused(f"no improvement {improvement_id}")
        if row.state != PROPOSED or row.baseline_value is not None or not is_trial_metric(row):
            raise ImprovementRefused(
                f"improvement {improvement_id} already has a baseline or is not a trial "
                f"proposal awaiting one; a baseline is never re-taken after the fact")
        row.baseline_value = float(value)
        row.baseline_ref = (ref or "")[:80]
        row.evidence = {**(row.evidence or {}),
                        "baseline_anchored": {"value": float(value), "ref": ref,
                                              "at": datetime.now(timezone.utc).isoformat()}}
    return {"improvement": improvement_id, "baseline": float(value), "ref": ref}


def reject(db, improvement_id: int, *, why: str, evidence: dict | None = None) -> str:
    """Reject a proposal whose sandbox verdict did not earn promotion, with the reason."""
    from ..core.models import Improvement

    with db.session() as s:
        row = s.get(Improvement, improvement_id)
        if row is None:
            raise ImprovementRefused(f"no improvement {improvement_id}")
        if row.state not in (PROPOSED, TESTING):
            raise ImprovementRefused(f"improvement {improvement_id} is {row.state}")
        row.state = REJECTED
        row.evidence = {**(row.evidence or {}), **(evidence or {}), "why": why[:400],
                        "decided_at": datetime.now(timezone.utc).isoformat()}
    return REJECTED


def approve(db, improvement_id: int, *, approved_by: str, why: str = "") -> dict:
    """An independent judge's approval of a tested change. Never the proposer's own (#85, #179).

    The author of a change has necessarily been thinking about the cases it handles well, so
    an approval from the proposer is refused, and a meta-agent role may approve only if it
    holds the judging power. Approval is recorded evidence, not promotion: the tier, its
    cooldown and its ceiling still decide whether and when the change may land.
    """
    from ..core.models import Improvement
    from . import roles

    who = governance.normalise_actor(approved_by)
    if not who:
        raise ImprovementRefused("an approval names who approved")
    if who in roles.BY_KEY and roles.JUDGE not in roles.BY_KEY[who].powers:
        raise ImprovementRefused(
            f"{who} may not approve: its powers are {list(roles.BY_KEY[who].powers)} and "
            f"approving is judging")
    with db.session() as s:
        row = s.get(Improvement, improvement_id)
        if row is None:
            raise ImprovementRefused(f"no improvement {improvement_id}")
        if row.state != TESTING:
            raise ImprovementRefused(
                f"improvement {improvement_id} is {row.state!r}; only a change that beat its "
                f"baseline in the sandbox can be approved")
        proposer = governance.normalise_actor((row.evidence or {}).get("proposed_by"))
        if proposer and proposer == who:
            raise ImprovementRefused(
                f"{who} proposed improvement {improvement_id} and may not approve it. The "
                f"proposing agent may not be the judge of its own change")
        # Recorded either way; for an unattributed proposal the approval cannot be shown to
        # be independent, so `promote` will refuse it however it was judged.
        row.evidence = {**(row.evidence or {}), "approved_by": who,
                        "approved_because": why,
                        "approval_independent": bool(proposer),
                        "approved_at": datetime.now(timezone.utc).isoformat()}
    return {"improvement": improvement_id, "approved_by": who, "proposed_by": proposer,
            "independent": bool(proposer)}


def promote(db, improvement_id: int, *,
            evidence: tuple[str, ...] = (), promoted_by: str = "") -> str:
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
        if row.baseline_value is None or row.result_value is None or not (
                row.result_value > row.baseline_value if trial_direction(row)
                else row.result_value < row.baseline_value):
            raise ImprovementRefused(
                f"improvement {improvement_id} has no recorded result better than its "
                f"recorded baseline ({row.result_value} against {row.baseline_value}); only "
                f"a change that beat a baseline recorded before it may be promoted (#92)")
        touches = governance.normalise_touches((row.evidence or {}).get("touches") or ())
        carried = _evidence_kinds(row, extra=evidence)
        proposer = governance.normalise_actor((row.evidence or {}).get("proposed_by"))
        approver = governance.normalise_actor((row.evidence or {}).get("approved_by"))
    promoter = governance.normalise_actor(promoted_by)

    # Separation of duties, at the door itself rather than at the callers that thought of it
    # (C-17, C-18, C-19). A change is promoted only when it has a recorded proposer, an
    # approval recorded by somebody else, and a named promoter who is not the proposer. All
    # three names are compared normalised, so 'Listing' and 'listing ' are listing.
    if not proposer:
        raise ImprovementRefused(
            f"improvement {improvement_id} has no recorded proposer, so no approval or "
            f"promotion of it can be shown to be independent of its author. Separation of "
            f"duties is not opt-in: re-propose it with `proposed_by`")
    if not promoter:
        raise ImprovementRefused(
            f"improvement {improvement_id} was proposed by {proposer!r}; its promotion "
            f"has to name who is promoting it, so that it can be shown not to be them")
    if promoter == proposer:
        raise ImprovementRefused(
            f"{proposer!r} proposed improvement {improvement_id} and may not promote it. "
            f"The proposing agent may not be the judge of its own change")
    if not approver:
        raise ImprovementRefused(
            f"improvement {improvement_id} beat its baseline and has not been approved. "
            f"Promotion needs an approval recorded by a judge independent of its proposer "
            f"(`approve`), not only a better number")
    if approver == proposer:
        raise ImprovementRefused("a change approved by its own proposer is unapproved")

    # The Improvement Director (#91): two cells optimising the same surface, or metrics
    # that trade against each other, promote neither until the conflict is resolved.
    from . import director

    director.detect(db)
    blocking = director.blocking(db, improvement_id)
    if blocking:
        raise ImprovementRefused(
            f"improvement {improvement_id} is in an unresolved conflict with "
            f"{blocking['with']}: {blocking['why']}. Neither side is promoted until the "
            f"Improvement Director's conflict is resolved")

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
                        "tier_evidence": graded["satisfied"],
                        "promoted_by": promoter}
        cell, result_value = row.cell, row.result_value
        trial_row = is_trial_metric(row)

    tiers.record_promotion(db, tier=graded["tier"],
                           summary=f"improvement {improvement_id} on {cell}",
                           detail={"improvement_id": improvement_id, "cell": cell})
    if not trial_row:
        # A trial-metric result is in the trial's units, not the cell's, and writing it as a
        # capability point would put a replay's on-time share on a dead-letter curve.
        record_capability(db, cell, result_value,
                          detail={"from": f"improvement:{improvement_id}"})
    return PROMOTED


# The one identity whose approval satisfies a gate-tier promotion. Owner approval is recorded
# on the row by `record_owner_approval`, never asserted by the promoting caller (C-21).
OWNER = "owner"

# Evidence kinds that exist only as a record on the improvement row. A caller naming one of
# these at promotion without the record is refused, not believed: "evidence=(REGRESSION_TEST,)"
# is a string, and a string is not a test result.
RECORDED_KINDS: tuple[str, ...] = ("regression_test", "adversarial_test", "owner_approval")


def record_test(db, improvement_id: int, *, kind: str, ref: str, passed: bool,
                recorded_by: str) -> dict:
    """Record a regression or adversarial test run against this improvement.

    The record names the run (`ref`: a test id, a job id, a commit) and who recorded it, and
    the recorder may not be the proposer. A failed run is recorded too, and it does not count.
    """
    from ..core.models import Improvement
    from . import tiers

    if kind not in (tiers.REGRESSION_TEST, tiers.ADVERSARIAL_TEST):
        raise ImprovementRefused(
            f"{kind!r} is not a test kind; recorded tests are "
            f"{[tiers.REGRESSION_TEST, tiers.ADVERSARIAL_TEST]}")
    who = governance.normalise_actor(recorded_by)
    if not who or not (ref or "").strip():
        raise ImprovementRefused("a test record names the run and who recorded it")
    with db.session() as s:
        row = s.get(Improvement, improvement_id)
        if row is None:
            raise ImprovementRefused(f"no improvement {improvement_id}")
        if who == governance.normalise_actor((row.evidence or {}).get("proposed_by")):
            raise ImprovementRefused(
                f"{who!r} proposed improvement {improvement_id} and may not record the tests "
                f"that clear it")
        tests = dict((row.evidence or {}).get("tests") or {})
        tests[kind] = {"ref": ref.strip(), "passed": bool(passed), "by": who,
                       "at": datetime.now(timezone.utc).isoformat()}
        row.evidence = {**(row.evidence or {}), "tests": tests}
    return {"improvement": improvement_id, "kind": kind, "passed": bool(passed)}


def record_owner_approval(db, improvement_id: int, *, approved_by: str, why: str) -> dict:
    """The owner's decision on a gate-tier change, recorded on the row it approves."""
    from ..core.models import Improvement

    who = governance.normalise_actor(approved_by)
    if who != OWNER:
        raise ImprovementRefused(
            f"{approved_by!r} is not the owner. A gate-tier change reaches production only "
            f"with the owner's recorded decision")
    if len((why or "").split()) < 3:
        raise ImprovementRefused("an owner approval says why; this is a label")
    with db.session() as s:
        row = s.get(Improvement, improvement_id)
        if row is None:
            raise ImprovementRefused(f"no improvement {improvement_id}")
        row.evidence = {**(row.evidence or {}),
                        "owner_approval": {"by": who, "because": why,
                                           "at": datetime.now(timezone.utc).isoformat()}}
    return {"improvement": improvement_id, "owner_approved": True}


def _evidence_kinds(row, *, extra: tuple[str, ...] = ()) -> tuple[str, ...]:
    """What this improvement actually carries, read off the row rather than asserted.

    Every kind is read from the row: the baseline, the sandbox result and the rollback from
    their columns, the tests from `record_test`, the owner's approval from
    `record_owner_approval`. A caller may name kinds it expects the row to carry, and naming
    one the row does not carry is refused rather than believed (C-21).
    """
    from . import tiers

    evidence = row.evidence or {}
    carried = set()
    if row.baseline_value is not None:
        carried.add(tiers.BASELINE)
    if row.result_value is not None:
        carried.add(tiers.SANDBOX_RESULT)
    if row.rollback_ref:
        carried.add(tiers.ROLLBACK)
    for kind, record in (evidence.get("tests") or {}).items():
        if isinstance(record, dict) and record.get("passed") and record.get("ref"):
            carried.add(kind)
    owner = evidence.get("owner_approval") or {}
    if isinstance(owner, dict) and governance.normalise_actor(owner.get("by")) == OWNER:
        carried.add(tiers.OWNER_APPROVAL)
    asserted = [kind for kind in extra if kind not in carried
                and kind not in (tiers.BASELINE, tiers.SANDBOX_RESULT, tiers.ROLLBACK)]
    if asserted:
        raise ImprovementRefused(
            f"evidence {asserted} was asserted by the caller and is not recorded on "
            f"improvement {row.id}. Record it with `record_test` or `record_owner_approval`; "
            f"a named kind is not a result")
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

        up = trial_direction(row)
        trial_row = is_trial_metric(row)
        expected = row.result_value or 0.0
        if up:
            degraded = observed < expected * (1 - REGRESSION_TOLERANCE)
        else:
            degraded = observed > expected * (1 + REGRESSION_TOLERANCE)
        # Below the baseline captured before the change is a regression whatever the
        # tolerance says: the change is now worse than not having made it.
        baseline = row.baseline_value
        below_baseline = baseline is not None and (
            observed < baseline if up else observed > baseline)
        degraded = degraded or below_baseline

        if degraded:
            row.state = REVERTED
            row.reverted_at = datetime.now(timezone.utc)
            row.evidence = {**(row.evidence or {}),
                            "reverted_because": (
                                f"observed {observed} against {expected} at promotion and "
                                f"{baseline} at baseline: "
                                + ("worse than the baseline captured before the change"
                                   if below_baseline else
                                   f"outside the {REGRESSION_TOLERANCE:.0%} tolerance")),
                            "rollback_ref": row.rollback_ref}
            outcome = {"improvement": improvement_id, "state": REVERTED,
                       "action": "reverted", "rollback_ref": row.rollback_ref,
                       "observed": observed, "expected": expected, "baseline": baseline,
                       "below_baseline": below_baseline}
        else:
            outcome = {"improvement": improvement_id, "state": PROMOTED, "action": "held",
                       "observed": observed, "expected": expected}

    if not trial_row:
        record_capability(db, row.cell, observed, detail={"from": "post-promotion monitoring"})
    return outcome


# The durable record of a rollback that has been decided and not yet shown to have taken
# effect (C-81). It lives on the PROMOTED row -- the state the next scan selects -- so a
# process killed between deciding and executing resumes the rollback rather than losing it.
ROLLBACK_PENDING = "rollback_pending"


def mark_rollback_pending(db, improvement_id: int, *, because: str,
                          observed: float | None = None) -> dict:
    """Record that a promoted trial improvement must be rolled back, before anything is undone.

    The row stays PROMOTED: REVERTED is the *completion* of a rollback, written by `revert`
    only once the executor has run and the active configuration or floor has been verified
    restored. Writing REVERTED first and executing second (the original order) meant a crash
    between the two left a reverted row nobody would scan again and a regression still live.
    Idempotent: a rollback already pending keeps its first decision and its attempt count.
    """
    from ..core.models import Improvement

    with db.session() as s:
        row = s.get(Improvement, improvement_id)
        if row is None:
            raise ImprovementRefused(f"no improvement {improvement_id}")
        if row.state != PROMOTED:
            return {"improvement": improvement_id, "state": row.state, "action": "none"}
        evidence = dict(row.evidence or {})
        pending = dict(evidence.get(ROLLBACK_PENDING) or {})
        if not pending:
            pending = {"because": because[:400], "observed": observed,
                       "decided_at": datetime.now(timezone.utc).isoformat(), "attempts": 0,
                       "rollback_ref": row.rollback_ref}
            row.evidence = {**evidence, ROLLBACK_PENDING: pending}
        return {"improvement": improvement_id, "state": PROMOTED, "action": "rollback_pending",
                "rollback_ref": row.rollback_ref, "observed": pending.get("observed"),
                "expected": row.result_value, "baseline": row.baseline_value,
                "below_baseline": True, "because": pending["because"],
                "attempts": pending.get("attempts", 0)}


def note_rollback_attempt(db, improvement_id: int, *, executor: str) -> int:
    """Count a rollback attempt durably *before* the executor runs, so a crash mid-way is
    visible as an attempt that never verified rather than as nothing having happened."""
    from ..core.models import Improvement

    with db.session() as s:
        row = s.get(Improvement, improvement_id)
        if row is None:
            raise ImprovementRefused(f"no improvement {improvement_id}")
        evidence = dict(row.evidence or {})
        pending = dict(evidence.get(ROLLBACK_PENDING) or {})
        if not pending:
            raise ImprovementRefused(
                f"improvement {improvement_id} has no pending rollback to attempt; decide it "
                f"with `mark_rollback_pending` first")
        pending["attempts"] = int(pending.get("attempts", 0)) + 1
        pending["last_attempt"] = {"executor": executor,
                                   "at": datetime.now(timezone.utc).isoformat()}
        row.evidence = {**evidence, ROLLBACK_PENDING: pending}
        return pending["attempts"]


def rollback_pending(db, improvement_id: int) -> dict | None:
    from ..core.models import Improvement

    with db.session() as s:
        row = s.get(Improvement, improvement_id)
        if row is None or row.state != PROMOTED:
            return None
        pending = (row.evidence or {}).get(ROLLBACK_PENDING)
        return dict(pending) if pending else None


def revert(db, improvement_id: int, *, because: str, observed: float | None = None,
           verified: dict | None = None) -> dict:
    """Complete the rollback of a promoted trial improvement: REVERTED, with the proof.

    `monitor` judges a promotion against a capability reading; a trial-metric promotion is
    judged by re-running its own trial on data that did not exist when it won. Either way
    REVERTED is written here only *after* the rollback executor has run and its effect has
    been verified (`verified`: what was checked and what it read) -- the active configuration
    is the version it replaced, the floor is gone. A revert asked for without that proof is
    refused: a row that says "reverted" while the regression is still running is the failure
    C-81 named, and it is worse than an honest "rollback pending".
    """
    from ..core.models import Improvement

    if not verified or not verified.get("verified"):
        raise ImprovementRefused(
            f"improvement {improvement_id} cannot be marked reverted without verified rollback "
            f"evidence. Decide it with `mark_rollback_pending`, run the executor, verify the "
            f"active configuration or floor, and pass that check as `verified`")
    with db.session() as s:
        row = s.get(Improvement, improvement_id)
        if row is None:
            raise ImprovementRefused(f"no improvement {improvement_id}")
        if row.state != PROMOTED:
            return {"improvement": improvement_id, "state": row.state, "action": "none"}
        evidence = dict(row.evidence or {})
        pending = dict(evidence.pop(ROLLBACK_PENDING, None) or {})
        row.state = REVERTED
        row.reverted_at = datetime.now(timezone.utc)
        row.evidence = {**evidence, "reverted_because": because[:400],
                        "rollback_ref": row.rollback_ref,
                        "rollback": {"decided_at": pending.get("decided_at"),
                                     "attempts": pending.get("attempts"),
                                     "verified": dict(verified),
                                     "completed_at": row.reverted_at.isoformat()}}
        return {"improvement": improvement_id, "state": REVERTED, "action": "reverted",
                "rollback_ref": row.rollback_ref, "observed": observed,
                "expected": row.result_value, "baseline": row.baseline_value,
                "below_baseline": True, "verified": dict(verified)}


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

    # #100's remaining clauses, each computed from rows by the Improvement Director rather
    # than written up: experiments that reached a verdict and the ones killed, what to stop
    # doing, and the upgrades nearest to landing.
    from . import director

    ran = director.experiments(db, days=days)
    lessons_learned = [{"id": r.id, "subject": r.subject, "from": r.origin_cell,
                        "statement": r.statement[:200]} for r in lessons]

    return {
        "window_days": days,
        "improvements_by_state": by_state,
        "promoted": [r.id for r in improvements if r.state == PROMOTED],
        "reverted": [r.id for r in improvements if r.state == REVERTED],
        "capability_movement": moved,
        "regressed_cells": regressed,
        "unmeasured_cells": unmeasured,
        "lessons_recorded": len(lessons),
        "learned": lessons_learned,
        "experiments_completed": ran["completed"],
        "experiments_killed": ran["killed"],
        "stop_doing": director.stop_doing(db),
        "top_next_upgrades": director.next_upgrades(db),
        "department_health": {c.key: (moved.get(c.key, {}).get("direction")
                                      or ("unmeasured" if c.key in unmeasured
                                          else "one reading"))
                              for c in CELLS},
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
