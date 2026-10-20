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
