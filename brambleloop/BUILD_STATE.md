# BUILD_STATE

_Updated 2026-09-20 by the Brambleloop build session. Maintained continuously so any future
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
| covered | 221 | satisfied, with a named test or artefact |
| partial | 43 | something real exists and is short of the requirement |
| missing | 0 | nobody has built it |
| owner_gated | 36 | waits on an owner decision, credential or legal acceptance |
| data_gated | 20 | waits on market evidence that does not exist yet in shadow mode |

Five values rather than two on purpose: "done / not done" is what makes a large build
dishonest, because a requirement waiting on an Etsy shop is not the same kind of unfinished
as one nobody has written. **43 requirements are executable** (partial +
missing); the counts above move as work lands and are regenerated from the registry, never
typed. 221 of 320 covered is **69.1% complete**, read from the registry rather than
estimated.

Seven of those moved out of `partial` this session without being built, and that is a claim
worth being precise about: they were re-audited, not finished. #39's retrieval half is
refused 403 by Etsy's bot protection, verified by request rather than assumed; #94, #104 and
#299 need a model or a credential to make the next measurement at all; #132 and #296 need
customers; #51's remaining half needs storage outside this provider. Each now names a gate
whose condition code can test, which is the only form of parking this build accepts. The
executable number went down because it was wrong, not because the work went away.

Build 1 remains recoverable throughout: baseline commit `d5168c0`, branch `build-1-baseline`.

## Current phase
PHASE 1 — SHADOW MODE, **deployed and running 24/7**. Nothing is connected to live customers,
live listings or live spend. The system runs unattended on Railway whether or not any Claude
session is open.

**`/api/verify` reports `ok: true` in production as of 2026-09-19T16:40Z — 12 of 12
checks passing**, against live state rather than only in tests. Also verified in production
on this deploy rather than asserted:

- **A real model call succeeded** (15:31Z, 14 tokens in, 4 out, CA$0.0000466). Month-to-date
  model spend CA$0.000047 against a CA$25 ceiling enforced before each request.
- **The continuity archive is retained**: archive 1 holds 5,299 rows across 41 tables,
  6.26 MB compressed to 604 KB. It survives a container replacement and a redeploy, and not
  the loss of the provider — which is the half still parked on `offsite_storage`.
- **The operator credential is configured** (Railway-side, never in this repository), so
  `GET /api/continuity/export` is reachable by the owner and `POST /api/queue/requeue` can
  re-drive a dead letter whose defect has been fixed. Both were closed-by-default before,
  which was the safe direction and also meant the export nobody could download.

Live: https://brambleloop-os-production.up.railway.app — dashboard `/`, health `/health`,
status `/api/status`, **verification `/api/verify`**.

## OWNER ACTIONS — now the only remaining lever

**Correction, same day.** An earlier version of this section said the build queue was empty
at 0 READY. That number was computed in a session container with no Etsy key, no model key
and no browser URL, so more gates were shut there than in production — where `/api/build`
showed one ready requirement, #268, un-parked automatically because `benchmark_observation`
is open there. The executor was right in both places; reporting one environment's answer as
the build's was not. Gate conditions are environment-dependent by design, which makes *where
a count was taken* part of the count (B-481).

**The gates themselves then changed, and that is the larger finding.** `browser_vision` named
two capabilities — "rendered-page and image evidence" — and held twenty-eight requirements
behind the more expensive of them. Ten needed no browser: the sanctioned Etsy endpoint
`listing_images` has been returning every gallery image's URL since the credential was proven
on 2026-09-19, and the model that can look at those URLs was credentialed the same day. What
stood in the way was that nobody had written the call. It is written now
(`gateway.anthropic.see`, `intel.vision.analyse`), and the gate is split (B-478).

Three gates also opened on environment variables — a browser URL, an image key, an archive
URL — holding thirty-nine requirements behind conditions a person could satisfy by typing, in
the one module whose purpose is that the queue cannot overstate itself. All three are now
recorded successful uses, and a test asserts the property over every gate in the table rather
than over those three (B-479).

