"""eng/stale-rebuild-loop: the stale-artefact loop converges, and model.probe stops re-billing.

Production (build ea3aacc7, read back 2026-11-18T13:53Z): systemic halt #380 open since
2026-10-11; 14 products halted by stale-artefact; the sentinel's last propagation said 50
rebuilds were "already queued" while zero rebuild jobs were unfinished; 23 rebuild jobs ran
in 7 days and not one produced a verified rebuild. Root causes, each pinned below by a test
that fails on the old code:

(a) `rebuild_graph.enqueue` counted a product whose last attempt had *ended* (waiting out
    RETRY_AFTER, or today's retry already used) -- and a held product -- as "already queued".
    Now: already_queued = a chain.rebuild for the product is in flight; the rest are reported
    as `retry_waiting` / `retry_held`.
(b) The rebuild never converged: the same rebuild that remade a product's PDF/charts/copy
    reached `marketing.schedule` before the hourly sweep closed the sentinel rows for those
    artefacts, and the marketing waiver counted them, so stale marketing was refused on every
    attempt. The verify pass also required every ref the sentinel named (all products' moved
    refs) to be on each row, so a correctly rebuilt row could never bind.
(c) `rebuild-incomplete` was opened after three verify checks and nothing ever resolved it
    (not even a verified rebuild). Now a verified rebuild and the sentinel's provenance check
    close it; after REBUILD_MAX_ATTEMPTS attempts at one change the product is held with a
    named reason instead of looping; the systemic halt resolves (ops.truth ->
    escalate_systemic) once the per-product staleness is gone.

Problem 2: `model.probe` (6-hourly) billed the identical request four times a day; the paid
call store replays within one job only, so a fresh, uncontradicted success is now reused.

The rebuild end-to-end test drives the real chain on SQLite; the production-shaped tests run on
SQLite and, when a local PostgreSQL toolchain exists, on a disposable PostgreSQL cluster.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit  # noqa: E702
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

_TMP = tempfile.mkdtemp(prefix="eng_stale_rebuild_")
os.environ.setdefault("BRAMBLELOOP_ARTIFACT_DIR", os.path.join(_TMP, "artifacts"))

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (AuditLog, Incident, Job, JobStatus, Phase,  # noqa: E402
                                     Product, utcnow)
from brambleloop.ops import artefacts as A  # noqa: E402
from brambleloop.ops import incident_lifecycle as L  # noqa: E402
from brambleloop.ops import production_evidence as PE  # noqa: E402
from brambleloop.ops import rebuild_graph as G  # noqa: E402
from brambleloop.publish import release_gates  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401 - registers handlers
from brambleloop.runtime import release  # noqa: E402
from brambleloop.runtime.worker import Worker  # noqa: E402

# The fourteen products production halted on stale-artefact (evidence 2026-11-18).
SLUGS = ["autumn-oak-mosaic-throw", "cloudline-baby-blanket", "harvest-table-runner",
         "hexie-coaster-set", "market-basket-trio", "mosaic-placemat-pair",
         "nordic-forest-mosaic-throw", "nordic-star-ornaments", "pet-snuggle-mat",
         "pressed-flower-motifs", "pumpkin-cluster-set", "spooky-garland",
         "valentine-heart-garland", "winter-village-graphghan"]

_MAKE_DB = None          # set per engine by the runner


def _sqlite_db():
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='esrl-', dir=_TMP)}/t.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _db():
    return (_MAKE_DB or _sqlite_db)()


def _run_job(db, agent, job_type, inputs, key):
    job = JobQueue(db).enqueue(agent, job_type, inputs, priority=0, idempotency_key=key)
    Worker(db, f"w-{key}", phase=Phase.SHADOW, job_types=[job_type]).run_once()
    with db.session() as s:
        row = s.get(Job, job.id)
        s.expunge(row)
        return row


class _MovedChain:
    """`release.CHAIN_VERSION` moved for the duration (a deploy that moves `chain:release`)."""

    def __init__(self, suffix="-moved"):
        self.suffix = suffix

    def __enter__(self):
        self.saved = release.CHAIN_VERSION
        release.CHAIN_VERSION = self.saved + self.suffix
        return self

    def __exit__(self, *exc):
        release.CHAIN_VERSION = self.saved


def _no_policy():
    from brambleloop.gates import platform_policy

    real = platform_policy.unreviewed_changes
    platform_policy.unreviewed_changes = lambda db: []
    return lambda: setattr(platform_policy, "unreviewed_changes", real)


def _production_estate(db, slugs=SLUGS):
    """Products with recorded artefacts built under the chain fingerprint *before* a deploy."""
    old = A.chain_fingerprint()
    with db.session() as s:
        for slug in slugs:
            s.add(Product(slug=slug, title=slug))
        s.flush()
        for slug in slugs:
            for cls, key in (("pdf", f"{slug}@1.0.0#pdf-us"),
                             ("marketing_asset", f"{slug}:pinterest:{A.fingerprint(slug)[:16]}")):
                A.record(s, artefact_class=cls, artefact_key=key, product_slug=slug,
                         inputs={"chain:release": old})
    return old


def _sentinel(db, tag):
    job = _run_job(db, "orchestrator", "ops.sentinel", {}, f"sentinel-{tag}")
    assert job.status == JobStatus.DONE, job.last_error
    return job.outputs


def _finish_all_rebuilds(db, at=None):
    with db.session() as s:
        for j in s.scalars(select(Job).where(Job.job_type == "chain.rebuild")):
            j.status, j.finished_at = JobStatus.DONE, at or utcnow()


# --- (a) "already queued" means a job in flight ----------------------------------------------

def test_a_finished_attempt_is_reported_waiting_not_already_queued():
    """The production contradiction: last_propagation_already_queued 50 with
    rebuild_jobs_unfinished 0. On the old code this reads already_queued == 28."""
    db = _db()
    _production_estate(db)
    with _MovedChain():
        first = _sentinel(db, "1")
        assert len(first["rebuild_enqueued"]) == 2 * len(SLUGS), first["rebuild_enqueued"]
        _finish_all_rebuilds(db)                       # every attempt ended (refused: no release)
        second = _sentinel(db, "2")
        assert second["rebuild_enqueued"] == [], second
        assert second["rebuild_already_queued"] == [], second["rebuild_already_queued"]
        assert sorted(second["rebuild_retry_waiting"]) == SLUGS, second
        ev = PE.stale_rebuilds(db, now=datetime.now(timezone.utc))
        assert ev["rebuild_jobs_unfinished"] == 0
        assert ev["last_propagation_already_queued"] == 0, ev
        assert ev["last_propagation_retry_waiting"] == len(SLUGS), ev
        # a product with a rebuild genuinely in flight (a verify pass) *is* already queued
        JobQueue(db).enqueue("listing", "chain.rebuild",
                             {"product_slug": SLUGS[0], "artefacts": ["x:y"], "verify": 1},
                             idempotency_key="live-verify")
        third = _sentinel(db, "3")
        assert {k.split(":", 2)[1].split("@")[0].split(":")[0]
                for k in third["rebuild_already_queued"]} == {SLUGS[0]}, third
        assert SLUGS[0] not in third["rebuild_retry_waiting"]


def test_a_held_product_is_reported_held_not_already_queued():
    db = _db()
    _production_estate(db, SLUGS[:3])
    restore = _no_policy()
    try:
        with _MovedChain():
            _sentinel(db, "1")
            _finish_all_rebuilds(db, at=utcnow() - timedelta(hours=13))
            with db.session() as s:
                s.add(Incident(severity="P0", product_slug=SLUGS[0], halts_publication=True,
                               signature=f"authority_chain_tamper:{SLUGS[0]}", summary="t"))
            out = _sentinel(db, "2")
        assert SLUGS[0] in out["rebuild_retry_held"], out
        assert "authority_chain_tamper" in out["rebuild_retry_held"][SLUGS[0]]
        assert not any(SLUGS[0] in k for k in out["rebuild_already_queued"]), out
        assert sorted(out["rebuild_retried"]) == SLUGS[1:3], out
    finally:
        restore()


def test_a_product_rebuild_names_only_its_own_moved_refs():
    """(b) A per-product job named every product's moved refs; the verify pass then demanded
    `cir:<other product>` on this product's rows, so a correct rebuild never bound."""
    db = _db()
    with db.session() as s:
        for slug in ("a", "b"):
            A.record(s, artefact_class="pdf", artefact_key=f"{slug}@1#pdf", product_slug=slug,
                     inputs={"chain:release": "0" * 16, f"cir:{slug}": "1" * 16})
    changed = {"chain:release": "2" * 16, "cir:a": "3" * 16, "cir:b": "4" * 16}
    with db.session() as s:
        G.enqueue(s, JobQueue(db), changed=changed, per="product", reason="t")
    with db.session() as s:
        jobs = {j.inputs["product_slug"]: j.inputs for j in
                s.scalars(select(Job).where(Job.job_type == "chain.rebuild"))}
    assert sorted(jobs["a"]["fingerprints"]) == ["chain:release", "cir:a"], jobs["a"]
    assert sorted(jobs["b"]["fingerprints"]) == ["chain:release", "cir:b"], jobs["b"]


