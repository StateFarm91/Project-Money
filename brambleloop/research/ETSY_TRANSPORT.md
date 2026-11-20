# The Etsy transport: what was built, what was exercised, and what is still a reading

**Written:** 2026-09-25 (UTC). **Phase:** SHADOW. **By:** the commerce/Etsy department,
working in an isolated worktree.

**The one sentence that matters: there are no Etsy credentials in this environment, so not one
write has ever reached Etsy.** Everything below distinguishes, claim by claim, between what a
real request to `openapi.etsy.com` established, what a local server built from Etsy's own
document established, and what is still only a reading of that document. The predecessor's
audit (`SHOP_READINESS.md`) is not repeated here; this is what happened to the gaps it found.

---

## 1. The gap, and what closing it required

`SHOP_READINESS.md` found three launch blockers in the write path. Verified independently
before any code was changed, by searching `src/` on 2026-09-25:

| Finding | Verified |
|---|---|
| `uploadListingImage` appears **zero** times in `src/` | yes |
| `updateListing` appears **zero** times in `src/` | yes |
| `integrations/http.py` sends `application/json` | yes -- `json.dumps`, `Content-Type: application/json`, for every request |

Etsy's own sentence, from its published API description: *"Setting a `draft` listing to
`active` will also publish the listing on etsy.com and requires that the listing have an image
set."* So the first finding is not a missing feature. It means **every draft this system could
create was permanently unactivatable**, and the shop would have opened with zero live listings
while every upstream gate -- certificate, Asset Truth, policy, thumbnail, parity -- passed.

Read on 2026-09-25 from `https://www.etsy.com/openapi/generated/oas/3.0.0.json` (fetched,
HTTP 200, document version 3.0.0) and
`https://developer.etsy.com/documentation/essentials/authentication/` (fetched, HTTP 200).
Both are Etsy's words about Etsy.

### What the document says, endpoint by endpoint

| Operation | Method and path | The **only** media type Etsy lists | Scope |
|---|---|---|---|
| `createDraftListing` | POST `/shops/{shop_id}/listings` | `application/x-www-form-urlencoded` | `listings_w` |
| `updateListing` | **PATCH** `/shops/{shop_id}/listings/{listing_id}` | `application/x-www-form-urlencoded` | `listings_w` |
| `uploadListingImage` | POST `/shops/{shop_id}/listings/{listing_id}/images` | `multipart/form-data`, binary in a part named **`image`** | `listings_w` |
| `uploadListingFile` | POST `/shops/{shop_id}/listings/{listing_id}/files` | `multipart/form-data`, binary in a part named **`file`** | `listings_w` |
| `updateListingInventory` | PUT `/listings/{listing_id}/inventory` | `application/json` | `listings_w` |
| `getListing` | GET `/listings/{listing_id}` (`includes=Images`) | -- | api key only |
| `deleteListing` | DELETE `/listings/{listing_id}` | -- | `listings_d` |

Four things in that table were not in the previous reading and each one is a defect the old
code would have hit:

1. **`updateListing` is a PATCH**, not a PUT or a POST.
2. **The two upload endpoints disagree about the file's field name.** The old transport
   hard-coded `file` for every upload, so a listing image sent through it is a well-formed
   request in which Etsy finds no image.
3. **Not every Etsy write is form-encoded.** `updateListingInventory` really is JSON. A
   transport with one body format is wrong for Etsy whichever format it picks, so the fix is
   per-endpoint encoding rather than swapping JSON for forms globally.
4. **`updateListing` has no `price` property.** Sending a price to it is accepted as an
   unknown form field, changes nothing, and returns 200. Price lives in the inventory
   endpoint. This is the single best argument for read-back verification in the whole API.

---

## 2. What was built

| Thing | Where |
|---|---|
| Listing image upload, binary in a part named `image`, rank and alt text, refusing empty bytes and non-image formats | `integrations/etsy.py:EtsyClient.upload_image` |
| Draft update: PATCH, form-encoded, whitelisted against Etsy's 24 writable fields, refusing `price` and `state` | `integrations/etsy.py:EtsyClient.update_listing` |
| Activation, implemented and triple-gated: phase, owner authority, and a Launch-0 authorisation passed to the call | `integrations/etsy.py:EtsyClient.activate` |
| Authenticated reads: shop, user, listing with images, listing images | `EtsyClient.get_shop / get_me / get_listing / get_listing_images` |
| Deletion that reads the listing back and refuses unless its state is the one expected | `EtsyClient.delete_listing` |
| `publish()` now takes listing images, uploads them, and reports `activatable` separately from `published` | `EtsyClient.publish`, `PublishOutcome.activatable` |
| Three authorities (READ / DRAFT_WRITE / ACTIVATE) in place of one publish-or-refuse gate | `integrations/etsy.py:Authority`, `refusal_for` |
| Per-endpoint encoding: form, multipart and JSON channels, with the Content-Type set from the channel used | `integrations/http.py:UrllibTransport` |
| OAuth 2.0 authorization-code grant with PKCE, refresh grant, rotation, expiry skew, scope checking, redacted logging | `integrations/etsy_oauth.py` |
| Read-back verification: Money normalisation, the `type` -> `listing_type` rename, and `NOT_RETURNED` as its own verdict | `integrations/etsy_verify.py` |
| The shadow-safe exercise: ping, read shop, create draft, upload image, update, read back, verify, delete | `integrations/etsy_probe.py` |
| A local server modelling Etsy's contract, with Etsy's real error strings | `tests/fake_etsy.py` |
| 27 checks | `tests/test_etsy_transport.py` |

