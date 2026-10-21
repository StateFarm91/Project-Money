"""The owner's batch-scoped authorisation for the Launch-0 independent image review (B3).

Owner approval, 2026-10-21 (DECISION_LOG `D-W4-LAUNCH-VISION-BATCH`): up to CA$7.07 in total
for the paid independent review of the 59-69 Launch-0 listing images, and for this batch ONLY a
temporary daily ceiling of CA$8.00 for the reviewing agent (`quality_director`). The CA$100
company month is unchanged; nothing else is authorised; the CA$1.00/day ceiling returns by
itself when the batch completes, expires or spends its cap.

No global configuration changes. `agents.registry` still says CA$1.00 for `quality_director`,
and every call outside this batch is checked against exactly that. A call is a batch call only
when all of these hold, checked inside `gateway.anthropic.check_budget_cad`'s budget lock in
the same atomic step that writes its reservation:

* it is made while `reviewing(...)` is active -- set only by `assets.build` for a release this
  batch scopes, on a job the batch itself enqueued;
* it is the reviewing agent's own review task (`AGENT`, `PURPOSE`);
* the batch is OPEN: not completed, not expired, not exhausted (all re-read under the lock);
* the release's stored frames are exactly the frames the batch was activated for, by sha256;
* the release has calls left (`CALLS_PER_FRAME`, the hero's grid read included);
* batch committed + this estimate <= the total cap, and the batch's spend today + this
  estimate <= the batch daily cap.

The company month is still checked first, unchanged. The agent's own day is then checked
against the batch daily cap instead of CA$1.00 -- for this call only. Anything that fails is
refused before the call, with a `spend.refused` row, and the frame stays unreviewed (UNKNOWN,
never PASS). The batch counts every reserved call at its padded estimate, never at less: a
call whose bill is unknown is counted in full and never sent again (`run` enqueues each
release's review once, with a single attempt).
"""
from __future__ import annotations

import contextvars
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base
from ..core.models import utcnow

BATCH_ID = "launch_image_review_2026_10"
DECISION_REF = "D-W4-LAUNCH-VISION-BATCH"
TOTAL_CAP_CAD = 7.07            # the owner's approval, in total
DAILY_CAP_CAD = 8.00            # the owner's temporary daily ceiling, this batch only
AGENT = "quality_director"
PURPOSE = "asset_inspection"    # `visual.inspect.TASK`: the frame review's own task
EXPIRY_DAYS = 14
# The frame review makes at most two vision calls per frame (describe, realism) and one more
# for the hero (identification at grid size). A release is allowed exactly that many.
CALLS_PER_FRAME = 2
HERO_EXTRA_CALLS = 1
JOB_TYPE = "assets.launch_review"
INPUT_KEY = "launch_review_batch"

OPEN, COMPLETED, EXPIRED, EXHAUSTED, REVOKED = ("open", "completed", "expired", "exhausted",
                                                "revoked")
ACTION_ACTIVATED = "launch_review.activated"
ACTION_CLOSED = "launch_review.closed"


class LaunchReviewRefused(Exception):
    """The batch may not do this; nothing was spent."""


class LaunchReviewBatch(Base):
    __tablename__ = "launch_review_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[str] = mapped_column(String(80), index=True)
    decision_ref: Mapped[str] = mapped_column(String(80))
    agent: Mapped[str] = mapped_column(String(64))
    purpose: Mapped[str] = mapped_column(String(64))
    total_cap_cad: Mapped[float] = mapped_column(Float)
    daily_cap_cad: Mapped[float] = mapped_column(Float)
    frame_scope: Mapped[dict] = mapped_column(JSON, default=dict)   # sha -> frame
    releases: Mapped[dict] = mapped_column(JSON, default=dict)      # release -> progress
    authorized_by: Mapped[str] = mapped_column(String(120))
    step_up: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default=OPEN)
    closed_why: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LaunchReviewCall(Base):
    """One reserved review call, written in the same locked step as its reservation."""

    __tablename__ = "launch_review_calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[str] = mapped_column(String(80), index=True)
    release: Mapped[str] = mapped_column(String(120), index=True)
    estimate_cad: Mapped[float] = mapped_column(Float)
    reservation_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


_TABLES = (LaunchReviewBatch.__table__, LaunchReviewCall.__table__)
_ensured: set[int] = set()
_lock = threading.Lock()


def ensure_tables(db) -> None:
    """Created on first use (the `experiments.controlled` pattern): two new tables, no change
    to any existing one."""
    engine = getattr(db, "engine", None) or db.get_bind()
    key = id(engine)
    if key in _ensured:
        return
    with _lock:
        if key not in _ensured:
            for t in _TABLES:
                t.create(engine, checkfirst=True)
            _ensured.add(key)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _now(now: datetime | None = None) -> datetime:
    return _aware(now) or datetime.now(timezone.utc)


