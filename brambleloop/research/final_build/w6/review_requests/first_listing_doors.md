# Review request: ENG-FIRSTLIST owner execution doors (G1 to G4)

Branch `eng/first-listing-runbook`, base `claude/w6-INTEG1` @ 6e47d9bb. Runbook:
`research/final_build/w6/first_listing_runbook.md` (§7 lists the gaps).

## What changed

| File | Change |
|---|---|
| `src/brambleloop/ops/owner_execution.py` (new) | `queue_publication` and `queue_activation`: enqueue exactly one `store.publish` / `store.activate` carrying the owner grant id |
| `src/brambleloop/app/command_center/approvals.py` | actions `publication.execute` and `activation.execute` (both step-up, reason required); the publication card gets "Create the Etsy draft now" when a grant is live; a new ACTIVATION card for each verified draft (`Listing.state == "published"`); a publication card is no longer shown once the release is on Etsy |
| `src/brambleloop/app/command_center/static/js/views/approvals.js` | `fillPreviewParams`: `"<from x.preview>"` placeholders are replaced by the digest the card's own preview returned (none yet → "Preview first", nothing sent); the preview's section list renders as text |
| `src/brambleloop/app/command_center/static/sw.js` | shell `cc-shell-v30` |
| `src/brambleloop/ops/production_evidence.py` | read-only section `first_listing_readiness` |
| `ops/readback.py` | evidence row for that section, advisory (WARN/PASS, never FAIL) |
| `tests/test_first_listing_doors.py` (new), `scripts/suite_final_segment.txt` | tests; the suite matches the timing patterns, so it is listed |

## Please check specifically

1. **No gate weakened.** Each door's checks are a subset of the handler's own (grant via
   `publication_authority.resolve` / `activation_authority.validate`, phase via
   `core.phase.resolve`, kill-switch). The handlers are unchanged and re-check everything at
   their boundary. The doors only add earlier refusals. Is there any input by which a door
   queues a job the handler would then *accept* where it previously could not be reached?
   (Intended: yes, exactly the owner-granted job. No other.)
2. **Refusal under SHADOW is deliberate.** A `store.publish` refused in SHADOW is never
   re-driven (`DELIBERATE_REFUSAL_TYPES`) and keeps its idempotency key, so queueing it would
   spend the grant on a dead letter.
3. **Idempotency.** The key is `owner-publish:<slug>:<version>:<release[:24]>:<grant>` /
   `owner-activate:<listing_id>:<grant>`, so there is one job per grant. A second press returns
   the existing job (`queued: false`, `job_status`). A refused or dead job needs a new grant.
   An open (pending/running) job for the same `slug@version` also short-circuits. Is "new grant
   per retry" acceptable, given grants last 24 h and need step-up?
4. **Signing context.** Neither execute action is in `OWNER_GRANT_SIGNING_ACTIONS`. The doors
   never sign (the test pins it).
5. **The activation card** is built from `Listing.state == "published"` and a non-empty
   `etsy_listing_id`. `max_spend_cad: 0.29` is US$0.20 at 1.4154, rounded up.
6. **The readback projection** emits only `slug@version`, a 12-character release hash prefix,
   PASS/FAIL/UNKNOWN per gated section, package state, blocker `source` identifiers (regex
   `^[a-z][a-z0-9_.:-]{0,63}$`), counts and booleans. No copy, reasons or grant ids. It calls
   `publication_authority.evidence` per certified Launch-0 release (at most 8, all reads), the
   same reading the Approvals inbox makes on every load. Is that cost acceptable on the readback
   route?
7. **JS.** `fillPreviewParams` is pure, and its behaviour is run under node in the test: no
   digest → null, the wrong preview's digest → null, the right one substituted, other params
   untouched, input not mutated.

## Not changed (reported)

* G5: no path clears a deleted draft's local `etsy_listing_id`, so that `slug@version` cannot be
  drafted again.
* W3: `Listing.state = "published"` is a *verified draft*, while `LIVE_ON_ETSY` counts it as live.
* No draft-only lane for product drafts below `limited_production`. That would be an owner
  decision.

## Results

`tests/test_first_listing_doors.py`, 4/4. The end-to-end test, on FakeEtsy and a scratch SQLite
DB with the real certified `cloudline-baby-blanket` fixture, covers: the door refused in SHADOW
(no job); a reason required; the kill-switch denying; the door queuing one store.publish with
the grant id and a second press queuing nothing; the draft created and read back (12/12 fields,
6 images, US+UK files) with no fee row; the publication door closed once the draft exists; the
automatic activation carrying no id and refusing; the ACTIVATION card; the activation door
queuing; activation refused by `SAMPLE_PHOTO_REQUIRED` with no fee; then, with only that gate
held, a new grant leading to `store.activated`, Etsy `state: active`, one `etsy_listing_fee`
CostEntry of about CA$0.28, and the door refusing on an active listing. No socket was reached
beyond the fake's loopback port.

Targeted runs (`JOBS=4 SUITE_REGISTRY=0 SUITES=... bash run_tests.sh`, venv from the lock files,
no PYTHONPATH), all passing on the final tree:

* baseline on 6e47d9bb (before any change): test_rehearsal_past_shadow_success,
  test_activation_authority, test_etsy_exercise, test_publish_execution_gate,
  test_etsy_readback_observe, test_w4_readback_evidence, test_shadow_rehearsal,
  test_draft_intent_precreate_refusal, test_rc1_auth, test_v11_cc_actions: 137 passing, 0 failing;
* with the change: test_first_listing_doors, test_w4_readback_evidence (row count 15 → 16, new
  advisory row), test_v11_cc_actions, test_v11_cc_views, test_w4_agents_secfix,
  test_w4_cc_company, test_w4_ccgap_live, test_w4_ccgap_views, test_w4_ccrel, test_w4_ccux,
  test_w4_ccall, test_w4_ccpacket, test_w4_launchfix, test_w4_resume_runner,
  test_ws4_3_owner_signing_flow, test_w4_secpatch_public_surface, test_activation_authority,
  test_rc1_auth, test_w4_close6_readback, test_ws4_boundary, test_opus2_a9_u6_sweep_visibility,
  test_w4_fmbatch1_cost_learning, test_ws2_r1_competitor_scans, test_w3_k7_owner_queue,
  test_w4_ccgap2, test_w4_prodfix_policy_review, test_watchlist_cadence,
  test_w4_intelrec_watchlist, test_ws2_r6_r7_watchlist_env_dedupe, test_compiler, test_reverse,
  test_twin: all passing.

The first with-change run failed two suites, both now fixed: test_w4_readback_evidence (it pins
the advisory rows and the row count, updated as the watchlist-cadence branch did) and this
suite's own runner (it printed an indented `OK`, which the harness counts as no passes). One
run also listed `tests/_watchlist_sim.py`, a helper module with no tests, by mistake. Not a
full certification run.
