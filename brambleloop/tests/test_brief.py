"""The flow from truth to creative, and the one direction creative may not go.

Requirement 63. The flow was half built -- CIR to twin to evidence -- and the constraint in
the middle was missing. Its shape is an asymmetry: *creative may select from truth and may
never extend it.* A hero showing three of seven stitch types is a photograph of part of a
thing. A hero showing an eighth is a claim about a pattern that does not contain it, made by
an image nobody thought of as a statement.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.publish import brief as B  # noqa: E402


def _brief(**kw) -> B.Brief:
    args = dict(product_slug="autumn-throw", version="1", evidence_ref="evidence/at-1.json",
                motifs=("leaf", "acorn"), dimensions=("90x122cm",),
                texture=("bobble", "moss"), construction=("worked_flat", "seamed"),
                deliverables=("pdf", "colour_chart"))
    args.update(kw)
    return B.brief_from_truth(**args)


# ---- the one-way rule -----------------------------------------------------


def test_showing_less_than_the_truth_is_allowed():
    out = B.check_creative(_brief(), {B.MOTIFS: ("leaf",), B.TEXTURE: ("bobble",)})
    assert out["ok"] is True
    assert out["omitted"][B.MOTIFS] == ["acorn"]
    assert "photograph of part of a thing" in out["omission_is_allowed"]


def test_showing_more_than_the_truth_is_invention():
    out = B.check_creative(_brief(), {B.MOTIFS: ("leaf", "pumpkin")})
    assert out["ok"] is False
    assert out["invented"][0]["invented"] == ["pumpkin"]
    assert "may not add to it" in out["invented"][0]["why"]


def test_every_category_the_requirement_names_is_constrained():
    for name in ("motifs", "dimensions", "texture", "construction", "included_deliverables"):
        assert name in B.CONSTRAINED
    assert len(B.CONSTRAINED) == 5


def test_invention_is_caught_in_each_category_not_only_motifs():
    brief = _brief()
    for category, invented in ((B.DIMENSIONS, "180x240cm"),
                               (B.TEXTURE, "cable"),
                               (B.CONSTRUCTION, "worked_in_the_round"),
                               (B.DELIVERABLES, "video_tutorial")):
        out = B.check_creative(brief, {category: (invented,)})
        assert out["ok"] is False, category
        assert out["invented"][0]["category"] == category


def test_a_deliverable_nobody_ships_is_the_expensive_one():
    out = B.check_creative(_brief(), {B.DELIVERABLES: ("pdf", "video_tutorial")})
    assert out["ok"] is False
    assert "arrives when they pay" in out["invented"][0]["why"]


def test_a_category_outside_the_closed_list_is_refused():
    try:
        B.check_creative(_brief(), {"style": ("cosy",)})
    except B.BriefRefused as e:
        assert "not constrained categories" in str(e)
    else:  # pragma: no cover
        raise AssertionError("an unconstrained category was accepted")


# ---- a brief that constrains rather than describes -------------------------


def test_a_brief_names_the_evidence_it_came_from():
    try:
        _brief(evidence_ref="  ")
    except B.BriefRefused as e:
        assert "describes it rather than constraining it" in str(e)
    else:  # pragma: no cover
        raise AssertionError("a brief with no provenance was accepted")


def test_a_brief_silent_about_a_category_is_refused():
    try:
        B.Brief(product_slug="p", version="1", derived_from="ev",
                allows={B.MOTIFS: ("leaf",)})
    except B.BriefRefused as e:
        assert "the opposite of a constraint" in str(e)
    else:  # pragma: no cover
        raise AssertionError("a brief left four categories open")


def test_an_empty_allowance_is_a_real_constraint_rather_than_silence():
    """Zero permitted motifs is a decision; no entry at all is an opening."""
    brief = _brief(motifs=())
    assert brief.allows[B.MOTIFS] == ()
    out = B.check_creative(brief, {B.MOTIFS: ("leaf",)})
    assert out["ok"] is False


# ---- the order is load-bearing --------------------------------------------


def test_every_stage_of_the_required_flow_is_present_in_order():
    assert B.FLOW.index(B.CIR) < B.FLOW.index(B.TWIN) < B.FLOW.index(B.EVIDENCE)
    assert B.FLOW.index(B.EVIDENCE) < B.FLOW.index(B.BRIEF) < B.FLOW.index(B.CREATIVE)
    assert B.FLOW.index(B.CREATIVE) < B.FLOW.index(B.ASSET_TRUTH) < B.FLOW.index(B.GATES)
    assert B.FLOW[-1] == B.EXPORT
    assert len(B.FLOW) == 8


def test_one_stage_at_a_time_advances():
    assert B.advance(B.EVIDENCE, B.BRIEF)["advanced"] is True


def test_skipping_the_brief_is_refused_because_a_later_brief_is_a_caption():
    out = B.advance(B.EVIDENCE, B.CREATIVE)
    assert out["advanced"] is False
    assert out["skipped"] == [B.BRIEF]
    assert "is a caption" in out["why"]


def test_an_asset_truth_comparison_before_the_creative_has_compared_nothing():
    out = B.advance(B.BRIEF, B.ASSET_TRUTH)
    assert out["advanced"] is False
    assert "compared nothing" in out["why"]


def test_going_backwards_is_a_real_thing_that_restarts_rather_than_continues():
    out = B.advance(B.GATES, B.BRIEF)
    assert out["advanced"] is False
    assert "restarts the flow" in out["why"]


def test_a_stage_that_does_not_exist_is_refused():
    try:
        B.advance(B.CIR, "vibes")
    except B.BriefRefused as e:
        assert "is not a stage" in str(e)
    else:  # pragma: no cover
        raise AssertionError("the flow grew a stage")


# ---- independence ---------------------------------------------------------


def test_the_asset_truth_comparison_cannot_be_signed_off_by_its_author():
    out = B.check_independence(produced_by="creative_cell", compared_by="creative_cell")
    assert out["independent"] is False
    assert "brings its own tasks" in out["why"]


def test_a_different_checker_is_independent():
    out = B.check_independence(produced_by="creative_cell", compared_by="asset_truth")
    assert out["independent"] is True


def test_an_unnamed_maker_or_checker_settles_nothing():
    try:
        B.check_independence(produced_by="creative_cell", compared_by="")
    except B.BriefRefused as e:
        assert "cannot be established either way" in str(e)
    else:  # pragma: no cover
        raise AssertionError("independence was assumed from a blank")


def test_state_states_the_one_way_rule():
    out = B.state()
    assert out["requirement"] == 63
    assert "may select from truth and may never extend it" in out["one_way_rule"]


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
