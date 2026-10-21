"""W4-LISTREADY: production's certification deadlock, reproduced and cleared at its roots.

Production b931d17 (read 2026-10-20): 299 stale artefacts, a stale-artefact P1 on 14 products,
the company-wide P0 `systemic-halt:publication` built only from them, and `gate.halted` for
every new release since 2026-10-11. Three root causes are fixed here, none by changing what
halts certification or publication:

* R1 -- the sentinel judged every artefact against the newest release of its slug, while
  `design_inputs` records it from its own release, so every artefact of an older release was
  stale forever. It is now judged against its own release and an older release's artefact is
  `superseded` (not stale, not fresh, no halt); publication refuses a superseded release.
* R3 -- a halted certification consumed its idempotency keys and could never run again. It is
  retried once per halt episode, only after the halt clears.
* R5 -- Launch-0 releases the chain never drafted are drafted through the normal gates.

Gate E is untouched: a customer-defect P1 still halts certification, genuinely stale artefacts
of the current release still raise halting P1s, and the P0 trips at the same threshold.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

_TMP = tempfile.mkdtemp(prefix="w4_listready_")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    AuditLog, Incident, Job, PatternVersion, Phase, Product,
)
from brambleloop.gates.incidents import DefectReport, IncidentTracker  # noqa: E402
from brambleloop.ops import artefacts as P  # noqa: E402
from brambleloop.ops import incident_lifecycle as IL  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401 - registers handlers
from brambleloop.runtime import release_recovery as RR  # noqa: E402
from brambleloop.runtime.worker import JobContext  # noqa: E402

_N = [0]


def _db():
    _N[0] += 1
    db = Database(f"sqlite:///{_TMP}/lr{_N[0]}.db")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _pv(db, slug, version, design, release):
    with db.session() as s:
        product = s.scalar(select(Product).where(Product.slug == slug))
        if product is None:
            product = Product(slug=slug, title=slug, status="certified")
            s.add(product)
            s.flush()
        s.add(PatternVersion(product_id=product.id, version=version, cir_json=design,
                             release_hash=release, certified=True))


def _record_from(db, slug, version, cls="pdf", key=None, inputs=None):
    """Recorded exactly as the chain records it: from that release's own fingerprints."""
    with db.session() as s:
        ins = inputs if inputs is not None else P.design_inputs(s, slug, version, chain=False)
        P.record(s, artefact_class=cls, artefact_key=key or P.pdf_key(slug, version, "US"),
                 product_slug=slug, inputs=ins)


def _sentinel(db, *, old_logic=False):
    with db.session() as s:
        current = P.current_from_db(s)
        if old_logic:                      # b931d17: newest-release fingerprints only
            current = dict(current)
        return P.sweep(s, current=current)


def _ctx(db, job):
    return JobContext(job=job, db=db, queue=JobQueue(db), registry=Registry(db),
                      phase=Phase.SHADOW)


# ---- R1: per-release freshness ----------------------------------------------------------

def test_an_older_release_artefact_is_superseded_not_stale_and_raises_no_halt():
    db = _db()
    _pv(db, "hex", "1.0.0", {"rows": 12}, "a" * 64)
    _record_from(db, "hex", "1.0.0")
    _record_from(db, "hex", "1.0.0", cls="certificate", key="hex@1.0.0")
    _pv(db, "hex", "1.1.0", {"rows": 14}, "b" * 64)          # the product moves on

    old = _sentinel(db, old_logic=True)
    assert old["stale"] == 2 and old["publication_blocked"] == ["hex"]   # the defect

    out = _sentinel(db)
    states = {v["artefact_key"]: v["state"] for v in out["verdicts"]}
    assert states == {"hex@1.0.0#pdf-us": P.SUPERSEDED, "hex@1.0.0": P.SUPERSEDED}
    assert out["stale"] == 0 and out["publication_blocked"] == []
    assert sorted(out["incidents_cleared"]) == ["stale-artefact:certificate:hex@1.0.0",
                                                "stale-artefact:pdf:hex@1.0.0#pdf-us"]
    with db.session() as s:
        rows = list(s.scalars(select(Incident).where(Incident.resolved.is_(False),
                                                     Incident.halts_publication.is_(True))))
        assert rows == []
        res = s.scalar(select(Incident).where(
            Incident.signature == "stale-artefact:pdf:hex@1.0.0#pdf-us"))
        assert "superseded, not stale" in res.detail["resolution"]
        assert res.detail["resolved_at"]
    assert IncidentTracker(db).publication_halted("hex") is False
    # never called fresh
    assert out["fresh"] == 0


