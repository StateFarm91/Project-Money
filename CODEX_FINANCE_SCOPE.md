# Finance operating-cost truth scope
Base a4c79ed; branch codex/final-finance-cost-basis-01. AB inherited; H unchanged.
Own new finance/listing_costs.py; finance/books.py cost basis/cash; finance/reconcile.py
listing-reference fee ingestion; pipeline.handle_store_activate fee accounting only;
new tests/report. No model migration, Visual, thresholds, production, spend or statuses.
Modelled listing-fee exposure persisted before external effect, reused across retry;
actual payment-ledger listing entries idempotent by external ID; event-dated budget
mirrors excluded from Books by exact ledger identity; unresolved model is retained; generic legacy missing basis UNKNOWN. Gateway price_basis assumed is modelled.
Tests inactive/retry/restart/reconciliation/no-doublecount/cash unknown. No heavy suites.

## Independent review correction (after 67aeda8)
Approved books.py/listing_costs.py/test scope: later renewal must not settle initial
reservation by listing ID alone, rewrite prior-period results, or escape today's budget.
Actual ledger has no activation-event binding: retain immutable unresolved model exposure,
append event-dated store_operator budget mirror, count measured ledger once in Books.
Unknown fee rows cannot become observed when signed amounts net to zero.
Downstream unit_cost/sustainability/spend_report scope approved but deferred for this repair.

## Downstream basis propagation (after b15b351)
Parent approved unit_cost.py, sustainability.py, spend_report.py and focused tests.
Reuse basis summary (row counts, signed sums, nullable actual) from listing_costs.py.
Preserve exposure amounts and threshold comparators; label recorded vs actual explicitly.
Legacy maintenance fixture lacks rate evidence: reading UNKNOWN with unchanged amounts.

## Tested-module cache freshness (after 5bb2c76)
Approved maturity.py _tested_modules helper/cache only, new focused tests/report.
Exact source bytes and absolute paths identify cached import set; addition/removal and
same-size/same-mtime replacement invalidate. No status/reachability/threshold changes.
Unreadable sources must raise/refuse, not return cached imports. Preserve SyntaxError skip.
Preserve cache_clear/cache_info compatibility. No resolver index optimization authorized.

## Resolver portability (after7ab2a6f)
Approved _module_of return-path normalization only plus focused tests. Path.as_posix preserves selection/ambiguity logic; no full report run or proofthreshold change. Direct absolute helper inputs retain original resolution behavior with slash spelling.

## Request import snapshots (after e8cf29a)
Approved private ContextVar immutable import snapshot; decorate maturity.report and closure.matrix only. Exact root/path/byte capture at entry and revalidation before return; mutation/unreadable abort, finally resets nested context. No status or other graph-cache semantics changes.
