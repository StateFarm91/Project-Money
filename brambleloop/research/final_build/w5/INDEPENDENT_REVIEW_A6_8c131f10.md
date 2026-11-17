# Independent review: A6 P0-LEARNING-INTO-DESIGN (consumer side), exact SHA 8c131f10

- Branch: `origin/opus2/a6-learning-to-design` @ `8c131f10372e406ab0d1922920c14bc0f1586edd`
- Base: `claude/w5-INTEG1` @ `7c42e706` (that is still origin's tip at review time)
- Commits: 7c9306e3 (WIP), ebead3dd, 8c131f10
- Files: `improve/consume.py` (+210, append only: confirmed), `runtime/pipeline.py` (+210/-9),
  `runtime/engineering_ops.py` (+8), `ops/retention.py` (+9), new
  `tests/test_w5_a6_learning_to_design.py`. No existing test was modified or deleted.
- Method: read-only, in detached scratch worktrees (`a6rev` for suites, `a6mut` for mutants).
  Nothing was committed, pushed or deployed. Both worktrees were clean after the runs.

## Verdict: DO NOT SHIP 8c131f10

Most of the mechanism holds. Approved values come only from closed vocabularies, so a lesson's
free text never becomes geometry. Every lesson-shaped draft still goes through compile and
certify. With no lessons the draft is byte-identical, and test_launch0 passes. The construction
guards for "the concept names its construction" and FORM_CONSTRUCTIONS are tested and kill
their mutants.

Two defects block the ship:

1. **A6-1 (HIGH, Product Truth).** An approved yarn-weight lesson certifies a pattern that
   states the wrong hook size.
2. **A6-2 (MEDIUM, honesty).** `lesson.acted_on` says the design changed when the CIR is
   byte-identical (same fingerprint).

Third, eight of the twelve guards I mutated are not protected by any test, including the
approver-role check and idempotency. Those are the authority and replay properties this
change claims.

## Findings

### A6-1 HIGH: an approved yarn weight certifies with a fixed 5.0 mm hook (Product Truth)

`creative.prototype.gauge_for` always returns `hook_mm=5.0`, whatever the weight. Before A6
every draft path used worsted, and a 5.0 mm hook fits worsted. A6 is the first runtime path
that drafts a non-worsted yarn: `_draft_creative` passes `yarn_weight=learning[...]`, and the
radar fallback sets `concept.yarn_weight`. The approved weights include
sport/dk/bulky/chunky. Nothing in compile or certify compares the hook with the weight. I
grepped `gates/`, `cir/` and `quality/`: no hook-band check exists.

Repro (`scratchpad/probes/probe3b.py`, and `probe1.py` for the radar path):
- Creative path, approve `yarn_weight=bulky` on a lesson matching the stocking winner. Result:
  `Gauge(9.5 sts, 10.5 rows, sc, hook_mm=5.0, yarn_weight='bulky')`. `gate.certify` returns
  **`granted: True`** with a release hash, and `PatternVersion 1.0.0 certified=True`.
- Radar fallback, `nordic-forest-basket` with `bulky`. Result: hook 5.0 mm, materials
  "bulky acrylic". Compile ok and certify done, and the chain continues to `gate.lanes`,
  `listing.draft` and `collection.assemble`.
- `dk` on the creative path gives `hook_mm=5.0` with `yarn_weight='light'`.

The usual hook ranges are about 3.5–4.5 mm for DK and 6.5–9 mm for bulky. A buyer is told to
use a 5.0 mm hook that cannot make the stated gauge in that yarn. The certificate, PDF, listing
facts (`listing_assets`, `pdf.py`, `tips.py`, `support/concierge.py` all print `hook_mm`) and
the release hash all carry the wrong hook. The author flagged this risk, and it is real and
reaches certification.

Required fix, before or with A6:
- Derive the hook from the weight band in `gauge_for`.
- Make certification refuse a hook outside the declared yarn's band, as a deterministic gauge
  finding.
- Add a test that a dk and a bulky lesson-shaped draft either certify with a band hook or are
  refused.

The interim alternative is to remove `yarn_weight` from `DESIGN_PARAMETERS` until the hook is
derived. A5's `GAUGE_FROM_YARN_BAND` repair also uses `gauge_for`, so it inherits the same
fixed hook.

Related (LOW): the flat-panel fallback (`concept_to_cir`) keeps `width_stitches` and `rows`
fixed when the yarn changes. The finished size therefore grows or shrinks by the gauge ratio
(+31% for worsted to bulky). The CIR stays self-consistent, but the declared size moves away
from the brief. The vessel/cosy/pouch/tapestry families re-derive counts from size, so they
are fine.

### A6-2 MEDIUM: `lesson.acted_on` and `acted_on_by` record a design change that did not happen

`_preferred_construction` compares only the *concept* construction (`want != current`), not
`ENGINE_ROUTE[want] != ENGINE_ROUTE[current]`. `author()` uses only the engine route, so a
preference between two concept constructions with the same route gives the same CIR.

Repro (`probe2.py`): the stocking winner is `in_the_round`. I approved `seamless_tube`, which
FORM_CONSTRUCTIONS allows for a stocking, and both route to `joined_rounds`. Result:
`construction joined_rounds -> joined_rounds; same geometry: True; fp differ: False`. Even so,
`out["learning"]["applied"] == [lid]`, a `lesson.acted_on` row
`{"parameter": "construction", "from": "in_the_round", "to": "seamless_tube"}` is written, and
the lesson gets `acted_on_by` pattern_engineering.

Effects:
- `compounding()` and learning metrics count a change that made no difference.
- The non-negotiable "never claim … until verified" is broken.
- Codex's contract ("Record a learning action only after a consumer actually changes its
  decision") is broken.

The test helper `_other_construction` deliberately avoids the same-route case, so the test
hides this.

Two more paths overclaim the same way:
- **Fitted garments.** `author()` ignores `yarn_weight` for `form == "fitted_garment"` (it
  builds through `garment_design.design_for` with its own gauge). An approved yarn lesson on a
  garment is recorded as `yarn_weight worsted -> X` while the CIR does not change. Found by
  reading the code, not executed.

Fix: record an application only when the produced CIR differs from the no-lesson draft in the
changed parameter, for example `cir.construction`, `cir.gauge.yarn_weight` or the fingerprint
against a baseline author. Otherwise report it as "applied: false, no effect".

### A6-3 MEDIUM: the approval authority is an unauthenticated string in an unsigned AuditLog row, and the read path does not re-check independence

- `approve_for_design(approved_by="owner")` trusts whatever string the caller passes.
  `" OWNER "` normalises to `owner` and is accepted (probe P2c). Nothing proves the owner took
  this action.
- `_design_approval` (the read side) accepts any `AuditLog` row with
  `action="lesson.design_approved"` and an actor in {owner, evaluator}. It does not re-check
  origin or consumer independence, and does not re-check withdrawal (withdrawal is covered
  separately, because `bus.inbox` filters withdrawn and superseded lessons).
  - Probe P2: a raw `AuditLog(actor="owner", action="lesson.design_approved", …)` written
    without `approve_for_design` is honoured.
  - Probe P2b: a lesson whose `origin_cell="evaluator"`, with an `evaluator` approval row, is
    honoured at read even though `approve_for_design` would refuse it.
- AuditLog is append-only by convention only: there is no hash chain or digest, and the row
  does not bind the lesson's statement or evidence.
- **Mitigation:** today no runtime handler, CLI or API calls `approve_for_design`, and no
  handler writes that action. Only test code can approve. That also means **the feature is
  unreachable in production**: the owner has no surface to approve a lesson. BUILD_STATE must
  not describe A6 as live learning.
- Judging roles today are only `evaluator`. An author cannot approve its own lesson under a
  different role name *through* `approve_for_design`, because the approver set is closed to
  {owner, evaluator} and the origin check is a normalised string equality. A forged row can
  still do it, as P2b shows.

Fix: on read, re-apply every approve-time check (origin ≠ approver, consumer ≠ approver,
subject allowed). Bind the approval to a digest of the lesson (statement, subject,
evidence_ref, origin). Best of all, move approval onto Codex's `DesignRule` path (see the
coexistence section).

