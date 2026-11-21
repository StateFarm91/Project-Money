"""NEW-PRODUCT-FLOW: with Launch-0 exhausted, a new research product reaches certified unaided.

Production readback on prod 2f7da291 failed two checks:
* "products progressing through certification": 0 certified in 7 days; 9 Launch-0 products at
  LISTING_READY and every other lifecycle stage empty;
* "autonomous company loop": 11/12 stages, none in `original_product` (no useful `cir.draft`,
  `cir.compile` or `gate.certify` in 7 days).

This suite reproduces that state on a scratch SQLite file and runs the real handlers through
the real worker:

* the Launch-0 release registry is exhausted (every release seeded before, as production's
  `catalogue-exhausted:launch0` incident says);
* a research concept is approved by `radar.concept_intake` and scored by `radar.score`;
* the owner has activated paid vision and a vision probe succeeded (the `image_vision` gate is
  open, as D-OWNER-APPROVE-ALL intends), with a FIXTURE vision provider standing in for the
  model -- no real call is made.

Then only the scheduler's own cadence jobs are enqueued (`radar.concept_intake`,
`mjs.seasonal_sentinel`, `supply.admit`), and the worker drains whatever they cause. Nothing
in this file writes a judgement, stubs `judgement_for`, or enqueues a chain job.

Root cause pinned here: the pre-engineering gate leaves every new research concept WAITING on
`image_vision` (#88 thumbnail at grid size, #83 craft impression). The vision judge
(`creative.intake.judge_held`) was only ever asked about `creative.winner_intake` rows
(tournament winners and engineered moment candidates). A radar concept had no board on file
and was never presented to the judge, so `radar.intake.rescore_judged` never found a
judgement and the concept waited forever, even with vision open.

Every gate stays: a concept judged not to read at grid size is refused and never drafted;
with vision closed nothing is judged and the concept waits with its reason; children's
products and engine holds are untouched (their suites are unchanged).

Every research source, finding, listing and judgement here is a TEST FIXTURE.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_new_product_flow.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("BRAMBLELOOP_PHASE", "shadow")


def _refuse(*_a, **_k):
    raise OSError("network refused: this test makes no outbound connection")


socket.socket.connect = _refuse  # type: ignore[assignment]
socket.create_connection = _refuse  # type: ignore[assignment]

import test_eng_families as EF  # noqa: E402 - the ENG-FAMILIES research-concept harness

from sqlalchemy import select  # noqa: E402

from brambleloop.core.models import (  # noqa: E402
    AuditLog, Job, JobStatus, PatternVersion, Product,
)
from brambleloop.creative import intake as creative_intake  # noqa: E402
from brambleloop.gateway import providers as gw  # noqa: E402
from brambleloop.gateway import routing  # noqa: E402
from brambleloop.gateway import anthropic as vision_probe  # noqa: E402 - the probe record
from brambleloop.gateway.model_gateway import ModelResponse  # noqa: E402
from brambleloop.gates.certificate import DOC_VERSION  # noqa: E402
from brambleloop.products import lifecycle  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.radar import intake  # noqa: E402
from brambleloop.runtime import release_recovery as RR  # noqa: E402
from brambleloop.runtime.worker import Worker  # noqa: E402

CONCEPT = EF.BASKET
SLUG = CONCEPT["slug"]
# The scheduler's cadences that move a research concept (runtime.worker.CADENCES).
CADENCE_JOBS = (("market_radar", "radar.concept_intake"),
                ("market_radar", "mjs.seasonal_sentinel"),
                ("orchestrator", "supply.admit"))
CYCLES = 3
MAX_JOBS_PER_CYCLE = 60


def _exhaust_launch0(db) -> None:
    """Production state: every Launch-0 release was seeded before (its `launch0-seed:` key is
    taken), so `seed_launch0` has nothing left and reports the catalogue exhausted."""
    with db.session() as s:
        for cir in RR.launch0_releases():
            s.add(Job(agent="crochet_engineer", job_type="cir.draft", inputs={"slug": cir.slug},
                      outputs={"drafted": True, "fixture": "earlier Launch-0 seed"},
                      status=JobStatus.DONE,
                      idempotency_key=RR.seed_key(cir.slug, cir.version, cir.fingerprint,
                                                  DOC_VERSION)))


def _open_vision(db) -> None:
    """The owner's activation of paid vision plus a successful probe under it (V0)."""
    import _paid_activation as paid

    from brambleloop.gateway import paid_provider_gate as G

    acts = paid.activate(db, G.ANTHROPIC_VISION)
    probe = next(a for a in acts if a["scope"] == G.PROBE)
    with db.session() as s:
        s.add(AuditLog(actor="ops", action=vision_probe.VISION_PROBE_ACTION,
                       detail={"ok": True, "activation_id": probe["id"]}))
    assert gw.vision_usable(db)


