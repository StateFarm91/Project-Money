# REVIEW REQUEST — eng/stale-rebuild-loop

Branch `eng/stale-rebuild-loop`, from `origin/claude/w6-INTEG1` @ 26762746. Nothing deployed;
no Railway, production, secrets, Etsy or spend touched. Final SHA: see the last commit on the
branch (this file is in it).

## Problem 1 — stale-artefact loop never converged (systemic halt #380)

Reproduced on a real chain (cloudline-baby-blanket through `Worker.run_once`, SQLite): move
`CHAIN_VERSION` → sentinel → drain. On the old code 16 of 25 artefacts verify, but all 9
`marketing_asset` rows stay stale through 3 verify checks. `rebuild-incomplete` then opens, and
the next sentinel reports `already_queued: 25` with no job in flight. That is the production
shape.

### Root causes

**(a) `already_queued` with no live job.** `rebuild_graph.enqueue(per="product")` appended to
`already_queued` in every DuplicateJob path that did not enqueue. That includes a first-attempt
key held by a DONE job that is waiting out `RETRY_AFTER`, a daily retry already used, and a
held product. So production's 50 were finished attempts, not queued work. Nothing was "stuck in
a queue".

**(b) Rebuilds never verified.**
1. *Marketing was refused on every attempt.* One `chain.rebuild` remakes the PDF, charts and
   copy, then reaches `marketing.schedule`. The sentinel's `stale-artefact:pdf:…` rows for
   those just-remade artefacts are still open, because only the next hourly sweep closes them.
   `release_gates._halting_other_than_staleness` waived only the outstanding marketing rows, so
   the gate saw "another halting incident" and blocked marketing. Production's stale estate is
   mostly marketing (126 stale), so nothing ever completed.
2. *The verify binding could never hold across products.* The per-product job carried every
   moved ref in the estate (`cir:<other product>`, …). `binding()` required each one on the
   row, so a correctly rebuilt row read as unbound.

**(c) No resolution path.**
- `rebuild-incomplete` was opened without `product_slug`, and nothing ever resolved it, not
  even a verified rebuild.
- A refused rebuild (withheld release) finished DONE with no incident and was retried daily
  without end: a silent loop.
- The systemic halt's own reconcile (`escalate_systemic` via ops.truth) was correct. It never
  fired only because the per-product staleness underneath it never cleared.

### Fix
- `rebuild_graph.enqueue`: `already_queued` now means a `chain.rebuild` for the product is in
  flight (pending, running or failed). Otherwise the product is `retry_waiting` or
  `retry_held`. Each per-product job names only the moved refs its own artefacts record (plan
  rows carry `refs`).
- `_targeted_rebuild` binding: a ref the row does not record is ignored. Every ref it *does*
  record must still equal the new fingerprint, and job binding is unchanged.
- Verify pass: bound, verified completions resolve their `stale-artefact:*` rows. When nothing
  is outstanding, `rebuild-incomplete:<slug>` is resolved too (`_close_on_verified_rebuild`).
  Nothing is closed for an unbound row or on a job's say-so.
- `rebuild-incomplete` (`_rebuild_incomplete`):
  - filed with `product_slug`;
  - `report_count` counts failed attempts at *this* change, and resets when the fingerprints
    differ;
  - at `REBUILD_MAX_ATTEMPTS = 3` it carries `held`, a named reason built from the latest
    `marketing.blocked`/`chain.rebuild_refused`, and is raised to P1.
- `release_gates`:
  - staleness families are `{stale-artefact, rebuild-incomplete}`, so a systemic halt made
    only of them never holds;
  - the marketing waiver also covers sentinel rows whose artefact reads FRESH now
    (`publication_gate` returns `fresh`) and non-exhausted rebuild-incomplete rows;
  - `retry_hold_reason` returns the named reason for an exhausted row, and holds while the
    newest certified release is withheld. That check is read live, so the hold lifts by itself
    when the gate clears.
  - Publication (`halted`/`blocks`/`reasons`) is unchanged.
- Sentinel: resolves `rebuild-incomplete:<slug>` when the deterministic provenance check reads
  none of the product's artefacts stale. Also records `rebuild_retry_waiting`/`_held` in the
  propagation audit.
- `production_evidence.stale_rebuilds` adds:
  - `last_propagation_retry_waiting`, `last_propagation_retry_held` (+ reasons);
  - `rebuilds_refused_7d` (+ reasons);
  - `open_rebuild_incomplete`, `rebuild_incomplete_held`.
