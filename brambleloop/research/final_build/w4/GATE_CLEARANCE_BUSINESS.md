# Business gate clearance (W4-GATESB)

Owner authorisation 2026-10-07. Per gate: cleared / owner action (exact cost, links, minutes) / not yet askable (and why) / data-gated. Nothing was bought, sent, published or spent.

| gate | status | owner minutes | max CA$ |
|---|---|---|---|
| benchmark_purchases | OWNER-ACTION | 75 | 300.0 |
| physical_proof | OWNER-ACTION | 5 | 59.65 |
| tester_roster | OWNER-ACTION | 20 | 0.0 |
| second_market_benchmark | COMPANY-SELECTED (observation pending) | - | - |
| owned_surfaces | PARTLY CLEARED (Etsy shop recognised) + OWNER-ACTION | 65 | 25.0 |
| customers | DATA-GATED (external: buyers) | - | - |
| ad_authority | NOT-YET-ASKABLE | - | - |
| live_listings | ASKED IN leave_shadow (company work first, per product) | - | - |

Asked now: ~165 min, up to CA$384.65.

## 1. benchmark_purchases -- buy these 13 (OWNER ACTION)

the gate text said 'roughly ten'; the owner approved thirteen at a CA$300 ceiling on 2026-09-20 (B-501, B-512) and intake enforces SET_SIZE=13 / SET_BUDGET_CAD=300. The required set is the 13 below, chosen by purchase_selection's deterministic facet coverage (B-485, B-507/B-509): 428 of 441 observed listings become redundant; a 10-pick set would leave bags, home_decor and ornaments uncovered

| # | department | listing | CA$ | link |
|---|---|---|---|---|
| 1 | garments | CROCHET PATTERN & VIDEO/ Caribbean Sea Sweater, Crochet Lace Sweater P | 22.00 | https://www.etsy.com/listing/4313051459/crochet-pattern-video-caribbean-sea |
| 2 | blankets | CROCHET PATTERN Large Mouth Bass Blanket - Crochet Pattern for Bass Fi | 16.00 | https://www.etsy.com/listing/540992118/crochet-pattern-large-mouth-bass-blanket |
| 3 | collections | CROCHET PATTERN EBOOK V-Stitch Summer Garment Collection includes V-Ne | 60.50 | https://www.etsy.com/listing/1748603334/crochet-pattern-ebook-v-stitch-summer |
| 4 | education | The Perfect Fit Guidebook: Unlocking Pattern Sizing and Body Measureme | 21.00 | https://www.etsy.com/listing/1500579838/the-perfect-fit-guidebook-unlocking |
| 5 | hats | CROCHET HAT PATTERN/ Star Stitch Big Bow Baby Hat, Rose Flower Beanie | 18.00 | https://www.etsy.com/listing/1465106601/crochet-hat-pattern-star-stitch-big-bow |
| 6 | amigurumi | CROCHET PATTERN Bulky & Quick Rustic Farmhouse Pumpkin Pattern | 18.00 | https://www.etsy.com/listing/648978969/crochet-pattern-bulky-quick-rustic |
| 7 | stockings | CROCHET PATTERN & VIDEO/ Snuggle Season Christmas Stocking, Crochet Ch | 19.00 | https://www.etsy.com/listing/1813509350/crochet-pattern-video-snuggle-season |
| 8 | kitchen_bath | CROCHET PATTERN & VIDEO/ Cozy Cottage Dishcloth, Easy Crochet Dishclot | 16.00 | https://www.etsy.com/listing/1889917386/crochet-pattern-video-cozy-cottage |
| 9 | seasonal_gift | CROCHET PATTERN & VIDEO/ Mj's Merry Advent Calendar Crochet Stockings  | 16.00 | https://www.etsy.com/listing/1330088510/crochet-pattern-video-mjs-merry-advent |
| 10 | unclassified | CROCHET PATTERN / Dusty Rose Baby Set | 20.00 | https://www.etsy.com/listing/628097461/crochet-pattern-dusty-rose-baby-set |
| 11 | home_decor | PUMPKIN PILLOW CROCHET Pattern / Hello Harvest Pumpkin Pillow pattern | 18.00 | https://www.etsy.com/listing/1321496043/pumpkin-pillow-crochet-pattern-hello |
| 12 | bags | CROCHET PATTERN & VIDEO/ Winterberry Soap Saver, Reusable Soap Pouch,  | 18.00 | https://www.etsy.com/listing/4446092413/crochet-pattern-video-winterberry-soap |
| 13 | ornaments | CROCHET PATTERN// Granny Square Ball, Granny square Christmas Ornament | 18.00 | https://www.etsy.com/listing/1613235888/crochet-pattern-granny-square-ball |
| | | **total** | **280.50** | ceiling CA$300 |

