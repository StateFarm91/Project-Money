# Independent delta review: W6 support-defect incident, 785849c0 → c5cad183

The branch was retargeted mid-review from 1d22cdca to c5cad183. Both are covered here, and the verdict is for c5cad183.

- **Worktree.** /home/user/bl-runs/wt-rev-support4, detached at c5cad183. It is clean: nothing was committed or pushed.
- **Python.** /home/user/bl-runs/venv-integ4.
- **Repro script.** /tmp/claude-0/-home-user-Project-Money/0aa334b9-5ba9-5fd2-9058-e50b4b8604ea/scratchpad/rev4/repro.py, run as `PYTHONPATH=src:tests python repro.py <R>` from `brambleloop/`.
- **Mutation harness.** /tmp/claude-0/-home-user-Project-Money/0aa334b9-5ba9-5fd2-9058-e50b4b8604ea/scratchpad/rev4/mut.py.

## Verdict: DO NOT SHIP c5cad183

(At 1d22cdca the verdict was also DO NOT SHIP 1d22cdca, because of F-0a and F-0b below. Both are fixed at c5cad183.)

At c5cad183 a defect the owner **confirmed** can still lose its hold with no decision on it (F-1). A superseded hold can also become a permanent hold on the release on sale, with no path to clear it (F-2).

## Fixed between 1d22cdca and c5cad183 (verified)

- **F-0a (HIGH at 1d22cdca).** A carried hold was never released by `not_a_defect`. R1 at 1d22cdca showed `current 9.0.0 held True`, with no open incident and no card, so the hold was permanent. At c5cad183 R1 shows `9.0.0 held False`. FIXED.
- **F-0b (HIGH at 1d22cdca).** Incident A was open and carried to 9.0.0. A second incident B on 9.0.0 (same per-row hold key `support.defect:row3`) was decided `not_a_defect`. That cleared 9.0.0 on every triage: `supersede` re-carried the hold and `release_resolved` removed it again. The steady state was `9.0.0 held False` while A was open, including when A was `confirmed` (R2, R2C). At c5cad183 R2 and R2C show `9.0.0 held True`. FIXED, via `still_held`. **It is not pinned by a test; see F-3/N3.**

## Findings at c5cad183

### F-1 (HIGH): a resolved `keep_hold` incident is missing from `still_held`, so a sibling `not_a_defect` releases a confirmed defect's hold.
- **Location.** defects.py:226-236. `still_held` is built only from OPEN incidents (`open_rows`). A confirmed incident that is then resolved keeps `keep_hold=True` but contributes nothing to `still_held`. Two things resolve a confirmed incident:
  - another resolver, the `resolve_signatures` path that the suite itself treats as valid in `test_the_owner_decides...` d4;
  - a supersession, defects.py:369.
- **What triggers it.** An older resolved, non-`keep_hold` incident lists the same version in `carried_to`. Every triage it clears the shared per-row check on that version.
- **Repro R8.**
  1. Incident A on 1.2.1 is carried to identical 9.0.0, then decided `not_a_defect`.
  2. Three buyers of 9.0.0 report the same row, which opens B. B is decided `confirmed` (`9.0.0 held True`).
  3. Someone resolves B (`keep_hold True`). On the next triage the output is `confirmed-defective 9.0.0 held False`.
- **Repro R8S** (supersede path).
  1. Same steps, but B is superseded by a changed 10.0.0 and is never touched by anyone. The output is `confirmed-defective 9.0.0 held False`.
  2. 10.0.0 is then withdrawn (decertified), and 9.0.0 is current again: `on-sale 9.0.0 held False`.
- **Effect.** The supersede path promises that "the old version stays held". It is broken on the next triage, and a rollback puts a confirmed-defective release back on sale, unheld.
- **Fix.** Build `still_held` from open incidents **and** from resolved incidents with `keep_hold`, using every held version (own and `carried_to`). Add R8/R8S as tests.

### F-2 (MED): the hold left by a supersession can become a permanent hold on the release on sale, with no card, no incident and no path.
- **Location.** defects.py:367-379 (supersede) and :295-297 (decision refuses resolved incidents).
- **Repro R3.**
  1. 1.2.1 is held, undecided. A changed 10.0.0 is certified, so the incident is superseded with `keep_hold`.
  2. 10.0.0 is decertified, so 1.2.1 is current again.
  3. The output is `current is 1.2.1 held True`, `open incidents []`, `open cards []`, and `record_owner_decision` returns `decision refused: that incident is already resolved`. No code path clears `support.defect:row3` on 1.2.1. I grepped every `record_reverification(` caller: only `release_resolved` clears this key, and it skips `keep_hold`.
- **Why it matters.** It also applies when the owner never decided: three buyer questions plus any later changed version hold the old release forever. This is the deadlock class from 05961fd0 N-1. It is fail-closed, so MED.
- **Fix.** Either of these:
  - re-open the incident or card when a `keep_hold` version becomes current again;
  - allow `not_a_defect` on a superseded incident that was never `confirmed`.

