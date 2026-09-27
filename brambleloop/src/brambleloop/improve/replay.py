"""Deterministic replay: the league's producer of runs, and the sandbox's forward trial.

Requirements 92, 95, 180, 187, 190, 193. The league could compare, promote and roll back
recorded runs, and nothing in the running system ever recorded one: `league.record_run` had
no caller, so every challenger waited for ever and the sandbox had no forward trial at all.
The routing and image challengers are model configurations, and producing a run for one is a
model call -- a spending decision this module never takes. But one of the company's decision
policies is fully deterministic and its history is already in the database: **the job-priority
policy** (#187), which decides, inside a band, which job is claimed first from its deadline
and its business value.

So this replays it. The historical jobs are the tasks: each job's arrival (`created_at`), its
service time (`finished_at - started_at`), its band, the deadline and value its inputs carried.
A policy is scored by simulating one worker draining those arrivals in the order the policy
would have claimed them, and counting the share of jobs -- weighted by how much their band
matters -- that would have finished before their deadline (an explicit one, or their band's
service level). The same simulation, the same rows, the same number, every time.

Three rules make it a league rather than a search that grades itself.

**Tasks are days, and the newest days are a holdout.** The shared set is every replayed day
except the most recent fifth, which is never used to choose anything; a challenger that wins
the shared days and loses the holdout is refused by `league.compare` exactly as the library
already does (#180).

**Challengers are authored by the Prompt / Tool Challenger and judged by somebody else.** The
neighbours of the incumbent (one weight up or down, the horizon halved or doubled) are
registered as challenger versions under that role; the comparison is `league.compare`, and a
winner becomes an improvement hypothesis in the ordinary sandbox (`improve.runner`), where the
evaluator -- never the author -- approves it and the scoring tier's cooldown and ceiling bind.
A loser is retired with its verdict recorded, so the registry never accumulates live
challengers nobody is judging.

**Promotion executes, and the monitor can undo it.** A promoted improvement makes the
challenger the incumbent in the registry, which is what `swarm.orchestrate.priority_for` reads
on the next enqueue. While it is being monitored, the version it replaced is replayed on every
fresh window beside it; if the promoted policy reads worse on fresh data, the monitor reverts
the improvement and `league.rollback` restores the previous version.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from . import league

ACTION = "improve.replay"
AUTHOR = "prompt_tool_challenger"
CELL = "runtime"
TRIAL = "league_replay"

# The service level each band implies when a job names no deadline of its own. The order is
# the bands' commercial argument: a customer incident is late after an hour, housekeeping
# after a month.
BAND_SLA_HOURS: dict[str, float] = {
    "customer_incident": 1, "truth_defect": 4, "seasonal_deadline": 24, "proven_winner": 48,
    "benchmark_change": 72, "new_opportunity": 168, "exploration": 336,
    "housekeeping": 720,
}
WINDOW_DAYS = 30
MIN_JOBS = 20
MIN_DAYS = 3
HOLDOUT_SHARE = 0.2

# What the simulation assumes, versioned (C-63 / Codex M02). A run records the simulator it
# was produced by, two runs are compared only under the same version, and a proposal states
# the version so the claim it makes is scoped to what was actually modelled: one worker, no
# lane concurrency, unknown service times defaulted, DEAD jobs never on time. A change to any
# of these is a new version, and old runs stop being comparable with new ones.
SIMULATOR: dict = {
    "version": "replay-sim/1",
    "workers": 1,
    "lanes": "not modelled: swarm.lane_hold's per-lane concurrency is ignored",
    "claim_order": "lowest priority number first, then arrival, then id; one job at a time",
    "service_time": ("finished_at - started_at; a job missing either is given 1s and counted "
                     "in dataset.unknown_service"),
    "dead_jobs": ("occupy the worker for their recorded service time and are never counted as "
                  "on time; the failure is kept, its cause is not modelled"),
    "scope": "the job-priority policy (swarm.orchestrate.priority_decision) and nothing else",
}
# Bounds a challenger's parameters stay inside; outside them a change is not a scoring tweak.
BOUNDS: dict[str, tuple[float, float]] = {
    "deadline_weight": (0.0, 4.0), "value_weight": (0.0, 4.0),
    "horizon_days": (3.0, 90.0), "value_scale_cad": (50.0, 5000.0)}


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _policy_key() -> tuple[str, str]:
    from ..swarm.orchestrate import PRIORITY_POLICY_KEY, PRIORITY_POLICY_KIND

    return PRIORITY_POLICY_KIND, PRIORITY_POLICY_KEY


def payload_for(params: dict) -> str:
    return json.dumps({k: float(params[k]) for k in sorted(BOUNDS)}, sort_keys=True)


# ---- the tasks: historical jobs ------------------------------------------------------------


def historical_jobs(db, *, now: datetime | None = None,
                    window_days: int = WINDOW_DAYS) -> list[dict]:
    """Every job that reached a terminal state in the window, as a replayable arrival."""
    from sqlalchemy import select

    from ..core.models import Job, JobStatus

    now = now or datetime.now(timezone.utc)
    start = now - timedelta(days=window_days)
    out = []
    with db.session() as s:
        for j in s.scalars(select(Job).where(Job.status.in_((JobStatus.DONE, JobStatus.DEAD)))
                           .order_by(Job.id)):
            created = _aware(j.created_at)
            if created is None or created < start or created > now:
                continue
            started, finished = _aware(j.started_at), _aware(j.finished_at)
            known = started is not None and finished is not None
            service = (finished - started).total_seconds() if known else 1.0
            out.append({"id": j.id, "job_type": j.job_type, "inputs": dict(j.inputs or {}),
                        "created": created, "service_s": max(1.0, service),
                        "dead": j.status == JobStatus.DEAD, "service_known": known,
                        "leased_by": j.leased_by or ""})
    return out


def dataset_of(jobs: list[dict]) -> dict:
    """The identity of a replayed task set: a fingerprint over the jobs' content and the
    bounds of when they were observed (C-63 / Codex M03).

    Two runs on the same fingerprint are the same evaluation repeated, however far apart they
    were recorded; a run whose bounds end before a promotion contains nothing that promotion
    could have affected. Both are read by the monitor before anything counts as fresh.
    """
    import hashlib

    rows = sorted((int(j["id"]), str(j["job_type"]), j["created"].isoformat(),
                   float(j["service_s"]), bool(j.get("dead"))) for j in jobs)
    fingerprint = hashlib.sha256(json.dumps(rows).encode("utf-8")).hexdigest()
    created = [j["created"] for j in jobs]
    workers = {str(j.get("leased_by") or "") for j in jobs} - {""}
    return {"fingerprint": fingerprint,
            "bounds": ([min(created).isoformat(), max(created).isoformat()] if created
                       else []),
            "jobs": len(jobs), "dead_jobs": sum(1 for j in jobs if j.get("dead")),
            "unknown_service": sum(1 for j in jobs if not j.get("service_known", True)),
            "workers_observed": len(workers)}


def fidelity(dataset: dict) -> dict:
    """Whether this history was produced by what the simulator models (Codex M02).

    The simulator drains one worker. A window whose jobs were leased by more than one worker
    was produced by a pool the replay does not model, so its verdicts describe a runtime that
    did not run those jobs; runs are still recorded and compared, and no promotion is
    proposed on them. Uncertainty is carried, not rounded away: the count of defaulted
    service times and of DEAD jobs travels with every run.
    """
    reasons = []
    if dataset.get("workers_observed", 0) > SIMULATOR["workers"]:
        reasons.append(f"{dataset['workers_observed']} workers leased these jobs; "
                       f"{SIMULATOR['version']} models {SIMULATOR['workers']}")
    return {"comparable": not reasons, "simulator": SIMULATOR["version"], "reasons": reasons,
            "unknown_service": dataset.get("unknown_service", 0),
            "dead_jobs": dataset.get("dead_jobs", 0)}


def _days(jobs: list[dict]) -> list[str]:
    return sorted({j["created"].date().isoformat() for j in jobs})


def split(days: list[str]) -> tuple[list[str], list[str]]:
    """Shared days and holdout days: the newest fifth is never tuned against."""
    if len(days) < MIN_DAYS:
        return days, []
    n = max(1, int(round(len(days) * HOLDOUT_SHARE)))
    return days[:-n], days[-n:]


# ---- the simulation -------------------------------------------------------------------------


def simulate_day(db, jobs: list[dict], policy: dict, *, proven: dict | None = None) -> float:
    """Band-weighted share of one day's jobs finishing before their deadline under `policy`."""
    from ..swarm.orchestrate import BAND_BY_KIND, deadline_of, priority_decision

    if not jobs:
        return 1.0
    proven = proven if proven is not None else {}
    prepared = []
    for j in jobs:
        decision = priority_decision(j["job_type"], j["inputs"], db=None, now=j["created"],
                                     policy=policy)
        kind = decision["kind"]
        slug = str(j["inputs"].get("slug") or j["inputs"].get("product_slug") or "")
        if kind == "proven_winner" and slug and not proven.get(slug, True):
            kind = "new_opportunity"
            decision["priority"] = BAND_BY_KIND[kind] - decision["moved"]
        deadline = deadline_of(j["inputs"]) or (
            j["created"] + timedelta(hours=BAND_SLA_HOURS.get(kind, 720)))
        weight = max(1.0, 100.0 - BAND_BY_KIND[kind])
        prepared.append({**j, "priority": decision["priority"], "deadline": deadline,
                         "weight": weight})
    prepared.sort(key=lambda j: (j["created"], j["id"]))
    clock = prepared[0]["created"]
    pending: list[dict] = []
    i = 0
    on_time = total = 0.0
    while i < len(prepared) or pending:
        while i < len(prepared) and prepared[i]["created"] <= clock:
            pending.append(prepared[i])
            i += 1
        if not pending:
            clock = prepared[i]["created"]
            continue
        pending.sort(key=lambda j: (j["priority"], j["created"], j["id"]))
        job = pending.pop(0)
        clock = clock + timedelta(seconds=job["service_s"])
        total += job["weight"]
        # A job that died did not finish, whatever the clock says (SIMULATOR["dead_jobs"]).
        if clock <= job["deadline"] and not job.get("dead"):
            on_time += job["weight"]
    return round(on_time / total, 6) if total else 1.0


