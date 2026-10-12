# INTEGRATION CHECKLIST

Order: **Platform → Orders → Growth → Design → Improve → Intel**. This is an integrator checklist, not authorization for Codex to apply patches, commit, push, migrate or deploy. No stage has been executed by this pack.

## Rules applying to every stage

- [ ] Pin and record the integrated parent and candidate hashes. The reviewed artifact checkpoint is `0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56`; six candidate series start from `9d6eed2`. Do not recover by resetting the current integrator branch to the old base.
- [ ] Obtain each agent's final per-row report when available; the preserved snapshot had none. Read patch contents and evidence over stale prose.
- [ ] Preserve C-73: member-certification collection triggers; no waiting spin; valid band priority; disclosure checks per distinct release; rendered_pages membership `(35, 39)`.
- [ ] Preserve Claude's in-progress independence test/rerun. Opus incorporates its eventual results and decides any necessary revalidation after pool changes; Codex does not edit or duplicate that work.
- [ ] Reconcile every changed handler, cadence, grant, priority and retention entry. Validate fresh and populated disposable DBs; do not run production migrations.
- [ ] Run common suites below and the stage-focused suites, retaining commands, exit codes, complete output, exact SHA/environment and fixture scope. No synthetic output is a pass record.
- [ ] Execute the stage's BEFORE and DURING adversarial cases. AFTER gaps may continue as assigned unfinished work; they cannot be recommended complete, and any protected action depending on them remains gated.
- [ ] Run final-action negative controls with spy adapters. The expected observable result is zero forbidden writes/spend plus a durable refusal.
- [ ] On a STOP condition, stop acceptance/advancement of the affected dependency path and return it to the assigned cluster. Independent safe launch-critical work may continue; do not turn every improvement into a new universal prelaunch gate.

Common suites after each stage, from `brambleloop/` in the integrator's authorized test checkout:

```text
python tests/test_closure.py
python tests/test_platform.py
python tests/test_cert_orchestration.py
python tests/test_capability_gates.py
python tests/test_executor.py
python tests/test_cert_wiring.py
```

This pack does not prescribe a new interpreter or dependencies; use the checkpoint's supported test environment. Check whole output/exit status for these script-style suites, not only the presence of a PASS line.

## 1. Platform

**Prerequisites:** Start from the preserved integrator checkpoint, retaining C-73 and the untouched Claude-independence work. Preserve current work before any integrator-authorized recovery. Finish C-65 precedence/proof/unchecked-state issues first. Confirm the disposable DB and concurrency harness.

**Expected preserved series:** `patches/platform.mbox`, ordered commit headers:

```text
d06928893f4615623023f1708c208e708cb686cb
02cc3a15bb42c3e6f2b2768f0db6162890e27e85
2c20df59235125da31950c110bb1b170b2b1e236
81ece066a2ceb921ecff921c42aa0be1c0c14960
0006b991ceabf3978e33483e67a2e047ad9b506b
253e71701c2c06a5ddd3db53419fd115768d53d5
```

Also reconcile `platform.uncommitted.diff` and separately preserved `platform_untracked/test_cert_thrash.py`; the latter currently blesses repeated-sweep backoff and needs the new negative case.

**Manual semantic reconciliations:** Reconcile closure semantics before relying on its totals. Keep executor capability tuples while making explicit reopen authoritative. Join queue claim, lane reservations, worker-target limits and cost controls. Preserve C-73 collection triggers. Require hash-bound review/rebuild completion and durable withheld reasons; do not accept unique-value UNMEASURED as success.

**Focused suites in addition to common suites:**

```text
python tests/test_reachability.py
python tests/test_cert_lanes_capacity.py
python tests/test_cert_rebuild_chain.py
python tests/test_cert_culture_teardown.py
python tests/test_cert_unique_value.py
python tests/test_gallery_escalation.py
python tests/test_cert_listing_frames.py
python tests/test_cert_thrash.py
```