# ---- scope -----------------------------------------------------------------------------------

def launch0_releases() -> list[str]:
    from ..runtime.release_recovery import launch0_releases as rel

    return [f"{c.slug}@{c.version}" for c in rel()]


def frame_scope(db) -> dict:
    """The exact frames to review: every stored listing frame of every Launch-0 release at the
    code's version, by sha256. `missing` names releases with no stored frames."""
    from sqlalchemy import select

    from ..core.models import ListingAsset

    scope, missing = {}, []
    with db.session() as s:
        for release in launch0_releases():
            slug, version = release.split("@", 1)
            rows = list(s.scalars(select(ListingAsset).where(
                ListingAsset.product_slug == slug, ListingAsset.version == version)
                .order_by(ListingAsset.position)))
            if not rows or any(not r.sha256 for r in rows):
                missing.append(release)
                continue
            for r in rows:
                scope[r.sha256] = {"release": release, "position": r.position,
                                   "role": r.role}
    return {"frames": scope, "missing": missing}


def max_calls(frames: list[dict]) -> int:
    return sum(CALLS_PER_FRAME + (HERO_EXTRA_CALLS if f.get("role") == "hero" else 0)
               for f in frames)


# ---- activation ------------------------------------------------------------------------------

def activate(db, *, by: str, stepped_up: bool, now: datetime | None = None) -> dict:
    """The owner's activation, behind the owner session and step-up. One batch, once."""
    from sqlalchemy import select

    from ..core.models import AuditLog

    if not stepped_up:
        raise LaunchReviewRefused("activating the launch image review needs the owner's step-up")
    if not str(by or "").strip():
        raise LaunchReviewRefused("an activation names the owner who gave it")
    ensure_tables(db)
    now = _now(now)
    with db.session() as s:
        if s.scalar(select(LaunchReviewBatch).where(
                LaunchReviewBatch.batch_id == BATCH_ID)) is not None:
            raise LaunchReviewRefused(f"{BATCH_ID} was already activated; it runs once")
    scope = frame_scope(db)
    if scope["missing"] or not scope["frames"]:
        raise LaunchReviewRefused(
            "not every Launch-0 release has stored listing frames yet, so the scope cannot be "
            f"fixed: {scope['missing']}. Activate after the listings release has built them")
    releases = {}
    for sha, f in scope["frames"].items():
        releases.setdefault(f["release"], {"frames": {}, "state": "pending"})
        releases[f["release"]]["frames"][str(f["position"])] = {"sha256": sha,
                                                                "role": f["role"]}
    with db.session() as s:
        s.add(LaunchReviewBatch(
            batch_id=BATCH_ID, decision_ref=DECISION_REF, agent=AGENT, purpose=PURPOSE,
            total_cap_cad=TOTAL_CAP_CAD, daily_cap_cad=DAILY_CAP_CAD,
            frame_scope=scope["frames"], releases=releases, authorized_by=str(by)[:120],
            step_up=True, status=OPEN, created_at=now,
            expires_at=now + timedelta(days=EXPIRY_DAYS)))
        s.add(AuditLog(actor=str(by)[:64], action=ACTION_ACTIVATED, artifact=BATCH_ID,
                       detail={"decision_ref": DECISION_REF, "total_cap_cad": TOTAL_CAP_CAD,
                               "daily_cap_cad": DAILY_CAP_CAD, "agent": AGENT,
                               "frames": len(scope["frames"]), "releases": len(releases),
                               "expires_at": (now + timedelta(days=EXPIRY_DAYS)).isoformat(),
                               "step_up": True}))
    return state(db, now=now)


# ---- the lifecycle: closes by itself ---------------------------------------------------------

def _committed(session, batch_id: str) -> float:
    from sqlalchemy import func, select

    return float(session.scalar(select(func.coalesce(func.sum(LaunchReviewCall.estimate_cad),
                                                     0.0))
                                .where(LaunchReviewCall.batch_id == batch_id)) or 0.0)


def _today(session, batch_id: str, now: datetime) -> float:
    from sqlalchemy import func, select

    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return float(session.scalar(select(func.coalesce(func.sum(LaunchReviewCall.estimate_cad),
                                                     0.0))
                                .where(LaunchReviewCall.batch_id == batch_id,
                                       LaunchReviewCall.at >= start)) or 0.0)


def min_call_estimate() -> float:
    """The cheapest review call this batch can make (a describe call), padded."""
    from ..gateway import anthropic as gw
    from ..gateway import routing
    from ..visual import inspect as I

    model = routing.route(PURPOSE)[1].model
    return gw.estimate_cad(model, input_tokens=len(I.describe_prompt()) // 4
                           + gw.IMAGE_TOKENS_ESTIMATE, output_tokens=I.DESCRIBE_MAX_TOKENS)


