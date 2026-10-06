"""Launch readiness: what actually stands between this shop and a live customer.

Master Plan sections 14, 26 and 36. Shadow mode is a phase, and the point of a phase is that
something ends it. This module answers the question that ends it, from the database and the
code rather than from anyone's recollection: for every requirement a live shop has, is it
met, and if not, who can meet it?

Three kinds of blocker, and the distinction is the whole value here:

- **build** -- something this system can do and has not done yet. Never an owner action. If a
  requirement is blocked on build, the answer is to build it, not to send the owner a message.
- **integration** -- something that needs an account, a key or a service that does not exist.
- **owner** -- something a person must do because it legally or physically cannot be
  automated: identity verification, banking, accepting terms, holding a hook.

Only the third kind reaches the owner queue, and each one arrives in the format the owner's
Execution Directive requires: the exact action, why it is required, the maximum cost, the
minutes it takes, and what waiting costs. The queue table has had those columns since the
first build and nothing has written to them, because until now nothing was blocked on the
owner: asking earlier would have been asking for things "because they will eventually be
needed", which the directive forbids.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

BLOCKED_BUILD = "build"
BLOCKED_INTEGRATION = "integration"
BLOCKED_OWNER = "owner"
# F-071 / F-086: blocked on an independent tester or contract crocheter -- the tester roster,
# which is outreach and never the owner. Physical validation is delegated; the owner is not
# the tester, so a requirement waiting on a sample is not waiting on the owner.
BLOCKED_TESTER = "tester"

# A shop with three listings reads as abandoned to a browsing buyer, and section 33's
# portfolio arithmetic assumes a spread. This is the floor for opening, not a target.
MIN_LISTINGS_TO_OPEN = 8

# Frames per listing. The plan is seven; the seventh is a collection cross-sell that only
# exists for products with siblings, so the floor is six.
MIN_APPROVED_ASSETS = 6


@dataclass(frozen=True)
class OwnerRequest:
    """One owner-only action, in the format the Execution Directive requires.

    `key` is the request's identity and it is what the owner queue de-duplicates on. The
    queue used to compare the action *text*, which worked only while every action was a
    frozen string: the moment one of them started deriving its figure from the catalogue,
    a changed number read as a new request and the owner got two entries for one decision.
    An action's wording is a rendering of the request; the requirement it belongs to is the
    request.
    """

    key: str
    action: str
    reason: str
    max_cost_cad: float
    minutes: int
    consequence_of_delay: str
    blocks: str


@dataclass(frozen=True)
class Requirement:
    key: str
    description: str
    ready: bool
    blocked_by: str | None = None
    evidence: dict = field(default_factory=dict)
    owner_request: OwnerRequest | None = None


@dataclass
class Readiness:
    requirements: list[Requirement] = field(default_factory=list)
    # F-175: what the report does not know, named. Empty is not the goal -- an empty register
    # without evidence is a register nobody filled in -- so it is reported as it is.
    unknowns: list[dict] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return all(r.ready for r in self.requirements)

    @property
    def outstanding(self) -> list[Requirement]:
        return [r for r in self.requirements if not r.ready]

    def blocked_on(self, who: str) -> list[Requirement]:
        return [r for r in self.outstanding if r.blocked_by == who]

    @property
    def buildable(self) -> list[Requirement]:
        """What this system can still do for itself. The honest to-do list."""
        return self.blocked_on(BLOCKED_BUILD)

    def owner_requests(self) -> list[OwnerRequest]:
        return [r.owner_request for r in self.outstanding if r.owner_request is not None]

    def to_dict(self) -> dict:
        return {
            "ready": self.ready,
            "requirements": [
                {"key": r.key, "description": r.description, "ready": r.ready,
                 "blocked_by": r.blocked_by, "evidence": r.evidence}
                for r in self.requirements
            ],
            "owner_actions": [
                {"action": o.action, "reason": o.reason, "max_cost_cad": o.max_cost_cad,
                 "minutes": o.minutes, "consequence_of_delay": o.consequence_of_delay,
                 "blocks": o.blocks}
                for o in self.owner_requests()
            ],
            "unknowns": list(self.unknowns),
        }


# ---- the owner-only actions, written once, in one place --------------------
#
# Each of these is blocked on a person because it cannot be otherwise: a platform's identity
# check exists precisely so that software cannot pass it on someone's behalf, and no amount of
# engineering makes a physical crochet sample appear.

ETSY_ACCOUNT = OwnerRequest(
    key="etsy_shop",
    action=("Open the Etsy shop for Brambleloop Studio and complete Etsy's identity "
            "verification (name, address, government ID as Etsy requests it), then add the "
            "shop name, currency CAD and Canada as the shop location."),
    reason=("Nothing can be published without a shop. Etsy's identity check is a legal "
            "requirement on the seller and must be completed by the person who is the "
            "seller -- automating it is both against Etsy's terms and against this "
            "system's own non-negotiables."),
    max_cost_cad=0.0,
    minutes=25,
    consequence_of_delay=("Every finished product stays in draft. The catalogue, imagery, "
                          "pricing and launch calendar are all complete and idle."),
    blocks="publishing anything at all",
)

ETSY_PAYOUT = OwnerRequest(
    key="payout",
    action=("Add the payout bank account and tax details to the Etsy shop (Canadian "
            "chequing account; GST/HST number if you have one, otherwise the small-supplier "
            "declaration)."),
    reason=("Etsy will not open a shop to buyers without a payout method, and revenue that "
            "cannot be paid out is not revenue. Banking credentials must be entered by the "
            "account holder."),
    max_cost_cad=0.0,
    minutes=15,
    consequence_of_delay="Listings cannot go live even once the shop exists.",
    blocks="publishing, and any revenue at all",
)

# Etsy's listing fee, and the CAD figure the estimate is built from. Read from
# `commerce.fee_schedule` (the dated fee reading in `gates.policy_knowledge`); `0.28` used to
# be typed here, hand-converted from a rate written down somewhere else. Names kept as
# aliases because other modules import them.
from ..commerce import fee_schedule as _FS  # noqa: E402
from ..finance.currency import ASSUMED_USD_PER_CAD as _USD_PER_CAD  # noqa: E402

LISTING_FEE_USD = _FS.LISTING.amount
LISTING_FEE_CAD = _FS.listing_fee_cad(_USD_PER_CAD)
LISTING_PERIOD_MONTHS = _FS.LISTING_RENEWAL_MONTHS


def listing_fees_request(listings: int) -> OwnerRequest:
    """The fee approval, costed from the catalogue that actually exists.

    This used to be a module constant whose text said "about US$1.80 (CA$2.50) for nine
    listings" -- true when it was written, and still being shown to the owner after the
    catalogue reached sixteen, next to an evidence field that computed CA$4.48 from the real
    count. An owner action asking for approval of a number is the last place a stale number
    belongs: the approval is for a figure, so the figure has to be the one they would
    actually be charged.
    """
    usd = listings * LISTING_FEE_USD
    cad = listings * LISTING_FEE_CAD
    # The ceiling is the figure plus headroom for a few more listings before launch, rounded
    # up to the dollar, so approving it does not have to be re-asked for every new product.
    ceiling = float(max(5, int(cad) + 2))
    return OwnerRequest(
        key="listing_fees",
        action=(f"Confirm you accept Etsy's listing fees for the opening catalogue: "
                f"US${LISTING_FEE_USD:.2f} per listing for {LISTING_PERIOD_MONTHS} months, so "
                f"about US${usd:.2f} (about CA${cad:.2f}) for the {listings} listings "
                f"currently drafted, plus {_FS.TRANSACTION.rate:.1%} transaction fee and "
                f"payment processing on each sale (fee reading of {_FS.READ_ON})."),
        reason=("This is the first spend that leaves the account, and the directive is "
                "explicit that no consequential spend happens without approval. It is "
                "small, but it is not zero and it is not reversible."),
        max_cost_cad=ceiling,
        minutes=2,
        consequence_of_delay="Publishing stays blocked on a two-minute decision.",
        blocks="publishing",
    )

PHYSICAL_SAMPLE = OwnerRequest(
    key="physical_calibration",
    action=("Crochet one sample -- the 20 cm storage basket is the best candidate, about "
            "6-8 hours -- weigh the yarn used, and measure the finished piece across and "
            "tall. Report: grams per colour, finished measurements, hook used, and anything "
            "the written instructions got wrong."),
    reason=("Yardage is an uncalibrated estimate carrying an explicit plus or minus 20%, and "
            "nothing but a real sample replaces that. It also calibrates every future "
            "estimate at that gauge, and it is the gate Class C products cannot pass at all. "
            "This cannot be automated: it requires hands, yarn and a hook."),
    max_cost_cad=25.0,
    minutes=420,
    consequence_of_delay=("Yardage stays a tolerance rather than a figure, Class C products "
                          "stay unshippable, and the first buyer becomes the tester."),
    blocks="calibrated yardage claims and any fitted garment",
)

# The owner parked this on 2026-09-20 and again on 2026-09-21: "remain parked -- do not
# require me personally to crochet a sample". So the requirement stays unmet and stays
# blocking, and the *request* is withdrawn from the queue, which are different things. A
# queue that keeps asking for the one thing its reader has twice said no to is a queue that
# teaches its reader to stop opening it, and the standing instruction is explicit: do not ask
# for an action already answered.
#
# `PHYSICAL_SAMPLE` is kept rather than deleted because the park is a decision that can be
# reversed, and the wording it would be reversed to should not have to be rewritten from
# memory on the day somebody changes their mind.
PHYSICAL_SAMPLE_PARKED = {
    "parked_by": "owner",
    "on": "2026-09-20",
    "restated": "2026-09-21",
    "decision": ("the owner will not be the one who crochets the calibration sample. The "
                 "requirement is unchanged and still blocks calibrated yardage and every "
                 "fitted garment; what is withdrawn is the ask"),
    "the_other_way_through": ("a pattern tester who has agreed to make one. That is the "
                              "`tester_roster` gate, and it is outreach rather than an owner "
                              "action"),
}


def _model_state(db) -> dict:
    """What the model provider's situation is, without importing it at module load."""
    from ..gateway.anthropic import last_probe

    probe = last_probe(db) or {}
    return {"usable": bool(probe.get("ok")),
            "last_probe_at": probe.get("at"),
            "last_probe_reason": (probe.get("reason") or "")[:200],
            "probed": bool(probe)}

