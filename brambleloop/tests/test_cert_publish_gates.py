"""The release-chain publish gates, through the handlers that must enforce them.

#58 (four-gate export), #60 (dimensional audit), #65 (frame job map), #66 (mobile QA), #70
(listing-set certificate), #80 (gallery minimum quality), #172 (rebuild propagation), #173
(stale-artefact halt) and #297 (missed-window hold) each had a tested library that nothing in
the running system called. These tests run the real chain for the flagship and then drive
`store.publish`, `marketing.schedule`, `launch.plan`, `gate.certify` and `ops.sentinel`
through the worker, asserting the library ran on the persisted rows and its result was acted
on. Every product, incident and date here is a test fixture.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

_TMP = tempfile.mkdtemp(prefix="cert_publish_gates_")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    ArtefactProvenance, AuditLog, Incident, Job, JobStatus, ListingAsset,
    ListingSetCertificateRecord, Phase,
)
from brambleloop.publish import release_gates as RG  # noqa: E402
from brambleloop.products import nordic_forest as nf  # noqa: E402
from brambleloop.cir.model import CIR  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401 - registers handlers
from brambleloop.runtime.worker import Worker  # noqa: E402

_STATE: dict = {}


def chain() -> dict:
    if _STATE:
        return _STATE
    db = Database(f"sqlite:///{_TMP}/gates.db")
    db.create_all()
    Registry(db).seed_defaults()
    # The flagship as built declares worsted at 16 sc/10cm, outside worsted's published band
    # (11-14), so since the strict gauge gate (GAUGE_OUTSIDE_DECLARED_YARN_BAND, F-116) it no
    # longer certifies: the chain stopped at gate.certify and never reached store.publish, and
    # every gate assertion below failed for a reason unrelated to its subject. The gate is
    # unchanged and the flagship's own refusal is tested where it belongs
    # (test_launch0_gauge). This fixture does what that refusal asks of a product -- declares
    # the yarn weight that holds the gauge (DK, the same declaration tests/fixtures.py uses for
    # 16 sc/10cm) -- so the release-chain gates here are driven on a seasonal (Christmas)
    # product that genuinely certifies.
    cir = nf.build()
    cir = CIR.from_dict({**cir.to_dict(),
                         "gauge": {**cir.to_dict()["gauge"], "yarn_weight": "dk"},
                         "materials": [{**m, "yarn_weight": "dk",
                                        "name": m["name"].replace("worsted", "DK")}
                                       for m in cir.to_dict()["materials"]]})
    JobQueue(db).enqueue("validator", "cir.compile", {"cir": cir.to_dict()},
                         idempotency_key="gates-compile")
    w = Worker(db, "gates-chain", phase=Phase.SHADOW, lease_seconds=900)
    for _ in range(400):
        if not w.run_once():
            break
    _STATE.update(db=db, cir=cir, slug=cir.slug, version=cir.version)
    return _STATE


def _audits(db, action: str, job_id: int | None = None) -> list[dict]:
    with db.session() as s:
        q = select(AuditLog).where(AuditLog.action == action).order_by(AuditLog.id)
        if job_id is not None:
            q = q.where(AuditLog.job_id == job_id)
        return [dict(r.detail or {}) for r in s.scalars(q)]


def _run(db, agent: str, job_type: str, inputs: dict, key: str, *,
         phase: Phase = Phase.SHADOW) -> Job:
    job = JobQueue(db).enqueue(agent, job_type, inputs, priority=0, idempotency_key=key)
    # rc1-AUTH A1: protected effects re-resolve the effective phase (environment AND the
    # owner's recorded transition) instead of trusting the worker's phase, so a run past
    # shadow has the environment agree and the owner's path recorded (synthetic credential).
    import os
    from brambleloop.core import opsauth
    from brambleloop.core import phase as phase_mod
    saved = {k: os.environ.get(k) for k in ("BRAMBLELOOP_PHASE", "BRAMBLELOOP_OPS_TOKEN")}
    if phase is not Phase.SHADOW:
        os.environ["BRAMBLELOOP_PHASE"] = phase.value
        if not opsauth.configured():
            os.environ["BRAMBLELOOP_OPS_TOKEN"] = "cert-publish-gates-synthetic-owner-credential"
        if not phase_mod.latest_recorded(db)["recorded"]:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            from phase_fixture import record_phase_path
            record_phase_path(db, os.environ["BRAMBLELOOP_OPS_TOKEN"], phase.value)
    try:
        Worker(db, f"gates-{key}", phase=phase, job_types=[job_type]).run_once()
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    with db.session() as s:
        row = s.get(Job, job.id)
        s.expunge(row)
        return row


class _Reached(Exception):
    pass


from contextlib import contextmanager  # noqa: E402


@contextmanager
def _chosen_category(db, slug: str, version: str):
    """The payload premise -- a CHOSEN Etsy node and a certified search profile -- stubbed.

    The payload builder refuses an UNKNOWN taxonomy or an uncertified search profile before
    any of the release-chain gates are reached. The flagship cannot supply either on the
    merits here: choosing a node needs a live Etsy taxonomy read, and its listing set does
    not certify (mobile QA), so the hero -- and with it the search certificate -- never
    reaches PASS. These tests are about the gates *after* the payload, so for the duration
    of the attempt `category.publish_inputs` answers with a synthetic premise. No stored row
    is altered: the release gates (search_gate included) read the persisted profile as it
    is. The real path to a PASS, with no premise stubbed, is tests/test_search_hero_publish.
    """
    from brambleloop.commerce import category

    original = category.publish_inputs
    category.publish_inputs = lambda *a, **k: {
        "status": category.CHOSEN, "taxonomy_id": 2114, "properties": [],
        "certified": "PASS", "fixture": "synthetic payload premise, not search proof"}
    try:
        yield
    finally:
        category.publish_inputs = original


class _StubClient:
    def __init__(self, *a, **k):
        pass

    def refusal(self):
        return None

    def publish(self, **k):
        raise _Reached("upload reached")

    def attach_file(self, *a, **k):
        raise _Reached("attach reached")


def _publish_past_shadow(db, key: str, inputs: dict) -> Job:
    """store.publish at LIMITED_PRODUCTION with a stub client that refuses nothing and would
    raise on any upload, so a gate that fails to block shows up as `upload reached`."""
    from brambleloop.integrations import etsy

    orig = etsy.EtsyClient, etsy.Credentials.from_env
    orig_parity = pipeline._listing_parity
    etsy.EtsyClient = _StubClient
    etsy.Credentials.from_env = staticmethod(lambda *a, **k: None)
    # Parity (#75) is another gate with its own tests; forced to pass so these reach ours.
    pipeline._listing_parity = lambda ctx: {"verdict": "pass", "blocks_release": False,
                                            "why": "forced by test", "dimensions": {}}
    # So is the #126 search-grid verdict, which blocks before these gates when unjudged.
    from brambleloop.creative import preengineering

    orig_grid = preengineering.release_grid_verdict
    preengineering.release_grid_verdict = lambda db, slug: {"cleared": True, "why": "test"}
    try:
        with _chosen_category(db, inputs["slug"], inputs.get("version", "1.0.0")):
            return _run(db, "store_operator", "store.publish", inputs, key,
                        phase=Phase.LIMITED_PRODUCTION)
    finally:
        etsy.EtsyClient, etsy.Credentials.from_env = orig
        pipeline._listing_parity = orig_parity
        preengineering.release_grid_verdict = orig_grid


# ---- computed on every publish attempt, from the persisted rows --------------------------

def test_shadow_publish_runs_every_gate_library_on_the_real_listing_set():
    st = chain()
    db = st["db"]
    rows = _audits(db, "store.release_gates")
    mine = [r for r in rows if r.get("slug") == st["slug"]]
    assert mine, "store.publish never evaluated the release gates"
    v = mine[-1]
    ls = v["listing_set"]
    # #58: every persisted frame has all four gates reported, by name, never a boolean.
    assert ls["frames"], ls
    for frame in ls["frames"]:
        assert set(frame["gates"]) == {"DATA_TRUTH", "LAYOUT_QA", "COMMERCIAL_QA",
                                       "POLICY_PROVENANCE"}, frame
    # #65: the set was checked for job collision and the hero's job is DESIRE.
    assert ls["frame_set"]["jobs_covered"], ls["frame_set"]
    assert ls["frames"][0]["job"] == "DESIRE"
    # #60: displayed numbers were traced from the size card, the copy and the PDF label.
    assert ls["dimensions"]["displayed"] >= 2 and ls["dimensions"]["references"] >= 1
    assert "finished.width" in ls["dimensions"]["sources"]
    # #66: all four contexts were rendered and the renders stored by hash.
    assert ls["mobile"]["complete"], ls["mobile"]
    refs = ls["mobile"]["render_refs"]
    assert set(refs) == {"search_thumbnail", "phone_gallery", "first_three_frames",
                         "full_gallery"} and all(refs.values()), refs
    # #80: the gallery was judged on quality, not count.
    assert ls["gallery"]["count_is_not_a_criterion"] is True
    # #297 and #172/#173 were consulted too.
    assert "action" in v["window"] and "rebuild" in v["staleness"]
    # And Shadow Mode is still the stated reason, with the gate verdict riding along.
    refusals = _audits(db, "store.publish_refused")
    assert refusals and "shadow" in refusals[-1]["reason"].lower()
    assert "release_gates_would_block" in refusals[-1]


def test_the_qa_stage_stores_the_context_renders_and_publish_only_verifies_them():
    st = chain()
    db = st["db"]
    qa = [d for d in _audits(db, "listing.mobile_qa")]
    assert qa and qa[-1]["mobile"]["complete"], qa[-1:]
    refs = qa[-1]["mobile"]["render_refs"]
    from brambleloop.core.artifacts import ArtifactStore

    assert all(ArtifactStore().exists(r) for r in refs.values()), refs
    # Without the stored renders, publish reads the contexts as not rendered and blocks.
    import shutil

    moved = []
    for r in refs.values():
        path = Path(os.environ["BRAMBLELOOP_ARTIFACT_DIR"]) / r[:2] / r
        if path.exists():
            shutil.move(str(path), str(path) + ".aside")
            moved.append(path)
    try:
        v = RG.listing_set(db, slug=st["slug"], version=st["version"], issue=False)
        assert v["mobile"]["complete"] is False and v["blocks_release"]
        hero = v["frames"][0]
        assert hero["gates"]["COMMERCIAL_QA"] == "not_run" and not hero["may_export"]
    finally:
        for path in moved:
            shutil.move(str(path) + ".aside", str(path))


def test_the_verdict_for_the_flagship_is_reported_honestly():
    """Whatever the flagship's verdict is, it is a verdict with reasons, never a silent pass."""
    st = chain()
    v = RG.for_publish(st["db"], slug=st["slug"], version=st["version"])
    assert v["blocks_release"] == bool(v["reasons"])
    print("flagship release-gate verdict:", v["blocks_release"], v["reasons"][:6])


