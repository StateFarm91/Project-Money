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

Probe-only authorization no longer permits the reference-conditioning second
request: until the first diagnostic output can be durably bound to that request,
reference probing requires an active generation authorization and checks this
before sending the first render. An arbitrary PNG under probe-only authority was
refused with no fake transport call. This is an intentional availability hold;
no new generation authorization is created. Independent review is still needed.

The legacy company and agent budget readers now refuse negative or non-finite
ledger amounts instead of letting them become spend credits. The persistent
SQLite test uses the real `Registry.record_cost` writer and confirms both company
readers and the agent reader hold. This is a reconciliation hold, not a repair
of invalid records. Direct writers can still record malformed or unknown usage;
a complete fix needs trustworthy positive estimate settlement and durable
reconciliation for all provider and ledger paths. DO NOT INTEGRATE remains.

A follow-up conservatively records invalid/missing model-response token counts at
the pre-call estimate in `ModelGateway._billing`, and does the same for invalid
non-cached usage at `routing.record`. Real gateway and durable-ledger tests
cover negative, missing and fractional counts. This does not certify every
provider's direct cost writer: independently audit the remaining paths and
reconcile unknown or historical bad rows before integration.

An unrecognized paid-attempt outcome was previously outside every counted
status and could silently free its budget exposure. Settlement now records an
unknown requested outcome as UNCERTAIN; a historical status outside the known
set holds company-budget accounting until reconciliation. A real durable SQLite
test checks restart and refusal by the authorization handler. Python 3.11 V0
and model-spend suites pass 57/57 with fake transports; no paid call was made.
This conservative hold does not repair unknown historic records or establish
complete provider-ledger reconciliation. PostgreSQL and independent review
remain required; DO NOT INTEGRATE remains.

An opt-in regression in `tests/test_codex_v0_postgres.py` ran against a freshly
created, loopback-only disposable PostgreSQL 16 database and passed: two
simultaneous real `authorize` calls sharing one funded reservation yielded one
allowed call and one `reservation_already_used` refusal. No paid provider was
contacted. This is one concurrency case, not a certification of all reservation,
release, settlement, or ledger races. Independent review remains required.

Settlement now takes the same budget lock as check-and-reserve. Contradictory
settlement outcomes (including two different billed amounts) hold UNCERTAIN at
the greatest known positive amount, in either order. File-backed SQLite cases
pass, and separate processes on a disposable PostgreSQL 16 database also
preserved the higher exposure. Python 3.11 V0/model-spend regressions pass
59/59 with fake transports. An independent reviewer found the repeated-bill
case, which is now covered.

These are known amounts or estimates, not proof that an unknown provider bill
cannot exceed the recorded exposure. Full reconciliation remains necessary.
The in-repository `settle` callers (`confirm` and `enforce`) call it outside
`budget_lock`; a caller entering `settle` while already holding that lock in
another session could self-block. Do not integrate until all callers and lock
ordering are reviewed and this API contract is enforced. Missing-table
continuity, other provider paths and the no-paid-provider hold also remain.

The same-execution-context nested budget transaction now refuses immediately;
`settle` exposes that refusal instead of swallowing it, so the caller can retry
outside the lock and the existing RESERVED exposure stays counted. Python 3.11
V0/model-spend regressions passed 61/61, and the opt-in PostgreSQL 16 test
verified the nested refusal and later settlement behavior. Independent review
confirmed the guard is scoped to its execution context. A different thread
that waits for the lock while its parent waits for that thread can still block;
inherited asynchronous contexts may also refuse conservatively. Cross-thread
and cross-process lock ordering, full reconciliation, and missing-table
continuity remain open. DO NOT INTEGRATE or activate a paid provider.
