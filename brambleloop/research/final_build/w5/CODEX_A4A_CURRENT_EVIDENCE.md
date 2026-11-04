# A4a current research evidence — partial checkpoint

Base: `codex/a4a-intake-owner-recheck` at `230f148d65f78ecab37667d7fb0f504edb319b5e`.

Research evidence no longer treats future-dated sources or future answer timestamps as current. Missing, malformed or future source dates and missing or malformed supports on a finding produce named refusal reasons instead of crashing the intake worker or borrowing a date from another valid source. Research-backed approved-pool reads now recheck cited evidence, so a source becoming invalid is withheld immediately rather than waiting for the next intake sweep. The next actual intake Worker still withdraws the unsupported decision.

Python 3.11, file-backed SQLite: A4a, concept-intake and retention suites 90/90. Disposable local PostgreSQL 16: opt-in `test_codex_a4a_recovery_postgres.py` 14/14, including five new real Worker evidence changes and prior recovery/owner cases. An independent reviewer reran the five targeted SQLite cases and checked the changes.

Limits: current evidence is re-read in separate sessions, not held under a common transaction through downstream effects. Research task, source, audit and prior intake rows are mutable and not authenticated; another writer can change them after revalidation. The change does not establish source provenance, close A4a stalled-task reopening or A4b enrichment, or grant integration or production approval. No production database or paid provider was used.
