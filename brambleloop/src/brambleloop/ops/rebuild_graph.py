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

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

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


# `jobs.idempotency_key` is VARCHAR(200) (core/models.py). A key built from every moved ref
# outgrows it as soon as a deploy moves many code fingerprints at once: on Postgres the insert
# then fails with StringDataRightTruncation and the sentinel dead-letters every hour
# (production 0417f35, 2026-10-11, W4-FMGATE). SQLite does not enforce the length, so only
# Postgres ever saw it.
IDEMPOTENCY_KEY_MAX = 200


def job_key(prefix: str, stamp: str) -> str:
    """`prefix:stamp`, or -- when that would not fit the column -- `prefix:sha256=<digest of
    stamp>`. Deterministic in the change, so the idempotency property is unchanged: the same
    change still enqueues once and a different change enqueues again."""
    key = f"{prefix}:{stamp}"
    if len(key) <= IDEMPOTENCY_KEY_MAX:
        return key
    digest = hashlib.sha256(stamp.encode()).hexdigest()
    key = f"{prefix}:sha256={digest}"
    if len(key) <= IDEMPOTENCY_KEY_MAX:
        return key
    return "rebuild:sha256=" + hashlib.sha256(f"{prefix}\0{stamp}".encode()).hexdigest()


def _bounded_key(prefix: str, stamp: str) -> str:
    """W4-FINHEALTH's spelling of the same fix (prefix carries its trailing ':'); one
    implementation, `job_key`, so both lanes' regression tests hold the same keys."""
    return job_key(prefix[:-1] if prefix.endswith(":") else prefix, stamp)


# How long after the last terminal attempt for a product the same change may be asked for
# again. Long enough that a verify cycle (3 x 20 min) has finished; one retry per UTC day.
RETRY_AFTER = timedelta(hours=12)


def _recent_rebuild_slugs(db, now: datetime) -> set[str]:
    """Products with a chain.rebuild in flight, or one that ended inside RETRY_AFTER.

    Review F6: one bounded query per sentinel run (in-flight rows plus rows touched inside the
    window), never every chain.rebuild ever written once per product."""
    from sqlalchemy import or_, select

    from ..core.models import Job, JobStatus

    since = now - RETRY_AFTER
    rows = db.execute(select(Job.inputs).where(
        Job.job_type == "chain.rebuild",
        or_(Job.status.in_((JobStatus.PENDING, JobStatus.RUNNING, JobStatus.FAILED)),
            Job.finished_at >= since,
            Job.finished_at.is_(None) & (Job.created_at >= since))))
    return {str((inputs or {}).get("product_slug") or "") for (inputs,) in rows}


def _retry_key(db, slug: str, key: str, *, now: datetime | None = None,
               recent: set[str] | None = None) -> str | None:
    """A fresh daily key when no chain.rebuild for `slug` is in flight and none ended inside
    RETRY_AFTER; otherwise None (the existing attempt stands)."""
    now = now or datetime.now(timezone.utc)
    if recent is None:
        recent = _recent_rebuild_slugs(db, now)
    if slug in recent:
        return None
    return job_key(f"{key}:retry", now.date().isoformat())


