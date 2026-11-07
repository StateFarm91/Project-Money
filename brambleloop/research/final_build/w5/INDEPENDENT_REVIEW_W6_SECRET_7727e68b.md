# Independent delta review: `claude/w6-secret-leak-followup` @ 7727e68b

Reviewed 2026-11-07 (UTC).

**Scope**
- The diff reviewed is `git diff 340025ca 7727e68b`:
  - `ops/secret_leak.py`, +51/-? lines
  - `runtime/release.py`, a one-key change
  - the test, +85 lines
- I also read the whole of `brambleloop/src/brambleloop/ops/secret_leak.py` and the ops.health block at `runtime/release.py:7286-7304`.
- For context I read `incident_lifecycle.open_or_restate` and `resolve_signatures`, and `owner_queue.ensure`.

**How it was run**
- Worktree: `/home/user/bl-runs/wt-rev-secret3`, detached at 7727e68b. It is clean: nothing was committed or pushed.
- Only fake secrets assembled at runtime were used, and no value was printed.
- Scripts and outputs are in `/tmp/claude-0/-home-user-Project-Money/0aa334b9-5ba9-5fd2-9058-e50b4b8604ea/scratchpad/rev_secret_d2/`:
  - `repro.py` and its output `repro.out`
  - `mut.py` and its output `mut.out`
- I first used `scratchpad/rev3/`, but another agent was writing to the same path. I killed only my own processes and moved to the unique directory above. Results in `rev3/mut.out` are not mine.

## Verdict: DO NOT SHIP 7727e68b

Status of the four earlier findings:

| Finding | Status |
|---|---|
| N-M1 | Partly fixed |
| N-L1 | Fixed: M3 and fallback-on-clean are now killed |
| N-L2 | Fixed |
| N-L3 | Over-corrected: it introduces a new medium hole |

**What works:**
- For a `var:` subject, the rule now behaves correctly: a variable that still holds the value always reopens.
- Growth in count within one process reopens.

**What remains:**
- For a subject that no variable holds, the "no variable holds it, so it was rotated" guard is vacuous, because such a secret never had a variable.
- Guard counts restart at zero in each process.
- So after a restart, a re-leak of a resolved non-env value is silent until its count exceeds the highest count ever recorded.
- Separately, the fallback incident is closed by a CLEAN sweep in a new process, which drops an exposure that was never carded.

## Findings

### D-M1 (Medium, blocking): after a restart, or in another process, a re-leak of a resolved non-env secret is silently acknowledged

**Location:** `brambleloop/src/brambleloop/ops/secret_leak.py:163-170` and `:200-208`.

**Cause:**
- `_resolved_for_same_catch` compares the current process's guard count against the max count of any resolved row.
- No process identity is recorded, so these numbers come from different processes and cannot be compared.
- The extra guard `s["variable"] is None` is always true for exactly the subjects that reach this path. Those are values no variable holds: a provider response, a stored Etsy OAuth token, a request header.
- The comment's inference "(it was rotated)" (`:166`) is therefore false for these subjects.
- The commit message says "Re-logging a revoked value ... reopens". That holds only within one process.

**Reproduction** (`repro.py` A1-A3, `escalate(session, summary=..., env={})`):

| Case | Steps | Result |
|---|---|---|
| A1 | A GitHub token from a provider response, count 5. The owner resolves it as "false positive, not rotating". | Acknowledged. This is the intended behavior: the same process and the same count. |
| A2 | Simulated restart. The same value is logged again in the new process, with count 1, 3, then 5. | Each sweep is `ack=True` and nothing opens. It reopens only at count 6. |
| A2, continued | After a reopen and a second resolution, the threshold ratchets up to the new max. | Every later process gets that many free re-leaks. |
| A3 | Counts recorded by another process: the web process recorded 40. A process that sees the value for the first time has count 2. | `ack=True`. |

**Why it matters:**
- A fresh process logging the value means a code path is formatting it again. That is a new exposure event.
- When the owner's resolution was a "false positive" or "not rotating", nothing in the system ever re-raises it until the count crosses the historical max.

**Fix (small):**
- Stamp a per-process boot id into `detail` at `open_or_restate`. A `uuid4` taken at `log_secret_guard` install would do. The guard's `summary()` has no process identity today.
- Acknowledge only when the covering resolved row carries the current boot id and the count is `<=`.

**Test to add:** resolve, then call `G.GUARD.caught.clear()` to simulate a restart, log the value once, and sweep. It must reopen.

### D-M2 (Medium, blocking): `_close_escalation_failed` closes the fallback P1 while the exposure that triggered it is still unescalated

**Location:** `secret_leak.py:131-132` (the CLEAN path) and `:181` (the CAUGHT path); `:234-241`.

**Cause:**
- The fallback row is process-blind: it records no fingerprint and no boot id.
- The guard is monotonic within a process. So a CLEAN reading after a CAUGHT one can only come from a *different* process, and that is exactly the case where the old catch is lost.

