# UPGRADECMP: F-738 identity-preserving promotion comparator (the F-737 cell's gate)

Branch `claude/w4-UPGRADECMP`, based on `origin/claude/w4-INTEG2` 9fd62cc. No model call.

## What changed

- `visual/upgrade_compare.compare(incumbent, challenger)` reads only recorded identity
  verdicts and `photoreal.gate` readings. It **refuses** a challenger when any of these holds:
  - it is not Laura (`canonical.laura_verdict`);
  - its identity retention (matched share of the drift dimensions) is below the
    incumbent's;
  - its realism is not strictly better;
  - it fails a realism check the incumbent passed;
  - either reading is missing.
- Otherwise it **proposes** the challenger. `file_owner_card` raises one owner card
  (`canonical_model_upgrade`) and records every comparison.
- Nothing is adopted. Replacing or re-freezing Laura still needs an owner decision in
  `canonical.AUTHORISED_IDENTITY_CHANGES`.

## Acceptance evidence (testslot)

| Test file | Result |
|---|---|
| `tests/test_w4_upgradecmp.py` (new) | 5/5. Includes the row's named test, "a realism win with identity loss is refused" |
| test_vacuity | 0 fail |

## Board rows

- F-738: the comparator and the owner card are built.
- F-737 / F-745 (improvement cell and experiments): these now have their promotion gate.
  - Running experiments needs model-bearing renders. These are externally gated: no provider
    renders certified crochet faithfully yet.
  - The reservation and budget path is the existing `check_budget`.
