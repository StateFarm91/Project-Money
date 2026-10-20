# W4-CLOSE6

**Branch and scope.**
- Branch `claude/w4-CLOSE6`, started from ee244a1 (W4-CLOSE5 final, accepted for the release).
- Same rules as CLOSE5: no deploy, no production writes (read-only GETs only), no spend, and no
  edits to the W-VISNEXT or W-FIRSTSALE files.
- Closures go through `research/final_build/w4/close5.py`. Its CLOSE6 blocks are tagged
  `w4-CLOSE6` and use the evidence in `evidence_CLOSE6/`.

## 1. Batch 1: F-685, F-686 and F-688 (Etsy Ads eligibility, recheck and credit)

| row | criterion (quoted) | tests | status |
|---|---|---|---|
| **F-685** Etsy Ads Eligibility | "persist etsy_ads_status, eligible_from/next_check, evidence_source and last_verified_at ... do not hard-code a derived date as authoritative." | `test_w4_close6_ads.py` (1) + `test_v11_ads_readiness.py` (2) | closed on b931d17 (see below) |
| **F-686** Ads Recheck | "automatically re-verify Etsy eligibility at/near the expected unlock; countdown reaching zero alone cannot change state to ELIGIBLE." | `test_w4_close6_ads.py` (2) | dev-proven, awaiting deploy (see below) |
| **F-688** Ads Credit Accounting | "Etsy Plus included Ads credit is separate from owner cash; record official entitlement, locally displayed CAD value, cycle, used/expired credit and incremental cash spend." | `test_w4_close6_ads.py` (2) | built; dev-proven, awaiting deploy (see below) |

**F-685: closed on b931d17.**
- The mapping's "MISSING" was stale. `growth/ads_readiness.py` persists all four fields.
- The reported countdown is stored as WAITING_REPORTED and marked as an estimate. It never
  gates as eligible.
- Production evidence (`evidence_CLOSE6/prod_api_owner_actions_ads_20261020T1119Z.json`): the
  hourly recheck raised OwnerAction #32 when the countdown came due, and did not set ELIGIBLE.

**F-686: dev-proven, awaiting deploy.**
- The recheck half was already deployed.
- The re-verification could never finish, because `record_evidence` had no caller. Production
  OwnerAction #32 has been open since 2026-10-11 and could not be satisfied.
- New route: authenticated `POST /api/ads/eligibility`.
  - It refuses a stale reading, a future one, and a WAITING reading with no recheck date.
  - A recorded reading closes the recheck action. The next countdown that comes due asks again.
  - ELIGIBLE can only come from a reading, and it authorises no spend.

**F-688: built; dev-proven, awaiting deploy.**
- New in `finance/credits.py`: the `AdsCreditCycle` table, `record_ads_credit_cycle`, and
  `ads_credit`, which is reported through `wallet` into `spend_report.governance`.
- New route: authenticated `POST /api/finance/ads-credit`.
- Each cycle records:
  - the official entitlement in USD;
  - the CAD value Shop Manager displays, with this system's conversion beside it, labelled as such;
  - the cycle dates;
  - credit used, as Etsy reports it (UNKNOWN when not reported, never 0);
  - expired credit;
  - recorded ad spend, and the incremental cash spent beyond the credit.
- No ceiling changes, and the ads SpendLimit is untouched.

**Deployed-tree run** (`evidence_CLOSE6/deployed_tree_tests_b931d17.json`): the F-685 test and
the F-686 countdown test pass on b931d17. The three tests that need the new code fail there, as
expected.

## 2. Proposed override for F-145 to F-148 (test-scratch hygiene), awaiting integrator acceptance (F-867)

`w4/OVERRIDES_PROPOSED_CLOSE6.json` proposes `completion_target: TESTED` for these four rows.
Every entry has `accepted_by: null`.

**Why an override is needed.**
- The producers are operator tooling: `run_tests.sh` and `tests/_tmp.py`. No runtime root can
  import them, so INTEGRATED is unreachable and TESTED is their ceiling.
