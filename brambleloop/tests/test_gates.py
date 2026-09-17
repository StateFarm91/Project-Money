"""Gate C (asset truth), Gate E (customer experience) and the release certificate."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.cir.twin import build_twin  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.gates.asset_truth import (  # noqa: E402
    Asset, AssetClass, Claims, Provenance, check_assets,
)
from brambleloop.gates.certificate import certify  # noqa: E402
from brambleloop.gates.incidents import (  # noqa: E402
    DefectReport, IncidentTracker, SupportCannotPatchPatterns, apply_support_patch,
)
from brambleloop.gates.policy import ListingDraft, check_listing  # noqa: E402
from tests import fixtures  # noqa: E402


def _twin_for(cir):
    return build_twin(cir, compile_cir(cir))


def good_provenance() -> Provenance:
    return Provenance(source="twin", created_by="asset_truth", tool="digital_twin@1")


def hero(**kw) -> Asset:
    base = dict(
        asset_id="hero-1",
        asset_class=AssetClass.DIGITAL_TWIN_RENDER,
        provenance=good_provenance(),
        is_hero=True,
    )
    base.update(kw)
    return Asset(**base)


def codes(findings):
    return {f.code for f in findings}


# ---- Gate C --------------------------------------------------------------


def test_clean_asset_passes():
    cir = fixtures.good_mosaic_panel()
    a = hero(depicts_stitches=["sc", "dc"], depicts_colors=["forest", "wine"])
    assert check_assets([a], cir, _twin_for(cir)) == []


def test_asset_depicting_absent_motif_is_rejected():
    """Gate C: 'a listing image containing a motif absent from CIR is rejected'."""
    cir = fixtures.good_mosaic_panel()
    a = hero(depicts_stitches=["sc", "dc", "tr"])  # pattern never works a treble
    assert "ASSET_MOTIF_ABSENT" in codes(check_assets([a], cir, _twin_for(cir)))


def test_asset_depicting_absent_colour_is_rejected():
    cir = fixtures.good_mosaic_panel()
    a = hero(depicts_colors=["forest", "gold"])
    assert "ASSET_COLOR_ABSENT" in codes(check_assets([a], cir, _twin_for(cir)))


def test_unsupported_size_claim_is_blocked():
    """Gate C: 'unsupported size claims are blocked'. Twin says 25cm wide."""
    cir = fixtures.good_mosaic_panel()
    a = hero(claims=Claims(finished_width_cm=180.0))
    assert "CLAIM_SIZE_UNSUPPORTED" in codes(check_assets([a], cir, _twin_for(cir)))


def test_size_label_must_match_computed_dimensions():
    cir = fixtures.good_mosaic_panel()
    a = hero(claims=Claims(size_label="queen"))
    assert "CLAIM_SIZE_LABEL_UNSUPPORTED" in codes(check_assets([a], cir, _twin_for(cir)))


def test_small_size_drift_within_tolerance_is_accepted():
    cir = fixtures.good_mosaic_panel()
    a = hero(claims=Claims(finished_width_cm=26.0))  # twin says 25.0; 4% off
    assert "CLAIM_SIZE_UNSUPPORTED" not in codes(check_assets([a], cir, _twin_for(cir)))


def test_unsupported_material_claim_is_blocked():
    cir = fixtures.good_sphere()  # declares worsted cotton only
    a = hero(claims=Claims(materials=["mohair"]))
    assert "CLAIM_MATERIAL_UNSUPPORTED" in codes(check_assets([a], cir, _twin_for(cir)))


def test_missing_provenance_is_rejected():
    """Gate C: 'asset provenance is stored'."""
    cir = fixtures.good_mosaic_panel()
    a = hero(provenance=Provenance(source="", created_by=""))
    assert "ASSET_PROVENANCE" in codes(check_assets([a], cir, _twin_for(cir)))


def test_ai_concept_as_undisclosed_hero_is_rejected():
    """An AI concept posing as a photo of a finished object is a misrepresentation."""
    cir = fixtures.good_mosaic_panel()
    a = hero(asset_class=AssetClass.AI_LIFESTYLE_CONCEPT,
             provenance=Provenance(source="generator", created_by="visual_director",
                                   tool="image-model", prompt_hash="abc123"))
    assert "ASSET_UNDISCLOSED_CONCEPT" in codes(check_assets([a], cir, _twin_for(cir)))


def test_ai_concept_disclosed_is_allowed():
    cir = fixtures.good_mosaic_panel()
    a = hero(asset_class=AssetClass.AI_LIFESTYLE_CONCEPT,
             provenance=Provenance(source="generator", created_by="visual_director",
                                   tool="image-model", prompt_hash="abc123"),
             disclosed_as_illustration=True)
    assert "ASSET_UNDISCLOSED_CONCEPT" not in codes(check_assets([a], cir, _twin_for(cir)))


def test_render_cannot_masquerade_as_a_photograph():
    cir = fixtures.good_mosaic_panel()
    a = hero(asset_class=AssetClass.PHYSICAL_PRODUCT_PHOTO,
             provenance=Provenance(source="generator", created_by="visual_director"))
    assert "ASSET_CLASS_MISMATCH" in codes(check_assets([a], cir, _twin_for(cir)))


def test_listing_needs_exactly_one_hero():
    cir = fixtures.good_mosaic_panel()
    twin = _twin_for(cir)
    assert "ASSET_NO_HERO" in codes(check_assets([hero(is_hero=False)], cir, twin))
    two = [hero(asset_id="a"), hero(asset_id="b")]
    assert "ASSET_MULTIPLE_HEROES" in codes(check_assets(two, cir, twin))


# ---- Policy --------------------------------------------------------------


def test_policy_blocks_unsupported_claims_and_ip():
    d = ListingDraft(title="Crochet Pattern", price_cad=9.99,
                     description="Guaranteed fit. A Disney inspired blanket. AI assisted.")
    c = codes(check_listing(d))
    assert "POLICY_UNSUPPORTED_CLAIM" in c and "POLICY_IP_RISK" in c


def test_policy_blocks_perpetual_sale_and_bad_compare_at():
    d = ListingDraft(title="X", description="AI assisted", price_cad=10.0,
                     compare_at_cad=8.0, is_on_sale=True, sale_days_running=120)
    c = codes(check_listing(d))
    assert "POLICY_PERPETUAL_SALE" in c and "POLICY_BAD_COMPARE_AT" in c


def test_policy_enforces_etsy_limits():
    d = ListingDraft(title="T" * 141, description="AI assisted", price_cad=5.0,
                     tags=[f"tag{i}" for i in range(14)] + ["a" * 21])
    c = codes(check_listing(d))
    assert {"POLICY_TITLE_LENGTH", "POLICY_TAG_COUNT", "POLICY_TAG_LENGTH"} <= c


def test_clean_listing_passes_policy():
    d = ListingDraft(title="Mosaic Crochet Blanket Pattern PDF with Video",
                     description="A two-colour mosaic throw. Made with AI assistance in "
                                 "drafting and checking.",
                     tags=["crochet pattern", "mosaic blanket"], price_cad=11.99)
    assert not [f for f in check_listing(d) if f.severity == "ERROR"]


# ---- Release certificate -------------------------------------------------


def test_certificate_granted_for_a_clean_release():
    cir = fixtures.good_mosaic_panel()
    cert = certify(
        cir,
        assets=[hero(depicts_stitches=["sc", "dc"], depicts_colors=["forest", "wine"],
                     claims=Claims(finished_width_cm=25.0))],
        listing=ListingDraft(title="Mosaic Crochet Blanket Pattern",
                             description="Two-colour mosaic throw, AI assisted drafting.",
                             tags=["crochet pattern"], price_cad=11.99),
    )
    assert cert.granted, cert.blocking_reasons
    assert cert.release_hash and len(cert.release_hash) == 64
    assert cert.pattern_text and "rep from * to end" in cert.pattern_text
    assert cert.twin_summary["width_cm"] == 25.0
    assert "reverse" in cert.stages_run


def test_broken_pattern_never_gets_a_certificate():
    """The deliberately broken fixture must be refused publication."""
    cert = certify(fixtures.broken_stitch_count())
    assert not cert.granted
    assert cert.release_hash is None
    assert any(f.code == "COUNT_MISMATCH" for f in cert.errors)


def test_misleading_asset_blocks_an_otherwise_valid_release():
    cir = fixtures.good_mosaic_panel()
    cert = certify(cir, assets=[hero(claims=Claims(size_label="king"))])
    assert not cert.granted
    assert "CLAIM_SIZE_LABEL_UNSUPPORTED" in {f.code for f in cert.errors}


def test_class_c_pattern_requires_a_physical_test():
    cir = fixtures.good_sphere()
    cir.risk_class = "C"
    blocked = certify(cir)
    assert not blocked.granted
    assert "PHYSICAL_TEST_REQUIRED" in {f.code for f in blocked.errors}

    passed = certify(cir, physical_test_passed=True)
    assert passed.granted, passed.blocking_reasons


def test_release_hash_changes_when_the_pattern_changes():
    a = certify(fixtures.good_mosaic_panel())
    cir = fixtures.good_mosaic_panel()
    cir.components[0].rows[2].declared_count = 40  # same value, no structural change
    b = certify(cir)
    assert a.release_hash == b.release_hash

    cir2 = fixtures.good_mosaic_panel()
    cir2.version = "1.0.1"
    assert certify(cir2).release_hash != a.release_hash


# ---- Gate E --------------------------------------------------------------


def _db():
    db = Database("sqlite://")
    db.create_all()
    return db


def test_repeated_defect_reports_correlate_into_one_incident():
    """Gate E: 'repeated defect reports correlate into one incident'."""
    t = IncidentTracker(_db())
    for i in range(3):
        inc = t.report(DefectReport("evergreen", "1.0.0", "panel", 14, f"cust-{i}",
                                    "stitch count does not work out at row 14"))
    assert inc.report_count == 3
    assert len(t.open_incidents("evergreen")) == 1
    assert inc.severity == "P1"


def test_escalated_incident_halts_publication():
    """Gate E: 'P0/P1 incident can halt publication workflow'."""
    t = IncidentTracker(_db())
    assert t.publication_halted("evergreen") is False
    for i in range(3):
        t.report(DefectReport("evergreen", "1.0.0", "panel", 14, f"cust-{i}", "row 14 wrong"))
    assert t.publication_halted("evergreen") is True


def test_distinct_problems_do_not_merge():
    t = IncidentTracker(_db())
    t.report(DefectReport("evergreen", "1.0.0", "panel", 14, "a", "row 14"))
    t.report(DefectReport("evergreen", "1.0.0", "panel", 30, "b", "row 30"))
    assert len(t.open_incidents("evergreen")) == 2


def test_a_single_report_does_not_halt_publication():
    t = IncidentTracker(_db())
    t.report(DefectReport("evergreen", "1.0.0", "panel", 14, "a", "confused at row 14"))
    assert t.publication_halted("evergreen") is False


def test_resolving_an_incident_clears_the_halt():
    t = IncidentTracker(_db())
    for i in range(3):
        inc = t.report(DefectReport("evergreen", "1.0.0", "panel", 14, f"c{i}", "row 14"))
    t.resolve(inc.id, "corrected round 14 repeat", new_version="1.0.1")
    assert t.publication_halted("evergreen") is False


def test_support_cannot_patch_canonical_patterns():
    """Gate E: 'support cannot silently patch CIR'."""
    try:
        apply_support_patch(slug="evergreen", row=14, new_text="sc 39")
        assert False, "support must have no path to the canonical pattern"
    except SupportCannotPatchPatterns as e:
        assert "file an incident" in str(e)


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
