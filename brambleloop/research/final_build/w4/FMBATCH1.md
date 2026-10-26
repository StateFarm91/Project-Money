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

## 19. F-621: the KPI trend is drawn in the Company tab

- `static/js/views/company.js` gains `kpiTrend`. A measured `kpi_trend_7d` is drawn as two
  shared `barChart`s: useful completions and defect dead letters per day over 7 days. An
  unmeasured one reads "KPI trend: Unknown (reason)" and draws no bars.
- **Tests:**
  - `tests/test_w4_fmbatch1_pwa.py` 3/3: static source checks, the mock data, and `node --check`.
  - `test_v11_pwa_static` green.
  - `test_v11_pwa_browser`: 220 passes, 0 failures. The browser harness adds two checks: two
    KPI charts on a measured department, and Unknown on an unmeasured one.
- **Changes to an existing check in the harness:**
  - The W4-CCFM1 check `ccfm1 company: ... 7-day completed-work chart` counted every
    `svg.chart rect` in the row. It now counts the completed-work chart's bars apart from the
    new KPI charts. It still requires exactly 7.
  - The Unknown-department check now also requires 0 KPI bars.

## 20. Batch S: commit signing (F-153, F-156, F-157)

- **F-153**: `ops/signing_audit.py` reads `%G? %GK` for a range. An empty
  `user.signingkey`, or a key path whose file is missing or empty, counts as no key. A
  configured key with unsigned commits is `claimed_but_unsigned`, which is refused. Measured
  2026-10-26 on b997efda..HEAD: 16 commits, all `N`. The configured
  `/home/claude/.ssh/commit_signing_key.pub` is 0 bytes, so the status is `unavailable`, not
  claimed. Signing is **not** in place; this row proves the honest reporting, not signatures.
- **F-157**: `deploy_guard.signing_evidence` is written into `RELEASE_<sha>.json` as
  `signing` (with status, unsigned commits and `intentional_unsigned`).
  `BRAMBLELOOP_SIGNING_REQUIRED=1` refuses an unsigned commit, and `_record_problems` flags a
  tracked record whose signing was required or claimed but whose commit is unsigned.
- **F-156**: `ops/SIGNING_RECOVERY.md` gives the steps to restore signing, with no private key
  in git. A test asserts that no tracked file holds a private-key block.
- Tests: `tests/test_w4_fmbatch1_signing.py` (7 tests, temporary git repos, positive and
  negative) is green, and `tests/test_deploy_guard.py` is green.
- Remaining for real evidence: the owner or operator installs a key and an allowed-signers
  file, per the doc. Until then, F-153 can only be closed as "unavailable, reported honestly",
  if the gate accepts that.

## 21. Batch T: F-107, F-089, F-096, F-091

- **F-107** (d2fd5071): `finance/value_units.py`.
  - `scope(requirement_id, benchmark_key)` stamps every bill through `spend_report.attribution`.
  - The read side falls back to the job's inputs.
  - `what_it_bought` gains `by_requirement` and `by_benchmark`; unattributed spend keeps its
    dollars.
  - Test: `test_w4_fmbatch1_value_units.py` (3). Regression: `test_spend_policy.py`, green.
- **F-089** (fccea594): `quality/physical_truth.py` and `GET /api/physical-truth`.
  - The route is operator-only (in `OPERATOR_GET_ROUTES`), because it names testers.
  - Each Class B/C product row carries tester, version, stage, samples, due, must-start-by,
    overdue, findings, yarn and size deltas, and launch_blocked.
  - A row is blocked until a sample has passed; a failed sample is a finding, and an unknown
    risk class is never treated as Class A.
  - Tests: `test_w4_fmbatch1_physical_truth.py` (4); regression `test_route_auth_default_deny.py` 7/7.
- **F-096** (ae9d7b89): `gateway/compat_pack.py`.
  - Five golden-task families: extraction, vision gallery, creative jury, benchmark comparison
    and improvement analysis, all scored by deterministic code.
  - UNSUPPORTED and ERROR never count as a pass. `compare()` reports tasks a swap would lose.
  - A live run reserves through the ceilings (the `test_model_spend_paths` scan caught the
    first draft, which did not).
  - `provider_watch.watch` asks for a fresh pack on any provider change.
  - Tests: `test_w4_fmbatch1_compat.py` (6), plus an assertion added to the F-099 test.
  - Still open: no live provider has run the pack, since that is a paid drill.
- **F-091** (this commit): **partial; engineering is not complete.**
  - Added `gateway/providers.py`: vendor selection by task, a vendor registry, an
    unknown vendor refused, and neutral ledger names.
  - Migrated `culture/classify.py`.
  - Corrected the false "swap without touching the callers" claim in `ops/dependencies.py`.
  - `test_w4_fmbatch1_provider_boundary.py` (4) uses an AST scan as a ratchet: a new direct
    vendor importer fails, and so does a migrated file left on the list.
  - 28 modules still import `gateway.anthropic` directly. Many are in the visual, creative and
    publish lanes (Workstream C and W-LISTREADY); others read the ceiling ledger.
    `intel/serp.py` and `intel/vision.py` are next.
