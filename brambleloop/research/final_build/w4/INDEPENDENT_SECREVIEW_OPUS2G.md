# Independent security and correctness review OPUS2G: second operator's pushes, 2026-11-01

Reviewer: independent (claude/w5-SECREVIEW-OPUS2G). Read-only on every branch under review; this
report is the only file written. Nothing was deployed, published, messaged or spent; Railway and
production were not touched. A throwaway local PostgreSQL 16 cluster (`/tmp/pgdata`, port 55432)
was used only to check DDL and the Postgres paths.

`git fetch origin` first; heads reviewed (all matched the brief):

| # | PR | Branch | Head | Diffed against |
|---|---|---|---|---|
| 1 | #5 | opus2/p0-listing-package | e93b16ed | b42f4245 |
| 2 | #6 | opus2/p1-owner-queue-races | 61d76d9f + cc8f2b4f | 007f5d1c |
| 3 | #7 | opus2/p1-culture-sweep-timeout | ec97a79e | d230e8fd (its base) |
| 4 | #8 | opus2/p0-family-membership | 0f862a1b | d230e8fd (its base) |

## Verdicts

| # | Subject | Verdict | Highest finding |
|---|---|---|---|
| 1 | PR #5 listing package (EF2-4, EF2-5) | **ACCEPT** | LOW |
| 2 | PR #6 owner-queue races (EF2-6, EF2-8, B-5, EF2-7) | **CHANGES_REQUIRED** | MED (dedupe step loses an owner deferral and lowers a stated ceiling to CA$0.00) |
| 3 | PR #7 culture sweep timeout | **CHANGES_REQUIRED** | MED (the claimed cause of the dead letter does not reproduce; other UNCERTAIN failures still escape) |
| 4 | PR #8 family membership | **CHANGES_REQUIRED** | MED (`amplify` raises KeyError for any culture family that reaches the order floor) |

None of the four weakens the paid-call anti-double-spend protocol, and none queues a paid job.

---

## 1. PR #5: opus2/p0-listing-package e93b16ed — ACCEPT

**EF2-4 (READY → BLOCKED → READY never re-asked): fixed at the root.** `already` now counts a
row for the current fingerprint only if it is open (including parked) or the owner closed it
(SATISFIED / WITHDRAWN). A row the job SUPERSEDED itself counts as absent.

**EF2-5 (legacy key orphaned): fixed.** The query adds `requirement_key == action_key` (the exact
unfingerprinted key) next to the `LIKE action_key:%` match, and the stale loop supersedes it.

Sequence probe on e93b16ed (`/tmp/rvtools/probe5.py`, real certified release fixture). Each step
shows (state, review_requested, review_withdrawn):

| Step | R | B | R | R | B | R | R |
|---|---|---|---|---|---|---|---|
| requested / withdrawn | T/F | F/T | **T**/F | F/F | F/T | **T**/F | F/F |

Final rows: superseded, superseded, open. Exactly one open request. The owner is re-asked
exactly once after each block. Other cases:
- Owner SATISFIED, then B, then R: **not** re-asked (correct).
- Owner WITHDRAWN: not re-asked (the PR's test).

Nothing publishes, uploads, messages or spends. `record` writes only:
- an OperatingReading;
- a local `ArtifactStore` file (filesystem root);
- an OwnerAction with `max_cost_cad=0.0`, stated (a review costs nothing).

### Findings

- **L5-1 LOW: an owner's deferral is overridden by a transient block.**
  - Repro: record R. The owner parks it (`owner_action.defer` → PARKED). Record B: the parked row
    is SUPERSEDED by the job. Record R: a new OPEN request is raised.
  - Observed: `parked: R -> False | B -> True | R -> True`.
  - Effect: the owner parked the request, and it comes back active after any transient block.
    The block-time supersede predates this PR, but EF2-4 is what makes it re-ask.
  - Suggested fix: treat a PARKED row for the current fingerprint as the owner's answer (do not
    supersede it on BLOCKED, or re-park on READY).
- **L5-2 INFO: a legacy-key request the owner SATISFIED is ignored.** The owner is asked again
  under the fingerprinted key. This is defensible because the legacy row names no content, but
  the handoff should say so.
- **L5-3 INFO (pre-existing):** `LIKE` treats `_` in `listing_package:` and in slugs as a
  wildcard. It can only over-match keys of the same shape, so it is harmless today.

### Mutations (`/tmp/rvtools/mut.py`, each reverted; worktree clean afterwards)

