# Children's category: market, safety and taxonomy research

_Researched 2026-09-24 by the SEO / Marketplace Research department, in shadow mode, in an
isolated worktree. No Etsy API call was made, no account was touched, nothing was published._

Every claim below carries a label:

| label | meaning |
|---|---|
| **SOURCED** | a URL was fetched or searched in this session and is quoted |
| **DERIVED** | arithmetic or inference performed here on a sourced number, shown |
| **ESTIMATED** | a judgement with no measurement behind it, said so |
| **UNKNOWN** | genuinely not established. Not filled in with a plausible number |

The repository's standing rule applies: an honest "not found" beats a confident guess, and
nothing here claims a listing, a customer or a revenue figure exists.

---

## 0. The one-paragraph version

Children's is not a category in the sense the existing pod taxonomy uses the word. It is an
**audience that cuts across the forms we already build** — a baby blanket is a blanket, a lovey
is amigurumi, a child's cardigan is a garment — and what makes it a distinct business decision
is not merchandising but **obligation**: the audience, not the form, is what attaches safety
constraints, platform prohibitions and statement requirements to the product. The commercial
case is good (the highest-velocity pattern listings visible to us are children's toys, and baby
demand is the flattest across the year of anything we have measured). The cost of entry is that
a children's pattern has to be *written differently*, and a few children's products we must
never publish instructions for at all. That last part is the finding that changes what we can
offer, and it is the part this research was most careful about.

---

## 1. Sub-categories, and which of them suit a PATTERN publisher

### 1.1 The structural point first

The existing specialist pods (`src/brambleloop/intel/pods.py`) are **forms**: blankets,
amigurumi, garments, hats, home_decor, bags. There is no children's pod, and there should not be
one — a children's pod would compete with the blankets pod for a baby blanket and neither would
clearly own it. **DERIVED** from reading the module: children's is a second axis (recipient), and
the right modelling is a per-product *audience* attribute that carries its own constraint set,
consulted alongside whichever form pod already owns the object.

`src/brambleloop/brand/storefront.py` already has a `Baby & Nursery` storefront section, and
`radar/opportunity.py` already carries `baby` and `nursery` as demand/competition keys. So the
merchandising surface exists; what does not exist anywhere in the repository is the audience's
safety and eligibility model. Verified by grep on 2026-09-24: **zero** occurrences of `choking`,
`CPSIA`, `safety eye`, `drawstring` or `small parts` in `src/` or `tests/`.

### 1.2 The sub-categories

| sub-category | form pod it belongs to | audience | fit for a pattern publisher | why |
|---|---|---|---|---|
| Baby blankets / afghans | `blankets` | gift-buyer for 0–24m | **Strong** | Class A — machine-verifiable geometry, no fitted sizing, no attached parts. Already the repo's highest scored non-mosaic demand key (`baby` 0.82). |
| Milestone / keepsake blankets (monthly markers, name, birth stats) | `blankets` | new parent | **Strong** | Personalisation is text and motif placement, which is compiler work, not physical testing. Highest emotional price tolerance in the audience. |
| Lovey / comforter / security blanket | `amigurumi` + `blankets` | 12m+ | **Strong, with a mandatory statement** | Small, fast, giftable; but it sits directly on the safe-sleep line (§2.5) and cannot be published without the statement set. |
| Amigurumi toys / plushies | `amigurumi` | 3+ (or 0+ if embroidered-face) | **Strong on craft, contested on market** | The highest-velocity listings we can see are here (§3.2). Also the most crowded and the most IP-polluted shelf (§3.3). |
| Rattles / teethers | `amigurumi` | 0–12m | **Avoid for now** | A rattle contains a hard insert; a teether is mouthed by definition. Both are the small-parts case at its most severe, and a teether is arguably a child-care article rather than a toy. |
| Baby/child hats, booties, mittens | `hats` | 0–10y | **Strong** | Head-circumference grading is arithmetic we already do; sub-4-hour makes, which the repo already identifies as the fastest review accumulator. |
| Children's garments (cardigans, dresses, sweaters) | `garments` | 3m–16y | **Medium** | Class C: needs graded sizing and, honestly, physical test-crocheting. CYC publishes the size tables (§4.3) so grading is not guesswork, but fit is still unverifiable by compiler. Also carries the drawstring rule (§2.4). |
| Nursery decor (wall hangings, buntings, baskets, cushions) | `home_decor` | the adult decorating the room | **Strong** | Decorates a room, is not handled by the child, and therefore carries far lighter obligations than anything the child holds. Best risk-adjusted entry in the whole audience. |
| Crib mobiles | `home_decor` | 0–5m | **Medium, with a mandatory statement** | Suspended over a sleeping infant on cords. Publishable, but only with the removal statement (§2.6). |
| Infant sleep accessories (crib bumpers, liners, loungers, nap pillows, inclined sleepers) | — | — | **Never** | Etsy prohibits the *patterns*, not only the products (§2.7). |
| Baby carriers / slings / wraps | — | — | **Never** | Load-bearing infant containment under a mandatory US standard (§2.8). |
| Children's loose-fitting sleepwear (nightgowns, robes, pyjamas) | `garments` | up to size 14X | **Never** | Flammability-regulated in both jurisdictions; an untreated crocheted nightgown is the exact product the Canadian regulation was written about (§2.3). |

