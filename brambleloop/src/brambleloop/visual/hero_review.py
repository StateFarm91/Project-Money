"""The disclosed hero's blind review (F-253 / parity HERO, F-027 / F-031 on the D-FB-7 path).

Parity HERO asks whether "a buyer understands the finished result immediately", and it is
read off a blind description rather than asserted by the brief (`visual.parity`). Photographs
and generated frames get that description from `publish.owned_photography`. A verified
disclosed render -- the image every Launch-0 listing actually carries -- never got one, so
parity HERO stayed unjudged for every Launch-0 product even after `image_vision` opened.

This makes it, and binds it:
* only while the `image_vision` gate is open (otherwise nothing is called, and the reason
  is returned);
* only for a usable disclosed set (structural truth PASS on the bytes);
* the hero's exact stored bytes are described blind (`inspect.describe_image`, one call,
  budgeted) against the hero claim, including the CIR's product families (F-027), and again
  at search-grid size (`inspect.identify_at_grid`, F-031);
* the result is filed with the frame's sha256, and `latest_for` returns it only for those
  bytes, so a re-rendered hero is never judged on an old description.
Nothing here grades realism: a disclosed render says it is not a photograph (D-FB-9).
"""
from __future__ import annotations

ACTION = "visual.hero_review"
HERO_CLAIM = {"shows_finished_object": True}


def review_disclosed_hero(db, slug: str, *, provider=None, store=None,
                          gate_open: bool | None = None) -> dict:
    """Describe the usable disclosed hero of `slug` blind and file the reading."""
    import os

    from ..core.artifacts import ArtifactStore
    from ..core.models import AuditLog
    from ..publish import disclosed_listing
    from ..visual.render_verification import authoritative_cir
    from . import inspect as inspection_mod

    if gate_open is None:
        from .gallery import gates_now

        gate_open = bool(gates_now(db, keys=("image_vision",)).get("image_vision"))
    if not gate_open:
        return {"reviewed": False, "why": "image_vision gate closed: no model has been proven "
                                          "to look at a picture"}
    rec = disclosed_listing.last_asset(db, slug=slug)
    if rec is None or not rec.get("usable_as_listing_asset"):
        return {"reviewed": False, "why": "no usable disclosed set on file for this product"}
    hero = next((f for f in rec.get("frames") or [] if f.get("role") == "hero"), None)
    if hero is None:
        return {"reviewed": False, "why": "the disclosed set has no hero frame"}
    sha = (hero.get("image") or {}).get("sha256")
    cir = authoritative_cir(slug, rec.get("version"))
    families = inspection_mod.product_families(cir)
    st = store if hasattr(store, "get") else ArtifactStore(store or hero.get("artifact_dir")
                                                           or None)
    data = st.get(sha, db=db)
    from ..core import workspace

    # Scoped to the call and removed with it (`core.workspace`; prefix counted by
    # `ops.health.TEMP_PREFIXES`), so a review never leaves a directory behind.
    with workspace.work_dir(None, prefix="hero-review-") as tmp:
        path = os.path.join(tmp, f"{slug}-hero.png")
        with open(path, "wb") as fh:
            fh.write(data)
        got = inspection_mod.describe_image(
            path, db=db, provider=provider,
            claim={**HERO_CLAIM, "identifies_as": families})
        grid = inspection_mod.identify_at_grid(path, families=families, db=db,
                                               provider=provider, work_dir=tmp)
    inspection = {"described": got.get("described"), "description": got.get("description"),
                  "semantic": got.get("semantic"),
                  "description_error": got.get("description_error"),
                  "grid": {k: grid.get(k) for k in ("verdict", "why", "grid_px", "clarity",
                                                     "problems", "families")},
                  "model": got.get("model"), "realism_not_applicable": True}
    # The grid reading joins the semantic one: a hero that is not identifiable at grid size
    # does not let a buyer understand the result "immediately" (F-031).
    sem = dict(inspection.get("semantic") or {})
    if sem and grid.get("verdict") == "blocked":
        sem["identified"] = False
    elif sem and grid.get("verdict") != "clear" and sem.get("identified") is True:
        sem["identified"] = None          # grid reading not made: unjudged, never passed
    if sem:
        inspection["semantic"] = sem
    detail = {"slug": slug, "version": rec.get("version"), "sha256": sha,
              "families": families, "inspection": inspection}
    with db.session() as s:
        s.add(AuditLog(actor="quality_director", action=ACTION,
                       artifact=f"{slug}@{rec.get('version')}", detail=detail))
    return {"reviewed": bool(got.get("described")), **detail}


def latest_for(db, slug: str, sha256: str) -> dict | None:
    """The newest hero review of exactly these bytes, or None."""
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    if not sha256:
        return None
    with db.session() as s:
        for row in s.scalars(select(AuditLog).where(
                AuditLog.action == ACTION,
                AuditLog.artifact.startswith(f"{slug}@", autoescape=True))
                .order_by(desc(AuditLog.id)).limit(20)):
            detail = row.detail or {}
            if detail.get("sha256") == sha256:
                return dict(detail.get("inspection") or {})
    return None
