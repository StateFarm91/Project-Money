# Brambleloop full-system audit — 2026-11-22

Audit lead: Claude Fable 5.2. Fixes: nine sub-agent sessions on Claude Opus 5.5
(`claude-opus-5-5`), one narrow branch each.

- **Audited tree:** `origin/claude/w6-release-19h22` at `f9011cf94` (production runs its parent
  `67efe8eb`; the tip adds only the DEPLOYED_HISTORY record).
- **Size:** 1,166 source files / 415,319 lines under `src/brambleloop`; 1,105 test files /
  309,696 lines; 374 HTTP routes.
- **Production facts** are the operator readback of 05:15Z, quoted, not re-measured: the audit
  had no production access and read no Railway variable or secret.

## How to read this report

Every finding carries a severity, the evidence (file:line on `f9011cf94`) and either the fix
branch or the exact reason no branch exists. "UNVERIFIED IN PRODUCTION" means the defect and its
fix were proven on the code and on fixtures only.

### Method and honest coverage

| Area | How it was audited |
|---|---|
| Paid-call gate, budget ceiling, owner activation | Read in full: `gateway/paid_provider_gate.py`, `gateway/anthropic.py` (ceiling, lock, month spend), `gateway/routing.py` (ceiling kinds), `ops/owner_directives.py` |
| Auth, step-up, TOTP, tokens, public surface | Read: `app/security.py`, `app/command_center/auth.py` (gate, TOTP, step-up), `core/opsauth.py`, `core/readbackauth.py` |
| Boot guard, phase, publish path | Read: `ops/release_record.py`, `core/phase.py`, `runtime/worker.py` (`protected_phase`, `Scheduler`), `runtime/pipeline.py` store.publish head, `gates/incidents.py`; boot guard executed against the production tree |
| Evidence / readback | Read `ops/production_evidence.py` assembly and judgements; profiled `evidence()` on the seeded production-shaped DB |
| Child safety | Read `gates/child_safety.py` (applicability, verdict), callers, the bulk-approval guards |
| Queue, scheduler, runner | Read `queue/durable.py` API, `app/runner.py`, `Scheduler.tick` |
| Whole source tree | Static scan (ruff F821/F811/F601/B006/B015/B018/B023/E722/PLE), dangerous-call scan, SQL string-building scan, import-graph reachability scan, LargeBinary read scan |
| Test suite | AST scan of all 1,105 test files for never-invoked tests and assertion-free tests, SKIP handling in `run_tests.sh`, spec gate suites run, known-red suites run, full suite started |
| Pipeline stages research → learning | NOT read line by line (≈250k lines). Covered by the spec gate suites (run, see P0 table) and by the full acceptance suite started on the production tree (run id below). Stage-level defects beyond those listed here are not excluded by this audit. |

Two areas were deliberately left to their owning lanes, per the coordinator: the BFL host
(`eng/bfl-regional-host`) and the concept gate (`eng/concept-gate`).

---

## Findings, ranked

