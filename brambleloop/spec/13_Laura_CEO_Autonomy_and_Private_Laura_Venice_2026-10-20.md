# Owner rulings 2026-10-20: Laura as AI CEO (business) and Venice for Private Laura (MANDATORY additions to the final build)

These are addendum requirements. They ADD to Build 2 (320 rows) and the Final Master (917 rows); they do not replace or renumber
anything. Every existing owner-reserved approval, financial ceiling, publication gate, legal obligation and security control is
unchanged.

## A. Business Laura: Founder and AI CEO (reconciles with D-FB-13 / spec 07)

| ID | Requirement |
|---|---|
| ADD-LCEO-01 | Business Laura holds real model-backed conversation in the Command Center: greetings, contextual follow-ups, executive reasoning, company questions, recommendations, delegation. Deterministic templates are not conversation. |
| ADD-LCEO-02 | Factual business answers are grounded in authorised company records. Deterministic retrieval is an evidence tool for the model, not a replacement for it. |
| ADD-LCEO-03 | Durable, scoped conversational memory (business tier only). |
| ADD-LCEO-04 | Within existing authority, Laura sets priorities, assigns and coordinates agent work through the real job queue, reviews and rejects deliverables, monitors quality, marketing, finance and CX, starts approved corrective actions, evaluates experiments and opportunities, manages queues and resources, improves workflows only through Learn, and reports significant developments. She needs no routine owner instructions. |
| ADD-LCEO-05 | Cost-aware multi-model routing (Anthropic now; OpenAI, Venice and others only after verified availability, price, terms and retention AND owner approval of any new paid provider or credential). Cheap models for routine work, stronger models for hard reasoning, independent review for consequential decisions. Per-agent and company limits are kept. |
| ADD-LCEO-06 | Routine Business Laura conversation targets about CA$10–15/month inside existing limits. Cost is tracked per conversation, decision, delegated task and successful outcome. Budget increases go to the owner only with performance evidence. |
| ADD-LCEO-07 | CEO autonomy acceptance test, run in production with real model calls and real evidence. Laura must: (1) respond naturally to a greeting; (2) report accurate company status; (3) identify a genuine priority; (4) delegate an authorised task; (5) receive and evaluate the result; (6) request a correction when needed; (7) update the timeline and memory; (8) report the outcome and costs; (9) stop or ask for approval at a protected action. No templates or faked delegation count. |

## B. Private Laura on Venice AI (owner's final provider decision; supersedes the "keep Anthropic" provider choice for Private Laura only)

| ID | Requirement |
|---|---|
| ADD-PLV-01 | Private Laura uses Venice AI through its officially documented API. Model IDs, pricing, authentication, context limits, data retention and content policy are verified from official sources. The strongest suitable conversational model is chosen. A Pro subscription is not assumed to include API credit. |
| ADD-PLV-02 | *(Amended 2026-10-20 by the owner's final ruling, DECISION_LOG D-W4-PL-VENICE-ADULT. The original wording is quoted verbatim in §D below and in that entry's trace.)* Same canonical fictional Laura (laura-r2-a42aeac7) with her established warmth, affection, humour, flirtatious personality, initiative and continuity. For the one adult owner, the private register includes sexual discussion, explicit adult dialogue and consensual erotic roleplay (D-W4-PL-VENICE-ADULT). Never claims to be human; a clearly fictional adult AI. Not a generic assistant. A model is eligible by privacy class (Venice-hosted, Private, pinned price), not by its moderation label. Never: minors (including age-play or young-seeming framing), non-consent presented as endorsed or real, exploitation, real people's names, likeness or voice, impersonation, or anything unlawful. Venice's Terms, including its mature-content rules, are the outer limit and are never worked around. |
| ADD-PLV-03 | The existing encrypted private-memory architecture is reused. No private text in business memory, finance, marketing, product, agent records, analytics, ordinary logs or response caches. Only the minimum operational metadata is kept outside the encrypted store. Memory persists across restarts, redeploys and model changes. |
| ADD-PLV-04 | Owner-only access: existing owner authentication plus the additional private verification. Not reachable by employees, customers, other agents or public endpoints. Key rotation and access controls are kept. |
| ADD-PLV-05 | Separate CA$0.50/day budget inside the CA$100 month. Token usage and cost are tracked without private text in billing records. A different budget needs owner approval. |
| ADD-PLV-06 | The credential lives only in Railway variables. It is never requested in chat or Claude Code. |
| ADD-PLV-07 | Production acceptance test: (1) Venice authenticates via Railway; (2) a genuine model reply; (3) personality and continuity; (4) private-memory retrieval; (5) no leakage into business systems; (6) cost accounting; (7) the daily budget is enforced; (8) persistence across restart or redeploy; (9) owner-only access; (10) graceful failure when Venice is unavailable. Not complete until it passes in production. |
| ADD-PLV-08 | No activation, paid call or deploy without separate owner approval of the model and budget. The existing reply path, encryption, memory and CC screens are reused; there is no second private-chat system. |

