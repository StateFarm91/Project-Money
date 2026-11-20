# FLUX 3 listing images: owner decisions (ENG-VIS-FLUX)

- **Date:** 2026-11-20 UTC.
- **Branch:** `eng/vis-flux`. It is not merged and not deployed.
- **Prices:** read from Black Forest Labs' pricing page on 2026-11-20 (https://docs.bfl.ai/quick_start/pricing, 1 credit = US$0.01).
- **Conversion:** CA$ figures use the build's single assumed rate, `core.fx.ASSUMED_CAD_PER_USD` = 1.4154. That rate is an assumption, not your bank's rate.

Nothing here has been spent: no BFL request has been made from this build.

---

## OWNER ACTION REQUIRED 1: make sure the BFL key is in Railway

| | |
|---|---|
| **Exact action** | In Railway, open the Brambleloop project and then the web service that `brambleloop/railway.json` deploys. Under **Variables**, confirm that **`BRAMBLELOOP_IMAGE_KEY_BFL`** exists. If it does not, add it. Its value is an API key from https://dashboard.bfl.ai, under **API Keys**, then **Create key**. Railway redeploys the service when a variable changes. |
| **Variable name the code reads** | `BRAMBLELOOP_IMAGE_KEY_BFL` (`gateway.images.key_var("bfl")`, stated again in `gateway.flux_provider.KEY_ENV_VAR`). One fallback is accepted: `BRAMBLELOOP_IMAGE_KEY`, but only together with `BRAMBLELOOP_IMAGE_PROVIDER=flux-3-image`. Prefer the specific name. |
| **Why** | No FLUX 3 render can be sent without it. The code reads only whether the key is present. It never reads the value into a report, a log or an error. |
| **Note** | The paid-provider gate's own record says production had `BRAMBLELOOP_IMAGE_KEY_BFL` set as of 0967c3ee (2026-11-02). This build cannot check that without reading Railway's variable values, and it deliberately does not. Please confirm it is still there and still valid; the BFL dashboard shows whether a key is active. |
| **Credit** | The BFL account needs prepaid credit. A 402 "Insufficient credits" answer is recorded as a top-up problem, never as a content refusal. |
| **Maximum cost** | CA$0. A key costs nothing. Credit is a separate purchase, sized below. |
| **Minutes** | About 4. |
| **If you wait** | Readiness stays `UNKNOWN [no_bfl_credential]`. No FLUX gallery is generated, and nothing is spent. |

## OWNER ACTION REQUIRED 2: activate `flux-3-image` for generation (existing step-up route)

| | |
|---|---|
| **Exact action** | In the Command Center, step up, then call `POST /api/cc/paid-providers/activate` with these values. Suggested ceilings are shown; you may choose lower ones. |
| | `provider` = `flux-3-image` |
| | `scope` = `generation` |
| | `daily_ceiling_cad` = **9.00** |
| | `monthly_ceiling_cad` = **60.00** |
| | `per_gallery_cad` = **2.50** |
| | `expires_at` = 30 days out (90 days at most) |
| | `max_attempts_per_request` = 2 |
| | `max_calls_per_run` = 40 |
| **Why** | A key is a credential, not an activation. Every render passes `paid_provider_gate.enforce`, which refuses with `not_activated_by_owner` until this exists. |
| **What then opens `image_generation`** | One probe render under that activation, which costs CA$0.07 (the 1k tier). |
| **Maximum cost** | The monthly ceiling you set. With the suggestion above, CA$60/month. That is inside, and never above, the CA$100 company ceiling; the code refuses a provider ceiling above the company's. |
| **Minutes** | About 3. |
| **If you wait** | Readiness stays `UNKNOWN [not_activated_by_owner]`. The generation job refuses before reserving anything. |

These two actions are the whole activation. Nothing else is needed for generation.
- **Publishing.** Publication of any generated image stays behind every existing gate: F-852 / D-W4-F852-AMEND, F-856, Etsy policy, SHADOW.
- **Identity.** The Laura identity gate is ENG-VIS-IDENTITY's.