def test_live_marketing_copy_written_from_an_older_release_is_stale_not_superseded():
    """Review F1 (BLOCKER): the review's reproduction. Marketing copy is the product's live
    copy; written from 1.0.0 and left after 1.1.0 it is STALE and halting, never superseded,
    and the rebuild that cures it may run (R4) while publication still refuses."""
    from brambleloop.ops import rebuild_graph
    from brambleloop.publish import release_gates as G

    db = _db()
    _pv(db, "hex", "1.0.0", {"rows": 12, "yards": 100}, "a" * 64)
    key = P.marketing_key("hex", "pin", "Hex: 100 yards")
    _record_from(db, "hex", "1.0.0", cls="marketing_asset", key=key)
    _pv(db, "hex", "1.1.0", {"rows": 14, "yards": 140}, "b" * 64)
    out = _sentinel(db)
    assert [v["state"] for v in out["verdicts"]] == [P.STALE], out["verdicts"]
    assert out["publication_blocked"] == ["hex"]
    assert IncidentTracker(db).publication_halted("hex") is True
    with db.session() as s:
        gate = rebuild_graph.publication_gate(s, slug="hex")
    assert gate["may_publish"] is False and gate["outstanding"] == [f"marketing_asset:{key}"]
    st = G.staleness(db, slug="hex")
    assert st["blocks"] is True and st["outstanding_only_marketing"] is True
    # the rebuild re-records the copy from the newest release: fresh, and the halt clears
    _record_from(db, "hex", "1.1.0", cls="marketing_asset", key=key)
    out = _sentinel(db)
    assert [v["state"] for v in out["verdicts"]] == [P.FRESH]
    assert out["incidents_cleared"] == [f"stale-artefact:marketing_asset:{key}"]
    assert IncidentTracker(db).publication_halted("hex") is False


def test_no_unversioned_artefact_is_ever_superseded():
    db = _db()
    _pv(db, "hex", "1.0.0", {"rows": 12}, "a" * 64)
    for cls, key in (("marketing_asset", P.marketing_key("hex", "email", "x")),
                     ("pdf", "hex.pdf"), ("certificate", "hex@unknown-version")):
        _record_from(db, "hex", "1.0.0", cls=cls, key=key)
    _pv(db, "hex", "1.1.0", {"rows": 14}, "b" * 64)
    out = _sentinel(db)
    assert {v["state"] for v in out["verdicts"]} == {P.STALE}, out["verdicts"]


def test_newest_is_the_highest_certified_version_not_the_last_row():
    """Review F2: an out-of-order certification (an older release certified after a newer
    one) must not make the real newest release superseded or let the older one publish."""
    from brambleloop.publish import release_gates as G

    db = _db()
    _pv(db, "hex", "1.1.0", {"rows": 14}, "b" * 64)
    _record_from(db, "hex", "1.1.0")
    _pv(db, "hex", "1.0.0", {"rows": 12}, "a" * 64)              # inserted last
    _record_from(db, "hex", "1.0.0")
    with db.session() as s:
        cur = P.current_from_db(s)
    assert cur.latest_version["hex"] == "1.1.0"
    states = {v["artefact_key"]: v["state"] for v in _sentinel(db)["verdicts"]}
    assert states == {"hex@1.1.0#pdf-us": P.FRESH, "hex@1.0.0#pdf-us": P.SUPERSEDED}
    assert G.superseded_release(db, slug="hex", version="1.1.0")["superseded"] is False
    old = G.superseded_release(db, slug="hex", version="1.0.0")
    assert old["superseded"] is True and old["newest"] == "1.1.0"
    # 1.10.0 is newer than 1.9.0 (not a string comparison)
    assert P.newest_version(["1.9.0", "1.10.0"]) == "1.10.0"


def test_versions_that_cannot_be_ordered_supersede_nothing_and_refuse_publication():
    from brambleloop.publish import release_gates as G

    db = _db()
    _pv(db, "hex", "1.0.0", {"rows": 12}, "a" * 64)
    _record_from(db, "hex", "1.0.0")
    _pv(db, "hex", "draft-b", {"rows": 14}, "b" * 64)
    assert P.newest_version(["1.0.0", "draft-b"]) is None
    assert P.SUPERSEDED not in {v["state"] for v in _sentinel(db)["verdicts"]}
    for v in ("1.0.0", "draft-b"):
        assert G.superseded_release(db, slug="hex", version=v)["superseded"] is True


def test_genuinely_stale_artefacts_of_the_current_release_still_raise_halting_p1s():
    db = _db()
    _pv(db, "hex", "1.0.0", {"rows": 12}, "a" * 64)
    _pv(db, "hex", "1.1.0", {"rows": 14}, "b" * 64)
    _record_from(db, "hex", "1.1.0")                               # fresh
    # built from a design the current release does not hold
    _record_from(db, "hex", "1.1.0", cls="certificate", key="hex@1.1.0",
                 inputs={"cir:hex": P.fingerprint({"rows": 13}), "release:hex": "b" * 16})
    out = _sentinel(db)
    states = {v["artefact_key"]: v["state"] for v in out["verdicts"]}
    assert states == {"hex@1.1.0#pdf-us": P.FRESH, "hex@1.1.0": P.STALE}
    assert out["publication_blocked"] == ["hex"]
    with db.session() as s:
        inc = s.scalar(select(Incident).where(
            Incident.signature == "stale-artefact:certificate:hex@1.1.0"))
        assert inc.severity == "P1" and inc.halts_publication is True
    assert IncidentTracker(db).publication_halted("hex") is True


def test_a_recertified_current_release_turns_its_own_artefacts_stale():
    db = _db()
    _pv(db, "hex", "1.0.0", {"rows": 12}, "a" * 64)
    _record_from(db, "hex", "1.0.0")
    with db.session() as s:
        s.scalar(select(PatternVersion)).release_hash = "c" * 64   # re-certified document
    out = _sentinel(db)
    assert out["stale"] == 1 and out["verdicts"][0]["moved"] == ["release:hex"]
    assert out["publication_blocked"] == ["hex"]


def _systemic(db):
    with db.session() as s:
        return IL.escalate_systemic(s)


