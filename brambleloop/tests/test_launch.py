"""Launch readiness: who is each remaining blocker waiting on?

The distinction this file defends is the one the Execution Directive cares about. A
requirement this system can satisfy itself is never an owner action — asking the owner for an
Etsy account because it will eventually be needed is precisely what the directive forbids.
A requirement that needs a person's identity, a person's bank account or a person's hands is
never ours, and pretending otherwise leaves the company permanently almost-ready.

So: every unmet requirement names who it waits on, nothing blocked on build reaches the owner
queue, and every owner action carries the five things the directive asks for.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

# The stocked warehouse puts its frames and PDFs on disk under their hashes, because the
# rollback rehearsal (#54) checks they are restorable; the store reads its root at import.
_TMP = tempfile.mkdtemp(prefix="launch_readiness_")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")

from sqlalchemy import select  # noqa: E402

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    ContentPiece, Listing, ListingAsset, PatternVersion, PhysicalTest, Product,
)
from brambleloop.launch.readiness import (  # noqa: E402
    BLOCKED_BUILD, BLOCKED_INTEGRATION, BLOCKED_OWNER, BLOCKED_TESTER, MIN_APPROVED_ASSETS,
    MIN_LISTINGS_TO_OPEN, assess, render,
)


def _db() -> Database:
    db = Database("sqlite://")
    db.create_all()
    return db


def _catalogue_slugs(n: int) -> list[str]:
    """Real product-first slugs, because the launch gate reads real CIRs.

    The fixture used synthetic `product-0` names, which have no CIR -- so
    `listing_photography` could never be satisfied in a test however much was stocked,
    which is a floor nothing can clear living in the fixture rather than in the code. Real
    slugs also make "a company that has done its half" mean the same thing here as it does
    in production.
    """
    from brambleloop.products.builder import CATALOGUE, for_slug
    from brambleloop.publish import owned_photography as _op

    out = []
    for slug in CATALOGUE:
        cir = for_slug(slug)
        if cir is not None and _op.needs_no_model(cir):
            out.append(slug)
        if len(out) >= n:
            break
    return out


VERSION = "1.0.0"


def _version(slug: str) -> str:
    """The stocked release is the product's real certified version, so the disclosed set,
    the listing and the pattern version all name the same release."""
    from brambleloop.products.builder import for_slug

    cir = for_slug(slug)
    return cir.version if cir is not None else VERSION
from brambleloop.gates.certificate import GAUGE_STANDARD as _GAUGE_STANDARD  # noqa: E402
# Listing copy that makes every owed disclosure (#41) where the buyer reads it: the digital
# nature in the title, the rest on the first screen.
_TITLE = "{title} - Digital Crochet Pattern (not a finished item)"
_DESCRIPTION = ("Intermediate skill level. You will need worsted yarn and a 5 mm hook. "
                "Written in US crochet terms. Instant digital download after purchase. "
                "Questions? Message us and we answer from the version you bought.")


def _stock(db, listings: int = MIN_LISTINGS_TO_OPEN, frames: int = MIN_APPROVED_ASSETS,
           content_each: int = 1, photographs: bool = True, package: bool = True) -> None:
    """A warehouse that looks like a company that has done its half of the work.

    `photographs=False` is the live situation of 2026-09-23: approved chart frames on every
    listing and not one product photograph that cleared its floors.

    `package=True` (C-80, #54) is the rest of "its half": the launch package the gate reads
    per listing -- disclosing copy, a current version-keyed support pack, the pricing and
    launch-calendar audits the stages write, the search baseline recorded at drafting, a PDF
    and frames on disk under their hashes, and the withdrawal rehearsal run for real over
    them. `package=False` is a company that has drafted listings and built nothing else yet.
    """
    from brambleloop.agents.registry import Registry
    from brambleloop.core.artifacts import ArtifactStore
    from brambleloop.products.builder import for_slug
    from brambleloop.publish import owned_photography as _op

    slugs = _catalogue_slugs(listings)
    store = ArtifactStore()

    with db.session() as s:
        for i, slug in enumerate(slugs):
            product = Product(slug=slug, title=f"Product {i}", status="certified")
            s.add(product)
            s.flush()
            s.add(PatternVersion(product_id=product.id, version=_version(slug),
                                 cir_json={}, release_hash="0" * 64, certified=True,
                                 # F-119: a company that has done its half has
                                 # re-certified under the current gauge standard; a
                                 # certificate without the stamp is legacy and counts zero.
                                 certificate={"granted": True,
                                              "gauge_standard": _GAUGE_STANDARD,
                                              "stages_run": ["compile", "twin", "reverse"]}))
            s.add(Listing(product_slug=slug, version=_version(slug),
                          title=_TITLE.format(title=f"Product {i}"),
                          description=_DESCRIPTION, price_cad=9.5, state="draft"))
            for position in range(frames):
                # real bytes under their real hash, so a restore has something to re-serve
                stored = store.put(f"{slug}-frame-{position}",
                                   f"frame {position} of {slug}".encode(), "image/png")
                s.add(ListingAsset(product_slug=slug, version=_version(slug), position=position,
                                   asset_class="INFOGRAPHIC", role="frame",
                                   sha256=stored.sha256, approved=True))
            for n in range(content_each):
                s.add(ContentPiece(product_slug=slug, channel="article",
                                   title=f"piece {n}", body="body"))
    if photographs:
        # F-852 / D-FB-7: the imagery a company can actually have done is a verified
        # disclosed render set, for each product a qualified renderer can draw truthfully.
        # This used to file self-declared `usable_as_listing_asset: True` photography rows,
        # which no longer count: usability is structural truth PASS on bound bytes.
        for slug in slugs:
            _disclosed_set(db, slug)
    if package:
        _package(db, slugs)
        _economics(db, slugs)


_DISCLOSED: dict = {}


def _disclosed_set(db, slug: str, *, disclosing_copy: bool = True) -> dict | None:
    """File the real disclosed render set for `slug`, when it is in Launch-0 scope.

    Built once per run (the producer and verifier are deterministic and the bytes stay in
    this run's artifact store) and filed into each database. The listing for the set's own
    version carries the copy disclosure unless told otherwise. Out-of-scope products get
    nothing: there is no truthful image path for them, and the fixture does not pretend.
    """
    from brambleloop.publish import disclosed_listing, listing_asset
    from brambleloop.visual.render_verification import authoritative_cir

    if not listing_asset._in_launch_scope(slug):
        return None
    if slug not in _DISCLOSED:
        rec = disclosed_listing.build(authoritative_cir(slug))
        assert rec["usable_as_listing_asset"], rec["launch_blocked"]
        _DISCLOSED[slug] = rec
    rec = _DISCLOSED[slug]
    disclosed_listing.record(db, rec)
    copy_text = _DESCRIPTION + ("\n\n" + disclosed_listing.COPY_DISCLOSURE
                                if disclosing_copy else "")
    with db.session() as s:
        row = s.scalar(select(Listing).where(Listing.product_slug == slug,
                                             Listing.version == rec["version"]))
        if row is None:
            s.add(Listing(product_slug=slug, version=rec["version"],
                          title=_TITLE.format(title=slug), description=copy_text,
                          price_cad=9.5, state="draft"))
        else:
            row.description = copy_text
    return rec


def _economics(db, slugs: list[str]) -> None:
    """F-329: a company that has done its half has also shown its economics are sustainable.

    Thirty days of modest measured AI/API spend -- platform cadences plus the creation spend
    tagged to each product -- so the steady-state forecast can be computed rather than
    refused. The sustainability gate reads these rows; nothing here asserts a verdict.
    """
    from datetime import datetime, timedelta, timezone

    from brambleloop.core.models import CostEntry

    now = datetime.now(timezone.utc)
    with db.session() as s:
        for d in range(1, 31):
            s.add(CostEntry(agent="gateway", kind="llm", amount_cad=0.02,
                            at=now - timedelta(days=d), purpose="observation"))
        for slug in slugs:
            s.add(CostEntry(agent="gateway", kind="llm", amount_cad=0.5,
                            at=now - timedelta(days=20), product_slug=slug,
                            purpose="creation"))


def _package(db, slugs: list[str]) -> None:
    """The #54 launch package for the stocked releases, as the chain's stages leave it."""
    from brambleloop.core.artifacts import ArtifactStore
    from brambleloop.core.models import ArtefactProvenance, AuditLog, Job, JobStatus
    from brambleloop.launch import rollback
    from brambleloop.ops import artefacts as provenance

    store = ArtifactStore()
    with db.session() as s:
        current = provenance.current_from_db(s)
        for slug in slugs:
            pdf = store.put(f"{slug}-pdf", f"customer pdf of {slug}".encode(),
                            "application/pdf")
            s.add(Job(agent="publisher", job_type="assets.build", status=JobStatus.DONE,
                      inputs={"slug": slug, "version": _version(slug)},
                      outputs={"slug": slug, "version": _version(slug), "pdf_sha256": pdf.sha256}))
            # the version-keyed support pack, fresh against what the system holds now
            s.add(ArtefactProvenance(
                artefact_class="support_knowledge", artefact_key=f"{slug}@{_version(slug)}#support",
                product_slug=slug, created_by="publisher", validation_status="passed",
                inputs={ref: current[ref] for ref in
                        (f"cir:{slug}", f"release:{slug}", "chain:release")}))
            for action, artifact in (("pricing.positioned", slug), ("launch.planned", slug),
                                     ("listing.query_portfolio", f"{slug}@{_version(slug)}")):
                s.add(AuditLog(actor="orchestrator", action=action, artifact=artifact,
                               detail={"fixture": "stocked warehouse"}))
    # the rehearsal is the real one, run over the fixture's rows and bytes
    for slug in slugs:
        rollback.rehearse(db, slug=slug, version=_version(slug), store=store)


def test_an_empty_company_is_blocked_on_itself_not_on_the_owner():
    readiness = assess(_db(), phase="shadow")
    buildable = {r.key for r in readiness.buildable}
    assert "catalogue_depth" in buildable
    assert "listing_imagery" in buildable
    # None of those are owner actions.
    owner_keys = {r.key for r in readiness.blocked_on(BLOCKED_OWNER)}
    assert not (buildable & owner_keys)


def test_every_unmet_requirement_names_who_it_waits_on():
    """An unmet requirement blocked on nothing reads as though it were nobody's job."""
    for phase in ("shadow", "staging", "production"):
        readiness = assess(_db(), phase=phase)
        unattributed = [r.key for r in readiness.outstanding if not r.blocked_by]
        assert not unattributed, (phase, unattributed)


def test_a_company_that_has_done_its_half_is_only_blocked_on_people():
    """F-852 / D-FB-7 rewrite. The fixture used to file self-declared "usable" photography
    rows for eight products, a half no company can do any more: generative redraw is
    refused and usability needs structural truth PASS on bound bytes. A company that has
    done everything it *can* has a verified disclosed set for every product a qualified
    renderer draws (Launch-0), and nothing else is pretended.

    So the property is asserted exactly: the one company-side item is listing imagery for
    the products with no truthful image path, named; the Launch-0 product with its verified
    set is counted listable; everything else waits on a person or an account.
    """
    from brambleloop.publish import listing_asset

    db = _db()
    _stock(db)
    readiness = assess(db, phase="shadow")
    # F-238 / F-239: the opening grid and the storefront preview are company-side work too,
    # and in this fixture they are honestly unfinished: no stocked product is launch-cleared
    # (`app.dashboard_truth.launch_inventory` -- no creative-gate survivor, and the gauge
    # criterion is unassessed there), so the first screen is empty and has no tiles. They are
    # named exactly, with the reason, rather than folded into "only imagery is left".
    # F-400 / F-879 (lane TOOLS): the Final Master closure is company-side work too, and it is
    # honestly unfinished while any launch-critical row is OPEN or the snapshot fails integrity.
    from brambleloop.build2 import final_master
    fm = final_master.summary(db)
    expected = ["listing_photography", "opening_grid", "storefront_preview"]
    # F-233 (W4-FM2): the storefront requirement reads the rendered icon/banner and buyer copy
    # (store_foundation.storefront_gate), not the briefs. While that gate has findings the
    # storefront is honestly unfinished company work, named with its asset findings.
    from brambleloop.store_foundation import storefront_gate
    if storefront_gate.problems(db):
        expected.insert(1, "storefront")
        store = next(r for r in readiness.requirements if r.key == "storefront")
        assert any(p.startswith("asset: ") for p in store.evidence["problems"]), store.evidence
    if not fm.get("launch_ready"):
        assert fm.get("launch_critical_open") or fm.get("integrity_violations") \
            or fm.get("status") != "OK", fm
        expected.append("final_master_closure")
    assert [r.key for r in readiness.buildable] == expected, \
        [r.key for r in readiness.buildable]
    grid = next(r for r in readiness.requirements if r.key == "opening_grid")
    assert grid.evidence["problems"][0].startswith("OPENING_GRID_EMPTY"), grid.evidence
    photo = next(r for r in readiness.requirements if r.key == "listing_photography")
    stocked = _catalogue_slugs(MIN_LISTINGS_TO_OPEN)
    in_scope = [s for s in stocked if listing_asset._in_launch_scope(s)]
    assert in_scope, "the stocked catalogue carries no Launch-0 product"
    assert photo.evidence["with_disclosed_render"] == sorted(in_scope), photo.evidence
    assert photo.evidence["listable"] == len(in_scope)
    assert sorted(photo.evidence["with_no_asset_at_all"]) == sorted(
        s for s in stocked if s not in in_scope)[:5]
    remaining = {r.blocked_by for r in readiness.outstanding
                 if r.key not in ("listing_photography", "opening_grid", "storefront_preview",
                                  "storefront", "final_master_closure")}
    # F-071: a sample waits on an independent tester -- a person, and not the owner.
    assert remaining <= {BLOCKED_OWNER, BLOCKED_INTEGRATION, BLOCKED_TESTER}, remaining


def test_a_verified_disclosed_set_takes_listing_imagery_off_the_company_side():
    """D-FB-7: with the Launch-0 product's disclosed set verified, QA-clean and disclosed in
    the image, the alt text and the copy, listing imagery is no longer company work. What
    still blocks the listing's parity is reported truthfully against who can clear it:
    HERO waits on a vision description (`image_vision`, closed in shadow), COMPETITIVE on a
    blind review over observed benchmark galleries -- integration/data gated, never folded
    into company work and never assumed passed."""
    from brambleloop.publish import listing_asset

    db = _db()
    slug = next(s for s in _catalogue_slugs(MIN_LISTINGS_TO_OPEN)
                if listing_asset._in_launch_scope(s))
    rec = _disclosed_set(db, slug)
    _certified(db, slug, {"granted": True, "gauge_standard": _GAUGE_STANDARD})
    readiness = assess(db, phase="shadow")
    photo = next(r for r in readiness.requirements if r.key == "listing_photography")
    assert photo.evidence["with_disclosed_render"] == [slug], photo.evidence
    assert photo.blocked_by == BLOCKED_INTEGRATION, (photo.blocked_by, photo.evidence)
    assert photo.evidence["parity_company_work"] == {}, photo.evidence
    waiting = photo.evidence["parity_waiting_on_gates"][slug]
    assert set(waiting) == {"hero", "competitive_blind_review"}, waiting
    assert "image_vision" in waiting["hero"]
    assert "listing_photography" not in {r.key for r in readiness.buildable}

    # The copy without its disclosure is company work again, and says which dimension.
    _disclosed_set(db, slug, disclosing_copy=False)
    again = next(r for r in assess(db, phase="shadow").requirements
                 if r.key == "listing_photography")
    assert again.blocked_by == BLOCKED_BUILD
    assert any(x.startswith("lifestyle_quality") for x in
               again.evidence["parity_company_work"][slug]), again.evidence


def test_a_thin_catalogue_is_ours_to_fix():
    db = _db()
    _stock(db, listings=MIN_LISTINGS_TO_OPEN - 3)
    readiness = assess(db, phase="shadow")
    assert "catalogue_depth" in {r.key for r in readiness.buildable}


def test_a_listing_short_of_frames_is_ours_to_fix_and_says_which():
    db = _db()
    _stock(db, frames=MIN_APPROVED_ASSETS - 2)
    readiness = assess(db, phase="shadow")
    frames = next(r for r in readiness.requirements if r.key == "listing_imagery")
    assert frames.blocked_by == BLOCKED_BUILD
    assert frames.evidence["listings_short_of_frames"], frames.evidence


def test_a_blocked_asset_stops_the_launch_and_is_not_an_owner_problem():
    db = _db()
    _stock(db)
    with db.session() as s:
        asset = s.scalars(select(ListingAsset)).first()
        asset.blocked_reasons = ["ASSET_MOTIF_ABSENT: depicts a cable the pattern never works"]
    readiness = assess(db, phase="shadow")
    truthful = next(r for r in readiness.requirements if r.key == "imagery_truthful")
    assert not truthful.ready
    assert truthful.blocked_by == BLOCKED_BUILD


def test_the_owner_queue_carries_everything_the_directive_asks_for():
    db = _db()
    _stock(db)
    for request in assess(db, phase="shadow").owner_requests():
        assert request.action.strip()
        assert request.reason.strip()
        assert request.minutes > 0, request.action
        assert request.max_cost_cad >= 0
        assert request.consequence_of_delay.strip()
        assert request.blocks.strip()


def test_nothing_blocked_on_build_is_ever_sent_to_the_owner():
    db = _db()
    readiness = assess(db, phase="shadow")
    for r in readiness.buildable:
        assert r.owner_request is None, r.key


def test_a_completed_physical_test_clears_its_requirement():
    """The one requirement the system can watch being satisfied.

    It used to clear an owner action too. The owner has since parked that ask twice -- they
    will not be the one who crochets the sample -- so the request is already withdrawn and
    the queue does not move. The requirement still clears, which is the part that was ever
    about evidence.
    """
    db = _db()
    _stock(db)
    before = assess(db, phase="shadow")
    assert not next(r for r in before.requirements
                    if r.key == "physical_calibration").ready

    with db.session() as s:
        s.add(PhysicalTest(product_slug="product-0", version="1.0.0", tester_ref="owner",
                           passed=True, measured={"grams": 180}))
    after = assess(db, phase="shadow")
    assert next(r for r in after.requirements if r.key == "physical_calibration").ready
    assert len(after.owner_requests()) == len(before.owner_requests())


def test_shadow_mode_can_never_be_launch_ready():
    db = _db()
    _stock(db)
    readiness = assess(db, phase="shadow")
    assert not readiness.ready
    phase = next(r for r in readiness.requirements if r.key == "phase")
    assert phase.blocked_by == BLOCKED_OWNER, "only the owner graduates the phase"


def test_etsy_is_reported_as_written_but_never_called():
    """The evidence has to track the system, not the system as it used to be.

    This line read "there is no Etsy client in this system at all" and stopped being true the
    moment one was written. A readiness report that describes a previous version of the
    system is worse than no report, because it is trusted -- so the assertion is now that
    "written" is distinguished from "connected", which is the distinction that matters.
    """
    readiness = assess(_db(), phase="shadow")
    etsy = next(r for r in readiness.requirements if r.key == "etsy_integration")
    assert etsy.blocked_by == BLOCKED_INTEGRATION
    assert etsy.ready is False
    assert etsy.evidence["client_written"] is True
    assert etsy.evidence["ever_called"] is False
    assert etsy.evidence["credentials_present"] is False, \
        "this environment must not carry Etsy credentials"


def test_the_report_states_the_owner_actions_in_the_required_format():
    db = _db()
    _stock(db)
    text = render(assess(db, phase="shadow"))
    assert "OWNER ACTION REQUIRED" in text
    for field in ("*Why:*", "*Maximum cost:*", "*Minutes required:*",
                  "*Consequence of waiting:*", "*Blocks:*"):
        assert field in text, field
    # F-852 / D-FB-7: the stocked company still owes truthful imagery for the products no
    # qualified renderer draws, so the report lists it as the company's own work rather than
    # saying nothing is left (see the test above).
    assert "truthful customer-ready listing imagery" in text
    assert "Nothing. Every remaining requirement needs a person or an account." not in text

    # With only person- and account-gated requirements left, the report says so in words.
    from brambleloop.launch.readiness import ETSY_ACCOUNT, Readiness, Requirement

    people_only = Readiness(requirements=[Requirement(
        key="etsy_shop", description="an Etsy shop exists", ready=False,
        blocked_by=BLOCKED_OWNER, owner_request=ETSY_ACCOUNT)])
    assert "Nothing. Every remaining requirement needs a person or an account." in \
        render(people_only)



def test_the_fee_approval_is_costed_from_the_catalogue_that_actually_exists():
    """An owner action asking approval for a number must name the real number.

    The fee request was a module constant reading "about US$1.80 (CA$2.50) for nine
    listings" -- true when it was written, and still shown to the owner after the catalogue
    reached sixteen, directly beside an evidence field that computed CA$4.48 from the real
    count. The approval *is* the figure, so a stale figure is not cosmetic: it asks consent
    for one amount against a charge of another.
    """
    from brambleloop.launch.readiness import LISTING_FEE_CAD, listing_fees_request

    nine = listing_fees_request(9)
    sixteen = listing_fees_request(16)
    assert "9 listings" in nine.action, nine.action
    assert "16 listings" in sixteen.action, sixteen.action
    assert nine.action != sixteen.action, "the request did not move with the catalogue"

    for count in (1, 9, 16, 40):
        request = listing_fees_request(count)
        expected = f"CA${round(count * LISTING_FEE_CAD, 2):.2f}"
        assert expected in request.action, (count, expected, request.action)
        # The ceiling never sits below what it is approving.
        assert request.max_cost_cad >= count * LISTING_FEE_CAD, count

    source = (Path(__file__).resolve().parents[1]
              / "src" / "brambleloop" / "launch" / "readiness.py").read_text()
    assert "for nine listings" not in source, \
        "the fee request has been hardcoded to a catalogue size again"


def test_the_fee_request_and_its_evidence_agree():
    """They sit next to each other in the report, so they must not disagree.

    This is the pairing that caught the defect: the owner reads the sentence, and anyone
    checking reads the evidence. One derived and one hardcoded is how they drifted.
    """
    from brambleloop.launch.readiness import listing_fees_request

    db = _db()
    _stock(db)
    report = assess(db, phase="shadow")
    fees = next(r for r in report.requirements if r.key == "listing_fees")
    assert fees.owner_request is not None
    assert fees.evidence["listings"] == MIN_LISTINGS_TO_OPEN
    assert f"CA${fees.evidence['estimate_cad']:.2f}" in fees.owner_request.action, (
        fees.evidence, fees.owner_request.action)
    assert fees.owner_request.action == listing_fees_request(
        fees.evidence["listings"]).action


def test_every_owner_request_has_a_stable_identity_distinct_from_its_wording():
    """The queue de-duplicates on the requirement, not on the prose.

    Comparing action text worked only while every action was a frozen string. The moment one
    of them derived its figure from the catalogue, a changed number read as a new request --
    and `test_the_owner_queue_is_written_by_the_system_not_by_hand` caught it immediately,
    queueing eight actions where seven existed. An owner queue that lists the same decision
    twice with two different numbers is worse than one that merely grows.
    """
    db = _db()
    _stock(db)
    report = assess(db, phase="shadow")
    requests = report.owner_requests()
    assert requests, "no owner requests at all"

    keys = [r.key for r in requests]
    assert all(keys), f"an owner request has no identity: {keys}"
    assert len(keys) == len(set(keys)), f"two owner requests share an identity: {keys}"

    requirement_keys = {r.key for r in report.requirements}
    for request in requests:
        assert request.key in requirement_keys, request.key

    # The identity must not be derived from the wording, or it would move with it.
    from brambleloop.launch.readiness import listing_fees_request

    assert listing_fees_request(9).key == listing_fees_request(400).key
    assert listing_fees_request(9).action != listing_fees_request(400).action


def test_the_adoption_prefixes_are_distinct_and_survive_a_changing_figure():
    """The migration path for owner actions queued before they carried an identity.

    A keyless row is adopted by matching the opening clause of its action, so two things
    have to hold: no two requests share that opening clause, or a row would be adopted into
    the wrong decision; and no derived figure reaches into it, or the row that made this fix
    necessary would fail to match its own replacement.
    """
    from brambleloop.launch import access, readiness as rd
    from brambleloop.runtime.release import ADOPT_PREFIX

    # Discovered rather than listed. Build 2 adds capability requests to this set, and a
    # hand-written list is a guard that stops guarding the moment somebody adds the eighth
    # request and does not think of this test.
    statics = [v for v in vars(rd).values() if isinstance(v, rd.OwnerRequest)]
    requests = statics + [rd.listing_fees_request(16)] + access.owner_requests({})
    assert len(requests) >= 9, [r.key for r in requests]
    prefixes = [r.action[:ADOPT_PREFIX] for r in requests]
    assert len(set(prefixes)) == len(prefixes), prefixes
    assert all(len(p) == ADOPT_PREFIX for p in prefixes), prefixes

    # The one request whose wording moves must keep its opening clause fixed.
    assert (rd.listing_fees_request(1).action[:ADOPT_PREFIX]
            == rd.listing_fees_request(4000).action[:ADOPT_PREFIX])

    # And the exact row production was holding when this was written must be adopted, not
    # duplicated: that row is the reason a full-text match was not enough.
    queued_before_the_fix = (
        "Confirm you accept Etsy's listing fees for the opening catalogue: US$0.20 per "
        "listing for 4 months, so about US$1.80 (CA$2.50) for nine listings, plus 6.5% "
        "transaction fee and payment processing on each sale.")
    assert (queued_before_the_fix[:ADOPT_PREFIX]
            == rd.listing_fees_request(16).action[:ADOPT_PREFIX])


def test_an_owner_action_queued_before_it_had_an_identity_is_adopted_not_duplicated():
    """The upgrade path, against the exact shape production was in.

    Production held seven owner actions queued before `requirement_key` existed, one of
    which -- the fee approval -- had since changed its wording because the figure now comes
    from the catalogue. Matching on full text adopts the six unchanged rows and adds an
    eighth beside the one that moved, which is the duplicate this whole fix exists to
    prevent.

    Driven by its own worker against its own database rather than the shared deployment
    surface: the readiness job is what is under test, so the test should not also be testing
    whether somebody else's worker is free.
    """
    import tempfile

    from sqlalchemy import select

    from brambleloop.agents.registry import Registry
    from brambleloop.core.models import OwnerAction
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime import pipeline  # noqa: F401 - registers the handlers
    from brambleloop.runtime.worker import Worker

    stale_fee = (
        "Confirm you accept Etsy's listing fees for the opening catalogue: US$0.20 per "
        "listing for 4 months, so about US$1.80 (CA$2.50) for nine listings, plus 6.5% "
        "transaction fee and payment processing on each sale.")

    tmp = tempfile.mkdtemp()
    db = Database(f"sqlite:///{tmp}/adopt.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    _stock(db)

    def run_readiness(key: str) -> None:
        JobQueue(db).enqueue("orchestrator", "launch.readiness", {}, idempotency_key=key)
        worker = Worker(db, "adopt-worker")
        for _ in range(200):
            if not worker.run_once():
                break

    # C-80 (#54): the requests that open live Etsy (the fee approval among them) are withheld
    # while any launch-package item is still ours to build -- see
    # test_live_etsy_asks_are_withheld_while_the_launch_package_is_ours_to_build. `_stock`
    # builds the package, so the fee request is queued here with that gate live.
    _adoption_round_trip(db, run_readiness, stale_fee)


def _adoption_round_trip(db, run_readiness, stale_fee) -> None:
    from brambleloop.core.models import OwnerAction

    run_readiness("adopt-1")
    with db.session() as s:
        rows = list(s.scalars(select(OwnerAction)))
        assert rows, "the readiness job queued nothing"
        assert all(r.requirement_key for r in rows), \
            [r.action[:50] for r in rows if not r.requirement_key]
        # Put the queue back into the pre-upgrade shape: no identities, and the fee row
        # carrying the wording it had before the figure was derived.
        ids = sorted(r.id for r in rows)
        for row in rows:
            if row.requirement_key == "listing_fees":
                row.action = stale_fee
            row.requirement_key = ""

    run_readiness("adopt-2")
    with db.session() as s:
        after = list(s.scalars(select(OwnerAction)))

    assert sorted(a.id for a in after) == ids, (
        "owner actions were duplicated or replaced across the upgrade instead of adopted",
        len(ids), len(after))
    assert all(a.requirement_key for a in after), \
        [a.action[:50] for a in after if not a.requirement_key]
    fee = [a for a in after if a.requirement_key == "listing_fees"]
    assert len(fee) == 1, [f.action[:60] for f in fee]
    assert fee[0].action != stale_fee, "the adopted row kept its stale figure"

def test_live_etsy_asks_are_withheld_while_the_launch_package_is_ours_to_build():
    """#54 (C-80 defect 10) through the worker: "before asking the owner to open/connect live
    Etsy operations, require ..." -- so a company that has drafted its listings and built no
    package yet is not allowed to ask the owner for the shop, the payout, the fees or the
    phase, and the assessment says which package items held them. Once the package exists
    (the same rows the chain's stages write), the asks go out.
    """
    from brambleloop.agents.registry import Registry
    from brambleloop.core.models import AuditLog, OwnerAction
    from brambleloop.launch.readiness import LAUNCH_PACKAGE_KEYS, OPENS_LIVE_ETSY_KEYS
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime import pipeline  # noqa: F401 - registers the handlers
    from brambleloop.runtime.worker import Worker

    tmp = tempfile.mkdtemp()
    db = Database(f"sqlite:///{tmp}/withheld.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    _stock(db, package=False)

    def run_readiness(key: str) -> dict:
        JobQueue(db).enqueue("orchestrator", "launch.readiness", {}, idempotency_key=key)
        worker = Worker(db, "withheld-worker")
        for _ in range(200):
            if not worker.run_once():
                break
        with db.session() as s:
            row = s.scalars(select(AuditLog).where(AuditLog.action == "launch.assessed")
                            .order_by(AuditLog.id.desc())).first()
            assert row is not None, "the readiness job assessed nothing"
            return dict(row.detail)

    assessed = run_readiness("withheld-1")
    with db.session() as s:
        queued = {a.requirement_key for a in s.scalars(select(OwnerAction))}
    assert queued, "the readiness job queued nothing"
    assert not (queued & OPENS_LIVE_ETSY_KEYS), (
        "a live-Etsy request was queued while the launch package is still ours to build",
        sorted(queued & OPENS_LIVE_ETSY_KEYS))
    blocked = set(assessed["launch_package_blocked"])
    assert blocked and blocked <= LAUNCH_PACKAGE_KEYS, assessed
    assert {"support_knowledge", "launch_calendar", "rollback_plan"} <= blocked, blocked
    assert set(assessed["owner_requests_withheld_until_package_ready"]) == OPENS_LIVE_ETSY_KEYS

    # the package gets built (the same rows the chain's stages write) and the asks go out
    _package(db, _catalogue_slugs(MIN_LISTINGS_TO_OPEN))
    assessed = run_readiness("withheld-2")
    assert assessed["launch_package_blocked"] == [], assessed
    assert assessed["owner_requests_withheld_until_package_ready"] == []
    with db.session() as s:
        queued = {a.requirement_key for a in s.scalars(select(OwnerAction))}
    assert OPENS_LIVE_ETSY_KEYS <= queued, sorted(queued)


def test_a_closer_may_only_close_what_it_opens():
    """It tidied away the canonical-model approval on the run after the pack passed.

    The readiness assessment is not the only thing that writes to the owner's queue: the
    reference-pack build raises `canonical_model_approval`, the tournament raises
    `canonical_model_selection`, the image benchmark raises its budget row, and
    `ops/funding.py` raises the provider-balance row. To the assessment every one of those
    is a key it did not generate, which is indistinguishable from a request that has been
    satisfied -- so it closed them.

    The result was silent and complete: the pack sat ready on all nine of its conditions,
    the owner was not asked to approve the identity, and nothing anywhere reported a
    problem. One subsystem tidying away another subsystem's question, in the name of not
    asking twice.
    """
    import tempfile

    from sqlalchemy import select

    from brambleloop.agents.registry import Registry
    from brambleloop.core.db import Database
    from brambleloop.core.models import OwnerAction
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime import pipeline  # noqa: F401 - registers the handlers
    from brambleloop.runtime.release import NOT_THE_READINESS_ASSESSMENTS_TO_CLOSE
    from brambleloop.runtime.worker import Worker

    tmp = tempfile.mkdtemp()
    db = Database(f"sqlite:///{tmp}/closer.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    _stock(db)

    with db.session() as s:
        for key in sorted(NOT_THE_READINESS_ASSESSMENTS_TO_CLOSE):
            s.add(OwnerAction(
                requirement_key=key, action=f"a question raised by {key}",
                reason="raised by a different subsystem", max_cost_cad=0.0, minutes=5,
                consequence_of_delay="the thing that raised it stays blocked",
                blocks="whatever it blocks"))

    JobQueue(db).enqueue("orchestrator", "launch.readiness", {},
                         idempotency_key="closer-1")
    worker = Worker(db, "closer-worker")
    for _ in range(200):
        if not worker.run_once():
            break

    with db.session() as s:
        rows = {r.requirement_key: r for r in s.scalars(select(OwnerAction))}
        for key in NOT_THE_READINESS_ASSESSMENTS_TO_CLOSE:
            assert key in rows, f"{key} was deleted rather than left alone"
            assert rows[key].done is False, \
                f"the readiness assessment closed {key}, which it does not raise"

    # And it still closes its own, or the queue goes back to only growing.
    assert "etsy_shop" not in NOT_THE_READINESS_ASSESSMENTS_TO_CLOSE


def test_an_owner_action_whose_requirement_is_satisfied_closes_itself():
    """The queue only ever grew, and production was asking for four finished things.

    A request stops being generated the moment its requirement is met -- but the row it
    created stayed open forever. On 2026-09-21 the live queue held ten actions, four of
    which were done: the Etsy shop that exists, the developer app that is working, the model
    key that is spending money, and a benchmark purchase superseded by an approved CA$300
    selection. The owner's standing instruction is "do not ask me to repeat an action
    already completed", and the queue was breaking it on four rows out of ten.
    """
    import tempfile

    from sqlalchemy import select

    from brambleloop.agents.registry import Registry
    from brambleloop.core.models import OwnerAction
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime import pipeline  # noqa: F401 - registers the handlers
    from brambleloop.runtime.worker import Worker

    tmp = tempfile.mkdtemp()
    db = Database(f"sqlite:///{tmp}/close.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    _stock(db)

    def run_readiness(key: str) -> None:
        JobQueue(db).enqueue("orchestrator", "launch.readiness", {}, idempotency_key=key)
        worker = Worker(db, "close-worker")
        for _ in range(200):
            if not worker.run_once():
                break

    run_readiness("close-1")
    with db.session() as s:
        # A row for a requirement this assessment does not ask about: the shape of every
        # action whose capability arrived after it was queued.
        # A3-03: the closer may close only what it owns, on a re-check of its condition.
        # `physical_calibration` is readiness-owned and its ask is withdrawn (owner parked
        # it), so the condition behind the row is cleared and the row must close. A key this
        # assessment does not own must stay open: unknown provenance is not "satisfied".
        s.add(OwnerAction(requirement_key="physical_calibration",
                          action="Do the thing that is now done", reason="it was needed"))
        s.add(OwnerAction(requirement_key="a_requirement_since_satisfied",
                          action="Raised by some other subsystem", reason="it was needed"))

    run_readiness("close-2")
    with db.session() as s:
        stale = s.scalar(select(OwnerAction).where(
            OwnerAction.requirement_key == "physical_calibration"))
        foreign = s.scalar(select(OwnerAction).where(
            OwnerAction.requirement_key == "a_requirement_since_satisfied"))
        still_open = [a.requirement_key for a in s.scalars(
            select(OwnerAction).where(OwnerAction.done == False))]  # noqa: E712

    assert stale.done is True, "an action nobody is asking for any more stayed open"
    assert still_open, "closing swept the queue instead of the satisfied row"
    assert "physical_calibration" not in still_open
    assert foreign.done is False, "readiness closed an action it does not own (A3-03)"


def test_the_owner_is_not_asked_to_crochet_the_calibration_sample():
    """Parked twice by the owner. The requirement stands; the ask is withdrawn.

    These are different claims and the honest state needs both: yardage is still an
    uncalibrated estimate and still blocks every fitted garment, and the owner has said
    twice that they will not be the one who makes the sample. A queue that keeps asking
    teaches its reader to stop opening it.
    """
    import tempfile

    from brambleloop.launch import readiness as rd

    tmp = tempfile.mkdtemp()
    db = Database(f"sqlite:///{tmp}/park.sqlite")
    db.create_all()
    _stock(db)

    report = rd.assess(db, phase="shadow", providers=[], storage_durable=False)
    physical = next(r for r in report.requirements if r.key == "physical_calibration")

    assert physical.ready is False                 # unmet, and still blocking
    # F-071 / F-086: the blocker is the independent tester route, never the owner.
    assert physical.blocked_by == rd.BLOCKED_TESTER
    assert not any(r.key == "physical_calibration" for r in report.blocked_on(rd.BLOCKED_OWNER))
    assert physical.evidence["owner_parked"]["parked_by"] == "owner"
    assert "tester_roster" in physical.evidence["owner_parked"]["the_other_way_through"]
    assert not any(o.key == "physical_calibration" for o in report.owner_requests())


def test_the_benchmark_purchase_ask_points_at_the_selection_and_the_upload_page():
    """It asked for "about ten" into "its own folder under the benchmark library path".

    There is no folder on a phone, the set is chosen rather than approximated, and the
    approved figure is CA$300 rather than the CA$120 this was estimated at before the
    catalogue existed.
    """
    from brambleloop.launch.readiness import BENCHMARK_PURCHASES

    assert BENCHMARK_PURCHASES.max_cost_cad == 300.0
    assert "/ops/teardown" in BENCHMARK_PURCHASES.action
    assert "/api/benchmark-selection" in BENCHMARK_PURCHASES.action
    assert "folder" not in BENCHMARK_PURCHASES.action
    assert "about ten" not in BENCHMARK_PURCHASES.action


def test_no_asset_is_blocked_is_not_true_of_no_assets():
    """A floor nothing can fail, on the launch gate.

    `imagery_truthful` asked whether any asset carried a block reason and passed when none
    did -- which is vacuously true of an empty asset table. Every other requirement here
    already guards its own emptiness with `and bool(listings)`; this one did not, so a
    company with no imagery at all reported its imagery as truthful.
    """
    readiness = assess(_db(), phase="shadow")
    truthful = next(r for r in readiness.requirements if r.key == "imagery_truthful")
    assert not truthful.ready, "no assets passed the 'no asset is blocked' check"
    assert truthful.evidence["assets_on_file"] == 0


def test_the_launch_gate_can_see_the_photographs_and_not_only_the_charts():
    """The disagreement found live on 2026-09-23.

    `listing_imagery` and `imagery_truthful` both reported READY while
    `/api/asset-coverage` reported `listable: 0 of 10`. They count rows in the asset table
    -- charts, schematics, earlier approvals -- and the rendered product photographs are
    audit records those checks cannot see. Two subsystems disagreeing about whether this
    company has listing imagery, with the optimistic one gating launch.
    """
    db = _db()
    _stock(db, photographs=False)

    readiness = assess(db, phase="shadow")
    keys = {r.key for r in readiness.requirements}
    assert "listing_photography" in keys, "nothing in launch readiness reads the renders"

    frames = next(r for r in readiness.requirements if r.key == "listing_imagery")
    photo = next(r for r in readiness.requirements if r.key == "listing_photography")
    assert frames.ready, "the stocked warehouse has its approved frames"
    assert not photo.ready, (
        "approved chart frames were accepted as product photography")
    assert photo.evidence["listable"] == 0
    assert photo.blocked_by == BLOCKED_BUILD


def test_the_photography_requirement_reads_the_same_source_as_the_coverage_endpoint():
    """Reading rather than recomputing is what stops the two drifting apart again."""
    import inspect as _inspect

    from brambleloop.launch import readiness as readiness_mod

    source = _inspect.getsource(readiness_mod.assess)
    assert "owned_photography.coverage" in source, (
        "a second implementation of coverage would disagree with the first one day")


# ---- F-119 / F-120: legacy counts zero; F-175: the unknowns register -----------------------


def _certified(db, slug: str, certificate: dict) -> None:
    with db.session() as s:
        product = Product(slug=slug, title=slug, status="certified")
        s.add(product)
        s.flush()
        s.add(PatternVersion(product_id=product.id, version=VERSION, cir_json={},
                             release_hash="1" * 64, certified=True, certificate=certificate))


def test_a_legacy_certification_counts_zero_toward_launch_until_recertified():
    """F-119: old certification is not current readiness, and the zero is reported, not hidden."""
    from brambleloop.gates.certificate import GAUGE_STANDARD

    db = _db()
    _certified(db, "harvest-table-runner", {"granted": True})            # Build-1, no stamp
    _certified(db, "cloudline-baby-blanket", {"granted": True})          # Launch-0
    _certified(db, "cottage-wall-hanging",
               {"granted": True, "gauge_standard": GAUGE_STANDARD})       # re-certified

    report = assess(db, phase="shadow", providers=[], storage_durable=False)
    depth = next(r for r in report.requirements if r.key == "catalogue_depth").evidence
    assert depth["certified_patterns"] == 2, depth
    assert depth["certified_in_launch_scope"] == 1
    assert depth["certified_legacy_recertified"] == 1
    assert depth["legacy_counted_zero"]["versions"] == 1
    assert depth["legacy_counted_zero"]["slugs"] == ["harvest-table-runner"]
    assert depth["certified_all_including_legacy"] == 3


def test_the_launch_report_names_its_unknowns_and_the_register_is_not_empty_today():
    """F-175: assumptions and unknowns are collected into the report the owner reads."""
    db = _db()
    report = assess(db, phase="shadow", providers=[], storage_durable=False)
    keys = {u["key"] for u in report.unknowns}
    assert report.unknowns, "an empty register with no evidence is not a clean bill"
    assert "physical_calibration" in keys                   # nothing has been crocheted
    assert "uncalibrated_primitives" in keys                # F-074's table, read here
    assert any(k.startswith("etsy_surface:") for k in keys)
    assert any(k.startswith("launch0_make_time:") for k in keys)
    for u in report.unknowns:
        assert u["source"] and u["unknown"] and u["touches"], u
    assert report.to_dict()["unknowns"] == report.unknowns
    assert "Unknowns and assumptions" in render(report)


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