## C. PROPOSED amendment to ADD-PLV-02 (2026-10-20, W4-VENICE). Superseded (historical)

> **Superseded (historical).** This proposal's eligibility rule is incorporated in the amended ADD-PLV-02 above
> (D-W4-PL-VENICE-ADULT). The text below is kept as the record of what was proposed.

The owner has clarified that "uncensored" must not be assumed to mean unsafe, and that legal, consent, privacy and
provider restrictions are never bypassed. The proposed wording, which replaces the sentence "Weaker moderation is
never used to bypass provider restrictions." only once approved:

> A model is eligible by **privacy class**: Venice Private (zero retention), verified from Venice's API metadata,
> with a pinned price. Eligibility does not depend on whether Venice labels the model "uncensored". A model's
> lighter moderation never bypasses the law, Venice's Terms, consent, privacy, or the pinned guardrails (adults
> only, fictional persona, no real-person likeness, nothing illegal). Anonymized models are never used.

The evidence and the model comparison are in `research/final_build/w4/VENICE.md` §9. ADD-PLV-02 as written above
remains binding until then.

## D. ADD-PLV-02 amended by the owner's FINAL RULING on adult conversation (2026-10-20)

**Status: IMPLEMENTED IN CODE, pending independent security review and ADD-PLV-07 production acceptance.**
- The owner's ruling and approvals are recorded in DECISION_LOG D-W4-PL-VENICE-ADULT, including the owner
  attestation.
- The four register copy edits passed Claude Code's permission review on the owner's explicit approval (fcb2bcd).
- Venice Terms §10.9(c): L1a, owner attestation, is RECORDED. L1b, documentary verification, is **NOT VERIFIED;
  the owner accepts it on attestation**. It is never reported as verified.
- Not complete until ADD-PLV-07 passes in production.

The original ADD-PLV-02, verbatim and superseded:

> Same canonical fictional Laura (laura-r2-a42aeac7) with her established warmth, affection, humour, flirtatious
> personality, initiative and continuity, within Venice's applicable rules. Never claims to be human. Not a
> generic assistant. Weaker moderation is never used to bypass provider restrictions. D-W4-PL-2 stays as recorded.

The history below records how the amendment was proposed. The full trace (original
against replacement) is DECISION_LOG `D-W4-PL-VENICE-ADULT`. The proposed binding wording is:

> ADD-PLV-02 (proposed): Same canonical fictional Laura (laura-r2-a42aeac7) with her established warmth, affection,
> humour, flirtatious personality, initiative and continuity. For the one adult owner, the private register
> includes sexual discussion, explicit adult dialogue and consensual erotic roleplay (D-W4-PL-VENICE-ADULT).
> Never claims to be human; a clearly fictional adult AI. Not a generic assistant. A model is eligible by privacy
> class (Venice-hosted, Private, pinned price), not by its moderation label. Never: minors (including age-play or
> young-seeming framing), non-consent presented as endorsed or real, exploitation, real people's names, likeness
> or voice, impersonation, or anything unlawful. Venice's Terms, including its mature-content rules, are the outer
> limit and are never worked around.

The model approval for `venice-uncensored-1-2` is owner-approved. It applies only while the model's verification
passes, and fails closed otherwise. It is implemented in `gateway/venice.py`.

## E. One Laura: conversational continuity (owner requirement 2026-10-20 and its clarification; D-W4-LAURA-UNIFIED)

**Status.** Rows 01–10, 12 and 13 are BUILT and offline-tested on `claude/w4-LAURAONE`. They are NOT deployed, so none is verified in production. ADD-LCONT-11 is OPEN. Evidence: `research/final_build/w4/LAURAONE.md`; `tests/test_w4_laura_unified.py`.