def replay(db, params: dict, jobs: list[dict], *, proven: dict | None = None) -> dict:
    """One policy over every replayed day: per-day quality on the shared set and the holdout."""
    policy = {**params}
    by_day: dict[str, list[dict]] = {}
    for j in jobs:
        by_day.setdefault(j["created"].date().isoformat(), []).append(j)
    shared, holdout = split(sorted(by_day))
    return {"tasks": {f"day:{d}": simulate_day(db, by_day[d], policy, proven=proven)
                      for d in shared},
            "holdout": {f"day:{d}": simulate_day(db, by_day[d], policy, proven=proven)
                        for d in holdout},
            "window": [min(by_day), max(by_day)] if by_day else [],
            "jobs": len(jobs)}


def _proven_map(db, jobs: list[dict]) -> dict:
    from ..swarm.orchestrate import product_proven

    slugs = {str(j["inputs"].get("slug") or j["inputs"].get("product_slug") or "")
             for j in jobs} - {""}
    return {slug: product_proven(db, slug) for slug in slugs}


# ---- the registry side ---------------------------------------------------------------------


def ensure_incumbent(db) -> dict:
    """The running policy as the registry's incumbent, registered once from the code default."""
    from ..swarm.orchestrate import DEFAULT_PRIORITY_POLICY

    kind, key = _policy_key()
    current = league.incumbent_payload(db, kind=kind, key=key)
    if current is not None:
        return {"config_id": current["config_id"], "version": current["version"],
                "params": json.loads(current["payload"] or "{}"), "registered": False}
    out = league.register(
        db, kind=kind, key=key, payload=payload_for(DEFAULT_PRIORITY_POLICY),
        why_changed=("incumbent job-priority policy recorded from swarm.orchestrate "
                     "DEFAULT_PRIORITY_POLICY: it runs because it was first, before any replay "
                     "had compared it with anything"),
        tests_declared=("tests/test_swarm.py", "tests/test_cert_improve_wave.py"),
        affected_departments=("runtime",), incumbent=True)
    return {"config_id": out["id"], "version": out["version"],
            "params": dict(DEFAULT_PRIORITY_POLICY), "registered": True}