def test_the_p0_trips_at_the_same_threshold_for_genuine_staleness_and_not_for_superseded():
    # Four products; the rule is >= 3 products and >= 50% of the catalogue.
    db = _db()
    for slug in ("a", "b", "c", "d"):
        _pv(db, slug, "1.0.0", {"s": slug}, "1" * 64)
        _record_from(db, slug, "1.0.0")
        _pv(db, slug, "1.1.0", {"s": slug, "v": 2}, "2" * 64)
    _sentinel(db, old_logic=True)
    assert _systemic(db)["systemic"] is True                     # production's P0
    _sentinel(db)
    ev = _systemic(db)
    assert ev["systemic"] is False and ev["resolved"]           # superseded is not staleness

    db = _db()
    for slug in ("a", "b", "c", "d"):
        _pv(db, slug, "1.0.0", {"s": slug}, "1" * 64)
    for slug in ("a", "b"):                                      # 2 products: below threshold
        _record_from(db, slug, "1.0.0", inputs={f"cir:{slug}": P.fingerprint({"x": 1})})
    _sentinel(db)
    assert _systemic(db)["systemic"] is False
    _record_from(db, "c", "1.0.0", inputs={"cir:c": P.fingerprint({"x": 1})})   # 3 of 4
    _sentinel(db)
    ev = _systemic(db)
    assert ev["systemic"] is True and ev["widespread_families"] == {
        "stale-artefact": ["a", "b", "c"]}


def test_publication_refuses_a_superseded_release():
    from brambleloop.publish import release_gates as G

    db = _db()
    cir = _launch0_cir().to_dict()
    hex_ = cir["slug"]
    _pv(db, hex_, "1.0.0", dict(cir, version="1.0.0"), "a" * 64)
    assert G.superseded_release(db, slug=hex_, version="1.0.0")["superseded"] is False
    _pv(db, hex_, "1.1.0", dict(cir, version="1.1.0"), "b" * 64)
    old = G.superseded_release(db, slug=hex_, version="1.0.0")
    assert old["superseded"] is True and old["newest"] == "1.1.0"
    assert G.superseded_release(db, slug=hex_, version="1.1.0")["superseded"] is False
    verdict = G.for_publish(db, slug=hex_, version="1.0.0", read_only=True)
    assert verdict["blocks_release"] is True
    assert any(r.startswith("superseded release (R1)") for r in verdict["reasons"])
    newest = G.for_publish(db, slug=hex_, version="1.1.0", read_only=True)
    assert not any(r.startswith("superseded release") for r in newest["reasons"])


# ---- R4: genuinely stale marketing is rebuildable; publication still refuses ----------------

def test_genuinely_stale_marketing_may_be_rebuilt_while_publication_still_refuses():
    from brambleloop.publish import release_gates as G

    db = _db()
    _pv(db, "hex", "1.0.0", {"rows": 12}, "a" * 64)
    key = P.marketing_key("hex", "pin", "t")
    # built from a design no certified release holds: genuinely stale against the newest
    _record_from(db, "hex", "1.0.0", cls="marketing_asset", key=key,
                 inputs={"cir:hex": P.fingerprint({"rows": 11})})
    out = _sentinel(db)
    assert out["stale"] == 1 and out["publication_blocked"] == ["hex"]

    st = G.staleness(db, slug="hex")
    assert st["halted"] is True and st["blocks"] is True          # publication refuses
    assert st["rebuild"]["outstanding"] == [f"marketing_asset:{key}"]
    assert st["outstanding_only_marketing"] is True                # the rebuild may run

    # any other halt still refuses the marketing rebuild too (Gate E unchanged)
    tracker = IncidentTracker(db)
    for i in range(3):
        tracker.report(DefectReport("hex", "1.0.0", "coaster", 4, f"c{i}", "row 4"))
    st = G.staleness(db, slug="hex")
    assert st["halted"] is True and st["outstanding_only_marketing"] is False


# ---- R3: a halted certification is retried once per halt episode --------------------------

def _launch0_cir(slug="hexagon-coaster-set"):
    from brambleloop.products import launch0 as l0

    for c in RR.launch0_releases():
        if c.slug == slug:
            return c
    raise KeyError(slug)


def _certify(db, job):
    """Run one gate.certify job as the worker does: the handler, then the job marked done."""
    from brambleloop.core.models import JobStatus

    out = pipeline.handle_certify(_ctx(db, job))
    with db.session() as s:
        s.get(Job, job.id).status = JobStatus.DONE
    return out


def _certify_job(db, cir, key):
    return JobQueue(db).enqueue("quality_director", "gate.certify", {"cir": cir.to_dict()},
                                idempotency_key=key)


def _actions(db, artifact):
    with db.session() as s:
        return [a.action for a in s.scalars(select(AuditLog).where(
            AuditLog.artifact == artifact).order_by(AuditLog.id))]


