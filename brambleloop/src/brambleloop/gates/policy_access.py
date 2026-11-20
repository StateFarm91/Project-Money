"""What of Etsy's legal policy software may read honestly, and what only a person can (#35, #39).

W4-B2GATE2, 2026-10-11. The `rendered_pages` gate opens for #35/#39 on a person's current
reading of the five etsy.com/legal sources (`platform_policy.page_readings_status`). That part
is not automatable here, and this module records *why*, per source, as evidence rather than as
a sentence in a document:

- **The pages themselves.** etsy.com/legal answers automated clients HTTP 403 from DataDome
  (re-proven 2026-10-11 from the build container: GET /legal/sellers/ with the identifying
  research user agent -> 403). Passing that challenge would be evasion, so this module never
  requests a legal page. In addition, Etsy's own robots.txt disallows `/*handmade/` for every
  agent, which covers `/legal/handmade/`, the Creativity Standards URL this repository watches:
  that page is off-limits to software even if the 403 were lifted. `robots_verdicts` computes
  this from the live robots.txt (which Etsy serves to every client) on each run.
- **What Etsy itself publishes about those pages through a sanctioned channel.** Etsy's Help
  Center article API (`help.etsy.com/api/v2/help_center/...`, robots-allowed, the reader
  `gates.policy_reader` already uses) returns articles that *link to* the legal pages, with
  Etsy's own `edited_at`. Those companion articles are not the policy and never open the gate.
  They are a change signal: when Etsy edits an article that points at a policy page after the
  person's last reading of that page, a re-read is suggested before the 30 days run out.
  The link is checked on every read -- an article that stops linking the page stops being
  its companion, and says so.
- **children_and_baby has no companion.** No Help Center article found on 2026-10-11 links
  its page, so for that source there is no machine signal at all: only the person's reading.

Only digests and Etsy's dates are stored; no article or policy text is kept.
"""
from __future__ import annotations

import fnmatch
import json
import re
import time
import urllib.error
import urllib.request
from datetime import date

from .platform_policy import POLICY_SOURCES, PolicyRefused, digest_of
from .policy_reader import HELP_API, MIN_SECONDS_BETWEEN_FETCHES, USER_AGENT, _text_of

AUDIT_ACTION = "policy.access_evidence"
ROBOTS_URL = "https://www.etsy.com/robots.txt"

DIRECT_FETCH = ("not attempted: etsy.com/legal answers automated clients HTTP 403 from DataDome "
                "(re-proven 2026-10-11 from the build container, GET /legal/sellers/ with an "
                "identifying user agent). Passing that bot challenge would be evasion, which "
                "this company refuses; a person reading the page in their own browser is not")

# Pages a person reads for each etsy.com/legal source. The watched URL first; then the pages
# Etsy's own Help Center links for the same policy (read 2026-10-11 through the article API):
# article 33558571339159 (edited 2026-07-23) links "Creativity Standards" at /legal/creativity,
# and article 115015808588 links the shilling policy at /legal/policy/shilling/. The
# repository's dated knowledge (`policy_knowledge.READINGS`) cites the children's-products
# policy page as well.
LEGAL_PAGES: dict[str, tuple[str, ...]] = {
    "seller_policy": ("https://www.etsy.com/legal/sellers/",),
    "creativity_standards": ("https://www.etsy.com/legal/handmade/",
                             "https://www.etsy.com/legal/creativity/"),
    "advertising_rules": ("https://www.etsy.com/legal/advertising/",),
    "shilling_and_reviews": ("https://www.etsy.com/legal/prohibited/",
                             "https://www.etsy.com/legal/policy/shilling/"),
    "children_and_baby": ("https://www.etsy.com/legal/prohibited-items/children/",
                          "https://www.etsy.com/legal/policy/childrens-clothing-and-products/"
                          "239344787532"),
}

# Help Center articles Etsy publishes that link each legal page, with the path fragments the
# link must contain. Found 2026-10-11 by reading the article API; each link is re-verified on
# every read.
COMPANIONS: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    "seller_policy": (("360024112614", ("/legal/sellers",)),
                      ("115015808588", ("/legal/sellers",)),
                      ("33558571339159", ("/legal/sellers",))),
    "creativity_standards": (("360024112614", ("/legal/handmade", "/legal/creativity")),
                             ("33558571339159", ("/legal/handmade", "/legal/creativity"))),
    "advertising_rules": (("360033701174", ("/legal/advertising",)),
                          ("360000338367", ("/legal/advertising",))),
    "shilling_and_reviews": (("115015808588", ("/legal/policy/shilling",)),
                             ("360000336727", ("/legal/prohibited",))),
    "children_and_baby": (),
}

