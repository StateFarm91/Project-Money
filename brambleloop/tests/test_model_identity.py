"""The canonical model's lock, and the gate that had no callers.

`visual/identity.py` was complete and correct and nothing in the codebase invoked it. That is
this build's most familiar failure in its most flattering disguise: a table nothing reads is
documentation, and a gate nothing calls is a good intention with tests. It would have gone on
being right and unconsulted while the first model-bearing listing shipped past it.

So these tests are about the two joins that were missing -- the pack surviving a restart, and
the gate blocking a release -- and about the property both exist to protect: nothing becomes
canonical without the owner, and an unverifiable identity is never a pass.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.visual import identity  # noqa: E402
from brambleloop.visual import model_registry as M  # noqa: E402


def _db() -> Database:
    db = Database("sqlite://")
    db.create_all()
    return db


def _complete_fields() -> dict:
    return {f: f"pinned-{f}" for f in identity.IDENTITY_FIELDS}


# ---------------------------------------------------------------------------
# Nothing selects itself


def test_a_candidate_does_not_become_canonical_by_being_first():
    db = _db()
    M.record_candidate(db, "face-a", fields=_complete_fields())
    M.record_candidate(db, "face-b", fields=_complete_fields())

    assert M.canonical_pack(db) is None
    assert len(M.candidates(db)) == 2
    try:
        M.select_canonical(db, "face-a", owner_approved=False)
    except identity.IdentityRefused as exc:
        assert "without the owner's selection" in str(exc)
        return
    raise AssertionError("a candidate became canonical without the owner")


def test_the_owner_selects_one_and_a_second_selection_is_a_redesign():
    db = _db()
    M.record_candidate(db, "face-a", fields=_complete_fields())
    M.record_candidate(db, "face-b", fields=_complete_fields())

    pack = M.select_canonical(db, "face-a", owner_approved=True)
    assert pack.version == 1 and pack.complete()
    assert M.canonical_pack(db) is not None

    try:
        M.select_canonical(db, "face-b", owner_approved=True)
    except identity.IdentityRefused as exc:
        assert "redesign" in str(exc)
        return
    raise AssertionError("a second identity was selected as though it were a first")


def test_an_incomplete_pack_is_refused_because_an_unpinned_field_drifts():
    db = _db()
    fields = _complete_fields()
    del fields["eyes"]
    M.record_candidate(db, "face-a", fields=fields)
    try:
        M.select_canonical(db, "face-a", owner_approved=True)
    except identity.IdentityRefused as exc:
        assert "eyes" in str(exc)
        return
    raise AssertionError("an incomplete reference pack was frozen")


def test_the_canonical_identity_cannot_be_rewritten_as_a_candidate():
    """A redesign wearing an import's clothes."""
    db = _db()
    M.record_candidate(db, "face-a", fields=_complete_fields())
    M.select_canonical(db, "face-a", owner_approved=True)
    try:
        M.record_candidate(db, "face-a", fields={"hair": "different"})
    except M.RegistryRefused:
        return
    raise AssertionError("the canonical identity was overwritten by a candidate write")


def test_the_pack_survives_a_restart():
    """A pack held in memory is gone after the next deploy, and a canonical model who
    disappears on a redeploy is not locked to anything."""
    import tempfile

    path = Path(tempfile.mkdtemp()) / "identity.sqlite"
    db = Database(f"sqlite:///{path}")
    db.create_all()
    M.record_candidate(db, "face-a", fields=_complete_fields())
    M.select_canonical(db, "face-a", owner_approved=True)

    reopened = Database(f"sqlite:///{path}")
    pack = M.canonical_pack(reopened)
    assert pack is not None and pack.version == 1
    assert pack.complete()


# ---------------------------------------------------------------------------
# The gate


def test_a_product_only_listing_is_not_asked_about_identity():
    db = _db()
    out = M.gate_frames(db, [{"role": "hero", "has_model": False},
                             {"role": "detail", "has_model": False}])
    assert out["verdict"] == "not_applicable"
    assert out["blocking"] == []
    assert "it is not asked" in out["why"]


def test_a_model_frame_with_no_canonical_pack_blocks():
    """Unverifiable is not a pass. #201 makes drift release-blocking, and a check that
    shrugs when it has nothing to compare against is not a check."""
    db = _db()
    out = M.gate_frames(db, [{"role": "hero", "has_model": True}])
    assert out["verdict"] == "unavailable"
    assert out["blocking"] and "no canonical model" in out["blocking"][0]


