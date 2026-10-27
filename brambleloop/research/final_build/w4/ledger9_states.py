#!/usr/bin/env python3
"""W4-LEDGER9: per-row delivery states for every Final Master and Build 2 ledger row.

Reads `ENGINEERING_LEDGER.json` (after `engineering_ledger.py` and `b0_reconcile.py`), the two
Final Master registries and git. Changes no row of the ledger. Writes `LEDGER9_STATES.json`.

Per row, two layers (owner directives 2026-10-27):

  facts (what the code is):  built, tested, integrated, reviewed, deployed
      (yes / partial / no / unverified / not_recorded / n/a)
  six states (what the requirement is). States 1-4 are a cascade: each is "yes" only if
  the one before it is. States 5 and 6 rest on their own records, and a defect blocks them:
    1 implementation_complete   yes | defective | unverified | partial | no | n/a
    2 integration_complete      yes | defective | no | n/a
    3 production_deployed       yes | defective | not_recorded | no | n/a
    4 production_verified       yes | pending (deployed, not yet production-verified) |
                                defective | no | n/a  -- production evidence only: a committed
                                production readback or production reading of the row, on top
                                of the ledger's acceptance; a deployed-tree test run is a test
    5 e2e_acceptance            passed | defective | not_passed | n/a  -- a committed
                                workflow-level record (production acceptance run, launch
                                rehearsal or equivalent); unit tests never count
    6 business_outcome          proven | no | n/a  -- real customer or revenue evidence
  gate: owner | data_customer | external | by_design | not_gated | n/a  (why acceptance is open)

A row whose intended workflow cannot execute because of a launch defect named in
LAUNCH_PATH.md (D1, D2, E3, E4; see DEFECTS) is "defective" from state 1 on, whatever its
ledger class says.

Deployed and production_verified are computed against a production SHA given on the command
line, never inferred: a row is deployed only when every commit recorded for it (the deployed
tree the ledger named, plus every later code commit naming the row) is an ancestor of that
SHA. Re-run after each deploy:

  python3 research/final_build/w4/ledger9_states.py --production <sha> [--integrated <ref>]

Gates are only assigned to rows whose engineering is built; unbuilt work is never gated here.
The script exits 1 if the Final Master rows are not exactly the registry's records, or if any
count does not reconcile to the row total.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]                                   # brambleloop/
sys.path.insert(0, str(HERE))
import b0_reconcile as b0                                # noqa: E402  (constants only)

LEDGER = HERE / "ENGINEERING_LEDGER.json"
OUT = HERE / "LEDGER9_STATES.json"

# SHAs the ledger text cites as references (candidates, production), not as row changes.
IN_CANDIDATE = ("COMPLETE", "AWAITING_EVIDENCE", "PROPOSED_COMPLETE")
REFERENCE_SHAS = {"2aeb177f", "e584ff01", "ee35a493", "b2e49455", "15800536", "d69a3ec"}
DEPLOY_BASIS = ("b931d17", "b997efd")                    # the ledger's deployed trees

OWNER_ROOTS = {"insights_paste", "paid_media_authority", "owned_surfaces",
               "testers_physical_proof", "benchmark_purchases", "etsy_shop_settings",
               "owner_rulings", "owner_other", "banking_feeds", "provider_admin_keys",
               "live_listings", "launch0_cap_CAP1", "model_credits", "visual_paid_generation",
               "oauth_transactions_r"}
DATA_ROOTS = {"real_customers", "data_accrual"}
EXTERNAL_ROOTS = {"etsy_no_api_or_403", "etsy_credential_403", "image_provider_capability",
                  "session_environment"}
# Not gates: engineering, release or re-verification work still to do.
OPEN_ROOTS = {"engineering_open", "release_undeployed_code", "release_not_deployed",
              "gate_open_reverify", "audit_criterion_not_demonstrated"}

# ---- launch defects (research/final_build/w4/LAUNCH_PATH.md on origin/claude/w4-LAUNCH1) ----
DEFECTS = {
    "D1": "gates.first_customer.check_etsy_remote_state reads the static literal "
          "publish.listing_schema.gaps(), so etsy_remote_state is permanently UNVERIFIABLE and "
          "store.publish is blocked before the first draft (LAUNCH_PATH s0 D1, s5 E1)",
    "D2": "launch.readiness.assess hard-codes listing_fees and brand_clearance ready=False with "
          "no evidence path, so transition_verdict is never ready and core.phase."
          "record_transition refuses every upward move (LAUNCH_PATH s0 D2, s5 E2)",
    "E3": "gates.platform_policy.record_page_reading passes no compare_basis, so the owner's "
          "first page reading of a source counts as a material policy change and opens a "
          "halting P1 (LAUNCH_PATH s5 E3)",
    "E4": "integrations.etsy_taxonomy.pattern_subtree matches no Etsy node, so no taxonomy "
          "node is chosen and the search certificate FAILs on every product (LAUNCH_PATH s1 A7, "
          "s5 E4; PRODREADY B2)",
}
# role "contains": the row's own requirement is what the defective code implements.
# role "workflow": the row's intended workflow must pass through the defective code.
DEFECT_ROWS = {
    # D1: the first-customer gate's remote-state area is F-594's "remote Etsy
    # write/read/delete proof before first publication"; no draft is ever created, so the
    # publish read-back (F-542) and draft-to-live activation (F-543) never run.
    "F-594": (("D1", "contains"),),
    "F-542": (("D1", "workflow"),),
    "F-543": (("D1", "workflow"), ("D2", "workflow"), ("E4", "workflow")),
    # D2: F-300 is the verdict assess() computes (launch/readiness.py cites it); #54 names the
    # brand/name clearance checkpoint; F-299's owner-approved phase change can never record.
    "F-300": (("D2", "contains"),),
    "B2#54": (("D2", "contains"),),
    "F-299": (("D2", "workflow"),),
    # E3: platform_policy implements #39 (cited in the module); F-536 is the same freshness
    # watch on the Final Master side.
    "B2#39": (("E3", "contains"),),
    "F-536": (("E3", "contains"),),
    # E4: F-005 is the category choice itself; etsy_taxonomy cites F-005/F-006/F-007/F-009;
    # release_gates.search_gate cites F-004/F-005/F-294; F-243/F-247 read the F-005 snapshot.
    "F-005": (("E4", "contains"),),
    "F-004": (("E4", "workflow"),),
    "F-294": (("E4", "workflow"),),
    "F-006": (("E4", "workflow"),),
    "F-007": (("E4", "workflow"),),
    "F-009": (("E4", "workflow"),),
    "F-243": (("E4", "workflow"),),
    "F-247": (("E4", "workflow"),),
}

# ---- production and end-to-end evidence (committed records only) ---------------------------
BOARD = HERE / "COMPLETION_BOARD_FINAL.json"
# closed_on_production_evidence rows whose reading is a production reading, not a test run on
# the deployed tree (the board's own reading text, quoted in LEDGER9.md).
CPE_PRODUCTION_READING = {"F-152", "F-299", "F-685", "F-878"}
# Workflow-level records: the row's own workflow ran end to end and the record says it passed.
E2E_RECORDS = {
    "B2#195": "autonomy.off_device_proof passed=true over 2026-10-25T01:03Z..10-26T01:03Z on "
              "production b997efd (evidence_FMBATCH1/prod_api_build_20261026T0103Z.json)",
    "B2#181": "24 h off_device_proof window on production 1b21e81 (evidence_BOARD/"
              "prod_api_build_20261019T1249Z.json; board audit PASS_PRODUCTION)",
    "F-152": "off-site archive written, read back and restored on production b931d17 "
             "(evidence_BOARD/prod_readback_b931d17a738d_20261020T1215Z.json)",
    "F-878": "launch packet generated by the deployed tree, recorded_suite PASS for every "
             "section (board closed_on_production_evidence)",
}
# Real customer or revenue evidence: none exists (production store.published = 0, no orders;
# LAUNCH_PATH s1 Stage E). Any future record is added here with its source.
BUSINESS_OUTCOME_RECORDS: dict = {}

SHA_RE = re.compile(r"\b[0-9a-f]{7,8}\b")
CODE_PREFIXES = ("brambleloop/src/", "brambleloop/tests/", "ops/", "brambleloop/scripts/",
                 "brambleloop/run_tests.sh")


def git(*a: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True)


@lru_cache(maxsize=None)
def resolve(sha: str) -> str | None:
    p = git("rev-parse", "--verify", "--quiet", f"{sha}^{{commit}}")
    return p.stdout.strip()[:8] if p.returncode == 0 else None


@lru_cache(maxsize=None)
def files(sha: str) -> tuple:
    return tuple(n for n in git("show", "--name-only", "--format=", sha).stdout.split() if n)


@lru_cache(maxsize=None)
def ancestor(sha: str, ref: str) -> bool:
    return git("merge-base", "--is-ancestor", sha, ref).returncode == 0


def is_code(sha: str) -> bool:
    return any(n.startswith(CODE_PREFIXES) for n in files(sha))


def touches_tests(sha: str) -> bool:
    return any(n.startswith("brambleloop/tests/") for n in files(sha))


def rid_of(row: dict) -> str:
    return row["id"] if isinstance(row["id"], str) else f"B2#{row['id']}"


def change_shas(row: dict) -> list[str]:
    """Code commits recorded for the row: branch_work, plus SHAs the ledger/B0 text names."""
    out = []
    for w in row.get("branch_work") or []:
        if w["sha"] not in b0.NOT_CODE:
            out.append(w["sha"])
    text = row.get("b0_reason", "") + " " + ("" if row["status"] in "FG" else row["why"])
    rid = rid_of(row)
    if rid in b0.OWNER_HELD:
        text += " " + b0.OWNER_HELD[rid]
    if rid in b0.OVERRIDE_BRANCH:
        text += " " + b0.OVERRIDE_BRANCH[rid][1]
    for s in SHA_RE.findall(text):
        if s[:7] in {x[:7] for x in REFERENCE_SHAS | set(DEPLOY_BASIS)}:
            continue
        full = resolve(s)
        if full and full not in out:
            out.append(full)
    return [s for s in dict.fromkeys(out) if resolve(s) and is_code(s)]


def deploy_basis(row: dict, ledger_deployed: str) -> str | None:
    """The deployed tree the ledger itself named for an F/G row (never inferred for others)."""
    if row["status"] not in ("F", "G"):
        return None
    for s in DEPLOY_BASIS:
        if s in row["why"]:
            return s
    return ledger_deployed        # F row asserted deployed against the ledger's production


SIX = ("implementation_complete", "integration_complete", "production_deployed",
       "production_verified", "e2e_acceptance", "business_outcome")


def load_prod_records() -> dict:
    """Committed production records per row, from the completion board (b931d17 readings)."""
    out: dict = {}
    board = json.loads(BOARD.read_text())
    for scope in ("final_master", "build2"):
        for x in board["rows"][scope]:
            rid = x["id"] if scope == "final_master" else f"B2#{x['id']}"
            rb = x.get("readback")
            if rb and not rb.get("not_passing"):
                out.setdefault(rid, []).append(f"readback {rb['file']}: "
                                               f"{', '.join(rb['features'])}")
            cpe = x.get("closed_on_production_evidence")
            if cpe and rid in CPE_PRODUCTION_READING:
                out.setdefault(rid, []).append(f"production reading: {cpe.get('reading')}")
            au = x.get("audit") or {}
            if au.get("production_reading") and au.get("verdict") in ("PASS",
                                                                       "PASS_PRODUCTION"):
                out.setdefault(rid, []).append(f"audit {au['verdict']}: "
                                               f"{au['production_reading'][:200]}")
    return out


prod_records: dict = {}


def states(row: dict, prod: str, integ: str, ledger_deployed: str) -> dict:
    rid, cls = rid_of(row), row["b0_class"]
    if cls == "NOT_APPLICABLE":
        na = {k: "n/a" for k in ("built", "tested", "integrated", "reviewed", "deployed",
                                 "production_verified")}
        return {**na, "gate": "n/a", "evidence": {"reason": row["b0_reason"][:200]},
                "six": {k: "n/a" for k in SIX}, "defects": []}
    shas = change_shas(row)
    basis = deploy_basis(row, ledger_deployed)
    ev: dict = {"change_shas": shas, "deploy_basis": basis}
    eng = row["engineering_complete"]

    # Built
    if eng or cls in ("COMPLETE", "COMPLETE_ON_BRANCH", "OWNER_HELD", "AWAITING_EVIDENCE",
                      "PROPOSED_COMPLETE", "MISSING_INTEGRATION"):
        built = "yes"
    elif cls == "BY_DESIGN" or rid == "F-652":
        built = "partial"
    else:
        built = "no"

    # Tested
    cites_test = "test_" in row["b0_reason"] or "tests" in row["why"]
    if eng or row["status"] in ("D", "E", "F", "G") or (built == "yes" and cites_test):
        tested = "yes"
    elif built == "yes" and any(touches_tests(s) for s in shas):
        tested = "yes"
        ev["tested_by"] = "a recorded commit changes brambleloop/tests/"
    elif built in ("yes", "partial"):
        tested = "unverified"
    else:
        tested = "no"

    # Integrated (into the integration ref; COMPLETE rows are in the combined candidate)
    if built == "no":
        integrated = "no"
    else:
        missing = [s for s in shas if not ancestor(s, integ)]
        if cls in ("COMPLETE_ON_BRANCH", "MISSING_INTEGRATION") and not shas:
            br = b0._branch_of(row)
            ok = br != "unknown" and ancestor(f"origin/{br}", integ)
            integrated = "yes" if ok else "no"
            ev["integrated_by"] = f"branch {br} head in {integ}" if ok else None
        elif missing:
            integrated = "no"
            ev["not_in_integrated"] = missing
        else:
            integrated = built
    # Reviewed: independent review is not recorded per row anywhere in the ledger.
    reviewed = "not_recorded"

    # Deployed against the given production SHA
    if integrated not in ("yes", "partial"):
        deployed = "no"
    else:
        fallback = None
        if not basis and not shas and cls in IN_CANDIDATE:
            fallback = b0.CERT_CANDIDATE      # B0: the code is in the combined candidate
            ev["deploy_basis"] = f"{fallback} (B0 class {cls}: in the combined candidate)"
        need = ([basis or fallback] if basis or fallback else []) + shas
        if not need:
            deployed = "not_recorded"
            ev["deployed_why"] = "no deployed tree or commit recorded for this row (not inferred)"
        else:
            out = [s for s in need if not ancestor(s, prod)]
            deployed = "no" if out else integrated
            if out == [fallback]:
                deployed = "not_recorded"     # the candidate is not deployed; which part of
                ev["deployed_why"] = (        # it predates production is not recorded
                    "combined candidate not in production; no row-level commit recorded")
            if out:
                ev["not_in_production"] = out
                if basis and ancestor(basis, prod):
                    ev["earlier_version_deployed"] = basis
    # Production verified: the ledger's acceptance (status G) AND a committed production
    # record of the row (prod_records) AND no code change to the row since that record.
    rec = prod_records.get(rid, [])
    if rec:
        ev["production_records"] = rec
    if row["acceptance_complete"] and deployed == "yes" and rec:
        later = [s for s in shas if basis and not ancestor(s, basis)]
        verified = "pending" if later else "yes"
        if later:
            ev["verification_predates"] = later
    elif deployed in ("yes", "partial"):
        verified = "pending"                  # deployed, not yet production-verified
        if row["acceptance_complete"]:
            ev["verified_why_not"] = ("ledger acceptance rests on tests and the deployed tree; "
                                      "no committed production record of the row")
    else:
        verified = "no"

    # Gate: why acceptance is still open, only for built work.
    root = row.get("board_root")
    if row["acceptance_complete"]:
        gate = "not_gated"
    elif built != "yes":
        # Unbuilt work is gated only where B0 recorded why the code cannot or may not be
        # written yet (quoted requirement text, or an owner decision); never on a board root.
        gate = {"BY_DESIGN": "by_design", "GENUINELY_GATED": "external",
                "OWNER_GATED": "owner"}.get(cls, "not_gated")
        if root in OWNER_ROOTS | DATA_ROOTS | EXTERNAL_ROOTS and gate == "not_gated":
            ev["board_gate_ignored_unbuilt"] = root
    elif cls in ("OWNER_HELD", "OWNER_GATED"):
        gate = "owner"
    elif cls == "GENUINELY_GATED" or root in EXTERNAL_ROOTS:
        gate = "external"
    elif root in DATA_ROOTS:
        gate = "data_customer"
    elif root in OWNER_ROOTS:
        gate = "owner"
    else:
        gate = "not_gated"
    ev["board_root"] = root

    # ---- the six states (a cascade) ----
    defects = [{"defect": d, "role": role} for d, role in DEFECT_ROWS.get(rid, ())]
    six: dict = {}
    if defects:
        six["implementation_complete"] = "defective"
    elif built == "yes" and tested == "yes":
        six["implementation_complete"] = "yes"
    else:
        six["implementation_complete"] = {"yes": "unverified", "partial": "partial"}.get(
            built, "no")
    impl_ok = six["implementation_complete"] == "yes"
    dfx = "defective" if defects else "no"
    six["integration_complete"] = "yes" if impl_ok and integrated == "yes" else dfx
    if six["integration_complete"] == "yes":
        six["production_deployed"] = deployed if deployed in ("yes", "not_recorded") else "no"
    else:
        six["production_deployed"] = dfx
    if six["production_deployed"] == "yes":
        six["production_verified"] = verified if verified in ("yes", "pending") else "pending"
    else:
        six["production_verified"] = dfx
    if defects:
        six["e2e_acceptance"] = "defective"
    elif rid in E2E_RECORDS:
        six["e2e_acceptance"] = "passed"
        ev["e2e_record"] = E2E_RECORDS[rid]
    else:
        six["e2e_acceptance"] = "not_passed"
    six["business_outcome"] = "proven" if rid in BUSINESS_OUTCOME_RECORDS else "no"
    return {"built": built, "tested": tested, "integrated": integrated, "reviewed": reviewed,
            "deployed": deployed, "production_verified": verified, "gate": gate,
            "six": six, "defects": defects, "evidence": ev}


def concerns(row: dict, st: dict, integ8_moved: set) -> list[str]:
    """Why a row's current B0 class looks unsupported by its own evidence (reported only)."""
    rid, cls, out = rid_of(row), row["b0_class"], []
    eng = row["engineering_complete"]
    if cls == "COMPLETE" and not eng and st["tested"] != "yes":
        out.append(f"(a) on a record/ruling with no cited test; ledger status {row['status']}")
    if rid in integ8_moved and row["status"] in "ABC" and st["tested"] != "yes":
        out.append(f"moved into (a) by INTEG8 on commit mentions; ledger status "
                   f"{row['status']} and no recorded commit changes a test")
    if cls in ("AWAITING_EVIDENCE", "PROPOSED_COMPLETE") and row["status"] in "AB":
        out.append(f"{cls} says the code is in place, but the ledger status is "
                   f"{row['status']} ({'not implemented' if row['status'] == 'A' else 'partial'})"
                   f" and no newer commit is recorded" if not st["evidence"]["change_shas"]
                   else f"{cls} with ledger status {row['status']}; commits "
                   f"{', '.join(st['evidence']['change_shas'])} recorded")
    if cls == "OWNER_GATED" and st["built"] != "yes" and "coordinator" in row["b0_reason"]:
        out.append(f"OWNER_GATED on work that is not (fully) built, held by a coordinator "
                   f"call rather than an owner-only action: {row['b0_reason'][:140]}")
    if cls == "COMPLETE" and row["status"] in "FG" and st["integrated"] != "yes":
        out.append("ledger F/G but a recorded commit is not in the integration ref")
    return out


