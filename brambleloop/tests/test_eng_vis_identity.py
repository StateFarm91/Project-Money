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


def calibrate(n_gen=40, n_imp=460):
    # F2: the floors apply to the HELD-OUT subset (5/6 of genuine, 2/3 of impostors), so
    # 40 genuine -> 33 held out and 460 impostors -> 306 held out.
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
    assert ev["total_genuine"] == 40 and ev["total_impostor"] == 460
    assert ev["calibration_genuine"] == 7 and ev["genuine_pairs"] == 33        # held out
    assert ev["calibration_impostor"] == 154 and ev["impostor_pairs"] == 306   # held out
    assert ev["evaluation"] == C.HELD_OUT and C.audit_split(ev) == []
    assert ev["match_at"] > ev["calibration_impostor_max"]      # above every calibration impostor
    assert ev["refuse_below"] < ev["match_at"]
    assert ev["far"] == 0.0 and ev["frr"] == 0.0
    assert ev["far_upper_95"] <= C.MAX_FAR_UPPER_95
    assert ev["production_ready"] and C.verify_evidence(ev)
    assert ev["canonical_references"] == canonical.CURRENT_REFERENCE_HASHES


def test_small_calibration_is_not_production_ready_whatever_it_scored():
    ev = calibrate(12, 10)
    assert ev["far"] == 0.0 and ev["frr"] == 0.0                     # perfect, but tiny
    assert not ev["production_ready"]
    assert ev["impostor_pairs"] == 6 and ev["far_upper_95"] > 0.3    # 0/6 held out: ~39%
    assert any("held-out impostor faces" in r for r in ev["not_ready_reasons"])


def test_held_out_split_is_disjoint_deterministic_and_keeps_augmentations_together():
    ev = calibrate()
    sp = ev["split"]
    assert not set(sp["calibration_units"]) & set(sp["held_out_units"])
    assert len(sp["calibration_units"]) + len(sp["held_out_units"]) == 500
    again = calibrate()
    assert again["split"] == sp and again["evidence_sha256"] == ev["evidence_sha256"]
    # thresholds are set only by calibration rows: moving a held-out impostor's score above
    # match_at raises FAR, it does not move match_at
    rows = [dict(r) for r in ev["rows"]]
    i = next(k for k, r in enumerate(rows) if r["label"] == C.IMPOSTOR
             and r["split"] == C.HELD_OUT)
    rows[i]["score"] = 0.999
    ev2 = C.summarise(rows, [], StubEmbedder())
    assert ev2["match_at"] == ev["match_at"] and ev2["false_accepts"] == 1, ev2["far"]
    # a genuine image and its augmentations always land in the same subset
    aug = C.summarise([{"id": "g1", "label": C.GENUINE, "sha256": "a", "score": .9,
                        "derived": False}] +
                      [{"id": f"g1~{n}", "label": C.GENUINE, "sha256": "a", "score": .9,
                        "derived": True} for n in C.AUGMENTATIONS] +
                      [{"id": f"g{k}", "label": C.GENUINE, "sha256": str(k), "score": .9,
                        "derived": False} for k in range(2, 9)] +
                      [{"id": f"i{k}", "label": C.IMPOSTOR, "sha256": str(k), "score": .2,
                        "derived": False} for k in range(9)], [], StubEmbedder())
    assert len({r["split"] for r in aug["rows"] if r["id"].startswith("g1")}) == 1


