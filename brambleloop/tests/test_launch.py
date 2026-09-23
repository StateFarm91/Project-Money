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

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    ContentPiece, Listing, ListingAsset, PatternVersion, PhysicalTest, Product,
)
from brambleloop.launch.readiness import (  # noqa: E402
    BLOCKED_BUILD, BLOCKED_INTEGRATION, BLOCKED_OWNER, MIN_APPROVED_ASSETS,
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


def _stock(db, listings: int = MIN_LISTINGS_TO_OPEN, frames: int = MIN_APPROVED_ASSETS,
           content_each: int = 1, photographs: bool = True) -> None:
    """A warehouse that looks like a company that has done its half of the work.

    `photographs=False` is the live situation of 2026-09-23: approved chart frames on every
    listing and not one product photograph that cleared its floors.
    """
    from brambleloop.agents.registry import Registry
    from brambleloop.products.builder import for_slug
    from brambleloop.publish import owned_photography as _op

    slugs = _catalogue_slugs(listings)
    if photographs:
        for slug in slugs:
            cir = for_slug(slug)
            Registry(db).audit("publishing", _op.ACTION, detail={
                "made": True, "method_version": _op.METHOD_VERSION, "slug": slug,
                "version": cir.version, "usable_as_listing_asset": True,
                "verdict": "clear"})

    with db.session() as s:
        for i, slug in enumerate(slugs):
            product = Product(slug=slug, title=f"Product {i}", status="certified")
            s.add(product)
            s.flush()
            s.add(PatternVersion(product_id=product.id, version="1.0.0",
                                 cir_json={}, release_hash="0" * 64, certified=True,
                                 certificate={"granted": True}))
            s.add(Listing(product_slug=slug, version="1.0.0", title=f"Product {i}",
                          description="copy", price_cad=9.5, state="draft"))
            for position in range(frames):
                s.add(ListingAsset(product_slug=slug, version="1.0.0", position=position,
                                   asset_class="INFOGRAPHIC", role="frame",
                                   sha256="a" * 64, approved=True))
            for n in range(content_each):
                s.add(ContentPiece(product_slug=slug, channel="article",
                                   title=f"piece {n}", body="body"))


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
    db = _db()
    _stock(db)
    readiness = assess(db, phase="shadow")
    assert not readiness.buildable, [r.key for r in readiness.buildable]
    remaining = {r.blocked_by for r in readiness.outstanding}
    assert remaining <= {BLOCKED_OWNER, BLOCKED_INTEGRATION}, remaining


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
    assert "Nothing. Every remaining requirement needs a person or an account." in text



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
        s.add(OwnerAction(requirement_key="a_requirement_since_satisfied",
                          action="Do the thing that is now done", reason="it was needed"))

    run_readiness("close-2")
    with db.session() as s:
        stale = s.scalar(select(OwnerAction).where(
            OwnerAction.requirement_key == "a_requirement_since_satisfied"))
        still_open = [a.requirement_key for a in s.scalars(
            select(OwnerAction).where(OwnerAction.done == False))]  # noqa: E712

    assert stale.done is True, "an action nobody is asking for any more stayed open"
    assert still_open, "closing swept the queue instead of the satisfied row"
    assert "a_requirement_since_satisfied" not in still_open


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
    assert physical.blocked_by == rd.BLOCKED_OWNER
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
