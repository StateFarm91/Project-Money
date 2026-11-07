"""A secret caught in the service's own logs becomes an incident and a rotation request.

P0-SECRET-LEAK-ESCALATE (W6). `ops.log_secret_guard.SecretLogGuard` redacts a credential
before a log line leaves the process and counts the catch by pattern and fingerprint -- but
nothing read `summary()`, so the count died with the process. The redaction protects the log
store; it does not un-leak the credential, which reached a code path that formatted it into a
message and may have reached others that do not log. The spec's leaked-credential playbook
(§28) is rotation, and rotation is the owner's act at the provider and in Railway.

So the health sweep (`ops.health`, every fifteen minutes, in the same process as the guard:
production runs one uvicorn process with the in-process runner, and the worker entrypoint
installs the guard too) calls `escalate`, which turns each caught secret into

* ONE durable incident, signature `secret_leak:<subject>`, P1, and
* ONE owner-queue action, requirement key `secret_leak_rotation:<subject>`, through
  `owner_queue.ensure` (deduplicated by key; the incident names the key in
  `detail.owner_action`, so the readiness closer keeps it open while the incident is open).

The subject is the environment variable whose value contains the caught secret when one does
(found by fingerprinting each variable's value in memory with the guard's own patterns),
otherwise `<pattern>:<fingerprint>`. **Never a value**: only the pattern name, the 12-hex
fingerprint the guard already computed, the logger name and counts are written anywhere. The
environment values are read, scanned and discarded inside `_identify`; none is stored,
returned or logged.

Repeat sweeps add nothing: the incident and the action are keyed on the subject, and an open
incident is restated only when the guard's count for one of its fingerprints has changed. The
incident is not auto-resolved -- nothing in software can prove a credential was replaced at
the provider -- it is closed by the owner (or a later producer) once rotation is confirmed.
"""
from __future__ import annotations

from . import log_secret_guard as guard

SIGNATURE = "secret_leak:"
KEY_PREFIX = "secret_leak_rotation:"

# When no environment variable holds the caught value (a secret from a provider response, a
# request header, a value not in this process's environment), the variable it most likely
# belongs to, by pattern class. Stated as "most likely" on the card, never as identified.
LIKELY_VARIABLE = {
    "anthropic_key": "ANTHROPIC_API_KEY",
    "openai_key": "OPENAI_API_KEY",
    "aws_access_key_id": "AWS_ACCESS_KEY_ID",
    "aws_secret_access_key": "AWS_SECRET_ACCESS_KEY",
    "etsy_oauth_token": "the stored Etsy OAuth token (re-authorise the shop)",
    "etsy_keystring": "ETSY_API_KEY",
    "github_token": "GITHUB_TOKEN",
    "stripe_live_key": "STRIPE_SECRET_KEY",
    "slack_token": "SLACK_TOKEN",
    "db_url_password": "DATABASE_URL",
    "bearer_token": "BRAMBLELOOP_OPS_TOKEN",
}


def _identify(fp: str, env: dict) -> str | None:
    """The variable whose value contains the secret with this fingerprint, or None."""
    for name in sorted(env):
        value = env.get(name)
        if not isinstance(value, str) or len(value) < 8:
            continue
        if guard.fingerprint(value) == fp:
            return name
        if any(f == fp for _line, _pat, f in guard.scan_text(value)):
            return name
    return None


def _subjects(summary: dict, env: dict) -> dict[str, dict]:
    """Group the guard's catches by what has to be rotated."""
    out: dict[str, dict] = {}
    for c in summary.get("caught") or []:
        pattern, fp = str(c.get("pattern")), str(c.get("fingerprint"))
        variable = _identify(fp, env)
        subject = f"var:{variable}" if variable else f"{pattern}:{fp}"
        s = out.setdefault(subject, {"variable": variable, "patterns": set(),
                                     "fingerprints": {}, "loggers": set()})
        s["patterns"].add(pattern)
        s["fingerprints"][fp] = s["fingerprints"].get(fp, 0) + int(c.get("count") or 0)
        s["loggers"].add(str(c.get("logger")))
    return out


def _card(subject: str, s: dict) -> dict:
    patterns = sorted(s["patterns"])
    if s["variable"]:
        what = s["variable"]
        named = f"{what} (identified: its value matches the caught fingerprint)"
    else:
        guess = LIKELY_VARIABLE.get(patterns[0], "the credential of this class")
        what = f"the {patterns[0]} credential, most likely {guess}"
        named = f"{what} (not identified: no environment variable holds the caught value)"
    fps = ", ".join(sorted(s["fingerprints"]))
    return {
        "action": (f"Rotate {what} in Railway: create a new credential at its provider, set "
                   f"it as the service variable in Railway and let it redeploy, confirm one "
                   f"real call succeeds with the new value, then revoke the old one at the "
                   f"provider. Tell Claude the date it was confirmed, never the value."),
        "reason": (f"The F-159 log guard caught {named} in this service's own log output "
                   f"(pattern {', '.join(patterns)}; fingerprint {fps}; logger "
                   f"{', '.join(sorted(s['loggers']))}). The line was redacted before it left "
                   f"the process, but the credential reached a code path that formats it, so "
                   f"it is treated as exposed until rotated (spec §28 leaked-credential "
                   f"playbook)."),
        "why_software_cannot": ("issuing and revoking a credential happens in the provider's "
                                "console and Railway's variables, signed in as the account "
                                "holder; this service never holds or sets its own secrets"),
        "max_cost_cad": 0.0,
        "minutes": 10,
        "consequence_of_delay": ("the exposed credential stays valid; anything that saw the "
                                 "code path that formatted it can act as this account"),
        "blocks": "nothing in the build; this is a security exposure, not a capability gate",
    }


