# Handoff — lane W4-STORE (real Etsy store)

Branch: `claude/w4-STORE` (worktree `.claude/worktrees/W4-STORE`). Latest pushed SHA: see `git log -1 origin/claude/w4-STORE`.

## Owned / done
| Item | Status | Evidence |
|---|---|---|
| Live-state snapshot record (getShop reading + dated owner observation; per-field source/freshness; unread = UNKNOWN) | PROVEN | `store_foundation/live_state.py` snapshot(); tests/test_w4_store_live_state.py |
| Drift report repo draft vs live; owner-configured fields authoritative (ADOPT_LIVE_INTO_REPO), proposals only, auto_apply/write_allowed False | PROVEN | live_state.drift(); same test |
| Owner-field protection: `shop_package.api_shop_fields` drops owner-configured `title`; `live_state.guard/write_refusal`; EtsyClient has no updateShop | PROVEN | same test |
| Content model `entered_on_etsy` from live evidence (`content.build(db)` → `live_state.annotate`) | PROVEN | same test |
| `store.live_drift` handler (reads stored readings only; P3 incident for owner field shown blank; resolves on later read) | PROVEN in code; cadence EXTERNAL-GATED | runtime/etsy_ops.py handle_store_live_drift; same test |
| STORE_READINESS.md/json: settings checklist A–G, taxonomy, attributes, policies, images, listings, upload/read-back, analytics, publication, owner-action checklist | written | `store_foundation/store_readiness.py --write` |

Live state in this environment: **UNKNOWN** for every field — no ETSY_* credential present; public shop page = HTTP 403 DataDome CAPTCHA (not bypassed).

## WIRING REQUESTS
1. **W4-AUTO** `runtime/worker.py` CADENCES: add `("store_live_drift", "orchestrator", "store.live_drift", 24 * 60 * 60)` right after `etsy_shop_snapshot`.
2. **W4-AUTO** `agents/registry.py`: add `"store.live_drift"` to the orchestrator allowed job types next to `"etsy.shop_snapshot"` (line ~727). GREEN class (read-only, no Etsy write).
3. **W4-CC** Command Center: route `POST /api/store/live_observation` → `store_foundation.live_state.record_observation(db, observed_at, fields, statement)` (session + CSRF), and show `etsy_ops.latest_reading(db, "store.live_drift")` on the store page.

## Next deterministic actions
- After wiring: production runs etsy.shop_snapshot → store.live_drift daily; re-run `python -m brambleloop.store_foundation.store_readiness --write` against the production DB to replace UNKNOWNs.
- Owner: OA-A1 (re-authorise) and OA-OBS (record About/Laura live text) unblock read-back.

## Tests run
Focused only (2026-10-07): test_w4_store_live_state 12/12, test_shop_package 18, test_w3_store_copy_routing 7,
test_w3_store_copy_surfaces 13, test_v11_store_foundation 20, test_v11_store_preview 13, test_etsy_readback_observe 37,
test_k8_shop_cx 17, test_vacuity 7 (after fix), test_secret_scan 7, test_reachability 11, test_w3_tmp_hygiene 16 — all pass.