**New adversarial cases and timing:**

- [AT-P01](ADVERSARIAL_TEST_PLAN.md#AT-P01) — BEFORE: Reopened status is overridden by executor gate membership
- [AT-P02](ADVERSARIAL_TEST_PLAN.md#AT-P02) — BEFORE: Module reachability is mistaken for requirement proof
- [AT-P03](ADVERSARIAL_TEST_PLAN.md#AT-P03) — BEFORE: Unchecked gates can coexist with closed_out
- [AT-P04](ADVERSARIAL_TEST_PLAN.md#AT-P04) — BEFORE: Unique-value comparison permits unmeasured or unsupported superiority
- [AT-P05](ADVERSARIAL_TEST_PLAN.md#AT-P05) — BEFORE: Delight scores are fixed proxies and can use another version
- [AT-P06](ADVERSARIAL_TEST_PLAN.md#AT-P06) — BEFORE: Frame review can clear unjudged, empty or stale evidence
- [AT-P07](ADVERSARIAL_TEST_PLAN.md#AT-P07) — BEFORE: Polling backoff grows without a new observation
- [AT-P08](ADVERSARIAL_TEST_PLAN.md#AT-P08) — BEFORE: New build SHA stands in for changed failure hypothesis
- [AT-P09](ADVERSARIAL_TEST_PLAN.md#AT-P09) — BEFORE: Lane enforcement needs atomic concurrent admission
- [AT-P10](ADVERSARIAL_TEST_PLAN.md#AT-P10) — BEFORE: Rebuild completion is not strictly request-bound
- [AT-P11](ADVERSARIAL_TEST_PLAN.md#AT-P11) — BEFORE: Escalation plans do not prove distinct rung execution
- [AT-P12](ADVERSARIAL_TEST_PLAN.md#AT-P12) — BEFORE: Launch readiness uses weak rollback and baseline proxies
- [AT-P13](ADVERSARIAL_TEST_PLAN.md#AT-P13) — BEFORE: Experiment cost attribution is partly a job-type proxy
- [AT-P14](ADVERSARIAL_TEST_PLAN.md#AT-P14) — AFTER: Continuous critical-dependency actions remain absent
- [AT-P15](ADVERSARIAL_TEST_PLAN.md#AT-P15) — AFTER: Validated-products-per-dollar optimization remains absent
- [AT-P16](ADVERSARIAL_TEST_PLAN.md#AT-P16) — AFTER: Recognizability without model remains unevidenced
- [AT-P17](ADVERSARIAL_TEST_PLAN.md#AT-P17) — AFTER: Opportunity scorers do not consume evidence freshness/population weighting
- [AT-P18](ADVERSARIAL_TEST_PLAN.md#AT-P18) — AFTER: Seasonal takeover has plans but no proven apply/revert executor

Consult [cross-cluster cases AT-X01–AT-X04](ADVERSARIAL_TEST_PLAN.md) at every relevant stage. All case content is authoritative by ID, independent of renderer heading-anchor behavior.

**Runtime traces:** closure → actionable OPEN accounting; scheduler → atomic lane claim → completion/recovery; invalidation → exact rebuild → hash evidence; withheld release → every downstream refusal.

**STOP:** STOP if any of the 20 reopened rows is hidden, unchecked gates look verified, missing evidence clears a quality gate, concurrent claims breach capacity, stale assets satisfy rebuild, or a free poll never becomes eligible. Missing #29/#50/#31/#44/#38/#131 stays assigned and incomplete; do not invent closure to proceed.

Stage evidence record (Opus fills, no values assumed): parent SHA; candidate SHA; reconciliations; executed suites and artifact URLs; new case results; observed traces; unresolved finding IDs; valid gates; reviewer; acceptance decision.

## 2. Orders

**Prerequisites:** Platform foundations accepted on the integration branch; current gates and source scopes remain enforced. Define paid/cancelled/refund semantics from the supported receipt payload and deterministic source fixtures. No real shop write or owner scope bypass.

**Expected preserved series:** `patches/orders.mbox`, ordered commit headers:

```text
0f50457f2e0f3019714f44bd59d8375dd5d7b1f6
8837c2fb864c8f4c4e03ea924f7841d1ca53ff7a
```

Saved uncommitted diff/status reports no additional work.

**Manual semantic reconciliations:** Integrate model additions through existing schema/bootstrap semantics on disposable data. Make order/version/ledger a recoverable logical unit, preserve signed contribution and original currency/basis. Agree unknown attribution and historic version handling with Growth/Design/Intel before consumers rely on readings.

**Focused suites in addition to common suites:**

```text
python tests/test_cert_orders.py
python tests/test_cert_commerce.py
python tests/test_cert_publish_gates.py
```

**New adversarial cases and timing:**

- [AT-O01](ADVERSARIAL_TEST_PLAN.md#AT-O01) — BEFORE: Receipt state is not reconciled for late full or partial refunds
- [AT-O02](ADVERSARIAL_TEST_PLAN.md#AT-O02) — BEFORE: Unpaid and cancelled receipts can become sales
- [AT-O03](ADVERSARIAL_TEST_PLAN.md#AT-O03) — BEFORE: Historical sale versions are assigned from current listing state
- [AT-O04](ADVERSARIAL_TEST_PLAN.md#AT-O04) — BEFORE: Out-of-order history corrupts first-purchase and repeat cohorts
- [AT-O05](ADVERSARIAL_TEST_PLAN.md#AT-O05) — BEFORE: Crash can leave order without version or ledger evidence
- [AT-O06](ADVERSARIAL_TEST_PLAN.md#AT-O06) — BEFORE: Unknown Etsy acquisition becomes organic and loop counters resist correction
- [AT-O07](ADVERSARIAL_TEST_PLAN.md#AT-O07) — BEFORE: Negative contribution is suppressed and fee estimates can look measured
- [AT-O08](ADVERSARIAL_TEST_PLAN.md#AT-O08) — BEFORE: Pricing and offer guards may annotate rather than prevent actions
- [AT-O09](ADVERSARIAL_TEST_PLAN.md#AT-O09) — BEFORE: Certification is treated as correction without correction scope
- [AT-O10](ADVERSARIAL_TEST_PLAN.md#AT-O10) — BEFORE: North-star metrics use draft and research proxies

Consult [cross-cluster cases AT-X01–AT-X04](ADVERSARIAL_TEST_PLAN.md) at every relevant stage. All case content is authoritative by ID, independent of renderer heading-anchor behavior.

**Runtime traces:** source receipt/revision → payment/refund truth → complete order/version/ledger → readings → bounded downstream decisions; correction provenance → affected buyer preparation.

**STOP:** STOP on unsupported recognized revenue, wrong refund amount, order/version/ledger divergence, first-purchase dependence on ingestion order, inferred historical version, false organic attribution or a guard that only warns before forbidden action.

Stage evidence record (Opus fills, no values assumed): parent SHA; candidate SHA; reconciliations; executed suites and artifact URLs; new case results; observed traces; unresolved finding IDs; valid gates; reviewer; acceptance decision.

## 3. Growth

**Prerequisites:** Orders commercial-truth contract passes late-update and restart cases. Platform accepts a documented rebuild request shape. Keep all actual ads/network-write paths gated. Prepare priority-contract tests even though Improve is not yet integrated.

**Expected preserved series:** `patches/growth.mbox`, ordered commit headers:

```text
120813c17a5c609d0dff44e7bcbf539f834659f3
c211c919a5c4ac161fff12491ba36abb33043c9b
b2726239ba1866cf86d596b1004831f468db883f
2d3d6857dde7170795c7e38b0129d8ea2681df6b
175633f7c97f33562590ffd79df5ad3839be3b9d
072e8e574d6ef6cd1b60d7fdabbedc3c03d06c08
```

Saved uncommitted diff/status reports no additional work.

**Manual semantic reconciliations:** Replace cumulative steering with idempotent policy input; maintain immutable applied-decision history. Agree priority authority with Improve and rebuild scope with Platform. Reconcile duplicate referral/promotion readers. Separate planned/drafted/sent and eligibility/graduated states; preserve source completeness for calibration and stars/creator attribution.

**Focused suites in addition to common suites:**

```text
python tests/test_cert_growth_ops.py
python tests/test_roles.py
python tests/test_cert_commerce.py
```

**New adversarial cases and timing:**

- [AT-G01](ADVERSARIAL_TEST_PLAN.md#AT-G01) — BEFORE: Third steering run repeats priority movement
- [AT-G02](ADVERSARIAL_TEST_PLAN.md#AT-G02) — DURING: Steering escapes protected priority bands
- [AT-G03](ADVERSARIAL_TEST_PLAN.md#AT-G03) — DURING: Fast-lane targeted rebuild request is not consumed
- [AT-G04](ADVERSARIAL_TEST_PLAN.md#AT-G04) — BEFORE: Commercial evidence has consumers but no normal producer
- [AT-G05](ADVERSARIAL_TEST_PLAN.md#AT-G05) — BEFORE: Blank agreements can pass tester graduation
- [AT-G06](ADVERSARIAL_TEST_PLAN.md#AT-G06) — AFTER: Distribution plans are not executable production chains
- [AT-G07](ADVERSARIAL_TEST_PLAN.md#AT-G07) — BEFORE: Club cadence uses release spacing and lacks feasibility input
- [AT-G08](ADVERSARIAL_TEST_PLAN.md#AT-G08) — BEFORE: Support draft timing can prevent later delivery measurement
- [AT-G09](ADVERSARIAL_TEST_PLAN.md#AT-G09) — BEFORE: Unknown traffic and absent contribution distort benchmark readings
- [AT-G10](ADVERSARIAL_TEST_PLAN.md#AT-G10) — BEFORE: Calibration can score overlapping or missing observations as actuals
- [AT-G11](ADVERSARIAL_TEST_PLAN.md#AT-G11) — BEFORE: Planning-time ads gates are not an execution-time guarantee
- [AT-G12](ADVERSARIAL_TEST_PLAN.md#AT-G12) — AFTER: Experiment rank changes may only reorder the dashboard
- [AT-G13](ADVERSARIAL_TEST_PLAN.md#AT-G13) — AFTER: Ads eligibility countdown and credit/cash separation are absent

Consult [cross-cluster cases AT-X01–AT-X04](ADVERSARIAL_TEST_PLAN.md) at every relevant stage. All case content is authoritative by ID, independent of renderer heading-anchor behavior.

**Runtime traces:** normal receipt/statistics producer → qualified economic reading → steer/plan → actual queue/action consumer; revoked authority after plan → zero adapter calls.

**STOP:** STOP if third run moves same decision again, ordinary work escapes protected bands, a targeted request broadens silently, source-less fixture fields become measured, blank agreements permit graduation, or planning bypasses the final spend guard. Live ads execution remains unavailable until its real integration and authority are proved.

Stage evidence record (Opus fills, no values assumed): parent SHA; candidate SHA; reconciliations; executed suites and artifact URLs; new case results; observed traces; unresolved finding IDs; valid gates; reviewer; acceptance decision.

## 4. Design

**Prerequisites:** Platform artifact/withholding foundations and Orders lifecycle truth are available. Record Intel prerequisites explicitly as pending until stage 6; do not fill missing judgement with synthetic rows in certification proof.

**Expected preserved series:** `patches/design.mbox`, ordered commit headers:

```text
7c3ad9d5f900e4e5019e88141b507c19c4eadd00
6df21318e9bcae5d1ec937a29e15480d194d53b1
7195d265da682396682973a6d2ac6e315424f826
```

Saved uncommitted diff/status reports no additional work.

**Manual semantic reconciliations:** Carry exact event/gap/concept/brief hashes through tournament→intake→CIR. Retain funnel refusal before engineering. Distinguish seller language from buyer evidence and publication from draft age. Preserve both Orders commercial directives and Improve/Intel lesson/reference inputs when merging ideation.

**Focused suites in addition to common suites:**

```text
python tests/test_cert_ideation.py
python tests/test_cert_preengineering.py
python tests/test_cert_design_pipeline.py
```

**New adversarial cases and timing:**

- [AT-D01](ADVERSARIAL_TEST_PLAN.md#AT-D01) — BEFORE: Winner judgement contract lacks a proven production writer
- [AT-D02](ADVERSARIAL_TEST_PLAN.md#AT-D02) — BEFORE: Reconsideration misses changed prerequisite evidence
- [AT-D03](ADVERSARIAL_TEST_PLAN.md#AT-D03) — BEFORE: Gap progression can attach to the wrong arena
- [AT-D04](ADVERSARIAL_TEST_PLAN.md#AT-D04) — BEFORE: Pipeline report advances on artifact or listing existence
- [AT-D05](ADVERSARIAL_TEST_PLAN.md#AT-D05) — BEFORE: Draft age can become launch-failure evidence
- [AT-D06](ADVERSARIAL_TEST_PLAN.md#AT-D06) — BEFORE: Seller language is labelled buyer evidence
- [AT-D07](ADVERSARIAL_TEST_PLAN.md#AT-D07) — AFTER: Breakthrough and cardigan end-to-end scope remains unfinished
- [AT-D08](ADVERSARIAL_TEST_PLAN.md#AT-D08) — BEFORE: Funnel evidence must bind the actual concept payload

Consult [cross-cluster cases AT-X01–AT-X04](ADVERSARIAL_TEST_PLAN.md) at every relevant stage. All case content is authoritative by ID, independent of renderer heading-anchor behavior.

**Runtime traces:** observed opportunity/event → generated winner → genuine judgement → funnel/gate → CIR → approved current-release artifacts → actual lifecycle events → response learning.

**STOP:** STOP on ambiguous gap mutation, mutated-concept reuse of a funnel verdict, stage completion from old/unapproved rows or launch failure learned from a draft. #308's safe refusal is not a delivered cardigan. Design end-to-end acceptance remains pending Intel's valid producer contract.

Stage evidence record (Opus fills, no values assumed): parent SHA; candidate SHA; reconciliations; executed suites and artifact URLs; new case results; observed traces; unresolved finding IDs; valid gates; reviewer; acceptance decision.

## 5. Improve

**Prerequisites:** Platform queue/pool semantics and Growth priority inputs defined; Orders outcome provenance accepted. Have independent evaluator identities and disposable failure-injection harness. Confirm no unrelated approval/permission expansion.

**Expected preserved series:** `patches/improve.mbox`, ordered commit headers:

```text
0f76cf247383e9308cb48c1d469227136496ce4e
3682e969254fa15ebdb4d9e1b9995773499b30ba
d06802e745e245eccdbe2ac88b50ea26a97cf50d
9a2ee67c405dbf9d9b56407c02512ba1f6b20652
```

Also reconcile `improve.uncommitted.diff` for `test_cert_wiring.py`; preserve current C-73 semantics.

**Manual semantic reconciliations:** Unify within-band priority authority with Growth. Reconcile pool/lane/backlog semantics with replay or restrict promotion claims until faithful. Persist rollback pending/effect/completion across restarts. Bind self-audits and competitive standards to exact releases/scopes, and merge veto with Platform's durable withholding. Apply saved test_cert_wiring diff only after preserving stronger C-73 checks.

**Focused suites in addition to common suites:**

```text
python tests/test_cert_improve_wave.py
python tests/test_swarm_runtime.py
python tests/test_cert_wiring.py
python tests/test_cert_culture_teardown.py
```

**New adversarial cases and timing:**

- [AT-M01](ADVERSARIAL_TEST_PLAN.md#AT-M01) — BEFORE: Rollback state commits before rollback effect
- [AT-M02](ADVERSARIAL_TEST_PLAN.md#AT-M02) — DURING: Replay model differs from multi-worker runtime
- [AT-M03](ADVERSARIAL_TEST_PLAN.md#AT-M03) — BEFORE: New replay record can be mistaken for fresh post-promotion evidence
- [AT-M04](ADVERSARIAL_TEST_PLAN.md#AT-M04) — BEFORE: Registered test filenames are not test execution provenance
- [AT-M05](ADVERSARIAL_TEST_PLAN.md#AT-M05) — BEFORE: Lesson matches receive invented currency-valued priority
- [AT-M06](ADVERSARIAL_TEST_PLAN.md#AT-M06) — AFTER: Adopting an audit floor does not implement the underlying improvement
- [AT-M07](ADVERSARIAL_TEST_PLAN.md#AT-M07) — BEFORE: Self-audits and keyword checks can certify wrong content
- [AT-M08](ADVERSARIAL_TEST_PLAN.md#AT-M08) — BEFORE: Taste and function-quality heuristics overstate independent quality
- [AT-M09](ADVERSARIAL_TEST_PLAN.md#AT-M09) — AFTER: Priority-policy replay is not a general challenger engine
- [AT-M10](ADVERSARIAL_TEST_PLAN.md#AT-M10) — DURING: Veto withholding must survive all rebuild paths

Consult [cross-cluster cases AT-X01–AT-X04](ADVERSARIAL_TEST_PLAN.md) at every relevant stage. All case content is authoritative by ID, independent of renderer heading-anchor behavior.

**Runtime traces:** proposal → independently evaluated dataset → promotion → active runtime config → fresh outcome → recoverable rollback; teardown obligation → changed artifact → release-specific independent evaluation.

**STOP:** STOP if REVERTED can coexist with un-restored active configuration after restart, reused history becomes fresh uplift, metadata filenames count as executed tests, proxy money/quality is reported measured, or a veto is lost through rebuild.

Stage evidence record (Opus fills, no values assumed): parent SHA; candidate SHA; reconciliations; executed suites and artifact URLs; new case results; observed traces; unresolved finding IDs; valid gates; reviewer; acceptance decision.

## 6. Intel

**Prerequisites:** Prior stages retain unresolved labels honestly. Design judgement/identity contract, Improve benchmark scope and Platform final-gate rules agreed. Preserve current C-73 and Claude-independence test without replacing their assumptions with stale patch context.

**Expected preserved series:** `patches/intel.mbox`, ordered commit headers:

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

Saved uncommitted diff/status reports no additional work.

**Manual semantic reconciliations:** Carry unresolved policy change across identical snapshots. Keep distinctiveness and swatches typed as limited evidence. Bind photos to real bytes/rights and published exposure. Separate seller and buyer geography. Reconcile Design/Intel event→winner progression and collection no-spin coherence behavior. Only Opus may reconcile real registry parks after proof; synthetic executor fixtures stay isolated.

**Focused suites in addition to common suites:**

```text
python tests/test_cert_intel_wave.py
python tests/test_cert_intel_wave2.py
python tests/test_executor.py
python tests/test_cert_growth_seasonal.py
python tests/test_seasonal_incidents.py
python tests/test_cert_design_pipeline.py
python tests/test_cert_improve_wave.py
```

**New adversarial cases and timing:**

- [AT-I01](ADVERSARIAL_TEST_PLAN.md#AT-I01) — BEFORE: Repeated unchanged policy snapshot erases unreviewed change
- [AT-I02](ADVERSARIAL_TEST_PLAN.md#AT-I02) — BEFORE: Distinctiveness is substituted for top-decile strength
- [AT-I03](ADVERSARIAL_TEST_PLAN.md#AT-I03) — BEFORE: Fabric swatch does not prove finished-product visual fidelity
- [AT-I04](ADVERSARIAL_TEST_PLAN.md#AT-I04) — BEFORE: Photo intake validates hash syntax and rights label, not evidence
- [AT-I05](ADVERSARIAL_TEST_PLAN.md#AT-I05) — BEFORE: Photo planning stops before review/publication but starts impact clock
- [AT-I06](ADVERSARIAL_TEST_PLAN.md#AT-I06) — BEFORE: Seller location opens a buyer-market evidence gate
- [AT-I07](ADVERSARIAL_TEST_PLAN.md#AT-I07) — BEFORE: Drift incidents resolve when evidence ages out or becomes unreadable
- [AT-I08](ADVERSARIAL_TEST_PLAN.md#AT-I08) — BEFORE: Benchmark-refresh trigger and purchased candidate can diverge
- [AT-I09](ADVERSARIAL_TEST_PLAN.md#AT-I09) — BEFORE: Company standing and entry superiority rely on capability/count proxies
- [AT-I10](ADVERSARIAL_TEST_PLAN.md#AT-I10) — AFTER: Quote-token heuristics cover only explicit title forms
- [AT-I11](ADVERSARIAL_TEST_PLAN.md#AT-I11) — AFTER: Registry reclassification is not in the preserved patch
- [AT-I12](ADVERSARIAL_TEST_PLAN.md#AT-I12) — DURING: Collection patch context predates the fixed no-spin behavior

Consult [cross-cluster cases AT-X01–AT-X04](ADVERSARIAL_TEST_PLAN.md) at every relevant stage. All case content is authoritative by ID, independent of renderer heading-anchor behavior.

**Runtime traces:** benchmark/reference producer → typed evidence → Design/Improve consumer → gated action; policy/photo/drift events → durable eligibility → final publication refusal; final registry/gate truth → independent full audit.

**STOP:** STOP if A→B→B clears a policy block, aged/unreadable drift evidence clears an incident, swatch/rarity clears finished-product/strength checks, fake photo/rights evidence reaches use, seller country opens a buyer-population gate, or C-73 no-spin behavior regresses. No integrated acceptance based on patched test comments.

Stage evidence record (Opus fills, no values assumed): parent SHA; candidate SHA; reconciliations; executed suites and artifact URLs; new case results; observed traces; unresolved finding IDs; valid gates; reviewer; acceptance decision.

## Final integrated validation

- [ ] Re-run cross-cluster contracts on the complete head. Rerun Design after Intel producers, Growth after Improve priority reconciliation, and Improve after Platform pool changes.
- [ ] Fresh full suite on a clean final integrated checkout, using repository-supported runner; no status restoration to make tests pass.
- [ ] Independent 320-row function-level audit using [FALSE_COMPLETION_AUDIT_TEMPLATE.md](FALSE_COMPLETION_AUDIT_TEMPLATE.md), with all actionable C-60 failures accounted for.
- [ ] Verify exact current gate states and separately validate each gated row's built half. Unknown gate state is not verified closure.
- [ ] Resolve or evidence-disprove every finding that affects a claimed requirement, preserving counterevidence. All unresolved executable obligations stay incomplete.
- [ ] Opus alone reconciles requirement ledger, certification defects and final report. Certification cannot follow from zero reported OPEN rows while proof/gate defects remain.

The stage order matches RESUME_MANIFEST.md. The disagreement is the prerequisite quality: C-65 work exists but is incomplete; Design/Intel and Growth/Improve need post-combination validation rather than acceptance of isolated green suites.
