# Independent security and integrity review: W4-LISTREADY at 8d520ed

- **Reviewed:** `origin/claude/w4-LISTREADY` @ 8d520ed.
  - **Diff:** `git diff b9137b55..8d520ed7 -- brambleloop/src brambleloop/tests`, 31 files, +1282/−86.
  - **Commits:** 7eec363 (LAUNCHPREP E1–E7, AGENTAUDIT E-6/E-8), 58aea40 (launch-review tables at
    boot), 3a52e2b (retention, card test), b58e925 (merge of `final-candidate-b997efd`, which
    carries 1580053), 1a7b1f3 (N2), d385d46 (N1/N3), 3d3adc8 (report §11) and 8d520ed (N1 status
    readers).
- **Also read:**
  - the previous review, `INDEPENDENT_SECREVIEW_LISTREADY_b9137b5.md` on
    `claude/w4-SECREVIEW-LISTREADY-b9137b5`. Its verdict was NO BLOCKER, with N1 MEDIUM, N2–N3 LOW
    and N4–N9 INFO;
  - `research/final_build/w4/LISTREADY.md` at 8d520ed (§11).
- **Reviewer:** an independent reviewer that did not write this code. This is a review only.
  - Nothing was fixed, deployed, posted or paid for.
  - No secrets were used and no production endpoint was called.
  - Tests ran at `nice -n 19` in a local venv. `test_product_run`, `test_acceptance_gates` and
    `test_cert_wiring` were not run.
- **Date:** 2026-10-21 (UTC).

## Verdict: **NO BLOCKER.** 8d520ed may be released with SHADOW unchanged

**The previous findings:**
- N1 is closed.
  - A single newest-by-version definition (`ops.artefacts.newest_release`) is now used by every
    "current release" reader the previous review listed.
  - `gate.certify` refuses a new certification of a version older than the newest certified one.
- N2 is closed.
- N3 is closed for the scenario the previous review described. A coverage residual remains (R4).
- Every N1, N2 and N3 regression test fails on b9137b5 and passes on 8d520ed. I re-ran this myself.

**No publication path is weakened:**
- `for_publish`, `superseded_release`, `store.publish` and `store.activate` are not in the diff.
- The `standards_gate` input (`teardown.enforce.current_release`) is now correct in the
  out-of-order state.
- The new certify refusal cannot block the newest version, except when a sibling version cannot be
  ordered (R5, INFO).

**The storefront changes:**
- No change turns **missing or stale** evidence into PASS:
  - a blank banner reads NO_EVIDENCE;
  - NOT_APPLICABLE needs five conditions, and each one is checked;
  - a stale or blank getShop reading closes no card.
- **One evidence source can be forged, though (R1, MEDIUM).** The new `delivery_policy` page is
  accepted on the shared **operator token**. A reading posted there turns a blank delivery policy
  from FAIL into NOT_APPLICABLE. That satisfies a first-sale check and can close the
  `policy_settings_paste` owner card. This is the F7 pattern again, for a new page.
- **The confirmation route does not require step-up (R2, LOW).** The owner-confirmation route
  that the banner (E1) and payout (E-8) evidence now rely on needs an owner session and CSRF, but
  **not step-up**.
- **Neither route is reachable with the operator token alone.** R1 is not a route problem: it is
  the operator *observation* route accepting a page it should refuse.

**Releasing with SHADOW unchanged is safe.** Neither R1 nor R2 can publish, spend or activate
anything:
- R1 moves an owner card and the launch-readiness report;
- R2 needs a signed-in owner session.

**Fix R1 (one line) before any readiness or STAGING decision rests on the first-sale surfaces.**

