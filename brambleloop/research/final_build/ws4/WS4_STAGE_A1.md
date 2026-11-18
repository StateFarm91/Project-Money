# WS4 Stage A, part 1: the bounded public-activation authority (off in code)

Main S3 (6953884261): "the bounded public-activation authority as a separately reviewable
increment (stays off until the owner approves that power)". Design: `WS4_standing_policy_design.md`
§1.5, §5.3, §5.4, §7.3, and the binding §9 M1 (going live is P0, Stage D then Stage A) and M6
item 11 (Stage A: activation grant, `deactivate`, rollback).

This increment is the **activation grant**. `EtsyClient.deactivate` and the rollback job are
part 2.

## What ships, and in what state

**The power is OFF.** `ops/standing_activation.py: STAGE_A_ENABLED = False`. While it is False,
three independent places refuse:

| Where | What happens |
|---|---|
| `standing_policy.ceiling_refusals` | Any policy content naming `store.activate` is refused, so no such policy can be approved or activated. |
| `standing_activation.issue` | Refuses before reading anything else. |
| `standing_activation.use_refusal` (through `OwnerGrant`) | Refuses at the client, immediately before the one request that goes public. |

Turning it on needs **both** of these:

1. **The owner's decision to grant the power.** It makes listings public and spends Etsy's
   listing fee without a per-product approval.
2. **A reviewed code change** that flips the constant, like every other ceiling (§9 M5).

After that, the owner still has to sign a policy whose `actions` include `store.activate`. The
statement they sign then says, in plain words, that the policy makes drafts LIVE, the fee, and
the pace.

## The bounds (code ceilings; the owner may tighten, never widen)

| Bound | Value | Basis |
|---|---|---|
| Activations per day | 1, also a DB CHECK on the slot number | §7.3 G-LIMITED first-14-day pace |
| Activations per 7 days | 3 | §7.3 G-LIMITED |
| Listing fees per 30 days | the lower of the policy's figure and CA$4.00 | at most 14 in 30 days at 1/day and 3/7 days, × CA$0.28 (US$0.20 × 1.4154) = CA$3.92 |
| Draft-only policy fees | still CA$0.00 | unchanged v1 ceiling |
| Which drafts | only one in SP lineage | §5.4 |
| Renewal | the listing Etsy holds must have `should_auto_renew` exactly `false` | a renewal is a recurring fee no ceiling here counts |

## What must hold before an activation grant is minted (all read at issue)

1. Mode T, and an EFFECTIVE policy that names `store.activate` (and `store.publish`).
2. **Stage D's G-SHADOW is MET for the same approval** (§9 M1: Stage A may not issue before it).
3. **Stage A's own shadow gate** (`a_shadow`) is met:
   - at least 7 days and 3 would-activate decisions, counted from the approval;
   - zero would-activate decisions for a release the owner never approved for activation
     through today's per-product path.
4. The release is still in policy. This is the same boundary classifier as publication, with
   "not on Etsy" replaced by lineage.
5. **SP lineage:**
   - a `store.publish` SEG of this same policy was consumed for this exact release;
   - the verified `store.published` row naming the recorded listing was written by the job
     that consumed it;
   - the listing is not already active.

   A draft the owner made, or a draft from another policy, is never in lineage.
6. The pace and fee ceilings above.

## The grant

The grant is signed under its own domain (`brambleloop/standing-grant/activate/v1`), so it can
never verify as a publication grant. It is single use and bound to one job, with a 15-minute
TTL. It binds `activation_authority.snapshot`, the same binding as today's per-product owner
activation:
- the listing id;
- the certified payload;
- the certified frames;
- the files the verified publish sent.

`standing_grants.consume` now takes the `action` and refuses a grant of the other kind.

**At use,** the worker reaches `use_refusal` through `OwnerGrant(approval_id="seg:<id>",
job_id=...)`. The client hands it the listing as Etsy holds it. The grant must:
- verify under the issuer key;
- be for `store.activate`;
- be for this release and this listing;
- have been consumed by this job;
- still match the snapshot.

The listing must not auto-renew. An owner's per-product grant is checked exactly as before.

## Not in this increment

- **Wiring into the job path (WS4-8).** Nothing in `store.publish` or `store.activate` requests
  or consumes a standing grant yet. Consume-at-claim for both kinds lands together in WS4-8.
- **Part 2:** `EtsyClient.deactivate(listing_id, grant)` (the only door that sends
  `state=inactive`), the `OwnerGrant.WITHDRAW` grant kind, and the `policy.rollback` job,
  which plans by default.
- **The Stage A shadow runner** that writes `standing_activation.shadow_decision` rows on a
  cadence. `record_shadow` exists and is what the gate reads.

## Owner actions this will eventually need (none requested now)

1. **Grant the activation power.** Making listings public and spending up to about CA$4 a month
   in listing fees without a per-product approval. This is asked only after Stage D's G-SHADOW
   has been met.
2. **Sign an activation policy** under step-up, after Stage A's own shadow gate is met.
