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
