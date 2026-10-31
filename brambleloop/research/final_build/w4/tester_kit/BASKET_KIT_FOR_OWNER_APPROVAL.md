# Small bread basket: physical tester kit for owner approval

> **PROVISIONAL (2026-10-31).** These 1.3.0 kits do not yet carry the record-sheet fields that W-PHYSFIX added on `claude/w4-PHYSFIX` 29378b85: wall-height method, `base_edge`, `corners_at_rim` and `rim_across_points_cm`. They also lack its one-tester terms. Once PHYSFIX lands in `claude/w4-INTEG8-next` (Batch 4), merge it and rebuild the kits with `tester_kit_coaster.py`. Do not commission a tester from these files.


**Product:** `market-basket-small@1.3.0`, the Crochet Hexagonal Bread Basket.
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

## Rebuilt 2026-10-31 for release 1.3.0 (owner decision D-W4-OWNER-BASKET-1.3.0)

The kit now binds to `market-basket-small@1.3.0`, content hash `c4aa14a0…`.
- **The design change:** Rnd 11 is "sc in back loop of next 60 sts", marked "back loop only".
  The unworked front loops make a defined edge where the base turns into the wall. This is the
  fold that the twin and the renders draw.
- **What did not change:** stitch counts (60 per wall round), the six-sided geometry, the size
  (16.0 cm across the points, 13.9 cm across the flats, 8.7 cm tall) and the yarn (40.2 m cream,
  11.9 m wine) were recomputed from the twin and are the same.
- **What the PDF no longer says:** the 1.2.1 soft-fold wording ("turning upward over the first
  few rounds", "about 8 to 9 cm") no longer applies and is gone.
- **What the renders still idealise:** one thing. They draw the corners running straight up the
  wall, and no wall round keeps the corners.

**The CA$66 ceiling is provisional** until the final kit, carrying the W-PHYSFIX fields, is
approved. A 1.2.x sample would not count as evidence for 1.3.0, because the content hash is
different.

---

## Rebuilt 2026-10-31 for release 1.2.1 (text only; superseded by 1.3.0 above)

The kit now binds to `market-basket-small@1.2.1`, content hash `9251c2ec…`. Release 1.2.1 changes
only the written text, from the independent PDF audit:
- the colour-change and ends wording: cut wine after Rnd 19; carry cream up the inside of the join;
- "the ch 1 does not count as a stitch".

The test PDF was rebuilt again the same day, after the independent construction review. The
content hash is unchanged. The changes:
- the wall is described as turning upward over the first few rounds, not "rising straight up";
- the Rnd 11 checkpoint reads "the edge of the base beginning to turn up";
- the height is given as "about 8 to 9 cm", because 8.7 cm is an upper bound;
- every render is captioned as idealised.

The review's suggested record-sheet fields (base edge, wall-height method, corners at the rim)
are backlog. The record sheet is unchanged.

Stitches, counts, geometry, yarn amounts and the CA$66 ceiling are unchanged. The test PDF is the
premium customer edition at 13 pages. A 1.2.0 sample would not count as evidence for 1.2.1,
because physical evidence binds to the exact content hash, so this kit replaces the 1.2.0 one.

---

## Resolved 2026-10-31: the nursery safety block is gone

The kit was rebuilt by the same builder after the LISTING1 source correction (kitchen and home, small size only) was integrated.

- The test PDF is now 7 pages, down from 9.
- Text extraction finds "nursery", "baby", "child", "CPSIA", "nesting", "three sizes" and "under 3" zero times each.
- At 1.2.0 the content hash was unchanged (`1ddde587…`). The 1.2.1 rebuild above has a new one.
- The PDF was never edited by hand.

---

## 1. Identity and digests (COMPUTED)

| Item | Value |
|---|---|
| Release | `market-basket-small@1.3.0`, one piece (`basket` × 1) |
| Content hash (evidence binds to this) | `c4aa14a000e5439b0dfb32812039178b5efed6b4ba840efef7e7c64a6b7c659c` |
| Test PDF `market-basket-small-1.3.0-TEST.pdf` (13 pages) | `edc25c5ab960628bd3a0ef29b5f8bbf1e1dffdc12469367c40aaa8265dd0c106` |
| Record sheet `market-basket-small-1.3.0-RECORD-SHEET.pdf` (2 pages) | `f8072169eb2dfd2b66b3b2d3002c8288451bdb902d627415b9c1fd3be03b9f29` |
| Manifest `KIT_MANIFEST.json` | `be9dcc3e4f040777f5bf5bd053a5e0472f7b43d228c98aa952d1b38929d8c48e` |
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
  - The sample binds to content `c4aa14a0…`.
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
    to `market-basket-small@1.3.0` at this content hash.
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
| Approve commissioning one independent tester to make `market-basket-small@1.3.0` from this kit, once it is final (not provisional). The ceiling is CA$66.00, provisional until the final kit is approved, (fee plus whole balls), or CA$59.65 with yarn reimbursed per metre. That condition (a test PDF with no children's notes) was met on 2026-10-31. | Etsy requires an unedited photo of a made sample for a pattern listing, and the first-customer gate needs `partial_physical` evidence of this exact content | CA$66.00 (ESTIMATED) | 25 | The basket cannot be listed compliantly, and its size and yardage claims stay estimates |
