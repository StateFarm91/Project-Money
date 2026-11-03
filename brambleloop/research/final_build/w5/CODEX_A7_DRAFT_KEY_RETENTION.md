# A7 permanent draft admissions — partial retention fix

Base: `codex/a7-supply-continuation` at `4213b2ac0c736163232f2efb8ef7744105f4c260`.

Radar treats `draft:<slug>` keys as permanent admissions. Previously both ordinary retention and dead-letter pruning could remove an unreferenced job and free this key, allowing a duplicate draft and false available-supply signal. This branch protects those keys regardless of job status, including in `JobQueue.purge_dead`, and rechecks keys immediately before the retention deletion. This is a conservative storage policy: permanent rows accumulate, and cancelled attempts remain held until an independently authorized recovery design is provided.

A persistent SQLite test uses actual `retention.apply`, queue purge and enqueue, reopens the database, and verifies completed, cancelled and dead admissions remain deduplicated while unrelated old jobs are removed. No deployment or production mutation occurred.

**Limitations:** This only preserves rows that still exist. Previously deleted keys cannot be reconstructed safely without historical evidence; direct database DELETE or idempotency-key mutation outside these paths is not fenced. The change does not implement capacity admission, portfolio rotation, or a safe explicit retry authorization. PostgreSQL concurrency and independent review remain required. Do not treat this checkpoint as full A7 or P0 completion.

An independent review found recovery and rebuild paths legitimately enqueue `cir.draft` under other keys. A follow-up preserves all draft jobs, counts their actual input slug when reporting supply, and makes the real `radar.score` handler hold a recorded admission. This is a conservative read-time mitigation: a competing producer can still admit between the read and enqueue. Those paths need a shared atomic admission authority that distinguishes approved rebuilds from new product admissions; neither this branch nor its tests prove global idempotency.

Retaining entire job rows indefinitely also retains their inputs, outputs, and errors. This has storage and privacy implications and needs a reviewed minimal durable tombstone and data-retention policy before production use.
