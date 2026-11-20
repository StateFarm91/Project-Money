VERDICT: DO NOT SHIP 6ba519c077c5bd12767eea7a5a2eccc1a366f297

# Independent review: origin/eng/improve @ 6ba519c0 (ENG-IMPROVE slice 1)

Base: origin/claude/w6-INTEG3 @ 39b926194fac895948d66b85261ff1965453cf04 (the merge-base, so the merge is a fast-forward).
Reviewed 2026-11-20. The suites ran on a venv with requirements.lock versions.

## Suite results (`JOBS=4 SUITE_REGISTRY=0 SUITES=… bash run_tests.sh`)

| Tree | Passing | Failing suites |
|---|---|---|
| base 39b92619 | 618 | **0** |
| base + improve (6ba519c0) | 646 | **1** |
| base + learn + improve | 672 | 3 (the union of both units' failures; no new interaction failure) |

The unit's own suites are green: test_eng_improve and test_eng_improve_readback. `test_route_auth_default_deny` passes 8/8.

### Blocking regression (introduced by this unit; the base is green)
- **`test_w4_resume_runner` fails.** The failing test is `test_f7_the_declared_final_segment_set_covers_every_matching_suite`, with: `declare these in scripts/suite_final_segment.txt: ['tests/test_eng_improve.py']`.
- The new suite matches the clock- or timing-sensitive criteria but is not declared, so a resumed run could count it from the wrong segment.
- **Fix:** add the line to `scripts/suite_final_segment.txt`.

## Requirement checks

### Tunable-key allowlist
PASS. `TUNABLES` is a closed, hard-coded tuple of 13 keys with no write path. `check()` refuses:
- any protected-invariant name;
- any undeclared key;
- any out-of-choice or out-of-bounds value.

`_assert_allowlist_safe()` refuses to import if a protected key is listed (tested with `qa.gate_pass_threshold`). The champion read guard falls back to the default when a stored value is tampered with.

My probe: 22 protected or unlisted keys × 3 value types were all refused by `check()`. The keys included `gate.certify.threshold`, `twin.tolerance`, `safety.child_warning`, `casl.consent_window`, `spend.daily_ceiling_cad`, `ads_max_bid`, `owner.exception.ttl`, `owner_exceptions`, `approval.required`, `phase`, `stage_a_enabled`, `pricing.floor_cad`, `evidence.min_sample` and `image.daily_cost_cap`.

**Mutation results:**
- **Killed:**
  - the undeclared-key refusal removed;
  - the choice check → `True`;
  - the tampered-value read guard removed;
  - the builder's own 4 in-test mutants (allow-all, no bounds, widened bounds, protected key allowlisted).
- **Survived (redundant layers, not holes):**
  - the protected check in `tuning.check` removed;
  - the vocabulary words `spend`/`budget`/`ceiling`, `owner`, `gate` + PROTECTED_GATES, and `safety` removed from `invariants`.

  The closed allowlist still refuses every such key, so these are defence-in-depth layers. Their vocabulary coverage belongs to the pre-existing invariants suites.

**Pre-existing observation (base code, not this unit).** The invariant vocabulary would **not** catch these keys if someone added them to the allowlist: `stage_a_enabled`, `pricing.floor_cad`, `price_band.max` and `visual.identity_lock`. It is worth adding `stage_a`, `price_floor`/`price_band` and `identity_lock` to the vocabulary. Related: `pricing.test_arm` is an allowlisted choice. Its "inside the certified band" promise is enforced only by the future reader, so it needs review when slice 2 wires it.

### Rollback
PASS. In the WATCHING phase, a 20% holdback compares the promoted value with the replaced one. At z ≤ −1.96 the previous value is restored as champion, marked ROLLED_BACK and audited. Mutating `if regressed` or `regressed = False` is killed.

### Promotion statistics
PASS:
- fixed looks (50·2^k);
- z ≥ 2.807 per look (Bonferroni over 6 looks);
- harm stop;
- 0 of 40 null streams promoted (tested).

Mutation results:
- **Killed:** `PROMOTE_Z→0.5`, `MIN_ARM_N→2`, `TREND_MIN_N→1`.
- **Survived:** `MIN_EFFECT 0.03→0.0`. This is minor because the z-gate still holds. A test is recommended.

### Caps
PASS. Share is ≤ 0.2, enforced at `start`; the mutant that removes it is killed. The challenger arm's spend cap is ≤ CA$5, and a zero cap means no recorded cost; the mutant that removes the cap is killed. The tuner spends nothing itself.

### ECRs
- **Dedupe:** PASS. Dedupe is by fingerprint(defect_class, department, module) over the open states; the mutant that removes it is killed.
- **Lifecycle:** PASS. DEPLOYED requires a commit. Only `verify` leaves DEPLOYED: it moves to VERIFIED only when stats.compare returns BETTER against the baseline, and otherwise REOPENS when the KPI is worse or there is no gain after 21 days. The mutants that accept "not worse" as verified, or allow DEPLOYED→VERIFIED through `advance`, are killed.
- **Readback:** PASS. `GET /api/readback/ecrs` is read-only, readback-token only (the operator token is refused), `no-store` and projected counts-only. It is covered by test_eng_improve_readback, and route_auth_default_deny passes.

### No faked improvement
PASS:
- `improving` is YES only on an UP trend (n ≥ 20 per window) or a VERIFIED ECR;
- a no-op is never improvement (tested);
- a missing or inactive consumer is a FINDING with an ECR, never a pass.

The honest status is correct: no tunable reader is wired yet, so no live challenger can run.

## Fit with eng/learn
The merge has four mechanical conflicts:
- BUILD_STATE.md and DECISION_LOG.md: keep both sides;
- `sw.js`: learn v40 vs improve v41, so the integrated tree needs **cc-shell-v42**;
- `autonomy_map.json`: regenerate it through the module.

After resolution, the combined tree's only failures are the units' own (no interaction failure). The lesson stores interoperate through the shared bus. Improve's `department_loops.lessons`/`_fired` seam should switch to ENG-LEARN's `learning_*` derived lessons in slice 2, as the review request states.

## To ship
Declare `tests/test_eng_improve.py` in `scripts/suite_final_segment.txt`, re-run the named suites to 0 failing, and (recommended) add a MIN_EFFECT boundary test.
