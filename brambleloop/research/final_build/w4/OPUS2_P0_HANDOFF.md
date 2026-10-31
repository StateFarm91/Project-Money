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
