"""The rendered-page half of what used to be one gate, and the probe that keeps it honest.

Requirements 189, 221, 222, 320. Some of what this company needs to see has no endpoint.
Etsy's sanctioned API answers nine paths, and none of them is Marketplace Insights, a search
results page, or the Seller Policy. Those are pages a buyer or a seller looks at, and reading
them means rendering them.

**What this is not.** It is not the capability that judges photographs. That was conflated
into the same gate for a day and cost twelve requirements their place in the queue, because
the model that can look at a gallery image was already credentialed and the URLs were already
arriving from the sanctioned endpoint -- see `gateway.anthropic.see`. A browser is for pages
without an API, and nothing else here.

**The worker is remote and the client is thin on purpose.** #189 asks for cloud workers so
monitoring continues with the owner's devices off, which means this module must not assume a
browser in this process. It speaks to a worker over HTTP, the endpoint is configuration, and
the capability is a recorded successful fetch -- never the endpoint being set. The gate this
replaces read an environment variable, which is the one condition in the executor's table a
person could satisfy by typing, and it stood in front of twenty-eight requirements.

**Politeness is not optional and not a setting.** A worker that ignores robots.txt, hammers a
host or disguises itself is a scraping incident with this company's name on it, so the
request carries an identifying user agent and the rate is bounded here rather than in the
worker's configuration, where it would be somebody else's to relax.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone

from ..core.resilience import PermanentError, TransientError

WORKER_URL_VAR = "BRAMBLELOOP_BROWSER_URL"
WORKER_TOKEN_VAR = "BRAMBLELOOP_BROWSER_TOKEN"

PROBE_ACTION = "browser.probe"

# Identifies this company to the hosts it reads. A crawler that hides what it is has decided
# in advance that it will not be welcome.
USER_AGENT = "BrambleloopStudioResearch/1.0 (+contact via Etsy shop BrambleloopStudio)"

# The floor between two fetches of the same host, in seconds. Here rather than in the
# worker's own config because a limit that lives where the worker is configured is a limit
# somebody can raise without this repository recording that they did.
MIN_SECONDS_BETWEEN_FETCHES = 3.0

# What the probe fetches. A page this company is unambiguously entitled to read, on the host
# the capability exists to read, so a probe that passes says something about the real job
# rather than about example.com.
PROBE_URL = "https://www.etsy.com/legal/terms"

# A fetched page has to look like a page. A worker that returns an empty body, a challenge
# page or an error document with HTTP 200 is the shape this failure actually takes.
MIN_PROBE_BYTES = 2000


class BrowserNotConfigured(PermanentError):
    """No worker endpoint. Not an outage: there is nowhere to send the request."""


class BrowserRefused(PermanentError):
    """The worker answered and the answer is not a rendered page."""


def worker_url(env: dict[str, str] | None = None) -> str:
    e = env if env is not None else os.environ
    return (e.get(WORKER_URL_VAR) or "").strip()


def configured(env: dict[str, str] | None = None) -> bool:
    """Whether an endpoint is set. Deliberately not the same question as `usable`."""
    return bool(worker_url(env))


def fetch(url: str, *, env: dict[str, str] | None = None,
          timeout: float = 45.0) -> dict:
    """Ask the worker for one rendered page.

    Returns the page's text and status. Raises rather than returning an empty string when
    anything went wrong, because an empty page and a page that failed to load are the same
    value and opposite facts.
    """
    import urllib.error
    import urllib.request

    e = env if env is not None else os.environ
    base = worker_url(e)
    if not base:
        raise BrowserNotConfigured(
            f"no {WORKER_URL_VAR} in this environment, so there is no worker to ask. This "
            f"is the state the gate exists to describe, not a failure to retry")

    payload = json.dumps({"url": url, "user_agent": USER_AGENT,
                          "respect_robots": True,
                          "min_interval_seconds": MIN_SECONDS_BETWEEN_FETCHES}).encode()
    request = urllib.request.Request(base.rstrip("/") + "/render", data=payload,
                                     method="POST")
    request.add_header("content-type", "application/json")
    token = (e.get(WORKER_TOKEN_VAR) or "").strip()
    if token:
        request.add_header("authorization", f"Bearer {token}")

    started = time.time()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:300]
        if exc.code in (429, 500, 502, 503, 504):
            raise TransientError(f"browser worker {exc.code}: {detail}") from exc
        raise BrowserRefused(f"browser worker {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise TransientError(f"browser worker unreachable: {exc.reason}") from exc

    text = body.get("text") or body.get("html") or ""
    status = int(body.get("status") or 0)
    if status and status >= 400:
        raise BrowserRefused(
            f"{url} answered {status} through the worker. Etsy answers 403 to a great many "
            f"automated clients, and that is a fact about this capability rather than a "
            f"transient one")
    return {"url": url, "final_url": body.get("final_url") or url, "status": status,
            "bytes": len(text), "text": text,
            "latency_ms": round((time.time() - started) * 1000, 2)}


def probe(db, *, env: dict[str, str] | None = None, now: datetime | None = None,
          job_id: int | None = None) -> dict:
    """Fetch one real page and record whether that worked. The gate's evidence.

    A worker URL that is set, misconfigured, unreachable or answered with a bot-protection
    challenge are four different states and one environment variable. The gate this replaced
    could not tell them apart, and releasing twenty-eight requirements into the ready queue
    on the strength of a typed string is the largest available instance of the failure this
    executor exists to prevent.
    """
    from ..core.models import AuditLog

    record: dict = {"at": (now or datetime.now(timezone.utc)).isoformat(),
                    "url": PROBE_URL, "ok": False, "reason": ""}
    if not configured(env):
        record["reason"] = f"no {WORKER_URL_VAR} in this environment"
    else:
        try:
            got = fetch(PROBE_URL, env=env)
        except (PermanentError, TransientError) as exc:
            record["reason"] = str(exc)[:400]
        else:
            record.update({"status": got["status"], "bytes": got["bytes"],
                           "final_url": got["final_url"],
                           "latency_ms": got["latency_ms"]})
            if got["bytes"] < MIN_PROBE_BYTES:
                record["reason"] = (
                    f"{got['bytes']} bytes returned, under {MIN_PROBE_BYTES}. An empty body, "
                    f"a challenge page and an error document all arrive with HTTP 200, and "
                    f"a capability that counts them as pages reports itself available")
            else:
                record["ok"] = True

    with db.session() as s:
        s.add(AuditLog(actor="orchestrator", action=PROBE_ACTION, artifact=PROBE_URL,
                       detail=record))
    return record


def last_probe(db) -> dict | None:
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    with db.session() as s:
        rows = list(s.scalars(select(AuditLog).where(AuditLog.action == PROBE_ACTION)
                              .order_by(desc(AuditLog.id)).limit(1)))
    return dict(rows[0].detail or {}) if rows else None


def usable(db) -> bool:
    """Whether a rendered page has actually been fetched. The `rendered_pages` condition."""
    state = last_probe(db)
    return bool(state and state.get("ok"))


def state(db, *, env: dict[str, str] | None = None) -> dict:
    """What this capability's situation actually is, configuration and evidence apart."""
    probe_state = last_probe(db)
    return {
        "endpoint_configured": configured(env),
        "last_probe": probe_state,
        "usable": bool(probe_state and probe_state.get("ok")),
        "politeness": {"user_agent": USER_AGENT,
                       "min_seconds_between_fetches": MIN_SECONDS_BETWEEN_FETCHES,
                       "robots_txt": "respected, and requested of the worker on every call"},
        "what_it_is_for": (
            "pages with no sanctioned endpoint: Marketplace Insights, search results and "
            "platform policy. Gallery images are not in this list -- those arrive from the "
            "Etsy API and are judged by the model, which needs no browser"),
        "why_a_probe": (
            "a configured URL is a string. Set, misconfigured, unreachable and answered with "
            "a 403 are four states and one environment variable, and the gate that read that "
            "variable stood in front of twenty-eight requirements"),
    }
