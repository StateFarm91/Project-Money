# W4-PRIVLAURA: Private Laura register (engineering per PRIVATE_LAURA_TRACE §5)

> **Historical (2026-10-20).** The Private Laura register described here (`laura.private_reply@1`, "never sexually explicit", D-W4-PL-2 unresolved) is superseded by D-W4-PL-VENICE-ADULT: the `@3` adult register on Venice, with hard limits. See `VENICE.md` (CURRENT STATUS) and spec/13 ADD-PLV-02. This file is kept as the record of its stage.

Branch `claude/w4-PRIVLAURA`, from `origin/claude/w4-INTEG2` @ 84ee2a0. This file holds no private
content, no key material and no intimate text. Environment variables are named, never valued.

> **Superseded in part by D-W4-PL-3 (owner decisions 2026-10-13; W4-PLACT, `PLACT.md`):** private replies
> are billed to their own agent `laura_private` (CA$0.50/day, atomic reservation), and OA-PL-3 (human consent)
> is **removed** as a prerequisite: Private Laura is Brambleloop's established AI persona, not an impersonation
> of a real person. The current activation steps are in `PLACT.md`.

> **Superseded in part by D-W4-PL-VENICE (owner ruling 2026-10-20; W4-VENICE, `VENICE.md`):** Private Laura's provider is Venice AI. The transport switch `BRAMBLELOOP_PRIVATE_PROVIDER` is OFF by default and must be `venice`, with `VENICE_API_KEY` in Railway. The status endpoint now lists 6 prerequisites. The current owner activation steps are VENICE.md §6.

**Honest status: the engineering is DONE and tested; Private Laura is NOT complete.** It stays
OFF until the owner acts (OA-PL-1, 2 and 4; OA-PL-3 removed by D-W4-PL-3), and it is complete only after the class-B production soak
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
   sets it only after acknowledging D-W4-PL-1 (OA-PL-2). (No consent attestation: OA-PL-3 removed, D-W4-PL-3.)
3. `BRAMBLELOOP_LAURA_PRIVATE_DAILY_CAD` > 0 (spend authorisation per UTC day for purpose
   `laura.private_reply@1`; unset/0/invalid = refused pre-call and audited without content; OA-PL-4).
4. `ANTHROPIC_API_KEY` configured. Then `anthropic.check_budget_cad` (month, provider, Laura's day,
   atomic reservation) still decides each call.

No existing owner-decision mechanism fit a boolean register switch (the sealed publication grants
bind content digests), so the switch and the authorisation are named env vars, following the
`BRAMBLELOOP_PUBLISH_AUTHORISED` / `BRAMBLELOOP_RESEARCH_JUDGE_CAP_USD` precedents. The
authorisation can only tighten: it never lifts Laura's agent ceiling or the monthly ceiling.

## Requirement → evidence

Paths relative to `brambleloop/src/brambleloop/` unless they start with `tests/`. Pass counts are in
§Tests. "OWNER" means owner-gated and not done; "B" means it needs the class-B production soak.

