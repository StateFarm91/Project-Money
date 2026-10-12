# FINAL BUILD BASELINE AUDIT — Brambleloop Final Master v1.0

2026-09-28 · integrator: Claude (this session) · basis: certified Build 2 engineering **019ebf0**,
production **fcb982d** · spec `spec/09_Brambleloop_FINAL_Master_v1.0_Audited.pdf` (sha256 526ed69c…a99).

Machine-readable sources (this document summarises them; they are authoritative):

| artefact | what it is |
|---|---|
| `master_registry.json` (`parse_master.py`, pinned by `tests/test_final_master_registry.py`) | every requirement F-001..F-879 with source lines, version, section, stated priority, supersessions |
| `module_reachability.json` | per module: reached from a live runtime root on 019ebf0 (C-65 call-graph rule); present in production tree fcb982d |
| `mapping/s1..s9.json` + `MAPPING_BRIEF.md` | nine disjoint worker mappings (proposals, not verdicts) |
| `aggregate.py` → `closure_matrix.json` | integrator adjudication: every row, final maturity, claimed maturity, downgrade reasons |

Nothing was merged, deployed, published or spent in producing this audit. Phase remains shadow.

---

## 1. Registry (complete parse)

- **866 requirement records, 859 distinct IDs** in the declared space F-001..F-879.
- **Absent: F-631..F-650** (20 IDs). v0.18 ends at F-630 and v0.19 starts at F-651; section
  numbering also jumps 64→67. No text anywhere defines them. Recorded, not invented.
- **Collision: F-514..F-520** are defined twice — v0.15 "Registry additions" (Outcome-Based
  Improvement … Controlled Self-Improvement) and v0.16 (Etsy Surface Inventory …). v0.16 cites
  "F-501–F-513" as the prior Etsy set, i.e. its author did not intend to replace v0.15's 514–520.
  Neither text says it supersedes the other and they do not conflict, so **both remain in force**
  as `F-5xx@v0.15` and `F-5xx@v0.16`. (D-FB-2)
- Records by version: v0.1 60 · v0.2 30 · v0.3 30 · v0.4 58 · v0.5 28 · v0.6 14 · v0.7 12 ·
  v0.8 68 · v0.9 30 · v0.10 20 · v0.11 20 · v0.12 30 · v0.13 50 · v0.14 50 · v0.15 20 · v0.16 37 ·
  v0.17 50 · v0.18 30 · v0.19 50 · v0.20 30 · v0.21 18 · v0.22 40 · v0.23 10 · v0.24 32 · v1.0 49.

## 2. Conflicts and supersessions (adjudicated)

| # | source | adjudication |
|---|---|---|
| S1 | v0.23 s78–79: F-789..F-798 supersede F-781..F-788 **where conflicting** | Private full reverse-engineering of purchased patterns is allowed (F-789, F-797). The publishable boundary stays: no protected text/images, no light derivative (F-790–F-792, F-795, F-798). F-781's "never fed into a publishable drafting path" survives as F-792's "competitor file excluded from the final instruction-writing context once the spec is frozen". |
| S2 | v1.0 s91: F-831..F-840 supersede any weaker notion of completion | Every row in this matrix is judged by the proof chain; Build 2 "COMPLETE+PROVEN" is evidence, not a Final Master verdict. |
| S3 | v1.0 s91: F-851..F-860 change the Visual default to B+C | F-674/F-676 (v0.19 "downstream AI photoreal image") are read through F-852: AI supplies presentation around a protected product region, not the product. The main-line generative product redraw (`publish/owned_photography.py`, `model_photography.py`) is the superseded direction — a defect against F-852, not a satisfied F-676. |
| S4 | line 1079: identity scores from the broken protocol are superseded | Old identity scores are not evidence (already enforced in Build 2). |
| S5 | F-685 "9 days remain" (2026-09-25 owner evidence) vs F-686 "countdown alone cannot change state" | Store the owner evidence with its date; never derive ELIGIBLE from arithmetic; recheck on the date. |
| S6 | F-614 (v0.18: shop shows Etsy Plus credit) vs Build 2 surface registry (assumes no paid subscription) | Master is newer owner evidence → the registry entry is stale; correct it and record the credit as non-cash (F-688). |
| S7 | F-071 "owner is not the tester" vs `products/launch0.py:1240` "owner action to crochet samples" | Master wins; wording is a defect (cluster C). |
| S8 | v0.1 P1 list (F-032..F-038, F-044, F-045, F-050, F-051, F-053..F-057) vs "launch-critical" P0 addenda | P1 items are MATURE (after real traffic) per source line 275. |
| S9 | v0.24 s84 launch list vs "Learn is a permanent department" | Launch needs Learn *architecture*, knowledge graph, gap detection, pattern/support links, provenance, correctness QA and the queue — not curriculum depth, video, email, lead magnets. |
| S10 | F-857 blind original graduation (Visual V2) vs launch | Graduation is required before any **photoreal product image** is published. It is not required to launch a listing whose imagery is deterministic and truthfully presented (schematic/render, disclosed). Launch therefore does not wait on V2 unless the owner requires photoreal heroes (D-FB-4). |

