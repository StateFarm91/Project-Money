"""Authorised follow-on work Laura can create from a business conversation (spec/07 item 11).

Laura proposes; the owner confirms; the company's *existing* authority boundary decides.

* GREEN follow-on -> an internal mission through the COO orchestrator's single enqueue
  boundary (`autonomy.orchestrator._enqueue_mission`), which re-checks that the job type is
  in the department's generatable allowlist, in `charters.SAFE_GENERATED`, and not in
  `charters.PROTECTED_JOB_TYPES`. Laura gets no wider authority than the orchestrator has.
* Protected follow-on (publish, activate, price, ads, customer message: anything in
  `PROTECTED_JOB_TYPES`) -> never a job. It becomes one deduplicated owner action
  (`autonomy.orchestrator._raise_approval`), and only after the owner has stepped up. The
  protected act itself still needs its own grant through Approvals.
* Anything else -> refused.

A follow-on can only be created from a proposal Laura stored with a conversation turn
(`laura_cc_turns.proposals`), so a client cannot name an arbitrary job type; the stored
proposal is re-validated against the catalogue at creation time anyway.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from sqlalchemy import select

LAURA_ACTOR = "laura"
MISSION = "mission"
OWNER_ACTION = "owner_action"


class FollowOnRefused(ValueError):
    """The authority boundary refused; the message is owner-facing."""


class FollowOnNotFound(FollowOnRefused):
    pass


class StepUpRequired(FollowOnRefused):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def green_allowed(department: str, job_type: str) -> str | None:
    """None if Laura may create this internal GREEN mission, else why not."""
    from ...autonomy import charters

    ch = charters.BY_KEY.get(department)
    if ch is None:
        return f"unknown department {department!r}"
    if job_type in charters.PROTECTED_JOB_TYPES:
        return f"{job_type} is protected; it can only become an owner action"
    if job_type not in ch.generatable or job_type not in charters.SAFE_GENERATED:
        return f"{job_type} is outside {department}'s GREEN generatable authority"
    return None


def protected(job_type: str) -> bool:
    from ...autonomy import charters

    return job_type in charters.PROTECTED_JOB_TYPES


def proposal(department: str, job_type: str, title: str, why: str, evidence: list[str],
             *, subject: str = "") -> dict | None:
    """A follow-on proposal, or None when neither GREEN nor protected (never offered)."""
    if protected(job_type):
        kind = OWNER_ACTION
    elif green_allowed(department, job_type) is None:
        kind = MISSION
    else:
        return None
    key = f"{kind}:{department}:{job_type}" + (f":{subject}" if subject else "")
    return {"key": key[:120], "kind": kind, "department": department, "job_type": job_type,
            "subject": subject[:80], "title": title[:200], "why": why[:300],
            "evidence": [str(e)[:200] for e in evidence[:10]],
            "requires_confirmation": True, "requires_step_up": kind == OWNER_ACTION,
            "authority": ("internal GREEN mission via the COO orchestrator" if kind == MISSION
                          else "protected: becomes an owner action; the act itself still "
                               "needs its own owner grant in Approvals")}


def _audit(db, action: str, artifact: str, detail: dict) -> None:
    from ...core.models import AuditLog

    with db.session() as s:
        s.add(AuditLog(actor=LAURA_ACTOR, action=action, artifact=artifact[:200],
                       detail=detail))


def create(db, turn_id: int, proposal_key: str, *, confirmed_by: str,
           stepped_up: bool) -> dict:
    """Create the follow-on a stored proposal describes. Idempotent per (turn, proposal)."""
    from ...autonomy import charters, generators, memory, orchestrator
    from ...queue.durable import JobQueue
    from .models import LauraFollowOn, LauraTurn, ensure_tables

    ensure_tables(db)
    with db.session() as s:
        turn = s.get(LauraTurn, int(turn_id))
        if turn is None:
            raise FollowOnNotFound(f"no conversation turn {turn_id}")
        prop = next((p for p in (turn.proposals or []) if isinstance(p, dict)
                     and p.get("key") == proposal_key), None)
        if prop is None:
            raise FollowOnNotFound(f"turn {turn_id} has no proposal {proposal_key!r}")
        prior = s.scalar(select(LauraFollowOn).where(LauraFollowOn.turn_id == turn.id,
                                                     LauraFollowOn.proposal_key == proposal_key))
        if prior is not None:
            return {"created": False, "kind": prior.kind, "result_ref": prior.result_ref,
                    "followon_id": prior.id, "department": prior.department,
                    "job_type": prior.job_type}
        question = turn.question
    dept, jt = str(prop.get("department") or ""), str(prop.get("job_type") or "")
    ch = charters.BY_KEY.get(dept)
    if ch is None:
        raise FollowOnRefused(f"unknown department {dept!r}")
    fp = hashlib.sha256(f"laura:{turn_id}:{proposal_key}".encode()).hexdigest()[:16]
    evidence = [str(e) for e in prop.get("evidence") or []][:10]
    reason = f"Laura (Founder/CEO) follow-on: {prop.get('title')} -- {prop.get('why')}"[:300]
    now = _now()

    verdict = constitution_review(db, dept, jt, str(prop.get("title") or ""))
    if verdict is not None and verdict.get("outcome") == "block":
        why = "; ".join(c["why"] for c in verdict.get("checks") or []
                        if c.get("outcome") == "block")[:400]
        raise FollowOnRefused(f"blocked by {', '.join(verdict.get('blocked_by') or [])} "
                              f"(company constitution): {why}")

    if protected(jt):
        if not stepped_up:
            raise StepUpRequired(f"{jt} is protected; step up before Laura records it as an "
                                 f"owner action")
        rk = f"laura:{jt}:{prop.get('subject') or dept}"[:200]
        cand = generators.Candidate(
            department=dept, job_type=jt, value=50, source="laura", reason=reason,
            fingerprint=fp, evidence=evidence, protected=True,
            approval={"requirement_key": rk,
                      "action": f"Laura asks for your decision: {prop.get('title')}"[:300],
                      "reason": reason, "max_cost_cad": 0.0, "minutes": 5,
                      "consequence": "Laura's proposal waits; nothing protected happens "
                                     "without your grant",
                      "blocks": jt})
        out = orchestrator._raise_approval(db, ch, cand, now)
        kind, ref = OWNER_ACTION, f"owner_actions:{rk}"
        detail = {"requirement_key": rk, "created": bool(out.get("created"))}
    else:
        why = green_allowed(dept, jt)
        if why:
            raise FollowOnRefused(why)
        block = memory.active_block(db, dept, now=now)
        if block:
            raise FollowOnRefused(f"{dept} is blocked by the owner "
                                  f"({(block.get('body') or {}).get('reason') or 'no reason'});"
                                  f" Laura does not route around a block")
        cand = generators.Candidate(
            department=dept, job_type=jt, value=50, source="laura", reason=reason,
            fingerprint=fp, evidence=evidence,
            inputs={"requested_by": LAURA_ACTOR, "laura_turn": int(turn_id),
                    "confirmed_by": confirmed_by[:80], "question": question[:200]})
        try:
            out = orchestrator._enqueue_mission(db, JobQueue(db), ch, cand, now)
        except orchestrator.ProtectedActionRefused as exc:
            raise FollowOnRefused(str(exc)) from None
        kind, ref = MISSION, f"jobs:{out['job_id']}"
        detail = {"job_id": out["job_id"], "agent": out.get("agent"),
                  "mission": out.get("key"), "created": bool(out.get("created"))}

    memory.record_event(db, f"laura.followon:{fp}", kind="laura.followon",
                        department=dept, actor=LAURA_ACTOR,
                        severity="decision" if kind == OWNER_ACTION else "info",
                        summary=f"Laura created a follow-on ({kind}): {prop.get('title')}",
                        refs=[ref, f"laura_cc_turns:{turn_id}"], at=now)
    _audit(db, f"laura.followon.{kind}", ref,
           {"turn_id": int(turn_id), "proposal": proposal_key, "confirmed_by": confirmed_by,
            "department": dept, "job_type": jt, **detail})
    with db.session() as s:
        row = LauraFollowOn(turn_id=int(turn_id), proposal_key=proposal_key, kind=kind,
                            department=dept, job_type=jt, result_ref=ref,
                            confirmed_by=confirmed_by[:80], detail=detail)
        s.add(row)
        s.flush()
        fid = row.id
    detail["constitution"] = (verdict or {}).get("outcome", "not available")
    detail.update(_remember(db, fid, kind, dept, jt, ref, prop))
    return {"created": True, "kind": kind, "result_ref": ref, "followon_id": fid,
            "department": dept, "job_type": jt, **detail}


def constitution_review(db, dept: str, jt: str, title: str) -> dict | None:
    """Lane D's company constitution (Finance / Product Truth / Security can block Laura).

    None when lane D is not merged; then only this module's own authority checks apply."""
    try:
        from ..core import constitution
    except ImportError:
        return None
    return constitution.review(db, {"kind": "delegation", "department": dept,
                                    "job_type": jt, "cost_cad": 0.0, "title": title})