def test_qualification_refuses_in_sample_evidence():
    ev = calibrate()
    assert ev["production_ready"]
    # 1. evidence from the old in-sample harness (version /1): refused
    old = {**ev, "version": "identity-calibration/1"}
    old["evidence_sha256"] = C.evidence_sha256(old)
    # 2. in-sample evidence re-labelled as held-out: every row "held_out", thresholds and FAR
    #    computed over the very impostors that set them, hash recomputed so it verifies
    rows = [{**r, "split": C.HELD_OUT} for r in ev["rows"]]
    imp = [r["score"] for r in rows if r["label"] == C.IMPOSTOR]
    forged = {**ev, "rows": rows, "impostor_pairs": len(imp), "far": 0.0,
              "match_at": C._ceil2(max(imp) + C.MARGIN_ACCEPT),
              "split": {**ev["split"], "calibration_units": [],
                        "held_out_units": sorted(C._unit(r) for r in rows)}}
    forged["evidence_sha256"] = C.evidence_sha256(forged)
    for bad in (old, forged):
        assert C.verify_evidence(bad)
        try:
            C.qualification(bad, owner_decision=PROD_DECISION)
        except C.InSampleEvidence as exc:
            assert "held-out" in str(exc) or "reproduce" in str(exc), exc
        else:
            raise AssertionError("in-sample evidence built a qualification record")
    # 3. a hand-built record that omits the held-out evaluation is refused by the gate too
    rec = C.qualification(ev, owner_decision=PROD_DECISION)
    cal = {k: v for k, v in rec["calibration"].items() if k != "evaluation"}
    hand = IG.qualification_record(embedder=rec["embedder"],
                                   embedder_version=rec["embedder_version"],
                                   weights_sha256=rec["weights_sha256"], calibration=cal,
                                   owner_decision=PROD_DECISION, fixture_only=False)
    with on_register(hand):
        q = IG.validate_qualification(hand, embedder=StubEmbedder())
    assert not q["admitted"] and any("in-sample" in r for r in q["reasons"]), q["reasons"]


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
    # F2: measured held-out. Thresholds come from the calibration subset only; the honest
    # held-out reading of this tiny set is that look-alikes DO cross match_at (FAR 2/6).
    assert ev["version"] == C.CALIBRATION_VERSION and ev["evaluation"] == C.HELD_OUT
    assert C.audit_split(ev) == [], C.audit_split(ev)
    assert ev["calibration_impostor_max"] < ev["match_at"] <= ev["genuine_min"], ev
    assert ev["false_accepts"] == 2 and ev["impostor_pairs"] == 6 and ev["frr"] == 0.0
    assert not ev["production_ready"] and ev["impostor_pairs"] < C.MIN_IMPOSTOR_PRODUCTION
    try:
        C.qualification(ev, owner_decision=PROD_DECISION)
    except C.InSampleEvidence:
        raise AssertionError("held-out evidence was refused as in-sample")
    rec = C.qualification(ev, owner_decision=PROD_DECISION)
    with on_register(rec):                    # not production-ready: refused even on register
        assert not IG.validate_qualification(rec)["admitted"]
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
    for k in ("match_at", "refuse_below", "genuine_pairs", "impostor_pairs", "far", "frr",
              "split", "evidence_sha256"):
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


def test_vision_judge_reserves_the_providers_own_image_figure_never_less_than_the_gate():
    """F4: an OpenAI identity read (4 images) is reserved at gpt-4.1's own per-image figure
    plus system text -- exactly the paid gate's estimate -- not at Anthropic's 6,000."""
    from brambleloop.gateway import anthropic as A, openai_chat as OC, providers as gw
    from brambleloop.visual import fidelity as F, inspect as I

    seen = {}

    class Resp:
        input_tokens, output_tokens, text = 3300, 200, "{}"

    class Prov:
        model = VJ.SECOND_JUDGE_MODEL
        cost_per_1k_input_cad = cost_per_1k_output_cad = 0.0

        def see(self, system, prompt, paths, *, max_tokens):
            seen["gate"] = gw.input_tokens(self.model, system=system, user=prompt,
                                           images=len(paths))
            return Resp()

    class Open(F.GatewayVisionJudge):
        def gate_open(self):
            return True

    saved = (gw.check_budget, gw.release_reservation, I._bill)
    gw.check_budget = lambda db, **kw: (seen.update(res=kw["input_tokens"]) or
                                        {"estimate_cad": 0.0, "reservation_id": None})
    gw.release_reservation = lambda *a, **k: None
    I._bill = lambda *a, **k: None
    try:
        prompt = "Task: identity_morphology\n" + VJ.person_prompt("photo_first")
        got = Open(None, provider=Prov()).read(prompt, [b"a", b"b", b"c", b"d"],
                                               system=VJ.SYSTEM, max_tokens=400)
    finally:
        gw.check_budget, gw.release_reservation, I._bill = saved
    assert got["answered"], got
    assert seen["res"] == seen["gate"], seen                    # never below the gate
    assert seen["res"] >= 4 * 1445                               # gpt-4.1 worst case/image
    assert seen["res"] < len(prompt) // 4 + 4 * A.IMAGE_TOKENS_ESTIMATE    # no 4x
    cad = OC.estimate_cad(Prov.model, input_tokens=seen["res"], output_tokens=400)
    assert 0.02 < cad < 0.04, cad                                # was ~CA$0.091


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
        # F5: independence is enforced by distinct judge ids (`person_readings` counts the
        # same id twice as one reading); the unused transports_independent helper is gone.
        assert VJ.judge_id(first) != VJ.judge_id(t)
        assert not hasattr(VJ, "transports_independent")
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


