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
PACK_VERSION = "v6-targeted-bust-revision-measured-against-the-approved-body"

# The scenes the pack is stress-tested across: the brief's controlled set, minus the neutral
# portrait, which is now a reference frame rather than a scene.
STRESS_SCENES: tuple[tuple[str, str], ...] = tuple(
    (k, v) for k, v in brief.STRESS_SCENES if k != "neutral_reference")


# How many times the torso frame may be re-rendered when it fails at its one job.
#
# That frame exists to make the chest and torso readable. A render in which they are not is
# a failed render, not a finding about the woman -- and the first three live builds each
# turned on whether one generation happened to frame her closely enough, which is a
# measurement decided by luck. Bounded at three because a fourth is evidence that the prompt
# is wrong rather than the sample, and the pack says so instead of paying for more.
TORSO_ATTEMPTS = 3


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
    judgements = len(brief.REFERENCE_FRAMES) + 2 + 2 * len(STRESS_SCENES)
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
    from ..ops import funding

    held = funding.blocked(db)
    if held.get("blocked") and generator is None:
        # The revised pack rendered eight images at CA$0.08 and died at the first vision
        # call, twice, because the balance was spent both times. Rendering again before the
        # judge can run would spend the same money for the same nothing.
        return {"built": False, "stage": "funding",
                "why": ("the model provider's balance is spent, so nothing rendered now "
                        "could be measured. " + held["why_this_stops_spending"]),
                "waiting_on": "model_provider_balance",
                "spent_cad": 0.0, "pack_version": PACK_VERSION}

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

    # The portrait is carried, not re-rendered. The owner approved this face as the target
    # direction and the revision is about one body dimension, so regenerating her head
    # would put the approved thing back at risk to change something else. It lives in the
    # repository because the artifact store is a container filesystem: the portrait
    # presented to the owner returned 404 within the hour, on the next deploy.
    carried = brief.approved_portrait()
    frames["neutral_portrait"] = {
        "frame": "neutral_portrait", "image_ref": carried,
        "image": tournament._keep(carried), "provider": "carried",
        "source": ("carried unchanged from the approved reference pack, not re-rendered. "
                   "The revision changes one body dimension and must not put an approved "
                   "face at risk to do it")}

    for key, prompt in brief.REFERENCE_FRAMES:
        if key == "neutral_portrait":
            continue
        # Each frame conditions on the owner's concept and on the frames already produced,
        # so the three are one woman rather than three interpretations of one description.
        # The full-length conditions on the torso frame rather than the portrait: it is the
        # body that has to carry across, and the portrait has none to carry.
        # Each revised frame sees the approved frame it is revising and the approved face
        # it must keep. Conditioning on the body being changed is what makes "fuller chest,
        # everything else the same" a change rather than a fresh interpretation.
        references = {
            "torso_fit_reference": [brief.approved_reference("torso_fit_reference"),
                                    frames["neutral_portrait"]["image_ref"]],
            "full_length_standing": [
                frames.get("torso_fit_reference", {}).get("image_ref", ""),
                brief.approved_reference("full_length_standing")],
        }[key]
        references = [r for r in references if r]
        try:
            render = _render(f"{prompt} {brief.revision_clause()}", provider=provider,
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

    seen = {key: observe(db, frames[key]["image_ref"]) for key, _ in brief.REFERENCE_FRAMES}
    for key, reading in seen.items():
        if reading.get("error"):
            return {"built": False, "stage": f"observe:{key}", "why": reading["error"],
                    "spent_cad": round(spent, 4), "pack_version": PACK_VERSION}

    # The torso frame has one job. If the chest or the torso came back unreadable, that is a
    # failed render rather than a fact about her, so it is rendered again -- the pack is a
    # permanent brand identity and it should not turn on whether one generation happened to
    # frame her closely enough.
    torso_attempts = 1
    required = identity.REQUIRED_MEASURABLE["morphology"]
    torso_prompt = dict(brief.REFERENCE_FRAMES)["torso_fit_reference"]
    while (torso_attempts < TORSO_ATTEMPTS
           and any(not _readable(seen["torso_fit_reference"].get(d)) for d in required)):
        torso_attempts += 1
        try:
            render = _render(f"{torso_prompt} {brief.revision_clause()}", provider=provider,
                             references=[brief.approved_reference("torso_fit_reference"),
                                         frames["neutral_portrait"]["image_ref"]],
                             env=env, work_dir=work_dir, generator=generator)
        except (PermanentError, TransientError):
            break
        spent += float(render.get("cad") or 0.0)
        ref = render.get("image_ref") or ""
        reading = observe(db, ref)
        if reading.get("error"):
            continue
        # Kept only if it reads more of the required dimensions than what it replaces: a
        # retry that loses the torso to gain the chest is not an improvement.
        def _score(r: dict) -> int:
            return sum(1 for d in required if _readable(r.get(d)))

        if _score(reading) > _score(seen["torso_fit_reference"]):
            frames["torso_fit_reference"] = {
                "frame": "torso_fit_reference", "image_ref": ref, "image": tournament._keep(ref),
                "provider": render.get("provider") or provider, "attempts": torso_attempts}
            seen["torso_fit_reference"] = reading
    frames["torso_fit_reference"]["attempts"] = torso_attempts

    torso = frames["torso_fit_reference"]["image_ref"]
    observed = _pin(seen)

    # Are the three frames one woman? The torso frame is the bridge and is checked both
    # ways: its face against the portrait, and the full-length's body against it. Checking
    # the full-length's *face* against the portrait is what the previous build did, and it
    # answered `unverifiable` every time for the obvious reason -- a face thirty pixels tall
    # cannot be matched, and calling the pack incoherent on that is a fault in the question.
    face_bridge = compare(db, portrait, torso)
    body_bridge = compare(db, torso, full_length)
    pack = _provisional(observed)
    coherent = identity.drift_check(_merge(face_bridge, body_bridge), pack)

    # Did the revision change the one dimension it was asked to, and only that one?
    #
    # This is the check the owner's instruction actually needs. "Increase the bust" is
    # satisfied trivially by a larger woman, and every floor in this module would pass her:
    # the face still matches, nothing drifted against a pack built from the new body, and
    # the chest is duly fuller. So the revised references are compared against the approved
    # ones, where a bigger waist is a `drift` and shows up as what it is.
    revision = _revision_check(db, compare, torso, full_length)
    unpinned = [d for d in identity.DRIFT_DIMENSIONS
                if str(observed.get(d, "")).strip().lower() in ("", identity.UNMEASURABLE)]
    required_unpinned = [d for d in identity.REQUIRED_MEASURABLE["morphology"]
                         if d in unpinned]

    scenes: list[dict] = []
    for key, prompt in STRESS_SCENES:
        try:
            render = _render(prompt, provider=provider,
                             references=[portrait, torso, full_length], env=env,
                             work_dir=work_dir, generator=generator)
            spent += float(render.get("cad") or 0.0)
            ref = render.get("image_ref") or ""
            against_face = compare(db, portrait, ref)
            # The body is compared against the torso frame, which is the reference that can
            # actually answer for the chest and the torso -- the two dimensions the owner
            # named as hard floors, and the two the full-length frame reads as unmeasurable.
            against_body = compare(db, torso, ref)
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
                    required_unpinned=required_unpinned, bridges={
                        "face_portrait_to_torso": face_bridge,
                        "body_torso_to_full_length": body_bridge},
                    revision=revision, coherence=coherent, provider=provider, spent=spent)


