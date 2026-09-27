# ADVERSARIAL TEST PLAN

Specifications only: no tests were implemented or executed for this documentation task. Run proposed cases only in an integrator-authorized isolated test checkout with disposable DB/artifact storage. Do not target production, real Etsy writes or paid services. This is test isolation, not a new product gate.

## Common harness and proof rules

1. Exercise the actual scheduler/queue/worker or authenticated route, including registration, grants, phase and capability checks. Library tests remain useful but do not replace this path.
2. Use a file-backed disposable DB for restarts. Fault-inject at named transaction/side-effect boundaries; reopen through normal bootstrap. Test simultaneous claims with synchronization barriers and, when authorized, the production DB engine in a disposable instance.
3. Substitute deterministic adapters only at external I/O boundaries. Keep internal producer, persistence, consumer and guard code real. Never inject the final evidence row in a test claiming producer coverage.
4. Fix clock and input identities. Capture before/after rows, hashes, audit job/attempt IDs, lease tokens, queue priorities, source observation windows and spy-adapter call counts. A refusal requires zero protected calls, not just a returned error string.
5. Every case needs a negative control and an admissible positive control. Re-run after restart/replay where applicable. Retain rejection reasons; do not weaken thresholds or remove failing tests to obtain green.
6. Label synthetic fixtures, recorded source fixtures, assumptions and real execution separately. Do not record a fixture as production evidence. Attach test command, source SHA, environment/schema/config versions and complete exit/result to the eventual test artifact.
7. An expected failure below is a hypothesis until reproduced. If disproved, retain counterevidence and have Opus revise the finding; never alter application behavior to match an incorrect audit.

## Mandatory failure-class coverage

| Required case | Specification |
|---|---|
| Partial refund; full refund arriving later | AT-O01 (separate source revisions and assertions) |
| Cancelled/unpaid receipt | AT-O02 |
| Out-of-order historical receipt | AT-O04 |
| Crash between order/version/ledger writes | AT-O05 |
| Third repeated Growth steering run | AT-G01 |
| Protected priority-band escape | AT-G02 |
| Mismatched targeted rebuild request | AT-G03 |
| Rollback failure/interruption/restart | AT-M01 |
| Stale replay presented as fresh | AT-M03 |
| Policy A→B→B without review; A→B→review | AT-I01 (both branches) |
| Evidence aging out with incident; unreadable visual series | AT-I07 (separate branches) |
| Changed artifact with stale approval; empty visual review set | AT-P06; AT-M07 |
| Simultaneous lane claims | AT-P09 |
| Repeated backoff without new observation | AT-P07 |
| Planning gate closes before execution | AT-G11; AT-X03 |
| Fixture evidence with no production producer | AT-G04; AT-D01; AT-X04 |

<a id="AT-P01"></a>

## AT-P01 — Reopened status is overridden by executor gate membership

