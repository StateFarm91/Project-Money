# Lane J / AREA=product -- adversarial certification of final-candidate-ddf9c6e

Interpreter: brambleloop/.venv/bin/python, PYTHONPATH=src. Phase shadow; no network, no spend.
Repro scripts live beside this file (`j_product_*.py`); every finding below was executed.

## Findings (all reproduced)

### P-1 MEDIUM -- seo.truth accepts any non-ASCII term (fullwidth/CJK brand, IP, superlative)
`seo/truth.py:check_term` builds its word list with `facts.words()` = `[a-z0-9]+`. A term made of
no ASCII letters has an empty word list, so no TERM_UNTRACEABLE finding is ever raised, and the
competitor/IP/claim checks all compare on the same ASCII-folded string, so they never match.
Repro `j_product_seotruth.py`: `validate_listing` returns `ok=True` with tags `ｒａｖｅｌｒｙ`,
`ＢＥＳＴ ＳＥＬＬＥＲ`, `ｄｉｓｎｅｙ`, `最佳` added to a clean 12-tag set, and with `ＢＥＳＴ ...` /
`... | ｄｉｓｎｅｙ | ...` in the title. `publish/listing_schema.tag_problems` and `title_problems` also
return `[]` for them (`j_product_schema.py`), so the production validator has the same blind spot.
Reach: `seo.proposals.propose` takes phrases from the owner's Etsy Stats export and observed buyer
language; such a phrase passes `truthful()` and takes a slot. Nothing applies a proposal to a
listing in this build (no importer of `seo.proposals` outside `seo/`), so it is a validator
defect, not a live leak.
Fix: NFKC-normalise (and strip Cf/Zs) before `words()`; refuse any term whose normalised form
has no traceable word (`if not norm.split(): TERM_UNTRACEABLE`); refuse tags with non-Latin
letters unless a fact licenses them.

### P-2 MEDIUM -- launch.readiness `catalogue_depth` counts size variants as patterns
`launch/readiness.py:479-485` compares `counted["versions"]` (certified PatternVersions in
Launch-0 scope) and in-scope listings against `MIN_LISTINGS_TO_OPEN = 8`. Launch-0 has 3
products but 5 in-scope CIR slugs (3 basket sizes + coaster + blanket); `j_product_depth.py`
prints `counted versions: 5 distinct products: 3`. `store_foundation/readiness.py:230` and
handoff_F state "sizes are not counted as products" and count 3. The threshold constant is not
lowered (8, verified), but the two gates disagree and the launch gate dilutes it: a 4th product
with three sizes would read 8 while the shop has 4 products.
Fix: count distinct `launch0.candidate_for_cir(slug).slug` in the launch gate.

### P-3 MEDIUM -- store lint is a closed regex list; many phrasings of the banned claims pass
`store_foundation/lint.py` (design: tripwire). Executed (`j_product_lint.py`), MISSED:
"Rated 4.9 stars", "Over 500 patterns sold", "Customers love it", "A trusted name in crochet",
"Established in the 2010s", "Fifteen years in business", "Over twenty years of crochet",
"Handmade with love", "Hand-crocheted sample shown", "We have tested every row",
"Only a few left", "Last chance", "Save 20 percent", "Half price this week", "Top quality",
"Most-loved pattern", "Etsy's choice", "Safe for babies", "Oeko-Tex certified",
"The b e s t pattern", "b<ZWSP>est pattern", "Ƅest crochet patterns". Negation-window evasion
(negatable rules): "Not a toy, we crocheted this basket ourselves", "Never boring, always
lab-tested", "We never skip it and these are baby safe" all pass.
Current shop copy is clean (`j_product_storetext.py`: no truth finding on any surface), so no
live defect; the lint cannot be the control for future or externally sourced text.
Fix: NFKC + zero-width strip before matching; spelled-out numbers; negation only for the exact
disclosure sentences (allow-list) rather than any negator within six words.

### P-4 MEDIUM -- store readiness never lints `opening_grid` (listing titles) or nested values
`store_foundation/content.py:Surface.text()` joins only `question/answer/text/name` keys of list
rows and top-level str values of dicts. `opening_grid` rows carry `title`, so the tile titles
(customer-facing) are never truth-linted; nested lists in a dict are skipped (`j_product_surface_text.py`:
grid title with "Best-selling ... Since 2014" -> `text()==''`, no findings; FAQ row with key
`body` likewise). Fix: include `title`, and recurse.

### P-5 MEDIUM -- `EtsyClient.create_draft/upload_image/delete_listing` need no OwnerGrant
rc1-AUTH D3 put the grant on `activate`/`publish` only. `j_product_client_nogrant.py`:
`EtsyClient(transport, credentials=..., phase="production", owner_authorised=True).create_draft(p)`
reaches the transport (POST /shops/S/listings) with no grant, no DB and no recorded-phase check;
the phase is a constructor string. No caller in `src/` other than `publish()` (which does check
the grant) and the owner probe/exercise scripts calls these, so `store.publish`/`store.activate`
remain closed (see Sound). Fix: make the three methods private or require the same `OwnerGrant`.