## 3. Maturity distribution (adjudicated, 866 rows)

Maturity is the highest level genuinely proven for the row's applicable chain. Levels are kept
distinct (F-844). Coverage: **150 FULL · 716 PARTIAL** — most rows have a real proven part and a
named missing part (`missing_part`).

| maturity | all | launch-critical |
|---|---|---|
| MISSING | 165 | 63 |
| IMPLEMENTED | 86 | 34 |
| TESTED | 47 | 26 |
| INTEGRATED (reached from a live root on 019ebf0) | 302 | 129 |
| DEPLOYED (behaviour present in production fcb982d) | 247 | 175 |
| EXERCISED (committed production artefact) | 19 | 19 |
| PRODUCTION-OBSERVED | 0 | 0 |
| COMMERCIALLY-EVIDENCED | 0 | 0 |

**Integrator adjudication applied mechanically (`aggregate.py`), 123 rows lowered from the
worker's claim, each with its reason in `adjudication`:**
- **EXERCISED requires a committed production artefact** (`research/b2_resume/evidence/prod_*`):
  106 rows whose exercise evidence was BUILD_STATE prose or UI recollection were capped at
  DEPLOYED. Status prose is a secondary record; UNKNOWN stays UNKNOWN (D-FB-3).
- **TESTED+ requires a cited test that exists**: 20 rows cited none → IMPLEMENTED.
- **INTEGRATED+ requires the producer module reached from a live root; DEPLOYED+ requires it in
  fcb982d** (1 row lowered on producer citation). Some rows hit two rules; 123 distinct rows moved.
- Nothing reaches PRODUCTION-OBSERVED or COMMERCIALLY-EVIDENCED: no live listing, customer,
  order or revenue exists.

Confidence of the underlying mappings: HIGH 296 · MEDIUM 536 · LOW 34.

## 4. Launch-critical vs mature

| class | rows | rule |
|---|---|---|
| LAUNCH-CRITICAL | 446 | customer-protective first sale: Product Truth, correct patterns, truthful Visual/listing, safe publication, marketplace compliance, order/customer truth, pricing/economics integrity, provenance, support/remedy, authority/spend controls, durability, recovery/idempotence, truthful owner visibility; plus source-stated P0 and v0.24 s84 launch list and the F-831..F-850 contract |
| MATURE | 413 | post-launch growth, optimisation, Studio polish, research depth, learning loops, Ads (disabled until owner authority, F-875), video/email/social, P1-after-traffic |
| NA | 7 | F-414 (pure permission), F-468, F-500, F-520@v0.15, F-698, F-717, F-842 (statements; their enforceable parts are mapped elsewhere) |

Launch-critical share by addendum is highest in v0.8 (57/68), v0.9 (29/30), v0.4 (43/58),
v0.1 (38/60), v1.0 (34/49), v0.22 (30/40); lowest in v0.13 (8/50), v0.14 (7/50), v0.17 (14/50).
Worker launch-class calls were accepted except where §2 adjudicates. Garment-only Product Truth
rows (F-754, F-757, F-763, F-765) stay LAUNCH-CRITICAL but **bind only when a garment is
listed**; Launch-0 is a basket set and a baby blanket.

