# Handoff — W3 lane I (Store/Etsy technical readiness)

Branch `claude/w3-I` (base `claude/v11-CANON` @ f0c2d12). Local commits only; nothing pushed.
Phase stays shadow; no Etsy call was made with any credential; no spend.

## Interface exported (first commit, bd9bf66)

`brambleloop.integrations.etsy_constraints` — for lanes B (preview) and G (SEO):

- `CONSTRAINTS[key]` → `Constraint(key, surface, what, value, basis, source, quote, enforced, note)`;
  `value(key)` raises `LookupError` for UNKNOWN (never a made-up number).
- `summary()` → JSON: every constraint with its quote and source (Etsy article id, URL,
  `edited_at`, retrieved 2026-10-06), counts by basis, the taxonomy/attribute call flow,
  taxonomy-id status.
- Checkers returning findings `{code, severity: fail|warn|unverified, detail, constraint,
  basis, source}`: `image_problems(surface, width=, height=, nbytes=, fmt=, transparent=,
  animated=, position=)`, `image_bytes_problems(surface, data)`, `image_info(data)`,
  `digital_file_problems([(name, size)])`, `text_problems(field, text)` (shop_title, about,
  announcement, section_name, listing_title, tag, alt_text, digital_sale_message),
  `shop_name_problems(name)`. Surfaces: shop_logo, profile_photo, big_banner, mini_banner,
  receipt_banner, about_photo, listing_image.
- `reconcile()` → every Etsy number the codebase asserts vs the evidence (never raises).

Key verified values: logo ≥ 500x500 (<10 MB, square crop); profile photo ≥ 400x400 square
(account-level); big banner min 1200x300 / rec **1600x400**; mini banner min 1200x160 / rec
1600x213; mobile banner crop **UNKNOWN**; listing images ≤ 20, rec ≥ 2000 px, first ≥ 635 px,
landscape/square first, jpg/gif/png/svg/heic only, no transparency/animation; thumbnails cut
square/portrait/landscape (ratios UNKNOWN); digital files ≤ 5 × 20 MB, names ≤ 70
`[A-Za-z0-9._-]`; title 140; tags 13 × 20, no leading `'`/`-`; shop title **55**; about 5000;
sections 20, name **24**; announcement limit UNKNOWN; materials count and description length
UNKNOWN (repo's 13 / 102400 unsourced).

## Requirements addressed

| Requirement | Status | Notes |
|---|---|---|
| Exact crop/size requirements (icon, banners, mobile crop, profile photo, listing images, thumbnail crop) | COMPLETE except mobile crop + thumbnail ratios = UNKNOWN (Etsy publishes none) | `ETSY_REQUIREMENTS.md` |
| Digital file limits | COMPLETE | 115015628347 |
| Field limits (title, tags, materials, description, sections, announcement, About) | COMPLETE; materials count, description length, announcement length UNKNOWN | |
| Taxonomy/attribute API flow | COMPLETE (documented + `TAXONOMY_FLOW`); taxonomy id 66 still UNVERIFIED — GATED on owner re-auth/keystring | |
| Reconcile constants and fix disagreeing code in lane-I files | COMPLETE | `.webp` removed; file-name/type/size refusal; publish preflight; tag leading punctuation; schema matrix text |
| Image upload + file attach + read-back proof vs local fake | COMPLETE (LOCALLY_TESTED) | real PNG/JPEG bytes; sha256 of received bytes; rank/alt/pixel read-back; negative cases |
| Real-Etsy confirmation | GATED | owner re-authorisation (checklist A1) |
| Owner settings checklist | COMPLETE | `ETSY_SETTINGS_CHECKLIST.md`, 7 batches, ~55–70 min |

## Files

Created: `src/brambleloop/integrations/etsy_constraints.py`, `tests/test_w3_etsy_constraints.py`,
`tests/test_w3_etsy_upload_readback.py`, `research/final_build/w3/ETSY_REQUIREMENTS.md`,
`research/final_build/w3/ETSY_SETTINGS_CHECKLIST.md`, this file.
Modified: `integrations/etsy.py` (IMAGE_CONTENT_TYPES, `digital_file_refusals`,
`publish_preflight`, source comments), `integrations/etsy_verify.py` (`verify_images`,
`ImageReadBack`, `PENDING`), `publish/listing_schema.py` (`TAG_NO_LEADING`, matrix text),
`tests/fake_etsy.py` (records sha256 of received image/file bytes; reports real image
dimensions instead of 1x1 — backward compatible; lane-I Etsy test infrastructure).

## Tests (run individually with the brambleloop venv, PYTHONPATH=src)

New: `test_w3_etsy_constraints.py` 17 OK; `test_w3_etsy_upload_readback.py` 9 OK.
Kept passing (see final counts in the integrator message): test_etsy, test_etsy_capability,
test_etsy_exercise, test_etsy_oauth_callback, test_etsy_property_contract,
test_etsy_readback_observe, test_etsy_surfaces, test_etsy_transport, test_listing_schema,
test_listing_parity_gate, test_r2_product_listing_writes, test_r2_product_client_grant,
test_r2_product_seo_unicode, test_vacuity, test_secret_scan.

## Runtime proof

- Evidence fetches (read-only, 2026-10-06): 20 Help Center articles via
  `help.etsy.com/api/v2/help_center/en-us/articles/<id>.json` (HTTP 200); HTML pages still 403;
  Open API document HTTP 200 (911 KB). Third-party guides consulted, not used.
- `test_upload_attach_and_read_back_confirm_what_was_sent`: real client + UrllibTransport →
  loopback fake: createDraftListing, uploadListingFile, 2 × uploadListingImage (2000x2000 PNG,
  2400x2000 JPEG); fake's received sha256 == sent; `verify_images` MATCH on rank/alt/px;
  `verify_files` and `runtime.etsy_ops.read_back` verified.

## WIRING REQUESTS (files lane I does not own)

1. **Lane C (copy):** `commerce.shop_package.shop_text()['title']` is **56** chars; Etsy's limit
   is **55** (360000343708). copy_v2's tagline must be ≤ 55; `etsy_constraints.reconcile()`
   checks `store_foundation.copy_v2.TAGLINE`/`SHOP_TITLE` when present.
2. **Lane C / owner of commerce.shop_package:** `shop_text()['policy_additional']` is
   populated; Open API: policy_additional "should only be set for shops located in the EU…
   outside of the EU, will result in an error". Brambleloop is Canadian → never send it via
   updateShop; licence goes in FAQ/About/listing (checklist F5). `store_foundation/content.py`
   marks `policy_licence` as API_WRITABLE via policy_additional — should be OWNER_MANUAL (FAQ).
3. **store_foundation.limits** (owner per brief: C/B): replace UNKNOWN/REPO_ASSERTED rows with
   verified values: `shop_title` 55, `section_name` 24, `shop_name` 20 (min 4, no
   spaces/punctuation), `about` 5000 VERIFIED, `sections_count` 20 VERIFIED, `banner_px`
   1600x400 (min 1200x300), `icon_px` 500x500; keep `announcement`, `faq_*`, `policy_text`,
   `digital_sale_message` UNKNOWN. Simplest: read from `etsy_constraints.CONSTRAINTS`.
   The module docstring's "Etsy's help pages refuse automated readers" is now outdated (the
   article API works).
