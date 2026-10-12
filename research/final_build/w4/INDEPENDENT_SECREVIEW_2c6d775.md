# Independent security review: release candidate 2c6d775

- Date: 2026-10-11 (UTC). Reviewer: an independent security reviewer who did not write this code.
- Scope: `git diff 7421ef6..2c6d775 -- brambleloop/src ops brambleloop/Dockerfile brambleloop/railway.json`
  (29 files, +824/-149). The baseline is the independent re-audit of 7421ef6
  (`origin/claude/w4-REAUDIT:research/final_build/w4/INDEPENDENT_REAUDIT_7421ef6.md`, which
  found D-1, L-1, L-2 and L-3). The Dockerfile and `railway.json` are unchanged in this delta.
- Mode: read-only on the candidate. Work was done in a detached worktree at 2c6d775. No
  Railway or Etsy calls were made, nothing was spent, and no secret values were read.
- Tests were run one at a time, each with a private TMPDIR that was deleted afterwards:
  - `tests/test_w4_auditfix_cc_auth.py`: 9/9
  - `tests/test_w4_auditfix_ceiling.py`: 0 failing
  - `tests/test_route_auth_default_deny.py`: 7/7
  - `tests/test_w4_ccgap_pdfium.py`: 2/2
  - Ad hoc: `create_all()` and migrate run twice on a scratch SQLite DB (126 tables). The
    second pass made no changes, and no index name is longer than 63 characters (the
    Postgres name limit).
- Line numbers refer to 2c6d775.

## Verdict: NO BLOCKER

I found no release-blocking defect. Each of the four re-audit items is fixed or mitigated as
claimed. The delta adds no unauthenticated route, no new mutating route, no spend or
ceiling-raising path, no Etsy write and no customer-message path. Only one LOW and some
INFO items remain.

| Area | Result |
|---|---|
| CC auth, session, CSRF and step-up | PASS. No auth primitive was weakened. The one new route is operator-gated |
| L-1 TOTP replay | FIXED. Code optionality remains (LOW-1, by design, now visible) |
| L-2 login reservation race | FIXED |
| D-1 NaN spend ceiling | FIXED, plus the same pattern hardened at the agent and ads levels |
| Spend and ads authority | PASS. No new path. `ads.campaign` only got stricter |
| Shadow mode | PASS. No Etsy write and no outbound message added |
| PDFium lock | PASS. No deadlock path. INFO-2 covers serialisation |
| Release record and deploy guard | PASS. No weakening. INFO-3 covers the optional `full_log` |
| Migration | PASS. Additive only (indexes), idempotent |
| Secrets in logs and API responses | PASS |
| XSS and phone layout in new views | PASS |

## Findings, by severity

### LOW-1: TOTP is still optional in code (re-audit L-1, first half; carried over and documented)
`app/command_center/auth.py:219-224` (`verify_totp`) and `:249-265` (`verify_owner`). When
`BRAMBLELOOP_OWNER_TOTP_SECRET` is unset, login and step-up need only the passphrase. The
candidate does not change this. It now reports it: `second_factor_status()` (`auth.py:186`)
appears in `/api/cc/auth/status` and on the Account tab, as booleans and a variable name, never
the secret.

*Exploit scenario.* Someone who steals the owner passphrase (phishing, shoulder-surfing or
password reuse) gets a full owner session, and step-up as well, because step-up re-verifies
the same factor. That covers authority grants and emergency resume.

*Action.* This is an owner configuration item, not a code blocker. Confirm the production
variable is set. The Account tab now shows "passphrase only" when it is not. Consider failing
readiness when the variable is unset outside development.

### INFO-1: the L-2 fix is correct; the global lockout DoS is unchanged
`auth.py:512-561` and `api.py:77-108`. The attempt is committed as a wrong-credential row
before PBKDF2 runs. The limit is then counted including that row (`>` rather than `>=`). Each
concurrent request therefore sees every reservation committed before its own count, so at most
the limit's worth can pass, in one process or across workers. A rate-limited reservation is
withdrawn, so it does not extend the lockout. A success withdraws its reservation. A failure
turns it into the single failure record. A store error fails closed: a reserve error returns
503, and a verification exception counts as a failure.

One side effect: rows still being verified also count toward the global limit of 20. An
attacker who fires a burst of wrong guesses holds the owner (without a trusted-device cookie)
out for the window. That was already true once the guesses had finished, so the DoS is the
same as before. The trusted-device cookie and the operator-minted recovery code still bypass
it.

