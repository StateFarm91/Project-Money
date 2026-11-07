# Independent review: visual stack opus2/v3-on-v1 @ 8427e777 (base 7c42e706)

Scope: `git log 7c42e706..8427e777`. In order: V1 (codex/v1-craft-enum @ ded427f6, about 55 commits), V2 (18079a8c, dc23fe75, 68401744, 49ec59a4 and the adaptation 8bca3606), V4 (16d8ccfd), V5 (6feab785), and V3 (3577ae72, plus the map regeneration 8427e777).

How I ran it:
- **Worktrees:** throwaway worktrees at 8427e777, at ded427f6 (V1 baseline), a mutation copy, and a trial merge onto origin/claude/w6-INTEG1 @ b282afc7. All four were removed with `git worktree remove --force`. I committed and pushed nothing.
- **Python:** /home/user/bl-runs/venv-integ4/bin/python, from `brambleloop/`, with `PYTHONPATH=src:tests`.
- **pytest:** not installed. I ran pytest-style files through a minimal stand-in that I wrote. It provides `raises`, `mark.parametrize`, `monkeypatch` and `tmp_path`, and lives in `scratchpad/shim/`.
- **Network:** none. No paid provider was called, and I printed no secrets.

## Verdicts

| Unit | Verdict | Why |
|---|---|---|
| V1 (ded427f6) | SHIP as reviewed here, with caveats | Its pytest-style tests pass under the stand-in. The test_w4_visnext2 drift failures are pre-existing and identical at ded427f6. I did not review its ~4.6k lines line by line. |
| V2 (+8bca3606) | **DO NOT SHIP** | N1: on the stack, V1's own test `test_codex_v1_obscured_craft` goes from PASS to FAIL. N2: the vessel path raises on undecodable bytes. N3: 8bca3606's session changes are untested, and 3 mutants survive. The fixes for prior findings F1–F7 are all confirmed. |
| V4 (16d8ccfd) | SHIP | Inert until the owner approves a room. Fails closed. 2/2 mutants killed. |
| V5 (6feab785) | SHIP | Not wired into any gate. Unreadable cases give UNKNOWN. 3/3 mutants killed. |
| V3 (3577ae72, 8427e777) | SHIP-with-fix (N4 should be fixed before any caller enables fixtures) | Production stays UNKNOWN. 7/7 mutants killed. A fixture PASS is a literal `PASS`, and its label is dropped in the may_export evidence (N4). |
| **Overall stack** | **DO NOT SHIP** | The suite is red (N1). The stack also does not merge cleanly onto INTEG1, where the V0 gate lives (N5). |

## Findings by severity

### N1. HIGH (process / correctness): V2 turns V1's deterministic FAIL into UNKNOWN, and V1's test goes red

- **Test:** `tests/test_codex_v1_obscured_craft.py:18` asserts `fidelity.verify_anchor(b"not an image", build_basket("small"))["status"] == "FAIL"`.
  - At ded427f6: 1 passed.
  - At 8427e777: 0 passed, 1 failed (AssertionError).
- **Cause:** `fidelity.py:1157-1163` (V2). For a vessel with no `side` view, `verify_anchor` returns UNKNOWN `vessel_views` before it ever decodes the bytes. A corrupt or non-image anchor is no longer a deterministic FAIL. It becomes UNKNOWN, which is a hold for capability instead of a defect routed to repair or regeneration.
- **Safety:** this is not fail-open, because UNKNOWN is never PASS.
- **Why it matters:**
  - It drops a deterministic failure that V1 deliberately pinned.
  - It shows the stack was declared green without running V1's pytest-style tests. Those files cannot run as plain scripts, and the file above has no `__main__` at all.
- **Fix:** decode both views first. An undecodable top or side is FAIL, as in the round path. Only then return UNKNOWN for a missing side view.

### N2. MEDIUM (fail-closed by exception, not by verdict): the vessel path raises on undecodable bytes

- **Location:** `vessel.py:140-159` (`_product_mask` calls `F._load` with no try), reached from `fidelity.py:1164`.
- **Repro:**
  - `verify_anchor(b"not an image", CIR, side=<good side>)` raises `PIL.UnidentifiedImageError`.
  - So do a good top with a junk side, and both views junk.
- **Contrast:** the round path wraps `_load` and returns a verdict.
- **Reachability today:** none. Production never supplies `side_data`; nothing calls `product_only(view="side")`. Once side views are wired, a corrupt candidate crashes `candidate_gates.fidelity_reading`, and therefore the whole gate evaluation, instead of recording FAIL.
- **Fix:** catch the decode error in `verify_top` and `verify_side` and return FAIL.

