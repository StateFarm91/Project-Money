# Owner Command Center API (v1.1 lane C) — contract for the PWA (lane D)

Status: implemented on branch `claude/v11-C` (see `handoff_C.md` for what is proven).
Module: `src/brambleloop/app/command_center/` — mounted by `app/main.py` at `/api/cc/*`
(JSON) and `/cc/` (static PWA files from `command_center/static/`).

Requirement IDs: F-882 (backend), F-884, F-885, F-886, F-887, F-888, F-889, F-896, F-897,
F-898, F-899, F-925, F-927, F-928, F-929.

## 0. Conventions every client must follow

* **Same origin only.** The PWA is served from `/cc/` on the same host as `/api/cc/*`. No CORS.
* **Session cookie.** `POST /api/cc/auth/login` sets `__Host-bl_cc` (HttpOnly, Secure,
  SameSite=Strict, Path=/). JavaScript never sees it; the browser sends it automatically.
  Use `fetch(url, {credentials: "same-origin"})`.
  *Local http dev*: browsers drop `Secure` cookies on plain http except on `localhost`.
* **CSRF.** Login and `GET /api/cc/auth/status` return `csrf_token`. Every non-GET request
  must send header `X-CSRF-Token: <csrf_token>`. The token is bound to the session; re-read it
  after login/step-up from the response or from `/api/cc/auth/status`.
* **Replay protection.** Every non-GET request (except login) must also send
  `X-CC-Nonce: <16–128 chars of [A-Za-z0-9_-], fresh per request>` (e.g.
  `crypto.randomUUID()`) and `X-CC-Timestamp: <unix seconds>` within ±120 s of server
  time. A reused nonce is refused (`409`, code `REPLAY`).
* **Content type.** Request bodies are JSON (`Content-Type: application/json`).
* **Step-up.** Consequential actions (approving a protected authority, resuming anything
  paused, owner decisions that loosen a control) require a recent re-authentication:
  `POST /api/cc/auth/step-up`. The window is `stepup_window_seconds` (default 300) and is
  reported as `stepup_valid_until` in `/api/cc/auth/status`. Without it the action answers
  `403` with code `STEP_UP_REQUIRED`; the client should prompt for the passphrase (+ TOTP when
  `totp_required`), call step-up, then retry with a **new** nonce.
* **Pausing never needs step-up.** Anything that only makes the company *more* restrictive
  (pause, kill switch to shadow, revoke a grant, revoke a session, acknowledge) needs only a
  valid session + CSRF + nonce.
* **Errors.** Refusals from the gate: `{"error": "<message>"}`. Command-center refusals:
  `{"error": "<message>", "code": "<CODE>"}`. Codes: `NOT_AUTHENTICATED` (401),
  `CSRF` (403), `REPLAY` (409), `STALE_REQUEST` (400), `STEP_UP_REQUIRED` (403),
  `RATE_LIMITED` (429), `LOGIN_NOT_CONFIGURED` (503), `BAD_CREDENTIALS` (401),
  `REFUSED_BY_AUTHORITY` (409: the existing authority mechanism refused — message says why),
  `BAD_REQUEST` (400), `NOT_FOUND` (404). `503` with `{"error": ...}` means the operator
  credential (`BRAMBLELOOP_OPS_TOKEN`) is not configured server-side: the whole command
  center is closed (fail closed).
* **Every refused attempt is audited** (table `cc_security_events`), visible in ACCOUNT.

### The status envelope (every tab section / provider)

Every department section has this shape (the cross-lane provider contract):

```json
{"status": "OK|DEGRADED|BLOCKED|UNKNOWN", "as_of": "2026-10-06T12:00:00+00:00" | null,
 "basis": "measured|estimated|modelled|unknown", "items": [...], "sources": ["table:id", ...],
 "reason": "why UNKNOWN/BLOCKED (present when not OK)", "provider": "module.function"}
```

**Rendering rules for the client (F-898):**
* `status == "UNKNOWN"` → render the word UNKNOWN (with `reason`), never `0`, `$0.00` or `—`
  that could read as zero.
* A money value is an object `{"value_cad": number|null, "state": "MEASURED|ESTIMATED|
  MODELLED|UNKNOWN|UNMEASURED", "basis": ..., "display": "CA$12.34"|"UNKNOWN", "sources": [...]}`.
  Render `display`. `value_cad` is `null` whenever the state is not measured/estimated; the
  client must never coerce `null` to 0.
