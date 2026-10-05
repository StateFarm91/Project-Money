"""Storefront and Search Visibility routes (F-239/F-293, F-248).

`POST /api/search-visibility` is the owner's intake for the Search Visibility page, guarded
by the operator credential like every other write (503 with no token configured, 401 on a
wrong one). It refuses (409) while there is no live listing, a listing it does not know, or
anything else `commerce.search_visibility` refuses. The two GET routes are aggregate reads:
the lifecycle state and the pre-launch storefront preview. Neither carries customer content.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse

from ..core import opsauth


def make_router(db):
    router = APIRouter()

    @router.post("/api/search-visibility")
    def search_visibility_intake(body: dict, authorization: str = Header(default="")):
        """Record one owner reading of Shop Manager > Marketing > Search Visibility."""
        from ..commerce import search_visibility as sv

        try:
            opsauth.check(authorization)
        except opsauth.OpsAuthUnavailable as e:
            return JSONResponse({"error": str(e)}, status_code=503)
        except opsauth.OpsAuthRefused:
            return JSONResponse({"error": "operator credential required"}, status_code=401)
        try:
            observed = datetime.fromisoformat(str(body.get("observed_at") or ""))
            items = body.get("items")
            if not isinstance(items, list):
                raise sv.SearchVisibilityRefused("items must be a list (empty when the page "
                                                 "lists nothing)")
            if not isinstance(body.get("complete"), bool):
                raise sv.SearchVisibilityRefused(
                    "complete must be true or false: only a complete reading may clear items")
            return sv.record_reading(db, observed_at=observed, items=items,
                                     complete=body["complete"],
                                     note=str(body.get("note") or ""))
        except (sv.SearchVisibilityRefused, ValueError) as e:
            return JSONResponse({"error": str(e)}, status_code=409)

    @router.get("/api/search-visibility")
    def search_visibility_state() -> dict:
        from ..commerce import search_visibility as sv

        return sv.state(db)

    @router.get("/api/storefront/preview")
    def storefront_preview() -> dict:
        """The pre-launch storefront preview, measured. Not the live shop (rendered_pages)."""
        from ..brand import storefront_preview as sp

        return sp.preview(db)

    return router
