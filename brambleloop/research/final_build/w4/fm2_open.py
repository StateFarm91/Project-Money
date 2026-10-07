"""Lane W4-FM2: the exact launch-critical OPEN list on this head, with the owning lane.

Reads closure_matrix.json (canonical adjudication) and FM_OPEN_CLUSTERS.json (cluster of each
row). Writes w4/FM2_OPEN.json. Run from brambleloop/: python3 research/final_build/w4/fm2_open.py
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
FB = HERE.parent

# Rows owned outside lane FM2 (coordinator assignment 2026-10-07).
ELSEWHERE = {"K5a": "SPEND", "K5b": "SPEND", "K9": "K9"}
ROW_ELSEWHERE = {"F-030": "VISUAL (gallery frames)", "F-254": "VISUAL (gallery frames)",
                 "F-914": "CC (wiring: /api/cc/money period)",
                 "F-416": "integrator (Dockerfile digest pinning)"}
END_STAGE = "PROCESS"


def main():
    m = json.loads((FB / "closure_matrix.json").read_text())
    scope = {e["uid"]: e for e in json.loads((FB / "LAUNCH_SCOPE.json").read_text())["entries"]}
    clusters = json.loads((HERE / "FM_OPEN_CLUSTERS.json").read_text())["clusters"]
    cl = {u: k for k, v in clusters.items() for u in v["rows"]}
    rows = {}
    for r in m["matrix"]:
        if r["launch_class"] != "LAUNCH-CRITICAL" or r["completion"] != "OPEN":
            continue
        assert scope[r["uid"]]["scope"] == "launch-critical"
        c = cl.get(r["uid"], "UNCLUSTERED")
        if r["uid"] in ROW_ELSEWHERE:
            owner = ROW_ELSEWHERE[r["uid"]]
        elif c in ELSEWHERE:
            owner = ELSEWHERE[c]
        elif c == END_STAGE:
            owner = "END-STAGE (integrator: frozen RC + full suite + independent re-audit)"
        else:
            owner = "FM2"
        rows[r["uid"]] = {"title": r["title"], "cluster": c, "producer": r.get("producer"),
                          "why_open": r.get("completion_reasons") or [],
                          "owning_lane": owner}
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True,
                          text=True).stdout.strip()
    out = {"generated_by": "research/final_build/w4/fm2_open.py", "head": head,
           "launch_critical_open": len(rows),
           "fm2_owned": sorted(u for u, r in rows.items() if r["owning_lane"] == "FM2"),
           "rows": rows}
    (HERE / "FM2_OPEN.json").write_text(json.dumps(out, indent=1) + "\n")
    print(len(rows), "open;", len(out["fm2_owned"]), "FM2:", out["fm2_owned"])


if __name__ == "__main__":
    main()
