# OPUS2-P0 handoff to Main Opus (second Opus operator, 2026-10-31)

Second Opus operator, replacing the one-time Fable assignment. Isolated branches only.
Nothing was merged, deployed, published or spent. Railway, Etsy, SHADOW mode, budgets and
Laura's canonical identity (`laura-r2-a42aeac7`, `visual/canonical.py`, the three references)
are unchanged.

## 1. Repository evidence

| Item | Value |
|---|---|
| Base | `origin/claude/w4-INTEG8-next` **4bc05dc2** (restart checkpoint, 2026-10-27T21:06Z) |
| Branch | `opus2/p0-revenue-workforce` |
| Commits | **0343b6b0** size-claim truth gate; **f3b763fb** Laura's home, basket rim negative, offline acceptance instrumentation; this handoff on top |
| Preserved Fable branch | `fable/p0-revenue-workforce` (base d11d494c): **732ad38d**, **f4f3f7bf**. Not for merge, see §2 |
| Production | ee35a493 (per `RESTART_CHECKPOINT.md`; not re-read from production in this session) |

Files changed on `opus2/p0-revenue-workforce`:

| File | Change |
|---|---|
| `src/brambleloop/gates/size_claims.py` | new |
| `src/brambleloop/publish/release_gates.py` | +11 lines in `for_publish`, after the listing-set reasons |
| `src/brambleloop/visual/laura_home.py` | new |
| `src/brambleloop/creative/flux3_generator.py` | scene environment from `laura_home`; room cue on product-only styled scenes |
| `src/brambleloop/creative/pattern_refs.py` | round-worked negative names a vessel's top rim |
| `scripts/p0_acceptance.py` | new (instrumentation, not a suite) |
| `tests/test_opus2_size_claims.py`, `tests/test_opus2_laura_home.py` | new |
| `research/final_build/w4/evidence_OPUS2/p0_acceptance_offline_4bc05dc2.json` | offline run record |

## 2. Ownership reconciliation

Read: root `BRANCH_OWNERSHIP.md` and `RESTART_CHECKPOINT.md` on `claude/w4-INTEG8-next` (4bc05dc2),
`research/final_build/w4/BRANCH_OWNERSHIP.md`, `INTEG8.md`, `LEDGER_STATUS.md`, `DEPARTMENTS.md`,
and the diffs of `claude/w5-INVENTORY` (0066c708), `claude/w5-CONCEPT` (af5cc7c1),
`claude/w4-LISTING1` (565475dc), `claude/w4-LAUNCHFIX` (323f302b) and `claude/w4-PDF1` (4ed0957a).

- **Fable's 15-stage register duplicates W5-INVENTORY.** `claude/w5-INVENTORY` owns the
  15-state inventory, flow health (stall/loop) and the CC Production view
  (`products/production_inventory.py`, `ops/flow_health.py`). Fable's `products/stage_register.py`
  + `products.stage_register` job does the same from different code. It is **preserved, not
  developed further, and should not be merged**. W-INVENTORY may read it for ideas: it adds a
  retention decision set for its read actions and a loop rule for repeated `cir.revise`.
- **Avoided as owned:** research-to-concept and the seed-shop watchlist (W-CONCEPT), PDF layout
  (W-PDF), basket identity and listing packages (W-LISTING), launch gates (W-LAUNCHFIX), manual
  adoption (W-ADOPT), the test runner (W-RESUMEFIX), the planned PDF-in-chain and
  listing-package jobs (integrator).
