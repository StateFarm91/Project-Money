"""W-VISNEXT: blind vision-judge adapters, the lifestyle product-region detector, restart of a
blocked run, persisting approved frames, the Command Center gallery card and wardrobe editor,
and the learning taxonomy end to end.

Offline and SHADOW. Every judge answer comes from the recorded fixtures in
`tests/fixtures/visnext/readings.json`; no provider is called, nothing is spent.
"""
import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import copy
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import test_w4_ownerimg as O  # noqa: E402  (sets the artifact dir; shared helpers)
import test_w4_fidelity as TF  # noqa: E402

from PIL import Image, ImageDraw  # noqa: E402

READINGS = json.loads((ROOT / "tests" / "fixtures" / "visnext" / "readings.json").read_text())
CLOUD = "cloudline-baby-blanket"


class Recorded:
    """A judge transport that answers from the recorded fixtures. Spends nothing.

    `scenarios` are fixture keys, searched in order for the task named on the prompt's first
    line ("Task: <task>"); fidelity's own craft question is answered with a crochet reading."""

    def __init__(self, *scenarios, name="recorded", model="judge-a", craft=None):
        self.scenarios, self.name, self.model = scenarios, name, model
        self.craft = craft or TF.PASSING_JUDGE.reading
        self.calls = []

    def read(self, prompt, images, *, system=None, max_tokens=300):
        first = prompt.split("\n", 1)[0]
        task = first[len("Task: "):] if first.startswith("Task: ") else (
            "craft" if "craft: one of" in prompt else "?")
        self.calls.append({"task": task, "images": len(images), "prompt": prompt})
        if task == "craft":
            return {"answered": True, "reading": dict(self.craft), "model": self.model}
        for sc in self.scenarios:
            if task in READINGS[sc]:
                return {"answered": True, "reading": copy.deepcopy(READINGS[sc][task]),
                        "model": self.model}
        return {"answered": False, "why": f"no recorded answer for {task}"}

    def tasks(self):
        return [c["task"] for c in self.calls]


class NeverCalled:
    """A provider that fails the test if the gateway ever reaches it."""

    model = "never"
    cost_per_1k_input_cad = cost_per_1k_output_cad = 0.0

    def see(self, *a, **k):
        raise AssertionError("a provider was called while the vision gate was closed")


REFS = {"neutral_portrait": O.png(64, 64), "torso_fit_reference": O.png(64, 64),
        "full_length_standing": O.png(64, 64)}


def laura_cand(db, **kw):
    from brambleloop.visual import outfits

    if outfits.get(db, "sage-cardigan-01") is None:
        O.approved_outfit(db)
        outfits.reserve(db, "sage-cardigan-01", CLOUD)
    base = dict(role="lifestyle", release=O.RELEASE, laura_present=True,
                outfit_id="sage-cardigan-01")
    base.update(kw)
    return O.cand(**base)


def exp_cloud():
    from brambleloop.visual import fidelity as F

    return F.expectation(TF._cir(CLOUD))


# ---- 1. blind, structured adapters ---------------------------------------------------------

def test_prompts_are_blind_to_the_expected_answer():
    from brambleloop.visual import vision_judges as VJ

    db = O.make_db()
    O.approved_outfit(db, "sage-cardigan-01")
    O.approved_outfit(db, "oat-jumper-02")
    seen = []
    for oid in ("sage-cardigan-01", "oat-jumper-02"):
        j = Recorded("outfit_sage_match")
        from brambleloop.visual import outfits

        VJ.Adapters(db, j, references=REFS).outfit_consistency(O.cand(), outfits.get(db, oid))
        seen.append(j.calls[0]["prompt"])
    # The question is identical whatever outfit is reserved: the judge cannot be steered.
    assert seen[0] == seen[1]
    cir = TF._cir(CLOUD)
    palette = [str(c.get("hex") if isinstance(c, dict) else getattr(c, "hex", "")).lower()
               for c in (getattr(cir, "colors", None) or [])]
    texts = [VJ.person_prompt("refs_first"), VJ.person_prompt("photo_first"),
             VJ.outfit_prompt(), VJ.anatomy_prompt(), VJ.realism_prompt(), VJ.item_prompt(),
             VJ.region_prompt()]
    assert len(texts) == 7
    for t in texts:
        low = t.lower()
        import re

        assert not re.search(r"\b(laura|should|expected|must match)\b", low), t[:80]
        assert not any(h and h in low for h in palette), t[:80]
        assert "cloudline" not in low and "edging the pattern" not in low
    # identity asks a comparison per dimension in a closed vocabulary, both orders
    assert '"same", "different", "cannot_tell"' in VJ.person_prompt("refs_first")
    assert VJ.person_prompt("refs_first") != VJ.person_prompt("photo_first")


