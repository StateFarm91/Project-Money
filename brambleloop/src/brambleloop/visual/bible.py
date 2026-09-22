"""The character bible: the half of #73 that is not a set of photographs.

The reference pack answers *who she is* -- face views, hair and eye descriptors, measured
proportions -- and `identity.drift_check` enforces it. #73 names four more things the pack
must carry and the pack did not: **makeup range, expression range, wardrobe rules and
lighting language**, plus **rejected drift examples**. Those are the styling half, and
without them the pack pins the woman while leaving everything around her free.

That gap is not cosmetic. The identity gate would accept a frame of exactly the right woman
in heavy editorial glamour makeup under coloured rim light wearing a printed dress that
competes with the crochet, because every dimension it measures would still match. #202 is
the requirement that says such a frame is wrong, and until now its rules lived in `brief.py`
as language for a prompt -- a rule that is asked for but never checked, which is the same
defect as a gate reading configuration instead of demonstrated capability.

So the four parts are written here **as closed questions about a rendered frame**, answered
by a vision model that never saw the prompt, exactly as identity and realism already are.
The prompt asks; the bible checks; the generator is never asked whether it complied.

**Three-valued, and unjudged is never within range.** A frame that does not show enough to
tell is a question to ask again, which is a different fix from a frame that broke a rule.

**Rejected drift examples are read, not written.** #73 asks the pack to carry examples of
drift that was refused. Inventing a plausible-sounding list would be the fabricated evidence
this company does not produce, and it would also be useless: the examples worth keeping are
the ones that actually happened here. `rejected_drift` reads them out of the audit log --
the pack builds that could not be frozen and why, and the finalists the owner declined --
so the list grows from what was really refused and is empty when nothing has been.

**Changing this is a brand-version event.** `BIBLE_VERSION` moves when the rules move, for
the same reason `PACK_VERSION` does: a frame judged under earlier rules is evidence about
those rules, and reading it back as current is how a tightened standard quietly never runs.
"""
from __future__ import annotations

import json

from ..core.resilience import PermanentError, TransientError

TASK = "asset_inspection"
MAX_TOKENS = 900

BIBLE_VERSION = "v1-makeup-expression-wardrobe-lighting-and-what-was-refused"

# The four parts #73 names. Each carries the range in the brief's own register, what falls
# outside it, and the closed questions that decide which side of the line a frame is on.
#
# `True` always means the frame is *within* range, so the arithmetic matches every other
# check here: a False is a breach and a missing key is a question nobody could answer.
AXES: dict[str, dict] = {
    "makeup": {
        "range": ("bare to soft natural daytime: evened skin tone, groomed brows, a little "
                  "definition around the eyes, a lip close to her own colour. Seasonal "
                  "warmth is allowed -- a deeper lip in winter styling -- as long as it "
                  "reads as the same woman on an ordinary day"),
        "outside": ("editorial or glamour makeup, heavy contour and highlight, a strong or "
                    "dark lip as the subject of the frame, graphic or winged liner, "
                    "glitter, false lashes, or any makeup that restructures the face the "
                    "identity gate measures"),
        "questions": {
            "makeup_is_daytime_natural": (
                "the makeup is bare or soft and natural, of the kind somebody wears on an "
                "ordinary day, rather than editorial or evening makeup"),
            "face_is_not_restructured": (
                "no heavy contouring, highlighting or reshaping changes the apparent "
                "structure of her cheekbones, nose or jaw"),
            "makeup_is_not_the_subject": (
                "the makeup is not the most striking thing in the frame -- no graphic "
                "liner, glitter, false lashes or dominant lip colour drawing the eye"),
        },
    },
    "expression": {
        "range": ("relaxed and warm: a neutral resting expression, a soft closed-mouth "
                  "smile, an open genuine smile, or a calm look away from the camera. She "
                  "is approachable and unposed"),
        "outside": ("the glamour register -- parted lips, sultry or challenging looks, a "
                    "chin-down stare -- and equally anything theatrical: a laugh that "
                    "closes her eyes, exaggerated delight, distress or vacancy. A closed "
                    "or obscured face also takes the facial identity floor with it"),
        "questions": {
            "expression_is_relaxed_and_warm": (
                "her expression is relaxed and warm -- neutral, softly smiling or openly "
                "smiling -- rather than posed, sultry, theatrical or distressed"),
            "face_is_open_and_readable": (
                "her eyes are open and her face is unobscured and readable, rather than "
                "closed, turned away, or hidden by hair, hands or the product"),
        },
    },
    "wardrobe": {
        "range": ("the crochet is the only styled item. Everything else is plain, "
                  "unpatterned, low in contrast and ordinary for daytime retail -- simple "
                  "knits, plain trousers or a plain skirt, in colours that sit under the "
                  "product rather than beside it. Seasonal layering is allowed"),
        "outside": ("competing prints or patterns, saturated colours that fight the "
                    "product, visible branding or slogans, more than one small piece of "
                    "jewellery, styling that reads as fashion editorial rather than "
                    "lifestyle, and anything that obscures the shoulder, chest, torso and "
                    "waist line the morphology floor has to read"),
        "questions": {
            "crochet_is_the_only_styled_item": (
                "the crocheted piece is the only styled or decorative thing she is "
                "wearing; everything else is plain and quiet"),
            "nothing_competes_with_the_product": (
                "no print, pattern, saturated colour, slogan or jewellery competes with "
                "the crochet for attention"),
            "no_visible_branding": (
                "no logo, brand mark or readable text appears on anything she wears"),
            "body_line_is_not_obscured": (
                "her shoulders, chest, torso and waist are not hidden by styling choices "
                "-- draped layers, crossed arms, held props -- beyond what the crocheted "
                "product itself covers"),
            "register_is_lifestyle_not_editorial": (
                "the styling reads as premium lifestyle photography a shopper would "
                "recognise, not as high-fashion editorial or glamour"),
        },
    },
    "lighting": {
        "range": ("soft directional daylight with one dominant source: window light, open "
                  "shade, an overcast afternoon. Gentle falloff, neutral to slightly warm "
                  "white balance, shadows soft enough to be kind and directional enough to "
                  "model the fabric"),
        "outside": ("hard studio beauty lighting, coloured gels, rim or hair light used "
                    "for glamour, heavy vignette, and the flat frontal ringlight that "
                    "erases every stitch. Flat light is not only a matter of taste -- it "
                    "removes the shadow that makes crochet texture legible, so it is a "
                    "product-truth failure wearing a styling costume"),
        "questions": {
            "light_is_soft_and_directional": (
                "the light is soft and comes mainly from one direction, like daylight, "
                "rather than hard studio lighting or flat frontal light"),
            "colour_is_neutral_or_warm": (
                "the white balance is neutral to slightly warm, with no coloured gels or "
                "unnatural colour cast"),
            "no_glamour_lighting_effects": (
                "no rim light, hair light, lens flare or heavy vignette is used for effect"),
            "stitch_texture_is_modelled": (
                "the light casts enough shadow across the crochet for individual stitches "
                "and the fabric's texture to be visible"),
        },
    },
}

