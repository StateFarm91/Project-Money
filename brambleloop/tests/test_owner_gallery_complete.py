"""D-OWNER-GALLERY-COMPLETE: a listing is not ready until every listing photo is ready."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))
import _tmp; _tmp.install()  # noqa: E401,E702

from brambleloop.products import lifecycle
from brambleloop.visual.shot_plans import CAMPAIGN_MIN_FRAMES


class _Rec:
    def __init__(self, n):
        self.certificate = {"frames": [{"position": i} for i in range(1, n + 1)]}


class _S:
    def __init__(self, rec):
        self.rec = rec

    def scalar(self, _q):
        if isinstance(self.rec, Exception):
            raise self.rec
        return self.rec


def test_seven_frame_standard_is_the_bar():
    assert CAMPAIGN_MIN_FRAMES == 7


def test_partial_gallery_is_not_complete():
    assert CAMPAIGN_MIN_FRAMES > 0
    for n in range(0, CAMPAIGN_MIN_FRAMES):
        assert lifecycle._complete_gallery(_S(_Rec(n)), "x") is False, n


def test_full_gallery_is_complete():
    assert lifecycle._complete_gallery(_S(_Rec(CAMPAIGN_MIN_FRAMES)), "x") is True


def test_no_certificate_or_unreadable_is_never_complete():
    assert lifecycle._complete_gallery(_S(None), "x") is False
    assert lifecycle._complete_gallery(_S(RuntimeError("db down")), "x") is False
    bad = _Rec(7); bad.certificate = {"frames": "seven"}
    assert lifecycle._complete_gallery(_S(bad), "x") is False


def test_certified_frames_refuses_a_partial_gallery_in_source():
    # The upload path names the rule; a partial gallery is a problem, not a warning.
    import inspect
    from brambleloop.runtime import etsy_ops
    src = inspect.getsource(etsy_ops.certified_frames)
    assert "CAMPAIGN_MIN_FRAMES" in src and "gallery incomplete" in src


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
