# v1.1 lane H handoff: Growth / Etsy Ads readiness / economics

Branch `claude/v11-H`, based on `claude/visual-investigation` @ 0694fb7. Nothing pushed, deployed,
published or spent. The phase is still shadow.

## Requirement status

| ID | Status | Evidence |
|---|---|---|
| Directive §12 (ads evidence- and economics-aware, no campaign without authority) | COMPLETE for proposal/readiness; GATED for execution | `growth/ads_readiness.py`. No executor exists, and tests check this. |
| F-912 Spend governor integration | PARTIAL | Every proposal reads the owner `SpendLimit('ads')` through `runtime.growth_ops.ad_authority`, the conservative paid-media caps and the governor anomaly hold (`spend-anomaly*` incidents). Lane E's cash/runway policy is consulted through `finance.accounting.policy.check_spend` once it exists. Until then the fallback ESCALATEs owner-cash proposals and says that cash was not checked. |
| F-918 Anti-gaming KPIs | COMPLETE (logic); UNEXERCISED (no real ad data) | `attributed_roas` / `kpis` use only Etsy Ads revenue that has attribution evidence. Organic, unattributed and Offsite orders are excluded and counted. Spend must be measured (`cost_entries.kind='ads'`), otherwise ROAS is UNKNOWN. Confidence stays `low` below 15 orders. The outcome KPI is contribution ROAS. A KPI never authorises spend. |
| F-919 Cross-agent challenge (§95: Growth spend violating Finance policy → blocked) | COMPLETE (fallback); integration with lane E is coded but only exercised against a stand-in | `propose()` → `finance_check()` → `AdFinanceChallenge` row. The most restrictive of Finance and the hard ceiling wins. Exceptions and unrecognised answers from Finance fail closed (BLOCK). |
| F-930 24/7 not reckless | COMPLETE | `next_work` returns only zero-spend internal work. Blocked items name their blocker. |
| F-263/F-272 readiness gate; F-242 organic first; F-685/686 eligibility | COMPLETE | Per-listing gates: listing_live, listing_certified, product_truth_clear, organic_signal, unit_economics, ads_eligibility (fresh operator evidence less than 24h old), trust_ladder. UNKNOWN never counts as PASS. |
| F-323/F-324 break-even; F-273/F-570 Offsite Ads | COMPLETE (modelled) | `unit_economics`: `measured` needs ≥20 orders with fees read from Etsy's ledger. Otherwise it is `modelled` from the listing price and the dated fee reading (refund rate UNMEASURED, so the break-even is a lower bound). A conservative worst-case figure is reported beside it. Offsite exposure comes from the dated advertising reading. It is labelled as exposure and `controllable: False`, with FX assumed. |
| F-267 owner authority; F-614/615 Plus credit | COMPLETE (gated) | A surviving proposal becomes an `OwnerAction` (`ads.proposal:<key>`, `max_cost_cad` = total). The credit cap is the official US$5 per cycle at the assumed FX. The fallback always ESCALATEs credit proposals because the balance is unverified. |

## Codex 8877f05 reuse

From `growth/ads_readiness.py` I reused `locked_row`, `snapshot`, `state`, `tick` and `record_evidence`, with small fixes: `None`-safe detail, and `stale` coerced to bool. Its `MarketplaceCapability` model was defined in `core/models.py`, which I may not edit. This module uses `core.models.MarketplaceCapability` if lane A lands it, and otherwise defines an identical table (`marketplace_capabilities`, same columns) locally, so the two never collide. I ported Codex's three ads tests (countdown, expiry, future evidence) into `test_v11_ads_readiness.py`. I did not take the worker/route/runner/lanes pieces. Those belong to lane A.

## Files

- Rewritten (new on this branch): `src/brambleloop/growth/ads_readiness.py`. Tables: `marketplace_capabilities` (conditional), `ads_spend_proposals`, `ads_finance_challenges`. `ensure_tables(db)` creates them with checkfirst.
- Tests: `tests/test_v11_ads_readiness.py` (11), `tests/test_v11_ads_challenge.py` (13), `tests/test_v11_ads_no_execution.py` (8).
- Evidence: `evidence/H_ads_runtime_proof.json`.

## Contracts

