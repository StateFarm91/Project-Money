"""The owner queue's lifecycle, packets and inventories (wave-3 K7).

F-180  Owner actions have explicit open / satisfied / superseded / withdrawn / parked / expired
       states with timestamps and reasons. Satisfied or superseded actions leave the active
       queue without erasing history: the row stays, `done` flips, and `state`, `state_at`,
       `state_reason` say why. A producer that only flips `done` is stamped
       `closed_unclassified` by the model's validator -- closed, reason not recorded -- rather
       than being credited with a reason it never gave.
F-870  Every owner gate states the exact action, *why software cannot do it*, time/cost, what
       it unlocks and the consequence of delay. A card missing any of these says so
       (`packet_missing`) instead of rendering a blank.
F-173  One authoritative owner-gate inventory: capability, cost, time, the kind of human
       requirement (credentials / legal / physical / spend / decision) and consequence.
F-174  The data-gate inventory: requirements waiting on customers, orders, traffic or reviews,
       and a guard that flags any such row labelled COMPLETE before that data exists.
F-197  The physical-proof card offers the independent tester route as the normal path, never
       asks the owner to crochet, and links to tester roster status.
F-204  An empty active queue proves nothing by itself: it is reported as proven-empty only when
       a fresh readiness assessment and a live gate read stand behind it.
F-623  The queue is prioritised with an explicit rank and urgency on every card.

Nothing here spends, publishes or messages anyone. `sweep` only moves rows whose own
`expires_at` has passed to `expired`.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

OPEN = "open"
SATISFIED = "satisfied"
SUPERSEDED = "superseded"
WITHDRAWN = "withdrawn"
PARKED = "parked"
EXPIRED = "expired"
CLOSED_UNCLASSIFIED = "closed_unclassified"

# Spec states first; the legacy state is honest about a close nobody explained.
STATES: tuple[str, ...] = (OPEN, SATISFIED, SUPERSEDED, WITHDRAWN, PARKED, EXPIRED,
                           CLOSED_UNCLASSIFIED)
ACTIVE_STATES = frozenset({OPEN})
CLOSED_STATES = frozenset({SATISFIED, SUPERSEDED, WITHDRAWN, EXPIRED, CLOSED_UNCLASSIFIED})
_TRANSITIONS: dict[str, frozenset[str]] = {
    OPEN: frozenset({SATISFIED, SUPERSEDED, WITHDRAWN, PARKED, EXPIRED}),
    PARKED: frozenset({OPEN, SATISFIED, SUPERSEDED, WITHDRAWN, EXPIRED}),
    # A closed row may be reopened when its condition comes back; history is the audit row.
    SATISFIED: frozenset({OPEN}), SUPERSEDED: frozenset({OPEN}), WITHDRAWN: frozenset({OPEN}),
    EXPIRED: frozenset({OPEN}), CLOSED_UNCLASSIFIED: frozenset({OPEN}),
}

# A readiness assessment older than this cannot prove the queue empty (the cadence is daily).
ASSESSMENT_FRESH_HOURS = 26

# F-870 / F-173: per owner gate, the kind of human requirement and why software cannot do it.
REQUIREMENT_KINDS = ("credentials", "legal", "physical", "spend", "decision")
GATE_PACKETS: dict[str, tuple[str, str]] = {
    "etsy_shop": ("legal", "opening a shop is the account holder's identity verification (KYC) "
                           "and acceptance of Etsy's seller terms; software must never perform "
                           "either"),
    "etsy_api": ("credentials", "the developer app and its shared secret are issued to the "
                                "account holder in Etsy's developer console after login"),
    "transactions_r": ("credentials", "the OAuth consent screen that grants transactions_r is "
                                      "shown only to the signed-in account holder"),
    "insights_access": ("credentials", "Shop Manager Insights has no authorised API; only the "
                                       "signed-in owner can read it"),
    "model_provider": ("spend", "a provider account and its credit are a payment the owner "
                                "authorises; software may not buy credit"),
    "image_generation": ("spend", "an image provider is a paid account the owner opens"),
    "image_vision": ("spend", "a vision-capable provider is a paid account the owner opens"),
    "ad_authority": ("spend", "advertising money leaves only on the owner's approval, and "
                              "ceilings are enforced in code after it"),
    "benchmark_purchases": ("spend", "buying competitor patterns is consequential spend"),
    "offsite_storage": ("credentials", "a bucket outside this provider is an account and a "
                                       "credential only the owner can create"),
    "owned_surfaces": ("credentials", "a site or Pinterest account is opened by a person who "
                                      "accepts its terms"),
    "production_window": ("decision", "deploying this build for an unattended window is the "
                                      "owner's call under the Execution Directive"),
    "acceptance_ruling": ("decision", "the acceptance wording is the owner's ruling"),
    "canonical_model": ("decision", "approving the canonical visual identity is the owner's "
                                    "ruling; software must not choose it"),
    "benchmark_observation": ("physical", "a browser-only observation a person makes and "
                                          "records"),
    "second_market_benchmark": ("physical", "a browser-only observation a person makes and "
                                            "records"),
    "culture_feed": ("credentials", "a feed account or export is granted by its holder"),
    "live_listings": ("decision", "leaving shadow mode is a phase change only the owner "
                                  "authorises"),
    "tester_roster": ("decision", "recruiting testers is outreach to real people, which needs "
                                  "the owner's authorisation to leave shadow mode"),
    "physical_proof": ("physical", "a finished object is made by human hands; software cannot "
                                   "crochet, and the normal route is an independent tester"),
}

TESTER_ROUTE = {
    "normal_path": "independent tester (tester_roster gate)",
    "asks_owner_to_crochet": False,
    "why": ("the owner parked the physical-sample ask on 2026-09-20 (launch.readiness "
            "PHYSICAL_SAMPLE_PARKED); the other way through is a tester who agreed to make one"),
    "status_path": "/api/cc/truth#tester_roster",
}


class LifecycleRefused(ValueError):
    pass


def _now(now: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    return now if now.tzinfo else now.replace(tzinfo=timezone.utc)


def _aware(v: datetime | None) -> datetime | None:
    if v is None:
        return None
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def effective_state(row) -> str:
    """The state a row is actually in. A legacy row closed before `state` existed reads
    `closed_unclassified` (migrated with the default `open` but `done` set)."""
    state = (row.state or OPEN) if hasattr(row, "state") else OPEN
    if row.done and state in (OPEN, PARKED):
        return CLOSED_UNCLASSIFIED
    if not row.done and state in CLOSED_STATES:
        return OPEN
    return state


def transition(session, row, state: str, reason: str, *, actor: str = "system",
               now: datetime | None = None) -> dict:
    """Move one OwnerAction to `state`, with a reason, and audit the move (history kept)."""
    from ..core.models import AuditLog

    if state not in STATES or state == CLOSED_UNCLASSIFIED:
        raise LifecycleRefused(f"{state!r} is not a state a caller may set: {STATES[:6]}")
    if not (reason or "").strip():
        raise LifecycleRefused("a lifecycle move needs a reason; a bare close is a checkbox")
    current = effective_state(row)
    if state == current:
        return {"id": row.id, "state": state, "changed": False}
    if state not in _TRANSITIONS[current]:
        raise LifecycleRefused(f"{current} -> {state} is not a lifecycle move")
    when = _now(now)
    # State first, then `done`: the model's validator only stamps closed_unclassified on a
    # row still open, so naming the state first is what keeps the reason.
    row.state = state
    row.state_at = when
    row.state_reason = reason[:1000]
    row.done = state in CLOSED_STATES
    session.add(AuditLog(actor=actor[:64], action="owner_action.lifecycle",
                         artifact=f"owner_action:{row.id or row.requirement_key}",
                         detail={"from": current, "to": state, "reason": reason[:500],
                                 "requirement_key": row.requirement_key,
                                 "at": when.isoformat()}))
    return {"id": row.id, "from": current, "state": state, "changed": True}


def close(row, state: str, reason: str, *, now: datetime | None = None) -> None:
    """For producers inside their own session: name why the row leaves the queue.

    Unlike `transition` it writes no audit row (the producer audits its own run), so it can be
    dropped into the many producers that used to write `row.done = True`.
    """
    if state not in CLOSED_STATES or state == CLOSED_UNCLASSIFIED:
        raise LifecycleRefused(f"{state!r} is not a closing state")
    row.state = state
    row.state_at = _now(now)
    row.state_reason = (reason or "")[:1000]
    row.done = True


def sweep(db, *, now: datetime | None = None) -> dict:
    """Expire open/parked rows whose own `expires_at` has passed. Idempotent."""
    from sqlalchemy import select

    from ..core.models import OwnerAction

    now = _now(now)
    expired: list[int] = []
    with db.session() as s:
        for row in s.scalars(select(OwnerAction).where(OwnerAction.done == False,  # noqa: E712
                                                       OwnerAction.expires_at.is_not(None))):
            if _aware(row.expires_at) <= now and effective_state(row) in (OPEN, PARKED):
                transition(s, row, EXPIRED,
                           f"its own expiry {_aware(row.expires_at).isoformat()} passed",
                           actor="ops.owner_queue", now=now)
                expired.append(row.id)
    return {"expired": expired, "at": now.isoformat()}


def history(db, *, limit: int = 200) -> dict:
    """Every row, active or not, by effective state (F-180: closing never erases)."""
    from sqlalchemy import select

    from ..core.models import OwnerAction

    by_state: dict[str, int] = {s: 0 for s in STATES}
    rows = []
    with db.session() as s:
        for row in s.scalars(select(OwnerAction).order_by(OwnerAction.id.desc())):
            st = effective_state(row)
            by_state[st] += 1
            if len(rows) < limit:
                rows.append({"id": row.id, "requirement_key": row.requirement_key,
                             "state": st, "done": bool(row.done),
                             "state_at": _aware(row.state_at).isoformat()
                             if row.state_at else None,
                             "state_reason": row.state_reason or "",
                             "raised_at": _aware(row.at).isoformat() if row.at else None,
                             "expires_at": _aware(row.expires_at).isoformat()
                             if row.expires_at else None})
    return {"by_state": by_state, "active": by_state[OPEN], "rows": rows,
            "states": list(STATES)}


# ---- packets (F-870) and the prioritised queue (F-623) -----------------------------------

PACKET_FIELDS = ("action", "why_software_cannot", "minutes", "max_cost_cad",
                 "capability_unlocked", "consequence_of_waiting")


def packet_for(card: dict, row_why: str = "") -> dict:
    """The F-870 fields a card carries, and which ones it is missing."""
    gate = card.get("gate")
    kind, why = GATE_PACKETS.get(gate or "", ("", ""))
    why = (row_why or why or "").strip()
    if not kind:
        kind = "decision" if card.get("kind") == "OWNER-DECISION" else ""
    out = {"why_software_cannot": why or None, "requirement_kind": kind or None}
    missing = []
    merged = dict(card, **out)
    for f in PACKET_FIELDS:
        v = merged.get(f)
        if v is None or (isinstance(v, str) and not v.strip()) or (
                isinstance(v, str) and v.strip() in ("not stated", "not described")):
            missing.append(f)
    # A spend gate whose ceiling nobody stated is not free: CA$0.00 there would be UNKNOWN
    # rendered as zero. The basis says so and the packet is incomplete until a cost is stated.
    cost = merged.get("max_cost_cad")
    if cost is None:
        # W3-WIRE4: an owner action whose cost basis is UNKNOWN (`OwnerAction.max_cost_known`).
        out["max_cost_basis"] = "UNKNOWN"
    elif kind == "spend" and not cost:
        out["max_cost_basis"] = "UNKNOWN"
        missing.append("max_cost_cad (spend gate with no stated ceiling)")
    else:
        out["max_cost_basis"] = "stated"
    out["packet_missing"] = missing
    out["packet_complete"] = not missing
    return out


def urgency(card: dict) -> str:
    """A word for the rank (the rank itself is `executor._urgency`)."""
    cost = float(card.get("max_cost_cad") or 0.0)
    if card.get("max_cost_basis") == "UNKNOWN":
        return "when costed: the spend is not yet stated"
    if cost == 0.0 and int(card.get("minutes") or 0) <= 15 and card.get("unblocks_count", 0):
        return "now: free, quick and unblocking"
    if cost == 0.0:
        return "soon: free"
    return "when budgeted: costs money"


def enrich_cards(db, cards: list[dict], *, why_by_action_id: dict | None = None) -> list[dict]:
    """Add packet, urgency, rank, lifecycle state and the tester route to inbox cards."""
    why_by_action_id = why_by_action_id or {}
    for i, card in enumerate(cards, start=1):
        card.update(packet_for(card, why_by_action_id.get(card.get("owner_action_id"), "")))
        card["rank"] = i
        card["urgency"] = urgency(card)
        card["state"] = OPEN
        if card.get("gate") == "physical_proof":
            card["tester_route"] = dict(TESTER_ROUTE, tester_status=tester_status(db))
            card["action"] = card["steps"] = (
                "authorise tester outreach so an independent tester can make the sample "
                "(tester_roster); you are not being asked to crochet")
    return cards


def tester_status(db) -> dict:
    """Tester roster status for the physical-proof card (F-197)."""
    try:
        from ..quality import testers

        roster = testers.from_db(db)
    except Exception as exc:  # noqa: BLE001 - an unreadable roster is UNKNOWN, never zero
        return {"status": "UNKNOWN", "reason": f"{type(exc).__name__}"}
    try:
        from ..build2 import executor

        recruited = bool(executor._tester_recruited(db, None))
    except Exception:  # noqa: BLE001
        recruited = None
    return {"status": "OK" if roster["count"] else "NOT-YET-OBSERVED",
            "testers": roster["count"], "tester_roster_gate_open": recruited,
            "note": roster["note"], "source": "physical_tests via quality.testers.from_db"}


# ---- F-204: an empty queue proves nothing by itself ----------------------------------------

def empty_guard(db, cards: list[dict], *, gates_read_live: bool,
                now: datetime | None = None) -> dict:
    """Whether "nothing is waiting on the owner" is proven, or merely observed."""
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    now = _now(now)
    with db.session() as s:
        row = s.scalar(select(AuditLog).where(AuditLog.action == "launch.assessed")
                       .order_by(desc(AuditLog.id)).limit(1))
        at = _aware(row.at) if row is not None else None
        withheld = list(((row.detail or {}) if row is not None else {}).get(
            "owner_requests_withheld_until_package_ready") or [])
    fresh = at is not None and now - at <= timedelta(hours=ASSESSMENT_FRESH_HOURS)
    empty = not cards
    reasons = []
    if not gates_read_live:
        reasons.append("the gates were not read live on this request")
    if at is None:
        reasons.append("no launch readiness assessment has ever been recorded")
    elif not fresh:
        reasons.append(f"the last readiness assessment is from {at.isoformat()}, older than "
                       f"{ASSESSMENT_FRESH_HOURS}h")
    if withheld:
        reasons.append(f"{len(withheld)} owner request(s) are withheld until the launch "
                       f"package is ready: {withheld}")
    proven = empty and not reasons
    return {"empty": empty, "proven_empty": proven,
            "state": ("NOT-EMPTY" if not empty else "PROVEN-EMPTY" if proven
                      else "UNPROVEN-EMPTY"),
            "assessment_at": at.isoformat() if at else None, "withheld": withheld,
            "why": ("a fresh assessment and a live gate read stand behind the empty queue"
                    if proven else "; ".join(reasons) if empty else
                    f"{len(cards)} card(s) are waiting"),
            "closes_anything": False,
            "rule": ("an empty queue closes nothing; the readiness closer still requires a "
                     "non-empty assessment before closing (runtime.release 'if requests:')")}


# ---- F-173 / F-174 inventories --------------------------------------------------------------

def inventory(db, env: dict | None = None) -> dict:
    """The one authoritative owner-gate inventory, read from the one queue."""
    from ..build2 import executor

    inbox = executor.approval_inbox(db, env=env)
    items = [{"rank": c.get("rank"), "gate": c.get("gate"),
              "requirement_key": c.get("requirement_key"),
              "capability": c.get("capability_unlocked"),
              "requirement_kind": c.get("requirement_kind"),
              "action": c.get("action"), "why_software_cannot": c.get("why_software_cannot"),
              "max_cost_cad": c.get("max_cost_cad"), "minutes": c.get("minutes"),
              "consequence_of_waiting": c.get("consequence_of_waiting"),
              "unblocks_count": c.get("unblocks_count"), "urgency": c.get("urgency"),
              "max_cost_basis": c.get("max_cost_basis"),
              "packet_complete": c.get("packet_complete"),
              "packet_missing": c.get("packet_missing")} for c in inbox["cards"]]
    by_kind: dict[str, int] = {}
    for it in items:
        by_kind[it["requirement_kind"] or "unclassified"] = by_kind.get(
            it["requirement_kind"] or "unclassified", 0) + 1
    final_gates: dict = {}
    try:
        from ..build2 import final_master

        fm = final_master.summary()
        final_gates = {"gated_by_kind": fm.get("gated_by_kind"),
                       "gated_by_key": fm.get("gated_by_key")}
    except Exception as exc:  # noqa: BLE001
        final_gates = {"status": "UNKNOWN", "reason": type(exc).__name__}
    return {"items": items, "count": len(items), "by_requirement_kind": by_kind,
            "incomplete_packets": [i["gate"] or i["requirement_key"] for i in items
                                   if not i["packet_complete"]],
            "final_master_gates": final_gates,
            "empty_state": inbox.get("empty_state"),
            "source": inbox["source"]}


DATA_GATE_WORDS = ("customer", "order", "traffic", "review", "buyer", "sale", "visit")


def data_gates(db, env: dict | None = None) -> dict:
    """Requirements waiting on customers/orders/traffic/reviews, and false-completion guard."""
    from ..build2 import executor, final_master

    inbox = executor.approval_inbox(db, env=env)
    executor_waits = [{"gate": d["gate"], "what": d["what"], "unblocks": d["unblocks"]}
                      for d in inbox.get("waiting_on_data") or []]
    customers_open = bool((inbox.get("gate_open") or {}).get("customers"))
    snap = final_master.load() or {}
    rows = snap.get("rows") or []
    waiting, false_complete = [], []
    for r in rows:
        gate = r.get("gate") or {}
        if gate.get("kind") != "data":
            continue
        got, _ = final_master.verdict(r) if r.get("launch_class") == "LAUNCH-CRITICAL" else (
            r.get("completion"), [])
        entry = {"uid": r.get("uid"), "title": r.get("title"), "gate": gate.get("key"),
                 "completion": got}
        waiting.append(entry)
        if got == "COMPLETE" and not customers_open:
            false_complete.append(entry)
    return {"executor_data_gates": executor_waits,
            "final_master_data_gated": waiting,
            "customers_gate_open": customers_open,
            "false_completion": false_complete,
            "status": ("BLOCKED" if false_complete else
                       "UNKNOWN" if not snap else "OK"),
            "rule": ("a requirement waiting on customers/orders/traffic/reviews cannot be "
                     "COMPLETE while the customers gate is closed"),
            "sources": ["build2.executor.approval_inbox.waiting_on_data",
                        "build2/final_master_closure.json (gate.kind == data)"]}
