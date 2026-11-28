"""ENG-FIRST-LISTING-PATH: once hexagon-coaster-set's gallery becomes valid, nothing downstream
blocks it from READY, the listing package, the owner's publication card and the door that
queues store.publish (research/FIRST-LISTING-PATH.md).

The production shape this reproduces (19i31, 46908fe66): the release has sat at the sale
pipeline's gallery stage for days. Its image run already ended once (the gallery event was
consumed and refused: "gallery not assembled"), the sweep's three bounded re-drives were spent
while the gallery was still invalid, and store.publish reads "suspended" because the launch-time
store.publish was refused in SHADOW three times with an identical result (the thrash breaker).
Then the gallery becomes valid with NO new image end state (a re-verification of stored frames).

Found at HEAD, fixed here:
* B1: nothing re-entered the gallery stage. The gallery event key is per (end state, epoch) and
  was already taken; the sweep's re-drive count was exhausted and only resets on progress, which
  could never come. The release stayed at gallery_in_production forever with a valid gallery.
  Now the hourly sweep re-enters the free gallery stage once per gallery certificate (and, while
  the image run is assembled but uncertified, once per hour), outside the bounded count.
* B2: a stage blocked on the listing package (attach: `listing_gates`) after its three re-drives
  was never re-entered when the package later changed. Now the sweep re-enters it once per new
  package fingerprint.
* B3: a thrash suspension tripped by closed-gate refusals (store.publish in SHADOW) stood after
  the owner moved the phase, and the shadow-era dead letters in the 72 h window re-tripped it.
  Now a closed-gate suspension recorded before the newest phase transition is lifted (and its
  incident resolved), and refusals that ended before that transition are not observations.

Not weakened (asserted below): SHADOW still refuses store.publish and the door; a failing
(non-refusal) loop stays suspended across a phase change; the door still needs a signed grant,
the kill-switch and a publishing phase; the handler still re-checks everything.

test_double (labelled): the image generator and judges (free stubs), the generated-gallery
certificate (`CertifiedGalleryDouble`, "stub gallery marked valid"), the buyer-facing
publication gates (`release_gates.for_publish`), and the readiness verdict at transition time.

Run: cd brambleloop && PYTHONPATH=src:tests $PY tests/test_first_listing_path.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import test_sale_pipeline_e2e as E  # noqa: E402  (its world, doubles and drain)

from sqlalchemy import func, select, update  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (AuditLog, EtsyTaxonomySnapshot, Incident, Job,  # noqa: E402
                                     JobStatus, Listing, PatternVersion)
from brambleloop.products import launch0 as L  # noqa: E402
from brambleloop.publish import listing_package as LP  # noqa: E402
from brambleloop.publish import sale_pipeline as SPL  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.swarm import orchestrate as orc  # noqa: E402
from brambleloop.visual import candidate_gates as CG  # noqa: E402
from brambleloop.visual import image_production as IP  # noqa: E402

OPS = "f" * 40
_W: dict = {}


def _world():
    """The release at the gallery stage with its event consumed and its re-drives spent."""
    if _W:
        return _W
    import fixtures_etsy_taxonomy as FX
    import test_w4_ownerimg as O
    from brambleloop.publish import release_gates
    from brambleloop.visual.outfits import listing_of

    db = Database(f"sqlite:///{tempfile.mkdtemp(dir=E._TMP)}/path.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    snap = FX.snapshot()
    with db.session() as s:
        s.add(EtsyTaxonomySnapshot(sha256="fixture", node_count=len(snap["nodes"]),
                                   nodes=snap["nodes"], properties=snap["properties"]))
    cir = L.cir_for("hexagon_coasters")
    job = E._run_job(db, "quality_director", "gate.certify", {"cir": cir.to_dict()}, "certify")
    assert job.outputs.get("granted"), job.outputs
    with db.session() as s:
        release = s.scalar(select(PatternVersion)).release_hash
    job = E._run_job(db, "publishing", "assets.build", {"slug": cir.slug, "version": cir.version,
                                                        "release": release, "rebuild": "x"}, "a")
    assert job.status is JobStatus.DONE, job.last_error
    E._drain(db, ("pricing.position", "listing.seo", "launch.plan"), limit=10)
    double = E.CertifiedGalleryDouble(db, cir.slug, cir.version, release, listing_of(cir.slug))
    restore = double.install()
    # The gallery is NOT valid when the image run ends: the certification route refuses.
    SPL._gallery_route_certify = lambda *_a: (
        {"certified": True, "why": "test_double certificate"} if double.certified else
        {"certified": False, "why": "verification:references:exhausted"})
    real_gen, real_judges = IP.resolve_generator, CG.RealJudges
    gen = O.StubGenerator()                                  # test_double, free
    IP.resolve_generator = lambda _db: gen
    CG.RealJudges = lambda _db: O.StubJudges()               # test_double
    real_gate = release_gates.for_publish
    gate = {"block": False}
    release_gates.for_publish = lambda *a, **k: (
        {"reasons": ["SEARCH_GRID: UNKNOWN (tournament pending)"], "blocks_release": True}
        if gate["block"] else {"reasons": [], "blocks_release": False})
    _W.update(gate=gate, db=db, cir=cir, release=release, double=double, slug=cir.slug,
              version=cir.version,
              restore=lambda: (restore(), setattr(IP, "resolve_generator", real_gen),
                               setattr(CG, "RealJudges", real_judges),
                               setattr(release_gates, "for_publish", real_gate)))
    # Every run this release will get (the launch-time route and the for-sale FLUX route the
    # listing package admits) ends while the gallery is still invalid, as in production.
    ran = E._drain(db, (SPL.JOB_TYPE, IP.JOB_TYPE, "listing.package", "assets.build"),
                   limit=200)
    _W["ran_before"] = ran
    run = SPL.get(db, cir.slug, cir.version, release)
    assert run["state"] == SPL.GALLERY and run["blocker"], run
    # Production's age: days at the gallery stage, the three bounded re-drives spent.
    with db.session() as s:
        s.execute(update(SPL.SalePipelineRun).where(
            SPL.SalePipelineRun.run_key == run["run_key"]).values(
            redrives=SPL.MAX_REDRIVES,
            progressed_at=datetime.now(timezone.utc) - timedelta(days=3)))
    return _W


def _sweep(db):
    return E._run_job(db, "listing", SPL.SWEEP_JOB_TYPE, {},
                      f"sweep-{datetime.now(timezone.utc).timestamp()}")


def test_1_the_gallery_becoming_valid_re_enters_the_chain_without_a_new_image_event():
    W = _world()
    db = W["db"]
    # Before: the sweep with the gallery still invalid neither progresses nor re-drives.
    _sweep(db)
    E._drain(db, (SPL.JOB_TYPE, IP.JOB_TYPE))
    assert SPL.get(db, W["slug"], W["version"], W["release"])["state"] == SPL.GALLERY
    # The stub gallery is marked valid (the other agents' gates pass on stored frames), while
    # one buyer-facing listing gate is still pending (UNKNOWN).
    W["double"].certified = True
    W["gate"]["block"] = True
    _sweep(db)
    ran = E._drain(db, (SPL.JOB_TYPE, IP.JOB_TYPE, "listing.package", "assets.build"))
    run = SPL.get(db, W["slug"], W["version"], W["release"])
    assert run["state"] == SPL.PDFS_CERTIFIED and run["blocker"] == "listing_gates", (run, ran)
    stages = [st for jt, st, *_ in ran if jt == SPL.JOB_TYPE]
    assert stages[:4] == ["gallery", "pdf_build", "pdf_certify", "attach"], ran
    # A second sweep enqueues nothing new for the same certificate and the same package.
    with db.session() as s:
        n = s.scalar(select(func.count()).select_from(Job).where(Job.job_type == SPL.JOB_TYPE))
    _sweep(db)
    with db.session() as s:
        m = s.scalar(select(func.count()).select_from(Job).where(Job.job_type == SPL.JOB_TYPE))
    assert m == n, (n, m)


def test_2_the_package_changing_re_enters_attach_after_the_re_drives_are_spent():
    W = _world()
    db = W["db"]
    key = SPL.run_key(W["slug"], W["version"], W["release"])
    with db.session() as s:          # hours later: the three bounded re-drives are spent
        s.execute(update(SPL.SalePipelineRun).where(SPL.SalePipelineRun.run_key == key).values(
            redrives=SPL.MAX_REDRIVES,
            progressed_at=datetime.now(timezone.utc) - timedelta(days=1)))
    W["gate"]["block"] = False       # the pending gate passes
    _sweep(db)                       # the package has not been re-assembled yet: nothing
    assert SPL.get(db, W["slug"], W["version"], W["release"])["state"] == SPL.PDFS_CERTIFIED
    # The six-hourly listing.package sweep records the changed package; the next hourly sale
    # sweep re-enters attach once for that fingerprint.
    E._run_job(db, "listing", "listing.package", {"cadence": "listing_package"}, "lp-sweep")
    _sweep(db)
    ran = E._drain(db, (SPL.JOB_TYPE,))
    run = SPL.get(db, W["slug"], W["version"], W["release"])
    assert run["state"] == SPL.READY, (run, ran)
    assert [st for _jt, st, *_ in ran] == ["attach", "ready"], ran
    got = SPL.ready_for_sale(db, W["slug"], W["version"], W["release"])
    assert got["ready"] is True, got
    pkg = LP.latest(db, W["slug"], W["version"])
    assert SPL.package_ready_for_sale(pkg, W["release"]), pkg.get("blockers")
    assert len(pkg.get("gallery") or []) >= 7, pkg.get("gallery")


def _phase_up(db):
    """The owner's recorded transition shadow -> staging -> limited_production, and the env."""
    from brambleloop.core import phase as phase_mod

    with db.session() as s:
        a = AuditLog(actor="orchestrator", action="launch.assessed", artifact="launch",
                     detail={"ready": True})
        b = AuditLog(actor="orchestrator", action="launch.rollback_rehearsed",
                     artifact="x", detail={"ok": True})
        s.add_all([a, b])
        s.flush()
        refs = {"readiness": str(a.id), "rollback": str(b.id)}
    os.environ["BRAMBLELOOP_OPS_TOKEN"] = OPS
    for to in ("staging", "limited_production"):
        phase_mod.record_transition(db, authorization=f"Bearer {OPS}", to=to,
                                    reason="test: owner phase decision", evidence_refs=refs,
                                    readiness_verdict=lambda _db, _to: {"ready": True,
                                                                        "failing": []})
    os.environ["BRAMBLELOOP_PHASE"] = "limited_production"
    assert phase_mod.effective(db, record_incident=False) == "limited_production"


