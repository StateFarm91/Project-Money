# Publication approval package: template for the first Etsy publish

**Prepared by W4-LAUNCH1, 2026-10-27, from the repo at `d8f5e852`. Production runs `ee35a493`, SHADOW.**

This is the package the owner reads before the first publish. The system already produces it as data. This template sets out the same sections in reading order. Every value the repo can supply is filled in; everything else is **PENDING**, with the exact source the live package reads it from.

**Live sources of this package:**
- **Draft grant (store.publish).** `POST /api/owner/publication/preview` returns `content` (the exact payload plus the F-704 evidence), `digest` and `display`. In the Command Center: **`#/approvals`**, card **"Create the Etsy draft for {slug} v{version}"**, action `publication.preview`.
- **Activation grant (store.activate; the listing goes live).** `POST /api/owner/activation/preview`, the same card flow with `activation.preview` and `activation.approve`.
- **Whole-catalogue view.** `GET /api/cc/launch/packet` (`launch.packet.build`, F-878).

**Binding rule (F-704).** The grant digest binds the payload **and** the evidence. If any section below changes after approval, including a new policy reading, the grant is void.

**Not passing means no approval.** The Command Center refuses approval unless every gated section is `PASS` (`approvals._require_publication_evidence`). UNKNOWN is never shown as passing.

**The preview can refuse.** `publication_authority.snapshot` raises unless all of these hold:
- the release is certified with this hash;
- a drafted listing is bound to it;
- the listing's taxonomy is CHOSEN and its search profile is certified PASS (`etsy_ops.certified_payload`).

Today the search certificate fails (LAUNCH_PATH E4), so **the preview itself cannot be generated yet**.

---

## 0. Decision requested

| Field | Value |
|---|---|
| Action | **Draft:** record a sealed 24 h owner publication grant for `{slug}@{version}`, release `{release_hash}`. `store.publish` then creates an **inactive** Etsy draft. **Live:** a second, separate activation grant. |
| Recommended first product | **market-basket-small@1.2.0** ("Crochet Hexagonal Bread Basket"). FROM REPO: it is the only product with a tester kit bound to its exact content hash (`1ddde587…`), so it can be the first to clear the physical gate. This is a recommendation, not a decision. |
| Phase at approval | must be `limited_production`, with environment and record agreeing. Today: **shadow** (PENDING: `GET /api/owner/phase`). |
| Kill-switch | `BRAMBLELOOP_PUBLISH_AUTHORISED` must be `1` at execution. Today: PENDING (Railway variable; not read here). |
| Grant lifetime | 24 h from approval; revocable through `POST /api/owner/publication/{id}/revoke` |

## 1. Product(s)

| Field | market-basket-small (recommended first) | Source |
|---|---|---|
| Candidate | nursery-nesting-baskets (small of S/M/L) | `products.launch0` |
| CIR slug @ version | market-basket-small@1.2.0 | VERIFIED (repo) |
| Title in CIR | Crochet Hexagonal Bread Basket | VERIFIED (repo) |
| Finished size (twin, at stated gauge) | 16.0 cm across points, 13.9 cm across flats, 8.7 cm wall | VERIFIED (repo); **not physically measured** |
| Yarn (twin) | cream 40.2 m, wine 11.9 m; worsted cotton; 5.0 mm hook | FROM REPO (`tester_kit/KIT_MANIFEST.json`) |
| Content hash (US text) | `1ddde587f537388b4a9dd5a74e9a0e0ebadc6ce0c0a79372dd6b867a230b3991` | VERIFIED (repo) |
| Release hash | PENDING | production `pattern_versions.release_hash` |
| Deliverables | US + UK terminology PDFs; each re-rendered at upload and hash-checked against `assets.built` (`check_pdf_hashes`) | code; hashes PENDING (production `assets.built` row) |

The other Launch-0 releases use the same layout. See LAUNCH_PATH §3 for their versions, hashes and plan prices.

## 2. Listing text (the exact fields sent)

PENDING, all of it. The source is `etsy_ops.sent_fields(etsy_ops.certified_payload(db, slug, version))`: the stored `Listing` row for this release (written by `listing.draft`, then `listing.seo`) plus the chosen taxonomy and properties. The repo holds no current listing row.

