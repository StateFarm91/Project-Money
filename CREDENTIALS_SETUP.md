# CREDENTIALS_SETUP

Integration setup instructions and status only. **Never store secrets in this repository.** Secrets live in the Claude Code environment variables (claude.ai/code → Environments → Default), in GitHub Actions secrets for scheduled jobs, and in the owner's password manager.

| Integration | Purpose | Status | Where the secret lives | Setup notes |
|---|---|---|---|---|
| GitHub (`StateFarm91`) | Source control, CI | active | Claude Code Remote session credential | Scoped to `StateFarm91/Project-Money`. The sandbox proxy blocks `/actions/secrets` and `/pages` API paths (owner sets those in the GitHub UI). |
| Etsy Open API v3 — seller app `MapleSheets Ops` | Create/update listings, upload digital files and images, read shop stats and orders | **waiting on owner (OWNER_ACTIONS Block 1)** | `ETSY_KEYSTRING`, `ETSY_REFRESH_TOKEN` as environment variables; same names as GitHub Actions secrets | OAuth 2.0 authorization-code + PKCE; scopes `listings_r listings_w listings_d shops_r shops_w transactions_r feedback_r`; access token 1 h, refresh token 90 days. Helper: `products/etsy-templates/etsy_api.py` (to be written). |
| Etsy Ads | In-marketplace ads | not started | n/a (dashboard only; no API) | Owner sets budget once per instruction. |
| Cloudflare, Stripe, Resend | Own-domain checkout / Track B pre-test | deferred (Block 2) | environment variables + GitHub Actions secrets | See `docs/infra/`. |