MODEL_CREDITS = OwnerRequest(
    key="model_credits",
    action=("Add credit to the Anthropic account the API key belongs to. The console's "
            "smallest top-up is enough to start; the build's own ceiling is CA$100 a month "
            "and is enforced in code, so a larger balance cannot be spent faster than that."),
    reason=("The key you supplied authenticates. The first request it made returned, "
            "verbatim, 'Your credit balance is too low to access the Anthropic API', so the "
            "account cannot serve a request. Nothing in the build treats the provider as "
            "available until a real call succeeds, which means four requirements stay parked "
            "and no model work starts -- correctly, but they are parked on this."),
    max_cost_cad=25.0,
    minutes=3,
    consequence_of_delay=("The creativity capability scorecard's blinded comparison (#94), "
                          "the creative north star's desirability judgement (#104) and the "
                          "two model-routing requirements (#177, #178) stay parked. The rest "
                          "of Build 2 continues unaffected."),
    blocks="every requirement that needs a model to make a judgement",
)

BENCHMARK_PURCHASES = OwnerRequest(
    key="benchmark_challenge",
    action=("Buy the selected MJs benchmark patterns -- the current set and its cost are at "
            "/api/benchmark-selection, chosen for coverage of the facets a customer-"
            "experience teardown can differ along rather than by popularity -- then open "
            "/ops/teardown on a phone, tap each pick and choose the downloaded files. Zips "
            "go in as they downloaded. Nothing needs renaming, sorting or describing."),
    reason=("#168 blocks a live launch until a representative Brambleloop product has been "
            "compared, dimension by dimension, against the best category-matched product a "
            "customer could buy instead. Without a purchased benchmark that comparison cannot "
            "be made, and an unrun challenge is not a pass -- it is the one check that would "
            "catch us shipping something a buyer would rate below what they already own."),
    # The owner approved CA$300 on 2026-09-20 and the selector spends CA$292 of it within
    # that ceiling. The figure was CA$120 and an estimate; it is now the cost of a named set.
    max_cost_cad=300.0,
    minutes=30,
    consequence_of_delay=("The pre-launch challenge stays unrunnable, so the first honest "
                          "comparison against a paid competitor happens in a buyer's "
                          "downloads folder."),
    blocks="the pre-launch benchmark challenge, and therefore live publishing",
)

TRADEMARK_SCREEN = OwnerRequest(
    key="brand_clearance",
    action=("Decide whether to run a trademark clearance search on \"Brambleloop Studio\" "
            "before launch, and whether to file. A knock-out search on the Canadian "
            "register is free; a filing is CA$458.05 for the first class."),
    reason=("The shop name goes on every listing, PDF and image. Discovering a conflict "
            "after the name is on a hundred customer documents is expensive in a way that "
            "checking first is not. Filing is a spend decision, so it is the owner's."),
    max_cost_cad=460.0,
    minutes=20,
    consequence_of_delay=("Brand equity accumulates on a name that has not been cleared. "
                          "Low risk at zero sales, rising with every sale."),
    blocks="nothing yet; rises with volume",
)

OBJECT_STORAGE = OwnerRequest(
    key="artifact_storage",
    action=("Approve object storage for generated PDFs and images (Railway volume or an S3-"
            "compatible bucket), about CA$1-5 per month, within the existing CA$20 ceiling."),
    reason=("Artifact bytes are written to a container filesystem and do not survive a "
            "restart. The hashes are durable, so nothing is silently lost and everything "
            "re-renders from the certified CIR -- but a buyer's download link cannot point "
            "at a file that is regenerated on demand from a process that may be cold."),
    max_cost_cad=5.0,
    minutes=10,
    consequence_of_delay=("Every asset has to be re-rendered after a deploy. Harmless in "
                          "shadow mode; a broken download for a paying customer once live."),
    blocks="reliable delivery of purchased files",
)

GRADUATION = OwnerRequest(
    key="phase",
    action=("After the checks above, record the move to staging (then limited "
            "production) via POST /api/owner/phase/transition with readiness and rollback "
            "evidence refs -- the ids of a recent launch.assessed row and a recent "
            "launch.rollback_rehearsed row (both passing from limited production up) -- "
            "and set BRAMBLELOOP_PHASE to the same value, one step at a time "
            "(F-299: either one alone runs as the more restrictive phase)."),
    reason=("Shadow mode is enforced in code and refuses to publish, message customers or "
            "spend on advertising. Only the owner moves the phase, which is the point: the "
            "system cannot promote itself."),
    max_cost_cad=0.0,
    minutes=5,
    consequence_of_delay="Everything stays drafted and nothing reaches a customer.",
    blocks="the entire commercial phase",
)


# ---- the assessment --------------------------------------------------------


def _build(key: str, description: str, ready: bool, evidence: dict) -> Requirement:
    """A requirement this system can satisfy itself. Unready always means blocked on build.

    Setting `ready` and `blocked_by` independently let them disagree -- an early version
    reported a requirement as not ready and blocked on nothing, which reads as though it
    were nobody's job.
    """
    return Requirement(key=key, description=description, ready=ready,
                       blocked_by=None if ready else BLOCKED_BUILD, evidence=evidence)


