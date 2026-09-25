"""The durable half of the canonical model, and the gate that actually blocks (#200, #201).

`visual/identity.py` had the whole design: two states with no path between them that does not
go through the owner, a reference pack that pins the fields which drift, and a drift check
that reports `unavailable` rather than passing when it has nothing to compare against.

It had no callers. Not one, anywhere in the codebase.

That is this build's most familiar failure in its most flattering disguise: a table nothing
reads is documentation, and a gate nothing invokes is a good intention with tests. The module
would have gone on being correct and unconsulted while the first model-bearing listing shipped
past it.

So this module is only the two joins that were missing.

**Persistence.** A pack held in memory is gone after the next deploy, and a canonical model
who disappears on a redeploy is not locked to anything. Candidates and the frozen pack live in
`model_identities`, and `select` still refuses to promote one without the owner.

**The release join.** `gate_frames` is called from the listing-image build, and it blocks a
model-bearing frame whose identity cannot be verified. With no canonical pack that is every
model-bearing frame, which is correct: #201 makes drift a release-blocking defect, and the
moment the check is allowed to shrug is the moment it stops being one. Frames that carry no
model are untouched, so a catalogue of product-only renders is unaffected until the day the
first model frame is built -- which is exactly when this has to bite.
"""
from __future__ import annotations

from ..core.resilience import PermanentError, TransientError
from . import identity

# What the observer is asked to read off a rendered face. Deliberately the drift dimensions
# rather than the full pack: the pack is what the owner approved, and this is what a single
# image can be asked about without inventing detail.
OBSERVE_FIELDS: tuple[str, ...] = identity.DRIFT_DIMENSIONS

TASK = "asset_inspection"
# Who is spending, named once per path rather than as a literal inside the ledger call.
# Every spend path in this module wrote a `spend_report.record` row naming its agent and
# called nothing before the provider, so the agent was a fact the bill knew and the guard
# did not. `check_budget` and `spend_report.record` now read the same constant, because an
# agent ceiling enforced against one name and billed against another enforces nothing.
#
# Two names, deliberately, because the two are different work under different permissions:
# reading drift off a rendered face is quality's, and the hair comparison is the creative
# director's gate on a revision. Both were already billed this way before this change; this
# only makes the pre-call check agree with the row.
OBSERVE_AGENT = "quality_director"
HAIR_AGENT = "creative_director"
# Thirteen dimensions and a phrase each. 300 fitted the five face dimensions it was written
# for; the body half would have been cut off mid-object and refused as unparseable, which is
# the same defect that cost sixteen benchmark samples.
OBSERVE_MAX_TOKENS = 700

OBSERVE_SYSTEM = (
    "You are describing one person in a photograph so that the same person can be recognised "
    "in another photograph -- the whole person, not only the face. Describe only what is "
    "actually visible. Clothing, pose and camera angle change apparent silhouette, so judge "
    "what the body is rather than what the garment suggests, and when a proportion is "
    "genuinely obscured say so instead of estimating it."
)


class RegistryRefused(ValueError):
    """A write that would let an identity be chosen by something other than the owner."""


# ---------------------------------------------------------------------------
# Persistence


def _row_to_pack(row) -> identity.ReferencePack:
    return identity.ReferencePack(version=row.version, fields=dict(row.fields or {}),
                                  approved_by_owner_at=row.approved_by_owner_at)


def packs(db) -> list[identity.ReferencePack]:
    from sqlalchemy import select

    from ..core.models import ModelIdentity

    with db.session() as s:
        rows = list(s.scalars(select(ModelIdentity).where(
            ModelIdentity.state == identity.CANONICAL)))
        return [_row_to_pack(r) for r in rows if r.approved_by_owner_at]


def canonical_pack(db) -> identity.ReferencePack | None:
    return identity.canonical(packs(db))


def candidates(db) -> list[identity.Candidate]:
    from sqlalchemy import select

    from ..core.models import ModelIdentity

    with db.session() as s:
        rows = list(s.scalars(select(ModelIdentity).where(
            ModelIdentity.state == identity.CANDIDATE)))
        return [identity.Candidate(key=r.key, fields=dict(r.fields or {}), state=r.state,
                                   note=r.note) for r in rows]


