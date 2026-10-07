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


# ---- W4-OWNER: the owner's decision packet -- batches -> decisions -> fields ---------------
#
# The owner saw one card per gate and one row per producer: the same Anthropic top-up twice
# (owner actions 19/20), "open the Etsy shop" for a shop open since 2026-09-19, shadow-mode
# graduation as both a readiness row and a `live_listings` gate, and tester outreach as both
# `tester_roster` and `physical_proof`. A decision is the unit the owner answers, so cards and
# rows are merged into decisions, and related decisions are presented together as a batch.
#
# Every decision carries the seven fields below. `max_cost_cad` None means UNKNOWN and is
# printed as UNKNOWN, never CA$0. Figures marked `estimated` are estimates, not quotes.

DECISION_FIELDS = ("decision", "why", "evidence", "max_cost_cad", "consequence_of_yes",
                   "consequence_of_no", "minutes")

BATCHES: tuple[dict, ...] = (
    {"id": "go_live", "order": 1, "title": "Go live on Etsy (one sitting in Shop Manager)",
     "why_batched": ("each of these is a step of the same move out of shadow mode; none is "
                     "useful alone, and answering them together takes one Etsy session")},
    {"id": "model_funding", "order": 2, "title": "Fund the model provider",
     "why_batched": ("model_provider, image_vision and the funding rows are one Anthropic "
                     "balance: one top-up opens all of them")},
    {"id": "rulings", "order": 3, "title": "Rulings only the owner can make (free, minutes)",
     "why_batched": "free decisions with no account or spend behind them"},
    {"id": "etsy_account", "order": 4, "title": "Owner-only Etsy account screens",
     "why_batched": ("each needs the signed-in account holder in a browser, so they are done "
                     "in the same login")},
    {"id": "storage", "order": 5, "title": "Storage and continuity spend",
     "why_batched": "both are storage accounts outside the code, approved as one spend line"},
    {"id": "benchmark", "order": 6, "title": "Competitive benchmark purchases",
     "why_batched": ("the purchase gate and the pre-launch benchmark challenge wait on the "
                     "same purchased patterns")},
    {"id": "channels", "order": 7, "title": "Owned publishing channels",
     "why_batched": "accounts that accept a platform's terms in the owner's name"},
    {"id": "paid_media", "order": 8, "title": "Paid media (after organic sales exist)",
     "why_batched": "advertising authority; recommended only after the shop has sold"},
    {"id": "other", "order": 99, "title": "Other open decisions",
     "why_batched": "decisions raised by producers outside the table above, as they stand"},
)
BATCH_BY_ID = {b["id"]: b for b in BATCHES}

