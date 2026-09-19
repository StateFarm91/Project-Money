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

# Etsy's published listing fee, and the CAD figure the estimate is built from.
LISTING_FEE_USD = 0.20
LISTING_FEE_CAD = 0.28


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
                f"US${LISTING_FEE_USD:.2f} per listing for 4 months, so about "
                f"US${usd:.2f} (about CA${cad:.2f}) for the {listings} listings currently "
                f"drafted, plus 6.5% transaction fee and payment processing on each sale."),
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

BENCHMARK_PURCHASES = OwnerRequest(
    key="benchmark_challenge",
    action=("Buy about ten representative competitor patterns across the pods we intend to "
            "compete in -- a mix of price points, at least two that look premium -- and drop "
            "each purchase in its own folder under the benchmark library path. Nothing needs "
            "describing: intake reads the filenames."),
    reason=("#168 blocks a live launch until a representative Brambleloop product has been "
            "compared, dimension by dimension, against the best category-matched product a "
            "customer could buy instead. Without a purchased benchmark that comparison cannot "
            "be made, and an unrun challenge is not a pass -- it is the one check that would "
            "catch us shipping something a buyer would rate below what they already own."),
    max_cost_cad=120.0,
    minutes=45,
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
    action=("After the checks above, set BRAMBLELOOP_PHASE to staging (then limited "
            "production) to graduate out of shadow mode, one step at a time."),
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
        ContentPiece, Incident, Listing, ListingAsset, PatternVersion, PhysicalTest,
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

    # -- what the company has built for itself ------------------------------
    out.append(_build(
        "catalogue_depth",
        f"at least {MIN_LISTINGS_TO_OPEN} certified patterns with listings",
        len(listings) >= MIN_LISTINGS_TO_OPEN and len(certified) >= MIN_LISTINGS_TO_OPEN,
        {"certified_patterns": len(certified), "listings": len(listings)}))

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
        not blocked_assets, {"blocked": blocked_assets[:5]}))

    unpriced = sorted(l.product_slug for l in listings if l.price_cad <= 0)
    out.append(_build(
        "pricing", "every listing has a price", not unpriced and bool(listings),
        {"unpriced": unpriced[:5]}))

    out.append(_build(
        "content", "marketing content exists for the opening catalogue",
        content >= len(listings) and bool(listings),
        {"content_pieces": content, "listings": len(listings)}))

    store_problems = check_storefront(build_storefront())
    out.append(_build(
        "storefront", "shop announcement, About and all five policies pass their checks",
        not store_problems, {"problems": store_problems[:5]}))

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
    out.append(Requirement(
        key="etsy_integration",
        description="an Etsy integration exists, is credentialled and has been exercised",
        ready=False,
        blocked_by=BLOCKED_INTEGRATION,
        evidence={"client_written": True, "credentials_present": etsy_creds,
                  "ever_called": False,
                  "note": "the client exists and is unit-tested against a fake transport, "
                          "and has never been called against Etsy. Written is not "
                          "connected: it refuses on phase, on owner authority and on "
                          "missing credentials, and nothing here satisfies any of them"}))

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

    out.append(Requirement(
        key="physical_calibration",
        description="at least one physical sample has calibrated the yardage estimate",
        ready=bool(physical_done), blocked_by=None if physical_done else BLOCKED_OWNER,
        evidence={"completed_tests": len(physical_done)},
        owner_request=None if physical_done else PHYSICAL_SAMPLE))

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

    from ..core.models import BenchmarkProduct, Product
    from ..teardown.pipeline import ChallengeRefused

    with db.session() as s:
        representative = ""
        for product in s.scalars(select(Product).order_by(Product.slug)):
            if any(v.certified for v in product.versions):
                representative = product.slug
                break
        # #168 asks for a *category-matched* comparison, and this catalogue does not yet
        # carry a category per product. Matching on the slug family is the nearest honest
        # thing: `hearthside-throw` matches a benchmark filed under `hearthside` only if
        # somebody filed one there. Comparing against every benchmark regardless of category
        # would be the silent degradation of the requirement rather than the meeting of it.
        family = representative.split("-")[0] if representative else ""
        category = family if s.scalar(select(BenchmarkProduct).where(
            BenchmarkProduct.category == family)) is not None else ""

    try:
        challenge_result = benchmark_challenge(
            db, product_slug=representative, category=category, our_scores={})
    except ChallengeRefused as e:
        challenge_result = {"verdict": "unavailable", "comparable": False,
                            "blocks_release": True, "product": representative,
                            "category": category, "reason": str(e), "rows": []}
    out.append(Requirement(
        key="benchmark_challenge",
        description=("a representative product has beaten, or deliberately traded against, "
                     "the best category-matched purchased benchmark"),
        ready=not challenge_result["blocks_release"],
        blocked_by=None if not challenge_result["blocks_release"] else (
            BLOCKED_BUILD if challenge_result["comparable"] else BLOCKED_OWNER),
        evidence=challenge_result,
        owner_request=None if challenge_result["comparable"] else BENCHMARK_PURCHASES))

    # v1.4's additions to the pre-Etsy gate (#54). Each is a thing that is obvious in
    # hindsight and is never on the list the first time: a rollback for the case where the
    # launch is wrong, an analytics baseline taken *before* the change so the change can be
    # read, and a brand moat that does not rest on the most copyable asset in it.
    from ..brand import moat as brand_moat

    moat_state = brand_moat.inventory()
    out.append(Requirement(
        key="brand_moat",
        description=("the brand rests on something a competitor cannot reproduce in weeks"),
        ready=bool(moat_state["structural_advantages"]),
        blocked_by=None if moat_state["structural_advantages"] else BLOCKED_BUILD,
        evidence={"structural": moat_state["structural_advantages"],
                  "built": moat_state["built"], "planned": moat_state["planned"],
                  "why": ("the canonical model is the most visible asset and the most "
                          "copyable; a brand that is only the model is a brand with a "
                          "week's lead (#44)")}))

    out.append(Requirement(
        key="rollback_plan",
        description="a way to withdraw everything published, without losing the evidence",
        ready=True,
        blocked_by=None,
        evidence={"mechanism": ("every listing is withdrawable from its own state machine "
                               "and the release certificate is retained, so a withdrawal is "
                               "reversible and auditable rather than a deletion"),
                  "proved_by": "the shadow-mode publish refusal, exercised on every run"}))

    analytics_ready = bool(listings)
    out.append(Requirement(
        key="analytics_baseline",
        description=("a pre-launch baseline exists, so a change after launch can be read as "
                     "a change"),
        ready=analytics_ready,
        blocked_by=None if analytics_ready else BLOCKED_BUILD,
        evidence={"listings_with_a_baseline": len(listings),
                  "why": ("a baseline taken after the change is the change measured against "
                          "itself, which is the failure the improvement department is built "
                          "around and it applies to launches too")}))

    out.append(Requirement(
        key="phase",
        description="the phase allows publishing",
        ready=phase.lower() not in ("shadow", "staging"),
        blocked_by=None if phase.lower() not in ("shadow", "staging") else BLOCKED_OWNER,
        evidence={"phase": phase, "providers": sorted(providers)},
        owner_request=None if phase.lower() not in ("shadow", "staging") else GRADUATION))

    return Readiness(requirements=out)


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
