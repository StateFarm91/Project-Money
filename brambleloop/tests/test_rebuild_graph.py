"""#172: the rebuild set, and the part of the estate the graph cannot see.

The number that matters is the coverage. Production holds 275 derived artefacts and not one
carries a provenance row, so a propagation over the recorded graph touches nothing and
reports that no rebuild is needed -- true of the graph, false of the shop.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.ops import artefacts as A, rebuild_graph as G  # noqa: E402

DESIGN = A.fingerprint({"rows": 12})
MOVED = A.fingerprint({"rows": 14})
PDF = A.fingerprint("pdf-v1")


def _db(chain=True):
    db = Database("sqlite://")
    db.create_all()
    with db.session() as s:
        A.record(s, artefact_class="pdf", artefact_key="hex.pdf", product_slug="hex",
                 inputs={"cir:hex": DESIGN})
        if chain:
            A.record(s, artefact_class="listing_copy", artefact_key="hex@1",
                     product_slug="hex",
                     inputs={"asset:hex.pdf": PDF, "cir:hex": DESIGN})
    return db


# --- direction and closure ------------------------------------------------------------------

def test_a_change_reaches_two_hops_downstream():
    """A listing built from a PDF built from a design is two hops away, and nobody rebuilds
    it by hand."""
    with _db().session() as s:
        plan = G.rebuild_set(s, changed={"cir:hex": MOVED})
    assert [r["key"] for r in plan["rebuild"]] == ["pdf:hex.pdf", "listing_copy:hex@1"]
    assert plan["count"] == 2


def test_the_order_is_parents_before_children():
    """Rebuilding the listing before the PDF regenerates it from the stale one, and
    afterwards everything claims to be current."""
    with _db().session() as s:
        plan = G.rebuild_set(s, changed={"cir:hex": MOVED})
    keys = [r["key"] for r in plan["rebuild"]]
    assert keys.index("pdf:hex.pdf") < keys.index("listing_copy:hex@1")
    assert "claims to be current" in plan["order_note"]


def test_an_unrelated_change_rebuilds_nothing():
    with _db().session() as s:
        plan = G.rebuild_set(s, changed={"cir:other": MOVED})
    assert plan["rebuild"] == []


def test_the_edges_come_from_the_provenance_rather_than_a_second_copy():
    assert "second answer" in G.state()["edges_from"]
    with _db().session() as s:
        graph = G.load_graph(s)
    assert set(graph["nodes"]) == {"pdf:hex.pdf", "listing_copy:hex@1"}
    assert "cir:hex" in graph["external_refs"]


def test_a_cycle_is_refused_rather_than_traversed():
    db = Database("sqlite://")
    db.create_all()
    fingerprint = A.fingerprint("x")
    with db.session() as s:
        A.record(s, artefact_class="pdf", artefact_key="a", product_slug="p",
                 inputs={"asset:b": fingerprint})
        A.record(s, artefact_class="chart", artefact_key="b", product_slug="p",
                 inputs={"asset:a": fingerprint})
    with db.session() as s:
        try:
            G.load_graph(s)
        except G.GraphRefused as exc:
            assert "does not terminate" in str(exc)
            assert "these go together" in str(exc)
        else:  # pragma: no cover
            raise AssertionError("a cycle was traversed")


# --- the coverage the rebuild set is read beside ------------------------------------------------

def test_a_propagation_over_an_uninstrumented_estate_reports_its_own_blindness():
    expected = [("chart", f"c{i}", "hex") for i in range(9)]
    with _db(chain=False).session() as s:
        plan = G.rebuild_set(s, changed={"cir:hex": MOVED}, expected=expected)
    assert plan["coverage"] == {"in_graph": 1, "not_in_graph": 9, "share": 0.1}
    assert "true of the graph and false of the shop" in plan["why"]


def test_full_coverage_says_so_plainly():
    with _db().session() as s:
        plan = G.rebuild_set(s, changed={"cir:hex": MOVED}, expected=[])
    assert plan["coverage"]["share"] == 1.0
    assert "carry no provenance" not in plan["why"]


# --- enqueue and block ------------------------------------------------------------------------------

def test_the_same_change_enqueues_once_and_a_different_change_enqueues_again():
    from brambleloop.queue.durable import JobQueue

    db = _db()
    queue = JobQueue(db)
    with db.session() as s:
        first = G.enqueue(s, queue, changed={"cir:hex": MOVED}, reason="design moved")
        again = G.enqueue(s, queue, changed={"cir:hex": MOVED}, reason="design moved")
        other = G.enqueue(s, queue, changed={"cir:hex": A.fingerprint({"rows": 20})},
                          reason="moved again")
    assert len(first["enqueued"]) == 2
    assert again["enqueued"] == []
    assert len(again["already_queued"]) == 2
    assert len(other["enqueued"]) == 2


def test_publication_is_blocked_until_every_descendant_is_rebuilt():
    with _db().session() as s:
        blocked = G.blocks_publication(s, changed={"cir:hex": MOVED}, rebuilt=set())
        partial = G.blocks_publication(s, changed={"cir:hex": MOVED},
                                       rebuilt={"pdf:hex.pdf"})
        done = G.blocks_publication(s, changed={"cir:hex": MOVED},
                                    rebuilt={"pdf:hex.pdf", "listing_copy:hex@1"})
    assert blocked["may_publish"] is False
    assert partial["may_publish"] is False
    assert "partly current, which is harder to find" in partial["why"]
    assert done["may_publish"] is True


def test_state_names_what_the_graph_does_not_cover():
    out = G.state()
    assert "false of the shop" in out["note"]
    assert out["order"].startswith("topological")


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
