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

from datetime import datetime, timedelta, timezone
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


def trial_league_replay(db, improvement_id: int) -> dict:
    """A configuration challenger and its incumbent, replayed on the same historical jobs."""
    from . import replay

    return replay.trial(db, improvement_id)


def _self_audit_after(row) -> datetime | None:
    anchored = ((row.evidence or {}).get("baseline_anchored") or {}).get("at")
    if anchored:
        return _aware(datetime.fromisoformat(anchored))
    return _aware(row.at)


def trial_self_audit(db, improvement_id: int) -> dict:
    """Our own products' self-audit on the element a teardown finding named (#164).

    The comparison #164 asks for is against the current Brambleloop standard, so the value is
    the catalogue's newest self-audit reading on that element recorded after the proposal (or
    after its anchored baseline) -- a later audit of the changed product, never the finding.
    """
    from ..core.models import Improvement
    from ..teardown import enforce

    with db.session() as s:
        row = s.get(Improvement, improvement_id)
        if row is None:
            raise SandboxRefused(f"no improvement {improvement_id}")
        change = dict((row.evidence or {}).get("change") or {})
        after = _self_audit_after(row) if row.baseline_value is not None else None
        if row.baseline_value is None:
            after = _aware(row.at) - timedelta(days=36500)
    key = change.get("key")
    if not key:
        return {"ran": False, "trial": "self_audit", "why": "the proposal names no element"}
    scores = enforce.catalogue_scores(db, key, after=after)
    if not scores:
        return {"ran": False, "trial": "self_audit",
                "why": (f"no self-audit of a Brambleloop product on {key} has been recorded "
                        f"since the proposal; the comparison is against our own product, "
                        f"measured, and nothing has measured it")}
    value = round(sum(v for _i, v in scores) / len(scores), 4)
    ids = [i for i, _v in scores]
    return {"ran": True, "trial": "self_audit", "value": value,
            "run_ref": f"self_audit:{key}:{ids}"[:190],
            "reads": {"findings": ids, "key": key},
            "why": (f"{len(ids)} product self-audit(s) on {key} read {value} on the 0-5 scale "
                    f"against the benchmark's {change.get('benchmark_score')}")}


# Codex M06 / M09: what each executor genuinely does when a promotion is applied. Named
# here so the state route and the executed record say the same thing.
SELF_AUDIT_IMPLEMENTS = "standard"          # a floor at the release gate, not an artefact change
LEAGUE_REPLAY_IMPLEMENTS = "job_priority_policy"   # the one configuration the replay produces runs for

def trial_policy_loop(db, improvement_id: int) -> dict:
    """A policy-loop challenger re-derived from the frozen decision rows it was proposed on."""
    from . import policy_loops

    return policy_loops.trial(db, improvement_id)


# v1.1 lane B: the five launch policy loops (listing/SEO, support, pattern defects, visual
# gate, cost per release). What a promotion executes is the registry incumbent the
# consumer reads (`policy_loops.active`).
POLICY_LOOP_IMPLEMENTS = "policy_loop_parameter"

TRIALS: dict[str, Callable[..., dict]] = {
    "counterfactual_rollback": trial_counterfactual_rollback,
    "league_replay": trial_league_replay,
    "self_audit": trial_self_audit,
    "policy_loop": trial_policy_loop,
}


# ---- what a promotion executes, how it is watched, and how it is undone -------------------


def _execute_league_replay(db, iid: int) -> dict:
    from . import replay

    return replay.execute(db, iid)


def _execute_self_audit(db, iid: int) -> dict:
    from ..core.models import Improvement
    from ..teardown import enforce

    with db.session() as s:
        row = s.get(Improvement, iid)
        change = dict((row.evidence or {}).get("change") or {})
        floor = row.result_value
    adopted = enforce.adopt_floor(db, int(change["finding"]), floor=float(floor),
                                  improvement_id=iid)
    # Codex M06: what this promotion implements is a *standard*, and the record says so.
    # The floor is the level our own self-audits of the current release reached; adopting it
    # commits the company to it at the release gate (`release_gates.for_publish` refuses a
    # release that reads below it) and on support cases (the pattern_help obligations). It
    # changes no pattern, listing, image or reply itself: the artefact change that raised a
    # release to this level was made on that artefact's own surface, and a later release that
    # falls below it is refused, not repaired, by this record.
    return {"executed": "standard floor", **adopted,
            "implements": SELF_AUDIT_IMPLEMENTS, "changes_artifact": False,
            "enforced_by": ("release_gates.for_publish via teardown.enforce._judge (unmet "
                            "below the floor); teardown.enforce.pattern_help_obligations on "
                            "open support cases"),
            "artifact_change": ("none by this promotion: the floor is enforced on every later "
                                "release, never applied to one")}


