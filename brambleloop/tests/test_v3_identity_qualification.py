"""V3 (OA-V3-LAURA-QUALIFICATION, fixture-only): automatic Laura identity verification.

Audit P0-b (`research/final_build/w5/VISUAL_WIRING_AUDIT_5ba84bf7.md`, "Point 1: identity"):
identity could never PASS automatically. This suite drives the fix end to end through
`candidate_gates.RealJudges.identity` -> `vision_judges.Adapters` -> `identity_gate`.

Everything here is a deterministic stand-in: two simulated vision-judge transports and a
stub face embedder admitted by a *fixture-only* qualification record. No network, no
provider, no API key, no spend. A fixture PASS proves the wiring, never Laura's identity:
every such result is labelled `identity_gate.FIXTURE_LABEL`, and production (no embedder,
no second transport, an empty qualification register) stays UNKNOWN.

Laura's canonical references are read, verified by sha256, and never written.
"""
import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ["BRAMBLELOOP_PHASE"] = "shadow"

from brambleloop.creative import failure_codes as FC  # noqa: E402
from brambleloop.visual import candidate_gates as CG  # noqa: E402
from brambleloop.visual import canonical, identity  # noqa: E402
from brambleloop.visual import identity_gate as IG  # noqa: E402
from brambleloop.visual import vision_judges as VJ  # noqa: E402

REFS = VJ.canonical_reference_bytes()
REF_SET = set(REFS.values())

# Frames under test (opaque bytes: the identity path never decodes them).
MATCH_FRAME = b"v3-fixture-frame: Laura from her canonical references"
DRIFT_FRAME = b"v3-fixture-frame: a different woman"
LOOKALIKE_FRAME = b"v3-fixture-frame: a woman similar to Laura"
BORDER_FRAME = b"v3-fixture-frame: borderline likeness"

ALL_SAME = {d: VJ.SAME for d in identity.DRIFT_DIMENSIONS}
FACE_DIFFERENT = {**ALL_SAME, "face": VJ.DIFFERENT, "eyes": VJ.DIFFERENT}


def reading(dims: dict) -> dict:
    return {**dims, "people_in_photograph": 1}


# Simulated answers per frame: what a careful judge would report.
DEFAULT_ANSWERS = {MATCH_FRAME: reading(ALL_SAME), DRIFT_FRAME: reading(FACE_DIFFERENT),
                   LOOKALIKE_FRAME: reading(ALL_SAME), BORDER_FRAME: reading(ALL_SAME)}


class StubJudge:
    """A simulated vision transport. Finds the candidate among the four images by the
    prompt's stated layout, refuses to answer unless the other three are her canonical
    references, and answers from a fixed table. Spends nothing."""

    def __init__(self, name, model, answers=None):
        self.name, self.model = name, model
        self.answers = dict(DEFAULT_ANSWERS if answers is None else answers)
        self.calls = 0

    def read(self, prompt, images, *, system=None, max_tokens=300):
        self.calls += 1
        if "Image 4 is another photograph" in prompt:
            cand, refs = images[3], images[:3]
        else:
            cand, refs = images[0], images[1:]
        if set(refs) != REF_SET:
            return {"answered": False, "why": "references are not the canonical set"}
        got = self.answers.get(cand)
        if got is None:
            return {"answered": False, "why": "no simulated answer"}
        return {"answered": True, "reading": got, "model": self.model}


FACE_VEC = [1.0, 0.0, 0.2]
VECTORS = {
    hashlib.sha256(REFS["neutral_portrait"]).hexdigest(): FACE_VEC,
    # a torso frame whose stand-in vector is far from the face: only for the worst-of test
    hashlib.sha256(REFS["torso_fit_reference"]).hexdigest(): [0.1, 1.0, 0.0],
    hashlib.sha256(MATCH_FRAME).hexdigest(): [0.99, 0.01, 0.2],
    hashlib.sha256(DRIFT_FRAME).hexdigest(): [0.1, 1.0, 0.0],
    hashlib.sha256(LOOKALIKE_FRAME).hexdigest(): [0.1, 1.0, 0.0],
    hashlib.sha256(BORDER_FRAME).hexdigest(): [0.8, 0.45, 0.2],
}
WEIGHTS = hashlib.sha256(b"v3-stub-embedder-weights").hexdigest()


