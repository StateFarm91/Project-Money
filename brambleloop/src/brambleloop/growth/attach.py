"""Cross-sell attach rate, optimised without misleading (F-775) -- W4-C10.

"Every product records legitimate related products, bundles, collections, tutorials, materials
and next-project recommendations. Agents optimize attach rate without misleading customers."

The graph half is `commerce.cross_sell.graph` (certified products only; tutorials are approved
lessons; materials are the CIR's own). This is the optimisation half it left UNMEASURED:

* `attach_rates(graph, orders)` -- for each buyer-facing edge (related, bundles, next projects
  in the catalogue) and each tutorial link, the share of buyers of the source who also bought
  (or, for a tutorial, opened) the target within `WINDOW_DAYS`. Below `MIN_SOURCE_BUYERS`
  buyers of the source it is UNMEASURED, never 0;
* `rank(graph, rates)` -- orders each product's recommendations by measured attach rate,
  unmeasured edges after measured ones (in graph order). It can only reorder edges the graph
  holds: optimisation never invents a recommendation;
* `check_copy(text, edge)` -- recommendation wording may not mislead: no claim that the item
  is required or needed to finish, no "matching"/"set" claim without a recorded collection or
  bundle edge, no invented urgency or scarcity, no "customers also bought" without a measured
  attach rate.
"""
from __future__ import annotations

import re
from datetime import timedelta

UNMEASURED = "UNMEASURED"
WINDOW_DAYS = 30
MIN_SOURCE_BUYERS = 20
EDGE_KINDS = ("related", "bundles", "next_projects", "tutorials")

_REQUIRED = re.compile(r"\b(required|you('ll| will)? need|needed to (finish|complete)|"
                       r"must (have|buy)|don'?t forget)\b", re.I)
_SET = re.compile(r"\b(matching|complete the set|goes with|pairs with)\b", re.I)
_URGENCY = re.compile(r"\b(only \d+ left|selling fast|last chance|ends (today|soon)|"
                      r"limited time|hurry)\b", re.I)
_SOCIAL = re.compile(r"\b(customers (also )?bought|people also bought|popular with|"
                     r"best ?seller)\b", re.I)


def _edges(node) -> list[tuple[str, str]]:
    out = [("related", t) for t in node.get("related") or []]
    out += [("bundles", t) for t in node.get("bundles") or []]
    out += [("next_projects", t) for t in (node.get("next_projects") or {}).get("in_catalogue",
                                                                              [])]
    tut = node.get("tutorials")
    if isinstance(tut, list):
        out += [("tutorials", t) for t in tut]
    return out


def attach_rates(graph: dict, orders, *, tutorial_opens=()) -> dict:
    """`orders`: [{buyer, product, at}]; `tutorial_opens`: [{buyer, lesson, at}]."""
    bought: dict[str, list[tuple[str, object]]] = {}
    for o in orders or ():
        bought.setdefault(o["product"], []).append((o["buyer"], o["at"]))
    later: dict[tuple[str, str], list] = {}
    for o in orders or ():
        later.setdefault((o["buyer"], o["product"]), []).append(o["at"])
    for t in tutorial_opens or ():
        later.setdefault((t["buyer"], f"lesson:{t['lesson']}"), []).append(t["at"])
    window = timedelta(days=WINDOW_DAYS)
    rates = {}
    for node in graph.get("nodes") or []:
        src = node["product"]
        buyers = {}
        for b, at in bought.get(src, []):
            buyers[b] = min(at, buyers.get(b, at))
        for kind, tgt in _edges(node):
            key = tgt if kind != "tutorials" else f"lesson:{tgt}"
            if len(buyers) < MIN_SOURCE_BUYERS:
                rates[(src, kind, tgt)] = {"rate": UNMEASURED, "buyers": len(buyers),
                                           "why": f"{len(buyers)} of {MIN_SOURCE_BUYERS} "
                                                  f"buyers of {src}"}
                continue
            hit = sum(1 for b, first in buyers.items()
                      if any(first <= at <= first + window for at in later.get((b, key), [])))
            rates[(src, kind, tgt)] = {"rate": round(hit / len(buyers), 4),
                                       "buyers": len(buyers), "attached": hit}
    return rates


def rank(graph: dict, rates: dict) -> dict:
    out = {}
    for node in graph.get("nodes") or []:
        edges = _edges(node)
        order = {e: i for i, e in enumerate(edges)}

        def key(e):
            r = rates.get((node["product"], *e), {}).get("rate", UNMEASURED)
            return (0, -r, order[e]) if r != UNMEASURED else (1, 0, order[e])

        out[node["product"]] = [{"kind": k, "target": t,
                                 "rate": rates.get((node["product"], k, t), {})
                                 .get("rate", UNMEASURED)}
                                for k, t in sorted(edges, key=key)]
    return {"recommendations": out,
            "rule": "only edges the graph holds are ranked; none is added"}


def check_copy(text: str, edge: dict) -> list[str]:
    """`edge`: {kind, rate}. Problems with recommendation wording; [] when honest."""
    t = str(text or "")
    out = []
    if _REQUIRED.search(t):
        out.append("claims the item is required: a recommendation is optional")
    if _SET.search(t) and edge.get("kind") not in ("bundles", "related"):
        out.append("claims a matching set without a recorded bundle or family edge")
    if _URGENCY.search(t):
        out.append("invents urgency or scarcity: digital patterns do not run out")
    if _SOCIAL.search(t) and not isinstance(edge.get("rate"), float):
        out.append("claims buyers' behaviour without a measured attach rate")
    return out