def _monitor_self_audit(db, iid: int) -> dict:
    from ..core.models import Improvement
    from ..teardown import enforce

    with db.session() as s:
        row = s.get(Improvement, iid)
        change = dict((row.evidence or {}).get("change") or {})
        promoted_at = _aware(row.promoted_at)
        baseline = row.baseline_value
        seen = list((row.evidence or {}).get("monitored_windows") or [])
    scores = enforce.catalogue_scores(db, change.get("key", ""), after=promoted_at)
    if not scores:
        return {"judged": False, "why": "no self-audit recorded since the promotion"}
    ref = str([i for i, _v in scores])
    if ref in seen:
        return {"judged": False, "why": "already judged against these self-audits"}
    observed = round(sum(v for _i, v in scores) / len(scores), 4)
    with db.session() as s:
        row = s.get(Improvement, iid)
        row.evidence = {**(row.evidence or {}), "monitored_windows": seen + [ref],
                        "monitoring": {"observed": observed, "window": ref}}
    worse = baseline is not None and observed < baseline
    return {"judged": True, "observed": observed, "worse": worse,
            "why": (f"self-audits {ref} read {observed} against the baseline {baseline}"
                    + (": worse than before the change" if worse else ""))}


def _rollback_self_audit(db, iid: int, *, why: str) -> dict:
    from ..core.models import Improvement
    from ..teardown import enforce

    with db.session() as s:
        change = dict((s.get(Improvement, iid).evidence or {}).get("change") or {})
    return enforce.drop_floor(db, int(change["finding"]), why=why)


def _verify_self_audit(db, iid: int) -> dict:
    from ..core.models import Improvement
    from ..teardown import enforce

    with db.session() as s:
        change = dict((s.get(Improvement, iid).evidence or {}).get("change") or {})
    return enforce.floor_absent(db, int(change["finding"]))


def _monitor_league_replay(db, iid: int) -> dict:
    from . import replay

    return replay.monitor(db, iid)


def _rollback_league_replay(db, iid: int, *, why: str) -> dict:
    from . import replay

    return replay.rollback(db, iid, why=why)


def _verify_league_replay(db, iid: int) -> dict:
    from . import replay

    return replay.rollback_verified(db, iid)


def _execute_policy_loop(db, iid: int) -> dict:
    from . import policy_loops

    return policy_loops.execute(db, iid)


def _monitor_policy_loop(db, iid: int) -> dict:
    from . import policy_loops

    return policy_loops.monitor(db, iid)


def _rollback_policy_loop(db, iid: int, *, why: str) -> dict:
    from . import policy_loops

    return policy_loops.rollback(db, iid, why=why)


def _verify_policy_loop(db, iid: int) -> dict:
    from . import policy_loops

    return policy_loops.rollback_verified(db, iid)


EXECUTORS: dict[str, Callable[..., dict]] = {
    "league_replay": _execute_league_replay, "self_audit": _execute_self_audit,
    "policy_loop": _execute_policy_loop}
MONITORS: dict[str, Callable[..., dict]] = {
    "league_replay": _monitor_league_replay, "self_audit": _monitor_self_audit,
    "policy_loop": _monitor_policy_loop}
# Rollback executors are idempotent: run twice, the second run finds the previous version
# already the incumbent (or the floor already gone) and changes nothing. That is what lets a
# rollback interrupted at any point be resumed by the next pass (C-81).
ROLLBACKS: dict[str, Callable[..., dict]] = {
    "league_replay": _rollback_league_replay, "self_audit": _rollback_self_audit,
    "policy_loop": _rollback_policy_loop}
