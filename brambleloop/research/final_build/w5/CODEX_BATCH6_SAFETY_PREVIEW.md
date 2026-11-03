# Codex Batch 6 safety preview — review only

This isolated preview combines these exact independently developed heads, all
descended from `claude/w5-INTEG1` at `7c42e706569af8d255d716133fc333d5c600c747`:

* A1 child safety: `ec9dc9a8c098bbb3e00b85c1206bafd06eb02871` (PR #34).
* A2 name and object truth: `94d165ec83287bab881083f0c2abed08bbed8b80` (PR #35).
* A4a research to concept: `bc65dd88010f20843eefc8c1f4d44676c2a1d86a` (PR #33).

The first merge retains both A1 and A2 coordination claims. The second retains
the A4a claim as well, and resolves the `publish/eligibility.py` conflict by
running both the A2 stripe proof and the A4a dishcloth and heat checks. Source
branches remain unchanged. Review both merge commits and the actual behavior,
not just this description.

The combined A1/A2/A4a regression revealed that A4a's nature-themed house
descriptors were refused by A2's construction-intent allowlist, stopping the
research-to-draft handoff. This preview uses neutral descriptors already
accepted by that existing contract; it does not relax the allowlist or bypass
originality checks. The descriptor vocabulary remains finite and can still be
exhausted or held by competing titles. Re-review the naming change and run the
combined suite on the final commit.

The owner's intended Batch 6 integration branch `claude/w6-INTEG1` was absent
from GitHub when checked. This preview is **not** that branch, an integration
verdict, a deployment candidate, or evidence of physical testing. Main retains
responsibility for integration, certification, and deployment. A1 reapproval and
physical evidence authority, A4a retry and atomic audit recovery, cross-branch
evidence fencing, independent acceptance, combined regression, and PostgreSQL
concurrency evidence remain open. The original PR limitations still apply.

Test execution and review results must identify the exact candidate commit and
Python/database environment; do not treat an SQLite result as PostgreSQL proof.
