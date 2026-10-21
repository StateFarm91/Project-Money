# Independent security and integrity review: W4-LISTREADY at d69a3ec

- **Reviewed:** `origin/claude/w4-LISTREADY` @ d69a3ec.
  - **Diff:** `git diff 8d520ed7..d69a3ec4 -- brambleloop/src brambleloop/tests`, 15 files, +224/−96.
  - **Commits:** 8afb843 (R1), a9fc0db (R2), 96f0eb1 (R3), e85b1d4 (R4), 8e7f840 (R10), e2617e5
    (R11), 23d9768 (decision index), 6101505 (`activate` → `open_batch`) and d69a3ec (board
    regeneration and card snapshot).
  - Outside `src`/`tests`, the range also touches `DECISION_LOG.md` (append only), `LISTREADY.md`
    and the three board files under `research/final_build/w4/`. I read these as well.
- **Previous review:** `INDEPENDENT_SECREVIEW_LISTREADY_8d520ed.md` on
  `claude/w4-SECREVIEW-LISTREADY-8d520ed`. Its verdict was NO BLOCKER, with R1 MEDIUM, R2–R4 LOW
  and R5–R11 INFO.
- **Reviewer:** an independent reviewer that did not write this code. This is a review only.
  - Nothing was fixed, deployed, posted or paid for.
  - No secrets were used and no production endpoint was called.
- **Tests:** a full certification suite was running on the shared machine, so I ran only small
  targeted test files, one at a time, at `nice -n 19`, in a scratch venv and scratch worktrees.
- **Date:** 2026-10-21 (UTC).

## Verdict: **NO BLOCKER.** d69a3ec may be released with SHADOW unchanged

- **R1 and R2 are closed.**
  - The operator token can no longer write the `delivery_policy` reading.
  - Every store-setting confirmation now needs an owner session plus step-up.
  - Both regression tests fail on 8d520ed and pass on d69a3ec.
- **R4, R10 and R11 are closed.**
- **R3 is closed for the case that the previous review described**, which is a target card that
  is already done. **The reverse order still drops the ask (S1, LOW, reproduced).**
  1. OA-F is merged while `policy_settings_paste` is open.
  2. That card then closes on its four getShop checks.
  3. OA-F is now "already done", so the FAQ and cancellations ask is gone with no evidence.

  This is the same severity, and has the same blast radius, as R3. Nothing can publish, activate
  or spend through it.
- **No publication or spend path changed.**
  - `pipeline.py`, `store.publish`, `store.activate`, `for_publish`, `superseded_release`,
    `grant_in` and the batch caps are not in the diff.
  - `launch_review.activate` → `open_batch` is a rename of one line. The body is unchanged, and
    no caller of the old name remains.
- **The board regeneration closes nothing by hand.**
  - I re-ran the generator at its recorded `branch_head` (e2617e5). The closed-on-production list
    and every `verified_complete` count match the committed board exactly.
  - No row moved *into* `verified_complete`. Twenty rows moved out of it.
- **F-498 left the closed list for the reason the commit message gives:** one of its three
  evidence tests was renamed. **F-586 and F-591 also left the list, and the message does not say
  so (S2, INFO).** They left by the generator's module-changed rule, and they moved in the safe
  direction.
- **No test was weakened.**

| # | severity | area | one line |
|---|---|---|---|
| S1 | LOW | store cards (R3 residual) | `store_readiness.py:480`: OA-F still closes as "merged" when `policy_settings_paste` is **open**. When that card later closes on getShop alone, OA-F is skipped as "already done" (`:500`), so the FAQ and cancellations ask disappears with no evidence. Reproduced on d69a3ec |
| S2 | INFO | board records | d69a3ec's message names only F-498. F-586 and F-591 also left `closed_on_production_evidence` (36 → 33), because `intel/etsy_surfaces.py` now differs from deployed b931d17. The board's `branch_head` is e2617e5, not d69a3ec |
| S3 | INFO | R4 residual | `release_recovery.py:336` still skips a product whose versions cannot be ordered, and does not record it. The census is used whatever its age, so a stale census can keep a P2 open. That fails visible, not silent |
| S4 | INFO | R1 depth | The optional consumer-side guard was not added: `shop_check_context` still honours a `delivery_policy` reading whoever recorded it. This has no exposure today, because the deployed b931d17 has no `delivery_policy` page, so no operator-written reading can exist |

