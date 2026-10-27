"""F-431's missing half: the research fetch step and the promotion of findings (W4-FMBATCH1).

F-431 Durable Knowledge Promotion: "Validated research findings become structured durable
knowledge, regression tests, capability metadata, architecture notes or decision records so
later agents reuse them." W4-RESEARCH built the task record; CLOSE5 found the run (fetch +
promotion) missing. This module is that run, called by the `learn.scan` cadence.

**The fetch step, bounded by construction (coordinator directive 2026-10-26):**
* only an explicit allowlist of public hosts (`ALLOWED_HOSTS`, each with the basis for reading
  it); https only; no credentials -- a URL with userinfo or a key/token parameter is refused,
  and no Authorization or cookie header is ever sent;
* robots.txt is read for the host first and obeyed for this user agent; unreadable robots is
  a refusal, never permission;
* an identifying user agent (the same one culture.feeds uses), a per-host floor between
  fetches, a byte cap, a timeout;
* free GETs only: no paid provider host can be on the list (tests/test_cert_spend_hosts
  scans for them), so the task's spend stays at CA$0 and its spend bound is untouched.
A fetched page is recorded on its task as a `fetched` source (url, date, bytes, sha256 and a
bounded excerpt) -- which is what lets a reader later record a `fact` resting on it.

**Promotion:** an answered task holding at least one fact becomes a lesson on the improvement
bus (`improve.bus.publish`, idempotent on `research_tasks:<id>`), routed by its domain's
subject. When the task's finding expires (F-433), the lesson is withdrawn with that reason,
so stale knowledge stops being matched. A domain with no subject is reported, not forced.
"""
from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

USER_AGENT = "BrambleloopStudioResearch/1.0 (+contact via Etsy shop BrambleloopStudio)"
FETCH_ACTION = "research.fetch"
MAX_BYTES = 512_000
TIMEOUT_S = 20.0
MIN_SECONDS_PER_HOST = 3.0
MAX_FETCHES_PER_RUN = 5

#: Host -> why this system may read it. Primary public sources only; nothing behind a login,
#: a paywall or terms that forbid automated reading.
ALLOWED_HOSTS: dict[str, str] = {
    "laws-lois.justice.gc.ca": "Justice Laws Website: official Canadian statutes and "
                               "regulations, Crown copyright, reproduction permitted",
    "www.canada.ca": "Government of Canada: official guidance published for public use",
    "www.cpsc.gov": "US Consumer Product Safety Commission: US government work, public domain",
    "en.wikipedia.org": "Wikimedia: terms permit identified automated reads",
    "help.etsy.com": "Etsy Help Center: robots-allowed public articles (gates.policy_reader)",
}
SECRET_PARAMS = ("key", "api_key", "apikey", "token", "access_token", "secret", "password",
                 "sig", "signature", "auth")

#: Learning domain -> improvement-bus subject a promoted finding is routed by.
DOMAIN_SUBJECT: dict[str, str] = {
    "techniques": "construction_preference", "aesthetics": "palette",
    "seasonal_behaviour": "seasonal_timing", "search_behaviour": "search_language",
    "media_capability": "thumbnail", "customer_pain": "delivery_experience",
    "marketplace_policy": "platform_policy",
}

_last_host_fetch: dict[str, float] = {}


class FetchRefused(ValueError):
    """A fetch this module will not make, with the reason."""


def check_url(url: str) -> str:
    """The host, if `url` may be fetched; FetchRefused otherwise. Makes no request."""
    u = urlparse(str(url or ""))
    if u.scheme != "https":
        raise FetchRefused(f"only https is fetched, not {u.scheme or 'no scheme'!r}")
    if u.username or u.password or "@" in (u.netloc or ""):
        raise FetchRefused("a URL carrying credentials is never fetched")
    host = (u.hostname or "").lower()
    try:
        port = u.port
    except ValueError as exc:
        raise FetchRefused(f"unreadable port in {url!r}") from exc
    if port not in (None, 443):
        # Review F-2: an allowlisted host on another port is another service.
        raise FetchRefused(f"only the default https port is fetched, not {port}")
    if host not in ALLOWED_HOSTS:
        raise FetchRefused(f"{host!r} is not on the research allowlist "
                           f"({sorted(ALLOWED_HOSTS)})")
    leaked = [k for k in parse_qs(u.query) if k.lower() in SECRET_PARAMS]
    if leaked:
        raise FetchRefused(f"a URL with secret-looking parameters {leaked} is never fetched")
    return host


class FetchUnavailable(OSError):
    """The network did not answer (DNS, timeout, TLS, reset): recorded as not fetched."""