- **Checked and found already built, so not rebuilt:** visual production (12-stage
  `visual.image_production`, FLUX 3 generator registered on first use, outfit reservation and
  distinctness, identity anchor; paid generation waits on the owner's `image_generation` gate);
  listing-outcome ingestion and its learners (`listing.outcomes`, outcome learning, kill table);
  Winner Amplification into concepts (W-CONCEPT's family-order intake).

## 3. Specification documents

Located in `brambleloop/spec/`: Master Plan v1.2 (11 pp), Execution Directive, Acceptance Gates,
Build 2 Queued Upgrades v1.4.3 (42 pp), FINAL Master v1.0 (74 pp) and v1.1 (78 pp), Final Build
v1.1 prompt, FLUX 3 standard (spec/12), Laura rulings (spec/07, spec/13). Machine registries:
`build2/requirements.json` (320 rows), FM ledgers. **Limitation:** the PDFs were extracted and
searched for the requirements this work touches; they were not read cover to cover in this
session. No authoritative document was missing.

## 4. Engineering delivered

### 4a. Size-claim truth gate (owner §12 Nesting Baskets, §15; extends F-065 to own listings; F-298)

- **Finding.** "Nesting Baskets, three sizes" is one launched candidate with three variants,
  each its own CIR, release and PDF (`market-basket-small|medium|large@1.2.0`). The medium PDF is
  correct for the medium. The defect is product-level copy: `seo.facts.PRODUCT_LICENCES` licenses
  "three" and "nesting" for every basket CIR's listing, so one release's listing could promise
  three sizes. W-LISTING's owner-approved fix (D-W4-OWNER-BASKET-IDENTITY: small basket alone,
  kitchen and home) removes this instance; nothing prevented the next one.
- **Rim.** All three basket CIRs end in plain sc rounds. No braided rim exists in any certified
  basket pattern, so imagery showing one is untrue.
- **Built.** `gates/size_claims.for_release` reads the stored listing (title, description, tags)
  and the release's stored US PDF, and refuses when either promises more sizes than the one size
  a release delivers. `publish.release_gates.for_publish` adds its reasons. Graded size-chart
  wording ("size M of 9") is reference, not a claim. An unreadable PDF is reported and the
  listing is still judged. `launch0_findings()` is the static check.
- **F-065 note.** The existing F-065 producer (`teardown/scorecard.promise_audit`) audits
  purchased competitor deliverables only.

### 4b. Laura's home (owner §14) and the rim negative (§12, §13)

- **Built.** `visual/laura_home.py`: one fictional Canadian family house (`laura-home-v1`), six
  rooms with fixed structure, light, anchor furniture and ordinary lived-in details, and shared
  house details so rooms read as one home. Each product category maps to one room. Showroom,
  luxury and "real sample" vocabulary is refused. Descriptions are refused, never truncated, past
  800 characters.
- **Wired.** The FLUX 3 lifestyle scene's `environment` now comes from the home, not the outfit's
  free-text `setting` (which invented a new room per generation; with none, the prompt fell back
  to "a calm, natural setting"). Product-only styled scenes lead with a short room cue inside the
  400-character edit cap. Canonical Laura references still lead every request (tested).
- **Rim.** `pattern_refs.negatives` for round-worked items now names a vessel's top rim: no
  braided, rolled, twisted, scalloped, picot or crab-stitch rim.
- **Spec fit.** Build 2 #72 lets environment vary across listings; rooms vary by product, the
  house stays the same. #74 product-first exceptions are unaffected (nothing adds Laura).

### 4c. Offline acceptance instrumentation (owner §19)

`scripts/p0_acceptance.py <dir>` runs the 18 demonstrations against the real handlers in a
SHADOW worker on a scratch DB, with sockets closed, credentials removed and a labelled fixture
for the model and vision judge. Result at 4bc05dc2 + this branch: **17 OFFLINE_PASS, 0 FAIL,
1 NOT_DEMONSTRABLE_OFFLINE** (performance learning: no live listing). Each record names the
production read that would prove it. Notable readings:

- #2/#3: a tournament winner outside the 34-seed POOL reaches `cir.draft` **only** after a vision
  judgement (fixture here). In production that judge needs vision credit (owner spend).
- #8: the coaster set's customer PDF is **7 pages** against the owner's benchmarks of 12 and 17;
  W-PDF owns the layout.
- #9: only deterministic disclosed renders exist offline; model-backed frames wait on the
  `image_generation` gate.

## 5. Tests executed

| Suite | Result |
|---|---|
| test_opus2_size_claims | 8/8 |
| test_opus2_laura_home | 8/8 |
| Publish path: test_cert_publish_gates, test_listing_parity_gate, test_w4_listready, test_search_truth, test_etsy, test_originality_runtime, test_rehearsal_stall, test_deliverable_qa, test_cert_improve_wave, test_v11_seo_proposals, test_w4_cap1_gates_intact, test_w4_cap1_placemat_price, test_w4_fmbatch1_drift | all pass |
| Visual: test_w4_flux3generator, test_w4_fluxapi, test_w4_fluxstages, test_w4_fluxtexture, test_w4_ownerimg, test_w4_visnext, test_w4_visnext2, test_w4_visnext_frames, test_w4_fidelity, test_w4_baseline_six, test_v11_store_foundation | all pass |
| Guards: test_canon_manifest, test_roles, test_secret_scan, test_w3_tmp_hygiene, test_vacuity, test_w4_fmbatch1_retention_guard | all pass |

No full suite was run (Main Opus's single uninterrupted run). Local venv built from
`requirements.lock` + `requirements-test.lock` on Python 3.13.

## 6. Integration safety

- **Merge conflicts expected:** `publish/release_gates.py` with W-LAUNCHFIX. This branch inserts
  11 lines after `reasons.extend(set_verdict["reasons"])`; LAUNCHFIX edits the signature and the
  tail. Separate hunks; the return dict was deliberately left unchanged.
- **After W-LISTING merges:** the static test switches branch automatically (nursery candidate
  held → no findings). Re-run `test_opus2_size_claims` on the merged tree. Checked in advance:
  the regenerated title, description and tags in W-LISTING's
  `manual_listings/market-basket-small-1.2.0/LISTING_PACKAGE.md` (565475dc) make no size claim.
  The parser's only hits there are the package's own commentary about the claims it removed,
  which the gate never reads (it reads the stored listing row and the PDF).
- **Database:** no schema change, no migration, no new job type, no new audit action read.
- **Security:** no new route, credential or network path.
- **Product Truth:** stricter only; adds one refusal reason.
- **Laura identity:** untouched. The scene environment changes; identity references and gates do not.
- **Spend:** none. No provider called; prompts change only when a paid generation is authorised.

## 7. Remaining requirements and owner items

- **Independent review needed:** both commits (size-claim gate on the publish path; prompt
  change on the paid-generation path).
- **Integration:** merge after W-LAUNCHFIX and W-LISTING, run the touched set, then the full suite.
- **Production acceptance:** the §19 reads listed in the acceptance JSON, and the 24-hour run.
- **Handed to owners:**
  - W-CONCEPT: the owner's two MJ's reference listings (Fall for Granny Baskets 1767833856;
    Homebody Baskets 4295011799) belong in its benchmark registry (`intel/benchmarks.py`, owned).
  - W-PDF: page depth (7 pages vs 12–17 benchmarks).
  - W-INVENTORY: Fable's register (§2) for comparison.
- **Owner decisions (not actions taken):** approve the Nesting Baskets outfit candidate (sage
  blouse, cream trousers, gold jewellery) through the wardrobe editor; review the six rooms in
  `laura_home.house()`; vision credit for the pre-engineering judge; `image_generation` spend.

## 8. Completion classification

| Capability | Implemented | Integrated | Deployed | Production verified | End-to-end accepted | Business outcome |
|---|---|---|---|---|---|---|
| Size-claim truth gate | yes (branch) | no | no | no | no | no |
| Laura's home + rim negative | yes (branch) | no | no | no | no | no |
| Offline acceptance instrumentation | yes (branch) | no | no | n/a | no | no |

The P0 workforce is **not** operational in production on the strength of this work.

## 9. Claims (BRANCH_OWNERSHIP update of 2026-10-31T01:10Z: claim by committing a line here)

- **CLAIMED 2026-10-31 (second Opus operator): growth and performance-learning ingestion into
  future product decisions.** Measured own-listing outcomes (`listing_outcomes` owner-export
  rows, orders) become routed lessons on the existing bus, so `radar.score`'s existing bounded
  lesson nudge reorders what is engineered next. New files plus small registrations; no edit to
  `radar.score`. Not claimed: the gallery cluster (found already built: `image_production` →
  `approve` → `ListingAsset`), next-product selection (overlaps W-INVENTORY's stall detection
  until it merges), competitor-scan evidence (inside W-CONCEPT's watchlist files).

## 10. Cluster 3 delivered: measured listing performance into product decisions

- **Gap (verified).** `listing.outcomes` records visits, favourites and orders; the outcome
  learner and kill table read them; none published a lesson. Market Radar reads only lessons
  (`improve.consume.matching` inside `radar.score`), so measured demand never changed which
  concept is engineered next.
- **Built.** `improve/commercial_lessons.py` + job `improve.commercial_lessons` (analyst,
  daily cadence, OBSERVE, CA$0; `runtime/commercial_ops.py`). Per radar category, from
  export-intake `ListingOutcome` rows carrying orders (F-297: fixtures and hand-inserted rows
  never count): MEASURED at >= 200 visits, compared only when two categories are measured.
  >= 1.5x the shop rate on >= 3 orders publishes `commercial_demand`; <= 0.5x on >= 400 visits
  publishes `commercial_underperformance`. Each lesson names the uncertified pool concepts in
  that category or family (the follow-ons), so `radar.score`'s existing bounded nudge (cap
  0.06) moves exactly those. Idempotent by evidence; changed evidence withdraws the old lesson
  (`bus.withdraw`). Nothing measured publishes nothing (UNMEASURED, never "no demand").
- **Registrations.** Two subjects in `improve.bus.SUBJECT_ROUTING` (market_radar,
  product_creativity, growth); `commercial_demand` in `consume.FAVOURS`,
  `commercial_underperformance` in `DISFAVOURS`; analyst permission; authority class O;
  `WORK_KEYS`; cadence; `autonomy_map.json` regenerated. No edit to `radar.score`.
- **Limits.** Matching is the bus's word overlap, so a family relative of a named follow-on
  (for example another `nordic-forest` concept) can also receive the bounded nudge. Concepts
  W-CONCEPT adds outside the POOL are matched by category and family words only.
- **Tests.** `test_opus2_commercial_lessons` 8/8 (includes the real `radar.score` handler). 37 related suites green: lesson bus, radar, registry, roles, autonomy map, wiring certification, close5 rows 1-6 (the Etsy-write scan forced the writer's name `record_lessons`), finhealth, cost governance, retention, vacuity, secret scan, tmp hygiene.

## 11. Backlog findings (no code: already built, owned, or owner-held)

- **Next-product selection.** Already covered after certification: `chain.rebuild` (hourly)
  re-drives certified releases with no current-chain listing, `ops.rebuild_graph` re-drives
  stale artefacts, `ops.queue_check` re-drives dead letters once per deploy, and the
  orchestrator wakes idle departments. Before certification the bottleneck is the vision judge
  for #83/#88 (owner spend), which code cannot replace without weakening the gate. Stall
  detection is W-INVENTORY's; an automatic re-drive of a stall W-INVENTORY reports is a
  follow-on once that branch merges (it would consume `flow_health.flow`, not re-derive it).
- **Gallery assembly.** Built: `visual.image_production` → `approve` → fresh verification →
  `ListingAsset`; item counts (`UNVERIFIABLE_COUNT`) and invented edgings are already gated.
- **Competitor-scan evidence.** Inside W-CONCEPT's `intel/watchlist.py` (not-accessible
  records, seed shops). Not taken.

## 12. Coordination mechanism

This session is subscribed to PR #3 events (reviews and comments from Main Opus wake it). A
Claude session does not run indefinitely; it resumes on those events, on a scheduled
check-in, or on an owner message. The durable record is this file and PR #3.

## 13. Review response and next claim (2026-10-31)

- **PR #3 CHANGES_REQUIRED addressed.** f3b763fb is reverted (6d96af30, no history rewrite)
  and re-applied as (a) 4f1efcc8 `laura_home` + FLUX 3 wiring, (b) f02426fa rim negative with
  its own `test_opus2_rim_negative`, (c) fc7bd63e acceptance instrumentation, plus f76d539c the
  size-claim test's vacuity line. Content is byte-identical to f3b763fb apart from the rim test
  moving file. The owner's variation requirement is f93b1ec3.
- **CLAIMED: OPUS2-CHAIN-DEADENDS** (P0-CHAIN-DEADENDS, and the successor half of
  P0-NEXT-PRODUCT). Recorded in `COORDINATION.json` on this branch.

## 14. Cluster 4: OPUS2-CHAIN-DEADENDS (P0-CHAIN-DEADENDS; successor half of P0-NEXT-PRODUCT)

Each W-INVENTORY dead end now has a deterministic successor (`runtime/chain_successors.py`):

| Dead end | Successor | Who acts |
|---|---|---|
| `pricing.position` refuses on the net floor or `OUTSIDE_PLAN_BAND` | one owner action `chain-deadend:pricing:<slug>@<version>` (CA$0, 10 min) with the refusal and reasons, plus a P2 incident | owner (a price outside the band is a commercial decision) |
| `pricing.position` refuses `UNKNOWN_PRODUCT` | P2 incident only, no owner action | company (catalogue defect) |
| `assets.build` `ok: false` (images misrepresent the pattern) | P2 incident naming the visual department, with the problems | company |
| `listing.parity` audit row unversioned | the row's detail now carries `version` and `release` (artifact unchanged, so slug-keyed readers keep working) | n/a |
| `launch.plan` HOLD / SIMPLIFY | `launch.plan` re-queued for the day after the missed occasion (06:00Z), or +30 days with no date; one per release per date; PIVOT is unchanged | the chain itself |

- **No loops.** The hourly `chain.successors` sweep (listing agent, class B like `chain.rebuild`)
  re-drives each open dead end **once per deployed commit**, because only a code change can
  change a deterministic refusal. It never re-drives while the commit is unknown (the
  `ops.queue_check` rule). It resolves the incident once the stage has succeeded for that exact
  slug, version and release.
- **Stage bodies unchanged.** `handle_assets_build`, `handle_pricing_position` and
  `handle_launch_plan` keep their names and bodies (tests inspect their source). Each lost its
  decorator, and a registered wrapper at the end of `runtime/release.py` runs it and adds the
  successor. A successor failure never changes the stage's own result.
- **Halts.** Every incident is P2 and non-halting: the stage's own refusal already stops the
  product, and nothing else is halted.
- **Tests.** `test_opus2_chain_deadends` 10/10 (owner action once, defect vs decision,
  images, re-plan date and idempotency, pivot, unknown occasion, per-commit re-drive,
  unknown-commit refusal, resolution, parity version).
- **Integration.** `runtime/release.py` (decorators moved; wrappers appended at the end),
  `runtime/pipeline.py` (parity detail; `WORK_KEYS`), `agents/registry.py` (listing may run
  `chain.successors`), `authority/classes.py`, `autonomy/charters.py` (store_commerce
  job_types), `runtime/worker.py` (hourly cadence), `autonomy_map.json` regenerated. W-INVENTORY
  can drop its "policy hold, no successor" notes for these four once both merge.

## 15. Cluster 5: OPUS2-COMPETITOR-EVIDENCE (P0-COMPETITOR-EVIDENCE)

- **Built.** `intel/scan_evidence.py` (read-only) + daily `intel.scan_evidence` (market_radar,
  class O, CA$0; `runtime/evidence_ops.py`). For each of the owner's eight named shops, in the
  owner's order, it reports: method (Open API v3, key-only), schedule (the scanner's
  cadence), last attempted, last successful, source timestamp, provenance (the row it read),
  failure reason, consecutive failures, limitations, and downstream output (listings observed
  with first and last seen). It also reports the credential state from the last `etsy.probe`
  and the two MJ's reference listings (1767833856 Fall for Granny Baskets, 4295011799 Homebody
  Baskets): observed or not, and why.
