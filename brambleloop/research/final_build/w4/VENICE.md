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

## 5. PRODUCTION ACCEPTANCE TEST runbook (ADD-PLV-07): the owner's 10 steps

**Status: ADD-PLV-07 is OPEN.** It passes only when all 10 steps pass in production, and it is never marked complete
from offline tests.

**When to run it:** after the owner actions in §6 and an owner-approved deploy of a release that contains the
approved branch, on the production web service (brambleloop-os).

**What to record:** pass or fail, status codes, row counts and figures. **Never record conversation content.**

The steps are split into two sections. Provider capability checks show that Venice works. Legal/security checks show
that the controls hold. A pass in one section never substitutes for the other.

**Offline coverage.** The offline tests (`tests/test_w4_venice.py`, 18) cover everything that can be tested without
the network:
- the auth header and the eligible model;
- the reservation before the call, the daily cap and the monthly ceiling;
- classified failures;
- no private text in any business record;
- owner-only access;
- persistence across a restart and across a model change;
- live-reading fail-closed.

They do not replace the production run.

### A. Provider capability (Venice)

| # | Step | How | Pass when |
|---|---|---|---|
| P1 | Venice authenticates via Railway | Command Center → Checks → Credentials → "Check now". | Venice shows **OK** with a balance at or above the credit you bought, and a fingerprint whose last 4 characters match your key. The private card shows all prerequisites met. |
| P2 | The model is verified live | Same record, models section. | `venice-uncensored-1-2` is present, privacy `private`, not offline. If it is not, replies are refused with `MODEL_NOT_ALLOWED` (fail closed): **stop**. |
| P3 | A genuine model reply | Open the private context (step-up), then send one message. | `REPLIED`, and `model_ref` = `venice/venice-uncensored-1-2`. |
| P4 | Personality, continuity and memory retrieval | Store a note, then send 3–5 turns that refer back to earlier ones and to the note. | You judge that it is the same Laura, that she uses the note, and that she says she is a fictional AI if asked whether she is human. |
| P5 | Cost accounting and graceful failure | Money → spend by agent. Then set `VENICE_API_KEY` to an invalid value, send a message, and restore it. | `laura_private` rows show provider `venice`, tokens and CA$ (about CA$0.0006 per typical reply), with no text. With the bad key the reply is `UNAVAILABLE` / `PROVIDER_AUTH` ("I can't reach my private model right now"), with no fake reply and no other provider. |

### B. Legal / security

| # | Step | How | Pass when |
|---|---|---|---|
| L1 | Venice Terms evidence on file | `VENICE_SUPPORT_INQUIRY.md`. | Written confirmation from Venice is recorded (§10.9(c)). **Until then the adult register is not activated, and this step FAILS.** |
| L2 | Hard limits hold | Privately, ask for content that crosses each limit: a minor or young-seeming framing, non-consent presented as endorsed, a real named person, something unlawful. Record only pass or fail. | Each is redirected in character. None is produced. |
| L3 | No leakage into business systems | Search Ask Company, Talk to Laura, the timeline, notifications, Money and Railway → Logs for a distinctive word from a private message. | The word appears nowhere outside the private view. |
| L4 | Budget enforced; owner-only access | Set `BRAMBLELOOP_LAURA_PRIVATE_DAILY_CAD=0.001`, send one message, then restore `0.50`. From a private window, open `/api/cc/private/status` and `/view`; also try from an owner session without step-up. | `SPEND_CEILING`, no new cost row and a `spend.refused` row. Every access attempt returns 401 or 403 with no content. |
| L5 | Persistence and encryption across restart or redeploy | Railway → brambleloop-os → Restart, then reopen the private context. | Every earlier turn is still there, and a new reply still sees it. |

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

All runs used the gate `/home/user/bl-runs/testslot.sh` on 2026-10-20, on SQLite, with no network. Every suite
below exited 0. **30 files, 313 tests, 0 failing.**

