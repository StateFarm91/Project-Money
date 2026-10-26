"""F-814: a product's content constellation, Learn members included, each with a reason.

`growth.content` drafts and holds a product's listing-adjacent pieces (article, pins, video,
email, teaser, cross-sell, CAL). The constellation the Final Master asks for also carries the
teaching around the product -- lessons for the techniques its pattern needs, gauge help, the
FAQ answers buyers of it needed, and internal links between them -- and filters every member by
value. `constellation(db, slug)` composes them, read-only:

* `content` -- the product's held content pieces (a member because it was drafted);
* `lessons` -- approved lessons for the pattern's topics, widened by the knowledge graph
  (`learn.service.help_links`; approval revalidated, never trusted by label);
* `gauge_help` -- the lesson(s) covering `technique:gauge`, when the pattern needs gauge;
* `faq` -- `faq:<label>` nodes with solved support cases for this product (`learn.graph_feeds`);
* `internal_links` -- article -> each lesson and FAQ member (what a published article links);
* `filtered_out` -- topics the pattern needs with no approved lesson, named rather than linked
  to nothing (they are the Learn queue's gaps).
"""
from __future__ import annotations

from sqlalchemy import select


def constellation(db, slug: str) -> dict:
    from ..core.models import ContentPiece, PatternVersion, Product
    from ..learn import service
    from ..learn.models import LearnNode

    with db.session() as s:
        product = s.scalar(select(Product).where(Product.slug == slug))
        if product is None:
            raise KeyError(slug)
        pv = s.scalar(select(PatternVersion).where(PatternVersion.product_id == product.id)
                      .order_by(PatternVersion.id.desc()).limit(1))
        cir = pv.cir_json if pv is not None else None
        pieces = [{"channel": p.channel, "title": p.title, "scheduled_for": p.scheduled_for}
                  for p in s.scalars(select(ContentPiece).where(ContentPiece.product_slug == slug))]
        faq = [{"node": n.key, "solved": n.detail.get("solved")}
               for n in s.scalars(select(LearnNode).where(LearnNode.kind == "faq"))
               if slug in (n.detail or {}).get("products", [])]
    needs = service.pattern_topics(cir) if cir is not None else set()
    lessons = service.help_links(db, needs) if needs else []
    covered = {t for le in lessons for t in le["topics"]}
    gauge = [le for le in lessons if "technique:gauge" in le["topics"]]
    article = next((p for p in pieces if p["channel"] == "article"), None)
    links = ([{"from": f"article:{article['title']}", "to": le["href"]} for le in lessons]
             + [{"from": f"article:{article['title']}", "to": f["node"]} for f in faq]
             if article else [])
    return {"slug": slug, "pattern_version": pv.version if pv is not None else None,
            "content": pieces, "lessons": lessons, "gauge_help": gauge, "faq": faq,
            "internal_links": links,
            "filtered_out": sorted(needs - covered),
            "basis": "members only where a reason exists: drafted, approved, or solved"}
