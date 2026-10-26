"""W-VISNEXT2: stage A (Laura identity anchor), stage D (edit the accepted lifestyle frame),
controlled pipeline runs of a certified release (Cloudline acceptance), and the fidelity
verifier at 1k. Offline: stub provider, stub/recorded judges, no network, no spend.

Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_w4_visnext2.py
"""
import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import hashlib
import importlib.util
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import test_w4_ownerimg as O  # noqa: E402  (artifact dir, certified scratch DB, drain)

CLOUD = "cloudline-baby-blanket"


# ---- 4. the fidelity verifier at 1k --------------------------------------------------------

def test_fidelity_verifier_is_not_qualified_at_1k():
    """Measured, not assumed. At 1k every planted defect still FAILs (no false PASS), but the
    calibration positives do not all PASS (false FAILs), so 1k is not qualified and the flat
    lay stays at 2k. Only the identity anchor, judged by vision and never a frame, uses 1k."""
    import test_w4_fidelity as T
    from brambleloop.creative import image_stages as S
    from brambleloop.visual import fidelity as F

    false_fail = []
    for slug in (T.CLOUD, T.WRAP, T.COASTERS):
        cir = T._cir(slug)
        for kw in T.PERTURBATIONS:
            v = F.verify_anchor(T.flat_lay(cir, canvas=1024, **kw), cir, judge=T.PASSING_JUDGE)
            assert v["status"] != "UNKNOWN" or v["unknown"], (slug, kw)
            if v["status"] != "PASS":
                false_fail.append((slug, kw, v["failed"]))
    negatives = [
        (T.CLOUD, "INVENTED_END_BAND_TREATMENT",
         dict(piece_edit=T.stripe_in_top_band("#1A2B3C", (0.018, 0.026)))),
        (T.CLOUD, "INVENTED_EDGING", dict(piece_edit=T.edging(T._hexrgb("#FAF6EB"), 0.03))),
        (T.CLOUD, "WRONG_REPEAT_COUNT", dict(piece_edit=T.fewer_repeats(10, 11))),
        (T.CLOUD, "OFF_PALETTE_COLOUR",
         dict(piece_edit=T.recolour_rows("#1A2B3C", "#D4A017", (0.40, 0.46)))),
        (T.COASTERS, "WRONG_PIECE_COUNT", dict(drop=1))]
    assert len(negatives) == 5
    for slug, code, kw in negatives:
        cir = T._cir(slug)
        v = F.verify_anchor(T.flat_lay(cir, canvas=1024, **kw), cir, judge=T.PASSING_JUDGE)
        assert v["status"] == "FAIL" and code in v["codes"], (slug, code, v["codes"])
    # The qualification flag must agree with the measurement, both ways.
    assert F.ANCHOR_1K_QUALIFIED is (not false_fail), false_fail
    assert false_fail, "1k now passes every calibration case: re-qualify deliberately"
    assert S.PRODUCT_SIZE == "2048x2048" and S.meets_listing_floor(S.PRODUCT_SIZE)
    assert not S.meets_listing_floor(S.IDENTITY_ANCHOR_SIZE)          # intermediate only
    stub = S.StubRenderer()
    rel = S.release_from_cir(T._cir(T.CLOUD), release_hash=O._release_of(CLOUD),
                             out_dir=tempfile.mkdtemp())
    try:
        S.product_only(rel, size="1024x1024", renderer=stub, work_dir=tempfile.mkdtemp())
        raise AssertionError("a 1k flat lay was accepted")
    except S.StageRefused:
        pass
    assert stub.calls == []


# ---- stage A and stage D through the orchestrator --------------------------------------------

class StagedGen(O.StubGenerator):
    """The stub provider, declaring the staged method; records what each role was handed."""

    accepts_staged_method = True
    name = "staged-stub"

    def __init__(self):
        super().__init__()
        self.handed = []

    def generate(self, **kw):
        self.handed.append({"role": kw["role"], "repair": kw.get("repair"),
                            "labels": [(r["kind"], r.get("label"), r.get("sha256"))
                                       for r in kw["references"]]})
        return super().generate(**kw)


