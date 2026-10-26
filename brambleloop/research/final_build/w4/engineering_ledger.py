#!/usr/bin/env python3
"""Workstream B status ledger: every Build 2 (320) and Final Master (917) row, A-H.

Deterministic, from committed evidence only (W4-FMBATCH1, 2026-10-26):
  * the newest completion board, `COMPLETION_BOARD_FINAL.json` at final-candidate-d69a3ec
    (generated 2026-10-21T11:36Z against production b931d17);
  * the closure matrix at d69a3ec (maturity, coverage, tests, missing_part per FM row);
  * FM_LEDGER.json / BUILD2_LEDGER.json as committed at b997efd, which is what production runs
    now (GET /health 2026-10-26: build.commit 15800536 = b997efd + release-record commits);
  * the src/ tree at b997efd;
  * the rows this lane built on claude/w4-FMBATCH1 (not deployed) and on claude/w4-CLOSE6
    (not merged), named explicitly in BRANCH_WORK below.

Statuses (owner directive 2026-10-25):
  A not implemented | B partial | C implemented, untested | D tested, not integrated |
  E integrated, not deployed | F deployed, awaiting verification | G verified |
  H waiting on owner/external evidence.
NA rows (ledger NOT-APPLICABLE, with the registry's reason) are listed as NA and counted as
NOT complete in both measures: nothing is waived. A row whose status the evidence does not
settle carries `unclear: true` and the reason. No row is closed here.

  python3 research/final_build/w4/engineering_ledger.py BOARD MATRIX FM_LEDGER B2_LEDGER TREE
"""
from __future__ import annotations

import json
import sys
from collections import Counter

LEVELS = ["MISSING", "IMPLEMENTED", "TESTED", "INTEGRATED", "DEPLOYED", "EXERCISED",
          "PRODUCTION-OBSERVED", "COMMERCIALLY-EVIDENCED"]
DONE_FM = {"PROVEN", "COMPLETE"}
DONE_B2 = {"PROVEN"}