class _Judge:
    """FIXTURE vision provider for the concept-board judge only; never a real call."""

    def __init__(self, answer: str):
        self.model = routing.route(creative_intake.JUDGE_TASK)[1].model
        self.cost_per_1k_input_cad = 0.0
        self.cost_per_1k_output_cad = 0.0
        self.answer = answer
        self.calls: list[list[str]] = []

    def see(self, system, prompt, urls, *, max_tokens):
        self.calls.append(list(urls))
        return ModelResponse(text=self.answer, provider="fixture", model=self.model,
                             input_tokens=10, output_tokens=5, latency_ms=1.0)


def _with_judge(judge):
    real = gw.provider_for

    def provider_for(task, **kw):
        return judge if task == creative_intake.JUDGE_TASK else real(task, **kw)
    gw.provider_for = provider_for
    return lambda: setattr(gw, "provider_for", real)


def _production_state(*, vision: bool):
    db = EF._db()
    _exhaust_launch0(db)
    EF._benchmarks(db, CONCEPT["concept"]["pod"])
    tid = EF._answered_task(db)
    intake.attach_proposal(db, tid, CONCEPT)
    if vision:
        _open_vision(db)
    return db


def _drain(db, *, cycles: int = CYCLES) -> list[dict]:
    """The scheduler's cadences, once per cycle, and everything they cause."""
    ran = []
    for c in range(cycles):
        q = JobQueue(db)
        for agent, job_type in CADENCE_JOBS:
            q.enqueue(agent, job_type, {"cadence": f"fixture-{c}"},
                      idempotency_key=f"fixture-cadence:{job_type}:{c}", priority=0)
        w = Worker(db, f"npf-{c}")
        for _ in range(MAX_JOBS_PER_CYCLE):
            if not w.run_once():
                break
        with db.session() as s:
            ran = [{"id": j.id, "type": j.job_type, "status": j.status.value,
                    "error": (j.last_error or "")[:200]}
                   for j in s.scalars(select(Job).order_by(Job.id))]
    return ran


def _certified(db, slug: str) -> list[PatternVersion]:
    with db.session() as s:
        return list(s.scalars(select(PatternVersion).join(
            Product, Product.id == PatternVersion.product_id).where(
            Product.slug == slug, PatternVersion.certified.is_(True))))


def _rows(db, action: str, artifact: str | None = None):
    with db.session() as s:
        q = select(AuditLog).where(AuditLog.action == action)
        if artifact is not None:
            q = q.where(AuditLog.artifact == artifact)
        return [(r.id, r.artifact, dict(r.detail or {})) for r in s.scalars(q.order_by(AuditLog.id))]


def _jobs(db, job_type: str):
    with db.session() as s:
        return list(s.scalars(select(Job).where(Job.job_type == job_type).order_by(Job.id)))


# ---- the production state --------------------------------------------------------------------

