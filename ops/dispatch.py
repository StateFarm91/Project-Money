#!/usr/bin/env python3
"""F-494: advisory dispatch of READY build work -- the next session's brief, ready to start.

The deployed runtime dispatches its own follow-on jobs and cadences. Build work (code) needs
a session, and nothing turned a newly READY build task into one without somebody saying
"continue". This turns each READY task the build executor reports into a **dispatch card**:
the rows, the lane name to enrol, the exact `ops/registry.py enrol` command (with `--rows`,
so the F-476 duplicate check and the F-455 context pack both apply), and the context pack.

Advisory and local only, by construction:
  * it reads the READY list (a saved `/api/build` or executor-queue JSON, or a local
    database through `build2.executor.queue`) and the local lane registry;
  * it skips work a live lane already holds and anything not READY (parked work waits on
    its gate; nothing here opens one);
  * it prints (or writes `--out`) the cards. It starts no session, pushes nothing, deploys
    nothing, and leaves the owner's per-SHA deploy approval and independent review exactly
    where they are.

  python3 ops/dispatch.py --ready-json build.json [--out DISPATCH.md] [--limit 5]
  python3 ops/dispatch.py --db sqlite:///path.db
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def ready_from_json(path: Path) -> list[dict]:
    d = json.loads(Path(path).read_text())
    for key in ("ready", "queue"):
        if isinstance(d.get(key), list):
            return d[key]
        if isinstance(d.get(key), dict) and isinstance(d[key].get("ready"), list):
            return d[key]["ready"]
    raise ValueError("no READY list in this file (expected 'ready' or 'queue.ready')")


def ready_from_db(url: str) -> list[dict]:
    sys.path.insert(0, str(HERE.parent / "brambleloop" / "src"))
    from brambleloop.build2 import executor
    from brambleloop.core.db import Database

    return executor.queue(Database(url), limit=200)["ready"]


def _held_rows(reg_data: dict) -> set[str]:
    out = set()
    for rec in (reg_data.get("jobs") or {}).values():
        if rec.get("integrated") or rec.get("role", "work") != "work":
            continue
        out.update(str(r).upper() for r in rec.get("rows") or [])
    return out


def cards(ready: list[dict], *, registry_data: dict, limit: int = 5) -> dict:
    sys.path.insert(0, str(HERE))
    import context_pack

    held = _held_rows(registry_data)
    out, skipped = [], []
    for t in ready:
        if t.get("state") not in (None, "READY", "ready"):
            skipped.append({"task": t.get("requirement_id"), "why": f"state {t.get('state')}"})
            continue
        rid = t.get("requirement_id")
        row = str(rid).upper() if str(rid).upper().startswith("F-") else f"#{rid}"
        key = row.upper()
        if key in held or (t.get("claimed_by")):
            skipped.append({"task": row, "why": "already held by a live lane or claimed"})
            continue
        lane = f"build-{key.strip('#').lower()}"
        pack = context_pack.build([row])
        out.append({
            "task": row, "title": t.get("title"), "priority": t.get("priority"),
            "lane": lane,
            "enrol": (f"python3 ops/registry.py enrol {lane} <log-path> {lane} "
                      f"<branch> --rows {row}"),
            "context_pack": f"python3 ops/context_pack.py --rows {row} --md",
            "files_to_read_first": pack["files_to_read_first"],
            "brief": (f"Build {row} ({t.get('title')}). Start from the context pack; run only "
                      "its targeted tests; commit on the lane branch; queue it with "
                      "ops/integrate.py enqueue. Deploy stays behind ops/deploy.sh with the "
                      "owner's per-SHA approval and the independent review."),
        })
        if len(out) >= limit:
            break
    return {"cards": out, "skipped": skipped, "advisory": True,
            "starts_sessions": False, "pushes": False, "deploys": False}


def to_markdown(c: dict) -> str:
    lines = ["# Dispatch cards (advisory; nothing was started)", ""]
    for k in c["cards"]:
        lines += [f"## {k['task']} {k.get('title') or ''}", "", k["brief"], "",
                  f"- enrol: `{k['enrol']}`", f"- context: `{k['context_pack']}`", ""]
    if not c["cards"]:
        lines += ["No READY build work that no live lane holds.", ""]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    def opt(name, default=None):
        return argv[argv.index(name) + 1] if name in argv else default

    try:
        if opt("--ready-json"):
            ready = ready_from_json(Path(opt("--ready-json")))
        elif opt("--db"):
            ready = ready_from_db(opt("--db"))
        else:
            print("refused: give --ready-json FILE or --db URL")
            return 2
    except (OSError, ValueError) as exc:
        print(f"refused: {exc}")
        return 2
    sys.path.insert(0, str(HERE))
    import registry

    reg = registry.Registry(Path(os.environ.get("BRAMBLELOOP_JOB_REGISTRY") or registry.REGISTRY))
    c = cards(ready, registry_data=reg.load(), limit=int(opt("--limit", 5)))
    text = to_markdown(c)
    if opt("--out"):
        Path(opt("--out")).write_text(text)
    print(json.dumps(c, indent=1) if "--json" in argv else text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