def _configs(db) -> list[dict]:
    from sqlalchemy import select

    from ..core.models import ConfigVersion

    kind, key = _policy_key()
    with db.session() as s:
        return [{"id": r.id, "version": r.version, "digest": r.digest,
                 "incumbent": r.incumbent, "retired": r.retired_at is not None,
                 "payload": (r.detail or {}).get("payload") or "",
                 "outcome": dict(r.measured_outcome or {})}
                for r in s.scalars(select(ConfigVersion).where(
                    ConfigVersion.kind == kind, ConfigVersion.key == key)
                    .order_by(ConfigVersion.id))]


def neighbours(params: dict) -> list[tuple[dict, str]]:
    """The incumbent's one-step neighbours, each with the reason it is worth trying."""
    out = []
    for name, step in (("deadline_weight", 1.0), ("value_weight", 1.0)):
        for sign in (1, -1):
            lo, hi = BOUNDS[name]
            value = min(hi, max(lo, float(params[name]) + sign * step))
            if value != float(params[name]):
                out.append(({**params, name: value},
                            f"{'raise' if sign > 0 else 'lower'} {name} from "
                            f"{params[name]} to {value}"))
    for factor, word in ((0.5, "halve"), (2.0, "double")):
        lo, hi = BOUNDS["horizon_days"]
        value = min(hi, max(lo, float(params["horizon_days"]) * factor))
        if value != float(params["horizon_days"]):
            out.append(({**params, "horizon_days": value},
                        f"{word} horizon_days from {params['horizon_days']} to {value}"))
    return out


