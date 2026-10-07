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
