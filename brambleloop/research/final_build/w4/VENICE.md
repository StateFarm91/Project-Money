# W4-VENICE: Private Laura on Venice AI

Branch `claude/w4-VENICE`, cut from `origin/claude/w4-INTEG4` @ 6531769 with `origin/claude/w4-BRANDRULE` @ eac52bb
merged in. That merge brings the binding owner ruling: `spec/13_…`, rows ADD-PLV-01..08 and DECISION_LOG
D-W4-PL-VENICE.

This file holds no private content and no key material. Variables are named here, never valued.

**Honest status.**
- The adapter and its tests are done on this branch.
- Nothing was deployed. No production variable was changed. No Venice key was created or handled.
- Nothing was spent: no paid call was made. Every Venice request in the tests goes to a mocked transport, and
  sockets are refused.
- The only network reads were to Venice's public documentation and its public, unauthenticated model list
  (`GET https://api.venice.ai/api/v1/models?type=text`).
- Production (b931d17, SHADOW) has no Venice code.
- Private Laura on Venice is **NOT complete**. It needs the owner actions in §6 and the 10-step production
  acceptance test in §5 (ADD-PLV-07).

---

## 1. Venice facts (official sources, read 2026-10-20 UTC)

A fact the official sources do not state is marked **UNKNOWN**.

