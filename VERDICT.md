# Batch 19-B security review: eng/autocoder and eng/autopromote

- Reviewed: 2026-11-20 (UTC), by an independent Claude security reviewer
- Base: `b098fcce` (production Batch 17, eng/colourwork head)
- Units: **(A)** `eng/autocoder @ caa9a6f1`, **(B)** `eng/autopromote @ 6c3cecd5`
- Scope: security review only. No PR opened, no Railway variables or secrets read.

| Unit | Verdict |
|---|---|
| A: eng/autocoder | **BLOCK** (findings A1, A2) |
| B: eng/autopromote | **BLOCK** (findings B1 and B7; both small fixes) |

---

## (A) eng/autocoder @ caa9a6f1: BLOCK

### Merge onto b098fcce
One conflict, in `brambleloop/src/brambleloop/autonomy/autonomy_map.json`. Only the
`generated_at` timestamp differed. I resolved it by taking theirs and regenerating with
`python3 -m brambleloop.autonomy.map --write ...`. The regenerated map differs from theirs
only in the timestamp, so the content is consistent with the merged tree.

### Tests
`PY=python3 JOBS=4 SUITE_REGISTRY=0 SUITES="test_eng_autocoder test_w4_readback_evidence test_swarm_runtime test_deploy_guard test_vacuity test_w4_resume_runner" bash run_tests.sh`
on the merge. Result: **6/6 suites green, 118 passing, 0 failing** (162 s, exit 0).

### Mutation
I changed `ALLOWED_REF_PREFIX = "refs/heads/auto/"` to `"refs/heads/"` and ran
`tests/test_eng_autocoder.py`. **The mutation was killed**: 3 tests failed
(`test_a_hosts_refuse_non_auto_refs_before_writing_anything` reported "local host pushed
'claude/repository-setup-nc9x6o'", plus `test_a_only_auto_refs_pass_the_allowlist` and
`test_j_each_rail_mutation_is_killed`).

### Checklist
| Requirement | Status |
|---|---|
| Refspec allowlist is `auto/*` only | PASS in-process (`assert_ref_allowed`, re-checked in both hosts). This is not enforced server-side; see A1. |
| Path denylist covers deploy guard, boot guard, release record, spend ceilings, child safety, auth, authority | **FAIL** (A2) |
| Removing tests or asserts, or adding skips, is refused | PASS, with gaps (A4) |
| Every call reserves spend through the gateway; per-ECR and monthly caps | PASS. `guarded_call` pre-checks per-ECR CA$/tokens, wall time and the monthly sub-ceiling, which is `min(40, gateway ceiling)` and binds at 0 when the ceiling is unreadable. `gateway.complete_json` reserves. See A5. |
| Secrets scanned out of diffs | PASS (`secret_findings` on added lines, before tests run and again at submit) |
| Kill switch | PASS. `BRAMBLELOOP_AUTOCODER_ENABLED`, default off. |
| Reviewer must SHIP before push | PASS. `submit` requires `ship is True`, binds the diff by sha256 and re-runs the rails. |
| No shell injection from ECR text | PASS. Every subprocess uses argv lists with no shell; the suite name is regex-checked; the branch comes from an int ECR id; the commit message goes through the JSON API. |

### Findings

**A1. HIGH: model-written code runs in the production worker, unsandboxed and before
review. The regex rails that guard it can be bypassed trivially.**
`Workspace.apply(op="test")` and `gate()` run model-written tests and source with
`subprocess.run([sys.executable, suite])` inside the worker container. The environment is
scrubbed (`_clean_env`), but:
- the subprocess has the same uid (the Dockerfile has no `USER`, so it runs as root) and full
  network access;
- `/proc/<ppid>/environ` (and `/proc/1/environ`) are readable from the subprocess, and they
  hold every worker credential, including `BRAMBLELOOP_GITHUB_TOKEN`, the provider keys and
  `DATABASE_URL`;
- the only guard is a regex over added lines (`test_execution_findings` /
  `spend_path_findings`), which string concatenation and `importlib` defeat.

