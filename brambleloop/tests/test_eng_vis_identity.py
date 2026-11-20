"""ENG-VIS-IDENTITY: a qualifiable identity method, a second independent judge, outfit claims
and durable identity records.

Deterministic stand-ins only (no network, no key, no spend): a stub embedder with fixed
vectors, simulated judge transports, and a scratch SQLite database that is reopened to stand
for a restart. The real SFace measurement is checked through its committed, content-hashed
evidence file (and re-run when the models are installed: BRAMBLELOOP_FACE_MODEL_DIR).

Laura's canonical references are read and verified by sha256, never written. Each gate also
has a source mutant (`_mutant`) that removes it; the test asserts the mutant is caught.
"""
import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import hashlib
import json
import math
import os
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ["BRAMBLELOOP_PHASE"] = "shadow"
os.environ.pop("OPENAI_API_KEY", None)

from brambleloop.visual import candidate_gates as CG  # noqa: E402
from brambleloop.visual import canonical, identity  # noqa: E402
from brambleloop.visual import identity_calibration as C  # noqa: E402
from brambleloop.visual import identity_gate as IG  # noqa: E402
from brambleloop.visual import identity_records as IR  # noqa: E402
from brambleloop.visual import outfits as O  # noqa: E402
from brambleloop.visual import vision_judges as VJ  # noqa: E402

REFS = VJ.canonical_reference_bytes()
REF_SET = set(REFS.values())
EVIDENCE = ROOT / "research/final_build/w6/identity_calibration/calibration_evidence.json"

ALL_SAME = {d: VJ.SAME for d in identity.DRIFT_DIMENSIONS}
FACE_DIFFERENT = {**ALL_SAME, "face": VJ.DIFFERENT}
FACE_UNSURE = {**ALL_SAME, "face": VJ.CANNOT_TELL}

DIM = 16


def _unit(v):
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v]


BASE = _unit([1.0] + [0.0] * (DIM - 1))


def _vec(seed: bytes, *, near: bool) -> list[float]:
    h = hashlib.sha256(seed).digest()
    noise = [(b - 128) / 128 for b in h[:DIM]]
    if near:      # genuine: the base plus small noise (cosine ~0.98)
        return _unit([BASE[i] + 0.12 * noise[i] for i in range(DIM)])
    # impostor: mostly orthogonal to the base (cosine ~0.2-0.4)
    return _unit([0.3 * BASE[i] + noise[i] * (1 if i else 0) for i in range(DIM)])


class StubEmbedder:
    """Fixed vectors: her references are the base; `laura:*` bytes are near it; anything else
    is an impostor. Same interface as `face_embedder.SFaceEmbedder` (embed/name/version)."""
    name, version = "stub-embedder", "0.0.1-test"
    weights_sha256 = hashlib.sha256(b"stub-embedder-weights").hexdigest()

    def embed(self, data: bytes):
        if data in REF_SET:
            return list(BASE)
        if data.startswith(b"noface"):
            raise ValueError("no face found")
        return _vec(data, near=data.startswith(b"laura:"))


def samples(n_gen: int, n_imp: int) -> list[dict]:
    out = []
    for i in range(n_gen):
        d = f"laura:{i}".encode()
        out.append({"id": f"g{i}", "label": C.GENUINE, "data": d,
                    "sha256": hashlib.sha256(d).hexdigest()})
    for i in range(n_imp):
        d = f"other:{i}".encode()
        out.append({"id": f"i{i}", "label": C.IMPOSTOR, "data": d,
                    "sha256": hashlib.sha256(d).hexdigest()})
    return out


def calibrate(n_gen=40, n_imp=320):
    return C.calibrate(StubEmbedder(), samples(n_gen, n_imp), REFS, with_augmentations=False)


PROD_DECISION = {"decision_id": "TEST-ONLY-ENG-VIS-IDENTITY", "decided_by": "test",
                 "decided_at": "2026-11-20T00:00:00Z", "decision": "approved",
                 "scope": IG.SCOPE_PRODUCTION}


