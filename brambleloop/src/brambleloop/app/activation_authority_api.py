"""Authenticated activation approval producer; never contacts Etsy or enqueues activation."""
from fastapi import APIRouter, Header, HTTPException
from ..core import opsauth
from ..ops import activation_authority as authority


def make_router(db):
    router = APIRouter(prefix="/api/owner/activation")

    def call(fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except opsauth.OpsAuthUnavailable as exc:
            raise HTTPException(503, str(exc)) from exc
        except opsauth.OpsAuthRefused as exc:
            raise HTTPException(403, str(exc)) from exc
        except (ValueError, KeyError, TypeError) as exc:
            raise HTTPException(409, str(exc)) from exc

    @router.post("/preview")
    def preview(body: dict, authorization: str = Header(default="")):
        call(opsauth.check, authorization)
        content = call(authority.snapshot, db, body.get("slug"), body.get("version"), body.get("release", ""))
        return {"content": content, "digest": authority.digest(content)}

    @router.post("/approve")
    def approve(body: dict, authorization: str = Header(default="")):
        return call(authority.approve, db, authorization=authorization,
                    slug=body.get("slug"), version=body.get("version"),
                    release=body.get("release", ""), expected_digest=body.get("expected_digest"),
                    reason=body.get("reason"))

    @router.post("/{approval_id}/revoke")
    def revoke(approval_id: int, authorization: str = Header(default="")):
        return call(authority.revoke, db, authorization=authorization, approval_id=approval_id)
    return router