Proof: `scratchpad/bypass_probe.py` builds a test that does
`open('/pr'+'oc/'+str(os.getppid())+'/env'+'iron','rb').read()` and
`importlib.import_module('url'+'lib.re'+'quest')`, and a source file that imports
`'sub'+'process'`. `check_changeset` returns `[]` and `execution_rails` returns `[]` for
both. This step runs before the reviewer, so the SHIP gate does not cover it.

Consequence: with the fine-grained token (contents:write on the whole repository), code
running in that process can push to **any** ref, including the production branch and
`claude/w6-release-*`, which autopromote certifies and deploys. That makes the in-process
`auto/*` allowlist advisory. The model's input includes ECR `evidence.examples` filed from
production loops, so prompt injection is a plausible trigger. A model error is enough.

Fix, all three required:
1. Execute model-written code only in an isolated sandbox: a separate container or job with
   no credentials in its environment or on disk and no network. At minimum use
   `unshare -rn` (or bubblewrap: `bwrap --unshare-all --die-with-parent`) with a non-root uid
   and a read-only bind of the workspace. Do not run it as a child of the credentialed
   worker.
2. Hold the GitHub token outside the process that runs tests, for example in a separate
   push step that receives only the reviewed file map. Also call
   `prctl(PR_SET_DUMPABLE, 0)` in the worker as defence in depth.
3. Enforce `auto/*` server-side. Add a repository ruleset or branch protection on the
   production branch, `main` and `claude/w6-release-*` that the autocoder token's identity
   cannot bypass. Better still, use a GitHub App installation restricted by a ruleset to
   `auto/*`. Treat the regex rails as lint, not a security boundary, and say so in the
   docstring.

**A2. HIGH: the path denylist misses child-safety, auth and spend-ceiling code.**
`path_refusal` returns `''` (editable) for:
- `src/brambleloop/intel/childrens.py`: the children's audience module ("what it forbids":
  small-parts and choking rules, 16 CFR 1500.19 statements, age bands). `publish/pdf.py`
  consumes it.
