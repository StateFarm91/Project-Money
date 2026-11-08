"""Review VISUAL D1 A-1 / A-2 (the owner's V3 condition): a fixture-labelled identity PASS is
never an accepted frame or an accepted identity anchor.

V3 stand-in judges label their readings `fixture_only`. `candidate_gates.gate_status` reads
such a PASS as UNKNOWN; this pins that the real wiring uses it end to end:
- `CG.evaluate` gives technical UNKNOWN with "identity" in `unknown`, and `record_candidate`
  stores the frame as "unverified", never "accepted" (A-2);
- `identity_anchor_verdict` (Laura's stage-A identity anchor, also used by `reverify`) gives
  technical UNKNOWN, so a stand-in likeness is never accepted as her identity context
  without the owner's review (A-1).
The same readings without the fixture label pass, so the test is not vacuous.

Run: cd brambleloop && PYTHONPATH=src:tests $PY tests/test_v3_fixture_wiring.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import test_w4_ownerimg as O  # noqa: E402

from brambleloop.visual import candidate_gates as CG  # noqa: E402
from brambleloop.visual import image_production as IP  # noqa: E402

FIXTURE_PASS = {"status": "PASS", "why": "[fixture_only_not_certification] stand-in judges",
                "fixture_only": True,
                "certification": "FIXTURE ONLY: not identity certification"}


class _Judges(O.StubJudges):
    def __init__(self, fixture: bool):
        super().__init__()
        self.fixture = fixture

    def identity(self, c):
        return dict(FIXTURE_PASS) if self.fixture else {"status": "PASS", "why": "stub"}


def _laura_cand(db):
    oid = O.approved_outfit(db)
    return O.cand(role="lifestyle", release=O.RELEASE, laura_present=True,
                  outfit_id=oid if isinstance(oid, str) else (oid or {}).get("outfit_id"))


def test_evaluate_and_record_read_a_fixture_identity_as_unverified():
    db = O.make_db()
    c = _laura_cand(db)
    fx = CG.evaluate(db, dict(c), judges=_Judges(True), record_outfit_use=False)
    assert fx["checks"]["identity"].get("fixture_only") is True       # the label is kept
    assert fx["technical_status"] != "PASS", fx["technical_status"]
    assert "identity" in fx["unknown"], fx["unknown"]
    plain = CG.evaluate(db, dict(c), judges=_Judges(False), record_outfit_use=False)
    assert "identity" not in plain["unknown"], plain["unknown"]
    row = IP.record_candidate(db, dict(c), fx, method="autonomous")
    from brambleloop.visual.image_records import ImageCandidate

    with db.session() as s:
        got = s.get(ImageCandidate, row["candidate_id"] if isinstance(row, dict) else row)
        assert got.outcome == "unverified" and got.technical_status != "PASS", (
            got.outcome, got.technical_status)


def test_a_fixture_identity_never_makes_an_accepted_identity_anchor():
    db = O.make_db()
    c = {**_laura_cand(db), "role": IP.IDENTITY_ANCHOR_ROLE, "sha256": "f" * 64}
    bind = {"status": "PASS", "why": "fixture binding"}
    fx = IP.identity_anchor_verdict(db, c, _Judges(True), bind)
    assert fx["technical_status"] == "UNKNOWN" and "identity" in fx["unknown"], fx
    plain = IP.identity_anchor_verdict(db, c, _Judges(False), bind)
    assert "identity" not in plain["unknown"], plain["unknown"]


def test_the_laura_gate_row_band_follows_its_status():
    """A-3 / A-N2: a fixture PASS row reads status UNKNOWN and band REVIEW."""
    row = dict(FIXTURE_PASS, band="PASS")
    ok = {"status": "PASS", "why": "x"}
    checks = {k: dict(ok) for k in ("body_proportions", "outfit_consistency",
                                    "outfit_distinctness", "realism", "anatomy",
                                    "product_truth", "outfit", "disclosure")}
    checks["identity"] = row
    order = {g["gate"]: g for g in CG.laura_gate_order(
        checks, {"publishable": False, "blockers": ["x"]})}
    ident = order["canonical_identity"]
    # A-N2: the band is in the identity band vocabulary (REVIEW), never the bare "UNKNOWN"
    from brambleloop.visual import identity_gate as IG

    assert ident["status"] == "UNKNOWN" and ident["band"] == IG.BAND_REVIEW, ident
    checks["identity"] = {"status": "PASS", "why": "x", "band": "PASS"}
    order = {g["gate"]: g for g in CG.laura_gate_order(
        checks, {"publishable": False, "blockers": ["x"]})}
    assert order["canonical_identity"]["band"] == "PASS"



def test_the_anchor_review_card_names_the_fixture_identity_reading():
    """A-N3: `_best` (what the owner's anchor-review card says) and reverify's history
    name a fixture-labelled identity PASS as UNKNOWN, not "UNKNOWN on []"."""
    db = O.make_db()
    c = {**_laura_cand(db), "role": IP.IDENTITY_ANCHOR_ROLE, "sha256": "e" * 64}
    bind = {"status": "PASS", "why": "fixture binding"}
    fx = IP.identity_anchor_verdict(db, c, _Judges(True), bind)
    IP.record_candidate(db, dict(c), fx, method="autonomous")
    best = IP._best(db, listing=c.get("listing") or "", role=IP.IDENTITY_ANCHOR_ROLE,
                    slug=c["slug"], version=c["version"], release=c["release"])
    assert best and "identity" in best["unknown"], best and best["unknown"]
    plain = {**c, "sha256": "d" * 64, "slug": c["slug"] + "-plain"}
    IP.record_candidate(db, dict(plain),
                        IP.identity_anchor_verdict(db, plain, _Judges(False), bind),
                        method="autonomous")
    best = IP._best(db, listing=plain.get("listing") or "", role=IP.IDENTITY_ANCHOR_ROLE,
                    slug=plain["slug"], version=c["version"], release=c["release"])
    assert best and "identity" not in best["unknown"], best and best["unknown"]



def test_reverify_history_names_the_fixture_identity_reading():
    """B-N3 (mutant AN3_reverify_raw): reverify records the previous verdict's UNKNOWNs
    through gate_status, so a fixture identity PASS it replaces is named in the history."""
    from brambleloop.core.artifacts import ArtifactStore
    from brambleloop.visual.image_records import ImageCandidate

    db = O.make_db()
    sha = ArtifactStore().put("test", b"fixture identity anchor bytes", "image/png",
                              db=db).sha256
    c = {**_laura_cand(db), "role": IP.IDENTITY_ANCHOR_ROLE, "sha256": sha}
    bind = {"status": "PASS", "why": "fixture binding"}
    cid = IP.record_candidate(db, dict(c), IP.identity_anchor_verdict(db, c, _Judges(True),
                                                                      bind),
                              method="autonomous")["candidate_id"]
    saved = IP._binding
    IP._binding = lambda *_a, **_k: dict(bind)
    try:
        out = IP.reverify(db, cid, judges=_Judges(False))
    finally:
        IP._binding = saved
    assert out.get("reverified"), out
    with db.session() as s:
        hist = s.get(ImageCandidate, cid).checks["_reverified"]["history"]
    assert "identity" in hist[-1]["previous_unknown"], hist


if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK   {name}")
            except Exception:  # noqa: BLE001
                import traceback

                failed += 1
                print(f"FAIL {name}")
                traceback.print_exc()
    print(f"{failed} failed")
    sys.exit(1 if failed else 0)
