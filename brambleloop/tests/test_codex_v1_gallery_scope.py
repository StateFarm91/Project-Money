"""Offline gallery selection must keep controlled experiments isolated."""
from brambleloop.core.db import Database
from brambleloop.visual import image_production as IP, shot_plans as SP
from brambleloop.visual.image_records import ImageCandidate, ImageProductionRun


def test_production_card_does_not_borrow_controlled_run_candidate(tmp_path):
    db = Database("sqlite:///" + str(tmp_path / "gallery.db"), scratch=True)
    db.create_all()
    listing, slug, version, release = "cloudline-baby-blanket", "item", "1", "a" * 64
    run = IP.run_key(slug, version, release)
    plan = SP.campaign_plan(listing)
    role = next(r["role"] for r in plan["roles"] if r.get("generate"))
    with db.session() as session:
        session.add(ImageProductionRun(run_key=run, slug=slug, version=version,
                                       release=release, listing=listing))
        session.add(ImageCandidate(
            sha256="b" * 64, run_key=run + "#controlled", method="autonomous",
            provenance_kind="ai_generated_autonomous", slug=slug, version=version,
            release=release, listing=listing, role=role, technical_status="PASS",
            outcome="accepted", checks={}, publishable=False,
        ))
    view = IP.readiness(db, listing, run_key_=run, plan=plan)
    entry = next(r for r in view["roles"] if r["role"] == role)
    assert entry.get("candidate") is None
    # The general production dashboard must not select an experiment either.
    dashboard = IP.readiness(db, listing, plan=plan)
    assert next(r for r in dashboard["roles"] if r["role"] == role).get("candidate") is None
    # A matching owner upload remains available to production only.
    with db.session() as session:
        session.add(ImageCandidate(
            sha256="c" * 64, run_key="", method="owner_submitted",
            provenance_kind="ai_generated_owner_submitted", slug=slug, version=version,
            release=release, listing=listing, role=role, technical_status="UNKNOWN",
            outcome="unverified", checks={}, publishable=False,
        ))
    view = IP.readiness(db, listing, run_key_=run, plan=plan)
    assert next(r for r in view["roles"] if r["role"] == role)["candidate"]["sha256"] == "c" * 64
    # A different experiment must neither borrow the first one nor production's owner upload.
    other = run + "#other"
    with db.session() as session:
        session.add(ImageProductionRun(run_key=other, slug=slug, version=version,
                                       release=release, listing=listing))
    view = IP.readiness(db, listing, run_key_=other, plan=plan)
    assert next(r for r in view["roles"] if r["role"] == role).get("candidate") is None


def test_missing_run_does_not_fall_back_to_an_unrelated_gallery(tmp_path):
    db = Database("sqlite:///" + str(tmp_path / "missing.db"), scratch=True)
    db.create_all()
    listing = "cloudline-baby-blanket"
    plan = SP.campaign_plan(listing)
    role = next(r["role"] for r in plan["roles"] if r.get("generate"))
    with db.session() as session:
        session.add(ImageCandidate(
            sha256="d" * 64, run_key="", method="owner_submitted",
            provenance_kind="ai_generated_owner_submitted", slug="item", version="1",
            release="a" * 64, listing=listing, role=role, technical_status="UNKNOWN",
            outcome="unverified", checks={}, publishable=False,
        ))
    view = IP.readiness(db, listing, run_key_="missing", plan=plan)
    assert next(r for r in view["roles"] if r["role"] == role).get("candidate") is None
    assert not view["gallery_ready"]
    assert any("unavailable production identity" in b for b in view["publication_blockers"])


def test_unscoped_dashboard_holds_mixed_production_release_identities(tmp_path):
    db = Database("sqlite:///" + str(tmp_path / "mixed.db"), scratch=True)
    db.create_all()
    listing = "cloudline-baby-blanket"
    plan = SP.campaign_plan(listing)
    role = next(r["role"] for r in plan["roles"] if r.get("generate"))
    with db.session() as session:
        for version in ("1", "2"):
            session.add(ImageCandidate(
                sha256="e" * 64, run_key="", method="owner_submitted",
                provenance_kind="ai_generated_owner_submitted", slug="item", version=version,
                release="a" * 64, listing=listing, role=role, technical_status="UNKNOWN",
                outcome="unverified", checks={}, publishable=False,
            ))
    view = IP.readiness(db, listing, plan=plan)
    assert next(r for r in view["roles"] if r["role"] == role).get("candidate") is None
    assert not view["gallery_ready"]
    assert any("ambiguous or unavailable production identity" in b for b in view["publication_blockers"])


def test_gallery_with_failed_set_check_is_not_reported_ready(tmp_path):
    db = Database("sqlite:///" + str(tmp_path / "incomplete.db"), scratch=True)
    db.create_all()
    listing = "cloudline-baby-blanket"
    plan = SP.campaign_plan(listing)
    # A one-frame plan can have a disclosed detail but no hero.
    plan = {**plan, "roles": [next(r for r in plan["roles"] if r["role"] == "detail")]}
    view = IP.readiness(db, listing, plan=plan)
    assert not view["set_check"]["ok"]
    assert not view["gallery_ready"]