class StubEmbedder:
    """A deterministic stand-in face embedder: a fixed table by sha256 of the bytes."""

    def __init__(self, name="v3-stub-embedder", version="0.0.1-fixture", weights=WEIGHTS,
                 raises=False):
        self.name, self.version, self.weights_sha256 = name, version, weights
        self.raises = raises

    def embed(self, data):
        if self.raises:
            raise RuntimeError("embedder unavailable")
        return VECTORS[hashlib.sha256(data).hexdigest()]


def calibration(**over) -> dict:
    cal = {"method": "fixture: stand-in vectors, no real calibration",
           "evidence_sha256": hashlib.sha256(json.dumps(VECTORS, sort_keys=True).encode())
           .hexdigest(),
           "genuine_pairs": 1, "impostor_pairs": 1,
           "match_at": 0.95, "refuse_below": 0.7,
           "canonical_references": sorted(canonical.CURRENT_REFERENCE_HASHES.values()),
           "reference_frames": ["neutral_portrait"]}
    cal.update(over)
    return cal


def decision(**over) -> dict:
    d = {"decision_id": IG.FIXTURE_DECISION_ID, "decided_by": "owner",
         "decided_at": "2026-11-07T00:00:00Z", "decision": "approved",
         "scope": IG.SCOPE_FIXTURE}
    d.update(over)
    return d


def fixture_record(**over) -> dict:
    kw = {"embedder": "v3-stub-embedder", "embedder_version": "0.0.1-fixture",
          "weights_sha256": WEIGHTS, "calibration": calibration(),
          "owner_decision": decision(), "fixture_only": True}
    kw.update(over)
    return IG.qualification_record(**kw)


def cand(frame: bytes) -> dict:
    """A Laura candidate whose stage receipt proves her three current references were sent."""
    return {"data": frame, "sha256": hashlib.sha256(frame).hexdigest(), "laura_present": True,
            "identity_evidence": {"conditioning": {
                "references": [{"sha256": h, "bytes": len(REFS[f])}
                               for f, h in canonical.CURRENT_REFERENCE_HASHES.items()],
                "proven": True}}}


def judges(*, a=None, b="default", embedder="default", record="default", allow=True):
    a = a or StubJudge("vision-a", "stub-model-a")
    b = StubJudge("vision-b", "stub-model-b") if b == "default" else b
    return CG.RealJudges(None, vision=a, second_vision=b,
                         embedder=StubEmbedder() if embedder == "default" else embedder,
                         qualification=fixture_record() if record == "default" else record,
                         allow_fixture=allow)


def ident(frame=MATCH_FRAME, **kw) -> dict:
    return judges(**kw).identity(cand(frame))


# ---------------------------------------------------------------------------------- PASS/FAIL

def test_canonical_match_reads_pass_labelled_fixture_only():
    assert all(REFS.values()), "canonical references must be readable by their sha256"
    got = ident()
    assert got["status"] == "PASS", got
    assert got["band"] == IG.BAND_PASS
    assert got["judges"] == ["vision-a:stub-model-a", "vision-b:stub-model-b"]
    assert got["biometric"]["status"] == "PASS" and got["biometric"]["similarity"] >= 0.95
    # labelled as not certification wherever it is recorded
    assert got["fixture_only"] is True and got["certification"] == IG.FIXTURE_LABEL
    assert "not identity certification" in IG.FIXTURE_LABEL.lower()
    assert got["why"].startswith(f"[{IG.CERT_FIXTURE}]")
    assert got["biometric"]["qualification"]["certification"] == IG.CERT_FIXTURE


