# handoff D (wave 3): Laura's Founder/CEO core

Branch `claude/w3-D` (pushed, non-force). Base `claude/v11-CANON` @ f0c2d12. `claude/visual-investigation`
was merged in three times, the last at the resume (A, B, C, E, G, H, I, K, K3, K6, K8, K10, K12, PRIV, SPEND,
TOOLS, CANON/D-FB-14, INT3). There were no conflicts. Phase stayed shadow.
There were no paid calls, no network, and no Etsy, Railway or customer effects.

## Interfaces (exported in the first commit, f64c4b2)

- **`brambleloop.laura.identity`** is the canonical identity API. It re-exports `laura.core.identity`:
  - `load(db)` / `current(db)` / `ensure(db)` return the verified record (version, sha256).
  - `genesis()` returns the **frozen** version 1 (laura-v15).
  - `record()` returns genesis plus the recorded amendments (current, laura-r2).
  - `public_profile()` and `voice_lint(text, surface=)`.
  - `amend(db, changes, owner_decision_id=, actor=, reason=)` is owner only.
  - `summary(db)` is the provider contract.
  - Constants:
    - `VISUAL_IDENTITY_ID` is `laura-r2-a42aeac7`, from `record()`.
    - `GENESIS_SHA256` is `8832a934…`, the original pin, restored.
    - `CURRENT_SHA256` is `20697b7c…`, genesis plus D-FB-14.
    - `RECORDED_AMENDMENTS`, `AUTHORITY`, `CHARTER`, `CONSTITUTION` and `PUBLIC_VOICE`.
- **`brambleloop.laura.executive`**:
  - `tick(db, queue=None, now=None)` returns a report.
  - `summary(db)` is the Command Center provider.
  - `priorities(db, status=, limit=)`.
  - `history(db, limit=, kind=)` returns her decisions.
  - `observe(db)`, `results_wake(db, queue)`, `EXEC_JOB = "laura.executive_tick"`.
- **`brambleloop.laura.core.constitution`**:
  - `review(db, proposal)` returns allow, block or owner_action, with `blocked_by`.
  - `challenge(db, raised_by=finance|product_truth|security, reason=, scope=)`.
  - `resolve_challenge(...)` works only for the raising department or the owner.
  - `open_challenges(db)`.

## Requirements and status

