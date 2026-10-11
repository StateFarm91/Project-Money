# W4-FINHEALTH — finance session recovery, zero-ceiling spend safety, truthful verify checks

Base: production 0417f35 (deployed 2026-10-11T13:58Z). Branch `claude/w4-FINHEALTH`. Nothing deployed,
no Railway/Etsy writes, no ceiling value changed, no model selection changed.

## 1. Finance `PendingRollbackError`

**Evidence.** Railway deploy logs for 69b50565 (0417f35) and 620d3f7f (fcb982d) carry only uvicorn
access/startup lines — no traceback text, so the error was not observable in logs. `/api/audit`
(`job.failed`, 294 rows) and `/api/queue/dead` contain no `PendingRollbackError`, so it was not a job
failure. It reaches the owner through a **reader**: the Command Center `accounting` provider.

**Root cause.** `app/command_center/providers._invoke` hands providers a bare SQLAlchemy `Session`.
`finance/accounting/schema._SessionDB.session()` wrapped that session with **no failure handling**.
`dashboard.summary` runs `posting_rules.post_all` (writes journal rows), catches its failure as
`"posting refresh failed: …"`, then keeps reading on the same session. If the posting failed at flush
(e.g. a Postgres-only `varchar(n)` overflow — SQLite never enforces lengths), the session was left in
"rollback required" state and the next read raised `PendingRollbackError`, so the whole Finance summary
became `Finance summary unavailable: PendingRollbackError: …`.

**Reproduced** (`tests/test_w4_finhealth.py::test_finance_summary_survives_a_failed_posting_refresh_via_the_provider_path`):
on the original `schema.py` the provider returns exactly
`Finance summary unavailable: PendingRollbackError: This Session's transaction has been rolled back due to a previous exception during flush…`.

**Fix.** `_SessionDB.session()` now rolls the session back before re-raising when the transaction is
already lost (SQLAlchemy marked it inactive, or a DBAPI error on Postgres aborted it). Nothing that was
not already lost is discarded; plain Python errors leave the transaction intact; the exception is always
re-raised; nothing is committed. The summary now renders with the refresh failure named in `reason`.

**Not verified:** which posting statement fails in production (no traceback retained). Production should
be re-read after deploy: if `reason` shows `posting refresh failed: <Type>`, that names the trigger.

## 2a. Spend safety — CA$0 agents billed before refusal (release-blocking, coordinator addition)

**Confirmed in code.** `gateway/anthropic.agent_daily_ceiling` returned `None` for a registered agent with
ceiling ≤ 0 — the "unknown spender" answer — so `check_budget_cad` skipped the agent check entirely. Every
path that relies on `check_budget_cad` (ModelGateway.complete_json/complete_each, images, vision, inspect,
tournament, laura_phrase, paid_calls, failover.decide, spend_policy, governor) therefore let `learn`, `coo`,
`laura` spend; ModelGateway refused only **after** the provider answered (post-hoc `spend_today > ceiling`),
and `spend_report.record` paths never refused.

**Reproduced** with a counting stub provider through `ModelGateway(registry=…)`: on the original gateway
`learn: provider asked 1 time(s) -- billed`.

**Fix.** A registered agent with ceiling ≤ 0 now returns a permission of `0.0`, so `check_budget_cad`
refuses any positive estimate **before** the reservation and before the provider call, with the refusal
audited (`spend_report.REFUSED_ACTION`, `which=agent_daily_ceiling`). Unregistered names still return
`None` (existing contract, `test_model_spend_paths`). Test: zero provider calls, zero cost rows, zero
reservations, three audited refusals; a positive-ceiling agent is unaffected. Compatible with LAURA1
3565b5f (`laura_briefing` refuses first on its own; the generic path now refuses too).

## 2b. `every_agent_has_a_cost_ceiling`

