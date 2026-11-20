"""Education SEO (F-817) -- W4-C11.

"Learn pages have independent search briefs, intent classification, title/meta/schema strategy,
FAQ opportunities and update cadence. Search optimization may not distort crochet truth."

`brief(db, slug)` builds one lesson's brief from its approved canonical spec, independent of
any product listing's SEO:

* intent -- how_to / troubleshoot / definition / comparison, by fixed patterns over the
  learner problem (the spec's own words; no model);
* title (at most `TITLE_MAX`) and meta description (at most `META_MAX`) from fixed templates;
* schema -- schema.org `HowTo` with the spec's steps for how-to lessons, `FAQPage` otherwise;
* FAQ opportunities -- recorded searcher phrases (`search:*` nodes, `learn.graph_feeds`) that
  point at a topic this lesson teaches, kept as the searcher wrote them;
* update cadence -- by intent: troubleshooting is revisited soonest because support finds new
  failure modes there.

Truth guard: every string the brief would publish is checked by `formats.drift` (no number or
stitch the spec does not state) and against `UNEARNED` claims ("easiest", "best", "perfect" ...),
which no lesson spec evidences. A brief that fails either is REFUSED, not trimmed.
"""
from __future__ import annotations

import re

from . import formats as F

TITLE_MAX = 60
META_MAX = 155
CADENCE_DAYS = {"troubleshoot": 60, "how_to": 120, "comparison": 120, "definition": 180}
UNEARNED = re.compile(r"\b(easiest|best|ultimate|perfect|fastest|foolproof|guaranteed|"
                      r"#1|number one|never fail)\b", re.I)
_INTENT = (("comparison", re.compile(r"\b(vs|versus|difference between|compared?)\b", re.I)),
           ("troubleshoot", re.compile(r"\b(fix|why|stop|wrong|mistake|uneven|curl\w*|"
                                       r"wav\w*|gaps?|holes?|too (tight|loose))\b", re.I)),
           ("definition", re.compile(r"\b(what is|what are|meaning of)\b", re.I)))


def intent(problem: str) -> str:
    for name, pat in _INTENT:
        if pat.search(problem or ""):
            return name
    return "how_to"


def _clip(text: str, n: int) -> str:
    return text if len(text) <= n else text[:n - 1].rsplit(" ", 1)[0] + "…"


def brief(db, slug: str) -> dict:
    from sqlalchemy import select

    from .models import LearnEdge, LearnNode, Lesson
    from .service import eligible

    with db.session() as s:
        row = s.get(Lesson, slug)
        if row is None or not eligible(row):
            raise PermissionError(f"lesson {slug!r} is not approved")
        spec, revision = dict(row.spec), row.revision
        topics = set(spec.get("topics") or [])
        phrases = []
        for e in s.scalars(select(LearnEdge).where(LearnEdge.relation == "needs_help")):
            if e.source.startswith("search:") and e.target in topics:
                node = s.get(LearnNode, e.source)
                phrase = (node.detail or {}).get("phrase") if node else None
                if phrase and phrase not in phrases:
                    phrases.append(phrase)
    problem = str(spec["learner_problem"]).strip()
    kind = intent(problem)
    a = spec["assumptions"]
    lead = {"how_to": "How to ", "troubleshoot": "Fix it: ", "definition": "",
            "comparison": ""}[kind]
    title = _clip(f"{lead}{problem}", TITLE_MAX)
    n = len(spec["steps"])
    meta = _clip(f"{problem[:1].upper()}{problem[1:]} in {n} steps, with a "
                 f"{F._norm(str(a['hook_mm']))} mm hook and {a['yarn_weight']} yarn "
                 f"({spec.get('terminology', 'US')} terms).", META_MAX)
    steps = [{"@type": "HowToStep", "position": i, "text": st["instruction"]}
             for i, st in enumerate(spec["steps"], 1)]
    schema = ({"@context": "https://schema.org", "@type": "HowTo", "name": title,
               "step": steps} if kind == "how_to" else
              {"@context": "https://schema.org", "@type": "FAQPage",
               "mainEntity": [{"@type": "Question", "name": title,
                               "acceptedAnswer": {"@type": "Answer",
                                                  "text": " ".join(x["text"] for x in steps)}}]})
    published = [title, meta]
    problems = []
    for text in published:
        problems += [f"{text!r}: {p}" for p in F.drift(spec, text)]
        problems += [f"{text!r}: unearned claim {m.group(0)!r}" for m in UNEARNED.finditer(text)]
    out = {"slug": slug, "revision": revision, "intent": kind, "title": title,
           "meta_description": meta, "schema": schema, "faq_opportunities": phrases,
           "update_every_days": CADENCE_DAYS[kind]}
    if problems:
        return {**out, "state": "REFUSED", "problems": problems}
    return {**out, "state": "READY", "problems": []}
