# ops/

Scripts that keep the state files honest. All read committed files only.

| Script | Purpose |
|---|---|
| `day.py` | Prints the competition day number from the immutable start timestamp. |
| `ledger.py` | Summarizes `finance/FINANCIAL_LEDGER.csv` (actuals only). |
| `status.py` | Prints the operator status report the owner expects when asking "Status?". |
| `build_candidates.py` | Merges raw lens research into `research/candidates/candidates.json` and `CANDIDATES.md`. |