def _close(session, batch, status: str, why: str, now: datetime) -> None:
    from ..core.models import AuditLog

    batch.status, batch.closed_why, batch.closed_at = status, why[:500], now
    session.add(AuditLog(actor="finance", action=ACTION_CLOSED, artifact=batch.batch_id,
                         detail={"status": status, "why": why[:500],
                                 "committed_cad": round(_committed(session, batch.batch_id),
                                                        6),
                                 "daily_ceiling_now_cad": "registry (CA$1.00 for "
                                                          f"{batch.agent})"}))


def close_if_due(session, batch, now: datetime | None = None) -> str:
    """Completed, expired or exhausted -> closed, in code. Returns the status after."""
    now = _now(now)
    if batch.status != OPEN:
        return batch.status
    if now >= _aware(batch.expires_at):
        _close(session, batch, EXPIRED, f"authorisation expired at "
               f"{_aware(batch.expires_at).isoformat()}", now)
    elif batch.releases and all(r.get("state") in ("done", "interrupted")
                                for r in batch.releases.values()):
        _close(session, batch, COMPLETED, "every release in scope was reviewed (or stopped "
               "with its bill unknown, never resent)", now)
    else:
        try:
            floor = min_call_estimate()
        except Exception:  # noqa: BLE001 - unpriceable: nothing more can be spent
            floor = float("inf")
        if batch.total_cap_cad - _committed(session, batch.batch_id) < floor:
            _close(session, batch, EXHAUSTED, f"the CA${batch.total_cap_cad:.2f} cap is spent "
                   "(no further call fits)", now)
    return batch.status


def _batch(session, batch_id: str = BATCH_ID):
    from sqlalchemy import select

    return session.scalar(select(LaunchReviewBatch).where(
        LaunchReviewBatch.batch_id == batch_id).order_by(LaunchReviewBatch.id.desc()))


def state(db, *, now: datetime | None = None) -> dict:
    """The batch as it stands, closing it first if it is due."""
    ensure_tables(db)
    now = _now(now)
    with db.session() as s:
        b = _batch(s)
        if b is None:
            return {"batch_id": BATCH_ID, "status": "not_activated",
                    "effective_daily_ceiling_cad": registry_ceiling(db)}
        close_if_due(s, b, now)
        committed = _committed(s, b.batch_id)
        return {"batch_id": b.batch_id, "status": b.status, "decision_ref": b.decision_ref,
                "agent": b.agent, "total_cap_cad": b.total_cap_cad,
                "daily_cap_cad": b.daily_cap_cad, "committed_cad": round(committed, 6),
                "remaining_cad": round(b.total_cap_cad - committed, 6),
                "frames": len(b.frame_scope or {}),
                "releases": {k: v.get("state") for k, v in (b.releases or {}).items()},
                "expires_at": _aware(b.expires_at).isoformat(),
                "closed_why": b.closed_why,
                "effective_daily_ceiling_cad": (b.daily_cap_cad if b.status == OPEN
                                                else registry_ceiling(db)),
                "note": "the batch ceiling applies only to this batch's review calls; every "
                        "other call is checked against the registry ceiling"}


def registry_ceiling(db) -> float:
    from ..agents.registry import PermissionDenied, Registry

    try:
        return float(Registry(db).get(AGENT).daily_cost_ceiling_cad or 0.0)
    except PermissionDenied:
        return 0.0


# ---- the per-call grant (inside the budget lock) ---------------------------------------------

_ACTIVE: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "launch_review_active", default=None)


@contextmanager
def reviewing(batch_id: str, release: str, frames: list[dict]):
    """Marks the calls made inside as this batch's review of `release`'s `frames`
    ([{position, role, sha256}]). Set only by `assets.build` on a batch-enqueued job."""
    token = _ACTIVE.set({"batch_id": batch_id, "release": release,
                         "frames": [dict(f) for f in frames]})
    try:
        yield
    finally:
        _ACTIVE.reset(token)


def active() -> dict | None:
    return _ACTIVE.get()


