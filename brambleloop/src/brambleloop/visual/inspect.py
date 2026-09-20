"""The checks this company makes on its own pictures, and the model that makes them.

Requirements 61 and 79. `visual/gallery.py` has always known what to ask -- ten named
physical-realism failures and the rule that a frame must do the job it was given -- and has
always reported unmade checks as *unjudged* rather than as passes. This is what makes them.

**Unjudged was the honest state and was never the finished one.** A frame with ten unmade
realism checks reports ten unmade realism checks, which is correct and useless: the listing
cannot ship and nobody can say why. The gap was a model that could look at the picture, and
that arrived on 2026-09-19 without anybody noticing, because the capability was filed under
a gate named after a cloud browser.

**#61's clause is the one that is easy to lose.** "Does this image communicate what its
caption claims" cannot be answered by measuring pixels -- `publish/layout_qa.py` already
measures the pixels, and a flat field of even-toned fabric passes every pixel test while
communicating nothing. It needs somebody to look and say what they see, and then a
comparison against what was promised.

**So the answer is compared rather than asked for.** The model is never shown the caption and
asked "does this match": that question has an obvious polite answer, and a grader shown the
expected result grades toward it. It is asked what the image shows, and this module compares.

**The generator does not grade itself.** #61 says so and it is structural here: the
description is produced from the rendered file, not from the plan that produced the file, so
a render that silently failed cannot describe what it intended.
"""
from __future__ import annotations

import json

from ..core.resilience import PermanentError, TransientError
from .gallery import REALISM_CHECKS

DESCRIBE_SYSTEM = (
    "You are looking at a product photograph for a craft marketplace listing. Describe only "
    "what is visibly present. Do not guess at the maker's intention, do not describe what "
    "the image is probably meant to show, and say plainly when something is unclear."
)

REALISM_SYSTEM = (
    "You are a crochet maker inspecting a photograph for physical impossibilities. You know "
    "how yarn behaves, how stitches scale, how fabric drapes and how seams join. Judge only "
    "what the picture shows."
)

DESCRIBE_MAX_TOKENS = 500
REALISM_MAX_TOKENS = 900
# Routed rather than hardcoded. This named the cheap model, which put a release-blocking
# judgement -- ten physical-realism checks and whether a picture says what its caption claims
# -- on the tier meant for extraction.
TASK = "asset_inspection"

# What a description is allowed to be about. Closed for the same reason every other
# vocabulary here is: an open field accepts "a lovely blanket", and a semantic check whose
# evidence is "a lovely blanket" cannot disagree with any caption ever written.
DESCRIPTION_FIELDS: tuple[str, ...] = (
    "object_shown", "object_count", "finished_or_in_progress", "human_present",
    "text_present", "chart_or_diagram", "dominant_colours", "clarity",
)


class InspectionRefused(ValueError):
    """An answer that is not an inspection."""


def describe_prompt() -> str:
    return (
        "Reply with a single JSON object and nothing else. Keys:\n"
        + "\n".join(f"- {f}" for f in DESCRIPTION_FIELDS)
        + "\n\n`object_count` is an integer. `finished_or_in_progress` is one of: finished, "
          "in_progress, unclear. `human_present`, `text_present` and `chart_or_diagram` are "
          "true or false. `clarity` is one of: clear, ambiguous, unreadable. Every other "
          "value is one short phrase. Omit nothing; use `unclear` where you cannot tell.")


def realism_prompt() -> str:
    return (
        "Reply with a single JSON object and nothing else, one key per check, each `true` "
        "(the picture is physically plausible on this point), `false` (it is not) or "
        "`unclear`. Add a key `reasons` mapping any `false` to one short phrase.\n\nChecks:\n"
        + "\n".join(f"- {c}" for c in REALISM_CHECKS))


def _json(text: str) -> dict:
    body = (text or "").strip()
    if body.startswith("```"):
        body = body.split("\n", 1)[-1].rsplit("```", 1)[0]
    try:
        parsed = json.loads(body)
    except ValueError as exc:
        raise InspectionRefused(
            f"the model did not answer with JSON: {body[:120]!r}") from exc
    if not isinstance(parsed, dict):
        raise InspectionRefused(f"expected one object, got {type(parsed).__name__}")
    return parsed


