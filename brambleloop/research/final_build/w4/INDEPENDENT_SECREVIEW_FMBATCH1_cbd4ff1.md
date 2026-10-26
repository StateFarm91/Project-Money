# Independent security and integrity review: W4-FMBATCH1, fixes and new rows (871b84a → cbd4ff1)

- **Reviewed:** `git diff 871b84a3..cbd4ff12 -- brambleloop/src brambleloop/tests brambleloop/ops brambleloop/run_tests.sh ops/`
  on `claude/w4-FMBATCH1`. I also read `brambleloop/scripts/classify_failure.py`, which the
  F-6 fix changes.
- **Read first:** `INDEPENDENT_SECREVIEW_FMBATCH1.md` (the review at 871b84a) and `FMBATCH1.md` §21–24.
- **Reviewer:** an independent Claude Code context that did not write this code. Review only:
  nothing was fixed. There were no network calls from the code under test, no paid calls, no
  secrets and no deploys.
- **Date:** 2026-10-26 (UTC).

## Verdict

| Question | Answer |
|---|---|
| **Can cbd4ff1 ship on top of the listings release with SHADOW on?** | **Not quite as it stands. One blocking fix is needed: N-1.** Everything else can ship. |
| Why N-1 blocks | `/api/finance` is a public GET. It now carries `owner_view.cash_and_payout`, which holds cash on hand (the bank balance), bank statement line IDs, the expected payout, owner payable, tax reserve, runway and the safe budget. Before this range that data was only served behind the owner session (`/api/cc/*`). SHADOW does not gate it: the data goes public the moment a bank statement or payout is imported. |
| After N-1 is fixed | Yes, ship it with SHADOW on. No new row adds a paid, outward, publishing or Etsy-write path. The extra swarm specialist is clamped to what the ceiling affords, and the worker wake is rate-limited to one per five minutes. |
| F-1 to F-11 | **All closed.** I reverted each fix (or mutated its behaviour) in a scratch copy, and every one made its test fail. See the table below. |
| Tests weakened? | **No.** The `test_deploy` assertions are unchanged; the other test edits make tests stricter. |
| F-11 acceptance (RUN > GROW > IMPROVE kept) | **Reasonable.** |

| # | Severity | Area | Short title |
|---|---|---|---|
| N-1 | **High** (the data is real once a statement or payout is imported) | F-620 `/api/finance` | Unauthenticated route serves the owner's bank balance, statement line IDs, payouts, reserves and runway |
| N-2 | Low | F-1 fix (taxonomy drift) | With re-queue OFF, the drift incident no longer halts publication, so a drifted listing can still reach `store.publish` past SHADOW |
| N-3 | Low | F-602 executive plan | "First sale" reads 0 orders as a measured 0 (not met) even when the order source is disconnected |
| N-4 | Info | F-3 fix (`deploy.sh`) | The header still documents `AUTO_ROLLBACK` as "default 1"; `AUTO_ROLLBACK_REASON` is a standing reason reused for every future rollback |
| N-5 | Info | F-2 fix (research fetch) | A redirect to a non-Latin-1 IDN raises `UnicodeEncodeError`, which is neither `FetchRefused` nor `OSError`. It is not followed, but no audit row is written |
| N-6 | Info | F-171 `/api/verify` and smoke | The new `status` reads `OK` while the smoke matrix is FAIL or UNKNOWN, and DEGRADED hides UNKNOWN in the smoke headline. Release gating is unaffected |
| N-7 | Info | F-722 and F-602 | Up to 3× more orchestrator ticks; a stale executive plan keeps its boost forever. Both stay inside the ceilings |
| N-8 | Info | F-4 fix (`compat_pack._bill`) | If the release fails after the record is written, the call is recorded twice. This over-counts, which is the safe direction |

---

## 1. Are F-1 to F-11 closed?

**Method.** For each fix I did two things in a scratch worktree at cbd4ff1:

- restored the 871b84a version of the fixed file and ran the fix's test;
- where the test then failed only because a new symbol was missing, mutated the *behaviour*
  instead, so the test was shown to check behaviour and not just a name.

I restored the tree after each step (`git status` clean).