4. **Lane B (preview):** `brand.storefront_preview.SECTION_LABEL_MAX = 30` (ASSUMED) exceeds
   Etsy's verified 24; use `etsy_constraints.value("section_name_max_chars")`. Use
   `image_bytes_problems("big_banner"| "shop_logo"| "profile_photo", png)` on exported assets;
   mobile crop is UNKNOWN — label the phone crop in the preview as an assumption.
5. **runtime/etsy_ops.images_read_back** (owner: runtime): replace the alt-text-only
   comparison with `etsy_verify.verify_images(expected, remote)` where expected carries the
   width/height from `etsy_constraints.image_info(bytes)`; treat PENDING as "re-read before
   activation", never as verified.
6. **Lane G (SEO):** constants in `commerce.seo`/`commerce.search` agree (140/13/20). Add the
   leading `'`/`-` tag rule (now in `listing_schema.tag_problems`) if seo truth checks tags
   separately; materials count and description length are UNKNOWN (do not present 13/102400
   as Etsy's).
7. **commerce.shop_package.SOURCES['etsy_help'], intel.etsy_surfaces:** note that the help
   centre is readable via its article API (do not change their tests' meaning without the
   owner lane).

## Open defects / could NOT verify

- Mobile banner crop geometry; thumbnail crop ratios; announcement/FAQ/policy/digital-message
  limits; materials count; description length — Etsy publishes none (UNKNOWN).
- Logo circular mask: folklore only.
- Taxonomy id 66 and required attributes; API behaviour of any upload; whether the shop is
  "open" — all GATED on owner login/re-auth.
- FAQ and 2FA/Etsy Ads click paths: UNVERIFIED (marked in checklist).
- Help Center "verified" means Etsy publishes it, not that Etsy enforced it on this shop.
