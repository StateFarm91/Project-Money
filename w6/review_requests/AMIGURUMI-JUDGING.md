# AMIGURUMI-JUDGING: an amigurumi concept from scan evidence is judged and drafted unaided

- **Branch:** `eng/amigurumi-judging`, cut from `claude/w6-release-19h8` (a117ed2).
- **Status:** NOT merged and NOT deployed. Production is unchanged and no production row was
  read. No PR was opened, and nothing was pushed to `claude/repository-setup-nc9x6o`.
- **Decision:** D-ENG-AMIGURUMI-JUDGING (DECISION_LOG). BUILD_STATE has its entry at the top.
- **New module:** `brambleloop/src/brambleloop/creative/toy_board.py`.
- **New suite:** `brambleloop/tests/test_amigurumi_judging.py` (11 tests).

## What the judging step waited for

SUPPLY-LANE row 4 named the problem: "amigurumi concepts remain unjudged, pending a toy render".
The chain looks like this:

```
radar.concept_pool / radar.concept_intake  -> approved concept (from the scans)
radar.score -> pre-engineering gate WAITING on image_vision (#88 grid read, #83 craft)
mjs.seasonal_sentinel -> regate_held -> judge_radar_waiting
    board_for(slug) == ""  ->  file_radar_board -> creative.board.make_board
        -> prototype.author: "'toy' has no finished size on file, so it cannot be prototyped"
    => held: board_image (no board could be drawn ...)              <-- every toy stopped here
```

The judge, the budget and the re-score already worked (NEW-PRODUCT-FLOW). What was missing was
the picture. `make_board` draws a prototype's twin fabric, and `disclosed_render` draws flat and
round pieces only. Neither can draw a shaped toy.

The stall reproduces on the real handlers. In the scan-derived pool, the frog
(`pool-garden-amigurumi-frog-student`) and the lamb route to `amigurumi_animal`. So do the
catalogue capybara, octopus, duckling, whale, frog and lamb. Every one of them was held on
`board_image` in every cycle.

## Why a FLUX render, and not a deterministic preview

I looked for an honest CIR-derived preview first. A stuffed animal is a 3-D form with appendages
crocheted in around it. The flat silhouette we could draw from round counts would be judged for
"craft impression" and "reads at grid size" on a picture that does not look like the product.
That is not honest in either direction, and a fabric swatch would be worse. SUPPLY-LANE already
declined to fake one, and I agree.

So the board is ONE FLUX concept render. The order is what keeps it honest: **the CIR exists
first, and the picture is prompted from it**, never the other way round (Execution Directive:
never make a beauty image and ask a model for the instructions).

## How it works (`creative/toy_board.py`, called from `judge_radar_waiting`)

1. **The engine's draft, for CA$0.** The concept is drafted exactly as `cir.draft` will draft it:
   - inputs: the payload `radar.score` offers (scored seed + intake `gate_inputs` +
     `concept_geometry`);
   - route: `fallback_constructions.plan`;
   - builder: `animals.build`;
   - and the draft must compile.

   A concept with any other route gets no render. A hedgehog, a beanie or a lovey is never paid
   for (tested).
2. **Child-safety preconditions, before any spend.** The render is refused if any of these
   fails:
   - every crocheted-in piece clears the small-parts cylinder;
   - the body note says the face is embroidered with yarn only;
   - no material names a hard part (safety eye, button, bead, bell, wire, pellets...);
   - the premise names nothing the engine refuses (`animals.premise_refusal`);
   - the `age_suitability` and `features` statements exist.

   **The certification gate is untouched.** The drafted frog is still withheld ONLY for
   `PHYSICAL_TEST_REQUIRED` and `CHILD_SAFETY_PHYSICAL_EVIDENCE_UNKNOWN` (tested).
3. **The prompt comes from the compiled CIR only.**
   - It names: the animal, each piece and how many ("2 arms, 2 legs"), plain colour words for the
     CIR's two colours, the yarn weight, and the embroidered face (sleepy or straight-stitch).
   - It forbids: safety eyes, buttons, beads, accessories, clothing, text and logos.
   - It names no other shop or design, and it is deterministic for one CIR.
4. **Inside every existing cap.** The render goes through `gateway.images.generate`, so all of
   these apply, checked under the budget lock before any network I/O:
   - the owner's `flux-3-image:generation` activation (D-OWNER-APPROVE-ALL: CA$5/day, CA$40/month,
     CA$2.50 per gallery);
   - the code's image caps (60/day, 16 and CA$2.50 per gallery), in gallery
     `concept-board:<slug>`;
   - the company month;
   - the job-level paid-call replay (F-307).

   It also has its own lower caps: **2 renders per run and 4 per UTC day**, so concept boards
   never take a listing gallery's budget. It uses the 1k tier, about CA$0.068 a render.
   `flux_provider.readiness` must be READY first (key present + activation active); otherwise
   nothing is recorded or spent.
5. **Paid once (no repeat on redrive).** Before the provider is asked, a `creative.toy_render`
   REQUESTED row is written under the budget lock. After that:
   - **FILED:** the board is on file; later runs judge it and never render again.
   - **DECLINED:** the gate refused before anything was sent (activation, ceiling, cap, no key).
     Nothing was billed, so a later run may ask again. A decline does not use the per-run or
     per-day toy cap.
   - **PAID_UNFILED:** the work may have been billed (an exception after acceptance, a
     timeout). It is never bought again by the system, and the concept is held with that reason.
   - **REQUESTED with no outcome** (the process died mid-render): treated the same as
     PAID_UNFILED.

   `creative.toy_render` is registered in retention as `lifetime_total`, so pruning can never
   reopen a paid request.
