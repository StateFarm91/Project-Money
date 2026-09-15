# BACKLOG

Self-directed work queue. Items move to `CURRENT_PRIORITIES.md` when selected.

## Track A — Etsy (selected strategy)
- [ ] Workbook v1 validation + quick-start PDF + README (ZIP ≤ 20 MB, ≤ 5 files)
- [ ] Etsy API client + fixtures + tests; PKCE flow; daily stats pull → `KPI_DASHBOARD.md`
- [ ] Listing 1 copy/tags/images; publish via API once credentials exist
- [ ] Listing 2 (GST/HST quick-method calculator + small-supplier tracker) generator
- [ ] Listing 3 (home-office + vehicle) and 4 (instalment planner; verify 2026 brackets first) generators
- [ ] Bundle listing; Q4 "get ready for the 2026 tax year" copy angle
- [ ] Shop policies + About text for the owner to paste
- [ ] Competitor keyword neighbourhood report from `findAllListingsActive` (EXP-001 benchmark)
- [ ] Weekly title/tag rewrite routine from API view data
- [ ] Line extension candidates: Shopify/Etsy-seller variant; therapist/allied-health practice templates (C08)
- [ ] Physical line via print-on-demand (C19): Printify API, Canadian print providers, personalized Canadian gifts for Q4; owner creates a Printify account (10 min); zero cost until an order (D-007)
- [x] Track B authorized (D-009): see MASTER_STRATEGY Track B section and CURRENT_PRIORITIES 8-9
- [ ] Track B: `products/store/` — Shopify Admin API client, CJ client, Meta Marketing API client (campaign/ad set/ad creation with lifetime budgets, insights pull), creative pipeline (Pillow images; fal.ai image-to-video; ffmpeg captions/stitching), support-agent Worker (Email Routing → D1 → Anthropic API with Shopify order lookup → reply; escalation log), disputes evidence helper, ledger importer for Shopify payouts and Meta invoices
- [ ] Track B: TikTok ads only after Meta results exist; Amazon excluded (policy/fees/time); TikTok Shop not available in Canada
- [ ] Ledger automation from Etsy Payments statements (`ops/ledger.py` importer)

## Track B — deferred pre-test (EXP-003; only after EXP-001 passes and compute allows)
- [ ] One static page + single-page free WCAG scan + plain-Stripe Payment Link for a CA$29 full-site automated pre-check (never "readiness"/"compliant"); owner Block 2 then
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