| Finding | Claim checked | Revert or mutation | Result |
|---|---|---|---|
| F-1 | No path reaches `store.publish` by default | Behaviour mutation: `requeue_enabled = lambda env=None: True` | **Killed.** `test_by_default_drift_requeues_nothing_and_asks_the_owner` fails (a `tx*` chain is queued). The file revert also fails. |
| F-1 | Only path | Reviewed every `ctx.enqueue` in the range. The only new enqueue is F-722's `autonomy.orchestrate` wake. Nothing new enqueues `listing.seo`, `launch.plan` or `store.publish`. | **Closed.** (See N-2 for a side effect.) |
| F-3 | No automatic push; no machine-written reason | `ops/deploy.sh` revert | **Killed** (`test_w4_fmbatch1_rollback`). By reading: a push needs `AUTO_ROLLBACK=1` **and** a non-empty `AUTO_ROLLBACK_REASON`, and the script passes that reason verbatim. Nothing in the repo sets either variable (grepped `*.sh *.py *.md *.json *.yml *.toml`). |
| F-2 | Redirect and scheme bypasses | `_redirect_handler` mutated to a plain `HTTPRedirectHandler` | **Killed** ("redirect to https://evil.example/x was followed"). Adversarial probe results are below. |
| F-8 | Network error is "not fetched"; `promote` still runs | File revert, with `FetchUnavailable` stubbed in so the test can import | **Killed** (`URLError` and `OSError` escape). |
| F-4 | Every billed response is recorded and the ceiling sees it | `compat_pack.py` revert | **Killed** (both `test_review_f4_*` fail: no spend row). `_bill` calls `spend_report.record(purpose="compat_pack")` and then releases. `estimate_cad` is present in a successful `check_budget_cad` return (`gateway/anthropic.py:646`), so an unreadable usage is billed at a non-zero estimate. |
| F-5 | Vision reserves image tokens; no reservation leaks | `compat_pack.py` revert | **Killed** (`test_review_f5_*`). |
| F-6 | Assertion text is never an "environment failure" | `classify_failure.py` revert | **Killed.** |
| F-7 | Refused unless the status is `verified` | (a) whole `deploy_guard.py` revert; (b) only the `_record_problems` condition reverted | **Killed** in both cases. Both refusal sites now refuse `required and status != "verified"`. |
| F-9 | A malformed plan row is UNKNOWN, not a 500 | `physical_truth.py` revert | **Killed** (`ValueError: Invalid isoformat string`). |
| F-10 | UNKNOWN contract is never routed | `failover.py` revert | **Killed** (`action == CALL` instead of `PARK`). |
| F-11 | WATCHING row is not rewritten every tick | `orchestrator.py` revert | **Killed** (`updated_at` changes). |

**F-2 adversarial probe.** Offline: I patched `https_open` and `http_open` to a fake transport
that returns scripted 302s, and drove the real `_default_get` and the real `check_url`.

```
check_url:
  HTTPS://EN.WIKIPEDIA.ORG/a                ALLOWED (scheme and host normalised)
  http://en.wikipedia.org/a                 refused: only https
  https://en.wikipedia.org:8443/a           refused: only the default https port
  https://en.wikipedia.org:0443/a, ":/"     ALLOWED (both are port 443; same service)
  https://en.wikipedia.org:99999/a          refused: unreadable port
  https://user:pw@…, https://host@evil…, https://evil\@host, https://host%2f@evil, https://host\t@evil
                                            refused: credentials
  https://evil.example#@en.wikipedia.org    refused: not on the allowlist
  https://en.wikipedia.org.evil.example     refused: not on the allowlist
  https://en.wikipedia.org./ (trailing dot) refused
  https://еn.wikipedia.org (Cyrillic е), xn--n-gtb.wikipedia.org   refused
  https://169.254.169.254/, https://[::1]/, file:///etc/passwd, //host/a, https:host/a   refused
  ?api_key=…                                refused: secret-looking parameter
redirects through _default_get:
  same-host relative /next                  FOLLOWED (correct)
  allow -> allow -> https://evil.example    refused at the second hop
  -> http:// same host                      refused: only https
  -> //evil.example (protocol-relative)     refused: not on the allowlist
  -> http://169.254.169.254/latest/meta-data refused
  -> userinfo, :8443, lookalike, ftp://     refused
  -> https://еn.wikipedia.org (IDN)         not followed: UnicodeEncodeError from urllib (see N-5)
robots.txt larger than MAX_BYTES            (False, "robots.txt larger than the byte cap: unreadable…")
```