- `retention`: decisions for the two audit actions now read by name (`chain.rebuild_refused`,
  `marketing.blocked`, both windowed). The retention guard caught this.

Nothing is marked fresh without a verified rebuild. Incidents close only on bound completion
evidence or the provenance check.

## Problem 2 — model.probe billed the same request 4×/24 h
Root cause: the `paid_calls` store replays within one job only (key `job:<id>`), and the
6-hourly cadence makes a new job each time. Each run therefore re-asked a question already
answered. Fix: `anthropic.probe_if_due` reuses a successful probe younger than 24 h, writing an
audited `model.probe` row marked `reused` at CA$0. It re-asks when:
- the funding owner-action is open;
- an `anthropic.*` paid call failed (`DECLINED`/`FAILED_BILLED`/`UNCERTAIN`) since that probe;
- the last probe failed;
- or it is an owner on-demand run (`force`).

`handle_model_probe` uses it. The gate never opens on a reuse (only an earlier success is
restated), and smoke recency still sees a fresh row.

## Tests — `brambleloop/tests/test_eng_stale_rebuild_loop.py` (new)
11 tests on SQLite, plus 9 production-shaped ones on a disposable **PostgreSQL 16** cluster
(the `_disposable_cluster` pattern). Results: **20/20 pass on the fix; 20/20 fail on
26762746.** On the old code:
- the e2e test fails on its real assertion (9 marketing artefacts still stale);
- the evidence test fails on `already_queued` with zero unfinished jobs.

Cases covered:
- production's 14 slugs: finished attempt → waiting not queued; live verify job → queued;
  held → held;
- own-refs payload;
- marketing waiver;
- bound / reset / named hold;
- withheld hold;
- staleness-only systemic halt holds nothing and resolves after the sentinel clears rows
  (`escalate_systemic`);
- real-chain e2e: stale → enqueued → rebuilt → verified → incidents resolved in one attempt,
  plus foreign-ref binding;
- P2: 4 cadence runs/day bill once, a failure since → re-asked, `force` → asked, a failed
  probe is never reused, cadence handler end to end.

## Suites run (targeted; full suite not run)
- `test_rebuild_graph test_w4_prodfix test_w4_fmgate_rebuild_key test_w4_autonomy_idle_departments
  test_cert_publish_gates test_cert_rebuild_chain test_w4_listready test_artefacts
  test_w4_readback_evidence test_w4_owner_incidents test_w6_fix_only_rebuild test_w3_k7_ops_truth
  test_w4_finhealth test_w4_placemat_reprice`: 177 passing. That run reported 3 suites failing;
  each one, re-run standalone:
  - `test_w4_readback_evidence`: env only (`httpx2` missing from the venv). After installing
    it, **23/23 OK** on the fix.
  - `test_w6_fix_only_rebuild`: **18/18 OK** standalone on both base and fix. The earlier
    `_reprice_on_plan_drift` source-inspection failure did not reproduce; the first run was
    against a mid-edit dirty tree.
  - `test_w4_listready`: 40 OK / 1 FAIL, **identical on base 26762746**. Pre-existing, in
    `test_f8`: "unclassified Etsy write call site `app/command_center/approvals.py
    _standing_policy`" (from the WS4 standing-policy merge). Not touched here.
- `test_w4_ondemand test_w4_smoke test_health test_funding test_w4_funding
  test_w4_fmbatch1_provider_health test_w4_auto_spend_wiring test_cost_governance_wave2`:
  **140 passing, 0 failing**.
- `test_w4_fmbatch1_retention_guard test_w4_retfix_retention_keys test_w4_firstsale_retention`:
  **15 passing, 0 failing**.

## PG status
PostgreSQL 16.15 is installed locally, and `psycopg` 3 was added to the test venv (the
requirements pin `psycopg2-binary`; the engine URL resolved to `psycopg`). All 9 production-shaped
tests pass on PG and fail on the old code on PG. The e2e real-chain test is SQLite only
(rendering-heavy).

## For the reviewer
- Behaviour change: an open `rebuild-incomplete` now carries `product_slug`. It therefore
  counts in `IncidentTracker.open_incidents(slug)` and `systemic_evidence` (as a staleness
  family). Production rows written before this have no slug. The sentinel resolves them by the
  slug in their signature.
- `REBUILD_MAX_ATTEMPTS = 3` attempts per change, at most one per day, so a product is held
  after about 3 days.
- `MODEL_PROBE_REUSE = 24 h` means 1 billed probe per day instead of 4.
