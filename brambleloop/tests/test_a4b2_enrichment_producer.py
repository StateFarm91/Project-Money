"""A4B-2 (Main verdict on A4b, HIGH): something in production answers open enrichment requests.

Before this, `enrichment_requests.answer` had no caller in `src/`. This test drives the
real hourly `research.enrichment_sweep` through the real Worker and checks four things:

* A refusal the authoritative seed now passes is answered and re-drafted with no hand-built
  payload. The path is: sweep, then answer job, then `draft:<slug>:enrich:1`, then drafted.
* A refusal the construction still makes is never answered, so no round is spent however
  many sweeps run.
* A dynamic or registry request stays held, with the contract's reason.
* A repeated sweep queues no second answer.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_a4b2_enrichment_producer.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import dataclasses
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from brambleloop.creative import enrichment_producer as P  # noqa: E402
from brambleloop.creative import enrichment_requests as E  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402
import test_opus2_enrichment_requests as T  # noqa: E402

BASKET = "nordic-forest-basket"           # a static seed the fallback can build
FOX = "woodland-fox-amigurumi"            # a static seed the fallback refuses


def _hourly_sweep(db):
    JobQueue(db).enqueue("crochet_engineer", "research.enrichment_sweep", {}, priority=0)
    T._run(db, "research.enrichment_sweep")
    return T._jobs(db, "research.enrichment_sweep")[-1][2]


def _refused(db, slug):
    seed = pipeline._seed_for(slug)
    T._established(db, seed)
    T._audit(db)("cir.draft_refused", artifact=slug, detail={
        "reason": "construction was not available when drafted", "gate": "construction",
        "category": seed.category})
    return seed


def test_production_sweep_answers_and_redrafts_with_no_hand_built_payload():
    db, path = T._store()
    _refused(db, BASKET)
    out = _hourly_sweep(db)
    assert out["answers"]["answers_queued"] == [BASKET], out
    answers = T._jobs(db, P.ANSWER_JOB)
    assert len(answers) == 1 and answers[0][0].startswith(f"enrich-answer:{BASKET}:")
    T._run(db, P.ANSWER_JOB)
    assert T._jobs(db, P.ANSWER_JOB)[0][2]["accepted"] is True
    assert E.state(db)[BASKET]["state"] == E.RESOLVED
    drafts = T._jobs(db, "cir.draft")
    assert [d[0] for d in drafts] == [f"draft:{BASKET}:enrich:1"], drafts
    T._run(db, "cir.draft")
    assert T._jobs(db, "cir.draft")[0][2].get("drafted") is True
    # The next hourly sweep finds nothing open and queues no second answer.
    again = _hourly_sweep(db)
    assert again["answers"]["answers_queued"] == [] and len(T._jobs(db, P.ANSWER_JOB)) == 1


def test_a_construction_that_still_refuses_spends_no_round():
    db, _ = T._store()
    seed = pipeline._seed_for(FOX)
    T._established(db, seed)
    JobQueue(db).enqueue("crochet_engineer", "cir.draft", T._payload(seed), priority=0)
    T._run(db, "cir.draft")
    assert T._jobs(db, "cir.draft")[0][2].get("gate") == "construction"
    for _ in range(4):
        out = _hourly_sweep(db)
        assert out["answers"]["answers_queued"] == [], out
    waiting = {w["slug"]: w for w in out["answers"]["waiting"]}
    assert waiting[FOX]["why"] == "construction still refuses the authoritative seed"
    assert waiting[FOX]["still_missing"], waiting
    assert not T._jobs(db, P.ANSWER_JOB)
    st = E.state(db)[FOX]
    assert st["state"] == E.OPEN and int(st.get("rounds", 0)) == 0, st


def test_dynamic_and_registry_requests_stay_held_with_the_contract_reason():
    db, _ = T._store()
    _refused(db, BASKET)
    T._sweep(db, audit=T._audit(db))
    real = pipeline._seed_for
    pipeline._seed_for = lambda slug, db=None: dataclasses.replace(real(slug), origin="intake")
    try:
        waiting = P.plan(db)["waiting"]
    finally:
        pipeline._seed_for = real
    assert [w["why"] for w in waiting] == [
        "dynamic approvals require an atomic enrichment authority contract"], waiting
    T._audit(db)(E.REQUESTED, artifact="mosaic-brief", detail={
        "state": E.OPEN, "asks": [{"field": "construction"}], "context": {"kind": "registry"},
        "rounds": 0})
    reading = P.plan(db)
    held = {w["slug"]: w["why"] for w in reading["waiting"]}
    assert held["mosaic-brief"] == "no approved authority contract for this enrichment"
    assert [r["slug"] for r in reading["ready"]] == [BASKET]
    assert "authority contract" in reading["scope"]


def test_the_answer_key_is_stable_for_one_request_and_seed():
    db, _ = T._store()
    _refused(db, BASKET)
    T._sweep(db, audit=T._audit(db))
    a, b = P.plan(db)["ready"], P.plan(db)["ready"]
    assert a == b and len(a) == 1
    first = P.produce(db, enqueue=T._enqueue(db))
    second = P.produce(db, enqueue=T._enqueue(db))
    assert first["answers_queued"] == [BASKET] and second["answers_queued"] == []
    assert second["answers_already_queued"] == [BASKET]
    assert len(T._jobs(db, P.ANSWER_JOB)) == 1


def test_the_answer_payload_is_exactly_what_the_contract_admits():
    seed = pipeline._seed_for(BASKET)
    db, _ = T._store()
    _refused(db, BASKET)
    T._sweep(db, audit=T._audit(db))
    ctx = E.state(db)[BASKET]["context"]
    payload = P.authoritative_payload(seed)
    assert payload == T._payload(seed)
    assert E._authoritative_input(db, BASKET, ctx, payload, None) is None


if __name__ == "__main__":
    import traceback

    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception:  # noqa: BLE001
                fails += 1
                print("FAIL", name)
                traceback.print_exc()
    print(f"{fails} failed")
    sys.exit(1 if fails else 0)
