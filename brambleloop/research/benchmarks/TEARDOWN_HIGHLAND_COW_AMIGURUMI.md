# Benchmark teardown: Highland Cow amigurumi (purchased 2026-11-20)

**Source.** One purchased Etsy pattern from shop CraftyWkingdom, "Highland Cow Crochet Pattern
PDF, Cow Amigurumi Pattern, Plush…". The owner bought it as a benchmark on 2026-11-20.
- Listing state at purchase: Bestseller, 4.7★ from 77 reviews, "In 20+ baskets".
- Price: CA$2.88 shown as "75% off" a CA$11.54 strike price.
- Delivery: 3 PDFs.

**Use.** STRUCTURE AND MERCHANDISING INTELLIGENCE ONLY (CLAUDE.md non-negotiable;
D-OWNER-PDF-STANDARD).
- Never copy its instructions, stitch counts, row sequences, photos, layout art, wording or
  design.
- The purchased files are NOT committed to this repository: they are licensed for personal
  use, with no redistribution. Main holds them outside git.
- This file records structure, defect classes and lessons only.

**Family.** Amigurumi / stuffed animal: a core family (D-OWNER-CORE-FAMILIES), and the
MadelineMaeCo-style demand the owner named.

---

## 1. What the buyer actually receives

| File | Pages | What it is |
|---|---|---|
| "HighlandCowCrochetPattern.pdf" | 1 | **A link page, not the pattern.** It has a shop logo, a "PRODUCT LINK" button pointing to a Google Drive file, "how to use: open in Canva", and a gift-for-feedback offer. |
| (Google Drive file behind the link) | 13 | The actual pattern, made in Canva at A4 portrait, 34 MB, image-heavy. |
| "TutorialCrochet.pdf" | 47 | A generic beginner stitch guide (yarn weights table, holds, slip knot, chain, basic stitches), illustrated. It carries a bonus "personal use licence" page and another review-for-gift page. |
| "CraftyWkingdomThankYou.pdf" | 1 | A thank-you card with a review request and a free-gift offer. |

**Lesson.** The bundle *feels* big (3 files, 61 pages) while the actual pattern is about 7
content pages. Buyers value the bundle. **Brambleloop's equivalent is honest:** we can include
a genuinely original "techniques used in this pattern" appendix generated from the CIR's
stitch set, so it covers only what this pattern uses. That is not a generic padding book.

## 2. Structure of the 13-page pattern

1. **Cover:** the shop name in a frame, the product name in large serif, "Crochet Amigurumi"
   in script, a full-bleed lifestyle hero of the finished toy, and a "CROCHET PATTERN"
   ribbon. *The same image is the Etsy listing hero.*
2. **Thank-you card:** it advertises a *different* product (a cow lovey), asks for a
   5-star review, and promises a FREE GIFT. (It appears twice in the file.)
3. **Overview page, one page, beside a lifestyle photo:**
   - difficulty;
   - materials (yarn weight, colours by part, hook in mm, safety eyes, markers, needle,
     stuffing);
   - abbreviations (8);
   - special stitches ("none").
4. **Pattern pages, one section per component** (head → body → legs ×N → tail → horns ×2 →
   ears ×2 → fur):
   - round-by-round lines, each ending in a stitch count where given;
   - inline "stuff now" cues;
   - colour-change and loop instructions in plain text;
   - **one real progress photo per component**: a hand-made sample held in hand on a plain
     ground.
5. **Assembly, two pages:** one card per joining step (ears, horns, legs, tail, head-to-body,
   fur), each with a real step photo and a placement cue tied to a round number.
6. **Finishing + "Congratulations!":** finishing steps beside a photo, followed by more
   review-for-gift asks.
7. **Throughout:** encouragement banners ("You're doing great!", "Little by little…") and
   decorative botanical clip-art frames.

## 3. What it does well (what we must match or beat)

- **W1. Per-component progress photos and per-step assembly photos.** This is the single
  biggest trust signal. Buyers can check their piece against the picture, and reviews praise
  "easy to follow". For Brambleloop this is part of D-OWNER-PDF-STANDARD (progress photos).
  For a generated, non-physical pipeline, see §6, L3.
- **W2. Component-first organisation**, with a clear header and a working note per piece.
- **W3. One-page "at a glance"** (difficulty, materials, hook, abbreviations) before any
  instructions.
