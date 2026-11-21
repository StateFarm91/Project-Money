# MISSION-CONTROL-2 — review request

Branch `eng/mission-control-2`, cut from `claude/batch19-fixers` 8204c93. NOT merged, NOT deployed; production
unchanged. Decisions: `D-MC2-APPROVE-ALL`, `D-MC2-HOME` (DECISION_LOG; decision index regenerated).

## What was asked

The owner said Mission Control (`/cc/`) "is a mess" and asked for an "approve all button":
1. a clean one-screen home with the 6 P0 conditions (live verdicts) and today's counts;
2. a searchable, server-side paginated inventory of ALL products (stage, proof, holds, next action);
3. an "Approve all eligible" owner button behind the EXISTING step-up, never approving child-safety holds,
   physical-sample attestations, spend above ceilings or public-publishing authority, every approval audited.

## What was built

### 1. Home = Mission control (`GET /api/cc/mission`, `app/command_center/mission.py`, `views/_mission.js`)
- Six conditions, each PASS / FAIL / UNKNOWN with its reason and the reader it came from. **The repository names no
  fixed list of six P0 conditions**, so they are defined in `D-MC2-HOME`, each from an existing reader:

  | # | Condition | Reader |
  |---|---|---|
  | 1 | Production is running and healthy | `p0_board.running` (health sweep, 45 min freshness) |
  | 2 | All mandatory shops scanned on time | `p0_board.shops` |
  | 3 | Products are advancing | `p0_board.development` + `ops.daily_ledger` (advances today or yesterday) |
  | 4 | Certified releases with PDFs and images | `p0_board.releases` + `p0_board.assets` |
  | 5 | Etsy drafts exist | `p0_board.etsy` |
  | 6 | Publication safety | `app.verify_checks.publication_checks` (the `/api/verify` checks) |

- An unreadable reader is UNKNOWN, never a pass (`test_a_failing_reader_is_unknown_never_a_pass`).
- Today's counts (UTC day so far) from `daily_ledger.ledger`: scans, products started, products advanced (sum of
  `advanced:*`), certified, PDFs (US + UK), images, listing packages, Etsy drafts, lessons, failures. UNKNOWN is never 0.
- The owner queue in one line: how many rows "Approve all eligible" would approve now, how many it never approves.
- The previous Home content is kept, folded under one "Full overview" `<details>` (tests pin its strings).

### 2. Inventory (`GET /api/cc/catalogue`, existing ENG-CATALOGUE)
- **Already built before this branch:** server-side SQL pagination (`page`, `page_size` ≤ 200), search (`q` on slug and
  title), filters (stage, state, category, family, owner, held), totals over every row. It is not rebuilt.
- **Added:** a `proof` field per row (`catalogue.proof`): certificate, US PDF, UK PDF, gallery, listing package, Etsy
  read-back, each present or listed as `missing`. Derived only from the row's existing `evidence`.
- Home links to it ("All products").

### 3. Approve all eligible (`GET`/`POST /api/cc/approve-all`, `app/command_center/approve_all.py`)
- **Eligible:** an open or parked OwnerAction row that `authority.standing_internal.classify` (the hourly sweep's
  table) marks ROUTINE_INTERNAL or AUTO_CLOSE, and that the key guard does not catch.
- **Auth:** owner session (passphrase + TOTP login), CSRF + nonce (the existing `/api/cc` gate), a FRESH step-up
  (`auth.require_stepup`, action `owner_queue.approve_all`) and the preview's `expected_digest`. A changed eligible set
  is refused 409 and moves nothing. Each row is re-read and re-judged inside the writing session. `execute` also refuses
  any actor that is not `owner:`.
- **Never approved, listed separately with the reason** (`approve_all.EXCLUDED`): `child_safety`, `physical_sample`,
  `spend_above_ceiling` (incl. paid ads / subscriptions), `public_publishing` (publication, activation, phase,
  standing policy, live listings), `owner_only` (grants, OAuth consent, KYC / legal / banking, external-policy
  attestation, unclassified kinds), `not_an_owner_action_row` (executor gates, grant cards, policy reviews, release).
- **Defence in depth:** the key guard excludes a classifier-routine row whose key names a child-safety, physical,
  spend or publication subject (`portfolio.rework:baby-safety-rattle` is ROUTINE to the classifier and excluded).