### N3. MEDIUM (test gap on the stated fix): 8bca3606's session and duplicate handling is untested

- **Test stub:** `test_v2_capability_redrive._follow` accepts `session=` and always returns `object()`. No test drives a real queue under a duplicate key, or a rollback.
- **Mutants that survive test_v2_capability_redrive:**
  - R_follow_nosession: `chain_successors.py`, where `follow` drops `session=session`. The job commits in its own transaction, so atomicity with the un-block is lost.
  - R_dup_swallow: `if session is not None: raise` changed to never raise. This is nearly equivalent, because V1's `restart` raises on `job is None` anyway.
  - R_exc_as_restarted: `redrive_capability_blocked` reports a rolled-back restart as `restarted`.
- **Behaviour is correct on probe.** `scratchpad/rv2/probe_dup.py` pre-inserts a Job holding the restart's `:e1` key, then runs the real `chain_successors.sweep` on the real JobQueue. Results:
  - `refused: restart not enqueued (DuplicateJob)`;
  - the run stays `blocked` with its reason intact;
  - there is no restart history;
  - there is exactly one job (the pre-existing one).
- **Verdict on the claim:** true, but only pinned by my probe. Add that probe as a test.

### N4. MEDIUM (latent; fixture evidence vs certification): a fixture identity PASS is a literal PASS, and its label is dropped downstream

- **What it returns:** `identity_check` (`vision_judges.py:253-266`) gives `status: "PASS"` with `fixture_only: True`. In `candidate_gates.exception_evidence` (`candidate_gates.py:~600`) only the status is copied, as `"identity": st.get("identity")`. `publication_verdict` feeds the same status into the POLICY_PROVENANCE gate (`worst(...)`).
- **Probe:** `scratchpad/rv2/probe_fixture.py`.
  - The identity check reads `PASS True [fixture_only_not_certification] ...`.
  - `exception_evidence.checks.identity` reads `PASS`.
  - No fixture marker appears anywhere in the exception evidence.
- **Mitigations today:**
  - No `src/` caller constructs `RealJudges` or `Adapters` with `embedder`, `qualification` or `allow_fixture`.
  - Laura publication still requires `canonical.asset_status == publication_approved`.
  - `ETSY_POLICY_STATUS` is UNKNOWN.
  - Nothing publishable results.
- **Why it still matters:**
  - The "shadow only" guard (`identity_gate._phase`) gives no separation in the current deployment, which is itself in shadow.
  - The record that `may_export` reads would show identity PASS with no fixture label.
- **Fix (either):**
  - make a fixture floor yield UNKNOWN with `fixture_would_pass: True`; or
  - propagate `fixture_only` into `exception_evidence`, and treat it as UNKNOWN in every gate that is fed.

### N5. MEDIUM (integration): the stack predates V0 and conflicts with it in the paid-generation path

- **V0 test:** `test_w5_v0_paid_provider_gate.py` does not exist on the stack. The V0 fix 0b3d54ee is in w6-INTEG1 but not in 8427e777.
- **Trial merge onto INTEG1 b282afc7:** conflicts in `creative/flux3_generator.py::generate` (V0 `gallery_scope` vs V1 nested-generation and run-key guards) and in `visual/image_production.py::_generate` (V0 `generation_gate_reason` and `spend_plan.guard` vs V1 `_begin_generation`). COORDINATION.json and suite_final_segment.txt also conflict.
- **My scratch resolution (both semantics kept; never committed):**
  - V0 gate: 52/52 passed;
  - V2 redrive, gallery and vessel suites, V3, V4, V5, V1 visual correctness and ownerimg: green;
  - visnext2: 8/4, the same as the base.
- **Integrator's job:** the conflict must be resolved by the integrator and re-reviewed, because it sits exactly on the spend and V0 gate path.
- **Liveness after V0:** `redrive` counts the gate as open from `gates_now` alone. If V0 adds conditions beyond the gate flag, a restarted run re-blocks with the same needle. It is then permanently "already re-driven once", even after the owner approves. This is safe, never a spend, but the run is stuck.

### N6. LOW (latent V0 bypass surface, V3)

- **Second judge:** `vision_judges.configured_second_transport` calls `SECOND_VISION_TRANSPORT(db)` and returns the result raw. Unlike the first judge, which defaults to `GatewayVisionJudge`, nothing requires the second transport to be `image_vision`-gated or budget-reserved.
- **Embedder:** `identity_gate.measure_biometric` calls `embedder.embed()` with no gate or spend reservation.
- **Today:** both are None or unconfigured. Wiring either must go through the V0 gate. A guard (assert the transport is gated) would make that structural.

