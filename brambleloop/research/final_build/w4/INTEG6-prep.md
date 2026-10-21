# INTEG6-prep (2026-10-21): Unified Laura on top of the listings release (preparation only)

Integrator: W-INTEG5, on the coordinator's instruction. Worktree `.claude/worktrees/W4-INTEG6-prep`,
branch `claude/w4-INTEG6-prep`, created from `origin/claude/w4-LISTREADY` b9137b5.
Production: b931d17, SHADOW.

**Preparation only:**
- no freeze, no full suite, no deploy;
- no production contact, no spend, no Railway change, no switch set.

The release order is first-sale (1580053), then listings (LISTREADY), then Laura (this branch).
`claude/final-candidate-bcce679` (INTEG5: Laura on b997efd) is superseded by this order. It was never
full-suite certified.

## 0. Lineage note for the listings release

LISTREADY b9137b5 descends from b997efd. It does **not** contain 1580053. 1580053 is b997efd plus
the release record f19b264e plus a merge of production b931d17, which is records only:
`git diff b997efd 1580053 -- brambleloop/src` is empty. So the listings release will need to merge
1580053, or production, to fast-forward from production (deploy_guard rule 1). This branch inherits
that merge when it is rebased on the certified listings head. The code under test is unaffected.

## 1. Merge

| # | Branch @ head | Merge commit | Conflicts and resolution |
|---|---|---|---|
| 1 | w4-LAURAONE-freeze @ f87e430 (freeze 2: all LOW/INFO review findings; contains c13e20d, a112da1, LAURACEO, VENICE-adult-wip). Merge base 6531769. | 84a5e10 | 5 conflicts, all resolved by keeping both sides (below) |
| - | INTEG6-prep harness fix | b857233 | §3 |

1. **`DECISION_LOG.md`, append-only.**
   - The LISTREADY block comes first, then the LAURAONE block. Order matters:
     LISTREADY's `### D-W4-LAUNCH-VISION-BATCH` is a sub-heading of the common
     `## D-W4-F852-AMEND`, so it must stay directly after that section.
   - 0 lines removed relative to either parent.
2. **`BUILD_STATE.md`, append-only.** Both new top entries are kept: LISTREADY's, then LAURAONE
   freeze 2's. 0 lines removed relative to either parent.
3. **`gateway/credentials.py`.**
   - Freeze 2 added `_effective_model(provider, env)` (S-4: for Venice, the selected model). Its
     fallback for other providers read `PROVIDERS[provider]["model"]`.
   - That fallback would raise `KeyError` for Anthropic on this base, because b997efd removed
     Anthropic's fixed `"model"` key in favour of `model_for` (routing's vision-judge model).
   - Resolution: the conflict takes freeze 2's `_effective_model(provider, env)` call, and its
     non-Venice fallback now calls `model_for(provider)`. Both behaviours are kept.
4. **`tests/test_cert_spend_hosts.py` DECLARED.** Resolved as in INTEG5 §2:
   - `credentials.py` is declared once (CREDHEALTH free checks plus Venice no-inference reads, billing
     basis UNKNOWN);
   - `venice.py` is added. The only place `VeniceProvider` is constructed is `laura_register.py:527`.
   - Freeze 2's new per-URL allowlist test (S-6) is kept and passes on the merged tree.
5. **`static/sw.js`.**
   - LISTREADY bumped the shell to `cc-shell-v21` (it adds `_launch_review.js` and `_shop_readings.js`).
   - LAURAONE bumped it to `cc-shell-v20` (it adds `laura_unified.js`).
   - The merged shell lists all three, and is neither side's shell, so `VERSION` is `cc-shell-v22`.
     `test_w4_launch_review_card` requires at least v20.

Files changed on both sides that auto-merged were checked by hand. The changes are disjoint and both
are present:
- **`gateway/anthropic.py`:** LISTREADY's launch-review batch grant inside `check_budget_cad`, and
  LAURAONE's N-9 no-redirect opener in `AnthropicProvider._send`.
- **`app/command_center/api.py` and `static/js/api.js`:** the launch-review and shop-observation
  routes, and the Laura converse, costs and unified routes.

No LISTREADY test mocks `urllib.request.urlopen` for an Anthropic call, so the N-9 opener cannot
bypass one of its mocks. `test_w4_fluxapi` and `test_w4_close5_vision_timeout` were adapted by
freeze 2.

**Regenerated with the tooling:**
- **`core/decision_index.json`** (`python -m brambleloop.core.decision_index`): 39 ids.
- **`autonomy/autonomy_map.json`** (`python -m brambleloop.autonomy.map --write`, to scratch): only
  `generated_at` differed, so it was left unchanged, as INTEG4 did.

## 2. Edits to existing tests

- **LAURAONE a112da1 and c13e20d:** audited in INTEG5.md §3 and §3a (`claude/w4-INTEG5`). None weakens
  a test, apart from the harness gap fixed in §3 below.
- **Freeze 2 (c13e20d..f87e430):**

| File | Edit | Verdict |
|---|---|---|
| `test_cert_spend_hosts.py` | new per-URL allowlist test for `credentials.py` and `venice.py` (S-6) | stricter |
| `test_w4_pl_reply.py` | asserts on the real Venice wire: no tools or tool_choice, `stream` false, roles exactly system then user, Venice's own system prompt off | stricter |
| `w4_pl_harness.py` | records raw wires; `_refuse` records the attempt and fails the context on exit (S-5), because the reply path turns any exception into PROVIDER_ERROR | stricter, with two defects fixed in §3 |
| `test_w4_close5_vision_timeout.py`, `test_w4_fluxapi.py` | the fakes also stand in for `venice.no_redirect_opener().open` (N-9), so keyed requests still hit the fake | equivalent (the same assertions; otherwise the fake would be bypassed) |
| `test_w4_laura_ceo.py`, `test_w4_laura_unified.py` | additions | additions only |