**F-2 is closed.** The only residue is N-5, which is an audit gap, not a bypass.

---

## 2. Did any new row add a paid, outward, publishing or Etsy-write path, or expose data without a credential?

**Outward, paid and publishing paths: none added.** Each new row by what it does:

- `executive_plan`, `useful_work`, `provider_health`, the Command Center autonomy block,
  `creators.measure_outcome`, `owned.assisted_conversions`, `proof._customer_rungs`,
  `kill_table.learn`, `remerchandising`, the Learn card and `/m` are all reads.
- `memory.remember`, `OwnerAction` and incidents are internal writes.
- `kill_table.learn` changes the thresholds of a *reading* (`commerce_readings.read`). It
  drives no executor.
- The only new enqueue is F-722's `autonomy.orchestrate` wake (see §3).

**Route exposure.** I checked each route with `security.requires_operator("GET", path)` at
cbd4ff1:

| Route | Credential required | What it returns | Assessment |
|---|---|---|---|
| `/api/finance` (`owner_view`) | **No** | `cash_on_hand_cad`, `cash_unreconciled_lines` (`kind:external_id` of bank lines), `expected_payout_cad`, `obligations.owner_payable`, `tax_reserve`, `runway`, `safe_discretionary_budget_cad`, MTD/YTD `profit`/`cash`/`net_sales`, and the close state | **N-1 (High).** |
| `/m` | No | Worker state, pending and dead counts, the owner inbox (top 6 cards), jobs done and spend today | Same exposure as `/`. `/` already renders `executor.approval_inbox` publicly (`main.py:5876`). Every value goes through `esc()`. **No new exposure.** |
| `/api/useful-work` | No | Ready-work ages, job ids and types, count and hours of open owner actions, WATCHING spans, completion rate | Operational aggregates; no personal or finance data. **Acceptable.** |
| `/api/company/departments` | No | `departments.coverage`: charter mission, generatable job types, KPI keys, cells, agent names | Static charter metadata. It replaces a second `/api/departments` route that was shadowed and could never be reached. **Acceptable.** |
| `/api/owned` (`assisted_conversions`) | No | Per-product order counts (direct and assisted) | Aggregates only; `customer_id` is used for grouping and never returned. **Acceptable.** |
| `/api/verify` (`provider_health`) | No (already public) | Reason class and HTTP status code only; `provider_reason` is now redacted | An improvement: raw provider prose was public before. |
| CC autonomy block | Owner session (`/api/cc/*`) | `useful_work` readings | **Acceptable.** |

---

## 3. Can the extra swarm specialist or the F-722 wake exceed a ceiling or run away?

**`swarm.allocate` (F-602): no.**

- The boost is `granted + 1` for a lane that has pending work and an agent on the critical
  path.
- The very next line is `granted = min(granted, affordable)`.
- The `#31` unproductive cap (`granted = 1`) still applies after it.
- `spend_increase_cad` stays `0.0`, and no ceiling is read-modify-written.
- With no plan, no boost: `priority_agents` returns an empty set on any error.
- Info (N-7): the stored plan has no expiry. If `refresh` fails forever, the last plan's
  boost persists. It is still clamped by `affordable`.

**F-722 worker wake: bounded, no loop.**

- `_refill_after` skips `autonomy.*` jobs, so an orchestrate job ending never wakes the
  orchestrator.
- `idle_wake` only enqueues when nothing is RUNNING and nothing is due.
- It uses the key `autonomy.orchestrate:idle:<epoch//300>`. `DuplicateJob` is raised for an
  existing key in *any* status (`queue/durable.py:250-256`), so there is at most one wake per
  five-minute bucket across every worker and lane (12 an hour).
- Exceptions are swallowed, so the job that ended is unaffected.
- Every mission it leads to still reserves through the ceilings.
- The executive-plan refresh inside `handle_orchestrate` is gated to once an hour by
  `updated_at` (aware ISO, `memory._mem_dict`).
- **Effect (N-7, Info):** a busy-then-idle queue can tick the orchestrator up to three times
  as often as the 15-minute window: at most 11 missions per tick, one per department, with
  no-op suppression. This raises the *rate* of spend inside the ceilings, never a ceiling.

---

## 4. Does UNKNOWN or UNMEASURED ever count as PASS or as 0?

