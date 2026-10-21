# W4-LAUNCHPREP: the smallest legitimate physical test, and what is still outstanding on Etsy

**Context**
- **Branch:** `claude/w4-LAUNCHPREP`, cut from `origin/claude/w4-LISTREADY` (9a4f99d).
- **Type:** documentation and research only. No code changed, no test suite run (a
  certification suite is running on this machine).
- **Production read:** b931d17, SHADOW, on 2026-10-21. Only unauthenticated public GETs:
  - `/api/audit` for `etsy.shop_snapshot`, `store.shop_sync`, `store.owner_confirmed`,
    `tester.agreement_recorded` and `physical.recorded`;
  - W-LISTREADY's scratch copies of 2026-10-20: `/api/launch`, `/api/incidents` and
    `/api/etsy/surfaces`.
- **Etsy:** no API call. The public storefront `etsy.com/shop/BrambleloopStudio` answers
  **HTTP 403** to this environment (WebFetch and curl), so nothing was read from it.
- **Owner correction (2026-10-21), applied:** these were done by the owner on 2026-10-11 and are
  **not** owner tasks here:
  - the banner and the logo;
  - the About section and shop story, and Laura's member biography;
  - the cancellation and privacy policies;
  - Etsy Payments and the Canadian bank account.
- **Companion files** (prepared text, no new copy):
  - `launchprep/paste_text.md`: the FAQ, and the delivery text in case a box exists;
  - `launchprep/observation_templates.json`: the two shop-observation bodies;
  - `launchprep/coaster_physical_test_template.json`: the physical-test intake body.

---

# Task A: the smallest legitimate physical test for a first sale

## A1. What the gate actually requires

There are three readers of physical evidence. The strictest one decides.

| reader | code | requires |
|---|---|---|
| first-sale gate **`physical_sample` (B4)** | `launch/first_sale.py:120-128` | A **`full_physical_make`** bound to this exact content, for **every** release of the product. The product row is the worst of its releases (`first_sale.py` `build`, `summary = _worst(...)`). |
| first-customer area **`gauge_and_size_claims`** | `gates/first_customer.py:300-341` with `gates/risk_matrix.py:471-486` | A passed sample bound to this content, of the class the risk tier needs. With no tier, the default is `partial_physical`. A full make satisfies a partial requirement (`satisfies`, `risk_matrix.py:89-104`). |
| first-customer area **`listing_claims`** | `gates/first_customer.py:749-751` | "Made by a tester" style phrases need a `full_physical_make` (F-072). |

**Binding** (`gates/certificate.py:437-499`): a row binds only when it:
- passed;
- has `completed_at`;
- is for the same slug@version;
- carries the **same content hash** as the US text of this release.

A changed hash reports the sample as invalidated.

**Passing** (`quality/physical.py:235-272`, `assess` at lines 120-194):
`passed = usable_for_calibration and size_agrees is not False`. That means:
- the yardage factor (measured metres / twin metres) is between **0.4 and 2.5**;
- there is no ERROR finding: unknown colour name, instructions not followed, or an implausible
  factor;
- every reported dimension is within **12 %** of the twin (`SIZE_DISAGREEMENT`).

A size disagreement also opens a defect that **halts that product's publication**
(`runtime/release.py:2953-2960`).

**So: a gauge swatch plus a section is not enough for a first sale.**
- A swatch is `partial_physical` (`SCOPE_CLASS`, `risk_matrix.py:93-97`).
- That would clear `gauge_and_size_claims` for a Class A or B product.
- It would **not** clear `physical_sample` (B4), which reads only `full_physical_make`.
- **The whole item must be made.** "Whole item" means everything the buyer's pattern makes.

The twin's yardage is multiplied by the pattern's `make` count (`cir/twin.py:335`). So a
"set of four" sample must contain all four pieces: one coaster weighed against the four-coaster
estimate gives a factor of about 0.25, which is an ERROR and does not pass.

## A2. Quickest product: `hexagon-coaster-set@1.2.0`

Every figure below is computed from the CIRs on this branch. Make hours come from
`seasonal.leadtime` and are ESTIMATED: 700 sts/h, +0.6 h finishing per piece, +colour changes.

