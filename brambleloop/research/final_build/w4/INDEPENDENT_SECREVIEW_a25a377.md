# Independent security review: release candidate a25a377

- Reviewed: 2026-10-18 (UTC)
- Candidate: `a25a3774bc6d80c8abc3a82cbc78a472c8cf94b5`. The branch tip
  `origin/claude/final-candidate-a25a377` is `1b21e81c`, which adds only the release record;
  `git diff a25a3774..1b21e81c -- brambleloop/src ops` is empty.
- Scope: `git diff 59675ef..a25a3774 -- brambleloop/src ops` (23 files, +1583/-38). The delta
  holds:
  - the INTEG3 fixes for the two suites that failed freeze 2 (`6cd2fcb9`, `7584ba8d`);
  - the FMCLOSE merge `13aed5e`: the Etsy webhook receiver, the order ledger and attribution
    route, accounting activity, the channel comparison, the sales-channel inventory, the
    first-ten cohort and the event wakes;
  - the VISROLE merge `52b702d`: role-appropriate frame review;
  - the growth-ops offsite fix (`a25a3774`);
  - the F-575 ingest-to-statement-lines revert, which nets to zero in `src`.
- Method: I read the whole diff and the code around it at a25a3774. I checked:
  - every new route against `app/security.py` default-deny;
  - the webhook verification path line by line;
  - the VISROLE classifier, its verdict and how its output reaches `frame_review_state`;
  - the budget path of `describe_image`.

  I also grepped the diff for Etsy write verbs, SQL text, spend ceilings and secret patterns.
  I ran no candidate tests, made no production calls and executed no candidate code. One
  stdlib-only Python check confirmed how `hmac.compare_digest` behaves (see L2).
- Baseline: `INDEPENDENT_SECREVIEW_59675ef.md` (NO BLOCKER). Line numbers below refer to
  a25a3774 under `brambleloop/src/brambleloop/` unless a path says otherwise.

## Verdict: NO BLOCKER

There is no BLOCKER or HIGH finding. I found one MEDIUM (an unauthenticated write
amplification on the webhook refusal path), two LOW findings on the webhook input path and
four INFO notes. None of them weakens authentication, publication, spend or Private Laura.

The checks that matter all pass:
- HMAC verification is constant-time.
- The skew limit is enforced.
- Replays are refused.
- The receiver fails closed when the secret is unset.
- No Etsy write was added.
- VISROLE keeps every veto, and an unknown role is treated as photographic.

M1 should be fixed before `ETSY_WEBHOOK_SECRET` is configured and the endpoint is registered
with Etsy. Until then it is a nuisance-level DoS surface, not a gate bypass.

## Findings, ranked

### M1 (MEDIUM): each unauthenticated webhook refusal writes an audit row, with no rate limit, and a public GET scans them all
`integrations/etsy_webhooks.py:202-211, 222-224, 292-296`; `app/main.py:2957, 2961-2971`