**As PASS: no.**

- `provider_health.check`: only `ok is True` is PASS. A missing row is UNKNOWN. A failure
  with an unreadable reason classifies as `other`, which is FAIL.
- `readback.py` requires the smoke verdict to be exactly `"PASS"`, so DEGRADED is a FAIL
  there.
- F-7: unreadable is refused.
- F-10: UNKNOWN is parked.
- `physical_truth`: an unknown risk class is blocked, and an unparseable date gives
  `overdue: None`, counted separately.

**As 0: one Low case (N-3) and some acceptable zeros.**

- **N-3 (Low).** `executive_plan._goals` reports `first_sale.reading = 0`, `met: False` from
  `count(orders)` even when the order source is disconnected (UNKNOWN in `finance.accounting.health`).
  `sustainable_monthly` correctly says UNMEASURED.
- **Acceptable zeros:**
  - `/m` "spend today CA$0.00" is a sum over the spend ledger itself, so zero is measured.
  - `useful_work.owner_blocked.hours` is 0.0 with zero open actions.
  - `finance owner_view.unreconciled` is 0 with zero imported lines. The count of
    `statement_lines` sits beside it, so "nothing imported" is visible.
- **Correctly UNMEASURED:** ads, ad credit, completion rate, WATCHING, `kill_table`
  baselines, and the creator and owned readings.
- **Display-only (N-6).** The new `/api/verify` `status` can read `OK` while
  `readbacks.smoke_matrix.verdict` is UNKNOWN or FAIL on a non-provider check. In the smoke
  headline, DEGRADED outranks UNKNOWN; the UNKNOWN checks are still listed under `unknown`.
  Neither changes `ok`, the HTTP status, or the readback.

---

## 5. Was any test weakened?

**No.**

- **`test_deploy.py::test_the_command_centre_shows_every_build_2_subsystem`.** The same three
  `in body` assertions ("executable left", "modelled probability", "binding layer") are now in
  a loop. Only the failure message is new; it lists any "unavailable:" blocks. The logic is
  identical.
- **`test_w4_fmbatch1_failclass.py`.** The expected advice string follows the deliberate F-6
  wording change ("do not revert" became "check the environment before reverting"). A new test
  asserts that assertion text is never classified.
- **`test_w4_fmbatch1_physical_truth.py`.** The `summary ==` dict gains `overdue_unknown: 0`,
  so it is an exact match on more keys: stricter.
- **`test_model_spend_paths.py`.** Adds the `compat_pack.run` pin: stricter.
- **`run_tests.sh`.** The F-6 label text only; `status`, `failed` and `failing_list` are still
  computed from exit codes.

One test codifies the problem in N-1. `test_owner_view_blocks_and_unmeasured_ads` GETs
`/api/finance` with no credential and expects `owner_view`. When N-1 is fixed, that test should
send the credential, and a negative test should be added.

---

## 6. Is the F-11 acceptance reasonable?

**Yes.**

- The order only sorts each department's runnable candidates (`orchestrator.py:335`).
  Permission, the ceilings, protected-work approvals and `MAX_MISSIONS_PER_TICK` (one per
  department) are unchanged.
- IMPROVE cannot starve permanently. Candidates whose evidence key already exists are dropped
  (`done_keys`), so a department's RUN and GROW candidates run out until new evidence arrives,
  and then IMPROVE is taken.
- The WATCHING write amplification is fixed and tested.
- Residual, for measurement rather than a fix: with F-722's faster ticks, a department whose
  RUN evidence changes every few minutes would favour RUN for longer. `useful_work` could
  report ready age per work class to make that visible.

---

## Findings

### N-1 (High): `/api/finance` `owner_view` serves the owner's cash, bank lines, payouts and reserves without a credential

**Where**
- `brambleloop/src/brambleloop/app/main.py:797`: `"owner_view": _finance_owner_view()` inside
  `api_finance`.
- `main.py:801-865`: `_finance_owner_view` calls `finance.accounting.cash.position`,
  `dashboard.summary` (MTD and YTD), `reconciliation.statement_lines` and `close.status`.
- `/api/finance` is not in `security.OPERATOR_GET_ROUTES` (`app/security.py:137-169`), so
  `requires_operator("GET", "/api/finance")` is `False`. I confirmed this at cbd4ff1.