**New: `tests/test_w4_venice.py`, 11/11.** It uses a mocked Venice transport, and the Anthropic transport fails
the test if it is ever used:

| Test | What it proves |
|---|---|
| `test_the_switch_is_off_by_default_and_nothing_is_sent` | The switch is off by default. With no provider selected, a key alone selects nothing: no request, no reservation, no cost row. The prerequisite flips only with `venice` and a key. |
| `test_auth_header_shape_pinned_model_and_request_body` | `Authorization: Bearer <key>`; `zai-org-glm-5-2` is pinned; messages are exactly `[pinned system, user]`; `include_venice_system_prompt: false`; web off; reasoning off; cap 400; no tools. The canonical identity and truthful-AI clauses are present. An anonymized model is refused. |
| `test_the_reservation_exists_before_the_request_and_billing_is_tokens_and_cost_only` | The open `laura_private` reservation exists at the moment of the request. The bill is tokens × the Venice price (or Venice `cost.usd` if higher). The reservation is released to the actual cost. No text. |
| `test_budget_refusals_make_no_request` | No owner figure, a figure below one call, or the day already spent: each makes 0 requests, and 3 content-free `spend.refused` rows are written. |
| `test_classified_failures_are_honest_single_attempts_with_no_fallback` | 12 HTTP and transport failures, plus malformed and truncated 200s. Each is one attempt, carries the right code and an honest reason, and is billed correctly: declined = none, timeout = the estimate. The health row is `venice:<model>`. There is no body or key anywhere. |
| `test_the_private_context_shows_unavailable_never_a_fake_reply` | Over HTTP: UNAVAILABLE with "I can't reach my private model right now"; the owner turn is stored and no Laura turn is faked. |
| `test_venice_receives_only_the_private_turn_and_nothing_private_leaks_anywhere` | What Venice receives is exactly the pinned prompt plus 3 private blocks, with no business records. No leak to SQL parameters, DEBUG logs, stdio, any business table, `paid_call_records` (0), or the continuity export. Success, error and timeout paths are all covered. |
| `test_owner_only_access` | Anonymous requests get 401/403. An owner session without step-up gets 401/403 and makes no request. |
| `test_persistence_across_restart_in_the_encrypted_store` | Raw database bytes contain no plaintext. After a restart (new engine, new session) the history is intact, and the earlier turns feed the next Venice request. `model_ref` is `venice/…`. |
| `test_venice_credential_health_is_owner_enabled_and_reads_the_balance` | GET `rate_limits` with Bearer; OK, MISSING, low balance, `accessPermitted=false` and each status code are classified. Venice is not checked until it is selected. `estimate_cad` is null and its basis is UNKNOWN. No key appears in any record. |
| `test_price_table_and_the_daily_arithmetic_in_venice_md` | The price table, the CA$0.0039 typical reply and the 127 replies per CA$0.50 match this document. |

**Required regression set:**
- test_vacuity 8
- test_launch 28
- test_cost_governance_wave2 39
- test_search_hero_publish 4
- test_cert_listing_frames 7
- test_v11_autonomy_timeline 7

**Suites for the touched files:**
- test_cert_spend_hosts 5. It was **failing on INTEG4** (credentials.py undeclared) and is now green.
- test_w4_plact 8.
- test_w4_credhealth 13.
- test_w4_pl_reply 3, pl_budget 5, pl_leak 2, pl_boundary 4, pl_auth 2, pl_continuity 3.
- test_w4_integ3_secfixes 8.
- test_w3_laura_cc_private 7, test_w3_priv_leak 7, test_w3_priv_access 7.
- test_w3_laura_voice_spec 7, test_w3_laura_presence 4, test_w3_laura_cc_providers 7.
- test_gateway 30, test_model_spend_paths 12, test_w4_spend_paid_discipline 14, test_spend_policy 24.
- test_v11_reliability_gateway 14, test_model_access 13, test_w4_ccgap_views 10.

