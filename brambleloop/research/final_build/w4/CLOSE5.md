# W4-CLOSE5

Branch `claude/w4-CLOSE5`, based on `origin/claude/w4-INTEG3` at 364ade0. Production is b931d17
(SHADOW). This branch makes no deploys, no production writes and no spend.

## 1. Security review of 324927f, R1 (LOW): FIXED, dev-proven

**Finding:** an unauthenticated refusal flood on `/api/etsy/webhook` could take the shared
AnyIO threadpool tokens (40 per process, shared with about 187 sync routes) and the DB pool
(5 + 10 overflow).

**Fix:**
- `integrations/etsy_webhooks.py`: `WebhookGate` / `GATE` gives the webhook its own
  `anyio.CapacityLimiter` with `WEBHOOK_SLOTS = 4`, so it never uses the default limiter.
  Admission is non-blocking (`threading.BoundedSemaphore.acquire(blocking=False)`). When the
  gate is saturated, the route returns `None` at once and runs no thread and no DB work.
  `busy()` returns a static 503 with `Retry-After: 5`. Etsy retries a 5xx, so a real delivery
  that is shed is not lost. `summary()["gate"]` exposes in-process counters
  (`slots`, `in_flight`, `admitted`, `shed_busy`) without a DB read.
- `app/main.py` `api_etsy_webhook`: `refuse` and `receive` run through `gate.run(...)`. A
  slot is taken only after the capped async body read, so a slow client cannot hold one.

**Tests:**
- `tests/test_w4_close5_r1.py`, 4 tests:
  - a private limiter is used (the default limiter's borrowed tokens do not change);
  - the 4th call is shed in under 50 ms, and its work never runs;
  - a slot is released when the work raises;
  - `slots < QueuePool pool_size (5)`;
  - the route answers 503 + Retry-After with `refuse`/`receive` never called and the refusal
    counters unchanged, then recovers (401 counted, 202 accepted).
- `tests/test_w4_integ3_secfixes.py::test_m1_...threadpool` is now **strengthened**: it
  requires `gate.run` and forbids `run_in_threadpool` in the route.

Production evidence is still needed, so this is dev-proven and awaiting deploy.