| ID | Mutation | Result |
|---|---|---|
| M5a | `already` back to "any row with the key" | **killed**: ef24 |
| M5b | legacy `== action_key` match removed | PENDING (rerun in progress at commit time) |
| M5c | WITHDRAWN dropped from the owner-closed set | **killed**: ef24 |
| M5d | open rows no longer count (`not r.done` dropped) | **killed**: `test_a_ready_package_asks_for_one_review…` |
| M5e | SATISFIED dropped from the owner-closed set | **killed**: `test_review_opus2f_a2_…never_asked_again` |

---

## 2. PR #6: opus2/p1-owner-queue-races cc8f2b4f — CHANGES_REQUIRED

### What holds

**EF2-6: fixed in the guard.** `_merge_cost` restates the figure and its basis together:
- UNKNOWN on either side stays UNKNOWN;
- between two stated figures, the higher wins;
- a newcomer that states no ceiling is ignored. An unflushed `OwnerAction()` carries `None`, not
  the 0.0 column default, so it is correctly not treated as "stated 0".

The ORM merge and `ensure` cannot produce a stated CA$0.00 from UNKNOWN. Probes P3/P4 confirm:
UNKNOWN then stated 0.0 stays UNKNOWN.

**EF2-8: fixed.** The validator reads `self.state` before stamping, so `history.deleted` holds the
real prior lifecycle, and a reverted reopen restores state, state_at and state_reason.

**B-5 index.** Checked on both engines:
- **SQLite:** `CREATE UNIQUE INDEX uq_owner_actions_open_requirement ON owner_actions (requirement_key) WHERE done = 0 AND requirement_key != ''`.
  It refuses a Core insert and a Core reopen; closed and keyless rows are free.
- **PostgreSQL 16 (real server):** `create_all` produced
  `CREATE UNIQUE INDEX … USING btree (requirement_key) WHERE ((done = false) AND (requirement_key <> ''::text))`,
  so the DDL is valid. A second ORM add merged (one open row). A Core insert raised
  `IntegrityError`.
- **Migrate path on Postgres:** with the index dropped and a duplicate inserted,
  `migrate.apply` → `DEFERRED: 1 conflicting row group(s)`; then `close_duplicates` → one closed;
  then `apply` → `index … created`.

**EF2-7:** `owner_queue.ensure` returns the persistent row.

### Findings

#### D-1 MED: the dedupe step can lose an owner decision and produce a stated CA$0.00 ceiling

`close_duplicates` keeps the highest-id `done=False` row and supersedes the rest, without looking
at state or cost. Two problems follow:

1. **PARKED counts as `done=False`.** An older row the owner deferred is superseded, and a newer
   re-raised OPEN row survives. The owner's deferral is lost and the item returns to the active
   queue.
2. **The ceiling is not merged.** A duplicate holding UNKNOWN or CA$50 is closed in favour of a
   newer row holding stated CA$0.00. This is exactly the EF2-6 invariant the guard now enforces,
   broken by the migration path.

Repro (`/tmp/rvtools/probe6.py` P2, SQLite with the index dropped):

```
K: #1 parked, UNKNOWN, "deferred by the owner"   #2 open, stated 0.0
C: #3 open, stated 50.0                           #4 open, stated 0.0
close_duplicates -> closed #1 (kept #2), closed #3 (kept #4)
K kept #2: open, stated 0.0     <- owner's deferral gone; UNKNOWN became stated CA$0.00
C kept #4: open, stated 0.0     <- CA$50 ceiling lowered to CA$0.00
```

Fix:
- Pick the keeper deterministically by lifecycle: a PARKED row the owner set outranks an OPEN
  one. Alternatively, carry the owner's parked state onto the keeper.
- Merge cost with `owner_queue_guard._merge_cost` across the group before closing.
- Write an AuditLog row per closed duplicate. The script currently writes none, unlike
  `owner_queue.transition`.

#### D-2 MED: EF2-7 is fixed only as a new API; the existing owner-decision caller still loses the decision

No production caller uses `ensure`. `app/command_center/approvals.py::_record_acceptance_ruling`
still does `s.add(OwnerAction(...)); s.flush(); owner_queue.transition(s, row, SATISFIED, …)`.
If an open row exists under `decision.api_vision_equivalence`:
- the guard merges the newcomer onto it and expunges `row`;
- the transition then edits a detached copy;
- the owner's ruling is not stored, and the open row stays open with its text restated;
- the response still reports success with the open row's id.

Repro (P5, generic key "RULE"): returned id 2, stored `(2, 'open', False, …, 'ruling')`.

It fails closed (the gate stays shut), but the owner is told the ruling was recorded. No code
path creates an open row under that key today. The guard docstring's claim "no current writer
does" is therefore true only by accident.

