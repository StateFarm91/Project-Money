"""Worker process entrypoint.

Run as its own Railway service (or `python -m brambleloop.app.worker_entry` locally). Exits
cleanly on SIGTERM so a platform restart drains rather than strands work -- leases mean even
an unclean kill is recoverable, but a clean exit is faster.
"""
from __future__ import annotations

import logging
import os
import sys

from ..agents.registry import Registry
from ..core.db import Database
from ..core.models import Phase
from ..runtime import pipeline  # noqa: F401  -- registers handlers
from ..runtime.worker import Worker

logging.basicConfig(
    level=os.environ.get("BRAMBLELOOP_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("brambleloop.worker")


def main() -> int:
    db = Database()
    db.create_all()
    Registry(db).seed_defaults()
    from ..intel.benchmarks import seed as seed_benchmarks

    seed_benchmarks(db)

    phase = Phase(os.environ.get("BRAMBLELOOP_PHASE", "shadow"))
    name = os.environ.get("BRAMBLELOOP_WORKER_NAME") or f"worker-{os.getpid()}"
    log.info("starting worker %s in phase %s", name, phase.value)

    worker = Worker(db, name, phase=phase)
    max_seconds = os.environ.get("BRAMBLELOOP_MAX_SECONDS")
    stats = worker.run(max_seconds=float(max_seconds) if max_seconds else None)
    log.info("worker %s exiting: %s", name, stats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
