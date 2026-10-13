# ACTIVATION_MATRIX (DRAFT, incomplete)

**DRAFT: stopped on owner instruction (release certification has priority).** Base `origin/claude/w4-INTEG2` 6cd2fcb.
Production 7bbbe72, read-only GETs 2026-10-13, saved in `evidence_ACTIVATION/`.

## Production readings (verified)
- `/api/verify` ok=false: `worker_is_alive`, `no_unexpected_dead_letters_in_24h` (the dead-letter fixes are on claude/w4-B2CLOSE 2190561 and need only the next deploy).
- model_provider: usable (model.probe ok 2026-10-13T00:00Z; CA$12.01 of CA$100 spent this month).
- image_vision: usable (vision.probe ok 2026-10-12T17:42Z). Most listing frames stay `unjudged`; VISROLE has to be deployed first.
- etsy_api: usable (ping ok 2026-10-12T18:00Z).
- culture_feed: usable (wikimedia_pageviews, 480 sourced observations).
- rendered_pages: closed (no BRAMBLELOOP_BROWSER_URL is set).

## Gate table (from production /api/build; most columns not yet filled)

| capability | requirement IDs | current state in prod | exact activation dependency | owner action | cost CAD | activation step | production acceptance test | class |
|---|---|---|---|---|---|---|---|---|
| benchmark_observation | - | OPEN | see executor.GATES | TBD | TBD | TBD | gate reads open in /api/build | TBD |
| model_provider | B2#94 | OPEN | see executor.GATES | TBD | TBD | TBD | gate reads open in /api/build | TBD |
| etsy_shop | - | OPEN | see executor.GATES | TBD | TBD | TBD | gate reads open in /api/build | TBD |
| etsy_api | - | OPEN | see executor.GATES | TBD | TBD | TBD | gate reads open in /api/build | TBD |
| image_vision | B2#15, B2#44, B2#61, B2#67, B2#86, B2#88, B2#116, B2#126, B2#218, B2#277, B2#281, B2#304, B2#308, B2#309 | OPEN | see executor.GATES | TBD | TBD | TBD | gate reads open in /api/build | TBD |
| rendered_pages | B2#35, B2#39 | closed | see executor.GATES | TBD | TBD | TBD | gate reads open in /api/build | TBD |
| transactions_r | B2#11, B2#12 | OPEN | see executor.GATES | TBD | TBD | TBD | gate reads open in /api/build | TBD |
| insights_access | B2#1, B2#37, B2#54, B2#236, B2#237 | closed | see executor.GATES | TBD | TBD | TBD | gate reads open in /api/build | TBD |
| acceptance_ruling | B2#189, B2#221, B2#222, B2#320 | closed | see executor.GATES | TBD | TBD | TBD | gate reads open in /api/build | TBD |
| tester_roster | B2#9, B2#43, B2#250 | closed | see executor.GATES | TBD | TBD | TBD | gate reads open in /api/build | TBD |
| image_generation | - | OPEN | see executor.GATES | TBD | TBD | TBD | gate reads open in /api/build | TBD |
| canonical_model | - | OPEN | see executor.GATES | TBD | TBD | TBD | gate reads open in /api/build | TBD |
| benchmark_purchases | B2#163, B2#165, B2#168, B2#315, B2#317 | closed | see executor.GATES | TBD | TBD | TBD | gate reads open in /api/build | TBD |
| production_window | B2#195 | closed | see executor.GATES | TBD | TBD | TBD | gate reads open in /api/build | TBD |
| offsite_storage | B2#51 | closed | see executor.GATES | TBD | TBD | TBD | gate reads open in /api/build | TBD |
| owned_surfaces | B2#4, B2#10, B2#246, B2#247, B2#248, B2#251, B2#255 | closed | see executor.GATES | TBD | TBD | TBD | gate reads open in /api/build | TBD |
| live_listings | B2#14, B2#16, B2#46, B2#238, B2#239, B2#241, B2#254, B2#263, B2#266 | closed | see executor.GATES | TBD | TBD | TBD | gate reads open in /api/build | TBD |
| customers | B2#8, B2#18, B2#19, B2#20, B2#21, B2#25, B2#28, B2#31, B2#33, B2#41, B2#45, B2#48, B2#120, B2#147, B2#169, B2#226, B2#229, B2#235, B2#242, B2#243, B2#244, B2#245, B2#252, B2#253, B2#256, B2#257, B2#258, B2#260, B2#265, B2#270, B2#272, B2#280, B2#292 | closed | see executor.GATES | TBD | TBD | TBD | gate reads open in /api/build | TBD |
| physical_proof | B2#64 | closed | see executor.GATES | TBD | TBD | TBD | gate reads open in /api/build | TBD |
| second_market_benchmark | - | closed | see executor.GATES | TBD | TBD | TBD | gate reads open in /api/build | TBD |
| culture_feed | B2#140 | OPEN | see executor.GATES | TBD | TBD | TBD | gate reads open in /api/build | TBD |
| model_bearing_render | B2#72, B2#130, B2#202, B2#203, B2#300 | closed | see executor.GATES | TBD | TBD | TBD | gate reads open in /api/build | TBD |
| ad_authority | B2#294, B2#295 | closed | see executor.GATES | TBD | TBD | TBD | gate reads open in /api/build | TBD |

## Not done
- Env-switched and default-off features (BRAMBLELOOP_* switches): not yet enumerated.
- Roadmap and presence rows marked GATED: not yet covered.
- Private Laura, executive intelligence and autonomy rows: not yet covered.
- Owner actions, costs and the "next deploy only" marking: not yet filled.
