#!/usr/bin/env python3
"""F-834 (W4-FMEND): emit runtime evidence packets for launch-critical rows from a recorded run.

`build2/final_proof.py` audits one packet per matrix row: run identity, a receipt per chain
stage (producer -> durable_state -> consumer -> decision -> effect -> result) bound by digest to
an artifact from the same run on the same head, a live root, the suite, and an independent
review. Until now no packet had ever been emitted, so every row was BLOCKED on "missing run
identity". This tool emits packets from the one recorded runtime run that exists on a
candidate -- a `scripts/shadow_rehearsal.py` evidence file -- and claims ONLY what that file
records:

* a row gets a packet only when its `producer` names (as `module.py::function`) the handler
  registered in the candidate's code for a job type the rehearsal ran inside the runtime
  (status `done`, or for `store.publish` the expected SHADOW refusal);
* the packet carries the `producer` receipt and the `live_root` receipt for that job and
  nothing else. The rehearsal records job outcomes, not the row's durable state, consumer,
  decision, effect or result, so those receipts are absent and listed in `not_observed`;
* `suite` is included only from a suite record for the same head (`--suite-record`), and
  no `independent_review` is ever written here: the emitter is the implementer, and
  final_proof refuses self-review.

So every packet this emits is expected to stay BLOCKED until a reviewer and a fuller run add
what is missing. It never edits the matrix and never marks anything COMPLETE.

    PYTHONPATH=src python scripts/emit_runtime_packets.py --matrix M --rehearsal R \
        --artifacts ROOT --out PACKETS.json [--suite-record S]

`--artifacts` is the root that final_proof resolves artifact paths against (`--artifacts` there).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Appended, so a PYTHONPATH naming the candidate's src/ wins (handlers are read from it).
sys.path.append(str(ROOT / "src"))

IMPLEMENTER = "w4-FMEND scripts/emit_runtime_packets.py"
STAGES = ("producer", "durable_state", "consumer", "decision", "effect", "result")
# Rehearsal step -> (job types it ran, the outcomes that mean the producer really ran,
# whether it ran inside the production start command's process).
STEP_JOBS = {
    "cir.compile": (("cir.compile",), {"PASS"}, True),
    "gate.certify": (("gate.certify",), {"PASS"}, True),
    "assets.build": (("assets.build",), {"PASS"}, True),
    "listing.seo": (("listing.seo",), {"PASS"}, True),
    "store.publish[shadow]": (("store.publish",), {"REFUSED_AS_EXPECTED"}, True),
    "support.case": (("support.triage", "support.reply"), {"PASS"}, False),
    "ledger": (("finance.reconcile",), {"PASS"}, False),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def handler_refs(job_types) -> dict[str, str]:
    """job type -> `module/path.py::function` of the handler the candidate registers."""
    from brambleloop.runtime import orders, pipeline, release  # noqa: F401 - registers
    from brambleloop.runtime.worker import handlers

    out = {}
    for jt in job_types:
        fn = handlers._handlers.get(jt)
        if fn is None:
            continue
        mod = fn.__module__.split("brambleloop.", 1)[-1].replace(".", "/") + ".py"
        out[jt] = f"{mod}::{fn.__qualname__}"
    return out


def observed_jobs(rehearsal: dict) -> dict[str, dict]:
    """job type -> what the rehearsal recorded for it (only producer-ran outcomes)."""
    out = {}
    for step in rehearsal.get("steps") or []:
        spec = STEP_JOBS.get(step.get("step"))
        if not spec or step.get("outcome") not in spec[1]:
            continue
        job_types, _ok, in_server = spec
        obs = step.get("observed") if isinstance(step.get("observed"), dict) else {}
        for jt in job_types:
            out[jt] = {"step": step["step"], "outcome": step["outcome"], "in_server": in_server,
                       "job": obs.get("job") or obs.get("triage_job") or obs.get("reconcile_job")}
    return out


def emit(rows, rehearsal: dict, rehearsal_rel: str, rehearsal_sha: str, refs: dict,
         suite: dict | None = None, suite_rel: str | None = None,
         suite_sha: str | None = None) -> list[dict]:
    head = rehearsal["head"]
    run_id = f"shadow_rehearsal:{rehearsal.get('head_short') or head[:7]}:{rehearsal['started_at']}"
    if rehearsal.get("tree_dirty") is not False:
        raise ValueError("rehearsal ran on a dirty tree; it is not evidence for the head")
    seen = observed_jobs(rehearsal)
    packets = []
    for row in rows:
        if row.get("launch_class") != "LAUNCH-CRITICAL":
            continue
        producer = row.get("producer") or ""
        hit = next((jt for jt, ref in refs.items() if jt in seen and ref in producer), None)
        if hit is None:
            continue
        o = seen[hit]
        receipt = {"artifact": "rehearsal", "head": head, "run_id": run_id, "observed": True}
        packet = {
            "uid": row["uid"], "head": head, "evidence_class": "runtime", "direct": True,
            "run_id": run_id, "implementer": IMPLEMENTER,
            "artifacts": {"rehearsal": {"path": rehearsal_rel, "sha256": rehearsal_sha}},
            "chain": {"producer": dict(receipt, identity=producer, job_type=hit,
                                       handler=refs[hit], job=o["job"],
                                       rehearsal_step=o["step"], outcome=o["outcome"])},
            "live_root": dict(receipt, kind="worker", producer=producer,
                              process=("the production start command's embedded worker "
                                       "(uvicorn brambleloop.app.main:app)" if o["in_server"]
                                       else "an in-process runtime Worker in the rehearsal")),
            "not_observed": {s: "the rehearsal records job outcomes, not this row's " + s
                             for s in STAGES[1:]},
            "missing_by_design": ["independent_review: the emitter is the implementer"],
        }
        if suite is not None:
            packet["artifacts"]["suite"] = {"path": suite_rel, "sha256": suite_sha}
            packet["suite"] = {"artifact": "suite", "head": suite.get("git_sha"),
                               "run_id": suite.get("run_id"), "observed": True,
                               "passed": suite.get("tests_passing"),
                               "failed": len(suite.get("failing_suites") or []),
                               "clean": suite.get("tree") == "clean"
                               and suite.get("dirty_paths") == 0}
        else:
            packet["missing_by_design"].append(
                "suite: no full-suite record for this head was given")
        packets.append(packet)
    return packets


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--matrix", required=True)
    ap.add_argument("--rehearsal", required=True)
    ap.add_argument("--artifacts", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--suite-record", default=None)
    args = ap.parse_args(argv)
    root = Path(args.artifacts).resolve()
    reh_path = Path(args.rehearsal).resolve()
    matrix = json.loads(Path(args.matrix).read_text(encoding="utf-8"))
    rows = matrix if isinstance(matrix, list) else matrix["matrix"]
    rehearsal = json.loads(reh_path.read_text(encoding="utf-8"))
    suite = suite_rel = suite_sha = None
    if args.suite_record:
        sp = Path(args.suite_record).resolve()
        suite, suite_rel, suite_sha = (json.loads(sp.read_text(encoding="utf-8")),
                                       str(sp.relative_to(root)), _sha256(sp))
    refs = handler_refs({jt for spec in STEP_JOBS.values() for jt in spec[0]})
    packets = emit(rows, rehearsal, str(reh_path.relative_to(root)), _sha256(reh_path), refs,
                   suite, suite_rel, suite_sha)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(packets, indent=1) + "\n", encoding="utf-8")
    print(f"{len(packets)} packet(s) for {sorted(p['uid'] for p in packets)} -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
