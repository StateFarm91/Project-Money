# W4-SMOKE: production smoke matrix (F-171) and per-feature readback gate (F-144)

Branch `claude/w4-SMOKE`, based on `origin/claude/w4-INTEG2` 85ec5d0. Nothing was deployed and
nothing was written to production; the only production contact was read-only GETs.

## What is new

- **`src/brambleloop/ops/smoke.py`**: the F-171 smoke matrix. Each check is read from rows the
  runtime wrote and is PASS, FAIL or UNKNOWN. UNKNOWN is never shown as a pass. The checks:
  - **Probes ran:** `model.probe`, `vision.probe` and `etsy.probe`, each within twice its
    cadence period. A probe that ran but was refused by its provider (Etsy 403) still counts as
    "ran"; the refusal is carried in the evidence.
  - **Continuity:** a restore proof within two periods, and no failed proof newer than it.
  - **Cadence coverage:** `ops.slo.cadence_freshness` against its own F-924 target of 0.95.
  - **Queue round-trip:** at least one job completed in the last hour, and no due job has waited
    more than an hour.
  - **Search intelligence:** `intel.serp_capture` completed within two periods.

  Served two ways:
  - `GET /api/verify/smoke`: 200 only on PASS, otherwise 503. It is public and read-only, and is
    noted in `security.PUBLIC_GET_NOTES`.
  - A `readbacks.smoke_matrix` block inside `/api/verify`. It does not change `/api/verify`'s
    own verdict.
- **`ops/readback.py`**: the F-144 per-feature readback manifest. There are 12 launch-critical
  features, each with an endpoint, a field, an expected value and the rows it evidences
  (F-144, F-169, F-158, F-171, F-172, F-371, F-840, F-878, F-880). A route that answers 401
  proves it exists and is gated. Exit codes:

  | exit | meaning |
  |---|---|
  | 0 | every feature PASS |
  | 5 | any FAIL or UNKNOWN |
  | 4 | production unreachable |

- **`ops/deploy.sh`**: after `verify_deploy.py` reports DEPLOYED, it runs the readback and exits
  5 if any feature fails, naming the features that are not done. `READBACK=0` skips it and says
  so. A checkout without `ops/readback.py` says it was not read back.

## Acceptance evidence (tests run through /home/user/bl-runs/testslot.sh)

| test | result |
|---|---|
| `tests/test_w4_smoke.py` (new) | 10/10. Covers: a fresh DB reads UNKNOWN; a healthy DB passes and a refused probe still "ran"; a stale probe, a failed restore, stale cadences and a stalled queue each FAIL; the readback PASS/FAIL/UNKNOWN cases; `deploy.sh` end to end against a loopback server (exit 0 on PASS, exit 5 when the smoke matrix fails); the route is public, read-only and never 200 unless PASS |
| `tests/test_deploy_verify.py` | 10/10 (the existing `deploy.sh` contract is unchanged) |
| `tests/test_route_auth_default_deny.py` | 7/7 |
| `tests/test_customer_data_auth.py` | 9/9 |
| `tests/test_vacuity.py` | 8/8 |
| `tests/test_deploy.py` | 2 of its tests run directly: `test_verify_endpoint_reports_the_standing_safety_assertions` OK and `test_every_get_endpoint_answers_rather_than_500ing` OK |

## Readback of production as it runs now (0417f35)

Read-only, saved in `evidence_SMOKE/readback_prod_*.json`. The readback reports FAIL (exit 5)
on three features:

- **no unexpected dead letters:** the fixes are on INTEG2 (843af70, 4b55f22) and not yet
  deployed.
- **every agent has a cost ceiling:** the W4-FINHEALTH `ceiling_audit` is on INTEG2 and not yet
  deployed.
- **smoke matrix:** UNKNOWN, because the route is not deployed yet.

The other 9 features PASS.

## Board rows

- **F-171:** advanced. The smoke matrix now exercises queues end to end, provider probes,
  continuity, cadences and search intelligence. It closes when a release carrying this branch
  is deployed and `ops/readback.py` reads PASS on it.
- **F-144:** advanced. The per-feature readback rule is now code, and the deploy path refuses to
  call a deploy done without it. It closes on the same deployed readback.

Neither row is marked complete here: each needs its production readback, which needs a deploy.