def test_a_halted_certification_is_never_retried_while_the_halt_holds_and_once_after():
    db = _db()
    cir = _launch0_cir()
    rel = f"{cir.slug}@{cir.version}"
    tracker = IncidentTracker(db)
    for i in range(3):                       # Gate E: a customer-defect P1, unchanged
        tracker.report(DefectReport(cir.slug, "1.0.0", "coaster", 4, f"c{i}", "row 4"))
    job = _certify_job(db, cir, "certify-first")
    out = _certify(db, (job))
    assert out.get("halted_by_incident") is True
    assert _actions(db, rel) == ["gate.halted"]

    holder = _ctx(db, JobQueue(db).enqueue("listing", "chain.rebuild", {}, idempotency_key="x"))
    r = RR.retry_halted(holder)
    assert r["retried"] == [] and r["still_halted"] == [rel]       # never while halted

    with db.session() as s:
        for inc in s.scalars(select(Incident).where(Incident.resolved.is_(False))):
            tracker.resolve(inc.id, "fixed in the next release")
    r = RR.retry_halted(holder)
    assert r["retried"] == [rel]
    again = RR.retry_halted(holder)
    assert again["retried"] == [] and again["already_retried"] == [rel]   # once per episode

    with db.session() as s:
        retry = s.scalar(select(Job).where(Job.idempotency_key.like("certify-after-halt:%")))
        first = s.scalar(select(Job).where(Job.idempotency_key == "certify-first"))
        assert retry.inputs == first.inputs                   # the halted CIR, nothing guessed
    out = _certify(db, (retry))
    assert out["granted"] is True
    assert _actions(db, rel)[:2] == ["gate.halted", "gate.certified"]
    assert RR.halted_releases(db) == []                  # decided: the episode is over
    assert RR.retry_halted(holder)["retried"] == []
    with db.session() as s:
        pvs = list(s.scalars(select(PatternVersion).join(Product).where(
            Product.slug == cir.slug, PatternVersion.version == cir.version)))
    assert len(pvs) == 1                                     # no duplicate certification


def test_a_retry_that_is_halted_again_opens_a_new_episode():
    db = _db()
    cir = _launch0_cir()
    tracker = IncidentTracker(db)
    for i in range(3):
        tracker.report(DefectReport(cir.slug, "1.0.0", "coaster", 4, f"c{i}", "row 4"))
    _certify(db, (_certify_job(db, cir, "first")))
    first = RR.halted_releases(db)[0]["halt_audit_id"]
    with db.session() as s:
        ids = [i.id for i in s.scalars(select(Incident).where(Incident.resolved.is_(False)))]
    for i in ids:
        tracker.resolve(i, "x")
    holder = _ctx(db, JobQueue(db).enqueue("listing", "chain.rebuild", {}, idempotency_key="y"))
    RR.retry_halted(holder)
    for i in range(3):                                        # halted again before it ran
        tracker.report(DefectReport(cir.slug, "1.0.0", "coaster", 5, f"d{i}", "row 5"))
    with db.session() as s:
        retry = s.scalar(select(Job).where(Job.idempotency_key.like("certify-after-halt:%")))
    assert _certify(db, (retry)).get("halted_by_incident") is True
    second = RR.halted_releases(db)[0]["halt_audit_id"]
    assert second > first
    assert RR.retry_halted(holder)["still_halted"]


# ---- R5: Launch-0 releases the chain never drafted ------------------------------------------

def test_every_uncertified_launch0_release_is_drafted_once_through_the_normal_job():
    db = _db()
    cir = _launch0_cir("cloudline-baby-blanket")
    _pv(db, cir.slug, cir.version, cir.to_dict(), "f" * 64)       # already certified
    holder = _ctx(db, JobQueue(db).enqueue("listing", "chain.rebuild", {}, idempotency_key="z"))
    seeded = []
    for run in range(9):                       # one release per whole-catalogue run
        out = RR.seed_launch0(holder)
        assert out["certified"] == [f"{cir.slug}@{cir.version}"]
        assert len(out["seeded"]) == 1 and out["seeded"][0] not in seeded
        assert len(out["already_seeded"]) == run and len(out["pending"]) == 8 - run
        seeded += out["seeded"]
    for rel in ("market-basket-small@1.2.0", "market-basket-medium@1.2.0",
                "market-basket-large@1.2.0", "hexagon-coaster-set@1.2.0",
                "nordic-forest-mosaic-throw-baby@1.3.0", "housewarming-key-basket@0.1.0"):
        assert rel in seeded, rel
    assert seeded[0] == "market-basket-small@1.2.0"           # listing order
    again = RR.seed_launch0(holder)
    assert again["seeded"] == [] and len(again["already_seeded"]) == 9
    assert again["pending"] == []
    with db.session() as s:
        drafts = list(s.scalars(select(Job).where(Job.job_type == "cir.draft")))
    assert len(drafts) == 9 and all(j.agent == "crochet_engineer" for j in drafts)
    # the seeded job is the ordinary draft: it drafts the engineered design and hands it to
    # the compiler, whose gates are unchanged
    basket = next(j for j in drafts if j.inputs["slug"] == "market-basket-small")
    got = pipeline.handle_cir_draft(_ctx(db, basket))
    assert got["drafted"] is True and got["artifact"] == "market-basket-small@1.2.0"
    with db.session() as s:
        assert s.scalar(select(Job).where(Job.job_type == "cir.compile")) is not None


# ---- the production situation, end to end ---------------------------------------------------