The three failing agents are **declared** CA$0 in `agents/registry.DEFAULT_AGENTS` ("publishes, activates,
spends and messages nothing"; `autonomy.charters`: "learn agent … CA$0 ceiling"). None makes model calls:
Laura's phrasing bills `orchestrator`; LAURA1's briefing refuses at CA$0. With 2a in place a CA$0 ceiling
is an enforced permission of zero, so the check now uses `registry.ceiling_audit`:

- OK: positive ceiling, or CA$0 that DEFAULT_AGENTS declares (`declared_no_spend`).
- FAIL (`misconfigured`): non-finite ceiling; zero/negative ceiling the declaration does not give
  (DB drift, or an undeclared agent).
- FAIL (`no_spend_agents_that_spent_today`): a declared no-spend agent with recorded spend today.

`spend_report.per_agent_today.over` now includes a CA$0 agent with any spend (it was hidden by
`ceiling > 0 and …`). Expected production result after deploy: this check passes with
`declared_no_spend: [coo, laura, learn]`.

### Owner proposal — daily ceilings for learn / coo / laura (NOT applied)

Current declared ceilings total CA$57.50/day against a CA$100/month model ceiling; the month is the
budget, a daily ceiling is a permission. Existing policy: read-only agents get CA$0 or a nominal CA$0.25
(meta-agents); Laura's phrasing has a 1% monthly allocation (CA$1.00).

| agent | today | proposal | rationale |
|---|---|---|---|
| learn | CA$0 | **keep CA$0** | `learn.scan` is gap-scanning of rows; charter says "no publication/spend". |
| coo | CA$0 | **keep CA$0** | orchestration/KPI/brief are deterministic; delegates to department agents that hold their own ceilings. |
| laura | CA$0 | **CA$0 now; CA$0.25/day if the owner wants model-written CEO briefings** | LAURA1's `laura.ceo_briefing@1` (STANDARD tier) is the only spend path that bills `laura`; 0.25/day matches the nominal read-only-agent tier and caps exposure at ≈CA$7.50/month inside the CA$100 month. Raising it is an owner decision (edit DEFAULT_AGENTS). |

OWNER ACTION (optional, CA$0 to decide, ≈2 min): approve or decline `laura` = CA$0.25/day. Cost of waiting:
Laura's briefing stays deterministic (complete, just not model-phrased).

## 2c. `no_unexpected_dead_letters_in_24h`

Live at 14:45Z the recent set was `mjs.scan` (Etsy 403, owned by ETSYCOMM) and `ops.sentinel`.
Evidence now adds `recent_by_type` (count, last_at, first error line ≤200 chars) and `recent_total`;
the verdict is unchanged and correct to be red.

**`ops.sentinel` root cause found and fixed** (unassigned, small): since the 0417f35 deploy every hourly
sentinel run dead-lettered with `StringDataRightTruncation … varchar(200)` on `INSERT INTO jobs` —
`ops/rebuild_graph.enqueue` builds `idempotency_key` from every changed ref (`stamp`), unbounded; SQLite
never enforced it. Keys that fit are unchanged; a longer key becomes prefix + `sha256(full key)` (≤200,
deterministic, change-sensitive). The 21 historical sentinel dead letters stay as history.

## 3. Recorded vs estimated spend

Verified correct to stay UNKNOWN: October has exactly one cost row — `image.probe`, `flux-2-pro`,
CA$0.027972, basis `modelled`, agent `gateway` (`/api/spend-report`). It is an image row
(`reconciles_by_construction`), so `token_priced_calls = 0` and drift is unmeasured. Reconciliation by
purpose: estimated 0.027972 = recorded 0.027972 (reservation price), `actual_cad: null` (provider billing
settlement OWNER-GATED). `model_spend_within_its_ceiling` reads the same 0.027972. Fix: the raw
`/api/spend-report` drift reported `calls_with_no_reservation_share: 0.0` with no token calls; now `None`.
The `state: healthy` field is left as is (pinned contract, `test_w4_cc_company`; `status: UNKNOWN` is the
measured flag).

## Tests

New `tests/test_w4_finhealth.py` (11). Focused existing suites run one at a time, all green:
test_rebuild_graph, test_cost_governance_wave2, test_model_spend_paths, test_w4_auditfix_ceiling,
test_spend_governance, test_v11_accounting_drill, test_v11_accounting_controller, test_cert_cost,
test_w4_ccfin, plus those listed in the commit. No existing assertion edited.

## Follow-ups (not done)
- `ops/health.py` over-ceiling reader still uses `ceiling > 0 and …` (same blind spot as per_agent_today).
- Production re-read after deploy: Finance summary `reason`, verify 13/13 except mjs.scan.