class on_register:
    """Temporarily put a record on the production register (restored on exit)."""

    def __init__(self, *recs):
        self.recs = recs

    def __enter__(self):
        self.saved = IG.PRODUCTION_QUALIFICATIONS
        IG.PRODUCTION_QUALIFICATIONS = tuple(self.recs)

    def __exit__(self, *a):
        IG.PRODUCTION_QUALIFICATIONS = self.saved


# ---- judges and candidates ------------------------------------------------------------------

MATCH = b"laura:frame-match"
OTHER = b"other:frame-impostor"


class StubJudge:
    def __init__(self, name, model, answers=None):
        self.name, self.model = name, model
        self.answers = answers or {}
        self.calls = 0

    def read(self, prompt, images, *, system=None, max_tokens=300):
        self.calls += 1
        if "Image 4 is another photograph" in prompt:
            cand, refs = images[3], images[:3]
        else:
            cand, refs = images[0], images[1:]
        if set(refs) != REF_SET:
            return {"answered": False, "why": "references are not the canonical set"}
        got = self.answers.get(cand, ALL_SAME)
        if got is None:
            return {"answered": False, "why": "unanswered"}
        return {"answered": True, "reading": {**got, "people_in_photograph": 1},
                "model": self.model}


def cand(frame: bytes, frames=None) -> dict:
    frames = frames or list(canonical.CURRENT_REFERENCE_HASHES)
    return {"data": frame, "sha256": hashlib.sha256(frame).hexdigest(), "laura_present": True,
            "identity_evidence": {"conditioning": {
                "references": [{"sha256": canonical.CURRENT_REFERENCE_HASHES[f],
                                "bytes": len(REFS[f])} for f in frames],
                "proven": True}}}


def qualified_record():
    ev = calibrate()
    assert ev["production_ready"], ev["not_ready_reasons"]
    return C.qualification(ev, owner_decision=PROD_DECISION)


def ident(frame=MATCH, *, a=None, b="default", record="qualified", frames=None):
    a = a or StubJudge("vision-a", "model-a")
    b = StubJudge("vision-b", "model-b") if b == "default" else b
    rec = qualified_record() if record == "qualified" else record
    j = CG.RealJudges(None, vision=a, second_vision=b, embedder=StubEmbedder(),
                      qualification=rec)
    if record == "qualified":
        with on_register(rec):
            return j.identity(cand(frame, frames))
    return j.identity(cand(frame, frames))


# ---- mutation helper ------------------------------------------------------------------------

def _mutant(module, old: str, new: str):
    """A copy of `module` with one source edit, loaded under the same package."""
    src = Path(module.__file__).read_text()
    assert src.count(old) == 1, f"mutation anchor not unique in {module.__name__}: {old!r}"
    m = types.ModuleType(module.__name__ + "_mutant")
    m.__package__ = module.__package__
    m.__file__ = module.__file__
    exec(compile(src.replace(old, new), module.__file__, "exec"), m.__dict__)
    return m


def _mutant_function(module, fname: str, old: str, new: str):
    """One function of `module` with one source edit (for modules that declare ORM tables)."""
    import inspect
    import textwrap

    src = textwrap.dedent(inspect.getsource(getattr(module, fname)))
    assert src.count(old) == 1, f"mutation anchor not unique in {fname}: {old!r}"
    ns = dict(module.__dict__)
    exec(compile(src.replace(old, new), module.__file__, "exec"), ns)
    return ns[fname]


# ============================================================ 1. calibration and qualification

def test_calibration_derives_thresholds_and_rates_from_measurements():
    ev = calibrate()
    assert ev["genuine_pairs"] == 40 and ev["impostor_pairs"] == 320
    assert ev["match_at"] > ev["impostor_max"]                       # above every impostor
    assert ev["refuse_below"] < ev["match_at"]
    assert ev["far"] == 0.0 and ev["frr"] == 0.0
    assert ev["far_upper_95"] <= C.MAX_FAR_UPPER_95
    assert ev["production_ready"] and C.verify_evidence(ev)
    assert ev["canonical_references"] == canonical.CURRENT_REFERENCE_HASHES


