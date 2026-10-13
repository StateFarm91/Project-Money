# Independent security review: release candidate 59675ef

- Reviewed: 2026-10-13 (UTC)
- Scope: `git diff 7bbbe72..59675ef -- brambleloop/src ops` (184 files, +15690/-566). I read
  the diff and the code around it at 59675ef. I ran no tests, made no production calls and
  executed nothing from the candidate.
- Method: I checked every new route against `app/security.py` default-deny, read the Private
  Laura path end to end (`private_context` -> `gateway/laura_register`), checked the spend and
  firewall call sites, the migration, the Etsy resolver backoff, the incident grouping and the
  new parsers. I also grepped the diff for Etsy write verbs and for secret patterns.
- Line numbers refer to 59675ef under `brambleloop/src/brambleloop/` unless a path says otherwise.

## Verdict: NO BLOCKER

All eight checks pass. I found no BLOCKER, HIGH or MEDIUM issue. There are two LOW findings
and four INFO findings, and none of them needs a change before release.

## Findings, ranked

### L1 (LOW): the private-reply purpose authorisation is checked, then reserved, in two steps
`gateway/laura_register.py:295-318`

`_purpose_committed_today` reads billed spend plus live reservations. The code compares that
total with `BRAMBLELOOP_LAURA_PRIVATE_DAILY_CAD`, and only after that does `check_budget_cad`
reserve. The read and the reservation are not atomic, so two owner turns sent at the same moment
can both pass the purpose cap. Each call is still reserved atomically against Laura's CA$0.50
agent day and against the monthly ceiling. The overshoot is therefore at most one estimate per
concurrent request, and it can never go above those ceilings. Optional fix: hold the purpose
check inside the reservation lock.

### L2 (LOW): the widen migration has no lock timeout
`core/migrate.py:71-110`, `:120`, called from `core/db.py:158-161` at startup

`ALTER TABLE ... ALTER COLUMN ... TYPE VARCHAR(n)` takes an ACCESS EXCLUSIVE lock. On Postgres a
larger length is a catalogue-only change with no table rewrite, but the lock must still wait for
any long transaction on `policy_snapshots`, and while it waits, startup waits too. These
properties are correct:
- **Widen-only.** It acts only when `model length > db length`. Narrowing, TEXT and unbounded
  VARCHAR are skipped.
- **Idempotent.** A second run finds an empty plan, and when two replicas run it at once the
  second ALTER is a no-op.
- **No other dialect.** SQLite is skipped.
- **Trusted identifiers.** Table and column names come from `Base.metadata`, not from input.

It is generic, so any future model-versus-database length drift is also widened at boot. Today
the only drift is `policy_snapshots.version` 40 -> 120 (`core/models.py:1477`). Optional
hardening: `SET LOCAL lock_timeout` before the ALTER.

### I1 (INFO): four new public read-only GETs
`app/main.py:2864` `/api/departments`, `:2929` `/api/etsy/surfaces`, `:4817`
`/api/funding/packets`, `:5062` `/api/verify/smoke`

None of these is in `OPERATOR_GET_ROUTES`. Each is a read-only aggregate with no writes, no
enqueue and no outbound call. `/api/verify/smoke` is listed in `PUBLIC_GET_NOTES`. The funding
packet exposes the monthly ceiling, month-to-date spend and run rate. The existing public
`/api/spend-report` and `/api/finance` already disclose the same figures, so this adds no new
exposure. Everything else new is gated:
- The two new POSTs (`/api/tester/agreement` `:1307`, `/api/insights/paste` `:3193`) do their
  own `opsauth.check`, and the gate already makes non-GETs default-deny.