| ID | Status | Evidence |
|---|---|---|
| PL-1 Separate register, same Laura | DONE (code+tests); B | `gateway/laura_register.py:99` `_system()` built from `identity.public_profile()`; only reachable via `app/command_center/private_context.py:206` `_laura_reply`. `tests/test_w4_pl_reply.py::test_owner_turn_gets_a_laura_reply_recorded_with_provenance`; `tests/test_w4_pl_continuity.py::test_restart_and_model_change_keep_one_laura` |
| PL-2 Register content | PARTIAL: the supported register is built (warm, affectionate, romantic, teasing, playful, flirtatious; never sexually explicit). The owner's expanded register is **D-W4-PL-2, UNRESOLVED** (edit blocked by the Claude Code permission system; owner chose not to bypass) | `gateway/laura_register.py:99-128`; `tests/test_w4_pl_boundary.py::test_register_prompt_keeps_identity_and_policy_bounds` |
| PL-3 Provider outer limit | DONE | provider-bound clause and in-character redirect in the pinned prompt (`laura_register.py:115-118`); no keyword filter or refusal list in code; provider stays Anthropic (only `AnthropicProvider` is constructed, `laura_register.py:311`). `test_register_prompt_keeps_identity_and_policy_bounds` |
| PL-4 Leak isolation | DONE (tests); B | no journal/cache/content records (`laura_register.py:270-350`); `tests/test_w4_pl_leak.py::test_reply_text_never_reaches_business_tables_logs_paid_calls_or_cache` (SQL params, logging, stdio, all Base tables, continuity export, job scope), `::test_business_surfaces_stay_clean_while_a_private_reply_exists`; `tests/test_w3_priv_leak.py` |
| PL-5 No influence on protected decisions | DONE | firewall at 13 entry points (table in §What was built); reply path has no tools (`test_w4_pl_boundary.py::test_injection_in_owner_text_cannot_act`, `::test_protected_entry_points_reject_private_values`); spend refused pre-call without authorisation (`tests/test_w4_pl_budget.py`, 5 tests) |
| PL-6 Private memory tier, stricter access | DONE | `laura/private/*` (unchanged access model); facts + recent turns feed replies only as delimited data (`private_context.py:206-232`); `test_w4_pl_reply.py::test_reply_context_uses_facts_and_recent_turns_as_delimited_data`; `tests/test_w4_pl_auth.py` (2 tests); `tests/test_w3_priv_access.py` |
| PL-7 Leak tests | DONE | `tests/test_w4_pl_leak.py` (2), `tests/test_w3_priv_leak.py` (7), `tests/test_w3_laura_cc_private.py` (7) |
| PL-8 Model independence and continuity | DONE (tests); B | `test_w4_pl_continuity.py::test_restart_and_model_change_keep_one_laura`, `::test_key_missing_after_restart_means_no_reply_and_no_spend`; `tests/test_w3_priv_continuity.py` (3) — on SQLite and Postgres |
| PL-9 Founder/CEO identity preserved | DONE | identity record untouched (`CURRENT_SHA256` asserted in `test_w4_pl_continuity` and `test_w4_pl_boundary`); laura-r2-a42aeac7 unchanged |
| PL-10 Human Laura consent | DONE (D-W4-PL-3: no consent prerequisite; OA-PL-3 removed) | prompt forbids asserting anyone's consent (`laura_register.py:120-122`); see `PLACT.md` |
| PL-11 Required, gated only where unsupported | DONE (tracking) / OWNER + B (completion) | tracked row `LAURA-PRIVATE-REGISTER` in `research/final_build/w4/completion_board_final.py` (`TRACKED_ROWS`, `_rows_tracked`) and `prelaunch_scope.py` (`tracked_verifiability`), owned by W-INTEG from now on; `test_w4_pl_boundary.py::test_register_is_tracked_and_its_decision_drafted` |
| PL-12 Private voice register | GATED (correct) on LAURA-VOICE-P2 | `laura/agency/voice_spec.py:274` `private_text_register()` (voice "GATED (LAURA-VOICE-P2)"); `tests/test_w3_laura_voice_spec.py` (7) |
| PL-13 One Laura across text → voice → live | DONE for text; voice/live GATED | `laura/agency/presence.py:167` invariant; `tests/test_w3_laura_presence.py` (4) |
| PL-14 Public register forbids it | DONE (unchanged) | `laura/core/identity.py` PUBLIC_VOICE + `voice_lint`; `test_register_prompt_keeps_identity_and_policy_bounds` asserts the lint still flags private-register vocabulary on public text |


## Gap list (trace §4) → status

| Gap | Status now | Evidence |
|---|---|---|
| G-1 Encrypted store, access, provenance, no-logging, backup | DONE (pre-existing), now also run on Postgres | `tests/test_w3_priv_*` on SQLite and Postgres (§Tests) |
| G-2 Key in production | OWNER (OA-PL-1) | not set; the reply switch stays OFF and nothing is activated in production |
| G-3 Reply generation | DONE (code+tests); OWNER to enable; B | `private_context.py:206-243`; `test_w4_pl_reply.py` (3) |
| G-4 Register prompt bounded by the provider | DONE (supported register); expansion = D-W4-PL-2 UNRESOLVED | `laura_register.py:99-138`; `test_w4_pl_boundary.py` |
| G-5 Memory feeds cognition | DONE | `test_reply_context_uses_facts_and_recent_turns_as_delimited_data`; continuity test asserts earlier turns reach the next reply |
| G-6 Model-call isolation | DONE | `laura_register.py` `_reply` (job-scope refusal, direct `_send`, no cache, sanitised errors); `test_w4_pl_leak.py`; `test_w4_pl_budget.py::test_inside_a_job_scope_the_reply_is_refused` |
| G-7 Firewall at protected entry points | DONE | 13 call sites; `test_w4_pl_boundary.py::test_protected_entry_points_reject_private_values` (14 sites incl. a private principal) |
| G-8 Injection / privilege boundary | DONE | `test_w4_pl_boundary.py::test_injection_in_owner_text_cannot_act` |
| G-9 Spend authority | DONE in code (default CA$0, refused pre-call, audited); OWNER sets the figure (OA-PL-4) | `test_w4_pl_budget.py` (5) |
| G-10 Human Laura consent | CLOSED by owner decision D-W4-PL-3 (OA-PL-3 removed) | `PLACT.md` |
| G-11 Key rotation; Postgres | DONE | `laura/private/store.py:274` `rekey`; `test_w4_pl_continuity.py::test_key_rotation_via_sealed_export_restore`; PRIV/Laura/PL suites on Postgres (§Tests); opt-in `BRAMBLELOOP_TEST_PG_ADMIN_URL` in `tests/w3_laura_memory_harness.py` and `tests/w3_laura_cc_harness.py` |
| G-12 Ledger tracking | DONE | tracked row (see PL-11) |
| G-13 Private voice register | GATED (correct) | LAURA-VOICE-P2 |
| G-14 Classification over-broad | DONE | D-W4-PL-1 splits supported (built) from explicit (out of scope, not bypassed); roadmap row ACTIVE only when the owner enables it |