def record_candidate(db, key: str, *, fields: dict, image_refs: list[str] | None = None,
                     note: str = "") -> int:
    """Store one generated face. A candidate, and nothing more."""
    from sqlalchemy import select

    from ..core.models import ModelIdentity

    with db.session() as s:
        row = s.scalar(select(ModelIdentity).where(ModelIdentity.key == key))
        if row is None:
            row = ModelIdentity(key=key)
            s.add(row)
        if row.state == identity.CANONICAL:
            raise RegistryRefused(
                f"{key!r} is the canonical identity. Rewriting her as a candidate is a "
                f"redesign wearing an import's clothes (#200)")
        row.state = identity.CANDIDATE
        row.fields = dict(fields or {})
        row.image_refs = list(image_refs or [])
        row.note = note or row.note
        s.flush()
        return row.id


def select_canonical(db, key: str, *, owner_approved: bool) -> identity.ReferencePack:
    """Freeze one candidate. Refuses without the owner, and refuses a second."""
    from sqlalchemy import select

    from ..core.models import ModelIdentity

    existing = canonical_pack(db)
    with db.session() as s:
        row = s.scalar(select(ModelIdentity).where(ModelIdentity.key == key))
        if row is None:
            raise RegistryRefused(f"no candidate {key!r} has been recorded")
        candidate = identity.Candidate(key=row.key, fields=dict(row.fields or {}),
                                       state=row.state, note=row.note)
        pack = identity.select(candidate, owner_approved=owner_approved, existing=existing)
        # The pack carries its own portrait. A reference pack without a reference image can
        # neither condition a generation nor be compared against one -- it is a description
        # of a woman nobody can produce, which is the opposite of a lock.
        if row.image_refs:
            pack = identity.ReferencePack(
                version=pack.version,
                fields={**pack.fields, "reference_image": row.image_refs[0]},
                approved_by_owner_at=pack.approved_by_owner_at)
            row.fields = dict(pack.fields)
        row.state = identity.CANONICAL
        row.version = pack.version
        row.approved_by_owner_at = pack.approved_by_owner_at
        return pack


# ---------------------------------------------------------------------------
# Observation


def observe_prompt() -> str:
    """The observer's question, asked about the whole person and honest about what is hidden.

    The `unmeasurable` instruction is the load-bearing one. A model asked for a waist
    proportion under a loose cardigan will produce a plausible phrase, that phrase will match
    or not by accident, and the resulting verdict is a coin toss wearing a measurement's
    clothes. The first reference-conditioned trial failed precisely here: the face was right,
    the chest was not, and nothing was looking.
    """
    return (
        "Reply with a single JSON object and nothing else, one key per item below. Each "
        "value is a short literal phrase describing what you can actually see, or the exact "
        'string "unmeasurable" when clothing, pose, crop or angle means you cannot judge it '
        "honestly. Do not estimate a proportion you cannot see; do not infer the body from "
        "the garment. If the photograph contains no person, reply exactly "
        '{"no_person": true}.\n\n'
        "Face and head:\n"
        + "\n".join(f"- {f}" for f in identity.FACE_DIMENSIONS)
        + "\n\nWhole-person morphology (the body itself, not the clothing):\n"
        + "\n".join(f"- {f}" for f in identity.MORPHOLOGY_DIMENSIONS))