Delivery (existing intake, nothing new):

1. Buy each listing on Etsy (signed in as the owner; any payment method).
2. Open Etsy > You > Purchases and reviews > Download files for that order.
3. Open https://brambleloop-os-production.up.railway.app/ops/teardown on the same phone or computer, paste the operator token (BRAMBLELOOP_OPS_TOKEN; kept in page memory only).
4. Tap the pick (rows are the approved set in the same order), choose the downloaded file(s) -- zips are accepted and expanded -- optionally type the price paid.
5. Repeat per purchase. The page shows received/outstanding; nothing needs renaming.

API: POST https://brambleloop-os-production.up.railway.app/api/teardown/intake (multipart: listing_ref, files, optional paid_cad, licence_terms). Gate opens on the first intake. Never copied into products.

## 2. physical_proof -- kit ready (asked together with item 3: one tester_outreach decision)

Pattern: **Crochet Hexagonal Bread Basket** `market-basket-small@1.2.0` (content 1ddde587f537388b), B (dimensional_form); scope full_make.

`market-basket-small` (Crochet Hexagonal Bread Basket) at its current
release. Chosen by rule, not taste, from the Launch-0 products whose risk class requires
physical evidence before live sale (`gates.risk_matrix`):

* hexagon-coaster-set is Class A -- clears on deterministic evidence; a make proves nothing
  it needs;
* cloudline-baby-blanket is Class B on high yardage: ~15 h make, ~600 m, ceiling ~CA$441;
* the three market baskets are Class B on `dimensional_form`, share one gauge, stitch and
  yarn weight (sc, 12.5 sts/10 cm, 5.0 mm, worsted cotton), and the small one is the
  cheapest make (~2.2 h, ~52 m; ceiling CA$59.65 at the risk matrix's own rates).

A full make of the small basket satisfies its partial-physical requirement (a full make
contains one, `risk_matrix.satisfies`), calibrates the sc/worsted-cotton yardage factor all
three baskets use, falsifies or confirms a closed 3-D form's stated size (the risk the class
exists for), and yields the finished-object photograph #64's upgrade path is waiting for.

Printable kit: `research/final_build/w4/tester_kit/` -- market-basket-small-1.2.0-TEST.pdf, market-basket-small-1.2.0-RECORD-SHEET.pdf

Materials (ESTIMATED CA$):

- worsted-weight 100% cotton yarn, colour A (cream) -- 1 ball (twin: 40.2 m needed; any ball of >= 50 m) -- CA$5.00
- worsted-weight 100% cotton yarn, colour B (wine) -- 1 ball (twin: 11.9 m needed) -- CA$5.00
- 5.0 mm crochet hook -- 1 -- CA$6.00
- tapestry needle, 4 stitch markers, scissors -- 1 set -- CA$4.00
- kitchen scale reading to 1 g -- tester's own -- CA$0.00
- tape measure / ruler (cm) -- tester's own -- CA$0.00
- materials total ~CA$20.00; approval ceiling CA$59.65 (gates.risk_matrix.owner_action_spec: 2.8 tester hours (estimate x1.3) at CA$20/h + 63 m yarn at CA$0.06/m. ESTIMATED ceiling; no tester has been paid yet)

