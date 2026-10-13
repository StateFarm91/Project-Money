"""W4-COPY: customer copy rewritten, every claim registered, forbidden claims fenced out.

Owner directive 2026-10-11. The tests hold five things:
- no customer surface carries a forbidden wording: an invented designer, testing or samples
  that did not happen, photographs, a human Laura, legal clearance, a proactive notice no
  channel can send, or machinery talk;
- each fence actually catches the wording it replaced;
- the AI disclosure is plain and names no human designer;
- one About exists, and it is the store copy;
- every claim carries evidence, and every legal question stays open rather than being
  asserted closed.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_w4_copy.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.store_foundation import claims as C  # noqa: E402

OLD_WORDINGS = {
    "C-01": "Parts of this design were developed with AI assistance, directed and edited by "
            "the designer.",
    "C-08a": "corrections and revisions are free forever, and buyers are told when the "
             "version they own changes",
    "C-08b": "we correct the pattern itself and send the corrected file to everyone who "
             "bought it",
    "C-15": "every stitch count was verified row by row by an automated pattern compiler",
    "C-15b": "Brambleloop Studio makes crochet patterns the way software gets made",
    "C-09": "the pattern file, its charts and its photographs may not be shared",
    "C-03": "Every pattern is tested by our pattern testers before release.",
    "C-03b": "Our samples are worked in a soft cotton.",
    "C-11": "Real photos of the finished blanket.",
    "C-13": "Laura is a real woman who crochets every sample.",
    "C-12": "We reply within 24 hours.",
    "C-16": "Our terms are legally reviewed.",
}


def ok(m):
    print(f"  ok  {m}")


def test_every_customer_surface_is_clean():
    a = C.audit()
    assert a["clean"], a["hits"]
    s = C.surfaces()
    assert len(s) > 50 and "listing:description_template" in s and "pdf:ai_disclosure" in s
    ok(f"{len(s)} customer surfaces scanned: no forbidden wording")


def test_each_fence_catches_the_wording_it_replaced():
    missed = {k: t for k, t in OLD_WORDINGS.items() if not C.scan(t)}
    assert not missed, missed
    for clean in ("This design was created with AI assistance.",
                  "We have not yet worked physical samples, so make a gauge swatch first.",
                  "Laura is Brambleloop's AI founder. She is an AI, not a person.",
                  "These are the terms Brambleloop offers; they have not yet been through "
                  "legal review."):
        assert not C.scan(clean), (clean, C.scan(clean))
    ok("every old false wording is caught; the truthful replacements pass")


def test_the_ai_disclosure_is_plain_and_invents_no_designer():
    from brambleloop.gates import platform_policy as pp
    from brambleloop.publish import pdf

    d = pp.DISCLOSURES["ai_assisted_design"]
    assert "AI assistance" in d and "designer" not in d.lower()
    assert d in C.sample_description()
    assert "AI assistance" in pdf.AI_DISCLOSURE and "compiler" not in pdf.AI_DISCLOSURE
    ok("listing, PDF and FAQ carry a plain AI disclosure with no human designer")


def test_one_about_and_it_is_the_store_copy():
    from brambleloop.brand import storefront
    from brambleloop.store_foundation import copy_v2 as V

    assert storefront.ABOUT == V.ABOUT
    assert "software" not in storefront.ABOUT.lower()
    assert V.VERSION == "copy_v3"
    assert V.export()["claim_register"][0]["key"] == "C-01"
    ok("brand.storefront.ABOUT is store copy v3; the export carries the claim register")


def test_claims_have_evidence_and_legal_questions_stay_open():
    keys = [c.key for c in C.CLAIMS]
    assert len(keys) == len(set(keys)) >= 16
    for c in C.CLAIMS:
        assert c.verdict in (C.SUPPORTED, C.QUALIFIED, C.REMOVED)
        assert len(c.evidence) > 40 and c.now
        if c.review:
            assert c.review in (C.OWNER, C.LEGAL) and c.review_question.endswith(("?", "."))
    legal = {c.key for c in C.CLAIMS if c.review == C.LEGAL}
    assert {"C-07", "C-10"} <= legal, legal
    from brambleloop.commerce import terms as T

    assert T.BRAMBLELOOP_TERMS.legal_review is None
    assert "not yet been through legal review" in T.render(T.BRAMBLELOOP_TERMS, "listing")
    ok("16 claims with evidence; licence and consumer-law questions remain open reviews")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    bad = 0
    for t in tests:
        try:
            t()
        except Exception as e:  # noqa: BLE001
            bad += 1
            import traceback

            traceback.print_exc()
            print(f"FAIL {t.__name__}: {e}")
        else:
            print(f"OK   {t.__name__}")  # run_tests.sh counts ^OK lines
    print(f"{len(tests) - bad}/{len(tests)} passed")
    sys.exit(1 if bad else 0)
