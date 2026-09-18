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


def _stock(db, listings: int = MIN_LISTINGS_TO_OPEN, frames: int = MIN_APPROVED_ASSETS,
           content_each: int = 1) -> None:
    """A warehouse that looks like a company that has done its half of the work."""
    with db.session() as s:
        for i in range(listings):
            slug = f"product-{i}"
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
    """The one owner action the system can watch being satisfied."""
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
    assert len(after.owner_requests()) == len(before.owner_requests()) - 1


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