**ESTIMATED**, and labelled as such: the "fit" column is our judgement, informed by the
constraint research below and by the repository's existing Class A/B/C verifiability model
(`radar/opportunity.py: RISK_VERIFIABILITY`). It is not a market measurement.

### 1.3 The recommendation this produces

**Nursery decor and baby blankets/keepsakes first; amigurumi second and only with an
embroidered-face default; children's fitted garments last.** That ordering is chosen on
obligation and verifiability, not on demand — the demand ordering would put amigurumi first, and
amigurumi is simultaneously the most crowded shelf, the most IP-polluted shelf and the one whose
patterns carry the heaviest safety writing.

---

## 2. Safety and regulatory reality

This section is the one that materially shapes what we can offer. It is written conservatively
and it is not legal advice; where the answer is genuinely unsettled it says so.

### 2.1 Does CPSIA apply to us?

**The obligations attach to the physical children's product, and we do not make one.**

- **SOURCED** — CPSC defines a children's product as *"a consumer product designed or intended
  primarily for children 12 years of age or younger"*, determined on four factors (stated
  intended use, packaging/advertising representations, common consumer recognition, and CPSC's
  Age Determination Guidelines).
  <https://www.cpsc.gov/Business--Manufacturing/Business-Education/childrens-products>
- **SOURCED** — a children's product requires third-party testing at a CPSC-accepted lab, a
  Children's Product Certificate, and tracking labels (same page).
- **DERIVED** — a PDF of instructions is not the physical article; the person who crochets the
  toy and then *sells* it is the manufacturer and inherits the CPC, testing and tracking-label
  obligations. Our regulatory exposure is therefore not CPSIA compliance — it is (a) what we
  instruct people to build, and (b) whether we mislead a buyer who intends to sell finished items
  into thinking none of this applies to them.
- **UNKNOWN** — we did not find any CPSC statement addressing patterns or instructions directly.
  We searched for it; it was not there. We are not asserting an exemption exists, only that no
  obligation was located, and nothing here should be read as advice to a buyer.
- **SOURCED (secondary)** — Etsy's own position is that the seller carries compliance: *"you are
  responsible for complying with all applicable laws and regulations for the products you list"*,
  and *"Etsy assumes no responsibility for the accuracy, labeling, or content of your listings."*
  <https://www.compliancegate.com/etsy-product-compliance-and-safety-requirements/>

**Consequence for our product:** every children's pattern carries a short, non-patronising block
telling a buyer who intends to sell finished items that they become the manufacturer, and
pointing at CPSC (US) and the Canada Consumer Product Safety Act (Canada) without pretending to
advise them.

### 2.2 Small parts, safety eyes, and the 36-month line

This is the single most important design constraint in the children's audience.

- **SOURCED** — the small parts ban (16 CFR 1501) applies to children's products *intended for
  use by children under 3*. A small part is any object that fits entirely, uncompressed and in
  any orientation, into the small parts cylinder. Whole toys, separable components, and pieces
  that come off during simulated-use testing all count.
  <https://www.cpsc.gov/Business--Manufacturing/Business-Education/Business-Guidance/Small-Parts-for-Toys-and-Childrens-Products>
- **SOURCED** — for toys and games intended for children **3 to under 6** that contain a small
  part, a cautionary statement is required under 16 CFR 1500.19. Books, paper articles, writing
  materials, modelling clay, fingerpaints, watercolours and paint sets are excepted.
  <https://www.law.cornell.edu/cfr/text/16/1500.19>
