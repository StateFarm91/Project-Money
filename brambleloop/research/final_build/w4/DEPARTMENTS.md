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
