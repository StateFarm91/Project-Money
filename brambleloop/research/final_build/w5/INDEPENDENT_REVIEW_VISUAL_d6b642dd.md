# Independent DELTA review: visual stack on INTEG1 @ d6b642dd, and V6 @ 80765387

## Scope

- **Merge commit 03e87f0c:** 8427e777 merged with claude/w6-INTEG1 @ 5913931f.
- **Fix commit d6b642dd:** the fixes for N1–N5.
- **V6:** `d6b642dd..80765387`. These are two commits, 5011f8ab and 80765387, and both change tests only.

## How I ran it

- **Worktrees:** throwaway worktrees `wt-rv-vis2` and `wt-rv-vis2-mut` at 80765387. Both were removed with `git worktree remove --force`.
- **Python:** `/home/user/bl-runs/venv-integ4/bin/python`, run from `brambleloop/` with `PYTHONPATH=src:tests`.
- **pytest-style files:** run through the stand-in in `scratchpad/shim/`, marked "(stand-in)" below.
- **Restrictions kept:** no network, no paid provider, nothing committed or pushed. I did not touch `wt-k12`.

## Verdicts

| Unit | Verdict |
|---|---|
| **d6b642dd** (visual stack on INTEG1) | **SHIP.** N1, N2, N3 and N5 are fixed and verified, and the merge is correct. N4 is only partly fixed (D1). That is latent, because no `src/` caller enables fixtures, but it must be closed before any caller does. |
| **80765387** (V6) | **SHIP.** It changes tests only. It is honest about the V1-SCENE-END-BANDS stop, and its stated mutant is killed. |

## Status of N1–N9

| ID | Status | Evidence |
|---|---|---|
| N1 HIGH: undecodable vessel anchor read as UNKNOWN | **FIXED** | `fidelity.py:1158-1169` decodes the top view, and the side view if one is given, before the vessel_views UNKNOWN. `test_codex_v1_obscured_craft` passes 1/1 (stand-in). Mutants N1_nodecode, N1_skipside and N1_decode_unknown are killed. A probe of empty, truncated, 1x1, 1x4000, uniform and L-mode images never raises; junk or truncated data gives FAIL `decode`. |
| N2 MED: vessel path raises | **FIXED** | `vessel.py:140-151` wraps `F._load` in `_Undecodable`; `verify_top` and `verify_side` return FAIL. Mutants N2_top_unknown and N2_side_unknown are killed. The caller (`candidate_gates.py:346`) maps `b""` to None. |
| N3 MED: redrive session/duplicate handling untested | **FIXED** | Two real-queue tests were added. All three prior survivors are now killed: R_follow_nosession, R_dup_swallow, R_exc_as_restarted. |
| N4 MED: fixture PASS read as a bare PASS | **PARTIAL** | `exception_evidence` is fixed and tested; it lists `fixture_only_checks`. The `publication_verdict` path is untested (its mutant survives), and `technical_status`, `outcome` and the `unknown` list still count a fixture PASS as PASS. See D1. |
| N5 MED: conflicts with V0 | **FIXED** | The merge resolution is correct (see the merge section). The V0 test passes 52/52. The liveness concern is mostly moot: `gates_now("image_generation")` reads `gateway.images.usable`, and the redrive needle is a substring, so it still matches the V0-suffixed reason. |
| N6 LOW: second judge and embedder bypass V0 | OPEN | Not addressed. Both are still unconfigured in `src/`. |
| N7 LOW: F8 liveness; F10 R5/R7 untested | OPEN | Not addressed. |
| N8 LOW: V4 notes | OPEN | Not addressed. |
| N9 LOW: pytest-style test files with no runner | OPEN | `test_codex_v1_obscured_craft` still has no `__main__`, so N1's regression test still reports nothing under the plain runner. |

## New findings

### D1. MEDIUM (latent; the "fixture never reads as certification" rule): N4 is only half closed

**Not covered by `gate_status`:**
- `candidate_gates.py:527` computes `technical = worst(*(c["status"] ...))` from the raw statuses.
- `:546` builds the `unknown` list from the raw statuses.
- `:680-695` `laura_gate_order` copies the identity check; its status is PASS, with the label kept in `why`.

**What follows downstream:**
- `image_production.py:322` and `:1461` map a technical PASS to `outcome="accepted"`.
- `:1331` treats a role as ready when its technical status is PASS.
- `:431` ranks a technical PASS first.