Fix: switch `_record_acceptance_ruling` to `ensure(...)` and then `transition`. Better, make the
guard refuse (raise) rather than silently merge when a caller later edits the expunged copy.

#### D-3 LOW: a legitimate close-plus-reopen in one flush now raises

- Repro (P1): in one session, close the newer open row for key X and `transition` the older,
  satisfied row for X back to OPEN.
- The guard allows it: the closing row is in `leaving`.
- The unit of work emits UPDATEs in primary-key order, so the older row's `done=0` runs first.
  - SQLite: `UNIQUE constraint failed`.
  - PostgreSQL: `UniqueViolation`.
- Fail-closed, and the transaction rolls back. `store_readiness` (the only reopen path) reopens
  only when no open row exists for that key, so this is latent.
- Fix: in `before_flush`, flush the closes first; or document the restriction.

#### D-4 LOW: the EF2-6 test does not pin "never lower"

`test_review_opus2ef2_ef26_…` restates 10 and then 80, so "always take the newcomer" (M6a) still
ends at 80. M6a is caught only by the EF2-7 test. Fix: add a 50 → 10 → assert 50 step.

#### D-5 INFO: a deferred index is only a log line and a `changes` entry

While duplicates exist in production, B-5 protection is absent and nothing in `/api/verify`
says so. Consider surfacing `owner_queue_dedupe.conflicts()` as a verify check.

### Mutations (separate worktree `/tmp/rv/pr6m`, reverted, clean)

| ID | Mutation | Result |
|---|---|---|
| M6a | the merge always takes the newcomer's ceiling | killed **only** by ef27 (survives ef26, see D-4) |
| M6b | UNKNOWN sticky only if the old side is UNKNOWN | **killed**: ef26 |
| M6c | `_merge_cost` call removed from the guard | **killed**: ef26 |
| M6d | lifecycle restore on a reverted reopen removed | **killed**: ef28 (`closed_unclassified`) |
| M6e | index made non-unique | **killed**: b5 + race-control test |
| M6f | migrate no longer defers over duplicates | **killed**: b5 migrate test (IntegrityError) |
| M6g | dedupe keeps the oldest row | **killed**: b5 migrate test |
| M6h | `ensure` returns the detached copy | **killed**: ef27 |
| M6i | `ensure` overwrites the ceiling | **killed**: ef27 |
| M6j | SQLite partial predicate dropped (full unique index) | **killed**: 6 tests |

---

## 3. PR #7: opus2/p1-culture-sweep-timeout ec97a79e — CHANGES_REQUIRED

### What holds

The new `except TimeoutError` branch in `culture/classify.py`:
- does not resend;
- releases the reservation with `actual_cad=estimate`;
- writes one ledger row at the estimate (`billing: unknown_counted_at_estimate`, never zero),
  carrying `paid_calls.ledger_note()`.

`gateway/paid_calls.py` and `gateway/anthropic.py` are untouched:
- `_classify_failure` still returns UNCERTAIN for a timeout;
- the guard still writes UNCERTAIN, opens the P1 incident and re-raises;
- a later attempt still gets `PaidCallUnresolved`.

No double count: a later attempt meeting the UNCERTAIN row is refused, and `classify` returns
"nothing filed" without a second ledger row. Only PENDING orphans are billed by the guard.
**F-307/F-339 are not weakened.**

End-to-end through the real worker and the real `culture.sweep` handler (`/tmp/rvtools/e2e7.py`):
- only the network was stubbed: `AnthropicProvider._send` raises; `feeds.discover` and
  `feeds.sweep` are stubbed;
- on ec97a79e a read timeout gives `attempt 1: status=done`;
- one call was sent;
- one cost row was written at CA$0.01343 (`unknown_counted_at_estimate`);
- the reservation was released;
- the paid-call outcome is UNCERTAIN;
- same result on SQLite and PostgreSQL 16.

### Findings

#### C-1 MED: the fix's causal claim does not reproduce; the production dead letter is not shown fixed

The same end-to-end harness on the base d230e8fd **and on the production commit ee35a493** shows
the escaped `TimeoutError` costs one retry, not the night:

```
attempt 1: status=failed  err=TimeoutError: The read operation timed out
attempt 2: status=done    (classify catches PaidCallUnresolved -- a PermanentError -- and files nothing)
```

This was reproduced on SQLite and on a real PostgreSQL 16. The PR's own third test makes the same
point: `classify` already turned `PaidCallUnresolved` into "nothing filed" before this PR.

