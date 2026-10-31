# Small bread basket: physical tester kit for owner approval

**Product:** `market-basket-small@1.2.0`, the Crochet Hexagonal Bread Basket.
- Positioning: a kitchen and home product.
- Size: small only. This kit covers that one size and no other.

**Status: prepared, nothing sent.**
- No tester has been commissioned or contacted.
- Nothing has been bought and no money has been spent.
- This document asks for an approval. It does not record one.

**How it was built:** by `quality.tester_kit.build(key="basket_small")` on branch
`claude/w4-PHYSFIX`. Each kit was built twice and both builds gave identical bytes. To reproduce
it, run `cd brambleloop && nice -n 19 python3 research/final_build/w4/tester_kit_coaster.py`
(add `--check` to compare without writing).

**Labels used below:**
- **COMPUTED**: produced by the repo's code.
- **ESTIMATED**: no measured source; no tester has ever been paid.

---

## ⚠ Before you approve: the test PDF still carries children's (nursery) safety notes

The kit's test PDF is the customer PDF of this release, rendered by `publish.pdf`. Pages 7–8
print a block titled "Safety notes for a children's item". It says, among other things, "intended
for children under 3 years" and "Keep this out of the cot … in a nursery".

**Where it comes from:** the catalogue (`products.launch0.childrens_assignment`), which still
files the small basket under the `nursery-nesting-baskets` listing.

**Why the PDF is not edited by hand:** the PDF is never patched, because patterns are software
releases.

**What fixes it:** the LISTING1 source correction (kitchen and home positioning) will remove the
block. The kit will then be rebuilt by the same builder.
- **The kit's own text has no nursery or baby wording:** the record sheet, the manifest and these
  instructions. A test checks this.
- **The content hash may not change.** It covers the pattern CIR and the written pattern text,
  not the PDF's safety block. If it does change, the kit is rebound to the new hash and the
  digests below are replaced.

**Do not send the kit to a tester until the rebuilt test PDF no longer contains this block.**

---

## 1. Identity and digests (COMPUTED)

| Item | Value |
|---|---|
| Release | `market-basket-small@1.2.0`, one piece (`basket` × 1) |
| Content hash (evidence binds to this) | `1ddde587f537388b4a9dd5a74e9a0e0ebadc6ce0c0a79372dd6b867a230b3991` |
| Test PDF `market-basket-small-1.2.0-TEST.pdf` (9 pages) | `a724cbae5d58ff469a991668d257f54dce57c7e0d0437bcb323ecca2bfb72b0c` |
| Record sheet `market-basket-small-1.2.0-RECORD-SHEET.pdf` (2 pages) | `ed68e9409f0d9aa9332c48f9784a9280c173925f8b555cd3ade2e48053023e42` |
| Manifest `KIT_MANIFEST.json` | `9e192bfdc95f125b4fd0373ea0bcc1e5c6e085711997dddbe1fed8a196ba2cbb` |
| Risk class | B (`dimensional_form`); the first-customer gate needs `partial_physical` of this content, and a full make satisfies it |

Copies for review are in the scratchpad's `customer_pdfs/tester_kit/` folder.

## 2. Exact materials (yardage COMPUTED; prices ESTIMATED Canadian retail)

| Item | Quantity | Est. CA$ |
|---|---|---|
| Worsted-weight 100% cotton yarn, colour A (cream) | 1 ball. The twin needs **40.2 m**; any ball of 50 m or more will do | 5.00 |
| Worsted-weight 100% cotton yarn, colour B (wine) | 1 ball. The twin needs **11.9 m** | 5.00 |
| 5.0 mm crochet hook | 1 | 6.00 |
| Tapestry needle, 4 stitch markers, scissors | 1 set | 4.00 |
| Kitchen scale reading to 1 g | the tester's own | 0.00 |
| Tape measure or ruler (cm) | the tester's own | 0.00 |

- **Total yarn:** 52.1 m ± 20%, from the twin's yardage tolerance.
- **Gauge:** 12.5 sts × 13.8 rows = 10 cm in sc, with a 5.0 mm hook.
- **Fibre:** cotton is taken from the yarn name. The CIR's `fibre_content` field is empty.

## 3. Cost (ESTIMATED: these are ceilings, not spend)

