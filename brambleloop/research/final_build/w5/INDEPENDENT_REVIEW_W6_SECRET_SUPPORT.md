# Independent review: W6 secret-leak escalation and support-defect incident

Reviewed 2026-11-07 (UTC). Merge-base for both branches: `7c42e706`. Each branch was checked out in a detached worktree:
`/home/user/bl-runs/wt-rev-secret` (1c4c9211) and `/home/user/bl-runs/wt-rev-support` (26bac0e9).
Mutants ran on separate copies (`/home/user/bl-runs/mut-secret`, `/home/user/bl-runs/mut-support`). No branch was modified, committed or pushed. No secret values were printed, and Railway and production were not touched.

Repro scripts are in `/tmp/claude-0/-home-user-Project-Money/0aa334b9-5ba9-5fd2-9058-e50b4b8604ea/scratchpad/rev/`: `repro_secret.py`, `repro_support.py`, `mut.py`, `mut_secret.json` and `mut_support.json`.

---

# Branch 1: `claude/w6-secret-leak-escalate` (P0-SECRET-LEAK-ESCALATE)

## Verdict: SHIP 1c4c9211

The branch does what its name says. Every 15 minutes, `ops.health` turns each secret the F-159 guard caught into one P1 incident and one owner rotation action:
- The action goes through `owner_queue.ensure`, so it is deduplicated and the before_flush guard applies.
- The subject is either the environment variable that holds the value, or `<pattern>:<fp>`.

I found no path that writes the secret value anywhere. The only things written are the pattern name, the 12-hex fingerprint, the logger name, counts and environment variable names:
- **DB:** incident `detail` and `summary`, and the owner-action text.
- **Job outputs, events and the Command Center:** the health job output holds only signatures and ids.
- **Logs:** the handler logs only `type(exc).__name__`.

The test proves this end to end. It dumps the SQLite file and the captured log and checks for both the full value and its last 20 characters. Mutant S1 confirmed that check catches a leak.

The findings below are robustness gaps, not leaks. They can be follow-ups.

### Findings

**S-M1 (Medium): an owner-resolved incident is reopened, with a new rotation card, on the very next sweep.**
- Location: `brambleloop/src/brambleloop/ops/secret_leak.py:144-163`.
- Cause: the skip-if-unchanged branch looks only for an *unresolved* incident. Once the owner resolves it, the next sweep falls through to `open_or_restate`. The process-local guard counter still holds the old catch, so this opens a fresh P1 and `ensure` inserts a new owner action.
- Who it hits: credentials whose rotation does not restart the process, such as the stored Etsy OAuth token, a provider-response token or a bearer token. A Railway variable change redeploys the service and resets the counter, so those credentials do not hit this.
- Repro (`repro_secret.py`): escalate, then mark the incident resolved and the action done, then escalate again with the same summary. The counts (incidents total/open, actions total/open) go from (1, 1, 1, 1) to (2, 1, 2, 1).
- This fails toward noise, not toward silence. The fix is to also skip when a *resolved* incident's fingerprints dict equals the current one.
- Mutant S7 survived, so no test covers the resolved case.

**S-M2 (Medium): a failure inside `escalate` is silently downgraded to `{"state": "UNKNOWN"}`.**
- Location: `brambleloop/src/brambleloop/runtime/release.py:7290-7295`.
- If `escalate` raises (repro: a malformed `count` raises `ValueError`), the health-sweep output records UNKNOWN. Nothing else happens: no incident, no owner action, no alarm.
- A caught secret is then never escalated while the failure persists. The pattern matches the sibling sub-sweeps, but for a P0 security path it should raise a fixed-signature `secret_leak:escalation_failed` incident.

**S-L1 (Low): any guard summary whose `status` is not exactly `"CAUGHT"` reads as CLEAN.**
- Location: `brambleloop/src/brambleloop/ops/secret_leak.py:127`.
- `escalate(None, summary={"status": "caught", "caught": [...]})` returns `CLEAN`. Today `summary()` is internal and well-formed. Deriving the status from `bool(summary["caught"])` would fail closed.

**S-L2 (Low): catches made in processes that never run `ops.health` are lost.**
- `scheduler_entry` and `worker_entry` install the guard, but escalation reads only the in-process counter of the process that runs the health job.
- This is correct for the documented single-process deployment, but it is a silent gap if a separate scheduler or worker process is ever split out. Persisting catches, or sweeping in each process, would close it.

