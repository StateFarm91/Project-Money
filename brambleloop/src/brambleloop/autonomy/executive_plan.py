"""F-602: the Executive / COO plan -- goals, critical path, department priorities and owner
decisions as one durable record, read by the swarm allocation.

Built from what the runtime already knows, never typed in:

* **goals** -- the company's stated commercial goals (first sale; a sustainable CA$3,000 a
  month), each with its current reading from orders. UNMEASURED is never zero.
* **critical path** -- the closed gates real work is parked on (`build2.executor` approval
  inbox, its not-yet-askable and data-gated lists), ordered by how many requirements each
  un-parks, each with the departments whose charter waits on it (`charters.gates`).
* **department priorities** -- departments on the critical path first, then the charter
  order the orchestrator already serves.
* **owner decisions** -- the batched owner queue (`owner_queue.batch_cards`): count, minutes
  and maximum cost; UNKNOWN cost stays UNKNOWN.

`refresh(db)` stores it in company memory (`executive:plan`); `swarm.orchestrate.allocate`
reads `priority_agents()` and gives a lane with open work on the critical path one more
specialist, inside what its ceiling affords (never raises a ceiling).

Not here, and named: the merge/deploy queue and file-authority ownership are build-side
(`ops/registry.py` lane ownership, F-457; `ops/deploy_guard.py`) and are not visible to the
runtime, which never holds the repository.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

MEMORY_KEY = "executive:plan"
MONTHLY_TARGET_CAD = 3000.0


def _goals(db, now) -> list[dict]:
    from sqlalchemy import func, select

    from ..core.models import Order

    with db.session() as s:
        orders = s.scalar(select(func.count()).select_from(Order)) or 0
        rev30 = float(s.scalar(select(func.coalesce(func.sum(Order.revenue_cad), 0.0)).where(
            Order.at >= now - timedelta(days=30))) or 0.0)
    # Review cbd4ff1 N-3: zero orders only means "no sale" when the order source is read.
    try:
        from ..finance.accounting import health as H

        state = H.reading(db, now=now)["sources"]["orders"]["state"]
        fig = H.figure_reading(state, orders > 0)
    except Exception as exc:  # noqa: BLE001 - an unreadable source is UNKNOWN, never 0
        state, fig = f"unreadable: {type(exc).__name__}", "UNKNOWN"
    first = ({"reading": "UNKNOWN", "met": None} if fig == "UNKNOWN" else
             {"reading": orders, "met": orders > 0})
    return [
        {"key": "first_sale", "statement": "the first real sale", **first,
         "source": "orders", "basis": f"order source {state} ({fig})"},
        {"key": "sustainable_monthly", "statement":
         f"a sustainable CA${MONTHLY_TARGET_CAD:,.0f} a month",
         "reading": round(rev30, 2) if orders else "UNMEASURED",
         "met": orders > 0 and rev30 >= MONTHLY_TARGET_CAD,
         "source": "orders.revenue_cad over the last 30 days"},
    ]


def _critical_path(db, env) -> list[dict]:
    from ..build2 import executor
    from . import charters

    depts: dict[str, list[str]] = {}
    for c in charters.CHARTERS:
        for g in c.gates:
            depts.setdefault(g, []).append(c.key)
    inbox = executor.approval_inbox(db, env=env)
    items = []
    for kind, rows in (("owner", inbox.get("cards") or []),
                       ("not_yet_askable", inbox.get("not_yet_askable") or []),
                       ("data", inbox.get("waiting_on_data") or []),
                       ("external", inbox.get("external_capability_unavailable") or [])):
        for r in rows:
            gate = r.get("gate")
            if not gate:
                continue
            unblocks = r.get("unblocks") or []
            items.append({"gate": gate, "kind": kind, "unblocks": len(unblocks),
                          "departments": sorted(depts.get(gate, [])),
                          "precondition": r.get("precondition")})
    items.sort(key=lambda i: (-i["unblocks"], i["gate"]))
    return items


def compute(db, *, env: dict | None = None, now: datetime | None = None) -> dict:
    from ..ops import owner_queue
    from . import charters
    from .orchestrator import DEPARTMENT_ORDER

    now = now or datetime.now(timezone.utc)
    env = env if env is not None else {}
    path = _critical_path(db, env)
    on_path = []
    for item in path:
        for d in item["departments"]:
            if d not in on_path:
                on_path.append(d)
    order = on_path + [c.key for c in DEPARTMENT_ORDER if c.key not in on_path]
    try:
        from ..build2 import executor

        batched = owner_queue.batch_cards(executor.approval_inbox(db, env=env)["cards"])
        decisions = {"count": batched["decisions"],
                     "minutes": sum(b["minutes_total"] for b in batched["batches"]),
                     "max_cost": [b["max_cost_display"] for b in batched["batches"]],
                     "batches": [b["id"] for b in batched["batches"]]}
    except Exception as exc:  # noqa: BLE001 - unreadable is UNKNOWN, never "none"
        decisions = {"count": "UNKNOWN", "why": type(exc).__name__}
    agents_by_dept = {c.key: list(c.agents) for c in charters.CHARTERS}
    return {"as_of": now.isoformat(), "goals": _goals(db, now), "critical_path": path,
            "department_priority": order, "critical_departments": on_path,
            "priority_agents": sorted({a for d in on_path for a in agents_by_dept.get(d, [])}),
            "owner_decisions": decisions,
            "not_modelled_here": ["merge/deploy queue (ops/deploy_guard.py, build-side)",
                                  "file/authority ownership (ops/registry.py, F-457)"]}


def refresh(db, *, env: dict | None = None, now: datetime | None = None) -> dict:
    from . import memory

    plan = compute(db, env=env, now=now)
    memory.remember(db, MEMORY_KEY, kind="executive.plan", department="executive",
                    subject="executive plan: goals, critical path, priorities", state="ok",
                    body=plan, sources=["build2.executor", "owner_queue", "orders"], now=now)
    return plan


def priority_agents(db) -> set[str]:
    """The agents of critical-path departments, from the last stored plan (empty if none)."""
    from . import memory

    try:
        row = memory.get(db, MEMORY_KEY)
    except Exception:  # noqa: BLE001 - no plan is no boost, never a failure
        return set()
    return set(((row or {}).get("body") or {}).get("priority_agents") or [])
