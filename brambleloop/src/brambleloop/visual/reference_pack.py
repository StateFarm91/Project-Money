"""Building the canonical reference pack from the owner's own candidate.

The tournament did its job and the answer was no. Five finalists were presented with their
measured results and the owner rejected all five, supplying instead a generated concept of
their own: *this is the woman*. That is the outcome the tournament exists to make possible --
"none of these" is only available to somebody who was shown the field rather than handed a
winner.

So this module does the thing the tournament was never asked to do: take one identity and
prove it can hold. Five properties, each against a specific way it goes wrong.

**The reference is two frames, not one.** Every tournament finalist's reference was a
head-and-shoulders crop, so stature, torso, bust, waist and hips came back `unmeasurable` on
the *reference itself* -- there was nothing for a later frame to be compared against, and the
morphology floor could only ever return `unverifiable`. A floor that cannot pass is not a
floor. The pack therefore has a neutral portrait for the face and a full-length standing
frame for the body, and the body frame is deliberately dressed to be readable.

**Face and body are judged against different references.** The face is compared to the
portrait and the morphology to the full-length, because comparing a seated winter scene
against a cropped portrait asks the judge about a body neither photograph shows.

**Chest and torso are required, not counted.** The owner named them: the failure that
started all of this was a convincing face above a chest that had changed. Three readable
dimensions out of eight clears the count while leaving exactly that unexamined, so
`identity.REQUIRED_MEASURABLE` makes bust and torso readable-or-unverifiable, and this module
requires them readable *and* matching somewhere in the set before a pack is complete.

**Nothing here selects her.** There is no function in this module that freezes an identity,
exactly as there is none in `tournament`. The pack is built, measured and presented; the
owner approves, and `model_registry.select_canonical` is the only thing that can freeze it.
"""
from __future__ import annotations

from ..core.resilience import PermanentError, TransientError
from . import brief, identity, model_registry, tournament

PACK_ACTION = "model.reference_pack"

# Part of the run fingerprint. A pack built before the full-length frame existed is not
# comparable to one built after it, and re-reading the old audit row as "already done" is
# how a corrected method quietly never runs.
PACK_VERSION = "v1-owner-candidate-two-frame-reference"

# The scenes the pack is stress-tested across: the brief's controlled set, minus the neutral
# portrait, which is now a reference frame rather than a scene.
STRESS_SCENES: tuple[tuple[str, str], ...] = tuple(
    (k, v) for k, v in brief.STRESS_SCENES if k != "neutral_reference")


class PackRefused(ValueError):
    """A pack that would be built from the wrong thing, or frozen by the wrong caller."""


def plan(db=None, env: dict | None = None) -> dict:
    """What the build would render and cost, before anything is spent."""
    from ..gateway import images, routing

    provider = tournament.preferred_provider(db, env)
    per_image = images.BY_KEY[provider].cad_per_image if provider in images.BY_KEY else 0.0
    renders = len(brief.REFERENCE_FRAMES) + len(STRESS_SCENES)
    # Two observations of the reference frames, one identity comparison between them, and
    # two comparisons per scene: the face against the portrait and the body against the
    # full-length.
    judgements = 2 + 1 + 2 * len(STRESS_SCENES)
    judge_rate = routing.estimate_cad(tournament.JUDGE_TASK)
    render_cad = round(renders * per_image, 4)
    judge_cad = round(judgements * judge_rate, 4)
    return {
        "provider": provider,
        "candidate": "the owner's supplied concept",
        "reference_frames": [k for k, _ in brief.REFERENCE_FRAMES],
        "scenes": [k for k, _ in STRESS_SCENES],
        "renders": renders,
        "judgements": judgements,
        "render_cad": render_cad,
        "judging_cad": judge_cad,
        "total_cad": round(render_cad + judge_cad, 4),
        "required_morphology": list(identity.REQUIRED_MEASURABLE["morphology"]),
        "spends_against": ("the CA$100 monthly model ceiling as Build-2 work, not the "
                           "CA$50 image-benchmark authorization"),
        "freezes_nothing": (
            "there is no function in this module that makes a candidate canonical. The pack "
            "is presented and the owner approves"),
    }


def _render(prompt: str, *, provider: str, references: list[str], env, work_dir,
            generator=None) -> dict:
    from ..gateway import images

    if generator is not None:
        return generator(prompt, env=env, size="1024x1024", reference_urls=references)
    return images.generate(prompt, env=env, provider_key=provider,
                           reference_urls=references, size="1024x1024", work_dir=work_dir)


def _merge(face_from: dict, body_from: dict) -> dict:
    """One set of per-dimension verdicts, each taken from the comparison that can answer it.

    A winter scene compared against a cropped portrait cannot say anything about hips; a
    full-length reference photographed in daylight says little about an expression. Asking
    each comparison only what it is in a position to know is the difference between a
    measurement and a number.
    """
    merged = {d: face_from.get(d) for d in identity.FACE_DIMENSIONS}
    merged.update({d: body_from.get(d) for d in identity.MORPHOLOGY_DIMENSIONS})
    return merged


