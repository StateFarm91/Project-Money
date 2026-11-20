# Laura identity verification: owner decisions (ENG-VIS-IDENTITY, 2026-11-20; slice 2 update)

**Status today:** Laura's identity still **cannot PASS** in production, and that is the correct
state. The verification method is built, measured and wired. The things it still needs are listed
below, and every one is either the owner's call or blocked on a key this build session did not have.

Identity: `laura-r2-a42aeac7`. Her three canonical references were read and verified by SHA-256.
They were never modified.

## What exists now (verified in this branch)

- **Biometric method, option (a).** YuNet face detector plus SFace face embedder: two ONNX models
  run on CPU with `onnxruntime` and numpy (`visual/face_embedder.py`).
  - Weights are pinned by SHA-256. Unpinned bytes are refused.
- **Calibration harness** (`visual/identity_calibration.py`, `identity-calibration/2`).
  - **Held-out split (slice 2).** The samples are split deterministically into a calibration
    subset (1/6 of genuine, 1/3 of impostors) and a disjoint held-out subset. Thresholds are
    fixed on the calibration subset only. FAR and FRR, with exact 95% bounds, are measured on the
    held-out subset only. Slice 1 measured FAR on the same impostors that set `match_at`, so its
    "0 false accepts" was 0 by construction.
  - Production floors apply to the **held-out** part: at least 30 genuine samples, at least 300
    impostor faces, FAR upper bound of 1% or less, FRR of 10% or less.
  - `qualification()` re-derives the split, thresholds and rates from the rows and refuses
    in-sample evidence (`InSampleEvidence`). The gate also refuses a record that does not
    declare a held-out evaluation.
  - A reference SHA mismatch refuses the whole run.
- **Measured on the licence-safe set available today** (`w6/identity_calibration/calibration_evidence.json`,
  evidence sha `1854ae98…`, held-out):

  | | value |
  |---|---|
  | genuine samples (Laura, owner-viewed frames generated on her face a42aeac7) | 12: 2 calibration, **10 held out** (+50 held-out augmentations, not counted) |
  | impostor faces (owner concept look-alikes + one unrelated generated woman) | 10: 4 calibration, **6 held out** |
  | highest calibration impostor / lowest calibration genuine | 0.433 / 0.696 |
  | derived thresholds | `match_at` 0.49, `refuse_below` 0.44 |
  | **held-out FAR** | **2 / 6** (two owner-concept look-alikes score 0.50 and 0.58) |
  | held-out FAR 95% upper bound | **72.9%**, so **not production-ready** |
  | held-out FRR | 0 / 10 (upper bound 25.9%; augmented 0 / 50) |
  | CPU cost | about 0.065 CPU-s per frame (1 thread); model load 0.2 s |
  | RAM | **about 110 MB** on top of the worker while loaded (CPU memory arena off; 121 MB peak for a bare Python process in the built image) |

  This is the honest reading. On a split this small, the four calibration look-alikes happen to
  score lower than two held-out ones, so the derived `match_at` lets those two through. Only the
  full impostor set (below) can show whether SFace separates her from look-alikes at a 1% bound.
  The slice-1 figure (FAR 0/10, upper bound 25.9%) was in-sample and is withdrawn.

  The owner's manual FLUX 3 attempts at Laura score 0.68–0.79. That is information only: they
  are unlabelled and never used as calibration labels.
- **Second independent judge.** OpenAI `gpt-4.1-2025-04-14`, a different provider from the
  Anthropic first judge.
  - It uses the same `GatewayVisionJudge` reservation path: the CA$100 ceiling and one ledger row.
  - **Reservation (slice 2, F4).** Each read is reserved at gpt-4.1's own per-image figure (1,600
    tokens; its worst case is 1,445) for the real 4 images, plus the system and prompt text. That
    is exactly the estimate the OpenAI paid gate checks, so a read is never under-reserved. It
    is about **CA$0.029 reserved per read**. Before slice 2 every vendor was reserved at
    Anthropic's 6,000-token image figure, about **CA$0.092 per read** (about 4×).
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
| **(a) SFace + YuNet ONNX on the Railway worker** | Apache-2.0 (SFace, OpenCV zoo) + MIT (YuNet): commercial use permitted | CA$0 API; 0.08 CPU-s | CA$0 model spend. RAM about 110 MB if kept resident ≈ US$1.2/mo of Railway memory, about CA$0 if loaded per job (counts against the CA$20 infrastructure ceiling, not the model ceiling) | **Recommended** |
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
- **Note (slice 2):** on today's tiny held-out set, SFace let 2 of 6 look-alikes through. That is
  not yet evidence for or against the method; the 450-face impostor set decides it. Approving
  (a) now lets that measurement run. Nothing PASSes until Decision 4.
- **Why:** an owner decision admits a biometric method for production
  (`identity_gate.validate_qualification` requires a production-scoped owner decision). This is a
  certification-authority exception under D-OWNER-STANDING-INTERNAL.
- **Max cost:** CA$0 for (a). About CA$2.2/month for (b).
- **Minutes:** 2.
- **If you wait:** identity stays HOLD. Every Laura frame goes to review and no Laura gallery can
  auto-certify.