---

## What an image costs (FLUX 3 Image is priced per image, by resolution tier; references are free)

| Tier | Output | Credits | US$ | CA$ (×1.4154) | Used for |
|---|---|---|---|---|---|
| `768sq` | 768×768 | 4.1 | 0.041 | 0.058 | not used |
| `1k` | about 1 MP | 4.8 | 0.048 | 0.068 | the stage-A identity anchor (intermediate, never shipped), the probe |
| `1.5k` | about 2 MP | 7.0 | 0.070 | 0.099 | not used: it is under the 2000 px listing floor |
| **`2k`** | **about 4 MP (2048×2048 at 1:1)** | **10.0** | **0.100** | **0.142** | **every listing frame** |
| `4k` | about 16 MP | 60.7 | 0.607 | 0.859 | not a default. The 4:5 tall frame only; whether it works with references is UNKNOWN (see the audit) |

## Per gallery and per month

**One seven-frame gallery:**
- Seven listing frames at 2k cost 7 × CA$0.142 = CA$0.99.
- A Laura gallery adds one identity anchor at 1k: CA$0.07.

| Gallery | Images | CA$ |
|---|---|---|
| Product-only, no repairs | 7 | **0.99** |
| With Laura, no repairs | 8 | **1.06** |
| With Laura and one repair on a third of the frames (typical) | about 10.3 | **about 1.39** |
| The code's hard ceiling per gallery | 16 | **2.50** |

**Per month at about 50 galleries:**

| Case | CA$/month |
|---|---|
| Laura galleries, no repairs (50 × 1.06) | **53** |
| Typical repairs (50 × 1.39) | **about 70** |
| Every gallery at its cap (50 × 2.50) | 125. This is never reached: the CA$100 company ceiling and your activation's monthly ceiling refuse first. |

**Recommendation:**
- Activate with a CA$60/month provider ceiling.
- That covers about 43 Laura galleries with typical repairs, or 56 without repairs.
- It leaves CA$40 of the CA$100 company month for vision review and everything else.
- Raise it only if the measured repair rate is lower than assumed.

## Caps in code (enforced below your activation; the environment can only lower them)

| Cap | Constant | Lowered by | Value |
|---|---|---|---|
| Images per UTC day, all image providers | `DAILY_IMAGE_CAP` | `BRAMBLELOOP_IMAGE_DAILY_CAP` | 60 images, so at most CA$8.49/day at 2k |
| Images per gallery | `GALLERY_IMAGE_CAP` | `BRAMBLELOOP_IMAGE_GALLERY_CAP` | 16 |
| CA$ per gallery, all image providers | `GALLERY_CAD_CAP` | `BRAMBLELOOP_IMAGE_GALLERY_CAD_CAP` | CA$2.50 |

- **Lower-only rule.** A value that is higher than the constant, unreadable or negative is ignored, and the constant stays in force.
- **Where the caps are checked.** They sit inside the same budget lock as the company month, after your activation's own day, month and gallery ceilings. The lower limit always binds.

## What is recorded for every image (D-W4-F852-AMEND item 7)

`gateway.flux_provenance` builds one record per render. It holds:
- the model and endpoint;
- the contract version;
- the prompt version and prompt hash;
- every reference's sha256, in position order, as found **inside the request body sent**, with Laura's three canonical originals marked by fingerprint;
- the request hash;
- BFL's task id, which is the receipt;
- the provider's credit figure and the reserved CA$ cost, with its ledger row;
- the output's sha256, pixel size and format;
- the gallery;
- the disclosure "AI-generated";
- `seed_supported: false`.

**Seeds.** FLUX 3 Image accepts no seed, so the seed is recorded only when BFL's result reports one. It is never invented.

**Incomplete records.** `missing()` names anything absent. Incomplete provenance is UNKNOWN, and UNKNOWN blocks.
