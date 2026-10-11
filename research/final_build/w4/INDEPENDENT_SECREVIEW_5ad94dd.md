# Independent security review: Laura minimal release candidate 5ad94dd

- Date: 2026-10-11 (UTC). Reviewer: independent security reviewer (did not write this code).
- Scope: `git diff e17cb9d 5ad94dd` (20 files, +3084/-24). e17cb9d is the Etsy-button candidate,
  a descendant of production 0417f35. 5ad94dd adds:
  - 089add7, cherry-picked from bbe50e4 (FINHEALTH);
  - dcda600, 401d9a2, 7bf9a69, b2f03de, 817b8ea and 32c5f1f (LAURA1, the CA$0.50/day budget);
  - 5ad94dd (tests only).
- Mode: read-only, in a detached worktree at 5ad94dd. No Railway or Etsy calls, nothing spent,
  and no secrets were read.
- Tests: run one at a time, each with a private TMPDIR that was deleted afterwards.
  - `test_w4_laura1_budget` 4/4
  - `test_w4_laura1_briefing` 19/19
  - `test_w4_finhealth` 11/11
  - `test_w3_laura_core_identity`: all OK
  - Ad hoc: every `brambleloop.*` module imports cleanly at 5ad94dd (0 failures). This shows
    the subset needs nothing it does not carry.
- Line numbers refer to 5ad94dd under `brambleloop/src/brambleloop/`.

## Verdict: NO BLOCKER

## Faithful subset of e3747c5: CONFIRMED

Ten of the 13 `src/` files this diff touches are byte-identical to e3747c5:

- `agents/registry.py`
- `gateway/anthropic.py`
- `gateway/laura_briefing.py`
- `gateway/routing.py`
- `laura/agency/briefing.py`
- `laura/agency/talk.py`
- `finance/spend_report.py`
- `finance/accounting/schema.py`
- `finance/economics.py`
- `core/` is the exception: see the list below.

The three files that differ do so only by content e3747c5 adds from other lanes:

- `app/main.py`: the 5ad94dd hunks are exactly FINHEALTH's `/api/verify` changes
  (`ceiling_audit`, `dead_letter_digest`). e3747c5 adds the other lanes' routes on top.
- `ops/rebuild_graph.py`: 5ad94dd uses FINHEALTH's `_bounded_key`. e3747c5 unifies it into
  FMGATE's `job_key`. Both are deterministic and stay within 200 characters (the prefix is cut
  to 129 plus the 71-character `sha256=` digest), so idempotency holds.
- `queue/durable.py`: 5ad94dd adds `dead_letter_digest` only. e3747c5 also has AUTONOMY's
  `fit_idempotency_key`, which nothing in 5ad94dd references.
- `core/decision_index.json`: differs by one entry from another lane.

Left out on purpose, and confirmed unneeded:

- `laura/executive/loop.py`, which carries AUTONOMY's `due_cutoff`. No 5ad94dd code references
  `due_cutoff`, `company_work_waiting` or `fit_idempotency_key`.
- No ORM model, column or table changes, so no migration is involved.

## Spend safety: PASS

- **CA$0 is refused before the provider is called.** `gateway/anthropic.py:217`
  (`agent_daily_ceiling`) now returns a 0.0 ceiling, not `None`, for a registered agent at
  CA$0. `check_budget_cad` therefore refuses any positive estimate before the request is made.
  Before this, a CA$0 agent's first call was billed and only refused afterwards. This is
  stricter only, and it affects `coo` and `learn`, which declare no spend.
- **Laura's CA$0.50/day.**
  - Declared at `agents/registry.py:774-785` and reconciled by `seed_defaults` on deploy (the
    existing declarative mechanism). The owner decision D-W4-LAURA1-BUDGET is in
    `DECISION_LOG.md`, recorded as relayed by the coordinator.
  - Only `gateway/laura_briefing.py` bills agent `laura`. `laura/agency/phrasing.py` bills
    `orchestrator`, and the executive tick makes no model call. The budget therefore covers
    the briefing synthesis only.