| Requirement | Status | Where |
|---|---|---|
| Canonical identity record: name, Founder/CEO role, charter, authority limits, public voice spec, visual id, truthful-identity rule | COMPLETE | `laura/core/identity.py` |
| **D-FB-14 re-pin as a recorded amendment** (urgent item a) | COMPLETE | See the D-FB-14 note below. |
| Immutable owner-controlled fields; changes only by a recorded owner decision | COMPLETE | Genesis hash is pinned. `laura_identity_versions` is hash-chained and refuses ORM update/delete. `amend` requires `actor="owner"`, a decision listed in `AUTHORISED_IDENTITY_AMENDMENTS` (`("D-FB-14",)`, which is spent: `amend` refuses a recorded amendment's id), and that decision in DECISION_LOG. A face change also needs `visual.canonical`'s own list. A raw-SQL tamper raises `IdentityTampered`, which blocks her tick and her constitution. |
| Executive tick: Laura → COO → departments → results → Laura | COMPLETE | `laura/executive/loop.py`. Cadence `laura_executive` runs every 5 min. She is also woken when the COO closes a mission she delegated. |
| Reads company state | COMPLETE | `autonomy.status`, KPI snapshots, owner actions, incidents, defect dead letters, and the finance/slo/learn/seo/ads/visual_rnd providers. A missing provider means UNKNOWN "not built". |
| Durable priorities with reasons and evidence | COMPLETE | `laura_priorities` table. It holds working state, not history. |
| Delegation through the existing COO mission mechanism (GREEN/SAFE only; protected work becomes an owner action) | COMPLETE | `orchestrator._enqueue_mission` / `_raise_approval` are reused unchanged. |
| Honest review with did_no_work | COMPLETE | Reuses `orchestrator.reconcile_missions`. |
| Challenge weak work | COMPLETE | A no-op gets a department review challenge. A failure gets one rework. If that is weak too, it becomes a routed Lesson (no loop). |
| Durable history of real actions only | COMPLETE | Stored in **laura.memory**, operational tier, `decision/<hash>`, per the integrator ruling. It is written by `Principal.laura()` and sourced to the company_timeline event. Public/customer principals are refused. |
| Constitution: Finance / Product Truth / Security can block her; she cannot expand authority | COMPLETE | See the details below. |
| Model independence | COMPLETE | The tick is deterministic and calls no model. `cognition` (env `BRAMBLELOOP_LAURA_MODEL`) is only a label on her decisions. |
| Empty queue → safe useful work | COMPLETE | Takes the departments' own evidence-driven generator candidates, at most 2 per tick. This now includes Visual R&D `next_work`. |
| Wiring (b), K3: `listing_outcomes` cadence, cfo grant, JOB_BANDS | COMPLETE | Commit d183b77. Test: `test_w3_laura_core_wiring::test_each_wired_job_…` |
| Wiring (b), H/H2 `visual.rnd` | COMPLETE | See the visual.rnd note below. |
| Wiring (b), SPEND: `PaidCallRecord` in create_all | COMPLETE | `core/db.py` imports `gateway.paid_calls` |
| K15, F-909 (`tax_pack`) / F-916 (`handoff`) runtime caller | COMPLETE | See the K15 note below. Test: `test_period_pack_…` |
| K15, F-907 (`attribution`) unreached | COMPLETE | `attribution.report(db, period=)` is part of the period pack (`cost_attribution`). |
| K15, importlib providers (F-913/914/915/927, seo.status, learn.improvement_status) | PARTIAL | See the K15 note below. |

D-FB-14 re-pin:

- Genesis is frozen again as `laura/core/genesis_r1.json`, hash `8832a934…`, the original pin (laura-v15).
- D-FB-14 is **version 2**: an owner amendment applied once by `ensure()` from `RECORDED_AMENDMENTS`. It changes exactly `rulings` and `visual_identity`.
- The amendment is checked in three ways:
  - D-FB-14 must be in `AUTHORISED_IDENTITY_AMENDMENTS`.
  - It must be in DECISION_LOG when the log is present. The deploy image does not ship the log; the test proves it is logged.
  - It must match `visual.canonical.REVISIONS`: the r2 id, the prior id equal to genesis's id, the r2 reference hashes, and an unchanged face hash.
- The expected head is pinned in `CURRENT_SHA256` (`20697b7c…`).
- A database written before D-FB-14 (lane F's case) stays valid and gains version 2. Lane F's harness re-pin is no longer needed.
- Test: `test_a_database_holding_only_the_original_genesis_gains_the_d_fb_14_version`.

visual.rnd (H/H2) wiring:

- `create_all` imports `visual.rnd.models`.
- The handler `visual.rnd.cycle` is in `autonomy/visual_rnd_job.py`. It reports an honest `work_done` and refuses a reported paid execution.
- CADENCES: `visual_rnd` (publishing, 6 h). The publishing grant, the exploration band and SAFE_GENERATED all include it.
- `generators.PROVIDERS["visual"]` reads `visual.rnd.status.next_work`. It takes GREEN items only, including the H2 `hero_calibrate` / `hero_challenge` items. GATED_SPEND, spend > 0 and paid kinds are dropped.
- Laura's `visual_rnd` priority delegates `visual.rnd.cycle`.

K15 runtime caller:

- New job `finance.accounting.period_pack` (`autonomy/period_packs.py`): cfo, daily, housekeeping band, finance-generatable.
- It runs `tax_pack.pack` and `handoff.pack` for the last closed month and stores them as one `company_memory` row `finance.period_pack:<YYYY-MM>`, with a timeline event when the content changes.
- It writes no file and files nothing. `work_done` counts only a content change.

K15 importlib providers:

- `autonomy.generators.provider_module` imports every provider with static import statements, and `laura.executive.loop` uses it. They are reachable: `test_k15_provider_modules_are_reachable…`, with a negative control on attribution.
- `app/command_center/providers.py` still uses importlib. That file is lane F's; see wiring request 1.

How the constitution works:

- **Finance**: `check_spend` (writes `acct_challenges`), paused spend scopes, and Finance challenges.
- **Product Truth**: an unresolved incident that halts publication blocks store, growth, visual and product-design work.
- **Security**: a P0/P1 security-class incident or a Security challenge blocks everything except never-paused departments (F-889 rule). A disabled agent is never routed around.

## Files

- New: `laura/__init__.py` (identical to lane E's), `laura/identity.py`, `laura/core/{__init__,identity,models,constitution,history}.py`, `laura/executive/{__init__,loop,handlers,proof}.py`.
- Shared files lane D owns:
  - `core/db.py`: create_all imports laura.core.models, visual.rnd.models and gateway.paid_calls
  - `agents/registry.py`: the `laura` agent (GREEN, CA$0, only `laura.executive_tick`; protected and truth-changing types forbidden), plus the grants `cfo += listing.outcomes, finance.accounting.period_pack` and `publishing += visual.rnd.cycle`
  - `runtime/worker.py` CADENCES: `laura_executive` 300 s, `listing_outcomes` (cfo, daily), `visual_rnd` (publishing, 6 h), `accounting_period_pack` (cfo, daily)
  - `swarm/orchestrate.py` JOB_BANDS: laura tick, listing.outcomes, visual.rnd.cycle (exploration), period_pack (housekeeping)
  - `autonomy/charters.py`: executive gets the `laura.` prefix and agent. Visual and finance generatable lists and SAFE_GENERATED gain the two new types.
  - New: `autonomy/visual_rnd_job.py`, `autonomy/period_packs.py`, `laura/core/genesis_r1.json`. `autonomy/generators.py` gains the visual provider and `provider_module`.
  - `autonomy/handlers.py`: imports the laura, visual_rnd and period_pack handlers and the results wake. It also declares WORK_KEYS for `listing.outcomes`, `visual.rnd.cycle` and `finance.accounting.period_pack` with setdefault (see wiring request 2).

## Tests

Run with the venv interpreter, `PYTHONPATH=src`, after the last merge unless noted. All passed.

| Suite | Result |
|---|---|
| `test_w3_laura_core_identity` | 11/11 |
| `test_w3_laura_core_constitution` | PASS |
| `test_w3_laura_core_continuity` | PASS (model/provider swap, process and scheduler restart, context reset) |
| `test_w3_laura_core_executive` | PASS |
| `test_w3_laura_core_wiring` (new) | 6/6 |
| `test_vacuity`, `test_secret_scan`, `test_reachability` | PASS |
| `test_cert_wiring` | 16/16 |
| `test_v11_wiring`, `test_v11_autonomy_orchestrator`, `test_cert_orchestration` | PASS |
| `test_r2_autonomy_useful_work`, `test_r2_autonomy_scheduler_isolation`, `test_roles`, `test_swarm`, `test_k3_listing_outcomes` | PASS |

The second group ran before the final merge. Identity, wiring and useful_work were re-run after it.

## Runtime proof

`research/final_build/w3/evidence/D_runtime_proof.json`: the real embedded runner, SHADOW, temp SQLite, closed network, 660 s, commit a1036898.

| What | Result |
|---|---|
| Identity provider | OK: **version 2**, sha `20697b7c…`, `laura-r2-a42aeac7`, applied on boot |
| Laura's ticks | 3, all useful (8 `priority.set` decisions), 0 failed |
| Jobs | 248 |
| Cadences that ran | `listing.outcomes` done; `visual.rnd.cycle` was running at the end (CPU contention); `finance.accounting.period_pack` was still queued |
| Spend | CA$0, 0 cost rows |
| Protected types generated by the orchestrator | 0 |
| Dead letters | 10, all `store.publish` refused by the SHADOW capability gate (the listing chain's own fail-closed path, not Laura's or the orchestrator's) |
| Laura delegations | 0. The company was busy, not idle, so she set priorities only. Delegation, review and challenge are proven in `test_w3_laura_core_executive`. |

This is a bounded window, not a soak.

## WIRING REQUESTS

1. **Lane F**, `app/command_center/providers.py::_resolve`: replace `importlib.import_module` with `brambleloop.autonomy.generators.provider_module(mod_name)`. It falls back to importlib for anything it does not list. This closes K15 for the Command Center path (F-913/F-914/F-915/F-927). Also drop the harness re-pin in `tests/w3_laura_cc_harness.py`, which is no longer needed.
2. **runtime/pipeline.py owner**: add to `WORK_KEYS`:
   - `"visual.rnd.cycle": ("work_done",)`
   - `"finance.accounting.period_pack": ("work_done",)`
   - `"laura.executive_tick": ("work_done",)`
   - `"listing.outcomes": ("exports_processed", "recorded_listings")`

   They are declared today by setdefault from lane D modules.
3. **Lane F** (optional): render the `finance.period_pack:<month>` memory row as the accountant pack card, with "prepared, not filed".

## Open defects / could NOT verify

- No completed `visual.rnd.cycle` or `period_pack` job within the 10-min runtime window, because of 4-CPU contention. Both handlers were run directly in a smoke and tests: cycle 131 s, work_done 14 then 4; pack work_done 1 then 0.
- `routing laura.business_phrase` was not registered; that is the gateway's job, not lane D's.
- The deploy image does not ship DECISION_LOG.md. Runtime `amend()` therefore cannot verify a new decision in production. This is pre-existing and fails closed.
