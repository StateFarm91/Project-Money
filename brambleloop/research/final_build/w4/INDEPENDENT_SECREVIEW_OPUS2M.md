# Independent security and correctness review OPUS2M: Secondary's fixes for OPUS2K, 2026-11-02

Reviewer: an independent Claude Code session (branch `claude/w5-SECREVIEW-OPUS2M`).
- The review was read-only on every branch under review. This report is the only file written.
- Every probe and mutation ran in scratch worktrees in the session scratchpad. Each mutation was
  reverted (the mutation script writes the original file back). Every worktree was clean afterwards
  (`git status --porcelain`: 0 lines in all 10).
- Nothing was deployed, published, messaged or spent. Railway and production were not touched.
  There was no network access beyond `git fetch`.
- Pet bed and stocking are out of scope.

| # | Subject | Branch | Head | Diffed against |
|---|---|---|---|---|
| 1 | K-1 / K-2 / K-3 / K-10 | opus2/p0-revenue-workforce | 6769e696 | c3074241 |
| 1m | same, merged | opus2/p0-revenue-workforce-b4merge | 651b1580 (merge of 6769e696) | 8f798b0 (first parent) |
| 2 | K-4 | opus2/p1-culture-sweep-timeout | e0be7c4d | 3468fe73 |
| 3 | K-5 / K-6a | opus2/p0-cir-colourwork | d4486b8c | 424d69a9 |

## Verdicts

| # | Subject | Verdict | Why |
|---|---|---|---|
| 1 | K-1/K-2/K-3/K-10 | **DO NOT SHIP as the K-1 closure** (small fix). It is not a regression: 6769e696 is strictly better than c3074241. | K-2, K-3 and K-10 are closed, and every OPUS2K repro is closed. But K-1 was a class of bypass, and only the listed words were added. The same live draft-path breach remains: "Tote Foursome", "Tote Threesome", "Tote Quad", "Tote Quadruplets", "Tote Triad", "Triple Tote", "Tote Quadruple", "Tote Combos", "Tote Assortments", "Tote Multi Pack", "Tote Trilogies" and "Hundred Tote" are each drafted as one tote, and `title_promise` backs them (M-1, MED). |
| 1m | merge 651b1580 | **Faithful** | `git diff 8f798b0..651b1580` is byte-identical to `git diff 771e1e1a..6769e696`. The 3 changed source and test files are identical at 6769e696 and 651b1580. The 72-title probe output and the catalogue probe are identical. The suites pass. |
| 2 | K-4 | **SHIP** (test-only) | A spy shows that the new test reaches `_outcome_unknown` with `last_call` set and the record PENDING, so M7n and M7r are now killed. M7o is confirmed equivalent. M7s still survives, although the commit message says the test kills it (M-5, LOW). |
| 3 | K-5/K-6a | **DO NOT SHIP** (one-line fix) | Every K-5 repro is closed. But the delta **loosens the gate**: matching now starts at a word boundary, so claim words inside a compound, which 424d69a9 refused on all-plain fabric, are now backed: "Minimosaic", "Microtapestry", "Multicolourwork", "Superfairisle", "Pseudointarsia" (M-2, MED). Restoring the substring match (mutant Wr) passes every suite. |

## Findings

