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
Verified by `./run_tests.sh` — **76 tests passing, 0 failing**:

- CIR engine (27), platform layer (14), release gates (27), shadow pipeline (8).
- The full release chain runs end to end with no human in the loop, and correctly *refuses*
  to publish in shadow mode.
- Cloud deployment: **none.** No Railway project is provisioned. Nothing runs when this
  session is off. The "persistent 24/7 company OS" is built but **not yet hosted** — this is
  the single biggest gap between the spec and reality.
- Etsy shop, listings, customers, revenue, ad spend: **none, CA$0, zero.**
- Market Radar emits *seeded placeholder* concepts, not real market data. No competitor
  scraping or trend integration exists yet.

## Last completed milestone
Shadow-mode pipeline: a product travels market brief -> opportunity score -> CIR -> compile ->
certify -> listing draft -> refused publish, autonomously, with a full audit trail.

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
- `core/db.py`, `core/models.py` — warehouse: jobs, agents, audit log, cost entries, ledger,
  spend limits, products, pattern versions, incidents, owner-action queue.
- `queue/durable.py` — leased jobs, idempotency keys, backoff with jitter, dead-letter.
- `agents/registry.py` — per-agent job-type permissions, daily cost ceilings, structurally
  forbidden combinations, audit trail, and a SpendGuard that pauses a scope on breach.
- `core/backup.py` — backup plus a restore drill that reloads and compares row counts.
- `gates/asset_truth.py` — imagery/claims checked against the digital twin.
- `gates/policy.py` — unsupported claims, IP tripwires, deceptive pricing, Etsy limits.
- `gates/certificate.py` — the full release chain and an immutable release hash.
- `gates/incidents.py` — defect correlation, P1 escalation, publication halt.
- `runtime/worker.py` — worker loop (authorize → dispatch → complete/fail) and scheduler.
- `runtime/pipeline.py` — the shadow release pipeline and its job handlers.
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
- **Gate A (Infrastructure): passing.** Worker death does not strand jobs (lease reclaim);
  duplicate publish/spend refused by DB-enforced idempotency keys; backoff then dead-letter;
  backup + restore drill comparing row counts; audit log identifies actor/action/artifact.
- **Gate B (Pattern Safety): passing except regression automation.** Known-good compiles;
  broken stitch count, bad repeat, overrun, underrun, unknown colour rejected; text mutations
  (repeat count, stitch substitution, run length, declared count, turning chain, dropped row,
  unparseable text) caught by reverse compilation. Outstanding: "a corrected bug creates a
  regression test" — the incident → regression-fixture automation is not built.
- **Gate C (Asset Truth): passing.** Absent motif/colour/component rejected; unsupported
  size, size-label, material and difficulty claims blocked; provenance mandatory; a render
  cannot masquerade as a photograph; an undisclosed AI concept cannot be the hero.
- **Gate D (Commercial Safety): passing.** Agent permissions and structural prohibitions;
  per-agent daily cost ceilings; ad budget breach prevented *and* the scope auto-paused.
  Outstanding: contribution accounting reconciles against real transactions (no real ones yet).
- **Gate E (Customer Experience): passing.** Repeated defects correlate into one incident;
  P1 halts the publication chain; support has no path to the canonical pattern.
  Outstanding: answering from the correct pattern version needs the support agent.
- **Gate F (Shadow Graduation): passing.** Full simulated product completes the chain without
  intervention. Model-provider failover is untested (no Model Gateway yet).

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
1. **Deploy.** Build the FastAPI admin/API surface and a container, then provision Railway
   (Postgres + worker + cron). This is what turns the OS from "runs when invoked" into "runs
   when everyone is asleep". Paid infrastructure approval is the first real owner gate.
2. Model Gateway (section 27): provider-agnostic routing, failover, pinned prompt versions,
   cost logging, eval fixtures. Needed before any LLM call enters the pipeline.
3. Real Market Radar: replace seeded placeholder concepts with actual demand signals from
   `spec/05_Competitor_and_Market_Seeds.txt`. Research only — never copy protected expression.
4. PDF/chart generation from the twin (reportlab/Pillow are installed and proven).
5. Incident → regression-fixture automation to close Gate B.
6. Brand/trademark clearance screening for "Brambleloop Studio" before any commercial launch.

## Changelog
- 2026-09-17: Initial build. Competition retired. CIR engine complete (27 tests).
- 2026-09-17: Platform layer — durable queue, agent governance, audit, spend caps, backup
  drill (14 tests). Gate D test caught a real bug: the spend guard raised inside its session,
  so the rollback discarded the `paused` flag and a breach would have refused one spend then
  accepted the next. Fixed: the pause commits before the raise.
- 2026-09-17: Release gates — asset truth, policy, certificate, incidents (27 tests).
- 2026-09-17: Shadow pipeline + worker/scheduler (8 tests). Two ordering bugs found and fixed:
  permission was checked *after* handler lookup (so an agent reaching for forbidden work that
  had no handler was recorded as "no handler" instead of denied), and a shadow-mode refusal
  was being retried with backoff against a mode that cannot change between attempts.
- Totals: 76 tests passing, 0 failing. Gates A, C, D, E, F passing; B passing except
  regression automation.
