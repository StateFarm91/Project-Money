# W-AGENTS department capability audit (owner directive 2026-10-25)

Date 2026-10-26 (UTC). Branch `claude/w4-AGENTS`. No departments were created.

**Sources.**
- Code: `agents/registry.py`, `autonomy/charters.py`, `runtime/worker.CADENCES`, `runtime/worker.handlers` (after `runtime.pipeline` is imported), `authority/classes.py`, `laura/executive/loop.py` and `laura/agency/delegation.py`.
- Production, through public read-only GETs at 2026-10-26 ~01:16Z: `/health` (build 1580053629), `/api/jobs?limit=2000` (ids 30858–32857, about 32 hours), `/api/queue/cadences` (115 cadences, `never_enqueued: []`) and `/api/departments`.
- The probe script and raw reads are in the session scratchpad; they are not committed.

**The test of "operational".** A registry entry does not count. An agent is operational only when all of these hold:
- a handler is registered for its job type;
- a cadence or chain wakes it;
- production completed it in the window;
- its output reports work done, not `ran: false`.

## Shared machinery

All of this already exists, and every department uses it:
- **Permissions:** `Registry.authorize` checks forbidden combinations, then allowed job types, then the action class (`authority/policy.check_dispatch`).
- **Spend:** the per-agent daily ceiling (`record_cost`), plus `gateway.anthropic.check_budget` before every model call and the monthly ceiling.
- **Model routing:** the provider-neutral gateway and failover. `worker.MODEL_JOB_TYPES` are parked while the provider is down.
- **Evidence:** `AuditLog`, `operating_readings` and `company_memory`.
- **Deliverable review:** the useful-work judge (`pipeline.did_no_work`); COO `autonomy.department_review` KPIs with anti-gaming guardrails; Laura's REVIEW/CHALLENGE of each mission she delegated.
- **Failure handling:**
  - lease, retry and backoff, then a dead letter (`queue.durable`);
  - `ops.queue_check` re-drives a dead letter once per deploy;
  - `improve.mine` turns dead letters into lessons;
  - write-ahead effect intents for external writes (`queue.effects`).
- **Laura's authority:**
  - she can delegate only job types that are both in the charter's `generatable` list and in `SAFE_GENERATED`, through the COO enqueue boundary and the constitution check;
  - protected types become owner cards;
  - spending, her own identity and the logo/banner are refused.

## Department table

**Columns.**
- **Handled/declared:** job types the department's agents hold that have a handler.
- **Prod done:** jobs completed in the ~32-hour window.
- **Model:** handlers that reach a model or vision provider.
- **Laura may delegate:** the charter's `generatable` list.

| Owner's department | Charter / agents (authority, CA$/day) | Handled / declared | Woken by | Model | Prod done | Laura may delegate | Verdict, and what is missing |
|---|---|---|---|---|---|---|---|
| Executive (Laura) | executive: laura (G, 0.50), coo (G, 0), orchestrator (G, 3.00), swarm_steward (G, 0.25) | 50/50 | 48 cadences; laura every 5 min, COO every 15 min | laura briefing (gateway, CA$0.50 cap) | coo 558, laura 393, orchestrator 635, swarm 102 | morning_handoff, scale.trajectory, department_review | **Operational.** Delegation is real but GREEN-only. The last `autonomy.orchestrate` enqueued 0 missions and holds approvals (`store_commerce:publication_review`). |
| Product Development | product_design: creative_director (G, 28.00), crochet_engineer (G, 4.00) | 19/20 (`cir.revise` missing) | 16 cadences; `cir.draft` only from radar promotions | 10 creative.* types | creative 20; **crochet_engineer 0** | seasonal.sentinel, outcome_learning, department_review | **Partly.** Research runs; 4 cadences were last no-ops (blinded: 1 pair; reference_reading: image_vision closed; the model tournament and pack are already done). **No CIR drafted in the window**, and a failing CIR has **no revise path** (`cir.revise`). |
| Brand & Publishing | store_commerce: **storefront_director** (G, 0; W-AGENTS) + visual: publishing (PDF/assets) | storefront 3/3 (new) | daily `storefront_review` (new) | none (deterministic) | 0 (not deployed yet) | `storefront.review` | **Built in code (b5226f7), not in production.** Proposals only; writes are held in SHADOW. |
| Growth & Marketing | growth: growth (G, 2.00), ads (Y, 1.00), experiment_steward (G, 0.25) | 11/11 (`content.draft` added) | 7 cadences | none | 13 | journey, distribution, conclude, ads_readiness | **Observes and plans; executes nothing**, correctly: there is no owned channel (`owned_surfaces`), no ad authority and no data. 64/64 experiments are `no_data`. |
| Etsy Operations | store_commerce: listing (G, 2.00), store_operator (Y, 1.00), pricing (G, 1.00) | 14/15 (`pricing.experiment` missing: protected) | 6 cadences | listing.seo | 21 (seo.cycle 15) | remerchandising, seo.cycle, storefront.review | **Reads and proposes.** store.publish and store.activate are held by phase and grant (correct). `pricing.position` did not run in the window. |
| Visual Production | visual: publishing (G, 2.00) | 10/11 (`assets.render` missing) | 4 cadences | 7 | 12 | identity_drift, visual.rnd.cycle | **No useful output.** `assets.owned_photography` ran 10 times on `market-basket-trio`, which has **no CIR** (repeated no-op); model_photography is a no-op; visual.rnd generated 0. |
| Market Intelligence | intelligence: market_radar (G, 4.00) | 14/15 (`radar.competitor_snapshot` missing) | 13 cadences | 4 | 67 (+12 pending) | radar.score, benchmark_refresh, pod_learning | **Operational for reads.** mjs.scan found 80 new listings; intel.acceptance FAIL 12/13; one mjs.scan read timed out. |
| Finance | finance: cfo (G, 1.00) | 10/10 | 9 cadences | none | 74 | reconcile, order_readings, readings, escalation, accounting cycle and period pack | **Operational.** Real authenticated receipt reads (0 receipts); books from observed entries only. |
| Customer Experience | support: support (Y, 2.00) | 2/2 (`support.reply` protected) | hourly triage | none | 32 (0 cases) | support.triage | **Correctly idle**: there are no customers. |
| Engineering & Reliability | platform + learn: orchestrator, learn (G, 0) and 8 meta-agents (G, 0.25 each) | all handled | 41+ cadences | probes only | orchestrator 635, learn 32, meta 2 each | queue_check, maturity, slo, improve.* | **Operational.** `/api/verify` and `/api/departments` answer (the departments 500 of AGENT_AUDIT is gone in production). |
| Quality & Compliance | product_truth: quality_director (G, 1.00), validator (G, 1.00), asset_truth (G, 1.00), policy (G, 1.00) | in production **8/13**; `cir.twin`, `cir.reverse`, `gate.asset_truth`, `gate.policy` and `gate.quality` have no handler | 3 cadences | gate.certify | quality_director 6; **validator, asset_truth and policy 0: they could never run** | sentinel, upgrade_impact | **Registry-only for 3 of 4 agents** (AM-10). The checks run only inside `gate.certify`; nothing re-checks a release after certification. **Fixed in batch 1.** |

## Batches

### Batch 1 (done): Quality & Compliance agents are operational

`runtime/quality_ops.py` adds handlers for:
- `gate.quality` (quality_director, daily cadence `quality_reverify`): queues one check of each kind per newest certified release, idempotent per release per day;
- `cir.twin` and `cir.reverse` (validator): compile, the twin, and the written pattern reverse-compiled in US and UK terms;
- `gate.asset_truth` (asset_truth): shape and technique claims of the title and listing copy against the twin;
- `gate.policy` (policy): `check_listing` on the drafted listing.

**AM-10 is respected.** These checks are *not* a verdict path:
- they run only on releases that are already certified;
- they never certify, revoke or block anything;
- a disagreement becomes one deduplicated **P2, non-halting** incident (regression detection).

`gate.quality` is generatable by Product Truth (SAFE_GENERATED), so Laura and the COO can delegate the sweep. `test_roles.DECLARED_BUT_UNBUILT` loses these five types, and AM-10 status is updated.

