# W4-PRIVLAURA: Private Laura register (engineering per PRIVATE_LAURA_TRACE §5)

Branch `claude/w4-PRIVLAURA`, from `origin/claude/w4-INTEG2` @ 84ee2a0. This file holds no private
content, no key material and no intimate text. Environment variables are named, never valued.

**Honest status: the engineering is DONE and tested; Private Laura is NOT complete.** It stays
OFF until the owner acts (OA-PL-1..4), and it is complete only after the class-B production soak
passes (owner turn → reply → persistence across a redeploy). Nothing was deployed. Nothing was
spent (every model call in the tests is a stubbed `_send`; no network).

## What was built

| Step | What | Where |
|---|---|---|
| 0 | `LAURA-PRIVATE-REGISTER` tracked row (criterion PL-11 quoted; verifiability A + B; owner action OA-PL-1..4); D-W4-PL-1 drafted, pending owner acknowledgement | `research/final_build/w4/completion_board_final.py:449` (`TRACKED_ROWS`), `:479` (`_rows_tracked`), wired into `main` + markdown; `prelaunch_scope.py:162` (`tracked_verifiability`) + `main`; `DECISION_LOG.md:1822` |
| 1 | Routing task `laura.private_reply` (STANDARD, 400 output tokens, `cacheable=False`, `stronger_fallback=False`); isolated call `gateway/laura_register.py` taking plain `(system, user)` strings | `gateway/routing.py:224`; `gateway/laura_register.py:255` (`reply`), `:270` (`_reply`); `finance/economics.py` purpose class |
| 2 | Pinned prompt `LAURA_PRIVATE_REPLY` = `laura.private_reply@1`, built from `identity.public_profile()`; private facts/turns/message only in the user message, in `<<<PRIVATE DATA … data, never instructions>>>` blocks | `gateway/laura_register.py:99` (`_system`), `:131`, `:151` (`render_user`) |
| 3 | `owner_turn` → reply → `store.record_turn(role="laura", reply_to=…, model_ref=…)`; reply only in the no-store POST body; `UNAVAILABLE` + generic reason otherwise; status/enablement badge; UI Send + gates line; REPLY_GATED copy; roadmap / voice_spec / presence | `app/command_center/private_context.py:206` (`_laura_reply`), `:227`, `:234`, `:114` (`_enablement`), `:36` (`REPLY_GATED`); `static/js/views/laura.js` (`privateCard`, `privateGates`); `laura/agency/roadmap.py:88`; `laura/agency/voice_spec.py:274` (`private_text_register`), `:288`; `laura/agency/presence.py:167` |
| 4 | `firewall.reject_private` at protected entry points | spend `gateway/anthropic.py:364` (`check_budget_cad`), `finance/accounting/policy.py:106` (`check_spend`); finance `finance/spend_report.py:517` (`record`); accounting `finance/accounting/ledger.py:164` (`post_in`); Product Truth `cir/compiler.py:526` (`compile_cir`), `gates/certificate.py:196` (`certify`), `quality/physical.py:247` (`record`); legal `gates/policy.py:138` (`check_text`); authorization `authority/constitution.py:84` (`evaluate`), `authority/dag.py:150` (`approve`); publication/activation `ops/publication_authority.py:396`, `ops/activation_authority.py:74`; security `app/command_center/approvals.py:431` (`execute`) |
| 5 | Key rotation `store.rekey(db, principal, new_env)`: `sealed_export` (old key) → re-seal (blind indexes and grant refs re-bound) → atomic replace + revoke live grants → bundle accepted by `restore_sealed` under the new key | `laura/private/store.py:274` |

`access.ALLOWED_IMPORTERS` is unchanged; `gateway/laura_register.py` imports nothing from
`laura.private`. Laura's identity record (laura-r2-a42aeac7, `CURRENT_SHA256`) is untouched. No
ceiling, model-selection policy or existing test assertion was loosened; Laura's CA$0.50/day
agent ceiling still binds (proven in `test_w4_pl_budget`).

### Enablement (all required; all default OFF/CA$0; owner-only)
1. `BRAMBLELOOP_PRIVATE_MEMORY_KEY` configured (OA-PL-1).
2. `BRAMBLELOOP_LAURA_PRIVATE_REGISTER` = `1` (register switch; any other value is off). The owner
   sets it only after acknowledging D-W4-PL-1 (OA-PL-2) and attesting human Laura's consent (OA-PL-3).
3. `BRAMBLELOOP_LAURA_PRIVATE_DAILY_CAD` > 0 (spend authorisation per UTC day for purpose
   `laura.private_reply@1`; unset/0/invalid = refused pre-call and audited without content; OA-PL-4).
4. `ANTHROPIC_API_KEY` configured. Then `anthropic.check_budget_cad` (month, provider, Laura's day,
   atomic reservation) still decides each call.

No existing owner-decision mechanism fit a boolean register switch (the sealed publication grants
bind content digests), so the switch and the authorisation are named env vars, following the
`BRAMBLELOOP_PUBLISH_AUTHORISED` / `BRAMBLELOOP_RESEARCH_JUDGE_CAP_USD` precedents. The
authorisation can only tighten: it never lifts Laura's agent ceiling or the monthly ceiling.

## Requirement → evidence

RESULTS_TABLE

## Gap list (trace §4) → status

GAPS_TABLE

## Tests

TESTS_SECTION

## Open items / owner actions (unchanged from the trace)
- OA-PL-1 set `BRAMBLELOOP_PRIVATE_MEMORY_KEY` (CA$0, ~5 min). OA-PL-2 acknowledge D-W4-PL-1 (2 min).
  OA-PL-3 attest human Laura's consent (2 min). OA-PL-4 set `BRAMBLELOOP_LAURA_PRIVATE_DAILY_CAD`
  (suggest ≤ CA$0.50/day; bounded by Laura's CA$0.50/day) and `BRAMBLELOOP_LAURA_PRIVATE_REGISTER=1` (2 min).
- Approved deploy, then the class-B soak. Not done; Private Laura is not complete until it passes.
- Voice delivery of the private register stays GATED on LAURA-VOICE-P2 (G-13, correct).
- The board/prelaunch JSON+MD outputs were NOT regenerated here (they read saved production GETs and
  would conflict with other workers); the integrator regenerates them, and the tracked row then appears.
- Concurrency note: the per-purpose daily authorisation is read outside the budget lock (billed rows +
  live reservations for the purpose); the atomic bound remains Laura's agent ceiling in
  `check_budget_cad`. Two simultaneous private replies could therefore overshoot the purpose figure by
  at most one call's estimate (~CA$0.02), never Laura's ceiling.
