# W4-PLACT: Private Laura activation decisions (owner, 2026-10-13)

Branch `claude/w4-PLACT`, from `origin/claude/w4-INTEG2` @ 9c3812b. Implements the owner's binding
2026-10-13 decisions, recorded as **D-W4-PL-3** (`DECISION_LOG.md:1920`). This file holds no
private content and no key material. Environment variables are named, never valued.

**Honest status.** The code and tests are done on this branch. Nothing was deployed, and no
production variable was changed. Nothing was spent: every model call in the tests is a stubbed
`_send`. Production (1b21e81) still runs the earlier PRIVLAURA code, which bills `laura` and has
no `laura_private` agent and no prerequisite list. Private Laura stays **OFF** by default. It is
**not complete** until the owner steps below are done and the class-B soak passes.

## The three decisions

### 1. Separate budget

| What | Where |
|---|---|
| New agent `laura_private`: CA$0.50/day, no job types, GREEN, forbidden everything Laura is; DECLARED_IO `exempt`; quality-exempt | `src/brambleloop/agents/registry.py:806-823` |
| Business Laura (`laura`) is still CA$0.50/day. The monthly ceiling is still CA$100 (`_policy_ceiling`). No other limit changed | `registry.py` (`laura` row unchanged); `tests/test_w4_plact.py::test_laura_private_is_its_own_agent_with_its_own_ceiling` |
| Private replies are billed to `laura_private` | `src/brambleloop/gateway/laura_register.py:63` (`AGENT`) |
| **Atomic pre-call reservation (fixes security-review L1).** `check_budget_cad(..., agent_daily_cap_cad=)` checks the day against min(agent ceiling, owner figure) inside `budget_lock`, in the same step as the reservation. The old `_purpose_committed_today` read, which ran outside the lock, is deleted. The cap can only tighten. A NaN, negative or garbage cap reads as CA$0. If a cap is given, an unregistered agent is refused | `src/brambleloop/gateway/anthropic.py:337`, `:356` (doc), `:420`, `:478`, `:576-599`; caller `laura_register.py:300-311` |
| `BRAMBLELOOP_LAURA_PRIVATE_DAILY_CAD` is still the owner switch, capped at the agent ceiling (CA$5 reads as CA$0.50) | `laura_register.py:171` (`agent_ceiling_cad`), `:179` (`daily_authorisation_cad`) |

### 2. Identity / consent

- **OA-PL-3 is removed as a prerequisite** from all of these:
  - roadmap status copy: `src/brambleloop/laura/agency/roadmap.py` row `LAURA-PRIVATE-REGISTER`;
  - board generator and its committed outputs: `research/final_build/w4/completion_board_final.py`
    (`IMPROVEMENT_DOMAIN["laura_private_register"]`, `TRACKED_ROWS` gate_detail and owner_action,
    now `OA-PL-1/2/4`), `COMPLETION_BOARD_FINAL.json/.md` and `PRELAUNCH_SCOPE.json`, patched to
    match the generator's text and truncation exactly;
  - docs: `PRIVLAURA.md` and `PRIVATE_LAURA_TRACE.md`, which carry superseded banners, with OA-PL-3
    struck;
  - UI: the private card lists prerequisites with no consent item (`laura.js` `privatePrereqs`).
- **D-W4-PL-3** is appended to `DECISION_LOG.md:1920`. It quotes the owner's clarification: "Private
  Laura is Brambleloop's established AI persona, not an impersonation of a real person."
  DECISION_LOG is append-only, so D-W4-PL-1 is left as written and D-W4-PL-3 supersedes its
  consent clause.
- **Truthful AI representation is kept.** The pinned prompt `laura.private_reply@1` is unchanged. It
  still says "You are an AI. Never claim or imply that you are human", "never claim a body, a physical
  action or a place", and "Never state or imply consent, a signature, an identity verification or a
  physical act on behalf of…" (`laura_register.py:113-127`).
- **The register wording is not changed**, and D-W4-PL-2 stays UNRESOLVED.
- Not edited:
  - `spec/07`: canonical owner text.
  - `INTEG3.md`: the integrator's record.
  - `presence.py:118`: about voice *cloning* of a real person, which is a different matter.

### 3. Status

