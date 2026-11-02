# Dispatch: how every engineering worker receives, acknowledges and reports work

This is mandatory for opus2 (Secondary Opus), Codex and every integrator-supervised worker.
The decision is I-DISPATCH-PROTOCOL in `COORDINATION.json`.

The integrator cannot wake or inspect another session. Delivery works **by polling**: you read
this branch when you wake. A PR comment or a record line does not prove you received anything;
only your `ack` event does.

## On every wake, first
```
git fetch origin claude/w4-INTEG8-next && git checkout origin/claude/w4-INTEG8-next -- COORDINATION.json dispatch ops/assignments.py
python3 ops/assignments.py status | grep -E "^\S+ +<you>"     # your assignments, stage, deadlines
python3 ops/assignments.py event <you> - heartbeat --note "awake" --push
```
`<you>` is `opus2`, `codex`, or the worker name in the assignment.

## For each assignment you own
| When | Command |
|---|---|
| First wake after it is posted (before `ack_due_by`, 3 h) | `event <you> <ID> ack --push` |
| You begin work (claim-checked; refused if it is not yours) | `event <you> <ID> start --push` |
| At least every 4 h while working | `event <you> <ID> heartbeat --note "<what>" --push` |
| A tested commit is pushed | `event <you> <ID> checkpoint --sha <sha> --push` |
| You want the integrator's review | `event <you> <ID> review_requested --sha <sha> --push` |
| You cannot continue | `event <you> <ID> blocked --note "<exact blocker>" --push` |
| You give it up | `event <you> <ID> released --push` |

Write only your own file, `dispatch/events/<you>.jsonl`. Lines you write anywhere else are marked forged and ignored.

## What the integrator does
On each check-in the integrator:
- reads `status` and `stale`;
- launches a review for each `review_requested`;
- records verdicts and integration in `COORDINATION.json`;
- posts the next assignment.

An overdue assignment (no ack by `ack_due_by`, no checkpoint by `checkpoint_due_by`, or no progress for 4 h) is REPORTED to the owner with the specific limitation. It is never moved without the owner's authorization (I-THREE-OPERATOR-STRUCTURE). If the owner authorizes a transfer, it is recorded in `ownership_history`, and `claim-check` then refuses the former owner.