def test_identity_needs_two_independent_judges_and_never_passes_without_biometrics():
    from brambleloop.visual import vision_judges as VJ

    db = O.make_db()
    a = Recorded("laura_match_a", name="judge-a", model="m-a")
    b = Recorded("laura_match_b", name="judge-b", model="m-b")
    ad = VJ.Adapters(db, a, second=b, references=REFS)
    c = laura_cand(db)
    ident = ad.identity(c)
    # both judges read Laura; conditioning unproven and no qualified biometric floor
    assert ident["status"] == "UNKNOWN" and ident["judges"] == ["judge-a:m-a", "judge-b:m-b"]
    assert a.tasks() == ["identity_morphology"] and b.tasks() == ["identity_morphology"]
    assert a.calls[0]["images"] == 4 and b.calls[0]["images"] == 4
    assert a.calls[0]["prompt"] != b.calls[0]["prompt"]        # alternated image order
    # one judge reading a face drift refuses outright
    drift = VJ.Adapters(db, Recorded("face_drift"), references=REFS).identity(c)
    assert drift["status"] == "FAIL" and drift["band"] == "AUTO_REFUSE"
    assert {"face", "eyes"} <= set(drift["failed"])
    # the same judge twice is one reading, not two
    same = Recorded("laura_match_a", name="judge-a", model="m-a")
    ad2 = VJ.Adapters(db, same, second=same, references=REFS)
    assert len([r for r in ad2._person(c) if r.get("answered")]) == 1


def test_body_proportions_compared_against_the_canonical_morphology():
    from brambleloop.visual import vision_judges as VJ

    db = O.make_db()
    c = laura_cand(db)
    two = VJ.Adapters(db, Recorded("laura_match_a", name="a", model="1"),
                      second=Recorded("laura_match_b", name="b", model="2"), references=REFS)
    assert two.body_proportions(c)["status"] == "PASS"
    one = VJ.Adapters(db, Recorded("laura_match_a"), references=REFS)
    got = one.body_proportions(c)
    assert got["status"] == "UNKNOWN" and "two independent readings" in got["why"]
    bust = VJ.Adapters(db, Recorded("bust_drift", name="a", model="1"),
                       second=Recorded("laura_match_b", name="b", model="2"), references=REFS)
    got = bust.body_proportions(c)
    assert got["status"] == "FAIL" and got["drifted"] == ["bust"]
    hidden = VJ.Adapters(db, Recorded("torso_hidden", name="a", model="1"),
                         second=Recorded("torso_hidden", name="b", model="2"), references=REFS)
    assert hidden.body_proportions(c)["status"] == "UNKNOWN"      # bust and torso unread
    # identity and body share the reading: one call per judge per image
    j = Recorded("laura_match_a")
    ad = VJ.Adapters(db, j, references=REFS)
    ad.identity(c), ad.body_proportions(c)
    assert j.tasks() == ["identity_morphology"]
    # no canonical references by their recorded bytes: nothing asked, UNKNOWN
    j2 = Recorded("laura_match_a")
    none = VJ.Adapters(db, j2, references={})
    assert none.body_proportions(c)["status"] == "UNKNOWN" and j2.calls == []


def test_outfit_consistency_five_slots_carryover_and_repetition():
    from brambleloop.visual import outfits
    from brambleloop.visual import vision_judges as VJ

    db = O.make_db()
    c = laura_cand(db)
    O.approved_outfit(db, "oat-jumper-02")
    outfits.reserve(db, "oat-jumper-02", "winter-village-graphghan")
    reserved = outfits.get(db, "sage-cardigan-01")

    def read(sc):
        return VJ.Adapters(db, Recorded(sc), references=REFS).outfit_consistency(c, reserved)

    ok = read("outfit_sage_match")
    assert ok["status"] == "PASS", ok
    assert set(ok["slots"]) == {"top_or_dress", "lower", "shoes", "outerwear", "accessories"}
    assert ok["slots"]["shoes"]["result"] == "not_shown"
    carry = read("outfit_reference_carryover")
    assert carry["status"] == "FAIL" and carry["codes"] == ["REFERENCE_CLOTHING_CARRYOVER"]
    rep = read("outfit_other_listing")
    assert rep["status"] == "FAIL" and rep["codes"] == ["WARDROBE_REPETITION"], rep
    wrong = read("outfit_shoes_wrong")
    assert wrong["status"] == "FAIL" and "shoes" in wrong["why"] and not wrong.get("codes")
    hidden = read("outfit_lower_hidden")
    assert hidden["status"] == "UNKNOWN"
    # no reserved outfit: nothing asked
    j = Recorded("outfit_sage_match")
    assert VJ.Adapters(db, j).outfit_consistency(c, None)["status"] == "UNKNOWN"
    assert j.calls == []


