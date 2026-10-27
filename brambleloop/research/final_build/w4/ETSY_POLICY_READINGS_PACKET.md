# Etsy policy readings: what to read, what to answer, and where to record it

**For the owner, or a reader the owner names. Prepared by W4-LAUNCH1 on 2026-10-27.**

This packet tells you what to read and where to record it. It contains **no answers**. Each reading must be made by a person, in their own browser, from the page itself. The company does not get past Etsy's bot protection. Automated requests to `etsy.com/legal` return HTTP 403 from DataDome, and Etsy's robots.txt disallows `/legal/handmade/` for software (`gates/policy_access.py`). A person reading the page is the honest source.

## Which sources, and why "six"

`gates/platform_policy.py:POLICY_SOURCES` watches **seven** sources today:
- the original **six policy surfaces** (Build 2, `gates/policy_knowledge.py`);
- `search_guidance`, added later (F-242).

**Required by a person: five sources.** The `etsy.com/legal` sources have no machine reader (`gates.policy_reader.external_sources()`):
- `seller_policy`
- `creativity_standards`
- `advertising_rules`
- `shilling_and_reviews`
- `children_and_baby`

**Read by machine: two sources.** These are hosted on the Help Center and read through Etsy's public article API (`gates.policy_reader.read_help_center`, basis `help_center_api`) when the production policy reader is on:
- `listing_image_rules`
- `search_guidance`

A person's page reading of these two is also accepted, and it outranks the excerpt seed.

**Recommendation.** Record all **six** surfaces below by hand. Etsy edited the image-rules article on **2026-10-22**: the Help Center API returned `edited_at: 2026-10-22T13:45:42Z` on 2026-10-27. Whether production has re-read it since is NEEDS PRODUCTION READBACK. `search_guidance` is the seventh source and is listed at the end.

**Why this is urgent now.** The repository's own readings are dated **2026-09-26** (`policy_knowledge.READ_ON`), and the freshness limit is 30 days (`platform_policy.MAX_AGE_DAYS`). As of 2026-10-27 every seeded reading is stale. This is confirmed by INTEG7 §"Date fix": tests had to pin their clock because "the real date had moved past a 30-day policy-freshness window".

## URL checks made for this packet (2026-10-27, one GET each, identifying user agent, no retry)

| URL | Result |
|---|---|
| `https://www.etsy.com/legal/sellers/` | 403 (bot protection; expected). It cannot be confirmed by software; a person must open it. |
| `https://www.etsy.com/legal/advertising/` | 403, as above |
| `https://www.etsy.com/legal/prohibited/` | 403, as above |
| `https://www.etsy.com/legal/prohibited-items/children/` | 403, as above |
| `https://www.etsy.com/legal/handmade/` | **not requested**: robots.txt disallows `/*handmade/` for software |
| Help Center API, article 115015663347 | 200: "Requirements and Best Practices for Images in Your Etsy Shop", edited 2026-10-22T13:45:42Z |
| Help Center API, article 360000336307 | 200: "How to Use Tags to Get Found in Search", edited 2026-04-21T15:22:37Z |

## How to record a reading (the same for every source)

**There is no Command Center screen for recording a policy page.** The only intake is the authenticated API. The Command Center only shows a review card **after** a reading registers as a change (see step 3).

**1. Open the URL in your own browser.** Read the page. Copy its full visible text.

**2. POST it to production with the operator token:**
```
POST https://<production host>/api/policy/snapshot
Authorization: Bearer <BRAMBLELOOP_OPS_TOKEN>
Content-Type: application/json

{
  "source":     "<one of the source keys below, exactly>",
  "text":       "<the page text you read, pasted in full>",
  "version":    "<the page's own 'last updated' / 'effective' date if it shows one, else the date you read it>",
  "summary":    "<your answers to the questions below, in your own words>",
  "read_by":    "<your name>",
  "checked_on": "<YYYY-MM-DD, the date you read it; optional, default today>"
}
```

