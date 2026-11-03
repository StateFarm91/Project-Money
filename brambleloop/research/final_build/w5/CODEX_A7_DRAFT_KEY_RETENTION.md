# A7 permanent draft admissions — partial retention fix

Base: `codex/a7-supply-continuation` at `4213b2ac0c736163232f2efb8ef7744105f4c260`.

Radar treats `draft:<slug>` keys as permanent admissions. Previously both ordinary retention and dead-letter pruning could remove an unreferenced job and free this key, allowing a duplicate draft and false available-supply signal. This branch protects those keys regardless of job status, including in `JobQueue.purge_dead`, and rechecks keys immediately before the retention deletion. This is a conservative storage policy: permanent rows accumulate, and cancelled attempts remain held until an independently authorized recovery design is provided.

A persistent SQLite test uses actual `retention.apply`, queue purge and enqueue, reopens the database, and verifies completed, cancelled and dead admissions remain deduplicated while unrelated old jobs are removed. No deployment or production mutation occurred.

**Limitations:** This only preserves rows that still exist. Previously deleted keys cannot be reconstructed safely without historical evidence; direct database DELETE or idempotency-key mutation outside these paths is not fenced. The change does not implement capacity admission, portfolio rotation, or a safe explicit retry authorization. PostgreSQL concurrency and independent review remain required. Do not treat this checkpoint as full A7 or P0 completion.
