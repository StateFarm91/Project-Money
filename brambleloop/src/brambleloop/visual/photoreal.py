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
    "coherent shadow direction, believable hair with stray strands, real yarn with "
    "visible twist and fuzz, fabric that falls under its own weight, an ordinary relaxed "
    "pose, and a little honest imperfection -- a crease, a stray fibre, an unstyled "
    "corner. No text, watermarks or logos anywhere. Avoid catalogue perfection, heavy "
    "background blur and glossy retouching. "
    # Named at this length because the first live frame failed on exactly these three and
    # the judge said why: "overly smooth, poreless, airbrushed... the overall symmetry and
    # evenness of features reads as retouched rather than photographed". A general request
    # for realism did not reach it; the specific defect has to be named to be avoided.
    "Her skin is unretouched and photographed as it is: visible pores and fine texture, "
    "uneven natural tone, faint shine where light falls, and ordinary asymmetry between "
    "the two sides of the face. No skin smoothing, no blemish removal, no eye or teeth "
    "brightening, no softening filter. It should look like an unedited raw frame from a "
    "real camera rather than a finished beauty image. "
    # Added after the calibration settled which way the evidence pointed. A real benchmark
    # photograph failed none of these checks and answered all three of the ones blocking
    # our renders, so the standard discriminates and the renders were the problem. Three
    # attempts had been blocked on the same trio, each time against direction that asked
    # generally for unretouched skin -- so this names the *scene* as well, because the two
    # remaining failures were about the frame rather than the face: a person on a seamless
    # backdrop with nothing else in shot is a catalogue cut-out however real her skin is.
    "The scene is a real place with real evidence of use: a wall with its own colour and "
    "marks, a floor edge, a hint of what is beyond the frame. Something in it is slightly "
    "out of place -- a crease in the fabric, a strand of hair across a shoulder, a thread "
    "end, a fold that has not been straightened. Nothing is arranged for the photograph "
    "and nothing has been cleaned up afterwards."
)


# ---------------------------------------------------------------------------
# Whether this judge can be satisfied at all
#
# Two renders in a row were blocked on `skin_looks_real`, `processing_is_restrained` and
# `not_sterile_perfection`, and the second of them plainly had pores, freckles and fine
# lines in it. At that point there are two possibilities and they need opposite fixes: the
# renders really are unphotographic, or the judge cannot pass a photograph. A standard that
# nothing can clear is the same defect as a floor nothing can fail, and this system has
# found that shape four times already -- so it is a question to ask rather than to assume
# the flattering answer to.
#
# The control is a real photograph: one of the benchmark shop's own listing images, which
# is a photograph a real person took with a real camera. It is used as a calibration
# control and nothing else -- not copied, not re-hosted, not imitated, and the design in it
# is never described. If the judge blocks that, the judge is wrong; if it clears it, the
# renders are.

CALIBRATION_ACTION = "photoreal.calibration"

# Moves when the checks or the wording move, because a calibration is a statement about
# one version of this standard and reading an older one back as current is how a tightened
# judge never gets re-checked.
CHECKS_VERSION = "v2-a-control-that-cannot-answer-is-not-a-standard-that-cannot-pass"


def calibrate(db, *, image_url: str, provider=None) -> dict:
    """Ask the judge about a photograph nobody generated, and record what it said.

    Three outcomes, not two, and the middle one turned out to be the common one. The first
    live calibration came back `unjudged` on `anatomy_is_possible` and
    `depth_of_field_is_natural`, because the control was a flat-lay swatch with no person
    and no background in it and honestly cannot answer either. Reading that as "the
    standard is unreachable" would have been a verdict computed from absence of evidence --
    the exact defect this function was added to test for, committed by the test.

    What matters is whether any check *failed* on a real photograph, and which checks were
    answered at all. That first control failed nothing and answered all three of the checks
    that were blocking our renders, so those three discriminate and the renders are what
    needs changing.
    """
    reading = judge(image_url, db=db, provider=provider)
    verdict = gate(reading)
    failed, unjudged = verdict["failed"], verdict["unjudged"]
    answered = sorted(k for k in CHECKS if k not in unjudged)

    if failed:
        reachable, meaning = False, (
            f"this judge failed a real photograph on {failed}, so what those checks "
            f"measure is not 'reads as generated'. Tightening a render against them would "
            f"be chasing a standard nothing can meet")
    elif unjudged:
        reachable, meaning = True, (
            f"a real photograph failed nothing. {answered} discriminate, and a render this "
            f"judge blocks on any of them is a render that needs changing. {unjudged} "
            f"stayed unjudged because this control could not show them: unproven rather "
            f"than unreachable, and a control that shows them would settle it")
    else:
        reachable, meaning = True, (
            "a real photograph cleared every check, so the standard is reachable and a "
            "render this judge blocks is a render that needs changing")

    return {
        "control": image_url,
        "control_is": ("a real photograph from an observed benchmark listing, used to "
                       "check whether this judge can pass a photograph at all. It is not "
                       "copied, re-hosted or imitated, and what it depicts is never "
                       "described"),
        "verdict": verdict["verdict"],
        "failed": failed,
        "unjudged": unjudged,
        "discriminating": answered,
        "notes": verdict["notes"],
        "reachable": reachable,
        "what_it_means": meaning,
    }


