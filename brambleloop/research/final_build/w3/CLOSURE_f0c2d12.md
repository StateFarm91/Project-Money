# Final Master v1.1 closure on f0c2d12 (wave-3 lane K)

Head: `f0c2d12580b1658206295608bb7b99d5a956620b` (`claude/v11-CANON`, base of wave 3).
Machine-readable result: `CLOSURE_f0c2d12.json`. Script: `closure_w3.py`, which can be re-run.

## How this was produced

1. **Reachability was regenerated on this head.** I used the FINAL_BUILD_RESUME_MANIFEST §14 snippet to write `module_reachability.json`. It now covers 503 modules, of which 425 are reached; before this run it covered 418, with 360 reached. No module that was reached before is now unreached.
2. **The mechanical layer was regenerated.** `aggregate.py` was re-run, writing `closure_matrix.json` and `LAUNCH_SCOPE.json`. Only the basis line changed. `tests/test_final_closure_matrix.py` passes all 12 tests.
3. **The mechanical layer is out of date by construction.** Its mapping rows are still from 019ebf0 and 6f9a2f7. Nothing merged since then is visible to it: FB-4 (PUB/FIN/OPS/STORE/LC/J/LAUNCH), rc1, v1.1 lanes A–I, r2 or CANON.
4. **Triage layer.** I re-checked every launch-critical OPEN row myself against this head. I started from `partial_classification_376c54b.json`, then looked at the commits since then, then checked the code and tests by grep.
   - A row moved to resolved (code **R**) is re-run through `aggregate.cap()` and `completion()`. If its producer module is unreached or its test is missing, it is still capped.
   - **R is a re-map claim, not certification (F-867).** The integrator has to accept it before maturity rises in the canonical matrix, either through `mapping/remap_f0c2d12/` or through `overrides.json`.

## Counts — v1.0 (F-001..F-879; 866 records)

| | Mechanical (canonical) | Wave-3 triage |
|---|---|---|
| Launch-critical COMPLETE | 73 | **138** |
| Launch-critical GATED | 66 | **91** |
| Launch-critical OPEN | **300** | **210** |
| Not launch-critical: POST-LAUNCH | 420 | 420 |
| Not launch-critical: NOT-APPLICABLE | 7 | 7 |

The 210 rows still OPEN after triage break down as follows:

| Kind of OPEN row | Rows | What it needs |
|---|---|---|
| Buildable now | 181 | Code, in clusters K1–K14 |
| PROCESS | 10 | Release-process steps on the successor candidate |
| STRUCTURAL | 16 | An integrator decision, not code (explained below) |
| REMAP | 3 | Probably superseded by lane E accounting; not verified |

The triage codes across all OPEN rows were R 69, G 25, O 181, P 10, S 12, M 3. Of the 69 R rows, 65 now compute as COMPLETE. The 4 that are still capped are F-178, F-836, F-837 and F-847: their producer is the offline adjudicator, so they count as STRUCTURAL.

**Caveat:** the 66 rows that were already mechanically GATED were not re-verified. Some may be stale; for example, the F-808 `owned_surfaces` gate may be affected by the fb4 lesson links.

## Counts — v1.1 (F-880..F-930; 51 records)

| Verdict | Rows | Detail |
|---|---|---|
| COMPLETE-PENDING-RECERT | 35 | Built and wired; suite green on ddf9c6e; the J audit found 0 launch-blocking issues; the r2 repairs have not been re-certified |
| GATED | 8 | F-880, F-881, F-895 and F-923 need `production_window`. F-897 needs CASL review and owner authority. F-904 and F-908 need a bank or Etsy ledger feed (data). F-924 needs hosted operating history (data). |
| OPEN | 8 | K15 (7 rows) and K16 / F-926 (1 row) |

Under the strict vocabulary of `aggregate.py`, the 35 rows pending re-certification are still OPEN: the remaining step is a successor freeze plus re-certification.

**Unregistered scope:** the Laura rulings (spec/07, D-FB-11..13) and the owner's rejection of the store preview are not F-rows. Under F-847 they should be entered as registry rows or `overrides.json` entries.

## OPEN launch-critical clusters (buildable; none is gated)

LB means the cluster blocks launch, either because the 376c54b classifier flagged it or because I judge so.