- **F-091, continued:** `intel/serp.py` and `intel/vision.py` now use `gateway/providers.py`
  (`for_task`, `check_budget`, `release_reservation`, and the neutral names). The facade's
  `check_budget` now requires `purpose`; `test_w4_spend_paid_discipline` caught a version that
  did not. 26 direct importers remain, all listed with reasons.
  - Tests, all green: boundary (4), `test_w4_spend_paid_discipline`, `test_model_spend_paths`,
    `test_intel`, `test_w4_marketintel`, `test_w4_b2vision`, `test_w4_close5_vision_timeout`.

## 22. Batch U: F-190, F-194, F-198, F-374, F-389

- **F-190** (b555f5f1): `scale.confidence.gate_status` carries `classes` (have, need, share,
  met for every evidence class).
  - The dashboard's CA$5K block renders one row per class.
  - The CC company item carries `evidence_classes`.
  - Test: `test_w4_fmbatch1_dashboard.py::test_f190`; `test_scale.py` green.
- **F-194** (07807184): `seasonal.leadtime.cohort_for` and `tag_cohorts`.
  - Cohorts: `launch_candidate` (LAUNCH0), `legacy` (builder catalogue), `programme` (other).
  - `catalogue_plans` returns `counts_by_cohort`, and the dashboard shows a cohort table and a
    cohort column on at-risk rows.
  - Test: `test_w4_fmbatch1_seasonal_cohort.py` (3); `test_leadtime.py` green.