## 5. Already satisfied

- **52 launch-critical rows are satisfied end to end** (INTEGRATED or higher, FULL coverage, no
  defect): F-012, F-029, F-064, F-079, F-084, F-087, F-101, F-102, F-104, F-108, F-132, F-137,
  F-138, F-141, F-142, F-143, F-163..F-166, F-207..F-211, F-220, F-223, F-228..F-230, F-232,
  F-241, F-256, F-267, F-272, F-277, F-292, F-302, F-327, F-336, F-361, F-376, F-379, F-395,
  F-440, F-471, F-513, F-519@v0.15, F-735, F-776, F-780, F-781. Strongest areas: whole-person
  canonical identity gate (v0.6), dual verdict (v0.7), hard spend reservations, durable queue,
  Build 2 certification machinery.
- **210 further launch-critical rows are INTEGRATED+ with no defect but PARTIAL**: the proven part
  runs; the named `missing_part` is the remaining work (often a gated half).
- **Build 2 not deployed**: every behaviour added after fcb982d is at most INTEGRATED. Deploying the
  Final candidate (owner-authorised) is what moves ~300 rows toward DEPLOYED/EXERCISED.

## 6. Genuinely missing executable work (launch-critical, not gated)

**103 launch-critical rows are below INTEGRATED with no gate; 87 launch-critical rows carry a
defect.** Grouped into disjoint execution clusters (file ownership disjoint; one integrator):

| cluster | owns | requirements | headline defect |
|---|---|---|---|
| **A · Listing search truth** | `commerce/seo.py`, `commerce/search.py`, new `commerce/category.py`, `publish/release_gates.claims_of` | F-002..F-009, F-011, F-014, F-015, F-020..F-026, F-245, F-250, F-251, F-294, F-298 | one hard-coded taxonomy 66 for every product; attributes never reach Etsy; tag/category edits don't invalidate the certificate; 9–10 tags where 13 are required; stuffed titles only audited |
| **B · Etsy publish/readback/observation** | `integrations/etsy*.py`, `runtime/pipeline.py::handle_store_publish`, new store.activate + shop/listing census cadences, `intel/etsy_surfaces` wiring | F-007 (transmission), F-515@v0.16, F-524, F-540..F-544, F-547, F-553, F-559, F-568, F-577, F-585, F-593, F-594 | store.publish sends **no image bytes** (draft unactivatable), no activation handler, no read-back on the production path, no file verification, shop/listing collectors tested but unwired, readiness `etsy_integration` hard-coded false |
| **C · Product truth & pattern gates** | `gates/certificate.py`, `runtime/pipeline.py::concept_to_cir/handle_certify`, `launch/readiness.py` (legacy count), `publish/eligibility.py`, `cir/model.py`, `publish/pdf.py` | F-071, F-074, F-078, F-081, F-086, F-090, F-111, F-112, F-116, F-118..F-120, F-175, F-363, F-754, F-757, F-765, F-783 (certify side) | physical evidence bound to no version (Class C can never unblock); gauge outside the yarn band printed as a warning; live authoring hard-codes worsted 16/10cm; legacy products count toward readiness and are refused only by shadow mode |
| **D · Money & order truth** | `finance/*`, `commerce/orders_ingest.py`, LedgerEntry migration | F-273, F-283, F-289, F-321..F-325, F-329, F-558, F-608, F-609 | P&L shows CA$0.00 as measured while the order source is disconnected; modelled fees stored as charged; every order labelled `etsy`; no break-even / sustainability gate |
| **E · Owner visibility, security, dashboard truth** | `app/main.py`, `build2/executor.approval_inbox`, `ops/health.py`, `ops/dependencies.py`, `/api/verify`, opsauth | F-128, F-131, F-179, F-181, F-182, F-185..F-189, F-196, F-202, F-203, F-205, F-206, F-663, F-665, F-689, F-696 | **customer support text readable unauthenticated at `/api/support`**; health reads env-var presence as HEALTHY; two owner-action sources; CA$5K card says "effectively zero" instead of UNMEASURED; cards for gates that unblock nothing |
| **F · Release, supply chain, ops tooling** | `requirements.lock`, `Dockerfile`, `run_tests.sh`, new `tests/test_secret_scan.py`, `ops/credential_register.py`, `ops/waiter.py` | F-123, F-154, F-158..F-160, F-169, F-170, F-334, F-337, F-340, F-344..F-347, F-350, F-416, F-461 | dependencies unpinned (`>=`), no secret scan, no credential rotation register, suite log not bound to SHA/clean tree |
| **G · IP firewall & originality** | `creative/preengineering.py`, benchmark licence model, new design-difference ledger, `gates/asset_truth.py` | F-783, F-785..F-788, F-791, F-794, F-795, F-798 | provenance optional and unconsumed; no licence record per purchase; no redesign gate; similarity review excludes benchmark 2 |
| **H · Visual structural truth (main line)** | new `visual/stitch_identity.py`, `visual/compose.py`, `visual/parity.py` structural floor, eligibility no-redraw policy | F-677, F-734, F-752, F-753, F-758, F-759, F-760, F-852, F-853, F-856 | PRODUCT TRUTH floor is an LLM motif/colour judgement that cannot tell star from waffle; research instrument not ported; no product-region preservation |
| **I · Learn (launch architecture only)** | new `learn/` package, models, knowledge graph | F-799, F-801, F-804, F-805, F-806, F-808, F-815, F-821, F-822, F-826, F-828 | nothing exists |
| **J · Final certification machinery** | `research/final_build/`, `src/brambleloop/build2/` validator, `scripts/shadow_rehearsal.py`, restart tests | F-125, F-178, F-831..F-840, F-843, F-845..F-850, F-867 | no closure validator for the Final matrix (consumer/fixture-only/proxy checks are manual); no end-to-end shadow rehearsal recorded |