def fm_identity(fm_rows: list) -> dict:
    reg = ROOT / "research/final_build"
    v10 = json.loads((reg / "master_registry.json").read_text())
    v11 = json.loads((reg / "master_registry_v1_1.json").read_text())
    uids = [r.get("uid") or r["id"] for r in v10["requirements"]] + \
           [r.get("uid") or r["id"] for r in v11["requirements"]]
    ids = [r["id"] for r in fm_rows]
    extra = sorted(set(ids) - set(uids))
    missing = sorted(set(uids) - set(ids))
    dups = sorted(k for k, n in Counter(ids).items() if n > 1)
    nums = sorted({int(i[2:5]) for i in uids})
    return {"registry_records": len(uids), "registry_v1_0_records": len(v10["requirements"]),
            "registry_v1_1_records": len(v11["requirements"]), "ledger_rows": len(ids),
            "id_span": f"F-{nums[0]:03d}..F-{nums[-1]:03d}",
            "absent_ids": v10["id_space"]["absent_ids"],
            "version_qualified_pairs": sorted(v10["id_space"]["collisions"]),
            "rows_not_in_registry": extra, "registry_records_not_in_ledger": missing,
            "duplicate_rows": dups,
            "original": len(uids), "additions": len(extra),
            "matches": not extra and not missing and not dups}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--production", default="ee35a493")
    ap.add_argument("--integrated", default="origin/claude/w4-INTEG8-next")
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args(argv)
    prod = resolve(a.production)
    integ = git("rev-parse", "--short=8", a.integrated).stdout.strip()
    if not prod or not integ:
        print("cannot resolve production or integration ref", file=sys.stderr)
        return 1
    prod_records.update(load_prod_records())
    led = json.loads(LEDGER.read_text())
    ledger_deployed = SHA_RE.search(led["sources"]["deployed"]).group(0)
    ident = fm_identity(led["rows"]["final_master"])
    problems = [] if ident["matches"] else [f"Final Master identity: {ident}"]
    sr = led["b0"]["status_report"]
    result = {"kind": "brambleloop.ledger9_states",
              "generated_by": "research/final_build/w4/ledger9_states.py",
              "ledger": "ENGINEERING_LEDGER.json", "production": prod,
              "integrated_ref": f"{a.integrated} {integ}",
              "final_master_identity": ident, "rule": __doc__.split("\n\n")[1].strip(),
              "defects": DEFECTS, "scopes": {}}
    for scope in ("final_master", "build2"):
        rows = led["rows"][scope]
        moved = set(sr[scope]["integ8"]["moved_into_a"])
        per, flags = {}, {}
        for row in rows:
            st = states(row, prod, integ, ledger_deployed)
            st["b0_class"] = row["b0_class"]
            st["ledger_status"] = row["status"]
            per[rid_of(row)] = st
            c = concerns(row, st, moved)
            if c:
                flags[rid_of(row)] = c
        counts = {k: dict(sorted(Counter(s[k] for s in per.values()).items()))
                  for k in ("built", "tested", "integrated", "reviewed", "deployed",
                            "production_verified", "gate")}
        six = {k: dict(sorted(Counter(s["six"][k] for s in per.values()).items()))
               for k in SIX}
        yes_word = {"e2e_acceptance": "passed", "business_outcome": "proven"}
        six_yes = {k: {"count": six[k].get(yes_word.get(k, "yes"), 0),
                       "pct": round(100 * six[k].get(yes_word.get(k, "yes"), 0) / len(rows), 1)}
                   for k in SIX}
        linked = {d: sorted(r for r, s in per.items() if any(x["defect"] == d
                                                               for x in s["defects"]))
                  for d in DEFECTS}
        for k, v in list(counts.items()) + list(six.items()):
            if sum(v.values()) != len(rows):
                problems.append(f"{scope} {k} does not reconcile: {v}")

        def furthest(s):
            if s["built"] == "n/a":
                return "not_applicable"
            for k in ("production_verified", "deployed", "integrated", "tested", "built"):
                if s[k] == "yes":
                    return k
            return "built_partial" if s["built"] == "partial" else "not_built"
        prog = Counter(furthest(s) for s in per.values())
        result["scopes"][scope] = {"total": len(rows), "six_states": six,
                                   "six_states_yes": six_yes, "defect_rows": linked,
                                   "counts": counts,
                                   "furthest_state": dict(prog),
                                   "class_unsupported": flags, "rows": per}
    a_out = Path(a.out)
    a_out.write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n")
    for p in problems:
        print("PROBLEM:", p)
    for scope, r in result["scopes"].items():
        print(scope, r["total"], json.dumps(r["six_states_yes"]))
        print("  six:", json.dumps(r["six_states"]))
        print("  facts:", json.dumps(r["counts"]))
        print("  defects:", json.dumps(r["defect_rows"]),
              "unsupported:", len(r["class_unsupported"]))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
