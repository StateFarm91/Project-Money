# Independent review: A4b, held/refused draft -> enrichment -> re-draft (PR #27)

- Branch: `origin/opus2/a4b-enrichment`
- Reviewed SHA: `230b7d8d7afca812a4188a52f2ef278cb8048b18`. Review extended to the new head
  **`e230545cb67e4c9034398e82c328dd5e3b1af018`**, which only adds a retention fix in
  `ops/retention.py` (+15 lines).
- Merge base with `origin/claude/w5-INTEG1` (7c42e706): `7c42e706569af8d255d716133fc333d5c600c747`
- Commits since the base: `271ca8be` (OPUS2 department flow test), `230b7d8d` (A4b), `e230545c` (retention fix)
- Reviewer: independent and read-only. I pushed nothing, committed nothing and modified no branch.

## Verdict

| SHA | Verdict |
|---|---|
| 230b7d8d | **DO NOT SHIP**. It contains a regression that stops production retention (A4B-1), plus the issues below. |
| e230545c | **DO NOT SHIP** as the closure of A4b. A4B-1 is fixed, and correctly. A4B-2..A4B-7 remain. |

The change is safe in one respect. It never bypasses a gate: a re-draft is an ordinary `cir.draft`
job and passes every gate the first draft passed (intake, pre-engineering, funnel, construction,
provenance, compile, certification). It does not publish anything. Merging it would not harm the
catalogue.

It does not meet the acceptance criteria:
- No production code ever re-drafts anything (A4B-2).
- A concept that can never be drafted can end in the state `resolved` instead of a named
  terminal state (A4B-4).
- The "once" guarantee fails when two answers run at the same time (A4B-5).
- An "enrichment" can be any invented payload (A4B-3).
- One of the two attempt-bound guards is not covered by any test (A4B-7).

## Findings

### A4B-1: HIGH (230b7d8d), FIXED in e230545c. Production retention refused to run
`enrichment_requests._rows(db, action)` reads `AuditLog` using a variable action name.
`retention.unknown_read_actions()` therefore returned `['unresolved:creative/enrichment_requests.py::_rows']`.

Effects at 230b7d8d:
- `retention.apply` raises `RetentionRefused`.
- The `ops.retention` handler (runtime/release.py:8356) records `ops.retention_refused` and prunes **nothing**, on every run.
- `test_cost_governance_wave2` shows 4 FAIL / 35 OK. At the merge base it shows 0 FAIL.

e230545c:
- Adds `research.enrichment_requested` and `research.enrichment_answered` as `lifetime_total`.
  I confirmed both are in `PROTECTED_ACTIONS`.
- Declares the `_rows` site in `UNRESOLVED_READ_SITES`.
- Keeps `cir.draft_refused` as `windowed`.

Is the fix correct and complete? Yes.
- All of A4b's bounded state (rounds, resolved/exhausted) lives in the two new actions, and both are now never pruned.
- `cir.draft_refused` can safely stay windowed. A refusal row only ever opens or updates a request:
  - the `exhausted` skip is computed from the protected ANSWERED rows;
  - re-opening a `resolved` request needs a refusal row id greater than `answered_row`, and the round cap counts protected rows.
  So pruning old refusals cannot re-open or reset anything.
- Job-table pruning (45 d) frees `draft:<slug>:<fp>` keys. Re-answering is gated by the protected
  request state, not by the key, so that is safe too.
- Probe P7 at e230545c: `unknown_read_actions() == []`.

Side effect: because these rows are now protected for life, the churn in A4B-6 is never pruned.

### A4B-2: HIGH. The loop is not closed in production: `answer()` has no caller
`grep` over `src/` finds no caller of `enrichment_requests.answer` or `open_requests`. I checked
this branch, 993cc0cd (A4a ideation) and ebead3dd (A6).

The only production job, `research.enrichment_sweep`, writes `research.enrichment_requested` rows
and nothing else. No production component produces an enriched concept, and none re-drafts.

The acceptance criterion "a refused draft is enriched and re-drafted once" is shown only by the test,
which calls `E.answer(...)` directly with a payload it builds by hand. Wiring gap #2 is therefore
still open in production. Requests pile up with nobody consuming them, and the
`enrichment_sweep` cadence reports `work_done` for them.

