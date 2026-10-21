# Independent security and integrity review: W4-LISTREADY at b9137b5

- **Reviewed:** `origin/claude/w4-LISTREADY` @ b9137b5.
  - **Diff:** `git diff d45e0333..b9137b55 -- brambleloop/src brambleloop/tests`, 29 files, +2083/−61.
  - **Contents:** the F1–F8 fixes (a46ac23, c97ccf1) and the owner-approved batch-scoped image-review
    spend authorisation. That authorisation is `finance/launch_review.py`, D-W4-LAUNCH-VISION-BATCH.
  - **Also in the diff:** the Command Center activation and Shop Manager readings cards, and the Etsy
    write-path and product-independence tests.
- **Also read:**
  - the earlier review, `INDEPENDENT_SECREVIEW_LISTREADY.md` on `claude/w4-SECREVIEW-LISTREADY`, of d45e033;
  - `research/final_build/w4/LISTREADY.md` at b9137b5 (§8 and §10).
- **Reviewer:** an independent reviewer that did not write this code. This is a review only.
  - Nothing was fixed, deployed, posted or paid for.
  - No secrets were used and no production endpoint was called.
- **Date:** 2026-10-21 (UTC).

## Verdict: **NO BLOCKER**

**The original findings:**
- The BLOCKER (F1) is closed.
- The HIGH (F2) is closed for the sentinel and the publication guard.
- F3–F7 are closed. F8's audit was done.
- Each regression test that claims to reproduce a finding fails on d45e033 and passes on b9137b5.
  I re-ran this myself (see the closure table).

**The spend authorisation:**
- It is atomic, and every cap is enforced in code under the budget lock.
- It reverts by itself when the batch closes. It leaves the CA$100 month and the registry's
  CA$1.00 ceiling unchanged.
- It cannot turn UNKNOWN into PASS.

**New findings:** I found no path that publishes to Etsy past Product Truth, the current-version
check, owner approval or marketplace policy. The most serious new finding is **N1 (MEDIUM)**:
- F2's "newest by version" rule was applied to four readers but not to every reader of "the
  current release";
- one of the readers it missed (`teardown.enforce.current_release`) feeds the `standards_gate`
  inside `for_publish`;
- the out-of-order state that F2 described can still arise.

| # | severity | area | one line |
|---|---|---|---|
| N1 | **MEDIUM** | F2 residual | `teardown.enforce.current_release`, `_targeted_rebuild` and `inventory.chain_evidence` still choose "current" by highest PatternVersion **id**. In an out-of-order state (still reachable), `for_publish(1.1.0)` judges teardown requirements on self-audits bound to 1.0.0, and stale 1.1.0 artefacts are "rebuilt" from 1.0.0 |
| N2 | LOW | spend batch | The one-shot batch can complete with CA$0 committed and nothing reviewed (vision gate closed, or every call refused), and it then cannot be re-activated. A release whose batch build fails before review stays `queued` until expiry |
| N3 | LOW | F8 residual | No write path exists, but a **live** listing of a superseded release stays live through Etsy auto-renew. Since R1 its artefacts read SUPERSEDED, so they raise no halt, and nothing tells the owner |
| N4 | INFO | spend batch | A batch run is a full `assets.build`: it re-renders frames and re-queues the downstream chain. The scope check fails closed if the bytes change |
| N5 | INFO | spend batch | While the batch is open, batch spend counts against `quality_director`'s agent-day. Its non-batch calls stay at CA$1.00, so they are refused for the rest of that UTC day (correct, but it starves other work) |
| N6 | INFO | registry | The ceiling is unchanged. `assets.launch_review` was added to `quality_director`'s `allowed_job_types`, `JOB_CLASS`, `OWNER_ONE_SHOTS` and `JOB_BANDS` |
| N7 | INFO | spend batch | `grant_in` trusts any `assets.build` job whose inputs carry `launch_review_batch`. It is not bound to the job the batch enqueued. No route accepts arbitrary job inputs, and the caps still bind |
| N8 | INFO | API | `GET /api/cc/launch-review` writes: it creates tables and may close the batch with an audit row. `activate` checks, then inserts, with no unique constraint; the nonce and step-up make a double insert impractical, and the caps hold even then |
| N9 | INFO | tests | The F8 tests match call sites by method name in the AST. An aliased, `getattr` or `partial` call would not be listed. The runtime `_authorise_write` boundary is still the real control |