| # | severity | area | one line |
|---|---|---|---|
| R1 | **MEDIUM** | E2 evidence | `delivery_policy` is not in `OWNER_ATTESTED_PAGES`. The operator token can post `editable_delivery_box: false`, which turns `policy_shipping_set` NOT_APPLICABLE, satisfies it, and can close `etsy_surface:policy_settings_paste` |
| R2 | LOW | E1 / E-8 evidence | `POST /api/cc/store/settings/{key}/confirm` has no `require_stepup`. A banner or payout confirmation made with no step-up now passes `banner_set`, closes `info_and_appearance_setup`, and is one of the three legs of `payout` readiness |
| R3 | LOW | store cards | OA-F (privacy, FAQ with licence, cancellations) is closed as "merged" once `etsy_surface:policy_settings_paste` exists, **even when that card is already done**. The FAQ and cancellations ask then disappears with no evidence |
| R4 | LOW | N3 residual | `superseded_live_listings` sees only `Listing.state == "active"`. A listing the owner activated in Shop Manager stays `published` in the database and is never surfaced. Unorderable versions are skipped silently |
| R5 | INFO | N1 refusal | One certified sibling with an unorderable version (for example `1.1.0-hotfix`) makes every new certification of the product refuse as `older_than_newest`. This fails closed, but it is audit-only, with no owner item |
| R6 | INFO | tests | The boot-tables regression test passes on b9137b5, so it does not reproduce the defect. The fix itself is verified by a fresh-process probe |
| R7 | INFO | N2 | The `/launch-review/resume` route does not catch `DuplicateJob`, and `resume_key` is count-based, so two concurrent resumes return a 500. Re-activation adds a second batch row with the same `batch_id`. The caps still hold |
| R8 | INFO | cards | Closures are one-way. A closed OA-E is never reopened ("already done"), and `info_and_appearance_setup` is reopened only on FAIL, which a blank banner no longer produces |
| R9 | INFO | E6 | `_is_rate_limited` matches `429` anywhere in the error text, and the snapshot can sleep about 85 s in the worker. The retry is bounded, and errors other than 429 are re-raised unchanged |
| R10 | INFO | records | The owner's E3 commission is not recorded in `DECISION_LOG.md`. LISTREADY.md:124 and :389 still say the snapshot fails `policy_additional_unset` |
| R11 | INFO | E-8 | `payout_evidence` reads `tax_position` but not `identity_verified`. A fresh legal_and_tax reading with `identity_verified: false` still counts as `tax_recorded` |

---

## 1. Per-finding closure table

"Fails on b9137b5" means I copied 8d520ed's test files into a worktree of b9137b5 and ran them
there, at nice 19.

`test_w4_launch_review` aborts at import on b9137b5, because `LR.vision_open` does not exist. I
changed only that module-level line to a `getattr` fallback so that the individual tests could run.

