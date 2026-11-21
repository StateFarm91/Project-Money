VERDICT: CAUSE REPRODUCED ON THE REAL CHAIN AND FIXED. A provenance row whose artefact no longer exists reads STALE for good. No stage can rewrite it, and when it is not marketing content it also makes `marketing.schedule` refuse the product's real marketing rebuild. A second defect is fixed too: a refusal by a real gate is now parked with its reason instead of counting as systemic staleness. Production rows were NOT read. That production holds orphans of this shape is inferred from the readback, not observed; the post-deploy check below settles it.

# Review request: eng/halt-380-verify

**Branch:** `eng/halt-380-verify`, cut from `claude/w6-release-19h1` (90403e5, which records the
deployed 1bb7c4f5). There was no earlier partial branch; the dead session left nothing on origin.
Not merged, not deployed, no PR. Production is unchanged. Main deploys only with the owner's
per-SHA approval.

**Evidence basis.** The readback figures in the brief (08:20Z, 1bb7c4f5) and the code. I read
no production rows, no token-gated readback and no Railway variable values. Railway deploy
logs carry only HTTP access lines, so they say nothing about jobs. Every finding below is a
code fact, reproduced on the real handlers.

## What production shows, and what it implies

- `chain.rebuild` 7 d: done 199, unfinished 0. Every attempt ran to the end.
- `rebuilds_verified_24h` is 8, the newest at 2026-11-20T13:12Z. This metric counts
  per-artefact `chain.rebuild_completed` rows. So after 13:12Z no verify pass completed a
  single artefact, while attempts kept running.
- 14 products are retry-waiting and 12 are `rebuild-incomplete`. Attempts end, fail verify and
  wait out RETRY_AFTER.

So the stages run, and on the second and later attempts they rewrite nothing the verify pass
asks for. That is the signature of names no stage can produce.

## Reproduction (real chain: cir.compile → … → marketing.schedule, real ops.sentinel and chain.rebuild)

Clean-slate rebuilds verify on the first check for every product tried: spooky-garland,
valentine-heart-garland, nordic-star-ornaments (launch held, evergreen pivot) and
harvest-table-runner. They do so even with the systemic halt open. So the failure needs state
that production products carry. I added the two kinds of orphan the code itself creates,
recorded under the pre-move chain fingerprint:

1. A `visual_truth` row for a gallery frame that no longer exists. `_persist_frames` deletes
   the ListingAsset rows a rebuild did not place (review 6817652112 N2) and leaves their
   provenance rows behind, keyed by the deleted row id.
2. A `marketing_asset` row for a draft from an earlier content plan: an earlier title,
   estimate, collection or positioning. ContentPiece rows are never deleted, and the
   provenance key is the title's hash.

On the base, check 1 completes 15 artefacts (PDFs, charts, copy, frames) and leaves 10
outstanding. Those 10 are the 2 orphans plus **all 8 real marketing pieces**. The 8 are
outstanding because `marketing.schedule` was refused with "rebuild outstanding (#172)": the
non-marketing orphan made `only_own_marketing_stale` false. Checks 2 and 3 complete 0. So does
the daily retry, with the same 10 outstanding. `rebuild-incomplete` opens with
`refused_by: halted (#173) … rebuild outstanding (#172)`, which is the product's own staleness.
This matches production's "8, then none".

| Brief candidate | Finding |
|---|---|
| Stage refused: certification, a withheld release, the premium PDF standard, child safety | Not what the reproduction shows. Those refusals end the chain early, but they do not explain the clean-slate products verifying. They are handled separately below (parking). |
| Stage does not produce the expected fingerprint | **The cause.** For a name whose artefact no longer exists, no stage can ever produce one. Every name that does exist is rewritten and binds. |
| Verify window or lease | Not a cause. The reproduction drains to completion, and H4's drain already refutes starvation. |

## Fixes

1. **`ops/artefacts.check`: vanished artefacts read RETIRED.** This applies only to a row that
   would otherwise read STALE, in one of two cases:
   - a `visual_truth` key `slug@version#id` whose ListingAsset row is gone;
   - a `marketing_asset` key `slug:channel:digest` whose ContentPiece exists and is
     `superseded`.

   Everything else fails closed and stays as it reads: a frame that exists, a draft still in
   the plan, content in any non-draft state, a title no piece carries (absence proves
   nothing), another slug's key, a video module key, any other class and any unreadable table.
   A FRESH row is never retired. RETIRED is the existing verdict (`retired()`), so the
   sentinel's existing rule closes the row as "retired, not stale".