### The authority change, and why it is not a loosening

The client had one gate: phase, then owner authority, then credentials. That was right while it
could only do one thing. It was wrong in both directions once it could do five:

- **Too strict to be useful.** A shop read, a draft, an image upload and a draft deletion are
  invisible to every buyer and cost CA$0. Refusing them in SHADOW means the first time this
  code runs against Etsy is the day the shop opens, which is the exact risk the module was
  written to avoid.
- **Too loose where it mattered.** `create_draft` and activation sat behind the same
  permission, so any authority that allowed a draft allowed publishing.

Now: `READ` needs a credential and nothing else. `DRAFT_WRITE` needs a credential and either
full publish authority or an explicit `shadow_writes_authorised` grant, which a call site must
pass and which the probe only sets when the operator has set `ETSY_SHADOW_WRITE=1`.
`ACTIVATE` needs the publishing phase, the owner's authority **and** a Launch-0 string passed
to that call -- a per-call argument, because a job configured once and forgotten cannot have
one. `refusal()`, the gate `runtime/pipeline.py` asks about, is unchanged, and SHADOW still
refuses to publish.

### OAuth, and why a static token was a day-two failure

Etsy's access token has "a functional life of 1 hour" and the refresh token lasts 90 days,
**issuing a new refresh token on every refresh**. `Credentials.from_env` read a static
`ETSY_ACCESS_TOKEN`, so the old system worked for up to an hour after a human pasted a token
and then returned 401s that look exactly like a revoked app -- failing on day two, with nobody
watching, rather than on day one.

`TokenProvider` refreshes 120 seconds before expiry, hands the rotated refresh token to an
`on_refresh` callback (never a file in this repository), and refuses an operation whose scope
Etsy did not grant -- checked against the `scope` field Etsy returns, because Etsy's granted
scope "may be a subset of the requested scopes". A token set read from the environment with no
stated expiry is treated as **already expired**, which costs one refresh at start-up and never
sends a dead token.

One discrepancy is recorded rather than resolved: Etsy's authentication page gives the token
endpoint as `https://api.etsy.com/v3/public/oauth/token`, and Etsy's OpenAPI description gives
`https://openapi.etsy.com/v3/public/oauth/token`. Both are Etsy's. The code sends to the first
and retries the second on a 404. **Neither has been exercised.**

---

## 3. Evidence: what was actually exercised

### 3.1 EXERCISED AGAINST THE REAL ETSY API

Three live requests to `openapi.etsy.com` on 2026-09-25, through this system's own transport
(`http.probe_live`), not through curl. They create nothing, change nothing, need no OAuth token
and cost CA$0.

| Request | Result |
|---|---|
| GET `/v3/application/openapi-ping`, no `x-api-key` | **HTTP 403** `{"error": "Invalid API key: should be in the format 'keystring:shared_secret'."}` |
| Same, `x-api-key: <well-formed but invalid>:<invalid>` | **HTTP 403** `{"error": "API key not found or not active, or incorrect shared secret for API key."}` |
| POST `/v3/application/shops/0/listings` with a JSON body and an invalid key | **HTTP 403**, the same API-key error |

What this proves, and it is more than it looks:

1. **Etsy is reachable from this environment and this transport speaks to it.** TLS through the
   agent proxy, HTTP/2, the response body parsed by `http._parse`, the status classified by
   `core.resilience.classify_http` as permanent -- all real, all working. The predecessor's
   audit could not say this: it said "no Etsy API call has ever been made from this system".
   One has now, and it was a read.
2. **The `keystring:shared_secret` header format is confirmed by Etsy, not by us reading
   Etsy.** Etsy's first error names the exact format, and supplying it changes the error to a
   different one. `Credentials.api_key_header` is right.
3. **403, not 401.** `classify_http` treats both as permanent, so retry behaviour is correct,
   but any code or runbook expecting 401 for a bad key is wrong.
4. **Etsy refuses on the API key before it reads a body.** The third request sent a JSON body
   to a form-only endpoint and got the API-key error, not a 415. So **no unauthenticated
   request can ever tell us anything about body handling** -- the encoding cannot be confirmed
   without the owner's OAuth grant. That is a finding about the limits of what this department
   can verify alone, and it is why section 5 exists.

Reproduce: `cd brambleloop && PYTHONPATH=src python3 -m brambleloop.integrations.etsy_probe`.
With no credentials it prints the ping result, the status `NOT EXERCISED`, and the owner action.

### 3.2 EXERCISED AGAINST A LOCAL MODEL OF ETSY -- NOT AGAINST ETSY

`tests/fake_etsy.py` is a real HTTP server on loopback. The client talks to it through the real
`UrllibTransport`, so the bytes on the wire are the bytes Etsy would receive, and the server
parses them with parsers that are not ours: `urllib.parse.parse_qsl` for form bodies and
Python's `email` package for multipart. Its two API-key errors are the real strings observed in
3.1. Its contract -- required fields, enums, media types, field names, the image-before-
activation rule, the deletable states, refresh-token rotation -- comes from Etsy's document.

The full sequence runs end to end and leaves nothing behind:

```
read_shop          ok   getShop 200
create_draft       ok   createDraftListing 201   application/x-www-form-urlencoded
upload_image       ok   uploadListingImage 201   multipart/form-data, part "image"
update_listing     ok   updateListing 200        application/x-www-form-urlencoded (PATCH)
refusals_hold      ok   price refused, state refused, activation refused
read_back          ok   11 of 11 fields matched, state=draft, images=1
cleanup            ok   deleteListing 204, shop holds nothing
```

What that establishes:

- **Our form encoding is parseable by a form parser**, booleans rendered as `true`/`false`,
  arrays comma-joined, and the Content-Type matches the bytes.
- **Our multipart encoding is parseable by an independent MIME parser**, with the file's bytes
  surviving intact and field names preserved -- including a filename containing a quote.
- **The image goes in a part named `image`.** The test that sends it in a part named `file` --
  which is what the old transport did -- gets a 400 naming the parts received. The audit's
  finding is now reproduced as a failing request rather than described in a document.
- **A JSON body on a form endpoint is a 415.** So the old encoding was not merely
  non-canonical; it was a request the endpoint's contract rejects.
- **Read-back verification detects a write the server ignored.** One test PATCHes `quantity`
  -- a field Etsy's update schema does not carry -- past the client's own guard. The request
  returns 200, the listing keeps its old value, and verification reports one MISMATCH with
  both values. That is the failure class that cannot be caught any other way.
- **Money and the rename are handled.** Price 9.99 comes back as `{amount: 999, divisor: 100,
  currency_code: CAD}` and verifies as a match; `type` comes back as `listing_type` and
  verifies with a note. A verifier that reported these as failures would be switched off
  within a day, which is how verification dies.
- **An expired access token is refreshed mid-call, the rotated refresh token is handed back,
  and a spent refresh token raises an owner action rather than a retry.**
- **PKCE matches RFC 7636's published test vector** -- an external check, because a wrong
  challenge fails in the owner's browser and not in any code path here.
- **The refusals refuse, and cost nothing.** Activation with everything else true and no
  Launch-0 string: refused, and no request sent. Activation of an imageless listing with a
  Launch-0 string: refused before the request, because a listing fee is charged on
  publication. Deleting an active listing through a draft cleanup: refused.
- **Activation works when authorised.** One test activates a listing **on the fake shop** and
  reads `state == "active"` back. Something has to prove the gates are the only thing stopping
  it; otherwise "activation is implemented" rests on code nothing has run. No test touches the
  real shop.
- **Nothing leaks.** The exercise report contains no access token, keystring or shared secret;
  `TokenSet`, `OAuthApp` and `Credentials` reprs carry fingerprints, not values.

**This is not evidence about Etsy.** It is evidence that our side of the wire is correct
against Etsy's stated contract. If Etsy's behaviour differs from its document, every one of
these tests still passes.

### 3.3 NOT EXERCISED, AND WHY

| Claim | Status | Why it cannot be checked here |
|---|---|---|
| Etsy accepts our form-encoded `createDraftListing` | **unexercised** | no credentials; Etsy refuses on the API key before reading a body |
| Etsy accepts our multipart image upload | **unexercised** | same |
| Etsy accepts a comma-joined array (`tags=a,b`) rather than repeated keys | **unexercised, and genuinely ambiguous** | Etsy's `tags` description says "A comma-separated list", while the OpenAPI default for an un-encoded form array is repeated keys. Both are Etsy's own document. `etsy.ARRAY_ENCODING` names the decision so one constant moves when a real 400 settles it |
| A 1x1 PNG is an acceptable listing image | **unexercised** | Etsy's image rules are on `help.etsy.com`, which returns 403 to every automated request from here. The probe finds out on its first real run; a refusal there is a finding, not a bug |
| The OAuth token endpoint host, and either grant | **unexercised** | no registered app, no authorization code. Two Etsy documents give two hosts |
| `TAXONOMY_PATTERNS = 66` is the patterns node | **unexercised** | needs an authenticated `getSellerTaxonomyNodes`. A wrong id is a listing in the wrong category, not an error |
| Whether the patterns node requires a listing property | **unexercised** | needs an authenticated call. If it does, every create is refused with a property id in the message |
| `deleteListing` really removes a draft | **unexercised** | the fake returns 204 and forgets the record because Etsy's document lists DRAFT as deletable |
| Etsy's Canadian fee stack | **unexercised** | `etsy.com/legal/fees` is 403 from here; unchanged from the predecessor's finding |

**Nothing in this work has been deployed and no listing, draft or shop exists on Etsy.**

Every row of that table now has a **signature** in `integrations/etsy_probe.TAXONOMY`: what we
send, what each possible response looks like, which of three causes it indicates, and the one
change that follows. See section 7.

---

## 3.4 The three states, and why there are three

Written down here because it is the thing most easily lost. Every claim about the Etsy write
path is in exactly one of:

| State | What it means | What establishes it |
|---|---|---|
| **IMPLEMENTED** | the code exists and is reachable | somebody wrote it |
| **LOCALLY_TESTED** | exercised end to end against `tests/fake_etsy.py`, failure paths included | a green local suite |
| **VERIFIED_AGAINST_ETSY** | observed in a real response from `openapi.etsy.com`, with the observation written down | a live request |

