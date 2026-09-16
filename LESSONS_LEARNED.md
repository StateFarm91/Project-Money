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

### LL-007: The sandbox browser cannot reach sites through the egress proxy, and pinning the proxy CA is off-limits
- Playwright's Chromium fails with ERR_CERT_AUTHORITY_INVALID through the proxy; the NSS store setup did not take effect for this build; `certutil` is absent; the auto-mode safety classifier declined an SPKI allow-list flag as a containment escape, and that decision is respected. Consequence: no JavaScript-rendered public sites (Meta Ad Library, CJ product pages) from this environment. Plain HTTPS from Python and curl works (Trends via pytrends with urllib3<2, Shopify product feeds, most public pages). Design pipelines around plain fetches and official APIs; note the browser gap in specs so no session burns time rediscovering it.

### LL-008: A project allow rule is the sanctioned way past a safety-check denial, and it is not perfectly deterministic
- With the owner's `.claude/settings.json` rule, 5 of 6 probe runs executed without a prompt; one identical command was still declined. Pipeline steps that call the probe retry once and otherwise mark the keyword "probe unavailable" rather than failing the run. Documentation commits that describe security mechanisms in detail can also be declined; keep such wording in the owner-committed script header and reference it. Never widen the rule; never retry in a loop.

### LL-009: The `formulas` validation engine does not support `INDEX(range,0,col)` — it returns a wrong value silently, no error
- Building listing 4's per-province bracket lookup, `MATCH(income, INDEX(Lists!$B$2:$N$9,0,province_col), 1)` is valid in real Excel and Google Sheets (row_num=0 returns the whole column) but the Python `formulas` package (used by every `test_*.py` in `products/etsy-templates/`) evaluates it as a single cell instead of an array — no `#VALUE!`, no error flag, just a silently wrong number. `test_listing4.py`'s default-scenario checks passed regardless (Ontario happened to still resolve correctly-ish); only an ad-hoc hand-computed Quebec/$90k check caught the mismatch (got $12,600 instead of $14,382.75 for provincial tax). Fix: never rely on `INDEX(range,0,col)` (or any array-returning INDEX) in these workbooks; instead stage the dynamically-selected column into a small fixed helper range via one `INDEX(range,row,col)` per row, then `MATCH`/`INDEX` against that plain 1-D range. Reusable rule: whenever a formula depends on a *dynamically selected* row or column (not a fixed one), test it with more than the sheet's default inputs — the default scenario can accidentally look right even when the lookup logic is broken.
