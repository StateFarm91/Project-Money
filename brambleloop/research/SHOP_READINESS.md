# Shop readiness — an honest audit of what would happen if the phase moved tomorrow

**Written:** 2026-09-24 (UTC). **Phase:** SHADOW. **By:** the commerce/Etsy department,
working in an isolated worktree.

**Nothing in this document describes something that exists on Etsy.** There is no shop. No
Etsy API call has ever been made from this system — not once, not in a test, not against a
sandbox. The client has only ever spoken to a fake transport in `tests/test_etsy.py`. Every
sentence below about "what would happen" is a reading of Etsy's own published API document,
not an observation.

The question this audit answers is narrow and specific: *if the owner opened the shop and set
`BRAMBLELOOP_PHASE` to production tomorrow, what would actually go wrong?* The answer is that
three things would fail outright, several would fail intermittently, and the shop's policy
page would be blank — and none of those was visible from the existing readiness report,
because that report measures our side of the wire.

---

## 1. Audit: what is built, what is stubbed, what is missing

### Built and tested

| Thing | Where | State |
|---|---|---|
| Etsy client with three ordered refusals (phase → owner authority → credentials) | `src/brambleloop/integrations/etsy.py` | Built, unit-tested against a fake transport, never called against Etsy |
| Draft-listing payload mapping, with Etsy's length/count limits enforced as refusals | `integrations/etsy.py:build_payload` | Built; **extended by this work** with Etsy's character-set rules |
| Digital-file upload shape (`POST .../listings/{id}/files`) | `integrations/etsy.py:attach_file` | Built; multipart encoding unverifiable without a live call, and the module says so |
| Half-done outcome (listing created, file not attached) reported as its own state | `integrations/etsy.py:PublishOutcome` | Built and tested |
| Shadow-mode publish refusal in the pipeline | `runtime/pipeline.py` | Built, exercised on every run |
| Platform-policy snapshot/freshness watch and AI-disclosure gate | `gates/platform_policy.py` | Built; **no fetcher writes to it** (see §5) |
| Customer-use terms, five axes, closed options, three-surface consistency | `commerce/terms.py` | Built; `enforceable` correctly false |
| Storefront: announcement, About, sections, banner/icon briefs | `brand/storefront.py` | Built |
| Buyer-trust disclosure set, image provenance, order→version map | `commerce/buyer_trust.py` | Built |
| Launch readiness with build/integration/owner blocker classes and an owner queue | `launch/readiness.py` | Built and honest |
| CASL consent gate for every commercial electronic message | `growth/owned.py` | Built |
| Listing-set certificate that self-invalidates on geometry/claims/policy change | `publish/listing_set.py` | Built |

### Built by this work

| Thing | Where |
|---|---|
| Etsy's digital-download listing contract, clause by clause, each labelled SOURCED (with the sentence) or INFERRED | `src/brambleloop/publish/listing_schema.py` |
| Character-set, repeated-symbol, duplicate-material and activation checks | `publish/listing_schema.check_payload` |
| The form-encoded request body Etsy's document describes | `publish/listing_schema.form_encoded` |
| A named gap list, each gap resting on a clause | `publish/listing_schema.gaps` |
| The shop configuration package: six policies, FAQ, AI disclosure, delivery, returns, About structure, the five API-writable shop fields and the list of what a person must type | `src/brambleloop/commerce/shop_package.py` |
| Jurisdiction claims with PRIMARY / SECONDARY / INFERRED evidence and `needs_professional_advice` | `commerce/shop_package.CLAIMS` |
| Tests | `tests/test_listing_schema.py` (14), `tests/test_shop_package.py` (18) |

### Stubbed — exists as a shape, has never run

- **The HTTP transport.** `integrations/http.py` has never made a request to Etsy. Its
  multipart encoder is written from documentation.
- **The digital-file upload.** Same. The module's own docstring already says so.

### Missing entirely

- **Listing images are never uploaded.** `uploadListingImage` is not called anywhere. This
  system generates, checks, certifies and approves listing imagery and then keeps all of it
  on our side of the wire. **This alone means no listing can ever go live** (§3).
