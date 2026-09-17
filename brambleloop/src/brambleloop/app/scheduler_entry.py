"""Scheduler entrypoint -- run on a cron (Railway cron service) or as a loop.

Enqueues due cadences. Idempotent per window, so overlapping cron firings cannot flood the
queue (Master Plan section 13).
"""
from __future__ import annotations

import logging
import os
import sys
import time

from ..core.db import Database
from ..runtime.worker import Scheduler

logging.basicConfig(level=os.environ.get("BRAMBLELOOP_LOG_LEVEL", "INFO"),
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("brambleloop.scheduler")


def main() -> int:
    db = Database()
    db.create_all()
    sched = Scheduler(db)
    once = os.environ.get("BRAMBLELOOP_SCHEDULER_ONCE", "1") == "1"
    interval = float(os.environ.get("BRAMBLELOOP_SCHEDULER_INTERVAL", "60"))
    while True:
        enqueued = sched.tick()
        if enqueued:
            log.info("enqueued cadences: %s", ", ".join(enqueued))
        if once:
            return 0
        time.sleep(interval)


if __name__ == "__main__":
    sys.exit(main())
