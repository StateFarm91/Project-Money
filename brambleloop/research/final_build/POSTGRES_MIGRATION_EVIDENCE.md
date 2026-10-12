# Postgres migration evidence — production fcb982d schema → Final Build head

Date: 2026-10-05 (UTC). Local Postgres 16 cluster (unix socket, trust auth, throwaway), not Railway.
Producer: `core/db.Database.create_all()` → `Base.metadata.create_all` + `core/migrate.apply`.
Consumer under test: HEAD ORM (`brambleloop.core.models`), code at 448e87c/85fdca0 (src identical).

## Run 1 — empty production schema
1. `git archive fcb982d brambleloop/src` → production code; `Database(url).create_all()` on fresh DB → 51 tables.
2. HEAD code `create_all()` on the same DB → **21 changes** (new tables + added columns + indexes);
   `migrate.plan(engine)` afterwards → `[]` (idempotent); 83 tables.

## Run 2 — data preservation (DB `migr2`)
1. Production code created schema, then a seeder inserted one row into **every** production table
   (51/51 seeded, 0 failed; generic type-based values; per-table counts recorded).
2. HEAD code `create_all()` → 21 changes; `migrate.plan` afterwards → `[]`.
3. Results:
   - Row-count mismatches vs pre-migration counts: **none** (51/51 tables preserved).
   - Rows with NULL in any newly added column: **none** (scalar defaults backfilled).
   - Legacy `ledger` row after backfill: `basis='unknown'`, `fees_basis='unknown'`,
     `reconciliation_state='unreconciled'`, `currency='CAD'` — i.e. legacy money rows are
     marked UNKNOWN/unreconciled, never silently promoted to measured.
   - HEAD ORM `select … limit 1` over every mapped class: **0 errors**.

## Limits (honest)
- Seeded rows are synthetic, one per table; production row volumes/edge values not reproduced.
  A pre-deploy rehearsal against a snapshot of the real Railway database remains required
  (owner/deploy gate — production DB not touched; not authorized).
- No down-migration exists; rollback = redeploy fcb982d code, which ignores the added columns/tables
  (additive-only migration). Verified additive: no column drops/renames/type changes in the plan.
