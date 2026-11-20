# W4-FMGATE: Final Master launch-critical rows against the deployed release 0417f35

Lane `claude/w4-FMGATE`, worktree `.claude/worktrees/W4-FMGATE`, based on
`0417f3516f30bb7c52926187fc475a0f46536e86`. Date 2026-10-11 UTC.

Nothing was written to Railway or Etsy. Nothing was spent and no customer was messaged. Production
was only read, with public GETs. No existing test assertion was edited. No spend ceiling and no
model-selection policy was changed.

Merged into this branch, all clean:

- `claude/w4-PACKETREL` 715b5db: the accepted F-845 override, the 7421ef6 freeze records,
  the release-record citation in the launch packet, and the deploy-guard binding in
  `freeze_candidate`. Its `src/` and test changes were checked first; no assertion is weakened.
- `claude/w4-SECREVIEW` 7d02c03.
- `claude/w4-MIGRATE` 252b35a.

## Counts (aggregate.py, launch-critical)

| | COMPLETE | GATED | OPEN |
|---|---|---|---|
| 0417f35 as deployed (`/api/build final_master`) | 355 | 126 | 9 |
| this branch, regenerated | **363** | **119** | **8** |

The brief's "356/126/8" is 0417f35 plus PACKETREL's accepted F-845 override, which 0417f35
does not carry.

The OPEN count goes down by only one because four rows were wrongly parked and are now OPEN
(F-144, F-171, F-718, F-733). The deploy cleared their gates and the remaining work is the
company's.

`summary.problems` is `[]` and `orphaned_partials` is `[]`.

## Production readback (2026-10-11T14:39Z, `evidence_FMGATE_0417f35/`)

- **`/health`:** build.commit is 0417f35 and `known` is true. The worker started at
  13:59:48Z.
- **`/api/status` boot_guard:** enforced and ok. The record is RELEASE_5dfd1ac and tree_sha256
  is 30a4dc93, which equals the release record.
- **`/api/verify` is `ok:false`** (fcb982d read 12 of 12). Two checks fail:
  - `every_agent_has_a_cost_ceiling`: the learn, coo and laura agents have a 0.0 ceiling. This
    lane did not change it; it is for the integrator or the owner to decide.
  - `no_unexpected_dead_letters_in_24h`.
- **`/api/queue/dead` shows two defects that appeared after the deploy. Both are repaired on
  this branch:**
  - **`ops.sentinel`** dead-lettered 7 times from 14:27Z with StringDataRightTruncation: the
    rebuild idempotency key is longer than VARCHAR(200). Repaired in **843af70**.
  - **`listing.taxonomy_refresh`** got a 403 from Etsy at 14:05Z, which the job
    dead-lettered. The 403 itself is the owner-held `etsy_api` credential. Repaired in
    **4b55f22**: a credential refusal is now reported instead of dead-lettered, the same
    handling W4-PRODDIAG gave `mjs.scan`.
- **Why these matter:** these dead letters are what keep `production_window`'s 24h
  off-device proof from ever passing.
- **Deploy guard:** `check --candidate 0417f35 --deployed fcb982d` returns ALLOW.
  `release/DEPLOYED_HISTORY.json` now lists 0417f35.

## End-stage rows

| row | result | basis / exact remaining gap |
|---|---|---|
| F-845 | COMPLETE | PACKETREL's override, accepted by the integrator (7421ef6 freeze). This lane added `CANDIDATE_0417f35.json` and `DEFECT_LEDGER_0417f35.json` (`freeze_candidate.check`, 0 refusals). |
| F-169 | COMPLETE | The release-eligible clean full suite is bound to the exact deployed tree. The running boot guard re-verified it in production. |
| F-839 | COMPLETE | Reachability was re-run on the deployed tree: 656 modules, 564 reached, none lost. The matrix was re-adjudicated and `final_proof` was run on 0417f35. INDEPENDENT_SECREVIEW reviewed the same deployable tree. |
| F-840 | COMPLETE | In production, a green suite (7877 tests) coexists with `final_master` `launch_ready:false`. `CANDIDATE_0417f35` and `final_proof_0417f35` cite the suite and the proof for the same SHA. |
| F-841 | COMPLETE | 0417f35 is the reviewed successor baseline: release record, SECREVIEW, freeze check, deployed and recorded in DEPLOYED_HISTORY. |
| F-846 | OPEN | One full loop has run: 7421ef6 freeze → REAUDIT → AUDITFIX → 7877-test suite → SECREVIEW → deploy. **Unblock:** the integrator accepts the TESTED target proposed in `OVERRIDES_PROPOSED_FMGATE.json`. The dry run computes COMPLETE. |
| F-834 | OPEN | `final_proof` on 0417f35 reads 917 BLOCKED. The packets carry only producer and live_root receipts. **Company work:** emit the durable_state → result receipts, bind the suite by tree, then a separate session does the independent review. |
| F-848 | OPEN | The rehearsal on 0417f35 is complete:false. The grant is blocked by owner `etsy_api`, and readiness has open owner items. The rehearsal also evaluates readiness on a fresh one-product database, where catalogue_depth, storefront_preview and sustainable_economics can never pass. **Company work:** cite a readiness reading from production-shaped state. |
| F-878 | OPEN | The route is live and gated: 401, where an unknown path returns 404. The deployed packet's tests/audit section is UNKNOWN in the image. The fix is merged here. **Unblock:** the integrator runs the suite, writes the release record and deploys. |

## The 126 GATED rows (`FMGATE_GATED_CLASSIFICATION.json`)

| class | rows | |
|---|---|---|
| Genuine owner gate | 62 | evidence includes production `/api/build` gates `open:false` |
| Genuine external | 26 | |
| Genuine data | 14 | |
| Re-keyed | 17 | details below |
| Misclassified, now OPEN | 4 | F-144, F-171, F-718, F-733 |
| Gate cleared, now COMPLETE | 3 | F-172, F-176, F-158 |

The 17 re-keyed rows:

- **11 rows moved from owner to data `production_window`.** The deploy has already happened,
  so what remains is elapsed operating time.
- **F-135 and F-850:** now owner `live_restart_drill`.
- **F-540:** now `etsy_api`.
- **F-518@v0.15:** now `publication_authority`.
- **F-396:** now `offsite_storage`.
- **F-924:** now data.

Further corrections:

- Stale missing_part text was corrected on F-160, F-321 and F-588.
- F-009's company half was built in **570e715**: per-listing filters on `/api/catalogue`.
- Eight rows that still name an unverified company sub-step are listed in the JSON.

## Exact unblocking actions

1. **Integrator:**
   1. Merge this branch.
   2. Run the full suite, write the release record and deploy (fixes 843af70, 4b55f22,
      570e715 and the PACKETREL packet fix).
   3. 24h later, read `/api/build off_device_proof`. 11 data rows close when it reads PROVEN.
   4. Accept the F-846 override.
   5. Decide the 0.0 ceilings for learn/coo/laura.
2. **Owner:** fix the Etsy credential (`etsy_api`): taxonomy and mjs.scan both get 403
   ("check ETSY_SHARED_SECRET"). This unblocks F-848's grant, F-540 and the 9 `etsy_api`
   rows.
