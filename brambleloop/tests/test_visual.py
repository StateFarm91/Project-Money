"""The canonical model system and visual commerce QA.

v1.4.3 requirements 77-81 and 200-204. Two failures shape all of it: an identity that becomes
canonical by being first rather than by being chosen, and a gallery that does one of its two
jobs well and the other not at all.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.visual import gallery as gal  # noqa: E402
from brambleloop.visual import identity as ident  # noqa: E402


# ---- the canonical model --------------------------------------------------


def test_no_candidate_becomes_canonical_by_being_first():
    """#200. The shortcut this module is organised against.

    Nobody decides, the reference pack fills with whatever was produced, and a hundred
    listings later the company has a recurring face nobody chose.
    """
    status = ident.status()
    assert status["canonical_selected"] is False
    assert ident.canonical([]) is None
    assert "nothing will select itself" in status["note"]

    complete = ident.Candidate("c1", fields={f: "described" for f in ident.IDENTITY_FIELDS})
    try:
        ident.select(complete, owner_approved=False)
    except ident.IdentityRefused as e:
        assert "nobody chose" in str(e)
    else:
        raise AssertionError("a candidate became canonical without the owner")

    pack = ident.select(complete, owner_approved=True)
    assert pack.version == 1 and pack.complete()
    assert ident.canonical([pack]) is pack


def test_an_incomplete_reference_pack_cannot_be_frozen():
    """An unpinned field is a field that drifts, and drift is what the pack prevents."""
    thin = ident.Candidate("c2", fields={"hair": "described"})
    try:
        ident.select(thin, owner_approved=True)
    except ident.IdentityRefused as e:
        assert "would be incomplete" in str(e)
        assert "facial_geometry" in str(e)
    else:
        raise AssertionError("an incomplete pack was frozen")


def test_replacing_the_canonical_model_is_a_separate_owner_decision():
    """#200 reserves redesign to the owner explicitly.

    Approving a selection is not approving a redesign, so a second select() is refused even
    with approval — otherwise the identity could be replaced as a side effect.
    """
    fields = {f: "described" for f in ident.IDENTITY_FIELDS}
    first = ident.select(ident.Candidate("c1", fields=fields), owner_approved=True)
    try:
        ident.select(ident.Candidate("c2", fields=fields), owner_approved=True,
                     existing=first)
    except ident.IdentityRefused as e:
        assert "redesign" in str(e)
    else:
        raise AssertionError("the canonical identity was replaced by a selection call")


def test_drift_with_no_reference_pack_is_unavailable_and_never_a_pass():
    """#201. A check that passed for want of a reference would be believed.

    And the assets it waved through would carry a face that changed slowly across a gallery,
    in the way buyers notice without being able to name.
    """
    nothing = ident.drift_check({"face": "anything"}, None)
    assert nothing["verdict"] == "unavailable"
    assert nothing["blocks_release"] is True
    assert "not a pass" in nothing["reason"]

    fields = {f: "described" for f in ident.IDENTITY_FIELDS}
    pack = ident.select(ident.Candidate("c1", fields=fields), owner_approved=True)

    matching = ident.drift_check(
        {"face": "described", "hair": "described", "eyes": "described",
         "age": "described", "stylisation": "described"}, pack)
    assert matching["verdict"] == "pass"

    drifted = ident.drift_check(
        {"face": "someone else", "hair": "described", "eyes": "described",
         "age": "described", "stylisation": "described"}, pack)
    assert drifted["verdict"] == "fail"
    assert "face" in drifted["failed"]
    assert "wrong woman" in drifted["reason"]

    # An unmeasured dimension counts as maximum drift rather than being skipped.
    partial = ident.drift_check({"face": "described"}, pack)
    assert partial["verdict"] == "fail"


def test_the_model_is_not_forced_into_products_that_sell_better_without_her():
    """#204. Product truth and category fit outrank compulsory brand recognition."""
    blanket = ident.shot_plan(product_form="blanket")
    assert blanket["product_first"] is True
    assert blanket["model_frames"] == 0
    assert "commercially stronger" in blanket["note"]

    cardigan = ident.shot_plan(product_form="fitted_garment")
    assert cardigan["product_first"] is False
    assert cardigan["model_frames"] >= 2
    assert any(f["role"] == "fit" for f in cardigan["frames"])

    # Every frame carries a commercial job, so none of it is filler (#80).
    for plan in (blanket, cardigan):
        assert all(f["job"] for f in plan["frames"])


# ---- gallery QA -----------------------------------------------------------


