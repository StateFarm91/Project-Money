# Independent security and correctness review OPUS2J: deltas on OPUS2I, plus the pet bed and stocking constructions, 2026-11-01

Reviewer: an independent Claude Code session (branch `claude/w5-SECREVIEW-OPUS2J`). This review
was read-only on every branch under review; this report is the only file written.
- Every probe and mutation ran in scratch worktrees in the session scratchpad and was reverted
  with `git checkout`. Every worktree was clean afterwards (`git status`: 0 modified).
- Nothing was deployed, published, messaged or spent. Railway and production were not touched.
- `git fetch origin` ran first. Every head matched the brief except one: `opus2/p0-stocking` is
  now at the merge be12b47b (parents 5c7b984a and d0a7685f). Both 5c7b984a and be12b47b were
  reviewed.

| # | Subject | Branch | Head | Diffed against |
|---|---|---|---|---|
| 1 | PR #3 | opus2/p0-revenue-workforce | 6d6d83d9 | 558e7ca9 (OPUS2I) |
| 2 | PR #7 | opus2/p1-culture-sweep-timeout | 7c3806fc | 4c777a0b (OPUS2I) |
| 3 | PR #8 | opus2/p0-family-membership | d8d80301 | fa529381 (OPUS2I) |
| 4 | — | opus2/p0-cir-colourwork | fa02cb49 | f57219d0 (OPUS2I HOLD); digests also checked against d230e8fd |
| 5 | — | opus2/p0-pet-bed | d0a7685f | merge-base with `claude/w4-INTEG8-next` = 7746cd46. The new work is the single commit d0a7685f on 55450fc3 (the OPUS2H-reviewed 13d67502 merge), so the probes compare against 55450fc3. |
| 6 | — | opus2/p0-stocking | 5c7b984a, merge be12b47b | Same merge-base 7746cd46. New work: 5c7b984a on 55450fc3, then the be12b47b union. |

## Verdicts

| # | Subject | Verdict | Highest open finding |
|---|---|---|---|
| 1 | PR #3 I-1 (inflected plural markers) | **CHANGES_REQUIRED** | MED (J-1: "Totes", "Two Market Totes", "Three Totes", "Twin Totes" and "Tote Quartets" still read as backed on one tote; the brief requires "Totes" unbacked) |
| 2 | PR #7 C-4 (only a guard-recorded UNCERTAIN is billed) | **ACCEPT** | LOW (J-3: three mutants survive) |
| 3 | PR #8 F-5 (culture families never derived as sets) | **ACCEPT** | INFO |
| 4 | Colourwork (I-2, I-4 to I-8) | **LIFT HOLD**, with a merge condition: the INTEG1 `colour_changes.py` conflict must be resolved and re-reviewed (J-7) | MED (J-7 integration). J-6 (MED) is pre-existing and not on this branch. |
| 5 | Pet bed (d0a7685f) | **CHANGES_REQUIRED** | HIGH (J-9: "Pet Bed Liner", "Pet Bed Blanket", "Pet Bed Mat", "Basket Weave Pet Mat", "Nest Toy" and others are drafted as a 45 cm basket, and no gate catches it) |
| 6 | Stocking (5c7b984a / be12b47b) | **CHANGES_REQUIRED** | HIGH (J-13: "Stocking Stitch Blanket", "Stocking Garland" and "Stocking Holder" in any category, and category `stocking` with any title such as "Snowflake Coaster", are drafted as a Christmas stocking, and no gate catches it) |

Across all six subjects:
- None weakens the paid-call anti-double-spend protocol (F-307/F-339), and none queues a paid job.
- No Launch-0 `design_digest`, release hash, CIR JSON, written pattern, yardage,
  `fabric_truth` verdict or compile finding moves. This was checked for 37 CIRs per commit
  (item 4, items 5 and 6).

---

## 1. PR #3: opus2/p0-revenue-workforce 6d6d83d9 — CHANGES_REQUIRED

The delta is `launch0._plural_marker_pattern` plus 7 test lines. Each `PLURAL_MARKERS` word now
matches as a whole word with `(?:s|es|d|ed)?`, and `library` matches as `librar(?:y|ies)`.
6d6d83d9 merges into `claude/w5-INTEG1` (6eb3ca0e) with no conflict (`git merge-tree`).

### I-1: fixed for the plural markers

Repro (`tp.py`): each title was applied to the drafted one-piece tote (`finished_objects == 1`).
The verdict is `title_promise.backed`; nt is the number of `eligibility.name_truth` findings.

| Title | 558e7ca9 | 6d6d83d9 |
|---|---|---|
| Market Tote Sets | True, nt 0 | **False, nt 1** |
| Tote Pairs / Tote Bundles / Tote Collections / Tote Duos / Tote Trios | True, nt 0 | **False, nt 1** |
| Bundled Totes | True, nt 0 | **False, nt 1** |
| Tote Libraries | True, nt 0 | **False, nt 1** |
| Sunset Market Tote / Closet Tote / Asset Tote | True | True (stay backed) |
| Market Tote Set / Bundle Tote | False | False |
| **Totes**, Market Totes, Tote Bags | True | **True** (J-1) |
| **Two Market Totes**, **Three Totes**, **Twin Totes**, **Tote Quartets** | True | **True** (J-1) |

