# v1.1 lane C handoff — Owner Command Center backend / API / security

Branch `claude/v11-C` (base `claude/visual-investigation` @ 0694fb7). Worktree
`/home/user/Project-Money/.claude/worktrees/v11-C`. Not pushed. Phase stays shadow; no
network, no provider calls, no deploy.

## Requirement status

| ID | Status | What exists / why not complete |
|---|---|---|
| F-882 (backend) | COMPLETE (backend) | `/api/cc/*` JSON API for HOME, APPROVALS, STORE, MONEY, OPERATIONS, AUTONOMY/LEARN, INSIGHTS, NOTIFICATIONS, ACCOUNT, ASK, TIMELINE, MORNING BRIEF, EMERGENCY; `/cc/` static mount (placeholder; lane D owns the PWA). Mobile UX itself is lane D. |
| F-884 | COMPLETE | `GET /api/cc/home`: headline (revenue/profit as Money objects, store, launch phase, autonomy, incidents, owner decisions), changes since last view (`POST /home/seen`), work in 24 h, opportunities. Test: built from seeded production tables. |
| F-885 | COMPLETE | Cards re-shape the existing single owner queue (`build2.executor.approval_inbox`) + publication candidates (`ops.publication_authority.evidence`) with every F-885 field; unknown max spend is `null`, never 0. |
| F-886 | COMPLETE for the actions that have an in-system mechanism | publication/activation preview/approve/revoke, improvement/challenger approval, incident acknowledge, owner-action defer. Gate cards whose decision happens at a provider (buy credits, OAuth) are shown with `not_executable_reason` — the gate re-checks reality. |
| F-887 | COMPLETE | Owner session (PBKDF2 passphrase hash from env, optional RFC 6238 TOTP), `__Host-` HttpOnly Secure SameSite=Strict cookie, CSRF header (HMAC of session token) + Origin/Sec-Fetch-Site check, nonce + timestamp replay protection, 5-min step-up for consequential actions, login/step-up/mutation rate limits, every refusal audited in `cc_security_events`. Installed inside the existing application-wide `security.operator_gate` (default-deny unchanged). |
| F-888 | COMPLETE | `GET /api/cc/account`: owner auth config, sessions (list / revoke / revoke-others), security events, connected OAuth services (no secrets), model providers, budgets, phase + live grants, notification policy, emergency state. |
| F-889 | COMPLETE | Pause department / spend / publishing / company and kill-to-shadow, built on existing mechanisms only: `Agent.enabled` (enforced by `Registry.authorize` in the worker), `SpendLimit.paused` (enforced by `SpendGuard`), grant revocation via `ops.*_authority.revoke`, `core.phase.record_transition(to=shadow)`. Pausing needs no step-up; resume needs step-up and only undoes what the command center paused (breach-paused scopes and otherwise-disabled agents stay). Executive, Product Truth, Finance, Platform are never paused (monitoring/evidence/recovery). |
| F-896 | COMPLETE (pull) | `GET /api/cc/brief/morning?hours=12`. Delivery is in-app only (no push/email: GATED, see below). |
| F-897 | COMPLETE (in-app) / GATED (external channels) | `cc_notifications`: deduped on unique key, severity-ranked, quiet hours + digest, auto-resolve; routine jobs/audit rows suppressed and counted; dead letters aggregated to one; security burst counts attacks only. External email/SMS/push is GATED: new integration + CASL review + owner authority. |
| F-898 | COMPLETE for lane C paths | Every view reads production tables or the cross-lane providers; UNKNOWN → `null` + state word, never 0 (test walks every Money object). Test greps the package for fixture/demo/mock paths. |
| F-899 | COMPLETE (ops) / PARTIAL (money) | `operations/drill` (job/incident/audit/agent: row, responsible agent, audit history, source). `money/drill` delegates to lane E `drill(db, metric)`; until E merges only `recorded_spend` drills to cost entries and the rest is UNKNOWN. |
| F-925 | COMPLETE for routine ops | Approvals, monitoring, emergency, sessions, notifications, incident ack via HTTP. One-time setup (generating the passphrase hash: `python -m brambleloop.app.command_center.auth hash`, setting env vars) is not routine operation. |
| F-927 | COMPLETE | `GET /api/cc/timeline` merges lane A `autonomy.status.timeline` (UNKNOWN until merged) with significant audit rows, newest first, each with `source`. |
| F-928 | COMPLETE (deterministic) | `POST /api/cc/ask`: product-blocked (product/pattern_versions/certificate findings/publication gate sections/incidents/audit), launch-blocked, overnight, profit, approval-reason, incidents. Every fact carries a source. No model call (no new paid API); a model paraphrase via `gateway.model_gateway` was deliberately not added. |
| F-929 | COMPLETE for Ask/actions | Ask returns `status: UNKNOWN` when no evidence supports an answer; owner actions require validated inputs and existing authority, refusals verbatim (409). |

## Files

Created: `src/brambleloop/app/command_center/{__init__,api,auth,models,providers,readers,tabs,approvals,emergency,notifications,ask}.py`, `src/brambleloop/app/command_center/static/index.html` (placeholder), `tests/test_v11_cc_{auth,actions,views}.py`, `research/final_build/v1_1/COMMAND_CENTER_API.md`, `research/final_build/v1_1/evidence/C_runtime_proof.json`, this file.

