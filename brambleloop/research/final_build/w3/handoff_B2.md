# Handoff — lane W3-B2: owner canonical brand assets in Brand, Storefront and Visual (D-FB-17)

Branch `claude/w3-B2`, based on `claude/visual-investigation` @ 88993c5. Phase stays shadow:
no Etsy write, no upload, no spend, no deploy, no image generation, no network.

## Decisions / requirements addressed

| Item (D-FB-17 / brief) | Status | Where |
|---|---|---|
| 1. Registry of the two canonical owner files, fail-closed `verify()`, protected-change rule `AUTHORISED_BRAND_CHANGES = ("D-FB-17",)` | COMPLETE | `brand/canonical_assets.py` |
| 1. Guard: autonomous Brand/Learn/Visual improvement cannot replace them on a score | COMPLETE for every path that exists | `canonical_assets.select`, `visual/rnd/objective.select` (`brand_role` candidates → `owner_review`, never winner), `brand/takeover` (`replaces_assets` refused; invariants `canonical_logo`, `canonical_banner`), `brand/judge.verdict` (`may_replace_canonical: False`). grep: `learn/`, `improve/`, `growth/`, `autonomy/` contain no code that writes a storefront logo/banner |
| 2. Remove scratchpad dependency | COMPLETE | `brand/owner_identity.concept_paths`, `brand/comparison.owner_path` read the repo copies (env override only if bytes hash to the owner's). Owner palette re-sample and A2 owner checks now run on any machine (previously skipped without the session scratchpad) |
| 3. Hierarchy in exports | COMPLETE | `identity_system`: `STATUS.state = SUPPORTING_PRODUCTION_SYSTEM` (superseded_by D-FB-17), `hero_artwork_png()`, `owner_logo_path()`, `asset_for(use)`, `HIERARCHY`, usage rules rewritten; `to_dict()["canonical"]`. `store_foundation/assets.banner_svg` labelled "not the storefront banner" |
| 3. Category lines vs catalogue | REPORTED (owner decides) | Banner nav: **Wearables, Gifts, Seasonal have no pattern**. Logo footer: **Gifts, Seasonal have no pattern**. Pixels untouched |
| 4. Banner publication assessment | COMPLETE | `store_foundation/owner_banner.py`; `research/final_build/w3/OWNER_BANNER_ASSESSMENT.md`; JSON at `research/final_build/w3/owner_banner_candidates/owner_banner_assessment.json`; `storefront_gate.check_banner` now consumes the canonical file and names each failing gate (`STORE_BANNER_OWNER_<GATE>_<FAIL/UNKNOWN>`, `STORE_BANNER_CANONICAL_UNVERIFIED`) instead of `STORE_BANNER_NOT_EXPORTED` |
| 4. Minimal reframes | COMPLETE, OWNER_REVIEW_REQUIRED, none adopted | `owner_banner_candidates/A_crop_4x1_top_anchored.png`, `B_pad_4x1_edge_colour.png` (+ `simulation_centre_crop_4x1.png`, not a candidate); each ≤ 300 KB |
| 5. Storefront rebuilt around the assets | COMPLETE (preview only) | `store_foundation/preview_v2.py`: banner = canonical file as supplied + honest blocked strip; About hero = owner logo artwork; shop icon by measurement; cards lifestyle-first with honest placeholder ("No picture of the finished piece yet") and the verified render as an inset evidence frame; owner board sections (assets + hierarchy, icon measurements, every banner gate, candidates, truth findings, listing image order). `preview.summary` gains a `storefront_banner` item |
| 6. Visual judges/objective reference the canonical assets | COMPLETE | `visual/rnd/judges.brand_target()`; `brand_consistency` (proxy/2) is UNKNOWN when the target fails verification and records the target; `objective.brand_target(role)`, `CANONICAL_BRAND_ROLES`; banner registered as the art target (`banner_art_target`) |

## Owner banner — gate results (exact file)

PASS (4): `canonical_integrity`, `etsy_banner_minimum_and_format`, `laura_never_claims_human_in_text`, `public_copy_truth_lint`.
FAIL (5): `f233_banner_canvas_4to1` (2.50:1 vs 4:1), `f233_identity_block_survives_4to1` (block 593 px tall > 496 px max 4:1 height; centre crop cuts 104 px off the monogram), `laura_publication_status` (not_for_publication), `ai_generated_imagery_disclosure` (file's C2PA manifest declares trainedAlgorithmicMedia / ChatGPT gpt-image; store disclosure lacks the generated-imagery sentence), `nav_categories_truth` (Wearables/Gifts/Seasonal empty).
UNKNOWN (6): `f233_identity_block_in_phone_window`, `laura_identity` (no embedder, no judges, no receipt → human review queue), `laura_photorealism_anatomy`, `laura_ai_disclosure_at_banner`, `product_truth`, `visible_text_complete`.

Key finding: **both owner files carry an embedded C2PA manifest** declaring them AI-generated
(OpenAI-signed; signature not verified here — no C2PA library).

Shop icon (measured with `storefront_gate.icon_legibility`): exact owner monogram crop is
illegible at 40 px (2.62:1) and 48 px (2.77:1), legible from 70 px (3.03:1) up; full lockup
illegible as a square icon at every size (coverage 5–7 %). Etsy takes one icon upload shown at
40 and 70 px (repo-modelled), so the A3 micro-mark is used for the icon, labelled
"small-size derivative of the owner artwork"; the owner artwork is used at every large size.

## Files

New: `src/brambleloop/brand/canonical_assets.py`, `src/brambleloop/store_foundation/owner_banner.py`,
`tests/test_w3_b2_canonical_assets.py`, `research/final_build/w3/OWNER_BANNER_ASSESSMENT.md`,
`research/final_build/w3/owner_banner_candidates/*` (3 PNG + JSON), this handoff.
Modified: `brand/{identity_system,owner_identity,comparison,judge,takeover}.py`,
`store_foundation/{storefront_gate,preview,preview_v2,assets}.py`,
`visual/rnd/{judges,objective}.py`; tests `test_w3_store_ux_gate.py`,
`test_w3_brand_identity.py`, `test_w3_brand_owner_identity.py` (expectations changed only where
D-FB-17 changes the intended output: A3 status is now SUPPORTING_PRODUCTION_SYSTEM; the banner
check names owner-file gates instead of NOT_EXPORTED — the banner still FAILs; no truth/safety
assertion loosened). Owner source PNGs and SHA256SUMS untouched (re-hashed by tests).

## Tests (focused; full suite not run)

`test_w3_b2_canonical_assets` 16 OK (hash immutability; tamper/missing fail-closed on a temp
copy; protected-change refusal; higher-scoring challenger refused in canonical_assets.select,
objective.select, takeover, judge; hierarchy; icon derivative only with a measured failure;
no scratchpad paths; assessment honesty — no PASS without evidence, unmeasurable gates
UNKNOWN, UNKNOWN alone blocks; candidates pixel-identical to the owner file and never
authorised; committed evidence matches the code; preview built around the owner files;
judges UNKNOWN on tampered target; identity review queued idempotently).
Also green: test_w3_store_ux_structure 16, _mobile 8, _gate 9, test_v11_store_foundation 20,
test_v11_store_preview 13, test_canon_store_brand_face 11, test_w3_brand_comparison 10,
test_w3_brand_identity 14, test_w3_brand_owner_identity 15, test_brand 23,
test_storefront_fb4 17, test_takeover 11, test_cert_takeover 5, test_cert_growth_seasonal 24,
test_w3_visual_commercial_objective 6, test_w3_visual_rnd_guard 6, test_w3_visual_rnd_loop 8,
test_w3_laura_memory_isolation 5, test_w3_priv_leak 7, test_vacuity 7, test_secret_scan 7,
test_reachability 11.
`test_w3_reachability_dynamic`: 1 FAIL (`test_without_the_rule_the_provider_modules_were_invisible`)
— **pre-existing**: fails identically on `claude/visual-investigation` @ 06271ff without this
lane's changes.

## Runtime proof

- `owner_banner.assess()` on the real file → BLOCKED, 4/5/6 as above (0.8 s).
- `owner_banner.write_evidence(Path("."))` wrote the JSON and three review PNGs.
- `identity_review_request(db)` on a scratch SQLite DB opened review #1 (band REVIEW, sha
  048a1991…), idempotent; `preview.summary(db)` shows `storefront_banner` FAIL, 11 findings.
- v2 preview rendered at 390 and 1280 px and screenshotted with headless Chromium (scratchpad
  only, not committed): banner shows the owner file with the blocked strip, header icon, About
  hero logo, lifestyle-placeholder cards, owner board tables.

## WIRING REQUESTS

1. ~~Lane C: add the generated-imagery sentence to `store_disclosure()`~~ **WITHDRAWN** after
   D-FB-18 item 9. Verified Etsy text requires AI disclosure for items for sale, and nothing
   verified covers shop banners, so no marketing sentence is required on the strength of C2PA.
   Restated narrowly: *if* the owner banner is ever published, lane C should scope the lines
   "Images are digital renderings … not photographs" and "Every picture labelled as a rendering,
   never a photo" to **listing** images. They would otherwise be untrue of the banner. This is
   a truth fix, not an AI notice.
2. **improve/invariants owner**: add `canonical_assets`, `AUTHORISED_BRAND_CHANGES`,
   `brand_role` to the protected-invariant names so a proposal cannot target them.
3. **Owner of `research/final_build/w3/evidence/B_metrics.json`**: re-run
   `scripts/w3_store_preview_evidence.py`; the committed browser metrics describe the previous
   v2 page (A3 banner, render-led cards). Tests still pass on them; they are stale, not false.
4. **Integrator**: record in BUILD_STATE that the storefront banner is BLOCKED with the gate list
   above, and add owner actions: identity review of the banner's woman; Product Truth review of the
   crochet shown; nav categories decision; choose reframe A/B/neither.

## Honest gaps

- What the banner shows (person, crochet items, every word) is not measured: no OCR, face
  detector or face-embedding model is installed. Visible words are a transcription; those gates
  stay UNKNOWN for human review.
- The C2PA manifest is parsed, not cryptographically verified.
- Etsy's handling of a 2.50:1 upload and its phone crop are unpublished; the centre crop and the
  2:1 phone window are labelled assumptions.
- `brand/storefront.check_storefront` still does not append `storefront_gate.problems()` (old
  wiring request to lane A); doing so now would refuse every seasonal takeover while the banner
  is blocked, so it is left for an explicit decision.
- No lifestyle frame exists for any pattern; cards show a placeholder rather than anything
  generated.


## Follow-up: owner decisions D-FB-18 (merged `claude/visual-investigation` first)

| D-FB-18 item | Status | Where |
|---|---|---|
| 1 Banner woman is Laura | COMPLETE | `canonical_assets.OWNER_IDENTITY_REVIEWS` (bound to sha 048a1991…). The banner's `laura_identity` = PASS (owner human review). `owner_banner.identity_review_request(db)` records it as a resolved `confirmed_same_person` review (reviewer "owner (D-FB-18)"). Any other sha → normal UNKNOWN + review queue (tested). |
| 1 Publication for this banner | REPORTED, not flipped | `visual.canonical.PUBLICATION_APPROVED` is a per-sha set with no surface scope, and membership implies every customer-facing gate passed. It cannot express "banner surface only". `laura_publication_status` stays FAIL. |
| 2 Concept crochet | COMPLETE (UNKNOWN kept) | `CROCHET_CLASSIFICATION = brand_lifestyle_concept`, mapped to no pattern. No repo or Etsy rule proves it is allowed on a banner, so `product_truth` stays UNKNOWN. VT-B2-1 is recorded as GATED. |
| 3 Categories | COMPLETE | New `store_foundation/navigation.py` (public = ≥ 1 product; hidden kept in the architecture). The preview's section chips filter on ≥ 1 product. The banner's baked-in nav stays a FAIL truth finding. |
| 4 Banner shape | COMPLETE | Etsy re-read live (Help Center API, 200): minimum 1200×300 and recommended 1600×400; **no ratio or crop rule stated**. The 3 dimensional gates are now `UNVERIFIED_ASSUMPTION` (advisory, non-blocking, never PASS). Candidates A/B are `REJECTED_BY_OWNER` and kept as small historical files (they are not shown in the preview). VT-B2-2 is recorded as NOT_REQUIRED_BY_EVIDENCE. etsy.com/legal and the seller handbook returned 403, so they stay UNVERIFIED. |
| 5 Shop icon | COMPLETE | `DERIVATIVE_APPROVALS["shop_icon"]` (D-FB-18 item 5). `shop_icon_choice()` → status OWNER_APPROVED; the hero is unchanged. |
| 9 AI disclosure | COMPLETE (UNKNOWN) | The gate requires exactly what verified Etsy text requires. Item rule: "Seller-prompted AI creations must disclose the use of AI." The banner requirement is unverified, so the gate is UNKNOWN. No sentence added; C2PA kept (tested). |

Assessment after the decisions:
- PASS 6: integrity, Etsy minimum/format, laura_identity (owner review), no human claim, Laura AI disclosure (store + About), copy truth lint.
- FAIL 2: laura_publication_status, nav_categories_truth.
- UNKNOWN 4: photorealism/anatomy, AI-imagery disclosure, product_truth, visible_text_complete.
- UNVERIFIED_ASSUMPTION 3: canvas 4:1, identity block in 4:1, phone window.

Tests: `test_w3_b2_canonical_assets` 18 OK (new: the owner review covers this banner only and
is recorded; navigation shows only populated categories; Etsy evidence recorded with
sources/quotes, nothing quoted from a 403 page; provenance kept; advisory-only does not block).
Store tests green: structure 16, mobile 8, gate 9, v11_store_foundation 20, v11_store_preview
13, canon_store_brand_face 11. Also green: test_vacuity 7, test_secret_scan 7,
test_reachability 11. `test_w3_reachability_dynamic` now 3 OK after the merge.

Additional WIRING REQUESTS:
5. **visual.canonical owner (lane H):** add a scoped owner publication approval, for example
   `PUBLICATION_APPROVALS = {sha: {"surfaces": ("storefront_banner",), "decision": ...,
   "gates_waived_by_owner": (...)}}`, with `asset_status(sha, surface=...)`. The banner's
   publication can then be modelled per surface without touching `PUBLICATION_APPROVED`.
6. **Lane C (`copy_v2.BANNER["nav"]`):** consume it only through `navigation.public_nav()` so no
   exported surface lists empty categories.