class Judges(O.StubJudges):
    """Stub judges; the identity anchor's body reading follows `body` in order."""

    def __init__(self, body=("PASS",), identity="PASS", lifestyle_product="PASS"):
        super().__init__()
        self.body, self.n, self.ident, self.lp = list(body), 0, identity, lifestyle_product

    def body_proportions(self, c):
        if c.get("role") == "laura_identity_anchor":
            st = self.body[min(self.n, len(self.body) - 1)]
            self.n += 1
            return ({"status": st, "why": "stub", "drifted": ["bust"]} if st == "FAIL" else
                    {"status": st, "why": "stub"})
        return {"status": "PASS", "why": "stub"}

    def identity(self, c):
        if c.get("role") == "laura_identity_anchor":
            return {"status": self.ident, "why": "stub"}
        return {"status": "PASS", "why": "stub"}

    def product_truth(self, c, bind):
        if c.get("role") == "lifestyle":
            return {"status": self.lp, "why": "stub"}
        return {"status": "PASS", "why": "stub"}


def _go(db, gen, judges):
    from brambleloop.visual import image_production as IP

    follow, _ = O.drain(db, generator=gen, judges=judges)
    IP.trigger(follow, slug=CLOUD, version="1.2.0", release=O.RELEASE)
    O.drain(db, generator=gen, judges=judges)
    return IP.run_key(CLOUD, "1.2.0", O.RELEASE)


def test_stage_a_anchor_is_judged_then_reused_after_the_canonical_three_and_stage_d_edits():
    from brambleloop.visual import image_production as IP

    db = O.make_db()
    gen = StagedGen()
    key = _go(db, gen, Judges())
    run = IP.get_run(db, key)
    assert "identity_anchor" in run["stages"] and run["state"] == "ready_for_owner_review", run
    roles = [h["role"] for h in gen.handed]
    assert roles.index("laura_identity_anchor") < roles.index("lifestyle")
    anchor = IP._best(db, listing=CLOUD, role=IP.IDENTITY_ANCHOR_ROLE, run=key)
    assert anchor["technical_status"] == "PASS" and anchor["publishable"] is False
    life = [h for h in gen.handed if h["role"] == "lifestyle"][0]
    kinds = [k for k, _, _ in life["labels"]]
    assert kinds.index("laura_canonical") < kinds.index("prior_candidate")
    assert ("prior_candidate", "identity_anchor", anchor["sha256"]) in life["labels"]
    # stage D: every other Laura role edits the accepted lifestyle frame; one outfit
    lif = IP._best(db, listing=CLOUD, role="lifestyle", run=key)
    others = [h for h in gen.handed if h["role"] in ("size", "colour_context")]
    assert others and all(("prior_candidate", "edit_base", lif["sha256"]) in h["labels"]
                          for h in others)
    assert run["card"]["campaign_consistency"]["status"] == "PASS"
    card = IP.gallery_card(db, key)
    assert card["identity_anchor"]["technical_status"] == "PASS"


def test_one_bounded_proportion_correction_then_block():
    from brambleloop.visual import image_production as IP

    db = O.make_db()
    gen = StagedGen()
    key = _go(db, gen, Judges(body=("FAIL", "PASS")))
    a = [h for h in gen.handed if h["role"] == "laura_identity_anchor"]
    assert len(a) == 2 and a[0]["repair"] is None and a[1]["repair"]["correction"] == ["bust"]
    assert IP.get_run(db, key)["state"] == "ready_for_owner_review"
    db2 = O.make_db()
    gen2 = StagedGen()
    key2 = _go(db2, gen2, Judges(body=("FAIL", "FAIL")))
    run2 = IP.get_run(db2, key2)
    assert len([h for h in gen2.handed if h["role"] == "laura_identity_anchor"]) == \
        IP.MAX_IDENTITY_ANCHOR_ATTEMPTS == 2
    assert run2["state"] == "blocked" and run2["attempts_exhausted"]
    assert "lifestyle" not in [h["role"] for h in gen2.handed]


