# AUTOMATIONS

What runs unattended, how, its dependencies, and how it fails safely. Never fabricate successful external execution: if a run did not happen or failed, the log says so.

## Running

| Name | Trigger | What it does | Dependencies | Failure mode | Status |
|---|---|---|---|---|---|
| _none yet_ | | | | | |

## Planned: mission heartbeat (design, to be created at the end of the Day-1 session)

**Purpose.** The directive requires deterministic recurring work without an active conversation (sections 21, 22, 31). The environment offers Claude Code Routines: a cron-scheduled trigger that opens a fresh Claude Code session in this environment with a standalone prompt.

**Design.**
- Trigger: Routine `project-money-heartbeat`, cron in UTC, fresh session per firing (`create_new_session_on_fire`), initially every 8 hours (3 sessions/day). Cadence is a tunable; it is raised when a product is live and customers need faster turnaround, and lowered if runs are idle.
- Prompt (standalone, since each session starts from nothing): identify as the operator; run `python3 ops/day.py`; read `CLAUDE.md`, `CURRENT_STATE.md`, `CURRENT_PRIORITIES.md`, `OWNER_ACTIONS.md`; pull the working branch; take the `ops/LOCK` lease; execute the highest-value actions for up to the session's budget; update state files, ledger (actual events only), dashboard, daily log; commit and push; release the lease.
- Concurrency safety: a session writes `ops/LOCK` (session id + UTC timestamp) and pushes it before doing work; a new session that finds a lock younger than 3 hours exits without editing. Stale locks (>3 h) are overridden and noted in `DAILY_LOG.md`. Pushes use `git pull --rebase` first; on conflict, the session resolves in favour of the newer ledger rows and re-pushes.
- Idempotency: external actions (creating listings, sending emails, posting) are recorded in `ops/actions.log` with an idempotency key before execution; a rerun checks the log first.
- Owner control: the Routine is visible in the owner's Routines list and can be paused or deleted there at any time. It consumes the owner's Claude usage; the cadence is chosen to keep that modest.
- Failure handling: a failed firing shows as `last_run.status != SUCCEEDED` in the Routines list; the next firing reads `DAILY_LOG.md` and continues. No firing may spend money or take an owner-only action.
- Monitoring: each session appends one line to `DAILY_LOG.md` even when nothing changed ("heartbeat: no actionable work; waiting on OWNER_ACTIONS #n").

**Dependencies.** Claude Code Routines in environment `env_011Rqnj5AepURDBdtY9dZ92j`; GitHub push access to `StateFarm91/Project-Money` branch `claude/repository-setup-nc9x6o`.
