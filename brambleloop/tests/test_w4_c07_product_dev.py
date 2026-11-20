"""W4-C07: product development and certification (F-114, F-675, F-678, F-758, F-759,
F-083, F-876, F-848, F-857, F-855; F-113 is W4-AGENTS C3's, tested in test_w4_c3.py).

Product Truth first: CIR -> compiler -> certificate; nothing certifies without its gates; no
model guesses an instruction; no paid render is made (CA$0). F-464 is proposed separately."""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import importlib.util
import json
import shutil
import sys
import tempfile
from dataclasses import replace
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests")]

import numpy as np  # noqa: E402
from sqlalchemy import select  # noqa: E402

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import Incident, PatternVersion, Product  # noqa: E402
from brambleloop.products.builder import CATALOGUE, build  # noqa: E402


def _db():
    from brambleloop.agents.registry import Registry

    db = Database("sqlite://")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _legacy(db, *, sc=16.0, slug="legacy-blanket"):
    cir = build(CATALOGUE["cloudline-baby-blanket"])
    cir = replace(cir, slug=slug, gauge=replace(cir.gauge, stitches_per_10cm=sc,
                                                rows_per_10cm=round(sc * 1.1, 1)))
    with db.session() as s:
        p = Product(slug=slug, title="Legacy blanket", status="certified")
        s.add(p)
        s.flush()
        s.add(PatternVersion(product_id=p.id, version=cir.version, cir_json=cir.to_dict(),
                             certified=True, release_hash=f"{slug}-r"))
    return cir


# ---- F-114 -----------------------------------------------------------------------------------

def test_f114_worthy_legacy_goes_through_band_compiler_twin_reverse_and_release_chain():
    from brambleloop.products import reengineer as RE

    db = _db()
    legacy = _legacy(db)
    assert RE.plan(db, "legacy-blanket",
                   salvage={"recommendation": "retire_recommended"})["state"] == "NOT_WORTHY"
    p = RE.plan(db, "legacy-blanket", salvage={"recommendation": "rescue_candidate"})
    assert p["state"] == RE.READY, p
    assert p["checks"]["gauge"]["band"] == [11.0, 14.0]
    assert p["checks"]["gauge"]["derived"] == 12.5          # 16 sc/10cm: worsted cannot hold it
    assert p["checks"]["compiler"]["ok"] and p["checks"]["reverse"]["ok"]
    w_old, w_new = p["checks"]["twin"]["legacy_cm"][0], p["checks"]["twin"]["reengineered_cm"][0]
    assert w_new > w_old                                      # the size change is stated
    assert p["version"] == "1.3.0" and p["from_version"] == legacy.version
    with db.session() as s:                                   # the legacy release is untouched
        assert s.scalar(select(PatternVersion)).cir_json["gauge"]["stitches_per_10cm"] == 16.0
    kept = _legacy(db, sc=12.0, slug="in-band")
    kp = RE.plan(db, "in-band", salvage={"recommendation": "rescue_candidate"})
    assert kp["checks"]["gauge"]["kept"] == 12.0 and kept.gauge.stitches_per_10cm == 12.0

    # The runtime path: salvage -> cir.reengineer -> cir.compile (which runs gate.certify).
    from brambleloop.agents.registry import Registry
    from brambleloop.core.models import Job, Phase
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime import pipeline  # noqa: F401
    from brambleloop.runtime.worker import JobContext, handlers

    from brambleloop.core.models import OwnerAction
    from brambleloop.runtime import engineering_ops as EO

    # The owner chooses: salvage raises one card and enqueues nothing.
    card_id = EO.reengineer_card(db, ["legacy-blanket"])
    assert EO.reengineer_card(db, ["legacy-blanket"]) == card_id          # not duplicated

    def run(inputs):
        job = JobQueue(db).enqueue("crochet_engineer", "cir.reengineer", inputs)
        Registry(db).authorize("crochet_engineer", "cir.reengineer")
        return handlers.get("cir.reengineer")(JobContext(job=job, db=db, queue=JobQueue(db),
                                                         registry=Registry(db),
                                                         phase=Phase.SHADOW))

    saved = RE.plan
    RE.plan = lambda db_, slug: saved(db_, slug, salvage={"recommendation": "rescue_candidate"})
    try:
        assert run({"slugs": ["legacy-blanket"]})["ran"] is False            # no choice
        assert run({"slugs": ["legacy-blanket"],
                    "owner_action_id": card_id})["ran"] is False             # undecided
        with db.session() as s:
            s.get(OwnerAction, card_id).done = True
        out = run({"slugs": ["legacy-blanket"], "owner_action_id": card_id})
    finally:
        RE.plan = saved
    assert out["sent_to_release_chain"] == 1
    with db.session() as s:
        compiles = [j for j in s.scalars(select(Job).where(Job.job_type == "cir.compile"))]
        assert len(compiles) == 1 and compiles[0].inputs["cir"]["version"] == "1.3.0"
        assert not list(s.scalars(select(PatternVersion).where(
            PatternVersion.version == "1.3.0")))                  # not certified here