Dependencies: **A → B** (taxonomy/properties chosen in A are transmitted by B) · **C, G → J**
(certificate changes before RC freeze) · **H → V2 lane** (structural instrument first, B+C
composition after the V2 coupon passes) · **B, D → owner transactions_r / etsy_exercise** for their
live halves · **all → J → RC freeze → owner launch packet**. E and F are independent of all others.
Shared hot file `runtime/pipeline.py`: B owns `handle_store_publish`, C owns `concept_to_cir` and
`handle_certify`; integrator resolves. `app/main.py` changes belong to E only (other clusters hand
route needs to E).

## 7. Owner / data / external gated (launch-critical)

64 owner · 14 data · 29 external. Principal keys: `transactions_r` (10), `production_window` (10),
`model_bearing_render` external (10), `rendered_pages` external (8), `live_listings` data (8),
`etsy_api`/`etsy_shop` (8, software half open), `image_vision` (5), `visual_v1_provider_capability`
external (5), `ad_authority` (4, MATURE work), `offsite_storage` (3), `production_deploy` (3),
`customers` data (3), `insights_access` (4), Etsy has no Messages/Customer-Service-Stats API (4),
`tester_roster`/`physical_proof` (4), `etsy_exercise` (3). In every case the software preparation
is listed in `next_action` and is not gated.

## 8. Visual V2 lane (isolated)

- R&D frozen at `codex/visual-v2-rnd` @ 035ff0c. B+C recommended; **V2-P06 continuous yarn
  topology FAIL; V2-P07 structural truth UNKNOWN (13.6 mm unaccounted feed)**; photographic realism
  UNKNOWN; spend $0. Cable crossing direction/attachment for Heirloom is an open owner clarification.
- Main-line work that does not wait on R&D: cluster H (port the deterministic stitch-identity
  instrument and structural floor; forbid product redraw by policy; product-region preservation
  verifier). This makes the existing photoreal path *honest* (it will refuse more), not better.
- R&D next step (unchanged, $0): persistent material-coordinate yarn with supply ledger → one-post
  DC coupon → neighbour/turn → full throw → six views/lights. Integration into `src/` only after a
  topology-correct coupon passes independent review. Graduation (F-857) on a blind Brambleloop
  original with both hard gates; on-model (F-858) after product lock.