- `/api/market-intel` and `/api/insights` were added to `OPERATOR_GET_ROUTES`.
- Every new `/api/cc/*` route (customers, store/*, checks/*) and `/cc/image-review` falls under
  the owner-session gate.
- External checks and `ads.set_limit` require step-up. `ads.set_limit` is capped at
  `CONSERVATIVE_CAPS`, and NaN or infinite values are refused.
- `/cc` -> `/cc/` returns a fixed relative Location and cannot be used as an open redirect.

There are no new `/api/cc/private/*` routes, no order or attribution routes and no webhooks.

### I2 (INFO): the OAuth callback now enqueues the Etsy follow-on jobs
`app/main.py:5221-5228`, `ops/on_demand.py:270-286`

This runs only when `result.ok` (the single-use state was verified). It enqueues
`etsy_taxonomy`, `mjs_scan` and `serp_capture` with an hourly idempotency key and an in-flight
check. These are existing job types: the worker re-authorises them and budget-checks them
before any call.

### I3 (INFO): the Insights paste key regex can backtrack quadratically
`intel/market_intel.py:344`

`_KEY`'s `(.+?)\s*$` is quadratic on a single line holding a long run of whitespace. The route
takes the operator credential only, and the input is capped at 20,000 characters (`main.py`
`/api/insights/paste`), so the worst case is a few seconds of CPU triggered by the operator.

### I4 (INFO): private replies share Laura's CA$0.50 agent day with the CEO briefing
`gateway/laura_register.py:314`

When the register is enabled, private replies draw on the same agent-day permission as
`laura.ceo_briefing`, so heavy private use can leave the briefing without budget for the day.
This is a design note, not a spend risk.

## Checks

### (1) Auth, TOTP and route default-deny: PASS
- `command_center/auth.py` is unchanged.
- Every new route sits behind the operator gate, the owner session (`/api/cc/` prefix or
  `OWNER_SESSION_PAGES`), or is one of the read-only public GETs listed in I1.

### (2) Private Laura: PASS
- **The reply switch defaults OFF.** It is on only when `BRAMBLELOOP_LAURA_PRIVATE_REGISTER` is
  exactly `"1"`. The context layer checks it at `private_context.py:211-213` and the call checks
  it again at `laura_register.py:281`.
- **The daily CAD defaults to 0.** `daily_authorisation_cad` returns 0 when the value is unset,
  unparseable, non-finite or ≤ 0 (`:166-174`). The call is then refused before any reservation
  (`:290`).
- **No paid-call journal or cache.** The call goes straight to `_send`, not `_guarded`, and it
  refuses when a job scope is active (`:276`). The routing task is `cacheable=False`
  (`gateway/routing.py`).
- **No content in billing or audit.** `_record` gets the pinned PROMPT ref and sha, not the user
  text. Errors are reduced to class name and HTTP status (`_sanitised`). The provider's error body
  is dropped. Every non-`ReplyUnavailable` exception becomes a fixed code with `from None`
  (`:262-267`), and `private_context._call` maps the rest generically.
- **Private values stay quoted.** They are revealed only in `private_context._laura_reply` and
  enter the prompt only inside delimited, neutralised data blocks.
- **Firewall call sites are intact.** The diff removes no `reject_private` call and adds new
  ones in:
  - `gateway/anthropic.check_budget_cad`
  - `spend_report.record`
  - `accounting/ledger.py`
  - `accounting/policy.py`
  - `gates/policy.py`
  - `authority/constitution.py`
  - `authority/dag.py`
  - `publication_authority`
  - `activation_authority`
  - `command_center/approvals.execute`
- **Key rotation is not exposed.** `store.rekey` has no route.

### (3) SHADOW and publishing: PASS
- **No Etsy write call.** A grep of the diff found no POST, PUT, PATCH or DELETE to Etsy.
- **Shop sync reads only.** `store_foundation/shop_sync.py` is limited to a GET allow-list
  (`ShopReader.get`, `:158-176`) authenticated with the api_key, and it redacts any credential
  Etsy echoes back.
- **The publication gate is tighter.** `publication_authority` now also requires the exported
  frame review (`:201-216`).
- **No phase gate or release gate was loosened.**

### (4) Spend: PASS
- **Ceilings are unchanged.** The diff changes no ceiling constant. The registry diff touches
  only a comment.
- **The new paid path reserves first.** `laura_register` reserves through `check_budget_cad`
  before `_send` and records billing exactly once on both the success and the failure paths.
- **On-demand checks add no paid path.** They only enqueue existing job types, which the worker
  budget-checks.
- **Ads authority stays capped.** `ads.set_limit` grants authority only, inside the code caps.

### (5) Secrets: PASS
- A pattern scan of the diff (API keys, AWS keys, private keys, DSNs with passwords, token
  literals) found nothing.
- `ops/db_backup/housekeep.sh` passes the S3 credentials to curl on stdin (`-K -`), not on its
  command line, and has no `set -x`.
- Nothing prints a secret value: `enablement()` reports names and booleans only.

### (6) Migration: PASS, with L2

### (7) Etsy resolver backoff and incident grouping: PASS
- **The resolver backoff is correct.** `integrations/etsy_shop_binding.py:179-206, 226-241`:
  - It is shared across processes because it reads its own audit rows.
  - A run of failures ends at the first `etsy.shop_resolved`.
  - The wait is 60 s × 2^(n-1), capped at 3600 s.
  - A clock-skewed row cannot extend the wait.
  - Both `refused` and `error` count as failures, while `no_token` does not.
  - A new grant does not reset the backoff, so binding can be delayed by up to an hour, as the
    code documents.
- **The earlier L1 is mitigated.** The grouped record now states how many distinct signatures
  it merges (`laura/agency/briefing.py:355, 371-374`).

### (8) New input parsing: PASS
- There are no webhooks in the diff.
- The ledger change is only the firewall call.
- The tester agreement validates its types and lengths.
- The Insights paste is size-capped and needs the operator credential (see I3).
- `/api/cc/store/image/{build}` and `/store/pdf/{slug}` only serve values on an allow-list
  (`owner_store.py:238-264`), so there is no path traversal.
- The image review page HTML-escapes everything it renders (`_esc`).