**Reproduction** (`repro.py` E1-E2):

| Case | Steps | Result |
|---|---|---|
| E1 | `escalation_failed(s, "OperationalError")` runs, then a CLEAN sweep (a new process, for example the redeploy that ships the bug fix). | The open list goes `['escalation_failed']` -> `[]`, with `actions=0`. The caught secret has no incident and no card, and the fallback is resolved with "a later ops.health sweep escalated successfully". That is false. |
| E2 | The fallback is open for value X. A new process catches a different value Y and escalates it. | The fallback closes. Only Y's incident is open, and X is gone. |

**Realistic sequence:** escalation raises, Claude or the owner deploys a fix, the new process reads CLEAN, and the P1 auto-closes. This is the most likely path to recovery, and it is the one that silently loses the exposure.

**Fix:**
- Stamp the boot id on the fallback row.
- Close it only from a successful CAUGHT escalation in the same boot id.
- Never close it from CLEAN. Mutant M6, which removes the CLEAN close, survives, so removing it breaks no test.
- In another process, leave the fallback for the owner to close. Optionally, record the pattern names (which are not secret) on the fallback so the owner can act.

**Test to add:** fallback, then CLEAN, then assert the fallback is still open. Also: fallback, then a different-boot CAUGHT, then assert it is still open.

### D-L1 (Low): three guards are untested (mutants survive)

The suite is `tests/test_w6_secret_leak_escalate.py`, run alone, 9/9 at baseline (64 s).

| Mutant | Result |
|---|---|
| M1: drop `s["variable"] is None` | KILLED |
| M2: drop the count check | KILLED |
| M3: `all` -> `any` | KILLED |
| M4: `<=` -> `<` | KILLED |
| M5: no close on the CAUGHT path | KILLED |
| M6: no close on CLEAN | SURVIVED. This is the desired direction (see D-M2). |
| M7: close on UNKNOWN too | **SURVIVED**. An UNKNOWN or malformed reading would close the fail-closed fallback. No test covers it. |
| M8: drop the `resolved == True` filter in `_resolved_for_same_catch` | **SURVIVED**. Open rows' fingerprints would then count as acknowledgement. |
| M9: `max` -> last-row-wins in `covered` | **SURVIVED**. A later resolved row with a lower count would lower the threshold. This is benign, but the max rule is untested. |
| M10: fallback stores `str(exc)` instead of the type name | **SURVIVED**. The no-value property of the fallback is protected only by review. Add a test where `escalate` raises `RuntimeError(FAKE_KEY)` and then assert `_assert_absent`. |
| M11: fallback ungated on CLEAN | KILLED |

### D-L2 (Low): restate churn when two processes report different counts for an open incident

**Location:** `secret_leak.py:153-162`.

**Reproduction** (A4): with an open incident, alternate readings of 5 and 2 restate on every sweep: `[True, True, True, True]`.
- This applies only if more than one process runs `ops.health`. The module docstring says one does.
- After a restart it causes one restatement, with the stored count going *down*. The boot id from D-M1 fixes this too.

### D-I1 (Info): reopening a `var:` subject is bounded, not noisy forever

**Reproduction** (N1): the owner resolves 5 times while the variable still holds the value.
- Each resolution gives exactly one new incident row and one new card on the next sweep. The totals are 6 incidents and 6 actions, with 1 open.
- It never reopens per sweep without an owner action. This is correct behavior: the value is demonstrably unrotated.
- One drawback: the owner cannot close an accepted "false positive" on a `var:` subject without a restart.

### D-I2 (Info): no secret value leaks on any path (checked)

- The DB dump after a mixed var/non-var escalation plus a fallback contains neither fake value, in full or as its last 20 characters (L1).
- `_card`, the incident summary and detail, the fallback summary (type name only) and the `detail["secret_leak"]` job output carry names, patterns and fingerprints only.
- The test's `_assert_absent` checks the DB and the log in four tests.

### D-I3 (Info): carried over from the previous review, unchanged

- The `like("secret_leak:%")` pattern still lets `_` act as a wildcard (`:202`).
- Any resolved row counts as acknowledgement whatever its resolution text, including hygiene `close_duplicates`.
- `covered` is still recomputed once per subject.

## Tests run (one suite at a time, venv-integ4)

| Suite | Result |
|---|---|
| `tests/test_w6_secret_leak_escalate.py` @ 7727e68b | 9/9 OK |
| 11 mutants, each running the same single suite | 7 killed, 4 survived (M7, M8, M9, M10), plus M6, which survives in the desired direction |

## To flip to SHIP

1. **Fix D-M1:** add a per-process boot id to the incident detail, and acknowledge only within the same boot id. Add a restart test.
2. **Fix D-M2:** never close the fallback on CLEAN or from a different boot id. Add tests for both.
3. **Kill M7 and M10**, and optionally M8.
