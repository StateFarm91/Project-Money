"""Which ten benchmarks to buy, chosen for what each one answers rather than for quality.

Requirements 165, 166, 317. The owner will buy roughly ten MJs patterns so this company can
study what a customer actually receives after paying. The selection is the part that decides
whether that money buys knowledge or ten copies of the same lesson, and #166 says it outright:
*prefer benchmarks that answer a distinct unknown rather than buying many similar products.*

**The obvious selection is the wrong one.** Sorting by favourites and taking the top ten buys
the ten most popular listings, which in one shop's catalogue will share a department, a price
band and a deliverable format -- so nine of them answer a question the first one already
answered. Popularity is a fact about the listing and this purchase is about the *set*.

**So the objective is coverage, and it is computed rather than argued.** Each candidate is
described by the facets a teardown could differ along -- department, price band, gallery
depth, whether the deliverable's terms are stated, sizing presentation, whether it is a
bundle, whether it is seasonal -- and each pick is the listing that adds the most facet
values nothing already chosen covers. Greedy rather than optimal on purpose: the optimum over
438 listings is a subset-selection problem whose answer nobody could check, and a selection
somebody cannot check is a selection nobody will trust with real money.

**Every pick names its unknown.** #166 asks for the research question beside the cost, so the
reason is generated from the facets the pick actually added and never from a template. A pick
that adds nothing new is not made at all: the run stops short of ten rather than filling the
list, because ten was always an approximation and "we bought three that taught us nothing" is
the failure mode being avoided.

**Nothing here buys anything.** It produces a list, its reasons and its cost, for a person to
act on. Purchasing is consequential spend and stays the owner's.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# The facets a purchased teardown can differ along. Each is something a *customer experience*
# audit (#317) could find different between two products: how it is organised, how it is
# priced, how much it shows, what it promises, how it is sized.
FACETS: tuple[str, ...] = (
    "department", "price_band", "gallery_depth", "deliverable_stated",
    "sizing", "bundle", "seasonal",
)

# Price bands in CAD. Coarse on purpose -- the question a band answers is "what does a buyer
# at this level receive", and finer bands would split one answer across several purchases.
PRICE_BANDS: tuple[tuple[str, float, float | None], ...] = (
    ("under_6", 0.0, 6.0),
    ("6_to_10", 6.0, 10.0),
    ("10_to_20", 10.0, 20.0),
    ("over_20", 20.0, None),
)

# Gallery depth bands. #2's weakness hunt found 413 of 438 listings carry fewer than five
# images, so "rich" is genuinely rare here and worth a purchase of its own.
THIN_GALLERY_AT_OR_BELOW = 4
RICH_GALLERY_AT_OR_ABOVE = 8

TARGET_PURCHASES = 10

# Below this a pick is not worth its price: it duplicates a lesson already bought. Stated as
# a threshold rather than as "stop when bored", so a short list is a finding.
MIN_NEW_FACETS = 1


class SelectionRefused(ValueError):
    """A selection that would be made from nothing, or reported as more than it is."""


@dataclass(frozen=True)
class Candidate:
    listing_ref: str
    title: str
    pod: str
    price_cad: float
    media_count: int
    seasonal: str
    url: str
    facets: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"listing_ref": self.listing_ref, "title": self.title, "pod": self.pod,
                "price_cad": round(self.price_cad, 2), "media_count": self.media_count,
                "url": self.url, "facets": dict(self.facets)}


def price_band(price_cad: float) -> str:
    for key, low, high in PRICE_BANDS:
        if price_cad >= low and (high is None or price_cad < high):
            return key
    return "unpriced"


def gallery_depth(media_count: int) -> str:
    if media_count <= 0:
        return "unknown"
    if media_count <= THIN_GALLERY_AT_OR_BELOW:
        return "thin"
    if media_count >= RICH_GALLERY_AT_OR_ABOVE:
        return "rich"
    return "moderate"


def describe(row) -> Candidate:
    """One observed listing as the facets a teardown could differ along.

    Facts only, and absence is `unknown` rather than a default. A listing whose deliverable
    terms nobody has read is not a listing with unstated terms, and buying on that confusion
    is buying to answer a question that was never asked.
    """
    detail = row.detail or {}
    deliverable = detail.get("deliverable") or {}
    sizing = detail.get("size_range") or {}

    stated = deliverable.get("format") if isinstance(deliverable, dict) else None
    facets = {
        "department": row.pod or "unclassified",
        "price_band": price_band(float(row.price_cad or 0.0)),
        "gallery_depth": gallery_depth(int(row.media_count or 0)),
        "deliverable_stated": ("unknown" if not deliverable
                               else "stated" if stated else "unstated"),
        "sizing": ("unknown" if not sizing
                   else str(sizing.get("kind") or sizing.get("range") or "stated")),
        "bundle": "bundle" if row.pod == "collections" else "single",
        "seasonal": row.seasonal or "evergreen",
    }
    return Candidate(
        listing_ref=row.listing_ref, title=row.title or "", pod=row.pod or "unclassified",
        price_cad=float(row.price_cad or 0.0), media_count=int(row.media_count or 0),
        seasonal=row.seasonal or "", url=row.url or "", facets=facets)


def candidates(db, benchmark_key: str, *, departments: list[str] | None = None,
               ) -> list[Candidate]:
    """Every observed listing this company could learn a customer experience from."""
    from sqlalchemy import select

    from ..core.models import BenchmarkListing

    with db.session() as s:
        rows = list(s.scalars(select(BenchmarkListing).where(
            BenchmarkListing.benchmark_key == benchmark_key)))

    wanted = set(departments or [])
    out = [describe(r) for r in rows]
    if wanted:
        out = [c for c in out if c.pod in wanted]
    # Stable order so the same catalogue produces the same selection twice. A selection that
    # moves between runs cannot be reviewed, and this one is reviewed by a person spending
    # money.
    return sorted(out, key=lambda c: (c.pod, -c.media_count, c.price_cad, c.listing_ref))


def _new_values(candidate: Candidate, covered: dict) -> dict:
    return {facet: value for facet, value in candidate.facets.items()
            if value != "unknown" and value not in covered.get(facet, set())}


def _reason(new: dict, candidate: Candidate) -> str:
    """The research question this purchase answers, from what it actually added."""
    parts = []
    for facet, value in new.items():
        readable = value.replace("_", " ")
        parts.append({
            "department": f"the first {readable} bought",
            "price_band": f"what a buyer at {readable} CAD receives",
            "gallery_depth": f"a {readable} gallery, against a catalogue where most are thin",
            "deliverable_stated": f"a listing whose deliverable terms are {readable}",
            "sizing": f"sizing presented as {readable}",
            "bundle": f"a {readable} rather than what is already selected",
            "seasonal": f"a {readable} product's merchandising",
        }.get(facet, f"{facet}: {readable}"))
    return "; ".join(parts) or "nothing new"


def select(db, benchmark_key: str, *, departments: list[str] | None = None,
           target: int = TARGET_PURCHASES) -> dict:
    """Choose the set, name what each one answers, and total what it costs.

    Stops early when no remaining listing adds a facet nothing covers. Ten was always an
    approximation of "enough", and a tenth purchase that answers a question already answered
    is money spent to make a list the right length.
    """
    pool = candidates(db, benchmark_key, departments=departments)
    if not pool:
        raise SelectionRefused(
            f"nothing has been observed for {benchmark_key!r}, so there is no catalogue to "
            f"choose from. A selection made from no observation is a list of guesses with a "
            f"price on it")

    covered: dict[str, set] = {facet: set() for facet in FACETS}
    chosen: list[dict] = []
    remaining = list(pool)

    while remaining and len(chosen) < target:
        scored = [(len(_new_values(c, covered)), c) for c in remaining]
        scored.sort(key=lambda pair: (-pair[0], pair[1].pod, pair[1].listing_ref))
        gain, best = scored[0]
        if gain < MIN_NEW_FACETS:
            break
        new = _new_values(best, covered)
        for facet, value in new.items():
            covered[facet].add(value)
        chosen.append({**best.to_dict(), "answers": _reason(new, best),
                       "new_facets": new})
        remaining = [c for c in remaining if c.listing_ref != best.listing_ref]

    total = round(sum(c["price_cad"] for c in chosen), 2)
    uncovered = {facet: sorted({c.facets[facet] for c in pool
                                if c.facets[facet] != "unknown"} - covered[facet])
                 for facet in FACETS}
    still_open = {k: v for k, v in uncovered.items() if v}

    return {
        "benchmark": benchmark_key,
        "observed": len(pool),
        "target": target,
        "selected": chosen,
        "selected_count": len(chosen),
        "total_cad": total,
        "currency_note": ("prices are the observed Etsy figures in CAD at observation time. "
                          "Taxes, and any sale price on the day of purchase, are not "
                          "included -- this is an expected cost, not a quote"),
        "stopped_early": len(chosen) < target,
        # Computed rather than asserted. The first version of this said "the target was
        # reached with facets still uncovered, listed below" whether or not any were, which
        # is a sentence that describes the list beside it without reading it.
        "why_stopped": ("no remaining listing adds a facet nothing selected already covers, "
                        "so a further purchase would buy a lesson already bought"
                        if len(chosen) < target else
                        f"the target of {target} was reached with {len(still_open)} facets "
                        f"still uncovered, listed below"
                        if still_open else
                        f"the target of {target} was reached and every facet the observed "
                        f"catalogue varies along is covered"),
        "facets_still_uncovered": still_open,
        "method": ("greedy coverage over the facets a customer-experience teardown can "
                   "differ along, not popularity. Sorting by favourites buys the ten most "
                   "popular listings, which in one shop share a department, a price band and "
                   "a format -- nine of them answering a question the first already answered"),
        "what_happens_after": ("files land in the quarantined benchmark library, which "
                               "refuses every reader that is not an analyst and stores no "
                               "competitor text in any table (teardown/library.py)"),
        "not_a_purchase": ("this is a list and a cost. Buying is consequential spend and is "
                           "the owner's"),
    }