`GET /api/cc/private/status` is owner-only (anonymous gets 401/403). It now returns `prerequisites`,
an ordered list of `{id, met, label}`, plus `prerequisites_met`. Labels name the variables and never
their values. They show a short commit SHA at most.
(`src/brambleloop/app/command_center/private_context.py:115` `_agent_present`, `:130` `_release_deployed`,
`:158` `prerequisites`, `:228-229`)

| id | met when |
|---|---|
| `key_configured` | `store.configured()`: `BRAMBLELOOP_PRIVATE_MEMORY_KEY` is present and valid |
| `register_switch` | `BRAMBLELOOP_LAURA_PRIVATE_REGISTER` is exactly `1` |
| `daily_cad_set` | `BRAMBLELOOP_LAURA_PRIVATE_DAILY_CAD` > 0, after capping at CA$0.50 |
| `laura_private_agent` | the registry row exists in this database with a positive, finite ceiling |
| `current_release_deployed` | build commit known AND running on the hosting platform AND the runtime boot guard (`ops.release_record.BOOT`) found a committed, release-eligible record for this exact tree. An unproven or unknown build is unmet, never assumed |

`enablement.enabled` (whether a reply may be attempted) now also requires `laura_private_agent`.

## PL-1..PL-14 → evidence

Paths are relative to `brambleloop/`. "B" means the class-B production soak is still needed.

| ID | Status | Evidence |
|---|---|---|
| PL-1 Separate register, same Laura | DONE (code+tests); B | unchanged `laura_register.py:99` `_system()` from `identity.public_profile()`; `tests/test_w4_pl_reply.py::test_owner_turn_gets_a_laura_reply_recorded_with_provenance` (now asserts billing to `laura_private`) |
| PL-2 Register content | PARTIAL, unchanged: supported register built; **D-W4-PL-2 UNRESOLVED** (wording not touched) | `laura_register.py:99-128`; `tests/test_w4_pl_boundary.py::test_register_prompt_keeps_identity_and_policy_bounds` |
| PL-3 Provider outer limit | DONE (unchanged) | `laura_register.py:115-118`; same test |
| PL-4 Leak isolation | DONE; B | `tests/test_w4_pl_leak.py` (2). The export check now looks for private *tables* (`laura_private_*`), because the billing agent name `laura_private` is a content-free business row by design; `tests/test_w3_priv_leak.py` (7) |
| PL-5 No influence on protected decisions | DONE, strengthened: the private budget is its own agent and is reserved atomically | `tests/test_w4_plact.py::test_private_spend_never_consumes_the_briefing_budget_and_vice_versa`, `::test_two_concurrent_private_turns_cannot_both_pass_the_cap`, `::test_the_monthly_ceiling_binds_both`, `::test_agent_daily_cap_only_tightens_and_fails_closed`; `tests/test_w4_pl_budget.py` (5); firewall tests in `test_w4_pl_boundary.py` |
| PL-6 Private memory tier | DONE (unchanged) | `tests/test_w4_pl_reply.py::test_reply_context_uses_facts_and_recent_turns_as_delimited_data`; `tests/test_w4_pl_auth.py`; `tests/test_w3_priv_access.py` |
| PL-7 Leak tests | DONE | `test_w4_pl_leak` (2), `test_w3_priv_leak` (7), `test_w3_laura_cc_private` (7) |
| PL-8 Model independence / continuity | DONE; B | `tests/test_w4_pl_continuity.py` (3); `tests/test_w3_priv_continuity.py` (3) |
| PL-9 Founder/CEO identity preserved | DONE (unchanged) | identity record untouched; `CURRENT_SHA256` asserted in `test_w4_pl_continuity`/`test_w4_pl_boundary` |
| PL-10 Human consent / authority distinction | **DONE by owner decision D-W4-PL-3**: no consent prerequisite (OA-PL-3 removed). The authority distinction is kept: she never claims to be human and never asserts consent, signatures or physical acts | `DECISION_LOG.md:1920`; `laura_register.py:113-127`; `tests/test_w4_plact.py::test_no_consent_prerequisite_and_truthful_ai_representation_kept` |
| PL-11 Required, gated only where unsupported | DONE (tracking) / OWNER + B (completion) | tracked row `LAURA-PRIVATE-REGISTER`, owner action now `OA-PL-1/2/4`; `tests/test_w4_pl_boundary.py::test_register_is_tracked_and_its_decision_drafted` |
| PL-12 Private voice register | GATED (correct) on LAURA-VOICE-P2 | `laura/agency/voice_spec.py:274`; `tests/test_w3_laura_voice_spec.py` (7) |
| PL-13 One Laura across text → voice → live | DONE for text; voice/live GATED | `laura/agency/presence.py:167`; `tests/test_w3_laura_presence.py` (4) |
| PL-14 Public register forbids it | DONE (unchanged) | `laura/core/identity.py` PUBLIC_VOICE + `voice_lint`; `test_register_prompt_keeps_identity_and_policy_bounds` |

