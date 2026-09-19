# BUILD_STATE

_Updated 2026-09-18 by the Brambleloop build session. Maintained continuously so any future
session resumes without rediscovery (Execution Directive step 1, Master Plan section 35)._

## Build 1: COMPLETE
**Accepted as complete by the owner on 2026-09-18**, and checkpointed as a recoverable
baseline before any Build-2 scope begins.

- Baseline commit `d5168c0cea93dde23f06592a36c5a253533b83e5`
- Durable remote checkpoint: branch **`build-1-baseline`** on `origin` (confirmed present)
- Recovery manifest, schema snapshot and production evidence: **`baseline/`**
- 541 tests passing, 0 failing · `/api/verify` 12 of 12 · `/api/launch` blocked on build: NONE
- Decisions B-001 … B-099

None of the seven owner actions has been performed. Etsy is not connected, the phase has not
changed, nothing has been published, no advertising has been bought and no customer activity
exists. See `baseline/BUILD_1_BASELINE.md`, including what the baseline does **not** preserve.

## Build 2: IN PROGRESS — Master Upgrades v1.4.3
The owner's v1.4.3 master is the canonical Build-2 specification
(`spec/08_Brambleloop_Queued_Upgrades_v1.4.3_MASTER.pdf`). All 320 numbered requirements are
audited against the system that actually exists and carried in `src/brambleloop/build2/requirements.json`,
readable live at `/api/build2`.

| status | count | meaning |
|---|---|---|
| covered | 134 | satisfied, with a named test or artefact |
| partial | 71 | something real exists and is short of the requirement |
| missing | 64 | nobody has built it |
| owner_gated | 39 | waits on an owner decision, credential or legal acceptance |
| data_gated | 12 | waits on market evidence that does not exist yet in shadow mode |

Five values rather than two on purpose: "done / not done" is what makes a large build
dishonest, because a requirement waiting on an Etsy shop is not the same kind of unfinished
as one nobody has written. **135 requirements are executable** (partial +
missing); the counts above move as work lands and are regenerated from the registry, never
typed.

Build 1 remains recoverable throughout: baseline commit `d5168c0`, branch `build-1-baseline`.

## Current phase
PHASE 1 — SHADOW MODE, **deployed and running 24/7**. Nothing is connected to live customers,
live listings or live spend. The system runs unattended on Railway whether or not any Claude
session is open.

**`/api/verify` reports `ok: true` in production as of 2026-09-19T04:55Z** — the two
previously dead-lettered cadences (`ops.continuity`, `seasonal.sentinel`) were requeued
on the deployed fixes and both completed, so the standing safety assertions are green
against live state rather than only in tests.

Live: https://brambleloop-os-production.up.railway.app — dashboard `/`, health `/health`,
status `/api/status`, **verification `/api/verify`**.

