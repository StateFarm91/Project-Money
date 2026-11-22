"""AMIGURUMI-JUDGING: an amigurumi concept from scan evidence is judged and drafted unaided.

SUPPLY-LANE row 4: amigurumi concepts were never judged. The radar vision judge needs a concept
board. The only board maker drew the concept's prototype from a digital twin, and a toy has no
prototype geometry ("'toy' has no finished size on file"). So every amigurumi concept waited
on `board_image` forever, although the animal engine (ENG-AMIGURUMI-BREADTH) can draft it, and
although the engine-demand list leads with amigurumi.

This suite builds the production shape on a scratch SQLite file and runs the real handlers
through the real worker:

* Launch-0 is exhausted;
* the concept pool is generated from synthetic watchlist scans (`test_concepts100`), with an
  answered research task behind each arena that has READY concepts. The scan-derived frog
  `pool-garden-amigurumi-frog-student` is the concept under test;
* paid vision is open (owner activation + probe) with a FIXTURE vision judge;
* `flux-3-image:generation` is activated at exactly D-OWNER-APPROVE-ALL's ceilings
  (`owner_directives.ACTIVATIONS`), with a BFL key variable set to a dummy and a FIXTURE
  transport (`images._post`) standing in for the provider. No request leaves the process.

Only the scheduler's cadence jobs are enqueued (`radar.concept_pool`, `radar.concept_intake`,
`mjs.seasonal_sentinel`, `supply.admit`), and the worker drains whatever they cause. Nothing
writes a board or a judgement, and nothing enqueues a chain job.

Every listing, research source, render and judgement here is a TEST FIXTURE.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_amigurumi_judging.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702 - per-process temp sandbox, removed at exit
import base64
import io
import os
import socket
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("BRAMBLELOOP_PHASE", "shadow")


def _refuse(*_a, **_k):
    raise OSError("network refused: this test makes no outbound connection")


socket.socket.connect = _refuse  # type: ignore[assignment]
socket.create_connection = _refuse  # type: ignore[assignment]

import _paid_activation as paid  # noqa: E402
import test_concepts100 as C100  # noqa: E402 - the synthetic watchlist scans and research
import test_new_product_flow as NPF  # noqa: E402 - Launch-0 exhaustion, vision, fixture judge

from sqlalchemy import select  # noqa: E402

from brambleloop.cir.model import Material  # noqa: E402
from brambleloop.core.models import AuditLog, CostEntry, Job, JobStatus  # noqa: E402
from brambleloop.creative import intake as creative_intake  # noqa: E402
from brambleloop.creative import toy_board as TB  # noqa: E402
from brambleloop.creative import fallback_constructions as FC  # noqa: E402
from brambleloop.gateway import images  # noqa: E402
from brambleloop.gateway import paid_provider_gate as G  # noqa: E402
from brambleloop.ops import owner_directives as OD  # noqa: E402
from brambleloop.products import moment_candidates as mc  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.radar import concept_pool as P  # noqa: E402
from brambleloop.runtime.worker import Worker  # noqa: E402

FROG = "pool-garden-amigurumi-frog-student"     # generated from the scans, not hand-written
CADENCE_JOBS = (("market_radar", "radar.concept_pool"),) + NPF.CADENCE_JOBS
CYCLES = 3
MAX_JOBS_PER_CYCLE = 400
KEY_ENV = {"BRAMBLELOOP_IMAGE_KEY_BFL": "test-not-a-secret"}


def _png_b64() -> str:
    from PIL import Image

    out = io.BytesIO()
    Image.new("RGB", (512, 512), (110, 140, 80)).save(out, format="PNG")
    return base64.b64encode(out.getvalue()).decode()


PNG = _png_b64()


class Flux:
    """FIXTURE BFL transport: records every attempted render, sends nothing."""

    def __init__(self, fail: BaseException | None = None):
        self.prompts: list[str] = []
        self.fail = fail

    def __enter__(self):
        import json

        self._saved = (images._post, images._get)

        def post(url, headers, payload, *, label, timeout):
            body = json.loads(payload) if isinstance(payload, (bytes, str)) else payload
            self.prompts.append(str((body or {}).get("prompt") or ""))
            if self.fail is not None:
                raise self.fail
            return {"data": [{"b64_json": PNG}]}

        def get(url, headers, *, label, timeout):
            raise AssertionError("no poll expected")

        images._post, images._get = post, get
        return self

    def __exit__(self, *exc):
        images._post, images._get = self._saved
        return False


@contextmanager
def _env(**values):
    saved = {k: os.environ.get(k) for k in values}
    try:
        for k, v in values.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        yield
    finally:
        for k, v in saved.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)


def _activate_flux(db, **over) -> None:
    """flux-3-image:generation at D-OWNER-APPROVE-ALL's own ceilings (or lower, for a test)."""
    ceil = dict(OD.ACTIVATIONS[("flux-3-image", "generation")])
    ceil.update(over)
    paid.activate(db, "flux-3-image", G.GENERATION, daily=ceil["daily_ceiling_cad"],
                  monthly=ceil["monthly_ceiling_cad"], per_gallery=ceil["per_gallery_cad"])