---

## 1. Per-finding closure table

"Fails on d45e033" means I copied b9137b5's test file into a worktree of d45e033 and ran it there,
at nice 19. The results:
- `test_w4_listready`: 15 OK, 9 FAIL on d45e033; 24/24 on b9137b5;
- `test_w4_owner_observations`: 0 OK, 3 FAIL on d45e033; 3/3 on b9137b5.

| # | sev | closed? | how verified | regression test fails on d45e033? |
|---|---|---|---|---|
| F1 | BLOCKER | **Closed** | See the F1 notes below the table | **Yes**: `test_live_marketing_copy_written_from_an_older_release_is_stale_not_superseded` and `test_no_unversioned_artefact_is_ever_superseded` both FAIL on d45e033 with an AssertionError |
| F2 | HIGH | **Closed for the named callers.** The residual is N1 | See the F2 notes below the table | **Yes**: `test_newest_is_the_highest_certified_version_not_the_last_row` FAILs on its assertion. `test_versions_that_cannot_be_ordered_…` FAILs too, but only with an AttributeError (`newest_version` did not exist), so on d45e033 it does not exercise the behaviour; the newest-version test does |
| F3 | MEDIUM | **Closed** | `retry_halted` calls `design_check` (`release_recovery.py:98-123`): it compares the recorded CIR with `_engineered_cir(slug)` by version, fingerprint and JSON-normalised content. On a mismatch it records `design_moved` and does not retry. `newer_certified` skips the retry with `superseded_by_newer`. `seed_launch0` does not seed a release below a certified one | **Yes**: `test_f3_…design_moved…` and `test_f2_f3_…newer_certified…` FAIL (old code retried) |
| F4 | LOW | **Closed** | `staleness()` now requires `and not policy` for `outstanding_only_marketing` (`release_gates.py:1272-1275`) | **Yes**: `test_f4_…` FAILs |
| F5 | LOW | **Closed** | See the F5 notes below the table | **Yes**: both `test_f5_…` FAIL |
| F6 | LOW | **Closed** | See the F6 notes below the table | Coverage only, as declared: passes on both |
| F7 | LOW | **Closed** | See the F7 notes below the table | **Yes**: all 3 `test_w4_owner_observations` tests FAIL on d45e033 |
| F8 | INFO | **Audit done.** The residual is N3 | See the F8 notes below the table | Audit, as declared: passes on both. It guards against regression only |

**F1 notes.**
- `built_from_version` now returns a version only for an explicit `slug@version` key
  (`ops/artefacts.py:552-569`).
- The fingerprint match for unversioned keys was deleted.
- Re-ran the earlier review's appendix A on b9137b5. Marketing copy written from 1.0.0, after
  1.1.0 is certified:
  - verdict `stale`;
  - `publication_blocked ['hex']`;
  - `publication_halted` True;
  - the rebuild graph gives `may_publish False` with `outstanding ['marketing_asset:hex:pin:…']`;
  - `staleness.blocks` True.

**F2 notes.**
- `newest_version` uses integer tuples and fails closed on unorderable versions. It is used in:
  - `current_from_db` (`artefacts.py:934-961`);
  - `_superseded_lookup` (`:651-664`);
  - `superseded_release` (`release_gates.py:1376-1384`);
  - `retry_halted` and `seed_launch0` (through `newer_certified`).
- Re-ran appendix B (rows inserted 1.1.0, then 1.0.0):
  - the 1.1.0 PDF reads `fresh`;
  - `superseded_release(1.1.0)` is False;
  - `superseded_release(1.0.0)` is True.
- **Not migrated:** the other "current release" readers (N1).

**F5 notes.**
- **Before queueing:** `certify_in_flight` is checked before a retry is queued
  (PENDING/RUNNING/FAILED, where FAILED means "will retry"; DEAD and CANCELLED are excluded).
- **At certify time:** `duplicate_certification` in `handle_certify` (`pipeline.py:905-916`). It:
  - runs **after** the Gate E halt check, which is unchanged;
  - stops only on an identical stored CIR and identical `DOC_VERSION`, with a `gate.certified`
    audit from another job after this job was created;
  - treats unreadable state as not a duplicate.

