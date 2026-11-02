# Independent integration review: INTEG5E (claude/w5-INTEG1 4af3418f)

Date: 2026-11-02 (UTC). Reviewer: independent, read-only. Subject: 4af3418f (parent f7466c06).

## Verdict: SHIP (certify 4af3418f)

## 1. Applied change == reviewed delta
- `git diff f7466c06 4af3418f` and `git diff a859f6fe d3a485a1 -- brambleloop/src brambleloop/tests` touch the same 2 files
  (creative/fallback_constructions.py +12/-9, tests/test_opus2_stocking.py +20), 32 insertions / 9 deletions each.
- Once `index` lines and hunk line numbers are removed, the two diffs are byte-identical, and so are their +/- lines.
  Nothing is missing and nothing extra was added. Only the hunk offsets differ, because the tapestry code sits above in f7466c06.
- Content: OPUS2O-6 (the contrast/stripe cuff needs 2 distinct palette colours; "solid" removed from the stocking allowlist),
  OPUS2O-9 (the dead Northlight/Home Depot citation removed from STOCKING_SIZE_SOURCE), and
  OPUS2O-7 (a test pins the pet route to the shared fold for U+2011/U+2012/U+2212/fullwidth "Cat Bed").

## 2. Interaction with f7466c06 (tapestry route and the single fold_title)
- `def fold_title` appears exactly once in all of brambleloop/src (fallback_constructions.py:32). No other module defines it or assigns to it.
- That one definition is the strong version: NFKC, `.replace("’", "'")`, every Pd dash and U+2212 mapped to "-", lower case, whitespace collapsed.
- Callers: the pet route (L195-196), the stocking route (`plan`, L236), the new stocking contrast-cuff check (L488),
  `tapestry_route` (L901), `_tapestry_chart` (L954) and `tapestry_basket` (L982). They all use the shared fold.
- d3a485a1 makes no source change to the pet route. OPUS2O-7 is a test-only pin, and it passes against the shared fold.
- An AST scan of the module's top-level functions, classes and assignments finds no name defined twice.

## 3. Suites (run one at a time from the worktree's brambleloop/, venv-integ4)
Command: `PYTHONPATH=src:tests /home/user/bl-runs/venv-integ4/bin/python tests/<suite>.py`
| suite | exit | OK | FAIL |
|---|---|---|---|
| test_opus2_stocking | 0 | 8 | 0 |
| test_opus2_pet_bed | 0 | 7 | 0 |
| test_opus2_tapestry_basket | 0 | 7 | 0 |
| test_opus2_draft_constructions | 0 | 18 | 0 |
| test_vacuity | 0 | 8 | 0 |
The full suite was not run (as instructed).

## Findings
None blocking and none new. The OPUS2Q-4/-5 LOW follow-ups were already routed to opus2 by the integrator.

## Commands
git fetch origin claude/w5-INTEG1 opus2/p0-stocking; git worktree add --detach .../integ5e 4af3418f;
git show / git diff comparisons (normalized), grep and an AST duplicate scan, the 5 suites above, and worktree removal.