- **F-198** (7f4a898f): the owned_surfaces gate lists `acceptable_surfaces` (site, pinterest,
  email, video; not the Etsy shop) and `why_required` per parked requirement (#4 #10 #246
  #247 #248 #251 #255).
  - The owner card is held under `not_yet_askable` until `live_listings` is open, and carries
    requirement_ids and why_required once asked.
  - Test: `test_w4_fmbatch1_owned_surfaces.py` (2). Green: gatesb, b2gates, executor,
    k7_owner_queue, owner_actions, board_close, wire4.
- **F-374** (c26c58f0): listing copy was already covered by the `policy_loop` trial
  (seo_lesson_match). Pricing is new.
  - New trial `runner.TRIALS["pricing_shadow"]` (kind `price_point`) scores net contribution
    per visitor at measured price points only. It needs MIN_POINT_VISITS and known orders;
    an unmeasured price is never extrapolated, and prices below the price or net floors are
    refused.
  - It has no executor, so it never changes a live price.
  - Test: `test_w4_fmbatch1_pricing_trial.py` (4); improve cert suites green.
- **F-389** (this commit): `improve/cost_learning.py`, run inside `league.cycle`.
  - Per routed task: this month's measured spend, saving per call against the cheaper tier,
    projected monthly saving, and `proposable` only when `routing.equivalence` holds.
    Results are ranked by saving and never applied; `override_route` still gates the change.
  - Context-size drift is reported against the declared typical_input_tokens, needing 5 or
    more calls, or it reads UNMEASURED. A failure is audited, not swallowed.
  - Test: `test_w4_fmbatch1_cost_learning.py` (3); `test_league`, `test_weekly` green.
  - Still open: no route evidence has been recorded in production, so nothing is proposable
    yet.

## 23. Independent review (INDEPENDENT_SECREVIEW_FMBATCH1.md at 871b84a): fixes

Each fix has a test. Every new behaviour test was run against the pre-fix tree (c089c7bd)
and failed there; the output is in `evidence_FMBATCH1/review_fixes_fail_before_fix.txt`.
The one exception is the F-4 spend-path pin, which is a new pin, not a behaviour; the F-4
behaviour tests do fail before the fix.

| Finding | Fix | Commit | Test |
|---|---|---|---|
| F-1 | The drift re-queue defaults OFF (`BRAMBLELOOP_TAXONOMY_DRIFT_REQUEUE=1` turns it on). With it off, the drift is still diffed, reported and raised as a P1 incident, and the rebuild becomes an owner action. Nothing moves toward `store.publish`, and with nothing queued the incident is non-halting, so no deadlock. | 50174256 | `test_w4_fmbatch1_drift.py::test_by_default_drift_requeues_nothing_and_asks_the_owner` (asserts no `tx*` listing.seo, launch.plan or store.publish) |
| F-3 | Automatic production rollback is OFF. Only `AUTO_ROLLBACK=1` plus the owner's own `AUTO_ROLLBACK_REASON` pushes; the script never writes a reason. One re-read before a P0 is acted on. | 53694b92 | `test_w4_fmbatch1_rollback.py` (by default no push; no reason means no push; a P0 that clears on re-read is not rolled back) |
| F-2 | Every redirect target and the final URL are re-checked: allowlist, https, default port. An oversized robots.txt is unreadable. | 617097b0 | `test_w4_fmbatch1_research_run.py::test_review_f2_*` |
| F-8 | Network errors become `FetchUnavailable` and are recorded as not fetched. One bad fetch never stops the others or `promote`. | 617097b0 | `test_review_f8_*` |
| F-4 | Every billed compat-pack response goes through `spend_report.record` (`purpose=compat_pack`), at the reservation estimate when usage is unreadable, and only then is released. `compat_pack.run` is pinned in `test_model_spend_paths`. | 330ed7c9 | `test_w4_fmbatch1_compat.py::test_review_f4_*` |
| F-5 | Vision reserves `IMAGE_TOKENS_ESTIMATE` per image. An unsupported vision task is decided before anything is reserved. | 330ed7c9 | `test_review_f5_*` |
| F-6 | Any suite whose output contains an `AssertionError` is a code failure. Assertion and FAIL lines are never evidence. The advice now reads "check the environment before reverting". | 07903e57 | `test_w4_fmbatch1_failclass.py::test_review_f6_*` |
| F-7 | With signing required, anything other than `verified` is refused, including `empty_range`, both in `signing_evidence` and in `_record_problems`. | 07903e57 | `test_w4_fmbatch1_signing.py::test_review_f7_*` |
| F-9 | A demand with no risk class and no test reads `unknown` (blocked). An unparseable `needed_by` gives `overdue: None` with the reason, never a 500. | 07903e57 | `test_w4_fmbatch1_physical_truth.py::test_review_f9_*` |
| F-10 | **Decision: fixed.** An exception while evaluating the fallback contract is UNKNOWN, and UNKNOWN is never routed. The row is `contract_refused` and the call parks rather than routing an unchecked fallback. The cost is that a broken contract table parks fallback traffic, which is visible and recoverable; routing unchecked is neither. | this commit | `test_w4_fmbatch1_providers.py::test_review_f10_*` |
| F-11 | **Decision: the pull order is accepted, and the write amplification is fixed.** RUN before GROW before IMPROVE is what F-656 requires (operations first; it changes order, never permission or spend), so it stays ON. The WATCHING row is now written on a state change, or when the open span's `last_seen` is at least `WATCHING_RESTATE_S` (1 h) old, not every tick. | this commit | `test_w4_fmbatch1_departments.py::test_review_f11_*` |

## 24. test_deploy investigation, and F-653 / F-620

- **`test_deploy.py`: not reproduced.**
  - The one failure seen earlier (`test_the_command_centre_shows_every_build_2_subsystem`) did
    not recur.
  - At f2efa2ba and at 06510fd2 (the commit before the F-190 and F-194 dashboard changes),
    the whole file ran once each through `testslot.sh`: 32 of 32 OK, exit 0, both times.
  - Six earlier full-suite logs in `/home/user/bl-runs` also show the test passing.
  - The check now names the missing string and any "unavailable" block (5c3a8298, same
    assertions), so a recurrence identifies itself.
  - Evidence: `evidence_FMBATCH1/test_deploy_f2efa2ba.txt` and `test_deploy_06510fd2.txt`.
- **F-653 (60ba9bb5):**
  - Phone (600 px and below) and tablet (601–1024 px) breakpoints.
  - Every table the dashboard draws, from any block, scrolls inside its own box
    (`_wrap_tables`).
  - A compact owner view at `/m`: health, what is waiting on the owner, today's numbers.
    Cards only, no table, with 44 px touch targets.
  - Test: `test_w4_fmbatch1_mobile.py` (3).
- **F-620 (this commit):** `/api/finance` carries `owner_view`.
  - MTD and YTD separately (from `finance.accounting.dashboard.summary`).
  - Ad spend split into free ad credit and cash: the recorded ads cost entries against the
    `ads_credit` grants (finance.credits; the credit draw is ESTIMATED).
  - The cash and payout position (`finance.accounting.cash.position`).
  - Unreconciled statement lines.
  - Monthly close status (`finance.accounting.close.status`).
  - Each block is guarded: an unreadable source reads UNKNOWN, and no recorded ads reads
    UNMEASURED, never 0.
  - Test: `test_w4_fmbatch1_finance_owner.py` (2).

## 25. Batch V: F-485, F-467, F-451, F-476, F-482; F-273/F-538 proposal

| Row | Commit | Built | Test |
|---|---|---|---|
| F-485 | d4986567 | `ops/registry.py` keeps a wait-for graph across live lanes: `wait` and `unwait`, cycles (deadlocks) and dangling waits. The survey carries `deadlocks`, and the CLI exits 1 on a deadlock. | `test_w4_fmbatch1_deadlock.py` (4) |
| F-467 | 952f1113 | An HTTP middleware enqueues `build.tick` at once after any successful write to a gate-opening route (owner decision, phase, publication or activation grants, ledger mapping, Insights, Etsy OAuth). It is idempotent per route per minute, and refused writes do nothing. | `test_w4_fmbatch1_unblock.py` (2) |
| F-451 (partial) | c7df4c70 | `/api/orchestrator` (operator-only) joins requirements, departments, dependencies, owner gates, external blockers, spend, deployments and active work. Each section is guarded, so an unreadable one is UNKNOWN. Build-side lanes stay outside the runtime. | `test_w4_fmbatch1_master_view.py` (3) |
| F-476 | 8c319836 | Registry enrolment refuses a second live lane holding the same requirement rows or the same question (a normalised fingerprint). Integrated lanes and re-enrolment do not count. | `test_w4_fmbatch1_dupwork.py` (3) |
| F-482 (partial) | 97cd3a9e | `core/contract_pins.py` fingerprints the CIR dataclasses. The pin in the test must move together with a dated declaration in `ops/CONTRACT_CHANGES.md`. Listing payload keys and API schemas are not yet pinned. | `test_w4_fmbatch1_contracts.py` (3) |

- **Proposal, not applied:** `OVERRIDES_PROPOSED_FMBATCH1_C.json`.
  - F-538 and F-273: the matrix's "no reader" / "never set" text is stale. `finance/reconcile.py`
    in b997efd reads the payment-account ledger and sets `offsite_ad_attributed`, with the
    cited `test_money_truth` tests.
  - Both stay gated on `transactions_r` and a real settlement. The dry run is clean.
- **Build 2:** none of the 4 remaining rows is buildable here: #32, #56 and #197 are NA, and
  #94 is with Workstream C.

## 26. Batch W: F-482, F-462, F-455, F-464, F-550

| Row | Commit | Built | Test |
|---|---|---|---|
| F-482 | 8efe4bb2 | The listing payload (`ListingPayload`) and API routes (path and methods) are now pinned beside the CIR. Each change needs a dated row in `ops/CONTRACT_CHANGES.md` and the new pin in the same commit. **Note for integration:** a lane that adds a route must declare it. | `test_w4_fmbatch1_contracts.py` (5) |
| F-462 | b7ee0598 | `ops/lock.py --scope LANE` takes a lease on one lane only (`ops/LOCK.<scope>`, now gitignored), and `leases` lists every lease. The unscoped global heartbeat lease is unchanged. | `test_w4_fmbatch1_lease_scope.py` (2) |
| F-455 | 3ca8d4de | `ops/context_pack.py` builds a lane's own rows: requirement, gap, next action, tests and the files to read first, and nothing else. It is driven by `--rows`, or by the lane's enrolled rows (`registry.py enrol --rows`). | `test_w4_fmbatch1_context_pack.py` (3) |
| F-464 (partial) | ba097848 | `runtime/awaiting.py`: `defer` and `check` make a wait on an external operation a durable poll job. No thread is held; giving up is recorded. The render handlers themselves are the product-engine lane's to convert. | `test_w4_fmbatch1_awaiting.py` (3) |
| F-550 | 3102036d | `intel/etsy_ops_report.py`, read-only, runs on the daily `commerce.readings` cadence. A daily exception report covers Etsy/listing incidents, Etsy-side dead letters, stale Etsy cadences and the probe state. A deep audit runs once per calendar quarter. There is no Etsy call and no listing change. | `test_w4_fmbatch1_etsy_ops.py` (2); `test_cert_commerce_readings` green |

## 27. Batch X: F-459, F-460, F-494 (build-side tooling); merge-step note

| Row | Commit | Built | Test |
|---|---|---|---|
| F-459 | 543f899d | `ops/integrate.py`: a FIFO merge queue (`enqueue`, `list`, `next`). The head lane is merged onto a local target in a throwaway worktree, and the target ref only moves by compare-and-swap, so last-writer-wins is refused. Protected targets (the production branch, `main`, `master`, remote refs) are refused outright. **It never pushes or deploys**: it prints the push command for the integrator. | `test_w4_fmbatch1_integrate.py` (4) |
| F-460 | 543f899d | The integration checklist runs per lane inside that merge: the shared-contract pins plus the lane's targeted suites. Any failure, or a conflict, leaves the target untouched and the lane queued. On success the merge commit is recorded on the lane in `ops/registry.py`. | same file |
| F-494 | a7938354 | `ops/dispatch.py`: READY build tasks, from a saved build/queue JSON or a local database, become **advisory** dispatch cards: lane name, `registry.py enrol --rows` command, context-pack command and brief. Work a live lane holds or has claimed, and anything not READY, is skipped. It starts no session, pushes nothing and deploys nothing. | `test_w4_fmbatch1_dispatch.py` (3) |

**Merge step (for the integrator).** F-482 pins the API routes, the listing payload and the CIR
in `brambleloop/tests/test_w4_fmbatch1_contracts.py`. When merging this branch with lanes that
add or change routes, or change `ListingPayload` or the CIR:
1. add one dated row per changed contract to `ops/CONTRACT_CHANGES.md`;
2. update `PINNED` in the test to the merged tree's `core.contract_pins.fingerprints()` in the same
   commit;
3. re-run the test.

The coordinator decided to keep the route pin (2026-10-26).

## 28. Batch Y: F-618, F-549, F-671, F-672 (partial), F-465, F-673, F-723, F-146, F-624; proposals F-147, F-148, F-607

| Row | Commit | What | Test |
|---|---|---|---|
| F-618 | 3cdb7837 | `analytics/metrics.py` canonical KPI functions; runrate, growth loops, books use them | test_w4_fmbatch1_metrics |
| F-549 | 8e37ca96 | `intel/etsy_scorecard.py`, `/api/etsy/scorecard` (operator-only) | test_w4_fmbatch1_etsy_scorecard |
| F-671 | 544a2055 | `products/dossier.py`, `/api/product/{slug}/dossier` (operator-only) | test_w4_fmbatch1_dossier |
| F-672 (B) | 14c80e22 | `products/lifecycle.py` derived stages and guarded transitions; handlers do not yet call `transition()` (product-engine lane) | test_w4_fmbatch1_lifecycle |
| F-465 | b65b59d8 | `build2/critical_path.py`: longest chain over `executor.DEPENDENCIES` + gate parks; `executor.queue` carries `critical_path` and each READY item's `unblocks_downstream`; unreadable reads UNKNOWN; cycles refused | test_w4_fmbatch1_critical_path |
| F-673 | 0f1fa531 | `radar/cards.py`, `/api/opportunities` (operator-only): radar score, department arbitrage (UNMEASURED when not rankable), rights lane via `culture.engine.file_topic` + `rights.route`, Class C blocker, next pre-production experiment | test_w4_fmbatch1_opportunity_cards |
| F-723 | 5122f5c5 | `finance/learning_value.py`: research spend >= CA$0.25 needs question, decision informed and new observations (>= 4 per CA$); refusals recorded; gallery batch wired before any reservation and realised after; report in `/api/spend-report` | test_w4_fmbatch1_learning_value |
| F-146 | d762c7f6 | test pins exactly one EXIT trap in run_tests.sh and INT/TERM exiting through it | test_w4_fmbatch1_runtests_trap |
| F-624 | c118c4a3 | `autonomy/capability_audit.py`: quarterly Etsy-surface + closure audit as decision records, run once per quarter from the morning handoff (no new cadence or permission) | test_w4_fmbatch1_capability_audit |

Also in 5122f5c5: retention decisions for `etsy.credential_health`, `gateway.provider_change` and `plan.strategy_reviewed`, which this branch's F-549/F-099/F-661 readers began reading by literal; `test_cost_governance_wave2` had been failing on them.

Proposals (not applied): `OVERRIDES_PROPOSED_FMBATCH1_D.json`.
- F-147 and F-148 are stale: W3-HYG built the leak census and `tests/_tmp.py`, with tests.
- F-607: the Accountant cycle exists (F-901). Splitting a separate `accountant` agent needs the cadence agent changed, and that is pinned to `cfo` in `test_v11_wiring` and the Laura-lane `test_w3_laura_core_wiring`. Left for the integrator.

## 29. Retention guard: audit actions read through constants (coordinator priority)

`ops.retention.unknown_read_actions` matched only `AuditLog.action == "literal"`. It now uses `ops/read_actions.py`, an AST scan that resolves:
- constants, including imported ones and class-level ones;
- module attributes (`vision.TASK`);
- dict keys (or values, when subscripted or read through `.values()`);
- comprehension and loop variables, including tuple unpacking over `.items()`;
- dataclass fields of instance literals (`art.actions`);
- the return values of zero-argument helpers;
- helper parameters, followed transitively through every call site, or the parameter default.

**Result:**
- 183 read actions were found. 101 were unclassified, and all 101 are now classified in `_RESOLVED_READ_ACTIONS`, which is merged with `setdefault` so the AGENTS branch's own entries win on merge.
- Prefix reads go in `KNOWN_READ_PREFIXES`. `recovery.` is protected through `PROTECTED_PREFIXES`.
- Unresolvable sites must be listed in `UNRESOLVED_READ_SITES` (3 sealed-chain/emergency sites), or the guard reports `unresolved:<path::function>` and fails closed.

**Classification rules:**
- `lifetime_total` (protected), because keep-per-action is global and does not preserve these reads:
  - a newest-row read filtered by artifact;
  - a per-entity last-N read;
  - an unwindowed count;
  - a window longer than the 90-day horizon (the seasonal 365-day evidence windows).
- `windowed`: 30-day and lights-out windows.
- `latest`: global newest-row reads.

The test also asserts:
- every `GrantLedger(...)` chain action is protected;
- the unresolved allowlist matches exactly what is still unresolved.

**Fail-before-fix:** `evidence_FMBATCH1/retention_guard_fail_before_fix.txt` shows 3 of the 5 tests failing against the previous `retention.py`.

**Cost:** the first scan takes about 3–15 s under load and is cached by source mtime. It runs only in the daily retention job.

Also fixed: `test_vacuity` flagged three earlier FMBATCH1 tests for loops over possibly-empty iterables. Non-emptiness assertions were added.

## 30. Production retention question (read-only, from code at 15800536)

**The question:** does the audit-log retention job delete evidence that code still reads?

**The job:** it runs daily (`retention_sweep`, agent `orchestrator`, GREEN authority), so it runs in SHADOW, and it does not run as a dry run. It deletes audit rows that meet all of these:
- older than 90 days;
- not among the 2 newest rows of their action;
- not in `PROTECTED_ACTIONS`.

At 15800536 the literal-string guard reports nothing unknown, so the job does not refuse.

**Exposure:**
- 93 of the 101 newly classified actions are read by production code; 50 of those should be `lifetime_total`.
- Production was first deployed on 2026-09-17, so no row reaches the horizon before about 2026-12-16.
- No evidence is lost today, unless rows from before 2026-09-17 were imported. A read-only count of `audit_log` rows older than 90 days would settle that.

**Mitigation:** ship 026365a1 before about 2026-12-16. The interim fallback is to raise `AUDIT_RETENTION_DAYS` above 365.

## 31. Batch Z: F-357, F-407, F-415, F-417, F-413, F-421–F-423, F-448, F-475, F-441 (partial); proposals F-446, F-450, F-458, F-479

| Row | Commit | What | Test |
|---|---|---|---|
| F-357 | 3e6a7d9d | `seasonal/childrens_demand.py`: monthly Wikimedia series per children's sub-category, read through the existing sanctioned feed with no credential or spend, at most once a month. Gives peak months, lead class and list-by date. UNMEASURED with less than 12 months of data. Appears in `/api/seasonal` | test_w4_fmbatch1_childrens_demand |
| F-407 | d303315e | `intel/evidence.py`: retrieval class plus authority tier (primary, secondary, community, unclassified); rank and conflict. `learning.record` stores tier and retrieval. Policy readings expose `source_tiers` without changing their digests | test_w4_fmbatch1_evidence |
| F-415 | 816f999c | `ops/licenses.py`: covers every locked package (licences from installed metadata), the 10 OFL fonts and the 7 providers. Provider terms are UNVERIFIED and in the review queue | test_w4_fmbatch1_licenses |
| F-417 | 74583308 | `ops/adoptions.py`: per-adoption cost (provider spend measured from cost entries, hosting as declared, packages free) and footprint (installed MB). Appears in `/api/spend-report` | test_w4_fmbatch1_adoptions |
| F-413, F-421–F-423 | 26712fd6 | `intel/search_strategy.py`: search rounds of exact terms, then terminology (glossary plus discovered terms), then broadened, then cross-domain. Runs on newly opened research tasks inside `learn.scan`, records each round, and stops at the evidence it needs. F-413: a method-adoption answer must list the existing methods considered, and a new build must name one it rejected | test_w4_fmbatch1_search_strategy; test_w4_fmbatch1_research updated |
| F-448 | 1df15b44 | `POST /api/research/evidence` (operator-only): owner-supplied sources and terms become `source_claim` observations, and the owner's terms join the search glossary. Route pin declared | test_w4_fmbatch1_owner_evidence |
| F-475 | 4cae8bfb | `intel/evidence_index.py`, `/api/evidence?subject=` (operator-only): the research corpora plus provenance, pod lessons, trend provenance and company memory. Lists every corpus searched. Route pin declared | test_w4_fmbatch1_evidence_index |
| F-441 (B) | cdf4dea0 | Each provider row records reversibility (from the code) and maintenance (UNVERIFIED). The provider-trial records themselves are in the visual lane | test_w4_fmbatch1_licenses |

**Proposals:** `OVERRIDES_PROPOSED_FMBATCH1_E.json`.
- F-450 is stale: `learn.scan` already runs the "unknown → research" loop.
- F-446: research is parallel through its own cadence. Whether that is enough is the integrator's call.
- F-458 and F-479: the matrix itself marks both as at target maturity.

## 32. Batch AA: F-452, F-466, F-488, F-490, F-581, F-582, F-630, F-484, F-492, F-496; proposal F-481

| Row | Commit | What | Test |
|---|---|---|---|
| F-452 / F-466 | b12e6655 | `build2/fm_graph.py`: Final Master rows that are not COMPLETE become graph nodes, joined by edges from gates and from the uids named in a row's `next_action`. The critical path counts them. `executor.sync` fans open gates out to the FM rows they release, records an `fm_unblocked` event only when that set changes, and reports gate keys with no live check as `unevaluable` | test_w4_fmbatch1_fm_graph |
| F-488 | 7fb22ec8 | `build.tick` records critical-path movement as `critical_path` build events. The dashboard headline shows the path length and its change, and a growing path raises an alarm | test_w4_fmbatch1_progress |
| F-490 | 2512c596 | `swarm/backpressure.py`: 3 or more defect dead letters in an hour, or any unresolved P0/P1 incident from the last 6 hours, makes `parallelism_advice` return scale_down, overriding the governor's scale_up | test_w4_fmbatch1_backpressure |
| F-581 / F-582 | c58a8992 | `finance/tool_decisions.py`: a vendor evaluation must state the capability gap, the existing capabilities checked for overlap, expected ROI, data quality, permissions, vendor risk and build-vs-buy. `SpendGuard.set_limit` refuses any `software:` scope that lacks an evaluation of that tool with ROI above cost | test_w4_fmbatch1_tool_spend |
| F-630 | a0ee0b78 | `build2/launch_scope.py`: in SHADOW, READY work that serves a launch-critical FM row (through the matrix's `build2_rows`) goes first. The shipped `launch_scope.json` is pinned to the matrix | test_w4_fmbatch1_launch_scope |
| F-484 / F-492 | 02858e8e | Dispatch cards derive the likely paths of a task from producer modules and hold back any task whose paths overlap a live lane's. Lane records carry `--stop` criteria (escalation and stop hours, who to escalate to, what stopping means), and `survey` reports lanes past them | test_w4_fmbatch1_dispatch, test_w4_fmbatch1_lane_stop |
| F-496 | 8b336faf | `app/hq_worker.py`: an HQ worker that runs only GREEN-only job types with a registered handler. An independence guard refuses any type the cloud fleet could not run. When an HQ lease lapses, the job returns to the cloud | test_w4_fmbatch1_hq_worker |

**Decisions needed** (not built):
- **F-483 (CI workflow).** It would run the suite on GitHub, using Actions minutes on the owner's account. That needs an owner or integrator decision.
- **F-463 (lane state in the runtime DB).** Build tooling would write to the production database. That needs an integrator decision on the route.
- **F-579 (accounting integration).** It waits on a scored vendor comparison. That comparison needs vendor facts this build has not read.

## 33. Coordinator decisions on F-483, F-463, F-579

These are recorded in DECISION_LOG `D-W4-FMBATCH1-BUILDSIDE` and proposed as gates in `OVERRIDES_PROPOSED_FMBATCH1_F.json`:

- **F-483** is owner-gated. CI would use about 150 Actions minutes a run: about 9,000 a month at two integrations a day, or about 4,500 for a nightly run. I added no workflow file.
- **F-463** is blocked by design. Build tooling never writes to the production database, and the requirement's "without the file" rules out the file-based registry.
- **F-579** is owner-gated on the accounting vendor decision.

## 34. Batch AB: F-681, F-667, F-694, F-690, F-670, F-712, F-713

| Row | Commit | What | Test |
|---|---|---|---|
| F-681 | 0d0a1ac0 | The `/api/finance` owner view now lists unreconciled statement items (newest first, up to 50) with their total, beside the existing cash/payout position and monthly close. The test checks the totals against SQL | test_w4_fmbatch1_finance_owner |
| F-667 | 3589af90 | `/api/company/departments/{key}`: one department's coverage, its agents' jobs and queue, 30-day spend, its cells' measurements and open improvements, incidents, blockers and (from F-690) inbound tasks. Route pin declared | test_w4_fmbatch1_dept_workspace |
| F-694 | f8aae50f | `improve/readings_bus.py`, run in the mine stage, publishes three kinds of reading as routed lessons, once per reading (idempotent on evidence): finance ceiling refusals (`cost`), unreviewed material policy changes (`platform_policy`), and 3 or more support cases for one product in 30 days (`instruction_clarity`) | test_w4_fmbatch1_readings_bus |
| F-690 | ff3395c6 | `autonomy/cross_team.py`: a task from one department to another, with its evidence. Creating it may enqueue a job only when the job is GREEN-only and one of the receiving department's agents may run it. A recurring customer confusion creates one pattern-team task | test_w4_fmbatch1_cross_team |
| F-670 | f9e25ef7 | The Studio CSS uses colour tokens only, with a dark set under `prefers-color-scheme`. Adds an inline SVG sparkline (no script, CSP-safe) and a Trends block (14-day spend and completed jobs) with drill-down links | test_w4_fmbatch1_theme |
| F-712 / F-713 | 1f5a2454 | `ops/task_contract.py`: a validated contract (base SHA, objective, owned paths, authority BUILD_ONLY or BUILD_AND_PROPOSE, budget, dependencies, outputs, tests, sentinel). It is required at `integrate enqueue --contract`, and dispatch cards carry a template. Integration fails a lane that changed files outside its owned paths | test_w4_fmbatch1_task_contract |

**Not built, decision needed:**
- **F-652, product imagery.** `/` is a public GET. Putting unpublished product images on it would expose designs before launch.
- **F-714, F-715 and F-710.** These need a second model provider.
- **F-699 and F-705.** These need a deploy and a challenger spend reservation.
- **F-707.** Visual `METHOD_VERSION` belongs to the Workstream C visual lane.

**Incident:** while choosing suites by grep, I started the forbidden `test_cert_wiring.py`. It ran for about 10 minutes before I stopped it by PID; no other process was touched. Suites are now picked by name only.

## 35. Batch AC: the last 22 rows (Learn, process, session log)

**Prerequisite check.** F-815 (knowledge graph) is built: `/api/learn/graph`, `link_topics` and `expand_topics` exist. Launch has not happened; the company is in SHADOW. Rows whose own next action says "post-launch" are therefore gated on launch.

| Row | Commit | What | Test |
|---|---|---|---|
| F-807 / F-803 / F-830 | 360a25b3 | `learn/graph_feeds.py`, run in `learn.scan`. Prerequisite edges are derived from the stitch taxonomy, and `ladder()` gives the learning path. SEO keyword phrases naming a stitch (US or UK) queue its Learn gap; an ambiguous name such as "double crochet" queues both readings and records the ambiguity. Resolved support cases become reusable `faq:<label>` nodes | test_w4_fmbatch1_learn_graph |
| F-814 | 15949000 | `growth/constellation.py`, `/api/marketing/constellation/{slug}` (operator-only): the product's held content, approved lessons for its pattern topics (through the graph), gauge help, FAQ members and internal links. Needs with no lesson are named. Route pin declared | test_w4_fmbatch1_constellation |
| F-824 | 8df9f3e6 | `learn/accessibility.py`. A diagram needs an accessible name and one text label per stage; one that fails is not served. Lessons carry alt text and an accessibility report, state their terminology, and keep steps worded and short | test_w4_fmbatch1_learn_a11y |
| F-800 | e85d5571 | `learn/curriculum.py`, `/api/learn/curriculum` (editor-only): foundations, building and advanced tracks set by depth on the prerequisite ladder, techniques placed by a table, unknown topics listed as `unplaced`, coverage per track | test_w4_fmbatch1_curriculum |
| F-864 / F-868 / F-869 | 73addbc7 | `ops/session_log.py`, writing to `research/final_build/SESSION_LOG.jsonl` in the repository. It records each session's outcome by model, a checkpoint (last pushed SHA plus uncommitted paths) and approval prompts. The summary shows UNMEASURED, never zero | test_w4_fmbatch1_session_log |

**Proposals** (`OVERRIDES_PROPOSED_FMBATCH1_G.json`):
- Gated on launch: F-804, F-809, F-816, F-817, F-823, F-828.
- F-818 belongs to the staleness lane (it registers lesson artefacts through `ops/artefacts`).
- F-829 is stale: the Learn improvement cell already exists.
- F-861, F-862, F-863, F-865 and F-866 are "keep practice" rows.
- F-652 product imagery is held off the public `/` page until launch, by coordinator decision. The rest of its design pass shipped with F-670.

**No unblocked rows remain** in the 74-row list.

## 36. Delta review of cbd4ff1: N-1 to N-8

| Finding | Commit | Fix | Test (fails before, passes after) |
|---|---|---|---|
| N-1 (High) | 15e06e61 | `/api/finance/owner` is operator-only and `owner_view` is gone from the public `/api/finance`. Route audit: the department workspace, the lifecycle board and the new `/api/spend-report/governance` are operator-only, and `/m` shows only a decision count with a link to `/cc/`. | test_w4_fmbatch1_finance_owner (negative test: unauthenticated `/api/finance` carries none of the owner keys or a bank line id); test_w4_fmbatch1_route_audit (every added route, by name) |
| N-2 | 9d2b1ce6 | `taxonomy_drift.held_drift` feeds `release_gates.for_publish`. A held drift blocks publication; `gate.certify` is still not halted. | test_w4_fmbatch1_drift (default path) |
| N-3 | 635281e4 | `executive_plan._goals` reads the order-source state: UNKNOWN / `met` None when disconnected. The earlier assertion of a measured 0 codified the defect and was corrected. | test_w4_fmbatch1_executive_plan |
| N-4..N-8 | 9ab57408 | N-4: the reason is given per invocation (`--auto-rollback-reason`), a standing env reason is refused, and the header is fixed. N-5: an IDN redirect raises `FetchRefused`. N-6: `_verify_status`, and UNKNOWN outranks DEGRADED. N-7: `PLAN_MAX_AGE` is 6 h. N-8: record once, with a `billed` flag. | test_w4_fmbatch1_rollback, test_w4_fmbatch1_research_run, test_w4_fmbatch1_provider_health, test_w4_fmbatch1_executive_plan, test_w4_fmbatch1_compat |

**Route audit result.**

*Public, carrying no owner, finance, customer or unpublished-product data:*
- `/api/finance`, now aggregates only (as at 871b84a);
- `/api/useful-work`;
- `/api/company/departments`;
- `/api/spend-report`, as before this branch;
- `/api/owned`;
- `/m`.

*Operator-only:* `/api/finance/owner`, `/api/orchestrator`, `/api/opportunities`, `/api/etsy/scorecard`, the product dossier, `/api/products/lifecycle`, `/api/evidence`, the constellation, the department workspace, `/api/physical-truth` and `/api/spend-report/governance`.

*Gated by the Learn editor credential:* `/api/learn/curriculum`.

*Default-deny (POST):* `/api/research/evidence`.

**Note.** `/` (not added by this branch) still renders the owner inbox cards publicly. `/m` no longer does. Whether `/` should match is for the owner.

**Pre-existing failure (not from these fixes).** `test_cert_publish_gates` fails 3 tests identically at 871b84a and at the head before N-2: "store.publish never evaluated the release gates" and two related failures. It belongs to the publication lane.
