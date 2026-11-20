# Laura identity verification: owner decisions (ENG-VIS-IDENTITY, 2026-11-20)

**Status today:** Laura's identity still **cannot PASS** in production, and that is the correct
state. The verification method is built, measured and wired. The things it still needs are listed
below, and every one is either the owner's call or blocked on a key this build session did not have.

Identity: `laura-r2-a42aeac7`. Her three canonical references were read and verified by SHA-256.
They were never modified.

## What exists now (verified in this branch)

- **Biometric method, option (a).** YuNet face detector plus SFace face embedder: two ONNX models
  run on CPU with `onnxruntime` and numpy (`visual/face_embedder.py`).
  - Weights are pinned by SHA-256. Unpinned bytes are refused.
- **Calibration harness** (`visual/identity_calibration.py`).
  - Thresholds come from measurements, never from choice.
  - It reports FAR/FRR with exact 95% upper bounds.
  - Production floors: at least 30 genuine samples, at least 300 impostor faces, FAR upper bound
    of 1% or less, FRR of 10% or less.
  - A reference SHA mismatch refuses the whole run.
- **Measured on the licence-safe set available today** (`w6/identity_calibration/calibration_evidence.json`,
  evidence sha `6884612e…`):

  | | value |
  |---|---|
  | genuine samples (Laura, owner-viewed frames generated on her face a42aeac7) | 12 (+60 augmented, not counted) |
  | impostor faces (owner concept look-alikes + one unrelated generated woman) | 10 |
  | Laura's worst score (worst-of-3 references) | 0.696 |
  | best look-alike score | 0.582 |
  | derived thresholds | `match_at` 0.64, `refuse_below` 0.54 |
  | FAR / FRR at `match_at` | 0 / 10 and 0 / 12 (augmented: 0 / 60) |
  | **FAR 95% upper bound** | **25.9%**, so **not production-ready** (10 impostors cannot support a 1% claim) |
  | CPU cost | 0.08 CPU-s per frame (1 thread); model load 0.2 s |
  | RAM | about 120 MB on top of the worker while loaded (165 MB peak for a bare Python process) |

  The owner's manual FLUX 3 attempts at Laura score 0.68–0.79. That is above `match_at`, but it
  is information only: they are unlabelled and never used as calibration labels.
- **Second independent judge.** OpenAI `gpt-4.1-2025-04-14`, a different provider from the
  Anthropic first judge.
  - It uses the same `GatewayVisionJudge` reservation path: the CA$100 ceiling and one ledger row.
  - It also passes OpenAI's own `paid_provider_gate` activation (`openai-vision`).
  - It answers only when an OpenAI key is set **and** the owner has activated `openai-vision`.
    Otherwise identity stays HOLD.
- **Rules.**
  - PASS needs the qualified method **and** two agreeing judges.
  - Disagreement means HOLD, with the reason given.
  - Drift means REFUSE.
  - UNKNOWN, unmeasured or unqualified means HOLD.
- **All three references are mandatory.** A frame conditioned without all three canonical
  references (face, torso, full body) is INVALID.
- **Outfits.**
  - `outfits.claim` makes an idempotent, durable claim of one distinct outfit per listing.
  - A blind per-frame check runs against the outfit's approved reference image, in addition to
    the five-slot description check.
- **Identity records.** The `visual_identity_records` table holds, per image: the verdict,
  references with their SHAs, the method, the qualification, every judge's reading and the
  outfit. It survives restarts.

## Options evaluated

