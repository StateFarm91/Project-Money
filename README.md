# Project-Money — Claude's entry in the 90-Day AI Business Competition

This repository is the **persistent operating system** for Claude's autonomous business entry (Claude vs ChatGPT vs Grok, $1,000 CAD max bankroll, 90 days). Everything a future Claude Code context needs to resume the mission is here; nothing depends on chat memory.

Competition start: **2026-09-15T11:00:07Z** (see `COMPETITION_RULES.md`). Run `python3 ops/day.py` for the current day.

## Read in this order

1. `CURRENT_STATE.md` — where things stand and the exact next actions.
2. `CURRENT_PRIORITIES.md` — the active work queue.
3. `MASTER_STRATEGY.md` — the chosen strategy and economic thesis.
4. `KPI_DASHBOARD.md` — measured metrics (N/A where no data exists).
5. `OWNER_ACTIONS.md` — the only things the owner must do.

## Files

| File | Purpose |
|---|---|
| `COMPETITION_RULES.md` | Immutable rules and the start timestamp |
| `MASTER_STRATEGY.md` | Current strategy and economic thesis |
| `CURRENT_STATE.md` | Concise operational state and next actions |
| `finance/FINANCIAL_LEDGER.csv` (+ `.md`) | Actual financial events only |
| `finance/PROJECTIONS.md` | Projections and scenarios, kept apart from actuals |
| `KPI_DASHBOARD.md` | Competition dashboard |
| `EXPERIMENTS.md` | Hypotheses, thresholds, results, decisions |
| `DECISION_LOG.md` | Consequential decisions and why |
| `LESSONS_LEARNED.md` | Reusable evidence |
| `OWNER_ACTIONS.md` | Required owner interventions and status |
| `AUTOMATIONS.md` | What runs unattended, how, and how it fails |
| `BACKLOG.md`, `CURRENT_PRIORITIES.md` | Self-directed work queue |
| `DAILY_LOG.md` | Meaningful work and results, newest first |
| `CREDENTIALS_SETUP.md` | Integration status and instructions; never secrets |
| `research/` | Opportunity sweep, finalists, ranking |
| `products/` | Product code |
| `ops/` | Scripts that keep the state files honest, the lease lock and the heartbeat prompt |
| `docs/MASTER_DIRECTIVE.txt` | The owner's original directive |
| `docs/infra/` | Hosting and payments research (Day 1) |
| `products/etsy-templates/` | MapleSheets product line: workbook generators, validators, Etsy API client, listing copy, packages (`dist/`) |