| # | sev | closed? | how verified | regression test fails on b9137b5? |
|---|---|---|---|---|
| N1 | MEDIUM | **Closed** | See the N1 notes below the table | **Yes**: 4 of the 5 N1 tests fail on their assertion. `…display_readers…` fails with an ImportError, and it is a source-text check (R6 notes) |
| N2 | LOW | **Closed** | See the N2 notes below the table | **Yes**: `…activation_is_refused_while_the_vision_gate_is_closed` and `…release_with_no_review_call_is_not_counted…` fail on their assertion; `…stuck_queued_release_is_requeued…` with a KeyError (`requeued`); `…unused_and_can_be_reactivated…` with an AttributeError (`UNUSED`); `…ceiling_reverts_when_the_batch_completes` with a KeyError |
| N3 | LOW | **Closed for the stated scenario.** The residual is R4 | See the N3 notes below the table | **Yes**: `test_n3_…` fails with an AttributeError on b9137b5 (the function did not exist) |
| N4–N9 | INFO | Recorded in LISTREADY §11 as INFO. N7 (binding the grant to the batch's own job) and N8 (unique `batch_id`) were not hardened. R7 widens N8 slightly | Read only | n/a |
| Backup export | defect | **Fixed** | `core/db.py` imports `finance.launch_review` in `create_all`. In a **fresh process** that never imports the module, `Database.create_all()` creates `launch_review_batches` and `launch_review_calls` on 8d520ed and not on b9137b5 (my probe) | **No** (R6): `test_a_model_reservation_then_a_continuity_export_succeeds` passes on b9137b5, because the test module imports `launch_review` before `create_all` |

**N1 notes.**
- `newest_release(session, product_id)` (`ops/artefacts.py:553`) chooses by `newest_version` from
  certified rows, and returns None when the versions cannot be ordered. It is used by:
  - `teardown.enforce.current_release` (`teardown/enforce.py:196`), which feeds `standards_gate`;
  - `_targeted_rebuild` (`runtime/release.py:4611`);
  - `inventory.chain_evidence` (`products/inventory.py:166`);
  - `teardown.lab` (three readers), `benchmark_matrix`, CC `readers` and `ask`.
- The two CC status readers pass `certified_only=False`. Every `PatternVersion` row is written
  `certified=True` (`pipeline.py:1405-1419` is the only writer), so in practice this is identical.
- **The refusal** (`pipeline.py:914-920`):
  - it runs after the Gate E halt check and before `duplicate_certification`;
  - it refuses when `newer_certified(slug, version)` is non-empty **and** this version has no
    stored row;
  - it audits `gate.certify_older_than_newest`.
- **Probed on 8d520ed with the suite's own helpers:**

  | case | result | expected |
  |---|---|---|
  | (a) certify 1.2.0 with 1.1.0 certified | granted | correct |
  | (b) re-certify the newest, 1.2.0 | granted | correct |
  | (c) re-certify 1.2.0, already stored, with 1.3.0 certified | granted (a document refresh) | acceptable: it updates the existing row in place, so the bad ordering is not recreated; every reader now orders by version, and publication still refuses the superseded release |
  | (d) certify 1.2.0 with an unorderable sibling certified | refused | fail-closed (R5) |
  | (e) `1.2` certified, then `1.2.0` | granted, and `1.2.0` is treated as newer | harmless |

- **The refusal cannot block a legitimate certification of the newest version,** except in case
  (d).

**N2 notes.**
- `activate` refuses unless `vision_open(db) is True` (`launch_review.py:196`); unreadable is not
  open.
- `review_finished` marks a release `done` only when a batch call was reserved for it; otherwise it
  returns the release to `pending` with the reason.
- `close_if_due` closes as `UNUSED`, not `COMPLETED`, when every release has finished with CA$0
  committed. An `UNUSED` batch can be re-activated only within its **original** expiry. A
  `COMPLETED`, `EXPIRED`, `EXHAUSTED` or `REVOKED` batch still refuses.
- `run()` moves a release that is stuck in `queued`, whose job is DONE, DEAD or CANCELLED, back
  to `pending`, and re-enqueues it under an `:attempt` key.
- `POST /api/cc/launch-review/resume` sits behind the `/api/cc` gate (owner session, same-origin,
  CSRF HMAC, nonce and timestamp) plus `require_stepup("launch_review.resume")`. It accepts only
  an OPEN batch.
- The caps are unchanged, and they are still enforced by `grant_in` under the budget lock.
- The card shows `releases_reviewed`/`releases_total` and `calls_made`.

**N3 notes.**
- `release_recovery.superseded_live_listings` runs inside `ops.sentinel`, which runs hourly
  (`worker.py:830`).
- It opens or restates one non-halting P2 per active listing whose version is not the newest
  certified version. The remediation owner is "owner".
- It resolves the P2 when that listing is no longer active.
- Nothing writes to Etsy.

---

## 2. New findings

### R1: MEDIUM: the delivery-policy reading, which turns a blank policy into NOT_APPLICABLE, is accepted on the operator token

**Where:**
- `commerce/shop_observations.py:31`: `OWNER_ATTESTED_PAGES = {"messages", "legal_and_tax"}`.
  The new `delivery_policy` page (`:54`) is not in it.
- `commerce/estate_api.py:69-89`: the operator route refuses only `OWNER_ATTESTED_PAGES`.
- `runtime/etsy_ops.py:110-127`: `shop_check_context` reads the newest `delivery_policy`
  observation, whoever recorded it.
- `intel/etsy_surfaces.py:2257-2276, 2334-2341`: that observation turns a blank `policy_shipping`
  into `NOT_APPLICABLE_HERE`, which is in `SATISFIES`.
- `runtime/etsy_ops.py:1109`: an owner action closes when all of its checks are in `SATISFIES`.

**Scenario (reproduced on 8d520ed through the real routes):**
1. Send `POST /api/etsy/shop-observation` with only `Authorization: Bearer <operator token>` and
   this body: `{"page":"delivery_policy","complete":true,"observed_at":<now-5m>,
   "values":{"editable_delivery_box":false}}`. The response is **200**.
2. Run `assess_shop` with that context on a digital-only getShop body that has a blank
   `policy_shipping` and a non-empty `digital_sale_message`. It gives
   `policy_shipping_set: NOT_APPLICABLE`.
3. If payment, refunds and privacy are set, the next `etsy.shop_snapshot`:
   - closes `etsy_surface:policy_settings_paste`;
   - lets `etsy_first_sale_surfaces` (`launch/readiness.py:1616`) count the check as satisfied.

**Why it matters:** the operator credential is shared with automation, which is why F7 moved the
attesting pages behind the owner session. E2's own design says that "a dated `false` [from the
owner] is the evidence". On this route, the "owner's dated reading" can be written by anything
that holds the operator token. E5 put the phone card behind step-up, but the operator route was
left open.