They are three rather than two because "done / not done" is what makes this kind of work
dishonest. `tests/fake_etsy.py` is a server built from Etsy's document **by the same hand that
read that document to write the client**, so a passing test says our client agrees with our
reading. If the reading is wrong, the client and the fake are wrong together and every test
still passes. **One successful fake-shop run is not evidence of Etsy's behaviour, and no
number of them adds up to one.**

Today: 4 claims IMPLEMENTED, 4 LOCALLY_TESTED, 4 VERIFIED_AGAINST_ETSY -- and the four verified
are exactly the four facts from the unauthenticated pings in 3.1. Not one concerns a write.

Where it is recorded, in all three places:

- **In the code.** `publish/listing_schema.py` holds the three constants, `ETSY_VERIFIED_FACTS`
  (the four observations, each with its date and the sentence Etsy returned), and
  `verification_matrix()`, which **refuses** to emit VERIFIED_AGAINST_ETSY for a claim
  `ETSY_VERIFIED_FACTS` carries no observation for. A claim cannot be promoted by being
  believed.
- **In `gaps()`.** Every gap carries `verification`, stamped from the matrix rather than
  written beside it, and a gap naming a claim the matrix does not track is refused. The gap
  list and the matrix cannot describe different worlds.
- **In the report the run emits.** `claims()` gives every claim a `state_before` and a
  `state_after`. A claim moves to VERIFIED_AGAINST_ETSY only when **both** are true: the
  requests went to `openapi.etsy.com`, and this run produced the confirming signature for that
  claim. A run against the fake produces identical findings and promotes nothing. That is a
  test (`test_a_green_run_against_the_fake_cannot_promote_anything_to_verified_against_etsy`),
  not a convention.

A claim the run *contradicted* is marked CONTRADICTED rather than quietly demoted, and a claim
the run *could not check* keeps its state with a note saying so -- because "we have not looked",
"we looked and it was wrong" and "we could not look" are three different facts.

---

## 4. What changed outside this department's own files

- `runtime/pipeline.py` now hands the transport to `Credentials.from_env`, so a production
  publish job refreshes an expired token instead of sending it. One line plus its reason.
- `publish/listing_schema.py:gaps()` -- the image and encoding gaps were rewritten rather than
  deleted. They were "this system does not do it" and they are now "Etsy has never confirmed
  that this system does it correctly", and **they remain launch blockers**, joined by a third:
  nothing has ever authenticated against Etsy. Downgrading them when the code was written
  would have converted a build task into a silent assumption, which is the failure this
  repository keeps a decision log to avoid.
- `tests/test_etsy.py` -- its fake transport moved to the new body channels, and the assertion
  that the create request carries `state: draft` was **inverted**: Etsy's create schema has no
  `state` property, so the client no longer sends one, and draft-ness is now asserted by
  reading the listing back rather than by setting a field and trusting it.

Not touched, as instructed: `visual/**`, `cir/**`, `publish/pdf.py`,
`runtime/release.py:assets.build`, `BUILD_STATE.md`, `DECISION_LOG.md`.

### The distinction `PublishOutcome` was missing

`publish()` reported `published=True` when the draft was created and the file attached. That
sentence was true about the requests and false about the listing: with no image, the draft
could never go live. `PublishOutcome.activatable` is now the separate question -- draft
created, file attached **and** at least one image uploaded -- and `publish()` records a problem
naming Etsy's own rule when it is handed no image bytes. `tests/test_etsy.py` asserts that
today's call is not activatable, which is the honest state of the publish path and was
previously invisible.

**One thing this work needs and does not own.** The probe uploads bytes. The pattern PDF and
the listing imagery are release artefacts, and artifact bytes in this system are not durable
without object storage, so a real end-to-end publish still depends on the storage decision
already in the owner queue. The probe therefore generates its own one-pixel PNG and treats the
pattern file as optional, so the transport can be exercised without waiting for that.

---

## 5. OWNER ACTION REQUIRED

One new item. It does not repeat the six already batched in BUILD_STATE, which stand.

### 5.1 -- Authorise the Brambleloop Etsy app once, in a browser

- **Exact action, in order:**
  1. Sign in to the Etsy account that owns BrambleloopStudio.
  2. At `etsy.com/developers/your-apps`, register the app (or open the existing one) and set
     the callback URL to the exact `https://` redirect this system will use. Etsy matches it
     character for character -- a trailing slash, a missing `www` or a capital `H` all fail.
  3. Put the keystring, shared secret and redirect URI in the **deployment's environment** as
     `ETSY_KEYSTRING`, `ETSY_SHARED_SECRET`, `ETSY_REDIRECT_URI`. Never in the repository.
  4. Run `PYTHONPATH=src python3 -m brambleloop.integrations.etsy_probe`; it prints an
     authorize URL with a fresh PKCE challenge. Open it, approve the scopes
     (`listings_r listings_w listings_d shops_r shops_w`), and let the callback capture the
     code. The code is single-use and expires quickly.
  5. Put the refresh token in the environment as `ETSY_REFRESH_TOKEN`. From then on this
     system refreshes its own access token.
- **Why it is required:** Etsy's authorization-code grant requires a human to approve scopes in
  a browser. There is no client-credentials or key-only route to a write scope, so **no amount
  of code removes this step**, and no code path around an auth wall was attempted. Until it is
  done, every claim in section 3.2 remains a claim about our own correctness.
- **Maximum cost:** CA$0. No fee is charged for an app, a draft, an image upload or a deletion.
  Etsy charges its listing fee on **publication**, which this work never performs.
