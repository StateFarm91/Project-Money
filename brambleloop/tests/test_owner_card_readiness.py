"""ENG-OWNER-CARD-READINESS: after a release reaches READY, the owner publication card's three
remaining sections -- parity, policy, rollback -- pass on real evidence made by their own
scheduled jobs, and stay not-passing when that evidence is absent or stale.

World: `test_first_listing_path` (hexagon-coaster-set@1.2.1 taken to READY on the real
handlers, SHADOW). Every producer below is enqueued by the real `Scheduler.tick` from the real
`CADENCES` table and run by a SHADOW `Worker` -- never called directly, never a written row.

Found at c60e63b17, fixed here:
* PARITY / COMPETITIVE: `creative.blind_review` reviewed only `products.builder.CATALOGUE`,
  which never names the Launch-0 releases the sale pipeline takes to READY. No row was ever
  written for hexagon-coaster-set, so COMPETITIVE read `unjudged` for good. It now also reviews
  every product holding a certified release.
* PARITY / HERO and #61: the hero's blind description and the frame review are made only
  inside `assets.build` while `image_vision` is open. A READY release built while vision was
  closed is never rebuilt, so both stayed missing for good. The hourly `sale.pipeline_sweep`
  now rebuilds such a release once per evidence state while vision is open (bounded; a review
  that was made and did not clear is never re-bought; nothing is queued while vision is shut).
* POLICY: `ops.policy_watch` was parked by the idle free-poll backoff (its outputs are the same
  every day by design) at 2x..32x its daily period, and 32 days is past the 30-day freshness
  window the card reads. It is now a liveness type, and an old park on it is lifted.
* ROLLBACK: no break. `launch.readiness` (daily, inside the 3-day window, never backed off)
  writes the `launch.rollback_rehearsed` row the card reads.

Not fixed, asserted as still blocking (needs a decision, see BUILD_STATE):
* a stored generated-gallery frame (`AI_LIFESTYLE_CONCEPT`, `gallery_persist` at 100+slot)
  has no #61 producer -- `assets.build` reviews only its own renders -- so #61 cannot bind
  once the generated gallery is stored, and the re-drive does not buy a review that cannot.
* the etsy.com/legal policy sources are a person's reading (bot protection is never evaded);
  without it the card's policy section stays FAIL however often the watch runs.

test_double (labelled): the world's doubles (`test_first_listing_path`); the image_vision gate,
the blind describer, the hero describer and the grid reading (fixtures, free); Etsy's Help
Center article API (`policy_reader._fetch`); the person's page reading of the five legal pages
(`record_page_reading`, the intake the Command Center uses).

Run: cd brambleloop && PYTHONPATH=src:tests $PY tests/test_owner_card_readiness.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
os.environ["BRAMBLELOOP_PHASE"] = "shadow"
os.environ.pop("BRAMBLELOOP_POLICY_READER", None)

import test_first_listing_path as FLP  # noqa: E402  (the READY world)

from sqlalchemy import select, update  # noqa: E402

from brambleloop.core.models import (AuditLog, Incident, Job, JobStatus,  # noqa: E402
                                     ListingAsset, Phase, PolicySnapshot)
from brambleloop.ops import publication_authority as pa  # noqa: E402
from brambleloop.publish import sale_pipeline as SPL  # noqa: E402
from brambleloop.runtime.worker import CADENCES, Scheduler, Worker  # noqa: E402
from brambleloop.swarm import orchestrate as orc  # noqa: E402

_S: dict = {}
DAY = timedelta(days=1)


def _world():
    if not _S:
        FLP.test_1_the_gallery_becoming_valid_re_enters_the_chain_without_a_new_image_event()
        FLP.test_2_the_package_changing_re_enters_attach_after_the_re_drives_are_spent()
        W = FLP._world()
        assert SPL.get(W["db"], W["slug"], W["version"], W["release"])["state"] == SPL.READY
        _S.update(W=W, db=W["db"], slug=W["slug"], version=W["version"], rh=W["release"],
                  day=0)
    return _S


def _section(name):
    S = _world()
    return pa.evidence(S["db"], S["slug"], S["version"], S["rh"])[name]


def _scheduled(job_type, *, advance_days=0):
    """The real scheduler opens the cadence window; a SHADOW worker runs only that job."""
    S = _world()
    db = S["db"]
    S["day"] += advance_days
    now = datetime.now(timezone.utc) + timedelta(days=S["day"])
    Scheduler(db).tick(now=now)
    with db.session() as s:
        pending = [j.id for j in s.scalars(select(Job).where(
            Job.job_type == job_type, Job.status == JobStatus.PENDING))]
    assert pending, f"the scheduler enqueued no {job_type} at {now.isoformat()}"
    for _ in pending:
        Worker(db, f"w-{job_type}", phase=Phase.SHADOW, job_types=[job_type],
               lease_seconds=900).run_once()
    with db.session() as s:
        rows = list(s.scalars(select(Job).where(Job.id.in_(pending))))
        for r in rows:
            s.expunge(r)
    assert all(r.status is JobStatus.DONE for r in rows), \
        [(r.job_type, r.status, (r.last_error or "")[:300]) for r in rows]
    return rows[-1]


def _age_rows(action, artifact, days):
    S = _world()
    with S["db"].session() as s:
        s.execute(update(AuditLog).where(AuditLog.action == action,
                                         AuditLog.artifact == artifact)
                  .values(at=datetime.now(timezone.utc) - timedelta(days=days)))


# ---- the schedule ---------------------------------------------------------------------------

def test_1_each_producer_is_scheduled_inside_its_card_window_and_never_parked_idle():
    from brambleloop.creative import blind_review
    from brambleloop.gates import platform_policy
    from brambleloop.launch import rollback
    from brambleloop.runtime import release, sale_pipeline_ops  # noqa: F401  (registers)
    from brambleloop.runtime.worker import handlers as registry

    period = {jt: p for _n, _a, jt, p in CADENCES}
    windows = {"launch.readiness": rollback.MAX_AGE_DAYS,
               "creative.blind_review": blind_review.MAX_REVIEW_AGE_DAYS,
               "ops.policy_watch": platform_policy.MAX_AGE_DAYS}
    for jt, days in windows.items():
        assert jt in period, f"{jt} is not on the cadence table"
        assert registry.get(jt) is not None, f"{jt} has no registered handler"
        # at most a day late (the spread offset) and still inside the window the card reads
        assert 2 * period[jt] <= days * 86400, (jt, period[jt], days)
        assert orc.is_pipeline_job(jt) or jt in orc.LIVENESS_JOB_TYPES, \
            f"{jt} can be parked by the idle free-poll backoff past its window"


# ---- rollback -------------------------------------------------------------------------------

def test_2_rollback_passes_on_the_scheduled_rehearsal_and_not_when_it_is_stale():
    S = _world()
    artifact = f"{S['slug']}@{S['version']}"
    assert _section("rollback")["state"] != pa.PASS          # absent: never rehearsed
    _scheduled("launch.readiness")
    sec = _section("rollback")
    assert sec["state"] == pa.PASS, sec
    assert sec["rehearsal"]["ok"] is True and all(st["ok"] for st in sec["rehearsal"]["steps"])
    _age_rows("launch.rollback_rehearsed", artifact, 4)       # older than MAX_AGE_DAYS (3)
    assert _section("rollback")["state"] == pa.UNKNOWN
    _scheduled("launch.readiness", advance_days=1)            # the next daily window
    assert _section("rollback")["state"] == pa.PASS


# ---- policy ---------------------------------------------------------------------------------

def _fake_help_center(url):
    """test_double: Etsy's public Help Center article API."""
    import re

    article = re.search(r"/articles/(\d+)\.json", url).group(1)
    body = "<p>" + ("Rules for listing photos and tags, read through the article API. " * 20) \
           + "</p>"
    return {"article": {"id": int(article), "title": f"article {article}", "body": body,
                        "edited_at": "2026-11-01T00:00:00Z", "draft": False}}


