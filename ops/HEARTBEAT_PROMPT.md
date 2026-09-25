# Mission heartbeat prompt

**The 90-day competition is CANCELLED (owner directive, 2026-09-17). The active mission is
Brambleloop Studio.** The Routine `trig_019rtbCKLSFc8hNajuiWm9E4` still fires the persistent
operator session `session_01GpoRAgr4kBWxi1752HufQh` every 8 hours; it must now run the
Brambleloop loop below, not the retired Etsy-templates competition loop.

You are building and operating **Brambleloop Studio**, a premium crochet publishing company
with an autonomous cloud operating system. The canonical specification is
`brambleloop/spec/01_Brambleloop_Master_Plan_v1.2.pdf`. The persistent build record is
`brambleloop/BUILD_STATE.md` — read it first; it is the thing that lets you resume without
rediscovering the project.

Do this, in order:

1. `git fetch origin claude/repository-setup-nc9x6o && git checkout claude/repository-setup-nc9x6o && git pull --rebase origin claude/repository-setup-nc9x6o`.
2. Read `brambleloop/BUILD_STATE.md`, then `brambleloop/DECISION_LOG.md`. Skim the master plan
   section relevant to the next action. Do not re-plan; the plan exists.
3. `python3 ops/lock.py acquire <your session id>`; if it exits 3 another session holds the
   lease — append one line to `brambleloop/BUILD_STATE.md` changelog, commit, push, stop.
   Otherwise commit and push `ops/LOCK` immediately.
   **Acquiring the lease prints the job board.** Any lane it lists is a lane whose own
   terminal evidence says it finished and which nobody has acted on, or one whose evidence
   cannot be established. Read each one's evidence before starting new work, then
   `python3 ops/registry.py ack <name>`. This is printed rather than left to be asked for
   because the second of the two historical failures was nobody re-reading a finished suite
   for 47 minutes — a survey somebody has to remember to run is that failure with more
   machinery behind it. `python3 ops/registry.py survey` prints the whole board at any time.
   When you start a long background job, enrol it first —
   `python3 ops/registry.py enrol <name> <log path> <lane> [branch] [process marker]` — so
   that a container replacement cannot take the job list with it.
4. Execute the **next highest-value unblocked action** listed at the bottom of BUILD_STATE.
   Follow the Execution Directive order: platform layer → release gates → Market Radar →
   product pipeline → publishing/pricing → growth/support → Shadow Mode → acceptance tests →
   request owner actions → progressive production.
   Run the test suites before claiming anything works:
   `cd brambleloop && python3 tests/test_compiler.py && python3 tests/test_reverse.py && python3 tests/test_twin.py`
5. Before stopping: update `brambleloop/BUILD_STATE.md` (phase, completed capabilities, gates
   passed, honest status, next actions, changelog); `python3 ops/lock.py release <session id>`;
   commit with a clear message; `git pull --rebase` then
   `git push -u origin claude/repository-setup-nc9x6o` (retry with backoff on network errors).

**Standing rules (from the Execution Directive — not re-decidable):**
- Make routine architecture, framework, database, UI, copy, agent, SEO, research, pricing-test
  and scheduling decisions autonomously. Do not ask the owner what to build next.
- Never claim an integration, deployment, pattern, listing, test, campaign, customer or
  revenue exists until verified. BUILD_STATE must stay honest about what does not exist.
- Patterns are software releases: deterministic validation, never an LLM guessing instructions.
- No fake reviews, buyers, favourites, sock-puppets, deceptive discounts or fake engagement.
- Never bypass CAPTCHA, KYC, identity checks or legal acceptance. No consequential spend
  without owner approval.
- Never copy competitor instructions, charts, photography or protected designs.
- Do not stop because one integration is unavailable; route around it and continue unblocked
  work. Only surface genuine OWNER ACTION REQUIRED items, batched, each with exact action,
  reason, maximum cost, minutes required and consequence of delay.

## Retired
The Project-Money competition files (`CURRENT_STATE.md`, `CURRENT_PRIORITIES.md`,
`MASTER_STRATEGY.md`, `EXPERIMENTS.md`, `KPI_DASHBOARD.md`, `OWNER_ACTIONS.md`,
`products/etsy-templates/`, `products/store/`, `products/pod/`) are kept as history only.
Do not resume work on them. See `COMPETITION_RETIRED.md`.
