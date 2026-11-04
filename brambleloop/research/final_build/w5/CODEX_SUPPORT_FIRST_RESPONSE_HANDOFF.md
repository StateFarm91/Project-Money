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

Triage follow-up: each case is now re-read and locked in its own transaction,
preserving oldest-first processing without locking the entire case history.
Intake metadata and post-enqueue bookkeeping also lock the case; sent cases
are not selected for a new draft. Python 3.11 focused SQLite tests pass 46/46.
An earlier version using one all-case lock passed the opt-in PostgreSQL race
test in both send/triage orders; the final per-case version has **not** been
run on PostgreSQL because workspace disk space was exhausted. The enqueue step
remains separate, so an owner send can still race a draft enqueue (the worker
skips an already-sent case). Teardown/lesson and other case writers, SQLite
concurrency, sent-evidence authentication, and no-reply disposition remain
open. No customer message was sent.

Timestamp follow-up: an unsent case no longer treats a malformed, future, or
pre-receipt `first_response_at` as a sent reply. The watch, triage, draft
recorder, reply Worker and timing writer use the same check; a real Worker
test confirms a malformed legacy marker remains stored while a draft can be
created and the owner alert remains open. Python 3.11 focused SQLite tests
pass 48/48. A valid legacy timestamp and the `sent` flag are still not
cryptographically authenticated. The owner-sent recorder refuses to overwrite
an invalid historic marker, so a separately authorized correction workflow is
still required. The final timestamp change has not been tested on PostgreSQL.

Intake follow-up: duplicate lookup now requires the same product and version in
addition to the existing buyer/message/time key; a question about another
purchase is no longer discarded as a duplicate. The operator API passes the
version through and overlong buyer references are refused rather than silently
truncated. Existing intake hashes remain unchanged. Actual authenticated API
tests cover same-scope retries, distinct products/versions, explicit receipt
times and rejected overlong references. Python 3.11 focused SQLite tests pass
49/49. A missing scope and a known scope deliberately form separate cases.
At this stage lookup and insert were not atomic; scope metadata was not newly
authenticated. No customer messages sent.
The `app/main.py` route overlaps other work and needs integration review.

Intake transaction follow-up: the supported owner-recorded path now serializes
duplicate lookup, standard case creation, and receipt metadata in one
transaction. It uses SQLite `BEGIN IMMEDIATE` or a PostgreSQL transaction
advisory lock and holds existing buyer-case row locks in id order. The actual
operator HTTP handler passed concurrent identical requests and returned one case
on file-backed SQLite, both with and without explicit receipt time; reopening
the database and retrying reused the same case. A simulated interruption after
the insert rolls the case back. Python 3.11 focused SQLite tests pass 51/51.
Independent review exercised the concurrency and rollback tests. No PostgreSQL
test was run for this change under the workspace storage constraint; the lock
covers only this intake path, not direct writes or other intake APIs. Lock wait,
large customer histories, sent/scope authority, and other support races remain
open. No customer messages were sent.

Hotspot follow-up: repeated cases or repeated row mentions from the same
recorded buyer reference now count once per product, version and row; unknown
buyer references and malformed rows do not manufacture corroboration. The
workspace retains separate candidate entries for different versions. A real
`support.triage` Worker and file-backed SQLite restart test confirms the
candidate audit contains no buyer references. Focused Python 3.11 SQLite
support/department/trust/workspace tests passed 54/54; an independent reviewer
reran the Worker test. Distinct recorded references are not authenticated
distinct people, and versionless cases remain grouped as version unknown.
These remain candidate defects, not physical proof or confirmed defects.
PostgreSQL and duplicate audit-event recovery are not verified here. No
customer messages were sent.

Service-level follow-up: held drafts and malformed timings remain untimed for
the delivered-response metric, and an incomplete set of recent delivered
timings cannot make `meets_target` pass. The verdict uses unrounded shares;
display shares remain rounded and the response explains that distinction.
Non-finite, negative, boolean and nonnumeric timing inputs are refused.
Python 3.11 focused tmpfs SQLite suites passed 57/57; an independent reviewer
reran service/trust and the rounding-boundary tests. This is not authenticated
proof of delivery: legacy sent markers remain unsigned and other malformed
case fields can still make a reading fail. The latest head was not tested on
PostgreSQL. No customer messages were sent.
