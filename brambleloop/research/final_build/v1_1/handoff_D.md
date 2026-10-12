# v1.1 lane D handoff: mobile-first Owner Command Center (PWA frontend)

Branch `claude/v11-D` (base `claude/visual-investigation` @ 0694fb7). Frontend only. I edited no
Python backend file. Built against lane C's contract `COMMAND_CENTER_API.md` and checked against
lane C's committed implementation (`claude/v11-C` @ 30bcab6).

## What exists

`src/brambleloop/app/command_center/static/` is about 150 KB. It has no build step, no npm
dependencies, no CDN and no web fonts. It uses vanilla ES modules and CSS.

- `index.html`: the shell. It has no inline script, style attribute or event handler. It sets the
  manifest, icons and theme-color.
- `js/app.js`: the shell logic. It covers owner sign-in (passphrase, plus TOTP when the server
  asks for it, plus a device label), the hash router, the phone bottom tab bar (Home, Approvals,
  Money, Store, More) and a desktop side nav at ≥900px. It also runs the badges, the phase pill,
  the online/offline indicator, the theme and SW registration.
- `js/api.js`: the typed client. Every path and header is listed in one place. Every POST sends
  `X-CSRF-Token`, a fresh `X-CC-Nonce` and `X-CC-Timestamp` (corrected for server skew). When
  the server answers `STEP_UP_REQUIRED`, the client asks for re-auth and retries once with a NEW
  nonce. Responses are cached only in memory, per tab, and only to show a stale view labelled as
  stale.
- `js/dom.js`: an `h()` helper. All text goes in through `textContent` or Text nodes, and
  href/src go through `safeUrl`. There is no innerHTML anywhere.
- `js/format.js`: the money rules. UNKNOWN, UNMEASURED or `value_cad: null` → **"Unknown"**, never
  CA$0.00. Basis labels are Actual / Estimated / Modelled / Recorded / Forecast.
- `js/components.js`: cards, pills, money/stat tiles, generic envelope renderer, source lists,
  an accessible `<dialog>` confirmation with step-up fields, and `guardedAction`.
- `js/views/*.js`: one module per view: home, approvals, money (+drill), store, operations, learn,
  insights, notifications, timeline, ask, account, emergency, more, drill.
- `sw.js`: the service worker. It caches only the listed shell and never intercepts `/api/`,
  non-GET or cross-origin requests. It fetches network-first and falls back to the cached shell
  when offline.
- `manifest.webmanifest` and `icons/`: the manifest has scope `./` (= `/cc/`), a 192/512 PNG icon,
  a maskable icon and shortcuts.

## Requirements

| ID | Status | Notes |
|---|---|---|
| F-882 | COMPLETE (UI) | All tabs are usable at 390px and 360px-safe; 16px gutters; tap targets ≥44px; dark and light themes. |
| F-883 | COMPLETE | Installable manifest plus SW. Offline: the shell loads from cache and says "Offline". A view this tab already loaded shows a STALE banner with its timestamp, and actions are disabled. `/api` is never stored. |
| F-884 | COMPLETE (UI) | Home brief: hero tiles for revenue/profit (Unknown-safe), decisions, incidents, products and jobs; "since you last looked" with a Mark-seen button; then sections. |
| F-885 | COMPLETE (UI) | Each card shows proposal, recommendation, uncertainty, benefit, downside, max spend, reversibility, deadline, consequence and evidence. A missing field shows "Not provided". With no evidence, Approve is disabled. |
| F-886 / F-887 (client side) | COMPLETE (UI) | One-tap actions go through a confirmation dialog. `requires_step_up` asks for the passphrase in that dialog, then calls step-up, then the action. Approvals require a reason. Preview needs no confirmation because it is read-only. |
| F-888 | COMPLETE (UI) | Account shows owner, devices (revoke one or revoke others), refused attempts, connected services and scopes, providers, budgets, authorities, notification policy, theme and sign-out. |
| F-889 | COMPLETE (UI) | Emergency: pause publishing, spend, company or a department after confirmation, with no step-up. Resume requires step-up and a reason. Kill switch returns the company to shadow and requires a reason. Never-paused functions are listed. |
| F-896 | COMPLETE (UI) | Overnight handoff card on Home (`/brief/morning`) with money spent. |
| F-897 | COMPLETE (UI) | Notifications sorted by severity. Each has a deep link, an acknowledge button, a suppressed count, a re-check button and a quiet-hours/min-severity/digest policy form. The More tab carries the badge. |
| F-899 / F-915 | COMPLETE (UI) | Every source ref links to `#/drill/<table:id>`. Job, incident, audit and agent refs go to `operations/drill`; other refs show the exact provenance string honestly. Money tiles go to `money/drill?metric=`. |
| F-914 | COMPLETE (UI) | Shows the revenue/profit/recorded-spend headline, a source-health warning, the accounting (lane E) envelope as tiles, spend limits and a legend. **Period controls send `?period=`, but lane C currently ignores it. The UI says so ("server did not confirm this period filter").** |
| F-926 | PARTIAL | The Store tab links out to the same-origin `preview_url`/`preview_path` reported by lane F. It is not embedded, because the edge sends `frame-ancestors 'none'`/XFO DENY. Lane F's provider does not report a URL yet, so the UI says the preview is not available. |
| F-927 | COMPLETE (UI) | Timeline is newest first, with a "show more" control and source links. It warns when the autonomy timeline (lane A) is UNKNOWN. |
| F-928 | COMPLETE (UI) | Ask Company has suggested questions, answer status, facts with source links and as_of, next action and method. An UNKNOWN answer is labelled as such. |

