# Handoff: wave-3 lane SPEND (K5a spend attribution + K5b gateway paid-call discipline)

Branch `claude/w3-SPEND` (merged `claude/visual-investigation` cfb19b5, no conflicts). Owned paths:
`gateway/**`, `finance/**`, and only the gateway call sites in `runtime/release.py`. No paid
call was made in any test or proof: every transport is an `EchoProvider` or an injected stand-in.

## Priority items

| Item | Status | Evidence |
|---|---|---|
| F-307 / F-339: a paid model or image call is never repeated when a job lease is reclaimed | COMPLETE | `gateway/paid_calls.py` is a write-ahead intent keyed by (effect, job, request sha256, occurrence). It claims through `queue.effects.claim` (interface only, no queue/** edit). It is guarded at the transports (`AnthropicProvider.complete/see`, `images.generate`). OK replays with zero tokens and is not billed. PENDING (worker died mid-call) is counted once at the estimate, not re-sent, and opens a P1. Tests: `test_w3_spend_paid_calls` (8), including two real-subprocess SIGKILL proofs. Runtime consumer: the worker's `spend_report.attributed_to` opens the job scope. |
| Single-path spend recording | HOLDS | `ModelGateway._record` / `spend_report.record` are the only writers. Each bill carries `paid_call_key`. `test_spend_stays_single_path_through_job_gateway`. |
| W-8: release-chain gateways via failover | COMPLETE | `failover.job_gateway` wraps `gateway_for`. A CACHED `(None, decision)` falls back to the declared tier (never a None gateway). PARK raises `Parked`. The 4 release handlers in `runtime/release.py` (blinded, tournament, expedition, seasonal cycle; 4 call sites) use it. `test_w3_spend_gateway_w8` (5). |
| Routing task `laura.business_phrase` (for lane F) | COMPLETE (interface) | `routing.TASKS`: cheap tier, 220 output and 700 input tokens, cacheable. It has a new `stronger_fallback=False`, so it parks instead of paying Sonnet. `ALLOCATION["laura.business_phrase@1"]=0.01` (CA$1/month). `economics`: support class. The helper is `gateway.laura_phrase.phrase(db, statement=, facts=, agent="orchestrator", job_id=, provider_factory=)` → `{text, source: model\|cache\|deterministic, reason, cost_cad}`. It never raises for money, health or a missing provider. It refuses any answer that adds a figure not in the facts. `test_w3_spend_laura_phrase` (6). |

## K5a / K5b rows

COMPLETE (test + live consumer):
- **F-303, F-320**: `finance/economics`, `unit_cost`.
- **F-183, F-184, F-110**: `spend_policy.vocabulary / binding_ceiling / escalation`. These go through `spend_report.governance` to `app/main.py` spend controls.
- **F-105**: governance `honesty` keeps measured, estimate/upper-bound and historical-unknown spend apart.
- **F-305, F-308, F-315, F-326**: `spend_hygiene.sweep` covers the unattributed tolerance, retry storm, oversized input, hourly spike and repeat paid request. It runs in the governor pass.
- **F-306**: the content-keyed cache plus the repeated-request detector. This holds for the laura phrase and `cached_analysis` paths only.
- **F-307, F-339, F-109**: `test_a_budget_refusal_survives_the_callers_rollback`.
- **F-474**: paid work only. A reclaimed render or call replays from the intent.

GATED:
- **F-106**: it compares only owner-reported provider figures (`ops.provider_accounts.REPORTED_FACTS`). A material, current-month gap opens an incident. A real provider billing comparison needs an Anthropic admin usage key, which is an OWNER ACTION.

OPEN (not addressed this wave; the audit reasons still stand):
- F-070, F-103, F-304 (listing id / image count need CostEntry columns), F-319, F-322, F-325, F-629.
- F-098, F-309, F-310, F-311, F-312, F-313, F-314, F-316, F-317, F-318, F-328, F-472.
- F-659: general intra-handler checkpoints beyond paid calls.

## Tests (all PASS)

- Lane tests: `test_w3_spend_paid_calls` 8, `_gateway_w8` 5, `_hygiene` 6, `_attribution` 4, `_laura_phrase` 6.
- Touched-module tests: `test_spend_policy`, `test_model_access`, `test_v11_reliability_gateway`, `test_cost_governance_wave2`.
- Repository checks: `test_vacuity`, `test_secret_scan`.

## Wiring requests

- **Lane F**: call `gateway.laura_phrase.phrase(...)` for optional phrasing. Always render the result's `text` (it is the deterministic statement whenever no model answered). Show `source` internally only.
- **Lane D**: none required. The queue is used only through `queue.effects.claim`, and `paid_call_records` self-creates via `paid_calls.ensure_table`. Optionally add `paid_calls.PaidCallRecord` to `core/db.py create_all`.

## Not verified

- Behaviour against a live Anthropic or image provider: no key, and paid calls are forbidden.
- Postgres advisory-lock behaviour of the intents: SQLite only.
- Threads started inside a handler do not inherit the paid-call scope (stated limit).
