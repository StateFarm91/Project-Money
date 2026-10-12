"""The company constitution as a check every Laura priority and delegation passes through.

D-FB-13: "The company constitution overrides executive authority: she cannot override Product
Truth, accounting truth, security, customer safety, evidence requirements, protected spend,
legal/platform restrictions or owner-only authority; Finance, Product Truth and Security can
challenge or block her."

`review(db, proposal)` returns a verdict; the executive tick acts only on `allowed`. It reuses
the company's existing controls rather than inventing parallel ones:

* **authority** -- her limits come from the *verified* identity record (an unverifiable
  identity blocks everything). A protected job type (`autonomy.charters.PROTECTED_JOB_TYPES`)
  is never a delegation: the verdict is `owner_action`. Anything else must be generatable by
  the target department's charter AND listed in `charters.SAFE_GENERATED` -- the same closed
  allowlist the COO's enqueue boundary re-checks. Her spend ceiling is CA$0.00.
* **finance** -- any proposal that costs money goes to Finance's own spend check
  (`finance.accounting.policy.check_spend`, which records an `acct_challenges` row); paused
  spend scopes; and any open Finance challenge against her work (`laura_challenges`).
* **product_truth** -- an unresolved incident that halts publication (Gate E) blocks
  product-forward work (store, growth, visual, product design) until Product Truth clears it;
  plus open Product Truth challenges.
* **security** -- an unresolved P0/P1 security-class incident, or an open Security
  challenge, blocks her delegations except to the never-paused monitoring/evidence/recovery
  departments (the single F-889 rule, `emergency.never_paused_refusal`). A delegation whose
  executing agent is disabled (an emergency pause) is blocked too.

Laura cannot resolve a challenge: only the department that raised it, or the owner.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

BLOCKERS: tuple[str, ...] = ("finance", "product_truth", "security")
# Work that moves product toward customers; Product Truth's publication halt stops it.
PRODUCT_FORWARD_DEPARTMENTS: frozenset[str] = frozenset(
    {"store_commerce", "growth", "visual", "product_design"})
SECURITY_SIGNATURE_PREFIXES: tuple[str, ...] = (
    "security", "authority_chain_tamper", "secret", "auth.", "etsy.auth", "opsauth")
RESOLVERS = {"finance": ("finance", "owner"), "product_truth": ("product_truth", "owner"),
             "security": ("security", "owner")}


class ChallengeRefused(PermissionError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _never_paused(department: str) -> bool:
    try:
        from ...app.command_center.emergency import never_paused_refusal

        return never_paused_refusal(department) is not None
    except Exception:  # noqa: BLE001
        return department in ("executive", "product_truth", "finance", "platform")


# ---- challenges ------------------------------------------------------------------------

def challenge(db, *, raised_by: str, reason: str, scope: dict | None = None,
              evidence: list | None = None, now: datetime | None = None) -> int:
    """Finance, Product Truth or Security objects to (part of) Laura's work. Returns the id."""
    from .models import LauraChallenge, ensure_tables

    if raised_by not in BLOCKERS:
        raise ChallengeRefused(f"{raised_by!r} cannot block Laura; only {list(BLOCKERS)} can")
    if not isinstance(reason, str) or len(reason.strip()) < 3:
        raise ChallengeRefused("a challenge states its reason")
    scope = {k: v for k, v in (scope or {}).items() if k in ("department", "job_type")}
    ensure_tables(db)
    with db.session() as s:
        row = LauraChallenge(at=now or _now(), raised_by=raised_by, scope=scope,
                             reason=reason.strip()[:2000], evidence=list(evidence or [])[:20])
        s.add(row)
        s.flush()
        return int(row.id)


def resolve_challenge(db, challenge_id: int, *, resolved_by: str, resolution: str,
                      now: datetime | None = None) -> None:
    from .models import LauraChallenge, ensure_tables

    ensure_tables(db)
    with db.session() as s:
        row = s.get(LauraChallenge, int(challenge_id))
        if row is None:
            raise ChallengeRefused(f"no challenge {challenge_id}")
        if resolved_by not in RESOLVERS.get(row.raised_by, ()):
            raise ChallengeRefused(
                f"{resolved_by!r} cannot resolve a {row.raised_by} challenge; only "
                f"{list(RESOLVERS[row.raised_by])} can (Laura cannot clear her own blocks)")
        row.resolved, row.resolved_by = True, resolved_by
        row.resolved_at, row.resolution = now or _now(), (resolution or "")[:2000]