def _production_state(*, flux: bool = True, **flux_ceilings):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    db = C100._db()
    NPF._exhaust_launch0(db)
    C100._scan(db)
    P.replenish(db, now=now, unit_cad=0.12, admit=False)
    for pod in sorted({r.pod for r in C100._pool(db) if r.state == P.READY}):
        C100._answered_task(db, pod)
    NPF._open_vision(db)
    if flux:
        _activate_flux(db, **flux_ceilings)
    return db


def _drain(db, *, cycles: int = CYCLES, start: int = 0) -> None:
    for c in range(start, start + cycles):
        q = JobQueue(db)
        for agent, job_type in CADENCE_JOBS:
            q.enqueue(agent, job_type, {"cadence": f"fixture-{c}"},
                      idempotency_key=f"fixture-cadence:{job_type}:{c}", priority=0)
        w = Worker(db, f"amij-{c}")
        for _ in range(MAX_JOBS_PER_CYCLE):
            if not w.run_once():
                break


def _run(db, *, flux: Flux | None = None, cycles: int = CYCLES, start: int = 0,
         judge_answer: str = '{"thumbnail_reads_small": true, "craft_impression": 4.3}'):
    judge = NPF._Judge(judge_answer)
    restore = NPF._with_judge(judge)
    try:
        with _env(**KEY_ENV), (flux or Flux()) as wire:
            _drain(db, cycles=cycles, start=start)
    finally:
        restore()
    return wire, judge


def _drafts(db, slug: str) -> list[Job]:
    with db.session() as s:
        jobs = list(s.scalars(select(Job).where(Job.job_type == "cir.draft").order_by(Job.id)))
        s.expunge_all()
    return [j for j in jobs if (j.inputs or {}).get("slug") == slug]


def _held(db, slug: str) -> list[dict]:
    with db.session() as s:
        jobs = list(s.scalars(select(Job).where(Job.job_type == "mjs.seasonal_sentinel",
                                                Job.status == JobStatus.DONE)))
    return [h for j in jobs
            for h in ((j.outputs or {}).get("regated") or {}).get("radar_held") or []
            if h["slug"] == slug]


def _image_costs(db, slug: str) -> list[CostEntry]:
    with db.session() as s:
        rows = [r for r in s.scalars(select(CostEntry).where(CostEntry.kind == "image"))
                if (r.detail or {}).get("slug") == slug or r.product_slug == slug]
        s.expunge_all()
    return rows


def _flux_calls(db, gallery: str) -> list:
    G.ensure_tables(db)
    with db.session() as s:
        rows = list(s.scalars(select(G.PaidProviderCall).where(
            G.PaidProviderCall.gallery == gallery)))
        s.expunge_all()
    return rows


# ---- the production state, and the stall ------------------------------------------------------


def test_the_scan_derived_frog_is_an_animal_engine_concept():
    """The concept under test comes from the scans, routes to the animal engine, and is a
    toy: its form has no prototype geometry, so the twin board refuses it."""
    db = _production_state(flux=False)
    pool = {r.slug: r for r in C100._pool(db)}
    assert FROG in pool and pool[FROG].family == FC.AMIGURUMI_ANIMAL, pool.get(FROG)
    assert pool[FROG].state == P.READY, pool[FROG].reasons


def test_mutation_without_the_toy_board_the_frog_waits_on_board_image_forever():
    """The defect: vision and FLUX open, yet nothing is rendered, judged or drafted."""
    db = _production_state()
    real = TB.toy_concept
    TB.toy_concept = lambda db, slug: False
    try:
        wire, judge = _run(db)
    finally:
        TB.toy_concept = real
    assert wire.prompts == [], "nothing renders without the toy board"
    assert not _drafts(db, FROG)
    held = _held(db, FROG)
    assert held and "has no finished size on file" in held[-1]["waiting_on"][0], held


# ---- the fix: judged and drafted unaided, the render paid once -------------------------------


