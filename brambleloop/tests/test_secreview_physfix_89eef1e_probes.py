"""Independent SECREVIEW of PHYSFIX-PHOTO 89eef1ec: probes for the geometry-only design digest.

Each test asserts the SAFE behaviour; a FAIL is a finding. Run from brambleloop/ with
    PYTHONPATH=src:tests python research/final_build/w4/secreview_physfix_89eef1e_probes.py

Adopted by W-PHYSFIX as a regression suite for R5. The one change: the path line below, which
pointed at `research/final_build/w4/../../../tests`, now points at this file's own directory.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_physfix import _db, _run, _certify, _inputs, _basket_medium  # noqa: E402
from brambleloop.cir.model import CIR, Op, Repeat  # noqa: E402
from brambleloop.quality.physical import design_digest  # noqa: E402


def _halted_medium():
    from brambleloop.gates.incidents import IncidentTracker

    db = _db()
    cir = _basket_medium()
    _certify(db, cir)
    job = _run(db, "physical.record", _inputs(cir, scope="full_make", holds_shape=True,
                                              measured_width_cm=40.0))
    assert (job.outputs or {})["publication_halted"], job.outputs
    return db, cir, IncidentTracker(db)


def _relabel(mut):
    # deep copy: the generator shares its Gauge object between builds
    c = CIR.from_dict(_basket_medium().to_dict())
    c.version = "1.3.0"
    mut(c)
    return c


def _expand_repeats(c):
    """Same stitches, other notation: `[inc] x6` written out as `inc, inc, inc, inc, inc, inc`."""
    for comp in c.components:
        for r in comp.rows:
            out = []
            for o in r.ops:
                if isinstance(o, Repeat) and o.times and all(isinstance(x, Op) for x in o.ops):
                    out += [Op(x.stitch, x.count, loop=x.loop, spans=x.spans)
                            for _ in range(o.times) for x in o.ops]
                else:
                    out.append(o)
            r.ops = out


def _upper_gauge_weight(c):
    c.gauge.yarn_weight = (c.gauge.yarn_weight or "").upper()


def _int_vs_float_gauge(c):
    c.gauge.stitches_per_10cm = 13
    c.gauge.rows_per_10cm = 14


def _float_gauge(c):
    c.gauge.stitches_per_10cm = 13.0
    c.gauge.rows_per_10cm = 14.0


# ---- digest-level: notation and representation are not geometry ----------------------------

def test_expanded_repeat_is_the_same_design():
    assert design_digest(_relabel(_expand_repeats)) == design_digest(_basket_medium())


def test_gauge_yarn_weight_case_is_the_same_design():
    assert design_digest(_relabel(_upper_gauge_weight)) == design_digest(_basket_medium())


def test_int_and_float_gauge_are_the_same_design():
    assert design_digest(_relabel(_int_vs_float_gauge)) == design_digest(_relabel(_float_gauge))


# ---- end to end: does the notation change certify past / lift the halt ---------------------

def test_expanded_repeat_does_not_certify_past_a_size_halt():
    db, cir, _ = _halted_medium()
    out = _certify(db, _relabel(_expand_repeats))
    assert out.get("halted_by_incident") is True, ("notation change certified", out.get("granted"))


def test_expanded_repeat_make_does_not_lift_the_halt():
    db, cir, tracker = _halted_medium()
    same = _relabel(_expand_repeats)
    _certify(db, same)
    job = _run(db, "physical.record", _inputs(same, scope="full_make", holds_shape=True,
                                              tester_ref="tester-2"))
    assert not (job.outputs or {}).get("size_halts_lifted"), job.outputs
    assert tracker.publication_halted(cir.slug), "same stitches lifted their own halt"


def test_gauge_case_does_not_certify_past_a_size_halt():
    db, cir, _ = _halted_medium()
    out = _certify(db, _relabel(_upper_gauge_weight))
    assert out.get("halted_by_incident") is True, ("case change certified", out.get("granted"))


# ---- controls -------------------------------------------------------------------------------

def test_control_same_geometry_second_make_routes_to_owner_and_stays_halted():
    db, cir, tracker = _halted_medium()
    # tester 2 makes the very release tester 1 measured wrong, and reports the stated size
    job = _run(db, "physical.record", _inputs(cir, scope="full_make", holds_shape=True,
                                              tester_ref="tester-2"))
    out = job.outputs or {}
    assert not out.get("size_halts_lifted"), out
    assert str(out.get("owner_review") or "").startswith("physical_size_conflict:"), out
    assert tracker.publication_halted(cir.slug)


def test_control_a_real_geometry_change_is_a_different_design():
    c = _relabel(lambda c: setattr(c.gauge, "stitches_per_10cm", c.gauge.stitches_per_10cm + 1))
    assert design_digest(c) != design_digest(_basket_medium())


if __name__ == "__main__":
    fails = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    for name, fn in tests:
        try:
            fn(); print("OK  ", name)
        except Exception as exc:  # noqa: BLE001
            fails += 1; print("FAIL", name, repr(exc)[:300])
    print(f"{len(tests) - fails}/{len(tests)} passed")
    sys.exit(1 if fails else 0)