def observe(db, image_ref: str, *, provider=None) -> dict:
    """Read the drift dimensions off one rendered face.

    Routed through the task table like every other model call, and billed. Returns an empty
    dict when nothing could be read -- which `drift_check` treats as maximum drift, because
    an unmeasured dimension is not a matching one.
    """
    import json

    from ..finance import spend_report
    from ..gateway import anthropic as gw

    provider = provider or gw.provider_for(TASK)
    estimate, held = 0.0, None
    try:
        # Checked before the call, not merely billed after it. `BudgetExceeded` and its
        # `AgentCeilingExceeded` subclass are both `PermanentError`, so a refusal arrives at
        # the same `except` as a provider failure and leaves the same `{"error": ...}` --
        # which `drift_check` already treats as maximum drift. An unmeasured dimension is not
        # a matching one, and a dimension unmeasured because the day's permission is spent is
        # still unmeasured.
        if db is not None:
            budget = gw.check_budget(
                db, model=provider.model,
                input_tokens=len(observe_prompt()) // 4 + gw.IMAGE_TOKENS_ESTIMATE,
                max_tokens=OBSERVE_MAX_TOKENS, agent=OBSERVE_AGENT, purpose=TASK)
            estimate, held = budget["estimate_cad"], budget["reservation_id"]
        response = provider.see(OBSERVE_SYSTEM, observe_prompt(), [image_ref],
                                max_tokens=OBSERVE_MAX_TOKENS)
    except gw.BudgetExceeded as exc:
        # A ceiling refusal is marked so a *loop* can tell it from a model that failed.
        # Both are "nobody looked", and `identity.drift_check` is right to read either as
        # not-a-match -- but a caller that goes on to the next scene after this one spends
        # another image render to ask a question the budget has already refused, and scores
        # a finalist down for it. `ceiling` is additive: every existing reader still sees an
        # `error` and still treats the dimension as unmeasured.
        if db is not None:
            gw.release_reservation(db, held)
        return {"error": str(exc)[:200],
                "ceiling": ("agent_daily_ceiling"
                            if isinstance(exc, gw.AgentCeilingExceeded)
                            else "monthly_model_ceiling")}
    except (PermanentError, TransientError) as exc:
        if db is not None:
            gw.release_reservation(db, held)
        return {"error": str(exc)[:200]}

    if db is not None:
        cost = round(
            response.input_tokens * provider.cost_per_1k_input_cad / 1000
            + response.output_tokens * provider.cost_per_1k_output_cad / 1000, 8)
        gw.release_reservation(db, held, actual_cad=cost)
        spend_report.record(
            db, agent=OBSERVE_AGENT, amount_cad=cost, estimated_cad=estimate,
            purpose=TASK, provider="anthropic", model=provider.model,
            department="quality", tokens_in=response.input_tokens,
            tokens_out=response.output_tokens, detail={"price_basis": "assumed"})

    body = (response.text or "").strip()
    if body.startswith("```"):
        body = body.split("\n", 1)[-1].rsplit("```", 1)[0]
    try:
        parsed = json.loads(body)
    except ValueError:
        return {"error": f"the observer did not answer with JSON: {body[:120]!r}"}
    if not isinstance(parsed, dict):
        return {"error": "the observer answered with something that is not an object"}
    return parsed


COMPARE_SYSTEM = (
    "You are deciding whether two photographs show the same woman -- the same whole person, "
    "not merely a similar face. You know that clothing, pose, lighting and camera angle "
    "change how a body looks without changing the body, and that a convincing face is "
    "exactly what stops people checking the rest of the frame."
)

COMPARE_MAX_TOKENS = 700


def compare_prompt() -> str:
    """Ask per dimension whether it is the same person, not what each picture looks like.

    This replaced a comparison of two free-text descriptions by string equality, which
    reported every dimension of every scene of every finalist as drift -- because two honest
    descriptions of the same woman are never identical strings. The question a judge can
    actually answer is the one being asked: same, different, or you cannot tell.
    """
    return (
        "The FIRST image is the approved reference photograph. The SECOND is a new "
        "photograph that is supposed to show the same woman.\n\n"
        "Reply with a single JSON object and nothing else, one key per item below, each "
        'exactly one of: "match" (the same person on this dimension), "drift" (visibly a '
        'different person on this dimension), or "unmeasurable" (clothing, pose, crop or '
        "angle means you cannot judge it honestly).\n\n"
        "Judge the body itself, not the garment: a loose sweater is not a wider torso, and "
        "a fitted one is not a narrower waist. Where the clothing genuinely hides a "
        'proportion, answer "unmeasurable" -- do not guess, and do not let the face carry '
        "the body.\n\n"
        "Face and head:\n"
        + "\n".join(f"- {d}" for d in identity.FACE_DIMENSIONS)
        + "\n\nWhole-person morphology:\n"
        + "\n".join(f"- {d}" for d in identity.MORPHOLOGY_DIMENSIONS))


