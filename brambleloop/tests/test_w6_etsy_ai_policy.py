"""ENG-ETSY-AI-POLICY (w6): listing copy may never claim human authorship the company lacks.

Etsy Help 44297885802647 (edited 2026-11-11): sellers "cannot misrepresent AI-generated work
as handmade or entirely their own creation". The fixed AI sentences were a convention; these
tests pin the guard that refuses the claims, and pin that the company's own sentences pass.

Run: cd brambleloop && python3 tests/test_w6_etsy_ai_policy.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.gates.platform_policy import DISCLOSURES  # noqa: E402
from brambleloop.integrations.etsy import EtsyRejected, build_payload  # noqa: E402
from brambleloop.publish import etsy_ai_policy as pol  # noqa: E402
from brambleloop.publish.pdf import AI_DISCLOSURE  # noqa: E402

GOOD = dict(title="Cabled Cushion Crochet Pattern", price_cad=7.5,
            tags=["crochet pattern"], materials=["cotton yarn"],
            description="A digital crochet pattern. " + DISCLOSURES["ai_assisted_design"])


def test_claims_are_refused_in_copy():
    for claim in ("I designed this pattern", "hand-drawn charts", "Designed by a human crocheter",
                  "tested by real crocheters", "my own design", "human-tested", "made by hand",
                  "the sample we crocheted"):
        assert pol.authorship_claim_problems(f"Lovely. {claim}."), claim


def test_company_sentences_pass():
    texts = [DISCLOSURES[k] for k in DISCLOSURES] + [AI_DISCLOSURE]
    assert len(texts) > 1
    for t in texts:
        assert pol.authorship_claim_problems(t) == [], t


def test_build_payload_refuses_claim_in_title_or_description():
    for field, value in (("description", GOOD["description"] + " Hand-drawn by me."),
                         ("title", "My Own Design Cushion Crochet Pattern")):
        bad = dict(GOOD, **{field: value})
        try:
            build_payload(**bad)
        except EtsyRejected as exc:
            assert pol.CODE in str(exc)
        else:
            raise AssertionError(f"{field} claim was accepted")


def test_build_payload_still_accepts_honest_copy():
    assert build_payload(**GOOD).who_made in ("i_did", "someone_else", "collective")


def test_sources_are_recorded_verbatim_with_dates():
    assert {s["article"] for s in pol.SOURCES} == {"44297885802647", "115015663347"}
    assert all(s["edited_at"] and s["read_on"] == "2026-11-19" for s in pol.SOURCES)


if __name__ == "__main__":
    import traceback

    fails = 0
    tests = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        try:
            fn()
            print(f"OK   {name}")
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            print(f"FAIL {name}")
            fails += 1
    print(f"\n{len(tests) - fails} passed, {fails} failed")
    raise SystemExit(1 if fails else 0)