- **SOURCED (search-result quotation)** — the required wording is
  *"WARNING: CHOKING HAZARD — Small parts. Not for children under 3 yrs."*
  The exact statement is rendered as an image in the eCFR text, so we quote it from search
  results rather than from the regulation's own prose. Treat the wording as needing one
  confirmation from a rendered copy of the rule before it goes on a live listing.
- **SOURCED** — ASTM F963 is the mandatory US toy standard; for soft toys the sections that bite
  are 4.3.7 stuffing materials, 4.27 stuffed and bean-bag-type toys, and 4.14 cords, straps and
  elastics, all third-party tested.
  <https://www.cpsc.gov/Business--Manufacturing/Business-Education/Toy-Safety/ASTM-F-963-Chart>
- **SOURCED (secondary)** — ASTM F963 practice for plush: seam strength must hold the filling in,
  and attached small parts such as eyes and noses are tension tested (reported as 90 N).
  <https://www.tradeaiders.com/plush-toy-safety-quality-control-professional-diy-pull-test-guide-for-seams-and-eyes.html>
- **Canada, SOURCED** — Toys Regulations SOR/2011-17 s.7(1): toys for children under three may
  not have separable parts that fit in the small parts cylinder at ≤4.45 N. s.31: eyes and noses
  ≤32 mm must either be ungraspable by the three-pronged claw hook or pass the Schedule 4
  detachment test. s.30 covers squeakers and similar inserts; s.28 fastenings; s.29 stuffing
  (clean, vermin-free, free of hard or sharp foreign matter, within toxicity limits).
  <https://laws-lois.justice.gc.ca/eng/regulations/SOR-2011-17/FullText.html>
- **SOURCED (craft-industry consensus)** — safety eyes are not recommended for toys intended for
  children under three; embroidered eyes, or felt/yarn eyes sewn on securely, are the standard
  alternative.
  <https://www.lilleliis.com/safety-eyes-for-amigurumi-toys/> ·
  <https://yarniss.net/blogs/crochet-for-beginners/safety-eyes-101-sizes-tips-and-safe-alternatives-for-toys>

**Consequence for our product.** A Brambleloop amigurumi pattern defaults to an **embroidered or
crocheted-on face**, with safety eyes offered only as a clearly-labelled variant for an audience
of 3+. This is the opposite of the market default — a safety-eye photograph is the genre's
visual signature — and it is worth being clear that it is a real merchandising cost we are
choosing to pay. A pattern that shows safety eyes in the hero image and says "not for under 3"
in the last paragraph is a pattern whose photograph contradicts its own warning.

### 2.3 Children's sleepwear: a hard refusal

- **SOURCED** — Canada's Children's Sleepwear Regulations SOR/2016-169 define loose-fitting
  sleepwear as nightgowns, nightshirts, dressing gowns, bathrobes, housecoats, robes, pyjamas and
  baby-doll pyjamas up to and including size 14X, and impose flammability testing after a
  wash/dry cycle where the garment is not flame-retardant treated.
  <https://laws-lois.justice.gc.ca/eng/regulations/SOR-2016-169/FullText.html> ·
  <https://www.canada.ca/en/health-canada/services/consumer-product-safety/legislation-guidelines/guidelines-policies/guide-children-sleepwear-flammability-requirement.html>
- **SOURCED (secondary)** — Etsy prohibits loose-fitting, non-flame-resistant sleepwear and
  loungewear for children sized from 10 months up to size 14 (Etsy's Children and Baby Products
  policy; see §2.7 on why we could not fetch it directly).
- **DERIVED** — crochet fabric from untreated natural or acrylic yarn is not flame-resistant and
  a crocheted nightgown or robe is loose-fitting by construction. We publish **no** children's
  sleepwear pattern.

### 2.4 Drawstrings: the constraint nobody expects a crochet pattern to hit

- **SOURCED** — 16 CFR 1120 places on the substantial product hazard list: children's upper
  outerwear sizes 2T–12 with neck or hood drawstrings, and sizes 2T–16 with waist or bottom
  drawstrings that do not conform to ASTM F1816-97. That standard prohibits hood/neck drawstrings
  outright and limits waist/bottom drawstrings to 3 inches outside the channel when the garment
  is expanded to its fullest width, with no toggles or knots at the free ends.
  <https://www.federalregister.gov/documents/2011/07/19/2011-17961/substantial-product-hazard-list-childrens-upper-outerwear-in-sizes-2t-to-12-with-neck-or-hood> ·
  <https://cpsc.gov/business--manufacturing/business-education/business-guidance/drawstrings-in-childrens-upper-outerwear/frequently-asked-questions-faqs>
