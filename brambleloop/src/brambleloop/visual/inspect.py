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
# Who is spending, named once. This was a literal in the `spend_report.record` call and
# nowhere else, so the ledger knew whose money it was and the pre-call guard did not -- the
# exact shape of the hole. One constant, read by both, so the ceiling that binds and the row
# that is billed cannot come to disagree about which agent made the call.
AGENT = "quality_director"

# What a description is allowed to be about. Closed for the same reason every other
# vocabulary here is: an open field accepts "a lovely blanket", and a semantic check whose
# evidence is "a lovely blanket" cannot disagree with any caption ever written.
DESCRIPTION_FIELDS: tuple[str, ...] = (
    "object_shown", "object_count", "finished_or_in_progress", "human_present",
    "text_present", "chart_or_diagram", "dominant_colours", "clarity",
    # Added 2026-09-21 from an actual render. The first image this company ever generated
    # through GPT Image 2 was a beautiful styled scene of a crochet basket holding a stack
    # of magazines, and the top one carried the KINFOLK masthead, legibly, in the centre of
    # the frame. Nothing in the pipeline would have objected: `text_present` was already a
    # field and the answer would have been `true`, which is a fact about the picture rather
    # than a problem with it.
    #
    # It is a problem with it. A third party's mark in a listing photograph is a listing
    # that uses somebody's brand to sell something they have nothing to do with, and this
    # company's own non-negotiables already forbid the same thing in words. It only ever
    # appeared in imagery once imagery could be generated, and it arrived on the first try,
    # unasked for, from the strongest prompt-adherence model in the set -- which is the
    # argument for checking rather than for trusting the brief.
    "third_party_marks",
)

# Marks block a release on their own, whatever the caption says. Unlike the contradictions
# below, this is not a disagreement between picture and claim: a real brand in the frame is
# wrong even when the caption describes it accurately.
MARKS_NONE = ("none", "no", "false", "unclear", "")


class InspectionRefused(ValueError):
    """An answer that is not an inspection."""


