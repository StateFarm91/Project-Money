# Independent security review: release candidate 5f18d11

**VERDICT: NO BLOCKER**

Reviewer: W-SECREVIEW, an independent reviewer who did not write any of the code reviewed.
Date: 2026-10-19 (UTC). The review was read-only. Nothing was deployed, no request was sent to
production and nothing was spent.

## Scope

- Base (production): `1b21e81c` (= a25a377 + release record)
- Candidate: `5f18d1189194589291a193d911e88804cda67446` (branch `claude/final-candidate-5f18d11`)
- Diff reviewed: `git diff 1b21e81c 5f18d118 -- brambleloop/src brambleloop/requirements.lock
  brambleloop/requirements.txt brambleloop/Dockerfile ops` (43 files, +2056/−376). `Dockerfile`
  and `ops/` have no changes in this range.
- Focus files: `integrations/etsy_webhooks.py`, `app/main.py` (`POST /api/etsy/webhook`),
  `agents/registry.py`, `gateway/anthropic.py`, `gateway/laura_register.py`,
  `app/command_center/private_context.py`, `static/js/views/laura.js`, `core/db.py`,
  `creative/prospecting.py` (BriefCursor), `creative/reference.py`, `intel/vision.py`,
  `core/fx.py`, `visual/compose.py`, `requirements.lock`, `requirements.txt`.

## Method

1. Read the whole diff by hand. Followed every changed public or owner route and every
   spend path into its callees (`agent_daily_ceiling`, `budget_lock`, `Registry.seed_defaults`,
   `spend_today`, `check_free_of_depiction`, the `creative.reference_reading` job handler).
2. Searched the diff for new route decorators. The only route whose body changed is
   `POST /api/etsy/webhook`. No route was added.
3. Compiled the new DDL and DML against the PostgreSQL dialect: `CreateTable` for both new
   tables, the `BriefCursor` update, and the `detail ->> 'reason'` GROUP BY.
4. Checked the scipy 1.17.1 hashes in the lock against the PyPI JSON API
   (`pypi.org/pypi/scipy/1.17.1/json`). This was a public read and touched nothing in production.
5. Ran the tests in a venv installed with `--require-hashes` from the candidate lock:
   `tests/test_w4_rel2.py` (PASS, 0 failing) and `tests/test_w4_plact.py` (8/8 passed).
6. Ran adversarial probes against file-backed SQLite:
   - `read_body`: chunked oversize → 413 `too_large`; negative or non-integer
     Content-Length → 400; a 5000-digit Content-Length → 400 (it hits Python's int-digit limit
     and comes back as a clean `ValueError`).
   - Signatures `v1,éÿ`, 44×`é`, a lone surrogate, empty, and `v1,` all came back as clean
     401/400 refusals. None produced a 500.
   - Refusal counter: 8 threads × 20 concurrent refusals gave an exact count of 164 (160 plus
     4 earlier). One counter row per reason, and 2 sampled audit rows (1 per reason).
   - `laura_private` budget: 12 concurrent reservations of CA$0.03 against an owner cap of
     CA$0.10 gave exactly 3 granted. Caps of NaN, −1, +inf and `"x"` gave 0 granted. A cap of
     CA$5.00 above the CA$0.50 agent ceiling gave 16 × 0.03 = CA$0.48, so the cap can only
     tighten.

## What holds (verified)

- **HMAC**: the expected MAC is now bytes, and every offered value is encoded and compared
  with `hmac.compare_digest` on bytes (`etsy_webhooks.py:245`). Non-ASCII input mismatches
  instead of raising. The signature is still verified before the body is parsed as JSON. I
  found no bypass, and no timing leak beyond what `compare_digest` already accepts.
- **Bounded storage on the public endpoint**: refusals go into a closed set of reasons,
  and anything outside it becomes `other`. That gives at most 10 counter rows. Audit rows are
  at most 1 per reason per hour, through a conditional-update claim, which is race-safe as the
  probe showed. Legacy rows are aggregated in SQL.