def test_production_deadlock_reproduced_then_cleared_with_every_gate_unchanged():
    """Older-release artefacts, the newest release certified past them, a newer release's draft
    halted by the P0 built from them; after the fix the halt clears and it certifies."""
    from brambleloop.runtime.release import handle_chain_rebuild

    db = _db()
    cir = _launch0_cir()                                  # hexagon-coaster-set@1.2.0
    for slug in (cir.slug, "p2", "p3"):
        _pv(db, slug, "1.0.0", {"s": slug}, "1" * 64)
        _record_from(db, slug, "1.0.0")
        _record_from(db, slug, "1.0.0", cls="certificate", key=f"{slug}@1.0.0")
        _pv(db, slug, "1.1.0", {"s": slug, "v": 2}, "2" * 64)
    # b931d17's sentinel and escalation
    _sentinel(db, old_logic=True)
    assert _systemic(db)["systemic"] is True
    halted = _certify(db, (_certify_job(db, cir, f"certify:{cir.slug}")))
    assert halted.get("halted_by_incident") is True

    # the fixed sentinel: the halt clears for the reason it was wrong, nothing else
    _sentinel(db)
    ev = _systemic(db)
    assert ev["systemic"] is False and ev["resolved"]
    assert IncidentTracker(db).publication_halted(cir.slug) is False

    rebuild = JobQueue(db).enqueue("listing", "chain.rebuild", {}, idempotency_key="hourly")
    out = handle_chain_rebuild(_ctx(db, rebuild))
    rel = f"{cir.slug}@{cir.version}"
    assert out["recovery"]["halted_certifications"]["retried"] == [rel]
    with db.session() as s:
        retry = s.scalar(select(Job).where(Job.idempotency_key.like("certify-after-halt:%")))
    granted = _certify(db, (retry))
    assert granted["granted"] is True
    assert "gate.certified" in _actions(db, rel)

    # the newest release now is 1.2.0: 1.1.0 is superseded and may not publish
    from brambleloop.publish import release_gates as G
    assert G.superseded_release(db, slug=cir.slug, version="1.1.0")["superseded"] is True
    assert G.superseded_release(db, slug=cir.slug, version=cir.version)["superseded"] is False
    out = handle_chain_rebuild(_ctx(db, JobQueue(db).enqueue(
        "listing", "chain.rebuild", {}, idempotency_key="hourly-2")))
    assert out["recovery"]["halted_certifications"]["retried"] == []


# ---- review of d45e033: F3, F4, F5, F6, F8 ---------------------------------------------------

def _halted(db, cir, key="first"):
    tracker = IncidentTracker(db)
    for i in range(3):
        tracker.report(DefectReport(cir.slug, "1.0.0", "coaster", 4, f"{key}{i}", "row 4"))
    assert _certify(db, _certify_job(db, cir, key)).get("halted_by_incident") is True
    with db.session() as s:
        for inc in s.scalars(select(Incident).where(Incident.resolved.is_(False))):
            tracker.resolve(inc.id, "fixed")


def _holder(db, key):
    return _ctx(db, JobQueue(db).enqueue("listing", "chain.rebuild", {}, idempotency_key=key))


def test_f3_a_halted_release_whose_design_moved_is_not_retried():
    db = _db()
    cir = _launch0_cir()
    moved = cir.to_dict()
    moved["title"] = moved["title"] + " (older draft)"            # the recorded CIR is stale
    from brambleloop.cir.model import CIR
    _halted_cir = CIR.from_dict(moved)
    tracker = IncidentTracker(db)
    for i in range(3):
        tracker.report(DefectReport(cir.slug, "1.0.0", "coaster", 4, f"m{i}", "row 4"))
    assert _certify(db, _certify_job(db, _halted_cir, "moved")).get("halted_by_incident")
    with db.session() as s:
        for inc in s.scalars(select(Incident).where(Incident.resolved.is_(False))):
            tracker.resolve(inc.id, "fixed")
    r = RR.retry_halted(_holder(db, "f3"))
    rel = f"{cir.slug}@{cir.version}"
    assert r["retried"] == [] and r["skipped"][rel].startswith("design_moved"), r
    with db.session() as s:
        assert s.scalar(select(AuditLog).where(AuditLog.action == "certify.retry_skipped"))


def test_f2_f3_a_halted_release_with_a_newer_certified_release_is_not_retried():
    db = _db()
    cir = _launch0_cir()                                          # hexagon-coaster-set@1.2.0
    _halted(db, cir)
    _pv(db, cir.slug, "1.3.0", dict(cir.to_dict(), version="1.3.0"), "e" * 64)
    r = RR.retry_halted(_holder(db, "f2"))
    rel = f"{cir.slug}@{cir.version}"
    assert r["retried"] == [] and r["skipped"][rel] == "superseded_by_newer: ['1.3.0'] certified"
    # and R5 does not seed a Launch-0 release older than a certified one
    out = RR.seed_launch0(_holder(db, "f2-seed"), limit=20)
    assert rel not in out["seeded"] and any(x.startswith(rel) for x in out["certified"])


def test_f5_no_retry_while_a_certify_for_the_same_release_is_in_flight():
    db = _db()
    cir = _launch0_cir()
    _halted(db, cir)
    JobQueue(db).enqueue("quality_director", "gate.certify", {"cir": cir.to_dict()},
                         idempotency_key="certify:normal-chain")      # pending, normal path
    r = RR.retry_halted(_holder(db, "f5"))
    rel = f"{cir.slug}@{cir.version}"
    assert r["retried"] == [] and r["skipped"][rel].startswith("certify_in_flight"), r


def test_f5_a_retry_and_a_normal_certify_certify_the_release_once():
    db = _db()
    cir = _launch0_cir()
    _halted(db, cir)
    RR.retry_halted(_holder(db, "f5b"))
    normal = JobQueue(db).enqueue("quality_director", "gate.certify", {"cir": cir.to_dict()},
                                  idempotency_key="certify:normal-chain-2")
    with db.session() as s:
        retry = s.scalar(select(Job).where(Job.idempotency_key.like("certify-after-halt:%")))
    assert _certify(db, retry)["granted"] is True
    second = _certify(db, normal)
    assert second.get("duplicate") is True
    rel = f"{cir.slug}@{cir.version}"
    acts = _actions(db, rel)
    assert acts.count("gate.certified") == 1 and "gate.recertified" not in acts
    assert "gate.certify_duplicate" in acts
    with db.session() as s:
        assert len(list(s.scalars(select(PatternVersion).join(Product).where(
            Product.slug == cir.slug, PatternVersion.version == cir.version)))) == 1


