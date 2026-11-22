# APPROVE-FIX: "Approve" and "Approve all" now actually approve

Branch: `eng/approve-fix`. Not deployed, and no PR opened.

## What was wrong

### A. Approvals did not persist

The production HTTP log for brambleloop-os (read-only, 2026-11-22 UTC) shows:

| time (UTC) | request | result |
|---|---|---|
| 00:16 to 00:19 | `GET /api/cc/approve-everything` (the list) | 200 after **166 s** |
| 00:19:33 | `POST /auth/step-up` | 200 (password and TOTP accepted) |
| 00:19:38 | `POST /api/cc/approve-everything` (the press) | **499**: browser closed it before any answer |
| 00:21 | list again | 200 after **122 s** |
| 00:22:15 | step-up | 200 |
| 00:22:51 | press | **499** |
| 00:25 | container restart | |

So the step-up worked, but the press itself never finished. `execute()` re-ran the whole two-minute preview (every release's evidence packet, every Laura card, every row) before writing anything. The browser gave up and the page was reloaded. Then the container restart at 00:25 ended the run. Nothing was committed, and no message reached the owner because there was never a response.

A second design problem made it worse: one refusing row anywhere rolled back every other row in the press.

Ruled out: the step-up token not being carried (the gate reads it from the session row, and the step-up returned 200), CSRF failures (the request would have returned 403, not 499), and the approve writing to a different table (the press and the page both read `owner_actions`).

### B. Approve-all covered only about 8 items

Everything that was not routine, in-cap spend, an improvement decision, a grant or a sample card fell into "needs its own card". That included unclassified cards that only need the owner's yes.

## The fix

- **The press sends the exact previewed items** (`preview()["items"]`). `approve_everything.execute_items`:
  - re-reads **only those rows** and re-judges each one at the write;
  - approves an item only while it is still exactly what you saw (same class, target, amount and grant content digest). Nothing you did not preview is ever approved;
  - writes each item in its **own savepoint**. A refusal is reported for that item and never undoes the others;
  - **stores the outcome** in the batch audit row. The list shows it as "Last press ... approved N" even if the browser closed the request.
- **The list loads faster.** The page asks for `?cards=0`, which skips a second full inbox read the page already does itself. The preview now reports `timings_ms`, which shows where the remaining time goes.
- **Approve all covers more.** New class `owner_approved_step_up`: every unclassified owner card that needs no choice between answers and that no other code reads as a decision. It is recorded `satisfied` as "owner-approved via step-up; not an attestation".
- **Still never in any bulk, each listed with its reason:**
  - child-safety holds;
  - physical attestations (`physical_size_conflict:`);
  - acts outside the app (OAuth consent, KYC, banking, legal, Shop Manager), each with a "Do it at ..." link;
  - spend over the CA$100/month cap, or with no stated amount;
  - ceiling raises;
  - cards needing a choice (acceptance ruling, launch decisions, phase, ads, buyer messages, storefront).
- **Spend:** headroom is re-read at the press, so a spend that now crosses the cap is refused for that row. The cap is never raised. Approval spends nothing itself, and every spend path's own guard still runs.
- **Grants** are signed only through their existing path, bound to the previewed content digest, with the publication evidence check.
- **The step-up** is still fresh (password and TOTP), required, and spent by the press.
- **Failures are visible.** The result stays on the card, never only in a toast that disappears.

Decision recorded as **D-APPROVE-FIX** in `brambleloop/DECISION_LOG.md`.

## What you will see

1. Approvals → **"Approve all (N)"**, with the full list of what it approves under "N in this press".
2. After the password and TOTP, a box saying "Approving N items. Keep this page open".
3. Then, at the top of the refreshed card: **"Approved N. Needs your action elsewhere M (listed below)."** If any item was refused: "Could not approve K", with each item's reason.
4. The approved cards are gone from the list. Below that, **"Needs your action elsewhere (M)"** lists every remaining item with its reason, and a link where one exists.

## Tests

- **New: `brambleloop/tests/test_approve_fix.py`, 8 passing.** It uses the real routes, a real login with a test TOTP, step-up and CSRF/nonce. It covers:
  - the press approves in the database, and the re-rendered list and inbox no longer show the approved items;
  - a 173-row queue: 170 approved in one press, 3 child-safety rows kept;
  - one failing row never undoes the others, and its reason is shown;
  - forged or unpreviewed items are never approved;
  - the press still needs a fresh step-up;
  - the spend cap is re-checked at the write;
  - rows that need a choice stay on their own card;
  - the page sends the items and keeps the outcome on screen.
- **Changed: `tests/test_approve_all_v2.py`.** `something.nobody.named` is now in the press (`owner_approved_step_up`). 15 passing.
- **Related suites,** run as `JOBS=3 SUITE_REGISTRY=0 SUITES="..." bash run_tests.sh`:
  - suites: test_approve_fix, test_approve_all_v2, test_eng_approvals, test_owner_directive_approve_all, test_mission_control2, test_mission, test_image_bf, test_v11_cc_actions, test_w4_owner_queue_race, test_opus2_owner_queue_races, test_ws4_3_owner_signing_flow, test_vacuity;
  - result: **TOTAL PASSING 144; suites failing 0** (run record `artifacts/suite_runs/20261122T003244Z-1124.json`).
- The full suite was **not** run.

## Not verified

- **The preview GET may still be slow** (grant evidence packets and Laura cards). The press no longer depends on it, and the list now reports `timings_ms` to find the cost.
- **Approved rows may be raised again.** Some producers could raise a closed row again if its underlying condition still holds in production; `owner_queue.ensure` inserts a new row in that case. Not observed here, because there is no production data. Check with `last_press` and the next list after deploy.
- Not deployed. The live site is unchanged until this branch is released.
