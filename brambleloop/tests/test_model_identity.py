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
    M.record_candidate(db, "face-a", fields=fields)
    M.select_canonical(db, "face-a", owner_approved=True)

    same = {"face": fields["facial_geometry"], "hair": fields["hair"],
            "eyes": fields["eyes"], "age": fields["age_band"],
            "stylisation": fields["representative_expressions"]}
    ok = M.gate_frames(db, [{"role": "hero", "has_model": True, "image_ref": "/tmp/a.png"}],
                       observer=lambda _db, ref: dict(same))
    assert ok["verdict"] == "pass", ok

    drifted = {**same, "hair": "a different woman's hair"}
    bad = M.gate_frames(db, [{"role": "hero", "has_model": True, "image_ref": "/tmp/a.png"}],
                        observer=lambda _db, ref: dict(drifted))
    assert bad["verdict"] == "fail"
    assert "hair" in str(bad["blocking"])


def test_an_unreadable_observation_blocks_rather_than_passing():
    """An unmeasured dimension is not a matching one."""
    db = _db()
    M.record_candidate(db, "face-a", fields=_complete_fields())
    M.select_canonical(db, "face-a", owner_approved=True)
    out = M.gate_frames(db, [{"role": "hero", "has_model": True, "image_ref": "/tmp/a.png"}],
                        observer=lambda _db, ref: {"error": "the observer could not answer"})
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