**S-L3 (Low): concurrent sweeps can open two incidents.**
- `open_or_restate` does a select and then an insert, with no lock and no unique index on open `Incident.signature`. The owner-queue lock is taken only afterwards, inside `ensure`.
- The worker is single-threaded and the cadence is deduplicated, so this is theoretical today.

**S-I1 (Info):** fingerprints are 48 bits of SHA-256 over the full match. That is fine for high-entropy keys. For `db_url_password`, the hash covers the whole URL, so offline guessing needs the user and host as well. This is acceptable.

### Tests run (one at a time)

| Suite | Result |
|---|---|
| `tests/test_w6_secret_leak_escalate.py` | 4/4 OK (56 s) |
| `tests/test_w4_fm2_log_secret_guard.py` | 8/8 passed |
| `tests/test_health.py` | 35 OK, 4 FAIL |

The 4 `test_health.py` failures are all environmental: `starlette.testclient requires httpx2`, which is not installable here. They are console TestClient tests unrelated to this diff.

### Mutants (secret branch)

| Id | Mutation | Result |
|---|---|---|
| S1 | put the last 24 characters of the env value into incident detail | **KILLED** (the DB-dump check) |
| S2 | `_identify` always returns None | **KILLED** |
| S3 | remove the health-sweep hook | **KILLED** |
| S4 | `escalate` raises | **KILLED** (output assertions) |
| S5 | remove the "fingerprints unchanged, skip" branch | SURVIVED. Behaviourally equivalent: `ensure` and the signature dedup still hold |
| S6 | replace `owner_queue.ensure` with a raw `OwnerAction` insert | SURVIVED. Equivalent because the global `owner_queue_guard` before_flush merges duplicates |
| S7 | existing-incident lookup ignores `resolved` | SURVIVED. No test covers resolved incidents (see S-M1) |
| S8 | drop `detail.owner_action` | **KILLED** |

---

# Branch 2: `claude/w6-support-defect-incident` (P0-SUPPORT-DEFECT-INCIDENT)

## Verdict: DO NOT SHIP 26bac0e9

The plumbing is correct:
- One incident per slug@version:row.
- A per-release withholding through the existing `quality_reverify` kind, which blocks publish and not build.
- Idempotent re-verification jobs.
- No change for other products.
- No support free text reaches Learning. The incident detail and summary hold only slug, version, row number and counts, and the audit `detail=hotspot` is `{product, row, mentions}`.

However, the hold does not actually stop the affected release. It clears itself within one worker cycle, and the escalation is then suppressed permanently. The write order is also not fail-closed.

### Findings

**D-H1 (High): the hold is released by re-running validators that the release already passed, and the row is then never escalated again.**
- Locations:
  - `brambleloop/src/brambleloop/support/defects.py:145-170`, `on_reverified`.
  - `brambleloop/src/brambleloop/support/defects.py:105-107`, the `if seen: return` branch.
  - `brambleloop/src/brambleloop/runtime/quality_ops.py:217`.
- Why it clears: the escalation queues `cir.twin` and `cir.reverse` against the same stored, certified CIR. Both are deterministic and passed at certification, so they pass again. `on_reverified` then resolves the P1 ("re-verification passed") and lifts the publication hold. No human ever sees it and no root-cause step happens. Neither check is specific to row N.
- Why it stays suppressed: after that, `seen` is non-empty, so any number of further cases on that row and release are ignored forever. They only show up as `support.defect_candidate` audit rows.
- The branch's own test asserts this sequence. In `tests/test_w6_support_defect_incident.py:148-164`, the release is no longer withheld once the jobs run, and t4 shows it is never re-escalated.
- Repro (R1 in `repro_support.py`): 3 cases on row 3, then triage, then run the twin and reverse jobs. The result is incident `resolved=True`, `withheld=False`.
- Net effect: the release is held only between triage and the next validator poll.
- Fix direction: re-verification passing should *downgrade* the incident to "not reproduced by the compiler, needs review". The hold should be released by the owner, by a new version, or by a change to the CIR row. A resolved release+row should re-open when mentions grow past a new threshold.

