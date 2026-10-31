"""Independent SECREVIEW of PHYSFIX-PHOTO 42eac691: adversarial probes for the F1 design digest.

Each test asserts the SAFE behaviour; a FAIL is a finding. Run from brambleloop/ with
    PYTHONPATH=src:tests python research/final_build/w4/secreview_physfix_42eac69_probes.py
"""
from __future__ import annotations

import sys

from test_physfix import (  # noqa: E402
    _db, _run, _certify, _inputs, _basket, _basket_medium, select, Incident)


def _halted_medium():
    from brambleloop.gates.incidents import IncidentTracker

    db = _db()
    cir = _basket_medium()
    _certify(db, cir)
    job = _run(db, "physical.record", _inputs(cir, scope="full_make", holds_shape=True,
                                              measured_width_cm=40.0))
    assert (job.outputs or {})["publication_halted"], job.outputs
    return db, cir, IncidentTracker(db)


def _same_geometry(**changes):
    c = _basket_medium()
    c.version = "1.3.0"
    for k, v in changes.items():
        setattr(c, k, v)
    return c


# ---- F1 residual: cosmetic changes count as "a different design" ---------------------------

def test_title_only_change_does_not_certify_past_a_size_halt():
    db, cir, _ = _halted_medium()
    out = _certify(db, _same_geometry(title=cir.title + " (revised)"))
    assert out.get("halted_by_incident") is True, ("retitle certified", out.get("granted"))


def test_trailing_space_in_title_does_not_certify_past_a_size_halt():
    db, cir, _ = _halted_medium()
    out = _certify(db, _same_geometry(title=cir.title + " "))
    assert out.get("halted_by_incident") is True, ("whitespace certified", out.get("granted"))


def test_designer_notes_change_does_not_certify_past_a_size_halt():
    db, cir, _ = _halted_medium()
    out = _certify(db, _same_geometry(designer_notes=(cir.designer_notes or "") + " Enjoy!"))
    assert out.get("halted_by_incident") is True, ("notes edit certified", out.get("granted"))


def test_a_second_make_of_the_same_geometry_never_lifts_the_halt():
    """The fix's own rule ("a sample of the halted design never resolves its own halt"),
    evaded by retitling: tester 1 measured 40 cm; tester 2 makes the identical geometry,
    reports the twin's size, and the conflicting evidence silently resolves the P1."""
    db, cir, tracker = _halted_medium()
    retitled = _same_geometry(title=cir.title + " (revised)")
    _certify(db, retitled)
    job = _run(db, "physical.record", _inputs(retitled, scope="full_make", holds_shape=True,
                                              tester_ref="tester-2"))
    assert not (job.outputs or {}).get("size_halts_lifted"), job.outputs
    assert tracker.publication_halted(cir.slug), "identical geometry lifted its own halt"


# ---- controls: these should hold -----------------------------------------------------------

def test_control_version_only_relabel_stays_halted():
    db, cir, tracker = _halted_medium()
    out = _certify(db, _same_geometry())
    assert out.get("halted_by_incident") is True
    assert tracker.publication_halted(cir.slug)


def test_control_certification_alone_never_resolves():
    db, cir, tracker = _halted_medium()
    _certify(db, _same_geometry(title=cir.title + " (revised)"))
    with db.session() as s:
        inc = s.scalar(select(Incident).where(Incident.signature.like("physical-size:%")))
        assert not inc.resolved


def test_control_halt_without_digest_blocks_every_design_of_the_product():
    from brambleloop.gates.incidents import IncidentTracker
    from brambleloop.quality import physical

    db = _db()
    cir = _basket_medium()
    _certify(db, cir)
    real = physical.design_digest
    physical.design_digest = lambda *a, **k: None       # an unreadable design at record time
    try:
        _run(db, "physical.record", _inputs(cir, scope="full_make", holds_shape=True,
                                            measured_width_cm=40.0))
    finally:
        physical.design_digest = real
    out = _certify(db, _same_geometry(title=cir.title + " (revised)"))
    assert out.get("halted_by_incident") is True, out
    assert IncidentTracker(db).publication_halted(cir.slug)
    # ...and a passed full make of a different design does not resolve a digest-less halt
    fixed = _same_geometry(title=cir.title + " (revised)")
    _run(db, "physical.record", _inputs(fixed, scope="full_make", holds_shape=True))
    assert IncidentTracker(db).publication_halted(cir.slug)


def test_control_halt_on_one_product_does_not_halt_another():
    from brambleloop.gates.incidents import IncidentTracker

    db, cir, _ = _halted_medium()
    small = _basket()
    assert not _certify(db, small).get("halted_by_incident")
    assert not IncidentTracker(db).publication_halted(small.slug)


if __name__ == "__main__":
    fails = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    for name, fn in tests:
        try:
            fn(); print("OK  ", name)
        except Exception as exc:  # noqa: BLE001
            fails += 1; print("FAIL", name, repr(exc)[:400])
    print(f"{len(tests) - fails}/{len(tests)} passed")
    sys.exit(1 if fails else 0)
