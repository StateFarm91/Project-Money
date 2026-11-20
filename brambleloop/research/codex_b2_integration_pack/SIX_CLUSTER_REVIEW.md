# COMPLETE SIX-CLUSTER REVIEW — PRESERVED AUDIT

This preserves the accepted independent audit as a navigable repository handoff. It is not certification. Detailed normalized defects, affected symbols, evidence links, smallest repair proposals and regression specifications are in [FINDINGS.md](FINDINGS.md) / [FINDINGS.json](FINDINGS.json). Read this review together with those records; no finding is considered repaired by documentation.

**Scope:** static review of the six preserved patch series and checkpoint evidence; no patches applied, application source changed or tests executed. Real DB/worker tests described below are tests present in patches, not runs performed by Codex. A complete integrated full suite and independent 320-row trace remain required.

| Cluster | Requirements | Patch state | Disposition | Reachability risk | Merge risk | Order |
|---|---:|---|---|---|---|---:|
| Platform | 20 | 6 commits + dirty diff + untracked test | REJECT / REWORK selected closure/gate/recovery portions | High | Very high | 1 |
| Orders | 17 | 2 commits | REJECT / REWORK source-of-truth ingest | High | High | 2 |
| Growth | 35 | 6 commits | REJECT / REWORK steering/evidence | High | Very high | 3 |
| Design | 21 | 3 commits | INCOMPLETE / WAIT FOR AGENT | High | Very high | 4 |
| Improve | 32 | 4 commits + dirty test diff | ACCEPT WITH FIXES | Medium–high | Very high | 5 |
| Intel | 26 | 9 commits | REJECT / REWORK selected policy/evidence portions | High | Very high | 6 |

No whole cluster is ACCEPT CANDIDATE for certification. Reject/rework preserves useful candidate work; it does not instruct discarding or restarting it. Opus selects and repairs; Codex has no assigned implementation cluster.


## Platform

**Assigned IDs:** 5, 29, 30, 31, 34, 38, 40, 44, 50, 54, 59, 61, 81, 131, 163, 169, 171, 172, 175, 188.

**Associated defects:** C-60, C-65, C-67, C-68, C-69, C-72; C-73 interaction.

**Exact preserved commits:**

```text
d06928893f4615623023f1708c208e708cb686cb
02cc3a15bb42c3e6f2b2768f0db6162890e27e85
2c20df59235125da31950c110bb1b170b2b1e236
81ece066a2ceb921ecff921c42aa0be1c0c14960
0006b991ceabf3978e33483e67a2e047ad9b506b
253e71701c2c06a5ddd3db53419fd115768d53d5
```

platform.uncommitted.diff changes orchestrate; platform_untracked/test_cert_thrash.py is separately preserved and currently endorses increasing backoff on a sweep without a new poll.

**Files changed:**

- `brambleloop/src/brambleloop/build2/closure.py`
- `brambleloop/src/brambleloop/build2/reachability.py`
- `brambleloop/src/brambleloop/app/runner.py`
- `brambleloop/src/brambleloop/commerce/lanes.py`
- `brambleloop/src/brambleloop/finance/governor.py`
- `brambleloop/src/brambleloop/runtime/release.py`
- `brambleloop/src/brambleloop/swarm/capacity.py`
- `brambleloop/src/brambleloop/swarm/orchestrate.py`
- `brambleloop/src/brambleloop/runtime/pipeline.py`
- `brambleloop/src/brambleloop/teardown/lab.py`
- `brambleloop/src/brambleloop/teardown/scorecard.py`
- `brambleloop/src/brambleloop/visual/gallery.py`
- `brambleloop/src/brambleloop/visual/parity.py`
- `brambleloop/src/brambleloop/launch/readiness.py`
- `brambleloop/src/brambleloop/publish/layout_qa.py`
- `brambleloop/src/brambleloop/publish/listing_assets.py`
- `brambleloop/src/brambleloop/queue/durable.py`
- `brambleloop/src/brambleloop/runtime/worker.py`
- `brambleloop/src/brambleloop/visual/inspect.py`