def test_small_calibration_is_not_production_ready_whatever_it_scored():
    ev = calibrate(12, 10)
    assert ev["far"] == 0.0 and ev["frr"] == 0.0                     # perfect, but tiny
    assert not ev["production_ready"]
    assert ev["far_upper_95"] > 0.2                                   # 0/10 bounds at ~26%
    assert any("impostor faces" in r for r in ev["not_ready_reasons"])


def test_clopper_pearson_upper_bound():
    assert abs(C.binomial_upper_95(0, 300) - 0.00994) < 1e-4
    assert abs(C.binomial_upper_95(0, 10) - 0.2589) < 1e-3
    assert 0.0 < C.binomial_upper_95(1, 100) < 0.05
    assert C.binomial_upper_95(0, 0) == 1.0


def test_qualified_record_validates_only_on_the_register():
    rec = qualified_record()
    q = IG.validate_qualification(rec, embedder=StubEmbedder())
    assert not q["admitted"] and any("production register" in r for r in q["reasons"]), q
    with on_register(rec):
        q = IG.validate_qualification(rec, embedder=StubEmbedder())
        assert q["admitted"] and q["certification"] == IG.CERT_QUALIFIED, q


def test_production_record_with_thin_calibration_is_refused_even_on_the_register():
    ev = calibrate(12, 10)
    rec = C.qualification(ev, owner_decision=PROD_DECISION)
    with on_register(rec):
        q = IG.validate_qualification(rec, embedder=StubEmbedder())
    assert not q["admitted"]
    assert any(">= 300 impostor" in r for r in q["reasons"]), q["reasons"]
    assert any("production_ready" in r for r in q["reasons"]), q["reasons"]


def test_tampered_evidence_cannot_build_a_record():
    ev = calibrate()
    try:
        C.qualification({**ev, "far": 0.5}, owner_decision=PROD_DECISION)
    except ValueError as exc:
        assert "evidence_sha256" in str(exc)
    else:
        raise AssertionError("tampered evidence built a record")


def test_committed_sface_evidence_is_intact_and_honestly_not_ready():
    doc = json.loads(EVIDENCE.read_text())
    ev = doc["evidence"]
    assert C.verify_evidence(ev), "calibration_evidence.json does not match its hash"
    assert ev["embedder"] == "sface-yunet-onnx"
    from brambleloop.visual import face_embedder as FE

    assert ev["weights_sha256"] == FE.weights_sha256()
    assert ev["canonical_references"] == canonical.CURRENT_REFERENCE_HASHES
    assert ev["impostor_max"] < ev["match_at"] <= ev["genuine_min"], ev
    assert ev["far"] == 0.0 and ev["frr"] == 0.0
    assert not ev["production_ready"] and ev["impostor_pairs"] < C.MIN_IMPOSTOR_PRODUCTION
    # no labelled sample is a real person's photograph: every licence says generated/owner
    m = json.loads((EVIDENCE.parent / "calibration_set.json").read_text())
    assert all("no real person" in s["licence"] or "no third-party person" in s["licence"]
               for s in m["samples"])


def test_real_sface_calibration_reproduces_when_installed():
    from brambleloop.visual import face_embedder as FE

    d = os.environ.get("BRAMBLELOOP_FACE_MODEL_DIR")
    emb, why = FE.try_load(d) if d else (None, "BRAMBLELOOP_FACE_MODEL_DIR not set")
    if emb is None:
        # Not installed here: the refusal itself is the checked behaviour (UNMEASURED).
        floor = IG.production_floor(d or "/nonexistent")
        assert floor["embedder"] is None and floor["qualification"] is None and floor["why"]
        return
    m = EVIDENCE.parent / "calibration_set.json"
    ev = C.calibrate(emb, C.load_set(m, ROOT), REFS)
    want = json.loads(EVIDENCE.read_text())["evidence"]
    for k in ("match_at", "refuse_below", "genuine_pairs", "impostor_pairs", "far", "frr"):
        assert ev[k] == want[k], (k, ev[k], want[k])


def test_face_model_refused_unless_pinned_sha():
    from brambleloop.visual import face_embedder as FE

    d = Path(os.environ.get("TMPDIR", "/tmp")) / "fake-face-models"
    d.mkdir(exist_ok=True)
    for m in FE.MODELS.values():
        (d / m["file"]).write_bytes(b"not the model")
    emb, why = FE.try_load(d)
    assert emb is None and "is not the pinned" in why, why


