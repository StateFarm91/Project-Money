"""Pattern video contract (F-813) -- W4-C11.

"When a video supports only a specific size/version, state that explicitly. The written pattern
remains complete enough to stand on its own unless the product explicitly promises otherwise."

Two checks, both deterministic:

* `scope_statement(product, video)` -- the sentence a video must carry when it covers less than
  the product: a subset of the sizes, or a pattern version other than the current one. Its
  sizes and version come from the records, never typed. `check_statement` refuses a video
  description that omits a size it covers or the version it was filmed from.
* `standalone(pattern_text, product)` -- the written pattern may not hand a step to the video
  ("see the video", "watch the video for the rest", "shown in the video"). Allowed only when the
  product explicitly promises a video-led product (`promises_video`), because then the buyer
  was told.

`product = {slug, version, sizes, promises_video}`, `video = {ref, sizes, version}`.
"""
from __future__ import annotations

import re

_DEFERS = re.compile(
    r"\b(see|watch|follow|refer to) (the |our |my )?(video|tutorial video)\b"
    r"|\bshown (only )?in the video\b"
    r"|\bvideo (for|shows) (the )?(rest|details|remaining|instructions|steps)\b"
    r"|\b(instructions|steps) (are )?in the video\b", re.I)


def scope_statement(product: dict, video: dict) -> str | None:
    all_sizes = list(product.get("sizes") or [])
    covered = [s for s in all_sizes if s in set(video.get("sizes") or all_sizes)]
    partial = bool(all_sizes) and len(covered) < len(all_sizes)
    other_version = video.get("version") != product.get("version")
    if not partial and not other_version:
        return None
    parts = []
    if partial:
        parts.append(f"size{'s' if len(covered) != 1 else ''} {', '.join(covered)} only")
    parts.append(f"version {video.get('version')} of the pattern")
    tail = (f"; the current pattern is version {product.get('version')}" if other_version
            else "")
    return f"This video shows {' from '.join(parts)}{tail}."


def check_statement(product: dict, video: dict, description: str) -> list[str]:
    need = scope_statement(product, video)
    if need is None:
        return []
    text = str(description or "")
    problems = []
    for s in video.get("sizes") or []:
        if s in (product.get("sizes") or []) and not re.search(rf"\b{re.escape(s)}\b", text):
            problems.append(f"the video covers size {s} and its description does not say so")
    if len(video.get("sizes") or product.get("sizes") or []) < len(product.get("sizes") or []) \
            and not re.search(r"\bonly\b", text, re.I):
        problems.append("the description does not say the video covers only some sizes")
    if not re.search(rf"\bversion {re.escape(str(video.get('version')))}\b", text):
        problems.append(f"the description does not name version {video.get('version')}")
    return problems


def standalone(pattern_text: str, product: dict) -> dict:
    hits = sorted({m.group(0) for m in _DEFERS.finditer(str(pattern_text or ""))})
    allowed = bool(product.get("promises_video"))
    return {"standalone": not hits or allowed, "defers_to_video": hits,
            "why": ("the product explicitly promises a video-led product" if hits and allowed
                    else "the written pattern hands steps to a video" if hits
                    else "the written pattern stands on its own")}
