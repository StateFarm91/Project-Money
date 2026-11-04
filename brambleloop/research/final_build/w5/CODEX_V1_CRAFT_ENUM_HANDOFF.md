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

The blind two-image comparator also previously passed a real compiled CIR
declaring edging when neither image reported seeing it. That observation now
holds UNKNOWN and cannot become a variant input. Both images visibly reporting
the declared edging still pass the comparison; existing definite mismatch
checks are unchanged. Python 3.11/tmpfs targeted suite 27/27; independent
declared-edging regression 1/1. This is not physical or authenticated evidence.

The blind comparison now also holds UNKNOWN when either image does not show a
colour present in the verifier's compiled-model render, or when its colour-usage shares
are malformed. A missing colour in the anchor does not prove the candidate
invented it. Unused palette entries do not create a visibility requirement;
the real compiled one-used/two-declared control remains PASS. Python 3.11/tmpfs
focused suite 33/33; independent used/malformed/unused-palette tests 6/6. This is a
conservative comparison, not proof of judge authenticity or physical fidelity.

The comparator previously interpreted a missing/malformed cable-presence flag or
edge-band classification as absence, and truthy malformed nested piece data as
presence. It now uses UNKNOWN for unrecognized or malformed fields, validating
the local band/repeat structure rather than trusting truthiness. Invalid numeric
spans are held rather than crashing. Python 3.11/tmpfs focused suite 44/44;
independent malformed-piece cases 7/7. Full verifier provenance and concurrent
source changes remain outside these checks.

**DO NOT INTEGRATE:** This is stacked on PR #47. Verdict metadata and stage-D
reads are unauthenticated and not fenced against concurrent writes. Existing V1
full-suite failures and the owner-controlled experiment remain unresolved.
