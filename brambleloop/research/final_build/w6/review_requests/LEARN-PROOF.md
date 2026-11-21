# LEARN-PROOF — benchmark lessons that change later outputs

Branch `eng/learn-proof`, cut from `claude/batch19-fixers` (8204c93). NOT merged, NOT deployed.
Production is unchanged.

## What the P0 asked for

"Real learning" needs proof that a lesson changes a later output. This branch stores both
benchmark teardowns' department lessons (L1–L7 of `TEARDOWN_HIGHLAND_COW_AMIGURUMI.md` and
`TEARDOWN_MADELINEMAECO_CAPYBARA.md`) as structured records. Four decision hooks read those
records. Each hook has a test that runs the same input before and after ingestion, and the
outputs differ.

## Records (`learning/benchmark_lessons.py`)

- There are 14 `BenchmarkLesson` records (`HC-L1..7`, `MM-L1..7`). Each has a `department` (an
  `improve.cells` key), a `lesson_class` and an `effect` hook. The hook is None when nothing
  reads that lesson yet, and the readback says so.
- Records are stored in the existing learning store: `learning_derived_lessons` with
  `loop="benchmark"`. Ingestion is idempotent.
- `evidence` holds the source file, the lesson number, the class, the effect, and the sha256 of
  the teardown's lessons section.
- Statements are our own paraphrase. A test checks that no shop name, character name, title or
  delivery-host wording is stored.
- **Source pinning.** The production image does not ship `research/`; the Dockerfile copies only
  src, release and tests. `SOURCE_SHA256` therefore pins each lessons section:
  - A checkout whose teardown changed, or that lost a cited `**Ln,`, refuses ingestion.
  - A deployment without the file uses the pinned digest.
  - `test_the_pinned_digests_match_the_teardowns_in_this_checkout` holds the pins to the files.
- **Where ingestion runs:** `learning.loops` (`runtime/learning_ops.py`), daily.
- **New table** `learning_lesson_effects`, additive and created on first use. It holds one
  `applied` row per (lesson, department, subject) and an `evaluated` count per (hook, department).

## Effects wired

| Effect | Lesson(s) → dept | Where | Before → after on the same input |
|---|---|---|---|
| `concept_rank` | MM-L1 → market_radar | `radar.scan` (`runtime/pipeline.py`), next to `consume.rank_adjustments` | No nudge → +0.02 per trait (low-sew, `<Name> the <animal>`), capped at +0.04, amigurumi only. In the test the ranking flips so "Bramble the Hedgehog" (low-sew) is first. A real scan moves `no-sew-reindeer` and records it in `radar.scanned.benchmark_lesson_nudges`. |
| `pdf_eye_options_age` | MM-L4 → pattern_engineering, HC-L5 → quality | `publish/pdf_standard.LESSON_RULES` rule `eye_options_age` (amigurumi) | Not required → required: `EYE OPTIONS`, `Embroidered eyes`, `Safety eyes`, and age guidance "under 3". The same PDF text with the panel removed passes the base standard and fails the learned one. |
| `pdf_hook_range_chunky` | MM-L3 → pattern_engineering | rule `hook_range_chunky` (CYC 5+ or any chenille material) | Not required → a hook range naming both ends in mm is required. A real engine PDF of `chunky-ribbed-scarf` passes it; the same text without the range fails. |
| `seo_low_sew_truth` | MM-L6 → seo_search | `seo/truth.validate_listing` | "no sew"/"low sew" segments pass → they are refused (`TERM_MISLEADING … MM-L6`) unless the certified CIR's seams support them. No-sew means 0 sewn seams; low-sew means ≤ 1. whipstitch, mattress and sew count as sewn; slst, pick_up and thread do not. `low_sew_modifiers(cir)` gives SEO the modifiers the construction earns. |
| `qa_defect_class` | MM-L7 → quality | `improve.mine.mine` → `benchmark_lessons.qa_classify` | Nothing → an incident reading "stitches were too tight with the stated hook" is recorded under `missing_gauge->tension_complaints`. Gate refusals with `gauge_every_fabric` / no gauge statement are recorded too. `defect_classes(db)` counts them. |

**Renderers.** The learned PDF rules would otherwise refuse documents that production builds
today: `PDF_LAYOUT = "engine"`, and the engine had no eye panel and no chunky hook range. So both
layouts now print them:
- The engine (`publish/pdf.py`) prints `Eye options` for an amigurumi and a `Hook range:` line
  for chunky or chenille yarn.
- The template prints the chunky `Hook range:`.
- The template's eye-options text moved, word for word, into `pdf_standard.eye_option_lines`,
  which both layouts share.
- The toy hook range stays 0.5 mm below the stated hook. The chunky range is 1.0 mm below and
  never above, because the gauge is measured at the stated hook.

**Pure hooks.** The PDF standard and the SEO validator take no database. They read a
process snapshot of the stored effects (`refresh`) and buffer what they applied (`note`). The
worker refreshes the snapshot before each handler (cached for 300 s) and flushes the buffer
after it (`runtime/worker.py`). Both functions take an explicit `lessons=` argument, which is
what the before/after tests use.

## Readback

`learning.progress.readback` now carries `benchmark_lessons`, and so do
`/api/readback/evidence` → `learning` and production_evidence `learning`. Per department it
reports `ingested`, `wired`, `applied` (distinct lessons) and `applications`. `applied` is a
number only when it was measured. It is `UNKNOWN`, with the reason, when:
- the store is unreadable;
- the lessons are not ingested;
- no hook reads that department's lessons (pricing, product_creativity, creative_assets,
  customer_experience);
- the department's hook has not run since ingestion.

A 0 means the hook ran and changed nothing.

## Tests

`tests/test_learn_proof.py` has 18 tests covering ingestion, refusal, digest pins, no competitor
wording, and each of (a)–(d) before and after. Readback tests cover UNKNOWN versus 0 and the
unreadable store. See "Suite run" below.

## Limits, said plainly

- No lesson has been applied in production. Nothing here was deployed or read from production.
- The concept-rank traits are read from concept text (slug, title, rationale), not from a
  certified construction. The ranking nudge is bounded, and no gate changes. The SEO claim is
  checked against the certified CIR.
- Buffered notes from pure hooks are lost if a process dies before the worker flushes them. The
  count can then undercount; it never overcounts.
- Notes from the PDF and SEO hooks are written only on the worker path, after the handler runs.
  A PDF built outside the worker (CLI, tests) is audited under the snapshot but is not counted.
- Lessons HC-L1–L4, HC-L6, HC-L7, MM-L2 and MM-L5 are stored with no hook, and the readback
  shows them as `wired: 0`.
- The engine PDF of amigurumi and chunky products gains a few lines, so the byte hashes of those
  documents change from this commit on. Worsted non-toy documents are byte-identical.

## Suite run

See the commit message and BUILD_STATE for the run id and totals.
