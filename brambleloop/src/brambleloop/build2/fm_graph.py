"""F-452 / F-466: Final Master rows in the same dependency graph as Build 2.

The Build 2 graph (`executor.DEPENDENCIES` + `gate_for`) covers the 320 Build 2 requirements
only; the 917 Final Master rows lived in the closure snapshot with no edges, so a gate opening
un-parked Build 2 work and said nothing about the Final Master rows waiting on it, and the
critical path could not see them.

Nodes: every Final Master row the closure does not count COMPLETE (verdict recomputed by
`final_master.verdict`, never read from the label), named by uid (`F-123`). Edges:

* `gate:<key> -> F-x` for a GATED row (an explicit owner/data/external gate with a key) --
  the same `gate:` namespace the Build 2 graph uses, so one gate counts everything it holds;
* `F-y -> F-x` when the row's recorded next action names another unfinished row ("after
  F-037 ...", "see F-003") -- the closure matrix's own mapping, read from the shipped snapshot.

`fanout(db)` is F-466: for every gate that is open *now* (`executor.GATES`, checked live),
the Final Master rows still recorded as waiting on it -- work that can start. A gate key with
no live check is reported as `unevaluable`, never as open. Read-only.
"""
from __future__ import annotations

import re

_REF = re.compile(r"\bF-\d{3}\b")


def nodes_and_edges(snapshot: dict | None = None) -> dict:
    from . import final_master

    snap = snapshot if snapshot is not None else (final_master.load() or {})
    rows = {r["uid"]: r for r in snap.get("rows") or []}
    open_rows: dict[str, str] = {}
    for uid, r in rows.items():
        state = final_master.verdict(r)[0] if r.get("launch_class") == "LAUNCH-CRITICAL" \
            else ("COMPLETE" if r.get("completion") == "COMPLETE" else
                  r.get("completion") or "OPEN")
        if state != "COMPLETE" and r.get("completion") != "NOT-APPLICABLE":
            open_rows[uid] = state
    edges: list[tuple[str, str]] = []
    for uid in open_rows:
        r = rows[uid]
        g = r.get("gate") or {}
        if open_rows[uid] == "GATED" and g.get("key"):
            edges.append((f"gate:{g['key']}", uid))
        for ref in set(_REF.findall(str(r.get("next_action") or ""))) - {uid}:
            if ref in open_rows:
                edges.append((ref, uid))
    return {"nodes": open_rows, "edges": sorted(set(edges))}


def fanout(db, *, env=None, snapshot: dict | None = None) -> dict:
    from . import executor

    g = nodes_and_edges(snapshot)
    live = {gate.key: gate for gate in executor.GATES}
    waiting: dict[str, list[str]] = {}
    for a, b in g["edges"]:
        if a.startswith("gate:"):
            waiting.setdefault(a[5:], []).append(b)
    opened, closed, unevaluable = {}, {}, {}
    for key, uids in sorted(waiting.items()):
        if key not in live:
            unevaluable[key] = sorted(uids)
            continue
        try:
            is_open = bool(live[key].open(db, env))
        except Exception:  # noqa: BLE001 - an unreadable gate is closed, never open
            is_open = False
        (opened if is_open else closed)[key] = sorted(uids)
    return {"unblocked": opened, "still_gated": closed, "unevaluable": unevaluable,
            "unblocked_rows": sorted({u for v in opened.values() for u in v})}