| ID | Sev | Subject | Finding | Repro |
|---|---|---|---|---|
| OPUS2M-1 | MED | 1 | **K-1 is closed for the listed words only.** It is the same closed-denylist pattern OPUS2K flagged. On the one-piece sunset tote, with `plan(category="bag")` = `tote` and `title_promise.backed` True: "Tote Foursome", "Tote Threesome", "Tote Quad", "Tote Quadruplets", "Tote Triad", "Tote Triple", "Triple Tote", "Tote Quadruple", "Hundred Tote", "Tote Trilogies" ("trilogy" is in the list, but the `token[:-1]` inflection cannot read "-ies"), "Tote Combos", "Tote Assortments" and "Tote Multi Pack" (only "multi-pack" or "multipack" is listed, and with no `s`), and "Mothers Tote", "Families Tote", "Daughters Tote" (the new markers have no plural forms). The two readers still disagree. "Tote Multipacks" is refused by `plan` but backed by `title_promise`. "Tote Doubles" is drafted by `plan` but unbacked by `title_promise`, so it fails closed later. Ambiguous titles with the same result: "Tote Pack", "Tote Kit", "Tote Lot", "Tote II", "Tote Gross", "Tote Score", "Matched Tote", "Coordinating Tote". *Fix:* one multiplicity reader shared by `plan()` and `title_promise`, so they cannot disagree. It should apply generic inflection (`s`/`es`/`ies`) to every count word and marker, and add foursome, threesome, quad(ruple/ruplet), triad, triple, hundred and "multi pack". Better still, route to `tote` only when every word in the title is in an allowlist, as recommended for the pet bed (OPUS2K-7). | `tp.py` on 6769e696 |
| OPUS2M-2 | MED | 3 | **Regression: the word-start anchor loosens the claim reader.** `colourwork_claims` now matches `\b<claim>` (d4486b8c launch0.py `found = [c for c in COLOURWORK_CLAIMS if re.search(rf"\b…", folded)]`). On 424d69a9 this was a substring match. On the all-plain `_band({})` fixture, as title and as tag: "Minimosaic", "Microtapestry", "Minitapestry", "Superfairisle", "Multicolourwork" and "Pseudointarsia" were refused (`fabric_truth.backed` False, 1 listing finding). Now they are backed with 0 findings. The commit and the comment ("never inside another word") present this as intended, but no false positive motivated it: the catalogue result is identical under both rules. *Fix:* restore the substring test for the base claims (`_fold(c).strip() in folded`). Mutant Wr does exactly that and passes `test_opus2_cir_colourwork`, `test_first_customer_gate` and `test_launch0`. Pin "Minimosaic Basket" as refused. | `cw.py` on 424d69a9 vs d4486b8c |
| OPUS2M-3 | MED | 3 | **Inflections and numbers above four still pass (pre-existing, K-5 class).** The base claims match as a prefix, but the variant regexes end in `\b`, so their inflected forms are missed. On plain fabric, as title and as tag: "Tapestries", "Graphgans", "Jacquards", "Duplicate Stitching", "Colour Works", "Color Works", "Two-Tones". The colour count regex lists only two/three/four/2/3/4, so "Five-Colour" and "5 Colour" pass. Also passing: "C-2-C", "C 2 C", "Corner-2-Corner", "Dual Colour", "Duo-Tone", "Duotone", "Colour Block", "Colorblock" and "Pixel Crochet" ("Two Colourways" and "Many Colours" are arguable). All of these also passed on 424d69a9, so none is a regression. *Fix:* end every variant with `\w*`, as the base claims are matched; use `(?:\d+|two|…|ten|multi|bi|tri|dual|duo) ?(?:colou?r|tone)`; add `c ?2 ?c`, `corner (?:to\|2) corner`, `colou?r ?block` and `duo ?tone`. | `cw.py` |
| OPUS2M-4 | LOW | 3 | **Unicode bypasses of `_fold`.** NFKC does not remove diacritics or invisible format characters, and `.lower()` runs before NFKC. Each of these passes on plain fabric: "Tape​stry" (zero-width space), "Mo­saic" (soft hyphen) and "Mo‍saic" (ZWJ) are split into two words; "Fáir Ísle", "Tápestry", "Mosäic" and "Colourwörk" lose the accented letter; "FAİR ISLE" (U+0130 lowers to i + U+0307); "Таpestry" (Cyrillic Т and а). A zero-width character between words ("Fair​Isle") is caught. *Fix:* delete category-Cf characters before folding, apply NFKD and drop the Mn marks, then fold. A confusables map is optional. | `cw.py` |
| OPUS2M-5 | LOW | 2 | **M7s is not killed, although commit e0be7c4d says it is.** M7s (`row is None or …`: a missing row counts as unknown) survives `test_opus2_culture_sweep_timeout`. The new test always has the PENDING row. This is low impact, because a set key with no row is near-unreachable. M7o is genuinely equivalent: `_classify_failure` returns non-UNCERTAIN only for `TransientError`/`PermanentError`, and `classify.py` catches both in an earlier `except`. | mutants on e0be7c4d |
| OPUS2M-6 | LOW | 2 (pre-existing, outside the delta) | **Orphan spend can be counted twice under a lasting DB write fault.** With the K-4 fault (the `_update(outcome=UNCERTAIN)` write fails) and `attempts=3`, the costs hold **two** `in_flight_when_worker_lost_counted_at_estimate` rows for one sent call. The cause is `paid_calls._count_orphan`, which writes the spend row and releases the reservation before it writes `orphan_billed=True`. When that flag write fails, every replay bills again. It is the same on 3468fe73, so it is not introduced here. It over-counts (the safe direction for the ceiling), but it breaks "counted ONCE". The K-4 test pins `attempts=1` only. *Fix:* write the flag in the same transaction as the spend row, or before it. | `k4.py` (attempts 1/2/3) on e0be7c4d and 3468fe73 |
| OPUS2M-7 | LOW | 1 | **List-entry test gaps.** These mutants survive `test_opus2_draft_constructions`: N5 (septet/octet removed from `_COUNT_WORDS`), N8 (the `(triple\|double)(dc\|tr\|sc)` not-a-count clause removed), N9 (treble/knit/sided removed from the double clause), N11 (hats/pouches/rugs/garlands/squares/hearts removed), N14 (totebags), N15 (cosys), N19 (seven…twelve removed from `_MULTIPLE_WORDS`), N20 (seventeen…twenty), N21 (sextet/septet/octet from `_MULTIPLE_WORDS`). Every core rule is killed (N1–N4, N6, N7, N10, N12, N13, N16–N18; K1, K1b and K5 from OPUS2K-3 are now killed). | mutants |
| OPUS2M-8 | LOW | 3 | **Test gaps.** Wa (NFKC removed) survives: no full-width title is pinned, although "Ｆａｉｒ Ｉｓｌｅ" is caught only because of NFKC. Also surviving: We (`held` lookbehind removed: the only "held" title also contains "double"), Wg ("four" removed), Wm (C2C mapped to intarsia, equivalent: also refused) and Wp (`two ?tone` to `two tone`, equivalent after folding). | mutants |
| OPUS2M-9 | INFO | 1 | **New fail-closed false positives on the retitle backstop.** "Double Handle Tote", "Double Strap Market Tote", "Double-Handled Tote", "Mother's Day Tote" and "Family Picnic Tote" are now unbacked (`double` counts 2; `mother` and `family` are markers). `plan` already refused all of them, and no catalogue CIR is affected. "Double Sided Tote" and "Two-Way Tote" stay backed. | `tp.py` |
| OPUS2M-10 | INFO | 3 | K-6a works as intended: "Double-Stranded Basket" and "Held Double Stranded Basket" are backed on plain fabric, while "Double-Stranded Fair Isle", "Double Stranded Colourwork", "Doubled Stranded" and "Double-Strand Stranded" are still refused. The two rules now agree on "double-stranded" (`title_promise._NOT_A_COUNT` on branch 1). OPUS2K-6a's "Two Colour Stripe Basket" is still refused (fail-closed). | `cw.py` |
| OPUS2M-11 | INFO | all | `launch0.py` merges cleanly across 6769e696 and d4486b8c (`git merge-tree`). The three heads still conflict with each other in `COORDINATION.json`, `publish/release_gates.py` and `publish/withholding.py`, which none of these deltas touches. That comes from the stale bases, and the merge-order condition already stated in OPUS2J/K still applies. Neither e0be7c4d nor d4486b8c is in 651b1580 yet. | `git merge-tree --write-tree` |

