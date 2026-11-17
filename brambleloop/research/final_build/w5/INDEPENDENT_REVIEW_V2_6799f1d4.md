# Independent review: origin/opus2/v2-vessel-fidelity @ 6799f1d4

- **Base:** `claude/w6-INTEG1` @ f5c3976d. I reviewed the full `git diff f5c3976d 6799f1d4`: 11 files, +1046/-16.
- **Commits:** e30b5fa0 (P0-c), 22940594 (P1-d + P2-a) and 6799f1d4 (the jagged-flat test).
- **Worktree:** /home/user/bl-runs/wt-rev-v2, detached at 6799f1d4. Nothing was committed or pushed, and every mutant was reverted with `git checkout -- src`.
- **Python:** /home/user/bl-runs/venv-integ4/bin/python, run from `brambleloop/` with `PYTHONPATH=src`.
- **Repro scripts:** in /tmp/claude-0/-home-user-Project-Money/0aa334b9-5ba9-5fd2-9058-e50b4b8604ea/scratchpad/rev/:
  - repro_vessel.py
  - repro_key.py
  - repro_e2e.py
  - repro_floor.py
  - repro_tiny.py
  - repro_flare.py
  - mut.sh

## Verdict: DO NOT SHIP 6799f1d4

The P1-d and P2-a parts are sound. The P0-c vessel verifier is not, because it deterministically PASSes wrong baskets:

- a basket in the wrong colourway (F1);
- any outline for the round `key_basket` (F2);
- pentagon, octagon or round baskets in small images (F3).

With a vision judge that reads "crochet", F1 and F2 PASS the whole anchor gate (`fidelity.verify_anchor`). Without a judge the anchor stays UNKNOWN through `craft_texture`, so nothing ships today. Even so, the deterministic layer is supposed to be the authority, and here it is the part that is wrong.

## Test runs (one at a time)

| test | result |
|---|---|
| tests/test_v2_vessel_fidelity.py | 12 OK, 0 failed |
| tests/test_v2_gallery_consistency.py | 4 OK, 0 failed |
| tests/test_v2_capability_redrive.py | 3 OK, 0 failed |
| tests/test_w4_visnext2.py | 11 passed, 0 failed |
| tests/test_w4_ownerimg.py | 35 passed, 0 failed |

## Findings

### F1. HIGH: the vessel band check never compares colours with the palette, so a wrong-colourway basket PASSes

