# W4-FIRSTSALE2: every first-sale Etsy surface has a truthful collector

**Context**
- **Branch:** `claude/w4-FIRSTSALE2`, from `origin/claude/w4-INTEG4` 6531769, which already
  contains W4-FIRSTSALE cc0c54e.
- **Production:** read only, with one GET to `/api/audit?action=commerce.orders_ingested`.
  - Nothing was deployed, POSTed, published or spent.
  - Etsy was not called.
- **The finding:** W4-CLOSE6 §11, from `origin/claude/w4-CLOSE6` e93b2fc.

## The defect

**First-sale readiness could never pass.**
- `launch.readiness.etsy_first_sale_surfaces` is ready only when every required surface is FRESH.
- Five required surfaces had `collector=None`: messages, orders, legal_and_tax, digital_files and
  taxonomy_and_attributes.
- A surface with no collector reads NO_COLLECTOR forever, so the item could not become ready,
  even after every owner action was done.

**A stale owner action on `orders`.** The surface also named `reauthorise_transactions_r`, which
is no longer true.
- Production on 2026-10-20 (12:02Z and 06:04Z) records `commerce.orders_ingested` with
  `ran: true`, `gate_missing: []` and 2 network calls on every cadence.
- So transactions_r is granted and receipts are read.

## The fix

**Each surface now has a named collector** (`launch/first_sale_surfaces.py`, new), registered in
`intel.etsy_surfaces.COLLECTORS` with a staleness tolerance:

| surface | collector | the reading | tolerance | satisfied only when |
|---|---|---|---|---|
| orders | `orders_ingest` | the latest `commerce.orders_ingested` with `ran: true` (its own timestamp) | 1 day | `orders_ingest.gate` is open **now** and that read recorded no gate gap |
| taxonomy_and_attributes | `taxonomy_match` | the newest Etsy taxonomy snapshot (`confirmed_at`) | 2 days | every Launch-0 release has a search profile that is CHOSEN on a node present in that tree, and the certificate's own `attributes` check is true |
| digital_files | `digital_deliverables` | `commerce.deliverables.durable_state`, re-hashed from Postgres at read time | 1 day | every Launch-0 release's certified US and UK PDFs are held, and the files (under the buyer-facing names) break none of Etsy's published digital-file rules (`etsy_constraints.digital_file_problems`) |
| messages | `shop_observation` | the owner's dated reading, POST `/api/etsy/shop-observation`, page `messages` | 30 days | complete; `notifications_inbox` is non-empty; `reply_window_hours` > 0 |
| legal_and_tax | `shop_observation` | the owner's dated reading, page `legal_and_tax` | 90 days | complete; `identity_verified` is true; `tax_position` is stated; `decided_on` is an ISO date |

**Evidence rules** (`intel.etsy_surfaces.evidence_state`):
- **New state, FAILING:** a current reading that measured the requirement unmet
  (`satisfied: false`). It is never FRESH.
- **No reading at all:** NO_EVIDENCE, never a pass. For example: no snapshot, no completed
  receipt read, nothing certified, or the page never observed.
- **Unreadable collector:** also NO_EVIDENCE.
- **Old reading:** STALE.
- **Reading dated in the future:** STALE, as before.
- The readiness clock is passed through, so a live reading cannot be dated after the check.

**The stale owner action is fixed.**
- `orders` no longer carries a standing owner action.
- Launch readiness raises `reauthorise_transactions_r` on the orders row only while the orders
  gate is actually closed (`commerce.orders_ingest.gate`). It then reports BLOCKED_OWNER.
- The orders evidence text is corrected: the scope has been granted since the 2026-09-25 grant,
  as shown by production's readings.

**The observation intake** (`commerce.shop_observations`) gains two pages, `messages` and
`legal_and_tax`.
- They use the same append-only, dated `etsy.shop_observation` row as CLOSE6's `about` page.
- A complete reading closes `messages_watch` or `legal_and_tax_setup` only when the stated values
  meet the requirement, not when a list happens to be empty.
- Malformed values are refused: a blank inbox, or a non-boolean `identity_verified`.
- **Merge note:** CLOSE6 adds an `about` entry to the same `PAGES` dictionary. The two entries
  are independent, so on merge keep both.

## Proof

`tests/test_w4_firstsale2_surfaces.py`, 7/7:
- **Ready case.** The item **reaches ready** when every input is genuinely satisfied:
  - a passing, fresh shop snapshot and listing census;
  - a completed receipt read with the gate open;
  - every Launch-0 release filed on a node of the stored tree, with complete attributes;
  - every release's certified PDFs held;
  - the owner's dated, complete Messages and Legal and tax readings.

  All 11 surfaces are FRESH, `ready: true`, and no owner action is open.
