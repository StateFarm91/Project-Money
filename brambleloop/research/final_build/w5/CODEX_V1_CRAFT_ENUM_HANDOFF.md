# V1 blind craft enum — review required

`codex/v1-craft-enum` continues `codex/v1-variant-base` at
`100f06496e108ca8ece2cc4899c11dc2339118a8`; the previous branch is unchanged.

The blind craft comparator previously treated an unsupported or malformed craft
label as a definite mismatch, even when the judge had not described a recognized
craft. Such readings now remain UNKNOWN and are marked unsuitable for stage-D
edit reuse. Previously stored UNKNOWN craft readings with an explicit unreadable
craft field are also held even without the new marker. A clearly observed
different supported craft and any independent image defect remain FAIL. This
does not turn uncertainty into PASS or assert
physical evidence.

Python 3.11, SQLite/tmpfs: 9/9 focused craft, obscured-image, variant-input,
cable and unfunded-judge cases. Independent reviewer reran the five enum cases
and the persistent variant-input case including the marker-less legacy reading
and confirmed the narrow behavior. No paid call or deployment occurred.

**DO NOT INTEGRATE:** This is stacked on PR #47. Verdict metadata and stage-D
reads are unauthenticated and not fenced against concurrent writes. Existing V1
full-suite failures and the owner-controlled experiment remain unresolved.
