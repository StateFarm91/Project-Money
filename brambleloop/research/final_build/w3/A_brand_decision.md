# Brambleloop identity: decision record (wave 3, lane A)

Date: 2026-10-06 (UTC). Status: **RECOMMENDED, PENDING OWNER APPROVAL**. Nothing has been
uploaded to Etsy, and the independent certifier (lane J) has not reviewed it yet.

Interface: `brambleloop.brand.identity_system` (direction `D1-briar-monogram`).
Evidence: `evidence/A_1..A_5_*.png` and `evidence/A_judge_verdict.json`. Rebuild the evidence with
`PYTHONPATH=src python research/final_build/w3/A_build_sheets.py`.

## What was built

Four directions. Each is a full small system: icon, emblem, wordmark, horizontal and stacked
lockups, a repeating motif, a named palette with colour, mono and reversed variants,
typography and usage rules. All of it is deterministic SVG made from geometry plus glyph outlines
taken from SIL OFL fonts. Nothing uses an image model, no money was spent, no font comes from a
CDN, and no SVG contains `<text>`.

| id | concept | wordmark type | palette |
|---|---|---|---|
| D1 briar-monogram | Built from the owner's concept. A serif B with a blossoming bramble sprig and a yarn figure-of-eight that ends in a ball. The icon is a simplified cut: the B held in a loop of yarn drawn from a small ball, with a leaf pair. | Libre Baskerville, spaced caps. CROCHET PATTERNS in Work Sans between hairlines. Lora Italic tagline. | forest, sage, cream paper, dusty rose, berry |
| D2 chain-link | Two loops interlocked like a crochet chain stitch, drawn over and under | Outfit, lower case | charcoal, oat, clay |
| D3 drupelet | A blackberry made of bobble-stitch drupelets, with a stem that curls into a loop | Young Serif, lower case | bramble wine, moss, cream |
| D4 tapestry-b | A B worked as a tapestry-crochet chart of V stitches | Arsenal SC | indigo, linen, saffron |

## How it was judged

**Measured** (`brand.judge`). These checks run on rasters of the geometry that ships, at the
real sizes:

- WCAG contrast
- ink coverage at 40 px
- crispness at 40 px (the share of ink pixels that land on a real palette colour rather than mush)
- **stroke survival at 40 px** (render at 160 px, erode by 0.5 px-at-40 on each side, keep the share that survives)
- thinnest stroke in px at 40
- **silhouette distinctness** (IoU at 40 px against the other directions and against five generic references: yarn ball, plain serif B, hook, flower sprig, circle badge)
- monochrome edge correlation
- circular-crop safety
- phone-header letter height (horizontal lockup fitted into 280×40 px)

**Judged** (labelled opinion: the builder's rubric, with a reason written for every score). The
criteria are premium, ownable, story, coherence, owner taste and fit with Laura. The weighting is
50/50 between measured and judged.

| direction | measured | judged | total | contrast | stroke survival@40 | thinnest stroke px@40 | header letter px | distinctness | worst generic IoU |
|---|---|---|---|---|---|---|---|---|---|
| **D1** | 92.9 | 96.7 | **94.8** | 9.97 | 0.654 | 2.0 | 16.5 | 0.517 | plain serif B 0.483 |
| D2 | 93.3 | 53.3 | 73.3 | 11.95 | 0.692 | 2.72 | 8.9 | 0.646 | yarn ball 0.354 |
| D3 | 76.6 | 70.0 | 73.3 | 5.65 | 0.659 | 1.28 | 8.2 | 0.431 | yarn ball 0.569 |
| D4 | 78.4 | 63.3 | 70.9 | 11.06 | **0.23** | n/a | 9.1 | 0.505 | plain serif B 0.495 |

**Sensitivity.** On the measured score alone, D1 and D2 tie (92.9 against 93.3). D1 wins on the
judged rubric: it is premium, it tells the name, it is coherent, and it matches the owner's taste.
If the owner-taste criterion is removed, D1's judged score is 96 and it still wins. The choice
therefore rests on judgement that the owner and lane J must confirm. The measurements only show
that D1 is not weaker at tiny sizes.

## Why D1 won, and the honest weaknesses

- It draws the name: bramble (leaf, blossom, berry), loop (yarn) and B. It is the owner's
  preferred direction, rebuilt as clean, original vector geometry. The owner's raster is neither
  embedded nor traced, and the props with slogans in the concept are excluded.
- The 40 px problem is solved by a separate icon. The detailed emblem cannot survive at 40 px, so
  the icon keeps only the B, one loop, the ball and a leaf pair. Every overlap uses a real mask
  knockout, so the one-colour version holds.
- **Weakness:** at 40 px the icon's silhouette is 0.483 IoU against a plain serif B. Most of its
  recognition comes from the letterform. The loop and ball are what make it Brambleloop's, but a
  serif monogram with botanicals is a popular Etsy aesthetic, so quality of execution is what sets
  it apart.
- **Weakness:** the owner's concept uses a script tagline. No open-licence formal script is
  available offline, and a script fails below about 14 px on a phone, so the tagline uses Lora
  Italic. If the owner wants a script, a licensed or OFL script can be outlined in later
  (`fontbuild`).
- Rose (#A86B5C) on forest measured only 2.65:1. The reversed variant therefore uses rose_light
  (#D49A8A, 4.73:1). A test found this.

## Icon iterations (evidence/A_5)

1. v1: a curl of yarn out of the bowl, ending in a ball. Rejected because it reads as "B?" at 40 px.
2. v2: a loop with a tail dropping to a ball. Rejected because it reads as "B!", and the oversized B
   swallowed the loop in one colour.
3. v3 (shipped): a closed loop drawn from a ball. The B is interlaced with knockouts and the leaf
   pair rides the loop. It reads as a monogram seal and fits a circular crop (0.2% ink outside).

## Runners-up (kept in `identity_system.alternatives()`)

- D2: interlocked ovals are the universal hyperlink/chain icon. They would read as "software
  project", which is the exact criticism the owner made of v1.
- D3: at 40 px it becomes a generic raspberry or grape (0.569 IoU against a yarn ball) and drifts
  toward a jam label.
- D4: its strokes do not survive at 40 px (0.23). Its pixel-chart look risks reading as a knitting
  app, and its colour blocks would compete with Laura.

## Blind structural comparison (descriptions only; no competitor asset fetched)

See `judge.BENCHMARKS`. D1 sits structurally with heritage yarn houses (restrained serif capitals,
small stampable emblem, one ink) and with botanical stationery studios (monogram, botanical line
work, serif and italic, hairlines). The lesson taken from both: the illustration needs a simplified
small-size cut, which D1 now has. The benchmark for top Etsy pattern shops says the grid of listing
photographs builds the brand more than the logo does. The mark therefore stays quiet, and the
listing imagery (lane H) carries the desire.

## What was not verified

- No human or customer has judged these marks. The rubric is the builder's opinion. Lane J and the
  owner are the judges, and only marketplace evidence (CTR, favourites, conversion) can confirm it.
- Etsy's exact icon and banner pixel sizes and crop shapes were not verified here (lane I owns
  that). The icon is designed to survive both square and circular crops.
- No trademark clearance search has been done for the mark or the name.
