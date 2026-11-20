"""The marketplace half of the lead-lag model, and what one shop's shelf can honestly say.

Requirement 140 asks how cultural interest precedes or follows *Etsy demand*. That needs two
series. `culture.feeds` supplies the cultural one; this supplies the marketplace one, from
the only marketplace evidence this company has: 438 observed listings in one benchmark shop,
each with the date it was first seen.

**What this measures, stated before it is used.** It is the rate at which a benchmark seller
*publishes* into a topic, not the rate at which buyers purchase in it. Those are different
things and the gap between them is real: a seller can be early, late or wrong. Publication is
still a demand signal, because a seller with 438 listings is making a bet with their own
making-time on every one -- but it is a signal about one seller's reading of demand, and
calling it "Etsy demand" would be a claim about a marketplace from a sample of one shop.

**So the series is labelled and its width is reported with it.** Every result carries the
number of shops behind it. At one shop, `lead_lag` gets a real answer about this benchmark's
timing and a caveat that travels with the number rather than sitting in a document.

**A topic with no listings is unmeasured, not zero.** The distinction the whole build keeps
returning to. A benchmark that has never published into a topic and a topic with no demand
are the same empty list and opposite facts, and only one of them is a reason not to enter.
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import date, timedelta

CHANNEL = "etsy"

# A topic matches a listing when a distinctive word from the topic appears in the title.
# Words this short or this common match everything, so they are dropped rather than
# weighted: "the" in a title is not evidence about "The Last of Us".
MIN_TERM_CHARS = 4
STOPWORDS: frozenset[str] = frozenset({
    "the", "and", "for", "with", "from", "that", "this", "your", "you", "are", "was",
    "series", "film", "movie", "season", "part", "list", "disambiguation", "tv",
})

# Below this many matched listings a series is not computed. Two listings produce a peak
# wherever the second one landed, which is a date rather than a trend.
MIN_MATCHED_LISTINGS = 4

# The weeks a series spans. Matched to the culture window's scale so the two peaks are
# comparable rather than one being a year's shape against a month's.
WEEKS = 26


def terms(topic: str) -> list[str]:
    """The words from a topic that could distinguish a listing title."""
    words = re.split(r"[^A-Za-z0-9]+", topic.replace("_", " "))
    return [w.lower() for w in words
            if len(w) >= MIN_TERM_CHARS and w.lower() not in STOPWORDS]


def matches(title: str, topic_terms: list[str]) -> bool:
    lowered = (title or "").lower()
    return any(term in lowered for term in topic_terms)


def series(db, topic: str, *, benchmark_key: str = "", today: date | None = None) -> dict:
    """How often the benchmark published into this topic, week by week.

    Normalised against the window's own peak, exactly as the culture series is, so the two
    peaks are comparable. Absolute counts are meaningless across topics -- "blanket" matches
    a hundred listings and a film title matches three -- and the question is when each one
    peaked, not which is bigger.
    """
    from sqlalchemy import select

    from ..core.models import BenchmarkListing
    from ..intel import benchmarks

    benchmark_key = benchmark_key or benchmarks.MJS_KEY
    topic_terms = terms(topic)
    if not topic_terms:
        return {"measurable": False, "topic": topic, "matched": 0,
                "reason": (f"{topic!r} has no word long enough to distinguish a listing "
                           f"title. Matching on short or common words matches everything")}

    end = today or date.today()
    start = end - timedelta(weeks=WEEKS)

    with db.session() as s:
        rows = list(s.scalars(select(BenchmarkListing).where(
            BenchmarkListing.benchmark_key == benchmark_key)))

    matched = [r for r in rows if matches(r.title, topic_terms)]
    if len(matched) < MIN_MATCHED_LISTINGS:
        return {
            "measurable": False, "topic": topic, "matched": len(matched),
            "shops": 1,
            "reason": (f"{len(matched)} matched listings, under {MIN_MATCHED_LISTINGS}. Two "
                       f"listings produce a peak wherever the second one landed, which is a "
                       f"date rather than a trend"),
            "unmeasured_is_not_zero": (
                "a benchmark that has never published into this topic and a topic with no "
                "demand are the same empty list and opposite facts, and only one of them is "
                "a reason not to enter"),
        }

    weeks: Counter = Counter()
    for row in matched:
        seen = row.first_seen.date() if hasattr(row.first_seen, "date") else None
        if seen is None or seen < start or seen > end:
            continue
        weeks[(seen - start).days // 7] += 1
    if not weeks:
        return {"measurable": False, "topic": topic, "matched": len(matched), "shops": 1,
                "reason": (f"{len(matched)} listings match and none was first seen inside "
                           f"the {WEEKS}-week window. The catalogue was observed in one "
                           f"pass, so first_seen is the observation date for everything the "
                           f"baseline found -- a series needs listings discovered over time")}

    peak = max(weeks.values())
    points = [{"week_starting": (start + timedelta(weeks=w)).isoformat(),
               "listings": weeks.get(w, 0),
               "interest": round(weeks.get(w, 0) / peak, 4)}
              for w in range(WEEKS + 1)]
    return {
        "measurable": True, "topic": topic, "matched": len(matched), "shops": 1,
        "benchmark": benchmark_key, "points": points,
        "measures": ("how often this benchmark published into the topic, not how often "
                     "buyers bought in it. A seller can be early, late or wrong"),
        "width": ("one shop. This is that seller's reading of demand, and calling it 'Etsy "
                  "demand' would be a claim about a marketplace from a sample of one"),
    }


def record(db, topic: str, *, signal_key: str = "", benchmark_key: str = "",
           today: date | None = None) -> dict:
    """Write the marketplace series as observations the radar's lead-lag model can read."""
    from ..intel import benchmarks
    from . import radar

    got = series(db, topic, benchmark_key=benchmark_key, today=today)
    if not got.get("measurable"):
        return {"recorded": 0, **got}

    key = signal_key or topic.lower().replace(" ", "_")
    source = f"benchmark:{benchmark_key or benchmarks.MJS_KEY}"
    written = 0
    for point in got["points"]:
        if not point["listings"]:
            continue
        radar.observe(db, key, channel=CHANNEL, interest=point["interest"],
                      observed_on=point["week_starting"], source=source)
        written += 1
    return {"recorded": written, "topic": topic, "signal_key": key,
            "matched": got["matched"], "shops": got["shops"],
            "width": got["width"], "measures": got["measures"]}
