# A5 correction hold audit continuation

Source: `codex/a5-correction-review` at `e68c93168e912f58ca7ac6c68c252016ae3a3d00`. This isolated continuation addresses only A5-8 for holds owned by the correction loop.

A repeated identical observation still restates the named open incident (`last_seen` and `report_count`), but no longer appends an identical `correction.held` audit. An opened, changed, or reopened hold is audited. A5 hold writers serialize via a transaction lock; incident changes and their audit commit together. Holds owned by other departments retain the prior behavior.

Python 3.11 / file-backed SQLite: A5, W5 integration, reverify withholding and retention suites 49/49 before adding one additional fault-injection case. Four targeted tests pass on the final source: real-handler lease replay, changed/reopened evidence, two concurrent A5 writers, and audit-write failure rolling back incident and successful retry. Python 3.11 / real disposable PostgreSQL 16: concurrent identical A5 writers 1/1 through `tests/test_codex_a5_hold_postgres.py` with a local opt-in URL.

Independent review required. This does not serialize writers outside this A5 path, resolve stale incidents for old versions (A5-6), address holds owned by other departments, or certify the complete correction pipeline. The pre-existing foreign-artifact provenance race, PostgreSQL coverage outside this focused test, integration conflicts and other findings in PR #30 remain open. No deployment, production changes or new approval authority.

## Independent review follow-up: stale worker

An independent reviewer found that the original audit-deduplication change allowed a stale producer to overwrite a newer observation. The updated A5-owned hold transaction locks the producer job row, checks a supplied lease token, status and expiry, and refuses a stripped token when the persisted job carries a token or a missing referenced job. Explicit unclaimed direct contexts remain supported; this is not a general worker-authentication contract. Five targeted SQLite tests and two real PostgreSQL 16 tests pass, including stale/stripped/missing producer cases. The A5 and related SQLite suites passed 51/51 before the final missing-producer check and its assertion; the final focused tests cover that last change. A job-first writer can still create lock-order contention, and a lease may expire between validation and transaction commit. Non-A5 writers do not take this advisory lock. Independent review and broader concurrency testing remain necessary.
