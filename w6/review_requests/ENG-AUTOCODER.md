# Review request: ENG-AUTOCODER (the in-production coding team)

- Branch `eng/autocoder` from `claude/w6-INTEG7-wip` @ `c6d4400`. No PR, by instruction.
- The final SHA is the commit that adds this file (the head of `eng/autocoder`). The
  implementation head before this file was `a2db291`.
- Not reviewed, not merged, not deployed. Nothing was read from or written to Railway, and no
  variable values were read. No real model call was made and nothing was spent. No `auto/*`
  branch exists.
- Decision record: `D-OWNER-AUTOCODER` in `brambleloop/DECISION_LOG.md`.
- Owner actions: `OWNER_ACTIONS_AUTOCODER.md`. The GitHub token is needed. **The kill switch is
  OFF by default.**

> **Superseded in part by `FIX-SECURITY-B19` (`f5b3ecd`, same branch). Read
> `w6/review_requests/FIX-SECURITY-B19.md` first.** Since that fix:
> - the worker never runs model-written code: no `run_suite` and no scrubbed-env subprocess, and
>   the `test` action is answered and never executed;
> - the targeted and mandatory suites run in `.github/workflows/autocoder-ci.yml` on the
>   `auto/**` push;
> - production certifies only on a `github-actions[bot]` success status for the exact SHA;
> - prompts are `@2`;
> - the Dockerfile `git` line is reverted.
>
> The sections below about in-worker tests, the image and `gate` running suites describe
> `a2db291` as built, and the regression table was measured on `a2db291`.

## What it is
- **`improve.code`** is a new handler in `runtime/release.py`, delegating to
  `improve/autocoder.py`.
  - Agent `autocoder`: GREEN, allowed only `improve.code`, daily ceiling CA$8.
  - Runs every 6 hours.
  - Authority class BUILD, and in the build plane (`plane_violations` stays empty).
  - Department work class IMPROVE, swarm band `exploration`, work key `work_done`.
- **Pick.** Open requests in FILED or REOPENED, ordered by priority. Engine demand counts one
  level higher (`evidence.engine_demand`, or `missing_capability` with "engine" in the module or
  title), then occurrences. Skipped:
  - requests already submitted or certified;
  - requests in flight (under 2 h);
  - requests refused in the last 7 days;
  - requests with 3 attempts;
  - requests whose CA$3.50 budget is spent.
- **Workspace.** A depth-1 snapshot of `BRAMBLELOOP_AUTOCODER_BASE`, defaulting to
  `RAILWAY_GIT_COMMIT_SHA`. It comes from the GitHub tarball, streamed to disk and extracted
  safely: no symlinks, no `..`, size caps. It lives in a `TemporaryDirectory`.
- **Loop.** `autocoder.step@1` through `failover.job_gateway` (standard tier, no stronger
  fallback). The model acts only through structured actions that code applies:
  - list, read, grep;
  - edit (exact old text, which must occur once);
  - create;
  - test (one `tests/test_*.py`).

  Writes are checked against the paths. Before any test runs, the execution rails run over the
  current diff. Tests run in a subprocess with a **scrubbed environment**: PATH, HOME, TMPDIR,
  LANG, PYTHONPATH only.
- **Budgets** (`Limits`; environment may only lower them; NaN and negative values are ignored):
  - per request: CA$3.50, 400k tokens, 40 min wall time, 12 iterations;
  - CA$40 a month for the autocoder, clamped to the model ceiling in force.

  They are checked before every call against the gateway's own padded estimate. The gateway's
  reservation, the CA$100 ceiling and the agent's daily ceiling still apply on top.
- **Gate (`gate`).**
  1. `autocoder_safety.check_changeset`:
     - path allowlist and denylist;
     - test weakening;
     - secrets;
     - spend, network, exec and environment paths;
     - process and secret-file reads;
     - size (at most 10 files and 600 lines).
  2. At least one targeted suite, plus `tests/test_vacuity.py` and
     `tests/test_w4_resume_runner.py`. All must exit 0.
- **Review.** `autocoder.review@1` on the deep tier, a different model from the author. It can
  be routed to OpenAI per task. It ships only when the verdict is `SHIP` and all 7 checks are
  `true`. `Review.diff_sha256` binds the verdict to the exact diff.
