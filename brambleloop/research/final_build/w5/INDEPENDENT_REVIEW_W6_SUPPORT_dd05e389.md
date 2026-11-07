# Independent delta review: W6 support-defect incident, c5cad183 → dd05e389

- **Worktree.** /home/user/bl-runs/wt-rev-support5, detached at dd05e389. Clean: nothing was committed or pushed.
- **Python.** /home/user/bl-runs/venv-integ4.
- **Repro script.** /tmp/claude-0/-home-user-Project-Money/0aa334b9-5ba9-5fd2-9058-e50b4b8604ea/scratchpad/rev5/repro.py. Run it from `brambleloop/` as `PYTHONPATH=src:tests python <repro.py> <R>`.
- **Mutation harness.** /tmp/claude-0/-home-user-Project-Money/0aa334b9-5ba9-5fd2-9058-e50b4b8604ea/scratchpad/rev5/mut.py.
- **Suite.** `tests/test_w6_support_defect_incident.py` at dd05e389, unmutated: 17 OK, 0 failures (74 s). I ran no other suites, because the delta touches only defects.py, one line of release.py, and this test.

## Verdict: SHIP dd05e389

The declarative `reconcile_holds` closes all of the prior F-1 to F-4 ordering holes, and I found no HIGH. The remaining issues fall into three groups:
- a pre-existing window of up to one hour, bounded by the triage cadence (F-1);
- an under-hold that needs a superseded version to be re-certified in place (F-2);
- fail-closed edges and stale text.

All are follow-ups.

## Prior findings (c5cad183), re-checked

- **F-1 (HIGH), confirmed-then-resolved loses its hold.** FIXED. `_active` keeps a `confirmed` incident active whatever resolves it. Tests d4 and x4 pin this.
- **F-2 (MED), permanent superseded hold.** FIXED in the form reported. There is no supersession any more, and an undecided incident stays open and decidable. A narrower form remains: see F-3 below.
- **F-3 (MED), metadata-only bump ends the hold.** FIXED. `instruction_hash` ignores title and notes, and test h2 pins this.
- **F-4 (LOW), untested guards.** The guards they covered (`still_held`, `carried_to` dedupe, `open_sigs`) were removed with the redesign.

## Findings at dd05e389

### F-1 (MED, pre-existing): a new or rolled-back current release with the held instructions is unheld until the next hourly triage
- **Location.** defects.py:265-270. `reconcile_holds` runs only from `support.triage` (release.py:2620, hourly per worker.py:663) and from `record_owner_decision`. Neither certification (`pipeline._persist_release`, pipeline.py:1605) nor decertification runs it, and `release_gates.for_publish` reads only the stored record.
- **Repro `window`.** An open incident is on 1.2.1. An identical 9.0.0 is certified. Before the next triage, `blocks_publish` for 9.0.0 is `False`; after triage it is `True`.
- **Repro `rollback`.** A confirmed incident is on 1.2.1. An identical 9.0.0 is certified, then a corrected 10.0.0. When 10.0.0 is decertified, 9.0.0 is current and unheld (`False`) until triage (`True`).
- **Effect.** `launch.plan` → `store.publish` can run in that window on a release whose defect the owner confirmed. Shadow mode refuses publication today, which is why this is MED and not HIGH.
- **Fix, either of these.**
  - Make the hold not depend on which release is current: hold every stored version whose `instruction_hash` matches an active incident's, not only the current one.
  - Call `reconcile_holds` (or an active-incident check) from `for_publish` or `_persist_release`.

### F-2 (MED): the hash is read from the held version's mutable `cir_json`, not from what buyers reported on
- **Location.** defects.py:267. `versions[(slug, held)][0]` is the current stored CIR of the held version. `_persist_release` (pipeline.py:1625-1638) replaces `cir_json` in place when a version is re-certified under a new release hash.
- **Repro `inplace`.**
  1. An open incident is on 1.2.1, and an identical 9.0.0 is current and held (`True`).
  2. 1.2.1's `cir_json` is changed, which is what an in-place re-certification does.
  3. After triage, 9.0.0 shows `held False` while the incident on 1.2.1 is still open.
- **Effect.** The release on sale still has the reported instructions, and it is unheld.
- **Fix.** Store `instruction_hash` in the incident's `detail` when `escalate` opens it, and compare the current release against that snapshot.

### F-3 (LOW-MED): a `confirmed` incident that something else resolves can never be re-decided
- **Location.** defects.py:345, where the decision is refused on `inc.resolved`, together with `_active` at :238.
- **Repro `confirmed_resolved`.**
  1. The owner records `confirmed`.
  2. `resolve_signatures` resolves the incident; the suite treats this as legitimate in d4.
  3. `not_a_defect` is then refused: "that incident is already resolved".
  4. After certifying an identical 9.0.0, both 1.2.1 and 9.0.0 are held and `cards []`.
- **Effect.** The hold lasts for good on these instructions. A changed-instruction release is free, so this is fail-closed. But an owner who confirmed by mistake has no path back.
- **Fix.** Allow a decision when `owner_decision == confirmed`, even if the incident is resolved.