**D-H2 (High): not fail-closed. The incident is committed before the hold and the jobs, so a transient failure leaves an open incident with no hold and no re-verification, permanently.**
- Location: `brambleloop/src/brambleloop/support/defects.py:96-131`.
- `open_or_restate` commits in its own session (lines 96-118). `withholding.record_reverification` (line 119) and `ctx.enqueue` (line 127) run afterwards. If either fails, the triage job fails. On the retry, `open_row` exists, so the code returns "already open" and the hold is never placed.
- Repro (R2): make `record_reverification` raise once for `support.defect:*`, run triage, restore it, then run triage again. The result is incident open, `withheld=False`, 0 re-verify jobs.
- Fix: place the hold first, or in one transaction. On "already open", re-assert the hold and the jobs, which are idempotent anyway.

**D-M1 (Medium): the target version is the all-time majority among citing cases, so a new release's defect is suppressed by an older release's resolved escalation.**
- Location: `brambleloop/src/brambleloop/support/defects.py:60-77`, specifically `versions.most_common(1)` at line 72.
- `mine_cases` counts mentions per (slug, row) across all versions. `_release_for` then picks the most common version.
- Repro (R1, second half): after 1.2.1 is escalated and auto-resolved, add certified version 9.9.9 and send 3 cases citing it on row 3. Triage finds `Counter` = {1.2.1: 3, 9.9.9: 3}. The tie goes to 1.2.1, which hits `seen`, so nothing happens: 9.9.9 is `withheld=False` with no incident.
- Related: if the case `version` names a release that is not stored, `record_reverification` returns `recorded: False`. The incident still opens, the jobs target a release that does not exist, and the certified release is never held. The code does not retry because the incident is already "open".

**D-M2 (Medium): one buyer can trigger a P1 and a publication hold.**
- Location: `brambleloop/src/brambleloop/support/department.py:301-306`. This counting predates the branch, but this branch is the first to make it consequential.
- Mentions are counted per case, not per distinct `customer_ref`.
- Repro (R3): `customer_ref="same-buyer"` sends 3 messages, which gives a P1 incident and `withheld=True`. Spec §10 says "repeated questions", which suggests distinct customers. It is a cheap denial of service on publication once support intake is live.

**D-L1 (Low):** `escalate`'s select-then-insert has no lock or unique constraint, so concurrent triage jobs could open duplicate incidents. The single-threaded worker and cadence deduplication make this theoretical today.

**D-L2 (Low):** `release_resolved` (`defects.py:173-200`) walks every resolved support incident on every triage run, one session per row. The cost grows without bound.

**D-I1 (Info):** withholding blocks future publish only. It does not deactivate an already-live listing. That is acceptable in SHADOW, but "stops affected releases" is publish-only.

**D-I2 (Info): UNKNOWN is never treated as a pass.**
- `_run_check` returns before `on_reverified` when `ok is None`.
- `on_reverified` requires `ok is True`.
- A check that raises maps to `ok=False`.
- The tests do not hold these guards, though (D1 and D2 below).

### Tests run (one at a time)

| Suite | Result |
|---|---|
| `tests/test_w6_support_defect_incident.py` | 3/3 OK (58 s) |
| `tests/test_opus2_reverify_withhold.py` | 0 failed |
| `tests/test_w4_fm2_surface_reverify.py` | 8/8 passed |
| `tests/test_fb4_ops.py` | 1 failing |

The single `test_fb4_ops.py` failure (`test_the_owner_intake_route_requires_the_operator_credential`) is environmental: `starlette.testclient requires httpx2`.

### Mutants (support branch)

| Id | Mutation | Result |
|---|---|---|
| D1 | a *failing* check also clears the support hold (drop `ok is not True`) | **SURVIVED** |
| D2 | one passing check suffices (drop the twin+reverse requirement) | **SURVIVED** |
| D3 | re-escalate an already-resolved release+row | **KILLED** |
| D4 | no withholding placed | **KILLED** |
| D5 | a pass on *another version* clears this version's hold (prefix without version) | **SURVIVED** |
| D6 | no `release_resolved` call in triage | **KILLED** |
| D7 | `release_resolved` ignores the "still open" check | **SURVIVED** |
| D8 | no re-verification jobs enqueued | **KILLED** |
| D9 | THRESHOLD 3 → 4 | **KILLED** |
| D10 | `halts_publication=True`, which halts all products | **KILLED** |

Four of the ten mutants survive, and all four relax the hold-clearing guards. The tests exercise only the happy-path pass. They never run a failing check, a single check, another version, or an open-plus-resolved mix.

---

## Cross-branch note
Both branches append a line at the same point of `brambleloop/scripts/suite_final_segment.txt`, so merging the second one will hit a trivial conflict. Their `release.py` hunks are in different functions and do not conflict.
