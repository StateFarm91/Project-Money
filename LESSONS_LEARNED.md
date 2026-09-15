# LESSONS_LEARNED

Reusable evidence from successes and failures. Add an entry whenever an experiment concludes or an assumption is disproven.

## Day 1 — 2026-09-15

### LL-001: The operator's compute is rate-limited; heavy agent fan-out is not affordable
- **What happened.** A 12-researcher opportunity-sweep workflow plus two infrastructure research agents consumed roughly 1M subagent tokens in about one hour and hit the owner's five-hour Claude usage limit at ~11:26 UTC (reset 15:10 UTC). Nine of twelve researchers and the merge step never ran; the session was idle for ~5 hours.
- **Evidence.** Workflow failure notices "You've hit your session limit · resets 3:10pm (UTC)"; session usage at 16:27 UTC: ~3.6M input, ~0.5M output, ~8.2M cache-read tokens.
- **Reusable rule.** Budget subagent work per five-hour window (target well under ~1M tokens per window). Prefer: (a) a few lean agents with capped searches over many exhaustive ones; (b) doing merge/ranking/synthesis inline instead of feeding large JSON into agents; (c) scheduling unattended runs no more than ~2-3 per day so a single firing cannot exhaust the window. Persist partial results early so a rate-limit failure loses nothing (the three completed researchers were recovered from the workflow journal).

### LL-002: Validate spreadsheets with the `formulas` engine, not LibreOffice, in this sandbox
- LibreOffice here is `libreoffice-core` only (no Calc): `soffice --convert-to` fails with "source file could not be loaded" even on a trivial .xlsx. The Python `formulas` package evaluates the whole workbook (6,122 cells in ~19 s) and catches errors; `products/etsy-templates/test_workbook.py` is the pattern. Keep formulas to functions that behave identically in Excel and Google Sheets.

### LL-003: Check brand names against existing businesses before writing them into owner instructions
- "MapleLedger" and "NorthLedger" both matched multiple existing Canadian bookkeeping firms; a shop with that name would invite confusion complaints. One web search per candidate name before use. "MapleSheets" and "LoonieBooks" were clean on 2026-09-15.

### LL-004: Run the adversarial review before building, not after
- The Day-1 skeptic reversed the second track (AODA scanner) by checking one legal fact the deep-dive had glossed (the 20-49 employee filing needs no website check) and by pricing the ads test realistically. Cost: ~90k tokens. It saved a 10-day build. Every new track gets a skeptic pass at the pre-test stage.

### LL-005: Channels the operator can run alone are the ranking criterion that matters most
- Community posting, social accounts and outreach all need the owner (and CASL forbids cold contact). Rank opportunities first by whether their first-10 channel is a marketplace with native search and a publishing API, the operator's own domain, or in-marketplace ads; discount "post in r/..." plans heavily.

### LL-006: Routines that spawn fresh sessions have no repository attached
- Test firing of the first heartbeat Routine (fresh session per firing) completed "SUCCEEDED" but pushed nothing: the fired session's config carried `sources: []`, so it had no repo checkout or push credential. Fix: create a persistent session with `source_url` + `outcome_branch` and point the Routine at it (`persistent_session_id`). Verify any automation by a test firing whose expected side effect is a commit you can see.