# --- (b) the marketing rebuild is not refused by rows the same rebuild already cured --------

def _gate_with(db, *, outstanding, fresh):
    real = G.publication_gate
    G.publication_gate = lambda s, slug: {"may_publish": False, "why": "stale",
                                          "outstanding": list(outstanding),
                                          "fresh": list(fresh)}
    restore = _no_policy()
    try:
        return release_gates.staleness(db, slug="a")
    finally:
        G.publication_gate = real
        restore()


def test_b_marketing_rebuild_waives_rows_whose_artefact_already_reads_fresh():
    db = _db()
    mk = "marketing_asset:a:pin:1"
    with db.session() as s:
        s.add(Product(slug="a", title="a"))
        for sig in (f"stale-artefact:{mk}", "stale-artefact:pdf:a@1#pdf-us",
                    "stale-artefact:chart:a@1#chart"):
            s.add(Incident(severity="P1", product_slug="a", halts_publication=True,
                           signature=sig, summary="stale"))
        s.add(Incident(severity="P2", product_slug="a", halts_publication=True,
                       signature="rebuild-incomplete:a", summary="incomplete", report_count=1))
    out = _gate_with(db, outstanding=[mk], fresh=["pdf:a@1#pdf-us", "chart:a@1#chart"])
    assert out["outstanding_only_marketing"] is True, out
    assert out["blocks"] is True and out["halted"] is True      # publication still refuses
    # a row whose artefact is still stale (not in `fresh`) still refuses the rebuild
    assert _gate_with(db, outstanding=[mk], fresh=["pdf:a@1#pdf-us"])[
        "outstanding_only_marketing"] is False
    # round 3 (review M-E of 0d2e6cbc): a pre-branch row (no `attempts` in its detail) is not
    # exhausted by its count alone -- it gets a fresh budget first, so it is still waived
    with db.session() as s:
        s.scalar(select(Incident).where(Incident.signature == "rebuild-incomplete:a")
                 ).report_count = G.REBUILD_MAX_ATTEMPTS
    assert _gate_with(db, outstanding=[mk], fresh=["pdf:a@1#pdf-us", "chart:a@1#chart"])[
        "outstanding_only_marketing"] is True
    # an exhausted rebuild-incomplete (its budget spent under the new code) is a hold,
    # never waived
    with db.session() as s:
        s.scalar(select(Incident).where(Incident.signature == "rebuild-incomplete:a")
                 ).detail = {"attempts": G.REBUILD_MAX_ATTEMPTS}
    assert _gate_with(db, outstanding=[mk], fresh=["pdf:a@1#pdf-us", "chart:a@1#chart"])[
        "outstanding_only_marketing"] is False