**Probe (`scratchpad/rv3/probe_n4.py`):** with every check PASS except a fixture identity PASS:
- technical_status is **PASS**, and the `unknown` list is `[]`;
- `laura_gate canonical_identity` is PASS;
- publication is still blocked, correctly.

**Untested change:** the `publication_verdict` change (`:645`) has no test. Mutant N4_pubverdict_raw survives both test_v3_identity_qualification and test_v6_gallery_e2e. The probe shows the mutant removes the `never ran: POLICY_PROVENANCE` blocker, so publication is held only by the other blockers.

The test name `test_a_fixture_pass_is_unknown_in_every_gate_it_feeds` overstates what the test covers: it checks `exception_evidence` only.

**Reachability:** none today. `RealJudges(allow_fixture=...)` defaults to False, and no `src/` caller passes it.

**Fix:**
- use `gate_status` for `technical`, `unknown` and `laura_gate_order`, or mark the candidate `fixture_only`;
- add a `publication_verdict` assertion.

### D2. LOW (process): the merge dropped V1's four COORDINATION claims

The merged `COORDINATION.json` is byte-identical to INTEG1's. The stack's 67 added lines are gone:
- `CODEX-V1-POST-RIB-TRUTH`
- `CODEX-V1-ANCHOR-BINDING`
- `CODEX-V1-VARIANT-BASE-TRUTH`
- `CODEX-V1-CRAFT-ENUM-TRUTH`

None of the four appears on 80765387. If releasing the claims at integration is intended, say so in the commit message; otherwise restore them. There is no code impact.

### D3. LOW (a V0 test gap that predates this work, at exactly the merge line)

Two mutants survive `test_w5_v0_paid_provider_gate` (52/52):
- removing `gallery_scope` from `Flux3Generator.generate` (mutant M_noscope);
- passing `gallery_scope(None)` instead.

Neither the V0 test nor INTEG1 references flux3. Without the scope, FLUX 3 renders fall back to the `product:`/`job:` bucket instead of the run's own per-gallery bucket.

My probe (`scratchpad/rv3/probe_scope.py`) shows the merged code is correct:
- inside `generate`, `current_gallery()` is the run key;
- after `generate`, it is `shared`;
- a nested refusal keeps the outer key.

Add that probe as a test.

### D4. LOW (test fidelity after the merge)

`test_v2_capability_redrive.GATE_REASON` (line 31) uses the pre-V0 reason, `...may not be called`. The real reason now ends `(not_activated_by_owner: ...)`. The substring needle `image_generation gate closed` still matches, but no test pins the merged format.

## Merge-resolution verdict: CORRECT

- **`flux3_generator.generate`:** V1's `_refresh_after_fork`, nested-generation refusal and run-key contextvars wrap V0's `gallery_scope(self.current_run_key)`. The scope sits inside the `try`, so it is entered before the key reset in `finally`. Verified by probe.
- **`image_production._generate`:**
  - V0's `generation_gate_reason(db)` is in the `CapabilityBlocked` message.
  - V0's inline `spend_plan.guard` is replaced by V1's `_begin_generation` (`:530-556`). That function runs the same `spend_plan.guard(_spend_plan(), spent_cad, calls_made, next_cost)` under a `SELECT ... FOR UPDATE`, maps `PlanRefused` to `BudgetStop`, and counts the call atomically.
  - V1's `paid and next_cost == 0` BudgetStop is kept.
  - `test_codex_v1_spend_guard` passes 62/62 (stand-in) and `test_codex_v1_flux_concurrency` 11/11 (stand-in).
- **Nothing from INTEG1 was dropped.** Every file that differs between 5913931f and 03e87f0c was also changed by the stack. For the other files both sides touched (`suite_final_segment.txt`, `api.py`, `release.py`), the merge delta equals the stack's own delta exactly. `suite_final_segment.txt` keeps all six INTEG1 lines plus V1's.
- **Fix commit:**
  - The autonomy map regenerates identically (only `generated_at` differs).
  - No numeric threshold or constant is removed or relaxed.
  - Laura: `IDENTITY_ID` is `laura-r2-a42aeac7` and `canonical.verify()` returns ok. No canonical or Laura file is touched.

## V6 (80765387)