| # | Severity | P0 impact | Finding | Fix |
|---|---|---|---|---|
| F-01 | CRITICAL | Blocks every Etsy draft and publication | Production tree has no full-suite release record; the boot guard forces SHADOW and opens a global halting P1 | Operational, see below (no code branch possible) |
| F-02 | HIGH | Hides F-01 from the owner | Readback says `publishing_halt_clear` and `draft_candidate` while every `store.publish` would be refused | `eng/audit-readback-phase` |
| F-03 | HIGH | Readback timeouts; web-process memory | Metadata reads load whole binary archives (root cause of the 45–105 s evidence endpoint, by code inspection) | `eng/audit-blob-reads` |
| F-04 | HIGH | Full suite cannot be release-eligible (feeds F-01); audit rows at risk | Retention guard red on the production tree: 6 audit actions and 5 read sites have no retention decision | `eng/audit-retention-guard` |
| F-05 | HIGH | Operator starts every session from a false record | BUILD_STATE has no current-production statement; ~40 deployed entries still read "NOT merged, NOT deployed" | `eng/audit-build-state` |
| F-06 | MEDIUM | Paid calls serialise behind a growing scan | Every budget decision loads the whole cost ledger inside the global budget lock | `eng/audit-budget-scan` |
| F-07 | MEDIUM | Governance of a publication waiver | The sample-photo publication waiver is authorised by a heading in a shipped JSON index, not by an owner-signed grant | Needs the owner (reason below) |
| F-08 | LOW–MEDIUM | False confidence in unwired capabilities | 47 modules (~6.5k lines) are imported only by tests; one module is dead | `eng/audit-dead-code` |
| F-09 | LOW–MEDIUM | A stated limitation silently discarded | Duplicate dict keys: contradictory `support_friction` disclosure in `visual/drape.py`; two duplicated routing keys | `eng/audit-hygiene` |
| F-10 | LOW | Suite total overstated | A Postgres-only test passes without running and is not reported as skipped | `eng/audit-hygiene` |
| F-11 | MEDIUM | Resilience | Web, worker pool, lanes and scheduler share one process and one GIL; restart policy is finite | Needs the owner (infrastructure change, reason below) |
| F-12 | LOW | Latent date drift | 151 `date.today()` calls depend on the process time zone (CLAUDE.md requires UTC); correct only while the container has no TZ set | `eng/audit-utc-health` |
| F-13 | LOW | Health probe cost | `/health` counts the whole `jobs` table on every probe (`app/main.py:680-686`) | `eng/audit-utc-health` |
| F-14 | HIGH | Readback timeouts | Readback handlers load every Job and AuditLog row as ORM objects: `swarm/orchestrate.py:1905` (`agent_quality`, called by `api_swarm_runtime` on every evidence read), `build2/maturity.py:448-451`, `products/inventory.py:158`, `gateway/paid_calls.py:560` | `eng/audit-table-scans` |

### F-01 — CRITICAL — production is forced to SHADOW; no draft or listing can reach Etsy

**Evidence.**
- `ops/release_record.py:183-236`: on Railway a build with no committed release-eligible
  full-suite record for its exact tree is forced to SHADOW at import (`forced_shadow`);
  `:263-300` opens a P1 `release.unproven_build` with `halts_publication=True` and no product
  slug.
- Executed on the production tree: `release_record.verify_build(env={"RAILWAY_ENVIRONMENT": ...})`
  → `ok: false`, reason "no committed release record names this build's tree digest"
  (tree `b0dfa6fb…`). `release/` holds no `RELEASE_67efe8eb…json`.
- The newest release-eligible full run on file is `20261119T135927Z-1739` on `a35ad302`
  (982 suites, 11,679 passing). The 37 later deploys (Batch 19a … 19h22) went out on changed
  and overlap suites. Each D-OWNER-DEPLOY-19* entry says so itself: "There is no full-suite
  certification yet: the boot guard still requires a full-suite record".
- `runtime/pipeline.py:2523-2536`: `store.publish` raises `ShadowModeRefusal` before any
  `createDraftListing` when the phase is SHADOW. `gates/incidents.py:94-117`: a halting
  incident with no slug halts publication for every product.
- `core/phase.py`: even with a release record, the phase stays SHADOW until the owner records a
  sealed phase transition (operator credential, readiness verdict).

**Consequence.** "0 drafts" and "no listing published" do not depend only on the BFL key. With
a working key and a certified gallery, the first `store.publish` would still be refused. P0
(first listing on Etsy) has three further prerequisites nobody has listed for the owner:
(1) a green full acceptance suite on the exact release tree and its committed release record;
(2) the owner's recorded phase transition out of SHADOW; (3) the signed publication grant.

**Why there is no fix branch.** A release record cannot be written by a code change: it must
name a full, clean, unresumed suite run on the exact tree that ships
(`release_record.check_record`). The audit did the two things it could:
- started the first full suite ever run on this tree: run `20261122T052554Z-3656`,
  `/home/user/bl-runs/audit-fullsuite`, 1,080 suites, JOBS=3. It is expected to fail on F-04
  (already reproduced); its failing-suite list is the complete red inventory of production;
- assigned F-04 so the suite can go green.

**Remaining action (coordinator, then owner).** Merge the audit branches, run the full suite on
the merged tree, commit the release record, deploy. Then **OWNER ACTION REQUIRED**: record the
phase transition (operator credential; CA$0; ~5 minutes; consequence of waiting: no draft and no
listing can be created, whatever else is fixed).

### F-02 — HIGH — the readback passes while publication is impossible

