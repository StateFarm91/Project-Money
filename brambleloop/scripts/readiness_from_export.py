#!/usr/bin/env python3
"""F-848 next_action (review 6773190553 #5): judge launch readiness on a REAL production state,
read-only, without this script ever holding the operator credential or touching production.

The shadow rehearsal's `seed_catalogue` builds a production-SHAPED catalogue in a scratch
database. The row's next_action asks for production's own state. Production's database is
reachable only through `GET /api/continuity/export`, which requires the operator credential
(`core.opsauth`; closed to everyone, the owner included, without it). So the split is:

  1. The credential holder (the integrator/operator) downloads the portable export:
       curl -H "Authorization: Bearer $OPS_TOKEN" https://<prod>/api/continuity/export -o x.jsonl
     It holds buyer and owner data: keep it outside the repository and delete it afterwards.
  2. This script restores it (`core.continuity.restore`, which refuses a truncated or unknown
     file) into a temporary SQLite database, evaluates the launch verdict a phase move up would
     face (`readiness.transition_verdict`) and explains every outstanding requirement
     (`shadow_rehearsal.explain_readiness`): who can clear it and the evidence it gave.

The restored copy lives only in a temporary directory that is deleted on exit, also when the
verdict raises; nothing is written beside the export. The only other write is the report itself,
and only when `--out` is given. Production is not contacted.

Two requirements read the machine this runs on, not production: `etsy_integration`
(`credentials_present`) and `phase` reflect the local operator's environment. Read them from
production's own /api/launch instead. The output names requirements, owners and evidence
digests; review it before sharing, since evidence can quote shop data.

    cd brambleloop && .venv/bin/python scripts/readiness_from_export.py EXPORT.jsonl
        [--to staging] [--out PATH]
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


def readiness_from_export(export_path: str | Path, *, to: str = "staging") -> dict:
    """Restore `export_path` into a throwaway database and report the transition verdict and
    every outstanding requirement explained. Read-only with respect to everything else."""
    sys.path.insert(0, str(SRC))
    sys.path.insert(0, str(ROOT / "scripts"))
    from brambleloop.core import continuity
    from brambleloop.core.db import Database
    from brambleloop.launch import readiness as R
    from shadow_rehearsal import explain_readiness

    with tempfile.TemporaryDirectory(prefix="bl-readiness-") as tmp:
        db = Database(f"sqlite:///{tmp}/restored.sqlite")
        counts = continuity.restore(export_path, db)
        verdict = R.transition_verdict(db, to=to)
        explained = explain_readiness(db, to=to)
        db.engine.dispose()
    return {"source": "continuity export (restored into a temporary database)",
            "restored_rows": sum(counts.values()), "tables": len(counts),
            "to": to, "ready": verdict["ready"], "failing": verdict["failing"],
            "questions": verdict["questions"], "explained": explained,
            "by_clearer": _by_clearer(explained)}


def _by_clearer(explained: list[dict]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for item in explained:
        out.setdefault(item["cleared_by"], []).append(item["key"])
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("export", type=Path)
    p.add_argument("--to", default="staging")
    p.add_argument("--out", type=Path, default=None)
    a = p.parse_args()
    report = readiness_from_export(a.export, to=a.to)
    text = json.dumps(report, indent=1, default=str)
    if a.out:
        a.out.write_text(text)
    print(text)
    return 0 if report["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
