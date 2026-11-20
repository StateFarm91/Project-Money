# Etsy settings checklist — owner login required (lane W3-I)

Prepared 2026-10-06 (UTC). Everything here needs the owner signed in to Etsy; none of it can be
done by this system (no Etsy write is authorised in Shadow Mode, and several fields have no API).
Batched by **where in Etsy you are**, so each batch is one place, one sitting.

**Path status.** `VERIFIED` = the click path is quoted from an Etsy Help Center article read on
2026-10-06 (article id given; evidence in `ETSY_REQUIREMENTS.md`). `UNVERIFIED` = no Etsy
article read today gives the path; follow Etsy's screens and tell us what you saw. Etsy moves
settings between "Info & Appearance", "Your shop" and the "Shop home editor"; its own articles
disagree in places, and where they do both routes are given.

**Assets.** Every file to upload comes from the store-foundation build (lanes A/B/C), not from
this checklist. Do not upload an asset that is not marked *certified for publication* in the
Command Center. In particular the current Laura portrait is **internal only / not
publication-approved** (D-FB-11..13): do not upload it anywhere in Etsy yet.

**Prerequisite.** Several fields (shop title, announcement, About) exist only "once your shop
is open" (Etsy 360000343708, 115015628487). BrambleloopStudio exists (2026-09-19) with no
listings; whether Etsy considers it "open" for these fields is **UNVERIFIED** here. If a field
is missing, it is that, not you — skip it and note it.

Total estimated time: **~55–70 minutes** across 7 batches (A is the only one that blocks
engineering work; the rest can wait for certified assets).

---

## Batch A — Etsy app re-authorisation (blocks real-Etsy proof) · ~6 min

| # | Setting | Path | Expected choice | Why | Min | If you wait |
|---|---|---|---|---|---|---|
| A1 | Re-authorise the Brambleloop Etsy app | Command Center → `GET /api/etsy/oauth/start` → open the URL it returns → Etsy consent screen → Allow (path: repo `integrations/etsy_authorise.py`, VERIFIED in code) | Grant **all** requested scopes, including `transactions_r` (the 2026-09-25 grant lacked it) | Without it nothing can confirm against real Etsy: the taxonomy id (66) and its required attributes, form/array encoding, image upload, read-back and delete all stay LOCALLY_TESTED only | 5 | Every Etsy write claim stays a reading of a document; the shop cannot see its own orders |
| A2 | Tell us the shop's state | Shop Manager home | Report: is the shop "open" (can you see *Add a shop title* / *Announcement*)? | Decides whether batches C/D can be completed now | 1 | We keep the "open?" status UNVERIFIED |

## Batch B — Your account (not the shop) · ~5 min

Path root: **Your account → Account settings** (VERIFIED, 115015651948).

| # | Setting | Path | Expected choice | Why | Min |
|---|---|---|---|---|---|
| B1 | Public profile picture | Account settings → Public profile → Browse/Choose file → Save Changes (VERIFIED) | The **Brambleloop logo mark** (square PNG/JPG, ≥ 400 x 400, < 10 MB, no transparency) — **not Laura** | This picture belongs to the *account holder*. Etsy shows it as the person behind the account; an AI persona there would present Laura as the legal account holder, which spec/07 forbids. Must be square or Etsy distorts it. | 2 |
| B2 | Preferred name | Account settings → About You → Edit public profile → Your Name → Change or remove (VERIFIED, 360000337387) | Your own name, or remove it. Not "Laura", not "Brambleloop" | Etsy: "can't be a business name"; it must be a real person's name | 1 |
| B3 | Bio | Account settings → Edit profile → About field (VERIFIED, 115015651948) | Leave blank or one honest line about the owner | Shop story belongs in the shop's About section | 1 |
| B4 | Two-factor authentication | Account settings → Security (UNVERIFIED path) | **On** | Protects the shop and the OAuth grant; Etsy requires 2FA during onboarding (115015672808) — confirm it is still on | 1 |

## Batch C — Settings → Your shop (+ Shop home editor) · ~20 min

Path root: **Shop Manager → Settings → Your shop** (VERIFIED, 115015628487 / 115015663247 /
115015710568). The Shop home editor is reached from there ("Shop home editor", top right) or
**Shop Manager → Sales Channels → pencil icon next to your shop name** (VERIFIED).