- **Activation.** `updateListing` is not called anywhere. The client creates drafts and
  stops. Nothing in the system can move a listing from `draft` to `active`, which is the
  step that publishes it.
- **OAuth.** `Credentials.from_env` reads a static `ETSY_ACCESS_TOKEN`. There is no
  authorization-code flow, no token refresh and no handling of an expired token. Etsy's
  document gives the flow (`authorizationCode`, token URL
  `https://openapi.etsy.com/v3/public/oauth/token`) and the required scope (`listings_w`).
- **Shop setup calls.** `updateShop`, `createShopSection` and `createShopReturnPolicy` exist
  in Etsy's API and are not called. Sections are decided in `brand/storefront.py` and cannot
  currently be created.
- **Listing properties (attributes).** Some taxonomy nodes mark properties `is_required`.
  Nothing here can read or set one.
- **A policy fetcher.** `gates/platform_policy.record_snapshot` has no caller in `src/`.

---

## 2. The shop configuration package

Assembled in `commerce/shop_package.py`, as data and code, rendered from decisions that
already existed rather than written a second time.

**The defect it was built on top of.** The buyer's licence existed in three places and said
three different things:

| Surface | What it said about selling finished items |
|---|---|
| `commerce/terms.py` (the decision) | "by individual makers and small businesses, not manufactured at scale" |
| `brand/storefront.py` (the shop policy) | "sell the items you make from it" — no limit |
| `commerce/seo.py` (every listing description) | "Sell what you make" |

That is requirement 40's drift failure, already live, before a single sale — and it is the
single most-asked question in the craft-pattern market. A buyer who found the difference
would be entitled to rely on the most favourable version, which is the storefront's.

`brand/storefront.py` now renders its policies from `shop_package.policies()`, which renders
the licence from `commerce/terms.py`. One decision, three surfaces, checked by
`commerce.terms.consistency` in `tests/test_shop_package.py`. **`commerce/seo.py`'s
description block is not yet unified** — see §5.

**What the package contains.**

- **Returns (digital).** States non-returnability in the first sentence, before the sale,
  then gives the two remedies that cost nothing and fix the actual problem. Etsy's own
  position is quoted: *"Sellers will no longer be able to accept returns on digital listings
  given the nature of the items"* — and, from the same announcement, a seller may still
  resolve a complaint however it chooses, which is why the policy promises help rather than
  a process.
- **Delivery / processing.** No processing time, nothing posted, where the file is, and what
  to do when a download fails — which is the case the policy exists for.
- **Licence.** Rendered from the five decided axes. Personal and teaching use; finished items
  saleable by individual makers and small businesses; no redistribution; version-aware email
  support; free corrections forever.
- **FAQ.** Ten questions, in the order buyers ask them. "Can I sell what I make from this
  pattern?" is first and is answered in the decided words, with its limit in the same answer.
- **AI disclosure.** Rendered from `gates/platform_policy.DISCLOSURES`, which is where the
  policy gate reads them, so a listing and the FAQ cannot disagree.
- **`digital_sale_message`.** The message Etsy sends the instant a digital item is bought.
  Newly added: it is the one surface that reaches every single customer, and it was empty.
- **`policy_additional`.** The only policy text Etsy's API can write. Carries the licence and
  the disclosures.
- **About structure.** Five things an About must cover, checked on substance rather than
  length, because four hundred characters of atmosphere passes a length check.

**What only a person can enter.** Etsy's API writes five shop text fields
(`title`, `announcement`, `sale_message`, `digital_sale_message`, `policy_additional`), plus
shop sections and return policies. It has **no write endpoint** for the delivery, returns,
privacy or FAQ policy text, for the About story, or for the banner and icon. Those are typed
into Shop Manager, once, by the owner. `shop_package.MANUAL_ONLY` lists each with the Shop
Manager path beside it, so the action is pasting six fields rather than composing a shop.

---

## 3. Listing schema completeness