---

## 1. Closure table

"Fails on 8d520ed" means that I copied d69a3ec's version of the test file into a worktree of
8d520ed and ran it there.

| # | prev sev | closed? | fix (file:line at d69a3ec) | regression test | fails on 8d520ed? |
|---|---|---|---|---|---|
| R1 | MEDIUM | **Closed** | `commerce/shop_observations.py:33`: `OWNER_ATTESTED_PAGES` now includes `delivery_policy`. `estate_api.py:77` refuses those pages on the operator route with 403 `OWNER_SESSION_REQUIRED`. The page is matched exactly, and `record` uses the same exact string (`:112`), so a case or whitespace variant cannot slip past the check and still be recorded | `test_w4_owner_observations::test_the_operator_credential_cannot_attest_kyc_tax_or_the_inbox` now posts `delivery_policy` too | **Yes**: on 8d520ed it gets a 200 and records the reading |
| R2 | LOW | **Closed** | `app/command_center/api.py:827`: `auth.require_stepup(db, request, "store.settings.confirm")` comes before `shop_sync.confirm`. `store.js:80` sets `requiresStepUp: true`, and `sw.js` is at v24, so the old shell is evicted | `test_w4_shopsync::test_a_store_setting_confirmation_needs_step_up`: step-up expired → 403 `STEP_UP_REQUIRED`; after step-up → 200; also checks that the JS flag is present | **Yes**: on 8d520ed it gets a 200 with no step-up |
| R3 | LOW | **Partly closed.** The residual is S1 | `store_readiness.py:480`: the merge check now uses `open_rows` instead of `all_keys` | `test_w4_storefront_checks::test_oa_f_is_not_merged_into_a_target_card_that_is_already_done` | **Yes** |
| R4 | LOW | **Closed** (the residual is S3) | `runtime/release_recovery.py:310-326`: the latest listing census (`estate` rows with `ours`, `state == "active"`, a slug and a version) is merged with the local rows that say `active`. Census `ours` comes from `_expected_listings`, which covers every `Listing` with an `etsy_listing_id` in any local state. An unreadable census adds nothing and removes nothing | `test_w4_listready::test_r4_etsy_state_surfaces_a_superseded_live_listing_our_row_does_not_show`: the local row is `draft`, the census says `active`, and a P2 opens with `source` and `should_auto_renew` | **Yes** |
| R5 | INFO | Not changed (hardening) | — | — | — |
| R6 | INFO | Not changed (test strength) | — | — | — |
| R7 | INFO | Not changed. The rename touches only the name | — | — | — |
| R8 | INFO | Not changed. S1 is one concrete instance of it | — | — | — |
| R9 | INFO | Not changed | — | — | — |
| R10 | INFO | **Closed** | `DECISION_LOG.md:2225`: `D-W4-STOREFRONT-E3` records the commission with its source and scope. The log diff is additions only. `LISTREADY.md:124` now states E2 and E3 as they are | `test_w3_decision_index` passes. The index gains `D-W4-LAUNCH-VISION-BATCH` and `D-W4-STOREFRONT-E3`, both at level 3, and both are real `###` headings in the log | n/a |
| R11 | INFO | **Closed** | `launch/readiness.py:241-242`: `identity_verified` must be `is True` on the same FRESH `legal_and_tax` reading, and it adds its own `missing` line. On an exception it stays at its default of False | `test_payout_…`: `missing` goes from 2 to 3, and a newer reading with `identity_verified: false` makes it not ready | **Yes** |

**The R4 implementation, checked line by line:**
- The census rows and the local rows are keyed by `(slug, version)`. Census rows win on a
  collision (`setdefault`).
- A stale incident still resolves when its signature is no longer held.
- Dropping `needs_owner_path: True` from `detail` is correct. `incident_lifecycle.REMEDIATION`
  maps `listing.superseded_live` to `("owner", …)`, so the computed `needs_owner_path` is False.
  The old detail flag contradicted that.
- Nothing writes to Etsy.

## 2. Owner-evidence routes and step-up

