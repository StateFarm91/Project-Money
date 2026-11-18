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
# F-159: no secret reaches the platform's log store from this process.
from ..ops import log_secret_guard as _log_secret_guard  # noqa: E402

_log_secret_guard.install()


def main() -> int:
    # M-2R: this process runs jobs, so it may never sign a storefront grant; the signing key
    # is scrubbed from its environment before any handler can read it.
    from ..ops import storefront_authority as _sfa

    if _sfa.mark_job_process():
        log.warning("removed the storefront signing key from the worker environment: "
                    "a job process never signs storefront grants")
    # WS4-0a: nor an owner publication or activation grant.
    from ..core import owner_grant_keys as _ogk

    if _ogk.mark_job_process():
        log.warning("removed the owner-grant signing key from the worker environment: "
                    "a job process never signs owner grants")
    # WS4-3: nor a standing publication policy row.
    from ..ops import standing_policy as _sp

    if _sp.mark_job_process():
        log.warning("removed the standing-policy signing key from the worker environment: "
                    "a job process never signs a standing policy")
    # WS4-7: nor a standing execution grant (only the policy-issuer service holds that key).
    # HIGH-2: `mark_job_process` records that the key WAS here before it scrubs it, and the
    # boot report below states that (Mode S + a P1): the scrub cannot remove the key from the
    # exec environment or the service settings, so presence is the fact that matters.
    from ..ops import standing_grants as _sg

    if _sg.mark_job_process():
        log.warning("removed the grant-issuer signing key from the worker environment: "
                    "only the policy-issuer service mints a standing grant")
    # A3-05: same runtime boot guard as the web service. On the hosting platform an unproven
    # build runs as SHADOW (the phase env is forced before the effective phase is read below).
    from ..ops import release_record

    release_record.apply_at_import()
    db = Database()
    # Round-2 L4: on its own database role (Mode T runbook) the worker never creates a table
    # it should not own; a missing one means web (the migration owner) has not deployed this
    # release yet, and the worker refuses to start until it has.
    schema = db.boot_schema("worker")
    if schema["refusal"]:
        log.error("worker refused to start: %s", schema["refusal"])
        return 3
    try:
        release_record.record_incident(db)
    except Exception:  # noqa: BLE001 - the phase is already forced
        pass
    Registry(db).seed_defaults()
    try:
        _sg.process_report(db, _sg.WORKER_COMPONENT)    # WS4-7 Mode T evidence (keys held)
    except Exception:  # noqa: BLE001 - a missing report keeps the deployment in Mode S
        log.exception("worker key report not written; the deployment stays Mode S")
    from ..intel.benchmarks import seed as seed_benchmarks

    seed_benchmarks(db)

    # F-299: the environment AND the recorded owner transition; disagreement -> the more
    # restrictive phase plus an incident. Shadow when nothing is recorded.
    from ..core.phase import effective_phase

    phase = effective_phase(db)
    name = os.environ.get("BRAMBLELOOP_WORKER_NAME") or f"worker-{os.getpid()}"
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
