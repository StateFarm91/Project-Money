"""Offline persistent tests for the stage-D lifestyle edit-base gate."""
from sqlalchemy import select

from brambleloop.core.artifacts import ArtifactStore
from brambleloop.core.db import Database
from brambleloop.visual import image_production as IP
from brambleloop.visual.image_records import ImageCandidate


def test_edit_base_never_uses_failed_or_vetoed_image(tmp_path, monkeypatch):
    from brambleloop.core import artifacts

    monkeypatch.setattr(artifacts, "DEFAULT_DIR", str(tmp_path / "artifacts"))
    db = Database("sqlite:///" + str(tmp_path / "variant.db"), scratch=True)
    db.create_all()
    payload = b"synthetic lifestyle input"
    digest = ArtifactStore().put("test", payload, "image/png", db=db).sha256
    run = IP.run_key("item", "1", "a" * 64)
    with db.session() as session:
        session.add(ImageCandidate(
            sha256=digest, run_key=run, method="autonomous",
            provenance_kind="ai_generated_autonomous", slug="item", version="1",
            release="a" * 64, listing="listing", role="lifestyle",
            technical_status="UNKNOWN", outcome="unverified",
            checks={"product_truth": {"status": "UNKNOWN"}},
        ))
    plan = {"listing": "listing", "roles": [{"role": "lifestyle", "job": "LIFESTYLE",
                                                "generate": True}]}

    def select_base():
        return IP._accepted_lifestyle(db, run, "listing", plan,
                                      slug="item", version="1", release="a" * 64)

    # An unresolved but non-failing image is allowed by the original stage-D spec.
    assert select_base()["data"] == payload
    assert IP._accepted_lifestyle(db, run, "listing", plan, slug="another", version="1",
                                  release="a" * 64) is None
    assert IP._accepted_lifestyle(db, run, "listing", plan, slug="item", version="1",
                                  release="a" * 12) is None
    with db.session() as session:
        row = session.scalar(select(ImageCandidate))
        row.slug = "another"
    assert select_base() is None
    with db.session() as session:
        row = session.scalar(select(ImageCandidate))
        row.slug = "item"
    path = tmp_path / "artifacts" / digest[:2] / digest
    path.write_bytes(b"corrupt")
    assert select_base() is None
    path.write_bytes(payload)
    with db.session() as session:
        row = session.scalar(select(ImageCandidate))
        row.checks = {"product_truth": {"status": "FAIL"}}
    assert select_base() is None
    # A contradictory nested verifier must not be hidden by a PASS outer label.
    from brambleloop.products.vessels import build_basket
    from brambleloop.visual import fidelity

    obscured = fidelity.compare_craft({"fabric_visible_clearly": "false", "craft": "knitting"},
                                     fidelity.expectation(build_basket("small")))
    with db.session() as session:
        row = session.scalar(select(ImageCandidate))
        row.checks = {"product_truth": {"status": "UNKNOWN", "fidelity": {
            "status": "UNKNOWN", "checks": [obscured]}}}
    assert select_base() is None
    # Older verifier results did not record the dedicated edit-base marker.
    legacy = {k: v for k, v in obscured.items() if k != "blocks_variant_input"}
    with db.session() as session:
        row = session.scalar(select(ImageCandidate))
        row.checks = {"product_truth": {"status": "UNKNOWN", "fidelity": {
            "status": "UNKNOWN", "checks": [legacy]}}}
    assert select_base() is None
    with db.session() as session:
        row = session.scalar(select(ImageCandidate))
        row.technical_status = "PASS"
        row.checks = {"product_truth": {"status": "PASS", "fidelity": {
            "status": "FAIL", "checks": []}}}
    assert select_base() is None
    with db.session() as session:
        row = session.scalar(select(ImageCandidate))
        row.checks = {"product_truth": {"status": "PASS"}}
        row.owner_visual_approval = False
    assert select_base() is None
    # A second row for the same bytes must not override an explicit veto.
    with db.session() as session:
        session.add(ImageCandidate(
            sha256=digest, run_key=run, method="autonomous",
            provenance_kind="ai_generated_autonomous", slug="item", version="1",
            release="a" * 64, listing="listing", role="lifestyle",
            technical_status="PASS", outcome="accepted", publishable=True,
            checks={"product_truth": {"status": "PASS"}},
        ))
    assert select_base() is None
