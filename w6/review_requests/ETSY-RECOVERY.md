# Review request: ETSY-RECOVERY (branch `eng/etsy-recovery`, from `claude/w6-release-19h4`)

_2026-11-21, UTC. Not deployed. No PR._

## 1. Why D-OWNER-ETSY-EXERCISE reports "not clean": what is known, what is not

Production (17f17c20) shows two attempts, both `ATTEMPTED, AND THE SHOP IS NOT CLEAN`.
The cause **cannot be determined from what production recorded.** The directive's audit
rows keep only `ok`, `status` and `shop_is_clean`. The deploy logs hold only
`attempt N: ok=False`. This session has no operator token, so it cannot read the report
(or the owner queue rows that name the listing). It read no Railway variable values.

From code, `shop_is_clean = shop_read_back.ok AND no ledger draft still on Etsy`. Three
candidates fit two identical not-clean results:

| Candidate | Mechanism in code | Repeats on attempt 2? |
|---|---|---|
| A. Own delete fails (e.g. 403 `listings_d`, 409) | cleanup raises; the draft stays in the ledger and in the shop | yes; attempt 2's sweep fails too and **adds a second draft** (the duplicate) |
| B. Soft delete (204, then GET 200 with state `removed`) | `reconcile` treats any 200 as stranded; the ledger row never closes | yes, **forever**: every later run reconciles the same row |
| C. `getListing` cannot see drafts | `delete_listing`'s pre-read 404s, so the delete fails; the shop's draft list still shows the marker | yes |

A leftover from an earlier run can only come from the ledger. No exercise ran before
02:20Z (P0-1), so any leftover is attempt 1's draft, seen again by attempt 2.

**What changes so the next run answers this.** `etsy.exercise_finished` now carries a
fixed-vocabulary `cause`: failed step names, taxonomy outcomes for the
sweep/create/cleanup/verify steps (for example `cleanup:...`, `verify_cleanup:delete_is_soft`),
read-back and ledger counts, and recovery counts with the HTTP status class. This is shown in
`factory_visibility.owner_etsy_exercise.last_runs[].cause` and in `last_recovery`.

## 2. Recovery (`integrations.etsy_exercise.recover_with` / `recover`)

It deletes a listing only when **all** of these hold:
- **Own.** The `etsy.exercise_draft_created` ledger names the id. The ledger title carries
  the marker. Etsy's title equals the ledger title, or the exercise's own
  `"<title> updated"` rename. The shop id matches.
- **Draft.** Etsy lists the id in the shop's `state=draft` read, and that row says `draft`.
- **Never active.** Etsy has no active→draft transition. This system holds no `etsy.activate`
  effect intent for the id. Etsy reports no views or favourites. If the intent table can't be
  read, nothing is deleted.

The delete goes through the unchanged `delete_listing(expect_states=("draft",))`. It counts
only if the read-back gives `getListing` 404 **and** the id is gone from a fresh draft read.
Both are required because of candidate C.

Each listing gets one outcome from `RECOVERY_OUTCOMES`: `removed_verified`, `already_gone`,
`delete_failed`, `delete_unverified`, `left_not_draft`, `left_not_provable`, `left_foreign`,
`could_not_ask`. Foreign, active and unprovable listings are never touched. A failed or
unverified delete is reported, the ledger row stays open, and it goes to the owner queue
(one row per listing, as before).

Where recovery runs. Both doors need the operator credential:
- `POST /api/etsy/exercise?mode=recover` runs recovery only. It creates nothing.
- `mode=full` now runs recovery first. If one of the exercise's own drafts cannot be removed,
  **no new draft is created**. This stops candidate A from adding a duplicate on every run.

`owner_authorised=False` is unchanged (it is hard-coded in `_client`). Recovery has no
activate or publish call (a test pins this). Cost: CA$0.

## 3. What was requested and NOT built: D-OWNER-ETSY-EXERCISE-2

The task asked for a new directive id, D-OWNER-ETSY-EXERCISE-2. It would give 3 attempts over
a fresh 24 h window, citing "You do it" / "full autonomous", and start at boot on
`RAILWAY_DEPLOYMENT_ID`. **This session's safety review blocked it, and it was not built.**
The owner gave D-OWNER-ETSY-EXERCISE a fixed budget of 2 attempts in one window, and that
budget is spent. Minting a new budget for unattended writes to the real shop, based on a
re-reading of earlier owner words, is the kind of self-extension of authority that needs a
fresh owner decision. Nothing on this branch runs the exercise or recovery at boot.

See OWNER_ACTIONS_P0.md P0-1b for the single owner action that replaces it.

## 4. Tests

New, in `tests/test_etsy_exercise.py`:
- an own leftover draft and its duplicate are cleaned;
- a ledger draft Etsy no longer holds is settled without a delete;
- a foreign, active, renamed, activated or viewed listing is never touched (no DELETE is sent);
- a failed delete is reported, with status class, owner action and open ledger row;
- a soft delete is `delete_unverified`, not cleaned;
- a full run creates no new draft while an own draft cannot be removed;
- visibility holds no id, title or Etsy text;
- the `mode=recover` endpoint still needs the operator credential;
- recovery cannot activate.

One test was updated: the step-0 sweep test now asserts that recovery removed the stale draft.

| Suite | Result |
|---|---|
| test_etsy_exercise | 52/52 |
| test_owner_etsy_exercise | 7/7 |
| test_factory_visibility | 2/2 (updated for the new shape) |
| test_vacuity | pass |
| test_etsy, test_etsy_transport, test_etsy_readback_observe, test_w4_etsycomm, test_w3_etsy_upload_readback, test_w4_readback_evidence, test_w4_retfix_retention_keys | pass |

These fail **identically on the base branch** (pre-existing, not caused here):
- `test_etsy_oauth_callback` (2) and `test_w4_fmbatch1_retention_guard` (1): retention has no
  decision for `unresolved:runtime/release.py::_attempt_gate_refusal`;
- `test_etsy_publish_e2e` (1): `KeyError('etsy_listing_id')`;
- `test_w4_launchfix` (2): `test_img_*`.

The new `etsy.exercise_recovery` action has a retention decision (`latest`).