- **W4. Assembly placement cues tied to round numbers** ("between rounds X–Y, behind the
  eyes").
- **W5. Warm, encouraging tone, and a cohesive cosy aesthetic**: cream ground, sage
  botanicals, serif and script type. It matches the cottage-core demand of the core families.
- **W6. Merchandising.** A lifestyle hero is identical on the listing and the PDF cover.
  Badges on the listing hero ("beginner friendly", "cute, cuddly & fun", "perfect gift
  idea"). 7+ gallery images including a video. Low price point.

## 4. Defects found (classes only; our edge)

| # | Defect class | Observed | Brambleloop answer |
|---|---|---|---|
| D1 | **No finished size, no gauge** | Neither appears anywhere. A buyer cannot know how big the toy will be or check tension. | Finished size and gauge from the certified CIR geometry, mandatory (template p.03–04). |
| D2 | **Vague yarn quantities** | "Few grams" and "1 ball", with no weight or length per colour, and no length for the fur strands. | Yardage and grams per colour from the twin, plus a variance note. |
| D3 | **Stitch counts missing on some rounds** | Several multi-round lines and plain rounds carry no count. | A stitch count on EVERY row and round (deterministic compiler). |
| D4 | **Arithmetic and typo errors in instructions** | At least one round reads as a double instruction ("6 sc inc x 6") where the stated count implies "sc inc x 6". | The compiler, twin and reverse validation make this class impossible. |
| D5 | **No child-safety notes at all** | It uses plastic safety eyes (also as nostrils) and many loose cut-yarn fur strands, a known pull-out and choking hazard for under-3s. The materials list says "safety eyes for toys" with no age guidance, and gives no embroidered-eye alternative. | The child-safety gate: age guidance, embroidered features for baby or under-3, strand-anchoring guidance, and no claim of "safe". |
| D6 | **Single terminology** | US terms only, stated in a note. | US and UK editions from one certified source. |
| D7 | **Hero vs sample mismatch** | The cover and listing hero look like an idealised (likely generated) render: denser fur, different proportions and colour. The in-PDF progress photos show a different, real sample. | The pictured item must be what the pattern makes (Product Truth). Generated images are labelled as renderings. |
| D8 | **Fragile delivery** | The Etsy download is a link to Google Drive or Canva. If the link dies, the buyer has nothing. | Deliver the actual PDFs as the Etsy files, verified by read-back. |
| D9 | **Padding and repetition** | Two copies of a thank-you page for another product. A generic 47-page tutorial. | Every page earns its place. An original appendix covers only the techniques used. |

## 5. Practices we must NEVER copy (policy and integrity)

- **N1. Incentivised reviews.** "Leave a review / 5-star review and receive a FREE gift"
  appears in all three files and on two pattern pages. Offering compensation for reviews
  breaks Etsy's review rules and our non-negotiable (no fake or incentivised engagement). A
  neutral "questions? message us on Etsy" line only (template p.13).
- **N2. Perpetual "75% off" strike pricing.** CA$11.54 → CA$2.88, "sale ends in 18h". It
  reads as a deceptive reference price if it never sells at the strike price. We never use
  deceptive discounts (non-negotiable). Pricing uses honest price points only.
- **N3. Advertising other products inside a paid pattern's instruction flow.**

## 6. Lessons for each department (to be ingested by ENG-LEARN / ENG-IMPROVE)

- **L1, Research / pricing.** A bestselling amigurumi animal pattern clears at a low impulse
  price point (here CA$2.88 effective, CA$11.54 anchor) with heavy review volume. Price
  research treats the strike price as noise and the effective price as the signal. The
  listing's AI review summary highlights "clear instructions" and "easy to follow".
  **Clarity is the review driver.**
- **L2, Product and concept.** Highland cow, shaggy-fur animals and cosy farm animals are a
  proven amigurumi demand cluster. A shaggy fur effect done by **original** means is a
  differentiator; we design our own construction and never adopt theirs. Concepts are
  original and scored by the existing concept pipeline.
- **L3, PDF and visual.** Per-component progress imagery is essential (W1). Without a
  physical sample, Brambleloop uses **CIR-generated per-component diagrams**: a deterministic
  rendered silhouette of each piece at its finished dimensions, with round markers. These are
  labelled as diagrams, never as photos, so we never fake a progress photo. When a real
  sample exists, real photos replace them.
- **L4, PDF template.** Our master template (D-OWNER-PDF-TEMPLATE) already has the
  at-a-glance, materials, sizing, construction, pattern, finishing, care/safety and gallery
  pages. For amigurumi, the pattern page should group by component with a per-component
  image slot (L3), and assembly should be numbered steps with placement cues tied to
  round numbers.
- **L5, Child safety.** Every amigurumi or baby release states age guidance and offers
  embroidered features where the gate requires them. Loose fur strands need an anchoring
  method and a care/inspection note. The benchmark's absence of any of this is the clearest
  gap we fill.
- **L6, Delivery.** Etsy files are the actual PDFs, never a link page. Read-back verifies
  that each file is downloadable and matches the certified hash (already an ETSY-PUBLISH
  requirement).
- **L7, Copy and SEO.** Title pattern observed: "<Animal> Crochet Pattern PDF, <Animal>
  Amigurumi Pattern, Plush…". Front-load the animal and "crochet pattern PDF". Listing badges
  on the hero ("beginner friendly", "gift idea") are only allowed when they are TRUE for our
  certified difficulty.

## 7. Scorecard (0–5; Brambleloop target ≥ 4 on every row)

| Dimension | Benchmark | Notes |
|---|---|---|
| Visual appeal / brand cohesion | 4 | Cosy, consistent and decorative. |
| Instruction completeness | 2 | No size or gauge, vague yarn, missing counts. |
| Instruction correctness | 3 | At least one typo-class error. |
| Progress and assembly imagery | 5 | Their strongest feature. |
| Child safety | 0 | None. |
| Terminology coverage | 2 | US only. |
| Delivery robustness | 1 | Link to Drive/Canva. |
| Integrity (reviews, pricing) | 0 | Incentivised reviews, perpetual strike price. |