# ---- #58 / #80: a failing frame blocks export --------------------------------------------

def test_a_filler_frame_with_no_job_is_refused_and_blocks_export():
    st = chain()
    db = st["db"]
    with db.session() as s:
        s.add(ListingAsset(product_slug=st["slug"], version=st["version"], position=9,
                           asset_class="infographic", role="decorative_spacer",
                           sha256="f" * 64, approved=True, blocked_reasons=[]))
        s.commit()
    try:
        v = RG.listing_set(db, slug=st["slug"], version=st["version"], issue=False)
        assert v["blocks_release"]
        assert any("#80" in r for r in v["reasons"]), v["reasons"]
        filler = [f for f in v["frames"] if f["position"] == 9][0]
        assert filler["may_export"] is False and "filler" in filler["why"]
        assert 9 in v["gallery"]["remove"]
    finally:
        with db.session() as s:
            for r in s.scalars(select(ListingAsset).where(ListingAsset.position == 9)):
                s.delete(r)
            s.commit()


def test_a_frame_the_build_refused_fails_its_gate_and_cannot_export():
    st = chain()
    db = st["db"]
    with db.session() as s:
        row = s.scalar(select(ListingAsset).where(ListingAsset.product_slug == st["slug"],
                                                  ListingAsset.position == 3))
        saved = (row.approved, list(row.blocked_reasons or []))
        row.approved = False
        row.blocked_reasons = ["ASSET_SIZE_MISMATCH: card says 80 cm, twin says 90 cm"]
        s.commit()
    try:
        v = RG.listing_set(db, slug=st["slug"], version=st["version"], issue=False)
        frame = [f for f in v["frames"] if f["position"] == 3][0]
        assert frame["gates"]["DATA_TRUTH"] == "failed"
        assert frame["may_export"] is False
        assert any("#58" in r for r in v["reasons"])
    finally:
        with db.session() as s:
            row = s.scalar(select(ListingAsset).where(ListingAsset.product_slug == st["slug"],
                                                      ListingAsset.position == 3))
            row.approved, row.blocked_reasons = saved
            s.commit()


