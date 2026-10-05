"""Owner-only phase-transition route (F-299).

Records the sealed PhaseTransition that, together with `BRAMBLELOOP_PHASE`, decides the
effective runtime phase (`core.phase`). It never edits the deployment environment: a recorded
move up has no effect until the environment agrees, and an environment change alone has no
effect until a transition is recorded.
"""
from fastapi import APIRouter, Header, HTTPException

from ..core import opsauth
from ..core import phase as phase_mod


def make_router(db):
    router = APIRouter(prefix="/api/owner/phase")

    def call(fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except opsauth.OpsAuthUnavailable as exc:
            raise HTTPException(503, str(exc)) from exc
        except opsauth.OpsAuthRefused as exc:
            raise HTTPException(403, str(exc)) from exc
        except (ValueError, KeyError, TypeError) as exc:
            raise HTTPException(409, str(exc)) from exc

    @router.get("")
    def current(authorization: str = Header(default="")):
        call(opsauth.check, authorization)
        r = phase_mod.resolve(db)
        return {**r, "history": phase_mod.history(db, limit=20)}

    @router.post("/transition")
    def transition(body: dict, authorization: str = Header(default="")):
        return call(phase_mod.record_transition, db, authorization=authorization,
                    to=body.get("to"), reason=body.get("reason"),
                    evidence_refs=body.get("evidence_refs"))
    return router