| # | Setting | Path | Expected choice | Why | Min |
|---|---|---|---|---|---|
| C1 | Shop name | Your shop → Shop name → Edit | **Keep `BrambleloopStudio`** (17 chars, valid: 4–20, no spaces/punctuation). Do not change it | Etsy allows only 5 self-service changes once open and every change shows a "name changed" icon for 45 days | 0.5 |
| C2 | Logo (shop icon) | Your shop → Logo → Add → Add file → crop (square) → Save | The **certified** logo PNG, 500 x 500 (min 500 x 500, < 10 MB), opaque background, mark centred with margin | Etsy: a shop with no logo may lose search visibility. Transparent pixels render black. The display mask shape is not published — the mark must survive a circle anyway | 2 |
| C3 | Shop title (tagline) | Shop home editor → "Add a shop title" (VERIFIED, 360000343708) | Lane C's tagline, **≤ 55 characters**. ⚠ The current repo title `Crochet patterns checked row by row before they are sold` is **56** characters and too technical — use the v2 copy | 55 is Etsy's limit; title shows under the shop name and in Google results | 2 |
| C4 | Banner | Shop home editor → Banner → choose type → Done (VERIFIED, 115015663247) | **Big Banner**, the certified 1600 x 400 file (min 1200 x 300). If no banner is certified yet choose **None** (Etsy: listings move up, logo becomes the main branding) — never upload the rejected v1 banner | Phone crop is not published by Etsy: after upload, open the shop in the **Etsy app on a phone** and confirm the wordmark is whole; report what you see | 4 |
| C5 | Announcement | Shop home editor → Announcement → Add/Edit → Save (VERIFIED) | Lane C's announcement; keep it short (Etsy publishes no limit; our cap 160) | Seasonal/notice line; can only be set once the shop is open | 2 |
| C6 | About your shop | Shop home editor → About section (VERIFIED) | Lane C's About text (**≤ 5,000 chars**), including the proportionate AI disclosure | Etsy: "Seller-prompted AI creations must disclose the use of AI" (360024112614) | 4 |
| C7 | Shop team | Your shop → Shop team → Add a team member (VERIFIED, 360000336867) | **You (the legal owner) as "Owner"**. Do **not** add Laura with the role "Owner" | Etsy: an Owner "must also be making, designing… [and] is responsible for any activity on the account". Laura is an AI persona and not the legal owner (spec/07). Whether and how Laura appears (About text, featured photo labelled as an AI brand representative) is decided by the store-foundation certification; human Laura's consent to public use of her name/likeness is an owner action recorded in spec/07 | 3 |
| C8 | About featured photos | Shop home editor → About → Featured photos | Up to 5, jpg/png/gif ≤ 2 MB, shown cropped to 760 x 468. **Only certified images**; renders captioned as renders, never as photographs | Customer truth (directive §16) | 0 now (later) |
| C9 | Location | Your shop → Location | Canada (your real province) | Required truthfulness; used for tax display | 1 |
| C10 | Listing order | Your shop → Listing order → Edit → **Custom** → Save (VERIFIED) | Custom | Lets the hero products lead; new listings otherwise jump to the top | 1 |
| C11 | Sold listings visibility | Your shop → Shop basics (VERIFIED that it exists) | Off until there are sales worth showing | An empty sold page reads as no sales | 0.5 |

## Batch D — Listings → Sections · ~6 min

Path: **Shop Manager → Listings → Sections → Organize your listings / Manage → Add section**
(VERIFIED, 360000345048).

| # | Setting | Expected choice | Why | Min |
|---|---|---|---|---|
| D1 | Create the sections | The certified section list (current repo: Blankets & Throws · Seasonal & Holiday · Home & Table · Baby & Nursery · To Wear · Collections & Bundles). Each name **≤ 24 chars** (longest today 21); max 20 sections | Declared shape before listings. Empty sections stay hidden from shoppers, so creating them now is safe | 5 |
| D2 | (later) Featured listings | Listings → star 4 listings → Listing status → Featured listings → Manage (VERIFIED) | The 4 certified hero listings, once active | Shown above the announcement | 0 now |

