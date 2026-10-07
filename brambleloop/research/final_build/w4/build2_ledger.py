"""Write research/final_build/w4/BUILD2_LEDGER.json (+ .md) from build2.closure.ledger.

Usage: PYTHONPATH=src python research/final_build/w4/build2_ledger.py [prod_api_build.json]
The optional argument is a read-only GET of production `/api/build`; its `gates` block supplies
live gate readings for the gates production knows. Gates it does not know stay `unchecked`.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from brambleloop.build2 import closure

HERE = Path(__file__).resolve().parent


def main(argv: list[str]) -> None:
    gate_open, source = None, ""
    if len(argv) > 1:
        prod = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
        gate_open = {k: bool(v.get("open")) for k, v in prod.get("gates", {}).items()}
        source = (f"production GET /api/build (read-only), deployed commit "
                  f"{prod.get('_commit', 'fcb982d')}, read {prod.get('_read_at', '2026-10-07')}")
    led = closure.ledger(gate_open=gate_open, gate_source=source)
    (HERE / "BUILD2_LEDGER.json").write_text(json.dumps(led, indent=1, default=str) + "\n",
                                            encoding="utf-8")
    c = led["counts"]
    lines = ["# Build 2 ledger (W4-B2)", "",
             f"Generated {led['as_of']} by `research/final_build/w4/build2_ledger.py` from "
             "`build2.closure.ledger` (evidence-computed; registry status is the claim under test).",
             f"Gate readings: {led['gate_source'] or 'none (registry parking only)'}.", "",
             "## Reconciliation of the owner dashboard figure", "",
             "The dashboard's `Build 2: 227/320 complete (70.9%), executable remaining 45, "
             "owner-gated 28, data-gated 20` is `build2.requirements.coverage()` served by "
             "production `/api/build2` at deployed commit fcb982d (read-only GET 2026-10-07: "
             "`evidence_B2/prod_build2_coverage_fcb982d.json`). That registry dates from "
             "2026-09-22 (af3a12f/53227fa). It is stale -- the 2026-09-27/28 certification "
             "reopened and re-parked rows, giving covered 218 / partial 85 / owner 9 / data 8 on "
             "the integrated branch -- and miscounted in meaning: `executable_remaining` = "
             "partial + missing, so partial rows parked on owner/data/external gates read as "
             "executable work, and `complete` is the registry's claim, not proof. The figures "
             "below are `closure.dashboard()` / `closure.ledger()`: evidence-computed, gated rows "
             "by the kind of their gate, OPEN the only executable remainder.", "",
             "| state | rows |", "|---|---|"]
    lines += [f"| {s} | {c[s]} |" for s in closure.LEDGER_STATES]
    lines += ["", "## Gated rows by exact gate", "", "| gate | kind | state | rows |", "|---|---|---|---|"]
    by_gate: dict[str, list] = {}
    for r in led["rows"]:
        if "gate" in r:
            by_gate.setdefault(r["gate"]["key"], []).append(r)
    for k, rs in sorted(by_gate.items()):
        lines.append(f"| {k} | {rs[0]['gate']['kind']} | {rs[0]['gate']['state']} | "
                     + " ".join(f"#{r['id']}" for r in rs) + " |")
    na = [r for r in led["rows"] if r["state"] == "NOT-APPLICABLE"]
    lines += ["", "NOT-APPLICABLE (process directives to the auditor, followed): "
              + ", ".join(f"#{r['id']}" for r in na)]
    od = [r for r in led["rows"] if r["state"] == "OPEN-DEFECT"]
    lines += ["", f"OPEN-DEFECT: {len(od)}" + ("" if not od else " -- " + ", ".join(
        f"#{r['id']} {r['why'][:80]}" for r in od))]
    (HERE / "BUILD2_LEDGER.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(c))


if __name__ == "__main__":
    main(sys.argv)