# ============================================================ 2. PASS needs qualification and two agreeing judges

def test_pass_only_when_qualified_and_both_judges_agree():
    got = ident()
    assert got["status"] == "PASS" and got["verdict"] == "PASS", got
    assert got["judge_agreement"]["state"] == "agree"
    assert got["biometric"]["qualification"]["certification"] == IG.CERT_QUALIFIED
    assert CG.gate_status(got) == "PASS"


def test_one_judge_holds():
    got = ident(b=None)
    assert got["verdict"] == "HOLD" and got["status"] == "UNKNOWN", got
    assert CG.gate_status(got) == "UNKNOWN"


def test_judges_disagreeing_holds_with_a_reason():
    unsure = StubJudge("vision-b", "model-b", answers={MATCH: FACE_UNSURE})
    got = ident(b=unsure)
    assert got["verdict"] == "HOLD", got
    assert got["judge_agreement"]["state"] == "disagree"
    assert "judges disagree" in got["why"] and "judges disagree" in " ".join(
        got["hold_reasons"])


def test_a_judge_reading_drift_refuses():
    differs = StubJudge("vision-b", "model-b", answers={MATCH: FACE_DIFFERENT})
    got = ident(b=differs)
    assert got["verdict"] == "REFUSE" and got["status"] == "FAIL", got


def test_the_same_judge_twice_is_one_judge():
    a = StubJudge("vision-a", "model-a")
    got = ident(a=a, b=StubJudge("vision-a", "model-a"))
    assert got["verdict"] == "HOLD", got


def test_impostor_frame_is_refused_by_the_biometric_floor():
    got = ident(OTHER)
    assert got["verdict"] == "REFUSE" and got["biometric"]["status"] == "FAIL", got


def test_second_transport_is_a_different_provider_and_is_off_without_a_key():
    os.environ.pop("OPENAI_API_KEY", None)
    assert VJ.configured_second_transport() is None
    os.environ["OPENAI_API_KEY"] = "sk-test-not-a-key"
    try:
        t = VJ.configured_second_transport()
        assert t is not None and t.name == "image_vision_openai"
        assert t.provider.model == VJ.SECOND_JUDGE_MODEL
        from brambleloop.visual.fidelity import GatewayVisionJudge

        assert isinstance(t, GatewayVisionJudge)           # the same reservation path
        first = GatewayVisionJudge(None)
        assert VJ.transports_independent(first, t)
        # its gate is closed without a database: unanswered, so identity HOLDs, nothing sent
        assert t.read("x", [b"img"])["answered"] is False
    finally:
        os.environ.pop("OPENAI_API_KEY", None)


# ============================================================ 3. UNKNOWN is HOLD

def test_unqualified_method_is_hold_never_pass():
    got = ident(record=None)
    assert got["verdict"] == "HOLD" and got["biometric"]["status"] == IG.UNMEASURED, got


def test_legacy_embedder_table_pass_is_not_a_consumer_pass():
    name = "eng-vis-legacy"
    IG.QUALIFIED_EMBEDDERS[name] = {"match_at": 0.9, "refuse_below": 0.5}
    try:
        ev = {"conditioning": cand(MATCH)["identity_evidence"]["conditioning"],
              "judges": [{"judge": "a", "scored": {d: identity.MATCH
                                                    for d in identity.DRIFT_DIMENSIONS}},
                         {"judge": "b", "scored": {d: identity.MATCH
                                                    for d in identity.DRIFT_DIMENSIONS}}],
              "biometric": {"embedder": name, "reference": [1, 0], "frame": [1, 0]}}
        g = IG.assess(ev)
        assert g["status"] == "PASS" and g["verdict"] == "HOLD", g
        assert CG.gate_status(g) == "UNKNOWN"
    finally:
        IG.QUALIFIED_EMBEDDERS.pop(name, None)


