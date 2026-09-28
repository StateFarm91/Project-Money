# Final Build closure-matrix mapping brief (workers read this in full)

You are a bounded mapping worker. The integrator (another Claude session) certifies; you do not.
Your job: for each Final Master requirement in your slice, determine from **code and evidence**
(never from names or similar-looking code) what exists, at what maturity, and what is next.

Working tree (read-only for you except your one output file):
`/home/user/Project-Money/.claude/worktrees/visual-investigation/brambleloop` (HEAD = 019ebf0 + registry commit).
Interpreter if you need to run something: `/home/user/Project-Money/brambleloop/.venv/bin/python`
with `PYTHONPATH=src`. Do NOT run `run_tests.sh` (full suite is ~20 minutes). Do not edit code,
do not commit, do not push, do not touch git state (no checkout/stash/reset). Read-only git
commands (`git show fcb982d:<path>`, `git log`, `git grep`) are fine. No network calls to Etsy,
Railway or model providers.

## Inputs
- `research/final_build/master_registry.json` — requirements (use `uid`, `full_text`, `version`,
  `section`, `master_priority`).
- `research/final_build/module_reachability.json` — per module under `src/brambleloop/`:
  `reached` (live-root call-graph reachability on 019ebf0, the Build 2 C-65 rule) and
  `in_production_fcb982d` (file exists in production tree).
- `src/brambleloop/build2/requirements.json` — Build 2's 320-row registry; each `note` holds
  the adjudicated evidence (modules, handlers, tests). `research/b2_resume/closure_state.json`
  gives each Build 2 row's final state (COMPLETE+PROVEN / OWNER-GATED / DATA-GATED /
  EXTERNAL-BLOCKED). Many Final Master requirements overlap Build 2 rows — find them by content.
- `research/BUILD2_CERTIFICATION.md` (defect ledger C-60..C-87), `BUILD_STATE.md`,
  `DECISION_LOG.md`, `research/*.md` (Visual, Etsy, reliability audits), `src/`, `tests/`.
- Executor gates: `src/brambleloop/build2/executor.py` (`Gate(...)` table) — the real owner/data/
  external gate keys.
- Visual V2 R&D (frozen, not integrated): branch `codex/visual-v2-rnd` @ 035ff0c
  (`git show 035ff0c --stat`, `git show 035ff0c:<path>`). Evidence there is R&D only: it is not
  on 019ebf0, so its maturity for the main line is at most "exists on R&D branch" — say so in
  `evidence`, keep `maturity` for the main line.

## Maturity (report the HIGHEST level genuinely proven; do not collapse)
- `MISSING` — nothing on 019ebf0 implements the executable definition. List what you searched.
- `IMPLEMENTED` — code implements it; no test asserts the behaviour.
- `TESTED` — a named test asserts the behaviour (not a tautology, not only existence).
- `INTEGRATED` — TESTED, and the producing code is reached from a live runtime root (scheduled
  handler / cadence in runtime/worker.py / enqueued job / API route computing from the DB — see
  module_reachability.json and the specific function), and where the requirement exists to
  influence a decision, the runtime consumer is shown. A library only tests call = TESTED.
- `DEPLOYED` — INTEGRATED and the same behaviour exists in production tree `fcb982d`
  (check the function, not just the file). Build 2 was never deployed, so behaviour added after
  fcb982d is at most INTEGRATED.
- `EXERCISED` — actually executed by the real runtime with durable evidence (production verify
  logs, research evidence of a real run). Test runs and fixtures never count.
- `PRODUCTION-OBSERVED` — observed operating in production on real external data.
- `COMMERCIALLY-EVIDENCED` — real customer/revenue evidence. None exists; never assign it.
Also give `coverage`: `FULL` or `PARTIAL` (what part of the requirement text is missing).

## Launch class
- `LAUNCH-CRITICAL`: needed for a customer-protective first sale — Product Truth, correct
  patterns, truthful Visual/listing representation, safe publication, marketplace compliance,
  order/customer truth, pricing/economics integrity, provenance, customer support/remedy,
  authority/spend controls, runtime durability, recovery/idempotence, truthful owner visibility.
  Source-stated: `master_priority` P0 items; v0.24 s84 launch list (Learn architecture, knowledge
  graph, content-gap detection, pattern/support links, provenance, correctness QA, ability to queue
  education work); F-831..F-850 certification contract.
- `MATURE`: post-launch/scale/optimization/growth/Studio polish/research depth/learning loops,
  `P1-after-real-traffic`, Ads (disabled until owner authority, F-875), video/email/social, etc.
  F-698: mature Studio/department capability is not a first-sale blocker.
- `NA`: not applicable to Brambleloop's product (explain), or a pure statement with no executable
  content (e.g. conclusion prose) — prefer mapping it to its enforceable part if any.
Give a one-line `launch_class_reason`.

## Gate
`{"kind": "none"|"owner"|"data"|"external", "key": "<executor gate key or short name>", "detail": "..."}`.
A gate applies only to the remaining step; software preparation that can be done now is not
gated and belongs in `next_action`.

## Output
Write ONE file: `research/final_build/mapping/<slice>.json` — a JSON list, one object per
requirement uid in your slice, in registry order, exactly these keys:
```
{"uid": "...", "launch_class": "...", "launch_class_reason": "...", "maturity": "...",
 "coverage": "FULL|PARTIAL", "missing_part": "..."|null,
 "producer": "path::function"|null, "durable_state": "table/file"|null,
 "consumer": "path::function"|null, "protected_effect": "..."|null,
 "tests": ["tests/test_x.py::test_name", ...], "evidence": ["path or note", ...],
 "build2_rows": ["#id STATE", ...], "gate": {...}, "defect": "..."|null,
 "next_action": "...", "confidence": "HIGH|MEDIUM|LOW", "searched": "..."|null}
```
`next_action` must be concrete and executable (file/function to build or wire, test to add,
owner action to request), or "none — at target maturity for launch" when appropriate.
`defect` is for something that exists but is wrong/unwired/proxy-as-truth/fixture-only.
Validate your file with `python3 -c "import json;json.load(open(PATH))"` before finishing.
Final reply: counts by maturity and launch_class, and the 5 most important launch-critical gaps.
Accuracy over speed; when unsure, say LOW confidence rather than guessing upward.
