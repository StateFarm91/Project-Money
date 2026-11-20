# OWNER ACTIONS: autocoder (the in-production coding team)

Written 2026-11-20 (UTC) by ENG-AUTOCODER. The job is `improve.code`; its code is in
`brambleloop/src/brambleloop/improve/autocoder*.py`, and its decision is D-OWNER-AUTOCODER in
`brambleloop/DECISION_LOG.md`.

**What it does once these actions are done.** Every 6 hours, the job takes one open engineering
change request and asks Claude to fix it. It works in a throwaway copy of the code, through the
model gateway, under hard budgets. Every diff must pass the deterministic rails, the targeted tests,
`test_vacuity` and `test_w4_resume_runner`, and then an independent reviewer model. Only then does it
push a branch named `auto/ecr-<id>`. It never pushes to `claude/repository-setup-nc9x6o` or `main`,
and it never deploys. Promotion is done by the certify-and-promote pipeline (ENG-AUTOPROMOTE).

## The kill switch: **OFF by default** (chosen deliberately)

`BRAMBLELOOP_AUTOCODER_ENABLED` unset means OFF. The brief said your directive authorises default
ON. I chose OFF for four reasons:
1. Your directive reached this session relayed through a task brief, not typed by you here.
2. The job cannot work without the token in action 1 anyway.
3. Turning it on takes one variable and one minute.
4. You may want to watch the first live runs.

To turn it on: Railway, then project **brambleloop**, then the app service (it runs the worker),
then **Variables**, then **New Variable**. Set `BRAMBLELOOP_AUTOCODER_ENABLED` = `1`. Railway
redeploys the service. To stop it at any time, set the variable to `0` or delete it. The next run
reports `OFF` and spends nothing.

## 1. `BRAMBLELOOP_GITHUB_TOKEN`: required (fine-grained, this repository only)

- **Create the token.**
  1. On github.com, click your avatar, then **Settings**.
  2. Click **Developer settings**, then **Personal access tokens**, then **Fine-grained tokens**,
     then **Generate new token**.
  3. Fill in the form:
     - **Token name:** `brambleloop-autocoder`
     - **Expiration:** 90 days. Put a renewal reminder in your calendar.
     - **Resource owner:** `StateFarm91`
     - **Repository access:** **Only select repositories**, then `StateFarm91/Project-Money`
  4. Under **Permissions**, then **Repository permissions**, set **Contents** to **Read and
     write** and **Commit statuses** to **Read-only** (the worker reads the CI sandbox's
     verdict; B19 A1). Metadata becomes Read-only automatically. Leave everything else at
     **No access**: no Workflows, no Actions, no Administration, no Secrets.
  5. Click **Generate token** and copy the value once.
- **Add it to Railway.**
  1. Railway, then project **brambleloop**, then the app service, then **Variables**, then
     **New Variable**.
  2. Set `BRAMBLELOOP_GITHUB_TOKEN` to the pasted value. Never paste it into a chat, an issue or
     the repository.
- **Protect the production branch so only Actions can push it. MANDATORY before the switch
  is turned on (B19 A1 / B4): the in-process `auto/*` allowlist is a second line; this ruleset
  is the boundary GitHub itself enforces.**
  1. github.com/StateFarm91/Project-Money, then **Settings**, then **Rules**, then **Rulesets**,
     then **New ruleset**, then **New branch ruleset**.
  2. **Name:** `production-branch`. **Enforcement:** Active.
  3. **Target branches:** **Add target**, then **Include by pattern**, once for each of:
     `claude/repository-setup-nc9x6o`, `main` and `claude/w6-release-*`. All three are
     required: `claude/w6-release-*` is what certify-and-promote deploys from.
  4. Rules:
     - tick **Restrict updates**;
     - tick **Restrict deletions**;
     - tick **Block force pushes**.
  5. **Bypass list:** **Add bypass**. Choose the **GitHub Actions** app (and yourself as Repository
     admin if you want a manual escape hatch). Do not add the token's user as a general bypass.
  6. Click **Create**.

  A ruleset bypass applies to every token of the account on the bypass list. So if you keep
  yourself on it, create the autocoder token from a separate machine-user account (a free
  GitHub account added as a collaborator with Write access) rather than your own, or install a
  GitHub App restricted to `auto/*`. Otherwise a token minted from your account bypasses too.

  With this in place, even a stolen autocoder token cannot move the production branch. The code
  already refuses any ref outside `auto/*`, and the ruleset makes GitHub refuse it too.