- **Minutes:** 15.
- **Consequence of waiting:** the shop cannot be built by software at all, and the first real
  Etsy request would be made on the day the shop opens -- which is the situation this whole
  module exists to prevent. Shadow-mode work continues unblocked meanwhile.
- **What happens the moment it is done:** with `ETSY_SHADOW_WRITE=1` the probe runs the eight
  steps in section 7.1 -- identity, one clearly-marked draft, image, update, read-back,
  contract verification, delete, verify the delete -- and classifies every outcome against the
  taxonomy in 7.2, so the run costs one attempt rather than five. Nothing is activated. It is
  safe to run twice, it sweeps anything an earlier attempt stranded, and if a deletion fails
  the report names the listing id and title to remove in Shop Manager. That run is the
  evidence section 3.3 is missing.

### What was run, and the one failure that is not this work's

Suites run individually in this worktree (`run_tests.sh` was not run, by instruction):
`test_etsy` 15, `test_etsy_transport` 27, `test_listing_schema` 14, `test_shop_package` 18,
`test_etsy_capability` 9, `test_launch` 24, `test_platform_policy` 13,
`test_capability_gates` 22, `test_acceptance_gates` 23, `test_provenance` 11, `test_radar` 32,
`test_deliverable` 14, `test_dependency` 9, `test_executor` 34, `test_gates` 33, `test_intel`
38, `test_access` 8, `test_model_access` -- all passing.

`test_deploy` reports one failure:
`test_scheduler_tick_endpoint_is_idempotent_within_a_window` -- "a repeated tick re-enqueued
['infra_heartbeat', 'health_sweep']". It **passes when run on its own**, it concerns the
scheduler's idempotence window and two infrastructure jobs, and nothing in this work touches
the scheduler. It is recorded here rather than left out, because a failure nobody wrote down
is a failure somebody else has to rediscover. It looks like the same family as the
already-diagnosed expiring test: a check whose correctness depends on an unstated condition,
here what ran before it in the same process. Not fixed here -- it is not this department's
file and guessing at someone else's timing invariant is how a real defect gets pinned shut.

This container also lacks the project's `.venv`; `sqlalchemy`, `pillow`, `reportlab`, `fastapi`
and `httpx` were installed into the system interpreter to make the suites runnable at all.

### The environment this code reads

Every one of these is read from the environment and **none of them is ever written to this
repository**. No value is logged: tokens appear in reports as an eight-character SHA-256
fingerprint.

| Variable | Required | What it is |
|---|---|---|
| `ETSY_KEYSTRING` (or `ETSY_API_KEY`) | yes | the app's keystring. Both names are accepted because two documents in this repository named the same value differently, and a name mismatch that presents as "no credentials" is the most expensive kind of typo |
| `ETSY_SHARED_SECRET` | yes | sent as `keystring:shared_secret` in `x-api-key`, which Etsy's live response confirms is the required format |
| `ETSY_SHOP_ID` | yes | the shop every write is addressed to |
| `ETSY_REFRESH_TOKEN` | yes, for writes | the 90-day token the system refreshes access with |
| `ETSY_REDIRECT_URI` | for authorising | the exact registered https callback |
| `ETSY_ACCESS_TOKEN` | no | a pasted one-hour token. With no `ETSY_ACCESS_TOKEN_EXPIRES_AT` it is treated as **already expired**, forcing one refresh rather than sending a token of unknown age |
| `ETSY_SCOPES` | no | what Etsy granted, space-separated, so a scope refusal happens here rather than as a 403 |
| `ETSY_SHADOW_WRITE` | no | `1` lets the probe create and delete one draft in the real shop. Never enables activation |

---

## 6. What this document cannot tell you

- **Whether Etsy accepts any of it.** Every entry in 3.3 turns into a fact or a defect on the
  first authenticated run, and some of them will be defects. That is the point of running it
  against a controlled test draft rather than against the first product.
- **Whether a 1x1 PNG, a 140-character title or a CA$9.99 price behaves as expected on a real
  listing page.** Those are product questions and the probe deliberately makes no product.
- **Whether `help.etsy.com`'s rules have changed.** Still 403 to automated readers, still the
  owner action the predecessor raised.

## 7. The prepared run: one attempt, not five

The owner's authorisation buys one cheap opportunity to learn eight things at once. If the run
is improvised when the credentials arrive, each surprise costs a round trip and a re-run; if
every outcome is named beforehand, the run costs one attempt. This section is that
preparation. It is all in `integrations/etsy_probe.py` and it is exercised, including every
failure path, against `tests/fake_etsy.py`.

`PYTHONPATH=src python3 -m brambleloop.integrations.etsy_probe --taxonomy` prints the whole
table without touching the network.

### 7.1 What the run does, in this exact order