- **Audit:** per row an `owner_action.lifecycle` row (actor `owner:cc:<session>`) and an `owner_action.approve_all` row
  (batch, class, rule, from/to, `step_up: true`, session); per press one `owner_queue.approve_all` row with counts, ids
  and excluded tallies. Never written as the standing authority. Nothing deleted, signed, sealed, published, spent or
  messaged. The client button uses the existing `guardedAction` (confirm + step-up dialog).

## Tests

New suite `tests/test_mission_control2.py` (13 tests, real routes, real passphrase + TOTP sessions):
- every new endpoint refuses without an owner session (and with the operator token);
- the POST needs CSRF + nonce; the step-up is enforced (expired step-up → 403 `STEP_UP_REQUIRED`; passphrase without
  TOTP and a wrong TOTP do not step up; a fresh step-up then succeeds); a stale digest → 409, nothing moves;
- exclusions honoured for all four named categories plus the other genuine classes and the guarded row; a second press
  approves nothing; every approval audited as the owner; re-judging at the write skips a row that became excluded;
- the guard and judge are pinned against mutations (`retire`/`toy` false positives, every genuine KIND_RULE refused);
- the home's six verdicts, today's counts and the queue line; an empty company passes nothing it cannot prove;
- the inventory pages and searches over 130 rows server-side; `proof` names what exists and what is missing.

The TOTP harness clears the spent-step markers before each login/step-up (the equivalent of waiting for the next 30 s
step); the real passphrase + code verification runs every time.

Run (`JOBS=4 SUITE_REGISTRY=0 SUITES="…" bash run_tests.sh`, py3.11 lockfile venv):

| Run | Suites | Result |
|---|---|---|
| `20261121T003401Z-2412` (dirty tree, before the vacuity fix) | 22: the new suite, test_eng_approvals, test_vacuity and every CC suite that pins the touched files | 356 passing, 4 suites failing |
| `20261121T004014Z-6296` (after the fix) | test_mission_control2, test_eng_approvals, test_vacuity, test_v11_pwa_static, test_w3_decision_index | 145 passing, **0 failing** |

Of the 4 failing suites in the first run:
- `test_vacuity` was this branch's: a loop over `ROUTINE + AUTO` without a non-emptiness assertion. Fixed; it passes in the second run.
- `test_eng_demand_supply` (amigurumi "round" refused at intake), `test_first_listing_doors` and `test_w4_launchfix`
  (gallery "N of the 7 required listing photos", D-OWNER-GALLERY-COMPLETE) are **pre-existing**. They fail identically on
  the untouched base 8204c93, run in a separate worktree (57 passing, 3 failing). Not touched here.

Browser proof against the real backend (`tests/fixtures/cc_mock/real_backend_bridge.py`, seeded with 3 routine and 5
excluded rows, Chromium at 390 px):
- Home shows the Mission control card. With an empty database the verdicts read FAIL/UNKNOWN, never PASS, and the
  counts read Unknown.
- Approvals shows "Approve all eligible (3)" and "Never approved in bulk (13)", with a reason per category. The
  confirm dialog names the exclusions.
- One press approved 3. The button then read "(0)" and was disabled. No page errors.

## Other changes
- `sw.js` → `cc-shell-v46`, `_mission.js` added to SHELL; `format.js` maps PASS/FAIL to pill colours.
- **Bundle:** 399,958 bytes against the 400,000 test ceiling (42 bytes headroom). To fit, without touching behaviour:
  the JSDoc typedef block in `api.js` (the contract doc is the source) and the per-version changelog lines in `sw.js`
  (its header says history is in git) were removed, and section-divider dash padding was shortened. **Open risk:** the
  next client change will exceed the ceiling; the bundle needs a real reduction (e.g. a CSS/JS minify step) soon.

## Not verified / open
- Nothing ran against production; no production row was read. The real number of eligible cards is unmeasured (the
  hourly sweep already supersedes routine kinds, so on production the eligible count may be small; the genuine
  exceptions are what remain, and those are deliberately never bulk-approved).
- The browser proof used the bridge against a seeded test database, not production data.
- The "six P0 conditions" are this branch's definition (D-MC2-HOME), not an owner-supplied list.
