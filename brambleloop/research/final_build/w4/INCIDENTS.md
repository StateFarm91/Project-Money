# Incidents -- the 18 production held open (W4-OWNER)

Generated 2026-10-07T01:11:19+00:00. Source: production /api/status open_incidents=18 (fcb982d, 2026-10-06); reproduced by tests/test_w4_owner_incidents.py.

**Before:** 18 open. **After (this build's handlers):** 17 closed by rule with a resolution and resolved_at, 1 open because its condition is true; 0 need the owner; 5 current conditions re-raised year-keyed. Production converges after the next deploy (owner decision `production_window`).

Rules: duplicates close into the oldest row (incident_lifecycle.close_duplicates); a failed cadence closes once it enqueues again (close_recovered_cadences); both run on every ops.health truth sweep; closing never deletes; every close carries resolution and resolved_at.

| signature | sev | class | remediation owner | status | resolution |
|---|---|---|---|---|---|
| seasonal.at_risk:market-basket-trio:Halloween | P2 | stale/incoherent | seasonal.sentinel | CLOSED | market-basket-trio is not merchandised for Halloween (its occasion is evergreen), so it has no Halloween window to be at risk in. The row was raised when every product was scheduled against every event. |
| seasonal.at_risk:pet-snuggle-mat:Halloween | P2 | stale/incoherent | seasonal.sentinel | CLOSED | pet-snuggle-mat is not merchandised for Halloween (its occasion is evergreen), so it has no Halloween window to be at risk in. The row was raised when every product was scheduled against every event. |
| policy_stale:seller_policy | P2 | executable (company) | company | CLOSED | seller_policy read on 2026-09-26 (version 2026-09-26:search_engine_excerpt_of_official_page); the watch reports it current |
| policy_stale:creativity_standards | P2 | executable (company) | company | CLOSED | creativity_standards read on 2026-09-26 (version 2026-09-26:search_engine_excerpt_of_official_page); the watch reports it current |
| policy_stale:listing_image_rules | P2 | executable (company) | company | CLOSED | listing_image_rules read on 2026-09-26 (version 2026-09-26:search_engine_excerpt_of_official_page); the watch reports it current |
| policy_stale:advertising_rules | P2 | executable (company) | company | CLOSED | advertising_rules read on 2026-09-26 (version 2026-09-26:search_engine_excerpt_of_official_page); the watch reports it current |
| policy_stale:shilling_and_reviews | P2 | executable (company) | company | CLOSED | shilling_and_reviews read on 2026-09-26 (version 2026-09-26:search_engine_excerpt_of_official_page); the watch reports it current |
| seasonal.at_risk:mosaic-placemat-pair:Halloween | P2 | stale/incoherent | seasonal.sentinel | CLOSED | mosaic-placemat-pair is not merchandised for Halloween (its occasion is evergreen), so it has no Halloween window to be at risk in. The row was raised when every product was scheduled against every event. |
| seasonal.calendar_behind:Halloween | P2 | stale | seasonal.sentinel | CLOSED | no product lane can still reach a customer for Halloween 2026; the remaining work is next year's, which the compression programme carries. |
| seasonal.preparation_late:LONG:search_language | P3 | stale | seasonal.sentinel | CLOSED | re-keyed with the event and year as seasonal.preparation_late:Christmas:2026:search_language; the old signature named a lane and no occasion, so it could never close. |
| stale-artefact:backlog | P3 | true condition | ops.sentinel + rebuild graph | OPEN (condition true) | - |
| seasonal.calendar_behind:Thanksgiving (CA) | P2 | stale | seasonal.sentinel | CLOSED | no product lane can still reach a customer for Thanksgiving (CA) 2026; the remaining work is next year's, which the compression programme carries. |
| build.stalled | P2 | stale | build.tick | CLOSED | nothing is ready: every remaining requirement is parked on a gate, which is waiting rather than a stall |
| seasonal.at_risk:pressed-flower-motifs:Halloween | P2 | stale/incoherent | seasonal.sentinel | CLOSED | pressed-flower-motifs is not merchandised for Halloween (its occasion is evergreen), so it has no Halloween window to be at risk in. The row was raised when every product was scheduled against every event. |
| policy_stale:children_and_baby | P2 | executable (company) | company | CLOSED | children_and_baby read on 2026-09-26 (version 2026-09-26:search_engine_excerpt_of_official_page); the watch reports it current |
| seasonal.at_risk:nordic-forest-bundle:Halloween | P2 | stale/incoherent | seasonal.sentinel | CLOSED | nordic-forest-bundle is not merchandised for Halloween (its occasion is Christmas), so it has no Halloween window to be at risk in. The row was raised when every product was scheduled against every event. |
| seasonal.preparation_late:MEDIUM:search_language | P3 | stale | seasonal.sentinel | CLOSED | re-keyed with the event and year as seasonal.preparation_late:Christmas:2026:search_language; the old signature named a lane and no occasion, so it could never close. |
| seasonal.at_risk:nordic-forest-mosaic-throw:Christmas | P2 | stale/incoherent | seasonal.sentinel | CLOSED | nordic-forest-mosaic-throw has no seasonal plan this run (it is not a certified product in the catalogue the calendar schedules), so it has no Christmas launch window to be at risk in. It is raised again if it is certifi |

## Re-raised by this build (current, year-keyed)

- `seasonal.at_risk:winter-village-graphghan:Christmas:2026` (P2): winter-village-graphghan has 20 days of runway left for Christmas 2026: past its preferred launch date and inside the last window where reallocating effort still changes whether a customer can finish 
- `seasonal.calendar_behind:Christmas:2026` (P2): Christmas 2026: 1 of 10 collection milestones are already past with no evidence (listing_indexing_date) while winter-village-graphghan, nordic-star-ornaments target it and a MEDIUM product can still r
- `seasonal.calendar_behind:Valentine's:2027` (P2): Valentine's 2027: 1 of 10 collection milestones are already past with no evidence (physical_test_deadline) while valentine-heart-garland target it and a LONG product can still reach a customer. A miss
- `seasonal.preparation_late:Christmas:2026:search_language` (P3): search_language for Christmas 2026 (MEDIUM) should have started 11 days ago and nothing shows it has (mjs.scanned/culture.sweep/learning.ingested). map buyer language before the copy is written, or th
- `seasonal.preparation_late:Christmas:2026:creative_assets` (P3): creative_assets for Christmas 2026 (MEDIUM) should have started 4 days ago and nothing shows it has (assets.built/assets.listing_images_built). photography and thumbnails take longer than anybody plan
