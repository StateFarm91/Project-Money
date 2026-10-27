# ops/

Scripts that keep the state files honest. All read committed files only.

| Script | Purpose |
|---|---|
| `day.py` | Prints the competition day number from the immutable start timestamp. |
| `ledger.py` | Summarizes `finance/FINANCIAL_LEDGER.csv` (actuals only). |
| `status.py` | Prints the operator status report the owner expects when asking "Status?". |
| `build_candidates.py` | Merges raw lens research into `research/candidates/candidates.json` and `CANDIDATES.md`. |
| `rank_candidates.py` | Scores candidates and writes `research/OPPORTUNITY_RANKING.md`. |
| `lock.py` | Lease lock for unattended sessions. |
| `board.py` | Job state from the job's own terminal evidence, never from a watcher's belief. |
| `registry.py` | The durable half of the board: persists where each lane's evidence lives (never its verdict) so a restarted process can still answer about the lanes it never saw. `python3 ops/registry.py` prints the survey. |
| `caps.py` (+ `test_caps.py`) | Money caps per track; every budget change must call `assert_within_cap`. |
| `integration_authority.py` | F-711: an integration branch (`claude/w4-INTEG*`) is updated only by the integrator (`BRAMBLELOOP_ROLE=integrator`), only by fast-forward, never deleted. Applied to every pushed ref by the pre-push hook through `deploy_guard.pre_push`; refuses if it cannot be loaded. |
| `registry.py` F-865 | Bounded parallelism: at most `BRAMBLELOOP_MAX_WORK_LANES` (default 6) live work lanes; `survey()["throughput"]` reports lanes integrated per 24 h per lane slot, not agent count. |
| `handoff.py` | F-861/F-862/F-863: a lane's handoff (objective, branch/head from git, decisions, defects, tests, unfinished work, next actions, conclusions) in `brambleloop/research/final_build/handoffs/`; DURABLE only when pushed and committed; `resume` re-verifies against the remote. |
| `review.py` | F-714/F-866: high-risk classes (customer-facing, financial, marketplace, security, infrastructure, Product Truth) by path; an adversarial review of one lane head by a different agent, recorded in `REVIEWS.jsonl`, never certifying; `ops/integrate.py` refuses a high-risk lane without a NO_BLOCKERS review of exactly its head. |
| `disagreement.py` | F-715: competing build proposals with evidence of closed kinds (test with rerun command, primary evidence, Product Truth, marketplace outcome, economics); `resolve` is deterministic and never reads proposer or model. |
| `workspace.py` | F-716: one lane's proposer, implementer, reviewer, disagreement, evidence, tests, cost, accepted/rejected approach and integration result, each PRESENT with its source or MISSING. |
