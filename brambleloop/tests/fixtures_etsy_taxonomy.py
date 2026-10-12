"""Recorded-shape responses for Etsy's two seller-taxonomy reads, for tests only.

Shaped exactly as Etsy's Open API v3 documents `getSellerTaxonomyNodes` (a `results` list of
SellerTaxonomyNode: id, level, name, parent_id, child_ids, full_path_taxonomy_ids, children)
and `getPropertiesByTaxonomyId` (a `results` list of TaxonomyNodeProperty: property_id, name,
display_name, scales, is_required, supports_attributes, supports_variations, is_multivalued,
max_values_allowed, possible_values, selected_values).

**The ids and names are illustrative, not Etsy's.** Nobody in this company has read the real
tree yet (that is what `listing.taxonomy_refresh` is for), so these are deliberately *not*
66 and deliberately include a node that only looks like a pattern node, a finished-goods
"Blankets" node outside the pattern subtree, and a deeper crochet child per object, so the
chooser is tested on structure rather than on remembered integers.
"""
from __future__ import annotations


def _node(nid, name, level, parent, children=()):
    kids = list(children)
    return {"id": nid, "level": level, "name": name, "parent_id": parent,
            "child_ids": [k["id"] for k in kids], "full_path_taxonomy_ids": [],
            "children": kids}


TREE = [
    _node(1000, "Home & Living", 0, None, [
        _node(1001, "Blankets & Throws", 1, 1000),     # finished goods, not a pattern
    ]),
    _node(2000, "Craft Supplies & Tools", 0, None, [
        _node(2100, "Patterns & How To", 1, 2000, [
            _node(2110, "Crochet", 2, 2100, [
                _node(2111, "Amigurumi & Toys", 3, 2110),
                _node(2112, "Blankets & Afghans", 3, 2110),
                _node(2113, "Home Decor", 3, 2110, [
                    _node(2114, "Coasters", 4, 2113),
                    _node(2115, "Baskets & Storage", 4, 2113),
                ]),
                _node(2116, "Holiday & Seasonal", 3, 2110),
            ]),
            _node(2120, "Knitting", 2, 2100),
        ]),
        _node(2200, "Yarn & Fiber", 1, 2000),
    ]),
]

NODES_RESPONSE = {"count": len(TREE), "results": TREE}


def _values(*names):
    return [{"value_id": 5000 + i, "name": n, "scale_id": None, "equal_to": []}
            for i, n in enumerate(names)]


COLOURS = ("Beige", "Black", "Blue", "Gold", "Gray", "Green", "Orange", "Pink", "Purple",
           "Red", "White", "Yellow")


def prop(pid, name, values=(), *, required=False, scales=()):
    return {"property_id": pid, "name": name, "display_name": name,
            "scales": list(scales), "is_required": required, "supports_attributes": True,
            "supports_variations": False, "is_multivalued": False,
            "max_values_allowed": None, "possible_values": _values(*values),
            "selected_values": []}


STANDARD_PROPERTIES = [
    prop(200, "Primary color", COLOURS),
    prop(52047899002, "Secondary color", COLOURS),
    prop(46803063641, "Holiday", ("Christmas", "Easter", "Halloween", "Thanksgiving",
                                  "Valentine's Day")),
    prop(46803063659, "Occasion", ("Birthday", "Wedding", "Mother's Day")),
    prop(3001, "Craft type", ("Crochet", "Knitting", "Sewing")),
    prop(3002, "Skill level", ("Beginner", "Intermediate", "Advanced")),
    prop(3003, "Recipient", ("Adults", "Babies", "Children")),
    prop(3004, "Subject", ("Animals", "Flowers", "Geometric")),
]


def properties_response(node_id: int) -> dict:
    results = list(STANDARD_PROPERTIES) if node_id != 2120 else []
    return {"count": len(results), "results": results}


class FakeResponse:
    def __init__(self, body):
        self.status = 200
        self.body = body


class RecordedTaxonomyClient:
    """Answers `_call` exactly as EtsyClient does, from the recorded responses above."""

    def __init__(self):
        self.calls: list[str] = []

    def _call(self, method, path, *, operation, authority=None, **_kw):
        self.calls.append(operation)
        if path == "/seller-taxonomy/nodes":
            return FakeResponse(NODES_RESPONSE)
        node = int(path.split("/")[3])
        return FakeResponse(properties_response(node))


def snapshot() -> dict:
    """The snapshot `etsy_taxonomy.refresh` would store from these responses, as `latest` returns it."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from brambleloop.integrations import etsy_taxonomy as T

    nodes = T.flatten(TREE)
    props = {str(n["id"]): properties_response(n["id"])["results"]
             for n in T.pattern_subtree(nodes)}
    return {"id": 1, "nodes": nodes, "properties": props, "sha256": "fixture",
            "fetched_at": "2026-09-28T00:00:00+00:00"}