# --- (c) bound, named hold, and resolution ----------------------------------------------------

class _Ctx:
    class _J:
        id = 1
        inputs: dict = {}

    def __init__(self, db):
        self.db, self.job = db, self._J()


def test_c_rebuild_incomplete_is_bounded_and_then_held_with_a_named_reason():
    db = _db()
    restore = _no_policy()
    try:
        with db.session() as s:
            s.add(Product(slug="a", title="a"))
            s.add(AuditLog(actor="marketing", action="marketing.blocked", artifact="a@1.0.0",
                           detail={"reasons": ["halted (#173): something refused it"]}))
        fp = {"chain:release": {"old": "0" * 16, "new": "1" * 16}}
        for n in range(1, G.REBUILD_MAX_ATTEMPTS):
            release._rebuild_incomplete(_Ctx(db), "a", "1.0.0", stale=["marketing_asset:a:x"],
                                        reason="t", fingerprints=fp, checks=3)
            assert release_gates.retry_hold_reason(db, slug="a") is None, n   # attempts left
        detail = release._rebuild_incomplete(_Ctx(db), "a", "1.0.0",
                                             stale=["marketing_asset:a:x"], reason="t",
                                             fingerprints=fp, checks=3)
        assert detail["attempts"] == G.REBUILD_MAX_ATTEMPTS and detail["held"], detail
        why = release_gates.retry_hold_reason(db, slug="a")
        assert why and "could not complete" in why and "something refused it" in why, why
        with db.session() as s:
            row = s.scalar(select(Incident).where(Incident.signature == "rebuild-incomplete:a"))
            assert row.product_slug == "a" and row.halts_publication and not row.resolved
        # a different change is a fresh budget: no longer held
        release._rebuild_incomplete(_Ctx(db), "a", "1.0.0", stale=["marketing_asset:a:x"],
                                    reason="t", checks=3,
                                    fingerprints={"chain:release": {"new": "2" * 16}})
        assert release_gates.retry_hold_reason(db, slug="a") is None
    finally:
        restore()