Read on **2026-09-24** from Etsy's own published API description,
`https://www.etsy.com/openapi/generated/oas/3.0.0.json` (document version 3.0.0), which was
fetched successfully. Etsy's help centre and policy pages (`help.etsy.com`,
`etsy.com/legal/*`) returned **HTTP 403 to every automated request** from this environment,
with and without a browser user agent — so anything attributed to them here is secondary and
says so.

### SOURCED — the sentence exists and is kept in `publish/listing_schema.CLAUSES`

| Rule | Evidence |
|---|---|
| Required to create: `quantity, title, description, price, who_made, when_made, taxonomy_id` | the request schema's own `required` array |
| A draft cannot be activated without an image | *"Setting a `draft` listing to `active` will also publish the listing on etsy.com and requires that the listing have an image set."* |
| Images are a separate endpoint | `POST .../listings/{listing_id}/images`, `multipart/form-data` |
| Files are a separate endpoint | `POST .../listings/{listing_id}/files`, `multipart/form-data` |
| `shipping_profile_id` — physical only | *"Required when listing type is `physical`."* |
| `return_policy_id` — active physical only | *"Required for active physical listings."* |
| `readiness_state_id` (processing profile) — physical only | *"Returned only when the listing is `active` and of type `physical`"* |
| Title characters: letters, digits, punctuation, maths symbols, whitespace, ™ © ® — and `%`, `:`, `&`, `+` **once each** | *"You can only use the %, :, & and + characters once each."* |
| Tag characters: letters, digits, whitespace, `-`, `'`, ™ © ® | the `tags` property description |
| Material characters: **letters, digits and whitespace only** | *"Valid materials strings contain only letters, numbers, and whitespace characters."* |
| Request body is `application/x-www-form-urlencoded` | the only media type listed for `createDraftListing` and `updateListing` |
| Write endpoints need the `listings_w` OAuth scope | the operations' `security` blocks |
| At most 20 images per listing | the `image_ids` property description |
| Some taxonomy nodes require listing properties | *"is_required: When true, listings assigned eligible taxonomy IDs require this property."* |
| `type` enum is `physical`, `download`, `both`; `who_made` is `i_did`, `someone_else`, `collective`; `updateListing.state` is `active`, `inactive` | the enums |
| `updateShop` writes five text fields and no more | its request schema |

### INFERRED — this company's reading, arguable

- `quantity = 999` for a file that is copied rather than consumed. Etsy requires a positive
  quantity; any number is arbitrary, and the maximum is the least misleading.
- `createDraftListing` takes no `state` field, so a created listing is a draft and activation
  is the separate `updateListing` call. Our payload still sends `state: "draft"`; it is
  harmless and it is not in the schema.
- **`TAXONOMY_PATTERNS = 66` has never been read back from Etsy.** The comment says
  `craft_supplies_and_tools.patterns`. Confirming it needs one authenticated GET to
  `getSellerTaxonomyNodes`, which needs a keystring this environment does not have and this
  phase would not use. A wrong taxonomy id is a listing in the wrong category, not an error.

### Gaps between the contract and what we produce

Each is in `publish/listing_schema.gaps()`, resting on a named clause.

| Gap | Blocks launch | Why |
|---|---|---|
| **No listing image is ever uploaded** | **Yes** | Etsy refuses to activate a listing with no image. The client uploads the pattern PDF to the *files* endpoint; that is not an image and it is a different endpoint. Every draft would be permanently unactivatable. |
| **The create request is sent as JSON** | **Yes** | `integrations/http.py` serialises with `json.dumps` and sets `Content-Type: application/json`. Etsy's document lists only `application/x-www-form-urlencoded` for this endpoint. `listing_schema.form_encoded()` is the shape the body needs. |
| **Nothing ever activates a listing** | **Yes** | `updateListing` is not called. The system's own tests correctly assert that it creates drafts; nobody noticed that nothing finishes the job. |
| Character sets unchecked | No — **fixed by this work** | A material written `100% cotton` was refused by Etsy and by nothing here. `build_payload` now refuses it. |
| Duplicate materials | No — **fixed by this work** | A CIR carries one material entry per colour, so an eight-colour blanket sent the same yarn eight times, and a fourteen-colour one would have been refused. `build_payload` now collapses them, preserving order. |
| Taxonomy id unverified | No | Wrong category, not an error. |
| Required listing properties unknown | No, probably | If the patterns node marks a property `is_required`, every listing is refused with a property id in the message. Knowable only by asking Etsy. |
| No OAuth refresh | No, then yes | A static token works until it expires. This fails on day two, not day one, which is the worse of the two. |

