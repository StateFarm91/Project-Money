"""The listing as a shopper meets it, which is never the listing as it was built.

Requirement 66. Evaluate every listing set the way a shopper actually sees it: the search
thumbnail, the phone gallery, the first three frames, then the full gallery. Store the
renders of those contexts during QA. Optimise the title-safe area and the visual hierarchy
for small screens rather than producing desktop-only output.

`publish.layout_qa` already renders and measures at mobile thumbnail scale, which is the
hardest single context and the reason the blank-hero defect was caught at all. What it does
not do is evaluate the *set* in the order a person meets it, and the order is where this
requirement's value is.

**The decision happens in a context the builder never occupies.** A listing is assembled at
full size, one frame at a time, by somebody who already knows what the product is. It is
chosen at 170 pixels, in a grid of competitors, by somebody who does not. Every check that
runs only at build size is a check run in a context no shopper is ever in.

**The first three frames are a context, not a prefix.** A phone gallery shows three before
anybody scrolls, and most people do not scroll. So those three have to answer the buying
question between them: if all three do the same job, or none of them sells, the listing has
already failed at the only depth most shoppers reach — and the full gallery being excellent
below that is invisible.

**A QA pass with no stored render cannot be re-examined.** The requirement says store them,
and the reason is that "we checked the mobile view" is not a finding anybody can revisit when
a listing underperforms three months later. Every context result carries the reference to
what was actually rendered, and a result without one is `not_rendered` rather than passed.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import eligibility
from .layout_qa import MOBILE_THUMB_PX, SAFE_MARGIN

SEARCH_THUMBNAIL = "search_thumbnail"
PHONE_GALLERY = "phone_gallery"
FIRST_THREE = "first_three_frames"
FULL_GALLERY = "full_gallery"

# In the order a shopper meets them, which is the order that matters.
CONTEXTS: tuple[str, ...] = (SEARCH_THUMBNAIL, PHONE_GALLERY, FIRST_THREE, FULL_GALLERY)

CONTEXT_MEANS: dict[str, dict] = {
    SEARCH_THUMBNAIL: {
        "px": MOBILE_THUMB_PX,
        "frames": 1,
        "why": ("where the decision is made, in a grid of competitors, by somebody who does "
                "not yet know what this is"),
    },
    PHONE_GALLERY: {
        "px": 390,
        "frames": 3,
        "why": "the gallery as it opens on a phone, before anybody scrolls",
    },
    FIRST_THREE: {
        "px": 390,
        "frames": 3,
        "why": ("a context rather than a prefix: most people do not scroll, so these three "
                "answer the buying question or nothing does"),
    },
    FULL_GALLERY: {
        "px": 2000,
        "frames": 0,          # 0 means all of them
        "why": "the listing as it was built, which is the context fewest shoppers reach",
    },
}

# How many frames a phone gallery shows before a scroll. Stated once so that FIRST_THREE and
# PHONE_GALLERY cannot drift apart.
BEFORE_SCROLL = 3

# The band a marketplace overlays its own UI on. Content here is content nobody sees, and it
# is a larger share of a thumbnail than of a full-size frame.
TITLE_SAFE_MARGIN = SAFE_MARGIN * 2

RENDERED = "rendered"
NOT_RENDERED = "not_rendered"


class MobileRefused(ValueError):
    """A context nobody rendered, or a set judged in a context no shopper occupies."""


@dataclass(frozen=True)
class ContextRender:
    """One context, actually rendered, with the artefact that proves it."""

    context: str
    render_ref: str
    frames_shown: int
    px: int
    ink_in_title_safe: float = 0.0

    def __post_init__(self) -> None:
        if self.context not in CONTEXTS:
            raise MobileRefused(f"{self.context!r} is not a context: {list(CONTEXTS)}")
        if not self.render_ref.strip():
            raise MobileRefused(
                f"{self.context}: name the render. 'We checked the mobile view' is not a "
                f"finding anybody can revisit when a listing underperforms three months "
                f"later, which is exactly when somebody wants to")
        if self.frames_shown < 0 or self.px <= 0:
            raise MobileRefused(f"{self.context}: negative frames or a zero-pixel render")

    @property
    def outcome(self) -> str:
        return RENDERED

    def to_dict(self) -> dict:
        return {"context": self.context, "render_ref": self.render_ref,
                "frames_shown": self.frames_shown, "px": self.px,
                "ink_in_title_safe": round(self.ink_in_title_safe, 4),
                "why": CONTEXT_MEANS[self.context]["why"]}


def first_three(frames: list[eligibility.Candidate]) -> dict:
    """Whether the three frames a phone shows first can carry the listing on their own.

    Not a prefix check. Those three are what most shoppers see in total, so the question is
    whether they answer the buying question between them -- and a set whose three best frames
    all do the same job has failed at the only depth most people reach, however good the rest
    of the gallery is.
    """
    ordered = sorted(frames, key=lambda f: f.position)[:BEFORE_SCROLL]
    if not ordered:
        raise MobileRefused("a listing with no frames has no first three")

    jobs = [f.job for f in ordered]
    problems: list[dict] = []

    if eligibility.DESIRE not in jobs:
        problems.append({
            "kind": "nothing_sells", "jobs": jobs,
            "why": (f"none of the first {len(ordered)} frames does "
                    f"{eligibility.DESIRE}. The gallery below this may be excellent and "
                    f"nobody will reach it")})
    if len(set(jobs)) == 1 and len(ordered) > 1:
        problems.append({
            "kind": "all_one_job", "jobs": jobs,
            "why": (f"all {len(ordered)} do {jobs[0]}. Three frames answering one question "
                    f"is one frame, shown three times, in the only context most shoppers "
                    f"occupy")})
    if len(ordered) < BEFORE_SCROLL:
        problems.append({
            "kind": "thin_gallery", "frames": len(ordered),
            "why": (f"{len(ordered)} frame(s) where a phone gallery shows "
                    f"{BEFORE_SCROLL}. Not a defect in itself, and worth seeing: the space "
                    f"is there and empty")})

    return {
        "frames": [f.asset_id for f in ordered], "jobs": jobs,
        "distinct_jobs": len(set(jobs)),
        "problems": problems,
        "ok": not [p for p in problems if p["kind"] != "thin_gallery"],
        "why": ("the first three answer different parts of the buying question, and one of "
                "them sells" if not problems else "; ".join(p["kind"] for p in problems)),
    }


def qa(frames: list[eligibility.Candidate], renders: list[ContextRender]) -> dict:
    """The whole set, in each context, with an unrendered context reported as unrendered."""
    by_context = {r.context: r for r in renders}
    duplicated = sorted({r.context for r in renders
                         if sum(1 for o in renders if o.context == r.context) > 1})
    if duplicated:
        raise MobileRefused(f"{duplicated} rendered twice; two renders of one context means "
                            f"somebody picks which to look at")

    contexts = {}
    for name in CONTEXTS:
        render = by_context.get(name)
        if render is None:
            contexts[name] = {"context": name, "outcome": NOT_RENDERED,
                              "why": CONTEXT_MEANS[name]["why"],
                              "problem": ("not rendered, so nothing is known about this "
                                          "context. Not the same as passing it")}
            continue
        row = render.to_dict()
        row["outcome"] = RENDERED
        if render.ink_in_title_safe > 0:
            row["problem"] = (
                f"{render.ink_in_title_safe:.1%} of the ink sits in the title-safe band, "
                f"where the marketplace overlays its own interface. That content is not "
                f"hard to read; it is not visible")
        contexts[name] = row

    unrendered = [c for c in CONTEXTS if contexts[c]["outcome"] == NOT_RENDERED]
    three = first_three(frames)
    problems = [c for c in CONTEXTS if contexts[c].get("problem")]

    return {
        "contexts": contexts,
        "not_rendered": unrendered,
        "first_three": three,
        "complete": not unrendered,
        "ok": not unrendered and not problems and three["ok"],
        "why": ("every context was rendered and none of them shows a problem"
                if not unrendered and not problems and three["ok"] else
                f"{len(unrendered)} context(s) not rendered; "
                f"{len(problems)} with a problem; first three "
                f"{'ok' if three['ok'] else 'failing'}"),
        "note": ("a listing is assembled at full size by somebody who knows what it is, and "
                 "chosen at 170 pixels by somebody who does not. A check that runs only at "
                 "build size runs in a context no shopper is ever in"),
    }


def state() -> dict:
    """The four contexts, in the order a shopper meets them."""
    return {
        "requirement": 66,
        "contexts": [{"context": c, **CONTEXT_MEANS[c]} for c in CONTEXTS],
        "before_scroll": BEFORE_SCROLL,
        "title_safe_margin": TITLE_SAFE_MARGIN,
        "refuses": [
            "a context result with no stored render, which cannot be re-examined later",
            "two renders of one context, which lets somebody pick",
            "a first three where nothing sells, or where all three do one job",
        ],
        "note": ("the first three frames are a context rather than a prefix: most people do "
                 "not scroll, so those three answer the buying question or nothing does, and "
                 "an excellent gallery below them is invisible"),
    }
