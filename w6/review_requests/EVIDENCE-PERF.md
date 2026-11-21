VERDICT: FASTER AND OUTPUT IDENTICAL ON EVERY SEEDED DATABASE. The repeated reads are gone: one provenance check per request, each product's lifecycle derived once, and the release blobs read in one pass instead of about four. The `ops/readback.py` timeout is now 120 s. **I could not reproduce 45-91 s locally.** The worst production-shaped seed I built took 9.6 s before and 6.5 s after, with a simulated 5 ms database round trip. Whether production drops under 10 s is UNVERIFIED until this is deployed and its `timing_ms` is read.

# Review request: eng/evidence-perf

**Branch:** `eng/evidence-perf`, cut from `claude/w6-release-19h4` (b42f89d). Not merged, not
deployed, no PR. Production unchanged: I read no production rows and no token-gated readback.

## What was slow (profiled, cProfile + per-section query counts)

On a seeded production-shaped DB, decoding JSON dominated the profile: about 14,600
`json.loads` calls, nearly all of them for `PatternVersion.cir_json` / `certificate`. The same
release history was loaded whole:

| reader | times per request (before) | what it needed |
|---|---|---|
| `lifecycle.derive` (certification board: 16; sale admission: 1 per parked release, 12) | 28 | the `certified` flag |
| `artefacts.newest_release` (factory_visibility `stale_incidents`) | 16 | the newest certified version string |
| `artefacts.current_from_db` | 1 query per product | `id, version, cir_json, release_hash, certified` (not the certificate) |
| `artefacts.check` | 1 (whole provenance rows) | 4 columns |
| `halted_releases` | 2 (publishing_halt, certification) | — |

`dead_letters` loaded every DEAD job ever, with its error text, and filtered by time in
Python. `factory_visibility.jobs_24h` loaded every job of five types ever.

## What changed (output identical)

- **`core/request_memo.py` (new).** A `ContextVar` memo opened by `production_evidence.evidence()`
  and `checks()` for one request only:
  - outside a scope, `memo()` is a plain call, so the worker, stage handlers and publication
    guard read live rows exactly as before;
  - a failed read is never cached (it stays UNKNOWN in every section that asks);
  - every reader gets a deep copy, except the read-only provenance verdicts;
  - scopes are re-entrant and never shared across threads or requests.
- **Memoised inside the scope:** `lifecycle.derive` (per slug), `release_recovery.halted_releases`
  and `listing_package.latest` (per `slug@version`).
- **`production_evidence.shared_provenance(db)`:** ONE `current_from_db` plus ONE `artefacts.check`
  per request, shared by every reader. `stale_incidents` takes the newest certified version per
  slug from `current.latest_version`. That is the same rule `newest_release` applied
  (`newest_version` over the certified versions, None when they cannot be ordered), so the
  16 whole-row queries are gone.
- **Column reads instead of whole rows** (shared code, same values):
  - `lifecycle._derive` reads `PatternVersion.certified` only;
  - `current_from_db` makes one ordered 6-column query for all releases, and fingerprints each
    CIR once, reusing that for the newest release;
  - `artefacts.check` reads 4 columns, ordered by id.
- **Bounded queries:**
  - `dead_letters` is limited to the window in SQL (`finished_at >= since`, or no `finished_at`
    and `created_at >= since`). This is a superset of the Python rule, which still re-checks
    every row.
  - `jobs_24h` keeps `created_at IS NULL OR created_at >= since`, exactly what the loop counted.
  - Both were checked against the base code with the same fixture, and they count the same rows.
- **Indexes** (additive; `core.migrate` creates missing indexes on an existing DB):
  - `ix_jobs_type_status_finished (job_type, status, finished_at)`: the newest DONE/DEAD job of
    a type;
  - `ix_audit_log_action_id (action, id)`: the newest row of an action;
  - `ix_audit_log_action_at (action, at)`: windowed reads.
- **`ops/readback.py`:** `HTTP_TIMEOUT_S = 120`, replacing the 60 s literal.

No field was dropped and no projection was widened. No-private-text holds: the seeded
inputs, outputs, error text, incident summaries and prompts never appear in the body.
UNKNOWN and 0 stay distinct: an unreadable provenance read is `{"readable": false,
"error_class": ...}` in every reader, never `open: 0`.

## Measurements (local SQLite; `sleep` per statement simulates DB round-trip latency)

Each body was compared with `cmp` after removing the two wall-clock fields (`timing_ms`,
`parked_admission_ms`). The rest was **byte-identical before and after** on all three DBs.

