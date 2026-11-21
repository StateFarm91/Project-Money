"""ENG-ADMIT-TO-BUILD: admitted pool concepts stop at the pre-engineering gate's vision checks.

Production readback (0aeb81d2, 20:40Z): the pool admitted 5 concepts at 19:56Z, but 45 minutes
later no `cir.draft` existed for any of them, products_in_flight was 1 and offers_waiting 0.
The daily ledger read concepts_approved 24 and products_started 0 for the day.

The chain is: pool admission -> `radar.concept_intake` (approved) -> `radar.score` ->
the pre-engineering gate -> `supply.offer` -> `cir.draft`. The gate's `premise_thumbnail` and
`jury` checks need `image_vision`. That capability opens only with an ACTIVE Anthropic vision
activation and a successful probe under it. The owner directive D-OWNER-APPROVE-ALL activated
`openai-vision:vision` and `flux-3-image:generation` only, so in production every admitted
concept waits, unpassed, on `image_vision`. Unmeasured is never pass, so this test does not
open the gate. It proves three things:

1. Without vision, admitted concepts are judged, wait on `image_vision`, and no pool draft
   is made (the production state). The new readback field `supply.after_admission_24h` names
   the stop: gate_waiting > 0 with gate_waiting_on {"image_vision": n}, offered 0.
2. With an activated, probed vision judge (FIXTURE provider, never a real call), the same
   admitted concepts pass the gate, are offered and become `cir.draft` jobs that run.
3. The readback field carries counts and the gate-key vocabulary only.

Every listing, judgement and product here is a TEST FIXTURE.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_admit_to_build.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702 - per-process temp sandbox, removed at exit
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("BRAMBLELOOP_PHASE", "shadow")

import test_new_product_flow as NPF  # noqa: E402
import test_supply_feed as SF  # noqa: E402
import test_supply_lane as LANE  # noqa: E402
import test_supply_research as SR  # noqa: E402

from sqlalchemy import select  # noqa: E402

from brambleloop.core.models import Job, JobStatus  # noqa: E402
from brambleloop.ops import production_evidence as PE  # noqa: E402
from brambleloop.radar import concept_pool as P  # noqa: E402


def _state(*, vision: bool):
    orig = NPF._open_vision
    if not vision:
        NPF._open_vision = lambda db: None       # production: no Anthropic vision activation
    try:
        db = SR._pre_deploy_state()
    finally:
        NPF._open_vision = orig
    restore = None
    if vision:
        _judge, restore = LANE._with_judge()
    try:
        SF._drain(db, cycles=3)                  # the deploy pass: compare, pool, intake, admit
    finally:
        if restore:
            restore()
    return db


class _OpenAITransport:
    """FIXTURE transport for `OpenAIProvider._post`: never a network call. Counts requests."""

    def __init__(self, *, status: int = 200, answer: str =
                 '{"thumbnail_reads_small": true, "craft_impression": 4.3}'):
        self.status, self.answer, self.calls = status, answer, 0

    def __call__(self, provider, body, headers, timeout):
        self.calls += 1
        if self.status != 200:
            return self.status, '{"error": {"message": "fixture provider error"}}'
        return 200, json.dumps({
            "id": f"fixture-{self.calls}", "model": provider.model,
            "choices": [{"message": {"content": self.answer}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 900, "completion_tokens": 30}})


def _state_openai(transport, *, cycles: int = 3):
    """Production's activations: openai-vision only (no Anthropic vision), a FIXTURE transport."""
    import _paid_activation as paid

    from brambleloop.gateway import openai_chat
    from brambleloop.gateway import paid_provider_gate as G

    orig_open = NPF._open_vision
    NPF._open_vision = lambda db: paid.activate(db, G.OPENAI_VISION, G.VISION,
                                                daily=2.0, monthly=10.0, per_gallery=1.0)
    saved_post = openai_chat.OpenAIProvider._post
    saved_key = os.environ.get(openai_chat.KEY_VAR)
    openai_chat.OpenAIProvider._post = lambda self, body, headers, timeout: transport(
        self, body, headers, timeout)
    os.environ[openai_chat.KEY_VAR] = "fixture-key-not-a-secret"
    try:
        db = SR._pre_deploy_state()
        SF._drain(db, cycles=cycles)
    finally:
        NPF._open_vision = orig_open
        openai_chat.OpenAIProvider._post = saved_post
        if saved_key is None:
            os.environ.pop(openai_chat.KEY_VAR, None)
        else:
            os.environ[openai_chat.KEY_VAR] = saved_key
    return db


