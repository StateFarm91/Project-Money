"""Certification C: the canonical model, attacked rather than exercised.

Every tamper happens on a COPY in a temporary directory. The committed assets are read,
never written. Tests that expose a defect are left failing on purpose.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

_ART = tempfile.TemporaryDirectory()
os.environ.setdefault("BRAMBLELOOP_ARTIFACT_DIR", _ART.name)

from brambleloop.core.artifacts import ArtifactStore  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.visual import brief, freeze, identity  # noqa: E402
from brambleloop.visual import model_registry as M  # noqa: E402

ASSETS = Path(brief.ASSETS_DIR)
REAL_ASSETS_DIR = brief.ASSETS_DIR


def _db() -> Database:
    db = Database("sqlite://")
    db.create_all()
    return db


def _fields() -> dict:
    return {f: f"pinned-{f}" for f in identity.IDENTITY_FIELDS}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest() -> dict:
    return json.loads((ASSETS / brief.MANIFEST_NAME).read_text())


def _copy_assets() -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="cert-assets-"))
    for p in ASSETS.iterdir():
        if p.is_file():
            shutil.copy2(p, tmp / p.name)
    return tmp


def _flip_one_byte(path: Path, offset: int = 1000) -> None:
    data = bytearray(path.read_bytes())
    data[offset] ^= 0x01
    path.write_bytes(bytes(data))


class _Assets:
    """Point brief at a directory for the duration, and always put it back."""

    def __init__(self, where: Path):
        self.where = str(where)

    def __enter__(self):
        brief.ASSETS_DIR = self.where
        return self

    def __exit__(self, *exc):
        brief.ASSETS_DIR = REAL_ASSETS_DIR
        return False


def _hashed_pack(db, face: str, torso: str = "b" * 64, full: str = "c" * 64):
    fields = {**_fields(), "reference_hashes": {"neutral_portrait": face,
                                                "torso_fit_reference": torso,
                                                "full_length_standing": full}}
    M.record_candidate(db, "face-a", fields=fields, image_refs=["/tmp/ref.png"])
    return M.select_canonical(db, "face-a", owner_approved=True)


def _refuses(fn, exc=identity.IdentityRefused) -> str:
    try:
        fn()
    except exc as e:  # noqa: PERF203
        return str(e)
    raise AssertionError(f"{fn} was accepted; expected {exc.__name__}")


# --- manifest truth ---------------------------------------------------------------------------

def test_manifest_hashes_equal_committed_bytes_computed_independently():
    _vac_99 = 0
    for entry in _manifest()["assets"]:
        _vac_99 += 1
        path = ASSETS / entry["file"]
        assert path.is_file(), entry["file"]
        assert _sha(path) == entry["sha256"], entry["file"]
    assert _vac_99, "_manifest()['assets'] was empty: the loop proved nothing (F-123)"


def test_exactly_one_approved_face_and_it_verifies():
    faces = [e for e in _manifest()["assets"] if e["role"] == "approved_face"]
    assert len(faces) == 1, faces
    assert brief.approved_portrait() == str(ASSETS / faces[0]["file"])


def test_a_second_approved_face_in_the_manifest_is_ambiguity_and_is_refused():
    tmp = _copy_assets()
    m = _manifest()
    m["assets"][1]["role"] = "approved_face"
    (tmp / brief.MANIFEST_NAME).write_text(json.dumps(m))
    with _Assets(tmp):
        _refuses(brief.approved_portrait)


# --- tampered copies --------------------------------------------------------------------------

def test_untampered_copy_is_accepted_as_control():
    tmp = _copy_assets()
    with _Assets(tmp):
        assert brief.approved_portrait() == str(tmp / "identity_portrait.jpg")
        paths = freeze.reference_paths(None, package={})
        assert paths["face"] == str(tmp / "identity_portrait.jpg"), paths


def test_one_flipped_byte_in_the_face_copy_is_refused_everywhere():
    tmp = _copy_assets()
    _flip_one_byte(tmp / "identity_portrait.jpg")
    with _Assets(tmp):
        msg = _refuses(brief.approved_portrait)
        assert "does not hash" in msg
        paths = freeze.reference_paths(None, package={})
        assert paths["face"] == "", paths
        assert paths["hashes"] == {}, paths


def test_truncated_or_deleted_face_copy_is_refused():
    tmp = _copy_assets()
    (tmp / "identity_portrait.jpg").write_bytes(b"")
    with _Assets(tmp):
        _refuses(brief.approved_portrait)
        assert freeze.reference_paths(None, package={})["face"] == ""
    (tmp / "identity_portrait.jpg").unlink()
    with _Assets(tmp):
        _refuses(brief.approved_portrait)
        assert freeze.reference_paths(None, package={})["face"] == ""


def test_missing_or_corrupt_manifest_is_refused_not_trusted_by_filename():
    tmp = _copy_assets()
    (tmp / brief.MANIFEST_NAME).unlink()
    with _Assets(tmp):
        _refuses(brief.approved_portrait)
        assert freeze.reference_paths(None, package={})["face"] == ""
    (tmp / brief.MANIFEST_NAME).write_text("{not json")
    with _Assets(tmp):
        _refuses(brief.approved_portrait)


def test_face_and_manifest_both_rewritten_is_still_refused_when_the_pack_pins_the_face():
    """An attacker who replaces the face AND rewrites the manifest hash gets past
    `approved_portrait` (the manifest is its trust root). The frozen pack's pinned hash must
    still refuse the swapped bytes in `reference_paths`."""
    original = _sha(ASSETS / "identity_portrait.jpg")
    tmp = _copy_assets()
    _flip_one_byte(tmp / "identity_portrait.jpg")
    m = _manifest()
    for e in m["assets"]:
        if e["role"] == "approved_face":
            e["sha256"] = _sha(tmp / "identity_portrait.jpg")
    (tmp / brief.MANIFEST_NAME).write_text(json.dumps(m))
    db = _db()
    _hashed_pack(db, face=original)
    with _Assets(tmp):
        paths = freeze.reference_paths(db, package={})
    assert paths["face"] == "", paths


# --- provenance -------------------------------------------------------------------------------

def test_provenance_mismatch_is_refused_by_check_and_by_gate():
    db = _db()
    pack = _hashed_pack(db, face="a" * 64)
    wrong = {"conditioned_on": {"reference_hashes": {"neutral_portrait": "e" * 64}}}
    out = identity.provenance_check(wrong, pack)
    assert out["verdict"] == identity.PROVENANCE_MISMATCH and out["blocks_release"]

    # right face, wrong body frame
    body_wrong = {"conditioned_on": {"reference_hashes": {"neutral_portrait": "a" * 64,
                                                          "torso_fit_reference": "9" * 64},
                                     "body_reference_frame": "torso_fit_reference"}}
    assert identity.provenance_check(body_wrong, pack)["verdict"] == \
        identity.PROVENANCE_MISMATCH

    # a key the pack never pinned is not silently ignored
    extra = {"conditioned_on": {"reference_hashes": {"neutral_portrait": "a" * 64,
                                                     "mystery_frame": "d" * 64}}}
    assert identity.provenance_check(extra, pack)["verdict"] == identity.PROVENANCE_MISMATCH

    same = {d: identity.MATCH for d in identity.DRIFT_DIMENSIONS}
    for record in (wrong, body_wrong, extra):
        gate = M.gate_frames(db, [{"role": "hero", "has_model": True,
                                   "image_ref": "/tmp/a.png", **record}],
                             observer=lambda _d, r, c: dict(same))
        assert gate["verdict"] == "fail", gate
        assert "provenance mismatch" in " ".join(gate["blocking"])


def test_frames_with_no_hashes_are_unverifiable_never_pass():
    db = _db()
    pack = _hashed_pack(db, face="a" * 64)
    for record in (None, {}, {"conditioned_on": {}},
                   {"conditioned_on": {"reference_hashes": {}}},
                   {"conditioned_on": {"reference_hashes": {"neutral_portrait": ""}}},
                   {"conditioned_on": {"reference_hashes": {"neutral_portrait": "zz" * 32}}},
                   {"conditioned_on": {"reference_hashes": {"neutral_portrait": "a" * 63}}},
                   {"conditioned_on": {"reference_image": "/tmp/ref.jpg"}}):
        out = identity.provenance_check(record, pack)
        assert out["verdict"] == identity.PROVENANCE_UNVERIFIABLE, (record, out)
        assert out["blocks_release"] is True, (record, out)


def test_gate_does_not_pass_a_model_frame_that_carries_no_hashes_at_all():
    """Against a pack that pins reference hashes, a model-bearing frame with no
    `conditioned_on` record has no hashes. Certification requirement: no hashes ->
    unverifiable, never pass. Observed: gate_frames skips provenance entirely for such a frame
    and passes it on drift alone."""
    db = _db()
    _hashed_pack(db, face="a" * 64)
    same = {d: identity.MATCH for d in identity.DRIFT_DIMENSIONS}
    out = M.gate_frames(db, [{"role": "hero", "has_model": True, "image_ref": "/tmp/a.png"}],
                        observer=lambda _d, r, c: dict(same))
    assert out["verdict"] != "pass", (
        f"a model frame with no reference hashes passed the release gate: {out}")


# --- replacement ------------------------------------------------------------------------------

def _approval(**kw) -> dict:
    rec = {"at": "2026-10-01", "decision": "repair the portrait", "supersedes_version": 1,
           "scope": "portrait_repair", "approved_by": "owner"}
    rec.update(kw)
    return rec


def test_replace_canonical_refuses_missing_and_malformed_records():
    db = _db()
    _hashed_pack(db, face="a" * 64)
    M.record_candidate(db, "face-b", fields=_fields())
    bad = [None, {}, [], "owner said so",
           {"at": "2026-10-01"},
           _approval(scope=""), _approval(scope="REDESIGN"), _approval(scope="whim"),
           _approval(decision="  "), _approval(at=""),
           _approval(supersedes_version="one"), _approval(supersedes_version=None),
           _approval(supersedes_version=0), _approval(supersedes_version=2)]
    for record in bad:
        _refuses(lambda r=record: M.replace_canonical(db, new_key="face-b",
                                                      redesign_approval=r))
    assert M.canonical_pack(db).version == 1
    _refuses(lambda: M.replace_canonical(db, new_key="face-a", redesign_approval=_approval()),
             M.RegistryRefused)


def test_replace_canonical_refuses_a_non_integer_version_rather_than_truncating_it():
    """`int(1.9)` is 1 and `int(True)` is 1. A record naming version 1.9 or True does not
    name version 1, and a validator that truncates has 'corrected' the record."""
    db = _db()
    _hashed_pack(db, face="a" * 64)
    M.record_candidate(db, "face-b", fields=_fields())
    for version in (1.9, True):
        _refuses(lambda v=version: M.replace_canonical(
            db, new_key="face-b", redesign_approval=_approval(supersedes_version=v)))


def test_replace_canonical_does_not_attribute_an_unsigned_record_to_the_owner():
    """A record with no `approved_by` is accepted and the audit row names `owner` as the
    actor, a claim the record never made."""
    from sqlalchemy import select

    from brambleloop.core.models import AuditLog

    db = _db()
    _hashed_pack(db, face="a" * 64)
    M.record_candidate(db, "face-b", fields=_fields())
    record = _approval()
    record.pop("approved_by")
    try:
        M.replace_canonical(db, new_key="face-b", redesign_approval=record,
                            reference_hashes={"neutral_portrait": "d" * 64})
    except identity.IdentityRefused:
        return
    with db.session() as s:
        rows = [r for r in s.scalars(select(AuditLog)) if r.action == M.REPLACED_ACTION]
    raise AssertionError(f"accepted an unsigned approval and audited actor={rows[0].actor!r}")


def test_valid_replacement_retires_not_deletes_and_increments_version():
    from sqlalchemy import select

    from brambleloop.core.models import ModelIdentity

    db = _db()
    _hashed_pack(db, face="a" * 64)
    M.record_candidate(db, "face-b", fields=_fields())
    pack = M.replace_canonical(db, new_key="face-b", redesign_approval=_approval(),
                               reference_hashes={"neutral_portrait": "d" * 64})
    assert pack.version == 2 and M.canonical_pack(db).version == 2
    with db.session() as s:
        rows = {r.key: (r.state, r.version, r.retired_at, r.predecessor_key)
                for r in s.scalars(select(ModelIdentity))}
    assert rows["face-a"][0] == identity.RETIRED and rows["face-a"][1] == 1 and rows["face-a"][2]
    assert rows["face-b"][0] == identity.CANONICAL and rows["face-b"][3] == "face-a"
    assert len(M.packs(db)) == 1, "exactly one canonical after replacement"
    # the old face hash no longer verifies
    old = {"conditioned_on": {"reference_hashes": {"neutral_portrait": "a" * 64}}}
    assert identity.provenance_check(old, M.canonical_pack(db))["verdict"] == \
        identity.PROVENANCE_MISMATCH


# --- recorded approval ------------------------------------------------------------------------

def test_the_approved_pack_fingerprint_is_unknown_not_invented():
    assert "approved_pack_fingerprint" in freeze.OWNER_APPROVAL
    assert freeze.OWNER_APPROVAL["approved_pack_fingerprint"] is None
    assert freeze.approved()["approved_pack_fingerprint"] is None


# --- superseded body frames -------------------------------------------------------------------

def _superseded() -> dict:
    return {e["file"]: e["sha256"] for e in _manifest()["assets"]
            if e["role"] == "superseded_body"}


def test_no_body_reference_is_returned_when_the_revised_frames_are_unrecoverable():
    paths = freeze.reference_paths(None, package={})
    assert paths["body"] == "" and paths["full_length"] == "" and paths["body_frame"] == ""


def test_superseded_bytes_are_refused_when_the_pack_pins_the_revised_body():
    store = ArtifactStore()
    torso = (ASSETS / "identity_torso_v5.jpg").read_bytes()
    stored = store.put("cert/torso.jpg", torso, "image/jpeg")
    db = _db()
    _hashed_pack(db, face=_sha(ASSETS / "identity_portrait.jpg"), torso="7" * 64)
    package = {"pack_version": "vX", "reference_frames": [
        {"frame": "torso_fit_reference", "image": {"sha256": stored.sha256}}]}
    paths = freeze.reference_paths(db, package=package)
    assert paths["body"] == "", paths


def test_superseded_bytes_are_never_returned_even_when_a_package_names_them():
    """With no hashed canonical pack, `expected_reference_hashes` trusts the package's own
    frame hashes. A package whose body frame IS a manifest `superseded_body` hash then gets
    the superseded bytes handed back as the body reference -- the one thing the manifest says
    must never be a reference."""
    store = ArtifactStore()
    superseded = set(_superseded().values())
    torso = (ASSETS / "identity_torso_v5.jpg").read_bytes()
    stored = store.put("cert/torso.jpg", torso, "image/jpeg")
    assert stored.sha256 in superseded
    package = {"pack_version": "vX", "reference_frames": [
        {"frame": "torso_fit_reference", "image": {"sha256": stored.sha256}}]}
    paths = freeze.reference_paths(None, package=package)
    returned = {brief.sha256_of(p) for p in (paths["body"], paths["full_length"]) if p}
    assert not (returned & superseded), (
        f"reference_paths returned superseded body bytes as a reference: {paths['body']}")


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e)[:400])
    brief.ASSETS_DIR = REAL_ASSETS_DIR
    print(f"{fails} failed")
    sys.exit(1 if fails else 0)
