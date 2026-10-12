"""Creativity benchmark memory (#86): commercial attributes, learned and stored with outcomes.

The requirement asks the company to study legitimate current market examples across
categories and learn *abstract commercial attributes* -- clever transformation, strong
silhouette, recognisable motif, cute characterisation, premium minimalism, gift narrative,
modularity, low-sew appeal, surprising function and collection logic -- storing attributes and
outcomes, never copied protected expression.

The attributes are judged from photographs. `intel.vision` asks them of every benchmark
gallery image under `COMMERCIAL_ATTRIBUTE_FIELDS`, with a system prompt that forbids naming
what the product depicts, and stores each answer as a `gallery_image_observation`. Until
2026-09-27 nothing read those fields back: the vocabulary existed and the memory did not. This
module is the memory. Daily it folds every judged listing's attributes together with the one
market outcome the sanctioned API returns (favourites, a demand proxy: a saved listing is not a
sale) and with Brambleloop's own outcomes (orders, UNMEASURED until a customer exists), stores
the reading as an `OperatingReading`, and `creative.ideation` reads it into every tournament
and expedition brief as the attributes the market is currently rewarding.

Two honesty rules. With no judged image the reading is UNMEASURED and says why -- the judging
runs behind `image_vision`, and a memory that filled itself from titles would be learning the
wrong thing from the wrong evidence. And a lift computed from fewer than
`MIN_LISTINGS_FOR_LIFT` listings is not a lift: one popular listing showing one attribute is an
anecdote about that listing.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

KIND = "creative.benchmark_memory"
ACTION = "creative.benchmark_memory"
OBSERVATION_KIND = "gallery_image_observation"
UNMEASURED = "UNMEASURED"

# A demand lift is a comparison of means, and a mean of one is a number wearing a costume.
MIN_LISTINGS_FOR_LIFT = 2
# How many distinct judgement phrases an attribute keeps. They are short readings of how an
# offer is built to sell ("reads as one gift in the first frame"), never what it depicts.
MAX_PHRASES = 6
DEMAND_BASIS = "favourites are a demand proxy: a saved listing is not a sale"


def _favourites(listing) -> int | None:
    value = ((listing.detail or {}) if listing is not None else {}).get("num_favorers")
    return int(value) if isinstance(value, (int, float)) and value >= 0 else None


def _mean(values: list[int]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


def build(db, *, today: date | None = None) -> dict:
    """Fold every judged listing's commercial attributes and outcomes into today's reading."""
    from sqlalchemy import func, select

    from ..core.models import (
        BenchmarkListing, BenchmarkObservation, LedgerEntry, OperatingReading,
    )
    from ..intel.vision import COMMERCIAL_ATTRIBUTE_FIELDS

    today = today or datetime.now(timezone.utc).date()
    with db.session() as s:
        listings = {(r.benchmark_key, r.listing_ref): r
                    for r in s.scalars(select(BenchmarkListing))}
        observations = list(s.scalars(select(BenchmarkObservation).where(
            BenchmarkObservation.kind == OBSERVATION_KIND)))
        orders = s.scalar(select(func.count()).select_from(LedgerEntry).where(
            LedgerEntry.gross_cad > 0, LedgerEntry.evidence_ref != "")) or 0

        # Per judged listing: which attributes any of its images showed, in the judge's words.
        judged: dict[tuple[str, str], dict[str, list[str]]] = {}
        for o in observations:
            observation = (o.detail or {}).get("observation") or {}
            entry = judged.setdefault((o.benchmark_key, o.listing_ref), {})
            for field in COMMERCIAL_ATTRIBUTE_FIELDS:
                phrase = str(observation.get(field) or "").strip()[:120]
                if phrase and phrase not in entry.setdefault(field, []):
                    entry[field].append(phrase)

        favourites = {key: _favourites(listings.get(key)) for key in judged}
        pods = {key: ((listings.get(key).pod or "unclassified") if listings.get(key) else
                      "unclassified") for key in judged}

        attributes: dict[str, dict] = {}
        for field in COMMERCIAL_ATTRIBUTE_FIELDS:
            shown = [key for key, attrs in judged.items() if attrs.get(field)]
            if not shown:
                continue
            with_f = [favourites[k] for k in shown if favourites[k] is not None]
            without_f = [favourites[k] for k in judged if k not in shown
                         and favourites[k] is not None]
            mean_with, mean_without = _mean(with_f), _mean(without_f)
            if (len(shown) >= MIN_LISTINGS_FOR_LIFT and mean_with is not None
                    and mean_without):
                lift: float | str = round(mean_with / mean_without, 3)
            else:
                lift = UNMEASURED
            phrases: list[str] = []
            for k in shown:
                for p in judged[k][field]:
                    if p not in phrases and len(phrases) < MAX_PHRASES:
                        phrases.append(p)
            attributes[field] = {
                "listings": len(shown),
                "pods": sorted({pods[k] for k in shown}),
                "phrases": phrases,
                "favourites_mean": mean_with,
                "favourites_mean_without": mean_without,
                "demand_lift": lift,
                "basis": DEMAND_BASIS,
            }

        measured = bool(attributes)
        payload = {
            "as_of": today.isoformat(),
            "requirement": 86,
            "measured": measured,
            "state": "measured" if measured else UNMEASURED,
            "judged_listings": len(judged),
            "with_favourites": sum(1 for v in favourites.values() if v is not None),
            "attributes": attributes,
            "outcomes": {
                "market": {"reading": "favourites per judged listing", "basis": DEMAND_BASIS},
                "brambleloop": {
                    "orders": orders if orders else UNMEASURED,
                    "reading": "measured" if orders else UNMEASURED,
                    "why": ("our own attribute-to-outcome link needs orders for our products; "
                            "none exist yet, so this half is UNMEASURED rather than inferred"
                            if not orders else
                            f"{orders} order rows exist; attribution to attributes follows "
                            f"through creative.outcome_learning"),
                },
            },
            "stores": ("attributes as judgements about how an offer is built to sell, in a "
                       "closed vocabulary; never the depicted design, motif or text"),
        }
        if not measured:
            payload["reason"] = (
                "no judged gallery observation carries a commercial attribute yet. The "
                "attributes are judged from photographs by intel.gallery_analysis, which runs "
                "behind image_vision; a memory filled from titles would be learning the wrong "
                "thing from the wrong evidence")

        row = s.scalar(select(OperatingReading).where(
            OperatingReading.kind == KIND, OperatingReading.period_key == today.isoformat()))
        if row is None:
            s.add(OperatingReading(kind=KIND, period_key=today.isoformat(), payload=payload))
        else:
            row.payload = payload
    return payload


def latest(db) -> dict | None:
    """The newest stored reading, or None when the memory has never run."""
    from sqlalchemy import desc, select

    from ..core.models import OperatingReading

    with db.session() as s:
        row = s.scalar(select(OperatingReading).where(OperatingReading.kind == KIND)
                       .order_by(desc(OperatingReading.period_key)).limit(1))
        return dict(row.payload or {}) if row is not None else None


def rewarded(db, *, pod: str | None = None, limit: int = 5) -> list[dict]:
    """The attributes the market is currently rewarding, for a brief; empty when unmeasured.

    Read from the stored reading rather than recomputed, so a brief and the reading it drew on
    can be put side by side. An attribute counts when its lift is measured and above one; the
    `pod` is annotated rather than used as a filter, because the requirement asks for study
    *across* categories and a gift narrative learned from ornaments is a gift narrative.
    """
    reading = latest(db)
    if not reading or not reading.get("measured"):
        return []
    out = []
    for name, a in (reading.get("attributes") or {}).items():
        lift = a.get("demand_lift")
        if isinstance(lift, (int, float)) and lift > 1.0:
            out.append({"attribute": name, "demand_lift": lift, "listings": a["listings"],
                        "phrases": list(a.get("phrases") or [])[:3],
                        "seen_in_pod": bool(pod) and pod in (a.get("pods") or []),
                        "as_of": reading.get("as_of")})
    out.sort(key=lambda x: (-x["demand_lift"], -x["listings"], x["attribute"]))
    return out[:limit]
