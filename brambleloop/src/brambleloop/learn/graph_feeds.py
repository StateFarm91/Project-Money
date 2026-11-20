"""Three feeds into the Learn knowledge graph (F-815's graph, `learn_nodes`/`learn_edges`).

* **F-807 difficulty ladder** -- prerequisite edges between stitch topics, derived from the
  stitch taxonomy (`cir.stitches`), never typed by hand:
  - a derived stitch requires its base (`dc_inc`, `dc_dec` -> `dc`; `hdc_inc`, `hdc3` ->
    `hdc`; `inc`, `dec` -> `sc`, whose names are "single crochet increase/decrease"; front-
    and back-post stitches -> `dc`; the star-stitch family -> `star_st`);
  - the height ladder `sc -> hdc -> dc -> tr`: each taller basic stitch is taught after the
    one below it (a teaching convention, recorded as such in the edge's evidence);
  - every worked stitch requires `ch` (the foundation chain).
  Edges point from the advanced topic to its prerequisite, which is the direction
  `service.expand_topics` follows, so help for `dc_inc` also links the `dc` lesson.
  `ladder(db, topic)` returns the transitive prerequisites, most basic first.
* **F-803 search-to-lesson** -- SEO keyword phrases (`keywords`) naming a stitch in US or UK
  terms become `search:<id>` sources with `needs_help` edges, and the topic's gap is queued
  unless an approved lesson covers it -- searchers' vocabulary reaches the Learn queue.
* **F-830 education compounds** -- each resolved support case with a specialist label is a
  `solved` edge into a shared `faq:<label>` node that counts solved cases and the products
  they came from, so one answer is reusable across products.
Idempotent: edges are keyed by content; re-running adds nothing.
"""
from __future__ import annotations

import re

from sqlalchemy import select

LADDER = ("sc", "hdc", "dc", "tr")
_DERIVED = {"dc_inc": "dc", "dc_dec": "dc", "hdc_inc": "hdc", "hdc3": "hdc", "inc": "sc",
            "dec": "sc", "fpdc": "dc", "bpdc": "dc", "beg_star_st": "star_st",
            "end_star_st": "star_st"}
_NO_CHAIN = {"ch", "sk", "slst"}


def prerequisite_edges() -> list[tuple[str, str, dict]]:
    from ..cir import stitches

    codes = sorted(stitches._STITCHES)
    out = []
    for code, base in _DERIVED.items():
        if code in codes and base in codes:
            out.append((code, base, {"rule": "derived stitch requires its base",
                                     "basis": "cir.stitches names and semantics"}))
    for lo, hi in zip(LADDER, LADDER[1:]):
        out.append((hi, lo, {"rule": "height ladder", "basis": "teaching convention"}))
    for code in codes:
        if code not in _NO_CHAIN and not code.startswith("cable"):
            out.append((code, "ch", {"rule": "worked into a foundation chain",
                                     "basis": "foundation chain"}))
    return out


def seed_prerequisites(db) -> int:
    from . import service

    n = 0
    for adv, base, ev in prerequisite_edges():
        service.link_topics(db, f"stitch:{adv}", f"stitch:{base}", "prerequisite", ev)
        n += 1
    return n


def ladder(db, topic: str) -> list[str]:
    """Transitive prerequisites of a topic, most basic first (a learning path)."""
    from .models import LearnEdge

    with db.session() as s:
        edges = [(e.source, e.target) for e in s.scalars(
            select(LearnEdge).where(LearnEdge.relation == "prerequisite"))]
    succ: dict[str, list[str]] = {}
    for a, b in edges:
        succ.setdefault(a, []).append(b)
    order: list[str] = []

    def visit(n, stack=()):
        for m in sorted(succ.get(n, [])):
            if m in stack:
                raise ValueError(f"prerequisite cycle through {m}")
            visit(m, stack + (m,))
            if m not in order:
                order.append(m)

    visit(topic)
    return order


def _names() -> list[tuple[str, str]]:
    from ..cir import stitches

    out = []
    for code, st in stitches._STITCHES.items():
        for name in {st.name_us, st.name_uk, code}:
            if len(name) >= 2:
                out.append((name.lower(), code))
    return sorted(out, key=lambda x: -len(x[0]))       # longest name wins


def search_demand(db) -> dict:
    from ..core.models import Keyword
    from .models import LearnEdge, LearnGap, LearnNode
    from .service import digest, eligible
    from .models import Lesson

    names = _names()
    found = 0
    with db.session() as s:
        approved = set()
        for lesson in s.scalars(select(Lesson)).all():
            if eligible(lesson):
                approved.update(lesson.spec["topics"])
        for kw in s.scalars(select(Keyword)).all():
            phrase = f" {re.sub(r'[^a-z0-9 ]+', ' ', (kw.phrase or '').lower())} "
            matched = next((name for name, _c in names if f" {name} " in phrase), None)
            if matched is None:
                continue
            # "double crochet" is the US dc and the UK sc: an ambiguous name queues both,
            # and says so, rather than guessing which terminology the searcher used.
            codes = sorted({c for name, c in names if name == matched})
            source = f"search:{kw.id}"
            ev = {"keyword_id": kw.id, "phrase": kw.phrase, "intent": kw.intent,
                  "matched": matched, "ambiguous_us_uk": len(codes) > 1}
            s.merge(LearnNode(key=source, kind="search", detail=ev))
            for hit in codes:
                topic = f"stitch:{hit}"
                s.merge(LearnNode(key=topic, kind="stitch", detail={}))
                s.merge(LearnEdge(key=digest([source, topic]), source=source, target=topic,
                                  relation="needs_help", evidence=ev))
                gap = s.get(LearnGap, topic)
                if gap is None:
                    gap = LearnGap(topic=topic, state="QUEUED", owner="learn", evidence=[])
                    s.add(gap)
                if ev not in gap.evidence:
                    gap.evidence = [*gap.evidence, ev]
                gap.state = "COVERED" if topic in approved else "QUEUED"
            found += 1
    return {"search_sources": found}


def solved_questions(db) -> dict:
    from ..core.models import SupportCase
    from .models import LearnEdge, LearnNode
    from .service import digest

    faq: dict[str, dict] = {}
    with db.session() as s:
        for c in s.scalars(select(SupportCase).where(SupportCase.resolved == True)):  # noqa: E712
            if not c.specialist:
                continue
            node = f"faq:{c.specialist}"
            f = faq.setdefault(node, {"solved": 0, "products": set()})
            f["solved"] += 1
            if c.product_slug:
                f["products"].add(c.product_slug)
            s.merge(LearnEdge(key=digest([f"support:{c.id}", node, "solved"]),
                              source=f"support:{c.id}", target=node, relation="solved",
                              evidence={"support_case_id": c.id,
                                        "product_slug": c.product_slug}))
        for node, f in faq.items():
            s.merge(LearnNode(key=node, kind="faq",
                              detail={"solved": f["solved"],
                                      "products": sorted(f["products"]),
                                      "reusable_across_products": len(f["products"]) > 1}))
    return {"faq_nodes": len(faq), "solved": sum(f["solved"] for f in faq.values())}


def run(db) -> dict:
    return {"prerequisites": seed_prerequisites(db), **search_demand(db),
            **solved_questions(db)}
