"""eng/halt-380: why the stale-artefact rebuilds never verified, and the systemic halt with them.

Production 7b250d61, readback 2026-11-21T03:29Z: systemic halt #380 open since 2026-10-11; 12
products both `rebuild-incomplete` and `stale-artefact`; 112 open stale-artefact incidents;
the sentinel reads 111 of 600 stale; chain.rebuild 7 d: done 171, pending 12; the oldest
unfinished rebuild 0.13 h old (a fresh pending rebuild every hour); no verified rebuild since
2026-11-20T13:12Z; last propagation: 50 already queued, 2 retry waiting.

Hypothesis tested first and REJECTED as stated: a deploy does not re-stale artefacts. The only
code fingerprint an artefact records is `chain:release` = fingerprint(CHAIN_VERSION), a
hand-set constant; deploys that do not bump it move nothing. CHAIN_VERSION 8 -> 9
(ENG-ESTIMATE-CLAIMS, 2026-11-20) did legitimately stale every PDF and listing copy once.

The cause, reproduced below on the real sentinel and chain.rebuild handlers:

H1  `rebuild_graph.enqueue` keyed each product's job on the *estate-wide* change set. Any
    other product's ref moving (a re-engineered design, a new certified release -- hourly in a
    live catalogue) minted a new key for every stale product whose own change had not moved.
    The new key bypassed the in-flight check, RETRY_AFTER and the hold: a fresh attempt every
    hour (pending 12, oldest 0.13 h).
H2  That attempt's stage token was sha(artefacts, fingerprints) -- the same as the first
    attempt's -- so its stage enqueue deduplicated onto the first attempt's stage job,
    finished, dead or partial. Nothing was rebuilt again, ever; the daily retry (whose token
    differs) was never reached because H1 kept the product "recent". The verify pass, bound to
    a stage job it never got, could not bind, and its failures re-opened `rebuild-incomplete`
    even after a verified close.
H3  Those no-op attempts were counted toward REBUILD_MAX_ATTEMPTS and held the product with
    "the stage ran and did not rewrite them" -- untrue -- and nothing re-read the hold.

Fixes: H1 routes a product whose own change already has an attempt through that attempt's key
(in flight -> already queued; ended -> the daily retry, honouring RETRY_AFTER and the hold);
H2 gives every attempt its own stage token; H3 releases, once, a hold whose counted attempts
did not each run a stage of their own (read from the verify passes' own `stage_job`), with one
targeted rebuild at the hold's change. No gate, binding rule, attempt cap or halt rule changed.

Run: cd brambleloop && python3 tests/test_eng_halt_380.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit  # noqa: E702
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import test_eng_stale_rebuild_loop as base  # noqa: E402  (db factory, sentinel runner)
from sqlalchemy import select  # noqa: E402

from brambleloop.core.models import (ArtefactProvenance, AuditLog, Incident,  # noqa: E402
                                     Job, JobStatus, PatternVersion, Phase, Product, utcnow)
from brambleloop.ops import artefacts as A  # noqa: E402
from brambleloop.ops import incident_lifecycle as L  # noqa: E402
from brambleloop.ops import rebuild_graph as G  # noqa: E402
from brambleloop.publish import release_gates  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import release  # noqa: E402
from brambleloop.runtime.worker import Worker  # noqa: E402

# The twelve products production holds in both families (readback 2026-11-21T03:29Z).
SLUGS = ["autumn-oak-mosaic-throw", "cloudline-baby-blanket", "harvest-table-runner",
         "mosaic-placemat-pair", "nordic-forest-mosaic-throw", "nordic-star-ornaments",
         "pet-snuggle-mat", "pressed-flower-motifs", "pumpkin-cluster-set", "spooky-garland",
         "valentine-heart-garland", "winter-village-graphghan"]
CHURN = "churn-new-release"       # a product whose own design moves every hour


def _estate(db, slugs, *, cls_keys=(("pdf", "{s}@1.0.0#pdf-us"),
                                    ("listing_copy", "{s}@1.0.0#listing"))):
    old = A.chain_fingerprint()
    with db.session() as s:
        for slug in slugs:
            p = Product(slug=slug, title=slug)
            s.add(p)
            s.flush()
            s.add(PatternVersion(product_id=p.id, version="1.0.0", cir_json={"slug": slug},
                                 certified=True, release_hash="ab" * 16, certificate={}))
        s.flush()
        for slug in slugs:
            for cls, key in cls_keys:
                A.record(s, artefact_class=cls, artefact_key=key.format(s=slug),
                         product_slug=slug, inputs={"chain:release": old,
                                                    f"cir:{slug}": A.fingerprint(
                                                        {"slug": slug})})


def _run(db, types=("chain.rebuild",), limit=400):
    w = Worker(db, "w-halt380", phase=Phase.SHADOW, job_types=list(types))
    for _ in range(limit):
        if not w.run_once():
            break


def _stages(db, doomed: set[int]):
    """The stage chain, settled: a stage job in `doomed` dies (a deploy killed its render);
    every other one rewrites its product's rows from the current fingerprints, as itself."""
    with db.session() as s:
        cur = A.current_from_db(s)
        for j in s.scalars(select(Job).where(Job.job_type == "assets.build",
                                             Job.status == JobStatus.PENDING)):
            slug = j.inputs["slug"]
            if j.id in doomed:
                j.status, j.finished_at, j.last_error = (JobStatus.DEAD, utcnow(),
                                                         "WorkerLost: lease expired")
                continue
            for row in s.scalars(select(ArtefactProvenance).where(
                    ArtefactProvenance.product_slug == slug)):
                row.inputs = {"chain:release": cur["chain:release"],
                              f"cir:{slug}": cur[f"cir:{slug}"]}
                row.job_id = j.id
            j.status, j.finished_at = JobStatus.DONE, utcnow()


