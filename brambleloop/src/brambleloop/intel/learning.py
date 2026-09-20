"""What the world outside this company said, kept apart from what this company knows.

Requirement 98. The radar itself is unremarkable -- observations with a source and a date --
and the requirement's real instruction is the second clause: every observation is *separated
from verified internal causal evidence*. That separation is the whole thing, because it is
lost in a single sentence and never recovered.

The failure runs like this. Somebody reads that textured stitches are trending. It goes in a
brief as context. The next brief cites the first. Six weeks later "textured stitches sell
better" is something the company knows, and nobody can say who measured it. The observation
was never wrong; it was never evidence either, and the step where it became evidence was a
sentence nobody noticed writing.

So observations live in their own table, they are called signals wherever they are used, and
the function that would turn one into causal evidence refuses by name. A decision may rest on
signals -- most early decisions must -- but it says so, and a reader six weeks later can tell
the difference between a thing this company measured and a thing it read.

Freshness is per domain rather than global, for the reason #38 gives about trend data: a
marketplace policy from three weeks ago may already be wrong, and a stitch technique from
last year is not stale at all.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone


@dataclass(frozen=True)
class Domain:
    key: str
    what: str
    fresh_for_days: int
    why: str


DOMAINS: tuple[Domain, ...] = (
    Domain("techniques", "new or revived crochet techniques", 365,
           "a stitch technique does not expire; it is either known here or it is not"),
    Domain("aesthetics", "palettes, styling and visual language", 180,
           "aesthetic language moves seasonally, roughly twice a year"),
    Domain("seasonal_behaviour", "how buyers behave around an occasion", 400,
           "one full cycle: last January's Christmas observation is about to be current"),
    Domain("marketplace_policy", "seller policy, listing rules, advertising rules", 21,
           "a policy read three weeks ago may already be the wrong policy, and acting on "
           "the old one is the kind of mistake that closes a shop"),
    Domain("search_behaviour", "how the platform's search and ranking behave", 60,
           "search behaviour changes without announcement and old observations mislead "
           "most exactly where they are most useful"),
    Domain("media_capability", "image, video and listing-media capabilities", 120,
           "capability changes are announced and then take months to matter"),
    Domain("competitor_positioning", "how other shops present and price themselves", 90,
           "positioning is a quarter-scale thing; a shop does not re-found itself monthly"),
    Domain("customer_pain", "what buyers complain about in this category", 180,
           "complaints are durable: the same six problems recur for years"),
)

DOMAIN_BY_KEY: dict[str, Domain] = {d.key: d for d in DOMAINS}


class LearningRefused(ValueError):
    """An observation with no source or date, or one being promoted into evidence."""


def record(db, *, domain: str, source: str, citation: str, summary: str,
           observed_on: date, detail: dict | None = None) -> int:
    """Store one external observation, with where and when it was observed.

    A source and a date are required rather than encouraged. An observation that cannot say
    where it came from is a belief, and the reason this refuses instead of flagging is that
    a flagged row is still a row somebody will quote.
    """
    from ..core.models import LearningObservation

    if domain not in DOMAIN_BY_KEY:
        raise LearningRefused(
            f"{domain!r} is not a learning domain: {sorted(DOMAIN_BY_KEY)}. An unclassified "
            f"observation gets whatever freshness the reader assumes")
    if not source.strip():
        raise LearningRefused("an observation with no source is a belief, not an observation")
    if not citation.strip():
        raise LearningRefused(
            "no citation. A future reader has to be able to go back to the thing itself, "
            "because the summary is already an interpretation")
    if len(summary.split()) < 6:
        raise LearningRefused(
            f"{summary!r} is a label rather than an observation; say what was observed")

    when = datetime(observed_on.year, observed_on.month, observed_on.day,
                    tzinfo=timezone.utc)
    if when > datetime.now(timezone.utc) + timedelta(days=1):
        raise LearningRefused("an observation cannot have been made in the future")

    with db.session() as s:
        row = LearningObservation(domain=domain, source=source.strip(),
                                  citation=citation.strip(), summary=summary.strip(),
                                  observed_on=when, detail=detail or {})
        s.add(row)
        s.flush()
        return row.id


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def observations(db, *, domain: str | None = None, today: date | None = None) -> list[dict]:
    """Every observation, each carrying its own age and whether it is still fresh."""
    from sqlalchemy import select

    from ..core.models import LearningObservation

    now = datetime(today.year, today.month, today.day, tzinfo=timezone.utc) if today \
        else datetime.now(timezone.utc)

    with db.session() as s:
        stmt = select(LearningObservation)
        if domain is not None:
            stmt = stmt.where(LearningObservation.domain == domain)
        rows = list(s.scalars(stmt.order_by(LearningObservation.observed_on.desc())))
        out = []
        for row in rows:
            age = (now - _aware(row.observed_on)).days
            window = DOMAIN_BY_KEY[row.domain].fresh_for_days
            out.append({"id": row.id, "domain": row.domain, "source": row.source,
                        "citation": row.citation, "summary": row.summary,
                        "observed_on": _aware(row.observed_on).date().isoformat(),
                        "age_days": age, "fresh_for_days": window,
                        "fresh": age <= window,
                        "kind": "external_signal"})
        return out


def radar(db, *, today: date | None = None) -> dict:
    """What is being watched, what has gone stale, and what nobody has looked at at all.

    A domain with no observations is named rather than counted as zero. Zero signal and no
    look are the same number and opposite situations: one says the world is quiet, the other
    says nobody checked, and only the second is a defect in this system.
    """
    rows = observations(db, today=today)
    by_domain: dict[str, list[dict]] = {d.key: [] for d in DOMAINS}
    for row in rows:
        by_domain[row["domain"]].append(row)

    watched, stale, unobserved = [], [], []
    for domain in DOMAINS:
        items = by_domain[domain.key]
        if not items:
            unobserved.append({"domain": domain.key, "what": domain.what,
                               "why_it_matters": domain.why})
            continue
        fresh = [i for i in items if i["fresh"]]
        entry = {"domain": domain.key, "what": domain.what,
                 "observations": len(items), "fresh": len(fresh),
                 "newest_age_days": min(i["age_days"] for i in items),
                 "fresh_for_days": domain.fresh_for_days, "why": domain.why}
        (watched if fresh else stale).append(entry)

    return {
        "watched": watched,
        "stale": stale,
        "unobserved": unobserved,
        "observations": len(rows),
        "note": (
            "no domain has been observed: this radar is a shape with nothing in it, which is "
            "worth saying plainly rather than reporting eight zeroes"
            if not rows else
            f"{len(watched)} domain(s) carry fresh observations, {len(stale)} have gone "
            f"stale, and {len(unobserved)} have never been looked at -- which is a different "
            f"thing from quiet"),
    }


def as_evidence(observation: dict) -> None:
    """The step that must not exist, present so that it refuses by name (#98).

    Somebody reads that textured stitches are trending; it goes in a brief as context; the
    next brief cites the first; six weeks later it is something the company knows and nobody
    can say who measured it. This is that step, and it raises.
    """
    raise LearningRefused(
        f"an external observation ({observation.get('source', 'unknown source')}) is a "
        f"signal, not causal evidence. It is that somebody said something, somewhere, on a "
        f"date -- not that this company measured it. Cite it as a signal, or measure the "
        f"thing here and record a lesson")


def support(claim: str, *, signals: list[dict], evidence: list[dict]) -> dict:
    """Assemble what a decision rests on, with the two kinds kept apart.

    A decision may rest on signals alone -- most early ones must -- and it says so. The point
    is not to forbid acting on what the world says; it is that a reader six weeks later can
    tell the difference between a thing this company measured and a thing it read.
    """
    if not claim.strip():
        raise LearningRefused("a claim with no text cannot be supported by anything")
    for item in evidence:
        if item.get("kind") == "external_signal":
            raise LearningRefused(
                "an external observation was passed as internal evidence. That is the "
                "single sentence in which a signal becomes something the company 'knows', "
                "and it is the reason these are two lists")

    return {
        "claim": claim,
        "signals": signals,
        "internal_evidence": evidence,
        "causal_basis": "internal_evidence" if evidence else "none",
        "rests_on_signals_alone": bool(signals) and not evidence,
        "note": ("this claim rests on external signals alone: it is a reasonable thing to "
                 "act on and not a thing this company has established"
                 if signals and not evidence else
                 "this claim has internal causal evidence behind it"
                 if evidence else
                 "this claim has neither signals nor evidence behind it"),
    }


# ---------------------------------------------------------------------------
# Feeding the radar from evidence this company actually has (#98)
#
# Eight domains, and until the benchmark credential existed nothing fetched any of them, so
# the radar honestly reported every one as unobserved. Four are now answerable from evidence
# already recorded -- and four are not, which is the part that matters. A feeder that filled
# all eight by inferring techniques from product titles would turn a truthful "nobody has
# looked" into a confident fiction, and the radar's whole value is that it distinguishes the
# two.
#
# What the benchmark scan genuinely supports:
#
#   competitor_positioning  -- how many listings, in which departments, at what prices
#   seasonal_behaviour      -- which occasions this market's catalogue is built around
#   aesthetics              -- the visual register its titles name, as term frequency
#   media_capability        -- how many images a listing in this market carries
#
# What it does not, and why nothing here pretends otherwise:
#
#   techniques      -- a title naming "mosaic" says a product exists, not that a technique
#                      is new or reviving. That needs a source about the craft, not a shop.
#   search_behaviour -- no observation of this platform's ranking exists at all.
#   marketplace_policy -- `ops.policy_watch` owns this; a second writer would let two
#                      freshness clocks disagree about the same policy.
#   customer_pain   -- there are no customers and no reviews read, and inferring complaints
#                      from a competitor's catalogue is inventing them.

BENCHMARK_SOURCE = "benchmark_scan"

FEEDABLE: tuple[str, ...] = (
    "competitor_positioning", "seasonal_behaviour", "aesthetics", "media_capability")

NOT_FEEDABLE: dict[str, str] = {
    "techniques": ("a title naming a stitch says a product exists, not that the technique "
                   "is new or reviving. That needs a source about the craft"),
    "search_behaviour": "nothing has observed this platform's ranking",
    "marketplace_policy": ("ops.policy_watch owns this domain; a second writer would let "
                           "two freshness clocks disagree about one policy"),
    # Corrected 2026-09-20. This said no review had been read, which was true when it was
    # written and is the reason the entry existed -- inferring complaints from a catalogue
    # *is* inventing them. Reading actual reviews is not inferring, it is observing, and the
    # distinction is the whole of the difference. `ingest_complaints` fills this domain from
    # a real read; it stays listed here for when no read has happened yet.
    "customer_pain": ("no review has been read yet. Inferring complaints from a "
                      "competitor's catalogue would be inventing them; reading their "
                      "reviews is observing them, and mjs.reviews does that"),
}


def ingest_benchmark(db, *, benchmark_key: str = "", today: date | None = None) -> dict:
    """Record what the observed benchmark catalogue genuinely says, in four domains.

    Idempotent per day and per domain: the citation carries the scan date, so running twice
    in a day updates nothing and running tomorrow adds tomorrow's reading. A radar that
    accumulated one row per invocation would report freshness as a function of how often the
    scheduler fired.
    """
    from sqlalchemy import select

    from ..core.models import BenchmarkListing, LearningObservation
    from . import benchmarks

    today = today or date.today()
    benchmark_key = benchmark_key or benchmarks.MJS_KEY
    with db.session() as s:
        rows = list(s.scalars(select(BenchmarkListing).where(
            BenchmarkListing.benchmark_key == benchmark_key)))

    if not rows:
        return {"recorded": [], "skipped": dict(NOT_FEEDABLE),
                "reason": "no benchmark listing has been observed, so there is nothing to "
                          "report about this market"}

    by_pod: dict[str, int] = {}
    by_season: dict[str, int] = {}
    media: list[int] = []
    for row in rows:
        by_pod[row.pod or "unclassified"] = by_pod.get(row.pod or "unclassified", 0) + 1
        if row.seasonal:
            by_season[row.seasonal] = by_season.get(row.seasonal, 0) + 1
        media.append(int(row.media_count or 0))

    thin = sum(1 for n in media if n < 5)
    citation = f"{benchmark_key}@{today.isoformat()}"
    readings = {
        "competitor_positioning": (
            f"{len(rows)} active listings across {len(by_pod)} departments; deepest is "
            f"{max(by_pod, key=by_pod.get)} at {max(by_pod.values())}",
            {"by_department": dict(sorted(by_pod.items(), key=lambda kv: -kv[1]))}),
        "seasonal_behaviour": (
            f"{len(by_season)} occasion(s) named in this catalogue's own listing data"
            if by_season else
            "no occasion is named in this catalogue's structured listing data, so what it "
            "sells seasonally is visible only in its titles",
            {"by_season": by_season}),
        "aesthetics": (
            f"the visual register this market names is readable from {len(rows)} titles; "
            f"per-department term frequency is in commerce.intent.arena_language",
            {"departments": sorted(by_pod)}),
        "media_capability": (
            f"{thin} of {len(rows)} listings carry fewer than five images",
            {"thin_galleries": thin, "listings": len(rows),
             "share": round(thin / len(rows), 3)}),
    }

    recorded: list[str] = []
    with db.session() as s:
        existing = {
            (r.domain, r.citation) for r in s.scalars(select(LearningObservation))}
    for domain in FEEDABLE:
        if (domain, citation) in existing:
            continue
        summary, detail = readings[domain]
        record(db, domain=domain, source=BENCHMARK_SOURCE, citation=citation,
               summary=summary, observed_on=today, detail=detail)
        recorded.append(domain)

    return {
        "recorded": recorded,
        "citation": citation,
        "listings": len(rows),
        "skipped": dict(NOT_FEEDABLE),
        "note": ("Four domains are answerable from a benchmark catalogue and four are not. "
                 "Filling all eight by inference would turn a truthful 'nobody has looked' "
                 "into a confident fiction, which is the one thing this radar exists to "
                 "prevent (#98)."),
    }


def ingest_complaints(db, *, themes: dict, today: date | None = None,
                      benchmark_key: str = "") -> dict:
    """Record recurring complaint themes as a `customer_pain` observation.

    The domain this system previously reported as unfeedable, and correctly: inferring
    complaints from a catalogue is inventing them. What changed is that reviews are now read,
    and a counted theme from a real review is an observation.

    Only *recurring* themes are recorded. A theme below the recurrence floor is one
    customer's bad day, and a radar carrying it would age it for 180 days as though it were a
    property of the category.
    """
    from sqlalchemy import select

    from ..core.models import LearningObservation
    from . import benchmarks

    today = today or date.today()
    benchmark_key = benchmark_key or benchmarks.MJS_KEY
    recurring = themes.get("recurring") or {}
    if not recurring:
        return {"recorded": [], "reason": (
            f"{themes.get('reviews_read', 0)} review(s) read and no theme reached the "
            f"recurrence floor of {themes.get('recurring_at')}. That is a reading, not a "
            f"silence: the domain stays unobserved rather than recording 'no complaints'")}

    citation = f"{benchmark_key}:reviews@{today.isoformat()}"
    with db.session() as s:
        seen = {(r.domain, r.citation) for r in s.scalars(select(LearningObservation))}
    if ("customer_pain", citation) in seen:
        return {"recorded": [], "reason": "already recorded for this reading"}

    top = ", ".join(f"{name} ({n})" for name, n in
                    sorted(recurring.items(), key=lambda kv: -kv[1])[:4])
    record(db, domain="customer_pain", source=BENCHMARK_SOURCE, citation=citation,
           summary=(f"{len(recurring)} complaint theme(s) recur across "
                    f"{themes.get('reviews_read', 0)} reviews in this category: {top}"),
           observed_on=today,
           detail={"recurring": recurring, "reviews_read": themes.get("reviews_read"),
                   "low_rated_share": themes.get("low_rated_share")})
    return {"recorded": ["customer_pain"], "citation": citation,
            "themes": sorted(recurring)}