Person: one independent adult crocheter (not the owner, F-071) who agreed through the tester programme (quality.tester_programme). Skill: confident with single crochet worked in joined rounds, increasing at six points to make a flat hexagon, and turning a base into straight walls; can read a written pattern in US terms; owns or can borrow a 1 g kitchen scale. Time: about 2-3 hours of making plus 15 minutes of measuring and recording.

Protocol:

1. Before starting: weigh each full ball and record the ball band (grams and metres)
2. Work a 10 x 10 cm sc swatch first; record stitches and rounds per 10 cm and the hook
3. Make the basket exactly as written in the test PDF; note every place you had to guess, re-read or rip back, with the round number
4. Weigh what is left of each ball; grams used = start minus end, per colour
5. Measure the finished base across the points and across the flats, and the wall height, in cm, without stretching
6. Record total hours and whether you followed the instructions exactly
7. Photograph the finished basket on a plain surface (top and side) in daylight
8. Return the record sheet and photos; the operator enters them (POST /api/physical-test and /api/physical-photo)

Records -> intake: your tester reference -> `tester_ref`; grams used, colour A (cream) -> `grams_by_color.cream`; grams used, colour B (wine) -> `grams_by_color.wine`; ball band: grams per ball -> `ball_band_grams`; ball band: metres per ball -> `ball_band_metres`; hook used (mm) -> `hook_mm`; swatch: sts and rounds per 10 cm -> `notes`; base across the points (cm) -> `measured_width_cm`; base across the flats (cm) -> `notes`; wall height (cm) -> `measured_height_cm`; total hours -> `hours`; followed exactly? yes/no -> `instructions_followed`; anything unclear or wrong (round numbers) -> `notes`

Entered via POST /api/physical-test (queued job physical.record); photo via POST /api/physical-photo {slug, sha256, source, rights}. the physical.record job writes a PhysicalTest row with completed_at.

## 3. tester_roster -- CONFIRM before anything is sent (OWNER ACTION)

Channel: Ravelry group 'The Testing Pool' -- a public tester-call post from the Brambleloop Ravelry account (makers browse it to find tests). Why: a public call is addressed to nobody, so it is not a commercial electronic message to an address; respondents contact us and give express consent on the intake form before we write to them. Needs: a Ravelry account in the owner's name (free; person-only signup).

### Exact post (not sent)

**[Tester call] Crochet Hexagonal Bread Basket -- worsted cotton, ~3 hrs, paid**

Hello! Brambleloop Studio (a small Canadian crochet pattern studio, Etsy shop BrambleloopStudio) is looking for 1-3 testers for a small hexagonal bread basket worked in single crochet: base about 16 cm across the points, walls about 9 cm tall, worsted-weight cotton in two colours (about 40 m + 12 m), 5.0 mm hook.

What we ask: make the basket from the test PDF within 14 days, follow it exactly, and fill in the one-page record sheet -- grams used per colour, the ball band (grams and metres), your hook, finished measurements, hours, and anything that was unclear or wrong. Mistakes you find are the most useful thing you can send.

What you get: the final pattern free, another Brambleloop pattern of your choice, a test fee for the make with yarn reimbursed (amount confirmed before you start), and credit if you want it. We never ask for reviews, ratings or favourites, and nothing depends on whether you like it.

To apply, reply in this thread or message the Brambleloop Ravelry account; we will send the intake form (it records your consent to be emailed about this test, which you can withdraw any time). Brambleloop Studio, Canada.

### Consent text (intake form)