* `basis` must be shown next to any estimated/modelled figure ("estimated", "modelled").

## 1. Authentication (F-887, F-888)

Server configuration (environment only, never the repo):
* `BRAMBLELOOP_OWNER_PASSPHRASE_HASH` — `pbkdf2_sha256$<iterations>$<salt_b64>$<hash_b64>`.
  Generate: `PYTHONPATH=src python3 -m brambleloop.app.command_center.auth hash`
  (prompts for the passphrase; prints the value to put in the hosting environment).
* `BRAMBLELOOP_OWNER_TOTP_SECRET` — optional base32 RFC 6238 secret. When set, login and
  step-up also require a 6-digit `totp` code.
* `BRAMBLELOOP_OPS_TOKEN` — existing operator credential; without it every `/api/cc/*` route
  except `auth/status` answers 503.

### `GET /api/cc/auth/status` (public)
```json
{"authenticated": false, "login_configured": true, "totp_required": false,
 "csrf_token": null, "session": null, "stepup_valid_until": null,
 "stepup_window_seconds": 300, "server_time": 1759752000}
```
When authenticated: `csrf_token` is a string, `session` =
`{"session_id": "s_...", "created_at": iso, "expires_at": iso, "idle_expires_at": iso,
  "device_label": "Pixel"}`, `stepup_valid_until` iso or null.

### `POST /api/cc/auth/login` (public; rate-limited)
Body `{"passphrase": "...", "totp": "123456"?, "device_label": "My phone"?}`.
200 → sets cookie, body `{"authenticated": true, "csrf_token": "...", "session": {...},
"stepup_valid_until": iso}` (a fresh login counts as step-up).
401 `BAD_CREDENTIALS`, 429 `RATE_LIMITED` (5 failures / 15 min per client, 20 global),
503 `LOGIN_NOT_CONFIGURED`.

### `POST /api/cc/auth/logout`
Revokes this session, clears cookie. → `{"logged_out": true}`

### `POST /api/cc/auth/step-up`
Body `{"passphrase": "...", "totp": "..."?}` → `{"stepup_valid_until": iso}`.
5 failed step-ups revoke the session.

## 2. Tabs (all `GET`, session required)

Each tab returns `{"tab": "<NAME>", "generated_at": iso, "sections": {<name>: envelope},
...tab-specific fields}`. Every envelope follows §0.

| Endpoint | Tab | Sections (provider) |
|---|---|---|
| `GET /api/cc/home` | HOME (F-884) | `headline` (money/store/launch/autonomy/incidents/owner actions), `changes_since_last_view`, `autonomy` (A), `store` (F), `money` (E/fallback), `incidents`, `owner_actions`, `opportunities` |
| `POST /api/cc/home/seen` | — | marks "last viewed" for `changes_since_last_view` → `{"seen_at": iso}` |
| `GET /api/cc/brief/morning?hours=12` | Morning handoff (F-896) | `what_changed`, `completed`, `money_spent`, `incidents`, `discoveries`, `queued_actions`, `decisions_needed` |
| `GET /api/cc/approvals` | APPROVALS (F-885) | `cards: [ApprovalCard]`, plus `waiting_on_data`, `external_capability_unavailable` |
| `GET /api/cc/approvals/{card_id}` | one card | `ApprovalCard` |
| `GET /api/cc/store` | STORE | `store_foundation` (F), `seo` (G), `products` (products/releases/listings from DB), `launch_packet` |
| `GET /api/cc/money` | MONEY (F-914 view) | `accounting` (E), `revenue`, `recorded_spend`, `spend_limits`, `source_health` |
| `GET /api/cc/money/drill?metric=<key>` | drill (F-899/F-915) | `rows` with source refs; via E `drill(db, metric)`; UNKNOWN when E absent |
| `GET /api/cc/operations` | OPERATIONS | `slo` (I), `queue` (jobs by status, dead letters), `cadences`, `incidents`, `agents` (enabled/paused), `emergency` |
| `GET /api/cc/operations/drill?kind=job\|incident\|audit\|agent&id=<id>` | drill (F-899) | the row, timestamps, responsible agent, related audit rows |
| `GET /api/cc/autonomy` (alias `GET /api/cc/learn`) | AUTONOMY/LEARN | `autonomy` (A), `improvement` (B), `jobs_24h`, `hours_since_owner_prompt`, `last_useful_action` |
| `GET /api/cc/insights` | INSIGHTS | `seo` (G), `ads` (H), `experiments`, `lessons`, `intel` |
| `GET /api/cc/timeline?limit=50` | Company timeline (F-927) | `events` from A `timeline(db, limit)` merged with audit log rows, newest first |
| `GET /api/cc/notifications` | NOTIFICATIONS (F-897) | `notifications: [Notification]`, `digest`, `policy`, `suppressed_count` |
| `GET /api/cc/account` | ACCOUNT (F-888) | `owner`, `sessions`, `security_events` (refused attempts), `connected_services`, `providers`, `budgets`, `authorities` (live grants), `notification_policy`, `emergency` |