| # | Fact | Value | Source |
|---|---|---|---|
| F1 | API base URL | `https://api.venice.ai/api/v1` | docs.venice.ai/overview/getting-started |
| F2 | Auth header | `Authorization: Bearer <VENICE_API_KEY>`. A key with no credentials returns 402 (a payment challenge), not 401. A key that is present but invalid returns 401. | docs.venice.ai/overview/getting-started; docs.venice.ai/api-reference/error-codes |
| F3 | OpenAI compatibility | "Venice is OpenAI-compatible, so you can use the OpenAI SDK." Chat: `POST /chat/completions`. Also `GET /models` (public), `GET /api_keys/rate_limits`, and `/responses`, embeddings, image and audio endpoints, which are not used here. | docs.venice.ai/overview/getting-started; docs.venice.ai/api-reference/endpoint/chat/completions; docs.venice.ai/api-reference/rate-limiting |
| F4 | Venice-specific request parameters | `venice_parameters.include_venice_system_prompt` **defaults to true**, which adds Venice's own system prompt next to ours. Others: `disable_thinking` (default false), `strip_thinking_response` (default false), `enable_web_search` (default "off"), `enable_web_scraping` / `enable_web_citations` (default false), `character_slug`, `enable_e2ee`. `reasoning_effort` takes none … max. `max_completion_tokens` caps visible output plus reasoning tokens. `max_tokens` is deprecated. | docs.venice.ai/api-reference/endpoint/chat/completions |
| F5 | Response usage | `usage.prompt_tokens`, `usage.completion_tokens` (which includes `completion_tokens_details.reasoning_tokens`), and a top-level `cost.usd` / `cost.diem` | same |
| F6 | Chat models and context | 137 text models are listed (public `GET /api/v1/models?type=text`, 2026-10-20). Each has a privacy class: **`private`** ("Zero data retention, contract-enforced") or **`anonymized`** (proxied to a third party; "Prompt content is still visible to that provider"). The proxied Claude, GPT, Gemini, Qwen-Max and Mercury models are **anonymized**. The candidates are in §2. | api.venice.ai/api/v1/models; docs.venice.ai/overview/models; docs.venice.ai/overview/privacy |
| F7 | Pricing model | USD per 1M tokens, per model: input, output, cache read and sometimes cache write. Some models charge more above a context threshold. Spend is drawn in this order: DIEM (1 DIEM = US$1/day of compute, refreshed daily), then earned credits, then bundled credits, then USD. **VCU is not mentioned** (UNKNOWN / not current). | docs.venice.ai/overview/pricing |
| F8 | Pro subscription and API | "A paid subscription does not include free or unlimited API usage." Pro, Plus and Max subscribers get a **one-time US$5 API credit** (not for VVV-staking upgrades) and a **US$1/month bundled-credit allowance**. Per ADD-PLV-01, Pro is **not assumed** to cover API use. | docs.venice.ai/overview/pricing |
| F9 | Minimum credit purchase; how USD credit is bought | **UNKNOWN**. The docs say only that the account "should have a spendable balance before calling paid endpoints"; balances show at venice.ai/settings/api. | docs.venice.ai/overview/guides/generating-api-key |
| F10 | Key options | Created at **venice.ai/settings/api** → Generate New API Key. Type **Inference Only** or Admin. Optional expiry. **Epoch Consumption Limits**: a per-key USD or DIEM cap per 24-hour epoch. The full key is shown only once. | docs.venice.ai/overview/guides/generating-api-key |
| F11 | Data retention, Venice | "Venice does not store or log prompt and response content for normal inference." Venice "may process metadata needed for authentication, billing, abuse prevention, reliability, analytics, and support." **Private** models: content "is processed for inference only and is not retained after the request completes", "Zero data retention, contract-enforced". No retention period is stated for metadata (**UNKNOWN**). | docs.venice.ai/overview/privacy; venice.ai/privacy |
| F12 | Data retention, third party | **Anonymized** models: "you should assume the provider is storing your content." | venice.ai/privacy |
| F13 | Training on content | Terms §10.2: Venice does "not use, any User Content to train any machine learning … algorithms". | venice.ai/legal/tos (last updated 2026-06-08) |
| F14 | Content policy (API) | Terms §12 prohibits: illegal use; abuse or exploitation of children, including CSAM (also AI-generated); "using in Input any third party's name, voice, image, or likeness without their consent"; "impersonating any person or entity, claiming a false affiliation or identity". §4 says users must not circumvent the mature-content filter. §9.3 and §10.3 refer to the third-party model providers' usage policies. The API returns `422 CONTENT_POLICY_VIOLATION` when a prompt "breaks the content policy of Venice or the model provider". Terms §10.11: Venice "reserves the right to … monitor". | venice.ai/legal/tos; docs.venice.ai/api-reference/error-codes |
| F15 | Rate limits (text) | Per model size, default / partner: XS 500 RPM, 5M TPM; S 150 RPM, 3M TPM; M and L 100 RPM, 2M TPM. Headers: `x-ratelimit-{limit,remaining,reset}-{requests,tokens}`. There is also an error budget: 50 failed requests per model per key in a rolling 30 s. `GET /api_keys/rate_limits` is "the canonical way to fetch your current limits". | docs.venice.ai/api-reference/rate-limiting |
| F16 | Error codes | 400 INVALID_REQUEST / INVALID_MODEL / TOO_MANY_TOKENS. 401 AUTHENTICATION_FAILED / …_INACTIVE_KEY / PRO_ONLY_MODEL. 402 INSUFFICIENT_BALANCE / API_KEY_{USD,DIEM}_SPEND_LIMIT_EXCEEDED. 403 UNAUTHORIZED / API_ACCESS_DISABLED (and IP-restricted keys). 404 MODEL_NOT_FOUND. 413 PAYLOAD_TOO_LARGE. 422 CONTENT_POLICY_VIOLATION. 429 RATE_LIMIT_EXCEEDED / MODEL_OVERLOADED. 500 INFERENCE_FAILED / UNKNOWN_ERROR. 503 MODEL_OFFLINE / MODEL_AT_CAPACITY. 504 REQUEST_TIMEOUT. | docs.venice.ai/api-reference/error-codes |
| F17 | Free auth/credit check | `GET /api/v1/api_keys/rate_limits` "Return[s] details about user balances and rate limits": `accessPermitted`, `balances.USD/DIEM/BUNDLED_CREDITS`, per-model RPM/RPD/TPM. It runs no inference. **Whether it is billed is UNKNOWN**, because the docs do not say. | docs.venice.ai/api-reference/endpoint/api_keys/rate_limits |

**Blocker review (D-W4-PL-VENICE says to look for alternatives only on a real blocker).** None found.
- **Technical.** The API is documented and OpenAI-compatible. Our own system prompt can be made the only one
  (`include_venice_system_prompt: false`).