# One entry per decision. `gates` / `keys` are the executor gates and OwnerAction
# requirement_keys that are this one decision. A card's own stated figure (from its
# producer's row or the access registry) wins over the table's.
DECISIONS: tuple[dict, ...] = (
    {"id": "etsy_kyc_payout", "batch": "go_live", "kind": "legal",
     "gates": ("etsy_shop",), "keys": ("etsy_shop", "payout"),
     "decision": ("Confirm in Etsy Shop Manager > Settings > Payment settings that identity "
                  "verification, the payout bank account (Canadian chequing) and tax details "
                  "(GST/HST number or small-supplier declaration) show complete; complete any "
                  "that do not."),
     "why": ("Etsy will not pay out or open a shop to buyers without them, and KYC/banking may "
             "only be entered by the account holder. The shop itself exists "
             "(BrambleloopStudio, executor gate etsy_shop, 2026-09-19)."),
     "max_cost_cad": 0.0, "cost_basis": "stated (Etsy charges nothing for this step)",
     "minutes": 15,
     "consequence_of_yes": "the payout prerequisite for publishing is met",
     "consequence_of_no": "listings cannot go live and no revenue can be paid out"},
    {"id": "listing_fees", "batch": "go_live", "kind": "spend",
     "gates": (), "keys": ("listing_fees",),
     "decision": "Approve Etsy's listing fees for the opening catalogue (figure on the card).",
     "why": "the first money that leaves the account; no consequential spend without approval",
     "max_cost_cad": None, "cost_basis": "from the readiness request (catalogue-derived)",
     "minutes": 2,
     "consequence_of_yes": "publishing is no longer blocked on fees",
     "consequence_of_no": "publishing stays blocked on a two-minute decision"},
    {"id": "leave_shadow", "batch": "go_live", "kind": "decision",
     "gates": ("live_listings",), "keys": ("phase",),
     "decision": ("Authorise graduation from shadow to staging, then limited production, one "
                  "step at a time, once the steps above are done."),
     "why": ("leaving shadow mode is a phase change only the owner authorises; the "
             "live_listings gate and the readiness 'phase' row are this one decision"),
     "max_cost_cad": 0.0, "cost_basis": "stated: no spend beyond the listing fees above",
     "minutes": 5,
     "consequence_of_yes": ("listings can be published under the publication authority; the "
                            "live-listing requirements un-park"),
     "consequence_of_no": "everything stays drafted and nothing reaches a customer"},
    {"id": "tester_outreach", "batch": "go_live", "kind": "decision",
     "gates": ("tester_roster", "physical_proof"), "keys": ("physical_calibration",),
     "decision": ("Authorise outreach to independent pattern testers and one paid sample make "
                  "(the 20 cm storage basket). You are not asked to crochet."),
     "why": ("recruiting testers is outreach to real people (an exit from shadow mode); the "
             "physical proof is made by that tester, so both gates are this one decision"),
     "max_cost_cad": None, "cost_basis": "estimated from gates.risk_matrix tester fee",
     "minutes": 5,
     "consequence_of_yes": ("a measured sample calibrates yardage and Class C products can "
                            "become shippable"),
     "consequence_of_no": ("yardage stays a +/-20% tolerance, Class C stays unshippable, the "
                           "first buyer becomes the tester")},
    {"id": "trademark_filing", "batch": "go_live", "kind": "spend",
     "gates": (), "keys": ("brand_clearance",),
     "decision": ("Decide whether to file a Canadian trademark for 'Brambleloop Studio' "
                  "(CA$458.05 first class). The free knock-out search is company work."),
     "why": "a filing is legal spend in the owner's name",
     "max_cost_cad": 460.0, "cost_basis": "stated (CIPO first-class fee, rounded up)",
     "minutes": 20,
     "consequence_of_yes": "the name is protected before brand equity accumulates on it",
     "consequence_of_no": "low risk at zero sales, rising with every sale"},
    {"id": "fund_model", "batch": "model_funding", "kind": "spend",
     "gates": ("model_provider", "image_vision", "image_generation"),
     "keys": ("model_credits", "model_provider_balance"),
     "decision": ("Add credit to the Anthropic account the API key belongs to "
                  "(console.anthropic.com -> Plans & Billing)."),
     "why": ("the balance is spent; the CA$100/month ceiling stays enforced in code, so a "
             "larger balance cannot be spent faster"),
     "max_cost_cad": 25.0, "cost_basis": "stated (smallest useful top-up)",
     "minutes": 5,
     "consequence_of_yes": ("judging, vision and text calls run again: identity "
                            "measurement, asset-truth checks, gallery analysis, #94"),
     "consequence_of_no": "every check that needs a model stays refused before spending"},
    {"id": "acceptance_ruling", "batch": "rulings", "kind": "decision",
     "gates": ("acceptance_ruling",), "keys": (),
     "decision": ("Rule whether an API + vision traversal satisfies the 'browser/vision' "
                  "wording of #189/#221/#222/#320 (yes / no)."),
     "why": "the acceptance wording is the owner's ruling",
     "max_cost_cad": 0.0, "cost_basis": "stated", "minutes": 2,
     "consequence_of_yes": "four requirements are graded against the API path",
     "consequence_of_no": "they stay parked and every acceptance grade stays provisional"},
    {"id": "production_window", "batch": "rulings", "kind": "decision",
     "gates": ("production_window",), "keys": (),
     "decision": ("Authorise deploying the reviewed build to the existing service for one "
                  "unattended window (phase stays shadow)."),
     "why": "deploying is the owner's call under the Execution Directive",
     "max_cost_cad": 0.0, "cost_basis": "stated: the existing service, no new spend",
     "minutes": 10,
     "consequence_of_yes": ("the off-device proof (#195) can be read from real rows, and the "
                            "fixes that close stale production incidents take effect"),
     "consequence_of_no": "#195 stays parked and production keeps the stale rows"},
    {"id": "transactions_scope", "batch": "etsy_account", "kind": "credentials",
     "gates": ("transactions_r",), "keys": ("reauthorise_transactions_r",),
     "decision": "Re-authorise the Etsy app with the transactions_r scope (consent screen).",
     "why": "the OAuth consent screen is shown only to the signed-in account holder",
     "max_cost_cad": 0.0, "cost_basis": "stated", "minutes": 3,
     "consequence_of_yes": "orders can be read (#11, #12)",
     "consequence_of_no": "the order source stays closed"},
    {"id": "insights_reading", "batch": "etsy_account", "kind": "credentials",
     "gates": ("insights_access",), "keys": (),
     "decision": ("Record one Marketplace Insights reading from Shop Manager "
                  "(POST the reading; no API exists)."),
     "why": "Shop Manager Insights has no authorised API; only the signed-in owner can read it",
     "max_cost_cad": 0.0, "cost_basis": "stated", "minutes": 10,
     "consequence_of_yes": "search-demand requirements (#1, #37, #236) get real readings",
     "consequence_of_no": "they stay parked on proxies"},
    {"id": "storage_durable", "batch": "storage", "kind": "spend",
     "gates": (), "keys": ("artifact_storage",),
     "decision": "Approve durable object storage for purchased files (Railway volume or S3).",
     "why": "container files do not survive a restart; a buyer's download link must",
     "max_cost_cad": 5.0, "cost_basis": "stated (per month)", "minutes": 10,
     "consequence_of_yes": "purchased files survive deploys",
     "consequence_of_no": "harmless in shadow; a broken download for a paying customer once live"},
    {"id": "storage_offsite", "batch": "storage", "kind": "credentials",
     "gates": ("offsite_storage",), "keys": (),
     "decision": "Create an object-storage bucket outside this provider and its credential.",
     "why": "an account and credential only the owner can create",
     "max_cost_cad": None, "cost_basis": "UNKNOWN (provider not chosen)", "minutes": 15,
     "consequence_of_yes": "the continuity archive survives losing the provider (#51)",
     "consequence_of_no": "a provider loss loses the archive with it"},
    {"id": "benchmark_purchase", "batch": "benchmark", "kind": "spend",
     "gates": ("benchmark_purchases",), "keys": ("benchmark_challenge",),
     "decision": ("Buy the selected benchmark patterns (/api/benchmark-selection) and upload "
                  "them at /ops/teardown."),
     "why": "buying competitor patterns is consequential spend",
     "max_cost_cad": 300.0, "cost_basis": "stated", "minutes": 30,
     "consequence_of_yes": "the pre-launch challenge (#168) and teardowns can run",
     "consequence_of_no": "the first honest comparison happens in a buyer's downloads"},
    {"id": "owned_surfaces", "batch": "channels", "kind": "credentials",
     "gates": ("owned_surfaces",), "keys": (),
     "decision": "Open a Pinterest business account and/or a site this company can publish to.",
     "why": "a person accepts the platform's terms",
     "max_cost_cad": None, "cost_basis": "UNKNOWN (a domain/site has a cost; Pinterest is free)",
     "minutes": 20,
     "consequence_of_yes": "off-Etsy content requirements un-park",
     "consequence_of_no": "they stay parked; Etsy-only discovery"},
    {"id": "ad_budget", "batch": "paid_media", "kind": "spend",
     "gates": ("ad_authority",), "keys": (),
     "decision": "Set a daily advertising cap (CA$/day) or decline paid media for now.",
     "why": "advertising money leaves only on approval; ceilings are enforced in code",
     "max_cost_cad": None, "cost_basis": "UNKNOWN until the owner names a cap", "minutes": 5,
     "consequence_of_yes": "the ads requirements un-park under that cap",
     "consequence_of_no": "no paid media; recommended until organic sales exist"},
)
DECISION_BY_GATE = {g: d for d in DECISIONS for g in d["gates"]}
DECISION_BY_KEY = {k: d for d in DECISIONS for k in d["keys"]}

