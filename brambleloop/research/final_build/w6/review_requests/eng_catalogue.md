# ENG-CATALOGUE review request — slice 1 (catalogue API with totals)

Branch `eng/catalogue`, base `origin/claude/w6-INTEG2` @ a35ad302. Code commit `9674cf5b`.
NOT deployed, NOT integrated. Nothing touches Railway, production, secrets, phase or STAGE_A_ENABLED.

## What changed

- `app/command_center/catalogue.py` (new): `GET /api/cc/catalogue`, owner session only, under the
  existing `/api/cc` default-deny gate, read-only.
  - **Single source of truth.** Rows come from `products.production_inventory.derive`, in
    recorded gate mode. The P0 board's `ROW_LIMIT = 25` preview is unchanged.
  - **Throwaway index.** On each read (cached for 60 s, like `production.view`) the derived rows
    load into a private in-memory SQLite index. It is never persisted, never written back, and
    nothing else reads it.
  - **Totals.** Totals by inventory state, 18-stage view, category, hold kind and next-action
    owner are `GROUP BY` / `COUNT(*)` over every row. The page's matching count uses `COUNT(*)`
    with the same `WHERE` clause.
  - **Filters and search.** Filters: `state`, `stage`, `category`, `family`,
    `held` (kind / `any` / `none`), `owner`, `next_action`. `q` searches slug and title,
    case-insensitive, with LIKE wildcards escaped. `page` and `page_size` are clamped
    (`page_size` ≤ 200).
  - **Per-row fields:**
    - stage;
    - evidence: certificate (release hash, content hash, physical-test flag), PDF sha256 with
      an `/api/cc/store/pdf/{slug}` link, gallery audit and frames with a
      `/api/cc/visual/evidence/{slug}` link, listing package ids, and Etsy (row, state,
      `etsy_listing_id`, read-back `live`/`verified`/`not_verified`, draft intent);
    - holds;
    - next action, with its owner read from `autonomy.charters.department_of`, or `owner` for
      owner, physical or paid holds and for the owner grant.
  - **SQL cross-check on every read.** The index is compared with the `products` table (every
    product row indexed) and the `listings` table (live and verified listings equal the index's
    Etsy stages plus honest UNKNOWN rows with a live listing). On a mismatch, `status` is UNKNOWN
    and every total is `null`.
- `app/command_center/api.py`: route registration (GET only).
- `scripts/suite_final_segment.txt`: `test_eng_catalogue.py` inserted before `test_product_run.py`.
  Note: `test_first_listing_doors.py` already sat after `test_product_run.py` at a35ad302. I left
  it there because that is another lane's file, so `test_product_run` is not last. Please confirm
  the intended order.

## 18-stage owner view (assumption to confirm)

The owner's verbatim 18-stage list is not on GitHub: none of the 455 comments on #28 contains it.
The mapping in `STAGES18` / `stage18()` follows the task's endpoints (research candidate → …
→ sales monitoring → revision/withdrawal). **If Main holds the owner's list, I will re-key
`STAGES18` to it; it is one table.** Rules:

- Each stage is an inventory state, or an inventory state split by evidence the row carries:
  - `published` with an `active`/`published_manually` listing → live on Etsy;
  - `published` with the verified-draft state (`listing_state.PUBLISHED`) and an Etsy id →
    Etsy draft verified;
  - `listing_package_completed` → physical sample pending/passed by the attribute, otherwise
    publication gates pending;
  - a `revision_required` row with a withdrawn listing → withdrawn/rejected.
- **Sales monitoring** needs a measured countable Etsy order for the slug. While the order
  source is unmeasured, a live listing is "live on Etsy", never sales monitoring with 0 sales.
- A `published` row with no listing evidence, or a row whose derivation raised, is **UNKNOWN**.
  It is counted in its own bucket, never folded into "revision required" and never 0.

## Guards and tests (`tests/test_eng_catalogue.py`, 12 tests, 320 fixture products)

- Owner-only: anonymous GET is 401/403; POST is 404/405.
- Read-only: a `before_cursor_execute` statement probe over an authenticated GET that forces a
  rebuild finds no INSERT/UPDATE/DELETE/DDL. The auth layer's `cc_owner_sessions` touch is
  excluded; it is not the catalogue's write.
- Pagination: every page is walked at 320 rows; each product appears exactly once, the last page
  size is right, and out-of-range and malformed paging is clamped.
- Totals vs SQL on `products`, `listings`, `pattern_versions` and `jobs`. Every stage filter's
  matching count equals its total. Category totals are checked against the fixture, with UNKNOWN
  for products without a concept.
- UNKNOWN never 0:
  - an underivable row is stage/state/owner UNKNOWN and counted under UNKNOWN;
  - an unbuildable catalogue has `null` totals;
  - a cross-check mismatch (patched, or a real lossy stage mapping, or a deleted index row)
    gives `null` totals.
- Paid-approval hold → next action owned by `owner`.

### Mutants (PYTHONDONTWRITEBYTECODE=1): 14/15 killed

Killed:

- trusted forced True
- derived-total check dropped
- live-listing cross-check forced ok
- product-row cross-check forced ok
- derivation-error → UNKNOWN removed
- unbuildable totals 0
- OFFSET off by one page
- LIKE escaping removed
- unmeasured sales treated as monitoring
- published-without-listing guessed live
- page clamp removed
- page-size clamp removed
- owner-hold routing removed
- charter owner hard-coded

**Survived (equivalent):** removing `ORDER BY slug, version, n`. Rows are inserted in
`rows_from`'s sorted order, so SQLite returns the same order. The clause stays for stability.

### Suites (venv, `JOBS=4 SUITE_REGISTRY=0`, run 20261119T151107Z-1307)

13 suites, 502 passing, 0 failing, 0 tmp leak:

- test_eng_catalogue
- test_vacuity
- test_w3_tmp_hygiene
- test_w4_resume_runner
- test_route_auth_default_deny
- test_web_security
- test_s4_p0_board
- test_v11_pwa_static
- test_v11_pwa_browser
- test_w4_ccux
- test_etsy_oauth_callback
- test_w4_fmbatch1_retention_guard
- test_w4_adopt_manual_listing

No new audit actions, so `ops.retention.unknown_read_actions()` is unaffected.

## Known limits (honest)

- **Cost per read.** Each uncached read re-derives the whole inventory, which is the existing
  `production.view` cost, cached for 60 s. Measured at 320 sparse fixture products: about 0.1 s
  per build locally. Production rows carry many more jobs and audits, so expect more;
  this was not measured on production data.
- **Category is not stored on `products`.** It comes from the concept pool (`radar.opportunity.
  POOL`) and recorded `radar_concepts` seeds. That table is never created here (`has_table`
  check). A product with neither is UNKNOWN.

## Next slices

- Agents panel (operating evidence per department/agent from persisted rows).
- The PWA catalogue page: cc_mock, check.mjs, and a service-worker bump above v32.
