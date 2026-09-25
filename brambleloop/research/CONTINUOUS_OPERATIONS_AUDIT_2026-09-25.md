# Continuous operation audit and staged rollout

Audit date: 2026-09-25. Base: `7122ec0907d45e8c0fd64c94177c49b7bb32ae2e`.
Branch: `codex/continuous-operations-audit`. This branch is not deployed.

## Evidence and preservation

Read CLAUDE.md, BUILD_STATE.md, decision log, master-plan sections on runtime,
execution directive, acceptance gates, and v1.4.3 requirements 171-196. The README
still describes the retired competition; CLAUDE.md correctly identifies Brambleloop.
BUILD_STATE contains historical assertions contradicted by later dated entries:
Etsy was authorized September 25. Do not use its introductory snapshot as current state.

Remote branches at audit: `claude/repository-setup-nc9x6o` (default/integration),
`build-1-baseline`, and `claude/cloud-pilot-products-audit`. No open PRs observed.
Build 1 recovery commit remains `d5168c0cea93dde23f06592a36c5a253533b83e5`.
The cloud pilot remains separate. No existing checkout, branch, checkpoint, live database,
listing, campaign, phase, or deployment has been changed by this audit.

Public production reads around 20:46 UTC returned:
- `/health`: deployed commit 7122ec0, Postgres available, worker alive, scheduler ticking.
- `/api/verify`: 12/12 passed; shadow mode, zero publications and advertising spend.
- `/api/status`: 4,889 completed jobs; 164 dead letters classified as deliberate refusals;
  15 open incidents; nine open owner actions; CA$76.3984 model operating spend, zero revenue.
These are dated observations, not current guarantees. A certified pattern is not a
listing cleared for launch. The full visual and owner review gates still apply.

## What exists versus what is missing

| Objective | Existing implementation | Remaining gap / action |
|---|---|---|
| Persistent coordinator | Railway embedded scheduler and worker; standalone entrypoints | One serial worker at audit; coding coordinator is a separate session |
| Durable jobs | Postgres jobs, leases, retry/backoff, idempotency keys | Stale attempts could overwrite successors; fenced in this branch |
| Independent departments | 24 permissioned logical agents, handlers and cadences | Logical agents were not independently executing; opt-in no-model lanes added here |
| Automatic refill | Worker drains follow-on jobs; scheduler restores cadence work after restart | Does not autonomously implement arbitrary BuildTasks or launch replacement coding agents |
| Development evidence | ops/board.py and ops/registry.py derive state from logs/git | Registry explicitly has no supervisor, queue, ownership, retry or merge policy; paths and logs can be lost with the host |
| Cost controls | Monthly and agent ceilings, reservation rows, spend ledger | Check/reserve race fixed here; reservation release before batched billing and expiry during uncertain calls still need reconciliation |
| Recovery | Lease reclaim, dead letters, per-deploy redrive, worker exception restart | Hung handlers are not killed; queue fencing cannot undo external effects |
| Owner decisions | OwnerAction table and approval cards | Reuse it; do not introduce another inbox |
| Controlled changes | Improvement proposals, tiers, rollback references, session integrator | No demonstrated independent cloud coding executor and branch promotion service |
| Off-device proof | build2/autonomy.py and observed Railway operation | Proof counts all audit hours as scheduler evidence and excludes only one attended job type; strengthen provenance before claiming fully unattended development |
| Ads eligibility | Etsy surface registry records no sanctioned Ads API | Durable reported countdown and hourly preparation/recheck added; fresh Etsy UI evidence still requires an operator until a sanctioned collector exists |
| Visual | CIR/twin/geometry, reference conditioning, parity and truth gates | Milestone D remains open in BUILD_STATE; this work does not resolve or supersede it |

## Changes in this branch

1. Every queue claim receives a fresh opaque lease token. Runtime completion/failure uses
   that token; an old attempt cannot overwrite a successor, even when worker names or retry
   counters repeat. SQLite claims now actually serialize writers; Postgres retains SKIP LOCKED.
   Reclaim queries lock only expired jobs. This is state fencing, not an exactly-once external
   transaction guarantee. Legacy administrative/test calls without tokens remain compatible.
2. Budget admission holds a short database transaction through reading ceilings and inserting
   the reservation, released before provider work. Per-agent checks count other callers'
   outstanding reservations. No ceiling is increased and no cheaper model is substituted.
3. `BRAMBLELOOP_WORKER_LANES=departments` partitions registered job types into Operations
   (heartbeat/queue recovery/health), Finance (reconciliation), Marketing (Ads preparation),
   and Production (remaining work). Existing queue and scheduler are reused. Each lane drains
   useful jobs automatically and sleeps when empty. Default remains `serial` for staged rollout.
   Health includes each lane; one ticking lane cannot make all lanes appear healthy.