### A6-4 MEDIUM (merge/semantic): the cir.revise hold conflicts with A5 and bypasses A5's named-hold contract

- Textual conflict with `origin/claude/w5-A5-correction-loop` 717c7925 in
  `runtime/engineering_ops.py` `handle_cir_revise` (one hunk). A6 adds the learning-hold block
  where A5 rewrote the whole preamble (open_hold check, revision cap, `already` fingerprint
  check, `stage`-aware compile check).
- Semantic: A5 requires every refusal to end in revision, a **named hold**
  (`record_hold`: P2 incident `correction-hold:<slug>@<version>` plus a `cir.correction_held`
  row) or an evidence wait. A6's revise hold returns
  `{"drafted": False, "gate": "learning.hold", "revised": False}`. It has no `held: True` key,
  calls no `record_hold` and opens no incident, so a learning-held version would leave the
  correction loop with no named hold. It also writes a `cir.draft_refused` audit row from a
  revise job (wrong verb; `intel.knowledge_gaps` filters it by `gate=="construction"`, so gap
  counts are not affected).
- Placement: at A6 the hold sits after `if result.ok: return`. In A5 that line becomes
  `if stage == "compile" and result.ok`, and A5 also sends certify, quality and assets
  refusals through cir.revise. The resolution must decide whether a learning hold stops those
  stages too. If it does, it must go through `record_hold(stage=..., reason="approved learning
  holds <construction>")`.
