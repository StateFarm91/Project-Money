# W4-LISTREADY: from "now" to 8 Launch-0 listings ready for the first Etsy sale

**Context**
- **Branch:** `claude/w4-LISTREADY`, cut from `origin/claude/final-candidate-b997efd` (b997efd)
  with `origin/claude/w4-FIRSTSALE2` (ade23d2) merged in (clean merge, c2e60b69).
- **Not merged:** CLOSE6 and VISNEXT2.
  - CLOSE6 adds an About-page launch hold; it does not close a listing gap.
  - VISNEXT2 is the staged Laura lifestyle pipeline. Launch-0 listings use the disclosed renders.
- **Production:** b931d17, SHADOW. Read only, with unauthenticated public GETs on
  2026-10-20 between 20:50Z and 21:00Z:
  - `/health`, `/api/verify`, `/api/launch`, `/api/etsy/surfaces`, `/api/incidents`, `/api/jobs`;
  - `/api/audit` for these actions: taxonomy, shop snapshot, census, orders, `assets.built`,
    `cir.*`, `gate.*`, `chain.rebuilt`, `ops.sentinel` and `ops.rebuild_propagated`.
- **Not done:** no deploy, no POST, no Etsy write, no spend, no key.
- **Coordinator decision, recorded:** the first approach, which relaxed `gate.certify` for
  staleness-only incidents, was refused by the permission classifier ([Security Weaken]).
  - It was reverted and never committed.
  - The fixes below change no rule about what halts certification or publication.

## 1. The finding: production has certified nothing since 2026-10-11