def _held(db, listing):
    from sqlalchemy import select

    from brambleloop.visual.image_records import LauraOutfit

    with db.session() as s:
        return sorted(r.outfit_id for r in s.scalars(select(LauraOutfit).where(
            LauraOutfit.listing == listing, LauraOutfit.approval_state == "approved")))


class interleave:
    """Run `other()` inside claim(), after it has read the free list and before its
    compare-and-set UPDATE: the window two workers race in (F3)."""

    def __init__(self, other):
        self.other, self.done = other, False

    def __enter__(self):
        self.saved = O._too_similar

        def hooked(s, row, listing):
            if not self.done:
                self.done = True
                self.other()
            return self.saved(s, row, listing)

        O._too_similar = hooked

    def __exit__(self, *a):
        O._too_similar = self.saved


def _race_db(name):
    db = _db(Path(os.environ.get("TMPDIR", "/tmp")) / name)
    _outfit(db, "outfit-a-sage", "sage cotton jumper", "grey wool trousers", "black loafers")
    _outfit(db, "outfit-b-plum", "plum silk blouse", "cream midi skirt", "brown mary janes")
    _outfit(db, "outfit-c-teal", "teal knit vest", "white wide-leg jeans", "red sneakers")
    return db


def test_interleaved_claim_whose_loser_already_has_uses_leaves_exactly_one_outfit():
    db = _race_db("race1.db")

    def other_worker():   # reserves B for the same listing and generates a frame in it
        got = O.check_use(db, "outfit-b-plum", listing="L", product="p", image_sha256="f" * 64)
        assert got["status"] == "PASS", got

    with interleave(other_worker):
        got = O.claim(db, "L")      # took A by compare-and-set, after B reached an image
    assert _held(db, "L") == ["outfit-b-plum"], _held(db, "L")
    assert got["status"] == "PASS" and got["outfit_id"] == "outfit-b-plum", got
    assert got["claimed"] is False
    assert got["race"] == [{"outfit_id": "outfit-a-sage", "action": "released", "uses": 0}]
    # A is free again for another listing; B stays B's
    assert O.claim(db, "M")["outfit_id"] == "outfit-a-sage"
    assert O.reserved_for(db, "L")["outfit_id"] == "outfit-b-plum"


def test_interleaved_claims_where_both_outfits_have_uses_retire_the_later_one():
    db = _race_db("race2.db")
    O.check_use(db, "outfit-b-plum", listing="L", product="p", image_sha256="1" * 64)
    from brambleloop.visual.image_records import LauraOutfit  # noqa: F401
    # simulate the worst case: A was reserved for L by a racing claim and also reached images
    with db.session() as s:
        a = O._row(s, "outfit-a-sage")
        a.listing, a.reserved_at = "L", O._now()
        a.uses = [{"listing": "L", "product": "p", "image_sha256": "2" * 64,
                   "at": "2099-01-01T00:00:00+00:00"}]          # its first use is later
    view, resolved = O.settle(db, "L")
    assert view["outfit_id"] == "outfit-b-plum" and _held(db, "L") == ["outfit-b-plum"]
    assert resolved[0]["outfit_id"] == "outfit-a-sage" and resolved[0]["action"] == "retired"
    # the retired loser is never handed to another listing
    assert O.claim(db, "M")["outfit_id"] == "outfit-c-teal"


def test_reserve_racing_a_claim_settles_to_one_outfit():
    db = _race_db("race3.db")
    seen = {}

    def other_worker():
        seen["got"] = O.reserve(db, "outfit-b-plum", "L")

    with interleave(other_worker):
        got = O.claim(db, "L")
    assert len(_held(db, "L")) == 1, _held(db, "L")
    winner = _held(db, "L")[0]
    assert got["outfit_id"] == winner
    assert seen["got"]["status"] == "PASS"          # it was first; the claim then settled
    assert O.reserve(db, "outfit-c-teal", "L")["status"] == "FAIL"


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


# ============================================================ 6. owner Decision 2: the contact sheet

from brambleloop.visual import identity_labelling as L  # noqa: E402


