# A4a intake owner recheck — partial checkpoint

Base: `codex/a4a-proposal-audit-recovery` at `29c10e90085845b6c3cf2e6b847d0bebe9cc27e1`.

Research intake now withholds ideation candidates when the stored task, gap or proposed slug no longer match. Approved-pool reads also withhold an ideation concept if its attached proposal has changed from the version judged. A prior intake decision's stored ideation trigger prevents silently reclassifying that existing decision as generic research when current markers are removed. Restoring the matching owner record restores visibility; the transient hold does not invent a new approval. Non-ideation research retains existing behavior.

Python 3.11: A4a, concept-intake and retention tests 85/85 on file-backed SQLite; opt-in `test_codex_a4a_recovery_postgres.py` 9/9 on disposable PostgreSQL 16 databases. Includes actual Worker radar.score on a reassigned gap, changed proposal, and removed current markers with intact prior decision. The previous recovery contention case invokes actual handlers with separately claimed durable jobs, not full Worker scheduler concurrency.

Limits: this is a sequential read-time hold, not a transaction fence: task/gap/proposal can change after a check and before intake approval or downstream work. Both source classification and prior decisions are mutable and unauthenticated; pre-decision marker removal or tampering with historical records is not ruled out. Existing downstream jobs, ingestion and every writer need a shared authority/ownership contract. This does not close A4a stopped-gap reopening, A4b enrichment or full integration. No production or paid provider used.