def _reader_on():
    from brambleloop.gates import policy_access, policy_reader

    saved = (policy_reader._fetch, policy_reader.MIN_SECONDS_BETWEEN_FETCHES,
             policy_access.assess, os.environ.get("BRAMBLELOOP_POLICY_READER"))
    policy_reader._fetch = lambda url, **_k: _fake_help_center(url)
    policy_reader.MIN_SECONDS_BETWEEN_FETCHES = 0

    def no_network(_db):
        raise OSError("test: no network for the legal-page access evidence")
    policy_access.assess = no_network
    os.environ["BRAMBLELOOP_POLICY_READER"] = "1"

    def restore():
        policy_reader._fetch, policy_reader.MIN_SECONDS_BETWEEN_FETCHES = saved[0], saved[1]
        policy_access.assess = saved[2]
        if saved[3] is None:
            os.environ.pop("BRAMBLELOOP_POLICY_READER", None)
        else:
            os.environ["BRAMBLELOOP_POLICY_READER"] = saved[3]
    return restore


def test_3_policy_passes_only_on_current_readings_of_every_source():
    from brambleloop.gates import platform_policy as PP
    from brambleloop.gates import policy_reader

    S = _world()
    db = S["db"]
    assert _section("policy")["state"] == pa.UNKNOWN          # absent: never read
    # The watch with no reader (a laptop): it seeds the repository's dated excerpts, which are
    # older than 30 days today -- genuinely stale, so FAIL, never PASS.
    _scheduled("ops.policy_watch")
    sec = _section("policy")
    assert sec["state"] == pa.FAIL and sec["stale"], sec
    restore = _reader_on()
    try:
        out = _scheduled("ops.policy_watch", advance_days=1).outputs
        assert sorted(out["help_center"]["read"]) == sorted(policy_reader.help_center_sources())
        sec = _section("policy")
        # the Help Center sources are current now; the five etsy.com/legal pages are a
        # person's reading, and without it the section stays FAIL
        assert sec["state"] == pa.FAIL, sec
        assert set(sec["stale"]) == set(policy_reader.external_sources()), sec
        for source in policy_reader.external_sources():       # test_double: the person
            PP.record_page_reading(db, source=source, text=f"{source} page text, read by a "
                                   "person in their own browser. " * 10,
                                   read_by="test_double:person", owner_attested=True)
        _scheduled("ops.policy_watch", advance_days=1)
    finally:
        restore()
    sec = _section("policy")
    assert sec["state"] == pa.PASS, sec
    # stale: every reading 31 days old reads FAIL
    with db.session() as s:
        latest = {}
        for r in s.scalars(select(PolicySnapshot).order_by(PolicySnapshot.id)):
            latest[r.source] = r.id
        s.execute(update(PolicySnapshot).where(PolicySnapshot.id.in_(list(latest.values())))
                  .values(checked_on=(date.today() - timedelta(days=31)).isoformat()))
    assert _section("policy")["state"] == pa.FAIL
    with db.session() as s:
        s.execute(update(PolicySnapshot).where(PolicySnapshot.id.in_(list(latest.values())))
                  .values(checked_on=date.today().isoformat()))
    assert _section("policy")["state"] == pa.PASS


