"""Freezing the canonical identity, and the ways a freeze quietly writes a hole (#200).

The owner approved the revised pack on 2026-09-22 and asked for seven properties to be
proved *after persistence*. Most of these tests are about the freeze refusing, because the
frozen pack becomes the definition of a person: `drift_check` compares against it and
`gate_frames` blocks on it, so a field it cannot state is not a missing sentence — it is a
dimension that can never drift again. That is the owner's unmeasurable-is-never-pass rule
made permanent rather than broken once, which is the worse of the two.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

# Before the artifact store is imported: it reads its root once, and the body reference
# the hash tests below file has to be somewhere the test owns.
_ART = tempfile.TemporaryDirectory(prefix="freeze-artifacts-")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = _ART.name

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog  # noqa: E402
from brambleloop.visual import brief, freeze, identity, model_registry  # noqa: E402
from brambleloop.visual import reference_pack  # noqa: E402


class _SoundReference:
    """A realism judge that finds the reference believable.

    Injected into every test that is about something else. Without it each of them would
    be blocked by the freeze-time realism gate, which is correct behaviour and would make
    them all tests of that one gate.
    """

    model = "claude-sonnet-5"  # priced: the pre-call ceiling check refuses an unpriced model
    cost_per_1k_input_cad = 0.0
    cost_per_1k_output_cad = 0.0

    def __init__(self, **checks):
        from brambleloop.visual import photoreal

        self.answers = {k: True for k in photoreal.CHECKS}
        self.answers.update(checks)

    def see(self, system, prompt, refs, max_tokens=0):
        import json as _json

        answers, self_ = self.answers, self

        class R:
            text = _json.dumps({**answers, "notes": "seen"})
            input_tokens = 1
            output_tokens = 1
        return R()



def _db() -> Database:
    tmp = tempfile.mkdtemp()
    db = Database(f"sqlite:///{tmp}/freeze.sqlite")
    db.create_all()
    return db


def _package(*, version: str = "v-test", unpinned: tuple[str, ...] = (),
             built: bool = True) -> dict:
    observed = {d: f"{d} as observed" for d in identity.DRIFT_DIMENSIONS}
    for dimension in unpinned:
        observed[dimension] = identity.UNMEASURABLE
    return {
        "built": built, "pack_version": version,
        "candidate_fingerprint": "fingerprint-" + version,
        "reference_observation": observed,
        "unpinned_dimensions": list(unpinned),
        "reference_frames": [
            {"frame": "neutral_portrait", "image": {"sha256": "a" * 64}},
            {"frame": "torso_fit_reference", "image": {"sha256": "b" * 64}},
            {"frame": "full_length_standing", "image": {"sha256": "c" * 64}},
        ],
    }


def _file(db, package: dict) -> None:
    with db.session() as s:
        s.add(AuditLog(actor="creative_director", action=reference_pack.PACK_ACTION,
                       detail=package))


def test_a_pack_that_cannot_state_the_bust_is_never_frozen():
    """The newest pack on file when the approval arrived had `bust: unmeasurable`.

    Freezing it would have written an identity whose chest has no value, and every later
    comparison against that field would have had nothing to compare to. The approval does
    not change that: the owner approved a bust proportion, not the absence of one.
    """
    db = _db()
    _file(db, _package(version="v16", unpinned=("bust",)))

    verdict = freeze.freezable(_package(version="v16", unpinned=("bust",)))
    assert verdict["freezable"] is False
    assert "bust_proportions" in verdict["missing"]

    try:
        freeze.freeze(db, owner_approved=True, realism_judger=_SoundReference())
    except freeze.FreezeRefused as exc:
        assert "hole" in str(exc) or "could not be read" in str(exc)
    else:                                                    # pragma: no cover
        raise AssertionError("a pack with an unstated bust was frozen")
    assert model_registry.canonical_pack(db) is None


def test_the_freeze_reaches_past_a_newer_unusable_pack_and_says_which():
    """A newer build that cannot state a required dimension is not a newer identity, it
    is an unusable one -- and taking the one behind it has to be visible, or the choice
    looks like "the newest pack" and nobody can audit it."""
    db = _db()
    _file(db, _package(version="v15"))                       # older, complete
    _file(db, _package(version="v16", unpinned=("bust",)))    # newer, unusable

    chosen = freeze.newest_freezable(db)
    assert chosen["pack_version"] == "v15"
    assert [s["pack_version"] for s in chosen["skipped_newer"]] == ["v16"]

    record = freeze.freeze(db, owner_approved=True, realism_judger=_SoundReference())
    assert record["frozen"] is True
    assert record["pack_version"] == "v15"
    assert record["skipped_newer"][0]["pack_version"] == "v16"


def test_nothing_freezes_without_the_owner_and_nothing_freezes_twice():
    db = _db()
    _file(db, _package(version="v15"))

    try:
        freeze.freeze(db, owner_approved=False, realism_judger=_SoundReference())
    except freeze.FreezeRefused as exc:
        assert "the owner's decision" in str(exc)
    else:                                                    # pragma: no cover
        raise AssertionError("froze without the owner")
    assert model_registry.canonical_pack(db) is None

    first = freeze.freeze(db, owner_approved=True, realism_judger=_SoundReference())
    assert first["frozen"] is True
    second = freeze.freeze(db, owner_approved=True, realism_judger=_SoundReference())
    assert second["frozen"] is False and second["already_canonical"] is True
    assert "redesign" in second["why"]


def test_every_field_is_sourced_and_none_is_invented():
    """Thirteen from what a model read off the frames, complexion from the owner's own
    written direction, and the angles from the frames the pack really rendered. A freeze
    that wrote a plausible sentence into a field the pack could not fill would be the
    identity equivalent of a placeholder product photograph."""
    fields = freeze.fields_from(_package())
    assert set(fields) >= set(identity.IDENTITY_FIELDS)
    assert fields["complexion"] == brief.PHYSICAL_DIRECTION["complexion"]
    assert "neutral_portrait" in fields["representative_angles"]
    assert fields["bust_proportions"] == "bust as observed"
    # An unmeasurable reading is dropped rather than written through as a value.
    thin = freeze.fields_from(_package(unpinned=("bust",)))
    assert "bust_proportions" not in thin


def test_the_reference_image_is_one_that_survives_a_restart():
    """The gate hands `reference_image` to a vision call, which needs a URL or a file that
    is actually on this disk. A render's `/tmp` path is neither after the next restart,
    and an `/api/...` path is not something a provider can fetch."""
    db = _db()
    _file(db, _package(version="v15"))
    record = freeze.freeze(db, owner_approved=True, realism_judger=_SoundReference())
    reference = record["fields"]["reference_image"]
    assert reference == brief.approved_portrait()
    assert Path(reference).is_file(), "the canonical reference image is not on disk"


def test_the_seven_properties_hold_against_the_persisted_pack():
    """The owner's list, run against the pack read back out of the database.

    Synthetic observations on purpose, and that is the strength of it: a drifted body
    under a matching face is not something a generator produces on request, so waiting
    for one would mean never checking the case that matters most.
    """
    db = _db()
    _file(db, _package(version="v15"))
    freeze.freeze(db, owner_approved=True, realism_judger=_SoundReference())

    proof = freeze.enforcement_proof(db)
    assert proof["proved"] is True, proof["failed"]
    assert [c["check"] for c in proof["checks"]] == [
        "the_revised_pack_is_what_loads",
        "facial_identity_is_enforced",
        "morphology_is_enforced_separately",
        "bust_and_torso_are_hard_dimensions",
        "unmeasurable_never_becomes_pass",
        "a_face_match_cannot_compensate_for_body_drift",
        "model_bearing_assets_cannot_bypass_the_gate",
        # The eighth, added 2026-09-26: the pictures, not only the logic.
        "references_are_the_approved_bytes",
    ]
    assert all(c["holds"] for c in proof["checks"])


def test_the_proof_reports_nothing_rather_than_passing_with_no_pack():
    """The failure this whole module is built against: a check that passes because it had
    nothing to compare with would be believed."""
    proof = freeze.enforcement_proof(_db())
    assert proof["proved"] is False
    assert "nothing to enforce" in proof["why"]


def test_the_proof_can_fail_and_is_not_a_row_of_yeses():
    """A floor nothing can fail is the same defect as one nothing can clear. Break the
    persisted pack's bust field and the properties that depend on it must stop holding."""
    db = _db()
    _file(db, _package(version="v15"))
    freeze.freeze(db, owner_approved=True, realism_judger=_SoundReference())

    from sqlalchemy import select

    from brambleloop.core.models import ModelIdentity

    with db.session() as s:
        row = s.scalar(select(ModelIdentity))
        fields = dict(row.fields)
        fields["bust_proportions"] = ""
        row.fields = fields

    proof = freeze.enforcement_proof(db)
    assert proof["proved"] is False
    assert "the_revised_pack_is_what_loads" in proof["failed"]