def test_production_wiring_without_models_is_hold():
    j = CG.RealJudges(None, vision=StubJudge("vision-a", "model-a"),
                      second_vision=StubJudge("vision-b", "model-b"))
    # the model may or may not be installed here; no record qualifies it either way
    assert j.qualification is None
    got = j.identity(cand(MATCH))
    assert got["verdict"] == "HOLD" and got["biometric"]["status"] == IG.UNMEASURED, got


def test_record_without_a_verdict_is_hold():
    assert IR._verdict({"status": "PASS"}) == "HOLD"
    assert IR._verdict({"status": "UNKNOWN"}) == "HOLD"
    assert IR._verdict({"status": "FAIL"}) == "REFUSE"


# ============================================================ 4. SHA mismatch refuses

def test_tampered_reference_refuses_calibration():
    bad = dict(REFS, torso_fit_reference=REFS["torso_fit_reference"] + b"x")
    try:
        C.calibrate(StubEmbedder(), samples(3, 3), bad, with_augmentations=False)
    except C.ReferenceMismatch as exc:
        assert "torso_fit_reference" in str(exc)
    else:
        raise AssertionError("calibration ran against a reference that is not hers")


def test_tampered_reference_makes_the_floor_unmeasured():
    rec = qualified_record()
    bad = dict(REFS, full_length_standing=b"not her")
    with on_register(rec):
        bio = IG.measure_biometric(StubEmbedder(), rec, MATCH, bad)
    assert bio["status"] == IG.UNMEASURED and "sha256" in bio["why"], bio


def test_conditioning_on_a_foreign_reference_is_invalid():
    c = cand(MATCH)
    c["identity_evidence"]["conditioning"]["references"].append(
        {"sha256": hashlib.sha256(b"someone else").hexdigest(), "bytes": 10})
    a, b = StubJudge("vision-a", "model-a"), StubJudge("vision-b", "model-b")
    rec = qualified_record()
    with on_register(rec):
        got = CG.RealJudges(None, vision=a, second_vision=b, embedder=StubEmbedder(),
                            qualification=rec).identity(c)
    assert got["verdict"] != "PASS" and got["validity"] == IG.INVALID, got


def test_all_three_references_are_mandatory():
    got = ident(frames=["neutral_portrait", "torso_fit_reference"])
    assert got["verdict"] == "HOLD" and got["validity"] == IG.INVALID, got
    assert "full_length_standing" in got["why"]


def test_sample_with_wrong_sha_is_refused():
    s = samples(1, 1)
    s[0]["sha256"] = "0" * 64
    try:
        C.calibrate(StubEmbedder(), s, REFS, with_augmentations=False)
    except C.ReferenceMismatch:
        pass
    else:
        raise AssertionError("a sample with the wrong sha256 was measured")


# ============================================================ 5. outfits and records survive a restart

def _db(path):
    from brambleloop.core.db import Database

    db = Database("sqlite:///" + str(path), scratch=True)
    db.create_all()
    return db


def _outfit(db, oid, top, lower, shoes):
    O.register(db, outfit_id=oid, garments={"top_or_dress": top, "lower": lower,
                                            "shoes": shoes})
    O.approve(db, oid)


def test_outfit_claims_are_unique_idempotent_and_survive_a_restart():
    p = Path(os.environ.get("TMPDIR", "/tmp")) / "outfits.db"
    db = _db(p)
    _outfit(db, "outfit-rust-cardigan", "rust wool cardigan", "dark denim jeans",
            "tan leather ankle boots")
    _outfit(db, "outfit-navy-dress", "navy linen dress", "", "white canvas sneakers")
    _outfit(db, "outfit-rust-cardigan-2", "rust wool cardigan", "dark denim jeans",
            "tan suede ankle boots")         # near-duplicate of the first
    a1 = O.claim(db, "listing-a")
    a2 = O.claim(db, "listing-a")
    assert a1["status"] == "PASS" and a1["outfit_id"] == a2["outfit_id"], (a1, a2)
    assert a2["claimed"] is False                                      # idempotent
    b = O.claim(db, "listing-b")
    assert b["status"] == "PASS" and b["outfit_id"] != a1["outfit_id"], b
    db.engine.dispose()
    again = _db(p)                                                    # a restart
    assert O.claim(again, "listing-a")["outfit_id"] == a1["outfit_id"]
    assert O.claim(again, "listing-b")["outfit_id"] == b["outfit_id"]
    c = O.claim(again, "listing-c")
    # the only free outfit is a near-duplicate of listing-a's: never reused across listings
    assert c["status"] == "UNKNOWN", c
    assert any(s["why"] == "WARDROBE_REPETITION" for s in c["skipped"]), c
    # and a different listing cannot take a claimed outfit through reserve either
    assert O.reserve(again, a1["outfit_id"], "listing-c")["status"] == "FAIL"