def test_4_the_policy_watch_is_never_parked_by_the_idle_backoff():
    S = _world()
    db = S["db"]
    restore = _reader_on()
    try:
        for _ in range(4):                    # a settled watch: the last three runs identical
            _scheduled("ops.policy_watch", advance_days=1)
    finally:
        restore()
    sig = f"{orc.BACKOFF_SIGNATURE_PREFIX}ops.policy_watch"
    # control: the same history without the exemption is parked (what production had)
    with db.session() as s:
        progress = orc._progress(s, since=datetime.now(timezone.utc) - timedelta(hours=72))
    assert progress["ops.policy_watch"]["identical_tail"], progress["ops.policy_watch"]
    real = orc.LIVENESS_JOB_TYPES
    orc.LIVENESS_JOB_TYPES = real - {"ops.policy_watch"}
    try:
        with db.session() as s:
            applied = orc._free_poll_backoff(s, progress, now=datetime.now(timezone.utc))
        assert any(a["job_type"] == "ops.policy_watch" for a in applied["applied"]), applied
        assert "ops.policy_watch" in orc.suspended_job_types(db)
    finally:
        orc.LIVENESS_JOB_TYPES = real
    # with the exemption: the park left from before is not in force, and the sweep lifts it
    assert "ops.policy_watch" not in orc.suspended_job_types(db)
    FLP.E._run_job(db, "orchestrator", "ops.thrash", {}, "thrash-policy")
    with db.session() as s:
        assert s.scalar(select(Incident).where(Incident.signature == sig,
                                               Incident.resolved.is_(False))) is None
    assert "ops.policy_watch" not in orc.suspended_job_types(db)
    _scheduled("ops.policy_watch", advance_days=1)            # and the cadence still runs it


# ---- parity ---------------------------------------------------------------------------------

