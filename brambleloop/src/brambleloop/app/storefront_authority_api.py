"""Operator reads of the storefront grant family (W4-AGENTS); never contacts Etsy or enqueues.

Proposals, preview and revoke only (all ops-bearer). Approving and rebasing are owner-session
actions with step-up in the Command Center (`app.command_center.approvals`, M-1).
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

    # W4-AGENTS M-1: there is deliberately no bearer /approve or /rebase. A storefront grant
    # is made only in the owner's Command Center session after a fresh step-up
    # (POST /api/cc/actions/storefront.approve). The bearer may only read and revoke (deny).
    @router.post("/{approval_id}/revoke")
    def revoke(approval_id: int, authorization: str = Header(default="")):
        return call(authority.revoke, db, authorization=authorization, approval_id=approval_id)
    return router
