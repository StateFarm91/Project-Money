# Research no-change history — partial checkpoint

Base: `codex/research-failed-audit-recovery` at `d22785bfcffab5d85c165b087fc95cd0e9d303ed`.

The no-change reader formerly limited itself to ten raw audit rows before excluding failed jobs and duplicate events. A burst of failed attempts could hide older completed investigations, defeating the bounded no-change stop. The query now filters noncompleted job-bound rows first, excludes future audit timestamps, and counts distinct completed jobs. It scans at most 1,000 candidate rows and holds for reconciliation if ambiguity exceeds that bound; malformed/missing evidence in an otherwise eligible audit also holds rather than pretending the history changed. Existing jobless historical rows retain legacy handling and are not authenticated.

Python 3.11, file-backed SQLite in tmpfs: seven focused cases passed. Tests exercise a real Worker stopping after completed history obscured by twelve dead-job audits, a bounded-history refusal, future/malformed records, real Worker no-change behavior, duplicate audit deduplication and failed-audit recovery. Independent review identified the malformed-history gap that was fixed; it reran four targeted cases across both revisions. Broader suites and PostgreSQL were not run under workspace disk pressure.

DO NOT INTEGRATE as full research recovery: jobless history and task attribution remain unauthenticated; concurrent writer and enqueue races are not fenced; stalled/stopped generation recovery remains open. The cap can require manual audit reconciliation for an abnormally long ambiguous history rather than inventing a decision. No production database or paid provider was used.