def enqueue(db, queue, *, changed: dict[str, str], reason: str,
            expected: list[tuple[str, str, str]] | None = None,
            per: str = "artefact", previous: dict[str, str] | None = None,
            now: datetime | None = None, hold=None) -> dict:
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
    if per == "product":
        # One job per product carrying that product's exact descendants in order. The chain
        # stage it drives rebuilds a whole product, so a job per artefact would run that
        # stage once per artefact for one change -- same result, many times the work. The
        # key still carries the new fingerprints, so the idempotency property is unchanged.
        by_product: dict[str, list[dict]] = {}
        for row in plan["rebuild"]:
            by_product.setdefault(row["product_slug"], []).append(row)
        retried: list[str] = []
        held: dict[str, str] = {}
        recent: set[str] | None = None
        for slug, rows in sorted(by_product.items()):
            key = job_key(f"rebuild:product:{slug}", stamp)
            payload = {"product_slug": slug,
                       "artefacts": [r["key"] for r in rows],
                       "reason": reason, "changed": plan["changed"],
                       "fingerprints": {
                           ref: {"old": (previous or {}).get(ref), "new": fp}
                           for ref, fp in sorted(changed.items())}}
            try:
                queue.enqueue("listing", "chain.rebuild", payload, idempotency_key=key)
                enqueued.extend(r["key"] for r in rows)
            except DuplicateJob:
                # W4-PRODFIX: the key names the change, so an attempt that ended without
                # delivering it (refused downstream, rebuild-incomplete) held the key for
                # good and the artefacts were never asked for again -- production 051dbee2
                # had 299 stale artefacts and no rebuild for days. Once the last attempt
                # for this product is terminal and old enough, ask again, once a day.
                if recent is None:
                    recent = _recent_rebuild_slugs(db, now or datetime.now(timezone.utc))
                again = _retry_key(db, slug, key, now=now, recent=recent)
                # INTEG7 (review S-2): no daily retry while an owner- or policy-gated reason
                # refuses this product's rebuild; it resumes when the gate clears.
                held_why = hold(slug) if (again and hold is not None) else None
                if held_why:
                    held[slug] = held_why
                    already.extend(r["key"] for r in rows)
                    continue
                if again:
                    try:
                        queue.enqueue("listing", "chain.rebuild",
                                      {**payload, "retry_of_key": key, "retry": again},
                                      idempotency_key=again)
                        enqueued.extend(r["key"] for r in rows)
                        retried.append(slug)
                        continue
                    except DuplicateJob:
                        pass
                already.extend(r["key"] for r in rows)
        return {"enqueued": enqueued, "already_queued": already, "retried": retried,
                "retry_held": held,
                "plan": plan, "reason": reason, "per": per,
                "idempotency": ("keyed on the product and the new fingerprint, so the same "
                                "change enqueues once and a different change enqueues again")}

    for row in plan["rebuild"]:
        key = job_key(f"rebuild:{row['key']}", stamp)
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


def publication_gate(db, *, slug: str, current: dict[str, str] | None = None) -> dict:
    """#172 at the publish path: may this product publish, given what has moved upstream?

    `changed` is every upstream reference a recorded artefact of this product was built from
    that has since moved (old and new fingerprint kept); `rebuilt` is every node whose
    upstreams all match now, which is the completion evidence -- a descendant is rebuilt
    when its provenance row says it was made from the current input, not when a job said so.
    """
    from .artefacts import FRESH, STALE, current_from_db

    current = current if current is not None else current_from_db(db)
    verdicts = check(db, current=current)
    changed: dict[str, str] = {}
    previous: dict[str, str] = {}
    from sqlalchemy import select

    from ..core.models import ArtefactProvenance

    recorded = {(r.artefact_class, r.artefact_key): (r.inputs or {}, r.built_at)
                for r in db.scalars(select(ArtefactProvenance)
                                    .where(ArtefactProvenance.product_slug == slug))}
    for v in verdicts:
        if v.product_slug != slug or v.state != STALE:
            continue
        inputs = recorded.get((v.artefact_class, v.artefact_key), ({}, None))[0]
        for ref in v.moved:
            if ref in current:
                changed[ref] = current[ref]
                previous[ref] = inputs.get(ref)
    rebuilt = {_node_key(v.artefact_class, v.artefact_key) for v in verdicts
               if v.state == FRESH}
    unprovable = sorted(_node_key(v.artefact_class, v.artefact_key) for v in verdicts
                        if v.product_slug == slug and v.state == STALE and v.unknown
                        and not v.moved)
    verdict = (blocks_publication(db, changed=changed, rebuilt=rebuilt) if changed
               else {"may_publish": True, "outstanding": [], "why": "nothing upstream moved"})
    nodes = load_graph(db)["nodes"]
    outstanding = [k for k in verdict["outstanding"]
                   if k in nodes and nodes[k].product_slug == slug]
    evidence = [{"key": _node_key(c, k), "built_at": str(built)}
                for (c, k), (_, built) in sorted(recorded.items())
                if _node_key(c, k) in rebuilt]
    return {
        "slug": slug, "may_publish": not outstanding, "outstanding": outstanding,
        "changed": {ref: {"old": previous.get(ref), "new": fp}
                    for ref, fp in sorted(changed.items())},
        "rebuilt_evidence": evidence[:40],
        # Reported, not blocking here: an upstream with no current fingerprint is the
        # sentinel's to raise (it halts through the incident flag the publish path reads).
        "unprovable": unprovable,
        "why": (f"{len(outstanding)} descendant(s) of this product still carry the old "
                f"input: {outstanding[:5]}" if outstanding else verdict["why"]),
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