`POST /api/etsy/webhook` is public by design (`app/security.py:127`). Every refused delivery
calls `_refused`, which inserts one `AuditLog` row (`etsy.webhook_refused`). That includes
`not_configured`, so it is true today, while no secret is set. The route has no rate limit
(the only limiter in `app/` is the owner login's). Anyone can therefore grow `audit_log` at
request rate.

The public `GET /api/etsy` then calls `etsy_webhooks.summary`, and `summary` iterates over
every refused row in Python (`:293-296`). That read gets slower in step with the flood. The
impact is limited to storage and availability: a refusal enqueues nothing and stores no
delivery, and authentication is not bypassed.

Fix (small):
- Count refusals in one counter row per reason (an upsert), or sample or rate-limit the audit
  write per source.
- Make `summary` aggregate refusals in SQL (`GROUP BY` on the reason) instead of in Python.

### L1 (LOW): the 64 KiB body cap is checked only after the whole body is buffered
`app/main.py:2969`; `integrations/etsy_webhooks.py:58, 162`

The route calls `await request.body()` before `receive`, so an unauthenticated client can make
the single-worker uvicorn (`railway.json`) buffer an arbitrarily large body before
`MAX_BODY_BYTES` refuses it. The cap does stop parsing and HMAC work on an oversized body, and
the size check runs before the HMAC.

This is the same pattern as the other public POSTs, such as the login's `request.json()`, and
the app has no global request-size limit. Fix: refuse on `Content-Length` above the cap, and
read `request.stream()` with a running cap. Optionally, add a global body-size middleware.

### L2 (LOW): a non-ASCII signature header raises an uncaught TypeError (a 500, not a refusal)
`integrations/etsy_webhooks.py:176-177`

`hmac.compare_digest(str, str)` raises
`TypeError: comparing strings with non-ASCII characters is not supported` when either string
contains non-ASCII characters (I confirmed this with the stdlib). Starlette decodes header
bytes as latin-1, so a `webhook-signature: v1,é` header reaches `compare_digest` as non-ASCII.
`receive` catches only `WebhookRefused`, so the request ends in a 500 with a server-side
traceback and no refusal is counted.

This is not a bypass: an exception never accepts. Fix: compare bytes
(`hmac.compare_digest(want.encode(), o.encode("latin-1"))`), or catch the error and refuse
with `bad_signature`.

### I1 (INFO): the refusal body and `/api/etsy` say whether the secret is configured
`integrations/etsy_webhooks.py:114-124, 224, 275`

A refusal returns its reason code and explanation, for example `not_configured` with a 503.
Public `GET /api/etsy` reports `webhooks.configured` as a boolean. Neither discloses the
secret, its length or the expected MAC: the `why` strings are fixed text, and the `skew` and
`event_type` values in them come from the request itself. This is acceptable for an endpoint
whose existence is public.

### I2 (INFO): some VISROLE role checks pass on the absence of deterministic findings
`visual/frame_role.py:140-145, 170-177, 208-211`

These checks pass when the deterministic auditors found nothing on the frame:
- `data_matches_record` passes when Asset Truth and the frame plan raise nothing for the
  frame, and every record label is drawn.
- `scale_not_misleading` passes on a non-size frame when there is no Asset Truth size or scale
  code.
- `disclosure_present` passes for a non-twin non-photo frame from its recorded simulated
  provenance kind.

These checks rest on the deterministic auditors, which matches the non-negotiable that
deterministic validation wins. They are not model passes. `classify` (`:67-74`) reads only
the code-assigned `asset_class` and `role` from `publish/listing_assets.py` (`:271-551`):
- `has_model` forces photographic.
- Anything not in `_BY_PLAN` falls through to `PHOTOGRAPHIC`.
- Nothing the model returns, and nothing a request supplies, can choose the lighter path.

`INFOGRAPHIC` and `PATTERN_PREVIEW` match any frame role (`"*"`). That is safe while those
classes are assigned only by the deterministic frame builders. A future code path that labels
generated imagery with those classes would skip the realism checks, and a test should pin
that.

### I3 (INFO): the attribution evidence string has no length cap
`app/main.py:4054-4087`; `finance/sources.py:69-114`

`POST /api/orders/attribution` is protected by the operator credential: it is in neither
`PUBLIC_MUTATING_ROUTES` nor the public GETs, and it calls `_operator_read_refusal`. The
source is checked against `ATTRIBUTABLE`, and empty evidence is refused. `evidence` is stored
in `Order.detail` at whatever length it is sent. That is operator-only, so this is a
hygiene note. A cap of about 2,000 characters would match the other operator inputs.

### I4 (INFO): the event-wake scan reads every order on each tick
`autonomy/event_wakes.py:68-74, 141-146`

`_observe` loads every order's `detail` every 15 minutes, and each set-type cursor is cut to
2,000 entries. Past 2,000 refunded or reviewed orders, the same "new" set reappears on every
scan. The idempotency key (`wake:<kind>:<fp>`) collapses those into one job, so there is no
runaway enqueue. This is a performance note only. Every routed job type is an existing,
unprotected safe job (`:40-51`).

### Carried from 59675ef
- **L2 (lock timeout): fixed.** `core/migrate.py:106-108` now runs
  `SET LOCAL lock_timeout = '5s'` inside the ALTER transaction. The statement is a constant.
- **L1 (Private Laura purpose check, then reserve): unchanged.** The delta does not touch
  `gateway/laura_register.py`.

## Checks

### (1) New routes: auth, scope and CSRF: PASS
- `GET /api/orders/ledger` (`main.py:4042`):
  - It is in `OPERATOR_GET_ROUTES` (`security.py:139`) and in `CUSTOMER_DATA_ROUTES`.
  - It calls `_operator_read_refusal`: 503 while the credential is not configured, 401 when it
    is wrong.
  - It is read-only.
- `POST /api/orders/attribution` (`main.py:4054`):
  - It is not in `PUBLIC_MUTATING_ROUTES`, so the application-wide gate default-denies it.
  - It also checks the operator credential itself.
  - It parses JSON with a type check, and the source is on an allow-list.
- `POST /api/etsy/webhook` (`main.py:2961`) is the only new public mutating route, and it is
  justified at `security.py:127-132`.
- CSRF: both new POSTs authenticate with an `Authorization` header or an HMAC, not with an
  ambient cookie, so cross-site form posts carry no credential. No new `/api/cc/*` route was
  added.
- `GET /api/etsy` gains the `webhooks` summary, which holds counts and booleans only (see M1
  and I1).

### (2) Etsy webhook receiver: PASS, with M1, L1 and L2
| Property | Where | Result |
|---|---|---|
| HMAC-SHA256 over `id.ts.raw_body`, keyed by the Base64-decoded `whsec_` secret | `etsy_webhooks.py:174` | PASS |
| Constant-time compare, any of several `v1,` entries accepted | `:176-177` (`hmac.compare_digest`) | PASS (see L2 for a non-ASCII header) |
| Body parsed only after the MAC matches | `:179-184` | PASS |
| Skew limit ±300 s in both directions; the timestamp is inside the MAC | `:164-173` | PASS |
| Replays refused: within the window by the UNIQUE `webhook_id` (`:77`, duplicate answers 200 and writes only a counter, `:230-237`); outside it by skew | | PASS |
| Concurrent duplicates resolve through the job idempotency key `etsy.webhook:<id>` and the unique insert falling back to `duplicate` | `:238-263` | PASS |
| Secret unset or malformed refused with 503 before any header is read; the receiver fails closed | `:112-124, 153` | PASS |
| The secret is never echoed or logged; the body is never stored (sha256 only) | `:83, 195, 207-209` | PASS |
| Body size bounded (64 KiB) | `:162` | PARTIAL (L1: bounded after buffering) |
| Foreign `shop_id` refused when `ETSY_SHOP_ID` is set | `:189-192` | PASS |
| A verified delivery is only a wake: it enqueues `commerce.orders_ingest`, nothing from the payload is written to an order, so a valid but stale payload cannot invent a sale | `:240-243` | PASS |

### (3) No Etsy writes; SHADOW and publication gates: PASS
- **No Etsy write call.** A grep of the delta finds no Etsy write call (POST, PUT, PATCH or
  DELETE). The only new outbound effect is the existing authenticated receipt read, run by the
  ingest job.
- **The FMCLOSE additions read or record only.**
  - `seo/proposals.py:144-157` only adds an `edit_hold` field. `writes_to_etsy` stays `False`.
  - `first_ten.edit_hold` can only hold an edit, never release one.
  - `sales_channels.observe` only raises P1 incidents for unreadied channels.
  - `activity`, `channel_comparison` and `order_ledger` are reads.
- **Publication still requires an all-`clear` review.** `frame_review_state`
  (`runtime/release.py:1667`) still requires every frame to be `clear` and
  sha-bound. No phase gate, release gate or publication gate was loosened.

### (4) VISROLE: PASS (I2)
- **The role is deterministic.** `classify` reads `has_model`, `asset_class` and `role` only,
  and an unknown role falls through to `PHOTOGRAPHIC` (`frame_role.py:67-74`). The model is
  never asked to classify.
- **Photographic frames keep the full check.** They still go through `inspect_image` and
  `gate` (`release.py:1598-1601`).
- **Non-photo frames are described blind and held to the five role checks**
  (`release.py:1582-1597`).
- **Unanswered is never passed.**
  - An unanswered or missing role check, or no description at all, gives `unjudged`
    (`frame_role.py:226-230`).
  - An `unclear` answer on third-party marks is `None` (`:181-185`).
  - Missing layout or type-size data is `None` (`:134-136, 149-158`).
  - An exception gives `unreviewed` (`release.py:1602-1606`).
- **Every veto still blocks.** Semantic problems, marks or a failed role check give
  `blocked`, and each `blocked` adds at least one blocking reason (`release.py:1645-1655`).
- **The vetoes before review are unchanged.** The unclaimed-role veto and the image-vision
  gate run before classification (`release.py:1558-1570`).
- **The hero is still identified.** A twin-render hero still goes through identification and
  the grid check (`:1621-1644`) and must draw "not a photograph" (`frame_role.py:200-207`).

### (5) Spend: PASS
- **No ceiling constant changed.** `SMALL_SUPPLIER_CAD = 30000` (`finance/accounting/activity.py:27`)
  is the GST/HST small-supplier alert threshold, not a spend ceiling.
- **Non-photo frames now cost less.** They call `describe_image`, which reserves through
  `gw.check_budget` before every `provider.see` and releases the reservation on failure
  (`visual/inspect.py:518-543`). It is one call where `inspect_image` made two, so per-frame
  spend goes down.
- **Ads spend is unchanged.** The growth-ops change (`runtime/growth_ops.py:406-432`) only
  changes how the offsite share is read: an unread order is no longer counted as "no", and
  the attributed count is kept. It adds no spend path.

### (6) Private Laura: PASS
- No file under `gateway/laura_register.py`, `app/command_center/private_context.py` or the
  routing changed.
- The switch is still `BRAMBLELOOP_LAURA_PRIVATE_REGISTER`, which must be exactly `"1"`, so it
  defaults OFF.

### (7) Secrets: PASS
- A pattern scan of the delta found nothing: Anthropic and AWS keys, private keys, `whsec_`
  literals, DSNs with passwords and api_key literals.
- The secret is read only from the environment (`etsy_webhooks.py:218`). A test helper signs
  with a caller-supplied secret, and none is embedded.

### (8) SQL and input parsing: PASS
- **No user input reaches SQL as text.** All new queries use the SQLAlchemy ORM with bound
  parameters. The only `text()` is the constant `lock_timeout`, and the existing widen ALTER
  takes trusted metadata identifiers.
- **The parsing is strict.**
  - The webhook parses only after the MAC and requires a JSON object.
  - Its event type is on an allow-list, `webhook-id` is capped at 200 characters and
    `resource_url` at 500.
  - The timestamp is an `int` with OverflowError and OSError handled.
- **The other new parsers are safe.**
  - The attribution route uses an allow-list for the source (I3).
  - `sales_channels.channel_for` coerces `receipt_type` to an int or an `unrecognised:` label,
    and the incident signature is capped at 200 characters.