**Evidence.** `ops/production_evidence.py:236-289` and `:1888-1895`: `publishing_halt_clear` is
judged from the systemic-signature incident and the truth sweep only; an open global halting
incident lands in `per_product_halting_by_family` as `products: 0, slugs: []` and changes
nothing. `:1177-1256`: `draft_candidate` reads the approval packet and the listing package, never
the phase. `grep -n "phase\|shadow\|boot_guard" ops/production_evidence.py` returns nothing: no
section names the effective phase or the boot-guard verdict. `publish/sale_pipeline.py` READY is
likewise phase-blind. This is how "the systemic publishing halt is CLEAR" was reported at 05:15Z
while F-01 stood. UNKNOWN was being read as PASS.

**Fix.** `eng/audit-readback-phase`: read-only `runtime_phase` section, global halting incidents
counted and judged, `draft_candidates_actionable_now`, `server_judgement.publication_path_open`.
No gate, phase rule or publish behaviour changes.

### F-03 — HIGH — metadata reads load whole binary archives

**Evidence.**
- `core/continuity.py:651-661` `retained()` ("without reading the payloads back") runs
  `select(ContinuityArchive)`; the model's `payload` (`core/models.py:1706`, a gzip of the whole
  database export) is not deferred, so all three retained archives are fetched to return ids
  and sizes. `:628-631` does it twice more when pruning.
- `/api/readback/evidence` (`app/main.py:5786-5798`) passes `deploy_handlers`;
  `production_evidence.deploy_readback` calls `api_continuity` (`app/main.py:1231-1253`), which
  calls `retained()`. So every evidence read pulls three full database archives over the wire.
- Profile on the seeded production-shaped DB (`tests/test_evidence_perf.py` seed, which omits
  `deploy_handlers`): 1.4 s, 557 statements. Production: 45–105 s and rising as the database,
  and therefore each archive, grows. The earlier perf lane optimised the sections it could
  profile and never exercised the handlers.
- Same pattern on `DurableArtifact.payload` (`core/models.py:1899`):
  `commerce/deliverables.py:429-430` lists every kept PDF and image with its bytes;
  existence checks (`core/artifacts.py:134`, `finance/accounting/statements.py:86,102`) fetch
  the blob to test presence. The worker shares the web process, so these also spike its memory.

F-14 is the second half of the same latency: `agent_quality` loads the whole `jobs` table on
every evidence read. A further 15 unbounded `select(CostEntry)` reads exist in report and
learning jobs (for example `finance/spend_report.py:465`, `finance/sustainability.py:109`);
they run on the worker, not on the readback path, and the table-scans lane was told to list
what it does not fix.

**Status.** Root cause by code inspection and local profile; UNVERIFIED IN PRODUCTION until the
deployed `timing_ms.deploy_readback` is read.

**Fix.** `eng/audit-blob-reads`.

### F-04 — HIGH — retention guard is red on the production tree

**Evidence.** Run `20261122T051906Z-794` on `f9011cf94`:
`tests/test_w4_fmbatch1_retention_guard.py::test_every_action_the_real_code_reads_is_classified`
fails. `ops.retention.unknown_read_actions()` returns `asset_inspection.openai_answer`,
`asset_inspection.openai_attempt`, `concept.judge_attempt`, `creative.regate`,
`owner_queue.approve_everything`, `paid_provider.refused`, and five unresolved read sites
(`ops/production_evidence.py::_credential_health`, `::after_admission`, `::rebuild_outcomes`,
`runtime/release.py::_attempt_gate_refusal`, `runtime/release_recovery.py::_halted_releases`).

**Consequence.** Audit rows that production code reads by name have no retention decision. Two
of them gate repeat paid calls (`concept.judge_attempt`, `asset_inspection.openai_attempt`) and
one is the record of an owner's stepped-up bulk approval. And one red suite makes the full suite
ineligible, which is F-01. (The two other suites BUILD_STATE lists as red, `test_w4_launchfix`
and `test_w6_listing_chain_e2e`, pass on this tip.)

**Fix.** `eng/audit-retention-guard`.

### F-05 — HIGH — BUILD_STATE has drifted from production

**Evidence.** `BUILD_STATE.md` (10,249 lines) contains no mention of `67efe8eb`, `19h22` or
`19i5`; `release/DEPLOYED_HISTORY.json` lists 57 deploys. Its newest ~40 entries each say "NOT
merged, NOT deployed; production unchanged" although their code is in the production tree (for
example `core/request_memo.py` from EVIDENCE-PERF, line 193). Line 20 still names two failing
suites that now pass. CLAUDE.md requires this file to be honest and to be read first.