- **Contractual.** The Terms prohibit using a real third party's likeness without consent and impersonating a
  person. Private Laura is the established, fictional AI persona laura-r2-a42aeac7 (D-W4-PL-3: "not an
  impersonation of a real person"). The pinned prompt forbids claiming to be human, and the request carries
  no real person's image or voice. That is compatible.
- **Security.** The pinned model is `private` (zero retention, contract-enforced), and the key stays in
  Railway.
- **Watch item, not a blocker.** Venice's privacy statements carry no retention period for metadata (F11), and
  Terms §10.11 reserves monitoring. This is recorded, not hidden.

## 2. Chosen model and expected cost

**Recommendation (subject to owner approval, ADD-PLV-08): `zai-org-glm-5-2` (GLM 5.2).** Facts from the
public model list on 2026-10-20:
- privacy class `private`;
- Venice's own `default` trait;
- context 1,000,000 tokens; maximum completion 131,072;
- **US$1.40 / 1M input, US$4.40 / 1M output** (cache read US$0.26);
- reasoning model, `reasoningEffortOptions: none, high, max`, **default effort `max`**.

Why this model, from the documented candidates, for natural, warm and consistent persona dialogue at a
reasonable cost:

| Model (private class unless noted) | In / out US$ per 1M | Context | Why not chosen |
|---|---|---|---|
| **zai-org-glm-5-2** (default) | 1.40 / 4.40 | 1M | **chosen.** Venice's general flagship ("improved instruction following", multilingual). Its reasoning can be switched off (`none`), so a reply is a reply and costs what it should. |
| z-ai-glm-5-3 | 1.75 / 5.50 | 1M | Newer, but described as tuned for "software engineering and long-horizon agent tasks". Reasoning effort cannot be set (`supportsReasoningEffort: false`), so reasoning tokens could not be controlled. |
| grok-4-7 (`most_intelligent`) | 2.27 / 6.80 | 500K | About 1.6x the cost, and its reasoning effort only goes down to "low". |
| kimi-k3 (`default_reasoning`) | 3.75 / 18.75 | 1M | About 3x the cost; a coding/agentic reasoning model. |
| hermes-3-llama-3.1-405b | 1.10 / 3.00 | 128K | An older (Llama 3.1) persona fine-tune; weaker instruction following, and its "steering" focus is a risk to the truthful-AI clauses. |
| venice-uncensored-role-play, venice-uncensored-1-2 | 0.50 / 2.00, 0.20 / 0.90 | 128K | **Excluded by ADD-PLV-02**: "Weaker moderation is never used to bypass provider restrictions." |
| claude-*, openai-gpt-*, gemini-* on Venice | various | various | **Excluded**: privacy class `anonymized`. The upstream provider sees the private text (F12). The code refuses them (`venice.PRIVATE_MODELS`). |

Dialogue quality cannot be measured without a paid call, which is not allowed before owner approval. Step 3 of
the acceptance test (§5) is where the owner judges personality and continuity live. If GLM 5.2 falls short,
the alternative to put to the owner is `grok-4-7`, which is also private class. Changing the model is a
one-line pin plus a price-table row, and it again needs the owner's approval.

**Cost per reply** (GLM 5.2, reasoning off; FX CA$1.4154/US$, from `core.fx`, Bank of Canada 2026-10-16; the
pinned system prompt is about 2,370 characters, roughly 600 tokens):

| Reply shape | Input tokens | Output tokens | US$ | **CA$** | **Replies in CA$0.50/day** |
|---|---|---|---|---|---|
| Short exchange | 900 | 80 | 0.00161 | 0.0023 | 219 |
| **Typical** (prompt + a few notes + recent turns) | 1,500 | 150 | 0.00276 | **0.0039** | **127** |
| Long context (20 notes, 12 long turns) | 4,000 | 300 | 0.00692 | 0.0098 | 51 |
| Worst case (output at the 400 cap) | 6,000 | 400 | 0.01016 | 0.0144 | 34 |

- **Pre-call reservation.** The reservation is deliberately pessimistic: characters/3 for tokens, the
  400-token output cap, and 1.25 padding. A typical turn reserves about CA$0.0085; a 12,000-character context
  reserves about CA$0.015. The reservation is released down to the actual bill as soon as Venice answers.
- **Monthly.** CA$0.50/day is at most **CA$15/month**, about US$10.60, inside the CA$100 month. At 20 typical
  replies a day it is about CA$2.35/month.
- **Comparison.** The same typical reply on the previous transport (claude-sonnet-5) was about CA$0.0096, so
  Venice/GLM 5.2 is about 2.4x cheaper per reply.

## 3. What was built (reusing the one Private Laura reply path)

Paths are relative to `brambleloop/src/brambleloop/`.

| Item | Where |
|---|---|
| **Venice transport.** `VeniceProvider`: pinned `MODEL = "zai-org-glm-5-2"`; a price table limited to `private`-class models; `payload()` sends `include_venice_system_prompt: false`, web search, scraping and citations off, `reasoning_effort: "none"` plus `disable_thinking`, `max_completion_tokens` = 400, no tools and no stream; `headers()` sends `Authorization: Bearer …`; `_post` is the only network call; `_read` handles usage, `cost.usd`, `<think>` stripping and finish "length" → truncated. | `gateway/venice.py` |
| **Railway variable names.** `VENICE_API_KEY`, read at call time from the environment only and never logged, stored or put in an exception. `BRAMBLELOOP_PRIVATE_PROVIDER`: **unset = OFF** (no provider, no reply); `venice` = Venice; `anthropic` = the pre-ruling transport, only as an explicit owner choice. | `gateway/venice.py` (`KEY_ENV`, `PROVIDER_ENV`, `selected`) |
| **Price table and atomic reservation.** `venice.estimate_for` prices the call from the Venice table (read 2026-10-20). The existing `anthropic.check_budget_cad(..., agent="laura_private", agent_daily_cap_cad=owner figure)` reserves it under `budget_lock`, so the month, the `laura_private` day (CA$0.50) and the reservation are one atomic step. The bill is `max(tokens × price, Venice's own cost.usd)`. | `gateway/laura_register.py` `_reply` |
| **Pinned prompt.** `laura.private_reply@1` is unchanged: the canonical identity laura-r2-a42aeac7 and the truthful-AI clauses. It is sent as the **only** system message (Venice's own prompt is turned off). | `gateway/laura_register.py` `_system`, `PROMPT` |
| **Classified errors and graceful failure.** One attempt, with no retry and no fallback to another provider. The fixed codes are `PROVIDER_AUTH` (401/403), `PROVIDER_CREDIT` (402, including the per-key spend cap), `PROVIDER_POLICY` (422 CONTENT_POLICY_VIOLATION), `PROVIDER_RATE_LIMITED` (429), `PROVIDER_UNREACHABLE` (5xx, unreachable, timeout) and `PROVIDER_ERROR` (other 4xx). The owner sees "I can't reach my private model right now … No reply was generated." Only a whitelisted Venice error **code** survives; the body is discarded. A 504 or socket timeout is billed at the reservation estimate (whether it billed is UNKNOWN, never zero). Declined 4xx/5xx are not billed and the reservation is released. | `gateway/venice.py` `classify`, `reply_code`; `gateway/laura_register.py` `REASONS`, `_sanitised` |
| **Billing holds tokens and cost only.** It uses the existing `ModelGateway._record` (provider `venice`, model, purpose, tokens, CAD, estimate, latency). There is no prompt and no reply in it. | `gateway/model_gateway.py` (unchanged) |
| **Status prerequisite.** `private_provider_venice` is met only when `BRAMBLELOOP_PRIVATE_PROVIDER=venice` and `VENICE_API_KEY` is present (names only). The status endpoint now lists 6 prerequisites. | `app/command_center/private_context.py` `prerequisites` |
| **CREDHEALTH: Venice.** `GET /api/v1/api_keys/rate_limits` (Bearer) proves the key authenticates and reads the **balance**, so credit is proven rather than assumed. The balance is INSUFFICIENT_CREDIT below one reply; `accessPermitted=false` or a 403 is PERMISSION. **Its cost is UNKNOWN** (F17), so it is recorded as `estimate_cad: null` with an `UNKNOWN` basis, never 0, and Venice is **checked only once the owner selects it**. Until then there is no request, no record and no card. | `gateway/credentials.py` `check_venice`, `check_all` |
| **Spend-host pin.** `api.venice.ai` was added to the paid-host scanner, and `gateway/venice.py` is declared. `gateway/credentials.py` was also declared: it had been undeclared since W4-CREDHEALTH, so this test **failed on INTEG4**, and that was verified. | `tests/test_cert_spend_hosts.py` |

## 4. Privacy analysis (ADD-PLV-03)

**What Venice receives:** one HTTPS POST per owner turn, made only from the owner-private context
(`private_context._laura_reply` → `laura_register.reply`). It contains:
1. the pinned system prompt (no private content); and
2. one user message, built by `render_user`, with three delimited data blocks:
   - the owner's private notes (at most 20);
   - the most recent private turns (at most 12);
   - the newest message.

Nothing from the company goes with it: no business memory, finance, catalogue, agents or timeline. The test
asserts the request holds exactly `[system, user]`, three blocks, and none of the seeded business records.
There are no tools, no web search and no Venice character.

**Where private text lives:**
- Only in the encrypted private store (`laura_private_*` tables; `laura/private/crypto.py`).
- In the owner's no-store POST response body.
- In transit to Venice. On a `private`-class model, Venice retains nothing after the request (F11).

**What is kept outside the encrypted store (metadata only):**
- The cost row: provider, model, purpose, tokens, CAD, estimate, latency, reservation id.
- The reservation row: amount, purpose, model.
- The model-attempt health row: `venice:<model>`, ok/kind, and a label such as `VeniceTransient 503
  MODEL_AT_CAPACITY`.
- The `spend.refused` audit row: figures and fixed text.
- The credential-health audit row: status, http status, balance figures, a 4-hex rotation marker.

**Proved absent** by `tests/test_w4_venice.py::test_venice_receives_only_the_private_turn_and_nothing_private_leaks_anywhere`:
- Business memory, finance, marketing, product, agent records, analytics and the timeline: every Base table is
  dumped and searched, including `cost_entries`, `audit_log`, `company_memory`, `company_timeline` and
  `paid_call_records`.
- Ordinary logs: the root logger at DEBUG, plus stdout and stderr.
- SQL bound parameters: every statement is watched.
- The response cache and the paid-call journal: the task is `cacheable=False` and the call is direct, never
  `_guarded`; `paid_call_records` = 0.
- The continuity export.

This holds for successful replies, for a provider error whose body carries a sentinel, and for a timeout. The
existing suites still pass: `test_w4_pl_leak` (business surfaces under an SQL watch never touch
`laura_private_*`) and `test_w3_priv_leak`.

**Residual risks (stated, not hidden):**
- Venice processes metadata for billing and abuse prevention, with no stated retention period (UNKNOWN).
- Terms §10.11 reserves the right to monitor.
- TLS terminates at Venice. This model has no TEE or E2EE; `e2ee-glm-5-2-p` exists if the owner later wants
  hardware attestation, at US$1.75/US$5.75.

## 5. PRODUCTION ACCEPTANCE TEST runbook (ADD-PLV-07)

Run this only after the owner actions in §6 and an owner-approved deploy of a release that contains this
branch. Record only pass/fail, status codes, row counts and figures, **never conversation content**. Every
step is on the production web service (brambleloop-os). Private Laura is complete only when all 10 pass in
production.

| # | Check (ADD-PLV-07) | How | Pass when |
|---|---|---|---|
| 1 | Venice authenticates via Railway | Command Center → Checks → Credentials → "Check now" (the `ops.provider_credentials` job). | Venice shows **OK**, with a balance at or above the credit you bought and a fingerprint whose last 4 characters match your key. Private card: "Activation prerequisites: 6 of 6 met". |
| 2 | Genuine model reply | Open the private context (step-up), then send one message. | `reply_status: REPLIED` and `model_ref` = `venice/zai-org-glm-5-2`. A Laura turn appears in the private view. |
| 3 | Personality and continuity | Send 3–5 turns that refer back to earlier ones. Run the owner checklist in PRIVLAURA.md (identity, register, never claims to be human, no invented history, business requests pointed to Talk to Laura). | The owner judges each item pass or fail. |
| 4 | Private-memory retrieval | Add a private note with "remember", then ask something that needs it. | The reply uses the note. |
| 5 | No leakage into business systems | Check Ask Company, Talk to Laura, the timeline, notifications, Money and the logs (Railway → Logs, search a distinctive word from your private message). | The word appears nowhere outside the private view. |
| 6 | Cost accounting | Money → spend by agent. | `laura_private` shows cost rows with provider `venice`, tokens and CA$ amounts, about CA$0.004 for a typical reply, and no text. |
| 7 | Daily budget enforced | Temporarily set `BRAMBLELOOP_LAURA_PRIVATE_DAILY_CAD=0.001`, send one message, then restore `0.50`. | The reply is `UNAVAILABLE` with reason `SPEND_CEILING` and **no** new cost row; a `spend.refused` audit row exists. |
| 8 | Persistence across restart or redeploy | Railway → brambleloop-os → Restart (or the next deploy), then reopen the private context. | Every earlier turn and reply is still there, and a new reply still sees them. |
| 9 | Owner-only access | From a private window with no session, open `/api/cc/private/status` and `/api/cc/private/view`. Also try from an owner session **without** step-up. | 401 or 403 in every case; no content. |
| 10 | Graceful failure when Venice is unavailable | Temporarily set `VENICE_API_KEY` to an invalid value (for example, add one character), send a message, then restore the real value. | `UNAVAILABLE`, reason `PROVIDER_AUTH`, the text "I can't reach my private model right now …", **no** fake reply, **no** Anthropic call (no `anthropic` cost row for `laura_private`), and the credential check shows REJECTED until restored. |

## 6. EXACT OWNER ACTIONS to activate (phone-friendly)

Do them in order. Never paste a key into chat or Claude Code: it goes only into Railway (ADD-PLV-06).

1. **Approve the model and the budget** (CA$0, 1 min). Reply: "Approve Venice zai-org-glm-5-2 for Private
   Laura at CA$0.50/day." This is required by ADD-PLV-08.
2. **Buy Venice API credit** (**US$10**, about CA$14.15, 3 min). Go to venice.ai → sign in → Settings → **API**
   (venice.ai/settings/api) → add USD API credit. US$10 covers a month at the full CA$0.50/day cap (about
   US$10.60) or about 3,600 typical replies. The minimum purchase is UNKNOWN in the docs. Do not count on the
   Pro one-time US$5 credit (F8).
3. **Create the API key** (CA$0, 2 min). Same page → **Generate New API Key**:
   - Description: `brambleloop-private-laura`.
   - Type: **Inference Only**.
   - No expiry, or one you will diarise.
   - **Epoch Consumption Limits: USD 0.36 per epoch**. This is a provider-side backstop about equal to
     CA$0.50/day; the code ceiling still governs.
   - Copy the key once.
4. **Set the key in Railway** (CA$0, 2 min). Railway → project → **brambleloop-os** (the web service) →
   Variables → New Variable → name `VENICE_API_KEY`, value = the key → Add. Railway redeploys the same build.
5. **Existing Private Laura prerequisites**, in the same Variables screen, if not already done (PLACT.md):
   - **a.** `BRAMBLELOOP_PRIVATE_MEMORY_KEY` = 32 random bytes in base64, generated on your own machine:
     `python3 -c "import secrets,base64;print(base64.b64encode(secrets.token_bytes(32)).decode())"`.
     Keep an offline copy. If it is lost, the private store is lost. (CA$0, 5 min.)
   - **b.** `BRAMBLELOOP_LAURA_PRIVATE_DAILY_CAD` = `0.50`. (CA$0.50/day at most, 1 min.)
   - **c.** `BRAMBLELOOP_LAURA_PRIVATE_REGISTER` = `1`. Acknowledge D-W4-PL-1 first. (CA$0, 1 min.)
6. **Select Venice** (CA$0, 1 min). Add `BRAMBLELOOP_PRIVATE_PROVIDER` = `venice`. This is the switch, and it is
   OFF until you set it.
7. **Approve the deploy** of the release that contains `claude/w4-VENICE`, which the integrator merges and
   certifies (CA$0, 2 min). Then run §5. It costs at most a few cents, inside the CA$0.50/day.

**If you wait:** Private Laura keeps storing your words encrypted and replies `UNAVAILABLE`
(`PROVIDER_NOT_SELECTED` or another gate). Nothing is spent, and no other provider is used.

## 7. Tests

All runs used the gate `/home/user/bl-runs/testslot.sh` on 2026-10-20, on SQLite, with no network. The results
are in the section below.