def describe_prompt() -> str:
    return (
        "Reply with a single JSON object and nothing else. Keys:\n"
        + "\n".join(f"- {f}" for f in DESCRIPTION_FIELDS)
        + "\n\n`object_count` is an integer. `finished_or_in_progress` is one of: finished, "
          "in_progress, unclear. `human_present`, `text_present` and `chart_or_diagram` are "
          "true or false. `clarity` is one of: clear, ambiguous, unreadable. "
          "`third_party_marks` lists any real brand name, logo, masthead, book or magazine "
          "title, or other identifiable third-party mark legible anywhere in the frame, "
          "including on props -- answer `none` only if there are none. Every other "
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
        held = None
        if db is not None:
            # `uncommitted_cad` is this run's own spend, which is not in the ledger yet.
            # Without it the ceiling is checked against a month total that does not include
            # anything this batch has already spent, so every call after the first in a batch
            # is authorised against a stale number. The same hole in `intel/vision.py` let
            # about twenty-one vision calls sit behind a single ledger row -- twenty of every
            # twenty-one authorised against a total that had not moved. Found by the
            # Reliability department and left here for Visual to apply, because this file is
            # Visual-owned and they were correct not to reach into it.
            #
            # `agent` and `purpose` are what make `quality_director`'s daily permission bind
            # on this path. Without them `check_budget` checked the month and nothing else,
            # so the one number this call site was measured against (CA$8.84 of
            # `asset_inspection` across 504 calls in the month to 2026-09-25) was checked by
            # nobody. A Visual call gets no exemption the other five spend paths do not get.
            budget = gw.check_budget(
                db, model=provider.model,
                input_tokens=len(prompt) // 4 + gw.IMAGE_TOKENS_ESTIMATE,
                max_tokens=max_tokens,
                uncommitted_cad=max(billed["actual"], billed["reserved"]),
                agent=AGENT, purpose=TASK)
            billed["reserved"] += budget["estimate_cad"]
            held = budget["reservation_id"]
        try:
            response = provider.see(system, prompt, [image_ref], max_tokens=max_tokens)
        except BaseException:
            # Released on the way out, including on a refusal. A reservation a failed call
            # never gives back holds budget nobody is spending until its TTL expires, and
            # this function makes two calls in a row: the second would be checked against a
            # month carrying the first one's abandoned claim.
            if db is not None:
                gw.release_reservation(db, held)
            raise
        cost = round(
            response.input_tokens * provider.cost_per_1k_input_cad / 1000
            + response.output_tokens * provider.cost_per_1k_output_cad / 1000, 8)
        billed["actual"] += cost
        billed["tokens_in"] += response.input_tokens
        billed["tokens_out"] += response.output_tokens
        # Given back with the bill rather than left to expire. The estimate is padded on
        # purpose and the actual is usually a third of it, so holding the estimate for the
        # full TTL after the provider has answered reserves money nobody is going to spend.
        if db is not None:
            gw.release_reservation(db, held, actual_cad=cost)
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
            db, agent=AGENT, amount_cad=billed["actual"],
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


def marks_found(description: dict) -> list[str]:
    """Any identifiable third-party mark the describer reported. See DESCRIPTION_FIELDS."""
    raw = (description or {}).get("third_party_marks")
    if raw is None:
        return []
    items = raw if isinstance(raw, list) else [raw]
    return [str(m).strip() for m in items
            if str(m).strip().lower() not in MARKS_NONE]


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
    marks = marks_found(inspection.get("description") or {})

    if failed or problems or marks:
        return {"verdict": "blocked", "failed_realism": failed,
                "semantic_problems": problems,
                "third_party_marks": marks,
                "why": ("artefacts a maker sees instantly, a picture that does not show "
                        "what its caption promises, or somebody else's brand in the frame. "
                        "The first two are worse than an obviously illustrated image; the "
                        "third is using a mark this company has no right to")}
    if unjudged:
        return {"verdict": "unjudged", "unmade": unjudged,
                "why": ("these checks were not made. Unmade is not passed, and a generated "
                        "frame with unmade realism checks does not ship")}
    return {"verdict": "clear", "failed_realism": [], "semantic_problems": [],
            "third_party_marks": [],
            "why": "every check was made and every check passed"}


def calibrate(db, *, image_url: str = "", provider=None, benchmark_key: str = "") -> dict:
    """Ask the realism checks about a photograph nobody generated.

    The question four blocked renders made unavoidable. Every product-first asset this
    company has made was blocked on `texture_not_repeating`, across two products and two
    method versions -- and crocheted fabric is, by construction, a surface that repeats.

    Two possibilities needing opposite fixes, and a render cannot tell them apart:

      the generator really is tiling a patch    -> the method or the provider changes
      the check cannot pass a crochet photograph -> the check changes

    `photoreal.calibrate` exists for exactly this question about its own list and settled
    it the other way: the renders were the problem and the standard was working. So the
    flattering assumption is not the one to make here either, and this asks the same way,
    against a real listing photograph used as a control and nothing else -- not copied,
    not re-hosted, not imitated, and never described.

    A check a real photograph *fails* is unreachable. A check it *cannot answer* is
    unproven rather than unreachable, which is a different finding needing a different
    control, and conflating them is how a working standard gets loosened.
    """
    from . import photoreal

    control = image_url or photoreal.control_image(db, benchmark_key=benchmark_key)
    if not control:
        return {"calibrated": False,
                "why": ("no benchmark listing photograph is on file, so there is no "
                        "control to calibrate against. That is not a finding about the "
                        "checks")}

    reading = inspect_image(control, db=db, provider=provider)
    checks = dict(reading.get("realism") or {})
    failed = sorted(k for k, v in checks.items() if v is False)
    unjudged = sorted(reading.get("realism_unjudged") or
                      [k for k in REALISM_CHECKS if k not in checks])
    answered = sorted(k for k in REALISM_CHECKS if k not in unjudged)

    return {
        "calibrated": bool(reading.get("realism_judged")),
        "control": control,
        "control_is": ("a real photograph from an observed benchmark listing, used to "
                       "check whether these checks can pass a photograph at all. It is "
                       "not copied, re-hosted or imitated, and what it depicts is never "
                       "described"),
        "checks": list(REALISM_CHECKS),
        "failed": failed,
        "unjudged": unjudged,
        "discriminating": answered,
        "unreachable": failed,
        "reachable": not failed,
        "what_it_means": (
            f"these checks failed a real photograph on {failed}, so what they measure is "
            f"not 'reads as generated'. Every render is being blocked by a question no "
            f"photograph of crochet can answer the way this gate wants, and tightening a "
            f"render against them would be chasing a standard nothing can meet"
            if failed else
            f"a real photograph failed none of them. {answered} discriminate, so a render "
            f"these checks block is a render that needs changing rather than a standard "
            f"that needs relaxing"),
        "why_unjudged_is_not_unreachable": (
            "a check this control could not answer is unproven, not unreachable. A "
            "different control settles it, and calling it unreachable would be a verdict "
            "computed from absence of evidence"),
    }
