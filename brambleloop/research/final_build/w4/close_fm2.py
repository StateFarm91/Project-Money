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
        set=dict(coverage="FULL", defect=None, missing_part=None,
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