def register_challengers(db, incumbent: dict) -> list[dict]:
    """Register the incumbent's neighbours as challengers, once each, authored by the role."""
    from ..core.models import AuditLog

    kind, key = _policy_key()
    known = {c["digest"] for c in _configs(db)}
    made = []
    for params, why in neighbours(incumbent["params"]):
        payload = payload_for(params)
        if league.digest_of(payload) in known:
            continue
        out = league.register(
            db, kind=kind, key=key, payload=payload,
            why_changed=(f"challenger to v{incumbent['version']}: {why}, to test on the "
                         f"historical job replay whether it meets more deadlines"),
            tests_declared=("improve.replay",), affected_departments=("runtime",),
            incumbent=False)
        with db.session() as s:
            s.add(AuditLog(actor=AUTHOR, action="improve.replay.challenger",
                           artifact=f"{kind}/{key}",
                           detail={"config_id": out["id"], "version": out["version"],
                                   "params": params, "why": why,
                                   "against": incumbent["config_id"]}))
        made.append({"config_id": out["id"], "version": out["version"], "why": why})
    return made


def _open_improvement_for(db, config_id: int) -> dict | None:
    return league.sandbox_owned(db, config_id)


def _monitored(db) -> list[dict]:
    """Promoted replay improvements and the versions they replaced, still being watched."""
    from sqlalchemy import select

    from ..core.models import Improvement

    with db.session() as s:
        return [{"improvement": r.id, **((r.evidence or {}).get("change") or {})}
                for r in s.scalars(select(Improvement).where(Improvement.state == "promoted"))
                if (r.evidence or {}).get("sandbox_trial") == TRIAL]


def _retire(db, config_id: int, verdict: dict, ref: str) -> None:
    from ..core.models import ConfigVersion

    league.record_measured_outcome(db, config_id, evidence_ref=ref, outcome={
        "league_verdict_full": verdict, "role": "challenger", "retired_by": ACTION})
    with db.session() as s:
        row = s.get(ConfigVersion, config_id)
        if row is not None and not row.incumbent and row.retired_at is None:
            row.retired_at = datetime.now(timezone.utc)


