"""F-421 (search strategy), F-422 (terminology discovery), F-423 (cross-domain transfer).

A research task's internal search used to be one pass over its literal query terms. A
question asked in US crochet terms found nothing filed in UK terms, a question about
"gauge" never met the knitting or textile literature that calls it "tension" or "stitch
density", and a search that found nothing simply stopped. This is the iterative strategy:

1. **exact** -- the task's own terms (what `open_question` already ran);
2. **terminology** -- each term swapped for its known equivalents (`GLOSSARY`: US/UK crochet
   names and trade synonyms), plus terms *discovered* from the evidence round 1 found: words
   that recur across the hits and are not in the query (F-422);
3. **broadened** -- the most specific term dropped, so a three-term AND that matched nothing
   becomes a two-term search;
4. **cross-domain** -- the same idea in adjacent fields (`BRIDGES`: knitting, weaving,
   textile engineering, sewing/garment grading, toy safety) (F-423).

Rounds stop as soon as `need` distinct pieces of evidence are held. Every round is recorded
on the task (`detail.search_rounds`: terms, hits, new refs, why it ran), and new evidence is
merged into `internal_evidence` with the round that found it. Internal corpora only; no
network, no spend.
"""
from __future__ import annotations

import re
from collections import Counter

GLOSSARY: dict[str, tuple[str, ...]] = {
    "single crochet": ("double crochet uk", "sc", "dc uk"),
    "double crochet": ("treble crochet uk", "dc", "tr uk"),
    "half double crochet": ("half treble uk", "hdc", "htr"),
    "treble crochet": ("double treble uk", "tr", "dtr uk"),
    "slip stitch": ("sl st", "ss"),
    "gauge": ("tension",),
    "tension": ("gauge",),
    "skein": ("ball", "hank"),
    "amigurumi": ("crochet toy", "stuffed toy"),
    "granny square": ("motif", "afghan square"),
    "magic ring": ("magic loop", "adjustable ring"),
    "colorwork": ("colourwork", "tapestry crochet", "mosaic crochet"),
    "colourwork": ("colorwork", "tapestry crochet"),
    "blanket": ("afghan", "throw"),
    "afghan": ("blanket", "throw"),
    "worsted": ("aran", "10 ply"),
    "dk": ("light worsted", "8 ply"),
    "frog": ("rip out", "unravel"),
    "listing": ("product page",),
    "conversion": ("sales rate",),
}

BRIDGES: dict[str, tuple[tuple[str, str], ...]] = {
    "gauge": (("knitting", "stitch gauge"), ("textile engineering", "stitch density")),
    "tension": (("knitting", "knitting tension"), ("textile engineering", "yarn tension")),
    "grading": (("sewing", "pattern grading"), ("garment", "size grading")),
    "sizing": (("sewing", "size chart"), ("garment", "ease")),
    "drape": (("textile engineering", "fabric drape"), ("weaving", "hand")),
    "colorwork": (("knitting", "fair isle"), ("weaving", "jacquard")),
    "colourwork": (("knitting", "fair isle"), ("weaving", "jacquard")),
    "amigurumi": (("toy safety", "small parts"), ("toy safety", "stuffing")),
    "shrinkage": (("textile engineering", "relaxation shrinkage"), ("laundering", "felting")),
    "blocking": (("knitting", "wet blocking"), ("textile finishing", "steaming")),
    "pattern": (("sewing", "sewing pattern"), ("knitting", "chart")),
}

ROUNDS = ("exact", "terminology", "broadened", "cross_domain")
_WORD = re.compile(r"[a-z][a-z\-]{3,}")
_STOP = frozenset("this that with from have were been their there which about after into "
                  "they them than then what when where while would could should also only "
                  "more most other such over under very each some none".split())


def equivalents(term: str, extra: dict | None = None) -> tuple[str, ...]:
    key = term.strip().lower()
    return tuple(dict.fromkeys((*GLOSSARY.get(key, ()), *(extra or {}).get(key, ()))))


def discover_terms(hits: list[dict], query: list[str], *, limit: int = 4) -> list[str]:
    """Words recurring in at least two hits that the query did not use (F-422)."""
    have = {w for t in query for w in t.lower().split()}
    seen: Counter = Counter()
    for h in hits:
        seen.update(set(_WORD.findall(str(h.get("text") or "").lower())))
    ranked = sorted(seen.items(), key=lambda kv: (-kv[1], kv[0]))   # reproducible (F-424)
    return [w for w, n in ranked if n >= 2 and w not in have and w not in _STOP][:limit]


def bridges(terms: list[str]) -> list[tuple[str, str]]:
    out = []
    for t in terms:
        for b in BRIDGES.get(t.strip().lower(), ()):
            if b not in out:
                out.append(b)
    return out


def plan(terms: list[str], round1_hits: list[dict], extra: dict | None = None) -> list[dict]:
    """The term sets each later round searches, with why. `extra`: owner-supplied terms."""
    steps: list[dict] = []
    for i, t in enumerate(terms):
        for eq in equivalents(t, extra):
            steps.append({"round": "terminology", "terms": terms[:i] + [eq] + terms[i + 1:],
                          "why": f"{t!r} is also called {eq!r}"})
    for w in discover_terms(round1_hits, terms):
        steps.append({"round": "terminology", "terms": [w] + terms[:1],
                      "why": f"{w!r} recurs in the evidence already found"})
    if len(terms) > 1:
        drop = max(terms, key=len)
        steps.append({"round": "broadened", "terms": [t for t in terms if t != drop],
                      "why": f"dropped the most specific term {drop!r}"})
    for field, term in bridges(terms):
        steps.append({"round": "cross_domain", "terms": [term],
                      "why": f"the same idea in {field}: {term!r}"})
    return steps


def run(db, task_id: int, *, need: int = 3, max_searches: int = 12) -> dict:
    from sqlalchemy import select  # noqa: F401

    from . import research

    with db.session() as s:
        row = s.get(research.ResearchTask, task_id)
        if row is None:
            raise research.ResearchRefused(f"no research task {task_id}")
        terms = list(row.query_terms or [])
        held = list(row.internal_evidence or [])
    refs = {h["ref"] for h in held}
    rounds = [{"round": "exact", "terms": terms, "hits": len(held), "new": len(held),
               "why": "the task's own terms (searched when it opened)"}]
    searches = 0
    try:
        from .owner_evidence import owner_terms

        extra = owner_terms(db)          # F-448: the owner's vocabulary joins the glossary
    except Exception:  # noqa: BLE001 - an unreadable owner glossary leaves the built-in one
        extra = {}
    for step in plan(terms, held, extra):
        if len(refs) >= need or searches >= max_searches:
            break
        found, _ = research.search_internal_report(db, step["terms"])
        searches += 1
        new = [h for h in found if h["ref"] not in refs]
        for h in new:
            refs.add(h["ref"])
            held.append({**h, "found_by": step["round"], "found_with": step["terms"]})
        rounds.append({**step, "hits": len(found), "new": len(new)})
    stopped = ("enough evidence" if len(refs) >= need else
               "search budget spent" if searches >= max_searches else "strategy exhausted")
    with db.session() as s:
        row = s.get(research.ResearchTask, task_id)
        row.internal_evidence = held
        d = dict(row.detail or {})
        d["search_rounds"] = rounds
        d["search_stopped"] = stopped
        row.detail = d
    return {"task": task_id, "evidence": len(refs), "rounds": rounds, "stopped": stopped}