- **Order of checks** (`laura_briefing.synthesize`, `:108`):
  1. Laura's permission is ≤ 0: audited refusal (`spend_report.record_refusal`), no call.
  2. No provider is configured: no call.
  3. `failover.gateway_for`, which checks the month and the agent's day for each model,
     otherwise PARK.
  4. `ModelGateway.complete_json`, then `check_budget_cad`: month, provider and agent day,
     reserved atomically under `budget_lock` before the request.

  `test_cap_is_checked_and_reserved_before_the_provider_call`,
  `test_a_call_that_would_exceed_the_daily_cap_is_refused_with_no_provider_call` and
  `test_the_monthly_ceiling_still_applies_when_lauras_day_has_room` all pass. The monthly
  ceiling, the D-1 NaN guards and the refusal of a non-finite permission are unchanged.
  `laura_daily_permission` reads NaN or inf as 0.
- **Nothing can raise a ceiling at runtime.** No new route or action writes `Agent` ceilings or
  `SpendLimit`. The budget changes only through a reviewed code deploy, as for every agent
  ceiling.
- **Fallback.** Every refusal, provider error or malformed output returns
  `source: unavailable` with a reason, and the deterministic briefing answers. Nothing raises
  for money.

## Prompt injection and evidence-only rendering: PASS

- The model returns only evidence ids per component. `briefing.validate` (`:653`) accepts a
  section only when:
  - it has exactly `{component, evidence}`;
  - the component was requested and appears once (a repeat fails closed);
  - every id is in that section's allow-list, with no duplicates.
- Decisions and facts/unknowns are always rendered deterministically, never from the model's
  output. Mandatory records always come first.
- Record text reaches the model only inside `DATA_OPEN`/`DATA_CLOSE` blocks. `<<<` and `>>>`
  are neutralised and records are flattened to one line (`laura_briefing._data`, `:37`). On
  the owner's screen each record is quoted (`briefing._q`, `:168`): quotes and brackets are
  rewritten, so a record cannot close its own quotation or forge an `[E#]` citation, and
  control characters are stripped.
- The provenance label comes from the reader's declared basis, never from the record's text.
- `test_record_text_is_quoted_data_never_deleted_and_never_an_instruction` passes.

## Private memory: PASS

- The pack reads business readers only.
- `_is_private` (`briefing.py:146`) drops any item whose source or section names
  private/spouse.
- `converse` still runs `reject_private` on the question (`talk.py:375`).
- Follow-ups read only the same session's last briefing (`last_briefing`, `:822`, filtered on
  `session_public_id`).
- Authority is unchanged: GREEN, with `FORBIDDEN_COMBINATIONS["laura"]` unchanged.
  `test_laura_agent_is_green_zero_ceiling_and_structurally_bounded` passes.

## Auth on Laura endpoints: PASS

`talk.converse` is reached only from:

- `POST /api/cc/laura/ask` (`app/command_center/api.py:613`);
- `presence.respond`, behind `POST /api/cc/laura/voice`.

Both are under `/api/cc/`, so they need the owner session, same-origin, CSRF, a nonce and the
mutation rate limit. No new route was added. The question is capped at 500 characters.

## Secrets: PASS

- No credential is placed in the prompt, the response or the audit. The briefing's spend line
  states only CA$ figures.
- `dead_letter_digest` adds the first line of a job's `last_error` (capped at 200 characters)
  to the public `/api/verify`. **INFO:** job error heads are already public at e17cb9d
  (`main.py` has `last_error[:200]` in other public views), so this exposes nothing new.

## Shadow mode: PASS

The diff adds no Etsy write, publish, activation, outbound message or phase change.

## Findings

- **INFO-1:** the CA$0.50/day budget relies on DECISION_LOG text relayed by the coordinator.
  The owner should confirm it once. Raising it again means another code change.
- **INFO-2:** CA$0 agents (`coo`, `learn`) are now refused before any call. This is
  intentional and fails safe. Any model call made under those agents now fails visibly.

No blocker.
