# Independent review: `origin/claude/w6-secret-leak-followup` @ 17f63074

Reviewed 2026-11-07 (UTC). The diff reviewed is the cumulative change `git diff 1c4c9211 17f63074`, 4 files, +130/-3:
- `ops/secret_leak.py`
- the ops.health block in `runtime/release.py:7286-7304`
- `REMEDIATION["secret_leak"]` in `ops/incident_lifecycle.py:189-193`
- `tests/test_w6_secret_leak_escalate.py`

For context I also read `open_or_restate`, `resolve_signatures`, `actionability` and `snapshot`, `owner_queue.ensure`, `log_secret_guard.summary` and the guard's filter, `Database.session`, and every `.resolved = True` site. No generic closer can close a `secret_leak:*` row.

**How it was run**
- Worktree: `/home/user/bl-runs/wt-rev-secret4`, detached at 17f63074. It was left clean: nothing was committed or pushed.
- Only fake secrets, assembled at runtime, were used.
- Scripts and outputs are in `/tmp/claude-0/-home-user-Project-Money/0aa334b9-5ba9-5fd2-9058-e50b4b8604ea/scratchpad/rev_secret4/`: `mut.py` with `mut1.out` and `mut2.out`, and `repro.py` with `repro.out`.

| Suite | Result |
|---|---|
| `tests/test_w6_secret_leak_escalate.py` | 8/8, 64 s |
| `tests/test_w4_owner_incidents.py` (nearby) | 6/6 |
| `tests/test_w4_fm2_log_secret_guard.py` (nearby) | 8/8 |

## Verdict: SHIP 17f63074

The acknowledgement rule is gone. A caught secret always ends in an open, carded incident or in the P1 fallback, and nothing in this change hides or auto-closes either one. The two blocking findings from the d2 review (D-M1 and D-M2) are resolved by construction:
- There is no ack, so there is no cross-process acknowledgement.
- The fallback has no closer at all.

The findings below are all Low or Info. None of them hides an exposure.

## The questions you asked

1. **Is any exposure hidden now? No.**
   - A resolved row is never consulted: `secret_leak.py:149-150` selects only open rows, so a resolved catch re-opens on the next sweep, in this process or a new one.
   - The only branch that skips work (`:151-160`) runs only when an open incident with identical fingerprints already exists.
   - A new process's count (1) differs from the stored count, so it restates. That is loud, not silent.
   - I found no generic auto-closer that matches `secret_leak:`.
   - There is one caveat about how an open incident is presented: see L2.
2. **Is the re-open noise bounded by the rotation's redeploy? Partly.**
   - The noise is one new incident row and one new owner action per owner resolution. It does not grow per sweep: after a re-open, the row stays open and is skipped.
   - It stops when the process restarts. A Railway-variable rotation does restart it.
   - The claim is false for subjects whose rotation does not redeploy: see L1.
3. **Can the fallback duplicate rows, leak a value, or raise out of ops.health?**
   - **Duplicate rows:** no. `open_or_restate` keeps one open row per signature, and `close_duplicates` folds the rows two concurrent sweeps could race into.
   - **Leak a value:** no. Only `type(exc).__name__` is stored. The mutant that stores `str(exc)` is killed.
   - **Raise out of ops.health:** no. R4 makes both `escalate` and `escalation_failed` raise, and the job still finishes DONE with `{'status': 'UNKNOWN', 'error': 'RuntimeError', 'fallback_error': 'KeyError'}`. However, no test covers this guard (L3).
   - A `BaseException` is out of scope, as it is everywhere in the sweep.
4. **Is UNKNOWN presented as clean? Not by this change.**
   - Only `status == "CLEAN"` reads as clean.
   - The failure dict now uses `status`, the same key `escalate` returns.
   - No consumer reads `detail["secret_leak"]`, so the change from `state` to `status` breaks nothing.
   - One case predates this change (Info I1): a process that never installed the guard reports `CLEAN` with `records_scanned: 0`.
5. **Do the tests protect each guard?** Yes for the important guards: 8 of 10 mutants are killed. The table follows.

