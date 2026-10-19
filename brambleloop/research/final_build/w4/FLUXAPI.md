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

## 4. Deterministic pattern references (`creative/pattern_refs.py`)

`build(cir, release_hash=..., out_dir=...)` renders three PNGs from the compiled CIR and twin. No model is involved and the cost is CA$0:

- `layout`: the full stitch/colour fabric (`charts.render_fabric`), rescaled with nearest-neighbour sampling to the **twin's true proportion**. The raw render came out landscape (1188×700), while the blanket is 79.2 × 96.4 cm.
- `motif`: two horizontal repeats by 24 rows, enlarged (44 px cells), with stitch glyphs, colour letters and row numbers (`charts.render_chart`).
- `construction`: the title, slug@version, release hash, construction, finished size, stitch and row counts, gauge, hook, repeat, yarns with hex swatches and metres, and constraints.

Each file is fingerprinted, and the manifest is bound to the release hash (`runtime.release._content_hash_of`, the hash `certify` names). A hash for different content is refused. `verify(manifest)` re-checks the bytes. The output is byte-deterministic. Cloudline 1.2.0 gives 99 stitches × 100 rows, a 9-stitch repeat, release `7c63dbdd501f…`.

## 5. Generation-stage interface for W-OWNERIMG (`creative/image_stages.py`)

```python
release = release_from_cir(cir, release_hash=..., out_dir=...)        # Release (pattern refs built, free)
product_only(release, refs=None, *, renderer=None, work_dir, db=None, job_id=None, max_attempts=2) -> Candidate
lifestyle(release, product_candidate, laura_refs, outfit, *, setting=..., action=..., renderer=None,
          work_dir, db=None, job_id=None, max_attempts=2) -> Candidate
variant(release, base_candidate, role, edit_instruction="", *, renderer=None, work_dir, db=None,
        job_id=None, max_attempts=2) -> Candidate
gallery_cost(lifestyle_count=2, variant_count=3, expected_attempts_per_accept=2.0, tier="1k") -> dict
```