def test_the_freeze_job_records_the_approval_and_refuses_to_replace_her():
    """It runs as a job on a recorded approval rather than on an operator token, and a
    re-run reports the identity that exists rather than writing a second one."""
    from brambleloop.agents.registry import Registry
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime.release import JobContext, handle_model_freeze

    db = _db()
    Registry(db).seed_defaults()
    _file(db, _package(version="v15"))
    queue = JobQueue(db)
    ctx = JobContext(job=queue.enqueue("creative_director", "creative.model_freeze", {}),
                     db=db, queue=queue, registry=Registry(db), phase=None)

    # Patched at `photoreal.judge` rather than injected, because this test is about the
    # handler and the handler has no injection point: a live vision call in a test would
    # be a test of the network. The gate itself is tested directly below.
    from brambleloop.visual import photoreal

    original = photoreal.judge
    photoreal.judge = lambda ref, db=None, provider=None: {
        "judged": True, "checks": {k: True for k in photoreal.CHECKS}, "notes": ""}
    try:
        first = handle_model_freeze(ctx)
        second_run = handle_model_freeze(ctx)
    finally:
        photoreal.judge = original

    assert first["frozen"] is True
    assert first["pack_version"] == "v15"
    assert first["enforcement_proved"] is True, first["enforcement_failed"]

    assert second_run["frozen"] is False and second_run["already_canonical"] is True


