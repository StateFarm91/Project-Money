"""A search certificate PENDING only on the hero is image-caused: it does not stop for-sale
admission, and it still blocks the package. Anything else pending, or REFUSED, is not."""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brambleloop.runtime import etsy_ops  # noqa: E402
from brambleloop.publish import listing_package as LP  # noqa: E402
from brambleloop.visual import image_production as IP  # noqa: E402


def _decide(selected):
    """Run the exact certified_payload rule on a stubbed publish_inputs reading."""
    from brambleloop.commerce import category

    real = category.publish_inputs
    category.publish_inputs = lambda *a, **k: selected
    try:
        try:
            etsy_ops._search_rule(selected)
            return "pass"
        except etsy_ops.HeroUnjudged:
            return "hero"
        except ValueError:
            return "block"
    finally:
        category.publish_inputs = real


def test_only_the_unjudged_hero_is_image_caused():
    assert _decide({"certified": "PENDING", "certified_pending": ["hero"]}) == "hero"
    assert _decide({"certified": "PENDING", "certified_pending": ["hero", "tags"]}) == "block"
    assert _decide({"certified": "PENDING", "certified_pending": []}) == "block"
    assert _decide({"certified": "REFUSED", "certified_pending": ["hero"]}) == "block"
    assert _decide({"certified": "STALE", "certified_problems": ["x"]}) == "block"
    assert _decide({"certified": "PASS"}) == "pass"
    assert issubclass(etsy_ops.HeroUnjudged, ValueError)   # every old catch still blocks


def test_the_package_tags_it_as_image_and_admission_accepts_it():
    real = etsy_ops.certified_payload

    def hero(*a, **k):
        raise etsy_ops.HeroUnjudged("only the hero is unjudged")

    etsy_ops.certified_payload = hero
    try:
        got, err = None, None
        try:
            got, err = LP._try_payload(etsy_ops, None, "s", "1")
        except etsy_ops.HeroUnjudged:
            got = "raised"
        assert got == "raised"
    finally:
        etsy_ops.certified_payload = real
    b = {"source": "certified_payload", "why": "only the hero is unjudged", "image": True}
    assert IP._admissible_blocker(b) is True
    assert IP._admissible_blocker({"source": "certified_payload", "why": "x"}) is False


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
