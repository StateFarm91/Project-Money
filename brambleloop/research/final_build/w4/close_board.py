"""W4-BOARD (2026-10-19): close rows whose gate production now reports OPEN, on production
readings of the DEPLOYED commit 1b21e81 (read-only GETs under w4/evidence_BOARD/).

Only rows whose remaining step was the gate itself plus a production reading are touched, and
each keeps its acceptance criterion; the reading that meets it is quoted into the row's
evidence. Final Master rows are corrected in their mapping slice and listed under
mapping/remap_1b21e81/ (aggregate.py REMAP_SHAS); the Build 2 row is moved to `covered` in the
registry with the reading in its note. aggregate.py and build2_ledger.py are then re-run.

  cd brambleloop && python3 research/final_build/w4/close_board.py
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
FB = HERE.parent
BL = FB.parents[1]
TS = "20261019T1249Z"
EV = f"research/final_build/w4/evidence_BOARD"
DEPLOYED = "1b21e81c6d1b228a93f72be44cfdf8193740b61b"

OFFSITE = (f"{EV}/prod_api_offsite_{TS}.json (production 1b21e81, {EV}/prod_health_{TS}.json "
           "build.commit): last_archive 2026-10-19T12:43:39Z ok=true stage=complete, "
           "encrypted=true, key continuity/2026/10/19/340ab26103f5a567.blarc, "
           "tables_restored 124, rows_restored 131981, survives provider_loss=true -- an "
           "export uploaded off-provider, read back, decrypted and restored into a scratch "
           "database")
CONTINUITY = (f"{EV}/prod_api_continuity_{TS}.json: nightly retained archives 2026-10-17T00:22Z, "
              "2026-10-18T01:10Z, 2026-10-19T00:41Z; last_proof ok, round_trip_digest == "
              "source_digest over 122 tables / 129255 rows; mismatches {}")
STARVED = (f"{EV}/prod_api_swarm_runtime_{TS}.json (production 1b21e81): starved_ready "
           "{reading: ok, starved: 0, late_ready: 0, why: 'no READY work is past its band SLA'} "
           "with parallelism.utilisation 0.98 (the worker busy) -- long-running work is not "
           "starving smaller READY jobs; band SLAs are the fairness bound")

SMOKE = (f"{EV}/prod_api_verify_smoke_20261019T1308Z.json (production 1b21e81, "
         f"{EV}/prod_health_20261019T1308Z.json build.commit): verdict PASS on every check -- "
         "probe_ran:model.probe, probe_ran:vision.probe, probe_ran:etsy.probe, "
         "continuity_restore_proven, cadence_coverage, queue_round_trip, "
         "search_intelligence_captured; HTTP 200 (the route never answers 200 unless PASS)")
READBACK = (f"{EV}/readback_1b21e81_20261019T1308Z.json: ops/readback.py --sha 1b21e81 run "
            "after the deploy: 11 PASS, 1 FAIL (no unexpected dead letters, #195)")

FM_EDITS = {
    ("s2", "F-171"): {
        "coverage": "FULL",
        "missing_part": None,
        "consumer": "ops/readback.py MANIFEST 'smoke matrix' (run by ops/deploy.sh after every "
                    "deploy; exit 5 unless PASS)",
        "next_action": "none -- the smoke matrix passed on the deployed 1b21e81",
        "evidence+": [SMOKE, READBACK],
        "tests+": ["tests/test_w4_smoke.py::test_a_healthy_production_passes_every_check_and_a_refused_probe_still_ran",
                   "tests/test_w4_smoke.py::test_stale_cadences_and_a_stopped_queue_fail",
                   "tests/test_w4_smoke.py::test_the_smoke_route_is_public_read_only_and_never_200_unless_pass"],
    },
    ("s8", "F-697"): {
        "coverage": "FULL",
        "missing_part": None,
        "gate": {"kind": "none", "key": None,
                 "detail": "offsite_storage OPEN in production (1b21e81): the gate read an "
                           "actual off-provider round trip, not a variable"},
        "next_action": "none -- offsite archive and restore drill run in production",
        "evidence+": [OFFSITE, CONTINUITY,
                      "durable_artifacts (the canonical model's approved body frames) is not in "
                      "core/continuity.EXCLUDED_TABLES, so its payload bytes ride in the offsite "
                      "archive (tests/test_w4_board_close.py::"
                      "test_f697_durable_artifacts_ride_in_the_continuity_export)"],
        "tests+": ["tests/test_offsite.py::test_a_complete_round_trip_restores_the_company",
                   "tests/test_w4_board_close.py::"
                   "test_f697_durable_artifacts_ride_in_the_continuity_export"],
    },
    ("s6", "F-486"): {
        "consumer": "src/brambleloop/runtime/worker.py::Worker.run_once (claims through "
                    "JobQueue.claim, so the aged ordering is what the worker executes)",
        "gate": {"kind": "none", "key": None,
                 "detail": "deployed: queue/durable.py aging runs in production 1b21e81"},
        "next_action": "none -- deployed and read in production",
        "evidence+": [STARVED],
    },
}

B2_CLOSE = {
    51: ("\n\nCLOSED 2026-10-19 (W4-BOARD) on production readings of the deployed 1b21e81: the "
         "offsite_storage gate is OPEN and the copy outside this provider exists and restores. "
         + OFFSITE + ". " + CONTINUITY + ". Rendered PDFs/charts stay re-derivable from the "
         "archived CIR + code, as recorded above."),
}


def main() -> int:
    remap = []
    for (sl, uid), ed in FM_EDITS.items():
        path = FB / "mapping" / f"{sl}.json"
        rows = json.loads(path.read_text())
        for r in rows:
            if r["uid"] != uid:
                continue
            for k, v in ed.items():
                if k.endswith("+"):
                    key = k[:-1]
                    r[key] = list(r.get(key) or []) + [x for x in v if x not in (r.get(key) or [])]
                else:
                    r[k] = v
            remap.append(r)
        path.write_text(json.dumps(rows, indent=1, ensure_ascii=False) + "\n")
    out = FB / "mapping" / "remap_1b21e81"
    out.mkdir(exist_ok=True)
    (out / "remap_w4_board.json").write_text(json.dumps(remap, indent=1) + "\n")

    reg_path = BL / "src/brambleloop/build2/requirements.json"
    reg = json.loads(reg_path.read_text())
    for r in reg:
        if r["id"] in B2_CLOSE and r["status"] != "covered":
            r["status"] = "covered"
            r["note"] = r["note"] + B2_CLOSE[r["id"]]
            r["proof"] = "tests/test_continuity.py tests/test_offsite.py"
            r.pop("parked_on", None)
    reg_path.write_text(json.dumps(reg, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"fm": [u for _s, u in FM_EDITS], "build2": list(B2_CLOSE)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