def test_an_amigurumi_concept_from_scan_evidence_reaches_cir_draft_unaided_paid_once():
    db = _production_state()
    wire, judge = _run(db)
    # The board: one disclosed AI concept render, prompted from the engine's own draft.
    board = mc.board_record(db, FROG)
    assert board and board["kind"] == TB.KIND and board["board_source"] == TB.SOURCE, board
    assert "not a photograph" in board["disclosure"] and "never used in a listing" in \
        board["disclosure"], board
    assert board["route"] == FC.AMIGURUMI_ANIMAL
    cir, _route, _i = TB.engine_draft(db, FROG)
    assert board["cir_fingerprint"] == cir.fingerprint
    frog_prompts = [p for p in wire.prompts if " frog amigurumi " in p]
    assert len(frog_prompts) == 1, wire.prompts
    assert frog_prompts[0] == TB.prompt_for(cir)
    assert "2 arms, 2 legs" in frog_prompts[0] and "embroidered" in frog_prompts[0]
    assert "No plastic safety eyes" in frog_prompts[0]
    # Paid once, through the gate, charged to its own gallery.
    calls = _flux_calls(db, TB.gallery_for(FROG))
    assert len(calls) == 1 and calls[0].status == G.BILLED and calls[0].provider == "flux-3-image"
    assert len(_image_costs(db, FROG)) == 1, _image_costs(db, FROG)
    # Judged on exactly those bytes (CB2-D01).
    judged = NPF._rows(db, creative_intake.JUDGED_ACTION, FROG)
    assert judged and judged[-1][2]["board_sha256"] == board["image"]["sha256"]
    # ... then drafted on the animal engine, entering by the one door.
    drafts = _drafts(db, FROG)
    assert len(drafts) == 1 and drafts[0].idempotency_key == f"draft:{FROG}", drafts
    assert drafts[0].status == JobStatus.DONE, drafts[0].last_error
    assert drafts[0].outputs.get("drafted") and \
        drafts[0].outputs.get("construction") == FC.AMIGURUMI_ANIMAL, drafts[0].outputs
    assert [d for _i, _a, d in NPF._rows(db, "supply.admitted", FROG)
            if d.get("key") == f"draft:{FROG}"]
    # Redrive: three more scheduler cycles and a re-run of the judging cadence.
    again, judge2 = _run(db, cycles=3, start=CYCLES)
    assert not [p for p in again.prompts if " frog amigurumi " in p], again.prompts
    assert len(_flux_calls(db, TB.gallery_for(FROG))) == 1
    assert len(_image_costs(db, FROG)) == 1
    assert len(_drafts(db, FROG)) == 1
    # The day and per-run toy caps held across the whole run.
    assert len(wire.prompts) + len(again.prompts) <= TB.MAX_RENDERS_PER_DAY, \
        (wire.prompts, again.prompts)


def test_the_toy_is_still_withheld_at_certification_for_its_physical_evidence():
    """The child-safety gate is never bypassed: the drafted frog compiles and certification
    withholds it ONLY for the physical sample and the child-safety physical evidence."""
    db = _production_state()
    _run(db)
    with db.session() as s:
        certs = [j for j in s.scalars(select(Job).where(Job.job_type == "gate.certify"))
                 if str((j.inputs or {}).get("slug") or (j.outputs or {}).get("artifact")
                        or "").startswith(FROG)]
        outs = [dict(j.outputs or {}) for j in certs if j.status == JobStatus.DONE]
    assert outs, "the frog reached gate.certify"
    out = outs[-1]
    assert out.get("granted") is False, out
    codes = sorted({r.split(":")[0].split()[-1] for r in out["reasons"]})
    # D-OWNER-NO-SAMPLE-SIZING: PHYSICAL_TEST_REQUIRED remains only where the toy is not sized
    # from standard gauge (gates.certificate.sized_from_standard_gauge); child safety always holds.
    assert "CHILD_SAFETY_PHYSICAL_EVIDENCE_UNKNOWN" in codes and set(codes) <= {
        "CHILD_SAFETY_PHYSICAL_EVIDENCE_UNKNOWN", "PHYSICAL_TEST_REQUIRED"}, out["reasons"]


# ---- no paid call repeats on redrive -----------------------------------------------------------


def test_a_render_that_may_have_been_paid_for_is_never_bought_again():
    """A failure after the provider may have taken the work (here a read timeout, billed at
    the estimate as UNKNOWN) is recorded and held; later runs never ask again."""
    db = _production_state()
    wire, _ = _run(db, flux=Flux(fail=TimeoutError("read timed out")))
    asked = [p for p in wire.prompts if " frog amigurumi " in p]
    assert len(asked) == 1, wire.prompts
    assert TB.state(db, FROG)["state"] == TB.PAID_UNFILED
    again, _ = _run(db, cycles=2, start=CYCLES)
    assert not [p for p in again.prompts if " frog amigurumi " in p]
    assert not _drafts(db, FROG)
    held = _held(db, FROG)
    assert held and "never bought again" in held[-1]["waiting_on"][0], held