- That is the same basis as the accepted overrides for F-123, F-170 and F-178.

**Status of the work itself.**
- W3-HYG built all four.
- The mapping's "MISSING" for F-148 ("direct runs get no scoped TMPDIR") has been stale since
  2026-10-06.
- The new `tests/test_w4_close6_hygiene.py` pins what W3-HYG left unpinned:
  - the harness success path;
  - the harness INT path;
  - F-146's single-EXIT-trap rule, including a planted-second-trap self-check.

**Dry run:** `aggregate.py --overrides w4/OVERRIDES_PROPOSED_CLOSE6.json --dry-run` reports
`problems: []`. All four rows adjudicate to maturity TESTED with no remaining reasons.

## 3. Batch 2: F-664 Ask Brambleloop and F-666 Overnight Brief (dev-proven, awaiting deploy)

| row | criterion (quoted) | tests | status |
|---|---|---|---|
| **F-664** Ask Brambleloop | "universal company command/search bar answering what changed, why profit moved, what blocks launch, what agents are doing, opportunities, spend and evidence." | `test_w4_close6_ask.py` (4) + `test_v11_cc_views.py` ask | dev-proven; 3 intents added (see below) |
| **F-666** Overnight Brief | "'While you were away' shows autonomous hours, tasks/experiments, products advanced/rejected, image candidates, Etsy findings, compute/ad spend, sales/profit, incidents and decisions." | `test_w4_close6_brief.py` (3) | dev-proven; 6 sections added (see below) |

**F-664: three intents added, dev-proven.**
- The mapping's "MISSING" was stale. v1.1 had already built Ask Company: `command_center/ask.py`,
  POST `/api/cc/ask`, and the Ask view.
- It now also answers what the agents are doing, spend, and opportunities. Every fact cites its
  row, and an empty store answers "nothing recorded" or UNKNOWN.

**F-666: six sections added, dev-proven.**
- The F-896 Overnight handoff already carried what changed, completed tasks, money spent by kind,
  incidents, discoveries, the queue and decisions.
- `command_center/brief.py` adds autonomous hours, experiments, products advanced or rejected,
  image candidates, Etsy findings, and sales and profit. The handoff card renders all of them.
- Sales that are not measured stay UNMEASURED, and an unreadable source is UNKNOWN.

**Looked at, not closed:**
- **F-662**, Live Company Timeline. `/api/cc/timeline` already merges the autonomy company
  timeline, incidents, decisions, spend and significant jobs. There is still no cause-to-effect
  linking, so I am leaving the row open rather than claiming it.
- **Build 2 #11 and #12**, the customer program and cohorts. The code is live in
  `commerce.orders_ingest`. With `transactions_r` open, the rows have nothing left to exercise
  until customers exist, which matches the production gate `customers=false`. That is a gate
  remap for the integrator.

## 4. F-144 Production Readback Gate (dev-proven, awaiting deploy)

**Criterion:** "Major operational features require deployed readback/verification after local tests."

**Already built (W4-SMOKE):**
- `ops/readback.py`: a per-feature manifest of endpoint, field, predicate and rows.
- `ops/deploy.sh`: exits 5 when a feature does not read back.
- `ops/smoke.py`, served at GET /api/verify/smoke.

**What W4-CLOSE6 adds:**
1. **Six features the manifest missed.** On b931d17, GET /api/departments answered 500 while
   every listed feature read PASS. Now also read back: department health, swarm runtime, the
   funding packet, the off-site archive, the continuity proof and the Etsy credential.
2. **The readback is evidence.** `deploy.sh` writes every readback to
   `evidence_BOARD/prod_readback_<sha12>_<ts>.json`.
3. **The board refuses "done" on a failed readback.** `completion_board_final.apply_readback`
   keeps a Final Master row out of verified_complete unless the readback of the deployed commit
   passed for every feature that names that row. No readback on file counts as UNKNOWN, and the
   row stays out. The rule only ever downgrades.