- **SOURCED** — Health Canada's position is that cords and drawstrings should be removed from
  children's hoods, hats and jackets, and that CCPSA ss.7(a)/8(a) make the seller responsible for
  the product not posing a danger. Health Canada recorded 16 Canadian incidents 1988–2014
  including three deaths, and 38 related recalls in eight years.
  <https://www.canada.ca/en/health-canada/services/consumer-product-safety/reports-publications/consumer-education/your-child-safe/is-your-child-safe.html> ·
  <https://stikeman.com/en-ca/kh/canadian-product-liability-law/health-canada-caution-drawstrings-in-children-upper-outerwear>

**Consequence.** A hooded child's cardigan or poncho pattern that instructs a chained tie through
the neckline is instructing the maker to build a listed substantial product hazard. Our
children's outerwear patterns use a button, a toggle-free closure or a sewn-on fixed tie; never a
hood or neck drawstring. This is checkable deterministically from the CIR, which is why it is in
the code deliverable.

### 2.5 The infant sleep environment: blankets and loveys

- **SOURCED** — AAP 2022: keep soft objects (pillows, pillow-like toys, quilts, comforters,
  mattress toppers, fur-like materials) and loose bedding (blankets, non-fitted sheets) away from
  the infant's sleep area, to reduce SIDS, suffocation, entrapment and strangulation risk.
  Applies to infants under 12 months.
  <https://publications.aap.org/pediatrics/article/150/1/e2022057991/188305/Evidence-Base-for-2022-Updated-Recommendations-for> ·
  <https://www.healthychildren.org/English/ages-stages/baby/sleep/Pages/a-parents-guide-to-safe-sleep.aspx>
- **SOURCED (secondary, consistent)** — loveys are for supervised awake use until 12 months;
  nothing loose belongs in the crib before then.
  <https://www.takingcarababies.com/blogs/sleep-basics/loveys>

**Consequence, and it is an awkward one commercially.** "Baby blanket" is the single most
merchandised object in the audience and the AAP's guidance is that it does not go in the crib
under 12 months. We do not solve that by not mentioning it. Every baby blanket and lovey pattern
carries a plain statement that the finished item is for supervised, awake use — tummy time, pram,
floor, cuddles — and not for an unsupervised sleep space before 12 months. **ESTIMATED**: we
expect this to cost nothing in conversion and to be a trust asset, because the audience that buys
a keepsake blanket is the audience that has read the safe-sleep material; but that is a
judgement, not a measurement, and it is worth an A/B once listings exist.

### 2.6 Crib mobiles

- **SOURCED (secondary, consistent with long-standing CPSC guidance)** — remove mobiles and crib
  gyms by the time the child can push up on hands and knees, or 5 months, whichever comes first;
  entanglement in the loops formed by ribbons and cords is the mechanism.
  <https://www.cpsc.gov/Newsroom/News-Releases/1989/Strangulation-Risk-Prompts-Warning-About-Crib-Kickers>

Publishable with that statement, out of the child's reach, and with no detachable small parts on
the hanging elements.

### 2.7 Etsy's Children and Baby Products policy — including patterns

This is the platform-level constraint and it is more restrictive than most sellers realise.

- **SOURCED (search-result quotation; the policy page itself is not retrievable by us)** —
  *"Etsy does not allow patterns, designs, or instructions for making prohibited children and
  baby items."* Policy URL:
  <https://www.etsy.com/legal/policy/children-and-baby-products-policy/239344787532>
- **SOURCED** — an updated Children and Baby Products policy took effect **2026-06-02**, adding
  *"clearer restrictions on products with small parts that may pose choking or ingestion risks"*,
  *"updated examples of prohibited infant sleep furniture and accessories"*, and additional
  prohibited examples such as infant neck flotation devices.
  <https://community.etsy.com/forum/announcements-290/topic/updates-to-our-children-and-baby-products-policy-182209/>
- **SOURCED (search-result quotation)** — prohibited infant sleeping accessories for children
  under 3 include crib bumpers, crib rail covers extending over the side of the crib, non-mesh
  crib liners, and pillows intended for babies to sleep on including infant loungers, baby support
  pillows and baby nap cushions. The US statutory backdrop is the Safe Sleep for Babies Act of
  2021, which bans crib bumpers and certain inclined sleepers.
  <https://feldmanshepherd.com/blog/safe-sleep-for-babies-act-bans-two-deadly-infant-sleep-products/>

