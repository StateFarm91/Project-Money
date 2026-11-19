# Review request: ENG-FAMILIES slice one (`eng/families`)

**Base:** `origin/claude/w6-INTEG2` @ a35ad302. Nothing is deployed. `BRAMBLELOOP_PHASE` and
`STAGE_A_ENABLED` are untouched. Nothing was spent, and there were no network calls beyond git.

## The gap

`radar.intake` admitted a researched concept only as a flat rows panel
(`SUPPORTED_CONSTRUCTIONS = ("flat_rows",)`). Yet `cir.draft` already drafts radar concepts
through `fallback_constructions.plan` into verified engines. A researched basket was refused,
while the same object from the static POOL drafted and certified as a basket.

## What changed

- **`creative/construction_families.py`** (new):
  - `route()` asks `fallback_constructions.plan`, the function `cir.draft` itself calls, which
    family the concept drafts. It adds no routing rule of its own.
  - It holds the concept when the declared form and construction name a different family
    (mislabel), when the engine refuses the title, or when the family isn't `verified` or
    `physical_gate`.
  - Every hold reason starts `construction_unsupported:<family>`.
  - `FAMILIES` / `UNBUILT` hold each family's status, the proving test, the sizes with their
    source, and the gaps. `draft_hold()` labels `cir.draft` refusals with the same family.
- **`radar/intake.py`**: `construction_verdict` delegates to `route()` and now takes the title,
  slug and rationale. The docstring and the risk-class comment are corrected. Children's
  pre-check, originality, dedupe and size checks are unchanged.
- **`runtime/pipeline.py`**: `cir.draft`'s three construction refusals record
  `hold: construction_unsupported:<family>` in their outputs and in the audit.
- **`products/production_inventory.py`**:
  - New hold kind `construction_unsupported`, added to `HOLD_KINDS`, so
    `production_summary.held_by_reason` counts it.
  - Intake-held concepts appear as `research_candidate` rows with the hold. They are read
    read-only from `radar_concepts`; a missing table means no rows, and an unreadable table is
    reported without closing any gate.
  - A `cir.draft` construction refusal reads `research_approved` "held: …" instead of "CIR
    drafted; not yet compiled".
- **`research/final_build/w6/construction_families.md`**: the inventory table of every family
  and engine, with status, proving test and gaps (catalogue engines included).
- **`DECISION_LOG.md`**: D-ENG-FAMILIES-1.

## Admitted families (slice one)

| Family | Status | Proof (research-derived, non-POOL concept) |
|---|---|---|
| flat_panel | verified | runner → compile, twin, reverse, size check → **granted** |
| vessel | verified | basket in joined rounds → **granted** |
| tapestry | verified | check-chart tapestry basket, contrast colour per stitch → **granted** |
| panel_pair | physical_gate | cushion front and back, seamed → refused only `PHYSICAL_TEST_REQUIRED` (class C) |

**Held:**
- partial: pouch (`ASSET_COLOR_ABSENT` at certify), tote, cosy, stocking, triangle;
- none: amigurumi, mosaic, cable, motif, C2C, garment, ornament, hat, and others.

## Behaviour change to an existing test

In `test_w5_concept_intake::test_an_unsupported_construction_is_refused_with_its_reason`, the
basket worked in the round is no longer refused, because that is the point of this work. The
test now asserts:
- a basket in the placemat category is held `construction_unsupported:vessel` (mislabel);
- a cable runner is held `construction_unsupported:cable` (B-080).

## Defects found, not fixed (owned elsewhere)

- `gates/policy.py` `_IP_TERMS` matches substrings: "Fer**nba**nk" is refused `'nba'`. It fails
  closed.
- `pouch`: one-colour work against a two-colour hero asset.

## Guards, mutants, suites

### Guards

- **`construction_families.route`**:
  - declared family vs. drafted family (mislabel);
  - engine refusal held under the refusing engine's family;
  - admission only for `verified` / `physical_gate`.
- **`test_router_admits_only_verified_or_physical_gated_families`**: every admitted family must
  name a proof test that exists in `tests/test_eng_families.py`.
- **`test_router_family_table_is_the_report_...`**: the report must name every family in
  `FAMILIES` and `UNBUILT`.

### Mutants

Applied one at a time with `PYTHONDONTWRITEBYTECODE=1`, running `tests/test_eng_families.py`.
**All 10 killed.**

| # | Mutant | Killed by |
|---|---|---|
| M1 | admit `partial` families | router + held tests |
| M2 | drop the declared-vs-drafted mismatch check | held test (tapestry with no claim; basket in placemat) |
| M3 | flat declaration accepts a shaped route | held test (flat pet mat titled "Cat Bed") |
| M4 | engine refusal admitted | held test (reason names the refusing engine) |
| M5 | inventory drops intake holds | held test (inventory row and hold) |
| M6 | inventory drops `cir.draft` construction holds | draft-hold inventory test |
| M7 | `cir.draft` refusal not labelled | draft-hold inventory test |
| M8 | hold prefix not parsed | held + children's tests |
| M9 | refusal label ignores the refusing engine | held test ("Tabby Cat Bed" → vessel) |
| M10 | children's pre-check skipped in intake | children's test |

### Suites

Run `20261119T153650Z-22910`: **22 suites, 367 passing, 0 failing**, 1150 s. The tree under
test is the content of commit 2ed3294d; no edits were made after the run started.

Command: `JOBS=4 SUITE_REGISTRY=0 run_tests.sh`. Suites run:

- **Touched:** test_eng_families (new, 9), test_w5_concept_intake,
  test_w5_a4a_research_to_concept, test_opus2_draft_constructions, test_w5_inventory,
  test_fallback_draft_provenance, test_w4_c03_fallback, test_w5_a7_supply_stall,
  test_w6_fix_only_rebuild, test_cadence_spread.
- **Required guards:** test_vacuity, test_w3_tmp_hygiene, test_w4_resume_runner,
  test_w4_c12_wiring, test_v11_autonomy_timeline, test_etsy_oauth_callback,
  test_w4_fmbatch1_retention_guard, test_w4_adopt_manual_listing, test_cert_spend_hosts,
  test_s1_product_truth_3, test_seasonal_cycle, test_prospecting.

`test_eng_families` reads `date.today()`, so it is listed in `scripts/suite_final_segment.txt`
just before `test_product_run`. No new job type and no new audit action, so there is no
retention or registry change.