| Cluster | Rows | Size | Likely files | Wave-3 lane overlap | Depends on | LB? |
|---|---|---|---|---|---|---|
| **K2** Storefront completion and shop-trust gate | F-233 F-234 F-235 F-237 F-263 F-279 | M | `brand/storefront.py::check_storefront` (line 249 passes on banner/icon **brief strings**), `commerce/shop_package`, `launch/readiness` | A (asset files), B, C | A's icon/banner files; C's `copy_v2` | **YES**: the trust ladder `shop_complete` passes on text briefs |
| **K15** v1.1 provider reachability | F-907 F-909 F-913 F-914 F-915 F-916 F-927 (details below) | S | `app/command_center/providers.py`, `build2/reachability.py`, `finance/accounting/*`, `autonomy/status.py` | F (`providers.py`), E (accounting), D (autonomy) | none | **YES** for the v1.1 money and timeline rows |
| **K16** Store preview v2 | F-926 | L | `store_foundation/preview.py` and its copy | B, C, A | owner Etsy login for live settings | **YES** (owner directive) |
| **K1** Search and listing truth residuals | F-001 F-002 F-013 F-022 F-028 F-030 F-058 F-060 F-242 F-251 F-254 F-255 F-257 F-291 | M | `commerce/search.py`, `commerce/seo.py`, `publish/listing_assets.py`, `publish/eligibility.py`, `gates/platform_policy.py` | G (I for schema) | none | no; the Launch-0 search certificate already passes on the merits |
| **K3** ListingOutcome producer (no runtime writer) | F-258 F-259 F-260 F-261 F-282 F-297 | M | `creative/style_learning.record_outcome` (uncalled), a new opsauth intake route, `growth/experiments`, `commerce/listing_tests` | G (minor) | real numbers are then gated on `live_listings` data | no, before launch |
| **K4** Launch verdict, demand-capture plan and visibility view | F-275 F-276 F-281 F-286 F-287 F-288 F-289 F-300 | L | `launch/readiness`, `commerce/launch`, `scale/leading`, `growth/mix` | F, G, D | K3 | partly: F-300 means a phase change does not require `readiness.ready` |
| **K5a** Spend attribution and reporting | F-070 F-103 F-105 F-106 F-110 F-183 F-184 F-303 F-304 F-305 F-319 F-320 F-322 F-325 F-326 F-629 | M | `finance/spend_report`, `finance/governor`, `finance/unit_cost`, `ops/provider_accounts`, `visual/reliability` | none (lane E F-907 may overlap) | none | no |
| **K5b** Paid-call discipline in the gateway and worker | F-098 F-109 F-306 F-307 F-308 F-309 F-310 F-311 F-312 F-313 F-314 F-315 F-316 F-317 F-318 F-328 F-339 F-472 F-474 F-659 | L | `gateway/routing`, `gateway/model_gateway`, `queue/durable`, `swarm/orchestrate`, `runtime/worker`, `intel/vision`, `finance/spend_policy` | D owns `worker.py` and `orchestrate.py` | none | no; F-307/F-339 (re-spend on lease reclaim) is the riskiest |
| **K6** Risk-based physical evidence | F-072 F-073 F-078 F-080 F-086 F-117 | M | a new `gates/risk_matrix.py`, `gates/certificate`, `gates/policy`, `launch/readiness`; F-078 needs a re-test owner action | none | none | no |
| **K7** Ops truth, provenance and owner surfaces | F-115 F-121 F-122 F-124 F-127 F-154 F-161 F-162 F-167 F-168 F-173 F-174 F-176 F-180 F-195 F-197 F-199 F-203 F-204 F-337 F-338 F-343 F-392 F-623 F-665 F-870 | L | `ops/artefacts`, `ops/backfill`, `ops/health`, `ops/incident_lifecycle`, `OwnerAction` lifecycle (`core/models` migration), dashboard | F, D (`core/db`) | none | no |
| **K8** Etsy estate, orders and CX | F-250 F-514 F-518 F-535 F-537 F-544 F-545 F-553 F-559 F-568 F-585 F-592 F-689 | L | `runtime/etsy_ops` (census of files and images), `intel/etsy_surfaces`, `commerce/terms`, `orders_ingest`, `support/`, routes | **I** | real data is gated on `transactions_r` and `live_listings` | no |
| **K9** Pattern truth for graded garments (not Launch-0) | F-362 F-363 F-750 F-751 F-753 F-755 F-756 F-761 F-762 F-763 F-768 F-770 F-777 F-779 F-784 F-792 F-794 F-795 | L | `cir/model`, `cir/graded`, `cir/stitches`, `publish/pdf`, `gates/policy`, `gates/originality`, `teardown/reader`, `intel/childrens` | none | none | no for Launch-0; these are candidates to move to post-launch |
| **K10** Learn residuals | F-799 F-801 F-805 F-806 F-826 | M | `learn/service`, `learn/api`, `improve/` | none | none | no |
| **K11** Authority and governance model | F-497 F-658 F-669 F-700 F-702 F-703 F-708 F-721 F-743 | L | `agents/registry`, `improve/governance`, an awaiting-approval job state, an AuthorityPolicy table | **D**, F | none | no; check whether D's orchestrator already covers F-658 |
| **K12** Visual residuals (model photography) | F-212 F-213 F-219 F-677 F-732 F-877 | M | `gateway/images`, `visual/identity`, `visual/provider_trial`, `visual/parity` | **H** | Laura identity rulings (spec/07) | no; off the Launch-0 path (D-FB-7) |
| **K13** Closure and certification tooling in code | F-123 F-129 F-130 F-133 F-136 F-382 F-400 F-831 F-832 F-833 F-834 F-838 F-844 F-860 F-867 F-879 | M | `build2/closure`, `maturity`, `reachability`, `final_proof`, `executor`; `launch/readiness` driven by `LAUNCH_SCOPE` | K (research side only) | none | no |
| **K14** Supply chain, deploy and operator-tooling residuals | F-135 F-158 F-159 F-331 F-333 F-335 F-341 F-342 F-380 F-381 F-397 F-416 | S | `Dockerfile` (pin by digest), lock evidence, secret-scan of PDF streams, `run_tests.sh` sentinel and self-enrolment, `ops/registry` | none | the deploy itself is `production_window` | no |

