"""V2 / P1-d: a gallery whose frames disagree on the item fails campaign_consistency.

The per-frame readings are the vision judge's recorded blind descriptions (the candidate side
of each frame's anchor-consistency check), read back from stored ImageCandidate rows through
`image_production._best`. No judge is called here: the readings are fixtures in the stored
checks, the shape `vision_judges.compare_items` records.

Run: cd brambleloop && PYTHONPATH=src $PY tests/test_v2_gallery_consistency.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.visual import candidate_gates as CG  # noqa: E402
from brambleloop.visual import image_production as IP  # noqa: E402
from brambleloop.visual.image_records import ImageCandidate, ensure_tables  # noqa: E402

BASE = {"listing": "basket", "version": "1.0.0", "release": "r1", "cir_fingerprint": "f1",
        "laura_present": False, "outfit_id": None}


def _row(i, reading):
    return {**BASE, "candidate_id": i, "item_reading": reading}


def test_frames_that_agree_pass_and_say_how_many_pairs_were_compared():
    same = {"distinct_yarn_colours": 2, "border_or_edging_visible": "no"}
    out = CG.campaign_consistency([_row(1, same), _row(2, dict(same)), _row(3, dict(same))])
    assert out["status"] == "PASS" and out["pairwise"]["compared"] == 3, out
    assert "3 frame pair(s) agree" in out["why"]


def test_frames_that_disagree_on_colour_count_or_edging_fail():
    a = {"distinct_yarn_colours": 2, "border_or_edging_visible": "no"}
    out = CG.campaign_consistency([_row(1, a), _row(2, {**a, "distinct_yarn_colours": 3})])
    assert out["status"] == "FAIL" and "colour count (2 vs 3)" in out["why"], out
    out = CG.campaign_consistency([_row(1, a), _row(2, {**a, "border_or_edging_visible":
                                                        "yes"})])
    assert out["status"] == "FAIL" and "edging" in out["why"], out


def test_an_unjudged_or_unclear_pair_is_unknown_never_pass():
    """I-V2-UNJUDGED-PAIRS: a pair nobody could judge blocks readiness as UNKNOWN."""
    a = {"distinct_yarn_colours": 2, "border_or_edging_visible": "no"}
    unclear = {"distinct_yarn_colours": "unclear", "border_or_edging_visible": "unclear"}
    out = CG.campaign_consistency([_row(1, a), _row(2, unclear), _row(3, None)])
    assert out["status"] == "UNKNOWN", out
    assert out["pairwise"]["unjudged"] == 3 and out["pairwise"]["not_judged"] == ["3"], out
    assert out["blocker"] == "campaign_consistency_unjudged: 3 pairs", out
    # No frame read at all (vision off): still UNKNOWN, never PASS.
    out = CG.campaign_consistency([_row(1, None), _row(2, None)])
    assert out["status"] == "UNKNOWN" and out["blocker"].endswith("1 pairs"), out
    # A disagreement beside an unjudged pair is still a FAIL, with its reason.
    out = CG.campaign_consistency([_row(1, a), _row(2, {**a, "distinct_yarn_colours": 4}),
                                   _row(3, None)])
    assert out["status"] == "FAIL" and "colour count" in out["why"], out
    # A single image has no pair to judge.
    assert CG.campaign_consistency([_row(1, None)])["status"] == "PASS"
    # The metadata checks still bind on top.
    assert CG.campaign_consistency([_row(1, a), {**_row(2, a), "version": "1.1"}])[
        "status"] == "FAIL"


def test_the_stored_reading_is_what_best_hands_to_the_gallery():
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='v2g_')}/g.sqlite")
    db.create_all()
    ensure_tables(db)
    reading = {"image_1": {"distinct_yarn_colours": 2},
               "image_2": {"distinct_yarn_colours": 3, "border_or_edging_visible": "yes"}}
    with db.session() as s:
        s.add(ImageCandidate(listing="basket", role="lifestyle_hero", run_key="k",
                             slug="basket", version="1.0.0", release="r1", sha256="a" * 64,
                             method="fixture", provenance_kind="generated", technical_status="PASS", publishable=True,
                             attempt=1, checks={"product_truth": {"fidelity": {"checks": [
                                 {"check": "anchor_consistency", "status": "PASS",
                                  "reading": reading}]}}}))
        s.add(ImageCandidate(listing="basket", role="flat_lay_detail", run_key="k",
                             slug="basket", version="1.0.0", release="r1", sha256="b" * 64,
                             method="fixture", provenance_kind="generated", technical_status="PASS", publishable=True,
                             attempt=1, checks={}))
    hero = IP._best(db, listing="basket", role="lifestyle_hero")
    plain = IP._best(db, listing="basket", role="flat_lay_detail")
    assert hero["item_reading"] == reading["image_2"], hero["item_reading"]
    assert plain["item_reading"] is None


def _plan():
    """Two generated roles, nothing else, so gallery_ready turns on consistency alone."""
    from brambleloop.visual import shot_plans as SP

    role = {"required_by": "fixture", "conditional": False, "preferred_source": "generated",
            "generate": True, "sources": {SP.DISCLOSED: "no"}}
    return {"category": "fixture", "image_count": 2, "roles": [
        {**role, "position": 1, "role": "lifestyle_hero", "job": "LIFESTYLE"},
        {**role, "position": 2, "role": "flat_lay_detail", "job": "DETAIL"}]}


def _readiness(reading_a, reading_b):
    rows = {"lifestyle_hero": _row(1, reading_a), "flat_lay_detail": _row(2, reading_b)}
    from brambleloop.publish import eligibility as el

    # V1's readiness resolves one production identity and certifies the set; both are pinned
    # to "fine" here so the verdict turns on campaign consistency alone.
    real = IP._best, IP._dashboard_identity, el.check_set
    IP._best = lambda db, *, listing, role, **kw: {
        **rows[role], "publishable": True, "technical_status": "PASS", "blockers": []}
    IP._dashboard_identity = lambda db, listing: (
        {"slug": "basket", "version": "1.0.0", "release": "r1"}, False)
    el.check_set = lambda cands: {"ok": True, "problems": []}
    try:
        return IP.readiness(None, "basket", plan=_plan())
    finally:
        IP._best, IP._dashboard_identity, el.check_set = real


def test_an_unjudged_gallery_is_not_ready_and_names_its_blocker():
    """Review V2 F7 (mutants G1, G4): gallery_ready needs PASS or N/A, never UNKNOWN."""
    a = {"distinct_yarn_colours": 2, "border_or_edging_visible": "no"}
    ok = _readiness(a, dict(a))
    assert ok["campaign_consistency"]["status"] == "PASS" and ok["gallery_ready"], ok
    assert not any(b.startswith(CG.UNJUDGED_BLOCKER) for b in ok["publication_blockers"])
    out = _readiness(a, None)
    assert out["campaign_consistency"]["status"] == "UNKNOWN", out["campaign_consistency"]
    assert out["gallery_ready"] is False, out
    assert f"{CG.UNJUDGED_BLOCKER}: 1 pairs" in out["publication_blockers"], out
    bad = _readiness(a, {**a, "distinct_yarn_colours": 3})
    assert bad["campaign_consistency"]["status"] == "FAIL" and bad["gallery_ready"] is False


if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK   {name}")
            except Exception:  # noqa: BLE001
                import traceback

                failed += 1
                print(f"FAIL {name}")
                traceback.print_exc()
    print(f"{failed} failed")
    sys.exit(1 if failed else 0)