**Fix.** `eng/audit-build-state`: a verified PRODUCTION NOW block, a per-entry ancestry note
derived from `git merge-base --is-ancestor`, and a guard test against future drift.

### F-06 — MEDIUM — the spend gate scans the whole ledger under the global lock

**Evidence.** `gateway/anthropic.py:203-230` `spent_this_month_cad` selects every `CostEntry`
ever written and filters the month in Python; it runs inside `budget_lock`
(`:512-538`, process lock plus `pg_advisory_xact_lock`) on every budget decision and every
paid-call authorisation (`gateway/paid_provider_gate.py:788-790`). Enforcement is correct today; cost grows with the lifetime ledger.

**Fix.** `eng/audit-budget-scan` (zero behaviour change, old implementation kept as the test
oracle).

### F-07 — MEDIUM — a publication waiver authorised by a file heading — NEEDS THE OWNER

**Evidence.** `publish/sample_photo.py:50-52` waives `SAMPLE_PHOTO_REQUIRED` when
`core/decision_index.recorded("D-OWNER-PUBLISH-WITH-RENDERS")` is true, that is, when
`core/decision_index.json` (generated from DECISION_LOG headings, `core/decision_index.py`)
lists the id. Any commit that adds a heading therefore waives a publication gate; nothing binds
the waiver to the owner's credential. `ops/owner_directives.py` is the stronger pattern (fixed
table, window, ceilings, sunset) and still rests on code, not on a signature.

**This is not a challenge to D-OWNER-PUBLISH-WITH-RENDERS**, which stands. The finding is the
mechanism. Blast radius is bounded: publication still needs the signed publication grant.

**Why no branch.** The fix is to require an owner-signed standing grant for the waiver. Writing
it requires the owner's step-up; shipping it without that signature would revoke a binding owner
decision in production, and creating the signature for the owner would be forging an
attestation. **OWNER ACTION:** decide whether to sign the waiver as a standing grant in the
Command Center (CA$0, ~2 minutes). Consequence of waiting: the waiver keeps working as today.

### F-08 — LOW–MEDIUM — modules only tests import

**Evidence.** Import-graph scan: `brand/iterations.py` has no importer at all; 47 modules
(6,522 lines) are imported only by tests or scripts, among them `publish/wearable_pdf.py`,
`visual/d_judge.py`, `ops/overnight_grade.py`, `growth/ads_decisions.py`, `learn/teaching_loop.py`,
`finance/accounting/guardrails.py`, `core/backup.py`. A green suite for an unwired module reads
as "this capability exists".

**Fix.** `eng/audit-dead-code`: delete what is dead, a tracked inventory of unwired
capabilities, and a reachability guard so the list cannot grow or rot unnoticed. Wiring the
unwired capabilities is product work and is not done here.

### F-09 — LOW–MEDIUM — duplicate dict keys

**Evidence.** `visual/drape.py:257` and `:283`: `"support_friction"` twice in one limitations
dict with contradictory statements ("BOUNDED ASSUMPTION, OFF BY DEFAULT" and "NOT MODELLED");
Python keeps the second. `runtime/pipeline.py:3949/4054` and `swarm/orchestrate.py:1384/1395`:
`"improve.self_tune"` twice.

**Fix.** `eng/audit-hygiene`, with an AST guard over the whole tree.

### F-10 — LOW — a test that passes without running

**Evidence.** `tests/test_w4_firstsale_deliverables.py:202-211` returns when `BL_TEST_PG_URL`
is unset and is counted OK; its notice does not start with `SKIP`, so `run_tests.sh:576`
reports zero skips.

**Fix.** `eng/audit-hygiene`.

### F-11 — MEDIUM — one process, one GIL — NEEDS THE OWNER

**Evidence.** `railway.json`: one service, `uvicorn … --workers 1`, `restartPolicyMaxRetries: 10`.
`app/runner.py:527-577` starts the worker pool, the lane workers, the scheduler and the
supervisor as threads of the web process. CPU-bound handlers (PDF, image composition) contend
with HTTP for the GIL; the stale-scheduler self-exit (`:509-523`) consumes the finite restart
budget. Separate entry points already exist (`app/worker_entry.py`, `app/scheduler_entry.py`).

