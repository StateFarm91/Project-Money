# The 90-day competition is retired

**Date:** 2026-09-17 (competition Day 2 of 90)
**Reason:** Owner directive — "Scrap the competition. Competition is cancelled. Forget about
that stuff. We have a new plan you're gonna build."

The active mission is now **Brambleloop Studio** (`brambleloop/`). Start at
`brambleloop/BUILD_STATE.md`.

## What the competition produced before it was cancelled

Kept as history, not as work in progress. Nothing here was ever published and no money was
ever spent or earned: CA$0 spend, CA$0 revenue, 0 customers, 0 live listings.

- `products/etsy-templates/` — five Canadian tax/bookkeeping spreadsheet listings, built and
  formula-validated (T2125 bookkeeping system, GST/HST quick-method calculator, home-office
  and vehicle tracker, instalment planner, bundle). The Etsy shop was never opened, so none
  were published.
- `products/pod/` — Printify API client and three personalized Canadian-gift designs.
- `products/store/` — research and spec for a paid-social dropshipping store; never built.
- `research/` — a 42-candidate opportunity sweep, finalist deep-dives and an adversarial
  review that selected the Etsy templates strategy (D-005).
- `ops/` — day counter, lease lock, ledger and status tooling. `ops/lock.py` is still used by
  the Brambleloop heartbeat; the rest is historical.

## Lessons worth carrying forward

`LESSONS_LEARNED.md` holds ten entries. Three generalize beyond the competition and are worth
reading before writing Brambleloop code:

- **LL-002** — validate spreadsheets/artifacts with a real engine, not by eyeballing them.
- **LL-009** — a validation tool can be silently wrong; a test that only exercises default
  inputs can pass while the logic underneath is broken.
- **LL-010** — anything rendering variable-length content must be tested with deliberately
  long and short inputs; the happy path is exactly where that bug hides.

All three are the same lesson in different clothes, and it is the lesson Brambleloop's whole
CIR/reverse-compiler architecture is built around: verify with independent machinery, not with
the thing that produced the output.