- **Body cap**: an oversized declared Content-Length is refused before any read. A
  streamed body is refused as soon as it passes 64 KiB.
- **Private Laura spend**: `agent_daily_cap_cad` is applied inside `budget_lock`
  (a PostgreSQL advisory xact lock plus a process lock) in the same step as the reservation
  (`gateway/anthropic.py:577`). It can only lower the ceiling. A non-finite or negative cap
  becomes 0. An unregistered agent with a cap fails closed. `daily_authorisation_cad` is also
  min'd with the declared ceiling. `laura_private` has no job types and inherits Laura's
  forbidden combinations.
- **Auth**: `GET /api/cc/private/status` is an existing route under the `/api/cc/*`
  operator gate (owner session). The new `prerequisites` output contains env var **names**,
  booleans, a short commit SHA and a release-record file name. It contains no secret values.
  `laura.js` builds its DOM through `h()`, which uses `textContent`, so there is no new
  innerHTML sink.
- **DB tables**: on PostgreSQL the DDL is valid. The reserved word `offset` is quoted
  (`"offset"`). Both tables use `create_all`/`create(checkfirst=True)`. Neither takes input from
  a request: BriefCursor keys come from code-defined arenas and the refusal reason is a closed
  set. Parameters are bound everywhere, and I found no injection.
- **Dependency**: all 61 scipy 1.17.1 sha256 hashes in the lock match the 61 files
  PyPI publishes exactly (no extra, none missing). The set includes the
  `cp311-manylinux_2_27_x86_64` wheel for the `python:3.11-slim` base. scipy requires
  `numpy<2.7,>=1.26.4`, and the lock pins numpy 2.4.6, which fits. The lock diff has **no
  removed lines**, so no other pin changed. The Dockerfile still runs
  `pip install --no-cache-dir --require-hashes --no-deps -r requirements.lock`.
- **fx**: CAD per USD goes from 1.3986 to 1.4154. Each USD call now reserves more CAD, which
  is the conservative direction. No ceiling changed.
- **vision**: the structured-output schema has `additionalProperties: false` and a closed
  `shot_type` enum. The parser still validates every answer.
- **compose.py**: pure local functions on bytes. No endpoint, no network, no spend. PIL's
  default decompression-bomb guard applies.

## Findings

| ID | Severity | Summary |
|----|----------|---------|
| M1 | MEDIUM | Public webhook runs synchronous DB I/O on the event loop; the refusal path now makes up to 3 transactions on one hot row |
| L1 | LOW | Refusal counter is int4 on PostgreSQL and stops silently on overflow |
| L2 | LOW | Refused reading text from the model still reaches persisted job output through `failed[].why` |
| L3 | LOW | The `current_release_deployed` prerequisite is displayed but does not gate replies |
| I1 | INFO | Same-day spend already billed to `laura` does not count against `laura_private` on deploy day |
| I2 | INFO | Minor `read_body` parsing edges |

### M1 (MEDIUM): synchronous DB work on the event loop of a public endpoint, amplified

- **Where:** `app/main.py:2962-2977` (`async def api_etsy_webhook` calls the synchronous
  `etsy_webhooks.refuse`/`receive` directly); `integrations/etsy_webhooks.py:270-312`.
- **Scenario:** an unauthenticated client floods `POST /api/etsy/webhook` with bad
  signatures. Each refusal now makes 2–3 blocking DB transactions: the bump update, then on
  first sight an insert, then the sample-claim update. All of them run on the event-loop
  thread, and all of them target the **same row** for a given reason. Before this change it was
  one blocking insert. With more than one worker or replica, the UPDATEs on that hot row wait on
  each other's row locks, and each wait blocks the worker's whole event loop. Every other
  request in that worker stalls, including owner Command Center calls. Storage stays bounded,
  so this is about availability, not growth. The sync-in-async pattern was already there for
  `receive`, so this is not a regression of an accepted control and does not block the release.
