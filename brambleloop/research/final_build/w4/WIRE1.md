# WIRE1: wiring the clusters left for app-owned files

Branch `claude/w4-WIRE1`, prepared for the integrator's review.

**Base.** `origin/claude/w4-INTEG7` e584ff01. The requested base `claude/w4-INTEG8` does not exist on origin (checked with
`git ls-remote`), so the integrator can rebase this branch onto INTEG8 when it lands. No new worktree was created:
the branch was checked out inside the existing W4-C08 worktree.

**Merged.** `claude/w4-C08` a2cc7da8, `claude/w4-C12` ccde9980 and `claude/w4-C03`. All three merged cleanly, and
none of them adds a route.

No provider or model call was made, nothing was spent, nothing was written to Etsy and nothing was deployed.

## 1. Visual routes (F-748, F-680)

- **Operator routes.** `GET /api/visual/studio` serves `visual.studio_view.canonical_model`, and
  `GET /api/visual/evidence/{slug}` serves `evidence_panel`. Both are listed in
  `app/security.OPERATOR_GET_ROUTES`, not in `PUBLIC_GET_ROUTES`. They return unpublished candidate hashes,
  rejection reasons and experiment runs.
- **Owner routes.** `GET /api/cc/visual/studio` and `GET /api/cc/visual/evidence/{slug}` are in
  `command_center/api.py`, behind the owner session (the `/api/cc/` prefix gate).
- **Panel.** `static/js/views/_visual_studio.js` is a read-only Visual Studio card at the top of the Images tab.
  It shows the canonical version and registry status, the best demonstrated provider, identity and realism yield,
  the drift count, active proposals, the number of images passing both gates, and a per-product evidence panel.
  It adds two `api.js` endpoints, and `sw.js` lists the file (cache bumped to `cc-shell-v26`).

## 2. C12 owner entry (`commerce/estate_api.py`)

Every route is under `/api/cc/etsy/`, so `security.operator_gate` applies the owner session (cookie, CSRF and nonce).
The shared operator token is refused there.

Every write records the owner's attestation of a Shop Manager page, so each write also:
- requires step-up (`auth.require_stepup`);
- runs as the signed-in owner and is audited in `cc_security_events`;
- answers 400 with the module's own reason when the module refuses the input.

| route | method | gate | module call |
|---|---|---|---|
| `/api/cc/etsy/search-visibility` | GET | owner session | `areas` + `aging(raise_incidents=False)` (F-560/F-561) |
| `/api/cc/etsy/search-visibility/{item_id}/remediated` | POST | owner session + step-up | `mark_remediated` (F-517) |
| `/api/cc/etsy/listing/{listing_id}/learning-window` | GET | owner session | `learning_window` (F-034) |
| `/api/cc/etsy/listing/{listing_id}/learning-capture` | POST | owner session + step-up | `record_capture`, actor = owner (F-034) |
| `/api/cc/etsy/registers` | GET | owner session | apps, Shared Access and partners registers (F-580/583/588) |
| `/api/cc/etsy/registers/{apps,shared_access,partners}` | POST | owner session + step-up | `record_*` |
| `/api/cc/etsy/dashboard/kpi-snapshot` | POST | owner session + step-up | `kpi_snapshot` with owner-read views (F-552) |
| `/api/cc/etsy/dashboard/traffic-sources` | POST | owner session + step-up | `record_traffic_sources` (F-562) |

**Not routed.**
- `bulk_plan` and `renewal_economics`: no executor exists, and these are computations, not owner readings.
- `etsy_dashboard.harvest`: it creates owner actions, so it belongs to a runtime cadence, not an HTTP write.

## 3. F-527 hook

`store_foundation/asset_health.check` now runs `brand.asset_consistency.sweep()`.
- Its findings join the list and are routed to `storefront_director`, the agent that reviews the shop against the
  brand rules. The brand findings previously routed to `brand`, which is no agent.
- `held_brand_assets` reports how many marks were checked and how many fixes were found.
- Live Etsy colour and typography stay UNMEASURED.

## 4. F-733 migration

The `load_laura_references` stage in `visual/image_production.py` now resolves Laura with
`canonical_registry.resolve(db)`. That covers the manifest bytes, the approved views, the conditioning packages and
the approval record. It no longer reads `canonical.verify()` plus the `IDENTITY_ID` and `CURRENT_REFERENCE_HASHES`
constants.

**Not migrated.** The other direct readers are mostly message strings, or live in other lanes' files:
`laura/*`, `store_foundation/brand_face.py` and `owner_banner.py`. Moving those is a behaviour change (fail closed),
not a mechanical edit.

## Contract

`ops/CONTRACT_CHANGES.md` has a 2026-10-27 API-routes row, and the route pin in `tests/test_w4_fmbatch1_contracts.py`
is set to `5f4aeb5f8c84b1e7`.

## Tests

`tests/test_w4_wire1_routes.py` covers:
- for each visual route: `requires_operator` true, not public, 401 when anonymous or with a wrong token, 200 with
  the operator token, and the expected keys;
- for each `/api/cc/` route: anonymous callers and the operator token are refused (401/403), and the owner session
  gets 200;
- for each write: 403 STEP_UP_REQUIRED when step-up has expired, 200 after step-up, the owner audited, and module
  refusals answered with 400 (an unknown register gets 404);
- the F-527 hook end to end through `asset_health.check`;
- the F-733 stage source;
- that the route pin is declared.
