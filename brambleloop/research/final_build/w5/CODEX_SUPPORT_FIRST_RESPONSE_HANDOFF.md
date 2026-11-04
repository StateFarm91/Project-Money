# Support first-response truth: review request

Continuation from `claude/w5-INTEG1` at
`7c42e706569af8d255d716133fc333d5c600c747`. A confident held support draft
sets `SupportCase.resolved` without sending it, but the first-response watch
treated `resolved` as a delivered reply. This suppressed or closed the owner
action and incident even while the buyer was waiting.

The first-response watch now requires recorded sent evidence (`sent` or
`first_response_at`); a draft or resolved flag alone no longer closes it.
`tests/test_codex_support_first_response_truth.py` exercises actual
`support.reply` Worker processing on file-backed SQLite, reopens the database,
checks the 30h owner alert and 37h escalation, then records a synthetic owner
send and checks closure. No customer message is sent by the test or code.
Python 3.11 focused support, department and fresh-message tests passed 32/32;
an attempted broader FB4 run was interrupted after 6 passes and is not a suite
pass.

Independent review confirms the narrow issue. A legitimate owner decision to
close a spam, withdrawn, or duplicate message without replying currently has
no separate authenticated disposition in this watch; such a case can keep an
alert until an explicit resolution workflow is designed. Existing truthy
`first_response_at` evidence is not newly authenticated here. Concurrent
customer case updates and PostgreSQL have not been verified. Do not treat this
change as a completed support department or authority contract.

Follow-up: newly drafted cases remain unresolved; existing resolution and sent
state are not deliberately changed by drafting. The `support.reply` worker
skips a case already recorded sent, and direct draft recording leaves an
already-sent answer untouched. This covers sequential operation only: a send
that races between the check and write was not transaction-fenced.

The sent recorder, draft recorder, draft copy check and response timing writer
now lock the case row before their respective writes, recheck sent state, and
skip an obsolete draft. The opt-in `test_codex_support_response_pg.py` passed
on a fresh local PostgreSQL 16 database, forcing actual Worker and owner-sent
transactions in both orders. Focused Python 3.11 SQLite tests pass 32/32. No
real message was sent. This is a limited fence for those four paths: intake,
triage, raw SQL, other writers and SQLite concurrency still need audit. The
runtime hunk in `runtime/release.py` overlaps other work and requires additive
integration review. No authenticated disposition or sent-evidence guarantee is
introduced by row locking.