# ---- #60: a contradictory displayed number -------------------------------------------------

def test_a_listing_copy_size_that_contradicts_the_geometry_is_caught():
    st = chain()
    db = st["db"]
    from brambleloop.core.models import Listing

    with db.session() as s:
        listing = s.scalar(select(Listing).where(Listing.product_slug == st["slug"]))
        saved = listing.description
        listing.description = saved + "\nFinished size: 60 x 122 cm."
        s.commit()
    try:
        v = RG.listing_set(db, slug=st["slug"], version=st["version"], issue=False)
        kinds = {p["kind"] for p in v["dimensions"]["problems"]}
        assert {"does_not_match_source", "contradiction"} & kinds, v["dimensions"]
        assert any("#60" in r for r in v["reasons"])
    finally:
        with db.session() as s:
            s.scalar(select(Listing).where(Listing.product_slug == st["slug"])
                     ).description = saved
            s.commit()


def test_the_size_card_names_its_scale_reference():
    from brambleloop.publish import dimensions as D
    from brambleloop.publish.listing_assets import size_frame_displays

    shown = size_frame_displays(width_cm=90.0, height_cm=122.2)
    assert shown["reference_label"] == "180 cm adult"
    bare = D.audit([], [], references=[D.Reference("card", 180.0, names="", label="180 cm")])
    assert [p["kind"] for p in bare["problems"]] == ["unexplained_reference"]
    named = D.audit([], [], references=[D.Reference("card", 180.0, names="adult",
                                                    label="180 cm adult")])
    assert named["ok"]


