"""W4-PRODREADY B2: when the real tree yields no crochet-pattern subtree, the refresh records
what the tree DOES name, so the matcher can be corrected from Etsy's own names.

Production 1b21e81 reads the seller taxonomy daily with the app keystring (3065 nodes,
credential not refused, gate open) and `pattern_subtree` finds 0 nodes, so every category is
UNKNOWN and search certification refuses. Until now the audit row said only that.

Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_w4_prodready_taxonomy.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import fixtures_etsy_taxonomy as FX  # noqa: E402
from brambleloop.integrations import etsy_taxonomy as T  # noqa: E402


def _tree_without_a_crochet_node():
    # Patterns filed by object, the technique not a node: the shape that yields 0 matches.
    return [FX._node(1, "Craft Supplies & Tools", 0, None, [
        FX._node(2, "Patterns & How To", 1, 1, [
            FX._node(3, "Blankets & Throws", 2, 2),
            FX._node(4, "Home & Living", 2, 2),
        ]),
    ]), FX._node(5, "Home & Living", 0, None, [FX._node(6, "Baskets", 1, 5)])]


def test_no_subtree_records_the_pattern_and_crochet_names_the_tree_has():
    nodes = T.flatten(_tree_without_a_crochet_node())
    assert len(nodes) == 6
    assert T.pattern_subtree(nodes) == []
    ev = T.name_evidence(nodes)
    assert ev["pattern_named"] == ["Craft Supplies & Tools > Patterns & How To"], ev
    assert ev["crochet_named"] == [], ev
    assert ev["pattern_node_children"] == [{
        "path": "Craft Supplies & Tools > Patterns & How To",
        "children": ["Blankets & Throws", "Home & Living"]}], ev


def test_the_fixture_tree_still_matches_and_evidence_is_bounded():
    nodes = T.flatten(FX.TREE)
    assert T.pattern_subtree(nodes), "the illustrative tree has a crochet pattern node"
    ev = T.name_evidence(nodes)
    assert any("Crochet" in p for p in ev["crochet_named"]), ev
    big = [{"id": i, "name": f"Pattern {i}", "path_names": [f"Pattern {i}"],
            "parent_id": None} for i in range(200)]
    ev = T.name_evidence(big)
    assert len(ev["pattern_named"]) == T.NAME_EVIDENCE_MAX
    assert len(ev["pattern_node_children"]) == T.NAME_EVIDENCE_MAX


def test_refresh_puts_the_evidence_on_the_audit_when_nothing_matches():
    import inspect

    from brambleloop.runtime import release

    src = inspect.getsource(release.handle_taxonomy_refresh)
    assert '"name_evidence"' in src, "the handler drops the evidence from its audit summary"
    src = inspect.getsource(T.refresh)
    assert "name_evidence(nodes) if not subtree" in src


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