**Why it is not HIGH:**
- It cannot publish, activate or spend.
- It needs a digital-only shop with `digital_sale_message` set.
- Etsy itself shows a fixed "Instant downloads" policy in that configuration.
- SHADOW has no listings.

**Fix:**
- Add `"delivery_policy"` to `OWNER_ATTESTED_PAGES`. The operator route then returns 403
  `OWNER_SESSION_REQUIRED`, and the step-up phone card is the only writer.
- Optionally, make `shop_check_context` ignore a `delivery_policy` reading whose `recorded_by` is
  not an owner session.
- Add a test, mirroring `test_the_operator_credential_cannot_attest_kyc_tax_or_the_inbox`, that
  includes `delivery_policy`.

### R2: LOW: the owner confirmations that now count as banner and payout evidence need no step-up

**Where:**
- `app/command_center/api.py:820-833`: `store_settings_confirm` has no `require_stepup`.
- These consumers are new in this diff:
  - `etsy_surfaces._owner_confirmation` (banner → PASS, which closes `info_and_appearance_setup`);
  - `runtime/etsy_ops.py:1412` (resolves the `LIVE_OWNER_FIELD_BLANK` banner incident);
  - `launch/readiness.payout_evidence` (`:228`: `payout_details` is one of the three legs of
    `payout` readiness).

**Scenario (reproduced):** I signed in, then expired the session's `stepup_until`.
- `POST /api/cc/etsy/shop-observation` → **403** step-up required. This is correct.
- `POST /api/cc/store/settings/banner/confirm` → **200**.
- `POST /api/cc/store/settings/payout_details/confirm` → **200**.
- With the operator token alone, the confirm route → **401** `NOT_AUTHENTICATED`. This is correct.

**Effect:** an owner session left open (no step-up, but valid CSRF and nonce) can produce the
evidence that closes a first-sale card and one leg of payout readiness. The route existed before
this diff, but before E1 and E-8 nothing consequential read it.

**Fix:**
- Add `auth.require_stepup(db, request, "store.owner_confirmed")` to `store_settings_confirm`.
- Set `requiresStepUp: true` on the Store-tab Confirm button (`static/js/views/store.js:80`).
- Add a route test with the step-up expired.

### R3: LOW: OA-F is closed by "merge" without evidence, even when its target card is already done

**Where:** `store_foundation/store_readiness.py:428, 480-489`.
- `_MERGED_INTO = {"OA-F": "etsy_surface:policy_settings_paste"}`.
- The condition is `_MERGED_INTO[oid] in all_keys`, where `all_keys` includes **done** rows.

