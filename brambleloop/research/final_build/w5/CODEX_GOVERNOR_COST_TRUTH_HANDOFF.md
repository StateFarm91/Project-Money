# Governor invalid cost truth: review only

Base: `codex/v0-provider-authority` at `649896e714600327c5ca76878447c325a3077ed6`.
On a disposable file-backed database, the real Command Center department
reader reported a negative `CostEntry.amount_cad` as a reconciled cost credit.
The existing V0 company budget already refuses negative or non-finite cost rows;
this continuation refuses those rows in the Governor's reporting/anomaly
window, and also validates historical rows before its lifetime total. The
Command Center reports UNKNOWN and the `/api/governor` response says the report
is unavailable, rather than returning a fabricated spend figure.

Tests on Python 3.11 with SQLite: `test_codex_governor_invalid_cost.py` 4/4;
`test_governor.py` and `test_w4_spenda_k5a.py` 33/33. Independent review
confirmed the narrow report behavior. No provider calls were made.

**Not a full finance fix or permission to activate providers.** Other finance
consumers may still sum invalid rows. There is no new unknown-cost recording or
reconciliation workflow and no assertion that the complete CA$100 ceiling is
safe. If invalid data reaches the scheduled Governor enforcement worker it
refuses instead of acting on a false total; recovery/reconciliation is needed.
Main must resolve the shared `app/main.py` overlap and decide whether historical
negative CostEntry amounts can be legitimate corrections before integration.
The V0 branch's existing DO NOT INTEGRATE hold remains in force.
