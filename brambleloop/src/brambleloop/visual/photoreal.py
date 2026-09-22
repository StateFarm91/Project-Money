"""The natural-photography standard, as a gate rather than an aspiration.

The owner's Final Master standard, given 2026-09-22: customer-facing imagery should look
like believable real photography, not recognisable AI imagery. That is a real commercial
requirement rather than a taste -- a buyer who clocks a listing photograph as generated
stops trusting the pattern behind it, and on a craft marketplace the maker audience is
unusually good at clocking it.

This is deliberately *not* `gallery.REALISM_CHECKS`. That list asks whether the crochet is
physically possible: stitch scale, yarn continuity, joins, drape. This one asks whether the
photograph is believable as a photograph: skin, hands, lighting, processing, the sterile
perfection that reads as a render. A frame can pass either and fail the other -- a flawless
studio-lit impossible seam, or an honest piece of fabric on a woman with eight fingers --
and folding them together would let one cover for the other.

Two rules carried from every other gate here:

**Unjudged is not passed.** A check the model did not answer is reported as unmade, and an
unmade check blocks exactly as a failed one does. The difference is what to do next: a
failure needs a different render, an unmade check needs the question asked again.

**The judge never sees the standard as a checklist to agree with.** It is asked what it can
see, in the vocabulary of the failure rather than of the verdict, and this module decides.
A grader shown "this should look like real photography" says yes.
"""
from __future__ import annotations

import json

from ..core.resilience import PermanentError, TransientError

TASK = "asset_inspection"
MAX_TOKENS = 900

# The owner's named rejections, each as a property that is either present or not. Phrased so
# that `True` means the photograph is *sound* on that axis, which keeps the gate's arithmetic
# the same as every other check here: a False is a failure and a missing key is unmade.
CHECKS: dict[str, str] = {
    "skin_looks_real": ("skin has ordinary texture, pores and tonal variation rather than "
                        "the poreless airbrushed surface a generator produces"),
    "anatomy_is_possible": "the body, limbs and proportions are anatomically possible",
    "hands_are_right": ("hands and fingers are correctly formed and correctly numbered, "
                        "the single most recognisable generated-image failure"),
    "textures_do_not_repeat": ("no surface tiles or repeats a patch of itself, which is "
                               "how a generator fills an area it cannot reason about"),
    "yarn_is_believable": ("the yarn reads as real fibre with real twist and fuzz rather "
                           "than a smooth plastic rope"),
    "crochet_geometry_is_plausible": ("stitches and fabric geometry could actually be "
                                      "worked by hand"),
    "lighting_is_coherent": ("shadows, highlights and reflections agree with one light "
                             "situation"),
    "processing_is_restrained": ("no excessive beauty retouching, skin smoothing, teeth "
                                 "or eye brightening"),
    "depth_of_field_is_natural": ("any blur behaves like a real lens rather than a cut-out "
                                  "subject pasted on a blurred plate"),
    "no_unexplained_text": ("no invented text, watermarks, logos or brand marks anywhere "
                            "in the frame"),
    "not_sterile_perfection": ("the scene has ordinary imperfection -- a crease, a stray "
                               "fibre, an unstyled corner -- rather than the frictionless "
                               "catalogue perfection that reads as generated"),
}

SYSTEM = (
    "You are a working photographer looking at an image and deciding whether it reads as a "
    "real photograph or as a generated one. You are not judging whether it is attractive. "
    "Report what you can actually see, and say plainly when a part of the frame does not "
    "show you enough to tell."
)


def prompt() -> str:
    lines = [
        "Answer as JSON. For each key give true if the statement holds, false if it does "
        "not, and omit the key entirely if the image does not show you enough to judge it. "
        "Do not guess: an omitted key is a useful answer and a wrong one is not.",
        "",
    ]
    for key, what in CHECKS.items():
        lines.append(f'  "{key}": {what}')
    lines.append("")
    lines.append('Add "notes": one short sentence naming anything that made the image read '
                 "as generated, or an empty string.")
    return "\n".join(lines)