def cycle(db, *, now: datetime | None = None) -> dict:
    """Replay the incumbent, its challengers and any watched predecessor; propose a winner."""
    from . import cells

    now = now or datetime.now(timezone.utc)
    kind, key = _policy_key()
    incumbent = ensure_incumbent(db)
    jobs = historical_jobs(db, now=now)
    days = _days(jobs)
    if len(jobs) < MIN_JOBS or len(days) < MIN_DAYS:
        return {"ran": False, "reading": "UNMEASURED", "incumbent": incumbent["config_id"],
                "jobs": len(jobs), "days": len(days),
                "why": (f"{len(jobs)} terminal job(s) over {len(days)} day(s) in the last "
                        f"{WINDOW_DAYS} days; a replay needs at least {MIN_JOBS} jobs over "
                        f"{MIN_DAYS} days, or its holdout is empty and its verdict is noise"),
                "runs": [], "challengers_registered": [], "proposed": [], "retired": []}

    proven = _proven_map(db, jobs)
    dataset = dataset_of(jobs)
    faithful = fidelity(dataset)
    configs = _configs(db)
    open_challengers = [c for c in configs if not c["incumbent"] and not c["retired"]]
    registered = []
    if not open_challengers:
        registered = register_challengers(db, incumbent)
        configs = _configs(db)
        open_challengers = [c for c in configs if not c["incumbent"] and not c["retired"]]

    watched = {int(m["replaces"]) for m in _monitored(db) if m.get("replaces")}
    to_run = [c for c in configs if c["incumbent"] or c in open_challengers
              or c["id"] in watched]
    runs = {}
    for c in to_run:
        params = json.loads(c["payload"] or "{}")
        if not params:
            continue
        result = replay(db, params, jobs, proven=proven)
        # The reference names the configuration, the dataset (its fingerprint), the window
        # and the count: the same tasks replayed tomorrow are the same run, not a new one.
        ref = (f"replay:{c['digest'][:12]}:{dataset['fingerprint'][:12]}:"
               f"{result['window'][0]}..{result['window'][1]}:{result['jobs']}")
        league.record_run(db, c["id"], tasks=result["tasks"], holdout=result["holdout"],
                          cost_cad=0.0, reliability=1.0, run_ref=ref, recorded_by=AUTHOR,
                          dataset=dataset, simulator=SIMULATOR)
        runs[c["id"]] = {"run_ref": ref, **result}

    inc_id = incumbent["config_id"]
    inc_run = runs.get(inc_id)
    proposed, retired, compared, winners = [], [], [], []
    for ch in open_challengers:
        cr = runs.get(ch["id"])
        if cr is None or inc_run is None:
            continue
        ir_result = league.result_of(inc_id, {**inc_run, "cost_cad": 0.0, "reliability": 1.0,
                                              "latency_s": None})
        cr_result = league.result_of(ch["id"], {**cr, "cost_cad": 0.0, "reliability": 1.0,
                                                "latency_s": None})
        verdict = league.compare(ir_result, cr_result,
                                 shared_tasks=tuple(sorted(inc_run["tasks"])))
        compared.append({"config_id": ch["id"], "promote": verdict["promote"],
                         "quality_gain": verdict["quality_gain"],
                         "holdout": verdict["holdout"], "blockers": verdict["blockers"][:2]})
        if not verdict["promote"]:
            _retire(db, ch["id"], verdict, f"replay:{inc_run['run_ref']}|{cr['run_ref']}")
            retired.append({"config_id": ch["id"], "why": verdict["blockers"][:2]})
            continue
        winners.append((cr_result.quality, -ch["id"], ch, cr, cr_result, ir_result))

    # One hypothesis per cycle: the best winner. Two winners promoted one after the other
    # would each be judged against an incumbent the other had already replaced; the others
    # stay open and are compared against whatever is running next cycle. No hypothesis at
    # all when the history was produced by a runtime the simulator does not model (M02): a
    # promotion cannot rest on behaviour the replay did not simulate.
    if winners and not faithful["comparable"]:
        proposed.append({"refused": ("the simulator does not model this history: "
                                     + "; ".join(faithful["reasons"]))[:200],
                         "config_id": winners[0][2]["id"], "fidelity": faithful})
    elif winners and not any(_open_improvement_for(db, c["id"]) for c in open_challengers):
        _q, _neg, ch, cr, cr_result, ir_result = max(winners, key=lambda w: (w[0], w[1]))
        baseline = round(ir_result.quality, 6)
        hypothesis = (f"replacing job-priority policy v{incumbent['version']} with challenger "
                      f"v{ch['version']} should meet more deadlines: on the single-worker "
                      f"replay ({SIMULATOR['version']}) of {inc_run['jobs']} historical jobs "
                      f"it scores {cr_result.quality:.4f} against {baseline:.4f}, and it held "
                      f"on the holdout days")
        try:
            iid = cells.propose(
                db, cell=CELL, hypothesis=hypothesis,
                expected_effect=(f"band-weighted on-time share on the {SIMULATOR['version']} "
                                 f"replay rises above {baseline:.4f} and holds on days "
                                 f"observed after the promotion"),
                rollback_ref=f"config:{inc_id}", touches=("priority",),
                proposed_by=AUTHOR, trial=TRIAL,
                trial_metric=f"replay_on_time:{key}", higher_is_better=True,
                baseline=baseline, baseline_ref=f"run:{inc_run['run_ref']}"[:80],
                change={"config_id": ch["id"], "kind": kind, "key": key, "replaces": inc_id,
                        "simulator": SIMULATOR["version"],
                        "judged_on": {"fingerprint": dataset["fingerprint"],
                                      "bounds": dataset["bounds"]},
                        "fidelity": faithful})
            proposed.append({"improvement": iid, "config_id": ch["id"],
                             "baseline": baseline,
                             "challenger_quality": round(cr_result.quality, 6)})
            with db.session() as s:
                from ..core.models import Improvement

                row = s.get(Improvement, iid)
                row.evidence = {**(row.evidence or {}), "expected_gain": round(
                    cr_result.quality - baseline, 6)}
        except Exception as exc:  # noqa: BLE001 - a refused proposal is reported
            proposed.append({"refused": str(exc)[:200], "config_id": ch["id"]})

    return {"ran": True, "reading": "measured", "incumbent": inc_id, "jobs": len(jobs),
            "days": len(days), "challengers_registered": registered,
            "runs": [{"config_id": k, "run_ref": v["run_ref"],
                      "shared_days": len(v["tasks"]), "holdout_days": len(v["holdout"])}
                     for k, v in runs.items()],
            "compared": compared, "proposed": proposed, "retired": retired,
            "watched": sorted(watched), "dataset": dataset, "fidelity": faithful,
            "simulator": SIMULATOR["version"]}


