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
    # A3-05: same runtime boot guard as the web service. On the hosting platform an unproven
    # build runs as SHADOW (the phase env is forced before the effective phase is read below).
    from ..ops import release_record

    release_record.apply_at_import()
    db = Database()
    db.create_all()
    try:
        release_record.record_incident(db)
    except Exception:  # noqa: BLE001 - the phase is already forced
        pass
    Registry(db).seed_defaults()
    from ..intel.benchmarks import seed as seed_benchmarks

    seed_benchmarks(db)

    # F-299: the environment AND the recorded owner transition; disagreement -> the more
    # restrictive phase plus an incident. Shadow when nothing is recorded.
    from ..core.phase import effective_phase

    phase = effective_phase(db)
    import socket

    name = os.environ.get("BRAMBLELOOP_WORKER_NAME") or \
        f"worker-{socket.gethostname()[:40]}-{os.getpid()}"
    log.info("starting worker %s in phase %s", name, phase.value)

    # rc1-AUTH A1: the boot-time phase is only the first reading; the worker re-resolves it
    # for every job (`live_phase`), and protected effects re-resolve it again at their
    # effect boundaries (`runtime.worker.protected_phase`).
    worker = Worker(db, name, phase=phase, live_phase=True)
    max_seconds = os.environ.get("BRAMBLELOOP_MAX_SECONDS")
    stats = worker.run(max_seconds=float(max_seconds) if max_seconds else None)
    log.info("worker %s exiting: %s", name, stats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