### P-6 LOW -- policy-loop key aliasing: `invariants.check` normalises, `active()`/`submit()` do not
`invariants._norm` collapses case, punctuation and zero-width suffix ("Min-Shared",
"min_shared<ZWSP>", "MIN_SHARED" pass as `min_shared`). `policy_loops.active()` then does
`payload[lp.param]` and `submit()` does `params_to[lp.param]`. `j_product_learn.py`: a registry
payload `{"Min-Shared": 3}` makes `active()` raise `KeyError('min_shared')`; `consume.policy`
(called from `runtime.release` listing.seo) has no guard, so a malformed incumbent breaks
listing drafts instead of falling back to the code default. Values stay bounds-checked, so no
threshold is loosened. Fix: compare exact keys (or canonicalise) in `check_payload`; wrap `active`.

### P-7 LOW -- the shop's own copy and listing descriptions contain " -- " (VOICE_DOUBLE_HYPHEN)
`readiness.evaluate` row `voice` = UNVERIFIED with four VOICE_DOUBLE_HYPHEN warns; every drafted
listing description ("Two PDFs ... -- the same pattern ...") ships it to Etsy verbatim, which the
lint's own rationale calls a defect. Warn-only; not a truth issue.

## Checked and SOUND (evidence)

* Launch-0 listings (real chain, `j_product_listings.py` first run + `j_product_drafted_check.py`):
  all five (3 baskets, coaster set, Cloudline blanket) carry their own noun, no foreign product
  word, no "mosaic"; prices 6.50/6.50/6.50/4.00/7.50 = plan; taxonomy 2115 (baskets), 2114
  (coasters), 2112 (blanket) = each product's own node; titles 92-107 chars, 13 tags <= 20 chars;
  `seo.truth.validate_listing` ok and store lint clean on all five. `test_launch0_listing_truth`
  (the PT-01/02/04 regression, real handlers) passes in full => rc1-LST holds.
* rc1-PAT: `test_version_immutability` (3), `test_release_versions` (4), `test_launch0` (52),
  `test_launch0_size_labels` (4) pass; changed content under a certified version is refused.
* rc1-AUTH: `test_rc1_auth` 11/11 (A1 rollback after boot stops activate; D1 replayed production
  row; D2 deleted/unsealed revocation; D3 client grant; D4 evidence refs); `test_activation_authority`
  2/2, `test_publish_execution_gate` pass. Code read: `pipeline.handle_store_publish/activate`
  call `protected_phase` (env AND recorded chained transition, more restrictive wins, fail-closed
  to shadow) before any effect and again at the effect boundary; publish resolves the sealed,
  24h, content-bound grant twice (`_revalidate_publish_effect`); the env flag can only deny.
  `core.phase.resolve`: env=production with no recorded transition -> shadow; an unverifiable
  newest row -> shadow; a recorded rollback cannot be skipped (newest row is not skipped).
* catalogue_depth: `MIN_LISTINGS_TO_OPEN = 8` unchanged; store foundation counts 3 products and
  emits CATALOGUE_DEPTH (owner) -- see P-2 for the launch-gate count caveat.
* Learn: `invariants.check` refused every protected/undeclared/nested/out-of-bounds/bool/NaN/str
  probe (30 cases in `j_product_learn.py`; MIN_MATCHED, MIN_DECISIONS, regression_margin,
  publish_*, catalogue_depth, price_floor, max_tags, nested dict all refused); `active()` and
  the executor re-check; `test_v11_learn_loops` 18/18 incl. regression -> rollback executed,
  read back at the consumer, incident opened, memory skip.
* SEO: `seo.proposals` / `seo.jobs` write only `seo_proposals` rows (`writes_to_etsy False`);
  nothing in `src/` outside `seo/` imports them, so no SEO proposal reaches a Listing at all.
  ASCII brand/IP/competitor/stuffing/duplicate/limit probes all refused (21-char tag, 14 tags,
  141-char title, "ravelry", "woobles", "disney", leetspeak, ZWSP-in-tag, duplicates by case).
  `test_v11_seo_truth` 9/9, `test_v11_seo_proposals` 8/8.
* Store preview: `_esc/_paras/_tile` entity-encode script, attribute break-out, `</style>`
  and svg payloads (`j_product_preview.py`); data-URI images are `<img>` only; document is
  `noindex`, labelled not-live. `test_v11_store_preview` 13/13, `test_v11_store_foundation` pass.
* Store copy: every surface truthful on current text (no sales/reviews/years/photograph claims;
  "no sample has been photographed", "not a photograph", "new shop -- no reviews yet").
* Visual disclosure (D-FB-7..10): `test_disclosed_render` and `test_disclosed_certified_upload`
  were still running at report time (heavy rendering); all assertions printed so far OK, none
  failed. Not claimed as complete.
