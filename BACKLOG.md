# BACKLOG

Self-directed work queue. Items move to `CURRENT_PRIORITIES.md` when selected.

## Track A — Etsy (selected strategy)
- [ ] Workbook v1 validation + quick-start PDF + README (ZIP ≤ 20 MB, ≤ 5 files)
- [ ] Etsy API client + fixtures + tests; PKCE flow; daily stats pull → `KPI_DASHBOARD.md`
- [ ] Listing 1 copy/tags/images; publish via API once credentials exist
- [ ] Listing 2 (GST/HST quick-method calculator + small-supplier tracker) generator
- [ ] Listing 3 (home-office + vehicle) and 4 (instalment planner; verify 2026 brackets first) generators
- [x] Bundle listing (5 = 1+2+3+4, CA$44); Q4 "get ready for the 2026 tax year" copy angle still open
- [ ] Shop policies + About text for the owner to paste
- [ ] Competitor keyword neighbourhood report from `findAllListingsActive` (EXP-001 benchmark)
- [ ] Weekly title/tag rewrite routine from API view data
- [ ] Line extension candidates: Shopify/Etsy-seller variant; therapist/allied-health practice templates (C08)
- [x] Physical line via print-on-demand (C19): ~~Printify API client~~ done (`products/pod/printify_api.py`, unit-tested, no live calls yet), Canadian print providers filter built in; ~~3 of 5 designs~~ done (`products/pod/build_designs.py` + `DESIGN_SPEC.md`); owner creates a Printify account (10 min); zero cost until an order (D-007). Still open: 2 more designs, blueprint pixel dimensions, Personalization Studio config, listing copy/mockups.
- [x] Track B authorized (D-009): see MASTER_STRATEGY Track B section and CURRENT_PRIORITIES 8-9
- [ ] Track B: `products/store/` — Shopify Admin API client, CJ client, Meta Marketing API client (campaign/ad set/ad creation with lifetime budgets, insights pull), creative pipeline (Pillow images; fal.ai image-to-video; ffmpeg captions/stitching), support-agent Worker (Email Routing → D1 → Anthropic API with Shopify order lookup → reply; escalation log), disputes evidence helper, ledger importer for Shopify payouts and Meta invoices
- [ ] Track B: TikTok ads only after Meta results exist; Amazon excluded (policy/fees/time); TikTok Shop not available in Canada
- [ ] Ledger automation from Etsy Payments statements (`ops/ledger.py` importer)

## Track B — deferred pre-test (EXP-003; only after EXP-001 passes and compute allows)
- [ ] **Design correction (D-014, 2026-09-16):** do not center this on a website/WCAG scanner. Tier it like a real filing-readiness tool: **20-49 employees** = applicability + self-attestation filing readiness only, no website module (D1 in `research/ADVERSARIAL_REVIEW.md`: this tier has no website obligation, so a scanner-first pitch is selling most of the market something irrelevant to their filing); **50+ employees** = adds the WCAG 2.0 AA website check plus the documented multi-year plan/policy requirement. One static page + a short applicability/readiness assessment + plain-Stripe Payment Link for a CA$29-59 report (never "readiness"/"compliant" — automated pre-check only); owner Block 2 then.
- [ ] Still unresolved even with the tiering fix, re-check before building: a brand-new domain will not rank in Google within a 90-day window (X3) so distribution needs paid search on exact-intent AODA-2026 terms or another channel, not organic SEO; CPCs on compliance/legal terms run CA$3-8+; buyers attesting to a government portal may prefer a human-reviewed audit over an automated one for filing confidence (noted failure mode in `research/finalists/F2-C11-aoda-wcag-compliance-scanner.md`); scope the pre-test to the assessment + one-time report only (skip the evidence vault/document engine/remediation tracker — that is a multi-week SaaS build, not a cheap pre-test).
- [ ] Bill 96 French-content scan module (parked; F3)

## Runner-ups kept warm
- [ ] C03 Agent-PR Guard GitHub Action (instant marketplace; Polar license)
- [ ] C28 Stripe-native NPS tool (Delighted refugees; late)
- [ ] C25 launch board with paid featured slots (cold start)
- [ ] C41 chat-export court PDF; C17 Express Entry alerts (distribution the operator cannot run)

## Operations
- [ ] Mission heartbeat Routine (create at end of Day-1 session); lock lease; idempotent actions log
- [ ] `ops/status.py` extend with Etsy stats once the API is live
- [ ] Recommend to owner: consider making this repository private (strategy and ledger are visible to competitors). Low priority; owner's call.