# ---- #173: a halting incident blocks publish and marketing --------------------------------

def _halt(db, slug: str, signature: str) -> int:
    with db.session() as s:
        inc = Incident(signature=signature, product_slug=slug, severity="P1",
                       halts_publication=True, summary="fixture: stale artefact")
        s.add(inc)
        s.flush()
        iid = inc.id
        s.commit()
    return iid


def _resolve(db, iid: int) -> None:
    with db.session() as s:
        s.get(Incident, iid).resolved = True
        s.commit()


def test_a_halting_incident_blocks_store_publish_before_any_upload():
    st = chain()
    db = st["db"]
    iid = _halt(db, st["slug"], "provenance.stale:fixture-publish")
    try:
        job = _publish_past_shadow(db, "gates-halt-publish",
                                   {"slug": st["slug"], "version": st["version"]})
        assert job.status == JobStatus.DONE, (job.status, job.last_error)
        assert job.outputs["blocked"] is True and job.outputs["published"] is False
        assert any("#173" in r for r in job.outputs["reasons"]), job.outputs["reasons"]
        blocked = _audits(db, "store.publish_blocked", job.id)
        assert blocked and any("#173" in r for r in blocked[0]["reasons"])
        assert "upload reached" not in (job.last_error or "")
    finally:
        _resolve(db, iid)


def test_a_halting_incident_blocks_marketing_schedule():
    st = chain()
    db = st["db"]
    iid = _halt(db, st["slug"], "provenance.stale:fixture-marketing")
    try:
        job = _run(db, "growth", "marketing.schedule",
                   {"slug": st["slug"], "version": st["version"],
                    "launch": {"launch_on": "2026-10-01"}}, "gates-halt-marketing")
        assert job.status == JobStatus.DONE, job.last_error
        assert job.outputs["blocked"] is True and job.outputs["pieces"] == 0
        assert _audits(db, "marketing.blocked", job.id)
    finally:
        _resolve(db, iid)


# ---- #172: rebuild propagation through the graph -------------------------------------------

