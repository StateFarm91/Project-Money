#!/usr/bin/env python3
"""F-714 Independent Review and F-866 Independent Model Review -- build-side, before promotion.

F-714: "High-risk customer-facing, financial, marketplace, security, infrastructure and Product
Truth work may receive independent adversarial review by a different model/agent before
promotion."
F-866: "A second model may adversarially review evidence without becoming certification
authority."

The runtime already separates judgement from authorship (a proposer cannot approve or promote
its own work; blind multi-judge panels). Build work had no such step: a lane that changed the
deploy guard or the finance books reached integration on its author's word plus its tests.

  classify(paths)   which high-risk classes a change touches (path table below, closed)
  record(...)       one adversarial review of one lane head, appended to
                    `brambleloop/research/final_build/REVIEWS.jsonl` (in the repository). It is
                    refused when the reviewer is the implementer, and it can never certify:
                    `certifies` is always false and any attempt to set it is refused (F-866 --
                    certification stays with deterministic validation, the release gates and
                    the owner).
  gate(lane, head, paths)
                    used by ops/integrate.py as a checklist item: a lane whose change touches a
                    high-risk class integrates only with a review of exactly that head by a
                    different agent, and with no open BLOCKERS verdict on it. A review of an
                    older head does not carry over. Low-risk lanes pass untouched.

Local tooling only: reads and appends one file, no network, no push.

  python3 ops/review.py classify PATH...
  python3 ops/review.py record --lane L --head SHA --implementer A --implementer-model M \
          --reviewer B --reviewer-model N --verdict NO_BLOCKERS|BLOCKERS --findings "..."
  python3 ops/review.py gate --lane L --head SHA PATH...
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "brambleloop" / "research" / "final_build" / "REVIEWS.jsonl"
PKG = "brambleloop/src/brambleloop/"
VERDICTS = ("NO_BLOCKERS", "BLOCKERS")

# Closed table: a new high-risk area is added here deliberately (the test pins every class).
HIGH_RISK: dict[str, tuple[str, ...]] = {
    "customer_facing": (PKG + "support/", PKG + "growth/", PKG + "seo/", PKG + "brand/",
                        PKG + "store_foundation/"),
    "financial": (PKG + "finance/", PKG + "commerce/", "ops/caps.py", "finance/"),
    "marketplace": (PKG + "integrations/", PKG + "publish/", PKG + "launch/"),
    "security": (PKG + "authority/", PKG + "gateway/", "ops/deploy_guard.py",
                 "ops/integration_authority.py", "ops/hooks/", "ops/signing_audit.py"),
    "infrastructure": (PKG + "runtime/", PKG + "app/", "ops/deploy.sh",
                       "ops/verify_deploy.py", "ops/db_backup/", "Dockerfile",
                       "railway.json", "railway.toml", "nixpacks.toml", "Procfile"),
    "product_truth": (PKG + "cir/", PKG + "quality/", PKG + "gates/"),
}


class ReviewRefused(ValueError):
    pass


def classify(paths) -> dict[str, list[str]]:
    hit: dict[str, list[str]] = {}
    for p in paths or ():
        p = str(p)
        p = p[2:] if p.startswith("./") else p
        for cls, prefixes in HIGH_RISK.items():
            if any(p == pre or p.startswith(pre) for pre in prefixes):
                hit.setdefault(cls, []).append(p)
    return hit


def _read() -> list[dict]:
    try:
        return [json.loads(ln) for ln in LOG.read_text().splitlines() if ln.strip()]
    except (OSError, ValueError):
        return []


def record(*, lane: str, head: str, implementer: str, implementer_model: str,
           reviewer: str, reviewer_model: str, verdict: str, findings: str,
           **extra) -> dict:
    if "certifies" in extra or "certify" in extra:
        raise ReviewRefused("a review never certifies (F-866): certification stays with the "
                            "deterministic gates, the release record and the owner")
    if extra:
        raise ReviewRefused(f"unknown fields {sorted(extra)}")
    if not re.fullmatch(r"[0-9a-f]{7,40}", str(head or "")):
        raise ReviewRefused("head must be the reviewed commit (7-40 hex)")
    for k, v in (("lane", lane), ("implementer", implementer), ("reviewer", reviewer),
                 ("implementer_model", implementer_model), ("reviewer_model", reviewer_model)):
        if not str(v or "").strip():
            raise ReviewRefused(f"{k} is required")
    if reviewer.strip().lower() == implementer.strip().lower():
        raise ReviewRefused("the implementer cannot review its own work (F-714)")
    if verdict not in VERDICTS:
        raise ReviewRefused(f"verdict must be one of {VERDICTS}")
    if not str(findings or "").strip():
        raise ReviewRefused("an adversarial review states what it checked and found")
    rec = {"utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "lane": lane,
           "head": head, "implementer": implementer, "implementer_model": implementer_model,
           "reviewer": reviewer, "reviewer_model": reviewer_model,
           "second_model": reviewer_model.strip().lower() != implementer_model.strip().lower(),
           "verdict": verdict, "findings": " ".join(str(findings).split())[:4000],
           "certifies": False}
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as fh:
        fh.write(json.dumps(rec, sort_keys=True) + "\n")
    return rec


def reviews_for(lane: str, head: str) -> list[dict]:
    return [r for r in _read() if r.get("lane") == lane and head and
            (r.get("head", "").startswith(head) or head.startswith(r.get("head", "-")))]


def gate(lane: str, head: str, paths) -> dict:
    risk = classify(paths)
    if not risk:
        return {"check": "independent review (F-714)", "ok": True, "required": False}
    revs = reviews_for(lane, head)
    blockers = [r for r in revs if r["verdict"] == "BLOCKERS"]
    clear = [r for r in revs if r["verdict"] == "NO_BLOCKERS"
             and r["reviewer"].lower() != r["implementer"].lower()]
    ok = bool(clear) and not blockers
    why = ("" if ok else
           "BLOCKERS recorded on this head" if blockers else
           f"no independent review of {head[:12]} recorded for lane {lane}")
    return {"check": "independent review (F-714)", "ok": ok, "required": True,
            "classes": sorted(risk), "reviews": len(revs), "why": why,
            "certifies": False}


def main(argv: list[str]) -> int:
    args = list(argv[1:])
    if not args:
        print(__doc__)
        return 2
    cmd = args.pop(0)
    opts, pos = {}, []
    while args:
        a = args.pop(0)
        if a.startswith("--") and args:
            opts[a[2:].replace("-", "_")] = args.pop(0)
        else:
            pos.append(a)
    try:
        if cmd == "classify":
            out = classify(pos)
        elif cmd == "record":
            out = record(**opts)
        elif cmd == "gate":
            out = gate(opts.get("lane", ""), opts.get("head", ""), pos)
        else:
            print(__doc__)
            return 2
    except (ReviewRefused, TypeError) as exc:
        print(f"refused: {exc}")
        return 2
    print(json.dumps(out, indent=1))
    return 0 if not isinstance(out, dict) or out.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
