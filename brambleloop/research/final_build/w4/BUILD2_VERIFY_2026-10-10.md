# Build 2 verification against the release candidate (W4-B2VERIFY, 2026-10-10)

Head verified: `56d7b38` (origin/claude/w4-SHADOWFIX). Production read-only: `fcb982d` (GET /api/status).
Claim under test: "Build 2 = 320/320 reconciled, OPEN-DEFECT 0; owner-gated 54 genuine; #242-245
DATA-GATED; #10/#54/#165 split."

## 1. Regeneration with the repo's own tooling

`PYTHONPATH=src python research/final_build/w4/build2_ledger.py <prod gates>` (= `build2.closure.ledger`).

| class | committed BUILD2_LEDGER.json (2026-10-07) | regenerated on 56d7b38 |
|---|---|---|
| PROVEN | 215 | **215** |
| OWNER-GATED | 58 | **54** |
| DATA-GATED | 37 | **41** |
| EXTERNAL-GATED | 7 | **7** |
| NOT-APPLICABLE (process directives #32 #56 #197) | 3 | **3** |
| OPEN-DEFECT (closure-computed) | 0 | **0** |
| total | 320 | 320 |

- The committed ledger was stale: it predates the GATESB re-park of #242-245 (ad_authority -> customers).
  Regenerated, the counts match the claim. No row changed state otherwise; the other diffs are
  evidence/gate-text refreshes.
- `closure.matrix()` (tests/test_closure.py, no DB): COMPLETE+PROVEN 218 (215 + 3 directives), OWNER 54,
  DATA 41, EXTERNAL 7, OPEN 0, `closed_out: false` -- because closed_out requires a live gate check
  (`gate_open is not None`), which only the production reading supplies.
- Gate reading: fresh read-only GET of production /api/build on 2026-10-10 (saved as
  `evidence_B2/prod_gates_2026-10-10.json`). Every gate a parked row waits on reads CLOSED; none opened,
  so no parked row reopens. **17 parked rows sit on gates production does not report** (production is
  fcb982d, older than these gates): insights_access 5, acceptance_ruling 4, transactions_r 2,
  production_window 1, model_bearing_render 5. Their closed state is UNKNOWN from a live reading
  (inferred closed only from the gate definitions); they are `unchecked` in the ledger, not 0 and not verified.
- Final Master snapshot (`research/final_build/aggregate.py` -> `build2/final_master_closure.json`)
  regenerates byte-identical: 917 rows, launch-critical COMPLETE 351 / GATED 124 / **OPEN 15**. That is a
  separate ledger from Build 2's 320; its 15 open launch-critical rows are not Build 2 rows.

**Executable remaining.** Closure-computed: 0. After the adversarial re-check below: **1 row with
executable company work (#10)** plus **1 gate-wiring defect (#35/#39)**. Neither is reflected in the
closure count, because the closure parks a partial row on its `parked_on` and does not inspect whether the
company half of a split is done.

## 2. Adversarial re-check of the 54 OWNER-GATED and 7 EXTERNAL-GATED rows

Method: every row's registry note, proof, closure evidence (named module exists / tested / reached from
a runtime root), the gate's opening condition, OWNER_ACTIONS placement, and D-FB-19 authority.

### Misclassified -- executable company work (listed, not done)

1. **#10 Free-to-Paid Acquisition Engine** (OWNER-GATED, owned_surfaces). The 2026-10-07 GATESB split names
   a company half -- draft one free lead-magnet asset through the product chain and run
   `growth.free_to_paid.check_asset` on it -- and that half is **not done**: no free asset exists,
   `/api/free-to-paid` calls `free_to_paid.plan([])`, and `growth/free_to_paid.py` has no runtime caller
   beyond that route (tests/test_closure.py uses it as the canonical "statically reached only" fixture).
   Needs no surface. Not done here: it is product work (a free motif/mini-pattern CIR that is not a
   catalogue object, through compile/twin/certify, then a stored FreeAsset the runtime plan reads), not a
   bounded edit. Owning lane per OWNER_ACTIONS.mislabelled_company_work: B2 / growth. Note appended to
   the registry row. The owner half (an owned surface) stays genuine.
2. **#35 Etsy Creativity / AI Disclosure Gate, #39 Policy Freshness Watch** (EXTERNAL-GATED,
   rendered_pages) -- gate wiring defect. The closure's own text says these rows need "a human policy
   snapshot, not a browser worker: a person reads the page and records it (POST /api/policy/snapshot,
   ~15 minutes every 30 days)". But `executor._rendered_pages_usable` opens only on a recorded
   `browser.probe`, so a recorded human snapshot never releases them, and OWNER_ACTIONS asks the owner for
   the opposite remedy (`infra.browser_worker`, cost UNKNOWN). Company work: decide the remedy (the
   closure text and D-FB-19 point to the human snapshot), re-wire the gate for #35/#39 to open on a current
   reviewed PolicySnapshot set, and re-cost or withdraw `browser_worker`. Not done here: it changes a gate
   that releases work and what the owner is asked; it belongs with the GATESI/integrator lane.