2. **`marketing.schedule` supersedes drafts its current plan no longer contains.** This applies
   to drafts only. Each superseded piece records `superseded_by` (job, version, time), and its
   audit lists `superseded_drafts`. Nothing is deleted.
3. **The verify pass (`_targeted_rebuild`)** sets retired names aside and records them under
   `retired`. It never counts them as completed. A pass that completed nothing and only set
   names aside closes nothing: the row is left to the sentinel's positive-evidence rule. The
   verify audit also gains `outstanding_read`, which records why each outstanding name is
   still outstanding.
4. **The sentinel's rebuild-incomplete judgement** sets retired names aside exactly as H3 does
   for obsolete-release names. The rest is then judged by the same positive-evidence rule
   (at least one name, FRESH or SUPERSEDED, nothing STALE).
5. **`rebuild_graph.publication_gate`** no longer counts a retired node as an outstanding
   descendant.
6. **Parking on a real gate.** When a verify pass gives up, `_rebuild_incomplete` reads the
   newest refusal written by this attempt's own chain (audit `job_id >= requested_by`). The
   gates it reads are:
   - `gate.blocked`, `gate.release_withheld` and `chain.rebuild_refused`;
   - `assets.listing_images_blocked`, `pricing.refused` and `listing.seo_blocked`;
   - `launch.held`, unless the evergreen pivot was queued;
   - `childrens.decision_required`;
   - `marketing.blocked`, only for a reason other than the product's own #173/#172 staleness.

   If it finds one, the row carries `parked {gate, reasons, job, audit_id, at}` and the held
   text names the gate. `incident_lifecycle.systemic_evidence` does not count a parked
   product toward the staleness families (`stale-artefact`, `rebuild-incomplete`) and
   reports `parked_on_a_gate`. The product stays halted: its rows stay open and halting, and
   `publication_halted` and `release_gates.staleness` still refuse it. An integrity failure is
   systemic whatever is parked. A later attempt refused by no gate un-parks the product. An
   attempt with no `requested_by` (legacy) never parks.

**Not touched:**
- the binding rule;
- REBUILD_MAX_ATTEMPTS, RETRY_AFTER, REBUILD_VERIFY_ATTEMPTS and the verify delay;
- the systemic rule's thresholds (3 products and 50%) and its denominator;
- `release_gates`' publish path, the kill switch, budgets and grants;
- child safety (a children's hold still halts the product; it is only named as a park);
- the premium PDF standard and every certification gate.

No test was weakened or skipped.

## Readback evidence: GET /api/readback/evidence ~45 s

- **Measured, not assumed.** On a real chain-built SQLite DB, `factory_visibility` takes
  47 ms and 12 × `sale_admission` takes 39 ms, about 100 indexed queries (every table it reads
  is indexed on the column it filters). At Postgres round-trip latency that is well under a
  second. **parked_admission is unlikely to be the 45 s by itself.** It is UNVERIFIED what is.
- **Made cheaper anyway, with no information lost:**
  - each distinct release's admission is read once, however many parked runs share it;
  - parked runs and `image_runs_by_state` select columns, not whole rows (the stage, card and
    decision JSON were loaded and dropped);
  - the report is unchanged: one entry per run, the same fields, the first 12;
  - it adds `parked_runs` (the total) and `parked_admission_ms`.
- **The endpoint now names the slow part.** The body gains `timing_ms` (whole milliseconds per
  fixed section name, sorted slowest first). The next readback reads it instead of guessing.

## Tests

New suite: `tests/test_halt_380_verify.py`, 4 tests, all passing. On the base (fix stashed),
3 fail and 1 passes by design:

- **Production shape, real chain.** One of production's twelve (cloudline-baby-blanket,
  evergreen, so it needs no launch window) is built on the real chain. Both orphans are added
  under the old chain, then the chain moves. With the fix:
  - the first attempt verifies on check 1 with nothing outstanding;
  - every real marketing piece is completed, and `marketing.schedule` is never refused;
  - the orphans are set aside as retired and the draft is `superseded`;
  - no `rebuild-incomplete` row opens, and the next sentinel reads 0 stale, enqueues nothing
    and closes the draft's row as "retired, not stale";
  - `publication_gate` has nothing outstanding.

  On the base, 10 stay outstanding across all 3 checks, as described above. (The base run
  used valentine-heart-garland. The test then switched to the evergreen slug so it does not
  depend on the calendar. It passed 4/4 on both slugs with the fix.)