I agree that Brambleloop Studio may email me about this pattern test (instructions, questions about my results, and the test fee). This is express consent under Canada's Anti-Spam Legislation, recorded with today's date; I can withdraw it at any time by replying 'unsubscribe' or using the link in any message, and it is actioned within 10 business days. Separately, I choose whether Brambleloop may show my photos of the finished object (on its Etsy listings / its own site / its emails / ads), and I can withdraw that permission for future use at any time. I am 18 or older. I understand no review, rating or favourite is requested, and my fee does not depend on my opinion.

### Intake form

- `handle` (required): name or handle to call you by (stored as a reference, not a contact list)
- `email` (required): email for this test only (kept with the consent record, not on the roster)
- `country_region` (required): country and province/state (for terminology and shipping-free kits)
- `experience` (required): crochet experience: beginner / intermediate / advanced
- `specialties` (required): what you usually make (departments)
- `can_weigh_grams` (required): do you have a kitchen scale reading to 1 g? (yes/no)
- `terms_preference` (required): US or UK crochet terms
- `express_consent` (required): tick: I agree that Brambleloop Studio may email me about this pattern test (instructio...
- `photo_permission_scopes`: optional: brambleloop_listing / brambleloop_site / brambleloop_email / advertising
- `credit_preference`: optional: credit by name / by handle / no credit

Offered: the final pattern PDF free, and the next Brambleloop pattern of their choice free; a test fee for the make (approved per make by the owner; default ceiling from gates.risk_matrix: CA$20/hour of estimated make time, yarn reimbursed at cost up to the stated ceiling); credit by name or handle in the pattern's acknowledgements, only if they want it. Never: a review, rating, favourite or testimonial (not askable: growth.creators); any condition on liking the pattern -- defects are the point of a test.

Owner steps: 1) sign in to (or create) the Brambleloop Ravelry account; 2) post OUTREACH.md's title and body as a new thread in the group 'The Testing Pool' (tester-call board); 3) forward replies to the operator, who sends the intake form and records each agreement (quality.tester_programme.record_agreement). Nothing is posted until you confirm. ~20 min, CA$0 (each make's fee is item 2's approval).

## 4. second_market_benchmark -- COMPANY-SELECTED (no owner action)

Decision D-W4-GATESB-1: B-482/B-508: a choice of shop, no credential, no spend; nothing in the Final Master reserves it.

- **LakesideLoops** (CA): Fredericton, New Brunswick, Canada, ~86,500 sales, ~12 yrs; the strongest Canadian crochet-pattern shop found (~86.5k sales, ~19x the next Canadian candidate). Canada is this company's home market and the one #268 most needs separated from the US anchor: same US stitch terms, different holidays (Thanksgiving six weeks apart), CAD pricing. Evidence: web search index snippet of etsy.com/shop/LakesideLoops (2026-10-07).
- **HanJanCrochet** (other): United Kingdom, ~103,768 sales, ~14 yrs; the strongest UK crochet-pattern shop found (~104k sales); covers the 'other' market #268 names, where UK stitch terms make the same words a different fabric. Second because the home market is the larger blind spot. Evidence: web search index snippet of etsy.com/shop/HanJanCrochet; also already cited as a price-band source in radar/market.py (2026-10-07).

Alternates: PippaPatternsCrochet (other, ~84,107), NikByDesign (CA, ~4,500), CrochetPatternHouse (CA, ~2,700).

the weekly intel.panel_discovery cadence verifies each shop via getShop and scans it on the existing credential once this build is deployed; the gate opens on observed listings in a second market.

## 5. owned_surfaces -- Etsy shop recognised; still missing (OWNER ACTION)

