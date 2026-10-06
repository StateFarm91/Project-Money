"""The autonomy map, generated from the code that is actually wired (directive §3).

Not a hand-written table: every link is read from the live roots the runtime boots --
`runtime.worker.CADENCES` (what the scheduler enqueues), `runtime.worker.handlers` after
`runtime.pipeline` is imported (what a worker can execute), `agents.registry.DEFAULT_AGENTS`
and `FORBIDDEN_COMBINATIONS` (what each agent may run), the follow-on `enqueue(...)` calls in
handler source (parsed with `ast`, literal job types only), and this package's charters and
generators. A link the code does not wire is reported as broken; a docstring that claims it is
not evidence.

    python -m brambleloop.autonomy.map --write <path.json>
"""
from __future__ import annotations

import ast
import inspect
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Findings from the read-only audit made before this lane changed anything (2026-10-06, base
# 0694fb7). Each is re-checked by `broken_links()` where it is mechanically checkable; this
# list keeps the ones that were repaired so the record of what was broken is not lost.
AUDIT_FINDINGS: list[dict] = [
    {"id": "AM-01", "severity": "critical", "departments": "all",
     "link": "work-generation",
     "finding": "Idle work generation was company-wide only: swarm.orchestrate.feed_idle "
                "feeds the standing backlog only when NO non-swarm job is open anywhere. With "
                "103 cadences the queue is almost never empty, so an individual department "
                "with nothing to do was never given work.",
     "status": "REPAIRED", "repair": "autonomy.orchestrator.tick: per-department idle "
                                     "detection and evidence-driven generation every 15 min"},
    {"id": "AM-02", "severity": "high", "departments": "product_design, product_truth, "
     "visual, store_commerce, support, finance, growth",
     "link": "work-generation",
     "finding": "The standing backlog (BACKLOG_JOBS) names work for only intelligence, "
                "platform/executive and learn; seven departments had no idle work generator "
                "at all.",
     "status": "REPAIRED", "repair": "charters.generatable + generators for all eleven"},
    {"id": "AM-03", "severity": "high", "departments": "all", "link": "mission-creation",
     "finding": "No mission record: a cadence job carries only {'cadence': name}; why work "
                "was created and from which evidence was not persisted anywhere queryable.",
     "status": "REPAIRED", "repair": "company_memory kind=mission with evidence sources"},
    {"id": "AM-04", "severity": "high", "departments": "all", "link": "learning-signal",
     "finding": "No department-level KPIs with anti-gaming guardrails (F-918). "
                "agent_quality reads per-agent job success, which a no-op run satisfies.",
     "status": "REPAIRED", "repair": "autonomy.kpis (VOID on guardrail, no-op counts zero, "
                                     "duplicate outputs count once)"},
    {"id": "AM-05", "severity": "high", "departments": "all", "link": "durable-memory",
     "finding": "No persistent company memory or company timeline tables (F-920, F-927); "
                "the audit_log is append-only machine chatter with no department, mission "
                "or outcome linkage.",
     "status": "REPAIRED", "repair": "company_memory + company_timeline (keyed, idempotent)"},
    {"id": "AM-06", "severity": "high", "departments": "executive", "link": "morning-handoff",
     "finding": "Nothing produced a morning handoff (F-896) inside the runtime; the overnight "
                "summary existed only as a development-session habit.",
     "status": "REPAIRED", "repair": "autonomy.morning_handoff (generated daily by the "
                                     "orchestrator after 11:00 UTC)"},
    {"id": "AM-07", "severity": "high", "departments": "platform", "link": "recovery-fencing",
     "finding": "The queue fenced stale completions by worker NAME only. The embedded runner "
                "named itself web-<pid>; containers in an overlapping deploy can share a PID, "
                "so a reclaimed job's original attempt could complete over its successor.",
     "status": "REPAIRED", "repair": "jobs.lease_token per claim (ported from Codex 8877f05), "
                                     "checked on complete/fail/heartbeat"},
    {"id": "AM-08", "severity": "medium", "departments": "all", "link": "wake",
     "finding": "An empty queue waited for the next cadence window (up to 15 min for the "
                "fastest, hours for most departments) instead of waking the company.",
     "status": "REPAIRED", "repair": "Scheduler.tick -> orchestrator.idle_wake"},
    {"id": "AM-09", "severity": "medium", "departments": "learn", "link": "improvement-path",
     "finding": "Department outcomes did not feed Learn except through failures: a "
                "department whose useful output stopped produced no lesson.",
     "status": "REPAIRED", "repair": "department_review routes Lesson rows on regression or "
                                     "guardrail breach; Learn's generator consumes lessons"},
    {"id": "AM-10", "severity": "medium", "departments": "product_truth",
     "link": "execution",
     "finding": "Registry permissions with no handler: gate.quality, gate.policy, "
                "gate.asset_truth, cir.twin, cir.reverse (and cir.revise, assets.render, "
                "content.draft, store.update, pricing.experiment, "
                "radar.competitor_snapshot). Agents asset_truth and policy hold only "
                "unhandled job types, so they can never run anything.",
     "status": "OPEN", "repair": "outside lane A's files (gates/, cir/ handlers); reported"},
    {"id": "AM-11", "severity": "info", "departments": "support",
     "link": "evidence-inputs",
     "finding": "Customer Support is woken hourly but the customers gate is closed; its "
                "honest state is idle-with-no-cases. KPIs read UNKNOWN, never 0.",
     "status": "BY DESIGN", "repair": ""},
    {"id": "AM-12", "severity": "high", "departments": "all", "link": "no-dev-dependency",
     "finding": "Historical autonomy also depended on the Claude heartbeat routine "
                "(ops/HEARTBEAT_PROMPT.md) and an owner-PC Windows watchdog. Nothing in the "
                "hosted runtime imports or requires either; the embedded runner + scheduler "
                "+ orchestrator now carry the loop.",
     "status": "REPAIRED (runtime side)",
     "repair": "verified by test_v11_autonomy_overnight: no session, no PC, work generated"},
    {"id": "AM-13", "severity": "medium", "departments": "executive, platform",
     "link": "starvation",
     "finding": "With one active pool worker, a CPU-bound render or planning cycle held the "
                "only claimer and the orchestrator / liveness checks waited behind it.",
     "status": "REPAIRED", "repair": "runtime.lanes control lane (ported/adapted from Codex "
                                     "8877f05), started by app.runner beside the pool"},
    {"id": "AM-14", "severity": "info", "departments": "visual", "link": "wake",
     "finding": "creative.model_freeze, creative.photoreal_calibration, visual.portrait_repair "
                "and visual.provider_trial have no runtime wake.",
     "status": "BY DESIGN", "repair": "owner-authorised one-shots (OWNER_ONE_SHOTS)"},
]

# Files never scanned for follow-on edges: the queue itself and this module.
_EDGE_SKIP = ("queue/durable.py", "autonomy/map.py")


# Owner-authorised one-shots: run when the owner approves a specific spend or freeze (registry
# comments, 2026-09-21..23), never woken autonomously -- by design, not a broken link.
OWNER_ONE_SHOTS: dict[str, str] = {
    "creative.model_freeze": "freezes the owner-approved model pack (owner approval 2026-09-22)",
    "creative.photoreal_calibration": "owner-authorised one vision call (2026-09-22)",
    "visual.portrait_repair": "owner-authorised CA$1.00 repair attempt (2026-09-23)",
    "visual.provider_trial": "owner-authorised CA$4.00 provider trial (2026-09-23)",
}


def _pkg_root() -> Path:
    return Path(__file__).resolve().parents[1]


def follow_on_edges() -> list[dict]:
    """Literal `X.enqueue(agent, "job.type", ...)` calls, attributed to the handler (job type)
    or helper function that contains them."""
    edges: list[dict] = []
    root = _pkg_root()
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8")
        if rel in _EDGE_SKIP or ".enqueue(" not in text:
            continue
        tree = ast.parse(text)
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            origin = (f"owner/API route {fn.name}" if rel == "app/main.py"
                      else f"{rel}:{fn.name}")
            for dec in fn.decorator_list:
                if isinstance(dec, ast.Call) and getattr(dec.func, "attr", "") == "register" \
                        and dec.args and isinstance(dec.args[0], ast.Constant):
                    origin = str(dec.args[0].value)
            for node in ast.walk(fn):
                if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "enqueue" \
                        and len(node.args) >= 2 and isinstance(node.args[1], ast.Constant) \
                        and isinstance(node.args[0], ast.Constant):
                    edges.append({"from": origin, "agent": node.args[0].value,
                                  "to": node.args[1].value, "file": rel,
                                  "line": node.lineno})
    uniq = {(e["from"], e["agent"], e["to"]): e for e in edges}
    return sorted(uniq.values(), key=lambda e: (e["from"], e["to"]))


def _live():
    from ..agents.registry import DEFAULT_AGENTS, FORBIDDEN_COMBINATIONS
    from ..runtime import pipeline  # noqa: F401 - registers handlers, as the runner does
    from ..runtime.worker import CADENCES, handlers

    agents = {a["name"]: a for a in DEFAULT_AGENTS}
    return agents, FORBIDDEN_COMBINATIONS, CADENCES, handlers


def broken_links() -> list[dict]:
    """Mechanically checkable defects in the wiring, as of the code being read now."""
    from . import charters

    agents, forbidden, cadences, handlers = _live()
    known = set(handlers.known())
    out: list[dict] = []
    for name, agent, jt, _p in cadences:
        a = agents.get(agent)
        if a is None:
            out.append({"kind": "cadence_agent_missing", "cadence": name, "agent": agent})
        elif jt not in a["allowed_job_types"] or jt in forbidden.get(agent, set()):
            out.append({"kind": "cadence_not_permitted", "cadence": name, "agent": agent,
                        "job_type": jt})
        if jt not in known:
            out.append({"kind": "cadence_without_handler", "cadence": name, "job_type": jt})
    for a in agents.values():
        dead = sorted(j for j in a["allowed_job_types"] if j not in known)
        if dead:
            out.append({"kind": "permission_without_handler", "agent": a["name"],
                        "job_types": dead,
                        "department": sorted({charters.department_of(j) or "?" for j in dead})})
        if a["allowed_job_types"] and not (set(a["allowed_job_types"]) & known):
            out.append({"kind": "agent_can_run_nothing", "agent": a["name"]})
    for e in follow_on_edges():
        a = agents.get(e["agent"])
        if e["to"] not in known:
            out.append({"kind": "follow_on_without_handler", **e})
        elif a is None or e["to"] not in a["allowed_job_types"]:
            out.append({"kind": "follow_on_not_permitted", **e})
    for ch in charters.CHARTERS:
        for jt in ch.generatable:
            if jt not in known:
                out.append({"kind": "generatable_without_handler", "department": ch.key,
                            "job_type": jt})
    return out


def build(db=None, *, now: datetime | None = None) -> dict:
    """The full map. With a database, next wake and blockers are read from it."""
    from . import charters
    from .orchestrator import _agent_for

    now = now or datetime.now(timezone.utc)
    agents, forbidden, cadences, handlers = _live()
    known = set(handlers.known())
    edges = follow_on_edges()
    live_status: dict = {}
    if db is not None:
        from .status import summary

        live_status = {i["department"]: i for i in summary(db, now=now).get("items", [])}

    departments = []
    for ch in charters.CHARTERS:
        jts = sorted({jt for jt in known | {j for a in agents.values()
                                            for j in a["allowed_job_types"]}
                      | {c[2] for c in cadences}
                      if charters.department_of(jt) == ch.key})
        dept_agents = sorted({a["name"] for a in agents.values()
                              if set(a["allowed_job_types"]) & set(jts)})
        dept_cadences = [{"name": n, "agent": ag, "job_type": jt, "period_seconds": p}
                         for n, ag, jt, p in cadences if charters.department_of(jt) == ch.key]
        incoming = [e for e in edges if charters.department_of(e["to"]) == ch.key]
        outgoing = [e for e in edges if charters.department_of(e["from"]) == ch.key
                    and charters.department_of(e["to"]) != ch.key]
        executable = [jt for jt in jts if jt in known]
        handler_modules = sorted({getattr(handlers.get(jt), "__module__", "?")
                                  for jt in executable})
        woken = {c["job_type"] for c in dept_cadences} | {e["to"] for e in incoming} \
            | set(ch.generatable)
        never_woken = [jt for jt in executable if jt not in woken
                       and jt not in OWNER_ONE_SHOTS]
        st = live_status.get(ch.key, {})
        departments.append({
            "department": ch.key, "name": ch.name, "mission": ch.mission,
            "agents": dept_agents, "charter_agents": list(ch.agents),
            "authority": {"generatable": list(ch.generatable),
                          "generatable_agents": {jt: _agent_for(jt) for jt in ch.generatable},
                          "forbidden": list(ch.forbidden),
                          "protected_never_enqueued": sorted(charters.PROTECTED_JOB_TYPES),
                          "escalation": ch.escalation},
            "wake_mechanisms": {
                "scheduler_cadences": dept_cadences,
                "orchestrator": "autonomy.orchestrate every 15 min + Scheduler.tick idle_wake",
                "follow_on_from": sorted({e["from"] for e in incoming}),
            },
            "cadence": sorted({c["period_seconds"] for c in dept_cadences}),
            "evidence_inputs": list(ch.inputs) + [f"{h.table}.{h.time_column}"
                                                  for h in ch.consumes],
            "work_generation": {
                "handoff": [{"table": h.table, "consumer_job_type": h.consumer_job_type,
                             "why": h.why} for h in ch.consumes],
                "overdue_cadence_catch_up": [jt for jt in ch.generatable
                                             if any(c["job_type"] == jt
                                                    for c in dept_cadences)],
                "self_review": f"autonomy.department_review every {ch.review_hours} h when "
                               "idle",
                "approval_items": ["store.publish -> owner_actions"]
                if ch.key == "store_commerce" else [],
            },
            "mission_creation": "orchestrator._enqueue_mission: job (idempotency key "
                                f"autonomy:{ch.key}:<evidence fingerprint>) + company_memory "
                                "kind=mission + company_timeline mission.created",
            "execution": {"handler_modules": handler_modules,
                          "executable_job_types": executable,
                          "permitted_without_handler": [jt for jt in jts
                                                        if jt not in known]},
            "durable_output": list(ch.outputs),
            "downstream_consumers": list(ch.handoff_to),
            "follow_on": [{"from": e["from"], "to": e["to"]} for e in outgoing],
            "learning_signal": [k.key for k in ch.kpis] + [
                "company_memory kind=kpi_snapshot", "lessons on regression/guardrail"],
            "improvement_path": "lessons -> learn (improve.mine / improve.retrospective) -> "
                                "improvements (sandbox/league/promotion monitor)",
            "next_wake": st.get("next_wake"),
            "blockers": st.get("blockers", [{"kind": "owner_gate", "gate": g}
                                            for g in ch.gates]),
            "never_woken_job_types": never_woken,
            "owner_one_shots": {jt: OWNER_ONE_SHOTS[jt] for jt in executable
                                if jt in OWNER_ONE_SHOTS},
        })
    return {"generated_at": now.isoformat(), "generated_by": "brambleloop.autonomy.map",
            "live_roots": ["runtime.worker.CADENCES", "runtime.worker.handlers",
                           "agents.registry.DEFAULT_AGENTS", "ast enqueue edges",
                           "autonomy.charters"],
            "counts": {"departments": len(departments), "cadences": len(cadences),
                       "handlers": len(known), "agents": len(agents),
                       "follow_on_edges": len(edges)},
            "departments": departments,
            "broken_links": broken_links(),
            "audit_findings": AUDIT_FINDINGS}


def main(argv: list[str]) -> int:
    path = argv[argv.index("--write") + 1] if "--write" in argv else None
    data = build()
    text = json.dumps(data, indent=1, sort_keys=False, default=str)
    if path:
        Path(path).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
