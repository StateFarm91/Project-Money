# W4-FLUXAPI: FLUX 3 Image adapter, multi-reference repair, pattern references, generation stages

Branch `claude/w4-FLUXAPI` (from `origin/claude/w4-INTEG2` @ 9c3812bd). Production is unchanged
(1b21e81, SHADOW). No paid call, no image generation, no BFL API request, no credential change
and no deploy were made. All research reads were unauthenticated GETs of public documentation.

## 1. Audit findings (before the repair)

| Question | Finding | Evidence |
|---|---|---|
| Did the refs[0]-only defect exist? | **Yes.** `_request_for` for the `bfl` dialect sent `{"prompt","width","height","image_prompt": refs[0]}`. With 3 references, the captured body carried 1 (`requested 3, transmitted 1, proven False`). Since F-212, `generate` refused such a call rather than sending it, so multi-reference BFL renders were impossible rather than silently truncated. | Captured offline on 9c3812bd; regression now in `tests/test_w4_fluxapi.py::test_the_old_defect_shape_is_gone_at_the_request_builder` |
| A worse, related defect | `image_prompt` **is not a FLUX.2 field.** In `api.bfl.ai/openapi.json` it appears only in `FluxPro11Inputs`, `FluxUltraInput`, `FinetuneFluxUltraInput` and `FluxDevInputs`. `Flux2Inputs` (used by `/v1/flux-2-pro`) defines `input_image`, `input_image_2` .. `input_image_8`, and does not set `additionalProperties: false`, so the API would not have rejected the unknown field. Every earlier "reference-conditioned" flux-2-pro render therefore sent its reference in an undocumented field. The conditioning receipt only proved the bytes were in the body, not that the model used them. | `FLUXAPI_bfl_evidence.json` (`schemas_defining_image_prompt`, `Flux2Inputs_reference_fields`) |
| Configured BFL model ids | `flux-2-pro` only (`https://api.bfl.ai/v1/flux-2-pro`, advertised 8 references, table price US$0.02). | `gateway/images.py` PROVIDERS |
| Spend reservation and ceilings | `images.reserve_render`, then `anthropic.check_budget_cad`: (1) the monthly ceiling, CA$100 (`spend_policy.ceiling_cad`, lowered by `BRAMBLELOOP_MODEL_MONTHLY_CEILING_CAD` and never raised by it); (2) `spend_policy.PROVIDER_CEILINGS_CAD`, which is **empty**; (3) the agent's daily permission (`creative_director` CA$28/day; the default `gateway` agent has no row); (4) a reservation row written under `budget_lock`. **No separate per-image or per-call ceiling exists**; the per-call bound is the reserved price itself. Ledger: `bill_render` / `record_render`. Replays are guarded by `paid_calls.guarded`. | `gateway/images.py`, `gateway/anthropic.py:332`, `finance/spend_policy.py:180` |
| Price accuracy | The flux-2-pro table price (US$0.02, assumed 2026-09-20) is **below** BFL's published FLUX.2 [pro] price: US$0.03 for the first output MP, plus US$0.015 per additional output MP and US$0.015 per input MP. Multi-reference calls would have under-reserved. | pricing feed, `FLUXAPI_bfl_evidence.json` |

## 2. BFL API facts (official sources, read 2026-10-19T16:58Z)

