# Independent review: A1 children's-safety chain as one unit (2026-11-07)

Target: `origin/claude/w6-INTEG1` 0f2459c5 + A1R core c3a7b93a + Codex leaves
`origin/codex/a1-waist-drawcord-unknown` 4800b597 and `origin/codex/a1-whole-toy-fit` 2af2a48e.
Both leaves contain c3a7b93a. They fork at 32f31633: 4800b597 has 5 commits of its own (named hold,
atomic hold, snapshot recheck, design-scoped small parts, waist drawcord). 2af2a48e has 6 (toy eyes,
neck drawcord, felt, attached crochet, flexible fit, whole toy). Nothing was pushed.

## Verdict: DO NOT SHIP c3a7b93a+4800b597+2af2a48e as merged

The safety logic now fails closed in every case I probed, and the earlier slug-reuse, retitle and
numeric-age escapes are fixed. Three things still block a ship:

1. Two required A1 suites are red on the merged tree: 7 failures in `test_childrens` and 4 in
   `test_codex_a1_hard_eyes`.
2. Infant-only product nouns still escape, as the earlier review already reported.
3. Three detector mutants (C10, C13, C14) survive only because the tests that would kill them are red.

## Merge recipe (exact, reproduced)

```
git fetch origin
git worktree add --detach /home/user/bl-runs/wt-rev-a1full 0f2459c5
cd /home/user/bl-runs/wt-rev-a1full
git merge --no-ff --no-edit 4800b597
#  CONFLICT COORDINATION.json (one hunk, "claims" array): HEAD adds CODEX-A7-FRESHNESS-FIX;
#  4800b597 adds OPUS2-A1R-CHILD-SAFETY-CORE, CODEX-A1-STUFFING-EVIDENCE, -AUDIENCE-SHORTHAND,
#  -HARD-EYES, -PART-ALIASES, -NAMED-SAFETY-HOLD, -HOLD-ATOMIC, -HOLD-SNAPSHOT, -WAIST-DRAWCORD.
#  Resolution: union. Keep HEAD's object, close it with "}," and then open "{" for theirs. JSON validates.
#  release.py auto-merges cleanly (W6 edits plus A1 hold edits).
git add COORDINATION.json && git commit --no-edit          # -> 4363d551
git merge --no-ff --no-edit 2af2a48e
#  CONFLICT COORDINATION.json: union (HOLD-SNAPSHOT entry, then CODEX-A1-FLEXIBLE-FIT entry).
#  CONFLICT tests/test_codex_a1_hard_eyes.py: union (keep the HEAD repeat/dedup test and the parked-action
#    test, then append the 4 new 2af2a48e worker tests).
#  CONFLICT tests/test_codex_a1_small_parts_finite.py: union (keep the 2 HEAD design-scoped/source-race
#    tests, then append test_large_flexible_sewn_pieces_need_physical_fit_evidence).
#  childrens.py and pdf.py auto-merge.
git add -A && git commit --no-edit                         # -> d39e14e1 (local only)
```
Conflicts with w6-INTEG1 itself: only `COORDINATION.json` (bookkeeping). No source conflicts.
The real conflict is a **semantic** one between the two leaves. It is finding F2.

Required follow-ups before ship (not applied, not verified): fix F1 and F2, then rerun the suites below.

## Probe results (u2probes/p6.py plus extended probes p7, p8 and p9, all on d39e14e1)

| Earlier gap | Now |
|---|---|
| One-piece stuffed ball under an assigned slug (cloudline-baby-blanket, market-basket-medium) | REFUSED (`undecided`): the assignment is bound to the exact CIR sha256 |
| Ball under an exempt slug (heart-row-ring-pillow) | REFUSED: the exemption is bound to the CIR sha256 |
| Exempt product retitled "Baby Basket" / "Nursery Basket for Baby" | REFUSED: NOT_FOR_CHILDREN plus child words gives UNDECIDED |
| "(0-12 months)", "ages 2+", "3 months", "Size 2T", "0–3 mo", "Ages 3 and up" | REFUSED (`age_under_18`) |
| "Pacifier Clip" | **still PASSES** (F3) |
| N6: unreadable construction | Code fails CLOSED: `['construction unreadable (RuntimeError): UNKNOWN, held']`, render refused `undecided`. The mutant still SURVIVES every A1 suite (F5) |
| N10: `small_parts.blocking` exception | Code fails CLOSED: `['sewn-on pieces unmeasurable …: unknown']`, render refused `small_parts`. The mutant still SURVIVES (F5) |
| N12: owner-action dedup | Covered. The new HEAD test checks repeat attempt gives 1 open action. Removing the in-function check is an equivalent mutant, because `ops.owner_queue_guard` (a flush hook) and `uq_owner_actions_open_requirement` also dedupe |

## Mutation results on the merged tree (all 12 A1 suites under pytest; the red tests deselected)