# ---- F-675 -----------------------------------------------------------------------------------

def test_f675_structural_truth_needs_every_property_from_product_truth():
    from brambleloop.quality import structural_truth as ST

    cir = build(CATALOGUE["cloudline-baby-blanket"])
    exp = ST.expected(cir)
    model = {"components": exp["components"], "construction": dict(exp["construction"]),
             "rows": {k: list(v) for k, v in exp["rows"].items()},
             "colours": {k: list(v) for k, v in exp["colours"].items()},
             "dimensions_cm": {k: list(v) for k, v in exp["dimensions_cm"].items()},
             "silhouette_iou": 0.995,
             "drape": {k: "PASS" for k in ST.DRAPE_LOCKS}}
    assert ST.assess(cir, model)["state"] == "STRUCTURALLY_TRUE"
    comp = exp["components"][0]
    off = json.loads(json.dumps(model))
    off["rows"][comp][3] += 1
    bad = ST.assess(cir, off)
    assert bad["state"] == "NOT_TRUE" and {"stitch_structure", "shaping"} <= set(bad["failed"])
    undraped = {**model, "drape": {}}
    assert ST.assess(cir, undraped)["state"] == "UNKNOWN"          # never PASS by omission
    wide = json.loads(json.dumps(model))
    wide["dimensions_cm"][comp][0] *= 1.05
    assert "dimensions" in ST.assess(cir, wide)["failed"]


# ---- F-678 -----------------------------------------------------------------------------------

def test_f678_the_benchmark_replays_end_to_end_against_its_freeze():
    from brambleloop.quality import benchmark_e2e as BE

    r = BE.run()
    assert r["state"] == "HOLDS", r["regressed"]
    st = r["stages"]
    assert st["pattern"]["status"] == st["cir"]["status"] == st["reference"]["status"] == "PASS"
    assert st["ad_image"]["new_generation"] == "SKIPPED_NEEDS_BUDGET"
    assert st["comparison"]["status"] == "UNKNOWN"
    with tempfile.TemporaryDirectory() as tmp:
        bench = Path(tmp) / "bench2"
        (bench / "out").mkdir(parents=True)
        for f in ("product_truth.py", "reference.py", "star_identity.py"):
            shutil.copy(BE.DEFAULT_DIR / f, bench / f)
        for f in ("product_truth.json", "bench2_manifest.json", "bench2_gate.json",
                  "private_comparison.json"):
            shutil.copy(BE.DEFAULT_DIR / "out" / f, bench / "out" / f)
        m = json.loads((bench / "out" / "bench2_manifest.json").read_text())
        m["cir_fingerprint"] = "000000000000"
        (bench / "out" / "bench2_manifest.json").write_text(json.dumps(m))
        moved = BE.run(bench, build_reference=False)
        assert moved["state"] == "REGRESSION" and moved["regressed"] == ["cir"]
        assert BE.run(Path(tmp) / "absent")["state"] == "UNKNOWN"


# ---- F-758 -----------------------------------------------------------------------------------

