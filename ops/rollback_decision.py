#!/usr/bin/env python3
"""F-381: a regression the post-deploy readback detects is contained by its severity.

F-381 (Final Master, launch-critical): "Every material autonomous deployment preserves a
known-good predecessor and an executable rollback/recovery path. Detected regression triggers
containment and rollback according to severity."

The predecessor and the executable path already exist: `ops/deploy.sh` rehearses the rollback
to the commit production runs before every push (`deploy_guard.py rehearse-rollback`, against
`brambleloop/release/DEPLOYED_HISTORY.json`), and `deploy.sh --rollback-to` performs one. What
was missing is the severity rule. A failed readback (`ops/readback.py`, F-144) ended in exit 5
with "fix forward or roll back per ops/ROLLBACK_RUNBOOK.md" whatever had failed, so a deploy
that broke the shadow phase or the cost ceilings stayed live exactly as long as one that only
left a dead letter.

The rule, computed from the readback:

* **P0 -- roll back now.** A readback feature that guards the company's safety or its ability
  to run at all: the shadow phase, nothing published, publication refusals recorded, the
  catalogue unpublished, every agent's cost ceiling, the boot guard's release record, the
  embedded worker, and the release identity. A P0 feature that FAILs **or reads UNKNOWN** is a
  P0 (UNKNOWN is never a pass), and so is production unreachable after the deploy.
* **P1 -- fix forward.** Every other feature (dead letters, the smoke matrix, a served route).
  The deploy stays, the failure is reported, and the next release fixes it. A feature this
  table does not name is P1 by default; it is never silently a pass.

`decide()` is pure. The CLI reads a readback JSON (`readback.py --json`) and exits 0 when
nothing failed, 5 for fix-forward, 6 when the severity requires a rollback; `ops/deploy.sh`
acts on 6 by performing the sanctioned rollback to the commit production ran before the push
(it re-enters itself with `--rollback-to`, so the guard checks the rollback like any deploy).
This module never deploys, never makes a network call and never touches production.

  python3 ops/rollback_decision.py --readback READBACK.json [--previous SHA]
"""
from __future__ import annotations

import argparse
import json
import sys

PASS, FAIL, UNKNOWN = "PASS", "FAIL", "UNKNOWN"
NONE, FIX_FORWARD, ROLLBACK = "NONE", "FIX_FORWARD", "ROLLBACK"
EXIT = {NONE: 0, FIX_FORWARD: 5, ROLLBACK: 6}

# Readback feature names (ops/readback.py MANIFEST) whose failure is a P0.
P0_FEATURES = frozenset({
    "release identity",
    "boot guard proves the release record",
    "embedded worker alive",
    "shadow phase holds",
    "nothing published in shadow",
    "publication refusals recorded",
    "every agent has a cost ceiling",
    "catalogue says nothing is published",
})


def severity(feature: str) -> str:
    return "P0" if feature in P0_FEATURES else "P1"


def decide(readback: dict, *, previous: str | None = None) -> dict:
    """The containment decision for one readback. `previous` is the rollback target."""
    if not isinstance(readback, dict) or "features" not in readback:
        return {"decision": ROLLBACK, "severity": "P0", "failed": [],
                "why": "no readable readback: nothing was verified after the deploy, which is "
                       "never a pass", "rollback_to": previous}
    failed = [{"feature": f.get("feature"), "verdict": f.get("verdict"),
               "severity": severity(str(f.get("feature")))}
              for f in readback.get("features") or [] if f.get("verdict") != PASS]
    if not readback.get("reachable"):
        return {"decision": ROLLBACK, "severity": "P0", "failed": failed,
                "why": "production did not answer the readback after the deploy",
                "rollback_to": previous}
    if not failed and readback.get("verdict") == PASS:
        return {"decision": NONE, "severity": None, "failed": [],
                "why": "every feature read back", "rollback_to": None}
    if not failed:
        # A non-PASS verdict with no failing feature is not a pass either.
        return {"decision": ROLLBACK, "severity": "P0", "failed": [],
                "why": f"readback verdict {readback.get('verdict')!r} with no feature named",
                "rollback_to": previous}
    p0 = [f for f in failed if f["severity"] == "P0"]
    if p0:
        return {"decision": ROLLBACK, "severity": "P0", "failed": failed,
                "why": "P0 regression: " + ", ".join(f"{f['feature']} {f['verdict']}"
                                                     for f in p0),
                "rollback_to": previous}
    return {"decision": FIX_FORWARD, "severity": "P1", "failed": failed,
            "why": "P1 only: " + ", ".join(f"{f['feature']} {f['verdict']}" for f in failed),
            "rollback_to": None}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--readback", required=True)
    ap.add_argument("--previous", default="")
    a = ap.parse_args(argv)
    try:
        with open(a.readback, encoding="utf-8") as f:
            readback = json.load(f)
    except (OSError, ValueError):
        readback = None
    out = decide(readback, previous=a.previous or None)
    print(json.dumps(out, indent=1))
    print(f"rollback_decision: {out['decision']} ({out['why']})", file=sys.stderr)
    return EXIT[out["decision"]]


if __name__ == "__main__":
    raise SystemExit(main())