_LINK = re.compile(r"""href=["'](https?://(?:www\.)?etsy\.com/legal/[^"'#?]*)""", re.I)


def external_sources() -> list[str]:
    from .policy_reader import external_sources as ext

    return ext()


# ---------------------------------------------------------------------------
# robots.txt, evaluated rather than assumed


def _rules_for_all_agents(robots_txt: str) -> list[tuple[str, str]]:
    """(directive, pattern) of the `User-agent: *` group(s)."""
    rules: list[tuple[str, str]] = []
    agents: list[str] = []
    in_rules = False
    for raw in (robots_txt or "").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        field, value = (x.strip() for x in line.split(":", 1))
        field = field.lower()
        if field == "user-agent":
            if in_rules:
                agents, in_rules = [], False
            agents.append(value)
        elif field in ("allow", "disallow"):
            in_rules = True
            if "*" in agents and value:
                rules.append((field, value))
    return rules


def _matches(pattern: str, path: str) -> bool:
    anchored = pattern.endswith("$")
    pat = pattern[:-1] if anchored else pattern
    glob = pat.replace("[", "[[]").replace("?", "[?]") + ("" if anchored else "*")
    return fnmatch.fnmatchcase(path, glob)


def robots_verdict(robots_txt: str, url: str) -> dict:
    """Allowed or disallowed for `*`, by the longest matching rule (Allow wins a tie)."""
    path = re.sub(r"^https?://[^/]+", "", url) or "/"
    best: tuple[int, str, str] | None = None
    for directive, pattern in _rules_for_all_agents(robots_txt):
        if _matches(pattern, path):
            key = (len(pattern), directive == "allow")
            if best is None or key > (best[0], best[1] == "allow"):
                best = (len(pattern), directive, pattern)
    if best is None:
        return {"url": url, "robots": "allowed", "rule": None}
    return {"url": url, "robots": "allowed" if best[1] == "allow" else "disallowed",
            "rule": f"{best[1].capitalize()}: {best[2]}"}


# ---------------------------------------------------------------------------
# the read


def _fetch_json(url: str, *, timeout: float = 30.0) -> dict:
    request = urllib.request.Request(url, method="GET")
    request.add_header("user-agent", USER_AGENT)
    request.add_header("accept", "application/json")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode())


def _fetch_text(url: str, *, timeout: float = 30.0) -> str:
    request = urllib.request.Request(url, method="GET")
    request.add_header("user-agent", USER_AGENT)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode(errors="replace")


def _previous(db) -> dict:
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    with db.session() as s:
        row = s.scalar(select(AuditLog).where(AuditLog.action == AUDIT_ACTION)
                       .order_by(desc(AuditLog.id)).limit(1))
        return dict(row.detail or {}) if row is not None else {}