def _remember(db, fid: int, kind: str, dept: str, jt: str, ref: str, prop: dict) -> dict:
    """Record the follow-on in Laura's operational memory (lane E), citing its row."""
    try:
        from .. import memory as lm
    except ImportError:
        return {"memory": "laura.memory not built"}
    try:
        e = lm.write(db, "operational", f"cc/followon/{fid}",
                     {"kind": kind, "department": dept, "job_type": jt, "result": ref,
                      "title": str(prop.get("title") or "")[:200]},
                     source=[f"laura_cc_followons:{fid}"], actor=lm.Principal.laura(),
                     subject=f"Command Center follow-on: {prop.get('title')}"[:200])
        return {"memory_ref": e.get("ref")}
    except Exception as exc:  # noqa: BLE001 - memory refusal never undoes the follow-on
        return {"memory": f"not recorded: {type(exc).__name__}: {str(exc)[:160]}"}


def recent(db, limit: int = 20) -> list[dict]:
    from .models import LauraFollowOn, ensure_tables

    ensure_tables(db)
    with db.session() as s:
        return [{"id": r.id, "at": r.at.isoformat() if r.at else None, "turn_id": r.turn_id,
                 "kind": r.kind, "department": r.department, "job_type": r.job_type,
                 "result_ref": r.result_ref, "proposal_key": r.proposal_key}
                for r in s.scalars(select(LauraFollowOn).order_by(LauraFollowOn.id.desc())
                                   .limit(max(1, min(int(limit), 100))))]
