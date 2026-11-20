"""Wave-4 lane FMGATE: Final Master launch-critical rows against the DEPLOYED release 0417f35.

Production runs 0417f3516f30 (GET /health build.commit, 2026-10-11T14:39Z). This lane gathered
read-only runtime evidence from it and from committed artefacts
(research/final_build/w4/evidence_FMGATE_0417f35/), re-ran the shadow rehearsal, reachability,
final_proof and the freeze check on a clean detached 0417f35 worktree, and re-read each
end-stage row and each GATED row against that evidence.

Same discipline as close_fm2.py / close_fml.py: each entry records what was re-read (`checked`)
and the corrected mapping fields. Nothing here certifies a row -- `aggregate.cap()/completion()`
adjudicates the overlay. A row is written as COMPLETE only when the overlay computes COMPLETE
and every cited test file was green in this lane's own sequential run
(w4/close_fmgate_test_results.json). A gate re-classification (kind/key/detail, or a gate the
deploy cleared so the row is honestly OPEN) is written as a `refresh`: it never raises a row.
No override is added (overrides.json is untouched; proposals are in
w4/OVERRIDES_PROPOSED_FMGATE.json for the integrator).

Unlike close_fm2's machinery this also edits mapping/v11.json (the v1.1 rows), and records the
written rows under mapping/remap_0417f35/ so `mapped_on` names the SHA the mapping was made on.

Run (from brambleloop/):
  python3 research/final_build/w4/close_fmgate.py --plan
  python3 research/final_build/w4/close_fmgate.py --run-tests      # sequential, one file each
  python3 research/final_build/w4/close_fmgate.py --apply
  python3 research/final_build/aggregate.py
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
FB = HERE.parent
ROOT = FB.parents[1]
sys.path.insert(0, str(FB))
import aggregate as agg  # noqa: E402

TAG = "w4-FMGATE"
SHA7 = "0417f35"
RESULTS = HERE / "close_fmgate_test_results.json"
REPORT = HERE / "CLOSE_REPORT_FMGATE.json"
REMAP = FB / "mapping" / f"remap_{SHA7}" / "remap_w4_fmgate.json"
PY = os.environ.get("BL_PY", "/home/user/Project-Money/brambleloop/.venv/bin/python")
S = "src/brambleloop/"
EV = "research/final_build/w4/evidence_FMGATE_0417f35/"
PROD = "production 0417f3516f30 (GET /health build.commit, 2026-10-11T14:39Z)"
RR = "tests/test_rc1_own_release.py::"
FMG = "tests/test_w3_final_master_gate.py::"
NONE = {"kind": "none", "key": "none", "detail": "no external/owner/data gate on the remaining step"}

WINDOW = {"kind": "data", "key": "production_window",
          "detail": ("owner authorisation is exercised: the Final Build 0417f35 was deployed and "
                     "has run unattended since 2026-10-11T13:59:48Z (" + EV + "prod_health_*). "
                     "The gate opens mechanically when autonomy.off_device_proof reads PROVEN "
                     "over 24h of real rows; at 14:39Z it was unmet only on "
                     "no_unexpected_dead_letters (ops.sentinel VARCHAR(200) truncation and "
                     "listing.taxonomy_refresh 403, both repaired on claude/w4-FMGATE "
                     "843af70/4b55f22), so it opens no earlier than 24h after that successor "
                     "is deployed")}

ROWS: dict[str, dict] = {
    # ---------------------------------------------------------------- end-stage rows
    "F-169": dict(
        checked=("the final handoff's full suite ran against the exact deployed tree and the "
                 "running build proves it: release/RELEASE_5dfd1ac...json is release_eligible "
                 "(7877 passing, 0 failing suites, tree clean, HEAD unmoved) and names "
                 "source_tree_sha256 30a4dc93...; " + PROD + " /api/status boot_guard "
                 "{enforced:true, ok:true, record RELEASE_5dfd1ac, tree_sha256 30a4dc93} -- "
                 "the runtime boot guard recomputed the deployed tree digest and matched it; "
                 "ops/deploy_guard.py check --candidate 0417f35 --deployed fcb982d = ALLOW "
                 "(" + EV + "deploy_guard_0417f35_vs_fcb982d.txt). The old gap ('deploy_guard "
                 "is run by hand, a push builds without it') is closed at runtime: an "
                 "unproven hosted build is forced to SHADOW with a P1 incident"),
        set=dict(coverage="FULL", defect=None, missing_part=None, maturity="INTEGRATED",
                 producer=(S + "ops/release_record.py::verify_build (runtime boot guard: the "
                           "hosted build must carry a committed release-eligible full-suite "
                           "record naming its exact deployable-tree digest; written by "
                           "run_tests.sh REQUIRE_CLEAN=1 + ops/deploy_guard.py record)"),
                 consumer=(S + "app/main.py::_startup / release_record.apply_at_import "
                           "(forces SHADOW + P1 incident on an unproven build); "
                           "/api/status boot_guard; ops/deploy_guard.py::check (deploy path)"),
                 durable_state="release/RELEASE_<sha>.json + release/suite_runs/*.json "
                               "(tracked, in the image); incidents (release.unproven_build)",
                 evidence=[EV + "prod_api_status_20261011T1439Z.json (boot_guard ok, "
                                "record RELEASE_5dfd1ac, tree 30a4dc93)",
                           "release/RELEASE_5dfd1ac56ba4a5e64c3cd29fd92212d9cdfadd8c.json",
                           EV + "deploy_guard_0417f35_vs_fcb982d.txt (ALLOW)"],
                 gate=dict(NONE),
                 next_action="none: every successor carries its own release record; the "
                             "boot guard re-checks it on every hosted boot"),
        tests=[RR + "test_boot_guard_accepts_a_recorded_build_and_rejects_tampering",
               RR + "test_boot_guard_rejects_a_red_or_unpinned_suite_record",
               RR + "test_boot_guard_opens_and_resolves_a_p1_incident",
               RR + "test_dockerfile_ships_the_release_records_and_main_runs_the_guard"]),
    "F-839": dict(
        checked=("the reachability audit was re-run on the final effective source tree: a "
                 "clean detached worktree at the deployed 0417f35 (" + EV +
                 "module_reachability_0417f35.json; installed as module_reachability.json): "
                 "656 modules, 564 reached from a live root, none lost against 2f36fe0, "
                 "gained app/command_center/launch_packet.py, launch/packet.py, "
                 "growth/free_assets.py, growth/free_to_paid.py; aggregate.py re-adjudicated "
                 "every row on it and final_proof.py ran on 0417f35 with the 0417f35 "
                 "rehearsal packets (" + EV + "final_proof_0417f35.json). Independent "
                 "function-level review of the same deployable tree (2c6d775 == 5dfd1ac == "
                 "0417f35 src/): research/final_build/w4/INDEPENDENT_SECREVIEW_2c6d775.md "
                 "(NO BLOCKER), on top of INDEPENDENT_REAUDIT_7421ef6.md"),
        set=dict(coverage="FULL", defect=None, missing_part=None, maturity="INTEGRATED",
                 producer=S + "build2/reachability.py::reached (per-function trace from the "
                              "runtime roots)",
                 consumer=("research/final_build/aggregate.py::cap (INTEGRATED needs a reached "
                           "producer); " + S + "build2/closure.py::proof_of (live dashboard)"),
                 durable_state="research/final_build/module_reachability.json (basis HEAD "
                               "0417f35)",
                 evidence=[EV + "module_reachability_0417f35.json",
                           EV + "final_proof_0417f35.json",
                           "research/final_build/w4/INDEPENDENT_SECREVIEW_2c6d775.md"],
                 gate=dict(NONE),
                 next_action="none for 0417f35; a material successor re-runs the same audit "
                             "before it is frozen"),
        tests=["tests/test_reachability.py::test_the_real_package_still_reaches_its_handlers_"
               "libraries"]),
    "F-840": dict(
        checked=("in production the green suite is demonstrably not sufficient: " + PROD +
                 " booted on a release-eligible green full suite (boot_guard ok, 7877 "
                 "passing) and its live launch gate still reads /api/build final_master "
                 "{status DEGRADED, launch_ready false, launch_critical COMPLETE 355 / GATED "
                 "126 / OPEN 9} -- build2/final_master.py refuses launch while any "
                 "launch-critical row lacks requirement-level proof. The candidate's "
                 "full-suite record and the final_proof report for the same SHA are cited "
                 "together in research/final_build/CANDIDATE_0417f35.json and " + EV +
                 "final_proof_0417f35.json (917 rows, certified false: a green suite "
                 "certifies none of them)"),
        set=dict(coverage="FULL", defect=None, missing_part=None, maturity="INTEGRATED",
                 producer=(S + "build2/final_master.py::summary (live launch gate: ready iff "
                           "zero launch-critical rows OPEN, whatever the suite says); "
                           "research/final_build/aggregate.py::cap (a green suite never "
                           "raises maturity)"),
                 consumer=S + "launch/readiness.py::assess (final_master check) -> /api/build "
                              "final_master; executor report",
                 durable_state="src/brambleloop/build2/final_master_closure.json (in the image)",
                 evidence=[EV + "prod_api_build_20261011T1439Z.json final_master",
                           EV + "prod_api_status_20261011T1439Z.json boot_guard",
                           EV + "final_proof_0417f35.json",
                           "research/final_build/CANDIDATE_0417f35.json"],
                 gate=dict(NONE),
                 next_action="none: the rule is enforced in the running launch gate"),
        tests=[FMG + "test_post_launch_rows_never_block_and_launch_is_ready_only_with_zero_open",
               FMG + "test_the_launch_readiness_gate_consumes_the_closure",
               FMG + "test_the_runtime_recomputes_every_verdict_and_agrees_with_the_adjudicator"]),
    "F-841": dict(
        checked=("an explicitly reviewed successor to 019ebf0 now exists and runs: 0417f35 "
                 "(release record RELEASE_5dfd1ac, freeze check 0 refusals in "
                 "CANDIDATE_0417f35.json, independent security review of the identical "
                 "deployable tree INDEPENDENT_SECREVIEW_2c6d775.md NO BLOCKER, migration/"
                 "rollback proof MIGRATION_ROLLBACK_2c6d775.md) and is deployed (" + PROD +
                 "); release/DEPLOYED_HISTORY.json records it, and the runtime treats the "
                 "deployed history as the only sanctioned rollback baseline "
                 "(known_good_predecessor; ops.truth.sweep rollback_baseline recoverable:true "
                 "on 0417f35)"),
        set=dict(coverage="FULL", defect=None, missing_part=None, maturity="INTEGRATED",
                 producer=(S + "ops/release_record.py::known_good_predecessor (reads the "
                           "shipped release/DEPLOYED_HISTORY.json: the baseline is the last "
                           "reviewed, deployed commit)"),
                 consumer=(S + "ops/assurance.py::rollback_baseline (ops.health sweep); "
                           "ops/deploy_guard.py rollback-commit (targets only a listed SHA)"),
                 durable_state="release/DEPLOYED_HISTORY.json; audit_log ops.truth.sweep",
                 evidence=["release/DEPLOYED_HISTORY.json (fcb982d, 0417f35)",
                           "research/final_build/CANDIDATE_0417f35.json",
                           "research/final_build/w4/INDEPENDENT_SECREVIEW_2c6d775.md",
                           EV + "prod_audit_ops_truth_sweep_26799.json"],
                 gate=dict(NONE),
                 next_action="none: 0417f35 is the reviewed successor baseline; the next one "
                             "is appended after its own review and verified deploy"),
        tests=["tests/test_w3_deploy_evidence.py::test_the_known_good_predecessor_comes_from_"
               "the_shipped_deployed_history",
               "tests/test_w3_deploy_evidence.py::test_the_history_ships_in_the_image",
               RR + "test_the_real_history_names_production_and_the_runbook_exists"]),
    "F-834": dict(
        refresh=True,
        checked=("runtime packets re-emitted on the deployed 0417f35 from its own shadow "
                 "rehearsal (" + EV + "runtime_packets_0417f35.json, 10 rows) and "
                 "final_proof.py run with 0417f35 reachability (" + EV +
                 "final_proof_0417f35.json): 917 BLOCKED, 0 REVIEWABLE"),
        set=dict(coverage="PARTIAL", defect=None, gate=dict(NONE),
                 missing_part=("final_proof needs, per launch-critical row, chain receipts "
                               "durable_state -> consumer -> decision -> effect -> result bound "
                               "to one run on the candidate head, a production_producer and "
                               "failure_test receipt, a suite receipt whose head/run match the "
                               "packet (the release record names 5dfd1ac, the packet 0417f35), "
                               "an execution_gate receipt on protected rows, and an "
                               "independent_review by a reviewer other than the emitter. The "
                               "rehearsal records job outcomes only, so the emitter can supply "
                               "producer + live_root receipts and nothing else"),
                 next_action=("company: extend scripts/emit_runtime_packets.py to read the "
                              "rehearsal DB proofs into per-stage receipts and to bind the "
                              "suite by the deploy-guard tree rule; then a separate session "
                              "reviews the packets (independent_review). Not owner-gated")),
        tests=[]),
    "F-846": dict(
        refresh=True,
        checked=("one full loop has run: freeze 7421ef6 (CANDIDATE/DEFECT_LEDGER_7421ef6) -> "
                 "independent re-audit (INDEPENDENT_REAUDIT_7421ef6.md: D-1, L-1..L-3) -> "
                 "repairs with regression tests (w4-AUDITFIX e0fe1da; tests/"
                 "test_w4_auditfix_*) -> full suite on the successor (RELEASE_5dfd1ac: 7877 "
                 "passing) -> independent re-audit (INDEPENDENT_SECREVIEW_2c6d775.md: all four "
                 "fixed, NO BLOCKER) -> deployed 0417f35. The next loop is open: "
                 "DEFECT_LEDGER_0417f35.json (5 rehearsal blockers carrying owner/external "
                 "gates, 3 production-readback defects; 2 repaired on claude/w4-FMGATE)"),
        set=dict(coverage="FULL", defect=None, gate=dict(NONE),
                 missing_part=None, maturity="TESTED",
                 producer="scripts/freeze_candidate.py (freeze + defect ledger) -> "
                          "research/final_build/DEFECT_LEDGER_<sha7>.json",
                 consumer="integrator release loop: independent re-audit and successor "
                          "full suite before deploy (ops/deploy_guard.py check)",
                 next_action=("integrator: the producer is operator tooling "
                              "(scripts/freeze_candidate.py), so INTEGRATED is unreachable by "
                              "construction; accept the structural TESTED target proposed in "
                              "w4/OVERRIDES_PROPOSED_FMGATE.json (same basis as F-843/F-845/"
                              "F-847)")),
        tests=["tests/test_freeze_candidate.py::test_exact_clean_eligible_evidence_freezes_"
               "locally_and_opens_the_ledger"]),
    "F-848": dict(
        refresh=True,
        checked=("scripts/shadow_rehearsal.py on a clean detached worktree at the deployed "
                 "0417f35, production mode, 457.9 s (" + EV + "shadow_rehearsal_0417f35.json; "
                 "also research/final_build/evidence/): complete:false. PASS: boot, "
                 "chain.jobs, cir.compile, gate.certify, assets.build, listing.seo, "
                 "network[shadow], network[past-shadow], orders.ingest, support.case, ledger; "
                 "store.publish[shadow] REFUSED_AS_EXPECTED; BLOCKED: owner_phase_transition "
                 "(readiness not ready), owner_publication_grant (taxonomy UNKNOWN), "
                 "store.publish[past-shadow]"),
        set=dict(coverage="PARTIAL", defect=None, gate=dict(NONE),
                 missing_part=("approval -> simulated publish is not exercised. Two blockers "
                               "carry real gates: the grant needs a certified Etsy taxonomy "
                               "(owner etsy_api: production listing.taxonomy_refresh got 403 at "
                               "2026-10-11T14:05Z) and the phase transition needs launch "
                               "readiness, whose owner items (seller_identity, etsy_shop, "
                               "payout, brand_clearance, benchmark_challenge, ...) are open. "
                               "But the rehearsal evaluates readiness on a FRESH scratch DB "
                               "holding one product, where findable:catalogue_depth, "
                               "clickable:storefront_preview and converts_honestly:"
                               "sustainable_economics can never pass whatever the owner does: "
                               "as built, the step cannot open"),
                 next_action=("company: make owner_phase_transition cite the readiness verdict "
                              "of a production-shaped state (seed the scratch DB from a "
                              "continuity export, or read production's live launch.assessed "
                              "row) instead of a one-product fresh DB; then the remaining "
                              "blockers are exactly the owner etsy_api / readiness gates")),
        tests=[]),
    "F-878": dict(
        refresh=True,
        checked=("the packet is reached from live roots on 0417f35 (reachability: "
                 "launch/packet.py via app/command_center/launch_packet.py) and is served in "
                 "production: GET /api/launch/packet and /api/cc/launch/packet answer 401 "
                 "(operator/owner-gated) where an unknown path under the same prefixes answers "
                 "404. But the deployed packet's tests/audit section is UNKNOWN by "
                 "construction: 0417f35's CC builder passes repo_root=None when research/ is "
                 "absent (the image ships src/ and release/ only), and its packet.py quotes "
                 "research RUN_*_full_suite.json. Reproduced offline on 0417f35 code: "
                 + EV + "launch_packet_0417f35_image_mode.json (recorded_suite UNKNOWN). The "
                 "PACKETREL fix (merged on this branch) cites the candidate's own release "
                 "record: " + EV + "launch_packet_fmgate_image_mode.json (recorded_suite "
                 "PASS, RELEASE_5dfd1ac, tree_digest+ancestor, 7877 passing)"),
        set=dict(coverage="PARTIAL", defect=None, gate=dict(NONE),
                 missing_part=("the deployed owner packet carries no tests/audit evidence "
                               "(recorded_suite UNKNOWN in the image); fixed on "
                               "claude/w4-FMGATE (launch/packet.py release-record citation + "
                               "CC builder passes the image's release/ root), not yet released"),
                 next_action=("integrator: full suite + release record + deploy of the "
                              "successor carrying the PACKETREL packet fix; then read "
                              "/api/cc/launch/packet recorded_suite with the owner credential "
                              "and commit it")),
        tests=[]),
    # ---------------------------------------------------------------- gated rows
    "F-172": dict(
        checked=("re-proven on the Final Build deploy before any phase change: " + PROD +
                 " /api/verify phase_is_shadow ok, nothing_published ok, "
                 "publication_was_actually_attempted_and_refused ok (185 expected refusals; "
                 "/api/queue/dead store.publish last_seen 2026-10-11T14:26:20Z, after the "
                 "13:59Z deploy); the production_deploy gate is cleared"),
        set=dict(coverage="FULL", defect=None, missing_part=None, gate=dict(NONE),
                 consumer=(S + "runtime/pipeline.py::handle_store_publish (refuses in "
                           "shadow; refusals are what api_verify counts); app/main.py::"
                           "dashboard (last clean /api/verify)"),
                 evidence=[EV + "prod_api_verify_20261011T1439Z.json",
                           EV + "prod_api_queue_dead_20261011T1439Z.json"],
                 next_action="none: re-run /api/verify after every deploy and before any "
                             "phase-change request"),
        tests=[]),
    "F-176": dict(
        checked=("the deployed candidate's baseline is recorded and recoverable in "
                 "production: ops.truth.sweep audit row 26799 at 2026-10-11T14:31:00Z on "
                 "0417f35 reads rollback_baseline {recoverable:true, recorded:true, "
                 "missing:[]} (" + EV + "prod_audit_ops_truth_sweep_26799.json); the "
                 "production_window gate it waited on was the deploy"),
        set=dict(coverage="FULL", defect=None, missing_part=None, gate=dict(NONE),
                 evidence=[EV + "prod_audit_ops_truth_sweep_26799.json"],
                 next_action="none: record_baseline writes once per deployed digest"),
        tests=[]),
    "F-158": dict(
        checked=("the gap was 'the image has never been built from the lock'. 0417f35 is "
                 "deployed: its Dockerfile installs only requirements.lock with pip "
                 "--require-hashes --no-deps, the release record's supply_chain is "
                 "{status verified, 34 distributions, 1375 hashes, SBOM, material change vs "
                 "fcb982d recorded}, and the hosted boot guard matched the deployed tree "
                 "digest -- which includes requirements.lock -- to that record "
                 "(/api/status boot_guard ok)"),
        set=dict(coverage="FULL", defect=None, missing_part=None, gate=dict(NONE),
                 maturity="INTEGRATED",
                 producer=(S + "ops/release_record.py::verify_build (requirements.lock is in "
                           "the deployable-tree digest the hosted build must match; the "
                           "record's supply_chain is verified by ops/deploy_guard.py record "
                           "from scripts/lock_requirements.py output)"),
                 consumer=("Dockerfile: pip install --require-hashes --no-deps -r "
                           "requirements.lock; " + S + "app/main.py::_startup boot guard"),
                 evidence=["release/RELEASE_5dfd1ac56ba4a5e64c3cd29fd92212d9cdfadd8c.json "
                           "supply_chain", EV + "prod_api_status_20261011T1439Z.json"],
                 next_action="none: every release record carries its supply-chain check"),
        tests=[RR + "test_boot_guard_accepts_a_recorded_build_and_rejects_tampering",
               RR + "test_dockerfile_ships_the_release_records_and_main_runs_the_guard"]),
    "F-144": dict(
        refresh=True,
        checked=("the production_deploy gate is cleared (Final Build 0417f35 deployed); "
                 "/api/verify on it reads ok:false (every_agent_has_a_cost_ceiling: learn/"
                 "coo/laura at 0.0; no_unexpected_dead_letters_in_24h)"),
        set=dict(coverage="PARTIAL", defect=None, gate=dict(NONE),
                 missing_part=("no per-feature readback rule: a launch-critical feature is "
                               "not refused 'done' until its deployed readback passes; the "
                               "deployed /api/verify itself is red on two checks"),
                 next_action=("company: per-feature readback manifest (endpoint + expected "
                              "field) for launch-critical features, run against production "
                              "after each deploy; integrator decision on the 0.0 agent "
                              "ceilings (not changed by this lane)")),
        tests=[]),
    "F-171": dict(
        refresh=True,
        checked=("the production_deploy gate is cleared; " + PROD + " /api/verify: 13 "
                 "checks, ok:false on every_agent_has_a_cost_ceiling and "
                 "no_unexpected_dead_letters_in_24h"),
        set=dict(coverage="PARTIAL", defect=None, gate=dict(NONE),
                 missing_part=("the smoke matrix does not exercise queues end to end, "
                               "provider probes, continuity or search intelligence, and on "
                               "the Final Build deploy it is red on two checks"),
                 next_action=("company: extend /api/verify (probe recency, continuity proof, "
                              "cadence coverage, queue round-trip); deploy the dead-letter "
                              "fixes (843af70, 4b55f22); integrator decides the 0.0 agent "
                              "ceilings")),
        tests=[]),
    "F-718": dict(
        refresh=True,
        checked=("the gate (production_window) does not govern this row: the approval record "
                 "is already readable from production -- GET /api/audit?action=model.frozen "
                 "row 5693 (2026-09-22T03:52:53Z, pack_version v15, candidate_fingerprint "
                 "914ee7da716baef7) and /api/model-identity canonical_selected:true v1"),
        set=dict(coverage="PARTIAL", defect=None, gate=dict(NONE),
                 next_action=("company: export the production model.frozen approval record "
                              "and pack fingerprint into the repository manifest with a test "
                              "that the manifest matches the DB row (read-only GET suffices)")),
        tests=[]),
    "F-733": dict(
        refresh=True,
        checked=("as F-718: production_window does not open this; the approval row is "
                 "readable now (/api/audit?action=model.frozen id 5693)"),
        set=dict(coverage="PARTIAL", defect=None, gate=dict(NONE),
                 next_action=("company: record the approved pack fingerprint from the "
                              "production model.frozen row in the repository manifest; store "
                              "provider conditioning packages; deploy hash-verified "
                              "reference_paths")),
        tests=[]),
    "F-135": dict(
        refresh=True,
        checked=("production_window opening (24h off-device proof) would not record a "
                 "lease-recovery drill; the drill needs a controlled kill of the production "
                 "worker mid-job"),
        set=dict(gate={"kind": "owner", "key": "live_restart_drill",
                       "detail": ("owner authorises a controlled restart of the production "
                                  "worker during a queued job (Railway restart; disturbs "
                                  "production); the drill then reads lease expiry and no "
                                  "duplicate effect from real rows")}),
        tests=[]),
    "F-850": dict(
        refresh=True,
        checked="same as F-135: a live restart drill, not the 24h window, closes this",
        set=dict(gate={"kind": "owner", "key": "live_restart_drill",
                       "detail": ("owner authorises restarting the live service during "
                                  "queued/in-flight work (publish / orders.ingest) on the "
                                  "deployed candidate")}),
        tests=[]),
    "F-540": dict(
        refresh=True,
        checked=("the remaining proof (refresh-token rotation in production) needs a working "
                 "Etsy credential: production /api/build gates.etsy_api open:false and "
                 "Etsy answered 403 at 2026-10-11T14:05Z; the 24h window does not open it"),
        set=dict(gate={"kind": "owner", "key": "etsy_api",
                       "detail": ("Etsy credential: a recorded successful etsy.probe; then "
                                  "rotation is proven on the deployed build")}),
        tests=[]),
    "F-518@v0.15": dict(
        refresh=True,
        checked=("a live-listing rollback is an Etsy write: it needs a publishing phase and "
                 "the owner's write grant, not the 24h window"),
        set=dict(gate={"kind": "owner", "key": "publication_authority",
                       "detail": ("owner write grant (OwnerGrant) in a publishing phase at "
                                  "execution time; in shadow the plan is computed and shown, "
                                  "never sent")}),
        tests=[]),
    "F-396": dict(
        refresh=True,
        checked=("of its two blockers, the off-device proof is now data (see production_window) "
                 "and the offsite archive destination is the owner's (gates.offsite_storage "
                 "open:false in production)"),
        set=dict(gate={"kind": "owner", "key": "offsite_storage",
                       "detail": ("an object-storage bucket and credential outside this "
                                  "provider; then the 24h off-device proof on the deployed "
                                  "build")}),
        tests=[]),
    "F-924": dict(
        refresh=True,
        checked=("the deploy happened (0417f35); the error budgets need hosted operating "
                 "history, which only elapsed time produces"),
        set=dict(gate={"kind": "data", "key": "hosted_operating_history",
                       "detail": ("hosted operating history of the deployed candidate "
                                  "(0417f35 since 2026-10-11T13:59:48Z); the SLO budgets "
                                  "read from real rows as it accrues")}),
        tests=[]),
    "F-009": dict(
        refresh=True,
        checked=("company half built on this branch: /api/catalogue now shows, per listing "
                 "version, the filters entered and lost to missing data from "
                 "ListingSearchProfile.filters (commerce/category.py::filter_audit), and "
                 "UNMEASURED with the reason while the node schema is unknown "
                 "(tests/test_w4_fmgate_catalogue_filters.py)"),
        set=dict(missing_part=("real filter values need the Etsy node schema, which is read "
                               "only once the etsy_api gate opens (production taxonomy read "
                               "403); the console view exists and reads UNMEASURED until then"),
                 consumer=("runtime/release.py::handle_listing_seo; app/main.py::"
                           "api_catalogue (per-listing filters)"),
                 next_action="owner gate etsy_api: a working Etsy credential lets "
                             "listing.taxonomy_refresh read the node schema"),
        tests=["tests/test_w4_fmgate_catalogue_filters.py::test_entered_and_lost_filters_per_"
               "listing_and_unmeasured_without_a_schema"]),
    "F-160": dict(
        refresh=True,
        checked=("missing_part was stale: ops/credential_register.py is reached on 0417f35 "
                 "(owner_requests via launch.readiness) and the rotation card reaches the "
                 "owner queue (tests/test_fb4_ops.py); what remains is the owner's rotation"),
        set=dict(missing_part=("the chat-exposed ANTHROPIC_API_KEY is still rotation-required: "
                               "rotating it is an owner act; the register and owner card are "
                               "wired")),
        tests=[]),
    "F-321": dict(
        refresh=True,
        checked=("missing_part was stale: runtime spend writers carry product attribution "
                 "since 6d86a8b; what remains is a live listing to attribute recurring cost to"),
        set=dict(missing_part=("maintenance cost per listing reads UNMEASURED until a listing "
                               "is live (data gate live_listings); spend rows already carry "
                               "product_slug at runtime (6d86a8b)")),
        tests=[]),
    "F-588": dict(
        refresh=True,
        checked=("missing_part was stale: intel/etsy_surfaces.py::_unknowns now carries every "
                 "Evidence(UNKNOWN) into coverage()['unknowns'] and a provider-set change "
                 "re-opens the partners review; what remains is the owner's reading of Etsy's "
                 "guidance (help.etsy.com 403 to automation)"),
        set=dict(missing_part=("the owner reads Etsy's production-partner guidance on whether "
                               "a generative imagery model is a partner; the UNKNOWN reaches "
                               "readiness and a provider change re-opens the review")),
        tests=[]),
}

for _uid in ("F-371", "F-380", "F-381", "F-495", "F-654", "F-701", "F-849", "F-880", "F-881",
             "F-895", "F-923"):
    ROWS[_uid] = dict(
        refresh=True,
        checked=("owner authorisation exercised (0417f35 deployed, unattended since "
                 "13:59:48Z); the remaining step is the off-device proof over 24h of real rows "
                 "-- elapsed operating history, not an owner act"),
        set=dict(gate=dict(WINDOW)), tests=[],
        prefix_missing=("deployed: 0417f35 runs unattended in production since "
                        "2026-10-11T13:59:48Z; the 24h off-device proof on it has not yet read "
                        "PROVEN (unmet only on dead letters fixed by 843af70/4b55f22). Earlier "
                        "mapping note: "))
ROWS["F-924"]["prefix_missing"] = ("deployed: 0417f35 since 2026-10-11T13:59:48Z; the error "
                                   "budgets accrue from its hosted history. Earlier mapping "
                                   "note: ")


def _mapping():
    rows, where = {}, {}
    for f in agg.mapping_files():
        for r in json.loads(f.read_text()):
            rows[r["uid"]] = r
            where[r["uid"]] = f
    return rows, where


def _overlay(uid, base, entry):
    ov = json.loads(json.dumps(base))
    for k, v in (entry.get("set") or {}).items():
        ov[k] = v
    if entry.get("prefix_missing") and not str(ov.get("missing_part") or "").startswith(
            entry["prefix_missing"][:40]):
        ov["missing_part"] = (entry["prefix_missing"] + str(ov.get("missing_part") or ""))[:1200]
    ov["tests"] = sorted(set(ov.get("tests") or []) | set(entry.get("tests") or []))
    note = f"{TAG} on {SHA7}: {entry['checked']}"
    ov["evidence"] = [e for e in ov.get("evidence") or []
                      if not (isinstance(e, str) and e.startswith(f"{TAG} on "))]
    ov["evidence"].append(note)
    return ov


def plan():
    rows, _ = _mapping()
    reach = json.loads((FB / "module_reachability.json").read_text())["modules"]
    out = []
    for uid, entry in ROWS.items():
        ov = _overlay(uid, rows[uid], entry)
        lvl, notes = agg.cap(dict(ov), reach)
        before = agg.completion(dict(rows[uid], maturity=agg.cap(dict(rows[uid]), reach)[0]))
        verdict, reasons = agg.completion(dict(ov, maturity=lvl))
        missing = [t for t in entry.get("tests") or [] if not agg._test_exists(t)]
        files = sorted({t.split("::")[0] for t in entry.get("tests") or []
                        if agg._test_exists(t)})
        out.append({"uid": uid, "refresh": bool(entry.get("refresh")), "before": before[0],
                    "verdict": verdict, "maturity": lvl, "reasons": notes + reasons,
                    "missing_tests": missing, "test_files": files,
                    "checked": entry["checked"], "row": ov})
    return out


def _own():
    return json.loads(RESULTS.read_text()) if RESULTS.exists() else {"suites": {}}


def run_tests(cands, only=None):
    own = _own()
    files = sorted({f for c in cands for f in c["test_files"]})
    for f in files:
        if only and f not in only:
            continue
        tmp = tempfile.mkdtemp(prefix="fmgate_t_")
        env = dict(os.environ, PYTHONPATH="src:tests", TMPDIR=tmp)
        t0 = time.time()
        try:
            p = subprocess.run([PY, f], cwd=ROOT, env=env, capture_output=True, text=True,
                               timeout=1500)
            out, code = p.stdout + p.stderr, p.returncode
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        own["suites"][f] = {"exit": code,
                            "ok": len(re.findall(r"^\s*(?:OK|PASS)\b", out, re.M))
                            + sum(int(n) for n in re.findall(r"^\s*(\d+)/\1 passed", out, re.M)),
                            "fail": len(re.findall(r"^\s*FAIL\b", out, re.M)),
                            "seconds": round(time.time() - t0, 1)}
        print(f, own["suites"][f], flush=True)
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                          capture_output=True, text=True).stdout.strip()
    own["_meta"] = {"head": head, "runner": "close_fmgate.py --run-tests (sequential, "
                                            "private TMPDIR per file)"}
    RESULTS.write_text(json.dumps(own, indent=1, sort_keys=True) + "\n")


def _green(f, own):
    r = own["suites"].get(f)
    return bool(r) and r["exit"] == 0 and r["ok"] > 0 and r["fail"] == 0


def apply(cands):
    own = _own()
    rows, where = _mapping()
    written, kept = [], []
    for c in cands:
        why = None
        if c["missing_tests"]:
            why = "cited test missing: " + ", ".join(c["missing_tests"])
        elif c["verdict"] == "COMPLETE":
            # Tests this lane cites must be green in its own run. The row's previously cited
            # tests are unchanged files that were green in the deployed tree's release suite
            # (RELEASE_5dfd1ac: 551 suites, 0 failing).
            bad = [f for f in c["test_files"] if not _green(f, own)]
            if bad:
                why = "cited test file not green in this lane's run: " + ", ".join(bad)
        elif not c["refresh"]:
            why = "overlay does not compute COMPLETE: " + "; ".join(c["reasons"])[:400]
        if why:
            kept.append({"uid": c["uid"], "why": why})
            continue
        row = c["row"]
        tag = f" | {TAG} {SHA7}"
        if tag not in str(row.get("searched") or ""):
            row["searched"] = (str(row.get("searched") or "") + tag)[:2000]
        rows[c["uid"]] = row
        written.append({"uid": c["uid"], "before": c["before"], "verdict": c["verdict"],
                        "refresh": c["refresh"], "maturity": c["maturity"],
                        "gate": row.get("gate"), "checked": c["checked"],
                        "test_files": c["test_files"]})
    by_file: dict[Path, list] = {}
    for uid, f in where.items():
        by_file.setdefault(f, []).append(uid)
    for f, uids in by_file.items():
        old = json.loads(f.read_text())
        text = json.dumps([rows[r["uid"]] for r in old], indent=1, ensure_ascii=False) + "\n"
        if text != f.read_text():
            f.write_text(text)
    REMAP.parent.mkdir(parents=True, exist_ok=True)
    REMAP.write_text(json.dumps([rows[w["uid"]] for w in written], indent=1,
                                ensure_ascii=False) + "\n")
    REPORT.write_text(json.dumps(
        {"lane": TAG, "basis": "deployed production 0417f3516f30bb7c52926187fc475a0f46536e86",
         "written": written, "kept": kept,
         "counts": {"written": len(written), "kept": len(kept),
                    "transitions": dict(Counter(f"{w['before']}->{w['verdict']}"
                                                for w in written))}},
        indent=1) + "\n")
    print(len(written), "written;", len(kept), "kept", kept)


if __name__ == "__main__":
    cands = plan()
    if "--plan" in sys.argv:
        for c in cands:
            print(c["uid"], c["before"], "->", c["verdict"], c["maturity"],
                  "MISSING " + str(c["missing_tests"]) if c["missing_tests"] else "",
                  "" if c["verdict"] == "COMPLETE" else "; ".join(c["reasons"])[:200])
        print(sorted({f for c in cands for f in c["test_files"]}))
    elif "--run-tests" in sys.argv:
        only = [a for a in sys.argv[2:] if a.startswith("tests/")]
        run_tests(cands, only or None)
    elif "--apply" in sys.argv:
        apply(cands)
