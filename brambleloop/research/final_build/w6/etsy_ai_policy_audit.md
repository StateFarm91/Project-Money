# Etsy AI / authorship / listing-photo policy audit (ENG-ETSY-AI-POLICY, fix round ENG-ETSY-AI-FIX)

Branch `eng/etsy-ai-policy`, base `a35ad302`. Read 2026-11-19. Nothing here deploys, publishes
or spends. Not legal advice.

## 1. Research: what could and could not be read

How each page was read, stated per page (ENG-ETSY-AI-FIX, review M6). "API" means the public
Zendesk Help Center article endpoint `https://help.etsy.com/api/v2/help_center/en-us/articles/<id>.json`,
fetched by an automated `curl` with no login, cookies or bot-protection workaround; the JSON
`body` was HTML-stripped and each quote below was string-matched against it. No page was read
in a browser, and no page was read by a person.

| Page | How read | Accessed (UTC) | Result |
|---|---|---|---|
| help.etsy.com article 44297885802647 | API, automated | 2026-11-19 (first attempt); **re-fetched and quotes re-verified 2026-11-19 by ENG-ETSY-AI-FIX** | HTTP 200, `edited_at` 2026-11-11T14:26:29Z, all 6 quotes below match verbatim |
| help.etsy.com article 115015663347 | API, automated | 2026-11-19 (first attempt); **re-fetched and quotes re-verified 2026-11-19 by ENG-ETSY-AI-FIX** | HTTP 200, `edited_at` 2026-11-06T18:10:09Z, all 5 quotes below match verbatim |
| help.etsy.com articles 115015628347, 115015628707, 360000336547 | HTML, automated, by the first attempt (ENG-ETSY-AI-POLICY) | 2026-11-19 | Reported read; **not re-verified in the fix round** -- treat those quotes as secondary |
| etsy.com/legal/creativity-standards, /legal/creativity, /legal/handmade, /legal/sellers, /legal/prohibited, /legal/policy/listing-image-requirements/253962679005 | automated GET | 2026-11-19 | **HTTP 403** (bot protection). Not read. No evasion attempted. |
| Seller Handbook articles 1522733284810, 1275449912004 | automated GET | 2026-11-19 | **HTTP 403**. Not read. |
| help.etsy.com articles 360000343608, 34707360607511 | automated GET | 2026-11-19 | **HTTP 404** |

**Rules quoted from pages actually read** (exact text):

* 44297885802647: "Etsy requires at least one unedited photo for most items." / "Craft patterns,
  recipes, seeds, or similar items: Include at least one real, unedited photo of something made
  using your product. AI-generated images cannot be the only images used to show the finished
  result." / "Sellers must still disclose when an item is created using AI and cannot misrepresent
  AI-generated work as handmade or entirely their own creation." / "we allow AI-generated art when
  sellers play a clear creative role in what they create and are transparent about their
  process" / "Don't use AI to hide damage or change an item's appearance in a way that could
  mislead buyers." / digital items "without a visual component" may use representative AI imagery.
* 115015663347: "Your listing must include at least one unedited photo of the actual item against
  a real background" / "If you sell functional guides like patterns, recipes, or instructions,
  you'll also need to show an actual result made using your instructions, not an AI-generated or
  simulated result, so buyers know what to expect." / "Your first listing image does not need to
  be the unedited photo, but make sure it is the clearest, most realistic representation of the
  item buyers will receive." / **"If you use AI to edit any of your listing photos, note whether
  images were edited in your listing description."**
* 115015628707 / 360000336547: handmade items "made and/or designed by you"; sellers must
  "Physically make or create the original designs for your items" (handmade section) and "If you
  work with a production partner, you must disclose that production partner in your relevant
  listings." Digital items "must be made and/or designed by you, the seller" (115015628347).

