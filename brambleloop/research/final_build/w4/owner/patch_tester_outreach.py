"""W-PHYSFIX (SECREVIEW 3e542a1 R13): bring the committed owner packets to the kit's one figure.

`build_owner_docs.py` regenerates the whole owner packet from vendored production readings and
other lanes' snapshots, which would also rewrite items that belong to other lanes. This script
changes only the `tester_outreach` decision and its `physical_proof` clearance detail. It reads
both from the code that now owns them: `ops.owner_queue.DECISIONS`, and
`GATE_CLEARANCE_BUSINESS.json`, which `gate_clearance_business.py` rebuilds from
`quality.tester_kit`. It then re-totals that decision's batch. It writes:
  research/final_build/w4/OWNER_ACTIONS.{json,md}
  src/brambleloop/app/command_center/snapshots/OWNER_ACTIONS.json

Run:  cd brambleloop && PYTHONPATH=src python3 research/final_build/w4/owner/patch_tester_outreach.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
W4 = HERE.parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.ops import owner_queue  # noqa: E402

TARGETS = (W4 / "OWNER_ACTIONS.json",
           ROOT / "src/brambleloop/app/command_center/snapshots/OWNER_ACTIONS.json")


def _display(v: float) -> str:
    return f"CA${v:,.2f}"


def patch(doc: dict) -> tuple[dict, float, float]:
    card = next(d for d in owner_queue.DECISIONS if d["id"] == "tester_outreach")
    gcb = json.loads((W4 / "GATE_CLEARANCE_BUSINESS.json").read_text())
    proof = next(g for g in gcb["gates"] if g.get("gate") == "physical_proof")
    for batch in doc["batches"]:
        for item in batch["items"]:
            if item.get("id") != "tester_outreach":
                continue
            old = float(item.get("max_cost_cad") or 0.0)
            new = float(card["max_cost_cad"])
            item.update(decision=card["decision"], max_cost_cad=new,
                        max_cost_display=_display(new), max_cost_basis=card["cost_basis"])
            for c in item.get("clearance") or []:
                if c.get("detail", {}).get("gate") == "physical_proof":
                    c["detail"] = proof
            total = round(float(batch["max_cost_cad_total"]) - old + new, 2)
            batch["max_cost_cad_total"] = total
            batch["max_cost_display"] = _display(total)
            return doc, old, new
    raise SystemExit("no tester_outreach decision in the packet")


def main() -> None:
    old = new = 0.0
    for path in TARGETS:
        doc, old, new = patch(json.loads(path.read_text()))
        path.write_text(json.dumps(doc, indent=1, default=str) + "\n")
    md = W4 / "OWNER_ACTIONS.md"
    text = md.read_text()
    doc = json.loads(TARGETS[0].read_text())
    card = next(i for b in doc["batches"] for i in b["items"] if i["id"] == "tester_outreach")
    batch = next(b for b in doc["batches"] if any(i["id"] == "tester_outreach"
                                                  for i in b["items"]))
    lines = text.split("\n")
    for n, line in enumerate(lines):
        if line.startswith("| tester_outreach |"):
            cells = line.split(" | ")
            cells[1] = card["decision"]
            cells[4] = card["max_cost_display"]
            lines[n] = " | ".join(cells)
        if line.startswith(f"## {batch['title']} ("):
            lines[n] = re.sub(r"max CA\$[\d,]+\.\d\d", f"max {batch['max_cost_display']}", line)
    md.write_text("\n".join(lines))
    print(f"tester_outreach CA${old:.2f} -> CA${new:.2f}; batch {batch['max_cost_display']}")


if __name__ == "__main__":
    main()
