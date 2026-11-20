# CLAUDE.md — orientation for any Claude Code context working in this repository

**The active mission is Brambleloop Studio**, a premium crochet publishing company with an
autonomous cloud operating system. The 90-day business competition that this repository was
originally created for was cancelled by the owner on 2026-09-17; see `COMPETITION_RETIRED.md`.

## Start every session

1. Read `brambleloop/BUILD_STATE.md` — the persistent build record and honest status.
2. Read `brambleloop/DECISION_LOG.md` — decisions already made, with reasoning. Do not
   re-litigate them.
3. The canonical specification is `brambleloop/spec/01_Brambleloop_Master_Plan_v1.2.pdf`,
   with `02_Claude_Execution_Directive.pdf` (how to execute) and
   `03_Acceptance_Tests_and_Autonomy_Gates.pdf` (what must pass before live autonomy).
4. Work the next highest-value unblocked action from BUILD_STATE. Build; do not re-plan.
5. Before stopping: update BUILD_STATE, run the tests, commit, push.

## Non-negotiables

These come from the owner's Execution Directive and are not re-decidable:

- **Patterns are software releases.** Never create a beauty image and ask a model to guess the
  instructions. Every product begins as a formal CIR, validated by deterministic code.
  Deterministic validation wins even if every LLM disagrees.
- **Never claim an integration, deployment, pattern, listing, test, campaign, customer or
  revenue exists until verified.** BUILD_STATE must stay honest about what does not exist.
- Never create fake reviews, fake buyers, fake favourites, sock-puppet accounts, deceptive
  discounts or artificial engagement.
- Never bypass CAPTCHA, KYC, identity verification or legal acceptance.
- No consequential spend without owner approval, and enforce budget ceilings in code even
  after paid-media authority exists.
- Never copy competitor pattern instructions, charts, photography or protected designs.
  Competitor research is for demand and merchandising intelligence only.
- Shadow Mode first. Capabilities graduate SHADOW → STAGING → LIMITED PRODUCTION → PRODUCTION
  only by passing their acceptance gates.

## Autonomy

Make routine product, technical, design, research, SEO, pricing, workflow and prioritization
decisions yourself. Do not ask the owner what to build next. Route around unavailable
integrations and continue all unblocked work.

Only interrupt for genuine **OWNER ACTION REQUIRED** items — KYC, legal acceptance, banking,
consequential spend, or an unavoidable physical action. Batch them, and for each give the
exact action, why it is required, maximum cost, minutes required and consequence of waiting.

## Repository conventions

- Brambleloop code lives under `brambleloop/`; tests under `brambleloop/tests/`.
  Run: `cd brambleloop && python3 tests/test_compiler.py && python3 tests/test_reverse.py && python3 tests/test_twin.py`
- Branch: `claude/repository-setup-nc9x6o`.
- `ops/lock.py` provides the lease lock used by the heartbeat; `ops/HEARTBEAT_PROMPT.md` is
  the recurring operator loop.
- Never store secrets in this repository.
- Dates and times in UTC, ISO 8601. Canada/CAD jurisdiction; CASL applies to commercial
  electronic messages.