Modified: `app/main.py` (+4 lines: `command_center.install(app, db)` after the storefront router), `app/security.py` (additive: `OWNER_SESSION_PREFIX`, `register_owner_session_gate`, `owner_session_route`, a 5-line branch at the top of `operator_gate` delegating `/api/cc/*` to the registered owner-session gate — 503 if none registered; `POST /api/cc/auth/login` added to `PUBLIC_MUTATING_ROUTES` with its reason).

New tables (on shared `Base`, created by `create_all` because `main.py` imports the package; also `ensure_tables` creates them lazily): `cc_owner_sessions`, `cc_nonces`, `cc_security_events`, `cc_notifications`, `cc_kv`. Additive only.

## Design decisions worth reviewing

* **Delegated operator credential.** Grants are sealed with `BRAMBLELOOP_OPS_TOKEN` by the existing authority modules. The command center calls those same functions with the server-held token on behalf of a session that passed session + CSRF + nonce + step-up. The browser never holds the operator token. The grant is the existing sealed/chained/expiring/revocable row and is re-validated at execution (proved by the revoke-before-execute test). The grant `reason` is tagged `[owner via command center owner:cc:s_…]`, and an `audit_log` row `cc.owner_action.*` names the session.
* **Refusals audited outside `audit_log`.** `tests/test_route_auth_default_deny.py` requires a refused request not to change `audit_log`; refusals therefore go to the append-only `cc_security_events` (shown in ACCOUNT and driving the security notification).
* **The operator bearer token alone is not accepted on `/api/cc/*`** (owner session required) — a deliberate separation; the existing `/api/owner/*` routes keep bearer auth.
* **Global login rate limit** (20 failures / 15 min across all clients) protects against distributed guessing but means an attacker can temporarily lock out owner login; existing sessions keep working. Revisit if it bites.
* **Ask Company is deterministic.** No model is called.

## Tests and results (python3 = /usr/bin/python3 with fastapi; the repo `.venv` lacks fastapi)

`cd brambleloop && PYTHONPATH=src python3 tests/<file>`:

* `test_v11_cc_auth.py` — 16/16 OK (auth on every non-public `/api/cc` route by enumeration, CSRF/cross-site/nonce/stale/replay on every mutating route, step-up, step-up lockout, login rate limit, JSON+same-origin login, cookie flags, session list/revoke/logout, TOTP incl. RFC 6238 vector, 503 when ops token unset, 503 when no passphrase hash, no secret echo; refusals audited and `audit_log` unchanged).
* `test_v11_cc_actions.py` — 7/7 OK (§95 revoke-before-execute for activation; publication grant revoked by publishing pause; department pause → `Registry.authorize` refuses, never-paused refused, resume leaves other-disabled agents; spend pause → `SpendGuard` refuses, resume leaves breach pause; kill → sealed shadow transition; improvement approval through `cells`; authority refusals audited).
* `test_v11_cc_views.py` — 12/12 OK (MONEY UNKNOWN not 0 when provider absent / disconnected / raising / malformed; provider receives a Session and passes through with provenance; home + morning brief from real DB rows; F-885 card fields; notification noise suppression + dedupe + severity + quiet hours + resolve; security burst counts attacks only; Ask grounded on `pattern_versions:`/`incidents:` sources; Ask UNKNOWN; timeline/drill provenance; every tab answers with envelopes; no fixture words in package).
* Existing: `test_route_auth_default_deny.py` 7/7 OK; `test_web_security.py` 11/11 OK; `test_customer_data_auth.py` 8/9 — the 1 FAIL is `/api/launch` raising `ModuleNotFoundError: numpy` (the system python3 has no numpy; pre-existing environment gap, unrelated to lane C); `test_oauth_security_audit.py` all OK except "uvicorn is importable" (uvicorn not installed — environment); `test_vacuity.py` — no lane C findings (remaining findings are pre-existing files); `test_secret_scan.py` — only pre-existing finding in `tests/test_rc1_ord2.py`.

## Runtime proof

`research/final_build/v1_1/evidence/C_runtime_proof.json`: the real `main.app` driven through ASGI TestClient over a fresh SQLite DB with seeded agents (shadow, no network): anonymous 401s (audited), bad login 401, login 200, missing CSRF 403, replay 409, HOME/MONEY with revenue `UNMEASURED` (value null), 14 approval cards from the real executor gates, notifications, Ask (launch-blocked ANSWERED with sources; profit UNKNOWN), department pause, platform pause refused, kill → shadow, security events in ACCOUNT, `/cc/` served with the strict CSP. Not exercised: a real uvicorn process, Postgres, a phone browser.

## WIRING REQUESTS

None required: `main.py` (owned by this lane) imports the package, so the tables register on `Base` before `create_all`. Optional for the integrator: add `from ..app.command_center import models as cc_models  # noqa: F401` to `core/db.py:create_all` so worker-only processes also create the tables (not needed for function; the web app creates them).

## Open items / could not verify

* Lane D PWA not present here; `/cc/` serves a placeholder.
* Provider functions for lanes A, B, E, F, G, H, I do not exist on this base: every such section reports UNKNOWN "not built" (tested). Behaviour with the real providers is verified only against the contract via injected modules.
* External notification channels: GATED (CASL + owner authority + new integration).
* Owner identity is "holder of the passphrase (+TOTP)", not a verified natural person — same principal model as the existing ops-token grants.
* Not tested on Postgres (SQL used is portable SQLAlchemy; nonce uniqueness relies on a unique index on both).
