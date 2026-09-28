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