- **States are derived.** `scanned`, `attempted_not_scanned`, `not_accessible`,
  `never_attempted`, `not_registered`. A seed shop reads `not_registered` on this base: no scan
  can have run, so none is claimed. After W-CONCEPT merges, it reads its watchlist state
  instead, including W-CONCEPT's `not_accessible` records. The anchor's failure is only a
  failure newer than its last success.
- **No content copied.** No competitor title, description or listing URL enters the evidence
  (tested). One durable `operating_readings` row per UTC day, which retention does not prune.
- **No W-CONCEPT files touched.** It reads `watchlist._state`, `watchlist.WATCHLIST` and
  `benchmarks.MJS*`.
- **Tests.** `test_opus2_scan_evidence` 7/7.
- **Production read once deployed:** `operating_readings` kind `intel.scan_evidence`. A
  Command Center tile and an `/api/readback/evidence` row are integration choices for the
  W-READBACK / CC owners.

## 16. Cluster 6: OPUS2-GALLERY-PHOTO-LED (P0-GALLERY-ASSEMBLY: the photo-led certificate)

- **Gap (from COORDINATION.json).** `listing_set.certify_disclosed` refused a mixed set, so a
  Launch-0 gallery could not lead with the owner's unedited sample photo, even after
  W-PHYSFIX-PHOTO's ordering. The photo frame was left out of the certificate, so the upload
  lacked it and LAUNCHFIX's sample-photo gate would refuse activation.
