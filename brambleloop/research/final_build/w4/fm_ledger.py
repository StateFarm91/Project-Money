"""Wave-4 Final Master ledger: every F-row (v1.0 F-001..F-879 + v1.1 F-880..F-930) classified.

Inputs (all in-repo, regenerated or read on the current head):
  * closure_matrix.json        -- aggregate.py's adjudicated v1.0 matrix (after the w4 fold)
  * module_reachability.json   -- regenerated on the head (build2.reachability)
  * w3/CLOSURE_f0c2d12.json    -- lane K's triage + v1.1 status (older audit)
  * w3/handoff_*.md            -- what wave-3 lanes claim (claims.py; claims, never certification)
  * v11_mapping.json (w4)      -- the v1.1 rows' mapping, adjudicated by the same cap() rules

Ledger status (WAVE4_BRIEF): PROVEN / OWNER-GATED / DATA-GATED / EXTERNAL-GATED /
NOT-APPLICABLE / OPEN-DEFECT. PROVEN means the canonical adjudicator computes COMPLETE (a test
that exists, a producer module reached from a live root, a named consumer, coverage FULL, no
defect) -- never a lane's word. Post-launch rows (D-FB-5 / F-400 / F-879) are classified on the
same rules and flagged `launch_blocking: false`; their OPEN-DEFECTs are real unfinished work
that does not block launch.

Run: python3 research/final_build/w4/fm_ledger.py   (writes FM_LEDGER.json/.md, FM_OPEN_CLUSTERS.json)
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
FB = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(FB))
import claims as claims_mod  # noqa: E402

GATE_STATUS = {"owner": "OWNER-GATED", "data": "DATA-GATED", "external": "EXTERNAL-GATED"}

# Cluster ownership for still-OPEN rows: wave-3 audit cluster -> (wave-4 lane, file area).
LANE_OF = {
    "K1": "SEO", "K2": "STORE", "K3": "LEARN", "K4": "CC", "K5a": "FM", "K5b": "FM",
    "K6": "PIPE", "K7": "OWNER", "K8": "STORE", "K9": "PIPE", "K10": "LEARN", "K11": "AUTO",
    "K12": "VISUAL", "K13": "FM", "K14": "FM", "K15": "FM", "K16": "STORE",
    "PROCESS": "integrator", "REMAP": "FM", "STRUCTURAL": "FM",
}


def _ledger_status(completion, gate, launch_class):
    if launch_class == "NA":
        return "NOT-APPLICABLE"
    if completion == "COMPLETE":
        return "PROVEN"
    if completion == "GATED":
        return GATE_STATUS[gate["kind"]]
    return "OPEN-DEFECT"


def _row_completion_any_class(row):
    """completion() for a post-launch row as if it were launch-critical (same rules)."""
    import aggregate
    r = dict(row, launch_class="LAUNCH-CRITICAL")
    return aggregate.completion(r)


def build():
    matrix = json.loads((FB / "closure_matrix.json").read_text())
    reach = json.loads((FB / "module_reachability.json").read_text())
    w3 = json.loads((FB / "w3" / "CLOSURE_f0c2d12.json").read_text())
    triage = {r["uid"]: r for r in w3["launch_critical"]}
    cluster_of = {u: k for k, c in w3["summary"]["clusters"].items() for u in c["ids"]}
    cl = claims_mod.parse()
    rows = []
    for r in matrix["matrix"]:
        uid = r["uid"]
        if r["launch_class"] == "LAUNCH-CRITICAL":
            comp, reasons = r["completion"], r["completion_reasons"]
        elif r["launch_class"] == "MATURE":
            comp, reasons = _row_completion_any_class(r)
        else:
            comp, reasons = "NOT-APPLICABLE", []
        gate = r.get("gate") or {}
        status = _ledger_status(comp, gate, r["launch_class"])
        t = triage.get(uid) or {}
        rows.append({
            "uid": uid, "version": "v1.0", "title": r["title"][:90],
            "launch_class": r["launch_class"], "launch_blocking": r["launch_class"] == "LAUNCH-CRITICAL",
            "status": status, "maturity": r["maturity"], "maturity_claimed": r["maturity_claimed"],
            "coverage": r.get("coverage"), "producer": r.get("producer"),
            "consumer": r.get("consumer"), "tests": r.get("tests") or [],
            "gate": ({"kind": gate.get("kind"), "key": gate.get("key")}
                     if status.endswith("GATED") else None),
            "reasons": reasons, "next_action": r.get("next_action"),
            "mapped_on": r["mapped_on"][:7],
            "w3_triage": t.get("triage"), "w3_cluster": cluster_of.get(uid) or t.get("cluster"),
            "claims": [{"lane": c["lane"], "status": c["status"]} for c in cl.get(uid, [])],
        })
    v11 = _v11_rows(w3, cl)
    rows += v11
    return rows, reach, cluster_of


def _v11_rows(w3, cl):
    """v1.1 rows adjudicated through the same cap()/completion() rules (w4/v11_mapping.json)."""
    import aggregate
    reach = json.loads((FB / "module_reachability.json").read_text())["modules"]
    mp = HERE / "v11_mapping.json"
    mapping = {r["uid"]: r for r in json.loads(mp.read_text())} if mp.exists() else {}
    out = []
    for r in w3["v1_1"]:
        uid = r["id"]
        m = mapping.get(uid)
        if m is None:
            status, mat, reasons, gate = "OPEN-DEFECT", "MISSING", ["v1.1 row not mapped"], None
            prod = cons = None
            tests = []
            nxt = None
        else:
            m = dict(m)
            claimed = m["maturity"]
            m["maturity"], notes = aggregate.cap(m, reach)
            comp, reasons = aggregate.completion(m)
            reasons = notes + reasons
            g = m.get("gate") or {}
            status = _ledger_status(comp, g, m["launch_class"])
            gate = {"kind": g.get("kind"), "key": g.get("key")} if status.endswith("GATED") else None
            mat, prod, cons, tests, nxt = (m["maturity"], m.get("producer"), m.get("consumer"),
                                           m.get("tests") or [], m.get("next_action"))
        out.append({
            "uid": uid, "version": "v1.1", "title": r["title"][:90],
            "launch_class": (m or {}).get("launch_class", "LAUNCH-CRITICAL"),
            "launch_blocking": (m or {}).get("launch_class", "LAUNCH-CRITICAL") == "LAUNCH-CRITICAL",
            "status": status, "maturity": mat, "producer": prod, "consumer": cons,
            "tests": tests, "gate": gate, "reasons": reasons, "next_action": nxt,
            "w3_status": r["w3"], "w3_cluster": next((k for k, c in w3["summary"]["clusters"].items()
                                                      if uid in c["ids"]), None),
            "claims": [{"lane": c["lane"], "status": c["status"]} for c in cl.get(uid, [])],
        })
    return out


def clusters(rows):
    """OPEN-DEFECT launch-critical rows grouped by owning cluster, with the files they touch."""
    w3 = json.loads((FB / "w3" / "CLOSURE_f0c2d12.json").read_text())["summary"]["clusters"]
    groups = defaultdict(list)
    for r in rows:
        if r["status"] != "OPEN-DEFECT" or not r["launch_blocking"]:
            continue
        claimed = any(c["status"] == "COMPLETE" for c in r["claims"])
        if claimed:
            key = "FOLD"
        elif r.get("w3_triage") == "R":
            key = "FOLD-R"
        elif r.get("w3_triage") == "G":
            key = "REGATE"
        elif r["version"] == "v1.1" and r.get("w3_cluster") is None:
            key = "V11-MAP"
        else:
            key = r.get("w3_cluster") or "UNCLUSTERED"
        groups[key].append(r)
    out = {}
    for k, rs in sorted(groups.items()):
        meta = w3.get(k, {})
        out[k] = {
            "title": meta.get("title") or {
                "FOLD": "Wave-3 claims COMPLETE, canonical mapping not re-mapped: verify tests + "
                        "reachability, fold into mapping/remap_<head>",
                "FOLD-R": "Wave-3 audit (lane K) re-checked as resolved on f0c2d12; never re-mapped "
                          "into the canonical mapping",
                "REGATE": "Wave-3 audit found an owner/data/external gate the canonical mapping "
                          "does not record (gate key missing)",
                "V11-MAP": "v1.1 rows (F-880..F-930) absent from the canonical matrix and the "
                           "runtime snapshot: requirement rows lost from the launch gate",
                "UNCLUSTERED": "Launch-critical OPEN rows not in any wave-3 cluster"}.get(k, k),
            "rows": sorted(r["uid"] for r in rs), "size": len(rs),
            "files": meta.get("files") or ("research/final_build/mapping/*, aggregate.py, "
                                           "build2/final_master_closure.json (FM-owned)"),
            "owner_lane": LANE_OF.get(k, "FM"),
            "reasons": dict(Counter(x.split(":")[0].split(" below")[0]
                                    for r in rs for x in r["reasons"])),
        }
    return out


def main():
    rows, reach, _ = build()
    lc = [r for r in rows if r["launch_blocking"]]
    summary = {
        "rows": len(rows),
        "by_version": dict(Counter(r["version"] for r in rows)),
        "status_all": dict(Counter(r["status"] for r in rows)),
        "status_launch_critical": dict(Counter(r["status"] for r in lc)),
        "status_post_launch": dict(Counter(r["status"] for r in rows
                                           if r["launch_class"] == "MATURE")),
        "launch_critical_open": sum(1 for r in lc if r["status"] == "OPEN-DEFECT"),
        "reachability_basis": reach.get("basis"),
        "unreached_modules": sorted(k for k, v in reach["modules"].items()
                                    if not v["reached"] and not k.endswith("__init__.py")),
    }
    out = {"generated_by": "research/final_build/w4/fm_ledger.py",
           "rule": __doc__.split("Ledger status")[1].split("Run:")[0].strip(),
           "summary": summary, "rows": rows}
    (HERE / "FM_LEDGER.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    cls = clusters(rows)
    (HERE / "FM_OPEN_CLUSTERS.json").write_text(json.dumps(
        {"generated_by": "research/final_build/w4/fm_ledger.py",
         "rule": "launch-critical OPEN-DEFECT rows only; clusters are file-disjoint by wave-3 "
                 "cluster file lists; FOLD = rows a wave-3 lane claims COMPLETE that the "
                 "canonical mapping has not re-mapped (owned by FM)",
         "clusters": cls}, indent=1) + "\n")
    _md(out, cls)
    print(json.dumps(summary, indent=1)[:3000])


def _md(out, cls):
    s = out["summary"]
    L = ["# Final Master ledger (wave 4, lane FM)", "",
         "Generated by `research/final_build/w4/fm_ledger.py`; machine-readable: `FM_LEDGER.json`,",
         "`FM_OPEN_CLUSTERS.json`. PROVEN = the canonical adjudicator (`aggregate.cap/completion`)",
         "computes COMPLETE on the current reachability; a lane's claim never counts.", "",
         f"Reachability: {s['reachability_basis']}", "",
         "## Counts", "", "| | " + " | ".join(sorted(s["status_all"])) + " |",
         "|---|" + "---|" * len(s["status_all"])]
    for name, key in (("all rows", "status_all"), ("launch-critical", "status_launch_critical"),
                      ("post-launch (not blocking)", "status_post_launch")):
        L.append(f"| {name} | " + " | ".join(str(s[key].get(k, 0)) for k in sorted(s["status_all"])) + " |")
    L += ["", f"Launch-critical OPEN-DEFECT: **{s['launch_critical_open']}**", "",
          "## Open clusters (launch-critical)", "", "| Cluster | Lane | Rows | Title |", "|---|---|---|---|"]
    for k, c in cls.items():
        L.append(f"| {k} | {c['owner_lane']} | {c['size']} | {c['title'][:80]} |")
    L += ["", "## Launch-critical rows not PROVEN", "", "| Row | Status | Maturity | Why / next |", "|---|---|---|---|"]
    for r in out["rows"]:
        if r["launch_blocking"] and r["status"] != "PROVEN":
            why = (r["gate"] and f"{r['gate']['kind']}:{r['gate']['key']}") or "; ".join(r["reasons"])[:140]
            L.append(f"| {r['uid']} {r['title'][:40]} | {r['status']} | {r['maturity']} | {why.replace('|', '/')} |")
    L += ["", "## Modules with no runtime caller (regenerated reachability)", "",
          ", ".join(f"`{m}`" for m in s["unreached_modules"]), ""]
    (HERE / "FM_LEDGER.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
