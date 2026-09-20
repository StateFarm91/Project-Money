"""Not misled before the purchase, not stranded after it.

v1.4.3 requirements 36, 41, 42 — the same customer at three moments, and all three failures
are quiet. Nobody complains; they refund, or they do not come back.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.commerce import buyer_trust as B  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402


def _db() -> Database:
    tmp = tempfile.mkdtemp()
    db = Database(f"sqlite:///{tmp}/trust.sqlite")
    db.create_all()
    return db


# ---- #36: proof and promise are different pictures ------------------------


def test_a_testers_photograph_needs_recorded_consent_before_it_is_a_record():
    """The same error as using a competitor's image, arriving from the friendly direction."""
    try:
        B.record_image("hero", "tester_photo", pattern_version="1.0.0", yarn="DK")
    except B.TrustRefused as e:
        assert "arriving from the friendly direction" in str(e)
    else:
        raise AssertionError("a third-party photo was recorded with no consent basis")

    try:
        B.record_image("hero", "customer_photo", pattern_version="1.0.0",
                       consent_basis="written_permission", consent_ref="  ", yarn="DK")
    except B.TrustRefused as e:
        assert "the basis is an assertion" in str(e)
    else:
        raise AssertionError("a consent basis was accepted with nowhere recorded")


def test_a_photograph_of_a_real_object_records_the_yarn_it_was_made_in():
    try:
        B.record_image("hero", "studio_photo", pattern_version="1.0.0")
    except B.TrustRefused as e:
        assert "choosing against this picture" in str(e)
    else:
        raise AssertionError("a physical photo was recorded with no yarn")


def test_an_image_without_a_pattern_version_cannot_be_invalidated_by_a_correction():
    try:
        B.record_image("hero", "twin_render", pattern_version="")
    except B.TrustRefused as e:
        assert "which images are now wrong" in str(e)
    else:
        raise AssertionError("an image was recorded with no version")


def test_a_gallery_of_renders_is_honest_and_is_not_proof():
    renders = [B.record_image(f"r{i}", "twin_render", pattern_version="1.0.0")
               for i in range(3)]
    result = B.gallery_proof(renders)
    assert result["has_physical_proof"] is False
    assert "honest and it is not proof" in result["note"]

    with_proof = renders + [B.record_image("p", "studio_photo", pattern_version="1.0.0",
                                           yarn="Drops Paris DK")]
    assert B.gallery_proof(with_proof)["has_physical_proof"] is True
    assert B.gallery_proof(with_proof)["proof_images"] == 1


def test_a_gallery_mixing_pattern_versions_says_so():
    images = [B.record_image("a", "twin_render", pattern_version="1.0.0"),
              B.record_image("b", "twin_render", pattern_version="1.1.0")]
    assert B.gallery_proof(images)["mixed_versions"] is True


# ---- #41: the misunderstanding that becomes a refund ----------------------


def test_the_digital_disclosure_belongs_in_the_title():
    """A buyer who thinks they are buying a blanket does not read the description."""
    buried = B.disclosure_check({k: ["description"] for k in B.REQUIRED_DISCLOSURES})
    assert buried["complete"] is False
    assert buried["misplaced"][0]["disclosure"] == B.TITLE_CRITICAL
    assert "most preventable one in the category" in buried["misplaced"][0]["why"]

    surfaced = {k: ["description"] for k in B.REQUIRED_DISCLOSURES}
    surfaced[B.TITLE_CRITICAL] = ["title", "first_screen", "description"]
    assert B.disclosure_check(surfaced)["complete"] is True


def test_every_required_disclosure_is_named_and_a_missing_one_is_reported():
    partial = B.disclosure_check({"digital_not_finished": ["title"]})
    assert partial["complete"] is False
    missing = {m["disclosure"] for m in partial["missing"]}
    assert {"skill_level", "required_materials", "terminology", "delivery",
            "support"} == missing

    try:
        B.disclosure_check({"vibes": ["title"]})
    except B.TrustRefused as e:
        assert "not required disclosures" in str(e)
    else:
        raise AssertionError("an invented disclosure was accepted")


def test_confusion_is_a_listing_defect_rather_than_a_cost_of_doing_business():
    db = _db()
    result = B.confusion_rate(db)
    assert result["measurable"] is False
    assert "built for rather than measured from" in result["reason"]


# ---- #42: the buyer runs an old build -------------------------------------


