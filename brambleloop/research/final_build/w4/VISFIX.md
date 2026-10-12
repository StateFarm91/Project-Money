# VISFIX: the visual and regression suites on INTEG2, made truthfully green

Branch `claude/w4-VISFIX`, based on `origin/claude/w4-INTEG2` 28ba6df. Stub providers only:
no spend, no deploys, no Etsy actions. Every test was run through `/home/user/bl-runs/testslot.sh`.

## Failures on clean INTEG2 (28ba6df), each reproduced before any change

| Suite | Before (clean INTEG2) | After (this branch) |
|---|---|---|
| test_launch | 13 OK / **15 FAIL** | 28 OK / 0 FAIL |
| test_cost_governance_wave2 | 38 OK / **1 FAIL** | 39 OK / 0 FAIL |
| test_v11_autonomy_timeline | 5 OK / **1 FAIL** | 6 OK / 0 FAIL |

### 1. test_launch: "2 piece(s) read at 340 px where the pattern makes 1"

- **Root cause.** W4-MULTIPIECE made `disclosed_render._flat_set` draw all `make` copies of a
  single flat component on the hero (the placemat pair, the ornament set of 6). That drawing
  is correct. But `disclosed_listing.listing_qa` still expected 1 piece for the flat form, so
  the 340 px legibility check refused a correct hero. The launch report inherited that
  refusal, which failed all 15 launch tests.
- **Fix.** Merged `claude/w4-IMGFIX`@35ff340. The expected count now comes from the CIR's
  `components[0].make` for a single-component flat piece, as it already did for rounds.
  - The source is the CIR, not the renderer's own `layout.objects`, so the check stays
    independent of the thing it checks.
  - Thresholds and the piece counter are unchanged.
  - A multi-component flat render still expects `copies or 1`, which is stricter, not looser.
- **Review.** I read the whole diff. No test, threshold or gate was weakened.
  `test_w4_imgfix` pins both slugs at 2 and 6 pieces, and pins that each one is usable.

### 2. test_cost_governance_wave2: `mkdtemp` in visual/hero_review.py:57 and visual/inspect.py:320

- **Root cause.** The B2VISION/HEROVISION work added two `tempfile.mkdtemp` call sites.
  `test_no_production_module_creates_a_directory_nothing_removes` allows exactly one: the
  `/api/continuity/export` background-task cleanup in app/main.py. That one is still the
  only one.
- **Fix (IMGFIX).** Both call sites now use `core.workspace.work_dir`.
  - Each directory is scoped to its call and removed on return or raise.
  - A supplied `work_dir` is never deleted.
  - The new prefixes `hero-review-` and `grid-identify-` are added to
    `ops.health.TEMP_PREFIXES`.
- **Review.** `identify_at_grid` was split into `_identify_in` with identical behaviour:
  the same budget reservation and release, the same verdict logic, and the same
  `unjudged` result on OSError.

### 3. test_v11_autonomy_timeline: committed map 57 follow-on edges, generator 58

- **Fix.** Regenerated the map with `python -m brambleloop.autonomy.map --write ...`.
  Only `generated_at`, the count, and one edge changed.
- **The new edge is a real code change, not drift.**
  - The edge is `runtime/release.py:_reprice_on_plan_drift`, which enqueues
    `pricing.position`.
  - It was added by W4-PLACEMATPRICE c1a56f0, which is on INTEG2. When the listing price
    drifts from the Launch-0 plan, `chain.rebuild` re-prices it.
  - The map was last regenerated at 012a875 (2026-10-11), which is before that commit.
- After the DISCLOSEDQA and HEROTOURNEY merges, the generator still agrees with the
  committed map (6/6).

## Branches reviewed

