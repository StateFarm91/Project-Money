# W4-CCUX: Command Center mobile improvements (base 0417f35, branch `claude/w4-CCUX`)

This is an improvement to the existing 390 px experience. It is not a redesign: there are no new
colours or brand changes, and Laura's view and ask flow are untouched (`laura.js` is not
modified). All features and evidence links are still in the DOM and reachable.

## Changes

| # | Problem at 0417f35 | Change | Files |
|---|---|---|---|
| 1 | **`/cc` → `/cc/` went through `http://`.** Starlette's trailing-slash redirect builds an absolute URL from the scheme the app sees. Behind Railway's TLS edge that scheme is `http`, so the redirect was `307 Location: http://<host>/cc/`, even when `X-Forwarded-Proto: https` was sent (probe at 0417f35). | An explicit `GET/HEAD /cc` route returns `308 Location: /cc/` (query kept, `Cache-Control: no-store`). The browser resolves a relative Location against the URL it actually requested, so the scheme and host always match what the trusted edge served. No Host or `X-Forwarded-*` value is read, so a client can't steer it, and the path is fixed, so it can't become an open redirect. Other methods get 405 and are never bounced to http. | `app/command_center/__init__.py` |
| 2 | **Decisions were not prioritised.** Approvals showed the long batch queue first. Cards came in arrival order, and Home only had a count. | **"Decide first"** comes first on Approvals and directly after the brief on Home. It shows the top 3 open decisions, each with max cost (Unknown when not stated, never CA$0.00), what happens if you do nothing, the deadline, and minutes/batch for queue items. Each title is a tap target of at least 44 px that opens the card with its evidence (or scrolls to the batch). The rest are counted ("1 more below" / "See every decision"). The ranking is deterministic and explained on the card: decidable with evidence (soonest deadline first) → missing evidence → batch queue in its own order → not executable here. The full approval cards follow in the same order, with the most urgent one open, then the batch queue. | `views/_decisions.js` (new), `views/approvals.js`, `views/home.js` |
| 3 | **Long pages** (Home 4.2k px, Company 6.4k px, Learn 4.1k px at 390 px). | Pages with 5 or more titled cards get an **"On this page · N sections"** index (tap to open and scroll to a section) and **Collapse all / Expand all**. A folded card keeps its title and status pill and gets a "Show" button. Folding hides content but never removes it. The fold choice is kept in memory for the page session only, with no browser storage. Collapsed heights: Home 5024→2561, Approvals 4188→1240, Learn 4242→1766, Company 6484→3321 px. | `js/sections.js` (new), `app.js`, `css/app.css` |
| 4 | **Phone navigation.** Sections under More gave no sign of where you were and no route back. More items were bare labels. The More menu's notification badge stayed blank because it was rendered after the chrome refresh. | A **"‹ More › Section"** breadcrumb on every More-routed page (hidden at ≥900 px, where the sidebar shows). A one-line **hint** under each More item. Badge counts are cached, so badges drawn later (the More menu) match the tab bar. | `app.js`, `routes.js`, `views/more.js`, `css/app.css` |
| — | The service worker shell must list every asset. | Added `js/sections.js` and `js/views/_decisions.js`, and bumped to `cc-shell-v11`. | `sw.js` |

## Regression tests

- `tests/fixtures/cc_mock/check.mjs` keeps all existing checks (no existing assertion was
  edited). It adds 35 `ccux …` browser checks at 390 px: Decide-first order and content,
  cost Unknown and never CA$0, a stated 0 stays CA$0.00, an in-page ranking unit check, link
  to evidence, "Show in batches" scroll, home placement, 44 px tap targets, index coverage,
  collapse/expand/Show, no links lost when folded, no horizontal scroll and tap floor while
  folded, approvals evidence and actions kept when folded, no fold state in localStorage, short
  pages have no toolbar, More hints and badge parity, breadcrumb there-and-back, no
  breadcrumb on primary tabs, and desktop sidebar with no breadcrumb. The mock approvals now
  carry a live `decision_batches` envelope; the existing two cards are unchanged. Result:
  **158 passed, 0 failed**. The screenshot cap went from 12 to 14 so the two new evidence
  shots fit.
- `tests/test_w4_ccux.py` (new, 8 tests): relative 308 under a plain-http app, with and
  without `X-Forwarded-Proto`; query kept; hostile Host / X-Forwarded-Host ignored; HEAD;
  POST gets 405 with no Location; the https client lands on https `/cc/` with the CC CSP;
  `/cc/` and the API gate are unchanged; the new modules are in the SW shell and use no
  storage or innerHTML; the wiring is pinned.
- Re-run, one at a time with a private TMPDIR: `test_v11_pwa_static` (81/0),
  `test_w4_cc_company` (23/23), `test_w4_ccgap_live` (6/6), `test_w4_ccgap_views` (10/10),
  `test_w4_ccpacket` (5/5), `test_v11_wiring_cc` (0 failing), `test_route_auth_default_deny` (7/7),
  `test_customer_data_auth` (9/9), `test_web_security` (11/11), `test_v11_cc_auth` (16/16),
  `test_w4_ccux` (8/8). Browser check flake note: `notifications: deep link` failed 2 of 6
  runs until the new block ended on a settled page (#/ask); then 0 of 8.

## Screenshots (390×844, mock API, full page)

The before shots are from 0417f35 and the after shots are from this branch. In full-page
captures the fixed tab bar appears mid-image.

| Page | Before | After |
|---|---|---|
| Home | `ccux_screens/before/home_390_full.png` | `ccux_screens/after/home_390_full.png`, `…/home_390_collapsed_full.png` |
| Approvals | `ccux_screens/before/approvals_390_full.png` | `ccux_screens/after/approvals_390_full.png`, `…/approvals_390_top.png`, `…/approvals_390_collapsed_full.png` |
| Autonomy & Learn | `ccux_screens/before/learn_390_full.png` | `ccux_screens/after/learn_390_full.png`, `…/learn_390_collapsed_full.png` |
| Company | `ccux_screens/before/company_390_full.png` | `ccux_screens/after/company_390_full.png`, `…/company_390_collapsed_full.png` |
| More | `ccux_screens/before/more_390_full.png` | `ccux_screens/after/more_390_full.png` |

Each page also has a viewport-only `*_390_top.png`. The before Approvals shot has no batch
queue because the 0417f35 mock had none.

## Not done / notes

- Cards start expanded. Default-folding long pages would hide content that existing checks
  read as visible, so folding is the owner's choice and is kept for the session.
- Production still serves 0417f35. None of this is deployed. There were no Railway or Etsy
  writes and no spend.
