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
    "sizing", "bundle", "seasonal", "has_video",
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
    favourites: int = 0

    def to_dict(self) -> dict:
        return {"listing_ref": self.listing_ref, "title": self.title, "pod": self.pod,
                "price_cad": round(self.price_cad, 2), "media_count": self.media_count,
                "favourites": self.favourites,
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
        # A real difference in what a customer receives, and therefore a real difference in
        # what a teardown can study: whether the listing ships a video alongside the PDF.
        # Added 2026-09-20 after the first full run decided eleven of thirteen picks on a
        # tie-break rather than on information -- once a department was claimed, every other
        # listing in it was worth exactly the same to the objective, which is the objective
        # admitting it had run out of things to distinguish.
        "has_video": ("video" if detail.get("has_video") else
                      "no_video" if "has_video" in detail else "unknown"),
    }
    return Candidate(
        listing_ref=row.listing_ref, title=row.title or "", pod=row.pod or "unclassified",
        price_cad=float(row.price_cad or 0.0), media_count=int(row.media_count or 0),
        seasonal=row.seasonal or "", url=row.url or "", facets=facets,
        favourites=int(detail.get("num_favorers") or 0))


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


def richness(candidate: Candidate) -> int:
    """How much a teardown of this listing could observe, for breaking a tie.

    Coverage decides which listing to buy; this decides *which of the equally covering ones*.
    Without it the tie-break was listing reference, which is deterministic and meaningless:
    the first full run settled eleven of thirteen picks that way, so within a department the
    choice was arbitrary and the reason given was "it sorted first".

    A deeper gallery, a video, stated deliverable terms and stated sizing are each more of
    the customer experience visible on the page -- which is the thing #317 buys these
    products to study. Counted rather than weighted: the differences are not commensurable
    and pretending they are would be a second arbitrary choice wearing arithmetic.
    """
    facets = candidate.facets
    score = 0
    score += {"rich": 2, "moderate": 1}.get(facets.get("gallery_depth"), 0)
    score += 1 if facets.get("has_video") == "video" else 0
    score += 1 if facets.get("deliverable_stated") == "stated" else 0
    score += 1 if facets.get("sizing") not in (None, "unknown") else 0
    return score


def _instead_of(best: Candidate, new: dict, runner_up: Candidate | None,
                covered: dict, redundant: int, pool_size: int) -> dict:
    """The comparison behind one pick, in the words a reviewer would ask for.

    Three parts, because three different questions get asked of a purchase list: what else
    was close, what that alternative would have taught instead, and how much of the
    catalogue was passed over for teaching nothing new. The last is the one that answers
    "are we buying thirteen similar things", and it is a count rather than an assurance.
    """
    if runner_up is None:
        return {"runner_up": None, "richness": richness(best),
                "why": (f"nothing else remained. {redundant} of {pool_size} candidates "
                        f"would have added no facet nothing already covers"),
                "redundant_candidates": redundant, "pool_considered": pool_size}

    alternative = _new_values(runner_up, covered)
    extra = sorted(set(new) - set(alternative))
    same = sorted(set(new) & set(alternative))
    return {
        "runner_up": {"listing_ref": runner_up.listing_ref, "title": runner_up.title,
                      "pod": runner_up.pod, "price_cad": round(runner_up.price_cad, 2),
                      "would_have_added": alternative,
                      "richness": richness(runner_up)},
        "richness": richness(best),
        "why": (
            f"both would have answered {', '.join(same) or 'nothing in common'}; this one "
            f"also answers {', '.join(extra)}"
            if extra else
            f"level on coverage at {len(new)} new facets, and this listing shows more of the "
            f"customer experience on the page: {richness(best)} against "
            f"{richness(runner_up)} on gallery depth, video, stated terms and stated sizing"
            if richness(best) != richness(runner_up) else
            f"level on coverage at {len(new)} new facets and level on observable depth; "
            f"this listing carries {best.favourites} favourites against "
            f"{runner_up.favourites}, so the department's slot went to the exemplar its own "
            f"market rewarded most"
            if best.favourites != runner_up.favourites else
            f"level on coverage at {len(new)} new facets, on observable depth and on "
            f"favourites, so a stable ordering decided it and the same catalogue produces "
            f"the same list twice"),
        "redundant_candidates": redundant,
        "pool_considered": pool_size,
        "redundancy_note": (
            f"{redundant} of the {pool_size} listings still in the pool would have added "
            f"nothing new at this point. They are not cheaper versions of this pick -- they "
            f"are the same lesson, and buying one is the failure #166 names"),
    }


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
            "has_video": (f"a listing that ships {readable.replace('_', ' ')}, which changes "
                          f"what the customer receives"),
        }.get(facet, f"{facet}: {readable}"))
    return "; ".join(parts) or "nothing new"