def control_image(db, *, benchmark_key: str = "") -> str:
    """One real listing photograph from the observed benchmark, or "" if none is on file."""
    from sqlalchemy import desc, select

    from ..core.models import BenchmarkListing
    from ..intel import benchmarks

    key = benchmark_key or benchmarks.MJS_KEY
    with db.session() as s:
        for row in s.scalars(select(BenchmarkListing)
                             .where(BenchmarkListing.benchmark_key == key)
                             .order_by(desc(BenchmarkListing.last_seen)).limit(60)):
            for url in (row.detail or {}).get("image_urls") or []:
                if url:
                    return str(url)
    return ""


# Which of these checks a reference image can pass on to everything conditioned on it.
#
# A generator given a reference reproduces the person in it, including her skin. If the
# frozen portrait is itself airbrushed, every frame built from it is airbrushed too, and no
# amount of prompt language saying "visible pores, no smoothing" can outvote the picture --
# the prompt is a request and the reference is evidence.
#
# Only the checks that are properties of the *subject* are inheritable. Lighting, depth of
# field, invented text and sterile perfection are properties of the scene the new frame
# builds around her, so a reference failing those says nothing about the render.
INHERITED: tuple[str, ...] = ("skin_looks_real", "processing_is_restrained",
                              "hands_are_right", "anatomy_is_possible")


REFERENCE_ACTION = "visual.reference_realism"


def reference_realism(db, *, provider=None, paths: dict | None = None) -> dict:
    """Whether the frozen identity pack could ever produce a believable photograph.

    The question three blocked renders made unavoidable. Every model frame is conditioned
    on the pack's reference image and every one came back failing `skin_looks_real` and
    `processing_is_restrained`, against direction that names airbrushed skin explicitly.
    Two explanations need opposite fixes and a render cannot tell them apart:

      the generator will not do unretouched skin  -> change the method or the provider
      the reference she is copied from is already airbrushed -> re-make the pack

    So the reference is judged by the same standard its renders are held to. This is the
    third time this system has had to ask "is the thing being measured wrong, or is the
    measurement wrong" and the answer has been different each time, which is why it is
    asked with evidence rather than assumed.

    Read-only: it judges images already on file and generates nothing.
    """
    from . import freeze

    paths = paths if paths is not None else freeze.reference_paths(db)
    record = paths.get("pack_version")
    readings: dict[str, dict] = {}
    for frame in ("face", "body"):
        ref = paths.get(frame)
        if not ref:
            continue
        reading = judge(ref, db=db, provider=provider)
        verdict = gate(reading)
        readings[frame] = {"verdict": verdict["verdict"], "failed": verdict["failed"],
                           "unjudged": verdict["unjudged"], "why": verdict["why"],
                           "judged": bool(reading.get("judged")),
                           "error": reading.get("error", ""),
                           "notes": reading.get("notes", "")}

    if not readings:
        return {"judged": False, "pack_version": paths.get("pack_version"),
                "why": ("no frozen reference image could be materialised, so there is "
                        "nothing to judge. That is not a finding about the pack")}

    inherited = sorted({f for r in readings.values() for f in r["failed"]
                        if f in INHERITED})
    other = sorted({f for r in readings.values() for f in r["failed"]
                    if f not in INHERITED})
    # A frame the judge could not read at all is not a frame that passed. Kept separate
    # from `unjudged`, which is the honest "a portrait cannot show you yarn" answer -- one
    # is a question to ask again and the other is a question this image cannot answer.
    unreadable = sorted(f for f, r in readings.items() if not r["judged"])
    out = {
        "judged": True,
        "pack_version": paths.get("pack_version"),
        "frames": readings,
        "unreadable_frames": unreadable,
        "inheritable_failures": inherited,
        "other_failures": other,
        "inherited_checks": list(INHERITED),
        "verdict": ("pack_is_the_cause" if inherited else
                    "pack_is_not_the_cause" if all(r["verdict"] == "clear"
                                                   for r in readings.values())
                    else "pack_is_not_the_cause_of_the_inherited_failures"),
        "what_it_means": (
            f"the frozen reference fails {inherited} itself, so every frame conditioned "
            f"on it inherits them. No prompt can outvote the picture the generator is "
            f"copying: the pack is what has to change, and re-rendering is spend on a "
            f"question already answered" if inherited else
            "the frozen reference clears the checks a render inherits from it, so "
            "airbrushed skin in a render is the generator's doing rather than hers. The "
            "method or the provider is what has to change"),
    }
    _file_verdict(db, out)
    return out


