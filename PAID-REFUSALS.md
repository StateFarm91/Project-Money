# eng/paid-refusals: why are paid calls refused? (visibility first)

Production 19h18 (b253437a), 2026-11-22T00:58Z: `paid_call_dedupe` showed 47 DECLINED intents out of 50 in 24 h (3 OK). 15 concepts wait at the pre-engineering gate on `image_vision`, and nothing has been judged.

## Hypotheses checked

- **Sunset: ruled out.** `owner_directives.SUNSET` is GIVEN_AT (2026-11-20T13:20Z) + 30 days, which is 2026-12-20T13:20Z. The evidence's `paid_activations_active` reads `openai-vision:vision: true`. Nothing was re-applied, and no grant or attestation was written.
- **Leaked reservations: possible.** RESERVED rows count against the provider's daily ceiling (`COUNTED`). One left by a dead worker blocks only until UTC midnight. The new `reserved_older_than_1h` field shows it.
- **Missing key: possible.** `concept_judge.choose` cannot build `OpenAIProvider` without the key, and then the route is "none". The new `openai_key_present` field (a boolean, never the value) shows it.
- **The route closing itself: possible.** A failed concept-judge call closes the openai route for 24 h. The new `openai_route_usable` field shows it.

## What this branch adds (no behaviour change)

These fields are added to `factory_visibility.paid_call_dedupe`. They carry counts, fixed codes and provider names only:

- `refusals_by_provider_code`: the gate's `paid_provider.refused` audits by provider and by its fixed code (`provider_daily_ceiling`, `no_budget_reservation`, `reservation_already_used`, `retry_ceiling`, `not_activated_by_owner`, ...).
- `declined_by_provider_class`: DECLINED intents by provider and by error class (`gate_refused`, `budget`, `no_key`, `auth`, `rate_limited`, `timeout`, `other`).
- `activations[provider:scope]`: active, state_code, status, expires_at, directive_sunset_at, daily_ceiling_cad, spent_or_reserved_today_cad, reserved_older_than_1h, calls_in_window_by_status.
- `concept_judge`: the last `creative.regate` time, and whether it found vision usable; judged and held counts; the route now; openai_route_usable; openai_key_present.

## Tests

`tests/test_paid_refusals.py` (3/3) checks that refusals are counted by code, that an active activation shows its state and ceiling, and that no free text appears in the output. The supply, readback and visibility suites also pass; see the commit.

## Next

The integrator releases this. One readback then names the code, and the fix follows the cause. Caps are never raised, and an activation is never renewed unless the evidence shows it expired. The sunset has NOT passed.