Finding: [CB2-P01](FINDINGS.md#cb2-p01); Platform; BEFORE; confirmed_static.

- **Preconditions:** all 20 manifest rows partial with no parked_on, retain Gate tuples
- **Actions / fault injection:** classify with closed/open/unchecked gate maps
- **Required assertions:** executable residue remains OPEN in every case; valid explicitly parked control rows retain their classification.
- **Runtime boundary to observe:** Registry + live gates → classify → matrix → integrator closure decision → all 151 reopened obligations accounted for.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-P02"></a>

## AT-P02 — Module reachability is mistaken for requirement proof

Finding: [CB2-P02](FINDINGS.md#cb2-p02); Platform; BEFORE; confirmed_static.

- **Preconditions:** library with one live read-only helper and one dead protected-action helper; owner/data-gated rows naming missing files
- **Actions / fault injection:** run proof/classification
- **Required assertions:** none earns fulfilled built-half proof; positive control requires the named behavior.
- **Runtime boundary to observe:** Runtime root → exact function → durable output → consuming decision → protected action/refusal → independent observation.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-P03"></a>

## AT-P03 — Unchecked gates can coexist with closed_out

Finding: [CB2-P03](FINDINGS.md#cb2-p03); Platform; BEFORE; confirmed_static.

- **Preconditions:** zero executable OPEN controls plus gated rows
- **Actions / fault injection:** matrix(None), failed gate read, valid live DB
- **Required assertions:** first two cannot yield verified closure; successful read is separately evidenced.
- **Runtime boundary to observe:** DB/gate check → matrix completeness → summary → certification recommendation withheld on uncertainty.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-P04"></a>

## AT-P04 — Unique-value comparison permits unmeasured or unsupported superiority

Finding: [CB2-P04](FINDINGS.md#cb2-p04); Platform; BEFORE; confirmed_static.

- **Preconditions:** granted certificate, absent own comparative scores, benchmark scored low; also no benchmark scores
- **Actions / fault injection:** certify and attempt draft/publish
- **Required assertions:** neither absence nor assumed superiority becomes passed unique-value evidence; measured positive/negative controls differ.
- **Runtime boundary to observe:** Own release evidence + purchased benchmark → comparison → durable withheld reason → draft/rebuild/publish refusal.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-P05"></a>

## AT-P05 — Delight scores are fixed proxies and can use another version

Finding: [CB2-P05](FINDINGS.md#cb2-p05); Platform; BEFORE; confirmed_static.

- **Preconditions:** two versions, only old version has artifacts; certificate-only new version
- **Actions / fault injection:** delight evaluation and follow-on
- **Required assertions:** no inherited quality score; a measured weak driver produces one traceable actionable proposal.
- **Runtime boundary to observe:** Current release artifacts + measured audit → delight finding → improvement proposal → actual changed artifact → reevaluation.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-P06"></a>

## AT-P06 — Frame review can clear unjudged, empty or stale evidence

Finding: [CB2-P06](FINDINGS.md#cb2-p06); Platform; BEFORE; confirmed_static.

- **Preconditions:** expected six frames
- **Actions / fault injection:** submit empty review, five-frame review, unjudged description and changed bytes at same version
- **Required assertions:** no complete clear verdict; explicit non-applicable realism never clears other required checks.
- **Runtime boundary to observe:** Frame bytes → independent claim review → hash-bound evidence → listing-set gate → blocked publication for omissions.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-P07"></a>

## AT-P07 — Polling backoff grows without a new observation

Finding: [CB2-P07](FINDINGS.md#cb2-p07); Platform; BEFORE; confirmed_static.

- **Preconditions:** three identical free polls and one sweep at t0
- **Actions / fault injection:** sweep repeatedly without new jobs through the deadline
- **Required assertions:** factor/deadline stable, next probe becomes eligible; only a newly completed unchanged probe increases backoff; changed result clears it.
- **Runtime boundary to observe:** Completed poll → durable observation cursor → backoff → scheduler → bounded retry → new observation.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-P08"></a>

## AT-P08 — New build SHA stands in for changed failure hypothesis

Finding: [CB2-P08](FINDINGS.md#cb2-p08); Platform; BEFORE; confirmed_static.

- **Preconditions:** paid failure breaker
- **Actions / fault injection:** unrelated build SHA change, then relevant corrected credential/input event
- **Required assertions:** unrelated build cannot repeatedly restart spend; authorized relevant retry is bounded and audited.
- **Runtime boundary to observe:** Failure signature → suspension → relevant change evidence → retry admission → observed outcome.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-P09"></a>

## AT-P09 — Lane enforcement needs atomic concurrent admission

Finding: [CB2-P09](FINDINGS.md#cb2-p09); Platform; BEFORE; risk_requires_reproduction.

- **Preconditions:** two workers synchronized at admission, one lane slot and another runnable lane
- **Actions / fault injection:** simultaneous claims, kill admitted worker, recover lease
- **Required assertions:** at most one lane admission, other lane progresses, slot is reclaimed once.
- **Runtime boundary to observe:** Pending jobs + allocation → atomic claim/reservation → worker execution → durable completion/recovery.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-P10"></a>

## AT-P10 — Rebuild completion is not strictly request-bound

Finding: [CB2-P10](FINDINGS.md#cb2-p10); Platform; BEFORE; risk_requires_reproduction.

- **Preconditions:** stale target A and fresh unrelated B, then repeated A request with same version
- **Actions / fault injection:** verify before/after exact downstream rebuild and restart
- **Required assertions:** B cannot close A; no stale output reuse or duplicate side effects.
- **Runtime boundary to observe:** Invalidation request → exact stage → hash-linked provenance → verification → only requested nodes marked rebuilt.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-P11"></a>

## AT-P11 — Escalation plans do not prove distinct rung execution

Finding: [CB2-P11](FINDINGS.md#cb2-p11); Platform; BEFORE; coverage_gap.

- **Preconditions:** repeated parity failure with image gate open
- **Actions / fault injection:** execute first failure and subsequent rung
- **Required assertions:** effective generation inputs change, results are rejudged, retry ceiling holds and failed parity still blocks.
- **Runtime boundary to observe:** Parity failure → strategy attempt → generated asset → independent review → next rung or release refusal.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-P12"></a>

## AT-P12 — Launch readiness uses weak rollback and baseline proxies

Finding: [CB2-P12](FINDINGS.md#cb2-p12); Platform; BEFORE; confirmed_static.

- **Preconditions:** failed restore audit, unrelated product baseline and old certified version
- **Actions / fault injection:** launch readiness
- **Required assertions:** each remains unmet until the matching successful evidence arrives.
- **Runtime boundary to observe:** Restore/baseline producer → scoped evidence → readiness → launch eligibility.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-P13"></a>

## AT-P13 — Experiment cost attribution is partly a job-type proxy

Finding: [CB2-P13](FINDINGS.md#cb2-p13); Platform; BEFORE; confirmed_static.

- **Preconditions:** two actual experiments of same type plus one untagged job
- **Actions / fault injection:** spend aggregation
- **Required assertions:** distinct real totals and explicit unattributed amount; no invented experiment.
- **Runtime boundary to observe:** Job/experiment linkage + cost → governor → capacity decision with known attribution quality.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-P14"></a>

## AT-P14 — Continuous critical-dependency actions remain absent

Finding: [CB2-P14](FINDINGS.md#cb2-p14); Platform; AFTER; coverage_gap.

- **Preconditions:** AI provider existential and missing recovery strategy, failed DB probe
- **Actions / fault injection:** normal scheduled assessment twice
- **Required assertions:** one durable scoped incident/decision, explicit recovery/export path, no fake successful drill.
- **Runtime boundary to observe:** Dependency/probe evidence → durable assessment → incident/owner queue → recovery readiness decision.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-P15"></a>

## AT-P15 — Validated-products-per-dollar optimization remains absent

Finding: [CB2-P15](FINDINGS.md#cb2-p15); Platform; AFTER; coverage_gap.

- **Preconditions:** same spend with different validated outputs, missing attribution and later refund
- **Actions / fault injection:** scheduled efficiency assessment
- **Required assertions:** true unit cost/unknown coverage and traceable changed allocation; no gross-profit substitution.
- **Runtime boundary to observe:** Job/artifact cost+time → unit-cost evidence → governor → bounded allocation → observed efficiency.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-P16"></a>

## AT-P16 — Recognizability without model remains unevidenced

Finding: [CB2-P16](FINDINGS.md#cb2-p16); Platform; AFTER; coverage_gap.

- **Preconditions:** model-free current listing with/without signature elements and unrelated brand controls
- **Actions / fault injection:** independent benchmarked review
- **Required assertions:** evidence supports only measured recognizability; layout validity alone never passes brand identity.
- **Runtime boundary to observe:** Brand artifacts → inventory provenance → independent model-free evaluation → creative decision.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-P17"></a>

## AT-P17 — Opportunity scorers do not consume evidence freshness/population weighting

Finding: [CB2-P17](FINDINGS.md#cb2-p17); Platform; AFTER; coverage_gap.

- **Preconditions:** equal fresh local, stale historical and US-only evidence for Canadian claim
- **Actions / fault injection:** actual scorer and listing claim path
- **Required assertions:** required discounts/refusal apply, persisted score identifies sources and dates.
- **Runtime boundary to observe:** Source trend/search fact → provenance stamp → weighted scorer → selected work/currentness guard.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-P18"></a>

## AT-P18 — Seasonal takeover has plans but no proven apply/revert executor

Finding: [CB2-P18](FINDINGS.md#cb2-p18); Platform; AFTER; coverage_gap.

- **Preconditions:** due takeover, closed surface authority, later mock-authorized surface and end date
- **Actions / fault injection:** scheduler through restart
- **Required assertions:** no call while closed, one applied transition and one verified restore when authorized; current product truth remains binding.
- **Runtime boundary to observe:** Calendar → durable takeover plan → final surface gate → apply receipt → scheduled restore → verified state.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-O01"></a>

## AT-O01 — Receipt state is not reconciled for late full or partial refunds

Finding: [CB2-O01](FINDINGS.md#cb2-o01); Orders; BEFORE; confirmed_static.

- **Preconditions:** paid two-line CAD receipt 10+20, first ingest; later refund 5 on first line, then remaining 25 after overlap expires
- **Actions / fault injection:** ingest each source revision twice
- **Required assertions:** exact net amounts, no unrelated-line full refund, no duplicate adjustment, downstream totals recomputed to zero net at full refund.
- **Runtime boundary to observe:** Receipt revision → normalized transaction/refund → durable order+ledger reconciliation → cohorts/CAC/loops → corrected growth decisions.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-O02"></a>

## AT-O02 — Unpaid and cancelled receipts can become sales

Finding: [CB2-O02](FINDINGS.md#cb2-o02); Orders; BEFORE; confirmed_static.

- **Preconditions:** unpaid, cancelled-before-payment, paid then cancelled/refunded and missing-state payloads
- **Actions / fault injection:** normal ingest
- **Required assertions:** no unsupported positive sale/customer-evidence gate; valid paid control records once; later state transitions reconcile.
- **Runtime boundary to observe:** Source payment state → normalizer → ledger → customers/data gate and economic decisions.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-O03"></a>

## AT-O03 — Historical sale versions are assigned from current listing state

Finding: [CB2-O03](FINDINGS.md#cb2-o03); Orders; BEFORE; confirmed_static.

- **Preconditions:** sale occurred on v1, listing now v2; include unknown historical version
- **Actions / fault injection:** ingest then certify correction v3
- **Required assertions:** v1 sale stays v1; unknown not silently v2; affected-buyer set is defensible.
- **Runtime boundary to observe:** Sale/delivery evidence → OrderVersion → correction scope → prepared notice/owner decision.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-O04"></a>

## AT-O04 — Out-of-order history corrupts first-purchase and repeat cohorts

Finding: [CB2-O04](FINDINGS.md#cb2-o04); Orders; BEFORE; confirmed_static.

- **Preconditions:** same buyer purchases A at t1, B at t2, ingest B then A and compare A then B
- **Actions / fault injection:** run readings
- **Required assertions:** identical first product A, acquisition date, repeat windows and lifetime values; refunded/unpaid controls excluded consistently.
- **Runtime boundary to observe:** Historical receipts → canonical chronological customer/order state → repeat/north-star → cohort decisions.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-O05"></a>

## AT-O05 — Crash can leave order without version or ledger evidence

Finding: [CB2-O05](FINDINGS.md#cb2-o05); Orders; BEFORE; confirmed_static.

- **Preconditions:** one paid versioned receipt
- **Actions / fault injection:** inject process stop after each customer/order/version/ledger boundary, reopen DB, replay twice
- **Required assertions:** one complete logical sale, correct version and ledger, no orphan or duplicate; follow-on readings only consume committed truth.
- **Runtime boundary to observe:** Receipt → atomic/recoverable unit → durable completion → readings queue → consistent outcomes across restart.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-O06"></a>

## AT-O06 — Unknown Etsy acquisition becomes organic and loop counters resist correction

Finding: [CB2-O06](FINDINGS.md#cb2-o06); Orders; BEFORE; confirmed_static.

- **Preconditions:** source-unknown Etsy order, measured paid order, then refund
- **Actions / fault injection:** two readings and replay
- **Required assertions:** unknown does not improve organic proof/CAC, paid stays paid, refund decreases net contribution without duplicate counters.
- **Runtime boundary to observe:** Receipt + measured attribution → source-qualified order → loop/CAC reader → channel allocation.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-O07"></a>

## AT-O07 — Negative contribution is suppressed and fee estimates can look measured

Finding: [CB2-O07](FINDINGS.md#cb2-o07); Orders; BEFORE; confirmed_static.

- **Preconditions:** sale whose fees exceed revenue; mixed measured/assumed FX and fee records
- **Actions / fault injection:** ingest/readings
- **Required assertions:** negative contribution retained, confidence distinguishes assumptions, no false profitable winner/reinvestment.
- **Runtime boundary to observe:** Source money + fee/FX basis → signed ledger/contribution → CFO/governor → spending recommendation.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-O08"></a>

## AT-O08 — Pricing and offer guards may annotate rather than prevent actions

Finding: [CB2-O08](FINDINGS.md#cb2-o08); Orders; BEFORE; risk_requires_reproduction.

- **Preconditions:** no in-band price satisfies floor, loss-making promotion, offer protected against retirement
- **Actions / fault injection:** pricing and portfolio handlers through downstream scheduler
- **Required assertions:** no prohibited price/retirement action emitted; reasons persist; admissible controls proceed.
- **Runtime boundary to observe:** Economics/offer evidence → guard verdict → price/retirement command consumer → protected action refused.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-O09"></a>

## AT-O09 — Certification is treated as correction without correction scope

Finding: [CB2-O09](FINDINGS.md#cb2-o09); Orders; BEFORE; risk_requires_reproduction.

- **Preconditions:** ordinary v2, correcting v3 withheld by another gate, two corrections with distinct affected sets
- **Actions / fault injection:** certify each
- **Required assertions:** no false correction, no premature safe-version promotion, every affected set preserved without sending.
- **Runtime boundary to observe:** Correction provenance + release eligibility → affected orders → durable notice preparation → owner/authorized delivery workflow.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-O10"></a>

## AT-O10 — North-star metrics use draft and research proxies

Finding: [CB2-O10](FINDINGS.md#cb2-o10); Orders; BEFORE; confirmed_static.

- **Preconditions:** old draft never published, research winner never compiled, published certified control
- **Actions / fault injection:** scheduled north-star
- **Required assertions:** no draft launch or research-as-engineering credit; denominator and missing evidence explicit.
- **Runtime boundary to observe:** Design/engineering/publication events → cohort readings → regression detection → incident/action.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-G01"></a>

## AT-G01 — Third steering run repeats priority movement

Finding: [CB2-G01](FINDINGS.md#cb2-g01); Growth; BEFORE; confirmed_static.

- **Preconditions:** pending eligible job and fixed steering inputs
- **Actions / fault injection:** run handler at least four times in one day, restart after second, then next day
- **Required assertions:** same decision applied once; audit history retained; new genuine decision distinguishable.
- **Runtime boundary to observe:** Weekly/seasonal evidence → durable steering decision → pending-job mutation → worker claim ordering.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-G02"></a>

## AT-G02 — Steering escapes protected priority bands

Finding: [CB2-G02](FINDINGS.md#cb2-g02); Growth; DURING; confirmed_static.

- **Preconditions:** truth/customer job plus fast-lane/winner jobs near their band edge
- **Actions / fault injection:** repeated steering plus new policy and restart
- **Required assertions:** no lower class outranks protected work; bounded recomputation is deterministic.
- **Runtime boundary to observe:** Commercial priority evidence → shared policy → durable priority → queue claim → protected work first.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-G03"></a>

## AT-G03 — Fast-lane targeted rebuild request is not consumed

Finding: [CB2-G03](FINDINGS.md#cb2-g03); Growth; DURING; confirmed_static.

- **Preconditions:** admitted slug A and unrelated certified B needing work
- **Actions / fault injection:** dispatch actual Growth request into Platform handler
- **Required assertions:** only intended A work starts or explicit refusal; completion binds request hashes; B untouched.
- **Runtime boundary to observe:** Fast-lane admission → validated rebuild request → target resolution → scoped stages → hash-bound completion.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-G04"></a>

## AT-G04 — Commercial evidence has consumers but no normal producer

Finding: [CB2-G04](FINDINGS.md#cb2-g04); Growth; BEFORE; coverage_gap.

- **Preconditions:** run normal receipt ingestion without manual row enrichment
- **Actions / fault injection:** all dependent readings; then inject equivalent payload via the proposed real producer
- **Required assertions:** absent-source outputs unmeasured; only produced, attributable values affect decisions.
- **Runtime boundary to observe:** Authorized review/attribution source → source-backed durable facts → readers → ads/creator/referral decision.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-G05"></a>

## AT-G05 — Blank agreements can pass tester graduation

Finding: [CB2-G05](FINDINGS.md#cb2-g05); Growth; BEFORE; confirmed_static.

- **Preconditions:** reliable tester with consent but no agreements, combined agreement, and separate valid agreements
- **Actions / fault injection:** distribution/graduation flow
- **Required assertions:** first two refused; final eligibility does not claim persisted ambassador until explicit authorized transition.
- **Runtime boundary to observe:** Tester delivery + agreements + consent → graduation gate → durable decision → authorized relationship transition.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-G06"></a>

## AT-G06 — Distribution plans are not executable production chains

Finding: [CB2-G06](FINDINGS.md#cb2-g06); Growth; AFTER; coverage_gap.

- **Preconditions:** valid product, missing tutorial and unavailable publishing surface
- **Actions / fault injection:** distribution cadence
- **Required assertions:** no fictional video/tutorial or sent output; authorized internal drafts have real hashes and consumers; surface gate remains closed.
- **Runtime boundary to observe:** Calendar/complaints → content task → actual artifact → quality/truth review → authorized surface action or explicit gate.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-G07"></a>

## AT-G07 — Club cadence uses release spacing and lacks feasibility input

Finding: [CB2-G07](FINDINGS.md#cb2-g07); Growth; BEFORE; confirmed_static.

- **Preconditions:** several releases imported same day but each took months; no platform answer
- **Actions / fault injection:** club reading
- **Required assertions:** no claimed sustainable short cadence or launch permission; valid measured production control differs.
- **Runtime boundary to observe:** Production lifecycle + feasibility response → club answers → launch guard → hold/eligible recommendation.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-G08"></a>

## AT-G08 — Support draft timing can prevent later delivery measurement

Finding: [CB2-G08](FINDINGS.md#cb2-g08); Growth; BEFORE; risk_requires_reproduction.

- **Preconditions:** draft at 10 minutes, actual delivery at 120 minutes; retry same delivery
- **Actions / fault injection:** service reading
- **Required assertions:** delivered SLA uses 120, draft metric remains 10, retry does not rewrite timestamps.
- **Runtime boundary to observe:** Support case → draft → authorized send receipt → delivery timing → trust/ads gate.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-G09"></a>

## AT-G09 — Unknown traffic and absent contribution distort benchmark readings

Finding: [CB2-G09](FINDINGS.md#cb2-g09); Growth; BEFORE; confirmed_static.

- **Preconditions:** unknown, mixed paid/organic, overlapping periods and one fully attributed control
- **Actions / fault injection:** benchmark reading
- **Required assertions:** unknown not search, mixed not forced, absent contribution unrankable, control correctly measured.
- **Runtime boundary to observe:** Orders + traffic outcomes → matched benchmark cell → economics ranking → allocation/pricing.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-G10"></a>

## AT-G10 — Calibration can score overlapping or missing observations as actuals

Finding: [CB2-G10](FINDINGS.md#cb2-g10); Growth; BEFORE; risk_requires_reproduction.

- **Preconditions:** weekly forecast; overlapping outcome rows, duplicate export, disconnected source, then complete actual window
- **Actions / fault injection:** calibration repeatedly
- **Required assertions:** no double count or zero fabrication; one valid score and reproducible confidence ceiling.
- **Runtime boundary to observe:** Forecast snapshot → complete actual source → calibration evidence → confidence ceiling → spending/scaling recommendation.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-G11"></a>

## AT-G11 — Planning-time ads gates are not an execution-time guarantee

Finding: [CB2-G11](FINDINGS.md#cb2-g11); Growth; BEFORE; coverage_gap.

- **Preconditions:** eligible plan, then revoke authority/trust, withdraw listing or exhaust budget
- **Actions / fault injection:** queued campaign with a spy adapter
- **Required assertions:** zero calls/spend for each; stale/direct jobs cannot bypass; permitted mock control reserves bounded budget once.
- **Runtime boundary to observe:** Plan → queued command → current final guard → budget reservation → authorized adapter → recorded result.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-G12"></a>

## AT-G12 — Experiment rank changes may only reorder the dashboard

Finding: [CB2-G12](FINDINGS.md#cb2-g12); Growth; AFTER; coverage_gap.

- **Preconditions:** two eligible experiments with opposite created/rank ordering and one ineligible top-ranked
- **Actions / fault injection:** normal dispatcher
- **Required assertions:** eligible ranked experiment is actually selected, ineligible remains blocked, selection audited.
- **Runtime boundary to observe:** Constraint reading → durable experiment priority → executor selection → allowed experiment action.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-G13"></a>

## AT-G13 — Ads eligibility countdown and credit/cash separation are absent

Finding: [CB2-G13](FINDINGS.md#cb2-g13); Growth; AFTER; coverage_gap.

- **Preconditions:** verified future eligibility event and credit balance, with source unavailable on expiry
- **Actions / fault injection:** cadence before/at/after date and restart
- **Required assertions:** preparation occurs, recheck queued once per due observation, unavailable source remains unknown, no automatic spend and no credit counted as cash.
- **Runtime boundary to observe:** Verified shop state → durable eligibility deadline → scheduler recheck → current eligibility + spend governor → campaign admission.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-D01"></a>

## AT-D01 — Winner judgement contract lacks a proven production writer

Finding: [CB2-D01](FINDINGS.md#cb2-d01); Design; BEFORE; coverage_gap.

- **Preconditions:** normal tournament winner with no handcrafted judgement rows
- **Actions / fault injection:** scheduled judgement path then intake
- **Required assertions:** holds while missing; genuine job output with matching concept hash permits only the checks it actually measured.
- **Runtime boundary to observe:** Tournament winner → judge task → durable provenance → intake/gate → CIR admission/refusal.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-D02"></a>

## AT-D02 — Reconsideration misses changed prerequisite evidence

Finding: [CB2-D02](FINDINGS.md#cb2-d02); Design; BEFORE; risk_requires_reproduction.

- **Preconditions:** held winner, unchanged craft/thumbnail, new valid grid result then changed capability evidence
- **Actions / fault injection:** normal cadence/result event twice
- **Required assertions:** reconsidered once for each changed dependency, no engineering when still blocked, no polling loop.
- **Runtime boundary to observe:** Gate dependency change → durable version → reconsideration job → full gate → at-most-once engineering.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-D03"></a>

## AT-D03 — Gap progression can attach to the wrong arena

Finding: [CB2-D03](FINDINGS.md#cb2-d03); Design; BEFORE; confirmed_static.

- **Preconditions:** two gaps in same pod, distinct arenas/events
- **Actions / fault injection:** engineer winner from second event
- **Required assertions:** only second gap advances; replay/other winner cannot overwrite first; missing identity is held.
- **Runtime boundary to observe:** CoverageGap/event → tournament input → winner intake → CIR/certification → exact gap progression.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-D04"></a>

## AT-D04 — Pipeline report advances on artifact or listing existence

Finding: [CB2-D04](FINDINGS.md#cb2-d04); Design; BEFORE; confirmed_static.

- **Preconditions:** rejected assets, old approved version, draft lacking SEO, challenge with no score
- **Actions / fault injection:** pipeline advancement
- **Required assertions:** no false completed stages; valid release progresses only through actually executed stages; scaling/lessons not fabricated.
- **Runtime boundary to observe:** Winner → certified current release → approved artifacts → SEO/challenge → authorized launch → measurement → scaling/lesson consumers.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-D05"></a>

## AT-D05 — Draft age can become launch-failure evidence

Finding: [CB2-D05](FINDINGS.md#cb2-d05); Design; BEFORE; confirmed_static.

- **Preconditions:** 90-day draft published today, never-published draft, old published listing with no source, measured old published failure
- **Actions / fault injection:** response learning
- **Required assertions:** only last can supply measured failure; no false negative lesson.
- **Runtime boundary to observe:** Publication + exposure/order evidence → response outcome → pod lesson/challenger → future selection.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-D06"></a>

## AT-D06 — Seller language is labelled buyer evidence

Finding: [CB2-D06](FINDINGS.md#cb2-d06); Design; BEFORE; confirmed_static.

- **Preconditions:** phrase only in competitor title, different phrase in authorized query export
- **Actions / fault injection:** SEO mapping
- **Required assertions:** provenance distinguishes both, unsupported demand remains unmeasured, truth/skill guards remain.
- **Runtime boundary to observe:** Seller/query observations → source-qualified intent map → SEO selection → published claims gate.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-D07"></a>

## AT-D07 — Breakthrough and cardigan end-to-end scope remains unfinished

Finding: [CB2-D07](FINDINGS.md#cb2-d07); Design; AFTER; coverage_gap.

- **Preconditions:** specified cardigan/breakthrough brief and available prerequisites
- **Actions / fault injection:** normal upstream workflow, without directly inserting winner/artifact rows
- **Required assertions:** either genuine downstream product evidence passes all gates or report names exact unfinished capability; never a completion claim on refusal.
- **Runtime boundary to observe:** Observed opportunity → generated brief → viable prototype → CIR → certification → finished-product visual chain → validated output.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-D08"></a>

## AT-D08 — Funnel evidence must bind the actual concept payload

Finding: [CB2-D08](FINDINGS.md#cb2-d08); Design; BEFORE; risk_requires_reproduction.

- **Preconditions:** carried and judged concept A
- **Actions / fault injection:** modify construction/brief while retaining slug and submit draft
- **Required assertions:** no compile job; unchanged A control succeeds and audit binds fingerprints.
- **Runtime boundary to observe:** Tournament evidence → immutable concept identity → draft validation → CIR admission.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-M01"></a>

## AT-M01 — Rollback state commits before rollback effect

Finding: [CB2-M01](FINDINGS.md#cb2-m01); Improve; BEFORE; confirmed_static.

- **Preconditions:** promoted bad policy and adopted floor
- **Actions / fault injection:** fail/kill before revert, after state update, during rollback and after effect before receipt; restart and monitor twice
- **Required assertions:** safe config/floor restored, pending work retried, no false completed rollback or duplicate harmful effect.
- **Runtime boundary to observe:** Fresh regression evidence → durable rollback request → idempotent rollback executor → verified active state → completion audit.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-M02"></a>

## AT-M02 — Replay model differs from multi-worker runtime

Finding: [CB2-M02](FINDINGS.md#cb2-m02); Improve; DURING; confirmed_static.

- **Preconditions:** multi-day backlog, two lanes/pool three, failed jobs, missing durations, product proven only later
- **Actions / fault injection:** replay and deterministic worker harness on same tasks
- **Required assertions:** mismatch blocks production-benefit claim; no future-knowledge leakage or failure-as-success.
- **Runtime boundary to observe:** Historical task snapshot → versioned faithful evaluator → shared holdout → promotion decision → actual priority/runtime observation.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-M03"></a>

## AT-M03 — New replay record can be mistaken for fresh post-promotion evidence

Finding: [CB2-M03](FINDINGS.md#cb2-m03); Improve; BEFORE; confirmed_static.

- **Preconditions:** promote on dataset D
- **Actions / fault injection:** rerecord D after promotion, alter contents preserving count/window, then add disjoint new observations
- **Required assertions:** first two cannot claim fresh production uplift; dataset changes detected; only valid new evidence supports monitoring.
- **Runtime boundary to observe:** Task dataset/version → immutable replay evidence → freshness check → hold/revert/ROI decision.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-M04"></a>

## AT-M04 — Registered test filenames are not test execution provenance

Finding: [CB2-M04](FINDINGS.md#cb2-m04); Improve; BEFORE; confirmed_static.

- **Preconditions:** change compiler source, do not run tests, then attach a failing and a passing run on different hashes
- **Actions / fault injection:** registration/proof view
- **Required assertions:** declared coverage not PASS; only matching executed result counts.
- **Runtime boundary to observe:** Source/config hash → registry version → actual test-run artifact → review/promotion proof.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-M05"></a>

## AT-M05 — Lesson matches receive invented currency-valued priority

Finding: [CB2-M05](FINDINGS.md#cb2-m05); Improve; BEFORE; confirmed_static.

- **Preconditions:** multiple identical/redundant lessons and no sales evidence
- **Actions / fault injection:** radar/draft priority
- **Required assertions:** no fabricated CAD return, deduped bounded heuristic, no measured compounding benefit merely for writing acted_on.
- **Runtime boundary to observe:** Lesson → bounded decision input → actual changed work → observed outcome → qualified learning credit.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-M06"></a>

## AT-M06 — Adopting an audit floor does not implement the underlying improvement

Finding: [CB2-M06](FINDINGS.md#cb2-m06); Improve; AFTER; coverage_gap.

- **Preconditions:** teardown trap, unchanged PDF/reply and manually higher score
- **Actions / fault injection:** sandbox and support generation
- **Required assertions:** no claim that trap was repaired until changed bytes/text and independent measurement exist; refusal remains when obligation unmet.
- **Runtime boundary to observe:** Benchmark finding → concrete change proposal → changed artifact/reply → independent self-audit → adoption/publish gate.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-M07"></a>

## AT-M07 — Self-audits and keyword checks can certify wrong content

Finding: [CB2-M07](FINDINGS.md#cb2-m07); Improve; BEFORE; confirmed_static.

- **Preconditions:** passing v1 audit, materially changed v2; misleading support text containing expected keywords; unrelated benchmark category
- **Actions / fault injection:** publish gates
- **Required assertions:** old audit/keywords cannot clear v2; applicable evidence required.
- **Runtime boundary to observe:** Exact artifact+benchmark evidence → scoped obligation evaluation → durable verdict → final publication block/allow.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-M08"></a>

## AT-M08 — Taste and function-quality heuristics overstate independent quality

Finding: [CB2-M08](FINDINGS.md#cb2-m08); Improve; BEFORE; confirmed_static.

- **Preconditions:** technically distinct but poor concept, many rejected/duplicate outputs, role unrelated to improvement
- **Actions / fault injection:** quality/role review
- **Required assertions:** no independent taste or realized-uplift claim from proxy counts; adverse outcomes remain visible.
- **Runtime boundary to observe:** Function output → qualified independent evaluation → attributable outcome → agent quality decision.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-M09"></a>

## AT-M09 — Priority-policy replay is not a general challenger engine

Finding: [CB2-M09](FINDINGS.md#cb2-m09); Improve; AFTER; coverage_gap.

- **Preconditions:** priority, prompt, model and tool challengers plus specialist proposal
- **Actions / fault injection:** nightly/weekly cadence
- **Required assertions:** only actually evaluated/executed kinds report outcomes; others name exact prerequisite and remain incomplete/gated.
- **Runtime boundary to observe:** Proposal/config kind → supported evaluator → evidence → approved execution → observed changed runtime.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-M10"></a>

## AT-M10 — Veto withholding must survive all rebuild paths

Finding: [CB2-M10](FINDINGS.md#cb2-m10); Improve; DURING; risk_requires_reproduction.

- **Preconditions:** owner veto plus failed comparative gate; certify, restart, hourly/targeted rebuild and direct draft/publish
- **Actions / fault injection:** lift only one reason
- **Required assertions:** no bypass and other reason retained; lift both permits only normal gated flow.
- **Runtime boundary to observe:** Owner ruling + all gate results → durable release eligibility → draft/rebuild/asset/publish consumers → refusal.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-I01"></a>

## AT-I01 — Repeated unchanged policy snapshot erases unreviewed change

Finding: [CB2-I01](FINDINGS.md#cb2-i01); Intel; BEFORE; confirmed_static.

- **Preconditions:** A baseline, B changed, identical B reread
- **Actions / fault injection:** policy watch and publish/new-class checks after each
- **Required assertions:** block persists without review; A→B→review(B) clears only B; later C blocks again; review(A) cannot clear B.
- **Runtime boundary to observe:** Policy snapshot → durable unresolved change → incident/gate → final protected action → refusal until matching review.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-I02"></a>

## AT-I02 — Distinctiveness is substituted for top-decile strength

Finding: [CB2-I02](FINDINGS.md#cb2-i02); Intel; BEFORE; confirmed_static.

- **Preconditions:** rare but incoherent/poorly presented concept against current benchmark cards
- **Actions / fault injection:** pre-engineering gate without and with genuine judged scores
- **Required assertions:** rarity alone cannot clear; comparable independent evidence drives verdict.
- **Runtime boundary to observe:** Concept+current benchmarks → independent compatible judgement → provenance → top-decile gate → engineering admission.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-I03"></a>

## AT-I03 — Fabric swatch does not prove finished-product visual fidelity

Finding: [CB2-I03](FINDINGS.md#cb2-i03); Intel; BEFORE; confirmed_static.

- **Preconditions:** garment concept with same stitch fabric but different shaping/assembly
- **Actions / fault injection:** board/grid and finished-product gate
- **Required assertions:** swatch never establishes garment fidelity; real full-object control must match structural dimensions/details before downstream image acceptance.
- **Runtime boundary to observe:** CIR → geometry/assembled reference → provenance-bound photoreal output → independent truth+benchmark comparison → release gate.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-I04"></a>

## AT-I04 — Photo intake validates hash syntax and rights label, not evidence

Finding: [CB2-I04](FINDINGS.md#cb2-i04); Intel; BEFORE; confirmed_static.

- **Preconditions:** nonexistent hash, mismatched bytes, corrupt image, revoked/missing rights, wrong product and valid control
- **Actions / fault injection:** photo intake
- **Required assertions:** invalid cases held/refused and no usable upgrade; valid evidence retained by hash/reference.
- **Runtime boundary to observe:** Photo bytes + rights evidence → validated intake → durable photo provenance → upgrade admission.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-I05"></a>

## AT-I05 — Photo planning stops before review/publication but starts impact clock

Finding: [CB2-I05](FINDINGS.md#cb2-i05); Intel; BEFORE; confirmed_static.

- **Preconditions:** valid intake, rejected asset, approved-but-unpublished asset, then authorized simulated publication
- **Actions / fault injection:** impact reader before/after each
- **Required assertions:** no impact claim before exposure; exact version and non-overlapping windows used; no live publish in test.
- **Runtime boundary to observe:** Photo intake → review → listing-set recertification → final publication guard → exposure event → qualified impact reading.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-I06"></a>

## AT-I06 — Seller location opens a buyer-market evidence gate

Finding: [CB2-I06](FINDINGS.md#cb2-i06); Intel; BEFORE; confirmed_static.

- **Preconditions:** UK seller serving US buyers and unknown buyer geography
- **Actions / fault injection:** discover/scan and market gate
- **Required assertions:** seller diversity visible, buyer market stays unknown; verified second buyer-population evidence alone can open relevant gate.
- **Runtime boundary to observe:** Shop/query/buyer evidence → typed geography provenance → market reader → selection/gate decision.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-I07"></a>

## AT-I07 — Drift incidents resolve when evidence ages out or becomes unreadable

Finding: [CB2-I07](FINDINGS.md#cb2-i07); Intel; BEFORE; confirmed_static.

- **Preconditions:** open hair-drift incident
- **Actions / fault injection:** age all evidence out; add three unreadable batches; then sufficient stable comparable batches
- **Required assertions:** first two preserve hold and say unmeasured; only last may resolve by documented rule.
- **Runtime boundary to observe:** Model-frame verdicts + pack/hash → durable series → incident state → final model-bearing publication gate.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-I08"></a>

## AT-I08 — Benchmark-refresh trigger and purchased candidate can diverge

Finding: [CB2-I08](FINDINGS.md#cb2-i08); Intel; BEFORE; confirmed_static.

- **Preconditions:** new strong seller B, larger known seller A in same pod; first run includes strong leader
- **Actions / fault injection:** assess
- **Required assertions:** request, if allowed, targets evidence needed from B; baseline behavior explicit and bounded; duplicate info rejected.
- **Runtime boundary to observe:** Observed trigger → scoped purchase selection → owner action with exact evidence/cap → owner-controlled acquisition.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-I09"></a>

## AT-I09 — Company standing and entry superiority rely on capability/count proxies

Finding: [CB2-I09](FINDINGS.md#cb2-i09); Intel; BEFORE; confirmed_static.

- **Preconditions:** obsolete approved frames, current rejected frames and ungraded concept with compiler support
- **Actions / fault injection:** standing/entry selection
- **Required assertions:** no inflated coverage or realized size superiority; prospective opportunity remains labelled.
- **Runtime boundary to observe:** Current product evidence + comparable benchmark → scoped standing/entry decision → original design task.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-I10"></a>

## AT-I10 — Quote-token heuristics cover only explicit title forms

Finding: [CB2-I10](FINDINGS.md#cb2-i10); Intel; AFTER; coverage_gap.

- **Preconditions:** explicit quote, unqualified known source phrase, song-title-only input and generic phrase controls
- **Actions / fault injection:** filing then real copy screen
- **Required assertions:** supported tokens reach screen; missing evidence is not blanket clearance; no new arbitrary legal threshold.
- **Runtime boundary to observe:** Source topic/content → protected-token evidence → copy consumer → rights gate → refusal/review.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-I11"></a>

## AT-I11 — Registry reclassification is not in the preserved patch

Finding: [CB2-I11](FINDINGS.md#cb2-i11); Intel; AFTER; coverage_gap.

- **Preconditions:** actual registry plus isolated synthetic gate test
- **Actions / fault injection:** real classification and all affected executor tests
- **Required assertions:** fixture cannot alter production registry; closed gates retain correct type; no software gap hidden by park.
- **Runtime boundary to observe:** Final built-half evidence + live gate truth → integrator classification → independent closure audit.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-I12"></a>

## AT-I12 — Collection patch context predates the fixed no-spin behavior

Finding: [CB2-I12](FINDINGS.md#cb2-i12); Intel; DURING; confirmed_static.

- **Preconditions:** collection missing member, then member certifies, then becomes incoherent
- **Actions / fault injection:** drain jobs/certify/rebuild
- **Required assertions:** no wait spin; one keyed trigger at valid band; incoherent collection not drafted; coherent control can proceed.
- **Runtime boundary to observe:** Member certification → keyed collection job → coherence gate → draft/refusal without spin.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-X01"></a>

## AT-X01 — Duplicate promotion/referral readers can disagree

Finding: [CB2-X01](FINDINGS.md#cb2-x01); Cross-cluster; DURING; risk_requires_reproduction.

- **Preconditions:** marginal promotion/referral with refund, unknown attribution and incomplete control
- **Actions / fault injection:** all readers and consuming pricing/experiment paths
- **Required assertions:** consistent measuredness/refusal and no second reader bypass.
- **Runtime boundary to observe:** Canonical transaction/control facts → shared verdict → pricing/experiment/referral consumers → permitted action/refusal.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-X02"></a>

## AT-X02 — Combined model and registration changes lack integration evidence

Finding: [CB2-X02](FINDINGS.md#cb2-x02); Cross-cluster; DURING; risk_requires_reproduction.

- **Preconditions:** disposable checkpoint-schema DB with orders/findings/jobs plus fresh DB
- **Actions / fault injection:** normal bootstrap and handler discovery only in test environment
- **Required assertions:** preserved rows, valid columns/defaults, unique grants/cadences/handlers and no silent unregistered job.
- **Runtime boundary to observe:** Saved schema/data → supported bootstrap → scheduler/grants → handler → durable evidence.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-X03"></a>

## AT-X03 — Final protected actions must combine every applicable gate

Finding: [CB2-X03](FINDINGS.md#cb2-x03); Cross-cluster; DURING; risk_requires_reproduction.

- **Preconditions:** once-valid release/plan
- **Actions / fault injection:** independently revoke each policy/veto/truth/rights/budget/approval prerequisite before execution; invoke direct, queued, retry and rebuild paths with spy adapters
- **Required assertions:** zero protected calls for every failed prerequisite; all-valid mock control exactly once.
- **Runtime boundary to observe:** All current prerequisite producers → durable eligibility → final action guard → authorized adapter → result/audit tied to inputs.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.

<a id="AT-X04"></a>

## AT-X04 — Test fixtures can conceal missing production evidence chains

Finding: [CB2-X04](FINDINGS.md#cb2-x04); Cross-cluster; AFTER; confirmed_static.

- **Preconditions:** empty disposable DB with normal bootstrap and deterministic external-boundary adapters, no final judgement/commercial/rights rows inserted
- **Actions / fault injection:** normal upstream jobs
- **Required assertions:** claimed evidence arises through actual producers or stays explicitly missing; fixture-only claims cannot qualify as full proof.
- **Runtime boundary to observe:** Boundary input → actual producer → evidence → consumer → decision → observable protected action/refusal.
- **Evidence to retain:** Common harness evidence above, plus the concrete state/action named in this case. No result is currently claimed.