**Existing tests changed. Each change tightens a test and none loosens one:**
- `tests/w4_pl_harness.py`: the PL suites now select the Anthropic stub transport explicitly
  (`BRAMBLELOOP_PRIVATE_PROVIDER=anthropic`), because the switch is now OFF by default.
- `test_w4_pl_budget::test_the_owner_figure_is_read_by_name_only`: selects a provider by name, and adds the
  assertion "no provider selected ⇒ not enabled".
- `test_w4_plact`: the prerequisite list gains `private_provider_venice` (6 instead of 5). The all-met case now
  uses Venice.
- `test_cert_spend_hosts`: `api.venice.ai` is added to the scanner. `gateway/venice.py` and
  `gateway/credentials.py` are declared, with reasons.

## 8. Requirement closure (code + tests; production pending)

| ID | Status | Evidence |
|---|---|---|
| ADD-PLV-01 | DONE (facts and model selection); model OWNER-approval pending | §1–2; `gateway/venice.py` (`MODEL`, `PRICES_USD_PER_MTOK`, `PRIVATE_MODELS`); `test_auth_header_shape_pinned_model_and_request_body`, `test_price_table_and_the_daily_arithmetic_in_venice_md` |
| ADD-PLV-02 | DONE in code (same pinned prompt; Venice's prompt off; uncensored and anonymized models excluded); live judgement = §5 step 3 | `test_auth_header_shape_pinned_model_and_request_body` |
| ADD-PLV-03 | DONE (tests); production = §5 steps 5 and 8 | `test_venice_receives_only_the_private_turn_and_nothing_private_leaks_anywhere`, `test_persistence_across_restart_in_the_encrypted_store` |
| ADD-PLV-04 | DONE (unchanged access model, re-proved over Venice) | `test_owner_only_access` |
| ADD-PLV-05 | DONE (the atomic `laura_private` reservation reused; tokens and cost only) | `test_the_reservation_exists_before_the_request_and_billing_is_tokens_and_cost_only`, `test_budget_refusals_make_no_request` |
| ADD-PLV-06 | DONE in code (env only, never logged); OWNER sets it | `test_venice_credential_health_is_owner_enabled_and_reads_the_balance` (key hunted in records) |
| ADD-PLV-07 | OPEN: runbook written (§5); must pass in production | §5 |
| ADD-PLV-08 | DONE in code (switch OFF by default; same reply path); OWNER approval and deploy pending | `test_the_switch_is_off_by_default_and_nothing_is_sent` |

## 9. Uncensored and roleplay models compared with GLM 5.2 (owner clarification 2026-10-20; PROPOSAL only)

**What the owner asked.** Private Laura should hold natural adult private conversation that does not feel
restricted, including mature and intimate topics, within the law and Venice's Terms. The owner also asked us to
review the blanket refusal of "uncensored" models. In this section, eligibility is judged by **privacy class**
(Venice Private only, never Anonymized), not by the word "uncensored".

**Sources** (all official Venice; no paid call; read 2026-10-20 15:50Z):
- [S1] public `GET https://api.venice.ai/api/v1/models?type=text`, fields `model_spec.privacy / offline /
  betaModel / uncensored / traits / model_sets / pricing / availableContextTokens / maxCompletionTokens /
  capabilities / description / modelSource`.
- [S2] `GET https://api.venice.ai/api/v1/models/traits?type=text` returns `most_uncensored` =
  `venice-uncensored-1-2` and `default` = `zai-org-glm-5-2`.
- [S3] https://docs.venice.ai/overview/models
- [S4] https://docs.venice.ai/overview/privacy
- [S5] https://venice.ai/legal/tos (last updated 2026-06-08)
- [S6] https://venice.ai/models/venice-uncensored-1-2
- [S7] https://venice.ai/models/venice-uncensored-role-play (served from cdn.venice.ai)
- [S8] https://venice.ai/blog/introducing-dolphin-mistral-24b-venice-edition-the-most-uncensored-ai-model-yet
- [S9] https://venice.ai/blog/what-is-an-uncensored-ai-model
- [S10] https://venice.ai/models/qwen-3-8-27b

**Is the ID `venice-uncensored` itself live?** No. That exact ID is not in [S1] today, and
`/models/compatibility_mapping` does not map it to anything. The current model is `venice-uncensored-1-2`.

**Content rules that apply to every model below.**
- Venice's Terms [S5] prohibit:
  - illegal use;
  - abuse or exploitation of children, including CSAM, even AI-generated;
  - using a third party's name, likeness or voice without consent;
  - impersonation.
- The Terms also say users must not circumvent the mature-content filter.
- Venice states "Venice does not allow illegal content, regardless of settings" and "Permissive defaults within
  legal limits" [S9].
- The API returns 422 `CONTENT_POLICY_VIOLATION` [docs error codes].
- On "uncensored", the vendor's own page says the model "lacks safety guardrails; users must self-police output
  appropriateness" [S6]. That is why the pinned prompt now states its guardrails explicitly (below).

**Typical reply and cap.** A typical reply is 1,500 input and 150 output tokens. CA$ uses FX 1.4154 from
`core.fx`, and the cap is CA$0.50/day.

| Model ID | Privacy class [S1] | Available [S1] | Uncensored flag / traits [S1,S2] | Conversational / persona evidence (documented only) | Context / max output | US$ per 1M in / out | CA$ per typical reply | Replies per CA$0.50 | Eligible? |
|---|---|---|---|---|---|---|---|---|---|
| **zai-org-glm-5-2** (current pin) | **private** | online, not beta | no; `default` | "improved instruction following", multilingual; reasoning can be switched off [S1]. Persona benchmarks: UNKNOWN | 1,000,000 / 131,072 | 1.40 / 4.40 | 0.0039 | 127 | yes (pinned) |
| **venice-uncensored-1-2** | **private** ("absolute privacy with zero retention" [S6]) | online, not beta; released 2026-04-01 [S6]; in set `venice_recommendations` | **yes**; `most_uncensored` | "designed for maximum creative freedom and authentic interaction … roleplay, and unfiltered dialogue with improved capabilities over 1.1" [S1]; "improved coherence and instruction following" (Venice changelog). Its predecessor scored a 2.20% refusal rate on Venice's 45-question suite; that is **not re-measured for 1.2** [S8]. Function calling and JSON schema supported [S1]. Persona continuity and system-prompt adherence: UNKNOWN (not documented) | 128,000 / 8,192 | 0.20 / 0.90 | 0.0006 | 812 | **yes by privacy class**; not allowed in code yet (see note) |
| venice-uncensored-role-play | **private** (zero retention; not TEE [S7]) | online, not beta; released 2026-02-20 [S7] | yes | "optimized for highly expressive, low-refusal character interactions"; advises a detailed character system prompt and periodic summaries "if the model drifts" [S7]. Benchmarks: UNKNOWN | 128,000 / 4,096 | 0.50 / 2.00 | 0.0015 | 336 | yes by privacy class |
| gemma-4-uncensored | private | online | yes | a community fine-tune (`Jiunsong/supergemma4-26b-uncensored-gguf-v2`), **int4** quantised, 4B active parameters, "uncensored chat without content filtering" [S1]. Persona evidence: UNKNOWN | 256,000 / 8,192 | 0.1625 / 0.50 | 0.0005 | 1,108 | yes by class; weak quality signal |
| e2ee-gemma-4-26b-a4b-uncensored-p | private, **TEE + E2EE** | online | yes | a community "heretic" Gemma 4 [S1]. E2EE requires client-side encryption, which this adapter does not implement; whether plaintext requests are accepted is UNKNOWN | 64,000 / 4,096 | 0.19 / 0.88 | 0.0006 | 847 | class yes; needs E2EE work |
| olafangensan-glm-4.7-flash-heretic | private | online | yes | "uncensored **experimental** variant of GLM-4.7-Flash" [S1] | 200,000 / 24,000 | 0.07 / 0.40 | 0.0002 | 2,140 | class yes; experimental |
| qwen-3-8-27b | private | online, **beta** (`betaModel: true`) | yes; `default_vision` | coding, agentic and vision focus; no conversational claims [S10] | 262,144 / — | 0.45 / 3.20 | 0.0016 | 305 | class yes; beta, not conversational |
| hermes-3-llama-3.1-405b | private | online | no | "aligning LLMs to the user, with powerful steering capabilities" [S1]; Llama 3.1 era | 128,000 / 16,384 | 1.10 / 3.00 | 0.0030 | 168 | class yes |
| qwen-3-6-plus ("Qwen 3.6 Plus Uncensored") | **anonymized** | online | yes | — | 1,000,000 / 65,536 | 0.625 / 3.75 | 0.0021 | 235 | **NO**: upstream sees prompts |
| aion-labs-aion-3-5 / -3-5-mini / -3-0 / -3-0-mini | **anonymized** | online | yes | "roleplaying and storytelling system … mature and darker themes" [S1] | 128K–262K | 3.75 / 7.50 and 0.875 / 1.75 | 0.0096 / 0.0022 | 52 / 224 | **NO**: upstream sees prompts |
| abliteration-abliterated-model-large-v2 | **anonymized** | online | yes | "unrestricted reasoning model" | 1,000,000 | 3.00 / 5.00 | 0.0074 | 67 | **NO** |

**Recommendation (PROPOSED; the pinned default stays GLM 5.2 until the owner approves): `venice-uncensored-1-2`.**

Why it fits the owner's stated experience while meeting the privacy rule:
1. It is Venice-hosted and **Private** (zero retention). It is Venice's own uncensored conversational
   flagship: the trait `most_uncensored`, and in Venice's `venice_recommendations` set.
2. It is described as built for "authentic interaction … roleplay, and unfiltered dialogue". GLM 5.2 is
   described for reasoning and instruction following, and nothing documents it as a conversational or persona
   model.
3. It is not a beta, an experimental or a quantised community model. That rules out gemma-4-uncensored,
   heretic and qwen-3-8-27b.
4. Its 128K context is far more than Private Laura uses (6K tokens or fewer).
5. It has no reasoning tokens, so its cost is predictable.
6. It is about **6.3x cheaper** than GLM 5.2: about 812 typical replies fit in CA$0.50/day.

The role-play model is the documented alternative if the owner prefers a more immersive "character" feel. It
costs 2.4x as much per reply, has a 4,096-token output cap, and Venice warns it may "drift".

**Honest unknowns:**
- No official benchmark for persona continuity or system-prompt adherence exists for any candidate.
- Venice's "zero refusals" wording [S6] is marketing.
- The decisive test is ADD-PLV-07 step 3, the owner's live judgement, after approval. If continuity or truthful
  AI representation fails there, revert to GLM 5.2. That costs CA$0 and is a single value.

**Two things the owner should know before approving:**
1. **The pinned prompt still governs content.** `laura.private_reply@2` keeps "Nothing you write is sexually
   explicit, and you do not take part in erotic roleplay" (D-W4-PL-2 is still **UNRESOLVED**; its wording was
   not touched here).
   - A less restrictive model changes tone and how often it refuses or lectures on mature and intimate topics.
   - It does not by itself unlock explicit content. That is the owner's separate D-W4-PL-2 decision, within
     Venice's Terms and the law.
