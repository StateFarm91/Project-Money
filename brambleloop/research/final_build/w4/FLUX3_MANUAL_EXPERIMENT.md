# FLUX 3 manual image experiment (owner-run, 2026-10-19)

- **Status:** owner-reported. Nothing in this note was measured by Brambleloop code. No
  provider was called by any worker, no money was spent by the system, and no image from the
  experiment is in the repository or on Etsy.
- **Recorded by:** W-OWNERIMG on `claude/w4-OWNERIMG`, 2026-10-19 (UTC). Production is
  1b21e81 (SHADOW).
- **What the images are:** AI-generated images, made by hand by the owner. **They are NOT
  photographs**, and they are not evidence that any physical object exists.

## 1. Tool and measurements (owner-reported, not API pricing)

| Fact | Value | Basis |
|---|---|---|
| Surface | `dashboard.bfl.ai` (Black Forest Labs web dashboard), used by hand | owner |
| Model label | "FLUX 3 Image" | owner, as shown in the dashboard |
| Cost per image | **US$0.048** | **owner-observed** on the dashboard. This is not a published API price, and no FLUX 3 price row exists in `gateway/images.py` (its table was embedded 2026-09-20 and has no FLUX 3 entry). |
| Time per image | **37–216 s** | owner-measured, wall clock, per image |
| Number of images, total spend | not reported | UNKNOWN. Not inferred. |

These figures are not used for any budget, reservation or spend plan in code. A system call
to any provider still needs a priced row with an official basis and date, a reservation
(`gateway.images.reserve_render`) and a spend plan (`visual.spend_plan`). W-FLUXAPI owns the
adapter question.

## 2. Method: staged conditioning (owner-reported)

### Stage A — Laura identity

- **Conditioning:** the three canonical references of `laura-r2-a42aeac7`
  (`visual.canonical.CURRENT_REFERENCE_HASHES`):
  - neutral portrait `a42aeac7…`;
  - torso `afe6191f…`;
  - full length `f32bac68…`.
- **Correction:** a proportion correction followed.
- **Outcome:** the owner approved the result.
- **The canonical files stay authoritative.** The Stage A output is not a new reference, not
  a revision of Laura's identity, and not a canonical asset. Only an owner decision recorded
  as a revision (D-FB-14 precedent) can change her references.

### Stage B — Cloudline flat-lay visualization

- **Product:** `cloudline-baby-blanket` v1.2.0, release `7c63dbdd501f`.
- **Conditioning:** three pattern-derived reference images:
  1. a 99×100 layout (99 stitches by 100 rows; the compiled pattern has 9,900 stitches);
  2. the 9-stitch motif;
  3. a construction/dimensions sheet.
- **What these references are:** informational, derived from the pattern. VISREF §1 calls
  this class "informational illustration". Conditioning a generator on them does not make
  the output a verified render of the CIR. `product_authority` keeps generated frames
  UNKNOWN, and F-852 prohibits generative product redraw.

### Stage C — lifestyle

- **Scene:** Laura on a sofa with the blanket on her lap.

### Stage D — wardrobe edit

- **Edit:** Laura's outfit changed to a sage-green cardigan.
- **Rule that applies:** D-W4-LAURA-OUTFIT. The cardigan becomes the outfit for exactly one
  listing (Cloudline). Its id must be registered before any image of it can pass.

## 3. What the owner approved, and what is unverified

| Question | State |
|---|---|
| The owner likes the look | **APPROVED (owner, visual)**. This is recorded as owner visual approval and is kept separate from technical verification. |
| The blanket in the image is the Cloudline pattern (stitch, motif, 99×100 layout, border, colours, size) | **UNVERIFIED** (UNKNOWN). No deterministic check has compared these pixels to the CIR. A generator can "correct" a motif. |
| The woman is Laura (identity gate) | **UNKNOWN**. No conditioning receipt proves which bytes the dashboard sent. No two-judge reading or qualified biometric floor exists. |
| Photorealism and anatomy (hands, fingers, drape) | **UNKNOWN**. The vision judge is unfunded. |
| Image size ≥2000 px, no transparency | **UNKNOWN** until the original bytes are submitted. |
| The image is a photograph of a real sample | **NO.** It is AI-generated. It can never satisfy a check that requires a photograph of a real sample (PROOF, FIT, physical proof). |
| Publication | **Blocked today.** See `OWNERIMG.md` §6 for each gate. |

## 4. How these images enter the system

They come in through the owner-assisted intake (`publish/owner_images.py`, Command Center
"Images" tab, or the CLI). It works as follows:

- The intake stores the original bytes unchanged, by sha256.
- It binds them to the certified release and its certified PDF hash.
- It labels them `ai_generated_owner_submitted` (never a photograph).
- It runs every existing check. `OWNERIMG.md` describes the workflow.
