"""The rebuild set, and the part of the estate the graph cannot see.

Requirement 172. An explicit dependency graph per product; when a node changes, compute the
exact downstream rebuild set, enqueue it idempotently, and block publication until every
required descendant has been rebuilt and re-certified -- storing old and new fingerprints,
the reason, the time, and the evidence that it completed.

The graph is not invented here. `ops.artefacts` already records what every artefact was made
from, and this reads those edges rather than maintaining a second opinion about them: a
dependency graph kept beside the provenance would be a second answer to "what does this
depend on", and the two would agree until the day it mattered.

What this adds is direction and closure. Provenance answers *what was this made from*; a
rebuild needs *what must now be remade*, which is the same edges followed the other way, and
transitively -- a listing built from a PDF built from a design is two hops from the design
and nobody rebuilds it by hand. And it needs an order: rebuilding the listing before the PDF
regenerates it from the stale one, which is worse than not rebuilding it, because afterwards
everything claims to be current.

**The number that matters is the one the graph cannot see.** Today the production estate
holds 275 derived artefacts and not one carries a provenance row, so a propagation over the
recorded graph would touch nothing and report that no rebuild is needed. That is a true
statement about the graph and a false one about the shop. So every plan reports its coverage,
and a plan that covers a small share of the estate says so on the same line as its rebuild
set -- because the rebuild set is the part people read.

**A cycle is refused rather than traversed.** A rebuild graph with a cycle is a rebuild that
does not terminate, and the shape it takes in practice is two artefacts each recorded as an
input to the other by a caller who meant "these go together".
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .artefacts import ARTEFACT_CLASSES, UNPROVEN, check


class GraphRefused(ValueError):
    """A cycle, or a node nobody recorded."""


@dataclass
class Node:
    """One artefact in the graph, with the refs it was built from."""

    key: str                       # "class:artefact_key"
    artefact_class: str
    artefact_key: str
    product_slug: str
    inputs: dict[str, str] = field(default_factory=dict)


def _node_key(artefact_class: str, artefact_key: str) -> str:
    return f"{artefact_class}:{artefact_key}"


def load_graph(db) -> dict:
    """Read the edges from the provenance rows rather than keeping a second copy."""
    from sqlalchemy import select

    from ..core.models import ArtefactProvenance

    nodes: dict[str, Node] = {}
    for row in db.scalars(select(ArtefactProvenance)):
        key = _node_key(row.artefact_class, row.artefact_key)
        nodes[key] = Node(key=key, artefact_class=row.artefact_class,
                          artefact_key=row.artefact_key, product_slug=row.product_slug,
                          inputs=dict(row.inputs or {}))

    # An artefact may be an input to another one: "asset:hex-coaster.pdf" refers to a node if
    # something recorded that artefact. Edges to refs nobody recorded are upstreams outside
    # the graph -- a design, a policy snapshot -- and are kept as such rather than dropped.
    by_ref: dict[str, str] = {}
    for key, node in nodes.items():
        by_ref[f"asset:{node.artefact_key}"] = key

    children: dict[str, set[str]] = {k: set() for k in nodes}
    external: set[str] = set()
    for key, node in nodes.items():
        for ref in node.inputs:
            parent = by_ref.get(ref)
            if parent is None:
                external.add(ref)
            elif parent != key:
                children[parent].add(key)

    _refuse_cycles(children)
    return {"nodes": nodes, "children": children, "external_refs": sorted(external)}


def _refuse_cycles(children: dict[str, set[str]]) -> None:
    colour: dict[str, int] = {}

    def visit(key: str, path: list[str]) -> None:
        state = colour.get(key, 0)
        if state == 1:
            cycle = path[path.index(key):] + [key]
            raise GraphRefused(
                f"a cycle: {' -> '.join(cycle)}. A rebuild graph with a cycle is a rebuild "
                f"that does not terminate, and in practice it is two artefacts each recorded "
                f"as an input to the other by somebody who meant 'these go together'")
        if state == 2:
            return
        colour[key] = 1
        for child in sorted(children.get(key, ())):
            visit(child, path + [key])
        colour[key] = 2

    for key in sorted(children):
        visit(key, [])


def rebuild_set(db, *, changed: dict[str, str],
                expected: list[tuple[str, str, str]] | None = None) -> dict:
    """Everything that must be remade because these refs moved, in the order to remake it.

    `changed` maps an upstream reference to its new fingerprint. The order is topological:
    rebuilding a listing before the PDF it quotes regenerates it from the stale one, which is
    worse than not rebuilding it, because afterwards everything claims to be current.
    """
    graph = load_graph(db)
    nodes, children = graph["nodes"], graph["children"]

    seeds = {key for key, node in nodes.items()
             if any(ref in changed for ref in node.inputs)}

    affected: set[str] = set()
    frontier = list(seeds)
    while frontier:
        key = frontier.pop()
        if key in affected:
            continue
        affected.add(key)
        frontier.extend(children.get(key, ()))

    order = _topological(affected, children)

    # Coverage: the rebuild set is the part people read, so what the graph cannot see is
    # reported on the same line rather than in a separate report nobody opens.
    unseen = 0
    if expected is not None:
        unseen = sum(1 for v in check(db, current={}, expected=expected)
                     if v.state == UNPROVEN)
    total = len(nodes) + unseen

    return {
        "changed": sorted(changed),
        "rebuild": [{"key": k, "artefact_class": nodes[k].artefact_class,
                     "artefact_key": nodes[k].artefact_key,
                     "product_slug": nodes[k].product_slug} for k in order],
        "count": len(order),
        "seeds": sorted(seeds),
        "coverage": {
            "in_graph": len(nodes),
            "not_in_graph": unseen,
            "share": round(len(nodes) / total, 3) if total else None,
        },
        "why": (f"{len(order)} artefact(s) descend from {sorted(changed)}"
                + (f", out of an estate where {unseen} artefact(s) carry no provenance at "
                   f"all -- a propagation over the recorded graph cannot reach them, and "
                   f"reports that no rebuild is needed, which is true of the graph and false "
                   f"of the shop" if unseen else "")),
        "order_note": ("topological: a listing rebuilt before the PDF it quotes is "
                       "regenerated from the stale one, and afterwards everything claims to "
                       "be current"),
    }


def _topological(keys: set[str], children: dict[str, set[str]]) -> list[str]:
    """Parents before children, deterministically."""
    inside = set(keys)
    indegree = {k: 0 for k in inside}
    for key in inside:
        for child in children.get(key, ()):
            if child in inside:
                indegree[child] += 1
    ready = sorted(k for k, n in indegree.items() if n == 0)
    order: list[str] = []
    while ready:
        key = ready.pop(0)
        order.append(key)
        for child in sorted(children.get(key, ())):
            if child not in inside:
                continue
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
                ready.sort()
    return order


def enqueue(db, queue, *, changed: dict[str, str], reason: str,
            expected: list[tuple[str, str, str]] | None = None) -> dict:
    """Enqueue the rebuild set idempotently, keyed on what moved.

    The key carries the new fingerprint, so the same change enqueues once however many times
    this is called, and a *different* change enqueues again -- which is the distinction a
    key on the slug alone loses, and the reason a re-engineered product could once never
    re-enter the chain.
    """
    from ..queue.durable import DuplicateJob

    plan = rebuild_set(db, changed=changed, expected=expected)
    stamp = "-".join(f"{ref}={fp[:8]}" for ref, fp in sorted(changed.items()))

    enqueued, already = [], []
    for row in plan["rebuild"]:
        key = f"rebuild:{row['key']}:{stamp}"
        try:
            queue.enqueue("listing", "chain.rebuild",
                          {"product_slug": row["product_slug"],
                           "artefact_class": row["artefact_class"],
                           "artefact_key": row["artefact_key"],
                           "reason": reason, "changed": plan["changed"]},
                          idempotency_key=key)
            enqueued.append(row["key"])
        except DuplicateJob:
            already.append(row["key"])

    return {"enqueued": enqueued, "already_queued": already,
            "plan": plan, "reason": reason,
            "idempotency": ("keyed on the new fingerprint, so the same change enqueues once "
                            "and a different change enqueues again")}


def blocks_publication(db, *, changed: dict[str, str], rebuilt: set[str]) -> dict:
    """Whether publication may proceed, which it may not until every descendant is remade."""
    plan = rebuild_set(db, changed=changed)
    outstanding = [row["key"] for row in plan["rebuild"] if row["key"] not in rebuilt]
    return {
        "may_publish": not outstanding,
        "outstanding": outstanding,
        "why": ("every descendant has been rebuilt" if not outstanding else
                f"{len(outstanding)} descendant(s) still carry the old input. Publishing now "
                f"ships a set that is partly current, which is harder to find than one that "
                f"is wholly stale"),
    }


def state() -> dict:
    """Where the edges come from, and what the graph does not cover."""
    return {
        "edges_from": ("ops.artefacts' provenance rows. A dependency graph kept beside them "
                       "would be a second answer to what an artefact depends on, and the two "
                       "would agree until the day it mattered"),
        "artefact_classes": sorted(ARTEFACT_CLASSES),
        "order": "topological, parents before children",
        "refuses": ["a cycle, which is a rebuild that does not terminate"],
        "note": ("The number that matters is the one the graph cannot see: an estate whose "
                 "artefacts carry no provenance produces a propagation that touches nothing "
                 "and reports that no rebuild is needed -- true of the graph, false of the "
                 "shop (#172)."),
    }
