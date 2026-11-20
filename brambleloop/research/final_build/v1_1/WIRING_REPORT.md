# v1.1 integrator wiring report (WIRE)

Branch `claude/v11-WIRE`. Base: `claude/visual-investigation` @ a1d3fac, which has lanes A to I merged.
Phase stayed shadow throughout. Nothing was pushed, nothing was deployed, Railway was not touched, `railway.json` was not changed, and nothing was spent.

## Applied

| Request | Where | What |
|---|---|---|
| A-1, C-opt, E, G-1, H-1, I W-6 | `core/db.py` `create_all` | Imports `autonomy.models`, `seo.models`, `finance.accounting.models`, `growth.ads_readiness`, `ops.slo` and `app.command_center.models`. A worker-only or scheduler-only process now creates every v1.1 table. |
| A-2 + the ledger question | `core/continuity.py` | See "Continuity decisions" below. |
| G-2/3/4, E, H-3, I W-4 | `runtime/v11_wiring.py` (new; imported by `runtime.pipeline`), `runtime/worker.CADENCES`, `agents/registry.py` | The job types are wired as listed in "Wired job types" below. |
| A bands | `swarm/orchestrate.JOB_BANDS` | `autonomy.orchestrate` is in band `truth_defect`. `department_review` and `morning_handoff` are `housekeeping`. The `setdefault` shim in `autonomy/handlers.py` has been removed. |
| next_work providers | `autonomy/generators.provider_candidates` and `PROVIDERS` | See "next_work providers" below. |
| A charters | `autonomy/charters.py` | New entries in `generatable`, and a `SAFE_GENERATED` entry for each, quoting the handler's own GREEN declaration. `seo.` is now a `store_commerce` prefix. |
| I W-1/W-2 | `app/runner.py`, `app/scheduler_entry.py` | A durable `scheduler` heartbeat row after every successful tick. A `worker` heartbeat row from worker 0, at most once every 60 s. The looping split scheduler now takes the `scheduler` lease (TTL 180 s), so a second scheduler sits idle. |
| I W-3 | `app/runner.py` | A stale-scheduler self-exit. See "Stale-scheduler self-exit" below. |
| B W-B1 | `runtime/release.py` | `consume.matching(..., subject=slug)` for `seo_search`, and `subject=f"support_case:{case_id}"` for `customer_experience`. |
| F | `app/command_center/{api,__init__}.py`, `app/security.py` | `GET /cc/store-preview`. See "Command center routes" below. |
| C/I W-5, A F-889 | `app/command_center/api.py` | Recovery and department routes. See "Command center routes" below. |
| Integrator note (cc_views) | `tests/test_v11_cc_views.py`, `app/command_center/tabs.py` | Fixed the timeline adapter and the test. See "Integrator note" below. |
| FX | `core/fx.py` (new) | See "FX" below. |

### Continuity decisions

- **Non-rederivable:** `company_memory` and `company_timeline`.
- **Non-rederivable, all six `acct_*` tables.** The journal is *posted from* source rows, but it cannot be re-derived from them:
  - corrections are reversals plus new versions;
  - a change made after a period lock is booked in the next open period;
  - the SHA-256 chain covers that history.

  Re-posting from today's sources would produce a different ledger. Statement lines are imported files that are not kept anywhere else. Period locks, exception resolutions and challenge verdicts are decisions taken on a particular day.
- **Non-rederivable, also:**
  - `ads_spend_proposals` and `ads_finance_challenges`, for the same reason as the verdicts above;
  - `cc_security_events`, which is a security audit trail.
- **Excluded from exports:** `cc_owner_sessions` and `cc_nonces`. This is tightening, with the same reasoning as `oauth_handshakes`: a restored copy must not accept the production owner's live session cookies.
- **Pre-existing defect fixed:** `NON_REDERIVABLE` listed `"ledger_entries"`, which is not the name of any table, so it labelled nothing. The real money ledger table is `ledger`. The new test asserts that every labelled name is a real table.

### Wired job types

| Job type | Cadence | Agent | Band | Notes |
|---|---|---|---|---|
| `seo.cycle` | 6 h | listing | housekeeping | |
| `finance.accounting.cycle` | 6 h | cfo | housekeeping | |
| `marketing.ads_readiness` | 1 h | growth | housekeeping | The handler refuses if the tick ever reports activation or a budget. |
| `ops.slo` | 15 min | orchestrator | truth_defect | Also added to `LIVENESS_JOB_TYPES`, so it is never backed off. |

