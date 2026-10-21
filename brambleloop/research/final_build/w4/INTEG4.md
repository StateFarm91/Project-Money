# INTEG4 (2026-10-20): release candidate 6b25eb0 on top of production b931d17

Integrator: W-INTEG4. Worktree `.claude/worktrees/W4-INTEG4`, branch `claude/w4-INTEG4`, created from
`origin/claude/w4-INTEG3` 364ade0 (= production b931d17 + its deploy record). Production: b931d17,
SHADOW. No deploy, no production write, no spend, no credential change. Production contact:
none by this integrator (local PostgreSQL only). One suite file, now moved out of the suite (§5),
made a public read-only GET of `/api/audit` when it ran.

**CERTIFIED: `15800536290bce6b3c85dbfcf460ff0b63a4329a` on `claude/final-candidate-b997efd`.**

| commit | what it is |
|---|---|
| `b997efda48e4c8a26176d2a3959430852300631f` | the tested source tree |
| `f19b264` | release record (records only) |
| `1580053` | records-only merge of production b931d17, so the candidate fast-forwards from production |

- **Full suite:** passed, 674 suites, 9025 tests.
- **Deploy guard:** DRY_RUN ALLOW.
- **Rollback rehearsal:** ALLOW.
- **Independent reviews:** NO BLOCKER on every range up to b997efd. Results and gates are in §8.

Superseded freezes (do not deploy):
- `claude/final-candidate-ea23282`: its suite was stopped after about 7 minutes (record `interrupted`) when the
  review of 17bc373 found M1 (§6).
- `claude/final-candidate-6b25eb0`: its suite failed 9 suites (§9).

## 1. Merges (in order, one implementation per defect)

| # | Branch @ head | Merge commit | Conflicts and resolution |
|---|---|---|---|
| 1 | w4-FIRSTSALE @ cc0c54e (final): durable PDF delivery, purchase rehearsal, Etsy image readiness, first-sale view, taxonomy matcher, retention, alt text | fd2055c | none. Focused: firstsale_deliverables, _retention, _taxonomy, _view, l0_product_readiness, vacuity: 6/6 suites pass. |
| 2 | w4-BRANDRULE @ 55083da (records only): D-W4-F852-PROPOSED, D-W4-F852-AMEND | d2b5d70 | `DECISION_LOG.md`, append-only: INTEG3's D-W4-SLOWLOOP-CONTRACT3 and BRANDRULE's sections both kept; 0 lines removed relative to either parent. |
| 3 | w4-CLOSE5 checkpoint @ d1ed36c: R1 webhook gate, grid-tournament cost cut, FM closures batches 1-6 | 4dd2218 | none. CLOSE5 edited `test_w4_integ3_secfixes` M1: strengthened (it must use the private gate; shared threadpool forbidden). 14 suites (close5_*, secfixes, required set) pass. |
| 4 | w4-VISNEXT @ 0beb522 (coordinator: FINAL; contains FLUXLIVE 7886f58, FLUXAPI, VISAUTO, FIDELITY, WRAPTEST, BRANDRULE 55083da) | 7f6dbe8 | `DECISION_LOG.md` append-only, both kept. Edits to existing tests reviewed, none weakening: `test_rc1_spend`/`test_cert_cost` bill the per-request documented price and assert it is never below the table price; `test_w4_condpack` asserts full-pack transmission; `test_eligibility` docstring only. 30 suites pass on the merged tree. FLUXLIVE is an ancestor of the merge (verified). |
| 5 | w4-CLOSE5 @ ee244a1 (coordinator: the intel.gallery_analysis read-timeout fix, mandatory): 180 s vision read timeout, all-required gallery_observation schema, 40-minute run bound, batch 7 | 263e94d | none. Existing tests changed by CLOSE5: `**kw` signature adaptations (`_send` takes `timeout=`), and `test_w4_rel2` asserts the new all-required schema and that an unjudgeable field is still dropped. 17 interplay suites pass (gateway, pl_*, b2vision, spend_paid_calls, visnext, fidelity, rel2). |
| - | INTEG4 security fixes, review of 7f6dbe8 | e28059d, 304e8a2 | §4 |
| 6 | w4-CREDHEALTH @ 0b6e699 (owner directive; ready inside the window) | 17bc373 | none; the trial merge was clean. |
| - | Regeneration (once) + F-852 override | d81dd4e | §3 |
| - | CLOSE5 x VISNEXT: F-152 scratch registry | ea23282 | §5 |
| - | INTEG4 fixes, review of 17bc373 (M1, I7, I8) + live verifier out of suite | 6b25eb0 | §6 |