- **Built.**
  - `listing_set.certify_photo_led` + `photo_lead_frame`: position 1 is the photo (job PROOF,
    purpose PHYSICAL_PROOF, medium PHYSICAL_PRODUCT_PHOTO, no disclaimer label), and the
    disclosed frames and supplements move down one, keeping their order and their disclosure.
  - Each attestation must hold: unedited, not AI-processed, test passed, test completed, full
    make, same release (and the photo's bytes are the test's photo), camera provenance, rights
    basis. The photographed configuration must be the listing's (F-757; one sample is one
    size). Alt text may not call it a render or AI imagery.
  - The photo adds its own readings to DATA_TRUTH (approved and unblocked, bytes hash-match)
    and COMMERCIAL_QA (the photo, now the hero, read at thumbnail size). Each must have run and
    passed; a failed disclosed gate stays failed.
  - The supplement rules moved to `_with_supplements`; `certify_disclosed`'s behaviour is
    unchanged.
- **Wired.** `release_gates.sample_photo_lead` re-reads every eligibility fact from the
  PhysicalPhoto and PhysicalTest rows rather than trusting PHYSFIX-PHOTO's `leads_gallery`
  mark. `disclosed_listing_set` uses the photo-led certificate when one exists.
  `etsy_ops.certified_images` uploads it first, with its certified alt text.
- **Dependency.** The full-make class comes from W-PHYSFIX's `risk_matrix.physical_class_of`.
  On this base it is absent, so `full_make` is not attested and the photo cannot lead (tested).
  After W-PHYSFIX merges, it works without change.