Field rules are enforced by `app/main.py:api_policy_snapshot` and `gates.platform_policy.record_page_reading` / `record_snapshot`:
- `source` must be a `POLICY_SOURCES` key, or the request returns 400 with the list.
- `text` must not be empty. **Only its SHA-256 digest is stored.** The text is never stored or logged.
- `version` holds at most 120 characters. A longer value is refused, not truncated.
- `summary` is stored on the snapshot row, so keep it to the answers.
- `read_by` must not be empty.
- `checked_on` must be an ISO date that is not in the future. If it is older than 30 days, the reading is recorded but the stale incident stays open.

A successful reading:
- is saved with basis `page`;
- writes an audit row `policy.page_reading_recorded`;
- closes the open `policy_stale:<source>` incident.

**3. Review the change card.**

**Expected on the first reading of each source:** `record_page_reading` compares your digest with the previous snapshot of *any* basis. Your page text will never match the repository's excerpt seed, so the system records a **material change**. That change does three things until it is reviewed:
- opens a halting P1 `policy_changed:<source>`;
- appears in the Command Center under **`#/approvals`**, as the card "Etsy policy changed: \<source\>";
- blocks publishing.

To review it:
- open the card;
- choose `policy.review_preview`;
- choose `policy.review` (step-up);
- in `tested`, write what you re-checked.

This comparison quirk is LAUNCH_PATH blocker E3. Until it is fixed, budget about 2 extra minutes per source.

**4. Repeat within 30 days.** A reading goes stale after 30 days. A new reading also changes the policy section of the publication evidence, so it voids any publication grant approved before it (F-704: the grant digest binds the evidence).

## Why the readings gate publishing (code paths)

- **The approval packet's `policy` section.** `ops/publication_authority.py:_policy` takes the `freshness()` of all seven sources:
  - any never-read source gives UNKNOWN;
  - any stale or unreviewed source gives FAIL.

  `policy` is a GATED section. The Command Center refuses `publication.approve` unless every gated section is PASS (`app/command_center/approvals.py:_require_publication_evidence`). **No fresh readings means no publication grant from the Command Center.**
