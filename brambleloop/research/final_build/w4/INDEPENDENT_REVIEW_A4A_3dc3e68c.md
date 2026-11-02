# Independent review: A4a P0-RESEARCH-TO-CONCEPT at `3dc3e68c`

- Branch: `origin/opus2/a4a-research-to-concept` at `3dc3e68c490c74d947dd235fd2e39d0f32e7bd5c`
- Base: `claude/w5-INTEG1` `7c42e706`. The code commit is `fee061e5`. `993cc0cd` and `3dc3e68c` change tests only.
- Diff: new `radar/ideation.py` (553 lines), `runtime/pipeline.py` (+29), `runtime/intel_ops.py` (+13), the new test `tests/test_w5_a4a_research_to_concept.py` (9 tests), and one line in `scripts/suite_final_segment.txt`.
- Method: read-only. Probes ran against a real SQLite file in a detached scratch worktree. Nothing was pushed, committed or deployed, and no branch was modified.
- Reviewed: 2026-11-02 UTC

## Verdict: DO NOT SHIP (for exact SHA 3dc3e68c)

One finding blocks shipping. The only product this chain can produce gets a granted certificate under a name and premise that its pattern does not make (A4A-1, Product Truth). Everything else is sound and could ship once A4A-1 is fixed (and preferably A4A-2):

