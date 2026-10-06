# Wave 4 — Completion team brief (owner directive 2026-10-06 "STOP THE CERTIFICATION LOOP. FINISH THE EXISTING BUILD.")

Read fully before working. You are ONE lane of a parallel completion team (8–12 lanes). The
integrator (parent session) reviews, runs affected tests, merges and pushes. Scope is the EXISTING
commission only: Build 2 (spec/08 v1.4.3, `src/brambleloop/build2/requirements.json`, 320 rows) +
existing Final Master (spec/09 v1.0 + spec/10 v1.1, `research/final_build/master_registry*.json`,
`master_v1.0.txt`, `master_v1.1.txt`, MASTER_SPEC_ERRATA.md, DECISION_LOG rulings through D-FB-18)
+ Owner Command Center + Store/Search/SEO/product/autonomy obligations. Do NOT start any new
"Actually Final" / Stylist / Live Presence scope.

## The goal is finished work, not audits
Audit only as far as needed to act. Then implement → focused test → runtime proof → commit → push.
Historical certification is evidence, not closure. Every row you touch ends PROVEN / OWNER-GATED /
DATA-GATED / EXTERNAL-GATED / NOT-APPLICABLE / OPEN-DEFECT, with evidence (test name, runtime
consumer path, artefact). Never reclassify executable company work as owner-gated.

## Setup
`git -C /home/user/Project-Money worktree add /home/user/Project-Money/.claude/worktrees/W4-<LANE> -b claude/w4-<LANE> claude/visual-investigation`
Work in `brambleloop/`. Interpreter: `/home/user/Project-Money/brambleloop/.venv/bin/python`,
`PYTHONPATH=src`. Always `export TMPDIR=/home/user/bl-tmp-<LANE>` (create it; delete it when done).
New test files start with `import _tmp; _tmp.install()` (tests/test_w3_tmp_hygiene.py enforces it),
print `OK <name>` / `FAIL <name>` lines, and assert non-emptiness before loops (test_vacuity).
No secret-looking literals (test_secret_scan). If you edit DECISION_LOG.md, regenerate
`PYTHONPATH=src python -m brambleloop.core.decision_index`.

## Tests — focused only
Run your new tests + the existing tests for every module you touch + test_vacuity, test_secret_scan,
test_reachability, test_w3_tmp_hygiene. NEVER run the full suite or run_tests.sh (one bounded
validation lane owns that). Never weaken/skip/delete a test or loosen a gate/threshold.

## Durability (session/usage limits must not cost a day)
Commit signed and push your branch at least every ~45 minutes of work and at every milestone:
`git -c user.name=Claude -c user.email=noreply@anthropic.com commit ...` with trailers exactly:
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GpoRAgr4kBWxi1752HufQh
Push ONLY your own branch, never force: `git push -u origin claude/w4-<LANE>`. Keep
`research/final_build/w4/handoff_<LANE>.md` current (rows → status → evidence; done; in progress;
exact next steps to resume; wiring requests). Never `pkill -f` by pattern; never bare `git stash`.

## Hard rules
Phase stays shadow. No deploy, no Railway mutation, no Etsy writes/publication, no customer
messages, no spend / new paid API calls, no banking/KYC/tax/legal acceptance. Read-only network at
most. Never overwrite owner-configured live Etsy fields (logo, banner, title/tagline, About,
Laura's profile/Designer role). Canonical brand files (brand/owner_source, D-FB-17/18) and Laura
identity (laura-r2-a42aeac7, D-FB-14) are protected. No fake reviews/engagement; never copy
competitor content (competitor research = demand/merchandising intelligence only). Product Truth,
customer truth, accounting truth, authorization, security and spend ceilings are never weakened.
UNKNOWN is never 0; proxy ≠ measurement; estimated ≠ actual.

## File ownership (edit only what your lane owns; else write a WIRING REQUEST in your handoff)
| Owner lane | Files |
|---|---|
| AUTO | runtime/worker.py (CADENCES), runtime/pipeline.py, swarm/orchestrate.py, autonomy/**, agents/registry.py, queue/** |
| CC | app/main.py, app/security.py, app/command_center/** (incl. static/), app/dashboard*.py |
| integrator | core/models.py, core/db.py, Dockerfile, run_tests.sh — new tables go in your own package module (learn/models.py pattern) + WIRING REQUEST for create_all import |
| B2 / FM | build2/requirements.json mapping, build2/closure.py, build2/maturity.py, research/final_build/w4/*ledger* |
Everything else: the lane whose mission names the package; if two lanes need the same module,
the first lane's edit wins and the second writes a WIRING REQUEST. Small, additive, surgical edits.

## Report
Final message ≤ 300 words: branch + head SHA (pushed), rows/items closed with status, tests run +
counts, runtime proof, wiring requests, what remains and why (exact gate).