def _readable(value) -> bool:
    """Whether an observation actually states the dimension rather than declining to."""
    return bool(value) and str(value).strip().lower() not in (
        "", identity.UNMEASURABLE, "unclear", "unknown", "obscured", "not visible")


def _pin(seen: dict[str, dict]) -> dict:
    """One observation of the whole woman, each dimension taken from the frame that can see it.

    `FRAME_AUTHORITY` says which frame answers for which dimension, and anything a frame
    reads as unmeasurable falls through to the next frame that has an opinion. The previous
    build pinned the body from the full-length frame alone and wrote `bust: unmeasurable`
    into the pack -- a reference that cannot state a dimension cannot be drifted from on it,
    so the floor was unpassable before a scene was rendered.
    """
    out: dict[str, str] = {}
    for frame, dimensions in brief.FRAME_AUTHORITY.items():
        for d in dimensions:
            if d not in out and _readable((seen.get(frame) or {}).get(d)):
                out[d] = seen[frame][d]
    for d in identity.DRIFT_DIMENSIONS:
        if d in out:
            continue
        for frame, _ in brief.REFERENCE_FRAMES:
            value = (seen.get(frame) or {}).get(d)
            if _readable(value):
                out[d] = value
                break
        else:
            out[d] = identity.UNMEASURABLE
    return out


def _provisional(observed: dict) -> identity.ReferencePack:
    """The pack as it stands before the owner approves it. Version 0, deliberately."""
    fields = {identity.DIMENSION_FIELD[d]: observed.get(d) or "described"
              for d in identity.DRIFT_DIMENSIONS}
    return identity.ReferencePack(version=0, fields=fields,
                                  approved_by_owner_at="not yet -- awaiting owner approval")


