"""Independent probes, SECREVIEW PHYSFIX b8d3dee. Run against the subject tree:
    cd brambleloop && PYTHONPATH=src:tests python tests/test_secreview_physfix_b8d3dee_probes.py
P5 prints FINDING while R35 is open (it does not assert, so it never breaks a suite)."""
import sys
import os
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(_HERE, "..", "src"), _HERE]
import test_physfix as T
from sqlalchemy import select
from brambleloop.core.models import Incident, AuditLog
from brambleloop.gates.incidents import IncidentTracker
from brambleloop.publish import withholding
from brambleloop.runtime import release as R

OWNER = dict(actor="owner:cc:s", stepped_up=True, reason="probe")

def halts(db, slug):
    return [i for i in IncidentTracker(db).open_incidents(slug) if i.signature.startswith("physical-size:")]

def ptid(job):
    o = job.outputs or {}
    if "physical_test_id" not in o: raise RuntimeError(f"job {job.status} {getattr(job, 'error', None)} {o}")
    return o["physical_test_id"]

def fail(db, cir, tester="tester-1"):
    return T._run(db, "physical.record", T._inputs(cir, scope="full_make", holds_shape=True, tester_ref=tester,
                  measured_width_cm=40.0, content_hash=R._content_hash_of(cir)))

def good(db, cir, tester):
    return T._run(db, "physical.record", T._inputs(cir, scope="full_make", holds_shape=True, tester_ref=tester,
                  content_hash=R._content_hash_of(cir)))

def p1_three_failures_interleaved():
    db = T._db(); vs = []
    for i, v in enumerate(["1.2.0", "1.3.0", "1.4.0"]):
        c = T._basket_medium(); c.version = v; T._certify(db, c); vs.append(c)
        fail(db, c, "tester-1")
        good(db, c, "tester-2")      # interleaved passing make of the same release
    hs = halts(db, vs[0].slug); assert len(hs) == 1, hs
    got = [r["version"] for r in R.measured_releases(hs[0].detail)]
    assert got == ["1.2.0", "1.3.0", "1.4.0"], got
    for c in vs:                          # every failed release's make is refused
        g = good(db, c, "tester-3")
        try: R.lift_size_halt(db, incident_id=hs[0].id, physical_test_id=ptid(g), same_design_confirmed=True, **OWNER)
        except R.SizeHaltLiftRefused: pass
        else: raise AssertionError(f"lifted on {c.version}")
    fx = T._geometry_changed_medium("1.5.0"); T._certify(db, fx)
    out = R.lift_size_halt(db, incident_id=hs[0].id, physical_test_id=ptid(good(db, fx, "tester-2")), **OWNER)
    assert sorted(out["withheld"]) == sorted(f"{c.slug}@{c.version}" for c in vs), out
    for c in vs: assert T._size_withheld(db, c)
    print("P1 ok: 3 failures interleaved with passes; all refused as evidence, all withheld")

def p2_two_open_halts():
    db = T._db()
    a = T._basket_medium(); T._certify(db, a); fail(db, a)
    g = T._geometry_changed_medium("1.3.0"); T._certify(db, g); fail(db, g, "tester-2")
    hs = halts(db, a.slug); assert len(hs) == 2, hs
    i1 = [h for h in hs if R.measured_releases(h.detail)[0]["version"] == a.version][0]
    try: R.lift_size_halt(db, incident_id=i1.id, physical_test_id=ptid(good(db, g, "tester-3")), same_design_confirmed=True, **OWNER)
    except R.SizeHaltLiftRefused as e: assert "1.3.0" in str(e), e
    else: raise AssertionError("other halt's failed release accepted")
    fx = T._geometry_changed_medium("1.4.0"); fx.components[0].rows.append(fx.components[0].rows[-1]) if False else None
    T._certify(db, fx)
    try:
        out = R.lift_size_halt(db, incident_id=i1.id, physical_test_id=ptid(good(db, fx, "t")), same_design_confirmed=True, **OWNER)
        print("P2 note: lift of I1 on 1.4.0 (geometry == 1.3.0's failed halt) ->", out["withheld"], "same_geometry:", out["same_geometry"])
    except R.SizeHaltLiftRefused as e:
        print("P2 note: refused:", str(e)[:160])
    assert IncidentTracker(db).publication_halted(a.slug), "second halt no longer halts"
    print("P2 ok: other open halt's release refused; product stays halted while I2 open")

