# A4a census price resilience — review checkpoint

Base: `codex/a4a-research-truth` at `bc65dd88010f20843eefc8c1f4d44676c2a1d86a`.

A malformed legacy SQLite price previously raised an exception in the research census and stalled the real research worker. Non-numeric, non-finite and non-positive prices are now unknown and excluded from price statistics; they do not become zero or an invented amount. A census with no valid prices remains insufficient. Tests use a persistent SQLite database and actual worker handlers, including all-invalid records; the known typed database value is used, not a claim about the source's original type.

This does not close source-task ownership, stale research jobs, audit recovery, PostgreSQL validation, or full A4a integration. The earlier Product Truth / source identity guards remain necessary. No network or paid provider was used in these tests.

Python 3.11.17, file-backed SQLite: `test_w5_a4a_research_to_concept.py`, `test_intel.py` and `test_w4_intelrec_watchlist.py` passed 93/93. Independent reviewer reran 5 targeted tests and confirmed booleans and numeric text are refused by the reader. This does not verify PostgreSQL or source-side type preservation.
