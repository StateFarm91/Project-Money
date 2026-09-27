"""The sandbox step: the part of observe -> hypothesise -> sandbox -> test -> promote that runs.

Requirement 92. `cells` had every door of the loop -- `propose`, `test_result`, `record_test`,
`approve`, `promote`, `monitor` -- and in the running system proposals were opened nightly and
then sat in PROPOSED for ever, because nothing took one through a sandbox, recorded its tests
or judged it. This is that step, as one pass a cadence runs. It adds no authority of its own:
every transition goes through the `cells` door that already refuses the wrong thing.

**A sandbox result is a trial the runner can re-derive from rows, or there is none.** A
proposal here is a hypothesis, not an executable patch, so the only honest sandbox is one that
computes what the metric would read with the change applied from evidence already recorded.
Each trial is registered by name in `TRIALS`, reads rows only, and returns the value with the
row it came from. A proposal no trial can evaluate stays PROPOSED and is reported as waiting
for one: a number invented to move it along would be the loop grading itself.

The one trial registered today is `counterfactual_rollback`, for the self-review's
`declining_capability` proposal ("the last promoted change in this cell should be
re-examined"). The change that proposal asks for is putting the last promotion back, and the
cell's capability *without* that promotion is on record: it is the baseline that promotion
captured before it landed. If that reading is better than where the cell is now, the evidence
supports the rollback; if not, `cells.test_result` rejects the proposal as no better.

**Tests are recorded runs by somebody other than the proposer.** The regression test replays
every captured defect fixture through the deterministic compiler (`gates.regression.run`) and
passes only when at least one fixture ran and every one is still caught -- an empty suite is
recorded as a failed run, not a pass. The adversarial test re-derives the sandbox value from
the rows and refuses any drift from what was recorded, re-runs the governance boundary, and
refuses a proposal whose hypothesis implies a riskier surface than it declared. Both go
through `cells.record_test`, recorded by `RUNNER`, which never proposes.

**Approval is the evaluator's, and only for what the runner itself tested.** The evaluator
role holds the judging power and no proposing power, and `cells.approve` refuses it for a
change it proposed. It approves only rows carrying this runner's own sandbox record and two
passed tests, so a change marked TESTING some other way is left for a judge rather than
waved through.

**Promotion follows #190's split.** A pre-authorised tier (`upgrades.PRE_AUTHORISED`) is
promoted through `cells.promote` when `upgrades.may_auto_promote` allows it, so the tier's
evidence, cooldown and ceiling bind. Every other tier becomes an owner card in the single
owner queue, and is promoted only once `cells.record_owner_approval` has recorded the owner's
decision on the row -- which nothing in this module ever calls.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from . import cells, governance, tiers, upgrades

ACTION = "improve.sandbox"
# Records tests. Never proposes, so `record_test`'s rule that the proposer may not record the
# tests that clear its own change always holds for it.
RUNNER = "sandbox_runner"
# The independent judge. `roles.evaluator` holds JUDGE and never PROPOSE.
JUDGE = "evaluator"
# The meta-agent role whose job this is: turning a hypothesis into a test that can come back
# negative. It is the author the upgrade pipeline records for the owner card.
UPGRADE_AUTHOR = "experiment_designer"

# Proposals that change nothing: their remedy is a measurement, which `improve.measure` takes.
MEASUREMENT_KINDS: tuple[str, ...] = ("never_measured", "stale_measurement")


class SandboxRefused(ValueError):
    """A trial asked to evaluate a proposal it cannot evaluate."""


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


# ---- trials ------------------------------------------------------------------------------


def trial_counterfactual_rollback(db, improvement_id: int) -> dict:
    """The cell's capability without its last promoted change, as recorded before it landed."""
    from sqlalchemy import select

    from ..core.models import Improvement

    with db.session() as s:
        row = s.get(Improvement, improvement_id)
        if row is None:
            raise SandboxRefused(f"no improvement {improvement_id}")
        proposed_at = _aware(row.at)
        candidates = [r for r in s.scalars(select(Improvement).where(
            Improvement.cell == row.cell, Improvement.state == cells.PROMOTED,
            Improvement.id != row.id)) if r.promoted_at is not None
            and _aware(r.promoted_at) <= proposed_at and r.baseline_value is not None]
        if not candidates:
            return {"ran": False, "trial": "counterfactual_rollback",
                    "why": (f"no promoted change on {row.cell} before this proposal carries a "
                            f"pre-change baseline, so there is nothing to re-examine and no "
                            f"recorded reading of the cell without it")}
        last = max(candidates, key=lambda r: (_aware(r.promoted_at), r.id))
        return {"ran": True, "trial": "counterfactual_rollback",
                "value": float(last.baseline_value),
                "run_ref": f"improvement:{last.id}:baseline:{last.baseline_ref}",
                "reads": {"improvement": last.id, "baseline_ref": last.baseline_ref,
                          "rollback_ref": last.rollback_ref},
                "why": (f"{row.cell} read {last.baseline_value} before improvement {last.id} "
                        f"was promoted; that is the recorded capability with it rolled back")}