# D-FB-7: the parity dimensions this company cannot answer by its own work today, and the
# capability each waits on. HERO needs a vision model to describe the hero (`image_vision`,
# held in shadow by the owner's provider decision); COMPETITIVE needs a blind review over
# observed benchmark galleries, which needs the same vision path and observed benchmark data.
_EXTERNAL_PARITY = {
    "hero": ("image_vision",),
    "competitive_blind_review": ("image_vision", "benchmark_observation"),
}


def _listing_photography(db, photo: dict) -> Requirement:
    """Truthful customer-ready listing imagery for every certified product-first pattern.

    A product counts when it has a photograph that cleared its floors or, under D-FB-7, a
    disclosed deterministic render set that verifies against its CIR and passed every
    listing-image QA gate (`owned_photography.coverage` counts both). Once every product has
    one, the listing's parity verdict is read: what still blocks it is reported against who
    can clear it -- company work stays `build`; HERO and COMPETITIVE, which wait on a vision
    model and observed benchmark data this company does not yet hold, are `integration`
    while their gates are closed, never folded into company work and never assumed passed.
    """
    description = ("every certified product-first pattern has truthful customer-ready listing "
                   "imagery that cleared its floors (a photograph, or a verified disclosed "
                   "render set under D-FB-7)")
    evidence = {
        "listable": photo["listable"], "certified": photo["certified"],
        "with_disclosed_render": photo.get("with_disclosed_render", [])[:10],
        "with_no_asset_at_all": photo["with_no_asset_at_all"][:5],
        "with_only_unusable_assets": photo["with_only_unusable_assets"][:5],
        "method_blocked_on": photo.get("method_blocked_on") or [],
        "why_this_is_separate_from_listing_imagery": (
            "that requirement counts approved rows in the asset table, which include "
            "charts and schematics. This one counts customer images that passed the gates, "
            "which is what a buyer sees")}
    if not photo["complete"]:
        return _build("listing_photography", description, False, evidence)

    from ..creative import blind_review
    from ..publish import listing_asset
    from ..visual import parity
    from ..visual.gallery import gates_now

    gates = gates_now(db, keys=("image_vision", "benchmark_observation"))
    company: dict[str, list[str]] = {}
    external: dict[str, dict[str, list[str]]] = {}
    for slug in photo["with_usable_asset"]:
        review = blind_review.current_review(db, slug=slug)
        verdict = parity.assess(listing_asset.frames_for(db, slug=slug),
                                benchmark_quality=review)
        for dim in verdict["failed"]:
            company.setdefault(slug, []).append(f"{dim}: failed")
        for dim in verdict["unjudged"]:
            closed = [g for g in _EXTERNAL_PARITY.get(dim, ()) if not gates.get(g)]
            if closed:
                external.setdefault(slug, {})[dim] = closed
            else:
                company.setdefault(slug, []).append(f"{dim}: unjudged")
    evidence["parity_company_work"] = company
    evidence["parity_waiting_on_gates"] = external
    evidence["gates"] = gates
    if company:
        return _build("listing_photography", description, False, evidence)
    if external:
        evidence["note"] = (
            "every product's listing set is built and passes the gates this company can run; "
            "parity still waits on " + ", ".join(sorted({d for v in external.values()
                                                         for d in v})) +
            ", each behind a closed gate (" + ", ".join(sorted({g for v in external.values()
                                                                for gs in v.values()
                                                                for g in gs})) +
            "). Unjudged is not a pass, so the listing stays blocked")
        return Requirement(key="listing_photography", description=description, ready=False,
                           blocked_by=BLOCKED_INTEGRATION, evidence=evidence)
    return _build("listing_photography", description, True, evidence)


def _count(session, model) -> int:
    from sqlalchemy import func, select

    return session.scalar(select(func.count()).select_from(model)) or 0