# What each rollback must be shown to have done before the row may say REVERTED: the active
# job-priority configuration is the version it replaced; the adopted floor is gone.
VERIFIERS: dict[str, Callable[..., dict]] = {
    "league_replay": _verify_league_replay, "self_audit": _verify_self_audit,
    "policy_loop": _verify_policy_loop}

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
                 "cost": r.cost_cad or 0.0, "evidence": dict(r.evidence or {})}
                for r in s.scalars(select(Improvement).where(
                    Improvement.state.in_((cells.PROPOSED, cells.TESTING)))
                    .order_by(Improvement.id))]


def _ours(evidence: dict) -> bool:
    return (evidence.get("sandbox") or {}).get("by") == RUNNER


# ---- #99: the department's own ROI order and its stagnation and thrash rules ---------------

STAGNATION_SIGNATURE = "improve-stagnation"
# Assessed promotions with no return before the department is treated as stagnating.
STAGNATION_ASSESSED = 3
# Reverts in one cell inside the window before that cell's proposals are held as thrash.
THRASH_REVERTS = 2
THRASH_DAYS = 30


def order(db, rows: list[dict]) -> dict:
    """PROPOSED rows in `roi.prioritise` order: expected impact per dollar, free first.

    A proposal that says in advance what it expects (`expected_gain`) is ranked; one that
    cannot is not refused its sandbox -- a trial is how it gets a number -- but it goes after
    every proposal that could say, and is reported as unprioritised.
    """
    from . import roi

    said = [{"key": r["id"], "expected_impact": r["evidence"].get("expected_gain"),
             "cost_cad": r.get("cost", 0.0)}
            for r in rows if r["evidence"].get("expected_gain") is not None]
    ranked = [c["key"] for c in roi.prioritise(said)["ranked"]] if said else []
    unsaid = [r["id"] for r in rows if r["evidence"].get("expected_gain") is None]
    by_id = {r["id"]: r for r in rows}
    return {"rows": [by_id[i] for i in ranked + unsaid], "ranked": ranked,
            "unprioritised": unsaid}


def discipline(db, *, now: datetime) -> dict:
    """The stagnation and thrash rules applied to the Improvement Department itself (#99)."""
    from sqlalchemy import select

    from ..core.models import Improvement, Incident
    from . import roi

    realised = roi.realised_benefit(db, now=now)
    stagnating = (realised["assessed"] >= STAGNATION_ASSESSED
                  and not realised["returned"])
    cutoff = now - timedelta(days=THRASH_DAYS)
    reverts: dict[str, int] = {}
    with db.session() as s:
        for r in s.scalars(select(Improvement).where(Improvement.state == cells.REVERTED)):
            if r.reverted_at is not None and _aware(r.reverted_at) >= cutoff:
                reverts[r.cell] = reverts.get(r.cell, 0) + 1
        existing = s.scalar(select(Incident).where(
            Incident.signature == STAGNATION_SIGNATURE, Incident.resolved.is_(False)))
        if stagnating and existing is None:
            s.add(Incident(severity="P2", signature=STAGNATION_SIGNATURE,
                           summary=(f"The Improvement Department is stagnating: "
                                    f"{realised['assessed']} promotion(s) assessed and none "
                                    f"returned its expected benefit. The sandbox is throttled "
                                    f"to one trial per pass until one does (#99)"),
                           halts_publication=False,
                           detail={"owner": "orchestrator", "realised": {
                               k: realised[k] for k in ("assessed", "hit_rate", "spent_cad")}}))
        elif not stagnating and existing is not None:
            existing.resolved = True
    thrashing = sorted(c for c, n in reverts.items() if n >= THRASH_REVERTS)
    return {"stagnating": stagnating, "assessed": realised["assessed"],
            "hit_rate": realised["hit_rate"], "thrashing_cells": thrashing,
            "limit": 1 if stagnating else None}


