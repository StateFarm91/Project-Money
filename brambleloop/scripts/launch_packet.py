#!/usr/bin/env python3
"""Generate the Launch-0 owner launch packet (F-878) from database and runtime state.

    PYTHONPATH=src python scripts/launch_packet.py [--db URL] [--sha SHA] [--out DIR]

Writes research/final_build/evidence/launch_packet_<sha>_<utc>.{json,md}. Reads only: no
network, no model, no provider, no writes to the database. Every verdict is read at run time;
nothing is hard-coded PASS, and anything unread is reported UNKNOWN.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _sha() -> str:
    from brambleloop.core import build

    sha = build.commit()
    if sha and sha != "unknown":
        return sha
    try:
        return subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], check=True,
                              capture_output=True, text=True).stdout.strip() or "unknown"
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", help="database URL (default: the runtime's configured database)")
    ap.add_argument("--sha", help="candidate commit (default: build identity, then git HEAD)")
    ap.add_argument("--out", default=str(ROOT / "research" / "final_build" / "evidence"))
    args = ap.parse_args(argv)

    from brambleloop.core.db import Database
    from brambleloop.launch import packet

    db = Database(args.db) if args.db else Database()
    p = packet.build(db, sha=args.sha or _sha(), repo_root=ROOT)
    j, m = packet.write(p, Path(args.out))
    print(f"verdict {p['verdict']}; wrote {j} and {m}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
