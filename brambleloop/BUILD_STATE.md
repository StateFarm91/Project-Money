# BUILD_STATE

_Updated 2026-09-17 by the Brambleloop build session. Maintained continuously so any future
session resumes without rediscovery (Execution Directive step 1, Master Plan section 35)._

## Current phase
PHASE 1 — SHADOW MODE (pre-deployment). Nothing is connected to live customers, live
listings or live spend, and nothing is deployed to the cloud yet.

## Canonical specification
`brambleloop/spec/01_Brambleloop_Master_Plan_v1.2.pdf` (vendored copy of the owner's handoff).
Treat v1.2 as canonical. Improvements become v1.3+ with a preserved changelog — do not
scatter canonical strategy across chat.

## Honest status — what actually exists
Verified by running the test suites in this repository:

- CIR engine: **built and passing 27 tests** (9 compiler, 12 reverse compiler/writer, 6 twin).
- Everything else: **not built yet.**
- Cloud deployment: **none.** No Railway project provisioned, nothing runs when this session
  is off. The "persistent 24/7 company OS" does not exist yet.
- Etsy shop, listings, customers, revenue, ad spend: **none, CA$0, zero.**

## Last completed milestone
CIR engine complete: schema, deterministic compiler, writer, reverse compiler, digital twin.

## Architecture decisions
See `DECISION_LOG.md` for reasoning. Summary:
- Python 3.11. Core value is deterministic arithmetic, PDF/chart generation and image work.
- Postgres in production; SQLite for hermetic tests. Durable queue via `SELECT ... FOR UPDATE
  SKIP LOCKED` (Postgres) with a portable fallback — no Redis, fewer moving parts to die
  unattended.
- FastAPI + server-rendered Jinja admin. No separate frontend build step.
- Railway as the deploy target (owner account `statefarm91` verified present, personal
  workspace, 3 existing projects). **Not provisioned** — paid infrastructure is an owner gate.
- Lives at `brambleloop/` inside the Project-Money repo for now, purely because push
  credentials are scoped to that repo. Migrating to a dedicated repo is a tracked follow-up,
  not a blocker.

## Completed capabilities
- `cir/stitches.py` — canonical stitch taxonomy (consumes/produces/height per stitch). US
  canonical, UK rendered downstream.
- `cir/model.py` — CIR dataclasses, JSON round-trip, components/rows/repeats/gauge/materials.
- `cir/compiler.py` — deterministic compiler. Validates per row: stitch availability, over/
  under-run, repeat divisibility, declared-vs-computed count, unknown colour, row ordering,
  empty rows. Warns on missing turning chains for tall stitches.
- `cir/writer.py` — CIR → customer-facing pattern text, US/UK terminology, magic-ring aware.
- `cir/reverse.py` — independent parser of customer-facing text + structural diff against
  canonical CIR. Shares no parsing code with the writer by design.
- `cir/twin.py` — digital twin: cell-level fabric model, chart/colour grids, finished
  dimensions from gauge, per-colour yardage estimate with an explicit ±20% tolerance until a
  physical test calibrates it.

## Acceptance gates passed
- **Gate B (Pattern Safety): substantially passing.** Known-good fixtures compile; broken
  stitch count, bad repeat, overrun, underrun and unknown colour are all rejected; customer
  text mutations (repeat count, stitch substitution, run length, declared count, turning
  chain, dropped row, unparseable text) are all caught by reverse compilation.
  Outstanding for full Gate B: "a corrected bug creates a regression test" needs the incident
  → regression-fixture automation, which depends on the platform layer.
- Gates A, C, D, E, F: **not yet attempted** (depend on the platform layer).

## Integrations connected
- None. Railway account exists but no project is provisioned.

## Owner actions required
- None right now. Do not ask the owner for Etsy/KYC/banking until the system actually reaches
  the integration that needs it (Master Plan section 35). Deferred, in the order they will be
  needed: paid infrastructure approval → brand/trademark clearance for "Brambleloop Studio"
  → Etsy account/KYC → banking.

## Financial state
- Spend: CA$0 (verified — nothing provisioned, nothing purchased)
- Revenue: CA$0
- Customers: 0

## Current blockers
- None blocking. All remaining work in the execution order is unblocked.

## Known refinements (tracked, not urgent)
- Yardage constants are uncalibrated heuristics with a stated tolerance; physical tests
  replace them per yarn/hook. Never present an uncalibrated estimate as precise.
- Reverse compiler handles the writer's grammar plus common variants; widen coverage as real
  pattern styles appear.
- Brand model imagery (Master Plan section 6) raises a disclosure question — AI-generated
  lifestyle imagery of a fictional model wearing an item that has not been physically made
  must not imply a photograph of a real finished object. Asset Truth + Policy Gate own this;
  flagged so it is decided deliberately, not by default.

## Next highest-value unblocked actions
1. Platform layer: DB schema (Master Plan section 15), durable queue with leases/idempotency/
   retry/backoff/dead-letter, scheduler, agent registry with permissions and budget ceilings,
   immutable audit log, cost ledger. Targets Gate A.
2. Release gates: Quality Director, Asset Truth Engine, Policy Gate, Quality Release
   Certificate. Targets Gates C and E.
3. Market Radar seeded from `spec/05_Competitor_and_Market_Seeds.txt`.
4. Shadow-mode orchestration + admin dashboard.
5. Full acceptance suite (Gates A–F), then request only the owner actions actually required.

## Changelog
- 2026-09-17: Initial build. CIR engine complete and tested. Competition project retired.
