"""Identity drift across batches and over time, not only frame by frame (#201).

`identity.drift_check` judges one frame against the frozen reference pack, and a frame that
drifts is refused. What that cannot see is the failure #201 names beside it: *gradual* drift
-- a face, a hairline, an apparent age or a rendering style that moves a little each batch,
every frame individually within tolerance or unreadable, until the canonical woman is
somebody else. That is a property of a series, so this keeps one.

Each `assets.model_photography` record carries the per-dimension verdicts its identity check
produced (`identity.dimensions`: match / drift / unmeasurable). Frames are grouped into
batches by the job that made them, and per batch each dimension gets a drift share over the
frames where it was readable. A dimension is **drifting gradually** when its share rises
across the last `TREND_BATCHES` batches without falling, or when the latest window's share
exceeds the earlier window's by `RISE`. An unreadable dimension is never counted as a match
-- the same rule the per-frame gate follows.

The daily reading is persisted (`OperatingReading`, kind `visual.identity_drift`) so the
series outlives audit retention, and a detected trend opens one incident that halts the
model-bearing publication path until the series stops rising; the per-frame gate already
refuses the drifted frames themselves, which is the "regenerate before release" half.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

KIND = "visual.identity_drift"
SIGNATURE = "identity_drift_series:"
WINDOW_DAYS = 60
TREND_BATCHES = 3
RISE = 0.25
MIN_READABLE = 2


def series(db, *, now: datetime | None = None) -> dict:
    from sqlalchemy import select

    from ..core.models import AuditLog
    from ..publish import model_photography
    from . import identity

    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=WINDOW_DAYS)
    with db.session() as s:
        rows = [(r.id, r.job_id, r.at, dict(r.detail or {})) for r in s.scalars(
            select(AuditLog).where(AuditLog.action == model_photography.ACTION)
            .order_by(AuditLog.id))]
    batches: dict[str, dict] = {}
    for rid, job_id, at, detail in rows:
        at = at if at is None or at.tzinfo else at.replace(tzinfo=timezone.utc)
        if at is not None and at < since:
            continue
        dims = ((detail.get("identity") or {}).get("dimensions")
                or (detail.get("identity") or {}).get("observed") or {})
        if not dims:
            continue
        # A batch is the job that rendered it; frames recorded without a job group by day.
        key = f"job:{job_id}" if job_id else f"day:{(at or now).date().isoformat()}"
        b = batches.setdefault(key, {"at": (at or now).isoformat(), "frames": 0,
                                     "counts": {}})
        b["frames"] += 1
        for d in identity.DRIFT_DIMENSIONS:
            v = str(dims.get(d) or identity.UNMEASURABLE).lower()
            c = b["counts"].setdefault(d, {"match": 0, "drift": 0, "unmeasurable": 0})
            c[v if v in c else "unmeasurable"] += 1
    ordered = sorted(batches.items(), key=lambda kv: kv[1]["at"])
    per_dim: dict[str, list] = {}
    for _key, b in ordered:
        for d, c in b["counts"].items():
            readable = c["match"] + c["drift"]
            per_dim.setdefault(d, []).append(
                round(c["drift"] / readable, 4) if readable >= MIN_READABLE else None)
    gradual = []
    for d, shares in per_dim.items():
        known = [x for x in shares if x is not None]
        if len(known) < TREND_BATCHES:
            continue
        tail = known[-TREND_BATCHES:]
        rising = all(b >= a for a, b in zip(tail, tail[1:])) and tail[-1] > tail[0]
        half = len(known) // 2
        early = sum(known[:half]) / half if half else 0.0
        late = sum(known[half:]) / (len(known) - half)
        if rising or late - early >= RISE:
            gradual.append({"dimension": d, "shares": known, "early": round(early, 4),
                            "late": round(late, 4), "rising": rising})
    return {"batches": len(ordered), "frames": sum(b["frames"] for _k, b in ordered),
            "per_dimension": per_dim, "gradual_drift": gradual,
            "measurable": len(ordered) >= TREND_BATCHES,
            "reason": ("" if len(ordered) >= TREND_BATCHES else
                       f"{len(ordered)} batch(es) of model-bearing frames in {WINDOW_DAYS} "
                       f"days; a trend needs {TREND_BATCHES}. UNMEASURED, not stable")}


def run(db, *, today: date | None = None) -> dict:
    """Compute the series, persist it, and open or resolve the drift incident."""
    from sqlalchemy import select

    from ..core.models import OperatingReading
    from ..ops import incident_lifecycle as lifecycle

    today = today or datetime.now(timezone.utc).date()
    out = series(db)
    drifting = {f"{SIGNATURE}{g['dimension']}": g for g in out["gradual_drift"]}
    with db.session() as s:
        row = s.scalar(select(OperatingReading).where(
            OperatingReading.kind == KIND, OperatingReading.period_key == today.isoformat()))
        if row is None:
            s.add(OperatingReading(kind=KIND, period_key=today.isoformat(), payload=out))
        else:
            row.payload = out
        life = lifecycle.reconcile(
            s, SIGNATURE, lambda inc: inc.signature in drifting,
            resolution="the dimension's drift share stopped rising across recent batches")
        opened = []
        for sig, g in drifting.items():
            _r, new = lifecycle.open_or_restate(
                s, signature=sig, severity="P2", halts_publication=True,
                summary=(f"gradual identity drift on {g['dimension']}: drift share "
                         f"{g['early']:.0%} -> {g['late']:.0%} across batches (#201). "
                         f"Model-bearing frames regenerate against the frozen pack before "
                         f"any is released"),
                detail=g)
            if new:
                opened.append(sig)
    return {**out, "incidents_opened": opened, "incidents_resolved": life["resolved"]}