**Actual runtime behavior, consumers and evidence:** Embedded worker pool and target activation; function/product lane controls at runtime; experiment cost attribution; twin/geometry/reverse/support/bundle provenance; targeted rebuild dispatch/completion; persisted certificate withholding; FAQ/terms consistency; frame layout and review; live escalation gates; launch readiness and thrash suspension. Consumers exist in runner/scheduler/claim/certify/draft/rebuild paths. Durable audit/provenance and withheld-state writes are real implementation, but their semantics must be validated.

**Gates, defects and evidence limits:** C-65 IS present in d069288: more selective call graph, library-over-root preference, owner-gated built-half checking and explicit unchecked-gate state. The manifest claim that no repair exists is stale. It does NOT repair the 20-row executor gate override; module-level existential proof and unchecked closed_out remain. Unique-value UNMEASURED is explicitly nonblocking in a test; certificate and fixed delight proxies are not comparative quality proof. Frame verdict conversion and empty/stale review sets need rework. Poll backoff can extend without new observation and unrelated build SHA is accepted as changed hypothesis. Targeted rebuild needs exact request/fingerprint proof; lane concurrency needs simultaneous claims. Escalation enqueues a reason, not demonstrated distinct strategy execution. Readiness and experiment attribution retain proxy risks.

**Apparently implemented slices:** Built slices of 5/30/175/188, 40, 54/59/61, 81, 163/169, 171/172 and 34 have meaningful runtime wiring. None is recommended complete from this series.

**Clearly unfinished / insufficient:** 29/50, 31, 38, 44 and 131 remain missing/weak despite adjacent work. They remain Platform assignments. Current tests need the negative cases in P01–P18. Existing real-worker rebuild/withholding tests are useful; single-worker and proxy-quality tests do not establish their broader claims.

**Tests added/changed:** `brambleloop/tests/test_closure.py`, `brambleloop/tests/test_reachability.py`, `brambleloop/tests/test_cert_lanes_capacity.py`, `brambleloop/tests/test_cert_rebuild_chain.py`, `brambleloop/tests/test_cert_culture_teardown.py`, `brambleloop/tests/test_cert_unique_value.py`, `brambleloop/tests/test_gallery_escalation.py`, `brambleloop/tests/test_cert_listing_frames.py`. Test bodies were reviewed, not executed. Adversarial cases and exact finding functions are linked in [FINDINGS.md](FINDINGS.md).

**Shared-file/semantic risk and dependencies:** See [SOURCE_INVENTORY.md](SOURCE_INVENTORY.md) and [CROSS_CLUSTER_CONTRACTS.md](CROSS_CLUSTER_CONTRACTS.md); textual merge success is not behavioral acceptance.

## Orders

**Assigned IDs:** 11, 12, 13, 22, 26, 42, 47, 49, 104, 132, 233, 234, 235, 252, 256, 269, 271.

**Associated defects:** C-60, C-64, C-66, C-67.

**Exact preserved commits:**

```text
0f50457f2e0f3019714f44bd59d8375dd5d7b1f6
8837c2fb864c8f4c4e03ea924f7841d1ca53ff7a
```

No saved uncommitted changes.

**Files changed:**

- `brambleloop/src/brambleloop/agents/registry.py`
- `brambleloop/src/brambleloop/app/main.py`
- `brambleloop/src/brambleloop/commerce/buyer_trust.py`
- `brambleloop/src/brambleloop/commerce/cohorts.py`
- `brambleloop/src/brambleloop/commerce/order_readings.py`
- `brambleloop/src/brambleloop/commerce/orders_ingest.py`
- `brambleloop/src/brambleloop/commerce/pricing.py`
- `brambleloop/src/brambleloop/commerce/referral.py`
- `brambleloop/src/brambleloop/core/models.py`
- `brambleloop/src/brambleloop/creative/ideation.py`
- `brambleloop/src/brambleloop/creative/standard.py`
- `brambleloop/src/brambleloop/growth/loops.py`
- `brambleloop/src/brambleloop/integrations/etsy.py`
- `brambleloop/src/brambleloop/runtime/commerce_readings.py`
- `brambleloop/src/brambleloop/runtime/orders.py`
- `brambleloop/src/brambleloop/runtime/pipeline.py`
- `brambleloop/src/brambleloop/runtime/release.py`
- `brambleloop/src/brambleloop/runtime/worker.py`
- `brambleloop/src/brambleloop/scale/trajectory.py`
- `brambleloop/src/brambleloop/swarm/orchestrate.py`

