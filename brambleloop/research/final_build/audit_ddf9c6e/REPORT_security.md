# Lane J audit: Owner Command Center security (SHA ddf9c6e, area = security)

Method: real FastAPI app, TestClient, fresh SQLite DB, no network. Repros: `j_sec_*.py` in this
directory (`./run.sh j_sec_NN_*.py`). Existing suites on this SHA all pass: test_web_security 11/11,
test_route_auth_default_deny 7/7, test_customer_data_auth 9/9, test_v11_cc_auth 16/16,
test_v11_cc_actions 7/7, test_v11_cc_views 13/13, test_v11_wiring_cc, test_rc1_auth 11/11.

Verdict: no LAUNCH-BLOCKING and no HIGH. Auth, CSRF, session, XSS, CSP, SW caching and buyer-ref
scrub hold. 3 MEDIUM, 3 LOW.

## Findings

### M1 MEDIUM  Login lockout of the real owner by any unauthenticated party (sustainable)
auth.py:`login_rate_limited` (global >=20 refused logins / 15 min), api.py `login` (limit checked
before the credential; the 429 refusals are themselves logged as kind=login refused events).
Repro j_sec_03: 20 bad logins with rotating X-Forwarded-For/UA -> next login WITH THE CORRECT
passphrase returns 429. At +14 min still 429; after 20 more attacker requests the burst is "16 min
old" and the owner is still 429, so ~20 requests/15 min holds the lock indefinitely. Per-client
limit is also bypassed by spoofing X-Forwarded-For (`client_hash`, 19 tries from one source all
401). Impact: owner cannot use the phone Command Center (approvals, kill switch via CC) while under
attack; operator-token routes still work. Fix: do not count 429/CSRF/non-JSON refusals as failures;
trust XFF only from the platform proxy; make the global limit slow (delay/captcha-less backoff) rather
than a hard lock for a correct credential, or exempt a login that presents valid TOTP+passphrase
from a known device.

### M2 MEDIUM  X-CC-Timestamp "nan" defeats freshness; nonce purge makes a request replayable
auth.py `_check_freshness`: `skew = abs(time.time() - float("nan"))` is nan; `nan > 120` is False,
so it passes. Repro j_sec_03 F1: ts=nan accepted (200); immediate replay 409; after the nonce ages
past NONCE_RETENTION (10 min) and is purged, the identical request is accepted again (200). Control
with a real stale timestamp is refused (400). Impact: documented replay protection is a one-header
bypass; replay still needs a live session cookie+CSRF, so bounded to captured requests during a live
session. Fix: `if not math.isfinite(x) or skew > N`.

### M3 MEDIUM  Department block bypasses the "monitoring never pauses" rule (F-889), no step-up
api.py `department_block` accepts executive/finance/platform/product_truth, which
emergency.pause refuses (NEVER_PAUSED). Repro j_sec_14: pause on each -> 409; block on each -> 200
without step-up; `orchestrator.tick` then reports all four BLOCKED (scheduling, reconciliation,
reliability, validation cadences stop generating work). A stolen/idle session can silently blind the
company. Fix: refuse block for NEVER_PAUSED departments (or require step-up and a loud incident).

### L1 LOW  publication.approve / activation.approve do not enforce evidence gating server-side
approvals.execute -> publication_authority.approve only checks a certified release + listing
binding + digest; evidence PASS is UI-only (`executable`). Repro j_sec_05: release with
certification FAIL, disclosure FAIL, parity/policy/search/rollback UNKNOWN: inbox card says
"Not ready", yet POST /api/cc/actions/publication.approve with a step-up session returns 200 and
`pub.validate` returns None (grant valid at the boundary). Needs step-up and the owner's own
decision; downstream publish gates still apply. (Patched only etsy_ops payload helpers to build a
synthetic CIR; evidence readers were real.) Fix: refuse approve unless `summary.all_gated_sections_pass`,
or require an explicit `override_reason`.