### F-4 (LOW): a corrected release changed only outside the allowlist stays held
- **Location.** defects.py:218.
- **Detail.** `grading` (the F-762 size matrix: body/intended cm and ease), `configuration` (F-757), `finished_size_note` and `risk_class` are all ignored. Repro `grading` prints `ignored` for each. So a fix made only to the size chart or ease leaves the corrected release held.
- **Effect.** Under `confirmed`, the owner's only way out is a false `not_a_defect`, and under F-3 there is no way out at all. It is fail-closed, so LOW.
- **Fix.** Consider adding `grading` and `configuration` to `INSTRUCTION_KEYS`.

### F-5 (LOW): an undecided incident resolved by anything else leaves an orphan card and no hold, and is never re-escalated
- **Repro `undecided_resolved`.**
  1. `resolve_signatures` is run on an open, undecided incident.
  2. Three more buyers report the row. The output is `held False open [] cards [1]`.
  3. The decision is then refused: "already resolved".
- **Who can trigger it.** No production code resolves `support.defect:` rows today, so this is LOW.
- **Fixes, any of these.**
  - Close the card in `reconcile_holds` when the incident is inactive.
  - Let `escalate` re-open a row that was resolved without an owner decision.

### F-6 (LOW): stale text still promises automatic supersession
This contradicts the "no automatic supersession" model and the honesty rule in CLAUDE.md. The stale text is in three places:
- **defects.py:154-156.** The incident's `clears` field says "or a newer certified version superseding this one".
- **defects.py:313-314.** The card's `consequence_of_delay` says "certifying a corrected version also ends the hold". In fact the incident, the card and the hold on the old version all remain.
- **ops/incident_lifecycle.py:191-194.** The REMEDIATION entry says "a newer certified version supersedes it (support.triage)".

### F-7 (LOW): performance and concurrency
- **Performance.** Every triage and every decision loads every PatternVersion's full `cir_json` and certificate, plus every `support.defect:` incident ever recorded, resolved ones included. It also hashes the full components twice per active incident, with no per-version cache. This is fine at today's scale. It could be narrowed to slugs with an active incident plus versions that already carry a `support.defect:row` key.
- **Concurrency.** `reconcile_holds` reads versions, then incidents, then writes only the difference.
  - Because `escalate` commits the incident before the hold, a concurrent reconcile cannot release a newly placed hold for lack of an incident.
  - A triage snapshot taken before a concurrent `not_a_defect` can re-place a hold. That lasts until the next triage and is fail-closed.
  - Residual risk: `record_reverification` is a read-modify-write of the whole certificate JSON with no row lock. The decision route, now an HTTP-time writer, can race a worker's `cir.twin`/`cir.reverse` write on the same version, and one check entry is lost. If the lost entry is a real twin failure, that is an under-hold until the next daily check. This is pre-existing in `withholding`, and the decision route makes it more reachable.
- **`cir_json` None or {}.** `instruction_hash` returns None, and the current release is not held (test e1 pins this as "unknown is not the same"). That fails open, but only on data no certified release can have.
- **Unknown new field.** It is ignored, so it errs toward holding, as the docstring says. If all six keys were renamed, every pattern would hash identically, and that too fails closed.

### F-8 (LOW, carried from 785849c0/c5cad183 F-5)
- A JSON array body still returns 500 at main.py:1464.
- `id: true` is accepted as 1.
- A decision is committed before `reconcile_holds`. If reconcile raises, the route returns 500 after the decision is recorded, and a retry of `not_a_defect` gets 400.

## Interaction with escalate's direct hold
`escalate` (defects.py:161) places the same `(slug, version, check)` that `reconcile_holds` wants for an open incident. It runs in the same triage, immediately before reconcile, so the two always agree. Mutant Mg, which removes escalate's hold placement, SURVIVES, because the hold is redundant. It is harmless, but `escalate`'s `withheld` field now reports a write that reconcile would have made anyway.

## R2 mutant (`not_a_defect` → inactive line, defects.py:236-237): equivalent, verified
- `owner_decision` is written only by `record_owner_decision`. There, `not_a_defect` always calls `_resolve` in the same session.
- I grepped `src/`: no code sets `Incident.resolved = False` (the only hits are `SupportCase`).
- So `not_a_defect` implies `resolved`, and the remaining expression `(not resolved) or decided == "confirmed"` is already False.
- The line only matters for hand-edited data.

## My mutants (tests/test_w6_support_defect_incident.py, one at a time)
| Id | Mutation | Result |
|---|---|---|
| Mg | `escalate` places no hold (reconcile only) | SURVIVED (equivalent: redundant placement) |
| Mm | `have` built from certified versions only, so holds on decertified versions are never released | KILLED (2 tests) |
| Mb | own-version hold wanted even when the version is not stored | SURVIVED (benign: `record_reverification` no-ops; `placed` lists it on every run) |
| (R2) | drop the explicit `not_a_defect` line | equivalent (above) |

Gaps not pinned by any test: F-1's window, and F-2 (a snapshot hash would need its own test).