# ---- the sandbox side: trial, execution, monitor --------------------------------------------


def _dataset_key(run: dict) -> str:
    """What identifies the tasks a run was scored on: its dataset fingerprint when it has
    one, otherwise the window in its reference (runs recorded before fingerprints existed)."""
    fp = (run.get("dataset") or {}).get("fingerprint")
    return f"fp:{fp}" if fp else run["run_ref"].split(":", 2)[-1]


def _simulator_version(run: dict) -> str | None:
    return (run.get("simulator") or {}).get("version")


def _latest_pair(db, incumbent_id: int, challenger_id: int, *, after: datetime | None = None):
    """The newest recorded runs of both configurations on the same dataset and simulator.

    Paired by dataset identity, and only when both were produced under the same simulator
    version: a run of a changed simulator against one of the old is two different games.
    """
    runs = league._runs(db)
    mine = {_dataset_key(r): r for r in runs.get(challenger_id, [])
            if after is None or r["at"] > after}
    theirs = {_dataset_key(r): r for r in runs.get(incumbent_id, [])
              if after is None or r["at"] > after}
    common = sorted((k for k in set(mine) & set(theirs)
                     if _simulator_version(mine[k]) == _simulator_version(theirs[k])),
                    key=lambda w: (mine[w]["at"], mine[w]["run_id"]))
    if not common:
        return None
    w = common[-1]
    return theirs[w], mine[w]


def _post_promotion_tasks(run: dict, promoted_at: datetime) -> dict:
    """The tasks of a run that were wholly observed after the promotion.

    A replay task is a day; a day that ends after the promotion but began before it mixes
    outcomes the promoted policy could and could not have affected, so only days strictly
    after the promotion day count. Tasks that are not dated (runs recorded by hand or by an
    older producer) are all kept, with the dataset bounds having already shown the run holds
    post-promotion observations.
    """
    tasks = dict(run.get("tasks") or {})
    dated = {}
    undated = {}
    for name, score in tasks.items():
        try:
            day = datetime.fromisoformat(str(name).split(":", 1)[1]).date()
        except (IndexError, ValueError):
            undated[name] = score
            continue
        if day > promoted_at.date():
            dated[name] = score
    return dated if (dated or not undated) else undated


def freshness(new: dict, *, promoted_at: datetime, judged: set[str]) -> dict:
    """Whether a run recorded after a promotion is *evidence about* the promotion (M03).

    Three things have to hold, and a timestamp later than the promotion is none of them: the
    run says what it was scored on (a dataset fingerprint and observation bounds); that
    dataset is not one the promotion was already judged on; and the observations extend past
    the promotion. A reused holdout, or the same history replayed tomorrow, is a repeated
    evaluation and is reported as one.
    """
    dataset = dict(new.get("dataset") or {})
    fp, bounds = dataset.get("fingerprint"), list(dataset.get("bounds") or [])
    if not fp or len(bounds) != 2:
        return {"fresh": False, "kind": "unbounded",
                "why": ("the run carries no dataset fingerprint or observation bounds, so it "
                        "cannot be shown to contain anything observed after the promotion")}
    if fp in judged:
        return {"fresh": False, "kind": "repeated_evaluation",
                "why": (f"dataset {fp[:12]} is the history the promotion was judged on; "
                        f"replaying it again is the same evaluation, not new evidence")}
    latest = _aware(datetime.fromisoformat(bounds[1]))
    if latest is None or latest <= promoted_at:
        return {"fresh": False, "kind": "predates_promotion",
                "why": (f"every observation in dataset {fp[:12]} predates the promotion "
                        f"({bounds[1]} against {promoted_at.isoformat()})")}
    return {"fresh": True, "kind": "post_promotion", "fingerprint": fp, "bounds": bounds}