**Scenario:**
1. `policy_settings_paste` closes on the four getShop policy fields. FAQ and cancellations are not
   getShop fields, so they are never evidenced there.
2. The next `sync_owner_actions` closes OA-F, "Policy Settings: privacy policy, **FAQ with
   licence**, cancellations", as "merged" into a card that is already closed.

The licence-FAQ ask, which carries the licence terms because `policy_additional` cannot be used,
then has no open card and no evidence. `test_store_cards_close_on_the_reading_and_duplicates_are_merged`
asserts this closure with no reading at all. It does so deliberately, but it confirms the gap.

**Fix:**
- Merge only into an **open** target (`_MERGED_INTO[oid] in open_rows`). Otherwise leave OA-F
  open, or keep the FAQ and cancellations parts as their own ask.
- Or extend `policy_settings_paste.evidence_required` to an owner FAQ reading.

### R4: LOW (N3 residual): only listings the company activated are checked

**Where:**
- `runtime/release_recovery.py:311`: the check selects `Listing.state == "active"`.
- `runtime/pipeline.py:2369`: `store.activate` is the only writer of `"active"`.
- `pipeline.py:2087`: publish leaves `"published"` or `"incomplete_on_etsy"`.

**Scenario:**
1. The company publishes a draft (state `published`).
2. The owner activates it by hand in Shop Manager.
3. A newer release is certified.

The database still says `published`, so no P2 is raised, which is exactly N3's case. Separately,
`:316` skips a product whose versions cannot be ordered (`newest is None`) without recording it.

**Exposure:** none in SHADOW.

**Fix:**
- Include every row with a non-empty `etsy_listing_id` whose state is not `withdrawn` or `draft`.
- Or read the live state, which `store.live_drift` and the listing reconcile already fetch.
- Record the skipped products whose versions cannot be ordered in the result.

### R5: INFO: one unorderable sibling version blocks every new certification of a product

- `newer_certified` (`release_recovery.py:91`) counts an unorderable version as newer.
- So once any certified version of a product is not a dotted run of integers, every new version
  of that product refuses with `older_than_newest` (probe d).
- `CIR.version` is not validated, but every current CIR uses `x.y.z`.
- This fails closed. The only signal is the `gate.certify_older_than_newest` audit row.

**Hardening:** validate `CIR.version` with `version_key` at compile time. Or raise an owner or
operator item when the refusal reason is that a version cannot be ordered.

### R6: INFO: test strength

- **The boot-tables regression test does not reproduce the defect.** It passes on b9137b5, because
  the test module imports `launch_review` at the top, which registers the tables before
  `create_all`. A subprocess test that never imports the module would reproduce it; my probe
  does exactly that.
- **`test_n1_the_display_readers_use_the_same_newest_release`** asserts behaviour for
  `newest_certified`. For the seven call sites it only checks that the source text contains
  `"newest_release("`. The behavioural N1 tests cover `enforce`, `_targeted_rebuild` and
  `chain_evidence`.
- **`test_w4_launch_review.py` monkeypatches `LR.vision_open = lambda db: True`** at module
  level, so every test in that file runs with the gate open. This is acceptable, because the N2
  test closes it explicitly and restores it in `finally`.

### R7: INFO: N2 API details

- `launch_review_resume` (`api.py:687-706`) does not catch `DuplicateJob`. `resume_key` is
  `count(jobs of JOB_TYPE) + 1`, so two concurrent resumes compute the same key and the second
  returns 500. Nothing is double-run.
- Re-activating an `UNUSED` batch inserts a **second** `LaunchReviewBatch` row with the same
  `batch_id`. `_batch` takes the newest by id, and `_committed`/`_today` sum by the `batch_id`
  string, so the caps hold. The N8 suggestion (a unique key, or an update in place) still applies.
- Resume does not re-check `vision_open`. A resume while the gate is closed returns releases to
  `pending` without spending. This is harmless.