def test_the_order_to_version_map_is_written_at_sale_time():
    """It cannot be reconstructed: once the listing moves on, nobody knows who holds what."""
    versions = B.VersionMap()
    versions.record_sale(order_ref="E-1", product_slug="hearthside-throw", version="1.0.0")
    versions.record_sale(order_ref="E-2", product_slug="hearthside-throw", version="1.0.0")
    versions.record_sale(order_ref="E-3", product_slug="hearthside-throw", version="1.1.0")
    versions.record_sale(order_ref="E-4", product_slug="other-thing", version="1.0.0")

    affected = versions.affected_by(product_slug="hearthside-throw",
                                    corrected_from=("1.0.0",))
    assert [r["order_ref"] for r in affected] == ["E-1", "E-2"]

    try:
        versions.record_sale(order_ref="", product_slug="x", version="1.0.0")
    except B.TrustRefused as e:
        assert "support cannot answer it" in str(e)
    else:
        raise AssertionError("a sale was recorded with no order reference")


def test_a_correction_notice_is_prepared_and_never_sent():
    versions = B.VersionMap()
    versions.record_sale(order_ref="E-1", product_slug="hearthside-throw", version="1.0.0")
    affected = versions.affected_by(product_slug="hearthside-throw",
                                    corrected_from=("1.0.0",))

    notice = B.correction_notice(
        product_slug="hearthside-throw", affected=affected, from_versions=("1.0.0",),
        to_version="1.0.1",
        what_changed=("row 42 of the border repeated one stitch too many, so the edge pulled "
                      "on one side"))
    assert notice["sent"] is False
    assert "owner-gated and refused in shadow mode" in notice["why_not_sent"]
    assert notice["affected_orders"] == ["E-1"]
    assert "1.0.0" in notice["body"]

    try:
        B.correction_notice(product_slug="x", affected=affected, from_versions=("1.0.0",),
                            to_version="1.0.1", what_changed="fixed a thing")
    except B.TrustRefused as e:
        assert "makes the buyer ask" in str(e)
    else:
        raise AssertionError("a vague correction notice was prepared")


# --- #258: the gallery, and the version an entry belongs to ---------------------------------

def test_a_photograph_of_an_older_version_is_real_and_proof_of_a_different_object():
    """It is the most believable wrong thing on the page, because it is real."""
    old = B.record_image("i1", "customer_photo", pattern_version="1.0.0",
                         consent_basis="written_permission", consent_ref="c-1",
                         yarn="worsted", colourway="ember")
    out = B.customer_gallery([old], selling_version="1.2.0")
    entry = out["entries"][0]
    assert entry["superseded"] is True
    assert "proof of a different object" in entry["why"]
    assert out["usable"] == 0


def test_the_colourway_is_what_a_browser_is_choosing_from():
    """The yarn is already required at construction; nothing had required the colour."""
    no_colour = B.record_image("i2", "customer_photo", pattern_version="1.2.0",
                               consent_basis="written_permission", consent_ref="c-2",
                               yarn="worsted")
    out = B.customer_gallery([no_colour], selling_version="1.2.0")
    assert out["entries"][0]["missing_notes"] == ["colourway"]
    assert out["usable"] == 0
    assert "colourway" in B.GALLERY_NOTES and "yarn" not in B.GALLERY_NOTES


def test_a_complete_current_entry_is_usable_proof():
    good = B.record_image("i3", "customer_photo", pattern_version="1.2.0",
                          consent_basis="written_permission", consent_ref="c-3",
                          yarn="worsted", colourway="soot")
    out = B.customer_gallery([good], selling_version="1.2.0")
    assert out["usable"] == 1
    assert out["entries"][0]["why"] == ""


def test_a_record_that_did_not_come_through_record_image_is_still_refused():
    """A second line rather than the line: record_image already refuses this."""
    raw = B.ImageRecord("i4", "customer_photo", "1.2.0",
                        consent_basis="written_permission", yarn="worsted", colourway="soot")
    out = B.customer_gallery([raw], selling_version="1.2.0")
    assert [r["ref"] for r in out["refused"]] == ["i4"]
    assert "most public place to be wrong" in out["refused"][0]["why"]


def test_an_empty_gallery_is_empty_rather_than_thin():
    out = B.customer_gallery([])
    assert out["entries"] == [] and out["refused"] == []
    assert "empty rather than thin" in out["note"]


def test_a_gallery_added_to_every_listing_measures_the_month_it_was_added():
    out = B.proof_lift(design="holdout")
    assert out["measurable"] is False
    assert "not the gallery" in out["why"]


def test_the_design_decides_what_the_lift_may_be_called():
    causal = B.proof_lift(design="holdout", with_gallery={"conversion": 0.03},
                          without_gallery={"conversion": 0.02})
    weak = B.proof_lift(design="pre_post", with_gallery={"conversion": 0.03},
                        without_gallery={"conversion": 0.02})
    assert causal["lift"] == 0.5 and causal["causal"] is True
    assert weak["causal"] is False
    assert "cannot separate the gallery from the week" in weak["claim"]


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
