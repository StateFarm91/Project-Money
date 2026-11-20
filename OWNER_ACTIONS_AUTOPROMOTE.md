# OWNER ACTIONS: autopromote (certify-and-promote on GitHub Actions)

Written 2026-11-20 (UTC) by ENG-AUTOPROMOTE. The workflow is `.github/workflows/certify-and-promote.yml`.
It runs the full suite on the release SHA, writes the release record and runs `ops/deploy.sh`.
No Claude usage is needed, and the deploy guard is unchanged. Until you do actions 1 and 2,
every promote stops at the backup gate, so certification runs but **nothing deploys**.

Add the secrets here: github.com/StateFarm91/Project-Money -> Settings -> Secrets and variables ->
Actions -> **New repository secret**. You can also add them as secrets of the `production`
environment (Settings -> Environments -> production, which the first run creates). Never paste
either value into a chat, an issue or the repository.

## 1. `RAILWAY_TOKEN`: required before anything deploys
- **Exact action:** Railway -> project **brambleloop** -> Settings -> Tokens -> create a
  **project token** for environment **production**. Name it `github-actions-backup`. Add it as
  the GitHub secret `RAILWAY_TOKEN`.
- **Why:** a backup is required before every release (ops/ROLLBACK_RUNBOOK.md). Actions starts
  the `db-backup` service by redeploying it through the Railway API, then waits up to 20 min for
  `BK RESULT OK`. It also reads the db-backup logs. Without the token the promote REFUSES. The
  rule "a `BK RESULT OK` under 24 h old is good enough" applies only when the token is present
  and the trigger produced no verdict, because those logs are readable only with the same
  token. A backup that ran and failed is always a REFUSE. The full rule is in
  `ops/autopromote.py`.
- **Scope note:** a project token can deploy any service in the brambleloop production
  environment, not only db-backup. The workflow uses it for db-backup only.
- **Maximum cost:** CA$0 for the token. Each backup costs a few cents of Railway compute. Each
  dump is about 650 MB on the 1000 MB volume, and on 2026-11-19 only 640 MB was free.
  **Prune old dumps or grow the volume first**, or the next triggered backup fails and the
  promote refuses.
- **Minutes:** 5.
- **Consequence of waiting:** every certified release stops before the push. Nothing unsafe
  happens, and nothing ships.

## 2. `BRAMBLELOOP_READBACK_TOKEN`: strongly recommended
- **Exact action:** use the same value as the existing production variable
  `BRAMBLELOOP_READBACK_TOKEN` (the evidence-surface token from W4-READBACK). Add it as the
  GitHub secret `BRAMBLELOOP_READBACK_TOKEN`.
- **Why:** after the deploy, `ops/readback.py` checks every feature in production. Without the
  secret the readback is **skipped with an explicit WARN**, and the run summary says
  `READBACK: SKIPPED (WARN)`. A skipped readback is never reported as a PASS.
- **Maximum cost:** CA$0. **Minutes:** 3.
- **Consequence of waiting:** deploys go out with only `/health` verified. A regression is not
  detected automatically, and the P0 rollback decision never runs.

## 3. Allow the Actions push to the production branch
- **Exact action:** if you protected `claude/repository-setup-nc9x6o`
  (ops/DEPLOY_CONTROLS.md, owner action 1), let **GitHub Actions** bypass the rule. In the
  ruleset, add a bypass actor: Repository admin role or "GitHub Actions" app. Do not add a
  general bypass. If the branch is unprotected, there is nothing to do, but read the trust note
  below.
- **Why:** `ops/deploy.sh` pushes the certified commit with the workflow's `GITHUB_TOKEN`
  (`contents: write`). The pre-push hook and `deploy_guard check` still run on that push.