def test_5_the_daily_blind_review_writes_the_row_parity_reads_for_a_ready_release():
    from brambleloop.creative import blind_review

    S = _world()
    db, slug = S["db"], S["slug"]
    assert blind_review.current_review(db, slug=slug) is None
    sec = _section("parity")
    assert sec["state"] != pa.PASS and "competitive_blind_review" in sec["unjudged"]
    _scheduled("creative.blind_review")
    row = blind_review.current_review(db, slug=slug)
    assert row is not None and row["slug"] == slug and "materially_inferior" in row
    # absent evidence: nobody has observed this pod, so the review is UNKNOWN and blocks
    assert row["materially_inferior"] is None
    sec = _section("parity")
    assert sec["state"] != pa.PASS and "competitive_blind_review" in sec["unjudged"], sec


class _HeroProvider:
    """test_double: the blind describer for the disclosed hero (free, no network)."""
    model = "claude-sonnet-5"
    cost_per_1k_input_cad = 0.0
    cost_per_1k_output_cad = 0.0

    def see(self, system, prompt, images, max_tokens=0):
        import json

        payload = json.dumps({"object_shown": "a set of hexagon coasters", "object_count": 4,
                              "finished_or_in_progress": "finished", "human_present": False,
                              "text_present": True, "chart_or_diagram": False,
                              "dominant_colours": "cream, wine", "clarity": "clear",
                              "third_party_marks": "none"})

        class R:
            text = payload
            input_tokens = 1200
            output_tokens = 90
        return R()


def _vision_on():
    import test_cert_listing_frames as CLF
    from brambleloop.build2 import executor
    from brambleloop.visual import hero_review
    from brambleloop.visual import inspect as inspection

    gate = executor.GATE_BY_KEY["image_vision"]
    saved = (gate.check, inspection.inspect_image, inspection.describe_image,
             inspection.identify_at_grid, hero_review.review_disclosed_hero)
    real_hero = hero_review.review_disclosed_hero
    gate.check = lambda db_, env: True
    inspection.identify_at_grid = CLF._fake_grid("clear")
    inspection.inspect_image = CLF._fake_vision([])
    inspection.describe_image = CLF._fake_describe(marks="none")
    hero_review.review_disclosed_hero = (
        lambda db_, slug_, **kw: real_hero(db_, slug_, provider=_HeroProvider(),
                                           gate_open=True, store=kw.get("store")))

    def restore():
        (gate.check, inspection.inspect_image, inspection.describe_image,
         inspection.identify_at_grid, hero_review.review_disclosed_hero) = saved
    return restore


def _builds(db, key_part):
    with db.session() as s:
        return [j for j in s.scalars(select(Job).where(Job.job_type == "assets.build"))
                if key_part in (j.idempotency_key or "")]


def test_6_hero_and_frame_review_are_made_by_the_scheduled_sweep_and_parity_passes():
    from brambleloop.creative import blind_review
    import test_blind_review as TB

    S = _world()
    db, slug, version = S["db"], S["slug"], S["version"]
    need = SPL.parity_evidence_needs(db, slug, version)
    assert set(need["missing"]) == {"hero_description", "frame_review"}, need
    # vision closed: the sweep queues nothing (a rebuild would record UNREVIEWED again)
    _scheduled("sale.pipeline_sweep")
    assert not _builds(db, SPL.PARITY_EVIDENCE_KEY)
    sec = _section("parity")
    assert sec["state"] != pa.PASS and "hero" in sec["unjudged"]
    assert sec["frame_review"]["reviewed"] is False
    restore = _vision_on()
    try:
        _scheduled("sale.pipeline_sweep", advance_days=1)     # next hourly window (a day on)
        builds = _builds(db, SPL.PARITY_EVIDENCE_KEY)
        assert len(builds) == 1, [(b.idempotency_key, b.status) for b in builds]
        Worker(db, "w-build", phase=Phase.SHADOW, job_types=["assets.build"],
               lease_seconds=900).run_once()
        with db.session() as s:
            b = s.get(Job, builds[0].id)
            assert b.status is JobStatus.DONE, b.last_error
        need = SPL.parity_evidence_needs(db, slug, version)
        assert need["missing"] == [] and need["not_buildable"] == [], need
        _scheduled("sale.pipeline_sweep", advance_days=1)     # bounded: nothing more to buy
        assert len(_builds(db, SPL.PARITY_EVIDENCE_KEY)) == 1
    finally:
        restore()
    assert SPL.get(db, slug, version, S["rh"])["state"] == SPL.READY
    sec = _section("parity")
    assert sec["dimensions"]["hero"] == "pass", sec
    assert sec["frame_review"]["reviewed"] is True, sec
    # still not PASS: the blind review has no observed benchmark (absent evidence)
    assert sec["state"] != pa.PASS and sec["unjudged"] == ["competitive_blind_review"], sec
    # real-shaped evidence: benchmark galleries observed in this product's pod that are no
    # deeper than ours and carry no video -- the next daily review reaches a verdict
    pod = blind_review.pod_for(slug, dict(blind_review.catalogue_slugs(db))[slug])
    TB._observed_pod(db, pod=pod, media=3, video=False)
    _scheduled("creative.blind_review", advance_days=1)
    row = blind_review.current_review(db, slug=slug)
    assert row["materially_inferior"] is False, row["why"]
    sec = _section("parity")
    assert sec["state"] == pa.PASS, sec
    # stale: a review older than MAX_REVIEW_AGE_DAYS no longer counts
    old = (datetime.now(timezone.utc) - timedelta(days=blind_review.MAX_REVIEW_AGE_DAYS + 1))
    with db.session() as s:
        for r in s.scalars(select(AuditLog).where(AuditLog.action == blind_review.ACTION,
                                                  AuditLog.artifact == slug)):
            r.detail = {**dict(r.detail or {}), "reviewed_at": old.isoformat()}
            r.at = old
    sec = _section("parity")
    assert sec["state"] != pa.PASS and "competitive_blind_review" in sec["unjudged"], sec
    _scheduled("creative.blind_review", advance_days=1)
    assert _section("parity")["state"] == pa.PASS