**Every route** below is under `/api/cc/`, so `auth.gate` has already required an owner session,
same-origin, CSRF HMAC, a nonce and a timestamp. I read every `@router.post` route in
`command_center/api.py` for `require_stepup`.

| route | operator token alone | owner session, no step-up | owner session with step-up |
|---|---|---|---|
| `POST /api/etsy/shop-observation`, `delivery_policy` / `messages` / `legal_and_tax` | **403** (R1 closed; tested) | n/a | n/a |
| `POST /api/etsy/shop-observation`, other pages (`policy_violations`, …) | 200 (by design; operator readings, not owner attestations) | n/a | n/a |
| `POST /api/cc/etsy/shop-observation` (any page) | 401 | 403 | 200 |
| `POST /api/cc/store/settings/{key}/confirm` (banner, payout_details, …) | 401 | **403** (R2 closed; tested) | 200 |
| `POST /api/cc/launch-review/activate`, `…/resume` | 401 | 403 | 200 |
| `POST /api/cc/authority/approve/{key}`, `…/grant`, `/actions/{action}`, `/images/runs/approve`, `/experiments/*` | 401 | 403 | 200 |

**What this establishes:**
- **No owner-evidence input to listing or first-sale readiness can be satisfied with the operator
  token alone.**
- **Every confirmation that readiness reads now needs an owner session plus step-up.** That covers
  the store-setting confirmations, the owner-attested observations, and launch-review activation
  and resume.

**Routes outside this diff:**
- **`POST /images/runs/visual-approval` has no step-up.** It was reviewed in
  `INDEPENDENT_SECREVIEW_7f6dbe8.md` and is still record-only: per `image_production.py:1380-1384`,
  no gate reads it, and `candidate_gates` asserts `owner_visual_approval_is_not_an_input`.
- **`POST /api/owner/decision` is on the operator credential.** It records improvement-loop and
  challenger approvals, by the documented design C-57. It is not listing or readiness evidence, and
  it is not in this diff.

  I note it so the claim above is not read as "every owner route": it is a pre-existing route that
  is not part of LISTREADY.

## 3. New findings

### S1: LOW: OA-F can still be closed by a merge without evidence (R3, reverse order)

**Where:**
- `store_foundation/store_readiness.py:480` closes OA-F as "merged" when
  `etsy_surface:policy_settings_paste` is **open**.
- `:500`: on a later sync, OA-F is in `done_keys` and not in `open_rows`, so it is skipped as
  "already done".
- `policy_settings_paste.evidence_required` (`intel/etsy_surfaces.py`, about line 1532) is four
  getShop fields. It does not include FAQ or cancellations.

**Reproduced on d69a3ec:**
1. Start with both cards open.
2. `sync_owner_actions` closes `store:OA-F` with the reason "merged into
   etsy_surface:policy_settings_paste".
3. Mark `policy_settings_paste` done, as its getShop checks do.
4. The next sync gives `store:OA-F` the reason "already done". Neither card is open.

**Which order is likely:** this is the order that the existing test
`test_store_cards_close_on_the_reading_and_duplicates_are_merged` sets up. In practice, both cards
are usually raised before the getShop policies are pasted, so this is likely the common path.

**Effect:** the same as R3. The licence-FAQ and cancellations ask disappears with no reading.
- It cannot publish, activate or spend.
- SHADOW has no listings.

**Fix:**
- Reopen a merged OA-F when its target closes. For example, keep a `merged_into` marker in
  `reason`, and treat "target done and OA-F closed only by merge" as open.
- Or never close OA-F by merge, and only suppress it while the target is open (`skipped`, not
  `done`).
- Add a test that runs this two-step order.

### S2: INFO: board regeneration records

- **The closures are not hand edits.**
  - I checked out e2617e5, which is the board's `branch_head`, and ran
    `research/final_build/w4/completion_board_final.py` (about 0.4 s).
  - `closed_on_production_evidence` and all three `verified_complete` counts are identical to
    d69a3ec's committed board: 98, 314 and 360.
  - The only differences are 27 rows that are `in_progress` versus `blocked_engineering`. The
    generator decides these from which `origin/claude/w4-*` refs were fetched in the last 24 h. My
    clone fetched only two refs, so this is environmental and closes nothing.