**Actual runtime behavior, consumers and evidence:** Scheduled receipt reader checks successful Etsy probe and transactions_r before client construction. Writes customers/orders/version/ledger, records original currency and labelled assumed FX. Scheduled readings feed winner/ladder ideation, bundle jobs, CFO owner recommendations, repeat/referral/loops, trajectory/north-star and correction preparation.

**Gates, defects and evidence limits:** Existing transaction refs do not reconcile later refunds; any refund affects whole receipt; creation-time overlap misses old revisions; paid/cancelled checks absent. Current listing version is not delivered historical version. First encounter is not first purchase. Separate writes can leave permanent order/version gaps after crash. Unknown Etsy is later organic; negative contribution suppressed. Pricing/retirement guard annotations need final-action negatives. Certification-as-correction and north-star draft/research proxies need scope correction.

**Apparently implemented slices:** Real built halves for ingest and many downstream readers repair zero-caller defects. Owner/data gates remain meaningful, and no Etsy writes were introduced by this audit.

**Clearly unfinished / insufficient:** Commerce truth and all dependent conclusions remain unproved until O01–O10 pass. Handler tests use fake receipt feeds behind real gates and assert DB/queue effects, but omit mutable-state reconciliation, bad payment state, history ordering and crash boundaries. Existing migration machinery is additive: no standalone migration file is not itself a defect.

**Tests added/changed:** `brambleloop/tests/test_cert_orders.py`. Test bodies were reviewed, not executed. Adversarial cases and exact finding functions are linked in [FINDINGS.md](FINDINGS.md).

**Shared-file/semantic risk and dependencies:** See [SOURCE_INVENTORY.md](SOURCE_INVENTORY.md) and [CROSS_CLUSTER_CONTRACTS.md](CROSS_CLUSTER_CONTRACTS.md); textual merge success is not behavioral acceptance.

## Growth

**Assigned IDs:** 7, 17, 18, 19, 24, 27, 237, 238, 239, 242, 243, 244, 245, 246, 247, 248, 249, 250, 251, 253, 255, 257, 258, 259, 260, 261, 262, 264, 267, 273, 275, 276, 291, 294, 295.

**Associated defects:** C-60, C-66, C-67, C-70; C-64 dependency.

**Exact preserved commits:**

```text
120813c17a5c609d0dff44e7bcbf539f834659f3
c211c919a5c4ac161fff12491ba36abb33043c9b
b2726239ba1866cf86d596b1004831f468db883f
2d3d6857dde7170795c7e38b0129d8ea2681df6b
175633f7c97f33562590ffd79df5ad3839be3b9d
072e8e574d6ef6cd1b60d7fdabbedc3c03d06c08
```

No saved uncommitted changes. Removing ads types from missing-handler tests is legitimate registration repair, not evidence of campaign execution.

**Files changed:**

- `brambleloop/src/brambleloop/app/main.py`
- `brambleloop/src/brambleloop/growth/weekly.py`
- `brambleloop/src/brambleloop/runtime/release.py`
- `brambleloop/src/brambleloop/scale/confidence.py`
- `brambleloop/src/brambleloop/scale/evidence.py`
- `brambleloop/src/brambleloop/runtime/commerce_readings.py`
- `brambleloop/src/brambleloop/support/service.py`
- `brambleloop/src/brambleloop/agents/registry.py`
- `brambleloop/src/brambleloop/ops/retention.py`
- `brambleloop/src/brambleloop/runtime/growth_ops.py`
- `brambleloop/src/brambleloop/runtime/pipeline.py`
- `brambleloop/src/brambleloop/runtime/worker.py`
- `brambleloop/src/brambleloop/swarm/orchestrate.py`
- `brambleloop/src/brambleloop/scale/war_room.py`

**Actual runtime behavior, consumers and evidence:** Registered/scheduled ads planning, distribution, journey and steering. Authenticated stats-CSV input; source-derived confidence/calibration/pricing inputs; support draft timing and copy refusal; trust-proof attachment and actionable friction incidents. Ads handler is present but still explicitly refuses live execution because integration is absent.