def compare_identity(db, reference_ref: str, candidate_ref: str, *, provider=None) -> dict:
    """Per-dimension verdicts from a judge shown both photographs."""
    import json

    from ..finance import spend_report
    from ..gateway import anthropic as gw

    if not reference_ref or not candidate_ref:
        return {"error": "a comparison needs two images"}

    provider = provider or gw.provider_for(TASK)
    estimate, held = 0.0, None
    try:
        # Two images, so two image allowances in the estimate. Sizing a two-image call on one
        # image's tokens is how a guard stays green while the bill doubles -- the same
        # optimism the padded estimator exists to refuse.
        if db is not None:
            budget = gw.check_budget(
                db, model=provider.model,
                input_tokens=len(compare_prompt()) // 4 + 2 * gw.IMAGE_TOKENS_ESTIMATE,
                max_tokens=COMPARE_MAX_TOKENS, agent=OBSERVE_AGENT, purpose=TASK)
            estimate, held = budget["estimate_cad"], budget["reservation_id"]
        response = provider.see(COMPARE_SYSTEM, compare_prompt(),
                                [reference_ref, candidate_ref],
                                max_tokens=COMPARE_MAX_TOKENS)
    except gw.BudgetExceeded as exc:
        # A ceiling refusal is marked so a *loop* can tell it from a model that failed.
        # Both are "nobody looked", and `identity.drift_check` is right to read either as
        # not-a-match -- but a caller that goes on to the next scene after this one spends
        # another image render to ask a question the budget has already refused, and scores
        # a finalist down for it. `ceiling` is additive: every existing reader still sees an
        # `error` and still treats the dimension as unmeasured.
        if db is not None:
            gw.release_reservation(db, held)
        return {"error": str(exc)[:200],
                "ceiling": ("agent_daily_ceiling"
                            if isinstance(exc, gw.AgentCeilingExceeded)
                            else "monthly_model_ceiling")}
    except (PermanentError, TransientError) as exc:
        if db is not None:
            gw.release_reservation(db, held)
        return {"error": str(exc)[:200]}

    if db is not None:
        cost = round(
            response.input_tokens * provider.cost_per_1k_input_cad / 1000
            + response.output_tokens * provider.cost_per_1k_output_cad / 1000, 8)
        gw.release_reservation(db, held, actual_cad=cost)
        spend_report.record(
            db, agent=OBSERVE_AGENT, amount_cad=cost, estimated_cad=estimate,
            purpose=TASK, provider="anthropic", model=provider.model,
            department="quality", tokens_in=response.input_tokens,
            tokens_out=response.output_tokens, detail={"price_basis": "assumed"})

    body = (response.text or "").strip()
    if body.startswith("```"):
        body = body.split("\n", 1)[-1].rsplit("```", 1)[0]
    try:
        parsed = json.loads(body)
    except ValueError:
        return {"error": f"the judge did not answer with JSON: {body[:120]!r}"}

    out = {}
    for dimension in identity.DRIFT_DIMENSIONS:
        value = str(parsed.get(dimension, "")).strip().lower()
        # Anything that is not one of the three answers is unmeasurable, never a match. A
        # judge that wandered off the vocabulary has not said the woman is the same.
        out[dimension] = value if value in identity.VERDICTS else identity.UNMEASURABLE
    return out


# ---------------------------------------------------------------------------
# The gate (#201)


HAIR_SYSTEM = (
    "You are comparing the hair of one woman in two photographs. Hair identity and hair "
    "styling are different things: the colour, the length and the cut are who she is, and "
    "whether it is up or down, tied back or loose, is how it was arranged that day. A "
    "woman with her hair up is not a different woman."
)

HAIR_MAX_TOKENS = 300


