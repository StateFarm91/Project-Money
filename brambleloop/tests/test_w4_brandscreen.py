"""W-BRANDSCREEN: the knock-out screening draft is validated, and is NOT a recorded search.

The automated half of the screening (domains by RDAP, search-engine observations) is in
research/final_build/w4/evidence_BRANDSCREEN/knockout_draft.json. The registers, Etsy and the
social handles need a person. These tests pin that the draft fails `brand.clearance.problems`
exactly on those screens, that the automated domain screen is well-formed on its own, and that
nothing has been recorded into KNOCKOUT_SEARCHES -- so brand_clearance cannot read cleared.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_w4_brandscreen.py
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.brand import clearance as CL  # noqa: E402

DRAFT = ROOT / "research/final_build/w4/evidence_BRANDSCREEN/knockout_draft.json"
SCREENED_ON = date(2026, 10, 27)
RESULTS: list[str] = []


def ok(name: str) -> None:
    RESULTS.append(name)
    print(f"OK {name}")


def _draft() -> dict:
    return json.loads(DRAFT.read_text())


def test_the_draft_is_not_a_valid_knockout_and_fails_on_the_person_screens():
    problems = CL.problems(_draft(), today=SCREENED_ON)
    assert problems, "an incomplete screening must not validate"
    for screen in ("trademark_register_ca", "marketplace", "social_handles"):
        assert any(f"screen {screen!r}" in p for p in problems), (screen, problems)
    assert not any("'domain'" in p for p in problems), problems
    assert not any("name is" in p or "searched_on" in p for p in problems), problems
    ok("draft fails validation exactly on the person-only screens (CIPO, Etsy, social)")


def test_the_domain_screen_is_complete_on_its_own():
    dom = _draft()["screens"]["domain"]
    assert dom["source"].startswith("https://")
    assert all("brambleloop" in q.replace("-", "") for q in dom["queries"])
    assert dom["hits"] == []
    ok("domain screen: https source, queries for the name, an explicit empty hits list")


def test_nothing_is_recorded_so_brand_clearance_cannot_read_cleared():
    assert CL.KNOCKOUT_SEARCHES == (), "a screening was recorded; review it against the draft"
    assert CL.latest()["state"] == "NONE"
    ok("KNOCKOUT_SEARCHES is empty: no clearance is claimed from an incomplete screening")


def test_the_draft_says_it_is_a_screening_and_not_legal_advice():
    d = _draft()
    assert "not legal advice" in d["_not_legal_advice"].lower()
    assert d["_status"].startswith("DRAFT -- INCOMPLETE")
    md = (ROOT / "research/final_build/w4/BRAND_SCREENING.md").read_text()
    assert "not legal advice" in md
    ok("draft and report state SCREENING, not legal advice")


if __name__ == "__main__":
    import traceback

    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
            except Exception:  # noqa: BLE001
                traceback.print_exc()
                print(f"FAIL {name}")
                fails += 1
    print(f"\n{len(RESULTS)} passed, {fails} failed")
    raise SystemExit(1 if fails else 0)