K15 row details:
- **F-909** (`tax_pack`) and **F-916** (`handoff`) have **no runtime caller at all**.
- **F-907** (`attribution`) is unreached.
- **F-913, F-914, F-915** (`dashboard`/`forecast`) and **F-927** (`autonomy/status.timeline`) are loaded through `importlib` from `PROVIDERS`, which the C-65 rule cannot see. Either make those imports static, or teach the reachability rule to read the `PROVIDERS` table.
- `seo/status` and `learn/improvement_status` are unreached the same way.

## Non-code items

**PROCESS** (the successor candidate on the integrated wave-3 head): F-169 (clean-tree suite), F-177 and F-843 (fold the re-map), F-839 (independent re-audit of the final head), F-840, F-845 (freeze; ddf9c6e's r2 repairs are not frozen), F-846 (re-audit), F-848 (rehearsal), F-878 (run `scripts/launch_packet.py` on the successor), F-841 (historical).

**STRUCTURAL** — an integrator override is needed, with a reason. Each of these rows' producer is `run_tests.sh`, a test, repo-root `ops/*.py`, or the offline `aggregate.py`/`final_proof.py`, so it can never reach a runtime root, and TESTED is its ceiling. The rows are F-170 F-178 F-205 F-332 F-334 F-340 F-344 F-345 F-346 F-347 F-348 F-349 F-350 F-836 F-837 F-847.

**REMAP** — these probably close under lane E accounting (F-903/F-904), but I did not verify that: F-558, F-608, F-609.

## GATED (exact gate) — wave-3 triage, launch-critical v1.0 and v1.1

| Kind | Gate key | Rows |
|---|---|---|
| owner | `etsy_api` | F-005 F-007 F-009 F-010 F-243 F-247 F-437 F-542 F-594 |
| owner | `etsy_shop` | F-040 F-240 F-299 F-515 |
| owner | `image_vision` | F-027 F-031 F-041 F-252 F-253 F-278 |
| owner | `production_window` | F-371 F-396 F-495 F-540 F-654 F-701 F-718 F-733 F-849 F-850 F-880 F-881 F-895 F-923 |
| owner | `production_deploy` | F-144 F-171 F-172 |
| owner | `transactions_r` | F-273 F-283 F-501 F-538 F-682 F-872 |
| owner | `tester_roster` | F-081 F-118 |
| owner | `offsite_storage` | F-152 F-628 F-697 |
| owner | `model_provider` | F-100 F-871 |
| owner | `publication_authority` | F-543 |
| owner | `payout` | F-577 |
| owner | `ad_authority` | F-295 |
| owner | `credential_rotation` | F-160 |
| owner | `deploy_trigger_config` | F-461 (the pre-push hook can be skipped; Railway auto-deploys) |
| owner | `casl_notification_authority` | F-897 |
| owner | `etsy_ai_partner_guidance` | F-588 |
| owner | `legal_and_tax` | F-578 |
| owner | `insights_access` | F-059 |
| owner | `owned_surfaces` | F-808 |
| owner | `physical_proof` | F-360 |
| owner | `policy_settings` | F-587 |
| owner | `provider_usage_api` | F-301 |
| owner | `spend_policy numbers` | F-695 |
| data | `live_listings` | F-248 F-280 F-321 F-524 |
| data | `customers` | F-088 F-284 F-323 |
| data | `insights_access` | F-246 F-249 F-285 |
| data | `bank_and_payment_ledger_feed` | F-904 F-908 |
| data | `hosted_operating_history` | F-924 |
| external | `model_bearing_render` | F-676 F-731 F-734 F-736 F-740 F-741 F-746 |
| external | `visual_v1_provider_capability` | F-221 F-222 F-225 F-227 F-674 F-851 |
| external | `rendered_pages` (Etsy returns 403) | F-039 F-042 F-239 F-293 F-536 |
| external | `no_messages_api` | F-556 F-557 F-617 |
| external | `image_vision` | F-364 |
| external | `customer_service_stats` | F-532 |

## What I could not verify

- **R rows were checked by one auditor**, by grep and by checking that the tests exist. I did not run those tests.
- **None of this is runtime proof.** Whether the producer runs in production is known only for modules in fcb982d.
- **Mechanically GATED rows were not re-checked.**
- **The M rows were not checked.**
- **No full suite was run** (that was forbidden by the lane rules).