**Production reading (read-only):** the readback of b931d17
(`evidence_BOARD/prod_readback_b931d17a738d_20261020T1215Z.json`) is FAIL on two features. Both
are fixed on the branch:
- "no unexpected dead letters": the gallery timeouts, fixed by ee244a1.
- "department health served": the /api/departments 500, fixed by CLOSE5.

Applying the rule to the current board downgrades no row that was verified.

**Tests:** `test_w4_close6_readback.py` (4) and `test_w4_smoke.py` (10, with its fixture
extended to the new endpoints).

## 5. F-834 Consumption Required: consumer receipts (built; closes only if the integrator accepts the TESTED override)

**Criterion:** "Producing a reading is insufficient when the requirement exists to influence a
downstream decision/action; prove the consumer."

**Before.** `final_proof` already refused a row without receipts for durable_state, consumer,
decision, effect and result. But the only recorded run, the shadow rehearsal, recorded job
outcomes only, so every packet stopped at the producer.

**Built.**
- `scripts/shadow_rehearsal.py::record_edges` records, from the rows the run wrote:
  - the durable row each producer job wrote, and which job wrote it;
  - that the `store.publish` job read that state: its gates name the same version, and its
    idempotency key names the same certified release;
  - what it decided (refused in SHADOW), the effect row (`store.publish_refused`), and the
    result (no `store.published` row, no Etsy id).
- `scripts/emit_runtime_packets.py::consumer_chain` turns that edge into chain receipts. It
  does so only for rows whose producer AND named consumer are the handlers on that edge.

**Evidence: a production-mode run on clean head 8e4efd3.**
- `evidence_CLOSE6/shadow_rehearsal_8e4efd3.json`, `runtime_packets_8e4efd3.json`, and
  `final_proof_8e4efd3.json` (all 917 rows BLOCKED; nothing certifies itself).
- F-048 and F-477 now carry all six chain stages, and final_proof reports no chain error for
  them.
- They stay BLOCKED on the independent review, the production-producer receipt, the
  failure-test receipt, and the execution-gate and suite receipts.

**Why it needs an override.** The producer is a script plus the offline adjudicator, so the
row's ceiling is TESTED. The entry is added to `w4/OVERRIDES_PROPOSED_CLOSE6.json` (F-867;
dry run: no problems, F-834 adjudicates COMPLETE at TESTED). Until the integrator accepts it,
the row stays open.

**Tests:** `test_w4_close6_proof.py` (3).

**Side finding.** In one production-mode rehearsal (a9e5395), listing.seo read FAILED: the
newest listing.seo job was a later re-run still pending when the chain was read. The 8e4efd3
run read PASS. The recorder now binds each edge to the job that wrote the row, not to the
newest job of that type.

## 6. F-662 Live Company Timeline: causal stories (dev-proven)

**Criterion:** "human-readable causal activity stream across departments instead of raw
tool-call noise."

**Built.**
- `runtime/lineage.py`: `JobContext.enqueue` records which job caused each follow-on job in
  `job_links`. It is best effort and never blocks an enqueue. A child enqueued inside the
  caller's own transaction is not linked.
- `command_center/causal.py::stories` tells each chain as one story across departments:
  - who did what, in words, and the outcome;
  - the cause of the first step: "scheduled", "caused by", or "cause not recorded", never
    guessed;
  - routine checks that caused nothing are counted, not listed.
- The stories are served on `/api/cc/timeline` and shown in the Timeline view.

**Tests:** `test_w4_close6_timeline.py` (3). A pipeline run is one story; an unrecorded cause
is shown as such.

## 7. Build 2 #11 and #12: re-gate to `customers` (PROPOSED, not applied)

- The proposal is in `w4/B2_REGATE_PROPOSED_CLOSE6.json`, with `accepted_by: null`.
- Production evidence (`evidence_CLOSE6/prod_orders_ingest_20261020T1229Z.json`):
  - `transactions_r` is OPEN;
  - `commerce.orders_ingest` and `commerce.order_readings` complete on cadence;
  - there are zero `orders.ingested` rows, because there are no receipts;
  - `customers` is closed.
