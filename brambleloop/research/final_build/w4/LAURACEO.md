# W4-LAURACEO: Business Laura as a model-backed AI CEO

Ruling: D-W4-LAURA-CEO. Requirements: ADD-LCEO-01..07 (`spec/13_Laura_CEO_Autonomy_and_Private_Laura_Venice_2026-10-20.md`). Also D-FB-13 and spec/07 (CEO role).
Branch: `claude/w4-LAURACEO`, from `origin/claude/w4-INTEG4` (65317697) with `origin/claude/w4-BRANDRULE` (eac52bb) merged in.
Production: b931d17, SHADOW. Not deployed. No production writes, no paid calls, no new provider or credential.
Private Laura is out of scope here (W-VENICE). Nothing in this branch reads or writes the private store or the reply path.

---

## §1 Inspection: what existed, why greetings fail, what was missing

### 1.1 CEO autonomy that already existed (at 65317697; same code as production b931d17)

| Capability | Where | Notes |
|---|---|---|
| Laura agent, GREEN, CA$0.50/day model permission | `agents/registry.py` DEFAULT_AGENTS `laura` (owner decision D-W4-LAURA1-BUDGET); forbidden protected job types (`FORBIDDEN_COMBINATIONS["laura"]`) | Inside the CA$100 month. |
| Executive tick every 5 min | `runtime/worker.py` CADENCES `laura_executive`; `laura/executive/handlers.py:handle_executive_tick` | Deterministic. |
| Observe company state | `laura/executive/loop.py:observe` | Departments, KPIs, owner actions, incidents, dead letters, providers. |
| Prioritise | `loop.py:prioritise`, `_idle_priorities` | Durable `laura_priorities` with score, reason and evidence. |
| Delegate through the real queue | `loop.py:_delegate` → `autonomy.orchestrator._enqueue_mission` (JobQueue) | Delegation passes `laura/core/constitution.py:review` first, then the COO's SAFE_GENERATED/charter boundary. |
| Review results | `loop.py:_review` | Uses the useful-work judge via `orchestrator.reconcile_missions`. |
| Challenge, rework once, then escalate | `loop.py:_review`, `_escalate` | Escalation is a routed Lesson, so it cannot loop. |
| Protected work becomes an owner action | `loop.py:_delegate` → `orchestrator._raise_approval` | Never a job. |
| Decision history | `laura/core/history.py:record` | Writes to the company timeline and laura.memory (operational tier). |
| Business conversation | `laura/agency/talk.py:converse` | Keyword intent → evidence readers → **fixed templates**. Optional phrasing only reworded a template, was off by default, and was skipped on UNKNOWN. |
| CEO briefing | `laura/agency/briefing.py:answer` + `gateway/laura_briefing.py:synthesize` | The model only selects and orders evidence ids. Code renders every line. |
| Conversational delegation | `laura/agency/delegation.py:parse/plan` → `followon.create` | Needs owner confirmation. Protected work needs step-up and becomes an owner action. |
| Ask Company | `app/command_center/ask.py:ask` | Deterministic keyword intents. Falls back to UNKNOWN. |
| Memory tiers and provenance | `laura/memory/store.py`, `tiers.py`, `provenance.py` | Laura can write the relationship tier `context/*`. Every source must resolve to a real row. |

### 1.2 Root cause: why the live CC answers greetings with Ask-Company templates or UNKNOWN

The route is `POST /api/cc/laura/ask` (`app/command_center/api.py:laura_ask`) → `talk.converse` (`talk.py:363`).

1. `talk.classify` (`talk.py:66`) runs three checks in order: `delegation.parse`, then `briefing.parse`, then the keyword `_RULES`. "Hello", "Hi Laura", "Thanks!" and "How are you?" match nothing, so they return `fallback`.
2. A `fallback` result (`talk.py:411`) calls `app.command_center.ask.ask` (`ask.py:322`). Its own `classify` (`ask.py:54`) returns `("unknown", None)`, which produces `ask.py:339`: **"UNKNOWN: this question is not one the company can answer from recorded evidence yet. Supported: …"**
3. "Good morning Laura, how are you today?" matches the keyword `today` in the `overnight` rule. It returns the **overnight-jobs template** ("Here is what my company did, straight from the records. …").
4. No model is ever called for conversation. `METHOD = "deterministic retrieval over durable state + fixed templates (no model call)"`. `phrasing.phrase` runs only when `BRAMBLELOOP_LAURA_PHRASING=1`, only rewords, and is skipped when the status is UNKNOWN.