def build(db, *, env: dict | None = None, work_dir: str | None = None,
          generator=None, observer=None, comparer=None) -> dict:
    """Render the reference frames and the stress set, and measure what held.

    Returns the package the owner is shown. Freezes nothing, stores nothing as canonical,
    and is explicit about every dimension it could not read.
    """
    provider = tournament.preferred_provider(db, env)
    if not provider and generator is None:
        # No credentialled image provider in this environment. Refused rather than attempted:
        # the gateway would raise on a None provider deep inside the first render, and a job
        # that dies with an AttributeError reports a bug where the truth is a missing
        # credential.
        return {"built": False, "stage": "provider",
                "why": ("no verified image provider is available in this environment, so "
                        "nothing can be rendered. The pack is unbuilt, which is not the "
                        "same as a pack that failed its floors"),
                "spent_cad": 0.0, "pack_version": PACK_VERSION}

    observe = observer or model_registry.observe
    compare = comparer or model_registry.compare_identity
    concept = brief.candidate_reference()

    spent = 0.0
    frames: dict[str, dict] = {}
    for key, prompt in brief.REFERENCE_FRAMES:
        # The portrait conditions on the owner's concept; the full-length conditions on the
        # concept *and* the portrait just produced, so the body frame is the same woman
        # rather than a second interpretation of the same description.
        references = [concept] if key == "neutral_portrait" else [
            frames["neutral_portrait"]["image_ref"], concept]
        try:
            render = _render(brief.base_prompt() + " " + prompt, provider=provider,
                             references=references, env=env, work_dir=work_dir,
                             generator=generator)
        except (PermanentError, TransientError) as exc:
            return {"built": False, "stage": key, "why": str(exc)[:300],
                    "spent_cad": round(spent, 4), "pack_version": PACK_VERSION}
        spent += float(render.get("cad") or 0.0)
        ref = render.get("image_ref") or ""
        frames[key] = {"frame": key, "image_ref": ref, "image": tournament._keep(ref),
                       "provider": render.get("provider") or provider}
        if key not in frames or not ref:
            return {"built": False, "stage": key, "why": "the render returned no image",
                    "spent_cad": round(spent, 4), "pack_version": PACK_VERSION}

    portrait = frames["neutral_portrait"]["image_ref"]
    full_length = frames["full_length_standing"]["image_ref"]

    face_seen = observe(db, portrait)
    body_seen = observe(db, full_length)
    if face_seen.get("error") or body_seen.get("error"):
        return {"built": False, "stage": "observe",
                "why": face_seen.get("error") or body_seen.get("error"),
                "spent_cad": round(spent, 4), "pack_version": PACK_VERSION}

    # Is the full-length frame the same woman as the portrait? If the body reference drifted
    # from the face reference, the pack is already two people and nothing downstream of it
    # means anything.
    coherence = compare(db, portrait, full_length)
    coherent = identity.drift_check(
        _merge(coherence, coherence), _provisional(face_seen, body_seen))

    observed = {**{d: body_seen.get(d) for d in identity.MORPHOLOGY_DIMENSIONS},
                **{d: face_seen.get(d) for d in identity.FACE_DIMENSIONS}}
    pack = _provisional(face_seen, body_seen)
    unpinned = [d for d in identity.DRIFT_DIMENSIONS
                if str(observed.get(d, "")).strip().lower() in ("", identity.UNMEASURABLE)]

    scenes: list[dict] = []
    for key, prompt in STRESS_SCENES:
        try:
            render = _render(prompt, provider=provider,
                             references=[portrait, full_length], env=env, work_dir=work_dir,
                             generator=generator)
            spent += float(render.get("cad") or 0.0)
            ref = render.get("image_ref") or ""
            against_face = compare(db, portrait, ref)
            against_body = compare(db, full_length, ref)
            verdict = identity.drift_check(_merge(against_face, against_body), pack)
        except (PermanentError, TransientError) as exc:
            scenes.append({"scene": key, "rendered": False, "why": str(exc)[:200]})
            continue
        scenes.append({
            "scene": key, "rendered": True, "image_ref": ref, "image": tournament._keep(ref),
            "provider": render.get("provider") or provider,
            "verdict": verdict["verdict"],
            "face": verdict["face"].get("verdict"),
            "morphology": verdict["morphology"].get("verdict"),
            "dimensions": verdict["dimensions"],
            "drifted": verdict.get("failed", []),
            "required_unreadable": verdict["morphology"].get("required_unreadable", []),
            "unmeasurable": (verdict["face"].get("unmeasurable", [])
                             + verdict["morphology"].get("unmeasurable", [])),
        })

    return _package(frames, scenes, observed=observed, unpinned=unpinned,
                    coherence=coherent, provider=provider, spent=spent)