Cleared portion: Etsy shop BrambleloopStudio -- production gate etsy_shop open=True (the shop's public identifier is set AND a recorded etsy.probe succeeded -- the identifier alone is a variable, which is not a shop).

- #4: Etsy satisfies nothing: concept tests must never use Etsy listings (fake-listing ban); they need a surface of our own
- #10: Etsy satisfies the paid destination (premium singles/collections are sold on the Etsy shop); the free-content top of the funnel needs a site
- #246: Etsy satisfies the pin landing destination (an Etsy listing URL once a listing is live); posting pins needs a Pinterest business account
- #247: Etsy satisfies the paid product each cluster ends on; the cluster pages need a site (Etsy shop pages cannot host informational content)
- #248: Etsy satisfies listing video slots (per listing, once live); a canonical tutorial and Shorts need a video channel
- #251: Etsy satisfies nothing: Etsy forbids marketing email to buyers from order data; a consented list needs our own signup + sending provider
- #255: Etsy satisfies the product each tool links to; the tools need a site to run on

Missing, each required because:

- **site** (a Brambleloop website on a domain the company controls): hosts free motifs/tutorials/tools, SEO topic clusters and the consented email signup (#4 #10 #247 #251 #255); Etsy shop pages cannot. Step: buy brambleloop domain (registrar of choice) and point it at a static host; the company builds and publishes the pages. CA$25.00 (ESTIMATED: one .com/.ca domain-year; static hosting on a free tier), 20 min.
- **pinterest** (a Pinterest business account for Brambleloop): pins with seasonal lead time and attribution (#246), concept interest tests (#4), free-to-paid funnel entry (#10). Step: create a free Pinterest business account (accepts Pinterest's terms; person-only), then authorise the app. CA$0.00 (free account), 15 min.
- **email** (an email sending provider with a CASL-compliant signup form): welcome/launch/seasonal lifecycle flows to consented subscribers (#251) and the funnel's consented-email step (#10). Step: open a free-tier sending account (accepts its terms, verifies the sender domain and a physical mailing address for CASL). CA$0.00 (free tier up to its subscriber cap), 20 min.
- **video** (a YouTube channel for Brambleloop): canonical technique tutorials and Shorts reused from flagship video modules (#248). Step: create a YouTube brand channel (Google account terms; person-only). CA$0.00 (free), 10 min.

Minimum to open the gate: site or Pinterest whose publish path passes owned_surface.probe.

## 6. customers -- DATA-GATED (buyers), not an owner authorisation

approval_inbox lists it under waiting_on_data, never as an owner card; gate text no longer reads as an owner grant; closure.DATA_GATES. Production fcb982d still showed 'grant real orders' as an owner card (evidence_GATESB/prod_console_owner_cards_fcb982d.json) -- fixed on deploy.
Test: `tests/test_w4_gatesb.py::test_customers_is_data_gated_and_never_an_owner_card`. 29 rows + #242-245 (re-parked from ad_authority: ads.adjust computes them daily; they wait on order data).

## 7. ad_authority -- prepared, NOT YET ASKABLE, no spend

Ready means: the listing exists on Etsy (Listing.etsy_listing_id set) and its state is active; its release is certified (Listing.release_hash set) -- the same release the listing was published from; orders can be read (transactions_r gate open), so CAC and contribution are measured rather than guessed; without it ads would run blind and are not recommended.

Recommendation the day it is ready (build2.gate_clearance.ad_readiness): CA$3.00/day, CA$25.00 per campaign, CA$60.00/month, max test loss CA$25.00, max CAC CA$6.00 (paid_media.CONSERVATIVE_CAPS, already enforced in code).

Structure: one Etsy Ads campaign over the ready listings (max 4), highest net first; Etsy exposes no seller targeting beyond listing choice and daily budget; measured by ads.adjust; organic-first proof (#242) gates scaling. Guardrails: paid_media.authorise_spend; paid_media.should_pause; growth_ops ads.campaign hard refusal while gate closed; SpendLimit('ads') positive unpaused cap.

## 8. live_listings -- company work first

lane W4-PIPE moves the strongest products through the final publication gate (ops.publication_authority evidence); see PRODUCT_INVENTORY on claude/w4-PIPE.
Then: per product with complete publication evidence: approve its sealed 24h publication grant (D-FB-10) and leave shadow for that listing (decision leave_shadow).

