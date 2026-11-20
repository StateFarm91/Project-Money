# ENG-DAILY slice 1: the daily production ledger, zero-output diagnosis and Daily panel

Branch `eng/daily`, based on `origin/claude/w6-INTEG2` @ 64146306. **Not merged, not deployed.** No production
database, queue or Railway reading was taken. Everything below was measured on fixtures.

## What this slice adds

### 1. Daily production ledger (`src/brambleloop/ops/daily_ledger.py`)
- **`ledger(db)`** gives per-UTC-day counts for the last 14 days, from persisted rows only. Every metric names its `basis`.
- **Readers are isolated.** Each reader has its own session, so a failed read (which aborts a PostgreSQL transaction) is UNKNOWN for that metric alone.
- **UNKNOWN is never 0.** A day is UNKNOWN when:
  - the source is unreadable (the error class is kept, never the text);
  - the day ends before the first recorded job;
  - the day is older than the source's retention horizon (`ops.retention`);
  - the shop is not registered on the watchlist.

  The shop sum is UNKNOWN if any shop is UNKNOWN. Today is flagged `today_partial`.

**Metrics and their sources:**

| Metric | Source |
|---|---|
| Scans per owner shop (9) | Anchor: `mjs.scan` jobs DONE that ran (a deferred run is not an attempt). The other 8 shops: their own entry in each `intel.watchlist_scan` row. |
| Concepts created, approved, refused | `radar_concepts`, bucketed by `at` / `decided_at`. |
| Concepts admitted to engineering | `supply.admitted` |
| Concepts held | `radar.supply_stall` readings |
| Held and refused reasons | Top 5, as tokens |
| Products started | `cir.drafted` |
| Products advanced per stage | `products.lifecycle.PIPELINE_JOBS` jobs DONE with useful work (`did_no_work`) |
| Certifications | `gate.certified` |
| US and UK PDFs | `assets.built` `detail.pdfs[US/UK]` |
| Images generated and verified | `image_candidates` (provider errors excluded; accepted = verified) |
| Images recovered | `paid_call.replayed` on `visual.` / `assets.` jobs |
| Completed galleries | `assets.listing_images_built` |
| Listing packages | `listing.package` results that are `ready_for_owner_review` |
| Etsy drafts | `store.published` / `store.publish_incomplete`, with ids |
| Live listings | `store.activated`, with ids |
| Lessons learned and applied | `lessons.at` and `acted_on_by[].at` |
| Dead letters and failures | Jobs DEAD; failures are the defect class from `classify_dead_letter` |
| Spend (CA$) | `cost_entries.amount_cad` |

**Honest gaps.** Some events have no timestamp of their own, so their metric counts the nearest timestamped row, and `basis` says so:
- lifecycle stage moves;
- the moment an Etsy id is set;
- the image verification time;
- "image recovered" (`_recover_generation` writes no row, so replays of paid image results are the proxy).

### 2. Zero-output diagnosis (`diagnose`)
A stage is diagnosed when its count is 0 today, or 0 over 24 h while its 13-day rate is above 0. A stage whose count today is UNKNOWN is diagnosed as `unknown`. Each diagnosis is recorded as an `OperatingReading(kind="ops.zero_output", period_key="<day>:<stage>")`.

The causes it can name:
- **`suspended`:** the producer job types appear in `suspended_job_types`, with the breaker's reason.
- **`queue_empty_upstream`:** the upstream metric was 0 on both days and no producer job is open.
- **`gate_refusing`:** refusal rows in the last 24 h, with the top reasons.
- **`budget_refused`:** `budget exceeded` dead letters, or `spend.refused` / `job.budget_exceeded`.
- **`hold`:**
  - a policy hold is an unreviewed #39 change, scoped with `policy_holds_manufacturing`, so a publication-only change never holds manufacturing;
  - an owner hold is an owner veto or a withheld release.
- **`undiagnosed`:** none of the above applies.

**Safe actions (free paths only):**
- **`rearm`:** only when `swarm.orchestrate.rearm_probe` already releases the loop and `spending_job_type` is false. It enqueues the cadence job under the cadence's own key (`cadence_key`), so the scheduler can never double it. The breaker's incident is untouched.
- **`reoffer`:** only when supply offers wait, `supply.assess` reports open slots and no refusal (capacity, backlog and cost all clear), and no `supply.admit` is open. It enqueues one `supply.admit` per UTC day (`daily-reoffer:<day>`). The admission pass keeps all its own gates.

