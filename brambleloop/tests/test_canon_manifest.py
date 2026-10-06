"""Laura's canonical identity is preserved, pinned and protected (D-FB-11, D-FB-12).

What this file proves, without any model call or network:
* MANIFEST.json v2 records every committed image (sha256, bytes, dimensions, role,
  provenance, forbidden_as_fallback), and `canonical.verify()` fails on a changed byte, a
  deleted file, a changed identity id or a decision id code does not recognise;
* the approved face is unchanged (a42aeac7...) and the canonical pack's face frame is it;
* historical and superseded frames are never handed out as a reference;
* retiring/replacing/repairing Laura, or freezing any build other than v15, is refused
  without an owner decision in `canonical.AUTHORISED_IDENTITY_CHANGES`;
* the identity gate fails "a woman similar to Laura";
* preserving assets flips no customer-facing readiness: nothing is publication-approved and
  photorealism still fails closed.

Run: cd brambleloop && PYTHONPATH=src python3 tests/test_canon_manifest.py
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.visual import brief, canonical, freeze, identity  # noqa: E402
from brambleloop.visual import model_registry as M  # noqa: E402

ASSETS = Path(brief.ASSETS_DIR)
REAL_ASSETS_DIR = brief.ASSETS_DIR
FACE = "a42aeac72ba5733e42f55f9eb527218242c50610531ec9263ffb6f3e82519bc9"
# D-FB-14: the owner-approved v6 body references, computed from the files independently below.
TORSO = "afe6191fb4c68d0a9c61229fe822a1032ee7c54150597210888db25b0f9ef0db"
FULL = "f32bac686cba46c75e3ac193e72f2bcea4ba7ebc80355a102a4bed4bca3931e0"
FAILS = 0


def check(name: str, fn) -> None:
    global FAILS
    try:
        fn()
        print(f"OK {name}")
    except Exception as exc:  # noqa: BLE001
        FAILS += 1
        print(f"FAIL {name}: {type(exc).__name__}: {exc}")


def _db() -> Database:
    db = Database("sqlite://")
    db.create_all()
    return db


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest() -> dict:
    return json.loads((ASSETS / brief.MANIFEST_NAME).read_text())


def _entries() -> list[dict]:
    m = _manifest()
    out = list(m["assets"]) + list(m["library"])
    assert out
    return out


class _Tmp:
    """A full copy of the assets tree that brief/canonical read for the duration."""

    def __enter__(self):
        self.root = Path(tempfile.mkdtemp()) / "assets"
        shutil.copytree(ASSETS, self.root)
        brief.ASSETS_DIR = str(self.root)
        return self.root

    def __exit__(self, *exc):
        brief.ASSETS_DIR = REAL_ASSETS_DIR
        shutil.rmtree(self.root.parent, ignore_errors=True)
        return False


# --- manifest truth ---------------------------------------------------------------------------

def test_the_manifest_verifies_and_names_laura():
    out = canonical.verify()
    assert out["ok"], out["problems"]
    m = _manifest()
    assert m["manifest_version"] == 2
    assert m["identity"]["identity_id"] == canonical.IDENTITY_ID == "laura-r2-a42aeac7"
    assert m["identity"]["name"] == "Laura"
    assert m["identity"]["face_sha256"] == FACE
    assert m["identity"]["revision"] == 2 and m["identity"]["revision_decision"] == "D-FB-14"
    assert m["identity"]["prior_identity_id"] == "laura-v15-a42aeac7"
    assert m["identity"]["prior_frozen_identity_version"].startswith("v15-")
    assert m["identity"]["reference_hashes"] == {
        "neutral_portrait": FACE, "torso_fit_reference": TORSO,
        "full_length_standing": FULL}


def test_every_entry_hashes_sizes_and_measures_independently():
    from PIL import Image

    entries = _entries()
    assert entries
    for e in entries:
        path = ASSETS / e["file"]
        assert path.is_file(), e["file"]
        assert _sha(path) == e["sha256"], e["file"]
        assert path.stat().st_size == e["bytes"], e["file"]
        with Image.open(path) as im:
            assert list(im.size) == e["dimensions"], e["file"]
        assert e["role"] in canonical.ROLES_V2, e
        assert isinstance(e["forbidden_as_fallback"], bool), e
        assert e["provenance"]["decision_ids"], e
        assert e["publication_status"] in canonical.PUBLICATION_STATUSES


def test_every_file_under_canonical_is_listed():
    files = sorted(p for p in (ASSETS / "canonical").rglob("*") if p.is_file())
    assert files
    listed = {e["file"] for e in _entries()}
    for p in files:
        assert str(p.relative_to(ASSETS)) in listed, p


def test_revision_two_is_the_face_plus_the_approved_v6_body_by_bytes():
    pack = ASSETS / "canonical" / "laura-r2-a42aeac7" / "reference_pack"
    assert _sha(pack / "neutral_portrait.jpg") == FACE
    assert _sha(pack / "torso_fit_reference.png") == TORSO
    assert _sha(pack / "full_length_standing.png") == FULL
    assert canonical.CURRENT_REFERENCE_HASHES == {
        "neutral_portrait": FACE, "torso_fit_reference": TORSO, "full_length_standing": FULL}
    revs = _manifest()["revisions"]
    assert [r["identity_id"] for r in revs] == ["laura-v15-a42aeac7", "laura-r2-a42aeac7"]
    assert revs[1]["supersedes"] == "laura-v15-a42aeac7" and revs[1]["decision"] == "D-FB-14"


def test_the_approved_face_is_unchanged_and_is_the_pack_face():
    assert _sha(ASSETS / "identity_portrait.jpg") == FACE
    assert brief.approved_portrait() == str(ASSETS / "identity_portrait.jpg")
    copy = ASSETS / "canonical" / canonical.IDENTITY_ID / "reference_pack" / "neutral_portrait.jpg"
    assert (ASSETS / "identity_portrait.jpg").read_bytes() == copy.read_bytes()


def test_missing_v15_frames_are_declared_not_synthesised():
    missing = _manifest()["missing_canonical"]
    assert missing
    frames = {(x["group"], x["frame"]) for x in missing}
    assert ("reference_pack", "torso_fit_reference") in frames
    assert ("reference_pack", "full_length_standing") in frames
    assert {f for g, f in frames if g == "stress_set"} == set(canonical.STRESS_FRAMES)
    for x in missing:
        assert x["sha256"] is None and x["sha256_known"] is False, x
        assert "OA-CANON-1" in x["recovery"]
    # No file claims the canonical stress-set role: none was recoverable.
    assert not [e for e in _entries() if e["role"] == "canonical_stress_set"]


def test_v6_is_never_claimed_to_be_v15():
    v6 = [e for e in _entries() if "v6_" in e["file"]]
    assert len(v6) == 5      # the stress scenes D-FB-14 did not approve stay historical
    for e in v6:
        assert e["role"] == "historical" and e["forbidden_as_fallback"] is True
        assert "NOT proven" in e["note"]
    body = [e for e in _entries() if e["sha256"] in (TORSO, FULL)]
    assert len(body) == 2
    for e in body:
        assert e["identity_id"] == "laura-r2-a42aeac7"
        assert "v6 bust-revision run 2026-09-21" in e["provenance"]["run"]
        assert "v15" not in e["provenance"]["run"].replace("v15 frames", "")
        assert "NOT the missing frozen-v15" in e["note"]
    # The v15 frames are still missing history of revision 1, never filled by v6 bytes.
    missing = _manifest()["missing_canonical"]
    assert len(missing) == 7
    for x in missing:
        assert x["identity_id"] == "laura-v15-a42aeac7" and x["sha256"] is None


# --- tamper evidence --------------------------------------------------------------------------

def test_a_changed_byte_in_any_canonical_or_historical_asset_fails():
    with _Tmp() as root:
        target = root / [e for e in _entries() if "v6_" in e["file"]][0]["file"]
        data = bytearray(target.read_bytes())
        data[len(data) // 2] ^= 0x01
        target.write_bytes(bytes(data))
        out = canonical.verify()
        assert not out["ok"] and any("bytes changed" in p for p in out["problems"]), out


def test_a_deleted_asset_fails():
    with _Tmp() as root:
        (root / "canonical" / canonical.IDENTITY_ID / "reference_pack"
         / "neutral_portrait.jpg").unlink()
        out = canonical.verify()
        assert not out["ok"] and any("not on disk" in p for p in out["problems"]), out


def test_a_changed_identity_id_or_unrecorded_decision_fails():
    with _Tmp() as root:
        path = root / brief.MANIFEST_NAME
        m = json.loads(path.read_text())
        m["identity"]["identity_id"] = "someone-else-v1-00000000"
        path.write_text(json.dumps(m))
        assert not canonical.verify()["ok"]
        m["identity"]["identity_id"] = canonical.IDENTITY_ID
        m["identity"]["owner_decision_ids"] = ["D-FB-99"]
        path.write_text(json.dumps(m))
        out = canonical.verify()
        assert not out["ok"] and any("decisions" in p for p in out["problems"]), out


def test_marking_an_asset_publication_approved_in_the_manifest_alone_fails():
    with _Tmp() as root:
        path = root / brief.MANIFEST_NAME
        m = json.loads(path.read_text())
        m["assets"][0]["publication_status"] = "publication_approved"
        path.write_text(json.dumps(m))
        assert not canonical.verify()["ok"]


def test_identity_decisions_are_recorded_in_the_decision_log():
    log = (ROOT / "DECISION_LOG.md").read_text()
    assert canonical.IDENTITY_DECISIONS
    for d in canonical.IDENTITY_DECISIONS + canonical.AUTHORISED_IDENTITY_CHANGES:
        assert f"## {d} " in log, d
    # The protected-authority mechanism: the current identity's revision cites an owner
    # decision that is recorded, authorised in code and spent by exactly one revision; no
    # authorisation exists that no revision accounts for.
    current = [r for r in canonical.REVISIONS if r["identity_id"] == canonical.IDENTITY_ID]
    assert len(current) == 1 and current[0]["status"] == "current"
    assert current[0]["decision"] == canonical.REVISION_DECISION_ID == "D-FB-14"
    assert f"## {current[0]['decision']} " in log
    entry = log.split("## D-FB-14 ", 1)[1].split("\n## ", 1)[0]
    for sha in (FACE, TORSO, FULL):
        assert sha in entry, sha
    for d in canonical.AUTHORISED_IDENTITY_CHANGES:
        assert [r for r in canonical.REVISIONS if r["decision"] == d and r["supersedes"]], d
    assert set(canonical.AUTHORISED_IDENTITY_CHANGES) == {
        r["decision"] for r in canonical.REVISIONS if r["supersedes"]}
    assert (ROOT / "spec" / "07_Laura_Owner_Ruling_2026-10-06.md").is_file()


# --- references and fallbacks -----------------------------------------------------------------

def test_historical_and_superseded_hashes_are_forbidden_references():
    forbidden = freeze.forbidden_reference_hashes()
    assert forbidden is not None
    hist = [e for e in _entries() if e["role"] in ("historical", "superseded_body",
                                                    "owner_concept")]
    assert hist
    for e in hist:
        assert e["sha256"] in forbidden, e["file"]
    assert FACE not in forbidden
    # D-FB-14: the revised body frames are canonical now; the v5 body frames stay forbidden.
    assert TORSO not in forbidden and FULL not in forbidden
    v5 = [e for e in _entries() if "v5" in e["file"] and e["sha256"] != FACE]
    assert v5
    for e in v5:
        assert e["sha256"] in forbidden and e["forbidden_as_fallback"], e["file"]


def test_a_historical_frame_is_never_returned_as_a_verified_reference():
    hist = [e for e in _entries() if e["role"] == "historical"]
    assert hist
    for e in hist:
        path = str(ASSETS / e["file"])
        # Even when somebody names its own hash as the expected one.
        assert freeze._verified(path, e["sha256"]) == "", e["file"]
        try:
            canonical.refuse_forbidden_reference(path)
        except canonical.CanonRefused:
            continue
        raise AssertionError(f"{e['file']} was accepted as a reference")
    canonical.refuse_forbidden_reference(brief.approved_portrait())  # the face is allowed


# --- identity creation and replacement --------------------------------------------------------

def _laura_db() -> Database:
    db = _db()
    fields = {**{f: f"pinned-{f}" for f in identity.IDENTITY_FIELDS},
              "reference_hashes": {"neutral_portrait": FACE,
                                   "torso_fit_reference": "b" * 64,
                                   "full_length_standing": "c" * 64}}
    M.record_candidate(db, canonical.REGISTRY_KEY, fields=fields,
                       image_refs=[brief.approved_portrait(), "b" * 64, "c" * 64])
    M.select_canonical(db, canonical.REGISTRY_KEY, owner_approved=True)
    return db


def _approval(**kw) -> dict:
    rec = {"at": "2026-10-06", "decision": "replace her", "supersedes_version": 1,
           "scope": "redesign", "approved_by": "owner"}
    rec.update(kw)
    return rec


def test_laura_cannot_be_replaced_or_redesigned_without_an_owner_decision():
    db = _laura_db()
    assert canonical.is_laura(M.canonical_pack(db))
    M.record_candidate(db, "someone-similar", fields={f: "x" for f in identity.IDENTITY_FIELDS})
    for record in (_approval(), _approval(scope="portrait_repair"),
                   _approval(owner_decision_id="D-FB-11"),
                   _approval(owner_decision_id="made-up"),
                   # the revision decision, offered for a different change, authorises nothing
                   _approval(owner_decision_id="D-FB-14"),
                   _approval(owner_decision_id="D-FB-14", scope="reference_revision")):
        try:
            M.replace_canonical(db, new_key="someone-similar", redesign_approval=record)
        except canonical.CanonRefused as exc:
            assert "AUTHORISED_IDENTITY_CHANGES" in str(exc) or "new owner decision" in str(exc)
            continue
        raise AssertionError(f"Laura was replaced on {record!r}")
    pack = M.canonical_pack(db)
    assert pack.version == 1 and canonical.is_laura(pack)


def test_a_portrait_repair_of_laura_is_refused_without_an_owner_decision():
    from brambleloop.visual import portrait_repair as pr

    db = _laura_db()
    tmp = Path(tempfile.mkdtemp())
    try:
        (tmp / "candidate.png").write_bytes(b"a prettier, different face")
        try:
            pr.adopt(db, candidate_ref=str(tmp / "candidate.png"), verdict=pr.REPAIRED,
                     redesign_approval=_approval(scope="portrait_repair"))
        except identity.IdentityRefused as exc:
            assert "Laura" in str(exc)
        else:
            raise AssertionError("a repaired face replaced Laura's approved face")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    assert canonical.face_hash_of(M.canonical_pack(db)) == FACE


def test_freezing_any_build_but_v15_is_refused():
    for version in ("v16-the-fallback-provider-has-time-to-render", "v14-x", "v17", "v6"):
        try:
            canonical.require_frozen_build(version)
        except canonical.CanonRefused:
            continue
        raise AssertionError(f"{version} could be frozen as Laura")
    canonical.require_frozen_build(freeze.OWNER_APPROVAL["approved_pack_version"])
    assert freeze.OWNER_APPROVAL["approved_pack_version"] == canonical.FROZEN_IDENTITY_VERSION


def test_the_pack_procedure_label_is_not_the_identity():
    from brambleloop.visual import reference_pack

    assert canonical.FROZEN_IDENTITY_VERSION != reference_pack.PACK_VERSION
    assert canonical.IDENTITY_ID.startswith("laura-r2-")
    assert canonical.PRIOR_IDENTITY_ID.startswith("laura-v15-")


# --- revision 2 in the registry (D-FB-14) ----------------------------------------------------

def test_the_revision_is_adopted_once_and_only_as_recorded():
    from brambleloop.visual import freeze as F

    db = _laura_db()
    assert canonical.revision_of(M.canonical_pack(db)) == canonical.PRIOR_IDENTITY_ID
    out = canonical.adopt_revision(db)
    pack = M.canonical_pack(db)
    assert out["identity_id"] == canonical.IDENTITY_ID and pack.version == 2
    assert canonical.revision_of(pack) == canonical.IDENTITY_ID and canonical.is_laura(pack)
    assert pack.fields["reference_hashes"] == canonical.CURRENT_REFERENCE_HASHES
    # The identity gate's references are the new pack's, by bytes.
    paths = F.reference_paths(db)
    assert paths["hashes"] == canonical.CURRENT_REFERENCE_HASHES, paths["hashes"]
    assert paths["body"].endswith("laura-r2-a42aeac7/reference_pack/torso_fit_reference.png")
    # Spent: neither a second adoption nor a replace citing D-FB-14 changes her again.
    for attempt in (lambda: canonical.adopt_revision(db),
                    lambda: M.replace_canonical(
                        db, new_key="again", reference_hashes=dict(canonical.CURRENT_REFERENCE_HASHES),
                        redesign_approval=_approval(owner_decision_id="D-FB-14",
                                                    scope="reference_revision",
                                                    supersedes_version=2))):
        try:
            attempt()
        except canonical.CanonRefused:
            continue
        raise AssertionError("D-FB-14 was applied twice")
    assert M.canonical_pack(db).version == 2


def test_the_revision_decision_cannot_carry_other_bytes():
    db = _laura_db()
    wrong = dict(canonical.CURRENT_REFERENCE_HASHES, torso_fit_reference="7" * 64)
    try:
        M.replace_canonical(db, new_key="other-body", reference_hashes=wrong,
                            redesign_approval=_approval(owner_decision_id="D-FB-14",
                                                        scope="reference_revision"))
    except canonical.CanonRefused:
        pass
    else:
        raise AssertionError("D-FB-14 authorised a body it did not approve")
    assert canonical.revision_of(M.canonical_pack(db)) == canonical.PRIOR_IDENTITY_ID


def test_the_revision_approves_no_publication_and_waives_no_gate():
    for sha in (FACE, TORSO, FULL):
        ready = canonical.customer_ready(sha)
        assert ready["customer_ready"] is False and ready["status"] == "GATED"
        assert {"photorealism", "anatomy", "product_truth_if_product_shown"} <= \
            set(ready["blocking"])
        assert canonical.asset_status(sha) == canonical.CANONICAL_REFERENCE
    assert "not_publication_approval" in _manifest()["revisions"][1]


# --- the identity gate ------------------------------------------------------------------------

_BODY = {d: "match" for d in identity.MORPHOLOGY_DIMENSIONS}


def test_a_similar_woman_is_not_laura():
    v = canonical.laura_verdict({"face": "match", "hair": "match", "eyes": "drift",
                                 "age": "match", **_BODY})
    assert v["verdict"] == "not_laura" and v["blocks"]
    v = canonical.laura_verdict({"face": "match", "hair": "match", "eyes": "unmeasurable",
                                 "age": "match", **_BODY})
    assert v["verdict"] == "unverified" and v["blocks"]
    v = canonical.laura_verdict({"face": "match", "hair": "match", "eyes": "match",
                                 "age": "match", "stylisation": "match", **_BODY})
    assert v["verdict"] == "laura" and not v["blocks"]


def test_the_frame_gate_holds_laura_to_every_locked_face_dimension():
    db = _laura_db()
    # drift_check alone passes this (3 of 5 face dimensions readable, none drifted); for
    # Laura it is a similar-looking woman nobody confirmed, and it blocks.
    seen = {"face": "match", "hair": "match", "age": "match", "eyes": "unmeasurable",
            "stylisation": "unmeasurable", **_BODY}
    alone = identity.drift_check(seen, M.canonical_pack(db))
    assert alone["verdict"] == "pass"
    out = M.gate_frames(db, [{"role": "hero", "has_model": True, "image_ref": "/tmp/x.png"}],
                        observer=lambda db_, ref, cand: dict(seen))
    assert out["verdict"] == "fail"
    assert any("not confirmed as Laura" in b for b in out["blocking"]), out["blocking"]
    assert out["results"][0]["laura"] == "unverified"


# --- customer-facing readiness is unchanged ---------------------------------------------------

def test_preserving_assets_flips_no_customer_readiness():
    assert canonical.PUBLICATION_APPROVED == frozenset()
    assert _manifest()["identity"]["publication_approved_assets"] == []
    entries = _entries()
    assert entries
    for e in entries:
        assert e["publication_status"] != canonical.PUBLICATION_APPROVED_STATUS, e["file"]
        assert canonical.customer_ready(e["sha256"])["customer_ready"] is False
    ready = canonical.customer_ready(FACE)
    assert ready["status"] == "GATED" and "photorealism" in ready["blocking"]
    assert canonical.asset_status(FACE) == canonical.CANONICAL_REFERENCE


def test_photorealism_still_fails_closed():
    from brambleloop.visual import photoreal

    assert photoreal.gate({"judged": False})["verdict"] == "unjudged"
    assert photoreal.gate({"judged": True, "checks": {}})["verdict"] == "unjudged"
    failed = photoreal.gate({"judged": True,
                             "checks": {k: True for k in photoreal.CHECKS} |
                             {"skin_looks_real": False}})
    assert failed["verdict"] == "blocked"


_TESTS = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
assert _TESTS
for _name, _fn in _TESTS:
    check(_name, _fn)

if FAILS:
    sys.exit(1)