def test_anatomy_and_realism_are_compared_in_code():
    from brambleloop.visual import vision_judges as VJ

    db = O.make_db()
    c = laura_cand(db)

    def run(sc, what):
        return getattr(VJ.Adapters(db, Recorded(sc), references=REFS), what)(c)

    assert run("anatomy_ok", "anatomy")["status"] == "PASS"
    six = run("anatomy_six_fingers", "anatomy")
    assert six["status"] == "FAIL" and "6 fingers" in six["why"]
    assert run("anatomy_unclear", "anatomy")["status"] == "UNKNOWN"
    two = VJ.compare_anatomy({**READINGS["anatomy_ok"]["anatomy"], "people": 2}, laura=True)
    assert two["status"] == "FAIL"
    assert run("realism_ok", "realism")["status"] == "PASS"
    tiled = run("realism_tiled", "realism")
    assert tiled["status"] == "FAIL" and "texture_not_repeating" in tiled["why"]
    assert run("realism_partial", "realism")["status"] == "UNKNOWN"   # unanswered keys
    from brambleloop.visual.gallery import REALISM_CHECKS

    assert set(VJ.REALISM_DEFECTS) == set(REALISM_CHECKS)


def test_blind_anchor_consistency_compares_two_descriptions_with_the_cir():
    from brambleloop.visual import vision_judges as VJ

    exp = exp_cloud()
    a, b = O.png(64, 64), O.png(64, 64)

    def run(sc):
        return VJ.blind_consistency(Recorded(sc), a, b, exp)

    assert run("item_same")["status"] == "PASS"
    assert run("item_border_invented")["code"] == "INVENTED_EDGING"
    assert run("item_knitted")["code"] == "WRONG_CRAFT_TEXTURE"
    assert run("item_extra_colour")["code"] == "WRONG_COLOUR_LAYOUT"
    assert run("item_hidden")["status"] == "UNKNOWN"
    assert VJ.blind_consistency(None, a, b, exp)["status"] == "UNKNOWN"
    j = Recorded("item_same")
    VJ.blind_consistency(j, a, b, exp)
    assert j.calls[0]["images"] == 2 and "same" not in j.calls[0]["prompt"].lower().split(
        "do not compare")[0]


def test_unfunded_or_closed_gate_is_unknown_and_calls_nothing():
    from brambleloop.visual import candidate_gates as CG
    from brambleloop.visual import fidelity as F

    db = O.make_db()
    c = laura_cand(db)
    vj = F.GatewayVisionJudge(db, provider=NeverCalled())     # image_vision closed
    judges = CG.RealJudges(db, vision=vj, references=REFS)
    v = CG.evaluate(db, c, judges=judges, record_outfit_use=False)
    for k in ("identity", "body_proportions", "anatomy", "realism", "outfit_consistency"):
        assert v["checks"][k]["status"] == "UNKNOWN", (k, v["checks"][k])
    assert "unfunded" in v["checks"]["realism"]["why"]
    assert v["technical_status"] != "PASS" and v["publishable"] is False