**Scenario**
1. The owner imports a bank statement or an Etsy payout. This is the normal F-620 workflow
   and is not gated by SHADOW.
2. Anyone who can reach the Railway URL GETs `/api/finance` with no credential.
3. They receive:
   - `owner_view.cash_and_payout.cash_on_hand_cad`: the business bank balance. For a sole
     proprietor this is personal financial data.
   - `cash_unreconciled_lines`: `kind:external_id` of bank statement lines.
   - `expected_payout_cad`, `obligations.owner_payable`, `tax_reserve`, `runway` and
     `safe_discretionary_budget_cad`.
   - MTD and YTD `profit`, `net_sales` and `cash`.
4. Before this range that data was served only through the owner-session Command Center
   (`app/command_center/providers.py:30`, `"accounting"` → `dashboard.summary`).
5. The repo's own standard is that comparable data is operator-only: `/api/orders/ledger`
   ("accounting evidence … Operator credential required", `main.py:4191`) and
   `/api/launch/packet` (spend limits).

**Today.** On a fresh database the blocks read UNKNOWN or `None`, so nothing real leaks until
a statement or payout is imported. It is still blocking, because import is an owner action
that SHADOW does not stop.

**Fix (one of):**
- Move `owner_view` to its own route (for example `/api/finance/owner`) and add it to
  `OPERATOR_GET_ROUTES`.
- Serve it only through `/api/cc/*` (the owner session), as the accounting summary already is.

Keep `/api/finance` public with only the aggregates it served at 871b84a.

**Tests**
- Change `test_w4_fmbatch1_finance_owner.py` to send the credential.
- Add a negative test: no credential gives 401, and the public `/api/finance` body contains no
  `cash_on_hand_cad`, `cash_unreconciled_lines` or `expected_payout_cad`.
- Consider extending `test_customer_data_auth`'s public-GET sweep to these finance keys.

### N-2 (Low): with re-queue OFF, a drifted listing's incident no longer halts publication

**Where:** `integrations/taxonomy_drift.py:236-246`.

- `halts = inputs is not None`.
- On the new default path (`held`), `inputs` is set to `None`, so the P1 incident is opened
  with `halts_publication=False`.

**Scenario**
1. A deployment past SHADOW has a normal (owner-chain) `store.publish` queued or due for a
   product whose category Etsy just changed.
2. The drift is detected, but nothing halts the publish.
3. The listing is written to Etsy on a taxonomy snapshot known to be stale, while the
   re-certification waits on the owner action.

The rationale given, that a halt with nothing queued would deadlock `gate.certify`, is right
about `gate.certify`. The fix trades "drift re-drives `store.publish`" for "drift no longer
stops `store.publish`". This is much less severe than F-1, because no *new* Etsy write is
caused, but it is a weakening relative to 871b84a for CHOSEN profiles.

**Fix:** make the held incident halt `store.publish` (and `launch.plan`) for that product only,
not `gate.certify`. Either `store.publish` refuses while a `taxonomy-drift:<slug>` incident is
open, or a publish-only halt flag is added. Test: with re-queue OFF, a queued `store.publish`
for the drifted slug past SHADOW is refused with the drift reason.

### N-3 (Low): the executive plan reads "first sale" from `count(orders)` even when orders are not readable

**Where:** `autonomy/executive_plan.py:32-49`.

**Scenario:** the Etsy order source is disconnected, which is the state `finance.accounting.health`
reports as UNKNOWN. The plan then records `first_sale: {reading: 0, met: False}` as a measured
fact, in company memory and the Command Center.

**Fix:** read the order-source state, as `cash.position` does with `H.figure_reading`, and
report `reading: "UNKNOWN"`, `met: None` when it is not connected.

### N-4 (Info): `deploy.sh` documentation and the standing rollback reason

- `ops/deploy.sh:15-16` still says `AUTO_ROLLBACK=0 … instead of rolling back …; default 1,
  F-381`. The code now defaults to 0. An operator reading only the header would believe
  automatic rollback is on. Update the header.
- `AUTO_ROLLBACK_REASON` is a standing environment value. Once set, it authorises every future
  automatic rollback with the same text. That matches the "owner accepted containment"
  design. Record the acceptance in `DECISION_LOG.md` with the reason text, so the guard's audit
  points to a dated owner decision.

### N-5 (Info): an IDN redirect target escapes the fetch's own audit