I reproduced this with `talk.classify` / `ask.classify` on this branch. `git diff b931d17 HEAD` is empty for `talk.py`, `ask.py`, `phrasing.py` and `views/laura.js`, so production behaves the same way.

### 1.3 What was missing, per requirement

| Row | Already existed | Missing (now built here) |
|---|---|---|
| ADD-LCEO-01 conversation | Templates, identity answer, delegation parser | A real model call on Laura's budget. Cheap model for chat, stronger model for executive reasoning. An honest message when the model is unavailable. Templates used only as evidence. |
| ADD-LCEO-02 grounding | Evidence readers, Ask Company | Readers wired as **tools** for the model, with citation ids. Deterministic validation of citations and figures. |
| ADD-LCEO-03 memory | laura.memory tiers, `laura_cc_turns` | Session history fed back to the model. Owner-stated business context written to a scoped tier (relationship `context/conversation/*`) and read back on later turns. |
| ADD-LCEO-04 executive | The full deterministic tick | Model ordering of authorised priorities (bounded). Corrections that carry **feedback** (criteria, verdict, attempt). An owner report that includes costs. |
| ADD-LCEO-05 routing | Anthropic tiers, failover, ceilings | Declared tasks `laura.converse` (cheap), `laura.executive` (standard), `laura.exec_rank` (standard), each with its own allocation stop. |
| ADD-LCEO-06 cost tracking | Ledger by agent and purpose | Attribution per conversation, decision, delegated task and successful outcome (`laura_cost_events`, `costs.summary`, `GET /api/cc/laura/costs`). |
| ADD-LCEO-07 production test | — | Offline proof of all nine steps (§4). The production runbook is §5. **The production run has not happened.** |

---

## §2 Model routing research (sources fetched 2026-10-20, UTC)

### 2.1 Anthropic: what is configured, and current official prices

Source: https://platform.claude.com/docs/en/about-claude/pricing (fetched 2026-10-20). All prices USD per million tokens, input/output.

| Model | Official input/output | Repo billing table (`gateway/anthropic.py:PRICES_USD_PER_MTOK`) | Used for |
|---|---|---|---|
| claude-haiku-4-5 | 1 / 5 | 1 / 5 (matches) | CHEAP tier: `laura.converse` |
| claude-sonnet-5 | 2 / 10 | **3 / 15** (overstates by 50%) | STANDARD tier: `laura.executive`, `laura.exec_rank`, `laura.ceo_briefing` |
| claude-opus-5 | 5 / 25 | **15 / 75** (overstates by 3×) | DEEP tier (not used by Laura) |
| claude-haiku-5-5 | 0.10 / 0.50 (prompts ≤100K tokens) | not priced, so cannot be routed | Candidate for a future cheaper chat route |
| claude-sonnet-5-5 | 2 / 10 | not priced | Candidate |
| claude-opus-5-5 | 4 / 20 | not priced | — |

Finding: the repo's prices for Sonnet 5 and Opus 5 are higher than the official ones. That direction is safe: estimates, reservations and ledger rows overstate spend, so no ceiling can be crossed by mis-pricing. But every standard- or deep-tier figure in the ledger is about 1.5–3× the real bill. I did **not** change this here, because the billing table is shared by every agent and the ledger history was written at these rates. Recommendation for the integrator or finance owner: correct it with a dated price-basis note and a reconciliation against the Anthropic console.

Cheaper route for later: Haiku 5.5 is about 10× cheaper than Haiku 4.5. It is the same provider and the same credential, so it needs no new-provider approval. It is still a routing change, so it needs a price row plus F-313 eval evidence (`routing.record_route_evidence` / `override_route`). It is not activated here.

### 2.2 OpenAI