| # | Step | What it establishes that nothing before it did |
|---|---|---|
| 0 | ping, then **sweep** | that Etsy is reachable with no token (and so whether a later failure is the network); and it deletes any test draft a **previous** run left, which is what makes this safe to run twice |
| 1 | authenticated identity + shop read | `getMe` and `getShop`: that the grant worked, the token is live, the scopes are there and `ETSY_SHOP_ID` is ours |
| 2 | create the test draft | that Etsy accepts our form-encoded `createDraftListing`. Title: "DO NOT BUY - Brambleloop transport test &lt;marker&gt;" |
| 3 | upload an image | that a multipart part named `image` reaches Etsy -- and whether a 1x1 PNG is acceptable at all |
| 4 | update permitted fields | that a form-encoded PATCH is accepted |
| 5 | read the listing back | a **separate request**. The write's own 200 is Etsy repeating our data at us; no mismatch can appear in it |
| 6 | verify taxonomy / properties / encoding / remote values | the only step that produces evidence about content. Reads `getSellerTaxonomyNodes` and `getPropertiesByTaxonomyId` and compares |
| 7 | delete the test draft | after re-reading the listing's state and refusing unless it is the draft we expect |
| 8 | verify the cleanup | reads it back and requires a 404. A 204 is Etsy accepting the request, which is a different claim |

Activation is not on that list. `activate()` keeps all three of its gates -- phase, owner
authority, and a Launch-0 string passed to the call -- and step 4b proves all three refuse,
for free, without sending anything. **CA$0**: Etsy charges no fee for an app, a draft, an
upload or a deletion, and charges its listing fee on publication, which this never performs.

**Idempotent and self-cleaning.** The draft is recorded in `left_behind` the moment it is
created and removed from it only when step 8 confirms Etsy no longer holds it. A failure at
any step returns a report rather than raising, always carries `left_behind` (empty when the
shop is clean) and `shop_is_clean`, and when anything is stranded it emits an **owner action**
naming the listing id and title for manual removal in Shop Manager. A second run sweeps what
the first could not remove, so the shop ends with one listing set, not two.

### 7.2 The failure taxonomy

Three causes, because the difference decides who fixes what:

- **OUR_BUG** -- we sent something wrong. The fix is in this repository. Includes the two
  outcomes that look like successes: a wrong taxonomy integer, and an array encoding Etsy
  stores without complaint.
- **ETSY_CONTRACT_DRIFT** -- Etsy behaves differently from Etsy's own published document. The
  reading was right and the document is stale; `listing_schema.READ_ON` needs refreshing
  alongside whatever code changes.
- **ENVIRONMENT** -- credentials, scopes, network or an outage. No code change at all; most
  end at the owner.

A fourth label, **CONFIRMED**, covers the outcomes that turn a claim into a fact, so the table
covers the whole outcome space and not only the bad half. Outcomes marked `settles: false` --
a network failure, a refused credential, a check that could not run -- leave the claim exactly
where it was: "we could not look" is not "it is broken".

50 signatures across the seven steps. The ones that answer section 3.3 directly:

| Claim | We send | Signal | Cause | The single change |
|---|---|---|---|---|
| form-encoded create | POST, `application/x-www-form-urlencoded`, 7 required fields | **201 + listing_id** | CONFIRMED | none |
| | | 415 | drift | switch this one call to the `json` channel -- one argument to `_call` |
| | | 400 "Required parameters missing" naming a field we sent | our bug | fix the name in `ListingPayload.to_dict` |
| | | 400 naming a field the document's `required` array omits | drift | add it to `listing_schema.REQUIRED_TO_CREATE` and to the payload |
| multipart image | binary in a part named `image`, `image/png` | **201 + listing_image_id** | CONFIRMED | none |
| | | 400 "No image supplied" / parts listed | our bug | the encoder's part name or boundary; the old transport sent `file` |
| | | 415 | drift | re-read the `uploadListingImage` request body |
| | | 400 naming the format | drift | send JPEG; drop PNG from `IMAGE_CONTENT_TYPES` |
| 1x1 PNG acceptable | a generated one-pixel PNG | 400/413 naming a dimension, size or ratio | our bug (the **fixture**) | `png(width, height)` at the size Etsy names. The transport claim stays LOCALLY_TESTED until an image is accepted |
| **tags: comma vs repeated keys** | `tags=a,b` (`ARRAY_ENCODING = "comma"`) | 400 naming tags or materials | our bug | `ARRAY_ENCODING = "repeat"` |
| | | **201, then Etsy holds ONE tag containing a comma** | our bug | `ARRAY_ENCODING = "repeat"`. *No status code anywhere says anything is wrong* -- only the read-back comparison sees it |
| | | Etsy returns exactly the tags we sent | CONFIRMED | none; the ambiguity closes |
| OAuth token host | refresh grant to `api.etsy.com`, `openapi.etsy.com` on 404 | 200 from the first | CONFIRMED | none |
| | | 404 then 200 from the second | drift | `etsy_oauth.TOKEN_URL` to the openapi host |
| | | 404 from both | drift | re-read the authentication page |
| | | 400 `invalid_grant` | environment | none in code; the rotated refresh token was not persisted. Owner re-authorises |
| `TAXONOMY_PATTERNS = 66` | taxonomy_id 66, then `getSellerTaxonomyNodes` | node absent, or named something other than Patterns -- **with a 201 either way** | our bug | `TAXONOMY_PATTERNS` = the id in `taxonomy_candidates`, which the same report prints |
| | | the listing carries a different taxonomy_id than we sent | drift | `TAXONOMY_PATTERNS` = the id Etsy returned; record that the node redirects |
| node requires a property | `getPropertiesByTaxonomyId` | 400 on **every** create, naming a property id | our bug | a build task: implement `updateListingProperty`; the gap becomes a launch blocker |
| | | `is_required` property, create still 201 | our bug | same, but it bites at activation instead |
| `deleteListing` removes a draft | DELETE, then GET | **204 then 404** | CONFIRMED | none |
| | | 204 then 200, still there | drift | owner action for Shop Manager; `delete_listing` returns the observed state. **Do not re-run** -- each run would leave another draft |
| | | 204 then 200 in state `removed`/`expired` | drift | Etsy soft-deletes: change step 8's expectation to that state, and make the sweep match on title rather than absence |
| | | 403 naming `listings_d` | environment | owner re-authorises with the delete scope; the draft is named for manual removal |