def test_the_freeze_job_declines_rather_than_raising_when_no_pack_can_be_frozen():
    """A refusal is the correct outcome, not an error: the job did its job by declining,
    and a dead letter would make a correct refusal look like a broken worker."""
    from brambleloop.agents.registry import Registry
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime.release import JobContext, handle_model_freeze

    db = _db()
    Registry(db).seed_defaults()
    _file(db, _package(version="v16", unpinned=("bust",)))
    queue = JobQueue(db)
    ctx = JobContext(job=queue.enqueue("creative_director", "creative.model_freeze", {}),
                     db=db, queue=queue, registry=Registry(db), phase=None)

    out = handle_model_freeze(ctx)
    assert out["ran"] is True and out["frozen"] is False
    assert "bust_proportions" in out["refused"]
    assert model_registry.canonical_pack(db) is None


def test_the_recorded_approval_authorises_the_identity_and_nothing_else():
    """The next session must not be able to read an identity approval as a launch one."""
    record = freeze.approved()
    assert record["at"] == "2026-09-22"
    for refused in ("Etsy publication", "advertising", "customer communication"):
        assert refused in record["does_not_authorise"]
    assert "Shadow Mode stands" in record["does_not_authorise"]
    assert "never eligible for automatic selection" in record["superseded"]


def test_a_reference_that_reads_as_generated_is_never_frozen():
    """The finding of 2026-09-23, made structural.

    Three model frames were blocked on `skin_looks_real` and `processing_is_restrained`
    against direction naming airbrushed skin at paragraph length, and the third escalation
    of that language achieved nothing -- because the prompt was arguing with the picture.
    Reading the frozen pack itself found poreless skin on the face frame and indistinct
    fingers on the body frame: every render inherited exactly the failures blocking it.

    Freezing is a one-way door, so this is the last moment the question can be asked for
    free. A pack that cannot produce a believable photograph is not an identity, it is a
    permanent floor nothing downstream can clear.
    """
    db = _db()
    _file(db, _package(version="v15"))
    try:
        freeze.freeze(db, owner_approved=True,
                      realism_judger=_SoundReference(skin_looks_real=False))
    except freeze.FreezeRefused as exc:
        assert "skin_looks_real" in str(exc)
        assert "a generator copies the skin it is shown" in str(exc)
    else:
        raise AssertionError("an airbrushed reference was frozen as canonical")

    assert model_registry.canonical_pack(db) is None, "a refused pack was still promoted"


