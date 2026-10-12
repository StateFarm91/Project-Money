"""F-895 Overnight Autonomy: grade one unattended night, read straight after a deploy.

The board row's remaining step is "deploy, then read one unattended night's useful work per
department from ops/slo department useful-work". This module is that read, prepared before the
deploy so the night is graded the morning after rather than argued about.

Two modes, and they are not equal:

* ``grade_db(db, start, end)`` -- **the proof**. Reads durable rows (jobs, audit_log, incidents,
  cost_entries) through the same helpers `ops.slo` uses: the department map
  (`slo.department_of`), the one useful-work judge (`runtime.pipeline.did_no_work`), the
  schedule (`runtime.worker.CADENCES`) and the self-observing exclusions. Run it where the
  production database is reachable read-only (Railway shell), or against a restored export.
* ``grade_public(fetch, base, start, end)`` -- **a pre-check** from public GET endpoints only
  (`/api/status`, `/api/audit`, `/api/swarm/runtime`). Public audit rows carry no job outputs,
  so it can count completions per department but cannot judge usefulness: its verdict is never
  better than INCOMPLETE. It exists so anyone can see, without database access, whether the
  night is worth grading.

Criteria (each names its source; a criterion with no data is UNKNOWN and the verdict is then
INCOMPLETE, never PASS):

1. the window has ended and lasted at least ``MIN_HOURS`` (a night, not a lunch break);
2. unattended: no audit row by an interactive actor (owner, operator, development sessions);
3. the scheduler kept scheduling: a cadence job was created in every hour of the window;
4. the deploy under test ran the whole night: the build commit is the one named, when named;
5. per department expected to work (it owns a non-self-observing cadence): at least one job
   finished in the window that did useful work by the judge;
6. at least ``MIN_DEPARTMENTS`` departments did useful work (the soak's independence bar);
7. no P0/P1 incident opened in the window.

Verdict: FAIL if any criterion fails; INCOMPLETE if any is UNKNOWN; otherwise PASS. Per-department
rows are reported whatever the verdict, including departments that ran but produced nothing --
the commonest overnight failure, and the one a completion count hides.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

MIN_HOURS = 6
MIN_DEPARTMENTS = 3
PASS, FAIL, UNKNOWN, INCOMPLETE = "PASS", "FAIL", "UNKNOWN", "INCOMPLETE"


def _aware(v):
    if v is None:
        return None
    if isinstance(v, str):
        v = datetime.fromisoformat(v.replace("Z", "+00:00"))
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def _crit(name: str, ok, evidence: dict, source: str) -> dict:
    return {"criterion": name, "result": UNKNOWN if ok is None else PASS if ok else FAIL,
            "evidence": evidence, "source": source}


def _verdict(criteria: list[dict]) -> str:
    if any(c["result"] == FAIL for c in criteria):
        return FAIL
    if any(c["result"] == UNKNOWN for c in criteria):
        return INCOMPLETE
    return PASS


def _window(start, end, now: datetime | None = None) -> tuple[datetime, datetime, float]:
    start, end = _aware(start), _aware(end)
    now = now or datetime.now(timezone.utc)
    if end is None or start is None or end <= start:
        raise ValueError("a window needs a start before its end")
    if end > now + timedelta(seconds=5):
        raise ValueError("a night cannot be graded before it has ended")
    return start, end, (end - start).total_seconds() / 3600


def expected_departments() -> dict[str, list[str]]:
    """Department -> the cadenced job types that make it expected to work overnight."""
    from . import slo

    selfobs = slo._self_observing()
    out: dict[str, list[str]] = {}
    for _name, _agent, job_type, _period in slo._cadences():
        dept = slo.department_of(job_type)
        if dept is None or job_type in selfobs:
            continue
        out.setdefault(dept, [])
        if job_type not in out[dept]:
            out[dept].append(job_type)
    return out


def _interactive(actor: str | None) -> bool:
    from .slo import INTERACTIVE_ACTORS

    a = (actor or "").lower()
    return any(a.startswith(p) for p in INTERACTIVE_ACTORS)


# ---- the proof: durable rows ---------------------------------------------------------------

def grade_db(db, *, start, end, commit: str = "", now: datetime | None = None) -> dict:
    from sqlalchemy import select

    from ..core.models import AuditLog, Incident, Job, JobStatus
    from . import slo

    start, end, hours = _window(start, end, now)
    judge, judge_src = slo._did_no_work()
    expected = expected_departments()
    selfobs = slo._self_observing()
    with db.session() as s:
        done = list(s.execute(select(Job.id, Job.job_type, Job.outputs, Job.finished_at)
                              .where(Job.status == JobStatus.DONE, Job.finished_at >= start,
                                     Job.finished_at <= end)).all())
        dead = list(s.execute(select(Job.job_type).where(
            Job.status == JobStatus.DEAD, Job.finished_at >= start,
            Job.finished_at <= end)).all())
        actors = [a for (a,) in s.execute(select(AuditLog.actor).where(
            AuditLog.at >= start, AuditLog.at <= end)).all()]
        cadence_hours = {int((t - start).total_seconds() // 3600)
                         for t in slo._cadence_job_stamps(s, start, end)}
        p1 = [i.signature for i in s.scalars(select(Incident).where(
            Incident.severity.in_(["P0", "P1"]), Incident.at >= start, Incident.at <= end))]
    rows: dict[str, dict] = {d: {"department": d, "expected_job_types": jts, "completed": 0,
                                 "useful": 0, "no_work": 0, "dead": 0, "example": None}
                             for d, jts in sorted(expected.items())}
    for jid, jt, outputs, finished in done:
        dept = slo.department_of(jt)
        if dept not in rows or jt in selfobs:
            continue
        r = rows[dept]
        r["completed"] += 1
        try:
            empty = judge(outputs or {}, jt)
        except Exception:  # noqa: BLE001 - unjudgeable is not useful
            empty = True
        if empty:
            r["no_work"] += 1
        else:
            r["useful"] += 1
            if r["example"] is None:
                r["example"] = {"job": f"jobs:{jid}", "job_type": jt,
                                "finished_at": _aware(finished).isoformat()}
    for (jt,) in dead:
        dept = slo.department_of(jt)
        if dept in rows:
            rows[dept]["dead"] += 1
    for r in rows.values():
        r["result"] = (PASS if r["useful"] else
                       FAIL if r["completed"] else UNKNOWN if not done else FAIL)
        r["why"] = ("useful work recorded" if r["useful"] else
                    "ran but every finished job did no work" if r["completed"] else
                    "nothing finished in the window")
    return _assemble(mode="db", start=start, end=end, hours=hours, rows=list(rows.values()),
                     interactive=[a for a in actors if _interactive(a)],
                     actors_known=True, cadence_hours=cadence_hours, p1=p1,
                     commit_expected=commit, commit_seen=_db_commit(),
                     judge=judge_src, usefulness_measured=True)


def _db_commit() -> str | None:
    try:
        from ..core import build

        ident = build.identity()
        return str(ident["commit"]) if ident["known"] else None
    except Exception:  # noqa: BLE001
        return None


# ---- the pre-check: public GETs ------------------------------------------------------------

def _get(fetch, base: str, path: str):
    status, body = fetch(base.rstrip("/") + path)
    if not (200 <= int(status) < 300):
        raise RuntimeError(f"GET {path} -> HTTP {status}")
    return json.loads(body)


def grade_public(fetch, base: str, *, start, end, commit: str = "",
                 now: datetime | None = None) -> dict:
    """`fetch(url) -> (status, bytes)`. Read-only GETs; never authenticates, never writes."""
    from . import slo

    start, end, hours = _window(start, end, now)
    expected = expected_departments()
    status = _get(fetch, base, "/api/status")
    seen_commit = ((status.get("build") or {}).get("commit")
                   if (status.get("build") or {}).get("known") else None)
    rows = []
    covered_all = True
    for dept, jts in sorted(expected.items()):
        completed, truncated = 0, False
        for jt in jts:
            got = _get(fetch, base, f"/api/audit?action=job.completed:{jt}&limit=1000")["audit"]
            for a in got:
                at = _aware(a["at"])
                if start <= at <= end:
                    completed += 1
            if len(got) >= 1000:
                oldest = min(_aware(a["at"]) for a in got)
                if oldest > start:
                    truncated = True
        covered_all = covered_all and not truncated
        rows.append({"department": dept, "expected_job_types": jts,
                     "completed": completed if not truncated else None, "useful": None,
                     "result": UNKNOWN,
                     "why": ("public audit rows carry no job outputs, so usefulness cannot be "
                             "judged here; run grade_db for the proof"
                             + ("; completions truncated by the 1000-row page"
                                if truncated else ""))})
    recent = _get(fetch, base, "/api/audit?limit=1000")["audit"]
    in_window = [a for a in recent if start <= _aware(a["at"]) <= end]
    actors_known = bool(recent) and min(_aware(a["at"]) for a in recent) <= start
    try:
        quality = _get(fetch, base, "/api/swarm/runtime").get("agent_quality") or {}
    except Exception:  # noqa: BLE001
        quality = {}
    out = _assemble(mode="public", start=start, end=end, hours=hours, rows=rows,
                    interactive=[a["actor"] for a in in_window if _interactive(a["actor"])],
                    actors_known=actors_known, cadence_hours=None, p1=None,
                    commit_expected=commit, commit_seen=seen_commit,
                    judge="none: public mode cannot judge usefulness",
                    usefulness_measured=False)
    out["agent_function_quality"] = {
        k: (v.get("function_quality") or {}).get("value")
        for k, v in (quality.get("agents") or {}).items()} if quality else None
    out["note"] = ("pre-check only: completions per department are counted from public audit "
                   "rows; usefulness and incidents need grade_db, so this verdict is at best "
                   "INCOMPLETE by construction")
    return out


# ---- shared --------------------------------------------------------------------------------

def _assemble(*, mode, start, end, hours, rows, interactive, actors_known, cadence_hours, p1,
              commit_expected, commit_seen, judge, usefulness_measured) -> dict:
    expected_hours = max(1, int(hours))
    useful = [r["department"] for r in rows if r.get("result") == PASS]
    criteria = [
        _crit(f"window ended and lasted at least {MIN_HOURS}h", hours >= MIN_HOURS,
              {"hours": round(hours, 2)}, "clock"),
        _crit("unattended: no interactive actor in the audit log",
              (not interactive) if actors_known else None,
              {"interactive_rows": len(interactive), "actors": sorted(set(interactive))[:10]},
              "audit_log.actor"),
        _crit("scheduler kept scheduling (a cadence job created every hour)",
              None if cadence_hours is None else len(cadence_hours) >= expected_hours,
              {"hours_with_cadence": None if cadence_hours is None else len(cadence_hours),
               "hours": expected_hours}, "jobs(idempotency_key LIKE 'cadence:%')"),
        *([_crit("the named build ran the night",
                 None if commit_seen is None else
                 commit_seen.lower().startswith(commit_expected.lower()),
                 {"expected": commit_expected, "seen": commit_seen},
                 "core.build.identity / api/status")] if commit_expected else []),
        *[_crit(f"department {r['department']} did useful work", (
            None if not usefulness_measured or r["result"] == UNKNOWN else
            r["result"] == PASS), {k: r.get(k) for k in ("completed", "useful", "no_work",
                                                         "dead", "example", "why")},
            "jobs.outputs judged by " + judge) for r in rows],
        _crit(f"at least {MIN_DEPARTMENTS} departments did useful work",
              len(useful) >= MIN_DEPARTMENTS if usefulness_measured else None,
              {"departments": useful}, "jobs.outputs"),
        _crit("no P0/P1 incident opened", None if p1 is None else not p1,
              {"p0_p1": (p1 or [])[:10]}, "incidents"),
    ]
    return {"requirement": "F-895", "mode": mode, "verdict": _verdict(criteria),
            "start": start.isoformat(), "end": end.isoformat(), "hours": round(hours, 2),
            "departments": rows, "criteria": criteria,
            "basis": ("measured from durable rows" if mode == "db" else
                      "public read-only endpoints; usefulness UNKNOWN")}


def to_markdown(report: dict) -> str:
    lines = [f"# F-895 overnight grade ({report['mode']}): **{report['verdict']}**",
             f"Window {report['start']} → {report['end']} ({report['hours']} h). "
             f"Basis: {report['basis']}.", "",
             "| Department | Completed | Useful | Result | Why |", "|---|---|---|---|---|"]
    for r in report["departments"]:
        fmt = (lambda v: "Unknown" if v is None else str(v))
        lines.append(f"| {r['department']} | {fmt(r.get('completed'))} | "
                     f"{fmt(r.get('useful'))} | {r['result']} | {r['why']} |")
    lines += ["", "| Criterion | Result | Source |", "|---|---|---|"]
    lines += [f"| {c['criterion']} | {c['result']} | {c['source']} |"
              for c in report["criteria"]]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - CLI glue
    import argparse
    import urllib.request

    p = argparse.ArgumentParser(description="F-895: grade one unattended night")
    p.add_argument("--start", required=True, help="ISO 8601 UTC")
    p.add_argument("--end", required=True, help="ISO 8601 UTC")
    p.add_argument("--commit", default="", help="build that must have run the night")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--db", help="database URL (read-only use) for the proof")
    g.add_argument("--public", help="base URL for the public pre-check")
    p.add_argument("--markdown", action="store_true")
    a = p.parse_args(argv)
    if a.db:
        from ..core.db import Database

        rep = grade_db(Database(a.db), start=a.start, end=a.end, commit=a.commit)
    else:
        def fetch(url):
            with urllib.request.urlopen(url, timeout=30) as r:  # noqa: S310 - GET only
                return r.status, r.read()
        rep = grade_public(fetch, a.public, start=a.start, end=a.end, commit=a.commit)
    print(to_markdown(rep) if a.markdown else json.dumps(rep, indent=1, default=str))
    return 0 if rep["verdict"] == PASS else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
