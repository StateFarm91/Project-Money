"""Controller-grade accounting (Master v1.1 section 94, F-901..F-917).

The Accountant agent's books. Everything here is *derived* from the durable sources the rest
of the company already writes -- `ledger` (orders ingest, Etsy listing fees), `cost_entries`
(model, image, infra and other spend), `spend_reservations` (commitments), the held-order
record and imported statement lines -- by idempotent posting rules into an immutable
double-entry journal. Nothing in this package can move money, file a return, change bank
details, borrow or sign anything (F-917, `guardrails`).

Module map:

* `models`          -- the journal, postings, period locks, statement lines, exceptions and
                       spend challenges (tables registered by `schema.ensure`).
* `accounts`        -- the chart of accounts.
* `ledger`          -- balanced, sealed, append-only journal; reversals, never edits.
* `posting_rules`   -- source rows -> journal entries, idempotent, with corrections.
* `health`          -- source health: measured / stale / disconnected (F-902).
* `reconciliation`  -- statement import, match / unmatched / duplicate, books agreement.
* `views`           -- trial balance, accrual and cash views (F-905).
* `profitability`   -- order / product / release / family / channel / period (F-906).
* `attribution`     -- spend to product / release / department (F-907).
* `cash`            -- cash, obligations, payouts, reserves, safe budget, runway (F-908).
* `forecast`        -- ranges with assumptions, never a booked figure (F-913).
* `tax_pack`        -- GST/HST-ready evidence pack; preparation only (F-909).
* `close`           -- month-end checklist and period locks (F-910).
* `anomalies`       -- duplicate charges, fee rates, deposits, refunds, spikes, drift (F-911).
* `policy`          -- Finance's spend challenge for Growth (F-912, F-919).
* `handoff`         -- human accountant export (F-916).
* `dashboard`       -- owner Money provider: summary / drill / next_work (F-914, F-915).
* `controller`      -- the Accountant agent's cycle (F-901).
* `guardrails`      -- what this package must never be able to do (F-917).
* `exceptions`      -- accounting exceptions: opened idempotently, resolved with a note.
* `schema`          -- table registration and the Database/Session adapter.
* `job`             -- the `finance.accounting.cycle` worker handler (wiring requested).
* `shadow_dataset`  -- SYNTHETIC data on throwaway SQLite for tests and runtime proof.
"""
