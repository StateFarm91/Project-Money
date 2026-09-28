# Finance operating-cost truth scope
Base a4c79ed; branch codex/final-finance-cost-basis-01. AB inherited; H unchanged.
Own new finance/listing_costs.py; finance/books.py cost basis/cash; finance/reconcile.py
listing-reference fee ingestion; pipeline.handle_store_activate fee accounting only;
new tests/report. No model migration, Visual, thresholds, production, spend or statuses.
Modelled listing-fee exposure persisted before external effect, reused across retry;
actual payment-ledger listing entries idempotent by external ID, suppress duplicate model
in Books; generic legacy missing basis UNKNOWN. Gateway price_basis assumed is modelled.
Tests inactive/retry/restart/reconciliation/no-doublecount/cash unknown. No heavy suites.
