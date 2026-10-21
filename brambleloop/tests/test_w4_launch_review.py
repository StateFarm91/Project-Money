"""D-W4-LAUNCH-VISION-BATCH: the owner's batch-scoped authorisation of the Launch-0 image review.

The owner approved up to CA$7.07 in total, and a temporary CA$8.00 daily ceiling for
`quality_director` for this batch only, reverting to CA$1.00 by itself. The CA$100 month is
unchanged. These tests drive the real budget path (`gateway.anthropic.check_budget`, the one
every review call takes) and prove: a reservation before each call; the batch total, the batch
day and the company month all enforced, with nothing sent once any is exhausted; out-of-scope
frames refused; the ceiling back at CA$1.00 when the batch completes, expires or is spent; a
refused call leaves the frame UNKNOWN, never PASS; and no change to the CA$100 ceiling or to the
registry's CA$1.00.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

_TMP = tempfile.mkdtemp(prefix="w4_launch_review_")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ.pop("BRAMBLELOOP_MODEL_MONTHLY_CEILING_CAD", None)

from sqlalchemy import func, select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, ListingAsset, SpendReservation  # noqa: E402
from brambleloop.finance import launch_review as LR  # noqa: E402
from brambleloop.gateway import anthropic as gw  # noqa: E402
from brambleloop.visual import inspect as I  # noqa: E402

# Activation now requires the image_vision gate open (delta review N2). These tests run with it
# open unless a test says otherwise; `test_n2_*` closes it explicitly.
_REAL_VISION_OPEN = LR.vision_open
LR.vision_open = lambda db: True

MODEL = "claude-sonnet-5"
T0 = datetime(2026, 10, 22, 9, 0, tzinfo=timezone.utc)
_N = [0]


def _db():
    _N[0] += 1
    db = Database(f"sqlite:///{_TMP}/lr{_N[0]}.db")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _frames(db, per_release=6):
    """Stored frames for every Launch-0 release (a fixture: the scope reads these rows)."""
    with db.session() as s:
        for r_i, release in enumerate(LR.launch0_releases()):
            slug, version = release.split("@", 1)
            for pos in range(1, per_release + 1):
                s.add(ListingAsset(product_slug=slug, version=version, position=pos,
                                   asset_class="disclosed_render",
                                   role="hero" if pos == 1 else "materials",
                                   sha256=f"{r_i:02d}{pos:02d}".ljust(64, "a")))


def _activated(db, **kw):
    _frames(db, **kw)
    return LR.activate(db, by="owner", stepped_up=True, now=T0)


def _release_frames(db, release):
    slug, version = release.split("@", 1)
    return [{"position": f["position"], "role": f["role"], "sha256": f["sha256"]}
            for f in LR.scoped_frames(db, slug, version)]


def _describe_call(db, now=T0):
    """Exactly the budget check `visual.inspect`'s describe call makes."""
    return gw.check_budget(db, model=MODEL,
                           input_tokens=len(I.describe_prompt()) // 4 + gw.IMAGE_TOKENS_ESTIMATE,
                           max_tokens=I.DESCRIBE_MAX_TOKENS, agent=I.AGENT, purpose=I.TASK,
                           now=now)


def _reservations(db):
    with db.session() as s:
        return int(s.scalar(select(func.count()).select_from(SpendReservation)) or 0)


def _refusals(db, which):
    with db.session() as s:
        return [r.detail for r in s.scalars(select(AuditLog).where(
            AuditLog.action == "spend.refused")) if (r.detail or {}).get("which") == which]


# ---- activation -----------------------------------------------------------------------------

def test_activation_needs_step_up_runs_once_and_fixes_the_owners_numbers():
    db = _db()
    _frames(db)
    try:
        LR.activate(db, by="owner", stepped_up=False, now=T0)
        raise AssertionError("activated without step-up")
    except LR.LaunchReviewRefused:
        pass
    st = LR.activate(db, by="owner", stepped_up=True, now=T0)
    assert st["status"] == LR.OPEN and st["frames"] == 60
    assert st["total_cap_cad"] == 7.07 and st["daily_cap_cad"] == 8.00
    assert st["decision_ref"] == "D-W4-LAUNCH-VISION-BATCH" and st["agent"] == "quality_director"
    assert st["expires_at"] == (T0 + timedelta(days=14)).isoformat()
    try:
        LR.activate(db, by="owner", stepped_up=True, now=T0)
        raise AssertionError("activated twice")
    except LR.LaunchReviewRefused:
        pass


def test_activation_refuses_until_every_launch0_release_has_stored_frames():
    db = _db()
    with db.session() as s:
        s.add(ListingAsset(product_slug="cloudline-baby-blanket", version="1.2.0", position=1,
                           asset_class="x", role="hero", sha256="c" * 64))
    try:
        LR.activate(db, by="owner", stepped_up=True, now=T0)
        raise AssertionError("activated on a partial scope")
    except LR.LaunchReviewRefused as exc:
        assert "market-basket-small@1.2.0" in str(exc)