Security-review **L1** (purpose cap read, then reserved separately) is **CLOSED**. The evidence is
`anthropic.py:576-599` and `test_two_concurrent_private_turns_cannot_both_pass_the_cap`. That test
releases two private turns together and holds the first model call open, then checks three cases:
(a) the owner's figure fits one call but not two, so exactly one provider call and one
`purpose_daily_authorisation` refusal; (b) the agent ceiling's remaining room fits one call but
not two, so exactly one call and one `agent_daily_ceiling` refusal; (c) a positive control with room
for both, where both reply.

## Tests

All runs go through `/home/user/bl-runs/testslot.sh` on 2026-10-19, on SQLite. The table is filled
from the run logs.

TESTS_TABLE_PLACEHOLDER

## Exact owner activation steps

Do these in order. Each one says what it costs and how long it takes. Steps 2–4 are Railway
variable changes on the **production web service**. Railway redeploys the same build when a
variable changes, so the soak in step 6 covers that.

| # | Exact action | Why | Max cost | Minutes | If you wait |
|---|---|---|---|---|---|
| 1 | Approve the release that contains W4-PLACT. The integrator merges `claude/w4-PLACT` into INTEG2, cuts the candidate (full suite plus security review), and you approve the deploy as usual. | Production 1b21e81 bills private replies to `laura` and has no `laura_private` agent or prerequisite list. | CA$0 | 2 (your approval) | Status in production cannot show the prerequisites. Do not enable before this deploy. |
| 2 | Acknowledge D-W4-PL-1 (OA-PL-2). Reply "D-W4-PL-1 acknowledged"; the integrator records it. | It is the scope decision for the supported register. It does not touch the register wording or D-W4-PL-2. | CA$0 | 2 | The register stays off by policy. |
| 3 | In Railway, production web service → Variables, add `BRAMBLELOOP_PRIVATE_MEMORY_KEY`. Its value is 32 random bytes, base64-encoded; generate it on your own machine with `python3 -c "import secrets,base64;print(base64.b64encode(secrets.token_bytes(32)).decode())"`. Keep an offline copy. (OA-PL-1) | The private store refuses everything without it. If the key is lost, the private store is lost, by design. | CA$0 | 5 | Every private operation returns 503. |
| 4 | In the same place, add `BRAMBLELOOP_LAURA_PRIVATE_DAILY_CAD` = `0.50` (or less) and `BRAMBLELOOP_LAURA_PRIVATE_REGISTER` = `1`. (OA-PL-4) | This authorises spend for `laura_private` and turns replies on. A figure above 0.50 is capped at 0.50. | **CA$0.50/day** at most (inside the CA$100 month) | 2 | Replies are refused before the call, with an audited reason. |
| 5 | Open the Command Center → Laura → private card. Check "Activation prerequisites: 5 of 5 met". If one is not met, its line names it. | This confirms each prerequisite without exposing any value. | CA$0 | 1 | — |
| 6 | Class-B soak: open the private context (step-up), send one message, and see Laura's reply. Then trigger a redeploy or restart and check that both turns are still there. Record only the status codes and row counts, never the content. | Completion criterion (PL-11, verifiability B). | ≤ one reply (~CA$0.02) | 5 | Private Laura stays tracked-open, not complete. |

ANTHROPIC_API_KEY is already a production variable. No other owner action is needed. **Human
consent is not a step** (D-W4-PL-3).

## Not done / open

- Nothing was deployed, and no production setting was touched (worker rules).
- The board and prelaunch outputs were patched as text to match the edited generator. They were not
  regenerated, because regeneration reads saved production GETs. The integrator may regenerate them.
- D-W4-PL-2 (expanded register) stays UNRESOLVED.
- The class-B soak is pending the owner steps above.