def p3_legacy():
    db = T._db(); a = T._basket_medium(); T._certify(db, a); fail(db, a)
    with db.session() as s:
        inc = s.scalar(select(Incident).where(Incident.signature.like("physical-size:%")))
        d = dict(inc.detail); d.pop("measured_releases"); inc.detail = d; iid = inc.id
    b = T._basket_medium(); b.version = "1.3.0"; T._certify(db, b); fail(db, b, "tester-2")
    with db.session() as s:
        got = [r["version"] for r in R.measured_releases(s.get(Incident, iid).detail)]
    assert got == [a.version, "1.3.0"], got
    print("P3 ok: legacy single-release incident is carried into the list on restatement")

def p4_atomic():
    db = T._db(); a = T._basket_medium(); T._certify(db, a); fail(db, a)
    b = T._basket_medium(); b.version = "1.3.0"; T._certify(db, b); fail(db, b, "tester-2")
    fx = T._geometry_changed_medium("1.4.0"); T._certify(db, fx); ev = ptid(good(db, fx, "tester-3"))
    iid = halts(db, a.slug)[0].id
    real = withholding.record_in; n = [0]
    def boom(*a_, **k):
        n[0] += 1
        if n[0] == 2: raise RuntimeError("injected")
        return real(*a_, **k)
    withholding.record_in = boom
    try:
        try: R.lift_size_halt(db, incident_id=iid, physical_test_id=ev, **OWNER)
        except RuntimeError: pass
    finally: withholding.record_in = real
    with db.session() as s:
        assert not s.get(Incident, iid).resolved
        assert s.scalar(select(AuditLog).where(AuditLog.action == withholding.DURABLE_AUDIT)) is None
    assert not T._size_withheld(db, a), "partial withholding committed"
    print("P4 ok: failure mid-withholding rolls everything back")

def p5_across_incident_lifetimes():
    """A fails (I1), owner lifts I1 on a real fix -> A withheld. Later the fix fails (I2).
    Is a passing make of A -- the release a size halt measured wrong -- accepted to lift I2?"""
    db = T._db(); a = T._basket_medium(); T._certify(db, a); fail(db, a)
    fx = T._geometry_changed_medium("1.3.1"); T._certify(db, fx)
    i1 = halts(db, a.slug)[0].id
    R.lift_size_halt(db, incident_id=i1, physical_test_id=ptid(good(db, fx, "tester-2")), **OWNER)
    assert T._size_withheld(db, a)
    fail(db, fx, "t")
    hs = halts(db, a.slug); assert len(hs) == 1, [(h.id, h.signature, h.resolved) for h in hs]
    ev = ptid(good(db, a, "t1"))
    try:
        out = R.lift_size_halt(db, incident_id=hs[0].id, physical_test_id=ev, same_design_confirmed=True, **OWNER)
    except R.SizeHaltLiftRefused as e:
        print("P5 ok: refused:", str(e)[:200]); return
    print("P5 FINDING: I2 lifted on a make of", a.version, "(withheld by I1) ->", out,
          "| halted now:", IncidentTracker(db).publication_halted(a.slug))

for p in (p1_three_failures_interleaved, p2_two_open_halts, p3_legacy, p4_atomic, p5_across_incident_lifetimes):
    try: p()
    except Exception as e:
        import traceback; print(p.__name__, "ERROR"); traceback.print_exc()