def _png(seed: int) -> bytes:
    import io as _io

    from PIL import Image

    b = _io.BytesIO()
    Image.new("RGB", (64, 64), (seed * 9 % 255, 120, 200)).save(b, "PNG")
    return b.getvalue()


def _stub_generator(out, calls):
    def gen(prompt, reference_urls):
        calls.append((prompt, list(reference_urls)))
        p = Path(out) / f"render-{len(calls)}.png"
        p.write_bytes(_png(len(calls)))
        return {"path": str(p), "cost_entry_id": len(calls)}
    return gen


READY = lambda db, env=None: {"state": "READY", "code": ""}  # noqa: E731


def test_contact_sheet_plan_conditions_every_frame_on_all_three_references():
    shots = L.plan()
    assert len(shots) == L.N_FRAMES == 24
    want = sorted(canonical.CURRENT_REFERENCE_HASHES.values())
    assert all(sorted(r["sha256"] for r in s["references"]) == want for s in shots)
    assert len({s["prompt"] for s in shots}) == 24                    # 24 different shots
    assert len({s["framing"] for s in shots}) >= 4 and len({s["angle"] for s in shots}) == 3
    assert L.N_FRAMES * L.price_usd() <= L.CAP_USD < (L.N_FRAMES + 1) * L.price_usd()


def test_contact_sheet_generation_refuses_without_key_and_activation_and_spends_nothing():
    out = Path(os.environ.get("TMPDIR", "/tmp")) / "cs-refused"
    calls = []
    for env in ({}, {"BRAMBLELOOP_IMAGE_KEY_BFL": "x"}):
        try:
            L.generate(None, out, env=env, generator=_stub_generator(out, calls))
        except L.NotReady as exc:
            assert exc.code in ("no_bfl_credential", "accounting_store_missing") or \
                "activation" in str(exc) or exc.code, exc
        else:
            raise AssertionError("generated without the key and the owner's activation")
    assert calls == [] and not (out / "contact_sheet.json").exists()


def test_contact_sheet_generate_sheet_label_and_add_round_trip():
    root = Path(os.environ.get("TMPDIR", "/tmp")) / "cs-repo"
    out = root / "sheet"
    calls = []
    man = L.generate(None, out, generator=_stub_generator(out, calls), ready=READY)
    assert len(man["frames"]) == 24 and len(calls) == 24
    assert all(len(refs) == 3 for _, refs in calls)
    assert all(f["label"] is None for f in man["frames"])          # never self-labelled
    again = L.generate(None, out, generator=_stub_generator(out, calls), ready=READY)
    assert len(calls) == 24 and len(again["frames"]) == 24          # idempotent: no re-buy
    png = L.contact_sheet(man, out)
    from PIL import Image
    import io as _io

    w, h = Image.open(_io.BytesIO(png)).size
    assert w > h > 0                                                # 6 x 4 grid
    page = L.labelling_page(man)
    assert page.count('value="laura"') == 24 and page.count('value="not_laura"') == 24
    laura, other = L.parse_numbers("1-20,22"), L.parse_numbers("21,23,24")
    for bad in (dict(laura=laura, not_laura=other[:-1], labelled_by="owner"),   # one missing
                dict(laura=laura + [21], not_laura=other, labelled_by="owner"),  # both ways
                dict(laura=laura, not_laura=other + [25], labelled_by="owner"),  # not on sheet
                dict(laura=laura, not_laura=other, labelled_by=" ")):           # nobody
        try:
            L.apply_labels(man, out, **bad)
        except L.LabelsRefused:
            pass
        else:
            raise AssertionError(f"labels accepted: {bad}")
    labelled = L.apply_labels(man, out, laura=laura, not_laura=other, labelled_by="owner")
    assert sum(f["label"] == L.LAURA for f in labelled["frames"]) == 21
    sp = root / "calibration_set.json"
    sp.write_text(json.dumps({"version": "x", "samples": []}))
    try:
        L.add_to_calibration_set(man, out, sp, root)                # unlabelled: refused
    except L.LabelsRefused:
        pass
    else:
        raise AssertionError("an unlabelled sheet reached the calibration set")
    assert L.add_to_calibration_set(labelled, out, sp, root) == {"added": 24, "samples": 24}
    assert L.add_to_calibration_set(labelled, out, sp, root)["added"] == 0     # idempotent
    added = json.loads(sp.read_text())["samples"]
    assert {s["label"] for s in added} == {C.GENUINE, C.IMPOSTOR}
    assert all("no real person" in s["licence"] for s in added)
    # tampered bytes after labelling: refused
    (out / man["frames"][0]["file"]).write_bytes(b"changed")
    try:
        L.apply_labels(man, out, laura=laura, not_laura=other, labelled_by="owner")
    except L.LabelsRefused as exc:
        assert "sha256" in str(exc)
    else:
        raise AssertionError("tampered frame was labelled")