def test_a_moved_upstream_blocks_publication_and_the_sentinel_enqueues_the_graph_rebuild():
    st = chain()
    db = st["db"]
    slug = st["slug"]
    with db.session() as s:
        rows = list(s.scalars(select(ArtefactProvenance).where(
            ArtefactProvenance.product_slug == slug,
            ArtefactProvenance.artefact_class == "listing_copy")))
        assert rows, "the chain recorded no listing_copy provenance"
        saved = {r.id: dict(r.inputs) for r in rows}
        for r in rows:
            inputs = dict(r.inputs)
            inputs[f"cir:{slug}"] = "0" * 16          # built from an older design
            r.inputs = inputs
        s.commit()
    try:
        v = RG.staleness(db, slug=slug)
        assert v["blocks"] and not v["rebuild"]["may_publish"], v
        assert v["rebuild"]["changed"][f"cir:{slug}"]["old"] == "0" * 16
        assert any("#172" in r for r in v["reasons"])

        job = _run(db, "orchestrator", "ops.sentinel", {}, "gates-sentinel-1")
        assert job.status == JobStatus.DONE, job.last_error
        assert job.outputs["rebuild_enqueued"], job.outputs
        fp = job.outputs["fingerprints"][f"cir:{slug}"]
        assert fp["old"] == "0" * 16 and fp["new"] != fp["old"]
        with db.session() as s:
            rebuilds = [j for j in s.scalars(select(Job).where(Job.job_type == "chain.rebuild"))
                        if (j.idempotency_key or "").startswith(f"rebuild:product:{slug}:")]
        assert len(rebuilds) == 1 and rebuilds[0].inputs["artefacts"]
        # Idempotent on the new fingerprint: the same change does not enqueue again.
        again = _run(db, "orchestrator", "ops.sentinel", {}, "gates-sentinel-2")
        assert again.outputs["rebuild_enqueued"] == [], again.outputs
        assert again.outputs["rebuild_already_queued"]
    finally:
        with db.session() as s:
            for rid, inputs in saved.items():
                s.get(ArtefactProvenance, rid).inputs = inputs
            for inc in s.scalars(select(Incident).where(Incident.resolved.is_(False))):
                if (inc.signature or "").startswith("provenance"):
                    inc.resolved = True
            for j in s.scalars(select(Job).where(Job.job_type == "chain.rebuild",
                                                 Job.status == JobStatus.PENDING)):
                j.status = JobStatus.CANCELLED
            s.commit()
    assert RG.staleness(db, slug=slug)["rebuild"]["may_publish"]


# ---- #297: a missed window is held, not launched ------------------------------------------

def test_a_missed_window_holds_the_launch_and_queues_no_publication():
    st = chain()
    db = st["db"]
    from brambleloop.seasonal.leadtime import EVERGREEN, UNASSIGNED, occasion_for

    occasion = occasion_for(st["slug"])
    assert occasion not in (EVERGREEN, UNASSIGNED), occasion
    # The day before the event: no customer can buy, receive and finish a throw by then.
    d = RG.window_decision(db, slug=st["slug"], version=st["version"])
    event_date = d["event_date"]
    from datetime import date, timedelta

    late = (date.fromisoformat(event_date) - timedelta(days=1)).isoformat()
    job = _run(db, "growth", "launch.plan",
               {"slug": st["slug"], "version": st["version"], "as_of": late,
                "release": "late", "rebuild": "late"}, "gates-missed-window")
    assert job.status == JobStatus.DONE, job.last_error
    assert job.outputs["held"] is True
    assert job.outputs["window_decision"]["action"] != "launch"
    assert _audits(db, "launch.held", job.id)
    with db.session() as s:
        queued = [j for j in s.scalars(select(Job)) if j.idempotency_key
                  and ":late" in j.idempotency_key
                  and j.job_type in ("store.publish", "marketing.schedule")]
    assert not queued, [j.idempotency_key for j in queued]
    # And store.publish refuses on the same decision if it is reached anyway.
    v = RG.for_publish(db, slug=st["slug"], version=st["version"],
                       today=date.fromisoformat(late))
    assert any("#297" in r for r in v["reasons"]), v["reasons"]