def trial(db, improvement_id: int) -> dict:
    """The sandbox trial: the challenger and the incumbent on the same recorded replay window."""
    from ..core.models import Improvement

    with db.session() as s:
        row = s.get(Improvement, improvement_id)
        change = dict((row.evidence or {}).get("change") or {})
    if not change.get("config_id") or not change.get("replaces"):
        return {"ran": False, "trial": TRIAL, "why": "the proposal names no configuration"}
    pair = _latest_pair(db, int(change["replaces"]), int(change["config_id"]))
    if pair is None:
        return {"ran": False, "trial": TRIAL,
                "why": "no replay window on which both versions have a recorded run"}
    inc, ch = pair
    verdict = league.compare(league.result_of(int(change["replaces"]), inc),
                             league.result_of(int(change["config_id"]), ch),
                             shared_tasks=tuple(sorted(inc["tasks"])))
    value = round(league.result_of(int(change["config_id"]), ch).quality, 6)
    return {"ran": True, "trial": TRIAL, "value": value,
            "run_ref": f"{inc['run_ref']}|{ch['run_ref']}"[:190],
            "reads": {"incumbent_run": inc["run_id"], "challenger_run": ch["run_id"]},
            "blockers": [] if verdict["promote"] else verdict["blockers"],
            "why": (f"challenger reads {value} on the replay window {ch['run_ref']}; the "
                    f"league verdict is {verdict['reason']}")}


def execute(db, improvement_id: int) -> dict:
    """Make the promoted challenger the running policy: what `priority_for` reads next."""
    from ..core.models import Improvement
    from ..swarm.orchestrate import clear_policy_cache

    with db.session() as s:
        row = s.get(Improvement, improvement_id)
        change = dict((row.evidence or {}).get("change") or {})
    out = league.promote(db, int(change["config_id"]), evidence_ref=f"improvement:{improvement_id}",
                         outcome={"promoted_by": "improve.sandbox",
                                  "improvement": improvement_id,
                                  "previous_incumbent": change.get("replaces"),
                                  "promoted_at": datetime.now(timezone.utc).isoformat()})
    clear_policy_cache()
    return {"executed": "registry incumbent", **out}


def monitor(db, improvement_id: int) -> dict:
    """The promoted policy against the one it replaced, on a window replayed since promotion."""
    from ..core.models import Improvement

    with db.session() as s:
        row = s.get(Improvement, improvement_id)
        change = dict((row.evidence or {}).get("change") or {})
        promoted_at = _aware(row.promoted_at)
        seen = (row.evidence or {}).get("monitored_windows") or []
    challenger_id, replaced_id = int(change["config_id"]), int(change["replaces"])
    pair = _latest_pair(db, replaced_id, challenger_id, after=promoted_at)
    if pair is None:
        return {"judged": False, "why": "no replay window recorded since the promotion"}
    old, new = pair
    if new["run_ref"] in seen:
        return {"judged": False, "why": "already judged against this window"}
    # What the promotion was judged on: the dataset the proposal named and every dataset the
    # challenger had been scored on before it was promoted.
    judged = {fp for fp in ((change.get("judged_on") or {}).get("fingerprint"),) if fp}
    judged |= {(r.get("dataset") or {}).get("fingerprint")
               for r in league._runs(db).get(challenger_id, []) if r["at"] <= promoted_at}
    judged.discard(None)
    fresh = freshness(new, promoted_at=promoted_at, judged=judged)
    if not fresh["fresh"]:
        # Remembered so the same non-evidence is not re-examined nightly; never a verdict.
        with db.session() as s:
            row = s.get(Improvement, improvement_id)
            row.evidence = {**(row.evidence or {}),
                            "monitored_windows": list(seen) + [new["run_ref"]],
                            "not_fresh": {"run_ref": new["run_ref"], **fresh}}
        return {"judged": False, "fresh": False, "kind": fresh["kind"], "why": fresh["why"]}
    new_tasks = _post_promotion_tasks(new, promoted_at)
    old_tasks = _post_promotion_tasks(old, promoted_at)
    common = sorted(set(new_tasks) & set(old_tasks))
    if not common:
        return {"judged": False, "fresh": True, "kind": "no_whole_day_yet",
                "why": (f"dataset {fresh['fingerprint'][:12]} reaches past the promotion but "
                        f"no whole day has been observed since it; judged when one has")}
    old_q = round(sum(old_tasks[t] for t in common) / len(common), 6)
    new_q = round(sum(new_tasks[t] for t in common) / len(common), 6)
    with db.session() as s:
        row = s.get(Improvement, improvement_id)
        row.evidence = {**(row.evidence or {}),
                        "monitored_windows": list(seen) + [new["run_ref"]],
                        "monitoring": {"observed": new_q, "replaced_reads": old_q,
                                       "window": new["run_ref"], "tasks": common,
                                       "dataset": fresh["fingerprint"],
                                       "bounds": fresh["bounds"],
                                       "simulator": _simulator_version(new)}}
    margin = league.required_margin(len(common))
    worse = new_q < old_q - margin
    return {"judged": True, "observed": new_q, "replaced_reads": old_q, "worse": worse,
            "fresh": True, "tasks": len(common),
            "why": (f"on {len(common)} post-promotion task(s) of dataset "
                    f"{fresh['fingerprint'][:12]} the promoted policy reads {new_q:.4f} and "
                    f"the version it replaced {old_q:.4f}"
                    + (f", worse by more than the {margin:.4f} margin" if worse else ""))}