- **Tests.** `test_opus2_photo_led_gallery` 6/6, on the real chain (gate.certify,
  assets.build, listing_set, certified_images) for the Cloudline blanket, with a labelled
  full-make stand-in where needed.
- **Integration.** Small hunks in `release_gates.py` (a new function before
  `disclosed_listing_set`, plus the certificate choice) and `etsy_ops.py` (W-ADOPT also edits
  this file).

## 17. Review OPUS2A fixes and the merged-head regression (2026-10-31)

- **Review OPUS2A (54766c9e) fixed in c94dbb5e.**
  - Size gate: F1.1 HIGH, F1.2, F1.3 and F1.4. Every probe row is pinned in tests, and an
    unread PDF now refuses.
  - `laura_home`: F2.1 decoys (`DECOY_FOR_CATEGORY`, plus a "no other crocheted or knitted item"
    line), F2.2 (brief checked; refused rather than cut) and F2.3 (no person named in the
    product-only cue).
  - Acceptance script: F4.1 and F4.2.
  - Rim INFO (the vessel wording on flat round pieces) is left as it is: harmless, as the
    review says.
- **Merged-head regression (124 suites, frozen 0b4607df = base 421743e8 + this branch).**
  119 passed and 5 failed. Each failure was diagnosed against the clean base 421743e8:

  | Suite | On base 421743e8 | Cause | Action |
  |---|---|---|---|
  | test_maturity | pass | the decorators moved to wrappers, so the derived job map read the wrappers' modules | **fixed**: originals keep `@handlers.register`; wrappers registered by explicit calls at the end of `release.py` (applied last) |
  | test_w4_launchfix | pass | the photo kind `physical_sample_photo` contains the substring `sample_photo` in two more modules | **fixed**: kind renamed `physical_photo_lead` (`listing_set.PHOTO_LEAD`) |
  | test_w4_resume_runner (F7) | **fail** | the final-segment list misses clock-sensitive suites | added this branch's two (`test_opus2_chain_deadends`, `test_opus2_photo_led_gallery`); the remaining three (`test_w4_launchfix`, `test_w4_owner_queue_race`, `test_w4_readback_evidence`) are Batch 4 suites for the harness owner |
  | test_cost_governance_wave2 | **fail** | retention has no decision for `chain.rebuild_completed`, `chain.rebuild_unbound`, `etsy.taxonomy_refreshed`, `ops.rebuild_propagated`, `ops.truth.sweep`, `paid_call.replayed` (Batch 4 readers) | base defect, not this branch; integrator |
  | test_w4_fmbatch1_retention_guard | **fail** | same six actions | base defect; integrator |

  After the fixes, test_maturity, test_w4_launchfix and every opus2 suite pass, as do
  test_v11_autonomy_timeline, test_ranking_readiness, test_w4_ownerimg and
  test_w4_firstsale_deliverables.

## 18. CLAIMED: OPUS2-REVERIFY-WITHHOLD (P0-REVERIFY-WITHHOLD, 2026-10-31T07:20Z)

Base merged: 0cf0c59d. A failed re-verification will record a durable withholding that
`for_publish` already refuses on, so pruning the audit row cannot reopen the gate.

**Delivered (2026-10-31).** `publish/withholding.py` gains kind `quality_reverify`
(publish-only, never build-blocking) and `record_reverification(db, slug, version, check=,
problem=)`, which holds each failing check under `certificate["reverify_failed"]` and clears
the kind only when no check is failing. `runtime/quality_ops._run_check` records every
definite reading (ok True/False; an unknown reading changes nothing) and returns
`withheld_checks`. `release_gates.for_publish` names it: "release withheld
(re-verification): ...". `withholding.reconcile` never clears it (not a publish-standard
kind). Tests: `tests/test_opus2_reverify_withhold.py` 4/4. The regression covers
23 suites: every suite reading withholding, quality_ops, gate.quality or for_publish,
plus the vacuity, retention, cost, roles, autonomy-timeline, maturity and launchfix guards.
All exit 0.

## 19. P0-DRAFT-CONSTRUCTIONS (claimed from `unowned`, 2026-10-31)

**Problem (W-CONCEPT report).** The radar fallback `concept_to_cir` drafted every concept as
one flat striped panel. Every seed still reaching it is a shaped object. That covers the two
baskets, three amigurumi, a hat set, a beanie, two shawls, a tote, two garments, a stocking, a
mobile, egg cosies, a pumpkin cluster and a ring cushion. A flat panel under those names is a
pattern that does not make the thing it is called.

**Built.**
- `creative/fallback_constructions.py`:
  - `plan(category, title, is_bundle)` returns `flat_panel`, `vessel` or `refused`, with
    `needs` and `why`.
  - `vessel(concept, provenance=)` builds a hexagon disc base from a magic ring
    (`products.vessels._disc_rounds`, `base_stitches_for`). The base count is a whole number
    of six wedges and of the concept's repeat. The walls alternate plain sc rounds (main
    colour) with the concept's own repeat (accent). The size comes from the title (bread
    gives small, market gives large, otherwise medium).
- `runtime/pipeline.handle_cir_draft` fallback block, the only integration point:
  - A refusal audits `cir.draft_refused` with `gate: construction`, `category` and `needs`,
    and returns `drafted: False, gate: construction`.
  - A vessel's provenance names `creative.fallback_constructions.vessel`,
    `products.vessels._disc_rounds`, `products.vessels.base_stitches_for`,
    `concept_geometry:<category>` and `gauge_for:<yarn>`. Unknown lineage still gets no
    provenance, so the originality gate still refuses it.
  - `cir.drafted` and the result carry `construction`.
  - Flat forms are unchanged byte for byte. Bundles keep `collection.assemble`.