**Verified limitation, stated rather than papered over.** `etsy.com` returns **HTTP 403** to this
environment — confirmed by direct request on 2026-09-24 against
`/legal/policy/children-and-baby-products-policy/239344787532` and against the Seller Handbook.
This matches what BUILD_STATE already records about Etsy's bot protection. So the policy text
above is quoted from search-result summaries of Etsy's own page, not from a fetch of it. **That is
a real evidence gap on a constraint we intend to enforce**, and it is listed in §6 as the first
thing to close.

### 2.8 Baby carriers and slings

- **SOURCED** — ASTM F2907-22 became the mandatory consumer product safety standard for sling
  carriers on 2022-11-19, codified at 16 CFR 1228; a sling carrier is defined as fabric or sewn
  fabric construction designed to contain up to two occupants from full-term birth to 35 lb, and
  manufacturers must issue a Children's Product Certificate citing part 1228.
  <https://www.cpsc.gov/business--manufacturing/business-education/business-guidance/sling-carriers> ·
  <https://www.federalregister.gov/documents/2022/08/19/2022-17707/safety-standard-for-sling-carriers>

A crocheted sling is a load-bearing infant-containment product whose failure mode is a dropped
infant. We publish no pattern for one.

### 2.9 EU GPSR — genuinely unsettled

- **SOURCED** — commentary is split: most treat purely digital goods as outside GPSR's practical
  scope, while the European Commission's Q&A is reported as saying GPSR applies to *"all types of
  products (physical or digital products, including software)"* placed on the EU single market
  where not already covered by other Union law. Etsy provides a shop-level setting to stop selling
  into the EEA and Northern Ireland, and it applies to physical **and** digital goods.
  <https://euverify.com/resource/gpsr-compliance-for-etsy-listings/> ·
  <https://help.etsy.com/hc/en-us/articles/28211364687383-What-is-the-General-Product-Safety-Regulation-GPSR>
- **UNKNOWN** — whether a crochet pattern PDF sold from Canada into the EU requires an EU
  Responsible Person. We did not establish this and we are not guessing at it.

This is a merchandising decision, not an owner action: it can wait until there is a listing.

### 2.10 What a responsible children's pattern must state

Collected from the above. This is the statement set the code deliverable enforces:

1. **Stated age suitability**, as an explicit band, not an implication from the photograph.
2. **Small parts / choking**, where any applied part exists — with the 16 CFR 1500.19 wording for
   a 3-to-6 audience, and a refusal rather than a warning for under 3.
3. **Face construction**, stating embroidered as the default and safety eyes as a 3+ variant.
4. **Safe sleep**, for anything soft going near a cot: supervised, awake use; not in an
   unsupervised sleep space before 12 months.
5. **Supervision**, plainly, for any toy.
6. **Construction integrity**, because in a crocheted toy the safety property *is* the
   workmanship: stitch tension tight enough that stuffing cannot migrate through the fabric,
   closed seams, and securely attached limbs.
7. **Fibre and care**, because washability is a hygiene property for this audience.
8. **If you sell what you make**, you become the manufacturer: CPSC/CPSIA in the US, CCPSA and the
   Toys Regulations in Canada. Pointer, not advice.
9. **Not legal advice**, and the date the safety guidance was compiled — because a safety
   statement with no date silently becomes a claim about the past, which is the same failure
   `gates/platform_policy.py` was built to prevent.

---

## 3. Demand, seasonality, price and competitive density

### 3.1 What we could actually measure

**Wikimedia pageviews, en.wikipedia, `user` agent class, monthly, 2025-09 → 2026-08.** Pulled
directly on 2026-09-24. This is the same feed `culture/feeds.py` already uses, so it is a signal
the system can re-take on a schedule.

| month | `Amigurumi` | `Baby_shower` |
|---|---|---|
| 2025-09 | 6,247 | 11,077 |
| 2025-10 | 6,519 | 10,141 |
| 2025-11 | 6,848 | 9,026 |
| 2025-12 | **7,676** | 6,914 |
| 2026-01 | 6,017 | 8,402 |
| 2026-02 | 4,745 | 7,492 |
| 2026-03 | 4,636 | 8,638 |
| 2026-04 | 4,261 | 8,232 |
| 2026-05 | 4,472 | 9,441 |
| 2026-06 | **3,997** | 9,760 |
| 2026-07 | 4,322 | 7,786 |
| 2026-08 | 4,340 | 7,325 |