def assess(db, *, phase: str, providers: Iterable[str] = (),
           storage_durable: bool = False) -> Readiness:
    """Every requirement a live shop has, checked against the warehouse as it stands.

    Deliberately reads state rather than re-deriving it: a readiness report that recomputes
    the catalogue would tell you the code works, which is what the test suite is for. This
    one tells you what the running company has actually produced.
    """
    from sqlalchemy import select

    from ..brand.storefront import build_storefront, check_storefront
    from ..core.models import (
        ContentPiece, Incident, Listing, ListingAsset, PatternVersion, PhysicalTest, Product,
        SpendLimit,
    )

    out: list[Requirement] = []

    with db.session() as s:
        certified = list(s.scalars(
            select(PatternVersion).where(PatternVersion.certified == True)))  # noqa: E712
        listings = list(s.scalars(select(Listing).where(Listing.state != "withdrawn")))
        assets = list(s.scalars(select(ListingAsset)))
        content = _count(s, ContentPiece)
        open_incidents = list(s.scalars(
            select(Incident).where(Incident.resolved == False)))  # noqa: E712
        paused = [l.scope for l in s.scalars(select(SpendLimit)) if l.paused]
        physical_done = list(s.scalars(
            select(PhysicalTest).where(PhysicalTest.passed == True)))  # noqa: E712
        # `PatternVersion` keys by `product_id`, so the slugs are joined here rather than
        # read off the version rows -- which is what the first draft of `listing_photography`
        # tried, and it raised rather than misreporting, which is the better failure.
        certified_ids = {p.id for p in s.scalars(select(Product))
                         if p.id in {c.product_id for c in certified}}
        certified_slugs = sorted(p.slug for p in s.scalars(select(Product))
                                 if p.id in certified_ids)

    # -- what the company has built for itself ------------------------------
    #
    # F-119 / F-120: old certification is not current readiness. Only a certified version in
    # launch scope (Launch-0), or a legacy one re-certified under the current gauge standard,
    # counts toward the catalogue; every other legacy certification counts zero and is
    # reported beside the count rather than inside it. The same rule the publish path refuses
    # on (`publish.eligibility.legacy_status`), so the readiness report cannot count a
    # product the publish gate would refuse.
    #
    # J-product P-2: the floor counts PRODUCTS, not sizes. A basket sold in three sizes is one
    # product (three CIR slugs, one Launch-0 candidate); the Master defines no rule that makes
    # a size a separate product, so sizes collapse onto their product here exactly as
    # `store_foundation.readiness` counts them.
    counted, legacy_uncleared = _launch_scope_counts(db, certified)
    listed_in_scope = [l for l in listings if l.product_slug in counted["slugs"]]
    listed_products = sorted({product_of_slug(l.product_slug) for l in listed_in_scope})
    certified_products = sorted(counted["products"])
    out.append(_build(
        "catalogue_depth",
        f"at least {MIN_LISTINGS_TO_OPEN} certified launch-scope products with listings "
        f"(sizes are not counted as separate products)",
        len(listed_products) >= MIN_LISTINGS_TO_OPEN
        and len(certified_products) >= MIN_LISTINGS_TO_OPEN,
        {"products_counted": len(certified_products),
         "products": certified_products,
         "products_with_listings": listed_products,
         "counting_rule": ("distinct products: every size/variant CIR slug maps to its "
                           "Launch-0 candidate (products.launch0.candidate_for_cir); the "
                           "Master defines no rule that counts sizes as separate products"),
         "certified_patterns": counted["versions"],
         "certified_in_launch_scope": counted["in_launch_scope"],
         "certified_legacy_recertified": counted["legacy_recertified"],
         "listings": len(listings), "listings_in_scope": len(listed_in_scope),
         "legacy_counted_zero": {"versions": len(legacy_uncleared),
                                 "slugs": sorted({x["slug"] for x in legacy_uncleared})[:20],
                                 "why": ("pre-calibration Build-1 certifications count zero "
                                         "until re-certified under the current gauge "
                                         "standard (F-119)")},
         "certified_all_including_legacy": len(certified)}))

    by_listing: dict[str, list] = {}
    for a in assets:
        by_listing.setdefault(a.product_slug, []).append(a)
    thin = sorted(l.product_slug for l in listings
                  if len([a for a in by_listing.get(l.product_slug, []) if a.approved])
                  < MIN_APPROVED_ASSETS)
    out.append(_build(
        "listing_imagery",
        f"every listing carries at least {MIN_APPROVED_ASSETS} approved frames",
        not thin and bool(listings),
        {"listings_short_of_frames": thin[:5],
         "approved_frames": sum(1 for a in assets if a.approved)}))

    blocked_assets = sorted({a.product_slug for a in assets if a.blocked_reasons})
    out.append(_build(
        "imagery_truthful", "no listing asset is blocked by Asset Truth",
        # `bool(assets)` is the whole fix. "No asset is blocked" is vacuously true when
        # there are no assets, so this passed on an empty set -- a floor nothing can fail,
        # sitting on the launch gate. Every other requirement here already guards its own
        # emptiness with `and bool(listings)`; this one did not.
        not blocked_assets and bool(assets),
        {"blocked": blocked_assets[:5], "assets_on_file": len(assets)}))

    # Whether the catalogue has photographs a buyer would actually see.
    #
    # `listing_imagery` above counts rows in the `ListingAsset` table, which is where
    # charts, schematics and earlier approvals live. The rendered product photographs are
    # audit records written by `assets.owned_photography`, and this requirement was the
    # only part of launch readiness that could see them -- because it did not exist.
    #
    # Live, 2026-09-23: `listing_imagery` and `imagery_truthful` both reported READY while
    # `/api/asset-coverage` reported `listable: 0 of 10`. Two subsystems flatly disagreeing
    # about whether this company has listing imagery, and the optimistic one was the one
    # gating launch. That is the value-living-in-two-places defect on the most consequential
    # gate in the system: a shop could have been declared imagery-ready with not one product
    # photograph that passed its floors.
    #
    # It reads `owned_photography.coverage` rather than recomputing, so the launch gate and
    # the coverage endpoint cannot drift apart again by construction.
    from ..publish import owned_photography
    from ..products.builder import for_slug
    from ..visual.render_verification import authoritative_cir

    photo_slugs, photo_versions = [], {}
    for slug in certified_slugs:
        # Launch-0 variants (the baskets, the coaster set) are defined in the Launch-0
        # registry rather than the catalogue builder; the disclosed-render path verifies
        # against that registry, so readiness resolves them from the same place.
        cir = for_slug(slug) or authoritative_cir(slug)
        if cir is not None and owned_photography.needs_no_model(cir):
            photo_slugs.append(slug)
            photo_versions[slug] = cir.version
    photo = owned_photography.coverage(db, slugs=photo_slugs, versions=photo_versions)
    out.append(_listing_photography(db, photo))

    unpriced = sorted(l.product_slug for l in listings if l.price_cad <= 0)
    out.append(_build(
        "pricing", "every listing has a price", not unpriced and bool(listings),
        {"unpriced": unpriced[:5]}))

    out.append(_build(
        "content", "marketing content exists for the opening catalogue",
        content >= len(listings) and bool(listings),
        {"content_pieces": content, "listings": len(listings)}))

    store_problems = check_storefront(build_storefront(db=db))
    out.append(_build(
        "storefront", "shop announcement, About, all five policies, the shop SEO surface "
                      "(F-236) and the public identity (F-240) pass their checks",
        not store_problems, {"problems": store_problems[:8]}))
    out.extend(_storefront_items(db))

    out.append(_build(
        "no_open_incidents", "no unresolved P0/P1 defect",
        not any(i.severity in ("P0", "P1") for i in open_incidents),
        {"open": [i.severity for i in open_incidents][:5]}))

    out.append(_build(
        "spend_guards", "no spend scope is paused by a breach", not paused,
        {"paused_scopes": paused}))

    # -- what needs an account, a key or a service --------------------------
    # This line said "there is no Etsy client in this system at all" and stopped being true
    # the moment one was written. A readiness report that describes the system as it used to
    # be is worse than no report, because it is trusted.
    from ..integrations.etsy import Credentials

    etsy_creds = Credentials.from_env() is not None
    # F-594: the item reads the controlled round trip's own breadcrumbs instead of being
    # hard-coded. It turns ready only on a *full* `etsy_exercise` run that finished ok
    # against openapi.etsy.com (its status says so; a run against the local model of Etsy
    # never counts) with every draft it created matched by a verified removal, and while
    # this deployment still holds a credential.
    exercise = _etsy_exercise_evidence(db)
    proven = bool(exercise["round_trip_proven"])
    out.append(Requirement(
        key="etsy_integration",
        description="an Etsy integration exists, is credentialled and has been exercised",
        ready=proven and etsy_creds,
        blocked_by=None if (proven and etsy_creds) else BLOCKED_INTEGRATION,
        evidence={"client_written": True, "credentials_present": etsy_creds,
                  "ever_called": exercise["ever_called_against_etsy"],
                  **exercise,
                  "note": ("a full create -> read back -> delete round trip finished ok "
                           "against openapi.etsy.com and left no draft behind"
                           if proven else
                           "the client exists and is tested against a fake transport; no "
                           "full round trip against openapi.etsy.com is on record with every "
                           "draft it created confirmed removed. Written is not connected")}))

    out.append(Requirement(
        key="artifact_storage",
        description="purchased files live in durable storage",
        ready=storage_durable,
        blocked_by=None if storage_durable else BLOCKED_OWNER,
        evidence={"durable": storage_durable},
        owner_request=None if storage_durable else OBJECT_STORAGE))

    # -- what only a person can do ------------------------------------------
    out.append(Requirement(
        key="etsy_shop",
        description="an Etsy shop exists, with identity verification complete",
        ready=False, blocked_by=BLOCKED_OWNER,
        evidence={"note": "cannot be automated: platform identity verification"},
        owner_request=ETSY_ACCOUNT))

    out.append(Requirement(
        key="payout",
        description="a payout account and tax details are on the shop",
        ready=False, blocked_by=BLOCKED_OWNER,
        evidence={"note": "banking credentials are entered by the account holder"},
        owner_request=ETSY_PAYOUT))

    out.append(Requirement(
        key="listing_fees",
        description="the owner has approved Etsy's listing and transaction fees",
        ready=False, blocked_by=BLOCKED_OWNER,
        evidence={"listings": len(listings),
                  "estimate_cad": round(len(listings) * LISTING_FEE_CAD, 2)},
        owner_request=listing_fees_request(len(listings))))

    model_state = _model_state(db)
    out.append(Requirement(
        key="model_credits",
        description="the model provider can actually serve a request, proved by one",
        ready=bool(model_state["usable"]),
        blocked_by=None if model_state["usable"] else BLOCKED_OWNER,
        # A key is not a capability. This evidence is the provider's own words about why,
        # because "unavailable" covers both "no key" and "no credit" and those are different
        # things for the owner to act on.
        evidence=model_state,
        owner_request=None if model_state["usable"] else MODEL_CREDITS))

    out.append(Requirement(
        key="physical_calibration",
        description="at least one physical sample has calibrated the yardage estimate",
        # F-071 / F-086: waiting on an independent tester, never on the owner.
        ready=bool(physical_done), blocked_by=None if physical_done else BLOCKED_TESTER,
        evidence={"completed_tests": len(physical_done),
                  **({} if physical_done else {"owner_parked": PHYSICAL_SAMPLE_PARKED})},
        # Never the owner's ask any more, only ever unmet. See PHYSICAL_SAMPLE_PARKED.
        owner_request=None))

    # F-073 / F-080 / F-081 / F-086: the risk-based evidence requirement that replaces "the
    # owner must crochet a sample". Each certified release needs the evidence its effective
    # risk tier names -- deterministic at the automated threshold for Class A, a partial
    # physical test for B, a full make for C -- bound to its exact content. The calibration
    # requirement above stays: the underlying truth objective is not deleted.
    from ..gates.risk_matrix import catalogue_status

    tiers = catalogue_status(db)
    out.append(Requirement(
        key="risk_based_physical_evidence",
        description=("every certified release holds the physical evidence its risk tier "
                     "requires, bound to its exact content"),
        ready=tiers["ready"], blocked_by=None if tiers["ready"] else BLOCKED_TESTER,
        evidence=tiers,
        # Waiting on an independent tester (the `tester_roster` gate), never on the owner's
        # hands; each unmet row carries the spend request the owner would approve.
        owner_request=None))

    out.append(Requirement(
        key="brand_clearance",
        description="the shop name has been through a trademark knock-out search",
        ready=False, blocked_by=BLOCKED_OWNER,
        evidence={"name": "Brambleloop Studio"},
        owner_request=TRADEMARK_SCREEN))

    # #168: the pre-launch benchmark challenge. Deliberately a requirement rather than a
    # report, because a comparison nobody is obliged to act on is a comparison that loses to
    # a launch date. It reads the library rather than re-scoring anything: with no purchased
    # benchmark torn down, the challenge is unrunnable and therefore unpassed.
    from ..teardown.pipeline import challenge as benchmark_challenge

    from ..core.models import Product
    from ..teardown.pipeline import ChallengeRefused

    # Certification C-40 (#168). Two things made this unrunnable that were never the owner's
    # to fix: products carried no category, so the challenge matched on a slug family that
    # no benchmark is ever filed under; and our own scores were passed as {}, so even a torn
    # down benchmark had nothing to be compared against. The category now comes from the
    # concept seed the product was engineered from, one representative per category is
    # challenged (the requirement says products, plural), and our scores are read from the
    # audits recorded against `brambleloop:<slug>` -- unscored stays unscored, never neutral.
    from ..runtime.pipeline import _seed_for
    from ..teardown.scorecard import SELF_PREFIX

    from ..core.models import TeardownFinding

    representatives: dict[str, str] = {}
    uncategorised: list[str] = []
    with db.session() as s:
        for product in s.scalars(select(Product).order_by(Product.slug)):
            if not any(v.certified for v in product.versions):
                continue
            seed = _seed_for(product.slug)
            category = (seed.category if seed is not None else "") or ""
            if not category:
                uncategorised.append(product.slug)
                continue
            representatives.setdefault(category, product.slug)
        ours_by_slug: dict[str, dict] = {}
        for slug in representatives.values():
            scores: dict[str, float] = {}
            for f in s.scalars(select(TeardownFinding).where(
                    TeardownFinding.benchmark_ref == f"{SELF_PREFIX}{slug}")
                    .order_by(TeardownFinding.id)):
                scores[f.dimension] = float(f.score)   # latest recorded audit wins
            ours_by_slug[slug] = scores

    challenges = []
    for category, slug in sorted(representatives.items()):
        try:
            result = benchmark_challenge(db, product_slug=slug, category=category,
                                         our_scores=ours_by_slug.get(slug, {}))
        except ChallengeRefused as e:
            result = {"verdict": "unavailable", "comparable": False, "blocks_release": True,
                      "product": slug, "category": category, "reason": str(e), "rows": []}
        challenges.append(result)
    if not challenges:
        challenges.append({"verdict": "unavailable", "comparable": False,
                           "blocks_release": True, "product": "", "category": "",
                           "reason": "no certified product carries a category to be matched",
                           "rows": []})
    blocking = [c for c in challenges if c["blocks_release"]]
    challenge_result = {
        "verdict": "passed" if not blocking else blocking[0]["verdict"],
        "comparable": all(c["comparable"] for c in challenges),
        "blocks_release": bool(blocking),
        "product": ", ".join(c["product"] for c in challenges),
        "category": ", ".join(c["category"] for c in challenges),
        "reason": blocking[0].get("reason", "") if blocking else "",
        "rows": [r for c in challenges for r in c.get("rows", [])],
        "per_category": challenges,
        "uncategorised": uncategorised,
    }
    # The owner's MJs protocol, enforced rather than remembered: *do not ask me to purchase
    # the benchmark set until the complete intake and analysis path is verified ready*. So
    # the purchase request is withheld while our own laboratory cannot read a page. An
    # unready lab makes this ours to finish, not the owner's to fund -- and the difference
    # between those two is CA$292 of somebody else's copyrighted work sitting in a folder.
    from ..teardown import readiness as laboratory

    lab = laboratory.check(db)
    may_ask = bool(lab["ready_for_purchase"])
    blocked_by = None
    owner_request = None
    if challenge_result["blocks_release"]:
        if challenge_result["comparable"]:
            blocked_by = BLOCKED_BUILD
        elif may_ask:
            blocked_by, owner_request = BLOCKED_OWNER, BENCHMARK_PURCHASES
        else:
            blocked_by = BLOCKED_BUILD

    out.append(Requirement(
        key="benchmark_challenge",
        description=("a representative product has beaten, or deliberately traded against, "
                     "the best category-matched purchased benchmark"),
        ready=not challenge_result["blocks_release"],
        blocked_by=blocked_by,
        evidence={**challenge_result,
                  "teardown_laboratory": {"ready_for_purchase": may_ask,
                                          "verdict": lab["verdict"],
                                          "blocking": lab["blocking"]}},
        owner_request=owner_request))

    # v1.4's additions to the pre-Etsy gate (#54). Each is a thing that is obvious in
    # hindsight and is never on the list the first time: a rollback for the case where the
    # launch is wrong, an analytics baseline taken *before* the change so the change can be
    # read, and a brand moat that does not rest on the most copyable asset in it.
    from ..brand import moat as brand_moat

    moat_state = brand_moat.inventory(db)
    recognisable = moat_state.get("recognisable_without_model") or {}
    moat_ready = (bool(moat_state["structural_advantages"])
                  and bool(recognisable.get("listings"))
                  and not recognisable.get("not_recognisable"))
    out.append(Requirement(
        key="brand_moat",
        description=("the brand rests on something a competitor cannot reproduce in weeks, "
                     "and every product-first listing is recognisable without the model"),
        ready=moat_ready,
        blocked_by=None if moat_ready else BLOCKED_BUILD,
        evidence={"structural": moat_state["structural_advantages"],
                  "built": moat_state["built"], "planned": moat_state["planned"],
                  "not_recognisable_without_model": recognisable.get("not_recognisable"),
                  # C-80 defect 15: say which basis the recognisability rests on
                  "recognisability_measured": recognisable.get("measured"),
                  "recognisability_by_proxy_only": recognisable.get("by_proxy_only"),
                  "recognisability_proxy": recognisable.get("proxy"),
                  "recognisability_measurement_gated_on": recognisable.get(
                      "measurement_gated_on"),
                  "why": ("the canonical model is the most visible asset and the most "
                          "copyable; a brand that is only the model is a brand with a "
                          "week's lead (#44)")}))

    # C-69 (#54): the items the gate listed and never checked, each read from what the chain
    # actually produced for every listing -- never a constant.
    out.extend(_launch_package_items(db, listings))

    # F-329 (Sustainability Launch Gate): before launch, steady-state economics must be shown
    # sustainable at opening prices. Reads finance.sustainability (the F-325 forecast, with
    # its insufficient-data refusal, and F-324 break-even per product); a forecast that
    # cannot be computed, or recurring AI/API cost that threatens contribution, blocks.
    from ..finance import sustainability

    econ = sustainability.verdict(db)
    fc = econ["forecast"]
    out.append(_build(
        "sustainable_economics",
        "estimated steady-state AI/API cost is sustainable against contribution at opening "
        "prices, with no constant owner top-ups",
        # RC1 audit C1: ready only on the documented criterion in
        # `finance.sustainability` (coverage complete, unit margin positive at recorded
        # prices with modelled fees; assumed volumes may only block), and the evidence says
        # the verdict is MODELLED and which figures are ASSUMED.
        bool(econ["sustainable"]) and econ.get("basis") == "MODELLED",
        {"status": econ["status"], "why": econ["why"],
         "basis": econ.get("basis"),
         "criterion": econ.get("criterion"),
         "checks": econ.get("checks"),
         "coverage_gaps": (econ.get("coverage") or {}).get("gaps"),
         "unit_economics": econ.get("unit_economics"),
         "sales_per_month_needed_to_cover_recurring": econ.get(
             "sales_per_month_needed_to_cover_recurring"),
         "measured_orders": econ.get("measured_orders"),
         "problems": econ.get("problems") or [],
         "missing": fc.get("missing") or [],
         "low_case_needs_owner_top_up": econ.get("low_case_needs_owner_top_up"),
         "scenarios": {k: {"basis": "MODELLED", "volume_basis": "ASSUMED",
                           "assumed_sales_per_month": v["assumptions"]["sales_per_month"],
                           "ai_cost_monthly_cad": v["ai_cost_monthly_cad"],
                           "contribution_monthly_cad": v["contribution_monthly_cad"],
                           "net_monthly_cad": v["net_monthly_cad"]}
                       for k, v in (fc.get("scenarios") or {}).items()},
         "measured": fc.get("measured"),
         "break_even": {slug: {"break_even_sales": r.get("break_even_sales"),
                               "break_even_sales_is_floor": r.get("break_even_sales_is_floor"),
                               "reading": r.get("reading"),
                               "contribution_basis": r.get("contribution_basis"),
                               "creation_cost_cad": r.get("creation_cost_cad"),
                               "contribution_per_sale_cad": r.get("contribution_per_sale_cad")}
                        for slug, r in list(sustainability.break_even(db)["products"]
                                            .items())[:20]}}))

    out.append(Requirement(
        key="phase",
        description="the phase allows publishing",
        ready=phase.lower() not in ("shadow", "staging"),
        blocked_by=None if phase.lower() not in ("shadow", "staging") else BLOCKED_OWNER,
        evidence={"phase": phase, "providers": sorted(providers)},
        owner_request=None if phase.lower() not in ("shadow", "staging") else GRADUATION))

    return Readiness(requirements=out, unknowns=unknowns(db, out))