def test_a_reference_flawed_only_in_its_own_scene_is_still_frozen():
    """The gate has to be able to pass, or it is the defect it was built against.

    Lighting and sterile perfection belong to the scene a new frame builds around her, so
    refusing on those would reject a usable identity over a flaw that never reaches a
    listing -- a floor nothing can clear, installed by the fix for a floor nothing can
    clear.
    """
    db = _db()
    _file(db, _package(version="v15"))
    out = freeze.freeze(db, owner_approved=True,
                        realism_judger=_SoundReference(lighting_is_coherent=False,
                                                       not_sterile_perfection=False))
    assert out["frozen"] is True


def test_a_reference_the_judge_could_not_read_is_unproven_rather_than_sound():
    """Unjudged is not a pass, and freezing on it would make the question permanent."""
    class _Silent(_SoundReference):
        def see(self, system, prompt, refs, max_tokens=0):
            class R:
                text = "the provider declined"
                input_tokens = 1
                output_tokens = 1
            return R()

    db = _db()
    _file(db, _package(version="v15"))
    try:
        freeze.freeze(db, owner_approved=True, realism_judger=_Silent())
    except freeze.FreezeRefused as exc:
        assert "unproven rather than sound" in str(exc)
    else:
        raise AssertionError("a pack nobody could judge was frozen")


# ---------------------------------------------------------------------------
# The references are the approved bytes (2026-09-26)


def _kept_body(db, *, frame: str) -> tuple[str, str]:
    """A body frame the artifact store can actually recover, and its sha256."""
    from brambleloop.visual import tournament

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as fh:
        fh.write(b"\x89PNG\r\n\x1a\n" + frame.encode())
        path = fh.name
    kept = tournament._keep(path, db=db, why="a test body reference")
    return path, kept["sha256"]


def _package_with_real_body(db) -> dict:
    package = _package(version="v15")
    _, torso = _kept_body(db, frame="torso")
    _, full = _kept_body(db, frame="full")
    package["reference_frames"] = [
        {"frame": "neutral_portrait", "image": {"sha256": brief.sha256_of(brief.approved_portrait())}},
        {"frame": "torso_fit_reference", "image": {"sha256": torso}},
        {"frame": "full_length_standing", "image": {"sha256": full}},
    ]
    return package


def _tampered_assets_dir() -> str:
    import shutil

    tmp = Path(tempfile.mkdtemp())
    for path in Path(brief.ASSETS_DIR).iterdir():
        if path.is_file():
            shutil.copy(path, tmp / path.name)
    (tmp / "identity_portrait.jpg").write_bytes(b"\xff\xd8not her")
    return str(tmp)


def test_the_freeze_pins_every_reference_by_hash():
    """The bytes she is, not the paths they were at."""
    db = _db()
    package = _package_with_real_body(db)
    _file(db, package)
    record = freeze.freeze(db, owner_approved=True, realism_judger=_SoundReference())
    hashes = record["fields"]["reference_hashes"]
    assert hashes["neutral_portrait"] == brief.manifest_entry(role=brief.APPROVED_FACE)["sha256"]
    assert hashes["torso_fit_reference"] == package["reference_frames"][1]["image"]["sha256"]
    assert hashes["full_length_standing"] == package["reference_frames"][2]["image"]["sha256"]
    # Persisted, not only returned: the gate reads the row.
    assert model_registry.canonical_pack(db).fields["reference_hashes"] == hashes


def test_reference_paths_hands_out_only_files_that_hash_to_the_pinned_bytes():
    db = _db()
    package = _package_with_real_body(db)
    _file(db, package)
    freeze.freeze(db, owner_approved=True, realism_judger=_SoundReference())

    paths = freeze.reference_paths(db, package=package)
    assert paths["face"] == brief.approved_portrait()
    assert paths["body"] and paths["body_frame"] == freeze.BODY_FRAME
    assert brief.sha256_of(paths["body"]) == paths["hashes"]["torso_fit_reference"]
    assert paths["hashes"]["neutral_portrait"].startswith("a42aeac7")