def test_open_gate_reserves_budget_before_the_call_and_bills_after():
    from brambleloop.build2 import executor
    from brambleloop.gateway import anthropic as gw
    from brambleloop.gateway.model_gateway import ModelResponse
    from brambleloop.visual import fidelity as F
    from brambleloop.visual import vision_judges as VJ

    db = O.make_db()
    order = []

    class Seeing:
        model = "claude-test-vision"
        cost_per_1k_input_cad, cost_per_1k_output_cad = 0.003, 0.015

        def see(self, system, prompt, paths, *, max_tokens):
            order.append("see")
            return ModelResponse(text=json.dumps(READINGS["anatomy_ok"]["anatomy"]),
                                 provider="anthropic", model=self.model, input_tokens=1000,
                                 output_tokens=100, latency_ms=1.0, stop_reason="end_turn")

    gate = executor.GATE_BY_KEY["image_vision"]
    saved = (gate.check, gw.check_budget, gw.release_reservation)

    def spy_budget(db_, **kw):
        order.append(("reserve", kw.get("agent"), kw.get("purpose")))
        return {"estimate_cad": 0.05, "reservation_id": None}

    def spy_release(db_, rid, actual_cad=None, **kw):
        order.append(("release", actual_cad))
        return True

    try:
        gate.check = lambda db_, env: True
        gw.check_budget, gw.release_reservation = spy_budget, spy_release
        ad = VJ.Adapters(db, F.GatewayVisionJudge(db, provider=Seeing()), references=REFS)
        got = ad.anatomy(laura_cand(db))
        assert got["status"] == "PASS", got
        assert order[0][0] == "reserve" and order[1] == "see" and order[2][0] == "release"
        assert order[2][1] > 0                                     # billed at the actual
        # a refused budget: nothing is sent, UNKNOWN
        order.clear()

        def refuse(db_, **kw):
            raise RuntimeError("ceiling reached")

        gw.check_budget = refuse
        got = VJ.Adapters(db, F.GatewayVisionJudge(db, provider=Seeing()),
                          references=REFS).realism(laura_cand(db))
        assert got["status"] == "UNKNOWN" and "see" not in order
    finally:
        gate.check, gw.check_budget, gw.release_reservation = saved


def test_evaluate_with_recorded_judges_reads_every_laura_gate_and_publication_stays_refused():
    from brambleloop.visual import candidate_gates as CG

    db = O.make_db()
    c = laura_cand(db)
    judges = CG.RealJudges(
        db, vision=Recorded("laura_match_a", "outfit_sage_match", "anatomy_ok", "realism_ok",
                            name="a", model="1"),
        second_vision=Recorded("laura_match_b", name="b", model="2"), references=REFS)
    v = CG.evaluate(db, c, judges=judges, record_outfit_use=False)
    st = {k: x["status"] for k, x in v["checks"].items()}
    assert st["body_proportions"] == "PASS" and st["outfit_consistency"] == "PASS"
    assert st["anatomy"] == "PASS" and st["realism"] == "PASS"
    assert st["identity"] == "UNKNOWN"          # biometric floor unqualified: review band
    assert v["technical_status"] != "PASS" and v["publishable"] is False
    assert any("F-852" in b for b in v["publication"]["blockers"])
    bad = CG.RealJudges(db, vision=Recorded("bust_drift", "outfit_reference_carryover",
                                            "anatomy_six_fingers", "realism_tiled"),
                        references=REFS)
    v2 = CG.evaluate(db, c, judges=bad, record_outfit_use=False)
    cats = set(v2["failure_categories"])
    assert {"body_proportion_drift", "outfit_consistency", "anatomy", "realism",
            "REFERENCE_CLOTHING_CARRYOVER"} <= cats, cats


# ---- 2. lifestyle product-region detector --------------------------------------------------

def _lifestyle_image():
    """A flat lay with an off-palette (mustard) block beside the product: a 'scene'."""
    img = Image.open(io.BytesIO(TF.flat_lay(TF._cir(CLOUD)))).convert("RGB")
    ImageDraw.Draw(img).rectangle((0, 0, 300, 2047), fill=(214, 168, 40))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_region_patches_validated_deterministically():
    from brambleloop.visual import vision_judges as VJ

    ok = VJ.validate_patches(READINGS["region_ok"]["product_region"], (2048, 2048))
    assert len(ok["patches"]) == 2 and ok["area"] >= VJ.MIN_TOTAL_AREA
    bad = VJ.validate_patches(READINGS["region_bad"]["product_region"], (2048, 2048))
    assert bad["patches"] == [] and "rejected" in bad["why"]
    none = VJ.validate_patches(READINGS["region_none"]["product_region"], (2048, 2048))
    assert none["patches"] == []


