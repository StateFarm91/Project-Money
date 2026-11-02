# Independent review: A1-R · P0-SAFETY-CHILDREN (architectural correction)

- **Reviewed:** 2026-11-02 (UTC). Read-only and adversarial.
- **Subject:** `origin/opus2/p0-child-safety-core` at **1dd257be**, one commit on top of `claude/w5-INTEG1` 7c42e706. 7c42e706 is an ancestor.
- **Method:** detached worktrees `a1rrev` (1dd257be) and `a1rbase` (7c42e706). Python is `/home/user/bl-runs/venv-integ4/bin/python`. Suites ran one at a time. Probes and logs are in `scratchpad/a1rr-probes/`. Nothing was committed or pushed.

## Verdict: **DO NOT SHIP** (1dd257be)

The architecture is correct, and the guard is real for the cases its tests cover:
- the construction gate is primary;
- the implicit candidate exemption is refused for a stuffed form;
- the two Launch-0 stuffed pieces carry reasoned entries;
- small parts has an UNKNOWN band;
- all four required mutants and the PDF fold-bypass mutant are killed;
- Launch-0 PDFs are byte-identical.

But acceptance items (1), (3) and (6) are not met:
- A **one-piece stuffed ball** renders through the real Worker with no children's decision (DONE).
- A seamed form whose stuffing is spelled "Fiber-Fill", "fibre-fill", "polyester filling", "toy fill", "kapok", "poly pellets" and so on, without the flag, renders (DONE).
- **Greek capital look-alikes** ("Βaby Basket", Greek Beta) render (DONE).
- The drafting routes do not use the shared fold. A2 adds a third, separate fold.

## Findings

