# Wave FB-1 worker brief (read in full before starting)

You are a bounded implementation worker in the Brambleloop Final Build. The integrator (another
Claude session) merges and certifies; you do not self-certify (F-867). Evidence decides.

## Setup (do exactly this)
```
cd /home/user/Project-Money
git worktree add .claude/worktrees/fb1-<X> -b claude/fb1-<X> be8d416
cd .claude/worktrees/fb1-<X>/brambleloop
PY=/home/user/Project-Money/brambleloop/.venv/bin/python
```
Base SHA is **be8d416** (certified Build 2 019ebf0 + Final Build registry/audit). Work only in
your worktree. Never touch other worktrees, never use `git stash`, never push to any branch but
`claude/fb1-<X>`. Commit in small, reviewable commits; push your branch after each meaningful
commit (`git push -u origin claude/fb1-<X>`) so a session reset loses nothing.

## Read first
- `research/final_build/FINAL_BUILD_BASELINE_AUDIT.md` (§2 supersessions, §6 your cluster row).
- Your rows in `research/final_build/closure_matrix.json` (filter by uid): `missing_part`,
  `defect`, `next_action`, `producer`, `tests`. Treat `next_action` as a strong hint, not a spec —
  the requirement text (`master_registry.json` `full_text`) is the spec.
- `CLAUDE.md` non-negotiables. Code style: match surrounding code (long explanatory comments
  where the codebase has them, tests written as `test_<behaviour_sentence>` functions with the
  `__main__` runner block used by every test file).

## Definition of done for each requirement you touch (F-831..F-840)
requirement → producer → durable state → runtime consumer → decision → protected effect →
observable result → test. A library only a test calls is NOT done: wire it to a live root
(registered handler named by a cadence in `runtime/worker.py`, an enqueued job, or an API route
computing from the DB) unless the requirement is purely a gate inside an already-live path.
Unknown stays UNKNOWN; a proxy stays labelled a proxy; never report missing data as zero.

## Hard limits
- No network calls to Etsy, Railway, model/image providers or anything external. Use the fakes
  the tests already use. No spend. No publication. Phase stays shadow.
- Never weaken, skip or delete a test to get green. If an existing test pins behaviour that a
  Master requirement explicitly forbids, change it to assert the required behaviour and list it
  under `tests_changed` with the requirement ID and one line of why.
- Do not edit files owned by another cluster (see your ownership line). If you need something
  from another cluster, write it in your report under `needs_from_others`; do not do it.
- Database changes: additive migrations only, via the existing migration mechanism
  (`core/migrate.py`); never drop or rewrite data.
- Do NOT run `run_tests.sh` (the full suite takes ~20 min and seven workers share this machine).
  Run every test file you touched or whose subject you touched, plus
  `$PY tests/test_cert_wiring.py` and `$PY tests/test_reachability*.py` if they exist when you add
  handlers/cadences. The integrator runs the full suite.

## Report (your final reply, and also committed as `research/final_build/waves/fb1_<X>.json`)
```
{"cluster": "<X>", "branch": "claude/fb1-<X>", "head": "<sha>", "base": "be8d416",
 "requirements": [{"uid": "F-...", "status": "DONE|PARTIAL|NOT_STARTED|BLOCKED",
   "what_changed": "...", "producer": "...", "consumer": "...", "live_root": "...",
   "tests": ["tests/..::test_..."], "remaining": "..."}],
 "tests_run": [{"file": "...", "passing": n, "failing": n}],
 "tests_changed": [{"test": "...", "uid": "...", "why": "..."}],
 "files_touched": [...], "migrations": [...], "needs_from_others": [...], "risks": [...]}
```
Prefer finishing fewer requirements end to end over touching many partially. If you run low on
budget, commit and push what is green, write the report with honest statuses, and stop.