**Gates, defects and evidence limits:** Steering overwrites daily movement history: third run can repeat; raw priority credits escape Improve bands. Growth slugs rebuild payload is not Platform's artefacts contract. Stars/creator/offsite facts are fixture-populated without receipt producer. Graduation supplies blank agreement texts yet can permit eligibility; graduated output is not durable transition. Distribution stays largely plan/readings; constructed tutorial references are not artifacts. Traffic defaults, missing contribution, overlapping calibration and draft→delivery timing require fixes. Trust is planning-time; final spend guard must recheck when a real adapter exists.

**Apparently implemented slices:** Useful slices of 17/18/19, 237, 259/261, 262/273/275 and planning for 242–251. Useful route/worker tests verify refusals and incidents.

**Clearly unfinished / insufficient:** No complete execution proof for distribution, rank-driven experiments, source-dependent commercial fields, safe steering or live campaigns. Tests cover second steering run, not third; hand-seeded agreement/source fields hide defects. Etsy Ads eligibility countdown/recheck and Etsy Plus credit versus cash tracking are absent; no date may be invented.

**Tests added/changed:** `brambleloop/tests/test_cert_growth_ops.py`, `brambleloop/tests/test_roles.py`. Test bodies were reviewed, not executed. Adversarial cases and exact finding functions are linked in [FINDINGS.md](FINDINGS.md).

**Shared-file/semantic risk and dependencies:** See [SOURCE_INVENTORY.md](SOURCE_INVENTORY.md) and [CROSS_CLUSTER_CONTRACTS.md](CROSS_CLUSTER_CONTRACTS.md); textual merge success is not behavioral acceptance.

## Design

**Assigned IDs:** 3, 88, 101, 109, 110, 112, 114, 115, 277, 278, 279, 281, 282, 283, 290, 293, 308, 309, 314, 316, 318.

**Associated defects:** C-60, C-61, C-66, C-67.

**Exact preserved commits:**

```text
7c3ad9d5f900e4e5019e88141b507c19c4eadd00
6df21318e9bcae5d1ec937a29e15480d194d53b1
7195d265da682396682973a6d2ac6e315424f826
```

No saved uncommitted changes. Intel supplies some prerequisites later; rerun complete Design trace after Intel without substituting its swatch/rarity proxies.

**Files changed:**

- `brambleloop/src/brambleloop/creative/ideation.py`
- `brambleloop/src/brambleloop/creative/intake.py`
- `brambleloop/src/brambleloop/creative/preengineering.py`
- `brambleloop/src/brambleloop/creative/prospecting.py`
- `brambleloop/src/brambleloop/runtime/pipeline.py`
- `brambleloop/src/brambleloop/runtime/release.py`
- `brambleloop/src/brambleloop/app/main.py`
- `brambleloop/src/brambleloop/commerce/intent.py`
- `brambleloop/src/brambleloop/improve/roi.py`
- `brambleloop/src/brambleloop/intel/mission.py`
- `brambleloop/src/brambleloop/intel/mission_runtime.py`
- `brambleloop/src/brambleloop/intel/observe.py`
- `brambleloop/src/brambleloop/publish/release_gates.py`
- `brambleloop/src/brambleloop/seasonal/leadtime.py`
- `brambleloop/src/brambleloop/ops/retention.py`

**Actual runtime behavior, consumers and evidence:** Stable winner identity and brief/storyboard/motif/emotional/window information. Carried judged winner reaches cir.draft→compile→certify; direct non-funnel concepts refused. Vision/skill-gap observations enter prompts. Provenance keyed to designs; gap/pipeline/mission/outcome readers expanded.

**Gates, defects and evidence limits:** Production writer for all concept.judged requirements is not proved by injected tests. Held re-entry watches limited changes. Pod-only gap selection can advance wrong arena. Pipeline stage presence can count unapproved/old assets or draft as completed SEO. Draft age can become failed launch lesson. Seller titles are marketplace seller language, not measured buyer evidence. Payload/funnel fingerprint binding needs negative proof.

**Apparently implemented slices:** Strong built slices of 3/88/101/109/110/112/114/115/277/278/281/283/290 and reporting 318. Changed direct-concept test strengthens funnel refusal; supplied-judgement worker chain is meaningful consumer proof.

