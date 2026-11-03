# V0 paid-provider reservation binding: review handoff

Continuation branch `codex/v0-provider-authority` is based on Secondary's
`opus2/v0-paid-provider-gate` at `76fc0f3d6b6d2588e7953cf369b81bd7e99acd74`.
The original branch remains unchanged.

Review of that exact parent found that `authorize` accepted the same CA$0.001 live
company reservation for two distinct CA$0.40 paid-call tickets. The monthly
ceiling counted the one small reservation while authorizing both larger attempts.
The reproduction used a durable SQLite file and did not call a provider.

This continuation requires that each company reservation cover the paid-call
estimate and that a reservation has never backed a previous attempt. Both checks
and insertion are inside the existing budget lock, which uses a process lock and
SQLite write lock or PostgreSQL advisory transaction lock. Declined attempts also
consume their reservation; a retry must obtain a new company budget decision.
No activation, spending ceiling, provider setting, or production data was changed.

Focused tests cover an underfunded reservation, sequential reuse including after
release, concurrent reuse against one SQLite file, and normal owner-authorized
flows. A PostgreSQL concurrency test and independent security review remain
necessary; no integration, production certification or deployment is claimed.

## Independent review: blocking findings

Do not integrate or activate V0. A reservation can be released or expire after
authorization while the paid attempt remains unresolved, and the company ceiling
can forget that exposure; a pre-send recheck cannot close the race. Probe scope is
caller controlled, so probe-only activation can authorize an arbitrary image
prompt. Both require correction and independent review. See Issue #28.

The subsequent partial hardening refuses negative/nonfinite settlement and counts
missing or zero usage at the estimate in the provider ledger. It does not establish
that all company CostEntry writers do the same. Retention now preserves reservation
rows referenced by provider attempts to avoid future SQLite ID reuse. Previously
deleted or reused IDs are not automatically recoverable and require reconciliation.
Neither change closes the company exposure or probe authority blockers.

The probe-scope follow-up restricts image and vision requests marked as probes to
their fixed diagnostic prompts and request shapes. Fake-transport tests refuse
arbitrary generation and vision prompts under probe-only activation. This is
implementation for independent security review, not an accepted authority model;
other paid-provider entry points and post-check races must still be reviewed.

The OpenAI research judge now counts invalid, missing or all-zero token usage at
its documented worst-case estimate, rather than crediting its process cap or
calling a paid response free. The test uses a fake HTTP response. The shared
company-ledger reconciliation and orphan exposure described above are still open.

## Conservative orphan-exposure guard (review required)

The company monthly budget and the V0 authorization recheck now include paid
attempts not covered by a live company reservation, under the same budget lock.
An uncertain or still-reserved attempt continues across month boundaries;
a billed attempt is included through its settlement month. An estimate not covered
by its live reservation is added; a reservation covers at most one attempt,
and a reservation created after an attempt cannot be its backing reservation.
Invalid historical estimates cause refusal, not a credit. Released/expired
reservation and persistent-SQLite concurrency/restart cases are tested.

This deliberately does not subtract any ledger entry: already booked spend can
be counted twice. It is a conservative safety hold, not completed financial
reconciliation; paid work may pause after otherwise successful calls. A durable,
reviewed binding between the attempt and exact CostEntry is still needed, as are
PostgreSQL race tests and independent review. The DO NOT INTEGRATE / no paid
production use decision remains. Probe-only Anthropic vision is also restricted to
its fixed diagnostic model and the current audited diagnostic image selected from
stored benchmark observations. Independent review of source selection, licence
handling and all provider paths is required.

A follow-up changes ambiguous exceptions after entering the image, Anthropic
vision and OpenAI research-judge transports to UNCERTAIN. Wrapped resets,
malformed 2xx bodies, and similar failures are not proof of a declined call.
Fake-transport tests exercise all three against persistent database state.
This can conservatively hold funds after a provider refusal. The lifecycle and
reconciliation remain unresolved and the no-integration hold stays in force.
