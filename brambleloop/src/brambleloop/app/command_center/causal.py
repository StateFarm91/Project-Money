"""F-662 Live Company Timeline: causal stories instead of tool-call noise (W4-CLOSE6).

  F-662  "human-readable causal activity stream across departments instead of raw tool-call
          noise."

/api/cc/timeline listed audit rows and company events side by side. This module turns jobs
into stories, using the cause-and-effect links `runtime.lineage` records when a job enqueues
another.
- A **story** is a root job and everything it caused, in order. For each step it gives the
  department (the agent that ran it), a plain-language line saying what happened, and the
  outcome.
- **Housekeeping** is a scheduled check that caused nothing (heartbeat, health, SLO, queue
  checks, the orchestrator tick). It is counted, not told: "41 routine checks ran". This is
  the noise the requirement asks the timeline to replace.
- A job with no recorded parent is a root. If it came from a cadence its idempotency key says
  so, and the story says "scheduled". Otherwise the story says "cause not recorded". A cause is
  never guessed.

Read-only.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select

HOUSEKEEPING_PREFIXES = ("ops.", "swarm.", "autonomy.orchestrate", "laura.executive_tick",
                         "build.tick", "learn.scan", "autonomy.department_review",
                         "support.triage", "finance.governor", "visual.rnd.cycle")

# What a job type did, in words an owner reads. A type not listed is shown by its name.
VERBS = {
    "cir.compile": "compiled the pattern",
    "cir.draft": "drafted a pattern specification",
    "gate.certify": "certified the release",
    "listing.draft": "drafted the listing",
    "assets.build": "built the PDFs and listing images",
    "pricing.position": "set the price",
    "listing.seo": "wrote the title, tags and description",
    "launch.plan": "planned the launch",
    "store.publish": "tried to publish to Etsy",
    "store.activate": "tried to activate the listing",
    "marketing.schedule": "scheduled the marketing",
    "commerce.orders_ingest": "read new orders",
    "commerce.order_readings": "read the order metrics",
    "intel.gallery_analysis": "studied competitor gallery images",
    "mjs.scan": "scanned the benchmark shops",
    "creative.tournament": "ran a design tournament",
    "creative.reference_reading": "read a reference design",
    "seo.cycle": "reviewed listing search copy",
    "support.reply": "drafted a customer reply",
    "finance.reconcile": "reconciled the books",
}


def _aware(v):
    if v is None:
        return None
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def _housekeeping(job_type: str) -> bool:
    return job_type.startswith(HOUSEKEEPING_PREFIXES)


def _outcome(j) -> str:
    st = j.status.value if hasattr(j.status, "value") else str(j.status)
    if st == "done":
        return "done"
    if st in ("dead", "failed"):
        err = (j.last_error or "").strip().splitlines()[0][:140] if j.last_error else ""
        return f"stopped: {err}" if err else "stopped"
    return st


def _subject(j) -> str:
    i = j.inputs if isinstance(j.inputs, dict) else {}
    cir = i.get("cir") if isinstance(i.get("cir"), dict) else {}
    slug = i.get("slug") or i.get("product_slug") or cir.get("slug") or ""
    ver = i.get("version") or cir.get("version") or ""
    return f"{slug} {ver}".strip()


def stories(db, *, hours: float = 48, limit: int = 20, scan: int = 3000,
            now: datetime | None = None) -> dict:
    from ...core.models import Job
    from ...runtime import lineage

    now = now or datetime.now(timezone.utc)
    since = now - timedelta(hours=hours)
    with db.session() as s:
        jobs = list(s.scalars(select(Job).where(or_(Job.created_at >= since,
                                                    Job.finished_at >= since))
                              .order_by(Job.id.desc()).limit(scan)))
        for j in jobs:
            s.expunge(j)
    by_id = {j.id: j for j in jobs}
    parent_of = lineage.parents(db, by_id)
    children: dict[int, list[int]] = defaultdict(list)
    for c, p in parent_of.items():
        if p in by_id:
            children[p].append(c)
    roots = [j for j in jobs if parent_of.get(j.id) not in by_id]
    told, routine = [], Counter()
    for r in sorted(roots, key=lambda j: _aware(j.created_at) or now, reverse=True):
        chain, todo = [], [r.id]
        while todo:
            jid = todo.pop(0)
            chain.append(by_id[jid])
            todo.extend(sorted(children.get(jid, [])))
        if len(chain) == 1 and _housekeeping(r.job_type):
            routine[r.job_type] += 1
            continue
        if len(told) >= limit:
            continue
        key = r.idempotency_key or ""
        if r.id in parent_of:
            cause = f"caused by jobs:{parent_of[r.id]} (outside this window)"
        elif key.startswith("cadence:"):
            cause = f"scheduled ({key.split(':')[1] if ':' in key else 'cadence'})"
        else:
            cause = "cause not recorded"
        steps = [{"job": f"jobs:{j.id}", "job_type": j.job_type, "department": j.agent,
                  "what": VERBS.get(j.job_type, j.job_type), "outcome": _outcome(j),
                  "caused_by": (f"jobs:{parent_of[j.id]}" if j.id in parent_of else None),
                  "at": (_aware(j.finished_at) or _aware(j.created_at)).isoformat()
                  if (j.finished_at or j.created_at) else None}
                 for j in chain]
        subject = _subject(r)
        last = steps[-1]
        told.append({
            "headline": (f"{subject}: " if subject else "")
                        + " → ".join(f"{s_['department']} {s_['what']}" for s_ in steps[:6])
                        + (f" → … ({len(steps) - 6} more)" if len(steps) > 6 else ""),
            "outcome": f"{last['department']} {last['what']}: {last['outcome']}",
            "cause": cause, "departments": sorted({s_["department"] for s_ in steps}),
            "started_at": steps[0]["at"], "last_at": last["at"], "steps": steps,
            "sources": [s_["job"] for s_ in steps]})
    return {"status": "OK", "as_of": now.isoformat(), "window_hours": hours,
            "stories": told,
            "routine": {"count": sum(routine.values()), "by_type": dict(routine.most_common(12)),
                        "why": "scheduled checks that caused nothing: counted, not told"},
            "basis": "jobs + job_links (runtime.lineage); a root without a recorded parent is "
                     "'scheduled' (cadence key) or 'cause not recorded', never guessed"}