**Removed or weakened assertions: none.** All three diffs add tests only. The one edit to an
existing test line (the `("Two-Tone Market Tote", "Three-Ply Cotton Tote")` tuple) adds two
titles and keeps both asserts. In the source, `_COUNT_WORDS`, `_MULTIPLE_WORDS` and
`_PLURAL_OBJECT_NOUNS` only grow. `_NOT_A_COUNT` grows, but only over "double" phrases, and
"double" was not counted at all before. K-2 makes `backed` stricter. On branch 3, two things
loosen: the `(?<!double )(?<!held )` lookbehind, which K-6a asked for, and the word-start anchor,
which nothing asked for (M-2). No deterministic validation was overridden.

**Catalogue (no CIR became unbacked or refused).** Two catalogue probes were run, and their output is
byte-identical before and after on both code branches (c3074241 = 6769e696 = 651b1580, and
424d69a9 = d4486b8c):
- `cat.py` covers every `BUILDERS ∪ PROPOSED_BUILDERS` CIR (11) and every `excluded_from_launch0()` row (18). It records `title_promise` (backed, claimed, markers), `fabric_truth`, `colourwork_findings`, `colourwork_claims` and a CIR repr hash.
- `inv.py` covers `inventory.universe()`: 28 slugs, of which 26 exist. That is the "26 products" the commits cite.

Together the two probes cover 27 distinct titles. In both, `launch0_is_all_gate_clean()` is
True, every CIR is `title_promise`-backed, and no `excluded_from_launch0` row has a gate reason.
The brief's figure of 40 CIRs could not be reproduced: no enumeration in the code yields 40.
The figure is therefore UNKNOWN, not PASS. The coverage above is everything the repository
enumerates.

## Mutations (each reverted; every worktree clean afterwards)

