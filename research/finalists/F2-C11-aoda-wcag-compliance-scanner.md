# F2 (C11, reframed) — AODA / WCAG compliance scanner: free scan → paid readiness report → monitoring

_Deep-dive 2026-09-15 (Day 1). Labels: **[low]** well-evidenced, **[med]** partly, **[high]** assumption._

## Business and target customer
1. Ontario private/non-profit organizations with 20+ employees that must file an AODA Accessibility Compliance Report by **2026-12-31** **[low]** (verified: mccarthy.ca, ogletree.com, woolvan.com, ontario.ca reporting portal); those with 50+ employees must have WCAG 2.0 AA websites **[low]**. Office/HR managers and owners who want a cheap check before attesting.
2. Small businesses anywhere facing the EAA (in force since 2025-06-28) or ADA pressure **[low]**.
3. Small web agencies/freelancers wanting cheap white-label monitoring for client sites **[med]**.

## Problem and offer
Manual AODA audits cost CA$800-2,500 for SMBs (verified 2026 pricing pages; up to $25k with remediation); free tools scan one page and speak in WCAG jargon. Offer:
- **Free**: single-page scan (axe-core rules mapped to WCAG 2.0/2.1 AA) with a plain-English score. Lead magnet, shareable.
- **AODA Website Readiness Report** (one-time): full-site crawl up to 200 pages, issues prioritized by severity and effort, plain-English fix guidance, accessibility statement draft, PDF suitable for a due-diligence file. CA$59 intro / CA$99 up to 1,000 pages. **[med]** on price points.
- **Monitoring**: CA$19/mo (1 site, weekly rescan, regression alerts); **Agency** CA$49/mo (10 sites, white-label PDF, client share links). **[med]**
- Later module: Bill 96 French-content scan (F3) using the same crawler.
Checkout: Stripe Managed Payments (digital; MoR handles Canadian GST/HST). Honest positioning: automated testing finds a subset of WCAG issues; no "guaranteed compliance" claims (FTC accessiBe order, 2025 **[low]**).

## Competitors (verified)
| Name | URL | Price | Weakness |
|---|---|---|---|
| accessibilitychecker.org | accessibilitychecker.org | free scan; paid plans, white-label for agencies | US/ADA framing; subscription-first |
| Decareto | decareto.com | from €34/mo (5 sites) | EU framing; no one-time SMB report |
| Accessalyze | accessalyze.com/agencies | Agency $99/mo | agency-only |
| PageAudit | pageauditors.com/pricing | $19-199/mo | subscription-only |
| wcagsafe.com | wcagsafe.com | content + tool (AODA guide) | unclear pricing; agency-marketing |
| Manual audit firms (accessibilitypartners.ca, perfectpixels.ca) | — | CA$800-25,000 | expensive, slow |
| Free: WAVE, axe DevTools, Lighthouse | — | free | single page, technical output |
Differentiation: one-time, AODA-2026-framed, full-site, plain English, cheap; monitoring as the upsell. Competition **high**; differentiation **[med]**.

## Distribution
- First 10: (a) SEO landing pages for exact-intent queries: "AODA website compliance checker", "AODA compliance report 2026 website", "is my website AODA compliant", "EAA website accessibility check", "WCAG 2.0 AA checker" — a real tool page can rank for long-tail where current results are agency blog posts **[high]**; (b) paid search test on exact-match AODA/EAA queries at CA$5-10/day for 14 days once the owner opens a Google Ads account **[med]**; (c) the free scan result page is shareable; (d) owner batch-submits to 10 tool directories (30 min) **[med]**.
- First 100: rankings compound; Q4 deadline urgency (Oct-Dec) **[med]**; agency tier discovered via the same pages; an "AODA 2026 checklist" content hub.
- Why choose this: CA$59 vs CA$800+; instant; deadline-specific; PDF evidence of due diligence. **[med]**
- Cost to reach: ads CA$150-250; domain CA$15. Distribution hypothesis testable in ~21 days after launch.

## Timelines and probabilities
- Build: crawler + axe-core runner (GitHub Actions on schedule, or Cloudflare Browser Rendering), report generator (PDF), landing + free scan, Stripe MP checkout + webhooks, Resend email: Day 3-12. Live Day ~12-14 (needs owner block: Cloudflare + domain + Stripe MP).
- Days to first customer: 14-40 **[high]**. P(first revenue) ≤7d: 0% · ≤14d: 10% · ≤30d: 35%.

## Economics (CAD)
| | Downside | Base | Upside | Assumptions |
|---|---|---|---|---|
| Day-30 revenue | 0 | 120 | 500 | 2 reports base |
| Day-90 revenue | 0 | 900 | 4,000 | base: ~9 reports + ~6 monitoring subs by Day 90; upside: ranking + Q4 urgency + 3-5 agency subs |
| Day-90 net profit | −300 | 560 | 3,300 | Stripe MP ≈ 7%; ads 250; domain 15; Workers Paid/Browser Rendering ≈ 0-15 |
Uncertainty **[high]**. Gross margin ≈ 90%. CAC via paid search unknown (CPC on accessibility terms is often CA$3-8 **[high]**); organic CAC ≈ 0. Sales cycle: minutes for the report; days for agencies. Recurring: monitoring subs; retention unknown **[high]**.

## Failure
P(meaningful failure) ≈ 55%. Causes: no traffic within 90 days (new domain); free-to-paid conversion of scanner users typically 1-3% **[med]**; buyers prefer human audits for filing confidence; ad CPCs too high for a CA$59 product.

## Capital
Domain CA$15; ads CA$150-250; Cloudflare Workers Paid CA$7/mo only if Browser Rendering is used; total CA$300-400 over the window.

## Owner workload
Setup block 60-90 min (Cloudflare account + domain + API token; Stripe account + Managed Payments + restricted key; Resend key; GitHub Actions secrets; optional Google Ads account with a hard budget cap). Then ≤15 min/week (glance at the weekly summary; approve any ad budget change above the pre-authorized cap).

## Automation architecture
Cloudflare Worker (static site + API + D1 for scans/orders); scans executed by a GitHub Actions workflow (Playwright + axe-core, cron + dispatch) or Cloudflare Browser Rendering; Stripe MP Checkout → webhook → queue scan → generate PDF (R2) → Resend email; weekly monitoring cron; free-scan rate limiting; Cloudflare Web Analytics; ledger rows from Stripe payout reports; support inbox answered by the operator on its 3-per-day schedule (within Stripe's 48-hour expectation).

## Platform and legal risks
No compliance guarantees; clear disclaimer that automated checks cover a subset of WCAG; scan only public pages, respect robots.txt and rate limits; PIPEDA privacy policy; refunds honoured (Stripe MP may refund within 60 days). Google Ads policy is fine for compliance tools.

## Kill / pivot / scale
- Kill: by Day 45, fewer than 50 free scans/week AND zero paid reports → stop ads, keep the site passive, reallocate to F1 scaling or a runner-up.
- Pivot: strong free-scan usage but no paid → test CA$29 price, add remediation guidance upsell; agencies responding → white-label first.
- Scale: paid-search ROAS > 1.5 or organic conversions → expand keywords (EAA, ADA Title II 2026-27 deadlines), add Bill 96 module (F3), add monthly monitoring upsells and annual plans.
Day-180 potential **[high]**: recurring monitoring, SEO compounding, continuing regulatory deadlines.