def test_c_withheld_release_holds_the_retry_instead_of_a_silent_daily_refusal():
    from brambleloop.core.models import PatternVersion
    from brambleloop.publish import withholding

    db = _db()
    restore = _no_policy()
    try:
        with db.session() as s:
            p = Product(slug="a", title="a")
            s.add(p)
            s.flush()
            s.add(PatternVersion(product_id=p.id, version="1.0.0", cir_json={"x": 1},
                                 certified=True, release_hash="ab" * 16, certificate={}))
        assert release_gates.retry_hold_reason(db, slug="a") is None
        withholding.record(db, "a", "1.0.0", kind=withholding.KINDS[0], reason="teardown QA")
        why = release_gates.retry_hold_reason(db, slug="a")
        assert why and "withheld" in why, why
    finally:
        restore()


def test_c_staleness_families_never_hold_and_the_systemic_halt_resolves_after():
    """Three of three products stale and rebuild-incomplete: the company-wide halt is the
    staleness escalated, so it holds nothing; once provenance reads fresh the sentinel closes
    the per-product rows and escalate_systemic (ops.truth) closes the halt."""
    db = _db()
    slugs = SLUGS[:3]
    _production_estate(db, slugs)
    restore = _no_policy()
    try:
        with _MovedChain():
            _sentinel(db, "1")
            with db.session() as s:
                for slug in slugs:
                    s.add(Incident(severity="P2", product_slug=slug, halts_publication=True,
                                   signature=f"rebuild-incomplete:{slug}", summary="i",
                                   report_count=1))
                ev = L.escalate_systemic(s)
            assert ev["systemic"] and ev["opened"], ev
            assert set(ev["widespread_families"]) == {"stale-artefact", "rebuild-incomplete"}
            for slug in slugs:
                assert release_gates.retry_hold_reason(db, slug=slug) is None, slug
            # the rebuild is delivered: every row re-recorded under the moved chain
            with db.session() as s:
                _rerecord(s, slugs)
            out = _sentinel(db, "2")
            assert out["stale"] == 0, out
            assert sorted(out["rebuild_incomplete_cleared"]) == sorted(
                f"rebuild-incomplete:{s_}" for s_ in slugs), out
            with db.session() as s:
                open_ = [i.signature for i in s.scalars(select(Incident).where(
                    Incident.resolved == False))]  # noqa: E712
                assert not [x for x in open_ if x.startswith(("stale-artefact:",
                                                              "rebuild-incomplete:"))], open_
                ev = L.escalate_systemic(s)
            assert not ev["systemic"] and L.SYSTEMIC_SIGNATURE in ev["resolved"], ev
            with db.session() as s:
                halt = s.scalar(select(Incident).where(
                    Incident.signature == L.SYSTEMIC_SIGNATURE))
                assert halt.resolved and halt.detail.get("resolution"), halt.detail
    finally:
        restore()