Polling: CLOSE5 was polled from 06:31Z; VISNEXT and CLOSE5 were merged when the coordinator
declared them final or mandatory. CREDHEALTH reported ready at 0b6e699 about 40 minutes after
the CLOSE5 fix landed, inside the 2-hour window.

## 2. Fresh venv

`/home/user/bl-runs/venv-integ4`: Python 3.11.17,
`pip install --no-deps --require-hashes -r requirements.lock` (the lock is unchanged by every
merged branch; sha256 d7b9a8e6…, identical to b931d17's), plus the test-only packages httpx 0.28.1,
httpcore 1.0.9 and certifi 2026.10.18. `pip freeze` is the 35 lock pins plus those 3, and
`pip check` is clean. The dependency suites run inside the full suite (§7).

## 3. Regeneration (once, after all merges) and the F-852 amendment

- **F-852/F-853 override (owner decision D-W4-F852-AMEND).** The entries from
  `w4/OVERRIDES_PROPOSED_F852_AMEND.json` were copied into `research/final_build/overrides.json`
  with `accepted_by` set. That is the board's own mechanism (F-867: a worker cannot certify
  itself). The dry run reported 0 problems.
  - Both rows were already COMPLETE/INTEGRATED, so **no row changed completion**.
  - The override records the amended meaning: the verified-exception route, its tests and its
    evidence.
- **Regenerated with venv-integ4:**
  - Build 2 ledger (`prod_api_build_20261020T0416Z.json`): PROVEN 229, OPEN-DEFECT 2. Unchanged.
  - aggregate, FM ledger, board, prelaunch scope.
  - CC snapshots.
  - decision index (31 ids).
- **The autonomy map changed only its timestamp**, so it was restored.
- **Honest effect of BOARD's rule.** A row whose named module this release edits reads
  dev-proven until the deploy is read back:
  - Build 2 verified 194 -> 101;
  - FM launch-critical verified 364 -> 328.

  No row was closed or opened by assertion. The CLOSE5 closures F-542 and F-718 drop off the
  closed list for the same reason. They return when the deploy is read back.
- Focused: board, board_close, cc_snapshots, decision_index, final_closure_matrix,
  final_master_gate, overrides_proposed, autonomy_timeline, close5_* (8 suites),
  b2_build2_ledger, owner_actions, cert_dashboard and others: 27 suites. All pass after §5's fix.

## 4. Independent review of b931d17..7f6dbe8: BLOCKER B1, fixed

Review by a fresh session, W-SECREVIEW4 (`claude/w4-SECREVIEW-7f6dbe8` @ 15cf725, copied here
as `INDEPENDENT_SECREVIEW_7f6dbe8.md`). An earlier session for the same review hit a usage limit
before writing anything and was archived. R1 (webhook flood) is **FIXED** by CLOSE5's private gate.

**B1 (BLOCKER).** `GET /api/model-tournament/image/{sha}` is public and served *any* stored
artifact by digest. The public `GET /api/audit` printed the certified PDFs' digests
(`assets.built`), and this release keeps those PDFs in Postgres. Together that made every paid
pattern a permanent free download. Production b931d17 has the same two routes, but its PDFs are
not on disk, so the leak is effectively closed there today.