### ApprovalCard (F-885)
```json
{"card_id": "gate:etsy_api" | "owner_action:12" | "publication:slug@v" | "improvement:7" | "challenger:3",
 "kind": "GATE|OWNER-DECISION|PUBLICATION|ACTIVATION|IMPROVEMENT|CHALLENGER",
 "title": "...", "proposed_action": "...", "recommendation": "...",
 "evidence": [{"label": "...", "state": "PASS|FAIL|UNKNOWN|...", "why": "...", "source": "..."}],
 "uncertainty": "...", "expected_benefit": "...", "downside": "...",
 "max_spend_cad": 0.0 | null, "reversibility": "...", "deadline": iso | null,
 "consequence_of_no_action": "...",
 "executable": true, "actions": [{"action": "publication.approve", "requires_step_up": true,
   "params": {"slug": "...", "version": "...", "release": "...", "expected_digest": "..."}}],
 "not_executable_reason": "external gate: no owner action opens it" | null,
 "sources": ["owner_actions:12", "build2.executor.approval_inbox"]}
```
`max_spend_cad: null` means UNKNOWN (render UNKNOWN, not 0).

### Notification
```json
{"id": 12, "dedupe_key": "incident:42", "severity": "critical|high|normal|low",
 "category": "decision|risk|deadline|commercial|anomaly|security",
 "title": "...", "body": "...", "consequence": "...", "deadline": iso|null,
 "evidence": ["incidents:42"], "deep_link": "/cc/#/approvals/gate:etsy_api",
 "first_seen_at": iso, "last_seen_at": iso, "occurrences": 3,
 "acked_at": iso|null, "delivered": "in_app", "held_for_quiet_hours": false}
```
Only the in-app channel exists. External channels (email/SMS/push) are **GATED** (owner
authority + CASL review) and are not sent.

## 3. Owner actions (F-886) — all `POST`, session + CSRF + nonce

### `POST /api/cc/actions/{action}`
Body: the action's params plus `"reason": "a sentence"` where noted.

| action | params | step-up | routes through |
|---|---|---|---|
| `publication.preview` | `slug, version, release` | no | `ops.publication_authority.snapshot/evidence` → `{content, digest, display}` |
| `publication.approve` | `slug, version, release, expected_digest, reason` | **yes** | `ops.publication_authority.approve` (sealed, chained, 24 h grant) |
| `publication.revoke` | `approval_id` | no | `ops.publication_authority.revoke` |
| `activation.preview` | `slug, version, release` | no | `ops.activation_authority.snapshot` |
| `activation.approve` | `slug, version, release, expected_digest, reason` | **yes** | `ops.activation_authority.approve` |
| `activation.revoke` | `approval_id` | no | `ops.activation_authority.revoke` |
| `improvement.approve` | `id, why` | **yes** | `improve.cells.record_owner_approval` |
| `challenger.approve` | `id, why` | **yes** | `improve.league.record_owner_decision` |
| `incident.acknowledge` | `incident_id, note?` | no | audit row only (does not resolve) |
| `owner_action.defer` | `owner_action_id, note?` | no | audit row only (the gate stays computed from reality) |