def _storefront_items(db) -> list[Requirement]:
    """F-238 opening grid, F-239/F-293 storefront preview, F-240 seller identity."""
    from ..brand import seller_identity, storefront_preview
    from ..brand.storefront import opening_grid

    grid = opening_grid(db)
    items = [_build(
        "opening_grid",
        "the shop's first screen holds launch-cleared products only, season first, strongest "
        "first, more than one price rung, and reads as one shop (F-238)",
        bool(grid["ok"]),
        {"problems": grid["problems"][:6], "visible": [t["slug"] for t in grid["visible"]],
         "excluded": len(grid["excluded"]), "coherence": grid["coherence"],
         "active_events": grid["active_events"]})]

    view = storefront_preview.preview(db, grid=grid)
    items.append(_build(
        "storefront_preview",
        "the pre-launch storefront preview renders at phone and desktop widths and passes its "
        "legibility checks: icon at 40/70px, banner crops, announcement opening, sections, "
        "first tiles from certified frames (F-239/F-293)",
        bool(view["ok"]),
        {"problems": view["problems"][:8], "icon_basis": view["icon"]["basis"],
         "banner_basis": view["banner"]["basis"],
         "tiles": [{"slug": t["slug"], "status": t["status"]} for t in view["tiles"]],
         # Not part of this requirement's verdict and never passed by it: the live shop as
         # Etsy serves it needs a browser worker and a live shop.
         "live_inspection": view["live_inspection"]}))

    ident = seller_identity.state()
    if ident["problems"]:
        blocked = BLOCKED_BUILD
    elif ident["undetermined"]:
        blocked = BLOCKED_OWNER
    else:
        blocked = None
    items.append(Requirement(
        key="seller_identity",
        description=("the public shop identity differs from the legal/tax identity only where "
                     "a cited Etsy rule permits, and the legal side is confirmed by the account "
                     "holder (F-240)"),
        ready=blocked is None, blocked_by=blocked,
        evidence={"problems": ident["problems"][:5], "undetermined": ident["undetermined"],
                  "pending_rule_readings": [r["field"] for r in ident["pending_rule_readings"]],
                  "note": ("legal, payout and tax identity are entered at Etsy KYC; the owner "
                           "request is the etsy_shop requirement's, not repeated here")},
        owner_request=None))
    return items


