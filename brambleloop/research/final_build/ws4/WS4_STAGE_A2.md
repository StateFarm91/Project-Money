# WS4 Stage A, part 2: taking standing-policy listings back down

Main S3 (6953884261), Stage A per design §9 M1 and M6 item 11, part 2 of 2. Part 1 is
`WS4_STAGE_A1.md` (the activation grant, off in code). This part implements design §5.3 v2
(rollback) and §5.4 (the withdrawal authority).

## What ships

| Piece | Where | What it does |
|---|---|---|
| `EtsyClient.deactivate(listing_id, grant=)` | `integrations/etsy.py` | The only request in the client that sends `state=inactive`. It reads the listing first and hands that reading to the grant. It sends one PATCH, then reads the listing again and raises unless Etsy reports `inactive`. `update_listing` still refuses `state`. |
| `OwnerGrant.WITHDRAW` (`store.withdraw`) | `integrations/etsy.py` | A grant that covers taking down one listing and nothing else. It is never accepted for publish or activate. |
| `withdraw_refusal`, `withdraw`, `plan` | new `ops/standing_withdrawal.py` | The bounds on a withdrawal (below), one recorded withdrawal, and the rollback plan. |

## The bounds (§5.4), re-read from the database at the client immediately before the request

1. **SP lineage.** A standing activation grant that a job consumed made this listing live. A
   listing the owner published personally, or one made live through today's per-product owner
   approval, is never in lineage, so this code can never reach it.
2. **The policy has stopped.** The owner's standing policy reads SUSPENDED, revoked (NONE), DEAD
   or BROKEN. While the policy is EFFECTIVE, ISSUE_PAUSED or NOT_YET, nothing is withdrawn.
3. **Rate.** At most 10 withdrawals in any hour.
4. **Before-state read-back.** Etsy's current copy of the listing has this id and reads
   `active`.

**The phase is deliberately not checked.** A withdrawal is deny-direction, and it is most
wanted right after the owner rolls the phase back to SHADOW. A test withdraws through a client
that is in SHADOW with no publishing authority. The client still requires a credential.

Every withdrawal is recorded as `listing.withdrawn`, with the state Etsy reported before and
after. The local Listing becomes `withdrawn`. Etsy does not refund the listing fee.

## The rollback plan executes nothing

`plan(db)` runs only on a stopped policy. It lists two things:
- the live SP-lineage listings;
- the SP-lineage drafts (lineage as defined in part 1).

It records `policy.rollback_planned` for the owner's card, once per distinct plan. It changes
nothing on Etsy and nothing locally.

To execute the plan, call `withdraw` once per listing, inside the bounds above. Nothing runs it
automatically. The policy has no signed "withdraw on stop" field, and adding one would be an
owner-signed content change, not a default.

## Not in this increment

- **The owner-asked case in §5.4.** The owner's own Etsy dashboard covers it today. An
  owner-signed withdrawal request is not built.
- **Draft deletion on stop** (§5.3 v1, `delete_listing`). The plan lists the SP drafts, and
  `delete_listing` with its expected-state read-back already exists. Wiring a withdrawal grant
  into it is a small follow-up, if you want it.
- **A job handler and cadence** for `plan`. It is a function today, like `record_shadow` in
  part 1. It belongs with WS4-8's job-path wiring.