- `src/brambleloop/creative/children.py` and `src/brambleloop/publish/pdf.py` (the
  children's warning block).
- `src/brambleloop/core/opsauth.py` (operator credential), `core/readbackauth.py`,
  `core/oauth_store.py`, `integrations/etsy_oauth.py`, `integrations/etsy_authorise.py`.
- `src/brambleloop/visual/spend_plan.py` (per-experiment `max_spend_cad` ceiling guard) and
  `visual/product_authority.py` (fail-closed product authority).

Fix: add these paths to `PROTECTED_PATHS`. Better, invert the model: protect by default and
allowlist the packages the autocoder may edit. Add a test that runs `path_refusal` over
every module whose name matches `child|minor|auth|oauth|secret|spend|ceiling|budget|authority|guard|gate`
and fails on any editable match.

**A3. MEDIUM: the rails see only added lines, so the effect of a change is invisible to
them.** A source edit can weaken a gate without matching any pattern, for example by
changing a constant a gate reads or by deleting a check in a non-test file (deletions are
not scanned). The LLM reviewer is the only control here. This is acceptable only once A1
and A2 are fixed and the editable surface is an allowlist.

**A4. LOW: gaps in the test-weakening checks.**
- `TestShape.functions` is keyed by bare name, so `test_x` methods in two classes collide.
- `early_return` inspects only the first statement, so `if True: return` is not caught.
- Assert counts are per function, so `assert x == 5` can become `assert x is not None`
  without detection.
- Helpers not named `test*` (and `conftest`-style modules other than `_tmp` and
  `_minipytest`) are not checked.

Fix: key by qualified name (`Class.test_x`), flag any `Return` reachable before the first
assert, and protect the `tests/_*.py` helpers by prefix.

**A5. LOW: per-ECR spend survives crashes only through the evidence note.**
`ecr_before_cad` comes from `evidence.autocoder.spent_cad`, which is written after a run.
A worker crash mid-run loses that run's spend from the per-ECR cap. The ledger-based
monthly cap still binds.

Fix: derive the per-ECR spend from `CostEntry` rows tagged with the ECR id (job id), not
from the note.

---

## (B) eng/autopromote @ 6c3cecd5: BLOCK

### Merge onto b098fcce
Clean merge, with no conflicts. The branch is based on `a35ad302` and brings the Batch 8–11
release records and `DEPLOYED_HISTORY` with it. `ops/deploy_guard.py`, `ops/deploy.sh` and
the boot guard are **unchanged** by this unit.

### Tests
`PY=python3 JOBS=4 SUITE_REGISTRY=0 SUITES="test_autopromote test_deploy_guard test_vacuity test_w4_resume_runner" bash run_tests.sh`
on the merge. Result: **1 suite failing: 69 passing, 1 failing** (exit 1). `test_w4_resume_runner` failed `test_f7_the_declared_final_segment_set_covers_every_matching_suite: declare these in scripts/suite_final_segment.txt: ['tests/test_autopromote.py']`. See B7. The other suites (`test_autopromote`, `test_deploy_guard`, `test_vacuity`) passed.

actionlint is **not installed** in this container, and `test_workflow_lint` itself prints
`SKIP actionlint not installed`. I reviewed the YAML by hand.

### Mutations
| Mutation (certify-and-promote.yml) | test_autopromote |
|---|---|
| Replace the backup gate with `echo '{}' > backup.json` | **killed** (`test_workflow_keeps_the_guard_intact`) |
| Change promote concurrency group to `promote-${{ github.run_id }}` | **killed** |
| Append `\|\| true` to the backup gate | **survived** (and see B1: the shipped YAML already behaves this way) |
| Add a `pull_request_target:` trigger | **survived** |

### Checklist
| Requirement | Status |
|---|---|
| One plain full run on the exact SHA | PASS. HEAD == sha, clean tree, branch head == sha; CHECKPOINT/RESUME/SHARD/SUITES unset; `REQUIRE_CLEAN=1`. |
| Guard unchanged | PASS. `deploy_guard.py` and `deploy.sh` are untouched; the dry run, guard and pre-push hook still decide. |
| Minimal permissions, no `pull_request_target`, no untrusted input in run steps | PASS. `contents: write` only; dispatch inputs go through `env:` and are validated (40-hex, `claude/w6-release-*`). See B3 and B4. |
| Secrets only where needed | PASS. `RAILWAY_TOKEN` appears only in the backup step and `BRAMBLELOOP_READBACK_TOKEN` only in the deploy step. See B3. |
| Backup required before deploy | **FAIL** (B1) |
| Readback skipped as WARN, never PASS | PASS. `::warning::`, a "SKIPPED (WARN)" summary, and `readback=SKIPPED-WARN` in the history evidence. |
| Concurrency limited to 1 | PARTIAL. Promote is 1 repository-wide; certify is 1 **per SHA** (B2). |

### Findings

**B1. HIGH: the backup gate does not gate. A REFUSE is masked by `| tee`.**
The step runs `python3 ops/autopromote.py backup | tee backup.json` with no `shell:` key.
On Linux runners GitHub then uses `bash -e {0}`, which has **no `pipefail`**, so the step's
status is `tee`'s (0). `autopromote.py backup` exits 1 on REFUSE (no token, failed backup or
timeout), and the deploy still runs.

Verified locally: `bash -e -c '(exit 1) | tee /dev/null; echo continued'` prints
"continued", while `bash -eo pipefail` stops with rc=1. The test asserts the presence of the
literal `"python3 ops/autopromote.py backup |"`, which pins the bug in place.

Exact fix:
```yaml
      - name: Pre-deploy backup gate
        shell: bash          # => bash --noprofile --norc -eo pipefail {0}
        env:
          RAILWAY_TOKEN: ${{ secrets.RAILWAY_TOKEN }}
        run: |
          set -o pipefail
          python3 ops/autopromote.py backup | tee backup.json
          python3 -c "import json,sys; sys.exit(0 if json.load(open('backup.json')).get('ok') is True else 1)"
```
Also set `defaults: run: shell: bash` at workflow level so every step gets pipefail. Add a
test asserting that the backup step has `shell: bash` or `set -o pipefail`, and that no step
has `|| true` or a pipe without pipefail.

