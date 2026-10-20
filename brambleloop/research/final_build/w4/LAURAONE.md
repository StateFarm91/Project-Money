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
| U8 | **Feed on** (OA-LCONT-2, after approval): send one message | One `laura.venice_context.sent` row whose sha256 equals the preview's, holding names and counts and **no values**; Venice replies with company awareness |
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
| OA-LCONT-4 | Approve deploy of a release with this branch, after integration and the independent security review (a4a6841 under review; a delta review covers this revision) | No deploy without approval | CA$0 | 5 | Nothing reaches production |

## 11. Not done / notes

- The four register strings were never edited here. They come from the owner's commit fcb2bcd, merged unchanged.
- ADD-LCONT-11 (production acceptance) is **OPEN**.
- Security review: a4a6841 is being reviewed independently. Everything from 3b7e6d0 onward needs the delta review.

## 12. Regression results (2026-10-20, revision 3dc3ced; focused suites via testslot; no full suite)

All 40 suites exited 0. Where no count is shown, the suite printed no summary line but exited 0.

| Group | Suites |
|---|---|
| New | `test_w4_laura_unified` 26/26 |
| Laura, Venice and Private Laura | `test_w4_venice` 19/19, `test_w4_laura_ceo` 13/13, `test_w4_plact` 8/8, `test_w4_credhealth` 13/13; `pl_auth` 2/2, `pl_leak` 2/2, `pl_reply` 3/3, `pl_boundary`, `pl_budget`, `pl_continuity` |
| Private store and firewall | `test_cert_spend_hosts`; `test_w3_priv_access`, `priv_continuity`, `priv_firewall`, `priv_leak`, `priv_provenance`, `priv_store` |
| Command Center Laura | `w3_laura_cc_private` 7/7, `cc_access` 5/5, `cc_followon` 4/4, `cc_talk` 9/9, `cc_wiring` 5/5, `cc_integration` 5/5; `laura_memory_isolation`, `laura_core_continuity`, `laura_voice_spec` 7/7 |
| Security fixes and front end | `test_w4_integ3_secfixes`, `test_v11_pwa_static` 82/82, `test_cert_mjs`, `test_w4_mjs_findings`, `test_w4_mjscount` 5/5, `test_w4_cc_company` 23/23 |
| Required set | `test_vacuity`, `test_launch`, `test_cost_governance_wave2`, `test_search_hero_publish` 4/4, `test_cert_listing_frames`, `test_v11_autonomy_timeline`, `test_w3_decision_index` |