def test_outfit_reference_check_is_slot_by_slot():
    from brambleloop.visual import wardrobe as W

    same = {s: VJ.SAME for s in W.SLOTS}
    assert VJ.compare_outfit_reference(same)["status"] == "PASS"
    assert VJ.compare_outfit_reference({**same, "shoes": VJ.DIFFERENT})["status"] == "FAIL"
    assert VJ.compare_outfit_reference({**same, "top_or_dress": VJ.CANNOT_TELL})["status"] \
        == "UNKNOWN"
    assert "reserved" not in VJ.outfit_reference_prompt().lower()       # blind


def test_identity_records_persist_and_are_idempotent():
    p = Path(os.environ.get("TMPDIR", "/tmp")) / "records.db"
    db = _db(p)
    got = ident()
    sha = hashlib.sha256(MATCH).hexdigest()
    r1 = IR.record(db, image_sha256=sha, listing="listing-a", identity=got,
                   outfit={"outfit_id": "outfit-x"})
    r2 = IR.record(db, image_sha256=sha, listing="listing-a", identity=got,
                   outfit={"outfit_id": "outfit-x"})
    assert r1["created"] and not r2["created"] and r1["id"] == r2["id"]
    assert r1["verdict"] == "PASS"
    assert {r["canonical_frame"] for r in r1["references"]} == set(
        canonical.CURRENT_REFERENCE_HASHES)
    assert all(r["canonical"] for r in r1["references"])
    assert r1["method"]["certification"] == IG.CERT_QUALIFIED
    assert r1["method"]["embedder"] == "stub-embedder"
    assert [j["judge"] for j in r1["judges"]] == ["vision-a:model-a", "vision-b:model-b"]
    held = ident(b=None)
    r3 = IR.record(db, image_sha256=sha, listing="listing-a", identity=held)
    assert r3["created"] and r3["verdict"] == "HOLD"
    db.engine.dispose()
    again = _db(p)                                                    # a restart
    h = IR.history(again, sha)
    assert [r["verdict"] for r in h] == ["PASS", "HOLD"]
    assert IR.latest(again, sha)["verdict"] == "HOLD"


def test_candidate_gate_writes_the_identity_record():
    p = Path(os.environ.get("TMPDIR", "/tmp")) / "gate.db"
    db = _db(p)
    checks = {"identity": ident(b=None), "outfit": {"status": "PASS"},
              "outfit_consistency": {"status": "UNKNOWN"},
              "outfit_distinctness": {"status": "PASS"}}
    sha = hashlib.sha256(MATCH).hexdigest()
    out = CG._identity_record(db, sha, "listing-a", {"slug": "s", "outfit_id": "o"}, checks)
    assert out["status"] == "PASS" and out["identity_verdict"] == "HOLD", out
    assert IR.latest(db, sha)["outfit"]["consistency"] == "UNKNOWN"
    assert CG._identity_record(None, sha, "l", {}, checks)["status"] == "UNKNOWN"


# ============================================================ 6. mutants: each gate, removed, is caught

def test_mutant_three_reference_rule_is_caught():
    m = _mutant(IG, "        if absent:\n", "        if False:\n")
    ev = {"conditioning": {"references": [{"sha256": canonical.FACE_SHA256, "bytes": 1}],
                           "proven": True}}
    assert IG.trial_validity(ev)["validity"] == IG.INVALID
    assert not any("all three" in r for r in m.trial_validity(ev)["reasons"])