Earlier mutants: N1–N4, N7, N9, N11, N13 and N15–N18 are KILLED (test_a1r core).
- N5' (non-yarn material): KILLED.
- N8' (geometric CLEAR treated as clear): KILLED.
- **N8'' (UNKNOWN-band piece dropped): SURVIVED** (F4).
- N6 and N10: SURVIVED (F5).

New mutants on the Codex logic:

| Mutant | Result |
|---|---|
| C1 assignment slug-only | KILLED (assignment_content) |
| C2 exemption hash ignored | KILLED (stuffing_evidence) |
| C3 retitle not rechecked | KILLED (child_title) |
| C4 uncheckable listing passes in `childrens_decision_for` | **SURVIVED** (F7) |
| C5 age threshold 18 to 1 | KILLED (listing_child) |
| C6 month/year ranges ignored | KILLED (listing_child) |
| C7 whole-toy hold removed | KILLED (small_parts_finite) |
| C8 waist drawstring | KILLED (waist_drawcord) |
| C9 snapshot recheck | KILLED (atomic_hold) |
| C10 felt treated as integral | **SURVIVED** (F2) |
| C11 eligibility listing words | KILLED (listing_child) |
| C12 pdf mismatched-assignment check | KILLED (assignment_content) |
| C13 unqualified toy eyes ignored | **SURVIVED** (F2) |
| C14 attached crocheted features ignored | **SURVIVED** (F2) |

## Findings

**F1 HIGH: `test_childrens` is red. 7 failures, already present on leaf 2af2a48e alone.**
- Where: `brambleloop/src/brambleloop/publish/pdf.py:790-791`, the whole-toy hold
  `if childrens == ("amigurumi_toy", ch.UNDER_3) and not blocks: blocks.append("whole toy …")`.
- What happens: this hold runs in `_refuse_an_undecided_childrens_title`, before
  `_refuse_what_the_childrens_assessment_refuses` (pdf.py ~1058-1060). Every under-3 amigurumi is
  therefore held as `small_parts` before its specific hazard is assessed.
- Tests broken: `test_a_childrens_pdf_whose_pattern_names_safety_eyes_under_three_is_refused`
  (tests/test_childrens.py:563), `test_unqualified_toy_eyes_are_unassessed_not_inferred_safe` (:620),
  `…applied_part_aliases…`, `…hard_eye_aliases…`, `…neck_or_hood_drawcord_variants…`,
  `…sewn_felt_shape…`, `…explicit_separate_crocheted_features…`.
- Still fail-closed: nothing renders, so no child product escapes.
- But the owner action is misdirected. It asks for "a measured small-parts sample" while the real
  finding (hard eyes, neck drawcord) is hidden until that sample is supplied.
- Repro: `cd brambleloop && PYTHONPATH=src:tests venv-integ4/bin/python tests/test_childrens.py`. The same 7
  fail at 2af2a48e. 4800b597 passes.
- Fix: run the content assessment before adding the whole-toy block, or include both findings.

**F2 HIGH: semantic merge conflict. `test_codex_a1_hard_eyes` is red (4 failures).**
- Tests: tests/test_codex_a1_hard_eyes.py:98, :110, :122 and :134, from 2af2a48e.
- What they assert: `status in {FAILED, DEAD}` and the hazard code in `result["error"]`.
- What the merged code does: 4800b597 (2e856b80) turned safety refusals into a named hold, so the
  status is DONE with `held=True`, `reason=safety_refusal`.
- The merged behaviour is correct. I checked it with p9.py: all four are held, the code (UNRECOGNISED_PART or
  NECK_OR_HOOD_DRAWSTRING) is in `why`, there is no pdf, and attempts=1.
- Fix: rewrite those 4 asserts to the held form, as in the test at line 10.
- Side effect: while these 4 and the F1 tests are red, mutants C10 (felt), C13 (unqualified toy eyes) and
  C14 (attached crochet) are not killed by any green test. The new detectors are effectively unguarded.

**F3 HIGH (carried over, not fixed): infant-only product nouns are not child-audience signals.**
- Where: `brambleloop/src/brambleloop/products/launch0.py:1697` (`CHILD_AUDIENCE_WORDS`) and `child_words_in`.
- Repro (p7.py, non-stuffed basket CIR, new slug) PASSES with no hold for: "Pacifier Clip", "Teething
  Ring", "Teether", "Rattle", "Soother Holder", "Binky Leash", "Bib", "Bassinet Cover",
  "Stroller Blanket", "Little One Blanket", "Lovie", "Toy", "Doll", "Plushie", "Babyshower Gift",
  and also "12M".
- Why it matters: pacifier clips, teethers and rattles are infant products by definition, with
  strangulation and choking hazards. They render with no children's safety block.
- Stuffed forms are still caught by construction. These flat or corded products are not.

**F4 MED: the M10 "UNKNOWN band blocks" test became vacuous, and mutant N8'' survives.**
- Change: 7e54c330 made every geometric-CLEAR message contain "…fit under force is unknown"
  (`gates/small_parts.py:104-106`).
