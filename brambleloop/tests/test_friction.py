"""The buyer's journey, and the two ways an audit of it flatters the shop.

Requirement 261. The first way is filing friction where it arrived: support absorbs nearly
all of it and causes almost none, so an audit grouped by arrival produces support macros and
leaves the listing saying the same wrong thing. The second is the shape this build keeps
finding -- a verdict computed from the absence of complaints passes a funnel nobody walked,
which is this shop's actual situation today.

Most of these tests are about the audit being unable to say `clean` when it means `empty`.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.commerce import friction as F  # noqa: E402
from brambleloop.commerce import seo  # noqa: E402


GOOD_TITLE = "Autumn Leaves Blanket | Crochet Pattern PDF | US and UK Terms"
GOOD_DESC = (
    "Autumn Leaves Blanket — a crochet pattern, not a finished item. You receive an instant "
    "digital download.\n\nWHAT YOU GET\n- Written instructions for every row\n- US terms, "
    "with UK equivalents in the stitch key\n\nTHE DETAILS\n- Finished size: 120 x 150 cm\n"
    "- Difficulty: Intermediate\n")


# ---- the listing, checked before any buyer exists -------------------------


def test_the_shops_own_generated_listing_copy_passes_this_audit():
    """The check that would have caught this module shipping a standard it does not meet.

    `seo.build_description` is the generator; this is the auditor. They were written for the
    same six confusions by the same build, which is exactly the situation in which two
    slightly different ideas of "answered" survive unnoticed until a real listing fails one
    of them.
    """
    desc = seo.build_description(
        "Autumn Leaves Blanket", size_label="120 x 150 cm",
        yardage_lines=["Main colour: about 900 m"], tolerance_pct=15,
        difficulty="Intermediate", colors=["cream", "rust"], terminology="US",
        gauge_line="14 dc x 8 rows = 10 cm", stitches=["double crochet"], pages=18)
    title = seo.build_title("Autumn Leaves Blanket", "blanket", ["leaves"])
    out = F.listing_audit(title=title, description=desc)
    assert out["clear"] is True, out["defects"]
    assert all(out["answered"].values())


def test_a_listing_that_never_says_it_is_a_pattern_is_a_defect():
    desc = GOOD_DESC.replace("a crochet pattern, not a finished item", "a cosy autumn make")
    out = F.listing_audit(title="Autumn Leaves Blanket | Crochet PDF", description=desc)
    found = {d["confusion"] for d in out["defects"]}
    assert "pattern_vs_finished_item" in found
    assert out["clear"] is False


def test_the_answer_below_the_fold_is_still_a_defect():
    """Said in paragraph nine, to the person who stopped reading at paragraph one."""
    desc = ("A beautiful heirloom make for autumn. " * 8
            + "\n\nThis is a crochet pattern, not a finished item.\n"
            + "US terms. Finished size: 120 x 150 cm. Difficulty: Intermediate. "
              "What you get: written instructions.")
    out = F.listing_audit(title="Autumn Leaves Blanket", description=desc)
    assert out["answered"]["pattern_vs_finished_item"] is True
    reasons = [d["why"] for d in out["defects"] if d["confusion"] == "pattern_vs_finished_item"]
    assert reasons and "did not open" in reasons[0]


def test_an_empty_description_is_refused_rather_than_passed():
    try:
        F.listing_audit(title="Blanket", description="   ")
    except F.FrictionRefused as e:
        assert "absence-of-failure" in str(e)
    else:  # pragma: no cover
        raise AssertionError("an empty description audited clear")


def test_the_audit_reads_the_artefact_not_the_generator():
    out = F.listing_audit(title=GOOD_TITLE, description=GOOD_DESC)
    assert out["evidence"] == "the listing artefact"
    assert "defendant" in out["note"]


# ---- friction is filed where it was caused --------------------------------


def test_a_refund_at_support_is_a_listing_defect():
    """The whole reason this module carries two stages instead of one."""
    frictions = [F.Friction(confusion="pattern_vs_finished_item", surfaced_at=F.SUPPORT,
                            order_ref=f"o{i}") for i in range(3)]
    report = F.audit(frictions, [F.Traversal(stage=F.SUPPORT, count=40),
                                 F.Traversal(stage=F.LISTING, count=40)])
    assert report["stages"][F.LISTING]["verdict"] == F.FRICTION_FOUND
    assert report["stages"][F.SUPPORT]["raised"] == []
    fix = report["actionable"][0]
    assert fix["fix_at"] == F.LISTING and fix["surfaced_at"] == [F.SUPPORT]


def test_one_broken_download_is_enough_but_one_confusion_is_not():
    walked = [F.Traversal(stage=s, count=40) for s in F.STAGES]
    broken = F.audit([F.Friction(confusion="file_access", surfaced_at=F.DELIVERY,
                                 order_ref="o1")], walked)
    single = F.audit([F.Friction(confusion="sizing", surfaced_at=F.SUPPORT,
                                 order_ref="o1")], walked)
    assert broken["stages"][F.DELIVERY]["verdict"] == F.FRICTION_FOUND
    assert single["stages"][F.LISTING]["verdict"] == F.CLEAN
    assert single["stages"][F.LISTING]["raised"][0]["act"] is False


def test_recurrence_is_a_rate_and_not_a_count():
    """Three in five is an emergency; three in four hundred is three people."""
    few = F.audit([F.Friction(confusion="sizing", surfaced_at=F.SUPPORT, order_ref=f"o{i}")
                   for i in range(3)],
                  [F.Traversal(stage=F.LISTING, count=40), F.Traversal(stage=F.SUPPORT, count=40)])
    many = F.audit([F.Friction(confusion="sizing", surfaced_at=F.SUPPORT, order_ref=f"o{i}")
                    for i in range(3)],
                   [F.Traversal(stage=F.LISTING, count=400),
                    F.Traversal(stage=F.SUPPORT, count=400)])
    assert few["stages"][F.LISTING]["verdict"] == F.FRICTION_FOUND
    assert many["stages"][F.LISTING]["verdict"] == F.CLEAN


def test_free_text_friction_is_refused():
    try:
        F.Friction(confusion="they seemed unhappy", surfaced_at=F.SUPPORT, order_ref="o1")
    except F.FrictionRefused as e:
        assert "cannot be counted" in str(e)
    else:  # pragma: no cover
        raise AssertionError("an uncountable category was accepted")


def test_friction_with_no_order_behind_it_is_refused():
    try:
        F.Friction(confusion="sizing", surfaced_at=F.SUPPORT, order_ref="  ")
    except F.FrictionRefused as e:
        assert "a worry, not an observation" in str(e)
    else:  # pragma: no cover
        raise AssertionError("friction without an order was accepted")


# ---- silence is not evidence ----------------------------------------------


def test_a_journey_nobody_walked_does_not_audit_clean():
    report = F.audit([], [])
    assert all(v["verdict"] == F.NOT_YET_WALKED for v in report["stages"].values())
    out = F.overall(report)
    assert out["passes"] is False
    assert out["verdict"] == F.NOT_YET_WALKED
    assert len(out["not_yet_walked"]) == len(F.STAGES)


def test_a_walked_but_thin_stage_is_unmeasured_not_clean():
    report = F.audit([], [F.Traversal(stage=s, count=3) for s in F.STAGES])
    out = F.overall(report)
    assert out["verdict"] == F.UNMEASURED
    assert out["passes"] is False


def test_clean_requires_every_stage_walked_and_measured():
    report = F.audit([], [F.Traversal(stage=s, count=50) for s in F.STAGES])
    out = F.overall(report)
    assert out["verdict"] == F.CLEAN and out["passes"] is True


def test_one_unwalked_stage_is_enough_to_withhold_the_pass():
    walked = [F.Traversal(stage=s, count=50) for s in F.STAGES if s != F.FIRST_USE]
    out = F.overall(F.audit([], walked))
    assert out["passes"] is False
    assert out["not_yet_walked"] == [F.FIRST_USE]


def test_a_complaint_proves_somebody_reached_the_stage_it_arrived_at():
    """Otherwise support is 'never walked' while it is visibly answering questions."""
    report = F.audit([F.Friction(confusion="file_access", surfaced_at=F.SUPPORT,
                                 order_ref="o1")], [])
    assert report["stages"][F.SUPPORT]["exposure"] >= 1
    assert report["stages"][F.SUPPORT]["verdict"] != F.NOT_YET_WALKED


def test_friction_outranks_an_unwalked_stage_in_the_headline():
    report = F.audit([F.Friction(confusion="file_access", surfaced_at=F.DELIVERY,
                                 order_ref="o1")], [])
    out = F.overall(report)
    assert out["verdict"] == F.FRICTION_FOUND
    assert out["passes"] is False


# ---- what it cannot see ---------------------------------------------------


def test_checkout_is_named_as_not_ours_to_fix():
    report = F.audit([], [F.Traversal(stage=s, count=50) for s in F.STAGES])
    assert report["stages"][F.CHECKOUT]["ours"] is False
    assert all(report["stages"][s]["ours"] for s in F.OURS)


def test_state_names_the_non_buyer_blind_spot_and_the_day_zero_half():
    out = F.state()
    assert "left without buying" in out["blind_spot"]
    assert "listing_audit" in out["available_now"]
    assert F.DELIVERY in out["needs_a_real_buyer"]


def test_every_confusion_the_spec_names_has_a_causing_stage():
    for name, spec in F.CONFUSIONS.items():
        assert spec["caused_at"] in F.STAGES, name
        assert spec["kind"] in (F.CORRECTNESS, F.COMPREHENSION), name
        assert spec["why"].strip(), name


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
