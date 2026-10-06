# W3 lane F handoff: Talk to Laura in the Owner Command Center (business context)

Branch `claude/w3-F`, based on `claude/v11-CANON` @ f0c2d12. It has merged `claude/w3-D` (3fd64e9),
`claude/w3-E` (c846efc) and, at the integrator's request, `claude/visual-investigation` (931d4ff).
Scope is **business conversations only**. No private or spouse register was built. The agency
package has no code path to a private tier, and lane E's API has no private tier either.

## Requirements and status
| Requirement (directive §8, spec/07 item 9, D-FB-13) | Status |
|---|---|
| Talk to Laura as a primary CC interface, covering the 8 owner questions | COMPLETE. Keyword intents, matched at word boundaries; anything unmatched falls back to Ask Company |
| Answers come from durable evidence with source links | COMPLETE. Each fact carries `source`, `link` (an in-app route), `as_of` and `basis` |
| Deterministic first; optional model phrasing only via the gateway, with spend recorded | COMPLETE. Phrasing is off by default. When used, it must keep every number and every UNKNOWN, otherwise the deterministic text is kept. Production routing task `laura.business_phrase` is not registered, so production phrasing is GATED |
| UNKNOWN when evidence is missing; no invented facts; UNKNOWN money is never CA$0.00 | COMPLETE |
| Evidence sources | autonomy status/timeline/missions, `laura.executive` priorities/decisions (D), accountant via `tabs.money_section`, Learn, lessons, seo (including `w3`), ads, store_foundation, `visual.rnd.status` (H; tolerated absent, H not merged here), approvals/incidents/products, `laura.memory` (E), `laura.identity` (D) |
| Authorised follow-on work | COMPLETE. Only a proposal stored with the turn can be acted on. GREEN work goes through `orchestrator._enqueue_mission`. Protected work requires step-up and goes through `_raise_approval`, so it becomes an owner action and never a job. Lane D's constitution check (Finance, Product Truth, Security) runs first. Department blocks are respected. Each follow-on is audited as `laura`, appears on the timeline, and is written to her operational memory |
| PWA Laura view, mobile first | COMPLETE. Laura is the first primary tab. The canonical portrait is served by the owner-gated `/api/cc/laura/portrait` and is visibly labelled "Internal — canonical reference, not publication-approved". The view shows the conversation, evidence links, and follow-on buttons with a confirmation dialog (plus step-up for protected work) |
| Non-owner cannot reach Laura | COMPLETE. Every route is under `/api/cc/`, behind owner session, CSRF, nonce, timestamp and same-origin |
| `/cc/store-preview?variant=` passthrough | COMPLETE |
| Integrator wiring: K3 listing outcomes | COMPLETE. `POST /api/listing-outcomes` (operator bearer, in main.py) and `POST /api/cc/listing-outcomes` (owner session, CSRF, nonce). `OutcomeRefused` returns 400 |
| Integrator wiring: A brand fonts | COMPLETE. `GET /brand/fonts/{name}` is allow-listed by file name (font/woff) under the app CSP `font-src 'self'`. Use `font_face_css("/brand/")` |
| Integrator wiring: G seo w3 | COMPLETE. New Store tab section `seo_w3`; Laura's SEO evidence states the strategy and constraint counts |
| Integrator wiring: E principal | COMPLETE. `Principal.owner(session_public_id)` is built only from `auth.current_public_id(request)`. A forged or empty id gives UNKNOWN |

## Files
- **New:** `src/brambleloop/laura/agency/{__init__,models,evidence,talk,followon,identity_view,phrasing}.py`, `app/command_center/static/js/views/laura.js`.
- **Modified:** `app/main.py` (listing-outcomes and brand-font routes), `app/command_center/api.py` (`/laura*`, `/listing-outcomes`, store-preview variant), `tabs.py` (`seo_w3`).
- **Modified:** `providers.py`. It now retries with the facade when a provider swallows the Session mismatch. This fixed the learn and ads providers, which had been reading UNKNOWN "no attribute 'session'" in every CC tab.
- **Modified (PWA):** `api.js`, `routes.js`, `dom.js` (icon), `sw.js` (shell v2 + laura.js), `app.css`.
- **New tables:** `laura_cc_turns` and `laura_cc_followons`, created by `models.ensure_tables`. No shared-file change was needed.
- **Tests:** `tests/w3_laura_cc_harness.py` and `tests/test_w3_laura_cc_{talk,followon,access,integration,wiring}.py`.
- **Evidence:** `research/final_build/w3/evidence_F/`, containing laura_phone.jpg 43 KB, laura_desktop.jpg 103 KB, and the browser check script.

## Tests (counts are OK lines)
- **Lane F (28/28):** talk 9, followon 4, access 5, integration 5, wiring 5.
- **Regression, all 0 FAIL:** pwa_static 79, cc_actions 7, cc_auth 16, cc_views 13, r2_security actions 4, department_block 2, freshness 3, login_lockout 5, v11_wiring_cc 5, v11_store_preview 13, secret_scan 6, vacuity 7, and lane E memory 28.
- **Before the visual-investigation merge, the regression list ran clean.** After the merge, see the final report for the rerun.

## Runtime proof
- **Setup:** a real backend through the bridge (`tests/fixtures/cc_mock/real_backend_bridge.py` plus a Registry seed), driven by Playwright Chromium.
- **Phone 390×844 and desktop 1280×860:** Laura is in the primary nav. The portrait loads from the gated API and carries its internal label. On the empty DB the overnight answer was UNKNOWN. Evidence links are in-app routes. There is no horizontal scroll and no console or CSP errors.
- **Follow-on:** confirming the proposed follow-on created a mission job (`jobs:N`). The next overnight answer then cited that mission and the `laura.followon` timeline event.

## DEFECTS / WIRING REQUESTS
1. **Lane D (blocking, owner-safe because it fails closed):** after the integration branch merge (D-FB-14, identity revision 2 `laura-r2-a42aeac7`), lane D's pinned `GENESIS_SHA256` no longer matches its genesis record.
   - Effect: `identity.ensure` raises `IdentityTampered`, the constitution blocks every Laura action, and the identity provider reads BLOCKED.
   - Request: lane D re-pins after recording the D-FB-14 amendment.
   - My test harness applies the re-pin in-process only, prints a WARN line, and separately proves the fail-closed behaviour.
2. **Gateway owner:** register routing task `laura.business_phrase` (cheapest tier, CA$0 until the owner authorises) if production phrasing is wanted. Until then it is refused and the deterministic answer stands.
3. **Lane D (optional):** record CC follow-ons as `laura_decisions` so her executive history includes owner-requested work. Today they are recorded in the audit log, the timeline, operational memory and `laura_cc_followons`.
4. **K3 optional item (show `listing_outcomes.latest` in growth view):** not done.

## Not verified / open
- Lane H's `visual.rnd` provider has not been merged into this branch. The adapter follows the contract but has not been exercised against it.
- Postgres has not been exercised; tests ran on SQLite only.
- No model phrasing ran against a real provider, and no paid calls were made.
- Intent classification uses keyword rules. Unusual phrasings fall back to Ask Company, or to UNKNOWN.