TRIALS: dict[str, Callable[..., dict]] = {
    "counterfactual_rollback": trial_counterfactual_rollback,
}

# Which trial answers which self-review proposal kind.
TRIAL_FOR_KIND: dict[str, str] = {"declining_capability": "counterfactual_rollback"}


def trial_for(evidence: dict) -> str | None:
    """The registered trial for a proposal: named on it, or implied by its kind."""
    named = str(evidence.get("sandbox_trial") or "").strip()
    if named:
        return named if named in TRIALS else None
    return TRIAL_FOR_KIND.get(str(evidence.get("kind") or ""))


# ---- tests ---------------------------------------------------------------------------------


def regression_test(*, directory=None) -> dict:
    """Every captured defect fixture, replayed through the deterministic compiler."""
    from ..gates import regression

    run = regression.run(directory)
    passed = run.checked > 0 and run.ok
    return {"passed": passed, "checked": run.checked, "failures": run.failures[:5],
            "why": ("every captured defect is still caught" if passed else
                    "no regression fixture could be run, and an empty suite is not a pass"
                    if run.checked == 0 else
                    f"{len(run.failures)} captured defect(s) no longer caught")}


def adversarial_test(db, improvement_id: int) -> dict:
    """Try to break the claim: drifted evidence, a boundary breach, a hidden riskier surface."""
    from ..core.models import Improvement

    with db.session() as s:
        row = s.get(Improvement, improvement_id)
        evidence = dict(row.evidence or {})
        hypothesis, recorded = row.hypothesis, row.result_value
    touches = governance.normalise_touches(evidence.get("touches") or ())
    sandbox = evidence.get("sandbox") or {}
    problems: list[str] = []

    trial = TRIALS.get(str(sandbox.get("trial") or ""))
    if trial is None:
        problems.append("no registered trial is recorded, so the result cannot be re-derived")
    else:
        again = trial(db, improvement_id)
        if not again.get("ran"):
            problems.append(f"the trial no longer runs: {again.get('why')}")
        elif recorded is None or abs(float(again["value"]) - float(recorded)) > 1e-9:
            problems.append(f"the recorded result {recorded} is not what the trial derives "
                            f"from the rows now ({again['value']})")
        elif again.get("run_ref") != sandbox.get("run_ref"):
            problems.append("the trial now reads a different row than the one recorded")

    boundary = governance.check(hypothesis, touches=touches)
    if not boundary.ok:
        problems.append(f"the governance boundary refuses it: {boundary.reason}")

    implied = governance.implied_surfaces(hypothesis)
    try:
        declared = tiers.classify(touches)
        everything = tiers.classify(tuple(touches) + tuple(implied))
        if everything.rank > declared.rank:
            problems.append(f"it declares {list(touches)} ({declared.key}) and its wording "
                            f"implies {sorted(implied)} ({everything.key})")
    except tiers.TierRefused as exc:
        problems.append(str(exc))

    return {"passed": not problems, "problems": problems,
            "why": "every attempt to break the claim failed" if not problems else
                   "; ".join(problems)[:400]}


# ---- the pass --------------------------------------------------------------------------------


def _rows(db) -> list[dict]:
    from sqlalchemy import select

    from ..core.models import Improvement

    with db.session() as s:
        return [{"id": r.id, "cell": r.cell, "state": r.state,
                 "baseline": r.baseline_value, "result": r.result_value,
                 "evidence": dict(r.evidence or {})}
                for r in s.scalars(select(Improvement).where(
                    Improvement.state.in_((cells.PROPOSED, cells.TESTING)))
                    .order_by(Improvement.id))]


def _ours(evidence: dict) -> bool:
    return (evidence.get("sandbox") or {}).get("by") == RUNNER