def test_the_simulated_state_is_productions():
    """Launch-0 exhausted; the research concept approved and scored, WAITING on image_vision."""
    db = _production_state(vision=False)
    from types import SimpleNamespace

    ctx = SimpleNamespace(db=db, enqueue=JobQueue(db).enqueue,
                          audit=lambda *a, **k: None)
    seeded = RR.seed_launch0(ctx)
    assert seeded["exhausted"] is True and not seeded["seeded"], seeded
    _drain(db, cycles=1)
    scored = [j for j in _jobs(db, "radar.score") if j.status == JobStatus.DONE]
    assert scored, "the approved research concept was scored"
    out = scored[-1].outputs
    assert out["slug"] == SLUG and out["promoted"] is False, out
    assert out["gate"]["waiting_on"] == ["image_vision"], out["gate"]
    assert not _jobs(db, "cir.draft")[len(RR.launch0_releases()):], "nothing new drafted"


# ---- the defect and its fix ------------------------------------------------------------------

def test_with_vision_open_a_new_research_product_reaches_certified_unaided():
    db = _production_state(vision=True)
    judge = _Judge('{"thumbnail_reads_small": true, "craft_impression": 4.3}')
    restore = _with_judge(judge)
    try:
        ran = _drain(db)
    finally:
        restore()
    # The judge looked at exactly one board: this concept's, bound to its bytes.
    judged = _rows(db, creative_intake.JUDGED_ACTION, SLUG)
    assert len(judge.calls) == 1 and judged, (judge.calls, [r for r in ran
                                                           if r["status"] != "done"])
    assert judged[-1][2]["judge"] == judge.model
    assert judged[-1][2]["board_sha256"] == creative_intake.board_digest_for(db, SLUG)
    # ... then the ordinary chain: draft -> compile -> certify, every gate run.
    drafts = [j for j in _jobs(db, "cir.draft") if (j.inputs or {}).get("slug") == SLUG]
    assert len(drafts) == 1 and drafts[0].idempotency_key == f"draft:{SLUG}", drafts
    assert drafts[0].status == JobStatus.DONE and drafts[0].outputs.get("drafted"), \
        drafts[0].outputs
    versions = _certified(db, SLUG)
    assert versions, [r for r in ran if r["type"] in ("cir.compile", "gate.certify")]
    cert = dict(versions[0].certificate or {})
    assert cert.get("granted") is True and cert.get("release_hash"), cert
    for stage in ("compile", "twin", "reverse"):
        assert stage in cert["stages_run"], (stage, cert["stages_run"])
    assert _rows(db, "gate.certified", f"{SLUG}@{versions[0].version}")
    # The lifecycle board the readback reads moves past LISTING_READY-only.
    assert lifecycle.derive(db, SLUG)["stage"] not in ("DISCOVERED", "RESEARCHING",
                                                       "SELECTED", "PATTERN"), \
        lifecycle.derive(db, SLUG)
    # Entered by the one door: an admitted supply offer.
    assert [d for _i, _a, d in _rows(db, "supply.admitted", SLUG)
            if d.get("key") == f"draft:{SLUG}"]
    # The judge is asked once; later cycles reuse the recorded judgement.
    assert len(judge.calls) == 1


# ---- every gate stays ------------------------------------------------------------------------

def test_a_concept_judged_not_to_read_at_grid_size_is_refused_and_never_drafted():
    db = _production_state(vision=True)
    judge = _Judge('{"thumbnail_reads_small": false, "craft_impression": 4.3}')
    restore = _with_judge(judge)
    try:
        _drain(db)
    finally:
        restore()
    assert len(judge.calls) == 1, judge.calls
    assert not [j for j in _jobs(db, "cir.draft") if (j.inputs or {}).get("slug") == SLUG]
    assert not _certified(db, SLUG)
    refused = [j.outputs for j in _jobs(db, "radar.score")
               if (j.outputs or {}).get("gate") and j.outputs["gate"]["decision"] == "refused"]
    assert refused and "premise_thumbnail" in refused[-1]["gate"]["failed"], refused