# Every question, flattened, so a caller can ask for the whole set without walking the axes.
QUESTIONS: dict[str, str] = {
    key: what for axis in AXES.values() for key, what in axis["questions"].items()}

AXIS_OF: dict[str, str] = {
    key: name for name, axis in AXES.items() for key in axis["questions"]}

SYSTEM = (
    "You are a photo editor at a premium craft brand, checking one image against the "
    "brand's styling rules. You are not judging whether the photograph is good or whether "
    "the woman is attractive. Report only what you can actually see, and omit any question "
    "the image does not show you enough to answer."
)


def prompt(axes: tuple[str, ...] | None = None) -> str:
    asked = axes or tuple(AXES)
    lines = [
        "Answer as JSON. For each key give true if the statement holds, false if it does "
        "not, and omit the key entirely if the image does not show you enough to judge it. "
        "An omitted key is a useful answer; a guessed one is not.",
        "",
    ]
    for key, what in QUESTIONS.items():
        if AXIS_OF[key] in asked:
            lines.append(f'  "{key}": {what}')
    lines.append("")
    lines.append('Add "notes": one short sentence naming the clearest styling problem you '
                 "saw, or an empty string.")
    return "\n".join(lines)


def judge(image_ref: str, *, db=None, provider=None,
          axes: tuple[str, ...] | None = None) -> dict:
    """Ask a model what it can see, about the axes this frame is in a position to answer.

    `axes` exists because of what a close crop did when it was asked anyway. The detail
    frame -- a hat filling the frame -- first returned `unjudged` on wardrobe, which the
    gate correctly refused to pass; then, on the next render, it answered *False*. A frame
    that cannot see an outfit saying the outfit is wrong is not evidence about the outfit,
    and under the rule that a failure anywhere blocks everywhere it became a false block on
    the whole sequence. `brief.FRAME_AUTHORITY` already draws this line for the identity
    dimensions: a frame is asked only what it is in a position to know.
    """
    from ..finance import spend_report
    from ..gateway import anthropic as gw

    provider = provider or gw.provider_for(TASK)
    try:
        response = provider.see(SYSTEM, prompt(axes), [image_ref], max_tokens=MAX_TOKENS)
    except (PermanentError, TransientError) as exc:
        return {"judged": False, "error": str(exc)[:200], "answers": {}}

    if db is not None:
        cost = round(response.input_tokens * provider.cost_per_1k_input_cad / 1000
                     + response.output_tokens * provider.cost_per_1k_output_cad / 1000, 8)
        spend_report.record(
            db, agent="creative_director", amount_cad=cost, estimated_cad=cost,
            purpose=TASK, provider="anthropic", model=provider.model,
            department="creative", tokens_in=response.input_tokens,
            tokens_out=response.output_tokens,
            detail={"price_basis": "assumed", "check": "character_bible",
                    "bible_version": BIBLE_VERSION})

    import re

    match = re.search(r"\{.*\}", response.text or "", re.S)
    if not match:
        return {"judged": False, "error": "no JSON in the styling answer", "answers": {}}
    try:
        parsed = json.loads(match.group(0))
    except ValueError as exc:
        return {"judged": False, "error": f"unreadable: {exc}"[:200], "answers": {}}

    # The closed vocabulary and real booleans only. A string "true" answers a different
    # question, and coercing it would invent an opinion the model did not give.
    asked = axes or tuple(AXES)
    answers = {k: bool(parsed[k]) for k in QUESTIONS
               if k in parsed and isinstance(parsed[k], bool) and AXIS_OF[k] in asked}
    return {"judged": True, "answers": answers, "axes": list(asked),
            "notes": str(parsed.get("notes") or "")[:240],
            "bible_version": BIBLE_VERSION}


