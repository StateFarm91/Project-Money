# FLUX integration audit (ENG-VIS-FLUX, slice 1)

- **Branch:** `eng/vis-flux`. It was cut from `origin/claude/w6-INTEG3` (39b92619), with `origin/eng/visual-factory` (c774d740) merged in.
- **Date of audit and of every documentation read:** 2026-11-20 UTC.
- **Network:** no BFL key exists in this build, so no live request was made. Every fact below comes from Black Forest Labs' official documentation, fetched from this container on the date above.

## Sources (all accessed 2026-11-20 UTC)

| # | URL | What was read |
|---|-----|---------------|
| S1 | https://api.bfl.ai/openapi.json | The machine-readable schema. It covers `Flux3ImageInputs`, `AsyncResponse`, `ResultResponse`, `SettledCostResultResponse` and `StatusResponse`. The security scheme `APIKeyHeader` is the header `x-key`. The paths are `/v1/flux-3-image`, `/v1/get_result` and `/v1/credits`. |
| S2 | https://docs.bfl.ai/api-reference/utility/generate-an-image-with-flux-3 | The API reference for `POST /v1/flux-3-image`, with text-to-image, edit and multi-reference examples. It uses the same schema as S1. |
| S3 | https://docs.bfl.ai/flux_3/flux3_image_overview | Up to ten references can be combined. `grounding` searches the web by default, and setting it to `false` turns that off. |
| S4 | https://docs.bfl.ai/flux_3/flux3_image_generate | Poll the `polling_url` until the status is `Ready`. The in-progress statuses are `Pending`, `Reasoning` and `Generating`. The `result.sample` signed URL expires after 1 hour. Never send `x-key` to that URL. |
| S5 | https://docs.bfl.ai/quick_start/pricing | 1 credit is US$0.01. The page embeds a rate card for `/v1/flux-3-image`: `tier768` 4.1, `tier1k` 4.8, `tier1_5k` 7, `tier2k` 10 and `tier4k` 60.7 credits. Exact sizes are billed at the smallest tier with at least as many pixels. |
| S6 | https://docs.bfl.ai/guides/prompting_unified_technical | The tiers are 768sq, 1k, 1.5k, 2k, 4k and `match_input`. An exact width or height must be 256–6256 px. The total is at most 16.8 MP, or 4 MP when reference images are sent. There is no `negative_prompt` or `prompt_upsampling` field. |
| S7 | https://docs.bfl.ai/api_integration/integration_guidelines | The returned `polling_url` must be used. Delivery URLs expire after 10 minutes and are not for direct serving. At most 24 concurrent requests are allowed. Use exponential backoff on 429. |
| S8 | https://docs.bfl.ai/api_integration/errors | The HTTP codes are 400, 402, 403, 422, 429, 500 and 503. `Request Moderated` happens before processing and `Content Moderated` after. FLUX 3 Image accepts `safety_tolerance` **0–4**, with a default of 2. A value above that is a 422. |

A trimmed, machine-extracted copy of S1 is kept at `tests/fixtures/bfl_flux3/openapi_snapshot.json`, and the S5 rate card at `tests/fixtures/bfl_flux3/pricing_rate_card.json`. The contract test (`tests/test_eng_vis_flux.py`) compares the code against both, with no network.

## What "FLUX 3" is today

- **The FLUX 3 family (S1, S3).** FLUX 3 is the current family: FLUX 3 Image, FLUX 3 Image Klein and FLUX 3 Video.
- **The multi-reference endpoint (S3).** The image-conditioning endpoint is **FLUX 3 Image itself**, `POST /v1/flux-3-image`.
  - Its `images` field takes one to ten references, each a URL or base64.
  - The prompt refers to each reference by its position.
- **FLUX.1 Kontext.** Kontext is the previous generation. The docs recommend FLUX.2 or later for new work.
- **This build's use.** This build conditions listing frames on FLUX 3 Image only. `flux-2-pro` stays in the provider table for the benchmark.

## The audit, item by item

