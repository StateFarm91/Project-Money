# Creative Standard diagnosis — why emotional_appeal killed 11/11 (W4-CREATIVE, 2026-10-07)

## Symptom
Command Center "Creative gate": 11 products audited, 0 survived, dominant failure `emotional_appeal`
(`app/main.py::_creative`, `app/dashboard_truth.py::creative_survivors` → `creative.audit.audit_catalogue`).
Because `dashboard_truth.launch_inventory` requires `creative_gate_survivor`, no catalogue product could
ever be launch-cleared.

## Causal chain (evidence: code + rerun)
1. `products/builder.py::Design` has fields slug, title, motif, palette, width, repeats, gauge, yarn, note.
   It has **no field** for recipient, occasion, feeling or function.
2. `creative/audit.py::concept_from_design` maps literally and hard-codes `function=""`, `feeling="cosy"`,
   recipient `self` and occasion `everyday` unless the slug contains a hint.
3. `creative/jury.py::weak_emotional_appeal` rejects when (a) recipient=self ∧ occasion=everyday ∧
   feeling∈{cosy, serene}, or (b) `function` is empty or under 3 words.
4. Branch (b) fires for **all 11** (function is always ""); branch (a) also fires for 3 (placemats,
   pressed-flower, wall hanging). One rejection ends a concept, so survival is 0 **by construction**.
   No other critic fired: the death count was `{"emotional_appeal": 11}`.
5. The input that would satisfy the gate (a stated function and a non-default person/moment) was
   **never produced by any stage** for this cohort. The LLM tournament/expedition path *does* ask for
   `function` (`prospecting.py`), but that cohort is separate (F-188) and has no runs in shadow.

## Is the gate defective?
No. It reads `function`, which the generator never wrote — a generator/design-process gap, not a gate
defect. Absence of a stated purpose is the failure the critic exists to name (it is not an
UNKNOWN-scored-as-zero measurement). Thresholds were left untouched; if anything the 3-word function
check is lenient, which is why the fix adds stricter validation on the *design* side. Proof the gate
is not weaker: `tests/test_w4_creative_brief.py::test_known_bad_candidates_still_rejected`,
`test_gate_thresholds_unchanged`, `test_raw_generator_reading_is_preserved`.

## Fix (design process, not standard)
`src/brambleloop/creative/emotional_brief.py` — a moment-first brief per product: recipient, occasion,
feeling, the scene (`moment`), `function`, `gifting` (required unless for oneself), ≥2 sensory hooks,
`handmade_life` ("Patterns for a More Handmade Life"), `laura_scene` (art direction for Visual, D-FB-16/17:
product-first where stronger), and a visual premise naming the real motif. Deterministic validation
refuses: the default triple; thin functions; social-proof/fabricated-buyer language; listing copy;
premise imagery the motif does not depict; a premise that does not name the motif; contradictions of
the slug's declared occasion/recipient; and the #109 emotional promise not executed in the object.
`audit.briefed_concept` applies a brief only when it validates; otherwise the product is judged as the
bare generator output it still is. The raw reading is kept beside the new one (`raw_generator`).

## Product-truth finding (held, not briefed)
Five titles promise imagery their motif does not depict, so no story may clear the gate for them until
Product retitles or redesigns (proposed titles in `emotional_brief.HELD`):
winter-village-graphghan (village / snowfall), autumn-oak-mosaic-throw (oak / fir-and-star),
nordic-star-ornaments (stars / snowfall), pressed-flower-motifs (flowers / heart-row),
cottage-wall-hanging (botanical / chevron-band).

## Result (shadow rerun, `research/final_build/w4/creative_audit_rerun.json`)
| Reading | Audited | Survived | Deaths |
|---|---|---|---|
| Before (raw generator) | 11 | 0 | emotional_appeal 11 |
| After (briefed catalogue) | 11 | 6 (needs_taste) | emotional_appeal 5 (the 5 held) |
| New moment-first candidates | 8 | 8 (needs_taste) | none; all ≥ clone threshold from catalogue |

Survivors are `needs_taste`: structurally clean, **not approved** — thumbnail legibility and craft
impression still require a vision judgement that does not exist in shadow. New candidates are concept
stage only (no CIR, pattern, listing or photo).

## r2 (2026-10-07): the whole gate, and exactly what clears `needs_taste`

