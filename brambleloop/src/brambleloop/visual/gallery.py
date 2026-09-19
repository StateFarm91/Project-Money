"""Visual commerce QA: the separation that keeps a gallery both honest and persuasive.

Requirements 77, 78, 79, 80, 81. The insight #78 turns on is that a gallery does two different
jobs and one frame cannot do both well. The hero creates desire and comprehension; the later
frames substantiate the purchase. A gallery of only evidence frames is a specification sheet
nobody clicks, and a gallery of only dream frames is a listing that converts and then refunds.

So frames carry a declared job, and the QA differs by job:

- **Conversion creative** is judged on whether it works at grid size and whether it could be
  mistaken for a photograph of a thing that does not exist.
- **Engineering evidence** is judged on whether it agrees with the twin — dimensions,
  materials, stitch counts, file contents.

The rule that ties them together is #77: the standard does not drop because an asset was
AI-assisted. If the available generator cannot reach the bar while staying truthful, the
answer is a different tool, a different composition or a physical sample — never a lower bar
with an apology in the alt text. #81 makes that an ordered ladder rather than a sentiment, and
the last rung is holding the listing.
"""
from __future__ import annotations

from dataclasses import dataclass

CONVERSION = "conversion_creative"
EVIDENCE = "engineering_evidence"

JOBS: dict[str, str] = {
    "hero": CONVERSION,
    "fit": CONVERSION,
    "lifestyle": CONVERSION,
    "scale": EVIDENCE,
    "detail": EVIDENCE,
    "construction": EVIDENCE,
    "evidence": EVIDENCE,
    "chart": EVIDENCE,
}

# Minimum readable size in a mobile search grid. Etsy's grid thumbnail is around this, and it
# is where the buying decision starts.
GRID_PX = 170

# Physical-realism failures (#79). Each is a specific artefact that says "generated" to a
# maker instantly, which is worse than an obviously illustrated image.
REALISM_CHECKS: tuple[str, ...] = (
    "stitch_scale_plausible", "yarn_continuity", "edge_construction", "drape",
    "joins_make_sense", "hands_and_fingers", "garment_fit", "shadows_consistent",
    "texture_not_repeating", "no_impossible_seams",
)

# The escalation ladder (#81), in order. Lowering the standard is not on it.
ESCALATION: tuple[tuple[str, str], ...] = (
    ("regenerate_constrained", "same tool, tighter brief"),
    ("change_composition", "different angle, crop or environment"),
    ("change_tool", "a different permitted image model"),
    ("deterministic_representation", "a chart or twin render, which is always truthful"),
    ("acquire_physical_proof", "a tester photograph of the real object"),
    ("hold_listing", "do not publish"),
)


class GalleryRefused(ValueError):
    """A frame that cannot do the job it was given."""


@dataclass
class Frame:
    role: str
    position: int
    readable_at_grid: bool | None = None
    realism: dict = None
    agrees_with_twin: bool | None = None
    disclosed_as_illustration: bool = False
    generated: bool = False

    def __post_init__(self) -> None:
        if self.role not in JOBS:
            raise GalleryRefused(
                f"{self.role!r} has no declared job. A frame with no job is filler, and #80 "
                f"asks for minimum quality rather than minimum count")
        self.realism = self.realism or {}

    @property
    def job(self) -> str:
        return JOBS[self.role]


