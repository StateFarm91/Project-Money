"""Freezing the canonical identity, and the ways a freeze quietly writes a hole (#200).

The owner approved the revised pack on 2026-09-22 and asked for seven properties to be
proved *after persistence*. Most of these tests are about the freeze refusing, because the
frozen pack becomes the definition of a person: `drift_check` compares against it and
`gate_frames` blocks on it, so a field it cannot state is not a missing sentence — it is a
dimension that can never drift again. That is the owner's unmeasurable-is-never-pass rule
made permanent rather than broken once, which is the worse of the two.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog  # noqa: E402
from brambleloop.visual import brief, freeze, identity, model_registry  # noqa: E402
from brambleloop.visual import reference_pack  # noqa: E402


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
        freeze.freeze(db, owner_approved=True)
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

    record = freeze.freeze(db, owner_approved=True)
    assert record["frozen"] is True
    assert record["pack_version"] == "v15"
    assert record["skipped_newer"][0]["pack_version"] == "v16"


def test_nothing_freezes_without_the_owner_and_nothing_freezes_twice():
    db = _db()
    _file(db, _package(version="v15"))

    try:
        freeze.freeze(db, owner_approved=False)
    except freeze.FreezeRefused as exc:
        assert "the owner's decision" in str(exc)
    else:                                                    # pragma: no cover
        raise AssertionError("froze without the owner")
    assert model_registry.canonical_pack(db) is None

    first = freeze.freeze(db, owner_approved=True)
    assert first["frozen"] is True
    second = freeze.freeze(db, owner_approved=True)
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
    record = freeze.freeze(db, owner_approved=True)
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
    freeze.freeze(db, owner_approved=True)

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
    freeze.freeze(db, owner_approved=True)

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

    first = handle_model_freeze(ctx)
    assert first["frozen"] is True
    assert first["pack_version"] == "v15"
    assert first["enforcement_proved"] is True, first["enforcement_failed"]

    second = handle_model_freeze(ctx)
    assert second["frozen"] is False and second["already_canonical"] is True


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