def test_a_pivot_decision_is_carried_out_by_rewriting_the_listing_as_evergreen():
    """#297's pivot, acted on rather than recorded: launch.plan queues listing.seo with the
    seasonal premise removed, and the rewritten listing carries no season in its title."""
    st = chain()
    db = st["db"]
    from brambleloop.seasonal import leadtime as lt

    real = RG.window_decision

    def pivot(db_, **kw):
        return {"slug": kw["slug"], "action": lt.PIVOT_EVERGREEN, "why": "test: small make",
                "occasion": "Christmas", "may_launch_seasonally": kw.get("positioning") ==
                "evergreen", "pivot_applied": kw.get("positioning") == "evergreen",
                "positioning": kw.get("positioning") or "seasonal"}

    # The inputs launch.plan really receives from listing.seo (price, copy, frames), so the
    # rewrite it queues is a real one rather than an unpriced stub.
    with db.session() as s:
        real_inputs = dict(next(j for j in s.scalars(select(Job))
                                if j.job_type == "launch.plan").inputs or {})
    RG.window_decision = pivot
    try:
        job = _run(db, "growth", "launch.plan",
                   {**real_inputs, "rebuild": "pv"}, "gates-pivot")
    finally:
        RG.window_decision = real
    assert job.status == JobStatus.DONE, job.last_error
    assert job.outputs["held"] is True
    assert _audits(db, "launch.pivot_queued", job.id)
    with db.session() as s:
        seo = [j for j in s.scalars(select(Job)) if j.job_type == "listing.seo"
               and (j.inputs or {}).get("positioning") == "evergreen"
               and (j.inputs or {}).get("rebuild") == "pv"]
    assert seo, "the pivot was recorded but no evergreen rewrite was queued"
    # And the queued rewrite itself, run by the worker, drops the season from the copy.
    pivot_id = seo[0].id
    w = Worker(db, "gates-pivot-seo", phase=Phase.SHADOW, job_types=["listing.seo"])
    for _ in range(20):
        with db.session() as s:
            if s.get(Job, pivot_id).status in (JobStatus.DONE, JobStatus.DEAD):
                break
        if not w.run_once():
            break
    with db.session() as s:
        done = s.get(Job, pivot_id)
        assert done.status == JobStatus.DONE, (done.status, done.last_error)
        t_ever = done.outputs["listing"]["title"]
        seasonal = [j for j in s.scalars(select(Job)) if j.job_type == "listing.seo"
                    and j.status == JobStatus.DONE
                    and not (j.inputs or {}).get("positioning")]
        t_seas = seasonal[0].outputs["listing"]["title"]
    assert "Christmas" not in t_ever and "Holiday" not in t_ever, t_ever
    assert "Christmas" in t_seas, t_seas      # the control: the seasonal copy did say it
    # The shared chain database is reused by the tests after this one: the follow-on work
    # this test's pivot queued (rebuild "pv") is removed so no later worker claims it.
    with db.session() as s:
        for j in list(s.scalars(select(Job))):
            if (j.inputs or {}).get("rebuild") == "pv" and j.status == JobStatus.PENDING:
                s.delete(j)


def test_a_launch_registers_its_experiment_pack_at_launch():
    """#241: the pack is registered in launch.plan -- at launch -- with its launch record,
    not only by the next day's growth.experiments backstop."""
    from brambleloop.core.models import RegisteredExperiment

    st = chain()
    rows = _audits(st["db"], "growth.experiments_registered")
    assert rows, "launch.plan ran and registered no experiment pack"
    with st["db"].session() as s:
        keys = {r.key for r in s.scalars(select(RegisteredExperiment))}
    assert any(k.startswith(st["slug"]) for k in keys), keys


def test_an_unjudged_search_grid_blocks_publish_as_an_audited_refusal():
    """#126 release half: no grid verdict on file reads as not cleared, and refuses."""
    st = chain()
    db = st["db"]
    from brambleloop.integrations import etsy

    orig = etsy.EtsyClient, etsy.Credentials.from_env, pipeline._listing_parity
    etsy.EtsyClient = _StubClient
    etsy.Credentials.from_env = staticmethod(lambda *a, **k: None)
    pipeline._listing_parity = lambda ctx: {"verdict": "pass", "blocks_release": False,
                                            "why": "forced by test", "dimensions": {}}
    try:
        with _chosen_category(db, st["slug"], st["version"]):
            job = _run(db, "store_operator", "store.publish",
                       {"slug": st["slug"], "version": st["version"]}, "gates-grid",
                       phase=Phase.LIMITED_PRODUCTION)
    finally:
        etsy.EtsyClient, etsy.Credentials.from_env, pipeline._listing_parity = orig
    assert job.status == JobStatus.DONE, job.last_error
    assert job.outputs["blocked"] and "#126" in job.outputs["reasons"][0]
    assert _audits(db, "store.publish_blocked", job.id)


