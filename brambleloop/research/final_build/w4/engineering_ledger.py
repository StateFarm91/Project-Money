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
                        "branch_work": "claude/w4-FMBATCH1 024897cc, claude/w4-CLOSE6 ff788bd"},
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
