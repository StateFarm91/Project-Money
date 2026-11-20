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
        # F-070: what the benchmarks already bought have taught, beside what the next ones
        # would cost -- so the ceiling is argued with information value, not only price.
        "post_purchase_information_value": information_value(db),
    }


def information_value(db) -> dict:
    """F-070: per purchased benchmark, what it cost and what it has taught since.

    Information value is counted, never scored: findings recorded against the benchmark,
    findings promoted into improvement hypotheses, improvements those promotions created
    (`Improvement.rollback_ref == "teardown-finding:<id>"`) and how many of them were promoted
    or reverted, and floors adopted on our own requirements. A benchmark whose price was not
    recorded has an UNKNOWN cost (None), never CA$0, and no cost-per-finding ratio.
    """
    from sqlalchemy import select as _select

    from ..core.models import BenchmarkProduct, Improvement, TeardownFinding

    with db.session() as s:
        products = list(s.scalars(_select(BenchmarkProduct).order_by(BenchmarkProduct.id)))
        findings = list(s.scalars(_select(TeardownFinding)))
        refs = {f"teardown-finding:{f.id}" for f in findings}
        improvements = (list(s.scalars(_select(Improvement).where(
            Improvement.rollback_ref.in_(refs)))) if refs else [])
        rows_out = []
        by_ref: dict[str, list] = {}
        for f in findings:
            by_ref.setdefault(f.benchmark_ref, []).append(f)
        imp_by_ref = {i.rollback_ref: i for i in improvements}
        for p in products:
            mine = by_ref.get(p.ref, [])
            imps = [imp_by_ref[f"teardown-finding:{f.id}"] for f in mine
                    if f"teardown-finding:{f.id}" in imp_by_ref]
            paid = float(p.paid_cad) if p.paid_cad and p.paid_cad > 0 else None
            promoted = sum(1 for f in mine if f.promoted)
            floors = sum(1 for f in mine if (f.detail or {}).get("adopted"))
            improved = sum(1 for i in imps if i.state == "promoted")
            reverted = sum(1 for i in imps if i.reverted_at is not None)
            rows_out.append({
                "ref": p.ref, "title": p.title, "pod": p.pod,
                "purchased_on": p.purchased_on or None,
                "paid_cad": paid,
                "paid_basis": "recorded" if paid is not None else "UNKNOWN",
                "teardown_state": p.teardown_state,
                "findings": len(mine),
                "findings_promoted": promoted,
                "improvements_created": len(imps),
                "improvements_promoted": improved,
                "improvements_reverted": reverted,
                "floors_adopted": floors,
                "cad_per_finding": (round(paid / len(mine), 4)
                                    if paid is not None and mine else None),
                "cad_per_improvement_promoted": (round(paid / improved, 4)
                                                 if paid is not None and improved else None),
                "taught_nothing_yet": (not mine and p.teardown_state not in ("queued", "in_teardown")),
            })
    known = [r["paid_cad"] for r in rows_out if r["paid_cad"] is not None]
    total_findings = sum(r["findings"] for r in rows_out)
    total_promoted = sum(r["improvements_promoted"] for r in rows_out)
    return {
        "purchased": len(rows_out),
        "benchmarks": rows_out,
        "paid_cad_known": round(sum(known), 2) if known else None,
        "paid_unknown_for": [r["ref"] for r in rows_out if r["paid_cad"] is None],
        "findings": total_findings,
        "improvements_promoted": total_promoted,
        "cad_per_finding": (round(sum(known) / total_findings, 4)
                            if known and total_findings and len(known) == len(rows_out)
                            else None),
        "taught_nothing_yet": [r["ref"] for r in rows_out if r["taught_nothing_yet"]],
        "basis": ("counts from teardown_findings and improvements; a benchmark is valued by "
                  "what it changed, not by a score. A ratio is shown only where every price "
                  "is recorded"),
        "why_empty": ("" if rows_out else
                      "no benchmark has been purchased: purchasing is the owner's "
                      "consequential spend, so there is no information value to count yet"),
    }