def check_frame(frame: Frame) -> list[dict]:
    """Judge one frame by the job it was given, not by a single blended standard."""
    findings: list[dict] = []

    if frame.job == CONVERSION:
        if frame.readable_at_grid is False:
            findings.append({"frame": frame.role, "check": "grid_readability",
                             "problem": (f"does not read at {GRID_PX}px, which is where the "
                                         f"buying decision starts")})
        elif frame.readable_at_grid is None:
            findings.append({"frame": frame.role, "check": "grid_readability",
                             "problem": "nobody has judged whether it reads at grid size",
                             "unjudged": True})
        if frame.generated and not frame.disclosed_as_illustration:
            findings.append({"frame": frame.role, "check": "asset_truth",
                             "problem": ("a generated image presented as a photograph of a "
                                         "finished object nobody has made")})
        failed_realism = [k for k in REALISM_CHECKS if frame.realism.get(k) is False]
        if failed_realism:
            findings.append({"frame": frame.role, "check": "physical_realism",
                             "problem": (f"{failed_realism} — artefacts a maker sees "
                                         f"instantly, which is worse than an obviously "
                                         f"illustrated image")})
        unjudged_realism = [k for k in REALISM_CHECKS if k not in frame.realism]
        if frame.generated and unjudged_realism:
            findings.append({"frame": frame.role, "check": "physical_realism",
                             "problem": f"{len(unjudged_realism)} realism checks unmade",
                             "unjudged": True})
    else:
        if frame.agrees_with_twin is False:
            findings.append({"frame": frame.role, "check": "twin_agreement",
                             "problem": ("an evidence frame that disagrees with the twin is "
                                         "evidence for the wrong product")})
        elif frame.agrees_with_twin is None:
            findings.append({"frame": frame.role, "check": "twin_agreement",
                             "problem": "not checked against the twin", "unjudged": True})
    return findings


def check_gallery(frames: list[Frame]) -> dict:
    """The gallery as a whole: does it do both jobs, and is any frame filler? (#78, #80)"""
    if not frames:
        return {"ok": False, "problems": [{"check": "empty", "problem": "no frames"}],
                "jobs": {}}

    ordered = sorted(frames, key=lambda f: f.position)
    jobs = {CONVERSION: [f.role for f in ordered if f.job == CONVERSION],
            EVIDENCE: [f.role for f in ordered if f.job == EVIDENCE]}

    problems: list[dict] = []
    for frame in ordered:
        problems.extend(check_frame(frame))

    if not jobs[CONVERSION]:
        problems.append({"check": "hero_dream",
                         "problem": ("every frame is evidence: a specification sheet nobody "
                                     "clicks (#78)")})
    if not jobs[EVIDENCE]:
        problems.append({"check": "evidence_proof",
                         "problem": ("every frame is creative: a listing that converts and "
                                     "then refunds (#78)")})
    if ordered[0].job != CONVERSION:
        problems.append({"check": "hero_position",
                         "problem": ("the first frame is evidence. Desire and comprehension "
                                     "come first, substantiation second (#78)")})

    blocking = [p for p in problems if not p.get("unjudged")]
    unjudged = [p for p in problems if p.get("unjudged")]
    return {
        "ok": not blocking and not unjudged,
        "blocking": blocking,
        "unjudged": unjudged,
        "jobs": jobs,
        "frames": len(ordered),
        "note": ("A shorter excellent gallery beats a longer one with filler, so frames are "
                 "judged by the job they were given rather than counted (#80)."),
    }


def escalate(attempt: int) -> dict:
    """The next rung when creative parity fails (#81). Lowering the bar is not a rung.

    Ordered so the cheap fixes come first and the expensive certainty comes last. Holding the
    listing is a real outcome, not a failure of the ladder: a listing held is a listing that
    did not lie.
    """
    if attempt < 0:
        raise GalleryRefused("attempt cannot be negative")
    if attempt >= len(ESCALATION):
        action, why = ESCALATION[-1]
        return {"attempt": attempt, "action": action, "why": why, "exhausted": True,
                "note": ("the ladder is exhausted. #77 is explicit that the standard does "
                         "not drop because an asset was AI-assisted, so the remaining option "
                         "is not to publish")}
    action, why = ESCALATION[attempt]
    return {"attempt": attempt, "action": action, "why": why, "exhausted": False,
            "remaining": [a for a, _ in ESCALATION[attempt + 1:]]}


# ---------------------------------------------------------------------------
# Asset versioning (#80, and stale-asset invalidation)


def stale_assets(assets: list[dict], *, current_release_hash: str) -> list[dict]:
    """Assets rendered from a version the product no longer is.

    An asset is evidence about a specific release. When the release changes, an asset that
    survives is evidence about something that no longer exists — and it is the most
    convincing kind of wrong, because it was true once.
    """
    return [a for a in assets
            if a.get("release_hash") and a["release_hash"] != current_release_hash]
