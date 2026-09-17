# DECISION_LOG — Brambleloop Studio

Consequential decisions with reasoning, so future sessions do not re-litigate them.

| # | Date | Decision | Why | Reversible? |
|---|---|---|---|---|
| B-001 | 2026-09-17 | Project-Money 90-day competition retired; Brambleloop Studio is the active mission. | Owner directive: "Scrap the competition. Competition is cancelled." Handoff package v1.2 supplied as canonical spec. | Owner's call |
| B-002 | 2026-09-17 | Python 3.11 for the core, not Node/TS. | The differentiating work is deterministic arithmetic, PDF/chart generation and image compositing. Python's reportlab/Pillow are already proven working in this environment. A JS frontend is not needed for an admin dashboard. | Yes, but costly |
| B-003 | 2026-09-17 | Postgres-backed durable queue (`FOR UPDATE SKIP LOCKED`), not Redis/Celery/SQS. | Master Plan section 13 demands durable jobs with leases, retries and idempotency. Postgres already has to exist for the warehouse; adding a second datastore adds a component that can die unattended at 3am with nobody watching. Fewer moving parts is a reliability decision, not a laziness one. | Yes |
| B-004 | 2026-09-17 | SQLite for tests, Postgres for production, behind one abstraction. | Acceptance tests must run hermetically anywhere, including before any cloud account exists. SKIP LOCKED degrades to a transactional claim on SQLite. | Yes |
| B-005 | 2026-09-17 | Writer and reverse compiler share **no** parsing code. | If they shared a grammar, a round-trip test would prove only that the bug is symmetric. Master Plan section 3 requires the reverse compiler to see "only the customer pattern". Independence is the whole point. | No — this is load-bearing |
| B-006 | 2026-09-17 | Digital twin refuses to model a pattern that failed compilation. | A twin built on broken arithmetic is fiction, and every downstream gate (Asset Truth, size claims, yardage) would then be reasoning about an object that cannot exist. | No |
| B-007 | 2026-09-17 | Yardage is an estimate with an explicit ±20% tolerance and a `calibrated` flag. | Yarn consumption genuinely varies by yarn, hook and tension. Inventing a precise number would be the exact "unsupported claim" the Policy Gate exists to block. Physical tests calibrate it (Master Plan section 3). | Yes, as data arrives |
| B-008 | 2026-09-17 | Magic ring modelled as a `foundation_kind`, not a free-text note. | The writer was emitting "sc in next 6 sts" for a magic-ring round — nonsense to a maker. An override string would have created a hole in reverse-compilation verification; a structural field keeps the check intact. | Yes |
| B-009 | 2026-09-17 | Built under `brambleloop/` in the Project-Money repo rather than a new repo. | Push credentials are scoped to `StateFarm91/Project-Money`. Blocking real progress on repo cosmetics would violate the directive's "do not stop because one integration is unavailable; route around it". Migration to a dedicated repo is trivial later and is tracked in BUILD_STATE. | Yes |
| B-010 | 2026-09-17 | Cloud not provisioned yet despite a verified Railway account. | Master Plan section 35 defers paid infrastructure approval until the system reaches the integration that needs it. Provisioning an empty project now would spend the owner's money to host nothing. Deploy when there is a service worth running. | Yes |

## Standing constraints carried from the spec

These are not re-decidable by a future session without the owner:

- Patterns are software releases. Never generate a beauty image and ask a model to guess the
  instructions (section 2).
- No fake reviews, buyers, favourites, sock-puppets, deceptive discounts or artificial
  engagement (Execution Directive, section 8).
- Never bypass CAPTCHA, KYC, identity checks or legal acceptance.
- Never copy competitor instructions, charts, photography or protected designs. Research is
  for demand and merchandising intelligence only.
- Never claim an integration, deployment, pattern, listing, test, campaign, customer or
  revenue exists until verified.
- Deterministic pattern validation wins even if every LLM disagrees (section 27).
