# Independent security review: W4-AGENTS at b199cdb

- **Reviewer:** an independent Claude Code context. It did not write this code. It reviewed and reported only; nothing was fixed.
- **Date:** 2026-10-26 (UTC).
- **Scope:** `git diff a14c9ef8..b199cdb1 -- brambleloop/src brambleloop/tests` on `origin/claude/w4-AGENTS` (31 files, +2085/−42).
- **Read alongside it:**
  - the prior review, `INDEPENDENT_SECREVIEW_AGENTS_a14c9ef.md` (from `claude/w4-SECREVIEW-AGENTS-a14c9ef`);
  - `research/final_build/w4/AGENTS.md` and `DEPARTMENTS.md`;
  - DECISION_LOG entries D-W4-AGENTS-M2R and D-W4-AGENTS-L1-DEFER.
- **Rules followed:** no network beyond installing the locked dependencies, no Etsy calls, no paid calls, no secrets, no deploys. Every suite ran at `nice -n 19`, one at a time, in a scratch venv built from `requirements.lock` (there is no `requirements-test.lock`; `httpx` was added for `TestClient`).

### Commits in the range

`git log a14c9ef8..b199cdb1`:

| Commit | Content |
|---|---|
| dea65bd | C2: F-217 identity subscores, F-744 model evidence ledger, F-738 promotion comparator, F-747 portable identity bundle |
| 347f0c5 | The L-2 fix from the **b5226f7** review: the storefront preview shows and binds the live text it replaces |
| 6ea10a5 | C3: F-527 brand asset health, F-775 cross-sell graph, F-113 salvage re-gate |
| d118a14 | Build 2 #94 creativity capability scorecard |
| 3ace401 | WIP: shared-contract registry and pins (F-456/F-482), "tests to follow" |
| 6e9fc7f | M-2R fix |
| b199cdb | Fixes for the a14c9ef review's L-2, L-3, L-4, L-5, I-3 and I-4 |

The brief expected the quality sweep, `cir.revise`, the competitor snapshot and the family engine to be in this range, but they are **not**. They landed before a14c9ef and were covered by the prior review. This range has only their L-fixes. dea65bd and 347f0c5 *are* in the range, but they contain the C2 visual work and the storefront preview binding. Both were reviewed here.

The commit range also has a naming collision. "L-2" in b199cdb is the a14c9ef review's `%policy%` collision. "L-2" in 347f0c5 is the b5226f7 review's DIFFERS-overwrite preview. Both were reviewed.

## Verdict

**PASS for shipping b199cdb with every write flag OFF and SHADOW on. There are no Critical, High or Medium findings.** M-2R is closed. Three Low findings remain. None of them is reachable in SHADOW or in today's single-container deployment, and none can write to Etsy, a product or a listing.

