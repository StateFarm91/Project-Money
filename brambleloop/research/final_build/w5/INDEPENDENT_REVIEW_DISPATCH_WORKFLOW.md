# Independent review: dispatch-board workflow

## Update after integrator note: new head `e9d73d25eb2705d2c5ea1933be76df2f4879566e`

### What changed between `8e5bb1f` and `e9d73d2`
- **The workflow file was moved.** `.github/workflows/dispatch.yml` is now `ops/github/dispatch.yml.pending`. A `git diff` between the two blobs is empty, so the content is byte-identical.
- **The README line was updated** to name the pending path.
- **No `.github/` directory remains** on `claude/w4-INTEG8-next`.

### Is the workflow still live anywhere?
I checked every remote branch that matches the push filters (`opus2/**`, `codex/**`, `claude/w5-**`) through the contents API. **None of them contains `.github/workflows/dispatch.yml`.** No branch can trigger the workflow now. The two runs at 20:09Z and 20:13Z wrote only the single board comment 6587295178 on #28.

The README still says "It runs only once the workflow file is on the default branch". For `push` that statement is wrong; see F8 for the correct wording.

### F8 (Medium, required before release): drop the `push` trigger

**How the push trigger behaves.** For `push`, GitHub runs the workflow definition **from the pushed commit**. Every other trigger in this file (`schedule`, `issue_comment`, `workflow_dispatch`) runs only from the default branch. In practice this means:
- (a) **It activates without the release.** Any branch that matches the filters and carries the file runs the workflow before the release. That is exactly what happened on INTEG8-next, bypassing the "owner decision / independent review" gate.
- (b) **After the release, every new matching branch carries it.** Once the file is on the default branch, every new `opus2/**`, `codex/**` or `claude/w5-**` branch cut from that branch carries it. Each push to those branches then starts a run.
- (c) **Branch copies can be changed.** A copy on a branch can be edited (different permissions, different code, another trigger), and that edited copy runs on push to that branch.

**This is not a privilege escalation.** Anyone who can push to this repository can already add any workflow with any permissions. Forks never receive this repository's token. The job always checks out INTEG8-next code, never the pushed code.

**What it does break is controlled activation.** Pre-release activation already happened once, and a modified copy on any branch would run under this workflow's name. This undermines the review gate (Shadow-mode discipline), and the trigger buys almost nothing: the 5-minute schedule and the `issue_comment` trigger already keep the board current.

**Recommendation:**
- Remove `push:` entirely from the release version.
- If push latency is ever wanted, use a `workflow_dispatch` that the watcher calls instead. Do not restrict `push` by branch: a branch filter cannot stop a copy on another branch from running.
- As defence in depth, add a job guard: `if: github.ref_name == github.event.repository.default_branch && (...existing condition...)`. A modified copy could delete the guard, but it does stop accidental activation from unmodified copies on feature branches.

