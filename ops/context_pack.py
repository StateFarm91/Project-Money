#!/usr/bin/env python3
"""F-455: a department's context pack -- the evidence for its own work, and nothing else.

A lane given the whole company's history spends tokens on it and borrows assumptions from
other domains. `build(rows)` assembles, for exactly the requirement rows a lane holds:

  * each row's requirement text (master registry / Build 2 registry), its matrix gap,
    next action, producer, consumer, cited tests and gate;
  * the module files those name (producer/consumer paths), as the files to read first;
  * the lane's own registry record when a lane is named (owned paths, waits, rows).

The rows come from `--rows` or from the lane's enrolment (`ops/registry.py enrol --rows`),
so dispatch and pack agree. Output is JSON or Markdown; it reads files and writes nothing.

  python3 ops/context_pack.py --rows F-485,F-467 [--md]
  python3 ops/context_pack.py --lane W4-FMBATCH1 [--md]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BL = ROOT / "brambleloop"
REGISTRY = BL / "research" / "final_build" / "master_registry.json"
MATRIX = BL / "research" / "final_build" / "closure_matrix.json"


def _fm_text() -> dict:
    d = json.loads(REGISTRY.read_text())
    rows = d.get("requirements") or d.get("rows") or d
    it = rows.values() if isinstance(rows, dict) else rows
    return {r["id"]: r for r in it if isinstance(r, dict) and "id" in r}


def _matrix() -> dict:
    return {r["uid"]: r for r in json.loads(MATRIX.read_text())["matrix"]}


def _b2_text() -> dict:
    sys.path.insert(0, str(BL / "src"))
    try:
        from brambleloop.build2 import requirements as reg

        return {str(r.id): {"title": r.title, "text": r.body} for r in reg.load()}
    except Exception:                                                  # noqa: BLE001
        return {}


def _paths(m: dict) -> list[str]:
    out = []
    for k in ("producer", "consumer"):
        v = str(m.get(k) or "")
        for p in re.findall(r"[\w./-]+\.py", v):
            out.append(p.split("::")[0])
    return sorted(set(out))


def build(rows: list[str], *, lane: dict | None = None) -> dict:
    fm, mx = _fm_text(), _matrix()
    b2 = None
    pack, files, unknown = [], set(), []
    for rid in rows:
        rid = rid.strip()
        if not rid:
            continue
        if rid.upper().startswith("F-"):
            uid = rid.upper()
            if uid not in fm and uid not in mx:
                unknown.append(rid)
                continue
            m = mx.get(uid, {})
            p = _paths(m)
            files.update(p)
            pack.append({"row": uid, "title": (fm.get(uid) or m).get("title"),
                         "requirement": (fm.get(uid) or {}).get("text"),
                         "gap": m.get("missing_part"), "next_action": m.get("next_action"),
                         "producer": m.get("producer"), "consumer": m.get("consumer"),
                         "tests": m.get("tests") or [], "gate": m.get("gate"),
                         "files": p})
        else:
            b2 = b2 if b2 is not None else _b2_text()
            key = rid.lstrip("#")
            if key not in b2:
                unknown.append(rid)
                continue
            pack.append({"row": f"#{key}", "title": b2[key]["title"],
                         "requirement": b2[key]["text"]})
    return {"rows": pack, "files_to_read_first": sorted(files), "unknown_rows": unknown,
            "lane": ({k: lane.get(k) for k in ("name", "lane", "branch", "owns", "rows",
                                               "waits_on")} if lane else None),
            "excluded": "every other row, department and lane: not this lane's context"}


def to_markdown(p: dict) -> str:
    lines = ["# Context pack", ""]
    if p["lane"]:
        lines += [f"Lane: {p['lane'].get('name')} (owns {p['lane'].get('owns') or 'nothing declared'})", ""]
    for r in p["rows"]:
        lines += [f"## {r['row']} {r.get('title') or ''}", "", f"Requirement: {r.get('requirement')}"]
        if r.get("gap"):
            lines += [f"Gap: {r['gap']}", f"Next: {r.get('next_action')}"]
        if r.get("files"):
            lines += ["Files: " + ", ".join(r["files"])]
        lines += [""]
    if p["unknown_rows"]:
        lines += [f"Unknown rows (not packed): {p['unknown_rows']}"]
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    rows, lane, md = [], None, "--md" in argv
    if "--rows" in argv:
        rows = argv[argv.index("--rows") + 1].split(",")
    if "--lane" in argv:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import registry

        name = argv[argv.index("--lane") + 1]
        lane = registry.Registry().load()["jobs"].get(name)
        if lane is None:
            print(f"refused: lane {name!r} is not enrolled")
            return 2
        rows = rows or list(lane.get("rows") or [])
    if not rows:
        print("refused: no rows (give --rows, or enrol the lane with --rows)")
        return 2
    p = build(rows, lane=lane)
    print(to_markdown(p) if md else json.dumps(p, indent=1))
    return 1 if p["unknown_rows"] else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
