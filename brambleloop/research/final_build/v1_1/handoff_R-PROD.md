# Handoff R-PROD — repairs for J-product audit of final-candidate-ddf9c6e

Branch `claude/r2-PROD` from `claude/visual-investigation` @ e631dad. Phase shadow throughout;
no network, no Etsy, no spend. Interpreter: brambleloop/.venv/bin/python, PYTHONPATH=src.

## Findings

| ID | Status | Fix |
|----|--------|-----|
| P-1 | COMPLETE | `seo.truth.canonical()` NFKC + strip Cf before every check; compatibility/zero-width spelling, non-ASCII content (CJK, symbols, emoji) and terms with no traceable word are `TERM_UNTRACEABLE`. `publish.listing_schema` (`title_problems`/`tag_problems`, so `check_payload`/`build_payload`) refuses `*_COMPATIBILITY_FORM` (NFKC changes the text, ™©® excepted) and `*_UNTRACEABLE_SCRIPT` (non-Latin letters). |
| P-2 | COMPLETE | `launch.readiness.catalogue_depth` counts distinct products (`product_of_slug` → `launch0.candidate_for_cir`); evidence carries `products_counted`, `products`, `products_with_listings`, `counting_rule`. Launch-0 = 3. `MIN_LISTINGS_TO_OPEN` stays 8. Master v1.1 searched: no rule counts sizes as products. |
| P-3 | COMPLETE | `store_foundation.lint`: `normalise()` (NFKC, Cf strip, homoglyph fold) + letter-spaced view; number words; ratings/stars, units sold, years/decades in words, handmade/hand-crocheted/"we tested", scarcity/discount/"limited", safety (safe for babies, non-toxic, Oeko-Tex, *-certified, hypoallergenic, lab-tested); `TRUTH_OBFUSCATED_TEXT`; negation limited to 4 words of the same clause (comma/dash/conjunction ends it). Age statements ("under 3 years") are not experience claims. |
| P-4 | COMPLETE | `Surface.text()` recurses dicts/lists, default-includes unknown keys (incl. `title`, `body`); only internal id/provenance keys skipped. |
| P-5 | COMPLETE (see note) | `create_draft`/`upload_image`/`delete_listing` call `_authorise_write` at the effect boundary: a verified `OwnerGrant` (publication; or the activation grant for that listing on existing-listing writes), or the draft-only `shadow_writes_authorised` lane only while `core.phase.effective(db)` re-resolved now is non-publishing. Constructor phase/owner flag authorise nothing. `publish()` unchanged in behaviour (images go through private `_upload_image` under the grant verified before create). |
| P-6 | COMPLETE | `invariants.canonical_key` (NFKC, Cf strip, lower, non-alnum→`_`) used by the guard; `canonical_payload` refuses twin aliases; `policy_loops.active()` reads by canonical key and falls back to the code default instead of KeyError; `submit()` canonicalises. |
| P-7 | COMPLETE | " -- " removed at source: `commerce/shop_package.py` customer strings, `commerce/seo.py` description template, and two children's safety statements in `intel/childrens.py` (punctuation only: parentheses / comma; words unchanged; the listing still prints the statement verbatim, as test_commerce requires). `intel/childrens.py` was not on the owned list; edited because the verbatim-statement test forbids typesetting it in the listing. Integrator: please confirm. |

## Tests
New (each fails on ddf9c6e, passes here — verified in a detached ddf9c6e worktree):
`test_r2_product_seo_unicode` 6, `test_r2_product_catalogue_depth` 4, `test_r2_product_store_lint` 7,
`test_r2_product_client_grant` 5, `test_r2_product_policy_alias` 7, `test_r2_product_voice` 2
(shared runner `tests/_r2_harness.py`).
Fixture-only updates (grant stubs, rc1-INT pattern; no assertion removed): test_etsy,
test_etsy_transport, test_etsy_readback_observe, test_rc1_auth, test_disclosed_certified_upload
(fake accepts `grant=`, aliases `_upload_image`), test_draft_creation_durability (fakes accept `grant=`).

Suites run green after the fix: v11_seo_* (29), v11_store_* (33), search_truth 32, v11_learn_loops 18,
shop_package 18, brand 23, storefront_fb4 17, vacuity 7, secret_scan 6, etsy 17, etsy_transport 44,
etsy_readback_observe 37, etsy_exercise 31, etsy_capability 9, etsy_surfaces 52, etsy_oauth_callback 41,
etsy_property_contract 4, rc1_auth 11, publish_execution_gate 1, activation_authority 2,
first_customer_gate 12, launch 28, launch0 52, launch0_gauge 1, launch0_size_labels 4,
launch0_listing_truth 14, commerce 53, childrens 40, deliverable_qa 61, product_run 36,
cert_rebuild_chain 10, disclosed_certified_upload 7, draft_creation_durability 6.

## Open / not done
- P-5: `attach_file`, `update_listing`, `set_listing_property` still need only DRAFT_WRITE
  authority; `runtime/pipeline.py` (not owned) calls them after publish without a grant handle.
  WIRING REQUEST if wanted: pass `grant=` through pipeline and gate them the same way.
- The owner shadow probe lane (`etsy_probe`/`etsy_exercise`, ETSY_SHADOW_WRITE) still drafts
  without a grant in a non-publishing phase (by design; cannot activate).
- Drafted descriptions still trip `TRUTH_SAFETY_CERT` on the regulator citation "CPSC" in the
  mandated children's safety text (pre-existing on ddf9c6e; descriptions are not truth-linted
  by any gate). Not changed.
