# DRIFTMARGIN: F-218 canonical model drift sentinel (graded margins, near-threshold trend)

Branch `claude/w4-DRIFTMARGIN`, based on `origin/claude/w4-INTEG2` 9fd62cc. Stub judge only;
no spend. Laura's identity gates are unchanged.

## What changed

- `model_registry.compare_identity`
  - The judge now also grades every match or drift answer `clear` or `borderline`, returned
    as `margins`.
  - The ternary verdicts are unchanged.
  - An off-vocabulary or missing grade is `unknown`, never `clear`.
- `model_photography.make` records `identity.margins`. Each dimension's grade comes from the
  comparison that could see it: face against the portrait, body against the body frame.
- `drift_series.series` trends the share of passes graded `borderline` per dimension. It uses
  the same rule it already applies to drift: rising across `TREND_BATCHES`, or late minus
  early ≥ `RISE`. A trend is reported as `near_threshold_trend` before any pass becomes drift.
  Ungraded passes give no reading.

## Acceptance evidence (testslot)

| Test file | Result |
|---|---|
| `tests/test_w4_driftmargin.py` (new) | 5/5 |
| test_cert_intel_wave2 | 0 fail |
| test_fb2_i_repairs | 0 fail |
| test_portrait_repair | 0 fail |
| test_model_photography | 0 fail |
| test_model_spend_paths | 0 fail |
| test_vacuity | 0 fail |

## Board row

- F-218: the software is done. Production evidence needs model-bearing frames, which are
  externally gated, plus deploy.
