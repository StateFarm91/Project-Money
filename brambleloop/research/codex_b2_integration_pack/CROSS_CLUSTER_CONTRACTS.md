# CROSS-CLUSTER CONTRACT MATRIX

These are semantic interface acceptance criteria derived from the existing requirements and identified defects. Suggested fields describe evidence that must be available; they do not mandate a new schema, duplicate architecture or altered threshold. Opus should reuse existing types where they can express the contract.

| Contract | Interface | Main finding IDs |
|---|---|---|
| [CT01](#ct01) | Orders → Growth commercial truth | CB2-O01 CB2-O02 CB2-O03 CB2-O04 CB2-O05 CB2-O06 CB2-O07 CB2-G04 CB2-G09 CB2-G10 CB2-X01 |
| [CT02](#ct02) | Platform ↔ Growth targeted rebuild | CB2-P10 CB2-G03 |
| [CT03](#ct03) | Growth ↔ Improve priority authority | CB2-G01 CB2-G02 CB2-M05 |
| [CT04](#ct04) | Platform ↔ Improve worker and replay semantics | CB2-P09 CB2-M02 CB2-M03 |
| [CT05](#ct05) | Intel → Design judgement/reference evidence | CB2-D01 CB2-D02 CB2-I02 CB2-I03 CB2-X04 |
| [CT06](#ct06) | Design ↔ Intel winner progression | CB2-D03 CB2-D04 CB2-D05 CB2-D07 CB2-D08 CB2-O10 |
| [CT07](#ct07) | Intel ↔ Improve benchmark evidence | CB2-P04 CB2-P05 CB2-M04 CB2-M06 CB2-M07 CB2-I06 CB2-I08 CB2-I09 |
| [CT08](#ct08) | Improve ↔ Platform withholding and rollback | CB2-M01 CB2-M10 CB2-P10 CB2-X03 |
| [CT09](#ct09) | Publication/spend gates at final protected action | CB2-G11 CB2-X03 CB2-P06 CB2-I01 CB2-I04 CB2-I05 CB2-I07 |
| [CT10](#ct10) | Physical photo → approved exposure → impact | CB2-I04 CB2-I05 CB2-P06 |
| [CT11](#ct11) | Schema, registration and checkpoint preservation | CB2-X02 CB2-I12 CB2-P01 |
| [CT12](#ct12) | Evidence availability → incident recovery | CB2-I01 CB2-I07 CB2-P07 CB2-P08 |

<a id="ct01"></a>

## CT01 — Orders → Growth commercial truth

- **Producer → consumer:** Receipt/statistics/review producers → reconciled Order, Customer, OrderVersion, LedgerEntry → CAC, cohort, trust, promotion, pricing and winner readers
- **Required semantics/evidence:** Stable external transaction ID; source revision/event time and ingest time; explicit paid/cancelled/refund state and amounts; signed gross/fees/refunds/contribution; currency/rate basis; source-completeness window; acquisition-source confidence; delivered-version evidence or unknown.
- **Invalid interpretations / failure rules:** Unknown is not organic, unpaid is not sale, partial refund is not whole receipt, estimated FX/fees are not measured settlement. Replays converge to identical totals; late changes invalidate downstream readings.
- **Ownership / reconciliation:** Orders emits canonical truth; Growth consumes it consistently and preserves unknowns. Duplicate readers share one semantic definition or explicitly distinct purposes.
- **Findings:** CB2-O01 CB2-O02 CB2-O03 CB2-O04 CB2-O05 CB2-O06 CB2-O07 CB2-G04 CB2-G09 CB2-G10 CB2-X01
- **Acceptance witness:** Trace one paid sale, partial refund and late full refund through all actual readers; every financial/action verdict must change consistently.

<a id="ct02"></a>

## CT02 — Platform ↔ Growth targeted rebuild

- **Producer → consumer:** Growth fast-lane/invalidation producer → validated chain.rebuild request → Platform target resolver/stages → completion verifier
- **Required semantics/evidence:** Request ID; explicit scope (release/artifact set); slug/version-to-artifact resolution; requested dependency fingerprints; reason; attempt identity; existing phase/withholding constraints.
- **Invalid interpretations / failure rules:** Do not silently interpret unsupported slugs as full scan. Fresh unrelated rows do not complete request. Repeated request is idempotent; changed target requires new evidence.
- **Ownership / reconciliation:** Agree exact request shape during Growth integration; an adapter may preserve existing APIs, but the semantic contract is mandatory.
- **Findings:** CB2-P10 CB2-G03
- **Acceptance witness:** Request A with unrelated B needing work; observe only allowed A stages and exact matching completion across restart.

<a id="ct03"></a>

## CT03 — Growth ↔ Improve priority authority

- **Producer → consumer:** Commercial/seasonal/lesson inputs → one priority_decision authority → queue storage → claim order
- **Required semantics/evidence:** Base band; typed evidence/reason and source decision ID; deadline/value estimate with basis; bounded adjustment; applied policy/config version; immutable decision/application receipt.
- **Invalid interpretations / failure rules:** No cumulative raw priority drift; no priority-band escape; CAD heuristic is not measured value. Same decision applied once or recomputed deterministically. Protected customer/truth work remains ahead.
- **Ownership / reconciliation:** Growth supplies decision inputs; Improve owns bounded policy semantics; Platform enforces resulting claim/capacity constraints.
- **Findings:** CB2-G01 CB2-G02 CB2-M05
- **Acceptance witness:** At least four steering runs and restart, then policy update; protected jobs retain precedence and decisions are traceable.

<a id="ct04"></a>

## CT04 — Platform ↔ Improve worker and replay semantics

- **Producer → consumer:** Actual queue/pool/lane event history → replay dataset/simulator → independent comparison → promoted scheduler policy
- **Required semantics/evidence:** Worker count/activation history; lane/function budgets and atomic reservations; service durations with uncertainty; terminal failure state; backlog crossing days; historical product proof as-of time; dataset/config/simulator hashes.
- **Invalid interpretations / failure rules:** Replay may claim only what it models. Single-worker simulation is not multi-worker production proof. Missing durations, failed jobs and future knowledge cannot become measured success.
- **Ownership / reconciliation:** Platform defines observable runtime semantics; Improve reproduces them or scopes evaluation honestly; promotion remains withheld on material mismatch.
- **Findings:** CB2-P09 CB2-M02 CB2-M03
- **Acceptance witness:** Compare deterministic multi-worker harness and replay on same preserved events including failures, backlog and recovery.

<a id="ct05"></a>

## CT05 — Intel → Design judgement/reference evidence

- **Producer → consumer:** Observed reference/board/judge producer → typed evidence store → Design brief/gate consumers
- **Required semantics/evidence:** Concept/brief/CIR/release hash; artifact hash; judge/provider/version; observation date/population; benchmark identity; rubric/dimension; measured/unknown/not-applicable distinctions; limitations and source rights.
- **Invalid interpretations / failure rules:** Distinctiveness is not strength; swatch is not finished object; grid judgement is not all craft judgement. Missing producer cannot be replaced by seeded final rows.
- **Ownership / reconciliation:** Intel supplies accurately scoped evidence; Design accepts it only for measured checks and schedules missing judgements within existing capability gates.
- **Findings:** CB2-D01 CB2-D02 CB2-I02 CB2-I03 CB2-X04
- **Acceptance witness:** Normal tournament input produces genuine judge work; changed evidence re-enters gate; absent/limited evidence cannot clear full-object checks.

<a id="ct06"></a>

## CT06 — Design ↔ Intel winner progression

- **Producer → consumer:** CoverageGap/MjsMissionEvent → same-arena/breakout tournament → intake winner → CIR/release → lifecycle/memory
- **Required semantics/evidence:** Exact gap/event/arena/pod IDs; immutable concept identity and fingerprints; originating tournament job; stage-specific verdicts; current artifact/release hash; actual published/exposure event and measured outcome.
- **Invalid interpretations / failure rules:** No pod-only arbitrary gap selection; no stage complete from row existence; no draft-age launch failure; no winner mutation under old funnel approval.
- **Ownership / reconciliation:** Both sides preserve shared identity through payloads and durable evidence; ambiguity holds rather than mutating another gap.
- **Findings:** CB2-D03 CB2-D04 CB2-D05 CB2-D07 CB2-D08 CB2-O10
- **Acceptance witness:** Two same-pod gaps, one successful winner, one held; only correct provenance advances through actual downstream outcomes.

<a id="ct07"></a>

## CT07 — Intel ↔ Improve benchmark evidence

- **Producer → consumer:** Observed/purchased benchmark → scoped findings and raw notes/confidence → self-audit/competitive standard → change and release gates
- **Required semantics/evidence:** Benchmark identity and acquisition/source basis; category/product class; dimension/rubric/version; actual measured scores and confidence; our release/artifact hash; independent evaluator; finding-to-change-to-result links.
- **Invalid interpretations / failure rules:** Capability presence and arbitrary fixed delight scores are not comparable product scores. Seller geography is not buyer population. Old self-audit cannot certify changed release. Metadata tests_run is not an execution record.
- **Ownership / reconciliation:** Intel preserves observation limits; Improve enforces only applicable evidence and distinguishes planned changes/adopted floors from actual implementation.
- **Findings:** CB2-P04 CB2-P05 CB2-M04 CB2-M06 CB2-M07 CB2-I06 CB2-I08 CB2-I09
- **Acceptance witness:** Known benchmark trap causes actual changed artifact, independently evaluated against same rubric, and unmet requirements block final action.

<a id="ct08"></a>

## CT08 — Improve ↔ Platform withholding and rollback

- **Producer → consumer:** Owner veto/QA/policy/regression events → durable release eligibility or rollback work → draft/rebuild/publish/config consumers
- **Required semantics/evidence:** Complete scoped withholding reason set; evidence/release hashes; invalidation version; rollback request/attempt/state; before/desired/verified actual configuration; idempotency receipt; durable unresolved incident.
- **Invalid interpretations / failure rules:** One reason cannot overwrite another; clearing one cannot clear all. REVERTED cannot mean rollback effect still pending. Retry/rebuild cannot bypass veto or re-enable bad config.
- **Ownership / reconciliation:** Platform provides recoverable execution/eligibility consumption; Improve supplies explicit requested changes and verified completion rather than audit-only labels.
- **Findings:** CB2-M01 CB2-M10 CB2-P10 CB2-X03
- **Acceptance witness:** Kill across rollback boundaries; invoke every rebuild/draft path under multiple holds; verify effect and hold persistence after restart.

<a id="ct09"></a>

## CT09 — Publication/spend gates at final protected action

- **Producer → consumer:** All eligible plans/evidence → current final guard → existing authorized external-write adapter → result audit
- **Required semantics/evidence:** Current phase/authority, applicable truth/quality/policy/rights/identity verdicts, exact artifact set hashes, budget/credit/cash state where applicable; action request identity and checked-state version.
- **Invalid interpretations / failure rules:** Planning success is not lasting authority. Direct/retry/rebuild paths cannot omit guards. Refusal means zero adapter calls and zero spend; an all-valid mock control proves the guard is reachable.
- **Ownership / reconciliation:** All clusters compose guards; integrator identifies the actual adapter boundary from final code, never assumes a handler name proves protection.
- **Findings:** CB2-G11 CB2-X03 CB2-P06 CB2-I01 CB2-I04 CB2-I05 CB2-I07
- **Acceptance witness:** Revoke every prerequisite between plan and execution and assert zero calls; actual live writes remain outside this test plan.

<a id="ct10"></a>

## CT10 — Physical photo → approved exposure → impact

- **Producer → consumer:** Photo bytes and permission source → intake → review/recertification → final publication gate → exposure event → impact reader
- **Required semantics/evidence:** Actual bytes/hash and image validity; product/version mapping; rights reference and revocation state; review for complete current frame set; approval/publication timestamps; exposed listing-set hash; comparable traffic windows.
- **Invalid interpretations / failure rules:** Hash syntax is not artifact existence, rights label is not permission evidence, upgrade_queued is not published, unapproved asset is not customer exposure.
- **Ownership / reconciliation:** Intel owns lifecycle producer; Platform supplies hash-bound gates/rebuild; Growth measures only verified exposure windows.
- **Findings:** CB2-I04 CB2-I05 CB2-P06
- **Acceptance witness:** Invalid bytes/rights refused; approved-unpublished produces no impact claim; authorized mocked exposure starts measurement only once.

<a id="ct11"></a>

## CT11 — Schema, registration and checkpoint preservation

- **Producer → consumer:** Combined patch declarations → normal bootstrap/scheduler → real handlers → durable outputs
- **Required semantics/evidence:** Compatible additive schema/defaults; unique registered job types; grants; cadence or upstream enqueue; priority bands; retention for evidence; current C-73 behavior and untouched independence work.
- **Invalid interpretations / failure rules:** Fresh DB success does not prove upgrade; append-only registration merges can still omit a grant or duplicate cadence. Old collection-spin test is not authoritative over fixed checkpoint.
- **Ownership / reconciliation:** Integrator resolves shared files and verifies both fresh and disposable populated DB; no production migration in this pack.
- **Findings:** CB2-X02 CB2-I12 CB2-P01
- **Acceptance witness:** Normal bootstrap schedules all required producers, preserves existing data and no-spin collection triggers, and exposes honest closure.

<a id="ct12"></a>

## CT12 — Evidence availability → incident recovery

- **Producer → consumer:** Policy/visual/probe observations → durable issue state → gates/recovery consumers
- **Required semantics/evidence:** Source/pack identity; observation window; readability/completeness; explicit bad/good/unknown verdict; unresolved issue lineage; recovery evidence and reviewer where required.
- **Invalid interpretations / failure rules:** Evidence disappearing, expiring or becoming unreadable is not recovery. Identical policy re-observation is not review. Polling the same state is not a new attempt.
- **Ownership / reconciliation:** Intel and Platform preserve issue state until relevant adequate evidence supports the documented resolution rule.
- **Findings:** CB2-I01 CB2-I07 CB2-P07 CB2-P08
- **Acceptance witness:** Advance clock past evidence window, reread identical policy and repeat sweeps; unresolved protected-action holds persist without permanent probe starvation.

## Shared-file conflict inventory

A clean Git merge is not contract acceptance. In particular, manually reconcile handler bodies and gate composition in `runtime/pipeline.py` and `runtime/release.py`, touched by all six. Other shared files and exact candidate commit inventories are in [SOURCE_INVENTORY.md](SOURCE_INVENTORY.md).

Semantic traps beyond textual conflicts: duplicate referral/promotion verdicts; Growth rank used only by board; Platform pool versus replay; actual versus inferred source geography; Design stages versus Intel rows; teardown audit scope versus current release; veto audit versus durable withholding; fixed C-73 member triggers versus old collection-wait tests. Run AT-X01–AT-X04 on the complete head.