def open_challenges(db) -> list[dict]:
    from .models import LauraChallenge, ensure_tables

    ensure_tables(db)
    with db.session() as s:
        return [{"id": c.id, "raised_by": c.raised_by, "scope": dict(c.scope or {}),
                 "reason": c.reason, "evidence": list(c.evidence or []),
                 "at": c.at.isoformat() if c.at else None}
                for c in s.scalars(select(LauraChallenge).where(
                    LauraChallenge.resolved == False)  # noqa: E712
                    .order_by(LauraChallenge.id))]


def _applies(scope: dict, department: str, job_type: str) -> bool:
    if not scope:
        return True
    if scope.get("department") and scope["department"] != department:
        return False
    if scope.get("job_type") and scope["job_type"] != job_type:
        return False
    return True


# ---- signals read from existing company controls ----------------------------------------

def _halting_incidents(s) -> list:
    from ...core.models import Incident

    return list(s.execute(select(Incident.id, Incident.summary).where(
        Incident.resolved == False, Incident.halts_publication == True)  # noqa: E712
        .order_by(Incident.id.desc()).limit(10)).all())


def _security_incidents(s) -> list:
    from ...core.models import Incident

    rows = s.execute(select(Incident.id, Incident.signature, Incident.severity).where(
        Incident.resolved == False, Incident.severity.in_(["P0", "P1"]))  # noqa: E712
        .order_by(Incident.id.desc()).limit(200)).all()
    return [r for r in rows if str(r.signature or "").lower().startswith(
        SECURITY_SIGNATURE_PREFIXES)]


def _spend_paused(s) -> bool:
    from ...core.models import SpendLimit

    return s.scalar(select(SpendLimit.id).where(SpendLimit.paused == True).limit(1)) \
        is not None  # noqa: E712


def _agent_enabled(s, agent: str | None) -> bool | None:
    from ...core.models import Agent

    if not agent:
        return None
    row = s.scalar(select(Agent).where(Agent.name == agent))
    return None if row is None else bool(row.enabled)