def test_a_crash_between_request_and_record_is_never_bought_again():
    """A REQUESTED row with no outcome (the process died mid-render) blocks every later render
    of that concept: the system cannot know the render was not paid for."""
    db = _production_state()
    with db.session() as s:
        s.add(AuditLog(actor="creative", action=TB.ACTION, artifact=FROG,
                       detail={"state": TB.REQUESTED, "job_id": 999999,
                               "fingerprint": "f" * 64, "provider": TB.PROVIDER}))
    wire, _ = _run(db)
    assert not [p for p in wire.prompts if " frog amigurumi " in p]
    assert not _drafts(db, FROG)
    held = _held(db, FROG)
    assert held and "never bought again" in held[-1]["waiting_on"][0], held


def test_a_refusal_before_sending_is_declined_and_may_be_asked_again_later():
    """A gate refusal (here the per-gallery cap, lowered to 0 by its lower-only variable) sends
    nothing and bills nothing. It is recorded as declined, so a later run may ask."""
    db = _production_state()
    with _env(**{G.GALLERY_IMAGE_CAP_ENV: "0"}):
        wire, _ = _run(db)
    assert wire.prompts == [], "the per-gallery cap refused before any request"
    assert TB.state(db, FROG)["state"] == TB.DECLINED, TB.state(db, FROG)
    assert "gallery_image_cap" in TB.state(db, FROG)["why"]
    assert not _image_costs(db, FROG)
    assert not [c for c in _flux_calls(db, TB.gallery_for(FROG)) if c.status in G.COUNTED]
    again, _ = _run(db, cycles=2, start=CYCLES)
    assert len([p for p in again.prompts if " frog amigurumi " in p]) == 1, again.prompts
    assert TB.state(db, FROG)["state"] == TB.FILED


def test_the_daily_caps_hold():
    """The code's daily image cap and the provider's daily CA$ ceiling each refuse first."""
    for env, ceilings, code in (({G.DAILY_IMAGE_CAP_ENV: "0"}, {}, "daily_image_cap"),
                                ({}, {"daily_ceiling_cad": 0.01}, "provider_daily_ceiling")):
        db = _production_state(**ceilings)
        with _env(**env):
            wire, _ = _run(db)
        assert wire.prompts == [], (code, wire.prompts)
        st = TB.state(db, FROG)
        assert st.get("state") == TB.DECLINED and code in st["why"], (code, st)
        assert not _image_costs(db, FROG) and not _drafts(db, FROG)
        # Declined requests cost nothing and never use up the day's toy-render cap.
        with db.session() as s:
            assert TB._requested_today(s, datetime.now(timezone.utc)) == 0


def test_without_the_flux_activation_nothing_is_rendered_or_recorded():
    db = _production_state(flux=False)
    wire, judge = _run(db)
    assert wire.prompts == []
    assert TB.state(db, FROG) == {}
    assert not _drafts(db, FROG)
    held = _held(db, FROG)
    assert held and "FLUX not ready" in held[-1]["waiting_on"][0], held


# ---- child safety before any spend -------------------------------------------------------------


def test_the_child_safety_preconditions_refuse_a_render_before_any_spend():
    db = _production_state(flux=False)
    _run(db)                                       # intake approves the frog; no FLUX yet
    _activate_flux(db)
    cir, _route, _i = TB.engine_draft(db, FROG)
    assert TB.safety_preconditions(cir) == []
    hard = cir.__class__.from_dict(cir.to_dict())
    hard.materials = list(hard.materials) + [Material(name="12 mm safety eyes")]
    assert any("hard part" in p for p in TB.safety_preconditions(hard))
    assert any("safety eye" in p for p in TB.safety_preconditions(
        cir, premise="a frog with safety eyes"))
    glued = cir.__class__.from_dict(cir.to_dict())
    glued.components[0].note = glued.components[0].note.replace("Embroider the face", "Glue")
    assert any("embroidered" in p for p in TB.safety_preconditions(glued))
    # And through the real path: a refusal claims nothing and sends nothing.
    real = TB.safety_preconditions
    TB.safety_preconditions = lambda cir, premise="": ["fixture: a hard part"]
    try:
        with _env(**KEY_ENV), Flux() as wire:
            got = TB.render_board(db, FROG)
    finally:
        TB.safety_preconditions = real
    assert got["board"] == "" and "child-safety precondition" in got["why"], got
    assert wire.prompts == [] and TB.state(db, FROG) == {}


def test_a_toy_the_animal_engine_will_not_draft_is_never_rendered():
    db = _production_state()
    hedgehog = "pool-amigurumi-hedgehog-newlyweds"
    assert not TB.toy_concept(db, hedgehog)
    assert not TB.toy_concept(db, "pool-beanie-banded-self"), "a beanie is not a toy board"
    with _env(**KEY_ENV), Flux() as wire:
        got = TB.render_board(db, hedgehog)
    assert got["board"] == "" and wire.prompts == [], got


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
            print(f"FAIL {t.__name__}: {type(exc).__name__}: {str(exc)[:1500]}")
            traceback.print_exc(limit=4)
    print(f"{len(TESTS) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