def test_a_replaced_committed_portrait_is_not_the_face_and_is_not_a_fallback():
    """The defect this closes: `reference_paths` fell back to whatever bytes sat at the
    committed portrait's path. A replaced file would have become the approved face
    without anybody deciding it, and every frame conditioned on it would have agreed."""
    db = _db()
    _file(db, _package(version="v15"))
    freeze.freeze(db, owner_approved=True, realism_judger=_SoundReference())

    original = brief.ASSETS_DIR
    brief.ASSETS_DIR = _tampered_assets_dir()
    try:
        paths = freeze.reference_paths(db, package=_package(version="v15"))
        assert paths["face"] == "", "tampered portrait bytes were handed out as the face"
        assert paths["expected_hashes"]["neutral_portrait"].startswith("a42aeac7")
        proof = freeze.enforcement_proof(db)
        assert "references_are_the_approved_bytes" in proof["failed"]
    finally:
        brief.ASSETS_DIR = original
    assert freeze.reference_paths(db, package=_package(version="v15"))["face"] == \
        brief.approved_portrait()


def test_a_body_frame_that_recovers_as_different_bytes_is_returned_as_nothing():
    """Same answer as an unrecoverable frame, because for the caller it is the same fact:
    there is no approved body reference to hand over."""
    from sqlalchemy import select

    from brambleloop.core.models import ModelIdentity

    db = _db()
    package = _package_with_real_body(db)
    _file(db, package)
    freeze.freeze(db, owner_approved=True, realism_judger=_SoundReference())
    assert freeze.reference_paths(db, package=package)["body"]

    with db.session() as s:
        row = s.scalar(select(ModelIdentity))
        fields = dict(row.fields)
        fields["reference_hashes"] = {**fields["reference_hashes"],
                                      "torso_fit_reference": "0" * 64,
                                      "full_length_standing": "1" * 64}
        row.fields = fields

    paths = freeze.reference_paths(db, package=package)
    assert paths["body"] == "" and paths["full_length"] == ""
    assert paths["face"] == brief.approved_portrait(), "the face was not touched"


def test_a_pack_frozen_before_hashes_were_recorded_is_still_pinned():
    """The production row of 2026-09-22 has no `reference_hashes`. Its face is the
    committed portrait by construction and its body frames are the sha256 values the
    build wrote when it kept the bytes, so nothing about it is unpinned."""
    from sqlalchemy import select

    from brambleloop.core.models import ModelIdentity

    db = _db()
    package = _package_with_real_body(db)
    _file(db, package)
    freeze.freeze(db, owner_approved=True, realism_judger=_SoundReference())
    with db.session() as s:
        row = s.scalar(select(ModelIdentity))
        fields = dict(row.fields)
        del fields["reference_hashes"]
        row.fields = fields

    expected = freeze.expected_reference_hashes(package, model_registry.canonical_pack(db))
    assert expected["neutral_portrait"].startswith("a42aeac7")
    assert expected["torso_fit_reference"] == package["reference_frames"][1]["image"]["sha256"]
    paths = freeze.reference_paths(db, package=package)
    assert paths["face"] == brief.approved_portrait() and paths["body"]
    # ...but a frame's provenance against such a pack is unverifiable, not verified.
    verdict = identity.provenance_check(
        {"conditioned_on": {"reference_hashes": {"neutral_portrait": expected["neutral_portrait"]}}},
        model_registry.canonical_pack(db))
    assert verdict["verdict"] == identity.PROVENANCE_UNVERIFIABLE


def test_the_approval_record_names_who_and_how_and_does_not_invent_the_fingerprint():
    record = freeze.approved()
    assert record["approved_by"] == "owner"
    assert record["channel"]
    assert record["approved_pack_version"].startswith("v15-")
    assert record["approved_pack_fingerprint"] is None
    assert "not determinable from code" in record["approved_pack_fingerprint_note"]
    # When the fingerprint is unknown the proof says so rather than claiming a match.
    db = _db()
    _file(db, _package(version="v15"))
    freeze.freeze(db, owner_approved=True, realism_judger=_SoundReference())
    check = [c for c in freeze.enforcement_proof(db)["checks"]
             if c["check"] == "references_are_the_approved_bytes"][0]
    assert check["evidence"]["fingerprint_compared"] is False


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