**Clearly unfinished / insufficient:** 279/282/308/309 remain unfinished; 314/316/293 retain evidence problems. Cardigan test explicitly stops with no prototype/CIR: safe refusal is not delivered product. Full pattern/CIR→faithful finished-product 3D reference→photoreal output→truth/benchmark validation remains unproved.

**Tests added/changed:** `brambleloop/tests/test_cert_ideation.py`, `brambleloop/tests/test_cert_preengineering.py`, `brambleloop/tests/test_cert_design_pipeline.py`. Test bodies were reviewed, not executed. Adversarial cases and exact finding functions are linked in [FINDINGS.md](FINDINGS.md).

**Shared-file/semantic risk and dependencies:** See [SOURCE_INVENTORY.md](SOURCE_INVENTORY.md) and [CROSS_CLUSTER_CONTRACTS.md](CROSS_CLUSTER_CONTRACTS.md); textual merge success is not behavioral acceptance.

## Improve

**Assigned IDs:** 53, 90, 92, 93, 95, 96, 97, 99, 100, 129, 147, 153, 154, 155, 156, 157, 158, 159, 160, 161, 164, 174, 176, 179, 180, 187, 190, 193, 194, 220, 228, 231.

**Associated defects:** C-60, C-62, C-63, C-66, C-67; C-68/C-73 interactions.

**Exact preserved commits:**

```text
0f76cf247383e9308cb48c1d469227136496ce4e
3682e969254fa15ebdb4d9e1b9995773499b30ba
d06802e745e245eccdbe2ac88b50ea26a97cf50d
9a2ee67c405dbf9d9b56407c02512ba1f6b20652
```

improve.uncommitted.diff edits test_cert_wiring. Preserve C-73 no-spin/disclosure semantics; do not reintroduce obsolete waiting-priority behavior.

**Files changed:**

- `brambleloop/src/brambleloop/agents/registry.py`
- `brambleloop/src/brambleloop/app/main.py`
- `brambleloop/src/brambleloop/core/models.py`
- `brambleloop/src/brambleloop/improve/cells.py`
- `brambleloop/src/brambleloop/improve/league.py`
- `brambleloop/src/brambleloop/improve/replay.py`
- `brambleloop/src/brambleloop/improve/roi.py`
- `brambleloop/src/brambleloop/improve/runner.py`
- `brambleloop/src/brambleloop/intel/mission_runtime.py`
- `brambleloop/src/brambleloop/publish/release_gates.py`
- `brambleloop/src/brambleloop/queue/durable.py`
- `brambleloop/src/brambleloop/runtime/pipeline.py`
- `brambleloop/src/brambleloop/runtime/release.py`
- `brambleloop/src/brambleloop/runtime/worker.py`
- `brambleloop/src/brambleloop/swarm/orchestrate.py`
- `brambleloop/src/brambleloop/teardown/audits.py`
- `brambleloop/src/brambleloop/teardown/enforce.py`
- `brambleloop/src/brambleloop/teardown/lab.py`
- `brambleloop/src/brambleloop/teardown/pipeline.py`
- `brambleloop/src/brambleloop/teardown/scorecard.py`
- `brambleloop/src/brambleloop/creative/ideation.py`
- `brambleloop/src/brambleloop/creative/standard.py`
- `brambleloop/src/brambleloop/culture/radar.py`
- `brambleloop/src/brambleloop/growth/mix.py`
- `brambleloop/src/brambleloop/improve/consume.py`
- `brambleloop/src/brambleloop/improve/evolution.py`
- `brambleloop/src/brambleloop/improve/roles.py`
- `brambleloop/src/brambleloop/improve/bootstrap.py`
- `brambleloop/src/brambleloop/ops/retention.py`

**Actual runtime behavior, consumers and evidence:** Historical policy replay creates runs and sandbox proposals; successful promotion changes actual priority config; monitor can rollback. Teardown obligations reach publish/support; veto reaches certify/assets/publish. Lessons affect radar/engineering/SEO; weekly STOP executes stale experiment stops and queues owner decisions. Versions, ownership and function metrics become durable records.

**Gates, defects and evidence limits:** Rollback marks reverted before effect and future scans miss it on failure. Single-worker daily simulation does not model new pool/backlog/failures adequately; new run timestamp can reuse old data as fresh. Static tests_run filenames are not executions. Fixed CAD per lesson is heuristic, not measured expected value. Self-audit floor adoption does not implement the underlying improvement, slug audit can clear changed release, keywords/taste/role counts are proxies. Veto audit must join durable withheld reasons. Actual replay scope is priority policy, not general prompt/tool/model evaluation.