def test_f758_a_faithfully_reproduced_reference_defect_is_fixed_upstream():
    from brambleloop.quality import reference_defects as RD

    db = _db()
    up = RD.classify({"kind": "button_count", "slug": "cardigan"}, {"button_count": "FAIL"})
    assert up["class"] == RD.UPSTREAM and up["tune_model"] is False
    gen = RD.classify({"kind": "hood_shape", "slug": "cardigan"}, {"hood_shape": "PASS"})
    assert gen["class"] == RD.GENERATOR and RD.record(db, gen) is None
    unk = RD.classify({"kind": "drape", "slug": "cardigan"}, {})
    assert unk["class"] == RD.UNKNOWN and unk["tune_model"] is False
    sig = RD.record(db, up, image_ref="gen-7")
    RD.record(db, up, image_ref="gen-8")                           # one incident, not two
    with db.session() as s:
        assert len(list(s.scalars(select(Incident).where(Incident.signature == sig)))) == 1
    assert RD.tuning_allowed(db, "cardigan", "button_count") is False
    try:
        RD.resolve(db, "cardigan", "button_count", reference_fix="ref@2", regression_test="",
                   regenerated_ref="gen-9")
        raise AssertionError("closed without a regression test")
    except RD.LoopRefused:
        pass
    RD.resolve(db, "cardigan", "button_count", reference_fix="ref@2",
               regression_test="tests/test_bench2.py::test_buttons", regenerated_ref="gen-9")
    assert RD.tuning_allowed(db, "cardigan", "button_count")


# ---- F-759 -----------------------------------------------------------------------------------

def test_f759_a_stitch_family_is_promoted_only_when_wrong_alternatives_are_rejected():
    from brambleloop.quality import stitch_benchmarks as SB

    star = SB.promotion_gate("star")
    assert star["state"] == "PROMOTABLE", star
    assert set(star["negatives"]) >= {"half_offset_checker", "hdc_rows", "seed", "knit",
                                      "double_gauge"}
    assert all(v != "PASS" for v in star["negatives"].values())
    assert SB.promotion_gate("bobble")["state"] == "UNSUPPORTED"
    assert SB.promotion_gate("cable")["promotable"] is False
    saved = SB.FAMILIES["star"]

    def lenient():
        f = saved()
        return {**f, "validate": lambda g: "PASS"}               # a validator that accepts all
    SB.FAMILIES["star"] = lenient
    try:
        blocked = SB.promotion_gate("star")
    finally:
        SB.FAMILIES["star"] = saved
    assert blocked["state"] == "BLOCKED" and "seed" in blocked["accepted_negatives"]


# ---- F-083 -----------------------------------------------------------------------------------

def test_f083_observed_make_time_replaces_the_assumed_speed_with_bounds():
    from brambleloop.quality import make_time as MT

    recs = [{"product_class": "blanket", "skill": "beginner", "hours": h,
             "estimated_hours": 20.0} for h in (24, 26, 30, 32, 40, 28)]
    recs.append({"product_class": "blanket", "skill": "beginner", "hours": None,
                 "estimated_hours": 20.0})
    d = MT.distributions(recs)
    g = d["groups"]["blanket/beginner"]
    assert g["state"] == "MEASURED" and g["n"] == 6 and d["skipped_incomplete"] == 1
    assert g["ratio"]["p10"] <= g["ratio"]["p50"] <= g["ratio"]["p90"]
    assert MT.distributions(recs[:3])["groups"]["blanket/beginner"]["state"] == "UNMEASURED"
    kw = dict(event="christmas", event_date=date(2026, 12, 25), today=date(2026, 10, 1),
              estimated_hours=20.0, product_class="blanket", skill="beginner")
    measured = MT.runway(records=recs, **kw)
    assumed = MT.runway(records=[], **kw)
    assert measured["basis"] == "MEASURED" and assumed["basis"] == "ASSUMED"
    ll = measured["latest_launch"]
    assert ll["pessimistic"] <= ll["typical"] <= ll["optimistic"]
    assert measured["make_hours"]["typical"] == round(20.0 * g["ratio"]["p50"], 2)


# ---- F-876 -----------------------------------------------------------------------------------

def test_f876_physical_evidence_is_requested_only_for_what_it_can_prove():
    from brambleloop.quality import evidence_request as ER

    for prop in ("stitch_counts", "written_matches_cir"):
        try:
            ER.request(prop)
            raise AssertionError(f"{prop} was requested from a tester")
        except ER.RequestRefused as exc:
            assert "deterministically" in str(exc)
    try:
        ER.request("everything")
        raise AssertionError("a vague request was made")
    except ER.RequestRefused:
        pass
    r = ER.requests_for({"yardage", "drape", "stitch_counts"},
                        known={"drape": "RESOLVED"}, product_slug="p")
    assert [x["property"] for x in r["requests"]] == ["yardage"]
    assert "grams" in r["requests"][0]["measure"]
    assert {x["property"] for x in r["refused"]} == {"drape", "stitch_counts"}