def hair_prompt() -> str:
    return (
        "Both images show the same woman on different occasions.\n\n"
        "Answer as JSON with exactly these keys:\n"
        '  "colour": "match", "drift" or "unmeasurable" -- the hair colour, including any '
        "highlights or depth of tone\n"
        '  "length": "match", "drift" or "unmeasurable" -- how long the hair is when it '
        "hangs loose. Judge the hair, not the arrangement: hair worn up is not shorter\n"
        '  "cut": "match", "drift" or "unmeasurable" -- the cut, including any fringe or '
        "layering\n"
        '  "arrangement_differs": true or false -- whether it is simply worn differently '
        "(up versus down, tied versus loose)\n"
        '  "note": one short sentence on what you saw\n'
    )


def compare_hair(db, reference_ref: str, candidate_ref: str, *, provider=None) -> dict:
    """Is this the same hair, separately from how it was arranged?

    Asked because the revision check flagged `hair` as changed between the approved body
    references and the revised ones, and the pictures show why: the colour, the length and
    the cut are identical and it is up in one pair and down in the other. The owner's
    preserve list says hair and colouring, and the brief itself says she wears it up or
    down -- so conflating styling with identity would fail a revision for doing what the
    brief allows. One dimension, one question, because this is the only dimension in the
    pack where the arrangement is a legitimate degree of freedom.
    """
    import json

    from ..finance import spend_report
    from ..gateway import anthropic as gw

    provider = provider or gw.provider_for(TASK)
    estimate, held = 0.0, None
    try:
        if db is not None:
            budget = gw.check_budget(
                db, model=provider.model,
                input_tokens=len(hair_prompt()) // 4 + 2 * gw.IMAGE_TOKENS_ESTIMATE,
                max_tokens=HAIR_MAX_TOKENS, agent=HAIR_AGENT, purpose=TASK)
            estimate, held = budget["estimate_cad"], budget["reservation_id"]
        response = provider.see(HAIR_SYSTEM, hair_prompt(),
                                [reference_ref, candidate_ref], max_tokens=HAIR_MAX_TOKENS)
    except gw.BudgetExceeded as exc:
        # A ceiling refusal is marked so a *loop* can tell it from a model that failed.
        # Both are "nobody looked", and `identity.drift_check` is right to read either as
        # not-a-match -- but a caller that goes on to the next scene after this one spends
        # another image render to ask a question the budget has already refused, and scores
        # a finalist down for it. `ceiling` is additive: every existing reader still sees an
        # `error` and still treats the dimension as unmeasured.
        if db is not None:
            gw.release_reservation(db, held)
        return {"error": str(exc)[:200],
                "ceiling": ("agent_daily_ceiling"
                            if isinstance(exc, gw.AgentCeilingExceeded)
                            else "monthly_model_ceiling")}
    except (PermanentError, TransientError) as exc:
        if db is not None:
            gw.release_reservation(db, held)
        return {"error": str(exc)[:200]}

    if db is not None:
        cost = round(response.input_tokens * provider.cost_per_1k_input_cad / 1000
                     + response.output_tokens * provider.cost_per_1k_output_cad / 1000, 8)
        # `estimated_cad` was the actual cost, which made the estimate-versus-actual column
        # of the spend report a tautology on this path: it reported perfect estimation
        # because it was comparing the bill with itself. It is the padded pre-call estimate
        # now, which is the number that was actually reserved against the ceiling.
        gw.release_reservation(db, held, actual_cad=cost)
        spend_report.record(
            db, agent=HAIR_AGENT, amount_cad=cost, estimated_cad=estimate,
            purpose=TASK, provider="anthropic", model=provider.model,
            department="creative", tokens_in=response.input_tokens,
            tokens_out=response.output_tokens, detail={"price_basis": "assumed"})

    import re

    match = re.search(r"\{.*\}", response.text or "", re.S)
    if not match:
        return {"error": "no JSON in the hair comparison"}
    try:
        parsed = json.loads(match.group(0))
    except ValueError as exc:
        return {"error": f"the hair comparison could not be read: {exc}"[:200]}

    verdicts = {k: str(parsed.get(k, identity.UNMEASURABLE)).strip().lower()
                for k in ("colour", "length", "cut")}
    arrangement_differs = bool(parsed.get("arrangement_differs"))
    # Three conditions, and the middle one is the fix for the first live run of this check.
    # Requiring all three to read `match` made the question unanswerable in exactly the
    # situation it exists for: the approved reference wears her hair up, and length is
    # unmeasurable from a bun by construction. The observer said so -- colour match, cut
    # match, length unmeasurable, "pulled up into a bun ... the color and highlight pattern
    # match" -- and the check called that a different woman. A floor that a bun can never
    # clear is the same defect as one nothing can fail.
    #
    # So: nothing may read `drift`, at least two of the three must be positively readable
    # as `match`, and the arrangement must actually differ. The last is the discipline --
    # the narrower question has to *explain* the flagged drift, not merely fail to find
    # one. Identical arrangement with hair still reading as changed is unexplained, and
    # unexplained is not styling.
    no_drift = identity.DRIFT not in verdicts.values()
    readable = sum(1 for v in verdicts.values() if v == identity.MATCH)
    same = no_drift and readable >= 2 and arrangement_differs
    return {
        "same_hair": same,
        "same_hair_needed": {
            "nothing_reads_drift": no_drift,
            "at_least_two_of_three_read_match": readable >= 2,
            "the_arrangement_actually_differs": arrangement_differs,
            "why": ("length is unmeasurable from a bun by construction, so demanding three "
                    "matches makes this unanswerable exactly when it is needed. Two "
                    "positive reads and no drift is evidence; the arrangement difference "
                    "is what makes it an explanation rather than a shrug")},
        "verdicts": verdicts,
        "arrangement_differs": arrangement_differs,
        "note": str(parsed.get("note") or "")[:240],
        "why_this_is_asked": (
            "hair identity and hair styling are different things, and the pack's single "
            "`hair` dimension conflates them. A woman with her hair up is not a different "
            "woman, and the brief says she wears it both ways"),
    }