**B2. MEDIUM: certify concurrency is per SHA, not 1.**
`group: certify-${{ inputs.sha || github.sha }}` lets two 4-hour full runs for different
SHAs (or release branches) run at once. Each pushes a record onto its branch. Promote is
serialised, but it can then promote an older SHA after a newer one if the certify runs finish
out of order.

Fix: use `group: brambleloop-certify` with `cancel-in-progress: false`. In promote, refuse
unless `RELEASE_SHA` descends from the deployed SHA; the guard's ancestry check may already
do this, but assert it in the workflow test.

**B3. MEDIUM: the certify job runs the suite (repository code) in a job that later pushes
with the write token.** `persist-credentials: false` keeps the token off disk during the
suite. But the suite (or an `ops/autopromote.py` subcommand) can plant `.git/hooks/*` or
edit `.git/config`. The next step's
`git -c http.https://github.com/.extraheader=AUTHORIZATION... push` runs those hooks, and
git exports `-c` values to hooks via `GIT_CONFIG_PARAMETERS`, which leaks the token. This
matters because of A1: the code under test may be model-authored.

Fix: split the work. A `certify` job with `permissions: contents: read` runs the suite and
`deploy_guard record` and uploads `brambleloop/release/` and `release_evidence/` as an
artifact. A separate `record` job with `contents: write` checks out the SHA fresh, downloads
the artifact, verifies that it names this SHA, and pushes with `-c core.hooksPath=/dev/null`.

**B4. MEDIUM (owner control): a `push` to `claude/w6-release-*` deploys to production with
no human gate.** The `environment: production` reviewer is described as optional, and the
workflow file runs as pushed (the trust note acknowledges this). Combined with A1, any
holder of a contents:write token can create a release branch with an edited workflow.

Fix, before enabling: make owner actions "production environment required reviewers" and
"branch ruleset on `claude/w6-release-*` and the production branch, no bypass for bot
tokens" **mandatory**, not optional. Alternatively, drop the `push` trigger and keep only
`workflow_dispatch` from the default branch.

**B5. LOW: `dispatch.yml` runs code from a non-default branch.** It checks out
`ref: claude/w4-INTEG8-next` and runs `ops/dispatch_board.py` with `issues: write` on every
issue comment. Code on that mutable branch runs without review on the default branch.

Fix: check out the default branch, or pin to a reviewed SHA.

**B6. LOW: the workflow test does not pin the trigger set or shell semantics.** Adding
`pull_request_target` or `|| true` survives `test_autopromote`.

Fix: assert that `on:` keys are exactly `{workflow_dispatch, push}`, that there is no
`pull_request_target` or `workflow_run`, that `${{ github.event.* }}` / `${{ inputs.* }}`
never appear inside `run:`, that `|| true` never appears in the backup or deploy steps, and
that pipefail is in force (B1).

**B7. MEDIUM (merge regression): on b098fcce the unit turns `test_w4_resume_runner` red.**
The base's F7 rule requires every suite matching the final-segment pattern to be declared in
`brambleloop/scripts/suite_final_segment.txt`. `tests/test_autopromote.py` matches the
pattern and is not declared, so a certify run on the merged tree would be red and could not
record a release.

Fix: add `tests/test_autopromote.py` to `brambleloop/scripts/suite_final_segment.txt` as part
of the merge, as eng/autocoder already did for its own suite, and rerun
`test_w4_resume_runner`.

---

## Summary
- **A: BLOCK.** The mechanics the brief asked for (refspec allowlist, kill switch, SHIP
  gate, budgets, secret scan, no shell injection) are implemented and tested. But model code
  executes in the credentialed worker behind regex-only rails (A1), so none of those
  in-process guarantees hold against a hostile or confused model. The denylist also misses
  child-safety and auth modules (A2).
- **B: BLOCK.** The guard is intact and the design is sound, but the pre-deploy backup gate
  is a no-op on failure (B1). Fixing B1 (with its test) and B7 is enough to move B to SHIP. B2–B4
  should land before the push trigger is enabled.