- **Fix:** wrap `refuse`/`receive` in `run_in_threadpool` (as the `/api/cc` voice route already
  does). Fold the bump and the sample claim into one transaction. Optionally, short-circuit
  counting at a per-process in-memory rate (for example, flush counts once per second) and rate
  limit `/api/etsy/webhook` per IP at the edge.

### L1 (LOW): refusal counter overflow on PostgreSQL

- **Where:** `integrations/etsy_webhooks.py:116` (`count: Integer`, which is int4 on PostgreSQL).
- **Scenario:** after 2³¹−1 refusals for one reason, `count + 1` raises "integer out of
  range". The broad `except` swallows it, so the counter freezes with no signal. Sampled audit
  rows also stop for that reason, because the bump runs first in the same `try`. This needs
  billions of requests, so the practical risk is low. The effect is lost observability, not a
  bypass.
- **Fix:** use `BigInteger` (as part of a migration), or saturate with `LEAST(count + 1, max)`.

### L2 (LOW): refused reading text still persisted via `failed[].why`

- **Where:** `creative/reference.py:468` (new `except ReferenceRefused` branch). Message
  sources: `creative/reference.py:128` (`body[:120]!r`, the model's own text) and `:134`
  (key names the model chose). The persistence path is `runtime/release.py:3002-3005`, which
  writes `out` as audit `detail` and returns it as the job result.
- **Scenario:** a competitor-image reading that is not JSON, or that uses keys outside the
  closed vocabulary, is refused. The new `record_refused_reading` correctly stores only the
  refusal class. But the same run's return value carries up to 200 characters of the refused
  model text, and that is persisted. The new docstring says "a refused reading's text is
  exactly what must not be stored", and that is not yet true on this path. This was already the
  behaviour on the generic `except` path, and the new branch keeps it.
- **Fix:** in both `failed.append` calls, store `kind` (the same classification
  `record_refused_reading` computes) and the exception class name instead of `str(exc)`.

### L3 (LOW): a displayed prerequisite is not enforced

- **Where:** `app/command_center/private_context.py:186` (`current_release_deployed`) compared
  with `:203` (`enabled`) and `gateway/laura_register._reply`.
- **Scenario:** the owner sees "Activation prerequisites: 4 of 5 met" with the release
  prerequisite unmet, but replies are generated anyway (and paid for) once the key, switch, CAD
  figure, provider and agent are present. Spend caps still bind, so this is a mismatch between
  what the UI says and what the code does, not a money bypass. `REPLY_GATED` says replies need
  to run "on a deployed release".
- **Fix:** either AND `rel["met"]` into `enabled` (and check it in `_reply`), or relabel the item
  as informational.

### I1 (INFO): billing identity change on deploy day

- **Where:** `gateway/laura_register.py` (removed `_purpose_committed_today`, `AGENT` changed
  from `laura` to `laura_private`).
- **Note:** private-reply spend already billed to agent `laura` earlier in the deploy's UTC day
  does not count against `laura_private`. Reservations held by the old process do not count
  either. The worst case is one extra day's CA$0.50 for a few hours, inside the unchanged
  monthly ceiling, and only if the register switch (off by default) was already on in
  production. No action is needed. If the switch is on, deploy shortly after 00:00 UTC.

### I2 (INFO): `read_body` parsing edges

- `int()` accepts `1_0` and `+5` as a Content-Length. The ASGI server's HTTP parser rejects
  these before the app sees them, so this is harmless.
- A client disconnect during the stream raises Starlette's `ClientDisconnect`. That is not
  counted as a refusal, and there is nobody left to answer, so it is harmless.

## Verdict

**NO BLOCKER.** I found no auth or HMAC bypass, no secret disclosure, no unbounded storage
growth, no way to exceed a spend cap under concurrency, and no tampered dependency.

I recommend fixing **M1** in the next release (add a threadpool and merge the transactions).
L1, L2 and L3 are small cleanups.