**F6 notes.**
- `test_f6_chain_rebuild_redrafts_a_changed_design_and_not_an_unchanged_one` is behavioural.
- The `test_etsy_surfaces` assertion now calls `orders_ingest.gate(db)` and checks its `missing`
  text. That makes the test stronger, not weaker.

**F7 notes.**
- `POST /api/etsy/shop-observation` (operator credential) returns 403 `OWNER_SESSION_REQUIRED`
  for `messages` and `legal_and_tax` (`estate_api.py:77-83`).
- The new `POST /api/cc/etsy/shop-observation` sits behind the default `/api/cc` gate (owner
  session, same-origin, CSRF HMAC, single-use nonce and timestamp: `auth.gate`) plus
  `require_stepup`.
- `recorded_by=actor(request)` comes from the signed-in session, not from the body.
- A future `decided_on` is refused (`shop_observations.py:131-134`).
- The other pages stay on the operator route, as LISTREADY §10 records.

**F8 notes.**
- I checked `EtsyClient`'s seven mutating methods by hand. Every public writer calls
  `_authorise_write`, and the private writers are reached only from public writers.
  - `activate` needs the phase, the grant and a per-call launch authorisation.
  - `update_listing` refuses `price` and `state`.
- **Call sites:**
  - `store.publish`, through `_publish_guarded` and then `_publish_and_read_back`, and
    `store.activate` both run `_release_gates`, which calls `for_publish`.
  - `store.activate` binds the listing by `slug` and `version` from the same inputs that it gates.
- **No other Etsy write route was found:**
  - no other `transport.request` with a write method;
  - `core/offsite.py`'s PUT and DELETE go to backup storage;
  - `etsy_oauth`'s POST is the token exchange.

---

## 2. New findings

### N1: MEDIUM: "current release" is still the highest PatternVersion id in three readers; one feeds `for_publish`

**Where:**
- `teardown/enforce.py:196-211`: `current_release` uses `order_by(desc(PatternVersion.id))`.
  It is used by:
  - `bind_self_audit` (`:214-227`);
  - `our_scores_detail` (`:252`);
  - `check` (`:380-387`).

  `check` is called from `publish/release_gates.py:1527` (`standards_gate`), which `for_publish`
  runs.
- `runtime/release.py:4611-4612`: `_targeted_rebuild` takes `pv` (version, release hash and
  `cir_json`) from the highest id.
- `products/inventory.py:165`: `chain_evidence` picks the highest id when no version is given, then
  calls `for_publish`.
- Display-only readers do the same. They are not security-relevant:
  - `app/command_center/readers.py:210`, `approvals.py:205`, `ask.py:109`;
  - `seasonal/benchmark_matrix.py:114`;
  - `teardown/lab.py:216, 482, 515`.

**The out-of-order state is still reachable.** F2 was fixed by changing what "newest" means. It was
not fixed by stopping an older version being certified after a newer one:
- `_version_conflict` (`runtime/pipeline.py:1313`) only compares the **same** version.
- `handle_certify` has no "below the newest certified version" refusal.
- The F2 and F3 guards cover only `retry_halted` and `seed_launch0`. They do not cover:
  - a normal `certify:<slug>:<version>…` job for 1.0.0 that was queued before 1.1.0 certified, the
    review's original "queued together, run in any order" case;
  - `_targeted_rebuild`'s own `rebuild-cert:` job;
  - a code rollback.

**Scenario (reproduced on b9137b5; see the appendix).** Rows were certified in the order 1.1.0, then
1.0.0.
- `superseded_release` says the newest is **1.1.0**, so only 1.1.0 may publish. This is correct.
- `enforce.current_release` says **1.0.0**.
- A self-audit recorded now is stamped as bound to 1.0.0's hash, and `our_scores_detail` returns it
  as the current score.
- So `for_publish(hex, 1.1.0)` evaluates its binding teardown requirements on evidence bound to a
  different release. This is the defect C-66/C-67 exists to prevent: an audit read for a release
  it never saw.
- Every new audit of the real newest release is also mis-stamped to 1.0.0. If the order later
  corrects, those audits all go stale at once.
