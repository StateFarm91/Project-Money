# W4-CCNOTIFY: F-897 Smart Notification Policy (deadlines and commercial events)

Branch `claude/w4-CCNOTIFY`, cut from INTEG2 `083c9fc`. Domain: command_center_ui. This is the domain's one class-A row in `PRELAUNCH_SCOPE.json`.

**Criterion** (registry F-897, quoted): "Notify the owner for decisions, risk, deadlines, meaningful commercial events and anomalies - not routine machine chatter. Alerts are deduplicated, severity-ranked and actionable."

## What already existed

`app/command_center/notifications.py` already provided:

- decisions, from the approval inbox;
- risk, from open incidents;
- anomalies: dead letters, paused spend scopes and security-refusal bursts;
- deduplication on `dedupe_key`;
- severity ranking;
- quiet hours and a digest;
- auto-resolve when a condition clears;
- suppression of routine events, which are counted rather than shown.

Two parts of the criterion had no source:

- **Deadlines.** The `deadline` column existed but was never set.
- **Meaningful commercial events.** None were produced.

## What this branch adds

**Deadlines**

- An incident's own `detail.deadline` sets the notification's deadline. One example is the Etsy policy-violation census, which already writes one.
- An open owner action with its own `expires_at` inside `DEADLINE_HORIZON_DAYS` (30 days) also produces a deadline. It is surfaced exactly once:
  - an approval card that merges the action inherits the earliest such deadline;
  - otherwise it becomes its own `owner_deadline:<id>` notification.
- Anything due within `DEADLINE_SOON_HOURS` (48 hours) is raised to at least `high`.
- When the owner action is closed, its deadline notification resolves automatically.
- Within one severity, the nearest deadline sorts first, on both the server and the view (`dueMs`).

**Commercial events**

These come from the `orders` table only, and are aggregated so that a sale never becomes one alert per row:

- `commercial:first_order` is `high`, and stays up for 7 days after the order.
- `commercial:orders:<UTC date>` is one notification per day. It is `low`, so it goes to the digest under the default policy.
- `commercial:refund:<order ref>` is `high`, with the order and any support case as evidence.
- With no orders, no commercial notification exists. There is never a fabricated "0 sales" alert.

**Actionable**

A test asserts that every notification carries:

- a consequence;
- at least one evidence reference;
- a `/cc/#/...` deep link;
- `delivered: in_app`.

## Still gated, unchanged

External delivery (email, SMS or push) needs the owner gate `casl_notification_authority`: a CASL review plus the owner's authority. Nothing here sends anything outside the app, and the policy's channels stay `["in_app"]`.

## Tests

`tests/test_w4_ccnotify.py` has 5 tests:

| Test | What it covers |
|---|---|
| no-orders | With no orders, no commercial alert is created and routine jobs stay suppressed |
| commercial | Commercial events are aggregated, ranked and deduplicated |
| deadlines | Incident and owner-action deadlines are attached and escalate; out-of-horizon and done actions are excluded; a deadline resolves when its action is done |
| actionable | Every alert is actionable and in-app only |
| view sort | The view sorts by deadline within a severity |

## Results

All runs went through `/home/user/bl-runs/testslot.sh` with N=3, on 2026-10-12.

**New:**

| Test | Passed |
|---|---|
| test_w4_ccnotify | 5/5 |

**Regression:**

| Test | Passed |
|---|---|
| test_w4_ccux | 8/8 |
| test_w4_ccgap_views | 10/10 |
| test_v11_wiring | 0 failing |
| test_w3_priv_leak | OK |
| test_w3_laura_cc_private | 7/7 |
| test_v11_pwa_static | 81/0 |
| test_cert_dashboard | 18/18 |

**Browser:** cc_mock `check.mjs` at 390 px: see below.
- cc_mock `check.mjs` at 390 px (pre-merge, on `083c9fc`): passes=217, failures=0.

## Checkpoint (2026-10-12, controlled pause)

**Status:** DONE in code. The run on the current head is not finished.

**Rows:** F-897 advanced. The in-app criterion is met. The external channel stays owner-gated (`casl_notification_authority`).

**Tests:**

- All results above are from the pre-merge commit on `083c9fc`.
- After INTEG2 `16e36ae` was merged in, the rerun of the new test plus the required regression set was stopped by the pause and has not run on this head.

**Known defects:** none.

**Next step:** run the following through the gate on this head:

1. `test_w4_ccnotify`;
2. the required set: test_vacuity, test_launch, test_cost_governance_wave2, test_search_hero_publish, test_cert_listing_frames, test_v11_autonomy_timeline;
3. the cc_mock check.