def assess(db, *, fetch_json=None, fetch_text=None, sleep=time.sleep,
           today: date | None = None) -> dict:
    """Record, per etsy.com/legal source, what software may read and what it read.

    One GET of robots.txt and one Help Center API GET per companion article, with the polite
    gap; never a legal page. Failures are recorded in the source's own words and are never
    readings. Writes one `policy.access_evidence` audit row.
    """
    from ..core.models import AuditLog

    fetch_json = fetch_json or _fetch_json
    fetch_text = fetch_text or _fetch_text
    today = today or date.today()
    previous = (_previous(db).get("sources") or {})

    robots_txt, robots_error = "", ""
    try:
        robots_txt = fetch_text(ROBOTS_URL)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        robots_error = f"{type(exc).__name__}: {str(exc)[:160]}"

    articles: dict[str, dict] = {}
    calls = 0
    sources: dict[str, dict] = {}
    for source in external_sources():
        pages = LEGAL_PAGES.get(source) or (POLICY_SOURCES[source][0],)
        robots = ([robots_verdict(robots_txt, u) for u in pages] if robots_txt else
                  [{"url": u, "robots": "unknown", "rule": None, "why": robots_error}
                   for u in pages])
        companions = []
        for article_id, fragments in COMPANIONS.get(source, ()):
            if article_id not in articles:
                if calls:
                    sleep(MIN_SECONDS_BETWEEN_FETCHES)
                calls += 1
                entry: dict = {"article_id": article_id, "ok": False}
                try:
                    art = (fetch_json(HELP_API.format(id=article_id)) or {}).get("article") or {}
                    if str(art.get("id")) != article_id:
                        raise PolicyRefused(f"the API answered with {art.get('id')!r}")
                    if art.get("draft"):
                        raise PolicyRefused("a draft is not published guidance")
                    body = art.get("body") or ""
                    entry.update(ok=True, title=str(art.get("title") or "")[:160],
                                 edited_at=str(art.get("edited_at") or ""),
                                 digest=digest_of(_text_of(body)),
                                 legal_links=sorted({m.rstrip("/") for m in _LINK.findall(body)}))
                except (urllib.error.URLError, OSError, ValueError, PolicyRefused) as exc:
                    code = getattr(exc, "code", None)
                    entry["reason"] = (f"HTTP {code}: refused; not retried" if code else
                                       f"{type(exc).__name__}: {str(exc)[:160]}")
                articles[article_id] = entry
            art = articles[article_id]
            c = {k: art.get(k) for k in ("article_id", "ok", "title", "edited_at", "digest",
                                          "reason") if art.get(k) is not None}
            if art.get("ok"):
                c["links_policy_page"] = any(f in link for link in art["legal_links"]
                                             for f in fragments)
                before = next((p for p in (previous.get(source) or {}).get("companions", [])
                               if p.get("article_id") == article_id and p.get("digest")), None)
                c["changed_since_last_run"] = bool(before and before["digest"] != c["digest"])
            companions.append(c)
        signal = [c for c in companions if c.get("ok") and c.get("links_policy_page")]
        sources[source] = {
            "pages": list(pages), "robots": robots, "direct_fetch": DIRECT_FETCH,
            "companions": companions,
            "machine_signal": ("help_center_companion" if signal else "none"),
            "needs_person": True,
            "why_person": (
                "the policy text is only on etsy.com/legal, which refuses software"
                + ("; robots.txt also disallows "
                   + ", ".join(r["url"] for r in robots if r["robots"] == "disallowed")
                   if any(r["robots"] == "disallowed" for r in robots) else "")
                + ("" if signal else "; and no Etsy Help Center article links this page, so "
                                     "there is no machine change signal either")),
        }
    report = {"read_on": today.isoformat(), "robots_url": ROBOTS_URL,
              "robots_read": bool(robots_txt), "help_center_calls": calls,
              "sources": sources,
              "changed_companions": sorted(
                  {s for s, v in sources.items()
                   if any(c.get("changed_since_last_run") for c in v["companions"])}),
              "never_fetched": "etsy.com/legal pages: " + DIRECT_FETCH}
    with db.session() as s:
        s.add(AuditLog(actor="orchestrator", action=AUDIT_ACTION, artifact="etsy_legal",
                       detail=report))
    return report


def status(db, *, today: date | None = None) -> dict:
    """The person's half and the company's half of #35/#39, side by side.

    `reread_suggested` names each source whose companion article Etsy edited after the
    person's newest page reading of it (or that changed since the previous run). It is a
    suggestion that shortens the wait for a re-read; it never opens or closes the gate,
    which stays `platform_policy.page_readings_status`.
    """
    from .platform_policy import page_readings_status

    today = today or date.today()
    readings = page_readings_status(db, today=today)
    last = _previous(db)
    per: dict[str, dict] = {}
    for source in external_sources():
        ev = (last.get("sources") or {}).get(source) or {}
        reading = readings["sources"].get(source) or {}
        checked = reading.get("checked_on") or ""
        newer = sorted(c["article_id"] for c in ev.get("companions", [])
                       if c.get("links_policy_page") and checked
                       and str(c.get("edited_at") or "")[:10] > checked)
        changed = [c["article_id"] for c in ev.get("companions", [])
                   if c.get("changed_since_last_run")]
        per[source] = {
            "person_reading": reading,
            "pages_to_read": list(LEGAL_PAGES.get(source) or (POLICY_SOURCES[source][0],)),
            "machine_signal": ev.get("machine_signal", "not yet assessed"),
            "robots": ev.get("robots", []),
            "reread_suggested": bool(newer or changed),
            "why": (f"Etsy edited companion article(s) {', '.join(newer or changed)} after "
                    f"this page was last read" if (newer or changed) else ""),
        }
    return {"gate_open": readings["open"], "not_current": readings["not_current"],
            "assessed_on": last.get("read_on"), "sources": per,
            "company_side": ("reads robots.txt and Etsy's Help Center article API (sanctioned, "
                             "robots-allowed) for articles that link each legal page, and "
                             "records their digests and Etsy's edited_at as change signals"),
            "person_side": ("reads each etsy.com/legal page in their own browser and records it "
                            "through POST /api/policy/snapshot with read_by; only that opens "
                            "the rendered_pages gate"),
            "direct_fetch": DIRECT_FETCH}