### A4B-3: MEDIUM. "Enrichment" is not evidence-backed; any payload is accepted, including a wholesale substitution
`answer(db, slug, payload)` checks only that `fallback_constructions.plan(category, title, slug, rationale)` no longer refuses the payload. It does not:
- require any source, citation or evidence;
- tie the payload to the original concept;
- pin the fields the seed owns (category, risk_class, rationale).

The A4b test itself re-concepts `woodland-fox-amigurumi` as category `basket`, "Woodland Storage Basket", under the fox slug.

Probe P5 (real SQLite file and Worker): payload `category="basket", title="Totally Unrelated Basket", rationale="invented, no source"` gives:
- `answer` → accepted / resolved;
- the real `cir.draft` drafts `woodland-fox-amigurumi@1.0.0` as a `vessel`, with provenance `UNKNOWN: queued geometry ... not what concept_geometry produces for category 'amigurumi'`.

Downstream originality and provenance gates should still stop publication, so this is not a gate
bypass. But the acceptance criterion "enrichment adds only evidence-backed facts" is not enforced
in code, and a product with a fox-amigurumi identity is drafted as a basket.

### A4B-4: MEDIUM. The re-check disagrees with the handler, so a permanently undraftable concept ends as `resolved` (not a named terminal state), and `answer` claims success for a draft it never queued
`_recheck` runs only `FC.plan` on the payload. The `cir.draft` handler applies more construction
refusals:
- a tapestry basket needs 2 distinct colours;
- `ValueError`/`KeyError` construction failures;
- it uses `seed.rationale`, not `payload.rationale`.

Probe P2 (real Worker): refused fox draft → sweep → answer with `category=basket, title="Tapestry Basket", colors={"A":"cream"}`:
1. Round 1: recheck passes, so `accepted: True, state: resolved, job: 3`. The real handler then refuses: `"tapestry needs two distinct colours"`, `gate: construction`.
2. The sweep re-opens the request (rounds 1 < 2).
3. Round 2, with the same payload: the fingerprint is the same, so `enqueue` raises `DuplicateJob`. The `enqueue` wrapper swallows it and returns `None`. `answer` still returns `accepted: True, state: resolved, round: 2, job: None` and writes an ANSWERED `resolved` row.
4. The final state is `resolved` for good. No draft exists, the request never becomes `exhausted`, and `open_requests` no longer lists it.

The loop is bounded, but the terminal state is false: it reports success for a concept that was refused.

Fix:
- treat a re-refusal at `rounds >= MAX_ROUNDS` as `exhausted`;
- do not record `resolved` when no job was queued;
- make `_recheck` apply the handler's construction rules, or read the outcome of the drafted job.

### A4B-5: MEDIUM (latent until A4B-2 is wired). Two concurrent `answer()` calls both draft
`answer` reads `state()`, then enqueues, then writes ANSWERED. Nothing between those steps
(lease, lock, unique row or compare-and-set) stops a second caller.

Probe P3 runs two threads on one SQLite file. The real `_recheck` is wrapped with a barrier only
to make the two calls overlap. Result: both answers return `accepted: True, round: 1`, and the
queue holds two drafts, `draft:woodland-fox-amigurumi:6f1a669087cc` and `...:3736185030b2`. So
"re-drafted once" does not hold under concurrency or re-delivery. Use a per-slug, per-round
idempotency key, such as `enrich:<slug>:<round>`, or a unique audit row.

### A4B-6: LOW-MEDIUM. Unbounded audit churn when a slug has two different construction refusals
`sweep` dedups only against the *latest* request's `asks`. Inside the OPEN branch it does not skip
refusal rows that already have a request.

Probe P1: two refusal rows with different reasons for one slug. Each sweep writes **2**
`research.enrichment_requested` rows and reports `work_done=2`, indefinitely: 12 rows after 6
sweeps. This happens in practice: an original refusal plus a re-draft refused for another reason
(the A4B-4 path).

At the hourly cadence this is about 48 protected rows per day per slug. Since e230545c those rows
are never pruned, and the cadence counts as productive work.