def test_f4_the_marketing_rebuild_exception_never_waives_an_unreviewed_policy_change():
    from brambleloop.core.models import PolicySnapshot
    from brambleloop.publish import release_gates as G

    db = _db()
    _pv(db, "hex", "1.0.0", {"rows": 12}, "a" * 64)
    key = P.marketing_key("hex", "pin", "t")
    _record_from(db, "hex", "1.0.0", cls="marketing_asset", key=key,
                 inputs={"cir:hex": P.fingerprint({"rows": 11})})
    _sentinel(db)
    assert G.staleness(db, slug="hex")["outstanding_only_marketing"] is True
    with db.session() as s:
        s.add(PolicySnapshot(source="seller_policy", material_change=True,
                             affects=["publishing"], digest="d" * 64, checked_on="2026-10-21"))
    st = G.staleness(db, slug="hex")
    assert st["policy_changes_unreviewed"] == ["seller_policy"]
    assert st["outstanding_only_marketing"] is False and st["blocks"] is True


def test_f6_chain_rebuild_redrafts_a_changed_design_and_not_an_unchanged_one():
    import json

    from brambleloop.gates.certificate import DOC_VERSION
    from brambleloop.runtime.pipeline import _engineered_cir
    from brambleloop.runtime.release import handle_chain_rebuild

    def run(stored: dict, key: str):
        db = _db()
        cir = _engineered_cir("hexagon-coaster-set")
        with db.session() as s:
            s.add(Product(slug=cir.slug, title=cir.title, status="certified"))
            s.flush()
            s.add(PatternVersion(product_id=s.scalar(select(Product.id)), version=cir.version,
                                 cir_json=stored, release_hash="r" * 64, certified=True,
                                 certificate={"doc_version": DOC_VERSION}))
        job = JobQueue(db).enqueue("listing", "chain.rebuild", {"slugs": [cir.slug]},
                                   idempotency_key=key)
        return handle_chain_rebuild(_ctx(db, job))["redrafted"]

    cir = _engineered_cir("hexagon-coaster-set")
    as_stored = json.loads(json.dumps(cir.to_dict(), default=str))   # what the DB holds
    assert run(as_stored, "same") == []                               # unchanged: no redraft
    changed = json.loads(json.dumps(cir.to_dict(), default=str))
    changed["components"][0]["rows"] = changed["components"][0]["rows"][:-1]   # one row less
    assert run(changed, "moved") == [f"{cir.slug}@{cir.version} design"]


def _etsy_mutating_methods():
    """EtsyClient methods that send POST/PUT/PATCH/DELETE (read from the client's own AST)."""
    import ast

    path = ROOT / "src" / "brambleloop" / "integrations" / "etsy.py"
    tree = ast.parse(path.read_text())
    out = {}
    for cls in [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "EtsyClient"]:
        methods = {f.name: f for f in cls.body if isinstance(f, ast.FunctionDef)}
        for name, fn in methods.items():
            for node in ast.walk(fn):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                        and node.func.attr == "_call" and node.args
                        and isinstance(node.args[0], ast.Constant)
                        and node.args[0].value in ("POST", "PUT", "PATCH", "DELETE")):
                    out[name] = ast.get_source_segment(path.read_text(), fn)
        return out, {n: ast.get_source_segment(path.read_text(), f) for n, f in methods.items()}
    raise AssertionError("EtsyClient not found")


def test_f8_every_etsy_write_is_authorised_at_the_client_boundary():
    """Owner directive / review F8 (1 of 2): every EtsyClient method that writes to Etsy
    checks authority at the effect boundary itself -- a verified owner grant, or the
    draft-only shadow lane in a non-publishing phase (`_authorise_write`) -- and activation
    (the only state change to live, and the fee) also needs the phase, the grant and a
    per-call launch authorisation. A private writer is reached only through a public one
    that checks."""
    mutating, methods = _etsy_mutating_methods()
    assert set(mutating) >= {"create_draft", "update_listing", "delete_listing", "activate",
                             "set_listing_property", "_upload_image", "_attach_file"}, mutating
    for name, body in mutating.items():
        if name.startswith("_"):
            callers = [n for n, b in methods.items() if n != name and f"self.{name}(" in b]
            assert callers, name
            for c in callers:
                assert "_authorise_write(" in methods[c] or c == "publish", (name, c)
        elif name == "activate":
            assert "launch_authorisation" in body and "_grant_refusal" in body or \
                "_authorise_write(" in body, body[:200]
        else:
            assert "_authorise_write(" in body, name
    # publish (the composite) verifies the owner grant itself before any write
    assert "_grant_refusal(" in methods["publish"] or "_authorise_write(" in methods["publish"]
    # price and state never travel through update_listing
    assert "PRICE_IS_ELSEWHERE" in methods["update_listing"]
    assert '"state" in fields' in methods["update_listing"]