def run(db, *, now: datetime | None = None, regression_dir=None) -> dict:
    """One pass: sandbox what a trial can evaluate, test, judge, then promote or route."""
    now = now or datetime.now(timezone.utc)
    # 0. OBSERVE + PROPOSE (v1.1 lane B): the policy loops read the outcomes recorded since
    #    the last pass and open at most one guarded, challenged proposal. Isolated: a loop's
    #    failure is reported in its own entry and never stops the sandbox pass.
    from . import policy_loops

    try:
        loops = policy_loops.cycle(db, now=now)
    except Exception as exc:  # noqa: BLE001 - reported, never silent
        loops = {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}
    sandboxed, waiting, tested, approved, promoted, carded, held = [], [], [], [], [], [], []
    anchored, rejected, executed = [], [], []
    rules = discipline(db, now=now)
    proposed_rows = [r for r in _rows(db) if r["state"] == cells.PROPOSED]
    ordering = order(db, proposed_rows)

    # 1. SANDBOX: a PROPOSED change with a baseline and a registered trial gets its result,
    #    in expected-impact order (#99), throttled while the department is stagnating.
    for r in ordering["rows"]:
        ev = r["evidence"]
        if ev.get("kind") in MEASUREMENT_KINDS:
            continue                          # a measurement, which improve.measure takes
        if rules["limit"] is not None and len(sandboxed) >= rules["limit"]:
            waiting.append({"improvement": r["id"], "cell": r["cell"],
                            "why": "the department is stagnating; one trial per pass (#99)"})
            continue
        if r["cell"] in rules["thrashing_cells"]:
            waiting.append({"improvement": r["id"], "cell": r["cell"],
                            "why": (f"{r['cell']} reverted {THRASH_REVERTS} or more promotions "
                                    f"in {THRASH_DAYS} days; held as thrash (#99)")})
            continue
        name = trial_for(ev)
        if name is None:
            waiting.append({"improvement": r["id"], "cell": r["cell"],
                            "why": "no registered sandbox trial can evaluate this proposal, "
                                   "so it waits rather than being given an invented result"})
            continue
        if r["baseline"] is None:
            if name in EXECUTORS or ev.get("trial_metric"):
                first = TRIALS[name](db, r["id"])
                if first.get("ran"):
                    cells.anchor_baseline(db, r["id"], first["value"], ref=first["run_ref"])
                    anchored.append({"improvement": r["id"], "baseline": first["value"],
                                     "trial": name})
                    waiting.append({"improvement": r["id"], "cell": r["cell"], "trial": name,
                                    "why": ("the trial's first reading became the baseline; "
                                            "a first measurement is never a result")})
                    continue
                waiting.append({"improvement": r["id"], "cell": r["cell"], "trial": name,
                                "why": first.get("why")})
                continue
            waiting.append({"improvement": r["id"], "cell": r["cell"],
                            "why": "no baseline was captured at proposal time"})
            continue
        out = TRIALS[name](db, r["id"])
        if not out.get("ran"):
            waiting.append({"improvement": r["id"], "cell": r["cell"], "trial": name,
                            "why": out.get("why")})
            continue
        if out.get("blockers"):
            cells.reject(db, r["id"], why=("the league held it: "
                                            + "; ".join(out["blockers"])[:350]),
                         evidence={"sandbox": {"trial": name, "run_ref": out["run_ref"],
                                               "by": RUNNER, "at": now.isoformat()}})
            rejected.append({"improvement": r["id"], "trial": name,
                             "why": out["blockers"][:2]})
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
            regression_ref = (f"gates.regression.run@{now.isoformat()}:"
                              f"{regression['checked']} fixture(s)")
            adversarial_ref = f"{ACTION}.adversarial@{now.isoformat()}:improvement:{iid}"
            cells.record_test(db, iid, kind=tiers.REGRESSION_TEST, ref=regression_ref,
                              passed=regression["passed"], recorded_by=RUNNER)
            cells.record_test(db, iid, kind=tiers.ADVERSARIAL_TEST, ref=adversarial_ref,
                              passed=adversarial["passed"], recorded_by=RUNNER)
            # C-82: these two runs actually happened, against a named configuration version
            # when the proposal carries one. They are the only way `tests_run` is written.
            observed = _record_config_test_runs(db, ev, runs=(
                ("gates.regression.run", regression_ref, regression["passed"]),
                (f"{ACTION}.adversarial", adversarial_ref, adversarial["passed"])))
            tested.append({"improvement": iid, "regression": regression["passed"],
                           "adversarial": adversarial["passed"],
                           "why": [regression["why"], adversarial["why"]],
                           "config_runs_recorded": observed})
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

    # 5. EXECUTE: a promotion that changes nothing is a promotion on paper. Whatever promoted
    #    this pass (or was promoted by the weekly executor) and has an executor is applied.
    executed = execute_promoted(db)

    closed = _close_settled_cards(db)
    return {"at": now.isoformat(), "sandboxed": sandboxed, "waiting": waiting,
            "tested": tested, "approved": approved, "promoted": promoted,
            "owner_cards": carded, "held": held, "cards_closed": closed,
            "anchored": anchored, "rejected": rejected, "executed": executed,
            "prioritised": ordering["ranked"], "unprioritised": ordering["unprioritised"],
            "discipline": rules,
            "trials": sorted(TRIALS),
            "policy_loops": {k: {kk: v.get(kk) for kk in ("reading", "why")}
                             | {"state": (v.get("outcome") or {}).get("state")}
                             for k, v in (loops.get("loops") or {}).items()},
            "note": (f"{len(sandboxed)} sandboxed, {len(tested)} tested, {len(approved)} "
                     f"approved by {JUDGE}, {len(promoted)} promoted, {len(carded)} routed to "
                     f"the owner, {len(waiting)} waiting for a trial that can evaluate them")}


