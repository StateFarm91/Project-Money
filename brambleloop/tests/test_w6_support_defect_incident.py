"""W6 P0-SUPPORT-DEFECT-INCIDENT: three support cases on the same row of a release act.

Real SQLite file, real Worker, real handlers (`support.triage`, `cir.twin`, `cir.reverse`), a
real certified launch-0 release and cases drafted by the real support department (so their
`cited_rows` come from the Concierge, not from the test):

* 3 cases on one row -> one correlated incident, one deterministic re-verification of that
  release (one `cir.twin` + one `cir.reverse` job), and that release's publication withheld;
* a 4th case adds nothing (no incident, job or hold; the open incident's count is refreshed);
* a different product is unaffected;
* the re-verification passing is recorded as evidence but does NOT clear the hold (the release
  already passed those checks to be certified; independent review W6 2026-11-07 HIGH);
* an owner-resolved incident releases its hold on the next triage, and the row is never
  re-escalated afterwards;
* one buyer writing three times does not escalate (distinct buyers);
* a failure between committing the incident and placing the hold is repaired by the next
  triage (fail-closed, self-healing);
* the hold targets the currently certified release when a citing case names it, not an older
  majority version.

Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_w6_support_defect_incident.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
os.environ["BRAMBLELOOP_PHASE"] = "shadow"

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.build2 import reachability  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (Incident, Job, JobStatus, PatternVersion, Phase,  # noqa: E402
                                     Product)
from brambleloop.products import launch0  # noqa: E402
from brambleloop.publish import withholding as W  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401 - registers handlers
from brambleloop.runtime import release  # noqa: E402,F401 - registers handlers
from brambleloop.runtime.worker import Worker  # noqa: E402
from brambleloop.support import defects  # noqa: E402
from brambleloop.support.department import CustomerExperience  # noqa: E402

ROW = 3
QUESTION = f"How many stitches should I have at the end of row {ROW}? My count is off."


def _cirs():
    keys = sorted(launch0.BUILDERS)
    return launch0.cir_for(keys[0]), launch0.cir_for(keys[1])


def _db(*cirs):
    path = os.path.join(tempfile.mkdtemp(prefix="w6_defect_"), "defect.sqlite")
    db = Database(f"sqlite:///{path}")
    db.create_all()
    Registry(db).seed_defaults()
    with db.session() as s:
        for cir in cirs:
            p = Product(slug=cir.slug, title=cir.title, status="certified")
            s.add(p)
            s.flush()
            s.add(PatternVersion(product_id=p.id, version=cir.version, cir_json=cir.to_dict(),
                                 certified=True, release_hash="r" * 64,
                                 certificate={"granted": True}))
    return db


def _case(db, cir, n: int, buyer: str | None = None, version: str | None = None) -> None:
    reply = CustomerExperience(db).handle(customer_ref=buyer or f"buyer-{cir.slug}-{n}",
                                          message=QUESTION, cir=cir, product_slug=cir.slug,
                                          version=version or cir.version)
    assert reply.cited_rows == [ROW], reply


def _work(db, job_types, key=None, inputs=None) -> int:
    """Enqueue (optionally) and run every pending job of these types through a Worker."""
    if key:
        JobQueue(db).enqueue("support", "support.triage", inputs or {}, priority=0,
                             idempotency_key=key)
    ran = 0
    w = Worker(db, "w6-defect", phase=Phase.SHADOW, job_types=list(job_types))
    while w.run_once():
        ran += 1
        assert ran < 50
    with db.session() as s:
        bad = [(j.job_type, j.status, j.last_error) for j in s.scalars(select(Job).where(
            Job.job_type.in_(list(job_types)), Job.status != JobStatus.DONE,
            Job.status != JobStatus.PENDING))]
    assert not bad, bad
    return ran


def _triage(db, key):
    _work(db, ["support.triage"], key=key)


def _incidents(db, slug=None):
    with db.session() as s:
        return [(i.signature, i.severity, i.resolved, i.halts_publication, dict(i.detail or {}))
                for i in s.scalars(select(Incident).order_by(Incident.id))
                if slug is None or i.product_slug == slug]


def _reverify_jobs(db):
    with db.session() as s:
        return [(j.job_type, j.status, dict(j.inputs or {})) for j in s.scalars(
            select(Job).where(Job.job_type.in_(["cir.twin", "cir.reverse"])))]


def test_three_cases_on_one_row_open_an_incident_reverify_and_withhold_only_that_release():
    a, b = _cirs()
    db = _db(a, b)
    for n in range(3):
        _case(db, a, n)
    _case(db, b, 0)                     # one case on another product: below threshold
    _triage(db, "t1")

    sig = defects.signature(a.slug, a.version, ROW)
    inc = [i for i in _incidents(db) if i[0].startswith(defects.SIGNATURE)]
    assert [i[0] for i in inc] == [sig], inc
    _sig, sev, resolved, halts, detail = inc[0]
    assert sev == "P1" and not resolved and halts is False and detail["mentions"] == 3
    jobs = _reverify_jobs(db)
    assert sorted(j[0] for j in jobs) == ["cir.reverse", "cir.twin"], jobs
    assert all(j[2]["slug"] == a.slug and j[2]["version"] == a.version
               and j[2]["support_defect"] == sig for j in jobs), jobs
    held = W.reasons(db, a.slug, a.version)
    assert held["blocks_publish"] is True and W.QUALITY_REVERIFY in held["reasons"], held
    assert defects.hold_check(ROW) in held["reasons"][W.QUALITY_REVERIFY]["reason"]
    assert held["blocks_build"] is False          # publication only; a fix can still ship

    # A 4th case, and a repeat triage: nothing new.
    _case(db, a, 3)
    _triage(db, "t2")
    _triage(db, "t3")
    inc2 = [i for i in _incidents(db) if i[0].startswith(defects.SIGNATURE)]
    assert len(inc2) == 1 and inc2[0][4]["mentions"] == 4 and not inc2[0][2], inc2
    assert len(_reverify_jobs(db)) == 2
    assert W.reasons(db, a.slug, a.version)["blocks_publish"] is True

    # The other product is untouched.
    assert W.reasons(db, b.slug, b.version)["withheld"] is False
    assert _incidents(db, b.slug) == []

    # The deterministic re-verification runs and passes. That is evidence, not a release:
    # the hold stays, the incident stays open and records that the compiler does not
    # reproduce the defect.
    assert _work(db, ["cir.twin", "cir.reverse"]) == 2
    assert all(j[1] == JobStatus.DONE for j in _reverify_jobs(db))
    after = W.reasons(db, a.slug, a.version)
    assert after["blocks_publish"] is True and W.QUALITY_REVERIFY in after["reasons"], after
    inc3 = [i for i in _incidents(db) if i[0].startswith(defects.SIGNATURE)]
    assert len(inc3) == 1 and inc3[0][2] is False, inc3
    assert sorted(inc3[0][4]["passed_checks"]) == ["cir.reverse", "cir.twin"], inc3
    assert "does not reproduce" in inc3[0][4]["reverification"], inc3
    assert not [i for i in _incidents(db) if i[0].startswith("quality.reverify:")]

    # Later triage keeps it held and adds no jobs (idempotency keys).
    _triage(db, "t4")
    assert len([i for i in _incidents(db) if i[0].startswith(defects.SIGNATURE)]) == 1
    assert len(_reverify_jobs(db)) == 2
    assert W.reasons(db, a.slug, a.version)["blocks_publish"] is True


def test_an_owner_resolved_defect_incident_releases_its_hold():
    a, _b = _cirs()
    db = _db(a)
    for n in range(3):
        _case(db, a, n)
    _triage(db, "o1")
    assert W.reasons(db, a.slug, a.version)["blocks_publish"] is True
    from brambleloop.ops import incident_lifecycle

    with db.session() as s:
        incident_lifecycle.resolve_signatures(
            s, [defects.signature(a.slug, a.version, ROW)],
            resolution="owner: the buyers misread the stitch key; not a pattern defect")
    _triage(db, "o2")
    assert W.reasons(db, a.slug, a.version)["withheld"] is False
    # A further case after the decision does not re-escalate the same release+row.
    _case(db, a, 3)
    _triage(db, "o3")
    assert W.reasons(db, a.slug, a.version)["withheld"] is False
    assert len([i for i in _incidents(db) if i[0].startswith(defects.SIGNATURE)]) == 1


def test_one_buyer_writing_three_times_does_not_hold_a_release():
    a, _b = _cirs()
    db = _db(a)
    for n in range(3):
        _case(db, a, n, buyer="buyer-same")
    _triage(db, "b1")
    assert [i for i in _incidents(db) if i[0].startswith(defects.SIGNATURE)] == []
    assert W.reasons(db, a.slug, a.version)["withheld"] is False
    _case(db, a, 3)                      # second and third distinct buyers
    _case(db, a, 4)
    _triage(db, "b2")
    assert W.reasons(db, a.slug, a.version)["blocks_publish"] is True


def test_a_failure_before_the_hold_is_repaired_by_the_next_triage():
    a, _b = _cirs()
    db = _db(a)
    for n in range(3):
        _case(db, a, n)
    real = W.record_reverification
    calls = {"n": 0}

    def flaky(*args, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("transient: hold write failed")
        return real(*args, **kw)

    W.record_reverification = flaky
    try:
        try:
            _triage(db, "f1")
        except AssertionError:
            pass                          # the triage job failed; that is the transient fault
        inc = [i for i in _incidents(db) if i[0].startswith(defects.SIGNATURE)]
        assert len(inc) == 1 and not inc[0][2], inc         # incident committed ...
        assert W.reasons(db, a.slug, a.version)["withheld"] is False  # ... hold missing
        W.record_reverification = real
        JobQueue(db).enqueue("support", "support.triage", {}, priority=0, idempotency_key="f2")
        w = Worker(db, "w6-defect", phase=Phase.SHADOW, job_types=["support.triage"])
        while w.run_once():
            pass
        with db.session() as s:
            j = s.scalars(select(Job).where(Job.idempotency_key == "f2")).one()
            assert j.status == JobStatus.DONE, (j.status, j.last_error)
    finally:
        W.record_reverification = real
    assert W.reasons(db, a.slug, a.version)["blocks_publish"] is True
    assert sorted(j[0] for j in _reverify_jobs(db)) == ["cir.reverse", "cir.twin"]


def test_buyers_are_counted_per_version_and_the_current_release_is_preferred():
    a, _b = _cirs()
    db = _db(a)
    with db.session() as s:                                 # an older stored release
        p = s.scalar(select(Product).where(Product.slug == a.slug))
        s.add(PatternVersion(product_id=p.id, version="0.9.0", cir_json=a.to_dict(),
                             certified=False, release_hash="o" * 64, certificate={}))
    for n in range(4):
        _case(db, a, n, version="0.9.0")                    # 4 buyers on the old version
    _case(db, a, 10)                                        # 2 buyers on the current one
    _case(db, a, 11)
    _triage(db, "v1")
    sigs = [i[0] for i in _incidents(db) if i[0].startswith(defects.SIGNATURE)]
    # The current release is NOT held on old-version buyers (delta review N-2) ...
    assert W.reasons(db, a.slug, a.version)["withheld"] is False, sigs
    # ... the old version, which alone reaches the threshold, is.
    assert sigs == [defects.signature(a.slug, "0.9.0", ROW)], sigs
    _case(db, a, 12)                                        # a 3rd buyer on the current
    _triage(db, "v2")
    assert W.reasons(db, a.slug, a.version)["blocks_publish"] is True
    sigs = [i[0] for i in _incidents(db) if i[0].startswith(defects.SIGNATURE)]
    assert defects.signature(a.slug, a.version, ROW) in sigs, sigs


def test_no_incident_for_a_version_that_is_not_stored():
    a, _b = _cirs()
    db = _db(a)
    for n in range(3):
        _case(db, a, n, version="7.7.7")
    _triage(db, "u1")
    assert [i for i in _incidents(db) if i[0].startswith(defects.SIGNATURE)] == []


def test_the_owner_decides_through_a_named_path_and_a_card():
    from brambleloop.core.models import OwnerAction
    from brambleloop.ops import incident_lifecycle

    a, _b = _cirs()
    db = _db(a)
    for n in range(3):
        _case(db, a, n)
    _triage(db, "d1")
    sig = defects.signature(a.slug, a.version, ROW)
    with db.session() as s:
        inc = s.scalar(select(Incident).where(Incident.signature == sig))
        inc_id = inc.id
        cards = [c.requirement_key for c in s.scalars(select(OwnerAction).where(
            OwnerAction.done == False))]  # noqa: E712
    assert defects.CARD_PREFIX + sig in cards, cards
    assert incident_lifecycle.kind_of(sig) in incident_lifecycle.REMEDIATION
    with db.session() as s:
        snap = incident_lifecycle.snapshot(s)
    assert sig not in snap["needs_owner_path"], snap["needs_owner_path"]
    held_before = W.reasons(db, a.slug, a.version)
    _case(db, a, 3)                                         # a new mention: no hold churn
    _triage(db, "d2")
    assert W.reasons(db, a.slug, a.version) == held_before   # N-4

    for bad in [("maybe", "a sentence long enough"), ("confirmed", "short")]:
        try:
            defects.record_owner_decision(db, inc_id, *bad)
            raise AssertionError("accepted " + repr(bad))
        except defects.DecisionRefused:
            pass
    out = defects.record_owner_decision(db, inc_id, "confirmed",
                                        "the row 3 count really is wrong in this release")
    assert out["hold_released"] is False
    assert W.reasons(db, a.slug, a.version)["blocks_publish"] is True
    with db.session() as s:
        inc = s.get(Incident, inc_id)
        assert not inc.resolved and inc.detail["owner_decision"]["decision"] == "confirmed"
    # Re-decided after review: not a defect -> resolved, hold released, card closed.
    out = defects.record_owner_decision(db, inc_id, "not_a_defect",
                                        "buyers misread the stitch key; the count is right")
    assert out["hold_released"] is True, out
    assert W.reasons(db, a.slug, a.version)["withheld"] is False
    with db.session() as s:
        assert not [c for c in s.scalars(select(OwnerAction).where(
            OwnerAction.requirement_key == defects.CARD_PREFIX + sig,
            OwnerAction.done == False))]  # noqa: E712


def test_a_newer_certified_version_supersedes_but_the_old_one_stays_held():
    a, _b = _cirs()
    db = _db(a)
    for n in range(3):
        _case(db, a, n)
    _triage(db, "s1")
    sig = defects.signature(a.slug, a.version, ROW)
    with db.session() as s:
        p = s.scalar(select(Product).where(Product.slug == a.slug))
        s.add(PatternVersion(product_id=p.id, version="9.0.0", cir_json=a.to_dict(),
                             certified=True, release_hash="n" * 64,
                             certificate={"granted": True}))
    _triage(db, "s2")
    inc = [i for i in _incidents(db) if i[0] == sig]
    assert inc and inc[0][2] is True and "superseded" in inc[0][4]["resolution"], inc
    assert W.reasons(db, a.slug, a.version)["blocks_publish"] is True   # old stays held
    assert W.reasons(db, a.slug, "9.0.0")["withheld"] is False


def test_the_defect_path_is_reached_from_the_runtime():
    reachability.reachable.cache_clear()
    reachability._references.cache_clear()
    v = reachability.reached("support/defects.py")
    assert v["reached"], v


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    print(f"{fails} failure(s)")
    sys.exit(1 if fails else 0)
