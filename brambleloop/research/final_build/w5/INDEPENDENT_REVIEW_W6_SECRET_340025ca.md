# Independent delta review: `claude/w6-secret-leak-followup` @ 340025ca

Reviewed 2026-11-07 (UTC).

**Scope**
- The diff reviewed is `git diff 1c4c9211 340025ca`: `ops/secret_leak.py` +60, `runtime/release.py` +9, and the test +62.
- I also read the whole of `brambleloop/src/brambleloop/ops/secret_leak.py` and the ops.health block in `runtime/release.py:7286-7304`.

**How it was run**
- Worktree: `/home/user/bl-runs/wt-rev-secret2`, detached at 340025ca. Nothing was committed or pushed.
- No secret values were printed. Only fake, runtime-assembled keys were used.
- Repro and mutant scripts are in `/tmp/claude-0/-home-user-Project-Money/0aa334b9-5ba9-5fd2-9058-e50b4b8604ea/scratchpad/rev2/`:
  - `repro.py`, run as `python repro.py <worktree>/brambleloop`.
  - `mut.py`, run with the mutant names as arguments. It mutates a throwaway copy, which has since been removed.

## Verdict: DO NOT SHIP 340025ca

Status of the three earlier findings:
- **ESCALATION_FAILED fallback (S-M2):** sound. It cannot leak a value, cannot raise out of ops.health, and does not duplicate rows.
- **Explicit-CLEAN rule (S-L1):** correct.
- **"Acknowledged" rule (S-M1):** over-corrected. The earlier failure produced noise; this one produces permanent silence:
  - The rule ignores counts and process identity.
  - It treats any resolved `secret_leak:*` row, under any signature and with any resolution text, as permanent acknowledgement of that fingerprint.
  - As a result, a fresh process whose environment still holds the exact value the owner marked "rotated" escalates nothing, forever.
  - On a P0 security path, that is a regression relative to 1c4c9211, where this case was noisy but visible.
  - The earlier review's suggested fix was to skip when a resolved incident's fingerprints **dict** (counts included) is equal. The commit implemented a key-subset check over all history instead.

## Findings

### N-M1 (Medium, blocking): an owner-resolved fingerprint is suppressed permanently, including after restart and when the value is demonstrably still in use

**Location:** `brambleloop/src/brambleloop/ops/secret_leak.py:161-168` and `:185-199`.

**Cause:** `_resolved_for_same_catch` returns `set(fingerprints) <= covered`, where `covered` is the union of fingerprint keys from every resolved `secret_leak:%` incident:
- Guard counts are discarded, so the rule cannot tell "the same stale catch, still in this process's counter" from "caught again".
- There is no process or start-up marker.
- The resolution reason is not considered. "False positive", "will rotate later" and a hygiene `close_duplicates` closure all count as acknowledgement.

**Reproduction** (`repro.py` R1-R3, with `escalate(session, summary=..., env=...)` on a fresh SQLite database):

| Case | Steps | Result |
|---|---|---|
| R1 | Catch the key with count 1 while `ANTHROPIC_API_KEY` holds it. Resolve the incident and mark the action done. The same value is then logged 50 times (count 1 -> 50). | `(incidents, open, actions, open) = (1, 0, 1, 0)` and `acknowledged=['secret_leak:var:ANTHROPIC_API_KEY']`. Nothing is opened or restated. |
| R2 | Simulate a new process: guard reset, count 1, and the environment **still holds the resolved value**. | `(1, 0, 1, 0)`, acknowledged. |
| R3 | The owner resolves the incident with "false positive, not rotating". The value leaks again via a provider response, with no environment variable holding it. | `(1, 0, 1, 0)`, acknowledged. |

**Why R2 matters:**
- A Railway variable change redeploys the service.
- So a process started after the resolution that still holds the old value in its environment is direct evidence that rotation did not happen.
- The code now hides exactly that evidence, and it does so indefinitely because resolved rows never age out.

**Fix (small):**
- Record a per-process identity in `detail` at open or restate time, for example the guard's start-up time or a boot UUID, plus the per-fingerprint counts.
- Acknowledge only when the resolved row carries the **current** process identity and every current count is `<=` the resolved count.
- Optionally, never acknowledge a `var:` subject whose variable still holds the fingerprint in a process started after `resolved_at`.

The new test, `test_an_owner_resolved_catch_is_not_reopened_but_a_new_value_is`, does not exercise a re-leak of the same value or a restart.

### N-L1 (Low): the subset check is untested at its boundary, and part of the rule is mutation-equivalent

Mutants were run against `tests/test_w6_secret_leak_escalate.py` only:

| Mutant | Result |
|---|---|
| M1: `_resolved_for_same_catch` returns True | KILLED |
| M2: returns False | KILLED |
| M3: `<=` replaced by "any overlap" | **SURVIVED** |
| M4: drop the `resolved == True` filter | **SURVIVED** |
| M5: same-signature only | KILLED (the cross-signature, rotated-value case is covered) |
| M10: drop the `if not fingerprints` guard | SURVIVED. Equivalent: `_subjects` always gives at least one fingerprint |

- **M3:** a multi-fingerprint subject where one fingerprint is new and one is resolved would be silently acknowledged under this mutant, and no test catches it. Add a test with a `var:` subject that holds two fingerprints.
- **M4:** this mutant would also count *open* rows' fingerprints. It is mostly masked by the earlier `existing` branch.

