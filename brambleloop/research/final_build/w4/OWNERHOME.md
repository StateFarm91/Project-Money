# W4-OWNERHOME — Command Center Home as a phone-first owner overview

Branch `claude/w4-OWNERHOME` from `origin/claude/w4-INTEG2` 61ddc18. Same view, same identity and brand;
no redesign. Not deployed. `store.js` and `laura.js` untouched.

## What the owner now sees on Home (390 px)

1. **Hero** (unchanged): revenue / profit / decisions / incidents / products / jobs, UNKNOWN where unknown.
2. **Decisions for you** (block 3) — the existing *Decide first* card: the ranked owner queue
   (`_decisions.rankDecisions`, the same ranking as Approvals), top 3 with max cost, consequence of doing
   nothing and deadline, plus a folded "Next decisions, ranked #4–#5" with cost and consequence.
   It stays directly after the hero because the existing browser contract
   (`ccux home: Decide first directly after the brief`, 3 tap targets) pins that, and those
   assertions were not edited.
3. **What's working** — executor capability gates that are open, checked live when the page is read
   (`build2.executor.gate_states`), plus the last production self-check (`verify.completed` audit row) with
   its time and failing checks.
4. **What's blocked** — root causes with counts. Leads with the finish-line board's root causes
   (W4-BOARD `company.finish_line`, rows of Build 2 + Final Master each cause holds, with the board's
   generated time), then the live closed gates ranked by requirements waiting, plus department blockers.
   Two units, two ranked lists, never interleaved. If the board is unreadable the block says so and the
   gates still answer.
5. **What the company accomplished (24 h)** — finished jobs that did useful work by the system's one
   useful-work judge (`autonomy.kpis.did_no_work`), grouped by kind with the latest result text and source
   job; jobs that did no work are counted, never shown as accomplishments.
6. **Ready to sell** — per product: certified release, pattern PDF (`artefact_provenance` class `pdf`),
   listing images (publication gate `listing_set` verdict, else `visual_truth` provenance, else UNKNOWN),
   publication verdict (`ops.publication_authority` via the existing publication cards), on Etsy. Summary
   only; the Store tab (CATALOG/STOREFRONT lanes) keeps the catalogue.
7. **Money and agent activity** — revenue, profit, recorded spend (all time) from `tabs.money_section`
   exactly as Money reads them (UNMEASURED/UNKNOWN stay words, never CA$0.00), recorded spend in the last
   24 h, and per-agent useful results vs no-work runs in 24 h.

Each block: status pill, one-line headline, at most 5 rows, freshness + "Open" link, and a folded
**Evidence (n)** list (≤30 rows, each with time and source row). Everything Home showed before (changes since
last view + Mark seen, overnight handoff, every section) is kept inside one folded "More on Home".

## Honesty rules
- Each block is read independently; an unreadable source makes **that block** UNKNOWN with the reason
  (tested by breaking provenance reads), never the page.
- No value is invented: missing PDF/images are `UNKNOWN` with why; revenue `None` + state; decisions count
  `Unknown` when the queue is unreadable.
- Recorded spend 24 h is labelled *recorded* (this system's own rows), not an invoice.

## Files
- `src/brambleloop/app/command_center/overview.py` (new), wired in `tabs.home` as section `overview`
  (reuses the queue, money, products and autonomy reads already made there).
- `static/js/views/_overview.js` (new), `views/home.js`, `css/app.css`, `sw.js` (shell + version v12).
- Tests: `tests/test_w4_ownerhome.py` (9); browser mock `tests/fixtures/cc_mock/check.mjs` +11 `ownerhome:`
  checks at 390×844 (six blocks in order, ≤5 rows, evidence folded and complete, root causes ranked,
  UNKNOWN money, PDF/image status, ranks 4–5 reachable without extra tap targets, no horizontal scroll with
  evidence open, ≥44 px toggles); fixture `data.mjs` gains an `overview`.
- Screenshots: `research/final_build/w4/ownerhome_screens/` (mock data, labelled as fixture).

## Real-data smoke (fresh seeded DB)
working UNKNOWN "nothing is verified yet"; blocked "31 closed gate(s) hold 94 requirement(s)"; decisions
"11 decision(s) open"; accomplished "No job finished in the last 24 h"; ready UNKNOWN "no product recorded";
money UNKNOWN "Revenue UNMEASURED; spend 24 h CA$0.00 (recorded, 0 row(s))". Home read time ≈3.9 s locally.

## Not done / follow-ups
- Production numbers not observed (not deployed). After deploy, read `/api/cc/home` → `sections.overview`.
- "Last verified" for gates is the live check time; per-probe timestamps (model.probe / etsy.probe) could be
  added from their audit rows.

## Merge with INTEG2 9261028
Merged (merge commit). `home.js`: the W4-ONDEMAND "Run checks now" card stays on Home as its own block
directly after the six blocks (not folded). `sw.js`: shell lists both `_overview.js` and `_checks.js`;
cache version bumped to `cc-shell-v13` (past both lanes' v12).