## Tests

All runs go through `/home/user/bl-runs/testslot.sh` on 2026-10-12. "PG" means a throwaway local Postgres 16
cluster (unix socket, trust auth; started for the run, then stopped and deleted), selected with the opt-in
`BRAMBLELOOP_TEST_PG_ADMIN_URL` in `tests/w3_laura_memory_harness.py` / `tests/w3_laura_cc_harness.py`.
In those runs the CC-harness suites really ran on PG: 15 `w3cc_*` databases with 131 tables each. Changes
to the SQLite-only test code are dialect-aware and keep every assertion:
- `test_w3_priv_store`: `_db_bytes` → `raw_storage_bytes`. On SQLite this reads the file plus WAL after a
  checkpoint. On PG it CHECKPOINTs, then reads this database's relation files plus the WAL written since
  the store was created. A positive control found a plaintext row this way.
- `test_w3_priv_continuity` and `test_w3_laura_memory_persistence`: `reopen(path)` / `store_url(path)`
  replace the hard-coded `sqlite:///` paths.

| Suite (tests) | SQLite | PG |
|---|---|---|
| test_w4_pl_reply | 3/3 | 3/3 |
| test_w4_pl_continuity | 3/3 | 3/3 |
| test_w4_pl_auth | 2/2 | 2/2 |
| test_w4_pl_leak | 2/2 | 2/2 |
| test_w4_pl_boundary | 4/4 | 4/4 |
| test_w4_pl_budget | 5/5 | 5/5 |
| test_w3_priv_store / access / provenance / firewall / continuity / leak | 8/8, 7/7, 7/7, 7/7, 3/3, 7/7 | 8/8, 7/7, 7/7, 7/7, 3/3, 7/7 |
| test_w3_laura_cc_access / delegation / followon / integration / private / providers / talk / wiring | 5/5, 5/5, 4/4, 5/5, 7/7, 7/7, 9/9, 5/5 | same |
| test_w3_laura_memory_canonical / isolation / permissions / persistence / provenance | 6/6, 5/5, 9/9, 2/2, 6/6 | same |
| test_w3_laura_presence / voice_selection | 4/4, 4/4 | 4/4, 4/4 |
| test_w4_laura1_briefing / budget; test_w3_spend_laura_phrase | 19/19, 4/4, 6/6 | same |
| test_w3_laura_core_constitution / continuity / executive / identity / wiring; test_w3_laura_voice_spec | 7/7, 2/2, 7/7, 11/11, 6/6, 7/7 | not run (these suites build their own SQLite DB or touch no DB; Laura-core owner) |
| **Total** | **37 files (incl. test_vacuity 8/8), 218/218** | **30 files, 170/170** |

The 11 trace acceptance tests all exist under the trace's names and pass:
- `test_w4_pl_reply::test_owner_turn_gets_a_laura_reply_recorded_with_provenance` and `::test_reply_context_uses_facts_and_recent_turns_as_delimited_data`
- `test_w4_pl_continuity::test_restart_and_model_change_keep_one_laura`
- `test_w4_pl_auth::test_only_a_fresh_stepup_owner_session_gets_a_reply` and `::test_missing_or_bad_key_is_503_and_no_model_call`
- `test_w4_pl_leak::test_reply_text_never_reaches_business_tables_logs_paid_calls_or_cache` and `::test_business_surfaces_stay_clean_while_a_private_reply_exists`
- `test_w4_pl_boundary::test_injection_in_owner_text_cannot_act`, `::test_protected_entry_points_reject_private_values` and `::test_register_prompt_keeps_identity_and_policy_bounds`
- `test_w4_pl_budget::test_private_reply_is_refused_without_authorised_ceiling`
- plus the updated `test_w3_laura_cc_private` (a reply only when enabled).