| product (releases) | releases a first sale needs | stitches | yarn (twin, ±20 %) | est. make h | construction | risk (effective) |
|---|---|---|---|---|---|---|
| **hexagon-coaster-set** | **1** | **672** (4 × 168) | **28.8 m** DK cotton (cream 22.6, wine 6.2) | 3.46 | flat hexagon, 7 joined rounds from a magic ring; one contrast round; 4 pieces | **A** |
| housewarming-key-basket@0.1.0 | 1 | 1,332 | 73.9 m worsted cotton (cream 42.5, pine 31.4) | 2.61 | 24 rounds, base then walls (closed 3-D form), **10 stripe colour changes** | B (dimensional_form) |
| nursery-nesting-baskets (small, medium, large @1.2.0) | **3** (worst-of-releases) | 1,050 + … | 52.1 + 112.2 + 192.8 = 357 m | 2.15 + 3.88 + 6.20 = 12.2 | 3-D baskets | B |
| nordic-star-ornaments@1.5.0 | 1 | 864 (6 × 144) | 49.3 m | 5.63 | 6 flat panels from a chain | A |
| mosaic-placemat-pair@1.4.0 | 1 | — | 217.4 m | 7.27 | 2 flat panels | A |
| nordic-forest-mosaic-throw-baby@1.3.0 | 1 | — | 311.7 m | 8.86 | blanket | A |
| cloudline-baby-blanket@1.2.0 | 1 | — | 605.4 m | 15.27 | blanket | B (high_yardage) |
| winter-village-graphghan@1.3.0 | 1 | — | 650.1 m | 18.55 | blanket | B (high_yardage) |

**Why the coasters, and not the key basket that the estimator says is faster (2.61 h against
3.46 h):**
- **Half the stitches.** The coasters have 672 stitches; the key basket has 1,332.
- **The estimator's gap is its finishing allowance.** It assumes 0.6 h of finishing per piece,
  so the four coasters carry 2.4 h of the 3.46 h. That rate is assumed, not measured
  (`leadtime.Assumptions`, line 116).
- **Simplest construction.** The coasters are flat: no walls, no turning a base into a side.
  They have 2 colour changes per piece; the key basket has 10 stripe changes.
- **Least yarn.** 28.8 m, which is one small ball of each colour.
- **Lowest risk of a failed, product-halting sample.**
  - Class A means a flat-form prediction; the closed 3-D wall height of a Class B basket is
    exactly the risk its class exists for.
  - A coaster that disagrees by more than 12 % halts only the coasters, but the point is a
    sample that passes.
- **One release.** The baskets would need three makes, small, medium and large: about 12 h and
  357 m.

The trade-off is stated honestly. A key-basket make would calibrate the **worsted cotton / sc**
yardage factor (`calibration_key`, `quality/physical.py:197`). The three nesting baskets share
that factor too, though they still need their own makes for B4. The coasters calibrate only
**DK cotton / sc**, which no other Launch-0 product uses. For the *first sale*, the coasters are
the quickest legitimate path.

## A3. What must be physically made

**The complete set of four hexagon coasters**, worked from the customer PDF of
`hexagon-coaster-set@1.2.0`, either the US or the UK file.
- That release's content hash is
  `3754ed17a63b790dc2c04b0f744de3fad34e5893ca69c0ff9f0c7cb41090937b`.
- Before starting, work a 10 × 10 cm sc gauge swatch (the tester-kit protocol).
- The swatch is the tester's own check. It is not the evidence.

## A4. Required evidence

**Enforced by code.** Missing items are refused, or do not bind:

| field | rule | source |
|---|---|---|
| `slug`, `grams_by_color`, `ball_band_grams`, `ball_band_metres` | required, otherwise 422 | `app/main.py:4868-4876` |
| `grams_by_color` keys | exactly **`cream`** and **`wine`**; any other name is `SAMPLE_UNKNOWN_COLOUR` (ERROR) | `physical.py:135-141` |
| ball band | **one** band for both colours, so buy both colours in the same yarn line | `SampleReport.ball_band` |
| `version` | `1.2.0`; the default would be `1.0.0` | `release.py:2911` |
| `scope` | `full_make`, which **must** carry a finished measurement or it is refused | `risk_matrix.scope_to_class` |
| `content_hash` | the hash above; a sample of other text binds nothing | `release.py:129-140`, `certificate.py:472-480` |
| `measured_width_cm` / `measured_height_cm` / `measured_around_cm` | across the points / across the flats / perimeter, unstretched. Each within 12 % of the twin's **9.7 / 8.4 / 29.0 cm** (accepted ranges 8.5–10.9 / 7.4–9.4 / 25.5–32.5 cm) | `physical.py:163-180` |
| `instructions_followed` | must be true, otherwise `SAMPLE_DEVIATED` (ERROR) | `physical.py:182-186` |
| `tester_ref` | defaults to **"owner"** if omitted, so always send the tester's roster ref (F-071) | `release.py:2924` |

