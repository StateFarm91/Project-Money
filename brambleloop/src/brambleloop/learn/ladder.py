"""Free-to-paid content ladder (F-771, F-811) -- W4-C11.

F-771: "Where strategically appropriate, Brambleloop may use a free searchable
article/tutorial as discovery and sell a cleaner premium PDF/package. The free and paid
experiences must be intentionally differentiated rather than accidental duplicates."

F-811: "Educational/free content may lead naturally to premium Brambleloop patterns, bundles
or tools when relevant. The free content must remain genuinely useful and must not become
deceptive teaser content."

`rung(free, paid)` judges one free piece against one paid product:

* `free = {key, lesson_slug, topics, features, steps, cta}` -- the features it delivers
  (`FEATURES`), its teaching steps' text and its calls to action (each `{text, position}`);
* `paid = {slug, topics, features}`.

States, first match wins:

* NOT_RELEVANT -- they share no topic (F-811: "when relevant"; a lesson does not advertise an
  unrelated product);
* DECEPTIVE -- the free piece withholds its own teaching: a step defers to the paid product
  ("buy the pattern for the rest", "unlock", "full instructions in the paid ..."), a step is
  empty, it has no step at all, or a call to action appears before the teaching ends or more
  than `MAX_CTA` times;
* DUPLICATE -- the paid product adds fewer than `MIN_PAID_ONLY` features the free piece does not
  already deliver: selling what is given away is an accident, not a ladder;
* LADDER -- otherwise, with the paid-only features named, which is the differentiation stated.
"""
from __future__ import annotations

import re

FEATURES = ("technique_steps", "full_pattern", "all_sizes", "chart", "printable_pdf",
            "schematic", "row_by_row_counts", "video", "support", "colourways")
MIN_PAID_ONLY = 2
MAX_CTA = 1
_TEASER = re.compile(
    r"\b(buy|purchase|get) (the |our )?(full |paid |premium )?(pattern|pdf|package)\b[^.]{0,40}"
    r"\b(rest|remaining|finish|full|complete)\b"
    r"|\bunlock\b|\b(rest|remainder) of (the )?(steps|instructions|pattern) (is|are) in\b"
    r"|\bfull instructions (are )?(only )?in the (paid|premium)\b", re.I)


def rung(free: dict, paid: dict) -> dict:
    shared = sorted(set(free.get("topics") or ()) & set(paid.get("topics") or ()))
    base = {"free": free.get("key"), "paid": paid.get("slug"), "shared_topics": shared}
    if not shared:
        return {**base, "state": "NOT_RELEVANT",
                "why": "no shared topic: the free piece does not lead to this product"}
    steps = list(free.get("steps") or [])
    problems = []
    if not steps:
        problems.append("the free piece teaches no step")
    for i, text in enumerate(steps, 1):
        if not str(text).strip():
            problems.append(f"step {i} is empty")
        elif _TEASER.search(str(text)):
            problems.append(f"step {i} defers its teaching to the paid product")
    ctas = list(free.get("cta") or [])
    if len(ctas) > MAX_CTA:
        problems.append(f"{len(ctas)} calls to action (at most {MAX_CTA})")
    if any(int(c.get("position", 0)) <= len(steps) for c in ctas):
        problems.append("a call to action interrupts the teaching")
    if problems:
        return {**base, "state": "DECEPTIVE", "problems": problems}
    paid_only = sorted(set(paid.get("features") or ()) - set(free.get("features") or ()))
    unknown = sorted(set(paid.get("features") or ()) - set(FEATURES))
    if unknown:
        raise ValueError(f"unknown features {unknown}; name them in FEATURES")
    if len(paid_only) < MIN_PAID_ONLY:
        return {**base, "state": "DUPLICATE", "paid_only": paid_only,
                "why": f"the paid product adds {len(paid_only)} feature(s) the free piece "
                       f"lacks; a ladder needs {MIN_PAID_ONLY}"}
    return {**base, "state": "LADDER", "paid_only": paid_only,
            "why": "the free piece is complete on its own and the paid product adds "
                   + ", ".join(paid_only)}
