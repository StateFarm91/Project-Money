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
