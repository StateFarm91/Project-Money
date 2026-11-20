"""ENG-MOTIF-BACKLOG (owner P0): paid renders whose motif check the budget gate refused are
recovered by re-checking the motif only -- never by regenerating them.

A real certification of the Cloudline blanket on a scratch database in SHADOW, sockets closed.
The filed render rows carry the refusal `motif_fidelity.check` really writes when the paid-provider
gate refuses (`[no_budget_reservation] ...`). The re-check runs through the real worker, the
real `check_budget` reservation and the real `motif_fidelity.check`, with a stub vision provider
(no network) and every image generator replaced by one that fails the test if it is called.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_motif_backlog.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import io
import json
import os
import socket
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
_TMP = tempfile.mkdtemp(prefix="motif_backlog_")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ.setdefault("BRAMBLELOOP_PHASE", "shadow")


def _refuse(*_a, **_k):
    raise OSError("network refused: this test makes no outbound connection")


socket.socket.connect = _refuse
socket.create_connection = _refuse

from PIL import Image  # noqa: E402
from sqlalchemy import select  # noqa: E402

import fixtures_etsy_taxonomy as FX  # noqa: E402
from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.artifacts import ArtifactStore  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    AuditLog, EtsyTaxonomySnapshot, Job, JobStatus, Listing, OperatingReading, PatternVersion,
    Phase,
)
from brambleloop.gateway import anthropic as A  # noqa: E402
from brambleloop.gateway import paid_provider_gate as G  # noqa: E402
from brambleloop.products import launch0 as L  # noqa: E402
from brambleloop.publish import listing_asset  # noqa: E402
from brambleloop.publish import listing_package as LP  # noqa: E402
from brambleloop.publish import model_photography as MP  # noqa: E402
from brambleloop.publish import motif_backlog as MB  # noqa: E402
from brambleloop.publish import motif_fidelity as MF  # noqa: E402
from brambleloop.publish import owned_photography as OP  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline, release  # noqa: E402,F401
from brambleloop.runtime.worker import CADENCES, Worker, handlers  # noqa: E402

_CACHE: dict = {}
REFUSAL = ("the comparison call failed: [no_budget_reservation] no live company-budget "
           "reservation for this call (reservation None); the accounting evidence the month "
           "ceiling writes is missing, so the call is refused (fail closed)")


# ---- stubs --------------------------------------------------------------------------------

class _Resp:
    def __init__(self, text):
        self.text, self.input_tokens, self.output_tokens = text, 1200, 120


class StubVision:
    """A vision provider that answers from a script. No network. Counts its calls."""

    name = "anthropic"
    model = A.DEFAULT_MODEL

    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = []
        p = A.AnthropicProvider(model=self.model)
        self.cost_per_1k_input_cad = p.cost_per_1k_input_cad
        self.cost_per_1k_output_cad = p.cost_per_1k_output_cad

    def see(self, system, prompt, image_urls, **kw):
        self.calls.append(list(image_urls))
        answer = self.answers.pop(0) if self.answers else "match"
        if isinstance(answer, BaseException):
            raise answer
        return _Resp(json.dumps(OBSERVED[answer]))


OBSERVED = {
    "match": {"repeating_unit_shape": "diamond lattice", "repeats_across": 11,
              "colour_arrangement": "two colours alternating", "same_pattern_as_chart": True,
              "fabric_readable": True},
    "mismatch": {"repeating_unit_shape": "checkerboard square", "repeats_across": 8,
                 "colour_arrangement": "two colours alternating",
                 "same_pattern_as_chart": False, "fabric_readable": True},
}


def _gate_refusal():
    """The exception the real gate raises through `AnthropicProvider.see` for a call with no
    reservation: PaidCallRefused's text, carried by VisionGateRefused."""
    exc = G.PaidCallRefused("no_budget_reservation", "no live company-budget reservation")
    return A.VisionGateRefused(str(exc), exc.code)


class NoRender(AssertionError):
    pass


@contextmanager
def no_generation():
    """Every image-generation entry point fails the test if it is reached."""
    from brambleloop.gateway import images

    def boom(*_a, **_k):
        raise NoRender("an image was generated during motif recovery")

    with patch.object(images, "generate", boom), patch.object(images, "submit_render", boom):
        yield


@contextmanager
def vision(stub):
    from brambleloop.gateway import providers

    with patch.object(providers, "provider_for", lambda *_a, **_k: stub):
        yield


# ---- fixtures -----------------------------------------------------------------------------