def escalate(session, *, summary: dict | None = None, env: dict | None = None) -> dict:
    """One incident and one owner rotation action per caught secret. Idempotent.

    `summary` defaults to this process's `log_secret_guard.summary()`; `env` to
    `os.environ`. Returns names, fingerprints and ids only.
    """
    import os

    from . import incident_lifecycle, owner_queue

    summary = guard.summary() if summary is None else summary
    status = summary.get("status")
    if status != "CAUGHT":
        # Only an explicit CLEAN reads as clean; anything else (missing, malformed, a status
        # this module does not know) is UNKNOWN, never CLEAN (review W6 2026-11-07, LOW).
        return {"status": "CLEAN" if status == "CLEAN" else "UNKNOWN",
                "guard_status": status if isinstance(status, str) else repr(type(status)),
                "records_scanned": summary.get("records_scanned", 0),
                "opened": [], "restated": [], "owner_actions": []}
    env = dict(os.environ) if env is None else env
    opened, restated, actions, acknowledged = [], [], [], []
    from sqlalchemy import select

    from ..core.models import Incident, OwnerAction

    for subject, s in sorted(_subjects(summary, env).items()):
        signature = (SIGNATURE + subject)[:200]
        key = (KEY_PREFIX + subject)[:200]
        card = _card(subject, s)
        detail = {"variable": s["variable"], "patterns": sorted(s["patterns"]),
                  "fingerprints": dict(sorted(s["fingerprints"].items())),
                  "loggers": sorted(s["loggers"]), "owner_action": key,
                  "source": "ops.log_secret_guard", "value_stored": False}
        existing = session.scalar(select(Incident).where(
            Incident.signature == signature, Incident.resolved == False))  # noqa: E712
        if existing is not None and (existing.detail or {}).get("fingerprints") == \
                detail["fingerprints"]:
            # Nothing new caught since the last sweep: no restatement, no churn, and an
            # owner action the owner has already closed is not reopened by the same catch.
            open_row = session.scalar(select(OwnerAction).where(
                OwnerAction.requirement_key == key,
                OwnerAction.done == False))  # noqa: E712
            if open_row is not None:
                actions.append({"key": key, "id": open_row.id})
            continue
        if existing is None and _resolved_for_same_catch(session, signature,
                                                         detail["fingerprints"]):
            # The owner resolved this exact catch (same fingerprints). The process guard keeps
            # it in its summary until restart, so re-seeing it is not a new exposure: do not
            # reopen a P1 or a rotation card for it (review W6 2026-11-07, MED). A different
            # fingerprint for the same variable is a new catch and opens as usual.
            acknowledged.append(signature)
            continue
        else:
            _row, new = incident_lifecycle.open_or_restate(
                session, signature=signature, severity="P1",
                summary=(f"Secret caught in the service log: rotate "
                         f"{s['variable'] or ', '.join(sorted(s['patterns']))} "
                         f"(fingerprint {', '.join(sorted(s['fingerprints']))})"),
                detail=detail)
            (opened if new else restated).append(signature)
        row = owner_queue.ensure(session, key, **card)
        actions.append({"key": key, "id": row.id})
    session.flush()
    return {"status": "CAUGHT", "records_scanned": summary.get("records_scanned", 0),
            "opened": opened, "restated": restated, "owner_actions": actions,
            "acknowledged": acknowledged}


def _resolved_for_same_catch(session, signature: str, fingerprints: dict) -> bool:
    """True when every caught fingerprint was already covered by a resolved secret-leak
    incident under any signature. A rotated value drops off its variable and would otherwise
    re-surface keyed by pattern+fingerprint."""
    from sqlalchemy import select

    from ..core.models import Incident

    if not fingerprints:
        return False
    covered: set[str] = set()
    for inc in session.scalars(select(Incident).where(
            Incident.signature.like(SIGNATURE + "%"), Incident.resolved == True)):  # noqa: E712
        covered |= set(((inc.detail or {}).get("fingerprints") or {}).keys())
    return set(fingerprints) <= covered


ESCALATION_FAILED = SIGNATURE + "escalation_failed"


def escalation_failed(session, error: str) -> dict:
    """Fail-closed fallback when `escalate` raised while the guard holds a caught secret:
    one P1 incident naming only the error type (no variable, fingerprint or value), so a
    caught secret never reduces to an UNKNOWN reading with nothing to act on."""
    from . import incident_lifecycle

    _row, new = incident_lifecycle.open_or_restate(
        session, signature=ESCALATION_FAILED, severity="P1",
        summary=("A secret was caught in the service log but its escalation failed "
                 f"({error}); rotate the credentials named in the log guard and check "
                 "ops.health"),
        detail={"source": "ops.secret_leak", "error": error, "value_stored": False})
    session.flush()
    return {"status": "CAUGHT", "escalation": "FAILED", "error": error,
            "opened": [ESCALATION_FAILED] if new else [],
            "restated": [] if new else [ESCALATION_FAILED]}