**The code ceiling, CA$59.65**, from `gates.risk_matrix.owner_action_spec`. The kit builder
recomputes this figure and refuses to build if it disagrees:

```
tester time  2.15 h (launch0.make_hours) x 1.3 = 2.795 h x CA$20/h  = CA$55.90
yarn         52.1 m (twin) x 1.2       = 62.52 m x CA$0.06/m        = CA$ 3.75
ceiling                                                             = CA$59.65
```

**The whole-ball figure.** Yarn is bought by the ball, not by the metre:

```
tester fee                                CA$55.90
2 balls x CA$5.00                         CA$10.00
fee + whole balls (tester owns tools)     CA$65.90   (CA$6.25 over the CA$59.65 ceiling)
fee + every listed material (CA$20.00)    CA$75.90   (tester owns no tools)
```

**Recommendation:** approve a ceiling of **CA$66.00**, which covers the fee plus two whole balls,
with the tester using their own tools.

**The alternative:** keep CA$59.65 and reimburse yarn per metre. The call to testers must then
say so.

## 4. Measurements and tolerances (twin COMPUTED; tolerance `quality.physical.SIZE_DISAGREEMENT` = 12%)

| Measurement | Twin | Pass band | Checked by code |
|---|---|---|---|
| Base across the points | 16.0 cm | 14.08–17.92 cm | yes (`measured_width_cm`) |
| Wall height | 8.7 cm | 7.66–9.74 cm | yes (`measured_height_cm`) |
| Base across the flats | 13.9 cm | 12.23–15.57 cm | yes (`measured_flats_cm`) |
| Circumference (optional) | 48.0 cm | 42.24–53.76 cm | yes, if given |
| Yarn used ÷ 52.1 m | 1.0 | plausible 0.4–2.5; stated claim ±20% (41.7–62.5 m) | factor bounds |

Two observations are required, and each is answered yes or no:
- **Does the base sit flat?** It must not rock.
- **Does the basket hold its shape?** The walls stand upright, with no collapse, lean or flare.

## 5. Photographic evidence

The shot list follows Etsy's image rules as read in `ETSY_IMAGE_COMPLIANCE.md` §5.1 (branch
`claude/w4-IMAGEPOLICY`). Etsy requires at least one **unedited** photo of something actually
made from the pattern, against a real background. The first image should be the most realistic
one.

**Rules for every shot:**
- daylight, on a real surface such as wood, linen or a countertop;
- every camera file kept **unedited**: no filter, crop, resize or retouch;
- landscape or square, at least 2000 px on each side;
- the whole basket in frame, with margin for Etsy's thumbnail crop.

| # | Shot | Use |
|---|---|---|
| **1 (first image)** | Three-quarter view from about 30° above. The basket is empty, or holds two or three rolls below the rim. | Listing hero; this is the required unedited photo |
| 2 | Straight down from above | Shows the hexagonal base and the six increase lines |
| 3 | Side view at table level | Shows wall height, and that the walls stand straight |
| 4 | Tape measure across the points (≈16 cm), then a tape at wall height (≈9 cm) | Honest scale |
| 5 | Close-up of the rim and the colour change | Stitch texture |
| 6 | In use on a set table with bread | Lifestyle |

**Intake:** each photo is entered through `POST /api/physical-photo` with its sha256 and
`rights_basis: tester_agreement`. A photo without a rights basis is held and never used.

## 6. Tester instructions

These are printed on the record sheet. No step is cut off.

1. Before starting, weigh each full ball and record the ball band (grams and metres).
2. Work a 10 × 10 cm sc swatch first. Record stitches and rounds per 10 cm, and the hook. Then
   **re-weigh each ball and use that as its start weight**, so the swatch's yarn is not counted as
   project yarn.
3. Make the basket exactly as written in the test PDF. Note every place you had to guess, re-read
   or rip back, with the round number.
4. Weigh what is left of each ball. Grams used = re-weighed start minus end, per colour.
5. Measure the finished base across the points and across the flats, and the wall height, in cm,
   without stretching.
6. Set the empty basket on a flat table. Does the base sit flat without rocking? Does it hold its
   shape (walls upright, with no collapse, lean or flare)? Answer yes or no to each, and write any
   problem in the problems box.
7. Record the total hours (not counting the swatch), and whether you followed the instructions
   exactly.