## Tests

- `tests/test_v11_pwa_static.py` is pure Python: **78 OK, 0 FAIL**. It checks:
  - manifest validity and real PNG sizes;
  - no inline script, handler or style;
  - no innerHTML/outerHTML/insertAdjacentHTML/document.write/eval/string-timer;
  - no external URL, @import or @font-face;
  - the SW returns early on `/api/` before `respondWith`, `cache.put` only for shell paths, and the shell list is complete;
  - the CSRF, nonce and timestamp headers and the step-up retry;
  - the only persisted storage is the theme key;
  - all imports resolve and no mock is shipped;
  - no `value ?? 0` coercion.

  I mutation-tested it: adding innerHTML, a Google Fonts import, removing the SW `/api` guard, or
  adding `amount ?? 0` each produces a FAIL.
- `tests/test_v11_pwa_browser.py` runs `tests/fixtures/cc_mock/check.mjs` with Node + Playwright
  Chromium at 390×844 against `tests/fixtures/cc_mock/server.mjs`. The mock enforces the
  contract's CSRF, nonce, timestamp and step-up rules and serves the static dir under the
  contract CSP. Result: **93 OK, 0 FAIL**. Per tab, for all 13 routes, it checks no console
  errors (CSP violations included), no horizontal scroll and the tap-size floor. It also checks:
  - Unknown money renders "Unknown" and a measured zero renders CA$0.00 labelled Actual;
  - Estimated, Modelled and Recorded labels appear;
  - drill-through rows appear;
  - all F-885 fields and evidence appear;
  - nothing is sent before confirmation, and cancel sends nothing;
  - step-up happens before the action, the headers are present and the nonce is unique;
  - pause needs no step-up;
  - Ask has source links and returns UNKNOWN when it should;
  - the notification deep link works;
  - the SW cache holds no `/api`;
  - offline shows the stale banner, and an offline reload shows no figures;
  - dark theme renders.

  If Node or Playwright is missing, the wrapper prints `SKIP` with no OK line, so the harness flags it.

  Fixture deviation: in the mock, login does not count as step-up, so the step-up prompt actually gets exercised.

## Runtime proof against the real backend

I ran lane C @ 30bcab6 in a scratch worktree with this static dir copied in, a fresh SQLite DB
and outbound network blocked. It was served through a stdlib HTTP→ASGI bridge, because this
interpreter has no uvicorn. The bridge rewrites `Origin` to the app's `https://testserver`
origin. The bridge is `tests/fixtures/cc_mock/real_backend_bridge.py`.

`real_backend_check.mjs` result: **44 OK, 0 FAIL** (`evidence/D_real_backend_check.txt`). It
covered:
- the real `__Host-` cookie login;
- the strict CSP on `/cc/`;
- all 13 routes with no error state, no horizontal scroll and no console errors;
- real Unknown money renders "Unknown";
- a real `/ask` POST was accepted with CSRF + nonce.

Screenshots: `evidence/D_screens/` holds 12 PNGs from the mock run, 284 KB in total.

## Wiring requests

None. Lane C already mounts `/cc/` from this directory. **Merge note:** lane C committed a
placeholder `static/index.html`. On merge, take lane D's version.

Packaging: confirm that the Docker image or package data includes `command_center/static/**`
(`.js`, `.css`, `.webmanifest`, `.png`, `.svg`).

## Open items / not verified

- I did not test on a real phone, iOS Safari, or PWA install/home-screen launch. Only headless
  Chromium was used.
- Push, email and SMS notifications are gated server-side. The UI says only in-app delivery exists.
- Period filter: the backend has no support for it yet.
- Store preview: lane F has not reported a URL yet.
- Lane E accounting item shape is unknown. The UI turns any money-shaped item into a tile and
  renders anything else generically.
- Things I noticed in other files (not mine, and I did not change them):
  - `test_secret_scan` fails on `tests/test_rc1_ord2.py:169`.
  - `test_vacuity` flags 3 loops in other files.
