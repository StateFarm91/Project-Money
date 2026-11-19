# ENG-CREDITS — review request (fix round 1)

**Fix round 1** answers main's DO NOT SHIP (M1, L1, L2, L3, L4, L7); see the section at the end.
The round-1 text below is kept as written; where it conflicts, the fix-round section wins.

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

## Fix round 1 (answers DO NOT SHIP: M1 and the LOWs)

Branch `eng/credits`, from 0904367c. Code commit: see the review-request comment on #28 for the
full sha. Nothing deployed; nothing touched Railway, production, secrets, `STAGE_A_ENABLED` or
any ceiling. A credit still never raises the cash ceiling (`ceilings_changed` 0 everywhere).

**M1 (all four parts)** — `finance/credits.py`, `app/command_center/api.py`:
1. *Booleans and non-numbers.* `amount` must be an `int` or `float`: `True`, `"100"`, `None`,
   lists and bytes are refused. (Previously `True` was stored as 1.0.)
2. *Bounds.* At most `MAX_GRANT_USD` = US$1000 per period, applied in USD whatever currency was
   typed (a CAD amount is converted first). A period is at most `MAX_PERIOD_DAYS` = 366 days,
   both ends inclusive. The evidence note is at most 1000 characters.
3. *Void.* New owner step-up action `finance.model_credit_void`, route
   `POST /api/cc/finance/model-credit/void` (`{id, reason}`), audit row
   `finance.model_credit_voided` (written, never read; retention check still clean). The row is
   **never deleted**: `voided_at`, `voided_by`, `void_reason` are set (three additive nullable
   columns). A voided grant draws nothing, does not count as credit, and does not block an
   overlapping grant, so one typo is now correctable. It is listed under `voided_grants`.
   Refused: not the owner, bad or missing id, an already-voided grant, a reason that is too
   short or carries a secret.
4. *Atomic overlap check.* New table `provider_credit_locks`, one row per model provider. Every
   recording (and every void) first `UPDATE`s its provider's row, then does the overlap read and
   the insert in the same transaction. On PostgreSQL that is a row lock: the second recorder
   waits for the first to commit and then sees its row. On SQLite it takes the database write
   lock, so the behaviour is the same. This was chosen over a unique constraint because no
   unique constraint can express "these date ranges overlap". Real PostgreSQL 16 test: it starts
   a throwaway cluster (127.0.0.1, free port, destroyed afterwards), then runs two threads that
   record overlapping grants while a seam holds both between the check and the insert. Exactly
   one is recorded and one is refused. It runs a second time after a void.
   If no local PostgreSQL toolchain exists the test prints SKIP; here it ran against 16.

**L1** `billed_usage_cad` is a total only when the provider reported every row. With some rows
reported it is UNKNOWN; `billed_state` says COMPLETE, PARTIAL or UNKNOWN, and the reported part is
`billed_reported_partial_cad`, labelled partial.
**L2** With no stated expiry, `expiry_basis` is `period_end` (the period the owner recorded), on
the record result, the accounting and `split()`. UNKNOWN remains only for a legacy row with no
period.
**L3** Currency and dates are validated whole. The route no longer truncates to 3 or 10
characters, so `USDX` and `2026-11-01junk` are refused. Dates must match YYYY-MM-DD exactly
(`date.fromisoformat` alone also accepts `20261101` and `2026-W45-1`).
**L4** The evidence note and the void reason are screened with `ops.log_secret_guard.scan_text`.
A hit is a refusal that names the pattern kind only; the note is never stored, audited or
echoed. The provider name is no longer echoed in a refusal either.
**L7** `model_allocation.md` cites `publish/motif_fidelity.py:375-377` (provider chosen at 375,
the unguarded `provider.see` call at 377) in the table and in F-A4. The earlier 374/375 were off by
a few lines.

### Tests and mutants

Eight new tests in `tests/test_eng_credits.py` (now 22) plus two updated for L1 and L2:
nonsense amounts and periods (M1.1, M1.2); currency and dates, at function and route level (L3);
void (function, route, step-up, audit, never deleted, frees the period, stops drawing); secrets
in the note and the reason (L4); the SQLite race; the PostgreSQL 16 race.

Required suite set (14 suites, `JOBS=4 SUITE_REGISTRY=0`, venv from the lock files, no
PYTHONPATH): **236 passing, 0 failing suites**.

**Mutants: 18 of 18 killed** (`PYTHONDONTWRITEBYTECODE=1`; each mutation made `test_eng_credits`
fail; source restored after each run):

| # | Mutation |
|---|---|
| F1 | A bool amount accepted |
| F2 | A string amount accepted |
| F3 | Amount cap removed |
| F4 | Period-length cap removed |
| F5 | Overlap lock removed (killed by both the SQLite and the PostgreSQL race) |
| F6 | A voided grant still blocks an overlap |
| F7 | A voided grant still draws in `split()` |
| F8 | A voided grant still counted in the accounting |
| F9 | Void does not mark the row |
| F10 | A grant can be voided twice |
| F11 | Void owner check removed |
| F12 | Secret screen removed |
| F13 | A partial billed figure read as the total |
| F14 | `expiry_basis` reads "stated" for a period-only grant |
| F15 | Loose date parsing (truncate) |
| F16 | Currency prefix accepted (`USDX`) |
| F17 | Void route without step-up |
| F18 | Void route without the audit row |