def _db(name):
    db = Database(f"sqlite:///{tempfile.mkdtemp(dir=_TMP)}/{name}.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    snap = FX.snapshot()
    with db.session() as s:
        s.add(EtsyTaxonomySnapshot(sha256="fixture", node_count=len(snap["nodes"]),
                                   nodes=snap["nodes"], properties=snap["properties"]))
    return db


def _run(db, agent, job_type, inputs, key):
    job = JobQueue(db).enqueue(agent, job_type, inputs, idempotency_key=key, priority=0)
    Worker(db, f"w-{key}", phase=Phase.SHADOW, job_types=[job_type],
           lease_seconds=900).run_once()
    with db.session() as s:
        row = s.get(Job, job.id)
        s.expunge(row)
        return row


def _certified(name):
    db = _db(name)
    cir = L.cir_for("cloudline_blanket")
    job = _run(db, "quality_director", "gate.certify", {"cir": cir.to_dict()}, "c")
    assert job.outputs.get("granted"), job.outputs
    with db.session() as s:
        rh = s.scalar(select(PatternVersion)).release_hash
    return db, cir, rh


def _png(seed: int) -> str:
    img = Image.new("RGB", (64, 64), (seed % 255, (seed * 7) % 255, (seed * 13) % 255))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return ArtifactStore().put(f"tests/motif-{seed}.png", buf.getvalue(), "image/png").sha256


def _owned_row(db, cir, seed, *, motif=None, verdict="clear"):
    """An `assets.owned_photography` row as the historical make() filed it."""
    sha = _png(seed)
    motif = motif or {"verdict": MF.UNMEASURABLE, "why": REFUSAL}
    detail = {"made": True, "slug": cir.slug, "version": cir.version,
              "method_version": OP.METHOD_VERSION, "role": "hero", "generated": True,
              "provider": "stub-generator", "disclosed_as_illustration": True,
              "image": {"sha256": sha, "url": f"/api/model-tournament/image/{sha}"},
              "image_ref": f"/tmp/gone/{sha[:8]}.png", "verdict": verdict,
              "why": "asset truth", "motif": motif,
              "motif_verified": motif.get("verdict") == MF.MATCH,
              "motif_why": motif.get("why"),
              "usable_as_listing_asset": verdict == "clear" and motif.get("verdict") == MF.MATCH,
              "spent_cad": 0.11}
    with db.session() as s:
        row = AuditLog(actor="publishing", action=OP.ACTION, detail=detail)
        s.add(row)
        s.flush()
        return row.id, sha


def _model_row(db, cir, seeds, *, motifs, floors_override=None):
    frames = []
    for seed, motif in zip(seeds, motifs):
        sha = _png(seed)
        floors = {f: "pass" for f in MP.FLOORS}
        floors["product_truth"] = ("pass" if motif["verdict"] == MF.MATCH else "fail"
                                   if motif["verdict"] == MF.MISMATCH else "unverifiable")
        floors.update(floors_override or {})
        frames.append({"made": True, "shot": "detail", "slug": cir.slug,
                       "version": cir.version, "method_version": MP.METHOD_VERSION,
                       "generated": True, "carries_model": True, "provider": "stub",
                       "image": {"sha256": sha}, "motif": motif, "floors": floors,
                       "usable_as_listing_asset": all(v == "pass" for v in floors.values())})
    detail = {"made": True, "slug": cir.slug, "version": cir.version,
              "method_version": MP.METHOD_VERSION, "carries_model": True, "generated": True,
              "frames": frames, "floors": MP._combine_floors(frames),
              "usable_as_listing_asset": False}
    with db.session() as s:
        row = AuditLog(actor="publishing", action=MP.ACTION, detail=detail)
        s.add(row)
        s.flush()
        return row.id


def _states(db):
    with db.session() as s:
        return {r.image_sha256: r.state for r in s.scalars(select(MB.MotifRecovery))}


def _jobs(db, job_type):
    with db.session() as s:
        return [(j.inputs or {}) for j in s.scalars(select(Job).where(Job.job_type == job_type))]


# ENG-SUPPLY (INTEG3): every job that ends a product chain enqueues a `supply.admit` refill,
# which admits the NEXT Launch-0 / pool product (market-basket-small, hexagon-coaster-set, ...)
# into the freed slot -- by design, and a different product each time. Draining that too
# would run the whole catalogue's chains, minutes each, none of them the chain under test.
# The drain is bounded to the release's own chain: every job type except supply admission.
CHAIN_JOB_TYPES = [jt for jt in handlers.known() if jt != "supply.admit"]


def _drain(db, limit=60):
    for i in range(limit):
        if not Worker(db, f"drain-{i}", phase=Phase.SHADOW, job_types=CHAIN_JOB_TYPES,
                      lease_seconds=900).run_once():
            return i
    raise AssertionError("the queue did not drain")


def _qualified_floor(frame):
    """STAND-IN (the convention test_motif_reservation uses): a qualified whole-product
    producer, which this base does not have -- PASS exactly when the motif matched. F-852
    gives a generated frame no PASS today, so without it every re-ask is parked."""
    verdict = ((frame or {}).get("motif") or {}).get("verdict")
    return {"status": "PASS" if verdict == MF.MATCH else
            "FAIL" if verdict == MF.MISMATCH else "UNKNOWN"}


@contextmanager
def qualified():
    with patch("brambleloop.visual.product_authority.structural_floor", _qualified_floor):
        yield


def _sweep(db, stub, key, *, floor=True):
    with no_generation(), vision(stub):
        if not floor:
            return _run(db, "publishing", MB.JOB_TYPE, {}, key)
        with qualified():
            return _run(db, "publishing", MB.JOB_TYPE, {}, key)


def _shared():
    if "rel" not in _CACHE:
        _CACHE["rel"] = _certified("shared")
    return _CACHE["rel"]


# ---- 1. registration ----------------------------------------------------------------------

def test_the_job_is_fully_registered():
    from brambleloop.agents.registry import DEFAULT_AGENTS
    from brambleloop.authority import classes
    from brambleloop.autonomy import charters, map as amap
    from brambleloop.ops import retention
    from brambleloop.runtime.pipeline import WORK_KEYS
    from brambleloop.swarm import orchestrate

    jt = MB.JOB_TYPE
    assert handlers.get(jt) is not None
    assert ("motif_backlog", "publishing", jt, 6 * 60 * 60) in CADENCES
    assert jt in next(a for a in DEFAULT_AGENTS if a["name"] == "publishing")["allowed_job_types"]
    Registry(_db("reg")).authorize("publishing", jt)
    assert classes.JOB_CLASS[jt] == classes.JOB_CLASS["assets.owned_photography"]
    assert charters.department_of(jt) == charters.department_of("assets.owned_photography")
    assert WORK_KEYS[jt] == ("work_done",) and orchestrate.JOB_BANDS[jt] == "proven_winner"
    committed = json.loads((ROOT / "src/brambleloop/autonomy/autonomy_map.json").read_text())
    assert committed["counts"] == amap.build()["counts"] and jt in json.dumps(committed)
    assert retention.unknown_read_actions() == []
    assert MB.AUDIT_SWEPT in retention.KNOWN_READ_ACTIONS


# ---- 2. what is a refusal -----------------------------------------------------------------

def test_only_a_budget_refusal_is_recoverable_legacy_and_coded():
    db, cir, _rh = _shared()
    from brambleloop.cir.compiler import compile_cir
    from brambleloop.cir.twin import build_twin

    twin = build_twin(cir, compile_cir(cir))
    path = os.path.join(_TMP, "probe.png")
    Image.new("RGB", (32, 32)).save(path)
    # Legacy: the text production filed before ENG-MOTIF coded the reason.
    assert MB.refusal_code({"verdict": MF.UNMEASURABLE, "why": REFUSAL}) == \
        "no_budget_reservation"
    for code in sorted(MB.BUDGET_CODES):
        why = f"the comparison call failed: [{code}] refused"
        assert MB.refusal_code({"verdict": MF.UNMEASURABLE, "why": why}) == code
    assert MB.refusal_code({"verdict": MF.UNMEASURABLE, "why": "the comparison call failed: "
                            "AgentCeilingExceeded: the day is spent"}) == "AgentCeilingExceeded"
    # Coded (since ENG-MOTIF): the real gate refusing for money is `budget_refused`.
    for code in sorted(MF._BUDGET_GATE_CODES):
        exc = G.PaidCallRefused(code, "refused")
        out = MF.check(db, path, cir, twin,
                       provider=StubVision([A.VisionGateRefused(str(exc), code)]))
        assert MB.refusal_code(out) == MF.UNMEASURED_BUDGET, (code, out)
    # Not this backlog's: a judged mismatch, a genuine unmeasurable, an owner who never
    # activated the provider, plumbing.
    assert MB.refusal_code(MF.check(db, path, cir, twin,
                                    provider=StubVision(["mismatch"]))) is None
    unreadable = {**OBSERVED["match"], "fabric_readable": False}
    stub = StubVision([])
    stub.see = lambda *a, **k: _Resp(json.dumps(unreadable))
    assert MB.refusal_code(MF.check(db, path, cir, twin, provider=stub)) is None
    exc = G.PaidCallRefused("not_activated_by_owner", "no activation")
    assert MB.refusal_code(MF.check(db, path, cir, twin, provider=StubVision(
        [A.VisionGateRefused(str(exc), exc.code)]))) is None
    assert MB.refusal_code(MF.check(db, path, cir, twin, provider=StubVision(
        [A.ProviderUnusable("no key")]))) is None
    assert MB.refusal_code({"verdict": MF.MATCH, "why": REFUSAL}) is None
    assert MB.refusal_code({"verdict": MF.UNMEASURABLE,
                            "why": "the fabric could not be seen [no_budget_reservation]"}) \
        is None
    assert MB.refusal_code({"verdict": MF.UNMEASURABLE, "unmeasured": "gate_refused",
                            "why": REFUSAL}) is None
    assert MB.refusal_code(None) is None


# ---- 3. the backlog is recovered without a single render -----------------------------------

def test_with_every_gate_as_it_is_the_backlog_is_found_and_parked_at_no_cost():
    """The production truth today: every refused render is found, and none is re-asked,
    because a match could not make a generated frame usable (F-852). No call, no spend, no
    regeneration; re-evaluated every sweep."""
    from brambleloop.finance import reservations

    db, cir, _rh = _certified("parked")
    shas = [_owned_row(db, cir, seed)[1] for seed in (81, 82)]
    stub = StubVision(["match", "match"])
    job = _sweep(db, stub, "p1", floor=False)
    assert job.status is JobStatus.DONE, job.last_error
    assert {_states(db)[s] for s in shas} == {MB.PARKED}
    assert stub.calls == [] and _jobs(db, OP.ACTION) == [] and _jobs(db, "assets.build") == []
    assert reservations.outstanding(db)["cad"] == 0
    counts = MB.report(db)["counts"]
    assert (counts["renders_found_blocked"], counts["renders_parked_unusable_if_matched"],
            counts["renders_rechecked"], counts["renders_passed"]) == (2, 2, 0, 0), counts
    # The day a qualified producer gives these frames a structural floor, they are asked.
    _sweep(db, stub, "p2")
    assert {_states(db)[s] for s in shas} == {MB.PASSED} and len(stub.calls) == 2


def test_a_backlog_of_refused_renders_is_recovered_with_no_regeneration():
    from brambleloop.finance import reservations

    db, cir, _rh = _certified("backlog")
    ids = [_owned_row(db, cir, seed)[1] for seed in (11, 12)]
    refused = {"verdict": MF.UNMEASURABLE, "why": REFUSAL}
    _model_row(db, cir, (13, 14), motifs=(refused, refused))
    # A later sequence reused frame 13: one render, filed twice, is recovered once.
    _model_row(db, cir, (13,), motifs=(refused,))
    # Already judged: never picked up.
    _owned_row(db, cir, 15, motif={"verdict": MF.MISMATCH, "why": "checkerboard"})
    _owned_row(db, cir, 16, motif={"verdict": MF.UNMEASURABLE,
                                   "why": "the fabric could not be seen well enough"})
    stub = StubVision(["match"] * 4)
    job = _sweep(db, stub, "b1")
    assert job.status is JobStatus.DONE, job.last_error
    states = _states(db)
    assert len(states) == 4 and set(states.values()) == {MB.PASSED}, states
    assert len(stub.calls) == 4                          # one motif comparison per render
    assert all(len(c) == 2 for c in stub.calls)          # the paid bytes and the chart
    # No regeneration of any kind: no generator call (no_generation), no photography job.
    assert _jobs(db, OP.ACTION) == [] and _jobs(db, MP.ACTION) == []
    # Every reservation was taken and given back; the spend is on the ledger, at cost.
    assert reservations.outstanding(db)["cad"] == 0
    from brambleloop.core.models import CostEntry

    with db.session() as s:
        costs = [c for c in s.scalars(select(CostEntry)) if c.purpose == MF.TASK]
    assert len(costs) == 4 and all(c.agent == MF.AGENT for c in costs)
    rep = MB.report(db)["counts"]
    assert rep["renders_rechecked"] == 4 and rep["regenerations_queued"] == 0
    # Idempotent: a second sweep re-checks nothing and spends nothing.
    job = _sweep(db, stub, "b2")
    assert job.outputs["rechecked"] == 0 and job.outputs["new"] == 0 and len(stub.calls) == 4
    # The readers see the answer that superseded the refusal, and each render is charged once.
    with qualified():
        owned = OP.current_states(db, slug=cir.slug, version=cir.version)
        by_sha = {a["image"]["sha256"]: a for a in owned}
        assert all(by_sha[s]["motif_verified"] and by_sha[s]["usable_as_listing_asset"]
                   for s in ids)
        assert len(OP.ordinary_attempts(db, slug=cir.slug, version=cir.version)) == 4
        assert OP.usable_asset(db, slug=cir.slug, version=cir.version) is not None
        newest = MP.sequences(db, slug=cir.slug)[0]
        assert newest["motif_rejudge_only"] and newest["floors"]["product_truth"] == "pass"
        assert all(f["motif"]["verdict"] == MF.MATCH for f in newest["frames"])
        # Only the floors the fixture's detail frames cannot answer (no fit frame) stay open:
        # the re-ask closed product truth and opened nothing else.
        assert {k for k, v in newest["floors"].items() if v != "pass"} == {
            "face_identity", "whole_person_morphology", "styling"}, newest["floors"]
        assert not listing_asset.usable(newest)


# ---- 4. only a genuine failure is regenerated ----------------------------------------------

def test_only_a_render_that_genuinely_fails_is_queued_for_regeneration():
    db, cir, _rh = _certified("failing")
    _, good = _owned_row(db, cir, 21)
    _, bad = _owned_row(db, cir, 22)
    stub = StubVision(["mismatch", "match"])      # scanned newest row (22) first, then 21
    job = _sweep(db, stub, "f1")
    assert job.status is JobStatus.DONE, job.last_error
    assert _states(db) == {good: MB.PASSED, bad: MB.FAILED}, _states(db)
    regen = _jobs(db, OP.ACTION)
    assert regen == [{"slug": cir.slug, "reason": "motif_backlog_failed"}], regen
    with db.session() as s:
        rec = s.scalar(select(MB.MotifRecovery).where(MB.MotifRecovery.image_sha256 == bad))
        assert rec.regen_job_id is not None and rec.verdict == MF.MISMATCH
    # A re-sweep never queues it twice.
    _sweep(db, stub, "f2")
    assert len(_jobs(db, OP.ACTION)) == 1
    # The failed render is failed in every reader, and blocks structurally as before.
    from brambleloop.visual.product_authority import structural_floor

    failed = next(a for a in OP.current_states(db, slug=cir.slug, version=cir.version)
                  if a["image"]["sha256"] == bad)
    assert failed["usable_as_listing_asset"] is False
    assert structural_floor(failed)["status"] == "FAIL"


def test_a_judge_that_cannot_see_the_fabric_is_a_genuine_failure():
    db, cir, _rh = _certified("unseen")
    _, sha = _owned_row(db, cir, 23)
    stub = StubVision([])
    stub.see = lambda *a, **k: (stub.calls.append(a[2]),
                                _Resp(json.dumps({**OBSERVED["match"],
                                                  "fabric_readable": False})))[1]
    _sweep(db, stub, "u1")
    assert _states(db) == {sha: MB.FAILED} and len(_jobs(db, OP.ACTION)) == 1


def test_a_model_frame_that_fails_regenerates_through_the_model_path():
    db, cir, _rh = _certified("model-fail")
    refused = {"verdict": MF.UNMEASURABLE, "why": REFUSAL}
    _model_row(db, cir, (31,), motifs=(refused,))
    _sweep(db, StubVision(["mismatch"]), "m1")
    assert _jobs(db, MP.ACTION) == [{"slug": cir.slug, "reason": "motif_backlog_failed"}]
    assert _jobs(db, OP.ACTION) == []


def test_a_recheck_with_no_verdict_is_retried_then_unresolved_never_regenerated():
    db, cir, _rh = _certified("no-verdict")
    _, sha = _owned_row(db, cir, 41)
    rows_before = len(OP.assets_for(db, slug=cir.slug, version=cir.version))
    gone = A.ProviderUnusable("no ANTHROPIC_API_KEY in this environment")
    for n in range(MB.MAX_RECHECKS):
        _sweep(db, StubVision([gone]), f"n{n}")
        last = n == MB.MAX_RECHECKS - 1
        assert _states(db)[sha] == (MB.UNRESOLVED if last else MB.QUEUED_RETRY), (n, _states(db))
        # Nothing filed while it can still be asked; the last answer is filed once.
        assert len(OP.assets_for(db, slug=cir.slug, version=cir.version)) == \
            rows_before + (1 if last else 0)
    assert _jobs(db, OP.ACTION) == []
    stub = StubVision(["match"])
    _sweep(db, stub, "n-after")
    assert _states(db)[sha] == MB.UNRESOLVED and stub.calls == []


# ---- 5. budget exhaustion leaves renders queued -------------------------------------------

def test_budget_exhaustion_leaves_every_render_queued_and_nothing_regenerated():
    from brambleloop.gateway import providers

    db, cir, _rh = _certified("budget")
    shas = [_owned_row(db, cir, seed)[1] for seed in (51, 52)]
    rows_before = len(OP.assets_for(db, slug=cir.slug, version=cir.version))
    stub = StubVision(["match", "match"])

    def spent(*_a, **_k):
        raise A.AgentCeilingExceeded("quality_director's daily permission is spent")

    with patch.object(providers, "check_budget", spent):
        job = _sweep(db, stub, "x1")
    assert job.status is JobStatus.DONE, job.last_error
    assert {_states(db)[s] for s in shas} == {MB.QUEUED_BUDGET}
    assert stub.calls == [] and _jobs(db, OP.ACTION) == []
    assert len(OP.assets_for(db, slug=cir.slug, version=cir.version)) == rows_before
    assert MB.report(db)["counts"]["renders_still_queued_budget"] == 2
    # The gate itself refusing the re-ask is a refusal too: still queued, not regenerated.
    _sweep(db, StubVision([_gate_refusal(), _gate_refusal()]), "x2")
    assert {_states(db)[s] for s in shas} == {MB.QUEUED_BUDGET}
    with db.session() as s:
        assert {r.budget_deferrals for r in s.scalars(select(MB.MotifRecovery))} == {2}
    # Budget back: the same renders are recovered, never lost, never re-rendered.
    _sweep(db, stub, "x3")
    assert {_states(db)[s] for s in shas} == {MB.PASSED} and len(stub.calls) == 2
    assert _jobs(db, OP.ACTION) == []


def test_unreadable_bytes_are_reported_not_regenerated():
    db, cir, _rh = _certified("bytes")
    _, sha = _owned_row(db, cir, 61)
    os.remove(os.path.join(os.environ["BRAMBLELOOP_ARTIFACT_DIR"], sha[:2], sha))
    stub = StubVision(["match"])
    _sweep(db, stub, "y1")
    assert _states(db)[sha] == MB.BYTES_MISSING and stub.calls == []
    assert _jobs(db, OP.ACTION) == []


# ---- 6. end to end ------------------------------------------------------------------------

def _chain(db, cir, rh, *, stop_after_assets=False):
    """Run the release's own chain. With `stop_after_assets`, the chain is left stalled after
    `assets.build` (as an `assets.build` dead end leaves it in production)."""
    with no_generation():
        if not stop_after_assets:
            _drain(db)
            return
        for jt in ("gate.lanes", "listing.draft", "assets.build"):
            Worker(db, f"step-{jt}", phase=Phase.SHADOW, job_types=[jt],
                   lease_seconds=900).run_once()
    q = JobQueue(db)
    with db.session() as s:
        for j in s.scalars(select(Job).where(Job.status == JobStatus.PENDING)):
            j.status = JobStatus.DEAD          # the stall: nothing downstream is queued
            j.last_error = "test: chain stalled after assets.build"
    del q


def test_e2e_gates_are_unchanged_a_recovered_generated_render_completes_no_gallery():
    """The production truth, with every gate as it is: a refused render is found, and not
    re-asked -- a match could not make a generated frame usable (no structural PASS, F-852 /
    D-FB-7) -- so it completes no gallery, nothing is handed on, and the report says 0,
    measured, with the reason in its own count."""
    db, cir, rh = _certified("e2e-real")
    _chain(db, cir, rh)                       # the release's own disclosed-render gallery
    builds_before = len(_jobs(db, "assets.build"))
    _, sha = _owned_row(db, cir, 71)
    stub = StubVision(["match"])
    job = _sweep(db, stub, "r1", floor=False)
    assert job.status is JobStatus.DONE and _states(db) == {sha: MB.PARKED}
    assert stub.calls == []
    rec = OP.last_asset(db, slug=cir.slug)
    assert listing_asset.usable(rec) is False                 # structural floor unchanged
    # The release's gallery is complete -- from its disclosed renders, not from this render.
    assert MB.gallery_complete(db, cir.slug, cir.version)[0] is True
    assert sha not in MB.gallery_complete(db, cir.slug, cir.version)[2]
    assert len(_jobs(db, "assets.build")) == builds_before    # nothing handed on
    counts = MB.report(db)["counts"]
    assert (counts["renders_found_blocked"], counts["renders_parked_unusable_if_matched"],
            counts["renders_passed"], counts["products_gallery_completed"],
            counts["listing_packages_became_ready"]) == (1, 1, 0, 0, 0), counts


def test_e2e_a_recovered_render_the_gallery_accepts_advances_through_the_chain_unkicked():
    """Advancement, end to end on the real worker: with a LABELLED stand-in for the one thing
    no generated frame has today -- a structural PASS from a qualified producer -- the
    recovered render completes the gallery, and the sweep hands the release to `assets.build`,
    which carries it to `pricing.position` and `listing.seo` with no manual kick. There the
    F-852 policy classification refuses a generated finished-object image, exactly as before:
    the stand-in reaches no other gate."""
    from brambleloop.visual import product_authority as PA

    db, cir, rh = _certified("e2e-advance")
    with db.session() as s:
        s.add(Listing(product_slug=cir.slug, version=cir.version,
                      title="Cloudline Textured Baby Blanket | Crochet Pattern PDF",
                      description="A worsted-weight baby blanket pattern.",
                      tags=["baby blanket crochet"], price_cad=7.5, state="draft",
                      release_hash=rh))
    _, sha = _owned_row(db, cir, 72)
    real = PA.structural_floor

    def stand_in(frame):          # STAND-IN: a structural PASS for this one render only
        if isinstance(frame, dict) and MB._sha(frame) == sha:
            return {"status": "PASS", "why": "test stand-in for a qualified producer"}
        return real(frame)

    with patch.object(PA, "structural_floor", stand_in):
        job = _sweep(db, StubVision(["match"]), "a1", floor=False)
        assert job.outputs["advanced"] == 1, job.outputs
        with no_generation():
            _drain(db)
    builds = [i for i in _jobs(db, "assets.build")
              if str(i.get("rebuild", "")).startswith(MB.GALLERY_TOKEN)]
    assert len(builds) == 1 and builds[0]["release"] == rh, builds
    token = builds[0]["rebuild"]
    priced = [i for i in _jobs(db, "pricing.position") if i.get("rebuild") == token]
    seo = [i for i in _jobs(db, "listing.seo") if i.get("rebuild") == token]
    assert priced and seo, (priced, seo)
    with db.session() as s:
        done = [j for j in s.scalars(select(Job).where(Job.job_type == "listing.seo"))
                if (j.inputs or {}).get("rebuild") == token]
        assert done and done[0].status is JobStatus.DONE
        blocking = " ".join((done[0].outputs or {}).get("blocking") or [])
    assert done[0].outputs.get("ok") is False and "POLICY_CLASSIFICATION" in blocking
    assert not [i for i in _jobs(db, "launch.plan") if i.get("rebuild") == token]
    with db.session() as s:
        assert s.scalar(select(MB.MotifRecovery)).gallery_completed_at is not None
    # The handoff fired once for this gallery: a re-sweep queues nothing new.
    with patch.object(PA, "structural_floor", stand_in):
        _sweep(db, StubVision([]), "a2", floor=False)
    assert len([i for i in _jobs(db, "assets.build")
                if str(i.get("rebuild", "")).startswith(MB.GALLERY_TOKEN)]) == 1


def test_e2e_a_completed_gallery_hands_a_stalled_release_on_to_listing_package():
    """No stand-ins. A release stalled after `assets.build`, whose gallery the unchanged
    readers accept (its verified disclosed renders): the handoff alone carries it through
    pricing.position -> listing.seo -> launch.plan -> listing.package, and the package is
    assembled. In SHADOW with no physical sample it is BLOCKED on the owner's physical-sample,
    Etsy and SAMPLE_PHOTO_REQUIRED gates -- and on no image or gallery gate."""
    db, cir, rh = _certified("e2e-package")
    _chain(db, cir, rh, stop_after_assets=True)
    assert not [j for j in _jobs(db, "listing.package")]
    done, _ident, _shas = MB.gallery_complete(db, cir.slug, cir.version)
    assert done

    def enqueue(agent, job_type, inputs, **kw):
        return JobQueue(db).enqueue(agent, job_type, inputs, **kw)

    hand = MB.gallery_handoff(enqueue, db, cir.slug, cir.version)
    assert hand["advanced"] and hand["queued"], hand
    with no_generation():
        _drain(db)
    with db.session() as s:
        pkg_jobs = [j for j in s.scalars(select(Job).where(Job.job_type == "listing.package"))
                    if (j.inputs or {}).get("slug") == cir.slug]
        assert pkg_jobs and pkg_jobs[-1].status is JobStatus.DONE, pkg_jobs
        row = s.scalar(select(OperatingReading).where(
            OperatingReading.kind == LP.KIND,
            OperatingReading.period_key == f"{cir.slug}@{cir.version}"))
        assert row is not None
        payload = dict(row.payload)
    assert payload["state"] in (LP.READY, LP.BLOCKED)
    blockers = payload.get("blockers") or []
    # D-OWNER-GALLERY-COMPLETE (merged with b17-c A4): this fixture's photography set
    # certifies fewer than CAMPAIGN_MIN_FRAMES frames, so the package correctly names the
    # gallery as incomplete -- an image blocker, tagged as one. Every other image gate the
    # handoff exists to clear must be gone.
    from brambleloop.visual.shot_plans import CAMPAIGN_MIN_FRAMES

    incomplete = [b for b in blockers if b.get("source") == "certified_frames"
                  and str(b.get("why", "")).startswith("gallery incomplete")]
    assert all(b.get("image") is True for b in incomplete), incomplete
    assert all(f"of the {CAMPAIGN_MIN_FRAMES} required" in b["why"] for b in incomplete)
    why = " ".join(b.get("why", "") for b in blockers if b not in incomplete)
    for image_gate in ("POLICY_CLASSIFICATION", "GALLERY", "ASSET_", "listing images"):
        assert image_gate not in why, (image_gate, why[:400])
    # A second handoff of the same gallery is the same job (idempotent).
    again = MB.gallery_handoff(enqueue, db, cir.slug, cir.version)
    assert again["token"] == hand["token"]


def test_the_photography_handlers_hand_a_usable_gallery_on():
    """The missing handoff, fixed at its producers: a photography job that files a usable
    record enqueues the release's `assets.build`; an unusable one enqueues nothing."""
    from brambleloop.runtime import release as R

    class Ctx:
        def __init__(self, db):
            self.db, self.queued = db, []

        def enqueue(self, agent, job_type, inputs, **kw):
            self.queued.append((agent, job_type, dict(inputs), kw.get("idempotency_key")))
            return None

    db, cir, rh = _certified("handler-handoff")
    ctx = Ctx(db)
    assert R._gallery_handoff(ctx, cir.slug, cir.version, {"made": True,
                                                           "usable_as_listing_asset": False}) \
        is None and ctx.queued == []
    with patch.object(MB, "gallery_complete", lambda *_a: (True, "abc123abc123", frozenset())):
        out = R._gallery_handoff(ctx, cir.slug, cir.version,
                                 {"made": True, "usable_as_listing_asset": True})
    assert out["advanced"] and ctx.queued[0][:2] == ("publishing", "assets.build")
    assert ctx.queued[0][2] == {"slug": cir.slug, "version": cir.version, "release": rh,
                                "rebuild": MB.GALLERY_TOKEN + "abc123abc123"}
    assert ctx.queued[0][3] == R.chain_key("assets", cir.slug, cir.version, rh,
                                           MB.GALLERY_TOKEN + "abc123abc123")
    # A gallery the existing reader does not accept is never handed on.
    with patch.object(MB, "gallery_complete", lambda *_a: (False, "", frozenset())):
        assert not R._gallery_handoff(ctx, cir.slug, cir.version,
                                      {"made": True, "usable_as_listing_asset": True})["advanced"]
    assert len(ctx.queued) == 1


# ---- 7. the report ------------------------------------------------------------------------

def _audit(db):
    def write(action, **kw):
        with db.session() as s:
            s.add(AuditLog(actor="publishing", action=action, artifact=kw.get("artifact"),
                           detail=kw.get("detail") or {}))
    return write


def _rec(s, n, state, *, slug="alpha-blanket", version="1.0.0", rechecks=1, regen=None,
         gallery=None, package=None):
    s.add(MB.MotifRecovery(render_key=f"k-{slug}-{n}", source_action=OP.ACTION, audit_id=n,
                           slug=slug, version=version, image_sha256=f"{n:064x}",
                           refusal_code="no_budget_reservation", state=state,
                           rechecks=rechecks, regen_job_id=regen,
                           gallery_completed_at=gallery, package_ready_at=package))


def test_the_report_counts_are_exact_and_unknown_is_never_zero():
    db = _db("report")
    rep = MB.report(db)
    assert rep["swept"] is False and set(rep["counts"].values()) == {MB.UNKNOWN}
    t0 = datetime(2026, 11, 1, tzinfo=timezone.utc)
    MB.ensure_tables(db)
    with db.session() as s:
        s.add(AuditLog(actor="publishing", action=MB.AUDIT_SWEPT, detail={}))
        _rec(s, 1, MB.PASSED, gallery=t0, package=t0 + timedelta(hours=2))
        _rec(s, 2, MB.PASSED, gallery=t0)                    # same product: counted once
        _rec(s, 3, MB.PASSED, slug="beta-hat")
        _rec(s, 4, MB.FAILED, slug="beta-hat", regen=99)
        _rec(s, 5, MB.FAILED, slug="gamma-cowl", regen=100)
        _rec(s, 6, MB.QUEUED_BUDGET, slug="gamma-cowl")
        _rec(s, 7, MB.QUEUED_BUDGET, slug="delta-shawl", rechecks=0)
        _rec(s, 8, MB.BLOCKED, slug="delta-shawl", rechecks=0)
        _rec(s, 9, MB.QUEUED_RETRY, slug="delta-shawl")
        _rec(s, 10, MB.UNRESOLVED, slug="delta-shawl", rechecks=3)
        _rec(s, 11, MB.BYTES_MISSING, slug="eps-wrap", rechecks=0)
        _rec(s, 12, MB.SUPERSEDED, slug="eps-wrap", version="0.9.0", rechecks=0)
        _rec(s, 13, MB.PASSED, slug="zeta-bag", gallery=t0)
        _rec(s, 14, MB.PARKED, slug="zeta-bag", rechecks=0)
        _rec(s, 15, MB.INELIGIBLE, slug="zeta-bag", rechecks=0)   # never a pass
    counts = MB.report(db)["counts"]
    assert counts == {
        "renders_found_blocked": 15, "renders_rechecked": 9, "renders_passed": 4,
        "renders_failed": 2, "renders_still_queued_budget": 2, "renders_queued_retry": 1,
        "renders_parked_unusable_if_matched": 1,
        "renders_unresolved": 1, "renders_awaiting_first_recheck": 1,
        "renders_bytes_missing": 1, "renders_superseded": 1,
        "renders_ineligible_on_merits": 1, "regenerations_queued": 2,
        "products_blocked": 7, "products_gallery_completed": 2,
        "listing_packages_became_ready": 1}, counts
    assert set(counts) == set(MB.COUNT_NAMES)
    # Unreadable: UNKNOWN, never 0.
    with patch.object(MB, "select", side_effect=RuntimeError("down")):
        bad = MB.report(db)
    assert bad["readable"] is False and set(bad["counts"].values()) == {MB.UNKNOWN}


def test_a_package_counts_as_ready_only_when_ready_after_the_gallery_completed():
    db, cir, _rh = _certified("pkg-ready")
    t0 = datetime.now(timezone.utc) - timedelta(hours=3)
    MB.ensure_tables(db)

    def reading(state, at):
        with db.session() as s:
            row = s.scalar(select(OperatingReading).where(
                OperatingReading.kind == LP.KIND,
                OperatingReading.period_key == f"{cir.slug}@{cir.version}"))
            payload = {"state": state, "assembled_at": at.isoformat()}
            if row is None:
                s.add(OperatingReading(kind=LP.KIND, period_key=f"{cir.slug}@{cir.version}",
                                       payload=payload))
            else:
                row.payload = payload

    with db.session() as s:
        _rec(s, 1, MB.PASSED, slug=cir.slug, version=cir.version, gallery=t0)
    reading(LP.READY, t0 - timedelta(hours=1))           # ready BEFORE: not this recovery's
    MB.sweep(db, lambda *a, **k: None, audit=_audit(db))
    reading(LP.BLOCKED, t0 + timedelta(hours=1))
    MB.sweep(db, lambda *a, **k: None, audit=_audit(db))
    with db.session() as s:
        assert s.scalar(select(MB.MotifRecovery)).package_ready_at is None
    reading(LP.READY, t0 + timedelta(hours=2))
    MB.sweep(db, lambda *a, **k: None, audit=_audit(db))
    with db.session() as s:
        assert s.scalar(select(MB.MotifRecovery)).package_ready_at is not None
    assert MB.report(db)["counts"]["listing_packages_became_ready"] == 1


def test_the_report_is_on_the_p0_board_and_the_readback_evidence():
    import importlib

    from brambleloop.app.command_center import p0_board as B
    from brambleloop.ops import production_evidence as pe

    sys.path.insert(0, str(ROOT.parent / "ops"))
    readback = importlib.import_module("readback")
    db = _db("surfaces")
    now = datetime.now(timezone.utc)
    sec = B.view(db, now=now)["sections"]["motif_recovery"]
    assert sec["state"] == B.UNKNOWN and set(sec["counts"].values()) == {MB.UNKNOWN}
    ev = pe.SECTIONS["motif_backlog_recovery"](db, now=now)
    assert ev["readable"] and ev["swept"] is False
    assert readback._judge_section("motif_backlog_recovery", ev, None)[0] == readback.WARN
    assert ("paid renders recovered from refused motif checks", "motif_backlog_recovery",
            None) in readback.EVIDENCE_ITEMS
    MB.ensure_tables(db)
    with db.session() as s:
        s.add(AuditLog(actor="publishing", action=MB.AUDIT_SWEPT, detail={}))
        _rec(s, 1, MB.PASSED)
        _rec(s, 2, MB.QUEUED_BUDGET)
    sec = B.view(db, now=now)["sections"]["motif_recovery"]
    assert sec["state"] == "RECOVERING" and sec["counts"]["renders_passed"] == 1
    ev = pe.SECTIONS["motif_backlog_recovery"](db, now=now)
    assert ev["counts"]["renders_still_queued_budget"] == 1
    assert readback._judge_section("motif_backlog_recovery", ev, None)[0] == readback.WARN
    with db.session() as s:
        s.scalar(select(MB.MotifRecovery).where(
            MB.MotifRecovery.state == MB.QUEUED_BUDGET)).state = MB.PASSED
    sec = B.view(db, now=now)["sections"]["motif_recovery"]
    assert sec["state"] == "RECOVERED"
    ev = pe.SECTIONS["motif_backlog_recovery"](db, now=now)
    assert readback._judge_section("motif_backlog_recovery", ev, None)[0] == readback.PASS
    assert readback._judge_section("motif_backlog_recovery", {"readable": False}, None)[0] \
        == readback.WARN
    # Read-only: the board and the evidence wrote nothing.
    with db.session() as s:
        assert len(list(s.scalars(select(MB.MotifRecovery)))) == 2


def test_a_gallery_completed_by_other_frames_is_not_counted_as_recovered():
    """A recovered render whose release's gallery is complete from OTHER frames (its verified
    disclosed renders) did not complete that gallery: no handoff, no count."""
    db, cir, rh = _certified("other-frames")
    _chain(db, cir, rh)
    builds_before = len(_jobs(db, "assets.build"))
    # A model detail frame, recovered by a match under the stand-in floor scoped to it; its
    # sequence has no fit frame, so it is not the listing gallery, which was already
    # complete from other frames. (This was an asset-truth-`blocked` owned render before
    # ENG-MOTIF-BACKLOG-FIX; a blocked render is now INELIGIBLE on its merits and never
    # re-asked, so it cannot reach PASSED.)
    _model_row(db, cir, (91,), motifs=({"verdict": MF.UNMEASURABLE, "why": REFUSAL},))
    sha = _png(91)
    from brambleloop.visual import product_authority as PA

    real = PA.structural_floor

    def scoped(frame):            # STAND-IN for this one render only; every other frame real
        if isinstance(frame, dict) and MB._sha(frame) == sha:
            return _qualified_floor(frame)
        return real(frame)

    with patch.object(PA, "structural_floor", scoped):
        _sweep(db, StubVision(["match"]), "o1", floor=False)
        assert _states(db) == {sha: MB.PASSED}
        done, _ident, shas = MB.gallery_complete(db, cir.slug, cir.version)
    assert done and sha not in shas
    assert len(_jobs(db, "assets.build")) == builds_before
    assert MB.report(db)["counts"]["products_gallery_completed"] == 0


def test_a_gallery_the_existing_reader_rejects_is_never_complete_or_handed_on():
    """Real gates: a release whose only listing record is a generated render (motif matched,
    asset truth clear) has no complete gallery -- the structural floor says UNKNOWN -- so the
    handoff enqueues nothing."""
    db, cir, _rh = _certified("unusable")
    _owned_row(db, cir, 93, motif={"verdict": MF.MATCH, "why": "matched"})
    record = listing_asset.last(db, slug=cir.slug)
    assert record and record.get("usable_as_listing_asset") is True
    assert listing_asset.usable(record) is False
    assert MB.gallery_complete(db, cir.slug, cir.version) == (False, "", frozenset())
    queued = []
    out = MB.gallery_handoff(lambda *a, **k: queued.append(a), db, cir.slug, cir.version)
    assert out["advanced"] is False and queued == []


# ---- ENG-MOTIF-BACKLOG-FIX: the per-sweep bound, the daily cap, no double charge, merits ------

class Crash(BaseException):
    """A process death: not an Exception, so nothing in the call path swallows it."""


def _direct_sweep(db, stub, *, limit=MB.SWEEP_LIMIT, now=None, floor=True):
    with no_generation(), vision(stub):
        if not floor:
            return MB.sweep(db, JobQueue(db).enqueue, limit=limit, now=now)
        with qualified():
            return MB.sweep(db, JobQueue(db).enqueue, limit=limit, now=now)


def _row(db, sha):
    with db.session() as s:
        r = s.scalar(select(MB.MotifRecovery).where(MB.MotifRecovery.image_sha256 == sha))
        s.expunge(r)
        return r


def test_limit_n_means_at_most_n_paid_reasks_across_every_row_state():
    """The probe the review ran: parked rows became worth asking and each bought a call
    outside the 50-row bound. One bound now covers every state."""
    db, cir, _rh = _certified("tick-bound")
    parked = [_owned_row(db, cir, seed)[1] for seed in (101, 102, 103)]
    _direct_sweep(db, StubVision([]), floor=False)
    assert {_states(db)[s] for s in parked} == {MB.PARKED}
    blocked = _owned_row(db, cir, 104)[1]            # a BLOCKED row alongside the parked ones
    stub = StubVision(["match"] * 8)
    out = _direct_sweep(db, stub, limit=1)
    assert len(stub.calls) == 1 and out["paid_reasks"] == 1, (stub.calls, out)
    assert list(_states(db).values()).count(MB.PASSED) == 1
    out = _direct_sweep(db, stub, limit=2)
    assert len(stub.calls) == 3 and out["paid_reasks"] == 2
    out = _direct_sweep(db, stub, limit=0)
    assert len(stub.calls) == 3 and out["paid_reasks"] == 0
    _direct_sweep(db, stub, limit=5)
    assert len(stub.calls) == 4
    assert {_states(db)[s] for s in parked + [blocked]} == {MB.PASSED}


def test_the_daily_cap_is_durable_and_only_lowered_by_the_environment():
    db, cir, _rh = _certified("daily-cap")
    shas = [_owned_row(db, cir, seed)[1] for seed in (111, 112, 113, 114, 115)]
    day1 = datetime(2026, 11, 19, 9, tzinfo=timezone.utc)
    stub = StubVision(["match"] * 10)
    with patch.dict(os.environ, {MB.DAILY_CAP_ENV: "2"}):
        assert MB.daily_cap() == 2
        _direct_sweep(db, stub, now=day1)
        assert len(stub.calls) == 2
        # Later the same day: the durable count says the day is spent, whatever the sweep.
        _direct_sweep(db, stub, now=day1 + timedelta(hours=6))
        assert len(stub.calls) == 2 and MB.claimed_today(db, now=day1) == 2
        # A direct re-check outside the sweep is held by the same cap.
        waiting = next(s for s in shas if _states(db)[s] != MB.PASSED)
        with no_generation(), vision(stub), qualified():
            out = MB.recheck_one(db, _row(db, waiting).id, now=day1 + timedelta(hours=7))
        assert out.get("deferred") == "daily_cap" and len(stub.calls) == 2
        _direct_sweep(db, stub, now=day1 + timedelta(days=1))
        assert len(stub.calls) == 4
    # Configurable only downward.
    for raw in ("1000", "41", "-1", "abc", ""):
        with patch.dict(os.environ, {MB.DAILY_CAP_ENV: raw}):
            assert MB.daily_cap() == MB.DAILY_CAP == 40, raw
    with patch.dict(os.environ, {MB.DAILY_CAP_ENV: "0"}):
        _direct_sweep(db, stub, now=day1 + timedelta(days=2))
        assert len(stub.calls) == 4


def test_an_answer_the_photography_job_filed_first_is_reused_not_paid_again():
    db, cir, _rh = _certified("answered-first")
    _, sha = _owned_row(db, cir, 121)
    MB.scan(db)
    # ENG-MOTIF's own re-ask in the photography job answers first: a new row, same image.
    answered_id, same = _owned_row(db, cir, 121, motif={"verdict": MF.MATCH,
                                                        "why": "the lattice matches"})
    assert same == sha
    stub = StubVision(["match"])
    out = _direct_sweep(db, stub)
    assert stub.calls == [] and out["paid_reasks"] == 0
    rec = _row(db, sha)
    assert rec.state == MB.PASSED and rec.recovered_audit_id == answered_id and rec.rechecks == 0
    assert MB.claimed_today(db) == 0


def test_a_crash_between_filing_and_settling_is_not_charged_twice():
    db, cir, _rh = _certified("crash-filed")
    _, sha = _owned_row(db, cir, 131)
    rows_before = len(OP.assets_for(db, slug=cir.slug, version=cir.version))
    real = MB._file_answer

    def file_then_die(*a, **k):
        real(*a, **k)
        raise Crash("killed after filing, before settling")

    stub = StubVision(["match", "match"])
    with patch.object(MB, "_file_answer", file_then_die):
        try:
            _direct_sweep(db, stub)
            raise AssertionError("the crash did not happen")
        except Crash:
            pass
    assert len(stub.calls) == 1 and _row(db, sha).rechecks == 1
    _direct_sweep(db, stub)
    assert len(stub.calls) == 1, "the answer already on file was paid for again"
    assert _row(db, sha).state == MB.PASSED
    assert len(OP.assets_for(db, slug=cir.slug, version=cir.version)) == rows_before + 1


def test_a_crash_during_the_paid_call_counts_as_a_claimed_attempt():
    db, cir, _rh = _certified("crash-call")
    _, sha = _owned_row(db, cir, 141)
    for n in range(MB.MAX_RECHECKS):
        stub = StubVision([Crash("killed mid-call")])
        try:
            _direct_sweep(db, stub)
            raise AssertionError("the crash did not happen")
        except Crash:
            pass
        assert len(stub.calls) == 1
        # Claimed BEFORE the call, in the claim's transaction: the attempt is counted.
        assert _row(db, sha).rechecks == n + 1 and MB.claimed_today(db) == n + 1
    stub = StubVision(["match"])
    _direct_sweep(db, stub)
    assert stub.calls == [] and _row(db, sha).state == MB.UNRESOLVED
    assert _jobs(db, OP.ACTION) == []


def test_a_render_ineligible_on_its_merits_is_never_reasked_or_passed():
    db, cir, _rh = _certified("merits")
    _, blocked = _owned_row(db, cir, 151, verdict="blocked")   # asset truth did not clear
    refused = {"verdict": MF.UNMEASURABLE, "why": REFUSAL}
    _model_row(db, cir, (152,), motifs=(refused,), floors_override={"styling": "fail"})
    _model_row(db, cir, (153,), motifs=(refused,), floors_override={"photographic_realism": "unverifiable"})
    stub = StubVision(["match"] * 3)
    _direct_sweep(db, stub)
    assert stub.calls == [], stub.calls
    assert set(_states(db).values()) == {MB.INELIGIBLE}, _states(db)
    _sweep(db, stub, "merits-job")
    counts = MB.report(db)["counts"]
    assert counts["renders_passed"] == 0 and counts["renders_ineligible_on_merits"] == 3
    assert _jobs(db, OP.ACTION) == [] and _jobs(db, MP.ACTION) == []


def test_a_match_that_leaves_the_render_unusable_is_not_counted_passed():
    """renders_passed counts renders that became USABLE, not every match: a detail frame
    carrying a floor it cannot answer is still unusable after a matching motif."""
    db, cir, _rh = _certified("match-unusable")
    refused = {"verdict": MF.UNMEASURABLE, "why": REFUSAL}
    _model_row(db, cir, (161,), motifs=(refused,),
               floors_override={"face_identity": "unverifiable"})
    stub = StubVision(["match"])
    _direct_sweep(db, stub)
    assert len(stub.calls) == 1
    (state,) = _states(db).values()
    assert state == MB.INELIGIBLE, state
    _sweep(db, stub, "match-unusable-job")
    counts = MB.report(db)["counts"]
    assert counts["renders_passed"] == 0 and counts["renders_ineligible_on_merits"] == 1
    assert len(stub.calls) == 1 and _jobs(db, "assets.build") == []


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            if sys.argv[1:] and not any(a in name for a in sys.argv[1:]):
                continue
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                fails += 1
                print("FAIL", name, repr(e))
                traceback.print_exc()
    print(f"{fails} failed")
    sys.exit(1 if fails else 0)
