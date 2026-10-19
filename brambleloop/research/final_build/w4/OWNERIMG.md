# OWNERIMG: autonomous listing-image production, with owner upload as a thin fallback

- **Branch:** `claude/w4-OWNERIMG`. It is based on `origin/claude/w4-INTEG2` 9c3812bd, plus
  `w4-BRANDRULE` (D-W4-LAURA-OUTFIT, D-W4-LAURA-FLUX3, the wrap experiment record) and `w4-VISREF`.
- **Production state:** 1b21e81 (SHADOW).
- **Scope:** offline. No provider was called, nothing was spent, no credential was changed,
  nothing was deployed and nothing was written to production.
- **Rulings applied, in order:**
  1. the original brief (owner-assisted intake);
  2. the owner redirect: autonomous production is primary, and the upload is a thin fallback
     that uses the same gates;
  3. D-W4-LAURA-FLUX3 (`spec/12_…`);
  4. the wrap experiment's failure codes.
- **Not touched:** `gateway/images.py` and the provider adapters, which W-FLUXAPI owns;
  `listing_assets.py`, `render_contract` and disclosed-render sizing, which W-PRODREADY owns;
  and W-INTEG3's branch.

## 0. What was reused (survey)

| Need | Reused | How |
|---|---|---|
| Durable workflow | `queue.durable.JobQueue`, `runtime.worker` handlers and idempotency keys, the `publishing` agent and its CA$2.00/day ceiling | Each stage is one job of `visual.image_production`. The next stage is enqueued under `imgprod:<slug>@<ver>@<release>:<stage>[:<round>]`. No new engine. |
| Spend bounds | `visual.spend_plan` (build/guard), the `image_generation` gate (`gallery.gates_now`), W-FLUXAPI's `reserve_render` | One per-gallery plan: 12 calls and CA$2.00 at most. A paid generator is refused while the gate is closed. |
| Byte storage | `core.artifacts.ArtifactStore.put(keep=…)` | Bytes are stored unchanged, keyed by sha256, with a durable DB copy. |
| Release binding | `release_gates._release` (certified `PatternVersion`) and `pipeline._certified_pdf_hashes` (the certified PDF hash, never a rebuild; VISREF §0 #7) | Used by `candidate_gates.binding`. |
| Photo intake | `physical_upgrade.intake` | Unchanged as the camera-photo path. An owner AI image never goes through it. `plan_upgrade` now takes a declared `role` (`proof` or `lifestyle`). |
| `owned_photography` refusal, F-852 | `eligibility.may_export` (`GENERATED_MEDIA`), `asset_truth` `ASSET_CONCEPT_AS_HERO` | Kept, and enforced through the shared publication verdict. |
| Identity | `identity_gate.assess`, `canonical.CURRENT_REFERENCE_HASHES`, `canonical.verify`, `canonical.reference_file` | Laura-only check. All three references must validate by sha256, or generation is refused. |
| Role checks | `eligibility.Candidate`/`may_serve`/`JOB_PURPOSES`, `frame_role.classify` (an unlisted frame is photographic) | The role check in `candidate_gates`. |
| Gallery set | `eligibility.check_set`, `gallery_jobs_for` | `image_production.readiness`. |
| Product Truth | `product_authority.structural_floor`, `compose.lifestyle_evidence` (VISREF) | `RealJudges.product_truth`. A generated frame reads UNKNOWN. A lifestyle frame built from pattern-derived references FAILs ("informational"). |
| Provenance kinds (#36) | `buyer_trust` (generated = `concept_illustration`, never proof), `asset_truth._APPROPRIATED` | Kinds `ai_generated_autonomous`, `ai_generated_owner_submitted` and `ai_generated_owner_manual`. None is ever a photograph. |
| Disclosure | `eligibility.honesty_label` (CONCEPT_LABEL) | Disclosure check. The Etsy reading stays a publication blocker. |
| Notifications | `app.command_center.notifications.candidates/refresh` (deduplicated) | A new source for two cases: ready for review, and blocked after the permitted attempts. |
| Prompt versioning | `improve.league.incumbent_payload(kind="prompt")` | `prompt_version()`. A brief changes only through a promoted league version. |
| CC auth | `/api/cc` `auth.gate` (session, CSRF, nonce, timestamp), `require_stepup` | New routes. Approval needs a step-up. |

## 1. Architecture: one set of gates, two entry points

```
assets.build (certified + usable disclosed set) ──trigger once per slug@ver@release──▶
visual.image_production  [12 stages, each a job, each recorded on image_production_runs]
   │  generator interface (W-FLUXAPI registers; stub in tests)
   ▼
candidate_gates.evaluate  ◀── publish/owner_images.intake (owner fallback, CLI or CC upload)
   ▼
image_candidates (learning + provenance) ─▶ readiness / gallery assembly ─▶ owner card ─▶ approve (re-checks gates)
```

- `candidate_gates.evaluate` never reads the generation method. A test asserts that identical
  evidence gives identical checks and an identical publication verdict.
- **Checks:** binding, provenance, quality, role, product_truth, identity, body_proportions,
  anatomy, realism, disclosure, outfit and outfit_consistency. Each reads
  PASS, FAIL, UNKNOWN or NOT_APPLICABLE.
- **Technical verdict:** the worst of the checks. UNKNOWN is never PASS.
- **Publication** is a separate verdict. It requires all of:
  - `eligibility.may_export` on the four mapped gates. F-852 still refuses every generated
    frame.
  - The Etsy listing-image policy (UNKNOWN, VISGATE V1).
  - For Laura, `canonical.asset_status` must be `publication_approved`.
- **Owner visual approval** is its own column, `owner_visual_approval`. No gate reads it.

### Orchestrator stages (D-W4-LAURA-FLUX3 §8 mapping)

| # | Stage | CC state | Notes |
|---|---|---|---|
| 1 | retrieve_release | reference_preparation | Binds the certified release and PDF hash; seeds the wrap learning example (idempotent). No certified release gives `awaiting_certified_pattern`. |
| 2 | prepare_references | reference_preparation | `Generator.prepare_references` (W-FLUXAPI's layout/detail/rules PNGs). Each reference is stored by sha256 and its kind is validated. |
| 3 | product_generation | product_generation | Product-only anchor. It carries no Laura references. |
| 4 | fidelity_gate | product_generation | PASS continues. FAIL regenerates, up to 3 attempts. UNKNOWN blocks with no notification: no qualified verifier exists for generated images. |
| 5 | load_laura_references | lifestyle_generation | `canonical.verify`. Skipped when the campaign has no Laura. |
| 6 | reserve_outfit | lifestyle_generation | Uses the listing's reserved outfit if it has one. Otherwise `styling.select_for_listing` chooses it, and it is registered, approved by `creative_director:styling/1` and reserved. |
| 7 | lifestyle_generation | lifestyle_generation | All 3 canonical references plus the product references. Fewer than 3 is refused. |
| 8 | remaining_roles | lifestyle_generation | The campaign's other generated slots. |
| 9 | verification | automated_verification | A FAIL with a routable repair goes to stage 10, at most 2 rounds. |
| 10 | repair | automated_verification | Targeted directives (§4). |
| 11 | gallery_assembly | gallery_assembly | Campaign plan, `check_set`, `campaign_consistency`. |
| 12 | owner_card | ready_for_owner_review / blocked | Ready only if every generated slot is technically PASS and the set and consistency hold. |

- **Bounds:**
  - `MAX_ATTEMPTS_PER_ROLE=3`;
  - `MAX_REPAIR_ROUNDS=2`;
  - `MAX_GENERATION_CALLS=12`;
  - `MAX_SPEND_CAD_PER_GALLERY=2.00`.
  - Every repeat is a new idempotency-keyed job, so the workflow cannot loop.
- **Notifications:** `ready_for_owner_review`, and `blocked` with `attempts_exhausted`. A
  capability block (no generator, unverifiable fidelity, no outfit) appears on the Images tab
  only.
- **`approve()`:**
  - re-reads every card candidate's `publishable`;
  - records the owner's look decision;
  - moves to `approved_for_publication` only when no blocker remains.
  - Today F-852 always remains, so approval is recorded and refused.

## 2. Owner upload workflow (phone, step by step)

This is a fallback. It produces evidence; it does not publish anything.

1. On the phone, open the Command Center (`/cc/`) and sign in.
2. Open **More → Images**. The top card shows each product's gallery state.
3. In **Submit an owner-made image**:
   1. **Image:** pick the original file you downloaded from `dashboard.bfl.ai`. Use the
      original download, not a screenshot or a chat re-upload; re-uploads change the bytes and
      lower the resolution.
   2. **Product:** choose it, e.g. `cloudline-baby-blanket`. **Version:** `1.2.0`.
      **Release:** `7c63dbdd501f`.
   3. **Gallery role:** `lifestyle` for the sofa image. Leave `hero` alone: a generated image
      is never the hero.
   4. **Provider / Model:** these are prefilled as `bfl-dashboard` / `FLUX 3 Image`.
   5. **Prompt:** paste the full prompt.
   6. **Reference fingerprints:** one line per reference, `sha256 kind`. Use `laura_canonical`
      for the three canonical files and `pattern_derived` for the layout, motif and sheet.
   7. **Cost:** optional, e.g. `0.048`.
   8. Tick **Laura appears** and enter the **outfit id** of the listing's reserved outfit.
      Each listing has its own outfit; the Images tab lists the registry.
   9. Tick **I approve the look** if you do. This is recorded, but it is not a technical
      check.
4. Tap **Submit image**. The result card lists each check, the technical verdict and the
   publication blockers.

**CLI equivalent:**

```
python -m brambleloop.publish.owner_images intake --file cloudline_sofa.png \
  --slug cloudline-baby-blanket --version 1.2.0 --release 7c63dbdd501f --role lifestyle \
  --provider bfl-dashboard --model "FLUX 3 Image" --prompt-file prompt.txt \
  --ref "a42aeac7... laura_canonical" --ref "<layout sha> pattern_derived" \
  --cost-usd 0.048 --laura --outfit <id> --owner-approved-look
```

## 3. Wardrobe registry (D-W4-LAURA-OUTFIT + D-W4-LAURA-FLUX3 §4)

- **Table `laura_outfits`** (persistent, created by `Database.create_all`). Columns:
  - `outfit_id`;
  - `garments` {top_or_dress, lower, shoes, outerwear, accessories};
  - `signature` (sha256 of the normalised complete outfit);
  - `colours`, `reference_hashes`, `approved_reference`;
  - `setting`, `concept`;
  - `approval_state` (proposed/approved/retired), `approved_by`;
  - `listing` (the reservation);
  - `uses` [(listing, slug@version, image sha, at)];
  - `replaced_by`.
- **Complete:** an outfit must name a top or dress and shoes, plus a lower garment unless it
  is a dress.
- **One listing, one outfit:**
  - `reserve` FAILs when the listing already holds a different approved outfit.
  - Every image in the listing may reuse that one outfit.
  - `campaign_consistency` refuses a gallery in which Laura wears two outfits.
- **Never across listings:**
  - A reservation held by another listing FAILs.
  - A second id with the same garments (`signature`) is refused at registration and at
    reservation.
- **Release and replace:**
  - `release` frees a reservation only while no image has used it.
  - `replace` retires the old outfit, which stays bound to its listing for good, and reserves
    the new one.
- **Missing or unapproved:**
  - Laura with no outfit id gives UNKNOWN, which blocks.
  - An unregistered or unapproved outfit gives UNKNOWN.
- **Identity:**
  - Registration refuses `identity_changes`, identity words (hair, face, eyes, age, body,
    proportions…) and the canonical identity hashes as outfit references.
  - The identity check runs first and independently. An identity FAIL is never recorded as an
    outfit use.
- **Consistency:** whether an image actually shows the reserved outfit is `outfit_consistency`.
  It needs the vision judge, so it reads UNKNOWN and blocks until that is funded. On FAIL the
  image is regenerated within the cap.
- **Gate order** (`canonical.LAURA_LISTING_GATES`):
  1. canonical_identity;
  2. **body_proportions**;
  3. photorealism;
  4. anatomy;
  5. product_truth_if_product_shown;
  6. **outfit_uniqueness**;
  7. **outfit_consistency**;
  8. composition_brand_qa;
  9. disclosure_policy;
  10. publication_gate.
- `CUSTOMER_FACING_GATES` itself is unchanged: it is part of Laura's identity record, whose
  hash is pinned. A test asserts the record hash still matches.

**Automatic styling (§5).** `visual/styling.py` is deterministic:

- **Inputs:** listing, category, product colours, season, materials, use and target
  customer.
- **Outfit choice:** garments come from a fixed wardrobe. Garments whose colour clashes with
  the product are skipped, and so are complete outfits whose signature another listing
  already uses.
- **Setting:** taken per category, avoiding settings other listings use.
- **Avoid list:** studio backdrops, generic catalogue poses, over-staging and hidden or
  merged hands.

## 4. Product Truth failure codes and targeted repair

- **Codes:** W-FLUXAPI owns the shared constant. `repair_routes.shared_codes()` imports it
  under any of `creative.image_stages.PRODUCT_TRUTH_FAILURE_CODES`, `FAILURE_CODES` or
  `creative.product_truth_codes.FAILURE_CODES`. Until that lands, it reads the four codes from
  the wrap experiment `RECORD.json`. Nothing is redefined.
- **Routes** (`ROUTES`):

  | Code | Route |
  |---|---|
  | `INVENTED_END_BAND_TREATMENT` | Prompt negatives |
  | `INVENTED_EDGING` | Prompt negatives |
  | `WRONG_CRAFT_TEXTURE` | Reference change (stitch-texture reference) plus negatives |
  | `UNVERIFIABLE_COUNT` | No route. It stays UNKNOWN, is verified only on the unfolded product-only image, and never passes. A judge reading PASS with this code is forced to UNKNOWN. |

- **Unrouted codes:** a code with no route is not repaired. There is no blind regeneration,
  and the image stays blocked.
- **Seed:** `seed_experiment` imports the wrap experiment as the first learning row
  (`method=owner_manual`, outcome rejected, identity UNKNOWN because owner approval is not an
  independent check, cost US$0.048 converted, latency 121.45 s).

## 5. Learning records

Each `image_candidates` row records:

- method, provider and model;
- prompt sha and prompt version;
- references;
- cost, its basis and latency;
- every check;
- technical verdict, publishable, outcome;
- `failure_categories`. These are identity_drift, body_proportion_drift, outfit_duplication,
  outfit_consistency, product_fidelity, quality, anatomy, realism, role, binding, provenance,
  disclosure and provider_error, plus the shared Product Truth codes.

`learning_summary` reports outcome counts, categories, spend, latency and cost per accepted
image. The cost per accepted image is None when nothing was accepted or any cost is unknown.

## 6. Campaign plans for all 8 (D-W4-LAURA-FLUX3 §6; `shot_plans.campaign_plan`)

- **Jobs:** one job per frame (#65). `check_set` refuses duplicates, so the ruling's three
  Laura frames map to three distinct applicable jobs:
  - LIFESTYLE;
  - SCALE ("against something a person knows");
  - COLOUR_CONTEXT ("in a room").
- **Hero:** stays the disclosed product view. ASSET_CONCEPT_AS_HERO and F-852 forbid a
  generated hero. This is recorded as `ruling_conflicts` and is an owner decision.
- **Legend:** D = disclosed render, G = generated candidate (disclosed fallback where one
  exists), L = Laura, P = photo only.

| Listing | Images | Order |
|---|---|---|
| cloudline-baby-blanket | 7 | hero D · lifestyle G/L · detail D · size G/L (fallback D) · colour_context G/L (fallback D) · materials D · whats_included D; + proof P when a sample exists |
| hexagon-coaster-set | 7 | hero D · lifestyle G · detail D · size G (D) · colour_context G (D) · materials D · whats_included D; + proof P |
| winter-village-graphghan | 7 | same as Cloudline, with Laura |
| nordic-forest-mosaic-throw-baby | 7 | same as Cloudline, with Laura |
| mosaic-placemat-pair | 7 | as coasters (no Laura) |
| nordic-star-ornaments | 8 | hero D · detail D · size D · angle G (no disclosed producer: "flat back is its front", V5a) · construction: no producer yet (V5b; generated cannot serve CONSTRUCTION) · colour_context D · materials D · whats_included D; no LIFESTYLE job |
| nursery-nesting-baskets | 10 | hero D · lifestyle G · detail D · size G (D) · sizing D · angle D · construction D · colour_context G (D) · materials D · whats_included D |
| housewarming-key-basket | 9 | as baskets without SIZING |

- **Wearable template** (`wearable_template`): hero · detail · size · angle (front/back) ·
  construction · **fit (photo only)** · materials · whats_included; + proof.
- **Proof:** PROOF is listed as conditional on a physical sample everywhere.

## 7. What blocks the owner's approved Cloudline images today, gate by gate

| Gate | State | Why |
|---|---|---|
| Binding | PASS once submitted with release `7c63dbdd501f` | It needs the certified `assets.built` PDF hash on production, which this branch did not read. |
| Quality | **Likely FAIL** | The FLUX 3 1k tier outputs 1024×1024 / 912×1140 (W-FLUXAPI `image_stages.PRODUCT_SIZE` / `LIFESTYLE_SIZE`). The floor is 2000 px on each side. The 2k/4k tier or a verified upscaler is needed. Checked on the actual bytes at upload. |
| Role | lifestyle PASS; **hero FAIL** | ASSET_CONCEPT_AS_HERO |
| Product Truth | **FAIL** | `lifestyle_evidence` refuses informational (pattern-derived) references as product truth. A generated frame has no qualified structural verifier (`product_authority`: UNKNOWN). The wrap experiment shows the failure mode is real: invented edging and texture. |
| Identity | **UNKNOWN** | No conditioning receipt proves the dashboard sent the 3 references. There is no two-judge reading and no qualified biometric floor. |
| Body proportions | **UNKNOWN** | The vision judge is unfunded. |
| Anatomy / realism | **UNKNOWN** | The vision judge is unfunded. |
| Outfit uniqueness | UNKNOWN until the sage cardigan is registered and reserved for Cloudline; PASS after | |
| Outfit consistency | **UNKNOWN** | The vision judge is unfunded. |
| Disclosure | PASS (label) | Etsy's AI-disclosure rule for listing images is unread. |
| Publication: F-852 | **FAIL** | Generated product imagery is refused in every role. Changing that needs an owner policy decision (VISREF E4). |
| Publication: Etsy policy | **UNKNOWN** | The Listing Image Requirements page is 403 (DataDome). The help articles conflict on "use your own photographs" for designed items (VISGATE §3). |
| Publication: Laura | **FAIL** | No Laura image is `publication_approved`. |
| Gallery certificate | not issued | Generated frames are not written as `ListingAsset` rows until approval passes (remaining work E5). |

## 8. Unattended end-to-end test (no spend) and the smallest real paid test

**Done, offline:**

- `test_unattended_end_to_end_shadow_stub_reaches_owner_card_without_owner_step`:
  1. A certified Cloudline release triggers the run once; a duplicate trigger is deduped.
  2. The real `JobQueue` drains 12+ stage jobs with the stub generator and stub judges.
  3. Styling picks and reserves an outfit.
  4. The product-only anchor goes out with no Laura references. Three Laura frames go out,
     each with all three canonical references and the same outfit.
  5. The status board shows `ready_for_owner_review`.
  6. Exactly one deduplicated notification is created.
  7. The owner's `approve` is refused by F-852.
- Production judges and generators are not stubs. With them, the run stops at `blocked(no
  image generator is wired)`, or at the fidelity gate with real judges. Both are tested.

**Proposal only: the smallest real paid end-to-end test (Cloudline).** The owner must approve
the spend.

- **Prerequisites:**
  - W-FLUXAPI merged and its generator registered;
  - the BFL API key in the secret store (an owner credential action);
  - the `image_generation` gate opened for this plan;
  - for verdicts, `image_vision` funded.
- **Calls** (FLUX 3 at the 2k tier, so the output can meet 2000 px; the price must be quoted
  from BFL's official pricing before reservation; the dashboard observation was US$0.048 at 1k):
  1. 1 product-only anchor;
  2. 1 lifestyle (Laura, sofa);
  3. 1 SCALE frame;
  4. 1 COLOUR_CONTEXT frame;
  5. up to 2 repairs.
  - That is at most **6 generation calls**, plus at most **8 vision readings** (identity ×2
    judges, body proportions, outfit consistency, anatomy, realism, fidelity on the anchor).
- **Cap:** **CA$5.00 hard** in the gallery `spend_plan` (call_count 6, plus the vision budget
  inside the existing V0/P1 plans). It sits inside the CA$50 benchmark and CA$100 monthly
  ceilings.
- **Success, all required:**
  - every request carries the 6 references, proven by the conditioning receipt;
  - every output is ≥2000 px and opaque;
  - the anchor's fidelity is not FAIL, and UNVERIFIABLE_COUNT stays UNKNOWN unless the anchor
    is unfolded and counted;
  - identity and body proportions PASS from two independent readings;
  - one outfit across 3 frames;
  - the run reaches `ready_for_owner_review` with no owner step;
  - cost per accepted image is reported.
  - Publication still stays blocked by F-852 and the Etsy policy. This test proves autonomy,
    not compliance.
- **Early stop:** a quote above plan, the wrong size, two consecutive identity drifts, any
  uncertain billing, or spend reaching the cap.

## 9. Work that needs no owner (remaining engineering, estimates)

| # | Work | Hours |
|---|---|---|
| E1 | Adapter glue: wrap W-FLUXAPI `image_stages` (product_only / lifestyle / variant, receipts, conditioning receipt) as a `Generator` and register it. Map their failure-code constant and confirm `shared_codes()` resolves it. | 3–5 |
| E2 | A vision-judge adapter for identity (two judges), body proportions, outfit consistency, anatomy and realism on `image_vision`. Each reads UNKNOWN when unfunded. | 6–10 |
| E3 | A fidelity verifier on the unfolded product-only anchor: compare piece count, colour order, edging and end bands against the CIR from W-FLUXAPI's layout reference. Deterministic where possible. Without it every run blocks at stage 4 (honest). | 10–20 |
| E4 | Restart a blocked run (e.g. after the generator lands) under a new round key, without double-counting attempts. | 1–2 |
| E5 | On `approved_for_publication`, persist frames as unapproved `ListingAsset` rows and rerun `release_gates.listing_set` (coordinate with W-PRODREADY). | 3–5 |
| E6 | Approved outfit reference: set `approved_reference` from the first accepted Laura image and send it as a supplementary reference. | 1–2 |
| E7 | A CC outfit-registry editor and run drill-down view. | 2–4 |

**Total:** about 26–48 h.

## 10. Owner decisions (batched)

1. **F-852 policy for generated lifestyle images** (VISREF E4).
   - **Why:** every generated frame is refused for publication today, whatever its quality.
   - **Cost:** CA$0.
   - **Time:** 10 min to decide.
   - **If it waits:** autonomous galleries reach owner review but never publish. LIFESTYLE
     stays open on 7 products.
2. **Read the Etsy Listing Image Requirements page in a browser** (VISGATE V1).
   - **Cost:** CA$0.
   - **Time:** about 10 min.
   - **If it waits:** every image class stays UNKNOWN for publication.
3. **Fund the vision judge** (`image_vision`, existing plan ≤CA$0.75), and approve the §8
   paid test (≤CA$5.00).
   - **Why:** identity, body, outfit, anatomy and realism cannot pass without it.
   - **If it waits:** they stay UNKNOWN and block.
4. **BFL API key** (credential action), only when approving §8.
5. **Hero rule versus §6 "lifestyle hero".** Today's gates keep the disclosed view as hero.
   Changing that is an owner decision and is not inferred from the ruling.

## 11. Tests

- **New:** `tests/test_w4_ownerimg.py`, 29/29.
- **Regression** (all exit 0):
  - test_vacuity;
  - test_launch;
  - test_cost_governance_wave2;
  - test_search_hero_publish 4/4;
  - test_cert_listing_frames;
  - test_v11_autonomy_timeline;
  - test_v11_pwa_static 82/82;
  - test_roles;
  - test_physical;
  - test_continuous_operations;
  - test_v11_wiring;
  - test_w3_k11_authority;
  - test_w4_visref 14/14;
  - test_swarm_runtime;
  - test_w4_ccnotify;
  - test_v11_cc_views 13/13;
  - test_web_security 11/11.
- **Final rerun:** see the commit that records the results.