- **#39, material change.** An unreviewed material change on any source whose `affects` includes `publishing` blocks `store.publish` for every product (`publish/release_gates.py:staleness`). The incident halts publication (`runtime/release.py` policy watch).
- **#35, new classes.** `platform_policy.check_new_class` refuses to enable a product or asset class unless every source is fresh and reviewed.
- **The certificate stamp.** Every release certificate records `policy_stamp` (`certified_against_current_policy`).
- **The Build 2 / Final Master `rendered_pages` gate (#35/#39).** `platform_policy.page_readings_status` opens only on audited, person-named, current, reviewed page readings of the five `etsy.com/legal` sources.

---

## The six sources

### 1. `seller_policy`: Etsy Seller Policy

- **Exact URL (watched):** https://www.etsy.com/legal/sellers/
- **Affects:** `publishing`, `listing`, `support`. Because it affects publishing, a material change blocks `store.publish`.
- **Questions the system needs answered (put the answers in `summary`):**
  1. Does the Seller Policy still require a seller to **disclose in the listing** when an item is created with the use of AI? What wording or placement does it ask for?
  2. Does it still require listings to **accurately represent** the item?
  3. For **digital downloads**: is it still true that they cannot be returned or cancelled by the buyer, and that Purchase Protection covers files that are not as described or never delivered?
  4. Are **off-platform communication** and sharing contact or payment details still prohibited, and unsolicited promotional messages treated as spam?
  5. Is there any new rule about **digital patterns, AI-assisted designs, or rendered (non-photograph) listing images** that the repo's reading (`policy_knowledge.READINGS["seller_policy"]`) does not cover?
  6. What is the page's "last updated" date? Put it in `version`.
- **Why it gates:** the AI disclosure and accurate representation are the basis for `platform_policy.DISCLOSURES` (`ai_assisted_design`, `disclosed_render`) on every listing and PDF.

### 2. `creativity_standards`: Etsy Creativity Standards

- **Exact URL (watched):** https://www.etsy.com/legal/handmade/
  - The repo's reading cites `https://www.etsy.com/legal/creativity`. Whether `/legal/handmade/` redirects there is **UNKNOWN**, because software may not request it.
  - Open the watched URL. If it redirects, record the page you land on and note the final URL in `summary`.
- **Affects:** `publishing`, `creative_assets`, `product_creation`.
- **Questions:**
  1. Is **"designed by a seller"**, including original designs offered as a **digital download**, still one of the permitted categories? Does it still cover seller-prompted AI work?
  2. Is AI use still allowed **where the seller plays a clear creative role and discloses it in the listing description**? Has the required disclosure wording or placement changed?
  3. Are **packages of AI prompts** still prohibited? Is there any new prohibition that could reach an AI-assisted crochet **pattern** (instructions, chart, PDF)?
  4. Do reselling and misrepresenting another maker's design remain removal reasons?
  5. Last-updated date, for `version`.
- **Why it gates:** this source decides whether Brambleloop's product class (`SELLER_DESIGNED_DIGITAL` with `AI_ASSISTED_DESIGN` disclosure) may be sold at all. `check_new_class` refuses without it.

### 3. `listing_image_rules`: Requirements and Best Practices for Images

- **Exact URL (watched):** https://help.etsy.com/hc/en-us/articles/115015663347. It resolves to the "-Requirements-and-Best-Practices-for-Images-in-Your-Etsy-Shop" slug, verified 2026-10-27, and was edited by Etsy **2026-10-22**.
- **Related legal page, also cited by the repo's reading:** https://www.etsy.com/legal/policy/listing-image-requirements/253962679005. If the Help article links it, read it too, and record the legal-page answers in the same `summary`.
- **Affects:** `creative_assets`, `publishing`.
- **Questions.** Question 1 is the decisive one for launch: every Launch-0 listing uses **disclosed deterministic renders, not photographs** (D-FB-7). The first image is a labelled digital rendering.
  1. Does Etsy permit a **digital pattern listing** whose images, including the **first image**, are clearly labelled **digital renderings** of the finished design rather than photographs?
     - The repo's 2026-09-26 excerpt says listing images must be "your own photographs or video... not stock photos, **artistic renderings**...", and that computer-generated mockups may be used in additional images "just make sure your first image is the real deal".
     - Record exactly what the current page says about **renderings, mockups, illustrations and AI-generated images**, and whether it distinguishes a **digital download** (where the file is the item) from a physical item.
  2. Does it require **AI-generated or AI-assisted images to be disclosed**? Where: image, alt text, or description?
  3. Current technical rules:
     - maximum images per listing;
     - accepted formats;
     - minimum and recommended size;
     - thumbnail crop or aspect;
     - file-size limit;
     - the rules for the first image (orientation, minimum px).
  4. What changed in the 2026-10-22 edit, if the page says?
  5. Last-updated date, for `version`.
- **Why it gates:**
  - every gallery frame is judged under `platform_policy.ASSET_ROLES` and `publish.eligibility.may_export`;
  - `integrations.etsy_constraints` holds the image specs that `etsy_image_readiness` checks offline;
  - if renders may not be the first image, the whole Launch-0 image strategy (D-FB-7, D-FB-9) needs an owner ruling **before** any grant.

### 4. `advertising_rules`: Etsy Advertising and Promotion policy

- **Exact URL (watched):** https://www.etsy.com/legal/advertising/
- **Affects:** `growth`, `paid_media`. It does not affect `publishing`, so a material change does not block `store.publish` through #39. It still must be fresh for the approval packet's `policy` section to PASS.
- **Questions:**
  1. Offsite Ads:
     - the current fee rates (the repo has 15%, or 12% above US$10,000 in trailing-365-day sales);
     - the per-order cap (repo: US$100);
     - the attribution window (repo: 30 days);
     - whether participation is still optional below US$10,000 and mandatory above.
  2. Etsy Ads (onsite): any minimum daily budget, and any rule that ads may not claim what the listing does not.
     - The repo's values of US$3-5 per day and the US$25 per-listing threshold are marked UNVERIFIED (owner spec v0.8). Confirm or correct them, quoting the page.
  3. Any rule about advertising AI-assisted or digital items.
  4. Last-updated date, for `version`.
- **Why it gates:** `commerce.fee_schedule` and `paid_media` caps read these figures. No paid media runs without owner authority in any case.

### 5. `shilling_and_reviews`: Prohibited items and services (shilling / reviews)

- **Exact URL (watched):** https://www.etsy.com/legal/prohibited/. The repo's reading also cites https://www.etsy.com/legal/policy/shilling/243317364583.
- **Affects:** `growth`, `support`, `portfolio`. Like advertising, it is not `publishing`, but it is required for the `policy` section.
- **Questions:**
  1. Is it still prohibited to have friends or family buy and review, or to compensate anyone (free or reduced items, samples, cash) for a review?
  2. What are the exact conditions under which a friend's or relative's review is allowed?
  3. Does anything on the page restrict **pattern testers** who receive a free pattern or a test fee? Brambleloop's tester call promises "We never ask for reviews, ratings or favourites" (`tester_kit/OUTREACH.md`). Record whether a tester may review at all.
  4. Last-updated date, for `version`.
- **Why it gates:** the tester programme (blocker E7) and every growth action are bound by it. The Execution Directive forbids fake or incentivised reviews regardless.

### 6. `children_and_baby`: Children and Baby Products policy

- **Exact URL (watched):** https://www.etsy.com/legal/prohibited-items/children/. The repo's reading cites https://www.etsy.com/legal/policy/childrens-clothing-and-products/239344787532. There is no Help Center companion article (`policy_access.py`), so there is no machine signal at all.
- **Affects:** `publishing`, `product_creation`.
- **Questions:**
  1. Does Etsy still prohibit the **patterns, designs or instructions** for making prohibited children's items, not only the items themselves?
  2. What is the current list of prohibited and restricted children's items? Do any of them cover a **crochet baby blanket**, a **nursery basket**, or **hanging ornaments**?
     - Launch-0 includes `cloudline-baby-blanket`, `nordic-forest-mosaic-throw-baby` and the nursery baskets.
     - Record especially anything on **infant sleep accessories, blankets for cribs, small parts or choking hazards, and drawstrings or cords**.
  3. What are the current sleepwear and loungewear rules (sizes and flame resistance)?
  4. Effective / last-updated date, for `version`. The repo has "updated 2026-08-11; earlier effective 2026-06-02".
- **Why it gates:** a prohibited children's design must be refused **before** a CIR is written (`product_creation`). Two of the eight Launch-0 products are baby blankets; their children's statements (`products.launch0.childrens_assignment`) rest on this reading.

---

### Seventh watched source (machine-read; a person may also record it)

`search_guidance`:
- **URL:** https://help.etsy.com/hc/en-us/articles/360000336307-How-to-Use-Tags-to-Get-Found-in-Search. Verified 200; edited 2026-04-21.
- **Affects:** `listing`, `publishing`, `search`.
- **Read by:** `policy_reader` when the production reader is on.
- **To record by hand anyway, answer:**
  - the title character limit;
  - the maximum tag count and characters per tag;
  - whether a tag may start with a symbol;
  - whether attributes act like tags;
  - whether the Search Visibility page still exists.

  These are the six constants in `seo.constraints` that the search certificate enforces.

## What this packet does not do

- It does not pre-fill any answer.
- It does not fetch any `etsy.com/legal` page.
- It does not record a snapshot.
- It does not decide the render-as-first-image question; that is the owner's ruling, informed by the reading.