### N7. LOW: carried over from the prior review

- **F8 (liveness):** still present. `_item_reading` reads only `anchor_consistency.reading.image_2`. A frame judged without that reading keeps the gallery UNKNOWN. This is safe.
- **F10:** R4 (experiment guard) is now tested. R5 and R7 are still not covered by the V2 tests; they are older guards.

### N8. LOW: V4 notes

- `same_room` is not wired into any gate; the commit title says "same-room check".
- The manifest accepts absolute paths, and accepts any non-empty `decision_id` string with no check against an owner decision record.
- A malformed `MANIFEST.json` raises in `flux3_generator` instead of being ignored. That is fail-closed, but it blocks generation.

### N9. LOW (test hygiene): test files that import pytest, which is not installed

All are added or modified by V1 in this stack:
- test_codex_v1_anchor_binding;
- test_codex_v1_blind_comparison;
- test_codex_v1_craft_enum;
- test_codex_v1_flux_concurrency;
- test_codex_v1_spend_guard;
- test_w4_visnext (one test, `restart_rolls_back_...`);
- test_w4_visnext2 (one test needs the `monkeypatch` fixture).

These have no `__main__`, so they report nothing when run as scripts:
- test_codex_v1_gallery_scope;
- test_codex_v1_obscured_craft;
- test_codex_v1_variant_base.

This is how N1 went unnoticed.

## Prior-review findings (INDEPENDENT_REVIEW_V2_6799f1d4)

I re-ran the original repro scripts, adapted, from `scratchpad/rv2/`.

| Prior finding | Status | Evidence |
|---|---|---|
| F1 HIGH: wrong colourway PASSes | FIXED | yellow/navy: palette 0 % FAIL, bands ['off'] FAIL. white/red: 66 % FAIL. End to end with the crochet judge: FAIL. Mutants F1_coverage0 and F1_nooff killed. |
| F2 HIGH: round CIR not checked, sides None gives NA | FIXED | key_basket with a square or hexagon top: FAIL. Round top: PASS. `sides=None`: UNKNOWN. M10 killed. |
| F3 MED-HIGH: tiny top view | FIXED | `MIN_TOP_RADIUS_PX=60`. Every 32–96 px case is UNKNOWN. M9 killed. |
| F4 MED: no wall model falls back to the round path | FIXED | A flared top round gives `vessel_anchor` UNKNOWN `basket:vessel_model`. Mutants killed. |
| F5 MED: prominence floor untested | FIXED | Lobed-circle test added. M1 (floor 0) killed: 2 failures. |
| F6 MED: share tolerance 0.6 | FIXED | Now 0.35, a new constant rather than a relaxation. R3b `[6,1,1,1,3]` gives FAIL. M4 killed. |
| F7 MED: gallery_ready not tested | FIXED | G1 (`!= FAIL`) and G4 (no blocker) are both killed by test_v2_gallery_consistency. |
| F8 LOW | Open | N7 |
| F9 LOW: unblocked with no job | FIXED | Atomic under V1's session; probe passes. Untested (N3). |
| F10 LOW | Partly fixed | R4 tested. R5 and R7 not. |

## Author claims

- **`_best` unions V1 and V2:** true. `structural` and `item_reading` both appear in the returned dict, and V1's scoping filters are intact.
- **`gallery_ready`:** true. It keeps V1's role-status, `set_check` and `ambiguous` conditions, and requires consistency `in (PASS, NA)`. The blocker is added to `publication_blockers`.
- **8bca3606:** true by probe, untested (N3).
- **G1 and G4 killed:** true.
- **test_w4_visnext2 failures are pre-existing:** confirmed. Under the plain runner it is 8/4 at both ded427f6 and 8427e777: the 3 prompt-builder 2.1.1 vs 2.1.0 drift failures plus 1 `monkeypatch` fixture artifact. Under the pytest stand-in the monkeypatch test passes on both, and only the drift failures remain. The stack does not cause them.
- **Thresholds:** no existing numeric constant in `src/` changes in 7c42e706..8427e777; every hit is a new constant. The test edits in ownerimg and visnext2 tighten PASS to UNKNOWN. V1's visnext edit switches to a no-edging CIR for the invented-edging negative; the assertion is unchanged.
- **Laura:** `canonical.FACE_SHA256`, the torso and full-length hashes, and `IDENTITY_ID laura-r2-a42aeac7` are unchanged. `canonical.verify()` has no problems. The diff does not touch canonical assets.
- **Paid generation:** no gate is opened and no gate definition changes. `redrive` re-checks gates, and the restarted job re-checks in `_generate`.

