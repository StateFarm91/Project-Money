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
| **R5** | `runtime/release_recovery.seed_launch0`, called by whole-catalogue `chain.rebuild` | `cir.draft` for every Launch-0 release whose code version is not certified. The key is `launch0-seed:<slug>:<version>:<fingerprint>:d<DOC>`. Drafting, compiling and certifying are the normal jobs with their normal gates. | none |

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

See §7a, filled in from the run.