def product_of_slug(slug: str) -> str:
    """The product a CIR slug belongs to: its Launch-0 candidate, else the slug itself."""
    from ..products import launch0

    cand = launch0.candidate_for_cir(slug or "")
    return cand.slug if cand is not None else (slug or "")


def _launch_scope_counts(db, certified) -> tuple[dict, list[dict]]:
    """Certified versions split into what counts toward launch and legacy that counts zero."""
    from sqlalchemy import select

    from ..core.models import Product
    from ..publish.eligibility import legacy_status

    with db.session() as s:
        slug_of = {p.id: p.slug for p in s.scalars(select(Product))}
    counted = {"versions": 0, "in_launch_scope": 0, "legacy_recertified": 0,
               "slugs": set(), "products": set()}
    legacy: list[dict] = []
    for pv in certified:
        slug = slug_of.get(pv.product_id, "")
        status = legacy_status(slug, pv.certificate)
        if not status["cleared"]:
            legacy.append({"slug": slug, "version": pv.version, "why": status["why"]})
            continue
        counted["versions"] += 1
        counted["slugs"].add(slug)
        counted["products"].add(product_of_slug(slug))
        counted["in_launch_scope" if status["in_launch_scope"] else "legacy_recertified"] += 1
    return counted, legacy


# ---- the unknowns register (F-175) --------------------------------------------------------