def _redirect_handler():
    """Review F-2: every redirect target is re-checked against the allowlist and https
    (and the default port) before it is followed; one that fails is refused, not followed."""
    import urllib.request

    class _Checked(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            check_url(newurl)            # raises FetchRefused: the redirect is not followed
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    return _Checked()


def _default_get(url: str, *, max_bytes: int = MAX_BYTES) -> tuple[int, bytes]:
    import urllib.error
    import urllib.request

    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                               "Accept": "text/html,text/plain,*/*"})
    opener = urllib.request.build_opener(_redirect_handler())
    try:
        with opener.open(req, timeout=TIMEOUT_S) as r:  # noqa: S310 - allowlisted, re-checked
            final = r.geturl()
            if final != url:
                check_url(final)         # what was read is what the provenance names
            return r.status, r.read(max_bytes + 1)
    except urllib.error.HTTPError as exc:
        return exc.code, b""
    except FetchRefused:
        raise
    except UnicodeError as exc:
        # Review cbd4ff1 N-5: urllib encodes a redirect target as Latin-1 before the
        # allowlist sees it, so an IDN Location raises here. Not followed, and recorded as a
        # refusal like any other off-allowlist redirect.
        raise FetchRefused(f"unreadable redirect target ({type(exc).__name__}); "
                           "not followed") from exc
    except (urllib.error.URLError, OSError) as exc:
        # Review F-8: a DNS failure, timeout or TLS error is "not fetched", never a crash.
        raise FetchUnavailable(f"{type(exc).__name__}: {str(exc)[:160]}") from exc


def robots_allows(url: str, *, get=None) -> tuple[bool, str]:
    """Whether robots.txt lets this user agent read `url`. Unreadable is a refusal."""
    from urllib import robotparser

    u = urlparse(url)
    status, body = (get or _default_get)(f"https://{u.hostname}/robots.txt")
    if status == 404:
        return True, "no robots.txt (404): no restriction published"
    if status != 200:
        return False, f"robots.txt answered {status}: unreadable, so not fetched"
    if len(body) > MAX_BYTES:
        return False, "robots.txt larger than the byte cap: unreadable, so not fetched"
    rp = robotparser.RobotFileParser()
    rp.parse(body.decode("utf-8", errors="replace").splitlines())
    ok = rp.can_fetch(USER_AGENT, url)
    return ok, "robots.txt allows this user agent" if ok else "robots.txt disallows it"


def fetch_for_task(db, task_id: int, url: str, *, get=None, now: datetime | None = None,
                   sleep=time.sleep) -> dict:
    """Fetch one allowlisted page politely and record it as a `fetched` source of the task."""
    from ..core.models import AuditLog
    from . import research

    now = now or datetime.now(timezone.utc)
    get = get or _default_get
    def _refused(why: str) -> dict:
        out = {"task": task_id, "url": url, "fetched": False, "why": why}
        with db.session() as s:
            s.add(AuditLog(actor="learn", action=FETCH_ACTION, detail=out))
        return out

    try:
        host = check_url(url)
        allowed, why = robots_allows(url, get=get)
        if not allowed:
            raise FetchRefused(why)
    except FetchRefused as exc:
        return _refused(str(exc))
    except OSError as exc:
        return _refused(f"robots.txt not reachable: {str(exc)[:200]}")
    wait = MIN_SECONDS_PER_HOST - (time.monotonic() - _last_host_fetch.get(host, -1e9))
    if wait > 0:
        sleep(wait)
    try:
        status, body = get(url)
    except FetchRefused as exc:
        return _refused(f"redirect refused: {exc}")
    except OSError as exc:
        return _refused(f"not reachable: {str(exc)[:200]}")
    finally:
        _last_host_fetch[host] = time.monotonic()
    if status != 200 or not body:
        out = {"task": task_id, "url": url, "fetched": False,
               "why": f"{host} answered {status} with {len(body)} bytes"}
    elif len(body) > MAX_BYTES:
        out = {"task": task_id, "url": url, "fetched": False,
               "why": f"page larger than the {MAX_BYTES}-byte cap; not stored partially"}
    else:
        text = body.decode("utf-8", errors="replace")
        n = research.add_source(db, task_id, source=host, citation=url, retrieval="fetched",
                                read_on=now.date())
        out = {"task": task_id, "url": url, "fetched": True, "source_ref": f"S{n}",
               "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(),
               "excerpt": text[:2000], "basis": ALLOWED_HOSTS[host], "spend_cad": 0.0}
    with db.session() as s:
        s.add(AuditLog(actor="learn", action=FETCH_ACTION,
                       detail={k: v for k, v in out.items() if k != "excerpt"}))
    return out


