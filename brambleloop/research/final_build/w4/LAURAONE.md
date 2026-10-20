# W4-LAURAONE: one Laura, one thread (conversational continuity)

- **Source.** Owner requirement 2026-10-20 ("LAURA CONVERSATIONAL CONTINUITY"), plus the owner's clarification the same day (one Laura; she remains the autonomous CEO; Laura's intent drives the business tools; binding information-flow rules; leak channels a–e).
- **Rows.** ADD-LCONT-01..11 (`spec/13` §E). Decision: D-W4-LAURA-UNIFIED.
- **Branch.** `claude/w4-LAURAONE` = `origin/claude/w4-LAURACEO` (a3eec7b) + `origin/claude/w4-VENICE-adult-wip` (98110d8; then fcb2bcd, the owner-approved register copy).
- **State.** Not deployed. No paid call, no key, no Railway change. Everything new is **OFF by default**.

## 1. Architecture

```
owner -- CC Laura view (ONE thread) -- POST /api/cc/laura/unified/{view,turn,crossing,control}
         (owner session + CSRF/nonce + private grant opened with a fresh step-up; approvals: step-up again)
  private_context.unified_turn
   1  record the owner turn in the ENCRYPTED store (every topic) + sealed label (business|private|everyday|mixed, sensitive)
   2  LAURA DECIDES (Venice, pinned router laura.unified_intent@1, laura_private budget):
        tool in {none, business.ask, business.executive, business.briefing, business.delegate} + optional draft brief
        (router unreachable -> code decides from the deterministic label, and says so: routed_by "code (...)")
   3  CODE DECIDES WHAT MAY CROSS (gateway/laura_unified.plan_brief):
        owner's own business-classified words (verbatim)      -> sent
        fixed canonical request for the chosen tool           -> sent      (structured, no conversation content)
        a mixed turn's business sentences / any Venice draft  -> shown to the owner, sent only on approval (step-up)
   4  LEAK GUARD on the brief, then on the EXACT outbound request (rendered user message): refuse on any hit, nothing sent
   5  Business Laura (ceo_chat.converse -> Claude, budget laura): evidence tools, figure/citation validation,
        authority-checked proposals -> follow-ons through the real job queue (owner confirms; protected = step-up + owner action)
   6  no tool -> Laura replies through the ONE private reply path (Venice, laura.private_reply@3, unchanged)
   7  every reply recorded in the same encrypted thread; the business side keeps only brief + result
```

- **One Laura.** There is one persona, `laura-r2-a42aeac7`, and both pinned prompts name it. She is an AI and never claims to be human.
  - Claude is her business reasoning tool, not a second personality. Its answers appear in the thread as Laura's, marked "business tool".
  - Venice does not rewrite them. Deterministic figure and citation validation wins, and a rewrite could change a figure.
- **Laura stays the CEO.**
  - Her executive loop (5-minute tick, priorities, delegation, reviews, escalations) is unchanged and never reads the thread.
  - In the thread, her intent picks the tool. A delegation becomes an authority-checked proposal. The owner confirms it, and it becomes a real queued job (`followon.create`). Protected work needs a step-up and becomes an owner action.
  - Constitution, charters and approval gates stay in code.
- **One endpoint.** When the switch is on, `/api/cc/laura/converse` and `/api/cc/private/turn` answer 409. The executive loop and follow-on routes are unaffected.
- **Business history follows the thread.** It is not tied to the login session (key `laura-unified-thread`), so it survives restarts and new sessions.

## 2. Information flow (binding rules → mechanism)