- `_targeted_rebuild` takes `pv` = 1.0.0 for stale **1.1.0** artefacts. It enqueues `assets.build`
  for 1.0.0, or `gate.certify` with **1.0.0's CIR** (`rebuild-cert:`). The 1.1.0 rows never clear,
  and after `REBUILD_VERIFY_ATTEMPTS` a halting `REBUILD_INCOMPLETE` P2 is opened.
  - This fails closed, but it stalls the product.
  - It also re-certifies the older release, which keeps the bad order in place.
- `inventory.chain_evidence` reports 1.0.0 as "the release". Its `for_publish` call then refuses it
  as superseded, so it reports a false refusal: fail-closed but misleading.

**Why it is not a BLOCKER:**
- A non-newest release still cannot publish, because `superseded_release` refuses it.
- The other `for_publish` gates are evaluated against the requested version.
- The state needs a stale older-version certify to run after a newer one.

**Why it is not LOW:** a gate inside `for_publish` can pass on another release's evidence, and the
state can be reached without any fault.

**Fix:**
1. Add one helper, for example `ops.artefacts.newest_certified(session, slug) -> PatternVersion | None`
   (newest by `version_key`, fail closed). Use it in `enforce.current_release`, `_targeted_rebuild`
   and `inventory.chain_evidence`, and preferably in the display readers too.
2. Remove the state at its source. `handle_certify` should refuse, after the Gate E check, any
   `cir.version` whose `version_key` is below the product's newest certified version. It should
   audit `gate.certify_older_than_newest`, the way `retry_halted` records `superseded_by_newer`.
3. Add a test that inserts 1.1.0 then 1.0.0 and asserts all of these:
   - `enforce.current_release(...)["version"] == "1.1.0"`;
   - `_targeted_rebuild` targets 1.1.0;
   - certifying 1.0.0 after 1.1.0 is refused.

### N2: LOW: the one-shot batch can be consumed with nothing reviewed

**Where:**
- `finance/launch_review.py:168-207` (`activate` has no `image_vision` check);
- `:253-273` (`close_if_due`: COMPLETED when every release is `done` or `interrupted`);
- `:422-423` (`review_finished` always sets `done`);
- `runtime/release.py:509-528`.

**Scenario (reproduced).**
1. The owner activates.
2. Each batch `assets.build` runs `_review_frames`.
3. With the `image_vision` gate closed, or with every call refused (for example, the company month
   is full), no call is reserved. Every frame is `unreviewed`, and the release is still marked
   `done`.
4. The batch closes as `completed` with **CA$0.00 committed**.
5. `activate` then refuses with "already activated; it runs once".

In my probe: status `completed`, committed 0.0, and re-activation refused.

This is spend-safe and gate-safe: UNKNOWN stays UNKNOWN. But the owner's single approval is used
up silently, and the card shows "completed". Recovering needs a code change, because `BATCH_ID` is
fixed.

**Related.** If a batch `assets.build` (with `max_attempts=1`) fails before `review_started`, its
release stays `queued`. The `assets.launch_review` run job has a fixed key and `max_attempts=1`, so
it never runs again. The `interrupted` branch of `run()` is therefore unreachable in practice, and
the batch can only close by expiring after 14 days.

**Fix:**
- Refuse activation (and show the reason on the card) unless `gates_now(... "image_vision")` is
  open.
- In `review_finished`, mark a release `done` only when at least one batch call was reserved for
  it. Otherwise return it to `pending` with the reason.
- Show "frames reviewed N of M" on the card.
- Optionally, let a later step-up "resume" re-enqueue the run job for `pending` releases. It would
  stay under the same caps and expiry.

### N3: LOW: a live listing of a superseded release is invisible (the F8 residual)

**Where:**
- `ops/artefacts.py:600-611`: a superseded release raises no halt, and its incident is closed;
- `publish/release_gates.superseded_release`, which guards only new publication and activation.

LISTREADY §10 states that there is no renewal write and that listings use Etsy's own renewal
setting.

**Scenario:**
1. 1.0.0 is live on Etsy, with `should_auto_renew` set.
2. 1.1.0 is certified.
3. 1.0.0's PDF, certificate and frames now read SUPERSEDED, so they raise no incident, and any
   earlier stale incident is closed as "superseded, not stale".
4. Nothing deactivates 1.0.0, re-lists it as 1.1.0, or raises an owner item.
5. Etsy keeps selling 1.0.0, and renews it at US$0.20 every four months.

