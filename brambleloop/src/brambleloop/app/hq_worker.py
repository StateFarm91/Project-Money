"""F-496: an optional HQ acceleration worker against the same queue -- and the guard that the
cloud never depends on it.

An HQ machine (more CPU, a GPU, a local renderer) can drain *some* job types faster. It runs
this entry point with `BRAMBLELOOP_HQ_JOB_TYPES=a,b,...` and the same database URL as the
cloud; it claims only those types, under the same leases, so an HQ that goes offline mid-job
returns the job to PENDING when the lease expires and a cloud worker takes it.

The independence guard (`plan`) refuses to start an HQ worker on:
* a job type no GREEN agent may run (HQ never publishes, spends against a YELLOW/RED
  authority, or takes an owner action -- those stay in the cloud, under the cloud's checks);
* a job type with no registered handler (nothing to accelerate);
* a cloud fleet restricted so that some HQ type is claimable *only* by HQ
  (`BRAMBLELOOP_CLOUD_JOB_TYPES` set and missing it) -- the cloud must be able to run
  everything HQ runs, or HQ going offline stops the company.

No credential is created or stored here; the operator supplies the database URL the same way
the cloud worker gets it.
"""
from __future__ import annotations

import os
import socket
import sys

ENV_TYPES = "BRAMBLELOOP_HQ_JOB_TYPES"
ENV_CLOUD_TYPES = "BRAMBLELOOP_CLOUD_JOB_TYPES"


class HQRefused(ValueError):
    pass


def _green_only_types() -> set[str]:
    from ..agents.registry import DEFAULT_AGENTS
    from ..core.models import Authority

    green, other = set(), set()
    for a in DEFAULT_AGENTS:
        (green if a.get("authority") == Authority.GREEN else other).update(
            a.get("allowed_job_types") or [])
    return green - other


def plan(job_types: list[str], *, cloud_types: list[str] | None = None,
         registered=None) -> dict:
    from ..runtime import pipeline  # noqa: F401 - registers handlers
    from ..runtime.worker import handlers

    types = sorted({t.strip() for t in job_types if t.strip()})
    if not types:
        raise HQRefused(f"{ENV_TYPES} names no job type")
    green = _green_only_types()
    not_green = [t for t in types if t not in green]
    if not_green:
        raise HQRefused(f"HQ runs GREEN-only job types; refused: {not_green}")
    has = registered or (lambda t: handlers.get(t) is not None)
    no_handler = [t for t in types if not has(t)]
    if no_handler:
        raise HQRefused(f"no registered handler for {no_handler}")
    if cloud_types is not None:
        orphan = [t for t in types if t not in set(cloud_types)]
        if orphan:
            raise HQRefused(f"the cloud fleet cannot claim {orphan}: HQ going offline would "
                            f"stop them (independence guard)")
    return {"job_types": types, "independent": True,
            "lease_fallback": "an expired HQ lease returns the job to PENDING for the cloud"}


def main() -> int:
    from ..core.db import Database
    from ..core.phase import effective_phase
    from ..runtime.worker import Worker

    cloud = os.environ.get(ENV_CLOUD_TYPES)
    try:
        p = plan((os.environ.get(ENV_TYPES) or "").split(","),
                 cloud_types=[t for t in cloud.split(",") if t] if cloud else None)
    except HQRefused as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    db = Database()
    worker = Worker(db, f"hq-{socket.gethostname()}", phase=effective_phase(db),
                    job_types=p["job_types"], live_phase=True)
    worker.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
