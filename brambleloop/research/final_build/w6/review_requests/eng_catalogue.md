# ENG-CATALOGUE review request

Branch `eng/catalogue`, base `origin/claude/w6-INTEG2` @ a35ad302 (INTEG2 has not moved).

| Slice | Content | Code commit |
| --- | --- | --- |
| 1 | Catalogue API with totals | `9674cf5b` (posted on #28 as fc83928c) |
| 2 | Operating evidence API (the agents panel) | `9e8e0388` |
| 3 | PWA pages: Catalogue and Agent evidence | `9e8e0388` |

Slice 2 and slice 3 are below the slice-1 sections.
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


---

# Slice 2 — operating evidence (`GET /api/cc/operating-evidence`)

`app/command_center/operating_evidence.py` (new). Owner session only, under the same gate,
read-only. Every figure comes from persisted rows. Per department, using
`autonomy.charters.department_of` on job types:

- **Last successful USEFUL job.** The newest DONE job that `runtime.pipeline.did_no_work`
  counts as work, so `WORK_KEYS` applies.
  - `ops.health`, `ops.heartbeat` and `ops.slo` never count. A green health check is not
    autonomy evidence.
  - The scan is bounded at `SCAN_LIMIT`, the newest 1000 completions. If the bound is reached
    with no useful job, the answer is **UNKNOWN**, never "none". "NONE" is reported only when
    every completion was scanned.
- **Next scheduled work.** The pending `MIN(run_after)` in SQL, and the department's next
  unsuspended cadence (`flow_health.next_cadences`, the scheduler's own arithmetic).
- **Queue.** Depth and oldest age per department and per stage (`production_inventory.
  stage_of`). Pending jobs and failed jobs awaiting retry count, from one SQL `GROUP BY
  job_type`.
- **In progress.** RUNNING jobs.
- **Last 24 h:**
  - useful vs no-op completions;
  - stage transitions (useful stage jobs);
  - listing packages completed (distinct `listing.seo_drafted` artifacts);
  - versions certified (`gate.certify` granted).
- **Recoveries.** `recovery.*` rows except `recovery.refused`, plus `queue.lease_reclaimed`.
  Refusals are counted separately (24 h).
- **Dead letters.** Total, open (no later DONE of the same type), defect vs refused
  (`classify_dead_letter`), and 24 h.
- **Blocked, with reasons.**
  - `swarm.orchestrate.suspended_job_types` (kind and why), and open defect dead letters.
  - If suspensions cannot be read, `blocked` is **UNKNOWN**, as are the department and the
    page state. It is never "not blocked".
- **Workers.** Healthy or unhealthy per `ops_runtime_samples` heartbeat (component and
  instance). Healthy means the latest beat is ok and is within `slo.WORKER_STALL_S`. With no
  heartbeat table, or no heartbeat ever recorded, the counts are UNKNOWN (null), never 0.
  `slo.worker_stall` is included as `queue_drain`.
- **Page state.** BLOCKED > UNKNOWN > OK. OK only if some department did useful work in the
  last 24 h; otherwise IDLE, so an empty database never reads OK. If jobs cannot be read,
  `departments`, `last_24h` and `dead_letters` are `null`.

**Retention:** `recovery.refused` is now read by name. It is recorded in
`KNOWN_READ_ACTIONS` as `lifetime_total`, which the protected `recovery.` prefix already
implies, and `ops.retention.unknown_read_actions()` returns `[]`. `test_etsy_oauth_callback`'s
retention guard caught this on an intermediate run before the fix.

## Tests: `tests/test_eng_catalogue_agents.py`, 10 tests

- Last useful job judged by `WORK_KEYS`: newer no-op and empty completions are skipped.
- A health check is never useful work, and the page then reads IDLE.
- An exhausted scan is UNKNOWN; with the full bound the older useful job is found; with
  every row scanned the answer is NONE.
- Queue depth, oldest age, failed-awaiting-retry, in progress, and the next pending
  run_after.
- A dead letter blocks with its job id until a later success.
- Suspensions block with their reason; unreadable suspensions give UNKNOWN.
- Healthy, stale and not-ok workers; no heartbeats gives null.
- Recoveries (24 h / 7 d / refused) and products completed in 24 h.
- Unreadable jobs give null sections.
- Owner-only route and statement probe.

**Mutants: 18/18 killed.**

- self-observation counted
- ran = useful
- exhausted scan reads NONE
- IDLE reads OK
- superseded dead letters ignored
- dead letters not blocking
- suspensions ignored
- unreadable suspensions treated as readable
- stale heartbeat healthy
- not-ok heartbeat healthy
- no heartbeats → 0
- failed not counted as waiting
- unreadable jobs → [] / {}
- reclaims not counted
- refused recoveries counted
- any certify counted
- packages not distinct
- no-op counted as a transition

# Slice 3 — PWA pages

Two new views under More:

- `#/catalogue` (`views/catalogue.js`):
  - totals: a tile per stage, including a separate Unknown tile;
  - families, from the server's SQL totals;
  - a filters form (search, stage, family, held) and a pager that re-query the server one
    page at a time (25 per page);
  - each row shows stage, family, holds, next action and owner, the why, and an Evidence
    disclosure (certificate, per-terminology PDF hashes linked to `/api/cc/store/pdf/{slug}`,
    gallery linked to `/api/cc/visual/evidence/{slug}`, listing package, and Etsy id, state,
    read-back and intent).
- `#/agents_evidence` (`views/agents_evidence.js`):
  - 24 h tiles;
  - workers;
  - queue by stage;
  - one row per department with all of the slice-2 fields;
  - recoveries.

Wiring: `api.js` gains the `catalogue` and `operatingEvidence` endpoints, `routes.js` the two
More items, and `sw.js` goes to **`cc-shell-v33`** (from INTEG2's v32) with both views in
SHELL. There is a single bump.

cc_mock:

- `data.catalogue(searchParams)`: 64 products, one UNKNOWN. It pages and filters the way the
  server does; totals are over all 64.
- `data.operatingEvidence()`: three departments, one each OK, BLOCKED and UNKNOWN; one
  healthy and one unhealthy worker.
- `server.mjs` routes both.

`check.mjs`:

- Both tabs join the every-tab sweep: no error state, no horizontal scroll at 390 px, no
  console errors, and tap targets checked.
- The More list is pinned with both ids.
- Catalogue checks:
  - "Products: 64" from the totals;
  - the Unknown stage tile is 1;
  - page 1 of 3 with 25 rows;
  - Next gives page 2 with no repeats;
  - the underivable row reads Unknown for both stage and owner;
  - the stage filter narrows, and rows show read-back and PDF hashes;
  - search works;
  - no stray `null` text node, and no null, undefined or NaN printed.
- Agent evidence checks:
  - the blocked department names its reason;
  - an exhausted scan and unread suspensions read Unknown (never "none" or "not blocked");
  - the last useful job, queue age and useful vs no-op are shown;
  - healthy and unhealthy worker tiles.

**Bugs the browser checks found and I fixed:**

- Raw `UNKNOWN` strings were printed in rows.
- `replaceChildren` printed a null child as the text "null". I also saw this in a 390 px
  screenshot.

**Page mutants: 5/5 killed** (UNKNOWN printed raw, null child printed, pager repeats the
page, unknown scan reads none, unread suspensions read clear).

# Suites on the clean tree at 9e8e0388 (run 20261119T153953Z-1510)

Venv, `JOBS=4 SUITE_REGISTRY=0`: **18 suites, 561 passing, 0 failing, 0 tmp leak.**

- The two new suites:
  - test_eng_catalogue
  - test_eng_catalogue_agents
- The 12 required guard suites:
  - test_vacuity
  - test_w3_tmp_hygiene
  - test_w4_resume_runner
  - test_route_auth_default_deny
  - test_web_security
  - test_s4_p0_board
  - test_v11_pwa_static
  - test_v11_pwa_browser (257 browser checks)
  - test_w4_ccux
  - test_etsy_oauth_callback
  - test_w4_fmbatch1_retention_guard
  - test_w4_adopt_manual_listing
- Four suites that read the SW version or the cc_mock fixture:
  - test_w4_fmbatch1_pwa
  - test_w4_ownerhome
  - test_first_listing_doors
  - test_w4_launch_review_card

# Open items, honest

- **18-stage list.** This is still my mapping, pending the owner's list.
- ~~PDF and gallery evidence in tests~~ **Closed at 85896793:**
  `test_pdf_gallery_and_listing_evidence_reach_the_row_end_to_end`.
  - It seeds a certified release with its `assets.build` job, per-terminology PDF hashes,
    `assets.listing_images_built`, `listing.seo_drafted` and a bound listing. The row derives
    to Listing package completed and carries the certificate, PDF hashes with link, gallery
    with link, and listing-package ids. The rows are removed afterwards.
  - 4/4 evidence-mapping mutants killed (pdf, gallery, listing package, certificate dropped).
  - Suite run at 85896793 (20261119T154644Z-22600): 561 passing, 1 suite failing.
    `test_w4_resume_runner::test_p09_a_finalize_failure_fails_the_run_and_never_fails_open`
    failed under the 18-suite parallel load. It then passed twice in isolation
    (20261119T155131Z-11103 and 20261119T155307Z-28777, 53/53 with `test_eng_catalogue`).
    This commit changes only `tests/test_eng_catalogue.py`. I am reporting it as a flake
    under load, not waiving it.
- **Last useful job cost.** It costs up to 5 queries of 200 rows per department per uncached
  read. The endpoint is not cached, so each page load re-reads.