def assess(reading: dict, *, axes: tuple[str, ...] | None = None) -> dict:
    """Each axis on its own, because they fail for different reasons and need different fixes.

    An averaged styling score would let a frame with correct makeup and coloured gels come
    out acceptable, which is the shape of every defect this system keeps finding: a verdict
    computed across dimensions that do not substitute for one another.
    """
    answers = dict(reading.get("answers") or {})
    asked = tuple(axes or reading.get("axes") or tuple(AXES))
    out: dict[str, dict] = {}
    for name, axis in AXES.items():
        if name not in asked:
            # Not asked of this frame, which is a different thing from asked and unanswered.
            out[name] = {"verdict": "not_asked", "breached": [], "unjudged": [],
                         "why": f"a frame of this kind cannot see {name}",
                         "range": axis["range"]}
            continue
        keys = list(axis["questions"])
        breached = sorted(k for k in keys if answers.get(k) is False)
        unread = sorted(k for k in keys if k not in answers)
        if breached:
            verdict, why = "outside_range", (
                f"{name} is outside the bible's range on {breached}")
        elif unread:
            verdict, why = "unjudged", (
                f"{unread} could not be read from this frame. Unjudged is not within "
                f"range -- it is a question to ask again")
        else:
            verdict, why = "within_range", f"{name} is within the bible's range"
        out[name] = {"verdict": verdict, "breached": breached, "unjudged": unread,
                     "why": why, "range": axis["range"]}
    return out


def gate(reading: dict, *, axes: tuple[str, ...] | None = None) -> dict:
    """Three-valued, and unjudged is never a pass. An axis not asked is not judged at all."""
    axes = assess(reading, axes=axes)
    outside = sorted(k for k, v in axes.items() if v["verdict"] == "outside_range")
    unjudged = sorted(k for k, v in axes.items() if v["verdict"] == "unjudged")

    asked = sorted(k for k, v in axes.items() if v["verdict"] != "not_asked")
    if outside:
        verdict, why = "blocked", (
            f"styling is outside the character bible on {outside}. "
            f"{reading.get('notes', '')}".strip())
    elif not reading.get("judged"):
        verdict, why = "unjudged", (
            f"the styling judge did not answer: {reading.get('error', 'no reason given')}")
    elif unjudged:
        verdict, why = "unjudged", (
            f"{unjudged} could not be judged from this frame. Unjudged is not within range")
    else:
        verdict, why = "clear", "every axis of the character bible is within range"

    return {"verdict": verdict, "outside": outside, "unjudged": unjudged,
            "asked": asked,
            "axes": axes, "notes": reading.get("notes", ""), "why": why,
            "bible_version": BIBLE_VERSION,
            "requirements": ("#73 -- the pack carries makeup range, expression range, "
                             "wardrobe rules and lighting language, and every model asset "
                             "is compared against them; #202 -- the product stays the "
                             "commercial subject and the register is lifestyle, not "
                             "glamour")}


# The prompt language that asks for this in the first place. Kept beside the questions so
# what is asked for and what is checked cannot drift into two different standards, which is
# the same reason `photoreal.DIRECTION` lives beside `photoreal.CHECKS`.
def direction() -> str:
    return (
        f"Makeup: {AXES['makeup']['range']}. Not {AXES['makeup']['outside']}. "
        f"Expression: {AXES['expression']['range']}. "
        f"Wardrobe: {AXES['wardrobe']['range']}. "
        f"Lighting: {AXES['lighting']['range']}."
    )


