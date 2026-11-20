"""Internal linking engine (F-816) -- W4-C11.

"Automatically propose and test useful links among lessons, patterns and support pages. Links
are based on reader intent and prerequisite/product relevance, not keyword stuffing."

A page is `{key, kind, title, topics, intent}`: `kind` lesson / pattern / support, `intent`
learn / make / troubleshoot. `pages_from_db` reads approved lessons (their canonical
`spec.topics`) and released patterns (`service.pattern_topics` of the CIR).

A link is proposed only for one of four stated reasons, each a fact of the records:

* `prerequisite` -- the target lesson teaches a prerequisite (a recorded `prerequisite` edge,
  one hop) of a topic the source needs and the source does not itself teach;
* `technique_used` -- a pattern links the lessons for techniques it actually uses;
* `apply_it` -- a lesson links patterns that use what it teaches (make intent only: a reader
  who is troubleshooting is not sent to a shop page);
* `answers` -- a support page links the lesson covering its topic.

Shared words in titles are never a reason, so a page called "Easy Double Crochet Blanket" gets
no link to a lesson because both say "double". At most `MAX_LINKS` per page, one per target,
the anchor is the target's own title (no repeated keyword anchors), strongest reason first.

`evaluate` tests a link once it has been shown: at `MIN_IMPRESSIONS` it is KEPT when its
click-through clears `MIN_CTR`, otherwise DROPPED; below that it is UNMEASURED, never 0.
"""
from __future__ import annotations

MAX_LINKS = 5
MIN_IMPRESSIONS = 200
MIN_CTR = 0.01
_RANK = {"prerequisite": 0, "technique_used": 1, "answers": 1, "apply_it": 2}


def pages_from_db(db) -> list[dict]:
    from sqlalchemy import select

    from ..core.models import PatternVersion, Product
    from .models import Lesson
    from .service import eligible, pattern_topics

    pages = []
    with db.session() as s:
        for row in s.scalars(select(Lesson).order_by(Lesson.slug)):
            if eligible(row):
                pages.append({"key": f"lesson:{row.slug}", "kind": "lesson",
                              "title": str(row.spec.get("learner_problem", row.slug)),
                              "topics": sorted(row.spec.get("topics", [])), "intent": "learn"})
        for pv, product in s.execute(select(PatternVersion, Product).join(Product)).all():
            pages.append({"key": f"pattern:{product.slug}", "kind": "pattern",
                          "title": product.title if hasattr(product, "title") else product.slug,
                          "topics": sorted(pattern_topics(pv.cir_json)), "intent": "make"})
    return pages


def _prereqs(db) -> dict[str, set[str]]:
    if db is None:
        return {}
    from sqlalchemy import select

    from .models import LearnEdge

    out: dict[str, set[str]] = {}
    with db.session() as s:
        for e in s.scalars(select(LearnEdge).where(LearnEdge.relation == "prerequisite")):
            out.setdefault(e.source, set()).add(e.target)
    return out


def propose(pages, *, db=None, prerequisites: dict | None = None) -> dict:
    pre = prerequisites if prerequisites is not None else _prereqs(db)
    lessons = [p for p in pages if p["kind"] == "lesson"]
    patterns = [p for p in pages if p["kind"] == "pattern"]
    out = {}
    for src in pages:
        own = set(src.get("topics") or ())
        cands: dict[str, dict] = {}

        def offer(target, reason, via):
            if target["key"] == src["key"]:
                return
            have = cands.get(target["key"])
            if have is None or _RANK[reason] < _RANK[have["reason"]]:
                cands[target["key"]] = {"target": target["key"], "anchor": target["title"],
                                        "reason": reason, "via": sorted(via)}

        for le in lessons:
            teaches = set(le["topics"])
            needed = {p for t in own for p in pre.get(t, ())} - own
            if teaches & needed:
                offer(le, "prerequisite", teaches & needed)
            elif src["kind"] == "pattern" and teaches & own:
                offer(le, "technique_used", teaches & own)
            elif src["kind"] == "support" and teaches & own:
                offer(le, "answers", teaches & own)
        if src["kind"] == "lesson" and src.get("intent") != "troubleshoot":
            for pa in patterns:
                if set(pa["topics"]) & own:
                    offer(pa, "apply_it", set(pa["topics"]) & own)
        ranked = sorted(cands.values(), key=lambda c: (_RANK[c["reason"]], c["target"]))
        out[src["key"]] = [{**c, "state": "PROPOSED"} for c in ranked[:MAX_LINKS]]
    return {"links": out,
            "rule": "a link needs a recorded prerequisite or a shared technique; shared title "
                    "words are never a reason"}


def evaluate(*, impressions: int | None, clicks: int | None) -> dict:
    if impressions is None or clicks is None:
        return {"state": "UNMEASURED", "ctr": None, "why": "not measured"}
    if impressions < MIN_IMPRESSIONS:
        return {"state": "UNMEASURED", "ctr": None,
                "why": f"{impressions} of {MIN_IMPRESSIONS} impressions"}
    ctr = clicks / impressions
    return {"state": "KEEP" if ctr >= MIN_CTR else "DROP", "ctr": round(ctr, 4),
            "why": f"click-through {ctr:.2%} against a {MIN_CTR:.0%} floor"}