def test_a_gallery_must_do_both_of_its_jobs():
    """#78. One frame cannot create desire and substantiate a purchase.

    All evidence is a specification sheet nobody clicks; all creative is a listing that
    converts and then refunds.
    """
    only_evidence = gal.check_gallery([
        gal.Frame("evidence", 0, agrees_with_twin=True),
        gal.Frame("detail", 1, agrees_with_twin=True)])
    assert only_evidence["ok"] is False
    checks = {p["check"] for p in only_evidence["blocking"]}
    assert "hero_dream" in checks and "hero_position" in checks

    only_creative = gal.check_gallery([
        gal.Frame("hero", 0, readable_at_grid=True),
        gal.Frame("lifestyle", 1, readable_at_grid=True)])
    assert "evidence_proof" in {p["check"] for p in only_creative["blocking"]}

    both = gal.check_gallery([
        gal.Frame("hero", 0, readable_at_grid=True),
        gal.Frame("detail", 1, agrees_with_twin=True)])
    assert both["ok"] is True
    assert both["jobs"][gal.CONVERSION] == ["hero"]
    assert both["jobs"][gal.EVIDENCE] == ["detail"]


def test_each_frame_is_judged_by_the_job_it_was_given():
    """A hero is judged on whether it works at grid size; evidence on whether it is true."""
    unreadable = gal.check_frame(gal.Frame("hero", 0, readable_at_grid=False))
    assert unreadable[0]["check"] == "grid_readability"
    assert "buying decision starts" in unreadable[0]["problem"]

    lying = gal.check_frame(gal.Frame("detail", 1, agrees_with_twin=False))
    assert lying[0]["check"] == "twin_agreement"
    assert "wrong product" in lying[0]["problem"]

    # Unjudged is its own state: not a pass, not a failure.
    unjudged = gal.check_frame(gal.Frame("hero", 0))
    assert unjudged[0]["unjudged"] is True

    # A frame with no declared job is filler and is refused outright.
    try:
        gal.Frame("vibes", 0)
    except gal.GalleryRefused as e:
        assert "minimum count" in str(e)
    else:
        raise AssertionError("a frame with no job was accepted")


def test_a_generated_hero_must_be_disclosed_and_must_survive_realism_checks():
    """#79. Artefacts a maker sees instantly are worse than an obviously illustrated image."""
    undisclosed = gal.check_frame(
        gal.Frame("hero", 0, readable_at_grid=True, generated=True,
                  realism={k: True for k in gal.REALISM_CHECKS}))
    assert any(f["check"] == "asset_truth" for f in undisclosed)

    broken = gal.check_frame(
        gal.Frame("hero", 0, readable_at_grid=True, generated=True,
                  disclosed_as_illustration=True,
                  realism={**{k: True for k in gal.REALISM_CHECKS},
                           "hands_and_fingers": False, "yarn_continuity": False}))
    realism = [f for f in broken if f["check"] == "physical_realism"][0]
    assert "hands_and_fingers" in realism["problem"]

    # Unmade realism checks on a generated frame are unjudged rather than assumed fine.
    unchecked = gal.check_frame(
        gal.Frame("hero", 0, readable_at_grid=True, generated=True,
                  disclosed_as_illustration=True))
    assert any(f.get("unjudged") and f["check"] == "physical_realism" for f in unchecked)


def test_the_escalation_ladder_never_includes_lowering_the_standard():
    """#77 and #81. Holding the listing is a real outcome, not a failure of the ladder."""
    rungs = [gal.escalate(i)["action"] for i in range(len(gal.ESCALATION))]
    assert rungs[0] == "regenerate_constrained"
    assert rungs[-1] == "hold_listing"
    assert not any("lower" in r or "relax" in r or "accept" in r for r in rungs)

    exhausted = gal.escalate(99)
    assert exhausted["exhausted"] is True
    assert exhausted["action"] == "hold_listing"
    assert "does not drop because an asset was AI-assisted" in exhausted["note"]

    # Cheap fixes come before expensive certainty.
    assert rungs.index("change_composition") < rungs.index("acquire_physical_proof")


def test_an_asset_from_a_previous_release_is_stale_rather_than_merely_old():
    """It is the most convincing kind of wrong, because it was true once."""
    stale = gal.stale_assets(
        [{"id": 1, "release_hash": "aaa"}, {"id": 2, "release_hash": "bbb"},
         {"id": 3}],
        current_release_hash="bbb")
    assert [a["id"] for a in stale] == [1]


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
