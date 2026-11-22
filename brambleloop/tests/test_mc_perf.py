"""eng/mc-perf: Mission Control route budgets on a production-shaped database.

The owner reported Mission Control "takes minutes and minutes to load when I click stuff".
`tests/mc_perf_harness.py` times every `/api/cc/*` GET route on the seed in
`tests/_mc_perf_seed.py`; MC-PERF.md has the before/after table. This test guards:

1. every fast Mission Control route stays under 500 ms on the seeded database;
2. the snapshotted pages (autonomy, learn, company) answer a repeat click under 500 ms, and
   every snapshot body says it is one, with its age (never stale-as-fresh);
3. any successful owner write under /api/cc/ drops the snapshots: the next read is live;
4. approvals and the approve-all / approve-everything previews are never snapshotted;
5. the page snapshot never caches a failure and is single-flight;
6. F-11: background CPU work that calls `yield_to_requests()` lets a request through faster
   than the same work without yielding.

Run: cd brambleloop && PYTHONPATH=src:tests .venv/bin/python tests/test_mc_perf.py
"""
from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mc_perf_harness as H  # noqa: E402  (sets up the sandbox, env and network refusal)

from brambleloop.app.command_center import company as company_mod  # noqa: E402
from brambleloop.app.command_center import page_cache  # noqa: E402

BUDGET_MS = 500.0
# Routes with a measured cold cost above the budget on this seed, each with its own cold
# guard (about 2x the measured after-fix value, so a regression to the old per-click cost
# fails while machine load does not). See MC-PERF.md for what remains and why.
COLD_GUARD_MS = {"/api/cc/autonomy": 15_000, "/api/cc/learn": 15_000,
                 "/api/cc/company": 60_000, "/api/cc/approvals": 2_500,
                 "/api/cc/approvals/x": 2_500, "/api/cc/approve-all": 2_500,
                 "/api/cc/approve-everything": 4_000, "/api/cc/brief/morning": 3_000,
                 "/api/cc/catalogue": 3_000, "/api/cc/first-sale": 3_000,
                 "/api/cc/demand": 3_000, "/api/cc/home": 60_000, "/api/cc/mission": 6_000,
                 "/api/cc/insights": 5_000, "/api/cc/launch/packet": 5_000,
                 "/api/cc/laura": 6_000, "/api/cc/money": 60_000, "/api/cc/notifications": 2_500,
                 "/api/cc/operations": 50_000, "/api/cc/p0-board": 2_500,
                 "/api/cc/production": 3_000, "/api/cc/store": 30_000,
                 "/api/cc/store/catalogue": 9_000, "/api/cc/truth": 50_000}
SNAPSHOTTED = ("/api/cc/autonomy", "/api/cc/learn", "/api/cc/company", "/api/cc/home",
               "/api/cc/money", "/api/cc/operations", "/api/cc/truth", "/api/cc/store")
NEVER_SNAPSHOTTED = ("/api/cc/approvals", "/api/cc/approve-all", "/api/cc/approve-everything")

_STATE: dict = {}


def _client():
    if "c" not in _STATE:
        # The Build 2 matrix walks the code graph for minutes; the company page reads it
        # from its own background snapshot, so the test stubs the walk (as its own suite does).
        company_mod.COMPUTE_BUILD2 = lambda db: (_ for _ in ()).throw(RuntimeError("stub"))
        H.seed()
        H._install_counters()
        _STATE["c"], _STATE["csrf"] = H.session()
    return _STATE["c"]


def _get_ms(path):
    c = _client()
    t0 = time.perf_counter()
    r = c.get(path)
    return (time.perf_counter() - t0) * 1000, r


def test_every_mission_control_route_is_within_budget():
    _client()
    page_cache.reset()
    slow = {}
    for p in H.routes():
        ms, r = _get_ms(p)
        assert r.status_code < 500, (p, r.status_code, r.text[:300])
        guard = COLD_GUARD_MS.get(p, BUDGET_MS)
        if ms > guard:
            slow[p] = round(ms)
    assert not slow, f"routes over budget: {slow}"