# =========================================================================================
# ENG-BENCHBUY: the benchmark shopping list across every watchlist shop
# =========================================================================================
#
# The owner's ask (2026-11-20): benchmark patterns to buy, with variety from each of the nine
# shops scanned daily, where owner demand (MadelineMaeCo, baby products, stuffed
# animals/amigurumi, pillows) counts as a first-class reason to buy.
#
# `select` above is unchanged and still serves the MJs approved set (teardown.intake). What
# follows keeps its design -- greedy facet coverage, a computed reason for every pick, and the
# rule that no pick is made without a new facet -- and adds what a multi-shop list needs:
#
# * the catalogue is every watchlist shop's scanned listings, restricted to PATTERN DIGITAL
#   DOWNLOADS (Etsy `listing_type == "download"` and a pattern word in the title or tags);
# * a per-shop quota (3, MadelineMaeCo 5) so no shop is bought out and none is skipped;
# * two new facets, ranked ahead of everything else: the capability gap a purchase teaches
#   (global -- one in-the-round purchase teaches it for the company) and the owner-demand
#   family (per shop -- baby, stuffed animal / amigurumi, pillow / cushion);
# * the budget is enforced here, in code, against the remaining CA$ ceiling after recorded
#   BenchmarkProduct spend, with every price shown beside its x1.158 FX/tax contingency;
# * owned items (both MJ benchmarks, every BenchmarkProduct row) never appear as "to buy".
#
# **Metadata only.** This reads rows the daily scans already wrote (title, tags, price, type,
# favourites). It makes no request, opens no listing, copies no competitor content, and has no
# purchase path: it returns a list for the owner to act on. A purchased PDF goes only through
# the quarantined intake (teardown.intake -> teardown.library, B-117).
import re as _re

# Verified against the owner's ask: nine shops, three each, five for MadelineMaeCo.
PER_SHOP_QUOTA = 3
SHOP_QUOTAS: dict[str, int] = {"madeline_mae_co": 5}
# The owner's FX + tax contingency on every observed CAD price (D-OWNER-BENCHBUY).
CONTINGENCY = 1.158
SHOPPING_KIND = "benchmark.shopping"
OWNER_CARD_KEY = "benchmark_shopping:set"

# Items the owner already holds and must never be offered again (both MJ benchmarks). Matched
# on a normalised title inside MJ's own catalogue; BenchmarkProduct rows are matched by listing
# reference and by title in every shop.
OWNED_TITLE_MARKERS: tuple[str, ...] = ("mini star stitch cardigan", "cardigan with pockets")

# The capability gaps this company's compiler/twin is weakest at, in teaching priority order.
GAPS: tuple[tuple[str, str], ...] = (
    ("in_the_round", r"in[- ]the[- ]round|seamless|top[- ]down|magic ring|magic circle|"
                     r"beanie|bucket hat|basket|bowl|\bhat\b"),
    ("colourwork_chart", r"colou?rwork|jacquard|fair ?isle|intarsia|\bc2c\b|corner to corner|"
                         r"pixel|graphghan|\bchart"),
    ("mosaic_tapestry", r"mosaic|tapestry|overlay"),
    ("granny_motif", r"granny|motif|hexagon|joined square|sunburst|medallion|afghan square"),
    ("garment_grading", r"cardigan|sweater|pullover|\bvest\b|jumper|\btee\b|\btop\b|dress|"
                        r"shrug|poncho|\bsizes?\b"),
    ("amigurumi", r"amigurumi|plush|stuffed|plushie|stuffie"),
    ("flat", r"\bflat\b|rectangle|scarf|blanket|\bwrap\b|shawl|runner|placemat|coaster|"
             r"dishcloth|washcloth|rug|ripple|panel"),
)
GAP_POD_HINTS: dict[str, tuple[str, ...]] = {
    "hats": ("in_the_round",), "amigurumi": ("amigurumi", "in_the_round"),
    "garments": ("garment_grading",), "blankets": ("flat",), "kitchen_bath": ("flat",),
}
# What the owner reports as "huge hits": permanent core families (D-OWNER-CORE-FAMILIES).
OWNER_DEMAND: tuple[tuple[str, str], ...] = (
    ("baby", r"\bbaby\b|newborn|infant|toddler|nursery|lovey|rattle|\bbib\b|romper|bootie"),
    ("stuffed_animal", r"amigurumi|stuffed|plush|plushie|stuffie"),
    ("pillow_cushion", r"pillow|cushion|bolster|pouf|ottoman"),
)
DEMAND_POD_HINTS: dict[str, tuple[str, ...]] = {"amigurumi": ("stuffed_animal",)}
PATTERN_WORDS = _re.compile(r"pattern|\bpdf\b|tutorial|e-?book|\bchart", _re.I)
SHOPPING_FACETS: tuple[str, ...] = FACETS + ("capability_gap", "owner_demand")
_GLOBAL_FACETS = ("capability_gap",)
_PRIORITY_FACETS = ("capability_gap", "owner_demand")