- **Push (`submit`).**
  - It is refused unless the review is SHIP for this diff's SHA and the rails pass again.
  - The ref is `assert_ref_allowed`. The host checks the ref and the paths again. Only
    `refs/heads/auto/*` is accepted.
  - `GitHubHost` uses the Git Data API: blobs, then a tree on the base tree, then a commit
    whose parent is the base, then the ref. If the ref already exists, it is force-moved,
    within `auto/*` only.
  - After a push the request is recorded as `code_submitted` with branch and SHA, and moved
    FILED to BUILDING to REVIEWED.
- **Refused.** The reason is kept on the request, for example `gate_rails`, `gate_tests`,
  `review_block` or `did_not_finish` with its budget stop.
- **Parked.** An environment fault parks the request: no provider, model or reviewer down, or
  a host error. The status is cleared and the attempt is not counted, but the spend is kept
  against the request's budget.
- **Kill switch and blockers.**
  - `BRAMBLELOOP_AUTOCODER_ENABLED` unset means OFF.
  - Enabled without the token, base or git: UNKNOWN, with each blocker named, an audit row, and
    no spend.
- **Mission Control.**
  - `GET /api/cc/autocoder` and the Autonomy tab's `autocoder` section show: open, coding,
    submitted, certified, deployed, refused with reason; spend per request; and the month
    against the sub-ceiling.
  - Readback: evidence section `autocoder` (counts and booleans only) plus an advisory row in
    `ops/readback.py`. PASS only when enabled and unblocked; OFF or blocked is WARN; unreadable
    is UNKNOWN.
- **Image.** `git=1:2.47.3-0+deb13u1` is added to the Dockerfile, because the resume-runner gate
  builds git repositories.

## Tests: `brambleloop/tests/test_eng_autocoder.py` (32 tests, all pass)
A refspec allowlist (18 refused refs, including the production branch, `main`, tags, force,
`src:dst` and `..`), in the rail and in both hosts, with zero network calls for a refused ref.
The GitHub host is checked against a fake API: only a POST of `refs/heads/auto/ecr-5`, a PATCH of
`/git/refs/heads/auto/...` on 422, the commit parent is the base, and a symlink in the tarball is
never extracted.
B path denylist (36 samples), the workspace refuses and leaves the file, and the push refuses a
protected path even with a forged review.
C weakening (10 forms) refused, strengthening allowed.
D secrets (6 forms), spend/network/exec paths (9 forms), model-written code not executed past the
rails, scrubbed environment.
E every budget binds; the environment only tightens; an over-budget run makes zero model calls
and leaves zero ledger rows; the monthly sub-ceiling parks before any call; an environment fault
parks.
F BLOCK, a false check, or a non-SHIP verdict pushes nothing; `submit` refuses no review, BLOCK,
or a review of another diff.
G end to end on a toy request in a temp git repository through the **real** `job_gateway`,
`ModelGateway`, reservation and ledger, with a scripted stub provider:
- `auto/ecr-<id>` exists, its parent is the base, it touches exactly the 2 files, and the fix is
  in;
- `main` and `claude/repository-setup-nc9x6o` are unmoved;
- the targeted and both mandatory suites ran;
- the request is REVIEWED / `code_submitted` with the SHA;
- 4 ledger rows on agent `autocoder` equal the run's spend;
- the panel shows it.

A weakened test (refused at `gate_rails`) and a failing mandatory suite (`gate_tests`) push
nothing.
H OFF by default; UNKNOWN with the named token or base blocker, an audit row and no spend; the
base defaults to the production SHA.
I pick order and cooldowns; registration, cadence, agent, class and plane; the handler through a
worker context; the readback section and its judge.
J **mutations killed.** The test swaps in each of these mutants and asserts that its check
reports a failure, then that everything is clean again once restored:
- the refspec accepts anything;
- the denylist is emptied;
- weakening, secret or spend scanners return nothing;
- the budget check is a no-op;
- the review checks are ignored;
- the limits stop clamping;
- the submit SHIP gate is removed.

**The mandatory suites in a tarball workspace:** both `test_vacuity.py` and
`test_w4_resume_runner.py` exit 0 inside a `git archive` snapshot (no `.git` at the root) with the
job's scrubbed environment (10.6 s and 92.8 s). In the toy e2e their results are a recorded
stand-in, because they need the whole repository. Production runs them for real.

## Regression runs on `a2db291`, before B19 (Python 3.11 venv from the locks; NOT a full-suite record)
Two batches covered 212 suite files, every `tests/test_*.py` I could run in the session.
Each file ran once with a 25-minute timeout, 5 in parallel. **`test_eng_autocoder.py`: 32/32.**