### A4B-7: LOW. Test gaps on the attempt bound (surviving mutants)
The guard that stops re-opening a resolved request after `MAX_ROUNDS`
(`int(prior["rounds"]) >= MAX_ROUNDS` in `sweep`) is not tested:
- Mutant M5 removes it and survives.
- Without that guard, each resolve → re-draft refused → re-open cycle grants another round. That
  allows unbounded re-drafts, which is exactly the "no infinite retry" acceptance.
- M6 removes the `rid <= answered_row` guard and also survives.

### A4B-8: INFO
- The `construction_registry` paths in `_holds` and `_recheck` are dead and untested on this base.
  The module exists only on `opus2/p0-construction-registry` and `claude/w5-SECREVIEW-OPUS2R`,
  not on INTEG1, A4a or A6.
- A6 (ebead3dd) adds `cir.draft_refused` with `gate: "learning.hold"`. A4b ignores it by design,
  because the sweep only answers `gate == "construction"`.
- The new job type has the required entries:
  - `JOB_BANDS["research.enrichment_sweep"] = "proven_winner"`;
  - a `JOB_CLASS` build entry;
  - `crochet_engineer.allowed_job_types`;
  - `WORK_KEYS`;
  - an hourly `CADENCES` entry;
  - the autonomy map has been regenerated. As a result, Intelligence now lists `crochet_engineer`.
- The CIR shape is unchanged, so no contract bump is needed. The re-draft inputs add `enrichment_round` and the optional `brief`.
- No test was deleted or weakened. The diff under `tests/` adds two files only.
- Other products are unaffected (P6). Refusals for other slugs at the `learning.hold` and
  `radar.intake` gates open no request. A re-delivered or duplicate sweep writes nothing new (P4).

## Gate pass-through (re-draft)
The re-draft is `enqueue("crochet_engineer", "cir.draft", data, idempotency_key="draft:<slug>:<fp>")`.
It is the same handler, and it applies, in order:
1. the retired-alias route;
2. the intake-approval gate;
3. `preengineering.gate_concept`, unless established; this gate runs on the new payload;
4. funnel verification, for creative concepts;
5. `FC.plan`;
6. provenance and lineage;
7. the name-truth reading;
8. then compile, twin, reverse and certification.

No gate is skipped. The A4b test marks the product `_established` (a certified PatternVersion), so
the pre-engineering gate is skipped for **both** drafts. That matches the first draft's behaviour,
but it means the test never shows a non-established concept passing that gate on re-draft.

## Probes (real SQLite file + DurableQueue + Worker, registered handlers; no handler mocked)
Script: `/tmp/claude-0/-home-user-Project-Money/0aa334b9-5ba9-5fd2-9058-e50b4b8604ea/scratchpad/a4bprobes/probe_a4b.py`.
Output at e230545c: `/tmp/claude-0/-home-user-Project-Money/0aa334b9-5ba9-5fd2-9058-e50b4b8604ea/scratchpad/a4bprobes/probes_e230545c.json`.

| Probe | Result (identical at 230b7d8d and e230545c unless noted) |
|---|---|
| P1 two refusals, 6 sweeps | 12 request rows, work_done=2 every sweep (A4B-6) |
| P2 recheck/handler divergence | final state `resolved`, round 2 `accepted:True, job:None`, no draft (A4B-4) |
| P3 concurrent answers | two draft jobs, both round 1 (A4B-5) |
| P4 duplicate / re-delivered sweep | 1 → 1 row (OK) |
| P5 invented substitution | accepted, drafted as vessel, provenance UNKNOWN (A4B-3) |
| P6 other slugs / other gates | only the construction-refused slug has a request (OK) |
| P7 retention | 230b7d8d: `unresolved:creative/enrichment_requests.py::_rows`; e230545c: `[]`, both actions lifetime_total and protected |
| unchanged-fingerprint answer | consumes a round, stays open, then `exhausted`; no draft, no loop (OK; covered by the A4b test) |

## Mutants (against tests/test_opus2_enrichment_requests.py)
`enrichment_requests.py` is unchanged between 230b7d8d and e230545c, so these results apply to both.
Script: `/tmp/claude-0/-home-user-Project-Money/0aa334b9-5ba9-5fd2-9058-e50b4b8604ea/scratchpad/a4bprobes/mutants.sh`

