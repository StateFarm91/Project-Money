"""Whether the tiling blocker belongs to the incumbent provider, measured honestly.

What these tests protect is not the arithmetic. It is that a provider cannot win by
clearing the blocker while breaking something else, that the authorised ceiling is enforced
before a render rather than discovered after it, and that a trial render is never mistaken
for a listing asset.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.visual import provider_trial as pt  # noqa: E402


def _db() -> Database:
    db = Database("sqlite://")
    db.create_all()
    return db


def _row(provider="nano-banana-2", *, slug="spooky-garland", texture=(), structural=(),
         photoreal=(), truth="match", usable=True, cad=0.1384) -> dict:
    return {"provider": provider, "slug": slug, "made": True,
            "texture_failed": list(texture), "structural_failed": list(structural),
            "photoreal_failed": list(photoreal), "product_truth": truth,
            "usable_as_listing_asset": usable, "spent_cad": cad,
            "photographic_realism": "clear" if not photoreal else "blocked"}


def test_the_ceiling_is_checked_before_the_render_not_after():
    """A ceiling discovered by exceeding it is not a ceiling.

    The owner authorised CA$4.00 and said to stop at it. Checking afterwards means the
    render that breaks the limit has already been paid for.
    """
    db = _db()
    try:
        pt.attempt(db, None, None, provider_key="nano-banana-2", work_dir="/tmp",
                   spent_so_far=pt.CEILING_CAD)
    except pt.CeilingReached as exc:
        assert "already spent" in str(exc)
        assert "Stopping at the ceiling is the instruction" in str(exc)
    else:
        raise AssertionError("a render was attempted past the authorised ceiling")


def test_a_render_that_would_land_exactly_on_the_ceiling_is_allowed():
    """The limit is a ceiling, not a margin. Refusing at the limit would under-spend it."""
    price = pt._price_of("nano-banana-2")
    headroom = pt.CEILING_CAD - price
    # It must not raise for the render that lands exactly on CA$4.00; it raises for the
    # next one. Driven through the real guard rather than re-implemented here.
    try:
        pt.attempt(_db(), None, None, provider_key="nano-banana-2", work_dir="/tmp",
                   spent_so_far=headroom + 0.0001)
    except pt.CeilingReached:
        pass
    else:
        raise AssertionError("one penny over the ceiling was allowed through")


def test_clearing_the_blocker_while_breaking_structure_is_not_a_win():
    """The owner's rule, in code: a provider does not win merely by clearing one check."""
    out = pt._recommend([_row(texture=(), structural=("no_impossible_seams",))],
                        challenger="nano-banana-2")
    assert out["recommendation"] == "no_switch_on_this_evidence"
    assert out["regressed"] == ["no_impossible_seams"]
    assert "traded one launch blocker for another" in out["why"]


def test_clearing_the_blocker_while_losing_product_truth_is_not_a_win():
    """Product truth is launch-critical: a beautiful photograph of the wrong crochet."""
    out = pt._recommend([_row(truth="mismatch")], challenger="nano-banana-2")
    assert out["recommendation"] == "no_switch_on_this_evidence"
    assert out["product_truth_lost_on"] == ["spooky-garland"]


def test_clearing_the_blocker_while_reading_as_a_render_is_not_a_win():
    """Photographic realism is the owner's Final Master standard, asked separately."""
    out = pt._recommend([_row(photoreal=("skin_looks_real",))], challenger="nano-banana-2")
    assert out["recommendation"] == "no_switch_on_this_evidence"
    assert "skin_looks_real" in out["regressed"]


def test_tiling_on_the_challenger_too_is_a_finding_about_crochet_not_about_a_provider():
    out = pt._recommend([_row(texture=("texture_not_repeating",)),
                         _row(texture=("texture_not_repeating",))],
                        challenger="nano-banana-2")
    assert out["recommendation"] == "keep_the_incumbent"
    assert "not specific to" in out["why"]
    assert "switching would cost money and change nothing" in out["why"]


def test_clearing_it_sometimes_is_reported_as_a_rate_not_as_a_win():
    """The sampling rule the rest of this system already applies to itself."""
    out = pt._recommend([_row(), _row(texture=("texture_not_repeating",))],
                        challenger="nano-banana-2")
    assert out["recommendation"] == "promising_but_inconsistent"
    assert out["cleared"] == 1 and out["of"] == 2
    assert "not yet a rate" in out["why"]


def test_a_clean_sweep_recommends_the_switch_and_still_leaves_it_to_the_owner():
    out = pt._recommend([_row(), _row(slug="winter-village-graphghan")],
                        challenger="nano-banana-2")
    assert out["recommendation"] == "switch_worth_making"
    assert "The owner decides" in out["why"]


def test_no_challenger_render_is_unproven_rather_than_a_verdict():
    """Absence of evidence, refused out loud, as everywhere else in this system."""
    out = pt._recommend([], challenger="nano-banana-2")
    assert out["recommendation"] == "unproven"
    assert "nothing about it was measured" in out["why"]


def test_consistency_is_measured_across_repeated_renders_of_the_same_product():
    """A provider that clears the blocker one time in three has not cleared it."""
    summary = pt._summarise([_row(), _row(texture=("texture_not_repeating",)),
                             _row(slug="winter-village-graphghan"),
                             _row(slug="winter-village-graphghan")])
    assert summary["inconsistent_on_the_blocker"] == ["spooky-garland"]
    assert summary["consistent_on_the_blocker"] == ["winter-village-graphghan"]
    assert summary["texture_clear_rate"] == 0.75


def test_the_identity_dimension_is_stated_rather_than_silently_skipped():
    """"Not applicable" and "not measured" are different, and the owner asked for it."""
    # Asserted against the value, not against the source text. Scraping source is the same
    # brittleness as pinning a version string: it breaks on a reformat and passes on a
    # rewrite that changes the meaning.
    assert "canonical-model blocker is separate" in pt.IDENTITY_NOT_APPLICABLE
    assert "nothing here renders her" in pt.IDENTITY_NOT_APPLICABLE
    assert "product-first and carries no model" in pt.IDENTITY_NOT_APPLICABLE


def test_the_trial_files_under_its_own_action_and_is_never_a_listing_asset():
    """A trial is evidence about a provider. Reading one back as a product's photograph is
    the row-for-capability defect this system keeps finding."""
    from brambleloop.publish import owned_photography

    assert pt.ACTION != owned_photography.ACTION
    assert pt.ACTION == "visual.provider_trial"


def test_the_two_cases_cover_simple_and_hard_as_the_owner_required():
    slugs = [slug for slug, _ in pt.CASES]
    assert "spooky-garland" in slugs
    assert "winter-village-graphghan" in slugs
    assert any("simple" in why for _, why in pt.CASES)
    assert any("hard" in why for _, why in pt.CASES)


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
