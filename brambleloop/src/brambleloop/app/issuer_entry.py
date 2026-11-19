"""WS4-7: the policy-issuer service -- the only process that can mint a standing grant.

Run as its own Railway service (`python -m brambleloop.app.issuer_entry`), never inside web or
the worker. Design §2.1 (Main S3, 6953884261):

* **No inbound interface.** No HTTP listener, no private-network port: a compromised worker can
  only ASK, by writing a `policy.grant_requested` row, and a request carries no authority (the
  issuer re-derives every fact from the database and reads only slug, version, release, job).
* **Its own keys only.** `BRAMBLELOOP_GRANT_ISSUER_KEY` is set on this service alone. It holds no
  Etsy credentials, no policy signing key, and runs no job handlers; `issuer_signing_refusal`
  refuses to sign if any of that is not so.
* **Pull loop under a lease.** Every `BRAMBLELOOP_ISSUER_INTERVAL` seconds (default 60) the
  holder of the `policy_issuer` lease writes a signed heartbeat (its own key report, the
  issuer third of the Mode T readiness check) and answers pending requests. A second issuer
  replica idles.
* **Small.** One SQL connection, no model, no image, no web framework: its resident memory is
  measured in `tests/test_ws4_7_issuer.py` and priced in the S3 cost note.
"""
from __future__ import annotations

import logging
import os
import socket
import sys
import time

log = logging.getLogger("brambleloop.issuer")
LEASE = "policy_issuer"


def tick(db, *, holder: str, now=None) -> dict:
    """One pass: the lease, the signed heartbeat, then each pending request answered."""
    from ..ops import slo, standing_grants as SG

    if not slo.acquire_lease(db, LEASE, holder, ttl_s=180, now=now):
        return {"leader": False, "answered": []}
    SG.ensure_tables(db)
    SG.issuer_heartbeat(db, now=now)
    answered = [SG.answer(db, req, now=now) for req in SG.pending_requests(db)]
    # WS4-8 Stage A: activation requests, answered by `standing_activation.issue` (which
    # refuses everything while STAGE_A_ENABLED is False).
    from ..ops import standing_activation_flow as stage_a

    answered += [stage_a.answer(db, req, now=now) for req in stage_a.pending_requests(db)]
    return {"leader": True, "answered": answered}


def main() -> int:
    logging.basicConfig(level=os.environ.get("BRAMBLELOOP_LOG_LEVEL", "INFO"),
                        format="%(asctime)s %(levelname)s %(message)s")
    from ..ops import log_secret_guard

    log_secret_guard.install()
    from ..ops import standing_grants as SG

    SG.mark_issuer_process()
    why = SG.issuer_signing_refusal()
    if why:
        # Refuse to run rather than run as something that cannot keep its promise.
        log.error("policy issuer refuses to start: %s", why)
        return 2
    from ..core.db import Database

    db = Database()
    holder = f"issuer-{socket.gethostname()}-{os.getpid()}"
    interval = float(os.environ.get("BRAMBLELOOP_ISSUER_INTERVAL", "60"))
    once = os.environ.get("BRAMBLELOOP_ISSUER_ONCE", "0") == "1"
    while True:
        try:
            out = tick(db, holder=holder)
            if out["answered"]:
                log.info("answered %d grant request(s)", len(out["answered"]))
        except Exception:  # noqa: BLE001 - one failed pass never stops the issuer
            log.exception("issuer pass failed; the next pass retries")
        if once:
            return 0
        time.sleep(interval)


if __name__ == "__main__":
    sys.exit(main())