# Work that exists on a branch the board did not read. Status + why + where.
BRANCH_WORK = {
    "F-010": ("E", "claude/w4-FMBATCH1 89bc962a: integrations/taxonomy_drift.py + tests"),
    "F-381": ("E", "claude/w4-FMBATCH1 be3fdd6a: ops/rollback_decision.py + deploy.sh"),
    "F-380": ("E", "guarded deploy path deployed; blast-radius half = F-381 on FMBATCH1"),
    "F-540": ("F", "deployed; production shows daily HEALTHY + rotation (evidence_FMBATCH1); "
                   "closure proposed, not accepted"),
    "F-100": ("F", "deployed packet served in production; closure proposed, not accepted"),
    "F-405": ("E", "claude/w4-FMBATCH1 024897cc research batch R"),
    "F-408": ("E", "claude/w4-FMBATCH1 024897cc research batch R"),
    "F-411": ("E", "claude/w4-FMBATCH1 024897cc research batch R"),
    "F-419": ("E", "claude/w4-FMBATCH1 024897cc research batch R"),
    "F-420": ("E", "claude/w4-FMBATCH1 024897cc research batch R"),
    "F-426": ("E", "claude/w4-FMBATCH1 024897cc research batch R"),
    "F-432": ("E", "claude/w4-FMBATCH1 024897cc research batch R"),
    "F-435": ("E", "claude/w4-FMBATCH1 024897cc research batch R"),
    "F-444": ("E", "claude/w4-FMBATCH1 024897cc research batch R"),
    "F-449": ("E", "claude/w4-FMBATCH1 024897cc research batch R"),
    "F-412": ("B", "claude/w4-FMBATCH1: bounded next_test recorded; no path into improve/runner"),
    "F-144": ("E", "claude/w4-CLOSE6 (unmerged): readback rule + 6 features"),
    "F-834": ("E", "claude/w4-CLOSE6 (unmerged): consumer receipts; TESTED override accepted"),
    "F-040": ("E", "claude/w4-CLOSE6 (unmerged): About reading path"),
    "F-846": ("D", "TESTED target accepted on claude/w4-CLOSE6 (D-W4-CLOSE6-F846), not applied"),
    "F-872": ("F", "closed on production b931d17 by claude/w4-CLOSE6 (unmerged)"),
    # W4-FMBATCH1 rows built after the first ledger generation (regenerated 2026-10-26).
    'F-139': ('E', 'claude/w4-FMBATCH1 batch O: ops/signal_hygiene.py + tests (FMBATCH1.md §9)'),
    'F-140': ('E', 'claude/w4-FMBATCH1 batch O: ops/signal_hygiene.py + tests (§9)'),
    'F-149': ('E', 'claude/w4-FMBATCH1 batch O: ops/signal_hygiene.py + tests (§9)'),
    'F-092': ('E', 'claude/w4-FMBATCH1 batch P: scale/dependency.register + tests (§10)'),
    'F-093': ('E', 'claude/w4-FMBATCH1 batch P: existential until a fallback drill (§10)'),
    'F-094': ('E', 'claude/w4-FMBATCH1 batch P: diversification_trigger (§10)'),
    'F-095': ('B', 'claude/w4-FMBATCH1: fallback contract built; a same-provider fallback with UNKNOWN quality/latency still routes (needs per-model golden evals); contract exceptions no longer route (review F-10, 5fec6bb0)'),
    'F-099': ('E', 'claude/w4-FMBATCH1 batch P: gateway/provider_watch.py (§10)'),
    'F-150': ('E', 'claude/w4-FMBATCH1: scripts/classify_failure.py + run_tests.sh (§11; review F-6 07903e57)'),
    'F-200': ('E', 'claude/w4-FMBATCH1 batch D: dashboard decision order (§12)'),
    'F-201': ('E', 'claude/w4-FMBATCH1 batch D: folds with summaries (§12)'),
    'F-394': ('E', 'claude/w4-FMBATCH1 batch I (§15)'),
    'F-470': ('E', 'claude/w4-FMBATCH1 batch I: swarm/resources storage and I/O (§15)'),
    'F-489': ('E', 'claude/w4-FMBATCH1 batch I: swarm/metrics.parallel_window (§15)'),
    'F-457': ('E', 'claude/w4-FMBATCH1 batch I (§15); override proposed (OVERRIDES_PROPOSED_FMBATCH1_B)'),
    'F-398': ('E', 'claude/w4-FMBATCH1: improve/cells audit record (§16)'),
    'F-621': ('E', 'claude/w4-FMBATCH1: company departments + KPI trend drawn (§17, §19)'),
    'F-661': ('E', 'claude/w4-FMBATCH1 batch C: executive command center (§17)'),
    'F-668': ('E', 'claude/w4-FMBATCH1 batch C: agents workspace (§17)'),
    'F-729': ('E', 'claude/w4-FMBATCH1 batch C + f2efa2ba: autonomy block with useful-work readings'),
    'F-431': ('E', 'claude/w4-FMBATCH1: intel/research_fetch run + promotion (§18; review F-2/F-8 617097b0)'),
    'F-153': ('E', 'claude/w4-FMBATCH1 418d59c8: ops/signing_audit.py; signing is unavailable and reported so (§20; review F-7 07903e57)'),
    'F-156': ('E', 'claude/w4-FMBATCH1 418d59c8: ops/SIGNING_RECOVERY.md + test (§20)'),
    'F-157': ('E', 'claude/w4-FMBATCH1 418d59c8: release-record signing evidence (§20)'),
    'F-107': ('E', 'claude/w4-FMBATCH1 d2fd5071: finance/value_units.py (§21)'),
    'F-089': ('E', 'claude/w4-FMBATCH1 fccea594: quality/physical_truth + /api/physical-truth (§21; review F-9 07903e57)'),
    'F-096': ('E', 'claude/w4-FMBATCH1 ae9d7b89: gateway/compat_pack.py (§21; review F-4/F-5 330ed7c9); no live provider has run it (a paid drill)'),
    'F-091': ('B', 'claude/w4-FMBATCH1: gateway/providers.py boundary + import ratchet; 26 direct vendor importers remain (visual/creative/publish lanes) (§21)'),
    'F-190': ('E', 'claude/w4-FMBATCH1 b555f5f1: evidence-gate share per class (§22)'),
    'F-194': ('E', 'claude/w4-FMBATCH1 07807184: seasonal cohorts (§22)'),
    'F-198': ('E', 'claude/w4-FMBATCH1 7f4a898f: owned_surfaces why_required; card held (§22)'),
    'F-374': ('E', 'claude/w4-FMBATCH1 c26c58f0: pricing_shadow trial (§22); price-at-outcome writer is in the listings lane, after the listings release'),
    'F-389': ('E', 'claude/w4-FMBATCH1 04ac701f: improve/cost_learning.py (§22)'),
    'F-601': ('B', 'claude/w4-FMBATCH1 871b84a3: department records with honest coverage; compliance/policy and analytics have no charter, executive no cell'),
    'F-454': ('B', 'claude/w4-FMBATCH1 871b84a3: domains mapped; analytics and integration have no agent; build-side lanes not visible to the runtime'),
    'F-656': ('E', 'claude/w4-FMBATCH1 871b84a3: RUN->GROW->IMPROVE pull, WATCHING spans (review F-11 5fec6bb0)'),
    'F-602': ('B', 'claude/w4-FMBATCH1 d6189dc2: executive plan read by swarm.allocate; merge/deploy queue and file ownership stay build-side'),
    'F-719': ('E', 'claude/w4-FMBATCH1 f2efa2ba: ops/useful_work readings (untouched opportunities UNMEASURED: no runtime table)'),
    'F-720': ('E', 'claude/w4-FMBATCH1 f2efa2ba: diagnosed ready-work alarm'),
    'F-722': ('E', 'claude/w4-FMBATCH1 c089c7bd: worker refill on a terminal event'),
    'F-653': ('E', 'claude/w4-FMBATCH1 60ba9bb5: breakpoints, scrolling tables, /m'),
    'F-620': ('E', 'claude/w4-FMBATCH1 956a6a3f: /api/finance owner_view'),
    'F-827': ('E', 'claude/w4-FMBATCH1 8eaaec6b: Studio Learn dashboard card'),
    # Build 2: the cohort/LTV code is live; only real buyers' orders are missing. The re-park
    # transactions_r -> customers is ACCEPTED on claude/w4-CLOSE6 (B2_REGATE_PROPOSED_CLOSE6).
    11: ("H", "code live (orders_ingest every 6 h, 0 receipts); waits on real buyers"),
    12: ("H", "code live (orders_ingest every 6 h, 0 receipts); waits on real buyers"),
}
# Blockers named by this lane's triage (FMBATCH1.md sections 3 and 4) where the board's root is
# not specific enough.
TRIAGE_BLOCKER = {
    **{u: ("missing production evidence", "release b997efd is deployed; the first daily refresh "
           "reads the property schemas; Etsy's answer decides CHOSEN/UNKNOWN")
       for u in ("F-005", "F-007", "F-009", "F-243", "F-247")},
    **{u: ("missing prerequisite", "owner approval of the batch-scoped vision review "
           "(W-LISTREADY, max CA$7.07)") for u in ("F-027", "F-031", "F-041", "F-252")},
    "F-437": ("missing prerequisite", "owner authorises the Etsy create/read/delete exercise"),
    "F-396": ("missing production evidence", "24 h unattended window (#195)"),
    "F-628": ("missing production evidence", "24 h unattended window (#195)"),
    "F-273": ("genuine external dependency", "a real settlement (customers)"),
    "F-538": ("genuine external dependency", "a real settlement (customers)"),
    11: ("genuine external dependency", "real buyers (re-gate to customers accepted on CLOSE6)"),
    12: ("genuine external dependency", "real buyers (re-gate to customers accepted on CLOSE6)"),
    195: ("missing production evidence", "the window has now passed in production (WINDOW_NOTE); "
          "acceptance against the row's full criterion (costs, recovery evidence) is owed"),
}
WINDOW_NOTE = ("production b997efd: autonomy.off_device_proof passed=true over "
               "2026-10-25T01:03Z..10-26T01:03Z (1417 jobs, 97 types, 25 hours, 0 unexpected "
               "dead letters; evidence_FMBATCH1/prod_api_build_20261026T0103Z.json)")