def test_a_matching_face_passes_and_a_drifted_one_blocks():
    db = _db()
    fields = _complete_fields()
    # A pack carries its own portrait: without one it can neither condition a generation nor
    # be compared against one, which is the opposite of a lock.
    M.record_candidate(db, "face-a", fields=fields, image_refs=["/tmp/reference.png"])
    pack = M.select_canonical(db, "face-a", owner_approved=True)
    assert pack.fields["reference_image"] == "/tmp/reference.png"

    # The observer is a comparison of two photographs returning a verdict per dimension.
    # Matching two free-text descriptions as strings reported every dimension of every
    # scene of every finalist as drift, because two honest descriptions of one woman are
    # never identical text.
    same = {d: identity.MATCH for d in identity.DRIFT_DIMENSIONS}
    ok = M.gate_frames(db, [{"role": "hero", "has_model": True, "image_ref": "/tmp/a.png"}],
                       observer=lambda _db, ref, cand: dict(same))
    assert ok["verdict"] == "pass", ok

    drifted = {**same, "hair": identity.DRIFT}
    bad = M.gate_frames(db, [{"role": "hero", "has_model": True, "image_ref": "/tmp/a.png"}],
                        observer=lambda _db, ref, cand: dict(drifted))
    assert bad["verdict"] == "fail"
    assert "hair" in str(bad["blocking"])


def test_an_unreadable_observation_blocks_rather_than_passing():
    """An unmeasured dimension is not a matching one."""
    db = _db()
    M.record_candidate(db, "face-a", fields=_complete_fields(),
                       image_refs=["/tmp/reference.png"])
    M.select_canonical(db, "face-a", owner_approved=True)
    out = M.gate_frames(db, [{"role": "hero", "has_model": True, "image_ref": "/tmp/a.png"}],
                        observer=lambda _db, ref, cand: {
                            "error": "the observer could not answer"})
    assert out["verdict"] == "fail"


def test_the_release_path_actually_calls_the_gate():
    """The whole point. `visual/identity.py` had no callers anywhere in the codebase."""
    source = (ROOT / "src/brambleloop/runtime/release.py").read_text()
    assert "model_registry.gate_frames" in source
    assert "identity_gate[\"blocking\"]" in source


def test_the_observer_is_asked_for_the_drift_dimensions():
    prompt = M.observe_prompt()
    for dimension in identity.DRIFT_DIMENSIONS:
        assert dimension in prompt
    assert "no_person" in prompt


# ---------------------------------------------------------------------------
# The body-drift failure the owner caught, 2026-09-21


def _observation(**override) -> dict:
    base = {d: f"pinned-{identity.DIMENSION_FIELD[d]}" for d in identity.DRIFT_DIMENSIONS}
    base.update(override)
    return base


def _pack() -> identity.ReferencePack:
    return identity.ReferencePack(version=1, fields=_complete_fields(),
                                  approved_by_owner_at="2026-09-21T00:00:00Z")


def test_a_perfect_face_on_a_different_body_fails():
    """The exact failure mode the first reference-conditioned trial produced.

    The face came back convincingly the same woman while the chest and upper-torso
    morphology changed substantially. That is worse than an obvious miss: a familiar face is
    precisely what stops anybody looking further down the frame. A face match may never
    compensate for morphology drift, and a single blended score is how it would.
    """
    out = identity.drift_check(_observation(bust="substantially fuller"), _pack())
    assert out["verdict"] == "fail"
    assert out["face"]["verdict"] == "pass"
    assert out["morphology"]["verdict"] == "fail"
    assert "bust" in out["morphology"]["drifted"]
    assert "does not compensate" in out["reason"]
    assert "garment fit cannot be compared" in out["reason"]


def test_the_two_floors_are_independent_and_neither_averages_into_the_other():
    pack = _pack()
    face_only = identity.drift_check(_observation(face="a different face"), pack)
    body_only = identity.drift_check(_observation(hips="much wider", waist="much narrower"),
                                     pack)
    assert face_only["verdict"] == "fail" and face_only["morphology"]["verdict"] == "pass"
    assert body_only["verdict"] == "fail" and body_only["face"]["verdict"] == "pass"
    assert "separate hard floors" in identity.drift_check(
        _observation(), pack)["floors_are_independent"]


def test_an_obscured_proportion_is_unmeasurable_and_never_a_pass():
    """Clothing, pose and perspective change apparent silhouette. A loose cardigan must not
    silently certify a different body."""
    hidden = _observation(**{d: "unmeasurable" for d in identity.MORPHOLOGY_DIMENSIONS})
    out = identity.drift_check(hidden, _pack())
    assert out["verdict"] == "unverifiable"
    assert out["blocks_release"] is True
    assert out["face"]["verdict"] == "pass"
    assert set(out["morphology"]["unmeasurable"]) == set(identity.MORPHOLOGY_DIMENSIONS)
    assert "Unmeasurable is not a pass" in out["reason"]


def test_a_group_with_too_little_readable_is_unverifiable_rather_than_passing():
    """Two measurable dimensions out of eight is not a morphology check."""
    mostly_hidden = _observation(**{d: "unmeasurable"
                                    for d in identity.MORPHOLOGY_DIMENSIONS[2:]})
    out = identity.drift_check(mostly_hidden, _pack())
    assert out["morphology"]["verdict"] == "unverifiable"
    assert out["verdict"] == "unverifiable"


