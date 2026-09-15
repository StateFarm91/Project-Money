# Deployment Infrastructure Research — AI-operated micro-business (owner in Canada, 90-day budget < C$1,000)

Research date: 2026-09-15 (Day 1), produced by a research subagent with live web fetches. Prices are USD unless marked. FX used for CAD estimates: **1 USD = 1.39 CAD** (USD/CAD 1.3915 on 2026-09-15, https://tradingeconomics.com/canada/currency). Every factual claim is tagged **[V]** (verified from a fetched page, URL given), **[T]** (third-party/aggregator page, approximate) or **[I]** (inferred / not verified live).

## 0. Live probes run from this sandbox (what the AI operator can do)

- The sandbox's GitHub token is a short-lived GitHub App user token for user **StateFarm91**; it reports `admin: true, push: true` on `StateFarm91/Project-Money` (public, `has_pages: false`). **[V, live probe]**
- `GET /repos/StateFarm91/Project-Money/pages` and `GET .../actions/secrets` both return **403 "Access to this GitHub API path is not permitted through this proxy"**; `GET .../actions/workflows` returns 200. **[V, live probe]** → From the sandbox the AI can push code/workflows and run Actions, but **cannot enable GitHub Pages or write repo secrets via the API through this proxy**. Those need the owner (one click) or a GitHub Actions run using an owner-supplied PAT.
- `gh` CLI is not installed; raw `curl` to api.github.com works. **[V]**

## 1. GitHub Pages in 2026

- Enabling requires choosing a publishing source in Settings → Pages; no current doc says pushing a branch enables Pages. **[V]** https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site . Legacy auto-enable for `gh-pages` appears only in old docs; unreliable in 2026 **[I]**.
- `GITHUB_TOKEN` cannot enable Pages: `actions/configure-pages` `enablement` "requires a token other than GITHUB_TOKEN" (PAT with repo scope / Pages write, or App with administration:write + pages:write). **[V]** https://raw.githubusercontent.com/actions/configure-pages/main/action.yml ; `GITHUB_TOKEN` has no `administration` permission **[V]** https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#permissions
- Limits: 100 GB/month soft bandwidth, 1 GB site, 10 builds/hour. **Policy: "not intended for or allowed to be used as a free web-hosting service to run your online business, e-commerce site, or ... SaaS"; no sensitive transactions.** **[V]** https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits
- **Conclusion:** fine for a docs/marketing page; **not** the primary host for the business.

## 2. Static + serverless hosts — free tiers, commercial terms, connection effort

| Host | Free tier (2026) | Commercial use on free | Card | Owner connect | AI can then do |
|---|---|---|---|---|---|
| **Cloudflare Workers (+ static assets)** | 100k req/day, 10 ms CPU/req, 100 Workers, 5 cron triggers; static-asset requests free & unlimited; KV 100k reads/1k writes/day, 1 GB; D1 5M rows read/100k written/day, 5 GB; R2 10 GB, free egress **[V]** https://developers.cloudflare.com/workers/platform/pricing/ , https://developers.cloudflare.com/workers/platform/limits/ , https://developers.cloudflare.com/workers/static-assets/billing-and-limitations/ , https://developers.cloudflare.com/d1/platform/pricing/ | No commercial prohibition in the Self-Serve Subscription Agreement (2025-09-12). §2.2.1(h) prohibits collecting card data on a property receiving Free Services **[V]** https://www.cloudflare.com/terms/ → use hosted checkout (Stripe Checkout / merchant of record) **[I]** | No (Free); card for Registrar purchases | Email signup; create API token (~5 min) | `wrangler deploy` from GitHub Actions with `CLOUDFLARE_API_TOKEN` + `CLOUDFLARE_ACCOUNT_ID` **[V]** https://developers.cloudflare.com/workers/ci-cd/external-cicd/github-actions/ ; KV/D1/R2, secrets, DNS, custom domains with automatic certs **[V]** https://developers.cloudflare.com/workers/configuration/routing/custom-domains/ |
| **Cloudflare Pages** | 500 builds/mo; no bandwidth limit stated **[V]** https://developers.cloudflare.com/pages/platform/limits/ | Same terms | No | Same account | Maintenance mode; Cloudflare steers new projects to Workers static assets **[V/T]** https://developers.cloudflare.com/workers/static-assets/migration-guides/migrate-from-pages/ |
| **Vercel Hobby** | 100 GB transfer, 1M invocations **[V]** https://vercel.com/docs/plans/hobby | **Prohibited**: "non-commercial personal use only" (any payment processing, advertising a product, ads) **[V]** https://vercel.com/docs/limits/fair-use-guidelines | No | GitHub OAuth | Pro $20/user/mo → ruled out on free |
| **Netlify Free** | 300 credits/mo hard cap; 15 credits/production deploy, 20/GB bandwidth; sites paused when exhausted **[V]** https://docs.netlify.com/manage/accounts-and-billing/billing/billing-for-credit-based-plans/how-credits-work/ , https://www.netlify.com/pricing/ | Allowed **[V]** https://www.netlify.com/blog/introducing-netlify-free-plan/ | No | GitHub OAuth | ~20 deploys/month; poor fit for frequent AI deploys **[I]** |
| **Render Free** | Spin-down after 15 min idle; free Postgres expires after 30 days **[V]** https://render.com/docs/free | No restriction found | No | GitHub OAuth | Cold starts; unsuitable for paying product |
| **Fly.io** | No free allowance since 2024-10-07; card required **[V]** https://fly.io/docs/about/pricing/ | n/a | Yes | Card | `flyctl` |
| **Railway** | $5 one-time trial credit; Hobby $5/mo **[V]** https://railway.com/pricing | No restriction | Hobby yes | GitHub OAuth | API token |
| **Deno Deploy** | 1M req/mo, KV 1 GiB; "personal use and smaller projects" **[V]** https://deno.com/deploy/pricing | Not verified **[I]** | No | GitHub OAuth | `deployctl` |
| **Supabase Free** | 500 MB DB, 2 projects, **paused after ~1 week inactivity** **[V]** https://supabase.com/pricing , https://supabase.com/docs/guides/platform/free-project-pausing | No restriction | No | GitHub OAuth | Needs keep-alive |
| **Neon Free** | 0.5 GB/project, scale-to-zero, permanent free, no card **[V]** https://neon.com/pricing | No restriction | No | GitHub OAuth | Neon API |
| **Upstash Redis Free** | 500k commands/mo, 256 MB **[V]** https://upstash.com/pricing/redis | No restriction | No | GitHub OAuth | REST token |

**Recommended host:** Cloudflare Workers + static assets (free, commercial-OK, unlimited static requests, KV/D1/R2 included, custom domain + certs automated, deployable from GitHub Actions with one API token). Fallbacks: Netlify Free (credit cap) or Neon/Supabase if Postgres is required.

**Cloudflare API token** ("Edit Cloudflare Workers" template + D1: Write, Cloudflare Pages: Write (optional), Zone → DNS: Write; Registrar: Write only if API domain purchases wanted). Permission names: https://developers.cloudflare.com/fundamentals/api/reference/permissions/ **[V]**; creation flow: https://developers.cloudflare.com/fundamentals/api/get-started/create-token/ **[V]**

## 3. Domains

| TLD | Cloudflare Registrar (at cost) | Porkbun | Namecheap |
|---|---|---|---|
| .com | $10.46 **[T]** (~$11.15 after Verisign's 2026-11-01 increase **[T]**) | $11.08 / $11.08 **[V]** | $10.48 reg; renewal ~$13.98–15.88 **[T]** |
| .ca | $9.19 / $9.19 **[T]** | $8.80–8.87 sale / $9.18 **[V]** | $11.98 / $14.98 **[T]** |
| .io | ~$50.00 **[T]** | $28.12 first-yr / $51.80 **[V]** | $34.98 **[T]** |
| .app | $14.20 **[T]** | $8.75 first-yr / $14.93 **[V]** | $7.98 / $22.98 **[T]** |

Sources: https://porkbun.com/products/domains **[V]**; https://www.cloudflare.com/products/registrar/ , https://developers.cloudflare.com/registrar/faq/ **[V]**; https://tldprice.org/registrar/cloudflare , https://tldprice.org/tld/ca **[T]**. CAD: .com ≈ C$14.5/yr, .ca ≈ C$12.8/yr at Cloudflare **[I]**.

- **Cloudflare Registrar API (beta, 2026-04-15):** search/check/register endpoints; needs a token with Registrar write, a billing profile with payment method, a default registrant contact, and prior acceptance of the Domain Registration Agreement; subset of TLDs. **[V]** https://developers.cloudflare.com/registrar/registrar-api/ , https://blog.cloudflare.com/registrar-api-beta/
- **Porkbun API:** `domain/create` requires verified account email + phone and sufficient prepaid credit; DNS API available. **[V]** https://porkbun.com/llms-full.txt , https://kb.porkbun.com/article/190-getting-started-with-the-porkbun-api → owner pre-funds, AI can register.
- **Namecheap API:** gated (≥20 domains or ≥$50 balance/spend, IP allowlist) **[T]** → not worth it.
- **.ca CIRA presence:** Canadian citizen or permanent resident ordinarily resident in Canada qualifies; individuals' WHOIS details hidden. **[V/T]** https://www.cira.ca/en/legal-policy-and-compliance/canadian-presence-requirements/

## 4. LLM API costs (per 1M tokens, USD) **[V]** https://platform.claude.com/docs/en/about-claude/pricing

| Model | Input | Output | Cache read | Batch (in/out) |
|---|---|---|---|---|
| Claude Haiku 4.5 | $1 | $5 | $0.10 | $0.50 / $2.50 |
| Claude Sonnet 5 | $2 | $10 | $0.20 | $1 / $5 |
| Claude Sonnet 4.6 | $3 | $15 | $0.30 | $1.50 / $7.50 |
| Claude Opus 5 / 4.8 / 4.7 / 4.6 | $5 | $25 | $0.50 | $2.50 / $12.50 |
| Claude Fable 5.1 / Fable 5 | $10 | $50 | $0.25 / $1 | $5 / $25 |

Prepaid credits (buy before use; expire after one year; non-refundable) **[V]** https://support.claude.com/en/articles/8977456-how-do-i-pay-for-my-claude-api-usage . Rate limits / tiers **[V]** https://platform.claude.com/docs/en/api/rate-limits .

Per-request cost, 2,000 in / 500 out **[I, arithmetic]**: Haiku 4.5 ≈ **$0.0045** (≈ C$0.006); Sonnet 5 ≈ $0.009; Opus 5 ≈ $0.0225. 10,000 requests/month on Haiku 4.5 ≈ $45 (≈ C$63). Batch halves non-interactive jobs.

Alternatives: OpenAI gpt-5-nano $0.05/$0.40, gpt-5-mini $0.25/$2.00 **[V]** https://developers.openai.com/api/docs/pricing ; Gemini 3.5 Flash-Lite $0.30/$2.50, 3.8/3.7 Flash $0.75/$3.75 **[V]** https://ai.google.dev/gemini-api/docs/pricing ; DeepSeek flash $0.15–0.30 / $0.60–1.20 **[V]** https://api-docs.deepseek.com/quick_start/pricing ; Together gpt-oss-120B $0.15/$0.60 **[V]** https://www.together.ai/pricing .

## 5. Transactional email and cookie-banner-free analytics

| Provider | Free tier | Domain verification | Notes |
|---|---|---|---|
| **Resend** | 3,000 emails/mo, 100/day, 3 domains **[V]** https://resend.com/pricing | API `POST /domains` returns MX/SPF/DKIM records; `POST /domains/{id}/verify` **[V]** https://resend.com/docs/api-reference/domains/create-domain , https://resend.com/docs/dashboard/domains/cloudflare | Fully automatable by the AI with a Resend key + Cloudflare DNS Write. |
| **Postmark** | 100/mo; Basic $15/mo **[V]** https://postmarkapp.com/pricing | Manual account approval **[V]** https://postmarkapp.com/support/article/1084-how-does-the-account-approval-process-work | Too small. |
| **Brevo** | 300/day with branding **[T]** | DKIM/DMARC | Daily cap. |
| **Amazon SES** | Free tier discontinued for new customers 2026-07-21; $0.16/1k **[V]** https://aws.amazon.com/ses/pricing/ | Sandbox exit review **[V]** https://docs.aws.amazon.com/ses/latest/dg/request-production-access.html | Not worth it under 3k/mo. |

**Pick: Resend.**

Analytics: **Cloudflare Web Analytics** free, no cookies/fingerprinting **[V]** https://www.cloudflare.com/web-analytics/ ; Umami Cloud Hobby free 100k events **[T]** https://umami.is/pricing ; Plausible $9/mo **[V]** https://plausible.io/#pricing ; GoatCounter free for small business **[V]** https://www.goatcounter.com/ . Pick: Cloudflare Web Analytics. PIPEDA / Quebec Law 25 still require a privacy policy **[I, not legal advice]**.

## 6. Recommendation — minimal owner setup block (≈ 60–75 min; budget 2 h)

**Target stack (free tiers that permit commercial use):** Cloudflare Workers + static assets (site + API) with D1 / KV / R2 → custom domain at Cloudflare Registrar → Resend (email) → Cloudflare Web Analytics → Anthropic API (Haiku 4.5 / Sonnet 5) only if the product needs live AI.

1. **GitHub (10 min).** Only if GitHub Pages will be used for docs: Settings → Pages → Source = "GitHub Actions" (30 s). Alternative: fine-grained PAT (Pages: write + Administration: write; 90-day expiry) → secret `PAGES_PAT`.
2. **Cloudflare account + domain (25–30 min).** Sign up → Billing → add card → Domain Registration → register `.com` (~$10.46/yr) or `.ca` (~$9.19/yr; CPR category) → zone created automatically. Optional: accept Domain Registration Agreement + default registrant contact so the AI can buy further domains via API.
3. **Cloudflare API token (5 min).** "Edit Cloudflare Workers" template + D1: Write, Zone → DNS: Write (+ Cloudflare Pages: Write, Registrar: Write optional) → copy once. Also copy Account ID and Zone ID.
4. **Cloudflare Web Analytics (2 min).** Add site → copy beacon token (public).
5. **Resend (5 min).** Sign up → API key (full access). The AI adds the domain, writes DNS, verifies.
6. **Anthropic Console (10 min, only if live AI needed).** Buy credits (US$25–50) → monthly spend limit → auto-reload off → API key.
7. **Store secrets (10 min).** GitHub repo → Settings → Secrets and variables → Actions: secrets `CLOUDFLARE_API_TOKEN`, `RESEND_API_KEY`, `ANTHROPIC_API_KEY`, (`PAGES_PAT`); variables `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_ZONE_ID`, `CF_ANALYTICS_TOKEN`. **[V]** https://docs.github.com/en/actions/security-for-github-actions/security-guides/using-secrets-in-github-actions . Deployments run inside GitHub Actions (`cloudflare/wrangler-action@v3`); runtime secrets reach the Worker via `wrangler secret put` in the workflow. The AI never needs raw secret values in its sandbox.
8. **Payments (separate research; see PAYMENTS_RESEARCH.md).** Hosted checkout (Stripe Checkout / Payment Links, or a merchant of record) so card data never touches the free-plan property and Canadian GST/HST is simplified **[I]**. Owner KYC ~15–30 min.

### Budget (90 days, CAD, FX 1.39) **[I]**
- Domain C$13–15/yr. Hosting/DB/KV/email/analytics C$0 on free tiers. Optional Workers Paid ($5/mo) if limits are exceeded: C$21.
- AI feature at 10k Haiku 4.5 requests/mo ≈ C$63/mo; initial credit US$25–50 ≈ C$35–70.
- **Total ≈ C$15 (no AI) to ≈ C$250 (AI + Workers Paid).**

### Key caveats
- Sandbox GitHub proxy blocks `/pages` and `/actions/secrets` → owner clicks / secret entry are mandatory (live probe). GitHub Actions runners are not subject to this block.
- Cloudflare Registrar API is beta with a partial TLD list.
- Supabase free projects pause after ~1 week; prefer D1.
- Vercel Hobby is non-commercial; GitHub Pages bars business use; Fly.io has no free tier.
- Official pages that returned 403/JS-only to the fetcher: namecheap.com, cira.ca, brevo.com, umami.is/pricing, community.cloudflare.com, deno.com AUP.