| ID | Requirement | Acceptance criteria | Status |
|---|---|---|---|
| ADD-LCONT-01 | One Laura, one thread. A single CC conversation with one session history and one persona (`laura-r2-a42aeac7`). She is a clearly fictional adult AI who never claims to be human. Claude and other models are business tools, not separate personalities. | With `BRAMBLELOOP_LAURA_UNIFIED=venice`, the Laura view shows one thread and the split routes answer 409. Both pinned prompts name the canonical identity and the AI clause. Switch off: behaviour unchanged. | BUILT, offline-tested |
| ADD-LCONT-02 | One encrypted conversation memory holds every turn regardless of topic. It provides continuity only and is never a company-memory database. | Every turn is in `laura_private_entries`, with its label sealed. No Base table, business module, department, analytics or executive path reads it. The thread survives a restart, a Venice model swap and a Claude tier change. | BUILT, offline-tested |
| ADD-LCONT-03 | Venice is Laura's conversational voice and decides when a business tool is needed (her intent). Every check stays deterministic and in code. | The router `laura.unified_intent@1` runs on Venice, billed to `laura_private`. Its tool comes from a fixed enum; unknown or malformed output is refused. Code builds or gates every brief. When the router is unreachable, code decides, and says so. | BUILT, offline-tested |
| ADD-LCONT-04 | Business reasoning tools (Claude via Business Laura, budget `laura`) receive only business-relevant context. Private content is excluded by default. | A leak guard (substring, normalised, 6-gram shingle and token overlap) checks the brief and the exact outbound request against every private turn and note. A hit means refused, not sent, and nothing persisted. | BUILT, offline-tested |
| ADD-LCONT-05 | Crossing the boundary needs the owner's explicit approval of the exact information. A brief Venice drafts is shown to the owner first. | The in-thread question shows the exact text. Approval needs a fresh step-up. One `laura_boundary_crossings` row holds the approved text only. Declined or pending requests never cross. A request resolves once. | BUILT, offline-tested |
| ADD-LCONT-06 | Private content never enters business tables, logs, audit, cost rows, the paid-call journal, analytics, the timeline, memory tiers, the continuity export, or delegated jobs, reviews, lessons and owner reports (channels a–e). | A sweep of a private, an adult and a mixed turn checks SQL parameters, logging, stdio, every Base table, the export and the outbound business payloads. A delegation and an executive tick are included. The `private_context` call site of Business Laura is statically guarded. | BUILT, offline-tested |
| ADD-LCONT-07 | Owner privacy controls: keep private, mark private, exclude from context, include again, and delete (real deletion). Key rotation keeps working. | Excluded turns leave Venice's context. Delete removes rows, replies and quoting crossing requests from the store and from later sealed exports. `rekey` preserves labels, flags and requests. | BUILT, offline-tested |
| ADD-LCONT-08 | Spending. Venice calls bill to `laura_private` (CA$0.50/day) and business tools to `laura` (existing allocations). There is a reservation before every call and no ceiling is raised. When a budget is exhausted, Laura says so, with no silent fallback; no path forwards thread history to Claude or GPT. | Tests check the agent per call, the reservation before each call, and that an exhausted budget means no call. Venice failures and an "anthropic" private provider send nothing to Anthropic. GPT is not wired. | BUILT, offline-tested |
| ADD-LCONT-09 | Owner-only access, with step-up as for the private context. | Anonymous requests get 401/403. An owner without an open private context gets 403. Opening needs a step-up, and so does approving a crossing. | BUILT, offline-tested |
| ADD-LCONT-10 | **Restricted business-context feed to Venice** (D-W4-LAURA-UNIFIED-FEED; design owner-approved 2026-10-20, activation needs separate approval, `BRAMBLELOOP_LAURA_BUSINESS_TO_VENICE`, OFF by default). Venice receives only a code-defined allowlist: company status, product progress, department activity, operational decisions and non-sensitive financial aggregates. It never receives credentials, customer PII, Etsy buyer data, messages, payment details, protected personal records or anything outside the declared scope. (The owner's own newest message is conversation, not company data: it always reaches Laura's router and reply on Venice, whatever its label; security review I-1.) | `laura/agency/venice_context.py`: every field has a name, type, declared source read function, size cap and sensitivity class. Deny-pattern validators fail closed (field dropped, recorded by name). The pack is capped at 3,000 bytes. An audit row holds sha256, names and counts with no values. The owner preview equals the payload. Switch off: nothing sent. Seeded PII, keys and private text never appear. | BUILT, offline-tested; activation awaits the owner (OA-LCONT-2) |
| ADD-LCONT-11 | PRODUCTION ACCEPTANCE: the runbook U1–U13 (LAURAONE.md §9: context feed preview / allowlist-only payload / value-free audit row, structured requests, the approval control, each leak path) in production after the owner approves deploy and activation. | All of U1–U13 pass with real model calls; evidence is row counts and status codes only. | **OPEN** |
| ADD-LCONT-12 | **Structured business requests by default.** A business tool receives a request rendered by code from the tool plus allowlisted parameters (metric ids, period, product ids, priority id, department, task object, count), extracted deterministically. It contains no conversation text. | The request equals the code rendering; the owner's words are absent from the outbound payload. A delegation with no allowlisted object is offered rather than sent. Mixed turns send nothing automatically. | BUILT, offline-tested |
| ADD-LCONT-13 | **Approval control.** Free text from the conversation, including the owner's own words, crosses only on the owner's explicit approval of the exact text. One tap is enough for her own business-classified words; step-up is required for anything else, including any text the leak guard finds overlapping private content. Marking an exchange private afterwards redacts the business records derived from it. | Each offer shows the exact text with `requires_stepup` and `overlaps_private`. A tap without the required step-up returns 403 `STEP_UP_REQUIRED` and nothing crosses. Approval writes one row holding the approved text only. Mark-private redacts the derived `laura_cc_turns` row and the crossing text. | BUILT, offline-tested |
