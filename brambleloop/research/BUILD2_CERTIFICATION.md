# Build 2 certification — defect ledger against candidate 63f2493

Candidate: `63f2493e1b5786cba660694f6ab78bc723127236`, tree `dbb99ff70ebc02f08db182bd932052de846538e8`,
frozen as branch `build2-candidate-63f2493` (pushed). Every defect below is recorded against
that candidate and repaired in an explicit follow-up commit.

| id | severity | area | defect (as found in 63f2493) | repair |
|---|---|---|---|---|
| C-1 | High | #320 acceptance | `intel/acceptance._latest_cycle` accepts any `seasonal.cycle_proof` audit row; a hand-written row with no job passes steps 10-12, though the contract says the proof must be recorded by a job. The test fixture encoded the pass. | pending |
| C-2 | Medium | #42 wiring claim | `commerce/cohorts.record_order` (which writes the bought version) has no production caller: no order ingest exists and Etsy receipts need the unGranted `transactions_r` scope. "Written at sale time" is overclaimed as COMPLETE. | pending |
| C-3 | Medium | cost governance tests | image-render reservation proven only by source-text order; no behavioural test that a spent ceiling sends nothing; the unknown-render-site guard was dropped. | pending |
| C-4 | Medium | #126 grid tests | the stand-in judge scores by URL prefix (the one side channel), and the median test uses identical judges, so median is never distinguished. | pending |
| C-5 | Low | tests | dead `if False` in the policy-knowledge digest check; vacuous loop in test_repeat; frame #1 STALE unasserted in the backfill sibling test. | pending |
| C-6 | High | benchmark firewall | `cir/specification.benchmark_matches` needs every benchmark piece contained; a partial relabel (body+sleeve of the cardigan) or trimming one row per piece certifies as ours | pending |
| C-7 | High | raglan construction | `garments.raglan_top_down` caps yoke increases at one per raglan line per round; dc raglans (incl. Pebble fixture) ship a neck edge 0.61-0.88 of the chest, back neck wider than cross-back at 3X-5X; no gate catches it | pending |
| C-8 | High | originality claim | `garment_design.design_for` reads only 4 concept fields; different concepts yield identical garments (at most 16 variants); non-garment concepts yield a fixed sc prototype rectangle | pending |
| C-9 | Low | assembly | drop-shoulder neckband 'opening' join passes specification but compiler warns ASSEMBLY_UNPLACED with an amigurumi message | pending |
| C-10 | Low | grading | built length falls 51.1 -> 50.6 cm (4X->5X, adult LONG fitted raglan): yoke and body rows rounded separately; monotonic check reads requested figures only | pending |
| C-11 | High | queue | `JobQueue.claim` on SQLite executes jobs more than once under concurrent workers (64 duplicates / 120 jobs, 6 threads): unconditional UPDATE by id | pending |
| C-12 | Medium | queue fencing | `complete/fail(worker=None)` overwrite a job another worker holds on a live lease | pending |
| C-13 | Low-Med | lease renewal | `JobQueue.heartbeat` not checked against the holder; a stale worker's renewal extends the new holder's lease | pending |
| C-14 | Medium | refusal classification | `deliberate_refusal` (health/verify/retention) and `requeue_dead` disagree for capability refusals outside store.publish | pending |
| C-15 | Medium | starvation | claim order `(priority, run_after, id)` has no aging; a band-200 job waited through 200 band-10 claims | pending |
| C-16 | Medium | build executor | `executor.complete` accepts completion of a PARKED/unclaimed task or one claimed by another worker | pending |
| C-17 | High | learning authority | `cells.promote` never requires an approval | pending |
| C-18 | High | learning authority | separation of duties skipped when `proposed_by` is empty | pending |
| C-19 | Medium | learning authority | actor names not normalised ('Listing', 'listing ') | pending |
| C-20 | High | governance | 10 gate/Product-Truth weakening phrasings and touches pass `governance.check` (verb forms, synonyms, distance, numeric constant edits, plain-words Product Truth, touch spelling) | pending |
| C-21 | High | tiers | 11 of 12 protected gates tier as `code`, not `gate`: a product_truth change promotes without owner approval | pending |
| C-22 | Medium | director | conflict detection compares raw touch strings ('Weights ' vs 'weights') | pending |
| C-23 | Medium | identity | `model_registry.gate_frames` passes a model frame with no `conditioned_on` hashes (should be unverifiable) | pending |
| C-24 | Medium | identity | superseded body frame bytes returned as reference when the pack is unhashed; no manifest superseded check | pending |
| C-25 | Low | identity | redesign approval truncates non-integer versions, never validates `at` | pending |
| C-26 | Low-Med | identity | approval without `approved_by` audited as the owner | pending |
| C-27 | High | provenance | worker backstop satisfied by a bare `record()` row (no creator, no job) | pending |
| C-28 | Medium | provenance | `ArtifactStore.put` accepts `lineage={}` / a string / an empty Lineage for watched classes | pending |
| C-29 | Medium | provenance | conflicting lineage for the same class+key silently overwritten, no history | pending |
| C-30 | Medium | provenance | a backfilled write can downgrade a recorded row | pending |
| C-31 | High | cost | `release.py` cycle-proof and `main.py` seasonal route build ModelGateway with no registry: no ceiling, reservation or ledger | pending |
| C-32 | Medium | cost | agent daily ceiling ignores other holders' live reservations | pending |
| C-33 | Medium | cost | provider ceiling ignores other holders' live reservations | pending |
| C-34 | Medium | cost | gateway ledger rows lack provider/model/purpose/estimate: drift unreconcilable, provider ceiling never binds on gateway spend | pending |
| C-35 | Low-Med | cost | gateway prices an unpriced model from the provider's own (possibly zero) rates | pending |
| C-36 | Low | cost | NaN / negative estimates pass a spent month | pending |
| C-37 | Low | cost | `images.generate` with no provider crashes (AttributeError) instead of refusing | pending |
| C-38 | Medium | gates | `owned_surfaces` opens on an environment variable; `customers` counts any ledger row (an expense); `tester_roster` counts any profile | pending |
| C-39 | Medium | closure | `closure.classify` accepts any data_gated row with no machinery (#82, #89, #276, #298 had none) | pending |
| C-40 | Medium | registry | executable work parked as gated: #2, #15, #98 (search half), #236, #168; wrong gates: #1, #37 (owner Insights), #189, #221, #222, #320 (owner ruling), #277, #281 (funding) | pending |
| C-41 | High | false completion (ids 1-160) | 66 rows claimed COMPLETE are libraries unreachable from the running system (proof-chain audit): 5, 24, 25, 28, 33, 34, 35, 36, 38, 41, 43, 45, 46, 48, 58, 60, 63, 65, 66, 68, 70, 76, 80, 83, 87, 88, 92, 95, 101, 105, 108, 110, 114, 115, 116, 117-122, 124, 125, 126, 131, 134-139, 141-143, 145, 146, 151-160 (#42 already re-parked under C-2); reopened | pending |
| C-42 | High | support path | `support.reply` / `support.triage` handlers are registered but never enqueued and have no cadence: the concierge path is unreachable | pending |
