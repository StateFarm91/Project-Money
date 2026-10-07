"""The sanctioned reader for the watched policies Etsy publishes in its Help Center (#39).

W4-GATESI, 2026-10-07. The `rendered_pages` gate was written as "a browser worker that can
fetch an Etsy page as a buyer sees it", and every watched policy was parked behind it. Two
facts split that in two:

- **etsy.com/legal/** answers every automated reader with HTTP 403 from DataDome
  (`server: DataDome`, `x-datadome: protected`, risk score 0.997 on an honest, identifying
  request, re-proven 2026-10-07). A headless browser in this container would be a client
  trying to pass a bot challenge, which is evasion and is refused. Those sources stay
  EXTERNAL (`build2.closure.EXTERNAL_GATES["rendered_pages"]`) and a person records them
  (`platform_policy.record_page_reading`).
- **help.etsy.com** is a Zendesk Help Center. Its HTML pages are behind a Cloudflare
  challenge, but its public Help Center *article API*
  (`/api/v2/help_center/en-us/articles/<id>.json`) answers 200 with the article body and
  Etsy's own `edited_at`, and robots.txt for help.etsy.com does not disallow it (only
  `/api/v2/help_center/*/articles/*/stats/view`). `integrations.etsy_constraints` already reads
  Etsy's image and listing limits this way. So the watched sources that *live* in the Help
  Center (`listing_image_rules`, `search_guidance`) need no browser at all.

This module reads exactly those: one GET per source, an identifying user agent, a polite gap
between requests, the article body reduced to text, digested by
`platform_policy.record_snapshot` (the text itself is never stored), basis
`help_center_api`. A material change is computed against the previous reading **of the same
basis**, so the first real reading does not masquerade as Etsy changing a policy relative to
an older search-engine excerpt. A source is recorded at most once per day unless its digest
moved.

What it never does: fetch etsy.com/legal, fetch an HTML page, retry past a refusal, or call
a refusal a reading.
"""
from __future__ import annotations

import html
import json
import re
import time
import urllib.error
import urllib.request
from datetime import date

from .platform_policy import POLICY_SOURCES, PolicyRefused, record_snapshot

BASIS = "help_center_api"
READ_BY = "gates.policy_reader"
AUDIT_ACTION = "policy.help_center_read"
HELP_API = "https://help.etsy.com/api/v2/help_center/en-us/articles/{id}.json"
USER_AGENT = "BrambleloopStudioResearch/1.0 (+contact via Etsy shop BrambleloopStudio)"
MIN_SECONDS_BETWEEN_FETCHES = 3.0
# An article body shorter than this is not a policy text: an error document or an empty
# draft arrives with HTTP 200 too.
MIN_TEXT_CHARS = 200

_ARTICLE = re.compile(r"^https://help\.etsy\.com/hc/[a-z-]+/articles/(\d+)")


ENABLE_VAR = "BRAMBLELOOP_POLICY_READER"


def enabled(env: dict[str, str] | None = None) -> bool:
    """Whether the cadence may make the network read here.

    On by itself in the hosted container (any `core.db.HOSTED_MARKERS` variable, which the
    platform injects -- no owner configuration), off in a test process or a laptop unless
    `BRAMBLELOOP_POLICY_READER=1`; `=0` turns it off anywhere. A test that runs the policy
    watch must never reach the network by accident.
    """
    import os

    from ..core.db import HOSTED_MARKERS

    e = env if env is not None else os.environ
    flag = (e.get(ENABLE_VAR) or "").strip()
    if flag == "0":
        return False
    return flag == "1" or any((e.get(m) or "").strip() for m in HOSTED_MARKERS)


def help_center_sources() -> dict[str, str]:
    """Watched source -> Help Center article id, for every source that lives there."""
    out: dict[str, str] = {}
    for source, (url, _affects) in POLICY_SOURCES.items():
        m = _ARTICLE.match(url)
        if m:
            out[source] = m.group(1)
    return out


def external_sources() -> list[str]:
    """Watched sources with no sanctioned reader (etsy.com/legal behind DataDome)."""
    hc = help_center_sources()
    return sorted(s for s in POLICY_SOURCES if s not in hc)