def grant_in(session, *, agent: str, purpose: str, estimate: float,
             now: datetime | None = None) -> dict | None:
    """None: not a batch call (the registry ceiling applies, unchanged). Otherwise either
    {"refused": why} or the grant {"daily_cap_cad", "batch_id", "release"}."""
    ctx = _ACTIVE.get()
    if ctx is None or agent != AGENT or purpose != PURPOSE:
        return None
    now = _now(now)
    # No table creation here: this runs inside the budget lock, and the context is only ever
    # set after `scoped_frames` has ensured the tables.
    b = _batch(session, ctx["batch_id"])
    if b is None:
        return {"refused": f"launch review batch {ctx['batch_id']} does not exist"}
    status = close_if_due(session, b, now)
    if status != OPEN:
        return {"refused": f"launch review batch {b.batch_id} is {status}: {b.closed_why}"}
    scope = b.frame_scope or {}
    in_scope = {sha: f for sha, f in scope.items() if f.get("release") == ctx["release"]}
    asked = {str(f.get("sha256")) for f in ctx["frames"]}
    if not asked or asked != set(in_scope):
        return {"refused": (f"{ctx['release']}: the frames under review are not exactly the "
                            f"frames this batch was activated for ({len(asked)} asked, "
                            f"{len(in_scope)} in scope); out of scope, not sent")}
    from sqlalchemy import func, select

    used = int(session.scalar(select(func.count()).select_from(LaunchReviewCall).where(
        LaunchReviewCall.batch_id == b.batch_id,
        LaunchReviewCall.release == ctx["release"])) or 0)
    allowed_calls = max_calls(list(in_scope.values()))
    if used >= allowed_calls:
        return {"refused": f"{ctx['release']}: all {allowed_calls} review calls this batch "
                           "allows for its frames are used"}
    committed = _committed(session, b.batch_id)
    if committed + estimate > b.total_cap_cad + 1e-9:
        return {"refused": f"launch review batch total CA${b.total_cap_cad:.2f}: "
                           f"CA${committed:.4f} committed, this call CA${estimate:.4f}"}
    today = _today(session, b.batch_id, now)
    if today + estimate > b.daily_cap_cad + 1e-9:
        return {"refused": f"launch review batch daily cap CA${b.daily_cap_cad:.2f}: "
                           f"CA${today:.4f} today, this call CA${estimate:.4f}"}
    return {"batch_id": b.batch_id, "release": ctx["release"],
            "daily_cap_cad": float(b.daily_cap_cad)}


def record_in(session, grant: dict, *, estimate: float, reservation_id,
              now: datetime | None = None) -> None:
    session.add(LaunchReviewCall(batch_id=grant["batch_id"], release=grant["release"],
                                 estimate_cad=float(estimate), reservation_id=reservation_id,
                                 at=_now(now)))


# ---- the run ---------------------------------------------------------------------------------

def _set_release(db, release: str, state_: str, **extra) -> None:
    from sqlalchemy.orm.attributes import flag_modified

    with db.session() as s:
        b = _batch(s)
        rel = dict((b.releases or {}).get(release) or {})
        rel.update(state=state_, **extra)
        b.releases = {**(b.releases or {}), release: rel}
        flag_modified(b, "releases")
        close_if_due(s, b)


def scoped_frames(db, slug: str, version: str) -> list[dict] | None:
    """The batch's frames for this release, or None when the batch does not cover it."""
    ensure_tables(db)
    with db.session() as s:
        b = _batch(s)
        if b is None:
            return None
        rel = (b.releases or {}).get(f"{slug}@{version}")
        if not rel:
            return None
        return [{"position": int(p), **f} for p, f in sorted(rel["frames"].items(),
                                                              key=lambda kv: int(kv[0]))]


def review_started(db, slug: str, version: str) -> None:
    _set_release(db, f"{slug}@{version}", "reviewing")


def review_finished(db, slug: str, version: str, *, unreviewed: list) -> None:
    _set_release(db, f"{slug}@{version}", "done", unreviewed=list(unreviewed))


def run(db, enqueue, *, now: datetime | None = None) -> dict:
    """Enqueue each scoped release's review once (one attempt: a bill-unknown call is never
    resent). A release found mid-review from an earlier attempt is marked interrupted, not
    retried; its frames stay unreviewed, which the gate reads as UNKNOWN."""
    from sqlalchemy import desc, select

    from ..core.models import Job, JobStatus

    st = state(db, now=now)
    if st["status"] != OPEN:
        return {"ran": False, "why": f"batch {st['status']}: {st.get('closed_why') or ''}"}
    started, interrupted, waiting = [], [], []
    for release, progress in sorted(st["releases"].items()):
        if progress == "reviewing":
            _set_release(db, release, "interrupted",
                         why="a review attempt did not finish; its calls' bills are unknown, "
                             "so it is not resent")
            interrupted.append(release)
            continue
        if progress != "pending":
            continue
        slug, version = release.split("@", 1)
        with db.session() as s:
            last = next((dict(j.inputs or {}) for j in s.scalars(
                select(Job).where(Job.job_type == "assets.build",
                                  Job.status == JobStatus.DONE).order_by(desc(Job.id)))
                if (j.inputs or {}).get("slug") == slug
                and (j.inputs or {}).get("version") == version), None)
        if last is None:
            waiting.append(release)
            continue
        job = enqueue({**last, INPUT_KEY: BATCH_ID},
                      f"{BATCH_ID}:{release}")
        if job is not None:
            _set_release(db, release, "queued")
            started.append(release)
    return {"ran": True, "queued": started, "interrupted": interrupted,
            "no_completed_build": waiting}