# Gates the company opens itself. Listed so the owner is never asked for them.
COMPANY_OPENED_GATES: dict[str, str] = {
    "culture_feed": ("opened by the company's own daily `culture.sweep` cadence (Wikimedia "
                     "Pageviews: free, no key, no account) on its first sourced "
                     "CultureObservation row; no owner action opens or speeds it"),
}


def _decision_for(card: dict) -> dict | None:
    return DECISION_BY_GATE.get(card.get("gate") or "") or DECISION_BY_KEY.get(
        card.get("requirement_key") or "")


def decision_fields(card: dict, decision: dict | None = None) -> dict:
    """The seven fields for one card, from its decision entry where one exists."""
    d = decision if decision is not None else _decision_for(card)
    stated = card.get("max_cost_cad")
    if card.get("max_cost_basis") == "UNKNOWN":
        stated = None
    if d is not None:
        cost = stated if stated is not None and (stated or d["max_cost_cad"] == 0.0) \
            else d["max_cost_cad"]
        basis = ("stated by the producer" if cost == stated and stated is not None
                 else d["cost_basis"])
        out = {"decision": d["decision"], "why": card.get("why") or d["why"],
               "minutes": d["minutes"],
               "consequence_of_yes": d["consequence_of_yes"],
               "consequence_of_no": (card.get("consequence_of_waiting")
                                     if card.get("consequence_of_waiting") not in
                                     (None, "", "not stated") and not str(
                                         card.get("consequence_of_waiting")).startswith(
                                         "requirements [")
                                     else d["consequence_of_no"]),
               "requirement_kind": d["kind"]}
    else:
        cost, basis = stated, ("stated by the producer" if stated is not None else "UNKNOWN")
        cyes = card.get("capability_unlocked") or ""
        out = {"decision": card.get("action") or card.get("what") or "",
               "why": card.get("why") or "",
               "minutes": card.get("minutes") or None,
               "consequence_of_yes": (f"unlocks: {cyes}" if cyes else ""),
               "consequence_of_no": (card.get("consequence_of_waiting")
                                     if card.get("consequence_of_waiting") != "not stated"
                                     else ""),
               "requirement_kind": card.get("requirement_kind")}
    out["max_cost_cad"] = cost
    out["max_cost_basis"] = "UNKNOWN" if cost is None else basis
    out["max_cost_display"] = "UNKNOWN" if cost is None else f"CA${cost:,.2f}"
    out["evidence"] = card.get("evidence") or card.get("how_it_is_checked") or ""
    missing = [f for f in DECISION_FIELDS if f != "max_cost_cad"
               and (out.get(f) in (None, "") or (isinstance(out.get(f), str)
                                                 and not out[f].strip()))]
    out["fields_missing"] = missing
    return out


