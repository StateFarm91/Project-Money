# Preserve quality hold if incident bookkeeping fails

Stacked on PR #104 (`d373da8`). The actual quality Worker previously attempted incident bookkeeping before writing the publication hold. A synthetic incident failure after a confirmed failed policy check therefore left the release without the expected durable hold while the job retried.

For a failed check the worker now records the existing quality publication hold first, then records the incident. The synthetic real Worker test injects an incident failure, verifies the job remains retryable and the hold persists, then expedites the synthetic retry and verifies the incident is recorded. The production retry policy is unchanged. Python 3.11 tmpfs SQLite quality and withholding regressions passed 27/27.

This is an ordering correction, not atomicity: a failed hold write, a crash, or a concurrent writer is not solved by this change. On the successful path the existing ordering remains: if incident resolution succeeds but hold removal fails, the incident can appear resolved while publication remains conservatively held until retry. Release/actor authentication, shared transaction fencing, PostgreSQL and integration remain open. No physical evidence, owner approval, purchase, publication or deployment occurred.
