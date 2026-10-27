# W4-INTELREC clusters C05 and C06 (Workstream C, 2026-10-27)

Source: `origin/claude/w4-FMBATCH2:brambleloop/research/final_build/w4/CLUSTERS.md`.

**Paths checked before starting:**
- present: `src/brambleloop/intel/`, `teardown/`, `radar/`, `seasonal/`, `store_foundation/`;
- absent: `src/brambleloop/launch/mix.py`, which C06 names. It is created in C06.

OFFLINE: all evidence here comes from fixtures, not production.

## C05: Market Intelligence and the research agent (15 rows)

| ID | Done here / where it stands | Test |
|---|---|---|
| F-401 | Built earlier: `intel/research_agent.py` (invokable, plus a daily `research.sweep`). | `test_w4_research_agent` |
| F-402 | Internal evidence first (`internal_evidence`), then F-406's external escalation, inside `investigate`. Nothing at runtime designs novel machinery, so there is no further hook to gate. | as F-406 |
| F-404 | Built earlier: a stale learning domain triggers research (`stale_domains_to_research`). The conflicting-evidence half is FMBATCH1's F-426 reconcile rule. | `test_w4_research_agent` |
| **F-406** | **Built.** When internal evidence cannot settle a platform question, `research_agent.official_sources` finds the primary pages this company already knows (`gates.policy_knowledge`), restricted to the fetch allowlist. They are recorded on the task (`detail.fetch_urls`), and `research_fetch.plan_fetches` now plans them. With the fetch step ON, the task waits open (`AWAITING_EXTERNAL`) for the read and then holds a `fetched` source. With it OFF, the stop names the pages and the switch. A page that failed to read is not retried every run. | `test_f406_*` (2) |
| F-429 | Built earlier: `research.flag_architecture`, read by `improve.weekly`. The traceability generator now maps it. | `test_w4_research_agent` |
| F-436 | Built earlier: the method ladder, cheapest adequate method first. Now mapped in traceability. | `test_w4_research_agent` |
| F-438 | **Not built: needs a decision.** Literature access needs a provider or an allowlist entry (for example arXiv's public API). The fetch allowlist was bounded by coordinator directive (2026-10-26), so adding a host is a coordinator or owner call. | (none) |
| F-441 | FMBATCH1 cdf4dea0 (licence, reversibility and maintenance per provider). The provider-trial records are the visual lane's. Not duplicated here. | (FMBATCH1) |
| F-446 | No research-specific lane, and none is needed. A blocked research question stops with an escalation (`R.stop`) and holds no worker, so other work runs. A dedicated lane would be a change in `runtime/lanes.py`, which is outside this cluster's files. | (design) |
| F-450 | Met by F-401 + F-404 + F-406: unknowns are detected (sweep), researched (internal, then allowlisted external) and escalated with the smallest action. | as above |
| F-224 | Built earlier: `visual/photo_principles.py` (`creative.photo_principles`). | `test_w4_photo_principles` |
| **F-231** | **Built.** `intel/gallery_grammar.py` quantifies the judged galleries per pod, using only the closed `shot_type` and the gallery rank. It reports image count, hero composition, close-up frequency, the model-vs-product mix, the first close-up's position and within-listing consistency. Lighting, background and framing are free text in `intel.vision`, so they are reported UNMEASURED. Stored daily by `creative.photo_principles`. | `test_f231_*` (2) |
| F-367 | Built earlier: `creative.children.competitive_study` (in `intel.children_portfolio`). | `test_w4_children` |
| F-789 | **Owner ruling, not built.** Reconstructing a purchased pattern's full architecture conflicts with CLAUDE.md ("never copy competitor pattern instructions"). Left for the owner, as before. | (none) |
| **F-565** | **Built.** `intel/insights_score.py` scores each owner-recorded Marketplace Insights term from searches ÷ competing listings, trend, Product Truth feasibility (a matched seed in a form with prototype geometry), policy eligibility (protected terms), expected margin (net contribution vs the floor) and catalogue fit (a storefront section). The raw snapshot is kept apart and never altered. An ineligible, infeasible or below-floor term gets no score; a term with no search count is UNKNOWN. The score is in the daily `market_intel` reading (`insights_opportunities`). | `test_f565_*` (3) |

**INTELREC residuals (review 720b291), committed separately:**
- **N-5:** a withheld paid step no longer marks a listing processed for good. It is revisited, in place, once a run would not withhold it. Test: `test_a_withheld_listing_is_revisited_once_paid_work_is_authorised`.
- **N-8:** the follow-on must pass `commerce.replication.check_proposal` and hold one of the study's causes, or it is parked (`not_adjacent`). Weeks live are counted from first certification. Tests: `test_n8_*`.

**Pre-existing failures on INTELREC 1d1c012d, not caused here** (the same tests fail on a clean checkout of 1d1c012d):
- `test_cert_intel_wave.test_director_company_view_uses_real_photography_and_queues_photography_when_behind`
- `test_cert_intel_wave2.test_a_material_policy_change_opens_a_blocking_incident_until_reviewed`

## C06: children's catalogue and launch mix (7 rows)

| ID | Done here / where it stands | Test |
|---|---|---|
| F-351 | Built in AGENTS C1: `creative.children.portfolio`, the daily `intel.children_portfolio`. | `test_w4_children` |
| F-353 | Built in C1: the 13 core categories, each researched or named as a gap. | `test_w4_children` |
| F-358 | Built in C1: neutral, gendered and style segment counts; no palette inferred. | `test_w4_children` |
| F-359 | Built in C1: children's sibling sets from `creative.family_engine` (recolour duplicates flagged). | `test_w4_children` |
| F-365 | Built in C1: a Baby & Kids collection proposed only at depth 4, with navigation by family and by age range (age range UNMEASURED where no audience is recorded). | `test_w4_children` |
| **F-366** | **Built:** `launch/mix.py` (`optimize`). It runs `radar.opportunity.select_portfolio`, measures the result by the five segments and repairs it: at least one children's product when an eligible one exists, and no segment above 50 % of the mix. Each swap evicts only a pick whose removal breaks none of section 33's constraints, and each is recorded. | `test_f366_*` (2) |
| **F-370** | **Built:** `launch/mix.rebalance`. It proposes bounded share changes from measured per-segment conversion. It does nothing below 500 measured visits per segment or with fewer than two measured segments (UNMEASURED). It moves at most 10 points per review and never goes outside the owner's minimum and maximum share. It is a recommendation only: nothing is added, removed or repriced. | `test_f370_*` |

The traceability generator now maps F-353, F-358, F-359, F-365, F-366 and F-370, and the file is regenerated.
