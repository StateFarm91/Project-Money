"""W4-CONDPACK: F-733 provider conditioning packages for Laura's canonical identity.

Each identity-lock image provider has a stored package under
`visual/assets/conditioning/laura-r2-a42aeac7/`. Each package records which canonical
frames the provider receives, in which order (face first) and how many its dialect actually
transmits (every reference, since W4-FLUXAPI). `verify_stored` re-derives every package from the canonical files and
refuses a changed reference, a forbidden hash, a reordered pack or an edited file. Laura's
images are read, never written. Local only; no provider call.

Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_w4_condpack.py
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
_TMP = tempfile.mkdtemp(prefix="w4_condpack_")

from brambleloop.visual import canonical  # noqa: E402
from brambleloop.visual import conditioning as C  # noqa: E402


def test_every_lock_provider_has_a_stored_package_that_verifies():
    keys = C.lock_providers()
    assert keys and "flux-2-pro" in keys and "gpt-image-2" in keys
    reg = C.registry()
    assert reg["ok"] is True, reg
    assert reg["identity"] == canonical.IDENTITY_ID == "laura-r2-a42aeac7"
    for row in reg["providers"]:
        assert row["ok"], row


def test_the_package_is_the_canonical_revision_face_first_and_honest_about_transmission():
    keys = C.lock_providers()
    assert keys
    forbidden = canonical.forbidden_hashes()
    for key in keys:
        pkg = json.loads(C.path_for(key).read_text())
        frames = [r["frame"] for r in pkg["references"]]
        assert frames == list(C.FRAME_ORDER), (key, frames)
        assert {r["frame"]: r["sha256"] for r in pkg["references"]} == \
            canonical.CURRENT_REFERENCE_HASHES
        assert not {r["sha256"] for r in pkg["references"]} & forbidden
        assert pkg["references"][0]["transmitted"] is True
    # W4-FLUXAPI: BFL carried only the first reference until 2026-10-19. Both BFL models now
    # carry the whole canonical pack (portrait, torso, full length), and nothing is limited.
    for bfl_key in ("flux-2-pro", "flux-3-image"):
        bfl = C.package(bfl_key)
        assert bfl["transmitted"] == 3 and bfl["complete_pack_transmitted"] is True, bfl_key
        assert all(r["transmitted"] for r in bfl["references"]) and "limitation" not in bfl
    gpt = C.package("gpt-image-2")
    assert gpt["transmitted"] == 3 and gpt["complete_pack_transmitted"] is True


def test_an_edited_stored_package_fails_verification():
    original = C.path_for
    tmp = Path(_TMP) / "flux-2-pro.json"
    data = json.loads(original("flux-2-pro").read_text())
    data["references"][0], data["references"][1] = data["references"][1], data["references"][0]
    tmp.write_text(json.dumps(data))
    C.path_for = lambda key: tmp
    try:
        out = C.verify_stored("flux-2-pro")
    finally:
        C.path_for = original
    assert out["ok"] is False and any(p.startswith("references") for p in out["problems"])


def test_a_missing_or_altered_reference_refuses_the_package():
    original = canonical.reference_file
    canonical.reference_file = lambda frame: "" if frame == "torso_fit_reference" \
        else original(frame)
    try:
        refused = None
        try:
            C.package("gpt-image-2")
        except C.ConditioningRefused as exc:
            refused = str(exc)
        assert refused and "torso_fit_reference" in refused
        assert C.verify_stored("gpt-image-2")["ok"] is False
    finally:
        canonical.reference_file = original


def test_a_forbidden_hash_can_never_enter_a_package():
    original = canonical.forbidden_hashes
    face = canonical.CURRENT_REFERENCE_HASHES["neutral_portrait"]
    canonical.forbidden_hashes = lambda m=None: frozenset({face.lower()})
    try:
        refused = None
        try:
            C.package("nano-banana-2")
        except C.ConditioningRefused as exc:
            refused = str(exc)
        assert refused and "forbidden" in refused
    finally:
        canonical.forbidden_hashes = original


def test_unknown_or_non_locking_providers_have_no_package():
    for key in ("imagen-4", "no-such-provider"):
        refused = None
        try:
            C.package(key)
        except C.ConditioningRefused as exc:
            refused = exc
        assert refused is not None, key


def test_building_reads_laura_and_never_changes_her_files():
    before = {f: Path(canonical.reference_file(f)).read_bytes() for f in C.FRAME_ORDER}
    assert before and all(before.values())
    C.package("gpt-image-2")
    after = {f: Path(canonical.reference_file(f)).read_bytes() for f in C.FRAME_ORDER}
    assert before == after
    assert canonical.verify()["ok"] is True


if __name__ == "__main__":
    import time

    failures = 0
    tests = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
    assert tests
    for name, test in tests:
        started = time.time()
        try:
            test()
            print("OK  ", name, f"{time.time() - started:.1f}s")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            import traceback

            traceback.print_exc()
            print("FAIL", name, type(exc).__name__, str(exc)[:500])
    print(f"{len(tests) - failures}/{len(tests)} passing")
    shutil.rmtree(_TMP, ignore_errors=True)
    sys.exit(bool(failures))
