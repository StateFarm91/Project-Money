"""W4-L0PACKET: write the Launch-0 product readiness packet for one database.

    PYTHONPATH=src python research/final_build/w4/l0_readiness_run.py <sqlite-path> <out-dir>

Reads only (`launch.product_readiness.build`): every outbound socket is refused, no
credential is read. Point it at a scratch release-chain DB (pipe_chain_run.py) or, after a
deploy, run the same module in production.
"""
from __future__ import annotations

import json
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))


def _closed(*_a, **_k):
    raise OSError("network closed for the readiness packet")


def main(argv: list[str]) -> int:
    socket.socket.connect = _closed            # type: ignore[assignment]
    socket.create_connection = _closed         # type: ignore[assignment]
    from brambleloop.core.db import Database
    from brambleloop.launch import product_readiness as PR

    db_path, out = Path(argv[0]).resolve(), Path(argv[1])
    db = Database(f"sqlite:///{db_path}", scratch=True)
    db.create_all()
    p = PR.build(db)
    out.mkdir(parents=True, exist_ok=True)
    (out / "L0_PRODUCT_READINESS.json").write_text(json.dumps(p, indent=1, default=str) + "\n")
    (out / "L0_PRODUCT_READINESS.md").write_text(PR.render_markdown(p))
    print(json.dumps({k: {g: x["gates"][g] for g in PR.GATES}
                      for x in p["products"] for k in [x["candidate"]]}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