- It changes tests only: `tests/test_v6_gallery_e2e.py`, 653 lines.
- **What is real:** the queue, the handlers and the deterministic verifiers. The generator is `Flux3Generator` on `StubRenderer`, with `paid=False` and spend 0.0.
- **The decision is reflected as answered, (a):** the run stops at `owner_card` and is `blocked` on the three in-scene roles, which are UNKNOWN on product_truth only (craft_texture, with V1's end-band reason). `approve()` is refused. V1-SCENE-END-BANDS is in REMAINING_GATES. Nothing is enqueued for listing, store or Etsy.
- **Room manifest:** the swap is restored in `finally`, and the test asserts the committed manifest is still empty.
- **Stated mutant:** V6_promote (`verify_lifestyle` with `end_bands_verified=True`) is killed by 3 tests, as claimed.
- **A wording point, not a defect:** the 5011f8ab message says the run reaches `ready_for_owner_review`, and 80765387 supersedes that.

## Tests (tree 80765387)

| Test | Result |
|---|---|
| test_codex_v1_obscured_craft (stand-in) | 1/1 (was 0/1 at 8427e777) |
| test_v2_capability_redrive | 0 failed (includes the 2 new real-queue tests) |
| test_v2_gallery_consistency | 0 failed |
| test_v2_vessel_fidelity | 0 failed (includes the new decode test) |
| test_v3_identity_qualification | 22/22 |
| test_v6_gallery_e2e | 10/10 |
| test_w5_v0_paid_provider_gate | 52/52 |
| test_w5_v1_visual_correctness | 32/32 |
| test_w6_fix_only_rebuild | 0 failures |
| test_codex_v1_spend_guard / flux_concurrency / gallery_scope (stand-in) | 62/62, 11/11, 4/4 |
| test_w3_k12_model_photography | 9/10 (see below) |

The test_w3_k12_model_photography failure is `test_f212_generate_attaches_receipt_and_refuses_unprovable_conditioning`, with `ImagesGateRefused [not_activated_by_owner] nano-banana-2 is not activated by the owner for generation`. This is the expected V0 not_activated failure that claude/w6-k12-v0-activation fixes; it is not caused by this stack.

## Mutants (each applied alone in the copy worktree, then reverted)

| Mutant | Target | Result |
|---|---|---|
| R_follow_nosession | chain_successors follow | **killed** (survived before) |
| R_dup_swallow | chain_successors re-raise | **killed** (survived before) |
| R_exc_as_restarted | redrive rollback reported as `restarted` | **killed** (survived before) |
| N1_nodecode | the decode loop removed | killed (vessel test and obscured_craft) |
| N1_skipside | side view never decoded | killed |
| N1_decode_unknown | decode gives UNKNOWN | killed (both tests) |
| N2_top_unknown | `verify_top` decode gives UNKNOWN | killed |
| N2_side_unknown | `verify_side` decode gives UNKNOWN | killed |
| N4_gate_status_raw | `gate_status` ignores `fixture_only` | killed |
| N4_excev_raw | `exception_evidence` uses raw status | killed |
| **N4_pubverdict_raw** | `publication_verdict` uses raw status | **SURVIVED** (v3 22/22, v6 10/10): D1 |
| M_noscope | merge: `gallery_scope` removed | **SURVIVED** the V0 test: D3 (V0 gap from before this work) |
| M_scope_none | merge: `gallery_scope(None)` | **SURVIVED** the V0 test: D3 |
| M_noreason | merge: `generation_gate_reason` dropped | killed (V0 51/52) |
| V6_promote | `verify_lifestyle` promotes the end bands | killed (v6 7/3) |

## Recommended follow-ups (none blocks SHADOW)

1. **D1:** apply `gate_status` to `technical_status`, `unknown` and `laura_gate_order`, and add a `publication_verdict` assertion. Do this before any caller enables fixtures.
2. **D3:** add `probe_scope.py` as a test of the FLUX 3 `gallery_scope`.
3. **D2:** restore the V1 COORDINATION claims, or state that they were released.
4. **N9:** add a `__main__` runner to `test_codex_v1_obscured_craft` and the other pytest-style files, or install pytest.
5. **D4**, N6, N7 and N8 as before.

Probe scripts are in `/tmp/claude-0/-home-user-Project-Money/0aa334b9-5ba9-5fd2-9058-e50b4b8604ea/scratchpad/rv3/`: probe_n4.py, probe_n2.py, probe_scope.py, mut3.sh and the logs.
