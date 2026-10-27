"""F-465: critical-path awareness over the Build 2 graph.

Nodes are the open requirements (not COVERED) and the gates they are parked on; an edge runs
from a prerequisite to what waits on it (`executor.DEPENDENCIES`, and gate -> requirement for
every requirement `gate_for` parks). For every node, `downstream` is the number of open
requirements that cannot finish until it does, and `chain` is the length of the longest
waiting chain behind it. The critical path is the longest chain; the ranking puts the work
(or the gate) that unblocks the most first, so spare capacity still goes to independent
work but the next session or owner decision shortens the path.

Read-only. `executor.queue` carries it beside READY work (`critical_path`), and
`ops/dispatch.py` cards can sort by `downstream`.
"""
from __future__ import annotations


def _work(n: str) -> bool:
    return n.startswith(("#", "F-"))


def graph(statuses: dict[int, str] | None = None, *, include_fm: bool = True,
          fm_snapshot: dict | None = None) -> dict:
    from . import executor
    from . import requirements as reg

    rows = reg.load()
    status = statuses or {r.id: r.status for r in rows}
    open_ = {rid for rid, st in status.items() if st != reg.COVERED}
    succ: dict[str, set[str]] = {}

    def edge(a: str, b: str) -> None:
        succ.setdefault(a, set()).add(b)
        succ.setdefault(b, set())

    for rid in open_:
        succ.setdefault(f"#{rid}", set())
        for dep in executor.DEPENDENCIES.get(rid, ()):
            if dep in open_:
                edge(f"#{dep}", f"#{rid}")
        gate = executor.gate_for(rid)
        if gate:
            edge(f"gate:{gate}", f"#{rid}")
    if include_fm:
        # F-452: the Final Master rows join the same graph (and the same gate namespace).
        from . import fm_graph

        fm = fm_graph.nodes_and_edges(fm_snapshot)
        for uid in fm["nodes"]:
            succ.setdefault(uid, set())
        for a, b in fm["edges"]:
            edge(a, b)
    return {"succ": succ, "open": open_}


def analyse(statuses: dict[int, str] | None = None, *, top: int = 10,
            include_fm: bool = True, fm_snapshot: dict | None = None) -> dict:
    g = graph(statuses, include_fm=include_fm, fm_snapshot=fm_snapshot)
    succ = g["succ"]
    chain: dict[str, int] = {}
    reach: dict[str, set[str]] = {}

    def visit(n: str, stack: frozenset = frozenset()) -> None:
        if n in chain:
            return
        if n in stack:
            raise ValueError(f"cycle through {n}")
        best, seen = 0, set()
        for m in succ.get(n, ()):
            visit(m, stack | {n})
            best = max(best, chain[m])
            seen |= reach[m] | ({m} if _work(m) else set())
        chain[n] = best + (1 if _work(n) else 0)
        reach[n] = seen

    for n in sorted(succ):
        visit(n)
    roots = [n for n in succ if not any(n in v for v in succ.values())]
    path, node = [], max(roots, key=lambda n: (chain[n], len(reach[n]), n), default=None)
    while node is not None:
        path.append(node)
        nxt = sorted(succ.get(node, ()), key=lambda m: (-chain[m], m))
        node = nxt[0] if nxt else None
    ranking = sorted(({"node": n, "downstream": len(reach[n]), "chain": chain[n]}
                      for n in succ), key=lambda r: (-r["downstream"], -r["chain"], r["node"]))
    return {"critical_path": path, "length": sum(1 for n in path if _work(n)),
            "ranking": ranking[:top],
            "gates_by_unblocked": sorted(({"gate": r["node"][5:], "unblocks": r["downstream"]}
                                          for r in ranking if r["node"].startswith("gate:")),
                                         key=lambda x: -x["unblocks"])[:top],
            "downstream": {n: len(reach[n]) for n in succ if _work(n)}}


MOVEMENT_EVENT = "critical_path"


def record_movement(db, *, analysis: dict | None = None) -> dict:
    """F-488: write a `critical_path` build event when the path's length or head changed."""
    from sqlalchemy import select

    from ..core.models import BuildEvent
    from . import executor

    cp = analysis or analyse()
    reading = {"length": cp["length"], "head": cp["critical_path"][:4],
               "top_gate": (cp["gates_by_unblocked"][0] if cp["gates_by_unblocked"] else None)}
    with db.session() as s:
        last = s.scalar(select(BuildEvent).where(BuildEvent.kind == MOVEMENT_EVENT)
                        .order_by(BuildEvent.id.desc()).limit(1))
        before = dict(last.detail or {}) if last else None
    if before is None or (before.get("length"), before.get("head")) != (reading["length"],
                                                                        reading["head"]):
        executor.record(db, kind=MOVEMENT_EVENT, actor="critical_path",
                        summary=f"critical path {reading['length']} step(s)", detail=reading)
    return reading


def movement(db) -> dict:
    """The newest critical-path reading against the one before it. UNMEASURED with none."""
    from sqlalchemy import select

    from ..core.models import BuildEvent

    with db.session() as s:
        rows = list(s.scalars(select(BuildEvent).where(BuildEvent.kind == MOVEMENT_EVENT)
                              .order_by(BuildEvent.id.desc()).limit(2)))
        rows = [(r.at, dict(r.detail or {})) for r in rows]
    if not rows:
        return {"state": "UNMEASURED", "why": "no critical-path reading recorded yet"}
    (at, now), prev = rows[0], (rows[1] if len(rows) > 1 else None)
    return {"state": "MEASURED", "length": now.get("length"), "head": now.get("head"),
            "top_gate": now.get("top_gate"), "at": at.isoformat() if at else None,
            "previous": prev[1].get("length") if prev else None,
            "previous_at": prev[0].isoformat() if prev and prev[0] else None,
            "delta": (now.get("length") - prev[1].get("length"))
            if prev and isinstance(prev[1].get("length"), int) else None}