**Unverified, do not rely on.** A web-search summary (not a page I could open) claimed an October
2026 Seller Handbook update says "AI-generated functional guides such as patterns, recipes and
instructions are no longer allowed". I could not read that article (403). The two Help Center
articles I did read do not say it; they require a *real photo of a result made from the
instructions*. If the claim is real it reaches every Brambleloop pattern (AI-assisted design).
That is an owner decision (`sample_photo.py` already says so); see Owner exceptions.

The Seller Policy sentence the code quotes ("If an item is created through the use of artificial
intelligence, you must disclose this in your relevant listings") and the Creativity Standards
"Designed by a seller ... seller-prompted AI art ... digital download" sentence are repository
excerpts (`gates.policy_knowledge`, basis `search_engine_excerpt_of_official_page`); I could not
re-read them first-hand.

## 2. Rule vs code

| # | Rule | What the code does | Status | Fix |
|---|---|---|---|---|
| 1 | Instructions not misrepresented as handmade/own creation | Instructions are deterministic CIR compilation validated by code, not an LLM prompt. PDF carries `AI_DISCLOSURE`; description carries `DISCLOSURES["ai_assisted_design"]`, enforced by `gates.policy.check_listing` (`POLICY_AI_DISCLOSURE_MISSING`). | Compliant | none |
| 2 | Copy must not claim human authorship / physical evidence | Fix round (review H1): structural guard. Authorship, making, testing and sample statements come only from a closed allowlist (`etsy_ai_policy.honest_statements`); any such claim in the remaining free text is refused after Unicode/case/spacing/joiner normalisation, all inflections and UK spellings. Wired into the listing-package gate `gates.policy.check_listing` (release drafting, certificate, first-customer doors, list-ready, listing tests), `manual_adoption.truth_problems` (owner-accepted live copy) and `integrations.etsy.build_payload`. A refusal raises an owner hold card with its reason (`etsy_ai_policy.hold_card`). | **Gap (fixed)** | tests `test_w6_etsy_ai_policy.py` (adversarial and false-positive corpora) |
| 3 | AI use disclosed in the listing | `ai_assisted_design`, `generated_imagery`, `disclosed_render` sentences generated from asset facts; `policy.check_listing` requires them verbatim. Fix round (H2b): before, an unclassified package owed nothing; now `check_ai_disclosure` requires `ai_assisted_design` on every package, classified or not. | **Gap (fixed)** | `gates.policy.check_ai_disclosure`; a mutant returning `[]` fails `test_w6_etsy_ai_policy` |
| 3a | Etsy AI policy for functional guides unresolved (see "Unverified" above) | Fix round (H2a): `etsy_ai_policy.publication_status` is UNKNOWN until a named person records a reading (`etsy_ai_policy.reading` audit row, PERMITTED/PROHIBITED, dated on or after 2026-11-11). UNKNOWN and PROHIBITED add a reason to `release_gates.for_publish`; staleness, rebuild retries and certification are untouched. | **Held (UNKNOWN)** | owner exception B |
| 4 | Pattern: at least one real unedited photo of something made with the product; first image should be the clearest realistic view | `publish.sample_photo` (`SAMPLE_PHOTO_REQUIRED`): photo through `physical_upgrade.intake`, SHA-256 on file, unedited attestation, passed FULL physical make bound to the release hash, and it must be the **first** certified frame. Refuses at activation, reports at draft. Stricter than Etsy (first image need not be the photo). | Compliant (gate) / **owner action** (no photo exists) | owner exception A |
| 5 | AI images not the only finished-result images | `platform_policy.ASSET_ROLES`: a generated image in a photograph role is refused however labelled (B-184); deterministic renders of own chart permitted, labelled; `disclosed_render` copy says "no sample has been photographed" unless a qualifying photo leads. | Compliant | none |
| 6 | "If you use AI to edit any of your listing photos, note whether images were edited" (115015663347, new 2026-11-06) | Fully generated/rendered images are covered by `generated_imagery`/`disclosed_render`. No path edits the unedited sample photo (intake refuses edited/AI-processed). No explicit "edited" note exists for AI-*edited real photos*, but no such photos are produced. | Compliant today; **unknown** if owner supplies edited extra photos | `owner_images` already marks `ai_generated_owner_submitted`; owner exception C |
| 7 | `who_made` | `ListingPayload.who_made = "i_did"` unconditionally; values validated against `i_did/someone_else/collective`; drift of it vs Etsy is an incident. No attestation gate. | **Unknown / owner** | Cannot be resolved in code: it is a representation by the account holder. Owner exception B. Not changed (changing it unprompted would be a decision, not a fix). |
| 8 | `when_made=made_to_order`, `is_supply=True`, `type=download` | Fixed defaults, read-back compared (`POLICY_FIELDS`). Etsy values for digital patterns not first-hand verified here. | Unknown | none |
| 9 | Production partners | None used; `production_partner_ids` is read back from Etsy but never sent. Digital files are not produced by a partner. | Compliant (n/a) | owner exception B if a partner is ever declared |
| 10 | Prompt bundles not sold | Not a product class. | Compliant | none |
| 11 | Watched policy freshness | `listing_image_rules` is read by `gates.policy_reader` from article 115015663347; `sample_photo.ETSY_SOURCES` quotes the 2026-10-22 version of that article. | Gap, docs only | `etsy_ai_policy.SOURCES` records the 2026-11-06/11-11 text; the owner reviews policy #39 |

## 3. Policy #39 — what `listing_image_rules` detected

`ops.policy_watch` (daily) runs `gates.policy_reader.read_help_center`, which fetches Help Center
article **115015663347** ("Requirements and Best Practices for Images in Your Etsy Shop") through
the public article API and digests the text (`platform_policy.record_snapshot`). A *material
change* is just a digest difference against the previous reading on the same basis
(`help_center_api`); it is not a judgement.

The article was edited **2026-11-06T18:10:09Z**. The repository's last quoted version is the
2026-10-22 edit (`sample_photo.ETSY_SOURCES`). I cannot see the production snapshot table, so I
cannot say which prior digest it compared with. By text, what is new relative to the quoted
2026-10-22 version is:

1. "Outside of your required unedited photo, you can still use photo-editing tools, including AI,
   to adjust lighting or color, crop or resize images, or change backgrounds."
2. "Your first listing image does not need to be the unedited photo, but make sure it is the
   clearest, most realistic representation of the item buyers will receive."
3. "If you use AI to edit any of your listing photos, note whether images were edited in your
   listing description."

(The 10-22 quote's "Make your first listing photo the clearest..." wording is replaced by (2).)
The functional-guide sentence (real result, not AI/simulated) is unchanged.

**What the owner reviews:** whether the change affects any certified listing. Effect on the
code: none loosens a gate. (2) means our "photo must be first frame" rule is stricter than Etsy;
I kept it (never weaken). (3) is a description-disclosure duty only for AI-*edited* photographs;
Brambleloop's images are generated renders, already disclosed. The owner acknowledges the
change in the Command Center policy form after reading the page in a browser. This note is not
a substitute for that reading.

## 4. Owner exceptions

* **A. Real sample photograph (blocks first activation).** Crochet a sample from the certified
  release, photograph it unedited against a real background, upload it through the
  physical-photo intake (`publish.physical_upgrade.intake`). Required by 44297885802647 and
  115015663347. Max cost: yarn and time. Consequence of waiting: listings stay in draft.
* **B. Authorship attestation.** Etsy's `who_made`/Creativity category is a statement by the
  shop's human owner. Decide whether "I did"/designed-by-seller is truthful for AI-assisted,
  compiler-generated patterns (the owner is the seller-designer directing the system) and record
  it; also decide whether the unverified "AI-generated functional guides are no longer allowed"
  claim reaches this shop by reading the Seller Handbook in a browser (403 to automation). If it
  does, the compliant channel is human-authored patterns, not disclosure. Minutes: ~15.
* **C. Edited extra photos.** If you add any AI-edited photograph, add the note "images were
  edited" to the description.
