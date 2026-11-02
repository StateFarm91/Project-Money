# Independent review: W5-A5 P0-CORRECTION-LOOP @ 717c79258b1f7b8e09d6680c5bd238552ff446f0

Reviewer: independent read-only Claude Code subagent, 2026-11-02 UTC. Detached scratch worktrees, since removed. Nothing pushed, committed or modified.
Diff reviewed: 7c42e706 (w5-INTEG1) -> 0dcf3b54 (code) -> 717c7925 (empty status commit). 8 files, +877/-47.

## Verdict: DO NOT SHIP (exact SHA 717c7925)

The loop does what it was asked to do on boundedness, idempotency, holds and evidence wait. Every mutant was killed and every suite I ran is green.
It is not shippable because the new GAUGE_FROM_YARN_BAND path can change certified designs beyond what was refused:
- It ignores physical evidence (A5-1).
- It runs on refusals that have nothing to do with the gauge (A5-2).
- It silently rewrites the hook size and the chain/row gauge (A5-3).

Separately, a refused re-certification of a version that is already certified lands in none of the three required terminal states (A5-4).
Each fix is small.

## Findings

### A5-1 HIGH: the loop re-gauges a physically evidenced design
`engineering_ops.live_codes` (line ~198) and `repair_gauge_band` call `gates.certificate.gauge_findings(cir)` with the default `physically_evidenced=False`.
Certification itself calls it with `physically_evidenced=physical_test_passed` (certificate.py:380). In that case an off-band gauge is only a WARNING (`GAUGE_OUTSIDE_BAND_PHYSICALLY_EVIDENCED`) and the release is granted.

`route_failure` adds `live_codes` to every refusal. So when a design whose off-band gauge is backed by a tester's measured sample is refused for any unrelated reason, the loop replaces that measured gauge with the band middle:
- the refusal can come from certify (e.g. PROVENANCE_MISSING), a re-verification, or assets;
- the revision changes content, so the physical binding is invalidated and the design changes.

Repro (probe p4): `gauge_findings(cir, physically_evidenced=True)` gives `[('WARNING','GAUGE_OUTSIDE_BAND_PHYSICALLY_EVIDENCED')]`. Yet `route_failure(ctx, cir, stage="certify", codes={"PROVENANCE_MISSING"})` returns `{'held': False, 'revise_job': 2, 'rules': ['GAUGE_FROM_YARN_BAND']}`.