def _record_config_test_runs(db, evidence: dict, *, runs: tuple) -> int:
    """Attach the runner's observed test runs to the configuration version under test.

    Only when the proposal names one (`change.config_id`), and only against that version's
    own digest -- `league.record_test_run` refuses anything else. Declared coverage stays in
    `tests_declared`; this is the observed half (C-82).
    """
    from ..core.models import ConfigVersion
    from . import league

    config_id = int(((evidence.get("change") or {}).get("config_id")) or 0)
    if not config_id:
        return 0
    with db.session() as s:
        row = s.get(ConfigVersion, config_id)
        digest = row.digest if row is not None else ""
    if not digest:
        return 0
    recorded = 0
    for test, run_id, passed in runs:
        try:
            out = league.record_test_run(db, config_id, test=test, run_id=run_id,
                                         source_sha256=digest, passed=passed,
                                         recorded_by=RUNNER)
        except league.LeagueRefused:
            continue
        recorded += 1 if out.get("recorded") else 0
    return recorded


def execute_promoted(db) -> list[dict]:
    """Apply every promoted trial improvement not yet executed. Idempotent on the row."""
    from sqlalchemy import select

    from ..core.models import Improvement

    with db.session() as s:
        todo = [(r.id, (r.evidence or {}).get("sandbox_trial"))
                for r in s.scalars(select(Improvement).where(
                    Improvement.state == cells.PROMOTED))
                if (r.evidence or {}).get("sandbox_trial") in EXECUTORS
                and not (r.evidence or {}).get("executed")]
    out = []
    for iid, trial in todo:
        try:
            done = EXECUTORS[trial](db, iid)
        except Exception as exc:  # noqa: BLE001 - recorded, and retried next pass
            out.append({"improvement": iid, "executed": False, "why": str(exc)[:200]})
            continue
        with db.session() as s:
            row = s.get(Improvement, iid)
            row.evidence = {**(row.evidence or {}), "executed": {
                **{k: v for k, v in done.items() if isinstance(v, (str, int, float, bool))},
                "at": datetime.now(timezone.utc).isoformat()}}
        out.append({"improvement": iid, "trial": trial, **done})
    return out