def test_unknown_anchor_goes_to_owner_review_and_never_becomes_pass():
    from brambleloop.queue.durable import DuplicateJob, JobQueue
    from brambleloop.visual import image_production as IP

    db = O.make_db()
    gen = StagedGen()
    judges = Judges(identity="UNKNOWN")
    key = _go(db, gen, judges)
    run = IP.get_run(db, key)
    assert run["state"] == "blocked" and "held for owner review" in run["blocked_reason"]
    assert not run["attempts_exhausted"]
    assert "lifestyle" not in [h["role"] for h in gen.handed]
    notes = IP.notification_candidates(db)
    assert any("needs your review" in n["title"] for n in notes)
    q = JobQueue(db)

    def follow(inputs, k):
        try:
            return q.enqueue(IP.AGENT, IP.JOB_TYPE, inputs, idempotency_key=k)
        except DuplicateJob:
            return None

    out = IP.resolve_identity_anchor_review(db, key, decision="confirmed_same_person",
                                            by="owner:test", follow=follow)
    assert out["resolved"] and out["restart"]["restarted"], out
    O.drain(db, generator=gen, judges=judges)
    run = IP.get_run(db, key)
    rec = IP._stage_data(db, key)["identity_anchor"]["outputs"]
    assert "owner review confirmed" in rec["basis"]
    anchor = IP._best(db, listing=CLOUD, role=IP.IDENTITY_ANCHOR_ROLE, run=key)
    assert anchor["technical_status"] == "UNKNOWN"                       # never PASS
    assert len([h for h in gen.handed if h["role"] == "laura_identity_anchor"]) == 1
    assert "lifestyle" in [h["role"] for h in gen.handed]                # resumed
    # not Laura: stage A ends
    db2 = O.make_db()
    gen2 = StagedGen()
    key2 = _go(db2, gen2, judges)
    q2 = JobQueue(db2)
    out2 = IP.resolve_identity_anchor_review(
        db2, key2, decision="not_laura", by="owner:test",
        follow=lambda i, k: q2.enqueue(IP.AGENT, IP.JOB_TYPE, i, idempotency_key=k))
    O.drain(db2, generator=gen2, judges=judges)
    assert IP.get_run(db2, key2)["attempts_exhausted"] and out2["resolved"]


def test_stage_a_is_skipped_for_generators_without_it_and_for_experiments():
    from brambleloop.visual import image_production as IP

    db = O.make_db()
    gen = O.StubGenerator()
    key = _go(db, gen, O.StubJudges())
    rec = IP._stage_data(db, key)["identity_anchor"]["outputs"]
    assert "does not carry the staged method" in rec["skipped"]
    assert IP.get_run(db, key)["state"] == "ready_for_owner_review"


def test_stage_d_needs_an_accepted_lifestyle_frame():
    from brambleloop.visual import image_production as IP

    db = O.make_db()
    gen = StagedGen()
    _go(db, gen, Judges(lifestyle_product="FAIL"))
    others = [h for h in gen.handed if h["role"] in ("size", "colour_context")]
    assert others and not any(lbl == "edit_base" for h in others for _, lbl, _ in h["labels"])


# ---- the generator carries stage A and stage D -------------------------------------------------

