"""Owner-only route for the Etsy ledger mapping verification (rc1-ORD2).

Records, revokes and re-anchors the sealed, chained owner verification that the ledger's
type strings and amount unit (`finance.reconcile.mapping_fingerprint`) were confirmed against
a live read. Until one holds, every fee read through the mapping is `unverified_mapping`,
never `measured`. Nothing here contacts Etsy.
"""
from fastapi import APIRouter, Header, HTTPException

from ..core import opsauth
from ..finance import reconcile


def make_router(db):
    router = APIRouter(prefix="/api/owner/ledger-mapping")

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
    def state(authorization: str = Header(default="")):
        call(opsauth.check, authorization)
        return {**reconcile.mapping_state(db),
                "fee_types": sorted(reconcile._FEE_EXACT),
                "refund_types": sorted(reconcile._REFUND_EXACT),
                "divisor": reconcile.LEDGER_AMOUNT_DIVISOR}

    @router.post("/verify")
    def verify(body: dict, authorization: str = Header(default="")):
        return call(reconcile.record_mapping_verification, db, authorization=authorization,
                    by=body.get("by"), evidence=body.get("evidence"))

    @router.post("/{verification_id}/revoke")
    def revoke(verification_id: int, authorization: str = Header(default="")):
        return call(reconcile.revoke_mapping_verification, db, authorization=authorization,
                    verification_id=verification_id)

    @router.post("/rebase")
    def rebase(body: dict, authorization: str = Header(default="")):
        return call(reconcile.rebase_mapping_chain, db, authorization=authorization,
                    reason=body.get("reason"))
    return router