- the chain wiring
- idempotency under re-runs and re-delivery
- the MAX_IN_FLIGHT bound
- the evidence floor on the normal path
- the gates (intake, children's pre-check, pre-engineering, certification), which are all used

## Findings

### A4A-1 HIGH: Product Truth. The research concept certifies as a "square dishcloth" that is a 38 x 11 cm strip
`POD_OBJECTS["kitchen_bath"]` maps both "Dishcloth" and "Hot Pad" to `category="placemat"`. `cir.draft` therefore uses `_GEOMETRY["placemat"]` (48 sts x 14 rows). At the worsted gauge `gauge_for` derives (12.5 sc / 13.8 rows per 10 cm), the twin is **38.4 x 11.4 cm**. The proposal's premise says "A square dishcloth worked flat in rows...". `gate.certify` still **granted** it with `reasons: []`, and `publish.eligibility.name_truth(cir)` returns `[]`.

- name_truth checks only count, assembly, fabric and imagery. It has no object-to-size check.
- `gates.first_customer.PRODUCT_TYPE_FAMILIES` has no dishcloth or hot-pad family.
- `cir.draft` skips name_truth for FLAT_PANEL anyway.
- `pdf.py` prints the twin's width_cm and height_cm, so the customer document would state a 38 x 11 cm "dishcloth".
- "Hot Pad" has the same problem: an 11 cm-tall hot pad does not take a pot.

The module docstring says the placemat template "honestly" makes these objects. It does not at that size. This breaks the Product Truth non-negotiable: deterministic validation granted a product whose name and premise the pattern does not make, and the chain now runs on the production radar.scan cadence with no human in the loop.

Repro: `a4a_probes.py truth` (scratchpad), or run `test_the_new_concept_continues_through_compile_to_certification` and read the compile job's CIR:

```
proposal: Oat Furrow Dishcloth placemat premise: A square dishcloth worked flat in rows of furrowed oat rows ...
twin size cm: 38.4 x 11.4 | gauge 12.5 sc / 13.8 rows per 10cm (medium)
name_truth: []
certify: DONE {'granted': True, 'reasons': []}
```

Suggested fixes:
- Give each PodObject its own geometry: a square of about 20–25 cm for a dishcloth, about 20 cm for a hot pad. Either add a `dishcloth` / `hot_pad` category to `_GEOMETRY`, or carry width_stitches and rows on the proposal.
- Add a deterministic object-to-dimension band (aspect ratio and size range per object noun) to `name_truth` or to certification.
- Add a test asserting the certified twin's size is inside the named object's band.

### A4A-2 MEDIUM: Evidence honesty in the crash-recovery path. A proposal can be built below the evidence floor, or crash
`investigate()` skips the insufficient-evidence branch when `t["state"] == ANSWERED and refs` (a crash between `research.answer` and `attach_proposal`). It then calls `build_proposal` with the *current* observations even when `obs["ok"]` is False.

- Repro (`a4a_probes.py crash`): answer the task, then crash attach_proposal. Then reduce the observations to 1 listing from 1 shop and re-deliver. The result is `proposed=True`, with the rationale "1 listings across 1 observed shops ... median price CA$5.5". The proposal text and price rest on evidence below the 3-listing / 2-shop floor. Intake is still fed the original fact-grade finding refs, so it does not notice.
- When the remaining observations are unpriced, re-delivery raises `TypeError: float() argument must be ... not 'NoneType'` (`float(obs["price_median_cad"])`). The job then retries until it is dead-lettered, and the gap holds the slot until the 14-day stall.

Fix: in the ANSWERED-with-refs path, either rebuild from the census recorded at answer time, or record `insufficient_evidence` whenever `not obs["ok"]`.

### A4A-3 MEDIUM: Liveness. A gap with a named outcome, a stall or a stopped task is never ideated again
`open_briefs` puts every gap with `rec["task"]` into `already` forever. After `insufficient_evidence`, the task stays OPEN, and research.sweep re-investigates it every 7 days. When the 30-day `time_bound_days` deadline passes, `stop_overdue` stops it. `investigate()` then returns "task is stopped", and the gap is never re-opened, even when evidence later arrives.

Repro (`a4a_probes.py deadline`): stop at +31 days, add 5 listings, and the handoff reports `opened: [], already: [1]`.

The same applies to `stalled` (`a4a_probes.py stall`) and `title_overlaps_competitor`. Termination is correct, so there is no infinite loop. But the module docstring ("the next watchlist scan adds observations and research.sweep re-investigates") is true only inside the 30-day window. Each uncovered arena gets one 30-day chance.

Separately, `expire_due` re-opens an expired *answered* ideation task under a new trigger without copying `ideation_brief`. That task goes to the generic research agent instead of the ideation step. This is informational.

### A4A-4 LOW: The originality check misses simple title variants
Results of `originality_reasons("Tideline Stripe Dishcloth", "Tideline Stripe", ...)` (probe `orig`):

- Refused correctly: equal, upper-case, reordered, singular/plural on one word, "Dish Cloth", "Striped", the accented "Tidelíne", "Tideline-Stripe ... Pattern", and long SEO titles that contain the exact descriptor.
- **Passes:**
  - "Tideline Stripes Dishcloths" (j = 0.20)
  - "Tide-Line Stripe Dishcloth" (j = 0.40)
  - fullwidth "Ｔｉｄｅｌｉｎｅ Ｓｔｒｉｐｅ Ｄｉｓｈｃｌｏｔｈ" (the `[a-z]+` tokenizer sees no tokens, and there is no NFKC normalisation)
  - "Tidelines Stripes Cotton Dishcloth Kitchen Towel Farmhouse"
  - "Tide Line Stripes Dish Cloths Crochet Pattern"
- Intake's own competitor-title check (Jaccard >= 0.8) passes all of the above too.

The risk is mitigated: titles come only from the six house descriptors, and no competitor text enters the proposal, CIR or listing. Verified: the proposal fields are the PodObject constants, the house descriptor, and counts and prices only. Fix: NFKC-normalise, singularise tokens, and compare with hyphens and spaces collapsed.

### A4A-5 LOW: Observation dating
- Future-dated listings count as fresh. `r[5] >= since` has no upper bound. Probe: 3 rows at +400 days gives `ok=True`.
- "Undated" rows cannot exist at the DB layer. `BenchmarkListing.first_seen` and `last_seen` default to `utcnow`, so an undated scrape gets its insert time. The 90-day staleness filter works (95-day rows are rejected).
- The 3-listing, 2-shop and price thresholds are enforced (probe `evidence`). Confidence is recorded as medium or high, or "none" when refused.

### A4A-6 LOW: The evidence floor is pod-wide, not per object
The floor counts all listings in the pod. The chosen object can rest on a single listing: "3 pod listings, only 1 names dishcloth" gives `ok=True`, confidence medium. The finding states `object_listings` honestly, but no floor applies to it.

### A4A-7 LOW: Mutation survivors (test gaps)
See the mutant table. These guards are untested:

- the stale-observation guard (M4, M11)
- the 0.5 overlap threshold (M1)
- the per-gap "already has a task" guard (M6). It survives because after approval the gap is answered by the new concept. On an insufficient-evidence gap the mutant re-runs `open_question` every scan, re-audits `ideation.brief_opened` and **resets the recorded outcome to None**. research's trigger dedupe stops a second task from being created.
- the intake enqueue key (M7). It survives because the "already answered and proposed" early return makes it unreachable in the tests.
- the 14-day stall (M8)

The code for M4, M8 and M11 is correct per probes P2 and P4.

### A4A-8 INFO: Production cost and bounds
- Each radar.scan job (6-hour cadence, plus plan.cycle) enqueues at most one extra coverage-handoff `radar.score`. It does so only when an open gap exists, and the job is keyed `coverage-handoff:scan:<scan job id>`.
- This is keyed **per scan job, not per day**: about 4–5 handoff jobs a day. Each one only re-enqueues the per-slug `score:<slug>:<date>` keys, which are deduped per day, so the cost is bounded. A per-day key (`coverage-handoff:<date>:<6h window>`) would make it explicit.
- `MAX_IN_FLIGHT=1` holds per handoff, but nothing locks it across concurrent handoff jobs. A "done" gap can also become in flight again if a later sweep proposes. This is a small, bounded overshoot.
- No new job types, so JOB_BANDS, JOB_CLASS and authority are unchanged.
- `research_agent` is allowed `research.investigate` and `market_radar` is allowed `radar.concept_intake`.
- `radar/ideation.py` is reachable from the runtime (tested).

### Verified OK
- **Idempotency.** Re-running cadences, hand re-delivery of investigate, handoff and intake, and a crash between `open_question` and `_record` (trigger dedupe) create no duplicate task, proposal, concept or draft.
- **Gates.** Research concepts go through the same gates as POOL concepts:
  - intake validation, including the anti-copy check against benchmark listings
  - the children's pre-check
  - the pre-engineering gate (held WAITING without a vision judgement, tested)
  - `cir.draft` construction routing
  - compile and certify
- **Bounds.** The 14-day stall and the 30-day deadline both terminate.
- **Tests.** No existing test was weakened. The only change outside the new test is an appended suite-segment line.

## Suites (run at 3dc3e68c, one at a time, with venv-integ4)
| suite | result |
|---|---|
| test_w5_a4a_research_to_concept | PASS (9/9, 0 failed; certify granted=True) |
| test_w5_concept_intake | PASS (0 failures) |
| test_w4_research_to_product_stall | PASS (0 failed) |
| test_opus2_knowledge_gaps | PASS (0 failed) |
| test_originality | PASS (28 passing, 0 failing) |
| test_shadow | PASS (rc 0, 10/10 OK, 1930 s; the first attempt hit a 2400 s timeout under load and was re-run) |
| test_swarm_runtime | PASS (rc 0, 10 OK) |
| test_w3_k11_authority | PASS (0 failing) |
| test_launch0 | PASS (rc 0, 52 OK) |
| test_radar | PASS (rc 0, 32 OK) |
| full suite | NOT RUN (per instructions): UNKNOWN |
| a4a through-certify on the merged a4a+a6+a4b tree | NOT RUN: UNKNOWN |

## Mutants (against test_w5_a4a_research_to_concept)
| mutant | result |
|---|---|
| M1 originality Jaccard 0.5 -> 0.99 | SURVIVED |
| M2 descriptor-substring check removed | KILLED |
| M3 MIN_LISTINGS 3 -> 1 | KILLED |
| M4 observation date filter removed | SURVIVED |
| M5 MAX_IN_FLIGHT 1 -> 5 | KILLED (5 tests) |
| M6 per-gap "already has task" guard removed | SURVIVED |
| M7 intake enqueue key made unique | SURVIVED |
| M8 STALL_DAYS 14 -> 10**6 | SURVIVED |
| M9 answered-and-proposed short-circuit removed | KILLED |
| M10 originality call removed from build_proposal | KILLED (2 tests) |
| M11 OBSERVATION_WINDOW_DAYS 90 -> 9000 | SURVIVED |
| M12 MIN_SHOPS 2 -> 1 | KILLED |

6 of 12 killed. The key guards are killed: originality call, evidence count thresholds, in-flight cap, and the idempotent short-circuit. The staleness window, overlap threshold, stall timer and per-gap guard are not covered by tests.

## Merge conflicts (git merge-tree, textual)
- vs `origin/claude/w5-INTEG1` (`7c42e706`, which is also the merge base): clean.
- vs `opus2/a6-learning-to-design` `ebead3dd`: clean. a6 edits `handle_cir_draft` (lines ~769–1161). a4a edits the scan and handoff (~271, ~312, ~377).
- vs `opus2/a4b-enrichment` `230b7d8d`: clean.
- Three-way (a6 + a4b, then a4a): clean.
- Semantic note: a6 changes the flat-panel draft path that the research concept takes (learning can change the yarn weight, which changes the gauge and so A4A-1's dimensions). The a4a through-certify test should be re-run on the combined tree. That combined run was NOT done here (UNKNOWN).

## Probe and harness files
All in `/tmp/claude-0/-home-user-Project-Money/0aa334b9-5ba9-5fd2-9058-e50b4b8604ea/scratchpad/`: `a4a_probes.py` (orig, evidence, crash, stall, deadline, truth), `m_M*.sh`, `mut_M*.log` and `a4asuite_*.out`.