| reading (production, 2026-10-20) | value |
|---|---|
| `systemic-halt:publication` (incident #380) | **P0, open, `applicability: current`**, last confirmed 20:45Z; evidence `integrity: []`, `widespread: ['stale-artefact']` |
| stale-artefact P1 halts | on 14 products, 11 to 27 each |
| `ops.sentinel` 20:02Z | checked 587, **stale 299**, `publication_blocked` 14 products |
| `gate.halted` "open P0/P1 incident" | nordic-star-ornaments@1.5.0 and mosaic-placemat-pair@1.4.0 (10:02Z, right after `cir.compiled ok`); winter-village-graphghan@1.3.0 on 10-12 |
| last `gate.certified` | 2026-10-11 |
| Launch-0 releases (code) held certified in production | **0 of 10** at the code's versions |

**Root causes (code):**
- **R1, the sentinel compared against the wrong version.**
  - `ops.artefacts.current_from_db` fingerprinted only the **newest** PatternVersion of a slug.
  - `design_inputs` records every artefact from **its own** release.
  - So every artefact of an older release read STALE forever. Each one raised a halting P1, and
    at 3 or more products and 50% of the catalogue the halts escalate to the company-wide P0.
- **R2, the deadlock this created.** Gate E halted `gate.certify` on those incidents, and
  certifying is how a stale estate gets rebuilt.
  - Gate E is **not** changed here.
  - The deadlock disappears once R1 stops raising the false halts.
- **R3, a halted certify is never retried.** It consumes the `cir.draft`, `cir.compile` and
  `gate.certify` idempotency keys, so a release halted once is never retried.
- **R4, stale marketing could never be rebuilt.** The marketing rebuild exception
  (`outstanding_only_marketing`) required that *nothing* halts the product. The sentinel's own
  rows for that stale marketing are halting, so the content could never be rebuilt.
- **R5, six Launch-0 releases were never drafted.** `chain.rebuild` redrafts only slugs that are
  already certified. These six never entered the chain:
  - market-basket-small, -medium and -large@1.2.0;
  - hexagon-coaster-set@1.2.0;
  - nordic-forest-mosaic-throw-baby@1.3.0;
  - housewarming-key-basket@0.1.0.

## 2. What was built (engineering class (a))

| fix | where | what it does | gates changed |
|---|---|---|---|
| **R1** | `ops/artefacts.py` (`Fingerprints`, `built_from_version`, `check`, `sweep`, `current_from_db`) | An artefact is judged against the PatternVersion it was built from. A versioned key names the release. An unversioned key (marketing) is matched by its recorded `cir:`/`release:` fingerprint to exactly one certified release; with no unique match it is judged against the newest release, as before. An artefact of a release the product has moved past is **`superseded`**: never fresh, raises no halt, and its old sentinel incident is closed with the reason. A plain dict `current` keeps the old meaning. | none |
| **R1 guard** | `publish/release_gates.superseded_release`, `for_publish` | Publication refuses any release that is not the product's newest certified release. Unreadable state refuses. | stricter |
| **R3** | `runtime/release_recovery.retry_halted`, called by whole-catalogue `chain.rebuild` | Re-enqueues the halted `gate.certify` with the halted job's own CIR. The key is `certify-after-halt:<slug>:<version>:<halt audit id>`: once per halt episode, never while `publication_halted`, and never after a later certify outcome. | none |
| **R4** | `publish/release_gates.staleness` | `outstanding_only_marketing` ignores only the sentinel's own rows for exactly the outstanding marketing assets. `halted`, `reasons` and `blocks` (what publication reads) are unchanged, and any other halt still refuses the rebuild. | none |
| **R5** | `runtime/release_recovery.seed_launch0`, called by whole-catalogue `chain.rebuild` | `cir.draft` for the next Launch-0 release (listing order) whose code version is not certified, **one per run** (`SEED_PER_RUN` = 1; hourly in production, so about 10 h for all ten). The key is `launch0-seed:<slug>:<version>:<fingerprint>:d<DOC>`. Drafting, compiling and certifying are the normal jobs with their normal gates. | none |
| redraft false positive | `runtime/release.handle_chain_rebuild` | `stale_design` compared `to_dict()` (tuples) with the stored JSON (lists), so every engineered design read "changed" and was redrafted once per fingerprint. Found by `test_product_run` once R5 had certified Launch-0 releases. It now compares through the same JSON encoding; a real design change still differs. | none |

**Tests: `tests/test_w4_listready.py`, 11/11.**
- `test_an_older_release_artefact_is_superseded_not_stale_and_raises_no_halt`:
  - the b931d17 logic gives 2 stale and `hex` blocked;
  - the new logic gives 2 superseded, 0 stale, incidents closed "superseded, not stale", and no
    halt.
- `test_an_unversioned_marketing_asset_is_matched_to_the_release_it_was_built_from`:
  - marketing built from 1.0.0 reads superseded;
  - a design that matches no release stays stale and halting.
- `test_genuinely_stale_artefacts_of_the_current_release_still_raise_halting_p1s`: a P1,
  `halts_publication`, and `publication_halted` is True.
- `test_a_recertified_current_release_turns_its_own_artefacts_stale`: a moved `release:` still
  reads stale.
- `test_the_p0_trips_at_the_same_threshold_for_genuine_staleness_and_not_for_superseded`:
  - with the old logic the P0 opens;
  - with the new logic it resolves;
  - genuine staleness on 2 of 4 products gives no P0, and on 3 of 4 it gives the P0.
- `test_publication_refuses_a_superseded_release`: `for_publish` blocks 1.0.0 with
  "superseded release (R1)", and 1.1.0 does not carry that reason.
- `test_genuinely_stale_marketing_may_be_rebuilt_while_publication_still_refuses`:
  - publication is still halted and blocked;
  - the rebuild flag is True;
  - with a customer-defect P1 added, the rebuild flag is False.
- `test_a_halted_certification_is_never_retried_while_the_halt_holds_and_once_after`:
  - while the Gate E P1 is open, the release is still halted and nothing is retried;
  - once resolved, it is retried once, and a second call gives `already_retried`;
  - the retry carries the halted job's inputs;
  - then `gate.certified`, exactly 1 PatternVersion, and no further retry.
- `test_a_retry_that_is_halted_again_opens_a_new_episode`.
- `test_every_uncertified_launch0_release_is_drafted_once_through_the_normal_job`:
  - 9 seeded (the 1 certified is skipped), including all six never-drafted releases;
  - re-running seeds 0;
  - the seeded `cir.draft` drafts the engineered design and enqueues `cir.compile`.
- `test_production_deadlock_reproduced_then_cleared_with_every_gate_unchanged`. This
  reproduces production's situation on three products:
  - older-release artefacts, the newest release past them, and the P0;
  - `gate.certify` of the new hexagon-coaster-set@1.2.0 is halted.

  After the fixed sentinel runs:
  - the P0 resolves and the product is no longer halted;
  - `chain.rebuild` retries the halted certify, and it is **granted**;
  - the old release now reads superseded at publish;
  - a second rebuild does not retry.

Every gate is unchanged: `gate.certify` still calls `publication_halted`, and Gate E's
customer-defect P1 still halts certification (asserted).

## 3. Gap table: the 11 first-sale surfaces

States: FRESH, FAILING, NO_EVIDENCE, STALE, NO_COLLECTOR, UNKNOWN.

| surface | production b931d17 today | after b997efd | after b997efd + FIRSTSALE2 + LISTREADY | what remains | class |
|---|---|---|---|---|---|
| listings | FRESH (census 00:09Z: 0 listings) | FRESH | UNKNOWN whether FAILING (shop snapshot fails `has_a_digital_listing`) | a real published listing | d (publication grant) |
| messages | NO_COLLECTOR | NO_COLLECTOR | NO_EVIDENCE | owner POSTs a dated `messages` reading (`notifications_inbox`, `reply_window_hours`) | d |
| orders | NO_COLLECTOR (and the stale `reauthorise_transactions_r`) | NO_COLLECTOR | **FRESH** (receipts read 18:03Z, `gate_missing: []`) | none | — |
| payment_settings | FRESH | FRESH | FRESH | owner confirms payout, KYC and tax in Shop Manager | d |
| legal_and_tax | NO_COLLECTOR | NO_COLLECTOR | NO_EVIDENCE | owner POSTs a dated `legal_and_tax` reading | d |
| your_shop | FRESH | FRESH | FRESH | — | — |
| info_and_appearance | FRESH, but the snapshot fails `banner_set` | same | same | owner uploads the banner and icon and pastes the About | d |
| options | FRESH | FRESH | FRESH | — | — |
| policy_settings | FRESH, but fails `policy_shipping_set` and `policy_additional_unset` | same | same | owner pastes the six policies | d |
| digital_files | NO_COLLECTOR (only 2 of the 10 current releases ever built; none certified at the code's version) | NO_COLLECTOR | NO_EVIDENCE at first. Once the halts clear, R3/R5 certify the releases and `assets.build` keeps their PDFs, and it becomes **FRESH** | deploy; then the chain runs (hours) | b |
| taxonomy_and_attributes | NO_COLLECTOR (tree read, 3065 nodes, 0 pattern∧crochet nodes) | NO_COLLECTOR (property route live) | FAILING until every Launch-0 profile is CHOSEN | b997efd's refresh reads the 2 property schemas (§3a); CHOSEN only if Etsy's schema offers "Crochet"; run `tests/verify_w4_firstsale_taxonomy_live.py` | b (+ Etsy's answer) |

### 3a. Etsy's real taxonomy names (production, 2026-10-21T00:01Z)

The first `name_evidence` arrived on the daily refresh (`/api/audit?action=etsy.taxonomy_refreshed`):

| field | what Etsy's tree contains |
|---|---|
| `pattern_named` | `Craft Supplies & Tools > Patterns & How To`; `... > Patterns & How To > Patterns & Blueprints` |
| `crochet_named` | `Art & Collectibles > Fiber Arts > Crochet` (finished art, not patterns); `Craft Supplies & Tools > Tools & Equipment > Tools > Hooking > Crochet Hooks` |
| children of `Patterns & How To` | Books & Magazines, Craft Machine Files, Critiques & Shop Tutorials, Kits, Patterns & Blueprints, Recipes, Tutorials |
| children of `Patterns & Blueprints` | none (a leaf) |

**Crochet is not a node anywhere under patterns.** It can only be a property of the pattern
node, which is FIRSTSALE's property route.

**The matcher was run unchanged on a structural replica of exactly these names.**
- The ids in the replica are placeholders. The real ids are not public, and none was used or
  invented for any listing.
- Every one of the 8 reported categories lands on
  **`Craft Supplies & Tools > Patterns & How To > Patterns & Blueprints`**, by the
  property route.
- The status is UNKNOWN because no schema is stored yet.
- `property_candidates` asks for exactly 2 schema reads: that node and its parent. That is well
  inside `MAX_PROPERTY_READS` = 40.
- **No matcher correction is needed.**

**What decides CHOSEN versus UNKNOWN** is Etsy's own `getPropertiesByTaxonomyId` answer for that
node. It is read only by b997efd's refresh, after deploy plus one daily run.
- If the schema offers the value "Crochet", all 10 releases are CHOSEN on that node, and
  `taxonomy_and_attributes` can read FRESH.
- If it does not, the category stays UNKNOWN, honestly. The fallback is an owner reading of
  the category picker in Shop Manager; it is not a guess.

## 4. Gap table: the 8 products (10 releases)

| product (code release) | in production today | after b997efd | after the LISTREADY release (local rehearsal, `evidence_FIRSTSALE/first_sale.md`) | remaining |
|---|---|---|---|---|
| nursery-nesting-baskets (market-basket-small/medium/large@1.2.0) | never drafted; legacy `market-basket-trio` halted | unchanged (no seeding) | drafted by R5, then certified and chained | B2, B3, sample, grant |
| cloudline-baby-blanket@1.2.0 | `assets.built` 10-11; halted by the P0 | halted | certified, chain completes | B2, B3, sample, grant |
| hexagon-coaster-set@1.2.0 | never drafted (legacy `hexie-coaster-set`) | unchanged | R5 then certified | B2, B3, sample, grant |
| nordic-star-ornaments@1.5.0 | 1.4.0 certified; 1.5.0 `gate.halted` 10-20 | halted | R3 retries once the halts clear | B2, B3, sample, grant |
| winter-village-graphghan@1.3.0 | `gate.halted` 10-12 | halted | R3 retries | B2, B3, sample, grant |
| nordic-forest-mosaic-throw-baby@1.3.0 | never drafted | unchanged | R5 | B2, B3, sample, grant |
| mosaic-placemat-pair@1.4.0 | 1.3.0 certified; 1.4.0 `gate.halted` 10-20 | halted | R3 | B2, B3, sample, grant |
| housewarming-key-basket@0.1.0 | never drafted | unchanged | R5 | B2, B3, sample, grant |

**Per-product gates after the release, as in the local rehearsal (all 8 the same):**
- **PASS:** certification, Product Truth, image truth, listing, price, disclosure,
  image-upload payload, durable delivery.
- **UNKNOWN:** etsy_category (B2) and etsy_upload_confirmed.
- **FAIL:** seo (cause: B2 only), vision_review (B3), physical_sample, publication_grant.

**Honest limits:**
- **What the fix will clear in production is not known yet.** Production's per-artefact rows
  could not be read. The 299 stale rows are mostly older-release artefacts, which R1 makes
  superseded. Any that are genuinely stale against their own release (re-certified documents)
  stay halting, correctly, and are rebuilt through the chain.
- **The P0 resolves only when genuine staleness falls below the threshold.** That needs fewer
  than 3 products, or under 50% of the catalogue, still halted. Read `/api/incidents` after the
  first sentinel run on the new release.
- **The retry depends on an open halt clearing.** R3 retries only once no halt remains on the
  product, including the P0.
- **Seeding adds work.** R5 seeds 10 drafts on the first whole-catalogue `chain.rebuild`. Each
  certified release then runs the normal chain. That is real compute, but no spend: assets are
  deterministic and paid vision stays behind its gate.

## 5. Shortest path to 8 sellable listings

| # | step | who | cost | minutes |
|---|---|---|---|---|
| 1 | Integrate `claude/w4-LISTREADY` (b997efd + FIRSTSALE2 + R1/R3/R4/R5) into the next release candidate; run the full suite | integrator | CA$0 | the suite run |
| 2 | **Owner: approve the deploy** of that candidate (b997efd's content is included) | owner | CA$0 | 5 |
| 3 | After deploy: first hourly `ops.sentinel` (halts clear), then `chain.rebuild` (R3 retries, R5 seeds). The chain certifies and builds the 10 releases; `launch.readiness` keeps the PDFs (`digital_files` FRESH) | company | CA$0 | about 1 to 6 h |
| 4 | Next daily taxonomy refresh (about 00:0xZ) reads the 2 property schemas (§3a); run `verify_w4_firstsale_taxonomy_live.py`. CHOSEN if Etsy's schema offers "Crochet"; otherwise UNKNOWN and an owner reading of the category picker | company (Etsy's answer decides) | CA$0 | 1 day |
| 5 | Owner: shop settings in Shop Manager (banner and icon, About, six policies, payout/KYC/tax confirm) | owner | CA$0 | 20 + 25 + 15 = 60 |
| 6 | Owner: POST the dated `messages` and `legal_and_tax` readings (`/api/etsy/shop-observation`) | owner | CA$0 for the reading; the tax position's own ceiling is CA$250 | 10 + 30 |
| 7 | **Owner: approve the funded B3 vision review** (§6) | owner | **max CA$7.07** | 5 |
| 8 | Physical sample of one Launch-0 product (gauge and size claims) | tester / owner | yarn plus tester time (UNKNOWN) | 10 to arrange |
| 9 | Owner: accept the listing fees and grant publication (phase + sealed draft grant) | owner | US$0.20 per listing, US$2.00 for 10 (about CA$2.83) | 2 + 15 |

## 6. Paid calls needed

**B3, the independent frame review** (`assets.frame_review`, `runtime/release._review_frames`):
- Each frame gets one vision call. A photographic frame gets two: describe, then realism.
- **Task:** `asset_inspection`, routed to `claude-sonnet-5` at US$3 / US$15 per Mtok.
- **Estimate inputs:** `gateway.anthropic.estimate_cad` uses the padded estimate (×1.25), USD→CAD 1.4154 and an image token estimate of 6000.

| call | per-call maximum |
|---|---|
| describe (500 output tokens max) | CA$0.0461 |
| realism (900 output tokens max) | CA$0.0563 |
| one frame, both calls | **CA$0.1024** |

| scope | maximum |
|---|---|
| 59 stored listing frames for 10 releases | **CA$6.04** |
| upper bound: all 69 upload images, both calls each | **CA$7.07** |

Actual usage is typically about a third of the padded estimate.

**Constraints, all enforced in code and unchanged here:**
- **Month:** the CA$100 model ceiling has CA$64.78 spent so far (`/api/verify`).
- **Day:** `quality_director`'s daily ceiling is **CA$1.00**. At the padded estimate that is about
  10 frames a day, so the review spreads over about 6 to 7 days unless the owner raises that
  ceiling. Raising it is an owner decision; nothing here proposes a change.
- **Re-review:** a frame review binds to the exact stored frame bytes. Any rebuild of a frame
  needs a re-review at the same per-frame cost.

No other paid call is on the path. Assets, PDFs, taxonomy reads and certification are
deterministic or free GETs.

## 7. Tests (testslot, venv-integ4, focused only, no full suite)

### Run 1, on 8e5f149 (R1, R3, R4, R5)

| suite | result |
|---|---|
| test_w4_listready (new) | 11/11 |
| **Required set:** test_vacuity 8, test_launch 28, test_cost_governance_wave2 39, test_search_hero_publish 4, test_cert_listing_frames 6 | all rc=0 |
| test_v11_autonomy_timeline | 5 + 1 FAIL at first: the committed autonomy map had 62 follow-on edges, live 64 (my two new edges, `retry_halted` and `seed_launch0`). The map was regenerated by its own generator (57f53ba, only those two edges plus a timestamp). Re-run: **6/6** |
| Sentinel, provenance, incidents: test_artefacts 23, test_cert_provenance 12, test_provenance_backfill 12, test_provenance_write_path 19, test_rebuild_graph 10, test_w3_k7_ops_truth 16, test_w4_owner_incidents 6, test_w4_fmgate_rebuild_key 4, test_w4_auto_provenance_concurrency 3, test_chaos 38, test_w4_laurafix_truncation 8 | all rc=0 |
| Pipeline, Gate E, chain: test_acceptance_gates 23, test_shadow 10, test_cert_rebuild_chain 10, test_cert_unique_value 6, test_cert_growth_ops 13, test_cert_improve_wave 24, test_w4_placemat_reprice 4, test_reachability 11, test_cert_wiring 16, test_deploy 32, test_protected_bands 6, test_rehearsal_stall 4, test_w4_auto_status 11, test_w4_autonomy_idle_departments 10, test_video 16, test_w4_visnext_frames 7 | all rc=0 |
| release_gates and first sale: test_cert_publish_gates 18, test_w4_firstsale2_surfaces 7, test_w4_firstsale_view 5, test_w4_firstsale_deliverables 6, test_w4_etsysurf 8, test_etsy_surfaces 53 | all rc=0 |
| **test_product_run** | **35 + 1 FAIL**, 3890 s: `test_a_stale_listing_is_rebuilt_even_when_its_release_is_unchanged` |

**The test_product_run failure was caused by this branch, and is fixed after run 1 without
changing the test.**
- That test drains a whole-catalogue `chain.rebuild`. R5 then seeded and certified all ten
  Launch-0 releases in the test database, and that is also why the suite took 3890 s.
- The second rebuild then reported 9 `redrafted ... design`. That exposed a latent false
  positive in `chain.rebuild`'s design comparison (tuples against stored JSON lists).
- **Fixed:**
  - the comparison is normalised through JSON;
  - R5 now seeds one release per run, which bounds the extra work a test drain or a
    production hour takes on.
- `test_w4_listready`'s seeding test was updated to that rule: one per run, in listing order,
  all nine eventually, none twice.

### Not re-run after the run-1 fixes (coordinator hold on test runs)

These changes have not been run under test yet:
- the `stale_design` JSON normalisation;
- `SEED_PER_RUN`;
- the updated `test_w4_listready` seeding test.

The syntax checks pass. **Before integration, re-run:**
- test_w4_listready
- test_product_run
- test_cert_rebuild_chain
- test_acceptance_gates
- test_shadow
- test_v11_autonomy_timeline (the map's edges are unchanged)
- the required set

**One more cost to weigh:** suites that drain a whole-catalogue `chain.rebuild` now also build
one Launch-0 product per rebuild. They were slower in run 1:
- test_acceptance_gates: 1338 s
- test_shadow: 914 s
- test_chaos: 1040 s
- test_cert_wiring: 988 s
- test_deploy: 1204 s

There were no baselines to compare against on this machine, so how much of that is from this
branch is UNKNOWN. If it is material, the integrator's alternative is a dedicated daily
`launch0.seed` cadence job. That needs agent permission, charter, authority and autonomy-map
entries, and was not done blind.

## 8. The owner-approved image review batch (D-W4-LAUNCH-VISION-BATCH, 2026-10-21)

**The approval, as relayed:**
- up to **CA$7.07 in total** for the paid independent review of the 59–69 Launch-0 listing images;
- for this batch only, `quality_director`'s daily ceiling raised to **CA$8.00**, reverting to CA$1.00 by itself;
- the CA$100 month is unchanged;
- nothing else is authorised;
- SHADOW mode stays, nothing is published, and no Etsy fees are incurred.

**The batch record.** `finance/launch_review.py` holds the tables `launch_review_batches` and `launch_review_calls`. They
are created on first use (the `experiments.controlled` pattern) and change no existing table.

| field | value |
|---|---|
| batch | `launch_image_review_2026_10` |
| approval reference | DECISION_LOG `D-W4-LAUNCH-VISION-BATCH` |
| total cap | CA$7.07 |
| agent | `quality_director` |
| batch daily cap | CA$8.00, applied to this batch's own review calls only |
| frame scope | every stored listing frame of the 10 Launch-0 releases at the code's versions, by sha256, fixed at activation (activation refuses until every release has frames) |
| expiry | **14 days** after activation |

**What every batch call is checked against.** All checks run inside `gateway.anthropic.check_budget_cad`'s budget lock, in the step that writes the reservation:
1. the CA$100 month: unchanged, and still first;
2. the batch is open: not completed, not expired, not exhausted, re-read under the lock;
3. the release's stored frames are exactly the scoped frames;
4. the release's call allowance: 2 per frame, plus 1 for the hero's grid identification;
5. the batch total: committed plus this estimate is at most CA$7.07;
6. the batch day: today's batch spend plus this estimate is at most CA$8.00;
7. the agent's own day is held to CA$8.00 for this call only.

**Calls outside the batch** are not in a `reviewing(...)` scope, so they read the registry's unchanged **CA$1.00**. The registry value is never written.

**Batch accounting.** The batch counts each call at its padded estimate, written in the same locked step as the reservation. A call whose bill is unknown is never counted at less.

**Closing, in code.** The batch closes:
- **completed** when every scoped release has been reviewed;
- **expired** after 14 days;
- **exhausted** when no further call fits under CA$7.07.

Closing is audited (`launch_review.closed`). From then on the effective ceiling is CA$1.00 and any further batch call is refused before it is sent.

**Results.** The review is the existing `_review_frames`, run by `assets.build`, and its result is the existing `assets.frame_review` row.
- The B3 gate (`frame_review_state`) is unchanged.
- A refused or failed call leaves the frame undescribed, so it reads unreviewed or unjudged: UNKNOWN, never PASS.
- Each scoped release is queued once, with `max_attempts=1`. A release found mid-review from an earlier attempt is marked `interrupted` and is not resent.

**Cost, corrected.** The hero's grid-identification call (+CA$0.0461 per hero) was missing from §6.
- Worst case for the 59 stored frames: 10 heroes × CA$0.1485 + 49 × CA$0.1024 = **CA$6.50**, within CA$7.07.
- The hard cap stops at CA$7.07 regardless.

**Activation, by the owner, from the phone, after the listings release is deployed and the Launch-0 frames are built.** Nothing runs before then.
1. Open the Command Center (`/cc/`) and go to **Completion**. Find the **Launch image review** card.
2. If the card says "Step-up needed first.", tap **Step up** and enter the passphrase and TOTP.
3. Tap **Activate** and confirm. The card then shows `open`, the frames in scope, CA$ committed of CA$7.07, the reviewer's
   daily ceiling now (CA$8.00 while open, CA$1.00 after) and the expiry.

The card calls the same `POST /api/cc/launch-review/activate` through the Command Center's shared CSRF, nonce and step-up
flow.

**Activate is disabled, with the reason shown, whenever the server would refuse:**
- "Step-up needed first.";
- "Already active." (or "Already used (completed / expired / exhausted).");
- "Frames are not yet built for every Launch-0 release (… missing)".

The frames reason comes from `GET /api/cc/launch-review`'s read-only `frames_ready` / `missing_releases`, which run the same
scope check that activation runs. The server re-checks every rule on the POST. The server rules and their tests are unchanged.

**PWA tests:**
- `tests/test_w4_launch_review_card.py`, 6/6. Static checks, plus the reason function run under node.
- test_v11_pwa_static 82/82.
- test_v11_pwa_browser 219/0 (new check: the card renders with Activate disabled and its reason).
- test_w4_firstsale_view 5/5.

**Tests:** `tests/test_w4_launch_review.py`, 13/13:
- activation needs step-up and runs once;
- activation is refused on a partial scope;
- outside the batch, the ceiling is still CA$1.00;
- every batch call is reserved first and counted;
- the total is enforced, and nothing is sent or reserved after exhaustion;
- the batch day is enforced;
- the month still binds, and CA$100 is unchanged;
- out-of-scope frames and other releases are refused;
- the per-release call allowance holds;
- the ceiling reverts on completion, on expiry and on exhaustion;
- a refused call reaches no provider, and the frame is not `clear`;
- the run queues each release once and never resends an interrupted one.

## 9. Remaining owner actions for the first sale

| # | action | why | max cost | minutes | consequence of waiting |
|---|---|---|---|---|---|
| 1 | Approve the deploy of the listings release (b997efd + FIRSTSALE2 + LISTREADY), after its certification suite passes | Production cannot certify anything until R1/R3/R5 run there; a deploy is owner-approved | CA$0 | 5 | No Launch-0 release certifies, so there is no listing |
| 2 | After deploy, once the Launch-0 frames are built: activate the image review (§8) | B3: every frame is unreviewed; the review is paid | CA$7.07 (approved) | 5 | `vision_review` stays FAIL for all 8 products |
| 3 | Shop Manager > Info & appearance: banner and icon, paste the About from `brand/storefront.ABOUT` | No image or About write endpoint; the live snapshot fails `banner_set` | CA$0 | 20 | The storefront reads as abandoned; `info_and_appearance` stays failing |
| 4 | Shop Manager > Policies: paste the six policies from `commerce.shop_package.policies()` | Only `policy_additional` is writable; the snapshot fails `policy_shipping_set` and `policy_additional_unset` | CA$0 | 25 | Blank policies at the first sale |
| 5 | Confirm payout, identity and tax in Shop Manager > Payment settings | KYC and banking are the account holder's alone | CA$0 | 15 | No payout; publishing is blocked |
| 6 | POST the dated `legal_and_tax` reading (`identity_verified`, `tax_position`, `decided_on`) at `/api/etsy/shop-observation` | No API exposes it; FIRSTSALE2's collector reads the owner's reading | CA$0 to record; the GST/HST position itself has a CA$250 registry ceiling | 30 | `legal_and_tax` stays NO_EVIDENCE, so first-sale readiness cannot pass |
| 7 | POST the dated `messages` reading (`notifications_inbox`, `reply_window_hours`) | Etsy has no messaging API | CA$0 | 10 | `messages` stays NO_EVIDENCE; buyer messages go unread |
| 8 | Physical sample: a tester crochets one Launch-0 product and records gauge and size | Gauge and size claims are UNRESOLVED without a bound sample | yarn plus tester time (UNKNOWN; not approved here) | 10 to arrange | `physical_sample` FAIL; the first-customer gate does not pass |
| 9 | Accept the listing fees, choose the go-live phase and grant draft publication for the first product(s) | Leaving SHADOW and paying Etsy is the owner's alone; it is also the only way to confirm the upload (B4) | US$0.20 per listing, US$2.00 for 10 (about CA$2.83) | 17 | No listing exists, so there is no first sale |

### Run 2 (2026-10-21, on e08ea56 with the batch; all through testslot with venv-integ4)

All 28 suites passed (rc=0, 0 FAIL). Counts:

| suites | results |
|---|---|
| this branch | test_w4_launch_review 13, test_w4_listready 11 (re-runs d45e033's untested seeding and JSON-normalisation changes) |
| required set | test_vacuity 8, test_launch 28, test_cost_governance_wave2 39, test_search_hero_publish 4, test_cert_listing_frames 6, test_v11_autonomy_timeline 6 |
| spend | test_spend_policy 24, test_rc1_spend 20, test_w4_spend_paid_discipline 13, test_model_spend_paths 12, test_w3_spend_paid_calls 8, test_w3_spend_gateway_w8 5, test_spend_governance 36, test_w4_plact 8, test_w4_pl_budget 5, test_w4_laura1_budget 4 |
| routes and security | test_route_auth_default_deny 7, test_customer_data_auth 9, test_w4_controlled_experiments 10, test_w4_integ4_secfixes 12, test_w4_smoke 10 |
| sentinel, chain, gates | test_artefacts 23, test_rebuild_graph 10, test_cert_publish_gates 18, test_cert_rebuild_chain 10, test_shadow 10 |

**Not run, on the coordinator's instruction:** test_product_run, test_acceptance_gates and test_cert_wiring. test_product_run's run-1 failure is fixed in d45e033 and is still to be re-run.

## 10. Independent review of d45e033 (BLOCKER): what was fixed (a46ac23)

The review is `INDEPENDENT_SECREVIEW_LISTREADY.md` on `claude/w4-SECREVIEW-LISTREADY`.

**Every new regression test reproduces the review's scenario.** I ran the new tests against the pre-fix source (9a4f99d)
and every one of them fails there. The exceptions, by design:
- F6 and F8 add coverage of behaviour that was already correct;
- the product-independence tests confirm behaviour that was already correct.

| # | fix | test (`test_w4_listready` unless named) | fails before |
|---|---|---|---|
| F1 BLOCKER | `built_from_version` links only an explicit versioned key (`slug@version`) to a certified release. Unversioned or ambiguous artefacts, including all marketing copy, are judged against the current release, so copy written from an older release is **STALE** and halting. R4 lets its rebuild run while publication still refuses. | `test_live_marketing_copy_written_from_an_older_release_is_stale_not_superseded` (the review's appendix A: stale, halted, outstanding, rebuild flag; re-recorded from 1.1.0 it is FRESH and the incident clears); `test_no_unversioned_artefact_is_ever_superseded` | yes |
| F2 HIGH | "Newest" is the highest **certified version** (`ops.artefacts.newest_version`: integer tuples, `1.10.0 > 1.9.0`), never the last-inserted row. This applies in `current_from_db`, the F-115 lookup, `superseded_release`, `retry_halted` and `seed_launch0`. Versions that cannot be ordered fail closed: nothing reads superseded, and publication refuses. | `test_newest_is_the_highest_certified_version_not_the_last_row` (inserted out of order: 1.1.0, then 1.0.0, the review's appendix B); `test_versions_that_cannot_be_ordered_supersede_nothing_and_refuse_publication` | yes |
| F3 MEDIUM | `retry_halted` skips the retry, recording `certify.retry_skipped`, when: the recorded CIR is not the code's current design for that slug@version (`design_moved`), or a newer certified release exists (`superseded_by_newer`). `seed_launch0` does not seed a release older than a certified one. | `test_f3_a_halted_release_whose_design_moved_is_not_retried`; `test_f2_f3_a_halted_release_with_a_newer_certified_release_is_not_retried` | yes |
| F5 LOW | No retry is queued while a `gate.certify` for the same slug@version is pending or running. A certify job whose identical release (same CIR, same document version) was certified by another job after it was queued stops with `gate.certify_duplicate`, so the release is certified once. The Gate E halt check is unchanged and runs first. | `test_f5_no_retry_while_a_certify_for_the_same_release_is_in_flight`; `test_f5_a_retry_and_a_normal_certify_certify_the_release_once` (1 `gate.certified`, no `gate.recertified`, 1 PatternVersion) | yes |
| F4 LOW | `outstanding_only_marketing` also requires no unreviewed platform-policy change (#39). The marketing rebuild exception never waives a non-staleness reason. | `test_f4_the_marketing_rebuild_exception_never_waives_an_unreviewed_policy_change` | yes |
| F6 LOW | A behavioural test of the `chain.rebuild` comparison: an unchanged design stored as JSON is not redrafted; the same design one row short is. `test_etsy_surfaces`'s edited assertion now checks `orders_ingest.gate(db)`'s own answer (missing `transactions_r`: "Only the owner … browser … reauthorise_transactions_r"), not source text. | `test_f6_chain_rebuild_redrafts_a_changed_design_and_not_an_unchanged_one`; `test_etsy_surfaces` 53/53 | coverage |
| F7 LOW | The `messages` and `legal_and_tax` readings are the owner's own attestation. `POST /api/etsy/shop-observation` (operator credential) refuses them with 403 `OWNER_SESSION_REQUIRED`. They are accepted at `POST /api/cc/etsy/shop-observation` behind the owner session and step-up, with `recorded_by` set to the signed-in owner and not taken from the body. A future `decided_on` is refused. | `test_w4_owner_observations` 3/3; `test_k8_shop_cx` 17/17 | yes |
| F8 INFO | Every Etsy write is enumerated and gated (below). | `test_f8_every_etsy_write_is_authorised_at_the_client_boundary`; `test_f8_every_etsy_write_call_site_is_classified_and_release_writes_pass_for_publish` | audit |

**F7 and the owner's existing flow.** I kept the operator route for the non-attesting pages: shared access, apps, policy
violations and options (covered by `test_k8_shop_cx`). The owner works from a phone, so the Completion tab has a new
**Shop Manager readings** card. It records both readings through the step-up route; the code is in `views/_shop_readings.js`
and the offline shell is now v21. Tests: `test_w4_launch_review_card` (now 7) and `test_v11_pwa_browser` 219/0.

### Every Etsy write path (owner directive)

**At the client.** `EtsyClient` has seven mutating methods: `create_draft`, `_upload_image` / `upload_image`,
`_attach_file` / `attach_file`, `set_listing_property`, `update_listing`, `delete_listing` and `activate`.
- Each public writer checks `_authorise_write`. That means either the owner's sealed, content-bound grant re-verified
  against the live phase, or the draft-only shadow lane in a non-publishing phase.
- The private writers are reached only through writers that check.
- `activate` additionally needs the phase, the grant and a per-call launch authorisation.
- `update_listing` refuses `price` and `state`.

**Call sites.** Every call site of those methods across `src/`, with any receiver:

| call site | gate |
|---|---|
| `runtime/pipeline._publish_and_read_back` (create, images, files, properties) | reached only from `_publish_guarded` and then `handle_store_publish`, after `_release_gates` → `release_gates.for_publish` |
| `runtime/pipeline.handle_store_activate` (state → active, the fee) | after `_release_gates` → `for_publish`, plus the launch authorisation |
| `integrations/etsy.publish` | the client's own composite; the grant is verified first |
| `integrations/etsy_probe`, `integrations/etsy_exercise` | the write-path exercise draft: shadow lane only, never a release, activation asserted refused, deleted |
| `commerce/listing_rollback.execute` | owner-grant restore of an existing listing's fields; publishing phase only; no caller in `src` today |

`for_publish` runs these checks:
- `superseded_release` (the current-version check);
- staleness and Gate E halts;
- the platform policy (#39);
- the listing set (Product Truth, image truth);
- search;
- standards;
- originality;
- `eligibility.product_publication` (Launch-0 first-customer scope);
- the plan price.

**No other write path exists.** There is no renewal write: listings are created with Etsy's own renewal setting, and
`renewal_decision` is advice only. There is no inventory write and no price write. A new write site fails the F8 test until
it is classified.

**Gaps found: none.** One observation: `listing_rollback.execute` checks the owner grant and phase but not `for_publish`. It
restores a listing's own previous field values and has no caller, so it is recorded here rather than changed. Wiring it to
any caller should add `for_publish`.

### Product independence (owner directive)

A failure in one product stops only that product:
- A customer-defect P1 on product A halts A, and product B still certifies.
- A stale artefact on A blocks A's publication only; B's staleness is clear.
- Below the company-wide threshold (2 of 4 products stale), nothing spreads.
- One Launch-0 release's dead draft does not stall the seeding of the next.

Tests: `test_a_failure_in_one_product_does_not_stop_an_unrelated_compliant_product` and
`test_one_releases_failure_does_not_stall_recovery_of_the_others`.

**What still reaches every product.** Only the designed company-wide safety gates, all unchanged:
- `systemic-halt:publication`: an integrity failure, or one failure family on 3 or more products and 50% or more of the
  catalogue;
- an unreviewed platform-policy change (#39);
- the SHADOW phase.

R1 and F1 mean stale-artefact incidents now count only genuine staleness, so the systemic halt trips only on real
widespread staleness.

### Run 3 (2026-10-21, on a46ac23 and c97ccf1, testslot + venv-integ4, one suite at a time)

All suites pass, after the two fixes noted under the table. Counts:

| suites | results |
|---|---|
| this branch | test_w4_listready 24, test_w4_launch_review 13, test_w4_owner_observations 3, test_w4_launch_review_card 7 |
| required set | test_vacuity 8, test_launch 28, test_cost_governance_wave2 39, test_search_hero_publish 4, test_cert_listing_frames 6, test_v11_autonomy_timeline 6 |
| sentinel and incidents | test_artefacts 23, test_rebuild_graph 10, test_provenance_write_path 19, test_w3_k7_ops_truth 16, test_w4_owner_incidents 6 |
| chain and gates | test_cert_publish_gates 18, test_cert_rebuild_chain 10, test_shadow 10 |
| Etsy surfaces | test_k8_shop_cx 17, test_etsy_surfaces 53, test_w4_firstsale2_surfaces 7, test_w4_etsysurf 8 |
| spend, routes, PWA | test_rc1_spend 20, test_model_spend_paths 12, test_route_auth_default_deny 7, test_customer_data_auth 9, test_v11_pwa_static 82, test_v11_pwa_browser 219/0 |
| long suites, once each | **test_product_run 36/36** (2371 s; the run-1 failure is fixed); **test_acceptance_gates 23/23** (1204 s) |

**Two failures in this run, both caused by this branch and both fixed in c97ccf1:**
- **test_vacuity** flagged a loop over a possibly empty iterable in my card test. A length assertion was added.
- **test_cost_governance_wave2** failed 4 tests: `gate.certified` is now read by name (F5) with no retention decision. A
  `windowed` decision was recorded in `ops.retention.KNOWN_READ_ACTIONS`.

Both suites were re-run after the fix: test_vacuity 8/8, test_cost_governance_wave2 39/39.

**Not run:** test_cert_wiring (still on hold) and any full suite.

## 11. Delta review of b9137b5 (NO BLOCKER): fixes and recorded INFO items

The review is `INDEPENDENT_SECREVIEW_LISTREADY_b9137b5.md` on `claude/w4-SECREVIEW-LISTREADY-b9137b5`. It closes F1 and F2.

| # | fix | test |
|---|---|---|
| N1 MEDIUM | **One definition of "current release":** `ops.artefacts.newest_release` / `newest_certified`, the highest certified version (semver), failing closed. **Used by:** `teardown.enforce.current_release` (it feeds `for_publish` via `standards_gate`), `_targeted_rebuild`, `inventory.chain_evidence`, and the display readers (`cc readers`, `ask`, `benchmark_matrix`, `teardown.lab`). **Removed at the source:** `gate.certify` refuses a *new* certification of a version older than a certified one, audited as `gate.certify_older_than_newest`; re-certifying an existing version is still allowed. `approvals.py` keeps id order because it is a list of releases, not a "current" pick. | `test_n1_*` in `test_w4_listready` (5). Each uses an out-of-order state (1.1.0 certified, then 1.0.0): current release, targeted rebuild, chain evidence, the display readers, and the refused older certification |
| N2 LOW | Activation requires the `image_vision` gate to be open, and the card shows why when it is not. A release is `done` only when a batch call was reserved for it; otherwise it goes back to `pending`, with the reason. If every release finishes at CA$0, the batch closes as **`unused`** (not completed), and it can be re-activated within its original expiry. A `queued` release whose batch build ended before the review is requeued (attempt key `:2`, …). The owner can tap **Resume** (step-up) to run pending releases again under the same caps. The card shows "releases reviewed N of M". | `test_n2_*` in `test_w4_launch_review` (4); `test_w4_launch_review_card` (reason cases now include the vision gate and `unused`) |
| N3 LOW | Each `ops.sentinel` run raises an owner P2, `listing.superseded_live:<slug>@<version>`, for every **live** listing of a release older than the newest certified one. It is non-halting, so the newest release is unaffected. Its remediation path is the owner's: update the listing in place or deactivate it. It is restated, never duplicated, and resolved when no such listing remains. | `test_n3_a_live_listing_of_a_superseded_release_raises_an_owner_visible_p2` |

**INFO items, recorded and left unchanged as instructed.**

| # | what the review found | why it stands |
|---|---|---|
| N4 | A batch run is a full `assets.build`: it re-renders the frames and re-queues the downstream chain. | The scope check fails closed if the bytes change. |
| N5 | While the batch is open, batch spend counts against `quality_director`'s agent-day, so that agent's non-batch calls (still at CA$1.00) are refused for the rest of that UTC day. | This is correct; it starves other work only for the day of the batch. |
| N6 | `assets.launch_review` was added to `quality_director`'s allowed job types, `JOB_CLASS`, `OWNER_ONE_SHOTS` and `JOB_BANDS`. | The ceiling itself is unchanged. |
| N7 | `grant_in` trusts any `assets.build` job whose inputs carry `launch_review_batch`. | No route accepts arbitrary job inputs, and the caps still bind. |
| N8 | `GET /api/cc/launch-review` writes: it creates the tables and may close the batch with an audit row. `activate` checks and then inserts, with no unique constraint. | The nonce and step-up make a double insert impractical, and the caps hold even if one happened. |
| N9 | The F8 write-path tests match call sites by method name in the AST, so an aliased or `getattr` call would not be listed. | The runtime `_authorise_write` boundary is the real control. |
