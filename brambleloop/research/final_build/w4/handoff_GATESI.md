# handoff — W4-GATESI (infrastructure gates, D-FB-19)

- Branch: `claude/w4-GATESI` (merged origin/claude/visual-investigation at 936a380). Latest pushed SHA: see `git log -1 origin/claude/w4-GATESI`.
- Owns gates: rendered_pages, image_vision, model_provider, offsite_storage, image_generation.

## Done
| Item | Status | Evidence |
|---|---|---|
| image_generation probe work_dir defect (prod probe 00:03Z failed on it) | FIXED, needs deploy | gateway/images.py; tests/test_w4_gatesi.py |
| offsite SigV4 region derived from endpoint | FIXED | core/offsite.py `region_for`; test_w4_gatesi, test_offsite 14/14 |
| listing_image_rules URL pointed at wrong article | FIXED | gates/platform_policy.py |
| Help Center policy reader (#39 partial) | FIXED, wired in release.handle_policy_watch, needs deploy | gates/policy_reader.py; live GET 200 x2 2026-10-07 |
| model_provider / image_vision | OWNER-GATED (one Anthropic top-up) | /api/model, /api/capabilities/probes |
| offsite_storage #51 | OWNER-GATED (B2 bucket + 5 vars) | /api/offsite |
| rendered_pages #35 #39 | EXTERNAL (DataDome 403, re-proven) + person recording | GATE_CLEARANCE_INFRA.json |

Deliverables: GATE_CLEARANCE_INFRA.md / .json (this dir).

## Tests run (all pass)
test_w4_gatesi 34/34, test_offsite 14, test_platform_policy 13, test_policy_knowledge 20, test_policy_intake 8, test_rc1_spend 20, test_w3_k12_model_photography 10, test_vacuity 7, test_secret_scan 7, test_reachability 11, test_w3_tmp_hygiene 16.

## Wiring requests
- B2/FM: narrow `build2/closure.py` EXTERNAL_GATES["rendered_pages"] text — help.etsy.com article API answers 200.
- CC: deploy package must include this branch for image_generation + policy reader to take effect.

## Remaining / next
Nothing executable left in this lane. Next deterministic action: integrator merges; owner executes the actions in GATE_CLEARANCE_INFRA.md.
