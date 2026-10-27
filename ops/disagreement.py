#!/usr/bin/env python3
"""F-715 Evidence Resolves Disagreement -- build-side competing proposals, decided by evidence.

The requirement: "Model prestige never decides a technical disagreement. Resolve competing
proposals using reproducible tests, primary evidence, Product Truth, real marketplace/customer
outcomes and measured economics."

The runtime already decides promotions by recorded runs (league.compare) and deterministic
validation. Development disagreements -- two workers, or two models, proposing different fixes
-- were adjudicated by whoever wrote the last message. This is the record and the rule:

  open       a disagreement: the question and the lane it belongs to
  propose    a competing approach, with who and which model proposed it (recorded for the
             collaboration workspace, F-716 -- and never read by `resolve`)
  evidence   one item for or against a proposal, of a closed kind:
               test                 a reproducible test (path in the repository + the command)
               primary_evidence     a primary source (a file, log or API reading by reference)
               product_truth        a Product Truth / CIR validation result
               marketplace_outcome  a real marketplace or customer outcome
               economics            a measured cost or margin
             "SUPPORTS" or "REFUTES". Opinion, rank, model name or confidence is not a kind.
  resolve    deterministic: a proposal with any REFUTES evidence is rejected; if exactly one
             proposal remains with SUPPORTS evidence it is ACCEPTED and the rest REJECTED;
             otherwise UNRESOLVED, naming what evidence would discriminate. Proposer identity
             and model are not inputs, so swapping them cannot change the outcome.

Files: `brambleloop/research/final_build/disagreements/<id>.json` (in the repository).
Local tooling only.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "brambleloop" / "research" / "final_build" / "disagreements"
KINDS = ("test", "primary_evidence", "product_truth", "marketplace_outcome", "economics")
RESULTS = ("SUPPORTS", "REFUTES")
ACCEPTED, REJECTED, UNRESOLVED = "ACCEPTED", "REJECTED", "UNRESOLVED"


class DisagreementRefused(ValueError):
    pass


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _path(did: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,80}", did or ""):
        raise DisagreementRefused(f"id {did!r} is not a plain identifier")
    return DIR / f"{did}.json"


def load(did: str) -> dict:
    try:
        return json.loads(_path(did).read_text())
    except (OSError, ValueError):
        raise DisagreementRefused(f"no disagreement {did!r}") from None


def _save(d: dict) -> dict:
    p = _path(d["id"])
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(d, indent=1) + "\n")
    os.replace(tmp, p)
    return d


def open_(did: str, *, question: str, lane: str) -> dict:
    if _path(did).exists():
        raise DisagreementRefused(f"{did} already exists")
    if not str(question).strip() or not str(lane).strip():
        raise DisagreementRefused("a disagreement names its question and lane")
    return _save({"id": did, "question": " ".join(question.split()), "lane": lane,
                  "opened_utc": _utc(), "proposals": {}, "evidence": [], "resolution": None})


def propose(did: str, key: str, *, by: str, model: str, approach: str) -> dict:
    d = load(did)
    if key in d["proposals"]:
        raise DisagreementRefused(f"proposal {key} already recorded")
    if not all(str(x).strip() for x in (key, by, model, approach)):
        raise DisagreementRefused("a proposal names its key, proposer, model and approach")
    d["proposals"][key] = {"by": by, "model": model, "approach": " ".join(approach.split()),
                           "utc": _utc()}
    d["resolution"] = None
    return _save(d)


def evidence(did: str, key: str, *, kind: str, ref: str, result: str, detail: str = "",
             command: str = "", repo: Path = ROOT) -> dict:
    d = load(did)
    if key not in d["proposals"]:
        raise DisagreementRefused(f"no proposal {key} in {did}")
    if kind not in KINDS:
        raise DisagreementRefused(f"evidence kind must be one of {KINDS}; opinion, rank, "
                                  "model or confidence is not evidence")
    if result not in RESULTS:
        raise DisagreementRefused(f"result must be one of {RESULTS}")
    if not str(ref).strip():
        raise DisagreementRefused("evidence cites what it is (a path, log, reading or record)")
    if kind == "test":
        if not (Path(repo) / ref).is_file():
            raise DisagreementRefused(f"test {ref} is not in the repository: not reproducible")
        if not str(command).strip():
            raise DisagreementRefused("a test is evidence only with the command that reruns it")
    d["evidence"].append({"proposal": key, "kind": kind, "ref": ref, "result": result,
                          "command": command, "detail": " ".join(str(detail).split())[:1000],
                          "utc": _utc()})
    d["resolution"] = None
    return _save(d)


def decide(proposals: dict, items: list[dict]) -> dict:
    """The rule, pure: reads proposal keys and evidence only (never `by` or `model`)."""
    keys = sorted(proposals)
    refuted = sorted({e["proposal"] for e in items if e["result"] == "REFUTES"})
    supported = sorted({e["proposal"] for e in items if e["result"] == "SUPPORTS"}
                       - set(refuted))
    status = {k: (REJECTED if k in refuted else UNRESOLVED) for k in keys}
    if len(supported) == 1:
        win = supported[0]
        status = {k: (ACCEPTED if k == win else REJECTED) for k in keys}
        return {"outcome": ACCEPTED, "accepted": win, "status": status,
                "basis": [e for e in items if e["proposal"] == win or e["result"] == "REFUTES"]}
    need = ("evidence that separates " + ", ".join(supported) if supported else
            "supporting evidence for any surviving proposal")
    return {"outcome": UNRESOLVED, "accepted": None, "status": status,
            "needs": need + " (a test, primary evidence, Product Truth, a real outcome or a "
                            "measured economic)"}


def resolve(did: str) -> dict:
    d = load(did)
    res = decide(d["proposals"], d["evidence"])
    d["resolution"] = {**res, "utc": _utc()}
    _save(d)
    return d


def for_lane(lane: str) -> list[dict]:
    out = []
    for p in sorted(DIR.glob("*.json")) if DIR.exists() else []:
        try:
            d = json.loads(p.read_text())
        except (OSError, ValueError):
            continue
        if d.get("lane") == lane:
            out.append(d)
    return out


def main(argv: list[str]) -> int:
    args = list(argv[1:])
    if len(args) < 2:
        print(__doc__)
        return 2
    cmd, did, rest = args[0], args[1], args[2:]
    opts, pos = {}, []
    while rest:
        a = rest.pop(0)
        if a.startswith("--") and rest:
            opts[a[2:]] = rest.pop(0)
        else:
            pos.append(a)
    try:
        if cmd == "open":
            out = open_(did, question=opts.get("question", ""), lane=opts.get("lane", ""))
        elif cmd == "propose" and pos:
            out = propose(did, pos[0], by=opts.get("by", ""), model=opts.get("model", ""),
                          approach=opts.get("approach", ""))
        elif cmd == "evidence" and pos:
            out = evidence(did, pos[0], kind=opts.get("kind", ""), ref=opts.get("ref", ""),
                           result=opts.get("result", ""), detail=opts.get("detail", ""),
                           command=opts.get("command", ""))
        elif cmd == "resolve":
            out = resolve(did)
        else:
            print(__doc__)
            return 2
    except DisagreementRefused as exc:
        print(f"refused: {exc}")
        return 2
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
