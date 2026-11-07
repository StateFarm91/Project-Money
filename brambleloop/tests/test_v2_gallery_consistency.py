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


def test_an_unclear_reading_is_not_a_disagreement_and_unjudged_frames_are_named():
    a = {"distinct_yarn_colours": 2, "border_or_edging_visible": "no"}
    unclear = {"distinct_yarn_colours": "unclear", "border_or_edging_visible": "unclear"}
    out = CG.campaign_consistency([_row(1, a), _row(2, unclear), _row(3, None)])
    assert out["status"] == "PASS", out
    assert out["pairwise"]["not_judged"] == ["3"] and "1 frame(s) not judged" in out["why"]
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