def _age(db, hours=1):
    """One hour passes: every job's clock moves back, so RETRY_AFTER and the 20-minute verify
    delay elapse as they would in production."""
    d = timedelta(hours=hours)
    with db.session() as s:
        for j in s.scalars(select(Job)):
            j.created_at = j.created_at - d if j.created_at else j.created_at
            j.finished_at = j.finished_at - d if j.finished_at else j.finished_at
            j.run_after = j.run_after - d if j.run_after else j.run_after


def _move_churn(db, n):
    with db.session() as s:
        pv = s.scalar(select(PatternVersion).join(Product).where(Product.slug == CHURN))
        pv.cir_json = {"slug": CHURN, "rev": n}


def _open(db, prefix):
    with db.session() as s:
        return sorted(i.signature for i in s.scalars(select(Incident).where(
            Incident.resolved == False, Incident.signature.like(prefix + "%"))))  # noqa: E712


# --- the production state, end to end -----------------------------------------------------------

def test_production_state_converges_and_the_systemic_halt_closes():
    """12 products stale after a chain move, their first stage jobs killed by a deploy, and a
    catalogue where some other product's design moves every hour. On the base code no product
    ever rebuilds (every later attempt deduplicates onto the dead stage) and the halt stays
    open; here each product's daily retry runs a stage of its own, verifies, and the halt
    resolves on its own evidence."""
    db = base._sqlite_db()
    _estate(db, SLUGS + [CHURN])
    restore = base._no_policy()
    try:
        with base._MovedChain():
            base._sentinel(db, "t0")
            _run(db)                                   # first attempts: stage jobs + verify 1
            with db.session() as s:
                doomed = {j.id for j in s.scalars(select(Job).where(
                    Job.job_type == "assets.build")) if j.inputs["slug"] in SLUGS}
                halt = L.escalate_systemic(s)          # what ops.truth runs
            assert len(doomed) == len(SLUGS)
            for hour in range(1, 40):
                _move_churn(db, hour)                  # another product's design moves
                _stages(db, doomed)
                _age(db)
                base._sentinel(db, f"t{hour}")
                _run(db)
                if hour == 3:
                    # the first attempts' verify checks ran out: production's state
                    with db.session() as s:
                        halt = L.escalate_systemic(s)
                    assert halt["systemic"], halt
                    assert len([x for x in _open(db, "rebuild-incomplete:")
                                if x.split(":", 1)[1] in SLUGS]) == len(SLUGS)
            _stages(db, doomed)
            _age(db)
            out = base._sentinel(db, "final")
            with db.session() as s:
                verdicts = {(v.product_slug, v.state) for v in A.check(
                    s, current=A.current_from_db(s))}
                completed = {a.artifact.split(":", 1)[1].split("@")[0] for a in s.scalars(
                    select(AuditLog).where(AuditLog.action == "chain.rebuild_completed"))
                    if not (a.detail or {}).get("already_fresh")}
                stacked = [j.inputs["product_slug"] for j in s.scalars(select(Job).where(
                    Job.job_type == "chain.rebuild", Job.status == JobStatus.PENDING))
                    if j.inputs.get("product_slug") in SLUGS]
            stale = sorted(sl for sl, st in verdicts if st == A.STALE and sl in SLUGS)
            assert stale == [], f"never rebuilt: {stale}"
            assert set(SLUGS) <= completed, sorted(set(SLUGS) - completed)
            assert stacked == [], stacked                 # nothing re-queued hourly
            assert not [x for x in _open(db, "stale-artefact:") if x != "stale-artefact:backlog"
                        and any(sl in x for sl in SLUGS)], _open(db, "stale-artefact:")
            assert not [x for x in _open(db, "rebuild-incomplete:")
                        if x.split(":", 1)[1] in SLUGS], _open(db, "rebuild-incomplete:")
            assert not out.get("rebuild_retry_held"), out.get("rebuild_retry_held")
            with db.session() as s:
                ev = L.escalate_systemic(s)
            assert not ev["systemic"] and L.SYSTEMIC_SIGNATURE in ev["resolved"], ev
            with db.session() as s:
                row = s.scalar(select(Incident).where(
                    Incident.signature == L.SYSTEMIC_SIGNATURE))
                assert row.resolved and row.detail.get("resolution"), row.detail
    finally:
        restore()