def test_flux3_generator_builds_the_anchor_and_the_edit_with_the_canonical_three_first():
    import test_w4_flux3generator as FG3
    from brambleloop.creative import flux3_generator as FG
    from brambleloop.creative import image_stages as S

    g, stub = FG3._gen()
    refs = FG3._orchestrator_refs(g.prepare_references(slug=FG3.SLUG, version=FG3.VER,
                                                       release=FG3.REL))
    a = g.generate(stage="identity_anchor", role=FG.IDENTITY_ANCHOR_ROLE, brief="alone",
                   references=refs + FG3._laura_refs(), outfit=FG3.OUTFIT, attempt=1,
                   repair={"correction": ["bust"]})
    ev = a["identity_evidence"]
    assert ev["stage"] == "identity_anchor" and ev["size"] == S.IDENTITY_ANCHOR_SIZE
    assert [r["role"] for r in ev["references"]] == list(S.LAURA_ROLES)
    assert "PROPORTION CORRECTION" in stub.calls[-1]["prompt"] and "bust" in \
        stub.calls[-1]["prompt"]
    assert "PRODUCT:" not in stub.calls[-1]["prompt"]
    out = g.generate(stage="product_generation", role=FG.ANCHOR_ROLE, brief="flat",
                     references=refs, outfit=None, attempt=1)
    g.anchor_lookup = lambda s, v, r, **k: {"data": out["data"], "status": "PASS",
                                            "sha256": hashlib.sha256(out["data"]).hexdigest()}
    ia = {"kind": "prior_candidate", "label": "identity_anchor",
          "sha256": hashlib.sha256(a["data"]).hexdigest(), "data": a["data"]}
    life = g.generate(stage="lifestyle_generation", role="lifestyle", brief="sofa",
                      references=refs + FG3._laura_refs() + [ia], outfit=FG3.OUTFIT, attempt=1)
    roles = [r["role"] for r in life["identity_evidence"]["references"]]
    assert roles[:3] == list(S.LAURA_ROLES) and roles[-1] == "identity_anchor"
    base = {"kind": "prior_candidate", "label": "edit_base",
            "sha256": hashlib.sha256(life["data"]).hexdigest(), "data": life["data"]}
    var = g.generate(stage="remaining_roles", role="size", brief="in hand",
                     references=refs + FG3._laura_refs() + [ia, base], outfit=FG3.OUTFIT,
                     attempt=1)
    ev = var["identity_evidence"]
    assert ev["stage"] == "variant" and ev["role"] == "scale_in_hand"
    vroles = [r["role"] for r in ev["references"]]
    assert vroles[:3] == list(S.LAURA_ROLES) and "base" in vroles and \
        "identity_anchor" in vroles and len(vroles) <= 10
    assert FG3.OUTFIT["description"] in stub.calls[-1]["prompt"]       # outfit kept identical


# ---- the Cloudline acceptance harness and controlled pipeline runs --------------------------