def _revision_check(db, compare, torso: str, full_length: str) -> dict:
    """The revised body against the approved body, dimension by dimension."""
    against = {
        "torso_fit_reference": compare(db, brief.approved_reference("torso_fit_reference"),
                                       torso),
        "full_length_standing": compare(
            db, brief.approved_reference("full_length_standing"), full_length),
    }

    def verdict_for(dimension: str) -> str:
        """The strongest thing either comparison could say about this dimension."""
        seen = [against[f].get(dimension) for f in against]
        if identity.DRIFT in seen:
            return identity.DRIFT
        if identity.MATCH in seen:
            return identity.MATCH
        return identity.UNMEASURABLE

    revised = verdict_for(brief.REVISED_DIMENSION)
    preserved = {d: verdict_for(d) for d in brief.PRESERVE_THROUGH_REVISION}
    moved = sorted(d for d, v in preserved.items() if v == identity.DRIFT)
    unreadable = sorted(d for d, v in preserved.items() if v == identity.UNMEASURABLE)

    return {
        "dimension": brief.REVISED_DIMENSION,
        "changed": revised == identity.DRIFT,
        "revised_verdict": revised,
        "preserved": preserved,
        "also_moved": moved,
        "unreadable": unreadable,
        "per_frame": against,
        "why_it_is_checked": (
            "'increase the bust' is satisfied trivially by a larger woman, and every floor "
            "in this module would pass her: the face still matches and nothing drifts "
            "against a pack built from the new body. Measuring the revision against the "
            "body it revised is the only place a widened waist shows up as one"),
        "unreadable_is_not_preserved": (
            "a preserved dimension neither comparison could read is reported here rather "
            "than counted as unchanged"),
    }


def _floor(scenes: list[dict], group: str) -> str:
    """Three-valued across the set. `unverifiable` is not `fail` and never a `pass`."""
    rendered = [s for s in scenes if s.get("rendered")]
    if any(s[group] == "fail" for s in rendered):
        return "fail"
    if not rendered or any(s[group] == "unverifiable" for s in rendered):
        return "unverifiable"
    return "pass"


def _required_evidence(scenes: list[dict], bridge: dict | None = None) -> dict:
    """Whether chest/bust and torso were actually evidenced somewhere in the pack.

    The owner named these as explicit hard floors. A set in which every scene happened to
    hide the chest is not a set that proved chest continuity -- it is a set that never
    looked, and the honest word for that is `unverifiable` rather than a pass earned by the
    other six dimensions.

    The torso-to-full-length comparison counts as evidence, and leaving it out was a real
    mistake rather than conservatism: those are two separately generated photographs of the
    same woman, compared dimension by dimension, which is precisely the continuity test
    being asked for. The first run of the three-frame pack had `bust: match` and `torso:
    match` on that comparison and reported both as unproven, because the check was reading
    only the four garment scenes -- in which a crocheted sweater and a winter scarf hide the
    chest exactly as the owner's rule says they should.
    """
    measurements: list[tuple[str, dict]] = [
        (s["scene"], s.get("dimensions") or {}) for s in scenes if s.get("rendered")]
    if bridge:
        measurements.append(("reference:torso_to_full_length", bridge))

    out: dict[str, dict] = {}
    for dimension in identity.REQUIRED_MEASURABLE["morphology"]:
        matched = [name for name, dims in measurements
                   if dims.get(dimension) == identity.MATCH]
        drifted = [name for name, dims in measurements
                   if dims.get(dimension) == identity.DRIFT]
        out[dimension] = {
            "verdict": ("fail" if drifted else "pass" if matched else "unverifiable"),
            "matched_in": matched, "drifted_in": drifted,
            "why": ("" if matched and not drifted else
                    "drifted where it was readable" if drifted else
                    "nothing in the pack showed it clearly enough to judge, so continuity "
                    "here is unproven rather than proven"),
        }
    return out