# --- H1 -------------------------------------------------------------------------------------------

def test_h1_another_products_change_never_stacks_an_attempt_on_one_in_flight():
    db = base._sqlite_db()
    _estate(db, ["a", "b", CHURN], cls_keys=(("pdf", "{s}@1.0.0#pdf-us"),))
    restore = base._no_policy()
    try:
        with base._MovedChain():
            base._sentinel(db, "1")
            _run(db)
            _move_churn(db, 1)
            out = base._sentinel(db, "2")
            assert out["rebuild_already_queued"] == ["pdf:a@1.0.0#pdf-us",
                                                     "pdf:b@1.0.0#pdf-us"], out
            assert out["rebuild_enqueued"] == [f"pdf:{CHURN}@1.0.0#pdf-us"], out
            with db.session() as s:
                firsts = [j.inputs["product_slug"] for j in s.scalars(select(Job).where(
                    Job.job_type == "chain.rebuild")) if not j.inputs.get("verify")]
            assert sorted(firsts) == ["a", "b", CHURN, CHURN], firsts
            _run(db)
            _stages(db, set())
            for _ in range(4):
                _age(db, hours=0.5)
                _run(db)
            with db.session() as s:
                unbound = s.scalars(select(AuditLog).where(
                    AuditLog.action == "chain.rebuild_unbound")).all()
            assert unbound == [], [u.artifact for u in unbound]
            assert _open(db, "rebuild-incomplete:") == [], _open(db, "rebuild-incomplete:")
    finally:
        restore()


def test_h1_an_ended_attempt_waits_for_its_retry_and_honours_the_hold():
    """Under a shifted estate key the product is still on RETRY_AFTER and its hold."""
    db = base._sqlite_db()
    _estate(db, ["a", CHURN], cls_keys=(("pdf", "{s}@1.0.0#pdf-us"),))
    restore = base._no_policy()
    try:
        with base._MovedChain():
            base._sentinel(db, "1")
            base._finish_all_rebuilds(db)
            _move_churn(db, 1)
            out = base._sentinel(db, "2")
            assert "a" in out["rebuild_retry_waiting"], out
            assert not any(k.startswith("pdf:a@") for k in out["rebuild_enqueued"]), out
            base._finish_all_rebuilds(db, at=utcnow() - timedelta(hours=13))
            with db.session() as s:
                s.add(Incident(severity="P0", product_slug="a", halts_publication=True,
                               signature="authority_chain_tamper:a", summary="t"))
            _move_churn(db, 2)
            out = base._sentinel(db, "3")
            assert "authority_chain_tamper" in out["rebuild_retry_held"]["a"], out
            assert not any(k.startswith("pdf:a@") for k in out["rebuild_enqueued"]), out
    finally:
        restore()


# --- H2 -------------------------------------------------------------------------------------------

def test_h2_every_attempt_gets_a_stage_of_its_own():
    db = base._sqlite_db()
    _estate(db, ["a"], cls_keys=(("pdf", "{s}@1.0.0#pdf-us"),))
    with base._MovedChain():
        payload = {"product_slug": "a", "artefacts": ["pdf:a@1.0.0#pdf-us"], "reason": "t",
                   "fingerprints": {"chain:release": {"new": A.chain_fingerprint()}}}
        jobs = [base._run_job(db, "listing", "chain.rebuild", payload, f"attempt-{n}")
                for n in (1, 2)]
    stage_ids = [j.outputs["stage_job"] for j in jobs]
    assert all(stage_ids) and stage_ids[0] != stage_ids[1], [j.outputs for j in jobs]


# --- H3 -------------------------------------------------------------------------------------------