def _norm(text: str) -> str:
    return _re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _text_of(row) -> str:
    detail = row.detail or {}
    tags = " ".join(str(t) for t in (detail.get("tags") or []))
    return f"{row.title or ''} {tags}".lower()


def digital_status(row) -> str:
    """`download`, `physical` or `unknown` from the API's own listing_type; never guessed."""
    kind = ((row.detail or {}).get("options") or {}).get("listing_type")
    if not kind:
        return "unknown"
    return "download" if str(kind).lower() == "download" else "physical"


def capability_gaps(row) -> tuple[str, ...]:
    text = _text_of(row)
    found = {g for g, rx in GAPS if _re.search(rx, text)}
    found.update(GAP_POD_HINTS.get(row.pod or "", ()))
    return tuple(g for g, _ in GAPS if g in found)


def owner_demand(row) -> tuple[str, ...]:
    text = _text_of(row)
    found = {d for d, rx in OWNER_DEMAND if _re.search(rx, text)}
    found.update(DEMAND_POD_HINTS.get(row.pod or "", ()))
    return tuple(d for d, _ in OWNER_DEMAND if d in found)


@dataclass(frozen=True)
class ShopCandidate:
    shop_key: str
    shop_name: str
    base: Candidate
    gaps: tuple
    demand: tuple
    bestseller: bool

    @property
    def listing_ref(self) -> str:
        return self.base.listing_ref

    @property
    def price_with_contingency(self) -> float:
        return round(self.base.price_cad * CONTINGENCY, 2)

    @property
    def facets(self) -> dict:
        return {**self.base.facets, "capability_gap": self.gaps, "owner_demand": self.demand}


def contingent(price_cad: float) -> float:
    return round(float(price_cad or 0.0) * CONTINGENCY, 2)


def recorded_spend(db) -> dict:
    """Spend recorded on BenchmarkProduct rows. A row with no recorded price is UNKNOWN, not 0."""
    from sqlalchemy import select

    from ..core.models import BenchmarkProduct

    with db.session() as s:
        rows = list(s.scalars(select(BenchmarkProduct)))
        known = [float(r.paid_cad) for r in rows if r.paid_cad and r.paid_cad > 0]
        return {"products": len(rows), "recorded_cad": round(sum(known), 2),
                "unknown_price_for": [r.ref for r in rows if not (r.paid_cad and r.paid_cad > 0)],
                "listing_refs": {str(r.listing_ref) for r in rows if r.listing_ref},
                "titles": {_norm(r.title) for r in rows if r.title},
                "by_listing": {str(r.listing_ref): {"files": len(r.files or []),
                                                    "state": r.teardown_state}
                               for r in rows if r.listing_ref}}


def _exclusion(row, owned: dict, shop_key: str) -> str | None:
    """Why a scanned listing cannot be a shopping-list pick, or None when it can."""
    if row.audit_state == "withdrawn":
        return "withdrawn"
    title = _norm(row.title)
    if shop_key == "mjs_off_the_hook_designs" and any(m in title for m in OWNED_TITLE_MARKERS):
        return "owned"
    if str(row.listing_ref) in owned["listing_refs"] or (title and title in owned["titles"]):
        return "owned"
    status = digital_status(row)
    if status == "physical":
        return "not_digital_download"
    if status == "unknown":
        return "digital_status_unknown"
    if not PATTERN_WORDS.search(_text_of(row)):
        return "not_a_pattern"
    if not (row.price_cad and row.price_cad > 0):
        return "price_unknown"
    return None


EXCLUSION_TEXT = {
    "withdrawn": "withdrawn from sale", "owned": "already owned",
    "not_digital_download": "not a digital download", "not_a_pattern": "not a pattern listing",
    "digital_status_unknown": "digital-download status not observed (UNKNOWN)",
    "price_unknown": "price not observed (UNKNOWN)",
}


def _shop_state(db, member) -> dict:
    from . import watchlist

    try:
        st = watchlist._state(db, member.key) if member.role != watchlist.ANCHOR else {}
    except Exception:  # noqa: BLE001 - a missing memory table is "unknown", never a crash
        st = {}
    return {"state": st.get("state") or "unknown",
            "last_error": (st.get("last_error") or "")[:160] or None}


