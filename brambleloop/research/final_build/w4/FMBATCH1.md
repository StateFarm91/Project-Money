# W4-FMBATCH1: the blocked-engineering launch-critical batch (3 Build 2 + 37 Final Master)

**Context**
- **Branch:** `claude/w4-FMBATCH1`, cut from `origin/claude/final-candidate-b997efd` (b997efd).
  Nothing else merged in.
- **Board:** `COMPLETION_BOARD_FINAL.json` on b997efd (generated 2026-10-20T12:00Z on 17bc373e).
  Selection: every row with `cls == blocked_engineering` that is Build 2 (3 rows: #11, #12, #195)
  or Final Master `launch_critical` (37 rows).
- **Production:** b931d17, SHADOW. Read only, with unauthenticated public GETs on 2026-10-21
  between 02:30Z and 02:56Z: `/health`, `/api/verify`, `/api/launch`, `/api/offsite`,
  `/api/audit?action=` `etsy.credential_health`, `etsy.taxonomy_refreshed`,
  `commerce.orders_ingested`. Saved in `evidence_FMBATCH1/`.
- **Not done:** no deploy, no POST, no Etsy write, no spend, no key, no Railway change.
  No full suite and none of the long suites.
- **Every criterion below is quoted from `master_registry.json` / `master_registry_v1_1.json` /
  `build2/requirements.json`.** No row is closed here. Proposals are in
  `OVERRIDES_PROPOSED_FMBATCH1.json` and `FM_REGATE_PROPOSED_FMBATCH1.json`, for the coordinator.

## 1. Triage counts

| class | rows | count |
|---|---|---|
| **(a)** engineering we could do now: **implemented on this branch** | F-010, F-381 | 2 |
| **(c)** already implemented: needs evidence, a merge or an acceptance | F-100, F-540, F-380, F-252, F-144, F-040, F-515@v0.16, F-834, F-846, F-872 | 10 |
| **(b)** blocked on a deploy, the owner or an external party (board label wrong or incomplete) | B2#11, B2#12, B2#195, F-273, F-538, F-005, F-007, F-009, F-243, F-247, F-396, F-628, F-437, F-371, F-495, F-654, F-701, F-849, F-880, F-881, F-895, F-923, F-924 | 23 |
| excluded: another lane owns the work | F-594 (W-FIRSTSALE2), F-733 (Laura canonical identity: W-LAURAONE / VISNEXT2), F-027, F-031, F-041 (W-LISTREADY launch image review) | 5 |
| **total** | | **40** |

**A finding that changes several rows: W4-CLOSE6 is not in the candidate.**
- `claude/w4-CLOSE6` (ff788bd) carries finished work on F-144, F-834, F-872, F-273, F-538,
  F-040, F-846 and Build 2 #11/#12, including coordinator-ACCEPTED proposals
  (D-W4-CLOSE6-OVERRIDES, D-W4-CLOSE6-FMREGATE, D-W4-CLOSE6-F846).
- It is an ancestor of neither b997efd nor `claude/w4-INTEG5` (INTEG5.md: "Not included:
  CLOSE6").
- Those rows read `blocked_engineering` on the board only because that work was never merged.
  This lane does not redo it. **Integrator action: merge CLOSE6 (or its accepted proposals).**

## 2. (a) Implemented on this branch

### F-010 Attribute Drift Monitor

**Criterion:** "Periodically re-check category/attribute schemas for platform changes."

**Before.**
- The daily `listing.taxonomy_refresh` re-read Etsy's tree and the pattern nodes' property
  schemas, and stored a new snapshot when the hash changed.
- Nothing consumed the change. A listing certified on a node Etsy renamed, removed or
  re-required kept its category and property payload.

**Built** (`src/brambleloop/integrations/taxonomy_drift.py`, new; two small hooks in
`runtime/release.py`; a REMEDIATION entry in `ops/incident_lifecycle.py`):
- **The diff.** On every refresh that stored a new snapshot, it is diffed against the previous
  one:
  - nodes removed or added;
  - nodes moved or renamed (the full ancestor path is compared, so a renamed parent moves
    every node under it);
  - per node, the properties added, removed or changed (name, required, multivalued, max
    values, allowed values, scales), and a schema read for the first time;
  - a node that gained a child, because a deeper truthful category may now exist.
- **Per product, from its newest search profile:**
  - CHOSEN on a changed node: a **halting P1** `taxonomy-drift:<slug>` incident, and
    `listing.seo` re-queued once per snapshot (rebuild token `tx<snapshot id>`, the release's
    last completed inputs);
  - UNKNOWN or refused: re-queued, with no incident, since it is already refused by its
    certificate;
  - unchanged node: left alone.
- **Resolution:** `_persist_search_profile` resolves the incident when the profile is rebuilt
  on the named snapshot or a later one.
- **No deadlock.** Gate E halts `gate.certify` on a halting incident. A halt with nothing
  queued to resolve it would block the very certification that rebuilds the profile (the
  W4-LISTREADY R2 pattern). So when no `listing.seo` can be re-queued, the P1 is opened
  **non-halting** and says why.
- **A refused or failed drift check reads `UNKNOWN`** in the refresh's audit, never "no drift".
  It never dead-letters the refresh (#195).
- **Production consequence after release.** Production snapshot 1 has the tree and no property
  schema (`evidence_FMBATCH1/prod_api_audit_taxonomy_refreshed_*`). b997efd's first refresh
  reads the two property schemas, which is a new snapshot. F-010 then re-queues `listing.seo`
  for the UNKNOWN Launch-0 profiles. Without it they would stay UNKNOWN until some unrelated
  chain re-run.

**Tests:** `tests/test_w4_fmbatch1_drift.py`, 9/9.
- Five diff tests and one judge test.
- `test_a_changed_schema_halts_the_listing_requeues_seo_and_resolves_on_rebuild` runs the real
  worker:
  - a certified hexagon coaster CHOSEN on snapshot A;
  - a refresh whose node schema re-requires "Skill level" and adds a value;
  - result: a halting P1, `publication_halted` true, exactly one `listing.seo` keyed `tx<id>`;
  - once that job runs, the profile is on the new snapshot, the incident is resolved, and
    publication is no longer halted;
  - a second identical refresh is a confirmation: no drift and no second re-run.
- `test_a_change_elsewhere_in_the_tree_leaves_a_valid_listing_alone`.
- `test_drift_with_nothing_to_rerun_is_reported_and_never_halts_certification`.
- **Mutation check:** disabling the hook in `handle_taxonomy_refresh` fails the 3 runtime tests.
  The tree was restored with `git checkout`.

### F-381 Rollback First-Class

**Criterion:** "Every material autonomous deployment preserves a known-good predecessor and an
executable rollback/recovery path. Detected regression triggers containment and rollback
according to severity."

**Before.**
- The predecessor and the executable path were proven by W4-ROLLBACK: `DEPLOYED_HISTORY.json`,
  `deploy_guard.py rehearse-rollback` before every push, and `deploy.sh --rollback-to`.
- Severity was missing. A failed post-deploy readback ended in exit 5 with "fix forward or
  roll back per the runbook", whatever had failed. The runbook has no severity rule.

**Built** (`ops/rollback_decision.py`, new; `ops/deploy.sh` readback block):
- **P0 features:**
  - shadow phase holds;
  - nothing published in shadow;
  - publication refusals recorded;
  - catalogue says nothing is published;
  - every agent has a cost ceiling;
  - boot guard proves the release record;
  - embedded worker alive;
  - release identity.
- **What counts as a P0:**
  - a P0 feature that FAILs **or reads UNKNOWN**;
  - production unreachable after the deploy;
  - an unreadable readback.
- **P0 handling:** `deploy.sh` performs the sanctioned rollback to the commit production ran
  before the push. That is the one it just rehearsed, and it goes through the same guarded
  path: it re-enters itself with `--rollback-to <predecessor> --deployed <sha>`.
- **Every other feature is P1:** exit 5, fix forward. A feature the table does not name is P1,
  never a pass.
- **No rollback loop.** A rollback that itself regresses is never rolled back again (exit 6).
- **`AUTO_ROLLBACK=0`** reports the P0 with the exact rollback command and exits 6 without
  pushing.

**Tests:** `tests/test_w4_fmbatch1_rollback.py`, 9/9.
- Five unit tests of the decision, including that every P0 name is a real `readback.MANIFEST`
  feature.
- Four tests run the real `ops/deploy.sh` against a local bare remote, with stub
  guard/readback scripts:
  - **P0:** production ends on a rollback commit whose tree is exactly the predecessor's, on top
    of the candidate. Both deploys are read back.
  - **P1:** exit 5, and the candidate stays.
  - **`AUTO_ROLLBACK=0`:** exit 6 and no push.
  - **A regressing rollback:** exit 6 after exactly one rollback.
- **Mutation check:** disabling the P0 branch in `deploy.sh` fails the 3 P0 end-to-end tests.
  Restored.

**Merge note.** CLOSE6 edits the same `deploy.sh` readback lines: it writes the readback JSON
to `evidence_BOARD/`. Keep both:
- use CLOSE6's `rb_json` path as this block's `--json` file;
- keep the `rollback_decision.py` call after it.

## 3. (c) Already implemented: evidence, merge or acceptance needed

| row | criterion (quoted, shortened) | what exists | evidence | what closes it |
|---|---|---|---|---|
| **F-540** OAuth Credential Health | "Continuously monitor ... credential status, granted scopes, expiry and refresh health without exposing values. Refresh-token rotation must be proven in production and persisted atomically." | daily `etsy.credential_health` cadence (worker.py) -> `oauth_store.credential_health` + a live refresh | `evidence_FMBATCH1/prod_api_audit_credential_health_20261021T0242Z.json`: 2026-10-13..10-21, 9 consecutive daily HEALTHY readings, scopes complete, live refresh ok each day, rotations 0 -> 74 persisted, values never exposed (fingerprint only). Tests: test_etsy_readback_observe 37/37, test_etsy_oauth_callback (rotation and race) green | **closure proposed** (OVERRIDES_PROPOSED_FMBATCH1; dry run COMPLETE) |
| **F-100** Owner-Gated Diversification Spend | "Funding/connecting another provider requires owner approval backed by measured resilience value." | `finance/funding_packet.diversification_packet`, GET /api/funding/packets | `evidence_BOARD/prod_api_funding_packets_20261020T0612Z.json`: concentration 97.8% (existential), measured resilience value (probe failure share 0.70, 86 parked jobs), CA$10 bounded experiment, `approves_itself: false`. test_w4_funding green | **closure proposed, with a stated judgement.** The matrix also suggested refusing registration without an approval row. Not added, because Venice is being wired by W-LAURAONE. Reject if the integrator reads the criterion as needing that row |
| **F-380** Code Change Governance | "Autonomous code changes require tests, version control, deploy evidence, rollback capability and post-deploy observation appropriate to their blast radius..." | `ops/deploy.sh` + `deploy_guard.py` (descendant + green suite record + tracked RELEASE record), pre-push hook, rehearse-rollback, readback; b931d17 deployed through it (DEPLOYED_HISTORY entry) | test_deploy_guard, test_deploy_path, test_w4_rollback_rehearsal, test_w4_smoke green; "appropriate to blast radius" = F-381 above | **override proposed**: gate `production_window` dropped. The 24 h window is not this row's criterion; the board inherited it from a shared mapping note. Dev-proven until F-381 ships |
| **F-252** First-Photo Click Gate | "...survives thumbnail/mobile crop, is high-resolution/well-lit ... maximizes truthful click appeal." | the matrix's next action (resolution and exposure floors) is done: `thumbnail.quality_floors` is called by `evaluate_thumbnail` | test_w4_thumbfloors 7/7 | the comparative "click appeal" half is the vision review, in **W-LISTREADY**'s lane (owner-approved batch, max CA$7.07). Not duplicated |
| **F-144** Production Readback Gate | "Major operational features require deployed readback/verification after local tests." | ops/readback.py + deploy.sh exit 5 (W4-SMOKE). CLOSE6 adds 6 features and the board rule `apply_readback` | readback of b931d17 FAIL on 2 features, both fixed in b997efd (CLOSE5) | merge CLOSE6; deploy; a passing readback |
| **F-040** Shop Quality Gate | "Icon, About/brand presentation and core trust elements must be complete before launch." | readiness reads the live getShop daily (`etsy_first_sale_surfaces`). CLOSE6 adds the About reading | `evidence_FMBATCH1/prod_api_launch_20261021T0256Z.json`: production holds launch on `banner_set`, `policy_shipping_set`, `policy_additional_unset`, `has_a_digital_listing` | merge CLOSE6 + deploy, then the owner's shop settings and About reading |
| **F-515@v0.16** Shop Completeness Gate | "...verify shop icon/logo, banner ..., About/story, policies, branding consistency, support expectations and required seller information. Missing trust surfaces cannot silently pass launch readiness." | same daily getShop gate, which already refuses silently missing surfaces in production (above). About = CLOSE6; seller information (`legal_and_tax`) and support (`messages`) = FIRSTSALE2 collectors | as F-040 | merge CLOSE6 + FIRSTSALE2, then deploy |
| **F-834** Consumption Required | "...prove the consumer." | CLOSE6: rehearsal edge recorder + consumer chain receipts | CLOSE6 `evidence_CLOSE6/final_proof_8e4efd3.json` | CLOSE6 TESTED override ACCEPTED (D-W4-CLOSE6-OVERRIDES); apply it |
| **F-846** Audit-Repair Loop | "Freeze -> audit -> defect -> repair -> regression -> full suite -> independent re-audit." | FULL coverage; the producer is operator tooling | OVERRIDES_PROPOSED_FMGATE.json | ACCEPTED at TESTED on CLOSE6 (D-W4-CLOSE6-F846); apply it |
| **F-872** Etsy Scope Reauthorization | "...transactions_r ... proven by readback before trusted use." | gate = granted scope AND a recorded working probe | production `commerce.orders_ingested` (read again 2026-10-21T00:04Z): `ran: true`, `gate_missing: []`, 2 authenticated calls (receipts + payment ledger), 0 receipts | closed on production by CLOSE6 (`test_w4_close6_scope.py`); merge it |

## 4. (b) Blocked on a deploy, the owner or an external party

| rows | real blocker (re-verified 2026-10-21) | proposal |
|---|---|---|
| **B2#195**, F-371, F-495, F-654, F-701, F-849, F-880, F-881, F-895, F-923 (24 h window), F-924 (hosted history) | **Deploy of the successor, then a 24 h unattended window.** Production /api/verify (`evidence_FMBATCH1/prod_api_verify_20261021T0242Z.json`) fails only `no_unexpected_dead_letters_in_24h`, on `intel.gallery_analysis` TimeoutError ×3 (last 2026-10-20T08:06Z). That is fixed by CLOSE5 ee244a1, which is in b997efd. No window can pass on b931d17. F-849's "buildable now" step was re-run here: `test_cert_claude_independence` 4/4 on this branch (`evidence_FMBATCH1/test_cert_claude_independence_be3fdd6a.txt`) | none: the label "deploy successor + 24h" is right |
| F-396, F-628 | the board names `offsite_storage`. It is **OPEN** in production (`evidence_FMBATCH1/prod_api_offsite_*`: off-provider B2 bucket, encryption key present, last archive 2026-10-21T00:00Z ok; F-697 closed). What is left is the #195 window | re-gate `owner:offsite_storage` -> `data:production_window` |
| F-005, F-007, F-009, F-243, F-247 | The engineering is done and tested: category matcher, property route, attribute truth, 13-tag block, filter audit. Results: test_search_truth 32/32, test_w4_firstsale_taxonomy 7/7, test_w4_prodready_taxonomy 3/3. Production reads the real tree daily (3065 nodes), but b931d17 reads no property schema. b997efd reads the 2 schemas (LISTREADY §3a). Etsy's answer then decides CHOSEN or UNKNOWN | re-gate `owner:etsy_api` -> proposed `data:taxonomy_schema_read`, with its board ROOT; coordinate with W-LISTREADY |
| F-437 | Live capability evidence that needs no write now exists in production: credential refresh, getShop, receipts and ledger, taxonomy. The create/read/delete exercise is an **Etsy write**, the owner's to authorise | re-gate `owner:etsy_api` -> proposed `owner:etsy_exercise_authorisation` |
| B2#11, B2#12, F-273, F-538 | **Real buyers** (external). The code is live, and receipts and the ledger are read every 6 h with 0 receipts | already re-gated to `customers` and ACCEPTED on CLOSE6 (B2_REGATE / FM_REGATE_PROPOSED_CLOSE6); not repeated; needs the CLOSE6 merge |

## 5. Excluded (other lanes)

| row | lane | why |
|---|---|---|
| F-594 First-Sale Readiness Gate | W-FIRSTSALE2 (done) | the first-sale surfaces |
| F-733 Canonical Asset Registry | W-LAURAONE / VISNEXT2 | the canonical model *is* Laura (`visual/freeze.py` D-FB-11) |
| F-027, F-031, F-041 (and F-252's vision half) | W-LISTREADY | the batch-scoped Launch-0 image review (D-W4-LAUNCH-VISION-BATCH) and its activation card |

## 6. Tests run (focused only, through testslot, venv-integ4)

**Required regression set:**

| suite | result |
|---|---|
| test_vacuity | rc 0 |
| test_launch | rc 0 |
| test_cost_governance_wave2 | rc 0 |
| test_search_hero_publish | 4/4 |
| test_cert_listing_frames | rc 0 |
| test_v11_autonomy_timeline | rc 0 (after regenerating `autonomy_map.json`: one new follow-on edge, taxonomy_drift -> listing.seo) |

**Touched and evidence suites:**

| suite | result |
|---|---|
| test_w4_fmbatch1_drift | 9/9 |
| test_w4_fmbatch1_rollback | 9/9 |
| test_search_truth | 32/32 |
| test_w4_fmgate_taxonomy_refusal | rc 0 |
| test_w4_firstsale_taxonomy | 7/7 |
| test_w4_prodready_taxonomy | 3/3 |
| test_incident_lifecycle | rc 0 |
| test_w3_k7_ops_truth | 16/16 |
| test_w4_owner_incidents | 6/6 |
| test_deploy_guard | rc 0 (re-run after the deploy.sh change) |
| test_deploy_path | rc 0 (re-run after the deploy.sh change) |
| test_w4_rollback_rehearsal | rc 0 (re-run after the deploy.sh change) |
| test_w4_smoke | rc 0 (re-run after the deploy.sh change) |
| test_w4_funding | rc 0 |
| test_w4_thumbfloors | 7/7 |
| test_etsy_oauth_callback | rc 0 |
| test_etsy_readback_observe | 37/37 |
| test_offsite | rc 0 |
| test_cert_claude_independence | 4/4 |

**Overrides dry run** (`aggregate.py --overrides OVERRIDES_PROPOSED_FMBATCH1.json --dry-run`,
saved as `evidence_FMBATCH1/overrides_dry_run.json.txt`):
- problems: [].
- F-540, F-100, F-380 and F-381 adjudicate COMPLETE.
- F-010 stays OPEN at TESTED. `taxonomy_drift.py` is not yet in `module_reachability.json`,
  which was generated on an earlier head. The cap is the honest reading.

## 7. For the coordinator

1. Merge or apply CLOSE6. It holds the accepted F-834/F-846 overrides, the B2 #11/#12 and
   F-273/F-538 re-gates, F-872's production closure, F-144's board readback rule and F-040's
   About path. Without it, 9 of these 40 rows stay mislabelled.
2. Decide `OVERRIDES_PROPOSED_FMBATCH1.json`:
   - F-540 and F-100: production evidence;
   - F-010, F-380 and F-381: dev-proven, so implemented_unverified until a release.
3. Decide `FM_REGATE_PROPOSED_FMBATCH1.json`:
   - F-396 and F-628 -> production_window;
   - the five taxonomy rows -> taxonomy_schema_read;
   - F-437 -> etsy_exercise_authorisation.
4. Release: deploy b997efd or a successor carrying this branch, then the 24 h window (#195 and
   its 10 FM rows).

**Owner actions surfaced** (already in OWNER_ACTIONS / LISTREADY; nothing new is invented here):

| action | why | max cost | minutes |
|---|---|---|---|
| Authorise one POST `/api/etsy/exercise` (F-437) | it is an Etsy write: a draft is created and deleted | UNKNOWN until checked: no fee is recorded for a draft in this repository; Etsy charges its US$0.20 listing fee on publication, which the exercise never does | about 5 |


## 8. Batch R (post-launch, coordinator follow-up): research discipline

No Build 2 row is non-launch-critical `blocked_engineering` (only #11, #12, #195, triaged
above). There are 213 Final Master post-launch `blocked_engineering` rows. The first batch is
the research-agent cluster. Its matrix next_action ("build intel/research.py") was stale:
W4-RESEARCH had built the module. Each row's own criterion was implemented as an extension of
`src/brambleloop/intel/research.py`, and the `learn.scan` cadence enforces the time bound.

| row | what the code now enforces |
|---|---|
| F-419 | a task defines evidence_needed, stop_condition, a time bound (1..365 days, giving a deadline) and a spend bound |
| F-444 | `stop` / `stop_overdue` record what was searched, what remains unknown, why it matters and the smallest owner/external action named when the task opened. `learn.scan` stops overdue tasks |
| F-405 | `search_internal_report` searches lessons, observations, incidents, both experiment tables, failure memory, benchmark listings, BUILD_STATE, DECISION_LOG and test names. Each corpus is recorded with its hits, or why it was unreadable or absent. The deploy image carries no repository documents |
| F-408 | a consequential fact from external sources needs 2 independent publishers, or a recorded reason a second source is not practical |
| F-426 | `contradicts` plus `reconcile`. An answer is refused while a conflict is neither reconciled nor recorded unresolved |
| F-420 | an answer names its effect (confidence changed, alternatives narrowed, constraint established, hypothesis produced, or stop justified), each checked. A source no finding cites is refused |
| F-435 | the structured conclusion (question, status, confidence, evidence, alternatives, constraints, applicability, unresolved, next_test) is stored, and `conclusion()` returns it. A next test is bounded to 1..90 days and a spend of at least CA$0 |
| F-411 | a method_adoption answer judges assumptions, topology, scale, data, runtime and failure_modes. `adopt` is true only if all six transfer |
| F-432 | a materially equivalent answered and fresh question (same content words, domain and decision) is reused. It re-opens only for new evidence or changed assumptions; stale answers re-open |
| F-449 | `metrics()`: resolved, reuse rate, stale answers refreshed, duplicates avoided, experiments prevented, spend avoided, source quality and decisions changed. Every figure is None when nothing has been measured, never a default 0 |

**Schema:** additive `research_tasks.deadline` and `detail` columns (`core.migrate` adds them).

**Tests:**
- `tests/test_w4_fmbatch1_research.py` 12/12.
- `tests/test_w4_research.py` 10/10, updated to the new required spec. Its corpora are isolated
  from the live repository documents; no assertion was relaxed.

**F-412** (the research-to-experiment bridge) is only partly done. A bounded `next_test` is
recorded in the conclusion, but nothing yet feeds it into `improve/runner`. It remains open.

## 9. Workstream B batch O (post-launch): signal hygiene

`src/brambleloop/ops/signal_hygiene.py` runs on every 15-minute `ops.health` sweep. It is
guarded: a failure records UNKNOWN and never fails the sweep.

| row | criterion | built |
|---|---|---|
| F-139 | "Homogeneous large backlogs create one actionable incident with count/scope while retaining item evidence." | Defect dead letters of one job type (3 or more) become one `dead-letters:<type>` incident. It carries the count, the first and last time, every job id (up to 200, with the truncation stated) and an error histogram. It is restated, never duplicated, and resolves when the backlog clears. Deliberate refusals are never aggregated |
| F-140 | "A permanently noisy/false health signal is itself a defect." | `noisy-signal:<sig>` opens when a watched signature opens 4 or more times in 7 days (flapping), or stays open with no detector confirming it for 14 days. It resolves when that pattern stops |
| F-149 | "Monitor scratch/cache growth, disk utilization and abnormal file-count growth before ENOSPC." | Each sweep stores an `ops.disk_sample` (free GB per filesystem, leftover temp directories). Over 24 h, temp-directory growth above 20 a day, or free space projected to run out within 48 h, opens `disk-trend:<what>` (P1). Fewer than 4 samples reads UNKNOWN |

**Tests:**
- `tests/test_w4_fmbatch1_hygiene.py` 6/6, both positive and negative cases, including a real
  `ops.health` worker run.
- Regression suites green: test_health, test_incident_lifecycle, test_w4_owner_incidents,
  test_w3_k7_ops_truth, test_vacuity.

**Status:** dev-proven on this branch only (E).

## 10. Workstream B batch P (post-launch): provider dependency

| row | criterion (quoted) | built | status |
|---|---|---|---|
| F-092 | "Measure provider concentration by calls, spend, critical workflows and requirements lost during outage." | `scale.dependency.register`: per provider and workload (judgement_vision or image_generation): spend, calls, shares, critical workflows (purposes ranked by spend), and the Build 2 requirements lost if the provider is down (`build2.executor` gate table). The `ai_provider` axis now counts judgement and vision only; image generation has its own axis | E |
| F-093 | "...explicitly an existential dependency until tested fallback exists." | A second billed judgement provider does not clear EXISTENTIAL without a passing `provider.fallback_drill` record from the last 30 days. An image provider never counts | E |
| F-094 | "Do not add a second paid provider for symmetry; trigger diversification when outage, price/terms, volume, revenue dependence or downtime cost justifies it." | `diversification_trigger`: measured thresholds only (probe failure at least 20%, at least 10 parked jobs, a recorded provider change, at least 80% of the monthly ceiling, revenue-dependent concentration). Concentration alone never triggers. An unmeasurable reason is listed as unmeasured. The trigger is carried on the F-100 funding packet | E |
| F-095 | "Define required structured output, vision, context, quality, latency and cost before a fallback can satisfy a gate." | `gateway/fallback_contract.py`: a per-tier contract plus `evaluate` (static capabilities, recorded evals and latency, cost bound). `failover.decide` never routes a fallback whose contract FAILs. A cross-provider fallback is routed only on PASS | **B, partial.** A same-provider approved fallback still routes when quality or latency is UNKNOWN; its verdict is shown on the row. Closing this needs recorded golden-task evals per model |
| F-099 | "Version provider pricing/model availability and re-run routing economics on material change." | `gateway/provider_watch.py`, run on the daily `ops.dependencies` cadence. It keeps a versioned snapshot (prices, tier models, DOWN or serving). On a change it records `gateway.provider_change`, re-runs `routing.plan` (`routing.economics_review`) and opens a P2 `provider-change:` incident, which an unchanged snapshot resolves | E |

**Tests:**
- `tests/test_w4_fmbatch1_providers.py` 6/6, both positive and negative cases.
- Green: test_dependency, test_cert_dependencies, test_w4_funding, test_v11_reliability_gateway,
  test_incident_lifecycle.

## 11. Workstream B batch T: ops and test hygiene

**F-146, F-147 and F-148: already implemented; not rebuilt.**
- The single EXIT trap: run_tests.sh, with the note at lines 327-336.
- The per-suite leak census: `TMP LEAKED`, with `TMP_LEAK_STRICT` making a leaking suite a
  failing one.
- `tests/_tmp.py`: the per-process sandbox, plus the static guard in `test_w3_tmp_hygiene.py`.
- Their TESTED-target overrides are **already ACCEPTED** in CLOSE6
  (`OVERRIDES_PROPOSED_CLOSE6.json`, D-W4-CLOSE6-OVERRIDES). They only need applying. Their
  matrix `missing_part` text is stale.

**F-150 Failure Classification Before Revert: built.**
- Criterion: "Classify ENOSPC/permissions/network/provider failures before reverting code."
- `scripts/classify_failure.py` matches the literal markers that the OS, Python and the
  providers print.
- For each failing suite whose output matches, `run_tests.sh` prints
  `ENVIRONMENT FAILURE (<class>): <line> -- not a code regression; do not revert for it`.
- The summary adds `ENVIRONMENT FAILURES: n of the m failing suites`.
- An assertion or code failure is never labelled as an environment failure.

**Tests:**
- `tests/test_w4_fmbatch1_failclass.py` 2/2. It covers the four classes plus an assertion, and a
  real `run_tests.sh` run in a sandbox repository with an ENOSPC suite, an assertion suite and a
  passing suite.
- Green: test_run_tests_script, test_w3_tmp_hygiene.

**Status:** E. The producer is operator tooling, so its ceiling is TESTED, the same basis as
F-145..F-148.

## 12. Workstream B batch D: dashboard (F-200, F-201)

- **F-200.** Criterion: "order the page by owner decision value: health/phase -> true active
  owner actions -> launch blockers -> product/creative truth -> spend -> operations
  detail/audit trail". The `/` page now runs in that order:
  1. headline and health;
  2. waiting on the owner, then external capability;
  3. launch readiness and open incidents;
  4. command centre and products;
  5. spend governance;
  6. volume and operations, learning, jobs, agents, audit trail.
- **F-201.** Criterion: "Large tables (audit trail, incidents, agents, learning changes) default
  to concise summaries with expandable/drilldown detail".
  - The audit trail, incidents, agents, learning changes and recent jobs each open as one
    summary line (counts) inside a `<details>` fold, with the full table inside.
  - The incident fold opens by default while any incident halts publication.
- **Tests:**
  - `tests/test_w4_fmbatch1_dashboard.py` 2/2: the section order is asserted, and every audit
    row is still present inside its fold.
  - Green: test_cert_dashboard (F-206's ordering is unchanged), test_dashboard_spend.
- **Status:** E.

## 13. F-412 Research-to-Experiment Bridge

- **Criterion:** "Translate promising research into the smallest bounded experiment that can
  falsify or support its applicability before a large build or spend."
- **Built:** `research.bridge(task, cell=, rollback_ref=)`.
  - An answered task whose effect produced a hypothesis with a bounded next test becomes an
    `improve.cells.propose` proposal. The improvement loop's own baseline, rollback, governance
    and failure-memory rules apply.
  - The proposal carries the falsification condition, the day bound and the spend bound, and
    it cites `research_tasks:<id>`.
  - The bridge is idempotent.
  - It is refused for an unanswered task, a task with no hypothesis or bounded test, and a
    method that did not transfer (F-411 `adopt` false). That last case means the research
    itself prevented the experiment.
- **Test:** `test_f412_...` in `tests/test_w4_fmbatch1_research.py`, now 13/13.
- **Status:** E.

## 14. Window rows read against the 24 h proof (proposals; not applied)

**Proof:** production b997efd, `autonomy.off_device_proof` passed=true over 2026-10-25T01:03Z
to 10-26T01:03Z.
- 1417 jobs of 97 types, completions in 25 distinct hours, scheduler alive in 25 hours.
- 0 unexpected dead letters, 26 incidents opened, operating cost CA$0.17.
- No restart happened in the window.
- Saved as `evidence_FMBATCH1/prod_api_build_20261026T0103Z.json`.

**Closures proposed:**

| file | rows | dry run |
|---|---|---|
| `OVERRIDES_PROPOSED_FMBATCH1_WINDOW.json` | F-371, F-654, F-701, F-849, F-396, F-628, each with its own criterion quoted and read against the proof | problems [], all 6 COMPLETE |
| `B2_CLOSURE_PROPOSED_FMBATCH1_195.json` | #195 | not dry-run (Build 2 proposal) |

- **F-628** also cites the continuity and off-provider archive restores (132 tables).
- **F-849** also cites b997efd's release-record full suite, which includes
  test_cert_claude_independence.
- **#195 carries a stated judgement.** Its criterion asks for "restart/recovery evidence", and
  there was no restart in the window. Reject the proposal if a restart inside the window is
  required.

**Not proposed:**

| rows | reason |
|---|---|
| F-495 | No department was blocked during the window, so "independence while others are blocked" is not shown |
| F-880, F-881, F-895, F-923, F-924 | Each needs the ops/slo soak grade, department useful-work, the external availability probe or the SLO budgets. These are operator-credentialed reads: one GET `/api/cc/operations/soak?start=2026-10-25T01:03:35Z` would evidence them |

## 15. Batch I: the gaps CLOSE5 named on F-394, F-470, F-489 and F-457

A pass over the 187 rows marked "missing implementation" found 28 rows already referenced by
tests. Some of those references are this lane's own; others are W4 lanes whose matrix rows
were never re-mapped from 019ebf0. CLOSE5.md names exactly what each of those rows still lacks.
This batch closes those named gaps.

| row | CLOSE5's gap | built |
|---|---|---|
| F-394 | "risk reduction, confidence" absent from `roi.prioritise` | Value = impact × confidence + risk_reduction, per CA$. An unstated confidence is flagged and ranks after a stated one of equal value. A confidence outside [0, 1] or a negative risk reduction is refused. The old ordering is unchanged without the new fields |
| F-470 | storage and platform capacity unmeasured | `resources.read` adds free space per working filesystem and I/O pressure (PSI). It saturates under 2 GB or 2% free, or at I/O avg60 of 50% or more. An absent path reads UNKNOWN. The platform's container limits (cgroup) are named as the capacity source |
| F-489 | wall-clock compression and conflict rate unmeasured | `swarm.metrics.parallel_window`, read from durable job rows: compression (work ÷ busy wall clock), useful parallel seconds and conflict rate (lease, race, lock and unique-clash markers). It reads None when the window is empty. Served on `/api/swarm/runtime` |
| F-457 | structural target decision | `OVERRIDES_PROPOSED_FMBATCH1_B.json`: TESTED target, because the producer `ops/registry.py` is operator tooling. Dry run: problems [] |

**Tests:**
- `tests/test_w4_fmbatch1_swarm.py` 5/5, both positive and negative cases.
- Green: test_w4_improvemetrics, test_w4_swarmcontrol, test_w4_swarmmetrics, test_roi.

**Status:** F-394, F-470 and F-489 are E. F-457 needs the integrator's decision.

**Still lacking, per CLOSE5:**
- F-126: visual benchmark rows are not superseded.
- F-431: the `research.run` job and the fetch step.
- F-398: the single joined improvement record.

These are the next batch.

## 16. F-398 Improvement Audit Trail: one joined record

- **Criterion:** "Every adopted autonomous improvement records trigger/evidence, old version,
  new version, tests, quality-floor verdicts, spend, deployment, observed outcome and rollback
  reference."
- **The gap CLOSE5 named:** there was no single joined record.
- **Built:**
  - `improve.cells.audit_record(row)` joins all nine fields from the row.
  - An absent field is None and is named in `missing`; `complete` is true only when nothing is
    missing.
  - `monitor` now keeps every post-promotion observation (`observed_outcomes`), whether the
    change held or was reverted.
  - `audit_gaps(db)` lists adopted improvements with incomplete records.
  - `history()`, which `/api/improve` serves, carries the record.
- **Tests:**
  - `tests/test_w4_fmbatch1_audit.py` 3/3: missing tests and observation are named; recording
    them completes the record; unattributed spend is listed as missing, never defaulted.
  - Green: test_w4_improvemetrics, test_improve_director.
- **Status:** E.
- **Left for other lanes:**
  - F-126, superseding visual-benchmark rows, is in `gateway/image_bench`, the FLUX and visual
    area that Workstream C owns.
  - F-431, the `research.run` job with an external fetch step, makes network fetches and is the
    next candidate.

## 17. Batch C: Command Center gaps CLOSE5 named (F-621, F-661, F-668, F-729)

All changes are in `app/command_center/executive.py` and `company.py`. None of the Laura files
or routes were touched.

| row | gap (CLOSE5) | built |
|---|---|---|
| F-621 | no charter-KPI trend | `kpi_trend`: per department per UTC day over 7 days, useful completions (distinct non-noop results) and defect dead letters, read in one pass with `autonomy.kpis` rules. Carried as `kpi_trend_7d` on every department. With no finished job it reads unknown |
| F-661 | objective, incidents, active departments, completed work, owner decisions missing | The executive block adds:<ul><li>the objective, from the latest `plan.strategy_reviewed` trajectory (UNKNOWN when never reviewed);</li><li>open incidents;</li><li>departments with completed work in 24 h;</li><li>jobs completed in 24 h;</li><li>owner decisions waiting.</li></ul> |
| F-668 | no org chart, heartbeat or learning | Each agent row has:<ul><li>`role`: director is the first agent its charter lists;</li><li>`heartbeat`: its newest recorded start or finish, None if it never ran;</li><li>`department_lessons_30d`, from the stated `DEPARTMENT_CELLS` mapping.</li></ul>The workspace adds an `org_chart` (department → director plus workers) and states its basis |
| F-729 | restarts, experiments, improvements, idle departments missing | Autonomy health adds:<ul><li>restarts recovered in 24 h (jobs done on a second or later attempt);</li><li>experiments by state;</li><li>improvements promoted and reverted in 7 days;</li><li>unintentionally idle departments: ready work waiting and nothing completed in 24 h.</li></ul> |

**Tests:**
- `tests/test_w4_fmbatch1_cc.py` 4/4.
- Green: test_w4_ccfm1, test_w4_ccfm2, test_w4_cc_company.

**Limit:** the new fields are served through the Command Center providers. The Company tab's
JavaScript does not yet chart `kpi_trend_7d`; it shows the existing completed-work trend.

**Status:** E.

**Design-quality rows:** F-652 and F-670 are visual-review criteria ("premium, image-rich",
"strong typography"). They need a human or vision review, not code, so they are left as owner
or independent review items.

## 18. F-431 Durable Knowledge Promotion: the research run (fetch step + promotion)

- **Criterion:** "Validated research findings become structured durable knowledge, regression
  tests, capability metadata, architecture notes or decision records so later agents reuse
  them."
- **The gap CLOSE5 named:** the research run and the fetch step were missing.

**Built:** `intel/research_fetch.py`, run by the existing `learn.scan` cadence.

*Fetch step* (within the coordinator's bounds):
- **Allowlist.** Only `ALLOWED_HOSTS`, each with its stated basis:
  - Justice Laws;
  - canada.ca;
  - cpsc.gov;
  - en.wikipedia.org;
  - help.etsy.com.

  www.etsy.com and AAP are not on the list.
- **No credentials.** The URL must be https. A URL with credentials or a key/token parameter is
  refused, and no auth header or cookie is ever sent.
- **robots.txt.** It is read first and obeyed; an unreadable robots.txt is a refusal.
- **Politeness.** An identifying user agent, a 3-second per-host floor, a 512 KB cap and at most
  5 fetches per run.
- **Free reads only.** No paid host can appear on the list (the `test_cert_spend_hosts` scan),
  so research spend stays at CA$0.
- **Recording.** A fetched page becomes a `fetched` source on its task (url, date, bytes, sha256,
  bounded excerpt), and every attempt has a `research.fetch` audit row.
- **Planning.** Planned fetches are the open children's-safety tasks whose primary page is
  allowlisted.

*Switch:*
- The fetch step runs only with `BRAMBLELOOP_RESEARCH_FETCH=1`. Otherwise the run says so and
  makes no request.
- Turning it on in production is a Railway variable, which is for the coordinator or owner.
  This lane changes no Railway setting.

*Promotion:*
- An answered task with at least one fact becomes a lesson on the improvement bus (`confirmed`,
  idempotent on `research_tasks:<id>`), routed by its domain. The new subject `platform_policy`
  routes to seo_search, portfolio, customer_experience and quality.
- When the task expires (F-433 freshness), its lesson is withdrawn.
- A domain with no subject is reported, never forced.

**Tests:**
- `tests/test_w4_fmbatch1_research_run.py` 5/5. Sockets are refused for the whole file and every
  answer is a stub. It covers the allowlist and credential refusals, robots disallow and
  unreadable robots, the run's plan and the off switch, promote-once, withdrawal on expiry, and
  an unrouted domain.
- Green: test_w4_research, test_w4_fmbatch1_research, test_mine.

**Status:** E. The fetch step stays off until the switch is set.
