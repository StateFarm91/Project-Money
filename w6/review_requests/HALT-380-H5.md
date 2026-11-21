VERDICT: H5 REFUTED AS STATED. A rebuild of an UNPROVEN graduated key does read fresh once the stage writes that exact key, and production's numbers leave about zero UNPROVEN-blocking incidents. A DIFFERENT sentinel/rebuild disagreement is CONFIRMED IN CODE AND FIXED: orphan `visual_truth` rows of deleted gallery frames read STALE forever. That production's 111 STALE rows are these orphans is INFERRED, not observed.

# Review request: eng/halt-380-h5

**Branch:** `eng/halt-380-h5`, cut from `claude/w6-release-19h1` (90403e5; deployed 1bb7c4f5,
which carries H3 and H4).
- Not merged, not deployed, no PR. Production is unchanged.
- No production row was read. No operator token was used and no Railway variable value was read.

**Input:** the 08:20Z readback in the brief:
- `sentinel_stale_artefacts` 111 of 600 checked;
- `open_stale_artefact_incidents` 112 across 12 products, the oldest 1487 h old;
- `rebuilds_already_fresh_7d` 874 against `rebuilds_verified_7d` 8;
- `chain.rebuild` done 199, `retry_waiting` 14.

## 1. H5 as stated: refuted

Test suite: `tests/test_halt_380_h5.py`, production-shaped. It has a graduated `visual_truth`
class, a frame that exists with no provenance row, and a rebuild followed by verify.

- **The stage writes the exact key.** `test_h5_literal_…` passes on base. Both sides treat the
  absent key as not fresh:
  - The sentinel reads it UNPROVEN, and blocking, because the class is graduated.
  - The rebuild does not find it in its verdicts, so it lands in `stale`.

  The rebuild enqueues `assets.build`, and the stage writes that exact `class:key`. The verify
  pass binds the row to the stage job, and `_close_on_verified_rebuild` closes the incident.
  Missing `expected` in `_targeted_rebuild` does not, by itself, stop a cure.
- **Every real stage writes the keys `expected_from_db` enumerates.** A full real-chain build of
  `cloudline-baby-blanket` (`cir.compile` through `listing.package`) was checked against
  `check(expected=expected_from_db)`. All 28 artefacts read FRESH: 0 UNPROVEN, 0 wrong keys, and
  no class without a row. This was an exploratory run, not committed.
- **The stage does not write the key.** `test_h5_a_stage_that_never_writes_…` passes on base and
  on the branch. The key stays UNPROVEN and blocking, and the attempt ends in a bounded
  `rebuild-incomplete` row. Absence never passes as current.
- **Production numbers.** `sentinel_stale_artefacts` is the count of **STALE** verdicts: rows
  that exist and whose inputs moved. `open_stale_artefact_incidents` counts every
  `stale-artefact:%` row, which includes the non-halting `stale-artefact:backlog` counter.
  - 111 STALE verdicts each hold their own row.
  - So 112 is 111 STALE-backed rows plus, most likely, the backlog counter.
  - That leaves about zero incidents that are UNPROVEN-in-a-graduated-class. H5 cannot be what
    holds 112 open.

### Related gap found on H5's path: fixed

The sentinel's propagation is driven only by STALE moved refs. A blocking UNPROVEN key, with
nothing stale, therefore **got no rebuild request at all**, and its incident waited for good.
`test_h5_unproven_blocking_key_gets_a_rebuild` fails on base.

The sentinel now requests one targeted `chain.rebuild` per product per day for exactly those
keys:
- key: `rebuild:unproven:<slug>:<date>`;
- held by the same `retry_hold_reason` as the daily retry;
- reported as `rebuild_unproven_requested`.

## 2. `already_fresh` keys and the sweep's close: refuted

`test_already_fresh_keys_close_on_the_next_sweep` passes on base. A key the rebuild reports
`already_fresh` reads FRESH from the same row, against the same `current_from_db`, so the
sweep's `fresh_signatures` closes its incident on the next pass. The close conditions do not
differ.

874 `already_fresh` against 8 verified is noise from the per-product rebuild set. It names
every artefact of the product whose input moved, and most are already fresh. It is not a set of
incidents the sweep fails to close.

## 3. The disagreement that does exist: orphan rows, confirmed and fixed

The gallery rebuild (`runtime/release.py`, review 6817652112 N2) **deletes** `ListingAsset`
rows beyond the rebuilt set. Their `visual_truth:<slug>@<v>#<ListingAsset.id>` provenance rows
stay. Once the chain or the design moves, each such row:

- reads **STALE**, because the row-side loop of `check` never asks whether the artefact still
  exists;
- raises a halting `stale-artefact` incident;
- is re-requested by every rebuild. The stage writes only the frames that exist, so the row is
  never rewritten. Each attempt ends in `rebuild-incomplete` and then a hold;
- keeps `rebuild_graph.publication_gate` refusing the product, because it reads the orphan as an
  outstanding descendant.

That is a permanent halt nothing can cure, with exactly the production signature: STALE-backed,
old, and per product. `test_orphan_…` and `test_a_held_rebuild_incomplete_row_naming_an_orphan_closes`
both fail on base.

### Fix: one shared verdict

**`ops/artefacts.standing(db)`** is THE reading: `current_from_db`, `expected_from_db`, and
`check(..., retire_orphans=True)`. It is used by:
- `handle_stale_artefact_sentinel`: the sweep, graduation and the rebuild-incomplete judge;
- `_targeted_rebuild`, which previously ran `check(current=…)` without the estate;
- `rebuild_graph.publication_gate`, which takes the same full-estate check and leaves retired
  nodes out of `outstanding`.

`test_the_rebuild_and_the_sentinel_read_one_verdict` checks that on a mixed estate the
rebuild's requested, already-fresh and retired sets are exactly the sentinel's. It fails on
base.