**Change requests.** Two situations file an `EngineeringChangeRequest`:
- a suspended loop with no re-arm (`failing_loop`; a spending loop always lands here);
- an undiagnosed zero (`missing_capability`).

ENG-IMPROVE's `improve/ecr.py` is on `eng/improve` (6ba519c), not on this base. The bridge calls `improve.ecr.file(...)` when that module is importable. Until then it records the exact `file()` kwargs as an `ops.ecr_pending` audit row. Re-runs re-file, deduplicated by ECR fingerprint, once ECR lands. No second `engineering_change_requests` model is defined, so merging cannot cause a table clash.

**Never touched:** gates, spend ceilings, owner exceptions and breaker incidents. A test checks the SpendLimit, PolicySnapshot, OwnerVeto and Incident counts, and `Incident.resolved`.

**Job wiring.** `ops.daily_ledger` runs every six hours through the handler in `runtime/release.py`, cadence `daily_ledger`. It is wired into:
- `FREE_JOB_TYPES`;
- the charters, agent registry and authority class;
- the orchestrator family `truth_defect`;
- the work key `recorded`.

The job writes `OperatingReading(kind="ops.daily_ledger", period_key=<day>)`.

### 3. Readback and panel
- **Readback.** `production_evidence.SECTIONS["daily_ledger"]` gives counts only. Spend is reduced to `spend_recorded` (true or false per day); no amounts, Etsy ids or reason text appear.
- **Panel.** `GET /api/cc/daily` is owner-only (`/api/cc` default-deny) and read-only. It returns the live ledger, today's recorded diagnoses, and a live read-only diagnosis preview (`act=False`, which writes nothing).
- **Front end.** The new More tab `#/daily` is `js/views/daily.js`. It reuses `barChart` as the sparkline, so UNKNOWN is a gap and the word "Unknown", never 0.
  - `sw.js` is now `cc-shell-v42` and includes the view.
  - The static bundle is 388,682 bytes, under the 400,000-byte budget.

### Retention
`KNOWN_READ_ACTIONS` gains five windowed actions:
- `intel.watchlist_scan`
- `listing.package`
- `job.budget_exceeded`
- `concept.intake_refused`
- `store.publish_blocked`

`UNRESOLVED_READ_SITES` documents `ops/daily_ledger.py::_causes`, which reads the `STAGES` refusal tuples over the last 24 h. `unknown_read_actions()` returns `[]`.

## Tests
- **`tests/test_eng_daily.py` (new): 19 of 19 pass.** It covers:
  - exact counts;
  - per-shop scans;
  - useful-only stage advances;
  - UNKNOWN never 0;
  - each diagnosis cause;
  - an ECR filed or pending;
  - re-arm on a free loop only, once;
  - a spending loop never re-armed;
  - re-offer only when admission is clear, once a day;
  - a read-only preview that writes nothing;
  - the owner-only route (anonymous and the operator token are both refused);
  - a readback that withholds spend, ids and reason text;
  - the worker-run wiring.
- **Mutants:** see the table below.
- **`test_v11_pwa_browser`:** 235 passes, 0 failures. It has two new Daily checks, and the More list is pinned with `daily`.
- **Required suites:** see the run table at the end (added by ENG-DAILY-FIX, review of a795be17 finding 6).


## Run table (added by ENG-DAILY-FIX)

The original slice-1 run would have shown `test_w4_readback_evidence` failing (22/23: no `daily_ledger`
readback row). After the fix, at `b77b1feb` (INTEG4 259e47c4 merged), clean tree, run record
`artifacts/suite_runs/20261120T045050Z-21073`, JOBS=6, 98 s:

| suite | OK | failed |
|---|---|---|
| test_eng_daily | 27 | 0 |
| test_v11_pwa_static | 86 | 0 |
| test_w4_readback_evidence | 23 | 0 |
| test_s4_p0_board | 18 | 0 |
| test_vacuity | 8 | 0 |
| test_w4_resume_runner | 40 | 0 |
| test_eng_improve | 24 | 0 |
| test_eng_learn | 13 | 0 |

TOTAL PASSING 239, 0 failing. `test_v11_pwa_browser` (not in the required set): 264 passes, 0 failures.
Details: `ENG-DAILY-FIX.md`.