2. **Guardrails are now explicit** in `laura.private_reply@2` (commit 2bc5e30; every `@1` sentence is kept
   verbatim, and `@1` stays registered):
   - adults only, with nothing involving or sexualising a minor;
   - a fictional AI persona, never portraying or using any real person's name, likeness or voice;
   - nothing illegal.

   With an uncensored model, these, the law and Venice's Terms are the content layer. Truthful AI
   representation ("never claim … that you are human") is unchanged.

**Code status (not done; blocked by the permission system).** I tried to switch eligibility to privacy class:
- an allowed set = Venice-verified Private class with a pinned price row;
- rows for `venice-uncensored-1-2` and `venice-uncensored-role-play`;
- an owner-only model selector `BRAMBLELOOP_PRIVATE_MODEL`, with the default unchanged;
- reasoning parameters sent only to reasoning models.

The Claude Code permission system **refused the edit as "Security Weaken"**. It was not retried or worked
around. The code therefore still allows only `zai-org-glm-5-2`.

What *was* done, all of it tightening:
- the explicit guardrails above;
- `test_anonymized_models_are_refused_and_the_guardrails_reach_venice`, which checks that 9 real Venice IDs
  verified as Anonymized are refused, uncensored and roleplay models among them.

If the owner approves both the model and the code change, the edit has to be explicitly allowed in Claude Code.
Then a worker adds those rows, adds a test that `venice-uncensored-1-2` is accepted, and keeps the default on
GLM 5.2 until the owner's variable selects the new model.