- Vocabulary mismatch:
  - cir.revise checks the hold against `cir.construction`, which is one of
    flat_rows/joined_rounds/spiral_rounds. Only `flat_rows` is in `DESIGN_CONSTRUCTIONS`, so a
    hold can never match a joined_rounds or spiral_rounds CIR at revise.
  - The radar draft checks holds against the fallback family (flat_panel, vessel, …), and the
    creative draft checks against the concept vocabulary.
  - So a `hold_construction=flat_rows` approval holds a radar flat_panel product at revise but
    not at draft. The same approval means different things at different call sites.
- A5's `GAUGE_FROM_YARN_BAND` repair also inherits the 5.0 mm hook (A6-1).

### A6-5 MEDIUM: test coverage. Eight of twelve guard mutants survive

See the mutant table. With no test, a change could weaken these silently:
- the approver-role check (either side)
- yarn-conflict cancellation
- the ENGINE_ROUTE guard
- `record_application` and `approve_for_design` idempotency
- the read-side subject check
- hold-to-construction matching

Idempotency itself works on the real code: probe P5 re-drafted the same product, and there
was still one `lesson.acted_on` row and one `acted_on_by` entry. No test locks this in, though.

The acceptance test drains `cir.compile` only, never `gate.certify`. I certified the
construction-changed and yarn-changed drafts by hand (probe3, probe3b); certification granted
both, which is how A6-1 surfaced.

### A6-6 LOW: approval semantics gaps
- Only the newest approval per lesson counts. A later approval for a different parameter
  silently replaces an earlier one (P8: a yarn approval was masked by a later hold approval).
  There is also no way to revoke an approval other than withdrawing the whole lesson.
- `hold_construction` and `yarn_weight` have no subject restriction. A
  `construction_preference` lesson can be approved as a hold (P7), and any subject (for
  example `search_language`) can set a yarn weight.
- Holds have no conflict rule, unlike yarn and construction. That is acceptable, since a hold
  only ever refuses, but say so in the documentation.
- `record_application` checks for an existing row and then inserts, with no unique
  constraint. Two concurrent drafts could each write a row. Low risk while
  `cir.draft` idempotency keys hold.

### A6-7 LOW: the creative path writes no learning into CIR provenance
On the radar path, `improve.consume.design_directives:lesson-N` is appended to the
provenance primitives. On the creative path it is not: the probe's primitives were only the
author, geometry and gauge entries. So a certified creative CIR carries no record of which
lesson shaped it. That is a prerequisite for the Codex pin contract (see below).