def test_drifted_frame_reads_fail_with_the_identity_code():
    got = ident(DRIFT_FRAME)
    assert got["status"] == "FAIL" and got["band"] == IG.BAND_AUTO_REFUSE, got
    assert {"face", "eyes"} <= set(got["failed"])
    assert got["code"] == FC.IDENTITY_DRIFT == CG.FAILURE_CATEGORY["identity"]
    assert got["fixture_only"] is True        # a fixture FAIL is labelled too


def test_a_lookalike_both_judges_accept_still_fails_on_the_biometric_floor():
    got = ident(LOOKALIKE_FRAME)
    assert got["status"] == "FAIL", got
    assert got["failed"] == ["biometric"] and got["code"] == FC.IDENTITY_DRIFT
    assert "similar to Laura is NOT Laura" in got["why"]


def test_borderline_biometric_is_unknown_review():
    got = ident(BORDER_FRAME)
    assert got["status"] == "UNKNOWN" and got["band"] == IG.BAND_REVIEW, got
    assert got["biometric"]["status"] == "BORDERLINE"


# ---------------------------------------------------------------------- judge independence

def test_one_judge_only_is_unknown():
    got = ident(b=None)
    assert got["status"] == "UNKNOWN", got
    assert "missing_judge_pair" in got["why"]


def test_the_same_judge_twice_is_unknown():
    a = StubJudge("vision-a", "stub-model-a")
    assert ident(a=a, b=a)["status"] == "UNKNOWN"
    # two transports with one judge_id (same name, same model) are one judge
    twin = StubJudge("vision-a", "stub-model-a")
    got = ident(a=a, b=twin)
    assert got["status"] == "UNKNOWN" and got["judges"] == ["vision-a:stub-model-a"], got


def test_a_second_judge_that_does_not_answer_is_unknown():
    silent = StubJudge("vision-b", "stub-model-b", answers={})
    got = ident(b=silent)
    assert got["status"] == "UNKNOWN" and "unanswered" in got["why"], got
    unparsed = StubJudge("vision-b", "stub-model-b", answers={MATCH_FRAME: "not json"})
    assert ident(b=unparsed)["status"] == "UNKNOWN"


def test_disagreeing_judges():
    # one reads Laura, the other cannot tell on the face: not provably her -> UNKNOWN
    unsure = StubJudge("vision-b", "stub-model-b",
                       answers={MATCH_FRAME: reading({**ALL_SAME, "face": VJ.CANNOT_TELL})})
    got = ident(b=unsure)
    assert got["status"] == "UNKNOWN" and got["band"] == IG.BAND_REVIEW, got
    # one reads Laura, the other reads a different face: a clear mismatch -> FAIL
    differs = StubJudge("vision-b", "stub-model-b",
                        answers={MATCH_FRAME: reading(FACE_DIFFERENT)})
    got = ident(b=differs)
    assert got["status"] == "FAIL" and got["code"] == FC.IDENTITY_DRIFT, got


# -------------------------------------------------------------------- qualification refusals

def test_production_configuration_stays_unknown():
    assert IG.PRODUCTION_QUALIFICATIONS == ()
    assert IG.QUALIFIED_EMBEDDERS == {}
    assert VJ.SECOND_VISION_TRANSPORT is None and VJ.configured_second_transport() is None
    prod = CG.RealJudges(None, vision=StubJudge("vision-a", "stub-model-a"))
    assert prod.second_vision is None and prod.embedder is None and not prod.allow_fixture
    got = prod.identity(cand(MATCH_FRAME))
    assert got["status"] == "UNKNOWN" and got["biometric"]["status"] == IG.UNMEASURED, got
    # even with two judges, production (no embedder) never passes
    two = CG.RealJudges(None, vision=StubJudge("vision-a", "stub-model-a"),
                        second_vision=StubJudge("vision-b", "stub-model-b"))
    got = two.identity(cand(MATCH_FRAME))
    assert got["status"] == "UNKNOWN" and got["band"] == IG.BAND_REVIEW, got