- Effect: `test_a1r5…` asserts `any(SP.UNKNOWN in b for b in SP.blocking(unknown))`
  (tests/test_a1r_child_safety_core.py:401, :404). That now passes even when the UNKNOWN-band piece is dropped.
- Real code is still closed.
- Fix: assert on the specific piece name or on the `: unknown)` verdict suffix.

**F5 MED: N6 and N10 still have no test, though the code fails closed.**
- Where: `products/launch0.py:1552` and `gates/small_parts.py:99`.
- No test feeds an unreadable construction or an exception from `separable_pieces`. Mutating either
  `return [... UNKNOWN ...]` to `return []` passes all 12 A1 suites.
- p8.py shows the current behaviour is CLOSED: UNKNOWN, then a hold.
- Fix: add the two p8 cases as tests.

**F6 LOW: Codex `__main__` blocks run only a subset, and the venv cannot run 3 Codex files.**
- `test_codex_a1_small_parts_finite.py` `__main__` (line 193) runs 2 of its 6 tests. One test is defined
  after the `__main__` block (line 199).
- `test_codex_a1_hard_eyes.py`, `_waist_drawcord.py` and `_atomic_hold*.py` have no `__main__` or
  need pytest. pytest is not installed in venv-integ4. I installed it into the scratchpad only.
- Any `python tests/X.py` gate therefore under-runs these files.

**F7 LOW: C4 survives.**
- Where: `launch0.childrens_decision_for` (`except ValueError: return (UNDECIDED, None)`).
- Not tested directly. It is held in practice by the eligibility and listing_package `except` branches.

**F8 LOW: the PostgreSQL hold path is unverified.**
- `test_codex_a1_atomic_hold_pg` reports 4 skipped, and atomic_hold reports 1 skipped.
- The NOWAIT/advisory-lock branch of `_childrens_hold` (runtime/release.py ~9822-9897) has never run on Postgres.
- The Codex handoff says the same.

**F9 INFO: hold-path robustness and auditability.**
- Fail-closed paths: when a CIR digest cannot be computed, the small_parts/safety hold raises
  TransientError and retries. It never clears, but no owner action is written for that case.
- Audit trail: the hold writes AuditLog and OwnerAction in one transaction, after rechecking the job lease and
  the certified CIR digest (C9 is killed). An existing parked action is not reopened.
- Decision records: the decisions themselves are code constants (`_ASSIGNED_DECISION_CIR_SHA256` and
  `_STUFFED_DECISION_CIR_SHA256`, launch0.py:1392-1407), commented "owner ratification remains pending".
  They are auditable through git, but there is no reapproval workflow, so any CIR edit to an assigned
  product holds it until a code change.
- All 6 bound digests match the current inventory, so nothing is held today by accident.

**Other review questions**
- Thresholds: none relaxed. CYLINDER_MM, tolerance, CLOSURE_MAX_STITCHES and the 18-year and 216-month bounds
  are unchanged or new. Geometric CLEAR is now *stricter* (it blocks).
- UNKNOWN treated as clear: no instance found in the code.
- Laura and identity rules: no change. The diff c3a7b93a..d39e14e1 contains no "laura". `_identity` in
  listing_package is the package audience identity, not persona or identity rules.

## Suites (venv-integ4, run one at a time from brambleloop/, merged tree d39e14e1)

| Suite | Result |
|---|---|
| test_a1r_child_safety_core | PASS (141s) |
| test_childrens | **FAIL 7** (F1) |
| test_risk_matrix | PASS (209s) |
| test_launch0 | PASS (39s) |
| test_opus2_stuffed_finishing | PASS |
| test_codex_a1_assignment_content | PASS 1 |
| test_codex_a1_atomic_hold | 9 passed, 1 skipped |
| test_codex_a1_atomic_hold_pg | 4 skipped |
| test_codex_a1_child_title | PASS 1 |
| test_codex_a1_hard_eyes | **4 failed, 3 passed** (F2) |
| test_codex_a1_listing_child | PASS 3 |
| test_codex_a1_small_parts_finite | PASS 6 (pytest) |
| test_codex_a1_stuffing_evidence | PASS 2 |
| test_codex_a1_waist_drawcord | PASS 2 |
| test_w6_support_defect_incident | PASS (0 failures) |
| test_w5_a7_supply_stall | PASS |

Free disk at start was 11G; it stayed at or above 8.3G throughout.

Artifacts are in /tmp/claude-0/-home-user-Project-Money/0aa334b9-5ba9-5fd2-9058-e50b4b8604ea/scratchpad/a1full/
(p7.py, p8.py, p9.py, mut3.py/.out, mut4.py/.out, mut4b.py/.out, suites.txt, log_*).
Worktrees: /home/user/bl-runs/wt-rev-a1full (merged), -mut and -leaf (scratch, both at d39e14e1, clean).
