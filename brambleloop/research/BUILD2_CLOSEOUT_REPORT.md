# Build 2 closeout report — 2026-09-27

Branch `claude/visual-investigation`, HEAD `5c777c9` (pushed). Integrated branch untouched at
`fcb982d`. Read live: `/api/closure`, `/api/build2`. Decisions D-B2C-1..12 in DECISION_LOG.

## A. Verdict
**Build 2 engineering: COMPLETE.** Every one of the 320 requirements is in one final state;
OPEN = 0; full suite 4,615 passing, 0 suites failing. Not deployed: production still runs
`fcb982d` (see S), and three owner actions gate what can run live (see E).

## B. Before → after
| | before (2026-09-26 registry) | after |
|---|---|---|
| registry: covered / partial / owner / data | 227 / 45 / 28 / 20 | 235 / 45 (all parked, 0 ready) / 20 / 20 |
| closure: COMPLETE+PROVEN / OWNER / DATA / EXTERNAL / OPEN | 161 / 27 / 42 / 19 / 71 (first audit) | 235 / 28 / 42 / 15 / **0** |

## C. Implemented / fixed (subsystem · gap · fix · evidence · commit · kind)
- Etsy knowledge · six policy surfaces never read, 6 P2 incidents · dated readings with basis, watch seeds + resolves, page-reading intake, fee schedule, AI disclosure ERROR · test_policy_knowledge 19, test_policy_intake 8, test_fee_schedule 7 · ca368e8, bef5597 · production code, tests
- Closure/registry · 67 covered rows unproven, no final-state vocabulary · closure.py, proof field, /api/closure, 67-row audit (44 proven, 17 downgraded, 3 directives) · test_closure 12 · ca368e8, 3bcb492, 8137d14 · code, data, tests
- Canonical model · unhashed face fallback, no manifest, no replacement procedure, hardcoded /api/model-pack, poisoned dead letter · MANIFEST.json, hash-pinned references, provenance_check in frame gate, replace_canonical, stand-aside · asset_manifest 8, model_identity 28, model_freeze 20, reference_pack 44, portrait_repair 24 · e5498b0, a49f1df · code, data, tests
- Learning loop · 12/12 cells unmeasured, 0 lessons, loop unwired · measure/mine/bootstrap/monitor/director, separation of duties, conflict block, rollback incidents, brief read-back, cadences · test_measure 7, test_mine 7, test_improve_director 14, test_improve_handlers 8 · f1c34d8, bef5597, de1f491 · code, tests
- Cost governance · "No spend limits configured", escalation only on GET, unreserved image/gateway spend, two BudgetExceeded classes, date-dependent test · governance block, finance.escalation_check, pre-call reservation, unified hierarchy, refusal audit, empty owner-number tables · test_escalation 8, test_dashboard_spend 5, wave2 39/39 · e5498b0, 6b4fc6b, 21df8c0 · code, tests
- Provenance · only one writer; 275 unproven · fail-closed lineage path, worker backstop, lineage columns, evidence-only backfill, /api/provenance by class/source · test_provenance_write_path 19, test_provenance_backfill 12 · e5498b0, 6b4fc6b · code, schema, tests
- Orchestration/incidents · loop could not complete work yet alarmed "stalled"; no fencing; detectors never resolved; seasonal logic stale · awaiting_build_session, model_bearing_render gate, lease fencing + worker lease renewal, incident lifecycle, event/year-keyed evidence-aware seasonal detectors, /api/incidents · executor 36, chaos 30, incident_lifecycle 7, seasonal_incidents 6 · e1fa6e9, de1f491 · code, tests
- Original design · no grading, garments unauthorable, reverse/writer texture- and piece-blind, certify first-piece only · graded.py (CYC tables), shaping.py, garments.py templates, garment_design.py concept route, loop-aware per-piece reverse, specification+assembly in certify, benchmark-containment refusal, schematic, asset truth over all pieces · garments 8, graded 8, shaping 8, schematic 4, garment_design 9, reverse 18, certification 12 · bef5597, afde931 · code, tests
- Runtime wiring (17 overstated rows) · correct libraries nothing called · swarm handlers, priority bands at enqueue, order-version table, persisted experiments, diversification, culture recurrence, adaptive scan, escalation ladder · swarm_runtime 10, trust_wiring 8, experiment_persistence 4, gallery_escalation 4 · bef5597, deee083, de1f491 · code, tests
- Parity/intel · COMPETITIVE had no writer; LIFESTYLE read a field product frames never wrote; #126 grid had no judges; #320 runner covered 9 of 13 steps · blind_review, benchmark_set, parity realism reader, three-judge vision panel, 13-step acceptance · blind_review, benchmark_set, parity_realism_reader 5, blinded (+4), acceptance 7 · afcf36d, 3c2a0be, de1f491 · code, tests
- Commerce scale · cohorts, kill table, repeat, paid-media economics, leading board absent · built with UNMEASURED/refusal semantics; no path can spend · cohorts 5, kill_table 7, repeat 6, leading 6, paid_media_economics 9 · bef5597 · code, schema, tests
- Dashboard truth · 45 parked rows shown as 45 "executable left" · ready vs parked split + closure on console · test_build2 (+1) · 0d7e0dc · code, tests

