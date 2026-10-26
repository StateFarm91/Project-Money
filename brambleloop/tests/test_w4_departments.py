"""W4-AGENTS department batch 1: Quality & Compliance agents run real work.

`validator`, `asset_truth`, `policy` and `quality_director` re-verify already-certified releases
with the certificate's own deterministic stages. They are never a verdict path: the certificate
is unchanged, nothing is blocked, and a disagreement is one non-halting P2 incident.

Run: cd brambleloop && PYTHONPATH=src:tests $PY tests/test_w4_departments.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (Incident, Job, Listing, PatternVersion, Phase,  # noqa: E402
                                     Product)
from brambleloop.products import launch0  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401
from brambleloop.runtime import quality_ops  # noqa: E402
from brambleloop.runtime.worker import CADENCES, JobContext, handlers  # noqa: E402

_TMP = tempfile.mkdtemp(prefix="w4dept_")
_N = [0]


def _db(cir=None, listing=None):
    _N[0] += 1
    db = Database(f"sqlite:///{_TMP}/d{_N[0]}.db")
    db.create_all()
    Registry(db).seed_defaults()
    if cir is not None:
        with db.session() as s:
            p = Product(slug=cir.slug, title=cir.title, status="certified")
            s.add(p)
            s.flush()
            s.add(PatternVersion(product_id=p.id, version=cir.version, cir_json=cir.to_dict(),
                                 certified=True, release_hash="r" * 64,
                                 certificate={"granted": True}))
            if listing:
                s.add(Listing(product_slug=cir.slug, version=cir.version, **listing))
    return db


def _cir():
    key = sorted(launch0.BUILDERS)[0]
    return launch0.cir_for(key)


def _run(db, agent, jt, inputs):
    job = JobQueue(db).enqueue(agent, jt, inputs)
    return handlers.get(jt)(JobContext(job=job, db=db, queue=JobQueue(db),
                                       registry=Registry(db), phase=Phase.SHADOW))


def test_every_quality_agent_now_has_a_handler_and_a_wake():
    for jt in ("gate.quality", "cir.twin", "cir.reverse", "gate.asset_truth", "gate.policy"):
        assert handlers.get(jt) is not None, jt
    assert ("quality_reverify", "quality_director", "gate.quality", 86400) in CADENCES
    reg = Registry(_db())
    for agent, jt in [
            ("validator", "cir.twin"), ("validator", "cir.reverse"),
            ("asset_truth", "gate.asset_truth"), ("policy", "gate.policy"),
            ("quality_director", "gate.quality")]:
        reg.authorize(agent, jt)


def test_certified_release_reverifies_clean_and_changes_nothing():
    cir = _cir()
    db = _db(cir)
    plan = _run(db, "quality_director", "gate.quality", {})
    assert plan["releases"] == 1 and plan["queued"] == 4
    again = _run(db, "quality_director", "gate.quality", {})
    assert again["queued"] == 0                          # idempotent per release per day
    with db.session() as s:
        jobs = list(s.scalars(select(Job).where(Job.job_type.in_(list(quality_ops.CHECKS)))))
    assert {(j.agent, j.job_type) for j in jobs} == {(a, t) for t, a in
                                                       quality_ops.CHECKS.items()}
    for j in jobs:
        out = handlers.get(j.job_type)(JobContext(job=j, db=db, queue=JobQueue(db),
                                                  registry=Registry(db), phase=Phase.SHADOW))
        if j.job_type == "gate.policy":
            assert out["ran"] is False and "no drafted listing" in out["why"]
            continue
        assert out["ok"] is True, (j.job_type, out)
        assert out["certificate_changed"] is False and out["incident"] is None
    with db.session() as s:
        pv = s.scalar(select(PatternVersion))
        assert pv.certified is True and pv.certificate == {"granted": True}


def test_a_drifted_release_raises_one_non_halting_incident():
    cir = _cir()
    db = _db(cir, listing={"title": "Amigurumi teddy bear in the round", "description":
                           "A Disney-style blanket, always 50% off.",
                           "tags": ["x"], "price_cad": 6.0})
    real = quality_ops.reverify
    quality_ops.reverify = lambda db_, check, slug, version: {
        "check": check, "ok": False, "problems": ["SIMULATED: writer drift"]}
    try:
        a = _run(db, "validator", "cir.reverse", {"slug": cir.slug, "version": cir.version})
        b = _run(db, "validator", "cir.reverse", {"slug": cir.slug, "version": cir.version})
    finally:
        quality_ops.reverify = real
    assert a["ok"] is False and a["incident"] and b["incident"] is None
    with db.session() as s:
        incs = list(s.scalars(select(Incident)))
        assert len(incs) == 1 and incs[0].severity == "P2"
        assert incs[0].halts_publication is False and incs[0].report_count == 2
        assert s.scalar(select(PatternVersion)).certified is True
    # the real policy check reads the drafted listing and finds its banned claims
    pol = real(db, "gate.policy", cir.slug, cir.version)
    assert pol["ok"] is False and pol["problems"], pol


def test_laura_and_the_coo_may_delegate_the_quality_sweep():
    from brambleloop.autonomy import charters
    from brambleloop.laura.agency import followon

    assert charters.validate() == []
    assert followon.green_allowed("product_truth", "gate.quality") is None


def test_photography_is_never_requested_for_a_slug_with_no_cir():
    """Batch 2 (E-12): production ran assets.owned_photography 10 times in 32 h on
    `market-basket-trio`, a retired concept slug with no CIR -- a daily no-op."""
    from brambleloop.core.models import BenchmarkListing
    from brambleloop.intel import mission_runtime as MR, pods
    from brambleloop.products.builder import for_slug

    assert for_slug("market-basket-trio") is None
    real_slug = next(sl for sl in launch0.LAUNCH0_SLUGS if for_slug(sl) is not None)
    db = _db()
    pod = next(k for k in pods.POD_KEYS if k != pods.UNCLASSIFIED)
    with db.session() as s:
        s.add(BenchmarkListing(benchmark_key="t", listing_ref="1", pod=pod))
    saved = (MR._our_dims, MR._their_dims, pods.Director.standing)
    MR._our_dims = lambda db_, pod_: {"_slugs": ["market-basket-trio", real_slug]}
    MR._their_dims = lambda db_, pod_, key=None: {}
    pods.Director.standing = lambda self, ours, theirs: {
        d: (pods.BEHIND if d == "photography_coverage" else pods.UNKNOWN)
        for d in pods.DIMENSIONS}
    asked = []
    try:
        MR.company_standing(db, enqueue=lambda agent, jt, inputs, **kw: asked.append(
            inputs["slug"]))
    finally:
        MR._our_dims, MR._their_dims, pods.Director.standing = saved
    assert asked == [real_slug], asked


def _bad_panel(width=50):
    """A concept_to_cir panel whose width the 4-stitch repeat does not divide."""
    from brambleloop.runtime.pipeline import Concept, concept_to_cir

    return concept_to_cir(Concept(slug="revise-fixture", title="Revise Fixture Panel",
                                  category="coaster", stitch_repeat=[("sc", 2), ("dc", 2)],
                                  width_stitches=width, rows=8,
                                  colors={"A": "cream", "B": "sage"}))


def test_a_failed_compile_is_revised_once_and_goes_back_through_the_compiler():
    from brambleloop.cir.compiler import compile_cir
    from brambleloop.runtime import engineering_ops as EO

    bad = _bad_panel(50)
    assert not compile_cir(bad).ok
    db = _db()
    out = _run(db, "validator", "cir.compile", {"cir": bad.to_dict()})
    assert out["compiled"] is False and out["revise_job"], out
    with db.session() as s:
        rev = s.get(Job, out["revise_job"])
    assert rev.agent == "crochet_engineer" and rev.job_type == "cir.revise"
    res = handlers.get("cir.revise")(JobContext(job=rev, db=db, queue=JobQueue(db),
                                                registry=Registry(db), phase=Phase.SHADOW))
    assert res["revised"] and res["detail"]["width_to"] == 52, res
    with db.session() as s:
        comp = s.scalars(select(Job).where(Job.job_type == "cir.compile",
                                           Job.id != rev.id)).all()
    nxt = [j for j in comp if j.inputs.get("revision") == 1]
    assert len(nxt) == 1
    from brambleloop.cir.model import CIR

    assert compile_cir(CIR.from_dict(nxt[0].inputs["cir"])).ok
    # a second failure is not revised again: the bound is one revision
    again = _run(db, "validator", "cir.compile", {"cir": bad.to_dict(), "revision": 1})
    assert again["revise_job"] is None
    assert handlers.get("cir.revise") is not None and EO.MAX_REVISIONS == 1
    Registry(db).authorize("crochet_engineer", "cir.revise")


def test_i3_a_negative_revision_input_cannot_lift_the_bound():
    bad = _bad_panel(50)
    db = _db()
    first = _run(db, "validator", "cir.compile", {"cir": bad.to_dict(), "revision": -5})
    assert first["revise_job"]
    with db.session() as s:
        assert s.get(Job, first["revise_job"]).inputs["revision"] == 0
    res = _run(db, "crochet_engineer", "cir.revise", {"cir": bad.to_dict(), "revision": -5})
    assert res.get("revised"), res
    with db.session() as s:
        nxt = s.scalars(select(Job).where(Job.job_type == "cir.compile")).all()
        assert all(j.inputs.get("revision") in (None, -5, 1) for j in nxt), \
            [j.inputs.get("revision") for j in nxt]
        assert any(j.inputs.get("revision") == 1 for j in nxt)


def test_an_unrepairable_failure_is_recorded_not_guessed():
    from brambleloop.cir.model import Op
    from brambleloop.core.models import AuditLog

    bad = _bad_panel(50)
    bad.components[0].rows[2].ops.append(Op("dc", 3))   # breaks the uniform-panel shape
    db = _db()
    res = _run(db, "crochet_engineer", "cir.revise", {"cir": bad.to_dict()})
    assert res["revised"] is False and res["unrepairable"] and res["codes"]
    with db.session() as s:
        assert s.scalar(select(AuditLog.id).where(
            AuditLog.action == "cir.revise_unrepairable")) is not None
        assert not s.scalars(select(Job).where(Job.job_type == "cir.compile")).all()


def test_competitor_snapshot_is_aggregates_only_and_never_copies_content():
    from brambleloop.core.models import BenchmarkListing, OperatingReading
    from brambleloop.runtime import intel_ops

    db = _db()
    empty = _run(db, "market_radar", "radar.competitor_snapshot", {})
    assert empty["ran"] is False                      # nothing observed: honest no-op
    secret = "Rival Exact Title With Their Words"
    with db.session() as s:
        for i, price in enumerate((8.0, 10.0, 0.0)):
            s.add(BenchmarkListing(benchmark_key="mjs", listing_ref=str(i), title=secret,
                                   url="https://example.invalid/rival", pod="home",
                                   price_cad=price, on_sale=(i == 0), media_count=5 + i,
                                   product_type="basket", seasonal="Christmas" if i else ""))
    out = _run(db, "market_radar", "radar.competitor_snapshot", {})
    assert out["groups"] == 1 and out["listings"] == 3 and out["network_calls"] == 0
    with db.session() as s:
        snap = s.scalar(select(OperatingReading).where(
            OperatingReading.kind == intel_ops.READING)).payload
    g = snap["groups"][0]
    assert g["price_median_cad"] == 9.0 and g["price_min_cad"] == 8.0    # 0.0 = unobserved
    assert g["on_sale_share"] == round(1 / 3, 3) and g["product_types"] == {"basket": 3}
    blob = repr(snap)
    assert secret not in blob and "example.invalid" not in blob
    assert set(g) <= intel_ops.ALLOWED_KEYS
    Registry(db).authorize("market_radar", "radar.competitor_snapshot")


def test_l3_snapshot_aliases_the_benchmark_and_allowlists_inner_values():
    from brambleloop.core.models import BenchmarkListing, OperatingReading
    from brambleloop.runtime import intel_ops

    db = _db()
    shop_key = "mjs_off_the_hook_designs"
    leak = "Rivals Secret Holiday Label"
    with db.session() as s:
        for i, (season, ptype) in enumerate((("Christmas", "1234"), (leak, "basket"),
                                            ("", "their custom type"))):
            s.add(BenchmarkListing(benchmark_key=shop_key, listing_ref=f"r{i}", pod="home",
                                   price_cad=9.0, product_type=ptype, seasonal=season))
    out = _run(db, "market_radar", "radar.competitor_snapshot", {})
    assert out["groups"] == 1
    with db.session() as s:
        snap = s.scalar(select(OperatingReading).where(
            OperatingReading.kind == intel_ops.READING)).payload
    g = snap["groups"][0]
    blob = repr(snap)
    assert shop_key not in blob and "off_the_hook" not in blob and leak not in blob
    assert "their custom type" not in blob
    assert g["benchmark"] == intel_ops.benchmark_alias(shop_key)
    assert g["benchmark"] == intel_ops.benchmark_alias(shop_key)      # stable, so deltas match
    assert g["seasonal"] == {"Christmas": 1, intel_ops.OTHER: 1}
    assert g["product_types"] == {"1234": 1, "basket": 1, intel_ops.OTHER: 1}
    # the guard refuses a raw key or a foreign inner value even if the builder regressed
    for bad in ({**g, "benchmark": shop_key}, {**g, "seasonal": {leak: 1}},
                {**g, "product_types": {"their custom type": 1}}):
        try:
            intel_ops._assert_no_content({"groups": [bad]})
            raise AssertionError(f"guard passed {bad}")
        except ValueError:
            pass


def _certify(db, cir, slug=None):
    with db.session() as s:
        p = Product(slug=slug or cir.slug, title=cir.title, status="certified")
        s.add(p)
        s.flush()
        d = cir.to_dict()
        d["slug"] = slug or cir.slug
        s.add(PatternVersion(product_id=p.id, version=cir.version, cir_json=d,
                             certified=True, release_hash=(slug or cir.slug)[:60]))


def test_family_engine_groups_certified_families_and_flags_recolours():
    import copy

    from brambleloop.creative import family_engine as FE
    from brambleloop.radar.opportunity import POOL

    db = _db()
    assert _run(db, "creative_director", "creative.family_engine", {})["ran"] is False
    fam_seeds = [p for p in POOL if p.family == "nordic-forest" and not p.is_bundle]
    assert len(fam_seeds) >= 3
    a = _bad_panel(52)
    b = _bad_panel(60)                                  # a different design (width)
    _certify(db, a, fam_seeds[0].slug)
    _certify(db, b, fam_seeds[1].slug)
    recolour = copy.deepcopy(a)
    for row in recolour.components[0].rows:
        row.color = "B" if row.color == "A" else "A"
    assert FE.structure_fingerprint(recolour.to_dict()) == FE.structure_fingerprint(a.to_dict())
    _certify(db, recolour, fam_seeds[2].slug)
    _certify(db, _bad_panel(56), "a-lone-product")
    rep = FE.family_report(db)
    nf = next(f for f in rep["families"] if f["family"] == "nordic-forest")
    assert nf["distinct_designs"] == 2 and nf["bundle_ready"] is True
    assert sorted([fam_seeds[0].slug, fam_seeds[2].slug]) in nf["recolour_duplicates"]
    assert nf["amplification"] == "UNMEASURED"           # no orders: never "no", never 0
    assert "a-lone-product" in rep["single_products"]
    assert rep["portfolio_has_bundle_ready_family"] is True and rep["writes"] == 0
    assert all(m["route"].startswith("radar.score") for m in nf["next_members"])
    out = _run(db, "creative_director", "creative.family_engine", {})
    assert out["families"] >= 1 and out["recolour_duplicates"] == 1
    with db.session() as s:
        assert len(s.scalars(select(Product)).all()) == 4    # the engine created nothing


def test_f126_image_benchmark_is_superseded_with_reason_and_evidence_retained():
    from brambleloop.core.models import AuditLog
    from brambleloop.gateway import image_bench as IB

    db = _db()
    with db.session() as s:
        s.add(AuditLog(actor="creative_director", action=IB.CANDIDATE_ACTION,
                       artifact="nano-banana-2", detail={"overall": 3.9}))
    called = []
    real = IB.run
    IB.run = lambda *a, **k: called.append(1) or {}
    try:
        out = _run(db, "creative_director", "creative.image_benchmark", {})
        again = _run(db, "creative_director", "creative.image_benchmark", {"owner_rerun": 1})
    finally:
        IB.run = real
    assert called == [], "a superseded benchmark renders and spends nothing"
    assert out["superseded"] and out["by"] == "D-W4-LAURA-FLUX3" and out["evidence_retained"]
    assert out["work_done"] == 1 and again["work_done"] == 0 and again["superseded"]
    with db.session() as s:
        rows = s.scalars(select(AuditLog).where(AuditLog.action ==
                                                IB.SUPERSEDED_ACTION)).all()
        assert len(rows) == 1 and rows[0].detail["retained_count"] == 1
        assert s.scalar(select(AuditLog).where(AuditLog.action == IB.CANDIDATE_ACTION))
    assert IB.state(db)["supersession"]["by"] == "D-W4-LAURA-FLUX3"


def _frames(db, readable: int, batches: int = 3):
    from brambleloop.core.models import AuditLog
    from brambleloop.publish import model_photography
    from brambleloop.visual import identity

    morph = list(identity.MORPHOLOGY_DIMENSIONS)
    for b in range(1, batches + 1):
        job = JobQueue(db).enqueue("publishing", "assets.model_photography", {"b": b}).id
        dims = {d: "match" for d in identity.FACE_DIMENSIONS}
        dims.update({d: ("match" if i < readable else "unmeasurable")
                     for i, d in enumerate(morph)})
        with db.session() as s:
            s.add(AuditLog(actor="publishing", action=model_photography.ACTION, job_id=job,
                           detail={"identity": {"dimensions": dims}}))


def test_f218_repeated_near_threshold_morphology_opens_an_incident_though_each_frame_passed():
    from brambleloop.core.models import Incident
    from brambleloop.visual import drift_series as DS, identity

    db = _db()
    _frames(db, readable=identity.MIN_MEASURABLE["morphology"])   # each passes at the floor
    out = DS.run(db)
    assert out["gradual_drift"] == [] and out["near_threshold"]["repeated"] is True
    assert DS.NEAR_SIGNATURE in out["incidents_opened"]
    with db.session() as s:
        inc = s.scalar(select(Incident).where(Incident.signature == DS.NEAR_SIGNATURE))
        assert inc is not None and inc.halts_publication and "F-218" in inc.summary
    healthy = _db()
    _frames(healthy, readable=6)                                   # comfortably readable
    out2 = DS.run(healthy)
    assert out2["near_threshold"]["frames"] == 0 and out2["incidents_opened"] == []


def test_quality_sweep_reaches_the_coo_and_lauras_idle_priorities_without_laura_code():
    from datetime import datetime, timezone

    from brambleloop.autonomy import charters, generators

    cir = _cir()
    db = _db(cir)
    items = quality_ops.next_work(db)
    assert items and items[0]["job_type"] == "gate.quality"
    snap = generators.Snapshot.read(db, datetime.now(timezone.utc))
    cands = generators.provider_candidates(db, charters.BY_KEY["product_truth"], snap)
    assert [c.job_type for c in cands] == ["gate.quality"]
    # L-4: one check's reading is not a fresh re-verification; all four must have run
    ref = {"slug": cir.slug, "version": cir.version}
    _run(db, "validator", "cir.twin", ref)
    assert quality_ops.next_work(db) and "1 certified" in quality_ops.next_work(db)[0]["why"]
    _run(db, "validator", "cir.reverse", ref)
    _run(db, "asset_truth", "gate.asset_truth", ref)
    assert quality_ops.next_work(db)                     # gate.policy has not run yet
    out = _run(db, "policy", "gate.policy", ref)         # no listing: an UNKNOWN reading
    assert out["ran"] is False and out["ok"] is None
    # once every release has a reading from every check there is nothing to offer
    assert quality_ops.next_work(db) == []


# ---- review of a14c9ef: L-2 and L-4 ---------------------------------------------------------

def _simulate(results):
    """Patch reverify to return the next item of `results` (a dict, or an exception)."""
    real = quality_ops.reverify
    it = iter(results)

    def fake(db_, check, slug, version):
        r = next(it)
        if isinstance(r, Exception):
            raise r
        return {"check": check, **r}
    quality_ops.reverify = fake
    return real


def test_l2_a_policy_reverify_incident_does_not_read_as_an_open_policy_risk():
    from sqlalchemy import func

    cir = _cir()
    db = _db(cir)
    real = _simulate([{"ok": False, "problems": ["SIMULATED: banned claim"]}])
    try:
        out = _run(db, "policy", "gate.policy", {"slug": cir.slug, "version": cir.version})
    finally:
        quality_ops.reverify = real
    assert out["incident"]
    with db.session() as s:
        inc = s.get(Incident, out["incident"])
        assert inc.signature.startswith("quality.reverify:listing-rules:"), inc.signature
        # the exact predicate scale/evidence.py uses for `no_open_policy_risk`
        assert s.scalar(select(func.count()).select_from(Incident).where(
            Incident.resolved == False, Incident.signature.like("%policy%"))) == 0  # noqa: E712
    for check in quality_ops.CHECKS:
        assert "policy" not in quality_ops.signature(check, "s", "1")
    ev = (ROOT / "src/brambleloop/scale/evidence.py").read_text()
    assert 'Incident.signature.like("%policy%")' in ev    # the predicate this protects


def test_l4_a_later_pass_resolves_the_reverify_incident():
    cir = _cir()
    db = _db(cir)
    ref = {"slug": cir.slug, "version": cir.version}
    real = _simulate([{"ok": False, "problems": ["SIMULATED: drift"]}, {"ok": True,
                                                                         "problems": []}])
    try:
        bad = _run(db, "validator", "cir.reverse", ref)
        good = _run(db, "validator", "cir.reverse", ref)
    finally:
        quality_ops.reverify = real
    assert bad["incident"] and good["resolved"] == 1
    with db.session() as s:
        inc = s.get(Incident, bad["incident"])
        assert inc.resolved is True and "later re-verification" in inc.detail["resolution"]
        assert s.scalar(select(PatternVersion)).certified is True


def test_l4_a_check_that_raises_is_recorded_as_a_finding():
    cir = _cir()
    db = _db(cir)
    real = _simulate([RuntimeError("twin build exploded")])
    try:
        out = _run(db, "validator", "cir.twin", {"slug": cir.slug, "version": cir.version})
    finally:
        quality_ops.reverify = real
    assert out["ok"] is False and out["raised"] is True and out["incident"]
    assert "RuntimeError" in out["problems"][0]
    with db.session() as s:
        inc = s.get(Incident, out["incident"])
        assert inc.severity == "P2" and inc.halts_publication is False


def test_b199_i1_a_check_that_can_never_read_is_reported_as_unverifiable():
    cir = _cir()
    db = _db(cir)                                       # no drafted listing: policy can't read
    ref = {"slug": cir.slug, "version": cir.version}
    for _ in range(2):
        _run(db, "policy", "gate.policy", ref)
    rows = quality_ops.unverifiable(db)
    assert [(r["check"], r["unknown_readings"]) for r in rows] == [("gate.policy", 2)], rows
    plan = _run(db, "quality_director", "gate.quality", {})
    assert plan["unverifiable"] and plan["unverifiable"][0]["check"] == "gate.policy"


def test_b199_i4_the_first_delta_after_aliasing_lines_up_with_a_raw_key_reading():
    from brambleloop.runtime import intel_ops

    snap = {"groups": [{"benchmark": intel_ops.benchmark_alias("mjs"), "pod": "home",
                        "listings": 5, "price_median_cad": 9.0}]}
    prev = {"groups": [{"benchmark": "mjs", "pod": "home", "listings": 3,
                        "price_median_cad": 8.0}]}
    out = intel_ops._with_delta(snap, prev)
    assert out["groups"][0]["delta"] == {"listings": 2, "price_median_cad": 1.0}


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                fails += 1
                print("FAIL", name, repr(e))
                traceback.print_exc()
    print(f"{fails} failed")
    sys.exit(1 if fails else 0)