### Stale or weak evidence -- fixed in this lane (bounded, docs/mapping only)

3. **Evidence mapping: 15 gated rows cited no test or no machinery** although both exist. Added `proof`
   citations (registry `requirements.json`; status and parking untouched). Each cited module was checked
   by the closure for exists / tested / reached; all 15 are reached, so no state changed:
   #1 intel/insights.py + test_insights_intake; #165 intel/benchmark_refresh.py; #189 #221 intel/browser.py +
   test_capability_gates; #222 #320 intel/acceptance.py + test_acceptance; #294 #295 runtime/growth_ops.py
   (ads.adjust); #315 teardown/audits.py + test_teardown_audits; #317 intel/purchase_selection.py,
   teardown/lab.py + test_purchase_selection; #39 gates/platform_policy.py + test_platform_policy;
   #300 seasonal/cycle.py + test_seasonal_cycle; #72 #130 visual/identity.py, publish/model_photography.py;
   #202 visual/brief.py. (The 7 gaps OWNER_ACTIONS.b2_genuine_gate_evidence_gaps listed -- #254 #263 #37
   #14 #16 #9 #51 -- are already mapped on this head.)
4. **#300** note said the assets link "reads FAILED not GATED -- left for the lead". Already fixed in code
   (`seasonal/cycle.EXTERNAL_BLOCKS` maps `model_bearing_render_path` -> BLOCKED; tests/test_seasonal_cycle.py).
   Note updated; classification unchanged.

### Confirmed genuine (no company work executable now)

- **#54, #165 splits**: company halves proven (launch/readiness.py reached + test_launch / test_cert_rebuild_chain;
  intel/benchmark_refresh.py reached on the weekly cadence). Only the Insights reading / the purchase remain.
- **#242-245**: DATA-GATED on customers; ads.adjust computes them; machinery reached. Correct.
- Remaining owner rows: live_listings 9 (publication is owner-authorised), image_vision 14 (provider credit:
  spend), benchmark_purchases 5 (purchase), owned_surfaces 7 minus #10's company half (accepting a platform's
  terms), insights_access 5 (Shop Manager has no API), acceptance_ruling 4 (a ruling), tester_roster 3 and
  physical_proof 1 (a real person; D-FB-19 item 9 requires the owner to confirm the exact outreach message),
  transactions_r 2 (browser consent), ad_authority 2 (spend), offsite_storage 1 (account + credential),
  production_window 1 (deployment). For each, the built half is reached from a runtime root and tested.