## Canonical specification
`brambleloop/spec/01_Brambleloop_Master_Plan_v1.2.pdf` (vendored copy of the owner's handoff).
Treat v1.2 as canonical. Improvements become v1.3+ with a preserved changelog — do not
scatter canonical strategy across chat.

## Honest status — what actually exists
Measured by `./run_tests.sh` on the current head: **857 tests passing, 0 failing** across
49 suites, including 23 that assert the owner's acceptance gates line by line. Measured, not
predicted — writing a predicted total on this line has been wrong twice. (Build 1 closed at
541 across 26 suites, at commit `d5168c0`.)

Suites: CIR engine (including row-level repeats and round-worked geometry), platform, release gates, market radar, model gateway, brand and
storefront, commerce (pricing, search, thumbnail, paid media), departments (support, content,
portfolio), quality (confidence, regression), finance, shadow pipeline, real-process
persistence, chaos, deployment surface, flagship run and adversarial attacks, generated
catalogue, accessibility, and the acceptance gates.
- The full release chain runs end to end with no human in the loop, and correctly *refuses*
  to publish in shadow mode. A single `plan.cycle` now carries an entire 11-SKU portfolio
  from market scan to eleven release certificates without intervention.
- Persistence is **proven, not assumed**: a worker is SIGKILLed mid-job against a file-backed
  database and a fresh process recovers and completes the work, inputs intact, with no
  duplicate side effects.
- Cloud deployment: **live and verified.** See "Deployment" below for the exact
  configuration, the twelve production checks that pass, and the measured cost.
- Catalogue: **19 engineered designs** — 11 generated from the motif library
  (`products/builder.py`) and 8 hand-built: the flagship mosaic throw, the basket in three
  measured sizes, the hexagon coaster, the cable throw, the bobble pillow and the ribbed
  scarf. The last six are the products whose names made claims their fabric did not honour,
  rebuilt rather than renamed (B-061, B-082). Every one compiles, reverse-compiles and
  certifies. Ten of the eleven release candidates ship an engineered design; the eleventh is
  the collection bundle, which correctly has no pattern of its own.
- **Construction beyond flat rows now exists.** Pieces worked in the round are measured as a
  surface of revolution, so a coaster, a tube, a cone and a basket get real finished sizes,
  a closed shaped piece gets a circumference and an explicit refusal to state a height, and
  fabric that must gather is named. Charts for round work are drawn as rounds. Two catalogue
  products were named for shapes their patterns did not make and are rebuilt (see the
  milestone below).
- Storefront, listings, imagery and content: **drafted and held.** Production at
  2026-09-18T08:40Z, after the chain-7 rebuild, holds 15 certified patterns, 16 listings all
  built by the current chain, 94 listing images with **all 94 approved**, 134 content pieces
  and 1 collection — none of it published, against 120 recorded publication refusals.
  Nothing in this system can publish: there is no Etsy, Pinterest, email, video or messaging
  integration at all.
- The chain-7 rebuild re-derived every product's imagery under the **armed** Asset Truth
  gate (B-098), which until this morning could not block anything: 15 restarted, 15 images
  built, **0 blocked**. That is the evidence that the defect was latent rather than a claim
  that it was.
- **Nothing in the launch report is blocked on build.** `/api/launch` reports every
  build-owned requirement satisfied; the eight unmet ones wait on the owner (seven) or on an
  Etsy credential that only the shop can produce.
- Etsy publishing: **code written and wired, never called.** `store.publish` asks the client
  past shadow mode, and the client's own three refusals stand in front of it, so the phase is
  the first of four conditions rather than the only one. A listing records the Etsy listing
  it became, so publishing twice cannot create two. The client exists, is unit-tested and
  refuses on phase, on owner authority and on missing credentials, in that order. Nothing in
  this environment can satisfy any of the three. "Written" is not "connected" and the
  readiness report still reports the integration as absent.
- Model providers: **none configured.** The Model Gateway is built and tested, but no API
  key exists in this environment, so `available_providers()` returns an empty list and the
  dashboard says "none". Nothing in the pipeline currently calls a model: every load-bearing
  step is deterministic code.
- Object storage: **none.** Rendered PDFs and charts are written to local disk, which is
  ephemeral in a container. The system knows this: artifact *hashes* are stored in Postgres
  and survive, the bytes may not, and `assets.storage_not_durable` is audited on every run.
- Etsy shop, listings, customers, revenue, ad spend: **none, CA$0, zero.**
- Market Radar now runs on **real observed competitor intelligence** (five seeded shops,
  dated 2026-09-17, with price bands, discount patterns, format signals and named gaps) and a
  **34-concept opportunity pool across 23 categories**. No live scraping integration exists;
  observations are point-in-time and carry their observation date so they cannot silently rot.

## Heartbeat 2026-09-18T16:14Z — both fixed cadences proved in production

`/api/verify` reads **11 of 12**. The failing check is
`no_unexpected_dead_letters_in_24h`, and it is **correct to be red**: it is counting two dead
letters from this morning, both from defects that are now fixed and deployed. The check is not
being softened — a dead letter that has been fixed is still a dead letter that happened, and
the window clears itself by 2026-09-19T15:00Z.

Both fixes are proved against production rather than asserted:

| cadence | proof |
|---|---|
| `ops.continuity` | ran at 14:52Z against live Postgres — **4,304 rows, 25 tables, 4,027 non-rederivable**, restored and digests matched |
| `seasonal.sentinel` | ran at 16:2xZ on commit `f07e4bf` — **done, 1 attempt**, 15 products scheduled, and it raised the P2 it was supposed to |

`POST /api/seasonal/recompute` was added to make that provable now rather than at midnight,
with an optional `as_of` for asking what the room looked like on a given day.

### What the war room actually says about this company

Measured against the 15 certified patterns in production, not a fixture:

- **Christmas: all 15 on track.** The four blankets have preferred launch dates of
  **27 September – 3 October** — nine to fifteen days away — and last viable dates of
  21–27 October.
- **Canadian Thanksgiving (12 Oct): missed for all 15.** Recommendations are `hold_for_next_cycle`
  for the blankets and `pivot_to_evergreen` for the quick makes.
- **Halloween: nine products at risk, and the runway is days.** `market-basket-trio` is at
  **zero days**; `spooky-garland` — a product whose entire premise is Halloween — has its last
  viable launch date on **2026-09-25, seven days away**.

None of it can be acted on, because nothing can be published without a shop. That does not
change the owner-action list; it puts dates on it. Every figure above is labelled `assumed`:
no completed physical test has reported hours, so the stitch rate the make-times divide by is
still a guess.

631 tests passing, 0 failing, 33 suites. Shadow Mode intact, CA$0 revenue, CA$0 model spend,
1 open incident (the Halloween P2, correctly raised).

## Last completed milestone
**The build loop moved out of the conversation and into Postgres (#195, #196, and the master
intent's Autonomous Build Executor).**

Build 2 *did* route around the missing Etsy credential — eight milestones landed while it was
unavailable and no requirement waited on it. But the thing doing the routing was a session.
The dependency graph was prose in this file, the priority queue was judgement, and the parking
decision was made once and remembered by whoever was in the conversation. All of that
evaporates when the session does, and the failure is invisible until the moment it matters.
**Autonomy that depends on a particular process staying alive is not autonomy.**

- **The graph, the queue and the parking state are rows.** `build_tasks` and `build_events` in
  Postgres, reconciled hourly by a `build.tick` cadence in the deployed worker. A claim
  carries a 90-minute lease, so a session that dies mid-requirement loses a worker rather than
  the build — another one takes it over with nobody noticing that intervention was needed.
- **Parking is checkable or it is refused.** Seven owner gates, each with a condition the code
  can *test*, and `sync()` refuses an owner-gated requirement that has no gate. That refusal
  is the load-bearing half: without it, such a requirement falls into the ready list as work
  nobody can do and the queue reports more ready work than exists — the one number the whole
  module is for. Free text would make parking a place to put anything difficult, and a queue
  that can absorb its own difficulties never reports being blocked and never finishes.
- **Two of the seven gates check rows, not environment variables.** Benchmark purchases is a
  `BenchmarkProduct` count; advertising authority is a `SpendLimit` with a positive cap. The
  question a gate asks is "is this true yet", not "is there a credential".
- **Un-parking is automatic.** A gate opens, its requirements go ready, and nothing had to
  remember. Setting `ETSY_SHOP_ID` un-parks four; a browser endpoint un-parks sixteen.
- **Never-idle is measured in completions, not ticks.** A loop that always has something to do
  can invent work. The watchdog distinguishes idle-with-ready-work (a stall, raises an
  incident) from idle-with-everything-parked (correct, raises nothing) — opposite situations
  that look identical from outside.
- **#196: the owner inbox is asynchronous by construction.** Seven cards with what, why,
  capability, maximum spend, risk, rollback and consequence of waiting, sorted free-and-quick
  first. An inbox is only asynchronous if the queue behind it does not wait, and that property
  lives in `sync()` rather than in the card layout.
- **#195: the off-device proof** counts five things and requires all of them — jobs completed,
  distinct job types, completions *spread across* the window, scheduler activity, and no
  unexpected dead letters. Because *"online" means useful work is progressing, not that HTTP
  returns 200* (#185), and a container answering health checks with a stalled queue passes
  every naive uptime monitor ever written.

### Two defects this surfaced

**Four requirements the registry called executable cannot be built without a credential**
(#177, #178, #221, #222). The gate validator refused them as ungated, which is exactly what it
is for. Registry reconciled; ready count and executable count now agree by construction, with
a test asserting it.

**`/api/build2` had been returning 500 in production for as long as it existed.** The registry
JSON sat at the repository root and the Dockerfile copies `src`, so it was never in the
container — passing every local test the whole time. The file now lives inside the package, so
it travels by construction. The more valuable fix is the general guard: a test that walks the
app's declared GET routes and calls every one, so a new endpoint is covered the moment it is
registered rather than when somebody remembers to list it.

## Previously in Build 2
**Cells to generate against, and a real finding about Christmas 2026 (#105, #113, #114,
#117-#123, #132).**

One idea runs through all of it: *generate against explicit cells and measure the cells*,
because the alternative is generating against a keyword and measuring a count. "Christmas
crochet patterns" produces what the phrase suggests. The same December contains a mantel
stocking, a teacher gift under fifteen dollars, a nursery keepsake somebody keeps for thirty
years, a table setting and a front door — different products for different people, and a
catalogue ends up with six variations on a blanket because nothing ever asked which cell each
one was for. **Six products against 288 cells reads as six products.**

- **Sixteen Christmas departments × eighteen contexts (#105, #113).** The contexts are people
  *and* places — "a teacher" and "the front door" are both cells somebody shops for, and
  neither is reachable from a keyword.
- **Skill level is segmentation, not difficulty (#114).** A wave of only flagships has no
  beginner entry and no impulse purchase; one of only quick makes has nothing anybody keeps.
  Both look busy.
- **Diversity is measured per axis (#119),** because twelve concepts sharing one construction
  have explored one construction, and twelve is exactly the number that makes it look like
  exploration.
- **A crowded archetype needs a named unmet angle first (#117).** Forty near-interchangeable
  pumpkin coasters is evidence the archetype sells *and* evidence the forty-first is invisible;
  only the second reading has arithmetic behind it. The refusal names the number, because
  "ours will be nicer" is what everybody entering a crowded category believes — including the
  forty already there.
- **White space is mined from complaints (#118).** A buyer saying what went wrong is a brief
  with a customer attached, which no search-volume report is. With nothing recorded the agent
  says so rather than proposing from the category, which is how a white-space agent
  rediscovers the commodity and reports it as discovery.
- **The mechanism transfers between seasons; the theme does not (#120)** — the distinction
  that collapses first under a deadline, because the finished design is right there.
- **Four-season programs and non-holiday occasions (#121, #122),** because a shop that only
  sells in December is closed for eleven months and calls it seasonality.

### A finding, not a feature

The collection calendar (#123) holds ten dated milestones per occasion. **Run today against
Christmas 2026, five of the ten are already past** — research start, concept freeze,
engineering start, physical-test deadline and creative-production deadline — with
listing/indexing due **2026-09-26, one week away**. A missed date is a portfolio failure
rather than an amber row, and the failure is silent: a phase that slips does not announce
itself, it becomes the next phase, and the first visible symptom is a product that lists in
December.

### What the calendar actually permits, computed 2026-09-19

Not a worry — the engines now answer it. Heaviest lane a customer could still finish, and
milestones already past:

| event | days out | heaviest lane still launchable | milestones past |
|---|---:|---|---|
| Christmas | 97 | **MEDIUM** | 5/10 |
| Halloween | 42 | QUICK | 8/10 |
| Thanksgiving (CA) | 23 | **none** | 8/10 |
| Valentine's | 148 | LONG | 4/10 |
| Easter | 197 | LONG | 3/10 |
| Mother's Day | 233 | **FLAGSHIP** | 2/10 |

Christmas 2026 by lane, as latest effective launch date:

| lane | up to | latest launch | from today |
|---|---:|---|---:|
| QUICK | 6h | 2026-11-15 | +57 days |
| SHORT | 20h | 2026-10-30 | +41 days |
| MEDIUM | 45h | 2026-10-03 | **+14 days** |
| LONG | 90h | 2026-08-12 | −38 days |
| FLAGSHIP | 150h | 2026-06-06 | −105 days |

**The prioritisation decision, made here rather than referred upward.** Christmas 2026 is a
QUICK and SHORT season for this company; MEDIUM is available only for something that can be
engineered inside the next two weeks, and LONG and FLAGSHIP Christmas work is arithmetically
impossible — a customer could not finish it. Thanksgiving (CA) is gone. **Flagship effort
belongs to Mother's Day 2027** (233 days, every lane open, 2 milestones past) and to the
four-season programs that do not wait for a date. That is what the concept queue should be
pointed at, and it is a consequence of the calendar rather than a preference.

The calendar is checked by the **daily `seasonal.sentinel` cadence**, not by somebody opening
a page: a function nobody calls produces that finding once and never again. Run against
today's state it finds **every** seasonal event behind — Halloween worst at 8 of 10 — which is
the honest state of a company that has never run a collection calendar. One incident for the
worst-affected event, because eight rows about one Christmas is the noise that trains
everybody to close the channel.

#132 is **partial**: all eleven north-star metrics are tracked by cohort, with the four that
need no customers separated from the seven that do — a dashboard showing four numbers and
seven blanks is read as four numbers.

## Previously in Build 2
**The creativity defect the owner named, addressed at the brief rather than at the gate
(#106-#110, #115, #124, #125, #127, #129).**

The defect is measured, not asserted: `creative/audit.py` compiles all eleven catalogue
products and finds one component shape, one construction and two stitches. That is not a taste
failure. It is a generator with one degree of freedom being asked for variety and answering
with colour — and **no validator fixes it**, because given a season and a category the
highest-probability output *is* the commodity. The commodity is what the category is made of.
A validator can only reject what arrives.

So all of this acts on the brief:

- **Two dimensions that do not normally co-occur (#106).** Motif × function, holiday × storage,
  tableware × character. One dimension is a category, and a category is what everybody else is
  already making. Two near-synonyms are the same failure with two names — storage crossed with
  organization reads like a combination and is one idea stated twice, which is exactly what a
  system under pressure to produce pairings emits.
- **Abstract transformation patterns, never a seller's expression (#107).** Becomes a set,
  nests, unfolds, stacks into a scene, inverts, reveals. A description that names a specific
  product is refused by the same content boundary the teardown library uses.
- **The silhouette gate enforces #108's own sentence literally.** "A concept that needs its
  title to explain why it is interesting is weak" is unenforceable while the two are read
  together, because the title supplies the interest and nobody can tell which half carried it.
  The premise is read with the title's words deleted: *"Gingerbread Village Basket"* /
  *"a gingerbread village basket"* leaves nothing.
- **The emotional promise names what delivers it (#109).** "Cosy" achieved by writing *cosy*
  in the listing is the failure the requirement names, and the cheapest way to satisfy any
  check that reads text. The promise must survive a buyer looking at the photograph with the
  sound off.
- **A motif grammar with its clichés marked (#110).** 10–20 motifs per season; a selection
  built only from the saturated set is reported as the commodity by construction.
- **A flagship's WOW mechanism must be grounded in the object (#115).** Naming one from a
  closed list is half; requiring four specific words about *this* object is the half that stops
  "it has a reveal" counting. A checkbox is what a generator learns to tick.
- **The floor is the trailing median, with an absolute floor underneath (#124).** A fixed
  threshold is one the company grows past and keeps meeting — the bar that rejected two thirds
  now rejects none, and the improving pass rate looks like success. A trailing median alone has
  the mirror failure, so the absolute floor sits below it.
- **Flagships aim at the top decile (#125), and boring is a verdict (#129).** #129's most
  important sentence is that agents must be able to reject technically valid ideas: every other
  gate here is a correctness gate, and the correctness score is *precisely* what a boring
  concept passes. A taste rejection is a closed vocabulary with no numeric content and it ends
  the question.
- **Rejection reasons are closed, or forty autopsies have forty reasons (#127).** Five of six
  rejections being "obvious" is a brief problem rather than six concept problems, and it is
  invisible under free text.

`GET /api/invention` reports the machinery and the measured defect side by side.

## Previously in Build 2
**CA$3,000 as arithmetic, and the metric everyone optimises instead (#24, #25, #27, #28, #31).**

A revenue target is a wish until it is a funnel, and the useful part of writing it as one is
not the number at the end. It is that only one term is ever binding, and the company almost
always works on a different one — because the binding term is usually the one nobody owns, and
the term under our hand is always the listing.

- **Contribution per visitor, not conversion rate (#24).** A CA$25 pattern converting at 1.6%
  beats a CA$12 pattern at 2.5%, and the second listing looks healthier on every dashboard.
  Conversion is a ratio whose denominator the company is also buying. The ranking function
  reports explicitly when the two orderings **disagree**, because that disagreement is the
  requirement rather than a footnote to it.
- **The target at four prices is four companies (#25).** 200 × CA$15, 150 × CA$20, 120 × CA$25
  — shown together so the price decision is visible as a decision instead of implicit in
  whichever number was written down first. Required visits are derived **only** from an
  observed conversion rate: the category benchmark is available, plausible, would complete the
  funnel, and would produce a confident plan about a company that does not exist.
- **The constraint is one term, walked in funnel order (#25, #28).** A test caught the first
  implementation contradicting its own stated principle: a listing with 100,000 impressions
  and 200 visits satisfies "strong conversion, low traffic", and buying more impressions when
  99.8% of them bounce is buying more of a broken funnel. The CTR check now precedes the
  traffic check. Rising defects outrank every commercial term — scaling a defect multiplies it.
- **#27's conditions sit beside the counts, and silence is not neutral.** Counts and conditions
  fail differently: volume arrives from one lucky listing. A shop with sixty orders from a
  single viral outlier, a negative contribution margin and an open policy warning satisfies
  **every count** in the gate and **none** of the eight conditions. An undeclared condition is
  unmet rather than unknown, because treating silence as neutral is the cheapest way to pass
  any gate.
- **An artefact produced by uncosted work is a floor, not a price (#31).** The averaging
  instinct spreads unattributed spend across the artefacts, which makes every unit cost look
  plausible. Free is the most dangerous price, so the uncosted producer count is reported per
  artefact and unattributed spend is its own number. Both of #31's ratios are reported even
  when one side is zero — `burning: true` today, with CA$0 earned.

`GET /api/runrate`. Honest gap: #31 is **partial** — per-artefact attribution needs cost
entries carrying job ids, which most handlers do not yet record.

## Previously in Build 2
**Four ways an autonomous system flatters itself, closed (#49, #52, #53, #55).**

None of these is a bug. Each is what a system does when nothing stops it: one that measures its
own throughput optimises throughput, because throughput is the thing it can move without
anybody's permission. One with cash in the account finds a use for it, because the obvious use
is more of whatever produced it. One that reviews itself weekly adds work, because removing
work is nobody's job. And one reporting confidence as a single number reports zero for a year
while a great deal is built, which teaches its owner to stop reading it.

- **Revenue does not automatically become ad budget (#49).** Four reserves filled in order —
  tax (never yours), operating floor, cash reserve, then whatever is spare. The
  *recommendation* is the envelope scaled by the modelled confidence, so a company with
  CA$20,000 in the account and no customers recommends **nothing**: cash from an unrepeatable
  source is not evidence that spending will repeat it. Confidence is read from the ladder
  rather than accepted as an argument. **No code path returns `owner_approval_required:
  False`** — an authority boundary in a docstring is one the next change forgets, and small
  amounts are how standing budgets start.
- **There is no function that returns a release count alone (#52).** The four companions —
  defect rate, support burden, conversion, contribution — travel with it structurally rather
  than presentationally, and a faster week where any of them degrades is reported as
  *degraded*. Writing it surfaced a real hole: the percentage-change guard skipped every
  metric whose previous value was zero, dropping the single most important movement it can
  see — a defect rate going from none to some.
- **A review that stops nothing has to say why (#53).** Not blocked: a hard requirement to
  stop something weekly manufactures removals, which is worse than the bureaucracy it
  prevents. But a silent empty list is exactly what a bureaucracy reports, every week, for
  years. One sentence costs a lean week nothing and makes an accumulating one visible. Five
  categories, because an experiment that will not conclude is a different problem from a
  cadence costing more than it returns.
- **The ladder opens with an architecture rung that is earned and moves nothing (#55).** A
  ladder whose every rung reads 0.00 shows no stages at all. Architecture is the layer this
  company *can* honestly earn — derived from rows: a certified pattern, a proved restore, a
  refused publish, completed work, no accumulating dead letters — and it is non-critical, so
  earning it does not move the modelled probability by a point. Progress is visible and is not
  convertible into confidence about revenue. CA$3,000 and CA$5,000 are now computed as
  separate questions and today give the same answer: **a smaller target is not a nearer one
  when nothing has been sold.**

`GET /api/discipline` reports all four together.

## Previously in Build 2
**Price memory, control cohorts and bundle attribution: three names for one mistake
(#45, #46, #47, #48).**

The mistake is *something changed, sales moved, therefore the thing that changed caused it*.
It is not carelessness — every version of it is locally reasonable, and every version makes a
dashboard improve, which is why none of them is caught by looking at the dashboard.

- **A comparison across a confounder is refused, not flagged (#46).** The price dropped in
  November and sales rose; it was December that rose. Season, traffic source, category and
  sale state are *columns*, because "was this price or was it December" has to be a filter and
  a note cannot be filtered on. Refusing rather than warning is deliberate: a warning is read
  by the person who wrote it and by nobody afterwards, and the number travels on alone.
- **An unmeasured elasticity is unmeasured, never zero.** Zero is not the absence of a claim;
  it is the claim that price does not matter, and it is what the obvious default would have
  said. This company has no sales, so everything here reports that.
- **Incrementality is measured against what the control predicts (#48).** Counting the
  control's own performance as a result of the spend makes every ad budget look self-funding.
  With one arm it cannot be done at all: a conversion rate measured on paid traffic is a
  statement about *who was shown the listing*, and scaling on it buys more of that audience
  and none of the improvement.
- **A bundle is judged on contribution, and not at all without a pre-bundle baseline (#45).**
  The failure is not that the bundle fails — it is that it succeeds with buyers who were
  already ours and used to buy the higher-margin thing beside it. Both halves are true at
  once, so nothing looks wrong: units rise, the catalogue looks broader, contribution is flat.
  Revenue is the metric that hides it, so the amplification check is separate and explicit
  rather than one number among nine that all went up. An incremental bundle still names what
  it displaced instead of netting it away.
- **#47's missing rung (#47).** The restored lifecycle classifier already ran four of the
  five stages; the gap was **clicks with no saves**, which is the product failing to appeal,
  versus **saves with no orders**, which is the offer. The two look identical in every
  aggregate and the interventions are opposite — reworking price and trust on a product
  nobody wanted produces a cheaper version of something nobody wants. Checked *before* the
  conversion stage so the cheaper diagnosis cannot claim the case first.

One test hardening came out of it: the ladder-coverage test enumerated classes by hand, so a
new class with no intervention ladder would have passed. It now derives from the module.

`GET /api/commercial` reports the price memory and names the confounders that are refused.

## Previously in Build 2
**Etsy's rules as a dated snapshot, the AI-disclosure gate, and customer-use terms decided
once (#35, #39, #40).**

Three requirements that look like paperwork and are the ones that close a shop. They share a
shape: each fails silently and in the future. A policy encoded in code is true the day it is
written; a generated lifestyle image is a compliance problem only once somebody complains; and
terms that were never decided are correct until the first customer asks the question they
actually have.

- **A platform policy is a dated snapshot, not a constant (#39).** Five surfaces watched
  separately — seller policy, creativity standards, listing-image rules, advertising rules,
  shilling and reviews — because each blocks a different workflow and one "Etsy policy" blob
  blocks everything or nothing. **Never checked and unchanged are opposite states**: an
  unread source blocks the workflows it governs, and a watch that reported "no material
  changes" from an empty table would be the most confident possible way to be wrong. A
  material change is a **digest difference rather than a judgement**, so the question reaching
  a person is "this changed, does it matter" instead of "has anything changed" — a much better
  question to be asked while tired.
- **The release certificate now records which reading of Etsy's rules it was issued under.**
  `POLICY_VERSION` answers which version of *our* rules; the new stamp answers the one that
  changes without telling us, and a certificate that cannot name it cannot be re-examined
  after the platform moves.
- **A label does not convert misrepresentation into disclosure (#35).** Asset roles carry a
  requirement — photograph, or generated-permitted — and a generated image in a role that makes
  a claim about the finished object is refused however carefully it is labelled. An AI render
  of a finished blanket is a picture of a blanket that does not exist, and the buyer is looking
  at it precisely to find out what they are buying. A deterministic render of our own chart is
  the exception: it *is* the artefact being sold.
- **Enabling a new product or asset class against an unread policy is refused**, which is #35
  read literally: a new class is exactly when the old reading is least likely to cover the case.
- **Customer-use terms are five deliberate choices, rendered once (#40).** Closed options, so
  "do not redistribute" cannot arrive by inheritance while the question customers actually ask
  — may I sell what I make at a craft fair? — gets answered for the first time in a support
  reply. PDF, listing and FAQ render from one decision and a consistency check refuses
  divergence, because writing them three times is the only way this drifts. **Decided is not
  enforceable**: the rendered PDF says the terms have not been through legal review, and
  `enforceable` stays False until a named reviewer and scope are recorded.

`GET /api/policy` shows the freshness answer first. A daily `ops.policy_watch` cadence opens
one blocking incident per stale or unread source; it deliberately **does not fetch**, because
no policy reader is connected and a cadence that fails every run on an absent dependency is a
dead letter with a schedule — a mistake this build has already made twice.

Honest gap: #39 is **partial**. Snapshots are recorded rather than retrieved, so today every
source reads as never checked and the watch is correctly blocking. Connecting a reader, or the
owner recording a snapshot by hand, is what closes it.

## Previously in Build 2
**The Culture & Nostalgia opportunity engine, rights gate first (#133-#147).**

Fifteen requirements, nothing built, and the reason to build the gate before the radar is that
a culture radar is the most dangerous thing a pattern company can own. The danger does not
arrive as a decision. It arrives as a gradient: the radar optimises for demand, the strongest
demand signals are all somebody's property, each step downstream receives a slightly more
abstract description of the same protected thing, and it reaches production having been
refused by nobody. Nobody chose it.

`culture/rights.py` exists before the radar that would feed it, the same order the benchmark
quarantine was built in:

- **Unclear rights route to the original lane, never to a refusal (#135).** Killing an
  opportunity because its obvious execution is protected teaches every downstream step that
  the gate is an obstacle, and a gate people argue with eventually loses one. The original
  lane is a turning, and the turning is where a product this company *owns* comes from.
- **Decomposition is checked, not trusted (#134).** The protected element is the most salient
  thing in the input, so it is exactly what survives a judgement call — "the warmth of
  watching <character>" is a sincere attempt at an emotion primitive and it is the
  infringement intact. Word-boundary matching, because a check that fires on "art" inside
  "heart" is one everybody learns to route around.
- **The public-domain screen refuses to do arithmetic it should not do (#135).** Term depends
  on authorship, work type, renewal and jurisdiction. The screen passes only works published
  before **1900**, records that passing is not clearance, and sends everything else to the
  original lane or to the owner.
- **Quotes, lyrics, slogans and catchphrases are their own class (#139)** — the class that
  feels most free and is not — and a final check catches one reaching customer-facing copy
  through the original lane, because a concept can pick up a token anywhere in the middle.

On top of that gate: the ten translation primitives (#134); nine reusable **eras** and ten
franchise-free **themes** (#137, #142) that recur annually and that nobody can withdraw in
January — 19 territories this company owns outright, counted, because a dependence nobody
measures is one nobody notices growing (#146); a white-space tournament measuring **families
and distinct premises rather than a count** (#138), since fifteen ideas in two families is one
idea in fifteen colours and the jury cannot see that reading concepts one at a time; the
six-role collection architecture (#143); the eleven-component opportunity score where **rights
feasibility and the make-time window are gates rather than weights** (#136) — five out of five
everywhere and zero on rights is not a four; signal memory with sources, exit reasons and
lessons, carried in the continuity export as non-rederivable (#144); the lead-lag model that
names the case where the radar is *reporting the news* (#140); a four-condition saturation
exit where any one is sufficient and unmeasured conversion is not failure (#145); the
rapid-response cell as two closed lists rather than a principle (#141); and culture lessons
routed to creativity, market radar, SEO and portfolio (#147).

`GET /api/culture` reports the rights routing first and unconditionally, because it is the
part that stops this becoming a legal problem and it is invisible in every other view. With no
feed connected the radar says **it has no source** rather than reporting no trends: an empty
trend list is indistinguishable from a world with no culture in it, and the second reading is
the one an absent owner would take.

Honest gaps: #133 and #140 are **partial** — the machinery is built and there is no connected
search or marketplace feed, so the lead-lag model has one series where it needs two. #146 is
partial: the borrowed/owned split is countable, and recurring Brambleloop characters and
collection worlds are not built. #147 is partial: outcomes updating the scoring weights needs
launch data that does not exist.

## Previously in Build 2
**The Competitive Product Teardown Laboratory, finished — and three regressions it exposed
(#152-#160, #164, #168).**

The laboratory had a twelve-dimension scorecard and no way to earn a score. "Chart quality: 4"
is a feeling with a number attached; #154 asks about legibility, symbols, legends, colour
independence, pagination, row numbering, motif boundaries, print quality, scale, schematics,
assembly diagrams and written correspondence. Twelve things a person can look at and disagree
about. `teardown/audits.py` is the nine schedules the requirements enumerate — **92 elements
across nine audits** — and four rules that keep them evidence rather than impressions:

- **An audit is complete or it is not scored.** Scoring five of twelve chart elements and
  reporting the mean would let a shallow teardown outrank a thorough one.
- **Only the extremes owe a mechanism.** A 3 is "competent" and teaches nothing. A 4 or 5 is a
  mechanism worth adopting and a 0-2 is a trap worth preventing, and both must say what
  produced them. Demanding an essay for all 92 elements is how ten purchases become a task
  nobody finishes.
- **A strength with no answer is reported, not converted.** A benchmark element scoring 4 or 5
  becomes a Brambleloop publishing requirement only when an advantage this company can
  *evidence* beats it. Otherwise it is recorded as an **unmatched strength** — a competitor
  does something we have no answer to, which is the most useful thing a teardown can find and
  the first thing an invented differentiator would destroy.
- **The requirement is to exceed, never to match.** #154 says clearer charts than the best
  benchmark and #156 says the best purchased experience rather than the average; parity is the
  floor #163 already refuses.

Video applies only where the manifest records video: a pattern that never promised video does
not have bad video, and scoring it zero manufactures a weakness out of a category difference.
Delivery packaging is half answered from the intake manifest, so the analyst answers only what
filenames cannot settle. Every free-text field still goes through `check_derived()`, so a
mechanism that is really the competitor's instructions is refused at the new door too.

**#164 is now a pipeline rather than a convention.** `teardown/pipeline.promote()` routes a
finding through `improve.cells.propose`, so the pre-change baseline and the governance
boundary both apply unchanged — and "relax the claim gates so our listings can state the same
size range as theirs" is refused by the same rule that refuses it anywhere else. A competitor
doing something this company is not allowed to do is a finding about the competitor. The
funnel counts **measured improvements, not filed findings**: a finding that became a
hypothesis nobody tested has changed nothing.

**#168 is a gate, not a report.** The pre-launch challenge compares a product against the best
category-matched benchmark on seven critical dimensions, blocks on a full-point gap unless a
tradeoff was declared *and* names an advantage we can evidence, and refuses to pass a critical
dimension by leaving it unscored. It is carried in `launch/readiness.py` as a real requirement
with an owner request attached. An unrun challenge is **not** a pass — it currently blocks,
and the unblock path is the owner's benchmark purchases.

### Three regressions this work exposed, all fixed

Running the full suite found four failing suites. All three defects were real, and one was
mine:

- **`growth/portfolio.py` had been overwritten, not extended.** The CA$5K portfolio-mix work
  replaced a Build-1 module that `runtime/pipeline.py` imports, so the weekly `portfolio.review`
  cadence would have dead-lettered on its next run. It had **not** yet done so in production —
  `/api/verify` records two historical dead letters, neither of them this one — because the
  cadence is weekly and the guard test caught it first. The lifecycle classifier is restored and the
  new mix/concentration/stress-test code now lives in `growth/mix.py`. They answer different
  questions — how a SKU is *performing* versus what the catalogue is *shaped* like — and a
  catalogue of twelve healthy stars with one role is a portfolio one trend away from zero.
- **A continuity export cut exactly on a table boundary restored as if complete.** Every table
  it contained was internally consistent, so every per-table row count agreed and the operator
  was told the restore succeeded. The header now declares which tables the file will contain
  and the file carries an end marker; a restore missing either is refused.
- **`/api/verify` returned 500 instead of 503 whenever there was a dead letter to report.**
  `cutoff` is timezone-aware, SQLite returns naive datetimes, and the comparison only runs when
  the dead-letter list is non-empty — so the endpoint an absent owner relies on was green in
  every state where nobody needed it and opaque in the one where they did. Fixed, with a test
  that plants a dead letter, because the existing tests all passed while the defect was live.

## Previously in Build 2
**The benchmark observation pipeline — written while the credential does not exist, so it runs
the moment it does (#207, #208, #212, #214, #303, #313, #319).**

The pieces already existed: the read-only Etsy client, the pods, the coverage queue, the
evidence grading. What was missing was the thing that drives them on a schedule. It is
deliberately written *before* the key arrives, because a pipeline written the day the key
lands is a pipeline debugged against a live marketplace. Every branch — first baseline,
unchanged catalogue, new listing, changed listing, unreadable gallery, no credential at all —
is exercised against an injected reader.

- **Baseline once, then only what moved (#212).** Each listing carries a content fingerprint
  over the fields that change *commercially* — title, description, price, tags, materials,
  state, last-modified, favourites. `views` is deliberately excluded: a field that moves every
  hour makes a fingerprint useless by making it always different. The second scan of an
  unchanged catalogue opens **zero** galleries, and the test asserts that by counting calls,
  because the rows look identical either way.
- **An audit is only claimed after it happened.** `audit_state` becomes `audited` after the
  gallery call returns, never from a catalogue row.
- **The gallery result is called an inventory, not an analysis.** Etsy publishes per-image
  hex, hue, saturation and brightness, so palette evidence is free — and nothing in the record
  claims a judgement about the shot was made, because that needs the model provider.
- **A scan's purpose is a queue, not a report (#314).** Arenas the benchmark sells into and
  Brambleloop does not become scored coverage gaps, using only components the scan can
  actually observe. Make time, contribution and creative potential are left **absent rather
  than guessed**, so the queue's own `evidence_weight` reads under 0.4 and says so.
- **#319 is enforced inside the pipeline**, not beside it: `mission.check_report()` runs
  against the scan's own output, so a scan that could not produce a compliant report fails
  rather than files one.
- **No credential is not an empty catalogue.** The easy implementation returns zero listings,
  which is indistinguishable from a shop that has none. This records that no observation was
  performed, names the six requirements that stay unmet, and states that nothing was
  substituted.

Six-hourly cadence, `POST /api/mjs/scan` to run it now. The interval is fixed and chosen to be
cheap; cadence that adapts to the shop's own posting behaviour (#313) is still to build, and
is recorded as partial rather than claimed.

## Previously in Build 2
**A second cadence died on its first production run, and the guard that would have caught
both.**

`seasonal.sentinel` dead-lettered three times: it constructed an `Incident` with a `title`
keyword that model does not have. The test I had written for it passed — **vacuously**. It
asserted over an empty incident list, because on the day it ran nothing in the fixture
happened to be at risk, so the branch that raises was never entered.

Two fixes, and the second matters more:

1. The handler builds the `Incident` correctly, with `summary`, `product_slug` and
   `halts_publication=False` — a timing risk must never halt publication.
2. The test now picks a date five days inside a real product's at-risk window and asserts
   **exactly one** incident with the slug, the runway and the severity. The handler takes an
   `as_of` input, which also lets an operator ask what the war room looked like on any day.

And the general guard: `test_every_scheduled_cadence_survives_actually_being_run` enqueues
every cadence against a seeded database and asserts none dead-letters. The existing test
proved each cadence had an agent and a handler — wiring — and both of this session's
production defects were handlers that could not survive their own first run, which no wiring
check can see. It excludes exactly one kind of dead letter: the shadow-mode publication
refusal, which is Gate F working, and which it asserts *must* be present.

## Previously in Build 2
**The CA$5,000/month model, built so it cannot flatter the company (#229, #230, #269, #270,
#273, #274, #275).**

The owner's framing is the specification: the probability must be *earned from actual market
evidence, not manufactured from optimistic assumptions*. That rules out the obvious
implementation — a weighted score over criteria somebody fills in produces a number that rises
as the architecture gets more sophisticated, which is precisely what #230 forbids.

**Against this company's real state today, `/api/scale` reports a probability of 0.0**, and
says: *"Effectively zero, and correctly so… No amount of further building moves this number —
only customers do."* Fifteen certified patterns, a deterministic compiler, a reverse compiler,
release gates, a benchmark mission and a seasonal engine, and not one customer.

Four properties, each a thing that *cannot* be done rather than a thing that should not:

- **Every rung counts rows.** No parameter sets a layer; no override exists.
- **Everything measured from orders is bounded by the ledger's order count.** This closes the
  hole every scoring model has: several rungs need counts from systems that do not exist yet
  (attribution, repeat tracking), and a caller supplying those could otherwise report a
  perfectly diversified, highly converting business into a database holding no sales. Tested
  adversarially with maximal fabricated inputs: still 0.0.
- **Small samples cannot produce confidence.** Observed rates are shrunk toward the
  pessimistic prior by their own sample size, so the first lucky week cannot set the year's
  expectations. Three orders is demand evidence worth under 0.05.
- **The ladder is a minimum, never an average (#274).** Tested with a company strong on six
  layers and dead on acquisition: the average reads above 0.7 and the model reports 0.0,
  because *"we can make it, price it, photograph it, and nobody buys it"* is exactly the
  failure an average hides.

Above that sits the #275 gate — six counts (selling SKUs, product families, outside customers,
orders, acquisition loops, months of history) that cap the figure at 0.74 until all are met.
Tested in both directions, because a model that can only ever report near zero would stop
being read.

**The scenario matrix (#273)** decomposes the target seven ways, sorted by the traffic each
path needs, with gross *and* contribution after Etsy's fees — CA$5,000 gross is about
CA$4,430 net, and a plan that reports only gross is one that hits its number on paper and
misses it in the bank. Required visits account for repeat and off-platform orders, which do
not arrive through the search funnel. Every row records whether its conversion rate was
observed and over what sample; today **zero paths are evidence-supported**, and the note says
the most attractive row is the one to distrust — it is attractive on account of its
assumptions, not its difficulty.

## Previously in Build 2
**Both owner-approved credentials built against their conditions — and the owner was right
about Etsy's authentication.**

### The correction, verified rather than accepted

The owner said Etsy v3 requires `x-api-key` containing *keystring and shared secret separated
by a colon*, not the keystring alone. Checked against Etsy's own documentation, which says
exactly that. **This codebase had it wrong** — `integrations/etsy.py` had been sending the
keystring alone since Build 1. It is the kind of wrong that costs a diagnosis round rather
than failing loudly: the header is accepted as a header and refused as a credential, so the
first real call returns 401 and every explanation for a 401 is plausible.

### What the sanctioned API actually covers

Fetched Etsy's published OpenAPI specification and analysed it rather than guessing. **32
endpoints are served by the API key alone, with no OAuth scope** — and nine of them carry the
MJs mandate:

| mandate element | covered? | how |
|---|---|---|
| resolve the canonical shop (#206) | yes | `findShops`, exact name match only |
| enumerate the full catalogue (#207) | yes | `findAllActiveListingsByShop`, paginated to the shop's own count |
| listing text and commerce metadata (#208) | yes | title, description, price, tags, materials, style, favourites, timestamps |
| gallery asset inventory (#209) | yes | every image URL at four sizes — **plus Etsy's own per-image hex, hue, saturation, brightness and black-and-white flag**, which answers palette and colour-architecture questions with no vision model at all |
| merchandising structure (#303) | yes | `getShopSections` — the shop's own categorisation, better evidence than our inference |
| change detection (#212) | yes | `last_modified_timestamp` plus a content fingerprint |
| image-level visual judgement (#209) | **no** | needs the approved model provider reading the public image URL — no browser, no scraping |
| rendered page presentation (#208) | **no** | badges, sale banners as presented, thumbnail crop in search. Recorded as an unmet fraction (#224). **A cloud browser is not being requested**: the API covers the mandate's substance |

Minimum scope is enforced rather than intended: an endpoint allowlist that raises before a
request is built, and no code path that could send an OAuth token. The credential never
appears in a log, an error, the call trail, `__repr__` or benchmark evidence.

### Model routing inside CA$25

Three tiers, and the tier is a property of the task, not the caller's mood:

| task | model | ~CA$/call | inside the ceiling |
|---|---|---|---|
| classification, extraction, routing | `claude-haiku-4-5` | 0.0030 | ~8,200 calls |
| gallery observation, listing copy | `claude-sonnet-5` | 0.0252 | ~990 calls |
| creative evaluation, benchmark challenge | `claude-opus-5` | 0.1294 | ~190 calls |

The ceiling is checked **before** each call — a ceiling checked afterwards is a report about
an overspend — against this calendar month's ledgered `llm` cost, with no override parameter.
Unchanged evidence is never paid for twice: the cache key is the content fingerprint *plus the
routed model*, so a downgrade cannot silently keep serving the better model's answers. And
`PATTERN_TASKS_REFUSED` means a model can never be asked for stitch counts, dimensions,
yardage or instructions, whatever the budget — the compiler owns those.

### The lead-time engine now runs itself

`seasonal.sentinel` is a daily cadence (#311). It names the at-risk rows rather than counting
them and raises a P2 only for windows where reallocating effort still changes the outcome — a
missed window is not an incident, because #297 already decided what happens to those, and an
incident per missed product per day trains everyone to ignore the channel. The finding stands
as planning evidence: Canadian Thanksgiving is missed for the generated catalogue, Christmas
remains actionable, and the 26.7-hour autumn oak throw's preferred launch is 2026-09-27.

## Previously in Build 2
**The competitive product teardown laboratory (#148, #149, #150, #151, #161, #162, #163,
#167, #169, #170) — built before the files arrive, because a boundary added afterwards was
absent exactly when it mattered.**

The owner will buy about ten representative competitor patterns so this company can study what
a customer actually receives after paying. That is legitimate and ordinary, and it puts a
folder of somebody else's copyrighted instructions on the same disk as a system that writes
crochet patterns.

- **The library is a quarantine, not a corpus.** It lives outside the repository tree, is in
  `.gitignore`, and `retrieve()` is its only reader. It refuses every generation, listing,
  support, marketing and publishing role *by name, with the reason*; refuses any role not
  explicitly an analyst; and refuses a path that resolves outside the library root, because a
  quarantine whose reader accepts `../../src` is a file-serving endpoint with a misleading
  name.
- **Nothing is ever stored as content.** The manifest holds filenames, roles, sizes and
  hashes. `check_derived()` refuses a finding whose text reads as row instructions or a
  transcription, and runs on both the mechanism and the improvement of every finding.
- **Intake never opens a file.** `scan()` works out the seller, the file roles, the chart /
  video / print / bonus presence and the hashes from filenames and the filesystem, then asks
  the owner only what it genuinely cannot infer. A manifest that had to parse a competitor's
  PDF would be reading the thing it exists to keep unread.
- **The composite standard refuses to be one seller's product with extra steps (#162).** Each
  dimension takes its target from whichever benchmark did it best, and **ties keep every
  contributor** — resolving a tie by insertion order would bias the whole standard toward
  whatever was torn down first, which is the single-source failure arriving by accident
  instead of by choice.
- **Parity is refused as a position (#163).** Every product class must name an advantage from
  a closed list anchored in capabilities already built, because free text accepts "better
  quality", which is a hope.
- **A finding with no action cannot be recorded (#164).** A teardown that produces no change
  is a review.

Readable at `/api/teardown`, which leads with whether the standard is still single-source.

## Business continuity is now proved in production, not only in tests

`POST /api/continuity/verify` against the live Postgres database, 2026-09-18T14:52Z:

- **4,304 rows across 25 tables** exported in portable JSON Lines
- **4,027 of them non-rederivable** — audit log, jobs, owner queue, incidents, ledger,
  benchmark observations
- restored into a scratch database and re-exported; **content digests match**
  (`c86bb1d4a49c…`)

The gap Build 1 wrote into its own baseline is closed and demonstrated against real data. What
remains is durable storage for the archive itself, which is an owner decision (below): the
evidence is durable in the audit log; the bytes are on a container filesystem.

## Previously in Build 2
**A defect production found in the continuity job, three dead letters in.**

`BRAMBLELOOP_REQUIRE_POSTGRES=1` refuses to let this company run on a SQLite file that a
restart destroys — and the restore proof deliberately builds exactly such a file to restore
into. The guard was right; the call site was wrong. `/api/verify` went to 11 of 12 on
`no_unexpected_dead_letters_in_24h`, which is the check doing its job.

The exemption is `Database(..., scratch=True)` — a parameter, not an environment variable, so
it cannot be switched on for the whole process including the application's own database.
Verified with the production flag set: the application path still refuses, the proof runs.
Regression test in `test_continuity.py` asserts both halves, because an exemption that
accidentally disarms the guard would be a worse defect than the one it fixed.

## Previously in Build 2
**The maker lead-time engine and the seasonal launch-date compiler (#283, #284, #285, #296,
#297, #310, #311) — the requirement the owner flagged non-negotiable, and the first piece of
Build 2 that produced a finding about this company rather than about its code.**

A crochet pattern is not the product the customer wants. The product they want is a finished
cardigan, on a person, on Christmas morning — and between the listing and that morning sit the
marketplace's indexing lag, the buyer's own planning, and forty hours of somebody's hands. A
shop that launches its Christmas blanket on December 1st has launched a blanket nobody can
finish, at the exact moment the search term peaks, and its own conversion data will report that
Christmas blankets do not sell.

    latest effective launch = event − completion buffer − make time
                                    − planning buffer − marketplace ramp
    preferred launch        = latest − creative iteration − ad learning window

- **Make time is derived from the twin, never typed.** Stitch count, colour changes counted in
  the order a person actually crochets, and per-piece finishing — the term every optimistic
  estimate drops. This company already refuses a typed finished size; make time decides
  whether a customer holds a finished object on the day, so it gets the same treatment.
- **Every figure says whether it is measured or assumed.** A launch date derived from six
  guesses and one derived from six months of sales data are different objects, and a dashboard
  that renders them identically ruins both. `Assumptions.measured()` is the only route from
  assumed to measured, so nothing graduates by being overwritten.
- **`calibrate_from_samples()` turns tester-reported hours into a real stitch rate** — the
  physical test intake has asked testers for hours since Build 1 and nobody had ever divided.
  With no completed samples it reports that, rather than returning a plausible number wearing
  a `measured` label.
- **A missed window is never launched on its seasonal premise (#297).** Finished engineering
  is not an argument. The recommendation is pivot-to-evergreen, simplify-to-a-quick-make or
  hold-for-next-cycle, with the reason.
- **`at_risk` is distinguished from merely past-preferred (#311)**, because they are different
  situations: one has runway to spend, the other is the last window in which reallocating
  effort changes the outcome.

**The finding, measured against the eleven generated designs on 2026-09-18** — `/api/seasonal`:

| | |
|---|---|
| Canadian Thanksgiving (12 Oct) | **missed for all eleven.** Even the 0.9-hour ornament needed to be live by 4 September |
| Halloween (31 Oct) | at risk for the larger pieces |
| Christmas (25 Dec) | all eleven still on track — but the largest, the 26.7-hour autumn oak throw, has a **preferred launch of 2026-09-27**, nine days away, and a last viable date of 21 October |

That is the first time this system has said something about the business that nobody had
asked it. It is also the argument for the owner actions below: a listing cannot go live
without a shop.

## Previously in Build 2
**The benchmark spine for the owner's named-shop mandate (#205, #206, #210, #211, #217, #301,
#305, #312, #314, #318, #319) — everything the MJs mission needs that does not require the
browser capability nobody has granted yet.**

The mandate is unusually emphatic: one specific shop, by name, explicitly not generalisable
into "watch proven sellers". Most of the ways it goes wrong are ways of *appearing* to satisfy
it, so each one has a refusal and a test:

- **A redirect to a different seller is refused, not followed.** `intel/benchmarks.py`
  classifies resolution as healthy / moved / unreachable / **wrong_shop** / unverified. A 404
  and a redirect that lands somewhere plausible look identical to a naive follower, and the
  second silently re-points the entire mission at a stranger. A move updates where we look; a
  wrong shop never does. With no capability configured the state is `unverified`, never
  `healthy`, because the dashboard is believed.
- **The owner's own URL is stored verbatim**, query string and all, and surfaces unchanged on
  `/api/mjs` — #301 requires it in the registry and in acceptance evidence, and tidying it into
  the short canonical route is the obvious, helpful, wrong thing.
- **Eight permanent specialist pods** with ordered routing, so a Christmas stocking reaches
  the stocking specialist rather than the seasonal one, and each pod owns a quality rubric. A
  listing nobody can classify goes to a visible `unclassified` queue rather than the nearest
  pod, because a map whose gaps are invisible reports full coverage of whatever it understood.
- **A dimension with no evidence is `unknown`, never `parity`.** Parity is a finding.
  Defaulting to it lets a company that has never looked at its benchmark report itself level
  with it, which is the most comfortable wrong answer available.
- **Lessons are stored only at the mechanism level**, against a closed vocabulary, and a note
  carrying a competitor's row-by-row instructions or chart is refused at the point of writing.
- **The gap queue has all seven states #314 names**, a transition table that refuses a state
  the work never passed through, and a mandatory reason for `not_pursuing` — a queue whose
  items can be closed silently shrinks by forgetting and then reports good coverage. Scores
  record the share of the weighting actually answered, so a 0.8 computed from one component
  out of seven cannot pass for a considered one.
- **#319, almost verbatim:** a report that says only "competitor scan complete" is refused.
  So is one that names a different shop, one with no date, and one whose catalogue coverage
  cannot say how many listings are known versus inspected.
- **#305 is enforced at provenance**, the only place a file's origin is stated: a source
  outside camera / twin / generator / designer blocks, and provenance describing a downloaded,
  scraped or recoloured competitor image blocks. By the time an image is in a gallery it looks
  like any other image, and "we would never do that" is not a control.

Four new tables (`benchmarks`, `benchmark_listings`, `benchmark_observations`,
`coverage_gaps`), three of them added to the continuity export's non-rederivable set. The
mission dashboard at `/api/mjs` leads with whether the mission can observe anything at all,
and says plainly that nothing in it is filled in from snippets, screenshots or fixtures.

## Previously completed milestone
**The access approval protocol, and the rule that stops a missing capability being faked
(#223, #224).**

The owner said they would approve reasonable access for the mandatory benchmark observation
and for 24/7 autonomy, and put the limit in the same sentence: not blanket authorization for
unbounded spending or credentials. `src/brambleloop/launch/access.py` is both halves.

- **Every request is bounded by construction.** A recurring cost with no monthly ceiling
  cannot be instantiated — the guard is in the type, not in a review, because a rule that
  lives in a docstring is one a future session writes around. Each request carries the exact
  action, purpose, capability unlocked, security scope, maximum cost, monthly ceiling,
  minutes, consequence of declining, and what continues regardless.
- **One queue, not two.** The capability requests go into the same consolidated owner queue
  through `launch.readiness`, keyed on the requirement so a re-run restates rather than
  duplicates — the same identity rule that stopped the fee approval appearing twice. Section
  14 says one queue and the reason is arithmetic: two means the owner reads whichever they
  remember.
- **Willingness is not approval.** `available()` asks the environment and nothing else, so no
  amount of stated intent turns a capability on.
- **A degraded substitute is never evidence (#224).** `accept_evidence()` grades every piece
  of benchmark evidence: a search snippet, a manual screenshot, a seeded fixture or a stale
  cache is *supporting* — real, keepable, and unable to close a requirement that asks for
  continuous cloud observation. Evidence labelled `browser_traversal` while the capability was
  never granted is downgraded, because the label must not be able to grade itself. A copied
  competitor photograph is refused outright rather than graded.

The engineering finding worth the owner's attention: **the first step of the benchmark mandate
appears to be free.** Etsy's Open API v3 issues a read-only keystring for public shop and
listing data — no shop, no KYC, no payout account, no cost — which is the platform's own
sanctioned route and covers resolving the shop, enumerating the catalogue and reading listing
text, price, tags and gallery image URLs. A paid cloud browser is worth approving only if that
proves insufficient. Nothing here claims it has been called: it is the documented path, and it
stays unverified until a key exists.

Readable at `/api/access`, which reports the unmet capability first and the request second.

## Earlier in Build 2
**Business continuity: the export, the restore, and the proof that the restore works
(requirement 51 — the gap Build 1 wrote into its own baseline, and the one the owner flagged
to close early in Build 2).**

`src/brambleloop/core/continuity.py`:

- **Portable, not engine-native.** Every table exports as JSON Lines with a per-table sha256
  and a declared row count. A `pg_dump` restores into Postgres and nowhere else, which is the
  dependency #51 exists to remove; this restores into any SQLAlchemy engine, and a
  Postgres-shaped export restoring into a scratch SQLite file is exactly what makes the proof
  below runnable from the application container at all.
- **The proof is a hash comparison, not a row count.** `prove_restore()` restores the export
  into an empty database, re-exports it and compares digests table by table. A restore that
  dropped every timestamp, mangled a JSON column or coerced a Decimal would pass a headcount
  unchanged.
- **Truncation and unknown formats are refused.** Each table declares its own row count and
  the reader checks it, so a half-written archive fails at the point it stopped rather than
  restoring silently as if it were complete.
- **No credential ever reaches the export, its manifest or the audit log.** The export names
  which database it came from — continuity evidence that cannot say that is not evidence —
  with the credentials redacted before anything is written.
- **Scheduled daily** as the `continuity_proof` cadence, and a failed proof raises a
  correlated P1 incident rather than a log line.

`src/brambleloop/core/opsauth.py` and `GET /api/continuity/export`: the one endpoint that can
return database contents authenticates with an operator token held only in the hosting
environment, compared in constant time, never echoed — and **closed to everyone when unset**
rather than open. The opposite default serves the company to the internet in the window
between deploying the endpoint and remembering to set the variable, which is exactly the
window in which nobody is looking. `/api/continuity` reports whether backups are being proved
without exposing anything a stranger could use.

Still open, and batched for the owner rather than hidden: the archive is written to ephemeral
container storage. The **evidence** is durable — digests, row counts and the restore proof
live in the audit log — but the bytes are not, and that needs durable object storage. Rendered
PDFs and charts are deliberately not archived: they are re-derivable from the CIR and the
code, which is what "patterns are software releases" buys.

Found by the test that exists for it: the new daily cadence was scheduled against an agent
with no permission to run it — the same defect production hit with the heartbeat in Build 1.
`test_every_scheduled_cadence_can_actually_run` caught it before it ever ran.

## Build-1 closing milestone
**Build 1 of Master Plan v1.2 is complete. Nothing in the launch report is blocked on build.**

Verified at 2026-09-18T08:40Z against production running commit `d5168c0`:

- `/api/verify` — 12 of 12 checks passing.
- `/api/launch` — every build-owned requirement satisfied; `blocked on build: NONE`. The
  eight unmet requirements are seven owner actions and one Etsy credential that only the
  shop can produce.
- `./run_tests.sh` — 541 passing, 0 failing, 26 suites, measured at `d5168c0`.
- Shadow Mode intact: `BRAMBLELOOP_PHASE=shadow`, 0 published against 120 recorded
  publication refusals, CA$0 revenue, CA$0 advertising, CA$0 model spend, no provider
  configured, no spend scope paused, 0 customers, 0 orders.
- The per-section coverage map below records what exists for each of the plan's 29 sections
  and what each unmet item waits on.

The last four defects closed to get here were all found by looking at what production had
actually produced rather than at what the code said it would:

1. **Every listing image in production was unreadable.** Three independent causes, each of
   which alone would have shipped an unsellable listing: no fonts in the container, so
   Pillow fell back silently to a bitmap face a few pixels tall; a fabric renderer that
   coloured cells only by colourway, so a deliberately single-colour textured design had
   nothing to show; and my own frame-level thumbnail check passing a blank hero at 78%
   coverage because it was measuring the title text while production blocked the same
   product at 11%.
2. **Production could not say which code it was running.** `version` is hand-maintained, so
   until now "the deploy landed" was inferred from effects — which is how each of the three
   idempotency layers cost a diagnosis round. `/api/status` now reports the build commit and
   says `unknown` rather than guessing.
3. **The fourth layer of the rebuild bug**, found with that new field. The rebuild had
   detected the cable throw as stale, enqueued the work, watched `assets.build` refuse it
   for blocked imagery — correctly — and then reported the same stale line on every later
   run while enqueueing nothing, because the listing stayed stale and so the transition, the
   token and the key never changed. `CHAIN_VERSION` 6 is the mechanism that frees it, and
   the audit record now distinguishes "stale and untried" from "stale, attempted, refused".
4. **The charts could not be read without colour vision** (§31). Twelve of the nineteen
   designs are two-colour work where the colour *is* the motif, the chart separated the
   yarns by hue alone, and the legend's only identifier per yarn was a coloured square.
   Every square now carries its yarn's letter, and a chart too small to carry one blocks
   rather than ships.

Writing the regression fixture for (4) then caught two defects I had just introduced — a
footer that stretched the disc chart to 2:1, and a flag reset that discarded a fact about
the container — which is what the fixtures are for.

## Previous milestone
**Construction beyond flat rows (§2, §3), and the defect it exposed.**

Two products in the catalogue were named for shapes their patterns did not make. "Market
Basket Trio" was a single flat 24-row rectangle whose own designer note called it "the side
panel, seamed into the basket" — with no seaming instruction anywhere in the document, so a
buyer would have paid for three baskets and received one panel. "Hexagon Coaster Set" was a
rectangle with a colourwork motif on it. Both were certified, both had listings drafted in
production. Nothing was published, because nothing in this system can publish.

What now exists:

- `cir/geometry.py` measures a round-worked piece as a surface of revolution: each round is a
  circle of fabric, and the row height splits between growing outward and rising upward. A
  disc, a tube, a cone and an open vessel are measured exactly; a closed shaped piece is
  *refused* a width and a height and reports its circumference instead, because the ball is
  made by the stuffing and the maker's tension, which are not in the gauge.
- The same model names fabric that has to gather — a round growing faster than its own height
  is a frill, which is a legitimate design and not a diameter.
- `geometry.corners` reads six stacked increase columns out of the stitch positions, so
  "hexagon" is evidence rather than an assertion.
- The twin no longer reports a flat width for anything worked in the round, and Asset Truth
  refuses a size claim it cannot check rather than passing it for want of a comparison.
- Product names are checked against the shape the pattern makes, narrowly: a
  three-dimensional noun, or a shape word attached to the object. A star motif *on* a
  rectangle is not a shape claim.
- The finishing is in the CIR. Seams name their pieces, the compiler checks they exist, the
  writer emits the steps, the reverse compiler reads them back, and a flat panel may be
  called a basket once something joins it into one.
- Written patterns name the yarn on every row of a multi-colour pattern — the whole catalogue
  was previously workable only from the chart — and say once per component whether to join
  the rounds or spiral. Both are checked by the reverse compiler.
- Charts for round work are drawn as rounds from the centre out, replacing a ragged staircase
  captioned with flat-fabric reading directions.
- `market-basket-trio` is now a storage basket worked in one piece from the centre of the
  base, in three sizes (15 / 20 / 25 cm across, measured), and `hexie-coaster-set` is a real
  six-cornered hexagon, set of four, with the yarn estimate covering all four.
- `CHAIN_VERSION` 5 and a new `DOC_VERSION` so the corrected documents reach products that
  were already certified, and re-certification now *replaces* the stored certificate instead
  of skipping it.
- A product whose certificate is refused has its listing withdrawn.

**Launch readiness and the owner queue (§14, §26).** The system now computes, from the
warehouse rather than from recollection, every requirement a live shop has, and attributes
each unmet one to *build* (ours), *integration* (an account or service that does not exist)
or *owner* (a person's identity, bank account or hands). Only the third kind reaches the
owner-action queue, which the system writes itself on a daily cadence in the Execution
Directive's format — action, reason, maximum cost, minutes, consequence of delay — and does
not duplicate on re-assessment. Visible at `/api/launch` and on the dashboard. The queue
table has had those columns since the first build and nothing had written to them, because
until the catalogue, imagery, pricing and copy existed, every blocker was ours.

## Earlier milestone
Master Plan v1.2's commercial departments, built on the proven infrastructure rather than
alongside it. Sections 6, 7, 8, 9, 10, 11, 12 and 16 now have running code and tests:

- **Brand system and Storefront Director (§6).** Palette, type, crop and lighting rules, a
  two-word collection naming grammar, the brand model's character bible with three enforced
  refusals, grid-coherence measurement, and the whole shop drafted — announcement, About, five
  policies, sections, banner and icon briefs.
- **Listing imagery (§7).** Seven ordered frames rendered from the twin, each declaring its
  asset class and claims, checked by Asset Truth, with the hero judged at Etsy's real
  search-grid size.
- **Search Domination (§8).** A query model that distinguishes reachable phrases from head
  terms a shop with no history cannot place for, thirteen tag slots spent under a word budget,
  coverage scored against reachable demand, and structured attributes from pattern data.
- **Pricing Intelligence (§9).** Market price scanner, contribution-per-visitor optimiser,
  bundle economist with a breakeven attach rate, price experiments whose stopping rule is
  fixed before they run, and promotion checks that refuse a permanent sale.
- **AI Customer Experience (§10).** Triage across seven desks with escalation ordered first,
  replies drafted and recorded as unsent, review solicitation refused, and repeated questions
  about one row surfaced as candidate defects.
- **Marketing (§11).** A full content ecosystem per product — article, four distinct pins,
  tutorial outline, email with a CASL unsubscribe, validated free teaser, cross-sell and a
  crochet-along where the make time warrants one — scheduled backwards from launch.
- **Portfolio (§12).** Section 12's diagnostic table as code, with intervention ladders, and a
  classifier that refuses to classify a SKU nobody has seen.
- **Confidence (§3) and regression capture (Gate B).** Seven dimensions tracked separately with
  no overall score, and confirmed defects frozen as permanent fixtures.
- **Paid media guard rails (§11).** Every ceiling section 11 names, and every auto-pause
  condition: tracking failure, unavailable listing, CAC breach, refund anomaly and the
  test-loss cap. Built while no campaign exists and no money can be spent — `authorise_spend`
  refuses on phase and on missing owner authority before it looks at any budget, because a cap
  is not permission.
- **Finance (§1, §15, §34).** The full P&L section 15 lists, read from observed entries only;
  a tax reserve that is never counted as ours; cost-per-validated-pattern computable without
  revenue; a CFO/Skeptic that reports concerns when everything is nominally fine and blocks on
  infrastructure above the owner's ceiling or advertising with no attributable orders; and a
  CA$100K trajectory that refuses to forecast from zero orders.
- **Row-level repeats (§2).** Written patterns now collapse a repeated row block into
  "Repeat rows 25-48 3 more times, ending with row 120", the way a printed pattern does.
  The flagship prints 48 rows instead of 120 and its PDF is 7 pages instead of 8. The cycle
  is *derived* from the compiled rows rather than declared in the CIR, so there is no field
  that can disagree with them, and the reverse compiler parses and expands the instruction
  itself from the customer text — it does not receive the writer's expansion, because then
  the two halves would no longer be independent.
- **The catalogue (§16).** A motif library and a builder; sixteen designs generated, every one
  compiling and reverse-compiling clean. Ten of eleven release candidates now ship an
  engineered design rather than the striped template; the eleventh is the bundle, which
  correctly has no pattern of its own.

## Earlier milestone (before that)
The complete shadow release chain on a real product. One unattended `plan.cycle` now runs
market scan → portfolio selection → engineered CIR → compile → digital twin → reverse compile
→ certificate → PDF and charts → pricing → listing and SEO → launch plan → refused publish,
for all eleven release candidates, with 101 jobs completed and no unexpected failures. The
flagship's actual output — the 8-page PDF, the chart, the price net of Etsy fees, the listing
copy, the launch dates and a support transcript — is written to
`reports/shadow_release_nordic_forest.md` so it can be inspected rather than taken on trust.
The chain was then deliberately attacked: 16 attack tests covering a single wrong stitch in a
motif, a stale chart from another size, drifted customer text, unsupported size claims,
invented motifs, a fake was-price, a bundle that is not cheaper, an unsupportable listing
claim, an agent reaching outside its permissions, support trying to amend a pattern, and a
corrupted or missing artifact. All are rejected by construction.

## Architecture decisions
See `DECISION_LOG.md` for reasoning. Summary:
- Python 3.11. Core value is deterministic arithmetic, PDF/chart generation and image work.
- Postgres in production; SQLite for hermetic tests. Durable queue via `SELECT ... FOR UPDATE
  SKIP LOCKED` (Postgres) with a portable fallback — no Redis, fewer moving parts to die
  unattended.
- FastAPI + server-rendered Jinja admin. No separate frontend build step.
- Railway as the deploy target (owner account `statefarm91` verified present, personal
  workspace, 3 existing projects). **Not provisioned** — paid infrastructure is an owner gate.
- Lives at `brambleloop/` inside the Project-Money repo for now, purely because push
  credentials are scoped to that repo. Migrating to a dedicated repo is a tracked follow-up,
  not a blocker.

## Completed capabilities
- `core/db.py`, `core/models.py` — warehouse: jobs, agents, audit log, cost entries, ledger,
  spend limits, products, pattern versions, incidents, owner-action queue.
- `queue/durable.py` — leased jobs, idempotency keys, backoff with jitter, dead-letter.
- `agents/registry.py` — per-agent job-type permissions, daily cost ceilings, structurally
  forbidden combinations, audit trail, and a SpendGuard that pauses a scope on breach.
- `core/backup.py` — backup plus a restore drill that reloads and compares row counts.
- `gates/asset_truth.py` — imagery/claims checked against the digital twin.
- `gates/policy.py` — unsupported claims, IP tripwires, deceptive pricing, Etsy limits.
- `gates/certificate.py` — the full release chain and an immutable release hash.
- `gates/incidents.py` — defect correlation, P1 escalation, publication halt.
- `runtime/worker.py` — worker loop (authorize → dispatch → complete/fail) and scheduler.
- `runtime/pipeline.py` — the shadow release pipeline and its job handlers. `radar.scan` now
  scores the real pool and emits the selected portfolio; `radar.score` re-scores each
  candidate at the moment it would consume engineering effort, because a job can sit in the
  queue while a seasonal window closes underneath it.
- `radar/market.py` — dated competitor profiles, category observations, and the SHOPPING DATE
  vs MAKING DATE window arithmetic (section 5).
- `radar/opportunity.py` — the 34-concept pool, the six-component score, and the section 33
  portfolio constraints.
- `radar/report.py` — renders the whole decision as reviewable markdown.
- `gateway/prompts.py` — immutable, content-hashed, version-pinned prompts.
- `gateway/model_gateway.py` — provider-agnostic routing, per-provider circuit breakers,
  strict JSON parsing, per-agent cost recording, and `require_deterministic()` which refuses
  to let a model verdict stand where the compiler has one.
- `gateway/evals.py` — property-based eval fixtures that block a prompt version change if the
  model starts inventing or dropping factual claims.
- `products/nordic_forest.py` — the first engineered design: a motif grid, three generated
  sizes.
- `publish/charts.py`, `publish/pdf.py` — charts and the customer PDF, rendered from the twin.
- `commerce/pricing.py`, `commerce/seo.py`, `commerce/launch.py` — fee-aware pricing that
  refuses deceptive discounts, listing copy assembled only from computed facts, and a launch
  plan anchored on the buying window.
- `support/concierge.py` — answers from the exact released version and cannot amend it.
- `core/artifacts.py` — content-addressed artifacts; hashes durable, bytes not.
- `core/resilience.py` — transient/permanent classification, Retry-After honouring, circuit
  breaker, artifact hash integrity, strict model-output parsing.
- `app/main.py`, `app/worker_entry.py`, `app/scheduler_entry.py`, `Dockerfile`,
  `railway.json` — the deployable surface. **Provisioned and running**: see "Integrations
  connected". The image installs `fonts-dejavu-core`, because without it Pillow fell back
  silently to a bitmap face a few pixels tall and every listing image rendered in production
  was unreadable at thumbnail size.
- `core/build.py` — which commit the running image was built from, surfaced on `/api/status`
  and `/health`. Reports `unknown` when the build environment does not say, and an unknown
  build never matches a commit, so "I cannot tell" is never reported as "the deploy landed".
- `publish/charts.py` — stitch and colour charts, flat and round, rendered from the twin.
  Cells are shaded by their stitch's relief as well as their colour, so single-colour
  textured fabric is visible, and every square of a multi-colour chart carries its yarn's
  letter so the chart can be read without relying on colour (section 31).
- `publish/listing_assets.py` — the six-frame listing plan (hero, chart, size, detail, format,
  siblings), rendered from the same twin as the PDF so no frame can assert something the
  pattern does not produce. Blocks on a missing font, on a hero whose fabric has no internal
  contrast, and on any frame Asset Truth rejects.
- `cir/stitches.py` — canonical stitch taxonomy (consumes/produces/height per stitch). US
  canonical, UK rendered downstream.
- `cir/model.py` — CIR dataclasses, JSON round-trip, components/rows/repeats/gauge/materials.
- `cir/compiler.py` — deterministic compiler. Validates per row: stitch availability, over/
  under-run, repeat divisibility, declared-vs-computed count, unknown colour, row ordering,
  empty rows. Warns on missing turning chains for tall stitches.
- `cir/writer.py` — CIR → customer-facing pattern text, US/UK terminology, magic-ring aware,
  repeated row blocks collapsed into an instruction. `collapses_rows()` is the single place
  that answers whether a document collapsed anything, so listing copy cannot promise a
  printed line for every row when the PDF no longer prints one.
- `cir/rowcycle.py` — detects the longest repeated row block in the compiled rows, expands it
  back, and writes the maker-facing sentence. Derived, never declared.
- `cir/geometry.py` — round-worked geometry as a surface of revolution: per-round
  circumference, radius, axial rise, shape classification (disc / tube / cone / vessel /
  dome / shaped / gathered), corner detection from stitch positions, and an explicit refusal
  where the geometry cannot support a finished size.
- `integrations/http.py` — a urllib transport for that client. Standard library only, no
  retries (that is the caller's policy), and never run against Etsy.
- `integrations/etsy.py` — the publishing path: a v3 draft-listing client behind three
  ordered refusals (phase, owner authority, credentials), a mapper that refuses rather than
  truncates, and an honest outcome for "listing created, file not attached". **Written and
  unit-tested against a fake transport; never called against Etsy.** No credentials exist in
  this environment. The multipart file upload is the one part that cannot be verified
  without a live call, and the interface says so rather than hiding it.
- `quality/physical.py` — the only measured input: grams per colour and the ball band become
  metres, metres against the estimate become a calibration factor keyed on that yarn and
  stitch, and a finished size outside 12% of the claim raises a defect rather than becoming
  a factor. Intake at `POST /api/physical-test` and the `physical.record` job.
- `launch/readiness.py` — every requirement a live shop has, checked against the warehouse,
  with each unmet one attributed to build, integration or the owner. Writes the owner-only
  ones into the owner-action queue in the Execution Directive's format, daily, without
  duplicating what is already there. Exposed at `/api/launch` and on the dashboard.
- `products/texture.py` — the designs whose names were claims the fabric did not honour: a
  cable throw that crosses, a bobble pillow that bobbles, a ribbed scarf that ribs. Post
  stitches, closed clusters and crossings now exist in the taxonomy, and
  `check_technique_claims` blocks any product whose name says otherwise.
- `products/vessels.py` — the round-worked designs: three basket sizes derived from a wanted
  diameter, and a hexagon coaster whose corners are real.
- `cir/reverse.py` — independent parser of customer-facing text + structural diff against
  canonical CIR. Shares no parsing code with the writer by design.
- `cir/twin.py` — digital twin: cell-level fabric model, chart/colour grids, finished
  dimensions from gauge, per-colour yardage estimate with an explicit ±20% tolerance until a
  physical test calibrates it.

## Master Plan v1.2 coverage, section by section

The honest answer to "is anything left that Claude can build?". Every section of
`spec/01_Brambleloop_Master_Plan_v1.2.pdf` is listed -- the plan numbers 1-17 and 25-36,
with no 18-24 -- against what exists and what it is waiting on. "Owner" means the item in
the owner queue above; "observations" means live marketplace or sales data that cannot exist
before the shop does.

| § | Section | State | Waiting on |
|---|---|---|---|
| 1 | Business Thesis and CA$100K Target | Machinery built: pricing, contribution P&L, portfolio selection, cost-to-create. Revenue CA$0 and cannot be otherwise in shadow. | Owner 2-4, 7 |
| 2 | Pattern Engineering (non-negotiable) | Complete. CIR, deterministic compiler, stitch taxonomy including post stitches, bobbles and crossings, round geometry, seams with placement. | — |
| 3 | Digital Twin, Reverse Compiler, Physical Testing | Twin and independent reverse compiler complete. Physical intake, calibration and falsification built and tested. | Owner 5 (the measurement) |
| 4 | Market Radar and Competitor Digital Twins | Built on dated, sourced observations with a 34-concept scored pool. No live scraping integration. | Observations |
| 5 | Seasonality, Launch Events, Winner Amplification | Shopping-vs-making window arithmetic and launch calendar built. Amplification needs winners. | Observations |
| 6 | Brand System, Storefront, Consistent Model | Built: brand tokens, announcement, About, five policies, all checked. Brand-model imagery deliberately not generated (disclosure question, tracked). | — |
| 7 | Listing Conversion and Asset Truth | Complete. Six-frame plan rendered from the twin, Asset Truth over every frame, thumbnail check at shopper scale. | — |
| 8 | Search Domination and Page Growth | Tag and title selection, coverage scoring, content ecosystem built. Ranking feedback needs a live shop. | Observations |
| 9 | Pricing Intelligence and Promotions | Fee-aware pricing, bundle arithmetic, refusal of deceptive discounts. Elasticity needs sales. | Observations |
| 10 | AI Customer Experience | Built: answers from the exact released version, cannot amend a CIR, refuses to guess, every reply recorded unsent. | Owner 7 |
| 11 | Marketing and Paid Media | Built with hard caps enforced in code; disabled, CA$0 spent. | Owner (paid-media authority) |
| 12 | Portfolio, Reviews, Product Mortality | Classification and mortality rules built. Needs reviews and sales. | Observations |
| 13 | 24/7 Cloud Architecture | Complete and running. Durable queue, leases, scheduler, twelve production checks, and the running commit now reported. | — |
| 14 | Agent Governance, Policy, Owner Approval | Complete. Per-agent permissions and cost ceilings, structurally forbidden combinations, RED actions, owner queue. | — |
| 15 | Intelligence Warehouse, Finance, Failure Recovery | Complete. Postgres warehouse, full P&L with a CFO challenge, backup with a tested restore, dead letters, circuit breakers. | — |
| 16 | Initial Catalogue and Agent Organization | 19 engineered designs, 15 agents, every design compiling and certifying. | — |
| 17 | Final Release Chain | Complete and exercised in production end to end. | — |
| 25 | Search Reality Corrections | Built: the corrections are in tag selection and coverage scoring. | — |
| 26 | Shadow Mode and Safe Autonomy | Complete and enforced in code. Verified continuously: 12/12 checks, 90 recorded publication refusals, nothing published. | Owner 7 |
| 27 | Model Gateway and Reproducibility | Gateway built with pinned, content-hashed prompts and deterministic override. No provider configured. PDFs render byte-identically. | — |
| 28 | Security, Privacy, Disaster Recovery | Backup and restore drill, no secrets in the repository, resilience classification, artifact hash integrity. | — |
| 29 | Originality, Trademark, Brand Clearance | Originality gate built and run in the chain. | Owner 6 |
| 30 | Owned Audience and Channel Resilience | Content ecosystem with a commercial job per piece, and channel attribution modelled. No email, Pinterest or site integration exists. | Owner 2-3, credentials |
| 31 | Localization and Accessibility | Complete as far as it can be. Terminology rendered at write time from one canonical CIR; charts carry hue-independent colour cues, explained legends, print-friendly contrast. Translation itself needs terminology review before sale. | Owner (translation review) |
| 32 | Pre-Launch Acceptance Tests | Complete. All six gates pass, every line with its own named test. | — |
| 33 | Initial Launch Portfolio Test | Complete. The portfolio selector runs under the section's constraints and an 11-SKU cycle completes unattended. | — |
| 34 | Cost-to-Create and Throughput Metrics | Built and reported. | — |
| 35 | What Must Happen Before Sending Claude Live | This is the owner queue, written by the system. Seven items. | Owner 1-7 |
| 36 | v1.2 Final Release Chain | Complete. | — |

**Nothing in this table is waiting on Claude.** Every remaining item needs either an owner
action from the queue above, or marketplace data that cannot exist until the shop is open.

## Acceptance gates

Every line of `spec/03_Acceptance_Tests_and_Autonomy_Gates.pdf` now has a named test in
`tests/test_acceptance_gates.py`, so "Gate B passes" is a claim backed by a test rather than
inferred from a scattering of others.

- **Gate A (Infrastructure): passing.** Worker restart loses no durable jobs; a replayed cycle
  duplicates no products; backup and a tested restore succeed; dead-letter and backoff work;
  the audit log identifies actor, action and artifact.
- **Gate B (Pattern Safety): passing — now complete.** Known-good compiles; a broken stitch
  count fails; a bad repeat fails; a construction-changing mutation of the customer text is
  caught by reverse compilation; **and a corrected bug creates a regression test**, which was
  the one line that kept this gate open. The repository carries a regression corpus of
  defective patterns that must keep failing.
- **Gate C (Asset Truth): passing.** An absent motif is rejected; unsupported size, material
  and difficulty claims are blocked; provenance is stored for every listing asset.
- **Gate D (Commercial Safety): passing — now complete.** Price and promotion changes pass
  policy; an ad budget breach is prevented and the scope auto-pauses with no refused spend
  leaking through; **contribution accounting reconciles against test transactions**, which was
  the outstanding line; per-agent cost ceilings hold.
- **Gate E (Customer Experience): passing — now complete.** Routine support is answered from
  the correct pattern version and recorded as unsent; repeated defect reports correlate into
  one incident; support cannot patch a CIR by any path; a P1 halts the publication workflow.
- **Gate F (Shadow Graduation): passing.** A full product completes Market Radar → Opportunity
  → CIR → QA → PDF/assets → pricing → listing draft → launch plan → simulated support with no
  intervention, and a second test asserts that **nothing graduated**: no publication, no
  ledger entry, no message sent.

Passing these is permission to graduate SHADOW → STAGING, not graduation. Nothing has
graduated, and nothing will without the owner.

## Integrations connected
- **Railway** — connected and load-bearing. Project `brambleloop`, environment `production`,
  services `brambleloop-os` (the app) and `Postgres` (the durable state). Deploys on push to
  `claude/repository-setup-nc9x6o`. `/api/status` reports the commit the running image was
  built from, so "the deploy landed" is now checkable rather than inferred.
- **Etsy** — *not* connected. The client is written and unit-tested against a fake transport
  and has never been called against Etsy. It refuses on phase, on owner authority and on
  missing credentials, and nothing in this environment satisfies any of the three.
- **Model providers** — none. `/api/status` reports `model_providers: []`, which is the
  truthful answer, and no model call has ever been made.
- **Object storage** — none. Artifact bytes live on the container filesystem and do not
  survive a restart; hashes are durable and everything re-renders from the certified CIR.
  This is owner action 1.

## Owner actions required

**Seven of these are written by the system, not by hand.** `launch.readiness` assesses every
requirement, decides who each unmet one waits on, and queues only the owner's — with the
five columns the Execution Directive asks for. Read them live at `/api/owner-actions`, or as
the report at `/api/launch`. As of 2026-09-18 there are seven, in dependency order:

1. **Object storage for generated PDFs and images** — max CA$5/month (within the CA$20
   ceiling), 10 minutes. Unlocks reliable delivery of purchased files.
2. **Open the Etsy shop and complete Etsy's identity verification** — CA$0, 25 minutes.
   Unlocks publishing anything at all. Must be done by the person who is the seller.
3. **Add the payout bank account and tax details** — CA$0, 15 minutes. Unlocks publishing and
   any revenue at all.
4. **Accept Etsy's listing and transaction fees for the opening catalogue** — about
   US$1.80 (CA$2.50) for nine listings plus 6.5% per sale; max CA$5, 2 minutes. The first
   spend that leaves the account, so it needs approval by the directive.
5. **Crochet one sample (the 20 cm basket), weigh the yarn, measure the piece** — max CA$25,
   about 7 hours. Unlocks calibrated yardage instead of a ±20% tolerance, and is the gate
   Class C products cannot pass at all. Cannot be automated: it needs hands, yarn and a hook.
6. **Decide on trademark clearance for "Brambleloop Studio"** — knock-out search free, filing
   CA$458.05; max CA$460, 20 minutes. Blocks nothing yet; the risk rises with every sale.
7. **Move `BRAMBLELOOP_PHASE` to staging, then limited production** — CA$0, 5 minutes.
   Unlocks the entire commercial phase. Only the owner moves the phase; the system cannot
   promote itself.

Plus one piece of housekeeping that predates the queue:

**8. Delete the stray Railway service `Project-Money` (housekeeping, ~1 minute).**
- *Exact action:* in the Railway project `brambleloop` → `production`, delete the service
  named `Project-Money` (`4dff24df-2186-4278-b01f-c11ec39a766f`).
- *Why:* it was created by accident — a deploy call spawned a second service instead of
  deploying to `brambleloop-os`. Its build failed and it is not running, so it costs nothing
  measurable, but it is not part of the system and should not sit in the project pretending
  to be.
- *Still outstanding as of 2026-09-18T04:05Z.* `list-services` on project `brambleloop`
  still returns it. Deletion has now been attempted from this session three times and
  declined each time, which is the correct default for an irreversible action — so it stays
  here as a request rather than being retried.
- *Maximum cost:* CA$0. Leaving it costs nothing either; this is tidiness, not spend.
- *Consequence of waiting:* none beyond confusion for whoever opens the project next.

Nothing on this list was asked for speculatively. Every item is a requirement the system has
actually reached and cannot meet itself, and the directive's prohibition on requesting
Etsy/KYC/banking "merely because they will eventually be needed" is enforced by the
readiness assessment: a requirement blocked on build never reaches the owner queue, and a
test asserts both directions.

## Financial state
Exact and verified. Nothing here is projected.

- **Recurring infrastructure:** Railway Hobby plan, US$5 / ~CA$7 per month, which includes
  US$5 of usage. Measured usage is ~US$1.70/month, so no overage is expected. Owner ceiling
  is CA$20/month; nothing may exceed it without the owner's approval.
- **Spend to date:** CA$0 invoiced. No bill has been issued yet.
- **Agent/model spend:** CA$0 — no model provider is configured and no model call has been
  made.
- **Advertising spend:** CA$0 — paid media is not enabled.
- **Revenue:** CA$0. **Customers:** 0. **Orders:** 0. **Listings live:** 0.

## Current blockers
- **Nothing is blocked on build.** Build 1 of v1.2 is complete and production-verified; see
  the coverage map and `/api/launch`. Every remaining item waits on an owner action from the
  queue above, or on marketplace data that cannot exist before the shop is open.
- A future session resuming here should **not** invent new scope. The owner has a v1.3
  commercial upgrade package queued for after Build 1; do not ask for it and do not guess
  its contents. If the owner has not yet acted on the queue, the honest next move is the
  deferred work in "Next highest-value unblocked actions" below, not a new department.

## Operating notes
- **Reproducible artifacts.** The customer PDF renders byte-identically from the same
  certified CIR. Without that the stored hash proved only that a render happened, which is
  not what `assets.build` claims and not enough to stand behind a purchased file that is
  re-rendered on demand.
- **Schema.** `Database.create_all()` creates missing tables *and* adds missing columns and
  indexes to existing ones, then returns what it changed so startup can audit it. Additive
  only — it refuses a NOT NULL column with no default rather than guessing a backfill.
- **Design fingerprints.** A slug and a version do not identify a design. Every key for
  design-derived work (`compile`, `certify`, the rebuild's re-draft) carries `CIR.fingerprint`,
  a content hash of the design, so the work re-runs exactly when the design changes. Without
  it a re-engineered product could never enter the chain, which is how two corrected designs
  sat in the repository while production kept serving the old ones.
- **Release hashes in the chain keys.** Every post-certification stage key carries the
  certified release hash, and `Listing.release_hash` records which release produced the
  listing, so the hourly rebuild can tell a stale listing from a current one even when the
  slug, the version and the chain version are all unchanged.
- **Chain version.** `runtime/release.CHAIN_VERSION` is stamped into every idempotency key
  after certification. Bump it whenever a stage that runs *after* `gate.certify` changes what
  it produces, or the upgrade will never reach products that already shipped. `chain.rebuild`
  runs hourly and restarts certified releases whose listing was not built by the current
  chain from the current release. Currently 6. It records *why* it judged each listing
  current or stale, and distinguishes a stale listing nobody has tried from one whose
  rebuild already ran and was refused downstream — because a rebuild cannot deliver a
  transition that a later stage refuses, and reporting the two identically is what hid a
  blocked product through three rebuilds.
- **Owner queue identity.** Each `OwnerRequest` carries the requirement key it belongs to,
  and `OwnerAction.requirement_key` stores it. The queue de-duplicates on that, not on the
  action's wording, because an action that derives a figure from the catalogue changes its
  text when the catalogue changes. A request whose figure moved is restated in the same row.
  `POST /api/launch-readiness` forces an assessment when waiting for the daily one would
  leave the owner reading a stale figure.
- **Build identity.** `/api/status` and `/health` report the commit the running image was
  built from. It is the only field that can tell whether a fix reached production: `version`
  is hand-maintained and proves nothing. An absent build variable reports `unknown` and
  never matches a commit, so "I cannot tell" is never reported as "the deploy landed".

- **Collapsed patterns and support.** The PDF may not print a line for row 97, but the
  compiled rows still contain it, and the concierge answers row questions from the compile
  result rather than the written text. A maker who asks about a row inside a repeat gets the
  right stitch count.

## Known refinements (tracked, not urgent)
- The suite is **~345 seconds** rather than twenty minutes, because `run_tests.sh` runs its
  files concurrently and schedules the six expensive ones first. Nothing about what the tests
  do changed: a lighter fixture for the tests that do not examine image content was the
  obvious move and is the wrong one, because rendering at a smaller scale is exactly how the
  blank hero passed locally while production was right to refuse it.
- **The suite is floor-limited by `test_product_run.py` (342s), and nothing else is worth
  optimising until that changes.** Measured, including a negative result worth keeping:
  sharing one cycle across the three read-only tests in `test_shadow.py` cut that file from
  245s to 121s and moved the whole suite's wall clock not at all (344s to 348s, noise),
  because the runner already overlapped the two files. Three of that file's tests drive the
  full eleven-product cycle; consolidating them or splitting the file would be the next
  lever, and it buys at most ninety seconds.
- Yardage constants are uncalibrated heuristics with a stated tolerance; physical tests
  replace them per yarn/hook. Never present an uncalibrated estimate as precise.
- Reverse compiler handles the writer's grammar plus common variants; widen coverage as real
  pattern styles appear.
- ~~Brand model imagery (section 6) raises a disclosure question.~~ **Decided 2026-09-18
  (B-097)**: a generated lifestyle image must be disclosed as an illustration wherever it
  appears, and may never be the hero. Set at full strength while nothing in the system
  generates one, and a test asserts the frame builder still produces none, so whoever changes
  that has to read the reasoning first.

## Next highest-value unblocked actions
1. An engineered amigurumi, when the radar selects one. The construction is now complete —
   geometry, seams, placement, stuffing and the size refusal — but on 2026-09-18 every one
   of the top fourteen concepts is Class A and the best amigurumi is Class B with a
   Christmas window that has not opened. Building one before the demand model asks is the
   same mistake as building to a hunch.
2. Shells, fans and granny clusters — stitches that work several times into one stitch.
   The catalogue does not need them today; a lace or granny-style product would.
3. Live-data halves of Pricing Intelligence, Thumbnail Warfare and Portfolio, which are built
   and correctly refuse to act without observations that do not exist yet.

Waiting on the owner rather than on us: a physical sample (the intake and calibration now
exist and are tested; the measurement does not), object storage, trademark clearance, and
the Etsy shop with its payout details. All seven are in the owner queue with costs and
timings, written there by the system rather than by hand.

## Changelog
- 2026-09-17: Initial build. Competition retired. CIR engine complete (27 tests).
- 2026-09-17: Platform layer — durable queue, agent governance, audit, spend caps, backup
  drill (14 tests). Gate D test caught a real bug: the spend guard raised inside its session,
  so the rollback discarded the `paused` flag and a breach would have refused one spend then
  accepted the next. Fixed: the pause commits before the raise.
- 2026-09-17: Release gates — asset truth, policy, certificate, incidents (27 tests).
- 2026-09-17: Shadow pipeline + worker/scheduler (8 tests). Two ordering bugs found and fixed:
  permission was checked *after* handler lookup (so an agent reaching for forbidden work that
  had no handler was recorded as "no handler" instead of denied), and a shadow-mode refusal
  was being retried with backoff against a mode that cannot change between attempts.
- 2026-09-17: Deployable surface (FastAPI admin/API, container, entrypoints), real-process
  persistence proof (5 tests) and the chaos suite (21 tests). Persistence testing exposed a
  race in its own harness — a three-second lease could expire during subprocess spawn — fixed
  by expiring leases deterministically in the database instead of sleeping on the wall clock.
- 2026-09-17: Market Radar (30 tests). Replaced the placeholder concept stubs with dated
  competitor intelligence and a 34-concept scored pool, and wired the section 33 portfolio
  selector into `radar.scan`. Three real bugs found while building it: the buy-window buffer
  was flat rather than proportional, so a 60-hour Christmas throw was scored as "too early"
  in September against direct evidence to the contrary; the constraint-repair loop could
  evict a quick low-price make to make room for a quick low-price make and spin forever; and
  the bundle was outranking everything in the pool while its members went unbuilt.
- 2026-09-17: Full shadow release chain on the flagship (26 tests) plus the deployment
  surface (8). Four real defects found and fixed while building it: the digital twin was using
  turning-chain units as physical row heights, overstating a blanket's finished length by
  half — a size claim, therefore a refund; the yardage constants were set by feel and came out
  at less than half of a checkable reference, which would have told a customer a throw needed
  190 m of yarn; support indexed row counts by row number into a zero-based list, so it
  confidently answered the wrong row; and the flagship's written instructions flattened every
  repeat across the full 144 stitches, producing a row instruction eleven lines long that no
  maker could follow.
- 2026-09-17: Model Gateway (21 tests). Prompts are immutable and content-hashed, output is
  parsed strictly, cost is recorded per agent so a runaway loop hits the daily ceiling rather
  than the bill, and a dead provider's circuit opens instead of absorbing doomed calls. Two
  standing constraints are now asserted rather than documented: no registered prompt may ask
  a model for pattern content, and `require_deterministic()` raises if a model verdict is
  offered where the compiler has one.
- 2026-09-17: **Deployed to Railway and verified in production.** Four real defects surfaced
  only by watching the deployed service, none of which any local test could have caught:
  the container hardcoded port 8000 so the health check probed nowhere; the embedded worker
  started a full planning cycle the instant the app came up and starved the health endpoint
  until the platform failed a working deployment; the operational heartbeat had been
  dead-lettering every fifteen minutes since the first boot because it was scheduled against
  an agent with no permission for it; and the fix for that never reached production, because
  agent seeding was insert-if-absent and the row already existed. A fifth appeared when a
  dated planning cycle ran two jobs instead of sixty: `plan.cycle` dropped `as_of`, so the
  run scored against today and collapsed into the morning's idempotency keys.
  Each fix carries a test: every cadence must be runnable by its agent, permissions reconcile
  on deploy, and a cycle's date must reach the radar.
- 2026-09-17: **Master Plan v1.2's commercial departments** (sections 6-12, 15, 16, 34).
  Brand system and Storefront Director; listing imagery as part of the release; Search
  Domination; Pricing Intelligence; AI Customer Experience; the content ecosystem; portfolio
  classification; separate confidence dimensions; regression capture closing Gate B; a motif
  library and sixteen generated designs; and the full P&L with a CFO challenge.
  Four real defects found while building: the thumbnail check counted non-background pixels,
  so a two-colour crochet fabric — half cream against a cream background — scored 9% and
  blocked six products for a problem none of them had; the fabric renderer coloured cells by
  their row's yarn, which in overlay mosaic is flat stripes and no motif at all; tag selection
  spent six of thirteen slots on the word "mosaic"; and the pipeline had been certifying a
  "Collection Bundle" whose PDF was a twelve-row striped panel — a product sold as three
  patterns and delivered as one invented swatch.
- 2026-09-17: **Row-level repeats** (20 tests). Written patterns collapse a repeated row
  block into an instruction: the flagship prints 48 rows instead of 120. The cycle is derived
  from the compiled rows, not declared, so no field can disagree with them; the reverse
  compiler parses and expands the instruction from the customer text alone, so the two halves
  stay independent. It also exposed a claim the copy had been making for two deploys — "a
  stitch count on every single row", in the description and in listing frame 2 — which stops
  being true the moment the document collapses rows 49-120 into one sentence. The claim is now
  derived from the document. `CHAIN_VERSION` bumped to 4 so both reach products already
  certified.
- 2026-09-17: **Construction beyond flat rows.** Round-worked geometry as a surface of
  revolution; honest finished sizes for discs, tubes, cones and vessels, and an explicit
  refusal for closed shaped pieces; gathering named; corners derived from stitch positions;
  round charts; the finishing in the CIR with seams checked both ways; row colours named in
  written instructions; and the join-or-spiral instruction stated and verified.
  It also exposed four real defects, two of them already in production as drafted listings:
  "Market Basket Trio" was one flat rectangle with no seaming instruction and "Hexagon
  Coaster Set" was a rectangle — both are now worked in the round and both are blocked by a
  new name-versus-shape check if they ever regress; a size claim the twin could not check was
  being passed rather than refused; and the entire catalogue's written instructions omitted
  which yarn each row uses, so a two-colour mosaic was workable only from the chart.
  `CHAIN_VERSION` 5 plus a new `DOC_VERSION`, and re-certification now replaces the stored
  certificate rather than skipping it — the fourth appearance of "code changed, the deployed
  database did not".
- 2026-09-17: **Launch readiness and the owner queue.** What stands between this shop and a
  live customer, computed from the database and split by who can actually clear it. The
  remaining blockers are now genuinely the owner's — an Etsy shop with identity
  verification, a payout account, acceptance of Etsy's listing fees, one physical sample,
  a decision on trademark clearance, object storage, and the phase itself — so for the first
  time the system writes its own owner queue rather than a human writing one for it.
- 2026-09-17: **Design fingerprints in the idempotency keys.** Found by watching production
  accept the round-worked rebuild and keep serving the old designs: `cir.draft` was keyed
  once per slug, forever, so a re-engineered product could not re-enter the chain and the
  `DOC_VERSION` bump could not reach the stage it existed for. Keys now carry the design's
  content hash, and the hourly rebuild compares the stored design against the one the code
  produces.
- 2026-09-17: **The post-certification chain keyed on the release.** The same collision one
  stage lower, found in production ten minutes after the previous fix: re-certification
  produced a new release hash and then found every downstream key already taken, so two
  corrected designs certified while their old listings stayed exactly as they were. Listings
  now record the release that produced them.
- 2026-09-18: **Build 1 accepted as complete and checkpointed.** Tagged locally as `build-1`
  at `d5168c0` and pushed as the branch `build-1-baseline`, because this environment's git
  transport rejects tag pushes while accepting branches — recorded rather than worked around
  silently. `baseline/` holds the recovery manifest, the schema snapshot (21 tables, 201
  columns, hashed) and a read-only capture of the production evidence. Recoverability is
  proved rather than asserted: the suite was re-run from a clean worktree checked out at the
  baseline commit. The manifest is explicit that the production database is **not** backed up
  here and cannot be from this environment, and which of its contents are re-derivable from
  code and which are not.
- 2026-09-18 08:14Z heartbeat: production verified 12/12 before and after; radar re-asked
  for today and it still selects nothing unbuilt, so B-079 holds and no product work was
  invented to fill the time. Three defects closed instead — the section 6 disclosure rule,
  the severity comparison that disarmed three gates, and the verify window that called a
  starting worker dead. Chain 7, 541 passing, 0 failing.
- 2026-09-18: **Every deploy opened a 90-second window where `/api/verify` lied.** Caught
  by the heartbeat itself: verify reported the worker dead and the scheduler silent, and the
  worker was fine — it had started 85 seconds earlier, and the first tick lands at 25s of
  start delay plus a 60s scheduler interval. A runner that has started and not yet ticked now
  reads as *starting*, for a grace derived from those two knobs rather than hardcoded, and
  the check's evidence says `starting: true` so it is never silently passing. The grace
  expires: a worker ten minutes silent still reads as dead, and so does one that ticked and
  stopped. That matters because the operator loop treats a failing check as the highest-value
  work, so a recurring false alarm costs a whole session.
- 2026-09-18: **A gate that could not block, found by writing a different test.** The
  section 6 disclosure question was open, so it was closed (B-097). Writing its tests turned
  up something worse: `ERROR` is the string `"ERROR"`, and three places filtered findings
  with `f.severity == "error"` — lowercase, false by construction. Asset Truth could not stop
  a listing image, the policy gate could not stop listing copy, and the confidence profile
  counted zero asset errors however many there were. All three gates ran, produced entirely
  correct findings, and had them dropped on the floor. Callers now ask `finding.is_error`.
  Checked across all seventeen designs before claiming anything: the defect was **latent** —
  nothing in the catalogue had tripped the gate, so it disarmed a guard rather than shipping
  untruthful imagery — and the chain is bumped to 7 so production re-derives that under the
  fixed gate instead of it being taken on trust.
- 2026-09-18: **One shadow cycle instead of four, and an honest negative result.** Four of
  the nine tests in `test_shadow.py` were 60 seconds each, three of them asserting different
  things about an identical eleven-product run, so the file paid three times for one piece of
  evidence. It now builds the cycle once: 245s to 121s, all ten tests passing. It did *not*
  make the suite faster -- 344s to 348s, noise -- because the runner already overlapped that
  file with the longer one. Kept anyway, because it frees a core for two minutes and because
  the file now says what it actually proves; recorded as a negative result so the next
  session does not repeat the experiment. The shared cycle is fingerprinted and re-checked
  before every use, and a test fires that guard rather than trusting a comment.
- 2026-09-18: **The suite is ~345 seconds instead of nineteen minutes.** Measured before
  changing anything: six of the twenty-six files were 97% of the 1133 seconds, each driving
  the full eleven-product pipeline with 2000-pixel rendering. The files were already
  independent processes with their own temporary databases and were simply queued one behind
  another, so they now run concurrently, the expensive six first, and print back in the
  canonical order -- an identical log, an identical 532 passing, and no test made cheaper or
  less representative. The tempting alternative was a smaller render for tests that do not
  examine the image, which is precisely how the blank hero passed locally while production
  refused it.
- 2026-09-18: **The migration path for the queue, and a way to run an assessment now.**
  Keying the queue on the requirement was only half the fix: pre-upgrade rows were matched
  on their full action text, which adopts every action whose wording is unchanged and fails
  for the only one that had changed. Production was holding exactly that row, so the fee
  approval would have been left keyless with a second row added beside it. A keyless row is
  adopted by its opening clause instead, which no derived figure reaches, and two tests
  assert the clauses are distinct and stable. Verified in production: seven actions before,
  seven after, `owner_actions_added: 0`, `owner_actions_restated: ["listing_fees"]`, and the
  queue now reads US$3.20 / CA$4.48 for the 16 listings that exist. Delivering it also
  needed `POST /api/launch-readiness`, because the assessment runs daily and the corrected
  figure would otherwise have sat undeliverable until midnight — the same argument as
  `/api/chain-rebuild`, and GREEN for the same reasons.
- 2026-09-18: **The owner queue keyed on prose.** Deriving the fee figure from the
  catalogue broke `test_deploy` on the next run: the queue de-duplicated open owner actions
  by comparing their text, which worked only while every action was a frozen string, so a
  changed number read as a new request and the owner would have seen eight entries for
  seven decisions -- two of them asking approval for different amounts for the same thing.
  Each request now carries its requirement key as its identity, and an action whose figure
  moved is restated in the same row rather than added beside itself. Actions queued before
  the column existed still match on text, so the upgrade does not re-queue what the owner is
  already looking at.
- 2026-09-18: **The one number the system asked for was hardcoded.** The owner action
  approving Etsy's listing fees read "about US$1.80 (CA$2.50) for nine listings" -- true
  when written, still shown after the catalogue reached sixteen, and sitting directly beside
  an evidence field that computed CA$4.48 from the real count. Everywhere else a claim is
  derived and checked; the place a figure is *asked for* is the last place a stale one
  belongs, because the approval is the figure. Derived now, with a test that the sentence
  and the evidence agree to the cent and another that refuses the old wording if it returns.
- 2026-09-18: **Charts that can be read without colour vision** (section 31). Twelve of
  the nineteen designs are two-colour work where the colour *is* the motif, the chart
  separated the yarns by hue alone, and the legend identified each yarn by a coloured square
  and nothing else -- so for a maker with a colour vision deficiency there was nothing in
  the file that said which yarn a square meant, and unlike a sighted maker they cannot
  recover it by looking harder. Every square of a multi-colour chart now carries its yarn's
  letter, in the corner so the stitch glyph still reads; the round chart puts it on the
  round number; the legend prints it inside the swatch and explains it; and a chart drawn
  too small to carry one blocks the frame plan instead of shipping. The letter indexes the
  CIR's own colour order, so the chart, the legend and the written instructions cannot
  disagree. `tests/test_accessibility.py` holds it to a property rather than an appearance:
  two yarns are given the *same* hex, and the squares must still differ.
- 2026-09-18: **Chain version 6, and the reason a refused rebuild looked untried.** The
  imagery fix changed what `assets.build` produces, which is exactly what `CHAIN_VERSION`
  exists for -- shipping it without the bump left every asset rendered by the old code in
  place and the blocked product unreachable. Diagnosing that needed the jobs list *and* the
  audit detail cross-referenced, because the rebuild had detected the cable throw as stale,
  enqueued the work, watched `assets.build` refuse it for blocked imagery (correctly), and
  then reported the same stale line on every later run while enqueueing nothing: the listing
  stayed stale, so the transition, the token and the key stayed the same. The record now
  says which of the two it is looking at. The rebuild still cannot fix it -- only changed
  code can, arriving as the bump -- but the difference is visible from outside the process,
  which is what B-073 was for.
- 2026-09-18: **Production says which commit it is running.** `/api/status` and `/health` now
  report the build's commit sha, branch, and whether it knows them at all. `version` is
  hand-maintained and proves nothing about a deploy, so until now the only way to tell
  whether a fix had landed was to look for its effects and hope no other change explained
  them -- which is how each of the three idempotency layers cost a diagnosis round to "the
  code is fixed and production disagrees". An absent build variable reports `unknown` and
  never matches a commit, because a check that treats "I cannot tell" as "yes" is worse than
  no check.
- 2026-09-18: **Three imagery defects, found by looking at what production actually
  rendered.** The cable throw's hero was a blank cream rectangle. Three separate causes, each
  of which alone would have shipped an unsellable listing: the container had no fonts, so
  Pillow fell back silently to a bitmap face a few pixels tall on every image the system has
  ever rendered in production; the fabric renderer coloured cells only by colourway, so a
  deliberately single-colour textured design had nothing to show; and my own frame-level
  thumbnail check passed the blank hero at 78% coverage because it was measuring the title
  text, while production blocked the same product at 11%. Fixed in all three places — the
  Dockerfile installs the fonts, cells are shaded by their stitch's relief (on the overhang
  pass too, which was erasing it), and a hero whose fabric has no internal contrast is
  refused. A check that can pass an empty image is worse than no check, because it is
  evidence.
- 2026-09-18: **Reproducible PDFs.** Two renders of one certified release, three minutes
  apart in production, were audited under two different hashes: reportlab stamps the time and
  a random id into every render. Since artifact bytes are not durable, a purchased file is
  re-rendered on demand, so the hash has to identify the file rather than the occasion.
- 2026-09-18: **Texture, and the third face of the naming defect.** Three products were
  named for techniques their patterns could not contain — a cable throw with no crossing, a
  bobble pillow with no bobble, a ribbed scarf with no rib — all plain sc/dc colourwork, one
  of them fourth in the selected portfolio with a certificate and a drafted listing in
  production. Nothing could see it: the shape check looks at silhouettes and Asset Truth at
  what images depict, and those patterns were internally perfect. Post stitches, bobbles and
  cable crossings are now in the taxonomy with real yarn costs and chart glyphs, the three
  products are rebuilt to do what they say, and a name claiming a technique the fabric does
  not work is refused at certification.
- 2026-09-18: **Placement in the finishing.** A seam now says where on the piece it
  happens — which rounds, how far either side of centre, and whether the second one mirrors
  — because knowing that the ear attaches to the head does not make a toy. It is validated
  against the piece it attaches to (a join at round 40 of a seven-round head, or two ears
  that would overlap, are errors every other check would pass), written into the document
  and read back independently. A multi-piece join with no placement is reported rather than
  allowed through: an unspecified assembly step is the "beauty image, guess the
  instructions" failure arriving through the back door.
- 2026-09-17: **The Etsy publishing path, written before it can publish.** A v3
  draft-listing client behind three ordered refusals — phase, then the owner's authority,
  then credentials — with a mapper that refuses rather than truncates and an honest outcome
  for "listing created, file not attached". `store.publish` asks it past shadow mode, so the
  phase is now the first of four conditions rather than the only one. Unit-tested against a
  fake transport that counts its calls; never called against Etsy, because nothing in this
  environment can satisfy the other three conditions. The multipart file upload is the one
  part that cannot be verified without a live call, and the interface says so.
- 2026-09-17: **Physical test intake and calibration**, plus the third layer of the rebuild
  bug. A real sample now has somewhere to land: it calibrates the yardage for its own yarn
  and stitch, and a finished size that disagrees with the claim raises a defect instead of
  being absorbed into the factor. The rebuild also needed the trigger in its keys — keying
  on the product, the code version and the certified release still left every downstream key
  taken, so a rebuild could detect staleness and do nothing about it, which it did three
  times while two products sat visibly wrong in production. It now records the comparison it
  made for every listing.
- Totals: 541 tests passing, 0 failing. All six acceptance gates pass, each line with its own
  named test. Gates A, C, D, E, F passing; B passing except
  regression automation.