def test_7_the_card_offers_approve_once_every_section_passes_on_this_evidence():
    from brambleloop.app.command_center import approvals
    from brambleloop.core import owner_grant_keys as ogk

    S = _world()
    db, slug, version = S["db"], S["slug"], S["version"]
    # keep the evidence current for this read (the earlier tests aged and restored it)
    _scheduled("launch.readiness", advance_days=1)
    saved = {k: os.environ.get(k) for k in ("BRAMBLELOOP_PUBLISH_AUTHORISED",
                                            "BRAMBLELOOP_OPS_TOKEN",
                                            ogk.SIGNING_KEY_VAR, ogk.VERIFY_KEY_VAR)}
    try:
        os.environ.update({"BRAMBLELOOP_OPS_TOKEN": FLP.OPS,
                           "BRAMBLELOOP_PUBLISH_AUTHORISED": "1", **ogk.generate_keypair()})
        cards = {c["card_id"]: c for c in approvals.inbox(db).get("cards") or []
                 if isinstance(c, dict) and c.get("card_id")}
        card = cards[f"publication:{slug}@{version}"]
        states = {e["label"]: e["state"] for e in card["evidence"]}
        for section in ("parity", "policy", "rollback"):
            assert states.get(section) == pa.PASS, card["evidence"]
        not_passing = [k for k in pa.GATED_SECTIONS if states.get(k) != pa.PASS]
        assert not_passing == [], card["evidence"]
        assert card["executable"] is True and card["actions"], card
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_8_a_stored_generated_gallery_frame_has_no_review_producer_and_still_blocks():
    """Not fixed (needs a decision): `gallery_persist` stores the certified generated gallery
    at 100+slot as AI_LIFESTYLE_CONCEPT rows; `assets.build` reviews only its own renders, so
    #61 can no longer bind and parity stays not-passing. The re-drive does not buy a review
    that cannot bind."""
    S = _world()
    db, slug, version = S["db"], S["slug"], S["version"]
    with db.session() as s:
        s.add(ListingAsset(product_slug=slug, version=version, position=101,
                           asset_class=SPL.GENERATED_CLASS, role="hero", sha256="ab" * 32,
                           claims={"source": "visual.image_production"}, approved=True,
                           blocked_reasons=[]))
    try:
        need = SPL.parity_evidence_needs(db, slug, version)
        assert need["not_buildable"] == ["frame_review:generated_gallery_frames"], need
        assert "frame_review" not in need["missing"]
        sec = _section("parity")
        assert sec["state"] != pa.PASS and sec["frame_review"]["reviewed"] is False, sec
        restore = _vision_on()
        try:
            before = len(_builds(db, SPL.PARITY_EVIDENCE_KEY))
            _scheduled("sale.pipeline_sweep", advance_days=1)
            assert len(_builds(db, SPL.PARITY_EVIDENCE_KEY)) == before
        finally:
            restore()
    finally:
        with db.session() as s:
            for r in s.scalars(select(ListingAsset).where(ListingAsset.position == 101)):
                s.delete(r)


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
        if FLP._W.get("restore"):
            FLP._W["restore"]()
    print(f"{failed} failed")
    sys.exit(1 if failed else 0)