### Checked and found sound
- Learning never bypasses compile, certify, the funnel or pre-engineering. All A6 changes come
  after the funnel and pre-engineering gates and before `author`, and the result is enqueued
  into the ordinary `cir.compile` → `gate.certify` chain. The title is unchanged, so the name
  gate sees the same words. Risk class comes from the form, not the construction, so the
  children's and closed-form path is unchanged.
- The fallback when a preference cannot be authored (`_drop_construction_change`) re-authors
  the concept as carried and reports why. The yarn change is kept.
- A withdrawn or superseded lesson never applies, because `bus.inbox` filters on both and
  `approve_for_design` refuses both.
- Byte-identical with no lessons: `_design_learning` returns `{}`, the compile idempotency key
  is unchanged, and `_fallback_lineage` (pure) only moved. test_launch0 passed 52/52. One
  minor exception: the creative-path return dict now always includes `construction`, which
  adds an output key but does not change the CIR.
- Retention: `lesson.design_approved` and `lesson.acted_on` are classified `lifetime_total`.
  That is correct, because both are read over all rows for authority and dedup.
  test_w4_fmbatch1_retention_guard passes. A5's retention additions auto-merge.

## Codex coexistence assessment (codex/p0-learning-reference c7bda4e, `CODEX_LEARNING_A6_CONTRACT.md`)

**Today the two would be competing approval authorities.** A6 approves through free-standing
`AuditLog lesson.design_approved` rows: an actor string, no digest and no evaluation. Codex
approves through `DesignRule` rows:
- the rule must have `state="approved"` and `active_slot=1`;
- `approved_by` must differ from `producer`;
- a `design_knowledge.rule_approved` audit row must carry `rule_digest` and
  `evaluation_digest`;
- the evaluation evidence must be re-validated.