# ============================================================ 7. the models in the Railway image

def _fetch_script():
    import importlib.util

    spec = importlib.util.spec_from_file_location("fetch_face_models",
                                                  ROOT / "scripts/fetch_face_models.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_dockerfile_fetches_the_pinned_models_without_breaking_the_build():
    docker = (ROOT / "Dockerfile").read_text()
    lines = [ln.strip() for ln in docker.splitlines()]
    assert "ENV BRAMBLELOOP_FACE_MODEL_DIR=/app/models/face" in lines
    run = [ln for ln in lines if ln.startswith("RUN") and "fetch_face_models.py" in ln]
    assert run == ['RUN python scripts/fetch_face_models.py --best-effort '
                   '"$BRAMBLELOOP_FACE_MODEL_DIR"'], run
    # after the locked install (onnxruntime comes from the lock), before the full source copy
    i_pip = next(k for k, ln in enumerate(lines) if "--require-hashes" in ln)
    i_run = lines.index(run[0])
    i_src = lines.index("COPY src ./src")
    assert i_pip < i_run < i_src
    lock = (ROOT / "requirements.lock").read_text()
    assert "\nonnxruntime==" in lock and "onnxruntime>=" in (ROOT / "requirements.txt").read_text()
    from brambleloop.visual import face_embedder as FE

    assert FE.DEFAULT_MODEL_DIR == os.environ.get("BRAMBLELOOP_FACE_MODEL_DIR",
                                                  "/app/models/face")


def test_fetch_script_reads_the_embedders_pins_and_deletes_a_mismatch():
    from brambleloop.visual import face_embedder as FE

    fs = _fetch_script()
    pins, default_dir = fs._pins()
    assert pins == FE.MODELS and default_dir == FE.DEFAULT_MODEL_DIR
    tmp = Path(os.environ.get("TMPDIR", "/tmp")) / "fetch-test"
    src = tmp / "src"
    src.mkdir(parents=True, exist_ok=True)
    (src / "m.onnx").write_bytes(b"model bytes")
    good = hashlib.sha256(b"model bytes").hexdigest()
    url = (src / "m.onnx").resolve().as_uri()
    dst = tmp / "dst"
    assert fs.main(str(dst), {"x": {"file": "m.onnx", "sha256": good, "url": url,
                                    "licence": "test"}}) == 0
    assert (dst / "m.onnx").read_bytes() == b"model bytes"
    bad = tmp / "dst-bad"
    assert fs.main(str(bad), {"x": {"file": "m.onnx", "sha256": "0" * 64, "url": url,
                                    "licence": "test"}}) == 1
    assert not (bad / "m.onnx").exists()                     # mismatched bytes never kept
    gone = tmp / "dst-gone"
    assert fs.main(str(gone), {"x": {"file": "m.onnx", "sha256": good,
                                     "url": (src / "nope").resolve().as_uri(),
                                     "licence": "test"}}) == 1
    # --best-effort: the build exits 0 and the embedder then refuses (HOLD, never PASS)
    import subprocess

    r = subprocess.run([sys.executable, "-I", str(ROOT / "scripts/fetch_face_models.py"),
                        "--best-effort", str(tmp / "offline")], capture_output=True, text=True,
                       env={**os.environ, "HTTPS_PROXY": "http://127.0.0.1:9",
                            "https_proxy": "http://127.0.0.1:9", "NO_PROXY": "", "no_proxy": ""},
                       timeout=120)
    assert r.returncode == 0 and "NOT installed" in r.stdout, (r.returncode, r.stdout, r.stderr)
    emb, why = FE.try_load(tmp / "offline")
    assert emb is None and why


def test_embedder_keeps_to_the_ram_budget_settings():
    src = (ROOT / "src/brambleloop/visual/face_embedder.py").read_text()
    assert "opts.enable_cpu_mem_arena = False" in src and "intra_op_num_threads" in src


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