| Field | Value | Source / rule |
|---|---|---|
| title | PENDING | stored `Listing.title`. FROM REPO, format used on the PRODREADY local chain: "{Product name} \| Crochet Pattern PDF \| US and UK Terms" |
| description | PENDING. It must contain, verbatim: `DISCLOSURES["ai_assisted_design"]`, `["disclosed_render"]` and `["digital_download"]` | `gates.platform_policy.DISCLOSURES`; checked by `commerce.buyer_trust.listing_disclosure_finding` |
| tags (≤ 13) | PENDING | `listing.seo` |
| materials | from CIR materials, de-duplicated | `integrations.etsy.build_payload` |
| price | CA$6.50 (plan) | VERIFIED (repo): `products.launch0.launch_price`, within the band |
| quantity / type | digital | `build_payload` |
| taxonomy_id + properties | **PENDING: UNKNOWN** (no CHOSEN category) | `commerce.category.publish_inputs`; blocker E4 |

Disclosure text, VERIFIED from `gates/platform_policy.py`:
- **ai_assisted_design:** "This design was created with AI assistance, and every row's stitch count is checked before release."
- **disclosed_render:** "About the images: each listing image is a digital rendering of the pattern's finished design, not a photograph. Every stitch in it is drawn from the pattern itself at the stated gauge, with a centimetre scale; no sample has been photographed, and your finished piece will vary with yarn and tension."
- **digital_download:** "This is a digital pattern. No physical item is shipped."
- **PDF AI disclosure:** `publish.pdf.AI_DISCLOSURE`.

## 3. Gallery