- **Batch 1 (108 files): 100 exit 0 at first.** All 8 failures are accounted for:
  - Caused by this change and fixed:
    - `test_cost_governance_wave2` (temp-prefix and retention-action wiring);
    - `test_gateway` (prompt wording, B-024);
    - `test_w4_readback_evidence` (21st advisory row);
    - `test_w4_resume_runner` (F7 final-segment declaration).

    Each now exits 0.
  - Pre-existing on the base and fixed here: `test_swarm_runtime` and
    `test_r2_autonomy_useful_work`, both now exit 0.
  - Pre-existing and left alone: `test_v11_cc_views` and `test_w3_tmp_hygiene`.
- **Batch 2 (104 files): 95 exit 0.** I re-ran the 9 failures, plus the base `c6d4400` in a
  worktree, one suite at a time, 3 in parallel:
  - `test_cert_orders`: "source changed during analysis" because I was editing during the run.
    Re-run exit 0.
  - `test_deploy`: a timeout under load. Exit 0 on both the base and this branch.
  - **Identical failure on the base and on this branch** (same tests, same assertion text), so
    pre-existing:
    - `test_physfix` (47/48, `basket_small` not byte-identical);
    - `test_r5_research_2` (7 passed, 3 failed);
    - `test_r5_research_3` (3 passed, 4 failed; the coaster route is refused by `flat_panel`);
    - `test_w6_listing_chain_e2e` (3/6, `store.publish` dead in shadow);
    - `test_w5_a9_package_event` (5 failed);
    - `test_platform` (`ops.continuity`: no table `radar_concepts`).
  - `test_cert_wiring`: __CERTWIRING__

Not run: no full `run_tests.sh` record. The numbers above are per-file exit codes in this session's
venv (Python 3.11, from `requirements.lock` + `requirements-test.lock`). They are not a
certification run.

## Calibration: the rails against 45 recent human commits
24 of 45 would pass. The refusals are mostly:
- protected paths (gateway, finance, gates, app/main);
- size (human commits up to about 2,500 lines);
- network or exec in tests.

That is by design: the autocoder takes small changes outside the guarded areas. The first pass
also refused tests that set `os.environ`. A test subprocess already has a scrubbed environment,
so that rule was narrowed for tests. `/proc` and secret-file reads stay refused everywhere, and
any `os.environ` or `getenv` in source stays refused.

## Not verified / limits (honest status)
- **No live run.** The GitHub API calls (tarball, blobs, trees, commits, refs) are tested only
  against a fake API. There is no token in this session.
- **The hand-off to ENG-AUTOPROMOTE is not wired.** Its workflow triggers on
  `claude/w6-release-*` pushes and on dispatch. An `auto/ecr-*` branch has to be integrated onto
  a release branch by the integrator, or by a later workflow on `auto/**`.
  `autocoder.mark_certified` exists for that readback, and nothing calls it yet.
- **Not an OS sandbox.** Model-written code runs in the worker during the loop. It is
  constrained by the scrubbed environment and static regex rails checked before each run.
  Obfuscated code could evade a regex. The independent review and full-suite certification are
  the later layers. A no-network runner (separate service) would close it.
- **Clock-sensitive tests.** A new test file that reads the clock or uses sleeps or timeouts
  must be declared in `brambleloop/scripts/suite_final_segment.txt`. That directory is
  protected, so such a test fails the resume-runner gate, and the model must write the test
  without clock dependence, or a human adds the line.
- The reviewer is the same vendor by default.
- Per-request CA$ is tracked on the request (`evidence.autocoder.spent_cad`). If two workers
  picked the same request at once, the 2-hour in-flight marker is the only guard. There is no
  row lock. Cadence and agent concurrency make this unlikely.

## Pre-existing failures on the base (`c6d4400`), and what this branch did with them
- Fixed here (one line each, in tables this change already edits):
  - `test_swarm_runtime` (`improve.self_tune` had no band);
  - `test_r2_autonomy_useful_work` (no work key).
- Left alone:
  - `test_v11_cc_views` (`/api/cc/autonomy` "learning" section);
  - `test_w3_tmp_hygiene` (`test_eng_improve_readback.py` does not install `_tmp`).

## Review asks
1. Is the protected-path set right? In particular, `app/main.py` and all of `gateway/` and
   `finance/` are off-limits.
2. Is OFF the right default for the kill switch, given the brief?
3. `git` in the production image (a deploy-affecting change).