**Catalogue (`tpu.py`):** 26 buildable `inventory.universe()` slugs and 11 `launch0.BUILDERS`,
so 37 CIRs. All 37 `(title, backed, plural_markers)` tuples are identical on 558e7ca9 and
6d6d83d9. None is unbacked. The four marker titles ("Hexagon Coaster Set", "Raised Diamond
Lattice Placemat Pair", "Textured Stripe Ornament Set (6)" and "Heart Applique Motif Library
(12)") still read their markers. No `backed` verdict changes.

### Findings

**J-1 MED: plural nouns and number words are still read as one object.** This is the same class
as I-1, one step over.

`title_promise` counts only:
- digits;
- `_COUNT_WORDS` (pair, duo, trio, quartet);
- `PLURAL_MARKERS`.

So on one tote:
- "Totes", "Market Totes" and "Tote Bags" read as backed (a plural object noun);
- "Two Market Totes", "Three Totes" and "Twin Totes" read as backed. The number words two to
  six and "twin" are not counted, although `fallback_constructions._MULTIPLE_WORDS` already
  lists them for `plan()`;
- "Tote Quartets" reads as backed. `quartet` is a count word, but it is compared as an exact
  token, and it is not a plural marker.

Where it bites:
- `plan()` refuses "Two Market Totes" and "Market Totes", because `_MULTIPLE_WORDS` has "two"
  and "totes". So the draft path is protected for those titles.
- `plan()` **drafts** "Tote Quartets" as one tote, and `title_promise` and `name_truth` back it.
  That is live on the draft path today.
- For any path that retitles after drafting (H1-4), the backstop `title_promise` / `name_truth`
  passes every title in the J-1 rows.

The brief requires "Totes" to read as unbacked on a one-piece tote. It does not.

*Fix:*
- count the number words (two to twelve) and twin/twins in `title_promise`;
- match `_COUNT_WORDS` with the same inflection rule as the markers ("quartets");
- treat a plural of the object's own product noun as a claim of more than one when
  `finished_objects == 1`. One option is the `_MULTIPLE_WORDS` noun list, generalised to
  `<noun>s` for the product-type words.
- Pin "Totes", "Two Market Totes" and "Tote Quartets" as unbacked.

**J-2 INFO: the inflection rule over-matches in the fail-closed direction.** "Paired Stripe
Tote" now reads as `pair` (unbacked on one tote). That refuses a name, which is acceptable. A
mutant that adds `tle|tled` ("Settle Tote" reading as `set`) survives, because nothing pins the
false-positive side beyond Sunset/Closet/Asset.

`F.cosy` still uses `\b{m}\b` with no inflections (fallback_constructions.py:487). So
"Egg Cosy Sets" drafts one cosy, and `title_promise` then refuses it. This fails closed, but the
draft and the gate disagree.

### Mutations (worktree `r`, each reverted; clean afterwards)

| ID | Mutation | Result |
|---|---|---|
| M1a | inflections removed (`\b{w}\b` again) | **killed** ("Market Tote Sets") |
| M1b | `librar(?:y)` only (no "ies") | **killed** ("Tote Libraries") |
| M1c | `d` dropped from the suffixes | **killed** ("Bundled Totes") |
| M1d | over-match (`tle\|tled` added) | survives: fail-closed direction, unpinned (J-2) |

---

## 2. PR #7: opus2/p1-culture-sweep-timeout 7c3806fc — ACCEPT

The change has three parts:
- `user = prompt(topics)` is built before `sent = True`, and before the budget check.
- New `_outcome_unknown(exc)`. Inside a job scope, it reads the paid-call guard's own record for
  `scope.last_call["paid_call_key"]`. It is True only when that row's outcome is UNCERTAIN, and
  False when there is no key (the guard never reached the provider). Outside a scope, it uses
  `anthropic._classify_failure(exc) == UNCERTAIN`.
- The uncertain branch bills at the estimate only if `sent and _outcome_unknown(exc)`. Otherwise
  it releases the reservation and re-raises.

`gateway/paid_calls.py` and `gateway/anthropic.py` are unchanged. 7c3806fc merges into INTEG1
with no conflict.

### C-4: fixed at the root inside a job

End-to-end repro (`c4.py`): the real `culture.sweep` job runs through the real `Worker` and
`paid_calls.guarded`, using the test file's `_worker_sweep`.

| Failure | 4c777a0b | 7c3806fc |
|---|---|---|
| Timeout / ValueError / ConnectionResetError / IncompleteRead (sent) | done, sent 1, UNCERTAIN, 1 row at CA$0.013425 `unknown_counted_at_estimate` | **same** (C-2 still holds) |
| pre-send: `paid_calls._assert_lease` raises (write-ahead) | **done, sent 0, phantom row CA$0.013425** | **FAILED, visible, sent 0, no cost row** |
| pre-send: `effects.claim` raises (record PENDING, no intent) | **done, phantom row** | **FAILED, visible, no cost row** |
| pre-send: `json.dumps` in `AnthropicProvider.complete` raises | **done, phantom row** | **FAILED, visible, no cost row** |

**Post-send, pre-record (`c4b.py`).** `_send` returns OK, and then `_update(outcome=OK)` raises,
so the record stays PENDING.
- Attempt 1 fails with no cost row.
- The retried attempt 2 meets the PENDING record. `_replay` counts the orphan **once at the
  estimate**: `in_flight_when_worker_lost_counted_at_estimate`, CA$0.013422.
- The call is never re-sent (sent = 1). The job is done.

So in this case UNKNOWN spend is counted one attempt later by the guard's orphan rule, never as
zero and never twice. The base also billed it, in attempt 1.

**F-307/F-339 still hold.**
- The call is never re-sent in any case above.
- The guard writes UNCERTAIN before re-raising (`_update`, then `mark_uncertain`, then
  `_incident`), so the classify-side read sees the committed row.
- `PaidCallUnresolved`, `PaidCallReplayedFailure` and `EffectRefused` are still `PermanentError`
  and go to the first branch, so they are not billed.

**UNKNOWN is never recorded as zero.**
- The uncertain branch writes `amount_cad=estimate`.
- The re-raise branch writes no row and leaves the case to the orphan rule.
- The only no-row case with a final outcome is DECLINED (a provider refusal), which is correct.

**Stale key.** `scope.last_call` survives a successful call, because the success path does not
consume `ledger_note()`. But a later pre-send failure in the same scope would read an OK row and
re-raise, so a stale key never bills. The uncertain branch consumes it. `culture.sweep` calls
`classify` once per job (release.py:7701), so a stale UNCERTAIN key is not reachable.

### Findings

**J-3 LOW: three mutants survive. These are test gaps, not fail-open paths in production.**
- **M7n** (`row.outcome != DECLINED` instead of `== UNCERTAIN`) survives. It would bill a
  PENDING record in classify and then again through the orphan rule on retry (double count).
  No test exercises a PENDING record. *Fix:* add the `effects.claim`-raises case, or the c4b
  shape, to the worker test, asserting exactly one cost row across both attempts.
- **M7o** (the outside-scope branch always UNCERTAIN) and **M7p** (`prompt()` moved back after
  `sent = True`) survive. The outside-job test's prompt bug fires first in the budget estimate,
  before `sent`.

**J-4 INFO: outside a job scope, a provider-side pre-send bug is still billed.** Repro: with
`db` and no job scope, `json.dumps` raising in `AnthropicProvider.complete` returns "classifier
call outcome unknown (TypeError)" and writes CA$0.040254 `unknown_counted_at_estimate`. That is
over-counted, never under. The only production caller runs in a job, so this matters only for
probes and ad-hoc calls.

**J-5 INFO: a registered vendor that does not use `paid_calls.guarded`** would now have its
in-job UNCERTAIN failures re-raised and unbilled, because `last_call` is None. Only `anthropic`
is registered (`providers._VENDORS`), so this is latent. State the guard as a precondition in
`register_vendor`.

### Mutations (worktree `c`, each reverted; clean afterwards)

| ID | Mutation | Result |
|---|---|---|
| M7l | `_outcome_unknown` always True | **killed** (c4 test) |
| M7q | `_outcome_unknown` always False | **killed** (c2/c3 worker test, timeout test) |
| M7m | no `paid_call_key` → True | **killed** (c4 test) |
| M7n | any non-DECLINED record counts | survives (J-3) |
| M7o | out-of-scope branch always UNCERTAIN | survives (J-3) |
| M7p | `prompt()` built after `sent = True` | survives (J-3) |

---

## 3. PR #8: opus2/p0-family-membership d8d80301 — ACCEPT

The change:
- `family_report` sets `bundle_ready = distinct >= 2 and not key.startswith("culture:")`, so
  `portfolio_has_bundle_ready_family` no longer counts culture families.
- `children.architecture` files culture-family kids under `navigation.by_family["single"]`, and
  lists the families only under `planned` (`internal: True`).

d8d80301 merges into INTEG1 with no conflict.

**Repro.** This uses the PR test's own fixture, two certified `sig-aurora` products.

| Reading | fa529381 | d8d80301 |
|---|---|---|
| `bundle_ready` | True | False |
| `navigation.by_family` | `culture:sig-aurora` | `single` only |
| `planned.culture_families` | (absent) | `["culture:sig-aurora"]` |

**Other derivations of a set from a family.** Every reader was checked:
- `children.portfolio.sibling_sets` reads `bundle_ready`, so it is now False.
- `engineering_ops` reads `portfolio_has_bundle_ready_family`.
- `cross_sell.graph`: `related` was already emptied (F-3). `bundles` and `next_projects` come
  from `radar.opportunity.POOL`, whose `family` values are static seed names, never `culture:`.
- `radar.opportunity._check` and `pipeline_board.BUNDLE_FAMILIES` use static seeds.

No path derives a set or bundle from a culture family.

**J-8 INFO.**
- `children.portfolio.sibling_sets` still lists a culture family as an entry, with
  `bundle_ready: False`. The name "sibling set" is slightly misleading, but nothing is derived
  from it.
- A real static family literally named `single` would merge with the singles bucket. There is
  none today.

### Mutations (worktree `f`, each reverted; clean afterwards)

| ID | Mutation | Result |
|---|---|---|
| M8o | culture clause removed from `bundle_ready` | **killed** |
| M8r | the prefix check misspelt (`"culture-"`) | **killed** |
| M8p | navigation groups culture families again | **killed** |
| M8q | `planned.culture_families` emptied | **killed** |

---

## 4. Colourwork: opus2/p0-cir-colourwork fa02cb49 — LIFT HOLD (merge condition J-7)

### I-2 HIGH: fixed at the root

`gates/first_customer.colourwork_findings` no longer returns `[]` at `per_row >= 2`. It judges
every claim it finds with `launch0.technique_backed(hit, colourwork_motif(grid))`, the same
function `fabric_truth` uses. The "at most N colours per row" message is kept only for one-colour
fabric.

Repro (`i2.py`): a joined-round basket with one `sc 1 with rust` in a 12-st round 3, every other
round plain. The listing title is "Overlay Mosaic Intarsia Basket", with tags ("mosaic", "fair
isle", "intarsia").

| Commit | `fabric_truth.backed` | `colourwork_findings` |
|---|---|---|
| f57219d0 | False | **[] (passes)** |
| fa02cb49 | False | **6 findings: mosaic, overlay, intarsia (title); mosaic, fair isle, intarsia (tags) — REFUSED** |

On a real band (rows 3-5, two contrast runs of 2 per row):
- "Tapestry Basket" + tag "tapestry" is backed with 0 findings.
- "Fair Isle Basket" is backed.
- "Overlay Mosaic Intarsia Basket" is still refused for mosaic, overlay and intarsia.

The two gates now agree on every case probed.

### H2-1 to H2-6: no regression

| Finding | Status at fa02cb49 | Evidence |
|---|---|---|
| H2-1 | holds | Token-stitch "Tapestry", "Fair Isle" and "Mosaic" are refused by `fabric_truth`. C10b and C15b (mosaic or intarsia moved to the motif rule) are killed by the h21 test and by the new i2 test. |
| H2-2 | holds | Rows "2 and 4", cut, ends = 6 (h22 test). The carried yardage is now pinned exactly (C19 killed by the new c19 test: 60-st row, rust 1.2 m against 1.0 m without the carry). |
| H2-3 | holds, extended | `COLOUR_ON_NON_STITCH` is an ERROR (C20 killed). A coloured chain now raises `COLOUR_ON_CHAIN` WARNING (I-6; C29 killed). |
| H2-4 | holds | `UNKNOWN_COLOR` fires on an empty table (C21 killed). |
| H2-5 | holds | `BASE_DIGESTS` (11 sha256) still matches. |
| H2-6 | holds | `COLOUR_KEY_UNWRITABLE` fires (C22 killed). |

### I-4 to I-8

**I-4: fixed.**
- A tapestry cut is counted as `tapestry_cuts` / `first_tapestry_cut_row`, with event kind
  `TAPESTRY_CUT`. It is no longer counted in `cut`, `first_cut_row` or `carry_is_possible`.
- `ends` adds `2 * tapestry_cuts`, and the tapestry sentence lists `TAPESTRY_CUT` rows.
- The OPUS2I mixed case (stripes in rows 1-5, tapestry rows 6 and 8) now gives `cut == 0`,
  `carry_is_possible`, `tapestry_cuts == 1` at row 8. The row sentence no longer says "cannot
  be carried" (C27 and C28 killed).
- `certificate.colour_carry_findings` no longer raises `COLOUR_CARRY_IMPOSSIBLE` for a tapestry
  cut. That is correct: the carry note concerns row changes, and the tapestry sentence already
  tells the maker to cut. A tapestry-only piece (`changes == 0`) was silent before and still is.

**I-5: fixed.** The new boundary fixtures isolate one rule each:
- C11 (`MIN_ROWS = 1`), C12 (`MIN_MINORITY_SHARE = 0`), C13 (`MIN_ROW_SHARE = 0`) and C24
  (`MIN_RUN = 1`) are all killed;
- C14 (`all` → `any`) is killed by the "Tapestry Mosaic Basket" case.

**I-6: fixed** (WARNING, as asked).

**I-7: fixed for the run.** `COLOURWORK_MIN_RUN = 2` adjacent contrast stitches. Contiguity of
the motif rows was not added (J-8b below).

**I-8: fixed.** The `moment_candidates.py` and `pipeline_board.py` docstrings are updated.

**`_tapestry` fixture change.** The fixture moved from 1 contrast stitch per 4 to 2 per 4, so
that it still meets the new run rule. This tightens the rule rather than weakening the test. The
writer assertion followed ("sc in next 2 sts with rust"), and a `plain != text` guard was added.

### Launch-0: no digest moves

`dg.py` computed nine values for each of 37 CIRs (11 `launch0.BUILDERS` and 26 buildable
`inventory.universe()` slugs) on **d230e8fd, f57219d0 and fa02cb49**:
- the sha256 of `to_json`;
- `physical.design_digest`;
- `pattern_refs.release_hash_of`;
- the sha256 of `writer.write_pattern`;
- `yarn_metres_by_color`;
- `fabric_truth.backed`;
- the compile ERROR codes;
- the compile WARNING codes;
- the sha256 of the colour-plan instructions.

**All 37 × 9 values are identical across the three commits.** No catalogue CIR gains the new
`COLOUR_ON_CHAIN` warning. `test_physfix` passes 46/46.

### Findings

**J-6 MED (pre-existing; not on this branch, so not a hold reason): spelling variants of a
technique claim bypass both gates on any fabric.** Both gates find claims by substring of
`COLOURWORK_CLAIMS` ("fair isle", "fairisle", "colourwork", "colorwork", …). These pass with no
finding, even on an all-plain one-colour CIR, on INTEG1 6eb3ca0e, f57219d0 and fa02cb49 alike:
- "Fair-Isle Basket" (title), and tag "fair-isle";
- "Colour Work Basket", "Color-Work Basket";
- "Stranded Basket" with tags ("stranded", "jacquard").

`fabric_truth.backed` is True and `colourwork_findings` is [] in each case.

*Fix:* normalise the text before matching. Fold `-`, `_` and repeated spaces to one space,
then match "colour work" and "fair isle". Add "stranded", "jacquard", "two-colour",
"two-color" and "duplicate stitch" as claims (motif-rule or refused). Track this as its own
item. It applies to the INTEG1 base today.

**J-7 MED (integration): fa02cb49 conflicts with INTEG1 in `cir/colour_changes.py`
(`git merge-tree`), and the conflict is semantic, not textual.**
- INTEG1 (PDF1 38909dae, d09a86be) added `rows_by_colour`, `last_row` and
  `rounds_instruction()`.
- INTEG1's `writer.py` uses `rounds_instruction` for joined or spiral rounds, and
  `instruction()` only for turned rows.
- `rounds_instruction` reads only row colours.

So after a naive resolution:
- a tapestry contrast in a **joined-round** piece, which is the I-2 repro's construction, would
  lose its tapestry sentence and its ends in the PDF;
- the fabric gates would still back it.

A trial merge (aborted) shows two conflict hunks in `colour_changes.py`, plus
`COORDINATION.json`.

*Merge condition:* resolve with `rounds_instruction` emitting the tapestry sentence and counting
tapestry colours' ends. Then re-run, on the merged tree:
- `test_opus2_cir_colourwork`;
- the 37 × 9 digest check;
- the INTEG1 PDF1 colour tests.

Get one more review of the resolution.

**J-8b LOW: two mutants survive.**
- **C24c** (`min_contrast_run` = max over rows instead of min) survives. One row with a run of
  2 lets the other motif rows be single dots. *Fix:* a boundary fixture with one row of run 2
  and two rows of run 1.
- **C26b** (only the first claim per text is judged) survives. It is near-equivalent: any one
  unbacked claim still refuses, but the findings under-report. INFO.

Motif rows are still not required to be contiguous (I-7's second half). That is a judgement
call; it is stated.

**Recommendation: LIFT HOLD.** The HIGH that kept the hold (I-2) is fixed at the root and
pinned. H2-1 to H2-6 hold. I-4 and I-5 are fixed with killing tests. No Launch-0 value moves.
- The lift is for the branch content. Merging into INTEG1 needs the J-7 resolution and its
  re-review.
- J-6 is pre-existing and should be fixed on its own track.

### Mutations (worktree `w`, each reverted; clean afterwards)

Run with `PYTHONDONTWRITEBYTECODE=1`. A first pass reported C14 as surviving because of a stale
`.pyc`: `all` → `any` keeps the source size and mtime second. It was re-run clean and is
killed.

| ID | Mutation | Result |
|---|---|---|
| C25 | listing gate `per_row >= 2: return []` restored (the I-2 base) | **killed** (i2 test) |
| C26 | listing gate ignores `technique_backed` | **killed** |
| C26b | first claim per text only | survives (near-equivalent, J-8b) |
| C11 / C12 / C13 / C24 | `MIN_ROWS = 1` / `MIN_MINORITY_SHARE = 0` / `MIN_ROW_SHARE = 0` / `MIN_RUN = 1` | **all killed** (i5/i7 test) |
| C24b | run clause removed from `technique_backed` | **killed** |
| C24c | run = max over rows | survives (J-8b) |
| C14 | `all` → `any` | **killed** (i2 "Tapestry Mosaic Basket") |
| C10b | mosaic/overlay/graphghan moved to the motif rule | **killed** (h21, i2) |
| C15b | intarsia moved to the motif rule | **killed** (h21) |
| (C10, C15 as `claim in ()`) | fall through to "unrecognised → False" | equivalent; discarded, replaced by C10b/C15b |
| C19 | carried yardage removed | **killed** (c19 test) |
| C27 | tapestry cut also counted as a row cut | **killed** (h22, i4) |
| C28 | tapestry cut ends not counted | **killed** (h22) |
| C29 | `COLOUR_ON_CHAIN` removed | **killed** |
| C20 / C21 / C22 | H2-3 / H2-4 / H2-6 checks removed | **all killed** |

---

## 5. Pet bed: opus2/p0-pet-bed d0a7685f — CHANGES_REQUIRED

**The construction is deterministic.** `plan(category="pet", title=…)` routes bed, beds, basket
and nest to `VESSEL`, unless `_PET_BED_NOT_PLAIN` matches. `vessel()` then builds the hexagon
basket at `_pet_bed_size()` = 45 cm across, 10 cm wall.

"Cat Basket Bed" passes every deterministic check:
- compiles with 0 ERROR and 0 WARNING findings;
- `reverse.compare` on the written pattern gives 0 ERRORs;
- the twin builds: forest 179.2 m, cream 68.4 m;
- `fabric_truth`, `assembly_promise` and `title_promise` are backed;
- 168 base sts, 42.8 cm diameter, 44.8 cm across the points / 38.8 cm across the flats, 10 cm
  wall, "Computed, not yet measured".

**No copied competitor content.** The construction is the repository's own hexagon vessel. The
diff adds no text, chart or image from outside.

**No Launch-0 digest moves.** The 37 × 7 values (json, digest, release, text, yarn, fabric,
errors) are identical on 55450fc3 and d0a7685f. Against the merge-base 7746cd46, the values
that exist there (no `design_digest`) are also identical.

**Integration.** d0a7685f sits on 55450fc3, which is 13d67502, so it lacks PR #3's 558e7ca9 and
6d6d83d9 (H1-2, H1-3, I-1).
- It merges cleanly into 6d6d83d9.
- It conflicts with INTEG1 in 18 files, including `runtime/pipeline.py`, `runtime/release.py`,
  `publish/withholding.py` and `test_physfix.py`. These come from the 55450fc3 lineage:
  6d6d83d9 itself merges cleanly into INTEG1.
- It should be restacked on 6d6d83d9 before integration.

### Findings

**J-9 HIGH: the title route has false positives that draft a different object as a basket, and
no gate catches them.** `_PET_BED_WORDS` matches anywhere in the title, and the refusal list
covers padding, shape, size and conjunctions only. The result (`pet.py`, `petroute.py`), with
category `pet` in every case:

| Title | 55450fc3 | d0a7685f | `name_truth` / product-type / `title_promise` on the drafted CIR |
|---|---|---|---|
| Basket Weave Pet Mat | flat_panel | **vessel** (a mat becomes a 45 cm basket) | 0 / 0 / backed |
| Basket Weave Pet Blanket | flat_panel | **vessel** | 0 / 0 / backed |
| Nest Toy, Cat Basket Toy | flat_panel | **vessel** | 0 / 0 / backed |
| **Pet Bed Liner**, Pet Bed Blanket, Pet Bed Mat, Pet Bed Cover, Pet Bed Pad, Dog Bed Topper, Cat Bed Hammock | refused | **vessel** | 0 / 0 / backed |
| Heated Cat Bed, Waterproof Dog Bed, Orthopedic Dog Bed, Window Cat Bed, Raised Edge Cat Bed | refused | **vessel** (an unmade feature claim) | 0 / 0 / backed |
| Pet Bedspread, Bedtime Pet Toy | flat_panel | flat_panel (`\bbed\b` is a whole word: correct) | — |
| Bolster / Cushioned / Donut / Cave / Hooded / Large / XL / "and" / "with" / "&" beds | refused | refused | — |

`product_type_findings` compares the listing's words with the CIR's own title words. A CIR
titled "Pet Bed Blanket" "makes a blanket" by that test. In "Basket Weave Pet Mat", "basket" is
read as the product type. `name_truth` has no form check. So every row above would certify and
list under a name its pattern does not make. That breaks Product Truth (non-negotiable), and the
brief's own example "pet bed liner" is one of the cases.

*Fix:*
- route only when the bed word is the head noun: the last product noun, with nothing but
  species and plain adjectives before it;
- refuse liner, blanket, mat, cover, pad, topper, hammock, toy, heated, waterproof, orthopedic,
  window, raised and "basket weave" by name;
- pin "Pet Bed Liner", "Basket Weave Pet Mat" and "Nest Toy" as not drafted as a vessel.

**J-10 MED: the size claim is implied by the name and never checked.** There is one design size
(45 cm), and the refusal list catches only "large/giant/xl/big". So these all draft the same
45 cm bed and pass every gate:
- "Small Dog Bed", "Medium Dog Bed", "Tiny Kitten Bed", "Mini Cat Bed";
- "Great Dane Bed", "Puppy Bed", "Hamster Bed", "Bird Nest", "Rabbit Basket".

"Dog Bed" at 45 cm makes a fit claim for every dog. The listing states the computed diameter,
but the name still promises fit. *Fix:*
- refuse any size word other than the design size's own;
- refuse a species outside the size's measured range;
- or route `dog` to refusal until a measured dog size exists.

**J-11 MED: the dimensions are invented, not sourced.**
- `_pet_bed_size()` builds `BasketSize("pet_bed", across_cm=45.0, tall_cm=10.0)` inline in
  `fallback_constructions`. It is not in `products.vessels.BASKET_SIZES`.
- It cites no source: no pet measurement, no published bed size, no worked sample.
- The brief requires sizes from `products.vessels` or a measured source.

*Fix:* move the size into `products.vessels` with a cited source for the 45 cm / 10 cm figures
(for example a published cat-bed size range). Otherwise keep the bed refused until one exists.

**J-12 LOW: "Pet Beds" and "Two Cat Beds" draft one bed and read as backed** (the J-1 class:
plural noun, number word). "Cat Beds Set" and "Cat Bed Pair" are caught by the markers.

The N3.2 test change (removing "Cat Bed" from the refused list and asserting VESSEL) is a
behaviour change, not a weakened gate: it still asserts the bed never takes the flat route.

### Mutations (worktree `p`, each reverted; clean afterwards)

| ID | Mutation | Result |
|---|---|---|
| MP1 | "large" dropped from the refusal list | **killed** |
| MP2 | refusal list never matches | **killed** |
| MP3 | design size 45 → 25 cm | **killed** (38-52 cm band) |
| MP4 | wall 10 → 23 cm | **killed** |
| MP5 | bed words route any category | **killed** ("Bed Runner") |
| MP6 | "mat" added to the bed words | **killed** ("Pet Snuggle Mat") |
| MP7 | conjunctions no longer refused | **killed** |

The routing mutants are killed, but the tests pin only the cases the route was designed for.
No test pins a J-9 false positive.

---

## 6. Stocking: opus2/p0-stocking 5c7b984a (merge be12b47b) — CHANGES_REQUIRED

**The construction is deterministic.** It is two identical L-shaped flat panels (`front`,
`back`) worked from the cuff down:
- a 4-row accent cuff band;
- the last leg row chains `extend` for the foot;
- the last 4 rows decrease at both ends;
- a 15-ch hanging loop;
- two whipstitch seams.

"Christmas Stocking" passes every deterministic check:
- compiles with 0 findings;
- `reverse.compare` gives 0 ERRORs;
- the twin builds: forest 48.2 m, cream 3.6 m;
- `assembly_promise`, `title_promise` and `finished_objects == 1` are backed;
- the size note reads "about 14 cm wide at the cuff, 36 cm from cuff to sole and 22 cm from
  heel to toe … Computed, not yet measured".

**No copied competitor content.** This is a generic flat two-panel construction, written from
the repository's own primitives.

**No Launch-0 digest moves.** The 37 × 7 values are identical on 55450fc3, 5c7b984a and
be12b47b, and against 7746cd46 for the values that exist there.

**The be12b47b merge is a clean union of the two `plan()` routes.** The pet-bed check comes
first and needs a bed word, so "Pet Stocking" still drafts a stocking. Suites below.

**Integration.** The same as item 5: the branch sits on 55450fc3. It merges cleanly into
6d6d83d9 and conflicts with INTEG1 in the same 18 files.

### Findings

**J-13 HIGH: the stocking route has false positives in every category, and no gate catches
them.** `plan()` drafts a stocking when either:
- `category == "stocking"`, whatever the title; or
- the title matches `\bstockings?\b` in **any** category not already refused by `NEEDS`.

This runs before any other shaped-category handling. At 55450fc3, every row below was refused or
drafted flat (`stk.py`):

| Category | Title | 5c7b984a and be12b47b | `name_truth` / product-type / `title_promise` / assembly |
|---|---|---|---|
| blanket | **Stocking Stitch Blanket**, Stocking Stitch Throw | **stocking** | 0 / 0 / backed / backed |
| home_decor, scarf | Stocking Stitch Pillow, Stocking Stitch Scarf | **stocking** | 0 / 0 / backed |
| home_decor | Stocking Holder, Stocking Hanger, **Stocking Garland**, Stocking Cuff | **stocking** | 0 / 0 / backed |
| home_decor | Stocking Stuffer Coasters | **stocking** | — |
| bag | Stocking Tote | **stocking** | 0 / 0 / backed |
| accessory | Stocking Cap | **stocking** (a hat) | — |
| stocking | **Snowflake Coaster**, Holiday Ornament, Advent Garland | **stocking** (the title is ignored) | 0 / 0 / backed |
| home_decor | Stockinette Blanket | flat_panel (correct: `\bstockings?\b`) | — |
| ornament, toy, hat, garment | Stocking Ornament, Stocking Stuffer Toy, Stocking Cap, Stockings | refused (category `NEEDS` first) | — |

The brief's own example "stocking stitch" is a false positive. A blanket concept titled
"Stocking Stitch Blanket" would be drafted, certified and listed as a Christmas stocking under a
blanket's name. `product_type_findings` passes because the CIR's own title holds "blanket".

*Fix:*
- route on the title only when "stocking" is the head noun;
- exclude "stocking stitch", "stocking stuffer", "stocking holder/hanger/cap/cuff", and
  stocking + another product noun;
- in category `stocking`, refuse a title that names another product type (or has no stocking
  word);
- pin "Stocking Stitch Blanket", "Stocking Garland" and category `stocking` + "Snowflake
  Coaster" as not drafted.

**J-14 MED: plural, motif and size names pass.**
- **Plurals.** "Fireplace Stockings" and "Nylon Stockings" draft one stocking. `_MULTIPLE_WORDS`
  has no "stockings", and `title_promise` does not read plural nouns (J-1). "Stocking Set",
  "Stocking Pair", "Two Christmas Stockings" and "3 Stockings" are refused.
- **Motifs.** "Nordic Snowflake Stocking" and "Reindeer Stocking" draft a plain stocking with no
  motif, and `name_truth` passes. Its motif check runs only when provenance declares a
  `products.motifs:` motif, and the fallback declares none. The same gap exists for the tote
  fallback ("Reindeer Market Tote" drafts). But `_STOCKING_NOT_PLAIN` already refuses colourwork
  and lettering words and not `launch0.MOTIF_WORDS`, so this route chose to allow them.
- **Size.** "Medium Stocking" drafts at the one design size. "Mini", "tiny", "small", "large",
  "giant", "jumbo", "xl" and "oversized" are refused.

*Fix:* add `stockings` to the multiple words. Refuse `launch0.MOTIF_WORDS` in a fallback title
(or run `motif_promise` on undeclared motifs). Refuse "medium".

**J-15 MED: "Hold the panels wrong sides together" does not fit two identical L-shaped
panels.**
- `back = dataclasses.replace(panel, name="back")`, so the back is the same piece, foot to the
  same side.
- Turning one panel over to bring its wrong side against the other's mirrors it, so the toes
  point in opposite directions.
- The pattern has to make the second panel mirrored, or say to stack the two with the same face
  up.
- The assembly geometry (`seam.is_placed`, perimeter to perimeter) does not model handedness, so
  no deterministic check sees it. A maker following the text literally gets a mismatched seam.

*Fix:* either state "place the back on the front with the same side facing up, edges matching,
and whipstitch around …", or model the back as the mirror (the foot chain worked at the start of
the heel row). Add a handedness check to the assembly geometry when an asymmetric piece is
seamed to a copy of itself.

**J-16 LOW: the dimensions are invented, and the stocking dimensions are not pinned.**
- `STOCKING_LEG_W_CM = 14`, `LEG_L = 26`, `FOOT_L = 22`, `FOOT_H = 10` are inline constants in
  `fallback_constructions`. They have no cited source and are not in `products.vessels` or any
  measured table.
- The note states the computed size, which is honest. But the brief asks for a measured
  source.
- MS6 (leg 26 → 60 cm) **survives** the stocking suite: nothing pins a dimension.

*Fix:* source the figures (for example a published stocking size) in a products table, and pin
the computed size note.

**J-17 INFO.** "Baby's First Stocking" drafts. Whether a children's-word title takes the
children's audience path depends on `launch0.childrens_decision`, outside this diff. It was not
traced further. The integrator should confirm that a fallback-drafted title with a child word
gets an audience assignment.

### Mutations (worktree `s`, each reverted; clean afterwards)

| ID | Mutation | Result |
|---|---|---|
| MS1 | refusal list never matches | **killed** |
| MS2 | multiple-object check removed | **killed** |
| MS3 | hanging loop and its seam dropped | **killed** |
| MS4 | heel chain set to 0 | killed only by a `ValueError` (op count ≥ 1); not a clean mutant |
| MS5 | front/back seam replaced | **killed** (ASSEMBLY finding) |
| MS6 | leg 26 → 60 cm | survives (J-16) |
| MS7 | "medium" added to the refusal list | survives (fail-closed direction; J-14) |
| MS8 | title routing removed (category only) | **killed**: the test pins cross-category title routing ("seasonal" "Fireside Stocking") as intended, which is the J-13 root |

---

## Test table

The suites were run from `brambleloop/` on each branch's worktree, as
`PYTHONPATH=src:tests python3 tests/<f>.py`, after `pip install -r requirements.txt`.
`run_tests.sh` was not run. "ok" counts the `OK`/`PASS` lines.

Each worktree's suites ran one at a time. However, the PR #7 batch and the PR #8 batch ran at
the same time in two separate worktrees, each with its own temporary DBs. The colourwork batch
and the item 5/6 batches each ran alone, and items 5/6 ran strictly one after another. Every
suite exited 0.

| Item | Commit | Suite | Result |
|---|---|---|---|
| #3 | 6d6d83d9 | test_opus2_draft_constructions | 19 OK, 0 failed, exit 0 |
| #3 | 6d6d83d9 | test_launch0 | 52 OK, exit 0 |
| #3 | 6d6d83d9 | test_w4_pipe_board | 70 OK, exit 0 |
| #3 | 6d6d83d9 | test_opus2_size_claims | 13 OK, exit 0 |
| #3 | 6d6d83d9 | test_first_customer_gate | 12 passing, exit 0 |
| #3 | 6d6d83d9 | test_compiler / test_twin / test_reverse / test_vacuity | 9 / 8 / 18 / 8 OK, exit 0 |
| #7 | 7c3806fc | test_opus2_culture_sweep_timeout | 5 OK, exit 0 |
| #7 | 7c3806fc | test_culture / test_culture_feed | 26 / 24 OK, exit 0 |
| #7 | 7c3806fc | test_w3_spend_paid_calls | 9 OK + PASS, exit 0 |
| #7 | 7c3806fc | test_w4_close5_vision_timeout | 5 (4 + PASS), exit 0 |
| #7 | 7c3806fc | test_w3_spend_hygiene | 7 OK + PASS, exit 0 |
| #7 | 7c3806fc | test_vacuity / test_w4_fmbatch1_retention_guard | 8 / 5 OK, exit 0 |
| #8 | d8d80301 | test_opus2_family_membership | 5 OK, exit 0 |
| #8 | d8d80301 | test_w4_c3 / test_w4_children | 4 / 6 OK, exit 0 |
| #8 | d8d80301 | test_vacuity / test_w4_fmbatch1_retention_guard | 8 / 5 OK, exit 0 |
| colourwork | fa02cb49 | test_opus2_cir_colourwork | 15 OK, exit 0 |
| colourwork | fa02cb49 | test_compiler / test_twin / test_reverse / test_vacuity | 9 / 8 / 18 / 8 OK, exit 0 |
| colourwork | fa02cb49 | test_pattern_truth / test_launch0 / test_leadtime | 11 / 52 / 21 OK, exit 0 |
| colourwork | fa02cb49 | test_first_customer_gate | 12 passing, exit 0 |
| colourwork | fa02cb49 | test_physfix | 46/46, exit 0 |
| pet bed | d0a7685f | test_opus2_pet_bed | 3 OK, exit 0 |
| pet bed | d0a7685f | test_opus2_draft_constructions / test_fallback_draft_provenance / test_opus2_knowledge_gaps | 18 / 1 / 9 OK, exit 0 |
| pet bed | d0a7685f | test_w4_listready / test_w4_auto_status | 31 / 12 OK, exit 0 |
| pet bed | d0a7685f | test_compiler / test_twin / test_reverse / test_vacuity / test_launch0 | 9 / 8 / 18 / 8 / 52 OK, exit 0 |
| stocking | 5c7b984a | test_opus2_stocking | 3 OK, exit 0 |
| stocking | 5c7b984a | test_opus2_draft_constructions / test_fallback_draft_provenance / test_opus2_knowledge_gaps | 18 / 1 / 9 OK, exit 0 |
| stocking | 5c7b984a | test_w4_listready / test_w4_auto_status | 31 / 12 OK, exit 0 |
| stocking | 5c7b984a | test_compiler / test_twin / test_reverse / test_vacuity / test_launch0 | 9 / 8 / 18 / 8 / 52 OK, exit 0 |
| merge | be12b47b | test_opus2_pet_bed / test_opus2_stocking | 3 / 3 OK, exit 0 |
| merge | be12b47b | test_opus2_draft_constructions / test_fallback_draft_provenance / test_opus2_knowledge_gaps | 18 / 1 / 9 OK, exit 0 |
| merge | be12b47b | test_w4_listready / test_w4_auto_status | 31 / 12 OK, exit 0 |
| merge | be12b47b | test_compiler / test_twin / test_reverse / test_vacuity / test_launch0 | 9 / 8 / 18 / 8 / 52 OK, exit 0 |

`test_physfix` does not exist on 6d6d83d9, so it was not run for #3.

## Probe scripts

These are in the reviewer's session scratchpad and were not committed:
- `tp.py`, `tpu.py` (#3);
- `c4.py`, `c4b.py` (#7);
- `i2.py`, `dg.py` (colourwork; `dg.py` and `dg2.py` also for items 5/6);
- `pet.py`, `pet2.py`, `petroute.py` (#5);
- `stk.py`, `stk2.py` (#6).

Each uses only the repository's public functions on the named commit, with no network and no
database outside a temporary SQLite file.
