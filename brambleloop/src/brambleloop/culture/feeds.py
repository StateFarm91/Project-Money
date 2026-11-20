"""A connected source of cultural signal, chosen for being free, sanctioned and honest.

Requirements 133, 140, 147. The radar has been built and empty since it was written: it
refuses to return an empty trend list, because a radar with no source reporting no trends
looks exactly like a radar with a source and a quiet week, and the second reading is the one
an absent owner takes from a dashboard. What was missing was a feed.

**Wikimedia's Pageviews API, and why this one.** It is the official Wikimedia REST endpoint,
it is free, it needs no key and no account, and its terms permit this use with an identifying
user agent. Nothing here scrapes, nothing evades a rate limit, and no consequential spend is
involved -- which is what the owner's approval for this gate allows and all it allows.

**What it measures, said plainly rather than in the marketing sense.** Pageviews are
*reference-reading* interest: how many people looked something up. That is not search
interest and it is not purchase intent, and the difference is the useful part rather than a
caveat. A topic rising in reference reading is a topic people are trying to understand; a
topic rising in Etsy demand is one they are trying to buy. #140 asks precisely how culture
leads or lags marketplace demand, and a series that measured the same thing as the
marketplace would have nothing to say about the gap between them. So the channel is named
`reference` rather than `search`, and it is never reported as search volume.

**One source is not the model.** #140 needs two series to measure a lead-lag relationship and
this is one of them; the other is Etsy demand, which arrives with listings. This feed makes
the culture half real and leaves that stated rather than papered over.

**The lag is two days and it is carried, not hidden.** Wikimedia's own pipeline runs one to
two days behind, so `observed_on` is the day the data describes and never the day it was
fetched. A reading dated today from a pipeline that cannot know today is how a series gets
a phantom collapse at its right-hand edge.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from ..core.resilience import PermanentError, TransientError

SOURCE_KEY = "wikimedia_pageviews"
BASE = "https://wikimedia.org/api/rest_v1/metrics/pageviews"

# Wikimedia asks every automated client to identify itself with something a human can
# contact. A user agent that hides what it is has decided in advance it will not be welcome,
# and this feed's whole justification is that it is sanctioned.
USER_AGENT = "BrambleloopStudioResearch/1.0 (+contact via Etsy shop BrambleloopStudio)"

# The channel this feed writes. Not "search": see the module docstring. A feed that called
# reference reading "search interest" would make #140's lead-lag model compare a series with
# a mislabelled copy of itself.
CHANNEL = "reference"

# How far behind the pipeline runs. Taken as the API's own documented behaviour rather than
# discovered by finding zeroes at the edge of a series.
PIPELINE_LAG_DAYS = 2

# The window a momentum reading is computed over. Four weeks: long enough that a weekend is
# not a trend, short enough that a rising topic is still rising when it is noticed.
WINDOW_DAYS = 28

# Requests per sweep. Wikimedia's guidance is courtesy above all, and a cultural signal that
# needs hundreds of calls an hour is not a cultural signal.
MAX_ARTICLES_PER_SWEEP = 25
MIN_SECONDS_BETWEEN_CALLS = 1.0

PROBE_ACTION = "culture.probe"


class FeedRefused(PermanentError):
    """The source answered and the answer is not a series."""


@dataclass(frozen=True)
class Reading:
    """One topic's interest over the window, normalised to the radar's 0..1 scale."""

    signal_key: str
    article: str
    observed_on: str
    interest: float
    peak_views: int
    latest_views: int
    days: int
    source: str

    def to_dict(self) -> dict:
        return {"signal_key": self.signal_key, "article": self.article,
                "observed_on": self.observed_on, "interest": self.interest,
                "peak_views": self.peak_views, "latest_views": self.latest_views,
                "days": self.days, "source": self.source}


def _agent_headers() -> dict:
    return {"User-Agent": USER_AGENT, "Accept": "application/json"}


def _get(url: str, *, timeout: float = 20.0) -> dict:
    request = urllib.request.Request(url, headers=_agent_headers(), method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:300]
        if exc.code in (429, 500, 502, 503, 504):
            # 429 is transient and is also a message: the courtesy limits above are the
            # response to it, not a retry loop.
            raise TransientError(f"wikimedia {exc.code}: {detail}") from exc
        if exc.code == 404:
            raise FeedRefused(f"no such article or no data: {url}") from exc
        raise FeedRefused(f"wikimedia {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise TransientError(f"wikimedia unreachable: {exc.reason}") from exc


def window(today: date | None = None) -> tuple[date, date]:
    """The range the pipeline can actually answer for, lag included."""
    end = (today or date.today()) - timedelta(days=PIPELINE_LAG_DAYS)
    return end - timedelta(days=WINDOW_DAYS - 1), end


def series(article: str, *, today: date | None = None, project: str = "en.wikipedia",
           get=None) -> list[dict]:
    """Daily views for one article across the window. The raw series, undecorated."""
    start, end = window(today)
    quoted = urllib.parse.quote(article.replace(" ", "_"), safe="")
    url = (f"{BASE}/per-article/{project}/all-access/user/{quoted}/daily/"
           f"{start.strftime('%Y%m%d')}/{end.strftime('%Y%m%d')}")
    body = (get or _get)(url)
    items = body.get("items") or []
    if not items:
        raise FeedRefused(
            f"{article!r} returned no days. An empty series and a topic nobody reads about "
            f"are the same value and different facts, so this refuses rather than recording "
            f"an interest of zero")
    return [{"day": i.get("timestamp", "")[:8], "views": int(i.get("views") or 0)}
            for i in items]


def reading(article: str, *, signal_key: str = "", today: date | None = None,
            get=None) -> Reading:
    """One topic's momentum, as a number the radar accepts.

    Normalised against the window's own peak rather than against any absolute scale. There
    is no absolute scale for cultural attention that this company can reach, and inventing
    one -- views divided by some remembered maximum -- would produce a number that looked
    comparable across topics and was not. Within one topic, over one window, "how close is
    today to this topic's own recent peak" is a question the data can answer.
    """
    rows = series(article, today=today, get=get)
    views = [r["views"] for r in rows]
    peak = max(views) if views else 0
    latest = views[-1] if views else 0
    interest = round(latest / peak, 4) if peak else 0.0
    start, end = window(today)
    quoted = urllib.parse.quote(article.replace(" ", "_"), safe="")
    return Reading(
        signal_key=signal_key or article.lower().replace(" ", "_"),
        article=article, observed_on=end.isoformat(), interest=interest,
        peak_views=peak, latest_views=latest, days=len(rows),
        source=f"{SOURCE_KEY}:{BASE}/per-article/en.wikipedia/all-access/user/{quoted}")


def sweep(db, articles: list[str], *, today: date | None = None, get=None,
          signal_keys: dict[str, str] | None = None) -> dict:
    """Read a handful of topics and record each as a dated observation with its source.

    Every failure is named. A sweep that recorded nothing and returned a bare empty result
    is the same shape as a quiet week, which is the exact confusion this whole module exists
    to remove -- so `recorded: 0` arrives with the reasons beside it.
    """
    import time

    from . import radar

    if len(articles) > MAX_ARTICLES_PER_SWEEP:
        raise FeedRefused(
            f"{len(articles)} articles in one sweep, against {MAX_ARTICLES_PER_SWEEP}. The "
            f"courtesy limit is here rather than in a configuration file because a limit "
            f"somebody can raise without this repository recording it is not a limit")

    recorded, failures = [], []
    for index, article in enumerate(articles):
        if index and get is None:
            time.sleep(MIN_SECONDS_BETWEEN_CALLS)
        try:
            got = reading(article, today=today, get=get,
                          signal_key=(signal_keys or {}).get(article, ""))
        except (PermanentError, TransientError) as exc:
            failures.append({"article": article, "why": str(exc)[:200]})
            continue
        radar.observe(db, got.signal_key, channel=CHANNEL, interest=got.interest,
                      observed_on=got.observed_on, source=got.source)
        recorded.append(got.to_dict())

    return {
        "source": SOURCE_KEY,
        "channel": CHANNEL,
        "recorded": len(recorded),
        "attempted": len(articles),
        "readings": recorded,
        "failures": failures,
        "measures": ("reference reading, not search interest and not purchase intent. The "
                     "gap between this and marketplace demand is what #140 measures, so a "
                     "feed that measured the same thing would have nothing to say"),
        "lag_days": PIPELINE_LAG_DAYS,
    }


def probe(db, *, article: str = "Crochet", today: date | None = None, get=None,
          now: datetime | None = None) -> dict:
    """Read one real series and record whether that worked. The gate's evidence.

    A source that is free and needs no key still has to answer. Unreachable, rate-limited,
    and returning an empty series are three different states, and a gate that checked
    whether a feed was "configured" could not see any of them -- there is no configuration.
    """
    from ..core.models import AuditLog

    record: dict = {"at": (now or datetime.now(timezone.utc)).isoformat(),
                    "source": SOURCE_KEY, "article": article, "ok": False, "reason": ""}
    try:
        got = reading(article, today=today, get=get)
    except (PermanentError, TransientError) as exc:
        record["reason"] = str(exc)[:400]
    else:
        record.update({"ok": True, "days": got.days, "interest": got.interest,
                       "observed_on": got.observed_on, "peak_views": got.peak_views})
        if got.days < WINDOW_DAYS // 2:
            record["ok"] = False
            record["reason"] = (
                f"{got.days} days of a {WINDOW_DAYS}-day window. A series with holes in it "
                f"is a momentum reading with holes in it, and the holes do not announce "
                f"themselves downstream")

    with db.session() as s:
        s.add(AuditLog(actor="orchestrator", action=PROBE_ACTION, artifact=SOURCE_KEY,
                       detail=record))
    return record


def state(db) -> dict:
    """What this feed is, what it is not, and whether it has ever answered."""
    from sqlalchemy import desc, func, select

    from ..core.models import AuditLog, CultureObservation

    with db.session() as s:
        rows = list(s.scalars(select(AuditLog).where(AuditLog.action == PROBE_ACTION)
                              .order_by(desc(AuditLog.id)).limit(1)))
        observations = s.scalar(select(func.count(CultureObservation.id)).where(
            CultureObservation.source != "")) or 0
    last = dict(rows[0].detail or {}) if rows else None

    return {
        "source": SOURCE_KEY,
        "requires_a_key": False,
        "cost_cad_per_month": 0.0,
        "sanctioned": ("Wikimedia's own REST API, used within its documented terms with an "
                       "identifying user agent. Nothing here scrapes and nothing evades a "
                       "rate limit"),
        "channel": CHANNEL,
        "measures": "reference reading: how many people looked a topic up",
        "does_not_measure": ("search volume, social volume or purchase intent. Calling this "
                             "search interest would make #140's lead-lag model compare a "
                             "series against a mislabelled copy of itself"),
        "lag_days": PIPELINE_LAG_DAYS,
        "last_probe": last,
        "usable": bool(last and last.get("ok")),
        "sourced_observations": observations,
        "still_missing_for_140": ("the marketplace demand series. A lead-lag model needs two "
                                  "series, and this is one of them"),
    }


def usable(db) -> bool:
    """Whether this feed has actually returned a series."""
    last = state(db)["last_probe"]
    return bool(last and last.get("ok"))


# The standing watch list: topics this catalogue is merchandised against, whose interest is
# worth a series whether or not they trend. Discovery finds what nobody thought to ask about;
# this is the floor beneath it.
#
# Every entry is a real article title. The first version derived them from the radar's domain
# keys -- "Viral Aesthetic", "Nostalgia Era", "Seasonal Tradition", "Celebrity Aesthetic" --
# which are vocabulary this build invented and not things anybody has written an encyclopaedia
# article about. The first production sweep recorded 7 of 12 and named the five failures,
# which is the only reason it was visible at all: a feed that returned zero for a missing
# article, rather than refusing, would have recorded five topics as having no cultural
# interest whatsoever and nobody would have looked again.
STANDING_TOPICS: tuple[str, ...] = (
    "Crochet", "Amigurumi", "Yarn", "Knitting", "Granny_square", "Crochet_hook",
    "Christmas_stocking", "Christmas", "Halloween", "Internet_meme", "Nostalgia", "Fashion",
)


def default_articles(db, *, limit: int = 12) -> list[str]:
    """Which topics to read whether or not they trend.

    Deliberately not derived from this build's own domain vocabulary. Those are filing
    categories, not things the world reads about, and asking a pageview API for them returns
    nothing -- which is a refusal here and would be an interest of zero anywhere less
    careful.
    """
    return list(STANDING_TOPICS)[:limit]


def env_override(env: dict[str, str] | None = None) -> list[str]:
    """An owner-supplied topic list, if one is set. Never required."""
    e = env if env is not None else os.environ
    raw = (e.get("BRAMBLELOOP_CULTURE_TOPICS") or "").strip()
    return [part.strip() for part in raw.split(",") if part.strip()]


# ---------------------------------------------------------------------------
# Discovery (#133): what spiked, rather than what somebody thought to ask about
#
# A fixed topic list is a radar that can only find what its author already knew. #133's
# purpose is *early demand discovery* -- identifying what people are emotionally engaging
# with before Etsy competition reflects it -- and a list written by hand reflects the author
# rather than the culture. So the day's most-read articles are the candidate set, and the
# fixed list becomes the floor rather than the whole of it.


# Pages that are not topics. Wikipedia's most-read list is dominated by them, and a radar
# that reported "Main Page is trending" every day would be ignored by the second week.
META_PREFIXES: tuple[str, ...] = (
    "Main_Page", "Special:", "Wikipedia:", "Portal:", "Help:", "Category:", "File:",
    "Template:", "Talk:", "User:", "-",
)

# How many of the day's top articles to consider. Deep enough that the list is not just the
# same handful of perennials, shallow enough to stay inside the courtesy limits.
DISCOVERY_DEPTH = 60


def _is_topic(article: str) -> bool:
    return bool(article) and not any(article.startswith(p) for p in META_PREFIXES)


def discover(*, today: date | None = None, project: str = "en.wikipedia",
             depth: int = DISCOVERY_DEPTH, get=None) -> dict:
    """What the world read most on the most recent day the pipeline can answer for.

    One request, not one per topic: the `top` endpoint returns the day's ranking in a single
    call, which is what makes discovery affordable against a free source this company wants
    to keep being welcome at.
    """
    _, day = window(today)
    url = (f"{BASE}/top/{project}/all-access/"
           f"{day.year:04d}/{day.month:02d}/{day.day:02d}")
    body = (get or _get)(url)
    items = ((body.get("items") or [{}])[0].get("articles")) or []
    if not items:
        raise FeedRefused(
            f"the top-articles endpoint returned no ranking for {day.isoformat()}. An empty "
            f"ranking and a day nobody read anything are the same value and different facts")

    ranked = [{"article": i.get("article", ""), "views": int(i.get("views") or 0),
               "rank": int(i.get("rank") or 0)}
              for i in items if _is_topic(i.get("article", ""))]
    return {"day": day.isoformat(), "project": project,
            "considered": len(items), "topics": ranked[:depth],
            "source": f"{SOURCE_KEY}:{url}",
            "note": ("the day's most-read articles, meta pages removed. A radar with a "
                     "hand-written topic list can only find what its author already knew, "
                     "which is the opposite of early discovery")}
