# LEARN-PROOF-2 — every benchmark lesson now changes a later output

Branch `eng/learn-proof-2`, cut from `claude/batch19c-etsy` (c5d6df2), which already contains
`eng/learn-proof`. NOT merged, NOT deployed. Production is unchanged.

## What was asked

LEARN-PROOF stored all 14 teardown lessons but hooked only six of them (HC-L5, MM-L1, MM-L3,
MM-L4, MM-L6, MM-L7). The other eight were stored with `effect: None`, and the readback showed
them as `wired: 0`. This branch hooks each of the eight to a deterministic effect, and adds
two second effects that the brief asked for: MM-L3 chenille as a yarn class, and MM-L7 tension
guidance. Each hook has a before/after test on the same input.

## Model change

`BenchmarkLesson` gains `also: tuple[str, ...]` and an `effects` property, so one lesson can
switch on more than one hook. `effect` is unchanged for the six existing hooks. These all read
`effects`: `effects_of`, `EFFECT_DEPARTMENTS`, `record`, `readback.wired` and `note_pdf`.
Ingested evidence now carries `effects`, so the first ingestion after deployment updates all
14 rows once. After that, ingestion is idempotent again.

## Hooks added

| Lesson → dept | Effect | Where | Before → after on the same input |
|---|---|---|---|
| HC-L1 → pricing | `price_effective_not_strike` | `intel/serp.capture` | A payload with a listed price of CA$11.54 and a `sale_price` of CA$2.88 is stored at **11.54** before. After, it is stored at **2.88**, with `strike_price: 11.54` kept apart; no band reads `strike_price`. The `price_band` result differs. A payload with no effective price is unchanged, because a missing sale price does not mean "no discount". The hook records one evaluation per capture. |
| HC-L2 → product_creativity | `concept_cluster_rank` | `radar.scan` through `concept_rank_adjustments` | Before: no nudge. After: an amigurumi concept in the cosy farm-animal cluster gets +0.02, and the order flips (test). The animal is read from the concept's own words. |
| MM-L1 (extended) → market_radar | `concept_rank` | same | Adds the `chunky_chenille` trait the lesson names. The MM-L1 cap is still +0.04; together with HC-L2 the cap is +0.06. Only amigurumi concepts are moved. |
| HC-L3 → creative_assets | `asset_no_fake_photo_claims` | `seo/truth.validate_listing` (blocking) | Before: "with step by step photos" and the tag "photo tutorial" are not refused by any HC-L3 rule. After: both are `TERM_MISLEADING … HC-L3`. We have no physical sample, so we have no progress photos; our progress imagery is CIR diagrams labelled as diagrams. |
| HC-L4 → pattern_engineering | `pdf_component_grouped` | `pdf_standard.LESSON_RULES` `component_grouped` (amigurumi, >1 component) | Before: not required. After: each component's name must appear in the instructions in the CIR's order. The real template PDF of the amigurumi fixture passes. The same text with the last component's name removed fails the learned rule only. |
| HC-L6 → customer_experience | `delivery_pdf_not_link` | `integrations/etsy.EtsyClient._attach_file`, on the bytes about to be uploaded | Before: an HTML link page named `pattern-us.pdf` passes `digital_file_refusals`, which checks only the name and size, and is uploaded. After: it is refused because it does not start with `%PDF-` and reads as a web page. A truncated PDF (no `%%EOF`) and a file that does not match a given certified sha256 are also refused. A real engine PDF still uploads. |
| HC-L7 → seo_search | `seo_front_load_object` | `validate_listing` **soft** list | Before: nothing. After: `TITLE_NOT_FRONT_LOADED` when "pattern" is not within the first 60 characters, or when the title opens with easy/beginner/cute/gift/new/best/sale instead of the object. This is advice and never blocks. The badge half of HC-L7 ("beginner friendly" only on a certified beginner pattern) was already a base rule in `commerce.search.tag_truth`, so no new code was needed for it. |
| MM-L2 → pattern_engineering | `pdf_join_as_you_go` | `technique_appendix` entry, plus rule `join_as_you_go` | A seam whose method is `slst` or `pick_up` and that has a stated `at_round` is a crocheted-in join. For such a seam, both layouts print a "Joining as you go" entry in the techniques appendix. Before: the standard does not require it. After: it is required, and the same text without the entry fails the learned rule only. A fully sewn toy is not asked for it. |
| MM-L3 (second) → pattern_engineering | `yarn_chenille_class` | `pdf_standard.yarn_class` / `CHENILLE_CARE_NOTE`, plus rule `chenille_care` | Chenille is a yarn-model record covering class, the CIR's gauge, hook range (never above the stated hook), tension guidance, and a shedding and care note. Both layouts print the care note through `chunky_hook_range_text`. Before: not required. After: required; the engine PDF of a chenille scarf passes, and the same text without the note fails. |
| MM-L5 → creative_assets | `hero_hand_scale` | `visual/shot_plans.flux_campaign_for`, SCALE slot | Before: a toy's scale brief is "beside everyday objects". After: "held in one open hand … the same toy and colourway as the PDF cover". A pillow's brief is unchanged. |
| MM-L7 (second) → quality | `pdf_tension_guidance` | rule `tension_guidance` (any CIR with a gauge) | Before: not required. After: the gauge section must say "larger hook", "smaller hook" and "Swatch again". Both layouts already print these lines. The same text without them fails the learned rule only. The QA side (incidents and refusals classified as `missing_gauge->tension_complaints`) is unchanged from LEARN-PROOF. |