**SOURCED**: `https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/Amigurumi/monthly/2025090100/2026083100`
(and the same URL with `Baby_shower`).

**DERIVED** from that table:

- Amigurumi: mean 5,340, peak/trough **1.92×**, peak December, trough June.
- Baby_shower: mean 8,686, peak/trough **1.60×**, peak September, trough **December**.
- The two are **counter-seasonal**: amigurumi's annual maximum falls in the same month as
  baby-shower's annual minimum. A children's portfolio built only from toys inherits a 1.9× swing;
  one that pairs toys with baby-occasion products should be materially flatter.

**Caveats, stated because they matter.** This is encyclopaedia reading, not purchase intent; it is
English Wikipedia, so the population is closest to `GLOBAL`/`US` in the repository's own
`radar/provenance.py` vocabulary, not `CA`; and it is one year, n=12. It is a proxy and it is
labelled a proxy. It does confirm, with a measurement rather than an assertion, the claim already
sitting in `radar/opportunity.py` that baby demand "repeats all year rather than once a season" —
that line had no series behind it until now.

### 3.2 Price and velocity, from a third-party aggregator

EtsyHunt's "top 100 best selling crochet patterns", data dated **2026-09-01**, fetched 2026-09-24:
<https://etsyhunt.com/best-etsy-crochet-patterns>

| rank | listing | weekly | lifetime | revenue | **DERIVED** avg price |
|---|---|---|---|---|---|
| 1 | Ghost Granny Square Blanket Pattern | 291 | 1,072 | $6,432 | $6.00 |
| 2 | Halloween Witch Fairy Crochet Doll Pattern | 70 | 3,446 | $19,849 | $5.76 |
| 3 | 150+ Bunny Crochet Patterns Bundle | 67 | 311 | $404 | $1.30 |
| 4 | 20,000+ Amigurumi Crochet Patterns Bundle | 63 | 140 | $463 | $3.31 |
| 5 | Haunted Harvest Crochet Patterns Bundle | 51 | 772 | $5,196 | $6.73 |
| 6 | Crochet Star Pillow Pattern | 50 | 13,999 | $116,052 | $8.29 |
| 7 | Winnie the Pooh Friends Crochet Pattern | 49 | 556 | $5,788 | $10.41 |
| 8 | Sitting Baby Cat Crochet Pattern | 48 | 3,225 | $19,318 | $5.99 |
| 9 | 14000+ Amigurumi Crochet Patterns Bundle | 48 | 118 | $177 | $1.50 |
| 10 | Crochet Christmas Wreath Pattern PDF | 47 | 118 | $372 | $3.15 |

**SOURCED-THIRD-PARTY**, and its accuracy is **not independently verified** — these are an
aggregator's estimates of another platform's sales, and we could not check them against Etsy
because Etsy returns 403 to us. The currency is presumably USD; it is not stated.

**DERIVED** from the arithmetic:

- Five of the top ten are children's toy patterns or bundles of them. On the evidence we can see,
  **children's toys are the highest-velocity shelf in crochet patterns.**
- Single-pattern amigurumi clusters tightly at **$5.76–$6.00**. The one non-toy single pattern
  (star pillow) sits higher at **$8.29**, and the licensed-character listing highest at $10.41.
- The mega-bundles price at **$1.30–$3.31 per transaction** — a fifth of a single pattern. They are
  not competing on the same axis as we would be.
- Against the repo's own 2026-09-17 competitor observations (`radar/market.py`: amigurumi at
  CA$2.75–8.78, garments at CA$9.90–14.05), the children's toy price ceiling is low and the
  blanket/decor ceiling is higher. **This is the commercial argument for leading with nursery
  decor and keepsake blankets rather than toys**, and it runs against where the volume is.

### 3.3 Competitive density, and the part of it we must not imitate

- **From repo observations, SOURCED** — `radar/opportunity.py: CATEGORY_EVIDENCE` records 43.2k
  reviews on one amigurumi collection at CA$2.75–8.78: "enormous volume, but the shelf is owned".
  `CATEGORY_COMPETITION` already scores `amigurumi` at 0.90, the highest of any key.
- **DERIVED from §3.2** — two of the top ten mechanics are ones the Execution Directive forbids us
  outright:
  1. **Licensed-character IP.** "Winnie the Pooh Friends Crochet Pattern" is the highest average
     price in the table. Character amigurumi is a large fraction of the shelf and it is trademark
     and copyright infringement.
  2. **Mass bundles of other people's patterns.** A "20,000+ Amigurumi Patterns Bundle" at $3.31
     is not a product; it is redistribution. Three of the top ten are of this shape.
