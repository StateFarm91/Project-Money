# W4-CCALL: Command Center completion, consolidated (CCREL + CCGAP2 + CCFM1 + CCFM2 + CCGROW)

Branch `claude/w4-CCALL` from `origin/claude/w4-INTEG2` @ 85ec5d0. The five worker branches are merged in with merge commits:

- **CCREL and CCGAP2** merged cleanly.
- **CCFM1** conflicted in `cc_mock/check.mjs` and `css/app.css`. Both conflicts were additions at the same anchor; the fix keeps both sides, and `node --check` passes.
- **CCFM2 and CCGROW** merged cleanly.

Nothing here deploys or writes to production or Etsy. Phase stays shadow, and UNKNOWN is never shown as 0.

| Part | Rows / items | Detail |
|---|---|---|
| CCFM1 | F-619, F-621, F-651, F-652, F-670 (F-620 blocked on F-614/F-610) | `CCFM1.md` |
| CCFM2 | F-661, F-668, F-729 (F-653 evidence; F-660 is runtime, not CC) | `CCFM2.md` |
| CCREL | Queue item 2: Approvals release card, Etsy Connect end to end in the mock, Laura CEO briefing view | `CCREL.md` |
| CCGAP2 | Queue item 3: CC_GAP FU-7 (reasons derived from the card's items), FU-5 (Laura "Needs you" equals the Approvals count) | `CCGAP2.md` |
| CCGROW | F-504, F-126 (experiment part); other growth/brand rows triaged as gated or not this domain | `CCGROW.md` |

Added directly on CCALL after the owner's launch-scope decision (2026-10-12: post-launch rows are built and verified before the store opens):

| Row | Change | Evidence |
|---|---|---|
| **F-622** Command Center Marketing & Customers | `tabs.marketing_customers` leads Insights as "Marketing & customers". It shows:<br>• orders by channel (organic / paid / owned / unattributed, from countable orders);<br>• refunds;<br>• ROAS, from `growth.ads_readiness` KPIs, counting evidence-attributed Etsy Ads orders only;<br>• CPC/CTR and review themes, both UNKNOWN: no sanctioned source;<br>• campaigns, meaning spend proposals and their status, with nothing executed;<br>• support cases (owner-recorded).<br>Orders and refunds read **UNKNOWN, never 0**, until the order source is read. No customer content appears. The criterion needs no live customers: the view is built and verified now, and it fills in once orders exist. | `tests/test_w4_ccall.py` (3 tests) |
| **F-660** Elastic Capacity | The criterion: "normal multi-agent operation continues when promotional/paid cloud credit is zero". It is verified locally:<br>• the credits wallet is empty;<br>• cloud and provider credential environment variables are removed;<br>• three workers complete three different agents' jobs **concurrently** (the barrier opens only when all three run at once);<br>• the dispatch path (runner, worker, durable queue) never reads the credits wallet.<br>Session independence is already proven by `test_cert_claude_independence`. | `tests/test_w4_f660_zero_credit.py` (2 tests) |
| F-453 Work-Conserving Scheduler | No code here. The pre-launch criterion is covered by existing tests: `test_continuous_operations::test_control_lane_progresses_while_production_is_blocked`, `test_cert_orchestration::test_concurrent_workers_never_execute_the_same_job_twice`, and the F-660 concurrency test above. The remaining step is the ledger's own: verify `BRAMBLELOOP_WORKER_THREADS>1` in production after an approved deploy (owner gate `production_window`). | — |

Not taken, with reasons:

- **F-453.** The deploy and production window belong to the integrator.
- **F-622.** Needs real buyers.
- **F-873.** Needs an owner ruling.
- **F-680 and F-748.** These are visual evidence panels in the image domain. `/cc/image-review` already exists.

## Test results on CCALL

These are the results at merge `bbd47a5`, which is CCALL plus INTEG2 `534f27a`. They were taken on 2026-10-12, between about 08:20Z and 09:10Z. Every run went through `/home/user/bl-runs/testslot.sh` with N=3. Every run was green.

**New tests:**

| Test | Passed |
|---|---|
| test_w4_ccall | 3/3 |
| test_w4_f660_zero_credit | 2/2 |
| test_w4_ccrel | 8/8 |
| test_w4_ccgap2 | 3/3 |
| test_w4_ccfm1 | 8/8 |
| test_w4_ccfm2 | 5/5 |
| test_w4_ccgrow | 4/4 |

**Regression:**

| Test | Passed |
|---|---|
| test_v11_pwa_static | 81/0 |
| test_w4_cc_company | 23/23 |
| test_v11_cc_views | 13/13 |
| test_w4_ccgap_views | 10/10 |
| test_w3_laura_cc_talk | 9/9 |
| test_w4_ownerhome | 10/0 |
| test_w4_ccux | 8/8 |
| test_experiment_persistence | OK |
| test_cert_growth_ops | 0 failing |
| test_growth | OK |
| test_vacuity | OK |
| test_w4_ondemand | 17/0 |
| test_route_auth_default_deny | 7/7 |
| test_customer_data_auth | 9/9 |
| test_cert_dashboard | 18/18 |

**Browser:**

- `test_v11_pwa_browser`: passes=217, failures=0.
- The cc_mock `check.mjs` at 390 px: passes=217, failures=0, exit code 0. Every new block passed:
  - ccfm1 (company, money and insights);
  - ccrel (approvals release card);
  - etsy connect (step-up, CSRF + nonce, and a non-Etsy authorize URL not followed);
  - laura briefing;
  - ccall insights (F-622).