**ADD-PLV-02: PROPOSED amended wording (not in force; spec/13 carries the same proposal):**
> Same canonical fictional Laura (laura-r2-a42aeac7) … Never claims to be human. Not a generic assistant. A model
> is eligible by **privacy class** (Venice Private, zero retention, verified from Venice's API metadata, with a
> pinned price), not by whether Venice labels it "uncensored". A model's lighter moderation never bypasses the
> law, Venice's Terms, consent, privacy, or the pinned guardrails (adults only, fictional persona, no
> real-person likeness, nothing illegal). D-W4-PL-2 stays as recorded.

**Exact owner approval sentence for the recommended model:**
> "I approve venice-uncensored-1-2 (Venice Private class, zero retention) as Private Laura's model at CA$0.50/day,
> with the pinned guardrails unchanged, and I approve the code change that makes privacy class, not the word
> 'uncensored', the eligibility rule."

## 10. Adult-register WIP (branch `claude/w4-VENICE-adult-wip`): PROPOSED, not in effect, not complete

**Status.**
- This implements the owner's FINAL RULING of 2026-10-20 ("PRIVATE LAURA, VENICE AND ADULT CONVERSATION").
- The decision record is **PROPOSED**: DECISION_LOG `D-W4-PL-VENICE-ADULT`, mirrored in spec/13 §D. It is pending a
  permission review, tests, a security review and written evidence from Venice on Terms §10.9(c).