- **DERIVED consequence.** The *addressable* top of the children's amigurumi shelf is smaller than
  the chart suggests. Ranks 2 and 8 (original characters) are the ones a legitimate publisher
  competes for. This is not a complaint — it is an argument that **original, safety-literate
  children's patterns have a cleaner differentiator here than in any other category we have looked
  at**, because a large part of the visible competition cannot be bought by a careful buyer
  without misgivings.
- **UNKNOWN** — absolute listing counts, review distributions and shop counts for the children's
  sub-categories on Etsy. These need the Etsy credential, which this department did not and will
  not use. No number is invented for them.

---

## 4. Keywords, taxonomy and attributes

### 4.1 Etsy taxonomy: what is established, and what is not

- **From the repository, verified** — `integrations/etsy.py` already pins
  `TAXONOMY_PATTERNS = 66  # craft_supplies_and_tools.patterns`, with tag/material maxima of 13
  and a digital quantity of 999.
- **SOURCED** — the documented way to establish the attribute set for a taxonomy node is
  `getSellerTaxonomyNodes` to find the node id, then `getPropertiesByTaxonomyId` for that id; only
  properties with `"supports_variations": true` may be used in `property_values`.
  <https://developer.etsy.com/documentation/tutorials/listings/>
- **SOURCED (search-result quotation)** — Etsy states the attribute options available vary by the
  chosen category, and that most categories include colour, celebration and occasion attributes
  (Etsy Seller Handbook, "Updates to Listing Categories and Attributes",
  <https://www.etsy.com/seller-handbook/article/362857340643>; the article returns 403 to us).
- **UNKNOWN, and deliberately left unknown** — the concrete required/optional attribute list for
  taxonomy node 66, and whether Etsy exposes any children's-specific attribute (age band,
  recommended age) on a digital pattern listing. Establishing it requires one
  `getPropertiesByTaxonomyId(66)` call. **This department was instructed to make no Etsy API call
  and made none.** We are not going to describe an attribute schema we have not read.

What the repository currently sends is in `commerce/search.py: listing_attributes()` — a
hand-built dict (`digital`, `instant_download`, `file_type`, `craft_type`, `pattern_type`,
`skill_level`, `primary_color`, `secondary_color`, `occasion`, `terminology`, `includes_chart`,
`includes_written_instructions`). **DERIVED**: none of those keys is verified against Etsy's actual
property list for node 66, and none of them expresses a children's audience. A children's launch
needs both gaps closed, in that order.

### 4.2 Title and tag structure for the children's audience

**DERIVED** from the observed competitor titles in `radar/market.py` and §3.2, plus the
repository's existing `commerce/search.py` tag budget rules:

- The audience word is the *recipient*, and it is a distinct search axis from the form word. A
  children's listing needs both: `Baby Blanket Crochet Pattern`, not `Blanket Crochet Pattern`.
- Age/size words are high-intent and specific: `newborn`, `0-3 months`, `toddler`, `3-6 months`,
  `12 months`, `size 2T`. The repo's `teardown/reader.py` already carries the
  `newborn / baby / toddler / child / adult / preemie` vocabulary.
- Occasion words carry the gifting intent that §3.1 shows is year-round: `baby shower gift`,
  `new baby`, `baby announcement`, `christening`, `first birthday`.
- **Safety terms are a differentiator, not a disclaimer.** `no safety eyes`, `embroidered eyes`,
  `baby safe` are search terms buyers making for an infant actually type. **ESTIMATED**: we have no
  volume data for them and are not inventing any; but they are free to include in a 13-tag budget
  and they align the listing with our actual product decision from §2.2.
- Existing rules in `commerce/search.py` still apply: no tag wholly containing another, and the
  per-word budget.

### 4.3 Sizing: the one place where a standard removes guesswork

The Craft Yarn Council publishes the size tables the whole industry grades against, free.
**SOURCED** — <https://www.craftyarncouncil.com/standards/baby-size-chart> and
<https://www.craftyarncouncil.com/standards/child-youth-sizes>

Baby (chest): 3 mo 16" / 40.5 cm · 6 mo 17" / 43 · 12 mo 18" / 45.5 · 18 mo 19" / 48 ·
24 mo 20" / 50.5. The charts also give centre-back-neck-to-wrist, back waist length, cross back,
arm length to underarm, upper arm, armhole depth, waist and hips.