def frozen_from(db) -> str:
    """Which pack build became canonical, or "" when the record does not say.

    Read rather than inferred. The one thing that must not happen here is guessing that
    the newest freezable build is the canonical one and then listing the real canonical
    build as superseded -- a rejected-drift list that names the approved identity as drift
    would be worse than no list.
    """
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    with db.session() as s:
        for row in s.scalars(select(AuditLog).where(AuditLog.action == "model.frozen")
                             .order_by(desc(AuditLog.id)).limit(5)):
            version = ((row.detail or {}).get("freeze") or {}).get("pack_version")
            if version:
                return str(version)
    return ""


def rejected_drift(db, *, limit: int = 12) -> dict:
    """What was actually refused, read out of the record rather than composed.

    #73 asks the pack to carry rejected drift examples. The useful ones are the refusals
    this company really made, each with the measurement that caused it -- a pack build that
    could not be frozen because a dimension was unreadable, a build that was sound but
    superseded, and the finalists the owner declined. A hand-written list of plausible
    failures would be evidence nobody gathered, and this company does not produce those.
    """
    from . import brief, freeze, tournament

    examples: list[dict] = []
    canonical = frozen_from(db)

    for row in freeze.candidates_on_file(db, limit=limit):
        if not row["freezable"]:
            examples.append({
                "kind": "pack_build_refused",
                "at": row["at"],
                "pack_version": row["pack_version"],
                "unstated_dimensions": row["missing"],
                "why_refused": row["why_not"],
                "lesson": ("a pack with an unreadable dimension would freeze a floor that "
                           "can never fail, so the dimension was re-rendered rather than "
                           "written down as though it had been measured"),
            })
        elif canonical and row["pack_version"] != canonical:
            examples.append({
                "kind": "pack_superseded",
                "at": row["at"],
                "pack_version": row["pack_version"],
                "why_refused": (f"measurable and sound, but {canonical} is the build the "
                                f"owner approved"),
                "lesson": ("a superseded pack stays as evidence and is never eligible for "
                           "automatic selection; nothing promotes it and select_canonical "
                           "refuses a second canonical outright"),
            })

    # And the field the owner was shown and declined, out of the tournament's own row.
    for key in _declined_finalists(db, limit=limit):
        examples.append({
            "kind": "candidate_declined_by_owner",
            "key": key,
            "why_refused": brief.REJECTED_FINALISTS_NOTE,
            "lesson": ("the tournament exists to make 'none of these' available. A "
                       "candidate that becomes canonical by topping a table is an "
                       "identity nobody chose"),
        })

    return {
        "examples": examples[:limit],
        "count": len(examples),
        "canonical_pack_version": canonical or None,
        "read_from": f"the audit log ({tournament.TOURNAMENT_ACTION} and the pack builds), "
                     f"not composed",
        "note": ("empty means nothing has been refused in this record yet, which is a fact "
                 "about the record rather than a claim that drift cannot happen"),
        "never_eligible": ("superseded packs and declined candidates stay as evidence and "
                           "are never eligible for automatic selection"),
    }


def _declined_finalists(db, *, limit: int) -> list[str]:
    """The finalists the owner was shown, once the owner has supplied their own concept.

    Guarded on `owner_candidate_supplied`, because a finalist is only *declined* after the
    owner has answered. Listing a field that is still open as rejected would invent a
    decision nobody made -- the same defect in the opposite direction.
    """
    from sqlalchemy import desc, select

    from ..core.models import AuditLog
    from . import brief, tournament

    if not brief.owner_candidate_supplied():
        return []

    with db.session() as s:
        for row in s.scalars(
                select(AuditLog).where(AuditLog.action == tournament.TOURNAMENT_ACTION)
                .order_by(desc(AuditLog.id)).limit(5)):
            finalists = (row.detail or {}).get("finalists") or []
            keys = [str(f.get("key") or f.get("candidate") or "") for f in finalists
                    if isinstance(f, dict)]
            keys = [k for k in keys if k]
            if keys:
                return keys[:limit]
    return []


def state(db=None) -> dict:
    """The bible as the pack carries it, for the owner and for #73's reconciliation."""
    out = {
        "bible_version": BIBLE_VERSION,
        "axes": {name: {"range": a["range"], "outside": a["outside"],
                        "questions": sorted(a["questions"])}
                 for name, a in AXES.items()},
        "enforced_how": ("every axis is answered about the rendered frame by a vision "
                         "model that never saw the prompt, and blocks the frame when it "
                         "is outside range or could not be read"),
        "changing_it": ("moving these rules moves BIBLE_VERSION, which is a brand-version "
                        "event: a frame judged under the earlier rules is evidence about "
                        "those rules"),
    }
    if db is not None:
        out["rejected_drift"] = rejected_drift(db)
    return out