**Authorised by:**
- the Master Plan §16 Engineering roles (Validator, Digital Twin, Reverse Compiler) and Brand/Publishing roles (Asset Truth);
- §17 (Adversarial QA, Asset Truth, Policy Gate);
- F-892 (charters: an agent is only real with authority it can use);
- F-701 (autonomy is core).

### Batch 2 (done): Visual Production stops asking to photograph slugs with no CIR

Production ran `assets.owned_photography` 10 times in 32 hours on `market-basket-trio` (E-12). That slug is a retired concept with no CIR (`products.launch0.LEGACY_DUPLICATES`), so every run was a no-op.

Two enqueuers passed such slugs without checking for a CIR, and both now skip them:
- the blind-review "return to development" path (`runtime/release.py`), which records `creative.return_skipped` with the reason;
- the MJs director's photography-coverage request (`intel/mission_runtime.company_standing`).

The cadence's own picker already skipped CIR-less slugs. Test: `test_w4_departments.test_photography_is_never_requested_for_a_slug_with_no_cir`.

### Batch 3 (done): Product Development revises a failed CIR once (`cir.revise`)

**Finding: `cir.draft` has no model path.** It drafts from engineered designs, `concept_to_cir` and `creative.prototype.author`, which are all deterministic, and Master Plan §2 forbids asking a model for instructions. So `cir.revise` is deterministic too: no model, no network, CA$0, inside the crochet_engineer CA$4.00 ceiling. No stub was needed.

How it works (`runtime/engineering_ops.py`):
- `cir.compile` used to end a failing concept with "the concept dies here". It now hands the failure to the crochet engineer **once** (`MAX_REVISIONS = 1`, keyed on the CIR fingerprint).
- The engineer applies only rules that change declared geometry parameters, never the design's idea. There is one rule today:
  - `REPEAT_DIVISIBILITY`, which answers the compiler's REPEAT / COUNT_MISMATCH / UNDERRUN / OVERRUN errors on a uniform flat panel;
  - the width becomes the nearest multiple of the repeat unit, with every row, declared count and the foundation moving together;
  - the width change is recorded.
- A revision that compiles goes back through `cir.compile`, then `gate.certify`. Deterministic validation decides.
- Anything else is recorded as `cir.revise_unrepairable` with its finding codes, not guessed at.
- `cir.revise` leaves `DECLARED_BUT_UNBUILT`.

Tests: `test_w4_departments.test_a_failed_compile_is_revised_once_and_goes_back_through_the_compiler` and `test_an_unrepairable_failure_is_recorded_not_guessed`.

### Batch 4 (done): Market Intelligence takes a competitor snapshot (`radar.competitor_snapshot`)

`runtime/intel_ops.py` runs a daily cadence, `competitor_snapshot` (market_radar). It aggregates the competitor listings already observed through sanctioned sources (`benchmark_listings`) per benchmark and pod:
- listing count and new listings in the last 7 days;
- price band (min / median / max CA$), with UNKNOWN when no price was observed, never 0;
- share on sale and median gallery size;
- seasonal mix and product types;
- the change since the previous snapshot.

**No competitor content is stored**: no title, description, URL, image, chart or instruction. The payload keys are restricted to `ALLOWED_KEYS` and checked before storing. It makes no network or model call and costs CA$0. With nothing observed it reports `ran: false`. `radar.competitor_snapshot` leaves `DECLARED_BUT_UNBUILT`.

Test: `test_w4_departments.test_competitor_snapshot_is_aggregates_only_and_never_copies_content`.

### Remaining

- **Still unbuilt, by authority** (the only entries left in `DECLARED_BUT_UNBUILT`):
  - `pricing.experiment` (PUBLISH, protected; owner authority required);
  - `assets.render` (no requirement row names a separate render job; `assets.build` covers it).

## Product-engine batch (2026-10-26)

### Requirement trace

**No row is named "Product Family Engine".** The name appears nowhere in the spec PDFs, the registries or any branch. The rows that define the capability are:

| Row | Criterion (abridged) | Board | What existed |
|---|---|---|---|
| MP v1.2 §5 | "Winner Amplification turns proven demand into matching products, bundles, sizes, colourways…" | (spec) | Pin-level amplification only (`growth/pins.amplify`); nothing at product or family level |
| MP v1.2 §33 | Launch portfolio needs "at least one bundle-ready family" | (spec) | `radar.opportunity._family_counts` at concept selection only |
| B2 #111 | Multi-Product Family Test before engineering; prefer families without forced derivatives | covered (proof: none) | `creative/family.family_test`, consumed by `creative/prospecting.proposition` (pre-engineering) |
| F-359 | Sibling/family variants where value exists; prevent low-value duplication | POST-LAUNCH / INTEGRATED (`creative/family.py`) | concept-level only; **no check on the certified catalogue** |
| F-791 | "Merely changing colour … is not sufficient" | COMPLETE | applies to competitor-inspired designs only |
| F-354 | Multi-size value | POST-LAUNCH / INTEGRATED (`cir/graded.py`) | exists |

**Missing:** nothing answered the family questions once products are certified:
- which families the catalogue actually has;
- whether one is bundle-ready (§33);
- which members are only recolours of a sibling (F-359 / F-791 duplication);
- what the next member is;
- whether proven demand justifies amplification (§5).

### Built