def test_f8_every_etsy_write_call_site_is_classified_and_release_writes_pass_for_publish():
    """Owner directive / review F8 (2 of 2): every call site of an Etsy write method, by any
    receiver, is enumerated. A release reaches Etsy only through `store.publish` (create,
    images, files, properties) and `store.activate` (state -> active), both of which run
    `_release_gates` -> `release_gates.for_publish` (Product Truth, the current-version guard,
    the listing set, search, standards, policy (#39), staleness) before the write; the client
    then needs the owner's sealed grant. There is no renewal, inventory or price write path:
    `update_listing` refuses price and state. Any new write site fails this test until it is
    classified here."""
    import ast

    mutating, _ = _etsy_mutating_methods()
    public = {m.lstrip("_") for m in mutating} | {"upload_image", "attach_file", "publish"}
    src_root = ROOT / "src" / "brambleloop"
    allowed = {
        ("runtime/pipeline.py", "_publish_and_read_back"):
            "store.publish, after _release_gates (for_publish); owner grant at the client",
        ("runtime/pipeline.py", "handle_store_activate"):
            "store.activate, after _release_gates (for_publish); launch authorisation",
        ("integrations/etsy.py", "publish"): "the client's composite; grant verified first",
        ("integrations/etsy_exercise.py", "create_draft"):
            "write-path exercise draft: shadow lane only, never a release, deleted",
        ("integrations/etsy_probe.py", "*"):
            "write-path probe's exercise listing: shadow lane only, activation asserted refused",
        ("commerce/listing_rollback.py", "execute"):
            "owner-grant rollback of an existing listing's fields; no caller in src",
    }
    found = set()
    for path in src_root.rglob("*.py"):
        rel = str(path.relative_to(src_root))
        text = path.read_text()
        tree = ast.parse(text)
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for node in ast.walk(fn):
                if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                        and node.func.attr in public):
                    continue
                recv = ast.get_source_segment(text, node.func.value) or ""
                if node.func.attr == "publish" and "bus" in recv:
                    continue                       # the learning bus, not Etsy
                if node.func.attr == "activate" and "launch_review" in recv:
                    continue                       # the owner's review batch, not Etsy
                if rel == "integrations/etsy.py" and fn.name in mutating:
                    continue                       # the client's own internals
                found.add((rel, fn.name))
    unknown = sorted(f for f in found if f not in allowed and (f[0], "*") not in allowed)
    assert not unknown, f"unclassified Etsy write call sites: {unknown}"
    assert ("runtime/pipeline.py", "_publish_and_read_back") in found
    assert ("runtime/pipeline.py", "handle_store_activate") in found
    pipe = (src_root / "runtime" / "pipeline.py").read_text()
    tree = ast.parse(pipe)
    fns = {n.name: ast.get_source_segment(pipe, n) for n in ast.walk(tree)
           if isinstance(n, ast.FunctionDef)}
    assert "for_publish(" in fns["_release_gates"]
    for handler in ("handle_store_publish", "handle_store_activate"):
        assert "_release_gates(" in fns[handler], handler
    # _publish_and_read_back is reached only from store.publish's guarded path
    callers = [n for n, b in fns.items() if n != "_publish_and_read_back"
               and "_publish_and_read_back(" in b]
    assert callers == ["_publish_guarded"], callers
    assert [n for n, b in fns.items() if n != "_publish_guarded"
            and "_publish_guarded(" in b] == ["handle_store_publish"]
    rel_gates = (src_root / "publish" / "release_gates.py").read_text()
    fp = rel_gates[rel_gates.index("def for_publish("):rel_gates.index("def our_competitive_reading")]
    for gate in ("superseded_release(", "staleness(", "listing_set(", "search_gate(",
                 "standards_gate(", "eligibility.product_publication(", "originality_gate("):
        assert gate in fp, gate


# ---- product independence (owner directive) ------------------------------------------------

def test_a_failure_in_one_product_does_not_stop_an_unrelated_compliant_product():
    """A customer-defect P1 or a stale artefact on product A halts A only: B's certification
    proceeds and B's staleness is clear. Only the designed company-wide safety gate (an
    integrity failure, or one failure family on >= 3 products and >= 50% of the catalogue)
    reaches every product, and below that threshold B is untouched."""
    from brambleloop.publish import release_gates as G

    db = _db()
    b = _launch0_cir("hexagon-coaster-set")
    tracker = IncidentTracker(db)
    for i in range(3):                                            # A: a real pattern defect
        tracker.report(DefectReport("cloudline-baby-blanket", "1.2.0", "blanket", 4,
                                    f"a{i}", "row 4"))
    assert tracker.publication_halted("cloudline-baby-blanket") is True
    assert tracker.publication_halted(b.slug) is False
    assert _certify(db, _certify_job(db, b, "b-cert"))["granted"] is True

    # a stale artefact on A, and on one more product: 2 of 4 -> below the systemic threshold
    for slug in ("pa", "pb", "pc", "pd"):
        _pv(db, slug, "1.0.0", {"s": slug}, "1" * 64)
    for slug in ("pa", "pb"):
        _record_from(db, slug, "1.0.0", inputs={f"cir:{slug}": P.fingerprint({"x": 1})})
    _sentinel(db)
    assert _systemic(db)["systemic"] is False
    assert G.staleness(db, slug="pc")["blocks"] is False
    assert G.staleness(db, slug="pa")["blocks"] is True


