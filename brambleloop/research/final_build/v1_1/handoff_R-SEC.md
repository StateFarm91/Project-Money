# Handoff: repair lane R-SEC (audit ddf9c6e security findings)

Branch `claude/r2-SEC` from `claude/visual-investigation` @ d53a760. Phase stays shadow; nothing
deployed, no Railway mutation, no network.

| finding | status | fix |
|---|---|---|
| M1 owner lockout | COMPLETE | `auth.client_ip`: X-Forwarded-For ignored unless `BRAMBLELOOP_TRUSTED_PROXY_HOPS=N` (N-th entry from the right) or `BRAMBLELOOP_CLIENT_IP_HEADER`; rate-limit key is the address only (UA is attacker-chosen). Only `BAD_CREDENTIALS` refusals count (429/CSRF/400 never extend a lock). Global limit still refuses unknown devices before verification, but a trusted-device cookie (`__Host-bl_dev`, hash stored, 90 d, limited 5 fails/15 min per device) and a single-use 15-min recovery code (`POST /api/owner/cc/login-recovery`, operator bearer via the default-deny gate) are exempt. Passphrase/TOTP always required. |
| M2 timestamp nan/inf | COMPLETE | `math.isfinite` check (fail closed); import-time guard `NONCE_RETENTION > 2 x skew`. |
| M3 block never-pause depts | COMPLETE | one rule `emergency.never_paused_refusal`, used by pause, the CC block route (409) and `autonomy.orchestrator` (an existing block row on those departments is reported as `ignored_block`, not obeyed). |
| L1 evidence gate | COMPLETE (publication) | `approvals._require_publication_evidence`: any gated section FAIL/UNKNOWN or an unreadable packet refuses `publication.approve` server-side. activation.approve unchanged: no evidence packet exists for it; `activation_authority.snapshot` already requires certified frames + verified publication files. |
| L2 revoke unknown id | COMPLETE | 404 `NOT_FOUND` unless the id is an APPROVED row of that ledger by its principal; nothing sealed. |
| L3 origin / echo | COMPLETE | Origin compared as (scheme, host, port): https on the Host (http only for loopback over http) or exactly `BRAMBLELOOP_PUBLIC_ORIGIN`. Refusals map to stable text; raw exception text goes to the server log and the `cc_security_events.detail`. |

## Deployment action (integrator/owner, not done here)
Set `BRAMBLELOOP_TRUSTED_PROXY_HOPS=1` on Railway (one edge proxy). Without it every client is
the proxy address, so the per-client limit is shared (fail-safe, but a new device can be held
at 429 by 5 wrong guesses; trusted devices and recovery codes are unaffected).

## Tests
New: `tests/test_r2_security_{login_lockout,freshness,department_block,actions}.py` (+
`tests/r2_security_harness.py`). Verified failing on ddf9c6e (0/5, 1/3, 0/2, 0/4; the passing
one is the retention guard) and passing here. `tests/test_v11_cc_actions.py`'s pause test now
supplies a fully passing evidence packet (it relied on the L1 gap); no assertion removed.