- **LISTREADY's own edits to existing tests** (`test_etsy_surfaces`, `test_w4_etsysurf`, cc_mock
  fixtures): these belong to the listings release and its independent review (b9137b5). On a read
  they follow FIRSTSALE2's new collectors. Each one asserts the stronger reading: the gate's own
  answer, and NO_EVIDENCE surfaces never counted as ready. None looked weakened. This is noted, not
  certified, by this integrator.

## 3. Harness defects fixed (b857233)

1. **Venice left live under `enabled(None)`.** This is carried over from INTEG5 e24f6f6, which is not
   in freeze 2.
   - With no stub and no caller mock, the harness still left Venice's real `_post` in place. It has
     no socket guard.
   - So under `enabled(None)`, a test that reached the model would make a real request to
     api.venice.ai with the dummy key.
   - Now Venice is refused, and recorded, just as Anthropic is, so S-5 fails the test. Callers' own
     Venice mocks are left in place.
2. **Restore order (new in freeze 2).**
   - The S-5 `AssertionError` was raised in `finally` before the env vars and `release_proven`
     were restored.
   - A failing test therefore left the register switch, the dummy key and the release stand-in set
     for every later test in the process.
   - It is now raised after everything is restored.

## 4. Migration proof (local PostgreSQL 16.15, port 5433, never production)

Output: `evidence_INTEG6prep/pg_migration_output.txt`, using the same three scripts as INTEG5. The
four code versions were `git archive`d: b931d17, 1580053, b9137b5 and b8572334.

**Full lazy surface** (every module imported, every Base and PrivateBase table created):

| Code | Tables | Added |
|---|---|---|
| b931d17 | 138 | — |
| 1580053 | 143 | +5 (INTEG4's) |
| LISTREADY | 145 | **+2 listings:** `launch_review_batches`, `launch_review_calls` |
| INTEG6-prep | **147** | **+2 Laura:** `laura_cost_events`, `laura_boundary_crossings` |

- No existing column was added, removed or altered at any step.
- A second boot is a no-op.
- **Rollback to LISTREADY, to 1580053 and to b931d17:** each boots the upgraded 147-table schema
  with no change.

**Plain `create_all`:** 131 → 136 → 136 → 136, with no change and clean rollbacks. All four new tables
are created lazily (`finance.launch_review.ensure_tables`, `laura.agency.models.ensure_tables`).

| table | columns |
|---|---|
| `launch_review_batches` | id, batch_id, decision_ref, agent, purpose, total_cap_cad, daily_cap_cad, frame_scope, releases, authorized_by, step_up, status, closed_why, created_at, expires_at, closed_at |
| `launch_review_calls` | id, batch_id, release, estimate_cad, reservation_id, at |
| `laura_cost_events` | id, at, kind, ref, cost_cad, measured, basis, model, purpose, outcome, detail |
| `laura_boundary_crossings` | id, at, session_public_id, approved_text, text_sha256, approval |

The private store has no schema change. The `xing` row kind is ignored by older code (INTEG5 §4).

## 5. Focused suites (venv-integ4, through testslot.sh; no full suite)

Tree: b857233. **50/53 suite files pass. 3 fail, all with the same cause, and that cause is in
LISTREADY, not Laura.**

**Failing:** one test in each of these suites:
- `test_w4_pl_leak`: test_reply_text_never_reaches_business_tables_logs_paid_calls_or_cache;
- `test_w4_venice`: 18/19;
- `test_w4_laura_unified`: 52/53.

**Error:** each one fails with `sqlite3.OperationalError: no such table: launch_review_batches` in
`core/continuity.export`, called from `_rows_of`.

**Cause.**
1. LISTREADY's `gateway/anthropic.check_budget_cad` imports `finance.launch_review` on every
   reservation. That import registers `launch_review_batches` and `launch_review_calls` on
   `Base.metadata`.
2. Those tables are created only lazily (`launch_review.ensure_tables`); `Database.create_all` does
   not import the module.
3. `continuity.export`, the backup path, walks every `Base` table. In any process that has made a
   model reservation, but has never touched a launch-review batch, the export raises.

**Reproduced on LISTREADY b9137b5 alone:** `test_w4_pl_leak` 1/2, the same error. LISTREADY's focused
set did not include these suites.

**Production impact if shipped as is:** after the first model call in a process, a continuity export
(backup) fails until a launch-review batch has been created.

**Suggested root fix, for the LISTREADY owner:** register the module in `Database.create_all`, as
INTEG3 did for the REL2 tables: `from ..finance import launch_review  # noqa: F401`. The tables are
then created at boot, and the migration stays additive (+2 tables at boot instead of lazily). Not
applied here: it belongs to the listings release and its review.

**All other suites pass:**
- **Laura:** laura_ceo 14/14, plact, pl_auth, pl_boundary, pl_budget, pl_continuity, pl_reply,
  priv_*, laura_cc_*, voice_spec.
- **Listings:** launch_review, launch_review_card, listready, firstsale2_surfaces,
  owner_observations, etsy_surfaces, etsysurf, integ4_shipped_records, k12_model_photography.
- **Freeze-2 adaptations:** close5_vision_timeout, fluxapi.
- **PWA:** pwa_static, ccpacket, ccux, ownerhome, cc_company.
- **Spend and security:** cert_spend_hosts (with the S-6 allowlist), credhealth, integ3_secfixes,
  integ4_secfixes, integ4_deliverable_routes, decision_index.
- **Required set:** vacuity, launch, cost_governance_wave2, search_hero_publish,
  cert_listing_frames, v11_autonomy_timeline.