def test_with_vision_closed_nothing_is_judged_and_the_concept_waits_with_its_reason():
    db = _production_state(vision=False)
    judge = _Judge('{"thumbnail_reads_small": true, "craft_impression": 4.3}')
    restore = _with_judge(judge)
    try:
        _drain(db, cycles=2)
    finally:
        restore()
    assert judge.calls == [], "no vision call while the image_vision gate is closed"
    assert not _rows(db, creative_intake.JUDGED_ACTION, SLUG)
    assert not [j for j in _jobs(db, "cir.draft") if (j.inputs or {}).get("slug") == SLUG]
    held = [h for j in _jobs(db, "mjs.seasonal_sentinel") if j.status == JobStatus.DONE
            for h in ((j.outputs or {}).get("regated") or {}).get("radar_held") or []
            if h["slug"] == SLUG]
    assert held and any("vision_model" in w for w in held[-1]["waiting_on"]), held


def test_a_judgement_is_never_carried_onto_a_board_nobody_looked_at():
    """CB2-D01 holds for radar boards: the judgement is bound to the filed board's bytes, and
    a re-rendered board voids it."""
    db = _production_state(vision=True)
    judge = _Judge('{"thumbnail_reads_small": true, "craft_impression": 4.3}')
    restore = _with_judge(judge)
    try:
        q = JobQueue(db)
        for agent, job_type in CADENCE_JOBS[:2]:
            q.enqueue(agent, job_type, {"cadence": "fixture"}, priority=0,
                      idempotency_key=f"fixture-cadence:{job_type}")
        # intake and its score, then the judge's cadence -- nothing downstream yet
        for types in (["radar.concept_intake"], ["radar.score"], ["mjs.seasonal_sentinel"]):
            assert Worker(db, "npf-bind", job_types=types).run_once(), types
    finally:
        restore()
    from brambleloop.products import moment_candidates as mc

    board = mc.board_record(db, SLUG)
    assert board and board["source"] == creative_intake.RADAR_BOARD_SOURCE, board
    assert board["kind"] == "digital_twin_render" and "not a photograph" in board["disclosure"]
    assert len(judge.calls) == 1 and creative_intake.judgement_for(db, SLUG)
    with db.session() as s:
        s.add(AuditLog(actor="creative", action=mc.BOARD_ACTION, artifact=SLUG,
                       detail={"slug": SLUG, "image": {"sha256": "f" * 64},
                               "image_ref": "sha256:" + "f" * 64}))
    assert creative_intake.judgement_for(db, SLUG) is None


def test_mutation_the_radar_judging_pass_removed_leaves_production_stalled():
    """Without `judge_radar_waiting` the defect returns: vision open, nothing judged, nothing
    drafted -- so the end-to-end proof above depends on the fix, not on the fixture."""
    db = _production_state(vision=True)
    judge = _Judge('{"thumbnail_reads_small": true, "craft_impression": 4.3}')
    restore = _with_judge(judge)
    real = creative_intake.judge_radar_waiting
    creative_intake.judge_radar_waiting = lambda ctx, **kw: {"judged": [], "held": [],
                                                             "rescored": []}
    try:
        _drain(db, cycles=2)
    finally:
        creative_intake.judge_radar_waiting = real
        restore()
    assert judge.calls == []
    assert not [j for j in _jobs(db, "cir.draft") if (j.inputs or {}).get("slug") == SLUG]
    assert not _certified(db, SLUG)


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]

if __name__ == "__main__":
    failed = 0
    assert TESTS
    for t in TESTS:
        try:
            t()
            print(f"OK   {t.__name__}")
        except Exception as exc:  # noqa: BLE001
            import traceback

            failed += 1
            print(f"  FAIL {t.__name__}: {type(exc).__name__}: {str(exc)[:1500]}")
            traceback.print_exc(limit=4)
    print(f"{len(TESTS) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
