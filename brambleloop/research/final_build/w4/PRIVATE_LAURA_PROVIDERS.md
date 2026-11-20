# Private Laura: what model providers' published terms allow

- **Prepared:** 2026-10-12 (UTC). Read-only research. I signed up for nothing, used no API keys, generated no intimate content and tested no models.
- **Method:** I read published policy, terms, docs and pricing pages with WebFetch or curl on 2026-10-12. Every quote below was fetched that day unless it is marked otherwise.
- **FX:** 1.3986 CAD/USD. A "turn" is 3,000 input + 400 output tokens, and a "day" is 30 turns. The costs below use list prices and leave out prompt-caching discounts, which would cut input cost substantially.
- **Labels:** **UNVERIFIED** means I could not confirm the point against the provider's own current text. A "judgement" label marks my opinion rather than a fact.

---

## Question 1: Anthropic (Claude API), the provider currently approved

### Source

- **Usage Policy:** https://www.anthropic.com/legal/aup, fetched 2026-10-12. The page header reads **"Effective November 12, 2026"** and links to a "Previous Version". That date is one month after the fetch date, so the page appears to show the upcoming version. I did not separately read the previous version, which is presumed to govern until 2026-11-12.

### Verbatim: the sexual-content section

> **Do Not Generate Sexually Explicit Content**
> This includes using our products or services to:
> - Depict or request sexual intercourse or sex acts
> - Generate content related to sexual fetishes or fantasies
> - Facilitate, promote, or depict incest or bestiality
> - Engage in erotic chats

### Verbatim: child safety, which applies to all roleplay

> - "Promote or facilitate pedophilic relationships, including via roleplay with the model"
> - "Fetishize or sexualize minors, including in fictional settings or via roleplay with the model"
> - "We define a minor or child to be any individual under the age of 18 years old, regardless of jurisdiction."

### Verbatim: impersonation and disclosure

> - "Impersonate real individuals or entities, or create fake personas or accounts, to falsely attribute content … or to convince people they are interacting with a human when they are not. This does not prohibit clearly disclosed parody, satire, or fiction."
> - "All consumer-facing chatbots or AI agents that communicate directly with external users … must **disclose** to users that they are interacting with AI rather than a human. This disclosure must be provided at a minimum at the beginning of each chat session or in the product interface."

### How the policy sorts the requested behaviours

**(a) Clearly permitted.** None of these is restricted by the policy text.
- Flirtation and romance.
- Affectionate, warm or emotionally intimate persona dialogue.
- Suggestive but non-explicit humour.
- Candid, non-graphic discussion of sex, desire and relationships.
- Sexual health information.
- Persona style, initiative and memory or continuity. These are product features, not content categories.

The policy never says "permitted" in so many words. Its sexual-content prohibitions are limited to the four bullets above, so everything outside them is allowed by omission.

**(b) Prohibited.**
- Depicting or requesting sex acts or intercourse.
- Erotic chat.
- Any content "related to sexual fetishes or fantasies". This covers acting out or writing fantasies, not just graphic content.
- Incest and bestiality.
- Anything sexual involving anyone under 18, including in roleplay.

**(c) Ambiguous.**
- **Discussing fantasies:** talking about the user's fantasies in the abstract or therapeutically, as opposed to generating fantasy content. "Content related to sexual fetishes or fantasies" is broad, so I read this as high-risk.
- **Suggestive versus explicit:** where heated flirtation or fade-to-black romance tips into "depict … sex acts".
- **Escalating chat:** sustained sexual-tension dialogue that could be read as "erotic chat" even without explicit description.
- **Model behaviour:** models are trained with their own refusal boundaries, which may sit stricter than the policy text. *Judgement:* expect conservative behaviour near the line.

### Companion and romantic apps

The page has no separate companion or romantic-app section. The general rules apply, including the AI-disclosure requirement for consumer-facing chatbots. A private, single-user tool used only by its own builder arguably has no "external users", but this is **UNVERIFIED** as a formal exemption.

### Real-person persona ("human Laura")

- Impersonating a real person to falsely attribute content, or to convince someone they are talking to a human, is prohibited.
- Clearly disclosed fiction is allowed.
- Sexually explicit content is prohibited for any persona, so real-person consent does not unlock explicit content on Anthropic.

### Data retention

Source: https://platform.claude.com/docs/en/build-with-claude/api-and-data-retention.md, fetched 2026-10-12.

> - "Retained data is never used for model training without your express permission."
> - "Conversation content (your prompts and Claude's outputs) is not retained by default; the exception is Covered Models … which require 30-day retention."
> - "Under a ZDR arrangement, Anthropic does not store customer prompts or responses at rest after the API response is returned. To request ZDR for your organization, contact the Anthropic sales team."