- **The rule is narrow** (table of 10 key cases above). Fails on base: the constant does not
  exist.
- **Parking:**
  - an image-gate refusal, a held launch and a child-safety decision each park their product
    with the gate's reason;
  - the product's own #173/#172 marketing refusal does not park, and neither does an older
    attempt's refusal;
  - no systemic halt is opened, and every parked product is still halted;
  - an integrity failure is still systemic;
  - a clean later attempt un-parks.

  Fails on base: there is no `parked`.
- **Guard:** a held launch whose evergreen pivot was queued, and an attempt without identity,
  never park. Passes both ways by design.

Also added: `tests/test_factory_visibility.py::test_parked_admission_reads_each_release_once_and_the_evidence_is_timed`.
The new suite is declared in `scripts/suite_final_segment.txt`, because the real chain reads
today.

Suites run on this branch (SQLite; dirty tree, so not release-eligible) are listed in the commit
message and below.

Final tree, SQLite, each suite run directly (`python3 tests/<suite>.py`). The tree was dirty,
so this is not a release-eligible runner record.

**Passing (29 suites):**
- New and changed: `test_halt_380_verify` (4/4), `test_factory_visibility` (2/2).
- Named in the brief: `test_publish_unhalt`, `test_eng_stale_rebuild_loop`,
  `test_cert_rebuild_chain`, `test_halt_380_h3`, `test_vacuity`.
- Earlier HALT-380 suites: `test_eng_halt_380`, `test_halt380_h4_rebuild_drain`.
- Readback, artefacts and recovery: `test_w4_readback_evidence` (23/23), `test_artefacts`,
  `test_rebuild_graph`, `test_eng_recovery`, `test_eng_stale_round2`.
- Provenance: `test_provenance_backfill`, `test_provenance_write_path`,
  `test_l0_physical_upgrade_provenance`.
- Chain and publication: `test_w6_listing_chain_e2e` (6/6), `test_w6_fix_only_rebuild`,
  `test_w4_fmgate_rebuild_key`, `test_cert_publish_gates`, `test_w4_listready`,
  `test_w4_prodfix`, `test_w4_learn_loops`, `test_estimate_claims` (9/9),
  `test_w4_resume_runner`.
- Core: `test_compiler`, `test_reverse`, `test_twin`.

**Failing (1 suite):** `test_w4_autonomy_idle_departments::test_a_wide_rebuild_fits_the_varchar_200_key_column`.
It is pre-existing and identical to the failure recorded in HALT-380.md: the test expects 14
enqueued, and PUBLISH-UNHALT U2 skips the 2 retired slugs. It is not fixed here.

**Not run here:** the PostgreSQL halves. No local toolchain exists, so those suites skip them.

## Post-deploy readback check (inferred vs observed)

- The first `ops.sentinel` after deploy should close stale-artefact rows with "retired, not
  stale" for dropped frames. Superseded drafts close after each product's next marketing
  rebuild.
- On each product's next attempt (RETRY_AFTER, about 16:30Z), `chain.rebuild_verified` should
  carry `retired` and an empty `outstanding`, and `rebuilds_verified_24h` should rise
  (marketing pieces completing).
- **If it does not:** the new `outstanding_read` names what each outstanding artefact reads,
  and `parked` names any gate. Either one is the next defect, and it is visible on the row.
- `systemic_evidence.parked_on_a_gate` lists products held by a real gate. Those are owner or
  department work, not rebuild defects.
- `timing_ms` names the slow evidence section.

## Open

1. **`gate.certify` refuses on any open halting incident of the product**
   (`publication_halted`), and that includes its own stale-artefact rows. A rebuild whose
   stage is `gate.certify` (twin, geometry or certificate stale, which happens only when the
   CIR or release moves) would deadlock in the same way marketing did before W4-LISTREADY R4.
   The chain move does not reach it, because certificates record no `chain:release`. It is not
   changed here because it is a gate.
2. Orphans could also be prevented at the producer by having `_persist_frames` retire the
   rows it drops. The read-side rule is needed anyway for the rows production already holds,
   so the producer change was left out to keep the diff to one rule.
