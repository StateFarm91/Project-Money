# CLOSE6b: `claude/w4-CLOSE6` merged onto the combined candidate (W4-B2, 2026-10-27)

- **Branch:** `claude/w4-CLOSE6b`, cut from `origin/claude/w4-INTEG7` 4d3d1ee8, with `origin/claude/w4-CLOSE6` ff788bd9 merged (`--no-ff`).
- **Purpose:** to prepare the merge for the integrator's next batch. This branch is not deployed, and CLOSE6 itself is not reviewed here.

## Conflicts and resolutions

| file | conflict | resolution |
|---|---|---|
| `commerce/shop_observations.py` | INTEG7 added the owner-observation pages `messages`, `legal_and_tax` and `delivery_policy` (FIRSTSALE2, LAUNCHPREP), plus their validation. CLOSE6 added the `about` page (F-040). | **Both kept.** The pages and their validators are independent. |
| `launch/readiness.py` (`etsy_first_sale_surfaces`) | INTEG7 changed the failing-check test to `not in es.SATISFIES` and added the `first_sale_surfaces` per-surface readings. CLOSE6 added the About-story requirement but kept the older `!= es.PASS`. | **Combined.** INTEG7's `SATISFIES` semantics are kept, since `!= PASS` would reopen checks INTEG7 accepts as satisfied. CLOSE6's About check is appended to `failing`. INTEG7's per-surface readings follow. |
| `app/command_center/static/sw.js` | INTEG7 is on `cc-shell-v25`; CLOSE6 is on `cc-shell-v17`. | **`cc-shell-v26`.** Both shells changed, so clients must fetch a new shell. Going back to v17 would serve stale caches. |
| `ops/deploy.sh` | INTEG7 writes the readback to `mktemp` (`$rb_out`), which the F-381 rollback decision reads. CLOSE6 writes it to `evidence_BOARD/prod_readback_<sha12>_<UTC>.json` (`$rb_json`) so the board can apply it (F-144). | **CLOSE6's evidence path,** with `rb_out="$rb_json"`. The rollback decision now reads the same durable file, and `READBACK_JSON` still overrides it. |
| `DECISION_LOG.md` | Both sides appended at the end. | **Union,** INTEG7's entries first and then CLOSE6's D-W4-CLOSE6-OVERRIDES, -FMREGATE and -F846. None of the three was already present. The log is append-only and nothing was edited. |
| `build2/final_master_closure.json` | Generated one-line snapshot. | **Regenerated** by `research/final_build/aggregate.py` on the merged tree. The regenerated `closure_matrix.json` is identical to the auto-merged one (all 917 rows and the summary). |
| `w4/BUILD2_LEDGER.json` / `.md` | Only `as_of` and "Generated" differ. Every row auto-merged. | CLOSE6's later timestamp (13:32:25Z) is taken. |
| `w4/COMPLETION_BOARD_FINAL.{json,md}`, `_CARD.json`, CC snapshot card | Generated (34 hunks). | **Regenerated** with the merged `completion_board_final.py`, which includes CLOSE6's readback application (F-144). `test_w4_close6_readback` requires it. The CC snapshot card is a copy of the regenerated card. |
| `w4/PRELAUNCH_SCOPE.{json,md}` | Generated from the board (36 hunks). | **Regenerated** with `prelaunch_scope.py` from the regenerated board. |

## Read this before trusting the regenerated board

The board's production evidence in `evidence_BOARD/` is pinned to **b931d17** (read 2026-10-20T05:40Z). Production now runs **b2e49455**, verified via `/health` at 21:50Z. The board compares each module against the production tree it was given, so the many modules INTEG7 has changed since b931d17 read as `implemented_unverified`.

| class | regenerated here | INTEG7 board | CLOSE6 board |
|---|---|---|---|
| Final Master verified_complete | 286 | 360 | 403 |
| Build 2 verified_complete | 76 | 98 | 178 |

The drop is stale production evidence, not lost work. The integrator should refresh `evidence_BOARD` against b2e49455, then regenerate the board, the card and PRELAUNCH_SCOPE. Neither count above is a completion claim.

## A semantic conflict that git did not show

CLOSE6's F-040 makes the About story a readiness input. Two INTEG7 tests, written after CLOSE6 branched, build a world in which "every input is genuinely satisfied" or "only the listing check fails", and neither world contains an About observation:

- `test_w4_firstsale2_surfaces.test_ready_when_every_input_is_genuinely_satisfied`
- `test_w4_storefront_checks.test_e4_a_failing_check_opens_only_its_own_owner_action`

On the merge both tests failed with `about_story:unobserved`. That is the correct readiness behaviour. **Resolution:** each fixture now records the owner's dated About observation, which is the newly required evidence. No assertion was changed or removed.

## Tests (named suites, on the merge)

All of these pass:

- **CLOSE6 suites:** `test_w4_close6_ads`, `_ask`, `_brief`, `_hygiene`, `_proof`, `_readback`, `_scope`, `_shop`, `_timeline`, `_titles`.
- **Command Center and storefront:** `test_w4_etsysurf`, `test_w4_smoke`, `test_w4_firstsale2_surfaces`, `test_w4_owner_observations`, `test_w4_launch_review_card`, `test_w4_storefront_checks`, `test_w4_board`, `test_w4_cc_company`.
- **Deploy and rollback:** `test_deploy_path`, `test_deploy_verify`, `test_w3_deploy_evidence`, `test_w4_fmbatch1_rollback`, `test_w4_rollback_rehearsal`.
- **Launch and closure:** `test_w3_final_master_gate`, `test_w4_close5_rows4`, `test_launch`, `test_k8_shop_cx`.

Before its fix, `test_w4_close6_readback` failed on the `$rb_json` variable and on the board readback. Both pass after the deploy.sh resolution and the board regeneration.
