# W4-LAUNCH1: the gate path from today to the first live Etsy listing

**Status.** Records only. Nothing was published or deployed, and no request was made to Etsy or Railway. No `src/` behaviour was changed.

**What was read.**
- **Gate code.** Read on `claude/w4-LAUNCH1`, cut from `origin/claude/w4-INTEG8-next` at `d8f5e852`.
- **Production.** Production runs `ee35a493` (deployed 2026-10-27T16:06Z, SHADOW), which is **not** an ancestor of `d8f5e852`.
- **Differences between the two in the gate files.** `git diff ee35a493 d8f5e852` was run over `launch/`, `core/phase.py`, `ops/publication_authority.py`, `ops/activation_authority.py`, `gates/`, `publish/release_gates.py`, `publish/eligibility.py`, `runtime/pipeline.py`, `integrations/etsy.py`, `publish/listing_schema.py` and `products/`. Only two differences touch a gate:
  - `launch/readiness.py`: INTEG8 adds the F-040 About-story check to `etsy_first_sale_surfaces`. It is not in production.
  - a provider-import rename.
- **Conclusion.** Every gate below reads the same in production, except where marked.

**Evidence labels used throughout:**
- **VERIFIED**: read in code, or run locally from the repo today.
- **FROM REPO**: stated by a committed report. It is not re-run here.
- **UNKNOWN**: cannot be determined from the repo.
- **NEEDS PRODUCTION READBACK**: the state lives in the production database. Another worker is building that readback.

---

## 0. One fact that changes the plan

The current code has two deadlocks. Both come before any owner action, so neither the owner nor a tester can clear them.

| # | Deadlock | Where | Effect |
|---|---|---|---|
| **D1** | `first_customer.check_etsy_remote_state()` reads the **static literal** `publish.listing_schema.gaps()`. Each row of that list is written in code. A successful Etsy round trip does not remove a row, and two rows are not about Etsy at all: "duplicate materials" and "character sets". So the area is permanently `UNVERIFIABLE`. | `gates/first_customer.py:606`, called by `gate_product`. That runs inside `publish.eligibility.product_publication`, then `publish.release_gates.for_publish`, then `runtime.pipeline._release_gates`. | `store.publish` returns `blocked` **before it creates the draft**. `_revalidate_publish_effect` refuses for the same reason. The first draft is the thing PRODREADY B5 expected to clear this area, and it can never be created. **Engineering.** |
| **D2** | `launch.readiness.assess` hard-codes `listing_fees` (line 788) and `brand_clearance` (line 836) as `ready=False`. No owner decision, record or approval is read. `owner_queue.DECISION_BY_KEY` only displays them. | `launch/readiness.py`, `transition_verdict`, `core.phase._readiness_at_transition` | `transition_verdict(...).ready` can never be True. So `core.phase.record_transition` refuses **every** upward move, including SHADOW→STAGING. `store.publish` needs `limited_production`, so it can never run. **Engineering**: the requirement needs an evidence path, for example a sealed owner decision row, before the owner's "yes" can count. |

Neither deadlock is fixed here, because this lane may not change `src/` behaviour. Both are blockers E1 and E2 in §5.

---

## 1. The gate sequence, in execution order

The first live listing is two Etsy writes, each behind its own owner grant:

- `store.publish` creates an **inactive draft**;
- `store.activate` turns that draft **active**.

Both refuse unless the effective phase is `limited_production` or `production` (`integrations.etsy.PHASES_THAT_MAY_PUBLISH`). The phase moves one step at a time: shadow → staging → limited_production.

### Stage A: per-release evidence (runs in SHADOW, continuously)