def _redrive(db, tag: str, *, cycles: int = 1) -> None:
    """A later cadence pass (fresh cadence keys, unlike SF._drain's fixture-0..n)."""
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime.worker import Worker

    for c in range(cycles):
        q = JobQueue(db)
        for agent, job_type in SF.CADENCE_JOBS:
            q.enqueue(agent, job_type, {"cadence": f"redrive-{tag}-{c}"},
                      idempotency_key=f"fixture-cadence:{job_type}:redrive-{tag}-{c}", priority=0)
        w = Worker(db, f"redrive-{tag}-{c}")
        for _ in range(SF.MAX_JOBS_PER_CYCLE):
            if not w.run_once():
                break


def _pool_drafts(db) -> list[Job]:
    admitted = {r.slug for r in SF._admitted_pool(db)}
    with db.session() as s:
        out = [j for j in s.scalars(select(Job).where(Job.job_type == "cir.draft"))
               if (j.inputs or {}).get("slug") in admitted]
        s.expunge_all()
        return out


def test_reproduces_production_admitted_but_never_drafted():
    db = _state(vision=False)
    assert SF._admitted_pool(db), "the deploy pass admits pool concepts"
    assert _pool_drafts(db) == [], "without vision no admitted concept is drafted"
    vis = PE.after_admission(db, now=SF.NOW)
    assert vis["score_handoff"] > 0 and vis["scored"]["promoted"] == 0, vis
    assert vis["gate_waiting"] > 0 and vis["gate_passed"] == 0, vis
    assert vis["gate_waiting_on"] == {"image_vision": vis["gate_waiting"]}, vis
    assert vis["offered"] == 0 and vis["admitted_to_engineering"] == 0, vis
    # the readback shows it at production's endpoint shape
    sup = PE.supply_visibility(db, now=SF.NOW)
    assert sup["after_admission_24h"] == vis, sup["after_admission_24h"]


def test_with_vision_admitted_concepts_pass_and_are_drafted():
    db = _state(vision=True)
    drafts = _pool_drafts(db)
    assert drafts, "an activated, probed vision judge lets admitted concepts be engineered"
    assert any(j.status == JobStatus.DONE for j in drafts), [j.status for j in drafts]
    vis = PE.after_admission(db, now=SF.NOW)
    assert vis["gate_passed"] > 0 and vis["scored"]["promoted"] > 0, vis
    assert vis["offered"] > 0 and vis["admitted_to_engineering"] > 0, vis


def test_openai_vision_alone_judges_and_admitted_concepts_are_drafted():
    from brambleloop.gateway import anthropic as A
    from brambleloop.gateway import paid_provider_gate as G

    transport = _OpenAITransport()
    db = _state_openai(transport)
    assert not A.vision_usable(db), "Anthropic vision stays closed, as in production"
    assert transport.calls > 0, "the owner-activated openai-vision judge was asked"
    drafts = _pool_drafts(db)
    assert drafts, "openai-vision judgements let admitted concepts be engineered"
    assert any(j.status == JobStatus.DONE for j in drafts), [j.status for j in drafts]
    vis = PE.after_admission(db, now=SF.NOW)
    assert vis["gate_passed"] > 0 and vis["offered"] > 0, vis
    # spend stayed inside openai-vision's activation ceilings, every call billed through the gate
    with db.session() as s:
        rows = list(s.scalars(select(G.PaidProviderCall).where(
            G.PaidProviderCall.provider == G.OPENAI_VISION)))
    assert rows and all(r.status == G.BILLED for r in rows), [r.status for r in rows]
    assert sum(r.actual_cad or r.estimate_cad for r in rows) <= 2.0, rows
    # idempotent per board image: a redrive sends nothing new for boards already judged
    before = transport.calls
    _redrive(db, "ok")
    assert transport.calls == before, (before, transport.calls)