- `Candidate(stage, role, path, sha256, release_hash, receipt)`. The receipt holds `model`, `provider`, `release_hash`, `prompt_ref`, `prompt_sha256`, `prompt_text_sha256`, `input_sha256s` (every reference, in order), `size`, `task_id`, `seed`, `cost_cad`, `provider_cost_credits`, `cost_entry_id`, `latency_ms`, `output_sha256`, `attempts`, `attempt_errors` and `price`.
- Reference order follows the owner's workflow. product_only: [layout, motif, construction]. lifestyle: [product candidate, Laura 1–3, outfit image?]. variant: [base candidate] (a FLUX 3 edit).
- `outfit` is W-OWNERIMG's registry entry, `{"id", "description", "image"?}`. `role` is one of `VARIANT_ROLES` (`detail_closeup`, `flat_lay`, `scale_in_hand`, `styled_scene`, `wardrobe_change`, `colour_context`). `wardrobe_change` requires the instruction.
- Prompts are pinned in `gateway.prompts`: `image.product_only@1`, `image.lifestyle@1` and `image.variant@1` are immutable and content-hashed.
- `renderer=None` means `flux3_renderer()`, which is `images.generate(provider_key="flux-3-image")`: reserve first, all references sent, bytes stored, billed. `StubRenderer` has the same call signature, makes no network call and spends nothing.
- Attempts: a `TransientError` is retried up to `max_attempts`, with a hard cap of `MAX_ATTEMPTS = 3`. `ImagesRefused`, `QuotaUnavailable` and `BudgetExceeded` are final after one call. Inside a job, `paid_calls` turns a retry of an already-billed render into a replay instead of a second purchase.
- Spend is attributed to agent `creative_director` (CA$28/day permission), with purpose `image.<stage>`.
- A candidate is **not** an approval. Verification and gallery approval stay with the gates (§7, steps 8–10).

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
| 2 | Pattern-derived refs (layout 99×100, motif, construction sheet) | **`creative.pattern_refs`** (new, tested on Cloudline), built on `publish.charts` | **BUILT** | Round-worked products (coasters, baskets) take the `render_round_chart` path; currently only flat CIRs are exercised | 2 |
| 3 | Laura refs | `visual.canonical` (laura-r2-a42aeac7, `reference_file`), `visual.conditioning` packages (now 3 frames for BFL), `visual.model_registry.canonical_image_refs` | EXISTS | Nothing. Pass `canonical.reference_file(frame)` for `FRAME_ORDER` | 0 |
| 4 | Unused outfit | W-OWNERIMG outfit registry (not on this branch) | MISSING here (owned by W-OWNERIMG) | Reserve-and-mark-used; passed to `lifestyle(outfit=...)` | (W-OWNERIMG) |
| 5 | Product-only candidate | **`creative.image_stages.product_only`** + `gateway.images` FLUX 3 | **BUILT** (no live render yet) | First paid live render (owner-gated spend, about $0.05) | 0.5 |
| 6 | Lifestyle candidates | **`image_stages.lifestyle`**; earlier paths are `publish.model_photography` and `visual.hero_candidates` | **BUILT** (no live render yet) | Orchestrator loop over 2 outfits/settings (W-OWNERIMG) | 1 |
| 7 | Other roles | **`image_stages.variant`** (6 closed roles); deterministic frames come from `publish.listing_set`, `visual.gallery_frames`, `visual.frame_role` | **BUILT** | Mapping from gallery slots (`visual.gallery`, #77–81) to variant roles | 2 |
| 8 | Independent verification | `visual.identity_gate` (F-213, Laura), `visual.final_image_gate` (Product Truth), `publish.motif_fidelity`, `visual.render_verification`, `gates.asset_truth`, `visual.photoreal` | PARTIAL | **Key gap:** `final_image_gate` can PASS a product region only by deterministic pixel proof against the disclosed renderer. A generative FLUX image can fail that gate but has no deterministic way to pass it. One option is a verifier that compares the candidate's product region with the pattern `layout` reference (palette, repeat period, aspect). Another is compositing the disclosed render into the scene. This needs a design decision before any generated product image can publish. | 8–12 |
| 9 | Reject and learn failure categories | `finance.systematic` (breaker per purpose), `learn.*`, `visual.rnd`, `visual.drift_series`; W-OWNERIMG owns learning records | PARTIAL | A closed failure-category vocabulary per stage (identity drift, product truth, anatomy, moderation, transient), written from receipts | 3 |
| 10 | Gallery assembly and approval | `visual.gallery`, `publish.listing_assets` (W-PRODREADY), `publish.listing_set`, `visual.approval_record`, Command Center (W-OWNERIMG) | PARTIAL | Assemble accepted candidates with deterministic frames, then the owner approval card | 3 (+W-PRODREADY) |

## 8. Tests

- `tests/test_w4_fluxapi.py` (13): all references are transmitted for FLUX 3 (`images[]`) and FLUX.2 (`input_image..8`); the defect shape is gone; over-limit (11/9) is refused with no POST and no reservation; the receipt lists every hash and field; the documented price is reserved before the POST and the ledger reconciles; the FLUX.2 MP formula is used; an exhausted budget means no POST; one POST on a transient failure; a bounded poll; terminal statuses stop the poll and the render is billed `accepted_then_failed`; bytes are stored and fingerprinted with the provider receipt; a 503 status body is read; aspect/tier mapping; unknown fields (`seed`) are refused.
- `tests/test_w4_fluxstages.py` (14): Cloudline references are 99×100, bound to the release, fingerprinted and byte-deterministic; the layout has the twin's proportion; a wrong release hash is refused; tampering is detected; prompts are pinned and immutable; product_only, lifestyle and variant are tested on the stub (reference order and refusals); bounded attempts, with only transient failures retried; product_only and lifestyle go through the real `flux3_renderer` on a mock transport (reserve before POST, every reference in `images[]`, 1:1 and 4:5 at 1k); an exhausted budget means no POST; the gallery cost model.
- Updated (stricter, not weaker): `test_w4_condpack` now requires BFL to transmit 3/3. `test_rc1_spend` and `test_cert_cost` now assert the render bills the documented per-call price (≥ the table price) instead of the stale US$0.02 table price.

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