def test_unqualified_embedder_is_unknown():
    got = ident(record=None)
    assert got["status"] == "UNKNOWN" and "no qualification record" in got["why"], got


def test_fixture_record_refused_in_production_config():
    got = ident(allow=False)
    assert got["status"] == "UNKNOWN", got
    assert "production never admits a fixture" in got["why"]
    assert got.get("fixture_only") is True          # still labelled
    os.environ["BRAMBLELOOP_PHASE"] = "production"
    try:
        got = ident(allow=True)
        assert got["status"] == "UNKNOWN" and "outside shadow" in got["why"], got
    finally:
        os.environ["BRAMBLELOOP_PHASE"] = "shadow"


def test_a_real_looking_record_is_refused_off_the_register():
    rec = fixture_record(fixture_only=False,
                         owner_decision=decision(decision_id="D-SOMEONE",
                                                 scope=IG.SCOPE_PRODUCTION))
    q = IG.validate_qualification(rec, embedder=StubEmbedder())
    assert not q["admitted"] and any("production register" in r for r in q["reasons"]), q
    assert ident(record=rec)["status"] == "UNKNOWN"


def test_generator_supplied_embeddings_are_never_used():
    name = "v3-test-injected"
    IG.QUALIFIED_EMBEDDERS[name] = {"match_at": 0.95, "refuse_below": 0.7}
    try:
        c = cand(MATCH_FRAME)
        c["identity_evidence"]["biometric"] = {"embedder": name, "reference": FACE_VEC,
                                               "frame": FACE_VEC}
        two = CG.RealJudges(None, vision=StubJudge("vision-a", "stub-model-a"),
                            second_vision=StubJudge("vision-b", "stub-model-b"))
        got = two.identity(c)
        assert got["status"] == "UNKNOWN", got
    finally:
        IG.QUALIFIED_EMBEDDERS.pop(name, None)


def _refused(rec, *, embedder=None, allow=True, needle=""):
    q = IG.validate_qualification(rec, embedder=embedder or StubEmbedder(),
                                  allow_fixture=allow)
    assert not q["admitted"] and q["spec"] is None, q
    assert not needle or any(needle in r for r in q["reasons"]), (needle, q["reasons"])
    assert ident(record=rec, embedder=embedder or StubEmbedder())["status"] == "UNKNOWN"


def test_record_with_a_wrong_hash_is_refused():
    rec = fixture_record()
    _refused({**rec, "record_sha256": "0" * 64}, needle="record_sha256")
    tampered = dict(rec, calibration=dict(rec["calibration"], match_at=0.5))
    _refused(tampered, needle="record_sha256")      # thresholds edited after the hash
    _refused(fixture_record(weights_sha256="not-a-hash"), needle="weights_sha256")


def test_record_with_a_missing_or_unapproved_decision_is_refused():
    _refused(fixture_record(owner_decision={}), needle="no owner decision")
    _refused(fixture_record(owner_decision=decision(decided_by="")), needle="no owner decision")
    _refused(fixture_record(owner_decision=decision(decision="pending")), needle="approved")
    _refused(fixture_record(owner_decision=decision(decided_at="soon")), needle="decided_at")
    _refused(fixture_record(owner_decision=decision(scope=IG.SCOPE_PRODUCTION)),
             needle="scoped fixture_only")


def test_record_with_bad_calibration_is_refused():
    _refused(fixture_record(calibration=calibration(match_at=0.6)), needle="out of order")
    _refused(fixture_record(calibration=calibration(evidence_sha256="")), needle="evidence")
    _refused(fixture_record(calibration=calibration(genuine_pairs=0)), needle="genuine_pairs")
    _refused(fixture_record(calibration=calibration(canonical_references=["a" * 64])),
             needle="current canonical references")
    _refused(fixture_record(calibration=calibration(reference_frames=["someone_else"])),
             needle="reference frame")
    rec = fixture_record()
    rec2 = {k: v for k, v in rec.items() if k != "fixture_only"}
    rec2["record_sha256"] = IG.record_sha256(rec2)
    _refused(rec2, needle="fixture_only")