# Build 2 customer/external rows whose measurement-and-response software is complete and
# tested on claude/w4-FMBATCH1; only the real-world evidence remains (acceptance stays H).
ENGINEERING_EVIDENCE = {
    8: "quality/proof.py _customer_rungs (consented customer photo; repeat buyer) + check_claim; "
       "tests/test_w4_fmbatch1_proof_customer.py, tests/test_proof.py (ca2a60e4)",
    20: "growth/owned.py counterparts, owned_share (orders by owned channel), "
        "assisted_conversions; CASL send_gate; tests/test_w4_fmbatch1_owned_assisted.py, "
        "tests/test_owned.py (ca2a60e4)",
    21: "growth/creators.py measure_outcome/scaling_decision from rows + may_scale, briefs, "
        "disclosure; tests/test_w4_fmbatch1_creator_outcomes.py, tests/test_creators.py "
        "(ca2a60e4)",
    23: "commerce/kill_table.py route/compose + learn() thresholds from listing outcomes, "
        "wired in runtime/commerce_readings; tests/test_w4_fmbatch1_kill_learn.py, "
        "tests/test_kill_table.py, tests/test_cert_commerce_readings.py (ca2a60e4)",
    292: "seasonal/remerchandising.py candidates (exact-slug sales, proven evergreen), moves, "
         "check_move; tests/test_w4_fmbatch1_remerch.py, tests/test_remerchandising.py "
         "(01f62da6)",
}