### next_work providers

The four providers come from lanes B, E, G and H. Only an item that meets all of these conditions becomes a candidate (`source="provider"`, value 60):

- it is internal, with no owner, gate, external effect, spend or `blocked_by`;
- it maps to an existing GREEN job type in the department's `generatable` allowlist;
- that job type is not protected, not already open, and has not succeeded within the last hour.

How each provider's items map:

| Provider | Becomes a candidate | Never queued |
|---|---|---|
| learn | `improve.sandbox`, `improve.monitor`, `learn.scan` | — |
| finance | `run_cycle`, `post_rows` and `reconcile` items become `finance.accounting.cycle` | investigations, month locks, `connect_source` |
| seo | `seo.run_cycle` and `seo.review:*` become `seo.cycle` | taxonomy confirmation, Stats export, adopt |
| ads | `ads.eligibility_tick` becomes `marketing.ads_readiness` | owner evidence, organic baseline, economics, rechallenge (no handler) |

Owner and protected items stay with the module that already raises them as owner actions. The orchestrator's enqueue boundary would refuse them regardless.

The mission fingerprint is the provider key plus the job's last successful run. That gives one mission per run of the job, and lets noop-suppression apply.

### Stale-scheduler self-exit

- It runs only in a process that runs the embedded scheduler.
- It triggers when the last tick is more than 15 min old, or when there has been no tick within 15 min plus the start delay.
- The condition must be seen on **two consecutive** 60 s checks.
- A tick from an earlier `start()` is ignored.
- It logs at `log.critical`, then calls `os._exit(1)`.
- Opt-out: `BRAMBLELOOP_SELF_EXIT_ON_STALE=0`.

### Command center routes

**`GET /cc/store-preview`** (lane F). It is mounted ahead of the public `/cc/` static shell. `security.owner_session_route` names the exact path, so `auth.gate` requires an owner session; the PWA shell stays public. The response carries `Cache-Control: no-store` and `X-Robots-Tag: noindex, nofollow`. The global CSP applies.

**Recovery and department routes** (C/I W-5, A F-889):

| Route | Auth |
|---|---|
| `GET /api/cc/operations/recovery` (read) | owner session |
| `GET /api/cc/operations/soak?start=` (read) | owner session |
| `POST .../recovery/restart-job` | step-up |
| `POST .../recovery/release-lease` | step-up |
| `POST .../recovery/rerun-cycle` | step-up |
| `POST /api/cc/departments/{d}/block` | session + CSRF only (blocking is restrictive) |
| `POST /api/cc/departments/{d}/unblock` | step-up |

- A recovery refusal (returned or raised) becomes an audited 409 `REFUSED_BY_AUTHORITY`.
- Block and unblock write `AuditLog` rows.
- `ops.slo.summary` was already on the Operations tab through `providers.call("slo")`.

### Integrator note (cc_views)

The real lane A timeline is an envelope. The adapter in `app/command_center/tabs.py` used to promote an UNKNOWN envelope to OK. It now keeps the envelope's own status, reason and sources.

The test forces absence with `AbsentProvider("timeline")` for the UNKNOWN assertion. It also checks that a real `company_timeline` event passes through with its source and refs.

### FX

`core/fx.py` is now the single source:

- `ASSUMED_USD_PER_CAD = 0.715`;
- `ASSUMED_CAD_PER_USD = 1/0.715 ≈ 1.3986`.

Before this change the two values disagreed by 2.1%: 1/1.37 = 0.730, not 0.715. 0.715 was kept because the books, the fee schedule, `scale.target` and their tests already use it.

Modules that now import it: `gateway.routing`, `gateway.anthropic`, `gateway.images`, `gateway.image_bench`, `visual.d_judge`, `finance.currency` and `scale.target`. The pipeline's listing-fee reservation uses it too, so the fee is CA$0.28. That matches `fee_schedule.listing_fee_cad(0.715)`; the reservation was CA$0.27 before.

Recorded model and image spend is now about 2.1% higher. That is the conservative direction. **No ceiling changed.**

## Deferred

