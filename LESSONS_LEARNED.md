# LESSONS_LEARNED

Reusable evidence from successes and failures. Add an entry whenever an experiment concludes or an assumption is disproven.

## Day 1 — 2026-09-15

### LL-001: The operator's compute is rate-limited; heavy agent fan-out is not affordable
- **What happened.** A 12-researcher opportunity-sweep workflow plus two infrastructure research agents consumed roughly 1M subagent tokens in about one hour and hit the owner's five-hour Claude usage limit at ~11:26 UTC (reset 15:10 UTC). Nine of twelve researchers and the merge step never ran; the session was idle for ~5 hours.
- **Evidence.** Workflow failure notices "You've hit your session limit · resets 3:10pm (UTC)"; session usage at 16:27 UTC: ~3.6M input, ~0.5M output, ~8.2M cache-read tokens.
- **Reusable rule.** Budget subagent work per five-hour window (target well under ~1M tokens per window). Prefer: (a) a few lean agents with capped searches over many exhaustive ones; (b) doing merge/ranking/synthesis inline instead of feeding large JSON into agents; (c) scheduling unattended runs no more than ~2-3 per day so a single firing cannot exhaust the window. Persist partial results early so a rate-limit failure loses nothing (the three completed researchers were recovered from the workflow journal).