### R8: INFO: card closures are one-way

- **Store cards:** `sync_owner_actions` closes OA-E on a fresh reading. A later reading in which
  either field is blank does not reopen it (`store_readiness.py:496` "already done").
- **Surface cards:** `handle_shop_snapshot` reopens a surface card only when a check reads
  **FAIL** (`etsy_ops.py:1112`). Since E1, a blank banner reads NO_EVIDENCE. If the banner is
  removed, or the owner's confirmation ages past 90 days, `info_and_appearance_setup` stays
  closed.
- A removed banner still surfaces as the `store.live_drift` P3, unless a confirmation younger
  than 90 days suppresses it.
- Neither case turns missing evidence into PASS: `etsy_first_sale_surfaces` still reads
  NO_EVIDENCE as not ready. Only the card's done flag lags.

### R9: INFO: E6 retry details

- `_is_rate_limited` (`etsy_ops.py:140-146`) also matches the text `429` inside any exception
  message. At worst this adds two extra reads (5 s and 20 s).
- `_get_shop_spaced` can block a worker thread for about 60 + 25 s.
- Both are bounded. `EtsyAuthNeedsOwner` and errors other than 429 are re-raised on the first
  attempt, as before.

### R10: INFO: records for the E3 rule change

- The removal of `policy_additional_unset` is described in code as owner-commissioned
  (LAUNCHPREP E3). I found no `DECISION_LOG.md` entry for it.
- LISTREADY.md:124 and :389 still say that the snapshot fails `policy_additional_unset`.
- The write-side restriction is intact:
  - `shop_package.SHOP_LOCATED_IN_EU = False`;
  - `etsy_constraints.policy_additional_eu_only`.
- The changed test (`test_etsy_surfaces.py:329`) replaces the old failure assertion with "not a
  readiness failure" **plus** a content assertion: a contradicting `policy_additional` is flagged
  by `policy_consistency`. Given the rule change, this is not a weakening, but the commission
  should be on record.

### R11: INFO: payout readiness does not read `identity_verified`

- `payout_evidence` (`launch/readiness.py:233-238`) sets `tax_recorded` from a FRESH
  `legal_and_tax` reading with a non-empty `tax_position`. It ignores `identity_verified`.
- In practice, getShop's `is_etsy_payments_onboarded` (also required) implies that Etsy's KYC is
  done.
- **Hardening:** also require `identity_verified is True`.

---

## 3. Storefront checks (E1–E7) and store cards: checklist

| item | missing or stale → PASS? | owner card closes without fresh evidence? | notes |
|---|---|---|---|
| E1 banner | **No**: blank → NO_EVIDENCE; PASS only on a non-blank field or a confirmation ≤ 90 days old with a server-set `confirmed_at` | No (only on PASS), but see R2 (no step-up) and R8 (one-way) | `live_drift` resolves the blank-banner P3 only on a fresh confirmation |
| E2 delivery N/A | **No**: needs all five (complete reading, fresh ≤ 90 d and not future-dated, `editable_delivery_box is False`, integer counts with active == digital, non-blank `digital_sale_message`); otherwise FAIL | **R1**: the reading can come from the operator token | |
| E3 `policy_additional_unset` removed | n/a; content still checked by `policy_consistency` | `policy_settings_paste` now closes on four checks | R10 |
| E4 per-check owner actions | No: `failing` = anything not in `SATISFIES` (NO_EVIDENCE included); `ready` still requires `not failing` | No: an unmapped check is named `shop_check:<key>`, never dropped | |
| E5 phone card | n/a | n/a | Posts to `/api/cc/etsy/shop-observation` with `requiresStepUp: true`; the server enforces step-up (verified: 403 when expired) |
| E6 spacing and 429 | n/a | n/a | R9 |
| E7 read-only policy rows | n/a | n/a | `owner_confirmable=False`, so `confirm` refuses them |
| OA-E (store card) | n/a | No: closes only on a getShop reading ≤ 7 days old showing both fields non-blank (tested: blank → stays open, 10-day-old → stays open) | R8 |
| OA-F (store card) | n/a | **Yes, by merge (R3)** | |
| Payout (E-8) | No: ready only when all three legs hold (fresh getShop `is_etsy_payments_onboarded is True`, a fresh `payout_details` confirmation, a FRESH legal_and_tax reading with a tax position); unreadable is not ready | n/a | R2, R11 |