def test_enough_readable_and_all_matching_passes():
    partial = _observation(**{d: "unmeasurable" for d in identity.MORPHOLOGY_DIMENSIONS[5:]})
    out = identity.drift_check(partial, _pack())
    assert out["verdict"] == "pass", out
    assert out["morphology"]["verdict"] == "pass"


def test_a_field_the_pack_never_pinned_is_unmeasurable_not_a_match():
    """An unpinned field is exactly the field that drifts."""
    fields = _complete_fields()
    del fields["bust_proportions"]
    pack = identity.ReferencePack(version=1, fields=fields,
                                  approved_by_owner_at="2026-09-21T00:00:00Z")
    out = identity.drift_check(_observation(), pack)
    assert out["dimensions"]["bust"] == identity.UNMEASURABLE


def test_the_pack_pins_the_body_as_well_as_the_face():
    for field in ("stature", "overall_build", "shoulder_proportions", "torso_length",
                  "bust_proportions", "waist_proportions", "hip_proportions",
                  "limb_proportions"):
        assert field in identity.IDENTITY_FIELDS
    assert set(identity.FACE_FIELDS) & set(identity.MORPHOLOGY_FIELDS) == set()


def test_the_observer_is_asked_about_the_body_and_told_not_to_guess():
    prompt = M.observe_prompt()
    for dimension in identity.MORPHOLOGY_DIMENSIONS:
        assert dimension in prompt
    assert "unmeasurable" in prompt
    assert "do not infer the body from the garment" in prompt.lower()
    # Thirteen dimensions and a phrase each does not fit in the budget written for five.
    assert M.OBSERVE_MAX_TOKENS >= 600


# ---------------------------------------------------------------------------
# The brief (#198)


def test_the_brief_forbids_building_her_from_a_real_persons_photograph():
    """The direction arrived beside a photograph of an identifiable public figure.

    A persistent commercial brand identity built from somebody's photograph is that person's
    likeness in commercial use, and it is also the celebrity resemblance the direction rules
    out in the same breath. Stated as a rule so a later prompt cannot reintroduce it.
    """
    from brambleloop.visual import brief

    rules = {k for k, _ in brief.FORBIDDEN}
    assert "real_person_reference" in rules
    assert "public_figure_likeness" in rules
    assert "celebrity resemblance" in brief.AVOID
    assert "not resembling any known public figure" in brief.base_prompt().lower()


def test_the_stress_test_covers_materially_different_situations():
    """Five flattering portraits prove only that the generator can repeat a portrait."""
    from brambleloop.visual import brief

    keys = {k for k, _ in brief.STRESS_SCENES}
    assert {"neutral_reference", "fitted_garment", "loose_layered_garment",
            "winter_seasonal", "non_garment_lifestyle"} <= keys
    assert brief.HARD_FLOORS == ("facial_identity", "whole_person_morphology")


def test_a_corrected_brief_is_not_locked_out_by_the_hours_idempotency_key():
    """The deploy-time enqueue is keyed on the brief, because the work is.

    This is the defect that kept the corrected tournament from running: two deploys in one
    hour, an idempotency key made only of the hour, and the second deploy -- the one
    carrying the corrected presentation -- enqueued nothing. The endpoint then reported the
    corrected tournament as "not yet run", which was true and unactionable.
    """
    from datetime import datetime, timezone

    from brambleloop.runtime import release
    from brambleloop.visual import tournament

    now = datetime(2026, 9, 21, 13, 40, tzinfo=timezone.utc)
    before = release.tournament_boot_key(now)
    assert release.tournament_boot_key(now) == before, "the same brief must not re-enqueue"

    original = tournament.PRESENTATION_VERSION
    try:
        tournament.PRESENTATION_VERSION = original + "-corrected"
        assert release.tournament_boot_key(now) != before
    finally:
        tournament.PRESENTATION_VERSION = original

    # The key carries the running commit, not the hour. The hour looked like a retry and was
    # a lockout: a job created under one commit holds the key for the rest of the hour, so
    # the deploy that corrects the method finds the key spent by the run it corrects. That
    # happened twice -- to the tournament, and then to the pack. A deploy re-asks; the
    # hourly cadence retries.
    import os

    os.environ["BRAMBLELOOP_COMMIT"] = "deadbeefcafe"
    try:
        assert release.tournament_boot_key(now) != before
        assert release.pack_boot_key(now).endswith("deadbeefcafe")
    finally:
        os.environ.pop("BRAMBLELOOP_COMMIT", None)
    later = datetime(2026, 9, 21, 14, 0, tzinfo=timezone.utc)
    assert release.tournament_boot_key(later) == before, "the hour must not change the key"


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