def shopping_list(db, *, ledger: list[dict] | None = None, budget_ceiling_cad: float | None = None,
                  members=None) -> dict:
    """The benchmark shopping list: variety across every watchlist shop, owner demand first.

    `ledger` is the previous list's picks that have since been bought: they stay on the list
    with their status and still count toward each shop's quota and the facet coverage, but
    their price is not charged again (their spend is already a recorded BenchmarkProduct).
    """
    from sqlalchemy import select

    from ..core.models import BenchmarkListing
    from ..teardown import intake
    from . import watchlist

    members = tuple(members or watchlist.WATCHLIST)
    ceiling = float(intake.SET_BUDGET_CAD if budget_ceiling_cad is None else budget_ceiling_cad)
    owned = recorded_spend(db)
    remaining = round(ceiling - owned["recorded_cad"], 2)

    with db.session() as s:
        rows = list(s.scalars(select(BenchmarkListing)))
    by_shop: dict[str, list] = {m.key: [] for m in members}
    for r in rows:
        if r.benchmark_key in by_shop:
            by_shop[r.benchmark_key].append(r)

    pool: list[ShopCandidate] = []
    shops: dict[str, dict] = {}
    for m in members:
        listings = by_shop[m.key]
        reasons: dict[str, int] = {}
        eligible = 0
        for r in listings:
            why = _exclusion(r, owned, m.key)
            if why:
                reasons[why] = reasons.get(why, 0) + 1
                continue
            eligible += 1
            detail = r.detail or {}
            pool.append(ShopCandidate(
                shop_key=m.key, shop_name=m.shop_name, base=describe(r),
                gaps=capability_gaps(r), demand=owner_demand(r),
                bestseller=bool(detail.get("is_bestseller"))))
        shops[m.key] = {"shop_key": m.key, "shop_name": m.shop_name, "role": m.role,
                        "scan": _shop_state(db, m), "observed": len(listings),
                        "eligible": eligible, "excluded": reasons,
                        "quota": SHOP_QUOTAS.get(m.key, PER_SHOP_QUOTA), "picks": []}

    # -- carried picks: bought already, still on the list, still count --------------------
    covered: dict[tuple[str, str], set] = {}
    picks_by_shop: dict[str, list[dict]] = {m.key: [] for m in members}

    def cover(shop_key: str, facets: dict) -> None:
        for facet, value in facets.items():
            scope = "*" if facet in _GLOBAL_FACETS else shop_key
            vals = value if isinstance(value, tuple) else (value,)
            covered.setdefault((scope, facet), set()).update(v for v in vals if v != "unknown")

    carried = 0
    for old in ledger or []:
        key = old.get("shop_key")
        ref = str(old.get("listing_ref"))
        if key not in picks_by_shop or ref not in owned["by_listing"]:
            continue
        info = owned["by_listing"][ref]
        status = "intake done" if info["files"] else "bought"
        keep = {**old, "status": status}
        keep.pop("chosen_over", None)
        picks_by_shop[key].append(keep)
        cover(key, {k: (tuple(v) if isinstance(v, list) else v)
                    for k, v in (old.get("facets") or {}).items()})
        carried += 1

    def new_for(c: ShopCandidate) -> dict:
        out = {}
        for facet, value in c.facets.items():
            scope = "*" if facet in _GLOBAL_FACETS else c.shop_key
            have = covered.get((scope, facet), set())
            if isinstance(value, tuple):
                fresh = tuple(v for v in value if v not in have)
                if fresh:
                    out[facet] = fresh
            elif value != "unknown" and value not in have:
                out[facet] = value
        return out

    # -- the greedy loop ------------------------------------------------------------------
    chosen: list[dict] = []
    spent = 0.0                       # contingent CAD of picks still to buy
    budget = max(remaining, 0.0)
    remaining_pool = list(pool)
    ended = {"cause": "nothing_left_to_learn", "excluded": None}
    skipped_for_budget = 0

    def open_slots(c: ShopCandidate) -> bool:
        return len(picks_by_shop[c.shop_key]) < SHOP_QUOTAS.get(c.shop_key, PER_SHOP_QUOTA)

    while True:
        live = [c for c in remaining_pool if open_slots(c)]
        scored = []
        for c in live:
            new = new_for(c)
            if not new:
                continue          # the rule that survives: no pick without a new facet
            generic = sum(1 for f in new if f not in _PRIORITY_FACETS)
            scored.append((
                -len(new.get("capability_gap", ())),
                -len(new.get("owner_demand", ())),
                len(picks_by_shop[c.shop_key]),   # the shop with the fewest picks so far first
                -generic, -richness(c.base),
                # favourites / bestseller: a tie-break only, last before the stable order
                -int(c.bestseller), -c.base.favourites,
                c.shop_key, c.listing_ref, c, new))
        if not scored:
            break
        scored.sort(key=lambda t: t[:9])
        # Variety survives a tight budget: money is held back for the cheapest first pick of
        # every shop that has none yet, so a gap/demand-first ranking cannot spend the whole
        # ceiling before the last shops are reached. Only when even that cannot be honoured
        # does the plain budget check apply, so the ceiling is never left idle.
        cheapest_first: dict[str, float] = {}
        for t in scored:
            c = t[-2]
            if not picks_by_shop[c.shop_key]:
                cheapest_first[c.shop_key] = min(
                    cheapest_first.get(c.shop_key, c.price_with_contingency),
                    c.price_with_contingency)

        def reserve_for(c: ShopCandidate) -> float:
            return round(sum(v for k, v in cheapest_first.items() if k != c.shop_key), 2)

        affordable = [t for t in scored
                      if spent + t[-2].price_with_contingency + reserve_for(t[-2]) <= budget]
        if not affordable:
            affordable = [t for t in scored
                          if spent + t[-2].price_with_contingency <= budget]
        if not affordable:
            top = scored[0][-2]
            ended = {"cause": "budget_exhausted", "excluded": {
                "listing_ref": top.listing_ref, "title": top.base.title,
                "shop": top.shop_name, "price_cad": round(top.base.price_cad, 2),
                "price_with_contingency_cad": top.price_with_contingency,
                "shortfall_cad": round(spent + top.price_with_contingency - budget, 2)}}
            break
        if affordable[0] is not scored[0]:
            skipped_for_budget += 1
        best_t = affordable[0]
        best, new = best_t[-2], best_t[-1]
        runner = next((t for t in scored if t[-2] is not best), None)
        cover(best.shop_key, new)
        spent = round(spent + best.price_with_contingency, 2)
        pick = {
            **best.base.to_dict(),
            "shop_key": best.shop_key, "shop_name": best.shop_name,
            "price_with_contingency_cad": best.price_with_contingency,
            "contingency_factor": CONTINGENCY,
            "status": "to buy",
            "teaches": _teaches(new),
            "owner_demand": list(best.demand),
            "capability_gaps": list(best.gaps),
            "answers": _reason_shopping(new, best),
            "new_facets": {k: (list(v) if isinstance(v, tuple) else v) for k, v in new.items()},
            "facets": {k: (list(v) if isinstance(v, tuple) else v)
                       for k, v in best.facets.items()},
            "chosen_over": _chosen_over(best, runner, new_for),
        }
        picks_by_shop[best.shop_key].append(pick)
        chosen.append(pick)
        remaining_pool = [c for c in remaining_pool if c is not best]

    # -- per-shop verdicts: an empty shop is visible, with its reason -----------------------
    for m in members:
        info = shops[m.key]
        info["picks"] = picks_by_shop[m.key]
        n_to_buy = sum(1 for p in info["picks"] if p["status"] == "to buy")
        if info["picks"]:
            info["status"], info["reason"] = "PICKED", (
                f"{len(info['picks'])} of {info['quota']} slots used")
        elif info["observed"] == 0:
            info["status"] = "UNKNOWN"
            info["reason"] = (f"no scanned listings are in the database for {m.shop_name} "
                              f"(scan state: {info['scan']['state']}"
                              f"{', ' + info['scan']['last_error'] if info['scan']['last_error'] else ''}"
                              f"). Nothing is assumed about its catalogue")
        elif info["eligible"] == 0:
            top = sorted(info["excluded"].items(), key=lambda kv: -kv[1])
            info["status"] = "EMPTY"
            info["reason"] = (f"{info['observed']} listings scanned, none eligible: " +
                              "; ".join(f"{n} {EXCLUSION_TEXT.get(k, k)}" for k, n in top))
        elif ended["cause"] == "budget_exhausted":
            info["status"] = "EMPTY"
            info["reason"] = (f"{info['eligible']} eligible listings, none chosen before the "
                              f"CA${budget:.2f} remaining benchmark budget was reached")
        else:
            info["status"] = "EMPTY"
            info["reason"] = (f"{info['eligible']} eligible listings, but each would teach "
                              f"nothing this list does not already teach")
        info["to_buy"] = n_to_buy
        info["slots_left"] = max(info["quota"] - len(info["picks"]), 0)

    to_buy = [p for p in chosen]
    total_plain = round(sum(p["price_cad"] for p in to_buy), 2)
    total_cont = round(sum(p["price_with_contingency_cad"] for p in to_buy), 2)
    observed_total = sum(s["observed"] for s in shops.values())
    if observed_total == 0:
        status, why = "UNKNOWN", ("no watchlist shop has scanned listings in the database, so "
                                  "there is no catalogue to choose from; nothing is guessed")
    else:
        status, why = "OK", ""
    return {
        "status": status, "reason": why,
        "shops": [shops[m.key] for m in members],
        "shops_with_picks": sum(1 for s in shops.values() if s["picks"]),
        "shops_total": len(shops),
        "to_buy": to_buy, "to_buy_count": len(to_buy),
        "carried": carried,
        "total_cad": total_plain, "total_with_contingency_cad": total_cont,
        "contingency_factor": CONTINGENCY,
        "budget": {"ceiling_cad": ceiling, "recorded_spend_cad": owned["recorded_cad"],
                   "remaining_cad": remaining,
                   "unknown_price_for": owned["unknown_price_for"],
                   "within_budget": total_cont <= max(remaining, 0.0),
                   "basis": ("the SET_BUDGET_CAD ceiling less recorded BenchmarkProduct spend; "
                             "every price is checked at x1.158 for FX and tax. A product with "
                             "no recorded price is listed as UNKNOWN, never counted as CA$0")},
        "stopped_because": ended["cause"], "budget_excluded": ended["excluded"],
        "budget_skips": skipped_for_budget,
        "quota": {"default": PER_SHOP_QUOTA, **SHOP_QUOTAS},
        "method": ("greedy facet coverage across all watchlist shops: capability gap first, "
                   "owner demand second, then every other facet; favourites only break ties"),
        "not_a_purchase": ("this is a list and a cost. Nothing is bought automatically; buying "
                           "is the owner's. A purchased PDF goes only through the quarantined "
                           "teardown intake"),
    }