def parse_description(text: str) -> dict:
    parsed = _json(text)
    unknown = sorted(k for k in parsed if k not in DESCRIPTION_FIELDS)
    if unknown:
        raise InspectionRefused(
            f"{unknown} are not description fields. The vocabulary is closed because an open "
            f"one accepts 'a lovely blanket', and a semantic check whose evidence is that "
            f"cannot disagree with any caption ever written")
    missing = [f for f in DESCRIPTION_FIELDS if f not in parsed]
    if missing:
        raise InspectionRefused(
            f"{missing} were not answered. A description with holes in it passes a caption "
            f"check by not contradicting it")
    return parsed


def parse_realism(text: str) -> dict:
    parsed = _json(text)
    reasons = parsed.pop("reasons", {}) or {}
    unknown = sorted(k for k in parsed if k not in REALISM_CHECKS)
    if unknown:
        raise InspectionRefused(f"{unknown} are not realism checks: {sorted(REALISM_CHECKS)}")
    out: dict = {}
    for check, value in parsed.items():
        if value is True or value is False:
            out[check] = value
        elif str(value).lower() == "unclear":
            continue  # unjudged, which `gallery.check_frame` already reports as unmade
        else:
            raise InspectionRefused(
                f"{check}={value!r} is neither true, false nor unclear. A realism check with "
                f"a third opinion is a check nobody can act on")
    return {"checks": out, "reasons": {k: v for k, v in reasons.items() if k in out}}


# ---------------------------------------------------------------------------
# The comparison (#61)


# What a claim and a description can disagree about. Each is a disagreement somebody would
# notice on the listing page, which is the only kind worth blocking a release for.
CONTRADICTIONS: tuple[tuple[str, str], ...] = (
    ("chart_or_diagram", "a frame whose job is the finished result is showing a chart"),
    ("finished_or_in_progress", "the caption promises a finished object and the picture "
                                "shows work in progress"),
    ("human_present", "the caption describes a worn garment and nobody is wearing it"),
    ("clarity", "the picture is unreadable, so it communicates nothing whatever it shows"),
)


def compare(description: dict, claim: dict) -> dict:
    """Does the picture communicate what the caption claims (#61)?

    The model never sees the claim. A grader shown the expected answer grades toward it, and
    "does this image match this caption" has an obvious polite answer -- which is why the
    requirement's own closing clause says not to let the generator grade itself, and why the
    comparison lives here in deterministic code rather than in a prompt.
    """
    problems: list[dict] = []

    if claim.get("shows_finished_object") and \
            description.get("finished_or_in_progress") != "finished":
        problems.append({"check": "finished_result",
                         "claim": "a finished object",
                         "seen": description.get("finished_or_in_progress"),
                         "why": ("a finished-result frame that does not show a finished "
                                 "object is the frame a buyer bought the pattern for")})
    if claim.get("shows_finished_object") and description.get("chart_or_diagram") is True:
        problems.append({"check": "chart_as_hero", "claim": "a finished object",
                         "seen": "a chart or diagram",
                         "why": "a chart preview must look like a chart preview, and only that"})
    if claim.get("shows_worn_garment") and description.get("human_present") is False:
        problems.append({"check": "worn_garment", "claim": "a worn garment",
                         "seen": "nobody wearing it",
                         "why": "fit is the question a garment listing has to answer"})
    if claim.get("shows_size_reference") and \
            not str(description.get("object_count") or 0).isdigit():
        problems.append({"check": "size_reference", "claim": "a scale reference",
                         "seen": description.get("object_count"),
                         "why": "a size card that cannot be counted communicates no size"})
    if description.get("clarity") == "unreadable":
        problems.append({"check": "clarity", "claim": "anything at all",
                         "seen": "unreadable",
                         "why": "an unreadable frame communicates nothing whatever it shows"})

    return {
        "communicates": not problems,
        "problems": problems,
        "description": description,
        "claim": claim,
        "method": ("the model described the picture without being shown the caption, and "
                   "this compared the two. Asking 'does this match' has an obvious polite "
                   "answer, and a grader shown the expected result grades toward it"),
    }


# ---------------------------------------------------------------------------
# Making the calls