## Tests (stack 8427e777 unless noted)

| Test | Result |
|---|---|
| test_v2_capability_redrive | 0 failed |
| test_v2_gallery_consistency | 0 failed |
| test_v2_vessel_fidelity | 0 failed |
| test_v3_identity_qualification | 21/21 |
| test_v4_scene_references | 0 failed |
| test_v5_scale | 0 failed |
| test_w5_v1_visual_correctness | 32/32 |
| test_w4_fidelity | 22/22 |
| test_w4_ownerimg | 35/35 |
| test_w4_visnext (plain) | 21/1: the pytest import |
| test_w4_visnext (stand-in) | 22/22 (base 22/22) |
| test_w4_visnext2 (plain) | 8/4 (base 8/4, identical) |
| test_w4_visnext_frames | 7/7 |
| test_w4_visual_certified_gallery | 7/7 |
| test_w4_visual_gallery_frames | 10/10 |
| test_scale, test_gallery_escalation, test_opus2_photo_led_gallery, test_motif_fidelity | pass |
| test_codex_v1_anchor_binding (stand-in) | 11/11 |
| test_codex_v1_blind_comparison (stand-in) | 43/43 |
| test_codex_v1_craft_enum (stand-in) | 13/13 |
| test_codex_v1_flux_concurrency (stand-in) | 11/11 |
| test_codex_v1_spend_guard (stand-in) | 62/62 |
| test_codex_v1_gallery_scope (stand-in) | 4/4 |
| test_codex_v1_variant_base (stand-in) | 1/1 |
| **test_codex_v1_obscured_craft (stand-in)** | **0/1 FAIL** (base ded427f6: 1/1): N1 |
| test_w5_v0_paid_provider_gate | absent on the stack. 52/52 on the trial merge onto INTEG1 with my conflict resolution (N5). |

## Mutants (each applied alone in a copy worktree, then reverted)

| Mutant | Target | Result |
|---|---|---|
| M1 PEAK_PROMINENCE 0 | vessel | killed |
| M4 SHARE_REL_MAX 99 | vessel | killed |
| M9 MIN_TOP_RADIUS_PX 0 | vessel | killed |
| M10 sides None gives NA | vessel | killed |
| F1 coverage min 0 | vessel | killed |
| F1 no "off" rows | vessel | killed |
| F4 unmodelled vessel skipped | vessel | killed |
| F4 no-side falls through to the round path | vessel (fidelity alone: survives) | killed |
| G1 gallery_ready `!= FAIL` | gallery (ownerimg: survives) | killed |
| G4 no named blocker | gallery | killed |
| G2 unjudged pairs give PASS | gallery and ownerimg | killed |
| IR `_item_reading` returns None | gallery | killed |
| R_follow_nosession | redrive | **survived** |
| R_dup_swallow | redrive | **survived** (near-equivalent) |
| R_exc_as_restarted | redrive | **survived** |
| R_once_removed | redrive | killed |
| R_gate_open_ignored | redrive | killed |
| I_allow_fixture removed | V3 | killed |
| I_phase check removed | V3 | killed |
| I_production register removed | V3 | killed |
| I_fixture label removed | V3 | killed |
| I_worst becomes max | V3 | killed |
| I_reference sha check removed | V3 | killed |
| I_embedder identity check removed | V3 | killed |
| V4 sha check removed | V4 | killed |
| V4 decision_id not required | V4 | killed |
| V5 TOLERANCE 99 | V5 | killed |
| V5 unlisted anchor accepted | V5 | killed |
| V5 tiny-box guard removed | V5 | killed |

## Required before SHIP

1. **N1:** decode the vessel views first, so an undecodable anchor is FAIL. `test_codex_v1_obscured_craft` must pass.
2. **N2:** catch decode errors in `vessel.verify_top` and `verify_side` and return FAIL.
3. **N3:** add a real-queue duplicate and rollback test for the redrive. `scratchpad/rv2/probe_dup.py` is ready to convert. Kill R_follow_nosession and R_exc_as_restarted.
4. **N5:** rebase the stack onto INTEG1, resolve the flux3_generator and `_generate` conflicts keeping V0 `gallery_scope` and the gate reason, and re-run the V0 test and this review's suites.
5. **N4, before any caller enables fixtures:** a fixture floor must never surface as a bare PASS in the may_export or exception evidence.
6. **N9:** give every pytest-style test file a script runner, or install pytest in the venv, so the suite can actually be run.