def _rerecord(s, slugs):
    from brambleloop.core.models import ArtefactProvenance

    for row in list(s.scalars(select(ArtefactProvenance).where(
            ArtefactProvenance.product_slug.in_(slugs)))):
        A.record(s, artefact_class=row.artefact_class, artefact_key=row.artefact_key,
                 product_slug=row.product_slug,
                 inputs={"chain:release": A.chain_fingerprint()})


# --- end to end on the real chain (SQLite): stale -> rebuilt -> verified -> resolved ---------

def _drain(db, name, limit=800):
    w = Worker(db, name, phase=Phase.SHADOW, lease_seconds=900)
    for _ in range(limit):
        if not w.run_once():
            break


def test_end_to_end_a_moved_chain_converges_in_one_attempt():
    from brambleloop.core.models import ArtefactProvenance
    from brambleloop.products import builder

    db = _sqlite_db()
    cir = builder.for_slug("cloudline-baby-blanket")
    JobQueue(db).enqueue("validator", "cir.compile", {"cir": cir.to_dict()},
                         idempotency_key="e2e-compile")
    _drain(db, "e2e-build")
    slug = cir.slug
    with db.session() as s:
        marketing = [f"marketing_asset:{r.artefact_key}" for r in s.scalars(
            select(ArtefactProvenance).where(ArtefactProvenance.product_slug == slug,
                                             ArtefactProvenance.artefact_class
                                             == "marketing_asset"))]
    assert marketing, "the chain drafted no content"
    with _MovedChain():
        first = _sentinel(db, "e2e-1")
        assert first["stale"] > len(marketing) and first["rebuild_enqueued"], first
        for _ in range(5):                               # the stage chain, then each check
            _drain(db, "e2e-drain")
            with db.session() as s:
                for j in s.scalars(select(Job).where(Job.status == JobStatus.PENDING)):
                    j.run_after = utcnow()               # the 20-minute delay, elapsed
        with db.session() as s:
            verdicts = A.check(s, current=A.current_from_db(s))
            stale = [f"{v.artefact_class}:{v.artefact_key}" for v in verdicts
                     if v.state == A.STALE]
            completed = {a.artifact for a in s.scalars(select(AuditLog).where(
                AuditLog.action == "chain.rebuild_completed"))
                if not (a.detail or {}).get("already_fresh")}
            open_ = [i.signature for i in s.scalars(select(Incident).where(
                Incident.resolved == False))]  # noqa: E712
            resolved = {i.signature: (i.detail or {}).get("resolution") for i in s.scalars(
                select(Incident).where(Incident.resolved == True))}  # noqa: E712
        assert stale == [], f"artefacts still stale after the rebuild: {stale}"
        assert set(marketing) <= completed, sorted(set(marketing) - completed)
        assert not [x for x in open_ if x.startswith(("stale-artefact:", "rebuild-incomplete:"))
                    ], open_
        assert all(resolved[f"stale-artefact:{k}"] for k in marketing), resolved
        assert not any(k.startswith("rebuild-incomplete:") for k in resolved), resolved
        second = _sentinel(db, "e2e-2")
        assert second["stale"] == 0 and second.get("rebuild_enqueued", []) == [], second
        ev = PE.stale_rebuilds(db, now=datetime.now(timezone.utc))
        assert ev["rebuilds_verified_24h"] >= len(marketing), ev
        assert ev["open_stale_artefact_incidents"] == 0 and ev["open_rebuild_incomplete"] == 0
        # (b) a request naming another product's moved ref still binds this product's row
        node = marketing[0]
        job = _run_job(db, "listing", "chain.rebuild",
                       {"product_slug": slug, "artefacts": [node], "reason": "foreign ref",
                        "fingerprints": {"chain:release": {"new": A.chain_fingerprint()},
                                         "cir:some-other-product": {"new": "f" * 16}}},
                       "e2e-foreign-ref")
        assert job.outputs["already_fresh"] == [node], job.outputs
        assert job.outputs["fresh_but_unbound"] == [], job.outputs