Before R1, the same artefacts would have raised halting P1s, which at least made the condition
visible.

**Exposure today:** none. Production is in SHADOW and has 0 listings.

**Fix:** a sentinel or estate check. For each `Listing` with `state == "active"` whose version is
not `superseded_release`'s newest, raise a P2 owner-queue item "superseded release live on Etsy".
The owner decides: update in place or deactivate. Before LIMITED PRODUCTION, also wire
`for_publish` into `commerce/listing_rollback.execute`, as LISTREADY already notes.

### N4: INFO: a batch run is a full rebuild

`handle_launch_review` re-enqueues the last DONE `assets.build`'s inputs with the batch key
(`launch_review.py:426-463`). Those jobs re-render and re-store every frame, PDF and render. On
success they enqueue `pricing.position` and the rest of the chain (`release.py:596-600`).

It is safe:
- the batch's frame scope is matched by sha256, so changed bytes are refused;
- in SHADOW nothing publishes;
- the payload passed downstream does not carry `launch_review_batch`.

But it is more work than "review the stored frames". If a render is not byte-deterministic, the
whole release is refused and then marked `done`, which is the N2 path.

### N5: INFO: the batch shares `quality_director`'s agent-day

For a batch call, the agent-day check is raised to CA$8.00, but `spent_today_cad` includes all of
the agent's spend (`gateway/anthropic.py:608-645`). Non-batch calls still read CA$1.00 and include
the batch's spend. So once about CA$1 of batch calls has been reserved in a UTC day, every other
`quality_director` call that day is refused.

This is correct: the registry ceiling holds for non-batch work. But it pauses that agent's other
duties (for example `gate.lanes`) on review days. Worth telling the owner; no code change is
needed.

### N6: INFO: registry entries added (the ceiling is unchanged)

`agents/registry.py:168-172` adds `assets.launch_review` to `quality_director.allowed_job_types`.
The `daily_cost_ceiling_cad=1.0` is unchanged. The same job type is also added to:
- `authority/classes.py` `JOB_CLASS` (build);
- `autonomy/map.py` `OWNER_ONE_SHOTS`;
- `swarm/orchestrate.py` `JOB_BANDS`.

`monthly_ceiling_cad` is not touched. The agent could enqueue the job itself, but `run()` refuses
unless an owner-activated batch is OPEN. Read "no change to the registry" as "no change to any
ceiling", which holds.

### N7: INFO: the batch grant is not bound to the batch's own job

`scoped_frames` and `reviewing()` are entered for any `assets.build` whose `inputs` carry
`launch_review_batch` (`release.py:508-515`). `grant_in` checks the batch, the release, the frame
set and the caps, but not the job's identity.

I found no route that enqueues a job with caller-chosen inputs (the `job_type` field at
`api.py:1106` is an owner grant, not an enqueue). Chain code re-enqueues `assets.build` from
`outputs`, never from `inputs`. So this is reachable only by code or database access, and the spend
is still bounded by CA$7.07, the scope and the per-release call allowance.

**Hardening:** in `scoped_frames`, also require
`ctx.job.idempotency_key == f"{BATCH_ID}:{slug}@{version}"`.

### N8: INFO: API details

- **`GET /api/cc/launch-review` writes:**
  - `ensure_tables` creates tables (DDL);
  - `state()` → `close_if_due` can close the batch and add a `launch_review.closed` audit row.

  This is harmless, but a GET should not write. Closing would happen anyway on the next batch call.
- **`activate` checks for an existing batch in one session and inserts in another**, and
  `batch_id` is not unique. Two concurrent step-up POSTs could insert two OPEN rows. This is
  impractical: each POST needs a fresh single-use nonce. The caps still hold, because `_committed`
  and `_today` sum by the `batch_id` string. A unique index on `batch_id` would close it.

### N9: INFO: the F8 tests are static

`test_f8_every_etsy_write_call_site_is_classified…` finds call sites by `ast.Attribute` name, so it
misses these forms:
- `getattr(client, "create_draft")(...)`;
- `functools.partial`;
- a method alias.

It also exempts every `.publish(...)` whose receiver contains `bus`, and every `.activate(...)`
whose receiver contains `launch_review`.

It is a good tripwire. The control that matters is `EtsyClient._authorise_write` at runtime, and
that is sound.