**Bytes never depend on the snapshot.** The renderers print the chenille care note and the
join-as-you-go entry whatever the process's learning snapshot holds. Each lesson switches on
only the *requirement*, as LEARN-PROOF did for the eye panel. If the snapshot decided the
printed content, the same certified CIR could hash differently in the worker and in the CLI,
and that would break hash-matched delivery (HC-L6).

## Readback

`learning.progress.readback` → `benchmark_lessons` is unchanged in shape. Every department
now has `wired ≥ 1`, so the reason "no decision hook reads this department's lessons" no
longer occurs. `applied` is a number only after that department's hook has run since
ingestion. Otherwise it is `UNKNOWN` with the reason: store unreadable, not ingested, or hook
not run. The tests assert that `UNKNOWN != 0` in every department that has not run, and that
a hook which ran and changed nothing reads `0`.

Where each department's count comes from:
- **Written directly:** market_radar and product_creativity (radar), pricing (SERP capture),
  quality (mine).
- **Buffered, then written by the worker's flush:** customer_experience (upload),
  creative_assets (campaign plan and listing), seo_search, and pattern_engineering /
  quality (PDF).

## Tests

`tests/test_learn_proof.py` now has 27 tests: the 17 from LEARN-PROOF, updated for the
model change, plus these ten:

- concept chenille and farm cluster;
- effective price through `serp.capture`;
- chenille yarn class and care note;
- tension guidance;
- component grouping;
- join-as-you-go;
- delivery through `EtsyClient._attach_file`;
- photo claims and front-loading;
- hand-scale campaign brief;
- the production readback after a partial run.

Fixtures only. Competitor content is never copied, and the existing no-competitor-wording test
still guards every statement. There is no sales data, no spend and no network.

## Limits, said plainly

- No lesson has been applied in production, and nothing here was deployed or read back from
  production.
- HC-L1 changes something only when the search payload carries an effective or sale price
  (`effective_price`, `sale_price`, `price_after_discount`, `discounted_price`). The sanctioned
  Etsy search payload may not carry one. When it does not, the hook records an evaluation and
  changes nothing, and the readback reads `0`, not a claim.
- HC-L3 is enforced on title and tags. Listing descriptions and alt text are not checked by
  this hook.
- HC-L4 checks the order of component names in the instructions. It does not check page
  layout.
- MM-L2 adds the explanation and the audit requirement. It does **not** add new compiler,
  twin or reverse validation of joined stitch counts. That is the larger capability the
  lesson names, and it remains open.
- MM-L5 changes the brief only. Whether a generated frame actually shows a hand is judged by
  the existing gallery gates, not by this hook.
- The upload hook, like the other pure hooks, notes into the process buffer. A note is counted
  only when the worker flushes it.
- Byte changes:
  - Engine and template PDFs of **chenille** products gain the care sentence.
  - Documents of CIRs with a crocheted-in join gain one appendix entry. None of the 14
    `launch0` builders that build in this checkout has such a join, so their bytes are
    unchanged.
  - Worsted and plain chunky documents are byte-identical.

## Suite run

Run `20261121T023222Z-3239` (`JOBS=4 SUITE_REGISTRY=0`) on code commit 55f4e9c, tree clean, py3.11 venv from
`requirements.lock` plus `requirements-test.lock`, 519 s. 33 suites: `test_vacuity`, `test_learn_proof`,
`test_pdf_standard`, `test_pdf_premium`, `test_pdf_template`, `test_pdf_diagrams`, `test_eng_plush`, `test_mine`,
`test_eng_learn`, `test_eng_learn_patterns`, `test_eng_learn_wiring`, `test_learning`, `test_v11_seo_truth`,
`test_w3_seo_strategy`, `test_r2_product_seo_unicode`, `test_w4_learn_loops`, `test_w4_learn_presale`,
`test_w4_readback_evidence`, `test_cert_learning`, `test_cert_preengineering`, `test_serp`, `test_w4_marketintel`,
`test_cert_intel_wave`, `test_vis_gallery_gates`, `test_etsy_publish`, `test_etsy_transport`, `test_etsy_exercise`,
`test_etsy_readback_observe`, `test_disclosed_certified_upload`, `test_draft_creation_durability`,
`test_cert_commerce`, `test_cert_publish_gates`, `test_w4_fmbatch1_readings_bus`.

**Result: `TOTAL PASSING: 601 ; suites failing: 0`.** `test_learn_proof` 27/27. The full suite was not run.