- Option to shorten: graduate first on an **sc/hdc** original (certified topology already exists
  for sc/hdc; Milestone D structural locks passed) rather than the cable Heirloom. Recorded as a
  V2 lane proposal, not a change to R&D ownership.

## 9. Owner-action sequence (F-870 packets; requested at the latest responsible moment)

| when | action | why software can't | time / max cost | unlocks | cost of delay |
|---|---|---|---|---|---|
| now (near-term) | **Re-authorise the Etsy app with `transactions_r`** (browser consent) | OAuth consent is the account holder's | ~5 min · $0 | order/receipt truth (F-501, F-558, F-608, F-609; 10 LC rows) | orders unreadable after first sale; money truth stays UNMEASURED |
| now | **Record the browser/vision acceptance ruling** (#189/#221/#222/#320) | ruling on wording is the owner's | ~5 min · $0 | 4 Build 2 rows | rows stay owner-gated; no other work waits |
| now (near-term) | **Fund / confirm model+vision provider headroom**: current spend CA$76.40 of CA$100 ceiling | financial authority (F-871) | ~5 min · proposed ≤ CA$25 top-up, ceiling enforced in code | vision/judging work, Visual evidence | vision-dependent QA halts at the ceiling |
| after cluster B | **Authorise one controlled Etsy write round trip** (`/api/etsy/exercise`: create draft → read back → delete) | first external write | ~2 min · $0 expected (draft created and deleted, never activated; Etsy charges its listing fee on publishing) | F-594 readiness, publish path proof | publish path stays unproven against real Etsy |
| after RC freeze (J) | **Authorise production deploy + unattended window** of the Final candidate | production merge/deploy is reserved | ~10 min · infra within CA$20/mo | ~300 rows toward DEPLOYED/EXERCISED; F-849/F-850 live drill; off-device proof | nothing is deployed; production keeps fcb982d |
| with deploy | **Create offsite storage bucket + credential** | account creation | ~15 min · ≤ CA$1/mo | continuity archive offsite (F-697) | provider loss = data loss |
| before a Class C product | **Recruit one independent tester** | outreach to real people | variable · tester fee TBD | physical proof for high-risk products | Launch-0 unaffected (low-risk classes) |
| at launch step | **Etsy identity/banking/tax activation, live listing approval** | KYC/legal (F-874: not before needed) | ~30 min · $0 | live listings | — |
| post-launch | Ads authority + daily cap; Insights/Stats exports; bounded Visual spend packet (F-877) when V2 coupon passes | spend/data authority | — | MATURE growth rows | — |

The owner is not asked to crochet anything (F-071). No owner block stops unrelated clusters.

## 10. Completion plan (from evidence)

1. **Wave FB-1 (now, parallel, $0):** clusters A, C, D, E, F, G in isolated worktrees from the
   current head, disjoint ownership, each returning a tested patch series. B starts once A's
   taxonomy/property interface is fixed (same wave, B consumes it). H (instrument port) and I
   (Learn skeleton) run as second-priority lanes. V2 R&D continues isolated.
2. **Integrate** each cluster under single-integrator discipline; targeted suites first, full
   suite from clean state after each merge batch; re-aggregate the matrix.
3. **J:** build the closure validator (consumer reached + reads the producer's state; non-test
   writer for every evidence table; proxy flag refusal) and the s92 acceptance tests; run the
   end-to-end shadow rehearsal (opportunity → … → publish refusal/simulation → order/support/
   accounting) on a fresh DB with the production start command.
4. **Freeze RC SHA** (F-845) → independent re-audit of the matrix on that SHA (different model/
   session) → adversarial sampling (dead libraries, unreachable handlers, fixture-only evidence,
   proxy-as-truth, lost repairs) → repair → successor RC gets a fresh audit.
5. **Owner launch packet** (F-878): RC SHA, tests/audit, Visual status (V1 NOT LOCKED; V2 state),
   Launch-0 products/listings, policy state, owner actions, spend limits, economics, rollback,
   activation steps. Stop at the consequential gate.

Decisions recorded: DECISION_LOG D-FB-1..D-FB-5.
