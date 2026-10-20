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


def test_an_unversioned_marketing_asset_is_matched_to_the_release_it_was_built_from():
    db = _db()
    _pv(db, "hex", "1.0.0", {"rows": 12}, "a" * 64)
    _record_from(db, "hex", "1.0.0", cls="marketing_asset", key=P.marketing_key("hex", "pin", "t"))
    _pv(db, "hex", "1.1.0", {"rows": 14}, "b" * 64)
    out = _sentinel(db)
    assert [v["state"] for v in out["verdicts"]] == [P.SUPERSEDED]
    # a marketing asset whose design matches no certified release is still judged stale
    _record_from(db, "hex", "1.1.0", cls="marketing_asset", key=P.marketing_key("hex", "pin", "u"),
                 inputs={"cir:hex": P.fingerprint({"rows": 99})})
    out = _sentinel(db)
    assert out["stale"] == 1 and out["publication_blocked"] == ["hex"]


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
    out = pipeline.handle_certify(_ctx(db, job))
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
    out = pipeline.handle_certify(_ctx(db, retry))
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
    pipeline.handle_certify(_ctx(db, _certify_job(db, cir, "first")))
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
    assert pipeline.handle_certify(_ctx(db, retry)).get("halted_by_incident") is True
    second = RR.halted_releases(db)[0]["halt_audit_id"]
    assert second > first
    assert RR.retry_halted(holder)["still_halted"]


# ---- R5: Launch-0 releases the chain never drafted ------------------------------------------

def test_every_uncertified_launch0_release_is_drafted_once_through_the_normal_job():
    db = _db()
    cir = _launch0_cir("cloudline-baby-blanket")
    _pv(db, cir.slug, cir.version, cir.to_dict(), "f" * 64)       # already certified
    holder = _ctx(db, JobQueue(db).enqueue("listing", "chain.rebuild", {}, idempotency_key="z"))
    out = RR.seed_launch0(holder)
    assert out["certified"] == [f"{cir.slug}@{cir.version}"]
    assert len(out["seeded"]) == 9
    for rel in ("market-basket-small@1.2.0", "market-basket-medium@1.2.0",
                "market-basket-large@1.2.0", "hexagon-coaster-set@1.2.0",
                "nordic-forest-mosaic-throw-baby@1.3.0", "housewarming-key-basket@0.1.0"):
        assert rel in out["seeded"], rel
    again = RR.seed_launch0(holder)
    assert again["seeded"] == [] and len(again["already_seeded"]) == 9
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
    halted = pipeline.handle_certify(_ctx(db, _certify_job(db, cir, f"certify:{cir.slug}")))
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
    granted = pipeline.handle_certify(_ctx(db, retry))
    assert granted["granted"] is True
    assert "gate.certified" in _actions(db, rel)

    # the newest release now is 1.2.0: 1.1.0 is superseded and may not publish
    from brambleloop.publish import release_gates as G
    assert G.superseded_release(db, slug=cir.slug, version="1.1.0")["superseded"] is True
    assert G.superseded_release(db, slug=cir.slug, version=cir.version)["superseded"] is False
    out = handle_chain_rebuild(_ctx(db, JobQueue(db).enqueue(
        "listing", "chain.rebuild", {}, idempotency_key="hourly-2")))
    assert out["recovery"]["halted_certifications"]["retried"] == []


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