### N-L2 (Low): UNKNOWN is surfaced nowhere

**Locations:** `secret_leak.py:131`; `runtime/release.py:7295`.
- `detail["secret_leak"]` is written into the ops.health job output only. `grep` finds no reader in the Command Center, in alerting or in any incident. An `escalate` UNKNOWN therefore opens nothing and alerts no one.
- In production the branch is unreachable anyway: `log_secret_guard.summary()` (`log_secret_guard.py:149`) only ever emits `CAUGHT` or `CLEAN`. The fix is defensive only. It is correct, and the test kills M6.
- The two UNKNOWN shapes use different keys: `escalate` returns `{"status": "UNKNOWN"}`, while the except path returns `{"state": "UNKNOWN"}`. A future reader would have to check both.
- **Suggestion:** if UNKNOWN should matter, open a P2 `secret_leak:guard_unknown` incident in the same way as ESCALATION_FAILED.

### N-L3 (Low): the ESCALATION_FAILED incident is never closed and is not actionable as worded

**Location:** `secret_leak.py:202-220`.

**Repro** (`repro.py` R7): call `escalation_failed` twice, then let `escalate` succeed. The open signatures are `['secret_leak:escalation_failed', 'secret_leak:var:ANTHROPIC_API_KEY']`.
- The fallback row is correctly deduplicated: one row, restated.
- But it stays open after recovery with no closer, and it has no owner-queue card.
- Its summary tells the owner to "rotate the credentials named in the log guard". The guard's catches are process-local and are not shown to the owner anywhere, so the owner cannot follow that instruction.
- **Suggestion:** resolve the row when a later `escalate` succeeds, using `reconcile`. Either name the patterns, which are not secret, or point to the health job output.

### N-I1 (Info): fallback path robustness (checked, OK)

**Location:** `runtime/release.py:7294-7304`.
- **No value can leak:** only `type(exc).__name__` and `type(exc2).__name__` are written.
  - M9, which stores `str(exc)`, SURVIVED. The no-value property of the fallback is therefore protected by code review, not by a test.
  - A test that raises an exception whose message contains the fake key would kill M9.
- **It cannot raise out of ops.health:** the inner `try/except Exception` covers both the `summary()` call and the database session. `detail["secret_leak"]` is always a dict when `["fallback_error"]` is assigned.
- **Partial writes do not survive:** `Database.session` rolls back on exception (`core/db.py:181-190`), so partial writes from the failed `escalate` are discarded. The fallback uses a new session.
- **No duplicate rows:** `open_or_restate` has a fixed signature. The test confirms one row over two sweeps.
- **The status check is ungated:** mutant M8, which calls the fallback even when the guard is CLEAN, SURVIVED. There is no test that a raising `escalate` on a clean guard opens nothing.
- **If `guard.summary()` itself is what raised:** the fallback raises too, and only UNKNOWN plus `fallback_error` is recorded. No incident opens. This is acceptable because nothing is known to be caught.
- **Benign fail-closed noise:** if every catch was owner-acknowledged and `escalate` then starts raising, a new P1 opens.

### N-I2 (Info): the O(n) scan is unbounded but does not matter

**Location:** `secret_leak.py:195-198`.
- Each acknowledged subject, on every sweep, loads every resolved `secret_leak:%` row and its JSON `detail`.
- Rows grow only with owner resolutions, which means a handful.
- Measured (`repro.py` R8): 5,000 resolved rows take 0.034 s per call on SQLite.
- **Optional:** compute `covered` once per `escalate` call instead of once per subject.

### N-I3 (Info): LIKE wildcard and other edge inputs (all fine or theoretical)

- **LIKE wildcard** (`secret_leak.py:197`): `SIGNATURE + "%"` contains `_`, which LIKE treats as a wildcard. A resolved `secretXleak:foo` row with a matching fingerprint suppresses a real catch (R6). No such family exists today. The module's sibling `incident_lifecycle.reconcile` already guards against this with `startswith`.
- **Other edge inputs:**
  - **Fingerprint collision:** at 48 bits this is negligible. Patterns are not compared, so a collision across pattern classes would also suppress, but this is theoretical.
  - **Empty fingerprint set:** returns False and opens the incident.
  - **The ESCALATION_FAILED row:** it has no `fingerprints`, so it covers nothing (R5).
  - **Rows with null `detail` or null `fingerprints`:** handled.

## Tests run (one at a time)

| Suite | Result |
|---|---|
| `tests/test_w6_secret_leak_escalate.py` @ 340025ca | 7/7 OK (60 s) |

Mutants (each ran the same single suite):

| Mutant | Result |
|---|---|
| M1 | KILLED |
| M2 | KILLED |
| M3 | SURVIVED |
| M4 | SURVIVED |
| M5 | KILLED |
| M6 | KILLED |
| M7 | KILLED |
| M8 | SURVIVED |
| M9 | SURVIVED |
| M10 | SURVIVED (equivalent) |

## To flip to SHIP

1. **Fix N-M1:** acknowledge only within the same process and only when no count has grown. Add tests for the following:
   - The same value is re-logged after resolution: it restates or reopens.
   - Simulated restart with the value still in the environment: it reopens.
2. **Add tests that kill M3 and M8.** A test that kills M9 is also advisable.
3. **Optional:** auto-close ESCALATION_FAILED on recovery (N-L3), and use an exact-prefix match (N-I3).
