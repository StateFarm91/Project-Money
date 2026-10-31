# W5-CONCEPT: evidence-backed concept intake

Branch: `claude/w5-CONCEPT` (from `origin/claude/w4-INTEG8-next` b0133916). Owner priority: P0
revenue-production workforce. Decisions: D-W5-CONCEPT and D-W4-OWNER-SEEDSHOPS in DECISION_LOG.

## The gap (verified)

Before this change, new products could only come from `radar/opportunity.py:POOL`, a static
hand-coded list of 34 `ConceptSeed`s. Three things happened, and none of them created a concept:

- `radar.scan` and `radar.score` scored POOL.
- `research.sweep` and `research.investigate` answered questions.
- `creative.family_engine` reported. When `intel.opportunity_review` and the family engine
  found demand that no POOL seed answered, the most they could record was
  `needs_original_design`.

So the factory could not create a new product without a code edit.

## Design

`src/brambleloop/radar/intake.py` defines a new `radar_concepts` table, created on first use
with `checkfirst` in the same way as `research_tasks`. The handler is `radar.concept_intake`
in `runtime/intel_ops.py`. It runs as the `concept_intake` cadence (market_radar, 6-hourly)
and is registered in the registry, authority, departments, orchestrate and WORK_KEYS.

The run is deterministic. It makes no model call and no network call, and costs CA$0.

```
answered research task  + concept proposal (intake.attach_proposal)   ┐
certified family, orders >= AMPLIFY_MIN_ORDERS, no declared next member ┘
   -> row PROPOSED (audit concept.intake_proposed)
   -> validate (every reason collected, none short-circuited)
   -> APPROVED (concept.intake_approved) -> radar.score enqueued, key score:<slug>:<date>
                                            (concept.intake_handoff)
      or REFUSED (concept.intake_refused, with reasons)
```

### Evidence

The intake never fabricates evidence. The research proposal's `evidence` must cite the task's
own findings (`F..`) or sources (`S..`). The task must be ANSWERED, its conclusion must not be
unresolved, and it must not have expired (F-433). Each cited item must carry a source date,
and at least one must be fact-grade.

Quality is computed as follows:

- **Inputs:** the recorded confidence weight (high 0.9, medium 0.65, low 0.35), the share of
  cited evidence that is fact-grade, and freshness. Freshness is measured against the domain's
  own window from `research.freshness_for`.
- **Thresholds:** the concept is refused below 0.40. Uncertainty is recorded as
  `1 - quality`.

A concept that cites no evidence is refused. So is one that cites refs the task does not hold,
or one that rests on an open task.

Family evidence is the measured, non-refunded orders across the family's certified members,
plus those members themselves. The same quality floor applies.

### Validation before scoring

1. **Shape.** The proposal needs a slug, title, category, price (at most 1.5 × the premium
   ceiling), maker and design hours, and a rationale of at least 12 words.
2. **Construction.** The construction must be one that `cir.draft` actually compiles for a
   radar concept. See the section below.
3. **Closed concept vocabulary.** `creative.concept.Concept` is applied, and the make lane is
   derived from the maker hours.