def test_a_provider_error_never_passes_and_is_not_repeated():
    transport = _OpenAITransport(status=500)
    db = _state_openai(transport)
    assert transport.calls > 0, "the judge was asked"
    assert _pool_drafts(db) == [], "a failed judgement drafts nothing"
    vis = PE.after_admission(db, now=SF.NOW)
    assert vis["gate_passed"] == 0 and vis["offered"] == 0, vis
    assert vis["gate_waiting"] > 0, vis
    from brambleloop.creative import concept_judge as CJ
    assert not CJ.openai_vision_usable(db), "a failing provider closes the route"
    before = transport.calls
    _redrive(db, "err", cycles=2)
    assert transport.calls == before, "a redrive never repeats the failed paid call"
    assert _pool_drafts(db) == []


def _drain_jobs(db, jobs, tag: str, *, cycles: int = 1) -> None:
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime.worker import Worker

    for c in range(cycles):
        q = JobQueue(db)
        for agent, job_type in jobs:
            q.enqueue(agent, job_type, {"cadence": f"{tag}-{c}"},
                      idempotency_key=f"fixture-cadence:{job_type}:{tag}-{c}", priority=0)
        w = Worker(db, f"{tag}-{c}")
        for _ in range(SF.MAX_JOBS_PER_CYCLE):
            if not w.run_once():
                break


def test_the_hourly_regate_alone_judges_through_openai_vision_and_drafts():
    """creative.regate (hourly and once per deploy) is enough: without the daily seasonal
    sentinel, the concepts wait; one creative.regate pass judges them via openai-vision,
    they pass the gate, are offered and get cir.draft."""
    import _paid_activation as paid

    from brambleloop.gateway import openai_chat
    from brambleloop.gateway import paid_provider_gate as G
    from brambleloop.runtime.worker import CADENCES

    assert any(j == "creative.regate" and every <= 60 * 60 for _n, _a, j, every in CADENCES), \
        "creative.regate runs at least hourly"
    no_sentinel = tuple(j for j in SF.CADENCE_JOBS if j[1] != "mjs.seasonal_sentinel")
    transport = _OpenAITransport()
    orig_open = NPF._open_vision
    NPF._open_vision = lambda db: paid.activate(db, G.OPENAI_VISION, G.VISION,
                                                daily=2.0, monthly=10.0, per_gallery=1.0)
    saved_post = openai_chat.OpenAIProvider._post
    saved_key = os.environ.get(openai_chat.KEY_VAR)
    openai_chat.OpenAIProvider._post = lambda self, body, headers, timeout: transport(
        self, body, headers, timeout)
    os.environ[openai_chat.KEY_VAR] = "fixture-key-not-a-secret"
    try:
        db = SR._pre_deploy_state()
        _drain_jobs(db, no_sentinel, "nosentinel", cycles=3)
        assert transport.calls == 0, "nothing judged without a regate pass"
        assert _pool_drafts(db) == []
        assert PE.after_admission(db, now=SF.NOW)["gate_waiting"] > 0
        _drain_jobs(db, (("market_radar", "creative.regate"),) + no_sentinel, "regate",
                    cycles=2)
    finally:
        NPF._open_vision = orig_open
        openai_chat.OpenAIProvider._post = saved_post
        if saved_key is None:
            os.environ.pop(openai_chat.KEY_VAR, None)
        else:
            os.environ[openai_chat.KEY_VAR] = saved_key
    assert transport.calls > 0, "creative.regate asked the openai-vision judge"
    vis = PE.after_admission(db, now=SF.NOW)
    assert vis["gate_passed"] > 0 and vis["offered"] > 0, vis
    assert _pool_drafts(db), "the re-gated concepts were drafted"


def test_privacy_counts_and_gate_keys_only():
    db = _state(vision=False)
    vis = PE.after_admission(db, now=SF.NOW)
    slugs = {r.slug for r in SF._admitted_pool(db)}
    text = json.dumps(vis)
    assert not any(s in text for s in slugs), text
    from brambleloop.build2 import executor
    assert set(vis["gate_waiting_on"]) <= set(executor.GATE_BY_KEY) | {"unrecognised"}
    for k, v in vis.items():
        assert isinstance(v, (int, dict)), (k, v)


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"OK   {name}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"{len(tests) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