Both would change designs, through different consumers (cir.draft parameters against the
writer's finishing checklist), and neither knows about the other. A6 also writes
`improve.consume.design_directives:lesson-N` into `primitives_used`, the same field where
Codex encodes `learning_rule:<rule>:<id>:<version>:<rule_digest>:<evaluation_digest>`.
Codex's `verify_cir_pins` would ignore A6's marker, so certification would accept a
lesson-shaped CIR with no verified pin. Pins are only checked if present, and A6 emits none.

The two can coexist, but only if A6's AuditLog approval is demoted. It must not stay an
authority. The follow-up must:

1. **Keep one authority.**
   - Register A6's three parameters as closed-vocabulary `DesignRule` keys in
     `design_knowledge.RULES`, for example `prefer_construction{construction}`,
     `yarn_weight{weight}` and `hold_construction{construction}`, with closed parameter sets
     equal to `DESIGN_PARAMETERS`, plus a scope such as `{"draft": "construction" | "yarn"}`.
   - Make the lesson the rule's provenance source (`_SOURCES["lesson"]` already exists).
   - Turn `approve_for_design` into "propose a DesignRule from lesson N". Codex's independent
     approval and evaluation then decide.
   - Make `_design_approval` and `design_directives` read only
     `design_knowledge.applicable()` / `verify_pins()`.
   - Either retire `lesson.design_approved` (stop honouring it) or migrate existing rows into
     proposals. Both must not be honoured at once.
2. **Freeze pins.** `cir.draft` / `_draft_creative` must call `freeze_pins(db, cir, pins)` on
   every lesson-shaped CIR, on both the creative and radar paths (A6-7). It must bump the CIR
   contract to v3 as the Codex contract requires. If v3 also stores structured pins, it must
   check they exactly match the encoded directives.
3. **Verify at the gates.** The certificate, release, quality and PDF paths must call
   `verify_cir_pins` and refuse unverifiable pins. A CIR shaped by learning with no pin must be
   refused rather than certified, so the `design_directives:lesson-N` primitive must be
   replaced by, or accompanied by, a verified pin.
4. **Record only real changes.** Write `lesson.acted_on` only when the frozen CIR actually
   differs (fixes A6-2), and reference the pin (rule_id/version/digest) instead of a bare
   AuditLog approval id.
5. **Resolve the single-active-rule limit.** Codex allows "only one rule can be active".
   A6's conflict-cancellation rule (two values cancel) has to fit that model. Either one active
   rule per scope and parameter, or Codex's "multi-rule baselines" must land first.
6. **Keep the closed vocabularies in one module.** Today they are duplicated as literals in
   `consume.py`, with only a test asserting equality.

## Suites (run at 8c131f10, `/home/user/bl-runs/venv-integ4/bin/python`, one at a time; the machine was shared with about seven other `test_shadow` runs, load around 6–7)

| Suite | Result |
|---|---|
| test_w5_a6_learning_to_design | PASS 6/6 (53 s) |
| test_launch0 | PASS 52 OK |
| test_compiler | PASS 9 OK |
| test_reverse | PASS 18 OK |
| test_twin | PASS 8 OK |
| test_swarm_runtime | PASS 10 OK |
| test_w3_k11_authority | PASS ("0 failing") |
| test_first_customer_gate | PASS 12 passing, 0 failing |
| test_cost_governance_wave2 | PASS 39 OK |
| test_w4_fmbatch1_retention_guard | PASS 5 OK |
| test_opus2_commercial_lessons (imports consume) | PASS |
| test_v11_learn_loops (imports consume) | PASS |
| test_w4_improvemetrics (imports consume) | PASS |
| test_w4_marketintel (imports consume) | PASS |
| test_w4_mjs_findings (imports consume) | PASS |
| test_shadow | SHADOW_RESULT |
| test_cert_design_pipeline (A6 test's driver) | CDP_RESULT |
| The author's "38 focused suites" | UNKNOWN (not all re-run) |

## Mutants (12 on the A6 guards, each run against test_w5_a6_learning_to_design)

| Mutant | Result |
|---|---|
| M1a approve-side approver-role check removed | **SURVIVED** |
| M1b read-side approver-role check removed | **SURVIVED** |
| M2a construction conflicts not cancelled | KILLED |
| M2b yarn conflicts not cancelled | **SURVIVED** |
| M3a FORM_CONSTRUCTIONS guard removed | KILLED |
| M3b ENGINE_ROUTE guard removed | **SURVIVED** |
| M4 `record_application` dedup removed (idempotency) | **SURVIVED** |
| M5 origin/consumer independence removed | KILLED |
| M6 read-side subject check (`_subject_may_set`) removed | **SURVIVED** |
| M7 "concept names its construction" guard removed | KILLED |
| M8 hold ignores which construction | **SURVIVED** |
| M9 `approve_for_design` idempotency removed | **SURVIVED** |

4 killed, 8 survived. Of the four guards the brief asked about:
- the role check survives on both sides (the test only tries actors that the origin or
  consumer checks also catch);
- conflict cancellation is killed for construction and survives for yarn;
- the FORM_CONSTRUCTIONS guard is killed;
- idempotency survives on both functions.

Mutant script: `scratchpad/probes/mutants.py`.

## Merge cleanliness (`git merge-tree --write-tree 8c131f10 <other>`)

| Other | Result |
|---|---|
| origin/claude/w5-INTEG1 7c42e706 | clean (it is the base) |
| opus2/a4a-research-to-concept 3dc3e68c | clean (both touch pipeline.py; auto-merged) |
| opus2/a4b-enrichment e230545c | clean (pipeline.py and retention.py auto-merged) |
| opus2/a2-name-object 51f87859 | clean (touches fallback_constructions.py only) |
| origin/claude/w5-A5-correction-loop 717c7925 | **CONFLICT** in `runtime/engineering_ops.py` (`handle_cir_revise` preamble; A6-4). pipeline.py and retention.py auto-merge. |

Clean textual merges were not semantically tested together. Merged suites: UNKNOWN.

## Probe files
`/tmp/claude-0/-home-user-Project-Money/0aa334b9-5ba9-5fd2-9058-e50b4b8604ea/scratchpad/probes/`
holds `probe1.py` (radar yarn, idempotency, forged and self approval, hold subject, masking),
`probe2.py` (same-route construction, creative yarn), `probe3.py` / `probe3b.py` (certify
chain) and `mutants.py`.