4. **Children's policy pre-check (product_creation).** Every proposal goes through
   `intel.childrens.prohibited_subject`. A children's concept is also blocked while the
   children_and_baby policy has an unreviewed material change (#39).
5. **Originality, dedupe and anti-copy.**
   - The slug must not match a POOL slug, an established design (`preengineering.established`:
     ENGINEERED, the catalogue, Launch-0 aliases or certified products), or an approved row.
   - The title must not match a POOL title or restate a POOL title in the same category
     (token Jaccard ≥ 0.5). It must not match a database concept's title or a certified
     product's title.
   - The structural distance (`creative.concept.nearest`, the same definition the gate and
     the tournament use) to the briefed catalogue and the approved rows must be at least
     `MIN_NOVELTY`, so recolours are refused.
   - The concept must not be indistinguishable from an observed competitor listing
     (`prospecting._matches_a_listing`).
   - Its title must not be a competitor's title (Jaccard ≥ 0.8 against `benchmark_listings`).

Whitespace, risk class and make lane are derived, never typed:

- whitespace is the measured nearest distance;
- the risk class is A, because a flat rows panel is the geometry the compiler proves end to end;
- the make lane comes from the maker hours.

A proposal cannot set the taste fields (`thumbnail_reads_small` and `craft_impression`). They
are stripped from it.

### Scoring and downstream (unchanged chain)

- `radar.scan` scores `POOL + approved rows` with the same `score_concept` and
  `select_portfolio`.
- `radar.score` and `cir.draft` resolve a slug through `_seed_for(slug, db)`. POOL is checked
  first, then the approved rows.
- The steering, the #38 evidence discount, the lesson nudge and the pre-engineering gate are
  all the same.
- For an intake concept, `radar.score` reads the stored concept and brief from the database,
  never from the job. It also reads the vision judge's record (`creative.intake.judgement_for`)
  and carries both to the `cir.draft` payload (`draft:<slug>`).
- The `concept_to_cir` lineage records `radar.intake:<source_ref>` as the design source.
- `release.py`'s seed lookups take `ctx.db`, so pricing, SEO, launch plan and marketing know
  an intake concept. These are one-line changes.
- `intel.watchlist.review` and `queue_scores` treat approved rows as answers to an arena. A
  gap that used to stop at `needs_original_design` now routes to `radar.score` once an intake
  concept answers it.

### Idempotency and budget

- The row fingerprint is a sha256 of the source ref, the normalised proposal, and the dated,
  graded evidence. It is unique, so unchanged input is skipped and audited nothing.
- A changed proposal for the same slug and source is evaluated once, and the earlier approval
  becomes `superseded`.
- A family variation that has already been decided is not proposed again.
- Each run makes at most 10 evaluations and proposes at most 2 variations per family.
- The run spends nothing. The only job it enqueues is `radar.score`.

## Supported construction families (the radar draft path)

`cir.draft` drafts a radar concept with `runtime.pipeline.concept_to_cir`. That produces a
`flat_rows` panel worked over the category's `_GEOMETRY` repeat. The only supported
construction is `flat_rows`, in these categories and forms:

| category | forms |
|---|---|
| blanket, baby | rectangle_throw |
| runner | runner |
| placemat | flat_panel |
| coaster | coaster, flat_panel |
| pillow | pillow |
| wall_decor | wall_hanging |
| pet | flat_panel, rectangle_throw |
| scarf | scarf |

Everything else is refused with an explicit `unsupported construction ...` reason. That covers:

- **Constructions:** in_the_round, seamless_tube, amigurumi_shaping, top_down_yoke, bottom_up,
  mosaic_overlay, tapestry, cable_panel, granny_square, motif_join, modular_panels,
  corner_to_corner and side_to_side.
- **Categories:** mosaic_blanket, graphghan, basket, seasonal_decor, ornament and flower. Each
  has a template row, but the template would draft it as a striped rectangle (B-059, B-080).

## What the CIR drafter cannot yet do that limits originality

- The radar fallback makes the same panel for every concept in a category. Its stitch repeat,
  width and rows come from the category alone, and its palette comes from the family or a
  default. The concept's motif, premise and palette story never reach the CIR. Two approved
  concepts in one category therefore compile to structurally identical patterns that differ
  only in slug, title and (sometimes) colour. Concept-level novelty is real, but pattern-level
  novelty is not. Certification-time originality checks (`gates.originality`) and the
  family-engine recolour test would see them as one design. This is the largest limit.
- There is no motif, chart or colourwork authoring on the radar path. The mosaic, tapestry and
  graphghan demand (the strongest signals in CATEGORY_DEMAND) cannot be served by intake.
- There is no shaping, no rounds and no assembly. Baskets, ornaments, amigurumi, stockings,
  hats and garments are out of scope here, although `creative.prototype.author` and
  `garment_design` handle some of them on the tournament path behind the funnel.
- Taste is unmeasured in production (see `rescore_judged`: once the vision judge records a verdict for a waiting intake concept, the next scheduled intake pass re-scores it, keyed `score:<slug>:<date>`, never after `draft:<slug>` exists).
   `image_vision` is CLOSED, so the pre-engineering gate
  leaves every intake concept WAITING. Promotion to `cir.draft` happens only once the vision
  judge records a verdict (proved in the tests with a fixture judgement).
- Nothing in production writes concept proposals onto research tasks yet. The research agent
  answers questions, but no producer authors a structured concept from an answer. The family
  path is fully automatic, but it waits on ≥ 5 real orders.

## Tests

The new file is `tests/test_w5_concept_intake.py`, with 13 tests:

- a concept that is NOT one of the 34 POOL seeds becomes a concept from evidence, waits at the gate without a judgement, is re-scored by the next scheduled intake pass once a (fixture) vision judgement is on record,
  and with a fixture judgement is promoted to `cir.draft` (`draft:<slug>`), which drafts and
  queues `cir.compile` with provenance;
- `radar.scan` scores the approved concept with the pool;
- a duplicate is refused (a POOL slug, and a recolour below the novelty floor);
- a competitor title is refused as a copy;
- an unsupported construction is refused with its reason (in_the_round basket, cable_panel);
- a concept without evidence is refused (no refs, unknown refs, unanswered task);
- low-quality evidence is refused;
- a children's prohibited subject is refused;
- unchanged input is not reprocessed, and a change is reprocessed and supersedes the old row;
- a proven family proposes coordinated variations without duplicates;
- an unproven family proposes nothing;
- the static POOL behaviour is unchanged (pool identity, portfolio, `_seed_for`, payload keys);
- the intake runs on the cadence table and is authorised.

## Seed shops (D-W4-OWNER-SEEDSHOPS, same branch)

- HanJanCrochet, IvyLoop, LoveandStitchDesigns and FireflyCrochets are now `Member`s (role
  `seed`) and mandatory `BenchmarkSpec`s, alongside the existing four. Their URLs come from
  `radar.market.COMPETITORS` and spec/05.
- When the sanctioned read cannot find a shop (404/410, or no exact `findShops` match), it is
  recorded as `not_accessible` with "not accessible: <reason>", the date, `monitoring: kept`
  and the dated spec/05 profile as alternative evidence.
  - No scan is recorded.
  - It backs off like an outage.
  - Laura's provider reads DEGRADED and names the limitation.
- New tests in `tests/test_w4_intelrec_watchlist.py`: all eight shops present, an inaccessible
  shop recorded as a limitation and not as scanned, and no competitor content copied. The
  existing fixtures now serve the seed shops (one listing each, in pods no other shop
  occupies), and the shop-count assertions include them.
