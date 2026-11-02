# INDEPENDENT REVIEW INTEG5F — claude/w5-INTEG1 4af3418f..50937469

Reviewer: independent, read-only. Date: 2026-11-02 (UTC). Scratch worktree detached at
50937469efcf6233d50e7c7416bbff6207fe515a, left clean, removed when the review finished. Nothing was modified, deployed, published or spent, and Railway was not touched.

## Verdict: SHIP (certification of 50937469)

No blocking, HIGH or MEDIUM findings. Every check asked for was run and passed. No result was
UNKNOWN.

## Findings

| ID | Severity | Finding | Repro |
|---|---|---|---|
| INTEG5F-1 | INFO | Band choices in 30b04b35 are sensible. `chain.successors` re-drives `pricing.position` / `assets.build` dead ends, which are both proven_winner, so proven_winner fits. truth_defect (its neighbour `chain.rebuild`) would also have been defensible, but its dead ends are unpublished stage refusals, not false published claims, so proven_winner is right. `listing.package` sits beside `listing.draft`/`listing.seo` (proven_winner). `intel.scan_evidence` is a read-only reading over competitor scans, the same family as `intel.benchmark_*` and `mjs.scan` (benchmark_change). `improve.commercial_lessons` and `learning.knowledge_gaps` are learning with no committed value (exploration, like `improve.*` and `learn.scan`). All five handlers were inspected. | `git show 30b04b35`; runtime/chain_successors.py, listing_package_ops.py, evidence_ops.py |
| INTEG5F-2 | INFO | No runnable job type is unbanded. 169 registered handlers, 0 not in JOB_BANDS, and test_swarm_runtime 10 OK / 0 FAIL. | runtime import check (below) |
| INTEG5F-3 | INFO | 45977d4c is exactly the reviewed stocking delta. The +/- lines of `git diff d3a485a1 7493c723 -- brambleloop/src brambleloop/tests` and `git diff 30b04b35 45977d4c -- same` are identical. Only the blob index and hunk line offsets differ. Same 2 files, 62+/8-. | `diff <(grep '^[-+]' d1) <(grep '^[-+]' d2)` → SAME |
| INTEG5F-4 | INFO | Merge 50937469 auto-merged cleanly. `git show --remerge-diff 50937469` has no diff body (header only, 13 lines). The merge delta is 9 files, 400+/5-: assembly.openings_cm repeat flattening, writer stuffed-finishing branch, the pouch route/builder, the pipeline POUCH branch, the tapestry OPUS2P-9 round notes, tests and COORDINATION.json. | `git show --remerge-diff 50937469`; `git diff --stat 45977d4c 50937469` |
| INTEG5F-5 | INFO | No amigurumi toy route, builder, constant or test came in. The only added line matching amigurumi/bear/bunny/plush/teddy in src is the comment `# OPUS2 (amigurumi): a stuffed, closed piece is never blocked` in cir/writer.py. Counts go from 135 to 136 (that comment), and whole-word `bear` stays at 5. No amigurumi test file exists, and `origin/opus2/p0-amigurumi` remains separate. A title like "Amigurumi Bear Drawstring Bag" is refused. | `git diff 4af3418f HEAD -- src \| grep '^+' \| grep -iE ...` |
| INTEG5F-6 | INFO | Exactly one `def fold_title` (creative/fallback_constructions.py:32). The AST scan for duplicate top-level defs/assigns and duplicate dict-literal keys across src finds only 2 entries, and both are identical at 4af3418f (pre-existing): `visual/drape.py` dict key `support_friction` and `brand/storefront.py` `ABOUT` assigned 3x. `handlers.register` duplicates (assets.build, launch.plan, pricing.position) are pre-existing deliberate successor wrappers (release.py:9797) and identical at base. CADENCES has no duplicate names. JOB_BANDS and WORK_KEYS have no duplicate keys. | dupcheck.py at head vs base |
| INTEG5F-7 | INFO | autonomy_map.json equals a fresh regeneration once `generated_at` is ignored. | `PYTHONPATH=src python -m brambleloop.autonomy.map --write <scratch>/amap_regen.json`, then a JSON compare |
| INTEG5F-8 | INFO | `retention.unknown_read_actions()` returns `[]`. | runtime import check |
| INTEG5F-9 | INFO | Launch-0 pattern text is byte-identical between 4af3418f and 50937469. This covers all 11 builders (BUILDERS + PROPOSED_BUILDERS) through `write_pattern(cir, compile_cir(cir))`, and none of them has `stuff_before_closing`. `assembly.openings_cm` is also identical for every Launch-0 component. | l0dump.py / l0open.py at base vs head, `cmp` → IDENTICAL |
| INTEG5F-10 | INFO (intended change) | Outside Launch-0, the writer change alters the Finishing text of exactly 2 of 26 engineered inventory pieces, `heart-row-ring-pillow` and `spring-garden-kneeler` (both stuffed). The "damp-finish standing up" or "pin it out damp" line and the "Check the ball band before blocking" line become "This piece is stuffed and closed, so it is not blocked...". This is the intended OPUS2P-8 fix. Neither slug appears in release/, baseline/ or evidence/. If either has a stored artefact in production, the normal chain staleness path will rebuild it. | invdump.py diff |
| INTEG5F-11 | INFO | The new drawstring route is conservative. Titles that refused before and now draft are "Drawstring Bag", "Drawstring Pouch" and "Drawstring Gift Pouch". Tote, backpack, plural/set, "Mini", "for Dice", "with Drawstring" and toy-category titles still refuse. No title that drafted at base now drafts differently. | route.py at base vs head |

## Suite results (run one at a time from the worktree's brambleloop/, `PYTHONPATH=src:tests /home/user/bl-runs/venv-integ4/bin/python tests/<suite>.py`)

| Suite | Exit | OK | FAIL/ERROR |
|---|---|---|---|
| test_swarm_runtime | 0 | 10 | 0 |
| test_opus2_drawstring_pouch | 0 | 4 | 0 |
| test_opus2_stuffed_finishing | 0 | 1 | 0 |
| test_opus2_stocking | 0 | 9 | 0 |
| test_opus2_tapestry_basket | 0 | 7 | 0 |
| test_opus2_draft_constructions | 0 | 18 | 0 |
| test_launch0 | 0 | 52 | 0 |
| test_pdf_premium (once) | 0 | 27 | 0 |
| test_vacuity | 0 | 8 | 0 |

## Commands (summary)

- `git fetch origin`; `git worktree add --detach <scratch>/integ5f 50937469`
- `git show 30b04b35`; I read the BANDS/JOB_BANDS sections of swarm/orchestrate.py and the five handlers.
- `git diff d3a485a1 7493c723 -- brambleloop/src brambleloop/tests` vs `git diff 30b04b35 45977d4c -- ...`
- `git show --remerge-diff 50937469`; `git diff 45977d4c 50937469`
- An AST duplicate scan (top-level names and dict-literal keys) at head and at `git archive 4af3418f`.
- A runtime import check of CADENCES, the handler registry vs JOB_BANDS, and `retention.unknown_read_actions()`.
- The autonomy map regenerated to scratch and compared with the timestamp ignored.
- Launch-0 writer and openings dumps, an engineered-inventory writer dump, and a routing table, each at base (git archive 4af3418f) and at head.
- The nine suites above, one at a time.
