"""Test helper (F-299): record the owner's PhaseTransition path up to `to`.

The runtime no longer takes `BRAMBLELOOP_PHASE` on its own word; a fixture that runs in
limited_production or production must record the owner's transitions too, through the same
sealed owner-only path the route uses.

rc1-AUTH D4: an upward transition's evidence refs must resolve to real, recent, passing
`launch.assessed` and `launch.rollback_rehearsed` rows, so this fixture writes one synthetic
pair (marked `synthetic_fixture`, artifact `phase-fixture@0` so no release reader picks them
up) and cites their ids. Synthetic test evidence; not provider proof.
"""
from brambleloop.core import phase as P


def synthetic_evidence(db) -> dict:
    """Ids of a synthetic passing readiness assessment and rollback rehearsal."""
    from brambleloop.core.models import AuditLog

    with db.session() as s:
        ready = AuditLog(actor="orchestrator", action=P.EVIDENCE_ACTIONS["readiness"],
                         artifact="phase-fixture@0",
                         detail={"ready": True, "synthetic_fixture": True})
        rehearsed = AuditLog(actor="orchestrator", action=P.EVIDENCE_ACTIONS["rollback"],
                             artifact="phase-fixture@0",
                             detail={"ok": True, "steps": [], "synthetic_fixture": True})
        s.add_all([ready, rehearsed])
        s.flush()
        return {"readiness": str(ready.id), "rollback": str(rehearsed.id)}


def record_phase_path(db, token, to="production"):
    """Idempotent: records only the steps above the currently recorded phase."""
    rec = P.latest_recorded(db)
    start = P.rank(rec["phase"]) if rec["recorded"] and rec["valid"] else 0
    for target in P.ORDER[start + 1:P.rank(to) + 1]:
        P.record_transition(db, authorization=token, to=target,
                            reason=f"synthetic fixture transition to {target}",
                            evidence_refs=synthetic_evidence(db),
                            env={P.ENV_VAR: target})