OWN_LANE_OTHER = {"F-594": "W-FIRSTSALE2", "F-733": "Workstream C (Laura canonical identity)"}


def _lvl(m):
    return LEVELS.index(m) if m in LEVELS else -1


def _matrix_status(cm: dict) -> tuple[str, bool, str]:
    cov = (cm.get("coverage") or "").upper()
    mat = cm.get("maturity") or ""
    if not cm:
        return "B", True, "no closure-matrix row"
    if cov in ("NONE", "MISSING") or mat == "MISSING":
        return "A", False, f"matrix coverage {cov or '-'} maturity {mat or '-'}"
    if cov == "PARTIAL":
        return "B", False, f"matrix coverage PARTIAL: {(cm.get('missing_part') or '')[:160]}"
    i = _lvl(mat)
    if i <= _lvl("IMPLEMENTED"):
        return "C", False, f"coverage FULL, maturity {mat}"
    if i == _lvl("TESTED"):
        return "D", False, "coverage FULL, maturity TESTED"
    if i == _lvl("INTEGRATED"):
        return "E", False, "coverage FULL, maturity INTEGRATED"
    return "F", False, f"coverage FULL, maturity {mat}"


def _blocker(row: dict, cm: dict) -> tuple[str, str]:
    uid = row["id"]
    if uid in TRIAGE_BLOCKER:
        return TRIAGE_BLOCKER[uid]
    if uid in BRANCH_WORK:
        st = BRANCH_WORK[uid][0]
        kind = ("missing production evidence" if st == "F" else
                "missing implementation" if st in ("A", "B") else "missing integration")
        return (kind, f"{BRANCH_WORK[uid][1]}")
    root = row.get("root")
    if root == "release_not_deployed":
        return ("missing production evidence", WINDOW_NOTE + "; to be read against the row")
    if root == "gate_open_reverify":
        return ("missing production evidence", f"gate open in production; re-verify: "
                f"{(row.get('remaining') or '')[:160]}")
    text = " ".join(str(cm.get(k) or "") for k in ("missing_part", "next_action")).lower()
    tests = cm.get("tests") or []
    if any(w in text for w in ("not deployed", "019ebf0 only", "on 019ebf0", "deploy ")):
        return ("missing production evidence", (cm.get("missing_part") or "")[:200])
    if (cm.get("maturity") == "TESTED" and (cm.get("coverage") or "").upper() == "FULL"):
        return ("missing integration", "maturity TESTED below the INTEGRATED target")
    if not tests:
        return ("missing implementation", "no test cited; " + (cm.get("missing_part") or "")[:180])
    return ("missing implementation", (cm.get("missing_part") or cm.get("next_action") or "")[:200])