| # | Question | Result |
|---|---|---|
| 1 | Is M-2R closed? Can a job, a worker path or a non-Command Center route mint or forge a grant? Can the context leak? | **Closed.** In today's deployment (`BRAMBLELOOP_EMBEDDED_WORKER` unset, so `1`) nothing can sign: `_seal` refuses before it reads the key, and `runner.start` scrubs the key from the environment. A separate worker marks itself and scrubs the key. Minting also needs the owner-request ContextVar, and only the Command Center action route sets it. The ContextVar does not leak: probed across requests, threadpool calls, child threads and after the `with` block exits. The residual risk applies only after the service split (I-2). |
| 2 | Can F-113 or anything else new change, retire, delist or delete a product, listing or asset? | **No.** Every new handler writes only an `OperatingReading`, audit rows, or (quality sweep) resolves its own P2 `quality.reverify:*` incidents. Nothing reads the salvage, cross-sell, asset-health or scorecard readings to act on them. `store_readiness` now opens, closes and reopens only `OwnerAction` rows. |
| 3 | Any new paid, Etsy-write, publication or outward path? | **None.** The four new job types are class R or O (research or observe), none of them protected, all at CA$0. `store.update` gained only an additional hold. `image_bench` gained only a dictionary field. |
| 4 | Do UNKNOWN or UNMEASURED readings ever count as PASS or 0? | **Mostly no, with four narrow exceptions:** L-1 (store.update compares UNKNOWN with UNKNOWN and STALE with STALE as "unchanged"), L-2 (salvage: an unreadable diversification reads PASS, and an unreadable radar portfolio reads FAIL), I-1 (an UNKNOWN check counts as "run" for freshness, though never as a pass) and I-6 (scorecard: a period with unknown orders adds 0 orders once another period's orders are known). None of them gates a write. |
| 5 | Was any test weakened? | **No.** The rewritten `test_agent_doable_store_cards_are_superseded_not_asked` is stricter (details below). Every other edit is additive or stricter. |
| 6 | Do the competitor snapshot and the cross-sell graph keep competitor text, URLs and images out? | **Yes.** The snapshot carries an alias and allowlisted labels only, and `_assert_no_content` now checks the inner values. The cross-sell graph reads only our own rows (certified CIRs, the radar POOL seeds, learn lessons, storefront sections). See I-4 for the strength of the alias. |

## 1. M-2R (closed)

**Verified in code:**
- **`_seal` refuses first** (`ops/storefront_authority.py`, `signing_refusal`). It refuses when either:
  - `_JOB_PROCESS["is"]` is set, or
  - `os.environ.get("BRAMBLELOOP_EMBEDDED_WORKER", "1") == "1"`.

  The second check is the same expression `app/runner.py:373` uses to decide whether to start the embedded threads, so the two cannot disagree. Probed: unset or `"1"` refuses; `"0"`, `"true"` and `" 1"` allow signing, and none of those values starts the embedded worker.
- **Startup scrub.** `runner.start` calls `mark_job_process()` after its own early-return check and before any thread starts, and `worker_entry.main` calls it first. The call pops `BRAMBLELOOP_STOREFRONT_SIGNING_KEY` from the environment. The mark is permanent for the process, so putting the key back does not help (pinned by `test_m2r_worker_startup_scrubs_the_key_and_the_process_never_signs_again`).
- **No other job runner.** `Worker(` is constructed only in `app/runner.py` and `app/worker_entry.py`. The autonomy and Laura proofs run `runner.start` in a child process (CLI only), which marks itself. No web route runs handlers inline. The Command Center refresh threads (`company.py`, `first_sale.py`, `launch_packet.py`, `owner_store.py`) are not job handlers and do not inherit the ContextVar: plain `threading.Thread` does not copy context on Python 3.13, and this was probed.
- **The owner-request context.**
  - `approve` and `rebase` call `_require_owner_request()`, which rejects an empty id (probed).
  - The only setter is `api.py:808-817`. It runs after the session/CSRF/nonce router gate and after `require_stepup` for `storefront.approve` and `storefront.rebase`.
  - `run_in_threadpool` (anyio 4) copies the context into the worker thread for that one call, and `reset(token)` runs in `finally`.
  - Probe result: the value is visible inside the threadpool call, and is `None` in a child thread, after exit in the same task, in 20 concurrent sibling requests, and on the main thread.
- **The signed row** now records `owner_session`.

**Tests:**
- `test_m2r_a_job_in_the_embedded_worker_cannot_mint_a_grant` drives a real `Worker.run_once` with the key set and a *forged* context. It is refused and no APPROVED row is added.
- The AST scan now covers all of `src/brambleloop` and includes `LEDGER`, `_seal`, `owner_request` and `_JOB_PROCESS`.
- The M-1 HTTP route tests still record a grant through `TestClient`. That proves the ContextVar reaches the threadpool rather than failing every legitimate approval.
- `test_w4_agents_secfix`: 11 OK.

**Consequence, as DECISION_LOG D-W4-AGENTS-M2R states:** while the single container runs the embedded worker, no storefront grant can be minted, so every storefront write stays held. The storefront write path cannot be reached in today's deployment, whatever the flags say.

## 2. Findings

### L-1 (Low): `store.update` checks the replaced text against our last *stored* reading, not the live shop; UNKNOWN and STALE values compare equal

- **Where:**
  - `runtime/storefront_ops.py:119-133` (`_replaced_since_approval`);
  - `ops/storefront_authority.py:204-226` (`live_replaced`);
  - the claim in AGENTS.md §6 L-2 ("compares the granted `replaces` with the live shop now").
- **What:**
  - `live_replaced` reads `live_state.snapshot(db)`, which is the newest stored getShop reading (FRESH up to 7 days, then STALE) or an owner observation. It does not read the shop.
  - The execution check compares only `live_value`. When both sides are `"UNKNOWN"`, or both carry the same STALE value, it treats the text as unchanged.
- **Scenario:**
  1. After the service split, the owner approves a DIFFERS announcement proposal against a getShop reading taken 2 days earlier.
  2. One hour later the owner edits the announcement by hand in Shop Manager.
  3. No `store.shop_sync` or getShop runs before the next `store.update`, so the stored value is unchanged.
  4. The check passes and the hand edit is overwritten, which is exactly what the b5226f7 L-2 fix set out to prevent.

  The same happens if the field had no reading at approval and still has none (the preview showed "UNKNOWN" and the owner approved anyway).
- **Not reachable today:** no grant can be minted (M-2R), SHADOW holds before `resolve`, and the kill switch is off.
- **Fix:**
  - At execution, require a FRESH reading of each replaced field observed *after* the grant's `approved_at`. A getShop immediately before `update_shop` is the simplest way.
  - Hold if either side is UNKNOWN or STALE.
  - Correct the AGENTS.md wording.

### L-2 (Low): F-113 salvage handles unreadable inputs asymmetrically, and one UNKNOWN still yields `rescue_candidate`

- **Where:** `creative/salvage.py:62-64, 79-88, 94-98`.
- **What:**
  - If `commerce.portfolio.diversification` raises, `competing = set()`, so every legacy product's portfolio gate reads **PASS** (UNKNOWN counted as PASS).
  - If `select_portfolio()` raises, `selected = set()`, so every product's `mjs_market` gate reads **FAIL**. Two such failures make `retire_recommended`.
  - `rescue_candidate` allows one UNKNOWN gate, so a product with no current blind review (creative UNKNOWN) and four PASSes is put forward for rescue.
- **Scenario:** a radar import error during the weekly run marks every legacy product FAIL on market. Together with any one other FAIL, the reading lists them all as `retire_recommended`.
- **Severity:** Low. The output is a reading only. Nothing retires, unlists or edits anything, and `writes: 0` holds; `test_f113_salvage_only_recommends_and_never_writes` passes. But a human or a later agent could act on a wrong recommendation.
- **Fix:**
  - An exception in a shared input should make that gate UNKNOWN for every row, not PASS or FAIL. `_guard` already does this for per-row errors.
  - Require creative ≠ UNKNOWN for `rescue_candidate`.

### L-3 (Low): F-775 `bundles` and `planned_family_members` point at uncertified seeds, despite the "certified-only edges" rule

- **Where:** `commerce/cross_sell.py:44-56` and the returned `rule` string. The test is `test_w4_c3.py:110-114`.
- **What:**
  - `bundles` lists every POOL seed in the family with `is_bundle`, whether certified or not.
  - `next_projects.planned_family_members` is by construction uncertified.
  - The module docstring and the returned `rule` say "edges point only at certified products", but the test checks only `related` and `in_catalogue`.
- **Scenario:** a future listing or PDF renderer trusts the graph's stated rule and shows `bundles` as "complete the set" links to buyers. A buyer is then pointed at a product that does not exist, which is a misleading recommendation, against F-775's "without misleading customers".
- **Today:** the graph is an internal reading with no consumer.
- **Fix:** filter `bundles` to certified slugs, or move both fields under a clearly internal `planned` key and narrow the `rule` text. Extend the test to every edge field.

### I-1 (Info): freshness counts an UNKNOWN check as "run"

- **Where:** `runtime/quality_ops.py` (`_run_check` records an audit row for `ok is None`, and `next_work` treats any reading as having run). AGENTS.md states this explicitly.
- **What:** it is never a pass: there is no incident resolution and no certificate change. But a release whose `gate.policy` can never read (no listing) is never offered for re-verification again, and nothing reports that it has been unverifiable for N days.
- **Fix:** expose an `unverifiable` count per release in the sweep's reading.

### I-2 (Info): residual risk after the service split

Once the web service runs with `BRAMBLELOOP_EMBEDDED_WORKER=0` and holds the signing key, the only in-process barrier is the `owner_request` ContextVar, and that is a public function.
- **The static guard can be evaded.** The regex in `test_m2r_minting_needs_the_owner_request_context_set_only_by_the_cc_route` matches only `sfa.`, `_sfa.` or `storefront_authority.`. The AST attribute check needs "storefront_authority" in the source text of the receiver. An import such as `from ..ops import storefront_authority as auth_x` followed by `auth_x.owner_request(...)` passes both. So does `getattr` or `importlib`.
- **Why it is only Info:** this is acceptable as defence in depth, because no job runs in that process.
- **Stronger fix:** the prior review's option 2, where the owner's device signs the previewed digest. It is still the way to remove the key from the server entirely.

### I-3 (Info): revocation is unavailable wherever signing is refused

- **What:** `LEDGER.revoke` appends a signed row (`sealed_chain.py:242` → `_seal`). In today's single container, neither the Command Center nor the bearer can revoke a storefront grant, and a separate worker never can.
- **Why it is harmless:** no grant can exist there, and the kill switch (`BRAMBLELOOP_STOREFRONT_WRITES_AUTHORISED`) is still a deny path that needs no key.
- **Fix:** state this in the AGENTS.md §6/§7 operator notes.

### I-4 (Info): the competitor benchmark alias can be reversed by anyone with the repository

- **Where:** `runtime/intel_ops.py` (`benchmark_alias`).
- **What:**
  - The alias is an unsalted SHA-256, truncated, of a key listed in `intel/benchmarks.py`. Anyone with the repository can map an alias back by hashing the list. It meets the aim (the shop name is not stored literally), but it is not anonymisation.
  - Snapshot readings written before b199cdb still hold raw keys.
  - The first delta after deploy will not line up, because `_with_delta` compares raw keys from the previous reading with the new aliases.
- **Fix:** none needed. If it matters, use an HMAC with a server-side secret or a stored alias table.

### I-5 (Info): `core/contracts.py` (3ace401) has no test and no caller

- **What:** F-456/F-482 add `check()` and `require()`, but nothing calls them and no test pins them. The commit says "tests to follow". `check()` returns `[]` at b199cdb.
- **Fix:** do not count F-456 or F-482 as delivered until a test runs `check()` and a consumer calls `require()`.

### I-6 (Info): the capability scorecard adds an unknown-orders period as 0 orders

- **Where:** `creative/capability_scorecard.py` (`_market`).
- **What:**
  - Once any period of a concept has `orders` recorded, periods with `orders = None` add 0 orders but still add their visits.
  - Conversion is understated, and `winner` can read False when the sale fell in an unrecorded period. `style_learning._orders_for` would have fallen back to the orders table.
  - Impressions and visits are mandatory at the only writer (`style_learning.py:209-210`), so CTR is not affected.
- **Fix:** sum orders and visits over periods with known orders only, or fall back to `_orders_for`.

### I-7 (Info): an asset-health failure stops the storefront review

- **Where:** `runtime/storefront_ops.py:37-42`.
- **What:** `asset_health.check` runs inside `handle_storefront_review` with no `try`. An exception there fails the whole review job, including the owner-gap draft enqueue. This is a robustness issue, not a security one.
- **Fix:** guard the call and record the health reading as UNKNOWN.

## 3. The prior review's Low findings: re-verification

| Finding | Status | Evidence |
|---|---|---|
| L-2 (`%policy%`) | **Closed** | Signatures use `SIGNATURE_ALIAS` (`gate.policy` becomes `listing-rules`). `_resolve` also closes the pre-alias signature. Test: `test_l2_a_policy_reverify_incident_does_not_read_as_an_open_policy_risk`. |
| L-3 (snapshot key and inner values) | **Closed** | Alias plus allowlist; `_assert_no_content` checks the alias prefix, pod, seasonal and product-type keys, and that values are integers. The test plants a shop key and a "Rivals Secret Holiday Label" and asserts that neither appears. |
| L-4 (resolve, freshness, raise) | **Closed** | A pass resolves only the same check's `quality.reverify:*` P2 rows, never a halting incident from elsewhere. Freshness needs all four checks. A raise becomes a P2 finding. See I-1. |
| L-5 (OA-D1 dropped) | **Closed** | OA-D1 is superseded only while `storefront:write_authority` is open. It closes on a FRESH sections reading with status OK, and otherwise it is still asked or reopened. In the evidence-close path the code sets `row.done` directly rather than calling `owner_queue.transition`, the same way the neighbouring "closed" path does. |
| I-3 (negative revision) | **Closed** | `max(0, …)` in both places, with a test. |
| I-4 (wording match) | **Closed** | Set membership, with a test that patches the message text. |
| b5226f7 L-2 (DIFFERS preview) | **Partly closed** | The preview and the signed digest now carry `replaces`. A grant without it is held. See L-1 for the execution check. |
| b5226f7 L-1 (Laura delegation) | **Open, deferred** | D-W4-AGENTS-L1-DEFER. Laura is frozen, and the deferral is recorded honestly. |

## 4. Edits to existing tests: none weakened

| Test | Change | Assessment |
|---|---|---|
| `test_w4_agents.test_agent_doable_store_cards_are_superseded_not_asked` | Before, it asserted that OA-D1 is skipped and superseded with no grant card. Now it covers four cases: (1) no card and no evidence means **not** skipped, and the row is still open and not done; (2) with the grant card open, the old assertions (skipped, superseded, "agent work", OA-C drafted, lifecycle audit row) all remain, plus the card name in the reason; (3) with the card done, the row is reopened; (4) a FRESH sections reading closes it. | **Stricter.** The one inverted assertion (case 1) is the L-5 behaviour change the prior review asked for. Every original assertion is kept under the condition where it should still hold. |
| `test_w4_departments.test_quality_sweep_reaches…` | "A single `cir.twin` makes the release fresh" became "all four checks are needed" | Stricter (L-4). |
| `test_w4_agents_secfix` M-2 tests | Wrapped in `sfa.owner_request("test-session")` | Needed for the new requirement. The refusals they test still come from the missing signing key and the foreign key pair, and the assertions are unchanged. |
| `test_w4_agents_secfix` AST scan | From six packages to the whole package; more names checked | Stricter. |

## 5. Tests run by the reviewer

All runs used `nice -n 19` and `PYTHONPATH=src:tests` on the detached HEAD `b199cdb1`. Every run exited 0 with no failures.

| Suite | Result |
|---|---|
| `test_w4_agents_secfix` | 11 OK |
| `test_w4_agents` | 14 OK |
| `test_w4_departments` | 17 OK |
| `test_w4_c3` | 3 OK |
| `test_w4_capability_scorecard` | 3 OK |
| `test_w4_c2_visual` | 4 OK |
| `test_w4_store_live_state` | 12 passed |
| `test_w4_storefront_checks` | 15 OK |
| `test_w4_listready` | 31 OK |
| `test_roles` | 35 OK |
| `test_route_auth_default_deny` | 7/7 |
| `test_w4_children` | 5 OK |

The reviewer's own probe (not committed) covered:
- the ContextVar across anyio threadpool calls, child threads, sibling requests and exit;
- an empty session id;
- the `signing_refusal` truth table over unset, `"1"`, `"0"`, `"true"` and `" 1"`.

## 6. Recommended actions

1. **Before any storefront write is enabled after the service split:** fix L-1. Read the shop fresh at execution, require a reading newer than the grant, and hold on UNKNOWN or STALE.
2. L-2: shared-input failures in salvage should give UNKNOWN, and `rescue_candidate` should require a known creative verdict.
3. L-3: make cross-sell edges certified-only, or label the planned edges as internal, and extend the test.
4. I-5: add the contracts test before F-456/F-482 are claimed.
5. I-1, I-6, I-7: small honesty and robustness fixes when next in these files.
6. Still open: the carried L-1 (Laura). The prior review's option 2 (owner-device signing) remains the long-term answer to I-2.

---
_Generated by [Claude Code](https://claude.ai/code)_