### INFO-2: the L-1 replay fix is correct
`auth.py:236-265`. The matched RFC 6238 step is inserted as `cc_nonces(nonce="totp:<step>")`.
The `nonce` column is `unique=True` (`models.py:50`). A `:` cannot appear in a client nonce
(`_NONCE_RE`, `auth.py:89`), so the two kinds cannot collide. An `IntegrityError` means a
replay, and that is atomic across workers. The step is consumed only after the passphrase has
verified, so a wrong guess cannot burn the owner's code. Rows outlive the 90 s window, because
`NONCE_RETENTION` is 10 min and a module-load assertion enforces it. Both route callers
(`api.py:96`, `api.py:140`) pass `db`. Nothing else calls `verify_owner`.

Minor usability effect: the owner cannot reuse the login code for a step-up within the same
30 s step.

### INFO-3: the release record's `full_log` pin is optional (no weakening)
`ops/deploy_guard.py:323-338`. `_full_log_problems` returns `[]` when the record has no
`full_log` key, so removing the key skips that check. This is not a regression. The guard's
pass/fail evidence is still the summary log under `release/`. It is sha256-pinned and must
contain `RUN ID`, `GIT SHA` and a `TOTAL ... failing 0` line, all of which survive
`summary_log` (`:508`), which keeps unindented lines. The record still has to match the tree
digest and be an ancestor of the candidate.

As before, records are hash-chained but not signed. Anyone with push rights could regenerate
a whole consistent record, so integrity rests on git write access (an existing design limit).
`summary_log` and `portable_log` only remove content (session markers and absolute paths)
before a file ships in the image.

### INFO-4: PDFium lock, no deadlock, bounded DoS
`visual/contents_frame.py:46, 104, 187`. A process-wide `RLock` is held only around PDFium
calls (open, page count, render), and the document is closed inside the lock. Nothing inside
takes another lock or touches the DB, so no lock-order deadlock is possible. The `RLock` is
also re-entrant. `contents_frame.py` is the only importer of `pypdfium2`
(`test_every_pdfium_use_is_under_the_lock` enforces this).

The input is this shop's own certified release PDF, not user upload. A slow render only
serialises other CONTENTS-frame renders. The launch packet that triggers them is single-flight
and auth-gated.

### INFO-5: indexes are now created on every boot
`core/migrate.py:96-112` (L-3 fix). This is additive only, with no drops or type changes and
no model or column changes in the delta. It checks before acting and is idempotent (verified
by running it twice). A Postgres `CREATE INDEX`, which is not `CONCURRENTLY`, on a large table
would block writes on that table during boot. The production tables are small, so this is
operational only.

## Area notes (verified, no finding)

- **New routes.**
  - `GET /api/launch/packet` (`app/main.py:4547`) is listed in `security.OPERATOR_GET_ROUTES`
    (`security.py:152`), so it needs the operator credential. `test_route_auth_default_deny`
    passes, so default deny still holds.
  - The changes in `api.py` add no new route. They add the login reservation, the TOTP `db=`
    argument, `second_factor` in status, and `live_work` on the existing owner-gated
    `/api/cc/completion` GET.
  - The new `company.py` and `tabs.py` functions (`release_identity`, `release_artefact`,
    `visual_pipeline_live`, `live_company_work`, `reconcile_owner_actions`, `slo_card`,
    `agents_card`) are read-only SELECTs or dict reshaping, served on existing owner-gated
    GETs. There is no new POST and no new step-up action, and the CSRF, nonce and step-up code
    is unchanged.
- **Spend.**
  - `monthly_ceiling_cad` (`gateway/anthropic.py:158`) now treats a NaN, inf or non-positive
    env value as "use the authorised ceiling". The env can still lower the ceiling, never
    raise it.
  - `_decide_and_reserve` refuses outright on a non-finite ceiling (`:502`).
  - A non-finite per-agent permission reads as 0, so the agent is refused (`:237`).
  - `ads.campaign` refuses a non-finite amount or headroom (`runtime/growth_ops.py:530`). It
    still needs `ad_authority`, then `paid_media.authorise_spend`, which refuses below
    PRODUCTION and has no ad integration.
  - No code path raises a ceiling or grants authority without the existing owner step-up.
- **Shadow mode.**
  - The delta touches no Etsy client, publish, activate or messaging code.
  - In `providers.py`, the only change is a retry with the DB facade on a known
    `AttributeError` message.
  - `emergency.py` and `ask.py` gained only timestamps.
- **Secrets.**
  - No new env value is echoed. `second_factor_status` returns booleans and the variable name.
  - The login failure path now raises `CCRefused` with a fixed message. The reservation row
    stores the hashed client key, never the passphrase or code.
  - `release_identity` reads only the boot record's sha and `recorded_at`.
- **XSS and phone.**
  - Every new view element is built with `h(...)` (text nodes), and the diff adds no
    `innerHTML`.
  - Server strings such as `release_artefact.label`, `reason`, job types and the `why` text
    render as text.
  - The CSS adds `overflow-wrap` for long tokens at 390 px, which only reduces overflow.
  - The `maxlength` to `maxLength` change sets the DOM property correctly.

## Blockers

None.
