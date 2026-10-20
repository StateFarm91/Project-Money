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
| ADD-PLV-02 | Same canonical fictional Laura (laura-r2-a42aeac7) with her established warmth, affection, humour, flirtatious personality, initiative and continuity, within Venice's applicable rules. Never claims to be human. Not a generic assistant. Weaker moderation is never used to bypass provider restrictions. D-W4-PL-2 stays as recorded. |
| ADD-PLV-03 | The existing encrypted private-memory architecture is reused. No private text in business memory, finance, marketing, product, agent records, analytics, ordinary logs or response caches. Only the minimum operational metadata is kept outside the encrypted store. Memory persists across restarts, redeploys and model changes. |
| ADD-PLV-04 | Owner-only access: existing owner authentication plus the additional private verification. Not reachable by employees, customers, other agents or public endpoints. Key rotation and access controls are kept. |
| ADD-PLV-05 | Separate CA$0.50/day budget inside the CA$100 month. Token usage and cost are tracked without private text in billing records. A different budget needs owner approval. |
| ADD-PLV-06 | The credential lives only in Railway variables. It is never requested in chat or Claude Code. |
| ADD-PLV-07 | Production acceptance test: (1) Venice authenticates via Railway; (2) a genuine model reply; (3) personality and continuity; (4) private-memory retrieval; (5) no leakage into business systems; (6) cost accounting; (7) the daily budget is enforced; (8) persistence across restart or redeploy; (9) owner-only access; (10) graceful failure when Venice is unavailable. Not complete until it passes in production. |
| ADD-PLV-08 | No activation, paid call or deploy without separate owner approval of the model and budget. The existing reply path, encryption, memory and CC screens are reused; there is no second private-chat system. |
