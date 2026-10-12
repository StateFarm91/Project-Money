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


# What each rung needs before it may be executed, and by whom. The first three generate
# images, which is model spend under the `image_generation` purpose and is never started from
# a gate verdict; physical proof needs an object somebody made (`physical_proof`). The
# deterministic rung needs neither -- a chart or twin render of the certified CIR -- which is
# why it is the one this plan takes by itself.
RUNG_GATES: dict[str, str] = {
    "regenerate_constrained": "image_generation",
    "change_composition": "image_generation",
    "change_tool": "image_generation",
    "deterministic_representation": "",
    "acquire_physical_proof": "physical_proof",
    "hold_listing": "",
}


# How an eligible gated rung is executed once its gate has opened (C-69, #81).
RUNG_EXECUTES_VIA: dict[str, str] = {
    "regenerate_constrained": "the product's photography job, re-run with the failure as a "
                              "constrained brief (it budget-checks and gates itself)",
    "change_composition": "the product's photography job with a changed composition",
    "change_tool": "the product's photography job on another permitted provider",
    "acquire_physical_proof": "the recorded physical test is used as the proof frame's "
                              "evidence",
}


# C-80 defect 8 (Codex P11): the three generation rungs are *different strategies*, not the
# same job three times. Each carries what changes, and the photography job reads it.
GENERATION_RUNGS: tuple[str, ...] = ("regenerate_constrained", "change_composition",
                                     "change_tool")
RUNG_BRIEFS: dict[str, dict] = {
    "regenerate_constrained": {
        "provider": "same",
        "composition": "unchanged",
        "constraints": ("The failed checks are named in the brief and the render must "
                        "answer each one directly; the composition stays as before.",)},
    "change_composition": {
        "provider": "same",
        "composition": "alternate",
        "constraints": ("Change the composition entirely: a three-quarter overhead angle, a "
                        "different crop that shows the whole object with a plain margin "
                        "round it, and a different plain surface and light direction from "
                        "any earlier render of this product.",)},
    "change_tool": {
        "provider": "alternate",
        "composition": "unchanged",
        "constraints": ("Rendered on a different permitted image model from every earlier "
                        "attempt at this product.",)},
}
# The audit action the photography job writes when it has attempted a rung, with the result.
ESCALATION_RESULT_ACTION = "creative.escalation_result"


def escalation_progress(db, *, slug: str, version: str) -> dict:
    """Where this release stands on the #81 ladder, from persisted rung results.

    Each rung attempt the photography job completed is a `creative.escalation_result` audit
    row for the release naming the rung and whether it produced a usable frame. The next
    attempt is the first generation rung with no completed result; when every generation
    rung has one, the ladder stands at the deterministic rung. A rung whose result is usable
    ends the walk (parity is re-read from the new frame, not assumed).
    """
    from sqlalchemy import select

    from ..core.models import AuditLog

    results: dict[str, dict] = {}
    with db.session() as s:
        for row in s.scalars(select(AuditLog).where(
                AuditLog.action == ESCALATION_RESULT_ACTION,
                AuditLog.artifact == f"{slug}@{version}").order_by(AuditLog.id)):
            d = dict(row.detail or {})
            if d.get("rung") and d.get("attempted"):
                results[d["rung"]] = {"usable": bool(d.get("usable")),
                                      "verdict": d.get("verdict"), "job_id": row.job_id,
                                      "at": row.at.isoformat() if row.at else None}
    attempted = [r for r in GENERATION_RUNGS if r in results]
    start_attempt = 0
    for r in GENERATION_RUNGS:
        if r in results and not results[r]["usable"]:
            start_attempt += 1
        else:
            break
    return {"results": results, "attempted": attempted, "start_attempt": start_attempt,
            "usable_from": next((r for r in GENERATION_RUNGS
                                 if results.get(r, {}).get("usable")), None)}


def gates_now(db, keys=("image_generation", "physical_proof")) -> dict[str, bool]:
    """The live state of the gates the ladder's rungs wait on, read from the database."""
    from ..build2 import executor

    out: dict[str, bool] = {}
    for key in keys:
        gate = executor.GATE_BY_KEY.get(key)
        try:
            out[key] = bool(gate.open(db)) if gate is not None else False
        except Exception:  # noqa: BLE001 - an unreadable gate is closed, and says so upstream
            out[key] = False
    return out