def batch_cards(cards: list[dict]) -> dict:
    """Cards -> decisions (merged) -> batches, in the order the owner should answer them."""
    decisions: dict[str, dict] = {}
    for c in cards:
        d = _decision_for(c)
        did = d["id"] if d else f"card:{c.get('gate') or c.get('requirement_key')}"
        batch = d["batch"] if d else "other"
        item = decisions.get(did)
        if item is None:
            item = dict(decision_fields(c, d), id=did, batch=batch,
                        gates=[], requirement_keys=[], owner_action_ids=[], unblocks=[],
                        ranks=[])
            decisions[did] = item
        if c.get("gate") and c["gate"] not in item["gates"]:
            item["gates"].append(c["gate"])
        rk = c.get("requirement_key")
        if rk and rk not in item["requirement_keys"]:
            item["requirement_keys"].append(rk)
        for oid in c.get("merged_owner_action_ids") or (
                [c["owner_action_id"]] if c.get("owner_action_id") else []):
            if oid not in item["owner_action_ids"]:
                item["owner_action_ids"].append(oid)
        for u in c.get("unblocks") or []:
            if u not in item["unblocks"]:
                item["unblocks"].append(u)
        if c.get("rank") is not None:
            item["ranks"].append(c["rank"])
    batches = []
    for b in sorted(BATCHES, key=lambda x: x["order"]):
        items = [i for i in decisions.values() if i["batch"] == b["id"]]
        if not items:
            continue
        costs = [i["max_cost_cad"] for i in items]
        batches.append({
            "id": b["id"], "title": b["title"], "why_batched": b["why_batched"],
            "items": items, "decisions": len(items),
            "minutes_total": sum(int(i["minutes"] or 0) for i in items),
            "minutes_known": all(i["minutes"] for i in items),
            "max_cost_cad_total": (None if any(c is None for c in costs)
                                   else round(sum(costs), 2)),
            "max_cost_display": ("UNKNOWN (at least one item is not costed)"
                                 if any(c is None for c in costs)
                                 else f"CA${sum(costs):,.2f}")})
    incomplete = [i["id"] for b in batches for i in b["items"] if i["fields_missing"]]
    return {"batches": batches, "decisions": sum(b["decisions"] for b in batches),
            "cards": len(cards), "incomplete": incomplete,
            "fields": list(DECISION_FIELDS),
            "rule": ("one decision per thing the owner answers: gates and producer rows that "
                     "are the same decision are merged; related decisions are batched; an "
                     "unknown cost is UNKNOWN, never CA$0")}


def _tester_estimate() -> float | None:
    try:
        from ..gates import risk_matrix as rm

        return round(8 * rm.TESTER_FEE_CAD_PER_HOUR + 25.0, 2)
    except Exception:  # noqa: BLE001 - an unreadable estimate is UNKNOWN, never 0
        return None


for _d in DECISIONS:
    if _d["id"] == "tester_outreach":
        _d["max_cost_cad"] = _tester_estimate()
        if _d["max_cost_cad"] is None:
            _d["cost_basis"] = "UNKNOWN"