- **model_bearing_render 5** (#72 #130 #202 #203 #300): EXTERNAL holds -- 0/16 and 0/7 provider draws
  certified; frozen with no further paid draws (D-B2C-1).

### Owner cards that still carry company work (costing)

`storage_offsite` and `browser_worker` are presented with max cost UNKNOWN. D-FB-19 item 1 says the
company brings the exact provider and cost. Costing them is company work, not an owner action
(`ad_budget` and `OA-G2` are UNKNOWN by design: not askable yet / a fee on attributed sales).

## 3. Proven in code+tests vs awaiting real-world evidence

**Proven in code+tests (on this branch, not deployed):** 215 PROVEN + 3 directives followed. "PROVEN" here is
module exists + tested + statically reached from a runtime root. Production still runs fcb982d, so none of the
post-fcb982d work is exercised in production. The built half of the 102 gated rows is also reached and tested, except #10 (finding 1).

**Awaiting real-world evidence** (code built; the evidence cannot be produced by code):

| what is missing | rows | gate |
|---|---|---|
| real customers / orders / traffic | 41 | customers (33) + registry data_gated (8) |
| a published Etsy listing and its impressions | 9 | live_listings |
| a working vision model (provider credit) | 14 | image_vision |
| purchased benchmark patterns | 5 | benchmark_purchases |
| an owned site / Pinterest / email surface | 7 (#10 also has company work) | owned_surfaces |
| an owner-recorded Marketplace Insights reading | 5 | insights_access |
| owner ruling on the browser/vision wording | 4 | acceptance_ruling |
| a real tester / a finished physical sample | 3 + 1 | tester_roster, physical_proof |
| Etsy transactions_r consent | 2 | transactions_r |
| an approved ad budget | 2 | ad_authority |
| an offsite bucket + credential | 1 | offsite_storage |
| an unattended production window of this build | 1 | production_window |
| a human Etsy policy reading (see finding 2) | 2 | rendered_pages |
| a stitch-faithful model-bearing render | 5 | model_bearing_render |

**Production observation, 2026-10-10 (read-only):** `etsy_api`, `etsy_shop` and `benchmark_observation`
read CLOSED (they read open on 2026-10-07), and /api/verify is 11/12 (failing
`no_unexpected_dead_letters_in_24h`: mjs.scan). #206 #301 #319 (the benchmark_observation rows) are PROVEN
in code, but the live capability is not serving on fcb982d today. Diagnosing the failing etsy.probe is
company work; whether it ends in an owner re-authorisation is not yet known.

## 4. Consolidated genuine owner actions (reused from OWNER_ACTIONS.json; no new batches)

Build 2 rows map to 11 owner items across 8 batches. Totals for those items: max CA$535 (+ UNKNOWN for
`storage_offsite`), 220 minutes. The full OWNER_ACTIONS.json is 10 batches / 26 decisions / 316 minutes /
CA$1,010.01 plus 4 uncosted items.

| # | batch.item | exact action | why (Build 2 rows) | max cost | min |
|---|---|---|---|---|---|
| 1 | model_funding.fund_model | Add credit to the Anthropic account (console.anthropic.com -> Plans & Billing) | opens model_provider + image_vision: #15 #44 #61 #67 #86 #88 #116 #126 #218 #277 #281 #304 #308 #309 | CA$25 | 5 |
| 2 | rulings.acceptance_ruling | Rule yes/no: does an API + vision traversal satisfy the "browser/vision" wording? | #189 #221 #222 #320 | CA$0 | 2 |
| 3 | rulings.production_window | Authorise deploying the reviewed build for one unattended window (phase stays shadow) | #195 | CA$0 | 10 |
| 4 | etsy_account.transactions_scope | Re-authorise the Etsy app with transactions_r (consent screen) | #11 #12 | CA$0 | 3 |
| 5 | etsy_account.insights_reading | Record one Marketplace Insights reading from Shop Manager (POST /api/insights/snapshot) | #1 #37 #54 #236 #237 | CA$0 | 10 |
| 6 | benchmark.benchmark_purchase | Buy the 13 listed MJs benchmark patterns (GATE_CLEARANCE_BUSINESS.md) and upload at /ops/teardown | #163 #165 #168 #315 #317 | CA$300 | 75 |
| 7 | channels.owned_surfaces | Open domain + static site, Pinterest business account, free-tier email | #4 #10 #246 #247 #248 #251 #255 | CA$25 | 65 |
| 8 | go_live.tester_outreach | Confirm the prepared tester call and approve one paid sample make (market-basket-small) | #9 #43 #250 #64 | CA$185 | 25 |
| 9 | go_live.leave_shadow | Authorise shadow -> staging -> limited production, step by step | #14 #16 #46 #238 #239 #241 #254 #263 #266 | CA$0 | 5 |
| 10 | storage.storage_offsite | Create an offsite object-storage bucket + credential | #51 | UNKNOWN (company to cost) | 15 |
| 11 | paid_media.ad_budget | Not askable yet: set SpendLimit 'ads' (rec. CA$3/day, CA$60/month) once organic sales exist | #294 #295 | not yet asked | 5 |

Each item's consequence of waiting is in OWNER_ACTIONS.json (`consequence_of_no`). In short: the rows
listed stay parked, and nothing is published, spent or contacted.

Not an owner action: `infra.browser_worker` for #35/#39, until finding 2 is resolved. If the human-snapshot
remedy is adopted, the replacement is a recurring ~15-minute policy reading (CA$0), recorded through the
existing intake.

## Verification run (focused, one process at a time)

tests/test_w4_b2_build2_ledger.py ALL OK; tests/test_closure.py 27/0; tests/test_build2.py,
tests/test_secret_scan.py, tests/test_final_closure_matrix.py exit 0.
