# Release notes: candidate a25a3774 (INTEG3), not deployed

- Full suite: run 20261013T022833Z-14781, 631 suites and 8563 tests passing, 0 failing, 0 tmp leak.
  It ran with REQUIRE_CLEAN=1 and JOBS=3.
- Schema change: one **widen-only** migration in `core.migrate.widen`, run inside
  `Database.create_all` at boot. It changes `policy_snapshots.version` from VARCHAR(40) to
  VARCHAR(120) on Postgres only, under `SET LOCAL lock_timeout = '5s'`.
  - The change is additive: no data is altered, no column is dropped, and nothing is ever
    narrowed.
  - It is rollback-safe. Rolling back to 7bbbe72 keeps the wider column, because the old code
    never narrows and works with VARCHAR(120); old code that seeds a reading then succeeds.
  - It is reversible by hand while no stored value exceeds 40 characters. After this build seeds
    its 49-character readings, a narrowing would need those rows removed first, and no such
    narrowing is needed for a rollback.
- The candidate fast-forwards from production 7bbbe72 (7bbbe72 is an ancestor).
- Details: `research/final_build/w4/INTEG3.md`.