**Apparently implemented slices:** Promising runtime slices across 53/90/92/93/95/96/97/99/100/161/174/176/179/187/193/194/220/228/231. Real proposal→policy→rollback handler test is valuable but happy-path only.

**Clearly unfinished / insufficient:** Broad 129/147/153–160/164/180/190 claims remain partial. Needs M01–M10. Independent score fixture is not actual product change; owner cards are not new agent execution. ACCEPT WITH FIXES applies only with durability/provenance repairs, not all 32 rows.

**Tests added/changed:** `brambleloop/tests/test_cert_improve_wave.py`, `brambleloop/tests/test_swarm_runtime.py`. Test bodies were reviewed, not executed. Adversarial cases and exact finding functions are linked in [FINDINGS.md](FINDINGS.md).

**Shared-file/semantic risk and dependencies:** See [SOURCE_INVENTORY.md](SOURCE_INVENTORY.md) and [CROSS_CLUSTER_CONTRACTS.md](CROSS_CLUSTER_CONTRACTS.md); textual merge success is not behavioral acceptance.

## Intel

**Assigned IDs:** 2, 15, 39, 64, 86, 116, 125, 126, 128, 139, 165, 201, 203, 208, 210, 211, 215, 219, 226, 227, 268, 287, 289, 299, 300, 304.

**Associated defects:** C-60, C-66, C-67, C-71; C-61/C-73 interactions.

**Exact preserved commits:**

```text
78ef13457b4bf05b535cc65678046ac57171e374
1d454356b093e6c92bd56af5dd2b14564d312503
cd8af208cc468cc1b1d837ad93e9ee87c884515e
abd473b62d2bba30077c8eee101dee0a9d42757d
ac5c10ab8cc8505cadb5ccc4cc8e74fe8a781056
fc8f8ba83008d7729d3a72a365bd480dde1ee7ac
e71882b31a67e03b746a34f2ce6b9d658ec20a51
3e42d6b11769af54a4d498d082257389659ad02a
883697edb928ffe0b96b54346435737f2adc7c33
```

No saved uncommitted changes. Keep genuine image_vision/model_bearing_render/owner/data boundaries; no physical/visual evidence can be fabricated to close them.

**Files changed:**

- `brambleloop/src/brambleloop/intel/mission_runtime.py`
- `brambleloop/src/brambleloop/runtime/release.py`
- `brambleloop/src/brambleloop/agents/registry.py`
- `brambleloop/src/brambleloop/build2/executor.py`
- `brambleloop/src/brambleloop/commerce/markets.py`
- `brambleloop/src/brambleloop/core/models.py`
- `brambleloop/src/brambleloop/creative/prospecting.py`
- `brambleloop/src/brambleloop/intel/benchmarks.py`
- `brambleloop/src/brambleloop/intel/etsy_public.py`
- `brambleloop/src/brambleloop/intel/observe.py`
- `brambleloop/src/brambleloop/intel/panel_discovery.py`
- `brambleloop/src/brambleloop/intel/serp.py`
- `brambleloop/src/brambleloop/radar/arbitrage.py`
- `brambleloop/src/brambleloop/runtime/pipeline.py`
- `brambleloop/src/brambleloop/runtime/worker.py`
- `brambleloop/src/brambleloop/swarm/orchestrate.py`
- `brambleloop/src/brambleloop/intel/benchmark_refresh.py`
- `brambleloop/src/brambleloop/gates/platform_policy.py`
- `brambleloop/src/brambleloop/publish/release_gates.py`
- `brambleloop/src/brambleloop/app/main.py`
- `brambleloop/src/brambleloop/creative/board.py`
- `brambleloop/src/brambleloop/creative/preengineering.py`
- `brambleloop/src/brambleloop/creative/strength.py`
- `brambleloop/src/brambleloop/publish/physical_upgrade.py`
- `brambleloop/src/brambleloop/culture/engine.py`
- `brambleloop/src/brambleloop/seasonal/benchmark_matrix.py`
- `brambleloop/src/brambleloop/seasonal/daily.py`
- `brambleloop/src/brambleloop/ops/retention.py`
- `brambleloop/src/brambleloop/publish/model_photography.py`
- `brambleloop/src/brambleloop/visual/drift_series.py`
- `brambleloop/src/brambleloop/creative/ideation.py`
- `brambleloop/src/brambleloop/creative/reference.py`
- `brambleloop/src/brambleloop/launch/access.py`

