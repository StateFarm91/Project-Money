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

Malformed or unavailable edging facts now hold UNKNOWN instead of being treated
as no edging. In particular, Cloudline's ambiguous end-band/edging state cannot
support a definite invented-edge FAIL or a PASS merely because both images show
an edge. The existing definite-invented-edge assertion remains intact and now
uses a real compiled no-edging basket as its control. Matching unsupported
band/cable claims in both images also hold UNKNOWN rather than passing. Python
3.11/tmpfs targeted suite 50/50; independent ambiguity case 1/1. No physical
or authenticated visual evidence is claimed.

Malformed craft, cable, ribbing or edging facts in the expectation now hold
the craft check UNKNOWN and block stage-D edit reuse. A separate definite craft
mismatch still fails. Python 3.11/tmpfs focused tests passed 55/55, including
persistent stage-D selection; an independent reviewer reran craft and stage-D
tests 11/11. Existing knitted-rope assumptions remain a separate review item.

Direct malformed or absent craft-reading inputs now also carry the edit-input
block marker. A persisted stage-D regression confirms this marker is honored.
The normal vision handler already converts an absent reading to an empty mapping;
legacy markerless no-reading results and unavailable-judge policy are unchanged.
Python 3.11/tmpfs focused tests passed 58/58.

The two VISNEXT wardrobe retry tests now use a clearly identified synthetic
photo-reference test double. Their original wardrobe, correction and learning
assertions are unchanged; chart-only references still follow the separately
tested structural hold. Together the VISNEXT and V1 correctness suites pass
53/53 on Python 3.11/tmpfs; independent review reran both wardrobe cases and
two structural hold controls 4/4. Synthetic reference bytes establish routing
only, not physical provenance, authority or fidelity.

An older lifestyle-positive test used Cloudline despite this route's inability
to authenticate its ambiguous band evidence. Its positive and dependency-drop
assertions now use a real compiled no-band design; an explicit Cloudline case
still requires UNKNOWN when the caller supplies only an anchor PASS. The full
offline fidelity suite had 21 passes and this one failure before the fixture
correction; the corrected case passed separately. No production authority or
physical fidelity is established by these synthetic images.

Visual restart previously committed the new epoch before enqueueing its job;
an interruption could strand the run. The restart transition and its queue
insert now share the caller's database transaction, with a locked run and a
stale run-state check. The two Command Center image callbacks pass that
transaction to the existing durable queue. Persistent SQLite tests cover an
interruption after insertion, a conflicting idempotency key, successful retry,
normal restart and identity-review restart. Three focused tests passed; an
independent reviewer reran the interruption/duplicate test. This does not
fence concurrent evidence writers, make identity review and restart one
transaction, or establish PostgreSQL concurrency behavior. Integration remains
blocked pending those checks and the previously recorded authority gaps.

Visual spend planning now refuses non-finite, negative or malformed plan and
runtime amounts, malformed call counters, and paid generators without a
positive maximum price. Raw stored counters reach validation before a call.
Python 3.11/tmpfs focused tests, including actual generation entry and existing
plan and paid-gate controls, passed 28/28; independent reviewer reran 25/25.
No provider was called. These checks trust the generator's free/paid declaration
and do not provide cross-process budget reservation or global budget proof.

A paid image dispatch now records a pending marker before the provider call;
missing, malformed or excessive cost and interrupted calls hold later
generation for review. Valid receipts record the actual charge. Free-adapter
settlement reads current stored spend under the run lock and holds unexpected
charges or missing receipts. Offline Python 3.11/tmpfs tests passed 33/33;
independent review reran the spend cases 31/31. No provider was called. These
are synthetic SQLite tests, not PostgreSQL concurrent-writer verification;
other stage writers, central finance accounting, billing truth, and interruption
after receipt but before candidate recording remain open. No reconciliation
workflow or authorization to clear a pending marker is provided here.

The paid-call marker now persists after a valid receipt until a candidate with
the same recorded call token, run, stage and cost is stored. Duplicate receipt
settlement and substitution of a different candidate are held. An injected
candidate-storage interruption leaves recorded cost and the hold in place.
Python 3.11/tmpfs tests passed 33/33 including existing paid-gate coverage;
independent review reran the spend cases 32/32. The token and candidate record
are mutable metadata, not authenticated evidence. Interruption after candidate
completion but before stage transition remains unresolved, as do PostgreSQL
concurrency, noncooperating writers and company-wide budget fencing.

The ordinary visual stage checkpoint and controlled-run metadata update now
take the same run-row lock used by the pending-call writers before changing
stage JSON. Focused Python 3.11/tmpfs tests passed 35/35; an independent
reviewer reran the ordinary checkpoint/hold case. SQLite does not establish
row-lock serialization. PostgreSQL concurrency, bulk SQL and other modules'
writers, evidence authority and company-wide finance fencing remain open.

Correction to the earlier token checkpoint: candidate checks are mappings, so
the token is now stored in a mapping instead of a scalar. A fake paid adapter
test exercises the actual generation, persistence and candidate-selection path.
The selector also recognizes the scalar field from earlier isolated test rows;
this does not migrate or authorize their pending markers. Python 3.11/tmpfs
spend, anchor and variant tests passed 44/44; the fake-paid selection case was
independently rerun. No real provider was called.

Visual stage invocations now record an operation key scoped to run, stage,
epoch, round, role and identity-anchor correction. A retry can reuse its
persisted candidate after checking identity and artifact bytes, retaining the
original attempt and follow-on job key. A different correction round still
generates separately; conflicting cost holds block replay. Real handler tests
cover failed follow-on enqueue, interrupted paid-marker completion and changed
candidate bytes. Python 3.11/tmpfs spend/recovery tests passed 38/38; independent
review reran the key handler cases. Existing candidates without operation keys
are not migrated, and metadata remains mutable. Reads, marker completion and
stage advancement are separate transactions: PostgreSQL concurrency,
noncooperating writers, evidence authority and company budget fencing remain
unverified. No real provider was called.

An additional real `remaining_roles` handler test interrupts after one saved
candidate, then retries with a one-attempt-per-role cap. The first role is
reused and only the second is generated; an independent reviewer reran the
case. The Python 3.11/tmpfs spend and recovery suite passed 39/39. This uses a
free synthetic generator and does not establish concurrent or paid-provider
behavior.

The identity-anchor stage now has an interruption test covering an initial
synthetic image plus one bounded correction. Retrying after the corrected
candidate is saved makes no third image. The new case and existing correction
and identity-anchor flows passed 3/3 in Python 3.11/tmpfs; an independent
reviewer reran the new case. This is not a real identity or provider test.

**DO NOT INTEGRATE:** This is stacked on PR #47. Verdict metadata and stage-D
reads are unauthenticated and not fenced against concurrent writes. Existing V1
full-suite failures and the owner-controlled experiment remain unresolved.
