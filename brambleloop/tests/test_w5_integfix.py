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
    from sqlalchemy import select
    from brambleloop.core.models import AuditLog, Job

    with db.session() as session:
        assert session.scalar(select(AuditLog).where(AuditLog.action == "gate.recertified"))
        assert session.scalar(select(Job).where(Job.job_type == "gate.quality"))
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


def _rounds_cir(rows_spec, *, make=1):
    """A joined-round piece: rows_spec = [(main colour, ops, declared count), ...]."""
    from brambleloop.cir.model import CIR, Component, Gauge, Row

    rows = [Row(i, ops, declared_count=n, color=colour)
            for i, (colour, ops, n) in enumerate(rows_spec, start=1)]
    return CIR(slug="j7-rounds", title="J7 Rounds", version="1.0.0",
               construction="joined_rounds", gauge=Gauge(18, 20),
               colors={"natural": "#EFE6D2", "rust": "#A4502C"},
               components=[Component("body", "joined_rounds", foundation=0,
                                     foundation_kind="magic_ring", rows=rows, make=make)])


def test_a_yarn_worked_again_as_a_contrast_is_never_cut_or_rested():
    """Review J7-1 (MED) / J7-2: the rounds wording decided "Cut X ... not used again" and
    "X rests" from main colours only, so a yarn that returns as a tapestry contrast was told
    to be cut (contradicting "Do not cut" and the ends count) or to rest while being worked.
    Also pins J7-3 mutants: the tapestry sentence when a main colour changes too (M2), its
    place before the ends line (M8), "on each <piece>" (M5) and the rounds routing (M4)."""
    from brambleloop.cir import writer
    from brambleloop.cir.colour_changes import analyse, rounds_instruction
    from brambleloop.cir.compiler import compile_cir
    from brambleloop.cir.model import Op, Repeat

    tap = [Repeat([Op("sc", 2), Op("sc", 2, color="natural")], times=3)]
    # Case C: natural rounds 1-2, rust 3-5, natural back as a contrast in rust round 4.
    case_c = _rounds_cir([("natural", [Op("sc", 6)], 6), ("natural", [Op("inc", 6)], 12),
                          ("rust", [Op("sc", 12)], 12), ("rust", tap, 12),
                          ("rust", [Op("sc", 12)], 12)])
    plan = analyse(case_c)["body"]
    assert plan.changes == 1 and plan.tapestry_rows == [4], plan
    line = rounds_instruction(plan)
    assert "Cut natural after Rnd 2" not in line, line            # J7-1: it returns in Rnd 4
    assert "Cut natural after Rnd 4" in line, line                # its real last use
    assert "pick it up again for Rnd 4" in line, line
    assert "Colourwork round 4" in line, line                     # M2: changes > 0 keeps it
    assert line.index("Colourwork round 4") < line.index("Ends to weave in"), line  # M8
    assert f"Ends to weave in: about {plan.ends}." in line and plan.ends == 4, line
    text = writer.write_pattern(case_c, compile_cir(case_c))
    assert "falls at the join" in text and "Colourwork round 4" in text   # M4: rounds path
    assert "Cut natural after Rnd 2" not in text
    # Case D: natural is worked as a contrast in round 3, so it does not "rest" there.
    case_d = _rounds_cir([("natural", [Op("sc", 6)], 6), ("natural", [Op("inc", 6)], 12),
                          ("rust", [Repeat([Op("sc", 2), Op("sc", 2, color="natural")],
                                           times=3)], 12),
                          ("natural", [Op("sc", 12)], 12)])
    assert "rests (Rnd 3)" not in rounds_instruction(analyse(case_d)["body"])   # J7-2
    # M5: a piece made several times says the ends are per piece.
    multi = _rounds_cir([("natural", [Op("sc", 6)], 6), ("natural", [Op("inc", 6)], 12),
                         ("natural", [Repeat([Op("sc", 2), Op("sc", 2, color="rust")],
                                             times=3)], 12)], make=2)
    assert "on each body" in rounds_instruction(analyse(multi)["body"], piece="body", make=2)


def test_a_two_colour_claim_needs_exactly_two_real_colours():
    """Review INTEG5G-1: "two colour" is a colour-count claim. It is backed by fabric that works
    exactly two colours with the minority >= 10% of stitches -- a striped two-colour blanket --
    and refused for one colour, a single contrast stitch, a one-row trim, or three colours."""
    from brambleloop.products import launch0 as L

    def motif(rows):
        return L.colourwork_motif(rows)

    stripes = [["a"] * 20, ["b"] * 20] * 5                      # 50 / 50
    ok, why = L.technique_backed("two colours", motif(stripes))
    assert ok, why
    for name, rows in (
            ("one colour", [["a"] * 20] * 10),
            ("one contrast stitch", [["a"] * 20] * 9 + [["a"] * 19 + ["b"]]),
            ("one trim row in twenty", [["a"] * 20] * 19 + [["b"] * 20]),   # 5% < 10%
            ("three colours", [["a"] * 20, ["b"] * 20, ["c"] * 20] * 4)):
        ok, why = L.technique_backed("two colours", motif(rows))
        assert not ok, (name, why)
    assert L.colourwork_claims("two color crochet") == ("two colours",)
    # technique words keep their own rule: stripes never back "colourwork"
    assert not L.technique_backed("colourwork", motif(stripes))[0]

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
