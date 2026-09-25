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
- **What happens the moment it is done:** with `ETSY_SHADOW_WRITE=1` the probe creates one
  clearly-marked draft ("DO NOT BUY - Brambleloop transport test"), uploads an image, updates
  it, reads it back from Etsy, verifies remote state field by field, and deletes it. Nothing is
  activated. If the deletion fails, the report names the listing id and the title to remove in
  Shop Manager. That run is the evidence section 3.3 is missing.

---

## 6. What this document cannot tell you

- **Whether Etsy accepts any of it.** Every entry in 3.3 turns into a fact or a defect on the
  first authenticated run, and some of them will be defects. That is the point of running it
  against a controlled test draft rather than against the first product.
- **Whether a 1x1 PNG, a 140-character title or a CA$9.99 price behaves as expected on a real
  listing page.** Those are product questions and the probe deliberately makes no product.
- **Whether `help.etsy.com`'s rules have changed.** Still 403 to automated readers, still the
  owner action the predecessor raised.

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