- **One input missing.** Each of the 7 inputs is removed in turn. Each time the item is **not
  ready**. That surface reads NO_EVIDENCE, and every other surface stays FRESH.
- **Measured unmet.** These read FAILING, never FRESH:
  - identity not verified;
  - one release's attributes incomplete;
  - one certified PDF missing;
  - the orders gate closed. This also raises `reauthorise_transactions_r` and BLOCKED_OWNER.
- **Old readings.** Readings older than their tolerance are STALE.
- **Empty database.** Never ready, and nothing reads FRESH.
- **Registry.** Every first-sale surface has a registered collector and tolerance.
  `check_registry()` is clean, and `owner_queue()` no longer contains
  `reauthorise_transactions_r`.

**Changed test:** `test_w4_etsysurf::test_a_fresh_passing_shop_still_names_what_no_collector_can_observe`
asserted the defect: that five surfaces have no collector.
- It is now `..._names_every_surface_without_a_reading`.
- With only the shop and census recorded, it asserts those five surfaces are NO_EVIDENCE and the
  item is not ready.
- It is not weakened: it still asserts not ready, and now also asserts the exact state.

## What remains for production (not company-closable here)

Once this is released, production will read:

| surface | expected reading | what it needs |
|---|---|---|
| orders | FRESH | nothing more; receipts are already read every cadence |
| taxonomy_and_attributes | FAILING | B2: the category matcher's first real read (FIRSTSALE §1) |
| digital_files | NO_EVIDENCE or FAILING until the next release certifies the code's Launch-0 versions; FRESH once `assets.build` has kept their PDFs (FIRSTSALE §2) | company: the release chain, after deploy |
| messages | NO_EVIDENCE | **owner action:** POST one dated reading |
| legal_and_tax | NO_EVIDENCE | **owner action:** POST one dated reading |

**Owner actions** (already in the registry as `messages_watch` and `legal_and_tax_setup`; now
they have an evidence path):

| page | values to post | max cost | minutes |
|---|---|---|---|
| `messages` | `{notifications_inbox, reply_window_hours}` | CA$0 | 10 |
| `legal_and_tax` | `{identity_verified, tax_position, decided_on}` | none here (the registry's CA$250 ceiling is the tax position's cost, not this step's) | 30 |

**Second changed test:** `test_etsy_surfaces::test_the_scope_re_authorisation_is_an_owner_action_rather_than_a_build_task`
asserted that `orders` carries `reauthorise_transactions_r` as a standing action, which is the
stale reference.
- It now asserts that `orders` has no standing action and has its collector.
- It also asserts that re-authorisation stays an owner action, raised from the live gate
  (`orders_ingest.OWNER_ACTION_KEY`; "Only the owner ... in a browser").
- And it asserts that it is still not a first-sale-blocking owner action.

## Tests

All run through testslot, on this branch. All exit 0 with no failures, except one suite noted
below.

**Required set:**

| suite | result |
|---|---|
| test_vacuity | 8 |
| test_launch | 28 |
| test_cost_governance_wave2 | 39 |
| test_search_hero_publish | 4 |
| test_cert_listing_frames | 6 |
| test_v11_autonomy_timeline | 6 |

**New and changed:**

| suite | result |
|---|---|
| test_w4_firstsale2_surfaces | 7/7 |
| test_w4_etsysurf | 8 |
| test_etsy_surfaces | 53 (after the assertion update; 52 + 1 FAIL before it) |

**Registry, readiness, observations and owner-queue readers:**

| suite | result |
|---|---|
| test_k8_shop_cx | 17 |
| test_w3_k7_owner_queue | 10 |
| test_w4_owner_actions | 6 |
| test_w3_k4_launch_verdict | 16 |
| test_rc1_own_packet | 2 |
| test_w4_fm2_surface_reverify | 8 |
| test_w4_fmend_packet_route | 4 |
| test_w4_packetrel | 6 |
| test_w4_ccpacket | 5 |
| test_w4_etsyreview | 3 |
| test_w4_gatesb | 10 |
| test_w4_b2close | 18 |
| test_w4_b2gate2 | 11 |
| test_w4_b2gates | 12 |
| test_w4_marketintel | 7 |
| test_fb4_launch | 9 |
| test_fb4_ops | 12 |
| test_etsy_exercise | 31 |
| test_etsy_readback_observe | 37 |
| test_access | 8 |
| test_deploy | 32 |
| test_w3_tmp_hygiene | 16 |

**Not caused by this branch:** `test_fb4_lc` gives 15 OK and 1 FAIL,
`test_the_partners_unknown_reaches_coverage_and_a_new_provider_reopens_it`.
- `flux-3-image` joined the image-provider set without a production-partners re-review.
- It fails identically on the clean base, INTEG4 6531769, checked in a detached worktree.
- It belongs to the lane that added the provider.