### F-3 (MED): `supersede` treats any CIR change as a correction, so a metadata-only bump ends a confirmed defect's hold on the release on sale.
- **Location.** defects.py:359 (`same = cir_json == cir_json`) and :367.
- **Repro R7.** A is `confirmed`. A 9.1.0 whose CIR differs only in `title` is certified; its rows are identical (`rows identical? True`). The output is `on-sale 9.1.0 held False open []`. Buyers must accumulate 3 new distinct reports on 9.1.0 before anything happens.
- **Tests.** The suite's own "corrected" fixture is a title-only change (test ...:390), so the tests encode this behaviour.
- **Fix.** Compare the reported row's compiled content, or the CIR minus non-instruction metadata. Treat "only metadata changed" as identical and carry the hold.

### F-4 (LOW): guards with no test (surviving mutants, c5cad183)
- **N3: `still_held` ignores open incidents' `carried_to` — SURVIVED.** This is exactly the F-0b fix (R2 direction: A open carried, B decided `not_a_defect`). The new test `..._but_not_another_incidents_hold` only covers the other order (A decided while B is open, where B's own version is enough). Fix: add R2 as a test.
- **N4: `still_held` keyed on (slug, version) without the check — SURVIVED.** This is fail-closed over-holding: an open incident on row 5 would block release of row 3's hold. Add a two-row test.
- **M8: no `customer_ref` truthiness guard in `_release_for` (defects.py:~92) — SURVIVED.** With the guard removed, `None` buyers collapse to one, so the guard's real effect is minor.
- **M9: `sig in open_sigs` in `release_resolved` (defects.py:233) — SURVIVED.** It is a dead guard, because `rows` are resolved incidents and signatures are unique per open row.
- **M10: `carried_to` de-duplication (defects.py:361) — SURVIVED.** R5 shows the dedupe works today (`carried_to ['9.0.0']` after 3 triages), but no test pins it.

### F-5 (LOW, carried): route and decision edges
- **Body shape.** At main.py:1462 a JSON array body still raises `AttributeError` and returns 500.
- **Bool ids.** `id: true` is accepted as 1.
- **Retry.** Re-posting a `not_a_defect` returns 400 "already resolved" (785849c0 F-6).
- **Duplicate cards.** In the R2 shape the owner gets two cards for the same row and identical CIR (A's and B's), each decided independently. This is the source of the contradictory-decision cases in F-1.
- **Mapping is now tested.** `DecisionRefused` is mapped to 400 and the `support_defect` branch is tested (M12 KILLED). 785849c0 F-4 M14/M15 are closed.

## Checked and OK (c5cad183)
- **Corrected version is itself defective (R4).** Superseding to 10.0.0 and then 3 buyers on 10.0.0 opens a fresh incident on 10.0.0 with a new card, and 10.0.0 is held while 1.2.1 stays held. `not_a_defect` on it releases only 10.0.0.
- **`confirmed`, then carry, then supersede (R5).** 1.2.1 and 9.0.0 stay held and 10.0.0 is free. The carried hold is idempotent across triages: one `carried_to` entry, and the withholding record is unchanged (`record()` compares the reason string).
- **Flip (R6).** Carry to 9.0.0, decertify 9.0.0, decide `not_a_defect`, recertify 9.0.0: 9.0.0 is released, which is correct after `not_a_defect`.
- **`confirmed` closes the card for good.** M5 KILLED. `confirmed` sets `keep_hold`: M6 KILLED.
- **Stale `still_held` within one triage.** The order is escalate, then supersede (sets `carried_to`), then `release_resolved`, so `carried_to` is current when `still_held` is read. A concurrent escalate between the read and the clear could drop an open hold until the next triage, which re-asserts it. That is transient, LOW.

## Mutants

Results are from tests/test_w6_support_defect_incident.py, run one at a time.

| Id | Mutation | Result |
|---|---|---|
| M1 | lower version supersedes (1d22cdca) | KILLED |
| M2 | no carry (1d22cdca) | KILLED |
| M3 | supersede without keep_hold (1d22cdca) | KILLED |
| N1 | no `still_held` skip | KILLED |
| N2 | release own version only | KILLED |
| N3 | `still_held` ignores open `carried_to` | **SURVIVED** |
| N4 | `still_held` ignores the check key | **SURVIVED** (fail-closed) |
| M4 | supersede does not close the card | KILLED |
| M5 | card reopens after a decision | KILLED |
| M6 | confirmed without keep_hold | KILLED |
| M7 | cases of any version count | KILLED |
| M8 | no customer_ref guard | SURVIVED (minor) |
| M9 | no open_sigs guard | SURVIVED (dead) |
| M10 | carried_to not deduped | SURVIVED |
| M11 | carried hold not placed | KILLED |
| M12 | route maps DecisionRefused to 500 | KILLED |
| M13 | resolved release+row re-escalates | KILLED |
| M14 | no current==held skip | KILLED |

## Suite
c5cad183, unmutated: `tests/test_w6_support_defect_incident.py` gives 14 OK, 0 failures. I ran no other suites: the delta touches only defects.py and this test.