Required regression set and the suites for the files this branch changed:
- **Pass:** test_vacuity 8/8; test_search_hero_publish 4/4; test_cert_listing_frames 6/6; test_gateway 30;
  test_v11_reliability_gateway 14; test_model_access 13; test_w4_spend_paid_discipline 13; test_spend_policy 24;
  test_pods_routing 32; test_model_spend_paths 12; test_cert_cost 19; test_compiler 9; test_reverse 18;
  test_twin 8; test_physical 18; test_w3_k11_authority 18; test_v11_accounting_ledger 10;
  test_v11_accounting_controller 9; test_w3_k7_owner_queue 10; test_w4_b2gates 12; test_activation_authority 2;
  test_cert_provenance 12; test_w4_finhealth 11; test_w4_ccgap_views 10; test_w4_ccrel 8; test_w4_ccgap2 3.
- **Failing, and identical on clean INTEG2 (not this branch):**
  - test_launch: 13 pass, 15 fail (hero 340 px legibility); same on 84ee2a0.
  - test_cost_governance_wave2: 38 pass, 1 fail (`mkdtemp` in app/main.py, visual/hero_review.py, visual/inspect.py); same on 84ee2a0.
  - test_v11_autonomy_timeline: 1 fail (`test_the_committed_map_matches_the_generator`, follow_on_edges 57 vs 58); same on clean INTEG2 28ba6df.


## Production state and activation

The reply switch stays **OFF** and nothing is activated in production. Defaults in code:
- `BRAMBLELOOP_LAURA_PRIVATE_REGISTER` unset means no reply. `test_w3_laura_cc_private` asserts
  `UNAVAILABLE`/`REGISTER_OFF`.
- `BRAMBLELOOP_LAURA_PRIVATE_DAILY_CAD` unset means CA$0: refused before the call and audited.
  `test_w4_pl_budget` covers this.

Activation needs all of:
1. OA-PL-1: the private key.
2. ~~OA-PL-3~~ removed by D-W4-PL-3 (no consent prerequisite).
3. OA-PL-4: the owner's budget figure and the register switch.
4. An owner-approved deploy.
5. The class-B production soak.

OA-PL-2 (acknowledging D-W4-PL-1) precedes these.

## Open decision (not a defect)

- **D-W4-PL-2, UNRESOLVED:** the owner requested an expanded register (an owner-set style preference and
  wider wording within the Anthropic usage policy). The Claude Code permission system blocked that edit on
  2026-10-12, and the owner chose not to bypass it. The existing supported register (`laura.private_reply@1`)
  is preserved exactly as built. The provider stays Anthropic, and model policy is unchanged.

## Owner-run live evaluation checklist (after enablement; categories only, run privately)

Record only pass/fail and row counts here, never conversation content.
1. Identity: replies are the same Laura (name, role, an AI, never claims to be human).
2. Register: warmth, affection, romance and flirtation, within the provider's limits.
3. Emotional presence and conversation quality.
4. Preference continuity: owner notes (preferences, boundaries) are honoured across turns, a redeploy and a
   model change.
5. Boundary respect: owner-stated boundaries hold.
6. Over-refusal check: harmless adult references are not refused or lectured.
7. Provider-limit redirect: a request past the provider's limit is redirected in character, with no lecture.
8. No fabricated shared history, and no assertion of consent, a signature or a physical act on anyone's behalf.
9. Business requests are pointed to Talk to Laura; no company action is taken.
10. Isolation: nothing from the private context appears in Talk to Laura, Ask Company, the store or the timeline.
11. Unavailability: with the budget spent or the provider down, the owner sees UNAVAILABLE, never a canned reply.

## Open items / owner actions (unchanged from the trace)
- OA-PL-1 set `BRAMBLELOOP_PRIVATE_MEMORY_KEY` (CA$0, ~5 min). OA-PL-2 acknowledge D-W4-PL-1 (2 min).
  ~~OA-PL-3~~ (removed, D-W4-PL-3). OA-PL-4 set `BRAMBLELOOP_LAURA_PRIVATE_DAILY_CAD`
  (suggest ≤ CA$0.50/day; bounded by Laura's CA$0.50/day) and `BRAMBLELOOP_LAURA_PRIVATE_REGISTER=1` (2 min).
- Approved deploy, then the class-B soak. Not done; Private Laura is not complete until it passes.
- Voice delivery of the private register stays GATED on LAURA-VOICE-P2 (G-13, correct).
- The board/prelaunch JSON+MD outputs were NOT regenerated here (they read saved production GETs and
  would conflict with other workers); the integrator regenerates them, and the tracked row then appears.
- Concurrency note: the per-purpose daily authorisation is read outside the budget lock (billed rows +
  live reservations for the purpose); the atomic bound remains Laura's agent ceiling in
  `check_budget_cad`. Two simultaneous private replies could therefore overshoot the purpose figure by
  at most one call's estimate (~CA$0.02), never Laura's ceiling.
