"""W4-CLOSE5: security review of 324927f, R1 (LOW) -- the public webhook's dedicated gate.

  R1  the unauthenticated /api/etsy/webhook runs its database work on its OWN small limiter
      (etsy_webhooks.GATE, WEBHOOK_SLOTS tokens), never AnyIO's shared default limiter, and a
      saturated gate answers a fast 503 + Retry-After with NO database work.

Local, deterministic; sockets refused by the REL2 harness; no provider is called.
Run: cd brambleloop && PYTHONPATH=src:tests $PY tests/test_w4_close5_r1.py
"""
from __future__ import annotations
import _opread  # W4-SECPATCH: owner-only GETs need the operator credential

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import asyncio
import os
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import test_w4_rel2 as R  # noqa: E402  (temp DB, socket guard, signed-delivery fixture)

from brambleloop.integrations import etsy_webhooks as wh  # noqa: E402


def test_r1_gate_uses_a_private_limiter_and_sheds_without_running_anything():
    gate = wh.WebhookGate(slots=3)
    release = threading.Event()
    started = threading.Semaphore(0)
    calls = []

    def work(tag):
        calls.append(tag)
        started.release()
        release.wait(10)
        return tag

    async def scenario():
        import anyio.to_thread

        default = anyio.to_thread.current_default_thread_limiter()
        base = default.borrowed_tokens
        tasks = [asyncio.create_task(gate.run(work, i)) for i in range(3)]
        for _ in range(3):
            while not started.acquire(blocking=False):
                await asyncio.sleep(0.005)
        # three in flight, all on the gate's own limiter; the shared default one is untouched
        assert gate.state()["in_flight"] == 3
        assert gate._limiter().borrowed_tokens == 3
        assert default.borrowed_tokens == base, (default.borrowed_tokens, base)
        # a fourth is refused at once: None, and `work` is never called
        t0 = time.perf_counter()
        assert await gate.run(work, "shed") is None
        assert time.perf_counter() - t0 < 0.05
        assert "shed" not in calls and gate.state()["shed_busy"] == 1
        release.set()
        assert sorted(await asyncio.gather(*tasks)) == [0, 1, 2]
        # slots come back: the next call is admitted
        assert await gate.run(lambda: "again") == "again"

    asyncio.run(scenario())
    st = gate.state()
    assert st == {"slots": 3, "in_flight": 0, "admitted": 4, "shed_busy": 1}, st


def test_r1_a_slot_is_released_when_the_work_raises():
    gate = wh.WebhookGate(slots=1)

    def boom():
        raise RuntimeError("x")

    async def scenario():
        try:
            await gate.run(boom)
        except RuntimeError:
            pass
        else:
            raise AssertionError("the exception was swallowed")
        assert await gate.run(lambda: 1) == 1

    asyncio.run(scenario())
    assert gate.state()["in_flight"] == 0


def test_r1_slots_are_fewer_than_the_db_pool_and_threadpool():
    # QueuePool default pool_size is 5 (core/db.make_engine sets none), and AnyIO's default
    # limiter is 40: the webhook can hold at most WEBHOOK_SLOTS of either.
    from sqlalchemy.pool import QueuePool
    import inspect

    pool_size = inspect.signature(QueuePool.__init__).parameters["pool_size"].default
    assert 1 <= wh.WEBHOOK_SLOTS < pool_size, (wh.WEBHOOK_SLOTS, pool_size)
    assert wh.GATE.slots == wh.WEBHOOK_SLOTS
    try:
        wh.WebhookGate(slots=0)
    except ValueError:
        pass
    else:
        raise AssertionError("a zero-slot gate was accepted")


def test_r1_the_route_answers_503_with_no_db_work_when_saturated_then_recovers():
    os.environ[wh.SECRET_ENV] = R.SECRET
    os.environ["ETSY_SHOP_ID"] = "555"
    real_refuse, real_receive = wh.refuse, wh.receive
    called = []
    try:
        c, main = R._app()
        before = _opread.get(c, "/api/etsy").json()["webhooks"]
        refused_before = dict(before["refused"])
        wh.refuse = lambda *a, **k: called.append("refuse") or real_refuse(*a, **k)
        wh.receive = lambda *a, **k: called.append("receive") or real_receive(*a, **k)
        h, body = R._delivery(wid="msg_close5_r1")
        bad = {**h, "webhook-signature": "v1,AAAA", "content-type": "application/json"}
        for _ in range(wh.GATE.slots):            # every slot held, as by a flood in flight
            assert wh.GATE.try_enter()
        try:
            shed0 = wh.GATE.state()["shed_busy"]
            for hdrs, payload in ((bad, body), ({**h, "content-type": "application/json"},
                                                body)):
                t0 = time.perf_counter()
                r = c.post("/api/etsy/webhook", content=payload, headers=hdrs)
                assert r.status_code == 503, r.text
                assert r.json() == {"accepted": False, "reason": "busy",
                                    "why": "webhook capacity saturated; retry"}
                assert r.headers.get("retry-after") == str(wh.BUSY_RETRY_AFTER_SECONDS)
                assert time.perf_counter() - t0 < 2.0
            # oversized body while saturated: still a 503, and not even the refusal is counted
            r = c.post("/api/etsy/webhook", content=b"{" + b" " * (wh.MAX_BODY_BYTES + 5) + b"}",
                       headers={"content-type": "application/json"})
            assert r.status_code == 503, r.text
            assert called == [], called
            assert wh.GATE.state()["shed_busy"] == shed0 + 3
        finally:
            for _ in range(wh.GATE.slots):
                wh.GATE.leave()
        after = _opread.get(c, "/api/etsy").json()["webhooks"]
        assert after["refused"] == refused_before, "a shed request did database work"
        assert after["gate"]["in_flight"] == 0 and after["gate"]["slots"] == wh.WEBHOOK_SLOTS
        # free again: a bad signature is a counted 401, a good delivery is accepted
        r = c.post("/api/etsy/webhook", content=body, headers=bad)
        assert r.status_code == 401 and r.json()["reason"] == "bad_signature", r.text
        r = c.post("/api/etsy/webhook", content=body,
                   headers={**h, "content-type": "application/json"})
        assert r.status_code == 202, r.text
        assert called == ["receive", "refuse", "receive"], called
        refused = _opread.get(c, "/api/etsy").json()["webhooks"]["refused"]
        assert refused.get("bad_signature", 0) == refused_before.get("bad_signature", 0) + 1
    finally:
        wh.refuse, wh.receive = real_refuse, real_receive
        os.environ.pop(wh.SECRET_ENV, None)
        os.environ.pop("ETSY_SHOP_ID", None)


if __name__ == "__main__":
    fails = 0
    ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            ran += 1
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    assert ran >= 4, "no tests collected"
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing")
    sys.exit(1 if fails else 0)