def inspect_image(image_ref: str, *, db=None, provider=None,
                  claim: dict | None = None) -> dict:
    """Describe one rendered asset, judge its realism, and compare against what was claimed.

    Two calls rather than one. Description and physical plausibility are different questions
    with different system prompts -- a maker inspecting for impossible seams is not the same
    reader as somebody saying what is in the frame -- and combining them invites the second
    answer to be coloured by the first.
    """
    from ..gateway import anthropic as gw

    provider = provider or gw.provider_for(TASK)
    out: dict = {"image": image_ref, "described": False, "realism_judged": False,
                 "model": provider.model}
    billed = {"reserved": 0.0, "actual": 0.0, "tokens_in": 0, "tokens_out": 0}

    def _call(system, prompt, max_tokens):
        if db is not None:
            billed["reserved"] += gw.check_budget(
                db, model=provider.model,
                input_tokens=len(prompt) // 4 + gw.IMAGE_TOKENS_ESTIMATE,
                max_tokens=max_tokens)["estimate_cad"]
        response = provider.see(system, prompt, [image_ref], max_tokens=max_tokens)
        billed["actual"] += round(
            response.input_tokens * provider.cost_per_1k_input_cad / 1000
            + response.output_tokens * provider.cost_per_1k_output_cad / 1000, 8)
        billed["tokens_in"] += response.input_tokens
        billed["tokens_out"] += response.output_tokens
        return response

    try:
        described = _call(DESCRIBE_SYSTEM, describe_prompt(), DESCRIBE_MAX_TOKENS)
        out["description"] = parse_description(described.text)
        out["described"] = True
    except (PermanentError, TransientError, InspectionRefused) as exc:
        out["description_error"] = str(exc)[:300]

    try:
        judged = _call(REALISM_SYSTEM, realism_prompt(), REALISM_MAX_TOKENS)
        realism = parse_realism(judged.text)
        out["realism"] = realism["checks"]
        out["realism_reasons"] = realism["reasons"]
        out["realism_judged"] = True
        out["realism_unjudged"] = sorted(set(REALISM_CHECKS) - set(realism["checks"]))
    except (PermanentError, TransientError, InspectionRefused) as exc:
        out["realism_error"] = str(exc)[:300]
        out["realism_unjudged"] = sorted(REALISM_CHECKS)

    if out["described"] and claim:
        out["semantic"] = compare(out["description"], claim)

    if db is not None and billed["actual"] > 0:
        from ..finance import spend_report

        spend_report.record(
            db, agent="quality_director", amount_cad=billed["actual"],
            estimated_cad=billed["reserved"], purpose=TASK, provider="anthropic",
            model=provider.model, department="quality",
            tokens_in=billed["tokens_in"], tokens_out=billed["tokens_out"],
            detail={"price_basis": "assumed", "image": image_ref[:120]})

    out["note"] = ("an unmade check is unjudged, never a pass. That was true before anything "
                   "could look at a picture and it stays true now: a call that failed leaves "
                   "the checks unmade rather than leaving them green")
    return out


def apply_to_frame(frame, inspection: dict) -> None:
    """Fill a `gallery.Frame` from an inspection, leaving unmade checks unmade.

    Deliberately not `frame.realism.update(...)` with a default: a check the model returned
    `unclear` for, or that a failed call never reached, stays absent so that
    `gallery.check_frame` goes on reporting it as unjudged. Defaulting an unmade check to
    True is how a release gate becomes a formality, and it is one line to write.
    """
    for check, value in (inspection.get("realism") or {}).items():
        frame.realism[check] = value
    description = inspection.get("description") or {}
    if description.get("clarity"):
        frame.readable_at_grid = description["clarity"] != "unreadable"


def gate(inspection: dict) -> dict:
    """Whether this asset may be released, from what was actually judged.

    Three outcomes rather than two. A failed check blocks; an unmade check blocks for a
    generated frame and does not for a photograph, which is the rule `gallery.check_frame`
    already applies; and a passed set releases. A gate with two outcomes has to call an
    unmade check something, and whichever it calls it is wrong half the time.
    """
    failed = sorted(k for k, v in (inspection.get("realism") or {}).items() if v is False)
    unjudged = list(inspection.get("realism_unjudged") or [])
    semantic = inspection.get("semantic") or {}
    problems = semantic.get("problems") or []

    if failed or problems:
        return {"verdict": "blocked", "failed_realism": failed,
                "semantic_problems": problems,
                "why": ("artefacts a maker sees instantly, or a picture that does not show "
                        "what its caption promises. Either is worse than an obviously "
                        "illustrated image")}
    if unjudged:
        return {"verdict": "unjudged", "unmade": unjudged,
                "why": ("these checks were not made. Unmade is not passed, and a generated "
                        "frame with unmade realism checks does not ship")}
    return {"verdict": "clear", "failed_realism": [], "semantic_problems": [],
            "why": "every check was made and every check passed"}