def _held_row(db, slug, *, fps, with_stage: int, without_stage: int, **extra):
    held = "3 rebuild attempts at this change left 1 artefact(s) stale (pdf)"
    with db.session() as s:
        s.add(Incident(severity="P1", product_slug=slug, halts_publication=True,
                       signature=f"rebuild-incomplete:{slug}", summary="held", report_count=3,
                       detail={"stale": [f"pdf:{slug}@1.0.0#pdf-us"], "fingerprints": fps,
                               "attempts": 3, "held": held, "refused_by": [], **extra}))
        # the product's first attempt at this change, ended a day ago (what production holds)
        new = {ref: v["new"] for ref, v in fps.items()}
        s.add(Job(agent="listing", job_type="chain.rebuild", status=JobStatus.DONE,
                  idempotency_key=f"rebuild:product:{slug}:first",
                  inputs={"product_slug": slug, "artefacts": [f"pdf:{slug}@1.0.0#pdf-us"],
                          "fingerprints": fps, "change_id": G.change_id(new, set(new))},
                  outputs={}, finished_at=utcnow() - timedelta(days=1)))
        for n in range(with_stage + without_stage):
            s.add(Job(agent="listing", job_type="chain.rebuild", status=JobStatus.DONE,
                      idempotency_key=f"rebuild-verify:{slug}:{100 + n}:3",
                      inputs={"product_slug": slug, "artefacts": [f"pdf:{slug}@1.0.0#pdf-us"],
                              "fingerprints": fps, "verify": release.REBUILD_VERIFY_ATTEMPTS,
                              "stage_job": (900 + n) if n < with_stage else None,
                              "requested_by": 100 + n},
                      outputs={"outstanding": [f"pdf:{slug}@1.0.0#pdf-us"]},
                      finished_at=utcnow() - timedelta(days=1)))


def test_h3_a_hold_counted_from_stageless_attempts_is_released_once():
    db = base._sqlite_db()
    _estate(db, ["a", "b", "c"], cls_keys=(("pdf", "{s}@1.0.0#pdf-us"),))
    restore = base._no_policy()
    try:
        with base._MovedChain():
            fps = {"chain:release": {"old": "0" * 16, "new": A.chain_fingerprint()}}
            _held_row(db, "a", fps=fps, with_stage=1, without_stage=2)     # production shape
            _held_row(db, "b", fps=fps, with_stage=3, without_stage=0)     # genuinely held
            _held_row(db, "c", fps=fps, with_stage=0, without_stage=3,     # DEAD/refused kind
                      failed_attempts=[{"why": "chain.rebuild went dead: KeyError"}] * 3)
            assert release_gates.retry_hold_reason(db, slug="a")
            out = base._sentinel(db, "1")
            assert out["rebuild_incomplete_holds_released"] == ["a"], out
            assert sorted(out["rebuild_retry_held"]) == ["b", "c"], out
            assert out["rebuild_enqueued"] == [], out      # the release's one rebuild only
            assert release_gates.retry_hold_reason(db, slug="a") is None
            assert release_gates.retry_hold_reason(db, slug="b")
            assert release_gates.retry_hold_reason(db, slug="c")
            with db.session() as s:
                row = s.scalar(select(Incident).where(
                    Incident.signature == "rebuild-incomplete:a"))
                assert not row.resolved and row.halts_publication, row.detail
                rec = row.detail[G.HOLD_RELEASE_KEY]
                assert rec["attempts_without_own_stage"] == 2, rec
                assert rec["attempts_with_own_stage"] == 1, rec
                restart = [j for j in s.scalars(select(Job).where(
                    Job.idempotency_key.like("rebuild:hold-released:a:%")))]
            assert len(restart) == 1 and restart[0].inputs["fingerprints"] == fps, restart
            assert restart[0].inputs["change_id"], restart[0].inputs
            out = base._sentinel(db, "2")                  # no second release of that hold
            assert "a" not in out["rebuild_incomplete_holds_released"], out
            # the released attempt runs a stage of its own
            _run(db)
            with db.session() as s:
                stage = s.scalars(select(Job).where(Job.job_type == "assets.build")).all()
            assert [j.inputs["slug"] for j in stage] == ["a"], [j.inputs for j in stage]
    finally:
        restore()


def test_h3_hold_text_says_when_the_attempt_ran_no_stage():
    db = base._sqlite_db()
    restore = base._no_policy()
    try:
        with db.session() as s:
            s.add(Product(slug="a", title="a"))
        fp = {"chain:release": {"old": "0" * 16, "new": "1" * 16}}
        for _ in range(G.REBUILD_MAX_ATTEMPTS):
            detail = release._rebuild_incomplete(base._Ctx(db), "a", "1.0.0",
                                                 stale=["pdf:a@1.0.0#pdf-us"], reason="t",
                                                 fingerprints=fp, checks=3)
        assert "ran no stage job of its own" in detail["held"], detail
        assert "the stage ran" not in detail["held"], detail
    finally:
        restore()


if __name__ == "__main__":
    import traceback

    fails = 0
    for name in [n for n in list(globals()) if n.startswith("test_")]:
        try:
            globals()[name]()
            print(f"OK   {name}")
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            fails += 1
            print(f"FAIL {name}", repr(e))
    print(f"{fails} failure(s)")
    sys.exit(1 if fails else 0)
