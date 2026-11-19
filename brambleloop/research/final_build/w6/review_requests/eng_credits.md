# ENG-CREDITS — review request (round 1)

Branch `eng/credits`. Base `claude/w6-INTEG2` @ a35ad302, which has not moved. Code commit:
89ae3cf13a0a15f999853cf652dbd9caf40f5572. Builder. Not merged and not deployed. Nothing touched
Railway, production, secrets, `BRAMBLELOOP_PHASE`, `STAGE_A_ENABLED`, routing defaults or any
ceiling.

## What changed

1. **`finance/credits.py`** extends the existing module; it is not a second ledger.
   - **Schema.** `ProviderCredit` gains three additive nullable columns: `period_start`,
     `period_end` and `recorded_by`. `core.migrate` adds them to the existing table.
   - **Draw window.** `split()` now bounds a grant's draw by the earlier of its expiry and its
     period end (`_draw_until`). Grants written before this change behave as before.
   - **`record_model_credit`.** Records a model-provider credit for the owner only.
     - Providers: anthropic or openai.
     - Amount: positive and finite, in USD or CAD.
     - Dates: ISO; the period must not be inverted; expiry must be on or after the period start.
     - Evidence note: required, at least 12 characters.
     - `recorded_by` must be `owner:`.
     - Refuses a grant whose period overlaps an existing grant for the same provider.
     - An empty expiry is recorded as UNKNOWN.
   - **`model_credit_accounting`.** Reports the calendar month, per provider.
     - The remaining eligible credit is **UNKNOWN** (never 0) until a recorded grant's window
       covers today.
     - Gross usage, in CAD and USD.
     - Billed usage: `CostEntry.observed_cad` only, otherwise UNKNOWN.
     - Estimated cash: gross less the assumed credit draw. With no grant, all usage is cash.
     - Paid calls that were DECLINED, FAILED_BILLED or UNCERTAIN this month, with their estimates.
     - The cash ceiling, reported but not changed (`ceilings_changed` 0).
   - **`model_cost_by_product`.** Reports the month's `llm` cost per product and per provider.
     - The per-product totals plus the unattributed remainder reconcile to the ledger.
     - Per certified listing package, the cost is the product's cost only when the product has
       exactly one certified package. Otherwise it is UNKNOWN: the ledger has no version column.
   - **`productive_model_use`.** For each family, reports STARVED, NO_CALLER, RUNNING or IDLE from
     the month's `spend.refused` rows and `llm` costs. It wires nothing.
2. **`POST /api/cc/finance/model-credit`.** Owner session plus step-up (`finance.model_credit`).
   - `recorded_by` comes from the session, never from the request body.
   - Writes an audit row `finance.model_credit_recorded`. Nothing reads that row by name, so
     `retention.unknown_read_actions()` still returns `[]`.
   - `GET` on the same path is read-only.
3. **P0 board section `model_credit`.** Read-only. Its state is `UNKNOWN` until a grant is
   recorded. `/api/finance/owner` gains `model_credit`.
4. **`research/final_build/w6/model_allocation.md`.** The routing audit (every model call site),
   the deterministic-misuse and bypass findings (F-D1–3, F-A1–5), the proposed allocation, and
   the starvation table. It is a proposal only; routing changes go through the owner card.

## Tests

The new suite is `tests/test_eng_credits.py`, 14 tests, added to `suite_final_segment.txt` before
`test_product_run`. It covers:
- UNKNOWN until recorded;
- a grant never raises the cash ceiling, and `routing.check` still refuses;
- per-product sums match the ledger;
- no auto-recharge, probe or network call (an AST identifier scan, plus no CostEntry,
  PaidCallRecord or SpendReservation row is written);
- the owner route needs step-up, and a forged `recorded_by` is ignored;
- the productive-use states;
- retention.

Suite runs:
- **Required set plus nearby finance suites** (18 suites): 255 passing, 0 failing. The suites:
  `test_eng_credits test_vacuity test_w3_tmp_hygiene test_w4_resume_runner test_w3_spend_attribution test_s2_fix_ledger test_s2_fix_routing test_s2_openai_provider test_cert_spend_hosts test_cost_governance_wave2 test_route_auth_default_deny test_s4_p0_board test_etsy_oauth_callback test_w4_f660_zero_credit test_w4_close6_ads test_w4_spenda_k5a test_w4_fmbatch1_finance_owner test_customer_data_auth`
- **Adjacent suites:** 38 passing, 0 failing. The suites:
  `test_r2_security_actions test_v11_cc_actions test_w4_auditfix_migrate test_continuity test_secret_scan test_r2_security_freshness`

**Mutants: 13 of 13 killed.** Each mutation below made at least one test fail:

| # | Mutation |
|---|---|
| M1 | Credit counts as known once any grant exists |
| M2 | Owner check removed |
| M3 | Overlap check removed |
| M4 | Cash ignores the credit |
| M5 | UNKNOWN reads as 0 |
| M6 | Unattributed cost dropped |
| M7 | Short evidence note accepted |
| M8 | Ceiling raised by the credit |
| M9 | `recorded_by` taken from the request body |
| M10 | Step-up removed |
| M11 | P0 state always RECORDED |
| M12 | Period end does not bound the draw |
| M13 | Failed calls not limited to the month |

## Honest status and review focus

- No credit has been recorded anywhere. Both the Anthropic and OpenAI credits are UNKNOWN.
- No paid caller was added, so `test_cert_spend_hosts` needs no new declaration. No route,
  allocation or ceiling changed.
- **Please review:**
  - The additive columns on `provider_credits`, and whether the migration owner creates them
    before a worker reads them.
  - The `split()` window change for grants that have a `period_end`.
  - The product-level (not version-level) basis for per-package cost.