def unknowns(db, requirements: list[Requirement] | None = None) -> list[dict]:
    """Every assumption and unknown the launch report rests on, collected in one place.

    Each entry names where it was read from, what is not known, and what it touches. They
    were recorded module by module -- the Etsy surface registry's unknowns, Launch-0's
    ESTIMATED and UNKNOWN labels, the twin's uncalibrated figures, the primitives no sample has
    measured -- and never gathered into the report the owner reads before launching. Zero is
    not a goal: an empty register with no evidence behind it would be the worst entry of all.
    """
    from sqlalchemy import func, select

    from ..cir.stitches import UNCALIBRATED, calibration_table
    from ..core.models import PhysicalTest

    out: list[dict] = []

    def add(key: str, source: str, unknown: str, touches: str) -> None:
        out.append({"key": key, "source": source, "unknown": unknown, "touches": touches})

    with db.session() as s:
        passed = s.scalar(select(func.count()).select_from(PhysicalTest).where(
            PhysicalTest.passed == True)) or 0  # noqa: E712
    if not passed:
        add("physical_calibration", "core.models.PhysicalTest",
            "no physical sample has been worked: every finished size, yardage and make-time "
            "figure is arithmetic from a stated gauge (twin.calibrated is False)",
            "size and yardage claims, Class C release, first-customer gauge_and_size_claims")

    uncalibrated = sorted(c for c, st in calibration_table().items() if st == UNCALIBRATED)
    if uncalibrated:
        add("uncalibrated_primitives", "cir.stitches.calibration_table",
            f"{len(uncalibrated)} stitch primitives have no measured height or yarn draw: "
            f"{', '.join(uncalibrated)}", "any pattern using them (F-074)")

    try:
        from ..intel import etsy_surfaces

        for surface, items in sorted(etsy_surfaces.coverage()["unknowns"].items()):
            for item in items:
                add(f"etsy_surface:{surface}", "intel.etsy_surfaces.coverage", item,
                    f"the Etsy surface {surface!r}")
    except Exception as e:  # noqa: BLE001 - an unreadable source is itself an unknown
        add("etsy_surfaces", "intel.etsy_surfaces.coverage",
            f"the surface registry could not be read: {type(e).__name__}", "Etsy surfaces")

    try:
        from ..products import launch0 as l0

        for slug in l0.LAUNCH0_SLUGS:
            cand = l0.candidate(slug)
            if cand.price.basis in (l0.ESTIMATED, l0.UNKNOWN):
                add(f"launch0_price:{slug}", "products.launch0.CANDIDATES",
                    f"the price band is {cand.price.basis}, not sourced", f"{slug} pricing")
            add(f"launch0_make_time:{slug}", "products.launch0.make_time",
                "make time is ESTIMATED at an assumed 700 stitches an hour, unmeasured until "
                "a sample is worked", f"{slug} make-time and lead-time claims")
    except Exception as e:  # noqa: BLE001
        add("launch0", "products.launch0", f"could not be read: {type(e).__name__}",
            "Launch-0")

    for r in requirements or []:
        ev = r.evidence or {}
        if ev.get("recognisability_by_proxy_only"):
            add(f"proxy:{r.key}", f"launch.readiness:{r.key}",
                f"measured by proxy only ({ev.get('recognisability_proxy')})", r.description)
        if r.key == "seller_identity":
            for f in ev.get("undetermined") or []:
                add(f"seller_identity:{f}", "brand.seller_identity",
                    f"the {f} on the legal/payout/tax side is UNKNOWN until the account "
                    f"holder confirms it at Etsy KYC", r.description)
        if r.key == "storefront_preview":
            add("storefront_preview:viewport", "brand.storefront_preview",
                "the phone banner crop, announcement length and section-label width are "
                "ASSUMED figures for Etsy's layout; the live shop is inspected only once a "
                "browser worker exists (rendered_pages)", r.description)
        if r.key == "model_credits" and not ev.get("probed"):
            add("model_provider", "gateway.anthropic.last_probe",
                "the model provider has never been probed", r.description)
    return out


# How recent the rollback rehearsal must be for the rollback plan to count as proved
# (C-80 defect 10: a rehearsed withdrawal round trip per listing, not a database restore).
ROLLBACK_PROOF_MAX_AGE_DAYS = 3
# The audit the listing stage writes per release with its search coverage at drafting: the
# pre-launch search baseline (#54). Traffic has no pre-launch reading -- it is UNMEASURED until
# the first Etsy Stats export is ingested (attribution.stats), and is recorded as such.
SEARCH_BASELINE_ACTION = "listing.query_portfolio"
TRAFFIC_BASELINE_KIND = "attribution.stats"
# #54's package: what must be ready before the owner is asked to open live Etsy operations.
LAUNCH_PACKAGE_KEYS: frozenset[str] = frozenset({
    "catalogue_depth", "digital_disclosure", "support_knowledge", "faq",
    "pricing_promotion_plan", "launch_calendar", "analytics_baseline", "rollback_plan",
})
# The owner requests that open or connect live Etsy operations, withheld while the package is
# not ready (the requirement's own ordering: package first, then the ask).
OPENS_LIVE_ETSY_KEYS: frozenset[str] = frozenset({"etsy_shop", "payout", "listing_fees",
                                                  "phase"})


def _launch_package_items(db, listings) -> list[Requirement]:
    """#54's digital disclosure, support knowledge, FAQ, pricing/promotion plan, launch
    calendar, analytics baseline and rollback plan, each measured per listing."""
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import desc, select

    from ..commerce.buyer_trust import listing_disclosure_finding
    from ..core.models import (ArtefactProvenance, AuditLog, OperatingReading,
                               PatternVersion, Product)
    from ..ops import artefacts as provenance

    releases = sorted({(l.product_slug, l.version) for l in listings})
    have = bool(releases)
    now = datetime.now(timezone.utc)

    def aware(v):
        return v if v is None or v.tzinfo else v.replace(tzinfo=timezone.utc)

    with db.session() as s:
        prov = {(r.artefact_class, r.artefact_key): r.validation_status for r in s.scalars(
            select(ArtefactProvenance).where(ArtefactProvenance.artefact_class.in_(
                ("support_knowledge", "release_bundle", "certificate"))))}
        current = provenance.current_from_db(s)
        fresh = {(v.artefact_class, v.artefact_key) for v in provenance.check(s, current=current)
                 if v.state == provenance.FRESH}
        audits: dict[str, set[str]] = {}
        for action in ("pricing.positioned", "launch.planned", "launch.held",
                       SEARCH_BASELINE_ACTION):
            audits[action] = {str(r.artifact or "") for r in s.scalars(
                select(AuditLog).where(AuditLog.action == action))}
        traffic = s.scalar(select(OperatingReading).where(
            OperatingReading.kind == TRAFFIC_BASELINE_KIND)
            .order_by(desc(OperatingReading.id)).limit(1))
        traffic_at = aware(traffic.at) if traffic is not None else None
        certs = {p.slug: bool(pv.certificate) for pv, p in s.execute(
            select(PatternVersion, Product).join(Product, Product.id == PatternVersion.product_id))}
    from . import rollback as rollback_mod

    rehearsals = {f"{slug}@{v}": rollback_mod.latest(db, slug=slug, version=v, now=now,
                                                     max_age_days=ROLLBACK_PROOF_MAX_AGE_DAYS)
                  for slug, v in releases}

    undisclosed = [f"{slug}@{v}" for slug, v in releases
                   if listing_disclosure_finding(db, slug=slug, version=v).get("finding")
                   or not listing_disclosure_finding(db, slug=slug, version=v).get("checked")]
    no_support = [f"{slug}@{v}" for slug, v in releases
                  if prov.get(("support_knowledge", f"{slug}@{v}#support")) != "passed"
                  or ("support_knowledge", f"{slug}@{v}#support") not in fresh]
    unpriced_plan = [l.product_slug for l in listings
                     if l.price_cad <= 0 or l.product_slug not in audits["pricing.positioned"]]
    uncalendared = [l.product_slug for l in listings
                    if l.product_slug not in audits["launch.planned"]]
    # C-80 defect 10 (Codex P12): the search baseline is the per-release coverage reading the
    # listing stage recorded at drafting, not `seo_score > 0`; the traffic baseline is the
    # first Stats export, UNMEASURED until one exists, and said so rather than proxied.
    no_baseline = [f"{slug}@{v}" for slug, v in releases
                   if f"{slug}@{v}" not in audits[SEARCH_BASELINE_ACTION]]
    traffic_status = ("MEASURED" if traffic_at is not None else
                      "UNMEASURED: no Etsy Stats export has been ingested; before the shop "
                      "exists there is no traffic to baseline, and the first export is the "
                      "baseline this gate will read")
    uncertified = [l.product_slug for l in listings if not certs.get(l.product_slug)]
    unrehearsed = [k for k, r in rehearsals.items() if r is None]
    rehearsal_failed = [k for k, r in rehearsals.items() if r is not None and not r.get("ok")]

    def req(key, description, bad, evidence):
        ready = have and not bad
        return Requirement(key=key, description=description, ready=ready,
                           blocked_by=None if ready else BLOCKED_BUILD,
                           evidence={**evidence, "listings": len(releases)})

    return [
        req("digital_disclosure", "every listing says, where a buyer reads first, that it is a "
            "digital pattern and not a finished item", undisclosed,
            {"missing_or_misplaced": undisclosed[:8]}),
        req("support_knowledge", "every listed release has a current, version-keyed support "
            "knowledge pack", no_support, {"without": no_support[:8]}),
        req("faq", "every listed release's FAQ was produced and checked against its PDF and "
            "listing (#40)", no_support, {"not_checked": no_support[:8]}),
        req("pricing_promotion_plan", "every listing was priced by the pricing stage, which "
            "refuses a fake discount; promotions are proposed only through the promotion "
            "rules", unpriced_plan, {"unplanned": unpriced_plan[:8]}),
        req("launch_calendar", "every listing has a launch date planned against its buying "
            "window", uncalendared, {"uncalendared": uncalendared[:8]}),
        req("analytics_baseline", "a pre-launch baseline exists: each listing's search "
            "coverage recorded at drafting (the traffic baseline is the first Stats export, "
            "recorded UNMEASURED until it exists)",
            no_baseline,
            {"releases_without_search_baseline": no_baseline[:8],
             "search_baseline_read_from": SEARCH_BASELINE_ACTION,
             "traffic_baseline": traffic_status,
             "traffic_baseline_at": traffic_at.isoformat() if traffic_at else None}),
        req("rollback_plan", "a way to withdraw everything published without losing the "
            "evidence: every listing's certificate retained and its withdrawal round trip "
            f"rehearsed (dry) within {ROLLBACK_PROOF_MAX_AGE_DAYS} days",
            uncertified + [f"unrehearsed:{k}" for k in unrehearsed]
            + [f"rehearsal_failed:{k}" for k in rehearsal_failed],
            {"without_retained_certificate": uncertified[:8],
             "unrehearsed": unrehearsed[:8], "rehearsal_failed": rehearsal_failed[:8],
             "rehearsals": {k: ({"ok": r.get("ok"), "at": r.get("at"),
                                 "failed_steps": [st["step"] for st in r.get("steps", [])
                                                  if not st["ok"]]}
                                if r is not None else None)
                            for k, r in sorted(rehearsals.items())[:8]},
             "read_from": rollback_mod.ACTION}),
    ]