- `tests/test_fallback_draft_provenance.py`: the pinned producer chain for
  `nordic-forest-basket` is updated to the vessel chain. No other assertion changed, and the
  digest is still recomputed independently.
- Tests: `tests/test_opus2_draft_constructions.py`, 4/4. It checks that every fallback seed is
  routed and none is a shaped object on a panel. The basket compiles in joined rounds from a
  magic ring and carries the concept's palette and repeat. Shaped concepts are refused by
  name with nothing compiled. Unknown lineage stays unknown.

**Not done (honest).** In-the-round colourwork charts and motif assembly (granny squares,
hexagon joins) are not fallback rules yet. Concepts that need them are refused by name. Those
refusals are the evidence §20 counts. No flat colourwork seed reaches the fallback: all of
them are engineered designs.

## 20. P0-LEARNING-GAPS (new; owner directive 2026-10-31 §3 items 17-18 and §4)

**Built.**
- `intel/knowledge_gaps.py`:
  - `LINES`: the owner's 12 intended product lines, each with a pod and catalogue categories.
    No category is in two lines.
  - `evidence(db)` counts per line: certified releases; `cir.draft_refused` rows with gate
    `construction` over 30 days (with refused slugs and needs); `cir.compiled ok:false`; and
    purchased `BenchmarkProduct` rows in the pod.
  - `score` uses fixed weights: no certified release counts 3; each refusal counts 1, up to
    3; each failed compile counts 1, up to 2.
  - `assess(db)` records `OperatingReading` kind `learning.knowledge_gaps`. It raises at most
    `MAX_OPEN=2` open `OwnerAction`s keyed `knowledge_gap:<line>`, one per pod. Each names the
    listing `benchmark_refresh._pick` (`purchase_selection`) would buy, with its observed
    price as the maximum cost.
  - It never asks twice. It never recommends a second purchase for a line the library
    already covers ("learning pending"). It never asks the owner to find a listing, and it
    never buys.
  - `latest(db)` lets Product Development and the owner view read the newest reading.
- `runtime/learning_gaps_ops.py`: the `learning.knowledge_gaps` job.
  - Agent `analyst`, action class O.
  - Weekly cadence `knowledge_gaps` in `worker.CADENCES`.
  - Work key `work_done`.
  - Retention entry for `cir.draft_refused` (windowed).
  - `autonomy_map.json` regenerated.
- Tests: `tests/test_opus2_knowledge_gaps.py`, 6/6, including a real `cir.draft` refusal
  becoming the amigurumi gap.

**Boundary with Codex P0-LEARNING-REFERENCE.** This touches no files under `teardown/`, and
not `improve/mine.py`, `improve/design_knowledge.py` or `quality/design_eval.py`. Codex's
analysed `BenchmarkProduct` rows count automatically as library coverage. A covered line then
stops recommending purchases until its teardown teaches something.
**Suggested integrator hook:** once Codex's `DesignRule` exists, a gap line whose approved rules
increase could lower its score. Not built, so as not to read an unmerged API.

## 21. P0-NEXT-PRODUCT: already covered; nothing built (2026-10-31)

**Finding.** Selecting the next product when capacity is free already works on its own:
- The hourly `chain.rebuild` (listing agent) calls `release_recovery.seed_launch0`.
- That drafts the next Launch-0 release whose code version is not certified: one per run
  (`SEED_PER_RUN=1`), in listing order, keyed per design and fingerprint.
- A release already seeded is skipped, so the next run takes the next one. A held or failed
  product therefore never stops the one after it.
- After certification, `chain.rebuild`, `rebuild_graph` and `ops.queue_check` carry the
  release onward.

**What I tried and withdrew.**
- `products.pipeline_board.handle_product_pipeline` is written as a `product.pipeline` job
  ("WIRING REQUEST to W4-AUTO") but is not registered. I wired it with a daily cadence and a
  Product & Design `next_work` provider.
- The overnight suite (`test_v11_autonomy_overnight`) then showed the board's advance
  enqueueing `cir.draft` for all 10 never-built Launch-0 slugs at once. It uses its own key
  (`pipeline-draft:<slug>`), so it duplicates `seed_launch0`'s drafting, and 10 chains reached
  `store.publish` in one night. That refusal in SHADOW is correct, but the suite counts it as
  10 unretried failures.
- All of that wiring is reverted. Nothing from it is on this branch.

**For the integrator.** Do not register `product.pipeline` as written. If the board should
run on a schedule, register it as a reading only, and remove its `launch_scope_drafts`
enqueue: `seed_launch0` already owns that advance.

**Gap that remains real.** Five board proposals and five creative candidates pass Product
Truth on the board but are not catalogue releases. Adopting them into the release registry is
a code change (`builder.CATALOGUE`, `RELEASE_VERSIONS`), so the runtime cannot make it. Each
needs an integrator decision.

**Also fixed here.** `learning.knowledge_gaps` (§20) had no department charter, so
`test_v11_autonomy_orchestrator` failed on 3cbf6e96. It is now in the Learn / Improvement
charter's `job_types`, and the autonomy map is regenerated.

## 22. P0-DRAFT-CONSTRUCTIONS, part 2: cushions as seamed panel pairs (2026-10-31)

**Built.**
- `creative/fallback_constructions.py` gains the family `panel_pair`.
  - It applies to categories `pillow` and `wedding`, and to any title naming a cushion or
    pillow. A title that names a cushion plus a closed shape the panel pair does not make,
    such as an egg cosy, stays refused.
  - `panel_pair(panel)` takes the concept's own flat panel (`concept_to_cir`, unchanged) as a
    front and a back. It whipstitches the left, top and right edges, then closes the bottom
    over the pad (`stuff_before_closing`).
  - Identical panels make every seam's two edges the same length by construction.
  - Its provenance chain gains `creative.fallback_constructions.panel_pair`.
