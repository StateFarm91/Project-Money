"""W4-ETSYCOMM: the owner's two Etsy-connection buttons, usable from a phone.

`/api/etsy/oauth/start` and `POST /api/etsy/probe` answer only to the operator Bearer token,
which is a secret the owner does not carry on a phone. So the two things only the owner can
do about the Etsy connection -- re-test the app key after fixing it at Etsy, and grant the
shop's scopes (including `transactions_r`) -- had no owner-session route at all.

These run behind the existing Command Center gate (owner session, CSRF, nonce, timestamp:
`security.operator_gate` -> `auth.gate`); "Connect" additionally needs a fresh step-up,
because it starts a grant of authority over the shop. Neither changes the scopes, the
redirect URI, the credentials or the Etsy app: `connect` calls the same
`etsy_authorise.begin` the operator route calls, with `SCOPES_WANTED` unchanged.

Nothing returned here is a credential. The authorize URL carries the public keystring and a
PKCE *challenge*; the verifier and the state stay sealed in the database, and only an
eight-character fingerprint of the state is returned or audited.
"""
from __future__ import annotations

from datetime import datetime, timezone

RECHECK_ACTION = "cc.etsy.recheck"
CONNECT_ACTION = "etsy.oauth_started"


class ConnectRefused(RuntimeError):
    def __init__(self, message: str, *, code: str, detail: dict | None = None):
        super().__init__(message)
        self.code = code
        self.detail = detail or {}


def _probe_view(probe: dict | None) -> dict:
    if not probe:
        return {"state": "NEVER_PROBED", "ok": None}
    return {"state": "OK" if probe.get("ok") else "FAILING", "ok": bool(probe.get("ok")),
            "at": probe.get("at"), "status": probe.get("status"),
            "reason": str(probe.get("reason") or "")[:400],
            "etsy_error": str(probe.get("etsy_error") or "")[:200]}


def status(db) -> dict:
    """What the owner needs to decide which button to press. No secret, no fingerprint of one."""
    from ...core import oauth_store
    from ...integrations import etsy_authorise
    from ...intel import etsy_public

    probe = etsy_public.last_probe(db)
    config = etsy_authorise.configuration()
    health = oauth_store.credential_health(db)
    granted = list(health.get("scopes") or [])
    wanted = list(config.get("scopes") or [])
    return {
        "api_key_probe": _probe_view(probe),
        "grant": {"stored": bool(health.get("stored")), "scopes": granted,
                  "missing_scopes": [s for s in wanted if s not in granted]},
        "authorise": {"ready": bool(config.get("ready")),
                      "problems": list(config.get("problems") or []),
                      "callback_path": config.get("callback_path"),
                      "scopes": wanted},
        "can_connect": bool(config.get("ready")) and not (probe and not probe.get("ok")),
    }


def recheck(db, *, actor: str) -> dict:
    """Queue one `etsy.probe` now (read-only ping, CA$0). At most one per minute."""
    from ...agents.registry import Registry
    from ...queue.durable import DuplicateJob, JobQueue

    key = f"etsy.probe:cc:{datetime.now(timezone.utc):%Y%m%dT%H%M}"
    try:
        job = JobQueue(db).enqueue("market_radar", "etsy.probe", {}, idempotency_key=key)
    except DuplicateJob:
        job = None
    Registry(db).audit("orchestrator", RECHECK_ACTION,
                       detail={"by": actor[:64], "enqueued": job is not None,
                               "job_id": getattr(job, "id", None)})
    return {"enqueued": job is not None, "job_id": getattr(job, "id", None),
            "note": ("the Etsy key is re-tested by the worker within a minute or two; this "
                     "page shows the result" if job is not None else
                     "a re-check was already queued this minute")}


def connect(db, *, actor: str) -> dict:
    """Start the shop authorization and return the URL the owner opens. Refuses honestly."""
    from ...agents.registry import Registry
    from ...integrations import etsy_authorise
    from ...intel import etsy_public

    probe = etsy_public.last_probe(db)
    if probe and not probe.get("ok"):
        said = probe.get("etsy_error") or probe.get("reason") or "no reason recorded"
        raise ConnectRefused(
            "Etsy is refusing this app's API key right now (last check "
            f"{str(probe.get('at') or '')[:16]}Z: {str(said)[:200]}). Authorising the shop "
            "would fail on the same key. Fix the key first: open "
            "etsy.com/developers/your-apps, confirm the app is active and its shared secret "
            "matches the one in Railway, then press 'Re-check Etsy connection'.",
            code="ETSY_KEY_REFUSED", detail={"api_key_probe": _probe_view(probe)})
    config = etsy_authorise.configuration()
    if not config["ready"]:
        raise ConnectRefused(
            "This deployment cannot start an Etsy authorization: "
            + "; ".join(config["problems"]),
            code="ETSY_NOT_CONFIGURED", detail={"problems": list(config["problems"])})
    started = etsy_authorise.begin(db, started_by=actor[:64])
    # Same audit row the operator route writes, so one reader sees every start.
    Registry(db).audit("orchestrator", CONNECT_ACTION,
                       detail={"state_fingerprint": f"***{started.state_fingerprint}",
                               "handshake": started.handshake,
                               "scopes": list(started.scopes),
                               "expires_at": started.expires_at,
                               "source": "command_center", "by": actor[:64]})
    out = started.to_dict()
    return {"authorize_url": out["authorize_url"], "state_expires_at": out["state_expires_at"],
            "scopes": out["scopes"], "redirect_uri": out["redirect_uri"],
            "state_fingerprint": out["state_fingerprint"], "next": out["next"],
            "note": out["note"]}