---

## 3. The spend authorisation: checklist

| property | result | where |
|---|---|---|
| Atomic reservation | **Yes**. `grant_in` reads and `record_in` writes in `locked_session`, inside `budget_lock` (process RLock plus `pg_advisory_xact_lock` or SQLite `BEGIN IMMEDIATE`), in the same step as `reservations.reserve_in` | `gateway/anthropic.py:585-596, 663-670` |
| CA$100 month, first and unchanged | **Yes**: checked before `grant_in`. `monthly_ceiling_cad` is not in the diff | `:552`; test `…company_month_still_binds…` |
| Batch total CA$7.07 | **Yes**: `committed + estimate > total + 1e-9` refuses. Committed counts reserved calls at the padded estimate, never at less | `launch_review.py:371-374` |
| Batch day CA$8.00 | **Yes**, `_today` from 00:00 UTC. It never binds before the total, since 8.00 > 7.07, which matches the approval | `:375-378` |
| Agent-day raised for batch calls only | **Yes**: `permission` is replaced in a local dict for this call. The registry is not written. `agent_daily_cap_cad` (W4-PLACT) can still narrow it | `gateway/anthropic.py:619-625` |
| Out-of-scope frames or releases refused | **Yes**: the frame set must equal the activation scope by sha256 for that release, and there is a per-release call allowance (2 per frame, plus 1 for the hero). Agent or purpose mismatch → `None` → registry CA$1.00 | `launch_review.py:343-370` |
| Revert on completion, expiry and exhaustion | **Yes**. These are status transitions in `close_if_due`, re-read under the lock on every call, and audited. Afterwards `grant_in` refuses and non-batch calls never saw CA$8.00. But see N2: "completion" can mean nothing was reviewed | `:253-273, 352-354` |
| UNKNOWN never PASS | **Yes**: a refusal raises `BudgetExceeded` inside `describe_image`, `inspect_image` and `identify_at_grid`, and `_review_frames` records `unreviewed`/`unjudged`. `frame_review_state` and the gate are unchanged | `release.py:1655-1660, 1677-1680`; test `…refused_review_call…never_passed` |
| No sends after refusal | **Yes**: the refusal is raised before any provider call | `check_budget_cad` |
| Step-up and CSRF on activation | **Yes**: the `/api/cc/*` default gate (session, same-origin, CSRF HMAC, nonce and timestamp) plus `require_stepup("launch_review.activate")`. `activate()` also refuses `stepped_up=False` | `api.py:658-684`, `auth.py:740-770` |
| Concurrency of review calls | Sequential in the worker thread. A `contextvars` value is set around `_review_frames` only, with no thread pool inside, so it neither leaks nor drops | `release.py:1601-1712` |
| Global ceiling or registry changed | No ceiling changed. Job-type registration was added (N6) | |

---

## 4. Newest-version selection: every caller

| caller | by version? | security-relevant |
|---|---|---|
| `ops.artefacts.current_from_db` | yes (F2) | sentinel |
| `ops.artefacts._superseded_lookup` | yes (F2) | sentinel |
| `release_gates.superseded_release` | yes (F2); unorderable → refuse | **publication** |
| `release_recovery.newer_certified` (`retry_halted`, `seed_launch0`) | yes; unorderable → counts as newer (skip) | recovery |
| `teardown.enforce.current_release` | **no, by id** (N1) | **publication** (`standards_gate`) |
| `runtime.release._targeted_rebuild` | **no, by id** (N1) | rebuild, and certify of an older CIR |
| `products.inventory.chain_evidence` | **no, by id** (N1) | diagnostic; refuses closed |
| CC `readers`, `approvals`, `ask`; `seasonal.benchmark_matrix`; `teardown.lab` | by id | display or analysis |
| `commerce.ranking_readiness._latest_version` | by `Listing.id` | display |

---

## 5. Weakened tests

None found.
- `test_etsy_surfaces.py:542-555`: a source-text check was replaced with a behavioural check.
  Stronger.
- `test_w4_listready.py`: `handle_certify` calls were moved into `_certify()`, which also marks the
  job DONE. This is needed because `certify_in_flight` now counts pending jobs; no assertion was
  dropped.
- The old F1 test, which asserted the misclassification, was replaced, as the review asked.
- The `cc_mock` fixtures only add the card's route and check.

