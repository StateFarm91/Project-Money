# Build 2 certification repair wave — common brief

You are repairing Brambleloop Studio (a crochet-pattern publishing system) requirements that
an independent function-level audit REFUTED at commit 9434c53. Read the repository's
`CLAUDE.md`, `brambleloop/BUILD_STATE.md` (skim) and `brambleloop/DECISION_LOG.md` (skim) first.

## Your workspace
- Your own git worktree: `<WT>` on branch `claude/b2r-<NAME>` (from 9d6eed2). Work ONLY there;
  use absolute paths (the shell cwd resets). Code is under `<WT>/brambleloop/src/brambleloop/`.
- Interpreter: `/home/user/Project-Money/brambleloop/.venv/bin/python` (call it $PY). Tests are
  scripts: `cd <WT>/brambleloop && $PY tests/test_x.py` (prints OK/FAIL lines and "n passing, 0 failing" or PASS).
- Commit on your branch often (checkpoint so an interruption loses nothing). Do NOT push, do NOT
  touch other branches, do NOT edit `src/brambleloop/build2/requirements.json`,
  `research/BUILD2_CERTIFICATION.md`, `BUILD_STATE.md` or `DECISION_LOG.md` (the lead owns them).
- Commit message trailer (exactly):
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01GpoRAgr4kBWxi1752HufQh

## The standard every row must meet (this is what the auditor checks)
A row is COMPLETE only when the behaviour its `body` describes actually happens in the RUNNING
system: a registered handler (`@handlers.register` in runtime/release.py, runtime/pipeline.py,
runtime/commerce_readings.py), enqueued by a cadence (`CADENCES` in runtime/worker.py) or by an
upstream handler, or an HTTP route that computes FROM THE DATABASE — and the result is ACTED ON
(it changes what a later job does, blocks something, enqueues something, or raises an incident),
not merely written to an audit row nobody reads. Specifically forbidden:
- hard-coded empty/constant inputs (`Observed()`, `[]`, `{}`, `None`, fixed constants) where the
  real value is in the DB; a gate whose outcome is constant; a library only called by tests;
  a static `state()` route that returns a description.
- new job types need: handler, cadence or upstream enqueue, a grant in agents/registry.py
  `allowed_job_types` for the owning agent, a band in swarm/orchestrate.py JOB_BANDS, and where
  relevant a retention entry in ops/retention.py KNOWN_READ_ACTIONS. Look at how existing
  cadences (e.g. commerce_readings, seasonal_engine) do it and match that idiom.
Prove each row with a HANDLER-LEVEL test (enqueue/run the job through the worker or call the
handler with a real DB built the way existing tests/test_cert_*.py do it, seed real rows, and
assert the downstream effect). Library-level unit tests are not proof.

## Gates (only when genuinely unavoidable)
A row may remain gated only when the missing input is real: `owner` actions (KYC, legal, banking,
spend, ad authority, buying products), `data` that does not exist yet (customers/orders, live
listings' traffic), or `external` (Product-Only Visual V1 image generation: model_bearing_render).
Even then the BUILT half must run in the live runtime today on DB data (on cadence), so that the day
the input arrives it is read — and with no data it must honestly record UNMEASURED, not fake a value.
Gate names in use: see build2/closure.py OWNER_GATES / DATA_GATES and build2/executor.py Gate(...).
If something can be built now in software, BUILD it; do not park it.

## Absolute constraints
Shadow mode only (BRAMBLELOOP_PHASE=shadow). No network calls to paid services, no Etsy writes, no
publishing, no ads, no spend, no deploy, no merge. Never expose or store secrets. Never weaken,
skip or delete an existing test, threshold, validator, Product Truth check, provenance rule or
certification criterion; if an existing test breaks because behaviour legitimately changed, fix the
test to assert the new stronger behaviour and say so. Never invent data, calibration, provenance,
owner decisions or customer outcomes. Purchased benchmark material is never committed.

## Coordination
Other agents are working in parallel on other clusters in their own worktrees. Keep edits to shared
registration files (runtime/worker.py CADENCES, agents/registry.py, swarm/orchestrate.py JOB_BANDS,
ops/retention.py, app/main.py, runtime/release.py) small and localised (append entries, don't
reorder or reformat) so the lead can merge. If a row in your list truly depends on another cluster's
work, say so rather than duplicating it.

## Before you finish
Run every test file you touched plus `tests/test_closure.py tests/test_platform.py
tests/test_cert_orchestration.py tests/test_capability_gates.py tests/test_executor.py` and any
test_cert_* file covering code you changed; all must pass. Commit. Then reply with a JSON block:
[{"id": n, "status": "covered"|"owner_gated"|"data_gated"|"partial", "parked_on": gate-or-null,
  "proof": "tests/test_file.py::what it proves", "note": "one or two sentences: what now runs, from
  which cadence/handler, and what acts on it; for a gated row: exactly what is real-gated and what built
  half runs today"}]
covering EVERY row in your list, plus your final commit hash and the list of tests you ran with counts.
Be honest: a row you could not finish is "partial" with the reason.