def _dead(db, job_type, inputs, error, key):
    q = JobQueue(db)
    job = q.enqueue("store_operator", job_type, inputs, idempotency_key=key)
    with db.session() as s:
        j = s.get(Job, job.id)
        j.status, j.last_error = JobStatus.DEAD, error
        j.finished_at = datetime.now(timezone.utc)
    return job.id


def test_3_a_shadow_refusal_suspension_lifts_with_the_phase_and_a_failing_loop_does_not():
    db = Database(f"sqlite:///{tempfile.mkdtemp(dir=E._TMP)}/thrash.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    os.environ["BRAMBLELOOP_PHASE"] = "shadow"
    inputs = {"slug": "hexagon-coaster-set", "version": "1.2.1", "release": "r"}
    refusal = ("ShadowModeRefusal: store.publish is a production capability; the system is in "
               "SHADOW mode and has no live Etsy connection. Draft retained for review.")
    for n in range(3):
        _dead(db, "store.publish", inputs, refusal, f"sp-{n}")
        _dead(db, "assets.build", {"slug": "x"}, "ValueError: boom", f"ab-{n}")
    out = orc.thrash_sweep(db)
    assert "store.publish" in out["suspended"] and "assets.build" in out["suspended"], out
    # SHADOW holds: still suspended on a re-sweep.
    assert "store.publish" in orc.suspended_job_types(db)
    try:
        _phase_up(db)
        sus = orc.suspended_job_types(db)
        assert "store.publish" not in sus, sus
        assert "assets.build" in sus, sus     # a failing loop keeps its breaker
        again = orc.thrash_sweep(db)          # shadow-era refusals in the window do not re-trip
        assert "store.publish" not in again["suspended"], again
        assert "assets.build" in again["suspended"], again
        with db.session() as s:
            open_sp = [i.signature for i in s.scalars(select(Incident).where(
                Incident.resolved.is_(False), Incident.signature.like("thrash:store.publish:%")))]
        assert open_sp == [], open_sp
        # A refusal AFTER the transition is an observation again (staging/limited refusals).
        for n in range(3):
            _dead(db, "store.publish", inputs, "capability not enabled: x", f"sp2-{n}")
        assert "store.publish" in orc.thrash_sweep(db)["suspended"]
    finally:
        os.environ["BRAMBLELOOP_PHASE"] = "shadow"


def test_4_the_owner_card_and_door_reach_store_publish_only_past_shadow_with_a_grant():
    from brambleloop.app.command_center import approvals
    from brambleloop.core import owner_grant_keys as ogk
    from brambleloop.ops import owner_execution as oe
    from brambleloop.ops import publication_authority as pa

    W = _world()
    db = W["db"]
    assert SPL.get(db, W["slug"], W["version"], W["release"])["state"] == SPL.READY
    slug, version, rh = W["slug"], W["version"], W["release"]
    # The launch-time store.publish (launch.plan) runs in SHADOW, as in production: refused,
    # dead-lettered, never re-driven (a deliberate refusal).
    E._drain(db, ("store.publish",))
    with db.session() as s:
        launch_time = list(s.scalars(select(Job).where(Job.job_type == "store.publish")))
    assert launch_time and all(j.status is JobStatus.DEAD for j in launch_time), \
        [(j.status, j.last_error) for j in launch_time]
    assert all("shadow" in (j.last_error or "").lower() for j in launch_time)
    saved = {k: os.environ.get(k) for k in ("BRAMBLELOOP_PUBLISH_AUTHORISED",
                                            "BRAMBLELOOP_OPS_TOKEN", "BRAMBLELOOP_PHASE",
                                            ogk.SIGNING_KEY_VAR, ogk.VERIFY_KEY_VAR)}
    try:
        os.environ.update({"BRAMBLELOOP_OPS_TOKEN": OPS, "BRAMBLELOOP_PUBLISH_AUTHORISED": "1",
                           **ogk.generate_keypair()})
        os.environ["BRAMBLELOOP_PHASE"] = "shadow"
        cards = {c["card_id"]: c for c in approvals.inbox(db).get("cards") or []
                 if isinstance(c, dict) and c.get("card_id")}
        card = cards.get(f"publication:{slug}@{version}")
        assert card is not None, sorted(cards)
        # The card names what is still owed after the gallery. In this world only the three
        # sections fed by their own daily jobs and judges are not PASS (parity: the
        # creative.blind_review cadence and the hero description; policy: ops.policy_watch;
        # rollback: the launch.readiness rehearsal) -- nothing the sale chain owns.
        owed = {e["label"] for e in card["evidence"]
                if e["state"] != "PASS" and e["label"] != "economics"}
        assert owed <= {"parity", "policy", "rollback"}, card["evidence"]
        if not card["executable"]:
            assert card["actions"] == [] and card["not_executable_reason"], card
        content = pa.snapshot(db, slug, version, rh)
        with ogk.owner_request("first-listing-path-owner"):
            gid = pa.approve(db, authorization=OPS, slug=slug, version=version, release=rh,
                             expected_digest=pa.digest(content),
                             reason="test: owner review of the package")["approval_id"]
        try:                                   # SHADOW: the door refuses and queues nothing
            oe.queue_publication(db, slug=slug, version=version, release=rh, approval_id=gid)
            raise AssertionError("door queued in SHADOW")
        except oe.ExecutionRefused as exc:
            assert "phase" in str(exc), exc
        _phase_up(db)
        os.environ["BRAMBLELOOP_PUBLISH_AUTHORISED"] = "0"
        try:                                   # the kill-switch still denies
            oe.queue_publication(db, slug=slug, version=version, release=rh, approval_id=gid)
            raise AssertionError("door queued with the kill-switch off")
        except oe.ExecutionRefused:
            pass
        os.environ["BRAMBLELOOP_PUBLISH_AUTHORISED"] = "1"
        out = oe.queue_publication(db, slug=slug, version=version, release=rh, approval_id=gid)
        assert out["queued"] is True, out
        assert "store.publish" not in orc.suspended_job_types(db)
        with db.session() as s:
            j = s.get(Job, out["job_id"])
            assert j.job_type == "store.publish" and j.status is JobStatus.PENDING
            assert j.inputs["owner_publication_approval_id"] == gid
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


if __name__ == "__main__":
    import traceback

    failed = 0
    try:
        for name, fn in sorted((n, f) for n, f in dict(globals()).items()
                               if n.startswith("test_")):
            try:
                fn()
                print("OK  ", name)
            except Exception:  # noqa: BLE001
                failed += 1
                print("FAIL", name)
                traceback.print_exc()
    finally:
        if _W.get("restore"):
            _W["restore"]()
    print(f"{failed} failed")
    sys.exit(1 if failed else 0)