**Actual runtime behavior, consumers and evidence:** SERP steers selection; new panel shops scanned; bounded benchmark purchase asks; CONCEPTING gaps queue same-arena work; pod maps affect ordering; actual objectives checked; coherence refuses collection draft; breakouts queue adjacent work; reference readings stored and consumed; policy/drift incidents can halt publication; photo intake queues upgrade.

**Gates, defects and evidence limits:** Policy A→B→B clears unreviewed change through latest snapshot. Distinctiveness is not top-decile strength. Prototype fabric raster is not finished-product fidelity. Photo hash syntax/rights label lacks bytes/permission proof; unapproved row has no complete review/publish path; impact starts at planning. Seller location misrepresents buyer geography. Drift expiry/unreadability can resolve incident. Refresh selection may choose other seller than trigger; baseline prose conflicts with leader-trigger path. Current-product coverage/engineering superiority use stale/count/capability proxies; quote extraction remains heuristic.

**Apparently implemented slices:** Useful slices of 2/15/116/128/139/165/208/210/211/215/219/227/287/289/299. Tests run real workers with injected boundary/row evidence, proving some consumers.

**Clearly unfinished / insufficient:** 39/64/125/126/201/268 unacceptable as written. 86/203/226/300/304 need integrator gate reconciliation. No requirements.json patch performs reclassification. Synthetic executor fixture proves mechanics only and its comments overstate registry change. Pre-C-73 seasonal-test context must not restore collection spin.

**Tests added/changed:** `brambleloop/tests/test_cert_intel_wave.py`, `brambleloop/tests/test_executor.py`, `brambleloop/tests/test_cert_growth_seasonal.py`, `brambleloop/tests/test_cert_intel_wave2.py`. Test bodies were reviewed, not executed. Adversarial cases and exact finding functions are linked in [FINDINGS.md](FINDINGS.md).

**Shared-file/semantic risk and dependencies:** See [SOURCE_INVENTORY.md](SOURCE_INVENTORY.md) and [CROSS_CLUSTER_CONTRACTS.md](CROSS_CLUSTER_CONTRACTS.md); textual merge success is not behavioral acceptance.

## Cross-cluster conclusion and unresolved disagreements

Keep Platform→Orders→Growth→Design→Improve→Intel. C-65 exists but is incomplete; executor tuple override still hides 20 reopened rows. Growth/Improve priority and Platform/Improve replay require combined validation; Design depends on Intel's valid evidence producers. Preserve C-73 and current independence work. No full integrated suite has been run. None of the six patch series updates requirements.json; comments about completed reclassification are not proof. Manifest integrity prose is not acceptance of later saved proxy/gate choices.

Conditional candidates #29/#50, #31, #44 and #38 remain Platform scope. Adjacent cost/layout/diversification/provenance additions do not close them. Etsy Ads countdown and separate credit/cash tracking remain retained owner scope related to Growth ads requirements; no date is established here.

## SAFE WORK CODEX COULD TAKE IF CLAUDE REMAINS LIMITED

No unassigned implementation cluster is established. Codex may independently specify adversarial tests, review source/producer-consumer traces and later integration diffs, and assess actual test/runtime evidence without modifying six-cluster application source. Executable independent tests or applying candidate source require an explicit authorized isolated-testing scope; do not duplicate Claude's ongoing independence rerun. No repair cluster is handed to Codex by this pack.

## Remaining uncertainty

No proposed regression case has been executed. Concurrent lane admission, some guard propagation, funnel mutation and timing/rebuild race concerns are explicitly labelled risk_requires_reproduction rather than reproduced defects. Negative searches prove absence only in the pinned preserved snapshot. Later Claude agent work may supersede these findings; compare deltas rather than repeat the entire audit. A finding disproved by a real trace should retain its counterevidence and be revised by the integrator. Static review cannot certify live operation or external capabilities.