---

## 4. Jurisdiction

Canada, CAD, selling digital goods internationally through a marketplace. Recorded in
`commerce/shop_package.CLAIMS` with evidence and consequence; `needs_professional_advice` is
a field on the claim, not a footer disclaimer.

**GST/HST — PRIMARY.** The CRA's own page: *"Your effective date of registration is no later
than the day of the supply that made you exceed $30,000. … You will have to register within
29 days of your effective date of registration."* The shop opens under the small-supplier
position. The CA$30,000 figure is a revenue number the finance department can compute, so
this becomes a threshold somebody watches rather than a thing somebody remembers. **The
decision of whether to register early, and whether to give Etsy a GST/HST number, is the
owner's and has a tax consequence** — giving Etsy the number moves responsibility for
collecting and remitting.

**Etsy as marketplace facilitator — SECONDARY, flagged for advice.** Etsy collects and remits
GST/HST on sales to Canadian buyers, and collects VAT on digital items where required.
Every page that states this authoritatively is on `help.etsy.com`, which refused every
automated read from here. The shop therefore states that tax is handled at checkout and
quotes no rate, which is true under either reading. Selling the same PDF off-Etsy later
would be a completely different tax question with the same file.

**EU right of withdrawal — SECONDARY, flagged for advice.** Under Directive 2011/83/EU, a
consumer's 14-day withdrawal right for digital content not supplied on a tangible medium is
lost only where they gave prior express consent to immediate supply *and* acknowledged losing
it. On Etsy that consent is collected by the platform's checkout — a dependency worth naming
rather than assuming, because if it is not collected the withdrawal period does not simply
stay at 14 days.

**CASL — already enforced.** A commercial electronic message to a Canadian recipient needs
consent, sender identification and a working unsubscribe. `growth/owned.py` already encodes
the consent bases and their clocks and gates every send. The shop-facing consequence is in
the privacy policy in the buyer's own words: buying something does not put you on a list.
The CRTC's guidance pages also refused automated reads; the gate cites the statute.

**Pattern copyright — INFERRED, flagged for advice.** Copyright in a pattern covers the
document, its charts and its photographs. What a buyer may do with a *finished object* is a
licence this company chooses to grant, not a right the law supplies. The terms are therefore
stated as what this shop permits, and `commerce.terms.enforceable` stays false until a
qualified person has read them. Over-claiming here is the standard failure of the category
and it is the claim most likely to be tested by a customer.

**Etsy's fee stack — SECONDARY, materially uncertain.** `launch/readiness.py` costs the
listing fee at US$0.20 / CA$0.28 and quotes 6.5% transaction plus payment processing. Third-
party sources report a **country-specific Regulatory Operating Fee of about 1.15% for
Canada**, and other third-party sources say Canada has none. Etsy's own fees page is 403 from
here. This is not a rounding difference on a CA$7 pattern; it is the difference between a
pricing floor that holds and one that does not.

---

## 5. Build work this department has not done

Honest list, not a plan. None of it is blocked on the owner.

1. **Upload listing images** (`uploadListingImage`) and **activate a listing**
   (`updateListing`, `state=active`). Without both, nothing publishes. These are the two
   largest missing pieces in the whole commerce path.
2. **Form-encode the create and update bodies.** `listing_schema.form_encoded()` produces the
   shape; the transport still sends JSON. Deliberately not changed here: the wire format
   cannot be verified without a live call, and changing the transport on the strength of a
   reading produces the same untested code carrying more confidence.