The fix (e28059d) has two parts.

1. **The route is now an allowlist.**
   - **Served:** a digest kept *only* for the canonical reference pack, or one named by a
     recorded `model.tournament` or `model.reference_pack` package.
   - **Refused:** a digest kept for any other purpose (deliverables, frames, experiments,
     production candidates, boards), a digest no package names (charts, PDFs, frames on disk),
     and anything at all when the state is unreadable (it fails closed).
   - **Image bytes only:** PNG, JPEG or WebP by magic number, with the media type taken from
     the bytes. A PDF is never served, even when a package names it.
   - **Headers:** `private` caching and `nosniff`.
2. **`/api/audit` without the operator credential shortens every 64-hex digest** to its first
   12 characters. The operator view is unchanged, and the names the overnight grader and the
   taxonomy verifier read are unaffected.

The same commit fixes L1-L4:
- **L1:** restart requires step-up.
- **L2:** the experiment reserves the gateway's own `render_estimate_usd`, never below the table
  price.
- **L3:** the Etsy upload checks every certified frame for experiment output, and the image check
  fails closed.
- **L4:** retention re-reads protection just before it deletes. This narrows the race; it does
  not remove it.

Tests:
- `tests/test_w4_integ4_secfixes.py`: 10/10, and 0/10 on the unfixed tree 263e94d.
- `tests/test_w4_integ4_deliverable_routes.py` (coordinator item 2): every GET route, routers
  included, plus every public mutating route.
  - Each path parameter is filled with the PDF digest, the slug, slug@version, the version
    and "1".
  - Each route is requested with no credential, with the file on disk and again after a
    simulated redeploy.
  - No response may carry the paid PDF: not raw, not base64, not as a PDF body.
  - Result: 4/4. On 263e94d it fails on exactly `GET /api/model-tournament/image/<pdf sha>`
    (200, raw bytes).
  - There is no customer delivery-token route in this build. Fulfilment is Etsy's digital-file
    delivery, so "without a token or owner auth" means "without any credential".
  - The owner route `/api/cc/store/pdf/{slug}` is in the sweep and refuses anonymous callers.

## 5. Cross-branch defects found and fixed at the root

| Suite | Cause | Fix |
|---|---|---|
| test_w4_wraptest (5 checks) | CLOSE5 ee244a1 gave `AnthropicProvider._send` a `timeout=` keyword; WRAPTEST's `FakeNetwork.send` stub did not take it, so every vision read errored to UNKNOWN | the stub takes `**_kw` (the adaptation CLOSE5 made in its own harnesses); no assertion changed (304e8a2) |
| test_w4_close5_rows `test_f152_every_scratch_site_is_classified` | CLOSE5's F-152 registry predates three VISNEXT scratch sites | classified truthfully: flux3 `_scratch` -> `image_production._generate` (store_bytes, record_candidate); `controlled.run_job` -> `handle_controlled_experiment` (ctx.audit); `fidelity.read` -> `craft_texture`. Each home is verified by the companion test (ea23282) |
| test_w4_firstsale_taxonomy_live | a live production read that exits 3 (UNKNOWN) by design; `run_tests.sh` counts any non-zero exit as a failing suite, so no full suite could be release-eligible | moved to `tests/verify_w4_firstsale_taxonomy_live.py` (an operator step, as its own docstring says); its offline rules run in `test_w4_firstsale_taxonomy::test_the_live_verifiers_own_rules_hold_offline` (6b25eb0) |

## 6. Independent review of 7f6dbe8..17bc373: NO BLOCKER; M1 fixed

Review by a fresh session, W-SECREVIEW5 (`claude/w4-SECREVIEW-17bc373` @ 5be3fbc, copied here as
`INDEPENDENT_SECREVIEW_17bc373.md`).