def _text_of(body_html: str) -> str:
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", body_html or "")
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return " ".join(html.unescape(text).split())


def _fetch(url: str, *, timeout: float = 30.0) -> dict:
    request = urllib.request.Request(url, method="GET")
    request.add_header("user-agent", USER_AGENT)
    request.add_header("accept", "application/json")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode())


def read_help_center(db, *, fetch=None, sleep=time.sleep, today: date | None = None) -> dict:
    """Read every Help-Center-hosted watched policy once; record what was actually read.

    `fetch(url) -> dict` is injectable so tests never reach the network. Each failure is
    recorded with the reason in the source's own words and is never a snapshot.
    """
    from ..core.models import AuditLog

    fetch = fetch or _fetch
    today = today or date.today()
    results: dict[str, dict] = {}
    for i, (source, article_id) in enumerate(sorted(help_center_sources().items())):
        if i:
            sleep(MIN_SECONDS_BETWEEN_FETCHES)
        url = HELP_API.format(id=article_id)
        entry: dict = {"article_id": article_id, "api_url": url, "ok": False}
        try:
            payload = fetch(url)
            article = (payload or {}).get("article") or {}
            if str(article.get("id")) != article_id:
                raise PolicyRefused(f"the API answered with article {article.get('id')!r}, "
                                    f"not {article_id}")
            if article.get("draft"):
                raise PolicyRefused("the article is a draft, which is not published policy")
            text = _text_of(article.get("body") or "")
            if len(text) < MIN_TEXT_CHARS:
                raise PolicyRefused(f"{len(text)} characters of body, under {MIN_TEXT_CHARS}: "
                                    f"not a policy text")
            edited = str(article.get("edited_at") or "")
            entry.update(title=str(article.get("title") or ""), edited_at=edited,
                         text_chars=len(text))
            if _already_read_today(db, source, text, today):
                entry.update(ok=True, recorded=False,
                             why="read; same digest as today's reading, not recorded twice")
            else:
                res = record_snapshot(
                    db, source, text=text, version=edited or today.isoformat(),
                    summary=f"Help Center article {article_id} '{entry['title']}' "
                            f"(edited_at {edited}) read through the article API",
                    checked_on=today.isoformat(), read_by=READ_BY, basis=BASIS,
                    compare_basis=BASIS)
                entry.update(ok=True, recorded=True, snapshot_id=res["id"],
                             digest=res["digest"], material_change=res["material_change"],
                             first_reading_on_basis=res["first_reading"])
        except (urllib.error.URLError, OSError, ValueError, PolicyRefused) as exc:
            code = getattr(exc, "code", None)
            entry["reason"] = (f"HTTP {code}: refused; not retried and not read" if code
                               else f"{type(exc).__name__}: {str(exc)[:200]}")
        results[source] = entry

    report = {"basis": BASIS, "read": sorted(k for k, v in results.items() if v["ok"]),
              "failed": sorted(k for k, v in results.items() if not v["ok"]),
              "external": external_sources(), "results": results,
              "external_why": ("etsy.com/legal answers automated readers 403 from DataDome; "
                               "a person records those (POST /api/policy/snapshot)")}
    with db.session() as s:
        s.add(AuditLog(actor="orchestrator", action=AUDIT_ACTION, artifact=BASIS,
                       detail={k: report[k] for k in ("read", "failed", "external")}
                       | {"results": {k: {kk: vv for kk, vv in v.items()}
                                      for k, v in results.items()}}))
    return report


def _already_read_today(db, source: str, text: str, today: date) -> bool:
    from sqlalchemy import select

    from ..core.models import PolicySnapshot
    from .platform_policy import digest_of

    digest = digest_of(text)
    with db.session() as s:
        for r in s.scalars(select(PolicySnapshot).where(PolicySnapshot.source == source)
                           .order_by(PolicySnapshot.id.desc()).limit(20)):
            if (r.detail or {}).get("basis") == BASIS:
                return r.checked_on == today.isoformat() and r.digest == digest
    return False