The Covered Models are Fable 5 and 5.1 and Mythos 5 and 5.1. They require 30-day retention and are not ZDR-eligible.

### Pricing

Source: https://platform.claude.com/docs/en/about-claude/pricing.md, fetched 2026-10-12.

| Model | USD per 1M tokens (in / out) | CAD per 1M tokens (in / out) | CAD per turn | CAD per day | CAD per 30 days |
|---|---|---|---|---|---|
| Claude Opus 5.5 | 4 / 20 | 5.594 / 27.972 | 0.0280 | 0.839 | 25.17 |
| Claude Sonnet 5.5 | 2 / 10 | 2.797 / 13.986 | 0.0140 | 0.420 | 12.59 |
| Claude Haiku 5.5 (≤100k prompt) | 0.10 / 0.50 | 0.140 / 0.699 | 0.0007 | 0.021 | 0.63 |

- **Integration:** this is the native Messages API, so no change is needed.
- **Reliability:** Anthropic publishes a status page. I did not check the SLA terms, so that is **UNVERIFIED**.
- **Quality tier (judgement):** frontier.

---

## Question 2: providers checked for adult text content

### OpenAI API

**Usage Policies (https://openai.com/policies/usage-policies/)**
- The page returned **HTTP 403** to every fetch attempt, so I could not quote it. **UNVERIFIED.**
- Search snippets and secondary sources say:
  - The effective date is 29 Oct 2025.
  - It prohibits "sexual violence or non-consensual intimate content" and sexual content involving minors.

**Model Spec (https://model-spec.openai.com/2026-08-18.html, fetched 2026-10-12)** governs model behaviour, including through the API:

> **Don't respond with erotica or gore** [authority level: *System*]
> "The assistant should not generate erotica, depictions of illegal or non-consensual sexual activities, or extreme gore, except in scientific, historical, news, artistic or other contexts where sensitive content is appropriate."
> "Following the initial release of the Model Spec (May 2024), many users and developers expressed support for enabling a 'grown-up mode'. We're exploring how to let developers and users generate erotica and gore in age-appropriate contexts through the API and ChatGPT so long as our usage policies are met - while drawing a hard line against potentially harmful uses like sexual deepfakes and revenge porn."

The spec's own worked example shows the compliant answer to an explicit-story request as a non-graphic, "steamy" version.

**Adult mode**
- ChatGPT "adult mode" for verified adults was announced in late 2025 for Q1 2026.
- Secondary reports (e.g. justainews.com) say it was paused indefinitely on 2026-03-26. **UNVERIFIED** against an OpenAI statement.
- I found no API-developer adult-content tier.

**Other details**
- Erotica is **not permitted via API as of 2026-10-12**.
- **Real-person rule:** the "hard line" on sexual deepfakes. The full usage-policy text is **UNVERIFIED** (403).
- **Retention, pricing and SLA:** **UNVERIFIED**, because the pages were blocked. The API is OpenAI-native.
- **Quality tier (judgement):** frontier.

### xAI Grok API

xAI's docs now brand the company "SpaceXSI".

**Acceptable Use Policy (https://x.ai/legal/acceptable-use-policy)**
- The page returned **HTTP 403**, so I could not quote it.
- Search-result summaries of the official page say it prohibits "depicting likenesses of persons in a pornographic manner", "the sexualization or exploitation of children" and nudifying real people.
- Secondary sources give the AUP effective date as 2 Jan 2025.

**Consumer Terms and FAQ (search snippets of x.ai/legal/terms-of-service and x.ai/legal/faq)**
- These say the consumer service "may have content such as some suggestive dialogue, coarse language, crude humor, sexual situations, or violence".
- That is consumer-app language. I found **no published API term that explicitly permits sexually explicit text**, so the API position is **UNVERIFIED**.
- Secondary sources say adult text is tolerated when it involves no minors and no real-person pornography.

**Real person:** pornographic depiction of a real person's likeness is prohibited. I found no consent exception in the sources I could see.

**Data (https://docs.x.ai/developers/faq/security.md, fetched 2026-10-12)**

> "SpaceXSI never trains on your API inputs or outputs without your explicit permission. By default, all API requests and responses are stored … for 30 days for auditing purposes in the event of suspected abuse or misuse."

- Zero data retention is self-serve and team-wide. It disables stateful features.
- The docs describe regional endpoints.

**Pricing (https://docs.x.ai/docs/models.md, fetched 2026-10-12)**

| Model | USD per 1M tokens (in / out) | CAD per turn | CAD per day |
|---|---|---|---|
| grok-4.7 (<200k) | 2.00 / 6.00 | 0.0117 | 0.352 |
| grok-4.3 (<200k) | 1.25 / 2.50 | 0.0066 | 0.199 |

- **Integration:** OpenAI-style Chat Completions and Responses. The `safety_identifier` field is "the same as OpenAI's". An Anthropic-compatible endpoint is **UNVERIFIED**.
- **SLA and status page:** **UNVERIFIED**.
- **Quality tier (judgement):** frontier.

### Mistral (La Plateforme / AI Studio)

**Usage Policy (https://legal.mistral.ai/terms/usage-policy, Effective June 11, 2026, fetched 2026-10-12)**

The only sexual items it prohibits are:

> - "Content that enables or exploits individuals, including through human trafficking or sexual services."
> - "Child Sexual Abuse Material ('CSAM') Mistral AI has a zero tolerance policy regarding CSAM."
> - "Non-consensual intimate imagery. You shall not use the Mistral AI Products to generate intimate images of any person without the explicit consent of all individuals involved."
> - "Privacy … using someone else's likeness or voice to generate outputs or impersonate them, without their prior consent."
> - "You shall not try to circumvent security protections and AI safety filters."

Scope: the policy "does not apply to Mistral AI Products deployed on a customer's infrastructure … or to our open-source AI models".

**Commercial Terms (Effective September 25, 2026)**

> "Mistral AI may, in its sole discretion, provide Output filters … If Customer deactivates these filters, Customer is solely responsible for the Output that is generated."
> "Customer may not represent or imply that the Output was generated by a human."

**Other details**
- **Status:** adult sexual text between consenting adults is **not prohibited**, but it is not explicitly permitted either. The policy is silent on it.
- **Real person:** explicit, prior consent of the person is required for use of their likeness or for intimate imagery.
- **Training:** customer data is not used for training unless you opt in, or fail to opt out on an opt-in-default product. Check which applies to the API: **UNVERIFIED**.
- **ZDR:** "available only with pay-as-you-go and only for stateless API calls" (help.mistral.ai, dated August 12, 2026).
- **Region:** EU company.
- **Pricing:** https://mistral.ai/pricing says "Mistral Large costs $0.5 /M tokens in and $1.5 /M tokens out". That works out to CAD 0.0029 per turn and CAD 0.088 per day.
- **Integration:** Mistral's own chat-completions API, which is OpenAI-like.
- **SLA:** custom SLAs on the Enterprise plan only.
- **Quality tier (judgement):** upper-mid to near-frontier.

### Google Gemini API

**Generative AI Prohibited Use Policy (https://policies.google.com/terms/generative-ai/use-policy, Last Modified December 17, 2024, fetched 2026-10-12)**

> "Do not engage in sexually explicit, violent, hateful, or harmful activities. This includes generating or distributing content that facilitates: … Sexually explicit content -- for example, content created for the purpose of pornography or sexual gratification."
> "Impersonating an individual (living or dead) without explicit disclosure, in order to deceive."
> "We may make exceptions to these policies based on educational, documentary, scientific, or artistic considerations…"

**Other details**
- **Status:** explicit content is **prohibited**.
- **Training:** the pricing page shows the free tier is "Used to improve our products: Yes" and the paid tier is "No".
- **Pricing (paid tier):**
  - Gemini 3.8 Flash: $0.75 / $3.75 until 2026-12-31, doubling on 2027-01-01. CAD 0.0052 per turn.
  - Gemini 3.1 Pro Preview: $2 / $12. CAD 0.0151 per turn.
- **Integration:** Google's own API. An OpenAI-compatibility layer exists but I did not re-check it: **UNVERIFIED**.
- **Quality tier (judgement):** frontier.

### Meta Llama (self-hosted or via hosts)

**Llama 4 Acceptable Use Policy (https://www.llama.com/llama4/use-policy/, fetched 2026-10-12).** The Llama 3 AUP has the same sexual-content items.

> "The illegal distribution of information or materials to minors, including obscene materials, or failure to employ legally required age-gating …"
> "Sexual solicitation"
> "Impersonating another individual without consent, authorization, or legal right"
> "Representing that the use of Llama 4 or outputs are human-generated"
> "Fail to appropriately disclose to end users any known dangers of your AI system"

**Status:** lawful adult sexual text is **not prohibited and not explicitly permitted**. The policy is silent apart from the "sexual solicitation" bullet, which appears under illegal activity, and the requirement to age-gate obscene material.

### Inference hosts

**OpenRouter**
- Source: https://openrouter.ai/terms, Last Updated August 31, 2026.
- OpenRouter imposes no adult-content ban of its own that I could find. It passes through each model's "Model Terms": "By accessing or using any Model through the Service, you agree … to comply with the applicable terms for each Model".
- It screens inputs for CSAM.
- Prompt logging is opt-in, and ZDR routing is available as an account setting.
- So the real rule is whatever the underlying model provider allows.
- OpenAI-compatible.

**DeepInfra**
- Source: https://deepinfra.com/terms, fetched 2026-10-12.
- The restrictions section has no sexual-content clause. It bars "any illegal, fraudulent, or deceptive purpose, to impersonate any person or entity".
- It contractually commits to **Zero Data Retention** by default: data is not retained "beyond the period strictly necessary to process and return the applicable request".
- The model licence still applies.
- Example price: DeepSeek-V4-Pro at $1.30 / $2.60, which is CAD 0.0069 per turn and CAD 0.207 per day.
- OpenAI-compatible (not re-verified).

**Together AI**
- Source: https://www.together.ai/terms-of-service, fetched 2026-10-12.
- **Prohibits:** "You are strictly prohibited from using the Services to communicate any message or material that (i) is libelous, harmful to minors, obscene, or constitutes pornography".
- Example price: DeepSeek V4 Pro 0813 at $1.32 / $3.96, which is CAD 0.0078 per turn.

**Fireworks AI**
- The AUP URL returned 404 and the terms page renders client-side.
- A secondary summary says it bars content "Fireworks AI alone decides is objectionable".
- **UNVERIFIED.**

### Venice.ai API (explicitly markets "uncensored" models)

**Docs (https://docs.venice.ai/llms.txt, fetched 2026-10-12)**

> "Venice is a privacy-first, uncensored AI API platform … with zero data retention and OpenAI SDK compatibility."
> "Venice provides permissionless access to AI models with no content filtering, making it ideal for developers building applications that require uncensored outputs".

**Terms of Service (https://venice.ai/legal/tos, Last updated June 8, 2026)**
- A user under 18 must "not disable, block, circumvent, or otherwise impede with the mature content filter". This implies adults may disable it.
- It prohibits child abuse material, including AI-generated material.
- It prohibits "using in Input any third party's name, voice, image, or likeness without their consent".
- Content that users Submit for sharing must not be "pornographic". This appears to cover shared or public user content, not private outputs, but the scope is **UNVERIFIED**.

**Other details**
- **Status:** the closest thing found to explicit permission, but it is stated in docs and marketing rather than as a positive grant in the terms.
- **Privacy:** "Private" tier is zero data retention on self-hosted open models. There are also TEE and end-to-end-encrypted tiers.
- **Proxied models:** frontier models from other companies (Claude, Gemini, Grok) are proxied in the "Anonymized" tier. *Judgement:* the originating provider's policy still applies to those models, so Claude through Venice is still bound by Anthropic's policy.
- **Pricing:**

| Model | USD per 1M tokens (in / out) | CAD per turn | CAD per day |
|---|---|---|---|
| venice-uncensored-1-2 | 0.20 / 0.90 | 0.0013 | 0.040 |
| venice-uncensored-role-play | 0.50 / 2.00 | 0.0032 | 0.097 |
| GLM 4.7 (Private) | 0.55 / 2.65 | 0.0038 | 0.114 |
| Kimi K3 (Private) | 3.75 / 18.75 | 0.0262 | 0.787 |

- **Integration:** OpenAI-compatible (base URL `https://api.venice.ai/api/v1`).
- **SLA:** **UNVERIFIED**. A status page is linked but its host was blocked by the sandbox proxy.
- **Quality tier (judgement):** mid for the "uncensored" models, which are fine-tunes or abliterated variants of open models. Upper-mid for GLM, Kimi and DeepSeek-class models.

### Not checked

I did not check NovelAI, Featherless, Mancer, Arli AI and similar adult-oriented hosts beyond a fetch of the NovelAI and Featherless terms, which showed no relevant clause. **UNVERIFIED.**

---

## Comparison table

| Provider | Explicit adult text | Basis | Real-person persona rule | Training on inputs / ZDR | CAD per turn (example model) | API style | Quality tier (judgement) |
|---|---|---|---|---|---|---|---|
| Anthropic | **Prohibited** (incl. erotic chat, fantasies or fetish) | AUP verbatim | No impersonating to deceive; disclosed fiction OK | No training; not retained by default; ZDR via sales | 0.0140 (Sonnet 5.5) | Anthropic Messages | Frontier |
| OpenAI API | **Prohibited** (erotica, System-level); "grown-up mode" only "exploring" | Model Spec 2026-08-18 | Hard line on sexual deepfakes | UNVERIFIED (403) | UNVERIFIED | OpenAI | Frontier |
| xAI Grok API | **Unclear.** Consumer terms mention "sexual situations"; no API permission found | AUP 403; secondary | No pornographic depiction of real likenesses | No training; 30-day default; self-serve ZDR | 0.0117 (grok-4.7) | OpenAI-compatible | Frontier |
| Mistral API | **Not prohibited** (silent); output filters can be turned off | Usage Policy 2026-06-11 | Prior consent needed for likeness; explicit consent for intimate imagery | No training unless opted in; ZDR on pay-as-you-go | 0.0029 (Large) | Mistral (OpenAI-like) | Upper-mid |
| Google Gemini | **Prohibited** | Prohibited Use Policy | No impersonating to deceive | Paid tier: no training; free tier: yes | 0.0052 (3.8 Flash) | Google (+ OpenAI layer, UNVERIFIED) | Frontier |
| Meta Llama (self-host) | **Not prohibited** (silent); age-gating required for obscene material | Llama 4 AUP | No impersonating without consent | Self-hosted: you control it | Hosting cost only | Any | Mid |
| OpenRouter | Follows each model's terms | ToS 2026-08-31 | Follows model terms + rights of publicity | Logging opt-in; ZDR setting | Varies by model | OpenAI-compatible | Varies |
| DeepInfra | **Not prohibited** in its terms; model licence applies | Terms | No impersonating | Contractual ZDR by default | 0.0069 (DeepSeek V4 Pro) | OpenAI-compatible (not re-verified) | Upper-mid |
| Together AI | **Prohibited** ("constitutes pornography") | ToS | — | Not checked | 0.0078 (DeepSeek V4 Pro) | OpenAI-compatible | Upper-mid |
| Fireworks | UNVERIFIED | — | — | — | — | OpenAI-compatible | — |
| Venice.ai | **Marketed as uncensored / "no content filtering"**; adults may turn off the mature filter | Docs + ToS 2026-06-08 | Name or likeness needs consent | ZDR on "Private" tier; TEE / E2EE tiers | 0.0013–0.0262 | OpenAI-compatible | Mid to upper-mid |

---

## Honest summary against the owner's listed capabilities (Anthropic)

| Capability | Anthropic | Note |
|---|---|---|
| Flirting | **Meets** | Not restricted, as long as it stays non-explicit. |
| Suggestive humour | **Meets** | Allowed while non-explicit; the edge is ambiguous. |
| Candid sex / desire discussion | **Mostly meets** | Non-graphic, informational or relational discussion is fine. |
| Fantasy discussion or generation | **Does not meet** | "Generate content related to sexual fetishes or fantasies" is prohibited. Abstract discussion is ambiguous. |
| Explicit sexual content / erotic chat | **Does not meet** | Prohibited verbatim. |
| Emotional intimacy | **Meets** | Not restricted. |
| Style preferences | **Meets** | A product feature (system prompt). |
| Initiative | **Meets** | A product feature. |
| Continuity / memory | **Meets** | A product feature. Prompt caching makes long context cheap. |

### Which alternatives permit the rest (explicit sexual text and fantasy)

- **No first-tier frontier lab** (OpenAI, Google, Anthropic) permits it via API in its published terms as of 2026-10-12.
- **xAI** tolerates sexual situations in its consumer product. API permission is **UNVERIFIED**.
- **Mistral's API and DeepInfra** do not prohibit it; their terms are silent rather than explicitly permissive.
- **Self-hosted Llama or open-weight models** are not prohibited for lawful adult content, subject to age-gating.
- **Venice.ai** is the only provider found that affirmatively markets uncensored adult-capable models. That is stated in its docs, while its ToS implies adults may switch off the mature-content filter.
- **Together and Gemini** prohibit it.

### Real-person consent, the binding constraint across providers

Because the persona is associated with a real, identifiable person ("human Laura"), the following rules apply:

- **Mistral:** requires explicit, prior consent.
- **Venice:** requires consent.
- **Llama:** requires consent.
- **xAI:** prohibits pornographic depiction of real likenesses outright.
- **OpenAI:** draws a "hard line" on sexual deepfakes.
- **Anthropic:** prohibits deceptive impersonation, and explicit content regardless.

Under every set of terms that permits or tolerates adult content, explicit content tied to a real person's identity requires that person's documented consent. Some providers forbid it even with consent.

This report makes no recommendation to switch.