def test_snapshotted_pages_answer_a_repeat_click_fast_and_show_their_age():
    page_cache.reset()
    for p in SNAPSHOTTED:
        _ms, first = _get_ms(p)
        assert first.status_code == 200, (p, first.text[:300])
        snap = first.json().get("snapshot")
        assert snap and snap["served_from_snapshot"] in (False, True), (p, snap)
        ms, second = _get_ms(p)
        snap2 = second.json()["snapshot"]
        assert snap2["served_from_snapshot"] is True, (p, snap2)
        assert snap2["age_s"] >= 0 and snap2["computed_at"] and snap2["ttl_s"] > 0
        assert ms < BUDGET_MS, (p, ms)


def test_an_owner_write_drops_every_snapshot():
    page_cache.reset()
    _get_ms("/api/cc/autonomy")
    _ms, r = _get_ms("/api/cc/autonomy")
    assert r.json()["snapshot"]["served_from_snapshot"] is True
    c = _client()
    import uuid
    w = c.post("/api/cc/home/seen", json={},
               headers={"X-CSRF-Token": _STATE["csrf"], "X-CC-Nonce": uuid.uuid4().hex,
                        "X-CC-Timestamp": str(int(time.time()))})
    assert w.status_code == 200, w.text[:300]
    _ms, r = _get_ms("/api/cc/autonomy")
    assert r.json()["snapshot"]["served_from_snapshot"] is False


def test_a_refused_write_does_not_drop_snapshots_and_a_get_never_does():
    page_cache.reset()
    _get_ms("/api/cc/autonomy")
    before = page_cache.STATS["invalidations"]
    c = _client()
    c.post("/api/cc/home/seen", json={})          # no CSRF/nonce: refused
    _get_ms("/api/cc/home")
    assert page_cache.STATS["invalidations"] == before
    assert _get_ms("/api/cc/autonomy")[1].json()["snapshot"]["served_from_snapshot"] is True


def test_approvals_and_previews_are_always_live():
    page_cache.reset()
    for p in NEVER_SNAPSHOTTED:
        for _ in range(2):
            body = _get_ms(p)[1].json()
            assert "snapshot" not in body, p


def test_the_snapshot_never_caches_a_failure_and_is_single_flight():
    page_cache.reset()
    calls = []

    def boom():
        calls.append(1)
        raise RuntimeError("unreadable")

    for _ in range(2):
        try:
            page_cache.get("t-fail", boom)
        except RuntimeError:
            pass
    assert len(calls) == 2
    page_cache.get("t-none", lambda: calls.append(1))      # a non-dict body is not kept
    page_cache.get("t-none", lambda: calls.append(1))
    assert len(calls) == 4

    n = []
    gate = threading.Event()

    def slow():
        n.append(1)
        gate.wait(5)
        return {"v": 1}

    ts = [threading.Thread(target=page_cache.get, args=("t-flight", slow)) for _ in range(20)]
    [t.start() for t in ts]
    time.sleep(0.2)
    gate.set()
    [t.join(10) for t in ts]
    assert len(n) == 1, len(n)
    os.environ["BRAMBLELOOP_CC_SNAPSHOT_TTL_S"] = "0"
    try:
        assert "snapshot" not in page_cache.get("t-flight", lambda: {"v": 2})
    finally:
        os.environ.pop("BRAMBLELOOP_CC_SNAPSHOT_TTL_S")


def _request_latency_with_background(yielding: bool) -> float:
    stop = threading.Event()

    def burn():
        x = 0
        while not stop.is_set():
            for i in range(200):
                x += i * i
            if yielding:
                page_cache.yield_to_requests(every=1)

    workers = [threading.Thread(target=burn, name=f"bg-burn-{k}", daemon=True)
               for k in range(4)]
    [w.start() for w in workers]
    try:
        time.sleep(0.1)
        samples = sorted(_get_ms("/api/cc/demand")[0] for _ in range(5))
    finally:
        stop.set()
        [w.join() for w in workers]
    return samples[len(samples) // 2]


def test_f11_background_work_that_yields_lets_requests_through():
    _client()
    base = sorted(_get_ms("/api/cc/demand")[0] for _ in range(5))[2]
    no_yield = _request_latency_with_background(False)
    with_yield = _request_latency_with_background(True)
    print(f"     /api/cc/demand median: idle {base:.0f} ms, 4 CPU threads {no_yield:.0f} ms, "
          f"4 yielding CPU threads {with_yield:.0f} ms")
    assert with_yield < no_yield, (base, no_yield, with_yield)


if __name__ == "__main__":
    failed = passed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                passed += 1
                print(f"OK   {name}")
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print(f"FAIL {name} {exc!r}"[:800])
    print(f"{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