def test_lifestyle_palette_runs_inside_located_patches_and_fails_off_palette():
    from brambleloop.visual import fidelity as F
    from brambleloop.visual import vision_judges as VJ

    cir = TF._cir(CLOUD)
    data = _lifestyle_image()
    rel = O.RELEASE or O._release_of(CLOUD)
    anchor = {"status": "PASS", "release_hash": rel, "sha256": "a" * 64}
    loc = VJ.locate_product(Recorded("region_ok"), data)
    assert loc["patches"]
    v = F.verify_lifestyle(data, cir, release_hash=rel, anchor=anchor, anchor_data=data,
                           product_region=loc["patches"], judge=Recorded("item_same"),
                           consistency=VJ.blind_consistency)
    rp = TF.st(v, "region_palette")[0]
    assert rp["status"] == "PASS", rp
    assert TF.st(v, "anchor_consistency")[0]["status"] == "PASS"
    # a patch that lands on the mustard block: the colour check FAILs, not the judge
    off = F.verify_lifestyle(data, cir, release_hash=rel, anchor=anchor,
                             product_region=[(10, 10, 290, 2000)], judge=None)
    assert TF.st(off, "region_palette")[0]["status"] == "FAIL"
    assert "OFF_PALETTE_COLOUR" in off["codes"]
    # no located patch: still UNKNOWN, never PASS
    none = VJ.locate_product(Recorded("region_none"), data)
    v3 = F.verify_lifestyle(data, cir, release_hash=rel, anchor=anchor,
                            product_region=none["patches"] or None, judge=None)
    assert TF.st(v3, "region_palette")[0]["status"] == "UNKNOWN" and v3["status"] != "PASS"


def test_region_detector_is_asked_only_after_the_anchor_passed():
    from brambleloop.visual import candidate_gates as CG

    db = O.make_db()
    j = Recorded("region_ok", "item_same")
    judges = CG.RealJudges(db, vision=j, references=REFS)
    pt = judges.product_truth(O.cand(data=_lifestyle_image(), role="detail",
                                     release=O.RELEASE), CG.binding(db, CLOUD, "1.2.0",
                                                                    O.RELEASE))
    assert "product_region" not in j.tasks()          # no anchor PASS on record
    assert pt["status"] != "PASS"


# ---- 3. restart of a blocked run ----------------------------------------------------------

def _queue(db):
    from brambleloop.queue.durable import DuplicateJob, JobQueue

    q = JobQueue(db)

    def follow(inputs, key):
        try:
            return q.enqueue("publishing", "visual.image_production", inputs,
                             idempotency_key=key)
        except DuplicateJob:
            return None
    return q, follow


def _drain(db, gen, judges, limit=60):
    from brambleloop.visual import image_production as IP

    q, follow = _queue(db)
    ran = 0
    while ran < limit:
        job = q.claim("test-worker", job_types=[IP.JOB_TYPE])
        if job is None:
            break
        IP.run_stage(db, dict(job.inputs), follow=follow, generator=gen, judges=judges)
        q.complete(job.id, outputs={}, worker="test-worker", lease_token=job.lease_token)
        ran += 1
    return follow


def _start(db, gen, judges):
    from brambleloop.visual import image_production as IP

    _, follow = _queue(db)
    IP.trigger(follow, slug=CLOUD, version="1.2.0", release=O.RELEASE)
    _drain(db, gen, judges)
    return IP.run_key(CLOUD, "1.2.0", O.RELEASE)


FUNDED = ("laura_match_a", "outfit_sage_match", "anatomy_ok", "realism_ok", "item_same",
          "region_ok")


def test_restart_after_the_vision_judge_is_funded_reverifies_without_regenerating():
    from brambleloop.visual import candidate_gates as CG
    from brambleloop.visual import image_production as IP

    db = O.make_db()
    gen = TF.FlatLayGenerator(CLOUD)
    key = _start(db, gen, CG.RealJudges(db, references=REFS))        # image_vision closed
    run = IP.get_run(db, key)
    assert run["state"] == "blocked" and "fidelity cannot be verified" in run["blocked_reason"]
    assert gen.calls == 1 and not run["attempts_exhausted"]
    can = IP.restartable(db, key)
    assert can["restartable"] and can["resume_at"] == "fidelity_gate" and can["reverify"]
    funded = CG.RealJudges(db, vision=Recorded(*FUNDED), references=REFS)
    _, follow = _queue(db)
    out = IP.restart(db, key, follow=follow, by="owner:test", reason="vision funded")
    assert out["restarted"] and out["epoch"] == 1 and out["enqueued"]
    # a stale first-epoch job is skipped, never run twice
    stale = IP.run_stage(db, {"slug": CLOUD, "version": "1.2.0", "release": O.RELEASE,
                              "stage": "fidelity_gate"}, follow=follow, generator=gen,
                         judges=funded)
    assert stale.get("skipped") and "epoch" in stale["why"]
    _drain(db, gen, funded)
    run = IP.get_run(db, key)
    assert "load_laura_references" in run["stages"], run
    assert IP._attempts(db, key, IP.ANCHOR_ROLE) == 1               # re-read, not regenerated
    best = IP._best(db, listing=CLOUD, role=IP.ANCHOR_ROLE, run=key)
    assert best["technical_status"] == "PASS"
    from brambleloop.visual.image_records import ImageCandidate

    with db.session() as s:
        row = s.get(ImageCandidate, best["candidate_id"])
        hist = row.checks["_reverified"]["history"]
    assert hist[-1]["previous_status"] == "UNKNOWN"
    assert run["restarts"] == 1 and run["generation_calls"] >= 1


