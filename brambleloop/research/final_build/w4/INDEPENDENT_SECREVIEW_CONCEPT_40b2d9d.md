# Independent security & integrity review — W5-CONCEPT delta bb680ec5..40b2d9d9

- **Subject:** `claude/w5-CONCEPT` @ `40b2d9d9`, diffed against `bb680ec5`. The merge of
  INTEG8-next (`92c72538`) is excluded. That leaves two commits (`7b3a8de`, `40b2d9d`) touching
  four files: `radar/intake.py`, `runtime/pipeline.py`, `tests/test_w5_concept_intake.py` and
  `CONCEPT_INTAKE.md`.
- **Prior review:** `INDEPENDENT_SECREVIEW_CONCEPT_bb680ec.md` (findings G1 HIGH, G2 LOW, G3 MEDIUM).
- **Reviewer:** an independent reviewer that did not write the change. It judged the code, not
  `CONCEPT_INTAKE.md`.
- **Date:** 2026-10-31 (UTC)
- **Method:**
  - I read the diff.
  - I ran the requested suites one at a time with `nice -n 19` in a clean worktree at
    `40b2d9d9`.
  - I ran 13 single-point mutants in a second worktree (`/tmp/mut`), restoring the file after
    each one. The worktree was clean afterwards (`git status` empty).
  - I probed edge cases with scratch scripts kept outside the repository. They import the
    subject's own test helpers.
  - The container had no `sqlalchemy`, so I installed `requirements.lock` and
    `requirements-test.lock` with `--require-hashes`.

## Verdict: **SHIP**

- **G1:** closed on every path the brief names.
- **G2:** closed.
- **G3:** all five former survivors (N8, N9, N10, N17, N18) are killed, and so is every new
  mutant of the fix.
- **Regressions:** no gate is relaxed, and no new fail-open path exists.

The residual items below are LOW/INFO. Each one ends in a CIR with no provenance, which the
certificate's originality stage refuses (`PROVENANCE_MISSING`), so none of them can produce a
release.

## Test runs (one at a time, `cd brambleloop && PYTHONPATH=src:tests nice -n 19 python tests/<f>`)

| suite | result |
|---|---|
| test_w5_concept_intake | pass, 0 failure(s) (45 s) |
| test_radar | pass (2 s) |
| test_shadow | running (partial report) |
| test_w4_fmbatch1_retention_guard | pass (31 s) |
| test_vacuity | pass (8 s) |
| test_cert_wiring | pending (partial report) |
| test_fallback_draft_provenance | pass (4 s) |

## 1. G1: is it closed on every path?

The fix is in `handle_cir_draft` (`runtime/pipeline.py:679-698`). When `_seed_for` returns
`None` (the slug is neither a POOL slug nor a currently approved intake concept), the draft is
refused if both of these hold:

- the slug is **not** established; and
- the job either declares `radar.intake:` provenance or `radar_concepts` has **any** row for
  the slug.

A refused draft is audited as `cir.draft_refused` (gate `radar.intake`, with the row state),
and nothing is enqueued.

| path | result | evidence |
|---|---|---|
| Queued `cir.draft` (from `radar.score`) for a concept withdrawn before the draft runs | **Refused** | `test_g1_a_queued_draft…`. My own probe also returned `{'drafted': False, 'gate': 'radar.intake', 'reasons': ['intake concept not currently approved (withdrawn)']}`, with no `cir.compile` job. |
| Re-draft carrying raw geometry and **no** provenance | **Refused** (the database row alone is enough) | The `bare` step in `test_g1_a_queued…`. This kills the "provenance-only" mutant G1b. |
| Job declaring `radar.intake:` provenance with **no** row | **Refused**, state `no row` | `test_g1_a_draft_declaring_intake_provenance_without_any_row_is_refused`. This kills the "row-only" mutant G1c. |
| Concept withdrawn between `radar.score` and `cir.draft` | **Refused** | The same test as the queued case: it withdraws after `promoted`, with the judgement still on record. |
| Refused, superseded or still-proposed concept (never approved) | **Refused** | `has_rows` matches any state. |
| Rows pruned after withdrawal | **Still refused** | `prune` always keeps the newest row per `(source_ref, slug)` (mutant N8 killed), so `has_rows` stays true for every slug intake has ever recorded. |

**Can the "established design" exemption be abused?**

- **An intake concept that reuses an established slug.** Intake refuses it at proposal time.
  `_originality_reasons` calls `preengineering.established(db, slug)` and also rejects POOL
  slugs and `<pool>-…` extensions (`radar/intake.py:595-606`). So no approved intake concept
  can hold an established slug.
- **What "established" includes.** `established` is a closed list: ENGINEERED,
  `LEGACY_DUPLICATES`, CATALOGUE, and `PatternVersion.certified` in the database. Job inputs
  cannot add to it, so a caller cannot make a slug established. A `LEGACY_DUPLICATES` slug is
  routed before this code is reached.
- **An intake row that collides with an established slug.** The exemption works as intended:
  a rebuild of `hexagon-coaster-set` is engineered even with a REFUSED intake row on that slug.
  This is asserted, and mutant G1d (exemption removed) is killed.
- **Residual case: a withdrawn intake concept that was already certified.** See H1 (LOW).

## 2. G2: what prune keeps

The deletable predicate (`radar/intake.py:1085-1087`) is:
`st in (REFUSED, SUPERSEDED, WITHDRAWN)`, **and** not the newest row of its `(source_ref, slug)`,
**and** `fp not in _current_fingerprints(...)`, **and** older than `RETENTION_DAYS`.

- **APPROVED** and **PROPOSED** rows are never deletable, whatever their age or position.
  Mutant N8 widens the filter to include them, and `test_n8` kills it.
