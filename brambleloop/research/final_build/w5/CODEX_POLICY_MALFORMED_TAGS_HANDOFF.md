# Policy re-verification must not coerce malformed tags

Stacked on isolated quality/policy integration preview PR #112 (`6f2c3cd`). The real `gate.policy` Worker previously converted the stored JSON tags with `list(...)`; a malformed object with a benign key became an apparently valid tag list and a passing policy recheck could clear an existing publication hold.

Policy re-verification now requires a list/tuple of strings. Malformed objects, strings, nulls and non-string members produce a failed check and retain the quality hold; a corrected valid tag list can pass and clear that check's hold. Existing title and description checks still run. This is scoped to the operational policy recheck and does not claim every direct policy caller validates tag data.

Python 3.11 tmpfs SQLite policy/quality/withholding regression passed 32/32. An independent reviewer reran the synthetic actual Worker hold/malformed-data/recovery case 1/1. This does not fence concurrent listing changes, authenticate authority or establish PostgreSQL or production acceptance. No physical evidence, owner decision, purchase, publication or deployment occurred.