- **File:** `brambleloop/src/brambleloop/visual/vessel.py:205`, in `_bands`.
- **Cause:** each pixel is labelled by `argmin` over the CIR palette with no distance limit, so any colour maps to its nearest palette entry. `verify_side` then compares only the label sequence.
- **Missing check:** nothing replaces the old path's `basket:palette` check. The old path does have one, as `repro_flare.py` shows.
- **Repro (`repro_vessel.py` R1/R1b):** `basket_small` (cream #FAF6EB and wine #6E1F2A) drawn in yellow and navy, or in white and red, gives `PASS` for sides, wall_bands and rim.
- **Repro (`repro_e2e.py` E2):** the same image through `F.verify_anchor(top, CIR, side=side, judge=<crochet stub>)` gives **PASS**.
- **Fix:** give each row label a maximum dE76 to its palette colour, with UNKNOWN or FAIL beyond it. Also add a palette-coverage check like `basket:palette`.

### F2. HIGH: a round vessel CIR gets no outline check, and "no side count" is NA instead of UNKNOWN

- **File:** `vessel.py:239`. The line `if not model.sides: return NA` treats `sides == 0` (the twin says *circle*) the same as `sides is None` (the twin cannot tell).
- **Real product:** `launch0.cir_for("key_basket")` has `sides=0`.
- **Effect for a circle:** a square or hexagonal key basket passes the top view. `corner_count` should be required to find 0 corners.
- **Effect for unknown sides:** a `None` side count is a verification gap, and per the fail-closed rule it must be UNKNOWN, not NA. `worst()` drops NA, so the vessel can PASS with its shape unverified.
- **Repro (`repro_key.py`):** `V.verify(top_view(4 or 6), side_view(), key_basket)` gives `PASS`, with `basket:sides` NOT_APPLICABLE.
- **Repro (`repro_e2e.py` E1):** the same image through `verify_anchor` with the crochet stub judge gives **PASS**.
- **Mutant M10:** `if not model.sides` changed to `if model.sides is None` survives. No test has a round vessel.

### F3. MEDIUM-HIGH: the top view has no minimum-pixel guard, so small images PASS wrong side counts

- **File:** `vessel.py:234-245` (`verify_top`).
- **Inconsistency:** the side view has `MIN_PX_PER_ROW`, but the top view has nothing comparable. `MIN_PRODUCT_FRAC` (line 51) is a fraction of the frame, so it does not depend on size. Mutant M9 (`MIN_PRODUCT_FRAC = 0.0`) also survives.
- **Repro (`repro_tiny.py`):** each of these is counted as 6 corners, which is a PASS for the hexagon basket:
  - a 24 px pentagon (blurred);
  - a 24 or 48 px octagon;
  - a 32 px octagon (blurred);
  - a 48 px round outline (blurred).
- **Fix:** require a minimum mean boundary radius in pixels, or a minimum number of pixels per side, and return UNKNOWN below it.

### F4. MEDIUM: a vessel with no constant trailing wall silently falls back to the round check

- **File:** `vessel.py:100`. When `wall_n == 0` the code runs `continue`, so `is_vessel()` returns False and `fidelity.verify_anchor` (`fidelity.py:1084`) runs the old round-piece path for a twin whose shape is `vessel`.
- **Example:** a vessel whose top round flares, or an edging round with a changed count.
- **Contradiction:** the docstring and the test name ("never uses the round check") say this cannot happen.
- **Repro (`repro_flare.py`):** with the last ring's count raised by 6, the twin shape is still `vessel`, but `is_vessel` is False and `verify_anchor` returns `kind: anchor` with the checks `basket:aspect` and `basket:palette`.
- **Fix:** if the twin's shape is `vessel` but no wall can be modelled, return UNKNOWN, never the round path.
- **Today:** no current product hits this. Wall extraction for basket_small, basket_medium, basket_large and key_basket is correct: CIR rows and compiled rows line up 1:1 (22, 48 and 24 rows), and there are no per-op colours.

### F5. MEDIUM: the prominence-floor mutant is reachable, so the author's argument is incomplete

- **File:** `vessel.py:42-48`.
- **What the argument covers:** a bump on a *polygon's flat*. For that case it holds.
- **What it misses:** the floor's real job is to stop a nearly round outline from being counted as a polygon.
- **Repro (`repro_floor.py`):** a circle with a 6-lobed ripple, `r(1+a·cos6θ)`.
  - With `PEAK_PROMINENCE = 0.035`, every `a` in {0.005, 0.01, 0.015} gives 0 corners and FAIL. This is correct, because the shape is a round basket.
  - With `PEAK_PROMINENCE = 0.0`, every one gives **6 corners and PASS as a hexagon**, with and without blur+JPEG.
- **Test gap:** `./mut.sh M1_floor0` still gives "0 failed". The guard is load-bearing and untested.
- **Docstring:** the docstring of `test_a_jagged_flat_is_not_a_corner` ("only the prominence floor keeps it…") also contradicts the module comment.
- **Fix:** add the lobed-circle negative as a test.

### F6. MEDIUM: the wall-band share tolerance is loose and untested

- **File:** `vessel.py:269`. `worst_rel <= 0.6` lets each band's share be off by up to 60 %.
- **Repro (`repro_vessel.py` R3b):** rows `[6,1,1,1,3]` against the CIR's `[4,2,1,2,3]` give PASS. That is wrong stripe widths, with each wine stripe at half width.
- **Mutant M4:** `0.6` changed to `99` survives.

### F7. MEDIUM: the gallery_ready tightening is correct but no test protects it

- **Code:** `image_production.py:1644` now reads `consistency["status"] in (CG.PASS, CG.NA)`. This is correct, and it is the only consumer of `gallery_ready`. Line 1633 adds the named blocker.
- **Mutant G1:** reverting to `!= CG.FAIL` survives all five tests.
- **Mutant G4:** removing the blocker survives all five tests.
- **Fix:** add a readiness test that asserts `gallery_ready is False` and that the blocker is in `publication_blockers` when consistency is UNKNOWN.

### F8. LOW (liveness): an anchor frame never has an item reading

- **File:** `image_production.py:424` (`_item_reading`).
- **Cause:** `_item_reading` reads `anchor_consistency.reading.image_2`. The anchor itself never has that check, and neither does any frame whose consistency check was "not judged" without a reading.
- **Effect:** if the anchor role is in `chosen`, every pair with it stays unjudged, so the gallery stays UNKNOWN even after vision is funded. This is safe (never PASS) but may block forever. The anchor-side reading (`image_1`) could serve for the anchor.

### F9. LOW: P2-a "once" is once per gate for the run's lifetime, not once per gate opening

- **File:** `image_production.py:1338`.
- **Behaviour:** the history check refuses a second automatic restart after any later close and reopen. This is safe, just stricter than "once per opening". It also uses up a `MAX_RESTARTS` slot.
- **Edge case at :1290:** `restart()` writes the history and un-blocks the run *before* `follow()`. If `follow` hits `DuplicateJob` and returns None, the run is left unblocked with no job queued, and the run is never seen again. This is unlikely, because the key includes the epoch.

### F10. LOW (test gap): P2-a experiment and generator-gate guards are not tested by the V2 tests

- **Mutants that survive `test_v2_capability_redrive`:**
  - R4, which removes the experiment `#` guard;
  - R5, which removes the budget-stop guard;
  - R7, which removes the `_generate` image_generation gate check.
- **Why this is LOW:** these guards predate this branch and are reachable only through `restartable` and `_generate`. Older tests cover the gate text. No experiment or budget run can carry the needle `"image_generation gate closed"`, because experiments raise "experiment is not live" and controlled runs never raise the gate error.

## Answers to the questions

**Vessel fidelity**
- **Can a wrong basket PASS?** Yes:
  - the wrong colourway passes (F1);
  - any outline passes for a round CIR (F2);
  - small images pass wrong side counts (F3);
  - wrong stripe widths up to 60 % off pass (F6).
- **What is caught at normal size:**
  - wrong side count (5, 8 or 0 for a hexagon CIR);
  - three stripes, or swapped order;
  - an added rim band;
  - a rim bulging 1.15x.
- **Is UNKNOWN ever turned into PASS?** No.
  - `worst()` keeps UNKNOWN.
  - A missing side view returns UNKNOWN.
  - `craft_texture` without a judge returns UNKNOWN.
  - The exception is `sides is None`, which becomes NA, which `worst()` drops (F2).
- **Is wall-rounds extraction correct?** Yes, for all four current vessel CIRs: `basket_small` gives `[4,2,1,2,3]` over 12 wall rows and 10 base rows. It is fail-open when there is no constant trailing segment (F4).
- **Does fail-closed hold?**
  - On a noisy background, yes: it gives UNKNOWN (`repro_vessel.py` R4, p90 spread 73.3), and mutant M7 is killed.
  - On a small side view, yes: it gives UNKNOWN.
  - On a small top view, no (F3).

**Gallery readiness**
- **Is `gallery_ready` PASS-or-N/A only?** Yes, but it is untested (F7).
- **Are the two test edits a tightening only?** Yes.
  - `test_w4_ownerimg` changes PASS to UNKNOWN and adds an assertion on the blocker's prefix.
  - `test_w4_visnext2` changes PASS to UNKNOWN.
  - Every FAIL assertion is unchanged: the version, CIR and outfit mismatches in `test_incompatible_gallery_mix_is_refused`.
  - Disagreeing readings FAIL, and partial or unclear pairs stay unjudged. Mutants G2, G3 and G5 are killed.

**P2-a capability re-drive**
- **Can it call a generator or spend while the gate is closed?** No.
  - A closed gate leads to `waiting`.
  - `gates_now` treats an unreadable gate as closed.
  - The restarted job re-checks the gate in `_generate` at `image_production.py:504`.
  - Mutants R2 and R3 are killed.
- **Can it restart a FAILed, budget-stopped or experiment run?** No. FAILed runs are refused (R6 killed). Budget stops and owner blocks are never considered, and `restartable` refuses budget stops, experiments and the restart cap.
- **Once?** Yes, once per gate for the run's lifetime, which is stricter than once per opening (F9). Mutant R1 is killed.

**Other questions**
- **Laura:** untouched. The diff does not touch Laura, identity, outfit, asset or config files. `product_only` changes only the product scene, and `features_laura=False` is unchanged.
- **Paid generation:** still OFF. Nothing in the diff opens a gate or changes a gate definition. The P2-a test stubs `gates_now` only.
- **The prominence-floor mutant:** not unreachable (F5).

**Tests:** the mutation results are below. The ones that survive point to the untested guards.

| Mutant | Target test | Result |
|---|---|---|
| M1 floor=0 | vessel | **survives** |
| M2 no side-view UNKNOWN | vessel | killed |
| M3 no MIN_PX_PER_ROW | vessel | killed |
| M4 share tol 99 | vessel | **survives** |
| M5 RIM_WIDTH_RATIO 1.5 | vessel | killed |
| M6 extra_top not rim FAIL | vessel | killed |
| M7 no bg-spread check | vessel | killed |
| M8 sides `>=` | vessel | killed |
| M9 MIN_PRODUCT_FRAC 0 | vessel | **survives** |
| M10 sides None-only NA | vessel | **survives** |
| G1 gallery_ready `!= FAIL` | gallery + ownerimg + visnext2 | **survives** |
| G2 unjudged → PASS | gallery | killed |
| G3 partial pair → compared | gallery | killed |
| G4 no named blocker | gallery + ownerimg + visnext2 | **survives** |
| G5 edging disagreement ignored | gallery | killed |
| R1 no once-guard | redrive | killed |
| R2 no open-gate check | redrive | killed |
| R3 any blocked reason | redrive | killed |
| R4 no experiment `#` guard | redrive | survives (older guard) |
| R5 no budget guard | redrive | survives (unreachable here) |
| R6 no FAIL guard | redrive | killed |
| R7 no `_generate` gate check | redrive | survives (older guard, covered elsewhere) |

## Required before SHIP

1. **F1:** a palette distance limit per band label, plus a palette or coverage check.
2. **F2:** `sides == 0` requires 0 corners, and `sides is None` gives UNKNOWN. Add a key_basket test.
3. **F3:** a minimum pixel size for the top view, giving UNKNOWN below it.
4. **F4:** a twin with `shape == "vessel"` but no wall model gives UNKNOWN, never the round path.
5. **Tests:** kill M1 (lobed-circle negative), M4, M10, G1 and G4.