def monitor_trials(db, *, now: datetime | None = None) -> dict:
    """Re-run each promoted trial improvement's trial on fresh data; revert what reads worse."""
    from sqlalchemy import select

    from ..core.models import Improvement
    from . import monitor as monitor_mod

    with db.session() as s:
        rows = [(r.id, r.cell, (r.evidence or {}).get("sandbox_trial"),
                 bool((r.evidence or {}).get(cells.ROLLBACK_PENDING)))
                for r in s.scalars(select(Improvement).where(
                    Improvement.state == cells.PROMOTED))
                if (r.evidence or {}).get("sandbox_trial") in MONITORS]
    judged, reverted, waiting, pending = [], [], [], []
    for iid, cell, trial, has_pending in rows:
        if has_pending:
            # A rollback decided on an earlier pass and not yet verified complete -- the
            # process died between deciding and executing, or between executing and
            # verifying. It is resumed, never re-judged: the decision stands until the effect
            # is shown (C-81).
            done = _complete_rollback(db, iid, cell, trial)
            (reverted if done["state"] == cells.REVERTED else pending).append(done)
            continue
        seen = MONITORS[trial](db, iid)
        if not seen.get("judged"):
            waiting.append({"improvement": iid, "why": seen.get("why")})
            continue
        if not seen.get("worse"):
            judged.append({"improvement": iid, "observed": seen.get("observed"),
                           "action": "held"})
            continue
        # 1. Decide, durably, on the still-PROMOTED row; 2. open the incident so the pending
        # rollback is visible even if nothing below runs; 3. execute, verify, and only then
        # write REVERTED.
        outcome = cells.mark_rollback_pending(db, iid, because=seen["why"],
                                              observed=seen.get("observed"))
        monitor_mod._rollback_proposal(db, iid, cell, outcome)
        done = _complete_rollback(db, iid, cell, trial)
        (reverted if done["state"] == cells.REVERTED else pending).append(done)
    return {"judged": judged, "reverted": reverted, "waiting": waiting,
            "rollback_pending": pending}


def _complete_rollback(db, iid: int, cell: str, trial: str) -> dict:
    """Run the idempotent rollback executor, verify its effect, then complete the revert.

    Every step is durable before the next: the attempt is counted before the executor runs,
    the executor's own writes commit as they happen, and REVERTED is written last -- with
    the verifier's reading on the row -- so a crash at any point leaves a PROMOTED row with
    `rollback_pending` that the next pass resumes. The incident opened when the rollback was
    decided is resolved here, and nowhere earlier.
    """
    from . import monitor as monitor_mod

    pending = cells.rollback_pending(db, iid) or {}
    because = str(pending.get("because") or "monitor judged the promotion worse")
    attempts = cells.note_rollback_attempt(db, iid, executor=trial)
    undone = ROLLBACKS[trial](db, iid, why=because)
    check = VERIFIERS[trial](db, iid)
    flat = {k: v for k, v in undone.items() if isinstance(v, (str, int, float, bool, type(None)))}
    if not check.get("verified"):
        return {"improvement": iid, "state": cells.PROMOTED, "action": "rollback_pending",
                "attempts": attempts, "rollback": flat, "verification": check,
                "observed": pending.get("observed"),
                "why": f"rollback executed and not verified: {check.get('why')}"}
    cells.revert(db, iid, because=because, observed=pending.get("observed"), verified=check)
    incident = monitor_mod._rollback_resolved(db, iid, check)
    return {"improvement": iid, "state": cells.REVERTED, "action": "reverted",
            "attempts": attempts, "observed": pending.get("observed"), "rollback": flat,
            "verification": check, "incident": incident["incident"]}


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
        # Codex M06 / M09: the honest extent of what a promotion executes. Nothing here
        # changes an artefact, routes a model or tool, or grants a permission.
        "executes": {
            "self_audit": (f"{SELF_AUDIT_IMPLEMENTS}: a floor on the requirement (#164) "
                           f"enforced at the release gate and on support cases; no artefact "
                           f"is changed by the promotion"),
            "league_replay": (f"{LEAGUE_REPLAY_IMPLEMENTS}: the registry incumbent the "
                              f"runtime's priority_for reads; the only configuration this "
                              f"engine replays"),
            "policy_loop": (f"{POLICY_LOOP_IMPLEMENTS}: the registry incumbent of one launch "
                            f"policy loop, read by its consumer (improve.consume.matching for "
                            f"SEO and support; watchlists read by learn.improvement_status."
                            f"next_work for pattern defects, visual pre-check and cost)"),
        },
        "does_not_execute": [
            "model, prompt or tool challengers (compared by improve.league on runs recorded "
            "elsewhere; promoted only through league._authorise on that evidence)",
            "architecture changes or specialist additions (owner cards from improve.weekly; "
            "never an automatic permission grant)",
            "artefact changes implied by an adopted standard",
        ],
    }