### The orphan rule is narrow and never silent

- **Class:** it applies only to the `ORPHAN_KEY` classes. Today that is `visual_truth` alone,
  keyed `<slug>@<version>#<int>`. All three writers key by `ListingAsset.id`:
  - `assets.build`
  - `visual.gallery_persist`
  - `publish.physical_upgrade`
- **Excluded classes:**
  - `marketing_asset`: it holds video rows that are not ContentPieces.
  - `pdf` and `chart`: they are enumerated from DONE jobs, so a row from a running job would
    look orphaned.
  - Any other key shape.
- **Estate:** it applies only with the full estate (`standing`). `check` without `expected`
  never retires an orphan. `test_guard_orphan_rule_is_narrow` covers this.
- **Reason recorded:** the row is retired with the reason "the artefact this row describes no
  longer exists: no visual_truth `<slug>@<v>` frame #N is on file…". The sweep closes the
  incident as "retired, not stale: …".
- **Rebuild:** a retired key is set aside before stage selection, audited as
  `chain.rebuild_retired` with each reason, and returned as `retired`. It is never requested
  and never outstanding.
- **rebuild-incomplete judge:** retired names are set aside with the sweep's reason and recorded
  in `detail.retired_names`, the same treatment as H3's obsolete-release names. The row is then
  judged on what remains, by the same positive-evidence rule.

### The graduation gate's intent is kept

- An artefact that **exists** with no row is still UNPROVEN and still blocks in a graduated
  class.
- A stale row of an existing frame still blocks the sentinel and `publication_gate`
  (`test_guard_a_stale_row_of_an_existing_frame_still_blocks`).
- Retirement applies only where the artefact itself is gone.
- Unchanged:
  - thresholds;
  - `release_gates`;
  - budgets, spend, the kill switch and grants;
  - the verify binding rule.

## Honest limits

- **The 111 rows are not observed to be orphans.** The orphan mechanism is proved in code. That
  production's 111 STALE rows are orphans is inferred from their shape. This readback decides it:
  1. Take the STALE verdicts in `ops.sentinel`'s latest sweep.
  2. Count those with class `visual_truth` whose `#<id>` is not in `listing_assets`.
- **After deploy,** the first sentinel's cleared incidents carry the resolution "retired, not
  stale: the artefact this row describes no longer exists". The detail's `retired` field counts
  every retired verdict, and `chain.rebuild_retired` audits list what rebuilds set aside.
- **If few of the 111 clear,** the rest are STALE rows of artefacts that exist. Their next
  suspects:
  - a recorded ref with no current fingerprint (`unknown`, for example a removed
    `asset:image_candidate_*`);
  - a ref the stage's `design_inputs` does not rewrite.

  Read `verdicts[].unknown` for those keys.
- **A second orphan source, seen and not fixed:** a ContentPiece whose re-draft gets a new title
  leaves the old piece and its row. The piece still exists, so retiring it would hide stale
  content. It is not done here.
- **Engine:** SQLite only. The Postgres half of `test_eng_stale_rebuild_loop` is skipped because
  there is no local toolchain.

## Suites run (this branch, SQLite)

Every suite below was run on the final code. The three suites that had started before the last
edit (`test_eng_stale_rebuild_loop`, `test_cert_rebuild_chain`, `test_provenance_write_path`)
were run again after it.

**New suite:** `test_halt_380_h5` 9/9. On base, 6 of the 9 fail:
- `unproven_blocking_key_gets_a_rebuild`
- `orphan_…`
- `held_rebuild_incomplete_row_naming_an_orphan_closes`
- `guard_a_stale_row_…`: it asserts that the orphan is not counted.
- `guard_orphan_rule_is_narrow`
- `rebuild_and_sentinel_read_one_verdict`

The 3 that pass on base are the refutations: `h5_literal`, `h5_stage_never_writes` and
`already_fresh`.

**Required suites, all passing:**
- `test_publish_unhalt`
- `test_eng_stale_rebuild_loop`: 20 OK. Its Postgres half was skipped: no toolchain.
- `test_cert_rebuild_chain`: 10 OK.
- `test_halt_380_h3`
- `test_vacuity`: 8 OK.

**Provenance and graduation suites, all passing:**
- `test_provenance`
- `test_cert_provenance`
- `test_w4_provenance`
- `test_provenance_backfill`
- `test_provenance_write_path`: 19 OK.
- `test_l0_physical_upgrade_provenance`
- `test_w4_auto_provenance_concurrency`
- `test_fallback_draft_provenance`
- `test_author_provenance`
- `test_ws5_e4_evidence_provenance`
- `test_w3_priv_provenance`
- `test_w3_laura_memory_provenance`
- `test_artefacts`

**Rebuild-graph and publication-gate callers, all passing:**
- `test_rebuild_graph`
- `test_eng_halt_380`
- `test_halt380_h4_rebuild_drain`
- `test_eng_recovery`
- `test_eng_stale_round2`
- `test_w4_listready`
- `test_w4_prodfix`
- `test_w4_fmgate_rebuild_key`
- `test_eng_catalogue`
- `test_originality_runtime`
- `test_w4_fidelity`
- `test_w4_finhealth`
- `test_w4_visnext`
- `test_w4_resume_runner`: the new suite is declared in `scripts/suite_final_segment.txt`.

**Core suites, all passing:** `test_compiler`, `test_reverse`, `test_twin`.

**One failure, pre-existing:** `test_w4_autonomy_idle_departments::test_a_wide_rebuild_fits_the_varchar_200_key_column`
fails identically on the base worktree. It expects 14 enqueued products, and 12 are enqueued
because the two retired legacy-duplicate slugs are never planned. This change did not touch it.