| ID | Subject | Mutation | Result |
|---|---|---|---|
| N1 / N2 | 1 (K-2) | numeral-vs-plural clause removed / `makes > 1` to `>= 1` | killed / killed |
| N3 / N4 / N6 | 1 (K-1) | "double" / duet…triplet / fifteen…eighteen removed from `_COUNT_WORDS` | killed |
| N5 | 1 | septet, octet removed | **survives** (M-7) |
| N7 | 1 | whole `double[- ](crochet…)` not-a-count clause removed | killed |
| N8 / N9 | 1 | `(triple\|double)(dc\|tr\|sc)` removed / treble, knit, sided removed | **survive** (M-7) |
| N10 / N12 / N13 / N16 | 1 (K-10/K-1) | beds+nests / multipack…combo / matching…daughter / shoppers removed from nouns | killed |
| N11 / N14 / N15 | 1 | hats…hearts / totebags / cosys removed | **survive** (M-7) |
| N17 / N18 | 1 (plan) | collective nouns / seven…twenty removed from `_MULTIPLE_WORDS` | killed |
| N19 / N20 / N21 | 1 (plan) | seven…twelve / seventeen…twenty / sextet…octet removed | **survive** (M-7) |
| K1 / K1b / K5 | 1 (K-3) | OPUS2K mutants: two…six removed / twin removed / `_NOT_A_COUNT` eats every two/three | killed (survived on c3074241) |
| M7n / M7r | 2 | non-DECLINED counts / key present → True | **killed** (survived on 3468fe73) |
| M7q / M7t | 2 | always False / no key → True | killed |
| M7s | 2 | missing row → True | **survives** (M-5) |
| M7o | 2 | out-of-scope always UNCERTAIN | survives: **equivalent** (verified, M-5) |
| Wb / Wo | 3 | old `[\s_\-]` fold / no fold | killed |
| Wc | 3 | base claims whole-word (`\b…\b`) | killed |
| Wd | 3 | both lookbehinds removed | killed |
| Wf / Wh / Wi / Wj / Wk / Wl / Wq | 3 | digits / two-tone / graphgan / c2c / duplicate-stitched / `(s\|ed)` / `colou?r work` removed | killed |
| Wn | 3 | listing gate back to substring over `COLOURWORK_CLAIMS` | killed |
| Wa / We / Wg | 3 | NFKC removed / `held` lookbehind removed / "four" removed | **survive** (M-8) |
| Wm / Wp | 3 | C2C → intarsia / `two ?tone` → `two tone` | survive: equivalent (M-8) |
| Wr | 3 | **base claims back to substring** (the proposed M-2 fix) | passes the suites: the fix is safe |

## Tests run (from `brambleloop/`, `PYTHONPATH=src:tests PYTHONDONTWRITEBYTECODE=1 python3 tests/<f>.py`, after `pip install -r requirements.txt`)

Every suite exited 0.

| Head | Suites |
|---|---|
| 6769e696 | test_opus2_draft_constructions (0 failed); test_launch0; test_w4_pipe_board; test_opus2_size_claims (0 failed); test_first_customer_gate (12 passing); test_compiler; test_twin; test_reverse; test_vacuity; test_w4_listready; test_opus2_knowledge_gaps (0 failed) |
| 651b1580 | test_opus2_draft_constructions (0 failed); test_first_customer_gate (12 passing); test_launch0 |
| e0be7c4d | test_opus2_culture_sweep_timeout (0 failed); test_culture; test_culture_feed; test_w3_spend_paid_calls (PASS 0 failing); test_w4_close5_vision_timeout (PASS 0 of 4 failing); test_w3_spend_hygiene (PASS); test_vacuity; test_w4_fmbatch1_retention_guard |
| d4486b8c | test_opus2_cir_colourwork (0 failed); test_compiler; test_twin; test_reverse; test_vacuity; test_pattern_truth; test_launch0; test_leadtime; test_first_customer_gate (12 passing); test_physfix (46/46) |

## Commands

```
git fetch origin opus2/p0-revenue-workforce opus2/p0-revenue-workforce-b4merge \
  opus2/p1-culture-sweep-timeout opus2/p0-cir-colourwork
git diff c3074241..6769e696; git diff 3468fe73..e0be7c4d; git diff 424d69a9..d4486b8c
diff <(git diff 771e1e1a..6769e696) <(git diff 8f798b0..651b1580)       # identical
git worktree add --detach $S/{r,r0,rm,rmut,c,c0,cmut,w,w0,wmut} <head>  # S = session scratchpad
python3 $S/probes/tp.py  < titles.txt  # title_promise + plan(category=bag) on the sunset tote, 72 titles
python3 $S/probes/cw.py  < cw.txt      # fabric_truth + colourwork_findings (title and tag) on _band({})
python3 $S/probes/cat.py; python3 $S/probes/inv.py   # catalogue, before vs after (diff: identical)
python3 $S/probes/k4.py                # spy on _outcome_unknown; K-4 fault at attempts 1/2/3
python3 $S/probes/mut.py <wt> <file> <id> '<old>' '<new>' <suite...>   # apply, run, restore
git merge-tree --write-tree 6769e696 d4486b8c   # launch0.py clean; 3 unrelated conflicts
```

The probe scripts stay in the reviewer's scratchpad and were not committed. Each uses only the
repository's public functions and test fixtures on the named commit, with no network and no
database outside the suites' temporary SQLite.