| Rule | Mechanism | Test |
|---|---|---|
| 1. The thread is continuity only, not company memory | Its tables live on their own metadata, outside `Base`. Only `private_context` may reveal (`ALLOWED_IMPORTERS` unchanged). No business, department, analytics or executive module reads it | `test_no_summary_or_compaction_feeds_a_business_call`, existing `test_w3_priv_firewall`, `test_w3_laura_cc_private` |
| 2. Venice gets the authorised context for continuity | Notes (≤20) and non-excluded turns (≤12). Business exchanges appear as a content-free placeholder unless OA-LCONT-2 is approved | `test_one_thread_keeps_continuity_across_subject_changes` |
| 3–4. Business tools get business context only; private content is excluded by default | `plan_brief` plus the leak guard on the brief and on the outbound request | `test_leak_guard_blocks_…`, `test_outbound_business_request_…` |
| 5. Crossing needs approval of the exact information | A sealed request shows the exact text. The approval route requires a fresh step-up. `laura_boundary_crossings` stores the approved text and its sha256, nothing else. A request resolves once | `test_a_mixed_turn_crosses_…`, `test_crossing_approval_over_http_needs_a_fresh_step_up` |
| 6. No private content in logs, analytics, finance or marketing | Billing holds tokens and cost only. Refusals carry fixed codes. There is no paid-call journal on the private path | `test_private_adult_and_mixed_turns_never_reach_…` |
| 7. Continuity survives restarts and model changes | The thread is in the database. Venice model swap and Claude tier change are both covered | `test_the_thread_survives_…` |
| 8. Owner controls | Mark private, exclude, include again, delete (a turn or a range; replies and crossing requests that quote it go too). **Delete is a real row deletion** from the encrypted store and from every sealed export made afterwards (an export the owner already holds is unchanged) | `test_privacy_controls_…`, `test_forget_is_real_deletion_…` |
| 9. No silent switch that forwards history to a business provider | The thread runs on Venice only (`UNIFIED_NEEDS_VENICE` otherwise). A Venice failure or exhausted budget means Laura says so. A private turn never falls back to Claude. GPT is not wired | `test_no_fallback_path_sends_thread_history_to_claude_or_gpt` |

### Data flow by provider

