# Independent delta review: W6 support-defect incident, 05961fd0

Reviewed 2026-11-07 (UTC). Scope: `git diff 26bac0e9 05961fd0`. I read all of `support/defects.py` and its callers: `runtime/release.py:2608-2621`, `runtime/quality_ops.py:191-229` and `publish/withholding.py`.
- Worktree: `/home/user/bl-runs/wt-rev-support2` (detached at 05961fd0). Nothing was committed or pushed, and the mutated file was restored (`git status` is clean).
- Repro and mutant scripts: `/tmp/claude-0/-home-user-Project-Money/0aa334b9-5ba9-5fd2-9058-e50b4b8604ea/scratchpad/rev2/repro.py` and `/tmp/claude-0/-home-user-Project-Money/0aa334b9-5ba9-5fd2-9058-e50b4b8604ea/scratchpad/rev2/mut.py`. Run both from `brambleloop/`.

## Verdict: DO NOT SHIP 05961fd0

All four claimed fixes are real, and each one is protected by a test: every one of 8 guard mutants was killed. But the HIGH fix swapped a self-clearing hold for a hold that only the code path can clear:
- The running system has no door to resolve a `support.defect:*` incident.
- It has no owner action, and no remediation owner is declared.

So a held release stays withheld from publication permanently, with no owner surface. The new distinct-buyer and current-version logic also counts buyers and mentions across all versions, so a **single** buyer on the current (for example, the corrected) release holds it as soon as older-version cases exist. Combined with the first problem, that hold is also permanent.

## Claimed fixes: are they real?

| Earlier finding | Fixed? | Evidence |
|---|---|---|
| D-H1: hold self-clears on a re-run of passed checks | **Yes.** `on_reverified` (defects.py:167-194) now only records `passed_checks` and `reverification` evidence and never resolves or clears. | Test 1, lines 154-171. Mutant M5 (restore the clear) is KILLED. |
| D-H2: not fail-closed | **Yes, by self-heal.** An open incident now falls through to re-assert the hold and the jobs on every triage (defects.py:116-151). | `test_a_failure_before_the_hold_is_repaired...`. M4 (return early on open) and M8 (hold only when new) are both KILLED. |
| D-M1: target is the majority version | **Yes.** The currently certified version is preferred when any citing case names it (defects.py:82-84). | `test_the_hold_targets_the_current...`. M3 is KILLED. |
| D-M2: one buyer escalates | **Partly.** Distinct `customer_ref` is enforced (defects.py:79, 106-109), but it is counted across versions (see N-2). | `test_one_buyer...`. M1 and M2 are KILLED. |

## Findings

### N-1 (HIGH): the hold can now never clear in the running system. It is a deadlock with no owner surface.
- **What clears the hold.** The only release path is `release_resolved` (defects.py:197-222), which needs the incident marked `resolved`.
- **What can mark it resolved.** Nothing in `src/` resolves a `support.defect:*` incident:
  - `grep -rn "support.defect" src/` hits only defects.py, release.py:2610-2620 and quality_ops.py:213-217.
  - The Command Center approvals list only `incident.acknowledge`, which "does not resolve it" (`app/command_center/approvals.py:36`).
  - No `OwnerAction` is created (`owner_queue.ensure` is never called).
  - `incident_lifecycle.REMEDIATION` (ops/incident_lifecycle.py:165-) has no `support.defect` family, and the incident `detail` carries no `owner_action`.
- **What the surfaces report.** `actionability()` reports `remediation_owner: None, needs_owner_path: true`, and `ops.truth` lists it under `needs_owner_path`. The test can resolve the incident only by calling `incident_lifecycle.resolve_signatures` directly (test file lines 181-186). The docstring's "owner / quality director" (defects.py:31, 136) names a decision door that does not exist.
- **Consequence.** Once three buyers cite a row, `release_gates.for_publish` refuses that release forever. That includes cases where the compiler proves there is no defect (both re-verifications pass and the incident says "does not reproduce"). The only escape is to certify a new version.
- **Aggravating factor.** The open incident reads `UNCONFIRMED` ("may no longer hold, it is not called current") after 48 h, while the hold is still being enforced. `last_seen` is refreshed only when `mentions` changes (defects.py:117-119), even though triage re-asserts the hold every run.
- **Repro.** `repro.py` R3 prints `UNCONFIRMED owner: None needs_owner_path: True ; still held: True`, both before and after another triage. Statically, there is no route or handler that resolves the incident.
- **Fix.**
  - Add a `support.defect` row to `REMEDIATION`.
  - Have `escalate` raise a deduplicated owner/quality decision through `owner_queue.ensure`, with these options:
    - "not a defect (compiler does not reproduce)": resolve the incident and release the hold;
    - "confirmed": keep the hold and fix in a new version.
  - Add a Command Center action that resolves exactly this incident family.
  - Refresh `last_seen` on each re-assertion.

