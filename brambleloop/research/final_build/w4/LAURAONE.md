# W4-LAURAONE: one Laura, one thread (conversational continuity)

Owner requirement 2026-10-20 ("LAURA CONVERSATIONAL CONTINUITY"). Rows: ADD-LCONT-01..10 (`spec/13`). Decision: D-W4-LAURA-UNIFIED.
Branch `claude/w4-LAURAONE` = `origin/claude/w4-LAURACEO` (a3eec7b) + `origin/claude/w4-VENICE-adult-wip` (98110d8).
Not deployed. No paid call, no key, no Railway change. Everything new is OFF by default.

## 1. Architecture

```
owner (CC Laura view, one thread)  --POST /api/cc/laura/unified/*-->  private_context.unified_*   (owner session + private grant from a fresh step-up)
   1. record the owner turn in the ENCRYPTED private store (every turn, every topic), with a label
   2. classify (deterministic, gateway/laura_unified.classify): business | private | everyday | mixed (+ sensitive)
   3a. private / everyday  -> Venice via the ONE existing private reply path (laura_register.reply, laura.private_reply@3, laura_private budget)
   3b. business            -> brief = the business question only -> LEAK GUARD vs private store -> Business Laura (ceo_chat.converse, Claude, laura budget)
   3c. mixed, or a brief the guard stops -> Laura asks in-thread "Can I share this with the business side?" showing the exact text; nothing is sent
   4. Laura's reply (from whichever side) is recorded in the same encrypted thread; the business side keeps only brief + result
```

- **One thread, one memory, one persona.** Every turn lives in `laura_private_entries` (AES-GCM; existing store, extended with a sealed label, an exclude flag and a sealed crossing-request kind). The same Laura (`laura-r2-a42aeac7`) on both sides: Business Laura's pinned persona and Private Laura's pinned prompt both name the canonical identity, an AI that never claims to be human.
- **Venice is the conversational layer for everything that is not business work.** Business answers are never rewritten by Venice: deterministic validation of figures and citations wins, and a rewrite could change a figure. They are delivered verbatim in the thread.
- **One endpoint.** With the switch on, `/api/cc/laura/converse` and `/api/cc/private/turn` answer 409 `UNIFIED_THREAD`, so no second, disconnected conversation can grow. With it off, nothing changes.
- **Classifier.** Deterministic word lists only. A Venice-side classifier was rejected: it would send business-labelled text to Venice when `BUSINESS_TO_VENICE` is off, and it costs money every turn. Ambiguous (no signal) is `everyday`, which is treated as private, so it fails toward privacy. The owner can force a turn private (`private: true`).

## 2. Privacy boundary: data flow

| Data | Venice (private provider) | Claude (Business Laura) | Business tables / logs / cost rows / timeline / export | Encrypted private store |
|---|---|---|---|---|
| Private or everyday owner turn, and Laura's Venice reply | yes, recent non-excluded turns (≤12) and notes (≤20) as context | **never**: leak guard, refused, not sent | **never** | yes |
| Business owner turn (the brief) | only if `BUSINESS_TO_VENICE=1`; otherwise a content-free placeholder turn | yes, the brief only | `laura_cc_turns` (brief + result) | yes |
| Business evidence (talk.converse pack, briefing pack) | only as it appears in a validated answer, and only if `BUSINESS_TO_VENICE=1` | yes (existing) | existing business records | no (only the validated answer) |
| Business Laura's validated answer | only if `BUSINESS_TO_VENICE=1` | n/a | `laura_cc_turns`, `laura_cost_events` | yes |
| Mixed turn | yes (it is private conversation) | only the exact approved text, after an owner approval with step-up | `laura_boundary_crossings`: approved text + sha256 only | yes, plus the sealed request |
| Pending or declined crossing text | n/a | never | never | sealed |
| Billing | tokens + cost, agent `laura_private` | tokens + cost, agent `laura` | `cost_entries`, `spend_reservations`, `audit_log` (no content) | — |

GPT/OpenAI: **not wired**. Text to OpenAI needs a separate owner approval and a terms review (D-W4-LAURACEO-ROUTE). It is an option only.

**Leak guard** (`gateway/laura_unified.leak_check`; deterministic, it wins):
- **What it checks.** Before any business call it checks the brief, and then the full outbound payload (pinned system prompt + rendered user message). It checks them against every non-business turn, both owner and Laura, and every private note.
- **How it matches.** Three ways: an exact substring (≥12 chars), a normalised substring (NFKC, casefold, punctuation folded, whitespace collapsed, ≥3 words), and any shared 6-word shingle.
- **What it allows.** Text the owner has already approved to cross is allow-listed.
- **When it hits.** The call is refused and nothing is sent. Laura asks in-thread to share the overlapping text.