| ID | Sev | Finding | Repro |
|---|---|---|---|
| A1R-1 | **HIGH** (child safety; acceptance 1, 6) | **`closed_stuffed_form` misses closed stuffed forms.** It is true only for (a) a seam with `stuff_before_closing`, or (b) a material name matching a narrow regex **and** at least one assembly seam. Three misses: **(i) a one-piece stuffed ball** (one magic-ring component closed by decreasing, polyester fibrefill in `materials`, `assembly=[]`) gives `False`; it compiles, and `assets.build` through the real Worker on a durable SQLite file is **DONE** under "Juniper Friend". This is the literal "stuffed ball" of acceptance 6: the commit's "stuffed ball" is the ring pillow (two pieces, a stuffed seam) renamed, so the case was never tested. **(ii) Stuffing spelled outside the regex**, with seams but no flag: "Fiber-Fill", "fibre-fill", "polyester filling", "toy fill", "fiberfil", "kapok", "poly pellets", "wool roving" and "foam insert" all give `False`. `compile_cir` is ok and the document renders ("Fiber-Fill" through the Worker: DONE). **(iii) Stuffing named only in `designer_notes`/a seam note**: `False`. The compiler's own stuffing reader (`cir/compiler.py:416`, "stuff"/"fibre") is a different heuristic again. *Fix:* fail closed. Any non-yarn material, or any material that is not a recognised yarn, together with a closed construction (a seam, or a rounds component that decreases back to a close), is a closed stuffed form or is UNKNOWN, which holds. Pin a one-piece ball and the material spellings through `assets.build`. | `a1rr-probes/p1.py` (A, B, C); `p2.py` ("one-piece ball DONE", "Fiber-Fill no flag DONE") |
| A1R-2 | MED (acceptance 3, text layer) | **The look-alike fold lower-cases before mapping, so Greek capitals miss or mis-map.** Results: Β→β (unmapped), Ν→ν→"v", Μ→μ→"u", Η→η→"n", Υ→υ→"u". "Βaby Basket" folds to `βaby basket` (no word), and a plain non-stuffed basket under that title is **DONE** through the Worker. Also missed: "ΒΑΒΥ", "Νursery", Cherokee "Ᏼaby", Cyrillic "Ү" and "Ь". What works: Cyrillic, fullwidth, math-alphanumeric, small capitals, circled letters, combining marks, RLM/RLO, soft hyphen, tag characters, U+2063 and ZWJ all fold correctly (probe D). *Fix:* map the capitals before `lower()`, or map both cases; add Β, Ν, Μ, Η, Υ, Ζ, Ү, Ь and the Cherokee capitals; preferably use a UTS #39 skeleton. | `p1.py` D; `p2.py` ("greek Beta DONE") |
| A1R-3 | MED (acceptance 3) | **The fold is not "one shared fold used by draft, renderer and survey".** `text_fold.fold` is imported only by `launch0.child_words_in`, which only the renderer and the survey call. The drafting routes read titles through `creative.fallback_constructions.fold_title` (NFKC and dashes, no Cf strip, no look-alikes). The test docstring's claim that the drafting routes use the fold is false. A2 (`opus2/a2-name-object` 51f87859) adds a **third** fold, `launch0._motif_fold` (NFKC with Cf/Mn stripped, no look-alikes), which reads motif words. After both merge there are three divergent folds. *Fix:* make `text_fold.fold` the single implementation; have `fold_title` and A2's `_motif_fold` call it. | grep `text_fold`/`unicodedata.normalize`; `git diff 7c42e706...51f87859 -- launch0.py` |
| A1R-4 | MED (acceptance 2, owner visibility) | **The hold is not a named, owner-visible hold.** A held product is a generic `ValueError` in `assets.build`. The Worker treats it as retryable (`retry=not PermanentError`), so it spends attempts toward a dead letter, and the OPUS2-P0 dead-end re-drive re-runs it. No hold record or owner decision item is written. The survey (`childrens_titles_without_an_assignment`) covers only catalogue builders and `inventory.universe()`, so a radar- or registry-drafted cushion held at runtime appears nowhere except the failed job. It does not block unrelated products: those are separate jobs, and the plain basket was DONE in the same run. *Fix:* a `PermanentError` subclass (for example `ChildrensDecisionRequired`) plus an audited hold or owner-decision row naming the slug and the reason. | `p2.py`; `runtime/worker.py` generic `except` |
| A1R-5 | LOW–MED (acceptance 4) | **The small-parts block applies only to stuffed forms, and the UNKNOWN→block path is unpinned.** `blocks = small_parts.blocking(cir) if stuffed else []`, so an assigned **non-stuffed** children's product with a sewn-on piece that fits the cylinder renders: probe F gives `bottom 27×27 mm: fits`, and the document is not refused. `separable_pieces` returns `[]` when `gauge is None`, so missing geometry reads as clear instead of UNKNOWN. Mutant M10 (block only on FITS, so UNKNOWN passes) **survives** the test: only `verdict()` is unit-tested at the band, and the end-to-end block uses a piece that FITS. *Fix:* run `blocking` for every assigned product, treat unmeasurable geometry as UNKNOWN, and pin an UNKNOWN piece through `_refuse_…`. | `p1.py` F; mutant M10 |
| A1R-6 | LOW (acceptance 2, audit) | **"Audited owner decision" is a code constant.** `NOT_MERCHANDISED_TO_A_CHILD` entries carry a reason but no decided-by or date, and no DECISION_LOG entry was added. The audit trail is git history only. No code path writes the dict: grep finds no runtime writer, only the test's pop/restore. `_decided_not_for_children` still auto-grants `NOT_FOR_CHILDREN` to candidate slugs, and `childrens_decision_for` correctly refuses that for stuffed forms (M4/M9 killed). But `listing_package.identity` still reports the raw `childrens_decision`, not `childrens_decision_for`, so a listing could show "not_for_children" for a stuffed form the renderer holds (the A1-7 class of divergence). | code read |
| A1R-7 | LOW (tests) | **Weak real-path assertions.** `_assets_build` cases assert only a substring of `last_error` and never `status == FAILED`. The kneeler control asserts that "children"/"stuffed" is absent from the error, but **not** that the job is DONE, so an unrelated failure passes. The "ears by at_round only" case clears placement on the ring pillow, which has no ears. The cushion test checks the hold by calling `_refuse_…` directly, not `assets.build`. The fold spellings are tested only in a unit call, not through the Worker on a non-stuffed product, which is where the word layer is the only layer. | test file |
| A1R-8 | INFO (merge) | Merges cleanly onto `claude/w5-INTEG1` 7c42e706, which is an ancestor. Against A2 51f87859 there is one textual conflict, in **COORDINATION.json**: both append a claim, which is trivial. `launch0.py` auto-merges. There is a semantic duplicate-fold issue (A1R-3). | `git merge-tree` |
| A1R-9 | INFO (verified true) | Launch-0 is unchanged. 8 variant PDFs plus the ring pillow and the kneeler render **byte-identically** on 7c42e706 and 1dd257be (sha256 equal for all 10). The only difference is that `childrens_decision` for the two stuffed pieces moves from `undecided` to the explicit reasoned `not_for_children`. No existing test was modified: the test diff is only the added `test_a1r_child_safety_core.py`. No child-safety guard was removed. The small-parts band is exact at the boundaries: 27.7/50 fits, 31.7/57.1 fits, 31.71 unknown, 35.7 unknown, 35.71 clear, depth 61.1 unknown, 61.11 clear. | `bytes_*.out`; `p1.py` E |