def plan_fetches(db) -> list[tuple[int, str]]:
    """Open tasks whose trigger names a known source with an allowlisted URL."""
    from . import childrens, research

    out = []
    for t in research.tasks(db, state=research.OPEN):
        if not str(t["trigger"]).startswith("childrens.unfetched:"):
            continue
        key = t["trigger"].split(":", 1)[1].split("#", 1)[0]
        src = childrens.SOURCES.get(key)
        if src is None or any(x.get("citation") == src.url for x in t["sources"]):
            continue
        try:
            check_url(src.url)
        except FetchRefused:
            continue
        out.append((t["id"], src.url))
    # F-406 (W4-INTELREC C05): pages the Research Agent planned for an open task whose
    # internal evidence could not settle a platform question (`detail.fetch_urls`).
    from sqlalchemy import select

    from ..core.models import AuditLog

    research._ensure(db)
    planned = {tid for tid, _u in out}
    with db.session() as s:
        # a page this step already failed to read for that task is not retried every run
        failed = {((a.detail or {}).get("task"), (a.detail or {}).get("url"))
                  for a in s.scalars(select(AuditLog).where(AuditLog.action == FETCH_ACTION))
                  if (a.detail or {}).get("fetched") is False}
        rows = list(s.scalars(select(research.ResearchTask).where(
            research.ResearchTask.state == research.OPEN)))
        for r in rows:
            cited = {x.get("citation") for x in r.sources or []}
            for url in (r.detail or {}).get("fetch_urls") or []:
                if url in cited or (r.id, url) in out or r.id in planned \
                        or (r.id, url) in failed:
                    continue
                try:
                    check_url(url)
                except FetchRefused:
                    continue
                out.append((r.id, url))
                planned.add(r.id)
                break
    return out


def promote(db) -> dict:
    """Answered tasks with a fact become routed lessons; expired ones are withdrawn."""
    from ..improve import bus
    from . import research

    promoted, withdrawn, unrouted = [], [], []
    with db.session() as s:
        rows = list(s.scalars(research.select(research.ResearchTask).where(
            research.ResearchTask.state.in_([research.ANSWERED, research.EXPIRED]))))
        snap = [(r.id, r.state, r.domain, r.question, r.outcome, list(r.findings or []),
                 dict(r.detail or {})) for r in rows]
    for tid, state, domain, question, outcome, findings, detail in snap:
        facts = [f for f in findings if f.get("claim_class") == "fact"]
        lesson = detail.get("promoted_lesson")
        if state == research.EXPIRED and lesson and not detail.get("lesson_withdrawn"):
            bus.withdraw(db, lesson, reason=f"research task {tid} expired (F-433 freshness)",
                         evidence_ref=f"research_tasks:{tid}", withdrawn_by="learn")
            _set(db, tid, lesson_withdrawn=True)
            withdrawn.append(lesson)
            continue
        if state != research.ANSWERED or lesson or not facts:
            continue
        subject = DOMAIN_SUBJECT.get(domain)
        if subject is None or subject not in bus.SUBJECT_ROUTING:
            unrouted.append({"task": tid, "domain": domain})
            continue
        statement = (f"Research answered '{question[:160]}': {outcome[:200]}. Facts: "
                     + "; ".join(f["statement"][:160] for f in facts[:3]))
        lid = bus.publish(db, origin_cell="learn", subject=subject, statement=statement,
                          evidence_ref=f"research_tasks:{tid}", confidence="confirmed")
        _set(db, tid, promoted_lesson=lid)
        promoted.append(lid)
    return {"promoted": promoted, "withdrawn": withdrawn, "unrouted": unrouted}


def _set(db, tid: int, **kv) -> None:
    from . import research

    with db.session() as s:
        row = s.get(research.ResearchTask, tid)
        row.detail = {**(row.detail or {}), **kv}


ENABLE_VAR = "BRAMBLELOOP_RESEARCH_FETCH"


def fetch_enabled(env=None) -> bool:
    """The fetch step makes outbound requests, so it runs only where the deployment says so
    (`BRAMBLELOOP_RESEARCH_FETCH=1`). Off is reported, never silent; promotion always runs."""
    import os

    e = env if env is not None else os.environ
    return str(e.get(ENABLE_VAR) or "").strip() == "1"


def run(db, *, get=None, now: datetime | None = None, sleep=time.sleep, env=None) -> dict:
    """One research run: bounded fetches for planned sources, then promotion."""
    planned = plan_fetches(db)
    if get is None and not fetch_enabled(env):
        fetches = {"enabled": False, "planned": len(planned),
                   "why": f"fetch step off: {ENABLE_VAR} is not 1 in this deployment"}
    else:
        done = []
        for tid, url in planned[:MAX_FETCHES_PER_RUN]:
            # Review F-8: one bad fetch never stops the others or the promotion below.
            try:
                done.append(fetch_for_task(db, tid, url, get=get, now=now, sleep=sleep))
            except Exception as exc:  # noqa: BLE001
                done.append({"task": tid, "url": url, "fetched": False,
                             "why": f"fetch failed: {type(exc).__name__}: {str(exc)[:160]}"})
        fetches = {"enabled": True, "planned": len(planned),
                   "results": [{k: f.get(k) for k in ("task", "url", "fetched", "why")}
                               for f in done]}
    return {"fetches": fetches, **promote(db)}