## D. Final closure matrix (235 / 28 / 42 / 15 / 0)
- COMPLETE+PROVEN 235: every covered row names a module that exists and a test that exercises it (3 are process directives recorded as followed: #32, #56, #197).
- OWNER-GATED 28 — owned_surfaces 4, 10, 246, 247, 248, 251, 255 · tester_roster 9, 250 · live_listings 14, 16, 254, 261, 262, 263 · offsite_storage 51 · physical_proof 64 · benchmark_purchases 165, 168, 315, 317 · ad_authority 242, 243, 244, 245, 294, 295 · image_generation 300.
- DATA-GATED 42 — customers 3, 8, 13, 18, 19, 20, 21, 22, 26, 29, 31, 233, 234, 249, 253, 256, 257, 258, 259, 260, 280, 292 · status data_gated 11, 12, 23, 82, 89, 94, 98, 104, 128, 132, 140, 235, 237, 238, 239, 252, 268, 276, 296, 298.
- EXTERNAL-BLOCKED 15 — rendered_pages (Etsy 403) 1, 2, 15, 37, 39, 189, 221, 222, 236, 277, 281, 320 · model_bearing_render (provider fidelity) 72, 130, 202.
- Registry note: 45 rows keep the registry status "partial" because something real is built and the remainder is parked on a named gate; the executor releases them automatically when that gate opens. None is ready to start (`executable_unparked` = 0) and each carries its final closure state above.

## E. Owner actions
| action | why only the owner | time | cost | unlocks | delay consequence | needed before |
|---|---|---|---|---|---|---|
| Fund the Anthropic API (actions 19/20 duplicate) | payment method | 5 min | within the CA$100/month ceiling in code | model_provider, image_vision, image_generation: blind-review evidence, grid judges, gallery vision, cycle proof, #300 | parity and #320 stay unjudged | staging |
| Decide if API+vision traversal satisfies "browser/vision" (#222, #320) | interpretation of the owner's own requirement | 2 min | 0 | acceptance grades stop being provisional | grades stay provisional | staging |
| Authorise deploying this branch after review | deployment authority | 10 min | 0 (infra ~CA$7/mo) | incident fixes, policy seeding, backfill, new cadences live | 17 production incidents persist | staging |
| Etsy identity, payout, shop activation | KYC, banking, legal | 30–60 min | Etsy fees | live_listings (6 rows) | no listing | public launch |
| Paid-media authority (scope `ads`) | spend | 5 min | owner-set cap | 6 rows | no ads (organic only) | after organic proof |
| Benchmark purchases + intake | spend | varies | ≤ CA$300 governed | #165 #168 #315 #317 | deliverable comparison missing | limited production |
| Owned surfaces (site/Pinterest), offsite storage, tester roster | accounts/people | 30 min each | small | 10 rows | owned channels idle | limited production |
| A physical sample or paid tester | physical object | days | ≤ CA$25 tester | yarn calibration, class C fit, proof rung 3 | estimates stay ±20% | public launch |

## F. Data gates
All 42 need evidence that cannot exist in Shadow Mode: orders, customers, traffic, impressions, reviews, conversion and a season's history. Derivation is impossible because no listing is live and no one has bought. The evidence arrives after launch through the order path (cohorts.record_order writes customer, order and version), the Etsy transactions_r scope (owner), Stats CSV intake (commerce/attribution) and time. Each module already reports UNMEASURED or refuses rather than fabricate. Launch can safely occur without them: they are optimisation, not safety. Physical calibration is separate: it needs a sample and is required before claiming yardage beyond ±20% or releasing class C garments.

## G. External blockers
- Etsy policy/search/Insights pages (12 rows) · Etsy bot protection · HTTP 403 to two independent fetchers (B-268, B-500, 2026-09-26) · works: official API, image vision, dated excerpt readings, person-recorded snapshots · fails: automated page reads · fail-closed: readings carry their basis and go stale on 30 days · next: owner or tester reads the six pages via POST /api/policy/snapshot · Build 2 can close with it documented: yes.
- Model-bearing / stitch-faithful render (#72, #130, #202) and **Product-Only Visual V1** · image providers (gpt-image-1.5; gemini) · 0 of 16 draws certified (VISUAL_V1_GRADUATION, 4cf6959), 0 of 7 (VISUAL_BENCH2, ad81e30) · works: blind deterministic Product Truth/CIR/reference chain, instruments, gates · fails: generator stitch-structure fidelity · fail-closed: model_bearing_render gate stays closed, parity blocks release · next: folded-view reference + presentation sentence, ~US$1.50, not run · closable documented: yes.

## H. Original-design capability
Generalised: a concept's form, construction, recipient, lane and premise choose, by rule, a CIR builder. Flat, round, vessel, texture and motif forms have geometry; garments now route through `creative/garment_design.py`. Evidence: the catalogue (throws, baskets, coasters, pillows, cable throw) plus two garment templates proven by two original designs at every sourced size (Harbour pullover 9 adult sizes; Pebble raglan 8 child sizes) and an autonomously designed raglan that survives the full release chain.
- garments: drop-shoulder and top-down raglan templates. Toys, cones, garlands and wreaths are still unsized and refused by name.
- grading/sizing: function-of-size from sourced CYC tables; unsourced measures refuse; monotonic check.
- stitch topology: loops, holds/resumes, skips carried through JSON, writer and reverse.
- construction: flat rows, joined/spiral rounds, yoke division, seams.
- yarn/gauge: gauge from yarn weight bands; yardage summed over pieces; calibration data-gated.
- pattern writing: US and UK, loop-aware, per piece.
- charts/schematics: stitch charts; schematic page for multi-piece designs. Shaped pieces are drawn at their widest row, which is a known limit.
- Product Truth and CIR: unchanged digests for existing products.
- provenance/originality: `CIR.provenance`, and benchmark-containment refusal.
- technical validation: compile, reverse, specification, assembly and certify.
- Visual handoff: unchanged, gated by parity.
- Generalised vs demo: the templates and the concept router are general. The two named garments are demonstrations of the templates, and a third, generated concept proves the route.

## I. Canonical model
Recovered: yes, from evidence. The approved face is the committed `visual/assets/identity_portrait.jpg` (sha a42aeac7…), recorded in MANIFEST.json as `approved_face`. The approved v15 body frames live only in production DurableArtifact storage, referenced by sha256.
- Record: model_identities `brambleloop-canonical`, version 1, approved 2026-09-22.
- Strategy: reference_hashes are written at freeze; `reference_paths` hands out only files whose bytes match; the manifest distinguishes approved, superseded and owner-concept assets.
- Enforcement: the model_registry frame gate plus `identity.provenance_check`. A frame conditioned on other bytes, or on unhashed ones, is refused or unverifiable.
- Validators: eight enforcement_proof checks, including references_are_the_approved_bytes.
- Replacement: `replace_canonical` requires an owner approval record, retires the old row and never deletes it. It was not used.
- Owner gate: the approved pack fingerprint exists only in the production audit row, so it is left None rather than invented. No substitute model was generated.

## J. Continuous learning
The loop runs on a cadence: measure (daily, a deterministic query per cell) → mine (six-hourly; incidents, gate blocks and dead letters become idempotent routed Lessons) → self-review proposals → sandbox and tests → independent approval (the proposer cannot approve or promote) → tier-gated promotion (weekly runs only approved scoring-tier changes) → monitor (a regression below baseline reverts it, opens an improve-rollback incident and publishes a Lesson).
- Evidence storage: CapabilityPoint, Lesson and Improvement rows, plus the audit log.
- Cross-product learning: creative briefs read the `product_creativity` inbox and record design provenance.
- Provider performance: league incumbents are registered and trial verdicts record the measured outcome. No challengers run, so nothing spends.
- Overfitting protection: the Improvement Director blocks conflicting changes, and survival is reported beside the research kill rate so a soft jury is visible.
- Gate protection: any proposal touching a gate, threshold or Product Truth is refused end to end. A test proves 110 constants and the cable-throw Product Truth digest are unchanged after nightly and weekly runs.

## K. Cost governance
"No spend limits configured" was true of one empty table: SpendLimit, the paid-media scoped caps. It was false of the company. The dashboard now shows each control.
- Global: CA$100/month ceiling, checked before every call and in code.
- Provider: `PROVIDER_CEILINGS_CAD` mechanism exists and is empty, pending owner numbers.
- Agents: 24 daily ceilings, checked before calls on the gateway path too.
- Task/experiment: the benchmark CA$50, trial and portrait-repair caps, and experiment `max_loss`.
- Concurrency: a reservation before every model and image call.
- Accounting and reconciliation: CostEntry, estimate drift, and a refusal audit.
- Runaway protection: retry backoff, the budget stop in the worker, and one exception hierarchy.
- Owner-configurable values: provider ceilings, department allocations, paid-media caps and ceiling changes.
- Dashboard: the governance block, ending "Scoped caps (paid media): none configured -- advertising authority not granted".
- Tests: escalation 8, dashboard 5, wave2 39, spend_governance 35, gateway 30, model_spend_paths 12.
- The missing owner numbers are not a missing mechanism.

## L. Provenance
- Investigated: 275 artefacts, all unproven in production. That count is a lower bound; pdf, chart and pricing artefacts are now enumerated too.
- Backfilled: 0 so far. The evidence-only backfill (`ops.provenance_backfill`) runs in production and has not run because the branch is not deployed.
- Backfill rules: certificate rows need a matching release hash; visual rows need a sha match to a build output; marketing rows need a match inside a job's time window. Anything unmatched stays UNPROVEN. code_commit is "unknown" for every backfilled row.
- New enforcement: a fail-closed write path on every chain handler, and a worker backstop that is log-only until the backlog closes, then enforcing.
- Schema: created_by, job_id, code_commit, provider, model, cost_cad, sha256, parents, validation_status, publication_authority, source and evidence.
- Tests: write_path 19, backfill 12, artefacts 23.
- New important artefacts without provenance: not through the chain handlers. The worker backstop audits any gap.

## M. Orchestration
- Discovery: the requirement registry.
- Prioritisation: section weight, and job bands applied at enqueue.
- Queueing: idempotent keys.
- Execution: permission-checked handlers.
- Completion: fenced to the lease holder.
- Retries: backoff, three attempts.
- Dead letters: deliberate refusals are classified, and the stale pack re-drive stands aside.
- Blocking: 18+1 checkable gates.
- Stale-job cleanup: retention.
- Crash recovery: lease reclaim.
- Idempotency: enqueue keys and backfill.
- Concurrency: SKIP LOCKED, fencing, and lease renewal capped at an hour.
- Starvation: bands instead of period-based priority.
- Progress metrics: completions, evidence freshness excluding self-observing jobs, and scheduler liveness from cadence keys.
- Cause of the idle periods: the deployed loop cannot write code or complete a requirement. Only a session editing the registry can. The watchdog therefore measured session cadence and called it "stalled". It now reports `awaiting_build_session` and resolves `build.stalled`.
- Four "ready" rows were unfinishable (#72, #75, #130, #202). Those are now parked, or closed in #75's case.

## N. Incidents
There were 17 before, and there are still 17 in production because nothing was deployed. With this branch deployed, the classification is:
- 6 policy_stale: fixed. Seeding resolves them with the snapshot named.
- 5 seasonal.at_risk: stale. Four are missed and one is a product not targeting the event. They are resolved with the recommendation.
- 2 calendar_behind: invalid. No milestone could ever be marked done.
- 2 preparation_late: stale. The work was running without evidence being read.
- 1 build.stalled: structural. It resolves as awaiting_build_session.
- 1 stale-artefact backlog: legitimate. It remains until the backfill and new write path close it.
- Owner actions 19/20 are duplicates, to be merged on deploy.
- The dashboard agrees only after deploy.

## O. Commerce/Etsy
- Engineering complete: publishing path, fee schedule, AI disclosure, publish hash check, cohorts, paid-media arithmetic (no spend path), leading indicators.
- Policy/research complete: dated excerpt readings of six surfaces and six topics. The Canadian regulatory fee is UNKNOWN.
- Owner action required: KYC, payout, shop activation, fee acceptance, ads authority.
- Launch-time: taxonomy read-back, live listing, transactions scope.
- The shop is not operational for sales: it is created, empty, with zero sales, and nothing is published.

## P. Pattern/product quality
Mechanically validated:
- stitch and row arithmetic, holds, assembly
- grading (monotonic, sourced)
- gauge consistency
- yardage estimates (±20%)
- US and UK instructions reverse-compiled, loop-aware
- charts, and schematics for multi-piece designs
- difficulty and accessibility
- page integrity
- PDF hash equal to the certified bytes at publish
- revision handling (chain version, certificates restart)

Still needs physical or customer evidence: yarn calibration, gauge truth, fit of class C garments, maker-tested proof, and download experience with buyers.

## Q. Visual
- Blind deterministic Product Truth/CIR/reference chain: PASS (frozen 9cf29f5).
- Validators: instruments, gates and parity eight-dimension, with realism now read for product frames.
- Image-generation provider: fidelity insufficient, 0/16 and 0/7. The production gate is also closed on funding.
- Product-Only Visual V1: NOT LOCKED.
- On-model: EXTERNAL-BLOCKED (model_bearing_render).
- Canonical-model requirement: enforced in code on the approved identity. No on-model frame passes yet.

## R. Tests
Focused suites were run per subsystem during integration. Added adversarial and regression tests include:
- gate weakening refused
- Product Truth weakening refused
- a proposer self-promoting refused
- a tampered face
- an older pack stamp
- a reclaimed job completing (refused)
- lease renewal and its cap
- a silent judge
- the ceiling reached before a judge call
- a benchmark relabelled as Brambleloop's
- a loop flipped in a pattern
- a multi-piece asset-truth case
- a stale snapshot not closing its incident
- no spend path in the commerce modules

Final full suite: **4,615 passing, 0 suites failing** (5c777c9's parent b80c31a).

The claimed pre-existing failure `test_a_spender_the_registry_has_never_heard_of_gets_no_invented_ceiling` was reproduced (wall-clock date vs frozen NOW) and fixed by passing `now=NOW`. Two fixture corrections are recorded, with reasons in the test files: an unrealistic gateway price, and a provenance expectation contradicting its sibling test. No test was skipped or disabled, and no threshold was weakened.

## S. Deployed state (read-only)
Production is at fcb982d.
- /api/verify: 12/12.
- Queue: done 5,399, dead 166.
- Open incidents: 17.
- Owner actions: 9.
- Build2: 227/45/28/20.
- Provenance: 275 unproven.
- Improve: 12 cells unmeasured.
- Gates: model_provider, image_vision and image_generation closed.

Everything in C exists only on `claude/visual-investigation`.

## T. Git
- Branch: claude/visual-investigation.
- HEAD: 5c777c9, pushed; working tree clean.
- Preserved: 4cf6959, 9cf29f5, ad81e30, fcb982d (integrated branch untouched).
- Closeout checkpoints: ca368e8, 4fc37b1, 17e33f9, f1c34d8, 3bcb492, e5498b0, a49f1df, 8137d14, 6b4fc6b, 21df8c0, c9165ac, afcf36d, e1fa6e9, bef5597, deee083, de1f491, 3c2a0be, de405f2, 0d7e0dc, afde931, b80c31a, 5c777c9.
- The local tag `build2-closeout` could not be pushed: the proxy refuses tag refs.
- No merge, deployment, publication, Etsy change, advertising spend or paid Visual generation occurred.

## U. Handoff to the Final Build
```json
{"build2": {"state": "engineering complete, not deployed", "head": "5c777c9",
  "closure": {"complete_proven": 235, "owner_gated": 28, "data_gated": 42, "external_blocked": 15, "open": 0}},
 "final_build": [
  "deploy the Build 2 branch after owner authorisation and verify incidents resolve (N)",
  "first production runs of provenance backfill, blind review, grid judges, acceptance once funded",
  "Visual: the documented folded-view experiment only if the owner funds it (G)",
  "launch path: Etsy KYC/payout/activation, first live listing, transactions scope (O)",
  "physical sample: yarn calibration and class C fit (P)"],
 "not_final_build": "no Build 2 requirement remains executable; gated items reopen automatically when their gate opens"}
```
