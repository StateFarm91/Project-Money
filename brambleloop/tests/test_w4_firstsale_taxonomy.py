"""W4-FIRSTSALE B2: the category matcher for the tree production actually reads.

Production read Etsy's real seller taxonomy daily (3065 nodes) and found no node whose path
names both a pattern and crochet, so every category was UNKNOWN. Etsy documents per-node
property schemas (getPropertiesByTaxonomyId), so a pattern node may carry the technique as a
property value. The matcher may now choose a pattern-named node, but only when Etsy's own stored
schema for exactly that node offers "Crochet". Ids and paths come only from the snapshot.

Every tree here is ILLUSTRATIVE (ids are not Etsy's). The live verification against the real
audit row is `tests/verify_w4_firstsale_taxonomy_live.py`.

Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_w4_firstsale_taxonomy.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import fixtures_etsy_taxonomy as FX  # noqa: E402
from brambleloop.commerce import category as C  # noqa: E402
from brambleloop.integrations import etsy_taxonomy as T  # noqa: E402

N = FX._node


def _tree():
    """Crochet is not a node: patterns are filed by object under one pattern root."""
    return [
        N(10, "Home & Living", 0, None, [N(11, "Baskets", 1, 10)]),
        N(20, "Craft Supplies & Tools", 0, None, [
            N(21, "Patterns & How To", 1, 20, [
                N(22, "Patterns & Blueprints", 2, 21, [
                    N(23, "Blanket Patterns", 3, 22),
                    N(24, "Home Decor Patterns", 3, 22),
                ]),
                N(25, "Knitting Patterns", 2, 21),
                N(26, "Tutorials", 2, 21),
            ]),
        ]),
    ]


CRAFT = FX.prop(9001, "Craft type", ("Crochet", "Knitting", "Sewing"))
NO_CROCHET = FX.prop(9001, "Craft type", ("Knitting", "Sewing"))


def _snap(props_for=None, tree=None):
    nodes = T.flatten(tree or _tree())
    return {"id": 7, "nodes": nodes,
            "properties": {str(k): v for k, v in (props_for or {}).items()}}


def test_property_route_chooses_the_exact_node_and_records_etsys_ids():
    snap = _snap({22: [CRAFT], 23: [CRAFT, FX.STANDARD_PROPERTIES[0]], 24: [CRAFT]})
    ch = C.choose(snap, "blanket")
    assert ch.status == C.CHOSEN, ch
    assert ch.taxonomy_id == 23 and ch.path_ids == [20, 21, 22, 23], ch
    assert ch.path_names[-1] == "Blanket Patterns"
    assert ch.crochet_basis == {"via": "property", "property_id": 9001,
                                "property": "Craft type", "value_id": 5000,
                                "value": "Crochet"}, ch.crochet_basis
    # basket: no child names the object; the family rule ("home") picks the home decor node
    b = C.choose(snap, "basket")
    assert b.status == C.CHOSEN and b.taxonomy_id == 24, b
    # ornament: neither object nor family -- the deepest generic pattern node above
    o = C.choose(snap, "ornament")
    assert o.status == C.CHOSEN and o.taxonomy_id == 22, o
    # the property that makes it crochet is SET to Etsy's own value id
    props = C.properties_for(snap, ch, C.Facts("blanket", "beginner", [("cream", None)]))
    craft = [d for d in props["decisions"] if d["property_id"] == 9001][0]
    assert craft["status"] == C.SET and craft["value_ids"] == [5000], craft


def test_no_stored_schema_or_no_crochet_value_is_unknown_never_chosen():
    ch = C.choose(_snap({}), "blanket")
    assert ch.status == C.UNKNOWN and ch.taxonomy_id is None
    assert "no stored property schema" in ch.why
    ch = C.choose(_snap({23: [NO_CROCHET]}), "blanket")
    assert ch.status == C.UNKNOWN and "offers no 'Crochet'" in ch.why, ch.why
    # a schema on a DIFFERENT node does not confirm this one
    ch = C.choose(_snap({24: [CRAFT]}), "blanket")
    assert ch.status == C.UNKNOWN


def test_another_crafts_pattern_root_is_never_a_crochet_root():
    tree = [N(30, "Craft Supplies & Tools", 0, None, [
        N(31, "Knitting Patterns", 1, 30, [N(32, "Blanket Knitting Patterns", 2, 31)])])]
    snap = _snap({31: [CRAFT], 32: [CRAFT]}, tree)
    assert C.pattern_roots(snap) == []
    assert C.choose(snap, "blanket").status == C.UNKNOWN
    # and under a generic root, a knitting child is never descended into
    snap = _snap({21: [CRAFT], 22: [CRAFT], 25: [CRAFT]})
    assert C.choose(snap, "blanket").taxonomy_id != 25


def test_ambiguous_pattern_roots_are_refused_unless_one_is_under_craft_supplies():
    tree = [N(40, "Home & Living", 0, None, [N(41, "Stencil Patterns", 1, 40)]),
            N(50, "Art & Collectibles", 0, None, [N(51, "Pattern Prints", 1, 50)])]
    snap = _snap({41: [CRAFT], 51: [CRAFT]}, tree)
    root, why = C.pattern_root(snap)
    assert root is None and "several unrelated pattern roots" in why
    assert C.choose(snap, "blanket").status == C.UNKNOWN
    tree.append(N(60, "Craft Supplies & Tools", 0, None, [N(61, "Patterns & How To", 1, 60)]))
    root, _ = C.pattern_root(_snap({}, tree))
    assert root["id"] == 61


def test_path_route_is_unchanged_on_the_illustrative_crochet_tree():
    snap = FX.snapshot()
    ch = C.choose(snap, "basket")
    assert ch.taxonomy_id == 2115 and ch.crochet_basis == {"via": "path"}, ch
    assert C.choose(snap, "blanket").taxonomy_id == 2112


def test_refresh_reads_the_candidate_schemas_and_records_the_choices():
    from brambleloop.agents.registry import Registry
    from brambleloop.core.db import Database
    from brambleloop.core.models import AuditLog

    db = Database(f"sqlite:///{tempfile.mkdtemp()}/tax.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    with db.session() as s:
        s.add(AuditLog(actor="market_radar", action="etsy.probe", artifact="fixture",
                       detail={"ok": True, "application_id": "fixture"}))

    class Client:
        def __init__(self):
            self.calls = []

        def _call(self, method, path, *, operation, authority=None, **_kw):
            assert method == "GET"
            self.calls.append(path)
            if path == "/seller-taxonomy/nodes":
                return FX.FakeResponse({"count": 2, "results": _tree()})
            nid = int(path.split("/")[3])
            return FX.FakeResponse({"results": [CRAFT] if nid in (21, 22, 23, 24) else []})

    client = Client()
    T.client_factory = lambda _db: client
    try:
        out = T.refresh(db)
    finally:
        T.client_factory = None
    assert out["ran"] and out["pattern_subtree"] == 0, out
    read = sorted(int(p.split("/")[3]) for p in client.calls[1:])
    assert 25 not in read and 11 not in read, read          # never knitting, never goods
    assert {21, 22, 23}.issubset(read), read
    assert out["network_calls"] == 1 + len(read) <= 1 + T.MAX_PROPERTY_READS
    choices = out["category_choices"]
    assert choices["blanket"]["status"] == C.CHOSEN
    assert choices["blanket"]["taxonomy_id"] == 23
    assert choices["blanket"]["path_ids"] == [20, 21, 22, 23]
    assert out["name_evidence"]["pattern_named"]
    # the stored snapshot gives the same answer the audit row reports
    assert C.choose(T.latest(db), "blanket").taxonomy_id == 23
    from brambleloop.runtime import release
    import inspect

    assert '"category_choices"' in inspect.getsource(release.handle_taxonomy_refresh)


def test_the_live_verifiers_own_rules_hold_offline():
    """INTEG4: the live production verifier (`tests/verify_w4_firstsale_taxonomy_live.py`) is
    an operator step outside the hermetic suite (its answer depends on production and exits 3
    while UNKNOWN). Its rules -- CHOSEN must end at its id, carry a crochet basis, and a
    contradiction is CONTRADICTED -- are checked here, offline, with no network."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "verify_w4_firstsale_taxonomy_live",
        Path(__file__).resolve().parent / "verify_w4_firstsale_taxonomy_live.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod._self_test()


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    assert tests
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"OK   {name}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {name}: {type(exc).__name__}: {exc}"[:1500])
    print(f"{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
