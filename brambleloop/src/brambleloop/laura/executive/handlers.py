"""Job handler for `laura.executive_tick` (GREEN: reads rows, writes Laura's priorities and
decisions, company memory/timeline, and missions through the COO's enqueue boundary; publishes,
spends and messages nothing). Imported by `autonomy.handlers`, which the runtime imports."""
from __future__ import annotations

from datetime import datetime, timezone

from ...runtime.worker import JobContext, handlers
from . import loop


def _declare_work_keys() -> None:
    # The useful-work judge reads `work_done` first; this declaration (requested for
    # runtime/pipeline.WORK_KEYS in the lane D handoff) keeps the type declared until then.
    try:
        from ...runtime import pipeline

        pipeline.WORK_KEYS.setdefault(loop.EXEC_JOB, ("work_done",))
    except Exception:  # noqa: BLE001
        pass


_declare_work_keys()


def _now(ctx: JobContext) -> datetime:
    raw = (ctx.job.inputs or {}).get("now")
    if raw:
        try:
            dt = datetime.fromisoformat(raw)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


@handlers.register(loop.EXEC_JOB)
def handle_executive_tick(ctx: JobContext) -> dict:
    r = loop.tick(ctx.db, ctx.queue, now=_now(ctx))
    return {"ran": True, "work_done": r["new_decisions"],
            "decisions_by_kind": r["decisions_by_kind"], "delegated": r["delegated"],
            "reviewed": r["review"]["reviewed"], "idle": r["idle"],
            "priorities": len(r["priorities"]), "identity_sha256": r["identity_sha256"],
            "cognition": r["cognition"]["engine"],
            "wake": (ctx.job.inputs or {}).get("wake") or (ctx.job.inputs or {}).get("cadence")}