# --- Problem 2: model.probe reuses a fresh, uncontradicted success ----------------------------

def _stub_probe(calls, ok=True):
    from brambleloop.gateway import anthropic as gw

    # round 2 (review M-D): the stub records what the real probe records -- the probe model
    # and the non-secret key fingerprint -- under a configured (dummy) key, since a reuse is
    # now tied to both.
    os.environ["ANTHROPIC_API_KEY"] = "test-dummy-key-not-a-secret"

    def fake(db, *, job_id=None, now=None, **kw):
        calls.append(now)
        record = {"at": (now or datetime.now(timezone.utc)).isoformat(),
                  "model": gw.PROBE_MODEL, "key_fp": gw.key_fingerprint(),
                  "ok": ok, "reason": "" if ok else "credit balance is too low"}
        with db.session() as s:
            s.add(AuditLog(actor="orchestrator", action="model.probe", artifact="stub",
                           detail=record))
        return record
    real = gw.probe
    gw.probe = fake

    def restore():
        gw.probe = real
        os.environ.pop("ANTHROPIC_API_KEY", None)
    return restore


def test_p2_four_cadence_runs_a_day_bill_once():
    from brambleloop.gateway import anthropic as gw
    from brambleloop.gateway.paid_calls import PaidCallRecord

    db = _db()
    calls: list = []
    restore = _stub_probe(calls)
    t0 = datetime(2026, 11, 18, 0, 5, tzinfo=timezone.utc)
    try:
        first = gw.probe_if_due(db, now=t0)
        assert first["ok"] and len(calls) == 1
        for h in (6, 12, 18):                           # the 6-hourly cadence, same day
            out = gw.probe_if_due(db, now=t0 + timedelta(hours=h))
            assert out["ok"] and out["reused"] and out["cost_cad"] == 0.0, out
        assert len(calls) == 1, calls
        assert gw.usable(db) is True and gw.last_probe(db)["reused"] is True
        gw.probe_if_due(db, now=t0 + timedelta(hours=24, minutes=1))   # a day on: re-asked
        assert len(calls) == 2, calls
        # the provider refusing the account since the last probe contradicts it: re-asked
        # (FIX-CYCLE-PROOF-BILLING: a ProviderUnusable decline, not any failed call)
        with db.session() as s:
            s.add(PaidCallRecord(key="k-fail", effect="anthropic.messages", job_id=9,
                                 job_type="identity.measure", fingerprint="f" * 64,
                                 outcome="DECLINED",
                                 error="ProviderUnusable: anthropic 400: credit balance",
                                 at=t0 + timedelta(hours=25)))
        gw.probe_if_due(db, now=t0 + timedelta(hours=26))
        assert len(calls) == 3, calls
        # an owner's on-demand run always asks
        gw.probe_if_due(db, now=t0 + timedelta(hours=26, minutes=5), force=True)
        assert len(calls) == 4, calls
    finally:
        restore()