`creative/family_engine.family_report(db)` plus the `creative.family_engine` job (creative_director, RESEARCH class, daily cadence `family_engine`, generatable by Product & Design). It is deterministic, reads only our own rows, costs CA$0, and creates no product. For each family it reports:
- **Membership:** certified members, grouped by the radar pool's declared family; anything without one is listed as a single product.
- **Distinct designs:** counted by a colour-free structure fingerprint.
- **`bundle_ready`:** two or more distinct certified designs. A bundle is derived, never asserted (#111).
- **`recolour_duplicates`:** members with the same structure in different colours.
- **`next_members`:** uncertified pool seeds of the same family, which must still pass the ordinary funnel.
- **`amplification`:** **UNMEASURED** below 5 family orders. That threshold is this module's own floor, documented in code; no row gives a number.

Test: `test_w4_departments.test_family_engine_groups_certified_families_and_flags_recolours`.

### F-789 (private R&D teardown): conflict reported, not built

- **Criterion:** "Agents may ingest the complete purchased pattern, reconstruct its functional garment architecture, stitch logic, grading, dimensions, workflow, customer experience, merchandising system and weaknesses inside the private benchmark environment." Board: POST-LAUNCH / INTEGRATED, producer `teardown/reader.py`.
- **Already implemented,** with the stricter reconciliation:
  - `teardown/reader.py` holds the purchased text only in memory and emits only closed-vocabulary tokens and numbers ("there is no code path that emits a substring of the document");
  - `teardown/size_family.py` parses the graded size family the same way;
  - F-786 to F-792 gate any publishable output (licence terms, Meaningful Redesign, Independent Instruction Draft).
- **Conflict.** The row's scope, "reconstruct … stitch logic, grading … to design a better product" (with F-790), goes beyond CLAUDE.md's non-negotiable that "competitor research is for demand and merchandising intelligence only". It also depends on *purchased* benchmarks, which are an owner spend card.
- **Decision.** I did not widen the reconstruction. The existing reader already limits it to our own closed vocabulary and numbers. Any extension (for example, reconstructed grading feeding design) needs an owner ruling reconciling F-789/F-790 with CLAUDE.md.

## Visual batch (2026-10-26)

**VISNEXT2 merged** (`origin/claude/w4-VISNEXT2` 5d16506, commit 13bd73e3).
- Its only conflict was the generated autonomy map, which was regenerated.
- One interaction fix: `test_w4_close5_rows` SCRATCH now classifies VISNEXT2's new scratch site, `experiments/controlled.py::verify_pipeline` (caller `verify`). Its re-rendered references are only compared with the frozen definition's fingerprints.
- `test_w4_visnext2` passes.

| Row | Criterion | Before | Done |
|---|---|---|---|
| F-126 | Keep invalid/confounded experiments marked superseded with reason | POST-LAUNCH, no producer. The provider image benchmark kept re-running daily and reporting a "winner" (nano-banana-2) after the owner's FLUX 3 ruling | `gateway/image_bench.SUPERSEDED` (by D-W4-LAURA-FLUX3, 2026-10-19, with the reason) and `superseded_record`: one idempotent audit row listing every retained benchmark row. Nothing is deleted. `creative.image_benchmark` now records the supersession and renders and spends nothing; no job input can lift it. `state()` exposes `supersession`. |
| F-217 | Identity subscores exposed: face, whole-person morphology and overall reported separately; a high face score cannot hide a morphology failure | POST-LAUNCH / DEPLOYED (`publish/model_photography.py`) | **Already met.** `face_identity` and `whole_person_morphology` are separate FLOORS, each of which must pass on its own; there is no average. No change. |
| F-218 | Repeated near-threshold morphology drift raises an incident even if individual images narrowly pass | POST-LAUNCH / INTEGRATED (`visual/drift_series.py`), but it counted only `drift` verdicts, so narrow passes were invisible | `drift_series` now counts **near-threshold passes**: a morphology group that passed with only the minimum readable dimensions, or a biometric BORDERLINE band. Three or more across two or more batches open one P2 incident that halts publication (`identity_drift_series:near_threshold_morphology`). It resolves only on a measured window without repeats. |
| FLUX rows | spec/12 §11 required tests (the three canonical references, refusal on a missing one, product references from the exact version, every reference reaching the provider, body proportions, one outfit per listing, no outfit reuse, automatic styling, product-only needing no Laura, Product Truth not bypassable, approvals before publication) | **No F-row names FLUX.** All eleven required tests already exist in `test_w4_flux3generator`, `test_w4_fluxapi`, `test_w4_fluxstages`, `test_w4_visnext` and `test_w4_visnext2`, all with stubs | No new code. Body proportions stay UNKNOWN until two independent judges read them (the integrator note). No paid call was made. |

Tests: `test_w4_departments` (11 tests, all pass), plus test_image_bench, test_w4_close5_rows, test_fb2_i_repairs, test_cert_intel_wave2, test_w4_visnext2, test_v11_autonomy_timeline and test_roles.

## F-515 Shop Completeness Gate (2026-10-26)

**Criterion (v0.16):** "Before first publication and continuously thereafter, verify shop icon/logo, banner or chosen intentional absence, About/story, policies, branding consistency, support expectations and required seller information. Missing trust surfaces cannot silently pass launch readiness."

**Board:** GATED / DEPLOYED / LAUNCH-CRITICAL, gate `etsy_shop` (owner): "daily etsy.shop_snapshot judges getShop; needs a usable shop credential on the deployed build". The v0.15 row (Launch Non-Delay Rule) is POST-LAUNCH.

**Finding: met in code; the board's gate reading is stale.**
- **Continuously:** `etsy.shop_snapshot` runs daily and judges getShop with `intel.etsy_surfaces.assess_shop`.
  - `launch/readiness`'s `etsy_first_sale_surfaces` item is not ready while any shop check fails or any first-sale surface lacks fresh evidence.
  - Surfaces with no API (About/story, seller information, the banner's intentional state) take their evidence from the owner's dated observations (`launch.first_sale_surfaces`), which are never assumed done.
  - The intended package and the owner's banner are checked by the `storefront` item (`check_storefront` + `storefront_gate`).
  - Tests: `test_etsy_readback_observe::test_missing_trust_surfaces_cannot_pass_silently` and `test_etsy_surfaces::test_an_empty_shop_body_is_no_evidence_on_every_check_and_never_green`.
- **Production** (`/api/launch`, read 2026-10-26): `etsy_shop` is **ready: true** ("shop identifier AND a recorded sanctioned read"), and `storefront` is ready: false, held by the banner's publication gates (the owner's rulings, D-FB-17). So the owner gate the board names has been cleared in production. The board still says GATED because its generator evaluates gates in the build environment, where no shop credential exists.
- **The Storefront Director (b5226f7)** now evaluates the same surfaces continuously and drafts the API-writable ones, so a gap is acted on, not only reported.
- **No code change, and the row is not re-classified by hand** (worker rule). Closing the row needs the board generator to read production gate evidence, or an integrator re-run against the deployed build.

## Remaining department gaps

| Gap | Status |
|---|---|
| `pricing.experiment` | PUBLISH, protected; needs owner authority. Unbuilt by authority. |
| `assets.render` | no requirement row names it; `assets.build` covers rendering. Unbuilt by authority. |
| Product Development: crochet_engineer ran 0 `cir.draft` in the window | radar.score ran 22 times and promoted nothing. Diagnosing why needs job outputs, which are not on the public read surface (`/api/jobs` lists no outputs; per-job reads are 404 without operator credentials). The next diagnostic step needs operator-authenticated read access. |
| Visual Production: no useful output | waits on the paid image path (`image_generation` / owner spend authority) and on certified products needing renders. |
| Growth: 64/64 experiments `no_data` | correct until listings are live (SHADOW). |
| Pricing agent: 0 jobs | **not a defect.** `pricing.position` is woken by the release chain after `assets.build`; there was no new release in the window. |

## Cluster C1: baby and children's products (ledger rows, 2026-10-26)

New code: `creative/children.py`, plus the job `intel.children_portfolio` (market_radar, RESEARCH, daily cadence `children_portfolio`). It reads our own rows and observed listings as counts only; it stores no competitor text, makes no network call and costs CA$0.

| Row (ledger status) | Criterion | Built | Test (`tests/test_w4_children.py`) |
|---|---|---|---|
| F-351 (B) Priority Product Family | baby/children's is a high-priority family for research, launch planning, catalogue expansion and seasonal planning | `PRIORITY_FAMILY`, consumed by `portfolio(db)`: one daily reading of the family's coverage, style segments, launch mix, architecture and sibling sets | `test_f351_portfolio_job_runs_daily_and_records_one_reading` |
| F-353 (B) Core Category Coverage | research the row's categories, from newborn cardigans through unisex designs | `CORE_CATEGORIES` is the row's own list. `coverage(db)` gives observed listings and radar seeds per category, and each gap becomes a named research item | `test_f353_core_categories_are_the_rows_list_and_gaps_are_named` |
| F-358 (A) Gender-Neutral & Style Segments | research gender-neutral and style-specific demand; never infer a palette or aesthetic | `style_segments(db)`: gender-neutral, gendered and style-term counts over observed children's listings. The palette is explicitly not inferred, and it reads UNMEASURED with no evidence | `test_f358_style_segments_count_without_inferring_a_palette` |
| F-359 (B) Sibling / Family Variants | sibling sets and coordinated products with genuine value; no low-value duplication | children's families from `creative.family_engine` (bundle-ready, recolour duplicates) carried in the portfolio's `sibling_sets` | family engine test + F-351 test |
| F-365 (B) Store Architecture | a Baby & Kids department when catalogue depth justifies it, navigated by product family and age range | `architecture(db)`: proposed only at 4 or more certified children's products (`BABY_KIDS_DEPTH`), with navigation by family and age range (Launch-0 `audience`; UNMEASURED where absent). The Storefront Director shows it as a `baby_kids_collection` advisory | `test_f365_baby_and_kids_collection_only_when_depth_justifies_it` |
| F-366 (B) Launch Mix Evaluation | the launch optimizer explicitly considers children's products alongside adult garments, home/decor, seasonal and accessories | `launch_mix(db)` scores Launch-0 and the candidate pool across the five segments; not ok when children's products are absent | `test_f366_launch_mix_considers_children_alongside_the_other_four_segments` |

**Honest limits:**
- F-365 is advisory only. "Baby & Kids" is not yet a section in the brand architecture (`copy_v2.SECTIONS`), so no `createShopSection` is drafted for it; adding it is a brand decision.
- F-366 evaluates the launch mix; it does not re-select the curated Launch-0 list.
- The depth threshold of 4 and the category patterns are this module's own constants; no row gives figures.

## Cluster C2: canonical-model evidence (ledger rows, 2026-10-26)

No provider is called; everything reads committed files and rows. Tests are in `tests/test_w4_c2_visual.py` (F-218's is in `test_w4_departments`).

| Row (ledger status) | Gap the matrix named | Built | Test |
|---|---|---|---|
| F-217 (B) Identity Subscores Exposed | `image_bench` scored a single `identity_match` | `image_bench.identity_subscores`. The benchmark's retained score is the **face** subscore only (its question was facial); **whole-person morphology = UNMEASURED** because it was never asked; **overall = min = UNMEASURED**, so a high face score cannot hide a morphology failure. It is on every per-model row of `decide`/`_measured_state`. The benchmark itself is superseded (F-126); production frames keep the real six-floor split. The `identity_match` key is kept (`test_image_bench` pins it). | `test_f217_benchmark_reports_face_morphology_and_overall_separately` |
| F-218 (B) Canonical Model Drift Sentinel | ternary verdicts, so narrow passes were invisible | built in the visual batch (4766be8a): an incident on repeated near-threshold passes | `test_w4_departments.test_f218_*` |
| F-744 (B) Model Evidence Ledger | experiments spread across audit rows; no single queryable ledger; `assets.model_photography` rows pruned after the retention window | `visual/model_ledger.py`. `harvest` normalises every experiment row (model photography, provider trials, benchmark trials and candidates, reference packs, portrait repairs) into one durable record, `operating_readings` `visual.model_experiment`, which retention does not prune. Each record carries canonical version, provider/model/mode, references, prompt, settings, output hash, identity (face and morphology), Product Truth, realism, cost, accepted and reason; anything never recorded is UNKNOWN. `failed_approaches` groups rejections. Daily job `visual.model_ledger` (publishing, OBSERVE) | `test_f744_every_experiment_is_kept_as_a_durable_normalised_record` (the failed approach survives deletion of its source rows) |
| F-738 (B) Identity-Preserving Promotion | no evidence comparator | `visual/model_promotion.py`. `summarise` reads the F-744 records per canonical version. `compare` returns PROMOTE only when identity retention is at least the incumbent's AND realism is strictly better; a realism win with identity loss is REFUSE; fewer than 5 judged frames is UNKNOWN. PROMOTE is an owner-decision recommendation only. `regression` is the rollback trigger. | `test_f738_a_realism_win_with_identity_loss_is_refused_and_unknown_never_promotes` |
| F-747 (B) Brand Asset Portability | the body frames existed only in production storage | **That gap is closed by the committed originals** (FLUX3 ruling: the three canonical files are committed and byte-identical, a42aeac7, afe6191f, f32bac68). `visual/portability.bundle` is the provider-neutral migration bundle (identity id, decisions, locked specification, committed hash-verified frames, with a check that no vendor is named in the specification). `restore_check` copies the frames out and re-verifies every hash. | `test_f747_identity_is_portable_without_any_provider` |

**Not wired (frozen Laura identity code):**
- `model_promotion.compare` is not yet a precondition inside `visual.model_registry.replace_canonical`. That function has no runtime caller, and the canonical identity code is frozen with Laura.
- Making a PROMOTE verdict required there is a one-line integration once the freeze lifts.

**Regression:** test_image_bench, test_roles, test_v11_autonomy_timeline, test_vacuity, test_w3_k11_authority, test_w4_close5_rows and test_w4_departments pass.

## Cluster C3: storefront and product commerce (ledger rows, 2026-10-26)

All deterministic, our own rows, CA$0. Tests are in `tests/test_w4_c3.py`.

| Row (ledger status) | Gap | Built | Test |
|---|---|---|---|
| F-527 (B) Brand Asset Health | no detection of stale, missing, low-resolution or off-brand assets on the live shop | `store_foundation/asset_health.check`, run in the Storefront Director's daily `storefront.review` (reading `storefront.asset_health`). It detects:<br>• shop icon missing, unread or stale, routed to `storefront_director` (owner step; no API);<br>• certified product with no approved hero;<br>• images only for older versions (stale);<br>• gate-blocked (off-brand or untrue) images;<br>• images under Etsy's 2000 px recommendation, where a size is recorded.<br>The last four route to `publishing`. A blank banner field is UNKNOWN, never "missing" (LISTREADY E7). Live colour and typography are UNMEASURED: no API returns them. | `test_f527_missing_stale_blocked_and_low_resolution_assets_are_routed` |
| F-775 (B) Cross-Sell Graph | pairs and bundles existed; tutorials and materials were not in the graph | `commerce/cross_sell.graph`, daily job `listing.cross_sell_graph` (listing). Per certified product: related family siblings, the family's bundles, its collection (`brand.storefront.section_for`), **approved** learn lessons for its own techniques (`learn.service.listing_help_links`), the CIR's materials, and next projects (same collection, planned family members). Edges point only at certified products; attach rate is UNMEASURED until orders exist. | `test_f775_cross_sell_links_only_certified_products_with_tutorials_and_materials` |
| F-113 (A) Commercial Salvage Test | missing | `creative/salvage.review`, weekly job `creative.salvage_review` (creative_director). For each legacy certified product (outside `launch0.launch_scope_slugs`) it re-runs today's gates:<br>• creative: the current MJs blind review;<br>• MJs-market: whether today's radar portfolio still selects it;<br>• seasonal: the #297 window;<br>• novelty: originality provenance;<br>• portfolio: cannibalising listing pairs.<br>The result is `retire_recommended`, `rescue_candidate` or `review`. **It only recommends:** it never deletes, unlists, deactivates or edits a product or listing. An unreadable gate is UNKNOWN. | `test_f113_salvage_only_recommends_and_never_writes` (row counts and the listing state unchanged after the job) |

**Regression:** test_w4_agents, test_roles, test_v11_autonomy_timeline, test_vacuity, test_w3_k11_authority and test_w4_listready pass. The autonomy map was regenerated.

## Build 2 #94: Creativity Capability Scorecard (2026-10-26)

**Criterion:** "Track creative capability over time using blinded human/agent benchmark comparisons, concept diversity, novelty distance, desirability scores, percentage of concepts surviving the tournament, market CTR/conversion, winner rate and repeated-theme fatigue. The objective is demonstrable improvement in idea quality, not simply more generated ideas." Status: data_gated.

**Before.** `tournament.scorecard`, `theme_fatigue`, `novelty` and `creative.blinded` each measured one thing, at one moment, over one set. Nothing combined them over time, and nothing computed CTR, conversion or winner rate per concept.

**Built** (`creative/capability_scorecard.py`; daily job `creative.capability_scorecard`, creative_director, RESEARCH, reading `creative.capability_scorecard`). `scorecard(db)` reports, per UTC month and as a trend:

| Measure | Source |
|---|---|
| tournament survival share | `creative.tournament` rows |
| blinded human/agent comparison and desirability | `creative.blinded` rows; win rate counted only from **valid** runs (enough pairs, no position bias) |
| novelty distance | each month's new products against every earlier product (`concept.nearest`), mean and minimum |
| concept diversity | distinct pods |
| repeated-theme fatigue | `theme_fatigue` over the cumulative catalogue |
| market CTR and conversion per concept, combined over all periods | `listing_outcomes` |
| winner rate | the share with a sale, among concepts with at least 200 impressions |

`objective` compares the quality trends (novelty, desirability, survival, fatigue) with idea volume. More ideas with flat quality reads as "more ideas, not better ideas".

**Anything without evidence is UNMEASURED, never 0.** Only the real market evidence (live traffic and sales) remains pending, and `pending_market_evidence` says so. The 200-impression floor and the "at least one sale" winner definition are this module's own, documented constants.

**Tests** (`tests/test_w4_capability_scorecard.py`):
- `test_an_empty_company_is_unmeasured_everywhere_never_zero`;
- `test_every_named_measure_is_combined_per_month_and_trended` (an invalid blinded run never becomes a 0; CTR, conversion and winner computed only above the impression floor);
- `test_the_scorecard_job_runs_daily_and_stores_one_reading`.

test_roles, test_v11_autonomy_timeline and test_vacuity pass. The autonomy map was regenerated.

## Workstream C batch W1: Shared Truth Contracts and the Contract Change Barrier (F-456, F-482; 2026-10-26)

**Rows.**
- F-456: cross-department contracts are versioned and authoritative.
- F-482: a contract change is declared before merge, and dependants pin or migrate; silent drift is prohibited.

**Built.**
- **Registry.** `core/contracts.py` declares five shared contracts:
  - `cir` (the CIR dataclasses);
  - `etsy_write_schemas` (the draft payload, `UPDATE_WRITABLE`, `SHOP_UPDATE_SCHEMA` and the section-title cap);
  - `shop_policy_sections`;
  - `storefront_proposal` (the Director's proposal record and agent-writable fields);
  - `live_shop_evidence` (live-shop field keys and drift statuses).
- **Version and fingerprint.** Each contract has a version and a deterministic SHA-256 fingerprint of its shape, and `contracts.json` pins both.
- **What `check()` reports:**
  - a shape change without a version bump (silent drift);
  - a version without a CHANGELOG entry (an undeclared change);
  - a bump whose pins were not regenerated;
  - an unpinned contract, or a pin for a contract that is no longer declared.
- **Consumer pins.** These consumers call `_contracts.require(name, version)` at import, so a contract that moves on fails them loudly until they migrate:
  - `runtime/storefront_ops` pins `storefront_proposal` and `etsy_write_schemas`;
  - `store_foundation/director` pins `live_shop_evidence` and `etsy_write_schemas`;
  - `runtime/quality_ops` and `runtime/engineering_ops` pin `cir`;
  - `brand/storefront` and `commerce/policy_consistency` pin `shop_policy_sections`.
- **Declaring a change.** Bump the version, add a CHANGELOG line, migrate or re-pin the dependants, then run `python -m brambleloop.core.contracts --write`.

**Tests** (`tests/test_w4_contracts.py`, 8/8):
- the contracts hold at HEAD;
- silent drift is caught;
- an undeclared or unregenerated bump is caught;
- removed and unpinned contracts are reported;
- `require` refuses a stale pin;
- every contract has at least one consumer pin at the current version (AST scan);
- the pinned consumers import cleanly.

**Not claimed.**
- Product IDs, evidence formats beyond the live-shop evidence, external APIs and quality floors are not yet registered contracts. Each is added by declaring its shape function here.
- The registry catches drift at test and import time. It is not a merge hook in CI, because no CI exists for this repository.

## Workstream C batch W2: the listing-test memory has a runtime caller (F-505; F-476 assessed; 2026-10-26)

**F-505.** The row's missing part: "the listing-test disproof memory (`commerce/listing_tests.write`/`may_test`) has no runtime caller".

**Built.**
- **Writing the memory.** `growth.experiments.conclude_all` now passes each concluded listing experiment to `listing_tests.remember_conclusion`. It builds a `ListingTest` from:
  - the stored registration;
  - the measured window and exposure (the same discipline reading the conclusion used);
  - a pre-period baseline (`experiments.pre_period`: the same metric over the periods recorded before registration, UNMEASURED when there are none);
  - the variables the experiment changes (`EXPERIMENT_VARIABLES`: thumbnail, price, search = title+tags, bundle).

  It writes through `listing_tests.write`, so every existing rule applies:
  - nothing is written without exposure, a pre-period and a full window;
  - a confounded result (#241) writes nothing;
  - a disproof needs a causal design;
  - a multi-variable change is remembered as a bundle;
  - a re-run is idempotent.

  The conclusion result now carries `memory`.
- **Checking it before registering.** `growth.experiments.persist` asks `listing_tests.registration_refusal` (`may_test`) before registering. An idea the memory holds as disproved in the same context is stored as killed, with the disproof as its reason, and reopens only in a changed context.
- **Context.** `listing_tests.context_for` takes the context from stored records only:
  - pod and season from the concept seed;
  - price band from the drafted listing's price;
  - shop maturity from booked orders and the first listing's age, the same derivation as `growth_ops.benchmark_observations`.

  Any part it cannot measure makes the context UNKNOWN. An UNKNOWN context writes nothing and refuses nothing.

**Tests** (`tests/test_w4_listing_memory.py`, 5/5):
- a concluded disproof is written once;
- a disproved idea is refused in the same context and allowed in another price band;
- an UNKNOWN context writes and refuses nothing;
- a test with no baseline is never remembered;
- only listing variables touch the memory.

Existing tests still pass: `test_listing_tests`, `test_experiment_persistence`, `test_k3_listing_outcomes`, `test_w4_ccgrow`, `test_w4_controlled_experiments`, `test_reachability` and `test_vacuity`.

**F-476: assessed, not built here.** Its missing part is "build-side duplicate-lane prevention is manual". That concerns how coordinators assign build lanes, not a runtime department. Runtime dedupe (idempotency keys, fingerprint-skipped scans, exclusive build-task claims) is already in place. Building it would mean inventing coordination tooling outside the brambleloop runtime, which the directive excludes, so the row stays PARTIAL for the coordinator's lane.

## Workstream C batch W3: the Research Agent (F-401, F-429, F-436, with F-402/F-430/F-435/F-437; 2026-10-26)

**Rows.**
- F-401: no dedicated research capability that agents can invoke or that triggers itself.
- F-429: no path for evidence to flag architecture for review.
- F-436: no research-method selection.

**Built.**
- **The agent.** `research_agent` is a new agent in the Intelligence charter (CA$0, GREEN). It holds `research.investigate`, `research.sweep` and `research.flag_architecture`, all classed RESEARCH. `intel/research_agent.py` holds the method; `runtime/intel_ops.py` holds the handlers. It works the existing research-task store (`intel.research`); no new table.
- **Invoked and self-triggered (F-401).**
  - Any agent invokes it with `request_research(ctx, …)`, which queues `research.investigate` for `research_agent`.
  - Its own daily `research.sweep` (cadence, and generatable by the COO and Laura through the Intelligence charter) runs `detect_unknowns` and `expire_due`, then queues an investigation for each open task not investigated in 7 days.
- **Method choice (F-436, F-402, F-437).**
  - An eight-method ladder, cheapest first: internal retrieval, repository inspection, official docs, marketplace observation, web search, academic literature, controlled browser, bounded experiment.
  - It records which methods are adequate per learning domain, and which are available to this agent now: only internal retrieval and the repository's research record.
  - It picks the lowest-cost method that is both adequate and available. Internal evidence is always searched first.
  - Marketplace policy and media capability are adequate only through official docs or an experiment (F-437), so those tasks report BLOCKED_ON_METHOD with what would unblock them, rather than an answer from notes.
- **Machine-usable conclusions (F-435).** Each run returns and audits (`research.investigated`):
  - question, status (EVIDENCE_GATHERED / UNRESOLVED / BLOCKED_ON_METHOD) and confidence;
  - evidence refs and the method choice with its alternatives;
  - constraints and applicability;
  - unresolved issues and the recommended bounded next test.

  It never writes a `fact` on its own. A question with no held evidence is recorded `unresolved` with the next test and answered, so it reopens on its domain's freshness.
- **Architecture flags (F-429, F-430).** `research.flag_architecture` (requested with `request_architecture_review`) records an `inference` finding plus a `research.architecture_flag` audit row.
  - It needs evidence the task holds that was read in full or measured internally.
  - It refuses any assumption naming a hard floor: certification, Shadow Mode, spend or budget, owner approval, KYC, legal acceptance, fake reviews, CAPTCHA.
  - The weekly evolution review (`improve.weekly`) now reports `research_architecture_flags`. A flag changes nothing.
- **Autonomy map** regenerated: +1 agent, +1 cadence, +3 handlers, `never_woken_job_types` empty.

**Tests** (`tests/test_w4_research_agent.py`, 8/8):
- the agent is declared, chartered, classed and scheduled;
- method selection, including the F-437 block;
- invocation by another agent, with internal evidence first and no network (socket refused);
- an unresolved question records the next test and reopens on freshness;
- policy questions are blocked on official docs;
- the sweep self-triggers once per task;
- architecture flags need graded evidence and refuse hard floors;
- the weekly review reads the flags.

**Not built (provider or owner).** Official-docs fetch, web search, literature access and controlled-browser research. Each is named in the ladder with what would make it available. Connecting any of them is a provider or owner decision.

**Found while regressing W3:** `test_r2_autonomy_useful_work.test_every_cadence_and_generatable_type_declares_its_work_keys` was failing for 10 W4-AGENTS types: the nine from earlier batches (`storefront.review`, `gate.quality`, `radar.competitor_snapshot`, `creative.family_engine`, `creative.salvage_review`, `listing.cross_sell_graph`, `creative.capability_scorecard`, `intel.children_portfolio`, `visual.model_ledger`) plus `research.sweep`. Those batches had not run this test. Each of these handlers already reports a measured `work_done` (checked handler by handler). They are now declared in `pipeline.WORK_KEYS` as `("work_done",)`, and the test passes.

## Note on lane overlap with W4-FMBATCH1 (F-476, F-482; 2026-10-26)

FMBATCH1 owns the F-45x to F-49x swarm and build-side rows. From now on W-AGENTS leaves them to that lane.

**How the two contract mechanisms relate.** Nothing is removed here; the integrator reconciles them at merge.
- **FMBATCH1 (F-482):** `core/contracts.py` with `fingerprint()` / `fingerprints()`, plus `tests/test_w4_fmbatch1_contracts.py` and `ops/CONTRACT_CHANGES.md`. It pins schema and interface shapes: the CIR dataclasses, `ListingPayload` and every API route. A pin cannot be bumped without a dated declaration.
- **W-AGENTS W1 (this lane):** its own `core/contracts.py`, plus `contracts.json`, `CHANGELOG` and `require(name, version)`. It covers runtime module contracts: versioned shapes for the CIR, the Etsy write schemas, shop policy sections, the storefront proposal and live-shop evidence. Consumer modules pin them at import with `require()`.
- **Path collision: resolved.** FMBATCH1 renamed its module to `core/contract_pins.py` (9347050d). W1's `core/contracts.py` keeps its path, so the two no longer collide. They remain complementary: FMBATCH1 pins schema and route shapes behind a declaration; W1 pins runtime module contracts with `require()` at import.

**Correction to the W2 section.** F-476's build-side duplicate-lane refusal is built by FMBATCH1 (`ops/registry.py`). W-AGENTS did not build it, and the row belongs to that lane.

## Workstream C batch W4: research evidence and triggers (F-405, F-432, F-404; 2026-10-26)

**Built (extends the Research Agent).**
- **F-405, internal evidence first.** `research_agent.search_all_internal` searches every internal store before any external method:
  - lessons and learning observations;
  - incidents;
  - pre-registered experiments;
  - the listing-test memory;
  - the failure memory;
  - earlier answered research.

  BUILD_STATE.md and DECISION_LOG.md are read first among repository records when they are present. They are not copied into the production image, so there repository inspection reports itself unavailable rather than returning empty. Every hit becomes an `internal` ref the task's findings may rest on.
- **F-432, research memory.** Before investigating, `prior_answer` looks for the same question (normalised) in the same domain that is already answered and still within its freshness. If one exists, the task is STOPPED as a duplicate, citing the prior task, and no work is repeated.
- **F-404, confidence trigger.** `stale_domains_to_research` is called by `research.sweep`. A learning domain whose observations have all gone stale becomes one research question per stale episode:
  - not re-opened while one is open;
  - not re-opened while an answer is unexpired;
  - the answer's own freshness re-opens it.

**Tests** (`tests/test_w4_research_agent.py`, now 11/11):
- `test_f405_every_internal_store_is_searched_before_any_external_method`
- `test_f432_a_question_already_answered_and_fresh_is_not_researched_again`
- `test_f404_a_stale_domain_becomes_one_research_question_per_episode`

**Not built.**
- F-404's "conflicting evidence" half: no deterministic contradiction detector exists, and a keyword guess would be theatre.
- F-402's "before designing novel machinery" hook: nothing at runtime designs machinery autonomously, so there is no consumer to gate.

**Pre-existing behaviour noted, not changed.** `intel.research.detect_unknowns` re-opens an unobserved-domain question the day after it is answered. It is W4-RESEARCH's code; the F-432 duplicate stop now ends each re-open at once.

## Workstream C batch W5: research discipline and reporting (F-420, F-444, F-449), plus a retention fix (2026-10-26)

**Built.**
- **F-420, no research theatre.** Each investigation records whether it changed anything (`changed`, `unchanged_runs`). An open task that two investigations in a row leave with exactly the same evidence is stopped on the third (`STOPPED_NO_CHANGE`), with the justification and its next bounded test. It is not re-read weekly for show.
- **F-444, research failure escalation.** `research_agent.escalations` lists every question research could not resolve, with:
  - what was searched (terms, internal hits, sources, methods);
  - what is still unknown;
  - why it matters (the decision it serves);
  - the smallest action that could resolve it (the missing adequate method and what it needs).

  `research.sweep` stores it daily as the `research.escalations` reading.
- **F-449, research quality metrics.** `research_agent.metrics` is stored daily as `research.metrics`. It counts:
  - questions resolved with a fact, and those recorded unresolved;
  - duplicates avoided and tasks stopped for no change;
  - stale questions refreshed;
  - reuse rate and source quality.

  Experiments prevented, spend avoided and decisions materially improved are **UNMEASURED**: no row yet links a research answer to a decision outcome, so none is counted as 0.

**Retention defect found and fixed (my lane's code).** `ops.retention.unknown_read_actions` finds the audit actions code reads only when they are written as string literals. Actions read through constants are invisible to it. Two consequences:
- The storefront grant chain (`owner.storefront.approved/revoked/rebased`, a sealed chain like the publication one) was unprotected. Pruning one old row would have made every storefront grant refuse (fail closed) and raised a tamper incident.
- F-126's claim that superseded image-benchmark evidence is retained was not true past 90 days.

These are now in `KNOWN_READ_ACTIONS`:
- the three storefront chain actions, `image.benchmark_trial` / `_candidate` and `research.investigated`, as `lifetime_total` (protected);
- `quality.reverified` and `research.architecture_flag` as `windowed`;
- `image.benchmark_superseded` as `latest`.

**Cross-lane finding, not fixed here.** A scan that resolves module constants finds **51** audit actions read by name through a constant that are not in `KNOWN_READ_ACTIONS`. The eight W4-AGENTS ones are classified above; the other 43 belong to other lanes. Examples: `etsy.shop_observation`, `store.live_observation`, `store.owner_confirmed`, `commerce.orders_ingested`, `routing.evidence`, `spend.provider_settlement`, `visual.hero_review`. Each needs its owning lane to decide how it is read, and the guard should resolve constants so the next one is caught.

**Tests** (`tests/test_w4_research_agent.py`, now 14/14):
- `test_f420_investigations_that_add_nothing_are_stopped_with_a_justification`
- `test_f444_and_f449_the_sweep_stores_escalations_and_metrics`
- `test_retention_protects_the_storefront_grant_chain_and_classifies_research_reads`

The retention-list tests (`test_cost_governance_wave2`, `test_etsy_oauth_callback`, `test_model_spend_paths`, `test_w4_close5_grid_spend`, `test_w4_firstsale_retention`) and `test_vacuity` pass.

**Not built.** F-412 (research-to-experiment bridge): the agent never writes a hypothesis on its own, so a bridge would have no producer. It becomes meaningful once an adequate external method (owner or provider) can produce hypotheses.

## Workstream C batch W6: the live shop's text at phone width (F-239; F-040 assessed; 2026-10-26)

**Where the rows stand at HEAD.**
- F-040's next action ("wire `etsy_surfaces.assess_shop` into readiness via getShop") was done by other lanes after the closure-matrix snapshot: `etsy_ops` judges the daily getShop reading, and `launch.readiness.etsy_first_sale_surfaces` requires its checks. Nothing to add here.
- F-239's pre-launch preview (`brand.storefront_preview`, F-293) measures the **drafts**: a simulated icon and banner, the draft announcement, and the sections the opening grid populates. The text Etsy actually holds was never measured at phone width.

**Built.**
- **`storefront_preview.live_text(db)`.** It reads the newest stored getShop and shop_sync readings. It applies the same phone rules to the live announcement (the opening sentence must fit the phone opening, cut between words) and to the live section titles (one phone-menu line).
  - A missing or stale reading is UNKNOWN (`ok: None`), never a pass.
  - It is reported beside the simulation as `preview()["live_text"]` and is deliberately not folded into the pre-launch verdict.
- **Storefront Director.** The review gains an ADVISORY row, `mobile_live_text`, with status OK, LIVE_FAILS_MOBILE or UNKNOWN. The owner's live text stands. No proposal is drafted from this row, and nothing is replaced.

**Tests** (`tests/test_w4_mobile_live_text.py`, 5/5):
- no reading is UNKNOWN;
- fitting text passes;
- a cut opening sentence and an over-long section title are advisory findings;
- a stale reading is not evidence;
- the preview reports live text beside the simulation.

Regression: `test_w4_agents`, `test_w4_c3`, `test_w4_children`, `test_storefront_fb4`, `test_w4_b2close`, `test_w4_cap1_gates_intact`, `test_launch` and `test_vacuity` pass.

**Owner or provider dependent (not built).**
- Live icon and banner legibility: needs the artwork bytes. Fetching Etsy's CDN image is an Etsy call this lane does not make. The owner can supply the files to `preview(icon=…, banner=…)`.
- The live storefront as Etsy renders it: browser worker, gate `rendered_pages`.

## Reconciliation with FMBATCH1's research rules (2026-10-26)

**What happened.** FMBATCH1 built the research rules first, in `intel/research.py`:
- batch R (024897cc): F-405, F-408, F-411, F-419, F-420, F-426, F-432, F-435, F-444, F-449;
- F-412 (13a32db7);
- the F-431 fetch-and-promotion run, `intel/research_fetch.py` (2716d560).

W-AGENTS W4 and W5 then re-implemented F-405, F-432, F-420, F-444 and F-449 inside the Research Agent (`intel/research_agent.py`), without checking FMBATCH1's log. Nothing is deleted here. This note is for the integrator. From now on W-AGENTS checks `origin/claude/w4-FMBATCH1` before every row.

**Principle.** The **rules** belong in `intel/research.py` (FMBATCH1): the task record, what opening and answering require, reuse, stop and escalation, metrics. The **agent** belongs in `intel/research_agent.py` (W-AGENTS): who runs research, when it runs, with which method, and the architecture flags. The agent should call the rules, not restate them.

**Per row: which implementation survives, and what the other adds.**

- **F-405, internal evidence first.** Survives: FMBATCH1's `search_internal_report`.
  - Why: it covers more stores (section-9 experiments, benchmark titles, test names), records each store searched with its hit count or why it was unreadable, and is applied when a task opens.
  - What mine adds: the listing-test memory, and earlier answered research as an evidence ref. Both are small additions to their corpus list.
  - At merge: `research_agent.investigate` should call `R.search_internal_report` and drop `search_all_internal`.
- **F-432, research memory.** Survives: FMBATCH1.
  - Why: `question_key` (content words, domain, decision) is applied when a task opens. A reused answer is never re-opened, and the reuse is counted (`reuse_count`, `spend_avoided_cad`). It also has an explicit `reopen_because` path.
  - What mine adds: only a check at investigation time (`prior_answer`), which their open-time check makes redundant. Drop `prior_answer` and `STOPPED_DUPLICATE`.
- **F-420, no research theatre.** Survives: FMBATCH1's answer rule. An answer must name its effect (confidence changed, alternatives narrowed, constraint established, hypothesis produced, or stop justified), and every source must support a finding.
  - What mine adds, which should be kept but call theirs: an agent-side stop after `NO_CHANGE_LIMIT` investigations that add no evidence. Their rules judge an answer; they do not stop an agent that keeps re-reading. Keep `_unchanged_runs` and replace `_stop()` with `R.stop(...)`, so the stop carries their F-444 escalation.
- **F-444, research failure escalation.** Survives: FMBATCH1's `stop()` / `stop_overdue()` / `escalations()`.
  - Why: the smallest action is named when the task opens (`if_unresolved`), recorded on the stopped task, and the time bound is enforced.
  - What mine adds: the method ladder can supply that smallest action automatically (the missing adequate method and what it needs). Pass `select_method(domain)`'s blocked method as `if_unresolved` when the agent opens a task. Drop `research_agent.escalations`.
- **F-449, research quality metrics.** Survives: FMBATCH1's `metrics()`.
  - Why: it derives from their richer detail (reuse counts, conclusions, effects); "materially improved" is defined as unseeable, and an empty table gives None, not 0.
  - Mine adds only the agent-side counters (`investigations`, `stopped_no_change`). Merge those two into theirs, or report them next to it. Drop `research_agent.metrics`. The daily readings in `research.sweep` should store `R.metrics` and `R.escalations`.
- **F-435, machine-usable output.** Survives: FMBATCH1's checked conclusion, stored on the task when it is answered.
  - Mine adds a per-investigation conclusion for tasks still open. Keep it as the audit detail only.
- **F-412, research-to-experiment bridge.** FMBATCH1 only (`R.bridge` into `improve.cells`). Mine noted it as not built; theirs stands.
- **Only in W-AGENTS, kept, but adapted to their API:**
  - F-401: the Research Agent, invoked through `request_research` and self-triggered by `research.sweep`;
  - F-436: method selection;
  - F-437: official docs are required for platform behaviour;
  - F-429 / F-430: architecture flags read by `improve.weekly`;
  - F-404: stale-domain triggers.

**Merge breakpoints the integrator must fix** (their stricter API against my calls, all in `intel/research_agent.py` and `runtime/intel_ops.py`):
1. `R.open_question` now requires `evidence_needed`, `stop_condition` and `if_unresolved`. These calls do not pass them, so they would raise `ResearchRefused`:
   - `stale_domains_to_research`: this would break `research.sweep`;
   - the `research.investigate` request path: refused cleanly;
   - several test fixtures.
2. `R.answer` now requires `effect=` and `conclusion=`. The unresolved branch of `investigate` calls `R.answer(outcome, confidence)`. It should call `R.stop(...)` (FMBATCH1's state for "could not resolve"), or answer with `effect={"kind": "stop_justified", …}` and a full conclusion.
3. `_stop()` writes `state = STOPPED` directly. It should be `R.stop()`, so an escalation is recorded.
4. `research.sweep` repeats `detect_unknowns` and `expire_due`, which FMBATCH1's `learn.scan` also runs alongside `stop_overdue` and the fetch run. Both calls are idempotent, but the sweep should keep only what is the agent's own: stale triggers, due investigations and the readings.
5. Once FMBATCH1's allowlisted fetch step is switched on, the ladder's `official_docs` is available for allowlisted hosts. `methods()` should read `research_fetch`'s switch rather than reporting the method unavailable.

**Tests.**
- Survive: FMBATCH1's rule tests (`test_w4_fmbatch1_research.py`, `test_w4_fmbatch1_research_run.py`).
- Keep and adapt to the API: `test_w4_research_agent.py`'s agent tests (declaration, method selection, invocation, sweep, flags, weekly review, F-404, retention).
- Drop with their code: my F-405, F-432, F-444 and F-449 tests.
- Keep the F-420 no-change stop test, routed through `R.stop`.

## Workstream C batch W7: photographic principles from the judged benchmark galleries (F-224; 2026-10-26)

**Prior work checked.** Neither `origin/claude/w4-FMBATCH1` nor any other branch's log names F-224.

**Row.** "Sanctioned MJs gallery images are judged into a closed non-copying merchandising vocabulary, but those observations are not converted into Brambleloop photographic standards or prompts."

**Built.**
- **`visual/photo_principles.py`.** It reads only each judged image's `shot_type` (the closed vocabulary `intel.vision.SHOT_TYPES`) and its gallery rank, joined to the listing's pod.
  - Per pod it measures the first-image shot shares, the share of galleries that include each shot type, and the median number of images judged.
  - A shot type that at least half of a pod's judged galleries include becomes a **principle**, over at least 5 judged listings. A pod below that floor is INSUFFICIENT and has no principles.
  - The free-text observation fields (composition, setting, ...) are never read, so no competitor wording or composition can reach a principle.
- **Comparison with the shot plans.** Each Launch-0 shot plan (`visual.shot_plans`) is compared with its pod's principles, using a shot-type to gallery-job map (for example `detail_macro` to DETAIL, `scale_reference` to SCALE, `in_use` to LIFESTYLE).
  - A principle whose job the plan lacks is an **advisory gap**.
  - No plan is changed. The plan's own gates (F-852, the disclosed-render rule, one job per frame) still decide what may fill a role.
- **Agent wiring.** New job `creative.photo_principles` for the Creative Director:
  - classed RESEARCH, generatable in Product Design, on a daily cadence;
  - declared in WORK_KEYS, and the autonomy map regenerated with no never-woken job types;
  - it stores the `creative.photo_principles` reading.

**Not built.** The row's "prompts" half. FLUX and model prompts are stub-only in this lane, and a generated image cannot fill a listing role under F-852. The profile is in the reading for the visual lane to consume once a provider path exists.

**Tests** (`tests/test_w4_photo_principles.py`, 5/5):
- no judged gallery gives no principle;
- a pod below the floor is INSUFFICIENT;
- wide shot types become principles and missing jobs are advisory gaps, with no competitor text carried;
- the handler stores a reading and changes no plan;
- every judged shot type maps to a gallery job.

Regression: `test_roles`, `test_r2_autonomy_useful_work`, `test_vacuity`, `test_w4_departments`, `test_reachability`, `test_w4_contracts` and `test_v11_autonomy_orchestrator` pass.

## Workstream C batch W8: children's competitive study at runtime (F-367; 2026-10-26)

**Prior work checked.** No branch log names F-367.

**Built.** `creative.children.competitive_study(db)` is now part of the daily `intel.children_portfolio` reading. From the listings already observed through sanctioned sources, it reports for each of the 13 core children's categories (F-353):
- listings, and distinct shops (by the L-3 stable alias, never by name);
- the price band (min / median / max CA$, UNMEASURED when no price was observed) and the share on sale;
- median gallery size;
- how many shops carry a product family there (two or more listings).

A category below 3 observed listings is THIN, and one with none is UNMEASURED. No title, URL, image or wording is kept.

Not built: the row's next action proposed an audience axis in `intel.pods` routing. That changes pod routing for the whole market map, which is the intelligence lane's, so the study reads the same `_CHILD` / `CORE_CATEGORIES` patterns C1 already uses.

**Test** (`tests/test_w4_children.py`, now 6/6): `test_f367_children_competitive_study_is_counts_and_prices_by_aliased_shop`.

## Where Workstream C stands after W8 (2026-10-26)

No open Workstream C row remains that is free of owner or provider dependencies, is not blocked on a live shop, and is not already another lane's. I stop here.

- **Already built elsewhere; the closure matrix is stale:**
  - F-018 language discipline: `commerce.seo.language_findings` plus the translation record (F-251);
  - F-040 shop quality gate: `etsy_ops` assesses getShop, `launch.readiness.etsy_first_sale_surfaces`;
  - F-089 physical truth dashboard (FMBATCH1);
  - F-412 and the research rules (FMBATCH1; see the reconciliation above).
- **Other lanes:**
  - F-45x to F-49x (FMBATCH1);
  - F-061 / F-062 benchmark purchase selection: intelligence/teardown, feeding the owner's purchase card;
  - F-246, F-278, F-285 (listings lane);
  - F-271, ads consuming the zero-sale ladder (growth/marketing).
- **Need a design or owner decision:** F-114, re-engineering legacy products. Re-gauging a legacy CIR means authoring new rows for a design no prototype may invent (`creative.prototype` refuses to invent pattern content). Which legacy products are worth rescuing follows the F-113 recommendations, which are an owner/portfolio decision.
- **Need a provider or network:** F-357 (new culture-feed series), F-406 / F-438 (external research), F-224's prompt half (FLUX is stub-only, and F-852 applies).
- **Need a live shop with data:** F-035, F-036, F-355, F-369, F-372, F-384, F-390, F-502, F-507, F-509, F-511.

## W4-AGENTS2 batch 1: departments report what they produced, quality-reviewed, to Laura (2026-10-26)

**Owner direction.** Departments do real work through the job queue, return evidence, pass quality review and report to Laura. In scope: Storefront, Growth, Marketing, Product Development, Visual Production, Market Intelligence, Finance and Customer Experience.

**Prior work checked.** Neither FMBATCH1 nor FMBATCH2 changes `autonomy/kpis.py` or adds department evidence. FMBATCH1's F-667 is a department workspace *view* (`/api/company/departments/{key}`), not the report.

**The stub, found in code.** Laura reads each department's report as the `kpi_snapshot` that `autonomy.department_review` writes from `autonomy.kpis.compute`. That snapshot carried only three generic activity KPIs, the same for every charter: useful completions, defect dead letters and cadence freshness. `kpis.compute` listed each charter's `kpis` definitions but measured nothing a department produced. No report said what Storefront drafted, what Finance booked or what Intelligence observed.

**Built (no new department, agent, job type or table).**
- **`autonomy/department_evidence.py`.** One reader per department, over rows and readings its own jobs write:
  - **Storefront** (`store_commerce`): surfaces OK, agent and owner gaps, unknown surfaces (newest `storefront.review`), listings drafted.
  - **Growth and Marketing** (`growth`):
    - listings audited and friction incidents (`growth.journey`), pins ready (`growth.distribution`);
    - experiments registered and concluded;
    - content pieces drafted and published (`marketing.schedule`'s `content_pieces`).
  - **Product Development** (`product_design`): certified and uncertified versions, `cir.draft` and `cir.revise` completions in 7 days.
  - **Visual Production** (`visual`): gallery assets, approved assets, shot-plan gaps (`creative.photo_principles`).
  - **Market Intelligence** (`intelligence`): benchmark listings observed, competitor-snapshot groups, research tasks open and answered.
  - **Finance**: net sales from the newest `finance.reconciled`, recorded spend over 30 days, and CFO challenges and blocking challenges from the newest `finance.challenged`.
  - **Customer Experience** (`support`): cases, open cases, drafted replies.
- **Item format.** Every item is `{value, status, sources, why}`:
  - OK when sourced and recent;
  - STALE when the newest source is older than 48 h;
  - UNKNOWN with no value when nothing recorded it. That includes spend with no cost row ("not rendered as CA$0.00", the morning brief's rule) and Customer Experience with no case.
- **Quality review (`review`).** Before it is reported, an OK or STALE item must cite a source and carry a value, an UNKNOWN item must carry no value, and a count must be non-negative. A failing item is REJECTED and listed; it is never passed through.
- **Reporting.**
  - `kpis.compute` adds `evidence`, so every `autonomy.department_review` snapshot Laura reads carries it. A charter outside the eight carries `None`, not an invented block.
  - The morning brief (`autonomy.morning_handoff`) adds `department_evidence`: per department, items passed, rejected, unknown and stale, and the reported values. Laura code is untouched (frozen).
- **Retention.** `finance.reconciled` and `finance.challenged` are classified `latest` (read through a parameter, which the literal scan cannot see).

**Tests** (`tests/test_w4_department_evidence.py`, 6/6):
- every named department has a reader on a real charter;
- nothing recorded is UNKNOWN, never 0, and passes review;
- a reading is cited and goes STALE;
- the review rejects unsourced, UNKNOWN-valued and negative items;
- the department review writes the evidence into Laura's snapshot;
- no cost row means UNKNOWN spend, and the morning brief carries the evidence.

## W4-AGENTS2 batch 2: Visual Production's photography cadence no longer loops on a product with no CIR (2026-10-26)

**Found in code.** `runtime.release._representative_slug` fell back to the first product row when no product-first product needed work, whether or not that product has a CIR. Production ran `assets.owned_photography` ten times on `market-basket-trio`, which has none, and each run was the same "no CIR" no-op.

**Fixed.** With nothing product-first to photograph, it returns nothing, and the handler reports "no certified product to photograph". The product-first ordering and the finished-catalogue fallback (a product with a CIR) are unchanged.

**Test.** `tests/test_w4_department_work.py::test_owned_photography_never_falls_back_to_a_product_with_no_cir` fails on the old fallback and passes now.

**Department duties checked and not built here**, in code, for the other named departments:
- **Storefront / pricing.** `pricing.experiment` is classed PUBLISH ("changes a live price"). It needs owner authority and a live listing, so it stays unbuilt by authority.
- **Growth / Marketing.**
  - `growth.journey`, `growth.distribution`, `growth.preproduction` and `marketing.schedule` are real handlers.
  - The growth agent's `content.draft` drafts only storefront content. Marketing content is `marketing.schedule`'s by design; no caller enqueues another kind.
- **Product Development.** `radar.score` promotes on a principled threshold and gate. "0 drafts in the window" is the promotion bar working, not a stub.
- **Visual Production.** Its other duties are provider-bound: owned and model photography need image generation, and `visual.rnd` paid arms.
- **Market Intelligence.** `intel.acceptance` failing is a missing-evidence result, gated on vision (provider).
- **Finance and Customer Experience.** Real handlers. Customer Experience has no case to work until there are customers (shop-blocked).
