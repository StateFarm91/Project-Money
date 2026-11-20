#!/usr/bin/env python3
"""F-716 Collaboration Workspace -- one view of an important multi-agent/model build lane.

The requirement: "Brambleloop Studio exposes proposer, implementer, reviewer, disagreement,
evidence, tests, cost, accepted/rejected approach and final integration result for important
multi-agent/model work."

Each of those already has a durable record of its own; nothing joined them, so answering "who
proposed this, who reviewed it, what did it cost, and did it land?" meant reading five files by
hand. `build(lane)` joins, for one lane, read-only:

  proposer, accepted/rejected approach, disagreement, evidence
                            ops/disagreement.py records for the lane (F-715)
  implementer, reviewer     ops/review.py records (F-714/F-866)
  tests                     the lane's handoff (ops/handoff.py, F-862) and merge-queue entry
  cost                      ops/session_log.py records for the lane (F-868), CA$ or UNMEASURED
  integration result        ops/integrate.py merge-queue `done` entry and the lane registry
                            record (ops/registry.py), integrated commit or NOT_INTEGRATED

Every element is PRESENT with its source or MISSING; nothing is inferred to fill a gap.

  python3 ops/workspace.py LANE [--md]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

ELEMENTS = ("proposer", "implementer", "reviewer", "disagreement", "evidence", "tests",
            "cost", "approach", "integration")
UNMEASURED = "UNMEASURED"


def _present(value, source):
    return {"state": "PRESENT", "source": source, "value": value}


def _missing(why):
    return {"state": "MISSING", "why": why}


def build(lane: str, *, registry_data: dict | None = None,
          queue_data: dict | None = None) -> dict:
    import disagreement
    import handoff
    import integrate
    import review
    import session_log

    dis = disagreement.for_lane(lane)
    revs = [r for r in review._read() if r.get("lane") == lane]
    # Outcome records carry a model; checkpoints do not and are not sessions' cost.
    sess = [r for r in session_log._read() if r.get("lane") == lane and r.get("model")]
    ho = handoff.resume(lane=lane)
    q = queue_data if queue_data is not None else integrate._load()
    done = [e for e in q.get("done", []) if e.get("lane") == lane]
    queued = [e for e in q.get("queue", []) if e.get("lane") == lane]
    if registry_data is None:
        try:
            import registry
            registry_data = registry.Registry().load()
        except Exception:                                              # noqa: BLE001
            registry_data = {"jobs": {}}
    reg = (registry_data.get("jobs") or {}).get(lane) or {}

    el = {}
    proposers = sorted({f"{p['by']} ({p['model']})" for d in dis
                        for p in d["proposals"].values()})
    el["proposer"] = (_present(proposers, "disagreements") if proposers
                      else _missing("no competing proposal recorded (ops/disagreement.py)"))
    impl = sorted({f"{r['implementer']} ({r['implementer_model']})" for r in revs}
                  | {f"session ({r['model']})" for r in sess if r.get("model")})
    el["implementer"] = (_present(impl, "REVIEWS.jsonl / SESSION_LOG.jsonl") if impl
                         else _missing("no review or session record names the implementer"))
    el["reviewer"] = (_present([{"reviewer": r["reviewer"], "model": r["reviewer_model"],
                                 "head": r["head"], "verdict": r["verdict"],
                                 "second_model": r["second_model"], "certifies": False}
                                for r in revs], "REVIEWS.jsonl") if revs
                      else _missing("no independent review recorded (ops/review.py)"))
    el["disagreement"] = (_present([{"id": d["id"], "question": d["question"],
                                     "outcome": (d.get("resolution") or {}).get("outcome")
                                     or "NOT_RESOLVED"} for d in dis], "disagreements")
                          if dis else _missing("no disagreement recorded"))
    ev = [e for d in dis for e in d["evidence"]]
    el["evidence"] = (_present(ev, "disagreements") if ev
                      else _missing("no evidence item recorded"))
    tests = sorted(set((ho.get("handoff") or {}).get("tests") or [])
                   | {t for e in done + queued for t in e.get("tests") or []})
    el["tests"] = (_present(tests, "handoff / merge queue") if tests
                   else _missing("neither a handoff nor a queue entry names tests"))
    costs = [r.get("cost_cad") for r in sess]
    known = [c for c in costs if isinstance(c, (int, float))]
    el["cost"] = (_present({"sessions": len(sess),
                            "cost_cad": round(sum(known), 4) if known else UNMEASURED,
                            "sessions_unmeasured": len(costs) - len(known)},
                           "SESSION_LOG.jsonl") if sess
                  else _missing("no session record for this lane (ops/session_log.py)"))
    res = [d for d in dis if d.get("resolution")]
    el["approach"] = (_present({d["id"]: d["resolution"]["status"] for d in res},
                               "disagreement resolutions") if res
                      else _missing("no resolved disagreement: no accepted/rejected approach"))
    integ = (reg.get("integrated") or {}).get("commit") or (done[-1]["commit"] if done else None)
    el["integration"] = (_present({"commit": integ,
                                   "target": done[-1].get("target") if done else
                                   reg.get("integration_ref")}, "merge queue / registry")
                         if integ else _missing("NOT_INTEGRATED"))
    missing = [k for k in ELEMENTS if el[k]["state"] == "MISSING"]
    return {"lane": lane, "elements": el, "missing": missing,
            "complete": not missing}


def to_markdown(w: dict) -> str:
    out = [f"# Collaboration workspace: {w['lane']}", ""]
    for k in ELEMENTS:
        e = w["elements"][k]
        val = (json.dumps(e["value"])[:600] if e["state"] == "PRESENT" else e["why"])
        out.append(f"- **{k}** {e['state']}: {val}")
    return "\n".join(out) + "\n"


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    w = build(argv[1])
    print(to_markdown(w) if "--md" in argv else json.dumps(w, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