### N-2 (MED; HIGH in combination with N-1): buyers and mentions are counted across versions, so one buyer on the current release holds it.
- **Location.** defects.py:76-87. `citing` takes every case on the product that cites the row, whatever its version, and `buyers` is the distinct refs across all of them. `mine_cases` mentions are also cross-version (support/department.py:300-306). The version chosen is then "current if any citing case names it".
- **Effect.** Three buyers report row 3 on 1.2.0, and the fix ships as 1.2.1. The first 1.2.1 buyer who mentions row 3, even with "row 3 works now", gets 1.2.1 withheld. Per N-1, it cannot be released.
- **The new test enshrines this.** `test_the_hold_targets_the_current...` (test lines 247-257) holds the current release on 2 buyers.
- **Repro (`repro.py` R1).** Three buyers cite row 3 on 0.9.0, then one buyer cites row 3 on 1.2.1. The result is `current held True`, with incidents `[...0.9.0:row3, ...1.2.1:row3]`.
- **Fix.** Count distinct buyers whose case version equals the chosen version, plus cases with no version, and require at least THRESHOLD of them.

### N-3 (LOW): an incident opens against a version that is not stored, and nothing is held.
- **Location.** defects.py:84 and 140-143. When no citing case names the current version, the majority version is chosen, and it may not be stored. `record_reverification` then returns `recorded: False`, but the P1 stays open permanently.
- **Repro.** R1, first line: incident `...0.9.0:row3` is opened and `current held False`.
- This is the "related" case from D-M1 in the earlier review. It is still unaddressed.

### N-4 (LOW): small churn when mentions change.
- **Answer to the question.** No churn on an idle re-assertion: the problem text is identical, `record` sees `changed=False`, and the `at` timestamp is stable. But the problem text embeds `mentions` (defects.py:142), so each new case rewrites `reverify_failed` and resets `withholding.quality_reverify.at`. The original hold time is lost from the certificate, although it is still in `incident.detail.held_at`.
- **Repro.** R2 prints `at unchanged on idle triage: True ; at changed on new mention: True`.
- **Fix.** Use a constant problem string that names the incident signature.

### N-5 (INFO): no real race between `release_resolved` and re-assertion.
- `escalate` returns early for a resolved signature, and `release_resolved` runs after the escalations in the same triage (release.py:2615-2620).
- Suppose the owner resolves between `escalate`'s open check and its hold write. The hold is re-placed, then cleared by the same triage's `release_resolved`. At worst, a concurrent triage leaves it for one cycle.
- `release_resolved` skips any signature that is still open (defects.py:209-214). The earlier D-L1 (no unique constraint on concurrent opens) and D-L2 (`release_resolved` scans every resolved incident, every run) still stand.

### N-6 (INFO): when versions are absent, the distinct-buyer count is correct.
- When no citing case has a version, `versions` is empty, so the release falls back to the newest certified release, and `buyers` counts the distinct non-empty `customer_ref`s of all citing cases. That is correct.
- `SupportCase.customer_ref` is a non-null string (core/models.py:981). Cases with an empty ref are not counted, which fails toward not escalating.

## Mutants (test_w6_support_defect_incident.py, one at a time)

| Id | Mutation | Result |
|---|---|---|
| M1 | drop the distinct-buyer guard | KILLED (one_buyer) |
| M2 | count cases instead of buyers | KILLED (one_buyer) |
| M3 | go back to the majority version | KILLED (targets_current) |
| M4 | return early when an incident is open (no re-assert) | KILLED (failure_repaired) |
| M5 | `on_reverified` resolves the incident and clears the hold | KILLED (test 1) |
| M6 | disable `release_resolved` | KILLED (owner_resolved) |
| M7 | re-escalate after resolution | KILLED (owner_resolved) |
| M8 | place the hold only when the incident is new | KILLED (failure_repaired) |

No test covers N-1 (that a decision door exists), N-2 (per-version buyer count) or N-3.

## Suites run (one at a time, system python3)

| Suite | Result |
|---|---|
| `tests/test_w6_support_defect_incident.py` | 6/6 OK (56 s) |
| `tests/test_opus2_reverify_withhold.py` | 0 failed |
| `tests/test_w4_fm2_surface_reverify.py` | 8/8 passed |