def build(board, matrix, fm_ledger, b2_ledger, tree) -> dict:
    cmap = {r["uid"]: r for r in matrix["matrix"]}
    fml = {r["uid"]: r for r in fm_ledger["rows"]}
    b2rows = b2_ledger["rows"]
    b2l = {r["id"]: r for r in (b2rows if isinstance(b2rows, list) else b2rows.values())}
    have = set(tree)
    out = {"build2": [], "final_master": []}
    for src in ("build2", "final_master"):
        for row in board["rows"][src]:
            uid, cls = row["id"], row["cls"]
            cm = cmap.get(uid, {}) if src == "final_master" else {}
            rec = {"id": uid, "title": row.get("title"), "scope": row.get("scope"),
                   "board_class": cls, "board_root": row.get("root"), "unclear": False}
            mods_in = all(m in have for m in row.get("modules") or []) if row.get("modules") \
                else None
            if src == "final_master":
                led = (fml.get(uid) or {}).get("status")
            else:
                led = (b2l.get(uid) or {}).get("state")
            done_deployed = (led in (DONE_FM if src == "final_master" else DONE_B2)) and \
                mods_in is not False
            if uid in BRANCH_WORK:
                st, why = BRANCH_WORK[uid]
                rec.update(status=st, why=why)
            elif cls == "verified_complete":
                rec.update(status="G", why=row.get("evidence", "")[:200])
            elif cls == "not_applicable":
                rec.update(status="NA", why="ledger NOT-APPLICABLE (registry reason); counted "
                                            "as not complete, never waived")
            elif cls == "implemented_unverified":
                if done_deployed:
                    rec.update(status="F", why="complete in the ledger committed at b997efd and "
                               "every named module is in the b997efd tree production now runs; "
                               "production verification of this row not yet read")
                else:
                    rec.update(status="E", why="proven on an integration branch after b997efd "
                               "(or a named module is absent from it): awaits a release")
                if row.get("recount") == "implemented_unverified":
                    rec.update(unclear=True, why=rec["why"] + "; spot audit downgraded this row "
                               "(BOARD_AUDIT.json)")
            elif cls == "in_progress":
                rec.update(status="B", unclear=True,
                           why=f"in progress on {row.get('responsible')}; status of that "
                               "branch's work not read here")
            elif cls in ("blocked_owner", "blocked_external"):
                rec.update(status="H", why=row.get("blocked_by") or "")
            else:  # blocked_engineering
                if src == "final_master":
                    st, unc, why = _matrix_status(cm)
                    if row.get("root") == "release_not_deployed":
                        st, why = "F", (WINDOW_NOTE + "; this row's own criterion still "
                                        "has to be read against it (closure not proposed "
                                        "row by row yet)")
                    rec.update(status=st, unclear=unc, why=why)
                elif row.get("root") == "release_not_deployed":
                    rec.update(status="F", why=WINDOW_NOTE)
                else:
                    rec.update(status="B", why=row.get("remaining") or "")
                kind, detail = _blocker(row, cm)
                rec["blocker"] = {"kind": kind, "detail": detail}
            if cls == "blocked_engineering" and "blocker" not in rec:
                kind, detail = _blocker(row, cm)
                rec["blocker"] = {"kind": kind, "detail": detail}
            if uid in OWN_LANE_OTHER:
                rec["owned_by"] = OWN_LANE_OTHER[uid]
            # engineering completion: built + integrated + tested
            if src == "final_master":
                eng = rec["status"] in ("E", "F", "G") or (
                    rec["status"] == "H" and _lvl(cm.get("maturity")) >= _lvl("INTEGRATED")
                    and bool(cm.get("tests")))
            else:
                ev = (b2l.get(uid) or {}).get("evidence") or {}
                live = any(c.get("live") for c in ev.get("runtime_consumers") or [])
                eng = rec["status"] in ("E", "F", "G") or (
                    rec["status"] == "H" and live and bool(ev.get("tests")))
            if src != "final_master" and uid in ENGINEERING_EVIDENCE:
                eng = True
                rec["engineering_evidence"] = ENGINEERING_EVIDENCE[uid]
            rec["engineering_complete"] = bool(eng)
            rec["acceptance_complete"] = rec["status"] == "G"
            out[src].append(rec)
    summary = {}
    for src, rows in out.items():
        n = len(rows)
        summary[src] = {
            "total": n, "by_status": dict(sorted(Counter(r["status"] for r in rows).items())),
            "unclear": sum(1 for r in rows if r["unclear"]),
            "engineering_completion": {"numerator": sum(r["engineering_complete"] for r in rows),
                                       "denominator": n},
            "acceptance_completion": {"numerator": sum(r["acceptance_complete"] for r in rows),
                                      "denominator": n},
            "blocked_engineering_blockers": dict(Counter(
                r["blocker"]["kind"] for r in rows if "blocker" in r)),
        }
    return {"kind": "brambleloop.engineering_ledger", "generated_by":
            "research/final_build/w4/engineering_ledger.py",
            "sources": {"board": "final-candidate-d69a3ec COMPLETION_BOARD_FINAL.json "
                                 f"(generated {board.get('generated_at')})",
                        "matrix": "final-candidate-d69a3ec closure_matrix.json",
                        "ledgers": "FM_LEDGER.json / BUILD2_LEDGER.json at b997efd",
                        "deployed": "b997efd (production /health 15800536, 2026-10-26)",
                        "branch_work": "claude/w4-FMBATCH1 (rows above, through 8eaaec6b), claude/w4-CLOSE6 ff788bd"},
            "definitions": {
                "engineering_completion": "status E, F or G; or H with the engineering half "
                    "integrated and tested (FM: matrix maturity >= INTEGRATED with cited tests; "
                    "Build 2: a live runtime consumer and a cited test). Independent review is "
                    "not tracked per row, so it is not part of the numerator's evidence",
                "acceptance_completion": "status G only: the full original criterion met, "
                    "production (and customer, where the criterion says so) evidence included"},
            "summary": summary, "rows": out}


def main(argv):
    board, matrix, fml, b2l, tree = argv[1:6]
    data = build(json.load(open(board)), json.load(open(matrix)), json.load(open(fml)),
                 json.load(open(b2l)), [x.strip() for x in open(tree) if x.strip()])
    out = argv[6] if len(argv) > 6 else "ENGINEERING_LEDGER.json"
    with open(out, "w") as f:
        json.dump(data, f, indent=1)
        f.write("\n")
    print(json.dumps(data["summary"], indent=1))


if __name__ == "__main__":
    main(sys.argv)