Response 200: `{"ok": true, "action": "...", "result": {...authority result...},
"audit_id": 123}`. Refusal by the underlying authority: `409 REFUSED_BY_AUTHORITY` with the
authority's own message (e.g. digest changed, chain broken). Grants are executed with the
server-held operator credential on behalf of the step-up-verified owner session; every grant
is still sealed, chained, expiring and re-validated at the execution boundary, so revoking it
before execution makes execution refuse (§95).

## 4. Emergency controls (F-889)

### `GET /api/cc/emergency`
```json
{"phase": {"phase": "shadow", ...core.phase.resolve...},
 "departments": [{"department": "growth", "agents": ["growth","ads"], "paused": false,
                  "pausable": true}],
 "spend": {"scopes": [{"scope": "llm", "paused": false}], "all_paused": false},
 "publishing": {"paused": true, "agents": ["store_operator"], "live_grants": []},
 "never_paused": ["platform", "monitoring", "evidence", "recovery"]}
```

### `POST /api/cc/emergency/pause` — no step-up
Body `{"scope": "company|publishing|spend|department", "department": "growth"?, "reason": "..."}`.
* `department` → disables that department's agents (`Agent.enabled=false`, enforced by
  `Registry.authorize` in the worker). Platform/monitoring/evidence agents are never paused.
* `spend` → `SpendLimit.paused = true` on every scope (`SpendGuard` refuses all spend) and
  disables the `ads` agent.
* `publishing` → disables `store_operator` + `publishing` agents and revokes every live
  publication/activation grant.
* `company` → all of the above for every pausable department.

### `POST /api/cc/emergency/kill` — no step-up
Body `{"reason": "..."}` → records an owner phase transition down to **shadow**
(`core.phase.record_transition`) and performs `company` pause. Result includes the new
effective phase.

### `POST /api/cc/emergency/resume` — **step-up required**
Body `{"scope": "publishing|spend|department|company", "department"?, "reason"}` →
re-enables agents / unpauses spend scopes. Never moves the phase up (that stays on the
existing evidence-bound `/api/owner/phase/transition` route).

## 5. Account & sessions (F-888)

* `GET /api/cc/account/sessions` → `{"sessions": [{"session_id", "device_label",
  "created_at", "last_seen_at", "expires_at", "current": bool, "revoked_at"}]}`
* `POST /api/cc/account/sessions/{session_id}/revoke` → `{"revoked": "s_..."}`
* `POST /api/cc/account/sessions/revoke-others` → `{"revoked": n}`
* `POST /api/cc/notifications/policy` body `{"quiet_hours": {"start": "22:00", "end":
  "07:00", "tz": "America/Toronto"}, "min_severity": "normal", "digest": "morning"}` →
  stored policy. Critical/security notifications ignore quiet hours.
* `POST /api/cc/notifications/{id}/ack` → `{"acked": id}`
* `POST /api/cc/notifications/refresh` → regenerates from durable state → `{"created": n,
  "deduplicated": n, "suppressed": n}`

## 6. Ask Company (F-928, F-929)

### `POST /api/cc/ask`
Body `{"question": "why is product throw-blanket blocked?"}` →
```json
{"question": "...", "intent": "product_blocked|overnight|launch_blocked|profit|approval_reason|incidents|unknown",
 "answer": "Product throw-blanket v1 is blocked by: certification FAIL (…), search UNKNOWN (…).",
 "status": "ANSWERED|UNKNOWN",
 "facts": [{"statement": "...", "source": "pattern_versions:4", "as_of": iso}],
 "next_action": "...", "sources": ["pattern_versions:4", "incidents:2", "audit_log:17"],
 "method": "deterministic retrieval (no model call)"}
```
When no durable evidence supports an answer, `status` is `UNKNOWN` and `answer` says what is
missing; nothing is invented. No model is called (no paid API calls in v1.1 lane C).

## 7. Static PWA

* `GET /cc/` → `static/index.html`; `GET /cc/<file>` → files in `static/` (lane D owns the
  contents). Served with a strict CSP:
  `default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:;
  connect-src 'self'; font-src 'self'; manifest-src 'self'; worker-src 'self';
  form-action 'self'; base-uri 'none'; frame-ancestors 'none'; object-src 'none'`
  (no inline script or style — put styles in a `.css` file).
* Service worker must live at `/cc/sw.js` (scope `/cc/`). Do not cache `/api/cc/*` responses
  as current truth (F-898); show the `as_of` of any cached view as stale.
