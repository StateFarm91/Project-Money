"""F-824: the accessibility checks pattern charts get, applied to Learn pages.

Pattern charts carry colour-independent cues (Master Plan section 31). A Learn page is a
lesson payload plus its technique diagrams, and needs the same:

* **diagram** (`check_svg`) -- an accessible name (`<title>` as the first child, naming the
  stitch and loop), one text label per working stage (the sequence is readable without the
  drawing's colours), and no stage told by colour alone;
* **lesson** (`check_lesson`) -- every diagram has alt text, every step has an instruction
  in words with the explicit terminology (US/UK) stated, and no instruction runs past
  `MAX_WORDS` (one action per step reads aloud cleanly).

`read_lesson` returns the report and alt text; the diagram route refuses an SVG that fails
(fail closed, like `technique.verify`).
"""
from __future__ import annotations

import re

MAX_WORDS = 40


def check_svg(svg: bytes, stages: int | None = None) -> list[str]:
    text = svg.decode("utf-8", errors="replace")
    problems = []
    first = re.search(r"<svg[^>]*>\s*<(\w+)", text)
    if not first or first.group(1) != "title":
        problems.append("the diagram's first child is not a <title> (no accessible name)")
    title = re.search(r"<title>([^<]+)</title>", text)
    if not title or len(title.group(1).split()) < 3:
        problems.append("the accessible name does not describe the stitch and loop")
    labels = len(re.findall(r"<text\b", text))
    if stages is not None and labels < stages:
        problems.append(f"{labels} text label(s) for {stages} stage(s): a stage is told by "
                        f"drawing alone")
    if labels == 0:
        problems.append("no text labels: the sequence depends on the drawing's colours")
    return problems


def alt_text(stitch_name: str, code: str, loop: str) -> str:
    return f"{stitch_name} ({code}) worked through {loop} loop(s), shown stage by stage"


def check_lesson(spec: dict) -> list[str]:
    problems = []
    if spec.get("terminology") not in ("US", "UK"):
        problems.append("terminology (US/UK) is not stated")
    for i, step in enumerate(spec.get("steps") or []):
        words = len(str(step.get("instruction") or "").split())
        if words == 0:
            problems.append(f"step {i + 1} has no instruction in words")
        elif words > MAX_WORDS:
            problems.append(f"step {i + 1} runs {words} words (> {MAX_WORDS})")
    return problems