def test_restart_refuses_spent_failures_budget_stops_and_running_runs():
    from brambleloop.visual import candidate_gates as CG
    from brambleloop.visual import image_production as IP

    db = O.make_db()
    gen = TF.FlatLayGenerator(CLOUD, piece_edit=TF.stripe_in_top_band("#1A2B3C",
                                                                      (0.018, 0.026)))
    key = _start(db, gen, CG.RealJudges(db, vision=TF.FakeJudge()))
    run = IP.get_run(db, key)
    assert run["state"] == "blocked" and run["attempts_exhausted"]
    can = IP.restartable(db, key)
    assert not can["restartable"] and "FAIL" in can["why"]
    _, follow = _queue(db)
    assert IP.restart(db, key, follow=follow, by="owner:test")["restarted"] is False
    # a budget stop is final; a run that is not blocked is not restarted; caps hold
    from sqlalchemy import update
    from brambleloop.visual.image_records import ImageCandidate, ImageProductionRun

    db2 = O.make_db()
    key2 = _start(db2, TF.FlatLayGenerator(CLOUD), CG.RealJudges(db2, references=REFS))
    with db2.session() as s:
        s.execute(update(ImageProductionRun).where(ImageProductionRun.run_key == key2)
                  .values(blocked_reason="budget stop: plan exhausted"))
    assert not IP.restartable(db2, key2)["restartable"]
    with db2.session() as s:
        s.execute(update(ImageProductionRun).where(ImageProductionRun.run_key == key2)
                  .values(blocked_reason="capability", stages={"_restart": {"epoch": 3}}))
    assert "cap" in IP.restartable(db2, key2)["why"]
    with db2.session() as s:
        s.execute(update(ImageProductionRun).where(ImageProductionRun.run_key == key2)
                  .values(status="ready_for_owner_review", stages={}))
    assert not IP.restartable(db2, key2)["restartable"]
    try:
        IP.restart(db2, key2, follow=follow, by="")
        raise AssertionError("an anonymous restart was accepted")
    except ValueError:
        pass
    assert ImageCandidate  # imported for the schema


# ---- 4. approved frames into ListingAsset, re-certified --------------------------------------

def _ready_run(db):
    from brambleloop.visual import image_production as IP

    gen = O.StubGenerator()
    follow, _ = O.drain(db, generator=gen, judges=O.StubJudges())
    IP.trigger(follow, slug=CLOUD, version="1.2.0", release=O.RELEASE)
    O.drain(db, generator=gen, judges=O.StubJudges())
    key = IP.run_key(CLOUD, "1.2.0", O.RELEASE)
    assert IP.get_run(db, key)["state"] == "ready_for_owner_review"
    return key


def _asset_rows(db):
    from sqlalchemy import select

    from brambleloop.core.models import ListingAsset

    with db.session() as s:
        return [(r.position, r.role, r.asset_class) for r in s.scalars(select(ListingAsset))]


def test_persist_never_bypasses_f852_or_the_publication_gates():
    from sqlalchemy import update

    from brambleloop.visual import gallery_persist as GP
    from brambleloop.visual import image_production as IP
    from brambleloop.visual.image_records import ImageProductionRun

    db = O.make_db()
    key = _ready_run(db)
    assert GP.persist_approved(db, key)["persisted"] is False          # not approved
    got = IP.approve(db, key, decided_by="owner:test")
    assert got["approved"] is False and any("F-852" in b for b in got["blockers"])
    # Even a run forced into approved_for_publication is re-verified and refused: nothing
    # is written while F-852 holds.
    with db.session() as s:
        s.execute(update(ImageProductionRun).where(ImageProductionRun.run_key == key)
                  .values(status="approved_for_publication"))
    out = GP.persist_approved(db, key, judges=O.StubJudges())
    assert out["persisted"] is False and any("F-852" in b for b in out["blockers"]), out
    assert _asset_rows(db) == []