| option | licence / access | per-check cost | 350 frames/mo (+50% retries = 525) | verdict |
|---|---|---|---|---|
| **(a) SFace + YuNet ONNX on the Railway worker** | Apache-2.0 (SFace, OpenCV zoo) + MIT (YuNet): commercial use permitted | CA$0 API; 0.08 CPU-s | CA$0 model spend. RAM 120 MB if kept resident ≈ US$1.2/mo of Railway memory, about CA$0 if loaded per job (counts against the CA$20 infrastructure ceiling, not the model ceiling) | **Recommended** |
| (a′) InsightFace ArcFace (buffalo_l / antelopev2) | Model weights are **non-commercial research only** ([InsightFace](https://raw.githubusercontent.com/deepinsight/insightface/HEAD/README.md), [package docs](https://pypi.org/project/insightface/0.7.2/)); commercial use needs a paid licence from InsightFace | CA$0 + licence fee (unquoted) | n/a | **Rejected (licence)** |
| (b) Hosted: AWS Rekognition `CompareFaces` | AWS account (billing + identity verification); Laura's images leave our systems | about US$0.001 per image, Group 1, first 1M images a month ([AWS pricing](https://aws.amazon.com/rekognition/pricing/), [2021 price notice](https://aws.amazon.com/about-aws/whats-new/2021/11/amazon-rekognition-pricing-apis); the lower-tier figure is from a third-party listing, [stork.ai](https://stork.ai/en/amazon-rekognition)), × 3 references = US$0.003 ≈ CA$0.0042 | about CA$2.2/mo (free tier: 1,000 images/mo for 12 months) | Viable fallback. It still needs our own impostor calibration and adds a vendor, KYC and data egress |
| (c) Vision-LLM as the identity method | existing gateway | about CA$0.012 per frame (gpt-4.1) | about CA$6.3/mo | **Rejected as the biometric floor**: non-deterministic, uncalibrated, and providers discourage face matching. **Used as the second judge** (below) |

SFace caveat: the published weights are Apache-2.0, but the paper trained them on public
face-recognition datasets whose own terms are research-oriented. The legal risk is low but not zero,
and it is the same caveat as every open face model. Accepting it is part of Decision 1.

## Decisions for the owner

### Decision 1: choose the identity method
- **Action:** approve option (a), SFace + YuNet on the worker, with the Apache-2.0/MIT licences and
  the training-data caveat above. Alternative: (b) AWS Rekognition (then Decision 1b: create an AWS
  account and key).
- **Why:** an owner decision admits a biometric method for production
  (`identity_gate.validate_qualification` requires a production-scoped owner decision). This is a
  certification-authority exception under D-OWNER-STANDING-INTERNAL.
- **Max cost:** CA$0 for (a). About CA$2.2/month for (b).
- **Minutes:** 2.
- **If you wait:** identity stays HOLD. Every Laura frame goes to review and no Laura gallery can
  auto-certify.

### Decision 2: confirm 18 or more additional genuine Laura frames
- **Action:** look at one contact sheet of 24 frames generated on her three references and mark each
  "Laura" or "not Laura".
- **Why:** production needs at least 30 independent genuine samples. We have 12. A genuine label
  must come from a human; the system cannot label its own output as Laura, which would be circular.
- **Max cost:** CA$0 for the review. Generating the frames is about US$1.15 (24 × US$0.048) under
  standing authority.
- **Minutes:** 10.
- **If you wait:** calibration cannot reach production-ready.

### Decision 3: second judge (OpenAI)
- **Action:**
  1. Confirm `OPENAI_API_KEY` is set on the Railway worker. If it is not, add it.
  2. Activate `openai-vision` in the paid-provider gate.
- **Why:** PASS needs two independent judges that agree, and the second judge must be a different
  provider.
- **Max cost:** about CA$0.012 per frame actual (CA$0.024 reserved), about **CA$6.3/month** at 525
  frame checks.
- **Minutes:** 5.
- **If you wait:** identity HOLDs with "1 independent judge reading(s); two must agree".

### Decision 4: admit the qualification record (later, once calibration is production-ready)
- **Action:** approve the record that `identity_calibration.qualification(evidence, owner_decision=…)`
  builds. It is then added to `identity_gate.PRODUCTION_QUALIFICATIONS`.
- **Why:** a production record must be on the register, must carry the owner's decision, and must
  cite production-ready evidence. Code refuses anything less, even when it is on the register.
- **Max cost:** CA$0.
- **Minutes:** 2.
- **If you wait:** identity HOLDs.

### No decision needed (FYI)
- **Impostor negatives.**
  - About 34 FLUX 3 contact sheets give about 306 non-Laura faces, including deliberate look-alikes.
    That is a one-time **US$1.63 ≈ CA$2.31**.
  - This is routine image generation under D-OWNER-STANDING-INTERNAL, through the gateway
    reservation path (`w6/identity_calibration/generate_negatives.py`).
  - **Not run yet:** this build session's BFL key was not available. Nothing was generated and
    nothing was spent.
- **Deploying the method.**
  - Add `onnxruntime` to the lock.
  - Run `scripts/fetch_face_models.py` in the image build (~39 MB of models, ~23 MB wheel).
  - This is engineering work at no cost, done once Decision 1 picks (a).

## Monthly cost at about 50 galleries × 7 images (350 frames; 525 checks with 50% retries)

| item | per frame | per month | new from this work? |
|---|---|---|---|
| SFace biometric floor | CA$0 | CA$0 (+ about CA$0–1.7 of Railway RAM, infrastructure ceiling) | yes |
| Second judge (OpenAI gpt-4.1, identity reading) | about CA$0.012 | about CA$6.3 | yes |
| Outfit reference check (first judge, 2 images; only once an outfit has an approved reference) | about CA$0.015 | about CA$7.9 | yes |
| First judge identity reading (Anthropic, already in the pipeline) | about CA$0.030 | about CA$15.8 | no |
| Calibration negatives | one-time | CA$2.31 once | yes |
| *If option (b) instead of (a)* | CA$0.0042 | CA$2.2 | |

**Impact on the CA$100/month ceiling:**
- New recurring spend from this work is about **CA$14.2/month (14%)**.
- All identity-related vision spend together is about **CA$30/month (30%)**.
- Every call is reserved before it is sent, so the ceiling is enforced in code and cannot be
  exceeded. If it is reached, identity reads UNKNOWN and holds; it never passes.

Assumptions:
- The prices are the code's pinned list prices (`gateway.openai_chat.PRICES_USD_PER_MTOK`, Anthropic
  provider rates) with USD→CAD 1.4154.
- Image tokens use the providers' published per-image rules: about 765 tokens per 1024px image for
  gpt-4.1, about 1,400 for Claude.
- None of these figures is a measurement of billing.
