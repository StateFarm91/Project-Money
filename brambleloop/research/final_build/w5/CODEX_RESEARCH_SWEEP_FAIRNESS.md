# Research sweep fairness — partial checkpoint

Base: `codex/research-nochange-history` at `ff3debb0b3ad9d690a5e1d3c5e6dd745d54757df`.

The research sweep previously sliced the first 25 due tasks before checking whether their same-day idempotency keys already existed. A run of 25 terminal same-day jobs could therefore prevent every later due task from being considered. The sweep now skips recorded same-day keys, queues up to 25 successful jobs, and bounds real enqueue attempts at 100. It records attempt count and whether that attempt bound was reached. Daily idempotency and stopped-task controls remain in place.

Python 3.11 file-backed SQLite in tmpfs: six focused tests passed. Real Worker tests cover 25 dead-key tasks followed by a runnable 26th, the 25-job cap, a competing insertion after the key snapshot, the 100-attempt bound and the existing new-evidence flow. Independent review reran the first two cases and the final interleaving/bound cases. No broad suite or PostgreSQL test ran under workspace disk pressure.

DO NOT INTEGRATE as complete research recovery. The existing-key read and queue insert are not one transaction. Concurrent sweeps do not share a global 25-job cap and can change due state after the snapshot; extreme concurrent insertion can defer later tasks at the 100-attempt bound. Legacy audit authority, stopped-task generation, and A4a/A4b ownership remain unresolved. No production database, paid service or shared branch was used.
