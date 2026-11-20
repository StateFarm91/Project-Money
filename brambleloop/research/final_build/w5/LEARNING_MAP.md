# Learning Department and reference-pattern intake: map of what exists (2026-10-31)

Source: a read-only survey of `claude/w4-INTEG8-next` at 0cf0c59d. Paths are relative to `brambleloop/src/brambleloop/`.

**There is no competing Learning Department to build.** The internal learning system is `improve/` (the lesson bus, mining, monitor, league, replay) together with `teardown/` (purchased-reference intake and analysis). `learn/` is the *customer tutorials* department; do not confuse the two.

## A. Learning

| # | Requirement | Status | Where it lives |
|---|---|---|---|
| 1 | Technical defects | PARTIAL | `improve/mine.py:mine` mines incidents, `gate.blocked`/`gate.halted` and DEFECT dead letters (cadences `failure_mine` 6 h, `nightly_improvement`). **Missing:** `cir.compiled ok=False` and UNREPAIRABLE revisions are never mined. |
| 2 | Independent reviews | PARTIAL | Jury autopsies are mined through `creative/audit.py`; `improve/monitor.py` handles regressions. `blind_review` publishes no lesson; `quality.reverified` failures are not ingested. |
| 3 | Physical tester results | PARTIAL | Yardage calibration (`quality/physical.py`) is read by every twin; a size disagreement opens an incident that is then mined. Notes are not turned into lessons. (W-PHYSFIX area.) |
| 4 | Customer feedback | PARTIAL | `improve/readings_bus.py:_customer`. `support/community.py` and `support/lesson_trigger.py` have **no callers**. |
| 5 | Etsy performance | PARTIAL | `creative/style_learning.py` and `creative/outcome_learning.py`; the writer is `improve/commercial_lessons.py` on opus2 (in review). |
| 6 | Versioned, approved design knowledge | **MISSING** | Fragments only: `Lesson` has provenance but no version and no approval; `BrandKnowledge` is promoted automatically and covers style only. |
| 7 | Lessons read by product development | PARTIAL | Read by radar scoring, queue priority, briefs, SEO, support and growth. **Not read** by `cir/writer.py`, the `cir.draft`/`cir.revise` content logic, `publish/pdf.py` or `visual/*`. Teardown requirements are a publish gate only. |
| 8 | Before-and-after evaluation on held-out cases | PARTIAL | Exists only for decision policies (`improve/replay.py`, `league.py`). `quality/benchmark_e2e.py` and `quality/stitch_benchmarks.py` have no runtime callers. |

## B. Purchased reference patterns (`teardown/`)

| # | Requirement | Status | Where it lives |
|---|---|---|---|
| 1 | Secure intake | EXISTS | `teardown/intake.py:receive`; `POST /api/teardown/intake` (ops token). |
| 2 | Provenance | EXISTS | `BenchmarkProduct`, `intel/purchase_selection.py`, `teardown/lab.write_manifest`. |
| 3 | Licence | EXISTS | `teardown/licence.py`, `BenchmarkLicence`. |
| 4 | Private storage | EXISTS (gap) | `teardown/library.py` role checks; `benchmark_library/` is gitignored; encrypted mirror. **Gap:** no `.dockerignore`, and `library_root()` is relative to the working directory. |
| 5 | Structured analysis | PARTIAL | `teardown/reader.py` and `size_family.py` (closed vocabulary). **Gap:** `analysis()` is not persisted, and **no `teardown.analyse` job exists**; `teardown_state` stays `queued`. |
| 6 | Instructional quality | PARTIAL | `teardown/audits.py` and `scorecard.py`; audits are scored manually. |
| 7 | Charts and schematics | PARTIAL | Manual `chart_benchmark`; `schematic_cross_check`. |
| 8 | Reusable guidance | PARTIAL | `enforce.requirements` is a publish gate only. |
| 9 | Independent review of extracted lessons | **MISSING** | No second reviewer or approval step. |
| 10 | Anti-copy | EXISTS (gap) | `gates/originality.py`, `library.check_derived`, `presentation_review`. **Gap:** charts are not compared with benchmark charts. |

## Library

**Owned:**
- Benchmark 1: "Cardigan with Pockets" (conservative licence reading).
- Benchmark 2: "Mini Star Stitch Cardigan" by MJ's Off The Hook Designs (personal use).

**Previously approved, not bought:** 13 MJ's patterns totalling CA$280.50 against a CA$300 ceiling (`research/final_build/w4/GATE_CLEARANCE_BUSINESS.md` §1; decisions B-501 and B-533). No `BenchmarkProduct` rows exist.

## Assignment

These gaps become Codex work order `CODEX_WO_P0_LEARNING_REFERENCE.md`, claim `P0-LEARNING-REFERENCE`.