**Why no branch.** The remedy is a second Railway service running `worker_entry`, with
`BRAMBLELOOP_EMBEDDED_WORKER=0` on web. That is a hosting change with a recurring cost and a
deploy-time variable change, not a code change: consequential spend and configuration belong to
the owner. **OWNER ACTION:** approve a separate worker service (cost: one more Railway service,
amount set by Railway's plan; ~10 minutes). Consequence of waiting: slow readbacks under load
and a service that stays down after ten crash exits. F-03 removes the worst of the latency
without it.

---

## Areas reviewed with no finding

- **Paid-call safety and the CA$100 cap.** One enforcement point, reservation before send,
  re-confirmation before I/O, orphans counted as billed, lower-only environment overrides, NaN
  handling, fail-closed on unreadable accounting, unknown spend kinds counted inside the
  ceiling (`gateway/routing.py:404-421`). No bypass found.
- **Auth.** Default-deny gate on all 374 routes with an allow-list of public reads and
  projections; constant-time token comparison; PBKDF2 600k; TOTP with single-use time steps;
  session cookie `__Host-`, CSRF HMAC, nonce and timestamp replay protection; step-up window
  5 minutes; readback token refused if equal to the operator token. No finding.
- **Secrets.** No dangerous calls (`shell=True`, `eval`, `pickle`, `verify=False`), no
  environment values logged, no SQL built from request input.
- **Child safety.** Applicability errs towards applying; UNKNOWN holds; physical evidence is
  UNKNOWN for every stuffed or sewn item, so those are HELD; bulk approvals exclude child-safety
  rows three ways. No finding, nothing waived.
- **Scheduler and queue.** Idempotency keys per cadence window, per-cadence isolation, lease
  fencing, dead-letter classification. No finding.
- **Test suite.** No never-invoked test in 1,105 files; mutation tests are common; assertion-free
  candidates sampled were delegating to asserting helpers. Only F-10.
- **Static scan.** Two `F821 datetime` hits in `runtime/worker.py:220,267` are annotations
  under `from __future__ import annotations` (harmless). B023 closures sampled are called inside
  their iteration.

---

## P0 status

### Mission P0 (first listing on Etsy, factory running unattended)

| Item | Status | Evidence / blocker |
|---|---|---|
| Systemic publishing halt clear | PASS as reported; **misleading** | F-02: a global halting P1 is not counted |
| Runtime phase allows a draft | **FAIL** | F-01: forced SHADOW; no owner phase transition |
| Full-suite release record for the production tree | **FAIL** | F-01; last eligible run is `a35ad302`, 2026-11-19 |
| Full acceptance suite green on production tree | **FAIL** (known) | F-04 red; full run `20261122T052554Z-3656` in progress |
| FLUX renders | FAIL | 403 not_authenticated; owner checking key; lane `eng/bfl-regional-host` |
| Concept gate passes concepts | FAIL (0 passed) | lane `eng/concept-gate` |
| Certified gallery for a for-sale release | FAIL (0 of 13) | waits on FLUX |
| Private Etsy draft | FAIL (0) | waits on gallery, then F-01 |
| Listing published | FAIL (0) | all of the above, plus the signed publication grant |
| Competitor scans | PASS as reported | 9 of 9 scanning |
| Learning lessons applied | PASS as reported | 3 applied |
| Paid spend inside CA$100 | PASS (code) | no bypass found |
| Readback evidence usable | DEGRADED | 45–105 s; F-03 |

### Spec acceptance gates (`spec/03`), on `f9011cf94`

| Gate | Status | Evidence |
|---|---|---|
| A Infrastructure | PASS | `tests/test_acceptance_gates.py` Gate A |
| B Pattern safety | PASS | `test_compiler` 9, `test_reverse` 18, `test_twin` 8 passing |
| C Asset truth | PASS | `test_gates` 45 passing |
| D Commercial safety | PASS | `tests/test_acceptance_gates.py` Gate D |
| E Customer experience | PASS (unit) | `test_gates` Gate E tests passing |
| F Shadow graduation | PASS (simulated chain; nothing graduated) | `tests/test_acceptance_gates.py` Gate F |

Gate results: `tests/test_acceptance_gates.py` on `f9011cf94` passes all 23 gate tests
(A 5, B 5, C 3, D 4, E 4, F 2). Gates A, D and F are therefore PASS on fixtures. Gate F's own
test asserts that nothing has graduated past SHADOW, which matches F-01.

---

## Fix branches

All sub-agents ran on `claude-opus-5-5` in their own cloud containers, from
`origin/claude/w6-release-19h22`. "Lead-verified" means the audit lead fetched the branch, ran
the suites named on this machine, and ran the new test against the base commit to see it fail.

| Branch | Tip | Finding | Suites (lead-verified) | New test on base | State |
|---|---|---|---|---|---|
| `eng/audit-blob-reads` | `0a7872f33` | F-03 | `test_audit_blob_reads`, `test_evidence_perf`, `test_continuity`: 28 passing, 0 failing | 5 of 6 fail | READY |
| `eng/audit-build-state` | `b551e4049` | F-05 | `test_audit_build_state_current`: 4 passing, 0 failing (sub-agent reports 61 passing across touched suites) | 1 of 4 fails | READY (docs + test only) |
| `eng/audit-budget-scan` | `3279551bc` | F-06 | `test_audit_budget_scan`, `test_governor`, `test_codex_v0_postgres`: 26 passing, 0 failing | 2 of 9 fail | READY |
| `eng/audit-dead-code` | `f12032d62` | F-08 | `test_audit_module_reachability`: 6 passing, 0 failing | 2 of 6 fail | READY (test + inventory only) |
| `eng/audit-hygiene` | `b10c02e20` | F-09, F-10 | `test_audit_no_duplicate_dict_keys`, `test_w4_firstsale_deliverables`: 9 passing, 0 failing, 1 SKIP now reported | 3 fail | READY |
| `eng/audit-readback-phase` | not pushed at report time | F-02 | — | — | IN PROGRESS: session `session_015ZfGXnqvHiaxFARDgHuhp2` reported the fix done and 42 related suites running |
| `eng/audit-retention-guard` | not pushed at report time | F-04 | — | — | IN PROGRESS: session `session_015ZfGXqyeTy7kqqpP1gpCco` |
| `eng/audit-table-scans` | not pushed at report time | F-14 | — | — | IN PROGRESS: session `session_015ZfGXnVG4okSrCgfbeLCs1` |
| `eng/audit-utc-health` | not pushed at report time | F-12, F-13 | — | — | IN PROGRESS: session `session_015ZfGXoTvEWckVcKuL12GMC` |

The four in-progress branches are NOT verified and must not ship until someone fetches each,
runs its suites and sees its new test fail on the base, as was done for the five above.

Notes on the delivered branches:
- F-08: nothing was deleted. `brand/iterations.py` is imported by a research script, so it is
  not dead. The inventory lists 58 modules with no production importer: 43 unwired
  capabilities, 13 entry points or tools, 2 test helpers. The 43 remain unwired; the guard makes
  that explicit and stops the list growing silently. Wiring them is product work.
- F-06: `gateway/routing.py` `spent_this_month` was already bounded in SQL; only
  `anthropic.spent_this_month_cad` needed the fix.
- F-05: 61 of the 69 annotated entries are ancestors of production; 6 are not; 2 name no
  resolvable tip. The new block counts 37 deploys since the last full-suite run.

Ready branches are also listed in `research/audit/READY.txt` in the main checkout.

## Not fixed by a branch, with the exact reason

| Finding | Reason |
|---|---|
| F-01 | A release record must name a full, clean suite run on the exact shipped tree; no code change can create one. Then the phase transition is an owner act under the operator credential. |
| F-07 | The fix requires the owner's stepped-up signature on a standing grant. Shipping the check without it revokes a binding owner decision; creating the signature would forge an attestation. |
| F-11 | A separate worker service is recurring hosting spend, and Railway's documentation limits the On Failure policy to 10 restarts by plan, so lifting it is a plan decision. |

## Full acceptance suite on the production tree

Run `20261122T052554Z-3656` (JOBS=3, 1,080 suites) was still running when this report was
written. Record: `/home/user/bl-runs/audit-fullsuite/brambleloop/artifacts/suite_runs/20261122T052554Z-3656.json`;
log: scratchpad `audit/fullsuite.log`. Its `failing_suites` list is the red inventory of
production. It cannot be release-eligible for the merged tree; a second full run is needed after
the audit branches merge.

## Deviation from the brief

The brief asked for sub-agents through the Agent tool. That tool was not available to the audit
lead, so the fixes were assigned to nine child cloud sessions created with model
`claude-opus-5-5`, the mechanism the operator session already uses for its lanes. Each ran in
its own container under the same rules.
