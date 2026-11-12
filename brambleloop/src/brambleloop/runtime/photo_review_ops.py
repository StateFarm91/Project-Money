"""P0-PHOTO-ASSET-REVIEW: the job that runs `publish.photo_asset_review` (asset_truth agent).

Hourly, and enqueued at once by `assets.physical_upgrade` when the photograph leads the
gallery. CA$0, deterministic, no model call, never publishes: it approves a photo frame only
when every stored-record check passes, then re-issues the listing-set certificate.
"""
from __future__ import annotations

from .worker import JobContext, handlers


@handlers.register("assets.photo_review")
def handle_photo_review(ctx: JobContext) -> dict:
    from ..publish import photo_asset_review as par

    frame_id = (ctx.job.inputs or {}).get("frame_id")
    if frame_id is not None:
        r = par.review_frame(ctx.db, int(frame_id))
        return {"reviewed": 1, "approved": int(r["approved"]),
                "refused": [] if r["approved"] else [{"frame_id": frame_id,
                                                      "failed": r["failed"]}],
                "work_done": int(r["approved"])}
    return par.sweep(ctx.db)
