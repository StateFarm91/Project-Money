"""The committed assets are pinned by hash, not by filename.

Five images live under `visual/assets`, and until the manifest existed the code told them
apart by name alone -- so a replaced file at `identity_portrait.jpg` would have become the
approved face without anybody deciding it, and every frame conditioned on it would have
agreed with it perfectly. These tests are about the manifest being true of the files on
disk, and about the accessors refusing bytes that are not the recorded bytes.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.visual import brief, identity  # noqa: E402

ASSETS = Path(brief.ASSETS_DIR)


def test_every_manifest_hash_is_the_hash_of_the_file_on_disk():
    _vac_28 = 0
    for entry in brief.asset_manifest():
        _vac_28 += 1
        path = ASSETS / entry["file"]
        assert path.is_file(), f"{entry['file']} is listed and not committed"
        assert brief.sha256_of(str(path)) == entry["sha256"], (
            f"{entry['file']} does not hash to what the manifest records")
    assert _vac_28, "brief.asset_manifest() was empty: the loop proved nothing (F-123)"


def test_every_committed_image_is_in_the_manifest_and_nothing_else_is():
    listed = {e["file"] for e in brief.asset_manifest()}
    on_disk = {p.name for p in ASSETS.iterdir()
               if p.is_file() and p.name != brief.MANIFEST_NAME}
    assert listed == on_disk, (listed ^ on_disk)


def test_exactly_one_asset_is_the_approved_face():
    faces = [e for e in brief.asset_manifest() if e["role"] == brief.APPROVED_FACE]
    assert len(faces) == 1, faces
    assert faces[0]["file"] == "identity_portrait.jpg"
    assert faces[0]["sha256"].startswith("a42aeac7")
    assert brief.approved_portrait() == str(ASSETS / "identity_portrait.jpg")


def test_every_role_is_one_of_the_three_and_every_entry_is_dated():
    _vac_51 = 0
    for entry in brief.asset_manifest():
        _vac_51 += 1
        assert entry["role"] in brief.ASSET_ROLES, entry
        assert entry["committed_on"] == "2026-09-21", entry
        assert "supersedes" in entry, "the key is required even when it is null"
    assert _vac_51, "brief.asset_manifest() was empty: the loop proved nothing (F-123)"


def test_the_superseded_body_frames_are_marked_as_such_and_are_not_a_face():
    for frame in ("torso_fit_reference", "full_length_standing"):
        path = brief.approved_reference(frame)
        entry = brief.manifest_entry(file=Path(path).name)
        assert entry["role"] == brief.SUPERSEDED_BODY
        assert "superseded_by" in entry
    try:
        brief.verified_asset("identity_torso_v5.jpg", expect_role=brief.APPROVED_FACE)
    except identity.IdentityRefused as exc:
        assert "not 'approved_face'" in str(exc)
    else:
        raise AssertionError("a superseded body frame was handed out as the face")


def _tampered_assets(tmp: Path, *, tamper: str) -> None:
    """A copy of the assets directory where one file's bytes are not the recorded bytes."""
    for path in ASSETS.iterdir():
        if path.is_file():
            shutil.copy(path, tmp / path.name)
    (tmp / tamper).write_bytes(b"\xff\xd8not the approved bytes")


def test_a_replaced_portrait_is_refused_rather_than_handed_out():
    """The one committed image a render may be conditioned on, and the one whose
    replacement would be noticed least: the manifest is what notices."""
    tmp = Path(tempfile.mkdtemp())
    _tampered_assets(tmp, tamper="identity_portrait.jpg")
    original = brief.ASSETS_DIR
    brief.ASSETS_DIR = str(tmp)
    try:
        try:
            brief.approved_portrait()
        except identity.IdentityRefused as exc:
            assert "does not hash to the manifest" in str(exc)
        else:
            raise AssertionError("tampered portrait bytes were handed out as the face")
        # The untouched files are still fine: the refusal is about the bytes, not the dir.
        assert brief.approved_reference("torso_fit_reference").endswith("identity_torso_v5.jpg")
    finally:
        brief.ASSETS_DIR = original


def test_a_replaced_candidate_is_not_the_owners_candidate():
    tmp = Path(tempfile.mkdtemp())
    _tampered_assets(tmp, tamper="owner_candidate_reference.png")
    original = brief.ASSETS_DIR
    brief.ASSETS_DIR = str(tmp)
    try:
        assert brief.owner_candidate_supplied() is False
    finally:
        brief.ASSETS_DIR = original
    assert brief.owner_candidate_supplied() is True


def test_a_missing_or_malformed_manifest_is_a_refusal_not_a_return_to_filenames():
    tmp = Path(tempfile.mkdtemp())
    _tampered_assets(tmp, tamper="MANIFEST.json")  # unreadable JSON
    original = brief.ASSETS_DIR
    brief.ASSETS_DIR = str(tmp)
    try:
        try:
            brief.approved_portrait()
        except identity.IdentityRefused as exc:
            assert "could not be read" in str(exc)
        else:
            raise AssertionError("a face was handed out with no manifest to check it")
        (tmp / "MANIFEST.json").write_text(json.dumps({"assets": [
            {"file": "identity_portrait.jpg", "sha256": "0" * 64, "role": "approved_face",
             "committed_on": "2026-09-21"},
            {"file": "identity_torso_v5.jpg", "sha256": "1" * 64, "role": "approved_face",
             "committed_on": "2026-09-21"}]}))
        try:
            brief.approved_portrait()
        except identity.IdentityRefused as exc:
            assert "2 entries" in str(exc)
        else:
            raise AssertionError("two files claiming the face were not refused")
    finally:
        brief.ASSETS_DIR = original


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