# ---- reservation, caps, scope -----------------------------------------------------------------

def test_outside_the_batch_the_ceiling_is_the_unchanged_ca1():
    db = _db()
    _activated(db)
    sent = 0
    try:
        for _ in range(40):
            _describe_call(db)
            sent += 1
    except gw.AgentCeilingExceeded:
        pass
    est = gw.estimate_cad(MODEL, input_tokens=len(I.describe_prompt()) // 4
                          + gw.IMAGE_TOKENS_ESTIMATE, output_tokens=I.DESCRIBE_MAX_TOKENS)
    assert sent == int(1.0 // est), (sent, est)                      # CA$1.00 / day
    with db.session() as s:
        assert s.scalar(select(func.count()).select_from(LR.LaunchReviewCall)) == 0


def test_every_batch_call_is_reserved_before_it_is_made_and_counted_by_the_batch():
    db = _db()
    _activated(db)
    release = LR.launch0_releases()[0]
    with LR.reviewing(LR.BATCH_ID, release, _release_frames(db, release)):
        before = _reservations(db)
        got = _describe_call(db)
    assert got["reservation_id"] is not None and _reservations(db) == before + 1
    assert got["agent_permission"]["daily_ceiling_cad"] == 8.00
    assert got["agent_permission"]["agent_ceiling_cad"] == 1.0           # registry untouched
    with db.session() as s:
        call = s.scalar(select(LR.LaunchReviewCall))
        assert call.reservation_id == got["reservation_id"]
        assert call.estimate_cad == got["estimate_cad"] and call.release == release


def test_the_batch_total_is_enforced_and_nothing_is_sent_once_it_is_spent():
    db = _db()
    _activated(db, per_release=8)        # 170 calls possible: more than CA$7.07 buys
    sent, refused_at = 0, None
    for release in LR.launch0_releases():
        frames = _release_frames(db, release)
        with LR.reviewing(LR.BATCH_ID, release, frames):
            for _ in range(LR.max_calls(frames)):
                try:
                    _describe_call(db)
                    sent += 1
                except gw.BudgetExceeded as exc:
                    refused_at = str(exc)
                    break
        if refused_at:
            break
    st = LR.state(db, now=T0)
    assert st["committed_cad"] <= 7.07 + 1e-9
    # the total binds: either this call would cross CA$7.07, or what is left is less than
    # the cheapest call and the batch closed itself as exhausted
    assert refused_at and ("batch total CA$7.07" in refused_at
                           or "the CA$7.07 cap is spent" in refused_at), refused_at
    assert st["remaining_cad"] < LR.min_call_estimate() + 0.06
    assert _refusals(db, "launch_review_batch")
    # exhausted: closed in code, and the ceiling is CA$1.00 again
    assert st["status"] == LR.EXHAUSTED and st["effective_daily_ceiling_cad"] == 1.0
    before = _reservations(db)
    release = LR.launch0_releases()[-1]
    with LR.reviewing(LR.BATCH_ID, release, _release_frames(db, release)):
        try:
            _describe_call(db)
            raise AssertionError("sent after the batch was spent")
        except gw.BudgetExceeded as exc:
            assert "exhausted" in str(exc)
    assert _reservations(db) == before                                # nothing reserved


def test_the_batch_daily_cap_is_enforced():
    db = _db()
    _activated(db)
    with db.session() as s:
        s.scalar(select(LR.LaunchReviewBatch)).daily_cap_cad = 0.10   # fixture: a tight day
    release = LR.launch0_releases()[0]
    with LR.reviewing(LR.BATCH_ID, release, _release_frames(db, release)):
        _describe_call(db)
        _describe_call(db)
        before = _reservations(db)
        try:
            _describe_call(db)
            raise AssertionError("the batch day was exceeded")
        except gw.BudgetExceeded as exc:
            assert "daily cap" in str(exc)
    assert _reservations(db) == before


def test_the_company_month_still_binds_inside_the_batch_and_is_unchanged():
    from brambleloop.finance import reservations

    db = _db()
    _activated(db)
    assert gw.monthly_ceiling_cad() == 100.0
    reservations.reserve(db, amount_cad=99.99, holder="someone-else", agent="other",
                         purpose="fixture", now=T0, ttl_seconds=3600)
    release = LR.launch0_releases()[0]
    with LR.reviewing(LR.BATCH_ID, release, _release_frames(db, release)):
        try:
            _describe_call(db)
            raise AssertionError("the month was crossed")
        except gw.BudgetExceeded as exc:
            assert not isinstance(exc, gw.AgentCeilingExceeded)
    assert _refusals(db, "monthly_ceiling")
    assert gw.monthly_ceiling_cad() == 100.0
    assert LR.registry_ceiling(db) == 1.0


def test_frames_outside_the_scope_are_refused():
    db = _db()
    _activated(db)
    release = LR.launch0_releases()[0]
    frames = _release_frames(db, release)
    swapped = frames[:-1] + [{**frames[-1], "sha256": "f" * 64}]      # one frame re-rendered
    before = _reservations(db)
    with LR.reviewing(LR.BATCH_ID, release, swapped):
        try:
            _describe_call(db)
            raise AssertionError("an out-of-scope frame was reviewed on the batch")
        except gw.BudgetExceeded as exc:
            assert "out of scope" in str(exc)
    with LR.reviewing(LR.BATCH_ID, "not-launch0@1.0.0", frames):
        try:
            _describe_call(db)
            raise AssertionError("another release was reviewed on the batch")
        except gw.BudgetExceeded:
            pass
    assert _reservations(db) == before


def test_a_release_gets_no_more_calls_than_its_frames_need():
    db = _db()
    _activated(db)
    release = LR.launch0_releases()[0]
    frames = _release_frames(db, release)
    with LR.reviewing(LR.BATCH_ID, release, frames):
        for _ in range(LR.max_calls(frames)):                         # 3 + 5 x 2 = 13
            _describe_call(db)
        try:
            _describe_call(db)
            raise AssertionError("a 14th call")
        except gw.BudgetExceeded as exc:
            assert "review calls" in str(exc)


# ---- revert: completed, expired, exhausted (exhausted above) ----------------------------------

def _ceiling_is_back(db, now):
    st = LR.state(db, now=now)
    assert st["status"] != LR.OPEN and st["effective_daily_ceiling_cad"] == 1.0, st
    release = LR.launch0_releases()[0]
    with LR.reviewing(LR.BATCH_ID, release, _release_frames(db, release)):
        try:
            _describe_call(db, now=now)
            raise AssertionError("a closed batch still raised the ceiling")
        except gw.BudgetExceeded:
            pass
    return st


def test_the_ceiling_reverts_when_the_batch_completes():
    db = _db()
    _activated(db)
    for release in LR.launch0_releases():
        slug, version = release.split("@", 1)
        LR.review_started(db, slug, version)
        with LR.reviewing(LR.BATCH_ID, release, _release_frames(db, release)):
            _describe_call(db)                    # a real (reserved) review call
        LR.review_finished(db, slug, version, unreviewed=[])
    st = _ceiling_is_back(db, T0)
    assert st["status"] == LR.COMPLETED and st["releases_reviewed"] == st["releases_total"]
    with db.session() as s:
        assert s.scalar(select(AuditLog).where(AuditLog.action == LR.ACTION_CLOSED)) is not None


def test_the_ceiling_reverts_when_the_authorisation_expires():
    db = _db()
    _activated(db)
    st = _ceiling_is_back(db, T0 + timedelta(days=14, seconds=1))
    assert st["status"] == LR.EXPIRED


# ---- UNKNOWN is never PASS ------------------------------------------------------------------

class _FakeProvider:
    model = MODEL
    cost_per_1k_input_cad = 0.0
    cost_per_1k_output_cad = 0.0

    def __init__(self):
        self.sent = 0

    def see(self, *a, **kw):
        self.sent += 1
        raise AssertionError("a refused call reached the provider")


def test_a_refused_review_call_leaves_the_frame_undescribed_never_passed():
    from brambleloop.runtime.release import frame_review_state  # noqa: F401  (gate unchanged)

    db = _db()
    _activated(db)
    with db.session() as s:
        s.scalar(select(LR.LaunchReviewBatch)).daily_cap_cad = 0.0    # nothing fits today
    release = LR.launch0_releases()[0]
    provider = _FakeProvider()
    img = os.path.join(_TMP, "frame.png")
    Path(img).write_bytes(b"\x89PNG\r\n\x1a\n")
    with LR.reviewing(LR.BATCH_ID, release, _release_frames(db, release)):
        out = I.describe_image(img, db=db, provider=provider, claim={"shows_text": True})
    assert provider.sent == 0
    assert out["described"] is False and "daily cap" in out["description_error"]
    # the frame verdict made from that reading is not `clear`, which the publish path reads
    # as not independently reviewed (UNKNOWN), never PASS
    from brambleloop.visual import frame_role
    verdict = frame_role.verdict(described=False, semantic_problems=[], marks=[], checks={})
    assert verdict["verdict"] != "clear"


# ---- the run: once per release, never resent -------------------------------------------------

def test_the_run_queues_each_release_once_and_never_resends_an_interrupted_one():
    from brambleloop.core.models import Job, JobStatus

    db = _db()
    _activated(db)
    releases = LR.launch0_releases()
    with db.session() as s:
        for release in releases[:2]:
            slug, version = release.split("@", 1)
            s.add(Job(agent="publishing", job_type="assets.build", status=JobStatus.DONE,
                      inputs={"slug": slug, "version": version, "cir": {}}))
    queued: list = []

    def enqueue(inputs, key):
        queued.append((key, inputs))
        return object()

    out = LR.run(db, enqueue)
    assert out["queued"] == sorted(releases[:2])
    assert all(i[LR.INPUT_KEY] == LR.BATCH_ID for _, i in queued)
    assert sorted(out["no_completed_build"]) == sorted(releases[2:])
    again = LR.run(db, enqueue)
    assert again["queued"] == [] and len(queued) == 2                 # never twice
    slug, version = releases[0].split("@", 1)
    LR.review_started(db, slug, version)                              # a crash mid-review
    third = LR.run(db, enqueue)
    assert third["interrupted"] == [releases[0]] and len(queued) == 2


def test_a_model_reservation_then_a_continuity_export_succeeds():
    """Integrator defect: the budget path imports this module, registering its tables in
    Base; continuity.export then read a table no process had created. They are created at
    boot (`Database.create_all`) now."""
    from brambleloop.core import continuity

    _N[0] += 1
    db = Database(f"sqlite:///{_TMP}/export{_N[0]}.db")
    db.create_all()
    Registry(db).seed_defaults()
    from sqlalchemy import inspect
    assert {"launch_review_batches", "launch_review_calls"} <= set(inspect(db.engine)
                                                                    .get_table_names())
    _describe_call(db)                                   # a model reservation
    out = continuity.export(db, os.path.join(_TMP, f"export{_N[0]}"))
    assert out.tables and "launch_review_batches" in {t.name for t in out.tables}, out


# ---- delta review N2 -------------------------------------------------------------------------

def test_n2_activation_is_refused_while_the_vision_gate_is_closed():
    db = _db()
    _frames(db)
    LR.vision_open = lambda db: False
    try:
        LR.activate(db, by="owner", stepped_up=True, now=T0)
        raise AssertionError("activated with the vision gate closed")
    except LR.LaunchReviewRefused as exc:
        assert "image_vision" in str(exc)
    finally:
        LR.vision_open = lambda db: True
    assert _REAL_VISION_OPEN(_db()) is not True              # a fresh database: closed


def test_n2_a_release_with_no_review_call_is_not_counted_as_reviewed():
    db = _db()
    _activated(db)
    release = LR.launch0_releases()[0]
    slug, version = release.split("@", 1)
    LR.review_started(db, slug, version)
    LR.review_finished(db, slug, version, unreviewed=["1", "2"])   # every call refused
    st = LR.state(db, now=T0)
    assert st["releases"][release] == "pending" and st["releases_reviewed"] == 0
    assert st["status"] == LR.OPEN


def test_n2_a_batch_that_spent_nothing_is_unused_and_can_be_reactivated_in_its_expiry():
    db = _db()
    first = _activated(db)
    for release in LR.launch0_releases():                 # every attempt interrupted, CA$0
        slug, version = release.split("@", 1)
        LR.review_started(db, slug, version)
    LR.run(db, lambda inputs, key: None)                   # marks them interrupted
    st = LR.state(db, now=T0)
    assert st["status"] == LR.UNUSED and st["committed_cad"] == 0
    again = LR.activate(db, by="owner", stepped_up=True, now=T0 + timedelta(days=1))
    assert again["status"] == LR.OPEN and again["expires_at"] == first["expires_at"]
    try:
        LR.activate(db, by="owner", stepped_up=True, now=T0 + timedelta(days=1))
        raise AssertionError("an open batch was activated again")
    except LR.LaunchReviewRefused:
        pass


def test_n2_a_stuck_queued_release_is_requeued_and_never_blocks_the_batch():
    from brambleloop.core.models import Job, JobStatus
    from brambleloop.queue.durable import JobQueue

    db = _db()
    _activated(db)
    release = LR.launch0_releases()[0]
    slug, version = release.split("@", 1)
    with db.session() as s:
        s.add(Job(agent="publishing", job_type="assets.build", status=JobStatus.DONE,
                  inputs={"slug": slug, "version": version, "cir": {}}))
    keys = []

    def enqueue(inputs, key):
        keys.append(key)
        return JobQueue(db).enqueue("publishing", "assets.build", inputs, idempotency_key=key,
                                    max_attempts=1)

    LR.run(db, enqueue)
    assert keys == [f"{LR.BATCH_ID}:{release}"]
    with db.session() as s:                                # the batch build died early
        s.scalar(select(Job).where(Job.idempotency_key == keys[0])).status = JobStatus.DEAD
    out = LR.run(db, enqueue)
    assert out["requeued"] == [release] and keys[-1] == f"{LR.BATCH_ID}:{release}:2"


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback
                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
