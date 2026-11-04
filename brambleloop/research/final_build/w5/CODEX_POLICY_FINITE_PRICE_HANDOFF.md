# Finite listing prices in policy re-verification

Stacked on policy missing-proof hold PR #87 (`f8e8fe2`). The actual `gate.policy` Worker previously accepted a synthetic stored infinite listing price because the policy gate only tested `price <= 0`. Selling prices now must be finite, positive and non-boolean; an optional compare-at price must also be finite, positive and above the selling price. Invalid stored prices use the existing quality withholding and a corrected valid value can clear that check's hold. No pricing recommendation, budget, purchase or paid provider is changed.

The actual Worker test uses a synthetic listing and checks the hold and recovery; direct tests cover infinities, NaN, booleans and valid values. Independent reviewer reran focused tests 2/2. This does not authenticate price authority or fence a concurrent price update, and no PostgreSQL, actual publication or production verification is claimed.

`test_policy_knowledge.py` is an executable script that calls `sys.exit(0)` during pytest collection, so the combined pytest invocation including it aborted at collection rather than producing a suite result. The regular pytest regression was rerun without that script. A disposable untracked SQLite file was created in this tmpfs worktree during that collection and is not part of the commit.

Python 3.11 tmpfs SQLite policy, proof and withholding regression passed 20/20 after excluding that script.