# ---- F-848 -----------------------------------------------------------------------------------

def test_f848_the_rehearsal_starts_at_the_opportunity_and_the_design():
    spec = importlib.util.spec_from_file_location("shadow_rehearsal",
                                                  ROOT / "scripts" / "shadow_rehearsal.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    from brambleloop.products import launch0

    cand = launch0.candidate("cloudline-baby-blanket")
    cir = launch0.cir_for(cand.variants[0].build)
    rec = m.Recorder()
    m.record_upstream(rec, cand, cir)
    steps = {s["step"]: s for s in rec.steps}
    assert list(steps) == ["opportunity", "design"]
    assert steps["design"]["outcome"] == m.PASS
    assert steps["design"]["db_proof"]["cir_fingerprint"] == cir.fingerprint
    assert steps["opportunity"]["outcome"] in (m.PASS, m.BLOCKED)
    assert "opportunity" in Path(ROOT / "scripts" / "shadow_rehearsal.py").read_text() \
        .split('required = [')[1].split("]")[0]


# ---- F-857 -----------------------------------------------------------------------------------

def test_f857_v2_graduates_only_on_a_blind_brambleloop_original():
    from brambleloop.quality import visual_graduation as VG

    cir = build(CATALOGUE["cloudline-baby-blanket"])
    prov = {"original": True, "sources": ["products/builder.py"], "finished_photos": []}
    refs = [{"ref": "render.png", "kind": "cir_render"}, {"ref": "mask.png", "kind": "mask"}]
    ok = VG.graduate(cir, prov, refs, [{"ref": "gen-1", "status": "PASS"}])
    assert ok["state"] == "GRADUATED"
    bench = replace(cir, authored="benchmark")
    assert VG.graduate(bench, prov, refs, [{"ref": "g", "status": "PASS"}])["state"] == \
        "NOT_GRADUATED"
    photo = refs + [{"ref": "designer.jpg", "kind": "finished_photo"}]
    out = VG.graduate(cir, prov, photo, [{"ref": "g", "status": "PASS"}])
    assert out["state"] == "NOT_GRADUATED" and "finished_photo" in out["reasons"][0]
    seen = {**prov, "finished_photos": ["sample.jpg"]}
    assert VG.graduate(cir, seen, refs, [{"ref": "g", "status": "PASS"}])["state"] == \
        "NOT_GRADUATED"
    assert VG.graduate(cir, prov, refs, [{"ref": "g", "status": "FAIL"}])["state"] == \
        "NOT_GRADUATED"


# ---- F-855 -----------------------------------------------------------------------------------

def test_f855_material_enhancement_only_with_protected_boundaries_and_revalidation():
    from brambleloop.quality import material_enhancement as ME

    rng = np.random.default_rng(0)
    H, W = 120, 160
    before = np.full((H, W), 60.0)
    sil = np.zeros((H, W), bool)
    sil[20:100, 30:130] = True
    fabric = 200.0 + 30.0 * ((np.add.outer(np.arange(H), np.arange(W)) // 6) % 2)
    before[sil] = fabric[sil]
    gy, gx = np.gradient(before)
    edges = (np.hypot(gx, gy) > 5) & sil
    band = ME._dilate(edges, ME.BAND_PX)
    fuzz = before.copy()
    free = sil & ~band
    fuzz[free] += rng.normal(0, 4, free.sum())                     # fibre between boundaries
    ok = ME.check(before, fuzz, sil, edges, revalidate=lambda a: "PASS")
    assert ok["state"] == "ALLOWED", ok
    moved = np.roll(fuzz, 3, axis=1)                                 # the geometry slid
    assert ME.check(before, moved, sil, edges, revalidate=lambda a: "PASS")["state"] == \
        "REFUSED"
    failed = ME.check(before, fuzz, sil, edges, revalidate=lambda a: "FAIL")
    assert failed["state"] == "REFUSED" and failed["revalidation"] == "FAIL"
    unk = ME.check(before, fuzz, sil, edges)
    assert unk["state"] == "REFUSED" and unk["revalidation"] == "UNKNOWN"


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("OK  ", n)  # run_tests.sh counts lines beginning OK