| seed | before 0 ms | after 0 ms | before 5 ms RTT | after 5 ms RTT | queries before → after |
|---|---|---|---|---|---|
| default (16 products × 8 releases, 120 KB CIR) | 0.94 s | 0.73 s | 3.93 s | 3.06 s | 565 → 448 |
| big (× 13 releases, 400 KB CIR, 100 KB cert; 121 MB DB) | 2.68 s | 1.57 s | 6.59 s | 4.91 s | 725 → 608 |
| huge (× 15 releases, 800 KB CIR, 200 KB cert, 15k jobs and audits; 278 MB DB) | 5.47 s | 2.98 s | 9.58 s | 6.46 s | 757 → 640 |

In every seed, `factory_visibility` was the slowest section before. After the change, the
single `current_from_db` pass is almost all of what remains in it. (The "before" runs reused
DB files that already had the new indexes.)

**Honest gap.** None of my seeds reaches 45-91 s. Production must differ in volume, latency or
data in a way I could not see without reading production. The fix removes repeated whole-blob
reads that scale with releases × products × parked runs, which is the shape the brief
suspected. Whether that was production's dominant cost is UNVERIFIED. After deploy, read
`timing_ms` and `factory_visibility.parked_admission_ms` from the evidence body: that settles it.

## Not changed (named, not hidden)

- `current_from_db` still decodes and fingerprints every release's CIR once per request. That
  is inherent to the check: `pipeline.py` rewrites `cir_json` in place, so caching it across
  requests would be unsafe.
- `visual_pipeline._vp_pdfs` makes about 2 queries per certified release (`_certified_pdf_hashes`).
  It is bounded by the number of releases and was left as is.
- `engine_demand` builds twins per held concept (CPU, about 0.4 s here). Left as is.

## Tests

New suite `tests/test_evidence_perf.py`, 7/7 passing. It uses the seeder `tests/_evidence_seed.py`:
600 provenance rows, 200 incidents, 16 products, 6000 jobs, 6000 audits, 40 parked runs.

- The production-sized evidence must build in under 30 s. This bound is generous: it takes
  0.35 s here. It also passes on the base, so it guards gross regressions only.
- Exactly one `check` and one `current_from_db` per request, each slug derived once,
  `halted_releases` read once, and each listing package read once. **Fails on base.**
- The body is identical with the memo disabled, and `checks()` gives the same result with and
  without its scope. **Fails on base** (no `_checks`).
- The memo is request-scoped. A new incident is seen by the next request. Outside a scope the
  memo calls through. Readers get copies. A failure is never cached and stays UNKNOWN.
- No seeded private text appears in the body.
- The bounded dead-letter and job-count queries count the same rows as the full scans (also
  passes on base, as it should).
- The new indexes exist after `create_all`, and `HTTP_TIMEOUT_S == 120`. **Fails on base.**

Suites run on this branch, all passing:

- the required suites: `test_w4_readback_evidence` 23/23, `test_factory_visibility`,
  `test_vacuity`;
- `test_artefacts`, `test_provenance`, `test_w4_provenance`, `test_provenance_backfill`,
  `test_provenance_write_path`, `test_rebuild_graph`;
- `test_halt_380_verify`, `test_halt_380_h3`, `test_eng_halt_380`, `test_incident_lifecycle`;
- `test_w4_c12_lifecycle`, `test_w4_fmbatch1_lifecycle`, `test_w4_fmbatch2_lifecycle_pipeline`;
- `test_opus2_listing_package`, `test_w4_auditfix_migrate`, `test_w4_close6_readback`,
  `test_eng_improve_readback`, `test_w3_k7_ops_truth`, `test_platform`,
  `test_opus2_owner_queue_races`, `test_l0_physical_upgrade_provenance`,
  `test_w4_auto_provenance_concurrency`.

The full `run_tests.sh` was NOT run.

## For the reviewer

- `request_memo` can only make reads within one request consistent with each other: a
  snapshot instead of the reads drifting while the body is built. Check that nothing inside
  `evidence()` writes rows and then expects a memoised reader to see them. The `ensure_tables`
  calls in `factory_visibility` create missing tables only; they write no rows.
- `artefacts.check` and `current_from_db` now `ORDER BY id`. Before, they relied on natural
  order, which is id order on SQLite but not guaranteed on Postgres. Which duplicate-version row
  "wins" is now deterministic and matches SQLite.