Production job 41979 failed attempts 2 **and** 3 with `PaidCallUnresolved`, and requeued job
34246 failed all three attempts the same way. So something on the production path let
`PaidCallUnresolved` escape the handler, and this PR does not identify or touch it.

`classify` is the only paid call in `handle_culture_sweep`; no other culture, seasonal or
engine module makes one. So the escaping exception, or the logged "error class", needs to be
re-read from the job rows (`jobs.last_error` for 41979) before this is called fixed.

The PR improves attempt 1 (no wasted retry, reservation released, spend counted). It cannot be
credited with clearing `no_unexpected_dead_letters_in_24h`. Its tests call
`classify(provider=fake)` directly and never run the worker. Add a worker-level regression in the
shape of `e2e7.py` once the real escaping path is known.

#### C-2 MED: other UNCERTAIN failures still escape, and their UNKNOWN spend is never recorded

`_send` raises raw (not wrapped):
- `ValueError` from `json.loads` on a truncated or unreadable 200;
- `ConnectionResetError` or `http.client.IncompleteRead` during `response.read()`.

The guard classifies all of these UNCERTAIN, but `classify` catches only `TimeoutError`.

e2e7 on ec97a79e with `badjson` and with `reset`:
- attempt 1 fails;
- **no cost row is written**;
- the reservation is left unreleased (`(0.01343, False)`) to expire;
- attempt 2 then completes.

That is UNKNOWN spend recorded as nothing, the very thing the PR fixes for timeouts. Fix: handle
by outcome, not exception type, i.e. any exception `_classify_failure` calls UNCERTAIN. For
example, catch `Exception` after the Permanent/Transient clause, or have the guard raise a typed
`PaidCallUncertain` that keeps the original as `__cause__`.

#### C-3 LOW: the PR's tests bypass the guard

The fake provider's `complete` raises directly, so `_guarded` and `_classify_failure` never run.
M7e (timeout classified DECLINED, i.e. re-sendable) passes the PR's suite. It is caught only by
the existing `test_w3_spend_paid_calls` and `test_w4_close5_vision_timeout`. Fake `_send`
instead, as `test_w3_spend_paid_calls` does.

### Mutations (pr7 worktree, reverted, clean)

| ID | Mutation | Result |
|---|---|---|
| M7a | timeout branch removed | **killed**: 2 tests |
| M7b | unknown spend recorded as 0.0 | **killed** |
| M7c | reservation not released | **killed** |
| M7d | call re-sent once inside the timeout branch | **killed** (calls == 1) |
| M7e | `_classify_failure`: TimeoutError → DECLINED | survives the PR's suite; **killed** by `test_w3_spend_paid_calls` and `test_w4_close5_vision_timeout` |

---

## 4. PR #8: opus2/p0-family-membership 0f862a1b — CHANGES_REQUIRED

### Ownership

- **Files:** 0f862a1b touches `creative/family_engine.py`, `commerce/cross_sell.py`,
  `creative/children.py`, a test and COORDINATION.json. Neither `claude/w5-INVENTORY` (5e72bce8)
  nor `claude/w5-CONCEPT` (40b2d9d9) changes any of these files relative to its merge base.
- **Callers:** neither branch (nor `claude/w5-INTEG1`) calls `family_of`. No code overlap.
- **Area:** W-CONCEPT owns "`creative/` concept path". This PR reads `culture_concepts` but does
  not generate concepts. It is adjacent, not duplicate.
- **Process (F-4, LOW):** P0-FAMILY-MEMBERSHIP is not one of the UNOWNED P0 clusters in
  BRANCH_OWNERSHIP.md. No claim line and no handoff document exist; only a COORDINATION entry.
  The integrator should confirm the claim. PRs #6, #7 and #8 all edit COORDINATION.json, so
  expect records-only conflicts.

### Findings

#### F-1 MED: `amplify` crashes with KeyError for any culture family at the order floor

`_culture_next_members` returns `{"concept": …}`, but `amplify` reads `nxt["seed"]`
(family_engine.py:285).

Repro (`/tmp/rvtools/probe8.py`): two certified products of signal `sig-aurora`, one unmade
concept, orders 6 (≥ `AMPLIFY_MIN_ORDERS` = 5):

```
next_members: [{'concept': 'aurora-ws-ornament', ...}]
amplify RAISED KeyError 'seed'   (family_engine.py:285)   queued: []
```

`handle_family_engine` then fails. The day's family reading is lost, and so is amplification for
**every** family after it in the loop, pool families included. It is latent only because nothing
has orders yet.

Do not just rename the key. `radar.score` takes a radar POOL seed slug, so it would be handed a
culture concept slug. The route for a culture member is the PR's own
"culture concept -> creative intake -> cir.draft". Keep culture families out of the `radar.score`
branch (park as `needs_member_route`) until a CA$0 route exists. Add a test that runs `amplify`
on a culture family with orders.