def select(db, benchmark_key: str, *, departments: list[str] | None = None,
           target: int = TARGET_PURCHASES, budget_cad: float | None = None) -> dict:
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
    # Why the loop ended, recorded where it ends rather than inferred afterwards from the
    # length of the list. The first version inferred it, and on the live catalogue it was
    # wrong in the direction that costs money: at a CA$300 ceiling the set stopped one pick
    # short of covering the `education` department, and the report said "no remaining
    # listing adds a facet nothing selected already covers" -- an information verdict for
    # what was a budget truncation. A reader deciding whether to raise the ceiling was told
    # there was nothing left to buy.
    ended: dict = {"cause": "target_reached", "excluded": None}

    while remaining and len(chosen) < target:
        scored = [(len(_new_values(c, covered)), c) for c in remaining]
        # Coverage, then observable depth, then how strongly the market rewarded it, then a
        # stable reference so the same catalogue produces the same list twice.
        #
        # The third term is *not* the popularity sort this module exists to refuse, and the
        # distinction is worth stating because it looks like one. Popularity as the set
        # objective buys ten similar things. Popularity as a tie-break inside a department
        # this set has already decided to cover changes nothing about diversity -- it picks
        # the most instructive exemplar of a slot already chosen on other grounds, and the
        # department's strongest seller is the customer experience most worth studying.
        #
        # It was added after a live run in which observable depth discriminated once in
        # thirteen: nearly every listing in this catalogue carries ten images, which is
        # Etsy's gallery cap, so `gallery_depth` is "rich" almost everywhere and a richness
        # tie-break is nearly constant on the real data. A mechanism that cannot separate the
        # cases it was written for is not a mechanism.
        scored.sort(key=lambda pair: (-pair[0], -richness(pair[1]), -pair[1].favourites,
                                      pair[1].pod, pair[1].listing_ref))
        gain, best = scored[0]
        if gain < MIN_NEW_FACETS:
            ended["cause"] = "nothing_left_to_learn"
            break
        # An approved budget is a ceiling in code, like every other ceiling here, rather
        # than a number somebody remembers at the till. When the best exemplar of a slot
        # would take the set past it, the affordable one is taken *and the swap is
        # recorded* -- because "we bought the cheaper one" is a decision the owner is
        # entitled to see, not a detail. What the ceiling cost is reported at the end.
        forgone = None
        new_if_bought = _new_values(best, covered)
        if budget_cad is not None:
            spent_so_far = sum(c["price_cad"] for c in chosen)
            if spent_so_far + best.price_cad > budget_cad:
                affordable = [(g, c) for g, c in scored
                              if g == gain and spent_so_far + c.price_cad <= budget_cad]
                if not affordable:
                    # Out of money, not out of information. The distinction is the whole
                    # point of reporting a reason: one of these is answered by raising the
                    # ceiling and the other is not.
                    ended.update(cause="budget_exhausted", excluded={
                        "listing_ref": best.listing_ref, "title": best.title,
                        "pod": best.pod, "price_cad": round(best.price_cad, 2),
                        "would_have_added": new_if_bought,
                        "shortfall_cad": round(
                            spent_so_far + best.price_cad - budget_cad, 2)})
                    break
                forgone = {"listing_ref": best.listing_ref, "title": best.title,
                           "price_cad": round(best.price_cad, 2),
                           "favourites": best.favourites,
                           "why_not": (f"CA${best.price_cad:.2f} would have taken the set "
                                       f"past the approved CA${budget_cad:.2f}")}
                gain, best = affordable[0]

        new = _new_values(best, covered)

        # Why this one and not another. A coverage score is a number, and a person about to
        # spend money on thirteen products is entitled to the comparison behind each: what
        # the closest alternative was, what it would have taught instead, and how many
        # listings were passed over because they would have taught nothing new.
        runner_up = next((c for _, c in scored[1:]
                          if c.listing_ref != best.listing_ref), None)
        redundant = sum(1 for g, _ in scored if g == 0)
        instead_of = _instead_of(best, new, runner_up, covered, redundant, len(scored))

        for facet, value in new.items():
            covered[facet].add(value)
        chosen.append({**best.to_dict(), "answers": _reason(new, best),
                       "new_facets": new, "chosen_over": instead_of,
                       **({"budget_forced": forgone} if forgone else {})})
        remaining = [c for c in remaining if c.listing_ref != best.listing_ref]

    # The count the owner's question actually asks for. The per-pick number is about the
    # moment that pick was made; "are we buying thirteen similar things" is about the
    # finished set, and the answer is how much of the catalogue the set makes redundant.
    covered_at_end = sum(1 for c in remaining if not _new_values(c, covered))

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
        "stopped_because": ended["cause"],
        "budget_excluded": ended["excluded"],
        # Computed rather than asserted. The first version of this said "the target was
        # reached with facets still uncovered, listed below" whether or not any were, which
        # is a sentence that describes the list beside it without reading it.
        "why_stopped": (
                        f"the approved CA${budget_cad:.2f} was reached with "
                        f"{len(still_open)} facets still uncovered. The next pick was "
                        f"{ended['excluded']['title'][:60]!r} at "
                        f"CA${ended['excluded']['price_cad']:.2f}, CA$"
                        f"{ended['excluded']['shortfall_cad']:.2f} past the ceiling, and it "
                        f"was the only thing left that would have taught "
                        f"{', '.join(f'{k}={v}' for k, v in ended['excluded']['would_have_added'].items())}"
                        if ended["cause"] == "budget_exhausted" and ended["excluded"] else
                        "no remaining listing adds a facet nothing selected already covers, "
                        "so a further purchase would buy a lesson already bought"
                        if len(chosen) < target else
                        f"the target of {target} was reached with {len(still_open)} facets "
                        f"still uncovered, listed below"
                        if still_open else
                        f"the target of {target} was reached and every facet the observed "
                        f"catalogue varies along is covered"),
        "facets_still_uncovered": still_open,
        "budget_cad": budget_cad,
        "within_budget": budget_cad is None or total <= budget_cad,
        "budget_forced_swaps": [
            {"instead_of": c["budget_forced"], "took": c["listing_ref"],
             "took_price_cad": c["price_cad"],
             "extra_it_would_have_cost": round(
                 c["budget_forced"]["price_cad"] - c["price_cad"], 2)}
            for c in chosen if c.get("budget_forced")],
        "listings_this_set_makes_redundant": covered_at_end,
        "share_of_catalogue_made_redundant": (
            round(covered_at_end / len(pool), 4) if pool else 0.0),
        "redundancy_meaning": (
            f"{covered_at_end} of the {len(pool)} observed listings would now teach nothing "
            f"this set does not already teach. That is the answer to 'are we buying similar "
            f"things': a high number means the set covers the catalogue, and a low one means "
            f"the catalogue varies in ways the set has not reached"),
        "each_pick_carries": ("the distinct unknown it answers, the runner-up it beat, what "
                             "that alternative would have taught instead, and how many "
                             "listings were passed over for teaching nothing new"),
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