## 6. Tests run (nice 19; local venv from `requirements.txt`, with fastapi and starlette pinned to `requirements.lock`)

| suite | b9137b5 | d45e033 + b9137b5's test file |
|---|---|---|
| test_w4_listready | 24/24 | 15 OK / 9 FAIL (the F1, F2, F3, F4 and F5 tests) |
| test_w4_owner_observations | 3/3 | 0 OK / 3 FAIL |
| test_w4_launch_review | 13/13 | n/a (new module) |
| test_w4_launch_review_card | 7/7 | n/a |
| test_etsy_surfaces | 53/53 | — |
| test_artefacts | 23/23 | — |
| test_cert_publish_gates | 18/18 | — |
| test_k8_shop_cx | 17/17 | — |
| test_rebuild_graph | 10/10 | — |
| test_w4_firstsale2_surfaces | 7/7 | — |

**Not run, as instructed:** test_product_run, test_acceptance_gates and test_cert_wiring.

---

## Appendix: reproduction (from `brambleloop/`, `PYTHONPATH=src:tests`, with the branch's own test helpers)

```python
import test_w4_listready as T
from sqlalchemy import select, desc
from brambleloop.ops import artefacts as P, rebuild_graph
from brambleloop.publish import release_gates as RG
from brambleloop.gates.incidents import IncidentTracker
from brambleloop.core.models import PatternVersion, Product, TeardownFinding
from brambleloop.teardown import enforce
from brambleloop.products import inventory

# A) original F1, now closed
db = T._db()
T._pv(db, "hex", "1.0.0", {"rows": 12, "yards": 100}, "a" * 64)
T._record_from(db, "hex", "1.0.0", cls="marketing_asset",
               key=P.marketing_key("hex", "pin", "Hex: 100 yards"))
T._pv(db, "hex", "1.1.0", {"rows": 14, "yards": 140}, "b" * 64)
T._sentinel(db)                          # stale, publication_blocked ['hex']

# B) original F2, now closed for the guard; N1, the same state through the other readers
db3 = T._db()
T._pv(db3, "hex", "1.1.0", {"rows": 14}, "b" * 64); T._record_from(db3, "hex", "1.1.0")
T._pv(db3, "hex", "1.0.0", {"rows": 12}, "a" * 64)
RG.superseded_release(db3, slug="hex", version="1.1.0")   # superseded False, newest 1.1.0
enforce.current_release(db3, "hex")                       # version '1.0.0'   <- N1
inventory.chain_evidence(db3, "hex")["release"]           # version '1.0.0'   <- N1
with db3.session() as s:
    f = TeardownFinding(benchmark_ref="brambleloop:hex", dimension="pdf", score=5.0,
                        mechanism="m", improvement="i", detail={})
    s.add(f); s.flush(); fid = f.id
enforce.bind_self_audit(db3, [fid], "hex")                # stamped to 1.0.0
enforce.our_scores_detail(db3, "hex")                     # read as current for the 1.1.0 publish
```

Observed on b9137b5:

```
A verdicts: [('hex:pin:43d36b484a4e94bf', 'stale')] blocked: ['hex']
A halted: True
A rebuild graph may_publish: False outstanding: ['marketing_asset:hex:pin:43d36b484a4e94bf']
A staleness blocks: True
B verdicts: [('hex@1.1.0#pdf-us', 'fresh')]
B superseded(1.1.0): False
B superseded(1.0.0): True
N1 teardown.enforce.current_release: {'release_hash': 'aaaa…', 'version': '1.0.0'}
N1 _targeted_rebuild's release query picks: 1.0.0
N1 inventory.chain_evidence release: {'version': '1.0.0', 'certified': True, 'release_hash': 'aaaaaaaaaaaa'}
N1 self-audit bound to: 1.0.0 | applies to the publish check: {'dimension:pdf': {'score': 5.0, 'finding': 1, 'release_hash': 'aaaa…'}}
N1 publication target (superseded_release newest): 1.1.0
```

**N2 probe** (`test_w4_launch_review` helpers):
1. Activate.
2. For every release, call `review_started`, then `review_finished(unreviewed=all)`, with no call
   reserved.

The result is `status completed | committed 0.0`, and re-activation gives
`launch_image_review_2026_10 was already activated; it runs once`.