#### F-2 LOW: the two new call sites are untested

Removing `db` from `cross_sell.graph`'s `family_of` call (M8e) or `children.architecture`'s (M8f)
passes the PR's suite and `test_w4_c3` / `test_w4_children`.

#### F-3 LOW (Product Truth): buyer-facing "related" edges now follow a news signal

`cross_sell.graph` lists `related` (a buyer-facing edge) for certified products in the same
family. Two products translated from one culture signal now count as "one visual idea sold as
a set" with `bundle_ready: True`, but nothing checks that they share a palette or motif.

It is a declared record, not an inference, so it does not fabricate. But a "related"/"set" claim
to a buyer needs evidence that the translations share a visual identity. Either keep culture
families internal-only (`planned`) until a visual-identity check passes, or record that check.

**No paid job queued:** `family_report` is read-only and `amplify` crashes before `enqueue`
(F-1). The pool path is unchanged.

### Mutations (separate worktree `/tmp/rv/pr8m`, reverted, clean)

| ID | Mutation | Result |
|---|---|---|
| M8a | culture lookup disabled | **killed** |
| M8b | rejected or withdrawn concepts counted as next members | **killed** |
| M8c | blank `signal_key` accepted as a family | **killed** |
| M8d | `family_report` does not pass `db` | **killed** (KeyError) |
| M8e | `cross_sell` does not pass `db` | **survives** (F-2) |
| M8f | `children` does not pass `db` | **survives** (F-2) |
| M8g | pool family no longer takes precedence | **killed** |

---

## Test table

Run one at a time from `brambleloop/` as `PYTHONPATH=src:tests python tests/<f>.py`; the full
`run_tests.sh` was not run. "OK" counts the test-function OK lines.

| Subject | Suite | Result |
|---|---|---|
| #5 | test_opus2_listing_package | 13/13 OK, exit 0 |
| #5 | test_vacuity | 8 OK, exit 0 |
| #5 | test_w4_fmbatch1_retention_guard | 5 OK, exit 0 |
| #6 | test_opus2_owner_queue_races | 12 OK, exit 0 |
| #6 | test_vacuity | 8 OK, exit 0 |
| #6 | test_w4_fmbatch1_retention_guard | 5 OK, exit 0 |
| #6 | test_w3_k7_owner_queue | 10 OK, exit 0 |
| #6 | test_w4_owner_queue_race | 3 OK, exit 0 |
| #6 | test_w4_auditfix_migrate | 2 OK, exit 0 |
| #6 | test_w4_owner_actions | 6 OK, exit 0 |
| #6 | test_deploy | PENDING (running at commit time) |
| #7 | test_opus2_culture_sweep_timeout | 3 OK, exit 0 |
| #7 | test_vacuity | 8 OK, exit 0 |
| #7 | test_w4_fmbatch1_retention_guard | 5 OK, exit 0 |
| #7 | test_culture | 26 OK, exit 0 |
| #7 | test_culture_feed | 24 OK, exit 0 |
| #7 | test_w3_spend_paid_calls | 8 OK, exit 0 |
| #7 | test_w4_close5_vision_timeout | 4 OK, exit 0 |
| #7 | test_w3_spend_hygiene | 6 OK, exit 0 |
| #8 | test_opus2_family_membership | 2 OK, exit 0 |
| #8 | test_vacuity | 8 OK, exit 0 |
| #8 | test_w4_fmbatch1_retention_guard | 5 OK, exit 0 |
| #8 | test_w4_c3 | 4 OK, exit 0 |
| #8 | test_w4_children | 6 OK, exit 0 |
| #8 | test_w4_intelrec_amplify | 11 OK, exit 0 |
| #8 | test_collections | 12 OK, exit 0 |
| #8 | test_w4_intelrec_c06 | 3 OK, exit 0 |
| #8 | test_w4_departments | 19 OK, exit 0 |

## Probe scripts

The scripts live in the reviewer's scratch directory `/tmp/rvtools`. They are not committed, and
each is described above:
- `probe5.py`: listing-package sequences;
- `probe6.py`, `probe6pg.py`: DDL, swap, dedupe, cost and EF2-7 probes on SQLite and Postgres;
- `e2e7.py`, `e2e7pg.py`: the worker-level `culture.sweep` with a faked transport, run on the
  base, production ee35a493 and the fix, for the modes `timeout`, `badjson` and `reset`;
- `probe8.py`: a culture family at the order floor through `amplify`.