3. **OAuth authorization-code flow and token refresh.**
4. **Unify `commerce/seo.py`'s description TERMS block** with `commerce/terms.py`. Two of the
   three surfaces now render from the decision; the listing description still writes its own
   sentence, which is the same defect at a third of the size.
5. **A policy fetcher for `gates/platform_policy`.** Nothing in `src/` calls
   `record_snapshot`, so the freshness watch has never read anything — correctly reporting
   "never checked" and correctly blocking new product classes. Because Etsy returns 403 to
   automated readers, the fetcher cannot be an HTTP client; it has to be an ops endpoint that
   takes pasted text. That is a build task, and it makes the owner action in §6 possible.
6. **A shop-section creation call** (`createShopSection`) so the six decided sections are
   created rather than typed.

---

## 6. OWNER ACTION REQUIRED

These are **new** items found by this audit. They do not repeat `launch/readiness.py`'s
existing queue (open the shop and pass identity verification, add the payout account,
approve listing fees, add model credits, brand clearance, object storage, move the phase),
which stands unchanged and is still the gate.

### 6.1 — Read Etsy's five policy pages and paste them into the policy watch

- **Exact action:** open these five pages in a browser and paste each one's text into the
  ops policy-snapshot form (build item §5.5 — tell this department when you want it and it
  will exist before you need it): `etsy.com/legal/sellers/`, `etsy.com/legal/handmade/`
  (Creativity Standards), the listing-image rules help article,
  `etsy.com/legal/advertising/`, `etsy.com/legal/prohibited/`.
- **Why it is required:** `gates/platform_policy` blocks enabling a new asset or product
  class against a policy nobody has read, and it has read nothing. This system cannot read
  them itself: every one of those URLs returns HTTP 403 to an automated request from this
  environment. A human browser is the only reader that works.
- **Maximum cost:** CA$0.
- **Minutes:** 25.
- **Consequence of waiting:** every release certificate is stamped against a policy version
  nobody has read, and the creativity/disclosure gate stays in its blocking state. Harmless
  in shadow; it is the difference between a compliant listing and a suspension notice once
  live.

### 6.2 — Decide the GST/HST position

- **Exact action:** decide (a) whether to register for GST/HST now or open as a small
  supplier, and (b) whether to give Etsy a GST/HST number. If you have an accountant, this
  is one email to them.
- **Why it is required:** software must not take a tax position. Registration is free, the
  CA$30,000 threshold takes effect on the sale that crosses it, and registration is due
  within 29 days of that date. Giving Etsy the number moves responsibility for collecting
  and remitting from the platform to you.
- **Maximum cost:** CA$0 to register; up to CA$250 if you want an hour of an accountant's
  time to decide.
- **Minutes:** 20, plus whatever the accountant takes.
- **Consequence of waiting:** none at zero sales. From the first sale onward, the wrong
  position is a correction to file rather than a decision to make.

### 6.3 — Have a Canadian lawyer read the customer-use terms

- **Exact action:** send `commerce/terms.py`'s five decided axes — personal and teaching use,
  finished items saleable by individual makers and small businesses, no redistribution,
  version-aware support, free corrections forever — to a Canadian lawyer, and tell this
  department the reviewer, date and scope so `commerce.terms.record_legal_review` can record
  it.
- **Why it is required:** `Terms.enforceable` is false and stays false until somebody
  qualified has looked. Until then these are terms this company offers, not protections it
  has, and the shop says so in writing on every surface — which is honest and is also the
  sentence a buyer reads before deciding whether to respect them.
- **Maximum cost:** CA$500 (a one-hour consultation).
- **Minutes:** 30 of your time; the lawyer's turnaround is theirs.
- **Consequence of waiting:** the terms are still shown and still say they are unreviewed.
  The risk rises with volume, and it is asymmetric: the finished-item clause is the one a
  customer will actually test.

### 6.4 — Confirm the Canadian fee stack once the shop exists

- **Exact action:** in Shop Manager → Finances → Payment account, read the actual fee lines
  on the first transaction and tell this department the figures: listing fee, transaction
  fee percentage, payment processing, and whether a **Regulatory Operating Fee** appears and
  at what rate.
