"""W4-PIPE: run the product pipeline board in shadow and write PIPELINE_BACKLOG.json/.md.

    PYTHONPATH=src python research/final_build/w4/pipeline_run.py --chain-db /scratch/run.sqlite

Renders go to a scratch ArtifactStore (BRAMBLELOOP_ARTIFACT_DIR). The board is recorded as one
`pipeline.board` audit row in the scratch DB, never in production. No network, no spend.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent


def md(res: dict) -> str:
    L = ["# Product pipeline backlog (W4-PIPE)", "",
         f"Generated {res['generated_at']} at `{res['head']}` by "
         "`research/final_build/w4/pipeline_run.py` (shadow, scratch DB + scratch artefact "
         "store). Stages: " + " → ".join(res["stages"]) + ". Publication is never advanced "
         "(`advances_publication` = False).", "",
         "## Candidates at each stage (current stage = first stage not PASS)", "",
         "| stage | at stage | passed |", "|---|---|---|"]
    for s in res["stages"]:
        L.append(f"| {s} | {res['at_stage'][s]} | {res['passed_stage'][s]} |")
    L += ["", f"Competitor findings as of {res.get('findings_as_of')} (intel.findings; demand and "
          "merchandising intelligence only).", "", "## Bundle families (mjs.findings bundle_premium)", "",
          "| family | members | cleared Product Truth | ready to price |", "|---|---|---|---|"]
    for fam, b in (res.get("bundle_families") or {}).items():
        L.append(f"| {fam} | {', '.join(b['members'])} | {', '.join(b['product_truth_passed'])} | "
                 f"{b['bundle_ready_for_pricing']} |")
    L += ["", "## Backlog", "", "| candidate | source | stage | status | next step | clearer |",
          "|---|---|---|---|---|---|"]
    order = {s: i for i, s in enumerate(res["stages"])}
    for r in sorted(res["candidates"], key=lambda r: (-order[r["stage"]], r["slug"])):
        L.append(f"| {r['slug']} | {r['source']} | {r['stage']} | {r['stage_status']} | "
                 f"{(r['next_step'] or '')[:160].replace('|', '/')} | {r['clearer']} |")
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chain-db")
    ap.add_argument("--no-visual", action="store_true")
    ap.add_argument("--only", help="comma-separated slugs: refresh just these rows and splice "
                                   "them into the existing backlog (other rows kept as they are)")
    a = ap.parse_args()
    only = set(a.only.split(",")) if a.only else None
    from brambleloop.core.artifacts import ArtifactStore
    from brambleloop.products import pipeline_board as pb

    today = date(2026, 10, 7)
    # The stored competitor findings (W4-MJS, intel.findings): the same payload the handler
    # reads from the `mjs.findings` OperatingReading in a database that ran mjs.scan.
    findings = json.loads((HERE / "MJS_FINDINGS.json").read_text())
    res = pb.board(today=today, store=ArtifactStore(), visual=not a.no_visual,
                   findings=findings, only=only)
    if a.chain_db:
        from brambleloop.core.db import Database

        db = Database(f"sqlite:///{a.chain_db}")
        pb.merge_chain(res, db, today=today)
        # recount after the chain verdicts landed
        res["at_stage"] = {s: 0 for s in pb.STAGES}
        res["passed_stage"] = {s: 0 for s in pb.STAGES}
        for r in res["candidates"]:
            cur = next((s for s in pb.STAGES
                        if r["stages"].get(s, {}).get("status") != pb.PASS), pb.STAGES[-1])
            r["stage"] = cur
            st = r["stages"].get(cur, {})
            r["stage_status"] = st.get("status", pb.NOT_RUN)
            r["next_step"] = st.get("next_step", "")
            r["clearer"] = st.get("clearer", "")
            res["at_stage"][cur] += 1
            for s in pb.STAGES:
                if r["stages"].get(s, {}).get("status") == pb.PASS:
                    res["passed_stage"][s] += 1
        pb.record(db, res)
    if only is not None:
        # Splice: replace only these rows in the backlog on file and recount its totals.
        full = json.loads((HERE / "PIPELINE_BACKLOG.json").read_text())
        mine = {r["slug"]: r for r in res["candidates"]}
        full["candidates"] = [mine.pop(r["slug"], r) for r in full["candidates"]] + list(
            mine.values())
        full["at_stage"] = {s: 0 for s in pb.STAGES}
        full["passed_stage"] = {s: 0 for s in pb.STAGES}
        for r in full["candidates"]:
            full["at_stage"][r["stage"]] += 1
            for s in pb.STAGES:
                if r["stages"].get(s, {}).get("status") == pb.PASS:
                    full["passed_stage"][s] += 1
        full["pipe_rows_refreshed"] = {"slugs": sorted(only), "chain_db": bool(a.chain_db),
                                       "at": datetime.now(timezone.utc).isoformat(
                                           timespec="seconds")}
        res = full
    res["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    res["head"] = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True,
                                 text=True).stdout.strip()
    (HERE / "PIPELINE_BACKLOG.json").write_text(json.dumps(res, indent=1, default=str) + "\n")
    (HERE / "PIPELINE_BACKLOG.md").write_text(md(res))
    print(json.dumps(res["at_stage"]), json.dumps(res["passed_stage"]))


if __name__ == "__main__":
    main()