- **A row holding a current fingerprint** is never deletable. `_current_fingerprints` produces
  exactly the value `evaluate` looks up: `fingerprint(source_ref, _clean(proposal), evidence)`
  over `research_candidates + family_candidates`, which is the same expression as at
  `radar/intake.py:910-911`. Mutants G2a and G2b are killed by `test_g2`. That test reproduces
  the prior A → B → A scenario at +200 days: nothing is removed, and the revert stays
  unchanged rather than being re-approved.
- **Failure direction.** If `_current_fingerprints` raises, `prune` raises before deleting
  anything. That fails closed.

## 3. G3: mutants re-applied (each run against `test_w5_concept_intake`)

| mutant | result | killing test |
|---|---|---|
| G1a: refusal block disabled | KILLED | test_g1_queued, test_g1_declaring |
| G1b: provenance-only (no `has_rows`) | KILLED | test_g1_queued (`bare`) |
| G1c: row-only (no provenance check) | KILLED | test_g1_declaring |
| G1d: established exemption removed | KILLED | test_g1_queued (rebuild) |
| G1e: `has_rows` always False | KILLED | test_g1_queued |
| G1f: refusal reports `drafted: True` | KILLED | both test_g1 tests |
| G2a: `fp not in current` dropped | KILLED | test_g2 |
| G2b: `_current_fingerprints` returns ∅ | KILLED | test_g2 |
| N8: prune may delete APPROVED or PROPOSED | KILLED | test_n8 |
| N9: prune ignores the 90-day age | KILLED | test_n9 |
| N10: `ops.retention.apply` always dry-runs the table | KILLED | test_n10 |
| N17: no withdrawal on loss of `amplification` | KILLED | test_n17 |
| N18: `gate_inputs` keeps judged brief fields from the stored row | KILLED | test_n18 |

Result: 13 of 13 killed. Every kill is a targeted assertion failure, not an incidental crash.

## 4. Regressions

- **The new branch only refuses.** It returns before any enqueue. It never adds a pass, and it
  only runs when `seed is None`, so an approved intake concept still goes through
  `gate_inputs` and then `gate_concept` unchanged.
- **The POOL, bundle, engineered and creative/funnel paths are unchanged.**
- **`prune` only got stricter.** It now deletes a subset of what it deleted before.
- **The new readers fail closed.** `has_rows(None, …)` returns False. A job that declares
  intake provenance while `ctx.db` is None reaches `latest_state(None)`, which raises, so the
  job fails rather than drafting.

## Findings

### H1 — LOW — withdrawal does not stop a re-draft of an intake concept that is already certified
`established()` counts "already certified". So once an intake concept has a certified
`PatternVersion` and is then withdrawn, a queued or rebuild `cir.draft` for it is exempt from
the new refusal. It then falls through to the raw-geometry fallback and enqueues `cir.compile`.

**Reproduction** (scratch `probe.py certified`):
1. Approve, judge, score and promote the concept.
2. Expire the task, then run `radar.concept_intake` (the concept is withdrawn).
3. Insert a `Product(slug=SLUG)` with a `PatternVersion(certified=True)`.
4. Run the queued `cir.draft`.

Observed:
- `established: already certified…`
- `{'drafted': True, 'rows': 16}`
- one `cir.compile` job
- the audit `cir.drafted` with `source: concept_to_cir fallback`.

**Why LOW:**
- `seed` is `None`, so `_fallback_lineage` records the lineage as unknown. The resulting CIR
  has no provenance and cannot certify (`gates/originality.py:122-129`, `PROVENANCE_MISSING`).
- It is a rebuild of an existing product, not new engineering.
- Reaching it requires a real certification that came after a legitimate approval.
- The cost is wasted compile work, plus a withdrawal that is silent for certified products.

**Suggested:** when `has_rows` is true and the slug is established *only* because it is
certified, either:
- audit `cir.draft_refused` (gate `radar.intake`), or
- state in `CONCEPT_INTAKE.md` that withdrawal does not reach certified products. Delisting
  is handled elsewhere.

### H2 — INFO — the lookups are exact-match, so a variant slug or provenance string is not recognised
`has_rows` compares the slug exactly, and the provenance check is a strict `startswith`.

**Reproduction** (scratch `probe.py case`): with the concept withdrawn, `cir.draft` was run
with each of these slugs:
- `TIDE-LINE-TABLE-RUNNER`
- `'tide-line-table-runner '` (trailing space)
- `' tide-line-table-runner'` (leading space)

Separately, a new slug was run with provenance `' radar.intake:…'` (leading space). Every one
drafted and enqueued `cir.compile`, and the upper-case variant compiled.

**Why INFO:**
- These are distinct artifact slugs, so nothing ties them to the withdrawn concept.
- The behaviour is identical to the pre-existing raw-geometry fallback, which any direct
  enqueuer can already reach with an arbitrary new slug (by design, "so the compiler's refusals
  stay reachable").
- `radar.score` enqueues the exact row slug, so the queued path is covered.
- Every such CIR has unknown lineage and is refused `PROVENANCE_MISSING` at certification.

**Optional hardening:**
- normalise the slug (`strip().lower()`) before `has_rows`;
- `strip()` the declared provenance, as `_fallback_lineage` already does.

### H3 — INFO
- **Only research and family candidates count.** `_current_fingerprints` keeps rows for these
  two candidate types alone. A row whose source no longer produces a candidate (for example, an
  expired task) can be pruned, but nothing exists to re-evaluate, so re-approval is impossible.
- **Two dates are in play.** `prune` takes `now.date()` while `run` may take an `as_of`. A
  fingerprint that depends on the date could therefore differ between them. The fingerprint
  carries no day-dependent quality (F1), so this is not exploitable today.

## Required before SHIP
None. H1 is recommended as a follow-up; H2 is optional.