def rollback(db, improvement_id: int, *, why: str) -> dict:
    from ..core.models import Improvement
    from ..swarm.orchestrate import clear_policy_cache

    kind, key = _policy_key()
    with db.session() as s:
        row = s.get(Improvement, improvement_id)
        change = dict((row.evidence or {}).get("change") or {})
    out = league.rollback(db, kind=kind, key=key, to_config_id=int(change["replaces"]),
                          why=why)
    clear_policy_cache()
    return out


def rollback_verified(db, improvement_id: int) -> dict:
    """Is the version this promotion replaced the *active* policy again? Read, not assumed.

    Two readings have to agree before a rollback counts as done (C-81): the registry names
    the replaced version as the incumbent and the promoted challenger as not, and
    `swarm.orchestrate.priority_policy` -- what the next enqueue actually reads -- resolves
    to that same version. A rollback that flipped a flag the runtime does not read has not
    rolled anything back.
    """
    from ..core.models import ConfigVersion, Improvement
    from ..swarm.orchestrate import clear_policy_cache, priority_policy

    with db.session() as s:
        row = s.get(Improvement, improvement_id)
        change = dict((row.evidence or {}).get("change") or {}) if row is not None else {}
        replaces = int(change.get("replaces") or 0)
        promoted = int(change.get("config_id") or 0)
        target = s.get(ConfigVersion, replaces) if replaces else None
        challenger = s.get(ConfigVersion, promoted) if promoted else None
        registry_ok = (target is not None and target.incumbent is True
                       and (challenger is None or challenger.incumbent is False))
    clear_policy_cache()
    active = priority_policy(db)
    active_ok = active.get("config_id") == replaces
    verified = bool(replaces) and registry_ok and active_ok
    return {"verified": verified, "check": "league_replay.rollback",
            "registry_incumbent_is_replaced": registry_ok,
            "active_config_id": active.get("config_id"), "expected_config_id": replaces,
            "why": ("the replaced version is the registry incumbent and the policy the "
                    "runtime reads" if verified else
                    f"registry restored: {registry_ok}; active policy reads config "
                    f"{active.get('config_id')} where {replaces} is expected")}


def state() -> dict:
    kind, key = _policy_key()
    return {"action": ACTION, "policy": f"{kind}/{key}", "author": AUTHOR,
            "tasks": "historical terminal jobs, one task per day; newest fifth held out",
            "metric": "band-weighted share of jobs finishing before their deadline or SLA",
            "band_sla_hours": dict(BAND_SLA_HOURS), "min_jobs": MIN_JOBS,
            "min_days": MIN_DAYS, "simulator": dict(SIMULATOR),
            # Codex M09: the honest extent of the challenger engine. Model, prompt and tool
            # challengers are registered and compared on recorded runs; nothing produces
            # those runs here, and no other configuration is replayed.
            "scope": ("the only configuration this engine produces runs for and proposes "
                      "changes to is the job-priority policy; every other configuration's "
                      "challenger waits for a run recorded elsewhere"),
            "freshness": ("a post-promotion run is evidence only when its dataset fingerprint "
                          "is new, its observation bounds pass the promotion and a whole day "
                          "has been observed since")}
