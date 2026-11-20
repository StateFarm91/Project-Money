"""Provider-health honesty: a probe that ran is not a provider that works (F-171; F-871).

Production, 2026-10-26 00:00Z: the model and vision probes ran on time and the provider
answered "credit balance is too low" (`ok: false`). The smoke matrix said PASS, because its
probe check asks only whether the probe *ran*. That is the machinery question; the business
question -- can a model actually be called -- was answered "no" and reported nowhere.

This module answers the second question for the billable model providers (`model.probe`,
`vision.probe`):

* `classify(reason)` -> a reason class: `credit`, `auth`, `rate_limit`, `overloaded`,
  `network`, `budget` (our own ceiling refused before the call), `no_key`, `other`.
* `check(row)` -> a smoke check: PASS only when the latest probe answered ok; FAIL for
  credit, auth, no_key and other; DEGRADED for the transient or self-imposed classes
  (rate_limit, overloaded, network, budget). Never PASS on a failed answer.
* `reconcile(db, session)` (the health sweep) opens one incident per provider and reason
  class, owner-actionable for credit/auth/no_key, and resolves it when a probe answers ok.

**No error body leaves this module.** Provider prose can carry request ids, account ids and,
in a misconfigured proxy, a key; only the class, the HTTP status code and a redacted excerpt
(`redact`) are ever put in a check, an incident or an API response.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

MODEL_PROBES: dict[str, str] = {"model.probe": "anthropic", "vision.probe": "anthropic"}
SIGNATURE = "provider-health:"
OWNER_CLASSES = ("credit", "auth", "no_key")
DEGRADED_CLASSES = ("rate_limit", "overloaded", "network", "budget")

_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("credit", ("credit balance is too low", "insufficient credit", "insufficient_quota",
                "billing_hard_limit_reached", "exceeded your current quota",
                "payment required", "http 402", " 402")),
    ("budget", ("budget:",)),
    ("no_key", ("no api key", "api_key in this environment", "not configured",
                "missing api key")),
    ("auth", ("invalid x-api-key", "authentication", "unauthorized", "permission",
              "forbidden", "http 401", "http 403", " 401", " 403", "invalid api key")),
    ("rate_limit", ("rate limit", "rate_limit", "too many requests", " 429", "http 429")),
    ("overloaded", ("overloaded", " 529", "http 529", " 503", "http 503")),
    ("network", ("timed out", "timeout", "connection", "name resolution", "unreachable")),
)

_SECRETS = (
    re.compile(r"sk-[A-Za-z0-9_\-]{6,}"),
    re.compile(r"(?i)bearer\s+\S+"),
    re.compile(r"(?i)(x-api-key|api[_-]?key|authorization)\s*[:=]\s*\S+"),
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"),
    re.compile(r"\b(req|org|acct|msg)_[A-Za-z0-9]+"),
    re.compile(r"[A-Za-z0-9_\-]{24,}"),
)


def classify(reason: str | None) -> str:
    low = f" {(reason or '').lower()} "
    for cls, needles in _RULES:
        if any(n in low for n in needles):
            return cls
    return "other"


def redact(reason: str | None, limit: int = 120) -> str | None:
    """A short excerpt with anything key-, id- or address-shaped removed; None when empty."""
    text = str(reason or "").strip()
    if not text:
        return None
    for rx in _SECRETS:
        text = rx.sub("[redacted]", text)
    return text[:limit]


def _status_code(reason: str | None) -> int | None:
    m = re.search(r"\b(4\d\d|5\d\d)\b", str(reason or ""))
    return int(m.group(1)) if m else None


def check(action: str, row) -> dict:
    """The provider-health smoke check for one probe's latest audit row (or None)."""
    name = f"provider_health:{action}"
    provider = MODEL_PROBES.get(action, "provider")
    if row is None:
        return {"check": name, "verdict": "UNKNOWN", "requirement": "F-171",
                "why": f"no {action} has been recorded", "evidence": {"provider": provider}}
    detail = row.detail if isinstance(row.detail, dict) else {}
    ok = detail.get("ok")
    reason = detail.get("reason") or detail.get("error")
    ev = {"provider": provider, "at": row.at.isoformat() if row.at else None,
          "provider_answered_ok": ok}
    if ok is True:
        return {"check": name, "verdict": "PASS", "requirement": "F-171",
                "why": f"{provider} answered the latest {action}", "evidence": ev}
    cls = classify(reason)
    ev.update(reason_class=cls, status_code=_status_code(reason),
              owner_action_required=cls in OWNER_CLASSES)
    verdict = "DEGRADED" if cls in DEGRADED_CLASSES else "FAIL"
    return {"check": name, "verdict": verdict, "requirement": "F-171",
            "why": (f"{provider} did not serve the latest {action}: {cls}"
                    + (" (owner action: the account needs attention)"
                       if cls in OWNER_CLASSES else "")),
            "evidence": ev}


def latest_rows(session) -> dict:
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    return {a: session.scalar(select(AuditLog).where(AuditLog.action == a)
                              .order_by(desc(AuditLog.id)).limit(1)) for a in MODEL_PROBES}


def reconcile(db, session, *, now: datetime | None = None) -> dict:
    """Open one incident per (provider, reason class) a probe failed with; resolve on ok."""
    from . import incident_lifecycle as lifecycle

    now = now or datetime.now(timezone.utc)
    failing: dict[str, dict] = {}
    for action, row in latest_rows(session).items():
        c = check(action, row)
        if c["verdict"] in ("FAIL", "DEGRADED"):
            ev = c["evidence"]
            sig = f"{SIGNATURE}{ev['provider']}:{ev['reason_class']}"
            failing.setdefault(sig, {"probes": [], **ev})["probes"].append(action)
    opened = []
    for sig, ev in failing.items():
        owner = ev["reason_class"] in OWNER_CLASSES
        _row, new = lifecycle.open_or_restate(
            session, signature=sig[:200], severity="P1" if owner else "P2",
            summary=(f"{ev['provider']} probes {ev['probes']} answered but failed: "
                     f"{ev['reason_class']}"
                     + ("; owner action required" if owner else "")),
            detail={"provider": ev["provider"], "reason_class": ev["reason_class"],
                    "status_code": ev.get("status_code"), "probes": ev["probes"],
                    "owner_action_required": owner}, now=now)
        if new:
            opened.append(sig)
    life = lifecycle.reconcile(
        session, SIGNATURE, lambda inc: inc.signature in failing,
        resolution="the provider answered the latest model and vision probes", now=now)
    return {"failing": sorted(failing), "opened": opened, "resolved": life["resolved"]}