- **Maximum cost:** CA$0. **Minutes:** 5.
- **Trust note (B19 B4):** the workflow no longer has a `push` trigger, because a push trigger
  runs the workflow file as pushed. It runs only by `workflow_dispatch` and refuses unless the
  run uses the default branch's copy of the file. **Required before first use:** add
  `claude/w6-release-*` to the same ruleset (Restrict updates, Block force pushes), with only
  GitHub Actions and you on the bypass list, so a bot token cannot create or move a release
  branch.

## 4. REQUIRED: approve each deploy with one click (B19 B4, no longer optional)
- **Exact action:** Settings -> Environments -> **production** -> Required reviewers -> add
  yourself.
- **Why:** the promote job uses the `production` environment. With a reviewer set, each deploy
  waits for an Approve click in the GitHub app. That keeps the exact-SHA owner approval used for
  Batches 5-11 without any Claude usage. The B19 security review made this mandatory: with the
  autocoder able to write code, a human click is the last gate before production.
- **Consequence of waiting:** do not dispatch the workflow until this is set; without it a
  certified release deploys with no human in the loop.
- **Maximum cost:** CA$0. **Minutes:** 2, plus about 1 per release.

## Cost and runtime (Actions minutes)

- The repository is **public**, as checked through the GitHub search API on 2026-11-20. Standard
  GitHub-hosted runners are **free with unlimited minutes** for public repositories, and
  `ubuntu-latest` is 4 vCPU / 16 GB. **Cost: CA$0.**
- Each release uses about 2.2-2.9 h of certify time plus about 10-30 min of promote time
  (backup wait, deploy, readback). The last six full runs took 7733-10566 s on a 4-job VM, and
  the outlier was 15491 s (4.3 h). The certify job is capped at **350 min**. GitHub-hosted jobs
  stop at 360 min.
- **If the repository becomes private:** a Free plan includes 2000 min/month on a **2 vCPU**
  runner. At about 180 min per run, that is about 11 releases a month, then US$0.008/min (about
  US$1.45, roughly CA$2, per release). On 2 vCPU the suite would probably take about 4-6 h and
  could hit the 6 h cap. In that case use a **self-hosted runner**, for example the existing VM:
  register it under Settings -> Actions -> Runners, then set the repository variables
  `CERTIFY_RUNNER` (its label) and `CERTIFY_TIMEOUT_MIN` (for example `600`). No workflow edit is
  needed.
- **If one run ever reaches 6 h on a hosted runner:** the job is killed, nothing is recorded and
  nothing deploys. The fix is the self-hosted runner above. It is never a checkpointed or
  sharded run, because D-W4-OWNER-RESUME-POLICY forbids that.

## How a release flows once this is done
1. The integrator pushes the certified candidate to a `claude/w6-release-<name>` branch whose
   history already contains the production commit, then dispatches the workflow from the
   default branch with that `sha` and `branch` (Actions UI, or the API). A push alone starts
   nothing (B19 B4).
2. **certify** (one at a time across the repository, `contents: read`): one plain
   `REQUIRE_CLEAN=1 bash run_tests.sh` on the exact SHA, then `deploy_guard.py record`; the
   record is uploaded as an artifact. **record** (a fresh checkout that ran no tests, the only
   job that can push): checks that the record names this SHA and touches only the record
   directories, then commits and pushes it onto the release branch as a fast-forward with git
   hooks disabled. If someone pushed to the branch during the run, the push fails and nothing
   deploys.
3. **promote** (one at a time across the repository): read the production SHA and refuse unless
   the release descends from it. If production
   reports a commit missing from DEPLOYED_HISTORY, append it as observed. Run the guard dry run,
   then the backup gate, then `ops/deploy.sh --deployed <prod sha>`. Finally record the deploy in
   DEPLOYED_HISTORY on the release branch.
4. To run it by hand: Actions -> certify-and-promote -> Run workflow, with `sha` and `branch`.
   `workflow_dispatch` appears only once the workflow file is on the default branch, which
   happens after the first release that contains it is deployed.