def test_written_generated_frames_are_rejudged_by_listing_set_and_never_certified():
    from brambleloop.visual import gallery_persist as GP

    db = O.make_db()
    frames = [{"position": 2, "role": "lifestyle", "job": "LIFESTYLE", "candidate_id": 1,
               "sha256": "c" * 64}]
    w = GP.write_frames(db, CLOUD, "1.2.0", frames, run_key="k")
    assert w["written"] == [2] and _asset_rows(db) == [(2, "lifestyle", "AI_LIFESTYLE_CONCEPT")]
    again = GP.write_frames(db, CLOUD, "1.2.0", frames, run_key="k")
    assert again["kept"] == [2] and again["written"] == []
    other = GP.write_frames(db, CLOUD, "1.2.0", [{**frames[0], "sha256": "d" * 64}],
                            run_key="k")
    assert other["refused"] and other["written"] == []                  # never overwritten
    cert = GP.recertify(db, CLOUD, "1.2.0", positions=[2])
    assert cert["blocks_release"] is True, cert and cert["certificate"] is False
    if cert["generated_frames_judged"]:
        f = cert["generated_frames"][0]
        assert f["may_export"] is False and "F-852" in f["why"], f


# ---- 5. Command Center gallery card and wardrobe editor --------------------------------------

def test_gallery_card_shows_images_and_keeps_three_decisions_apart():
    from brambleloop.visual import image_production as IP

    db = O.make_db()
    key = _ready_run(db)
    card = IP.gallery_card(db, key)
    gen = [f for f in card["frames"] if f["image_url"]]
    assert gen and all(f["image_url"].startswith("/api/cc/images/candidates/") for f in gen)
    assert all(f["label"].startswith("AI-generated") for f in gen)
    d = card["decisions"]
    assert set(d) == {"visual_approval", "technical_certification", "publication_authorization"}
    assert d["visual_approval"]["state"] == "not_recorded"
    assert d["visual_approval"]["affects_gates"] is False
    assert d["publication_authorization"]["state"] == "not_available"
    assert any("F-852" in b for b in d["publication_authorization"]["blockers"])
    tech_before = d["technical_certification"]["state"]
    rec = IP.record_visual_approval(db, key, decided_by="owner:test", approved=True,
                                    note="lovely light")
    assert rec["recorded"] and rec["visual_approval"]["is_publication_authorization"] is False
    card2 = IP.gallery_card(db, key)
    assert card2["decisions"]["visual_approval"]["state"] == "approved"
    assert card2["decisions"]["technical_certification"]["state"] == tech_before
    assert card2["decisions"]["publication_authorization"]["state"] == "not_available"
    assert IP.get_run(db, key)["state"] == "ready_for_owner_review"     # nothing moved
    # the publication decision keeps the visual record and is still refused
    IP.approve(db, key, decided_by="owner:test")
    run = IP.get_run(db, key)
    assert run["owner_decision"]["visual"]["approved_look"] is True
    assert run["state"] == "ready_for_owner_review"


def test_cc_routes_and_view_for_the_card_restart_and_wardrobe():
    from brambleloop.app.command_center.api import make_router

    paths = {(r.path, tuple(sorted(r.methods or ()))) for r in make_router(None).routes}
    names = {p for p, _ in paths}
    assert {"/api/cc/images/runs/card", "/api/cc/images/candidates/{candidate_id}/image",
            "/api/cc/images/runs/visual-approval", "/api/cc/images/runs/restart",
            "/api/cc/wardrobe", "/api/cc/images/outfits/action"} <= names
    view = (ROOT / "src/brambleloop/app/command_center/static/js/views/images.js").read_text()
    for needle in ("1. Visual approval", "2. Technical certification",
                   "3. Publication authorization", 'h("img"', "Restart at", "Wardrobe",
                   "Set outfit reference"):
        assert needle in view, needle
    assert "innerHTML" not in view
    api = (ROOT / "src/brambleloop/app/command_center/static/js/api.js").read_text()
    assert "images/runs/visual-approval" in api and "/wardrobe" in api


