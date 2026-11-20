"""Review main-integ #1: a disclosed set's #66 mobile renders must be ON FILE at publish time.

`release_gates._disclosed_mobile` re-verifies every stored render ref against the artifact
store. A render missing from the store makes the reading not_rendered / incomplete, which
`disclosed_listing_set` turns into COMMERCIAL_QA not_run and a blocking reason. These tests
pin that, so a mutant that ignores missing renders (`missing = []`) is killed.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))
import _tmp; _tmp.install()  # noqa: E401,E702

from brambleloop.core.artifacts import ArtifactStore
from brambleloop.publish import release_gates as RG


def _rec(refs: dict, *, complete=True):
    return {"qa": {"mobile": {"ok": True, "complete": complete, "not_rendered": [],
                              "why": None,
                              "contexts": {n: {"render_ref": r} for n, r in refs.items()}}}}


def _stored(root, payload: bytes) -> str:
    return ArtifactStore(root).put("mobile.png", payload, "image/png").sha256


def test_every_render_on_file_keeps_the_reading_complete():
    with tempfile.TemporaryDirectory() as root:
        a, b = _stored(root, b"render-a"), _stored(root, b"render-b")
        out = RG._disclosed_mobile(_rec({"search_grid": "sha256:" + a, "thumb": b}),
                                   store_root=root)
        assert out["complete"] is True and out["ok"] is True, out
        assert out["not_rendered"] == [] and out["render_refs"] == {"search_grid": a, "thumb": b}


def test_a_render_missing_from_the_store_is_not_rendered_and_incomplete():
    with tempfile.TemporaryDirectory() as root:
        a = _stored(root, b"render-a")
        gone = "0" * 64
        out = RG._disclosed_mobile(_rec({"search_grid": a, "thumb": "sha256:" + gone}),
                                   store_root=root)
        assert out["complete"] is False and out["ok"] is False, out
        assert out["not_rendered"] == ["thumb"], out
        assert "not on file" in out["why"] and "thumb" in out["why"]


def test_an_empty_ref_counts_as_missing():
    with tempfile.TemporaryDirectory() as root:
        out = RG._disclosed_mobile(_rec({"thumb": None}), store_root=root)
        assert out["complete"] is False and out["not_rendered"] == ["thumb"], out


def test_no_mobile_reading_is_none_never_a_pass():
    assert RG._disclosed_mobile({"qa": {}}) is None


if __name__ == "__main__":
    import traceback
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as exc:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(exc))
                traceback.print_exc()
    print(f"{fails} failed")
    sys.exit(1 if fails else 0)