- **Why it is required:** `launch/readiness.py` and the pricing floor are built on US$0.20 +
  6.5% + processing. Third-party sources disagree about whether Canada carries a ~1.15%
  Regulatory Operating Fee; Etsy's own fees page returns 403 to automated readers. On a CA$7
  pattern the difference decides whether the floor holds.
- **Maximum cost:** CA$0.
- **Minutes:** 5.
- **Consequence of waiting:** the margin model is wrong by an unknown amount in the wrong
  direction. Nothing breaks; the numbers in every pricing decision are quietly optimistic.

### 6.5 — Set each listing's AI attribution in Shop Manager

- **Exact action:** when listings are created, set each one's AI-use disclosure and
  attribution in Shop Manager (reported to be the "Designed by" attribution rather than "Made
  by"), in addition to the disclosure line the description already carries.
- **Why it is required:** this is a **SECONDARY** finding and it is flagged as such. Multiple
  third-party sources report that Etsy requires AI disclosure in two places — a line in the
  description *and* a listing setting — and Etsy's own help pages could not be read from
  here. What is **PRIMARY** is that Etsy's API document contains no AI, attribution or
  disclosure field of any kind: the strings "artificial intelligence", "generative",
  "disclosure" and "attribution" each appear **zero** times in it, and no field is named for
  AI. So if such a setting exists, **no software can set it** and a person must. Confirm the
  requirement when you first open the listing editor.
- **Maximum cost:** CA$0.
- **Minutes:** 10 to confirm, then about 1 per listing.
- **Consequence of waiting:** the third-party sources describe removal without warning for
  non-disclosure. Our description-level disclosure is already present and is the substantive
  half; the setting, if it exists, is the half a checkbox catches.

---

## 7. What this audit could not check

Stated so that its absence is not mistaken for a pass.

- **Anything on `help.etsy.com` or `etsy.com/legal/*`.** HTTP 403 to every automated request
  from this environment. Shop-policy setup, the fee schedule, Canadian remittances, VAT on
  digital items and the Creativity Standards are all behind that wall.
- **Etsy's seller taxonomy.** Needs an authenticated call. The taxonomy id we send is
  unverified, and so is whether the patterns node requires a listing property.
- **Whether any of this works.** Every claim about Etsy's behaviour here is a reading of a
  document. The first real request will teach us something this audit could not.
- **Whether the terms are enforceable.** That is §6.3 and it is not a software question.

---

## Sources

Fetched successfully from this environment on 2026-09-24:

- Etsy Open API v3 description (document version 3.0.0) —
  `https://www.etsy.com/openapi/generated/oas/3.0.0.json`
- Etsy announcement, "An update to our policy on returns for digital items" —
  `https://community.etsy.com/t5/Announcements/An-update-to-our-policy-on-returns-for-digital-items/td-p/139765812`
- Etsy Open API discussion #1524, "Updated Requirements for Listing Drafts" (2026-01-29) —
  `https://github.com/etsy/open-api/discussions/1524`
- Etsy Listings tutorial — `https://developer.etsy.com/documentation/tutorials/listings`
- Canada Revenue Agency, "When to register for and start charging the GST/HST" —
  `https://www.canada.ca/en/revenue-agency/services/tax/businesses/topics/gst-hst-businesses/when-register-charge.html`

Cited but **not readable** from this environment (403), and therefore secondary wherever
relied on:

- `https://help.etsy.com/hc/en-us/` (shop policies, fees, Canadian remittances, VAT on
  digital items)
- `https://www.etsy.com/legal/fees/`, `https://www.etsy.com/legal/sellers/`
- `https://crtc.gc.ca/eng/com500/` (CASL guidance; the statute itself is at
  `https://laws-lois.justice.gc.ca/eng/acts/E-1.6/`)
- `https://eur-lex.europa.eu/EN/legal-content/summary/consumer-information-right-of-withdrawal-and-other-consumer-rights.html`
  (Directive 2011/83/EU overview; read through a search summary)
