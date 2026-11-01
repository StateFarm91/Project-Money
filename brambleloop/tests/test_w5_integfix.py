"""Batch 5 integration fixes (W5-INTEG1): interactions between independently reviewed branches.

Each test fails on the pre-fix tree and names the two branches whose combination it covers.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from brambleloop.gates import size_claims as SC  # noqa: E402


def test_a_round_or_row_number_is_a_place_in_the_pattern_not_a_count():
    """W4-PDF1 basket 1.3.0 x OPUS2 size-claim truth: the 1.3.0 checkpoint tip "Up to Rnd 10
    the basket should lie flat" was read as a promise of ten baskets and refused the release."""
    for text in ("If it ruffles or cups Up to Rnd 10 the basket should lie flat.",
                 "By Round 12 the bowl stands on its own.",
                 "After Row 4 the basket wall begins."):
        assert SC.claims_in(text) == [], (text, SC.claims_in(text))
    # Real counts still count, including next to a round reference.
    assert SC.claimed_count(SC.claims_in("Includes 3 baskets.")) == 3
    assert SC.claimed_count(SC.claims_in("Work Round 4, then make 2 bowls.")) == 2
    assert SC.claimed_count(SC.claims_in("A set of 3 nesting baskets in one pattern.")) == 3


def test_round_as_a_shape_or_row_never_hides_a_real_size_claim():
    """Review INTEG5FIX F1 (HIGH): "Round" is a basket shape and "row" a layout word; every one
    of these promised several pieces or sizes before the fix and must still be refused."""
    for text in ("Round 3 baskets", "Round 3-piece basket set", "Round 3 basket sizes",
                 "Round three sizes", "Shop this round 3 basket set.",
                 "Our round 3 baskets nest neatly.", "round 4 bins",
                 "Round two baskets for your shelf", "A row 3 baskets wide", "Rows 2 bags",
                 "3 rounds baskets", "Row of 3 baskets", "Rnd 2 3 baskets",
                 "Round basket set of 3", "Round, 3 baskets"):
        state = SC.check_texts({"listing title": text})["state"]
        assert state == SC.FAIL, (text, state, SC.claims_in(text))



class _Ctx:
    """The slice of JobContext `_persist_release` uses: db, job, phase, enqueue, audit."""

    def __init__(self, db):
        from types import SimpleNamespace

        from brambleloop.core.models import Job

        self.db, self.enqueued, self.audits = db, [], []
        with db.session() as s:   # provenance needs the job the certificate was built by
            job = Job(job_type="gate.certify", agent="quality_director")
            s.add(job)
            s.flush()
            job_id = job.id
        self.job = SimpleNamespace(agent="quality_director", id=job_id)
        self.phase = None

    def enqueue(self, *a, **k):
        self.enqueued.append((a, k))

    def audit(self, action, **k):
        self.audits.append((action, k))


def test_a_recertified_release_keeps_both_permanent_and_reverify_withholdings():
    """Review INTEG5FIX F3: the merged re-certification branch of `pipeline._persist_release`
    applies `carry_reverification` (OPUS2) and `carry_permanent` (PHYSFIX). Re-certify a
    size-failed, re-verification-failed version under a NEW release hash and both survive."""
    import tempfile

    from brambleloop.core.db import Database
    from brambleloop.products import launch0 as l0
    from brambleloop.publish import withholding as W
    from brambleloop.runtime import pipeline as P

    db = Database(f"sqlite:///{tempfile.mkdtemp()}/integ5.sqlite")
    db.create_all()
    ctx = _Ctx(db)
    cir = l0.cir_for("basket_small")
    P._persist_release(ctx, cir, {"gates": "first"}, "a" * 64)
    W.record(db, cir.slug, cir.version, kind=W.PHYSICAL_SIZE_FAILED,
             reason="physical sample measured 14.1 cm across the points (claimed 16.0)")
    W.record_reverification(db, cir.slug, cir.version, check="pdf", problem="pdf hash drift")
    before = W.reasons(db, cir.slug, cir.version)
    assert {W.PHYSICAL_SIZE_FAILED, W.QUALITY_REVERIFY} <= set(before["reasons"]), before

    P._persist_release(ctx, cir, {"gates": "second"}, "b" * 64)   # a new release hash
    assert any(a == "gate.recertified" for a, _ in ctx.audits), ctx.audits  # branch reached
    after = W.reasons(db, cir.slug, cir.version)
    assert W.PHYSICAL_SIZE_FAILED in after["reasons"], after       # carry_permanent
    assert W.QUALITY_REVERIFY in after["reasons"], after           # carry_reverification
    assert after["blocks_build"] is True and after["blocks_publish"] is True, after


def test_a_joined_round_tapestry_piece_prints_its_colourwork_in_the_pattern():
    """Review OPUS2J J-7 (W5-INTEG1 x P0-CIR-COLOURWORK): PDF1's joined-round wording
    (`colour_changes.rounds_instruction`) must carry the tapestry sentence and its ends; it
    returned None when no round changed its main colour, so the PDF said nothing about how to
    work a contrast carried inside the stitches."""
    from brambleloop.cir import writer
    from brambleloop.cir.colour_changes import analyse, rounds_instruction
    from brambleloop.cir.compiler import compile_cir
    from brambleloop.cir.model import CIR, Component, Gauge, Op, Repeat, Row

    rows = [Row(1, [Op("sc", 6)], declared_count=6, color="natural"),
            Row(2, [Op("inc", 6)], declared_count=12, color="natural"),
            Row(3, [Repeat([Op("sc", 2), Op("sc", 2, color="rust")], times=3)],
                declared_count=12, color="natural"),
            Row(4, [Op("sc", 12)], declared_count=12, color="natural")]
    cir = CIR(slug="j7-fixture", title="J7 Fixture", version="1.0.0",
              construction="joined_rounds", gauge=Gauge(18, 20),
              colors={"natural": "#EFE6D2", "rust": "#A4502C"},
              components=[Component("body", "joined_rounds", foundation=0,
                                    foundation_kind="magic_ring", rows=rows)])
    plan = analyse(cir)["body"]
    assert plan.changes == 0 and plan.tapestry_rows == [3], plan
    line = rounds_instruction(plan)
    assert line and "Colourwork round 3" in line and "Ends to weave in: about" in line, line
    text = writer.write_pattern(cir, compile_cir(cir))
    assert "Colourwork round 3" in text, "the written pattern omits the tapestry instruction"

if __name__ == "__main__":
    fails = 0
    tests = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        try:
            fn()
            print("OK  ", name, flush=True)
        except Exception as e:  # noqa: BLE001
            fails += 1
            import traceback

            traceback.print_exc()
            print("FAIL", name, f"{type(e).__name__}: {str(e)[:500]}", flush=True)
    print(f"{len(tests) - fails}/{len(tests)} passed")
    sys.exit(1 if fails else 0)