- `wedding-ring-cushion` now drafts. It compiles, `launch0.title_promise` is backed (an
  assembled form with real seams), and `publish.eligibility.name_truth` finds nothing. Its
  risk class C still requires a physical test at certification, which is the correct gate.
- `cir.drafted` now records `name_truth` for the vessel and panel-pair families. It is a
  reading only; publication's `NAME_OUTRUNS_PATTERN` stays the refusal.

**Found (honest).** "Nordic Forest **Mosaic** Storage Basket" fails name truth as a vessel:
one colour per round is relief, and the house rule (`pipeline_board`) is never to call that
"mosaic". The old flat-panel draft failed the same way, so this is not a regression, and
publication refuses it.
- The draft audit now carries the problem, so the gap is visible.
- A truthful two-colour-per-round chart in the round is the next construction rule worth
  building. Alternatively, the radar seed could be retitled "relief", which is the
  integrator's or W-CONCEPT's call, since the seed lives in `radar/opportunity.py`.

Tests: `tests/test_opus2_draft_constructions.py`, 5/5.

## 23. P0-DRAFT-CONSTRUCTIONS, part 3: triangle shawls; tote blocked on a chain gauge (2026-10-31)

**Built: family `triangle`.** It applies to category `shawl` and to titles naming a shawl,
shawlette, triangle scarf or kerchief.
- `triangle(concept)` works flat from the point. It starts with 3 sc on a 3-chain foundation,
  then works an increase at each end of every row.
- The colour changes every two rows, so each change falls at the same edge and the resting
  colour is carried up that edge.
- The row count is chosen so the last row is nearest a 150 cm wingspan at the yarn's
  published gauge. The size note states the computed wingspan and depth, and says it has not
  been measured.
- Provenance names `creative.fallback_constructions.triangle`.
- **Stitch-pattern guard.** A shawl title naming a stitch pattern is refused, naming the
  chart it would need. The words are lattice, lace, mosaic, cable, bobble, granny, chevron,
  ripple, waffle, shell, puff, popcorn, star, diamond, tulip, fair isle, tapestry and filet.
  Plain single crochet is none of those.
- So both radar shawl seeds ("Lattice Triangle Shawl", "Mother's Day Lace Shawlette") stay
  refused, with needs "a lattice/lace stitch chart worked on triangle shaping". The knowledge-
  gap job counts that.
- Tests: `tests/test_opus2_draft_constructions.py`, 6/6. A plain triangle compiles. Each row
  adds exactly 2 stitches. Name truth is clean, and certification finds nothing beyond the
  missing provenance (a unit build has no lineage). The wingspan is within 2 cm of target.
- **Finding for the integrator.** `publish.eligibility.name_truth` does not read "lattice" or
  "lace". A plain single-crochet triangle titled "Lattice Triangle Shawl" passed it in the
  probe. The guard here covers this fallback only, and the vocabulary gap stays open for
  every other path.

**Tried and not built: tote with slot handles.**
- The tote would be a vessel with two handle slots: on one round, skip h and chain h on
  opposite sides; on the next, work into the chains.
- It compiles. Certification refuses it with `SPECIFICATION_INCOMPLETE: chain gauge`, because
  a slot's length depends on `Gauge.chains_per_10cm` and no yarn here has a stated one.
  Inventing a figure would be fabricated evidence.
- Strap-sewn handles cannot be measured either: `cir.assembly` places a join only along
  flat-row side edges, not on a span of a piece worked in rounds.