def _file_verdict(db, out: dict) -> None:
    """Put the verdict on the audit log so nobody has to pay for it twice.

    The render path has to know whether the reference can produce a photograph, and it
    cannot make a vision call of its own inside a "should I render" decision -- that would
    be a spend to decide whether to spend. So the answer is filed where it can be read for
    nothing, keyed to the pack it was made about.
    """
    if db is None:
        return
    try:
        from ..core.models import AuditLog

        with db.session() as s:
            s.add(AuditLog(actor="creative_director", action=REFERENCE_ACTION,
                           detail=out))
    except Exception:  # noqa: BLE001 - a diagnostic that cannot file is still a diagnostic
        return


def filed_verdict(db, *, pack_version: str = "") -> dict | None:
    """The most recent filed reference verdict, and only for the pack it was made about.

    A verdict about a superseded pack says nothing about the one in force. Returning it
    anyway would block a new identity on the old one's failures, or -- worse -- clear a new
    one on the old one's pass, which is a gate reading evidence about something else.
    """
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    with db.session() as s:
        for row in s.scalars(select(AuditLog).where(AuditLog.action == REFERENCE_ACTION)
                             .order_by(desc(AuditLog.id)).limit(20)):
            detail = row.detail or {}
            if not detail.get("judged"):
                continue
            if pack_version and detail.get("pack_version") != pack_version:
                continue
            return detail
    return None


PORTRAIT_ACTION = "visual.carried_portrait_realism"


def _portrait_fingerprint(path: str) -> str:
    """The portrait's content hash. A verdict belongs to the bytes it was made about."""
    import hashlib
    from pathlib import Path

    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return ""


def carried_portrait(db, *, provider=None, path: str = "") -> dict:
    """Whether the committed portrait every pack build carries can pass what it passes on.

    `reference_pack.build` does not re-render the face. It carries
    `brief.approved_portrait()` -- a file in this repository -- because the owner approved
    that face and a revision about one body dimension must not put it back at risk. Which
    means the carried portrait's realism is not one pack's property: it is every future
    pack's, until the file changes.

    Production, 2026-09-23: that file is what the frozen pack's face frame is, and it came
    back `blocked` on `skin_looks_real` and `processing_is_restrained` on two independent
    runs. So every pack this code can build inherits an airbrushed face and would be
    refused by the freeze gate -- after rendering seven frames and paying for them.

    Keyed by content hash rather than by date or pack version. The answer cannot change
    while the bytes do not, so this is asked once ever rather than once per build, and a
    replaced portrait is a different question that gets asked again automatically.
    """
    from . import brief

    path = path or brief.approved_portrait()
    fingerprint = _portrait_fingerprint(path)
    if not fingerprint:
        return {"judged": False, "why": f"the carried portrait is not readable at {path}"}

    filed = filed_portrait_verdict(db, fingerprint=fingerprint)
    if filed:
        return filed

    reading = judge(path, db=db, provider=provider)
    verdict = gate(reading)
    out = {
        "judged": bool(reading.get("judged")),
        "fingerprint": fingerprint,
        "portrait": path,
        "verdict": verdict["verdict"],
        "failed": verdict["failed"],
        "unjudged": verdict["unjudged"],
        "inheritable_failures": sorted(f for f in verdict["failed"] if f in INHERITED),
        "notes": reading.get("notes", ""),
        "why_it_matters": (
            "every reference pack carries this exact file forward as its face frame, so a "
            "failure here is not one pack's problem -- it is every pack this code can "
            "build, until the file is replaced"),
    }
    if db is not None and out["judged"]:
        try:
            from ..core.models import AuditLog

            with db.session() as s:
                s.add(AuditLog(actor="creative_director", action=PORTRAIT_ACTION,
                               detail=out))
        except Exception:  # noqa: BLE001 - a diagnostic that cannot file is still one
            pass
    return out


def filed_portrait_verdict(db, *, fingerprint: str) -> dict | None:
    """The filed verdict for exactly these bytes, or nothing.

    Nothing means nobody has checked, which is not the same as a pass and not the same as
    a failure. Callers that must not spend read this and proceed when it is empty.
    """
    if db is None or not fingerprint:
        return None
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    with db.session() as s:
        for row in s.scalars(select(AuditLog).where(AuditLog.action == PORTRAIT_ACTION)
                             .order_by(desc(AuditLog.id)).limit(20)):
            detail = row.detail or {}
            if detail.get("judged") and detail.get("fingerprint") == fingerprint:
                return detail
    return None