def _provisional(face_seen: dict, body_seen: dict) -> identity.ReferencePack:
    """The pack as it stands before the owner approves it. Version 0, deliberately."""
    fields = {}
    for d in identity.FACE_DIMENSIONS:
        fields[identity.DIMENSION_FIELD[d]] = face_seen.get(d) or "described"
    for d in identity.MORPHOLOGY_DIMENSIONS:
        fields[identity.DIMENSION_FIELD[d]] = body_seen.get(d) or "described"
    return identity.ReferencePack(version=0, fields=fields,
                                  approved_by_owner_at="not yet -- awaiting owner approval")


def _floor(scenes: list[dict], group: str) -> str:
    """Three-valued across the set. `unverifiable` is not `fail` and never a `pass`."""
    rendered = [s for s in scenes if s.get("rendered")]
    if any(s[group] == "fail" for s in rendered):
        return "fail"
    if not rendered or any(s[group] == "unverifiable" for s in rendered):
        return "unverifiable"
    return "pass"


def _required_evidence(scenes: list[dict]) -> dict:
    """Whether chest/bust and torso were actually evidenced somewhere in the set.

    The owner named these as explicit hard floors. A set in which every scene happened to
    hide the chest is not a set that proved chest continuity -- it is a set that never
    looked, and the honest word for that is `unverifiable` rather than a pass earned by the
    other six dimensions.
    """
    out: dict[str, dict] = {}
    for dimension in identity.REQUIRED_MEASURABLE["morphology"]:
        matched = [s["scene"] for s in scenes if s.get("rendered")
                   and (s.get("dimensions") or {}).get(dimension) == identity.MATCH]
        drifted = [s["scene"] for s in scenes if s.get("rendered")
                   and (s.get("dimensions") or {}).get(dimension) == identity.DRIFT]
        out[dimension] = {
            "verdict": ("fail" if drifted else "pass" if matched else "unverifiable"),
            "matched_in": matched, "drifted_in": drifted,
            "why": ("" if matched and not drifted else
                    "drifted where it was readable" if drifted else
                    "no scene in the set showed it clearly enough to judge, so continuity "
                    "here is unproven rather than proven"),
        }
    return out


def _package(frames: dict, scenes: list[dict], *, observed: dict, unpinned: list[str],
             coherence: dict, provider: str, spent: float) -> dict:
    face_floor = _floor(scenes, "face")
    body_floor = _floor(scenes, "morphology")
    required = _required_evidence(scenes)
    required_ok = all(v["verdict"] == "pass" for v in required.values())
    rendered = [s for s in scenes if s.get("rendered")]

    return {
        "built": True,
        "pack_version": PACK_VERSION,
        "provider": provider,
        "candidate": brief.CANDIDATE_IS_OWNER_SUPPLIED,
        "reference_frames": [frames[k] for k, _ in brief.REFERENCE_FRAMES if k in frames],
        "reference_observation": observed,
        "unpinned_dimensions": unpinned,
        "reference_frames_are_the_same_woman": {
            "verdict": coherence["verdict"],
            "face": coherence["face"].get("verdict"),
            "why_it_is_checked": (
                "the portrait pins the face and the full-length pins the body. If they are "
                "two different women the pack is incoherent before any scene is rendered, "
                "and every measurement after it is against a reference that does not exist"),
        },
        "scenes": scenes,
        "scenes_rendered": len(rendered),
        "scenes_expected": len(STRESS_SCENES),
        "complete": len(rendered) == len(STRESS_SCENES),
        "face_floor": face_floor,
        "morphology_floor": body_floor,
        "required_morphology": required,
        "required_morphology_ok": required_ok,
        "morphology_readable_scenes": [s["scene"] for s in rendered
                                       if s["morphology"] == "pass"],
        "morphology_drifted_scenes": [s["scene"] for s in rendered
                                      if s["morphology"] == "fail"],
        "ready_for_owner_approval": bool(
            rendered and len(rendered) == len(STRESS_SCENES)
            and face_floor == "pass" and body_floor == "pass" and required_ok
            and coherence["verdict"] != "fail"),
        "spent_cad": round(spent, 4),
        "decision": "owner",
        "nothing_is_frozen": (
            "this package is evidence, not a selection. The identity is frozen only by "
            "model_registry.select_canonical with the owner's explicit approval, and a pack "
            "whose floors did not pass is not made canonical by being the only candidate"),
        "hard_floors": list(brief.HARD_FLOORS),
        "floors_never_average": (
            "face and whole-person morphology are reported separately and neither "
            "compensates for the other. A face match above a changed chest is the failure "
            "this measurement exists to catch, and a blended score would call it a pass"),
    }