def escalation_plan(failed: list[str], *, deterministic_available: bool,
                    start_attempt: int = 0, gate_open: dict[str, bool] | None = None) -> dict:
    """Walk a parity failure through the #81 ladder as a recorded plan.

    Nothing here renders, spends or asks anybody. Each rung from `start_attempt` is read off
    `escalate()` and classified: rungs that need paid generation or a physical object are
    recorded as `gated` with the gate that holds them; the deterministic rung is `taken` when
    a deterministic render is available, because it is free and always truthful; and if no
    rung was taken the listing is held. Lowering the bar is not a rung.
    """
    rungs, taken = [], None
    attempt = start_attempt
    while True:
        step = escalate(attempt)
        action = step["action"]
        gate = RUNG_GATES.get(action, "")
        if action == "hold_listing":
            status = "outcome" if taken is None else "not_needed"
        elif gate and (gate_open or {}).get(gate) and taken is None:
            # C-69 (#81): the gate is read live; a rung whose gate has opened is attempted
            # in ladder order rather than skipped as gated forever.
            status = "taken"
        elif gate and (gate_open or {}).get(gate):
            status = "eligible"
        elif gate:
            status = "gated"
        elif action == "deterministic_representation":
            status = ("taken" if deterministic_available and taken is None else
                      "not_needed" if deterministic_available else "unavailable")
        else:  # pragma: no cover - every rung is classified above
            status = "unclassified"
        entry = {"attempt": attempt, "action": action, "why": step["why"], "status": status}
        if gate:
            entry["gated_on"] = gate
            entry["gate_open"] = bool((gate_open or {}).get(gate))
            entry["executed"] = False
        if status == "taken":
            taken = action
            entry["executes_via"] = RUNG_EXECUTES_VIA.get(
                action, "assets.build renders the chart and twin from the certified CIR: "
                        "deterministic and free")
        rungs.append(entry)
        if step["exhausted"] or action == "hold_listing":
            break
        attempt += 1
    return {
        "failed_dimensions": list(failed),
        "rungs": rungs,
        "taken": taken,
        "start_attempt": start_attempt,
        "gated": [r["action"] for r in rungs if r["status"] == "gated"],
        "gates_read_live": gate_open is not None,
        "outcome": ("replace the failing frame with a deterministic representation"
                    if taken else "hold the listing"),
        "still_blocks_release": True,
        "note": ("The plan records the path; release still waits for the parity gate to "
                 "pass on the new frames. Paid generation and physical proof are never "
                 "started from here (#81)."),
    }


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


def minimum_quality(frames: list[dict]) -> dict:
    """#80 at export: every frame earns its place by its job and its gates, never by count.

    Each frame is `{"position", "role", "job", "passed", "why"}` -- `job` the commercial job
    it was assigned (empty when none could be), `passed` whether every quality gate that
    applies to it ran and passed. A frame with no job is filler and a frame that failed its
    gate is weak; both are refused for export, and the remedy for either is removing the
    frame, never adding another one to reach a number. The gallery's length is reported and
    never judged.
    """
    filler = [f for f in frames if not f.get("job")]
    weak = [f for f in frames if f.get("job") and not f.get("passed")]
    keep = [f for f in frames if f.get("job") and f.get("passed")]
    problems = (
        [{"kind": "filler", "position": f.get("position"), "role": f.get("role"),
          "why": ("no commercial job, so the frame answers no buyer question. A gallery "
                  "padded to a count is worse than a shorter one (#80)")} for f in filler]
        + [{"kind": "weak", "position": f.get("position"), "role": f.get("role"),
            "job": f.get("job"),
            "why": (f"does not pass its quality gate for {f.get('job')}: "
                    f"{f.get('why') or 'no reason recorded'}. Remove or remake it; "
                    f"do not keep it to hold the count")} for f in weak])
    return {
        "ok": bool(frames) and not problems,
        "frames": len(frames),
        "keep": [f.get("position") for f in keep],
        "remove": [f.get("position") for f in filler + weak],
        "problems": problems if frames else [{"kind": "empty", "why": "no frames"}],
        "count_is_not_a_criterion": True,
        "note": ("A shorter excellent gallery is preferable to a longer one with filler; a "
                 "frame is added only when it answers a buyer question, adds proof or "
                 "increases desire (#80)."),
    }