def gate_frames(db, frames: list[dict], *, observer=None) -> dict:
    """Block model-bearing frames whose identity cannot be verified.

    `frames` are dicts carrying at least `role` and `has_model`, and `image_ref` when there
    is a file to look at. Frames with no model are not examined at all -- a product-only
    render has no identity to drift.
    """
    modelled = [f for f in frames if f.get("has_model")]
    if not modelled:
        return {"checked": 0, "blocking": [], "verdict": "not_applicable",
                "why": ("no frame in this listing carries the model, so there is no identity "
                        "to drift. A product-only render is not waved through; it is not "
                        "asked")}

    pack = canonical_pack(db)
    if pack is None:
        return {
            "checked": len(modelled), "verdict": "unavailable",
            "blocking": [f"{f.get('role', '?')}: no canonical model has been selected"
                         for f in modelled],
            "why": ("#201 makes drift a release-blocking defect, and drift is measured "
                    "against a reference pack. With no pack every model-bearing frame is "
                    "unverifiable, and unverifiable is not a pass -- the moment this check "
                    "is allowed to shrug is the moment it stops being a check"),
        }

    blocking: list[str] = []
    results: list[dict] = []
    for frame in modelled:
        ref = frame.get("image_ref") or ""
        reference = pack.fields.get("reference_image") or frame.get("reference_image") or ""
        if ref and reference:
            seen = (observer or compare_identity)(db, reference, ref)
        else:
            seen = {"error": "no reference image to compare against"} if ref else {
                "error": "no image to look at"}
        verdict = identity.drift_check(seen, pack)
        results.append({"role": frame.get("role"), "verdict": verdict["verdict"],
                        "failed": verdict.get("failed", []),
                        "observation_error": seen.get("error", "")})
        if verdict["blocks_release"]:
            blocking.append(f"{frame.get('role', '?')}: {verdict['reason'] or 'unverifiable'}")

    return {"checked": len(modelled), "results": results, "blocking": blocking,
            "verdict": "pass" if not blocking else "fail",
            "pack_version": pack.version}


def state(db) -> dict:
    """What the identity system is, read from rows rather than asserted."""
    pack = canonical_pack(db)
    return {
        **identity.status(packs(db), candidates(db)),
        "persisted": True,
        "gate_is_wired": True,
        "what_blocks_today": (
            "every model-bearing frame, because no canonical model has been selected"
            if pack is None else
            f"a model-bearing frame that drifts from pack version {pack.version}"),
    }