## Batch E — Settings → Info & Appearance · ~5 min

Path: **Shop Manager → Settings → Info & Appearance** (VERIFIED, 360000337107, 115015663247).

| # | Setting | Expected choice | Why | Min |
|---|---|---|---|---|
| E1 | Message to Buyers | Lane C's post-purchase message | Shown on the receipt and confirmation email | 1 |
| E2 | Message to Buyers for **Digital Items** | Lane C's digital message (how to download, US/UK terms files, how to get help) | Etsy: "If you sell digital items, include a Message to Buyers for Digital Items" — it shows on the buyer's Downloads page | 2 |
| E3 | Order receipt banner | Optional: certified banner ≥ 760 x 100, or leave empty | Branding on receipts | 1 |

## Batch F — Settings → Policy Settings · ~10 min

Path: **Shop Manager → Settings → Policy Settings** (VERIFIED, 115014372467). Desktop or mobile
web only — not the Seller app.

| # | Setting | Expected choice | Why | Min |
|---|---|---|---|---|
| F1 | Returns & exchanges | **Nothing to create** for a digital-only shop | Etsy: these policies are for non-digital items | 0 |
| F2 | Cancellations | Owner decision from lane C's draft. Suggested: cancellations **off** for instant downloads, with the "we fix the pattern" remedy stated in policy/FAQ | Etsy offers a shop-wide toggle and time frame | 2 |
| F3 | Privacy | Create a policy → paste lane C's privacy text → Publish | Etsy recommends all sellers have one; PIPEDA/CASL context | 3 |
| F4 | Fixed policies | View only (Instant downloads preset) | Not editable | 0 |
| F5 | FAQ | Paste lane C FAQ incl. pattern licence / copyright (path UNVERIFIED; Etsy says licensing info "may" go in FAQs) | Licence belongs here because `policy_additional` is **EU-shops only** — sending it from a Canadian shop is an error (Open API) | 4 |
| F6 | EU/Omnibus "trader" status | Leave as Etsy set it unless you registered a business; owner/legal decision | Etsy auto-adds "trader" for business sellers shipping to EU | 0.5 |

## Batch G — Settings → Options and Offsite Ads · ~3 min

| # | Setting | Path | Expected choice | Why | Min |
|---|---|---|---|---|---|
| G1 | **Allow buyers to purchase digital prints** | Shop Manager → Settings → **Options** → "Allow buyers to purchase digital prints" → **Disabled** (VERIFIED, 43476182453399, edited 2026-09-24) | **Disabled** | Etsy is auto-enrolling eligible US/Canadian digital listings in a test where a third party (Ventur Editions) sells a printed item made from the buyer's file. A crochet pattern PDF printed as a physical item is not our product, conflicts with the pattern licence, and puts a third party's product next to ours | 1 |
| G2 | Offsite Ads | Shop Manager → Settings → **Offsite Ads** → Opt out (VERIFIED, 360000338367) | **Owner decision.** No spend: Etsy charges 15% of an attributed order (cap US$100/order) only when a sale happens. Opt-out is available only while the shop has never made US$10,000 in 365 days. Suggested: stay enrolled at launch (reach at zero fixed cost) unless Finance shows a pattern price cannot carry 15% | It is a fee on margin, not a spend; recorded so it is a decision rather than a default | 1 |
| G3 | Etsy Ads | Shop Manager → Marketing (UNVERIFIED) | **Off** (no budget) | No paid-media authority exists; code enforces CA$0 | 0.5 |

---

## What this checklist deliberately does not include

- **KYC, banking, billing card, set-up fee, tax numbers** — already handled at shop creation
  (2026-09-19) or separate owner/legal items; not store settings.
- **Listing creation/activation** — no listing is published in Shadow Mode; activation is a
  separate gated owner approval.
- **Real-Etsy upload confirmation** — becomes possible only after A1; the probe sequence
  (`integrations.etsy_probe`) then runs draft → upload → read back → delete without publishing.

## After you finish — send us

1. Screenshot (phone, Etsy app) of the shop top fold with the banner (C4).
2. Which fields were missing because the shop is not "open" (A2).
3. The OAuth completion page result (A1).