8. Photograph in daylight on a real surface, keeping every camera file unedited (see §5).
9. Take shots 1–6 from §5.
10. Return the record sheet and the original photo files.

**The record sheet asks for:**
- your tester reference;
- baskets made (of 1);
- grams of cream and of wine;
- the ball band (grams and metres);
- the hook;
- swatch stitches and swatch rounds per 10 cm;
- the base across the points and across the flats, and the wall height;
- base sits flat (yes/no) and holds its shape (yes/no);
- total hours;
- whether you followed the pattern exactly;
- anything unclear or wrong, by round number.

The sheet states that it covers exactly one size, small. It also says that no review, rating or
favourite is requested, and that the fee does not depend on the tester's opinion.

**The person:** one independent adult crocheter, who is not the owner (F-071). They should be
confident with sc in joined rounds, six-point increases and turning a base into walls. They
should read US terms and have a 1 g scale. Time: 2–3 hours, plus about 15 minutes.

**Operator entry:** `tester_kit.intake_payload(sheet, content_hash=…, key="basket_small")`
produces the exact `POST /api/physical-test` payload. That payload carries `scope: full_make`,
`made: {"basket": 1}`, `size: small` and the content hash.

## 7. Turnaround (ESTIMATED; the repo holds no recruitment data)

| Step | Time |
|---|---|
| Your decision | about 25 minutes |
| Post the call and recruit an applicant | 2–7 days |
| Tester window | up to 14 days; the make itself is about 2.15 h (COMPUTED) |
| Operator intake | same day |
| **Total** | **about 1–3 weeks** from your approval |

## 8. Outcomes and the failure path

The code reaches each outcome; nobody assigns it by hand.

- **PASS:**
  - Conditions: the size is within 12%; the base sits flat and the basket holds its shape; no
    problem is recorded; the instructions were followed; the yarn factor is plausible.
  - The sample binds to content `1ddde587…`.
  - It clears the first-customer `gauge_and_size_claims` area **for the small size only**. The
    evidence says so: "proven: small; not proven: medium, large".
  - Only a made basket whose measured size agreed counts. A gauge swatch alone never proves the
    size and never clears this area.
  - If the factor is not 1.0, it calibrates `worsted cotton:sc` yardage.
- **PARTIAL:** the base rocks, the basket does not hold its shape, or the tester wrote a
  problem or any other note.
  - The sample is stored, binds nothing and calibrates nothing.
  - It comes to you as an owner action that names the problem.
  - Software never turns a PARTIAL into a pass. You decide between a pattern fix and a repeat
    sample.
- **FAIL:** an implausible yarn factor, an unknown colour, the instructions not followed, or a
  size outside 12%. The sample binds nothing.
- **Refused at intake (re-enter from the sheet):** "followed exactly?" left blank or not a plain
  yes or no, a missing shape answer, or a missing measurement.
  - **A size outside 12% halts publication of this release.** The halt is a P1 incident scoped
    to `market-basket-small@1.2.0` at this content hash.
  - The halt is bound to the design, not the version number, so relabelling the same pattern
    as a new version stays halted.
  - A corrected design can be certified, but certification lifts nothing. The halt lifts only
    when a passed full make of the corrected design measures the stated size.
- **Fix path:**
  1. Correct the generator (`products.vessels.build_basket`), or the renderer if the text was
     unclear. The PDF is never patched.
  2. Bump the version, which changes the content hash.
  3. Re-certify.
  4. Rebuild this kit with the same builder.
  5. Run a new test against the new hash. That needs a second approval and a second ceiling.
- **Tester deviation:** re-test the same version, with no new release.
- **Implausible factor:** first check the ball band and the grams for a transcription error.

## 9. OWNER ACTION REQUIRED (for your batch; not yet asked)

| Action | Why | Max cost | Minutes | Consequence of waiting |
|---|---|---|---|---|
| Approve commissioning one independent tester to make `market-basket-small@1.2.0` from this kit. The ceiling is CA$66.00 (fee plus whole balls), or CA$59.65 with yarn reimbursed per metre. Approve only after the rebuilt test PDF no longer carries the children's notes. | Etsy requires an unedited photo of a made sample for a pattern listing, and the first-customer gate needs `partial_physical` evidence of this exact content | CA$66.00 (ESTIMATED) | 25 | The basket cannot be listed compliantly, and its size and yardage claims stay estimates |