### Decision 2: label one contact sheet of 24 Laura frames
- **Action:**
  1. On the worker: `python3 scripts/identity_contact_sheet.py generate --db $DATABASE_URL`, then
     `... sheet`.
  2. Open `contact_sheet/label.html` (or `contact_sheet.png`) and mark each of the 24 frames
     "Laura" or "not Laura". The page prints the exact `... label --by NAME --laura … --not-laura …`
     command. `... add` then appends the frames to the calibration set.
  - Every frame is conditioned on all three canonical references, verified by SHA-256.
  - Frames you mark "not Laura" are kept as impostors: look-alikes made on her own references,
    the hardest test there is.
- **Why:** production needs at least **30 held-out** genuine samples. With 1/6 of genuine
  samples spent on calibration, that needs at least **36** in total. We have 12, so **24 more
  confirmed "Laura" frames** are needed. A genuine label must come from a human; the system
  cannot label its own output as Laura, which would be circular. The code refuses a sheet with
  any frame unlabelled, labelled twice, or with no labeller named.
- **If fewer than 24 are confirmed:** a second sheet is needed (the same command; it is
  idempotent and buys only frames that are missing).
- **Max cost:** CA$0 for the review. Generating the 24 frames costs at most **US$1.152 ≈ CA$1.63**
  (24 × US$0.048, hard cap US$1.16 in code), under standing authority.
- **Precondition:** the BFL key (`BRAMBLELOOP_IMAGE_KEY_BFL`) and your `generation` activation of
  `flux-3-image`. Without both, `generate` refuses before any reservation, and nothing is spent
  (ENG-VIS-FLUX's provider path).
- **Minutes:** 10.
- **If you wait:** calibration cannot reach production-ready.

### Decision 3: second judge (OpenAI)
- **Action:**
  1. Confirm `OPENAI_API_KEY` is set on the Railway worker. If it is not, add it.
  2. Activate `openai-vision` in the paid-provider gate.
- **Why:** PASS needs two independent judges that agree, and the second judge must be a different
  provider.
- **Max cost:** about CA$0.015 per frame actual (CA$0.029 reserved), about **CA$8.0/month** at 525
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
  - Production needs at least 300 **held-out** impostor faces. With 1/3 spent on calibration,
    that is at least 450 in total: about 50 FLUX 3 contact sheets of 9 non-Laura faces,
    including deliberate look-alikes. That is a one-time **US$2.40 ≈ CA$3.40**.
  - This is routine image generation under D-OWNER-STANDING-INTERNAL, through the gateway
    reservation path (`w6/identity_calibration/generate_negatives.py`, `n_grids` 50, cap US$2.40).
  - **Not run yet:** this build session had no BFL key or activation. Nothing was generated and
    nothing was spent.
- **Deploying the method: done in slice 2.**
  - `onnxruntime==1.29.0` is in `requirements.lock`, hash-pinned. It adds `flatbuffers`,
    `packaging` and `protobuf`.
  - The Dockerfile runs `scripts/fetch_face_models.py --best-effort` after the locked install
    (~39 MB of models). The image was built and booted in this session: both models were fetched
    and SHA-verified, `/health` returned ok, and the floor loaded the embedder with no
    qualification, so identity HOLDs.
  - An unreachable mirror never breaks the deploy. The floor then reads UNMEASURED and
    identity HOLDs. A tampered model file is refused at load (verified in the built image).

## Monthly cost at about 50 galleries × 7 images (350 frames; 525 checks with 50% retries)

| item | per frame | per month | new from this work? |
|---|---|---|---|
| SFace biometric floor | CA$0 | CA$0 (+ about CA$0–1.7 of Railway RAM, infrastructure ceiling) | yes |
| Second judge (OpenAI gpt-4.1, identity reading) | about CA$0.015 (CA$0.029 reserved) | about CA$8.0 | yes |
| Outfit reference check (first judge, 2 images; only once an outfit has an approved reference) | about CA$0.015 | about CA$7.9 | yes |
| First judge identity reading (Anthropic, already in the pipeline) | about CA$0.030 | about CA$15.8 | no |
| Calibration negatives (~50 grids) | one-time | CA$3.40 once | yes |
| Decision 2 contact sheet (24 frames) | one-time | CA$1.63 once | yes |
| *If option (b) instead of (a)* | CA$0.0042 | CA$2.2 | |

**Impact on the CA$100/month ceiling:**
- New recurring spend from this work is about **CA$15.9/month (16%)**.
- All identity-related vision spend together is about **CA$32/month (32%)**.
- Every call is reserved before it is sent, so the ceiling is enforced in code and cannot be
  exceeded. If it is reached, identity reads UNKNOWN and holds; it never passes.

Assumptions:
- The prices are the code's pinned list prices (`gateway.openai_chat.PRICES_USD_PER_MTOK`, Anthropic
  provider rates) with USD→CAD 1.4154.
- Image tokens use the providers' published per-image rules: about 765 tokens per 1024px image for
  gpt-4.1 (worst case 1,445; 1,600 reserved), about 1,400 for Claude.
- None of these figures is a measurement of billing.