**Where:** `intel/research_fetch.py:110-128`.

**Scenario**
1. Python's `http_error_302` quotes `newurl` with `encoding="iso-8859-1"` *before* calling
   `redirect_request`.
2. A `Location` with a Cyrillic host raises `UnicodeEncodeError` (a `ValueError`, not
   `FetchRefused` and not `OSError`).
3. It escapes `_default_get` and `fetch_for_task`. It is caught only by `run()`'s per-fetch
   `except Exception` (from the F-8 fix).
4. The redirect is **not followed**, but no `learn.research_fetch` audit row is written for
   that fetch.

**Fix:** in `_default_get`, catch `ValueError` and turn it into
`FetchRefused("unreadable redirect target")`.

### N-6 (Info): `/api/verify` `status` and the smoke headline

**Where**
- `main.py:5330`: `status = "FAIL" if not passed else "DEGRADED" if unhealthy else "OK"`
  considers only `provider_health:*` rows. It reads `OK` beside a smoke matrix that is FAIL
  (for example a stale probe) or UNKNOWN.
- `ops/smoke.py:246`: DEGRADED outranks UNKNOWN in the headline verdict.

**Effect:** none on gating. `ok`, the 200/503 status and `readback.py` (which needs `"PASS"`)
are unchanged. But a reader of `status` is told `OK` while the matrix says otherwise.

**Fix:** derive `status` from both `passed` and `smoke["verdict"]` (`OK` only if the smoke
verdict is PASS), and rank UNKNOWN at least equal to DEGRADED in the headline.

### N-7 (Info): orchestrator cadence and plan staleness

These are described in §3. Both are bounded by the ceilings.

**Fix (optional):**
- Expire `priority_agents` when the plan is older than, say, 6 hours.
- Record the number of idle wakes per day in `useful_work`.

### N-8 (Info): `compat_pack._bill` can record a call twice

**Where:** `gateway/compat_pack.py:160-180`.

**Scenario:** if `spend_report.record` succeeds and `release_reservation` then raises, the
`except` branch calls `_bill` again, because `resp` is set. This over-counts, which is the safe
direction for a ceiling. There is still no live caller.

**Fix:** set a `billed` flag after `record`.

---

## Tests run (at cbd4ff1, `nice -n 19`, one suite at a time)

**Environment**
- The venv was built from `brambleloop/requirements.lock`. There is no `requirements-test.lock`
  in the repository.
- The installed `starlette` needs `httpx2` for `TestClient`. `httpx2` is not in the lock, and
  installing a package from outside the lock was not permitted in this session, so the
  `TestClient` suites could not run.

**Passed**
- `test_w4_fmbatch1_drift` (10)
- `test_w4_fmbatch1_rollback` (12)
- `test_w4_fmbatch1_research_run` (10)
- `test_w4_fmbatch1_compat`
- `test_w4_fmbatch1_signing`
- `test_w4_fmbatch1_failclass` (3)
- `test_w4_fmbatch1_providers` (7)
- `test_w4_fmbatch1_departments`
- `test_w4_fmbatch1_executive_plan`
- `test_w4_fmbatch1_refill`
- `test_w4_fmbatch1_provider_boundary`
- `test_w4_fmbatch1_creator_outcomes`
- `test_w4_fmbatch1_kill_learn`
- `test_w4_fmbatch1_owned_assisted`
- `test_w4_fmbatch1_proof_customer`
- `test_w4_fmbatch1_remerch`
- `test_model_spend_paths`
- `test_w4_spend_paid_discipline`
- The F-9 test function, run directly.

**Not run here (needs `httpx2`)**
- `test_w4_fmbatch1_physical_truth` (whole file; only F-9 was run directly)
- `test_w4_fmbatch1_useful_work`
- `test_w4_fmbatch1_mobile`
- `test_w4_fmbatch1_finance_owner`
- `test_w4_fmbatch1_learn_card`
- `test_w4_fmbatch1_provider_health`
- `test_route_auth_default_deny`
- `test_customer_data_auth`
- `test_deploy`

For the routes, I called the route functions directly (`_finance_owner_view`, `dashboard_mobile`,
`api_useful_work`) and checked authentication with `security.requires_operator`.

**Also not verified here:** the full suite, the browser (`cc_mock`) checks, and any production
behaviour.