| Mutant | Result | Killed by |
|---|---|---|
| M1: UNKNOWN reads as CLEAN | KILLED | `only_an_explicit_clean_status_reads_clean` |
| M2: fallback not gated on CAUGHT | KILLED | `failed_escalation_with_a_clean_guard_opens_nothing` |
| M3: fallback stores `str(exc)` | KILLED | `failed_escalation_of_a_caught_secret...` |
| M4: failure dict key back to `state` | KILLED | `...clean_guard_opens_nothing` |
| M5: remove the fallback's inner `except` | **SURVIVED** | none (see L3) |
| M6: remove `REMEDIATION["secret_leak"]` | KILLED | `failed_escalation_of_a_caught_secret...` (needs_owner_path) |
| M7: auto-close the fallback on a successful escalation | KILLED | `failed_escalation_of_a_caught_secret...` (fail-3) |
| M8: re-add an ack rule (skip when a resolved row exists) | KILLED | `resolved_catch_reopens...` |
| M9: fallback severity P2 | KILLED | `failed_escalation_of_a_caught_secret...` |
| M10: drop `value_stored: False` from the fallback | SURVIVED | none. Cosmetic: the flag is only a label. |

## Findings

### L1 (Low): the claim that re-opens stop at "the rotation's redeploy" is false for subjects whose rotation does not redeploy

**Location:** `incident_lifecycle.py:190-193`, and the test docstring `test_w6_secret_leak_escalate.py:163-166`.

**Cause:**
- The Etsy OAuth token is rotated by re-authorising the shop (`secret_leak.py:46`). That changes no Railway variable, so nothing redeploys.
- The same applies to a provider-response value no variable holds, and to a false positive.
- In each of these cases the process keeps the catch, so every owner resolution re-opens the incident, plus a fresh owner action, until some unrelated deploy or restart.

**Repro:** `repro.py` R1 runs `escalate(summary=etsy_oauth_token)`, then resolves, four times. The incident row count goes `[1, 2, 3, 4]`. The noise is bounded per resolution, so it is not a flood, but the stated end condition is wrong.

**Fix:**
- Change the REMEDIATION text to "...which the next restart or redeploy clears (restart the service in Railway if the rotation did not redeploy)".
- Optionally, add a per-subject note on the card for `etsy_oauth_token`.

### L2 (Low, predates this change): a held catch goes UNCONFIRMED after 48 h ("it may no longer hold")

**Location:** `secret_leak.py:151-160`.

**Cause:**
- The no-change branch `continue`s without calling `_restate`, so `detail.last_seen` never moves.
- `actionability` (`incident_lifecycle.py:337-344`) then labels the incident UNCONFIRMED: "it may no longer hold, and it is not called current". That is wrong for an exposure this process still holds.
- The fallback row behaves the same way once escalation recovers.
- The incident still stays open and listed, so it is mislabelled, not hidden.

**Repro:** `repro.py` R2 runs two identical escalations, then `actionability(now=+49h)`, which returns `UNCONFIRMED`.

**Fix:** in the skip branch, move only `last_seen` forward. Do not bump `report_count`, to keep the no-churn property.

### L3 (Low): the guard that keeps the fallback from raising out of ops.health is untested

**Location:** `release.py:7297-7304`.

**Detail:**
- The guard works: R4 shows the job finishes DONE with `fallback_error: 'KeyError'`.
- Mutant M5, which narrows the `except` to `ZeroDivisionError`, survives the suite.

**Fix:** add a test in which `escalate` and `escalation_failed` both raise, then assert the job finishes DONE with `fallback_error` set.

### L4 (Low): the fallback tells the owner to "Read the ops.health job output (secret_leak) ... for the guard's pattern/fingerprint lines", but that output has neither

**Location:** `secret_leak.py:187-197`.

**Detail:**
- `repro.py` R3 shows the output keys are only `['error', 'escalation', 'opened', 'restated', 'status']`.
- The service log shows only `***<fingerprint>`, with no pattern, and only for as long as Railway retains the log.
- Pattern names and fingerprints are not secret: the main path already stores them.

**Fix:** copy `[(pattern, fingerprint, logger, count)]` from `guard.summary()["caught"]` into the fallback's `detail` and output. Wrap that read in its own try, so that the fallback still opens if it fails.

### I1 (Info, predates this change): a process without the guard installed reads CLEAN

**Location:** `log_secret_guard.py:149`.

**Detail:**
- `summary()` returns `CLEAN` with `records_scanned: 0` when nothing is attached.
- `escalate` passes that through as CLEAN.
- Production installs the guard at start-up, so this is a theoretical gap.

**Fix (optional):** treat `records_scanned == 0`, or a guard that is not installed, as UNKNOWN.

### I2 (Info): REMEDIATION now takes precedence over `detail.owner_action` for the per-credential incidents

**Location:** `incident_lifecycle.py:333-335`.

**Detail:**
- The per-credential incidents' `remediation_path` used to be the specific `secret_leak_rotation:var:X` key. It is now the generic sentence, which says "the rotation card names the exact steps".
- `owner_action` is still in `detail`, and the readiness hold-open (`release.py:9257-9268`) still uses it, so nothing breaks.
- The sentence is also slightly wrong for the fallback, which has no card.
