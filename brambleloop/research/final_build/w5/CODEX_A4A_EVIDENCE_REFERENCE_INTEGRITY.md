# A4a research evidence-reference integrity — partial checkpoint

Base: `codex/a4a-evidence-dates` at `b057f54422c8fb85237fd3c7aaf83ea6bdffc566`.

The intake evidence reader previously built dicts keyed by recorded evidence identifiers, silently selecting one of multiple matching records, and could count a repeated citation more than once in fact-share. Malformed records could also crash the intake sweep. Research evidence now holds malformed records, duplicate identifiers, identifiers colliding across evidence kinds and duplicate proposal citations. Duplicate citations are counted only once when reporting quality. Current pool reads withhold unsupported concepts, and the real intake worker records withdrawal/refusal.

Python 3.11 file-backed SQLite: A4a, concept-intake and retention 94/94. Disposable local PostgreSQL 16: opt-in `test_codex_a4a_recovery_postgres.py` 18/18, including three new actual Worker cases and a citation-quality case. An independent reviewer reran the four targeted SQLite tests and examined the namespaces used by current writers.

This validates record shape and ambiguity; it does not authenticate source records or historical evidence, nor does it create a transaction fence through intake and downstream work. Concurrent changes, A4a task ownership and A4b enrichment remain unresolved. No production database or paid provider was used.
