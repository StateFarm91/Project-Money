# F3 (C33 + C37) — Bill 96 French-content compliance scan (module of F2), with an optional translation pack

_Deep-dive 2026-09-15 (Day 1). Labels: **[low]** well-evidenced, **[med]** partly, **[high]** assumption._

## Business and customer
Online stores and business websites that serve Quebec residents (the Charter applies regardless of where the business is located **[low]**, verified: multilingualizer.com 2026, weglot.com) that still have English-only product pages, policies, checkout strings or emails. Enforcement is complaint-driven; first-offence fines CA$3,000-30,000, doubled/tripled on repeats; 2026 cases (URBN Canada, Waterco) landed around CA$3,000 for English-only web content **[low]**.

## Offer
- Free "Bill 96 French-content score": crawl, detect English-only pages/strings, missing French policies, language switcher, checkout and email language. 
- CA$29 report (list of non-compliant pages/strings, priority fixes, FR/EN checklist); CA$9/mo monitor for new English-only content (Stripe MP, digital).
- Optional translation pack (CA$149-349, reviewed fr-CA, Translate & Adapt-compatible CSV) sold as a service via plain Stripe **only if** report buyers ask **[high]**.

## Verification that weakened the standalone case
Shopify's free **Translate & Adapt** auto-translates up to 2 languages natively (4.5 stars, 1,396 reviews); Weglot from US$17/mo; Langify from US$17.50 **[low]**. So "get French" is cheap; the remaining value is *finding what is still English* after such tools are enabled (checkout, apps, emails, policies) and documenting due diligence. Demand is latent; fines are real but sporadic. No Fiverr "Bill 96" gigs surfaced in search **[med]**, which cuts both ways (no proven marketplace demand, no competition).

## Distribution
SEO in FR and EN ("Bill 96 website compliance checker", "Loi 96 site web conformité", "OQLF site web anglais"); law-firm and translation-vendor guides own the SERP **[med]**; Shopify Community answers need the owner. Shares F2's site, checkout, crawler and ads account, so incremental cost ≈ CA$0-50.

## Timelines, probabilities, economics (CAD)
- Incremental build after F2's engine exists: 2-3 days. Earliest sensible launch: Day 25-35.
- P(first revenue) ≤30d from its own launch: 25% **[high]**.
- Day-90: downside 0 · base 300 · upside 2,500 (if translation packs sell) · net ≈ base 250. Failure ≈ 65%.
- Capital: ≤ CA$50 incremental. Owner: none beyond F2's block. Automation: same as F2 plus fr-CA translation pipeline (LLM API, glossary, review pass) if the pack is offered.

## Risks
Translation quality claims (fr-CA nuance) → refunds; legal-adjacent framing (this is a content check, not legal advice); services excluded from Stripe Managed Payments (use plain Stripe for the pack).

## Decision
Not a standalone winner. Build as F2's second module once F2's crawler and checkout are live and F2 shows any paid conversion; kill if the F2 engine itself fails. Day-180 potential **[med]** (Quebec francization deadlines continue; agency tier could bundle both scans).