def test_mutant_unqualified_pass_is_caught():
    m = _mutant(IG, '    elif g["status"] == "PASS" and not hold:',
                '    elif g["status"] == "PASS":')
    name = "eng-vis-mutant"
    for mod in (IG, m):
        mod.QUALIFIED_EMBEDDERS[name] = {"match_at": 0.9, "refuse_below": 0.5}
    try:
        ev = {"conditioning": cand(MATCH)["identity_evidence"]["conditioning"],
              "judges": [{"judge": j, "scored": {d: identity.MATCH
                                                  for d in identity.DRIFT_DIMENSIONS}}
                         for j in ("a", "b")],
              "biometric": {"embedder": name, "reference": [1, 0], "frame": [1, 0]}}
        assert IG.assess(ev)["verdict"] == "HOLD"
        assert m.assess(ev)["verdict"] == "PASS"            # the mutant would have passed it
    finally:
        IG.QUALIFIED_EMBEDDERS.pop(name, None)


def test_mutant_production_floors_are_caught():
    m = _mutant(IG, '    if rec.get("fixture_only") is False:\n        refused += '
                    'production_calibration_refusals(cal)\n', '')
    rec = C.qualification(calibrate(12, 10), owner_decision=PROD_DECISION)
    with on_register(rec):
        assert not IG.validate_qualification(rec, embedder=StubEmbedder())["admitted"]
    m.PRODUCTION_QUALIFICATIONS = (rec,)
    assert m.validate_qualification(rec, embedder=StubEmbedder())["admitted"]


def test_mutant_reference_sha_check_is_caught():
    m = _mutant(C, "        if got != want:\n", "        if False:\n")
    bad = dict(REFS, neutral_portrait=b"someone else")
    try:
        C.verified_references(bad)
        raise AssertionError("the real module accepted a tampered reference")
    except C.ReferenceMismatch:
        pass
    m.verified_references(bad)                                # the mutant accepts it


def test_mutant_outfit_distinctness_in_claim_is_caught():
    m = _mutant(O, "            if (row.signature and twin is not None) or near is not None:",
                "            if False:")
    p = Path(os.environ.get("TMPDIR", "/tmp")) / "mutant-outfits.db"
    db = _db(p)
    _outfit(db, "outfit-green-top", "green cotton t-shirt", "black jeans", "white sneakers")
    _outfit(db, "outfit-green-top-2", "green cotton t-shirt", "black jeans",
            "white canvas sneakers")
    assert O.claim(db, "l1")["status"] == "PASS"
    assert O.claim(db, "l2")["status"] == "UNKNOWN"          # real: near-duplicate refused
    assert m.claim(db, "l2")["status"] == "PASS"             # mutant: reuses the outfit


def test_mutant_record_default_verdict_is_caught():
    mv = _mutant_function(IR, "_verdict", 'else "HOLD"', 'else "PASS"')
    assert IR._verdict({"status": "UNKNOWN"}) == "HOLD"
    assert mv({"status": "UNKNOWN"}) == "PASS"


def test_mutant_outfit_reference_difference_is_caught():
    from brambleloop.visual import wardrobe as W

    m = _mutant(VJ, "    if diff:\n        return _c(\"outfit_reference\", FAIL",
                "    if False:\n        return _c(\"outfit_reference\", FAIL")
    r = {**{s: VJ.SAME for s in W.SLOTS}, "lower": VJ.DIFFERENT}
    assert VJ.compare_outfit_reference(r)["status"] == "FAIL"
    assert m.compare_outfit_reference(r)["status"] == "PASS"


def test_mutant_gate_status_verdict_rule_is_caught():
    m = _mutant(CG, '    if st == PASS and "verdict" in (check or {}) and check.get("verdict") '
                    '!= PASS:\n        return UNKNOWN\n', '')
    held = {"status": "PASS", "verdict": "HOLD"}
    assert CG.gate_status(held) == "UNKNOWN"
    assert m.gate_status(held) == "PASS"


def test_canonical_references_untouched():
    assert {f: hashlib.sha256(b).hexdigest() for f, b in REFS.items()} == \
        canonical.CURRENT_REFERENCE_HASHES
    assert canonical.IDENTITY_ID == "laura-r2-a42aeac7"


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