- **Earlier findings:** B1 FIXED (the reviewer's bypass probes all returned 404); L1-L4 FIXED.
- **CREDHEALTH:** `GET /api/cc/credentials` is owner-only, the on-demand check needs step-up,
  there is no public endpoint, no key value appears anywhere, and the checks are free and bounded.
- **The CLOSE5 timeout fix:** safe.

**M1 (MEDIUM), fixed in 6b25eb0.** A resumed experiment run could resend a paid render while an
earlier attempt's billing was unknown. The paid-call guard keys calls by their occurrence within
one execution, so the resumed loop reused attempt 1's DECLINED key and never reached attempt 2's
in-flight record.

The fix: on resume, the guard's own `paid_call_records` decide. A new attempt is sent only if
every earlier paid call of the job was DECLINED. Otherwise the run settles as failed with nothing
resent, a PENDING call is counted once as an orphan, and unreadable records never lead to a resend.

`tests/test_w4_integ4_resume.py`:
- 2/2 here; 0/2 on 17bc373 (the resumed run sent a second paid render);
- 5/5 with CREDHEALTH's restart tests on PostgreSQL 16 (`evidence_INTEG4/pg_migration_output.txt` §7).

Also fixed:
- **I7:** any 64+ hex run is shortened, and so is the `artifact` column.
- **I8:** the owner-view key fingerprint is domain-separated, and KEY_ROTATION.md says so.

Not fixed (next release):

| ID | What remains |
|---|---|
| I1 | The BFL polling URL is not host-checked before `x-key` is sent. It needs a spoofed BFL answer over verified TLS. The fix changes an existing fixture's polling host, which belongs to the image worker. |
| I2 | `laura_present` is self-declared. |
| I3 | The release comparison is tautological. It is unreachable today. |
| I5 | Experiment and candidate images are never pruned. Growth is bounded by spend. |
| I6 | `/owner-images` reads the body before its size check. Owner-only, behind CSRF. |
| I9 | Public `/api/audit` shows the BFL credit balance. No key or fingerprint is shown. |
| I10 | The sweep fills path parameters, not query parameters. |
| I11 | The resumed `attempt_log` keeps only the settle entry. |

**Delta review of 17bc373..6b25eb0** by a fresh session, W-SECREVIEW6
(`claude/w4-SECREVIEW-6b25eb0`): result in §8.

## 7. New tables and migration (local PostgreSQL 16.15, never production)

| table | from | created |
|---|---|---|
| `experiment_authorizations` | VISNEXT (controlled experiments) | at boot (`Database.create_all`) |
| `controlled_experiment_runs` | VISNEXT | at boot |
| `laura_outfits` | VISNEXT/OWNERIMG lineage | at boot |
| `image_production_runs` | VISNEXT/OWNERIMG lineage | at boot |
| `image_candidates` | VISNEXT/OWNERIMG lineage | at boot |

FIRSTSALE uses the existing `durable_artifacts` table; CLOSE5 and CREDHEALTH add no table.

Proof (`evidence_INTEG4/pg_migration_output.txt`, scripts `pg_schema_boot.py` and
`pg_schema_diff.py`), on 7f6dbe8, on ea23282 and again on the frozen 6b25eb0:

1. A schema built by production b931d17 code has 131 tables.
2. Candidate boot: 136 tables, exactly the 5 new ones, `create_all` changes `[]`, and **no
   column added, removed or altered on any existing table**.
3. A second boot is a no-op.
4. **Rollback:** b931d17 code booting the upgraded schema changes nothing. It ignores the
   tables, so rolling back is safe.

All 5 tables were exercised on PostgreSQL:
- `test_w4_controlled_experiments` 10/10: 8 authorization rows, 8 run rows;
- `test_w4_ownerimg` 35/35 (a fresh database per `make_db`): 10 run rows, 61 candidate rows,
  49 outfit rows;
- `test_w4_firstsale_deliverables` 6/6 with `BL_TEST_PG_URL` (`durable_artifacts` kept,
  re-rendered and refused, plus the purchase rehearsal).

## 8. Release gates

The gates were run on b997efd, with the release record and production b931d17 merged on top
(final commit 1580053). The src tree and requirements.lock are identical to b997efd.

### Full suite

**Run 20261021T002000Z-11418 on b997efd passed.**

| field | value |
|---|---|
| suites | 674 |
| tests passing | 9025 |
| suites failing | 0 |
| temporary files leaked | 0 |
| release-eligible | yes |
| duration | 7665 s |

Run settings: REQUIRE_CLEAN=1, JOBS=3, venv-integ4, a SIG_DFL launcher, and a harness-tracked
watcher. The coordinator paused the other workers, so the machine was quiet.

`test_cert_wiring` passed 16/16 in 870 s. Its 1200 s drain limit is unchanged.

Evidence on `claude/w4-INTEG4` in `evidence_INTEG4/suite_runs/20261021T002000Z-11418/`: the
record, the log, the gzipped full log and the per-suite outputs.

Earlier runs on this freeze:
- **Killed:** two runs died when the container restarted.
- **Run 20261020T204746Z-1135:** 9022 tests passing, 1 suite failing (`test_cert_wiring`, "queue
  did not drain: 221 jobs in 1203s"). The other workers' suites were running at the same time.

### test_cert_wiring root cause

`evidence_INTEG4/cert_wiring_timing/` holds the per-handler timing.

| run | conditions | time |
|---|---|---|
| production b931d17 | quiet machine, run side by side with the candidate | 825 s |
| b997efd | the same | 844 s |
| production b931d17 | loaded machine | 964 s |
| b997efd | loaded machine | 1194 s |

The quiet runs differ by 2.3 %.

- **What the candidate adds:** only `visual.image_production` (23 jobs, 15.7 s) and about 6 s in
  `ops.maturity_disagreements`.
- **What it does not add:** no handler waits on a provider, a 180 s vision timeout, the 40-minute
  gallery bound or a retry sleep.
- **Noise:** `visual.rnd.cycle`, whose code is identical in both trees, ranged from 178 s to 254 s.
- **Conclusion:** the failures were CPU contention. The code was not changed and the limit was not
  changed.

The two later cert_wiring failures in run 1135 come from the incomplete drain. When the drain
throws, `drained()` never fills `_STATE`, so the spies the drain would have reached stay empty.
Every complete drain passes 16/16.

### Deploy guard

`python3 ops/deploy_guard.py record` gave `ok: true`:
- `release/RELEASE_b997efda….json`;
- tree_sha256 `96631dabb89c15b8eed00816b0daeb075b94d9f25c2d04e48984538968119612`.

It was committed with `release/NOTES_b997efd.md`, the run record, its log and the full log as
**f19b264**. The records commit changes nothing under `src/`.

### Fast-forward fix

The first DRY_RUN check said REFUSE: "candidate f19b264e231b is not a descendant of deployed
b931d17a738d: deploying it would roll production back".

The cause: b931d17 is INTEG3's records-only commit on `claude/final-candidate-324927f`, and it was
never on `claude/w4-INTEG3`, where INTEG4 started.

The fix: merge it, records only. It touches only release/ and research/, so the deployable digest
(src/ + requirements.lock) is unchanged. Result: **1580053**.

### DRY_RUN deploy

`DRY_RUN=1 sh ops/deploy.sh --deployed b931d17…`, run at 1580053: **ALLOW**. The check said ALLOW
and the built-in rollback rehearsal said ALLOW. Nothing was pushed.

Output: `evidence_INTEG4/release_gates/dry_run_deploy_15800536.out`.

### Rollback rehearsal (dry run only)

- `DRY_RUN=1 sh ops/deploy.sh --rollback-to b931d17… --reason "INTEG4 rollback rehearsal to
  production b931d17" --deployed 1580053…` gave **ALLOW**. It built rollback commit e6abb26
  locally and pushed nothing.
- `deploy_guard.py rehearse-rollback --candidate HEAD --deployed b931d17` gave **ALLOW**.

The new tables are additive, and b931d17 ignores them (§7).

### Backup and restore readiness

This was a read-only Railway log read; nothing was redeployed. The latest db-backup run,
`20261020T035733Z`, reported `BK restore_ok` and `BK RESULT OK`:
- dump of 400,700,102 bytes, sha256 9b048ea4…;
- 135 tables, 143,054 rows restored;
- volume 3.7 GB, 682 MB free.

Details: `evidence_INTEG4/release_gates/db_backup_readiness.md`. The fresh pre-deploy backup is taken
at deploy time, with the owner's approval. The free space holds one more dump, not two.

### Independent review

84deb4b (W-SECREVIEW7) covers 6b25eb0..b997efd: **NO BLOCKER**. It applies to the final tree,
because 1580053 differs from b997efd only in records (release/ and research/), not in src/,
requirements.lock or ops/.

The chain of reviews covers b931d17..b997efd: 7f6dbe8 (B1, fixed), 17bc373, 6b25eb0, b997efd.

Open INFO items for the next release:

| ID | What remains |
|---|---|
| I1 | The BFL polling URL is not host-checked before `x-key` is sent. |
| I2 | `laura_present` is self-declared. |
| I3 | The release comparison is tautological. |
| I5 | Experiment and candidate images are never pruned. |
| I6 | `/owner-images` reads the body before its size check. |
| I9 | Public `/api/audit` shows the BFL credit balance. |
| I10 | The sweep fills path parameters, not query parameters. |
| I11 | The resumed attempt log keeps only the settle entry. |
| I12-I19 | INFO items from the last two reviews; see those reports. |

### Not done

**No deploy.** Deploying 1580053 needs:
- the owner's explicit approval of the SHA;
- a fresh db-backup first.

## 9. Freeze 6b25eb0: 9 suites failed, each fixed at the root (b997efd)

Run 20261020T122822Z-2163 on 6b25eb0: 9007 tests passing, 9 suites failing, 0 temporary files
leaked, 12385 s. Every one of the 9 is cross-branch: an invariant test the merged branch never ran.

| Suite | Cause | Fix |
|---|---|---|
| test_product_run | FIRSTSALE keeps the PDFs in Postgres, so `assets.storage_not_durable` stopped firing, although the chart and legend are still ephemeral | the audit names every ephemeral file of the build |
| test_cert_spend_hosts | `gateway/credentials.py` (CREDHEALTH) addresses paid-provider hosts and was undeclared | declared, on the basis of the 17bc373 review's "free, budget-neutral, bounded: SAFE" |
| test_fb4_lc | FLUXAPI's `flux-3-image` reopened the F-588 production-partners verdict | re-audited: same vendor and role as `flux-2-pro`, and the buyer's PDF is code-rendered, so NOT_APPLICABLE stands (recorded with its basis) |
| test_swarm_runtime | `visual.controlled_experiment` had no priority band | `exploration` |
| test_visual_inspection | `credentials.py` hardcoded a model string | `model_for`: the model routing gives the vision judge (`asset_inspection`) |
| test_w3_hq_independence | `repair_routes` read research/ at runtime; production's image has no research/, so the seed silently did nothing | the records ship under `src/brambleloop/visual/assets/owner_experiments` (byte-identical, test `test_w4_integ4_shipped_records`) |
| test_w3_k12_model_photography | the premise "BFL carries one reference" changed with FLUXAPI | premises updated; the F-212 refusal is still proven, before any request or reservation |
| test_v11_pwa_browser | `/api/cc/credentials` was missing from the mock (404); the first-sale rows were counted as lanes; the More menu now has 11 items | mock route and fixture selectors updated; new check that the provider-keys card never shows a key. 218/0 |
| test_cert_wiring | the 1200 s drain limit was exceeded under load | no code change (see §8) |