- What is left of both rows needs real buyers. That is a data gate, as with the #242 re-park
  (W4-GATESB).

## 8. Coordinator decisions recorded (D-W4-CLOSE6-OVERRIDES)

The coordinator accepted two proposals on 2026-10-20. `accepted_by` is set in both files, and
DECISION_LOG has the entry. Both are applied at INTEG5, not on this branch.
- `OVERRIDES_PROPOSED_CLOSE6.json`: F-145, F-146, F-147, F-148 and F-834 at TESTED.
- `B2_REGATE_PROPOSED_CLOSE6.json`: Build 2 #11 and #12 re-parked on `customers`.

## 9. Batch 5: F-872 closed on production; F-273 and F-538 corrected and re-gated

**F-872** Etsy Scope Reauthorization: closed on b931d17.
- Criterion: "Required OAuth scopes such as transactions_r are explicitly reauthorized and
  proven by readback before trusted use."
- Production `commerce.orders_ingested`
  (`evidence_CLOSE6/prod_api_orders_ingested_20261020T1321Z.json`):
  - until 2026-10-13, every run read UNMEASURED with zero network calls, because the gate was
    closed;
  - since 2026-10-13T03:28Z, every run reads `measured` after an authenticated getShopReceipts
    read (2 calls, 0 receipts).
- `test_w4_close6_scope.py` (3) pins the rule:
  - no receipt is read unless the scope is granted AND a working credential has been
    demonstrated;
  - a read refused for scope is never trusted;
  - the read that worked closes the re-authorisation request.
- The code tests pass on the deployed tree. The production-evidence test reads this branch's
  evidence file, so it is run on the branch.

**F-273** Offsite Ads Accounting and **F-538** Finance Reconciliation.
- The mapping was stale. `finance/reconcile.py` already does this work on every receipt read:
  - reads Etsy's payment-account ledger;
  - replaces modelled fees with charged ones;
  - sets `offsite_ad_attributed` from `offsite_ads_fee` entries;
  - reports unknown ledger types and never counts them.
- What is left is a real settlement: an attributed sale, the owner-recorded mapping
  verification, and classifying any tax, credit or subscription types that appear.
- Both rows moved from the now-open `transactions_r` owner gate to the `customers` data gate,
  as F-683 and F-323 already are. Neither is claimed complete.

## 10. Batch 6: F-040 Shop Quality Gate (proven on the branch only, awaiting deploy)

**Criterion:** "Icon, About/brand presentation and core trust elements must be complete before
launch."

**What was already true.** The mapping said readiness checked only draft text; that was stale.
- W4-ETSYSURF made `etsy_first_sale_surfaces` read the daily live `etsy.shop_snapshot`.
- In production it holds launch on the banner, shipping and additional policies, and a missing
  digital listing (`evidence_CLOSE6/prod_api_launch_shop_20261020T1329Z.json`).

**The gap.** Nothing could see the About story: getShop has no About field.

**The fix.**
- `commerce/shop_observations.py` accepts an `about` page: the owner's dated reading, through
  the existing POST /api/etsy/shop-observation.
- `launch/readiness.py` holds launch when the About reading is unobserved, stale, incomplete,
  or says the About is not published.

**Tests:** `test_w4_close6_shop.py` (4).

## 11. Finding for the integrator: first-sale readiness can never pass as built

Production `etsy_first_sale_surfaces` lists five required surfaces with `collector=None`:
messages, orders, legal_and_tax, digital_files, taxonomy_and_attributes. A surface with no
collector is NO_COLLECTOR forever, and the item is ready only when every surface is FRESH. So
launch readiness cannot become ready even after every owner action is done.

The `orders` surface also still names `reauthorise_transactions_r` as its owner action,
although transactions_r is open and receipts are read on every cadence.

The fix touches the first-sale readiness view and the digital-file and taxonomy collectors,
which are W-FIRSTSALE's scope. I left it alone. It needs either:
- a collector per surface (for example, `orders` from the `commerce.orders_ingested`
  readings); or
- an owner-observation evidence path, as `about` now has.