def test_one_releases_failure_does_not_stall_recovery_of_the_others():
    db = _db()
    holder = _holder(db, "ind-seed")
    first = RR.seed_launch0(holder)["seeded"]
    from brambleloop.core.models import JobStatus
    with db.session() as s:                                       # its draft died
        for j in s.scalars(select(Job).where(Job.job_type == "cir.draft")):
            j.status = JobStatus.DEAD
    nxt = RR.seed_launch0(_holder(db, "ind-seed-2"))
    assert nxt["seeded"] and nxt["seeded"] != first and first[0] in nxt["already_seeded"]


# ---- delta review N1: every "current release" reader, out of order --------------------------

def _out_of_order(db, slug=None):
    """1.1.0 certified first, 1.0.0 inserted after it (the reachable out-of-order state)."""
    cir = _launch0_cir().to_dict()
    slug = slug or cir["slug"]
    _pv(db, slug, "1.1.0", dict(cir, slug=slug, version="1.1.0"), "b" * 64)
    _pv(db, slug, "1.0.0", dict(cir, slug=slug, version="1.0.0"), "a" * 64)
    return slug


def test_n1_teardown_current_release_is_the_highest_version():
    from brambleloop.teardown import enforce

    db = _db()
    slug = _out_of_order(db)
    assert enforce.current_release(db, slug)["version"] == "1.1.0"


def test_n1_a_targeted_rebuild_targets_the_newest_release():
    from brambleloop.runtime.release import handle_chain_rebuild

    db = _db()
    slug = _out_of_order(db)
    key = P.pdf_key(slug, "1.1.0", "US")
    _record_from(db, slug, "1.1.0", key=key, inputs={f"cir:{slug}": P.fingerprint({"x": 1})})
    job = JobQueue(db).enqueue("listing", "chain.rebuild",
                               {"product_slug": slug, "artefacts": [f"pdf:{key}"],
                                "reason": "test"}, idempotency_key="n1-rebuild")
    handle_chain_rebuild(_ctx(db, job))
    with db.session() as s:
        builds = [j.inputs for j in s.scalars(select(Job).where(
            Job.job_type.in_(("assets.build", "gate.certify"))))]
    assert builds, "the targeted rebuild enqueued nothing"
    for inputs in builds:
        version = inputs.get("version") or (inputs.get("cir") or {}).get("version")
        assert version == "1.1.0", inputs


def test_n1_inventory_chain_evidence_reports_the_newest_release():
    from brambleloop.products import inventory

    db = _db()
    slug = _out_of_order(db)
    try:
        out = inventory.chain_evidence(db, slug)
    except Exception as exc:  # noqa: BLE001 - only the release selection is under test
        raise AssertionError(f"chain_evidence raised {type(exc).__name__}: {exc}")
    assert out["release"]["version"] == "1.1.0", out["release"]


def test_n1_the_display_readers_use_the_same_newest_release():
    from brambleloop.ops.artefacts import newest_certified

    db = _db()
    slug = _out_of_order(db)
    with db.session() as s:
        assert newest_certified(s, slug).version == "1.1.0"
    src = ROOT / "src" / "brambleloop"
    for rel in ("app/command_center/readers.py", "app/command_center/ask.py",
                "seasonal/benchmark_matrix.py", "teardown/lab.py", "teardown/enforce.py",
                "products/inventory.py", "runtime/release.py"):
        assert "newest_release(" in (src / rel).read_text(), rel


def test_n1_an_older_version_is_never_newly_certified_after_a_newer_one():
    db = _db()
    cir = _launch0_cir()                                    # hexagon-coaster-set@1.2.0
    _pv(db, cir.slug, "1.3.0", dict(cir.to_dict(), version="1.3.0"), "e" * 64)
    out = _certify(db, _certify_job(db, cir, "older"))
    assert out["granted"] is False and out["refused"] == "older_than_newest", out
    assert "gate.certify_older_than_newest" in _actions(db, f"{cir.slug}@{cir.version}")
    with db.session() as s:
        assert {v for (v,) in s.execute(select(PatternVersion.version).join(Product).where(
            Product.slug == cir.slug))} == {"1.3.0"}


# ---- delta review N3: a live listing of a superseded release is owner-visible ---------------

def test_n3_a_live_listing_of_a_superseded_release_raises_an_owner_visible_p2():
    from brambleloop.core.models import Listing
    from brambleloop.ops import incident_lifecycle as IL

    db = _db()
    _pv(db, "hex", "1.0.0", {"rows": 12}, "a" * 64)
    with db.session() as s:
        s.add(Listing(product_slug="hex", version="1.0.0", title="t", description="",
                      tags=[], price_cad=5.0, state="active", etsy_listing_id="123"))
    assert RR.superseded_live_listings(db)["opened"] == []      # 1.0.0 is the newest
    _pv(db, "hex", "1.1.0", {"rows": 14}, "b" * 64)
    out = RR.superseded_live_listings(db)
    sig = "listing.superseded_live:hex@1.0.0"
    assert out["opened"] == [sig]
    with db.session() as s:
        inc = s.scalar(select(Incident).where(Incident.signature == sig))
        assert inc.severity == "P2" and inc.halts_publication is False
        row = IL._row(inc)
        assert row["remediation_owner"] == "owner" and row["needs_owner_path"] is False
    assert IncidentTracker(db).publication_halted("hex") is False   # 1.1.0 unaffected
    assert RR.superseded_live_listings(db)["held"] == [sig]         # restated, not doubled
    with db.session() as s:
        s.scalar(select(Listing)).state = "withdrawn"
    assert RR.superseded_live_listings(db)["resolved"] == [sig]


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback
                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