Fix: pass physical evidence through (the certificate's own findings), or use only the refusing stage's codes, never live self-detection, for certify/quality/assets.

### A5-2 MEDIUM: an unrelated refusal is "corrected" with a gauge change (the case the worker flagged)
This is a silent change, not a correct correction.

Probe p1 is the scenario of `test_a_failed_reverification_is_corrected_as_a_new_version`:
- The re-verification actually failed for `CLAIM_CONSTRUCTION_UNSUPPORTED: name promises a basket...`.
- `live_codes` added the gauge code. The loop rewrote gauge 30.0 -> 12.5 sts/10cm, so every finished dimension grows by about 2.4x.
- It certified 1.3.0 with a `correction` relation whose `what_changed` reads "GAUGE_FROM_YARN_BAND (correction loop, quality)" and started `listing.draft`.

What this means:
- The defect that withheld 1.2.0 is not addressed.
- Buyers of 1.2.0 would be notified about a correction that does not correct their problem.
- The single revision for 1.2.0 is spent.

Probe p8 shows the same thing on the assets path: `COLOR_NOT_IN_PATTERN` was answered by a gauge revision.

The new test asserts this behaviour as correct. Under this review that is a test that blesses the defect, not a weakened test.

Fix: only revise when a rule answers a code the refusing stage actually raised. Today the legacy gauge defect still surfaces by itself through `gate.certify` re-certification and the `products.inventory` GAUGE path.

### A5-3 MEDIUM: GAUGE_FROM_YARN_BAND changes more than the stitch gauge, and does not record it
`repair_gauge_band` does `replace(cir, gauge=gauge_for(weight))`. `creative.prototype.gauge_for` returns a brand-new Gauge, which:
- hardcodes `hook_mm=5.0`;
- derives `rows_per_10cm` from `SC_ROW_RATIO`;
- resets `chains_per_10cm=None` and `chain_gauge_uncertainty=0.0`.

Repro (probe p3), hexagon_coasters (DK):
- before: `Gauge(22.0, rows 24.0, hook 3.5, chains_per_10cm 21.0, uncertainty 0.05)`
- after: `Gauge(14.5, rows 16.0, hook 5.0, chains None, 0.0)`
- the published US pattern now reads "Gauge: 14.5 sts x 16.0 rows = 10cm in sc, 5.0mm hook".

The audit row only records `gauge_from`/`gauge_to` stitches. So the hook change and the lost chain calibration are unrecorded design changes.

Fix: replace only `stitches_per_10cm` (and rows by an explicitly recorded ratio), keep the hook and chain calibration, and record every changed field.

### A5-4 MEDIUM: a refused re-certification of an already certified slug@version ends in none of (a)/(b)/(c)
The certify refusal path calls `route_failure(..., bump_version=False)` unconditionally. When the refused CIR is an already certified version (a Launch-0 re-draft or re-certification under a tightened gate):
- the revision is made in place under the same version;
- recompile and recertify are then refused by PT-03 `version_immutable`.

Repro (probe p5, through Worker): legacy certified harvest-table-runner@1.2.0 (off-band gauge), then `gate.certify` of that same CIR. The run went:
- gate.certify refused; cir.revise done, `to_version 1.2.0`; cir.compile; gate.certify `refused: version_immutable`.

The result:
- incident `release.version_immutable:...@1.2.0`;
- no `correction-hold`, no correcting minor version;
- the `cir.revised` row says revised, and the cap is spent.

PT-03 means the certified release is not edited in place (stored gauge stays 30.0). But the terminal-state contract is broken.

Fix: when slug@version is already certified, set `bump_version=True` (a correcting minor version) on the certify path as well.

### A5-5 LOW: the cap is per version, not per lineage
Each correcting minor version (bump path) starts with `revision_attempts == 0`: quality/assets pass `revision=0`, and the durable count is keyed by the new slug@version.
Termination across a lineage relies on each rule being idempotent. The gauge rule leaves the gauge in band, and the repeat rule leaves the width divisible.
I found no non-terminating sequence with today's two rules. The bound is still not structural, so a future non-idempotent rule would chain versions.

### A5-6 LOW: compile/certify holds only resolve when the same version certifies
`handle_certify` resolves `correction-hold:<slug>@<version>` only on that exact version. The REMEDIATION text offers "a new design version" as the fix, but certifying a new version leaves the old hold open forever, as a stale P2 incident.

### A5-7 LOW: `codes_of` regex accepts any 4+ letter uppercase word before a colon
`codes_of(["ERROR PHYSICAL_TEST_REQUIRED: ... NOTE: x", "ERROR: plain"])` returns `['ERROR','NOTE','PHYSICAL_TEST_REQUIRED']`.
A refusal message containing such a token would turn an evidence-only refusal into a hold. No current certificate message does this (I checked the three evidence messages), so it is latent.

### A5-8 LOW/INFO: quality and assets holds are restated on every re-run
For quality and assets, `open_hold` only looks for the `correction-hold:` signature. The stage's own hold (`quality.reverify:*` / `chain-deadend:assets:*`) is never seen.
So every cadence re-routes and writes another `cir.correction_held` audit row. It is bounded (no jobs: the cap or no-rule path holds), but noisy. `cir.correction_held` and `cir.revise_unrepairable` have no retention classification, so they fall to the default horizon. That is acceptable because neither is read for the bound.

### A5-9 LOW: race between two concurrent revise jobs
Two `cir.revise` jobs for the same slug@version with different fingerprints can both read `attempts == 0` before either writes `cir.revised`, which gives two revisions. Only possible with concurrent workers. Not reproduced.

### A5-10 INFO: separation of duties
`assets.build` runs as the `publishing` agent, and `FORBIDDEN_COMBINATIONS["publishing"]` contains `cir.revise` and `gate.certify`. The publishing stage now causes a content revision (enqueued for crochet_engineer and re-certified).
It is not a permission bypass, because the job runs as crochet_engineer. Owners should confirm the intent.

## Adversarial checks

| Check | Result |
|---|---|
| Revise twice by resetting the counter (re-draft with new fingerprint, revision=0) | Bounded by the durable count. Test plus M6 mutant. |
| Replayed / duplicate certify events | One revise job (idempotency key). Test plus M3. |
| Lost lease on cir.revise | One `cir.revised` row, one recompile. Test. |
| Revision producing the same fingerprint (lost-lease re-run) | `already` path, no second row. |
| Revision producing a new fingerprint each time (same version) | Held at attempts=1. |
| Certified release edited in place | Never: bump path makes a new minor version, and the certify path is saved by PT-03 (but see A5-4). |
| Hold blocks only that version; a healthy product proceeds | Yes (tests 1/2/5, probe p8). |
| Evidence-only codes never become a hold or a revision | Yes (test plus M4/M4b), with A5-7 as a latent caveat. |
| Incident resolved on later certification of the same version | Yes. Other versions: no (A5-6). |
| Retention: cir.revised in PROTECTED_ACTIONS (lifetime_total) | Verified. Removing it fails test_w4_fmbatch1_retention_guard (M5). |
| Assets path through Worker | Real Asset Truth failure not reachable with fixtures: assets.build of the legacy fixture passed through to pricing.position. With the stage body stubbed to return `ERROR COLOR_NOT_IN_PATTERN` (probe p8, real wrapper, real chain_successors, real Worker): one revision, one dead-end hold, consistent. |
| New job types needing JOB_BANDS/JOB_CLASS | None. cir.revise is already in orchestrate.JOB_BANDS (proven_winner) and authority.classes (_B). |
| autonomy_map regeneration | `amap.build()` equals the committed map exactly, ignoring generated_at (0 diff lines). The edge cir.compile->cir.revise moved to `runtime/engineering_ops.py:route_failure`. |
| Tests weakened | None. Only the new test file was added; no existing test was touched. |

## Suites (venv-integ4, run one at a time)

| Suite | Result |
|---|---|
| test_w5_a5_correction_loop | PASS 13/13 |
| test_swarm_runtime | PASS |
| test_w3_k11_authority | PASS |
| test_shadow | PASS 10/10 on re-run (1708s). The first run timed out at 1800s under machine load average about 8. |
| test_launch0 | PASS |
| test_first_customer_gate | PASS 12/12 |
| test_cert_publish_gates | PASS |
| test_opus2_reverify_withhold | PASS |
| test_incident_lifecycle | PASS |
| test_w4_fmbatch1_retention_guard | PASS |
| test_cost_governance_wave2 | PASS |
| test_cert_rebuild_chain | PASS |
| test_reachability | PASS |
| test_w3_reachability_dynamic | PASS |
| test_w4_c12_wiring (committed map counts equal live) | PASS |
| test_new_modules_are_reached | does not exist; reachability is covered by the two reachability suites above |
| Full suite | UNKNOWN (not run, by instruction) |

## Mutants (all against test_w5_a5_correction_loop unless noted)

| Mutant | Killed by |
|---|---|
| M1a: route_failure cap `>=` -> `>` | test_cap_off_by_one, test_durable_count |
| M1b: both cap sites `>=` -> `>` | same two tests |
| M2: no hold incident | 5 tests |
| M3: revise idempotency key removed | test_fixable_certify..., test_duplicate_certify_events |
| M4: evidence codes routed to revise | test_missing_physical_evidence |
| M4b: evidence codes routed to hold | test_missing_physical_evidence |
| M6: `revision_attempts` returns 0 | test_durable_count, test_lost_lease_rerun |
| M5: `cir.revised` dropped from retention | test_w4_fmbatch1_retention_guard |

Gap: no mutant-killing test exists for A5-1, A5-2 or A5-3. The current tests assert the A5-2 behaviour as intended.

## Merge cleanliness
- **vs origin/claude/w5-INTEG1 (7c42e706):** clean. INTEG1 is an ancestor of A5 (fast-forward, 0 commits behind).
- **vs origin/opus2/a6-learning-to-design (8c131f10):** one CONFLICT in `runtime/engineering_ops.py`, in `handle_cir_revise`.
  - A5's open_hold, cap and `already` block sits against A6's `_design_learning` "learning held" early return.
  - `ops/retention.py` and `runtime/pipeline.py` auto-merge.
  - A semantic issue remains after the textual resolve: A6's early return (`learning["held"]`) is a fourth terminal state, with no `correction-hold` incident and no `cir.correction_held` audit.
  - Resolve it by placing A6's check after `open_hold`, and either route its held outcome through `record_hold(...)` or explicitly add it as a named terminal state.
  - Regenerate `autonomy_map.json` after merge, because A6 changes pipeline.py.

## Probes
Kept in /tmp/claude-0/-home-user-Project-Money/0aa334b9-5ba9-5fd2-9058-e50b4b8604ea/scratchpad/probes (p1-p8). Logs are in /tmp/claude-0/-home-user-Project-Money/0aa334b9-5ba9-5fd2-9058-e50b4b8604ea/scratchpad/logs.