4. Ads readiness persists in `marketplace_capabilities`, is scheduled hourly through the existing
   scheduler, and appears in `/api/etsy/ads-readiness`, `/api/status`, and the Command Center.
   An authenticated evidence endpoint uses the existing operator credential. No Ads API, listing
   publication or campaign activation is introduced.

## Master continuation requirements retained

The Visual objective remains: validated pattern/CIR -> structurally faithful finished-product
3D reference -> downstream AI photoreal listing/ad image -> independent Product Truth and
benchmark-listing-photo validation. A procedural render alone is not the final listing image.
Neither a model verdict nor a deadline may loosen deterministic or Visual gates. Existing
Launch-0 owner review and physical-proof requirements remain binding.

Ads seed evidence is a conversation report of Shop Manager on September 25 saying nine days
remaining, not a fresh API observation. October 4 is an estimated recheck date. `last_verified_at`
is initially null. Countdown expiry becomes RECHECK_REQUIRED, never ELIGIBLE. The hourly job
prepares a candidate inventory and experiment checklist and opens one owner action when fresh
Etsy evidence is needed. It does not claim to have contacted Etsy. An operator may record
recent UI evidence; confirmed eligibility still grants no spending authority. Evidence expires
for operational purposes after 24 hours. Etsy Plus credit and owner cash remain distinct and
unverified; no credit balance or approved budget is invented. Actual campaign activation and
credit/cash transaction reconciliation are not implemented in this increment.

## Safest path to fully continuous work

A. Integrate this bounded branch after reviewing current integration-head changes. Run queue,
   budget and migration tests against real Postgres, plus existing release/Visual suites in
   the project's Linux environment. Drain old worker replicas before using parallel lanes:
   an old binary does not present lease tokens, so mixed-version workers are not fenced.
B. Deploy in shadow mode on existing infrastructure, first serial. Verify commit identity,
   schema additions, Ads cadence completion and existing verification gates. Then enable
   department lanes within the existing infrastructure ceiling. Prove Marketing/Finance/
   Operations progress while a production job is slow, and collect per-lane latency/cost.
   Revert the setting to serial if shared database load or reliability regresses.
C. Before parallel paid/model workers, reconcile each reservation to ledger entries atomically;
   hold uncertain provider charges pending reconciliation, and enforce per-job timeouts in
   isolated processes. Add provider idempotency/effect receipts or explicit reconciliation
   for publication, messaging and spending. Queue idempotency alone does not guarantee once-only
   external effects. Never blindly retry an ambiguous commercial outcome.
D. Extend the existing BuildTask graph and evidence board with a cloud-resident bounded executor,
   not a second backlog. It must claim tasks atomically, use isolated checkouts keyed by task and
   base SHA, persist logs/results outside container temp storage, and refill only unblocked work
   after verified completion or bounded recovery. API-based execution must use the same spend
   ledger and authorized ceilings; cloud chat sessions are optional burst adapters.
E. A single integration authority validates exact base/head SHAs, required tests, declared
   surfaces, unchanged Product Truth gates, deployment evidence and rollback before promoting.
   High-risk changes go to the existing owner queue. No worker gets unrestricted merge/deploy
   or marketplace authority. An owner decision must not stop unrelated departments.
F. Record a genuine 24-hour no-session window with scheduler-specific evidence, worker leases,
   useful outputs by department, restarts, costs, and no manually supplied jobs. Report queued,
   running, blocked, failed, verified, merged and deployed as distinct states. Never infer a
   completion from a watcher being alive or a process ending.

Launch work proceeds alongside these increments. Full self-improving development automation is
not a new prerequisite for finishing Visual, product claims, durable downloads, or the already
prepared Etsy integration exercise. Existing product and acceptance gates remain prerequisites.

## Rollback and limits

Revert application code or set worker lanes back to serial; retain additive tables/columns so
recorded evidence is not destroyed. Do not roll back by deleting jobs, reservations, the Ads
record, or baseline branches. No infrastructure or provider account was provisioned. No new
recurring paid service was enabled. Fully unattended coding/refill and 24-hour end-to-end proof
remain unfinished; this document must not be presented as a deployment or autonomy certificate.


## Validation performed

144 unique tests passed across test_continuous_operations (16), test_spend_governance,
test_cost_governance_wave2, test_gates, test_continuity and test_swarm. Includes simultaneous
SQLite claims, stale-attempt completion/failure/heartbeat rejection, concurrent budget
admission, per-agent reservations, independent lane progress, embedded startup/refill/shutdown,
Ads persistence/due-date/evidence expiry, and authenticated evidence submission. An existing
path-format assertion was made portable with Path.as_posix; its safety expectation is unchanged.

Three deployment smoke tests passed (health, status, dashboard). The complete test_deploy run
was interrupted while the existing catalogue render worked in Pillow; no full deployment-suite
pass is claimed. Production Postgres concurrency, Linux kill/restart tests, actual deployment,
Etsy UI refresh, and a new 24-hour off-device proof were not executed. No test contacted Etsy,
published a listing or purchased advertising.