Child/youth (chest): 2 → 21" / 53 cm · 4 → 23" / 58.5 · 6 → 25" / 63.5 · 8 → 26½" / 67 ·
10 → 28" / 71 · 12 → 30" / 76 · 14 → 31½" / 80 · 16 → 32½" / 82.5.

**DERIVED**: these bands are what make children's garments gradeable by code rather than by
test-crocheting every size, and they are also what lets a deterministic check ask whether a
pattern that claims "2T–12" actually publishes finished measurements for each size in that span.

---

## 5. Code deliverable

`src/brambleloop/intel/childrens.py` with `tests/test_childrens.py`.

It earns its place on one argument: **every constraint in §2 is a property of a product concept
that code can evaluate before a pattern is written**, and the alternative — a human remembering
nine statement requirements and a dozen prohibitions at listing time — is the failure mode this
repository exists to remove. The module carries:

- a dated snapshot of the constraints with every one naming a source URL and a read date, in the
  shape `gates/platform_policy.py` established, so a change in Etsy's policy is detectable as a
  change rather than as a difference of opinion;
- the age bands with the 36-month regulatory line;
- the sub-category table from §1.2, each entry pointing at the form pod that owns it in
  `intel/pods.py` and at the constraints that apply to it;
- the subjects whose *instructions* we refuse to publish;
- `assess()`, which returns findings that each state what was measured and why;
- `required_statements()`, the §2.10 set, resolved per sub-category and audience;
- the CYC size tables, as data, with the source.

What it deliberately does **not** contain: any demand number, price estimate or competition score
for a children's sub-category. Those belong in `radar/opportunity.py`, they need evidence we do
not have, and a module that carried an invented 0.8 next to a sourced regulation would make the
regulation look invented too. A test asserts that absence.

---

## 6. What is blocked, and on what

| # | blocked thing | blocked on | what would unblock it |
|---|---|---|---|
| 1 | Reading Etsy's Children and Baby Products policy **verbatim** | `etsy.com` returns HTTP 403 to this environment (verified 2026-09-24) | The policy text arriving by a sanctioned route. Until then the module's prohibition list is built from search-result quotations of Etsy's page and is marked as such in the code. |
| 2 | The attribute schema for taxonomy node 66 | one `getPropertiesByTaxonomyId(66)` call, which this department was instructed not to make | Another department, or a later session, making that call once. It is cheap and it is the highest-value single unknown in §4. |
| 3 | Listing counts / review distributions / shop counts per children's sub-category | the Etsy credential, same constraint | Same. Until then `CATEGORY_DEMAND`/`CATEGORY_COMPETITION` for children's keys stay as the estimates they already are, and are not dressed up. |
| 4 | Confirming the exact 16 CFR 1500.19 warning glyph string | the regulation renders it as an image | One look at a rendered copy of the rule before any live listing carries the wording. |

**No OWNER ACTION REQUIRED item arises from this research.** Nothing here needs money, KYC, legal
acceptance or a physical act.

---

## 7. Recommendations

1. **Adopt children's as an audience attribute, not a pod.** One new axis on the product concept,
   consulted alongside the existing form pods.
2. **Enter through nursery decor and keepsake/baby blankets.** Highest price ceiling, lightest
   obligation, and the demand is the flattest across the year of anything we have measured.
3. **Make the embroidered face the Brambleloop default for amigurumi**, with safety eyes as a
   labelled 3+ variant, and let the hero photograph match the warning. Treat it as positioning,
   not as a caveat.
4. **Publish no sleepwear, no infant sleep accessory, no sling and no crib bumper — not even the
   pattern.** Etsy's policy reaches instructions, and so does our own judgement.
5. **Add a sixth policy surface to `gates/platform_policy.py: POLICY_SOURCES`** for the Children
   and Baby Products policy, gating the workflows `publishing` and `product_creation`. This
   department did not edit that file because another department may be in it; it is a small change
   and it should be made by whoever integrates this.
6. **Spend one API call on `getPropertiesByTaxonomyId(66)`** and replace the hand-built attribute
   dict in `commerce/search.py` with the real property list, adding a children's age attribute if
   one exists.
7. **Re-take the Wikimedia series quarterly.** It is free, it is already wired, and it turns the
   "baby demand is year-round" line in `radar/opportunity.py` from an assertion into a measurement.