- `brambleloop.growth.ads_readiness.summary(db)` returns `status` (UNKNOWN with no listings; BLOCKED when no listing is ready; OK when at least one is), `as_of`, `basis` (unknown/modelled/measured), `items` (`listing_readiness` and `spend_proposal` rows) and `sources`. It also returns `eligibility`, `proposals{finance_blocked, awaiting_owner, not_ready}`, `kpis`, `spend_executed_cad: 0.0` and `execution_capability: "none"`. It never raises.
- `next_work(db, now=None)` returns a list of `{key, department:"growth", kind, action, why, spend_cad:0.0, blocked_by}`. The keys are `ads.eligibility_tick`, `ads.eligibility_evidence` (owner), `ads.organic_baseline:<slug>`, `ads.economics:<slug>` and `ads.rechallenge:<proposal_id>`. Lane A can map `ads.eligibility_tick` to `tick(db)` and `ads.rechallenge:<id>` to `rechallenge(db, id)`.
- Lane E integration: `check_spend(db, proposal)` gets a dict with `kind="ads_spend"`, `department="growth"`, `purpose`, `slug`, `funding`, `daily_budget_cad`, `days`, `amount_cad`/`total_cad`, `max_cac_cad`, `economics` (with basis), `hypothesis`, `stop_condition` and `key`. The expected return is `{"verdict": "ALLOW"|"ESCALATE"|"BLOCK", "reasons": [...]}`. `decision`, `allowed` and a bool are also accepted. Anything else is treated as BLOCK.

## WIRING REQUESTS

1. `core/db.py` `Database.create_all`: add `from ..growth import ads_readiness  # noqa: F401; v1.1 lane H ads tables` beside the Learn import. Without this, the tables are created lazily by `ensure_tables`.
2. If lane A adds Codex's `MarketplaceCapability` to `core/models.py`, it must keep the table name and columns identical. This module adopts it automatically.
3. Optional (lane A): an hourly cadence `marketing.ads_readiness` → `ads_readiness.tick(ctx.db)`, as in Codex 8877f05.

## Runtime proof

`evidence/H_ads_runtime_proof.json`, run on a throwaway SQLite database:

- Empty database: `summary` returns UNKNOWN/unknown and `items=[]`.
- Fixture listing at CA$12: modelled contribution CA$10.58 (conservative CA$8.34), break-even ROAS 1.134 (conservative 1.438), Offsite exposure CA$1.80 standard / CA$1.44 reduced.
- §95 case (max CAC CA$40, inside every ceiling): FINANCE_BLOCKED with the margin reason, and no owner item.
- Credit test inside policy: ESCALATE, then AWAITING_OWNER with one OwnerAction.
- The real trust ladder on the fixture shop reads FAIL, so `summary` reports BLOCKED. That is correct.

## Tests run

- `PYTHONPATH=src python3 tests/test_v11_ads_readiness.py`: 11 passing, 0 failing.
- `tests/test_v11_ads_challenge.py`: 13 passing, 0 failing.
- `tests/test_v11_ads_no_execution.py`: 8 passing, 0 failing.
- `test_paid_media_economics.py`: 9/9. `test_growth.py`: 13 OK.
- `test_cert_growth_ops.py`: 12 OK, 1 FAIL from `ModuleNotFoundError: numpy` in the system python3. This is an environment problem and not related to ads.
- `test_vacuity.py`: my files have no findings. It still fails on pre-existing findings in `test_launch0_listing_truth.py`, `test_pattern_truth.py` and `test_web_security.py`.
- `test_secret_scan.py`: fails on pre-existing `tests/test_rc1_ord2.py:169`. My files are clean.
- `/home/user/Project-Money/.venv/bin/python` has no sqlalchemy, so I used system `python3` (SQLAlchemy 2.1.0).

## Gaps / not verified

- Lane E's real `check_spend` was not available. The integration was only exercised against a stand-in module, and cash/runway policy is not checked in fallback mode.
- The trust-ladder PASS in the proposal tests is a supplied fixture (`trust_gate=` parameter). Against a real shop the ladder reads FAIL/UNKNOWN today.
- There is no real Etsy Ads data, eligibility evidence, ad spend or attributed order, so every KPI is UNEXERCISED in production.
- Owner approval is an `OwnerAction`. `done` cannot tell approved from dismissed, and `rechallenge` marks a withdrawn item `done`. An authenticated owner decision route is lane C's or A's work.
- No ad executor exists, by design. If one is ever built, it must re-run `rechallenge` before any spend.