- **Needs one of:** a measured chain gauge (physical calibration, the owner's tester queue),
  or an assembly-model extension for spans on round pieces (shared `cir/assembly.py`,
  integrator's call).

## 24. Review OPUS2B2 (9c1a0037): every finding fixed (2026-10-31)

Report: `claude/w5-SECREVIEW-OPUS2B2-9c1a003`. The verdict was ACCEPT for parts 1, 2, 4, 5
and 6, and CHANGES REQUIRED for part 3. Base merged: `f4c3899b`.

| Finding | Fix | Test |
|---|---|---|
| **F3.1 MED (required)**: a shop that once scanned and failed since reads "scanned" | `scan_evidence._failed_since_success` derives the state from the latest attempt. A refusal (credential refused, 403, a recorded limitation) is `not_accessible`; an outage is `attempted_not_scanned`. `failure_reason` is always given, and the old success stays as `last_successful`. The anchor follows the same rule. | `test_review_opus2b2_f31_success_then_repeated_refusal_is_not_scanned` (the reviewer's repro). The earlier anchor test pinned the old behaviour and now expects `not_accessible`. |
| F1.1 LOW: the pricing owner action stays open after the dead end clears | The sweep's resolve branch closes `chain-deadend:pricing:<slug>@<version>` as `satisfied`, with a reason, through `owner_queue.close`. | `test_review_opus2b2_f11_the_pricing_owner_action_closes_with_its_dead_end` |
| F1.2 LOW: the parity row's version is not defaulted like the verdict's | `version` now defaults to `"1.0.0"`, matching `_listing_parity`. | the parity source pin is updated |
| F2.1 LOW: re-certification drops the re-verification withhold | `withholding.carry_reverification` carries the failing checks and the `quality_reverify` kind onto the new certificate (fail closed, marked `carried_across_recertification`). The pipeline then queues `gate.quality` at once, so the new content is checked promptly. | `test_review_opus2b2_f21_a_recertification_keeps_the_failure_and_queues_the_checks` |
| F2.2 INFO: two texts still say nothing is blocked | The incident note now says publication is withheld. `certificate_changed` is true only when the reading changed the record. | the same test, plus `test_w4_departments` |
| F4.1 LOW: overlapping owner exports double-count | `commercial_lessons._non_overlapping` keeps each product's widest periods first and drops a row that overlaps one already kept. | `test_review_opus2b2_f41_overlapping_exports_are_counted_once` |
| F5.1 LOW: no cap shared with benchmark_refresh | `MAX_PURCHASE_REQUESTS_OPEN=3` across the `knowledge_gap:` and `benchmark_refresh:` prefixes. A listing benchmark_refresh already asks about is held. | `test_review_opus2b2_f51_one_cap_with_benchmark_refresh_and_no_double_ask` |
| F5.2 LOW: declined lines come back; a missing price shows CA$0 | A line whose request was closed rests for `SUPPRESS_DAYS_AFTER_CLOSE=56`. A pick with no observed price is never raised. | `test_review_opus2b2_f52_a_closed_line_rests_and_a_priceless_pick_is_never_raised` |

Not changed: F2.1's pre-existing loss of `teardown_qa` on re-certification. That belongs to
the owner of the re-certification path; only my own kind is carried.

## 25. Review OPUS2C (9c1a0037): every finding in opus2 code fixed (2026-10-31)

Report: `claude/w5-SECREVIEW-OPUS2C-9c1a003`. The verdict was ACCEPT for parts 1, 3 and 4, and
CHANGES REQUIRED for part 2 (F2-1 HIGH).

| Finding | Fix | Test |
|---|---|---|
| **F2-1 HIGH**: the photo-led certificate accepts a photo `sample_photo.qualifying_photos` rejects | `release_gates.sample_photo_lead` now asks that rule only. The lead qualifies exactly when the rule lists this photo id with this frame's SHA-256. The rule covers the owner's Command Center attestation of these bytes, a file the system did not make, a passed full make bound by `first_customer.physical_binding` to this release's content hash, rights, and bytes on file. Every attestation field comes from that one verdict, and the refusal carries the rule's reason. `owner_attested` was added to `listing_set.PHOTO_ATTESTATION`. There is no second photo standard. | `test_review_opus2c_f21_only_a_qualifying_photo_may_lead` covers (a) intake-unedited but not owner-attested, (b) an attestation of other bytes, and (c) a sha recorded with a provider. `test_the_photo_lead_takes_its_attestation_from_the_one_rule_only` is a static check that no rebuilt attestation remains. The positive fixture now binds the full make to the content hash and attests through `physical_upgrade.attest_unedited(actor="owner:cc:…")`. The `risk_matrix.physical_class_of` stand-in is now a no-op: the real classifier is on this base, and replacing it broke the rule. |
| F2-2 LOW: camera provenance read from the frame | Moot. It is derived from the qualifying verdict. | (as above) |
| N1.1 LOW: size-claim forms that got through | New patterns: `vessel_group` ("Market Basket Trio"), `named_range` ("small to large", "XS to 5X"), `multi_size` ("multi-size", "graduating sizes"), `dimension_tail_unit` ("Sizes: 20, 25 and 30 cm"), `dimension_slash` (a same-unit list; "20 cm / 8 in" stays one size), `article_named` ("a small, a medium and a large"), `vessel_count` ("3 baskets", "3-piece basket set"), and `named_plus` ("small + large"). | `test_review_opus2c_n11_n12_probe_rows_are_each_judged_as_the_review_expects`. Every review row is pinned, and the earlier pass rows still pass. |
| N1.2 LOW: "two hook sizes" read as a claim | A count whose in-between words name a hook or needle is advice. | (same) |
| N2.1 INFO: categories without a decoy entry can name another knitted item | `laura_home.KNITTED_OR_CROCHETED` is filtered from every category's clutter and moment, so the "no other crocheted or knitted item" sentence is true for every frame. | `test_review_opus2c_n21_no_frame_of_any_category_names_another_knitted_item` |
| N3.1 MED: a trio concept drafted as one basket | `fallback_constructions.plan(slug=, rationale=)` refuses a concept whose slug, title or rationale makes a size claim (`gates.size_claims`). The refusal needs "one certified release per size". Through the real handler, `market-basket-trio` is a retired alias that already routes to the three engineered sizes. `pumpkin-cluster-set` (3 sizes) is refused too. | `test_review_opus2c_n31_n32_several_sizes_and_shaped_categories_are_refused` |
| N3.2 LOW: the flat route takes shaped or charted categories | `NEEDS` gains `ornament` and `flower`. Title words gain `granny`, `hexagon`, `hexie` and `bed`. `mosaic_blanket` and `graphghan` are deliberately left on the flat route: they are flat fabrics, W-CONCEPT's intake refuses them upstream, publication's colourwork rule refuses a false mosaic claim, and `test_shadow` drafts a raw mosaic concept to prove bad arithmetic dies at the compiler. Refusing them broke that core test, so the refusal was withdrawn. | (same); `test_shadow` passes |
| N3.3 LOW: draft failures were not named refusals | `handle_cir_draft` turns `ValueError`/`KeyError` from a construction (including `UnknownStitch`) into `cir.draft_refused` with `gate: construction`. | `test_review_opus2c_n33_a_construction_that_cannot_be_built_is_a_named_refusal` |
| Test gap: vessel twin and reverse unasserted | The vessel test now asserts `build_twin` and `reverse.compare(...) == []`. | `test_a_basket_concept_drafts_a_vessel_…` |

**N3.2 follow-up for the integrator.** Once W-CONCEPT (accepted for Batch 5) merges, `NEEDS`
could import its `UNSUPPORTED_CATEGORY_WHY` so there is one table. I have not done it here,
because that branch is not on this base.

**Next construction (blocked; integrator's call).** Two colours per round, which would make
"Mosaic" titles truthful, needs a per-stitch colour in the CIR. `first_customer.colourwork_findings`
states it: "a CIR row carries one colour". That is a change to the shared model, compiler,
twin and writer, not a fallback rule.
