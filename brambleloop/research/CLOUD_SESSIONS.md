# Cloud sessions as Build-2 throughput — viability assessment

Date: 2026-09-25. Assessed by the coordinator against the owner's stated pilot preconditions.
Status of each claim below: VERIFIED means I ran the check in this container and read the result.

## Verdict

Cloud sessions are **viable for a bounded class of work** and **not viable for Visual**. They are
invisible to the operator board, so they may only be used where the job's own terminal evidence is
a pushed branch. One pilot has been dispatched under exactly those terms.

## Findings against the owner's preconditions

### No production credentials — VERIFIED, and structural rather than promised
This environment holds no Brambleloop production credential. Checked by name, never by value:
`BRAMBLELOOP_SECRET_KEY`, `DATABASE_URL`, `ETSY_KEYSTRING`, `ETSY_SHARED_SECRET`,
`BRAMBLELOOP_OPS_TOKEN`, `RAILWAY_TOKEN` are all absent. A child session inherits this environment.

This matters more than an instruction would: a cloud session **cannot** perform a real Etsy write,
read the sealed credential, or deploy, because the material to do so does not exist in the
container. It is not trusted to refrain; it is unable. The Etsy refresh token stays sealed in
production's Postgres under production's secret key, neither of which is reachable from here.

`GITHUB_TOKEN` is present (needed to push a branch). AWS keys present belong to the harness, not to
Brambleloop.

### Dependency availability — VERIFIED, with one hard exclusion
`brambleloop/requirements.txt` is 12 ordinary wheel-available packages. `.venv` is **not** committed
(`git ls-files` matches 0 paths under `.venv/`), so a cloud session must build one; that is roughly
a one-minute `pip install`.

**Mitsuba is deliberately absent** (~200MB renderer, documented in requirements.txt as hand-run
only). Therefore **Visual/Mitsuba work cannot move to cloud sessions.** This is not a limitation to
route around — it coincides exactly with the owner's own precondition of no Visual-owned files.

### Operator-board integration — VERIFIED GAP, and it governs everything else
`ops/board.py` determines job liveness by reading `/proc/<pid>/status` and iterating `/proc`. That is
machine-local by construction. A cloud session runs in a separate container with a separate `/proc`,
so **the board cannot see, supervise, or reap a cloud session.**

Claiming otherwise would be this codebase's recurring defect exactly: a check that cannot see the
thing it exists to measure. So cloud sessions are not enrolled on the board and are not reported as
board jobs. This is consistent with the owner's coordinator rule — job completion comes from the
job's own terminal evidence, never from a watcher's state. For a cloud session the terminal evidence
is **a pushed branch**, which is observable from any container.

### Repository/branch isolation and file ownership — AVAILABLE, must be imposed by brief
A cloud session clones fresh and pushes to its own `outcome_branch`. It shares no filesystem and no
worktree with the five local lanes, so it cannot corrupt their state. Ownership collisions are
therefore only possible at merge time, and are prevented the same way the local lanes are: an
explicit exclusive file boundary in the brief, plus a `git status --porcelain` boundary check that
the session must paste as part of its completion sentinel.

### Artifact persistence — EPHEMERAL, same as local
The container is reclaimed after inactivity. Nothing survives that is not committed and pushed.
Cloud sessions are therefore unsuitable for work whose product is a large artifact rather than a
diff.

### Merge coordination — UNCHANGED
Everything still merges through the single coordinator queue. A cloud branch is merged by me, after
its blast-radius suite runs on the integrated tree. Cloud work does not gain deployment authority.

### Spend accounting — SEPARATE POOL
Cloud sessions draw on the $250 promotional cloud credit, not on the constrained interactive weekly
allowance, and not on the CA$20/month recurring infrastructure ceiling (they are not infrastructure;
nothing recurring is provisioned). So cloud work does relieve the interactive constraint, which was
the owner's actual question.

## The class of work cloud sessions can take

Suitable: pure-computation audits, additive test authoring, research and documentation, analysis of
committed code — anything whose output is a diff and whose proof is a green suite.

Unsuitable: Visual/Mitsuba (renderer absent by design); anything needing production credentials,
the sealed Etsy token, Railway, or the ops token; anything whose completion must be observed by the
operator board; anything mutating state shared with a live lane.

## Pilot dispatched

One low-risk pilot, `claude/cloud-pilot-products-audit`: an adversarial audit of the four unowned
pure-computation product modules (`personalisation`, `motifs`, `texture`, `vessels`), additive only.
Verified before dispatch that no live lane has changed any file under `products/`.

Its completion sentinel is objective and self-evidencing: the research file exists, the new test file
passes, the full suite is green at or above the recorded baseline with zero failures, and
`git status --porcelain` shows no file touched outside the declared boundary. Nothing about that
sentinel depends on a watcher.
