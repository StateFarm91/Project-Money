# Owner canonical banner — publication assessment (lane B2, D-FB-17 + D-FB-18)

Generated 2026-10-06 (UTC) by `brambleloop.store_foundation.owner_banner.assess()`
(assessment version 2, after the owner's answers in DECISION_LOG D-FB-18).
Machine-readable record: `research/final_build/w3/owner_banner_candidates/owner_banner_assessment.json`
(regenerate with `owner_banner.write_evidence(Path("."))`; `tests/test_w3_b2_canonical_assets.py`
fails if this file and the code disagree).

**File:** `src/brambleloop/brand/owner_source/brambleloop_owner_banner_canonical.png`,
sha256 `048a199133f7589cc243cb876a7ee5b0f68b5d6530929a922c79de9eda64eb98`, 1983×793 RGB PNG
(2.50:1), byte-identical to what the owner supplied (re-hashed on every read; never edited; its
C2PA provenance chunk is kept).

**Verdict: still BLOCKED, now on 2 FAIL + 4 UNKNOWN.** 6 gates pass and 3 are advisory
UNVERIFIED_ASSUMPTION. The banner stays the canonical art target. Nothing has been substituted
or adopted.

Statuses: PASS (with evidence) · FAIL (with evidence) · UNKNOWN (blocks; never a pass) ·
UNVERIFIED_ASSUMPTION (advisory: an internal assumption Etsy does not state. It is never a
pass and never a verified failure, and it drives no redesign. D-FB-18 item 4).

## Etsy evidence (read-only GETs, 2026-10-06)

| Topic | Status | Source (retrieved / Etsy edited) | Etsy's words |
|---|---|---|---|
| Big banner size | VERIFIED (Help Center) | help.etsy.com article 115015663347, via the Help Center article API (`/api/v2/help_center/en-us/articles/115015663347.json`). Retrieved 2026-10-06T18:29:18Z; edited 2026-05-04T19:20:43Z | "The minimum required size for big shop banners is 1200 x 300px." "The recommended size is 1600 x 400px." "Image sizes are optimized for mobile displays." |
| Banner display | VERIFIED (Help Center) | article 115015663247. Retrieved 18:29:18Z; edited 2026-05-05T14:06:33Z | "Big Banner: A large image with a minimum size of 1200 x 300 pixels." "This image appears when shoppers view your shop on the standard view of the website as well as on mobile devices." |
| Banner aspect / crop | **NOT STATED** | both articles above | Neither article gives a required aspect ratio, a crop rule or a safe zone. 1600×400 is a *recommendation*. |
| AI disclosure | VERIFIED (Help Center) | article 360024112614. Retrieved 18:29:57Z; edited 2025-09-17T18:36:53Z | "…This category also includes seller-prompted AI creations." "Seller-prompted AI creations must disclose the use of AI." This is a rule about items offered for sale. No fetched text covers shop banners. |
| Seller Policy, Creativity Standards, seller handbook | **BLOCKED (HTTP 403)** | etsy.com/legal/sellers/, etsy.com/legal/creativity, etsy.com/seller-handbook/article/1275449912004. Retrieved 18:29:36Z | Nothing quoted. These stay UNVERIFIED. `gates.policy_knowledge` holds earlier search-engine excerpts: disclose AI "in your relevant listings". |

## Gates on the exact file

| Gate | Status | Evidence / why |
|---|---|---|
| `canonical_integrity` | **PASS** | The file is byte-identical to what the owner supplied. |
| `etsy_banner_minimum_and_format` | **PASS** | The file is a 1983×793 opaque PNG. That meets Etsy's minimum (1200×300) and recommended size (1600×400), as quoted above. These are published figures; Etsy's handling has not been observed because nothing has been uploaded. |
| `f233_banner_canvas_4to1` | **UNVERIFIED_ASSUMPTION** | The file is 2.50:1. "4:1" was only this repo's assumption. Etsy states no required ratio and no crop rule, so this is not a failure. |
| `f233_identity_block_survives_4to1` | **UNVERIFIED_ASSUMPTION** | The identity block is rows 44–636 (593 px tall). It would lose 104 px *if* Etsy centre-cropped to 4:1, which Etsy does not state. |
| `f233_identity_block_in_phone_window` | **UNVERIFIED_ASSUMPTION** | The block fits horizontally inside an assumed 2:1 window. Etsy publishes no phone crop. |
| `laura_identity` | **PASS (owner human review)** | D-FB-18 item 1: the owner confirmed the woman is Laura (`laura-r2-a42aeac7`). The review is bound to these exact bytes (`canonical_assets.OWNER_IDENTITY_REVIEWS`) and recorded as a resolved review (`confirmed_same_person`, reviewer "owner (D-FB-18)") in the `visual.identity_gate` queue. **It covers no other image.** Every other frame keeps the normal gate and queue (tested). No machine reading is claimed: the biometric floor is still unmeasured. |
| `laura_publication_status` | **FAIL** | `asset_status` = `not_for_publication`. D-FB-18 confirmed her identity, not publication. **What's missing:** `visual.canonical.PUBLICATION_APPROVED` is a per-asset sha set with no surface scope, and membership implies every customer-facing gate passed. So it cannot express "owner-approved for the storefront banner only", and photorealism/anatomy are unjudged. The model was not flipped. |
| `laura_photorealism_anatomy` | **UNKNOWN** | No vision reading exists, and none is invented. |
| `ai_generated_imagery_disclosure` | **UNKNOWN** | The file's own C2PA manifest declares it AI-generated (ChatGPT / gpt-image, OpenAI-signed; signature not verified here). Etsy's verified text requires AI disclosure for *items for sale*. No verified Etsy text says what a shop banner requires, and the policy pages returned 403. **No marketing sentence is added on the strength of C2PA** (D-FB-18 item 9), and the provenance metadata stays in the file. |
| `laura_never_claims_human_in_text` | **PASS** | `TRUTH_LAURA_HUMAN_CLAIM` fires on no transcribed word. |
| `laura_ai_disclosure_at_banner` | **PASS** | Both the store disclosure and the About say Laura is an AI. The banner adds no human claim, and no verified rule requires AI wording inside the image. |
| `product_truth` | **UNKNOWN** | D-FB-18 item 2: the crochet is classified `brand_lifestyle_concept` and mapped to **no** pattern. Product Truth is unchanged. The repo's rules permit a generated `mood_frame` only as a listing image that makes no claim about the object; no rule, and no fetched Etsy text, covers concept crochet on a storefront banner. Whether a shopper reads it as for sale is unmeasured. Hence UNKNOWN, with task VT-B2-1 recorded. |
| `nav_categories_truth` | **FAIL** (reported truth finding) | The banner's baked-in nav names Wearables, Gifts and Seasonal, which hold no pattern. The owner chose not to alter the source file. Every generated surface hides those categories until populated (`store_foundation.navigation`). |
| `public_copy_truth_lint` | **PASS** | No truth rule fires on any transcribed word. |
| `visible_text_complete` | **UNKNOWN** | No OCR is installed. The transcription's completeness is unverified. |

**Logo footer** (not a banner gate): it reads HOME · BABY · GIFTS · SEASONAL. Gifts and Seasonal
are empty. Same treatment: the pixels are untouched, and generated navigation shows only Home
and Baby.

## Categories (D-FB-18 item 3)

`store_foundation.navigation`: public navigation = categories with ≥ 1 product (today Home,
Baby). Wearables, Gifts, Seasonal (and the planned Blankets) remain in the category
architecture (`copy_v2.SECTIONS`). They are hidden until populated. The preview's section chips
and visible shop text name no hidden category (tested).

## Recorded Visual tasks (not started — paid generation needs owner spend approval)

- **VT-B2-1 — GATED.** Reproduce the banner scene with verified Brambleloop products in place of
  the concept crochet, preserving Laura, the warm room, the central identity, the tagline and
  the feel. Owner review comes before any public replacement. Trigger: the Product Truth review
  says concept crochet is unsuitable publicly, or matching products exist.
- **VT-B2-2 — NOT_REQUIRED_BY_EVIDENCE.** Recompose the same scene at Etsy's verified banner
  dimensions, preserving Laura, the warm room, the lifestyle aesthetic, the central identity,
  the crochet/yarn environment, the tagline, balance and feel. Owner review comes before
  replacement. Etsy states no required ratio, so this opens only if Etsy evidence, or the
  owner's in-app check after an owner-approved upload, shows the composition is cropped.

## Earlier reframes — REJECTED by the owner (D-FB-18 item 4)

`owner_banner_candidates/A_crop_4x1_top_anchored.png` (cut the tagline/heart/category line) and
`B_pad_4x1_edge_colour.png` (edge padding) are marked `REJECTED_BY_OWNER` and cannot be
adopted. Decision: **kept as small historical evidence** (≤ 300 KB each, deterministic) so the
record of what was proposed and rejected stays auditable. `simulation_centre_crop_4x1.png`
shows one possible Etsy crop; it was never a candidate.

## Shop icon (D-FB-18 item 5)

The A3 micro-mark is **owner-approved** at Etsy's tiny icon sizes, where the canonical B is
measured unreadable: 2.62:1 contrast at 40 px, legible from 70 px. Approval is recorded as
`canonical_assets.DERIVATIVE_APPROVALS["shop_icon"]` and appears in `shop_icon_choice()`. The
hero logo is unchanged.

## Still gated (owner / verification)

1. **Laura publication approval for this banner.** It needs an owner publication decision plus
   a per-surface approval in `visual.canonical` (the model can't express one today), plus
   photorealism/anatomy readings.
2. **Product Truth on the concept crochet** (human reading or a policy ruling), or VT-B2-1.
3. **Nav text baked into the banner.** Publish only when those categories hold products, or the
   owner decides otherwise.
4. **Etsy's banner AI-disclosure requirement.** Needs a human/owner reading of the Seller
   Policy / Creativity Standards pages (403 to automated readers).
5. **Visible-text completeness** (human check).
6. **Real Etsy crop.** The owner checks it in the Etsy app after an owner-approved upload.
