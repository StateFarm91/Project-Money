"""Scheduler entrypoint -- run on a cron (Railway cron service) or as a loop.

Enqueues due cadences. Idempotent per window, so overlapping cron firings cannot flood the
queue (Master Plan section 13).

This is the cron path: it needs no HTTP credential because it never goes through the web
edge. The HTTP equivalent, `POST /api/scheduler/tick`, is operator-authenticated like every
other mutating route (audit A3-02); a cron that uses it must send the operator bearer token.
"""
from __future__ import annotations

import logging
import os
import socket
import sys
import time

from ..core.db import Database
from ..runtime.worker import Scheduler

logging.basicConfig(level=os.environ.get("BRAMBLELOOP_LOG_LEVEL", "INFO"),
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("brambleloop.scheduler")


def main() -> int:
    # A3-05: same runtime boot guard as the web service (forces SHADOW on an unproven build).
    from ..ops import release_record

    release_record.apply_at_import()
    db = Database()
    db.create_all()
    sched = Scheduler(db)
    once = os.environ.get("BRAMBLELOOP_SCHEDULER_ONCE", "1") == "1"
    interval = float(os.environ.get("BRAMBLELOOP_SCHEDULER_INTERVAL", "60"))
    from ..ops import slo as _slo

    holder = f"scheduler-{socket.gethostname()}-{os.getpid()}"
    while True:
        # v1.1 lane I W-1: in the split (looping) topology a lease makes a second scheduler
        # idle instead of double-ticking; the once/cron path keeps its idempotent windows.
        if not once:
            try:
                leader = _slo.acquire_lease(db, "scheduler", holder, ttl_s=180)
            except Exception:  # noqa: BLE001 - a lease read failure must not stop scheduling
                log.exception("scheduler lease unavailable; ticking (windows are idempotent)")
                leader = True
            if not leader:
                time.sleep(interval)
                continue
        enqueued = sched.tick()
        try:
            _slo.record_heartbeat(db, "scheduler", instance=holder,
                                  detail={"enqueued": len(enqueued)})
        except Exception:  # noqa: BLE001 - liveness evidence must never stop scheduling
            log.exception("scheduler heartbeat row not written")
        if enqueued:
            log.info("enqueued cadences: %s", ", ".join(enqueued))
        if once:
            return 0
        time.sleep(interval)


if __name__ == "__main__":
    sys.exit(main())