### Verdict
- **Current head `e9d73d2`: SHIP.** No workflow is active, and the inert `.pending` file is safe to carry.
- **Release version (the `.pending` content moved to `.github/workflows/dispatch.yml` on the default branch): SHIP with one required change, F8.** Remove the `push` trigger. Fixing F1 (author filter on #28, plus locking the issue), F2 (match only the bot-authored board comment) and F3 (`None None` review rows) in the same commit is strongly recommended. F4 through F6 are optional hardening. The content exactly as reviewed, push trigger included, is **DO NOT SHIP** until F8 is fixed.

---

## Original review (head 8e5bb1f; still applies to the `.pending` content)

- **Subject:** `origin/claude/w4-INTEG8-next` @ `8e5bb1f089505576d7c0e4d1083279c734c205ef`
- **Files:** `.github/workflows/dispatch.yml`, `ops/dispatch_board.py`, `ops/assignments.py`, `ops/test_assignments.py`, `dispatch/README.md`
- **Reviewed:** 2026-11-02 (UTC). This was a read-only review. I modified nothing and pushed nothing.
- **Repository:** StateFarm91/Project-Money. It is PUBLIC, and its default branch is `claude/repository-setup-nc9x6o`.

## Verdict: SHIP (8e5bb1f)

The workflow meets all of the owner's hard requirements:
- It is coordination-only and never assigns, reassigns, merges or deploys.
- The token is scoped to `contents: read, issues: write`.
- It does not reference any secret except `GITHUB_TOKEN`, and never prints it.
- It makes no model or paid API calls.
- Nothing from a comment, title or branch name is interpolated into `run:`.

None of the findings below is a security breach or a blocker. F1, F2 and F3 are cheap fixes that should go into the same release. F0 is a documentation and honesty correction that has to be made in BUILD_STATE and the README now.

## Verified facts

- **Dry run passes.** I extracted exactly the sparse set (`COORDINATION.json`, `dispatch/`, `ops/assignments.py`, `ops/dispatch_board.py`) into an empty temp directory. I then ran `python3 -I ops/dispatch_board.py --repo StateFarm91/Project-Money --issue 28` with no token. It exited 0 and printed a board, so every module it imports is present. With `--post` and no token it still exits 0 and writes nothing.
- **The workflow is already live.** GitHub lists `dispatch-board` (`.github/workflows/dispatch.yml`) as **active**. There are two successful `push` runs on `claude/w4-INTEG8-next`, at 20:09:05Z and 20:12:58Z. Comment 6587295178 on #28 was posted by `github-actions[bot]` at 20:09:12Z and edited at 20:13:32Z. See F0.

## 1. Permissions — OK

- The top-level `permissions:` block replaces the repository's default token permissions. Every scope not listed is `none`, so the job cannot gain more through the default settings.
- There is no `pull_request_target`, `workflow_run` or `pull_request` trigger. No fork-PR path exists.
- `issues: write` is needed to create and patch the comment.
- `contents: read` is what `actions/checkout` needs. On a public repository it adds nothing an anonymous reader does not already have.
- This is the minimum practical set.

## 2. Untrusted input — OK, with one hardening item and one spoofing finding

**No script injection.** The only `${{ }}` in `run:` is `github.repository`, which is trusted. The comment body appears only inside an `if:` expression (`contains(...)`), which is evaluated by the Actions engine and never reaches a shell. Comment text reaches Python only as JSON data, and only these values are echoed into the board:
- `who`, from the fixed set MAIN, SECONDARY or CODEX;
- `kind`, which matches `[A-Z-]+`;
- the timestamp;
- `html_url`.

A commenter therefore cannot inject markdown, mentions or code into the board.

**Which code runs:**
- **`schedule`, `issue_comment` and `workflow_dispatch`** use the workflow file on the default branch.
- **`push`** uses the workflow file **in the pushed commit**. Pushes made in forks run in the fork, with the fork's own token, and never get this repository's token.
- **On every trigger** the job checks out and runs `claude/w4-INTEG8-next`, not the pushed branch.

**Push access controls the code.** Anyone who can push to `claude/w4-INTEG8-next` controls the code that runs with the `issues: write` token. This is acceptable, because anyone with push access can already add an arbitrary workflow with broader permissions. It grants no new privilege.

**Hardening (Low):** set `persist-credentials: false` on the checkout. The script reads the token from `env` and does not need it written into `.git/config`.

**Spoofing (Medium, F1):** see F1 below.

## 3. Loops, spam and rate limits — OK

- **No self-trigger loop.** Writes made with `GITHUB_TOKEN` do not trigger workflows, and only `issue_comment: created` is subscribed in any case.
- **At most one write per run.** Each run does either one PATCH or one POST, and it only POSTs when no board comment exists. A commenter cannot make it post unbounded comments.
- **Floods are collapsed.** `concurrency` with `cancel-in-progress` merges a comment flood into roughly one run at a time.
- **Rate-limit cost.** One run costs `2 × ceil(N/100) + 1` API calls for N comments; the comment list is fetched twice. The `GITHUB_TOKEN` limit is 1,000 requests per hour per repository, which is ample at current volume.
- **Noise from other comments.** `issue_comment` fires for comments on every issue and PR in the repository. Those runs are skipped by `if:`, which adds noise to the Actions list but costs nothing.
- **Constant edits (Low, F4).** The board text contains `computed <timestamp>`, so `c["body"] != text` is always true. The bot PATCHes on every run, about 288 times a day from the schedule alone. That fills the edit history but sends no notifications.

## 4. Correctness of `ops/dispatch_board.py`

- **Error handling — good.** The board is fully computed before any write. An API or HTTP error raises an exception, and the job fails cleanly with no partial post. `urllib` errors print only the URL, never the headers.
- **Pagination — correct.** The loop stops when a page has fewer than 100 items; an exact multiple of 100 costs one extra empty call. Issue comments come back in ascending order, so de-duplication picks the oldest marker comment.
- **No token — correct.** Without a token it reads the public API and prints. `--post` is ignored without a token.
- **Unanswered-message logic — a reasonable heuristic.** Any later tagged message from a different sender clears all earlier ones. CODEX counts as "the other side" for MAIN.
- **Tag parsing is strict (Low, F5).** `[MAIN] **ASSIGN**` and `[MAIN] Assign` give an empty kind and are never tracked. `[MAIN] ASSIGNMENT` is not in `NEEDS_REPLY`.

## 5. Concurrency, timeout, pinning and sparse checkout

- **Concurrency — adequate.** It uses a single group with `cancel-in-progress: true`. Cancelling mid-PATCH is harmless. Cancelling right after a POST, before the listing updates, could in theory leave two board comments; this is rare and self-limiting.
- **Timeout — adequate.** `timeout-minutes: 3` covers a run that normally takes a few seconds; each request has a 30 s socket timeout.
- **Pinning (Low, F6).** `actions/checkout@v4` is a mutable tag. It is a first-party action, so the risk is low, but supply-chain best practice is to pin a full commit SHA and keep `# v4.x.y` as a comment.
- **Sparse checkout — correct.** It is in non-cone mode. Every file the script touches is present: `COORDINATION.json`, `dispatch/events/*.jsonl`, `ops/assignments.py` and `ops/dispatch_board.py`. `assignments.py` imports only the standard library.

## 6. Secrets in logs — none

- `print(text)` prints only the board.
- The token goes only into the `Authorization` header.
- No `set -x` and no echoing of environment variables.

## Findings and fixes

| # | Severity | Finding | Fix |
|---|---|---|---|
| F0 | Medium (honesty/process) | The workflow comment and the README say it "runs ONLY when this file is on the default branch" and "needs an owner decision". This is false for `push`: GitHub runs the workflow from the pushed commit. It is **already active** and posting on #28 because the file is on `claude/w4-INTEG8-next`, which is one of its own `push` branches. It will also run on any `opus2/**`, `codex/**` or `claude/w5-**` branch that contains the file. | Correct the comment, the README and BUILD_STATE to "live since 2026-11-02T20:09Z via push trigger". If the owner's decision was meant to gate going live, remove the file from INTEG8-next (or remove the `push` trigger) until that release. |
| F1 | Medium | Messages are not filtered by author. Anyone on GitHub can comment on a public issue. A forged `[MAIN] ASSIGN` creates a false "unanswered" alarm. A forged `[SECONDARY] ACK` hides a real unanswered Main message. The same forged text can also mislead the sessions that read #28 for instructions, which is a prompt-injection channel outside this workflow. | In `messages()`, keep only comments where `c["author_association"] in {"OWNER","MEMBER","COLLABORATOR"}` (all sessions post as StateFarm91, which is OWNER). Also **lock issue #28** so only collaborators can comment; this also stops comment floods. |
| F2 | Low-Medium | `post()` edits the first comment that contains `<!-- dispatch-board -->`, whoever wrote it. If the bot's board is ever deleted, an outsider's comment containing the marker becomes the target. If the PATCH is refused, every run fails; if it is allowed, the bot overwrites the outsider's comment. | Match `BOARD_MARK in body and c["user"]["login"] == "github-actions[bot]"` (or `c["user"]["type"] == "Bot"`). In `messages()`, exclude comments by author rather than by marker. |
| F3 | Low (visible bug) | 2 of the 72 `reviews` entries in COORDINATION.json have no `recorded` or `subject` (they use `pr`, `at` or `verdict`). `A.parse(None) or t` treats them as recorded now, so the live board permanently shows `- None None` twice under "Reviews recorded since Main's last message". Reproduced in the dry run. | Use `rec = A.parse(r.get("recorded") or r.get("at"))`, skip entries where `rec is None`, and print `r.get("subject") or f"PR {r.get('pr')} {r.get('sha')}"`. |
| F4 | Low | The timestamp makes every run a PATCH. | Compare bodies with the `computed …` line removed, and PATCH only when the content changed. |
| F5 | Low | The tag grammar is strict (bold or lowercase kinds are ignored). | Accept `\**` around the kind and use `re.I`, or document the exact form in the issue body. |
| F6 | Low | `actions/checkout@v4` is not SHA-pinned, and `persist-credentials` is left at its default `true`. | Pin the full commit SHA and add `persist-credentials: false`. |
| F7 | Info | `issue_comment` creates a skipped run for every comment anywhere in the repository. The schedule auto-disables after 60 days with no repository activity. | No action needed. |

`ops/assignments.py` and `ops/test_assignments.py` were read but not run. I was asked not to run heavy tests, and the board uses only `status` and `load_coord`, which the dry run exercised. Nothing in those two files affects the security of the workflow.
