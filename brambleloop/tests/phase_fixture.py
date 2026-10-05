"""Test helper (F-299): record the owner's PhaseTransition path up to `to`.

The runtime no longer takes `BRAMBLELOOP_PHASE` on its own word; a fixture that runs in
limited_production or production must record the owner's transitions too, through the same
sealed owner-only path the route uses. Synthetic evidence refs; not provider proof.
"""
from brambleloop.core import phase as P


def record_phase_path(db, token, to="production"):
    """Idempotent: records only the steps above the currently recorded phase."""
    rec = P.latest_recorded(db)
    start = P.rank(rec["phase"]) if rec["recorded"] and rec["valid"] else 0
    for target in P.ORDER[start + 1:P.rank(to) + 1]:
        P.record_transition(db, authorization=token, to=target,
                            reason=f"synthetic fixture transition to {target}",
                            evidence_refs={"readiness": "fixture-readiness",
                                           "rollback": "fixture-rollback"},
                            env={P.ENV_VAR: target})
