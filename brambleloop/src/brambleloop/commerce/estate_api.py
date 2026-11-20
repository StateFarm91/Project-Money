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

WIRE1 (C12 owner entry). Under `/api/cc/etsy/`, so `security.operator_gate` applies the OWNER
SESSION (cookie, CSRF, nonce) before any handler runs; never the shared operator token. Every
write records the owner's own attestation of a Shop Manager page, so it also needs step-up
(`command_center.auth.require_stepup`) and is audited with the signed-in owner as `by`:
- GET  /api/cc/etsy/search-visibility        three areas (F-560) and finding aging (F-561)
- POST /api/cc/etsy/search-visibility/{item_id}/remediated   a shipped fix (F-517; step-up)
- GET  /api/cc/etsy/listing/{listing_id}/learning-window      F-034 schedule and captures
- POST /api/cc/etsy/listing/{listing_id}/learning-capture     one dated capture (step-up)
- GET  /api/cc/etsy/registers                 apps, Shared Access, partners (F-580/583/588)
- POST /api/cc/etsy/registers/{register}      the owner's reading of that page (step-up)
- POST /api/cc/etsy/dashboard/kpi-snapshot    F-552 snapshot with owner-read views (step-up)
- POST /api/cc/etsy/dashboard/traffic-sources F-562 Stats export (step-up)
"""
from __future__ import annotations

from fastapi import APIRouter, Header, Request
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

        if str(body.get("page") or "") in shop_observations.OWNER_ATTESTED_PAGES:
            # Review F7: the operator credential is shared with automation; an owner's
            # attestation of KYC, tax or the message inbox is not accepted on it.
            return JSONResponse({"error": "this page is the owner's own attestation: record it "
                                          "from the Command Center (owner session + step-up, "
                                          "POST /api/cc/etsy/shop-observation)",
                                 "code": "OWNER_SESSION_REQUIRED"}, status_code=403)
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

    # ---- WIRE1: C12 owner entry (owner session; step-up on every write) ---------------------

    def _cc(request: Request):
        from ..app.command_center import auth

        return auth

    async def _body(request: Request) -> dict:
        auth = _cc(request)
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            raise auth.refuse(db, request, 400, "BAD_REQUEST", "body must be JSON") from None
        if not isinstance(body, dict):
            raise auth.refuse(db, request, 400, "BAD_REQUEST", "body must be a JSON object")
        return body

    def _owner_write(request: Request, action: str, fn, refused: tuple):
        auth = _cc(request)
        auth.require_stepup(db, request, action)
        pid = auth.current_public_id(request)
        try:
            out = fn(f"owner:cc:{pid}")
        except refused as exc:
            raise auth.refuse(db, request, 400, "REFUSED", str(exc)[:300], kind="action",
                              session_public_id=pid) from None
        auth.record(db, kind="action", outcome="ok", request=request, session_public_id=pid,
                    detail={"action": action})
        return JSONResponse(out, status_code=200, headers={"Cache-Control": "no-store"})

    def _date(v):
        from datetime import date

        return date.fromisoformat(str(v or "")[:10])

    def _when(v):
        from datetime import datetime, timezone

        at = datetime.fromisoformat(str(v or ""))
        return at if at.tzinfo else at.replace(tzinfo=timezone.utc)

    @router.get("/api/cc/etsy/search-visibility")
    def cc_search_visibility(request: Request):
        from . import search_visibility as sv

        return JSONResponse({"areas": sv.areas(db), "aging": sv.aging(db, raise_incidents=False)},
                            headers={"Cache-Control": "no-store"})

    @router.post("/api/cc/etsy/search-visibility/{item_id}/remediated")
    async def cc_search_remediated(item_id: int, request: Request):
        from . import search_visibility as sv

        body = await _body(request)
        return _owner_write(request, "etsy.search_visibility.remediated",
                            lambda by: sv.mark_remediated(db, int(item_id),
                                                          ref=str(body.get("ref") or "")[:200]),
                            (sv.SearchVisibilityRefused, ValueError))

    @router.get("/api/cc/etsy/listing/{listing_id}/learning-window")
    def cc_learning_window(listing_id: str, request: Request):
        from . import listing_lifecycle as ll

        return JSONResponse(ll.learning_window(db, str(listing_id)[:32]),
                            headers={"Cache-Control": "no-store"})

    @router.post("/api/cc/etsy/listing/{listing_id}/learning-capture")
    async def cc_learning_capture(listing_id: str, request: Request):
        from . import listing_lifecycle as ll

        body = await _body(request)
        return _owner_write(
            request, "etsy.learning_capture",
            lambda by: ll.record_capture(
                db, str(listing_id)[:32], day=int(body.get("day", -1)),
                source=str(body.get("source") or ""), evidence=str(body.get("evidence") or ""),
                observed_at=_when(body.get("observed_at")),
                values=body.get("values") if isinstance(body.get("values"), dict) else None,
                actor=by),
            (ll.LifecycleRefused, ValueError, TypeError))

    @router.get("/api/cc/etsy/registers")
    def cc_registers(request: Request):
        from . import shop_security as ss

        return JSONResponse({"apps": ss.apps_register(db),
                             "shared_access": ss.shared_access_register(db),
                             "partners": ss.partners_register(db)},
                            headers={"Cache-Control": "no-store"})

    @router.post("/api/cc/etsy/registers/{register}")
    async def cc_register_reading(register: str, request: Request):
        from . import shop_security as ss

        body = await _body(request)
        common = dict(observed_at=body.get("observed_at"), complete=body.get("complete"),
                      statement=str(body.get("statement") or ""))
        items = body.get("items") if isinstance(body.get("items"), list) else []
        record = {"apps": lambda: ss.record_apps(db, apps=items, **common),
                  "shared_access": lambda: ss.record_shared_access(db, members=items, **common),
                  "partners": lambda: ss.record_partners(
                      db, partners=items, source=str(body.get("source") or ""), **common)}
        if register not in record:
            raise _cc(request).refuse(db, request, 404, "NOT_FOUND",
                                      f"no register {register!r}; one of {sorted(record)}")
        return _owner_write(request, f"etsy.register.{register}", lambda by: record[register](),
                            (ss.RegisterRefused, ValueError, TypeError))

    @router.post("/api/cc/etsy/dashboard/kpi-snapshot")
    async def cc_kpi_snapshot(request: Request):
        from ..integrations import etsy_dashboard as ed

        body = await _body(request)
        reading = body.get("owner_reading") if isinstance(body.get("owner_reading"), dict) else None
        return _owner_write(
            request, "etsy.dashboard.kpi_snapshot",
            lambda by: ed.kpi_snapshot(db, start=_date(body.get("start")),
                                       end=_date(body.get("end")), owner_reading=reading,
                                       channel=str(body.get("channel") or "all")[:20]),
            (ed.DashboardRefused, ValueError, TypeError))

    @router.post("/api/cc/etsy/dashboard/traffic-sources")
    async def cc_traffic_sources(request: Request):
        from ..integrations import etsy_dashboard as ed

        body = await _body(request)
        return _owner_write(
            request, "etsy.dashboard.traffic_sources",
            lambda by: ed.record_traffic_sources(
                db, text=str(body.get("text") or "")[:200000], start=_date(body.get("start")),
                end=_date(body.get("end")), exported_on=_date(body.get("exported_on"))),
            (ed.DashboardRefused, ValueError, TypeError))

    return router