| Branch | Decision | Why |
|---|---|---|
| `claude/w4-IMGFIX`@35ff340 | **Merged** | It fixes failures 1 and 2 at the root and weakens no gate (see above). |
| `claude/w4-DISCLOSEDQA`@9df29d3 | **Merged** | Complete. #61 now reviews the frames a Launch-0 listing actually uploads (the certified disclosed set from `etsy_ops.certified_images`), blind, bound to their sha256. `store.publish` (`pipeline._listing_parity`) and the publication grant (`publication_authority._parity`) read it and only tighten. The review runs only while `image_vision` is open. Its last commit had not been re-tested; on this branch `test_w4_disclosedqa` passes 8/8 and the parity and publish suites pass (below). Known limit: `applies()` treats an unreadable certificate as "no disclosed set", which falls back to the previous `frame_review_state` read. That is no looser than INTEG2, and with no certificate nothing can be uploaded (the certified path is the only upload path). |
| `claude/w4-HEROTOURNEY`@9814b80 | **Merged** (as the conflict-resolved tip, never f40c7f9 alone) | f40c7f9 contained merge-conflict markers; 9814b80 resolves them, keeping B2VISION's `unresolvable` and `by_product` (only the hero on file speaks for #218 and #126). It was untested at its tip; here `test_w4_herotourney` passes 4/4, `test_blinded` 46/46 and `test_w4_b2vision` 7/7. The only conflict was `ops.health.TEMP_PREFIXES`; I kept both `exported-review-` and `grid-tournament-`. I tried routing the hero through `blinded.resolve_image` and reverted it. The branch's resolver is stricter on URIs (http(s) only, the same as `gateway.anthropic._image_block`) and honours the frame's `artifact_dir`. The change bought nothing and broke a filename-keyed stub. |

## Tests on the merged branch (testslot)

Required regression set:

| Test | Result |
|---|---|
| test_vacuity | 8/8 |
| test_launch | 28/28 |
| test_cost_governance_wave2 | 39/39 |
| test_search_hero_publish | 4/4. IMGFIX/DISCLOSEDQA's `LISTING_PRICE_NOT_PLAN` failure no longer occurs; PLACEMATPRICE on INTEG2 fixed it. |
| test_cert_listing_frames | 6/6 |
| test_v11_autonomy_timeline | 6/6 |

Visual, hero, thumbnail and listing-frame suites, plus the suites the merged branches touch:

| Test | Result |
|---|---|
| test_w4_imgfix | 3/3 |
| test_w4_disclosedqa | 8/8 |
| test_w4_herotourney | 4/4 |
| test_blinded | 46/46 |
| test_w4_b2vision | 7/7 |
| test_w4_multipiece | 5/5 |
| test_w4_firstimg | 12/12 |
| test_w4_thumbfloors | 7/7 |
| test_w4_herovision | 6/6 |
| test_listing_parity_gate | 6/6 |
| test_cert_publish_gates | 18/18 |
| test_publish_execution_gate | 1/1 |
| test_w3_k11_authority | 18/18 |
| test_cert_intel_wave2 | 15/15 |
| test_cert_preengineering | 19/19 |
| test_w4_autonomy_idle_departments | 10/10 |
| test_cert_wiring | 16/16 |
| test_w4_placemat_reprice | see the handback |

## Requirement rows whose evidence this changes

- **B2 #61 Visual Semantic QA.** The software half is built and tested: the frames that are
  actually uploaded are reviewed, and publication reads that review. The row is **not
  closed**. Its acceptance needs a model looking at the pictures, which needs the
  `image_vision` gate open, which needs a funded vision provider (owner, model credits).
  Unchanged from the board's root.
- **F-278 Hero Thumbnail Tournament.** The board's remaining software item is "keeping
  candidates per product >=2 at the tournament".
  - Met for round sets (the coaster set has a second candidate at gap 0.06) and vessels
    (the ANGLE view). Every candidate is verified PASS by `render_verification`.
  - Flat single pieces (the blanket) truthfully have 1 candidate. They are reported
    `insufficient_candidates` and are not padded.
  - The judgement itself is still GATED on the funded vision provider. **Not closed.**
- **F-027 / F-031 (first-image gate, thumbnail simulator).** The flat-set hero now passes
  340 px legibility with its true piece count, so those listings are no longer refused by
  a wrong expectation. The evidence is corrected; no row is newly closed.
- No row is closed by this branch.

## Blockers

- Owner: fund the vision provider (`image_vision` gate). Without it, #61 and F-278 cannot
  produce judged evidence. This blocker is already on the owner queue; this branch adds
  nothing to it.
