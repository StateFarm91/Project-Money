"""Lesson content freshness (F-818) -- W4-C11.

"Agents monitor lessons for stale links, changed terminology, broken media, obsolete products,
new evidence and support-driven gaps. Updates are versioned and regression-checked."

`monitor(db, links=..., media=...)` reads every saved lesson and reports, per lesson:

* `stale_link` -- a link (from `linking.propose`, or the lesson's own `spec.links`) whose
  target is not an approved lesson or a known product;
* `terminology` -- a step whose printed term is no longer what `cir.stitches.term` prints for
  that stitch in the lesson's terminology (the taxonomy is the authority, and it moved);
* `broken_media` -- an asset whose sha256 is not among the bytes the store holds. With no
  media index supplied the check is UNKNOWN, not passed;
* `obsolete_product` -- a product the spec names (`spec.products`) that no longer exists or
  carries a retiring status;
* `rule_regression` -- the saved spec no longer passes `service.validate_spec` (a rule
  tightened after it was approved);
* `new_evidence` -- support cases still arriving on a topic this lesson covers: the lesson
  exists and people are still asking;
* `support_gap` -- a queued gap one graph hop from the lesson's topics that support raised.

`update(db, slug, new_spec)` is the only write: it refuses a spec that fails validation or
whose formats drift (`formats.render` + `formats.drift`), or that still carries a finding of
its own; otherwise it saves through `service.save_lesson`, which gives a new revision and
resets the reviews -- an update is re-reviewed, never inherited.
"""
from __future__ import annotations

RETIRING = frozenset({"retired", "withdrawn", "archived", "delisted"})


def _lesson_findings(spec, *, slug, links, approved_slugs, products, media, gaps,
                     expanded) -> list[dict]:
    from ..cir import stitches
    from .service import validate_spec

    out = []
    t = spec.get("terminology", "US")
    targets = list(links.get(slug, [])) + list(spec.get("links") or [])
    for target in targets:
        key = target["target"] if isinstance(target, dict) else str(target)
        kind, _, name = key.partition(":")
        ok = (kind == "lesson" and name in approved_slugs) or \
             (kind == "pattern" and name in products and products[name] not in RETIRING)
        if not ok:
            out.append({"kind": "stale_link", "target": key})
    for i, step in enumerate(spec.get("steps") or [], 1):
        try:
            now = stitches.term(step.get("stitch"), t)
        except KeyError:
            now = None
        if now != step.get("term"):
            out.append({"kind": "terminology", "step": i, "printed": step.get("term"),
                        "taxonomy": now})
    if media is None:
        out.append({"kind": "broken_media", "state": "UNKNOWN",
                    "why": "no media index supplied; not checked, not passed"})
    else:
        for asset in spec.get("assets") or []:
            if asset.get("sha256") not in media:
                out.append({"kind": "broken_media", "sha256": asset.get("sha256")})
    for p in spec.get("products") or []:
        if p not in products or products[p] in RETIRING:
            out.append({"kind": "obsolete_product", "product": p,
                        "status": products.get(p, "missing")})
    errs = validate_spec(spec)
    if errs:
        out.append({"kind": "rule_regression", "errors": errs})
    topics = set(spec.get("topics") or [])
    for g in gaps:
        support = [e for e in g["evidence"] if isinstance(e, dict) and
                   ("support_case_id" in e or "support_cluster" in e)]
        if not support:
            continue
        if g["topic"] in topics:
            out.append({"kind": "new_evidence", "topic": g["topic"], "support": len(support)})
        elif g["state"] == "QUEUED" and g["topic"] in expanded:
            out.append({"kind": "support_gap", "topic": g["topic"], "support": len(support)})
    return out


def _context(db):
    from sqlalchemy import select

    from ..core.models import Product
    from .models import LearnGap, Lesson
    from .service import eligible

    with db.session() as s:
        lessons = [(r.slug, dict(r.spec or {}), eligible(r))
                   for r in s.scalars(select(Lesson).order_by(Lesson.slug))]
        products = {p.slug: p.status for p in s.scalars(select(Product))}
        gaps = [{"topic": g.topic, "state": g.state, "evidence": list(g.evidence or [])}
                for g in s.scalars(select(LearnGap))]
    return lessons, products, gaps


def monitor(db, *, links: dict | None = None, media=None) -> dict:
    from .service import expand_topics

    lessons, products, gaps = _context(db)
    approved = {slug for slug, _spec, ok in lessons if ok}
    out = {}
    for slug, spec, ok in lessons:
        findings = _lesson_findings(spec, slug=slug, links=links or {},
                                    approved_slugs=approved, products=products,
                                    media=None if media is None else set(media), gaps=gaps,
                                    expanded=expand_topics(db, spec.get("topics") or []))
        out[slug] = {"approved": ok, "findings": findings,
                     "state": ("STALE" if any(f.get("state") != "UNKNOWN" for f in findings)
                               else "UNKNOWN" if findings else "FRESH")}
    return {"lessons": out}


class UpdateRefused(ValueError):
    pass


def update(db, slug: str, new_spec: dict, *, media=None) -> dict:
    from . import formats as F
    from .service import save_lesson, validate_spec

    errs = validate_spec(new_spec)
    if errs:
        raise UpdateRefused("; ".join(errs))
    drifted = {}
    for fmt in F.FORMATS:
        r = F.render(new_spec, fmt, revision="candidate", slug=slug)
        p = F.drift(new_spec, r.get("checked_text", r["body"]))
        if p:
            drifted[fmt] = p
    if drifted:
        raise UpdateRefused(f"formats drift: {drifted}")
    lessons, products, gaps = _context(db)
    approved = {s for s, _sp, ok in lessons if ok and s != slug}
    own = [f for f in _lesson_findings(new_spec, slug=slug, links={}, approved_slugs=approved,
                                       products=products,
                                       media=None if media is None else set(media), gaps=[],
                                       expanded=set())
           if f.get("state") != "UNKNOWN"]
    if own:
        raise UpdateRefused(f"the update still carries findings: {own}")
    revision = save_lesson(db, slug, new_spec)
    return {"slug": slug, "revision": revision, "state": "DRAFT",
            "why": "a new revision; reviews reset, so the update is re-reviewed"}
