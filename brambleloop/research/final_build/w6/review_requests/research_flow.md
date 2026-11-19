# Review request — eng/research-flow (ENG-RESEARCH), fix round 1

Main's independent review of ecb5ce0c gave DO NOT SHIP. Every finding is addressed below.
Nothing is deployed; no Railway, production, secret or spend was touched.

## H1 — the #108 qualifier is derived, never typed

- `proposal_writer.brief_for(slug, title, category, concept)` now derives:
  - `silhouette_qualifiers` with `creative.intake.qualifiers_for` on the creative `Concept`
    built from the proposal's own fields (the same fields `radar.intake.validate` builds);
  - `thumbnail_storyboard` from the category, `concept.motif` and `concept.palette_story`.
- Each proposal carries `brief_provenance` (`derived_from` the concept fields; the qualifier
  rule is named) and `silhouette_precheck`, which is #108 run exactly as the gate runs it
  (`preengineering._silhouette`) on the derived brief.
- Honest per-pod result on the flat-rows radar draft path (all three derive `[]`):
  - **home_decor → pillow.** `pillow` is not in `GENERIC_FORMS`, so #108 passes with no
    qualifier. Two concept fields were corrected because the gate refused them honestly:
    `spring_refresh` → `housewarming`. Plain bands draw nothing from the spring grammar
    (#110), and "everyday, for oneself, serene" names no buying moment (#83 jury).
  - **blankets → rectangle throw, kitchen_bath → coaster.** These are generic forms with
    plain-row stripes, so they carry no qualifier. #108 REFUSES them at radar.score.
- What the refusal shows:
  - `research_flow.lineage` names it with the #108 reason ("…shape rather than an outline…").
    Only `#108 `-prefixed text is surfaced, never a novelty reason.
  - The gap is `held_by_108` and **not qualifying**, so the conclusion reads
    `no_qualifying_opportunity` with the reason.
  - Before scoring, an approved or proposed concept whose precheck fails is already named
    "held by #108".
- **Why no relabel or alternative for blankets/kitchen.** I checked every engine route:
  - The radar draft path compiles only `flat_rows` (`radar.intake.SUPPORTED_CONSTRUCTIONS`),
    and `concept_to_cir` emits striped rows.
  - The only charted colourwork fallback (`fallback_constructions.tapestry_route`) drafts
    baskets, which radar intake refuses.
  - So no supported construction gives a rectangle throw or a coaster a real motif
    composition, texture or shaping. Making one is an **open engineering item**: a charted
    flat panel on the radar path. I did not relabel anything to pass.
- **Tests.**
  - The end-to-end test now uses a home-decor arena, which honestly clears #108.
  - New `test_a_generic_concept_with_no_qualifier_is_held_by_108_and_says_so` drives the
    kitchen arena: refused, not qualifying, reason named, nothing drafted.
  - New `test_the_brief_is_derived_from_the_concept_not_a_constant`.
  - The old `failed == []` assertion now runs only on the honestly qualifying concept.
  - The novelty test now asserts that the coaster FAILS #108 and that the precheck agrees.
- **Pre-existing, not on this branch's diff (flagged for Main).** Two other writers still type
  `silhouette_qualifiers: ["motif_composition"]`:
  - `radar/ideation.py:542`;
  - the family-variation proposer at `radar/intake.py:925`. Its premise names "motif", so
    derivation would agree.
  The same derivation should replace both.

## H2 — P0 board SyntaxError

- `p0_board.js:121` had one `)` too many; it is removed.
- Note: `node --check file.js` parses as CommonJS and passed silently. The file is an ES
  module, and `node --input-type=module --check < file` is what catches it. Both changed JS
  files (p0_board.js, sw.js) are clean that way.

## M1 — per-row pill

`research_flow.health_of(row)` derives the pill on the server:
- not scheduled → UNKNOWN (missing) or DEGRADED;
- failing (consecutive failures, or failures in 7 days) → DEGRADED;
- never succeeded → UNKNOWN;
- stale → STALE;
- otherwise OK.

The JS shows `r.health` (UNKNOWN for anything else). Test:
`test_a_never_succeeded_or_failing_source_never_reads_ok`.

## M2 — MP1.2-s4 off-Etsy channels

`competitor_websites`, `youtube` and `pinterest` are now registry rows (`kind="offsite"`).
They are MISSING, with an "UNAVAILABLE: …" reason, in `sources()`, in `research_sources.md`
§4a, and in the board's limitations. Test:
`test_the_off_etsy_channels_of_mp1_2_s4_are_visible_as_unavailable`.

## LOWs

- **Watchlist set.** The registry test asserts the exact shop set derived from the registry
  (`mjs.scan` + `intel.watchlist_scan` rows == `WATCHLIST` keys), with no hardcoded 8.
- **Conclusion failure.** In the concept_intake handler, `conclude` is guarded. A failure is
  audited as `intel.research_conclusion_failed`, the job's `research_outcome` reads
  `conclusion_failed`, and the job still succeeds.
- **Vision.** `vision_ok=None` reads BLOCKED ("could not be read"), never scheduled.
- **Downstream.** Without lineage tables, findings, concepts and engineering are `None` and
  the board reads "Unknown: no lineage recorded yet", not 0.

SW cache is `cc-shell-v35`.

## Mutants (fix round 1, PYTHONDONTWRITEBYTECODE=1)

Each mutant was applied alone and the suite rerun; every one is killed.

- H1 constant `["motif_composition"]` restored in `brief_for`: 4 tests fail.
- N1 never-succeeded reads OK: 1 fails.
- N2 failures ignored: 1 fails.
- N3 #108-refused gap still "qualifying": 1 fails.
- N4 `vision_ok=None` reads scheduled: 1 fails.
- N5 downstream 0 without lineage tables: 1 fails.
- N6 `conclude` unguarded: 1 fails.
- N7 an offsite row dropped: 1 fails.
- N8 #108 reason not surfaced in the lineage: 1 fails.
- J1 old JS pill (`scheduled` → OK) restored: `test_v11_pwa_browser` fails.

The mock P0 board in `tests/fixtures/cc_mock` now carries the `research_sources` section, so
the browser check counts twelve sections. Three new checks: a never-succeeded source reads
UNKNOWN, unknown downstream reads Unknown, and the #108 hold is named.

## Suites

SUITES_PLACEHOLDER

---

# Round 0 (ecb5ce0c), kept for the record


This branch was cut from `origin/claude/w6-INTEG2` @ a35ad302. Nothing on it has been deployed.
It does not touch Railway, production, secrets, Etsy, spend, BRAMBLELOOP_PHASE or
STAGE_A_ENABLED. It adds no new job type, so the autonomy map is unchanged. It reads no new
audit action: `unknown_read_actions()` returns [].

## 1. Source registry

`research/final_build/w6/research_sources.md` is the prose form of the code registry
`intel.research_flow.sources()`. The registry takes each cadence from `CADENCES`, and
`status_of()` derives each status (scheduled / disabled / blocked / missing). A test fails if a
research cadence or any of the eight mandatory shops falls out of the registry.

Sources that are not scheduled stay visible as limitations:
- `research_fetch` is **disabled**: `BRAMBLELOOP_RESEARCH_FETCH` is a deployment flag, and
  turning it on is Main's decision.
- `gallery_analysis` is **blocked** on `image_vision`.
- `marketplace_insights` is **blocked by design**: only the owner can record the readings.
- `external_trends` (Google/Pinterest Trends, social) is **missing**: no official API is wired,
  and none will be scraped.

## 2. The loop: where it stopped and what changed

The loop was traced on the real handlers with `_watchlist_sim`:

watchlist_scan → watchlist_compare → coverage gap + research → proposal_writer →
concept_intake → radar.score → pre-engineering gate → cir.draft.

**Stop 1 (fixed).**
- *Defect:* every watchlist proposal was refused deterministically at the gate. It had no #88
  thumbnail storyboard and no #108 silhouette qualifier, and nothing consumes the resulting
  `returned_to_ideation` row for intake concepts.
- *Fix:* `proposal_writer.brief_for(pod)` adds the brief, written from `POD_CONCEPTS` only.

**Stop 2 (fixed).**
- *Defect:* #87 novelty and intake's anti-copy check compared a concept only with the
  anchor's listings. A concept inspired by other watchlist shops was never checked against
  them, and it waited on `benchmark_observation` when the anchor had nothing in the pod.
- *Fix:* both now use `prospecting.watchlist_comparables`, which covers all eight shops.
- *Effect:* this can only add twins to refuse. In the sense of the earlier behaviour it widens
  nothing, but please review that judgement.

**Stop 3 (legitimate, not bypassed).**
- The gate's vision checks wait for a recorded verdict.
- `intake.rescore_judged` re-scores the concept automatically once a verdict exists.
- Asking the paid judge about a board-less radar-intake concept is still an open item. It
  belongs to the creative director's budget and the `image_vision` gate.

**Conclusion (new).**
- `radar.concept_intake` now ends with `research_flow.conclude`, which writes one
  `intel.research_conclusion` reading per day.
- The reading's outcome is either `opportunities` (stages, and what holds each one) or
  `no_qualifying_opportunity` (with its evidence).
- It names shops by alias only. `_assert_no_content` refuses a shop name or key.

## 3. Mission Control

A new P0 board section, `research_sources`, served under the existing owner-only `/api/cc`
gate.

It shows one row per source:
- agent, method and status with its reason;
- last attempt, last success and Etsy's source timestamp;
- listings observed, changes discovered and staleness;
- next scan, failures and backoff, and why the shop was not attempted;
- findings, concepts and engineering per shop alias. The existing `downstream` counted gaps by
  the shop's own key, which is always 0 for `watchlist` gaps.

The section also carries the loop's stages and the latest conclusion.

Other properties:
- It writes nothing: lineage is read only when its tables already exist.
- A shop name in the payload makes the section UNKNOWN.
- The JS view is added and the SW cache is bumped to `cc-shell-v33`.

## Tests

`tests/test_research_flow.py` has 15 tests; it is in `suite_final_segment.txt`, before
test_product_run. They cover:
- A watchlist change reaches `cir.draft` with no manual step.
- Without a vision verdict the concept waits, the hold is named, and nothing is drafted.
- The proposal has no deterministic gate failure.
- "No qualifying opportunity" is recorded, with its evidence. No comparison at all is a named
  conclusion of its own.
- An inaccessible shop stays visible and the others still scan.
- No competitor text, shop name or key reaches a proposal, a task, a concept or the
  conclusion.
- Novelty is measured against non-anchor watchlist shops.
- The registry covers every research cadence.
- Statuses are derived.
- The board's per-source evidence and per-shop downstream, the failing-shop row, write-nothing,
  and the shop-name refusal.

**Mutants.** All were run with PYTHONDONTWRITEBYTECODE=1, and every one is killed:
- M1 brief removed: 4 tests fail.
- M2 anchor-only cards: 2 fail.
- M3 conclusion never "opportunities": 2 fail.
- M4 no-content check removed: 1 fails.
- M5 conclude not called: 5 fail.
- M6 disabled read as scheduled: 1 fails.
- M7 engineering stage lost: 1 fails.
- B1 per-shop engineering lost: 2 fail.
- B2 shop key instead of alias: 3 fail.
- B3 table guard removed: 1 fails.
- B4 evidence no-content check removed: 1 fails.
- B5 failures forced to 0: 1 fails.
- B6 section unregistered: 3 fail.

**Wide suites.** The run used `run_tests.sh` with JOBS=4. The suites were the mandatory list
plus every suite that imports preengineering, prospecting, intake, proposal_writer or
concept_intake, plus radar/intel/research/watchlist/p0. That is 49 suites, 822 passing.

Two suites failed on that run:
- `test_research_flow` printed lowercase "ok", which the runner does not count.
- `test_cert_lanes_capacity` hit "runtime graph source changed during analysis" because I
  edited files mid-run.

Both pass on a clean rerun.