def _teaches(new: dict) -> str:
    parts = []
    if new.get("capability_gap"):
        parts.append("capability: " + ", ".join(g.replace("_", " ") for g in new["capability_gap"]))
    if new.get("owner_demand"):
        parts.append("owner-demand family: " + ", ".join(
            d.replace("_", " ") for d in new["owner_demand"]))
    rest = [f for f in new if f not in _PRIORITY_FACETS]
    if rest and not parts:
        parts.append("market lesson: " + ", ".join(f.replace("_", " ") for f in rest[:3]))
    return "; ".join(parts) or "nothing new"


def _reason_shopping(new: dict, c: ShopCandidate) -> str:
    plain = {k: v for k, v in new.items() if k not in _PRIORITY_FACETS}
    bits = []
    if new.get("capability_gap"):
        bits.append("closes a capability gap not yet covered: " + ", ".join(
            g.replace("_", " ") for g in new["capability_gap"]))
    if new.get("owner_demand"):
        bits.append("owner-demand family for this shop: " + ", ".join(
            d.replace("_", " ") for d in new["owner_demand"]))
    if plain:
        bits.append(_reason(plain, c.base))
    return "; ".join(bits) or "nothing new"


def _chosen_over(best: ShopCandidate, runner, new_for) -> dict | None:
    if runner is None:
        return None
    other = runner[-2]
    would = {k: (list(v) if isinstance(v, tuple) else v) for k, v in runner[-1].items()}
    return {"listing_ref": other.listing_ref, "title": other.base.title,
            "shop": other.shop_name, "would_have_added": would,
            "why": ("ranked behind on capability gap, owner demand and facet coverage; "
                    "favourites were consulted only as a last tie-break")}


# -- the persisted daily reading, the owner card and the Mission Control read model -----------

def previous_ledger(db) -> list[dict]:
    from sqlalchemy import desc, select

    from ..core.models import OperatingReading

    with db.session() as s:
        row = s.scalar(select(OperatingReading).where(OperatingReading.kind == SHOPPING_KIND)
                       .order_by(desc(OperatingReading.period_key)).limit(1))
        payload = dict(row.payload or {}) if row is not None else {}
    out: list[dict] = []
    for shop in payload.get("shops") or []:
        out.extend(p for p in shop.get("picks") or [])
    return out