- **What moved between 8d520ed and d69a3ec:**
  - No row moved into `verified_complete`.
  - 20 rows moved `verified_complete` → `implemented_unverified`.
  - 23 rows moved `blocked_engineering` → `in_progress`.
  - 5 rows moved out of `in_progress`.
- **Why F-498 left the closed list.** `_closures` drops it because
  `tests/test_w4_etsysurf.py::test_a_fresh_passing_shop_still_names_what_no_collector_can_observe`,
  named in `BOARD_CLOSURES.json`, was renamed in bcf748f to
  `…_still_names_every_surface_without_a_reading` (`_test_exists` is False). This matches the
  commit message.
- **F-586 and F-591 also left, and the message does not say so.** Their closure records are
  intact. They now classify `implemented_unverified`, because `intel/etsy_surfaces.py` differs
  from deployed b931d17 (`deployed is False`). F-498 would also drop on this rule. The direction is
  safe, but the record should name all three.
- **The board's commit.** The board was generated at e2617e5. 6101505 and d69a3ec came later, and
  they change only `finance/launch_review.py` and `api.py`, which are already absent from or
  changed against production. Regenerating at d69a3ec would give the same classes.
- **The shipped card snapshot** (`app/command_center/snapshots/COMPLETION_BOARD_FINAL_CARD.json`)
  is byte-identical to the generator's `COMPLETION_BOARD_FINAL_CARD.json`, and `test_w4_board`
  passes.

### S3: INFO: R4 residuals

- **A product whose versions cannot be ordered is still skipped silently.**
  `release_recovery.py:336` skips it when `newest is None`, and it does not appear in the result.
  This was the second half of R4. It fails closed only in the sense that no P2 is raised.
- **The census is read with no freshness bound.**
  - A census that is days old can keep a superseded-live P2 open after the owner has deactivated
    the listing. This fails visible, and the next daily census clears it.
  - An old census cannot hide a live listing that the local rows show.

### S4: INFO: R1 depth

- `runtime/etsy_ops.shop_check_context` (around `:124`) still reads the newest `delivery_policy`
  observation without checking `recorded_by`.
- With the route closed, only the step-up owner route can write that page. Deployed b931d17 has no
  `delivery_policy` page (`grep -c` of the deployed file gives 0), so no operator-written reading
  can exist in production.
- Adding a `recorded_by` filter would only add defence in depth.

## 4. Tests

| check | result |
|---|---|
| Weakened tests | **None.** The diff to `test_w4_launch_review.py` is only the rename. `test_payout_…` goes from 2 to 3 missing items and adds an identity-false case, so it is stronger. The other test changes add tests |
| Every new or changed regression test fails on 8d520ed | **Yes**, all five: R1, R2, R3, R4 and R11 |

**Test files run at d69a3ec (nice 19):**

| file | result |
|---|---|
| test_w4_owner_observations | 3/3 |
| test_w4_storefront_checks | 15/15 |
| test_w4_shopsync | 14/14 |
| test_w4_listready | 31/31 |
| test_w4_launch_review | 18/18 |
| test_w4_board | passes |
| test_w3_decision_index | passes |

**Not run:** `test_product_run`, `test_acceptance_gates`, `test_cert_wiring`,
`test_compiler`/`test_reverse`/`test_twin` and the full suite. I left these out because of the
shared machine.

## 5. Publication and spend paths

- **Not in the diff:** `runtime/pipeline.py` (publish, `store.activate`), `publish/*`,
  `integrations/etsy_*`, `finance/*` other than the one-line rename, the budget lock, `grant_in`,
  the batch caps and the `image_vision` gate.
- **Writes:** R4 only opens or resolves non-halting P2 incidents
  (`halts_publication=False`).
- **Card movement:** R1, R2, R3 and R11 only make evidence harder to obtain, or cards harder to
  close.

## 6. Recommended order

1. **S1:** before any first-sale readiness decision relies on OA-F or the licence FAQ.
2. **S2:** name F-586 and F-591 in the board's change note or in BUILD_STATE.
3. **S3, S4, and the R5–R9 carry-overs:** hardening, at convenience.
