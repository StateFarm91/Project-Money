"""F-630: greatness without finish-line drift -- before launch, launch work goes first.

The Final Master forbids endless pre-launch expansion: while the company is in SHADOW, work
that does not serve launch must not crowd out work that does. The link is the closure matrix's
own mapping: a Build 2 requirement serves launch when a LAUNCH-CRITICAL Final Master row lists
it among its `build2_rows`. That mapping is projected into `launch_scope.json` beside this
module (it ships in the image; `research/` does not) by `build_map`, and a test pins the
shipped file to the matrix.

`order(ready, phase)` puts launch-serving READY work first in SHADOW and tags every item
(`pre_launch_scope`: `serves_launch` / `deprioritised_pre_launch`); after SHADOW the order is
untouched. Nothing is removed from the queue -- spare capacity still reaches later work.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

MAP_FILE = Path(__file__).resolve().with_name("launch_scope.json")
SERVES = "serves_launch"
DEPRIORITISED = "deprioritised_pre_launch"


def build_map(matrix: dict) -> dict[str, list[str]]:
    out: dict[str, set] = {}
    for r in matrix.get("matrix") or []:
        if r.get("launch_class") != "LAUNCH-CRITICAL":
            continue
        for b in r.get("build2_rows") or []:
            m = re.match(r"#(\d+)", str(b))
            if m:
                out.setdefault(m.group(1), set()).add(r["uid"])
    return {k: sorted(v) for k, v in sorted(out.items(), key=lambda kv: int(kv[0]))}


@lru_cache(maxsize=1)
def launch_map() -> dict[str, list[str]]:
    try:
        return json.loads(MAP_FILE.read_text())
    except (OSError, ValueError):
        return {}


def serves_launch(requirement_id: int) -> list[str]:
    return launch_map().get(str(int(requirement_id)), [])


def order(ready: list[dict], phase: str) -> list[dict]:
    known = bool(launch_map())
    for r in ready:
        fm = serves_launch(r["requirement_id"]) if known else []
        r["pre_launch_scope"] = (SERVES if fm else DEPRIORITISED) if known else "UNKNOWN"
        r["serves_launch_rows"] = fm[:5]
    if (phase or "").lower() != "shadow" or not known:
        return ready
    return sorted(ready, key=lambda r: (r["pre_launch_scope"] != SERVES,))   # stable