def _package(frames: dict, scenes: list[dict], *, observed: dict, unpinned: list[str],
             required_unpinned: list[str], bridges: dict, coherence: dict, provider: str,
             spent: float, revision: dict | None = None) -> dict:
    bridges = bridges or {}
    face_floor = _floor(scenes, "face")
    body_floor = _floor(scenes, "morphology")
    required = _required_evidence(scenes, bridges.get("body_torso_to_full_length"))
    required_ok = all(v["verdict"] == "pass" for v in required.values())
    rendered = [s for s in scenes if s.get("rendered")]
    drifted_scenes = [s["scene"] for s in rendered if s["morphology"] == "fail"]

    # Which of chest, torso and waist the close-fitting frame could actually read. The
    # owner asked for one frame that exposes all three together, because a set in which
    # every frame hides the chest is clean and proves nothing.
    fit_scene = next((s for s in rendered if s["scene"] == brief.FIT_VALIDATION_SCENE), None)
    fit_dims = (fit_scene or {}).get("dimensions") or {}
    fit_frame_reads = sorted(d for d in ("bust", "torso", "waist")
                             if fit_dims.get(d) in (identity.MATCH, identity.DRIFT))
    if len(fit_frame_reads) < 3:
        fit_frame_reads = []

    # Stated one by one rather than folded into a single boolean, because the single boolean
    # was wrong in a way nobody could see: it required `morphology_floor == "pass"`, which
    # requires every scene to be fully readable, in a set the owner specified to include a
    # winter coat and a loose sweater. That condition could never be met however well the
    # identity held -- a floor that cannot be cleared is the same defect as one that cannot
    # fail, met from the other side. What replaces it is stricter about the things that
    # matter and honest about the thing that does not: no drift anywhere, the two named
    # dimensions evidenced somewhere, every dimension pinned, the frames coherent.
    conditions = {
        "every_scene_rendered": {
            "met": bool(rendered) and len(rendered) == len(STRESS_SCENES),
            "detail": f"{len(rendered)} of {len(STRESS_SCENES)}"},
        "facial_identity_held": {
            "met": face_floor == "pass",
            "detail": f"face floor: {face_floor}"},
        "no_morphology_drift_anywhere": {
            "met": not drifted_scenes,
            "detail": (f"drifted in {drifted_scenes}" if drifted_scenes
                       else "no body dimension drifted in any scene")},
        "chest_and_torso_evidenced": {
            "met": required_ok,
            "detail": {k: v["verdict"] for k, v in required.items()}},
        "every_dimension_pinned": {
            "met": not unpinned,
            "detail": f"unpinned: {unpinned}" if unpinned else "all thirteen pinned"},
        "reference_frames_coherent": {
            "met": coherence["verdict"] != "fail",
            "detail": f"portrait/torso/full-length: {coherence['verdict']}"},
        # The owner's explicit requirement: at least one controlled close-fitting frame has
        # to expose chest, torso and waist together. Without it the set can be full of
        # `unmeasurable` and technically clean.
        "a_close_fitting_frame_reads_chest_torso_and_waist": {
            "met": bool(fit_frame_reads),
            "detail": (f"{brief.FIT_VALIDATION_SCENE}: "
                       f"{fit_frame_reads or 'chest, torso and waist not all readable'}")},
    }
    if revision is not None:
        conditions["the_bust_actually_changed"] = {
            "met": bool(revision["changed"]),
            "detail": f"against the approved body: {revision['revised_verdict']}"}
        conditions["nothing_else_changed"] = {
            "met": not revision["also_moved"],
            "detail": (f"also moved: {revision['also_moved']}" if revision["also_moved"]
                       else "every preserved dimension held")}

    return {
        "built": True,
        "pack_version": PACK_VERSION,
        "provider": provider,
        "candidate": brief.CANDIDATE_IS_OWNER_SUPPLIED,
        "reference_frames": [frames[k] for k, _ in brief.REFERENCE_FRAMES if k in frames],
        "reference_observation": observed,
        "unpinned_dimensions": unpinned,
        "required_dimensions_unpinned": required_unpinned,
        "revision": revision,
        "close_fitting_validation": {
            "scene": brief.FIT_VALIDATION_SCENE,
            "reads": fit_frame_reads,
            "why": ("chest, torso and waist have to be readable together somewhere, or a "
                    "set in which every frame hides them is clean and proves nothing")},
        "reference_bridges": {
            "face_portrait_to_torso": {d: bridges["face_portrait_to_torso"].get(d)
                                       for d in identity.FACE_DIMENSIONS},
            "body_torso_to_full_length": {d: bridges["body_torso_to_full_length"].get(d)
                                          for d in identity.MORPHOLOGY_DIMENSIONS},
        },
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
        "approval_conditions": conditions,
        "ready_for_owner_approval": all(c["met"] for c in conditions.values()),
        "why_not_every_scene_reads_as_pass": (
            "a scene whose chest is under a loose crocheted sweater is `unverifiable`, and "
            "the owner's rule is explicit that it must be. Requiring every scene to read "
            "`pass` would require a wardrobe nobody sells in -- it is a floor that cannot "
            "be cleared, which is the same defect as one that cannot fail. What is required "
            "instead is stated condition by condition above: nothing drifted anywhere, the "
            "two named dimensions were evidenced somewhere, and every dimension is pinned"),
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