def _harness():
    spec = importlib.util.spec_from_file_location(
        "cloudline_acceptance", ROOT / "research/final_build/w4/cloudline_acceptance/run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_cloudline_acceptance_dry_run_end_to_end_through_the_experiment_command():
    from brambleloop.core.db import Database
    from brambleloop.experiments import controlled as C
    from brambleloop.visual import experiment as XP
    from brambleloop.visual import gallery_persist as GP
    from brambleloop.visual import image_production as IP

    H = _harness()
    out = Path(tempfile.mkdtemp(prefix="cl-acc-")) / "out"
    s = H.run(live=False, out=out)
    assert [t["step"] for t in s["timeline"]] == [1, 2, 3, 4, 5, 6, 7]
    assert s["timeline"][0]["granted"] is True and set(s["pdf_sha256"]) == {"US", "UK"}
    assert s["orchestrator"]["state"] == "ready_for_owner_review", s["orchestrator"]
    assert "identity_anchor" in s["orchestrator"]["stages"]
    assert s["card_title_banner"] == C.CERTIFIED_LABEL                 # certified: truthful
    assert s["publication"]["state"] == "not_available"
    assert s["shared_cap_group"] == ["exp-2026-10-20-wrap-7ref",
                                     "exp-2026-10-21-cloudline-acceptance"]
    imgs = s["experiment_images"]
    assert len(imgs) == s["orchestrator"]["generation_calls"] >= 3
    db = Database(f"sqlite:///{out / 'scratch_shadow.db'}", scratch=True)
    assert all(XP.is_experiment_image(db, h) for h in imgs)
    key = s["orchestrator"]["run_key"]
    try:
        IP.approve(db, key, decided_by="owner:test")
        raise AssertionError("an experiment gallery was approved for publication")
    except XP.ExperimentRefused:
        pass
    try:
        GP.write_frames(db, CLOUD, "1.2.0", [{"position": 2, "role": "lifestyle",
                                              "candidate_id": 1, "sha256": imgs[-1]}],
                        run_key=key)
        raise AssertionError("an experiment image became a listing asset")
    except XP.ExperimentRefused:
        pass
    assert IP.restartable(db, key)["restartable"] is False
    ordinary = s["timeline"][0]["ordinary_run"]
    assert ordinary is None or "image_generation gate closed" in ordinary   # never touched


def test_shared_cap_is_counted_once_across_both_definitions():
    from brambleloop.experiments import controlled as C
    from brambleloop.visual.image_production import BudgetStop

    db = O.make_db()
    C.authorize(db, "exp-2026-10-20-wrap-7ref", by="owner", stepped_up=True)
    wrap = C.submit(db, "exp-2026-10-20-wrap-7ref", by="owner", stepped_up=True,
                    enqueue=lambda i, k: None)
    C._update(db, wrap["run_id"], status="completed", generation_spent_cad=4.95)
    C.authorize(db, "exp-2026-10-21-cloudline-acceptance", by="owner", stepped_up=True)
    cl = C.submit(db, "exp-2026-10-21-cloudline-acceptance", by="owner", stepped_up=True,
                  enqueue=lambda i, k: None)
    C._update(db, cl["run_id"], status="running")
    try:
        C.guard_generation(db, cl["run_id"], 0.14)
        raise AssertionError("the shared cap was double-counted")
    except BudgetStop as exc:
        assert "shared generation cap" in str(exc)
    C._update(db, wrap["run_id"], generation_spent_cad=1.0)
    C.guard_generation(db, cl["run_id"], 0.14)                        # room now
    assert abs(C._group_spent(db, "exp-2026-10-20-wrap-7ref")[0] - 1.14) < 1e-9


def test_pipeline_definition_drift_and_foreign_runs_are_refused_before_spend():
    import json
    import shutil

    from brambleloop.experiments import controlled as C
    from brambleloop.visual import experiment as XP

    db = O.make_db()
    v = C.verify(C.load("exp-2026-10-21-cloudline-acceptance"), db)
    assert v["ok"], v["problems"]                                      # make_db certifies it
    saved = C.DEFINITIONS_DIR
    d = Path(tempfile.mkdtemp()) / "definitions"
    shutil.copytree(saved, d)
    f = d / "exp-2026-10-21-cloudline-acceptance" / "definition.json"
    j = json.loads(f.read_text())
    j["pipeline"]["pattern_references"][0]["sha256"] = "0" * 64
    j["pipeline"]["prompt_sections"]["image.flux3.identity@2"] = "1" * 64
    f.write_text(json.dumps(j))
    try:
        C.DEFINITIONS_DIR = d
        p = C.verify(C.load("exp-2026-10-21-cloudline-acceptance"), db)["problems"]
    finally:
        C.DEFINITIONS_DIR = saved
    assert any("pattern references" in x for x in p) and any("identity@2" in x for x in p)
    try:
        C.require_pipeline_run(db, 999, ns="exp999", slug=CLOUD, version="1.2.0",
                               release=O.RELEASE)
        raise AssertionError("a foreign controlled stage was accepted")
    except XP.ExperimentRefused:
        pass


def test_live_acceptance_refuses_without_keys():
    H = _harness()
    saved = {k: os.environ.pop(k, None) for k in H.KEY_VARS}
    out = Path(tempfile.mkdtemp()) / "out"
    try:
        try:
            H.run(live=True, out=out)
            raise AssertionError("live ran without keys")
        except H.Refused:
            pass
    finally:
        for k, val in saved.items():
            if val is not None:
                os.environ[k] = val
    assert not out.exists()


if __name__ == "__main__":
    fails = passes = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn) and fn.__module__ == __name__:
            try:
                fn()
                passes += 1
                print("OK  ", name)
            except BaseException as e:  # noqa: BLE001 - Refused is a SystemExit
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    print(f"\n{passes} passed, {fails} failed")
    sys.exit(1 if fails else 0)
