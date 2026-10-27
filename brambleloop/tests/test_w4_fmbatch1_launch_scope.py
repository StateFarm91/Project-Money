"""F-630: in SHADOW, READY work that serves a launch-critical Final Master row is ordered
first; after SHADOW the order is untouched; the shipped map matches the closure matrix."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.build2 import launch_scope as L  # noqa: E402


def test_shipped_map_matches_the_matrix():
    matrix = json.loads((ROOT / "research/final_build/closure_matrix.json").read_text())
    assert L.build_map(matrix) == L.launch_map()
    assert len(L.launch_map()) > 50


def test_shadow_orders_launch_work_first_and_tags_everything():
    some = int(next(iter(L.launch_map())))
    other = max(int(k) for k in L.launch_map()) + 1000
    ready = [{"requirement_id": other, "priority": 1.0},
             {"requirement_id": some, "priority": 2.0}]
    out = L.order([dict(r) for r in ready], "shadow")
    assert [r["requirement_id"] for r in out] == [some, other]
    assert out[0]["pre_launch_scope"] == L.SERVES and out[0]["serves_launch_rows"]
    assert out[1]["pre_launch_scope"] == L.DEPRIORITISED
    live = L.order([dict(r) for r in ready], "production")
    assert [r["requirement_id"] for r in live] == [other, some]


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("OK  ", n)  # run_tests.sh counts lines beginning OK