**Two of those gates then opened, and the work behind them was done.** Verified live at
2026-09-20T20:00Z: `image_vision` opened on a real MJs gallery image judged a photograph, and
`culture_feed` on 28 days of Wikimedia pageviews. Production's queue went 0 → 13 READY, and
those thirteen are now closed: the gallery-analysis loop and its consumers (#209, #304, #303,
#208, #210, #211), the culture radar with a source, discovery and domain filing (#133), the
findings routed into the improvement system (#147), the visual semantic and physical-realism
checks that were named and never made (#61, #79), and the construction-evidence
decomposition (#116, #278). #140 moved to `data_gated`: both series exist, and the
marketplace one needs listings discovered over time rather than a catalogue observed in one
pass.

Where the 79 parked requirements wait, read from production 2026-09-21T02:10Z:

| gate | parked | what opens it | cost |
|---|---|---|---|
| `customers` | 21 | a real customer, which is the phase decision | the phase decision |
| `rendered_pages` | 20 | a browser worker that actually fetched an Etsy page | **recommended against** |
| `image_generation` | 12 | one image actually generated by a reference-conditioning provider | ~CA$18.55 benchmark, then ~CA$3.40/mo |
| `owned_surfaces` | 7 | a list, a blog or a social account that exists | the phase decision |
| `live_listings` | 6 | a published listing | the phase decision |
| `ad_authority` | 6 | paid-media authority | the owner's, later |
| `benchmark_purchases` | 4 | one purchased benchmark pattern row | CA$292 approved, see below |
| `physical_proof` | 1 | one completed PhysicalTest, by whoever the protocol says | protocol pending |
| `tester_roster` | 1 | one person who has agreed to test a pattern | outreach |
| `offsite_storage` | 1 | a continuity archive actually written outside this provider | ~CA$1/mo bucket |

**Seventeen of the seventy-nine are behind the three gates the owner is currently
progressing.** The other sixty-two are behind going live, behind paid media, or behind the
browser worker this build recommended against buying.

### Spend policy, as of 2026-09-20

**QUALITY FIRST. COST SECOND. WASTE NEVER.** The owner raised the combined model, vision and
image ceiling from CA$25 to **CA$100 a month** and reversed the argument that went with it:
"the cheaper option is adequate" is no longer a reason, and "the better option costs several
times more" is no longer an objection when the improvement is commercially meaningful. The
ceiling is an authority rather than a target; the expectation is that most months cost far
less. Infrastructure keeps its separate CA$20 ceiling.

The policy lives in `finance/spend_policy.py` as code, with the owner's six priorities and,
beside each, what may not be traded away for money. `/api/spend-policy` reads it;
`/api/spend-report` says what the month bought by provider, model, agent, department, product
and purpose, with the pre-call reservation beside the bill (B-513, B-517).

**What the reconciliation found.** Three things had drifted while nobody was arguing about
them: the ceiling was written in two modules *and* hardcoded into a `/api/verify` assertion,
so carrying out the owner's decision would have turned a safety check red (B-514); four
vision call sites bypassed `routing.TASKS` entirely, running MJs gallery analysis on the
cheapest tier while the table declared standard — on the owner's second-highest spending
priority, for a day (B-515); and two cadence intervals were set by the old ceiling rather
than by the work (B-516). Gallery analysis is now 25 images every two hours on the standard
tier: the benchmark's visual evidence closes in four days rather than nineteen.

**Measured on the first run under the new accounting, not estimated:** CA$0.029 an image, so
about CA$8.70 a day while the backlog drains and CA$33 to finish it. The same run corrected
the image-token estimate for the third time — 800, then 2,000, now **6,000** from the actual
bill, having been under the truth twice in the direction that turns a ceiling into a
suggestion (B-521). Gallery analysis is capped at 40% of the month, and the cap is about
priority order rather than thrift: a four-day backlog must not consume the ceiling and leave
concept generation, the owner's first priority, refused (B-522).

Purchasing benchmark patterns and authorising advertising remain consequential spend and stay
the owner's.

### The owner's 2026-09-20 approvals, answered

**1. Browser worker — recommend not buying one yet.** The minimum architecture question turned
out to be upstream of the cost question. Half of what the old gate held needed no browser at
all and is done. The other half reads Marketplace Insights, search results and platform
policy, and those sit behind an edge that deliberately refuses automated clients: re-confirmed
today, `robots.txt` answers 200 and `/legal/terms` answers 403 to a client identifying itself
honestly. B-268 already decided that getting past it by pretending to be a browser is evasion,
and doing that to a marketplace this company intends to sell on trades a small convenience for
the relationship. So: a Playwright worker inside the existing Railway project would cost about
**CA$1–3/month** (inside the ceiling) and would most likely return 403s; a hosted browser API
is **US$50+/month** and buys the same 403 more expensively. The client and its probe are built
and committed, so the day access exists the capability is one variable away. **No service has
been provisioned and no spend incurred.** (B-500)

**2. Image generation — measured, not recommended. Superseded by the owner's quality-first
decision.** There was a recommendation here: FLUX 2 Pro, on the grounds that it was the
cheapest candidate supporting reference conditioning. The owner replaced that instruction on
the same day — do not lock a provider because it is inexpensive — and the recommendation is
deleted rather than defended, because a named winner beside an unrun benchmark is the price
list deciding again with a second opinion for cover (B-502).

`gateway/image_bench.py` decides it instead: six trials this catalogue genuinely needs
rendered (stitch truth, hero comprehension, thumbnail strength, premium lifestyle, the
canonical model brief, an anti-drift repeat against a reference), **five samples each**, on
every model that can hold an identity at all — **120 images, CA$6.19** of the owner's CA$25
benchmark budget. Judged blind by the vision capability against a rubric whose every line
cites its requirement. **Imagen 4 Ultra is excluded before the benchmark, on a requirement
rather than a score**: the best published photorealism of the field and no reference
conditioning, so #200 is unmeetable by it at any quality (B-503).

The whole monthly spread across the four eligible models is **CA$2.19 – CA$6.90**, which is
not an amount a catalogue decision should turn on; a test fails if that spread ever grows
enough to make cost a real argument. **Nothing is chosen and nothing can be until an account
exists** — creating one needs a payment method and an identity this build may not supply, so
the measurement is the owner action. `/api/image-benchmark`.

**3. Cultural signal source — done, CA$0.** Wikimedia Pageviews: official, free, keyless,
sanctioned within its documented terms with an identifying user agent. Verified live
2026-09-20T20:00Z. It measures *reference reading*, not search volume and not purchase intent,
and is labelled `reference` for that reason — #140 measures the gap between that and
marketplace demand, so a feed that measured the same thing would have nothing to say (B-483).

**4. Benchmark set — thirteen approved to CA$300; the list is at
`/api/benchmark-selection?target=13`.** Thirteen purchases total **CA$268** and cover every
facet the observed catalogue varies along; ten would total CA$212 and leave `stockings`,
`seasonal_gift` and `unclassified` unbought — the first two being the departments this
campaign window is aimed at, which is why the CA$56 margin is worth paying (B-501). Each pick
now carries **the runner-up it beat, what that alternative would have taught instead, and the
extra the winner adds**; the set carries how many of the 438 observed listings it makes
redundant, which is the number that answers "are we buying thirteen similar things" (B-507).
The selection is deterministic, so it is reviewed rather than trusted. Files land in the
quarantined library, which refuses every reader that is not an analyst and stores no
competitor text in any table.

**5. Physical sample — parked, and the gate no longer asks the owner to crochet.** Its
description said "needs somebody to crochet a Brambleloop sample", which put the owner's hands
in a gate and so into the action list. The condition is unchanged: one completed PhysicalTest.
Who performs it is a question for the revised risk-based protocol (B-486).

**6. Etsy #268 — closed as an owner item; recorded `data_gated`.** The sanctioned read
capability is the applicable evidence and is not requested again (B-508).

**6a. (context)** Nothing sanctioned is missing. The credential is proven and has been since
2026-09-19; it read the 438 listings the whole mission runs on. #268 was parked on
`benchmark_observation`, which that credential *is*, so it was parked behind a condition
already true. What it needs is a second benchmark shop **outside the United States** — one
shop's term frequencies are one market's language however many listings they came from. That
is a choice of shop, on the credential that already exists: no new capability, no spend, and
nothing for the owner to repeat (B-482).

Listed below in the Execution Directive's format; the live queue is `/api/launch`.

**~~Add credit to the Anthropic account the API key belongs to.~~ DONE 2026-09-19.** Credit
arrived and a real call succeeded in production at 15:31Z; the gate opened by itself and the
four requirements un-parked. Kept here with its original wording because an owner-action list
that deletes what was done stops being a record of what this company asked for.
- *Exact action:* open the Anthropic console's billing page and add credit. The smallest
  top-up is enough.
- *Why:* the key supplied on 2026-09-19 authenticates, and the first request it made returned
  `Your credit balance is too low to access the Anthropic API`. Nothing in this build treats
  the provider as available until a real call succeeds, so four requirements (#94, #104,
  #177, #178) are parked on it.
- *Maximum cost:* CA$25/month, enforced in code before every call, not by intention.
- *Minutes:* about 3.
- *Consequence of waiting:* those four requirements stay parked. No other Build-2 work is
  affected, and the gate opens by itself within six hours of credit arriving — the probe
  cadence does not need to be told.

**Separately, and not a build item:** the key was pasted into this session in plaintext and
in a screenshot. It is stored only as a Railway variable and appears nowhere in this
repository, but a key that has travelled through a chat transcript should be rotated once the
build no longer needs this one. The owner has said a replacement is coming.

## Canonical specification
`brambleloop/spec/01_Brambleloop_Master_Plan_v1.2.pdf` (vendored copy of the owner's handoff).
Treat v1.2 as canonical. Improvements become v1.3+ with a preserved changelog — do not
scatter canonical strategy across chat.

## Honest status — what actually exists
Measured by `./run_tests.sh` on commit `8afbdc4`: **2,667 tests passing, 0
failing** across 146 suites, including 23 that assert the owner's acceptance gates line by line. Measured, not
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
**2026-09-21 — #198 answered, the identity made whole-person, the tournament built, and the
MJs purchase stopped.**

### OWNER ACTION REQUIRED — do not buy the MJs set yet

`/api/teardown/readiness` reports **NOT READY**, checked from evidence rather than from a
list: a PDF reader is importable and **nothing uses it**, and `library.retrieve` — the
quarantine's only sanctioned reader — **is called by nothing at all**. The purchase would
land, be filed, be hashed, be manifested, have its filenames audited against the listing's
promises, and then sit there. Every downstream capability the owner listed — materials, yarn,
hook, gauge, sizing, construction, shaping, assembly, charts, troubleshooting, the
cross-reference against what the listing advertised — is a schedule waiting on observations
nothing produces. **The gap is a module, not a dependency** (B-560).

Ready: listing imagery, listing promises, provenance. Missing: PDF ingestion, pattern
analysis, promise cross-reference against the instructions, construction-to-object.

### #198 — answered, and recorded as code

`visual/brief.py` holds the direction in the owner's own phrasing. Two prohibitions sit apart
from taste: **no photograph of a real identifiable person** is used as a reference or
conditioning source, and no candidate that reads as a recognisable public figure is accepted.
The direction arrived beside a photograph of a public figure; it was not used. A persistent
commercial brand identity built from somebody's photograph is that person's likeness in
commercial use, and it is the celebrity resemblance the direction rules out in the same
breath (B-558).

### The body-drift failure is fixed

The canonical identity is now **the entire woman**. The pack pins stature, build, shoulders,
torso, bust, waist, hips and limbs alongside the face. `drift_check` returns **two group
verdicts that never average into one another** — a blended score is precisely how a good face
waves a different body through. A dimension is three-valued: match, drift, or **unmeasurable**
when clothing, pose or crop genuinely hides it; a group with fewer than three readable
dimensions is `unverifiable` rather than passing (B-557).

### The tournament (#199) is built and contains no way to choose

Twenty-four seed notes varying hair, colouring, stature and figure from one shared base
prompt. Screen on the owner's ten criteria; a candidate reading as a public figure leaves on
the rule, not the score. Five finalists stress-tested across five materially different scenes
— neutral, fitted garment, loose layered garment, winter, non-garment — each conditioned on
the finalist's own portrait, which is the mechanism the canonical identity will use. There is
no `select_canonical` anywhere in the module and a test reads the source to keep it that way
(B-559). It opens an owner action when it completes.

Suite green at **2,783 across 152 suites**. `/api/verify` 12/12.

## Previously — last completed milestone
**Heartbeat 2026-09-21T08:15Z — the identity gate had no callers.**

`visual/identity.py` was complete, correct and **invoked by nothing anywhere in the
codebase**. A grep for every one of its functions returned nothing outside the module. It
would have gone on being right and unconsulted while the first model-bearing listing shipped
past it — which is exactly the case #201 exists for.

Two joins were missing and only those two were built (B-555):

- **Persistence** — `model_identities` holds candidates and the frozen pack, because a pack
  held in memory is gone after the next deploy, and a canonical model who disappears on a
  redeploy is not locked to anything. `select_canonical` still refuses without the owner, and
  refuses a second selection as the redesign it is.
- **The release join** — `model_registry.gate_frames` is called from the listing-image build
  and its verdict is in `blocking`. With no canonical pack, every model-bearing frame is
  blocked. That is correct rather than inconvenient: unverifiable is not a pass. Frames
  carrying no model are not examined at all, so today's product-only catalogue is untouched
  and the gate bites on the day the first model frame is built.

`#200 Permanent Identity Lock` and `#201 Model Anti-Drift Release Gate` are the two `partial`
requirements this closes. `/api/model-identity` reports the state from rows.

**And four notes had gone stale the moment the capability arrived.** #200 said "no candidate
has been generated, because that needs the image capability" — it does not any more, and the
honest blocker is now a different one: #198, the owner's aesthetic direction, without which
#199's tournament is meaningless and generating faces would only invite the first of them to
become canonical by being first. #200 and #201 are `owner_gated` now rather than `partial`.
#292 and #300 parked their imagery halves on the same capability and are **unblocked and
unbuilt**, which is a different state from parked and is now recorded as one (B-556).

The registry's own validator caught the incomplete half of that edit: an owner-gated
requirement has no remaining work for `parked_on` to describe, and both rows still carried
`image_generation`. A guard that refuses an incoherent registry is worth more than the edit
it refused.

Suite green at **2,755 across 150 suites**. `/api/verify` 12/12.

## Previously — last completed milestone
**2026-09-21T07:00Z — the image gate opened on demonstrated capability, twelve requirements
unparked, and both reachable candidates are measured.**

### The benchmark, measured

| model | overall | fabric (floor 2.5) | identity (floor 3.0) | repeatability | median latency |
|---|---|---|---|---|---|
| `gpt-image-2` | **3.570** | 3.187 ✅ | **3.0 ✅** | 0.948 | 14.6 s |
| `flux-2-pro` | 3.467 | 3.013 ✅ | **0.8 ❌** | 0.937 | 9.7 s |

Both on complete thirty-sample schedules. **GPT Image 2 leads and nothing is locked** —
Google remains an eligible unmeasured candidate, and a leader chosen over candidates nobody
could render is a shortlist of one.

The benchmark earned its cost here: FLUX's `image_prompt` conditioning does not hold a face
across a regeneration. No amount of reading a pricing page would have found that, and an
identity that does not survive a regeneration produces a catalogue that drifts into somebody
else by February. Quality decided before any tie-break was consulted (B-554).

Unmeasured, with reasons: `nano-banana-2` — Google project denied access, caught by the
two-image reference probe rather than by a thirty-sample schedule; `seedream-v5-lite` — no
credential, and Volcano Engine is not practically reachable from Canada.

### Spend

**Benchmark, cumulative lifetime: CA$34.43 of the CA$50 the owner authorized** (inclusive of
every prior run, including the invalidated ones). **Month-to-date model spend: CA$33.85 of
CA$100.** The two figures overlap because the blind judging bills through the model gateway.

### The gate opened on evidence

`image_generation` was missing from `ops.capability_probes` entirely, so a capability that had
been rendering for hours was recorded nowhere and twelve requirements sat parked on the
absence of a row nobody was writing. The probe now runs in that job and also on deploy when a
credential is unproven. Verified live: probe ok, provider `flux-2-pro`, `usable: true`, and
the executor went **0 READY → 12 READY, 79 parked → 67**.

Of the twelve, **eight are `owner_gated` by their own definition** — led by **#198, the
canonical model's aesthetic direction**, which is the owner's to give and which #199's
candidate tournament depends on. Four are `partial` and are the autonomous loop's.

## Previously — last completed milestone
**2026-09-21T05:15Z — the benchmark ran for real, spent past its budget, and every defect
it found was in the benchmark. It is stopped at the ceiling and the overrun is recorded.**

### OWNER ACTION REQUIRED — benchmark budget

| | |
|---|---|
| **Action** | Decide whether to raise the image-provider benchmark budget above CA$25, or stop and choose from what has been measured |
| **Why** | The benchmark has spent **CA$31** of an approved **CA$25** and has one of two reachable candidates measured |
| **What the overrun bought** | Nothing. It went to defects in the benchmark itself, all now fixed |
| **Maximum cost** | ~CA$10 to finish GPT Image 2's schedule |
| **Minutes** | 2 |
| **Consequence of waiting** | The provider choice stays unmade and the twelve requirements behind `image_generation` stay parked |

The job now refuses to start once the cumulative total is reached and raises this itself.
Two things let an approved figure become CA$31 without anyone crossing a visible line: the
ceiling was applied per run, so four runs each stayed inside a number approved once; and
`spent_to_date` counted only the renders while the blind judging — the larger half — bills
through the model gateway, so it reported CA$7 against a real CA$31 (B-550).

### Verification of the three credentials

| Provider | Verified | Evidence |
|---|---|---|
| **BFL FLUX 2 Pro** | **yes** | real renders, reference conditioning proven |
| **OpenAI GPT Image 2** | **yes** | real renders, identity lock held across a regeneration |
| **Google Nano Banana 2** | **no** | key authenticates and lists models; every `generateContent` call, text and image, returns 403 "Your project has been denied access" |

All three are installed as Railway service variables and appear nowhere else: a grep of the
working tree for each finds zero occurrences.

### What the benchmark measured

`flux-2-pro`, complete 30-sample schedule: overall **3.467**, fabric **3.013**, identity
match **0.8**. It clears the fabric floor of 2.5 and fails the identity floor of 3.0.
`gpt-image-2` has not completed a schedule. **No winner is locked, and none should be** — a
leader chosen over candidates nobody could render is a shortlist of one.

### Every defect the run found, all in the benchmark

- **The identity floor was unpassable by construction** — the drift trial ran with no
  reference image and the judge was shown one picture while being asked whether two people
  matched (B-542).
- **OpenAI conditions through `/v1/images/edits`**, multipart, not a field on
  `/v1/images/generations` (B-545).
- **Black Forest Labs needed base64**, and was handed the local filesystem path of the
  canonical render (B-547).
- **A partial schedule was stored and reused**, ranking one model on sixteen samples against
  another's thirty (B-543).
- **The follow-up job could not stop** — progress was read from the run's results while
  storage required a complete schedule, so it re-queued itself every few minutes at about
  CA$1.85 a time (B-546).
- **`JUDGE_MAX_TOKENS` was 500** and the rubric outgrew it, so sixteen of thirty samples died
  to a truncated JSON answer rather than to a model (B-548).
- **The live ceiling variable still said CA$25**, five days after the owner raised it to
  CA$100 (B-548).
- **Two working providers could not open the image gate**, because the probe resolved its
  provider through a variable nobody had set (B-549).

**The identity lock then held.** The canonical model rendered through GPT Image 2, and a
second image conditioned on her — different garment, different season, same face. That is
#200 and #201 working for the first time in this build.

## Previously — last completed milestone
**2026-09-21T03:30Z — the benchmark ran for real, and every defect it found was in the
benchmark.**

All three image credentials are installed as Railway service variables and appear nowhere
else: a grep of the working tree for each finds zero occurrences. **FLUX 2 Pro and GPT Image
2 are verified with real sanctioned generation calls. Google is not** — the key authenticates
and lists models, and every `generateContent` call, text as well as image, returns 403 "Your
project has been denied access", which is a Google-side restriction on that project rather
than a billing tier or a request-shape problem.

The benchmark runs as `creative.image_benchmark` on a six-hourly cadence rather than behind an
endpoint, because the endpoint needs an operator credential no session holds. Each candidate's
scores are stored as it finishes, and a candidate already measured under the current method is
reused rather than re-rendered.

**It ran, and it reported no winner, and it was right to.** The first live run spent CA$6.40
and said no candidate cleared both floors. That was true of the test:

- **The identity floor was unpassable by construction.** `identity_repeat`'s prompt says "the
  same woman as the reference image" and `run` passed no reference, so each model was asked to
  invent the same stranger twice from a description; the judge was then asked whether two
  people matched while being shown one photograph. #200 is explicit that an identity lock is
  reference conditioning rather than a better prompt. A check that cannot pass is not a check
  (B-542).
- **OpenAI conditions through a different endpoint.** `/v1/images/generations` answered
  `Unknown parameter: 'image'`. Reference conditioning lives on `/v1/images/edits` as
  multipart with the reference uploaded as a file. This cost a whole candidate: GPT Image 2
  rendered twenty-five of thirty samples and failed exactly the five carrying the identity
  lock (B-545).
- **A partial schedule was stored and reused**, ranking one model on sixteen samples against
  another's thirty — the fault `teardown.audits` refuses by name (B-543).
- **The follow-up job could not stop.** Progress was read from the run's own results while
  storage required a complete schedule, so a candidate that scored but never finished counted
  as progress, was never stored, and the job re-queued itself every few minutes at about
  CA$1.85 a time. A follow-up condition that cannot become false is a spend with no stopping
  rule. Caught live, mid-spend (B-546).

**The identity lock then held.** The canonical model rendered, and a second image conditioned
on her — different garment, different season, same face, same eyes, same hair. That is #200
and #201 working for the first time in this build.

## Previously — last completed milestone
**2026-09-21T01:50Z — the first images this company has ever generated, and the four
defects that only a real key could show.**

The owner supplied Google, Black Forest Labs and OpenAI credentials. **FLUX 2 Pro and GPT
Image 2 both rendered.** Google's key authenticates and lists models, and every
`generateContent` call — text as well as image — returns **403 "Your project has been denied
access"**, which is a Google-side restriction on that project rather than a billing tier or a
request-shape problem. All three keys are set on Railway; the image-generation gate stays shut
because it is a probe, and one of the three cannot render.

Four defects, none of which any amount of reading could have found:

**The benchmark would have sent one invented body to every provider.** `generate` posted
`{"prompt", "size"}` with a bearer token to each provider's base endpoint, on the stated
reasoning that the differences "are not worth an abstraction nobody has exercised". Google
wants `x-goog-api-key`, a `:generateContent` suffix, a `contents` array and an `imageConfig`,
and would have refused that body under any billing arrangement. An abstraction nobody has
exercised is not thin, it is untested (B-537).

**An empty balance was being recorded as a content refusal.** Google answered 429 `limit: 0`
and BFL answered 402 `Insufficient credits`. The first would have been retried for ever as a
transient outage; the second fell through to a refusal path whose own message says the
provider objected to the brief — so the log would have said a crochet basket was declined on
content grounds. A content refusal is answered with a new brief and an empty balance with a
top-up, so a wrong diagnosis is worse than none (B-538).

**A presigned link is only an image while it lasts.** BFL's URL expires about ten minutes
after it is issued — measured, 01:47Z issue against `se=01:57:00Z`. The canonical identity
pack of #200 cannot be a set of links that stop resolving over lunch. Every render is written
to disk now, which also fixes the mirror-image defect: Google and OpenAI return inline base64
and never a URL, and the old parser looked only for URLs (B-539).

**And the first generated image carried somebody else's trademark.** GPT Image 2 was asked for
a basket beside a linen armchair; it produced a styled scene in which the basket holds
magazines, the top one carrying the **KINFOLK masthead**, legibly, centre frame. Nothing would
have objected — `text_present` was already a field and `true` was the honest answer, which is
a fact about the picture rather than a problem with it. It is a problem with it, and not one a
caption can fix. Unasked for, first attempt, from the strongest prompt-adherence model in the
set. `third_party_marks` is now a description field and blocks the asset, and the describer is
asked about **props** specifically, because that is where it was (B-540).

Suite green at **2,724 across 149 suites**.

## Previously — last completed milestone
**Heartbeat 2026-09-21T00:30Z — the owner queue was asking for four finished things.**

Production held ten open owner actions. Four were done: the Etsy shop that exists, the
developer app that is working, the model key that has spent CA$2.66, and a benchmark
purchase superseded by the approved CA$300 selection. A fifth asked the owner to crochet a
calibration sample, which they have parked twice.

The cause is one missing half of a loop. `launch.readiness` adds an action and restates its
figure, and never closes one. A request stops being generated the moment its requirement is
satisfied — but the row it created stays open for ever, so the queue only grows and its
oldest entries are the ones most likely to be finished. The owner's standing instruction is
"do not ask me to repeat an action already completed", and the live queue was breaking it on
four rows in ten (B-531).

Actions no longer requested now close themselves, guarded: an assessment that produced *no*
requests is far more likely to have failed than to describe a company with nothing left for
its owner to do, and closing the whole queue on that would destroy the record of what was
asked.

Two rows were stale rather than finished. The physical sample is withdrawn from the queue and
recorded as **parked by the owner**, with the requirement unchanged and still blocking
calibrated yardage and every fitted garment — the ask is withdrawn, not the requirement, and
the other way through is a pattern tester rather than the owner (B-532). The benchmark
purchase asked for "about ten" patterns into "its own folder under the benchmark library
path" at CA$120: there is no folder on a phone, the set is chosen rather than approximated,
and it now points at `/api/benchmark-selection` and `/ops/teardown` at the approved CA$300
(B-533).

Also confirmed live rather than assumed this heartbeat: `/api/verify` 12 of 12; the gallery
drain is running and on schedule (1,048 images pending, ~CA$0.034 an image observed against
CA$0.029 estimated, within the 40% allocation); 134 dead letters are all publication
refusals and **zero are defects**; the off-site archive records a configuration failure
rather than a stale success.

**And the image-provider action list was checked against the providers' own pricing pages
rather than against memory.** Three things were wrong. Google AI Studio was listed as free
and cardless, first in the queue because it was the easy one — but Nano Banana 2's image
output reads "Not available" under Free Tier, so that key would have authenticated and
refused to render (B-534). Nano Banana was priced at US$0.063, roughly Google's 1K figure,
while the benchmark renders it at 2048px, which is US$0.101 — an estimate for a rendering
nobody was going to make, understating the dearest candidate by 60% (B-535). And Imagen 4 is
no longer listed on that page at all, so its row left the provider table and survives only as
the recorded requirement-based exclusion (B-536).

All three sign-ups need a payment method. The benchmark now plans at **CA$20.11** of the
approved CA$25.

Suite green at **2,716 across 149 suites**.

## Previously — last completed milestone
**The three practical gates, built as far as they go without the owner's credentials.**

### Off-site storage — built, tested, unconfigured, and honest about it

`core/offsite.py` writes the continuity export to any S3-compatible bucket. SigV4 signing is
checked against the key-derivation vector AWS publishes rather than against itself; the
payload is sealed with AES-256-CBC under a PBKDF2-stretched passphrase held in a variable the
bucket credentials do not include, and it is authenticated before it is decrypted, so a
flipped bit is a refusal rather than a restore.

The archive is one function on purpose — export, upload, read back, compare digests,
decompress, restore into a scratch database — because an upload recorded as a success and a
restore proven separately are two facts about two different objects. The only claim worth
recording is that *this* object, as it now sits in that bucket, restores this company.
Verified end to end against an injected transport: 45 tables restored, `survives provider
loss: true`.

A daily `ops.offsite_archive` cadence runs it and prunes only after a good write. An
unconfigured destination is recorded as a **failed** archive rather than skipped — the gate
reads those rows, and a job that returned early on a missing variable would leave the last
`ok` standing from whenever the credential last worked (B-524). Production confirms it:
`/api/offsite` reports `configured: false`, `usable: false`, with a recorded attempt.

**Recommendation: Backblaze B2.** Eleven nines of durability like the others, US$6/TB/month
with egress free up to three times the stored amount, native object lock and versioning, and
the only one of them that publishes its drive failure statistics. At this archive's size —
604 KB compressed, 14 retained — the bill is under CA$1 a month at any of them, so the choice
is made on recoverability rather than on price, which is what the owner asked for. The code is
provider-neutral: R2, Wasabi and AWS need only different variables.

### Mobile teardown intake — one tap per purchase

`teardown/intake.py` and a single-file page at `/ops/teardown`. The owner taps a pick and
chooses files; the seller, department, price, listing reference, recorded reason and the
listing's promises all come from the catalogue row that justified the purchase. A system that
makes somebody retype what it already stored is a system abandoned around purchase four,
which is exactly the failure #170 exists to prevent.

Zips are expanded here — bounded in entry count, expanded size and compression ratio, refusing
an entry that climbs out of the folder — because the alternative is asking a phone to unzip.
Files are hashed, classified by filename, manifested, audited against what the listing
promised, and mirrored to the archive. Nothing opens a file: the quarantine holds.

The reply says `durable: false` when the mirror could not be made, loudly and with the reason.
On this host an upload that was not mirrored is a purchase that will have to be made again,
and "uploaded" and "kept" are different claims.

The promise audit has three outcomes rather than two. A claim nobody observed is
`unverifiable`, never `kept` — an audit that resolved its unknowns in either direction would
manufacture a finding about the seller out of a gap in our own observation.

### Image generation — the benchmark would have compared one model against itself

Three defects found, all the same shape: a fact recorded once, with no way of noticing the
world had changed.

`image_bench.run` called `images.generate` with no provider, which resolves whichever provider
the environment names — so every candidate's prompt went to the same endpoint. It would not
have errored. It would have returned five near-identical rows and handed the decision to the
cost tie-break, which is precisely the decision the owner ruled out. Credentials are held per
*account* now (one Google key covers two candidates), `generate` takes the provider it is to
use, and a candidate with no credential is recorded as **unmeasured rather than beaten**
(B-525).

`decide` now reports `locked: false` while any eligible candidate went unmeasured. A leader
chosen over models nobody could render is a shortlist of one wearing a result's clothes
(B-526).

`plan()["runnable"]` was a literal `False` with a sentence beside it explaining that no
account existed. True when written; it would have gone on saying so after the accounts were
made. It is computed from credentials now (B-527).

### And the selector told the owner the wrong reason it stopped

At the approved CA$300 the live set stops at **twelve** picks costing **CA$292**, with the
`education` department uncovered — and `why_stopped` said no remaining listing added anything
new. It was the ceiling, by CA$13. Somebody reading that line to decide whether to raise it
was told there was nothing left to buy. The cause is now recorded where the loop ends, with
the excluded pick, its price and its shortfall (B-528).

Suite green at **2,711 across 149 suites**. Production `/api/verify` 12 of 12; 0 READY, 79
parked.

## Previously — last completed milestone
**Online means work is progressing, and the self-healing turned out to already exist.**

**#185 — `ops/health.py`.** The requirement writes its own definition into the middle of the
sentence and the module takes it literally: *online means useful work is progressing, not
merely that HTTP returns 200*. A container can serve 200s, tick a worker, run a scheduler,
hold an empty queue and complete nothing for a week — every liveness signal green, because
none of them is about work. That is this build's recurring defect in its most respectable
costume: the verdict is computed from the absence of failures, and a system doing nothing has
none. So `progress` is a signal with the same standing as the heartbeat, and an
otherwise-green system reports **`idle`**, which is a different word from healthy on purpose.

*Writing the self-healing half produced the finding that replaced it.* Both obvious repairs
already exist: a lease is reclaimed inside `JobQueue.claim` on **every** claim, and a dead
letter is re-driven once per deploy (B-327) — which is the right trigger, because a dead
letter is fixed by a code change. Re-driving one on a fifteen-minute timer re-runs a failure
nothing has fixed, ninety-six times a day: a retry storm with a health check's name on it. So
the sweep detects, escalates, and names where each repair actually lives, which makes
"self-healing" a claim somebody can check. What it cannot fix at all — a container restart, a
missing credential, money already spent — it escalates by name rather than attempting,
because a repair that is announced and does not happen is worse than none: nobody looks.

Escalation waits for persistence — one bad sweep is a blip and a deploy produces several — and
the history is read from the handler's own audit trail rather than memory, because a container
replacement is exactly when conditions happen. Cadence: `health_sweep` → `ops.health`, every
fifteen minutes, GREEN, spends nothing.

**#183 — `/api/console`, and the two views the dashboard was missing.** Approvals now arrive
as the executor's own cards, each with its action and its consequence of waiting, because a
count of queued actions does not answer *is anything waiting on me*; and learning changes
arrive with their source and date. Both are on the dashboard page itself, so the answer is
readable on a phone without composing a request. The console's health is #185's verdict, which
means it can say `idle` — a console that cannot say so is one that will report a green week of
nothing. It aggregates what the read endpoints already serve, at the same exposure, and opens
no new door; the continuity export and the dead-letter requeue stay behind the operator
credential. No public marketing site exists or is planned, which is the requirement's other
half.

**Verified in production on `0782969`, not asserted.** The three new cadences fired and
completed on the live service within ten minutes of the deploy — `ops.health` (job 1749),
`ops.sentinel` (1747) and `ops.capacity` (1745) — and the console reports `healthy`, 0
pending, 134 dead letters.

The sentinel's first real sweep is the evidence that the backlog calibration mattered: it
found **275 derived artefacts with no provenance row** across the live estate, and raised
**one** P3 incident carrying that number rather than 275 incidents. Without that decision
(B-364a) production would now hold 285 open incidents and the ten real ones would be
unreadable. Nothing was reported stale, nothing was blocked, and `graduation()` correctly
says absence may not be enforced yet.

The 134 dead letters are all publications refused by shadow mode — the guard working — which
is what prompted counting deliberate refusals apart from defects (B-374).

**#172 — the rebuild set, and the part of the estate the graph cannot see.**
`ops/rebuild_graph.py` reads its edges from #171's provenance rows rather than keeping a
second opinion, follows them the other way and transitively — a listing built from a PDF
built from a design is two hops away and nobody rebuilds it by hand — and emits them
topologically, because rebuilding the listing before the PDF regenerates it from the stale
one and afterwards everything claims to be current. A cycle is refused, not traversed. The
number that matters is the coverage, printed on the same line as the rebuild set because the
rebuild set is the part people read: **production holds 275 derived artefacts and not one
carries a provenance row**, so a propagation over the recorded graph touches nothing and
reports that no rebuild is needed — true of the graph, false of the shop.

**#260/#261 — the two halves of "why did they buy", and the one that cannot see non-buyers.**
`commerce/friction.py` audits the buyer journey and files every friction at the stage that
*caused* it rather than the stage it arrived at. That distinction is the module. Support is
where nearly all friction lands and where almost none is made: "I thought I was buying the
blanket" arrives in the support queue, an audit grouped by arrival produces a support macro,
the macro works — the buyer is refunded quickly, the response-time metric improves — and the
listing goes on saying the same thing to the next four hundred people. A shop can become
measurably excellent at absorbing a defect it has never once removed, with every number
moving the right way while it happens.

Two thresholds, not one: a correctness defect acts at n=1 (nobody's second complaint makes a
missing file more missing) and a comprehension defect needs a rate — three in five is an
emergency, three in four hundred is three people, and the difference is a denominator a count
does not carry. And a stage with no complaints and no traversals reads `not_yet_walked`,
never `clean`, because zero complaints from zero buyers is identical evidence to a flawless
funnel and this shop is the first case today. Five of the six confusions the spec names are
made in the listing copy, so that half of the audit runs now, against the listing artefact
rather than against `seo.build_description` — asking the generator whether its own output is
correct is asking the defendant. A test asserts the shop's generated copy passes its own
auditor, which is the check that catches a standard a module ships without meeting.

`growth/interviews.py` is the other half. Its output is never a finding: `Hypothesis.status`
is `hypothesis`, and the only exit is evidence from an instrument that asked nobody a
question — another interview reproduces the selection rather than testing the claim, and is
refused by name. The three ways a voluntary sample decides its answer in advance are each
closed structurally: the incentive lives on the invitation and must be identical across a
round (`Response` has no incentive field at all, because one chosen after reading a response
is contingent on sentiment however kindly meant — contingency is ordering, not motive);
"what nearly stopped you" carries a 14-day window and a later answer is kept as
`reconstructed`, since a hesitation is rebuilt rather than retrieved; and selection rules
that can see the outcome — `left_a_good_review`, `repeat_buyer`, `no_refund_requested`,
`high_order_value` — are refused by name, because each one describes itself as *asking our
best customers* and each produces a warm sample that measures nothing. Invitations pass
through the CASL gate on the purchase relationship; a published business address is refused
as a basis for surveying a private buyer.

Both name the same blind spot from opposite sides: **everyone who did not buy**. The
interview reaches only survivors of the decision it is trying to understand. Both land
`partial` — #260 parked on `customers`, #261 on `live_listings` — and #261's listing half is
the part that stays true for every buyer who has not arrived yet. Decisions B-406..B-412.

**#262 — checking the forecast, and paying for having been optimistic.**
`scale/calibration.py`. Three structural choices, each closing a way a calibration flatters
the model it is checking. A `Forecast` carries `made_on` and it must precede the period it
predicts: recalibrating against expectations recorded afterwards builds a model that is
always well calibrated and never right, because the expectation adjusts to the outcome on the
way past and nobody involved notices. The error is decomposed in log space rather than by a
waterfall — revenue is a product of seven terms, and substituting them one at a time gives
each term a different share depending where in the sequence it is walked, so whoever does the
decomposition chooses, after seeing the numbers, how much of the miss belongs to the term
they would rather blame. In logs the split is exact and order-independent, and a term with no
measured actual lands in `unexplained` instead of being spread across the measured ones.

Optimism costs five times what pessimism costs, automatically — there is no argument
`ceiling()` accepts that raises it — and recovery is a ratchet: three consecutive accurate
periods before it starts, then one step at a time, because symmetric recovery lets one good
month erase a year of forecasting high. The output is a *ceiling* applied to
`scale.confidence.probability`, never a second probability, since two answers to one question
means the flattering one gets quoted.

And the honest note about today: **every period would be excluded**. With nothing published
there are no live listings, so a calibration run would score a model nobody applied as
catastrophically optimistic and take confidence to the floor — arithmetic about an unopened
shop rather than a finding. Excluded periods are counted in the result rather than silently
shrinking the denominator. `partial`, parked on `live_listings`. Decisions B-413..B-417.

**#267 — the weeks a single calendar throws away.**
Most of this requirement was already built: `seasonal/compression.py` retires lanes one at a
time and moves each closing lane's share into the fastest lane still open, so the
early-flagship to late-quick-make shift falls out of the arithmetic rather than out of
somebody remembering it in November. What was missing is the word *and* in "product and
marketing capacity", and it is not a detail — the two run on different clocks. Engineering
leaves an occasion when its last lane closes, because nothing new could be launched, indexed
and finished in time. Marketing leaves weeks later, at the buyer's own last practical make
date, because the catalogue already listed goes on selling until then. Those weeks are the
ones that earn most, and a shop budgeting one capacity against one calendar has already moved
its attention to February.

`seasonal/rollforward.py` holds the two as separate ledgers over one calendar and states the
rule: **engineering rolls forward first, marketing rolls forward last.** Rolling forward is
refused in both directions — nothing leaves an occasion that still holds it, and engineering
may not arrive at one inside its own preparation lead, because capacity moved out of a season
that is ending into one that is already late has been spent on being late twice. On today's
real calendar the ledger already shows the gap: Thanksgiving is 22 days out, unlaunchable and
still entirely buyable.

The curve it will not draw: `demand_curve()` computes the structural floor — past the last
practical make date demand is zero, because nobody can finish the object — and reports the
decay before it as unobserved, naming what would settle it. Makers do not all wait for the
last possible day, but no listing of this shop's has been watched through a season, and a
decay date taken from a plausible shape is a point estimate presented as a fact. `covered`.
Decisions B-418..B-421.

**#179/#180 — the agents whose only job is other agents, and the league they argue in front of.**
`improve/roles.py` names the eight meta-agents #179 lists and enforces the three rules that
stop such a swarm flattering itself. The requirement's own last clause — *measured by verified
uplift, not number of changes* — is implemented as arithmetic rather than as a policy:
`scorecard()` computes from realised uplift alone and `proposals_made` cannot reach it,
because a swarm graded on changes made will make changes — forty findings, thirty proposals,
twelve promotions, and no capability curve anywhere that moved, with every number on the way
pointing upward. The other half matters as much: a rejected proposal scores **zero, never
negative**, since penalising rejection teaches the swarm to propose only what will obviously
pass. No role both proposes and judges. The cost optimiser may not buy its savings from
reliability, the reliability engineer may not buy uptime from contribution, and no role may
trade deterministic validation at all.

`partial`, and the gap is named rather than counted around: none of the eight has an entry in
`agents/registry.py`, a job type, a ceiling or a cadence. The roster is a specification of
roles, not running agents.

**#180** hardened `improve/league.py` rather than adding a second judge beside it. Four things
it was quietly missing. **The shared set is overfitted by the league itself** — refusing a
challenger's own tasks stops one author gaming one comparison and does nothing about a hundred
challengers judged, over a year, against the same forty tasks; a holdout is now carried, never
tuned against, and winning the tuned set while losing the holdout is refused with that named
as the reason. **Latency is the fourth axis**, and the one that looks free, because it is
nobody's line item until a cadence misses its window. **A margin is not a significance test** —
the bar now scales with how much was measured, since 0.03 on four tasks is a coin and a league
promoting on coins churns while every report counting promotions calls it progress. **Rollback
is a recorded target** with a required reason, answerable before it is needed.

Two existing league tests failed against the new bar, and both encoded the old weaker
standard: a test about how the *cost* bar scales was incidentally testing sample size on a
four-task fixture. The fixture was widened and the margin scaling given its own tests, rather
than the new threshold relaxed until the old test passed — which is the obvious move and is
how a standard quietly reverts. Decisions B-422..B-427.

**#191 — two clocks, and the department that is never stale and never moves.**
`improve/freshness.py`. The requirement says each department decides how often its evidence
should be reconsidered based on how fast its world changes, and what existed was a single
thirty-day constant carried separately by `improve/profiles.py` and `improve/bus.py` — far
too slow for a competitor's catalogue and meaningless for the compiler. Each cell is now
mapped to a *world speed*: adversarial 24h, market 72h, operational 168h. A cell with no
declared world raises rather than taking a default, because a default is the single global
constant coming back.

The entry worth arguing about is the one with **no interval at all**. Compiler mathematics
does not go stale with time — a stitch count right in March is right in September — so
`pattern_engineering` is answered on a code fingerprint, the same mechanism `ops.artefacts`
uses for derived files. A very long interval was the easier choice and is wrong in exactly one
way: it reports the compiler current for another month after somebody changes it.

**And two clocks, not one.** A freshness SLA measured in "when did we last look" rewards
looking: a department re-running a scan every hour and learning nothing scores perfectly on
recency, and that is the commonest real state of an improvement programme — busy, current and
flat. So evidence age and capability movement are separate readings, and `CHURNING` — fresh
and going nowhere — is reported as a problem rather than a pass. Direction is read against each
cell's own polarity, because half these metrics are better when they fall; the first version of
that test used `finance`, whose metric is forecast *error*, and asserted a rising number was
healthy. Never-measured is kept apart from stale: one is instrumented, the other re-run.

`partial`, and the gap is the honest one: `sweep()` is tested but nothing calls it on a
schedule, so nothing is flagged to anybody yet. That arrives with #193's nightly window, and
claiming the flagging works before a cadence runs it would be capability from configuration.
Decisions B-428..B-431.

**#190/#193/#194 — the autonomy block, and the fourth costume of the same defect.**
`improve/pipeline.py` is the object between a proposal and a promotion; the governance half
already existed in `improve/tiers.py` and is not rebuilt. **Evidence is a recorded run, never
a field the proposal sets** — a proposal that runs its own tests and reports them passed has
reported an opinion in the shape of a fact. And **evidence describes a version**: each
proposal carries a fingerprint, evidence records the fingerprint it ran against, and revising
the proposal invalidates it rather than ageing it out. That is the failure that only happens
to something working around the clock, where the content moves silently under evidence
gathered hours earlier. Auto-promotion reads the tier and never the proposal's own view of its
risk — there is no confidence field to set, because classification-by-surface exists precisely
so a change cannot talk its way into a faster lane. The owner card is refused unless impact,
cost and rollback are each exact; "minimal impact, low cost, we can revert" is what an
approval queue fills with when nobody checks, and a person reading it has been told nothing
and will approve it.

`improve/nightly.py`, with the `improve.nightly` cadence and handler. The whole risk in a
scheduled sweep is the word **completed**: a job that finishes without raising and writes "ok"
reads identically whether it did the work or skipped every stage, and the comfortable reading
is the one believed. So a stage has three outcomes and never two — found, found nothing, or
did not run — and a stage that read zero rows reports `did_not_run` however it describes
itself, because finding nothing in nothing has not established there was nothing to find. The
verdict is computed from what each stage returned. **This is the fourth costume of the same
defect this build keeps meeting**, after a funnel stage that killed nothing (B-278), an
artefact with no provenance row (B-360) and a buyer journey nobody walked (B-408).

Run against the real database, the handler reports `incomplete` and names the five stages with
nothing to read. That is the honest output for a shadow-mode company, and exactly what a
success-on-no-exception job would have hidden.

`improve/weekly.py`, with the `improve.weekly` cadence and handler. Eight domains audited
rather than visited — nothing read is `not_audited`, and the cycle will not call itself
complete while one remains. The substance is the architecture review: `improve/velocity.py`
already refuses the add-only review for cadences, and **that argument does not stop at
cadences**. A review permitted to add specialists and never to merge or retire one grows the
org chart every week, one individually defensible step at a time, which is what makes the
total indefensible and invisible. Three of the four moves subtract. Revising a metric is the
dangerous one: a department may never propose the revision of its own measure, the old
metric's history is preserved rather than migrated, and ten phrasings of "the number is
unfair" are refused by name — because a department that changes its metric after a bad quarter
has not improved, it has moved the goalposts, and from inside that feels like better
measurement.

Both handlers are covered by the platform suite's `test_every_scheduled_cadence_survives_actually_being_run`,
which runs every cadence for real rather than checking one is registered. #191 closes to
`covered` with them: the nightly sweep is what calls `freshness.sweep()` and reports the stale,
churning and never-measured departments. Decisions B-432..B-439.

**#179 closes: the eight roles become running agents.**
Each meta-agent now has an entry in `agents/registry.py` at GREEN with a CA$0.25 daily
ceiling, exactly one job type it may run, and a daily cadence. Both lists are *generated from
the roster* rather than retyped, because two lists of the same eight drift and the drift is
silent: an agent with no role has authority over nothing, and a role with no agent is a job
description nobody holds. The agent **is** the role, so `ctx.job.agent` dispatches and a pass
by an agent that is not a role is refused rather than defaulted to something.

None of them proposes or promotes. Proposing runs through #190's upgrade pipeline and
promotion through #178's tiers, and a meta-agent that could promote would be the company
rewriting itself faster than it can observe the results — the failure #178 exists to prevent.
The ceilings are nominal rather than absent, because a meta-agent able to spend real money
deciding whether somebody else should have spent money is the wrong shape.

Run against the real database, all eight report `unmeasured` and propose nothing. That is
asserted by test rather than described: a swarm reporting activity against no rows would be
reporting on work it invented, which is the specific failure `swarm.next_work` already names
for ordinary agents and which applies with more force to the agents whose only job is other
agents.

**And a rule broken two hours after recording it.** #190's module was written as
`improve/pipeline.py` while `runtime/pipeline.py` already existed — exactly the collision
B-421 was written to prevent. Nothing would have broken; different packages mean no import
collision. It would only have meant two unrelated modules answering to one name in a codebase
where imports are read far more often than they are written. It was found by stumbling into
the other module while tracing a missing handler, not by running the check. Renamed to
`improve/upgrades.py` across four files. Recorded as B-440, because writing a rule down is
evidently not the same as following it.

**#146, and three requirements that were reporting themselves as ready work.**
The culture cluster's registry notes were already honest — #133 said no feed is connected,
#140 said it needs a connected search source, #147 said it needs launch data. All three sat
in the **ready queue** anyway. A note is read by people; the queue reads gates, and the ready
count is the one number the executor exists to keep honest. A `culture_feed` gate now holds
them, opening on the first `CultureObservation` row that names its source — counted rather
than configured, because an observation with no source is the same unverifiable thing as no
observation. Ready fell from 33 to 29 and nothing was lost: the work is parked where it can
un-park itself.

That leaves **#146**, which was genuinely buildable. `culture/cast.py` holds what
`translate.owned_territories()` could only count, and two refusals carry the requirement.

**Recurrence cannot be declared.** "Recognisable original IP that customers return for" is a
claim about the second time, so an element is `proposed` until it has appeared in three
releases across two seasons — and eight appearances inside one season is still proposed,
because returning requires having gone away. There is no status field to set, one product
cannot be counted twice, and a retired element coming back is a new proposal so the roster
shows somebody decided twice.

**Originality is checked on the primitives, never the name.** The dangerous failure is not a
product that borrows openly — that path exists and is routed. It is a character with an
original name whose design is a recognisable external one: it looks like an asset, carries the
full legal risk of what it resembles, and cannot be defended because nobody wrote down what it
was derived from. `propose()` scans name, description and every primitive through
`rights.check_free_of` rather than implementing a second containment test, since two answers
to "is this token present" means the more permissive one gets used.

A collection world must answer `can_host()` for a category it has never seen, and `dependence()`
refuses a single reading — "not permanent dependence" is a direction, and a dependence nobody
trends is one nobody notices growing.

The roster is empty, and stays empty. Filling it now with invented names is exactly the
failure the module refuses; the elements get earned as products are designed.
Decisions B-441..B-444.

**#57/#58/#65/#69 — what an asset is made of, and what it is allowed to do.**
`publish/eligibility.py`. `AssetClass` already said what an asset is *made of* — a twin
render, a photograph, an infographic. #57's own sentence asks something else: *a technically
correct chart cannot be promoted to hero merely because it rendered successfully.* Rendering
successfully is a fact about the medium. Being the hero is a question about the purpose, and
nothing held the second — which is exactly why the only reason a chart ever becomes a hero is
that it was the asset that finished rendering. Purpose is now a second, orthogonal axis, and
the row that matters most is that **nothing but a photograph may be `PHYSICAL_PROOF`**,
whatever it is labelled, because a label is precisely where that gets claimed.

**#65's rule is about jobs, not pixels.** "Prevent five technically different images from
communicating essentially the same thing" reads like a similarity check, and implemented that
way it passes the actual failure: five genuinely different charts all doing `DETAIL`. So every
frame declares one job from the ten named, and two frames sharing a job is the defect. Frame
one is the hero and its job is `DESIRE`, stated rather than derived — a listing whose first
frame documents rather than sells has spent the only frame most shoppers see. Missing jobs are
listed and never refused, because a shop adding a frame per uncovered job is padding the
gallery to satisfy a checklist.

**Four gates, and the fifth costume.** Each of `DATA_TRUTH`, `LAYOUT_QA`, `COMMERCIAL_QA` and
`POLICY_PROVENANCE` reports passed, failed or **not_run**, and export requires all four to
have run *and* passed. A boolean would make a gate nobody wired up indistinguishable from one
that passed — the same defect as B-278, B-360, B-408 and B-435, in a fifth place.

**And a label is never a licence.** #69 says it outright, so it has to be structural: the
honesty label is computed from the medium rather than accepted from a caller, and `may_export`
reads the asset-truth verdict *independently* of it. There is no ordering in which a
disclaimer makes a failing asset exportable. It is required only where the render/photograph
distinction is material, because labelling a materials list trains buyers to read nothing and
costs the label its meaning on the frames where it matters. Decisions B-445..B-448.

**#60/#68/#70 — traced numbers, named defects, and a certificate that invalidates itself.**
`publish/dimensions.py` audits every number on the way *out*. `cir.geometry` was already
canonical and already refused what it could not measure, and none of that says anything about
what reached the card — every defect #60 names happens after the measurement is right. The
check that matters is the third one: **two displayed numbers disagreeing about the same axis
of the same component**, which is invisible to any check that validates measurements one at a
time, and one at a time is how measurements are usually checked. The requirement's own
unexplained 180 cm marker is caught as `untraceable` — not wrong so much as unreadable, and
unreadable is worse because nobody can disagree with it.

`publish/defects.py` gives visual defects the treatment compiler defects already had. They
never got it for a nameable reason: a compiler defect is a wrong number and a layout defect is
a look, so it feels like taste, and taste does not get a fixture — but `layout_qa` measures
rendered pixels, which makes these reproducible, and anything reproducible can be fixtured. A
defect with no reproduction is refused; it is a memory, and memories prevent nothing. And a
**recurrence after a fixture is a bug in the fixture**, not a second bug in the renderer,
which is what stops a second broken fixture being added instead of the first being widened.
"Improve monotonically" is implemented as the narrow claim it can support: not that defect
counts fall — production finds what production finds — but that the set of classes with a
passing fixture never shrinks.

`publish/listing_set.py` certifies the listing, which is a separate object from the release
certificate because the two go stale for different reasons: a size card can be quoting
geometry that has since changed while the pattern's own certificate stays perfectly valid. The
load-bearing word is **invalidates** — a revocation step is a step somebody forgets, and the
forgetting is silent, so validity is recomputed from the current inputs rather than read from
a flag.

**And two more requirements stopped advertising work nobody can start.** #61 leads with
independent visual review and #64's trigger is a photograph of an object nobody has made.
Parked on `browser_vision` and a new `physical_proof` gate — which opens on the first
PhysicalTest row with a completion date, counted rather than read from a flag saying testing
is set up. Ready fell from 29 to 19. Decisions B-449..B-452.

**#63/#66 — the one direction creative may not go, and the context the builder never occupies.**
`publish/brief.py`. The CIR-to-evidence half of the flow was built; the constraint in the
middle was not, and its shape is an asymmetry. **Creative may select from truth and may never
extend it.** A hero showing three of seven stitch types is a photograph of part of a thing —
no listing shows everything. A hero showing an eighth is a claim about a pattern that does not
contain it, made by an image nobody thought of as a statement. Subset, one direction, across
all five categories the requirement names. A category the brief is *silent* about is refused,
because silence is a category creative may fill in; an empty allowance is a real constraint
and stays distinct from no entry.

The flow is ordered because a brief produced once the creative exists is a caption — the same
shape as a forecast dated after its period, arriving for the same reason: the convenient order
is the wrong one and nothing else notices. Going backwards is permitted and reported as
*restarting*, since a defect found at the gates genuinely sends work back to the brief.

`publish/mobile.py` evaluates the set where it is chosen rather than where it was built. A
listing is assembled at full size, one frame at a time, by somebody who already knows what the
product is; it is chosen at 170 pixels, in a grid of competitors, by somebody who does not.
**The first three frames are a context, not a prefix** — a phone shows three before anybody
scrolls, most people do not scroll, and three frames all doing one job is one frame shown
three times in the only context most shoppers occupy. An unrendered context reads
`not_rendered`: "we checked the mobile view" is not a finding anybody can revisit when a
listing underperforms three months later, which is exactly when somebody wants to.

**And prose was doing a gate's job for the third time.** #168 said "unrunnable until
benchmarks are purchased" and #79 said "needs the vision capability", and both sat in the
ready queue. Parked on `benchmark_purchases` and `browser_vision`. Ready is 15 against 87
parked, and the number now means what it says. Decisions B-453..B-457.

**#33 — a year with many occasions in it, and the constant that says otherwise.**
`seasonal/engine.py`. The merge instruction is explicit: *preserve Christmas as the current
campaign, not the company identity.* And `compression.PRIORITY_PROGRAMMES` is
`{"Christmas": 0.45}` — a constant naming one occasion, granting it nearly half of engineering
capacity permanently, read by five modules. **That is the Christmas Strike Team, in code**, and
no amount of rolling-wave machinery wrapped around it changes what it says.

Priority now comes from a score with no favourites. Seven factors **multiplied, not averaged**,
because they are conjunctive: an occasion with no time remaining scores zero however strong its
demand, and an average lets six good factors carry one fatal one — the same reason
`scale.confidence` takes a minimum over its rungs. A missing factor is refused rather than
defaulted, because a factor left out of a product is a factor silently set to one, which is the
most optimistic possible assumption and the one nobody notices making.

**The evergreen floor is the inverse of the priority floor, and nothing had it.**
`MIN_PRIORITY_SHARE` stops a seasonal programme decaying; nothing stopped evergreen being
squeezed to zero, and a shop entirely inside Christmas has nothing to sell in February. It is
subtracted before anything is granted rather than checked afterwards — and that was not
theoretical: rounding three equal shares independently produced 0.8001 against a pool of 0.8,
eating the floor from above. Caught by the test that asserted the invariant, fixed by giving
the remainder to the largest share.

Squads stand down by arithmetic, because nobody stands a team down in a busy week.
Construction primitives and commercial lessons cross seasons; designs, motifs, colourways and
copy do not — recolouring last October's product is not the insight, it is the product again.
And a breakout moves allocation and is *structurally* unable to reach a gate, because
"emergency" is the word people use when they want to skip a step.

**And then the constant went.** All five call sites now read
`compression.priority_shares()`, which returns scores when any occasion has them and the
owner's named campaign, labelled `current_campaign_seed`, when none does. A straight cutover
was the tempting move and would have been wrong: scoring needs observed demand, visibility and
competitive weakness, this shop has none, and every occasion would have scored zero — reserving
nothing for the campaign whose making window is actually open. That is absence, not rigour.
What the migration buys is that the owner's decision can no longer be read as a measurement,
and a test refuses any direct read of the seed outside its accessor, because a direct read is
that decision with the label stripped off.

The guard test written one commit earlier asserted the constant was still present so
`state()`'s claim could not go stale silently. The migration broke it, which is exactly what it
was for: the claim got updated because a test failed, not because somebody remembered. #33 is
`covered`.

**And the process failure got a check.** Three times this session prose in a registry note was
doing a gate's job — the cultural feed, vision, physical proof, purchased benchmarks. Every
note was accurate; every one of those requirements sat in the ready queue. `test_executor` now
fails if an unparked requirement's note describes a blocker. It is phrase-matching and crude,
and crude is the right trade: a false positive costs a reworded note, a false negative costs
the ready count its meaning. Verified against the live registry rather than assumed — it
matches four real notes, which pass only because they are now parked.
Decisions B-458..B-462.

**#215/#219/#220/#227/#228 — learning from the best shops without becoming one.**
Six requirements in this group had never been audited; five of them were buildable and are
now built. `intel/panel.py` and `intel/veto.py`.

**#227 is the spine, and its failure is aggregation rather than any single decision.** Every
individual choice to match the benchmark is defensible — they are good, this is what good
looks like, we should be at least this good — and a year of defensible choices is a shop that
looks like a copy of a shop. There is no moment where anybody decides to become derivative,
which is precisely why parity alone is a refusal rather than a caution. #215 pushes equally
hard the other way: sharing an arena with an elite seller is *not* a reason to stay out of it,
so entering is permitted and the over-correction is what gets avoided.

**A standard may be raised by a competitor and never lowered by one.** Lowering because
somebody else slipped is a race to the bottom with a paper trail, and it is the more tempting
move because it is free and shows up as an improvement in every metric about hitting
standards.

**A panel of one is one shop's aesthetic with a formal name.** MJs is named once, as the
anchor, so "the panel" never quietly means it; a mechanism needs two independent sellers
before it is a mechanism rather than one shop's habit.

**And the owner's veto records why.** A veto is easy; the reason evaporates — acted on once,
and six months later nobody can say whether the same objection was raised eleven times or
once, so an evaluator that could have been trained on eleven instances was trained on nothing.
Reasons come from a countable vocabulary, the third repetition is a finding about the
*evaluator*, and retirement needs thirty predictions made **before** the owner ruled, because
grading a model on answers it has seen is the natural mistake when the owner's rulings are the
easiest training data to hand.

**One requirement now remains `missing` across all 320.** Decisions B-464..B-468.

**#226 — and nothing is `missing` any more.**
`intel/pod_learning.py`. The requirement's last sentence — *the pod should become measurably
more discerning and creative over time* — contains a trap, and it is the one
`improve/velocity.py` was built against. **Discerning and creative pull against each other.**
A pod that rejects everything is maximally discerning and contributes nothing; one that
accepts everything is maximally generative and worthless. A single score can rise while either
collapses, and the one that collapses is whichever the score happens to weight least — which
is exactly how a pod becomes very good at saying no. So there are two measures, nothing
returns one without the other, and a test asserts no single pod score exists anywhere in the
module.

**Discernment is precision against outcomes, never rejection rate.** Rejection rate is the
measure that gets used, because it is available the moment a call is made and rises whenever
the pod is being careful. What it measures is caution. Both directions count: a pod that never
says no reports that, and noes that would have worked are counted separately, because a pod
whose every refusal was wrong is expensive in a way precision alone hides.

The six record kinds split into learning from failure and learning from success, and a memory
collapsed into one is reported as drifting cautious or drifting imitative — the second being
**#227's failure arriving through the learning system** rather than through a decision anybody
made. Reported as a direction, never a target: there is no correct ratio, only a pod that has
stopped doing one of them.

And pods are deliberately *not* added to `improve.cells.CELLS`. The literal reading of
"participate in the continuous-learning architecture" is to make each pod a department cell,
which would double CELLS from twelve to twenty-four and quietly double every count computed
over it — including the freshness sweep and the nightly bottleneck stage. A department is a
function of this company; a pod is a lens on somebody else's catalogue. Decisions B-469..B-472.

**With #226 closed, no requirement in the 320 is `missing`.** What remains is 57 `partial` —
things that exist and fall short — plus 56 parked on owner actions and absent data.

**A red suite that was not a code defect, and the fix that is one line rather than sixty-four.**
A full run failed **eleven suites** on `No space left on device` with nothing in the diff to
explain it. The cause: the suites had left **37,284 temporary directories totalling 29 GB** in
`/tmp` — about twelve hundred per run, across roughly thirty runs this session. Sixty-four
test files call `tempfile.mkdtemp`, which unlike `TemporaryDirectory` never cleans up, and
each directory holds a SQLite database and sometimes a rendered image.

The fix is in `run_tests.sh`, not in sixty-four files: `mkdtemp` honours `TMPDIR`, so the
runner gives the whole run one temporary directory and removes it on exit, including on
interrupt — the runs killed half way are exactly the ones nobody goes back to tidy. Fixing
the call sites would be sixty-four edits that each have to stay correct, and the
sixty-fifth would leak again. Verified: a run now leaves zero directories behind.

*And the first fix did not work, while the suite was green.* `trap ... EXIT` replaces an
earlier EXIT trap rather than adding to it, so the `$outdir` trap thirty lines below silently
discarded the one that removed the run's TMPDIR. Stray directories in `/tmp` went to zero —
the containment was real — and the run directory itself survived with 342 MB in 399
subdirectories, so the disk still filled at a third of the rate, on a run that passed 1,995
tests. It was caught by counting what was left rather than by trusting the change, which is
this build's recurring defect arriving in a shell script while fixing something else. One
cleanup function, one trap. Verified on the run after: 1,995 passing, **zero** leftover
directories of either kind, disk steady at 23%.

Worth keeping because of what it looked like from inside: eleven red suites, a green run
twenty minutes earlier, and nothing in the change to blame. The log said `ENOSPC` on every
single failure, which is the sort of thing that is obvious once read and invisible while
guessing.

**#253/#254/#256 — the club, the customisation and the referral.**

`products/personalisation.py` (#254) gives "keep canonical pattern truth intact" a precise
reading: every customisation is a **presentation** choice, which changes what the buyer is
shown, or a **construction** choice, which changes the instructions and is a new design
wearing the old one's name. Letters are stitches. The failure prevented is the one every shop
makes — offering custom initials, delivering a hand-edited PDF, selling it under a certified
product's name — so the buyer's copy is the only one nobody checked, and the one most likely
to be wrong because it is the only one edited by hand. It is *routed*, not refused: it becomes
a product and goes through the chain. The pricing follows the same line, because a
presentation choice costs nothing per order and a construction choice costs a full chain run.

`commerce/club.py` (#253) names what the appeal hides: a club is payment for work that does
not exist yet — a liability before it is income, and the only product where failing to deliver
costs more than the sale. Of its four questions, three need buyers or a policy read; **the
cadence is answerable today and is the one that ends clubs.** Month one ships what already
existed; month two needs a new pattern, certified, on a date somebody else chose. It requires
1.3× headroom, because a club that exactly fits its period has no room for the week somebody
is ill, and there is always that week.

`commerce/referral.py` (#256) draws the same line for a third time — a reward is for an
action, never an outcome statement — importing the refused phrases from `commerce/reviews.py`
rather than listing them again. A mechanic nothing can attribute is refused *before* it runs,
because one that cannot be judged will be judged anyway, favourably, by whoever proposed it.

**#257/#258/#259 — proof, reviews, and the sprint that mostly happens beforehand.**

`commerce/reviews.py` (#257): the prohibition's third verb is the precise one. *Gating* is
not buying — it is withholding something the buyer already paid for until they leave a
rating, and no money moves, which is exactly why it ends up in a support template written by
a shop that would never buy a review. Eight phrasings are refused by name. The analytical
half has an arithmetic problem the rule does not: a shop with three reviews has a rating one
bad day away from 3.7, so the star distribution is **refused below twenty rather than
caveated** — a caveat is read once and an average is read every week. The useful output is
the routing: a *misunderstood* theme is usually a missing disclosure, and sending it to the
design queue rewrites a pattern that was correct.

`commerce/buyer_trust.py` (#258): a gallery entry belongs to a pattern version. A customer's
photograph of v1.0.0 beside a listing selling v1.2.0 is proof of a *different object*, and it
is the most believable wrong thing on the page because it is real — so it is marked, not
removed. The colourway is now required (the yarn already was, at construction). Whether proof
lifts conversion needs both arms: a gallery added to every listing measures the month it was
added.

`commerce/first_hundred.py` (#259): read as written, the requirement produces a plan that
starts on the day of the first sale — the wrong day for four of its five priorities. The
first buyer either gets the file or does not; a listing is written before anybody reads it;
prevention that begins after the first sale is not prevention. **Only rapid support genuinely
needs customers.** So four priorities are checkable today and are not waiting for anybody,
which matters because the alternative is comfortable: a plan beginning at the first sale lets
all four sit unfinished while the shop feels prepared. The sprint ends at a hundred — a
permanent sprint is just how the company works — and it may spend support hours, sample costs
and a slower release cadence, never the price.

**#249/#250 — the creator portfolio, and the two programmes that must not merge.**
`growth/creators.py` extended. "Scale high-contribution relationships and stop weak ones" is
correct, and applied to a roster where most relationships are unmeasured it stops the ones
nobody got round to measuring — a null sorts to the bottom of a ranking, and the bottom is
where things are cut from. So an unmeasured relationship is classified `unmeasured` and named,
never weak. For #250: a tester is paid to find what is wrong; an ambassador is given a
relationship for saying what is good. Under one agreement the test fee becomes a review fee —
and the testing stops working, because a tester whose standing depends on enthusiasm reports
fewer defects, and the physical sample is the most expensive signal this company buys. Two
agreements, a recorded revocable consent, and testing terms that mention anything public are
refused by name.

**#251/#255 — tools that answer first, and the number the flows refuse to be judged on.**
`growth/tools.py`. A calculator that withholds its answer until somebody hands over an address
is a lead capture form wearing a calculator's name. The more useful finding is that **five of
the six tools the requirement names are arithmetic this system already runs on every release**
— yardage from the twin, finished size from the compiler, make time from the lead-time engine,
the last practical make date from the calendar, colourway contrast from the substitution guide
— so what is missing is a surface, which is one owner action rather than five engineering
ones. For #251 there is no open-rate field anywhere: an open is not a business outcome, a flow
judged on opens is optimised toward subject lines and away from the purchase, and a segment
built on one is built on whether somebody's mail client fetched an image. Incremental
contribution needs a holdout, and `growth/experiments.py` already refuses without one.

**#248 — the clip that outlives its pattern.** `growth/video.py`. The instruction with
weight in this requirement is *keeping a canonical tutorial*, and the reason is not tidiness:
five platform videos with no canonical source diverge silently, and a corrected pattern
leaves the troubleshooting clip telling three thousand people to do the thing that was wrong.
That is the same defect as a stale PDF, so a module is recorded in `ops/artefacts.py` against
the design it was cut from and goes stale by the same mechanism — found by the hourly sentinel
rather than by somebody remembering that videos exist. Repurposing is checked: a twelve-minute
technique explanation cut to fifteen seconds is refused as a trailer for nothing.
Troubleshooting modules are seeded from #247's observed questions, so a clip about a problem
nobody has had is refused.

**#246 — a pin set that is genuinely several pins.** `growth/pins.py`. The requirement says
"avoid spammy duplicate pins" and the mechanism is not about images: five pins that differ in
crop, overlay and filter are one pin posted five times, and they are indistinguishable from
five pins to any check that looks at the file. What makes two pins different is what they are
*about* — seven reasons anybody saves one object — and the four things a pin factory produces
when asked for variants are named as not being pins. Amplifying a winner means another angle;
the same pin again with a different overlay is the same spam arriving through the door marked
success. The schedule is the seasonal calendar's own milestones, because a second set of
seasonal dates is a second answer to when the work is late.

**#247 — search clusters from questions makers demonstrably asked.**
`growth/clusters.py`. A keyword list produced by asking a model what crocheters search for is
a list of things that *sound* like searches, and it is indistinguishable from a good one
until a year of writing has been spent on it. This company already holds a list it has
evidence for: the complaint themes counted from observed reviews. A complaint is an
informational intent that arrived too late — "the stitch counts do not add up", "I ran out of
yarn", "it did not fit" are the questions somebody would have typed a week earlier. A theme
nobody has seen three times is one customer's bad day rather than a cluster, on the observer's
own constant. A cluster with no paid destination is refused — and the download-help cluster
says outright that it sells least of all, which is better than pretending every article sells
something.

**#233/#234 — the ladder, and what a bundle is.** `commerce/ladder.py` names the rungs with
nothing on them (a buyer who climbs to one arrives and finds nothing) and the steps that are
too big: a buyer who has spent CA$4 does not next spend CA$20, and a rung five times the last
one is a missing step wearing a price — invisible in a tier diagram, because both rungs are
occupied. The discount rule is the requirement's own sentence made mechanical: a tier on sale
more than a third of its live days has no regular price left, and the flagship is never
routinely discounted, because it is the one product whose job is to say what this shop is
worth. `commerce/bundles.py` makes "natural" checkable — same occasion, same yarn weight,
same collection, same recipient, same room — and delegates *did it work* to the attribution
engine that already refuses without a baseline, because two answers to one question means the
flattering one gets quoted.

**#188 — `finance/governor.py`, and the three numbers it refuses to invent.** Cost is
attributed across the five dimensions the requirement names, and every dollar is either
attributed or named `unattributed`, with the two summing to the bill or the table being
refused outright — because an attribution table that sums to less than the invoice is worse
than none, and the missing spend is always the spend nobody has a story for. The other three
controls are measurements this company cannot take, and each says so: an anomaly needs
fourteen days of baseline (a detector with none fires on the first real day of work, teaches
everybody to ignore it, then never fires again); marginal value has a zero numerator while
no order is attributed to any spend, and calling that "worthless" would justify cutting the
spend that has not had time to work; and parallelism cannot be judged from one worker count,
which answers with whatever was running when somebody asked. The verdict is completions per
*minute*, not per worker-minute — that always falls when a worker is added, and the question
is whether the queue drained faster.

## Previously — last completed milestone
**Freshness is proved, not assumed — and a trajectory that refuses to state a probability.**

**#171/#173 — every derived artefact tied to its evidence, and a sentinel that can stop a
publication.** `ops/artefacts.py`. The chain already fingerprinted the three things it had
been burned by; what did not exist was the general statement. Every artefact class the
requirement names now records the fingerprints of what it was made from, and the rule that
answers the requirement's own sentence — *a stable slug must never make stale output appear
current* — is that **an artefact with no provenance row is unproven, never fresh**. It has
no mismatch to report, so a sweep comparing only recorded rows calls the estate clean and
leaves every un-instrumented file looking current.

The sentinel is hourly, and three things make it real rather than decorative:

- Its block is the existing `halts_publication` flag that `runtime/pipeline.py` already
  consults, and the test asserts the publish path **refuses** rather than asserting a row
  was written. A block that is only a row is a claim about a block.
- It enqueues the existing `chain.rebuild` for each stale product, so the deterministic
  rebuild is triggered rather than recommended.
- It can clear. An artefact whose upstreams match again resolves its own incident, because
  a sentinel that can only add incidents halts the company the first time anything is
  rebuilt.

A mismatch and an absence are graded differently, on the requirement's own wording — it
blocks on *any mismatch*. An absence is a backlog: blocking on it the first time this ran
would have halted the whole catalogue over instrumentation nobody had fitted. `graduation()`
states the condition for enforcing absence as a count, not a judgement. Both of #173's named
test conditions are exercised: deliberate stale-data injection, and a restart through a new
`Database` against the same file.

**#26 — a trajectory made of assumptions, labelled as one.** `scale/trajectory.py`. The
requirement's last sentence governs the module rather than being appended to it: **no
function returns a bare probability**, because a number detaches from its provenance the
moment somebody writes it in a summary. Below a 60% observed share the run is named an
assumption space and states no probability at all — today that share is zero. The output
that *is* useful with no data is the sensitivity ranking: it does not say what will happen,
it says which assumption the answer is hostage to, which is the one thing worth going and
measuring. The seed is the date, because the first thing anybody does with a nightly number
is compare it to last night's.

*A process note worth keeping:* `ops/artefacts.py` was first written as `ops/provenance.py`,
beside the existing `radar/provenance.py`, and its test file overwrote
`tests/test_provenance.py` — 161 lines of #38/#50 coverage, recovered from git rather than
from memory. The near-duplicate name was the whole cause (B-364).

## Previously — last completed milestone
**The commercial spine: two production queues, a creator roster, offers, baselines,
experiment memory, the free-to-paid funnel and where the week goes.**

Nine requirements landed together because they are one argument. #5 decides which queue a
product is made in, #13 decides the shape it is sold in, #10 decides what brings somebody to
it, #9 and #21 decide who can vouch for it, #14 decides what its numbers are compared
against, #16 decides what a test of it may claim, #22 decides what happens when one of them
finally works, and #30 decides how much of the week any of it gets. Each is summarised in
its registry note; what follows is what they have in common.

**Every one of them is a refusal that costs something now to stop a mistake later**, and in
five of the eight the mistake is the same shape this build keeps finding — *a verdict
computed from the absence of failures will always pass a run that did not happen*:

| where | the absence that would have passed | what is required instead |
|---|---|---|
| #5 lanes | a QA-stability flag somebody set | the regression corpus, its run, certified releases and open halting incidents, each read positively — an unread signal is its own refusal |
| #5 gates | "no gate complained" | a gate *run* per stage; a stage nobody reached is absent, and absent is not passing |
| #16 listing tests | a listing with no exposure, read as a failure | a listing nobody saw did not fail, it was not tested — and an unreadable test writes nothing to memory, because a disproof would block an idea nobody tried |
| #14 baselines | a refund rate of zero on a shop with no orders | absent, named as absent; and a rate computed from three orders is a rumour with its own message |
| #10 funnel | 0% conversion from an upstream of zero | no rate at all, because 0% makes an untried funnel look like a failed one |
| #21 creators | an outcome nobody measured, averaging as a zero | unmeasured is named and blocks; spend does not scale on no bad news |

**#5 — two production queues, and the floor that stops one eating the other.**
`commerce/lanes.py`. The fast lane buys learning rate and search coverage; the flagship lane
buys authority, content depth and order value. A garment cannot be argued into the fast lane
by typing "one component" onto it under a deadline, because the pod decides what a thing is
and the deadline does not. Both lanes have a capacity floor: the fast lane eats the flagship
lane one defensible week at a time, and a catalogue of four magnificent blankets has had
four chances a year to learn what sells. The mix is a share of **making capacity, never a
count of products**. "Both retain all applicable quality gates" is structural —
`applicable_gates()` takes the product and **has no lane argument at all**, asserted by
signature rather than by example.

**#9/#21 — a roster that buys work and never an opinion.** `growth/creators.py`. The
deliverable vocabulary is closed and contains no review, so "never require or purchase
dishonest reviews" is unrepresentable rather than discouraged; a sentiment condition is
refused even when the deliverable is honest, including the one nobody writes down ("we will
send the next one if it goes well"). A stated follower count stays a claim with its source,
there is no reach projection anywhere in the module, and a test reads the source to assert
the absence. Permission is scoped: a photograph licensed for the creator's own channel is
not licensed for our listing. Outreach is a commercial electronic message and travels on
CASL's conspicuously-published-address basis, with the message requirements delegated to
`growth/owned.py` rather than restated. Seeding starts at zero spend, because a digital
pattern costs nothing to give.

**#13 — the offer is a variable.** `commerce/offers.py`. The same design sold six ways is
six propositions, and one failing says nothing about the other five, so a design may not be
retired until it has worn more than one *family* of offer — three bundles are one offer
tested three times. Both measurements are reported and neither alone, because revenue per
buyer is the one that flatters. Two of the six offers cannot be delivered today and are
named unavailable rather than quietly priced: nothing here can make a video, and a stated
answer time is a promise nobody has measured the capacity to keep.

**#14 — one funnel at a time.** `commerce/benchmarks.py`. A baseline belongs to a cell
(category, traffic source, price band, shop maturity) and a comparison across cells is
refused with the axes that differ, because the failure the requirement names is somebody
reading two correct numbers side by side. A thin cell answers, which makes it more dangerous
than an empty one, so below the floor the number is not produced at all.

**#16 — a memory that can also forget.** `commerce/listing_tests.py`. A disproof closes a
question only in the context that produced it, and reopens when the caller names what
changed; a memory that never forgets is a way to stop learning, which is the same failure as
no memory arriving from the other side. The memory is a table, because "we tried that last
year" is exactly the knowledge a restart loses.

**#10 — free work with a commercial job.** `growth/free_to_paid.py`. A free pattern for
something this company sells does not lead to it, it **replaces** it — and that failure looks
exactly like success from the inside, because the downloads go up while conversion falls. An
email is a rung only once it is consented.

**#22 — rank is not credibility.** `commerce/replication.py`. In a catalogue of three the
best seller may have sold twice. A winner normally differs from the field on every dimension
at once, each a complete explanation of which at most one is true, so candidate causes are
ranked by how *distinguishable* they are and a fully confounded winner is reported as
confounded rather than explained. The study returns its capacity on the end date whether or
not the question was answered.

**#30 — the default is not more engineering.** `scale/allocation.py`. The requirement
names the failure it prevents, and it is the one this system is most exposed to rather than
least: engineering work is always available, always visible, always finishes, and never
requires anybody outside this company, while distribution requires an audience that does not
exist yet and can always be defensibly deferred until the thing being distributed is better.
A shop can be improved indefinitely and shown to nobody, and no week feels wasted. So the
mature 30/30/30/10 mix is the default rather than the reward, distribution has a floor no
bottleneck may cross, and an unmeasured bottleneck is not a bottleneck — guessing produces
whichever term somebody has a benchmark for, which is the one nearest the code. "After core
engineering stabilizes" is #5's evidence, imported rather than restated, because two
definitions of stable is one definition and one excuse. It runs as a **weekly cadence**
(`capacity_review` → `ops.capacity`, GREEN, spends nothing) rather than as a function
somebody remembers to call, because a module nobody calls is precisely "whatever was easiest
to pick up" — the thing the requirement prevents. Its handler is executed end to end by its
own test, since a handler whose interesting half no test runs is an untested handler with a
passing test beside it, and this build has shipped that twice.

*Worth recording, because it is the same slide happening inside the module written to stop
it:* the first draft's build-phase mix put distribution at 15% against the 20% floor it
enforces everywhere else, with a docstring claiming the floor was respected. The invariant
test — every mix this module ships passes its own check — is what caught it, and it is the
only kind of proof that survives the next edit.

**One gate was added and two requirements re-parked.** #4 and #10 were parked on
`browser_vision` and `live_listings` because those were the nearest existing keys, and
neither is what they wait for: a concept post and a free article wait on somewhere of this
company's own to publish them. `owned_surfaces` now exists. A gate that is nearly right is
worse than a new one, because it opens on the wrong day and puts work in the ready queue
that still cannot start.

**Live:** `/api/lanes`, `/api/creators`, `/api/offers`, `/api/benchmarks`,
`/api/listing-tests`, `/api/free-to-paid`, `/api/replication`, `/api/allocation`.

## Previously — last completed milestone
**Four commercial requirements, and the one defect shape behind three of them.**

**#5 — two production queues, and the floor that stops one eating the other.**
`commerce/lanes.py` operates the fast lane (ornaments, kitchen and bath textiles, simple
decor, selected hats, suitable simple amigurumi, quick seasonal gifts) and the flagship lane
(premium blankets, major collections, selected garments, sophisticated seasonal products).
What the fast lane buys is learning rate and search coverage; what the flagship lane buys is
authority, content depth and order value. Three things make it code rather than a policy
note:

- *A garment cannot be argued into the fast lane.* The pod is a necessary condition and the
  product's own measurements decide the rest, so typing "one component" onto a cardigan
  under a deadline changes nothing. This is the commonest way a fast lane goes wrong.
- *Both floors are enforced.* The fast lane eats the flagship lane one defensible week at a
  time — the fast product is always the better use of *this* week — and a catalogue that is
  all flagship has had four chances a year to learn what sells. The mix is a share of
  **making capacity, never a count of products**, because a flagship costs several fast
  products and a count that looks balanced is a capacity split that is not.
- *"Both retain all applicable quality gates" is structural.* The list is the release
  chain's own `CANONICAL_STAGES`, imported rather than retyped, and `applicable_gates()`
  takes the product and **has no lane argument at all**. A test asserts that by signature
  rather than by example, because an example only proves the case somebody thought of.

Flagship is never merely "not fast": substance is proved, and a product that is neither
simple enough to buy learning rate nor substantial enough to buy authority is routed to
neither queue and told so. A Class B fast-lane product says out loud that a physical sample
sets its wall clock — which is why the trend lane (#291) takes Class A only, and why a test
holds #291 at least as strict as this lane so it cannot become an exemption in a second
costume. Live at `/api/lanes`.

**The requirement's own opening — "after core QA stabilizes" — is read from records.**
The tempting implementation is a boolean somebody sets. `qa_stable()` instead counts the
regression corpus, runs it, counts certified releases and reads unresolved halting incidents,
and **an unread signal is its own refusal**. `RegressionRun.ok` is true for a run that
checked nothing, so the fixture count decides whether there is a verdict at all. Until the
chain is steady there is one queue — running exactly the same gates, because nothing about
the checking ever changes here.

**#4 — pre-production demand validation, where the value and the hazard are the same act.**
A picture of a thing that does not exist, posted where people buy things, is a pre-order
somebody will try to place. `commerce/preproduction.py` requires the concept to be named as
one in words a scroller reads rather than in a trailing hashtag, refuses every phrase that
promises a purchase, and refuses a price — a number with a currency in front of it is an
offer. There is **no code path in the module that can author an engagement number**, and a
test asserts the absence by reading the source, because "we would never" is not a control.
Nothing is published: no social credential has been granted. The refusals run anyway, so
they are tested before the day they matter.

**#268/#269 — the cross-border lens, and exact money.** The benchmark this company measures
itself against is a US shop, so `commerce/markets.py` answers *whose language is this* before
any comparison is read as a finding, and names the holidays that do not transfer.
`finance/currency.py` carries `Money`, `Rate` and a fee schedule that includes the two fees
that quietly eat a cross-border margin: currency conversion and the regulatory operating fee.

**#240 — a catalogue competing with itself, and the stuffing that "fixes" it.** The two
failures are opposites, and a module that counted one would push the catalogue into the
other, so both are counted. Its own test caught the module inverting: a facet stated by a
single listing was reported as 100% concentrated, which made the least crowded facet read as
the most crowded.

**The shape behind three of these** is the one this build keeps finding, and it is worth
naming again because it arrives in a new costume each time: *a verdict computed from the
absence of failures will always pass a run that did not happen.* It was a QA-stability flag
in #5, a gate list checked by "nothing complained" in the release path, and "flagship" read
as "not fast" in the routing. Each fix is the same fix — require positive evidence that the
work was done, never the absence of a complaint.

## Previously — last completed milestone
**The tournament runs at scale, the scorer was finally fed, and the queue's top item was
work nobody could start.**

**#3 — the tournament at its specified size.** The requirement asks for roughly 75-100
*inexpensive* concepts cut by five kill gates. Generating a hundred at the deep tier costs
about CA$2.52, which contradicts the requirement's own word: the funnel's shape is to spend
little across a wide field and concentrate cost only after it is cut. A cheap-tier
`concept_ideation` task now does 100 concepts for about **CA$0.27**, and cheapness is a
routing fact a test asserts rather than an intention. `field()` fills the field by
round-robin across reachable proven arenas so breadth is structural, and `tournament()` runs
the real funnel stages — two of them. It names the three it cannot run: proposition needs a
margin and an unmet angle, prototype needs a compile and a twin, release needs the gates, and
running them with placeholder verdicts would produce a five-stage funnel that had cut nothing
twice. First run at scale: **80 generated, ideation examined 80 and killed 0, research killed
78 — 58 sameness, 20 unverifiable.**

The first attempt was refused by the funnel's own rule that *a stage killing nothing did not
happen*. The honest fix was not to weaken it but to let a zero-kill stage prove itself:
`advance()` now takes `examined`, and a stage that killed nothing must declare its gate saw
every entrant. A count short of that is refused as a stage that partly did not happen.

It is now a weekly cadence (`product_tournament`) against the one arena this cycle's wheel
picks — one arena rather than twelve, because a field spread across every department puts two
or three concepts against each and cannot support a comparison against anything. The wheel
reserves 45% of its slots for Christmas, so the priority programme gets depth rather than a
turn: **9 of the next 20 cycles are Christmas**, starting with Christmas/garments at 96 days
against 140 observed MJs listings and no Brambleloop garment at all.

**#2 — the scorer had never been called with anything.** `score_market()` was correct
arithmetic that had never produced a number about this business, which is the same defect as
a credential nobody has used. `score_observed()` now feeds it the four dimensions first-party
observation genuinely supports — demand from observed favourites, the opening in the
incumbents' offers from the weakness hunt, what the market charges from observed prices, and
machine-verifiability from the share of a department's observed forms the compiler can build.
That is **52% of the weight**, above the floor and comparable across departments because
every department is scored from the same source. Demand and price are each a department's
median against the strongest department *in the one catalogue observed*, and say so wherever
they surface. Listing density stays unmeasured rather than being taken from a single shop's
shelf space.

**#2's deliverable clarity closed, and with it the requirement's own eight-item list.** The
note said it needed "a field the observation does not carry" — true of the stored row, not of
the payload. Every catalogue page was already arriving with each listing's description and
nothing was reading it. `intel/deliverable.py` reads it once, in memory, and stores eight
booleans: whether the listing states its format, delivery, extent, contents, stitch terms,
finished size, yarn and hook. **The facts are kept and the seller's words are not**, on the
same rule the review reader follows. Limited sizes and weak bundles closed with it; a size
letter is read only from a clause that says "size", because a bare `s`, `m` or `l` is one of
the commonest characters in a pattern listing and a matcher that read "1200 m" of yarn as a
size range would manufacture the weakness it was written to find. The two the requirement
names that no text can answer — branding coherence and whether the styling looks like this
year — are reported under `needs_vision` rather than dropped so the list could be called
complete, and **#2 is parked on `browser_vision`**.

The reading reaches unchanged listings, which is the gallery backlog's lesson applied before
it could repeat: a reading attached to the new-or-changed branch describes the shop's recent
edits and nothing else. It costs no extra request, so the whole map closes on one scan.

**The queue's top item was unstartable.** #292's own note said every re-merchandising move
this build can reach was built and the rest waits on image generation — and the executor,
which cannot read prose, went on offering it as the single highest-value READY requirement.
Hand-maintaining a second list of gated requirements inside `executor.py` is what let the two
drift, always in the same direction. The registry now declares its own gate:
`Requirement.parked_on` sits beside the sentence that states it and is written in the same
edit. A gate the registry names that no `Gate` defines is refused, because a key nothing
checks never opens and the requirement would leave the queue permanently rather than wait in
it. **Ready 90 → 88, parked 40 → 42.**

**`mjs.reviews` ran for the first time: 100 reviews read, 0 recurring complaint themes.**
Zero is a finding, not an absence — a shop with a hundred reviews and no complaint reaching
the floor of three is a strong incumbent, and the honest reading of the arbitrage opening
here is that it is not going to come from their customer service.

**Fifty-eight sameness deaths were one brief asked twelve times.** Reading the first
tournament's 78 kills as a harsh jury would have been the comfortable conclusion and it is
not what happened. Within one slot the pod, form and occasion are already identical, so a
pair only clears the novelty floor when its motif, recipient *and* function all differ — and
one brief does not produce that. The brief now varies per concept: #106's nine named pairs
crossed with #107's nine transformation patterns give **81 structurally distinct questions**,
walked with a stride co-prime to both factors so consecutive concepts never share a pairing,
and continued across batches so a slot visited seven times asks eighty-four questions rather
than the same twelve seven times. Every cross is still built through `cross()`, so #106's
near-synonym and one-dimension refusals apply: the variety is generated and it is still
checked.

Underneath it, a determinism defect. The pairing was chosen with `hash((pod, form))`, which
Python salts per process, while the docstring promised the same arena always asks the same
question. **The brief was silently different on every worker restart**, which makes any
comparison between two runs unreadable — the field moved and nothing recorded that it had. It
is a blake2b digest now, with a test that spawns three interpreters under different seeds.

**The proposition stage runs.** Two of its three checks are computable from observation. The
family test (#111) asks whether the hero's construction reaches enough roles including a
cheap one, or whether the collection would have to be forced after the hero exists — which is
exactly when the answer is always yes. The angle check is one-sided on purpose: it refuses a
concept whose every word the department uses at all is used by more than 34% of its listings,
and it does **not** endorse one whose words simply do not appear, because an absent word is
absence of evidence. **Margin is named as not applied rather than run.** Contribution after
platform fees passes every concept — a digital file has no marginal cost — and what decides a
pattern's margin is the cost to create it, which is #31 and does not exist. A check that
always passes is not a gate. A proposition stage fed below its floor of 35 is refused by the
funnel and the refusal is *reported*, because "research left too few to reach stage three" is
a finding about the field, not about the gate.

**A cadence its agent may not run dead-letters on its first fire.** `product_tournament` went
live and died at 05:12Z: `creative_director` had permission for `creative.blinded` and
`creative.expedition` and not for `creative.tournament`.
`test_every_scheduled_cadence_can_actually_run` exists for exactly this and caught it — the
push went out before the full suite's result was read, so production found it first. That is
the wrong order and it is the reason that test was written.

**#7 — what can I use instead, and how much of it.** The first question a pattern buyer asks
is the one nobody answers, and it is normally answered with a paragraph of confident prose.
`publish/substitution.py` answers it as arithmetic on the pattern's own gauge and yardage, and
refuses in three places. Gauge decides which weights substitute, not the name on the band. A
pattern with no gauge gets no guidance at all. Across fibre classes it gives a direction and
no number, because how much cotton and acrylic differ per stitch is measured on a swatch.

**I wrote the wrong arithmetic first and the smoke test caught it.** Scaling a pattern's
yardage by the ratio of two weights' lengths per 100g looks right and is wrong — that ratio
is about *mass*, not length used. At the same gauge and finished size the stitch count and
each stitch's yarn path are unchanged, so the metres barely move; what moves is how many balls
they arrive in. The wrong version gave a 900 m pattern a band of 485–900 m and **would have
sent a buyer home with half the yarn**. The regression test holds the correction and states
why the obvious arithmetic is the wrong one, because the next person will have the same idea.

It is rendered into the pattern PDF rather than parked behind an endpoint nothing calls —
which is the defect this same session spent its morning fixing in `score_market()`.

**And it found something on its first real pattern.** Every CIR this system generates declares
**worsted acrylic at 16 stitches per 10 cm, and the published band for medium yarn is 11–14**.
The stated yarn cannot hold the stated gauge. That is all eleven products. The PDF prints the
inconsistency and tells the buyer to swatch; it does not pick a side, because which number is
wrong is a swatch's answer and nothing here has swatched. Promoting it from a printed note to
a release gate would stop the whole catalogue, which is a reason to do it deliberately rather
than a reason not to. **OWNER-VISIBLE, not owner-blocking.**

**#8 — the proof stack.** Five rungs, each a query against rows: deterministic validation,
independent reverse compilation, a physical tester's example, a real customer project, a
repeat purchase. The claim level is the highest **contiguous** rung — a customer photograph
arriving before any tester made the thing licenses nothing new, and reporting the highest rung
in isolation is how a listing claims a test nobody ran. `check_claim` is wired into the policy
gate and into `certify()`, deliberately separate from the existing unsupported-claim patterns:
those refuse sentences that are never sayable, and "maker tested" is true the day a tester
finishes one and false the day before. A completed sample that **failed** is evidence and not
a proof point. Every rung states what it does *not* prove, because a ladder that only says
what each rung establishes invites the reader to round it up.

The permission half is enforced at provenance: `tester` and `customer` are permitted sources,
and either without a recorded `consent_ref` is `ASSET_CONSENT_MISSING`. A reference rather
than a boolean — somebody has to be able to go and look, and absent consent is not implied
consent. Rungs four and five read False until orders exist and are parked on the `customers`
gate.

**A remainder that needs orders had nowhere to wait.** `parked_on` covered capabilities
somebody can grant; #18's remainder needs *orders*, and nothing in the gate table could open
for that. The `customers` gate is the one entry the owner cannot grant — it counts ledger
rows, and its test asserts that no environment variable can open it.

## Four of the tournament's five stages run

**#3 stage four.** `creative/prototype.py` authors a CIR from a concept's form and
construction, compiles it, and asks the twin whether the object it describes is the one that
was asked for. No model is consulted — a test asserts the module never reaches for a gateway,
because section 2 outranks everything else. The finished size is the input and the stitch
count is **derived**, which is the direction that cannot produce a "blanket" 100 cm wide and
17 cm tall.

**The gauge is derived from the declared yarn's published band**, which makes this morning's
catalogue defect — worsted at 16 sts/10 cm against a band of 11–14 — structurally impossible
in anything this system authors.

**I shipped a bug into it and kept the bug as the gate.** My first draft alternated single and
double crochet rows under a gauge stated in single crochet. It **compiled perfectly** and
built a 150 cm throw the twin measured at 225 cm — a CIR that is internally consistent and
describes the wrong object, which is exactly what the digital twin exists to catch and what a
compile-only gate would have passed. The stage now asks the twin as well and refuses a size
drift above 20%.

Sixteen forms have geometry; **six are refused rather than sized by guess**, with reasons: a
graded garment is a size chart rather than a finished size, a shawl's size *is* its shaping, a
garland is a repeat count. Those refusals are the engineering backlog stated precisely.

**#29 — a dependency is existential when it is concentrated AND load-bearing.** The rule's two
halves pull against each other, and a module implementing only the first tells a pre-revenue
company to open a second marketplace. Today: **`ai_provider` is genuinely existential** — one
provider at 100%, and nothing needing judgement runs without it. `sku` is 100% `home_decor`,
concentrated and not yet load-bearing. `traffic_source` and `marketplace` are unmeasurable
with reasons, because "no traffic source is dominant" is true of a company with no traffic.

**Two fixture faults, and one in my own checking.** Nothing exercised the tournament's later
stages because the field double answered `in_the_round` whatever form it was asked about,
used a key stride that was a multiple of both 4 and 5 (so recipient and function repeated
identically every batch), and wrote near-identical premises. Fixed, research survivors went
2 → 24. I stopped short of proposition's floor of 35 rather than tune a fixture until it
cleared a gate — the live run reached 45. And my own spot-check command, `… | grep "^FAIL" ||
echo clean`, reported clean on a file that failed to parse. Checks are by exit code now.

Suite **1506 passing, 0 failing**.

## The first tournament at scale, and the three price tables underneath it

**2026-09-20T06:04Z, job 1718, Mother's Day / garments: 80 generated → research kept 45 →
proposition kept 11.** Research's kill rate went from 0.975 to 0.438, inside the
requirement's 35–45 target for that stage. The 58 sameness deaths in the first run really
were one brief asked twelve times, and the per-concept invention crosses fixed it. Three of
five stages ran; `proposition_refused` is empty, so stage three cleared its floor of 35
legitimately.

**It also reported `cost_cad: 0.0` for eighty concepts, and the month's spend did not move.**
That is not possible, and chasing it found three price tables that disagreed.

- The cheap tier routes to `claude-haiku-4-5`; the billing table held only
  `claude-haiku-4-5-20251001`. `PRICES.get(model, (0.0, 0.0))` priced **every cheap-tier call
  at nothing**, so the CA$25 monthly ceiling could never be reached by cheap work — an
  unbounded budget reporting zero, the same defect class as the `kind="model"` versus
  `kind="llm"` bug from the same night.
- `AnthropicProvider.__post_init__` defaulted an unknown model to zero while `_cost_for`, ten
  lines below, raised saying *"an unpriced call is an unbounded one"*. **Two code paths for
  one rule, and the silent one was the one the gateway used.**
- Routing restated the deep tier at USD 5/25 per million tokens; the provider bills 15/75.
  **Every estimate in the system was a third of the truth** — which is why the first
  expedition, estimated at CA$0.15 a field, cost CA$1.02.

One price table now. Routing reads it rather than restating it, an unpriced model is refused
at construction, and a test locks the tables together. **CA$25 buys about 64 release-blocking
blinded comparisons a month, not the 192 a passing test used to believe** — the assertion was
corrected, not the price.

**The wheel could starve its own priority programme.** The run picked Mother's Day, not
Christmas — correctly per the schedule, and that is the bug. Twenty slots with the first nine
reserved, positioned by a week number counted from the Unix epoch, so the phase was
arbitrary: it landed at a non-priority position with Christmas 96 days out, thirteen cycles of
runway left and the next Christmas slot eight cycles away. **A reservation a phase offset can
push outside the runway is not a reservation.** The turn is capped at the runway now and the
slots are spread across it, so the worst wait for a Christmas cycle from *any* phase is 2
instead of 8.

**#31's attribution closed.** `registry.record_cost` always accepted a job id; `ModelGateway`
never passed one, so every model cost reached the ledger with a null job and `unit_costs()`
could match none of them to the artefact that caused them. Correct arithmetic over an empty
attribution — the same shape as a scorer nobody feeds. An artefact can now be produced by
several actions, and one whose count lives in the row is counted from the row: a discovery
run is one audit entry that produced eighty concepts, and calling it one concept would report
a field at eighty times its unit cost, which reads as a reason to stop doing discovery.

Model spend **CA$1.17 of CA$25**. Production verify **12/12 green** at 2026-09-20T05:04Z.
Suite **1481 passing, 0 failing** before this batch.

## Previously — last completed milestone
**Discovery produced its first real products, and the headline number needed its caveat.**

At **2026-09-20T04:02Z** the weekly expedition ran live for the first time: **Mother's Day /
garments — 18 concepts proposed across fitted garment, draped garment and scarf, 18
surviving, CA$1.02.** Names from the run: *Asymmetric Dawn Yoke, Shutter Sleeve Top, Folding
Facet Jacket, Household Squares Kimono, Lit Window Wrap, Fan Wedge Ruana, Shingle Tier
Capelet, Medallion Bloom Shawl.* The loop works: a proven MJs arena with no Brambleloop
answer went in, and eighteen distinct garment concepts came out through the deterministic
gates. **This is the first time this system has invented a product outside `home_decor`.**

**18 of 18 is not a strong field and not a weak gauntlet — it is structural.** Our catalogue
is eleven home-decor products, so every garment concept scores maximum novelty against it
automatically and the jury's `sameness` critic has nothing to fire on. A novelty gate
measured against a catalogue containing nothing like the candidate **cannot fail**. The first
expedition into any new pod will survive at 100%, and that number says *we have never made
one of these*, not *these are good*. The run now reports `novelty_comparable` and states in
words what its own survival rate means.

Two sequencing defects found in the same run. It went to **Mother's Day at 231 days** while
Christmas sat at 96 and Halloween at 41 — the wheel indexed each half in whatever order the
matrix returned, so the run was aimed at the occasion whose runway was least in danger. Both
halves are now ordered soonest first. And `choose()` had picked `Halloween/bags` on the
previous cycle, an arena where nothing can still be made in time, burning the slot on every
retry; reachability is now checked where the arena is chosen.

**Measured cost correction:** the cadence comment said CA$0.32 a run. The real figure is
**CA$1.02**, about CA$4.40 a month against the CA$25 ceiling. An estimate left in place after
the real number is known is how a budget drifts.

**#2's last two weakness signals closed** from endpoints already in the sanctioned allowlist.
The deep audit records `has_video` per listing, measured only where a gallery was actually
audited — counting unknown as "no video" would turn an unfinished backfill into a
competitor's weakness. And `mjs.reviews` reads the shop's reviews weekly, counting recurring
complaint themes: **counts only, never a review's text, a reviewer or a quotation**, because
a complaint theme is a fact about a category and a review is somebody's words. That also
corrects a claim made earlier the same night — `customer_pain` was recorded unfeedable
because "inferring complaints from a competitor's catalogue is inventing them", which was
true, and reading their reviews is observing rather than inferring.

**#292** now computes which re-merchandising moves it can take instead of taking the list
from its caller. `search_positioning` became genuinely available when the credential made a
department's buyer language countable; the rest report what they wait on. The weekly
`remerchandising_review` runs the inspection "periodically inspect" asks for.

**Re-audited:** #293 → covered, #104 → data_gated, #98 → data_gated.

Model spend **CA$1.17 of CA$25**. Production verify **12/12**, dead-letter defects 0. Suite
**1420 passing, 0 failing**.

## Previously — last completed milestone
**The garment primitive, arena language, and the third form of a silent success (#104, #293).**

**The armhole division.** Garments are 140 of 438 observed MJs listings and the deepest
proven-and-unserved arena, and this engine could not build one — not for want of rounds,
shaping, assembly or grading, all of which existed. One primitive was missing: **working into
part of a previous row.** A yoke worked in rounds splits, the sleeve stitches go on hold, the
body continues over the rest; without it the compiler saw a body round consuming 32 of 48,
called it an underrun, and was right to.

`Row.skips`, `Component.holds` and `Component.resumes` now express it, with five checks —
because *"place 24 sts on hold for the sleeve"* is a promise, and an unchecked promise ships
a pattern with live stitches nobody comes back for. A sleeve two stitches short is a hole in
the armpit and compiled silently before. The writer states the division where it happens: a
divided pattern that reads *"Rnd 3: sc 32 (32 sts)"* over a round of 48 is arithmetically
correct, agrees with the twin, and is unfollowable. **A top-down yoke now compiles clean.**
`top_down_yoke` and `bottom_up` route to `joined_rounds`, so every concept construction is
buildable.

**Discovery from proven arenas.** 12 live proven-and-unserved arenas. Christmas takes the
**0.45 share the compression engine already reserves**, not one turn in twelve, and sweeps
all four of its departments rather than deepening one. Forms come from observed listings in
the pod; a form the engine cannot build is reported rather than dropped; a saturated form
must earn its place; a form carries a lane *floor* so Halloween hats stay reachable as QUICK
makes at 42 days. The pass reports `is_a_tournament: false` against the funnel's own ideation
floor, because generating 75 concepts per arena to clear a threshold is optimising for
volume.

**The existing catalogue is 0 of 11 commercially informed** — none of it aims at a proven
market, and none is even in a proven *department*. Plateau is now a checkable defect: a move
under 0.03 is not a move, and unmeasured is never reported as flat.

**#293's other half.** `arena_language()` counts terms across a department's observed titles
and sorts them into the six facets — for stockings: object=stocking, season=christmas,
aesthetic=farmhouse/rustic/chunky, skill=easy/beginner/chart, technique=cable/granny/mosaic.
Observed by construction. Marketplace furniture is separated rather than dropped, a word
meaning two things is classified as neither, and it emits single words and never a title,
because term frequency is demand intelligence and a title is somebody's expression.

**The same defect shape, three times.** An outcome indistinguishable from success while
nothing happened. (1) `arenas()` read a key the matrix does not return and reported no arenas
against 27. (2) The discovery cadence completed saying "nothing to do" and consumed its
weekly window. (3) It then completed reporting `ran: true, proposed: 0, cost_cad: 0` twice,
because a prompt asked for six concepts inside a 2000-token budget and came back as truncated
JSON — a budget too small is not a transient fault, and the retry bought a second identical
failure. The re-drive rule now reads **work done, not a flag**: a completed job whose every
work counter is zero is a no-op. The flag was the unreliable half each time.

Also found: the jury's anti-copying critic was never passed its benchmark, so the one gate
against arriving as an MJs clone never fired. It compares the five things both sides state
and reports its own limit — catching a borrowed *execution* needs a product in hand, which is
the `benchmark_purchases` gate.

Model spend **CA$0.1525 of CA$25**. Production verify **12/12**, queue depth 0, dead-letter
defects 0 (120 Shadow Mode publication refusals, working as designed). Suite **1383 passing,
0 failing**.

## Previously — last completed milestone
**Discovery that starts from a proven market rather than from what compiles (#104).**

The direction of travel is inverted. Discovery no longer begins with a brief and looks for a
market; it begins with a market the benchmark has *proven*, in a department this catalogue
does *not* answer, and asks what would have to be built. Three refusals carry the owner's
instruction that not every concept may become another throw, runner or garland:

- **The arena picks the form.** An expedition into `hats` produces hats, and the forms it may
  target are counted from observed listings in that pod — the vocabulary comes from what the
  market contains, not from what this compiler finds easy.
- **A form the engine cannot build is an engineering requirement, not a rejection.** Dropping
  it is exactly how a catalogue converges on flat panels while believing it is being
  selective.
- **A saturated form has to earn its place.** Another rectangle throw is not discovery.

Live against the real matrix: **12 proven-and-unserved arenas**. Christmas/garments (140
listings, 97 days), Thanksgiving/blankets (85, 23 days), Halloween/hats (85, 42 days),
Christmas/blankets, Christmas/hats, and bags across four occasions.

The gauntlet is deterministic and every gate may empty the field: buildable form →
adversarial jury → novelty against the catalogue → novelty against its own siblings →
feasibility, which is marked and never fatal. Siblings are checked pairwise because a field
can pass every individual gate and still be one idea submitted five times. **An empty field
is a real answer**, and a better one than a survivor that only survived because the gauntlet
was loosened until one did.

**Four defects found building it, three of them live.**

1. **Six of twenty-two forms were absent from the buildability map**, `stocking` among them.
   An absent form has no buildable construction, so the pairing rules silently refused to
   build a Christmas stocking — a pod the benchmark carries thirteen listings in and the
   owner names a top priority. A form missing from that table is not unconstrained, it is
   unbuildable, and nothing said so.
2. **`arenas()` read `proven_gaps`; the matrix returns `proven_and_unserved`.** Production
   reported no arenas at all against a matrix holding twenty-seven. Second reader/writer key
   disagreement of the build, same comfortable failure both times: a wrong key does not
   raise, it returns empty, and empty is the flattering answer.
3. **A lane derived from physical size dropped Halloween/hats at 42 days** — a beanie, which
   is exactly the product the compression doctrine says to reach for as an occasion closes.
   Size and make time are correlated and not the same thing. Forms now carry a lane *floor*
   and take the fastest viable lane at or above it.
4. **A cadence that wrongly said "nothing to do" consumed its window.** `arena_expedition`
   fired, hit defect 2, reported no arenas, and **completed**. It would have sat idle for
   seven days after the repair, and the dead-letter re-drive cannot help because the job did
   not fail. `ops.queue_check` now re-drives both shapes under one bound — once per deployed
   commit — and `arenas()` raises rather than returning empty when the matrix contradicts
   observed listings.

**The garment gap is one named primitive, not a vague difficulty.** Joined rounds, increase
and decrease ops, placed multi-component seams and size grading across a run all exist —
`cir/grading.py` says in its own docstring that it was written for the garments pod. What is
missing is **working into part of a previous row**: `Row.into` names a row index and the
compiler takes that whole row's count, so the armhole division cannot be expressed and a
cardigan can only ship as a flat panel nobody can wear. That one primitive unblocks
`top_down_yoke` and `bottom_up`, and with them **140 of the 438 observed listings** — the
deepest proven-and-unserved arena.

Two new instruments earned their place immediately. `GET /api/queue/dead` groups dead letters
by failure: the 121 turned out to be 120 Shadow Mode publication refusals working as designed
plus one real defect. `GET /api/queue/cadences` reports when each cadence last ran and what
it returned, and found defect 4 in one request — a cadence that completed with nothing to do
is invisible at queue depth zero and looks exactly like a healthy system.

Model spend: **CA$0.1524 of CA$25**. Suite **1342 passing, 0 failing**.

## Previously — last completed milestone
**The first blinded run scored 11-1 for this catalogue and was worthless (#94).**

It ran in production for CA$0.1523. Twelve same-pod pairs, position share exactly 0.50,
comfortably above the sample floor, `valid: true`, verdict `ahead`, win rate 0.9167. Both
guards green. The number was meaningless and the judge's own reasons say why — it named
"throw" in nine of the twelve:

> *"A cosy rectangle throw gives far more warmth and everyday use than a single pillow."*
> *"...whereas a single coaster feels like a small extra."*

Our home decor is mostly rectangle throws; this benchmark's home decor is pillows, coasters
and wreaths. The run measured **which object is bigger**, which is true whoever designed
either one. That is a third confound beside position bias and a thin sample, and neither
existing guard flinched at it.

It cannot be corrected after the fact, so it is removed by construction: pairing is now
same-**form** as well as same-pod. A throw is judged against a throw. The honest cost is
that almost nothing remains to compare — `form_overlap()` reports **0 of 11 concepts have a
like-for-like opponent**. This catalogue makes garlands, ornaments, table runners, wall
hangings and flat panels; this benchmark's home decor does not. That is a finding about the
catalogue, not a limitation of the measurement, and a more useful one than "92%".

Two rules came out of it. A run that cannot reach the sample floor is refused **before** it
spends, because paying for a result already known to be `unmeasured` is worse than not
measuring. And results carry a `method_version`: the 11-1 verdict is still served, marked
superseded and not valid, because the record of a measurement that was confidently wrong is
what stops the same mistake being made confidently a second time.

**The measurement was worth running early precisely because it was wrong in a way no amount
of reasoning about the design had produced.**

Two more #94 measures now exist, both computable and both awkward reading. **Theme fatigue**,
per field because "the catalogue is repetitive" is not actionable: pod, feeling and make_lane
each hold exactly **one** distinct value across all eleven products; recipient is 82% `self`.
A field with one value is not a preference, it is a missing field. **Novelty distance**
reports the minimum beside the mean, because the mean is the reassuring number and the
minimum is the true one — mean 0.34, minimum 0.25, closest pair winter-village-graphghan
against nordic-star-ornaments.

**Two production defects, both found by the new dead-letter endpoint in one request.** 121
dead letters turned out to be 120 Shadow Mode publication refusals working exactly as
designed, plus one real failure. `/api/status` now splits refusals from defects, because a
three-digit number that is 99% healthy is an alarm nobody can read. The real one was my own
handler, and fixing it surfaced the serious one: **`ModelGateway` ledgered its calls as
`kind="model"` while every ceiling counts `kind="llm"`**, so a real gateway call would have
been invisible to the budget — the ceiling would have read CA$0.00 indefinitely while money
left the account. It had never bitten because nothing had ever constructed a ModelGateway;
the blinded run is the first thing that does, and would have been the first spend, uncapped.

**A deploy now re-drives the dead letters it fixed, exactly once per commit.** The blinded
job died on a typo and would have sat in the graveyard until its next monthly window, thirty
days after the repair. A commit that did not fix the defect kills the job again and it waits
for the next one. Verified in production: dead-letter defects went 1 → 0 by itself, and the
re-driven job ran.

Model spend to date: **CA$0.1524 of the CA$25 monthly ceiling.** Suite **1312 passing, 0
failing**.

## Previously — last completed milestone
**The blinded human/agent comparison, and what it refuses to tell you (#94, #104).**

Everything #94 asks for that code can compute has been in `tournament.scorecard()` since
Build 1. The half that needed a judge became possible on 2026-09-19: the model gate opened
from a recorded successful call, and the benchmark scan returned 438 real listings. The
human side is a catalogue a person designed and a market has already paid for.

This is the owner's product-quality concern turned into a number. The creative gate has been
reporting 0 of 11 survivors with emotional appeal as the dominant failure, and *"are ours as
appealing as theirs"* has been an opinion.

Three guards, because this measurement returns a confident number whether or not it measured
anything:

- **Blinding is mechanical.** `blind()` refuses a card carrying a tell and refuses one with
  an empty field, because a card is identifiable by its holes. The harder problem was
  register: a Concept carries evocative free text in motif, premise, palette_story and
  function; a benchmark listing carries none of it, and our prose against their keywords
  would let a judge separate the sides without reading either. So the free-text fields are
  **not on the card at all** — the comparison is over the structural promise both sides
  genuinely state, rendered from the same enumerations.
- **A judge that prefers the first option is measuring order.** Presentation order is
  randomised per pair and recorded before judging. Past a 70% position share the run is
  reported **invalid and discarded rather than corrected**: a correction applied to a judge
  that was not really reading puts error bars around nothing.
- **A win rate from four pairs is not a capability.** Below twelve judged pairs there is no
  rate, only `unmeasured` — which is not parity and not losing.

What it deliberately does not compare is **the photograph**, which is most of why a listing
sells. That half needs browser/vision and says so in its own output.

Live readiness: 438 benchmark listings, **220 usable as opponents (50%)**, CA$0.1294 per
pair, 193 affordable, CA$0.0001 spent of CA$25 this month. The 218 that cannot be opponents
are named by reason — 143 state no feeling, 42 state no product form, 29 are bundles, 4 are
guidebooks or unclassified. Refusing to describe an unreadable listing creates a selection
bias toward richly-titled ones, and `readability()` reports it, because an unstated bias is a
wrong number rather than a limitation.

It runs on a **monthly** cadence and there is no endpoint that runs it: a request that spends
the model budget should not be one URL away. Monthly is a spending decision — twelve pairs is
6% of the ceiling, weekly would be 27% for a number that cannot move that fast, and a
measurement that expensive is one somebody eventually switches off.

Our side is the existing catalogue through `audit.concept_from_design`, and that is the
point: all eleven products are `home_decor` and all eleven are `cosy`, because the generator
has no field in which to be anything else.

**#303 is parked on browser_vision** — its API half is complete and live (438 listings, 2
unclassified, stored drift 0, palette closing on the gallery backfill), and the two columns
left are judgements about a photograph. **#94 and #104 were re-audited from owner_gated to
partial**: both were parked on model_provider, that gate opened, and their status strings had
not caught up.

Suite **1297 passing, 0 failing**. Production 12/12 verify, queue depth 0, watchdog moving.

## Previously — last completed milestone
**The 58 unrouted benchmark listings, and the six routing defects reading them exposed
(#303, #207, #210, #312).**

The first full observation of the MJs catalogue put 58 of 438 listings — 13% — into
`unclassified`. That number was in the dashboard and was not actionable: it said one listing
in eight reached no specialist and gave nobody the evidence to fix it. `market_map.gaps()`
and `GET /api/mjs/coverage` now name them, with the terms recurring across them, because the
pod vocabulary may only grow from observed titles. Widening it from imagination produces pods
that match nothing and a router that drops the same listings while looking broader.

Reading the 58 found **three defects in the router and three more in the fixes for them**,
and every one needed a real Etsy title to appear at all:

1. **Substring matching, failing in both directions.** `"slippers" in title` missed "Crochet
   Slipper Boot Pattern"; `"vest"` is inside `"harvest"`, so "Hello Harvest Chunky Throw
   Blanket" and "Harvest Twist Ear Warmer" were both filed as garments. A missed listing is
   visible in the unclassified count. A wrongly-routed one is invisible forever.
2. **A vocabulary narrower than the catalogue it watches.** Four departments had no
   specialist: kitchen and bath textiles, amigurumi and soft sculpture, multi-pattern ebooks
   and guidebooks.
3. **Stored routing that never updates.** The scanner routes on discovery and short-circuits
   on an unchanged fingerprint, so a widened vocabulary would have reached only listings MJs
   later edits. Both fixes above would have looked like they worked and changed nothing.
4. **A motif taken for a form.** Adding "pumpkin" sent "Hello Pumpkin Mosaic Cardigan" and
   "Pumpkin Pillow Crochet Pattern" to the specialist in stuffing firmness — the same
   invisible misrouting, reintroduced by its own fix.
5. **HTML entities.** Etsy returns titles escaped; "Men&#39;s Cardigan Pattern" tokenised to
   `men 39 s cardigan pattern`, and the bundle rule read thirty-nine patterns. Seventeen
   cardigans and four blankets had moved pods on a possessive apostrophe.
6. **A stemmer that cost a pod its own keyword.** Stripping "es" after s/x/z/h turns "boxes"
   into "box" and "purses" into "purs" — the bags pod would have stopped matching `purse`.

The rules that came out of it: match on words, not substrings; **form beats motif**, always;
**the earliest match wins**, because a title that names two products names the one it is
selling first; a stitch name and a character name are not products.

**Verified in production.** 438 listings, **unclassified 2**, stored routing drift **0** after
the scan reconciled it. The two that remain name no product at all ("Dusty Rose Baby Set"),
and guessing is the worse answer. Twelve pods now carry the catalogue:

| pod | listings | | pod | listings |
|---|---|---|---|---|
| garments | 140 | | bags | 17 |
| blankets | 85 | | kitchen_bath | 14 |
| hats | 85 | | ornaments | 13 |
| collections | 29 | | home_decor | 11 |
| amigurumi | 20 | | stockings / seasonal_gift | 10 / 10 |
| | | | education / unclassified | 2 / 2 |

**Two merchandising mechanisms this company does not have, now counted rather than sensed.**
MJs sells 29 multi-pattern collections and 2 standalone guidebooks. Collections are a pod
rather than a keyword because a six-pattern ebook is a bundle first: routing it to whichever
product its title mentions first hides the mechanism.

Also fixed: `POST /api/mjs/scan` was defined twice. FastAPI serves the first match, so the
second handler could never run — and both bodies agreed, which is the dangerous version,
because the module name `api_mjs_scan` referred to the unreachable one. A test now asserts no
method and path pair is registered twice.

28 new regression tests, each built from an observed title. Suite **1268 passing, 0 failing**.

## Previously — last completed milestone
**The Etsy credential was verified by using it, and the benchmark mission ran for the first
time (#206, #301, #303, #319, #2).**

The developer application was approved on 2026-09-19 and the credentials are in Railway. The
owner's condition was that the gate open from demonstrated capability, and Etsy makes that
condition concrete rather than theoretical: **v3 refuses the keystring alone** with `Shared
secret is required in x-api-key header`, so a half-configured credential returns 403 and
looks exactly like a working one to anything checking whether two variables are set.

- `etsy_public.probe()` makes the smallest sanctioned read — an application ping returning an
  application id and nothing about anybody's shop — and records the outcome as a row. Both
  the `etsy_api` and `benchmark_observation` gates read that row. A six-hourly cadence runs
  it *ahead of* the scan that depends on it, so the gate closes again by itself if the
  credential is revoked, rather than being discovered by finding an empty catalogue.
- Nothing about the credential reaches the row, the audit detail or a failure message, and a
  test searches the recorded evidence for its parts.
- **Verified in production at 2026-09-19T18:03Z**: `ok: true`, application id returned. Four
  gates are now open and nine requirements un-parked by themselves.

**The mission then ran, live, at 18:04Z. 438 listings observed** from
`MJsOffTheHookDesigns` through the sanctioned read-only API: garments 141, blankets 88, hats
82, seasonal gift 19, bags 18, stockings 13, ornaments 13, home decor 6, unclassified 58. Ten
listings and ten galleries audited in depth. `observation_state: observing`, and the mission's
own honest statement is now *"coverage above is measured, not assumed"* rather than a
description of what it would do with a credential.

**The coverage matrix now has both halves (#299), and it reads as a plan.** 27 department
and event pairs where the benchmark was observed selling and this catalogue has no answer,
ordered by how deep they are and how soon the occasion is. The top of that list:

| event | department | benchmark listings | days away |
|---|---|---|---|
| Christmas | garments | 141 | 97 |
| Thanksgiving (CA) | blankets | 88 | 23 |
| Christmas | blankets | 88 | 97 |
| Halloween | hats | 82 | 42 |
| Christmas | hats | 82 | 97 |

The discipline that makes the matrix worth having: a department is *proven and unserved* only
when somebody actually looked. An unobserved market and a market with nothing in it render
identically — both as an empty cell — and the empty cell is the one somebody points at in a
planning meeting.

**Two defects found by production disagreeing with itself.** `/api/mjs` reported 438 listings
known while the new matrix reported zero observed, reading the same table. The scanner writes
`benchmark_key` `mjs_off_the_hook_designs`; the living market map and the new matrix both
defaulted to `"mjs"`. A wrong key does not raise — it returns an empty result indistinguishable
from the truth — so **the market map had been reporting "no benchmark listing has been
observed" from the moment the first scan succeeded**. The existing test wrote its fixtures
under the same wrong literal, which is why a closely covered module carried the defect: the
test and the code shared one assumption. Both readers now default from the scanner's own
constant, and the regression test asserts no reader carries a literal key of its own.

**The first competitive weakness this company has measured rather than assumed:** 413 of 438
observed listings carry fewer than five images. #2's weakness hunt reported `measurable:
false` an hour ago and reports a number now, which is the difference a first-party credential
makes and the reason the hunt refused to report an empty list as "none found".

Nothing was written to Etsy. The shop stays empty, Shadow Mode holds, and these credentials
authorise reading public marketplace data and nothing else — enforced by an endpoint
allowlist that raises before a request is built, not by an intention.

## Previously in Build 2
**The Etsy shop opened, and the reconciliation it produced was not the one it looked like
(#279, #282, #216, #59, #62, executor).**

BrambleloopStudio exists as of 2026-09-19: empty, zero sales, staying that way while Shadow
Mode holds. The owner asked for anything blocked only by the shop's existence to be unparked
automatically. **Nothing qualified, and saying so is the finding.**

The four requirements parked on `etsy_shop` — Marketplace Insights, the query budgeter, the
portfolio allocator, targeted offers — were never blocked by the shop existing. They are
blocked by *automated access* to it, which is the developer credential still pending.
Unparking them on this good news would have put work in the ready queue that nothing can
start: the exact failure the executor exists to prevent, arriving as a reward. So they moved
to a new `etsy_api` gate, `etsy_shop` stays satisfied and carrying nothing — a gate that has
opened is evidence — and the ready count did not move. `ETSY_SHOP_NAME` is set Railway-side.

Then the owner's first priority, which is product quality rather than product count.

- **#279 and #282 — the seasonal transformation engine.** Every transformation is routed
  before it is costed. Palette, styling, gift context and collection story change what a
  buyer sees and nothing a maker makes: a photograph, not a pattern. Motif vocabulary, trim
  and a companion accessory change the object, so they take a CIR, a compile and a physical
  test — and therefore have to be worth them. **An engineered variant carrying no emotional
  promise is refused by name**, because that is the creative jury's dominant failure arriving
  through the seasonal door, and a seasonal palette does not fix it.
- **The test that answers the standard.** The throw the jury rejects for emotional appeal —
  an everyday thing for oneself that feels cosy, the default answer to every crochet brief —
  goes through the engine and comes out clearing every mechanical critic. The child still
  faces the jury on its own; the engine's job is to produce something that survives the gate,
  never to be trusted instead of it.
- **#282's worked example is a function, not a paragraph.** The striped cardigan in three
  seasonal palettes returns `catalogue_growth: 1`, not 4.
- **#216 — the breakthrough lane.** Eight divergence axes, and the label that makes them
  honest: "what the competitor has not made" requires having looked, so with nothing observed
  the divergence runs against our own catalogue and every brief says so. A brief calling that
  a market gap is refused. Both lanes are held open by a floor, because incremental work has
  a visible customer and breakthrough work has an argument, and the argument loses every
  planning round unless something stops it.
- **#59 and #62 — measuring the pixels.** Build 1 shipped a hero that was entirely truthful
  and entirely invisible, and everything upstream reported success. Layout QA now measures
  the rendered frame: flat frames, badge-band content, the square crop the mobile grid
  applies, type too short to be type, and the one that matters most — ink at listing scale
  and none at 170px, which is an image nobody will ever click. The hero is held to it inside
  `check_frame_plan`, not beside it.

One defect found in my own checker while writing its tests: inferring the background from the
corners inverted on a full-bleed frame — the subject reached the corners, became the
background by definition, and a frame that was 97% one block of colour was reported as 96%
empty. Fixed by measuring the dominant colour over the whole image, and both the failure and
the fix are in the tests.

## Previously in Build 2
**The seasonal machine, built out around the Christmas instruction (#289, #287, #291, #292,
#2).**

Five requirements that all answer the same question from different sides: given an occasion
and a finite company, what gets built, by whom, how fast, and out of what already exists.

- **#289, collections.** Coherence and originality as opposing constraints. Members carry the
  palette and story a buyer recognises across a grid, and they must differ structurally —
  measured by the concept engine's own `distance()`, which scores a pure recolour at zero
  because palette is not a term in it. So a derivative is refused by exactly the arithmetic
  that refuses a duplicate in a tournament field: one mechanism, two places, no second
  definition of "the same idea" to drift. The *closest* pair is reported, never the mean.
- **#287, strike teams.** A team is a share of capacity or it is a name. Christmas, Halloween
  and Easter stand; a fourth event brings counted rows rather than enthusiasm. A quarter of
  capacity is reserved for evergreen work, because a seasonal programme that consumes
  everything leaves a shop excellent in December and absent in February. A team whose occasion
  has passed releases what it held without anybody remembering.
- **#291, the fast lane.** Every fast lane begins as a queue-jump and ends as an exemption,
  one defensible deadline at a time. So the gate list is the release chain's own, *imported
  rather than retyped* — a second copy is how the guarantee quietly stops being true — and a
  test reads `certificate.py` and asserts the constant matches the stages the chain actually
  appends. What the lane buys is scope: one component, three colours, no technique the
  catalogue has never used, because a new technique needs a sample and a sample is the one
  part of this company nobody can hurry.
- **#292, re-merchandising.** A recolour presented as a launch inflates catalogue size,
  release rate and collection breadth at once, so no move here increments the catalogue, and
  any move touching construction, rows, gauge or the release hash is refused as the new
  product it is. "Proven" is a claim about sales this company has none of: candidates are
  *eligible*, on every row.
- **#2, micro-market scoring.** An unmeasured dimension leaves the arithmetic and is named.
  Filling it with a neutral value keeps the number's shape and loses its meaning, and nobody
  can tell by looking. Markets scored at confidences more than fifteen points apart are
  refused a ranking outright, because a caveat is read once and a ranking is read every week.

## Previously in Build 2
**Christmas is attacked with faster products as the slow ones close, and the model provider
became real (#6, #293, #177, #178, model access).**

The owner's second correction: the make-time interval work must not read as permission to
deprioritise Christmas. A 150-hour flagship genuinely cannot be finished for this one.
"Christmas is closed" is a different sentence, and the difference is most of the commercial
year. It is now encoded rather than remembered.

- **The engine may retire a product class and may never stand down an occasion.** Two
  refusals enforce it: a priority programme with open lanes cannot fall below its capacity
  floor, and one that names no department to pursue is treating the occasion as a single
  product class.
- **The mix shifts by arithmetic.** Each lane's share is its runway verdict weighted by how
  soon it closes, so a comfortable lane with months of runway ranks below a tight one shutting
  in a fortnight — the tight one is the opportunity about to be lost. MEDIUM leads at 150
  days, SHORT at 120, QUICK from 75, QUICK alone at 45. Nobody decides that.
- **Christmas is a taxonomy.** Departments come from the calendar's own event map filtered by
  open lanes: ornaments, stockings, home decor, bags, hats, seasonal gift. Blankets drop out
  by themselves at 60 days.
- **A closed launch lane is not a closed occasion.** When nothing new can be launched and
  indexed in time the programme moves to merchandising and holds its floor through the
  fortnight the occasion earns the money, releasing only past the buyer's last practical make
  date. Next year's flagship track runs now and is capped below this year's share.

**The model provider is verified, not configured.** The owner supplied a key; the first call
it made returned `Your credit balance is too low to access the Anthropic API`. The gate was
changed to read a recorded successful call rather than an environment variable — a
variable-check would have un-parked four requirements onto work that cannot run. Credit
arrived, and at **2026-09-19T15:31Z a real call succeeded in production** (14 tokens in, 4
out, CA$0.0000466 against a CA$25 ceiling enforced before the request). The gate opened by
itself and #94, #104, #177 and #178 un-parked with nobody telling it to, which is the
property the executor was built for, observed rather than asserted.

Two of those were then built:

- **#178, risk tiers.** A change is graded by what it touches, never by what it is called —
  the description is the part somebody chooses. Five tiers, each with a cooldown (six changes
  to one surface in an afternoon cannot be attributed to any of them), a rolling weekly
  ceiling (continuous learning with no ceiling is a company rewriting itself faster than it
  can observe the result) and the evidence its failure mode needs. An unknown surface grades
  *upward*. The gate tier never promotes without a person. Enforced in `cells.promote()`, not
  offered.
- **#177, capability profiles.** Assembled from the rows rather than stored beside them, and
  reviewed deterministically: a run of three measurements the wrong way, a metric never
  measured, a stale baseline, a tactic rejected twice for the same reason, a lesson nobody
  acted on. A model can write a plausible hypothesis about anything, and a cell proposing
  fluently every week looks exactly like a cell that is learning. A clean record proposes
  nothing. Nothing here promotes.
- **#293, buyer language.** Six facets, and a refusal for the two ways the map becomes a
  description of ourselves. Every phrase is labelled assumed or observed and the two are never
  blended into one ranked list.

One measurement defect, found while checking a number rather than reported by it:
`run_tests.sh` counted only pass lines beginning `OK` at column zero, so nine suites written
this session contributed **zero** to the headline total. Exit codes still caught their
failures, so nothing was broken and the number was quietly wrong — the harder fault to
notice. Markers standardised, and a suite that exits clean while reporting no passes now
counts as a failure.

## Previously in Build 2
**An Anthropic key arrived, and the gate it opens is not the gate it looks like
(model access, #17, #18).**

The owner supplied an API key on 2026-09-19. The first request it made returned, verbatim:
*"Your credit balance is too low to access the Anthropic API."* The key authenticates; the
account cannot serve a request. Both halves of that are recorded because both matter.

- **The model gate now reads a call, not a variable.** It used to check whether
  `ANTHROPIC_API_KEY` was set, which would have reported the provider available and
  un-parked #94, #104, #177 and #178 onto work that cannot run — the queue advertising work
  nobody can start, which is exactly what the build executor was written to prevent, arriving
  through the one door nobody was watching. `gateway/anthropic.probe()` makes the smallest
  call the API accepts on the cheapest model and records the outcome in the provider's own
  words. A six-hourly cadence runs it, so when credits arrive the gate opens by itself.
- **The CA$25/month ceiling is enforced in front of the call.** Spend counted from ledger
  rows; the estimate assumes the model writes its whole output allowance and is padded 1.25×
  on top; an unpriced model is refused as an unbounded call; configuration can lower the
  ceiling and never raise it. Prices are the provider's published list at an assumed exchange
  rate, so every row carries `price_basis: assumed`.
- **The key is in Railway and nowhere else** — not in the repository, not here, not in any
  log or audit row. A repository-wide search for the prefix returns nothing.
- **One owner action was added**, below. It is the only thing in this batch that needs a
  human, and the rest of Build 2 is unaffected by it.

Then down the queue:

- **#3, the selection tournament.** The shape is the requirement — 75-100 concepts to 5-10
  releases — and it is the part that disappears. Four refusals keep it a funnel: survivors
  plus killed equals entrants, a stage that killed nothing did not happen, a kill cause
  outside the vocabulary aggregates to nothing, and a stage fed below its floor is choosing
  among whatever happened to be there. `may_engineer()` refuses a concept the tournament has
  not carried to prototype, which is the requirement's opening sentence made mechanical.
- **#98, the external learning radar.** The radar is unremarkable; the second clause is the
  requirement. Observations carry `kind=external_signal`, `as_evidence()` exists so it can
  refuse by name, and `support()` refuses a signal passed in the evidence list — because the
  step where "textured stitches are trending" becomes something the company knows is a
  sentence nobody notices writing. Nothing fetches these yet and every domain reports
  unobserved, which is different from quiet.
- **#131, seasonal storefront takeovers.** Surfaces transition on different dates read off
  the collection calendar, every takeover carries the revert date scheduled with its start —
  the failure is the Christmas banner still up in February — and six brand invariants are
  refused rather than flagged.
- **#17 and #18.** The trust accelerator is a sequence where unmeasured is never passed and
  proof is counted from rows, with `record_proof()` refusing anything free-standing: the rule
  against manufactured reviews in mechanical form. Support takes the *minimum* of its
  canonical and escalated service levels, because one average lets a fast automated majority
  bury the slow escalated minority where the unhappy buyers are. Whether fast support reduces
  refunds is reported unmeasurable — there are no orders — rather than assumed.

## Previously in Build 2
**What an improvement returned, whether an idea seeds a family, and two requirements that
were pretending to be executable (#99, #101, #111, #112, #288, #51, #39).**

Six requirements, and the thread running through them is the second half: the half that gets
skipped because the first half feels like the work.

- **#99 knew what every improvement cost and nothing about what any returned.** Realised
  benefit is now read against the baseline captured at proposal time, and deliberately *not*
  against the sandbox result that won the promotion — that number was taken under the
  conditions chosen to show the change working, and reading it as the return would make every
  promotion succeed by construction. A promotion younger than the window is `too_early`; an
  older one with nothing measured since is a cost with no return, which is a real outcome
  rather than a broken system.
- **#101 counted lessons acted on; the direction it is named after is the other one.** A new
  design now records which accumulated lessons it drew on. Drawing on nothing is recorded,
  not forbidden — the first product in a new territory legitimately has nothing to stand on —
  and a catalogue of them reports restarting from generic intelligence by name.
- **#111 asks whether an idea seeds a family before engineering, because afterwards the
  answer is always yes.** Five roles, a construction→size-band range for whether the visual
  idea still reads, and a construction→form map for whether it can be built that way at all.
  Both are needed: size compatibility alone would pair an amigurumi robin with a scarf, which
  is the forced derivative the requirement names arrived at from the other side. A mosaic
  throw gets no quick companion — its motif on a coaster is four stitches nobody can see — so
  it is reported as a family with no entry price rather than as a collection.
- **#112 puts make-time into creative scoring, where the owner's correction belongs.** Graded
  against the interval, so infeasible means the optimistic bound has passed and everything
  short of it is an instruction to hurry. Wired in rather than offered: the jury gained a
  `shopping_window` critic that rejects what the buyer cannot finish and judges *nothing*
  when nobody said how long is left, because an unknown window is not a comfortable one.
- **#288's gap report now produces work.** Each uncovered department becomes a brief with the
  forms that serve it, the lane each implies, the last optimistic launch date and the family
  role it would fill — and a department past its window is next season's gap, not this
  season's. A brief is not a product: nothing in the module counts as coverage, and a test
  holds that line.
- **#51 was proving a restore every night of a file that no longer existed an hour later.**
  The export landed on ephemeral container storage. A proved export is now retained in the
  database — three generations, gzipped, hashed, refused on read if the bytes do not match —
  and exports exclude the archive table so a backup does not carry the previous backups. It
  survives a container replacement, a redeploy and a crash. It does not survive losing the
  provider, which is the failure #51 actually names, so that half is parked on a new
  `offsite_storage` gate rather than claimed.
- **#39's retrieval half is blocked from outside, established rather than assumed.** A plain
  HTTPS GET of Etsy's seller-policy page returns 403 from their bot protection while
  `robots.txt` fetches fine, so it is the edge refusing an automated client. Spoofing a
  browser user-agent past it is evasion and was not done.

One defect in the executor, and it was its own kind: `sync()` skipped past an existing task
when its requirement stopped being schedulable, so requirements re-audited as gated kept
reporting themselves ready — the queue advertising work nobody can start, which is precisely
what the module was written to prevent. Stale rows are retired, the reverse transition brings
them back, and both directions have a regression test.

## Previously in Build 2
**Make-time became a distribution, and the claim it had produced was withdrawn (#283, #284,
#36, #41, #42, #38, #50).**

The owner's correction landed on a real defect, and one this build makes nowhere else. The
lead-time chain is exact arithmetic over guesses — seven crochet hours a week, an assumed skill
multiplier, no Brambleloop maker ever timed — and its single date was reported first as a fact
and then as an impossibility covering a whole season. Unmeasured is not zero and absent is not
inferred; a point estimate is not a proof of impossibility either.

- **The interval is asymmetric and only samples narrow it.** Craft overruns: a project going
  well finishes a little early, one going badly finishes very late. A symmetric band would be
  a third wrong claim dressed as rigour. More planning does not narrow it — timing somebody
  does — and even fully calibrated it stays an interval, because two makers differ.
- **Infeasible now requires the optimistic bound to have passed.** Christmas 2026 at 97 days:
  QUICK/SHORT comfortable, MEDIUM tight, **LONG high risk** (needs 95 days optimistically,
  has 97), FLAGSHIP genuinely infeasible (needs 134, short by 37). So the correction is a
  distinction rather than an excuse — one window really has shut and one has not.

Then down the queue, which named the rest:

- **A tester's photograph without recorded consent is refused (#36)** — the same act as using
  a competitor's, arriving from the friendly direction, which is exactly why it gets a
  mechanical check rather than good intentions. A physical photograph records its yarn,
  because a buyer choosing a substitute is choosing against that picture.
- **The digital-not-finished disclosure belongs in the title (#41).** A buyer who thinks they
  are purchasing a blanket does not read the description, and that refund is the most
  preventable one in the category. Confusion contacts are a listing defect, not a cost of
  doing business — counting them as a cost budgets for them.
- **The order-to-version map is written at sale time (#42),** because it cannot be
  reconstructed: once the listing moves on, nobody knows who holds what. The one requirement
  here impossible to retrofit, so it exists before the first order does.
- **A trend datum with no population or window is refused; a foreign one is discounted (#38).**
  Those are different answers to different problems. The discount is baked into the value the
  consumer sees, because a caveat beside a figure is read once and the figure travels alone.
  Staleness is measured against the topic's own seasonality — last January's Christmas figure
  is one cycle old; last January's meme is archaeology.
- **Dependency impact is graded by what stops, not by vendor (#50).** Postgres holds the
  company's memory; GitHub holds a copy of code that is also on disk. A dependency with no
  recovery strategy is refused at construction, because a hand-written map marks three things
  critical and those are the three somebody was already worried about.

One modelling fix in the executor: **executable and ready are two numbers, not one.** The old
invariant held only while every gated requirement was also `owner_gated`, and broke the moment
a requirement was half-built with its remainder behind a credential — the ordinary case. #303
and #304 are now correctly parked while still counted as owed.

## Previously in Build 2
**Heartbeat 2026-09-19T08:14Z — the mission's capacity, its map and its memory (#302, #303,
#316).**

The operator loop ran as designed: lease acquired, production `/api/verify` green, and then
the build queue — not a judgement call — named the top three ready requirements. All three
fail in a way that leaves the org chart intact.

- **The capacity floor is reserved, not allocated (#302).** Capacity merely allocated to a
  mission gets borrowed, and the borrowing decision is locally sensible *every single time*:
  generic research is busy now, the specialists are idle now, moving them is obviously right.
  It is obviously right often enough that the mission ends up with specialists on paper and no
  throughput, and nobody ever decided to defund it. The refusal names the five kinds of work it
  would starve. Above the floor the ceiling is money rather than headcount, and a fan-out must
  name which of coverage, quality or latency it is buying — "we could use more" is what an
  elastic system asks for by default.
- **The map records judgement columns as absent with the capability named (#303).** Silhouette,
  merchandising mechanism and styling are judgements about a photograph; inferring them from a
  title would make every row look complete and be fiction — *persuasive* fiction, because seven
  of ten columns would be right. Completeness is scored against what the available capabilities
  can observe, or a correctly limited map reports itself permanently broken. Palette is a third
  case and is distinguished: Etsy publishes it per image, so its absence is **a request nobody
  made**, not a capability nobody has.
- **A map that does not know how stale it is is not living.** Every row carries its evidence
  date; the map reports its oldest. A catalogue map nobody refreshed is indistinguishable from
  a current one right up to the moment it is wrong — which is exactly when the shop changed
  something, and exactly when somebody is reading it.
- **Only an outcome moves the learning memory (#316).** The failure every learning system has
  is confidence that grows with repetition: forty observations of one shop's Christmas listings
  is one observation made forty times. "Observed again" is refused **by name**, with the reason
  attached. A challenger wins on outcomes or not at all, a tie leaves the incumbent standing —
  promoting on equal evidence is promoting on novelty — and superseded lessons are kept,
  because a memory that has only ever been right is not learning.

One refactor fell out: the pods' competitor-expression boundary lived inline inside
`lesson()`, and the learning memory needed the same rule. It is now called rather than copied
— a boundary that exists twice drifts, and the copy that drifts is always the newer one.

#303 stays **partial**: full discoverable catalogue coverage needs the Etsy credential. The map
is built and waiting.

## Previously in Build 2
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

### Then it continued, from the requirement the queue named

The loop's first job was to say what to do next, and it said **#302's cluster** — the
MJs-proven-arena response (#306, #307, #308, #309). Built immediately, because it is what
makes tomorrow's credential productive: the pipeline is what waits for observations, not the
other way round.

- **A third content boundary, drawn in a different place (#306).** The teardown library
  refuses a competitor's instructions and the culture router refuses their property. This one
  has to *permit* "cropped V-neck button cardigan" while refusing "their stripe sequence" —
  because a rule that forbade entering a proven arena would make the intelligence mission
  conclude that the useful answer is never to act on what it found, which is the most
  expensive possible conclusion for the company's stated top priority.
- **"MUST consider" is satisfied by a recorded refusal and never by silence,** and entering
  requires a differentiator — #163's anti-parity rule arriving through the competitive door.
- **Seasonalising enumerates eight lenses (#307),** and a palette-only answer is reported as
  the recolour it is: exactly the output this build measured as its creativity defect.
- **Fourteen pipeline stages, each naming its gate (#309).** A long pipeline never fails by
  collapsing; it fails by one stage quietly becoming optional, and a failed gate stops the run
  rather than marking it amber.
- **The owner's Christmas cardigan example (#308) is a test fixture** over #306 and #307
  rather than a special case in the code.

### Three defects this surfaced

**Four requirements the registry called executable cannot be built without a credential**
(#177, #178, #221, #222). The gate validator refused them as ungated, which is exactly what it
is for. Registry reconciled; ready count and executable count now agree by construction, with
a test asserting it.

**The watchdog could not see the commonest kind of progress.** Registry-driven completions
— a session finishes work and moves the status — were recorded only as a sync event, so the
loop reported *stalled* while six requirements had just closed. A false alarm in the channel
that exists to catch a real one is worse than no channel. Fixing it naively then made the
first sync count the whole 140-requirement backlog as completions, so a table created ten
seconds ago reported a busy loop: a completion is a transition this system **observed**, not a
status it found on first sight.

**The off-device proof counted a different set than its verdict tested.** Run against
production it reported sixteen dead letters where the condition meant one: shadow-mode publish
refusals are the gate working and were excluded from the test but not from the number printed
beside it. Same class of defect as an unmeasured rate reported as zero, in the one report whose
whole job is to be believed.

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

| lane | up to | days needed (optimistic / typical / pessimistic) | verdict at 97 days |
|---|---:|---|---|
| QUICK | 6h | 37 / 40 / 47 | comfortable |
| SHORT | 20h | 47 / 56 / 80 | comfortable |
| MEDIUM | 45h | 63 / 83 / 137 | tight |
| LONG | 90h | 95 / 135 / 243 | **high risk** |
| FLAGSHIP | 150h | 134 / 202 / 382 | **infeasible** |

The spread is wide because nothing has been calibrated: zero completed physical tests. Every
recorded sample narrows it, and nothing else does — more planning does not narrow an interval,
timing somebody does.

**Corrected 2026-09-19: "arithmetically impossible" was wrong, and wrong in the way this
build refuses everywhere else.** The arithmetic is exact; its inputs are guesses — an assumed
seven crochet hours a week, an assumed skill multiplier, and no Brambleloop maker ever timed.
Make-time is now an interval (`seasonal/uncertainty.py`), and *infeasible* requires the
**optimistic** bound to have passed. Against that, Christmas 2026 at 97 days reads:
QUICK and SHORT **comfortable**, MEDIUM **tight**, LONG **high risk** (needs 95 days
optimistically, has 97), FLAGSHIP genuinely **infeasible** (needs 134, short by 37).

So LONG Christmas work is attemptable and carries real risk, rather than being impossible.
Thanksgiving (CA) is gone. **Flagship effort
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
- 2026-09-20T08:19Z heartbeat: lease taken, production `/api/verify` verified 12 of 12
  against live state, and the commercial spine landed -- #5 production lanes, #9/#21 creator
  roster, #10 free-to-paid funnel, #13 offer engineering, #14 conversion baselines, #16
  listing-test memory, #22 bestseller replication and #30 capacity allocation, the last of
  which is now a weekly `capacity_review` cadence. Registry 177 of 320 covered, 87
  executable. One gate added (`owned_surfaces`) and #4/#10 re-parked onto it. Then #26's
  trajectory model and #171/#173's artefact provenance and stale-artefact sentinel: 179 of
  320 covered, 85 executable. Then #183/#185's console and health sweep (1,817 tests
  passing on `0782969`, deployed and live: production console reports `healthy`, 0 pending,
  134 dead letters all of which are deliberate shadow-mode refusals) and #188's spend
  governor: 182 of 320 covered, 82 executable. Decisions B-345..B-373.
- 2026-09-20 continued: #172's rebuild graph (`9e4dcfb`, suite green at 2,005 across 119
  suites, zero leftover directories), then #260/#261 — the first-100 interview instrument and
  the purchase-friction audit. Both land `partial` and parked, #260 on `customers` and #261
  on `live_listings`, and both name the same blind spot: the interview reaches only survivors
  of the purchase decision, and the people who left are the ones whose friction costs most.
  #261's listing half runs today against the listing artefact and the shop's own generated
  copy is asserted to pass it. Then #262's forecast calibration, which caps
  `scale.confidence` rather than computing a second probability and excludes every period
  today as unexposed, and #267's capacity roll-forward, which holds engineering and marketing
  as separate ledgers because the occasion stops being launchable weeks before it stops being
  buyable. Then #179's meta-agent roster (`partial`: defined and enforced, not yet running
  agents) and #180's league hardening -- latency as a fourth axis, a holdout never tuned
  against, a promotion bar that scales with how much was measured, and a recorded rollback
  target. Suite green at 2,144 across 125 suites on `7855fef`, zero leftover directories.
  Then the autonomy block: #191's per-department freshness SLAs (green at 2,168), and
  #190/#193/#194 -- the upgrade pipeline, the nightly window and the weekly deep cycle, with
  both new cadences wired and exercised by the platform suite that runs every cadence for
  real (green at 2,242 across 129 suites on `4725036`). Then #179 closed: the eight
  meta-agents became running agents with their own authority, ceilings and cadences, all
  generated from the roster so the three lists cannot drift (green at 2,249). Then the
  culture cluster: a `culture_feed` gate parks #133/#140/#147, which had been reporting
  themselves as ready while their own notes said no feed exists, and #146's owned-IP roster
  lands with recurrence that cannot be declared (green at 2,279). Then #57/#58/#65/#69: asset
  purpose as a second axis orthogonal to medium, one commercial job per frame checked for
  collision rather than similarity, four gates where not_run is not passed, and an honesty
  label that is never a licence (green at 2,308). Then #60/#68/#70: measurements traced to
  the geometry object with the two-numbers-disagreeing check, visual defects given the
  fixtures compiler defects already had, and a listing certificate invalidated by its inputs
  rather than by being revoked. #61 and #64 parked on browser_vision and a new physical_proof
  gate; ready fell from 29 to 19 (green at 2,359). Then #63/#66: creative constrained to a
  subset of truth in one direction, the flow ordered so a brief cannot be a caption, and the
  listing evaluated where it is chosen rather than where it was built. #168 and #79 parked;
  ready is 15 against 87 (green at 2,395). Then #33's seasonal engine: priority from a score
  with no favourites, an evergreen floor taken before anything is granted, squads that stand
  down by arithmetic, and a breakout that cannot reach a gate (green at 2,433). Then the
  migration itself: all five call sites off the constant and onto a labelled accessor, with
  the owner's campaign surviving as a seed that cannot be read as a measurement. Plus a test
  that fails when a note describes a blocker and the requirement is not parked. Registry 201
  of 320 covered, 63 executable. Decisions B-404..B-463.
- 2026-09-20T16:14Z heartbeat: lease acquired, production verified 12 of 12 on `/api/verify`,
  and the live deployment is `aff020260a72` -- Railway had already auto-deployed the #33
  migration pushed minutes earlier. Console reports `healthy`, 0 pending, 134 dead letters
  (all deliberate shadow-mode publication refusals, per B-374). **The eight meta-agents of
  #179 are seeded in production**: `cost_optimiser`, `creative_critic`, `evaluator`,
  `experiment_designer`, `failure_miner`, `lesson_router`, `prompt_tool_challenger` and
  `reliability_engineer` all exist as Agent rows with their own authority and ceilings, which
  is the verification that matters -- a roster in a module is a definition and an Agent row is
  a thing the queue will dispatch to. All five new endpoints answer 200. The three new
  cadences (`improve.nightly`, `improve.weekly`, `improve.role_work`) have not fired yet and
  are not expected to: they are daily and weekly, the container started at 16:14, and the
  recent window holds only the 15-minute and hourly ones. Saying they are deployed is true;
  saying they have run would not be.
- 2026-09-20 intel block, closing the MJs benchmark cluster. #215/#219/#220/#227/#228: a
  panel that is never one shop (MJs named once, in one constant; three members minimum;
  membership read per category), a standard a competitor may raise and never lower, entry
  refused on parity alone, and an owner veto recorded in a closed vocabulary whose third
  repetition is a finding about the evaluator rather than about the product. The veto retires
  only on predictions the evaluator made *before* the owner ruled -- a prediction dated at or
  after the ruling is refused by the constructor, because the owner's rulings are the easiest
  training data to hand. Then #226: a pod's capability is two numbers and no function returns
  one alone, discernment is precision against settled outcomes and explicitly not rejection
  rate, and pods stay out of `improve.cells.CELLS` so that one vocabulary does not come to
  mean two things. Then #214: a mechanism is how a listing works on a buyer, never what the
  product depicts -- depiction words refused at construction, containment reusing
  `culture.rights` rather than a second copy of it, and a tournament requiring two mechanisms
  this shop lacks *and* our own demand evidence, because a pipeline that answers every
  competitor listing is handing them the roadmap. #207-#211 parked on `browser_vision`:
  #221 mandates vision for the observation layer, so they are not code that could be written
  now and switched on later. Registry 208 of 320 covered, 56 executable, **0 READY** --
  nothing is `missing`, and every one of the 94 parked requirements names a gate that opens
  from demonstrated capability. Decisions B-464..B-476.
- The empty backlog then broke the executor's own tests, nine at once, and none of them
  because the thing it tested had broken: they read `next_ready()` off the live registry to
  get something to claim, and one asserted `ready > 0` directly beside a comment explaining
  that same mistake in its previous costume. Ready work is now produced the way it will
  actually be produced from now on -- by a gate's condition becoming true -- and both idle
  states are asserted through the deployed worker: parked-and-silent raises nothing,
  gate-open-and-silent raises exactly one incident across two ticks. B-477.
- 2026-09-20 owner-approved gate preparations, and two corrections to what was reported
  earlier the same day. The queue count of 0 READY was taken in a credential-free session
  container; production had one ready requirement, #268, because `benchmark_observation` is
  open there. Where a gate count was taken is part of the count (B-481). And #268 turned out
  to be parked on a gate that was already open -- the Etsy credential it names has been
  proven by use since 2026-09-19 and read the 438 listings the whole mission runs on. What
  it waits on is a second market to compare against, which is a choice of shop and not a
  credential, so `second_market_benchmark` now names it and `commerce.markets` computes the
  attribution from the benchmark's registered market instead of returning `US` for whatever
  key it was handed (B-482).
- The larger finding: **`browser_vision` was two capabilities under one name**, and the
  cheaper one had been paid for since 2026-09-19. Ten of its twenty-eight requirements
  needed no browser -- the sanctioned `listing_images` endpoint returns every gallery image's
  URL and the model that can look at them was already credentialed. Nobody had written the
  call. It is written (`gateway.anthropic.see`, `intel.vision.analyse`: one image per call,
  closed answer vocabulary parsed strictly, the depicted subject refused by the system
  prompt, every failure counted and named), and the gate is split into `image_vision` and
  `rendered_pages` (B-478). Five notes that justified parking turned out to be a day out of
  date, having been written before the capability arrived and survived it -- #207 is closed
  on that basis, having actually run (B-480).
- **No gate in the executor's table opens on a typed string any more.** Three did, holding
  thirty-nine requirements behind conditions a person could satisfy by typing: a browser URL,
  an image key, an archive URL. Each is now a recorded successful use, and the test is stated
  over every gate that holds requirements rather than over those three (B-479).
- Owner-approved preparations delivered: the **culture feed is connected** (Wikimedia
  pageviews -- free, keyless, sanctioned, labelled `reference` reading rather than search
  interest, because #140 measures the gap between the two); the **image-generation provider
  decision is worked out** with three priced candidates, reference conditioning as the
  deciding property and an estimate of CA$3.40 in the first month, with vision substitution
  refused in code rather than discouraged in a note (B-484); the **benchmark purchase
  selector** chooses for facet coverage rather than popularity and stops short of ten rather
  than filling the list (B-485); and the `physical_proof` gate no longer names whose hands
  do the work (B-486). Decisions B-478..B-486.
- 2026-09-20, owner's quality-first decision. The instruction is that quality decides and a
  modestly dearer model that materially outperforms is worth paying for, and the first thing
  it cost was a recommendation already sitting in the code: FLUX 2 Pro, chosen because it was
  the cheapest candidate that supports reference conditioning. That is deleted rather than
  defended -- a named winner beside an unrun benchmark is the price list deciding again with
  a second opinion for cover (B-502). `gateway/image_bench.py` replaces it: six trials this
  catalogue genuinely needs rendered, five samples each, four eligible models, 120 images at
  **CA$6.19** of the CA$25 the owner authorised, judged blind by the vision capability
  against a rubric whose every line cites its requirement (B-505). Imagen 4 Ultra leaves
  *before* the benchmark on a requirement rather than a score: the best published
  photorealism in the field and no reference conditioning, so the canonical model cannot be
  held across seasons by it at any quality (B-503). Five samples rather than three because
  one render is a sample of a distribution and this choice governs every listing image the
  company ships; five rather than as many as the ceiling allows, because budget is not a
  reason (B-504). With no results it names nobody, and a model below the fabric floor is out
  at any price -- both refusals guarding the same failure, a measurement quietly becoming a
  price comparison (B-506).
- The benchmark purchase list now answers the question a person about to spend CA$268
  actually asks. Each pick carries the runner-up it beat, what that alternative would have
  taught instead and the extra the winner adds; the set carries how many of the 438 observed
  listings it makes redundant, measured over the finished set rather than per pick -- the
  per-pick count reads zero in a catalogue of near-duplicates right up until the duplicate is
  bought (B-507).
- #268 recorded `data_gated` on the owner's instruction, with the proven sanctioned Etsy
  capability as the applicable evidence and nothing further owed by the owner. Its
  `parked_on` came off with it: that field states what *remaining* work needs, and the
  executor refuses one on a requirement that is not executable -- which it did, loudly, the
  moment the status changed. The gate stays defined and carries nothing, as the condition
  that would make it executable again (B-508). Decisions B-502..B-508.
- 2026-09-20, the governing spend policy. The owner raised the combined model ceiling from
  CA$25 to CA$100 and reversed the argument with it: **QUALITY FIRST, COST SECOND, WASTE
  NEVER**. The build had followed "start economically" faithfully and the faithfulness had
  become the problem -- decisions had accumulated whose stated justification was the ceiling
  rather than the work, each defensible, together a company optimising for cheapness
  (B-513).
- Reconciling it found three things that had drifted while nobody was arguing about them.
  The ceiling was written in two modules *and* hardcoded into a `/api/verify` assertion, so
  carrying out the owner's decision would have turned a safety check red -- the exact shape
  of check that file's own comment warns against, three lines above, added by the session
  that wrote the warning (B-514). Four vision call sites never consulted `routing.TASKS` at
  all: `intel.vision` built its provider from `VISION_PROBE_MODEL` -- the *probe's* model,
  chosen because a probe should be the smallest possible real call -- so MJs gallery
  analysis ran on the cheapest tier while the table declared standard, on the owner's
  second-highest spending priority (B-515). And two cadence intervals were set by the old
  ceiling rather than by the work (B-516).
- Fixed with one ceiling, `provider_for(task)`, three new declared tasks, and two tests
  stated over the whole codebase: every vision call site names a task in the routing table,
  and no module outside the gateway names a model string at all. Gallery analysis is now 25
  images every two hours on the standard tier -- the benchmark's visual evidence closes in
  four days rather than nineteen -- and it is self-limiting, because a rate that stayed high
  against an empty queue would be the waste clause rather than the quality one. The blinded
  creative benchmark went monthly to fortnightly rather than weekly, and the reason is the
  measurement: the thing it tracks does not move in seven days, so it stops where more
  frequency would stop adding information rather than where it would start costing money.
- Spend accounting: provider, model, agent, department, product and purpose are columns
  rather than JSON keys, with the pre-call reservation beside the bill and under-estimation
  flagged specifically, because that is the direction where a ceiling is checked against a
  number smaller than the invoice (B-517). The report covers the calendar month rather than
  "the month so far" -- its upper bound was `now`, which silently dropped rows timestamped a
  few seconds ahead of the reader's clock (B-518).
- The image benchmark now scores twelve judged dimensions, asks gallery consistency once per
  set, and measures repeatability and latency from data the run already produces (B-519).
  Inside the deciding margin, repeatability breaks the tie before cost does: both are
  tie-breaks and only one is about quality (B-520). Judging moved to the deep tier, taking
  the benchmark from CA$6.19 to **CA$18.55** of the CA$25 authorised -- the judgement decides
  which provider renders every listing image afterwards, so measuring carefully with a blunt
  instrument was the one economy that could not be defended. Decisions B-513..B-520.
- 2026-09-21, the Teardown Laboratory can read a page. The owner's MJs protocol said not to
  ask for the CA$292 purchase until the complete intake and analysis path was verified ready,
  and the honest answer was no: `library.retrieve` -- the quarantine's only sanctioned reader
  -- was called by nothing at all, so a purchase would have been filed, hashed, manifested and
  never opened. `teardown/reader.py` is that missing module, built so that nothing leaves it
  which this repository did not already contain: closed vocabularies and numbers, no code path
  that emits a substring of the document (B-566). Readiness is now proved by running the whole
  path against a real Brambleloop PDF on every request rather than by a table of ticks, and the
  launch assessment withholds the purchase request entirely while the lab is unready (B-567).
  **The verdict is now READY**; the purchase is the owner's decision, not a blocked build.
- Pointing that reader at this company's own pattern found the first thing it audited: every
  Brambleloop pattern shipped with no finishing section. The document ended at the last row --
  no fastening off, no ends, no blocking -- and now does not (B-568).
- 2026-09-21, the canonical model. The tournament rendered a field, stress-tested five
  finalists and presented them; the owner rejected all five and supplied their own generated
  concept as the candidate. The tournament is now closed rather than re-running, and its
  results stay as evidence that cannot be promoted (B-569). The reference pack built from the
  owner's candidate is two frames -- a neutral portrait for the face and a full-length
  standing frame for the body -- because every finalist had been measured against a cropped
  portrait on which the body was unmeasurable by construction (B-570). Chest/bust and torso
  are required-readable rather than counted (B-571), and the owner's revised bust direction is
  a pinned identity dimension rather than a styling preference (B-572). **Nothing is frozen**:
  the pack is built, measured and presented, and only the owner's approval makes it canonical.
- 2026-09-21 evening, the canonical reference pack is built and **awaiting the owner's
  approval**. Three reference frames (portrait, torso, full-length), five stress scenes, and
  all six approval conditions met: every scene rendered, facial identity held in all five,
  no morphology drift anywhere, chest and torso both evidenced, all thirteen dimensions
  pinned, reference frames coherent. Nothing is frozen -- `select_canonical` with the
  owner's approval is the only thing that can. Five live builds were needed and each found a
  different version of one defect: a reference that cannot state the dimension it is trusted
  for, an approval condition nothing could satisfy, an hour-long idempotency lockout, a
  stale replica answering about a different pack, and a frame whose verdict turned on
  sampling luck (B-573..B-579). Total spend across all five: about CA$2.50.
- 2026-09-21 heartbeat: #292 and #300 un-parked and their imagery halves built. Both were
  gated on `BRAMBLELOOP_IMAGE_KEY`, a variable that stopped existing when credentials moved
  to per-account keys, so a capability proven in production for a day read as absent and the
  check could no longer come true (B-581). `publish/owned_photography.py` makes the missing
  asset: a styled illustration of the finished object, generated from the certified CIR,
  described by a model that never sees the claim, compared deterministically, gated on three
  verdicts, and disclosed as generated everywhere it appears (B-582). It runs as a daily job,
  idempotent per release; the seasonal cycle reports what exists rather than rendering.
  The first live asset rendered, passed every existing check and depicted a
  checkerboard where the pattern makes a diamond lattice: **motif fidelity is not
  yet checkable**, so it is named as a gate rather than waved through, and the
  asset is evidence to look at rather than a listing image (B-585).
  `/api/seasonal/remerchandising` computes its own availability now, rather than
  defaulting to "nothing works" because its caller passed nothing (B-583).
- The test runner now discovers its suites. The hand-maintained list was three files out of
  date, so two mornings' work was green without being run by the full suite -- both passed
  directly, nothing was broken, and the claim was weaker than it sounded (B-580). 155 suites,
  **2,831 tests passing, 0 failing**.
- Totals: 541 tests passing, 0 failing. All six acceptance gates pass, each line with its own
  named test. Gates A, C, D, E, F passing; B passing except
  regression automation.