- **Why it is required.**
  - The worker reads the code it edits as a tarball of the base commit, through the GitHub API.
  - It pushes `auto/ecr-<id>` through the Git Data API.
  - Both need a token. The container holds no other git credential.
- **Maximum cost:** CA$0. Fine-grained tokens are free.
- **Minutes:** about 10 (5 for the token, 5 for the ruleset).
- **Consequence of waiting:** with the switch ON and no token, every run reports **UNKNOWN** with
  the blocker `BRAMBLELOOP_GITHUB_TOKEN is not set` in:
  - its result;
  - the audit log (`improve.code`);
  - Mission Control (Autonomy tab, "autocoder" section, and `GET /api/cc/autocoder`);
  - the advisory readback row.

  It is never a silent no-op, and it spends nothing: the check happens before any model call.
  Change requests keep piling up for a human-started builder session.

## 2. Optional: an integration base other than production

- **Exact action:** set `BRAMBLELOOP_AUTOCODER_BASE` to a branch or SHA, for example the
  current integration branch.
- **Default:** the production SHA Railway reports (`RAILWAY_GIT_COMMIT_SHA`), so the autocoder
  fixes what is actually running.
- **Cost:** CA$0. **Minutes:** 2.
- **Consequence of waiting:** none. The default works.

## 3. Optional: a reviewer on a different vendor

- **Exact action:** after the OpenAI route is owner-activated (S2, `BRAMBLELOOP_MODEL_ROUTES`), add
  `autocoder.review=openai` to that variable.
- **Default:** the reviewer runs on Claude's deep tier, a different model from the author
  (standard tier).
- **Cost:** within the same ceilings. **Minutes:** 2.
- **Consequence of waiting:** the review stays independent by prompt and model, but not by
  vendor.

## Budgets (enforced in code; you can lower them, never raise them, with variables)

| Budget | Default | Variable |
|---|---|---|
| Per change request, all attempts | CA$3.50 | `BRAMBLELOOP_AUTOCODER_ECR_CAD` |
| Tokens per request | 400,000 | `BRAMBLELOOP_AUTOCODER_ECR_TOKENS` |
| Wall time per run | 40 min | `BRAMBLELOOP_AUTOCODER_WALL_S` |
| Iterations per run | 12 | `BRAMBLELOOP_AUTOCODER_ITERATIONS` |
| Autocoder month (inside the CA$100 model ceiling) | CA$40 | `BRAMBLELOOP_AUTOCODER_MONTHLY_CAD` |
| Agent `autocoder` per day | CA$8 | (agent registry) |

The CA$100 monthly model ceiling (`BRAMBLELOOP_MODEL_MONTHLY_CEILING_CAD`) still binds on top of
all of these. At CA$40 a month, the autocoder can take roughly 11 or more requests to a submitted
branch.

## Where the tests run (B19 A1)

The production worker never executes code the model wrote: no test, script or import from the
modified tree. After the rails pass and the reviewer says SHIP, it pushes `auto/ecr-<id>`, and
`.github/workflows/autocoder-ci.yml` runs the named suites plus `test_vacuity` and
`test_w4_resume_runner` on a GitHub-hosted runner with no secrets and `contents: read`. A
separate job that checks nothing out posts the result as the commit status
`brambleloop/autocoder-ci`. The worker reads it back on its next run; only a green result from
`github-actions[bot]` moves the request to `code_certified`. No owner action is needed for the
workflow itself: it uses only the run's own `GITHUB_TOKEN`.

## Deploy note

The worker image no longer needs `git` (B19 A1 removed every in-worker test run), so the
Dockerfile is unchanged by this unit. It ships through the normal certify-and-promote path.
Nothing here is deployed by this session.