**Recorded but not enforced:** `hook_mm` and `hours`. The `hours` figure calibrates the
make-time rate in `leadtime.calibrate_from_samples`.

**Required by the spec, carried in `notes`** (F-076, Final Master v1.0 §8):
- the version worked, US or UK terms, and skill level;
- any yarn substitution (brand and fibre);
- gauge (sts and rounds per 10 cm);
- completion status;
- confusion points and corrections, by round number;
- all four coasters' individual measurements. The payload carries the **mean**.

**Photos: not required by any gate.** The tester-kit protocol asks for top and side daylight
photos. They are recorded separately through `POST /api/physical-photo {slug, sha256, source}`.
A listing may use them only with the tester's recorded `photo_scopes`.

The full payload, with every measurement left as a placeholder, is in
`launchprep/coaster_physical_test_template.json`.

## A5. Yarn and material cost (CA$)

| item | quantity | CA$ |
|---|---|---|
| DK-weight 100 % cotton, cream | 1 ball (needs 22.6 m ±20 %, so up to 27 m; any ball ≥ 50 m) | **≈ 4–8, ESTIMATE** (not price-checked) |
| DK-weight 100 % cotton, wine, same yarn line | 1 ball (needs 6.2 m, up to 7.4 m) | **≈ 4–8, ESTIMATE** |
| 5.0 mm hook (the CIR's gauge hook), tapestry needle, 4 markers | a tester usually owns these | 0–10, ESTIMATE |
| 1 g kitchen scale, cm tape | the tester's own | 0 |
| **total materials** | | **≈ CA$8–26, ESTIMATE** |

- The risk matrix's own costing (`owner_action_spec`) is 34.6 m × CA$0.06/m = **CA$2.07**.
- That costs metres, not the whole balls a tester has to buy, so the ball estimate above is the
  realistic one.
- **Precision note.** About 12 g of cotton in total is used, so a 1 g scale gives roughly
  ±10–15 % on the factor. That is well inside the 0.4–2.5 band, but coarse as a calibration.

## A6. Tester time

| basis | hours |
|---|---|
| make, code estimate (`launch0.make_hours`) | 3.46 |
| tester allowance (×1.3 for write-up, `TESTER_TIME_MULTIPLE` / `owner_action_spec`) | **4.5** |
| plus swatch, weighing, measuring 4 pieces, photos (tester-kit protocol) | +0.5 |
| **planning figure** | **about 4–5 h**. Likely less in practice (672 sc), but nothing measured yet |

**Spend ceiling (the risk matrix's own formula):** 4.5 h × CA$20/h + 35 m × CA$0.06 =
**CA$92.03, ESTIMATED**. No measured tester rate exists. This is consequential spend, so the
owner must approve it; it is **not approved here**.

## A7. Can an authorised external tester do it? Yes, and must

**The tester must be external.**
- F-071: the owner is never the tester.
- The owner parked self-crocheting (DECISION_LOG B-532).

**Recording, as the code requires:**
1. **Roster.** `POST /api/tester/agreement` (operator credential, `app/main.py:1309-1358`)
   with:
   - `handle_ref` and `specialties`;
   - **`express_consent: true`** and `consent_source` (the CASL consent must already exist);
   - optional `photo_scopes` and `agreed_on`.

   It returns the tester's `ref`. The first outreach message needs the owner's explicit
   confirmation of its exact wording (DECISION_LOG directive, item 9).
   **Production today:** 0 `tester.agreement_recorded` rows and 0 `physical.recorded` rows.
2. **The make.** The tester works the customer PDF of exactly this release.
3. **Intake.** The operator (not the tester) enters the record sheet with
   `POST /api/physical-test`.
   - This is a default-deny route that needs the operator credential.
   - It queues `physical.record` under `quality_director`.
   - The job writes the `PhysicalTest` row stamped with `evidence_class` and `content_hash`.
   - It can open a halting defect if the size disagrees.
4. **Dependency on the deploy.**
   - `physical.record` loads "the CIR the chain examined" for slug@version
     (`release.py:129-140`).
   - `hexagon-coaster-set@1.2.0` has **never been drafted in production** (LISTREADY §4).
   - The intake must therefore wait until the LISTREADY release is deployed and R5 has seeded
     the coasters. The coasters are 3rd in listing order; at one seed an hour that is a few
     hours.
   - **The tester can start now.** The PDF is a deterministic build, and the record only has to
     wait for the hash to exist in production.
   - Before sending the payload, check that the certified release's hash equals the one above.

## A8. What it closes, and what it does not

**Closes, for `hexagon-coaster-set@1.2.0` only, once a passing row binds:**

| requirement | id | where |
|---|---|---|
| first-sale physical sample | `physical_sample` (blocker **B4**) | `launch/first_sale.py:120-128` |
| first-customer gauge and size claims | area `gauge_and_size_claims` | `gates/first_customer.py:300-341` |
| first-customer listing claims: physically evidenced | area `listing_claims` (`physically_evidenced=True`) | `gates/first_customer.py:749-751` |
| inventory row "gauge_and_size_claims → physical_sample" | `products/inventory.py:381` | |
| Build-2 gate `physical_proof` (#64), which opens on the first completed `PhysicalTest` row | `build2/executor.py:933` | |
| this release's row in launch requirement `risk_based_physical_evidence` | `launch/readiness.py:750` | |
| DK cotton/sc yardage calibration (F-075, F-082); first measured make-time rate (F-083) | `quality/physical.calibration_from_db`, `leadtime.calibrate_from_samples` | |

**Does not close:**
- `risk_based_physical_evidence` as a whole. The other Class B releases still need their own
  evidence.
- Any other product's B4.
- `vision_review` (B3), `etsy_category` (B2), `etsy_upload_confirmed` or `publication_grant`.

**Copy that becomes untrue for the coasters only**, and must be changed by the company before it
is re-pasted:
- the FAQ answer "Has this pattern been made up in yarn? Not yet by us…";
- the CIR's "Computed, not yet measured on a worked sample".

---

# Task B: what is genuinely outstanding on Etsy

## B1. Why the snapshot reports three failures

Production's daily `getShop` reading (`etsy.shop_snapshot`):
- **2026-10-18, 10-19, 10-20:** evidence FRESH. Failures: `banner_set`, `policy_shipping_set`,
  `policy_additional_unset`, `has_a_digital_listing`.
- **2026-10-21 00:04:29Z:** NO_EVIDENCE, because Etsy returned a 429 per-second rate limit
  (see E6).

The readings are **not stale**: they postdate the owner's 2026-10-11 setup. They are not the
whole truth either.

| check | field read | what it saw | diagnosis |
|---|---|---|---|
| `banner_set` (`intel/etsy_surfaces.py:2194`) | `getShop.image_url_760x100` | blank | **Our check is wrong (E1).** That field is the only banner field in Etsy's Shop schema. Our own shop sync already records that "a big banner may not appear there" (`store_foundation/shop_sync.py:84-87`). The 2026-10-06 checklist (C4) told the owner to choose a Big Banner, and the owner reports the banner done. Blank here is **missing evidence, not a missing banner**. The same false reading also opened the `store.live:owner_field_blank:shop_banner` P3 and half of the `etsy.shop:incomplete` P1. |
| `policy_shipping_set` (`etsy_surfaces.py:2204`) | `getShop.policy_shipping` | blank | **Probably our check (E2); needs one owner glance.** The verified 2026-10-06 path (Help 115014372467; W3 checklist F1–F5) found, for a digital-only shop, only a fixed, non-editable "Instant downloads" policy and no delivery text box. If that is still so, the check demands a field the owner cannot type. Delivery is already told to every buyer by `digital_sale_message` (PASS) and the FAQ. |
| `policy_additional_unset` (`etsy_surfaces.py:2210`) | `getShop.policy_additional` | **non-blank** | **Our check is wrong (E3).** It requires the field blank because Etsy's *updateShop* documentation says only EU shops may *send* it. Etsy itself holds a value for this Canadian shop, so "must be blank" is not a readiness fact. Nothing is missing, and nothing should be deleted. |
| `has_a_digital_listing` | `digital_listing_count` | 0 | Genuinely missing. It is the publication grant (LISTREADY §9 #9), not a shop setting. |

**Passing on 2026-10-20**, so configured and verified by the API:
- icon;
- title;
- **announcement**;
- **message to buyers for digital items**;
- payment, refunds and privacy policy text;
- Etsy Payments onboarded;
- not on vacation;
- currency CAD.

The policy-consistency incident `etsy.shop:policy_inconsistent` is **P2**: the live
shipping/refunds/privacy text "differs from canonical". That is because the owner wrote their
own wording. No contradiction was found; a contradiction would raise P1. The live text is
authoritative.

## B2. Reconciliation: every storefront item

Classes:
- **(1)** configured and verified;
- **(2)** configured, but needs a fresh production readback;
- **(3)** genuinely missing;
- **(4)** needs an owner-only confirmation.

| item | class | evidence |
|---|---|---|
| Shop logo / icon | **1** | getShop `icon_url_fullxfull` set (10-20); owner 10-11 |
| Banner | **2 → 4 after fix** | owner 10-11. The API cannot show a Big Banner (E1). One tap in the Command Center will count once E1 lands. No re-upload. |
| Shop title (tagline) | **1** | `title` set (10-20) |
| Announcement | **1** | `announcement` set (10-20). Nothing to paste. |
| About and shop story | **2** | owner 10-11. No API field, and no `store.owner_confirmed` row exists. Not read by any first-sale gate. An optional one-tap record lets the Laura-disclosure advisory run. |
| Laura's member biography and role | **2** | owner 10-11. No API, and no record. Same as above. |
| Message to buyers (digital) | **1** | `digital_sale_message` set (10-20) |
| Privacy policy | **1** | `policy_privacy` set; owner 10-11 |
| Cancellation / returns | **1** | `policy_refunds` set; owner 10-11; return policies read by `getShopReturnPolicies` (200) |
| Payment policy | **1** | `policy_payment` set (10-20) |
| **Shipping / delivery policy for digital items** | **4** | blank on the API. Owner: is there an editable delivery box? (E2) |
| Returns and exchanges for digital downloads | **1** | Etsy permits no returns on digital listings. The refunds text is set, and the FAQ carries the remedy. |
| Additional policies | **2** | non-blank on the API. Our check is wrong (E3). Its content is not shown anywhere we can read (E7). No owner action. |
| **FAQ** | **4 (3 if empty)** | no API field. The owner did not list it as done; check, and paste if empty |
| Etsy Payments | **1** | `is_etsy_payments_onboarded` true; owner 10-11 |
| Payout bank account | **2** | owner 10-11 (Canadian bank). Not in the API, and no `store.owner_confirmed` row. Optional one tap. **Not** a first-sale gate input. |
| **Seller identity / KYC** | **4** | No API. `legal_and_tax.identity_verified` must be the owner's dated reading. Etsy Payments onboarding suggests it is done, but that is not evidence. |
| **Tax interview / GST/HST position** | **4 (3 if undecided)** | No API. It is an owner decision: register now, or open as a small supplier, and whether to give Etsy a number (`commerce/shop_package.py:596`). Not decided in any record. |
| **Messaging: notifications and reply window** | **4** | Etsy has no messaging API. `messages` needs `notifications_inbox` plus `reply_window_hours`. Etsy's own standard is a first reply within 48 h (`support/response_watch.py`). |
| Currency, location, vacation | **1** | CAD; `is_vacation` false |
| Two-factor | **2** | Etsy required it at onboarding. No API; optional one tap. |
| A digital listing | **3** (not a shop setting) | `digital_listing_count` 0. The publication grant, LISTREADY §9. |
| Orders read (`reauthorise_transactions_r`) | **2** | Shown open in production, but receipts were read fine on the LISTREADY build (`gate_missing: []`). Clears with the deploy. |

## B3. Owner checklist: only what is genuinely outstanding

### Now (no deploy needed): about 25–45 minutes, CA$0

Use Etsy in a desktop browser or mobile web; the Seller app does not show Policy settings.
- No Etsy URL could be verified from here (Etsy answers 403), so paths are menu paths.
- Shop Manager is normally `https://www.etsy.com/your/shops/me` (UNVERIFIED).

| # | action | where | prepared text | min | cost | recorded where |
|---|---|---|---|---|---|---|
| 1 | **FAQ:** if the FAQ list is empty (or partial), paste the 15 Q&As in order | Shop Manager → Settings → Policy settings → FAQs (path UNVERIFIED; W3 F5) | `launchprep/paste_text.md` §1 | 10 | 0 | No API. Tell the company what you pasted. It is recorded by the Store tab's FAQ confirm (`store.owner_confirmed`, key `faq`) |
| 2 | **Delivery policy:** look for an editable delivery/shipping text box for digital items. If there is one, paste the delivery text. If there is only the fixed "Instant downloads" policy, change nothing and say so | Shop Manager → Settings → Policy settings (VERIFIED 2026-10-06, Help 115014372467) | `launchprep/paste_text.md` §2 | 3 | 0 | Your one-line answer decides E2. If you pasted, the next daily `getShop` shows it |
| 3 | **Messages:** check that new-message email notifications are on, note the address they go to, and choose a reply window (≤ 48 h recommended by Etsy's standard) | Account settings → Emails / notification settings (the repo says "Shop Manager > Settings > Emails"; path UNVERIFIED) | — | 5 | 0 | Recorded after the deploy as row D1 below |
| 4 | **Identity and tax:** check that Shop Manager shows identity verification complete. **Decide** the GST/HST position: small supplier or registered, and whether to give Etsy a GST/HST number | Shop Manager → Settings → Legal and tax information (and Finances → Payment settings for verification status; paths UNVERIFIED) | none: a tax position is yours alone, and the repo takes none (`shop_package.CLAIMS`) | 15–30 | 0 to record. Advice, if you want it, falls under the registry's CA$250 ceiling for this decision | Recorded after the deploy as row D2 below |
| 5 | **Physical test (Task A):** approve commissioning one external tester for the coaster set, and approve the exact outreach message | a direct owner decision. Requirement key `physical_evidence:hexagon-coaster-set@1.2.0:3754ed17a63b` (`risk_matrix.retest_key`). A Class A release may have no card in the queue, because its risk tier needs no physical evidence; the B4 gate does | the spend ceiling and payload in Task A | 5 | **≤ CA$92.03 ESTIMATED** tester + about CA$8–26 yarn (not approved) | `tester.agreement_recorded`, then `physical.recorded` |

**Optional, record-only (nothing to set up):** the Command Center Store tab → Live shop
settings has one-tap **Confirm** buttons already deployed in b931d17. They are available for:
- About;
- shop members;
- payout details;
- two-factor;
- banner.

These record what you did on 2026-10-11 as `store.owner_confirmed`, valid 90 days. Today they do
not change a first-sale gate. Once E1 lands, the banner confirmation will.

### After the listings release is deployed: about 5 minutes, CA$0

The `messages` and `legal_and_tax` observation pages do **not exist** in production b931d17
(added by FIRSTSALE2), so production would answer 400 today.

| # | action | route and exact fields | min |
|---|---|---|---|
| D1 | Record the messages reading from item 3 | `POST /api/etsy/shop-observation` with `page: "messages"`, `observed_at`, `complete: true`, `values.notifications_inbox` (text) and `values.reply_window_hours` (number > 0), plus `statement`. Closes `etsy_surface:messages_watch`. FRESH 30 days. | 2 |
| D2 | Record the identity and tax reading from item 4 | same route with `page: "legal_and_tax"`, `values.identity_verified` (**true** only if Etsy shows it complete), `values.tax_position` (text) and `values.decided_on` (ISO date). Closes `etsy_surface:legal_and_tax_setup`. FRESH 90 days. | 2 |

- Both bodies are in `launchprep/observation_templates.json`.
- The route needs the operator credential (`Authorization: Bearer` with `BRAMBLELOOP_OPS_TOKEN`).
  There is no phone card for it yet (E5).
- **There is no `about` page** in this intake (`shop_observations.PAGES`). About is recorded with
  the Store-tab confirm above.

## B4. Engineering findings for W-LISTREADY

These are defects in our checks, not in the shop. Nothing here relaxes a rule.
- Each fix replaces "blank field = missing" with an evidence path that actually exists.
- UNKNOWN stays UNKNOWN; it never becomes PASS.

| id | file:line | defect | fix |
|---|---|---|---|
| **E1** | `intel/etsy_surfaces.py:2194`; `runtime/etsy_ops.py:95` | A blank `image_url_760x100` is judged FAIL. Etsy's Shop schema has no Big Banner field, so blank is not evidence of absence. `info_and_appearance_setup` can never close for a Big-Banner shop. | Blank → **UNEVIDENCED** (not FAIL). Close `banner_set` on either a set `image_url_760x100` or a fresh (≤ 90 d) `store.owner_confirmed` row for `banner` (`shop_sync.SETTINGS`, `owner_confirmable=True` already). An owner statement of "no banner" stays FAIL. Resolve `store.live:owner_field_blank:shop_banner` on the same evidence. |
| **E2** | `intel/etsy_surfaces.py:2204`; `runtime/etsy_ops.py:97,104` | `policy_shipping_set` demands a free-text field that, per the verified 2026-10-06 path, a digital-only shop's Policy settings does not expose. | Once the owner's item-2 answer confirms there is no box: for a shop with only digital listings, treat a blank `policy_shipping` as not applicable. Evidence is the owner's dated reading, plus a non-blank `digital_sale_message`. If a box exists, keep the check as it is. |
| **E3** | `intel/etsy_surfaces.py:2210`; `runtime/etsy_ops.py:99` | `policy_additional_unset` turns an *API write* restriction (EU-only `updateShop` field) into a readiness rule. Etsy holds a value for this Canadian shop. | Remove it from `CLOSES_ON_SHOP_CHECKS["policy_settings_paste"]` and from the snapshot's FAIL set. Keep the write-side refusal (`shop_package.py:543-547`, `etsy_constraints.py:281`). Add `policy_additional` to the policy-consistency comparison, so its **content** is checked for contradictions with the licence and refund facts. |
| **E4** | `launch/readiness.py:1572-1574` | Any failing shop check lists **every** surface's owner action as open. That is why `payment_settings_setup` shows open although `etsy_payments_onboarded` passes. | Map each failing check to its own action through `CLOSES_ON_SHOP_CHECKS`. A check with no action, such as `has_a_digital_listing`, should point to the publication grant. |
| **E5** | `commerce/estate_api.py:69`; `commerce/shop_observations.py:28-56` | The `messages` and `legal_and_tax` readings can be recorded only with the operator bearer token. There is no Command Center card, so the owner cannot do it from the phone. | Add a Store-tab card (session + CSRF + nonce, like `/store/settings/{key}/confirm`) that calls `shop_observations.record` with the same validation. |
| **E6** | `runtime/etsy_ops.py:906` and `:1310` | On 10-21, `store.shop_sync` (5 GETs at 00:04:04Z) and `etsy.shop_snapshot` (00:04:29Z) read `getShop` in the same minute. The snapshot got a 429 and was not retried until the next day. | Have the snapshot reuse the sync's same-day `getShop` body, or retry with backoff on a 429. (The 10-20 reading stays FRESH until 10-27.) |
| **E7** | `store_foundation/shop_sync.py:79-127` | `SETTINGS` has no rows for `policy_shipping`, `policy_payment` or `policy_additional`, so neither the owner nor the company can see what those fields hold. | Add read-only CONFIRMED-LIVE rows showing presence and a short excerpt. That would settle E3's content question with no owner action. |

## B5. Not on this list, on purpose

- Banner, logo, About, Laura's biography, the cancellation and privacy policies, and Etsy
  Payments with the bank account: done by the owner on 2026-10-11.
- Announcement and the message to buyers for digital items: verified set by `getShop`.
- The listing-fee acceptance and the publication grant, the funded image review and the deploy
  approval: tracked in LISTREADY §9. They are not Etsy settings.
- No brand asset paths are given, because the banner and icon are already uploaded.
  - The repository's canonical banner (`048a199133f7`, D-FB-17) is still failing its own
    Laura-publication gates (`/api/launch` storefront requirement).
  - It is not proposed as a replacement.
