"""Batch 19 integration: the premium-PDF blocker never deadlocks image admission and never
hides a real PDF defect (D-OWNER-SALE-PIPELINE + D-MAIN-IMAGE-ADMISSION)."""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brambleloop.publish import listing_package as LP  # noqa: E402
from brambleloop.visual import image_production as IP  # noqa: E402


def _ed(verdict, bound=False):
    return {"verdict": verdict, "bound_to_release_pdfs": bound}


def test_uncertified_pdfs_waiting_on_the_gallery_are_an_image_blocker():
    for eds in ({"US": _ed("UNKNOWN"), "UK": _ed("UNKNOWN")},
                {"US": _ed("PASS", bound=False), "UK": _ed("UNKNOWN")}):
        b = LP.pdf_standard_blocker({"both_pass": False, "editions": eds})
        assert b["source"] == "pdf_standard" and b.get("image") is True, b
        assert IP._admissible_blocker(b), b


def test_a_failing_pdf_or_an_unreadable_reading_is_never_an_image_blocker():
    for eds in ({"US": _ed("FAIL"), "UK": _ed("UNKNOWN")},
                {"US": _ed("PASS", bound=True), "UK": _ed("FAIL")},
                {}):
        b = LP.pdf_standard_blocker({"both_pass": False, "editions": eds})
        assert "image" not in b, b
        assert not IP._admissible_blocker(b), b
    assert "D-OWNER-PDF-STANDARD" in LP.pdf_standard_blocker(
        {"both_pass": False, "editions": {"US": _ed("FAIL")}})["why"]


if __name__ == "__main__":
    import _minipytest

    _minipytest.run_module(globals())