def test_record_version_and_production_scope_are_checked():
    rec = {**fixture_record(), "version": "embedder-qualification/0"}
    rec["record_sha256"] = IG.record_sha256(rec)
    _refused(rec, needle="record version")
    real = fixture_record(fixture_only=False, owner_decision=decision(decision_id="D-X"))
    _refused(real, needle="not scoped to production")


def test_the_worst_reference_frame_counts():
    rec = fixture_record(calibration=calibration(
        reference_frames=["neutral_portrait", "torso_fit_reference"]))
    got = IG.measure_biometric(StubEmbedder(), rec, MATCH_FRAME, REFS, allow_fixture=True)
    assert got["status"] == "FAIL" and len(got["against"]) == 2, got
    assert ident(record=rec)["status"] == "FAIL"


def test_the_embedder_in_use_must_be_the_qualified_one():
    _refused(fixture_record(), embedder=StubEmbedder(version="0.0.2"), needle="not the qualified")
    _refused(fixture_record(), embedder=StubEmbedder(weights="f" * 64), needle="weights hash")
    got = ident(embedder=StubEmbedder(raises=True))
    assert got["status"] == "UNKNOWN" and "embedder unavailable" in got["why"], got


def test_tampered_reference_bytes_are_unmeasured():
    bad = dict(REFS, neutral_portrait=b"not her")
    got = IG.measure_biometric(StubEmbedder(), fixture_record(), MATCH_FRAME, bad,
                               allow_fixture=True)
    assert got["status"] == IG.UNMEASURED and "recorded sha256" in got["why"], got


# ----------------------------------------------------------------------------- canon intact

def test_laura_canonical_identity_unchanged():
    assert canonical.FACE_SHA256 == (
        "a42aeac72ba5733e42f55f9eb527218242c50610531ec9263ffb6f3e82519bc9")
    assert canonical.TORSO_SHA256 == (
        "afe6191fb4c68d0a9c61229fe822a1032ee7c54150597210888db25b0f9ef0db")
    assert canonical.FULL_LENGTH_SHA256 == (
        "f32bac686cba46c75e3ac193e72f2bcea4ba7ebc80355a102a4bed4bca3931e0")
    assert canonical.IDENTITY_ID == "laura-r2-a42aeac7"
    for frame, want in canonical.CURRENT_REFERENCE_HASHES.items():
        assert hashlib.sha256(REFS[frame]).hexdigest() == want, frame
    assert canonical.verify()["problems"] == []
    assert canonical.IDENTITY_RULE.startswith("An image depicting a woman similar to Laura")


def test_a_fixture_pass_is_unknown_in_every_gate_it_feeds():
    """Review VISUAL_STACK N4: the fixture PASS keeps its label on the check, but the export
    evidence and the publication gates count it UNKNOWN, never a bare PASS."""
    got = ident()
    assert got["status"] == "PASS" and got["fixture_only"] is True
    assert CG.gate_status(got) == "UNKNOWN"
    assert CG.gate_status({**got, "status": "FAIL"}) == "FAIL"
    assert CG.gate_status({k: v for k, v in got.items() if k != "fixture_only"}) == "PASS"
    ok = {"status": "PASS", "why": "fixture"}
    checks = {k: dict(ok) for k in ("binding", "product_truth", "quality", "role", "realism",
                                    "anatomy", "provenance", "body_proportions", "disclosure",
                                    "outfit", "outfit_distinctness", "outfit_consistency")}
    checks["identity"] = got
    ev = CG.exception_evidence(cand(MATCH_FRAME), checks, None, False,
                               other_publication_blockers=[])
    assert ev["checks"]["identity"] == "UNKNOWN", ev["checks"]
    assert ev["fixture_only_checks"] == ["identity"], ev


if __name__ == "__main__":
    fails = passes = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                passes += 1
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    print(f"\n{passes} passed, {fails} failed")
    sys.exit(1 if fails else 0)