An outcome no signature matches comes back as `UNCLASSIFIED` with no cause, and the report
says plainly that this is a gap in `TAXONOMY` rather than a question for the reader. **No entry
says "investigate"**; a test asserts it.

### 7.3 Secrets

No access token, refresh token, keystring, shared secret or authorization code appears in any
log, report, fixture or test. `http.Redactor` removes a secret two ways, because either alone
fails: by **field name** (`access_token`, `authorization`, `code`, ...) and by **value**, seeded
with the credentials the process actually holds, so a token echoed back inside an error
message, a URL or a field Etsy added after this code was written is caught too. A redacted
value becomes `***<8 hex of SHA-256>` -- the same fingerprint property `TokenSet`, `OAuthApp`
and `Credentials` reprs already have, extended from the objects to the bytes that came back.
Redaction happens where a response becomes a report, not where a report is printed. A test
makes the fake echo the `Authorization` header back inside an error body and asserts the token
does not reach the report.

### 7.4 What is still unknowable until the credentials exist

Everything in 3.3 and everything in 7.2 above. The taxonomy makes each outcome *classifiable
on sight*; it does not make any of them *known*. Also still unknowable: whether a 140-character
title or a CA$9.99 price behaves as expected on a real listing page (product questions, and
this run deliberately makes no product), and Etsy's Canadian fee stack (`etsy.com/legal/fees`
is still 403 to automated readers from here).

One dependency outside this department's files: `etsy_oauth.SCOPES_REQUIRED` has no entry for
`getSellerTaxonomyNodes` or `getPropertiesByTaxonomyId`, and `missing_scopes` refuses an
operation it does not know rather than guessing. Both endpoints carry root-level `api_key`
security in Etsy's document, so the entries are empty tuples. Without them the run still
completes and still cleans up, but the taxonomy and property claims stay IMPLEMENTED -- so the
run says so, in the step record, naming the exact two lines.

---

## 8. The trigger: how the prepared run actually runs, and where

**Written:** 2026-09-25 (UTC). **Phase:** SHADOW. **State:** IMPLEMENTED and LOCALLY_TESTED.
**Not VERIFIED_AGAINST_ETSY** — nothing in this section has been run against Etsy, and a
green local suite cannot make it so.

### 8.1 The gap, verified before anything was written

Section 7 prepared the run. It did not give it anywhere to run. Verified by `grep` across
`src/` on 2026-09-25:

| Finding | Verified |
|---|---|
| `run_exercise` is called from exactly one place: `etsy_probe.main()` | yes |
| No FastAPI route reaches it | yes — `etsy_probe` appeared nowhere in `app/main.py` |
| No job handler reaches it | yes — no `@registry.register` handler imports it |

And the constraint that decides the design: **the refresh token is sealed in production's
Postgres under production's `BRAMBLELOOP_SECRET_KEY`, and neither exists in a development
container.** So the only machine that *can* run the exercise is the deployed service, and the
only way to ask it to is an endpoint. A runbook that says "ssh in and run the module" is not
an answer on a platform whose containers are replaced several times an hour.

### 8.2 What was built

`integrations/etsy_exercise.py`, and one route.

```
POST /api/etsy/exercise?mode=full       the eight steps, then the rotation proof
POST /api/etsy/exercise?mode=rotation   the rotation proof alone — no draft, no write
```

Guarded by `opsauth`, identically to `/api/continuity/export`, `/api/queue/requeue` and
`/api/etsy/oauth/start`: **401** on a wrong or absent credential, **503 when the token is
unset**, because unconfigured-means-closed is the only default that does not serve the company
to the internet during the window between a deploy and remembering to set a variable. POST
rather than GET, because a GET is fetched by link previewers, by browser prefetch and by
anything that follows a URL out of a log, and none of those may create a draft.

It does **not** re-implement the run. `etsy_probe.run_exercise` is invoked unchanged. What the
module adds is the four things a real shop needs that a pure function cannot provide.

#### Activation is structurally unreachable

`_client()` hard-codes `owner_authorised=False` — written in the function, not passed to it.
`EtsyClient.refusal()` checks the phase, then that flag, then the credentials, and
`refusal_for(ACTIVATE)` returns `refusal()` unchanged when it is not None. So there is no
phase, no environment variable and no argument to this module that produces an activation
authority: a test asserts it for `shadow`, `staging`, `limited_production` **and**
`production`. `_client()` then asserts that the client it just built reports an activation
refusal, and **refuses to start the run at all** if it does not — so a future loosening of the
gates stops this path rather than arming it.

`activate()` itself is byte-for-byte unchanged and pinned: `test_activate_keeps_its_three_gates_byte_for_byte`
holds the SHA-256 of its source. And the strongest form of the claim is measured on the wire:
a whole run is driven through a recording transport and **no request in it carries a `state`
field at all**.

#### A draft's existence becomes durable in the instant Etsy creates it