def run(db, *, now: datetime | None = None, regression_dir=None) -> dict:
    """One pass: sandbox what a trial can evaluate, test, judge, then promote or route."""
    now = now or datetime.now(timezone.utc)
    sandboxed, waiting, tested, approved, promoted, carded, held = [], [], [], [], [], [], []

    # 1. SANDBOX: a PROPOSED change with a baseline and a registered trial gets its result.
    for r in _rows(db):
        if r["state"] != cells.PROPOSED:
            continue
        ev = r["evidence"]
        if ev.get("kind") in MEASUREMENT_KINDS:
            continue                          # a measurement, which improve.measure takes
        name = trial_for(ev)
        if name is None:
            waiting.append({"improvement": r["id"], "cell": r["cell"],
                            "why": "no registered sandbox trial can evaluate this proposal, "
                                   "so it waits rather than being given an invented result"})
            continue
        if r["baseline"] is None:
            waiting.append({"improvement": r["id"], "cell": r["cell"],
                            "why": "no baseline was captured at proposal time"})
            continue
        out = TRIALS[name](db, r["id"])
        if not out.get("ran"):
            waiting.append({"improvement": r["id"], "cell": r["cell"], "trial": name,
                            "why": out.get("why")})
            continue
        state = cells.test_result(db, r["id"], out["value"], evidence={"sandbox": {
            "trial": name, "run_ref": out["run_ref"], "by": RUNNER,
            "reads": out.get("reads"), "at": now.isoformat(), "why": out.get("why")}})
        sandboxed.append({"improvement": r["id"], "cell": r["cell"], "trial": name,
                          "baseline": r["baseline"], "result": out["value"],
                          "state": state})

    regression = None
    for r in _rows(db):
        if r["state"] != cells.TESTING or not _ours(r["evidence"]):
            continue
        iid, ev = r["id"], r["evidence"]
        recorded = ev.get("tests") or {}

        # 2. TEST: regression and adversarial, recorded by the runner, once per row.
        if tiers.REGRESSION_TEST not in recorded or tiers.ADVERSARIAL_TEST not in recorded:
            if regression is None:
                regression = regression_test(directory=regression_dir)
            adversarial = adversarial_test(db, iid)
            cells.record_test(db, iid, kind=tiers.REGRESSION_TEST,
                              ref=(f"gates.regression.run@{now.isoformat()}:"
                                   f"{regression['checked']} fixture(s)"),
                              passed=regression["passed"], recorded_by=RUNNER)
            cells.record_test(db, iid, kind=tiers.ADVERSARIAL_TEST,
                              ref=f"{ACTION}.adversarial@{now.isoformat()}:improvement:{iid}",
                              passed=adversarial["passed"], recorded_by=RUNNER)
            tested.append({"improvement": iid, "regression": regression["passed"],
                           "adversarial": adversarial["passed"],
                           "why": [regression["why"], adversarial["why"]]})
            recorded = {tiers.REGRESSION_TEST: {"passed": regression["passed"]},
                        tiers.ADVERSARIAL_TEST: {"passed": adversarial["passed"]}}

        failed = [k for k in (tiers.REGRESSION_TEST, tiers.ADVERSARIAL_TEST)
                  if not (recorded.get(k) or {}).get("passed")]
        if failed:
            held.append({"improvement": iid, "why": f"{failed} did not pass; not judged"})
            continue

        # 3. JUDGE: the evaluator approves what beat its baseline and survived both tests.
        if not ev.get("approved_by"):
            try:
                cells.approve(db, iid, approved_by=JUDGE, why=(
                    f"beat its baseline in the runner's {ev['sandbox'].get('trial')} trial "
                    f"({r['result']} against {r['baseline']}), and the regression suite and "
                    f"adversarial checks recorded by {RUNNER} both passed"))
                approved.append(iid)
            except cells.ImprovementRefused as exc:
                held.append({"improvement": iid, "why": str(exc)[:300]})
                continue
        elif governance.normalise_actor(ev.get("approved_by")) != JUDGE:
            held.append({"improvement": iid,
                         "why": f"approved by {ev.get('approved_by')!r}; left to that judge"})
            continue

        # 4. PROMOTE or ROUTE, by tier.
        outcome = _promote_or_route(db, iid, now=now)
        {"promoted": promoted, "carded": carded}.get(outcome["route"], held).append(outcome)

    closed = _close_settled_cards(db)
    return {"at": now.isoformat(), "sandboxed": sandboxed, "waiting": waiting,
            "tested": tested, "approved": approved, "promoted": promoted,
            "owner_cards": carded, "held": held, "cards_closed": closed,
            "trials": sorted(TRIALS),
            "note": (f"{len(sandboxed)} sandboxed, {len(tested)} tested, {len(approved)} "
                     f"approved by {JUDGE}, {len(promoted)} promoted, {len(carded)} routed to "
                     f"the owner, {len(waiting)} waiting for a trial that can evaluate them")}


