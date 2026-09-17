# CREDENTIALS_SETUP

Integration setup instructions and status only. **Never store secrets in this repository.** Secrets live in the Claude Code environment variables (claude.ai/code → Environments → Default), in GitHub Actions secrets for scheduled jobs, and in the owner's password manager.

| Integration | Purpose | Status | Where the secret lives | Setup notes |
|---|---|---|---|---|
| GitHub (`StateFarm91`) | Source control, CI | active | Claude Code Remote session credential | Scoped to `StateFarm91/Project-Money`. The sandbox proxy blocks `/actions/secrets` and `/pages` API paths (owner sets those in the GitHub UI). |
| Etsy Open API v3 — seller app `MapleSheets Ops` | Create/update listings, upload digital files and images, read shop stats and orders | **waiting on owner (OWNER_ACTIONS Block 1)** | `ETSY_KEYSTRING`, `ETSY_REFRESH_TOKEN` as environment variables; same names as GitHub Actions secrets | OAuth 2.0 authorization-code + PKCE; scopes `listings_r listings_w listings_d shops_r shops_w transactions_r feedback_r`; access token 1 h, refresh token 90 days. Helper: `products/etsy-templates/etsy_api.py` (written, unit-tested, no live calls made yet). |
| Etsy Ads | In-marketplace ads | not started | n/a (dashboard only; no API) | Owner sets budget once per instruction. |
| Printify (personal access token) | Create/publish print-on-demand products to the Etsy shop; read orders | waiting on owner (Block 1 step 9, optional) | `PRINTIFY_TOKEN` environment variable | Printify API v1 (`https://api.printify.com/v1/`); shop connected to Etsy inside Printify. Helper: `products/pod/printify_api.py` (written, unit-tested, no live calls made yet). |
| Shopify Admin API (custom app `Operator`) | Catalogue, orders, fulfilment, theme, markets | waiting on owner (Block 2A) | `SHOPIFY_ADMIN_TOKEN`, `SHOPIFY_STORE_DOMAIN` | Admin API 2026-07; scopes listed in OWNER_ACTIONS. |
| CJ Dropshipping API | Product sourcing, order routing, tracking | waiting on owner (Block 2A) | `CJ_API_KEY` | CJ open API v2; CJ Shopify app for auto-routing. |
| Cloudflare (Workers, D1, Email Routing, Registrar) | Domain purchase, DNS, support-agent Worker | waiting on owner (Block 2B) | `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID` | Registrar API beta for the .com purchase; Email Routing → Worker for the support inbox. |
| Anthropic API | Customer-support agent (Haiku 4.5) | waiting on owner (Block 2B) | `ANTHROPIC_API_KEY` | Spend limit US$40/month set by owner. |
| Meta Marketing API (system user) | Campaigns, ad sets, creatives, insights on the owner's ad account | waiting on owner (Block 2C) | `META_SYSTEM_TOKEN`, `META_AD_ACCOUNT_ID`, `META_PAGE_ID`, `META_PIXEL_ID` | No app review needed for own assets; lifetime budgets enforce caps. |
| fal.ai | Image-to-video and image generation for creatives | waiting on owner (Block 2C) | `FAL_KEY` | Kling/Wan/Seedance models ≈ US$0.03-0.08 per second. |
| Stripe / Resend | Own-domain checkout for templates; transactional email | not needed for now | — | Shopify Payments and Etsy cover payments; revisit if a Stripe checkout is wanted. |
