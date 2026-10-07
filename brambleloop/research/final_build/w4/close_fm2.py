"""Wave-4 lane FM2: close the launch-critical OPEN rows lane FM left (w4/FM2_OPEN.json).

Same discipline as `close_fm.py` (whose overlay/adjudication machinery this reuses): each entry
records what was implemented or read on this branch (`checked`) and the corrected mapping
fields. Nothing here certifies a row -- `aggregate.cap()/completion()` adjudicates the overlay,
and a row is written back only when the overlay computes COMPLETE or GATED (or the entry is an
honest `refresh` that stays OPEN) AND every cited test file was green in this lane's own
sequential run (w4/close_fm2_test_results.json).

Run (from brambleloop/):
  python3 research/final_build/w4/close_fm2.py --plan
  python3 research/final_build/w4/close_fm2.py --run-tests   # sequential, one file at a time
  python3 research/final_build/w4/close_fm2.py --apply
  python3 research/final_build/w4/v11_map.py && python3 research/final_build/aggregate.py
  python3 research/final_build/w4/fm2_open.py
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
FB = HERE.parent
ROOT = FB.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(FB))
sys.path.insert(0, str(FB / "w3"))
import aggregate as agg  # noqa: E402
import close_fm  # noqa: E402
import fold  # noqa: E402

TAG = "w4-FM2"
RESULTS = HERE / "close_fm2_test_results.json"
REPORT = HERE / "CLOSE_REPORT_FM2.json"
PY = os.environ.get("BL_PY", "/home/user/Project-Money/brambleloop/.venv/bin/python")
FM2T = "tests/test_w4_fm2_storefront_trust.py::"

ROWS = {
    "F-233": dict(
        checked="commerce/trust.shop_complete_problems reads store_foundation.storefront_gate "
                "(rendered icon measured at 40/70 px, the owner's canonical banner through every "
                "publication gate with UNKNOWN blocking, buyer-facing copy lint, sections, "
                "banner/announcement/grid continuity) and fails closed on a gate error; "
                "trust.accelerator (shop_complete rung -> ads) and launch/readiness 'storefront' "
                "both consume it, so a brief-only shop no longer reads complete",
        set=dict(coverage="FULL", defect=None, missing_part=None, maturity="INTEGRATED",
                 gate={"kind": "none", "key": "none",
                       "detail": "no external/owner/data gate on the remaining software step"},
                 consumer="src/brambleloop/launch/readiness.py::assess (requirement "
                          "'storefront' incl. storefront_gate findings); "
                          "src/brambleloop/commerce/trust.py::accelerator (rung shop_complete "
                          "via shop_complete_problems -> growth_ops.ads_plan)",
                 next_action="none: the gate is built and consumed; today it blocks on the "
                             "owner banner's review gates, which is the gate working"),
        tests=[FM2T + "test_shop_complete_reads_the_asset_gate_not_the_brief",
               FM2T + "test_shop_complete_passes_only_when_brief_and_asset_checks_both_pass",
               FM2T + "test_an_unevaluable_asset_gate_fails_closed",
               FM2T + "test_launch_readiness_storefront_requirement_carries_the_asset_gate",
               FM2T + "test_the_real_gate_today_blocks_paid_traffic_on_the_owner_banner_review"]),
    "F-263": dict(
        checked="growth_ops.ads_plan prerequisites now: owner ad authority, the #17 trust gate "
                "whose shop_complete rung reads the real storefront_gate (F-233 fixed), a "
                "published listing, the listing's stored search certificate PASS and current "
                "(F-294: tags + category + properties), measurement proven (F-297 "
                "listing_outcomes.measurement_status), organic-first proof and measured "
                "allowable CAC. The remaining step is the owner's ads SpendLimit",
        set=dict(coverage="FULL", defect=None, missing_part=None,
                 gate={"kind": "none", "key": "none",
                       "detail": "the readiness gate is complete; running ads additionally "
                                 "needs the owner's ads SpendLimit (ad_authority), which the "
                                 "gate itself checks"},
                 next_action="none for the gate; ads stay blocked until the owner grants "
                             "ad_authority (a prerequisite the gate enforces)"),
        tests=[FM2T + "test_ads_plan_requires_a_current_passing_search_certificate",
               FM2T + "test_the_real_gate_today_blocks_paid_traffic_on_the_owner_banner_review",
               "tests/test_cert_growth_ops.py::test_ads_adjust_reads_economics_from_rows_and_escalates_a_winner"]),
    "F-159": dict(
        checked="ops/log_secret_guard applies the release secret-scan patterns (byte-identical, "
                "parity-tested against tests/test_secret_scan.PATTERNS) to every record the "
                "production processes log: installed by app.access_log.install at app.main "
                "import (web), and by the worker and scheduler entrypoints; a match is redacted "
                "to its fingerprint before the line reaches the platform's log store, the record "
                "is never dropped and an unscannable record is suppressed. Its CLI scans an "
                "exported log window at release (exit 1 on a finding, unreadable = not clean)",
        set=dict(coverage="FULL", defect=None, missing_part=None, maturity="INTEGRATED",
                 producer="src/brambleloop/ops/log_secret_guard.py::SecretLogGuard (+ "
                          "tests/test_secret_scan.py over tracked/generated files)",
                 consumer="src/brambleloop/app/access_log.py::install (app.main import); "
                          "src/brambleloop/app/worker_entry.py, app/scheduler_entry.py "
                          "(log_secret_guard.install at start-up)",
                 durable_state=None,
                 protected_effect="no credential reaches the production runtime log; a "
                                  "catch is counted by fingerprint only",
                 next_action="none: at release, `python -m brambleloop.ops.log_secret_guard "
                             "scan <exported window>` is the optional second check"),
        tests=["tests/test_w4_fm2_log_secret_guard.py::test_patterns_are_byte_identical_to_the_release_scan",
               "tests/test_w4_fm2_log_secret_guard.py::test_a_secret_logged_by_the_service_never_reaches_the_handler",
               "tests/test_w4_fm2_log_secret_guard.py::test_an_exception_carrying_a_secret_is_redacted_not_printed",
               "tests/test_w4_fm2_log_secret_guard.py::test_every_service_entrypoint_installs_the_guard",
               "tests/test_w4_fm2_log_secret_guard.py::test_the_release_cli_fails_on_an_exported_log_window_with_a_secret"]),
    "F-514@v0.16": dict(
        refresh=True,
        checked="served at GET /api/etsy/surfaces (commerce/estate_api -> surface_inventory."
                "served + summary, channel per surface); unknowns include every Evidence"
                "(UNKNOWN) (F-588); re-verified daily against held scopes and collector "
                "freshness (surface_inventory.reverify inside etsy.shop_snapshot); and now "
                "re-verified against Etsy's current OpenAPI document "
                "(etsy_surfaces.openapi_reverify + etsy_ops.reverify_openapi, job "
                "etsy.openapi_reverify, drift incident) with the classification state per "
                "surface on the served inventory. The job has no cadence yet (runtime/"
                "worker.py is lane AUTO's): until wired, the served inventory reports "
                "'classification: never re-verified' -- honest, not green",
        set=dict(coverage="PARTIAL", defect=None,
                 missing_part="the etsy.openapi_reverify job is not yet on a cadence "
                              "(WIRING REQUEST to lane AUTO: worker.py CADENCES + "
                              "agents/registry orchestrator allow-list)",
                 next_action="Lane AUTO: add (\"etsy_openapi_reverify\", \"orchestrator\", "
                             "\"etsy.openapi_reverify\", 7 * 24 * 60 * 60) to CADENCES and "
                             "\"etsy.openapi_reverify\" to the orchestrator allow-list "
                             "(GREEN, read-only public GET, CA$0)"),
        tests=["tests/test_w4_fm2_surface_reverify.py::test_an_ads_api_appearing_names_the_unsupported_surfaces",
               "tests/test_w4_fm2_surface_reverify.py::test_a_removed_operation_names_the_surface_that_cites_it",
               "tests/test_w4_fm2_surface_reverify.py::test_the_job_stores_the_reading_opens_and_resolves_drift_and_reuses_a_fresh_reading",
               "tests/test_w4_fm2_surface_reverify.py::test_the_served_inventory_reports_the_classification_state",
               "tests/test_k8_shop_cx.py::test_the_inventory_is_served_with_a_channel_per_surface_and_every_named_surface"]),
    "F-213": dict(
        checked="visual/identity_gate.trial_validity (wave-3 K12): missing reference bytes, "
                "unproven conditioning (gateway.images.conditioning_receipt), an expired or "
                "superseded reference (canon manifest forbidden hashes + per-reference "
                "expires_at), a foreign reference, a missing judge pair and unmeasurable "
                "morphology make a trial INVALID/UNMEASURED with score None and "
                "counts_against_provider False. Consumed by visual/rnd/loop (visual.rnd.cycle "
                "cadence), the only path that can produce a model-bearing frame while "
                "model_photography.make is refused (F-852)",
        set=dict(coverage="FULL", defect=None, missing_part=None,
                 producer="src/brambleloop/visual/identity_gate.py::trial_validity / assess",
                 consumer="src/brambleloop/visual/rnd/loop.py (visual.rnd.cycle); "
                          "src/brambleloop/store_foundation/owner_banner.py (banner identity)",
                 next_action="none"),
        tests=["tests/test_w3_k12_model_photography.py::test_f213_invalid_and_unmeasured_trials_are_never_a_score",
               "tests/test_w3_k12_model_photography.py::test_f677_and_f732_rnd_door_overrides_caller_pass"]),
    "F-219": dict(
        checked="visual/identity_gate.assess puts every result that is neither provably her nor "
                "an obvious drift in the REVIEW band (blocks, never auto-approved); open_review "
                "persists it in visual_rnd_identity_reviews (idempotent per subject+image), "
                "resolve records a named reviewer's decision without approving publication, "
                "and queue() is read by visual/rnd/status; the R&D loop opens the reviews",
        set=dict(coverage="FULL", defect=None, missing_part=None,
                 producer="src/brambleloop/visual/identity_gate.py::assess / open_review / "
                          "resolve / queue",
                 consumer="src/brambleloop/visual/rnd/loop.py (opens reviews); "
                          "src/brambleloop/visual/rnd/status.py (review queue)",
                 durable_state="visual_rnd_identity_reviews",
                 next_action="none"),
        tests=["tests/test_w3_k12_model_photography.py::test_f219_borderline_enters_review_obvious_drift_is_refused",
               "tests/test_w3_k12_model_photography.py::test_f219_review_queue_through_the_rnd_door"]),
    "F-732": dict(
        checked="identity_gate.assess: PASS needs a valid trial on her current reference bytes, "
                "two judges reading every locked face dimension and the morphology floor as a "
                "match, and the deterministic biometric floor (cosine of face embeddings from a "
                "QUALIFIED embedder, computed in code); a similar woman can only be REVIEW or "
                "FAIL. No face-embedding model is installed or qualified, so the biometric "
                "floor is UNMEASURED and nothing passes -- and model-bearing renders are "
                "refused on the production path anyway (F-852, model_photography.make)",
        set=dict(coverage="PARTIAL", defect=None,
                 producer="src/brambleloop/visual/identity_gate.py::assess / biometric_floor",
                 consumer="src/brambleloop/visual/rnd/loop.py (visual.rnd.cycle)",
                 gate={"kind": "external", "key": "model_bearing_render",
                       "detail": "a positive exact-identity PASS needs a qualified "
                                 "face-embedding model (QUALIFIED_EMBEDDERS, a dependency + "
                                 "licence + qualification set) and model-bearing renders are "
                                 "prohibited on the production path (F-852); until then the "
                                 "gate holds every frame at REVIEW/FAIL"},
                 missing_part="the biometric floor has no qualified embedder, so exact identity "
                              "can be refused but never positively proven",
                 next_action="when model-bearing renders are re-authorised: qualify a "
                             "face-embedding model into identity_gate.QUALIFIED_EMBEDDERS"),
        tests=["tests/test_w3_k12_model_photography.py::test_f677_and_f732_rnd_door_overrides_caller_pass",
               "tests/test_w3_k12_model_photography.py::test_f219_borderline_enters_review_obvious_drift_is_refused"]),
    "F-677": dict(
        checked="visual/final_image_gate.evaluate (wave-3 K12): PASS only by deterministic "
                "proof -- a qualified disclosed-render source passing the independent pixel "
                "verifier against the certified CIR (product_authority.structural_floor) and "
                "every product pixel of it unchanged in the judged image (compose.verify), "
                "bound by sha256; a vision reading can only FAIL; anything else is UNKNOWN. "
                "Consumed by the R&D loop and, via structural_floor, by parity.assess, "
                "listing_asset and model/owned photography reuse. The LLM-proxy defect is gone: "
                "the proxy can no longer approve",
        set=dict(coverage="FULL", defect=None, missing_part=None,
                 producer="src/brambleloop/visual/final_image_gate.py::evaluate (+ "
                          "product_authority.structural_floor)",
                 consumer="src/brambleloop/visual/rnd/loop.py; src/brambleloop/visual/"
                          "parity.py::assess (structural_floor); publish/listing_asset.py",
                 next_action="none"),
        tests=["tests/test_w3_k12_model_photography.py::test_f677_final_image_gate_is_deterministic_and_the_proxy_can_only_fail",
               "tests/test_w3_k12_model_photography.py::test_f677_and_f732_rnd_door_overrides_caller_pass"]),
    "F-518@v0.15": dict(
        checked="commerce/listing_rollback (wave-3 K8): the daily etsy.listing_census attaches "
                "a rollback plan (certified value per drifted updateListing field, owner steps "
                "for inventory/state fields, remote fingerprint, stop conditions) to the drift "
                "incident; execute() sends it only past shadow, with the owner's write grant "
                "presented at execution time, against an unchanged listing, and verifies by "
                "read-back, recording every attempt as listing.lifecycle before/after rows",
        set=dict(coverage="PARTIAL", defect=None,
                 gate={"kind": "owner", "key": "production_window",
                       "detail": "executing a live-listing rollback is a live Etsy write: it "
                                 "needs a publishing phase and the owner's write grant "
                                 "(OwnerGrant) at execution time; in shadow the plan is "
                                 "computed and shown, never sent"},
                 missing_part="the restore is executed only with the owner's live write grant "
                              "in a publishing phase",
                 next_action="owner: production window + write grant; then the attached plan "
                             "is executed through listing_rollback.execute"),
        tests=["tests/test_k8_listing_estate.py::test_a_title_edited_on_etsy_gets_a_defined_rollback_plan_that_is_not_executed",
               "tests/test_k8_listing_estate.py::test_rollback_refuses_in_shadow_and_without_grant_and_records_each_refusal",
               "tests/test_k8_listing_estate.py::test_rollback_with_every_condition_clear_restores_and_reads_back"]),
    "F-834": dict(
        refresh=True,
        checked="build2/final_proof.py now binds the row's named consumer (s92: the consumer "
                "receipt must name it and, with --reachability, it must be reached from a live "
                "root; disabling it reopens the proof -- tests/test_final_proof.py), and "
                "aggregate.completion refuses COMPLETE without a named producer->consumer chain "
                "(F-831). What remains is end-stage: real runtime evidence packets (run "
                "identity, observed receipts per stage) exist only from a run on the frozen "
                "release candidate, and REVIEWABLE needs an independent reviewer (self-review "
                "is refused)",
        set=dict(coverage="PARTIAL", defect=None,
                 missing_part="no real runtime evidence packets: they come from a run on the "
                              "frozen release candidate, with protected_action_applicability "
                              "set per audited row and an independent reviewer",
                 next_action="END-STAGE (integrator): on the frozen RC, emit packets for the "
                             "launch-critical rows, run final_proof.py --matrix "
                             "closure_matrix.json --reachability module_reachability.json and "
                             "commit the report with the independent review"),
        tests=["tests/test_final_proof.py::test_disabling_the_consumer_reopens_the_proof"]),
}


def _overlay(uid, base, entry):
    close_fm.HEAD_SHA7 = TAG
    ov = close_fm._overlay(uid, base, entry, "FM2")
    return ov


def plan():
    rows, _ = fold._mapping()
    reach = json.loads((FB / "module_reachability.json").read_text())["modules"]
    out = []
    for uid, entry in ROWS.items():
        ov = _overlay(uid, rows[uid], entry)
        lvl, notes = agg.cap(dict(ov), reach)
        verdict, reasons = agg.completion(dict(ov, maturity=lvl))
        missing = [t for t in entry.get("tests") or [] if not agg._test_exists(t)]
        files = sorted({t.split("::")[0] for t in ov["tests"] if agg._test_exists(t)})
        out.append({"uid": uid, "refresh": bool(entry.get("refresh")), "verdict": verdict,
                    "maturity": lvl, "reasons": notes + reasons, "missing_tests": missing,
                    "test_files": files, "checked": entry["checked"], "row": ov})
    return out


def _own():
    return json.loads(RESULTS.read_text()) if RESULTS.exists() else {"suites": {}}


def _green(ref, own):
    m = re.match(r"(tests/[\w/]+\.py)", ref or "")
    if not m or not agg._test_exists(ref):
        return False
    r = own["suites"].get(m.group(1))
    return bool(r) and r["exit"] == 0 and r["ok"] > 0 and r["fail"] == 0


def run_tests(cands, only=None):
    own = _own()
    files = sorted({f for c in cands for f in c["test_files"]})
    env = dict(os.environ, PYTHONPATH="src")
    for f in files:
        if only and f not in only:
            continue
        t0 = time.time()
        p = subprocess.run([PY, f], cwd=ROOT, env=env, capture_output=True, text=True,
                           timeout=900)
        out = p.stdout + p.stderr
        own["suites"][f] = {"exit": p.returncode,
                            "ok": len(re.findall(r"^\s*OK\b", out, re.M)),
                            "fail": len(re.findall(r"^\s*FAIL\b", out, re.M)),
                            "seconds": round(time.time() - t0, 1)}
        print(f, own["suites"][f], flush=True)
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                          capture_output=True, text=True).stdout.strip()
    own["_meta"] = {"head": head, "runner": "close_fm2.py --run-tests (sequential)"}
    RESULTS.write_text(json.dumps(own, indent=1, sort_keys=True) + "\n")


def apply(cands):
    own = _own()
    rows, where = fold._mapping()
    written, kept = [], []
    for c in cands:
        why = None
        if c["missing_tests"]:
            why = "cited test missing: " + ", ".join(c["missing_tests"])
        elif c["verdict"] not in ("COMPLETE", "GATED") and not c["refresh"]:
            why = "overlay does not compute COMPLETE/GATED: " + "; ".join(c["reasons"])[:400]
        else:
            bad = [t for t in c["row"]["tests"] if agg._test_exists(t) and not _green(t, own)
                   and not fold.test_green(t, close_fm._cc4a_results())]
            if bad:
                why = "cited test not green: " + ", ".join(bad)[:300]
        if why:
            kept.append({"uid": c["uid"], "why": why})
            continue
        row = c["row"]
        tag = f" | {TAG} close"
        if tag not in str(row.get("searched") or ""):
            row["searched"] = (str(row.get("searched") or "") + tag)[:2000]
        rows[c["uid"]] = row
        written.append({"uid": c["uid"], "verdict": c["verdict"], "refresh": c["refresh"],
                        "maturity": c["maturity"],
                        "gate": row.get("gate") if c["verdict"] == "GATED" else None,
                        "checked": c["checked"], "test_files": c["test_files"]})
    by_file: dict[Path, list] = {}
    for uid, f in where.items():
        by_file.setdefault(f, []).append(rows[uid])
    for f, rs in by_file.items():
        old = json.loads(f.read_text())
        new = {r["uid"]: r for r in rs}
        text = json.dumps([new[r["uid"]] for r in old], indent=1, ensure_ascii=False) + "\n"
        if text != f.read_text():
            f.write_text(text)
    REPORT.write_text(json.dumps(
        {"lane": TAG, "written": written, "kept_open": kept,
         "counts": {"written": len(written), "kept": len(kept),
                    "by_verdict": dict(Counter(w["verdict"] for w in written))}},
        indent=1) + "\n")
    print(len(written), "written;", len(kept), "kept", [k["uid"] for k in kept])


if __name__ == "__main__":
    cands = plan()
    if "--plan" in sys.argv:
        for c in cands:
            print(c["uid"], c["verdict"], c["maturity"],
                  "MISSING " + str(c["missing_tests"]) if c["missing_tests"] else "",
                  "" if c["verdict"] in ("COMPLETE", "GATED") else "; ".join(c["reasons"])[:300])
        print(sorted({f for c in cands for f in c["test_files"]}))
    elif "--run-tests" in sys.argv:
        only = [a for a in sys.argv[2:] if a.startswith("tests/")]
        run_tests(cands, only or None)
    elif "--apply" in sys.argv:
        apply(cands)