**Second defect in the design process.** The jury is one of eleven checks in
`preengineering.gate_concept`, the gate `radar.score` and `cir.draft` actually call. Run through
it, the 8 "surviving" candidates were all **REFUSED** on deterministic grounds the jury reading
never showed: no thumbnail storyboard (#88, 8/8), a generic tube/pouch form with no silhouette
qualifier (#108, 2), Christmas/spring concepts declaring no season-grammar motif (#110, 3).
Fix (design process, gate unchanged): `emotional_brief.GATE_BRIEFS` writes storyboard, named
techniques, grammar motifs and qualifiers, with an honesty check (`gate_brief_problems`: a
storyboard may not show imagery the motif does not depict). Two candidates were redesigned
rather than dressed up: the advent garland's pockets became mittens (snow alone is the saturated
motif), the kneeler's lattice became a tulip trellis. Result: **8/8 WAITING, 0 failed checks**;
each waits only on `image_vision` (+ `benchmark_observation`; + grid for the LONG wrap).
Proof: `test_candidates_fail_no_deterministic_check`, `test_without_the_design_brief_the_same_gate_refuses`.
The candidate gate now compares against the briefed catalogue (stricter sameness, not looser).

**What clears `needs_taste`: a measurable gate, not an owner taste review.** No code path
accepts an owner verdict (B-137). It clears when, for the candidate's slug: (1) a concept board
with a content digest is on file (`intake.board_for`/`board_digest_for`; `board.make_board`
renders one from a prototype twin, so it needs a CIR first); (2) `gateway.anthropic.vision_usable`
is true (production: "no vision probe has succeeded"); (3) `intake.judge_held` records a
`concept.judged` row naming its judge, bound to that board's sha256, with
`thumbnail_reads_small=true` and `craft_impression >= 3.5` (bar unchanged); (4) LONG/FLAGSHIP
only: `creative.grid_tournament` verdict clear; (5) novelty needs observed competitor listings
(production holds 441; shadow has none). `regate_held` then re-presents the winner automatically.
`test_needs_taste_clears_only_on_a_recorded_judgement` proves the mechanism with fixture values
(passed at 4.0, refused at 3.0 or thumbnail false); nothing in the design process writes them.

**Demand evidence (W4-MJS `MJS_FINDINGS.json`, cited by digest, proxy ≠ measurement).** Queue for
engineering: first-christmas-stocking (stockings underserved, median favourites 1472.5 proxy;
Christmas window open; Christmas-stocking arena uncovered, observed) → reading-nook-cable-wrap
(garments 1701 proxy; arena uncovered) → tea cosy (kitchen/bath uncovered) → advent garland
(seasonality) → four with no matching finding (UNMEASURED, not zero).

| Reading | Before | After |
|---|---|---|
| Catalogue (Creative Standard, jury) | 0/11 survive (emotional_appeal 11) | 6/11 needs_taste; 5 held for Product Truth retitle |
| New candidates, full pre-engineering gate | 8/8 refused (deterministic) | 8/8 waiting (vision only), 0 refused |
| Approved / engineered | 0 | 0 — honestly: no eyes exist in shadow |

Artefact: `creative_gate_r2.json` (temp-DB runtime proof: cadence `persist_catalogue_audit` deaths
`{emotional_appeal: 5}`, `dashboard_truth.creative_survivors` count 6/11).

## r3 (W4-CREATIVE2, 2026-10-07): the five holds released, holds made self-checking
W4-PIPE/PIPE3 retitled the five held products to what their motif depicts (relief fabric:
double crochet above a single-crochet ground, one colour per row). `title_conflicts` on each
released title is empty: Winter Snowfall Relief Throw / snowfall, Fir and Star Relief Throw /
fir-and-star, Nordic Snowflake Ornament Set (6) / snowfall, Heart Applique Motif Library (12) /
heart-row, Cottage Chevron Wall Hanging / chevron-band. Each now carries a moment-first brief in
`CATALOGUE_BRIEFS` that `validate` accepts (the validator caught and refused one draft premise,
"for a first tree", because the snowfall motif depicts no tree). `HELD` is empty; a hold is
self-checking (`stale_holds`, `test_every_hold_is_live`) so a stale hold fails CI.

| Reading (scratch DB, cadence + dashboard) | Before | After |
|---|---|---|
| Catalogue survivors | 6/11 (emotional_appeal 5) | 11/11 needs_taste, 0 deaths |
| Approved | 0 | 0 — needs_taste still waits on a recorded vision judgement |

Artefact: `creative_gate_r3.json` (proof: `creative_gate_r3_proof.py`).
