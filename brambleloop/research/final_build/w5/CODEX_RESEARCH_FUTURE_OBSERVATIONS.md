# Research future-dated observation handling — partial checkpoint

Local base: `codex/research-sweep-fairness` at `0f68c1d334d6f9c6005edac4610c9a16b8b5f33c`. The corresponding GitHub commit `e50251f3a43c28e1efd71cb32261f1b3dea175a3` has the same tree; its commit object was recreated through the GitHub connector.

A stored future-dated external observation formerly counted as fresh and could mask genuinely stale marketplace-policy evidence, preventing the normal research sweep from opening a needed question. New future-calendar-date observations are refused. Existing future-dated records are explicitly marked and excluded from freshness/radar counts: a future-only domain is unobserved, while a domain with only old plus future records remains stale. An explicit `today` parameter is a calendar-day as-of query; ordinary reads use the current UTC instant.

Python 3.11 file-backed SQLite in tmpfs: ten focused tests passed, including an actual research.sweep Worker that opens and queues a stale-policy question, future-only and future-write cases, date-level as-of semantics, and existing learning/research/Serp regressions. One additional focused test passed for a same-day future timestamp at an injected current instant. An independent reviewer reran three targeted tests. PostgreSQL and broad suites remain unrun under disk pressure.

DO NOT INTEGRATE as complete Research or Learning: timestamps, observations and research authority are not authenticated by this change, and source changes can race downstream reads and effects. Future-only domains are reported unobserved; this change does not itself open research for a never-observed domain. No production database, external service, or paid provider was used.