`run_exercise` records the draft in an in-memory `left_behind` list. That is right for a
function and worth nothing if the process dies between the create and the delete: the shop
then holds a listing nothing anywhere knows about. `_Breadcrumbs` subclasses `EtsyClient` and
writes an audit row the moment `create_draft` returns an id — committed before the id reaches
the caller — and a matching row only when a **read of Etsy** confirms the listing is gone. An
unmatched pair is a permanent, queryable record, readable after a crash, by a different
container, with no re-run.

#### The shop is read back independently of the report

`run_exercise` reports `shop_is_clean` from its own bookkeeping, which is right about what
*this* run did and knows nothing about what a killed run did. `shop_read_back()` asks Etsy for
the shop's drafts and looks for the marker prefix. A report's opinion of the shop is not the
shop.

#### One run at a time, held by something that cannot outlive its holder

On Postgres, a **session-level advisory lock on a dedicated connection**. The choice is the
point: an advisory lock is released by the database when the connection drops, so it cannot
outlive the process holding it — precisely the property a job lease does not have. On SQLite
there is no advisory lock and an in-process mutex is the whole guarantee; the report says
which of the two was in force rather than implying the stronger one.

### 8.3 Inline, not a durable job — and why

The requirement was to decide honestly against the 5-minute lease and the worker's behaviour.
It runs **inline, inside the HTTP request**. The queue is the wrong home for this work:

- **`JobQueue._reclaim_expired` hands an expired lease to another worker without stopping the
  first one.** There is no cancellation and no fencing token. If the run ever exceeded
  `DEFAULT_LEASE_SECONDS` (300) — a slow Etsy, a stalled TLS handshake, one transient retry —
  a second worker would begin a second exercise against the same real shop while the first was
  still mid-flight. The step-0 sweep deletes test drafts **by title prefix**, so the second
  run's housekeeping deletes the first run's live artefact; interleave it the other way and
  the first run creates its draft after the second has swept, and the shop ends holding a
  draft only one report mentions. That is exactly the half-finished run this had to be
  designed against, arriving through the recovery path.
- **`claim()` increments `attempts` against `max_attempts`**, so a run that fails is
  re-executed up to three times, each attempt creating a draft.
- **`idempotency_key` guarantees a job is enqueued once, not executed once.** The single
  guarantee the queue is built on is the one this work needs and does not get.
- **The work is not long by the queue's standard**: about a dozen Etsy round trips plus at most
  one token refresh. The lease exists for renders and builds.
- **The report is the deliverable.** Inline it is returned to the operator who asked; as a job
  it would be written into a row somebody then has to find.

Inline, the HTTP request *is* the lease: one caller, one run, no reclaim, no retry. The failure
mode inline is a dropped connection rather than a stranded draft — and the breadcrumb ledger is
what makes even a killed container leave the listing id and title behind in writing, with the
next run's step-0 sweep removing it and an owner action naming it if the sweep cannot.

### 8.4 The operator command

```
curl -sS -X POST "https://<host>/api/etsy/exercise" \
     -H "Authorization: Bearer $BRAMBLELOOP_OPS_TOKEN"
```

`?mode=rotation` runs the rotation proof alone — two authenticated shop reads, no draft,
nothing to clean up, and the safest order is to run that one first. Either way: **CA$0**. Etsy
charges no fee for an app, a shop read, a draft, an image upload, a deletion or a token
refresh; its listing fee is charged at publication, which nothing on this path performs.

The reply is the authoritative report: the eight steps with what each measured and what Etsy
returned, every finding classified against the 50-signature taxonomy, every claim's
`state_before` and `state_after`, an independent read of the shop, the credential's state after
cleanup, `/api/verify`'s own verdict, and — if anything was stranded — an owner action carrying
the listing id and title to remove in Shop Manager. HTTP 200 when the run is clean and
verified, 502 when it is not, 409 when another run holds the claim or no credential exists.

### 8.5 What was exercised, and what that is worth

30 checks in `tests/test_etsy_exercise.py`, all against `tests/fake_etsy.py`. Including: the
three `opsauth` outcomes and a refused call that reaches the network zero times; every phase
failing to produce an activation authority; a `refusal_for` that lies and a run that refuses to
start because of it; a whole run with no `state` field on any request; a broken delete that
strands a draft, names it in the owner queue with its id and title, writes it to the durable
ledger, and is then swept by the next run's step 0; a shop read that contradicts a clean
report; a second concurrent call refused; and one sweep for every secret the fake ever minted,
over the report, the audit rows and the owner queue together.

**None of it is evidence about Etsy.** `against_etsy()` is false for every one of those runs
because `EtsyClient.BASE` is not `openapi.etsy.com`, and
`test_a_green_run_against_the_fake_promotes_nothing` asserts that no claim moved. The three
states in §3.4 stay three.

## Sources

Fetched successfully from this environment on 2026-09-25:

- Etsy Open API v3 description, document version 3.0.0 --
  `https://www.etsy.com/openapi/generated/oas/3.0.0.json`
- Etsy Open API v3, "Authentication" --
  `https://developer.etsy.com/documentation/essentials/authentication/`
- `https://openapi.etsy.com/v3/application/openapi-ping` -- three live requests, section 3.1

Standards relied on directly:

- RFC 7636 (PKCE), including the appendix B test vector used in `tests/test_etsy_transport.py`
- RFC 6749 section 4.1.3, for the token request's form encoding