6. **Disclosed, never a listing image.** The board is filed as `creative.concept_board`:
   - kind `ai_concept_render`;
   - disclosure: "an AI concept render (FLUX), prompted from the drafted CIR's ...; not a
     photograph, not the made toy, and never used in a listing";
   - it carries the CIR fingerprint and the prompt hash;
   - it is never written to `listing_asset` frames.

   The judgement is bound to its bytes (CB2-D01), as for every board.

After the judgement, the existing path is unchanged: `rescore_judged` → `radar.score` (the whole
pre-engineering gate again) → `supply.offer(draft:<slug>)` → `supply.admit` → `cir.draft`.

## Tests (`tests/test_amigurumi_judging.py`)

The production shape:
- Launch-0 is exhausted;
- the concept pool is built from the synthetic watchlist scans (`test_concepts100`), with
  answered research tasks;
- paid vision is open (activation + probe) with a FIXTURE judge;
- `flux-3-image:generation` is activated at exactly `owner_directives.ACTIVATIONS`' ceilings;
- the BFL key variable holds a dummy, and a FIXTURE transport stands in for the provider (no
  request leaves the process).

Only the cadence jobs are enqueued, and the real worker drains them.

| test | proves |
|---|---|
| `test_the_scan_derived_frog_is_an_animal_engine_concept` | the concept under test is generated from scans and routes to `amigurumi_animal` |
| `test_mutation_without_the_toy_board_the_frog_waits_on_board_image_forever` | the stall reproduces without the fix |
| `test_an_amigurumi_concept_from_scan_evidence_reaches_cir_draft_unaided_paid_once` | one disclosed render, prompted from the CIR; one BILLED gate row and one image CostEntry; judged on those bytes; `draft:<slug>` admitted and drafted on `amigurumi_animal`; 3 more cycles of redrive: no second render, no second cost, no second draft; the day cap held |
| `test_the_toy_is_still_withheld_at_certification_for_its_physical_evidence` | the child-safety gate is never bypassed |
| `test_a_render_that_may_have_been_paid_for_is_never_bought_again` | a timeout is held as PAID_UNFILED, and never re-asked |
| `test_a_crash_between_request_and_record_is_never_bought_again` | an orphaned REQUESTED row blocks every later render |
| `test_a_refusal_before_sending_is_declined_and_may_be_asked_again_later` | the per-gallery cap refuses first (nothing billed); a later run renders once |
| `test_the_daily_caps_hold` | the code's daily image cap and the provider's daily CA$ ceiling each refuse; declines never use the day's toy cap |
| `test_without_the_flux_activation_nothing_is_rendered_or_recorded` | no activation: nothing recorded or spent, held with "FLUX not ready" |
| `test_the_child_safety_preconditions_refuse_a_render_before_any_spend` | hard parts, a glued face and a "safety eyes" premise each refuse; nothing is claimed or sent |
| `test_a_toy_the_animal_engine_will_not_draft_is_never_rendered` | a hedgehog and a beanie are never rendered |

## Suite run

See the end of this file.

## Open / not verified

- **UNVERIFIED in production.** Two things are needed for the render, and one for the judgement:
  - the BFL key in the service environment (`BRAMBLELOOP_IMAGE_KEY_BFL`);
  - the D-OWNER-APPROVE-ALL flux activation row;
  - the **anthropic-vision** activation and probe for the judge (as NEW-PRODUCT-FLOW). That
    directive activates `openai-vision`, not `anthropic-vision`, and this branch does not route
    the radar judge elsewhere. **If anthropic-vision is closed, nothing is rendered:** the
    judge-call cap check comes before the render, and vision-closed concepts are held before
    any board is made.
- **No real FLUX render of a toy has been seen.** Whether a 1k FLUX render of "2 arms, 2 legs
  crocheted onto the body" looks like the engine's frog is unmeasured. The judge is asked about
  the concept's appeal, not fidelity. **The judgement is of an AI concept render, which may
  flatter the product; please weigh that.** A fidelity check of render against CIR is not built.
- **Lovey and ball-body toys are not covered.** Loveys (`classic-bear-lovey`,
  `cosy-bunny-lovey`) are still held on `board_image`. The ball-body bear already boards
  through its prototype form. Extending this to `FC.LOVEY` means reproducing that draft
  dispatch; it is a follow-up.
- **Cadence.** Judging runs on the daily `mjs.seasonal_sentinel`. At 4 toy renders a day, the
  7-toy engine-demand list clears in about 2 days.
- **Pre-existing failure.** `test_w4_fmbatch1_retention_guard` fails identically on the base
  (two `unresolved:` entries in `runtime/release*.py`). The new `creative.toy_render` action is
  classified, and the guard no longer lists it.

## Suite run (2026-11-21, dirty tree on a117ed2, run individually with `PYTHONPATH=src:tests`)

| suite | result |
|---|---|
| test_amigurumi_judging (new) | 11 passed, 0 failed |
| test_new_product_flow | 6 passed, 0 failed |
| test_supply_lane | 9 passed, 0 failed |
| test_concepts100 | exit 0, 0 failed |
| test_eng_animals | exit 0 |
| test_eng_plush | exit 0, 0 failed |
| test_eng_families | exit 0, 0 failures |
| test_w5_v0_paid_provider_gate | 52/52 |
| test_vacuity | exit 0 |
| test_compiler / test_reverse / test_twin | exit 0 |
| test_w4_fmbatch1_retention_guard | FAIL, identical on base a117ed2 (pre-existing `unresolved:` entries); `creative.toy_render` is classified |

Test edits outside the new suite: none.