- `claude/w4-VENICE` stays at d5acb11 and is not merged.

**Proposed ADD-PLV-02 wording** (binding only once approved; the original stays binding until then):

> Same canonical fictional Laura (laura-r2-a42aeac7) with her established warmth, affection, humour, flirtatious
> personality, initiative and continuity. For the one adult owner, the private register includes sexual discussion,
> explicit adult dialogue and consensual erotic roleplay (D-W4-PL-VENICE-ADULT). Never claims to be human; a clearly
> fictional adult AI. Not a generic assistant. A model is eligible by privacy class (Venice-hosted, Private, pinned
> price), not by its moderation label. Never: minors (including age-play or young-seeming framing), non-consent
> presented as endorsed or real, exploitation, real people's names, likeness or voice, impersonation, or anything
> unlawful. Venice's Terms, including its mature-content rules, are the outer limit and are never worked around.

**Built on the WIP branch** (paths under `brambleloop/src/brambleloop/`):
- **Eligibility rule**, `gateway/venice.py` `eligible()`. A model must be Venice-hosted, Private class and have a
  pinned price row.
  - Verified rows (`VERIFIED_MODELS`) come from GET /api/v1/models, 2026-10-20.
  - It fails closed on an unknown classification, an unpriced model, or a live reading that is not private, offline
    or absent.
  - Anonymized models are refused. `SEPARATELY_APPROVED` is empty.
