"""ENG-FIRST-LISTING: the first-listing readiness reading names WHY a release is withheld.

Production evidence (2026-11-22T00:00Z) showed cloudline-baby-blanket@1.2.0 with certification
FAIL: certificate granted, release matching, "withheld": true. The evidence projection emitted
only that boolean, so nobody outside the database could tell a competitive-standard withhold
(#220) from a teardown requirement, a re-verification failure or the teardown QA. The section
now carries `withheld_kinds` (the fixed vocabulary `publish.withholding.KINDS`, never reason
text). The gate is unchanged: a withheld release still FAILs certification.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_first_listing_fix.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from sqlalchemy import select  # noqa: E402

import test_w4_departments as D  # noqa: E402 - the department suite's release fixture
from brambleloop.core.models import PatternVersion  # noqa: E402
from brambleloop.publish import withholding as W  # noqa: E402


def _rh(db):
    with db.session() as s:
        return s.scalar(select(PatternVersion)).release_hash


def test_withheld_kinds_are_named_and_the_gate_still_fails():
    from brambleloop.ops import production_evidence as pe
    from brambleloop.ops import publication_authority as pa

    cir = D._cir()
    db = D._db(cir)
    W.record(db, cir.slug, cir.version, kind=W.COMPETITIVE_STANDARD,
             reason="competitive standard (#220): gallery_images bar 10.0, ours 7.0")
    ev = pa.evidence(db, cir.slug, cir.version, _rh(db))
    cert = ev["certification"]
    assert cert["state"] == pa.FAIL and cert["withheld"] is True, cert
    assert cert["withheld_kinds"] == [W.COMPETITIVE_STANDARD], cert
    diag = pe._section_diagnostics(ev)["certification"]
    assert diag["withheld"] is True and diag["withheld_kinds"] == [W.COMPETITIVE_STANDARD], diag


def test_a_kind_outside_the_vocabulary_is_never_echoed():
    from brambleloop.ops import production_evidence as pe

    ev = {"certification": {"withheld": True,
                            "withheld_kinds": ["owner_veto", "<script>secret reason</script>"]}}
    diag = pe._section_diagnostics(ev)["certification"]
    assert diag["withheld_kinds"] == ["owner_veto"], diag


def test_nothing_withheld_reads_an_empty_list():
    from brambleloop.ops import publication_authority as pa

    cir = D._cir()
    db = D._db(cir)
    cert = pa.evidence(db, cir.slug, cir.version, _rh(db))["certification"]
    assert cert["withheld"] is False and cert["withheld_kinds"] == [], cert


def test_competitive_bars_are_reported_as_numbers_and_still_withhold():
    from brambleloop.core.models import CompetitiveStandard
    from brambleloop.ops import production_evidence as pe
    from brambleloop.ops import publication_authority as pa
    from brambleloop.publish import release_gates

    cir = D._cir()
    db = D._db(cir)
    with db.session() as s:
        s.add(CompetitiveStandard(key="video_in_gallery", value=1.0, higher_is_better=True,
                                  history=[]))
    # The publish gate writes the standard into the record, exactly as in production.
    g = release_gates.for_publish(db, slug=cir.slug, version=cir.version, read_only=True)
    assert any("video_in_gallery" in r for r in g["reasons"]), g["reasons"][:8]
    ev = pa.evidence(db, cir.slug, cir.version, _rh(db))
    assert ev["certification"]["state"] == pa.FAIL
    assert W.COMPETITIVE_STANDARD in ev["certification"]["withheld_kinds"]
    diag = pe._section_diagnostics(ev)["certification"]
    assert diag["competitive_now"] == [{"standard": "video_in_gallery", "bar": 1.0,
                                        "ours": 0.0, "verdict": "below"}], diag
    assert pe._competitive_now([{"standard": "secret", "bar": 1}]) == []


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                fails += 1
                print("FAIL", name, repr(e))
                traceback.print_exc()
    print(f"{fails} failed")
    sys.exit(1 if fails else 0)