| Area | Before this slice (file:line at 39b92619) | Verified against | Finding | Action |
|---|---|---|---|---|
| Model, endpoint | `gateway/images.py` provider `flux-3-image`, `https://api.bfl.ai/v1/flux-3-image`, dialect `bfl3` | S1, S2 | Correct | Pinned by the contract test |
| Auth | `x-key` header (`_request_for`) | S1 security scheme | Correct | Pinned |
| Request fields | `BFL3_FIELDS` = prompt, images, aspect_ratio, resolution, safety_tolerance, grounding, version | S1 `Flux3ImageInputs` | **Stale.** The schema now also has `user`, `width` and `height` | `BFL3_FIELDS` is now read from `flux_contract.REQUEST_FIELDS` |
| Seed | Not sent. `result.seed` is recorded if present | S1 (no `seed`; `additionalProperties: false`) | Correct. FLUX 3 Image **cannot be seeded**, so determinism by seed is not available | Provenance records `seed_supported: false`, and the provider's seed only when its result reports one. A seed is never invented, because it would be a 422 |
| Whole-body validation | Unknown fields refused. No range checks | S1, S6, S8 | **Gap.** `safety_tolerance` above 4, exact sizes over 4 MP with references, `match_input` without refs and similar requests would leave the building and come back 422 | `flux_contract.validate_request` runs on the built body before any reservation |
| References | Base64 inline, all of them, in order. More than 10 is refused. The receipt proves the bytes are in the body (F-212) | S1 (`images` takes one to 10), S3 | Correct | Unchanged. Provenance carries their SHAs and order |
| Resolution | `2048x2048` maps to `aspect_ratio 1:1`, `resolution 2k`. The output size is measured after rendering (`image_stages._measure`) but **not rejected** | S5, S6 (2k is "about 4 MP") | **Gap.** A below-floor or wrongly shaped output was recorded with `meets_listing_floor: false` and still went on to QA | `gateway/flux_qc`: a listing frame is rejected at generation (see below) |
| Tall 4:5 frame | `TALL_LIFESTYLE_SIZE = 3664x4580` at the 4k tier | S6 (exact sizes are at most 4 MP with references; `match_input` shrinks to 4 MP) | **UNKNOWN.** The docs do not say whether `resolution: 4k` is honoured when references are sent. Reaching at least 2000 px on the short side of a 4:5 frame needs more than 4 MP | Not a default. If it is used, the generation check measures the real output, so a downsized result is rejected rather than shipped. Each attempt costs CA$0.86 |
| Safety | `safety_tolerance` not sent, so the default of 2 applies. `grounding: false` | S8, S3 | Correct. Grounding off keeps web images out of the inputs | Range 0–4 is now enforced if a caller sets it |
| Submit / poll | POST, then GET of the returned `polling_url` with `x-key`. The poll is bounded (150 × 2 s) | S4, S7 | Correct | `flux_contract.validate_submit` / `classify_result` are available and pinned to the recorded shapes |
| Status vocabulary | `BFL_IN_PROGRESS` = pending, reasoning, generating, queued, processing. Everything else is terminal | S1 `StatusResponse`, S8 | Correct in effect: `queued` and `processing` are not documented but harmless. `No Card Generated` is terminal | Unchanged (LOW). The contract names the documented set |
| Moderation | A terminal status, with the body in the message | S8 (`details["Moderation Reasons"]`) | Correct | `flux_contract.moderation_reasons` extracts the categories |
| Delivery | Downloaded at once without `x-key`. The SHA is recorded on arrival | S4, S7 (10 min / 1 h expiry) | Correct | A corrupt download is now re-fetched for free (up to 2 times) before it is called corrupt |
| Errors | 402 is quota. A 429 that names a plan limit is quota. Other 429s and 5xx are transient. A 503 that carries a status body is read. 422 and others are refused | S8 | Correct | Unchanged |
| Retries | Transient errors only, at most 3 per stage (`image_stages.MAX_ATTEMPTS`). The gate retry ceiling is 2 per request. `already_billed` idempotency | S7 | Correct | QC rejections are **not** retried with the same request, because the gate would refuse it as already billed. A replacement goes through `flux_provider.replacement_allowed` |
| Concurrency | Not enforced. The scratch lock serialises one adapter | S7 (24) | Not reachable at current volumes (the day cap is 60 images) | None |
| Price | `BFL3_TIER_USD` = 0.041 / 0.048 / 0.070 / 0.100 / 0.607 | S5 rate card | Correct | Pinned by the contract test |
| Spend path | `reserve_render`, then `check_budget_cad`, then the owner gate `enforce`, then the post, then the ledger row | — | Correct | Code caps per day, per gallery (count) and per gallery (CA$) are added inside the gate |
| Provenance | Spread over the stage receipt | D-W4-F852-AMEND item 7 | **Gap.** There was no single record and no completeness check | `gateway/flux_provenance` holds one record per render, and `missing()` names any absent field |
| Activation | `paid_provider_gate` refuses every render without the owner's activation | P0-PAID-PROVIDER-OWNER-GATE | Correct | `flux_provider.readiness` gives the generation job an UNKNOWN reason **before** it reserves |

## Generation-time check (`gateway/flux_qc.py`)

- **Listing frames.** A listing frame is PNG or JPEG, opaque, at least **2000 px on the shortest side**, and within 1% of the aspect ratio it asked for.
- **Intermediate frames.** An intermediate frame (the stage-A identity anchor, 1k tier) follows the same format and aspect rules, with a 900 px floor.
- **When it runs.** The check runs the moment the bytes are on disk, before any judge.
- **A failing render:**
  - stays **billed**, with its ledger row;
  - keeps its bytes at its path;
  - gets an audit row, `image.generation_rejected`;
  - raises `ImagesRejectedAtGeneration` with the reason codes.
- **Corrupt downloads.** A corrupt download is re-fetched from the same delivery URL at most twice before it is rejected. Re-fetching costs nothing.
- **Upscaling.** Nothing is upscaled or re-encoded to pass.

## Open items (honest)

- **No live render yet.** This needs the owner's key, an activation and one render.
  - That render would also check whether the 2k tier at 1:1 delivers exactly 2048×2048 (S6 says only "about").
  - The generation check will reject the render if it does not.
- **The 4:5 frame at 4k with references is UNKNOWN** (see the table above).
- **Wiring the rejection reason into W-OWNERIMG's repair routes** belongs to the gallery orchestrator. This slice only exposes `.reasons`.