def render(readiness: Readiness) -> str:
    """The report, as markdown, for a human who wants to read it rather than parse it."""
    lines = ["# Launch readiness", ""]
    lines.append(f"Ready to publish: **{'yes' if readiness.ready else 'no'}**")
    lines.append("")
    lines.append("| requirement | ready | blocked on |")
    lines.append("|---|---|---|")
    for r in readiness.requirements:
        lines.append(f"| {r.description} | {'yes' if r.ready else 'no'} | "
                     f"{r.blocked_by or '-'} |")

    buildable = readiness.buildable
    lines += ["", "## Still ours to do", ""]
    if buildable:
        lines += [f"- {r.description} ({r.evidence})" for r in buildable]
    else:
        lines.append("Nothing. Every remaining requirement needs a person or an account.")

    lines += ["", "## Unknowns and assumptions (F-175)", ""]
    if readiness.unknowns:
        lines += [f"- **{u['key']}** ({u['source']}): {u['unknown']} -- touches {u['touches']}"
                  for u in readiness.unknowns]
    else:
        lines.append("None recorded -- which is itself unverified, not a clean bill.")

    requests = readiness.owner_requests()
    lines += ["", "## OWNER ACTION REQUIRED", ""]
    if not requests:
        lines.append("None outstanding.")
    for i, o in enumerate(requests, start=1):
        lines += [
            f"**{i}. {o.action}**", "",
            f"- *Why:* {o.reason}",
            f"- *Maximum cost:* CA${o.max_cost_cad:.2f}",
            f"- *Minutes required:* {o.minutes}",
            f"- *Consequence of waiting:* {o.consequence_of_delay}",
            f"- *Blocks:* {o.blocks}", "",
        ]
    return "\n".join(lines) + "\n"


def _etsy_exercise_evidence(db) -> dict:
    """What the `etsy_exercise` audit breadcrumbs prove about the Etsy round trip (F-594).

    Read from the append-only ledger `integrations.etsy_exercise` writes: the finished-run
    rows (mode, ok, status) and the draft created / removed pairs. `_status` in that module
    starts a successful live run's status with "EXERCISED against openapi.etsy.com" and a
    run against the local model with "RAN AGAINST A LOCAL MODEL"; only the first counts.
    """
    from sqlalchemy import select

    from ..core.models import AuditLog

    live_prefix = "EXERCISED against openapi.etsy.com"
    local_prefix = "RAN AGAINST A LOCAL MODEL"
    created: set[str] = set()
    removed: set[str] = set()
    runs: list[dict] = []
    if db is None:
        return {"round_trip_proven": False, "ever_called_against_etsy": False,
                "exercise_runs": 0, "drafts_created": 0, "drafts_unmatched": []}
    with db.session() as s:
        for row in s.scalars(select(AuditLog).where(AuditLog.action.in_((
                "etsy.exercise_finished", "etsy.exercise_draft_created",
                "etsy.exercise_draft_removed"))).order_by(AuditLog.id)):
            detail = row.detail or {}
            if row.action == "etsy.exercise_finished":
                runs.append({"mode": detail.get("mode"), "ok": bool(detail.get("ok")),
                             "status": str(detail.get("status") or ""),
                             "at": row.at.isoformat() if row.at else None})
            elif detail.get("listing_id"):
                (created if row.action == "etsy.exercise_draft_created"
                 else removed).add(str(detail["listing_id"]))
    live_full = [r for r in runs if r["mode"] == "full" and r["ok"]
                 and r["status"].startswith(live_prefix)]
    unmatched = sorted(created - removed)
    return {
        "round_trip_proven": bool(live_full) and bool(created) and not unmatched,
        "ever_called_against_etsy": any(r["status"] and not r["status"].startswith(
            local_prefix) for r in runs),
        "exercise_runs": len(runs),
        "last_full_live_ok_at": live_full[-1]["at"] if live_full else None,
        "drafts_created": len(created),
        "drafts_unmatched": unmatched[:10],
    }


# ---- A3-07: one launch assessment, shared by the launch.readiness handler and the packet ----

@dataclass
class LaunchAssessment:
    """The launch verdict exactly as the gate computes it.

    `ready` is `readiness.ready` AND the off-device autonomy proof (#195) being PROVEN. The
    owner's launch packet and the `launch.readiness` job both read this, so the document the
    owner signs off on is the same computation as the gate -- same providers, same storage
    durability, same autonomy proof.
    """

    readiness: Readiness
    off_device: dict
    ready: bool
    providers: list[str]
    storage_durable: bool


def launch_assessment(db, *, phase: str, artifact_dir=None) -> LaunchAssessment:
    """Read-only: the inputs the handler uses, resolved the way the handler resolves them."""
    from ..build2 import autonomy
    from ..core.artifacts import ArtifactStore
    from ..gateway.model_gateway import available_providers

    try:
        providers = list(available_providers())
    except Exception:  # noqa: BLE001 - a gateway problem must not stop the assessment
        providers = []
    storage_durable = bool(ArtifactStore(artifact_dir).durable)
    readiness = assess(db, phase=phase, providers=providers, storage_durable=storage_durable)
    off_device = autonomy.launch_item(db)
    ready = bool(readiness.ready) and off_device.get("status") == autonomy.PROVEN
    return LaunchAssessment(readiness=readiness, off_device=off_device, ready=ready,
                            providers=providers, storage_durable=storage_durable)
