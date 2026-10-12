# W4-CCGROW: growth/* and brand/* Final Master rows (F-504, F-126; the rest triaged)

Branch `claude/w4-CCGROW`, cut from `origin/claude/w4-INTEG2` @ 85ec5d0. The change makes no schema migration: the new fields live in the existing `RegisteredExperiment.detail` JSON column.

## Rows advanced

| Row | Ledger next action | Change | Evidence |
|---|---|---|---|
| **F-504** Experiment Attribution | "Add measured_effect and retain_or_rollback fields to RegisteredExperiment and set them in growth.experiments.conclude_all" | `experiments.attribution(row, verdict, causal)` produces two outputs.<br>• `measured_effect`: observed vs the pre-registered success line, plus `effect_vs_expected`, signed so that ≥ 0 means at least as good. It is UNMEASURED with no reading.<br>• `retain_or_rollback`: **retain** only on a claimable success with a causal design and its control present. **rollback** on a claimable failure. **undecided** otherwise, with the reason (for example "association, not a cause").<br>`conclude_all` writes both into `detail` and returns them. `/api/experiments` shows both, plus the superseded marker. | `test_w4_ccgrow::test_attribution_retains_only_a_causal_success`, `::test_api_experiments_reports_effect_decision_and_superseded` |
| **F-126** Superseded Evidence Retention (experiment part) | "Add a Superseded marker (status + reason + superseded_by) … and a test that superseded rows are retained and excluded from aggregates" | `experiments.supersede(db, key, reason=, superseded_by=)` sets the state to `superseded` and stores `detail.superseded = {reason, superseded_by, previous_state, at}`. The row, its thresholds and its readings are retained. The row is excluded from `balance` and from `conclude_all`. Superseding is refused without a reason, or when the successor is unregistered or is the row itself. | `::test_supersede_retains_the_row_and_leaves_every_aggregate`, `::test_supersede_refuses_without_a_reason_or_a_registered_successor` |

**F-126 is not fully closed.** It also names `BenchmarkObservation` and the visual benchmark result rows. Their aggregators live in `improve/` and `visual/`, which belong to the learning and image domains and are not in this worker's queue. The same marker convention (`detail.superseded`) applies there.

## Other growth/* and brand/* rows (board order), not taken

| Row | Why not taken |
|---|---|
| F-032, F-033, F-260, F-369, F-384, F-503 | Need live listings, traffic or orders (data or external gates) |
| F-271, F-548, F-684, F-767, F-771, F-773, F-811, F-812, F-819 | Owner-gated (authority, content or channel decisions) |
| F-040, F-515, F-526, F-584 | Owner gate etsy_shop: a usable shop credential and getShop |
| F-527 Brand Asset Health | Needs the F-515 live shop snapshot (getShop icon/banner URLs), so it is blocked on the same Etsy credential |
| F-365 Store Architecture | Store/product catalogue logic, which belongs to another worker |
| F-814 Content Constellation | Needs Learn members (F-799/F-815), which do not exist yet |
| F-692 Constraint Routing | DATA-GATED on customers |

## Tests

These run through `testslot.sh`:

- `tests/test_w4_ccgrow.py` (new)
- `tests/test_experiment_persistence.py`
- `tests/test_cert_growth_ops.py`
- `tests/test_growth.py`
