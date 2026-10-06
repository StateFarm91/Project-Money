"""Owner-only phase-transition route (F-299), with the launch verdict and visibility view.

Records the sealed PhaseTransition that, together with `BRAMBLELOOP_PHASE`, decides the
effective runtime phase (`core.phase`). It never edits the deployment environment: a recorded
move up has no effect until the environment agrees, and an environment change alone has no
effect until a transition is recorded.

K4: a move up is refused unless the launch readiness verdict, evaluated at transition time,
is ready (F-300; `core.phase.record_transition`). `GET /api/owner/phase/verdict` shows that
same verdict for the next step up without recording anything, and
`GET /api/owner/phase/visibility` serves the owner visibility view (F-287,
`launch.visibility.view`). Both are owner-credential reads, like `GET /api/owner/phase`.
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

    @router.get("/verdict")
    def verdict(authorization: str = Header(default="")):
        """The F-300 verdict a move to the next phase up would be judged on, evaluated now."""
        call(opsauth.check, authorization)
        rec = phase_mod.latest_recorded(db)
        here = rec["phase"] if rec["recorded"] and rec["valid"] else phase_mod.DEFAULT
        if phase_mod.rank(here) + 1 >= len(phase_mod.ORDER):
            return {"recorded_phase": here, "next": None,
                    "why": "already at the highest phase"}
        nxt = phase_mod.ORDER[phase_mod.rank(here) + 1]
        try:
            v = phase_mod.live_readiness(db, nxt)
        except Exception as exc:  # noqa: BLE001 - unreadable is not ready
            v = {"ready": False, "failing": [f"unevaluable: {type(exc).__name__}"]}
        return {"recorded_phase": here, "next": nxt, "verdict": v,
                "rule": "a move up is recorded only when this verdict is ready (F-300)"}

    @router.get("/visibility")
    def visibility(authorization: str = Header(default="")):
        call(opsauth.check, authorization)
        from ..launch import visibility as vis

        return vis.view(db)
    return router
