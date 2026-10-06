"""Routes for the Etsy estate and the CX workspace (wave-3 K8: F-514, F-545, F-553, F-568,
F-585, F-592, F-689).

`make_router(db)` follows `app.storefront_api`: every write and every read that carries
customer content goes through the operator credential (`core.opsauth`: 503 with no token
configured, 401 on a wrong or missing one, never echoing either). Aggregate reads stay open
like the rest of the dashboard and carry no buyer's words or reference.

- GET  /api/etsy/surfaces            the inventory, served, plus today's re-verification
- GET  /api/etsy/estate              the latest census estate, delivery, renewals, lifecycle
- GET  /api/etsy/listing-lifecycle   one listing's unified trail (?listing_id=)
- POST /api/etsy/shop-observation    the owner's dated reading of a browser-only page
- GET  /api/etsy/policy-violations   open violation incidents (operator)
- GET  /api/cx/summary               the CX workspace as aggregates
- GET  /api/cx/workspace             the CX workspace per buyer (operator; customer content)
"""
from __future__ import annotations

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse

from ..core import opsauth

CUSTOMER_DATA_ROUTES = frozenset({"/api/cx/workspace"})


def _refusal(authorization: str) -> JSONResponse | None:
    try:
        opsauth.check(authorization)
    except opsauth.OpsAuthUnavailable as e:
        return JSONResponse({"error": str(e)}, status_code=503)
    except opsauth.OpsAuthRefused:
        return JSONResponse({"error": "operator credential required"}, status_code=401)
    return None


def make_router(db):
    router = APIRouter()

    @router.get("/api/etsy/surfaces")
    def surfaces() -> dict:
        from . import surface_inventory

        return {"inventory": surface_inventory.served(),
                "reverification": surface_inventory.summary(db)}

    @router.get("/api/etsy/estate")
    def estate() -> dict:
        from ..runtime.etsy_ops import CENSUS_READING, latest_reading
        from . import listing_lifecycle

        census = latest_reading(db, CENSUS_READING)
        if census is None:
            return {"state": "UNOBSERVED", "why": "no listing census has been read",
                    "lifecycle": listing_lifecycle.summary(db)}
        return {"state": "OBSERVED", "observed_at": census.get("observed_at"),
                "estate": census.get("estate") or [], "delivery": census.get("delivery"),
                "renewals": census.get("renewals"), "drift": census.get("drift"),
                "rollback_plans": census.get("rollback_plans"),
                "lifecycle": listing_lifecycle.summary(db)}

    @router.get("/api/etsy/listing-lifecycle")
    def lifecycle(listing_id: str) -> dict:
        from . import listing_lifecycle

        return {"listing_id": listing_id,
                "events": listing_lifecycle.trail(db, str(listing_id)[:32])}

    @router.post("/api/etsy/shop-observation")
    def shop_observation(body: dict, authorization: str = Header(default="")):
        """Body: {page, observed_at (ISO 8601), complete (bool), values (object), statement}."""
        refused = _refusal(authorization)
        if refused is not None:
            return refused
        from . import shop_observations

        try:
            return shop_observations.record(
                db, page=str(body.get("page") or ""), observed_at=body.get("observed_at"),
                complete=body.get("complete"), values=body.get("values"),
                statement=str(body.get("statement") or ""))
        except shop_observations.ObservationRefused as e:
            return JSONResponse({"error": str(e)[:300]}, status_code=400)

    @router.get("/api/etsy/policy-violations")
    def policy_violations(authorization: str = Header(default="")):
        refused = _refusal(authorization)
        if refused is not None:
            return refused
        from . import policy_violations as pv
        from . import shop_observations

        return {"open": pv.open_items(db),
                "page": shop_observations.latest(db, "policy_violations")["state"]}

    @router.get("/api/cx/summary")
    def cx_summary() -> dict:
        from ..support import workspace

        return workspace.summary(db)

    @router.get("/api/cx/workspace")
    def cx_workspace(customer_ref: str = "", limit: int = 50,
                     authorization: str = Header(default="")):
        refused = _refusal(authorization)
        if refused is not None:
            return refused
        from ..support import workspace

        return workspace.workspace(db, customer_ref=customer_ref or None,
                                   limit=max(1, min(int(limit), 500)))

    return router