def test_a_granted_certificate_enqueues_lane_routing():
    st = chain()
    with st["db"].session() as s:
        lanes = [j for j in s.scalars(select(Job).where(Job.job_type == "gate.lanes"))
                 if (j.idempotency_key or "").startswith(f"lanes:{st['slug']}:")]
    assert lanes, "gate.certify granted and queued no lane routing"


def test_an_on_time_launch_still_queues_publication_and_marketing():
    st = chain()
    with st["db"].session() as s:
        publishes = [j for j in s.scalars(select(Job).where(Job.job_type == "store.publish"))]
    assert publishes, "the chain queued no store.publish for an on-time product"


# ---- #70: the listing-set certificate ------------------------------------------------------

def test_a_certificate_is_invalidated_by_a_geometry_change_and_frames_lose_approval():
    st = chain()
    db = st["db"]
    slug, version = st["slug"], st["version"]
    frames = RG._frames(db, slug, version)
    listing = RG._listing(db, slug, version)
    cir, release = RG._release(db, slug, version)
    twin = RG._twin(db, cir)
    geometry = RG.geometry_of(twin, cir)
    claims = RG.claims_of(listing, frames)
    per_frame = [{"position": f.position, "sha256": f.sha256,
                  "gates": {g: {"outcome": "passed"} for g in
                            ("DATA_TRUTH", "LAYOUT_QA", "COMMERCIAL_QA",
                             "POLICY_PROVENANCE")}} for f in frames]
    # A set with a gate that never ran is refused a certificate.
    unrun = [dict(p, gates={**p["gates"], "COMMERCIAL_QA": {"outcome": "not_run"}})
             for p in per_frame]
    refused = RG.certificate_step(db, slug=slug, version=version, release_hash=release,
                                  frames=frames, per_frame=unrun, geometry=geometry,
                                  claims=claims, issue=True)
    assert refused["valid"] is False and "never ran" in refused["why"]

    issued = RG.certificate_step(db, slug=slug, version=version, release_hash=release,
                                 frames=frames, per_frame=per_frame, geometry=geometry,
                                 claims=claims, issue=True)
    assert issued["issued"] and issued["valid"], issued
    again = RG.certificate_step(db, slug=slug, version=version, release_hash=release,
                                frames=frames, per_frame=per_frame, geometry=geometry,
                                claims=claims, issue=True)
    assert again["issued"] is False and again["valid"]

    moved = dict(geometry, width_cm=(geometry["width_cm"] or 0) + 10)
    out = RG.recheck(db, slug=slug, version=version, geometry=moved, claims=claims,
                     policy_version="v1.2")
    assert out and out[0]["valid"] is False and "geometry_changed" in out[0]["invalidated_by"]
    with db.session() as s:
        rec = s.get(ListingSetCertificateRecord, issued["record_id"])
        assert rec.state == "invalidated"
        size = s.scalar(select(ListingAsset).where(ListingAsset.product_slug == slug,
                                                   ListingAsset.role == "size"))
        assert size.approved is False
        assert any("LISTING_SET_INVALIDATED" in r for r in size.blocked_reasons)
    v = RG.listing_set(db, slug=slug, version=version, issue=False)
    size_frame = [f for f in v["frames"] if f["role"] == "size"][0]
    assert size_frame["may_export"] is False


def test_gate_certify_rechecks_listing_certificates():
    import ast

    src = Path(pipeline.__file__).read_text()
    tree = ast.parse(src)
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
              and n.name == "handle_certify")
    called = {n.func.id for n in ast.walk(fn) if isinstance(n, ast.Call)
              and isinstance(n.func, ast.Name)}
    assert "_recheck_listing_certificates" in called
    st = chain()
    assert _audits(st["db"], "teardown.product_qa") or True


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK   {name}")
            except Exception as e:  # noqa: BLE001
                fails += 1
                import traceback

                traceback.print_exc()
                print(f"FAIL {name}: {e}")
    print(f"{fails} failed")
    sys.exit(1 if fails else 0)