Sources: [API reference: Generate an image with FLUX 3](https://docs.bfl.ai/api-reference/utility/generate-an-image-with-flux-3) ·
[OpenAPI](https://api.bfl.ai/openapi.json) (sha256 `7fbcacd8…f9`) ·
[FLUX 3 Text to Image](https://docs.bfl.ai/flux_3/flux3_image_generate) ·
[FLUX 3 Image Editing](https://docs.bfl.ai/flux_3/flux3_image_layout) ·
[Pricing](https://docs.bfl.ai/quick_start/pricing) ·
[Integration guidelines](https://docs.bfl.ai/api_integration/integration_guidelines) ·
[Release notes](https://docs.bfl.ai/release-notes) (FLUX 3 Image: October 1, 2026) ·
[FLUX.2 editing](https://docs.bfl.ai/flux_2/flux2_image_editing). Machine-readable excerpts are in
`FLUXAPI_bfl_evidence.json`.

| Question | Answer |
|---|---|
| Is FLUX 3 Image available through the API? | **Yes.** `POST https://api.bfl.ai/v1/flux-3-image`, header `x-key`. The model id in this repo is `flux-3-image`, matching the endpoint slug. There is no separate model field. `version` accepts only `"latest"`. A Klein variant is at `/v1/flux-3-image-klein`. |
| Multi-reference | `images`: one string or a list, "each is an http(s) URL or base64, **one to 10 total**". The prompt refers to them as "Image 1" … "image 10", in list order. FLUX.2 [pro] uses `input_image`, `input_image_2` … `input_image_8` ("up to 8 via API, up to 10 in the playground"). |
| Editing | Yes, on the same endpoint ("the prompt decides whether to generate or edit; there is no `mode` field"). It supports bounding-box edits in the prompt and multi-reference composition ("the person from image 1 wears the jacket from image 2 …"). |
| Resolutions and aspect ratios | `resolution` ∈ {`768sq`, `1k` (default), `1.5k`, `2k`, `4k`}, equal-area tiers ("about" 1/2/4/16 MP). `aspect_ratio` ∈ 21:9, 2:1, 16:9, 3:2, 7:5, 4:3, 5:4, 1:1, 4:5, 3:4, 5:7, 2:3, 9:16, 1:2, 9:21, or `auto` (the default; it follows the first reference). Each reference must be at most 16 MP (HTTP 400) and at least 256×256 (HTTP 422). |
| Other inputs | `safety_tolerance` 0–7 (default 2); `grounding` (default **true**: "web search and image search"). `additionalProperties: false`, so `seed`, `width`, `input_image` and similar fields get HTTP 422. |
| Official price | Per image, by resolution: 768sq **$0.041**, 1k **$0.048**, 1.5k **$0.070**, 2k **$0.100**, 4k **$0.607**. References are not charged. Source: the pricing feed behind the pricing page (US cents; 1 credit = $0.01), confirmed in the release notes for 768sq/1k/2k/4k. This matches the owner's observed US$0.048 per image. |
| Async flow | The submit response has `id`, `polling_url`, `cost` (credits), `input_mp` and `output_mp`. Poll `polling_url` (always the returned one). Statuses: `Pending`, `Reasoning`, `Generating` (in progress), then `Ready`, `Request Moderated`, `Content Moderated`, `Error`, `Task not found` or `No Card Generated`. A failed task can return HTTP 503 with a JSON `status`. Concurrency limit: 24 requests. |
| Receipt metadata | Submit: `id`, `cost`, `input_mp`, `output_mp`. Ready: `result.sample` (URL), `result.prompt` (expanded prompt) and `result.duration` (seconds). `get_result` may return a settled `cost`. **FLUX 3 returns no seed and does not accept one**; the task `id` is the reproducibility handle. |
| Result-URL expiry | The FLUX 3 page says the `result.sample` URL "expires after **1 hour**". The integration guidelines say "Generated images expire after **10 minutes**", which the repo measured in 2026-09. The sources disagree, so the adapter stores the bytes immediately either way. |
| Free endpoint | `GET /v1/credits` exists, but the docs do not say it is non-billing. It also needs the key, which is not in this container, so it was **skipped**. |

Railway (`brambleloop` / `brambleloop-os` / production, names only, values redacted by the
connector): **`BRAMBLELOOP_IMAGE_KEY_BFL` is set.** `BRAMBLELOOP_IMAGE_KEY_GOOGLE` and
`BRAMBLELOOP_IMAGE_KEY_OPENAI` are also set. `BRAMBLELOOP_IMAGE_PROVIDER` is not set, which is
correct because callers name `provider_key`. `flux-3-image` uses account `bfl`, so it resolves
the existing key: `images.key_for("flux-3-image")` reads `BRAMBLELOOP_IMAGE_KEY_BFL`. The BFL
credit balance is **UNKNOWN**.

## 3. Repair (`gateway/images.py`, `visual/conditioning.py`)

- **All references are transmitted.** FLUX.2 uses `input_image` .. `input_image_8`. FLUX 3 uses `images: [...]` in order. The cap is the provider's documented `reference_images` (8 and 10). **More references than the cap are refused** (`ImagesRefused`) before any reservation or request, never truncated. `image_prompt` is never sent.
- **FLUX 3 Image added** as `flux-3-image` (dialect `bfl3`, limit 10, table price $0.048 = the 1k tier). `WxH` maps to a documented `aspect_ratio` (an undocumented ratio is refused) and to an equal-area `resolution` tier. `grounding` is **off by default**: web and image search would bring other people's photography into a Brambleloop render. Unknown fields are refused locally instead of costing a 422.
- **The receipt** (`conditioning_receipt`) records every reference's `sha256`, `field` (`images[i]` / `input_image_N`), position, a `reference_sha256s` list, `reference_limit`, and the `price` reserved.
- **Price reservation before the call.** `render_estimate_usd` gives FLUX 3's tier price, read from the built body, and FLUX.2's published MP formula, including every reference's input MP. It is never below the table price. That estimate is reserved through the existing `reserve_render` / `check_budget_cad`, and the ledger bills the same estimate, so reservation and bill reconcile. **No ceiling was changed.**
- **Bounded attempts.** Each `generate` makes exactly one POST. The poll is bounded (150 × 2 s = 300 s, which covers the owner's slowest 216 s). Only the documented in-progress statuses keep polling; any other status (moderation, `Task not found`, `No Card Generated`, anything unknown) ends the poll immediately. Before, `"Request Moderated"` did not match `request_moderated` and the poll ran to its timeout. A 503 poll response carrying a JSON `status` is read as a status. The FLUX 3 poll branch was also missing (`dialect == "bfl"` only) and is now fixed.
- **Result bytes** are fetched and written to `work_dir` at once and `sha256`-fingerprinted. The result also carries `model` and `provider_receipt` (`id`/`task_id`, `cost` credits, `input_mp`, `output_mp`, `duration_s`, `seed` (always None on FLUX 3), the expanded-prompt sha256, and `settled_cost_credits`).
- **Conditioning packages regenerated.** `SINGLE_REFERENCE_DIALECTS` is now empty, so BFL packages carry the full Laura pack (portrait, torso, full length): `flux-2-pro.json` has `transmitted: 3`, and a new `flux-3-image.json` was added.

## 4. Product references from the certified pattern (`creative/pattern_refs.py`, `creative/stitch_texture.py`)

D-W4-LAURA-FLUX3 rule 2, plus the owner directive after the reading-nook test. `build(cir,
release_hash=..., out_dir=..., version=None)` renders **four** PNGs from the compiled CIR and twin.
No model is involved and the cost is CA$0. They become provider image inputs 4–7:

| # | role | content |
|---|---|---|
| 4 | `layout` | The complete product. Every component is drawn `make` times at **one shared px-per-cm** in its true finished proportion. Flat pieces use `render_fabric`; round pieces use `render_round_fabric`, scaled uniformly so a schematic circle is not stretched into an ellipse. There is no text, because words in a reference get copied. |
| 5 | `texture` | **New, with priority over the chart.** A close-up of what the crochet fabric looks like, drawn from `cir.stitches` and the twin's cells: the sideways chain of top-loop Vs, short sc bodies, dc posts with the diagonal yarn-over and open gaps, hdc bars, and 2-over-2 cable crossings with the front pair raised over the back pair. It uses gauge-true proportions. The crop runs from the bottom edge up until every stitch type in the piece appears, plus one cycle, and it never splits a cable group. Where the CIR gives no crossing side, the manifest records `UNKNOWN (drawn as front by convention)`. |
| 6 | `detail` | The symbolic chart, kept: per component, enlarged, with glyphs and row numbers, plus the legend. |
| 7 | `rules` | The technical rules: pieces (×make, rows×sts, cm, shape), piece count, garment size and built measures (when graded), gauge, repeat, stitches, exact colours with swatches and metres, assembly, prohibited additions, and **"THIS FABRIC: NEVER"**, the CIR-derived negatives. |

- **Category adapts from the data.** Multi-piece: the hexagon set draws 4 coasters, and the Harbour pullover draws body ×1, sleeve ×2 and neckband ×1, with assembly steps and garment measures. Front and back appear separately only where the CIR models them as separate components; the Harbour body is a single piece.
- **Binding.** Each file is sha256-fingerprinted and named with the release-hash prefix. The manifest is bound to the release hash (`runtime.release._content_hash_of`). A wrong hash, a wrong `version`, or another version's content with this hash are all **refused**. Every reference is kept inside FLUX 3's input bounds (≥256 px, ≤16 MP). The output is byte-deterministic.
- **`fabric_facts` / `negatives`** are derived from the cells, never typed by hand. They cover: end bands (maximal uniform runs at each end); edging (declared only by a component or assembly naming edging/border/trim/fringe); ribbing (declared only by front/back-loop stitches or fpdc+bpdc); cable columns, crossing size, separator, edge stitches and row period; and the rows where colour changes. On the reading-nook wrap they reproduce exactly the owner's line-by-line check: 8 cable columns, 2-over-2 crossings, 3 dc between, 3 dc at the edges, crossings every 4 rows, plain cream sc at rows 1–4 and 153–156, and colour changes only at rows 5 and 153.
- **Certification** is the caller's input. Stages take a `Release` whose hash the orchestrator reads from the certified ProductVersion row. pattern_refs proves content identity but does not run `certify` (the reading-nook wrap is uncertified because of UNCALIBRATED_PRIMITIVE cable2x2).

## 5. Generation stages (`creative/image_stages.py`, `creative/flux_prompt.py`): interface for W-OWNERIMG

```python
release = release_from_cir(cir, release_hash=..., out_dir=..., version=None)       # refs 4-7, free
flat    = product_only(release, *, scene=None, renderer=None, work_dir, db=None, job_id=None, max_attempts=2)
verdict = fidelity_verdict(flat, status="PASS"|"FAIL"|"UNKNOWN", checker=..., failures=[failure_codes...])
life    = lifestyle(release, flat, laura_refs=None, outfit, *, fidelity=verdict, scene={environment,pose,framing},
                    role="lifestyle_hero", supplementary=(), renderer=None, work_dir, db=None, job_id=None, max_attempts=2)
var     = variant(release, base, role, edit_instruction="", *, outfit=None, scene=None, laura_refs=None,
                  renderer=None, work_dir, ...)
gallery_cost(...) ; campaign_references(...) ; combined_reference_sheet(...) ; laura_references(...)
```

D-W4-LAURA-FLUX3 compliance, each rule with a test:

| Rule | Implementation | Test |
|---|---|---|
| 1. Three canonical Laura references, always | `laura_references()` checks bytes against `canonical.CURRENT_REFERENCE_HASHES` (a42aeac7, afe6191f, f32bac68) and the forbidden list. Exactly three, in canonical order, at inputs 1–3. Re-checked in `_run` immediately before the call. Missing, altered, reordered, substituted, extra or forbidden references are refused before any call. | `test_w4_fluxstages`: `…canonical_laura_fingerprints…`, `…every_laura_generation_supplies_all_three…`, `…invalid_missing_or_substituted…refused_before_any_call` |
| Supplementary added, never substituted | Supplementary images go only after the campaign set (product candidate, outfit image, approved lifestyle). | `…supplementary_images_are_added_after_the_originals…` |
| 2. Product references from the exact certified version | `pattern_refs.build` binding plus `campaign_references`, which re-hashes every product reference against the release's fingerprints. | `…product_refs_come_only_from_the_exact_certified_version`, `test_w4_fluxtexture::…binds_to_the_release_and_the_stitch_set` |
| 3. Campaign set: face, torso, body, layout, **texture**, chart, rules | Seven inputs, plus the flat-lay product candidate and the outfit image: 9 of FLUX 3's 10. If a provider's documented limit is lower, references 4–7 are merged **losslessly** (pixel for pixel, no scaling, refused above 16 MP) into one sheet, and the receipt records `limitation` and `combined_sheet`. If even that does not fit, the call is refused. The Laura originals are never merged. | `…all_campaign_references_reach_the_provider_payload` (captured payload: 8 `images`, exact bytes), `…lower_provider_limit_merges_4_to_7_losslessly…` (crop equality; limit 4 is refused) |
| Receipt | Every position/role/sha256, the provider task id, seed (None on FLUX 3), cost, credits, latency, request sha256, conditioning proof, output sha256, attempts, prompt sections and text hash. | the payload test |
| Product-only needs no Laura or outfit | `product_only` carries references 4–7 only, and its prompt has no IDENTITY section. | `…product_only_needs_no_laura_and_no_outfit` |
| 7. Full prompt, generated and versioned | `flux_prompt.build` assembles seven pinned sections: `image.flux3.references@1`, `identity@1` (face, bust and body preservation), `product@2` (id, version, release, construction, pieces, size, exact hex colours, stitches, assembly, prohibited additions, the texture reference), `negatives@1`, `scene@1` (role, outfit, environment, pose and framing from W-OWNERIMG), `realism@1`, and `disclosure@1` (AI-disclosure, candidate-only publication restriction). The receipt holds each section's ref and sha256, `builder_version` and the text sha256. | `…the_full_prompt_is_built_from_certified_data_and_pinned`, `test_w4_fluxtexture::…prompt_carries_the_negatives…` |

**After the reading-nook test (owner directive):**
(a) The stitch-texture reference, above.
(b) The category-aware negatives, above. They always include "crochet, not knitting". A prompt cannot be built without them.
(c) **Stage order.** `product_only` is an unfolded, countable flat lay seen from directly above with margins. `lifestyle` is refused unless `fidelity` is a PASS verdict for **that exact flat lay** (matching sha256 and release). FAIL, UNKNOWN, a verdict for another image, and a non-flat-lay product image are all refused before any call. The check that produces the verdict is W-OWNERIMG's or the gates' (Product Truth unchanged); `fidelity_verdict` only binds its answer to the bytes.
(d) **`creative/failure_codes.py`** is the one shared constant: `INVENTED_END_BAND_TREATMENT`, `INVENTED_EDGING`, `WRONG_CRAFT_TEXTURE` and `UNVERIFIABLE_COUNT`, each in category `product_fidelity` (= `candidate_gates.FAILURE_CATEGORY["product_truth"]` on W-OWNERIMG), and each naming its counter. W-OWNERIMG's learning records should import it. The test asserts it equals the RECORD.json codes.

Bounded attempts: only `TransientError` retries, up to `max_attempts`, with a hard cap of 3. Refusals, moderation, `QuotaUnavailable` and `BudgetExceeded` are final. `StubRenderer` has the same interface, no network and no spend, and accepts `reference_limit=` to imitate a smaller provider.

## 6. Cost model (published price; the pass rate is UNKNOWN)

One gallery is 1 product-only + 2 lifestyle + 3 variants = 6 accepted images, all at the 1k tier ($0.048 each). CA$ uses the repo's assumed rate of 1.3986 per US$.

| renders bought per accepted image | renders | US$ | CA$ |
|---|---|---|---|
| 1.0 (everything passes first time) | 6 | 0.288 | 0.40 |
| 1.5 | 9 | 0.432 | 0.60 |
| **2.0 (planning assumption)** | **12** | **0.576** | **0.81** |
| 3.0 (= per-call attempt cap, worst bounded) | 18 | 0.864 | 1.21 |

At the CA$100 monthly ceiling that is about **124 galleries per month** at the planning rate, and
the `creative_director` daily permission (CA$28) allows about 34 galleries per day. A
lifestyle shot at 1.5k instead of 1k costs $0.070. A 4k hero costs $0.607, which is 12.6× the
1k price, so it is not a default. Excluded from these figures: vision-model verification
(priced by the text gateway) and Klein ($0.009 at 1k), which was not evaluated.

## 7. AUTONOMOUS_PIPELINE_PLAN

| # | Step | Existing modules | Status | Missing | Est. h |
|---|---|---|---|---|---|
| 1 | Retrieve the certified product | `runtime.release` (`_load_cir`, `_released_on`, `_content_hash_of`), `gates.certificate.certify`, `products.launch0.cir_for` | EXISTS | A one-call `certified_release(db, slug)` that returns (CIR, release_hash) only when certified | 1 |
| 2 | Pattern-derived refs: layout (99×100 for Cloudline), stitch texture, chart, rules | **`creative.pattern_refs`** + **`creative.stitch_texture`** (flat, round, multi-piece and garment all tested) | **BUILT** | Texture realism is diagrammatic, not photographic; its effect on FLUX output is unmeasured until a paid run | 0 |
| 3 | Laura refs | `visual.canonical` (laura-r2-a42aeac7, `reference_file`), `visual.conditioning` packages (now 3 frames for BFL), `visual.model_registry.canonical_image_refs` | EXISTS | Nothing. Pass `canonical.reference_file(frame)` for `FRAME_ORDER` | 0 |
| 4 | Unused outfit | W-OWNERIMG outfit registry (not on this branch) | MISSING here (owned by W-OWNERIMG) | Reserve-and-mark-used; passed to `lifestyle(outfit=...)` | (W-OWNERIMG) |
| 5 | Product-only flat lay | **`image_stages.product_only`** (unfolded, countable) + `gateway.images` FLUX 3 | **BUILT** (no live render yet) | First paid live render (owner-gated, about $0.05) | 0.5 |
| 6 | Lifestyle candidates | **`image_stages.lifestyle`**: three canonical Laura refs, the campaign set, gated on a flat-lay PASS verdict | **BUILT** (no live render yet) | Orchestrator loop (W-OWNERIMG) | 1 |
| 7 | Other roles | **`image_stages.variant`** (6 closed roles); deterministic frames come from `publish.listing_set`, `visual.gallery_frames`, `visual.frame_role` | **BUILT** | Mapping from gallery slots (`visual.gallery`, #77–81) to variant roles | 2 |
| 8 | Independent verification | `visual.identity_gate` (F-213, Laura), `visual.final_image_gate` (Product Truth), `publish.motif_fidelity`, `visual.render_verification`, `gates.asset_truth`, `visual.photoreal` | PARTIAL | **Key gap:** `final_image_gate` can PASS a product region only by deterministic pixel proof against the disclosed renderer. A generative FLUX image can fail that gate but has no deterministic way to pass it. One option is a verifier that compares the candidate's product region with the pattern `layout` reference (palette, repeat period, aspect). Another is compositing the disclosed render into the scene. This needs a design decision before any generated product image can publish. | 8–12 |
| 9 | Reject and learn failure categories | **`creative.failure_codes`** (shared, 4 owner codes); `visual.candidate_gates.FAILURE_CATEGORY` (W-OWNERIMG); `finance.systematic` | PARTIAL | W-OWNERIMG's learning records import `failure_codes` | 1 (+W-OWNERIMG) |
| 10 | Gallery assembly and approval | `visual.gallery`, `publish.listing_assets` (W-PRODREADY), `publish.listing_set`, `visual.approval_record`, Command Center (W-OWNERIMG) | PARTIAL | Assemble accepted candidates with deterministic frames, then the owner approval card | 3 (+W-PRODREADY) |

## 8. Tests

| file | count | covers |
|---|---|---|
| `tests/test_w4_fluxapi.py` | 13 | The adapter. Every reference is transmitted (FLUX 3 `images[]`, FLUX.2 `input_image..8`); the old defect shape is gone; over-limit references are refused before any spend; the receipt lists every hash and field; the documented price is reserved before the POST and the ledger reconciles; the FLUX.2 MP formula; an exhausted budget sends nothing; one POST per render; a bounded poll; terminal statuses stop the poll and are billed `accepted_then_failed`; bytes are stored and fingerprinted with the provider receipt; a 503 status body is read; aspect and tier mapping; unknown fields are refused. |
| `tests/test_w4_fluxstages.py` | 16 | D-W4-LAURA-FLUX3. The three canonical refs are always supplied first; invalid, missing or substituted refs are refused before any call; supplementary refs are added, never substituted; product-only has no Laura; product refs come only from the exact version; multi-piece, round and garment adaptation stays inside FLUX bounds; the full campaign set reaches the provider (captured payload); the lossless combined sheet under a lower limit; the full pinned prompt; bounded attempts; reserve-before-POST; an exhausted budget; the gallery cost. |
| `tests/test_w4_fluxtexture.py` | 9 | Reading-nook lessons. The texture binds to the release and stitch set; it shows the plain cream band and whole cable groups; the crop never splits a group; the wrap negatives name each owner failure; declared features are not forbidden; the prompt carries the negatives and names the texture; product-only is a flat lay; lifestyle is gated on a PASS for that exact flat lay; the shared failure codes equal RECORD.json. |
| Updated (stricter) | | `test_w4_condpack` (BFL now 3/3), `test_rc1_spend` and `test_cert_cost` (bill at the documented per-call price). |

Regression set (all through `testslot`, all green): vacuity 8, launch 28,
cost_governance_wave2 39, search_hero_publish 4, cert_listing_frames 7, v11_autonomy_timeline 7,
plus gateway 30, spend_paid_discipline 14, cert_cost 19, rc1_spend 20, image_bench 59,
model_spend_paths 12, w3_spend_paid_calls 9, reference_pack 44, provider_trial 22, condpack 7.

## API limitations (what the docs do not give us)

- **No seed.** FLUX 3 Image neither accepts nor returns one, so exact regeneration is impossible; the task `id` and `result.prompt` hash are the receipt.
- **The 10-reference cap** fits the campaign set (7) plus the flat lay and the outfit image (9). One slot is left for a supplementary image.
- **References are not charged**, so the campaign set costs the same as text-to-image ($0.048 at 1k).
- **Result URLs expire** (1 hour on the FLUX 3 page, 10 minutes in the integration guidelines); bytes are stored at once.
- **`grounding` defaults to true**, which allows web and image search. The adapter sets it to false.
- **Unknown fields return 422**, so no `seed`, `width` or `output_format`; resolution is a tier, not pixels.
- **Reference bounds**: each reference must be ≤ 16 MP and ≥ 256 × 256, which every pattern reference is held to.
- **Prompt length limit: not documented.** The built prompt is about 3–4 k characters; whether FLUX 3 truncates it is UNKNOWN until a paid run.
- **Whether FLUX 3 follows the texture reference and the negatives is unmeasured.** These references address the four observed failures, but only a paid render plus the Product Truth gate can show it.

## 9. Owner actions

To enable FLUX 3 through the API, **no new credential is needed**: `BRAMBLELOOP_IMAGE_KEY_BFL` is
already on brambleloop-os and covers `flux-3-image`. Remaining:

1. **Merge and deploy** this branch through the integrator. Production does not yet have the `flux-3-image` route or the multi-reference repair.
2. **BFL credit balance: UNKNOWN.** The account answered 402 `Insufficient credits` on 2026-09-21. If the balance is below about US$1, top up on dashboard.bfl.ai. Why: every render reserves against it. Max cost: owner's choice (one gallery is about US$0.58 at the planning rate). About 3 minutes. If this waits, the first live render returns `QuotaUnavailable` (refused, not retried, nothing billed).
3. **Approve the first paid live render** (consequential-spend rule): one product_only candidate for Cloudline at $0.048, to prove the live route and its receipt. Until then, FLUX 3 through the API is documented and wired but **unmeasured**.

## 10. Open items, not closed here

- Historical flux-2-pro "identity" renders were conditioned through an undocumented field. Their conditioning should be treated as **UNKNOWN**, not proven. No stored verdict was re-classified by this branch.
- The flux-2-pro table price (`usd_per_image` 0.02) is left as the benchmark's frozen figure. `image_bench` fingerprints it and `visual.rnd` picks the cheapest table price. The per-call reservation and bill now use the documented formula.
- No per-provider ceiling is set (`PROVIDER_CEILINGS_CAD` is empty). Setting one for `flux-3-image` is an owner decision on the limit's value.