def _promote_or_route(db, iid: int, *, now: datetime) -> dict:
    from ..core.models import Improvement

    with db.session() as s:
        row = s.get(Improvement, iid)
        touches = governance.normalise_touches((row.evidence or {}).get("touches") or ())
        owner = ((row.evidence or {}).get("owner_approval") or {})
        hypothesis = row.hypothesis
    try:
        tier = tiers.classify(touches)
        proposal = upgrades.from_improvement(db, iid, author_role=UPGRADE_AUTHOR)
    except (tiers.TierRefused, upgrades.UpgradeRefused) as exc:
        return {"route": "held", "improvement": iid, "why": str(exc)[:300]}

    owner_decided = governance.normalise_actor(owner.get("by")) == cells.OWNER
    if tier.key in upgrades.PRE_AUTHORISED or owner_decided:
        if tier.key in upgrades.PRE_AUTHORISED and not owner_decided:
            verdict = upgrades.may_auto_promote(db, proposal, now=now)
            if not verdict["may_auto_promote"]:
                return {"route": "held", "improvement": iid, "tier": tier.key,
                        "why": verdict["why"][:300]}
        try:
            cells.promote(db, iid, promoted_by=JUDGE)
        except (cells.ImprovementRefused, tiers.TierRefused) as exc:
            return {"route": "held", "improvement": iid, "tier": tier.key,
                    "why": str(exc)[:300]}
        upgrades.close_owner_card(db, f"{upgrades.IMPROVEMENT_CARD_PREFIX}{iid}")
        return {"route": "promoted", "improvement": iid, "tier": tier.key,
                "by": JUDGE, "owner_approved": owner_decided}

    try:
        card = upgrades.owner_card(proposal)
    except upgrades.UpgradeRefused as exc:
        return {"route": "held", "improvement": iid, "tier": tier.key, "why": str(exc)[:300]}
    queued = upgrades.queue_owner_card(
        db, f"{upgrades.IMPROVEMENT_CARD_PREFIX}{iid}", card,
        action=(f"Decide improvement {iid} ({tier.key} tier): {hypothesis[:200]}. It beat "
                f"its recorded baseline in the sandbox and passed its regression and "
                f"adversarial tests. Approve by recording your decision on improvement {iid} "
                f"(cells.record_owner_approval, approved_by='owner'), or decline it"),
        minutes=5, blocks=f"improvement:{iid}")
    return {"route": "carded", "improvement": iid, "tier": tier.key, **queued}


def _close_settled_cards(db) -> list[str]:
    """Close a card whose improvement is no longer waiting for a decision."""
    from sqlalchemy import select

    from ..core.models import Improvement, OwnerAction

    closed = []
    with db.session() as s:
        cards = [(a.id, a.requirement_key) for a in s.scalars(select(OwnerAction).where(
            OwnerAction.done == False)) if (a.requirement_key or "").startswith(  # noqa: E712
                upgrades.IMPROVEMENT_CARD_PREFIX)]
        for _id, key in cards:
            try:
                iid = int(key.split(":", 1)[1])
            except (IndexError, ValueError):
                continue
            row = s.get(Improvement, iid)
            if row is None or row.state != cells.TESTING:
                closed.append(key)
    for key in closed:
        upgrades.close_owner_card(db, key)
    return closed


def state() -> dict:
    return {
        "action": ACTION,
        "trials": {k: (v.__doc__ or "").strip().splitlines()[0] for k, v in TRIALS.items()},
        "trial_for_kind": dict(TRIAL_FOR_KIND),
        "records_tests_as": RUNNER, "approves_as": JUDGE,
        "pre_authorised_tiers": list(upgrades.PRE_AUTHORISED),
        "never": ["invents a sandbox result", "records an owner approval",
                  "approves a change it did not sandbox"],
    }