- **I W-8 (gateway call sites to `failover.gateway_for`).** Spend recording would stay single-path, because `gateway_for` builds an ordinary `ModelGateway`, so `_record` is still the only billing path. It is deferred for two other reasons:
  1. `gateway_for` returns `(None, decision)` for a CACHED decision. All four `runtime/release.py` call sites, and the `BriefingGateway` wrappers, would pass a `None` gateway into `blinded.run` and `prospecting.*`. Each needs cached-answer plumbing first.
  2. Fallback to a stronger, and therefore dearer, model changes spend behaviour on production paths. That should ship with its own tests per call site and owner visibility. It should not be a mechanical swap.
- **W-B3/W-B4 (optional tightening).** Not applied: neither is a one-line change. W-B3 needs a new obligation type in the release gate, and W-B4 needs routing in the render path.
- **W-7 (`railway.json`, `railway.watchdog.json`).** Not applied, by instruction; it needs owner approval.
- **Re-pointing `finance/books.py` at the journal** (lane E follow-up). Not done; it touches many readers.
- **AM-10 (registry permissions with no handler).** Decision: **keep them as declared-but-unbuilt, and neither wire them nor remove them.**
  - `gate.quality`, `gate.policy`, `gate.asset_truth`, `cir.twin` and `cir.reverse` already execute in-process inside `gate.certify`. In `gates/certificate.certify`, these are `build_twin` (L192), `reverse_compare` (L221), `check_assets` (L264) and `check_listing` (L285). Standalone handlers would create a second gate verdict outside the certificate, which could disagree with it. That would weaken "deterministic validation wins" rather than strengthen it.
  - `cir.revise`, `assets.render`, `content.draft`, `store.update`, `pricing.experiment` and `radar.competitor_snapshot` are unbuilt capabilities. `store.update` and `pricing.experiment` are protected.
  - This set is a recorded decision, pinned by `tests/test_roles.py::DECLARED_BUT_UNBUILT` ("a design statement from the Master Plan"). Removing the entries would re-litigate that decision.
  - The AM-10 entry in the autonomy map now records this decision instead of OPEN.

## Tests and proof

All suites were run with `/home/user/Project-Money/brambleloop/.venv/bin/python` and `PYTHONPATH=src`.

**Main run:** 60 suites, 910 OK, 0 genuine FAIL. That covers:

- every `test_v11_*` suite except the PWA browser suite;
- continuous_operations, chaos, cert_orchestration, cert_lanes_capacity, persistence, health, roles, swarm_runtime, cert_wiring and fb4_ops;
- route_auth_default_deny, web_security, secret_scan, vacuity and platform;
- release_versions, search_truth, gateway and model_spend_paths;
- continuity, currency, cert_commerce, model_access, fee_schedule, model_provider, cert_cost, oauth_security_audit, customer_data_auth, cert_claude_independence, improve_handlers and mine.

In that run, `test_cert_lanes_capacity` failed one test with "runtime graph source changed during analysis", because I was editing a source file while it ran. It passes 15/15 on re-run.

**Re-run after the last edits:** 13 suites (v11_wiring 14, v11_wiring_cc 5, cc_views 13, cc_auth 16, cc_actions 7, continuity 15, oauth_security_audit 87, cert_lanes_capacity 15, route_auth 7, web_security 11, vacuity 7, secret_scan 6, autonomy_timeline 6). All OK.

**Runtime proof:** `evidence/WIRE_runtime_proof.json`. Lane A's `autonomy.proof` child ran the real `app.runner.start()` for 600 s on the committed wiring code. The run was in shadow, on a temporary SQLite database, with no credentials and every proxy pointed at a closed port. Nothing was enqueued by hand.

- **Jobs:** `seo.cycle`, `finance.accounting.cycle`, `marketing.ads_readiness` and `ops.slo` (twice) were all enqueued by the scheduler and finished DONE under the real worker. 261 jobs ran in total.
- **Heartbeats:** 30 scheduler and 9 worker heartbeat rows.
- **Spend:** 0 `cost_entries` rows.
- **Orchestrator:** generated 0 protected jobs.
- **Dead letters:** 10 `store.publish`, all from the existing release chain and refused by SHADOW.
- **Provider missions:** none fired in this window, because the cadences had already run each job less than 1 h earlier. Provider-to-mission reachability is proven in `test_v11_wiring` instead, against the real orchestrator and queue.

This was a bounded run, not the 24-hour soak.
