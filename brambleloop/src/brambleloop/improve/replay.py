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
            service = ((finished - started).total_seconds()
                       if started is not None and finished is not None else 1.0)
            out.append({"id": j.id, "job_type": j.job_type, "inputs": dict(j.inputs or {}),
                        "created": created, "service_s": max(1.0, service)})
    return out


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
        if clock <= job["deadline"]:
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
        tests_run=("tests/test_swarm.py", "tests/test_cert_improve_wave.py"),
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
            tests_run=("improve.replay",), affected_departments=("runtime",),
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
        ref = (f"replay:{c['digest'][:12]}:{result['window'][0]}..{result['window'][1]}:"
               f"{result['jobs']}")
        league.record_run(db, c["id"], tasks=result["tasks"], holdout=result["holdout"],
                          cost_cad=0.0, reliability=1.0, run_ref=ref, recorded_by=AUTHOR)
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
    # stay open and are compared against whatever is running next cycle.
    if winners and not any(_open_improvement_for(db, c["id"]) for c in open_challengers):
        _q, _neg, ch, cr, cr_result, ir_result = max(winners, key=lambda w: (w[0], w[1]))
        baseline = round(ir_result.quality, 6)
        hypothesis = (f"replacing job-priority policy v{incumbent['version']} with challenger "
                      f"v{ch['version']} should meet more deadlines: on the replay of "
                      f"{inc_run['jobs']} historical jobs it scores {cr_result.quality:.4f} "
                      f"against {baseline:.4f}, and it held on the holdout days")
        try:
            iid = cells.propose(
                db, cell=CELL, hypothesis=hypothesis,
                expected_effect=(f"band-weighted on-time share on the replay rises above "
                                 f"{baseline:.4f} and holds on fresh days"),
                rollback_ref=f"config:{inc_id}", touches=("priority",),
                proposed_by=AUTHOR, trial=TRIAL,
                trial_metric=f"replay_on_time:{key}", higher_is_better=True,
                baseline=baseline, baseline_ref=f"run:{inc_run['run_ref']}"[:80],
                change={"config_id": ch["id"], "kind": kind, "key": key, "replaces": inc_id})
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
            "watched": sorted(watched)}


# ---- the sandbox side: trial, execution, monitor --------------------------------------------


def _latest_pair(db, incumbent_id: int, challenger_id: int, *, after: datetime | None = None):
    """The newest recorded runs of both configurations on the same replay window."""
    runs = league._runs(db)
    mine = {r["run_ref"].split(":", 2)[-1]: r for r in runs.get(challenger_id, [])
            if after is None or r["at"] > after}
    theirs = {r["run_ref"].split(":", 2)[-1]: r for r in runs.get(incumbent_id, [])
              if after is None or r["at"] > after}
    common = sorted(set(mine) & set(theirs), key=lambda w: (mine[w]["at"], mine[w]["run_id"]))
    if not common:
        return None
    w = common[-1]
    return theirs[w], mine[w]


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
    pair = _latest_pair(db, int(change["replaces"]), int(change["config_id"]),
                        after=promoted_at)
    if pair is None:
        return {"judged": False, "why": "no replay window recorded since the promotion"}
    old, new = pair
    if new["run_ref"] in seen:
        return {"judged": False, "why": "already judged against this window"}
    old_q = league.result_of(int(change["replaces"]), old).quality
    new_q = league.result_of(int(change["config_id"]), new).quality
    with db.session() as s:
        row = s.get(Improvement, improvement_id)
        row.evidence = {**(row.evidence or {}),
                        "monitored_windows": list(seen) + [new["run_ref"]],
                        "monitoring": {"observed": round(new_q, 6),
                                       "replaced_reads": round(old_q, 6),
                                       "window": new["run_ref"]}}
    margin = league.required_margin(len(new["tasks"]))
    worse = new_q < old_q - margin
    return {"judged": True, "observed": round(new_q, 6), "replaced_reads": round(old_q, 6),
            "worse": worse,
            "why": (f"on fresh window {new['run_ref']} the promoted policy reads {new_q:.4f} "
                    f"and the version it replaced {old_q:.4f}"
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


def state() -> dict:
    kind, key = _policy_key()
    return {"action": ACTION, "policy": f"{kind}/{key}", "author": AUTHOR,
            "tasks": "historical terminal jobs, one task per day; newest fifth held out",
            "metric": "band-weighted share of jobs finishing before their deadline or SLA",
            "band_sla_hours": dict(BAND_SLA_HOURS), "min_jobs": MIN_JOBS,
            "min_days": MIN_DAYS}