def test_wardrobe_editor_and_outfit_reference():
    from brambleloop.visual import candidate_gates as CG
    from brambleloop.visual import image_production as IP
    from brambleloop.visual import outfits

    db = O.make_db()
    c = laura_cand(db)
    w = outfits.wardrobe_editor(db)
    assert [o["outfit_id"] for o in w["outfits"]] == ["sage-cardigan-01"]
    assert w["outfits"][0]["distinctness"]["status"] == "PASS"
    assert set(w["catalogue"]) == set(w["slots"]) and w["max_similarity"] == 0.6
    try:
        outfits.set_approved_reference(db, "sage-cardigan-01", c.get("sha256") or "e" * 64,
                                       by="owner:test")
        raise AssertionError("an unjudged image became the outfit reference")
    except outfits.OutfitRefused:
        pass
    judges = CG.RealJudges(db, vision=Recorded(*FUNDED), references=REFS)
    v = CG.evaluate(db, c, judges=judges, record_outfit_use=False)
    assert v["checks"]["outfit_consistency"]["status"] == "PASS"
    IP.record_candidate(db, c, v, method="autonomous", run="r")
    got = outfits.set_approved_reference(db, "sage-cardigan-01", v["sha256"], by="owner:test")
    assert got["approved_reference"] == v["sha256"]
    from brambleloop.visual import canonical

    try:
        outfits.set_approved_reference(db, "sage-cardigan-01", canonical.FACE_SHA256,
                                       by="owner:test")
        raise AssertionError("a canonical identity reference became an outfit reference")
    except outfits.OutfitRefused:
        pass


# ---- 6. learning: taxonomy end to end, improvements only through the Learn path -------------

def test_wardrobe_codes_flow_from_the_judge_to_learning_and_a_league_challenger():
    from brambleloop.visual import candidate_gates as CG
    from brambleloop.visual import image_learning as L
    from brambleloop.visual import image_production as IP

    db = O.make_db()
    gen = TF.FlatLayGenerator(CLOUD)
    judges = CG.RealJudges(db, vision=Recorded(
        "laura_match_a", "outfit_reference_carryover", "anatomy_ok", "realism_ok",
        "item_same", "region_ok"), references=REFS)
    before = IP.prompt_version(db)
    key = _start(db, gen, judges)
    run = IP.get_run(db, key)
    assert run["state"] == "blocked", run
    tax = L.taxonomy(db, slug=CLOUD)
    assert tax["unclassified"] == [], tax["unclassified"]
    wardrobe = tax["by_owner"].get("wardrobe:wardrobe") or {}
    assert wardrobe.get("REFERENCE_CLOTHING_CARRYOVER", 0) >= 3, tax
    assert tax["by_owner"]["gate"].get("outfit_consistency", 0) >= 3
    reps = [r for r in gen.repairs if r]
    assert reps and any("REPLACE ALL clothing" in " ".join(
        n for d in r["directives"] for n in d.get("negatives", [])) for r in reps)
    prop = L.propose_brief_challenger(db, min_count=3, slug=CLOUD)
    assert prop["registered"] and "REFERENCE_CLOTHING_CARRYOVER" in prop["codes"]
    assert prop["promoted"] is False
    assert IP.prompt_version(db) == before            # nothing changed until the league says
    again = L.propose_brief_challenger(db, min_count=3, slug=CLOUD)
    assert again["registered"] is False               # identical challenger: no new version
    # a code nobody registered would be visible, not silently counted
    assert L.owner_of("SOMETHING_NEW") is None
    assert L.owner_of("WARDROBE_REPETITION") == "wardrobe:wardrobe"
    assert L.owner_of("INVENTED_EDGING").startswith("product_truth:")


def test_wardrobe_repetition_seen_by_the_judge_repicks_the_outfit():
    from brambleloop.visual import candidate_gates as CG
    from brambleloop.visual import image_production as IP
    from brambleloop.visual import outfits

    db = O.make_db()
    O.approved_outfit(db, "oat-jumper-02")
    outfits.reserve(db, "oat-jumper-02", "winter-village-graphghan")
    O.approved_outfit(db, "sage-cardigan-01")
    outfits.reserve(db, "sage-cardigan-01", CLOUD)
    gen = TF.FlatLayGenerator(CLOUD)
    judges = CG.RealJudges(db, vision=Recorded(
        "laura_match_a", "outfit_other_listing", "anatomy_ok", "realism_ok", "item_same",
        "region_ok"), references=REFS)
    key = _start(db, gen, judges)
    run = IP.get_run(db, key)
    old = outfits.get(db, "sage-cardigan-01")
    assert old["approval_state"] == "retired" and run["outfit_id"] != "sage-cardigan-01", run
    learn = IP.learning_summary(db, slug=CLOUD)
    assert learn["failure_categories"].get("WARDROBE_REPETITION", 0) >= 1


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