| Field | Value | Source |
|---|---|---|
| Image kind | disclosed deterministic renders (D-FB-7/D-FB-9); no photograph, no generated product image (F-852) | code |
| Frame count | FROM REPO: 9 for market-basket-small (8 medium, 8 large; 6 for most others; 8 for the key basket), all legible ≥ 11.2 px at display size | PRODREADY §1.1, local chain, 2026-10-19 |
| Frame order, sha256, alt text | PENDING | `etsy_ops.certified_images` in listing-set-certificate order (`record_id`) |
| Listing-set certificate | PENDING | evidence `listing_set` (valid, record_id) |
| Independent vision review (#61) | PENDING: UNKNOWN until the approved CA$7.07 vision batch is activated | evidence `parity.frame_review`, `exported_frame_review` |
| Policy fit of renders as **first image** | **OPEN QUESTION**: see ETSY_POLICY_READINGS_PACKET §3 Q1 | person reading of `listing_image_rules` |

## 4. Product Truth certificate

| Field | Value | Source |
|---|---|---|
| Product Truth | **PASS** (`passes_gates: True`) for nursery-nesting-baskets and all 8 Launch-0 products, computed 2026-10-27 | VERIFIED (repo): `products.launch0.product_truth` |
| Declared disqualifiers (shown to owner) | "a worked sample whose walls slump at the stated gauge…"; "a base disc that does not lie flat…"; "any decision to add an applied trim…" | VERIFIED (repo) |
| Certification | PENDING | evidence `certification`: `certified`, `certificate_granted`, `release_matches`, `content_hash`, `policy_version`, `stages_run`, `blocking_finding_codes`, `withheld` |
| Name truth (`NAME_OUTRUNS_PATTERN`) | enforced at publish | `publish.eligibility.name_truth` |

## 5. Physical test evidence

| Field | Value | Source |
|---|---|---|
| Risk class | B (dimensional_form) | VERIFIED (repo): `gates.risk_matrix.matrix_for` |
| Required before the first customer | partial_physical of this exact content (a full make satisfies it) | `risk_matrix.first_customer_requirement` |
| Bound samples | **NONE.** PENDING tester. | `first_customer.physical_binding`, from the `PhysicalTest` rows in `POST /api/physical-test` |
| Tester kit | built: test PDF, record sheet, outreach post (**not sent**) | `research/final_build/w4/tester_kit/` |
| First-customer nine areas | PENDING: must all be PASS. Today `gauge_and_size_claims` = UNRESOLVED; `etsy_remote_state` = UNVERIFIABLE by construction (LAUNCH_PATH D1) | `gates.first_customer.blocking` |
| Owner review | required even at 9/9 PASS (`first_customer.NEVER_AUTHORISES`) | code |

## 6. Policy readings

| Field | Value | Source |
|---|---|---|
| Section state | PENDING. Expected FAIL today: the repo seed is dated 2026-09-26, older than 30 days. | evidence `policy` (`platform_policy.freshness`) |
| Per source: checked_on, version, basis, read_by | PENDING: one row for each of seller_policy, creativity_standards, listing_image_rules, advertising_rules, shilling_and_reviews, children_and_baby and search_guidance | `policy_snapshots` |
| Unreviewed changes | PENDING: must be none | `platform_policy.unreviewed_changes` |
| Render-as-first-image ruling | PENDING owner, informed by the `listing_image_rules` reading | the packet |

## 7. Price and economics

| Field | Value | Basis |
|---|---|---|
| Price | CA$6.50 | **set** by the plan (not measured) |
| Etsy fees per sale | CA$0.90 (transaction 6.5% + processing 3% + CA$0.25 + amortised listing fee) | **modelled**: `commerce.pricing.fees(6.50)` |
| Net per sale | CA$5.60 | **modelled** |
| Not modelled | Offsite Ads, regulatory operating fee, currency conversion | `pricing.fees().unmodelled_fees` |
| Sales volume | unknown: no order ingested | evidence `economics` |

## 8. Search certificate

| Field | Value | Source |
|---|---|---|
| State | **FAIL** (category UNKNOWN; F-005) | FROM REPO: PRODREADY B2, LISTREADY. Live: evidence `search` |
| Next step | production taxonomy names readback, then a matcher fix | LAUNCH_PATH E4 |

## 9. Phase change

| Field | Value | Source |
|---|---|---|
| Current | shadow (recorded and environment) | production `GET /api/owner/phase` (PENDING readback) |
| Required for the draft | limited_production: two owner transitions, shadow → staging → limited_production | `core.phase.record_transition` |
| Each transition cites | `launch.assessed` row ≤ 7 d and `launch.rollback_rehearsed` row ≤ 3 d (passing from limited_production upward), plus a live `transition_verdict` that is **ready** | `core.phase` |
| Today | cannot be recorded (LAUNCH_PATH D2: `listing_fees` and `brand_clearance` are constant False) | code |
| Rollback of the phase | a move down is always allowed with a reason; readiness is never evaluated on a move down | `core.phase.record_transition` |

## 10. Rollback / unpublish plan (verbatim from `ops.publication_authority.ROLLBACK_PATH`)

- **This grant:** "covers draft creation only: an Etsy draft is never visible to buyers, so no buyer can exist for it".
- **Remove the draft:** "EtsyClient.delete_listing(listing_id) -- reads the listing back first and refuses unless Etsy reports it as draft or inactive".
- **If later activated:** "activation is a separate owner grant (store.activate). To withdraw a live listing the owner deactivates it in Etsy Shop Manager -- no automated deactivation job exists in this system -- and the release chain marks the local Listing 'withdrawn' (audited listing.withdrawn); it is restored via chain.rebuild from the retained release".
- **Buyers:** "deactivation does not reach buyers who already purchased… That Etsy behaviour is UNKNOWN to this system (not verified); a correcting release prepares buyer notices that the owner sends".
- **Rehearsal:** PENDING. The latest `launch.rollback_rehearsed` for this release must be ok and ≤ 3 days old (evidence `rollback`).
- **Phase rollback:** `POST /api/owner/phase/transition {to: "shadow", reason}`, then set `BRAMBLELOOP_PHASE=shadow`. The kill-switch `BRAMBLELOOP_PUBLISH_AUTHORISED≠1` refuses every publish immediately.

## 11. Spend

| Item | Amount | Approval |
|---|---|---|
| Draft creation | CA$0 (Etsy charges no fee for a draft) | this grant |
| Activation listing fee | US$0.20 per listing ≈ CA$0.28 (`LISTING_FEE_USD` × `ASSUMED_CAD_PER_USD` 1.4154); renewal every 4 months or on sale | the separate `listing_fees` owner decision. It is checked at activation against the agent's daily ceiling (`handle_store_activate`) |
| Transaction and processing fees | taken by Etsy per sale (modelled above) | inherent |
| Paid media / Etsy Ads / Offsite Ads | **none**; no paid-media authority exists | none requested |
| Tester sample (physical evidence) | ≤ CA$59.65 ESTIMATED ceiling for market-basket-small | the separate `tester_outreach` owner decision |
| Anything else | **none unless separately approved** | — |

## 12. Gated sections summary (what the Command Center shows)

| Section | Must be | Today (repo view) |
|---|---|---|
| certification | PASS | PENDING (production) |
| parity | PASS | UNKNOWN (vision batch not activated) |
| listing_set | PASS | PENDING (production) |
| disclosure | PASS | PENDING (production; PASS on the PRODREADY local chain) |
| policy | PASS | FAIL/UNKNOWN expected (stale seed) |
| search | PASS | FAIL (taxonomy) |
| rollback | PASS | PENDING (rehearsal ≤ 3 d) |
| economics | informational (MODELLED) | MODELLED |