def review(db, proposal: dict, *, now: datetime | None = None) -> dict:
    """Judge one priority/delegation. Never raises: an unreadable control blocks (fail closed).

    proposal: {"kind": "delegation"|"priority", "department", "job_type", "cost_cad",
               "title", "spend_kind"}
    """
    from ...autonomy import charters
    from . import identity

    now = now or _now()
    dept = str(proposal.get("department") or "")
    jt = str(proposal.get("job_type") or "")
    cost = proposal.get("cost_cad") or 0
    try:
        cost = float(cost)
    except (TypeError, ValueError):
        cost = float("inf")
    checks: list[dict] = []

    def add(by: str, outcome: str, why: str, ref: str = "") -> None:
        checks.append({"by": by, "outcome": outcome, "why": why, "ref": ref})

    # authority: from the verified identity record, never from the proposal
    try:
        cur = identity.current(db)
        rec = cur["record"]
        ceiling = float(rec["authority"]["spend_ceiling_cad"])
        add("authority", "pass", f"identity verified (v{cur['version']} "
            f"{cur['sha256'][:12]}...)")
    except Exception as exc:  # noqa: BLE001
        add("authority", "block", f"identity unverifiable ({type(exc).__name__}); no Laura "
            "action proceeds on an unverified identity")
        ceiling = 0.0
    if jt:
        if jt in charters.PROTECTED_JOB_TYPES:
            add("authority", "owner_action", f"{jt} is protected; it becomes an owner action "
                "item, never a job")
        else:
            ch = charters.BY_KEY.get(dept)
            if ch is None:
                add("authority", "block", f"unknown department {dept!r}")
            elif jt not in ch.generatable or jt not in charters.SAFE_GENERATED:
                add("authority", "block", f"{jt} is outside {dept}'s generatable SAFE "
                    "allowlist; Laura cannot expand her authority")
    if cost > ceiling:
        add("authority", "block", f"CA${cost:.2f} exceeds her spend ceiling CA${ceiling:.2f}")

    # finance
    if cost > 0:
        try:
            from ...finance.accounting.policy import check_spend

            v = check_spend(db, {"proposer": "laura", "department": dept,
                                 "amount_cad": cost, "kind": proposal.get("spend_kind") or
                                 "other", "purpose": proposal.get("title") or jt}, now=now)
            add("finance", "pass" if v.get("allow") else "block",
                "; ".join(v.get("reasons") or [])[:400],
                f"acct_challenges:{v.get('challenge_id')}")
        except Exception as exc:  # noqa: BLE001 - fail closed
            add("finance", "block", f"Finance spend check unavailable "
                f"({type(exc).__name__}); spend is refused")
    try:
        with db.session() as s:
            if cost > 0 and _spend_paused(s):
                add("finance", "block", "a spend scope is paused", "spend_limits")
            halting = _halting_incidents(s)
            security = _security_incidents(s)
            from ...autonomy.orchestrator import _agent_for

            agent = _agent_for(jt) if jt and jt not in charters.PROTECTED_JOB_TYPES else None
            enabled = _agent_enabled(s, agent)
    except Exception as exc:  # noqa: BLE001 - fail closed
        add("security", "block", f"company controls unreadable ({type(exc).__name__})")
        halting, security, agent, enabled = [], [], None, None

    if halting and dept in PRODUCT_FORWARD_DEPARTMENTS:
        add("product_truth", "block",
            f"{len(halting)} unresolved incident(s) halt publication; product-forward work "
            f"waits for Product Truth (e.g. #{halting[0].id}: {halting[0].summary[:120]})",
            f"incidents:{halting[0].id}")
    if security and not _never_paused(dept):
        add("security", "block",
            f"{len(security)} unresolved P0/P1 security incident(s) "
            f"(#{security[0].id} {security[0].signature}); only monitoring/evidence/recovery "
            "departments continue", f"incidents:{security[0].id}")
    if enabled is False:
        add("security", "block", f"agent {agent} is disabled (emergency pause or owner "
            "decision); Laura does not route around a pause", f"agents:{agent}")

    try:
        for c in open_challenges(db):
            if not _applies(c["scope"], dept, jt):
                continue
            if c["raised_by"] == "security" and _never_paused(dept) and c["scope"] == {}:
                continue           # a blanket security hold never stops monitoring
            add(c["raised_by"], "block", f"open {c['raised_by']} challenge: {c['reason'][:300]}",
                f"laura_challenges:{c['id']}")
    except Exception as exc:  # noqa: BLE001 - fail closed
        add("security", "block", f"challenges unreadable ({type(exc).__name__})")

    # W3 K11 (F-700): the Brambleloop Constitution as one check, applied to her proposals as
    # to every coordinator work item. Fails closed.
    try:
        from ...authority import constitution as company

        verdict = company.evaluate(db, {
            "actor": "laura", "job_type": jt, "department": dept, "cost_cad": cost,
            **{k: proposal.get(k) for k in (
                "kind", "title", "description", "hypothesis", "provenance", "claims",
                "metrics", "customer_harm", "success_metric", "falsified_if", "fingerprint",
                "addresses_failure", "skip_validation") if proposal.get(k) is not None}},
            now=now, record_audit=False)
        for x in verdict["violations"]:
            add("constitution", "block", f"{x['text']}: {x['why']}"[:400],
                f"constitution:{x['clause']}")
    except Exception as exc:  # noqa: BLE001 - fail closed
        add("constitution", "block", f"company constitution unreadable ({type(exc).__name__})")

    blocks = [c for c in checks if c["outcome"] == "block"]
    owner = [c for c in checks if c["outcome"] == "owner_action"]
    outcome = "block" if blocks else "owner_action" if owner else "allow"
    return {"allowed": outcome == "allow", "outcome": outcome,
            "blocked_by": sorted({c["by"] for c in blocks}),
            "checks": checks, "at": now.isoformat()}
