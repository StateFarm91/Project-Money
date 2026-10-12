# W4-FUNDING: funding asks are prepared packets (F-871, F-100)

Branch `claude/w4-FUNDING`, based on `origin/claude/w4-INTEG2` 083c9fc. Nothing was spent, no key
was set and no provider was contacted.

## What is new

**`src/brambleloop/finance/funding_packet.py`** builds one standard, deterministic record from
rows the runtime wrote. Two packets:

- **`credit_packet(db, provider)` (F-871).** Contents:
  - **Bounded experiment:** what the credit buys, as the provider's 30-day spend broken down by
    purpose from `cost_entries`.
  - **Max spend:** the monthly ceiling the gateway enforces before every call, this month's
    spend, and the headroom.
  - **Run rate:** the measured daily run rate.
  - **Outage evidence:** the `model.probe` failure share, parked model jobs, and funding
    exhaustion events.
- **`diversification_packet(db)` (F-100).** Contents:
  - **Concentration:** the AI-provider axis from `scale.dependency` (holders, share, verdict).
  - **Measured resilience value:** the probe failures, parked model jobs and exhaustion events a
    second provider would have carried.
  - **Bounded trial:** a one-off trial capped at CA$10.

Every unmeasured figure is null, with the reason. `approves_itself` is always false: approval
stays the owner's act of setting the provider's key in the hosting environment after reading the
packet.

**Wiring:**

- `GET /api/funding/packets` serves both packets. It is a public, read-only aggregate, the same
  class as `/api/status` spend, with no customer data; `test_customer_data_auth` sweeps it.
- `ops/funding.note` is the producer of the owner's "add credit" action when a provider refuses
  on a spent balance. That action now carries its prepared packet: ceiling, spent this month,
  headroom and run rate.

## Acceptance evidence (tests through the shared slot)

`tests/test_w4_funding.py` passes 5/5. It covers:

- An empty ledger is unmeasured, never 0.
- The credit packet names its purposes, its bound and its outage evidence.
- The diversification packet carries the measured value and a one-off bound.
- The owner funding action carries the packet.
- The route is registered.

Regression:

| test | result |
|---|---|
| `test_funding` | 10/10 |
| `test_spend_governance` | 36/36 |
| `test_customer_data_auth` | 9/9 |
| `test_route_auth_default_deny` | 7/7 |
| `test_vacuity` | 8/8 |

## Rows

- **F-871:** advanced. The "bounded experiment + max spend prepared first" packet is now one
  standard record attached to the owner's funding action. Production reads `model_provider` OPEN
  (credit was added), so the row is re-verified, not assumed done. It closes on a production
  readback of `/api/funding/packets` after a deploy.
- **F-100:** advanced. The approval card now exists with measured resilience value.

**Not done, on purpose: no hard refusal of unapproved providers.** The row's earlier
next_action also asked for gateway routing to refuse an "unapproved" provider. That was not
done. Production already runs owner-funded Anthropic, OpenAI and BFL keys, and the owner
setting a key is today's approval channel. A new refusal would change live behaviour without an
owner-approved list of providers. Owner decision needed: whether an explicit approved-provider
list should gate routing.

The funding decision itself remains the owner's (gate `model_provider`).

## Status at the owner pause (2026-10-12)

**DONE.** Pushed before the pause; no change since.

- **Rows:** F-871, F-100 advanced (none closed).
- **Tests:** test_w4_funding 5/5; test_funding 10/10, test_spend_governance 36/36, test_customer_data_auth 9/9, test_route_auth_default_deny 7/7, test_vacuity 8/8.
- **Required regression set** (test_launch, test_cost_governance_wave2, test_search_hero_publish,
  test_cert_listing_frames, test_v11_autonomy_timeline): not run on this branch. That set was
  added after this branch was pushed.
- **Known defects:** none.
- **Next step:** integrator merge, deploy, read back /api/funding/packets; owner decides whether an approved-provider list should gate routing.