## Prior findings (A1-1..A1-7)

| ID | Status at 1dd257be |
|---|---|
| A1-1 (gate keyed on stuffed AND placed) | **PARTIAL.** The placement field is gone and the stuffed flag alone triggers. The panel_pair cushion is held and the catalogue pieces have reasoned entries. Variant (e) is still open: stuffing without the flag works only for regex-matching names. The one-piece ball is open (A1R-1). |
| A1-2 (no confusable or invisible fold) | **PARTIAL.** Cyrillic, Cf, fullwidth and math letters are fixed; Greek capitals and others are open (A1R-2). |
| A1-3 (untested split, mutants survive on INTEG1) | **CLOSED.** The test is self-contained, and M1–M9 are killed on this INTEG1-based head. |
| A1-4 (implicit exemption accepted for a stuffed form) | **CLOSED** in the renderer and the survey; the listing package still reads the raw decision (A1R-6). |
| A1-5 (zero tolerance on small parts) | **PARTIAL.** The ±4 mm UNKNOWN band and the evidence register exist. It applies to stuffed forms only, and UNKNOWN→block is unpinned (A1R-5). The toy's own `ami_small_parts` is not on this base: once the amigurumi branch lands, two small-parts implementations will exist. |
| A1-6 (registry hold reads req.title) | **N/A on this base.** The registry is not on INTEG1, so this is still open on `opus2/p0-construction-registry`. |
| A1-7 (survey and renderer diverge) | **MOSTLY CLOSED.** The survey reads construction and covers `inventory.universe()`. Runtime-drafted products are still outside it (A1R-4). |

## Mutants (each applied, run against test_a1r_child_safety_core, restored; worktree verified clean)

| ID | Mutant | Result |
|---|---|---|
| M1 | `closed_stuffed_form` always False (gate-always-false) | KILLED |
| M2 | `child_words_in` without the fold (no-fold) | KILLED |
| M2b | `fold` = `lower()` only | KILLED |
| M3 | renderer `stuffed = False` (reads words only) | KILLED |
| M4 | `childrens_decision_for` accepts the default (default-decision-accepted) | KILLED |
| M5 | PDF path reads words without the fold (fold bypass) | KILLED |
| M6 | `SMALL_PARTS_TOLERANCE_MM = 0` | KILLED |
| M7 | small-parts check removed | KILLED |
| M8 | material path in `closed_stuffed_form` dropped | KILLED |
| M9 | NOT_MERCHANDISED check bypassed in `_for` | KILLED |
| M10 | `blocking` only on FITS (UNKNOWN passes) | **SURVIVED** |

## Suites (1dd257be, each run alone)

| Suite | Result |
|---|---|
| test_a1r_child_safety_core | PASS (6/6, 57 s) |
| test_childrens | PASS (1 s) |
| test_launch0 | PASS (68 s) |
| test_launch0_listing_truth | PASS (727 s) |
| test_pdf_premium | PASS (230 s) |
| test_opus2_stuffed_finishing | PASS (0 failed) |
| test_first_customer_gate | PASS (12/12) |
| test_vacuity | PASS |
| test_shadow | **UNKNOWN**: timed out at 1800 s under heavy machine contention (about 7 concurrent test_shadow runs from other reviews). 5 tests were OK and 0 failed before the kill. |
| test_swarm_runtime | PASS (36 s) |

## Commands

```
S=/tmp/claude-0/-home-user-Project-Money/0aa334b9-5ba9-5fd2-9058-e50b4b8604ea/scratchpad
git worktree add --detach $S/a1rrev 1dd257be; git worktree add --detach $S/a1rbase 7c42e706
cd $S/a1rrev/brambleloop && PYTHONPATH=src:tests $PY $S/a1rr-probes/{p1,p2}.py
for w in a1rbase a1rrev; do (cd $S/$w/brambleloop && PYTHONPATH=src:tests $PY $S/a1rr-probes/bytes.py); done
python3 $S/a1rr-probes/mut.py $S/a1rrev test_a1r_child_safety_core
git merge-tree --write-tree 1dd257be 7c42e706; git merge-tree --write-tree 1dd257be 51f87859
```
