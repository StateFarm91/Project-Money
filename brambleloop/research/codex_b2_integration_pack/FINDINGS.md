# OPUS REPAIR AND INTEGRATION PACK — NORMALIZED FINDINGS

Authority: independent audit input only. Claude/Opus integrates and certifies. Build 2 is NOT certified.

Evidence checkpoint: `0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56`. These are static findings on preserved candidate patches, not an executed integrated build. No application changes or repair patches have been applied by this pack.

Classifications: `confirmed_static` means directly visible behavior/contradiction; `risk_requires_reproduction` means a concrete failure hypothesis requiring the specified test; `coverage_gap` means the audited obligation remains unproved/unimplemented. Severity is Codex review priority, not a change to Claude's ledger. BEFORE means repair before accepting/integrating that cluster; DURING means explicit manual reconciliation before accepting the combined stage; AFTER means unfinished scope may continue after selective integration, but never count as fulfilled meanwhile. These labels do not change launch gates.

Machine-readable companion: [FINDINGS.json](FINDINGS.json). Each record has a one-to-one [adversarial test specification](ADVERSARIAL_TEST_PLAN.md).

| ID | Cluster | Severity | Timing | Classification | Finding |
|---|---|---|---|---|---|
| [CB2-P01](#cb2-p01) | Platform | Critical | BEFORE | confirmed_static | Reopened status is overridden by executor gate membership |
| [CB2-P02](#cb2-p02) | Platform | Critical | BEFORE | confirmed_static | Module reachability is mistaken for requirement proof |
| [CB2-P03](#cb2-p03) | Platform | High | BEFORE | confirmed_static | Unchecked gates can coexist with closed_out |
| [CB2-P04](#cb2-p04) | Platform | High | BEFORE | confirmed_static | Unique-value comparison permits unmeasured or unsupported superiority |
| [CB2-P05](#cb2-p05) | Platform | High | BEFORE | confirmed_static | Delight scores are fixed proxies and can use another version |
| [CB2-P06](#cb2-p06) | Platform | High | BEFORE | confirmed_static | Frame review can clear unjudged, empty or stale evidence |
| [CB2-P07](#cb2-p07) | Platform | High | BEFORE | confirmed_static | Polling backoff grows without a new observation |
| [CB2-P08](#cb2-p08) | Platform | Medium | BEFORE | confirmed_static | New build SHA stands in for changed failure hypothesis |
| [CB2-P09](#cb2-p09) | Platform | High | BEFORE | risk_requires_reproduction | Lane enforcement needs atomic concurrent admission |
| [CB2-P10](#cb2-p10) | Platform | High | BEFORE | risk_requires_reproduction | Rebuild completion is not strictly request-bound |
| [CB2-P11](#cb2-p11) | Platform | Medium | BEFORE | coverage_gap | Escalation plans do not prove distinct rung execution |
| [CB2-P12](#cb2-p12) | Platform | High | BEFORE | confirmed_static | Launch readiness uses weak rollback and baseline proxies |
| [CB2-P13](#cb2-p13) | Platform | Medium | BEFORE | confirmed_static | Experiment cost attribution is partly a job-type proxy |
| [CB2-P14](#cb2-p14) | Platform | High | AFTER | coverage_gap | Continuous critical-dependency actions remain absent |
| [CB2-P15](#cb2-p15) | Platform | High | AFTER | coverage_gap | Validated-products-per-dollar optimization remains absent |
| [CB2-P16](#cb2-p16) | Platform | High | AFTER | coverage_gap | Recognizability without model remains unevidenced |
| [CB2-P17](#cb2-p17) | Platform | High | AFTER | coverage_gap | Opportunity scorers do not consume evidence freshness/population weighting |
| [CB2-P18](#cb2-p18) | Platform | High | AFTER | coverage_gap | Seasonal takeover has plans but no proven apply/revert executor |
| [CB2-O01](#cb2-o01) | Orders | Critical | BEFORE | confirmed_static | Receipt state is not reconciled for late full or partial refunds |
| [CB2-O02](#cb2-o02) | Orders | Critical | BEFORE | confirmed_static | Unpaid and cancelled receipts can become sales |
| [CB2-O03](#cb2-o03) | Orders | High | BEFORE | confirmed_static | Historical sale versions are assigned from current listing state |
| [CB2-O04](#cb2-o04) | Orders | High | BEFORE | confirmed_static | Out-of-order history corrupts first-purchase and repeat cohorts |
| [CB2-O05](#cb2-o05) | Orders | Critical | BEFORE | confirmed_static | Crash can leave order without version or ledger evidence |
| [CB2-O06](#cb2-o06) | Orders | High | BEFORE | confirmed_static | Unknown Etsy acquisition becomes organic and loop counters resist correction |
| [CB2-O07](#cb2-o07) | Orders | High | BEFORE | confirmed_static | Negative contribution is suppressed and fee estimates can look measured |
| [CB2-O08](#cb2-o08) | Orders | High | BEFORE | risk_requires_reproduction | Pricing and offer guards may annotate rather than prevent actions |
| [CB2-O09](#cb2-o09) | Orders | High | BEFORE | risk_requires_reproduction | Certification is treated as correction without correction scope |
| [CB2-O10](#cb2-o10) | Orders | High | BEFORE | confirmed_static | North-star metrics use draft and research proxies |
| [CB2-G01](#cb2-g01) | Growth | Critical | BEFORE | confirmed_static | Third steering run repeats priority movement |
| [CB2-G02](#cb2-g02) | Growth | Critical | DURING | confirmed_static | Steering escapes protected priority bands |
| [CB2-G03](#cb2-g03) | Growth | High | DURING | confirmed_static | Fast-lane targeted rebuild request is not consumed |
| [CB2-G04](#cb2-g04) | Growth | High | BEFORE | coverage_gap | Commercial evidence has consumers but no normal producer |
| [CB2-G05](#cb2-g05) | Growth | High | BEFORE | confirmed_static | Blank agreements can pass tester graduation |
| [CB2-G06](#cb2-g06) | Growth | High | AFTER | coverage_gap | Distribution plans are not executable production chains |
| [CB2-G07](#cb2-g07) | Growth | Medium | BEFORE | confirmed_static | Club cadence uses release spacing and lacks feasibility input |
| [CB2-G08](#cb2-g08) | Growth | Medium | BEFORE | risk_requires_reproduction | Support draft timing can prevent later delivery measurement |
| [CB2-G09](#cb2-g09) | Growth | High | BEFORE | confirmed_static | Unknown traffic and absent contribution distort benchmark readings |
| [CB2-G10](#cb2-g10) | Growth | High | BEFORE | risk_requires_reproduction | Calibration can score overlapping or missing observations as actuals |
| [CB2-G11](#cb2-g11) | Growth | High | BEFORE | coverage_gap | Planning-time ads gates are not an execution-time guarantee |
| [CB2-G12](#cb2-g12) | Growth | Medium | AFTER | coverage_gap | Experiment rank changes may only reorder the dashboard |
| [CB2-G13](#cb2-g13) | Growth | High | AFTER | coverage_gap | Ads eligibility countdown and credit/cash separation are absent |
| [CB2-D01](#cb2-d01) | Design | High | BEFORE | coverage_gap | Winner judgement contract lacks a proven production writer |
| [CB2-D02](#cb2-d02) | Design | Medium | BEFORE | risk_requires_reproduction | Reconsideration misses changed prerequisite evidence |
| [CB2-D03](#cb2-d03) | Design | High | BEFORE | confirmed_static | Gap progression can attach to the wrong arena |
| [CB2-D04](#cb2-d04) | Design | High | BEFORE | confirmed_static | Pipeline report advances on artifact or listing existence |
| [CB2-D05](#cb2-d05) | Design | High | BEFORE | confirmed_static | Draft age can become launch-failure evidence |
| [CB2-D06](#cb2-d06) | Design | Medium | BEFORE | confirmed_static | Seller language is labelled buyer evidence |
| [CB2-D07](#cb2-d07) | Design | High | AFTER | coverage_gap | Breakthrough and cardigan end-to-end scope remains unfinished |
| [CB2-D08](#cb2-d08) | Design | Medium | BEFORE | risk_requires_reproduction | Funnel evidence must bind the actual concept payload |
| [CB2-M01](#cb2-m01) | Improve | Critical | BEFORE | confirmed_static | Rollback state commits before rollback effect |
| [CB2-M02](#cb2-m02) | Improve | High | DURING | confirmed_static | Replay model differs from multi-worker runtime |
| [CB2-M03](#cb2-m03) | Improve | High | BEFORE | confirmed_static | New replay record can be mistaken for fresh post-promotion evidence |
| [CB2-M04](#cb2-m04) | Improve | High | BEFORE | confirmed_static | Registered test filenames are not test execution provenance |
| [CB2-M05](#cb2-m05) | Improve | Medium | BEFORE | confirmed_static | Lesson matches receive invented currency-valued priority |
| [CB2-M06](#cb2-m06) | Improve | High | AFTER | coverage_gap | Adopting an audit floor does not implement the underlying improvement |
| [CB2-M07](#cb2-m07) | Improve | High | BEFORE | confirmed_static | Self-audits and keyword checks can certify wrong content |
| [CB2-M08](#cb2-m08) | Improve | Medium | BEFORE | confirmed_static | Taste and function-quality heuristics overstate independent quality |
| [CB2-M09](#cb2-m09) | Improve | High | AFTER | coverage_gap | Priority-policy replay is not a general challenger engine |
| [CB2-M10](#cb2-m10) | Improve | High | DURING | risk_requires_reproduction | Veto withholding must survive all rebuild paths |
| [CB2-I01](#cb2-i01) | Intel | Critical | BEFORE | confirmed_static | Repeated unchanged policy snapshot erases unreviewed change |
| [CB2-I02](#cb2-i02) | Intel | High | BEFORE | confirmed_static | Distinctiveness is substituted for top-decile strength |
| [CB2-I03](#cb2-i03) | Intel | High | BEFORE | confirmed_static | Fabric swatch does not prove finished-product visual fidelity |
| [CB2-I04](#cb2-i04) | Intel | High | BEFORE | confirmed_static | Photo intake validates hash syntax and rights label, not evidence |
| [CB2-I05](#cb2-i05) | Intel | High | BEFORE | confirmed_static | Photo planning stops before review/publication but starts impact clock |
| [CB2-I06](#cb2-i06) | Intel | High | BEFORE | confirmed_static | Seller location opens a buyer-market evidence gate |
| [CB2-I07](#cb2-i07) | Intel | High | BEFORE | confirmed_static | Drift incidents resolve when evidence ages out or becomes unreadable |
| [CB2-I08](#cb2-i08) | Intel | Medium | BEFORE | confirmed_static | Benchmark-refresh trigger and purchased candidate can diverge |
| [CB2-I09](#cb2-i09) | Intel | High | BEFORE | confirmed_static | Company standing and entry superiority rely on capability/count proxies |
| [CB2-I10](#cb2-i10) | Intel | Medium | AFTER | coverage_gap | Quote-token heuristics cover only explicit title forms |
| [CB2-I11](#cb2-i11) | Intel | High | AFTER | coverage_gap | Registry reclassification is not in the preserved patch |
| [CB2-I12](#cb2-i12) | Intel | High | DURING | confirmed_static | Collection patch context predates the fixed no-spin behavior |
| [CB2-X01](#cb2-x01) | Cross-cluster | High | DURING | risk_requires_reproduction | Duplicate promotion/referral readers can disagree |
| [CB2-X02](#cb2-x02) | Cross-cluster | High | DURING | risk_requires_reproduction | Combined model and registration changes lack integration evidence |
| [CB2-X03](#cb2-x03) | Cross-cluster | Critical | DURING | risk_requires_reproduction | Final protected actions must combine every applicable gate |
| [CB2-X04](#cb2-x04) | Cross-cluster | High | AFTER | confirmed_static | Test fixtures can conceal missing production evidence chains |

<a id="cb2-p01"></a>

## CB2-P01 — Reopened status is overridden by executor gate membership

- **Cluster / severity / timing:** Platform / Critical / BEFORE
- **Classification:** confirmed_static; not executed; unresolved audit input.
- **Claude defects:** C-65
- **Requirements:** #277, #278, #281, #147, #104, #243, #244, #245, #250, #294, #295, #61, #39, #64, #116, #165, #208, #210, #211, #304
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/build2/closure.py::classify` — [preserved_patch:38](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/platform.mbox#L38)
  - `brambleloop/src/brambleloop/build2/executor.py::gate_for` — [checkpoint_source:788](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/src/brambleloop/build2/executor.py#L788)
- **Existing behavior:** A partial row without parked_on can inherit a gate through executor tuples; 20 reopened rows are hidden as gated.
- **Required behavior:** Explicit reopening must take precedence; distinguish executable residue from a valid external dependency.
- **Why current evidence is insufficient:** The saved C-65 tests do not prove precedence for the manifest's 20 rows.
- **Smallest safe repair:** Make explicit reopen authoritative without deleting legitimate capability gates; add the full 20-row regression.
- **Adversarial regression:** AT-P01. Setup: all 20 manifest rows partial with no parked_on, retain Gate tuples. Act: classify with closed/open/unchecked gate maps. Assert: executable residue remains OPEN in every case; valid explicitly parked control rows retain their classification.
- **Required runtime trace:** Registry + live gates → classify → matrix → integrator closure decision → all 151 reopened obligations accounted for.
- **Dependencies:** All six; Intel reclassification

<a id="cb2-p02"></a>

## CB2-P02 — Module reachability is mistaken for requirement proof

- **Cluster / severity / timing:** Platform / Critical / BEFORE
- **Classification:** confirmed_static; not executed; unresolved audit input.
- **Claude defects:** C-65, C-60
- **Requirements:** #61, #163, #175
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/build2/closure.py::proof_of` — [preserved_patch:22](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/platform.mbox#L22)
  - `brambleloop/src/brambleloop/build2/reachability.py::function_reached` — [preserved_patch:787](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/platform.mbox#L787)
- **Existing behavior:** Closure accepts existence of reachable named machinery without tracing the required output and action.
- **Required behavior:** Reachability is necessary evidence, not sufficient proof of the requirement.
- **Why current evidence is insufficient:** A static route or unrelated live function in the same library can satisfy broad module evidence; owner-gated rows with missing files need explicit failure.
- **Smallest safe repair:** Refuse missing/unrelated proof and attach requirement-specific producer/consumer/action evidence; keep AST output advisory.
- **Adversarial regression:** AT-P02. Setup: library with one live read-only helper and one dead protected-action helper; owner/data-gated rows naming missing files. Act: run proof/classification. Assert: none earns fulfilled built-half proof; positive control requires the named behavior.
- **Required runtime trace:** Runtime root → exact function → durable output → consuming decision → protected action/refusal → independent observation.
- **Dependencies:** All six

<a id="cb2-p03"></a>

## CB2-P03 — Unchecked gates can coexist with closed_out

- **Cluster / severity / timing:** Platform / High / BEFORE
- **Classification:** confirmed_static; not executed; unresolved audit input.
- **Claude defects:** C-65
- **Requirements:** #61, #39
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/build2/closure.py::matrix` — [preserved_patch:91](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/platform.mbox#L91)
- **Existing behavior:** Missing DB or gate-read errors are labelled unchecked, but closed_out still follows OPEN count.
- **Required behavior:** Do not present unchecked gate state as verified closure.
- **Why current evidence is insufficient:** Reporting a warning separately does not invalidate an apparently final summary.
- **Smallest safe repair:** Make certification-readiness explicitly indeterminate when required gate checks are unavailable; preserve detailed state counts.
- **Adversarial regression:** AT-P03. Setup: zero executable OPEN controls plus gated rows. Act: matrix(None), failed gate read, valid live DB. Assert: first two cannot yield verified closure; successful read is separately evidenced.
- **Required runtime trace:** DB/gate check → matrix completeness → summary → certification recommendation withheld on uncertainty.
- **Dependencies:** Intel; integrator

<a id="cb2-p04"></a>

## CB2-P04 — Unique-value comparison permits unmeasured or unsupported superiority

- **Cluster / severity / timing:** Platform / High / BEFORE
- **Classification:** confirmed_static; not executed; unresolved audit input.
- **Claude defects:** C-72, C-60
- **Requirements:** #163
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/teardown/lab.py::compare_advantages` — [preserved_patch:3235](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/platform.mbox#L3235)
  - `brambleloop/src/brambleloop/teardown/lab.py::product_qa` — [preserved_patch:3277](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/platform.mbox#L3277)
  - `brambleloop/src/brambleloop/teardown/scorecard.py::check_unique_value` — [preserved_patch:3316](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/platform.mbox#L3316)
- **Existing behavior:** Certificate capabilities are compared to lower benchmark scores; unmeasured unique value does not block.
- **Required behavior:** An advantage must be established on comparable evidence for the actual product; retain the requirement's refusal semantics.
- **Why current evidence is insufficient:** test_cert_unique_value explicitly accepts UNMEASURED with no block; certificate presence is not a comparative score.
- **Smallest safe repair:** Separate capability existence from measured advantage; preserve refusal or honest prerequisite hold until relevant evidence exists.
- **Adversarial regression:** AT-P04. Setup: granted certificate, absent own comparative scores, benchmark scored low; also no benchmark scores. Act: certify and attempt draft/publish. Assert: neither absence nor assumed superiority becomes passed unique-value evidence; measured positive/negative controls differ.
- **Required runtime trace:** Own release evidence + purchased benchmark → comparison → durable withheld reason → draft/rebuild/publish refusal.
- **Dependencies:** Improve teardown enforcement; Intel benchmarks

<a id="cb2-p05"></a>

## CB2-P05 — Delight scores are fixed proxies and can use another version

- **Cluster / severity / timing:** Platform / High / BEFORE
- **Classification:** confirmed_static; not executed; unresolved audit input.
- **Claude defects:** C-66, C-67
- **Requirements:** #169
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/teardown/lab.py::measured_self_scores` — [preserved_patch:3095](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/platform.mbox#L3095)
  - `brambleloop/src/brambleloop/teardown/lab.py::_act_on_delight` — [preserved_patch:3159](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/platform.mbox#L3159)
- **Existing behavior:** Artifact/certificate presence yields fixed delight scores; slug-wide artifacts may span versions.
- **Required behavior:** Keep capability proxies distinct from product-specific measured delight and real improvement effects.
- **Why current evidence is insufficient:** Test accepts improvement OR refused OR already_open; this does not prove an actionable improvement or valid quality measurement.
- **Smallest safe repair:** Label proxies, bind evidence to release, and require a genuine measured driver before asserting comparative delight.
- **Adversarial regression:** AT-P05. Setup: two versions, only old version has artifacts; certificate-only new version. Act: delight evaluation and follow-on. Assert: no inherited quality score; a measured weak driver produces one traceable actionable proposal.
- **Required runtime trace:** Current release artifacts + measured audit → delight finding → improvement proposal → actual changed artifact → reevaluation.
- **Dependencies:** Improve

<a id="cb2-p06"></a>

## CB2-P06 — Frame review can clear unjudged, empty or stale evidence

- **Cluster / severity / timing:** Platform / High / BEFORE
- **Classification:** confirmed_static; not executed; unresolved audit input.
- **Claude defects:** C-67, C-60
- **Requirements:** #61, #59
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/runtime/release.py::_review_frames` — [preserved_patch:4216](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/platform.mbox#L4216); [checkpoint_source](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/src/brambleloop/runtime/release.py)
  - `brambleloop/src/brambleloop/runtime/release.py::frame_review_state` — [preserved_patch:4257](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/platform.mbox#L4257); [checkpoint_source](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/src/brambleloop/runtime/release.py)
- **Existing behavior:** Described deterministic frames may convert unjudged to clear; empty maps and slug/version lookup do not establish full hash-bound review.
- **Required behavior:** Review every required current frame for applicable claims; unknown stays unknown; changed bytes invalidate approval.
- **Why current evidence is insufficient:** Existing tests cover selected rejected frames but not empty sets, hash changes or legitimate non-applicable subchecks.
- **Smallest safe repair:** Bind review to expected role/position/hash set; retain independent unknowns, separately mark genuinely inapplicable dimensions.
- **Adversarial regression:** AT-P06. Setup: expected six frames. Act: submit empty review, five-frame review, unjudged description and changed bytes at same version. Assert: no complete clear verdict; explicit non-applicable realism never clears other required checks.
- **Required runtime trace:** Frame bytes → independent claim review → hash-bound evidence → listing-set gate → blocked publication for omissions.
- **Dependencies:** Intel physical upgrade; Improve standards

<a id="cb2-p07"></a>

## CB2-P07 — Polling backoff grows without a new observation

- **Cluster / severity / timing:** Platform / High / BEFORE
- **Classification:** confirmed_static; not executed; unresolved audit input.
- **Claude defects:** C-67, C-68
- **Requirements:** #34
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/swarm/orchestrate.py::_free_poll_backoff` — [preserved_patch:4418](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/platform.mbox#L4418)
  - `brambleloop/src/brambleloop/swarm/orchestrate.py::suspended_job_types` — [preserved_patch:4459](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/platform.mbox#L4459)
- **Existing behavior:** Repeated sweeps reuse the same DONE tail and extend suppression from now.
- **Required behavior:** Backoff increments only after a newly completed unchanged attempt and eventually allows a probe.
- **Why current evidence is insufficient:** Untracked test doubles the factor on a second sweep without a new poll.
- **Smallest safe repair:** Store last counted observation/job and absolute next-attempt deadline; do not refresh on reread.
- **Adversarial regression:** AT-P07. Setup: three identical free polls and one sweep at t0. Act: sweep repeatedly without new jobs through the deadline. Assert: factor/deadline stable, next probe becomes eligible; only a newly completed unchanged probe increases backoff; changed result clears it.
- **Required runtime trace:** Completed poll → durable observation cursor → backoff → scheduler → bounded retry → new observation.
- **Dependencies:** Improve STOP-list behavior

<a id="cb2-p08"></a>

## CB2-P08 — New build SHA stands in for changed failure hypothesis

- **Cluster / severity / timing:** Platform / Medium / BEFORE
- **Classification:** confirmed_static; not executed; unresolved audit input.
- **Claude defects:** C-67
- **Requirements:** #34
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/swarm/orchestrate.py::retry_allowed` — [preserved_patch:4494](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/platform.mbox#L4494)
  - `brambleloop/src/brambleloop/swarm/orchestrate.py::suspended_job_types` — [preserved_patch:4459](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/platform.mbox#L4459)
- **Existing behavior:** Any new commit can release a tripped loop.
- **Required behavior:** Retry must name changed relevant conditions or hypothesis and retain the cost/retry ceiling.
- **Why current evidence is insufficient:** Tests change only BRAMBLELOOP_COMMIT and expect retry.
- **Smallest safe repair:** Associate retry authorization with failure/input/dependency change; a new build may be evidence only when relevant.
- **Adversarial regression:** AT-P08. Setup: paid failure breaker. Act: unrelated build SHA change, then relevant corrected credential/input event. Assert: unrelated build cannot repeatedly restart spend; authorized relevant retry is bounded and audited.
- **Required runtime trace:** Failure signature → suspension → relevant change evidence → retry admission → observed outcome.
- **Dependencies:** Improve configuration execution

<a id="cb2-p09"></a>

## CB2-P09 — Lane enforcement needs atomic concurrent admission

- **Cluster / severity / timing:** Platform / High / BEFORE
- **Classification:** risk_requires_reproduction; not executed; unresolved audit input.
- **Claude defects:** C-68
- **Requirements:** #5, #30, #175, #188
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/swarm/capacity.py::share_decision` — [preserved_patch:1593](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/platform.mbox#L1593)
  - `brambleloop/src/brambleloop/swarm/orchestrate.py::lane_hold` — [preserved_patch:1822](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/platform.mbox#L1822)
  - `brambleloop/src/brambleloop/queue/durable.py::claim` — [checkpoint_source:239](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/src/brambleloop/queue/durable.py#L239)
- **Existing behavior:** Capacity is evaluated around queue claiming; serial tests do not establish concurrent limits.
- **Required behavior:** Concurrent workers must neither exceed lane/function capacity nor mutually defer all runnable work.
- **Why current evidence is insufficient:** Single-worker tests with fabricated RUNNING rows cannot prove race behavior.
- **Smallest safe repair:** Use transactional reservation/admission or equivalent proven atomic protocol; release reservations on recovery.
- **Adversarial regression:** AT-P09. Setup: two workers synchronized at admission, one lane slot and another runnable lane. Act: simultaneous claims, kill admitted worker, recover lease. Assert: at most one lane admission, other lane progresses, slot is reclaimed once.
- **Required runtime trace:** Pending jobs + allocation → atomic claim/reservation → worker execution → durable completion/recovery.
- **Dependencies:** Improve replay semantics

<a id="cb2-p10"></a>

## CB2-P10 — Rebuild completion is not strictly request-bound

- **Cluster / severity / timing:** Platform / High / BEFORE
- **Classification:** risk_requires_reproduction; not executed; unresolved audit input.
- **Claude defects:** C-69
- **Requirements:** #171, #172
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/runtime/release.py::_targeted_rebuild` — [preserved_patch:2585](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/platform.mbox#L2585); [checkpoint_source](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/src/brambleloop/runtime/release.py)
  - `brambleloop/src/brambleloop/runtime/release.py::handle_chain_rebuild` — [preserved_patch:2517](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/platform.mbox#L2517); [checkpoint_source:2315](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/src/brambleloop/runtime/release.py#L2315)
- **Existing behavior:** Completion checks emphasize fresh artifact rows and stage dispatch.
- **Required behavior:** Completion must match requested artifact identities, dependencies/fingerprints and the actual rebuild attempt.
- **Why current evidence is insufficient:** Fresh unrelated output can look sufficient; repeated unchanged requests and stage-key collisions lack proof.
- **Smallest safe repair:** Carry a durable request/attempt identity and verify expected dependency hashes before completion; keep narrow staleness exception scoped.
- **Adversarial regression:** AT-P10. Setup: stale target A and fresh unrelated B, then repeated A request with same version. Act: verify before/after exact downstream rebuild and restart. Assert: B cannot close A; no stale output reuse or duplicate side effects.
- **Required runtime trace:** Invalidation request → exact stage → hash-linked provenance → verification → only requested nodes marked rebuilt.
- **Dependencies:** Growth fast lane; all release writers

<a id="cb2-p11"></a>

## CB2-P11 — Escalation plans do not prove distinct rung execution

- **Cluster / severity / timing:** Platform / Medium / BEFORE
- **Classification:** coverage_gap; not executed; unresolved audit input.
- **Claude defects:** C-72, C-67
- **Requirements:** #81
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/visual/gallery.py::escalation_plan` — [preserved_patch:3646](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/platform.mbox#L3646)
  - `brambleloop/src/brambleloop/runtime/pipeline.py::_listing_parity` — [preserved_patch:3544](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/platform.mbox#L3544); [preserved_patch:2067](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/orders.mbox#L2067); [preserved_patch:2284](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/growth.mbox#L2284)
- **Existing behavior:** Live gates allow a rung and photography job is enqueued with a reason.
- **Required behavior:** Each attempted strategy must change the intended inputs/tool/composition and progress only on evaluated results.
- **Why current evidence is insufficient:** An enqueued reason string proves neither recomposition nor tool change.
- **Smallest safe repair:** Persist rung attempt/result and connect each supported rung to actual changed strategy; leave unsupported rungs unavailable.
- **Adversarial regression:** AT-P11. Setup: repeated parity failure with image gate open. Act: execute first failure and subsequent rung. Assert: effective generation inputs change, results are rejudged, retry ceiling holds and failed parity still blocks.
- **Required runtime trace:** Parity failure → strategy attempt → generated asset → independent review → next rung or release refusal.
- **Dependencies:** Intel visual evidence

<a id="cb2-p12"></a>

## CB2-P12 — Launch readiness uses weak rollback and baseline proxies

- **Cluster / severity / timing:** Platform / High / BEFORE
- **Classification:** confirmed_static; not executed; unresolved audit input.
- **Claude defects:** C-66, C-67
- **Requirements:** #54
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/launch/readiness.py::_launch_package_items` — [preserved_patch:3860](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/platform.mbox#L3860)
- **Existing behavior:** Recent continuity.verified existence and generic readings/SEO can stand in for rollback and analytics readiness.
- **Required behavior:** Readiness must cite successful relevant restore evidence and an identified prelaunch analytics baseline.
- **Why current evidence is insufficient:** Positive presence assertions do not test failed verification rows or unrelated periods/releases.
- **Smallest safe repair:** Require success, scope, timestamp and artifact/DB identity appropriate to each readiness item.
- **Adversarial regression:** AT-P12. Setup: failed restore audit, unrelated product baseline and old certified version. Act: launch readiness. Assert: each remains unmet until the matching successful evidence arrives.
- **Required runtime trace:** Restore/baseline producer → scoped evidence → readiness → launch eligibility.
- **Dependencies:** Orders/Growth measurements

<a id="cb2-p13"></a>

## CB2-P13 — Experiment cost attribution is partly a job-type proxy

- **Cluster / severity / timing:** Platform / Medium / BEFORE
- **Classification:** confirmed_static; not executed; unresolved audit input.
- **Claude defects:** C-66, C-67
- **Requirements:** #188, #31
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/finance/governor.py::_experiment_of` — [preserved_patch:1298](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/platform.mbox#L1298)
  - `brambleloop/src/brambleloop/finance/governor.py::spend_by` — [preserved_patch:1324](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/platform.mbox#L1324)
- **Existing behavior:** Unlabelled exploration jobs receive exploration:<job_type> pseudo-experiment labels.
- **Required behavior:** Separate actual experiment IDs from unattributed/category spend; do not claim per-experiment evidence for proxies.
- **Why current evidence is insufficient:** Test explicitly treats the proxy label as attributed experiment spend.
- **Smallest safe repair:** Expose attribution basis and preserve unknown experiment identity; link genuine jobs to experiment records.
- **Adversarial regression:** AT-P13. Setup: two actual experiments of same type plus one untagged job. Act: spend aggregation. Assert: distinct real totals and explicit unattributed amount; no invented experiment.
- **Required runtime trace:** Job/experiment linkage + cost → governor → capacity decision with known attribution quality.
- **Dependencies:** Improve experiment accounting

<a id="cb2-p14"></a>

## CB2-P14 — Continuous critical-dependency actions remain absent

- **Cluster / severity / timing:** Platform / High / AFTER
- **Classification:** coverage_gap; not executed; unresolved audit input.
- **Claude defects:** C-60, C-67
- **Requirements:** #29, #50
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/ops/dependencies.py::map_state` — [checkpoint_source:148](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/src/brambleloop/ops/dependencies.py#L148)
  - `brambleloop/src/brambleloop/ops/dependencies.py::drill` — [checkpoint_source:179](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/src/brambleloop/ops/dependencies.py#L179)
  - `brambleloop/src/brambleloop/scale/dependency.py::report` — [checkpoint_source:133](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/src/brambleloop/scale/dependency.py#L133)
- **Existing behavior:** No new scheduled dependency mapping/probe/recovery-strategy consumer in preserved patches.
- **Required behavior:** Existing dependency inventory must be refreshed and missing backup/recovery strategies or failed probes must produce proportional action.
- **Why current evidence is insufficient:** Absence of relevant patch hunks/callers; static libraries and plans were already the rejected evidence.
- **Smallest safe repair:** Connect existing inventory/probe readers to bounded recurring assessment and durable incident/owner action; retain genuine external dependencies.
- **Adversarial regression:** AT-P14. Setup: AI provider existential and missing recovery strategy, failed DB probe. Act: normal scheduled assessment twice. Assert: one durable scoped incident/decision, explicit recovery/export path, no fake successful drill.
- **Required runtime trace:** Dependency/probe evidence → durable assessment → incident/owner queue → recovery readiness decision.
- **Dependencies:** Platform runtime; Improve diversification

<a id="cb2-p15"></a>

## CB2-P15 — Validated-products-per-dollar optimization remains absent

- **Cluster / severity / timing:** Platform / High / AFTER
- **Classification:** coverage_gap; not executed; unresolved audit input.
- **Claude defects:** C-60, C-67
- **Requirements:** #31
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/finance/unit_cost.py::unit_costs` — [checkpoint_source:65](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/src/brambleloop/finance/unit_cost.py#L65)
  - `brambleloop/src/brambleloop/finance/unit_cost.py::throughput_target` — [checkpoint_source:159](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/src/brambleloop/finance/unit_cost.py#L159)
- **Existing behavior:** Experiment/job attribution and ROI work do not supply every required unit cost or scheduled optimization consumer.
- **Required behavior:** Track the specified artifacts/minutes/costs and optimize using actual validated output and contribution.
- **Why current evidence is insufficient:** Absence of relevant patch hunks/callers; static libraries and plans were already the rejected evidence.
- **Smallest safe repair:** Wire existing unit-cost reader with honest coverage/unknowns to a bounded governor decision; avoid duplicating accounting.
- **Adversarial regression:** AT-P15. Setup: same spend with different validated outputs, missing attribution and later refund. Act: scheduled efficiency assessment. Assert: true unit cost/unknown coverage and traceable changed allocation; no gross-profit substitution.
- **Required runtime trace:** Job/artifact cost+time → unit-cost evidence → governor → bounded allocation → observed efficiency.
- **Dependencies:** Orders money; Improve ROI; Growth acquisition

<a id="cb2-p16"></a>

## CB2-P16 — Recognizability without model remains unevidenced

- **Cluster / severity / timing:** Platform / High / AFTER
- **Classification:** coverage_gap; not executed; unresolved audit input.
- **Claude defects:** C-60, C-67
- **Requirements:** #44
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/brand/moat.py::inventory` — [checkpoint_source:120](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/src/brambleloop/brand/moat.py#L120)
  - `brambleloop/src/brambleloop/brand/moat.py::without` — [checkpoint_source:147](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/src/brambleloop/brand/moat.py#L147)
- **Existing behavior:** Inventory has hand-set existence flags; new layout checks do not measure model-free brand recognizability.
- **Required behavior:** Evidence must cover the master's named brand signatures and product-first continuity.
- **Why current evidence is insufficient:** Absence of relevant patch hunks/callers; static libraries and plans were already the rejected evidence.
- **Smallest safe repair:** Replace unsupported existence claims with artifact-backed inventory and independent model-free comparisons; preserve existing creative gates.
- **Adversarial regression:** AT-P16. Setup: model-free current listing with/without signature elements and unrelated brand controls. Act: independent benchmarked review. Assert: evidence supports only measured recognizability; layout validity alone never passes brand identity.
- **Required runtime trace:** Brand artifacts → inventory provenance → independent model-free evaluation → creative decision.
- **Dependencies:** Design grammar; Intel benchmarks; Improve standards

<a id="cb2-p17"></a>

## CB2-P17 — Opportunity scorers do not consume evidence freshness/population weighting

- **Cluster / severity / timing:** Platform / High / AFTER
- **Classification:** coverage_gap; not executed; unresolved audit input.
- **Claude defects:** C-60, C-67
- **Requirements:** #38
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/radar/provenance.py::weight` — [checkpoint_source:128](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/src/brambleloop/radar/provenance.py#L128)
  - `brambleloop/src/brambleloop/radar/provenance.py::check_presentable_as_current` — [checkpoint_source:169](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/src/brambleloop/radar/provenance.py#L169)
  - `brambleloop/src/brambleloop/radar/arbitrage.py::score_observed` — [preserved_patch:1233](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/intel.mbox#L1233)
  - `brambleloop/src/brambleloop/intel/serp.py::differentiation_by_pod` — [preserved_patch:1209](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/intel.mbox#L1209)
- **Existing behavior:** Source/date additions do not show weight/currentness checks consumed by new scorers; seller location is misused separately.
- **Required behavior:** Preserve source/window/population and discount stale/mismatched evidence before selection or current-demand claims.
- **Why current evidence is insufficient:** Absence of relevant patch hunks/callers; static libraries and plans were already the rejected evidence.
- **Smallest safe repair:** Feed existing provenance functions into actual score/claim paths; preserve unmeasured when provenance is unavailable.
- **Adversarial regression:** AT-P17. Setup: equal fresh local, stale historical and US-only evidence for Canadian claim. Act: actual scorer and listing claim path. Assert: required discounts/refusal apply, persisted score identifies sources and dates.
- **Required runtime trace:** Source trend/search fact → provenance stamp → weighted scorer → selected work/currentness guard.
- **Dependencies:** Intel I06; Design D06; Growth market cells

<a id="cb2-p18"></a>

## CB2-P18 — Seasonal takeover has plans but no proven apply/revert executor

- **Cluster / severity / timing:** Platform / High / AFTER
- **Classification:** coverage_gap; not executed; unresolved audit input.
- **Claude defects:** C-60, C-67
- **Requirements:** #131
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/brand/takeover.py::plan` — [checkpoint_source:183](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/src/brambleloop/brand/takeover.py#L183)
  - `brambleloop/src/brambleloop/brand/takeover.py::schedule` — [checkpoint_source:107](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/src/brambleloop/brand/takeover.py#L107)
  - `brambleloop/src/brambleloop/brand/takeover.py::calendar` — [checkpoint_source:199](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/src/brambleloop/brand/takeover.py#L199)
  - `brambleloop/src/brambleloop/seasonal/daily.py::takeovers` — [preserved_patch:3718](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/intel.mbox#L3718)
- **Existing behavior:** Seasonal plans/collection rows do not execute or restore storefront changes.
- **Required behavior:** Due transitions and reversion must pass authorized surface/quality gates and be durably recoverable.
- **Why current evidence is insufficient:** Absence of relevant patch hunks/callers; static libraries and plans were already the rejected evidence.
- **Smallest safe repair:** Connect existing plan to permitted executor with before-state/result receipts; keep unavailable write surface gated and do not publish during repair.
- **Adversarial regression:** AT-P18. Setup: due takeover, closed surface authority, later mock-authorized surface and end date. Act: scheduler through restart. Assert: no call while closed, one applied transition and one verified restore when authorized; current product truth remains binding.
- **Required runtime trace:** Calendar → durable takeover plan → final surface gate → apply receipt → scheduled restore → verified state.
- **Dependencies:** Intel collections; Growth surfaces; owner authority

<a id="cb2-o01"></a>

## CB2-O01 — Receipt state is not reconciled for late full or partial refunds

- **Cluster / severity / timing:** Orders / Critical / BEFORE
- **Classification:** confirmed_static; not executed; unresolved audit input.
- **Claude defects:** C-64, C-66
- **Requirements:** #11, #12, #22, #252, #269, #271
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/commerce/orders_ingest.py::lines` — [preserved_patch:1053](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/orders.mbox#L1053)
  - `brambleloop/src/brambleloop/commerce/orders_ingest.py::_record_line` — [preserved_patch:1112](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/orders.mbox#L1112)
  - `brambleloop/src/brambleloop/commerce/orders_ingest.py::_last_ingested` — [preserved_patch:1167](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/orders.mbox#L1167)
  - `brambleloop/src/brambleloop/commerce/cohorts.py::record_order` — [preserved_patch:196](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/orders.mbox#L196)
- **Existing behavior:** Existing external refs return early; any receipt refund marks all lines refunded; creation-time overlap misses old updates.
- **Required behavior:** Represent current payment/refund truth per transaction and reconcile changes without double counting; discover updates to old receipts.
- **Why current evidence is insufficient:** Duplicate happy-path ingest proves deduplication only, not mutable commerce truth.
- **Smallest safe repair:** Idempotent reconciliation keyed by external transaction and source revision; line-appropriate refund amounts; durable update cursor/reconciliation sweep.
- **Adversarial regression:** AT-O01. Setup: paid two-line CAD receipt 10+20, first ingest; later refund 5 on first line, then remaining 25 after overlap expires. Act: ingest each source revision twice. Assert: exact net amounts, no unrelated-line full refund, no duplicate adjustment, downstream totals recomputed to zero net at full refund.
- **Required runtime trace:** Receipt revision → normalized transaction/refund → durable order+ledger reconciliation → cohorts/CAC/loops → corrected growth decisions.
- **Dependencies:** Growth; Intel breakouts; Improve ROI

<a id="cb2-o02"></a>

## CB2-O02 — Unpaid and cancelled receipts can become sales

- **Cluster / severity / timing:** Orders / Critical / BEFORE
- **Classification:** confirmed_static; not executed; unresolved audit input.
- **Claude defects:** C-64, C-66
- **Requirements:** #11, #12, #269
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/commerce/orders_ingest.py::lines` — [preserved_patch:1053](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/orders.mbox#L1053)
  - `brambleloop/src/brambleloop/commerce/orders_ingest.py::_record_line` — [preserved_patch:1112](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/orders.mbox#L1112)
- **Existing behavior:** Normalization does not check paid/cancelled state before writing revenue.
- **Required behavior:** Only eligible paid transactions count as sales; cancelled/unpaid/unknown states have explicit non-sale treatment.
- **Why current evidence is insufficient:** Tests seed sale-shaped receipts without state-transition negatives.
- **Smallest safe repair:** Normalize supported receipt states from the actual reader contract and hold unknowns; separate payment events from sale recognition.
- **Adversarial regression:** AT-O02. Setup: unpaid, cancelled-before-payment, paid then cancelled/refunded and missing-state payloads. Act: normal ingest. Assert: no unsupported positive sale/customer-evidence gate; valid paid control records once; later state transitions reconcile.
- **Required runtime trace:** Source payment state → normalizer → ledger → customers/data gate and economic decisions.
- **Dependencies:** Growth trust and ads

<a id="cb2-o03"></a>

## CB2-O03 — Historical sale versions are assigned from current listing state

- **Cluster / severity / timing:** Orders / High / BEFORE
- **Classification:** confirmed_static; not executed; unresolved audit input.
- **Claude defects:** C-64
- **Requirements:** #42
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/commerce/orders_ingest.py::_catalogue` — [preserved_patch:1078](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/orders.mbox#L1078)
  - `brambleloop/src/brambleloop/commerce/orders_ingest.py::_record_line` — [preserved_patch:1112](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/orders.mbox#L1112)
  - `brambleloop/src/brambleloop/commerce/buyer_trust.py::on_certified` — [preserved_patch:116](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/orders.mbox#L116)
- **Existing behavior:** Current listing version is assigned to imported historical transactions.
- **Required behavior:** Bind sale to the delivered version or retain unknown; do not fabricate historical certainty.
- **Why current evidence is insufficient:** Fixture matches current listing and calls it recorded at sale time.
- **Smallest safe repair:** Use immutable delivery/listing-version history where available; unknown history must stay explicit and conservatively route correction review.
- **Adversarial regression:** AT-O03. Setup: sale occurred on v1, listing now v2; include unknown historical version. Act: ingest then certify correction v3. Assert: v1 sale stays v1; unknown not silently v2; affected-buyer set is defensible.
- **Required runtime trace:** Sale/delivery evidence → OrderVersion → correction scope → prepared notice/owner decision.
- **Dependencies:** Platform release hashes; Growth trust

<a id="cb2-o04"></a>

## CB2-O04 — Out-of-order history corrupts first-purchase and repeat cohorts

- **Cluster / severity / timing:** Orders / High / BEFORE
- **Classification:** confirmed_static; not executed; unresolved audit input.
- **Claude defects:** C-64, C-66
- **Requirements:** #11, #12, #252, #104, #132
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/commerce/orders_ingest.py::ingest` — [preserved_patch:1179](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/orders.mbox#L1179)
  - `brambleloop/src/brambleloop/commerce/orders_ingest.py::_record_line` — [preserved_patch:1112](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/orders.mbox#L1112)
  - `brambleloop/src/brambleloop/commerce/cohorts.py::record_customer` — [preserved_patch:195](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/orders.mbox#L195)
  - `brambleloop/src/brambleloop/commerce/cohorts.py::record_order` — [preserved_patch:196](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/orders.mbox#L196)
- **Existing behavior:** First customer record reflects first encountered receipt, which need not be earliest chronologically.
- **Required behavior:** First acquisition/product and repeat classification must be invariant to arrival order.
- **Why current evidence is insufficient:** Repeated identical batches do not exercise late historical events.
- **Smallest safe repair:** Derive earliest paid qualifying transaction and recompute dependent cohort/repeat values on backfill.
- **Adversarial regression:** AT-O04. Setup: same buyer purchases A at t1, B at t2, ingest B then A and compare A then B. Act: run readings. Assert: identical first product A, acquisition date, repeat windows and lifetime values; refunded/unpaid controls excluded consistently.
- **Required runtime trace:** Historical receipts → canonical chronological customer/order state → repeat/north-star → cohort decisions.
- **Dependencies:** Growth attribution; Design learning

<a id="cb2-o05"></a>

## CB2-O05 — Crash can leave order without version or ledger evidence

- **Cluster / severity / timing:** Orders / Critical / BEFORE
- **Classification:** confirmed_static; not executed; unresolved audit input.
- **Claude defects:** C-64
- **Requirements:** #11, #12, #42, #269
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/commerce/orders_ingest.py::_record_line` — [preserved_patch:1112](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/orders.mbox#L1112)
  - `brambleloop/src/brambleloop/commerce/cohorts.py::record_order` — [preserved_patch:196](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/orders.mbox#L196)
- **Existing behavior:** Customer, order, version and ledger writes span separate transactions; duplicate order path can bypass missing dependent writes.
- **Required behavior:** Restart must converge to a complete, exactly-once logical transaction with traceable partial state.
- **Why current evidence is insufficient:** Happy duplicate replay lacks interruption at individual writes.
- **Smallest safe repair:** Use one DB transaction where possible, otherwise explicit recoverable ingestion state/outbox and repair-on-replay of every dependent row.
- **Adversarial regression:** AT-O05. Setup: one paid versioned receipt. Act: inject process stop after each customer/order/version/ledger boundary, reopen DB, replay twice. Assert: one complete logical sale, correct version and ledger, no orphan or duplicate; follow-on readings only consume committed truth.
- **Required runtime trace:** Receipt → atomic/recoverable unit → durable completion → readings queue → consistent outcomes across restart.
- **Dependencies:** Platform recovery; Growth reads

<a id="cb2-o06"></a>

## CB2-O06 — Unknown Etsy acquisition becomes organic and loop counters resist correction

- **Cluster / severity / timing:** Orders / High / BEFORE
- **Classification:** confirmed_static; not executed; unresolved audit input.
- **Claude defects:** C-64, C-66
- **Requirements:** #22, #256, #271, #269
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/commerce/orders_ingest.py::_record_line` — [preserved_patch:1112](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/orders.mbox#L1112)
  - `brambleloop/src/brambleloop/commerce/order_readings.py::loop_block` — [preserved_patch:813](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/orders.mbox#L813)
  - `brambleloop/src/brambleloop/growth/loops.py::observe` — [checkpoint_source:140](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/src/brambleloop/growth/loops.py#L140)
- **Existing behavior:** Generic Etsy acquisition is mapped to organic; non-negative deltas cannot represent downward corrections.
- **Required behavior:** Unknown attribution stays unknown; loop metrics reconcile refunds/corrections and distinguish event counts from net outcomes.
- **Why current evidence is insufficient:** Seeded attributed outcomes do not prove production attribution; increasing-only tests miss refunds.
- **Smallest safe repair:** Persist attribution basis/confidence; aggregate from reconciled facts or signed corrections, not assumed organic and positive-only updates.
- **Adversarial regression:** AT-O06. Setup: source-unknown Etsy order, measured paid order, then refund. Act: two readings and replay. Assert: unknown does not improve organic proof/CAC, paid stays paid, refund decreases net contribution without duplicate counters.
- **Required runtime trace:** Receipt + measured attribution → source-qualified order → loop/CAC reader → channel allocation.
- **Dependencies:** Growth G04/G09; Intel breakout

<a id="cb2-o07"></a>

## CB2-O07 — Negative contribution is suppressed and fee estimates can look measured

- **Cluster / severity / timing:** Orders / High / BEFORE
- **Classification:** confirmed_static; not executed; unresolved audit input.
- **Claude defects:** C-64, C-66
- **Requirements:** #269, #49, #22
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/commerce/orders_ingest.py::_record_line` — [preserved_patch:1112](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/orders.mbox#L1112)
  - `brambleloop/src/brambleloop/commerce/orders_ingest.py::_to_cad` — [preserved_patch:1096](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/orders.mbox#L1096)
- **Existing behavior:** Contribution is clamped to zero; fee calculation is modelled while FX assumption is explicitly labelled.
- **Required behavior:** Retain losses and mark estimated versus measured money inputs end to end.
- **Why current evidence is insufficient:** Positive-sale tests cannot show that loss-making orders remain visible to governors.
- **Smallest safe repair:** Remove loss suppression in derived truth; retain provenance for fee/FX assumptions without pretending settlement is measured.
- **Adversarial regression:** AT-O07. Setup: sale whose fees exceed revenue; mixed measured/assumed FX and fee records. Act: ingest/readings. Assert: negative contribution retained, confidence distinguishes assumptions, no false profitable winner/reinvestment.
- **Required runtime trace:** Source money + fee/FX basis → signed ledger/contribution → CFO/governor → spending recommendation.
- **Dependencies:** Growth evidence; Improve ROI

<a id="cb2-o08"></a>

## CB2-O08 — Pricing and offer guards may annotate rather than prevent actions

- **Cluster / severity / timing:** Orders / High / BEFORE
- **Classification:** risk_requires_reproduction; not executed; unresolved audit input.
- **Claude defects:** C-64, C-67
- **Requirements:** #13, #233, #235, #269
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/commerce/pricing.py::decide_price` — [preserved_patch:1279](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/orders.mbox#L1279)
  - `brambleloop/src/brambleloop/runtime/release.py::handle_pricing_position` — [preserved_patch:2105](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/orders.mbox#L2105); [preserved_patch:2458](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/growth.mbox#L2458); [checkpoint_source:386](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/src/brambleloop/runtime/release.py#L386)
  - `brambleloop/src/brambleloop/runtime/pipeline.py::handle_portfolio_review` — [preserved_patch:1960](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/orders.mbox#L1960)
- **Existing behavior:** Discount/net guards can add reasons while returning a price; offer guard edits coexist with portfolio classification/actions.
- **Required behavior:** Disallowed discounts, impossible net floors and protected retirement must stop their actual downstream action.
- **Why current evidence is insufficient:** Current tests check reasons/guard fields or feasible prices, not impossible constraints and execution.
- **Smallest safe repair:** Propagate explicit refusal into consumers; reconcile classification and actionable work list rather than adding warning prose.
- **Adversarial regression:** AT-O08. Setup: no in-band price satisfies floor, loss-making promotion, offer protected against retirement. Act: pricing and portfolio handlers through downstream scheduler. Assert: no prohibited price/retirement action emitted; reasons persist; admissible controls proceed.
- **Required runtime trace:** Economics/offer evidence → guard verdict → price/retirement command consumer → protected action refused.
- **Dependencies:** Growth pricing/promotions; Platform publishing

<a id="cb2-o09"></a>

## CB2-O09 — Certification is treated as correction without correction scope

- **Cluster / severity / timing:** Orders / High / BEFORE
- **Classification:** risk_requires_reproduction; not executed; unresolved audit input.
- **Claude defects:** C-64, C-67
- **Requirements:** #42
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/commerce/buyer_trust.py::on_certified` — [preserved_patch:116](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/orders.mbox#L116)
  - `brambleloop/src/brambleloop/runtime/pipeline.py::handle_certify` — [preserved_patch:2190](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/platform.mbox#L2190); [preserved_patch:1922](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/orders.mbox#L1922); [preserved_patch:1548](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/improve.mbox#L1548)
- **Existing behavior:** New certified versions update current_safe_version and prepare notices without demonstrated correction-specific trigger.
- **Required behavior:** Distinguish routine versions from correction releases and approved releasability; prepare notices only for affected buyers.
- **Why current evidence is insufficient:** One v1→v2 fixture proves preparation, not correct scope or safety ordering.
- **Smallest safe repair:** Require explicit correction relation and release eligibility; maintain notice preparation/delivery states separately.
- **Adversarial regression:** AT-O09. Setup: ordinary v2, correcting v3 withheld by another gate, two corrections with distinct affected sets. Act: certify each. Assert: no false correction, no premature safe-version promotion, every affected set preserved without sending.
- **Required runtime trace:** Correction provenance + release eligibility → affected orders → durable notice preparation → owner/authorized delivery workflow.
- **Dependencies:** Platform withholding; Improve veto

<a id="cb2-o10"></a>

## CB2-O10 — North-star metrics use draft and research proxies

- **Cluster / severity / timing:** Orders / High / BEFORE
- **Classification:** confirmed_static; not executed; unresolved audit input.
- **Claude defects:** C-66
- **Requirements:** #104, #132
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/creative/standard.py::north_star_cohorts` — [preserved_patch:1491](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/orders.mbox#L1491)
  - `brambleloop/src/brambleloop/creative/standard.py::north_star_from_db` — [preserved_patch:1593](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/orders.mbox#L1593)
- **Existing behavior:** Listing existence and upstream research survival can stand in for actual launch and engineering outcomes.
- **Required behavior:** Compute each named metric from its actual lifecycle event; unavailable observations remain unmeasured.
- **Why current evidence is insufficient:** Seeded metric regressions prove arithmetic, not validity of source event semantics.
- **Smallest safe repair:** Use published/delivered and engineering-stage events with release/cohort identity; label leading proxies separately.
- **Adversarial regression:** AT-O10. Setup: old draft never published, research winner never compiled, published certified control. Act: scheduled north-star. Assert: no draft launch or research-as-engineering credit; denominator and missing evidence explicit.
- **Required runtime trace:** Design/engineering/publication events → cohort readings → regression detection → incident/action.
- **Dependencies:** Design lifecycle; Intel progression

<a id="cb2-g01"></a>

## CB2-G01 — Third steering run repeats priority movement

- **Cluster / severity / timing:** Growth / Critical / BEFORE
- **Classification:** confirmed_static; not executed; unresolved audit input.
- **Claude defects:** C-67
- **Requirements:** #264, #267, #276, #291
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/runtime/growth_ops.py::steer` — [preserved_patch:2160](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/growth.mbox#L2160)
  - `brambleloop/src/brambleloop/runtime/growth_ops.py::handle_growth_steer` — [preserved_patch:2256](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/growth.mbox#L2256)
  - `brambleloop/src/brambleloop/runtime/growth_ops.py::record` — [preserved_patch:1173](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/growth.mbox#L1173)
- **Existing behavior:** Daily reading is overwritten: first run moves, second skips and erases movement history, third can move again.
- **Required behavior:** Repeated execution of the same steering decision must be idempotent across runs and restarts.
- **Why current evidence is insufficient:** Existing regression asserts only the second run.
- **Smallest safe repair:** Persist applied decision identity per job or recompute priority from immutable base/current policy; retain movement history independently of summary replacement.
- **Adversarial regression:** AT-G01. Setup: pending eligible job and fixed steering inputs. Act: run handler at least four times in one day, restart after second, then next day. Assert: same decision applied once; audit history retained; new genuine decision distinguishable.
- **Required runtime trace:** Weekly/seasonal evidence → durable steering decision → pending-job mutation → worker claim ordering.
- **Dependencies:** Improve priority policy; Platform queue

<a id="cb2-g02"></a>

## CB2-G02 — Steering escapes protected priority bands

- **Cluster / severity / timing:** Growth / Critical / DURING
- **Classification:** confirmed_static; not executed; unresolved audit input.
- **Claude defects:** C-67
- **Requirements:** #264, #267, #276, #291, #187
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/runtime/growth_ops.py::steer` — [preserved_patch:2160](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/growth.mbox#L2160)
  - `brambleloop/src/brambleloop/swarm/orchestrate.py::priority_decision` — [preserved_patch:1861](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/improve.mbox#L1861)
- **Existing behavior:** Growth mutates priority by raw credits while Improve bounds changes within a band.
- **Required behavior:** One priority authority must preserve customer/truth protection and bounded permitted urgency.
- **Why current evidence is insufficient:** Growth tests expect large raw movements and never compare against protected jobs.
- **Smallest safe repair:** Route steering through shared priority policy; store reasons as inputs, not cumulative deltas; preserve established band invariants.
- **Adversarial regression:** AT-G02. Setup: truth/customer job plus fast-lane/winner jobs near their band edge. Act: repeated steering plus new policy and restart. Assert: no lower class outranks protected work; bounded recomputation is deterministic.
- **Required runtime trace:** Commercial priority evidence → shared policy → durable priority → queue claim → protected work first.
- **Dependencies:** Improve M02; Platform lane admission

<a id="cb2-g03"></a>

## CB2-G03 — Fast-lane targeted rebuild request is not consumed

- **Cluster / severity / timing:** Growth / High / DURING
- **Classification:** confirmed_static; not executed; unresolved audit input.
- **Claude defects:** C-69, C-67
- **Requirements:** #291, #172
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/runtime/growth_ops.py::handle_growth_steer` — [preserved_patch:2256](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/growth.mbox#L2256)
  - `brambleloop/src/brambleloop/runtime/release.py::handle_chain_rebuild` — [preserved_patch:2517](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/platform.mbox#L2517); [checkpoint_source:2315](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/src/brambleloop/runtime/release.py#L2315)
  - `brambleloop/src/brambleloop/runtime/release.py::_targeted_rebuild` — [preserved_patch:2585](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/platform.mbox#L2585); [checkpoint_source](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/src/brambleloop/runtime/release.py)
- **Existing behavior:** Growth emits slugs, Platform selects targeted behavior from artefacts; request may fall through to broad scan.
- **Required behavior:** Contract must explicitly resolve requested slugs to scoped release/artifact targets or reject unsupported input.
- **Why current evidence is insufficient:** Queue-existence assertion proves neither targeting nor completion.
- **Smallest safe repair:** Agree one validated request schema and adapter; unsupported fields must not silently trigger broad rebuild.
- **Adversarial regression:** AT-G03. Setup: admitted slug A and unrelated certified B needing work. Act: dispatch actual Growth request into Platform handler. Assert: only intended A work starts or explicit refusal; completion binds request hashes; B untouched.
- **Required runtime trace:** Fast-lane admission → validated rebuild request → target resolution → scoped stages → hash-bound completion.
- **Dependencies:** Platform P10

<a id="cb2-g04"></a>

## CB2-G04 — Commercial evidence has consumers but no normal producer

- **Cluster / severity / timing:** Growth / High / BEFORE
- **Classification:** coverage_gap; not executed; unresolved audit input.
- **Claude defects:** C-66, C-67
- **Requirements:** #244, #249, #257, #258, #256
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/runtime/commerce_readings.py::_review_stars` — [preserved_patch:675](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/growth.mbox#L675)
  - `brambleloop/src/brambleloop/runtime/growth_ops.py::creators_reading` — [preserved_patch:1658](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/growth.mbox#L1658)
  - `brambleloop/src/brambleloop/runtime/growth_ops.py::ads_plan` — [preserved_patch:1337](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/growth.mbox#L1337)
  - `brambleloop/src/brambleloop/commerce/orders_ingest.py::_record_line` — [preserved_patch:1112](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/orders.mbox#L1112)
- **Existing behavior:** Review stars, creator references and offsite/paid attribution appear in fixtures but are not populated by the saved receipt writer.
- **Required behavior:** Connect supported evidence sources with provenance or remain unmeasured; never infer missing commercial truth.
- **Why current evidence is insufficient:** Hand-seeded Order.detail values prove readers only.
- **Smallest safe repair:** Document actual source contracts and add the narrow authorized ingestion path or remove measured claims until source exists.
- **Adversarial regression:** AT-G04. Setup: run normal receipt ingestion without manual row enrichment. Act: all dependent readings; then inject equivalent payload via the proposed real producer. Assert: absent-source outputs unmeasured; only produced, attributable values affect decisions.
- **Required runtime trace:** Authorized review/attribution source → source-backed durable facts → readers → ads/creator/referral decision.
- **Dependencies:** Orders O06; Intel physical proof

<a id="cb2-g05"></a>

## CB2-G05 — Blank agreements can pass tester graduation

- **Cluster / severity / timing:** Growth / High / BEFORE
- **Classification:** confirmed_static; not executed; unresolved audit input.
- **Claude defects:** C-66, C-67
- **Requirements:** #250
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/runtime/growth_ops.py::creators_reading` — [preserved_patch:1658](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/growth.mbox#L1658)
  - `brambleloop/src/brambleloop/growth/creators.py::may_graduate` — [checkpoint_source:569](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/src/brambleloop/growth/creators.py#L569)
- **Existing behavior:** Caller supplies empty testing_terms/ambassador_terms and returns graduated references; checker can permit reliability+consent without actual terms.
- **Required behavior:** Verify separate actual agreements and consent before relationship transition; eligibility is not completed graduation.
- **Why current evidence is insufficient:** Fixture expects graduation with these caller inputs; no persistent transition is established.
- **Smallest safe repair:** Load referenced agreements, reject missing evidence, record eligibility separately from executed relationship change.
- **Adversarial regression:** AT-G05. Setup: reliable tester with consent but no agreements, combined agreement, and separate valid agreements. Act: distribution/graduation flow. Assert: first two refused; final eligibility does not claim persisted ambassador until explicit authorized transition.
- **Required runtime trace:** Tester delivery + agreements + consent → graduation gate → durable decision → authorized relationship transition.
- **Dependencies:** Owner evidence; Orders creator attribution

<a id="cb2-g06"></a>

## CB2-G06 — Distribution plans are not executable production chains

- **Cluster / severity / timing:** Growth / High / AFTER
- **Classification:** coverage_gap; not executed; unresolved audit input.
- **Claude defects:** C-67
- **Requirements:** #246, #247, #248, #251, #255, #295
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/runtime/growth_ops.py::plan_pins` — [preserved_patch:1577](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/growth.mbox#L1577)
  - `brambleloop/src/brambleloop/runtime/growth_ops.py::plan_clusters` — [preserved_patch:1613](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/growth.mbox#L1613)
  - `brambleloop/src/brambleloop/runtime/growth_ops.py::plan_video` — [preserved_patch:1632](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/growth.mbox#L1632)
  - `brambleloop/src/brambleloop/runtime/growth_ops.py::tools_reading` — [preserved_patch:1725](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/growth.mbox#L1725)
  - `brambleloop/src/brambleloop/runtime/growth_ops.py::handle_growth_distribution` — [preserved_patch:1836](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/growth.mbox#L1836)
- **Existing behavior:** Plans and checks are recorded; tutorial refs may be constructed strings; flow design selection does not prove the chosen causal plan fits.
- **Required behavior:** Every claimed produced/distributed result needs a real consumer; unavailable external surfaces stay gated.
- **Why current evidence is insufficient:** Plan counts and landable/hostable flags do not prove content creation, canonical tutorial existence or authorized delivery.
- **Smallest safe repair:** Wire bounded internal draft tasks and validate referenced artifacts; expose plan-only versus produced/approved/distributed states.
- **Adversarial regression:** AT-G06. Setup: valid product, missing tutorial and unavailable publishing surface. Act: distribution cadence. Assert: no fictional video/tutorial or sent output; authorized internal drafts have real hashes and consumers; surface gate remains closed.
- **Required runtime trace:** Calendar/complaints → content task → actual artifact → quality/truth review → authorized surface action or explicit gate.
- **Dependencies:** Design assets; Platform provenance; owner surfaces

<a id="cb2-g07"></a>

## CB2-G07 — Club cadence uses release spacing and lacks feasibility input

- **Cluster / severity / timing:** Growth / Medium / BEFORE
- **Classification:** confirmed_static; not executed; unresolved audit input.
- **Claude defects:** C-66
- **Requirements:** #253
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/runtime/commerce_readings.py::_club_answers` — [preserved_patch:690](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/growth.mbox#L690)
- **Existing behavior:** Release interarrival is used as cadence evidence; platform feasibility remains unanswered.
- **Required behavior:** Separate throughput observations from production lead time and answer only supported feasibility inputs.
- **Why current evidence is insufficient:** Seeded releases can pass a cadence check without proving sustainable production capacity.
- **Smallest safe repair:** Use actual lifecycle durations/capacity evidence; preserve genuinely unanswered demand/platform questions.
- **Adversarial regression:** AT-G07. Setup: several releases imported same day but each took months; no platform answer. Act: club reading. Assert: no claimed sustainable short cadence or launch permission; valid measured production control differs.
- **Required runtime trace:** Production lifecycle + feasibility response → club answers → launch guard → hold/eligible recommendation.
- **Dependencies:** Design leadtime; owner surface

<a id="cb2-g08"></a>

## CB2-G08 — Support draft timing can prevent later delivery measurement

- **Cluster / severity / timing:** Growth / Medium / BEFORE
- **Classification:** risk_requires_reproduction; not executed; unresolved audit input.
- **Claude defects:** C-66, C-67
- **Requirements:** #18, #17
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/runtime/release.py::_check_and_time_reply` — [preserved_patch:848](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/growth.mbox#L848); [checkpoint_source](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/src/brambleloop/runtime/release.py)
  - `brambleloop/src/brambleloop/support/service.py::record_response` — [preserved_patch:909](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/growth.mbox#L909)
  - `brambleloop/src/brambleloop/support/service.py::service_level` — [preserved_patch:941](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/growth.mbox#L941)
- **Existing behavior:** Once response_minutes exists, the draft-ready path may never transition to a measured delivered response.
- **Required behavior:** Track draft-ready and sent/received timing separately; trust uses actual delivered service.
- **Why current evidence is insufficient:** Test proves draft timing separation but not draft→delivery update.
- **Smallest safe repair:** Persist distinct lifecycle timestamps and idempotently update actual delivery from authorized send result.
- **Adversarial regression:** AT-G08. Setup: draft at 10 minutes, actual delivery at 120 minutes; retry same delivery. Act: service reading. Assert: delivered SLA uses 120, draft metric remains 10, retry does not rewrite timestamps.
- **Required runtime trace:** Support case → draft → authorized send receipt → delivery timing → trust/ads gate.
- **Dependencies:** Growth ads; existing support integration

<a id="cb2-g09"></a>

## CB2-G09 — Unknown traffic and absent contribution distort benchmark readings

- **Cluster / severity / timing:** Growth / High / BEFORE
- **Classification:** confirmed_static; not executed; unresolved audit input.
- **Claude defects:** C-66, C-67
- **Requirements:** #238, #239, #24
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/runtime/growth_ops.py::benchmark_observations` — [preserved_patch:1980](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/growth.mbox#L1980)
  - `brambleloop/src/brambleloop/runtime/growth_ops.py::benchmarks_reading` — [preserved_patch:2041](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/growth.mbox#L2041)
- **Existing behavior:** Unknown traffic defaults to etsy_search; opportunity input passes contribution_per_order_cad=None.
- **Required behavior:** Maintain unknown source and compute contribution only from reconciled matching observations; no measured ranking from absent inputs.
- **Why current evidence is insufficient:** Occupied cells/diagnosis existence do not prove correct cohort identity or usable contribution ranking.
- **Smallest safe repair:** Separate unknown/mixed cells; join matching periods/orders with provenance; expose unrankable markets.
- **Adversarial regression:** AT-G09. Setup: unknown, mixed paid/organic, overlapping periods and one fully attributed control. Act: benchmark reading. Assert: unknown not search, mixed not forced, absent contribution unrankable, control correctly measured.
- **Required runtime trace:** Orders + traffic outcomes → matched benchmark cell → economics ranking → allocation/pricing.
- **Dependencies:** Orders O01/O06/O07

<a id="cb2-g10"></a>

## CB2-G10 — Calibration can score overlapping or missing observations as actuals

- **Cluster / severity / timing:** Growth / High / BEFORE
- **Classification:** risk_requires_reproduction; not executed; unresolved audit input.
- **Claude defects:** C-66
- **Requirements:** #262, #27, #275
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/scale/evidence.py::calibration` — [preserved_patch:508](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/growth.mbox#L508)
  - `brambleloop/src/brambleloop/scale/evidence.py::record_forecast` — [preserved_patch:474](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/growth.mbox#L474)
  - `brambleloop/src/brambleloop/growth/weekly.py::solve` — [preserved_patch:43](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/growth.mbox#L43)
- **Existing behavior:** Outcome-period sums do not establish disjoint coverage; missing observations can become measured zero.
- **Required behavior:** Forecast evaluation requires complete comparable actual windows, deduplication and explicit missingness.
- **Why current evidence is insufficient:** Fixtures with clean periods miss duplicate windows and disconnected-source conditions.
- **Smallest safe repair:** Bind forecast to metric/window/source version; score only complete non-overlapping actuals or a defensible normalized series.
- **Adversarial regression:** AT-G10. Setup: weekly forecast; overlapping outcome rows, duplicate export, disconnected source, then complete actual window. Act: calibration repeatedly. Assert: no double count or zero fabrication; one valid score and reproducible confidence ceiling.
- **Required runtime trace:** Forecast snapshot → complete actual source → calibration evidence → confidence ceiling → spending/scaling recommendation.
- **Dependencies:** Orders reconciliation; Growth CSV

<a id="cb2-g11"></a>

## CB2-G11 — Planning-time ads gates are not an execution-time guarantee

- **Cluster / severity / timing:** Growth / High / BEFORE
- **Classification:** coverage_gap; not executed; unresolved audit input.
- **Claude defects:** C-70, C-67
- **Requirements:** #17, #242, #243, #244, #245, #294, #295
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/runtime/growth_ops.py::ads_plan` — [preserved_patch:1337](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/growth.mbox#L1337)
  - `brambleloop/src/brambleloop/runtime/growth_ops.py::handle_ads_campaign` — [preserved_patch:1507](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/growth.mbox#L1507)
  - `brambleloop/src/brambleloop/runtime/growth_ops.py::trust_checks` — [preserved_patch:2698](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/growth.mbox#L2698)
- **Existing behavior:** Planner checks trust/organic evidence; campaign handler has authority checks but currently refuses live execution because integration is absent.
- **Required behavior:** Before any future protected spend, re-read current authority, trust, eligibility, listing state and budgets atomically enough to prevent stale-plan bypass.
- **Why current evidence is insufficient:** Current tests prove no spending, not safe live execution once adapter is added.
- **Smallest safe repair:** Keep refusal now; place full final-action guard adjacent to future adapter call, independent of plan validity.
- **Adversarial regression:** AT-G11. Setup: eligible plan, then revoke authority/trust, withdraw listing or exhaust budget. Act: queued campaign with a spy adapter. Assert: zero calls/spend for each; stale/direct jobs cannot bypass; permitted mock control reserves bounded budget once.
- **Required runtime trace:** Plan → queued command → current final guard → budget reservation → authorized adapter → recorded result.
- **Dependencies:** Orders commercial truth; Platform final gates

<a id="cb2-g12"></a>

## CB2-G12 — Experiment rank changes may only reorder the dashboard

- **Cluster / severity / timing:** Growth / Medium / AFTER
- **Classification:** coverage_gap; not executed; unresolved audit input.
- **Claude defects:** C-67
- **Requirements:** #264, #276
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/runtime/growth_ops.py::steer` — [preserved_patch:2160](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/growth.mbox#L2160)
  - `brambleloop/src/brambleloop/scale/war_room.py::board` — [preserved_patch:2662](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/growth.mbox#L2662)
- **Existing behavior:** steer_rank is consumed in board sorting; executor selection is not demonstrated.
- **Required behavior:** Continuous execution must consume the selected constraint/rank without weakening experiment gates.
- **Why current evidence is insufficient:** Test reads flight/board order, not the next experiment actually run.
- **Smallest safe repair:** Connect existing experiment dispatcher to validated rank or report display-only until connected.
- **Adversarial regression:** AT-G12. Setup: two eligible experiments with opposite created/rank ordering and one ineligible top-ranked. Act: normal dispatcher. Assert: eligible ranked experiment is actually selected, ineligible remains blocked, selection audited.
- **Required runtime trace:** Constraint reading → durable experiment priority → executor selection → allowed experiment action.
- **Dependencies:** Improve experiments/ownership

<a id="cb2-g13"></a>

## CB2-G13 — Ads eligibility countdown and credit/cash separation are absent

- **Cluster / severity / timing:** Growth / High / AFTER
- **Classification:** coverage_gap; not executed; unresolved audit input.
- **Claude defects:** C-70, C-67
- **Requirements:** #242, #243, #294, #295 — Owner-retained Etsy Ads eligibility/countdown and credit/cash requirement; IDs identify related existing ads scope, not an invented numbered requirement.
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/runtime/growth_ops.py::ads_plan` — [preserved_patch:1337](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/growth.mbox#L1337)
  - `brambleloop/src/brambleloop/runtime/growth_ops.py::handle_ads_adjust` — [preserved_patch:1450](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/growth.mbox#L1450)
  - `brambleloop/src/brambleloop/runtime/growth_ops.py::ad_authority` — [preserved_patch:1239](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/growth.mbox#L1239)
- **Existing behavior:** Saved patches contain ad planning but no shop waiting-period expiry recheck or Etsy Plus credit/cash separation.
- **Required behavior:** Retain the owner's explicit countdown requirement using verified current shop evidence; no invented date or spend.
- **Why current evidence is insufficient:** No matching implementation in the preserved series; not a new numbered master requirement.
- **Smallest safe repair:** Within Marketing scope, persist verified eligibility state/date/source, schedule idempotent recheck on expiry, prepare plans beforehand and distinguish credit/cash accounting.
- **Adversarial regression:** AT-G13. Setup: verified future eligibility event and credit balance, with source unavailable on expiry. Act: cadence before/at/after date and restart. Assert: preparation occurs, recheck queued once per due observation, unavailable source remains unknown, no automatic spend and no credit counted as cash.
- **Required runtime trace:** Verified shop state → durable eligibility deadline → scheduler recheck → current eligibility + spend governor → campaign admission.
- **Dependencies:** Owner/shop evidence; Platform scheduler; Orders finance

<a id="cb2-d01"></a>

## CB2-D01 — Winner judgement contract lacks a proven production writer

- **Cluster / severity / timing:** Design / High / BEFORE
- **Classification:** coverage_gap; not executed; unresolved audit input.
- **Claude defects:** C-61, C-67
- **Requirements:** #88, #115, #277, #278, #281
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/creative/intake.py::judgement_for` — [preserved_patch:395](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/design.mbox#L395)
  - `brambleloop/src/brambleloop/creative/intake.py::intake` — [preserved_patch:757](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/design.mbox#L757)
  - `brambleloop/src/brambleloop/creative/preengineering.py::gate_concept` — [preserved_patch:1106](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/design.mbox#L1106); [preserved_patch:2710](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/intel.mbox#L2710)
- **Existing behavior:** Intake consumes named concept judgement evidence that tests inject; all required quality judgements lack a demonstrated normal producer.
- **Required behavior:** Actual judge jobs must emit hash-bound, named, independent evidence for every mandatory check; absence holds engineering.
- **Why current evidence is insufficient:** A fake judge record proves consumption only; grid evidence cannot silently substitute craft assessment.
- **Smallest safe repair:** Trace/add the narrow missing producer or retain explicit hold; connect result arrival to reconsideration.
- **Adversarial regression:** AT-D01. Setup: normal tournament winner with no handcrafted judgement rows. Act: scheduled judgement path then intake. Assert: holds while missing; genuine job output with matching concept hash permits only the checks it actually measured.
- **Required runtime trace:** Tournament winner → judge task → durable provenance → intake/gate → CIR admission/refusal.
- **Dependencies:** Intel I02/I03; model/image gates

<a id="cb2-d02"></a>

## CB2-D02 — Reconsideration misses changed prerequisite evidence

- **Cluster / severity / timing:** Design / Medium / BEFORE
- **Classification:** risk_requires_reproduction; not executed; unresolved audit input.
- **Claude defects:** C-61, C-67
- **Requirements:** #88, #125, #126, #277
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/creative/intake.py::regate_held` — [preserved_patch:865](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/design.mbox#L865)
  - `brambleloop/src/brambleloop/creative/intake.py::judgement_for` — [preserved_patch:395](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/design.mbox#L395)
- **Existing behavior:** Held-winner reconsideration observes a limited set of judgement changes.
- **Required behavior:** Any relevant new grid/top-decile/capability evidence should trigger bounded idempotent reconsideration.
- **Why current evidence is insufficient:** One injected thumbnail/craft change does not cover other gate inputs.
- **Smallest safe repair:** Track dependency fingerprints/version or enqueue reconsideration on validated prerequisite changes.
- **Adversarial regression:** AT-D02. Setup: held winner, unchanged craft/thumbnail, new valid grid result then changed capability evidence. Act: normal cadence/result event twice. Assert: reconsidered once for each changed dependency, no engineering when still blocked, no polling loop.
- **Required runtime trace:** Gate dependency change → durable version → reconsideration job → full gate → at-most-once engineering.
- **Dependencies:** Intel judgement/board; Platform scheduling

<a id="cb2-d03"></a>

## CB2-D03 — Gap progression can attach to the wrong arena

- **Cluster / severity / timing:** Design / High / BEFORE
- **Classification:** confirmed_static; not executed; unresolved audit input.
- **Claude defects:** C-61, C-67
- **Requirements:** #314, #309, #215
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/creative/intake.py::_gap_for` — [preserved_patch:716](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/design.mbox#L716)
  - `brambleloop/src/brambleloop/creative/intake.py::advance_gap` — [preserved_patch:727](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/design.mbox#L727)
  - `brambleloop/src/brambleloop/intel/mission_runtime.py::consume_concepting` — [preserved_patch:327](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/intel.mbox#L327)
- **Existing behavior:** Gap lookup can use first gap in a pod rather than exact originating gap/event.
- **Required behavior:** Carry exact gap, event, arena and winning design identity through every stage.
- **Why current evidence is insufficient:** A fixture with one gap per pod cannot reveal wrong provenance.
- **Smallest safe repair:** Propagate explicit IDs in job inputs and validate their relationship; refuse ambiguous fallback.
- **Adversarial regression:** AT-D03. Setup: two gaps in same pod, distinct arenas/events. Act: engineer winner from second event. Assert: only second gap advances; replay/other winner cannot overwrite first; missing identity is held.
- **Required runtime trace:** CoverageGap/event → tournament input → winner intake → CIR/certification → exact gap progression.
- **Dependencies:** Intel same-arena producer; Orders outcomes

<a id="cb2-d04"></a>

## CB2-D04 — Pipeline report advances on artifact or listing existence

- **Cluster / severity / timing:** Design / High / BEFORE
- **Classification:** confirmed_static; not executed; unresolved audit input.
- **Claude defects:** C-67, C-60
- **Requirements:** #309, #281, #318
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/intel/mission_runtime.py::_stage_evidence` — [preserved_patch:1819](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/design.mbox#L1819)
  - `brambleloop/src/brambleloop/intel/mission_runtime.py::advance_pipeline` — [preserved_patch:1896](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/design.mbox#L1896)
  - `brambleloop/src/brambleloop/intel/mission_runtime.py::_challenge_for` — [preserved_patch:1885](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/design.mbox#L1885)
- **Existing behavior:** Asset rows and listing existence can satisfy stages without approved current release evidence; full scaling/lessons tail is absent.
- **Required behavior:** Each stage must have the required result and consumer for that exact release; missing terminal stages remain incomplete.
- **Why current evidence is insufficient:** Report-field/stopped-stage assertions cannot prove quality or full lifecycle execution.
- **Smallest safe repair:** Replace existence predicates with stage-specific provenance/verdict checks; add missing tail only within assigned scope.
- **Adversarial regression:** AT-D04. Setup: rejected assets, old approved version, draft lacking SEO, challenge with no score. Act: pipeline advancement. Assert: no false completed stages; valid release progresses only through actually executed stages; scaling/lessons not fabricated.
- **Required runtime trace:** Winner → certified current release → approved artifacts → SEO/challenge → authorized launch → measurement → scaling/lesson consumers.
- **Dependencies:** Platform artifacts; Intel progression; Growth execution

<a id="cb2-d05"></a>

## CB2-D05 — Draft age can become launch-failure evidence

- **Cluster / severity / timing:** Design / High / BEFORE
- **Classification:** confirmed_static; not executed; unresolved audit input.
- **Claude defects:** C-66
- **Requirements:** #316, #318
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/intel/mission_runtime.py::response_outcomes` — [preserved_patch:1961](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/design.mbox#L1961)
  - `brambleloop/src/brambleloop/creative/intake.py::response_lesson` — [preserved_patch:926](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/design.mbox#L926)
- **Existing behavior:** Failure timing can use Listing.created_at rather than publication/exposure.
- **Required behavior:** No launch failure without verified launch age and sufficient observable opportunity; source absence differs from zero sales.
- **Why current evidence is insufficient:** Fixture with old listings does not distinguish draft age from live exposure.
- **Smallest safe repair:** Use publication/exposure events and source completeness; keep unsold/unlaunched/unknown outcomes distinct.
- **Adversarial regression:** AT-D05. Setup: 90-day draft published today, never-published draft, old published listing with no source, measured old published failure. Act: response learning. Assert: only last can supply measured failure; no false negative lesson.
- **Required runtime trace:** Publication + exposure/order evidence → response outcome → pod lesson/challenger → future selection.
- **Dependencies:** Orders O10; Growth traffic

<a id="cb2-d06"></a>

## CB2-D06 — Seller language is labelled buyer evidence

- **Cluster / severity / timing:** Design / Medium / BEFORE
- **Classification:** confirmed_static; not executed; unresolved audit input.
- **Claude defects:** C-66
- **Requirements:** #293
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/creative/intake.py::buyer_language` — [preserved_patch:564](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/design.mbox#L564)
  - `brambleloop/src/brambleloop/commerce/intent.py::map_product` — [preserved_patch:1596](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/design.mbox#L1596)
  - `brambleloop/src/brambleloop/runtime/release.py::handle_listing_seo` — [preserved_patch:2318](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/platform.mbox#L2318); [preserved_patch:2575](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/growth.mbox#L2575); [preserved_patch:2200](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/design.mbox#L2200); [preserved_patch:3547](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/improve.mbox#L3547); [checkpoint_source:433](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/src/brambleloop/runtime/release.py#L433)
- **Existing behavior:** Observed seller listing-title phrases feed buyer-language claims.
- **Required behavior:** Distinguish seller wording from measured buyer queries; preserve source and population.
- **Why current evidence is insufficient:** Observed tags in a draft prove transfer, not buyer demand.
- **Smallest safe repair:** Label source accurately and use buyer-query evidence when available; do not upgrade seller text to measured demand.
- **Adversarial regression:** AT-D06. Setup: phrase only in competitor title, different phrase in authorized query export. Act: SEO mapping. Assert: provenance distinguishes both, unsupported demand remains unmeasured, truth/skill guards remain.
- **Required runtime trace:** Seller/query observations → source-qualified intent map → SEO selection → published claims gate.
- **Dependencies:** Growth statistics ingestion; Intel provenance

<a id="cb2-d07"></a>

## CB2-D07 — Breakthrough and cardigan end-to-end scope remains unfinished

- **Cluster / severity / timing:** Design / High / AFTER
- **Classification:** coverage_gap; not executed; unresolved audit input.
- **Claude defects:** C-61, C-67
- **Requirements:** #279, #282, #308, #309
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/creative/intake.py::intake` — [preserved_patch:757](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/design.mbox#L757)
  - `brambleloop/src/brambleloop/runtime/release.py::handle_creative_tournament` — [preserved_patch:1257](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/design.mbox#L1257); [preserved_patch:430](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/intel.mbox#L430); [checkpoint_source:2686](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/src/brambleloop/runtime/release.py#L2686)
  - `brambleloop/src/brambleloop/intel/mission_runtime.py::advance_pipeline` — [preserved_patch:1896](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/design.mbox#L1896)
- **Existing behavior:** Saved cardigan test ends with no prototype winner/CIR; other breakthrough variants lack demonstrated completed chain.
- **Required behavior:** Implement the specified design/engineering/visual progression or retain exact honest blocker; do not rename a stopped-path test success as product completion.
- **Why current evidence is insufficient:** Negative-path test proves safe refusal only; Intel's new briefs do not prove viable engineering.
- **Smallest safe repair:** Continue assigned missing generator/prototype capability with existing gates intact; validate a real eligible product through full chain.
- **Adversarial regression:** AT-D07. Setup: specified cardigan/breakthrough brief and available prerequisites. Act: normal upstream workflow, without directly inserting winner/artifact rows. Assert: either genuine downstream product evidence passes all gates or report names exact unfinished capability; never a completion claim on refusal.
- **Required runtime trace:** Observed opportunity → generated brief → viable prototype → CIR → certification → finished-product visual chain → validated output.
- **Dependencies:** Intel briefs/references; Platform provenance; external Visual blocker

<a id="cb2-d08"></a>

## CB2-D08 — Funnel evidence must bind the actual concept payload

- **Cluster / severity / timing:** Design / Medium / BEFORE
- **Classification:** risk_requires_reproduction; not executed; unresolved audit input.
- **Claude defects:** C-61
- **Requirements:** #3, #277, #281
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/creative/intake.py::verify_funnel` — [preserved_patch:854](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/design.mbox#L854)
  - `brambleloop/src/brambleloop/runtime/pipeline.py::handle_cir_draft` — [preserved_patch:1191](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/design.mbox#L1191)
- **Existing behavior:** Funnel lookup is slug-based; mutated payload reuse was not proved safe.
- **Required behavior:** Only the carried concept/version/hash may use its funnel evidence.
- **Why current evidence is insufficient:** Existing test blocks direct uncarried slug but not mutation under a carried identity.
- **Smallest safe repair:** Bind immutable concept/brief fingerprint to funnel and gate verdict; reject mismatched draft input.
- **Adversarial regression:** AT-D08. Setup: carried and judged concept A. Act: modify construction/brief while retaining slug and submit draft. Assert: no compile job; unchanged A control succeeds and audit binds fingerprints.
- **Required runtime trace:** Tournament evidence → immutable concept identity → draft validation → CIR admission.
- **Dependencies:** Intel/Improve brief modifications

<a id="cb2-m01"></a>

## CB2-M01 — Rollback state commits before rollback effect

- **Cluster / severity / timing:** Improve / Critical / BEFORE
- **Classification:** confirmed_static; not executed; unresolved audit input.
- **Claude defects:** C-62, C-63
- **Requirements:** #93, #100, #164, #190
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/improve/runner.py::monitor_trials` — [preserved_patch:1358](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/improve.mbox#L1358)
  - `brambleloop/src/brambleloop/improve/replay.py::rollback` — [preserved_patch:943](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/improve.mbox#L943)
  - `brambleloop/src/brambleloop/improve/runner.py::_rollback_self_audit` — [preserved_patch:1134](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/improve.mbox#L1134)
- **Existing behavior:** cells.revert commits REVERTED before ROLLBACKS executes; next scan selects PROMOTED only.
- **Required behavior:** After failure/restart, rollback remains pending until the active configuration/floor is restored and verified.
- **Why current evidence is insufficient:** Successful rollback fixture omits failure between state and side effect.
- **Smallest safe repair:** Use durable rollback_pending/attempt evidence and idempotent executor; commit completion only after verified effect; retain incident until resolved.
- **Adversarial regression:** AT-M01. Setup: promoted bad policy and adopted floor. Act: fail/kill before revert, after state update, during rollback and after effect before receipt; restart and monitor twice. Assert: safe config/floor restored, pending work retried, no false completed rollback or duplicate harmful effect.
- **Required runtime trace:** Fresh regression evidence → durable rollback request → idempotent rollback executor → verified active state → completion audit.
- **Dependencies:** Platform queue/recovery and withholding

<a id="cb2-m02"></a>

## CB2-M02 — Replay model differs from multi-worker runtime

- **Cluster / severity / timing:** Improve / High / DURING
- **Classification:** confirmed_static; not executed; unresolved audit input.
- **Claude defects:** C-63, C-68
- **Requirements:** #95, #180, #187, #190
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/improve/replay.py::historical_jobs` — [preserved_patch:528](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/improve.mbox#L528)
  - `brambleloop/src/brambleloop/improve/replay.py::simulate_day` — [preserved_patch:567](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/improve.mbox#L567)
  - `brambleloop/src/brambleloop/improve/replay.py::replay` — [preserved_patch:609](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/improve.mbox#L609)
  - `brambleloop/src/brambleloop/swarm/capacity.py::share_decision` — [preserved_patch:1593](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/platform.mbox#L1593)
- **Existing behavior:** Single-worker daily simulation omits actual pool/lane behavior; unknown durations default and DEAD jobs can lose failure meaning; current proof can leak into history.
- **Required behavior:** Replay claims must be scoped to faithfully simulated behavior; promotion must preserve protected bands and account for actual worker/lane semantics.
- **Why current evidence is insufficient:** A synthetic winning schedule proves simulator consistency, not production benefit.
- **Smallest safe repair:** Version the simulator assumptions; preserve failure/backlog/duration uncertainty and historical knowledge; compare against actual queue semantics before promotion.
- **Adversarial regression:** AT-M02. Setup: multi-day backlog, two lanes/pool three, failed jobs, missing durations, product proven only later. Act: replay and deterministic worker harness on same tasks. Assert: mismatch blocks production-benefit claim; no future-knowledge leakage or failure-as-success.
- **Required runtime trace:** Historical task snapshot → versioned faithful evaluator → shared holdout → promotion decision → actual priority/runtime observation.
- **Dependencies:** Platform P09; Growth G02

<a id="cb2-m03"></a>

## CB2-M03 — New replay record can be mistaken for fresh post-promotion evidence

- **Cluster / severity / timing:** Improve / High / BEFORE
- **Classification:** confirmed_static; not executed; unresolved audit input.
- **Claude defects:** C-63
- **Requirements:** #93, #95, #179, #180, #193
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/improve/replay.py::cycle` — [preserved_patch:745](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/improve.mbox#L745)
  - `brambleloop/src/brambleloop/improve/replay.py::_latest_pair` — [preserved_patch:852](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/improve.mbox#L852)
  - `brambleloop/src/brambleloop/improve/replay.py::monitor` — [preserved_patch:909](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/improve.mbox#L909)
- **Existing behavior:** Run timestamp after promotion may refer to unchanged historical tasks; identity uses coarse window/count evidence.
- **Required behavior:** Freshness must bind task identities/content/windows and independent post-promotion outcomes; reused holdout is not fresh evidence.
- **Why current evidence is insufficient:** Test inserts a later run but does not prove underlying task freshness.
- **Smallest safe repair:** Record dataset fingerprint and observation bounds; distinguish repeated evaluation from new evidence; preserve holdout isolation.
- **Adversarial regression:** AT-M03. Setup: promote on dataset D. Act: rerecord D after promotion, alter contents preserving count/window, then add disjoint new observations. Assert: first two cannot claim fresh production uplift; dataset changes detected; only valid new evidence supports monitoring.
- **Required runtime trace:** Task dataset/version → immutable replay evidence → freshness check → hold/revert/ROI decision.
- **Dependencies:** Orders/Platform event provenance

<a id="cb2-m04"></a>

## CB2-M04 — Registered test filenames are not test execution provenance

- **Cluster / severity / timing:** Improve / High / BEFORE
- **Classification:** confirmed_static; not executed; unresolved audit input.
- **Claude defects:** C-60, C-67
- **Requirements:** #96
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/improve/bootstrap.py::register_code_versions` — [preserved_patch:4113](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/improve.mbox#L4113)
  - `brambleloop/src/brambleloop/improve/bootstrap.py::_policy_payloads` — [preserved_patch:4089](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/improve.mbox#L4089)
- **Existing behavior:** Version registration populates tests_run from static filename tuples without running tests.
- **Required behavior:** Separate declared validation coverage from actual executed result tied to source/environment.
- **Why current evidence is insufficient:** Test asserts metadata presence, not execution.
- **Smallest safe repair:** Rename/structure declared tests and attach real run IDs only when observed; never synthesize passed tests.
- **Adversarial regression:** AT-M04. Setup: change compiler source, do not run tests, then attach a failing and a passing run on different hashes. Act: registration/proof view. Assert: declared coverage not PASS; only matching executed result counts.
- **Required runtime trace:** Source/config hash → registry version → actual test-run artifact → review/promotion proof.
- **Dependencies:** All integration validation

<a id="cb2-m05"></a>

## CB2-M05 — Lesson matches receive invented currency-valued priority

- **Cluster / severity / timing:** Improve / Medium / BEFORE
- **Classification:** confirmed_static; not executed; unresolved audit input.
- **Claude defects:** C-66
- **Requirements:** #97, #147, #187
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/runtime/pipeline.py::handle_radar_score` — [preserved_patch:3487](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/improve.mbox#L3487); [preserved_patch:1356](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/intel.mbox#L1356)
  - `brambleloop/src/brambleloop/improve/consume.py::act` — [preserved_patch:3053](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/improve.mbox#L3053)
- **Existing behavior:** Each matching engineering lesson can add fixed CAD value; acted_on can describe a nudge without demonstrated benefit.
- **Required behavior:** Heuristic priority must not appear as measured expected business value or realized learning benefit.
- **Why current evidence is insufficient:** Score-change and acted-on assertions do not establish monetary value or improved outcome.
- **Smallest safe repair:** Represent lesson priority as bounded heuristic reason; reserve currency fields for sourced estimates with uncertainty; record effect separately.
- **Adversarial regression:** AT-M05. Setup: multiple identical/redundant lessons and no sales evidence. Act: radar/draft priority. Assert: no fabricated CAD return, deduped bounded heuristic, no measured compounding benefit merely for writing acted_on.
- **Required runtime trace:** Lesson → bounded decision input → actual changed work → observed outcome → qualified learning credit.
- **Dependencies:** Growth priority; Orders outcomes

<a id="cb2-m06"></a>

## CB2-M06 — Adopting an audit floor does not implement the underlying improvement

- **Cluster / severity / timing:** Improve / High / AFTER
- **Classification:** coverage_gap; not executed; unresolved audit input.
- **Claude defects:** C-62, C-67
- **Requirements:** #153, #154, #155, #156, #157, #158, #159, #160, #164
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/improve/runner.py::trial_self_audit` — [preserved_patch:1042](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/improve.mbox#L1042)
  - `brambleloop/src/brambleloop/improve/runner.py::_execute_self_audit` — [preserved_patch:1094](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/improve.mbox#L1094)
  - `brambleloop/src/brambleloop/teardown/enforce.py::adopt_floor` — [preserved_patch:2248](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/improve.mbox#L2248)
  - `brambleloop/src/brambleloop/teardown/enforce.py::apply_pattern_help` — [preserved_patch:3978](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/improve.mbox#L3978)
- **Existing behavior:** A better self-audit can promote a floor; support obligations can be attached without proof the artifact/reply changes.
- **Required behavior:** Trace proposal to a specific implemented change, independent reevaluation and actual consuming artifact/response.
- **Why current evidence is insufficient:** Seeded better audits and attached obligations can bypass the missing improvement executor.
- **Smallest safe repair:** Separate standard adoption from implementation; connect existing artifact/support generators to explicit obligations and record actual changed output.
- **Adversarial regression:** AT-M06. Setup: teardown trap, unchanged PDF/reply and manually higher score. Act: sandbox and support generation. Assert: no claim that trap was repaired until changed bytes/text and independent measurement exist; refusal remains when obligation unmet.
- **Required runtime trace:** Benchmark finding → concrete change proposal → changed artifact/reply → independent self-audit → adoption/publish gate.
- **Dependencies:** Platform current-release evidence; Intel benchmarks

<a id="cb2-m07"></a>

## CB2-M07 — Self-audits and keyword checks can certify wrong content

- **Cluster / severity / timing:** Improve / High / BEFORE
- **Classification:** confirmed_static; not executed; unresolved audit input.
- **Claude defects:** C-66, C-67
- **Requirements:** #153, #154, #155, #156, #158, #159, #160, #220
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/teardown/enforce.py::our_scores` — [preserved_patch:2115](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/improve.mbox#L2115)
  - `brambleloop/src/brambleloop/teardown/enforce.py::support_text_evidence` — [preserved_patch:2149](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/improve.mbox#L2149)
  - `brambleloop/src/brambleloop/teardown/enforce.py::_judge` — [preserved_patch:2159](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/improve.mbox#L2159)
  - `brambleloop/src/brambleloop/teardown/enforce.py::check` — [preserved_patch:2187](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/improve.mbox#L2187)
- **Existing behavior:** Self scores use brambleloop:<slug>; support text presence can substitute semantic clarity.
- **Required behavior:** Bind audits to release/content hashes and compare applicable benchmark scope; keyword presence alone cannot prove correctness.
- **Why current evidence is insufficient:** Tests add scores for slug and known keywords without changed-release or misleading-text negatives.
- **Smallest safe repair:** Invalidate self-audits on dependency changes and distinguish structural keyword checks from independent semantic evidence.
- **Adversarial regression:** AT-M07. Setup: passing v1 audit, materially changed v2; misleading support text containing expected keywords; unrelated benchmark category. Act: publish gates. Assert: old audit/keywords cannot clear v2; applicable evidence required.
- **Required runtime trace:** Exact artifact+benchmark evidence → scoped obligation evaluation → durable verdict → final publication block/allow.
- **Dependencies:** Platform P04/P05; Intel benchmark provenance

<a id="cb2-m08"></a>

## CB2-M08 — Taste and function-quality heuristics overstate independent quality

- **Cluster / severity / timing:** Improve / Medium / BEFORE
- **Classification:** confirmed_static; not executed; unresolved audit input.
- **Claude defects:** C-66
- **Requirements:** #129, #174, #179
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/creative/standard.py::taste_judge` — [preserved_patch:2873](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/improve.mbox#L2873)
  - `brambleloop/src/brambleloop/swarm/orchestrate.py::function_quality` — [preserved_patch:3752](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/improve.mbox#L3752)
  - `brambleloop/src/brambleloop/improve/roles.py::activity_from_db` — [preserved_patch:3383](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/improve.mbox#L3383)
- **Existing behavior:** Common pairings/novelty margins label taste; function metrics use broad row counts and role attribution proxies.
- **Required behavior:** Label screening heuristics and evidence limits; reward observed quality/outcomes rather than row production.
- **Why current evidence is insufficient:** Fixture categories prove deterministic filters, not elite taste or role-caused uplift.
- **Smallest safe repair:** Retain useful filters but separate heuristic judgement from independent evaluation and attributable realized outcomes.
- **Adversarial regression:** AT-M08. Setup: technically distinct but poor concept, many rejected/duplicate outputs, role unrelated to improvement. Act: quality/role review. Assert: no independent taste or realized-uplift claim from proxy counts; adverse outcomes remain visible.
- **Required runtime trace:** Function output → qualified independent evaluation → attributable outcome → agent quality decision.
- **Dependencies:** Design judgement; Orders commercial outcomes

<a id="cb2-m09"></a>

## CB2-M09 — Priority-policy replay is not a general challenger engine

- **Cluster / severity / timing:** Improve / High / AFTER
- **Classification:** coverage_gap; not executed; unresolved audit input.
- **Claude defects:** C-62, C-63, C-67
- **Requirements:** #90, #95, #180, #190, #193, #194
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/improve/replay.py::cycle` — [preserved_patch:745](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/improve.mbox#L745)
  - `brambleloop/src/brambleloop/runtime/release.py::handle_nightly_improvement` — [preserved_patch:4641](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/improve.mbox#L4641); [checkpoint_source:3351](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/src/brambleloop/runtime/release.py#L3351)
  - `brambleloop/src/brambleloop/improve/evolution.py::additions` — [preserved_patch:3214](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/improve.mbox#L3214)
  - `brambleloop/src/brambleloop/improve/evolution.py::route_owner_card` — [preserved_patch:3335](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/improve.mbox#L3335)
- **Existing behavior:** Actual replay covers job-priority configurations; other versions and specialist additions can be metadata/owner cards.
- **Required behavior:** State implemented challenger scope accurately; model/tool evaluation and approved architecture execution need their own real paths.
- **Why current evidence is insufficient:** Seven run rows or queued owner cards do not prove all challenger types or agent creation.
- **Smallest safe repair:** Keep narrow capability claim; complete genuinely assigned remaining executor/evaluator paths without automatic permissions expansion.
- **Adversarial regression:** AT-M09. Setup: priority, prompt, model and tool challengers plus specialist proposal. Act: nightly/weekly cadence. Assert: only actually evaluated/executed kinds report outcomes; others name exact prerequisite and remain incomplete/gated.
- **Required runtime trace:** Proposal/config kind → supported evaluator → evidence → approved execution → observed changed runtime.
- **Dependencies:** Platform runtime; owner permissions/funding

<a id="cb2-m10"></a>

## CB2-M10 — Veto withholding must survive all rebuild paths

- **Cluster / severity / timing:** Improve / High / DURING
- **Classification:** risk_requires_reproduction; not executed; unresolved audit input.
- **Claude defects:** C-67, C-69
- **Requirements:** #228, #163, #172
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/runtime/pipeline.py::handle_certify` — [preserved_patch:2190](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/platform.mbox#L2190); [preserved_patch:1922](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/orders.mbox#L1922); [preserved_patch:1548](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/improve.mbox#L1548)
  - `brambleloop/src/brambleloop/runtime/pipeline.py::_mark_withheld` — [preserved_patch:2204](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/platform.mbox#L2204)
  - `brambleloop/src/brambleloop/runtime/release.py::handle_chain_rebuild` — [preserved_patch:2517](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/platform.mbox#L2517); [checkpoint_source:2315](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/src/brambleloop/runtime/release.py#L2315)
  - `brambleloop/src/brambleloop/publish/release_gates.py::standards_gate` — [preserved_patch:1478](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/improve.mbox#L1478)
- **Existing behavior:** Improve audits and returns withheld on veto; Platform separately persists certificate withholding for other gates.
- **Required behavior:** One durable release eligibility record must represent all withholding reasons and all downstream paths must consume it.
- **Why current evidence is insufficient:** A direct publish refusal test does not prove hourly/targeted rebuild respects veto state.
- **Smallest safe repair:** Reconcile durable withholding reasons; re-evaluate all reasons before clearing, never overwrite one reason with another.
- **Adversarial regression:** AT-M10. Setup: owner veto plus failed comparative gate; certify, restart, hourly/targeted rebuild and direct draft/publish. Act: lift only one reason. Assert: no bypass and other reason retained; lift both permits only normal gated flow.
- **Required runtime trace:** Owner ruling + all gate results → durable release eligibility → draft/rebuild/asset/publish consumers → refusal.
- **Dependencies:** Platform P04/P10; Intel policy/photo gates

<a id="cb2-i01"></a>

## CB2-I01 — Repeated unchanged policy snapshot erases unreviewed change

- **Cluster / severity / timing:** Intel / Critical / BEFORE
- **Classification:** confirmed_static; not executed; unresolved audit input.
- **Claude defects:** C-71, C-67
- **Requirements:** #39
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/gates/platform_policy.py::record_snapshot` — [preserved_patch:2287](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/intel.mbox#L2287)
  - `brambleloop/src/brambleloop/gates/platform_policy.py::unreviewed_changes` — [preserved_patch:2294](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/intel.mbox#L2294)
  - `brambleloop/src/brambleloop/gates/platform_policy.py::review_change` — [preserved_patch:2315](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/intel.mbox#L2315)
  - `brambleloop/src/brambleloop/runtime/release.py::handle_policy_watch` — [preserved_patch:2408](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/intel.mbox#L2408); [checkpoint_source:2457](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/src/brambleloop/runtime/release.py#L2457)
- **Existing behavior:** Only latest snapshot is examined; A→B sets changed, B→B sets false and can resolve block without review.
- **Required behavior:** Unreviewed material change remains blocking until review/test evidence covers the effective changed version.
- **Why current evidence is insufficient:** Test covers A→B→explicit review, not A→B→B.
- **Smallest safe repair:** Track unresolved change by source/digest lineage, carrying it across identical readings; bind review to digest and tested evidence.
- **Adversarial regression:** AT-I01. Setup: A baseline, B changed, identical B reread. Act: policy watch and publish/new-class checks after each. Assert: block persists without review; A→B→review(B) clears only B; later C blocks again; review(A) cannot clear B.
- **Required runtime trace:** Policy snapshot → durable unresolved change → incident/gate → final protected action → refusal until matching review.
- **Dependencies:** Platform closure; Improve release eligibility

<a id="cb2-i02"></a>

## CB2-I02 — Distinctiveness is substituted for top-decile strength

- **Cluster / severity / timing:** Intel / High / BEFORE
- **Classification:** confirmed_static; not executed; unresolved audit input.
- **Claude defects:** C-66, C-71
- **Requirements:** #125, #129
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/creative/strength.py::concept_score` — [preserved_patch:2799](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/intel.mbox#L2799)
  - `brambleloop/src/brambleloop/creative/strength.py::benchmark_scores` — [preserved_patch:2793](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/intel.mbox#L2793)
  - `brambleloop/src/brambleloop/creative/preengineering.py::_top_decile` — [preserved_patch:1108](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/design.mbox#L1108); [preserved_patch:2681](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/intel.mbox#L2681)
- **Existing behavior:** Closed-vocabulary difference score can pass top-decile check when judged strength is absent.
- **Required behavior:** Measure required concept/presentation strength comparably on current category evidence; rarity is only one input.
- **Why current evidence is insufficient:** Test asserts the proxy pass rather than independent validity.
- **Smallest safe repair:** Retain distinctiveness as labelled feature; do not use it to clear unmet presentation/strength judgement; obtain independent compatible scores.
- **Adversarial regression:** AT-I02. Setup: rare but incoherent/poorly presented concept against current benchmark cards. Act: pre-engineering gate without and with genuine judged scores. Assert: rarity alone cannot clear; comparable independent evidence drives verdict.
- **Required runtime trace:** Concept+current benchmarks → independent compatible judgement → provenance → top-decile gate → engineering admission.
- **Dependencies:** Design D01; Improve taste

<a id="cb2-i03"></a>

## CB2-I03 — Fabric swatch does not prove finished-product visual fidelity

- **Cluster / severity / timing:** Intel / High / BEFORE
- **Classification:** confirmed_static; not executed; unresolved audit input.
- **Claude defects:** C-61, C-71
- **Requirements:** #126, #308, #309
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/creative/board.py::make_board` — [preserved_patch:2644](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/intel.mbox#L2644)
  - `brambleloop/src/brambleloop/creative/preengineering.py::gate_concept` — [preserved_patch:1106](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/design.mbox#L1106); [preserved_patch:2710](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/intel.mbox#L2710)
- **Existing behavior:** Board renders capped prototype fabric raster, crops square and resizes; silhouette/assembly not established.
- **Required behavior:** Treat swatch as material evidence only; preserve CIR→faithful finished-product 3D reference→photoreal image→truth/benchmark validation objective.
- **Why current evidence is insufficient:** Artifact hash and grid job existence do not prove finished object.
- **Smallest safe repair:** Label artifact scope and prevent swatch from satisfying full-object checks; use actual supported geometry/reference pipeline or honest external hold.
- **Adversarial regression:** AT-I03. Setup: garment concept with same stitch fabric but different shaping/assembly. Act: board/grid and finished-product gate. Assert: swatch never establishes garment fidelity; real full-object control must match structural dimensions/details before downstream image acceptance.
- **Required runtime trace:** CIR → geometry/assembled reference → provenance-bound photoreal output → independent truth+benchmark comparison → release gate.
- **Dependencies:** Design prototype; Platform provenance; external Visual capability

<a id="cb2-i04"></a>

## CB2-I04 — Photo intake validates hash syntax and rights label, not evidence

- **Cluster / severity / timing:** Intel / High / BEFORE
- **Classification:** confirmed_static; not executed; unresolved audit input.
- **Claude defects:** C-71, C-67
- **Requirements:** #64
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/publish/physical_upgrade.py::intake` — [preserved_patch:2859](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/intel.mbox#L2859)
  - `brambleloop/src/brambleloop/runtime/release.py::_intake_photo` — [preserved_patch:3017](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/intel.mbox#L3017); [checkpoint_source](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/src/brambleloop/runtime/release.py)
  - `brambleloop/src/brambleloop/app/main.py::api_physical_photo` — [preserved_patch:2565](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/intel.mbox#L2565)
- **Existing behavior:** Any 64-hex value and accepted rights_basis string can enter upgrade path without verifying bytes/rights reference.
- **Required behavior:** Verify stored image bytes/hash, product/version association and recorded permission/license basis before use; retain held state otherwise.
- **Why current evidence is insufficient:** Test creates a hash-shaped reference and checks inserted row; no content or rights document proof.
- **Smallest safe repair:** Resolve content-addressed artifact, verify image/hash and bind rights evidence/source; no invented permission.
- **Adversarial regression:** AT-I04. Setup: nonexistent hash, mismatched bytes, corrupt image, revoked/missing rights, wrong product and valid control. Act: photo intake. Assert: invalid cases held/refused and no usable upgrade; valid evidence retained by hash/reference.
- **Required runtime trace:** Photo bytes + rights evidence → validated intake → durable photo provenance → upgrade admission.
- **Dependencies:** Platform artifacts; owner/tester/customer evidence

<a id="cb2-i05"></a>

## CB2-I05 — Photo planning stops before review/publication but starts impact clock

- **Cluster / severity / timing:** Intel / High / BEFORE
- **Classification:** confirmed_static; not executed; unresolved audit input.
- **Claude defects:** C-67
- **Requirements:** #64, #258
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/publish/physical_upgrade.py::plan_upgrade` — [preserved_patch:2904](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/intel.mbox#L2904)
  - `brambleloop/src/brambleloop/publish/physical_upgrade.py::measure_impact` — [preserved_patch:2953](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/intel.mbox#L2953)
  - `brambleloop/src/brambleloop/runtime/release.py::handle_physical_upgrade` — [preserved_patch:3048](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/intel.mbox#L3048); [checkpoint_source](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/src/brambleloop/runtime/release.py)
- **Existing behavior:** Unapproved proof row is added; upgrade_queued planning date starts before/after measurement without demonstrated review/publish chain.
- **Required behavior:** Upgrade lifecycle must progress through review, recertification and authorized publication; impact anchored to actual exposed version/time.
- **Why current evidence is insufficient:** Test proves unapproved frame and later seeded traffic, not that buyers saw it.
- **Smallest safe repair:** Queue existing gated review/rebuild path; retain separate planned/approved/published states and immutable publication event for measurement.
- **Adversarial regression:** AT-I05. Setup: valid intake, rejected asset, approved-but-unpublished asset, then authorized simulated publication. Act: impact reader before/after each. Assert: no impact claim before exposure; exact version and non-overlapping windows used; no live publish in test.
- **Required runtime trace:** Photo intake → review → listing-set recertification → final publication guard → exposure event → qualified impact reading.
- **Dependencies:** Platform P06/P10; Growth traffic; Design visual truth

<a id="cb2-i06"></a>

## CB2-I06 — Seller location opens a buyer-market evidence gate

- **Cluster / severity / timing:** Intel / High / BEFORE
- **Classification:** confirmed_static; not executed; unresolved audit input.
- **Claude defects:** C-71, C-66
- **Requirements:** #268, #38, #219
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/intel/panel_discovery.py::market_for` — [preserved_patch:879](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/intel.mbox#L879)
  - `brambleloop/src/brambleloop/intel/panel_discovery.py::discover` — [preserved_patch:950](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/intel.mbox#L950)
  - `brambleloop/src/brambleloop/intel/benchmarks.py::market_of` — [preserved_patch:719](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/intel.mbox#L719)
  - `brambleloop/src/brambleloop/build2/executor.py::_second_market_observed` — [preserved_patch:558](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/intel.mbox#L558); [checkpoint_source:406](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/src/brambleloop/build2/executor.py#L406)
  - `brambleloop/src/brambleloop/commerce/markets.py::whose_language_is_this` — [preserved_patch:574](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/intel.mbox#L574)
- **Existing behavior:** Shop location is stored as market and contributes to second-market gate.
- **Required behavior:** Distinguish seller geography from observed buyer/query population; no Canadian/global demand claim from seller address.
- **Why current evidence is insufficient:** Test registers a foreign shop and expects buyer-market gate open.
- **Smallest safe repair:** Store geography role/source explicitly; use relevant population evidence to satisfy market requirement, retaining useful seller diversity separately.
- **Adversarial regression:** AT-I06. Setup: UK seller serving US buyers and unknown buyer geography. Act: discover/scan and market gate. Assert: seller diversity visible, buyer market stays unknown; verified second buyer-population evidence alone can open relevant gate.
- **Required runtime trace:** Shop/query/buyer evidence → typed geography provenance → market reader → selection/gate decision.
- **Dependencies:** Platform #38; Design buyer-language

<a id="cb2-i07"></a>

## CB2-I07 — Drift incidents resolve when evidence ages out or becomes unreadable

- **Cluster / severity / timing:** Intel / High / BEFORE
- **Classification:** confirmed_static; not executed; unresolved audit input.
- **Claude defects:** C-67
- **Requirements:** #201
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/visual/drift_series.py::series` — [preserved_patch:3974](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/intel.mbox#L3974)
  - `brambleloop/src/brambleloop/visual/drift_series.py::run` — [preserved_patch:4032](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/intel.mbox#L4032)
- **Existing behavior:** Absent current gradual_drift resolves prior incident; batch count can be measurable despite insufficient readable dimensions.
- **Required behavior:** Unknown/expired evidence must not establish recovery; only sufficient comparable stable evidence can resolve drift.
- **Why current evidence is insufficient:** Tests cover rising share and too few batches without an existing incident.
- **Smallest safe repair:** Use explicit drifting/stable/unmeasured states per dimension; preserve unresolved incident on missingness, scoped to correct identity pack.
- **Adversarial regression:** AT-I07. Setup: open hair-drift incident. Act: age all evidence out; add three unreadable batches; then sufficient stable comparable batches. Assert: first two preserve hold and say unmeasured; only last may resolve by documented rule.
- **Required runtime trace:** Model-frame verdicts + pack/hash → durable series → incident state → final model-bearing publication gate.
- **Dependencies:** Platform review; Intel photo/model evidence

<a id="cb2-i08"></a>

## CB2-I08 — Benchmark-refresh trigger and purchased candidate can diverge

- **Cluster / severity / timing:** Intel / Medium / BEFORE
- **Classification:** confirmed_static; not executed; unresolved audit input.
- **Claude defects:** C-71, C-67
- **Requirements:** #165
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/intel/benchmark_refresh.py::assess` — [preserved_patch:1600](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/intel.mbox#L1600)
  - `brambleloop/src/brambleloop/intel/benchmark_refresh.py::_pick` — [preserved_patch:1576](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/intel.mbox#L1576)
- **Existing behavior:** Strong competitor trigger picks by pod, potentially from another seller; first-baseline no-ask prose conflicts with unconditionally generated leader triggers.
- **Required behavior:** Request must answer the actual trigger and accurately state baseline policy; avoid duplicate purchased information.
- **Why current evidence is insufficient:** Tests assert bounded asks/prices, not seller/format correspondence or first-run leader behavior.
- **Smallest safe repair:** Constrain selection by trigger identity/format and record rationale; align baseline rule and tests without broadening spend.
- **Adversarial regression:** AT-I08. Setup: new strong seller B, larger known seller A in same pod; first run includes strong leader. Act: assess. Assert: request, if allowed, targets evidence needed from B; baseline behavior explicit and bounded; duplicate info rejected.
- **Required runtime trace:** Observed trigger → scoped purchase selection → owner action with exact evidence/cap → owner-controlled acquisition.
- **Dependencies:** Improve teardown library; owner purchase

<a id="cb2-i09"></a>

## CB2-I09 — Company standing and entry superiority rely on capability/count proxies

- **Cluster / severity / timing:** Intel / High / BEFORE
- **Classification:** confirmed_static; not executed; unresolved audit input.
- **Claude defects:** C-66
- **Requirements:** #211, #215, #15
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/intel/mission_runtime.py::_our_dims` — [preserved_patch:163](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/intel.mbox#L163)
  - `brambleloop/src/brambleloop/intel/mission_runtime.py::entry_axes` — [preserved_patch:52](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/intel.mbox#L52)
  - `brambleloop/src/brambleloop/intel/serp.py::positioning` — [preserved_patch:1118](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/intel.mbox#L1118)
- **Existing behavior:** Approved images across versions can inflate coverage; compiler-wide size capability can be claimed for unbuilt specific products.
- **Required behavior:** Compare current applicable releases; separate potential engineering capability from demonstrated product advantage.
- **Why current evidence is insufficient:** Image-count and constant-size fixtures do not prove actual product quality or graded deliverables.
- **Smallest safe repair:** Filter current release/hash/roles and phrase capability as prospective until actual product evidence exists.
- **Adversarial regression:** AT-I09. Setup: obsolete approved frames, current rejected frames and ungraded concept with compiler support. Act: standing/entry selection. Assert: no inflated coverage or realized size superiority; prospective opportunity remains labelled.
- **Required runtime trace:** Current product evidence + comparable benchmark → scoped standing/entry decision → original design task.
- **Dependencies:** Design progression; Platform quality; Improve standards

<a id="cb2-i10"></a>

## CB2-I10 — Quote-token heuristics cover only explicit title forms

- **Cluster / severity / timing:** Intel / Medium / AFTER
- **Classification:** coverage_gap; not executed; unresolved audit input.
- **Claude defects:** C-66, C-67
- **Requirements:** #139
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/culture/engine.py::quote_tokens` — [preserved_patch:3184](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/intel.mbox#L3184)
  - `brambleloop/src/brambleloop/culture/engine.py::file_topic` — [preserved_patch:3211](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/intel.mbox#L3211)
- **Existing behavior:** Heuristics detect quoted spans/qualifiers and some exclaimed memes, not all protected dialogue/lyrics in real inputs.
- **Required behavior:** Do not infer comprehensive screening from limited token extraction; preserve existing rights gates and declared uncertainty.
- **Why current evidence is insufficient:** One catchphrase fixture proves that example only.
- **Smallest safe repair:** Extend evidence-driven token declaration/consumer coverage where actual source contains protected text; keep uncertain copy held for existing review.
- **Adversarial regression:** AT-I10. Setup: explicit quote, unqualified known source phrase, song-title-only input and generic phrase controls. Act: filing then real copy screen. Assert: supported tokens reach screen; missing evidence is not blanket clearance; no new arbitrary legal threshold.
- **Required runtime trace:** Source topic/content → protected-token evidence → copy consumer → rights gate → refusal/review.
- **Dependencies:** Design generated copy; Growth content

<a id="cb2-i11"></a>

## CB2-I11 — Registry reclassification is not in the preserved patch

- **Cluster / severity / timing:** Intel / High / AFTER
- **Classification:** coverage_gap; not executed; unresolved audit input.
- **Claude defects:** C-71
- **Requirements:** #86, #203, #226, #300, #304
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/build2/executor.py::gate_for` — [checkpoint_source:788](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/src/brambleloop/build2/executor.py#L788)
  - `brambleloop/src/brambleloop/build2/closure.py::classify` — [preserved_patch:38](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/platform.mbox#L38)
  - `brambleloop/src/brambleloop/build2/requirements.json::86,203,226,300,304` — [checkpoint_source](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/src/brambleloop/build2/requirements.json)
  - `brambleloop/tests/test_executor.py::_parked_on_image_generation` — [preserved_patch:2457](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/intel.mbox#L2457)
- **Existing behavior:** No saved requirements.json edits implement claimed reclassification; synthetic gate fixture tests mechanics only.
- **Required behavior:** Integrator alone reconciles genuine parks after built-half proof; do not restore obsolete parks to satisfy tests.
- **Why current evidence is insufficient:** Fixture comments claim reclassification absent from series; three previously failing executor cases need full rerun.
- **Smallest safe repair:** Leave statuses untouched during repair; Opus maps real owner/data/external residue using final evidence and tests production registry separately.
- **Adversarial regression:** AT-I11. Setup: actual registry plus isolated synthetic gate test. Act: real classification and all affected executor tests. Assert: fixture cannot alter production registry; closed gates retain correct type; no software gap hidden by park.
- **Required runtime trace:** Final built-half evidence + live gate truth → integrator classification → independent closure audit.
- **Dependencies:** Platform P01/P02/P03; all six

<a id="cb2-i12"></a>

## CB2-I12 — Collection patch context predates the fixed no-spin behavior

- **Cluster / severity / timing:** Intel / High / DURING
- **Classification:** confirmed_static; not executed; unresolved audit input.
- **Claude defects:** C-73, C-67
- **Requirements:** #289, #187
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/runtime/release.py::handle_collection_assemble` — [preserved_patch:2132](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/orders.mbox#L2132); [preserved_patch:3342](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/intel.mbox#L3342); [checkpoint_source:1238](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/src/brambleloop/runtime/release.py#L1238)
  - `brambleloop/src/brambleloop/runtime/release.py::enqueue_member_collections` — [checkpoint_source:1210](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/src/brambleloop/runtime/release.py#L1210)
  - `brambleloop/src/brambleloop/runtime/pipeline.py::handle_certify` — [preserved_patch:2190](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/platform.mbox#L2190); [preserved_patch:1922](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/orders.mbox#L1922); [preserved_patch:1548](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/improve.mbox#L1548)
  - `brambleloop/tests/test_cert_growth_seasonal.py::test_a_bundle_waiting_for_members_defers_and_does_not_die` — [preserved_patch:3792](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/intel.mbox#L3792)
- **Existing behavior:** Saved test context still expects requeued=True; latest checkpoint moved to certification-triggered collection work.
- **Required behavior:** Preserve C-73 member-triggered, banded, idempotent collection execution plus Intel coherence refusal.
- **Why current evidence is insufficient:** Applying old expectations can silently undo the known-good fix.
- **Smallest safe repair:** Manually reconcile against checkpoint; do not reintroduce timer spin or 999 priority; test coherent/incoherent and member-update cases.
- **Adversarial regression:** AT-I12. Setup: collection missing member, then member certifies, then becomes incoherent. Act: drain jobs/certify/rebuild. Assert: no wait spin; one keyed trigger at valid band; incoherent collection not drafted; coherent control can proceed.
- **Required runtime trace:** Member certification → keyed collection job → coherence gate → draft/refusal without spin.
- **Dependencies:** Platform queue; Design members; Improve priority

<a id="cb2-x01"></a>

## CB2-X01 — Duplicate promotion/referral readers can disagree

- **Cluster / severity / timing:** Cross-cluster / High / DURING
- **Classification:** risk_requires_reproduction; not executed; unresolved audit input.
- **Claude defects:** C-66, C-67
- **Requirements:** #19, #235, #256, #264
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/commerce/order_readings.py::promotion_block` — [preserved_patch:680](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/orders.mbox#L680)
  - `brambleloop/src/brambleloop/commerce/order_readings.py::referral_block` — [preserved_patch:781](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/orders.mbox#L781)
  - `brambleloop/src/brambleloop/runtime/commerce_readings.py::_referral` — [preserved_patch:736](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/growth.mbox#L736)
  - `brambleloop/src/brambleloop/runtime/growth_ops.py::promotion_reading` — [preserved_patch:1930](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/growth.mbox#L1930)
- **Existing behavior:** Orders and Growth compute overlapping verdicts with different source/threshold assumptions.
- **Required behavior:** One documented evidence/window/verdict contract per decision; divergent readers cannot independently authorize actions.
- **Why current evidence is insufficient:** Each cluster's isolated fixtures can pass while producing contradictory advice.
- **Smallest safe repair:** Reuse canonical reconciled inputs and verdicts, or explicitly separate metrics/purposes; test same DB through every consumer.
- **Adversarial regression:** AT-X01. Setup: marginal promotion/referral with refund, unknown attribution and incomplete control. Act: all readers and consuming pricing/experiment paths. Assert: consistent measuredness/refusal and no second reader bypass.
- **Required runtime trace:** Canonical transaction/control facts → shared verdict → pricing/experiment/referral consumers → permitted action/refusal.
- **Dependencies:** Orders; Growth; Improve experiments

<a id="cb2-x02"></a>

## CB2-X02 — Combined model and registration changes lack integration evidence

- **Cluster / severity / timing:** Cross-cluster / High / DURING
- **Classification:** risk_requires_reproduction; not executed; unresolved audit input.
- **Claude defects:** C-64, C-67, C-68
- **Requirements:** #11, #64, #161, #174, #175
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/core/models.py::Order` — [preserved_patch:1381](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/orders.mbox#L1381)
  - `brambleloop/src/brambleloop/core/models.py::PhysicalPhoto` — [preserved_patch:2591](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/intel.mbox#L2591)
  - `brambleloop/src/brambleloop/core/models.py::TeardownFinding` — [preserved_patch:81](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/improve.mbox#L81)
  - `brambleloop/src/brambleloop/core/migrate.py::apply` — [checkpoint_source:71](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/src/brambleloop/core/migrate.py#L71)
  - `brambleloop/src/brambleloop/agents/registry.py::seed_defaults` — [checkpoint_source:341](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/src/brambleloop/agents/registry.py#L341)
  - `brambleloop/src/brambleloop/runtime/worker.py::CADENCES` — [preserved_patch:4296](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/platform.mbox#L4296); [preserved_patch:2161](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/orders.mbox#L2161); [preserved_patch:2289](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/growth.mbox#L2289); [preserved_patch:1697](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/improve.mbox#L1697); [preserved_patch:1407](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/intel.mbox#L1407)
- **Existing behavior:** Three clusters add model fields and multiple clusters add handlers/grants/cadences; individual fresh DB tests do not prove populated DB compatibility.
- **Required behavior:** Preserve data and register every new normal entry path in both fresh and upgraded databases without touching production.
- **Why current evidence is insufficient:** No full integrated suite/upgrade result exists; a missing migration file alone is not proof of a defect.
- **Smallest safe repair:** Use existing additive migration mechanism; reconcile declarations and validate disposable populated copies before acceptance.
- **Adversarial regression:** AT-X02. Setup: disposable checkpoint-schema DB with orders/findings/jobs plus fresh DB. Act: normal bootstrap and handler discovery only in test environment. Assert: preserved rows, valid columns/defaults, unique grants/cadences/handlers and no silent unregistered job.
- **Required runtime trace:** Saved schema/data → supported bootstrap → scheduler/grants → handler → durable evidence.
- **Dependencies:** All six; integrator owns actual migrations

<a id="cb2-x03"></a>

## CB2-X03 — Final protected actions must combine every applicable gate

- **Cluster / severity / timing:** Cross-cluster / Critical / DURING
- **Classification:** risk_requires_reproduction; not executed; unresolved audit input.
- **Claude defects:** C-65, C-67, C-69, C-70, C-72
- **Requirements:** #17, #39, #61, #64, #163, #171, #172, #228
- **Affected files/functions:**
  - `brambleloop/src/brambleloop/publish/release_gates.py::staleness` — [preserved_patch:1446](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/improve.mbox#L1446); [preserved_patch:2384](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/intel.mbox#L2384)
  - `brambleloop/src/brambleloop/publish/release_gates.py::standards_gate` — [preserved_patch:1478](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/improve.mbox#L1478)
  - `brambleloop/src/brambleloop/runtime/pipeline.py::handle_certify` — [preserved_patch:2190](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/platform.mbox#L2190); [preserved_patch:1922](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/orders.mbox#L1922); [preserved_patch:1548](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/improve.mbox#L1548)
  - `brambleloop/src/brambleloop/runtime/release.py::handle_chain_rebuild` — [preserved_patch:2517](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/platform.mbox#L2517); [checkpoint_source:2315](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/src/brambleloop/runtime/release.py#L2315)
  - `brambleloop/src/brambleloop/runtime/growth_ops.py::handle_ads_campaign` — [preserved_patch:1507](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/growth.mbox#L1507)
- **Existing behavior:** Gates are spread across planning, certification, asset and publication paths; clean merges can drop one or allow a stale decision.
- **Required behavior:** Final authorized write/spend must consume current, hash-bound eligibility and budget/owner/policy state, including direct/retry/rebuild paths.
- **Why current evidence is insufficient:** Testing each gate's library or planner separately does not prove conjunction at the adapter.
- **Smallest safe repair:** Reconcile one explicit final guard contract with scoped invalidation; preserve phase/owner/quality gates; prevent bypass by earlier passed plan.
- **Adversarial regression:** AT-X03. Setup: once-valid release/plan. Act: independently revoke each policy/veto/truth/rights/budget/approval prerequisite before execution; invoke direct, queued, retry and rebuild paths with spy adapters. Assert: zero protected calls for every failed prerequisite; all-valid mock control exactly once.
- **Required runtime trace:** All current prerequisite producers → durable eligibility → final action guard → authorized adapter → result/audit tied to inputs.
- **Dependencies:** All six

<a id="cb2-x04"></a>

## CB2-X04 — Test fixtures can conceal missing production evidence chains

- **Cluster / severity / timing:** Cross-cluster / High / AFTER
- **Classification:** confirmed_static; not executed; unresolved audit input.
- **Claude defects:** C-60, C-66, C-67
- **Requirements:** #88, #125, #126, #180, #244, #250, #257, #268
- **Affected files/functions:**
  - `brambleloop/tests/test_cert_design_pipeline.py::test_a_carried_judged_winner_is_queued_drafted_and_compiled_3_277_281` — [preserved_patch:2676](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/design.mbox#L2676)
  - `brambleloop/tests/test_cert_growth_ops.py::test_commerce_readings_read_stars_club_answers_and_referral_and_act` — [preserved_patch:3137](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/growth.mbox#L3137)
  - `brambleloop/tests/test_cert_intel_wave2.py::test_a_physical_photo_with_rights_upgrades_the_listing_and_measures_impact` — [preserved_patch:4433](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/intel.mbox#L4433)
  - `brambleloop/tests/test_cert_improve_wave.py::test_a_replayed_challenger_is_sandboxed_promoted_executed_and_rolled_back` — [preserved_patch:2591](https://github.com/StateFarm91/Project-Money/blob/0d42f2fe8f32f437a6bd1afcf8217ec1bd35aa56/brambleloop/research/b2_resume/patches/improve.mbox#L2591)
- **Existing behavior:** Several tests insert final evidence rows directly and then prove consumption.
- **Required behavior:** Separate consumer-unit/handler proofs from full producer→consumer certification evidence.
- **Why current evidence is insufficient:** A real DB plus fake final evidence does not prove a normal producer exists or semantics are true.
- **Smallest safe repair:** Keep useful fixtures, label their scope, and add producer-origin integration controls; no test deletion or gate weakening.
- **Adversarial regression:** AT-X04. Setup: empty disposable DB with normal bootstrap and deterministic external-boundary adapters, no final judgement/commercial/rights rows inserted. Act: normal upstream jobs. Assert: claimed evidence arises through actual producers or stays explicitly missing; fixture-only claims cannot qualify as full proof.
- **Required runtime trace:** Boundary input → actual producer → evidence → consumer → decision → observable protected action/refusal.
- **Dependencies:** All six; independent reviewer