| Mutant | Result |
|---|---|
| M1 idempotency_key=None | KILLED |
| M2 key = spent `draft:<slug>` | KILLED |
| M3 no MAX_ROUNDS in answer (never exhausts) | KILLED |
| M4 sweep re-opens exhausted | KILLED |
| M5 no `rounds >= MAX_ROUNDS` cap on reopening a resolved request | **SURVIVED** (A4B-7) |
| M6 no `rid <= answered_row` guard | **SURVIVED** (A4B-7) |
| M7 answer accepted when not OPEN | KILLED |
| M8 recheck removed | KILLED |
| M9 asks-dedup removed | KILLED |
| M10 fingerprint includes round | SURVIVED (benign: the state check blocks a repeat) |
| M11 gate filter removed | KILLED |

## Suites run (venv-integ4, one at a time)
| Suite | 230b7d8d | e230545c |
|---|---|---|
| test_opus2_enrichment_requests | PASS 3/3 | PASS 3/3 |
| test_cost_governance_wave2 | **FAIL 4** (35 OK); merge base 7c42e706: PASS | PASS 39/39 |
| test_w4_fmbatch1_retention_guard | UNKNOWN | PASS 5/5 |
| test_opus2_department_flow | PASS | PASS |
| test_swarm_runtime | PASS 10/10 | PASS 10/10 |
| test_w3_k11_authority | PASS | PASS 18 |
| test_w4_f454_agents | PASS | PASS |
| test_v11_autonomy_timeline | PASS 6/6 | PASS 6/6 |
| test_fallback_draft_provenance | UNKNOWN | PASS |
| test_w5_concept_intake | UNKNOWN | PASS 39 |
| test_opus2_draft_constructions | UNKNOWN | PASS 18 |
| test_opus2_knowledge_gaps | UNKNOWN | PASS 9 |
| test_w4_c12_wiring | UNKNOWN | PASS 4 |
| test_launch0 | UNKNOWN | PASS 52 |
| test_shadow | UNKNOWN | PASS 10/10 (2587 s, loaded host) |
| test_cert_wiring | UNKNOWN (killed by the 1500 s timeout, load ~9) | **FAIL 5**. The first failure is `queue did not drain: 322 jobs in 1584s`. That is the test's own wall-clock drain budget, exceeded while host load was 6 to 9 on 4 cores. The other 4 failures (`agent_quality never called`, `retirement_review not reached`, `culture.radar.memory not called`, `row 144 claimed covered`) follow from the drain not finishing. I did not run the merge base on this host, so whether A4b caused this is **UNKNOWN**. It is not a PASS. Re-run on an idle host and compare with 7c42e706. |

Logs:
- 230b7d8d: `/tmp/claude-0/-home-user-Project-Money/0aa334b9-5ba9-5fd2-9058-e50b4b8604ea/scratchpad/a4bprobes/suites/`
- e230545c: `/tmp/claude-0/-home-user-Project-Money/0aa334b9-5ba9-5fd2-9058-e50b4b8604ea/scratchpad/a4bprobes/suites2/`

## Merge cleanliness (`git merge-tree --write-tree`)
| Pair | 230b7d8d | e230545c |
|---|---|---|
| vs origin/claude/w5-INTEG1 (7c42e706) | clean | clean |
| vs claude/w5-A4a-research-to-concept 993cc0cd | clean | clean |
| vs opus2/a6-learning-to-design ebead3dd | clean | clean |
| 993cc0cd vs ebead3dd | clean | n/a |

No textual conflicts. All three branches touch `runtime/pipeline.py`, but in separate hunks:
- A4b: `WORK_KEYS` and the import list;
- A4a: radar scan/score;
- A6: the `cir.draft` handler body.

No semantic conflict was found. A6's new `learning.hold` refusals fall outside A4b's construction filter.

## Required before SHIP
1. A4B-2: wire a production caller for `answer` that builds an enriched concept from recorded
   research, or re-scope the acceptance and the COORDINATION claim to "request side only".
2. A4B-4: name the terminal state correctly. A re-refusal at `MAX_ROUNDS` becomes `exhausted`,
   and `resolved` is never written without a queued job.
3. A4B-5: per-round idempotency for `answer`.
4. A4B-6: dedup the sweep against every request already written for a refusal row.
5. A4B-7: tests that kill M5 and M6.
6. A4B-3: require evidence or source references in the payload, and pin the seed-owned fields, or refuse a category change under the same slug.