| Data | Venice (private provider) | Claude (Business Laura) | Business tables / logs / cost / timeline / export | Encrypted store |
|---|---|---|---|---|
| Private, everyday or adult turn, and Laura's Venice reply | yes (context ≤12 turns) | **never** (guard; refused, not sent) | **never** | yes |
| Owner's business turn (brief) | the new message goes to Laura's router (she reads it to decide; it is the owner's words, not company evidence). In later context it appears only if OA-LCONT-2; otherwise as a placeholder | yes, verbatim | `laura_cc_turns` (brief + result) | yes |
| Canonical tool request | — | yes | `laura_cc_turns` | — |
| Venice-drafted brief | (Venice wrote it) | only after owner approval of the exact text | `laura_boundary_crossings` + `laura_cc_turns` after approval | sealed request |
| Mixed turn's business sentences | yes (part of the turn) | only after approval | as above | sealed request |
| Business evidence and validated answer | only if OA-LCONT-2 | yes (existing) | existing | the answer |
| Delegated job payloads, results, reviews, lessons, reports | — | — | brief-derived only | — |
| Billing | tokens + cost, `laura_private` | tokens + cost, `laura` | `cost_entries`, `spend_reservations` (no content) | — |

GPT/OpenAI is **not wired**. It needs a separate owner approval and a terms review (D-W4-LAURACEO-ROUTE). It is an option only.

### Leak guard and residual risk

`gateway/laura_unified.leak_check` is deterministic, and it wins. It compares a candidate with every non-business turn (owner and Laura), every private note (key and text) and every unapproved crossing request. Text the owner approved to cross is allow-listed. It matches four ways:

| Match | Rule |
|---|---|
| Exact substring | ≥12 chars |
| Normalised substring | NFKC, casefold, punctuation folded; ≥3 words |
| Shared shingle | any 6-word shingle |
| **Token overlap** | ≥70% of a private text's distinct content tokens (≥5 tokens of 4+ characters, stop words removed) |

It runs twice: on the brief, and on the exact outbound user message (`ceo_chat.converse(outbound_check=…)`, before any reservation).

| Channel | Control |
|---|---|
| (a) direct briefs | `plan_brief`, then the guard |
| (b) summaries / compaction | **none exist**. The one call site of Business Laura in `private_context` passes the outbound guard (statically asserted). Any future summary would hit the same guard |
| (c) Venice-generated briefs | **never sent automatically**. The owner sees the exact draft and approves it with step-up. The guard also catches near-verbatim paraphrase (overlap and shingles). Choice: owner review rather than structured-only, because a delegation needs free text; structured fields (tool enum → canonical request) are used where they suffice |
| (d) delegated jobs, reviews, lessons, owner reports | Jobs are created only from business turns (`laura_cc_turns`). The executive loop never reads the thread. Asserted over every Base table after a delegation and an executive tick |
| (e) logs, audit, cost rows, timeline | SQL parameters, logging, stdio, every Base table and the continuity export are all swept |

**Residual risk (honest):**
- **Paraphrase.** A paraphrase with different words and low token overlap would pass the guard. It can only originate from a Venice draft or from the owner's own business-classified words. Venice drafts are always shown to the owner first, so the residual channel is the owner retyping private content in a message that the classifier labels business-only, without private signal words.
- **Very long threads.** The guard reads the newest 500 turns (the store's read cap). Older private turns are not compared. They do not reach business briefs by any path either, because briefs are built only from the current turn, canonical requests or owner-approved text.
- **Short private texts.** Texts under 12 characters and 3 words are not matched. The classifier, not the guard, covers them.
- **Marking private afterwards.** Marking a business turn private later does not erase the business record already made. The guard then blocks any further use of that text.

## 3. Memory tiers

| Tier | Holds | Where |
|---|---|---|
| Thread (all topics) | owner and Laura turns; sealed label, sensitive and excluded flags | `laura_private_entries` kind `turn` (AES-GCM) |
| Private notes | owner-supplied facts | kind `fact` (unchanged) |
| Crossing requests | exact text, origin (owner_quote / laura_draft), status | kind `xing` (sealed) |
| Business conversation | briefs + results | `laura_cc_turns` (session key `laura-unified-thread`) |
| Business memory | owner-stated business preferences | `laura.memory` relationship tier (unchanged; `reject_private`) |
| Crossed text | approved text only | `laura_boundary_crossings` (new, Base) |

Key rotation (`store.rekey`) re-seals labels, flags and crossing requests unchanged (tested).

## 4. Cost attribution

| Call | Agent | Purpose | Typical cost (`venice-uncensored-1-2`) |
|---|---|---|---|
| Laura's intent (every turn, Venice) | `laura_private` | `laura.unified_intent@1`, ≤120 output tokens | ≈ CA$0.001 |
| Laura's reply (Venice) | `laura_private` | `laura.private_reply@3` | ≈ CA$0.0006 (VENICE.md §9) |
| Business tool (Claude) | `laura` | `laura.converse@1` / `laura.executive@1` (8% / 5% stops) | ≈ CA$0.002–0.02 |

- **Venice capacity.** About 300 Venice turns per CA$0.50 day.
- **Reservation.** Every call is reserved before it is made. No ceiling is raised.
- **When a budget is exhausted.** Laura says so in the thread. There is no fallback in either direction.

## 5. Venice as the primary layer (against VENICE.md)

| Question | Verdict |
|---|---|
| Private class, zero retention, contract-enforced (F11) | documented; `venice-uncensored-1-2` verified Private (pinned row + live check) |
| Server-side conversation state | **UNKNOWN** (not documented); not used. Requests are stateless; continuity is ours |
| Context / output for `venice-uncensored-1-2` | 128K / 8,192 (documented); we send ≤ ~6K tokens |
| JSON-following for the router | function calling and JSON schema are documented [VENICE.md S1]; actual router accuracy is **UNKNOWN** until the production test. Malformed output is refused and code decides |
| Metadata retention period | **UNKNOWN** (F11) |
| Persona continuity / system-prompt adherence benchmarks | **UNKNOWN** |
| Terms §10.9(c) vs adult content | owner attestation recorded (D-W4-PL-VENICE-ADULT). The register copy is BLOCKED (§7) |

Verdict: Venice is fit as Laura's conversational voice and intent layer. It is not fit as the source of business facts, which stay with Business Laura's evidence tools and validation.

## 6. Owner switches (all default OFF)

| Switch | Effect |
|---|---|
| `BRAMBLELOOP_LAURA_UNIFIED=venice` | One thread; split routes return 409. Unset or anything else: today's behaviour, byte for byte |
| `BRAMBLELOOP_LAURA_BUSINESS_TO_VENICE=1` | Business briefs and validated answers enter Venice's context: a **new company-data flow to a new provider** (OA-LCONT-2) |
| Shared with Private Laura | `BRAMBLELOOP_PRIVATE_MEMORY_KEY`, `BRAMBLELOOP_LAURA_PRIVATE_REGISTER=1`, `BRAMBLELOOP_PRIVATE_PROVIDER=venice`, `VENICE_API_KEY`, `BRAMBLELOOP_LAURA_PRIVATE_DAILY_CAD`, a proven deployed release |
| In-thread controls | keep this private, mark private, exclude from context, include again, delete (a turn or a selection) |

## 7. PRODUCTION ACCEPTANCE RUNBOOK (ADD-LCONT-11, OPEN; run only after the owner approves deploy and activation)

| # | Step | Pass |
|---|---|---|
| U1 | With the switch off, open Laura | The split view is unchanged; the unified status shows `unified: off` |
| U2 | Set OA-LCONT-1 and OA-LCONT-3, redeploy, then open the conversation (step-up) | One thread; prerequisites all met |
| U3 | "Good morning" → a personal message → "What should the shop prioritise this week?" → "and how are you feeling?" | The same Laura throughout. The business answer cites records (routed_by `laura`). The last reply remembers the personal message |
| U4 | A mixed message (personal + business) | Laura answers, and asks to share exactly the business sentence. Decline: nothing crosses. Approve with step-up: one `laura_boundary_crossings` row with that text |
| U5 | "Have Design make three more banners" → confirm the follow-on | A real job in the queue; nothing published |
| U6 | Railway restart, then reopen | The thread is intact; a new reply uses earlier turns |
| U7 | Read-only DB check (row counts and grep for a test phrase only) | The test phrase appears in no Base table, log line, cost row or timeline |
| U8 | Set `BRAMBLELOOP_LAURA_PRIVATE_DAILY_CAD=0.001`, send one message, restore | Laura says the budget is used up; no Claude call |
| U9 | Delete the U3 personal message | Gone from the view; a row count of `laura_private_entries` falls |

## 8. Owner actions

| ID | Exact action | Why | Max cost | Minutes | Consequence of waiting |
|---|---|---|---|---|---|
| OA-LCONT-1 | After a release containing this branch is deployed: Railway → brambleloop-os → Variables → `BRAMBLELOOP_LAURA_UNIFIED=venice` | The thread is off by default | CA$0 direct. Spend stays inside the existing `laura_private` CA$0.50/day and `laura` CA$0.50/day | 2 | Laura stays two split conversations |
| OA-LCONT-2 (optional) | Approve and set `BRAMBLELOOP_LAURA_BUSINESS_TO_VENICE=1` | A new flow of company data to a new provider needs your separate approval | CA$0 extra (more tokens per Venice call, inside the same cap) | 2 | Venice sees only "a business exchange happened"; its replies cannot refer to business details |
| OA-LCONT-3 | Private Laura prerequisites: `BRAMBLELOOP_PRIVATE_MEMORY_KEY`, `BRAMBLELOOP_LAURA_PRIVATE_REGISTER=1`, `BRAMBLELOOP_PRIVATE_PROVIDER=venice`, `VENICE_API_KEY`, `BRAMBLELOOP_LAURA_PRIVATE_DAILY_CAD=0.50`, Venice API credit (VENICE.md §6) | Venice is Laura's voice; nothing replies without these | CA$0.50/day cap; Venice credit purchase (minimum UNKNOWN) | 10–15 | The thread records turns and routes business by code, but Laura has no conversational voice |
| OA-LCONT-4 | Approve deploy of a release containing this branch, after integration and an independent security review | No deploy without approval | CA$0 | 5 | Nothing here reaches production |

## 9. BLOCKED / not done

- **The four register strings were never edited here.** They are `laura.js:273`, `voice_spec.py` `private_text_register` "bounds", `roadmap.py` `LAURA-PRIVATE-REGISTER` detail and `private_context.py` `REPLY_ENABLED`. The owner's own commit `fcb2bcd` (`claude/w4-VENICE-adult-wip`) was merged unchanged, and all four are byte-identical to that commit. The router prompt carries no register wording. `laura.js` loads the thread view by dynamic import, so line 273 does not move.
- ADD-LCONT-11 (production acceptance) is **OPEN**.

## 10. Tests

`tests/test_w4_laura_unified.py`: 21 offline tests. Regression results are in §11.

## 11. Regression results (2026-10-20, focused suites via testslot; no full suite)

- **New suite.** `test_w4_laura_unified` 21/21, re-run after merging fcb2bcd.
- **Laura, Venice and Private Laura suites, all green:**
  - `test_w4_venice` 18/18, `test_w4_laura_ceo` 13/13, `test_w4_plact` 8/8, `test_w4_credhealth` 13/13;
  - `test_w4_pl_auth` / `pl_reply` / `pl_leak` / `pl_boundary` / `pl_budget` / `pl_continuity`;
  - `test_cert_spend_hosts`;
  - `test_w3_priv_access` / `continuity` / `firewall` / `leak` / `provenance` / `store`;
  - `test_w3_laura_cc_private` 7/7, `test_w3_laura_cc_access` / `followon` / `talk` / `wiring` / `integration`, `test_w3_laura_memory_isolation`, `test_w3_laura_core_continuity`, `test_w3_laura_voice_spec` 7/7;
  - `test_w4_integ3_secfixes`.
- **Command Center front end, all green:** `test_v11_pwa_static` 82/82, `test_cert_mjs`, `test_w4_mjs_findings`, `test_w4_mjscount`, `test_w4_cc_company` 23/23.
- **Required set, all exit 0:** `test_vacuity`, `test_launch`, `test_cost_governance_wave2`, `test_search_hero_publish` (4/4), `test_cert_listing_frames`, `test_v11_autonomy_timeline`, `test_w3_decision_index`.