### L2 LOW  revoke of a non-existent approval id reports success
api.py/approvals: `publication.revoke {"approval_id":999999}` -> 200 `{"revoked":999999}` and writes
a sealed revocation row for an id that was never a grant (sealed_chain.revoke does not check).
Misleading owner-facing result; pre-revokes a future audit id. Fix: 404 unless the id is an
APPROVED row of that ledger.

### L3 LOW  Origin check ignores scheme; stale-refusal replay; error text echo
`_same_origin` compares netloc only (Origin http://host passes, j_sec_02), mitigated by Secure +
SameSite=Strict cookie. Authority refusals echo raw Python messages (e.g. "invalid literal for
int()") in the 409 body (no secrets found). Not exploitable.

## Checked and SOUND (evidence)
- Authn: all 39 /api/cc routes (every method) refuse unauthenticated with 401, except the two
  public auth routes; /cc/store-preview 401; path tricks (//, %2e%2e, trailing slash, case, %00,
  traversal into static) 404/401; HEAD/OPTIONS 405; method-override headers/params ignored (j_sec_01).
- Privilege confusion: operator bearer on /api/cc/* and /cc/store-preview -> 401; owner cookie on
  /api/owner/*, /api/support, operator POSTs -> 401/403; operator token as cookie -> 401.
- CSRF: missing/forged/other-session token 403; cross-site Origin, Sec-Fetch-Site, Origin null,
  look-alike host 403 (j_sec_02). No CORS headers; preflight 405.
- Nonce: replay 409; skew +/-200 s 400; short nonce 400; 30/min per-session mutation limit works.
- Step-up: publication/activation approve, improvement/challenger approve, emergency resume,
  department unblock, all three recovery actions 403 STEP_UP_REQUIRED when the window is expired;
  5 bad step-ups revoke the session; non-string passphrases refused.
- Sessions: fixation impossible (server issues token; preset cookie 401); cookie HttpOnly, Secure,
  SameSite=Strict, __Host-; logout kills the old cookie; revoke-other kills it; idle >2 h and
  absolute expiry 401 (j_sec_03).
- Emergency: pause never raises phase; resume leaves a cap-breach-paused spend scope and an agent
  disabled for another reason alone (j_sec_04); kill -> effective phase shadow; bad scopes/types
  409; publication grant revoked at the boundary after revoke (j_sec_05).
- Sealed chain: approve goes through publication_authority.approve (sealed, chained, 24 h);
  revoke-before-execute makes `validate` return "grant revoked".
- XSS: UI has no HTML sink (h()/textContent only, safeUrl drops javascript:); DB-seeded script
  payloads in product title, incident, audit actor, owner action, ask answers come back as JSON
  strings only; store preview is built from code data, every field `_esc`, no inline script/handlers,
  CSP script-src 'self', frame-ancestors 'none', XFO DENY, no-store (j_sec_06, 08).
- CSP on /cc/*: default-src none, script-src self, style-src self, frame-ancestors none, nosniff.
- Service worker: /api never intercepted or cached, non-GET and cross-origin ignored, only listed
  shell files cached; no localStorage use except theme.
- Customer data: real write path (POST /api/support/messages + response_watch) leaves no buyer ref
  or message text in any CC GET, drill, notification, approval card or Ask answer (j_sec_07).
  Seeded known refs are redacted by the middleware even when embedded in incident/owner-action text.
  Note: only identifiers are scrubbed, not free text; a future writer that embeds buyer message text
  in an incident/audit detail would surface it (observed with synthetic seeds in j_sec_06).
- Ask Company: deterministic, no model; empty DB -> UNKNOWN, never CA$0; injection text in DB is
  returned as data. Minor: product match is substring ("why is p blocked?" answered for "xss-prod")
  and names the matched slug.
- Secrets: fuzz of every POST with 16 hostile bodies -> no 5xx, no token/passphrase/hash/cookie in
  any response, event row, audit row or captured log (j_sec_09).
- rc1-SEC regressions: unauthenticated mutating routes none; unauth plan-cycle?as_of=<script> 401
  (operator 400); dashboard/HTML routes escape a Job.last_error script payload; no unauth route
  leaks a seeded buyer ref (j_sec_11).
