"""Authenticated storefront-grant producer (W4-AGENTS); never contacts Etsy or enqueues a job.

The owner reads the Storefront Director's recorded proposals, previews one (the exact change
and its digest) and approves it; the next `store.update` for that proposal may then send it,
in a publishing phase only.
"""
from fastapi import APIRouter, Header, HTTPException

from ..core import opsauth
from ..ops import storefront_authority as authority


def make_router(db):
    router = APIRouter(prefix="/api/owner/storefront")

    def call(fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except opsauth.OpsAuthUnavailable as exc:
            raise HTTPException(503, str(exc)) from exc
        except opsauth.OpsAuthRefused as exc:
            raise HTTPException(403, str(exc)) from exc
        except (ValueError, KeyError, TypeError) as exc:
            raise HTTPException(409, str(exc)) from exc

    @router.post("/proposals")
    def proposals(body: dict | None = None, authorization: str = Header(default="")):
        from ..store_foundation import director

        call(opsauth.check, authorization)
        return {"proposals": director.proposals(db)}

    @router.post("/preview")
    def preview(body: dict, authorization: str = Header(default="")):
        call(opsauth.check, authorization)
        content = call(authority.snapshot, db, body.get("proposal"))
        return {"content": content, "digest": authority.digest(content)}

    @router.post("/approve")
    def approve(body: dict, authorization: str = Header(default="")):
        return call(authority.approve, db, authorization=authorization,
                    proposal=body.get("proposal"), expected_digest=body.get("expected_digest"),
                    reason=body.get("reason"))

    @router.post("/{approval_id}/revoke")
    def revoke(approval_id: int, authorization: str = Header(default="")):
        return call(authority.revoke, db, authorization=authorization, approval_id=approval_id)

    @router.post("/rebase")
    def rebase(body: dict, authorization: str = Header(default="")):
        return call(authority.rebase, db, authorization=authorization,
                    reason=body.get("reason"))
    return router