## 4. Route authentication summary

| route | operator token alone | owner session without step-up | owner session with step-up and CSRF |
|---|---|---|---|
| `POST /api/etsy/shop-observation`, page `delivery_policy` | **200 (R1)** | n/a | n/a |
| `POST /api/etsy/shop-observation`, `messages` or `legal_and_tax` | 403 | n/a | n/a |
| `POST /api/cc/etsy/shop-observation` (any page) | 401 | 403 | 200 |
| `POST /api/cc/store/settings/{key}/confirm` | 401 | **200 (R2)** | 200 |
| `POST /api/cc/launch-review/activate` and `…/resume` | 401 | 403 (`require_stepup`) | 200 |

## 5. Weakened tests

None found that weakens a control.
- **`test_etsy_surfaces.py`: the E3 test.** Replaced in step with the commissioned rule change, and
  a content-contradiction assertion was added (R10).
- **`test_w4_launch_review.py`: `…ceiling_reverts_when_the_batch_completes`.** It now makes one
  real reserved call per release, as N2's new semantics require. It also asserts
  `releases_reviewed == releases_total`, which is stronger.
- **`test_w4_launch_review_card.py`:**
  - the step-up count went from 2 to 3 (the delivery card);
  - the new reason-function cases cover `vision_open` false or missing, and `unused`.
- **`test_w4_storefront_checks.py` (new):** this file covers:
  - stale and blank readings closing nothing;
  - NO_EVIDENCE without a confirmation;
  - FAIL without the delivery reading;
  - an unmapped check being named.

  It does not test the operator route (R1) or step-up on confirm (R2).

## 6. Tests run (nice 19)

| suite | 8d520ed | b9137b5 with 8d520ed's test file |
|---|---|---|
| test_w4_listready | 30/30 | 6 FAIL (5 N1 tests and the N3 test) |
| test_w4_launch_review | 18/18 | Aborts at import; with the `getattr` shim, 5 FAIL (the four N2 tests and the completion test) |
| test_w4_launch_review_card | 7/7 | 2 FAIL |
| test_w4_storefront_checks | 14/14 | 13 FAIL (new API) |
| test_etsy_surfaces | 53/53 | 1 FAIL (the E3 test) |
| test_w4_owner_observations | 3/3 | not re-run |
| test_v11_cc_views, test_v11_store_foundation, test_k8_shop_cx, test_incident_lifecycle, test_teardown, test_teardown_readiness, test_teardown_audits | all pass (14, 20, 17, 7, 12, 7, 21) | not re-run |
| test_compiler, test_reverse, test_twin | rc 0 | not re-run |

## 7. Records-only merge (1580053)

- 1580053 came in through b58e925, a merge of `origin/claude/final-candidate-b997efd`. Against its
  first parent, the merge changes 10 files.
- All of them are under:
  - `brambleloop/release/` (NOTES, RELEASE json, `suite_runs`);
  - `brambleloop/research/release_evidence/`.
- `git diff b58e925^1 b58e925 -- brambleloop/src brambleloop/tests` is empty.
- A pattern scan of the added lines for keys, tokens, private keys and database credentials found
  nothing.

## 8. Recommended order

1. **R1:** add `delivery_policy` to `OWNER_ATTESTED_PAGES`, and add the route test. Do this before
   the first-sale readiness or STAGING decision relies on it.
2. **R2:** add step-up to the store-settings confirm route.
3. **R3 and R4:** before LIMITED PRODUCTION.
4. **R5–R11:** hardening and records, at convenience.