def test_p2_a_failed_probe_is_never_reused():
    from brambleloop.gateway import anthropic as gw

    db = _db()
    calls: list = []
    restore = _stub_probe(calls, ok=False)
    t0 = datetime(2026, 11, 18, 0, 5, tzinfo=timezone.utc)
    try:
        gw.probe_if_due(db, now=t0)
        out = gw.probe_if_due(db, now=t0 + timedelta(hours=6))
        assert len(calls) == 2 and not out.get("reused") and gw.usable(db) is False, out
    finally:
        restore()


def test_p2_the_cadence_handler_does_not_rebill_an_unchanged_probe():
    """The production shape: job_type model.probe, four jobs, one request fingerprint. On the
    old code the second job calls the provider again."""
    db = _db()
    calls: list = []
    restore = _stub_probe(calls)
    try:
        for n in range(3):
            job = _run_job(db, "orchestrator", "model.probe", {}, f"cadence:model_probe:{n}")
            assert job.status == JobStatus.DONE, job.last_error
            assert job.outputs["ok"] is True
        assert len(calls) == 1, calls
        assert job.outputs.get("reused") is True
        job = _run_job(db, "orchestrator", "model.probe", {"on_demand": True}, "od-probe")
        assert len(calls) == 2 and not job.outputs.get("reused"), job.outputs
    finally:
        restore()


# --- runner ------------------------------------------------------------------------------------

PG_TESTS = ("test_a_finished_attempt_is_reported_waiting_not_already_queued",
            "test_a_held_product_is_reported_held_not_already_queued",
            "test_a_product_rebuild_names_only_its_own_moved_refs",
            "test_b_marketing_rebuild_waives_rows_whose_artefact_already_reads_fresh",
            "test_c_rebuild_incomplete_is_bounded_and_then_held_with_a_named_reason",
            "test_c_withheld_release_holds_the_retry_instead_of_a_silent_daily_refusal",
            "test_c_staleness_families_never_hold_and_the_systemic_halt_resolves_after",
            "test_p2_four_cadence_runs_a_day_bill_once",
            "test_p2_the_cadence_handler_does_not_rebill_an_unchanged_probe")


def _pg_factory(base_url):
    """A brand-new empty database in the disposable cluster per test."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url

    url = make_url(base_url)
    counter = [0]

    def make():
        counter[0] += 1
        name = f"esrl_{os.getpid()}_{counter[0]}"
        admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
        with admin.connect() as c:
            c.execute(text(f'CREATE DATABASE "{name}"'))
        admin.dispose()
        db = Database(str(url.set(database=name).render_as_string(hide_password=False)),
                      scratch=True)
        db.create_all()
        Registry(db).seed_defaults()
        return db
    return make


def _run(names, label):
    fails = 0
    for name in names:
        fn = globals()[name]
        try:
            fn()
            print(f"OK   {label}{name}")
        except Exception as e:  # noqa: BLE001
            import traceback

            traceback.print_exc()
            fails += 1
            print(f"FAIL {label}{name}", repr(e))
    return fails


if __name__ == "__main__":
    names = [n for n in list(globals()) if n.startswith("test_")]
    fails = _run(names, "")
    try:
        from test_codex_v0_postgres import _disposable_cluster
    except Exception:  # noqa: BLE001
        _disposable_cluster = None
    if _disposable_cluster is not None:

        with _disposable_cluster():
            raw = os.environ.get("CODEX_V0_TEST_DATABASE_URL")
            if raw and os.environ.get("CODEX_V0_DISPOSABLE_DATABASE") == "yes":
                _MAKE_DB = _pg_factory(raw)
                fails += _run(PG_TESTS, "[postgres] ")
                _MAKE_DB = None
            else:
                print("SKIP [postgres] no local PostgreSQL toolchain: production-shaped "
                      "tests ran on SQLite only")
    print(f"{fails} failure(s)")
    sys.exit(1 if fails else 0)
