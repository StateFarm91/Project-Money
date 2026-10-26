# W4-LAURAONE: one Laura, one thread (conversational continuity)

- **Source.** Owner requirement 2026-10-20 ("LAURA CONVERSATIONAL CONTINUITY"). The owner then refined it twice on the same day:
  - **First clarification.** One Laura who remains the autonomous CEO; her intent drives the business tools; binding information-flow rules; leak channels a–e.
  - **Review.** Unified Laura is the preferred candidate. The restricted business-context feed to Venice is **owner-approved for design**, with activation still needing separate approval. Structured requests come first; text-based leak detection is the second line.
- **Rows and decisions.** Rows ADD-LCONT-01..13 (`spec/13` §E). Decisions D-W4-LAURA-UNIFIED and D-W4-LAURA-UNIFIED-FEED.
- **Branch.** `claude/w4-LAURAONE` = `origin/claude/w4-LAURACEO` (a3eec7b) + `origin/claude/w4-VENICE-adult-wip` (98110d8, then fcb2bcd with the owner's register copy, then 3cf3c8b).
- **State.** Not deployed. No paid call, no key, no Railway change. **Every switch is OFF by default.**

## 1. Architecture

```
owner -- CC Laura view (ONE thread) -- POST /api/cc/laura/unified/{view,turn,crossing,control,feed-preview}
         (owner session + CSRF/nonce + private grant opened with a fresh step-up)
  private_context.unified_turn
   1  record the owner turn in the ENCRYPTED store (every topic) + sealed label (business|private|everyday|mixed, sensitive)
   2  LAURA DECIDES (Venice, pinned router laura.unified_intent@1, laura_private budget):
        tool in {none, business.ask, business.executive, business.briefing, business.delegate} (+ optional draft)
        (router unreachable -> code decides from the deterministic label, and says so: routed_by "code (...)")
   3  CODE DECIDES WHAT CROSSES (gateway/laura_unified.plan_brief):
        AUTOMATIC  = a STRUCTURED request: tool + allowlisted parameters extracted deterministically
                     (metrics, period, product ids, priority id, department, task object, count),
                     rendered by code. No conversation text at all.
        OFFERED    = free text only: the owner's own business words (one explicit tap), a mixed turn's
                     business sentences, a Venice draft, a delegation with no allowlisted object
                     (all: fresh step-up). Any offer whose text overlaps the private conversation is
                     upgraded to step-up and flagged.
   4  LEAK GUARD (defence in depth) on the request and on the EXACT outbound request: refuse on any hit
   5  Business Laura (ceo_chat.converse -> Claude, budget laura, no business-memory writes from the thread):
        evidence tools, figure/citation validation, authority-checked proposals -> real queued jobs
   6  no tool (or a mixed turn) -> Laura replies through the ONE private reply path (Venice, laura.private_reply@3);
        with BRAMBLELOOP_LAURA_BUSINESS_TO_VENICE=1 Venice also gets the restricted context pack (§3)
   7  every reply recorded in the same encrypted thread; the business side keeps only the request + result
```

- **One Laura.** There is one persona, `laura-r2-a42aeac7`. She is an AI and never claims to be human.
  - Claude is her business reasoning tool. Its answers appear in the thread as Laura's, marked "business tool". Venice does not rewrite them, because deterministic validation wins.
- **Laura stays the CEO.**
  - Her executive loop (tick, priorities, delegation, reviews) is unchanged and never reads the thread.
  - In the thread, her intent picks the tool. A structured delegation ("Have Design make 3 more banners.") becomes an authority-checked proposal. The owner confirms it, and it becomes a real queued job (`followon.create`). Protected work needs step-up and becomes an owner action.
- **One endpoint.** When the switch is on, `/laura/converse` and `/private/turn` answer 409.
- **Business history follows the thread** (key `laura-unified-thread`), not the login session.

## 2. Information flow (binding rules → mechanism → test)

| Rule | Mechanism | Test (`tests/test_w4_laura_unified.py`) |
|---|---|---|
| 1. The thread is continuity only | Private tables live outside `Base`. `ALLOWED_IMPORTERS` is unchanged. No business, department, analytics or executive reader touches the thread | `test_no_summary_or_compaction_feeds_a_business_call` (+ existing firewall suites) |
| 2. Venice gets authorised conversational context | Notes ≤20 and non-excluded turns ≤12. Business exchanges appear as a placeholder. The company pack is sent only with the feed switch on | `test_one_thread_keeps_continuity_…`, `test_feed_switch_off_…` |
| 3–4. Business-only context, private excluded by default | **Structured requests only**; free text never crosses automatically | `test_structured_requests_…`, `test_leak_guard_blocks_…` |
| 5. Approval of the exact information | A sealed offer shows the exact text. One tap for clean owner business words; step-up for everything else, including any text that overlaps private content. `laura_boundary_crossings` holds the approved text and its sha256 only | `test_a_mixed_turn_crosses_…`, `test_crossing_approval_over_http_…`, `test_a_brief_venice_drafts_…` |
| 6. No private content in logs, analytics, finance or marketing | Billing and audit hold tokens, costs, names and counts only | `test_private_adult_and_mixed_turns_never_reach_…`, `test_feed_is_allowlisted_…` |
| 7. Continuity through restarts and model changes | The thread lives in the database | `test_the_thread_survives_…` |
| 8. Owner controls | Keep private, mark private (also **redacts derived business records**), exclude, include, delete (real row deletion) | `test_privacy_controls_…`, `test_forget_is_real_deletion_…`, `test_marking_private_afterwards_redacts_…` |
| 9. No silent switch to a business provider | The thread runs on Venice only. A failure or exhausted budget means Laura says so. GPT is not wired | `test_no_fallback_path_…` |

### Data flow by provider

| Data | Venice | Claude (Business Laura) | Business tables / logs / cost / timeline / export |
|---|---|---|---|
| Private, everyday or adult turns; Venice replies | yes (context) | **never** | **never** |
| Owner's business turn | the new message goes to the router; afterwards a placeholder | **structured request only** (code-rendered); her exact words only on her tap | `laura_cc_turns` (request + result) |
| Mixed turn's business sentences; Venice drafts | yes / authored by Venice | only after approval with step-up | crossing row (approved text only) + request |
| Restricted company-context pack (§3) | **only** with `BRAMBLELOOP_LAURA_BUSINESS_TO_VENICE=1` | — | audit row: sha256, field names, counts, dropped names; **no values** |
| Business evidence and validated answers | **never** (the earlier "business exchanges to Venice" design is withdrawn) | yes (existing) | existing |
| Billing | tokens and cost, `laura_private` | tokens and cost, `laura` | no content |

GPT/OpenAI is **not wired**. It needs a separate owner approval and a terms review. It is an option only.

## 3. Restricted business-context feed to Venice (`laura/agency/venice_context.py`)

The schema is defined in code. Each field has a name, a type, a declared source (one read function; never the raw database or an arbitrary table), a size cap and a sensitivity class. A field outside the allowlist cannot be emitted.

| Field | Type | Declared source | Max | Class |
|---|---|---|---|---|
| `company_phase` | identifier | `core.phase.resolve` | 20 chars | status |
| `open_owner_decisions` | int | `approvals.inbox` (count) | 1 | aggregate |
| `products_by_status` | {status: count} | `products` GROUP BY status | 12 keys | aggregate |
| `certified_pattern_versions` | int | `pattern_versions` WHERE certified (count) | 1 | aggregate |
| `department_jobs_24h` | {agent: {status: count}} | `jobs` last 24 h GROUP BY agent, status | 20 agents | aggregate |
| `model_spend_month_cad` | float | `cost_entries` this UTC month (sum) | 1 | aggregate |
| `model_ceiling_month_cad` | float | `spend_policy.CEILING_CAD` | 1 | aggregate |
| `revenue_total_cad` | float or null | `readers.revenue` (reconciled total; null = UNKNOWN, never 0) | 1 | aggregate |
| `laura_priorities` | [{department, status, title}] | `laura.executive.priorities` (open, top 5) | 5 × 140 chars | decision_title |
| `laura_recent_decisions` | [{kind, subject}] | `laura.executive.history` (top 5) | 5 × 140 chars | decision_title |
| `owner_decision_titles` | [str] | `approvals.inbox` titles (top 5) | 5 × 140 chars | decision_title |

- **Validators.**
  - `reject_private` (the private-value firewall).
  - Deny patterns: email, phone, Canadian postal code, any run of 5+ digits (ZIP codes, Etsy receipt, buyer and order ids, card fragments), card, IBAN, key prefixes (`sk-`, `ghp_`, `AKIA`, `AIza` …), bearer/secret/token/password words, hex or base64 blobs of 24+ characters, street addresses, and customer/payment vocabulary (customer, buyer, receipt, transaction, refund, payment, card, invoice, address, email, phone, message …).
  - Numbers must be finite, non-negative and not booleans. Identifiers must be short slugs.
  - Free text is allowed only in `decision_title` fields.
- **Fail closed.** Any hit drops the **whole field**, recorded as `{name, validator}`, never the value.
- **Size and audit.** The pack is capped at 3,000 bytes; fields are dropped from the lowest priority up, recorded by name. Each pack actually sent writes `audit_log` `laura.venice_context.sent` with sha256, field names, counts, bytes and dropped names only.
- **Preview.** `POST /api/cc/laura/unified/feed-preview` (owner-only, no-store) shows exactly the payload, with the same sha256, plus each field's source and class and what was dropped. Tested: preview payload == what Venice received == the audited sha256.
- **Excluded by construction.** Credentials and keys; customer names, emails, addresses, Etsy buyer data and messages; payment details; protected personal records; private conversation; product titles and any line item with a counterparty.
- **Spend.** The pack adds about 100–800 input tokens to a Venice reply (≈ CA$0.0002 on `venice-uncensored-1-2`), inside `laura_private`'s CA$0.50/day.

## 4. Residual risks: before and after this revision

| # | Before (a4a6841) | After |
|---|---|---|
| 1 | **Owner paraphrase.** Her own business-labelled words went to Claude automatically, so a paraphrase of private content with low overlap could pass | **Closed by design.** Only code-rendered structured requests are sent automatically. Her words cross only on her explicit tap of the exact text. A tap on text that overlaps private content needs step-up (`overlaps_private`) |
| 2 | **Short private texts** (under 12 characters and 3 words) were not matched | **Exact whole-phrase match** (normalised) for short texts that contain a content token. "darling" or a code word blocks; "hi" or "ok" cannot block every request. Residual: a short private phrase made only of stop words is not matched, and carries no content |
| 3 | **The guard looked back 500 turns** | **The whole retained store** (`store.conversation(limit=None)`). Cost: one decrypt per retained turn per business call (milliseconds at thousands of turns). Delete keeps the store bounded |
| 4 | **Marking private afterwards** did not erase the business record | The **derived business records are redacted**: the `laura_cc_turns` request, answer, facts and proposals, and an approved crossing's text (its sha256 kept as proof). Links are sealed in the thread (`business_ref`, `crossed_ref`). Residual: a job already created from a structured delegation keeps its code-rendered task; it never held conversation text. Thread calls write nothing to Laura's business memory (`allow_memory=False`) |
| 5 | Venice drafts | Unchanged: always shown, step-up, guard on top |
| 6 | **Feed: personal names inside decision titles** | New. Not detectable in general. Mitigated: titles come from code-generated approval cards and priorities; the vocabulary deny-list drops any customer, buyer or message wording; the whole field fails closed. The owner sees every title in the preview before activating |

## 5. Memory tiers

| Tier | Holds | Where |
|---|---|---|
| Thread | turns; sealed label, flags, `business_ref` | `laura_private_entries` kind `turn` (AES-GCM) |
| Private notes | owner facts | kind `fact` |
| Crossing offers | exact text, origin, step-up flag, status, `crossed_ref`/`business_ref` | kind `xing` (sealed) |
| Business conversation | structured requests / approved text + results | `laura_cc_turns` (`laura-unified-thread`) |
| Crossed text | approved text only (redactable) | `laura_boundary_crossings` |

Key rotation re-seals all of these (tested).

## 6. Cost attribution

| Call | Agent | Typical cost |
|---|---|---|
| Laura's intent (Venice) | `laura_private`, `laura.unified_intent@1` | ≈ CA$0.001 |
| Laura's reply (Venice) | `laura_private`, `laura.private_reply@3` | ≈ CA$0.0006, + ≈ CA$0.0002 with the feed |
| Business tool (Claude) | `laura`, `laura.converse@1` / `laura.executive@1` (8% / 5% stops) | ≈ CA$0.002–0.02 |

Every call is reserved before it is made. No ceiling is raised. When a budget is exhausted, Laura says so, with no fallback in either direction.

## 7. Venice as the primary layer (against VENICE.md)

| Question | Verdict |
|---|---|
| Private class, zero retention (F11) | documented; `venice-uncensored-1-2` verified Private |
| Server-side conversation state | **UNKNOWN**; not used (continuity is ours) |
| Context / output | 128K / 8,192 (documented); we send ≤ ~7K tokens |
| JSON adherence for the router | function calling and JSON documented; real accuracy **UNKNOWN** until production. Malformed output is refused and code decides |
| Metadata retention period | **UNKNOWN** |
| Persona benchmarks | **UNKNOWN** |

## 8. Owner switches (all default OFF)

| Switch | Effect |
|---|---|
| `BRAMBLELOOP_LAURA_UNIFIED=venice` | One thread; split routes return 409 |
| `BRAMBLELOOP_LAURA_BUSINESS_TO_VENICE=1` | The **restricted, allowlisted context pack** (§3) enters Venice's context. Design approved; activation is a separate owner decision (OA-LCONT-2) |
| Shared with Private Laura | `BRAMBLELOOP_PRIVATE_MEMORY_KEY`, `BRAMBLELOOP_LAURA_PRIVATE_REGISTER=1`, `BRAMBLELOOP_PRIVATE_PROVIDER=venice`, `VENICE_API_KEY`, `BRAMBLELOOP_LAURA_PRIVATE_DAILY_CAD`, a proven deployed release |
| In-thread controls | keep this private; mark private (redacts derived records); exclude; include; delete; share-this offers; feed preview |

## 9. PRODUCTION ACCEPTANCE RUNBOOK (ADD-LCONT-11, OPEN)

Run this only after the owner approves the deploy and activation. Evidence is status codes, row counts, hashes and field names only.

| # | Step | Pass |
|---|---|---|
| U1 | Switch off: open Laura | The split view is unchanged; unified status shows `off` |
| U2 | Set OA-LCONT-1 and OA-LCONT-3, redeploy, then open (step-up) | One thread; all prerequisites met |
| U3 | "Good morning" → a personal message → "How did the shop do this week?" → "and how are you feeling?" | The same Laura throughout. The business answer shows `brief_origin: structured`, and the request in `laura_cc_turns` is code-rendered (not her words). The last reply remembers the personal message |
| U4 | **Structured requests**: "How were sales overnight for <product>?" | `intent.params` lists metrics, period and product id; the request in `laura_cc_turns` holds only those |
| U5 | **Approval control**: tap "Share exactly this…" on the U4 offer (no step-up). Then send a mixed message and try to share it without step-up, then with | The U4 tap crosses one row of exactly that text. The mixed share is refused with `STEP_UP_REQUIRED`, then crosses after step-up. A declined offer crosses nothing |
| U6 | **Leak paths**: send a personal message containing a unique test phrase; then grep (read-only) business tables, logs, cost rows, the timeline and `audit_log` for it | 0 matches (paths a–e) |
| U7 | **Context feed preview** with the switch still off | The preview lists only allowlisted fields; Venice requests carry no pack; no `laura.venice_context.sent` rows |
| U8 | **Feed on** (OA-LCONT-2, after approval): send one message | One `laura.venice_context.sent` row whose sha256 equals the preview's, holding names and counts and **no values**; Venice replies with company awareness. Read the row's `outcome`: `REPLIED` means it left and was answered; `PROVIDER_ERROR` (or a Venice transport code) means it *possibly* left, because the failure happened inside the send (2c29b42 review Q-4). A failure before the send writes no row |
| U9 | "Have Design make three more banners" → confirm the follow-on | A real queued job; nothing published |
| U10 | Railway restart, then reopen | The thread is intact and continuity holds |
| U11 | Mark U3's business turn private | Its `laura_cc_turns` row is redacted |
| U12 | Set `BRAMBLELOOP_LAURA_PRIVATE_DAILY_CAD=0.001`, send one message, restore | Laura says the budget is used up; no Claude call |
| U13 | Delete the U6 message | The row count of `laura_private_entries` falls |

## 10. Owner activation decisions

| ID | Exact action | Why | Max cost | Minutes | Consequence of waiting |
|---|---|---|---|---|---|
| OA-LCONT-1 | After a release containing this branch is deployed: Railway → brambleloop-os → Variables → `BRAMBLELOOP_LAURA_UNIFIED=venice` | The thread is off by default | CA$0 direct (inside `laura_private` and `laura` at CA$0.50/day each) | 2 | Laura stays two split conversations |
| OA-LCONT-2 | Review the feed preview (§3), then set `BRAMBLELOOP_LAURA_BUSINESS_TO_VENICE=1` | Design approved 2026-10-20; **activation** of company aggregates flowing to Venice is your separate decision | ≈ CA$0.0002 per reply, inside CA$0.50/day | 5 | Venice has no company awareness; business detail stays in business-tool answers |
| OA-LCONT-3 | `BRAMBLELOOP_PRIVATE_MEMORY_KEY`, `BRAMBLELOOP_LAURA_PRIVATE_REGISTER=1`, `BRAMBLELOOP_PRIVATE_PROVIDER=venice`, `VENICE_API_KEY`, `BRAMBLELOOP_LAURA_PRIVATE_DAILY_CAD=0.50`, Venice API credit | Venice is Laura's voice | CA$0.50/day; Venice credit minimum UNKNOWN | 10–15 | No conversational voice; business is routed by code only |
| OA-LCEO-1 | `BRAMBLELOOP_LAURA_CEO_MODEL=1` (integration review S-1) | Business Laura's model conversation, executive reasoning, tick ranking **and the model-synthesised CEO briefing** (`laura_briefing.synthesize`, the briefing you approved on 2026-10-11) stay off until you activate them. The unified thread's business tool needs this too. Setting it is a deliberate **re-enablement** of that briefing (2c29b42 review Q-5) | inside `laura` CA$0.50/day (converse 8%, executive 5%, exec_rank 2% stops, plus briefing synthesis calls; ≈CA$12/month) | 2 | Business Laura answers deterministically from the records; **the CEO briefing is the deterministic fallback, not the model-synthesised one, from the deploy of this branch until you set it**; the unified thread's business tool says it is off |
| OA-LCONT-4 | Approve deploy of a release with this branch, after integration and the independent security review (a4a6841 under review; a delta review covers this revision) | No deploy without approval | CA$0 | 5 | Nothing reaches production |

## 10a. Response to the independent security review of a4a6841 (`INDEPENDENT_SECREVIEW_LAURAONE.md`) and the INTEG5 finding

Every test named below is in `tests/test_w4_laura_unified.py` unless another file is named. Each one asserts a behaviour that a4a6841 did not have: the review's PoCs reproduced it there. The fix lands in `89860a1` and later commits on this branch. The scope is frozen: these are fixes only, with no new functionality.

| Finding | Fix | Regression test | Status |
|---|---|---|---|
| **B-1(a)** code fallback sent the owner's words | When code rather than Laura routes the turn (router unreachable, out of budget, malformed, not selected, register off), **nothing is sent automatically**. Her words are only offered, with step-up. `routed_by` is shown in the UI | `test_review_b1_router_unavailable_sends_nothing_to_the_business_side` (5 causes) | FIXED |
| **B-1(b)** raw words in `laura_cc_turns` | Automatic sends are code-rendered structured requests only (a112da1). Raw words cross only on her approval of the exact text | `test_review_b1_personal_content_with_laura_routing_crosses_only_a_code_request`, `test_structured_requests_…` | FIXED |
| **B-1(c)** guard never inspected the current turn | Negative screen of the current turn (`laura_unified.sensitive_screen`), covering personal, health, legal, identity, personal finance, relationship, contact and credential content. A hit means no parameters are taken from the turn and any offer needs step-up | same test, plus `test_review_b1_no_sensitive_category_crosses_without_an_owner_tap` (7 categories) | FIXED |
| **B-1(d)** the classifier decided by itself | The classifier no longer decides that anything crosses. Automatic sending requires Laura's router choice, and the request is code-rendered. Her text needs her tap; step-up is required unless the words are business-classified, pass the screen and do not overlap private content | as above | FIXED |
| B-1 (review rec. c) `remember` notes | Thread calls write no business memory (`allow_memory=False`, a112da1) | `test_delegation_…` table sweep | FIXED |
| **H-1** split route leaked business and excluded turns after switch-off | `_laura_reply` now uses the unified context builder: excluded turns never, business exchanges as a placeholder, no feed | `test_review_h1_switching_off_never_forwards_business_or_excluded_turns_to_venice` | FIXED |
| **M-1** truncated body; silent pinned-row fallback | `_http` returns the full body up to 2 MB (larger is refused). An unreadable model list is recorded as unreadable. The newest successfully parsed reading decides, so a contradiction stays sticky. If checks ran but none parsed, the model is not eligible (fail closed). If no check has ever run, the pinned row decides, as designed | `test_review_m1_live_model_check_parses_long_lists_and_fails_closed` | FIXED |
| **M-2** bearer key forwarded on redirect | `venice.no_redirect_opener()` refuses every 3xx before contacting the new location, in both `VeniceProvider._post` and `credentials._http` (which also covers the Anthropic and BFL credential checks) | `test_review_m2_the_bearer_key_is_never_forwarded_on_a_redirect` (cross-host over loopback; https→http and cross-host on the handler) | FIXED |
| **L-1** login or opening step-up approved crossings | Approval counts only a step-up performed **after** the offer was made, and never the login window. The route passes the step-up's issue time | `test_review_l1_approval_needs_a_step_up_performed_after_the_offer` (function + HTTP) | FIXED |
| **L-2** TOCTOU double crossing | `store.resolve_crossing` compare-and-sets on the sealed row (ciphertext and nonce) in one UPDATE; `rowcount != 1` refuses | `test_review_l2_a_crossing_resolves_exactly_once_under_a_race` | FIXED |
| **L-3** over-long crossing left half-approved | Offers over 2,000 characters are never created (`held: too_long`). Approval checks the length **before** resolving | `test_review_l3_an_over_long_crossing_is_never_left_half_approved` | FIXED |
| **L-4** mark-private blocked business | Mark-private redacts the derived `laura_cc_turns` row (a112da1), so the history no longer carries it | `test_review_l4_marking_a_business_turn_private_does_not_block_later_business` | FIXED |
| **L-5** deletion narrower than documented | Delete now also removes the approval turn and Business Laura's reply to it, and redacts the crossed text and derived business rows. Copies at database level (free pages, WAL, backups) are outside the application; documented, not fixable here | `test_review_l5_delete_cascades_to_derived_records` | FIXED (database level documented) |
| **L-6** Venice reply labelled business | Venice-authored replies are always labelled `private` (or `everyday`) | `test_review_l6_venice_replies_are_never_labelled_business` | FIXED |
| I-1 owner's words always reach Venice | Spec ADD-LCONT-10 wording aligned: her newest message is conversation and reaches Laura's router and reply | doc | FIXED (doc) |
| I-2 global allow-list | The allow-list is scoped to approved texts the request actually carries (the brief and the history window) | `test_review_i2_the_allow_list_is_scoped_to_what_the_request_carries` | FIXED |
| I-3 credential error bodies (≤300 chars) in audit | Kept deliberately. The key-redacted provider error is the owner's only diagnosis of a failing credential, and it holds no conversation content. Removing it would take that diagnosis away from the owner | — | OPEN (accepted risk, documented) |
| I-4 stale label | `credentials.PROVIDERS["venice"]["model"]` set to `venice-uncensored-1-2` | — | FIXED |
| I-5 reported model not compared | Fixed in the 2026-10-21 round (owner directive: fix every low-risk finding). A Venice answer whose reported model is neither the requested model nor a dated/versioned id of it is refused (`MODEL_MISMATCH`). It is billed, and its text is never used | `test_review_i5_a_substituted_model_answer_is_never_used` | FIXED |
| I-6 guard residuals | Superseded: structured-first design, whole-store guard, short exact matching, current-turn screen | above | ADDRESSED |
| **INTEG5** @3 sent on a non-Venice transport | Option (a): with any provider other than Venice, `laura_register.reply` refuses `laura.private_reply@3` with `REGISTER_NEEDS_VENICE` before any reservation or request. There is no silent fallback to @2, because that would be a different Laura than the owner chose. The `pl_*` and `plact` suites now drive the same reply path over a stubbed **Venice** transport; their assertions are unchanged apart from the provider and model names and Venice's estimate | `test_integ5_the_adult_register_is_never_sent_to_a_non_venice_transport`; a new case in `test_w4_pl_reply` | FIXED |

**Residual risks after this round (honest):**
- **The owner taps her own text.** Text she taps to share crosses as she approved it. A business-classified, screen-clean, non-overlapping text crosses with one tap. Anything else needs step-up.
- **The screen is a category screen, not a proof.** Personal content that uses none of the screened categories and does not overlap earlier private turns can be labelled business. Even then, the only thing that crosses automatically is a code-rendered request built from allowlisted parameters, never her words.
- **Paraphrase in her own tapped text.** This is unchanged: the owner sees the exact text before it crosses.
- **Mark-private relabels Business Laura's answer too.** A later answer that closely repeats it (6-word shingles) is refused. This fails closed.
- **Database-level copies.** Deleted rows can survive in free pages, WAL and backups.
- **Pinned row before the first check.** If no credential check has ever run, the pinned row decides eligibility, as designed.
- **I-3 and I-5** are OPEN, as listed in the table.

## 10b. Response to the delta review (a4a6841..c13e20d) and the integration review (bcce679)

Both reviews found NO BLOCKER. This round fixes the findings the coordinator assigned. No new features were added.

| Finding | Fix | Regression test | Status |
|---|---|---|---|
| **N-1** (LOW) personal sentences got a one-tap offer | One tap only when **every clause** of the offered text carries a business signal and none carries a personal signal: private words, a screen category, or first-person talk ("I", "I've", "my" + anything but a business noun). Otherwise step-up. Dialog reworded: "Check this is only business: one tap shares exactly this." | `test_review_n1_personal_sentences_never_get_a_one_tap_offer` (both review sentences, with the HTTP-equivalent refusal) | FIXED |
| **N-2** (LOW) feed truncated before the deny checks | `_check_text` runs `reject_private` and every deny pattern on the **full** value. An over-long value is refused (`over_length`), never cut | `test_review_n2_feed_validators_check_the_full_value_before_any_cut` (email, id and customer fragments straddling the cap) | FIXED |
| **S-1** (LOW) LAURACEO paid calls start on deploy | New owner switch `BRAMBLELOOP_LAURA_CEO_MODEL=1` (default OFF), checked in `laura_converse.available` and therefore by every Business Laura model path. While off, `/laura/converse` answers deterministically through `talk.converse`, and the tick keeps its deterministic order | `test_w4_laura_ceo.py::test_ceo_model_switch_off_makes_no_model_call` (converse, executive, tick, CC route; Anthropic `_send` records nothing) | FIXED |
| **S-4** (INFO) Venice card shown before selection; fixed model name | `credentials.state` omits Venice until `BRAMBLELOOP_PRIVATE_PROVIDER=venice`. PERMISSION advice names `venice.model(env)` | `test_review_s4_venice_card_only_when_selected_and_names_the_effective_model` | FIXED |
| **S-2** (LOW) rollback below this code drops the H-1/L-5 protections | Documented as a rollback caveat, below. The only code-level mitigation is a filter backported into older releases, which is out of this branch's reach | doc | DOCUMENTED |
| **Mixed messages** (owner directive) misleading approval text | Every offer carries a sealed `kind`: business, mixed, draft or personal. The wording is honest for each. Mixed: "Your message was partly personal. Only the part below would go…". Business: "Check this is only business". Draft: "my wording, not yours". Personal is the default. Overlapping text is never called business | `test_review_mixed_and_personal_offers_use_honest_wording` | FIXED |
| **N-3** (LOW) a step-up approved every pending offer for 5 minutes | An approval that needs step-up carries the owner's passphrase (and TOTP) **in the approval request itself**. It is verified for that action only: single use, and bound to that crossing. No session-wide window counts. A wrong credential counts as a failed step-up (401). UI: the share dialog asks for it | `test_review_l1_n3_approval_is_verified_for_this_exact_action` (an unrelated fresh step-up → 403; wrong → 401; with credentials → crosses) | FIXED |
| **N-4** (INFO) feed "sent" audit written before the call | The row is written only when the request actually left. It now records `outcome` (REPLIED, or the provider-side code); pre-call refusals write nothing | `test_review_n4_feed_audit_row_only_when_the_request_left` | FIXED |
| **N-5** (INFO) the crossed-row link was sealed after the business call | `crossed_ref` is sealed immediately after `boundary.record`, then `approval_turn`, then `business_ref` | `test_review_n5_the_crossed_row_link_is_sealed_before_the_business_call` (simulated crash; delete still redacts) | FIXED |
| **N-6** (INFO) a short private phrase blocked structured requests | Code-rendered requests are exempt from `short_exact`, because they hold no conversation text. The full guard still runs on history and on free text | `test_review_n6_a_short_private_phrase_does_not_block_a_structured_request` | FIXED |
| **N-7** (INFO) unreadable inbox reported as 0 | `open_owner_decisions` / `owner_decision_titles` are `null` (UNKNOWN) unless the inbox status is OK | `test_review_n7_unreadable_inbox_is_unknown_never_zero` | FIXED |
| **N-8** (INFO) redaction kept the text's sha256 | Redaction clears the hash too; the row and its time remain as proof | `test_review_n8_redaction_clears_the_text_hash_too` | FIXED |
| **N-9** (INFO) Anthropic and BFL API calls followed redirects | `AnthropicProvider._send` and BFL `_post`/`_get` open through `venice.no_redirect_opener()`. Unkeyed image downloads are unchanged | `test_w4_close5_vision_timeout`, `test_w4_fluxapi` (adapted to patch the opener); `test_review_m2_…` covers the handler | FIXED |
| **N-10** (INFO) the test dependency was missing from the lock | `requirements-test.lock` (httpx 0.28.1, httpcore 1.0.9, certifi; hashes from PyPI), installed after the production lock. The production lock is unchanged | — | FIXED |
| **N-11** (INFO) test quality | M-2: B binds `127.0.0.2`. L-1: no `if`. M-1: the real `_http` over loopback reads more than 2,000 bytes. pl_reply asserts on the **real Venice wire** (no tools, no stream, system then user, Venice system prompt off). The unified positive control checks the exact business purposes billed | `test_review_n11_real_http_reads_more_than_2000_bytes`, `test_w4_pl_reply`, the M-2 and L-1 tests | FIXED |
| **S-3** (INFO) feed preview needed no private grant | The preview route needs the live private grant, like the thread | `test_review_s3_feed_preview_needs_the_private_grant` | FIXED |
| **S-5** (INFO) harness refusal swallowed as PROVIDER_ERROR | The harness records every refused transport call and fails the test when its context closes | `test_review_s5_harness_fails_when_a_refused_transport_is_called` | FIXED |
| **S-6** (INFO) whole-file declaration also covered Venice | `test_cert_spend_hosts` adds an exact per-URL allowlist for `credentials.py` and `venice.py` | `test_free_check_and_transport_modules_address_only_their_allowlisted_urls` | FIXED |

### S-2 rollback caveat (operator steps)

Once the unified thread has been used, the encrypted store holds turns whose sealed `label` and `excluded` flags only this code honours. Older code (b997efd, b931d17) ignores them in its split private path. Its `forget` also leaves sealed crossing requests and crossed text behind.

Before rolling back below a release that contains this branch:
1. Turn the private register off: unset `BRAMBLELOOP_LAURA_PRIVATE_REGISTER`. The old split path then sends nothing.
2. While still on this code, delete (Laura view → select → Delete) any turn you do not want an older release to see. This also removes derived requests and redacts the crossed text.
3. Unset `BRAMBLELOOP_LAURA_UNIFIED` and `BRAMBLELOOP_LAURA_BUSINESS_TO_VENICE`.
4. Then roll back.

Do not re-enable the register on the older release until you roll forward again.

## 10c. Response to the review of f87e430 (NO BLOCKER)

| Finding | Fix | Test |
|---|---|---|
| **R-1** (LOW) one tap still possible for personal text with no first-person word or no clause break | Clauses now also split on commas and on "and"/"but"/"then". `me/we/us/our` (outside business nouns) and subject-dropped self-talk ("Can't sleep…", "Throwing up…") count as personal. The health screen adds fever, vomiting, sleep and similar; the relationship screen adds breakup, moved out, left me and similar | `test_review_n1_personal_sentences_never_get_a_one_tap_offer` (now includes the review's 3 PoC sentences) |
| **R-2** (LOW) briefing synthesis called Anthropic with the CEO switch OFF while the response said `not_called` | `laura_briefing.synthesize` is behind `BRAMBLELOOP_LAURA_CEO_MODEL` too. OFF means the deterministic briefing and no call, so `not_called` is now true. The briefing suites opt into ON for the model behaviour | `test_w4_laura_ceo.py::test_ceo_model_switch_off_makes_no_model_call` (adds two briefing questions with an Anthropic key set; no `_send`) |
| **R-3** (LOW) a feed sent by a reply that failed post-send reconciliation wrote no audit row | `ReplyUnavailable` carries `sent`, set by the reply path itself (post-send `BUDGET`, `MALFORMED`, `MODEL_MISMATCH` and provider failures are `sent=True`). The audit decision uses that flag, not a code list | `test_review_r3_feed_audit_row_written_when_reconciliation_fails_after_the_send` |
| R-10 (INFO) nits | `boundary.redact` docstring corrected. An offer overlapping *other* private turns is relabelled `personal`, whether it was business or mixed; its own source turn is not counted against it | the mixed-wording test |
| R-4..R-9 (INFO) | Not assigned in this round | OPEN (in the review file) |

## 10d. Response to the review of 2c29b42 (`INDEPENDENT_SECREVIEW_LAURAONE_2c29b42.md`, NO BLOCKER)

| Finding | Decision | Fix | Test (fails on 2c29b42, passes here) |
|---|---|---|---|
| **Q-1** (LOW) one tap for personal text joined by a dash, ellipsis, slash or "so" | **FIXED**, the robust way | One tap now also needs `business_grammar`: the whole offered text is ONE question or request (letters, digits, spaces, in-word hyphens and apostrophes, one optional terminal `?`/`.`) written entirely in a **closed business vocabulary** -- the structured renderer's metrics, date ranges, task objects and departments, the business nouns, question words, auxiliaries and function words, plus the company's own product slugs and titles. Any unknown word (a name, "grieving", "overdose") or any joining punctuation fails toward a step-up. Personal phrasings are not enumerated. As defence in depth `_CLAUSE` also splits on em/en dash, ` - `, `…`, `...`, `/`, `(` and so/because/since/while/after | `test_review_q1_one_tap_needs_the_closed_business_grammar`, `test_review_q1_clause_split_covers_dashes_slashes_brackets_and_conjunctions` |
| **Q-2** (INFO) the N-1 test lost `screen == []` | **FIXED** | The five screen-hitting samples are kept unchanged. A second set (`SCREEN_CLEAN_PERSONAL`, 17 sentences: every Q-1 and Q-2 sentence plus each named separator) asserts `screen == []`, `one_tap_business(text) is False`, step-up, kind `personal`, refusal of one-tap approval, and nothing reaching the business transport | `test_review_n1_personal_sentences_never_get_a_one_tap_offer` |
| **Q-3** (INFO) R-10 mixed→personal relabel untested | **FIXED** | none needed (code was right) | `test_review_q3_mixed_offer_overlapping_earlier_private_turn_is_relabelled_personal`: an earlier private turn, then a mixed turn quoting its words. Asserts `kind == "personal"`, step-up, no "stays between us"; a non-overlapping mixed control keeps the mixed wording. Fails when `private_context.py:574` is reverted to `kind == "business"` (scratch copy) |
| **Q-4** (INFO) R-3 `sent` over-reports pre-send failures | **FIXED** (cheap) | `reply` passes a `track` flag into `_reply`; it flips immediately before `provider._send` (after the budget, estimate and payload steps). The catch-all wrapper and the send-failure branch use it. A failure inside `_send` (DNS, refused connection) is still `sent=True`: it cannot be told apart from a request that left, so the audit still over-reports, never under. Runbook U8 now says `PROVIDER_ERROR` means "possibly sent" | `test_review_q4_no_feed_audit_row_when_the_wrapper_catches_a_pre_send_failure` |
| **Q-5** (INFO) OFF also makes the CEO briefing deterministic; OA-LCEO-1 did not say so | **FIXED** (documentation) | OA-LCEO-1 (§10) now names the model-synthesised briefing in its paths, cost and consequence, so setting the switch is a deliberate re-enablement | n/a (documentation) |
| **Q-6a** more step-ups for ordinary questions ("Show me sales…", "we/us" questions) | **ACCEPTED** | None. It fails safe (usability only), and the closed grammar makes one tap stricter still: any question outside the vocabulary needs a step-up. The owner still sees the exact text and can approve it with re-authentication. The vocabulary can grow by code review if real questions keep needing a step-up | — |
| **Q-6b** briefing suites set `BRAMBLELOOP_LAURA_CEO_MODEL=1` at module level | **ACCEPTED** | None. Each suite runs in its own process (`H.run`; no single-process runner or CI workflow exists), and the OFF proof in `test_w4_laura_ceo` pops the variable itself. Restoring it per test would add fixtures to three suites for a runner that does not exist. Revisit if a single-process runner is introduced | — |
| **Q-6c** `boundary.py:58` docstring over 100 characters | **FIXED** | Line re-wrapped | — |

## 10e. Response to the review of 3b9c4f5 (`INDEPENDENT_SECREVIEW_LAURAFIX_3b9c4f5.md`, NO BLOCKER)

| Finding | Decision | Fix | Test |
|---|---|---|---|
| **T-1** (LOW) product-title words were vocabulary one by one ("Is Rose going to make it to the launch?" with a "Rose Cardigan" product got one tap) | **FIXED** | `business_grammar` matches each product slug and title as a WHOLE phrase (words in order, spaces or hyphens, word boundaries, optional possessive), longest first, and replaces it with one placeholder token (`product`). Title words are never vocabulary on their own. One-word titles or slugs are ignored, because "Rose" alone is as likely a person; such questions need a step-up | `test_review_t1_product_titles_count_only_as_whole_phrases` (the report's Rose, Willow, "Grief Shawl for Mark" and "Mother's Day Blanket" sentences, plus a one-word title; product questions by whole title or slug keep one tap). Fails on 3b9c4f5 |
| **T-2** (INFO) open `\w*` suffixes (`priorit\w*`, `department\w*`, `launch\w*`, `deploy\w*`) | **FIXED** | `_GRAMMAR_FIXED` lists explicit inflections and no longer reuses `_BIZ_NOUN` | Four run-together tokens (incl. the report's `prioritiesmarkdied`, `departmentsarahleftme`) in `test_review_q1_one_tap_needs_the_closed_business_grammar`. Fails on 3b9c4f5 |
| **T-3** (INFO) `_FIRST_PERSON` unpinned | **FIXED** (test) | none (code was right) | `FIRST_PERSON_CLEAN` (the report's three "my" sentences plus one "our") in the N-1 test: each passes the screen and the grammar, and must still be refused end to end. Fails when `_FIRST_PERSON` is removed from `one_tap_business` (scratch copy) |
| **T-4** (INFO) the "may have left" direction of Q-4 unpinned | **FIXED** (test) | none (code was right) | `test_review_t4_a_failure_inside_the_send_counts_as_possibly_sent`: feed ON, Venice 503 inside `_send` → one `venice_context.sent` row with the transport code as `outcome`, and `exc.sent is True` directly. Fails when the flag is flipped after `_send` (mutation H, scratch copy) |
| **T-5** (INFO) minor | **FIXED** (NBSP, numbers, style) / **ACCEPTED** (vocabulary weight) | A space or NBSP before the terminal `?`/`.` is tolerated. Number tokens are only a count up to 99, an ordinal, a year `20xx` or `#1234` (so "Show sales 4821 at the shop." needs a step-up). Blank lines fixed. The emotionally weighted vocabulary words (night, worst, need, support…) are kept: each clause still needs a business word, nothing crosses without the owner's tap, and the list is reviewed whenever it grows | in the T-1 test |
| Integrator line (INTEG6b 1e44bd7) | **CARRIED** | The non-emptiness assertion before the Q-1 loop; the N-1 loop has one too | `test_vacuity` passes |

## 11. Not done / notes

- The four register strings were never edited here. They come from the owner's commit fcb2bcd, merged unchanged.
- ADD-LCONT-11 (production acceptance) is **OPEN**.
- Security review: a4a6841 is being reviewed independently. Everything from 3b7e6d0 onward needs the delta review.

## 12. Regression results (freeze 2026-10-21; focused suites via testslot at low priority; no full suite)

All suites exit 0. Where no count is shown, the suite printed no summary line but exited 0.

| Group | Suites |
|---|---|
| New | `test_w4_laura_unified` 53/53 |
| Laura, Venice and Private Laura | `test_w4_venice` 19/19, `test_w4_laura_ceo` 14/14, `test_w4_plact` 8/8, `test_w4_credhealth` 13/13; `pl_auth` 2/2, `pl_reply` 3/3, `pl_leak` 2/2, `pl_boundary`, `pl_budget`, `pl_continuity` |
| Private store and firewall | `test_cert_spend_hosts`; `priv_access`, `priv_continuity`, `priv_firewall`, `priv_leak`, `priv_provenance`, `priv_store` |
| Command Center Laura | `laura_cc_access` 5/5, `cc_delegation` 5/5, `cc_followon` 4/4, `cc_integration` 5/5, `cc_private` 7/7, `cc_providers` 7/7, `cc_talk` 9/9, `cc_wiring` 5/5; `laura_voice_spec` 7/7 |
| Security fixes and front end | `test_w4_integ3_secfixes`, `test_v11_pwa_static` 82/82, `test_w4_cc_company` 23/23 |
| Transports touched by N-9 | `test_w4_close5_vision_timeout`, `test_w4_fluxapi` 13/13, `test_w4_wraptest`, `test_w4_controlled_experiments` 10/10 |
| Required set | `test_w3_decision_index`, `test_vacuity`, `test_launch`, `test_cost_governance_wave2`, `test_search_hero_publish` 4/4, `test_cert_listing_frames`, `test_v11_autonomy_timeline` |

**Future work (not built).** Visual and voice Laura is not built here, and nothing in this branch precludes it:
- the persona (`laura-r2-a42aeac7`) and the continuity memory (the encrypted thread) are provider-independent;
- a voice or avatar surface would read the same thread through `private_context`, under the same boundary.
