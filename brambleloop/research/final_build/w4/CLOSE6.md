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