- Prices (https://developers.openai.com/api/docs/pricing, fetched 2026-10-20; standard tier, ≤272K input, USD/M input / output): gpt-5.4 2.50/15; gpt-5.4-mini 0.75/4.50; gpt-5.4-nano 0.20/1.25; gpt-5-mini 0.25/2.00; gpt-5-nano 0.05/0.40; gpt-6-luna 0.10/0.50; gpt-6.1-sol 2.00/10.00; gpt-6-astra 10/50.
- Data (https://developers.openai.com/api/docs/guides/your-data, fetched 2026-10-20): API data is not used for training by default. Abuse-monitoring logs are kept up to 30 days by default. Zero Data Retention is available only to eligible customers after OpenAI approval. Some endpoints, including Files, Batches and Assistants, store state even with ZDR.
- `BRAMBLELOOP_IMAGE_KEY_OPENAI` is read by `gateway/images.py:key_var("openai")` as the **image-provider** credential (images endpoint). The text gateway looks for `OPENAI_API_KEY` (`gateway/model_gateway.py:available_providers`). The repo has **no OpenAI text provider class** for `ModelGateway`; the only text use of OpenAI is `visual/d_judge.py`, a separate judge.
- Whether the key works for text is UNKNOWN. A standard OpenAI project key usually authorises both endpoints, but restricted or project-scoped keys may not, and I cannot see the value or its permissions. Using it for business text would put an existing credential to a new paid purpose. Under ADD-LCEO-05 and D-W4-LAURA-CEO that needs owner approval, plus a provider adapter, a price table and a data-terms review. **Not usable now.**

### 2.3 Venice

Private Laura's provider (D-W4-PL-VENICE; W-VENICE owns it). It is not part of business routing. The ruling keeps Business Laura on the business routing, so any Venice business use would be a new paid purpose and need owner approval. I did no research on it.

### 2.4 Usable now vs needs owner approval

| Route | Status |
|---|---|
| Anthropic Haiku 4.5 / Sonnet 5 via `ANTHROPIC_API_KEY` | **Usable now**, if the Railway key is set (production probes say so; I did not re-verify). Laura's CA$0.50/day permission is already owner-approved. |
| Anthropic Haiku 5.5 / Sonnet 5.5 | Same provider. Needs a price row and F-313 eval evidence. Owner approval only if it changes budget. |
| OpenAI text (any model) | Needs **owner approval**, an adapter, and a terms/retention review. |
| Venice for business | Out of scope. Needs owner approval. |

### 2.5 Routing table as implemented (`gateway/routing.py:TASKS`)

Formula for estimates: typical input + max output, at the repo billing rates, CA$ at 1.4154 CAD/USD (`core/fx.py`), unpadded. The gateway pads 1.25× for the reservation, so actual bills are at or below these figures.

| Task class | Task / prompt | Model | Input / max output tokens | Est. CA$ per call |
|---|---|---|---|---|
| Greeting, chit-chat, follow-up, factual Q&A | `laura.converse@1` | claude-haiku-4-5 | 3000 / 450 | 0.0074 |
| Executive reasoning: priorities, recommendations, delegation, briefings | `laura.executive@1` | claude-sonnet-5 | 6000 / 800 | 0.0425 (0.028 at official price) |
| Tick ordering of authorised priorities (ids only) | `laura.exec_rank@1` | claude-sonnet-5 | 3000 / 200 | 0.0170 |
| CEO briefing selection (existing) | `laura.ceo_briefing@4` | claude-sonnet-5 | 6000 / 1472 | 0.0567 |

No Laura task escalates to a stronger tier (`stronger_fallback=False`). When a model is down or too expensive, the owner is told so.

---

## §3 What was implemented

### 3.1 Conversational Business Laura (ADD-LCEO-01/02/03)
- `laura/agency/ceo_chat.py:converse` runs RETRIEVE → REMEMBER → ROUTE → CALL → VALIDATE → PERSIST:
  - **RETRIEVE** (`retrieve`): `talk.converse(persist=False)` is the evidence tool. It runs the same classification, readers, Ask Company, delegation parser and authority-checked proposals, but writes no turn and makes no phrasing call. A headline pack (owner queue, phase, Laura's executive state) is added so greetings are grounded too. A briefing request reads `briefing.evidence_pack` directly, so there is no second model call. The template `answer` is discarded.
  - **REMEMBER**: the last 6 turns of this owner session, plus `relationship` memory under `context/conversation/*`.
  - **ROUTE** (`route`): greetings go to the cheap tier. Executive intents and wording (`should`, `priorit…`, `recommend`, …) go to the standard tier.
  - **CALL**: `gateway/laura_converse.py:call`. Checks run in the same order as the briefing path: permission > 0, then purpose allocation, then provider, then `failover.gateway_for` (month ceiling and agent day), then `complete_json` (atomic reservation before the request).
  - **VALIDATE** (`validate`): citations must name records that were offered. Every number in the reply must appear in the evidence, the owner's words, the conversation or memory. Any claim to be human is rejected. A failing reply is **WITHHELD** with the reason; the invented figures are not echoed.
  - **PERSIST**: the turn goes to `laura_cc_turns` (intent `ceo:*`, method names model and prompt). The cost goes to `laura_cost_events`. An owner-stated preference goes to memory, citing `laura_cc_turns:<id>`.
- When the model is unavailable, status is `UNAVAILABLE` with the exact reason and the message "I won't hand you a canned answer…". Retrieved records are attached and labelled as evidence, not as a reply.
- API: `POST /api/cc/laura/converse` and `GET /api/cc/laura/costs`. The CC Laura view now calls `lauraConverse`. `/laura/ask` stays as the evidence tool, and its existing tests are unchanged.

### 3.2 Executive loop (ADD-LCEO-04)
- **Model priority ordering** (`loop.py:_model_rank`): the model orders only the priorities that code already derived and authorised. Invented ids are ignored, and the constitution and COO boundary still re-check every delegation. Limited to `EXEC_RANK_PER_DAY = 2` per UTC day, inside Laura's day permission and the `exec_rank` allocation. The tick's `cognition` records `deterministic+model-ranked` when this is used.
- **Corrections with feedback** (`loop.py:_feedback`): a rework or challenge job carries `inputs.laura.feedback`, containing the criteria (`REVIEW_CRITERIA`), the verdict, the error, the evidence, `attempt=1` and `max_corrections=1`. It is still bounded: a weak correction becomes a Lesson.
- **Owner report** (`loop.py:_owner_report`): at most one per six-hour window in which Laura acted. It lists what she delegated, reviewed, corrected and escalated and the owner approvals she raised, plus costs per unit of work and her month projection. It goes on the company timeline (severity `decision` when she raised an owner approval) and into operational memory `report/<window>`. It is in-app only; nothing is sent externally (CASL).
- Protected actions are unchanged: they become an owner action card through `_raise_approval` (step 9).

### 3.3 Cost tracking (ADD-LCEO-06)
- `laura/agency/costs.py`, table `laura_cost_events` (additive): conversation (the turn's gateway bill), decision (`exec_rank` bill), delegation and outcome (ledger rows with the job's id). A cost that cannot be measured is stored with `measured=False` and reported as UNKNOWN, never 0. `summary()` gives per-unit costs, cost per *successful* outcome, and Laura's month from the ledger, with projection and target.
- Allocation stops (`finance/spend_policy.py:ALLOCATION`), all inside the unchanged CA$0.50/day and CA$100/month: `laura.converse@1` 8% (CA$8), `laura.executive@1` 5% (CA$5), `laura.exec_rank@1` 2% (CA$2). That totals CA$15, the top of the ADD-LCEO-06 target.

### 3.4 Expected monthly cost (routine), with arithmetic
Assumes a routine day of 20 chat turns, 4 executive questions, 2 tick orderings and 1 briefing, priced at the repo billing rates with worst-case output:
- chat: 20 × 0.00743 = CA$0.149/day
- executive: 4 × 0.04246 = CA$0.170/day
- ordering: 2 × 0.01699 = CA$0.034/day
- **Conversation subtotal: CA$0.352/day × 30 = CA$10.57/month.** With the existing briefing (1 × 0.0567/day = CA$1.70/month), the total is **CA$12.27/month**.
- The daily total of CA$0.409 is below Laura's CA$0.50/day permission, which by itself caps her at about CA$15.5/month.
- At official Sonnet 5 prices the same day costs about CA$0.30, roughly CA$9/month.
- If chat moved to Haiku 5.5 after F-313 evidence, chat would cost about CA$0.45/month.

---

## §4 Tests (offline: stub transport, no network, no key)

`tests/test_w4_laura_ceo.py`: **13/13 pass** (adds `test_validation_matches_the_same_figure_but_never_a_new_one`: 0.50 = 0.5, a clock time read from a timestamp, list markers; a new figure is withheld without echoing it).

| ADD-LCEO-07 step | Test |
|---|---|
| 1 greeting | `test_step1_greeting_is_a_natural_model_reply_not_a_template`: cheap tier; the reply is the model's, differs from the template and is not UNKNOWN; the turn persists; headline evidence is offered |
| 2 accurate status | `test_step2_status_is_grounded_and_an_invented_figure_is_withheld`: cited records carry sources; invented figures and a human claim are WITHHELD |
| 3 priority | `test_step3_executive_reasoning_uses_the_stronger_tier…` and `test_step3_the_tick_lets_the_model_order_only_authorised_priorities`: standard tier; the reply names a real owner action; invented ids are ignored; no protected jobs; cadence ≤ 2/day |
| 4 delegation | `test_steps4_to_8…` (tick → PENDING job with `inputs.laura`) and `test_step4_conversation_delegation_creates_a_real_job_after_confirmation` |
| 5 evaluate | `test_steps4_to_8…`: review decisions useful/failed; outcome cost attributed from the ledger |
| 6 correction | `test_steps4_to_8…`: the rework carries feedback (criteria, verdict, error, attempt 1/1); a second failure becomes a Lesson, not a loop |
| 7 timeline + memory | `test_steps4_to_8…` (timeline kinds, operational `report/*`) and `test_conversation_memory_is_durable_scoped_and_used_next_turn` |
| 8 outcome + costs | `test_steps4_to_8…` (report summary with costs; `costs.summary`; unknown job → UNKNOWN) and `test_cc_route_and_costs_endpoint` |
| 9 protected stop | `test_step9_a_protected_action_stops_and_becomes_an_owner_approval_card`: step-up required; owner action created; zero protected jobs; the tick also raises an owner action |
| Templates never the reply | `test_a_template_is_never_returned_as_the_conversational_reply` (the CC view calls `lauraConverse`) |
| Budget | `test_budget_enforcement_refuses_before_any_provider_call`: permission 0, day spent and allocation spent each cause no provider call; a real call is billed to `laura`; the routine-day estimate is ≤ CA$0.50 and the month ≤ CA$15 |
| No Private Laura data | `test_no_private_laura_data_is_touched`: firewall refusal; static check that no private store, Venice or `laura_private` reference appears; no `laura_private` spend |

Regression (each through `testslot.sh`, all exit code 0):
- Required set: test_vacuity, test_launch, test_cost_governance_wave2, test_search_hero_publish (4/4), test_cert_listing_frames, test_v11_autonomy_timeline.
- Suites for touched files: test_w3_laura_cc_talk 9/9, _delegation 5/5, _followon 4/4, _integration 5/5, _access 5/5, _private 7/7, _providers 7/7, _wiring 5/5; test_w3_laura_core_executive; test_w3_laura_core_wiring; test_w4_laura1_budget 4/4; test_w4_laura1_briefing 19/19; test_w4_laurafix_truncation 8/8; test_w3_spend_laura_phrase; test_spend_policy; test_model_access; test_w4_spend_paid_discipline; test_cert_cost; test_w4_pl_leak 2/2; test_w4_pl_boundary; test_w4_ccgap_views 10/10; test_w4_ccgap2 3/3; test_w4_ccrel 8/8; test_w3_laura_presence 4/4; test_w3_decision_index 3/3.

---

## §5 PRODUCTION ACCEPTANCE RUNBOOK (ADD-LCEO-07)

Run this **only after** the integrator deploys a build containing this branch **and** the owner approves running it. Each step makes real model calls billed to `laura` (about CA$0.25 in total).

Before starting:
- Production is not in an emergency stop.
- `GET /api/cc/laura` shows the canonical identity.
- `GET /api/cc/laura/costs` loads. Record `laura_month.spent_cad` as the baseline.
- The Railway `ANTHROPIC_API_KEY` exists. Check the variable name only; do not read its value.
- Laura's registry row shows `daily_cost_ceiling_cad = 0.50`.

Sign in to the Command Center as the owner. Open **Laura** and use the Ask box, which now posts to `/api/cc/laura/converse`. For each step, record the turn id, `status`, `model`, `method`, `cost` and the cited sources. Screenshots go in `evidence/`.

1. **Greeting.** Type "Good morning Laura, how are you?"
   - Pass: `status` ANSWERED or PARTIAL, `model.source=model`, `model.task=laura.converse`, and a natural reply that is not an "UNKNOWN: this question…" or overnight template. `cost.cost_cad > 0`.
2. **Company status.** Ask "Where does the company stand right now?"
   - Pass: every cited fact links to an existing record (open each drill link).
   - Cross-check each figure against Approvals, Operations and Finance. Any mismatch is a FAIL.
   - A `WITHHELD` status counts as a correct refusal; re-ask.
3. **Priority.** Ask "What should we prioritise this week, and why?"
   - Pass: `model.task=laura.executive`, and the priority she names exists in `GET /api/cc/laura` priorities or the owner queue.
4. **Delegation.**
   - Wait for one tick (≤5 min), then check `/api/cc/laura` `recent_decisions` for a `delegation` with `jobs:<id>`. Open the job: it must exist with `inputs.laura`.
   - Alternatively, ask "Have Design review our banner options", then confirm the proposed follow-on. Pass: `result_ref` is `jobs:<id>` and the job exists.
5. **Evaluate.** After the job finishes, wait for the next tick.
   - Pass: a `review` decision cites that job with verdict useful, noop or failed, and `/api/cc/laura/costs` `outcome.reviewed` has increased.
6. **Correction.**
   - If a delegated job failed or did no work, there is a `rework` or `challenge` decision, and its job's `inputs.laura.feedback` has `attempt: 1` and the criteria.
   - If nothing failed naturally, record "not exercised" and leave the step open until it occurs. **Do not fake a failure.**
7. **Timeline and memory.**
   - The company timeline shows `laura.*` events for steps 4–6.
   - Tell Laura "Please only plan launches on weekdays." The turn's `memory.memory_ref` is set. On the next question, her reply reflects it.
8. **Outcome and costs.**
   - The timeline has a `laura.report` event for the window, with conversation, ordering, delegated-work and per-successful-outcome costs.
   - `/api/cc/laura/costs` matches the ledger (`cost_entries`, agent `laura`) within CA$0.0001.
9. **Protected stop.** Ask "Have the store publish harbour-shawl on Etsy."
   - Pass: there is no `store.*` job. The proposal is `owner_action` and requires step-up. After step-up, an owner action card appears in Approvals. Nothing is published. **Do not grant it.**

**Failure handling.** If any step returns `UNAVAILABLE`, record the stated reason (key, permission, allocation, parked) and stop. That is an honest failure and must not be marked PASS.

**Closing.** ADD-LCEO-07 closes only when all nine steps pass in production with evidence. Until then the row stays open (UNKNOWN is never PASS).

---

## §6 Owner actions

None are needed to merge this branch. To run §5:

| # | Exact action | Why | Max cost | Minutes | If it waits |
|---|---|---|---|---|---|
| OA-LCEO-1 | Approve deploying the integrated build containing W4-LAURACEO, and running the §5 acceptance in production | Production deploys and paid calls need owner approval | ≈CA$0.25 for the run; routine use ≈CA$12/month inside the existing CA$0.50/day permission (no budget change) | 15 | Laura keeps answering from templates in production |

Optional, later: approve the Haiku 5.5 chat route after F-313 eval evidence. It is the same provider and would cut chat cost by about 10×.
Not requested: OpenAI text routing and Venice business use. Both would be new paid purposes needing approval, an adapter and a terms review.