| # | Gate | What it checks (module:function) | Satisfied by | Evidence that proves it |
|---|---|---|---|---|
| A1 | **CIR compile + certification** | `gates.certificate.certify`, run by the `gate.certify` handler. It covers compile, independent reverse compile, the twin, the risk matrix and benchmark containment. A PatternVersion has `certified=True` plus a `release_hash`. | code + data (the release chain) | A `gate.certified` audit row and `pattern_versions.certified` with `certificate.granted=True`. Read by `ops.publication_authority._certification`. |
| A2 | **Product Truth** | `products.launch0.product_truth(candidate)`, which covers the title, motif and assembly promise and fabric truth. It is also enforced at publish by `publish.eligibility.name_truth` (`NAME_OUTRUNS_PATTERN`). | code | `passes_gates=True`. **VERIFIED today for all 8 Launch-0 products** (§3). |
| A3 | **Not superseded / not halted / no unreviewed policy change** | `publish.release_gates.staleness` and `superseded_release`. It refuses on any open `halts_publication` incident (#173), any unreviewed material policy change that affects `publishing` (#39), or an outstanding rebuild (#172). | code + data, plus an owner review for a policy change | No halting incident for the slug. `platform_policy.unreviewed_changes()` is empty for the publishing sources. |
| A4 | **Originality** | `release_gates.originality_gate` | code | The gate's reasons are empty. |
| A5 | **Seasonal window** | `release_gates.window_decision` (#297) | code + date | `may_launch_seasonally=True`. |
| A6 | **Listing-set certificate** | `release_gates.listing_set`, then `disclosed_listing_set`. It covers the frame set (#65), dimensions (#60), mobile QA (#66), the gallery floor (#80), the four-gate export (#58) and the certificate (#70). | code + data (disclosed renders, D-FB-7/D-FB-9) | A valid listing-set certificate `record_id` bound to the release hash. |
| A7 | **Search certificate** | `release_gates.search_gate` (F-004/F-005/F-294). It needs a stored Etsy taxonomy id, attributes, copy, tags and the hero. | code + **external data** (Etsy taxonomy schema) | `search.verdict == "PASS"`. **FROM REPO: FAIL on every product** (PRODREADY B2; LISTREADY says CHOSEN only if Etsy's schema offers "Crochet": UNKNOWN). |
| A8 | **Standards / withholding** | `release_gates.standards_gate` (#153-#160, #220, #228 owner veto) and `withholding.reconcile` (#163) | code + data | No reasons. |
| A9 | **First-customer nine-area gate** (Launch-0 only) | `gates.first_customer.blocking`, called from `publish.eligibility.product_publication`. Every area must be PASS; UNVERIFIABLE and UNRESOLVED block. The areas are listed in the next table. | mixed | `first_customer_blocking == []` |
| A10 | **Price = plan** | `release_gates.launch_price_check` and `products.launch0.launch_price` | code | `state != "DRIFT"`. **VERIFIED in plan** (§3). |
| A11 | **Taxonomy drift not held** | `integrations.taxonomy_drift.held_drift` | code + Etsy data | No held incident. |
| A12 | **Creative parity (#75)** | `runtime.pipeline._listing_parity` and `visual.parity.assess`. Eight dimensions, incl. HERO and COMPETITIVE. Both frame reviews are needed: `runtime.release.frame_review_state` and `visual.exported_review.review_state`. | code + **funded `image_vision`** (D-W4-LAUNCH-VISION-BATCH, CA$7.07, approved, NOT activated) | `parity.verdict == PASS`, no dimension unjudged, frames independently reviewed. **FROM REPO: UNKNOWN on all** (PRODREADY B3). |
| A13 | **Search-grid tournament (#126)** | `creative.preengineering.release_grid_verdict` | code + data | `cleared=True`. **NEEDS PRODUCTION READBACK.** |
| A14 | **PDF hash = certified** | `runtime.pipeline.check_pdf_hashes` against the `assets.built` hashes | code | `store.pdf_hash_verified` audit row. |
| A15 | **Certified image bytes present** | `runtime.etsy_ops.certified_images` (F-524) | code + durable bytes | `problems == []` |

The nine areas of the first-customer gate (A9), from `gates/first_customer.py`:

| Area | Function | Cleared by | State today |
|---|---|---|---|
| `final_pdf` | `check_final_pdf` | code | FROM REPO: PASS (PRODREADY) |
| `terminology` | `check_terminology` | code | FROM REPO: PASS |
| `counts_and_construction` | `check_counts_and_construction` | code | FROM REPO: PASS |
| `gauge_and_size_claims` | `check_gauge_and_size_claims`, `physical_binding`, then `gates.certificate.bind_physical_evidence` and `gates.risk_matrix.first_customer_requirement` | **physical**: a passed `PhysicalTest` bound to this exact content hash. The class must be at least `partial_physical`, even for class A (`need = required_physical or PARTIAL_PHYSICAL`). | UNRESOLVED on all products; no sample is on file (FROM REPO) |
| `listing_claims` | `check_listing_claims` | code (+ physical, for "made by a tester" claims) | FROM REPO: PASS |
| `imagery` | `check_imagery` and `disclosed_imagery` | code + data | FROM REPO: PASS (disclosed set + certificate) |
| `etsy_remote_state` | `check_etsy_remote_state` reads `listing_schema.gaps()` | **nothing today (D1)**. Needs an engineering change: read the verified round-trip evidence, for example `launch.readiness._etsy_exercise_evidence`, or the verified facts. | UNVERIFIABLE, permanently, as coded |
| `fulfilment_and_download` | `check_fulfilment_and_download`, then `commerce.deliverables.durable_state` | data: certified PDFs held in Postgres `durable_artifacts` and re-hashed. Durable object storage (owner) also clears it. | NEEDS PRODUCTION READBACK. PRODREADY B6 read FAIL before FIRSTSALE's Postgres path. |
| `licence_and_safety_statements` | `check_licence_and_safety_statements` | code | FROM REPO: PASS |

`first_customer.NEVER_AUTHORISES`: even nine PASSes are "evidence for an owner review, not a substitute". The owner must have read the document.

### Stage B: leave SHADOW (owner-only, one step at a time)

| # | Gate | What it checks (module:function) | Satisfied by | Evidence |
|---|---|---|---|---|
| B1 | **Readiness evidence row** | `core.phase._resolve_evidence`: `evidence_refs.readiness` = id of a `launch.assessed` AuditLog row ≤ 7 days old. It must have `ready=True` for a move into limited_production or above. | code (`launch.readiness` handler, `runtime/release.py:4085`) | the audit row id |
| B2 | **Rollback rehearsal row** | `evidence_refs.rollback` = id of a `launch.rollback_rehearsed` row ≤ 3 days old (`launch.rollback.rehearse`). It must have `ok=True` for limited_production or above. | code | the audit row id |
| B3 | **Live launch verdict** | `core.phase._readiness_at_transition`, which calls `launch.readiness.transition_verdict(db, to=...)`. That needs all of: every requirement of `assess()` (the six F-300 questions plus `other_hard_gates`), the off-device autonomy proof `PROVEN` (`build2.autonomy.launch_item`), and the F-275 demand-capture plan complete (`launch.demand.capture_plan`). It is evaluated **for STAGING too**, and only `phase` is excluded. | see the requirement table below | sealed into the transition row as `readiness_at_transition` |
| B4 | **Owner records the transition** | `core.phase.record_transition`, through `POST /api/owner/phase/transition` `{to, reason, evidence_refs:{readiness, rollback}}` with the ops token | **owner** | a sealed, hash-chained `owner.phase.transition` row |
| B5 | **Environment agrees** | `core.phase.resolve`: `BRAMBLELOOP_PHASE` must equal the recorded phase, or the more restrictive phase wins and a P1 `phase_mismatch` incident opens | **owner** (Railway variable) | `GET /api/owner/phase` with `agree: true` |
| B6 | Repeat B1-B5 for staging → limited_production. From here, the cited readiness and rollback rows must **pass**. | same | owner | a second transition row |

The requirements of `launch.readiness.assess()` that `transition_verdict` needs. These are the minimum list; anything unmapped falls into `other_hard_gates` and also blocks.

| Requirement | Ready when | Blocked by (code's own label) | State |
|---|---|---|---|
| `catalogue_depth` | ≥ 8 certified launch-scope **products** with listing rows | build/data | NEEDS PRODUCTION READBACK. 8 products in scope in code (`CATALOGUE_FLOOR_APPROVED=True`). LISTREADY: 0 of 10 Launch-0 releases certified in production at the code's versions on 2026-10-20. |
| `listing_imagery`, `imagery_truthful`, `listing_photography` | ≥ 6 approved frames per listing; no Asset-Truth block; coverage | build | NEEDS PRODUCTION READBACK |
| `pricing`, `content`, `pricing_promotion_plan`, `launch_calendar`, `analytics_baseline`, `digital_disclosure`, `support_knowledge`, `faq`, `rollback_plan` | per listing: audit rows and provenance | build (release chain) | NEEDS PRODUCTION READBACK |
| `storefront`, `seller_identity`, storefront items | `brand.storefront.check_storefront` and `commerce.trust.shop_complete_problems` | owner (done 2026-10-11) + build | NEEDS PRODUCTION READBACK. The owner completed storefront setup on 2026-10-11 and **must not be asked again**. |
| `no_open_incidents` | no open P0/P1 | data | NEEDS PRODUCTION READBACK |
| `spend_guards` | no paused spend scope | data | NEEDS PRODUCTION READBACK |
| `etsy_first_sale_surfaces` | `intel.etsy_surfaces.first_sale_blockers` fresh (messages, legal_and_tax readings, plus about_story on INTEG8 only) | owner readings via CC | NEEDS PRODUCTION READBACK |
| `etsy_integration` | a **full** `etsy_exercise` round trip against openapi.etsy.com, with every test draft verified deleted (`_etsy_exercise_evidence`) | integration: needs the owner's word to run the CA$0 test-draft round trip (held since 2026-09-25) | NOT DONE as of the last repo record (BUILD_STATE 2026-09-25: "gated on the owner's word") |
| `artifact_storage` | `ArtifactStore.durable` | **owner** (object storage, CA$1-5/month) | FROM REPO: not durable. Note that this reads the store flag only, not FIRSTSALE's Postgres path, so it stays false even where `fulfilment_and_download` passes. |
| `etsy_shop` | shop identifier + recorded sanctioned read | owner (done) | FROM REPO: shop `BrambleloopStudio` exists, OAuth verified 2026-09-25 |
| `payout` | `payout_evidence` | owner (KYC/banking) | NEEDS PRODUCTION READBACK |
| `listing_fees` | **constant False** (D2) | owner, but there is no evidence path | blocks forever as coded |
| `model_credits` | the last provider probe succeeded | owner (funding) | NEEDS PRODUCTION READBACK |
| `physical_calibration` | ≥ 1 `PhysicalTest` passed | **physical** (tester) | none on file (FROM REPO) |
| `risk_based_physical_evidence` | **every certified release** holds its tier's evidence (`gates.risk_matrix.catalogue_status`): class B/C need a physical sample, class A is deterministic. This covers non-Launch-0 certified releases too. | physical | none on file |
| `brand_clearance` | **constant False** (D2) | owner, but there is no evidence path | blocks forever as coded |
| `benchmark_challenge` | a representative product beat or traded against a purchased category benchmark | build / owner (benchmark purchases) | NEEDS PRODUCTION READBACK |
| `brand_moat` | structural advantages + recognisable without the model | build (+ vision) | NEEDS PRODUCTION READBACK |
| `sustainable_economics` | `finance.sustainability.verdict` MODELLED, sustainable | build | NEEDS PRODUCTION READBACK |
| `final_master_closure` | `build2.final_master.summary().launch_ready` | build | NEEDS PRODUCTION READBACK |
| off-device autonomy proof | `build2.autonomy.launch_item` = PROVEN | build | NEEDS PRODUCTION READBACK |
| demand-capture plan | `launch.demand.capture_plan().complete` | build | NEEDS PRODUCTION READBACK |

### Stage C: create the inactive draft (`store.publish`), in LIMITED PRODUCTION

Order inside `runtime.pipeline.handle_store_publish`, then `_publish_guarded`, `_revalidate_publish_effect` and `_publish_and_read_back`:

1. **`visual.experiment.refuse_if_experiment`**: an experiment never publishes.
2. **Parity and release gates computed** (Stage A), and audited as `listing.parity` and `store.release_gates`.
3. **`protected_phase(ctx)` ≠ SHADOW**: the phase is re-resolved now.
4. **`EtsyClient.refusal()`**:
   - the phase is in `PHASES_THAT_MAY_PUBLISH`;
   - **`BRAMBLELOOP_PUBLISH_AUTHORISED=1`** (owner kill-switch; it may only deny);
   - credentials are present (sealed OAuth in `oauth_credentials`).
5. **Parity refusal**, if `blocks_release`.
6. **Listing row exists** and has no `etsy_listing_id`.
7. **PDF hash check** (`check_pdf_hashes`).
8. **Search-grid tournament** (`creative.preengineering.release_grid_verdict`).
9. **Release-gate block**, if `blocks_release`. **D1 stops the publish here today.**
10. **Certified image bytes** (`etsy_ops.certified_images`).
11. **`_revalidate_publish_effect`**, run at `pre_claim` and `before_create`:
    - the owner **publication grant** (`ops.publication_authority.resolve`): sealed, scoped to `slug@version` + release + CIR digest + exact payload + F-704 evidence, 24 h, revocable, hash-chained;
    - the phase is re-checked twice;
    - parity and gates are re-run;
    - the payload, PDFs and images are rebound to the reserved digest.
12. **`OwnerGrant.refusal` in the client**, immediately before `createDraftListing`.
13. **Read-back** (F-542): fields, image count, draft state and exact files. Then a `store.published` row, or `store.publish_incomplete` plus a halting incident.

**Owner grant** (`ops.publication_authority.approve`):
- **Command Center:** `#/approvals`, card **"Create the Etsy draft for {slug} v{version}"**. The card has two actions:
  - `publication.preview` (no step-up);
  - `publication.approve` (step-up, with `expected_digest` taken from the preview).
- **Server-side rule:** the CC refuses unless **every gated section** of the evidence passes (`approvals._require_publication_evidence`). The gated sections are certification, parity, listing_set, disclosure, policy, search and rollback.
- **API:** `POST /api/owner/publication/preview` then `/approve`, with the ops token.

### Stage D: activate (`store.activate`): this is the first live listing

`runtime.pipeline.handle_store_activate`:

1. Gates are recomputed and audited (`store.activate_gates`).
2. SHADOW refuses.
3. An Etsy draft must be recorded for the release.
4. **Remote read-back** of the draft against the certified listing (`integrations.etsy_verify.activation_readiness`):
   - every sent field, the image count against the certificate frames, and the exact files from the `store.published` row;
   - the disclosure **as Etsy holds it**;
   - parity and the release gates again.
5. Owner authority:
   - `client.refusal_for(Authority.ACTIVATE)`, which includes the kill-switch;
   - **`ops.activation_authority.validate`**: a separate sealed grant bound to `listing_id`, the frames and the verified files.
6. **Daily spend ceiling**: the agent's spend today + the pending listing fee (US$0.20 × `ASSUMED_CAD_PER_USD`) must be ≤ `daily_cost_ceiling_cad`.
7. `EtsyClient.activate`, then a read-back showing `active`.

**Owner grant**:
- **Command Center:** `#/approvals`, actions `activation.preview` and `activation.approve` (step-up).
- **API:** `POST /api/owner/activation/preview` and `/approve`.

### Stage E: what proves "first live listing"

All of the following:
- a `store.published` row, with read-back verified;
- a `store.activation_verified` row with `ready: true`;
- an activation read-back of `active`;
- `listing.state == "active"` with an `etsy_listing_id`;
- the next `etsy.listing_census` matches.

None of these exist (FROM REPO: production `store.published` = 0).

---

## 2. Who satisfies what (summary)

| Class | Gates |
|---|---|
| **Code** | A1-A6, A8, A10, A11, A14, A15; most readiness build rows; **and D1/D2, which need a code change before anything else can clear** |
| **Data / external** | A7 (Etsy taxonomy schema: "Crochet" node UNKNOWN), A13, A12 (needs funded `image_vision`), the policy readings (§ ETSY_POLICY_READINGS_PACKET.md) |
| **Physical** | `gauge_and_size_claims` for every published product; readiness `physical_calibration` and `risk_based_physical_evidence` (all certified releases) |
| **Owner** | phase transitions B4/B5 (×2); kill-switch; publication grant; activation grant; listing-fee approval; object storage; payout/KYC confirmation; vision batch activation; tester outreach + sample fee; trademark decision; the five legal-page policy readings (or a named reader) |

---

## 3. Product readiness (repo only)

Run locally today from `d8f5e852`, with deterministic code and no DB: `products.launch0` (`LAUNCH0_SLUGS`, `cir_for`, `launch_price`, `product_truth`), `cir.compiler.compile_cir`, `cir.twin.build_twin`, `gates.risk_matrix.matrix_for`, and `gates.certificate._release_hash` over `cir.writer.write_pattern(..., "US")`. The scratch scripts were not committed.

**Production stage for every row: NEEDS PRODUCTION READBACK.** LISTREADY (production b931d17, 2026-10-20) found 0 of 10 Launch-0 releases certified in production at the code's versions. R5 seeds one per hourly `chain.rebuild`. Whether `ee35a493` has certified them since is UNKNOWN.

| Product (candidate) | CIR slug @ version | Compiles | Product Truth | Content hash (US) | Risk class (eff.) | Physical required for the first customer | Plan price | Repo pipeline stage | Next missing step |
|---|---|---|---|---|---|---|---|---|---|
| nursery-nesting-baskets | market-basket-small@1.2.0 | yes | PASS | `1ddde587f537388b` | B (dimensional_form) | partial_physical (a full make also satisfies it) | CA$6.50 | certified + listing set + legible (FROM REPO, PRODREADY local chain); **tester kit built for exactly this hash** | owner confirms `tester_outreach` (CA$59.65 max); the tester works the kit; then `POST /api/physical-test` |
| nursery-nesting-baskets | market-basket-medium@1.2.0 | yes | PASS | `00182234041c441c` | B | partial_physical | CA$6.50 | as above | a sample bound to this hash (no kit) |
| nursery-nesting-baskets | market-basket-large@1.2.0 | yes | PASS | `cc698c1b14984eeb` | B | partial_physical | CA$6.50 | as above | a sample bound to this hash (no kit) |
| cloudline-baby-blanket | cloudline-baby-blanket@1.2.0 | yes | PASS | `7c63dbdd501fa6b1` | B (high_yardage; declared A) | partial_physical | CA$7.50 | as above | swatch/component sample |
| hexagon-coaster-set | hexagon-coaster-set@1.2.0 | yes | PASS | `3754ed17a63b790d` | A | partial_physical (first-customer floor) | CA$4.00 | as above | swatch sample (smallest make in the catalogue) |
| nordic-star-ornaments | nordic-star-ornaments@1.5.0 | yes | PASS | `3c97c95970d3ee23` | A | partial_physical | CA$4.50 | as above (retitled "Textured Stripe Ornament Set (6)") | swatch sample |
| winter-village-graphghan | winter-village-graphghan@1.3.0 | yes | PASS | `b41e0430fe3dadb9` | B (high_yardage) | partial_physical | CA$7.50 | as above | swatch/component sample |
| nordic-forest-mosaic-throw-baby | …@1.3.0 | yes | PASS | `01679f95e4ddd1b7` | A | partial_physical | CA$7.50 | as above | swatch sample |
| mosaic-placemat-pair | mosaic-placemat-pair@1.4.0 | yes | PASS | `5f1c939a89f909d8` | A | partial_physical | CA$5.00 | as above (retitled "Raised Diamond Lattice Placemat Pair") | swatch sample |
| housewarming-key-basket | housewarming-key-basket@0.1.0 | yes | PASS | `142b52f0f9c62e9f` | B (dimensional_form) | partial_physical | CA$5.50 | as above | a sample bound to this hash |

The table has 10 releases (8 products). No variant is `twin.calibrated`, and no `PhysicalTest` is recorded anywhere in the repo.

**Common to all.** None of them can pass the steps below today:
- A7 (search certificate);
- A12 (vision review);
- D1 (`etsy_remote_state`);
- `gauge_and_size_claims`.

These are all listed in §5.

**Retired, never publishable.** `market-basket-trio` and `hexie-coaster-set` (`products.launch0.LEGACY_DUPLICATES`). PRODUCT_INVENTORY lists other catalogue products (cable blanket, bobble pillow, ribbed scarf, and others); they are outside Launch-0 scope and are not candidates for the first listing.

**Closest to physical verification:**
1. **market-basket-small@1.2.0.** This is the only product with a built tester kit (`research/final_build/w4/tester_kit/`: test PDF, record sheet, CASL consent, the outreach post — prepared, **not sent**). The kit's `content_hash` `1ddde587…` equals today's computed hash, so a sample would bind. It is waiting on one owner decision: `owner_queue` `tester_outreach`, CA$59.65 ESTIMATED ceiling, 25 min.
2. **hexagon-coaster-set@1.2.0.** Class A, so a swatch-scale partial test satisfies it, and it is the smallest object. There is no kit yet; building one is company work.
3. **nordic-star-ornaments@1.5.0** and **mosaic-placemat-pair@1.4.0**. Class A, small makes, no kit.

---

## 4. Policy, price, rollback: where the approval package reads them

See `PUBLICATION_APPROVAL_PACKAGE_TEMPLATE.md` and `ETSY_POLICY_READINGS_PACKET.md`.

---

## 5. Blockers to first publication

Each blocker is listed with its class and the exact next action. The order is roughly the order in which they must clear.

| # | Blocker | Class | Exact next action |
|---|---|---|---|
| E1 | **D1**: the `etsy_remote_state` area reads a static gap list, so `store.publish` can never create the first draft | **engineering** | Change `gates.first_customer.check_etsy_remote_state` to accept database evidence. It should pass on a proven `etsy_exercise` round trip (`launch.readiness._etsy_exercise_evidence().round_trip_proven`) together with `listing_schema` verified facts, and otherwise stay UNVERIFIABLE. It should also stop counting non-Etsy internal gaps. This changes a gate, so it needs a security-classifier-safe review. The rule is not loosened: the evidence becomes reachable. |
| E2 | **D2**: `listing_fees` and `brand_clearance` are hard-coded `ready=False`, so no phase transition can ever be recorded | **engineering** | Make each requirement read an evidence row: a sealed owner decision for listing fees; a recorded knock-out search plus the owner's trademark decision for brand_clearance. Keep both False without that row. |
| E3 | The owner's first page reading of each source is compared with the repo's excerpt seed (`record_page_reading` passes no `compare_basis`). It therefore records a "material change", opens a halting P1 `policy_changed:<source>`, and needs a CC review before publishing | **engineering** (the CC review is the workaround: owner, ~2 min per source) | Either pass `compare_basis=PAGE_BASIS` in `record_page_reading`, as `policy_reader` already does for Help Center reads, or document that each first reading is followed by `policy.review` in `#/approvals`. |
| E4 | Search certificate FAIL: no Etsy taxonomy node matched ("Crochet" under Patterns & Blueprints is UNKNOWN) | **external / engineering** | Read production's latest `listing.taxonomy_refresh` record of pattern/crochet names (production readback). Then correct `etsy_taxonomy.pattern_subtree` to the real node, with no assumed node. |
| E5 | Policy readings: the repo seed is dated 2026-09-26, older than 30 days, so the `policy` section is FAIL/UNKNOWN. The image article was edited by Etsy on **2026-10-22** | **owner** (person reading) + **data** | The owner or a named reader records the five etsy.com/legal sources, plus the image rules (§ packet). Then review any `policy_changed` card in `#/approvals`. |
| E6 | Vision review / parity HERO and COMPETITIVE unjudged | **owner** (activation step-up of the approved CA$7.07 batch) | Activate D-W4-LAUNCH-VISION-BATCH in production, then let `assets.build` / blind review run. |
| E7 | No physical sample bound to any Launch-0 content | **physical** (tester) + **owner** (outreach + fee) | Owner confirms `tester_outreach` (market-basket-small, ≤ CA$59.65). A tester works the kit and the result is recorded via `POST /api/physical-test`. Repeat per product to be published, at least partial_physical. |
| E8 | `risk_based_physical_evidence` covers **every** certified release whose risk tier requires physical evidence (class B/C), not only the ones to be listed | **physical / engineering decision** | Readback the list of certified releases in production. Either evidence each one, or decide (company) whether non-launch releases should be de-certified or scoped out. Do not weaken the gate. |
| E9 | The Etsy write path has never been confirmed (`etsy_integration`) | **owner** (word to run) + external | Owner says "run the controlled round trip" (CA$0: test draft, image, update, read-back, delete, verify 404). Then `integrations.etsy_exercise`. Only the owner can remove a stranded draft. |
| E10 | Durable storage: `artifact_storage` reads `ArtifactStore.durable` | **owner** | Approve object storage (CA$1-5/month, inside the existing ceiling), or rule that the Postgres `durable_artifacts` path satisfies the requirement. The second option is an engineering change to readiness. |
| E11 | Production state of every Launch-0 release (certified? drafted? listing set?) | **data** | Wait for the production readback worker. LISTREADY said 0 of 10 were certified on 2026-10-20. |
| E12 | Payout/KYC/tax confirmation, model credits, benchmark challenge, brand moat, economics, Final Master closure, off-device proof, demand plan | **owner / data** | Production readback of `GET /api/owner/phase/verdict`, which lists `failing`. Act only on what it names. |
| E13 | Two phase transitions (shadow→staging→limited_production), each with fresh evidence rows and `BRAMBLELOOP_PHASE` set to match | **owner** | After E1-E12: `POST /api/owner/phase/transition`, then set the Railway variable. Repeat once. |
| E14 | Publication grant, then activation grant, plus `BRAMBLELOOP_PUBLISH_AUTHORISED=1` | **owner** | In `#/approvals`: preview, read the package, then approve (step-up), once per release, for the draft and again for activation. |