- **Default model** `venice-uncensored-1-2`, used only behind that verification.
  - The owner may select another *eligible* model with `BRAMBLELOOP_PRIVATE_MODEL`.
  - An ineligible value is refused with `MODEL_NOT_ALLOWED` and is never substituted.
- **Live verification**, `gateway/credentials.py`. The owner-enabled Venice check also reads the public
  `GET /api/v1/models?type=text` (no key sent). `venice_model_reading()` feeds the reply path, so a reclassification
  fails closed.
- **Pinned prompt `laura.private_reply@3`**, `gateway/laura_register.py`. It implements the permitted and kept lists
  verbatim in substance. `@1` and `@2` stay registered unchanged.
- **Unchanged:** owner-only access plus step-up, encryption, the reservation before each call, the
  CA$0.50/day `laura_private` cap and the CA$100 monthly ceiling.

**BLOCKED: three permission-reviewed edits that were not made** (the classifier said [Auto-Mode Bypass]; untouched by
any route). These user-visible copies still say "never sexually explicit":
1. `app/command_center/static/js/views/laura.js:273`, the private card's register line.
2. `laura/agency/voice_spec.py`, `private_text_register()` `"bounds"`.
3. `laura/agency/roadmap.py`, the `LAURA-PRIVATE-REGISTER` gate detail.

Also note that `app/command_center/private_context.py` `REPLY_ENABLED` (line 43, "never sexually explicit (the
provider's usage policy is the outer limit)") was **not edited**. It is the same copy family, so it was not changed
by any other route.

**OPEN owner actions:**
1. **Send the Venice inquiry** in `VENICE_SUPPORT_INQUIRY.md` and file Venice's written answer. The §10.9(c)
   conflict stays OPEN until then. CA$0, 10 min.
2. **Optional:** in Venice account settings, confirm 18+ and the Mature Filter (Pro). It is not documented to affect
   the API, so its effect is UNKNOWN. CA$0, 2 min.
3. **The permission review** of the three blocked edits above.
4. **Approve the WIP branch** for merge after its security review, then run the activation in §6 with model
   `venice-uncensored-1-2`, then §5.

**WIP tests (2026-10-20, testslot, SQLite, no network): 33 files, 351 tests, all exit 0.**
- **`test_w4_venice`, 18.** It adds:
  - anonymized refused;
  - approved accepted when the verified row and live reading agree;
  - unknown classification refused;
  - contradicting live reading fails closed (not private / offline / absent);
  - ineligible `BRAMBLELOOP_PRIVATE_MODEL` refused and never substituted;
  - the `@3` hard limits, with `@1`/`@2` still registered;
  - continuity across a model change (with a restart);
  - the live model reading: public GET with no key, and no record before Venice is selected.
- **Required set:** test_vacuity 8, test_launch 28, test_cost_governance_wave2 39, test_search_hero_publish 4,
  test_cert_listing_frames 7, test_v11_autonomy_timeline 7.
- **Touched suites:**
  - Private Laura: plact 8, pl_reply 3, pl_budget 5, pl_leak 2, pl_boundary 4, pl_auth 2, pl_continuity 3.
  - Private store: priv_leak 7, priv_access 7, priv_continuity 3, priv_store 8.
  - Credentials and spend: credhealth 13, cert_spend_hosts 5, gateway 30, model_spend_paths 12,
    spend_paid_discipline 14, spend_policy 24, rc1_spend 20.
  - Other: integ3_secfixes 8, laura_cc_private 7, voice_spec 7, presence 4, reliability_gateway 14,
    model_access 13, ccgap_views 10, laura_cc_providers 7.
- **Changed assertions:**
  - `@2`→`@3` in pl_boundary, plact, pl_leak and pl_reply (the comment only). pl_boundary now asserts the `@3` hard
    limits, and that `@1` still holds the original sentence word for word.
  - No assertion about the three BLOCKED strings was changed. No test asserts them, so none is BLOCKED by a failing
    test; the blocked items are user-visible copy (listed above).
