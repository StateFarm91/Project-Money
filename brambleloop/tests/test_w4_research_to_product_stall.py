"""W4-AGENTS2 batch C1: why tournament winners stopped reaching engineering.

Production: 191 creative tournaments ran and none reached engineering after `cir.draft` job
24731. Reproduced offline here with the real job system (the tournament handler, the
seasonal sentinel's re-gate and the worker), with only the model call substituted by the
design-pipeline fixture generator (`test_cert_design_pipeline`).

What the code shows:
* **The legitimate gate.** Every winner the funnel carries meets the pre-engineering gate,
  whose #88 (does it read at mobile-grid size) and #83 (the jury's taste) checks are
  judgements only a vision model can make. Without one the winner is WAITING on
  `image_vision`, never engineered. `regate_held` re-presents it once a named vision judge has
  recorded `concept.judged` against the bytes of the board on file. That needs a board (a
  deterministic twin board for expensive make lanes, otherwise image generation) and a
  usable vision model. With the vision provider's credit exhausted nothing is judged, so
  nothing is drafted.
* **A defect, fixed.** `regate_held` read only the newest `REGATE_ROWS` (200) intake rows.
  After 191 tournaments, an older WAITING winner fell out of that window and was never
  re-presented, even after its judgement arrived. It now reads the newest intake row of every
  design, and the number of paid judge calls per run stays capped at `REGATE_LIMIT`.

Run: cd brambleloop && PYTHONPATH=src:tests $PY tests/test_w4_research_to_product_stall.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import test_cert_design_pipeline as T  # noqa: E402 - the real-runtime design harness

from brambleloop.core.models import AuditLog  # noqa: E402
from brambleloop.creative import intake  # noqa: E402


def test_without_a_vision_judgement_every_carried_winner_waits_and_nothing_is_drafted():
    db = T._db()
    T._stockings(db)
    decisions = []
    for _ in range(3):
        result, row = T._tournament(db)
        assert result["ran"] is True and result["winner"], result
        assert row["funnel"]["carried"] is True
        decisions.append((row["decision"], tuple(row["gate"]["waiting_on"] or ())))
    assert all(d == (intake.WAITING, ("image_vision",)) for d in decisions), decisions
    out, _ = T._handler(db, "mjs.seasonal_sentinel", {}, agent="market_radar")
    reg = out["regated"]
    assert reg["vision_usable"] is False and not reg["queued"] and reg["held"]
    waits = " ".join(" ".join(h["waiting_on"]) for h in reg["held"])
    assert "vision_model" in waits                     # the exact thing it waits for
    assert not T._jobs(db, "cir.draft")


def test_an_old_waiting_winner_is_regated_after_more_than_regate_rows_newer_intakes():
    db = T._db()
    T._stockings(db)
    _result, row = T._tournament(db)
    slug = row["concept"]["key"]
    assert row["decision"] == intake.WAITING
    # More newer intake rows than the old window held (other designs, refused, so they are
    # never re-presented themselves).
    with db.session() as s:
        for i in range(intake.REGATE_ROWS + 5):
            s.add(AuditLog(actor="creative_director", action=intake.INTAKE_ACTION,
                           artifact=f"filler-design-{i}", detail={"decision": intake.REFUSED}))
    assert slug not in {a for _i, a, _d in intake.intake_rows(db)}   # outside the old window
    T._judge(db, slug)
    out, _ = T._handler(db, "mjs.seasonal_sentinel", {}, agent="market_radar")
    assert {"slug": slug, "decision": "engineering"} in out["regated"]["presented"], out
    drafts = T._jobs(db, "cir.draft")
    assert len(drafts) == 1 and drafts[0].inputs["slug"] == slug


def test_latest_per_slug_keeps_only_the_newest_row_of_each_design():
    db = T._db()
    with db.session() as s:
        for i, (slug, dec) in enumerate([("a", "waiting"), ("b", "waiting"), ("a", "refused")]):
            s.add(AuditLog(actor="x", action=intake.INTAKE_ACTION, artifact=slug,
                           detail={"decision": dec}))
    rows = intake.latest_per_slug(db)
    assert [(a, d["decision"]) for _i, a, d in rows] == [("a", "refused"), ("b", "waiting")]


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                fails += 1
                print("FAIL", name, repr(e))
                traceback.print_exc()
    print(f"{fails} failed")
    sys.exit(1 if fails else 0)