def judge(image_ref: str, *, db=None, provider=None) -> dict:
    """Ask a model what it can see. Returns readings, never a verdict."""
    from ..finance import spend_report
    from ..gateway import anthropic as gw

    provider = provider or gw.provider_for(TASK)
    try:
        response = provider.see(SYSTEM, prompt(), [image_ref], max_tokens=MAX_TOKENS)
    except (PermanentError, TransientError) as exc:
        return {"judged": False, "error": str(exc)[:200], "checks": {}}

    if db is not None:
        cost = round(response.input_tokens * provider.cost_per_1k_input_cad / 1000
                     + response.output_tokens * provider.cost_per_1k_output_cad / 1000, 8)
        spend_report.record(
            db, agent="publishing", amount_cad=cost, estimated_cad=cost, purpose=TASK,
            provider="anthropic", model=provider.model, department="creative",
            tokens_in=response.input_tokens, tokens_out=response.output_tokens,
            detail={"price_basis": "assumed", "check": "photographic_realism"})

    import re

    match = re.search(r"\{.*\}", response.text or "", re.S)
    if not match:
        return {"judged": False, "error": "no JSON in the realism answer", "checks": {}}
    try:
        parsed = json.loads(match.group(0))
    except ValueError as exc:
        return {"judged": False, "error": f"unreadable: {exc}"[:200], "checks": {}}

    # Only the closed vocabulary, and only real booleans. A string "true" is an answer to a
    # different question, and coercing it would invent an opinion the model did not give.
    checks = {k: bool(parsed[k]) for k in CHECKS
              if k in parsed and isinstance(parsed[k], bool)}
    return {"judged": True, "checks": checks,
            "notes": str(parsed.get("notes") or "")[:240]}


def gate(reading: dict) -> dict:
    """Three-valued, and unmade is never passed.

    `blocked` when a named failure is present, `unjudged` when the frame was not fully
    read, `clear` only when every check came back sound. The distinction matters because
    the two non-clear outcomes need opposite next moves: a blocked frame needs a different
    render and an unjudged one needs the question asked again.
    """
    checks = dict(reading.get("checks") or {})
    failed = sorted(k for k, ok in checks.items() if ok is False)
    unmade = sorted(k for k in CHECKS if k not in checks)

    if failed:
        verdict, why = "blocked", (
            f"the photograph reads as generated on {failed}. "
            f"{reading.get('notes', '')}".strip())
    elif not reading.get("judged"):
        verdict, why = "unjudged", (
            f"the realism judge did not answer: {reading.get('error', 'no reason given')}. "
            f"Unjudged is not a pass")
    elif unmade:
        verdict, why = "unjudged", (
            f"{unmade} could not be judged from this frame. Unjudged is not a pass -- it "
            f"is a question to ask again, which is a different fix from a failure")
    else:
        verdict, why = "clear", "reads as a believable photograph on every named axis"

    return {"verdict": verdict, "failed": failed, "unjudged": unmade,
            "checks": checks, "notes": reading.get("notes", ""), "why": why,
            "standard": ("the owner's Final Master natural-photography standard, "
                         "2026-09-22: believable real photography, not recognisable AI "
                         "imagery, and never product truth traded for beauty")}


# The prompt language that asks for this in the first place. Kept beside the checks so the
# thing asked for and the thing checked cannot drift apart into two different standards.
DIRECTION = (
    "Photographed as real photography, not as a render: natural window light with one "
    "coherent shadow direction, ordinary skin texture with visible pores and no beauty "
    "retouching, believable hair with stray strands, real yarn with visible twist and "
    "fuzz, fabric that falls under its own weight, an ordinary relaxed pose, and a little "
    "honest imperfection -- a crease, a stray fibre, an unstyled corner. No text, "
    "watermarks or logos anywhere. Avoid catalogue perfection, heavy background blur and "
    "glossy retouching."
)