## 3. Memory tiers

| Tier | Holds | Where |
|---|---|---|
| Thread (all topics) | every owner and Laura turn, label, exclude flag | encrypted `laura_private_entries` (kind `turn`) |
| Private notes | owner-supplied facts | encrypted (kind `fact`), unchanged |
| Crossing requests | the exact text proposed to cross, status | encrypted (kind `xing`) |
| Business conversation | business briefs + Business Laura's results | `laura_cc_turns` (unchanged table) |
| Business memory | owner-stated business preferences | `laura.memory` relationship tier (unchanged, `reject_private` firewall) |
| Crossed text | approved text only | `laura_boundary_crossings` (new business table) |

Continuity across restarts and model changes holds because the conversation lives in the database, not in a model. A Venice model swap (`BRAMBLELOOP_PRIVATE_MODEL`) or a Claude tier change reads the same rows. Key rotation (`store.rekey`) re-seals labels, flags and crossing requests unchanged.

## 4. Cost attribution

- **Venice turns.** Billed to `laura_private`: CA$0.50/day, the owner's `BRAMBLELOOP_LAURA_PRIVATE_DAILY_CAD` tightens it, inside the CA$100 month. The atomic reservation happens before the request, through the existing path.
- **Business turns.** Billed to `laura`: CA$0.50/day, with the existing converse 8% and executive 5% purpose stops, and the reservation before the request.
- **Cost estimate.**
  - About CA$0.0006 per Venice reply (VENICE.md §9).
  - About CA$0.002–0.02 per business turn (LAURACEO.md).
  - The estimate is unchanged. No limit is raised.
- **When a budget is exhausted.** Laura says so in the thread (`SPEND_CEILING` / "refused by the spend controls"). There is no fallback to another provider in either direction.

## 5. What Venice receives (evaluated against VENICE.md)

Venice receives one OpenAI-compatible `POST /chat/completions` per non-business turn:
- the pinned `laura.private_reply@3` system prompt (unchanged);
- the owner's notes, up to 20;
- the recent non-excluded turns, up to 12;
- the new message.

Venice's own system prompt, web search and scraping are off. There are no tools.

| Venice as primary layer | Verdict |
|---|---|
| Private class, zero retention, contract-enforced (F11) | documented; pinned model `venice-uncensored-1-2` verified Private |
| Server-side conversation state / threads | **UNKNOWN** (not documented); not used. Continuity is ours, stateless per request |
| Context 128K / output 8,192 for `venice-uncensored-1-2` | documented; we send ≤ ~6K tokens |
| Metadata retention period | **UNKNOWN** (F11) |
| Terms §10.9(c) vs adult content | owner attestation recorded (D-W4-PL-VENICE-ADULT); register copy BLOCKED (below) |
| Persona continuity / system-prompt adherence benchmarks | **UNKNOWN** (not documented); production acceptance only |
| Cost to verify the key (`rate_limits`) | **UNKNOWN** (F17) |

Venice is fit as the primary conversational layer for private and everyday conversation. It is not fit as the reasoning layer for business facts: it has no evidence tools and no figure validation. That is why business work stays on Business Laura.

## 6. Owner switches (all default OFF)

| Switch | Effect |
|---|---|
| `BRAMBLELOOP_LAURA_UNIFIED=venice` | One thread in the CC; old split routes answer 409. Unset or any other value means today's behaviour |
| `BRAMBLELOOP_LAURA_BUSINESS_TO_VENICE=1` | Business briefs and validated answers enter Venice's context. A new company-data flow to a new provider, so it needs a separate owner approval (OA-LCONT-2) |
| Shared with Private Laura | `BRAMBLELOOP_PRIVATE_MEMORY_KEY`, `BRAMBLELOOP_LAURA_PRIVATE_REGISTER=1`, `BRAMBLELOOP_PRIVATE_PROVIDER=venice`, `VENICE_API_KEY`, `BRAMBLELOOP_LAURA_PRIVATE_DAILY_CAD`, deployed release |
| Per-turn controls (owner, in-thread) | keep private (force label), mark private, exclude from context, include again, forget (a turn or a range) |

## 7. BLOCKED / not done here

- The four register strings (`laura.js:273`, `voice_spec.py` `private_text_register` "bounds", `roadmap.py` `LAURA-PRIVATE-REGISTER` detail, `private_context.py` `REPLY_ENABLED`) are untouched. They are pending the owner's own commit. The unified thread uses the private reply path's register exactly as it stands.
- Marking a business turn private afterwards does not erase the business record already made from it. It does stop all later use: the guard then treats its text as private.
- Production acceptance (ADD-LCONT-10) stays OPEN.
