"""W4-B2MOAT: #44 brand moat measured once and recorded; read paths never pay.

image_vision opened in production on 2026-10-12. The #44 recognisability measurement runs a
vision judge on each listing's hero frame inside `brand.moat.evidence`. That function was
called from `launch.readiness.assess`, which runs on every request from:
- `GET /api/launch`;
- the public dashboard;
- `GET /api/launch/packet`.

So with the gate open, an unauthenticated page load would have paid a judge per listing, and
nothing recorded the answer.

The fix:
- the daily `launch.readiness` job measures, and records each measurement as
  `brand.recognisability_measured`;
- read paths read the recorded measurement for the listing's current hero frame;
- an older frame's record is not this frame's measurement.

Stub judge, no spend.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_w4_b2moat.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.brand import moat  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, Listing, ListingAsset  # noqa: E402

_TMP = tempfile.mkdtemp()


def ok(m):
    print(f"  ok  {m}")


def _db():
    db = Database(f"sqlite:///{_TMP}/d{len(os.listdir(_TMP))}.sqlite")
    db.create_all()
    return db


def _listing(db, slug, sha):
    with db.session() as s:
        s.add(Listing(product_slug=slug, version="1.0.0", title="t", description="d"))
        s.add(ListingAsset(product_slug=slug, version="1.0.0", position=1,
                           asset_class="TWIN_RENDER", role="hero", sha256=sha))


def _fake_judge(colours):
    def fake(ref, *, db=None, provider=None, claim=None):
        assert Path(ref).is_file(), ref
        return {"described": True, "realism": {}, "realism_unjudged": [], "semantic": {},
                "description": {"dominant_colours": colours, "human_present": False,
                                "third_party_marks": "none"}}
    return fake


def test_the_job_measures_and_records_and_read_paths_read_the_record():
    from brambleloop.build2 import executor
    from brambleloop.core.artifacts import ArtifactStore
    from brambleloop.visual import inspect as inspection

    db = _db()
    sha = ArtifactStore().put("test/hero.png", b"\x89PNG hero", "image/png").sha256
    _listing(db, "throw", sha)
    gate = executor.GATE_BY_KEY["image_vision"]
    saved = (gate.check, inspection.inspect_image)
    calls = []
    try:
        gate.check = lambda db_, env: True

        def counting(ref, **kw):
            calls.append(ref)
            return _fake_judge("deep pine green, cream and a little gold")(ref, **kw)
        inspection.inspect_image = counting
        # Read path first: nothing recorded, nothing paid.
        read = moat.inventory(db, measure=False)["recognisable_without_model"]
        assert calls == [] and read["by_proxy_only"] == ["throw"], read
        why = read["per_listing"]["throw"]["measured"]["why"]
        assert "read paths do not pay" in why, why
        # The job measures once and records it.
        job = moat.inventory(db)["recognisable_without_model"]
        assert len(calls) == 1 and job["measured"] == ["throw"]
        with db.session() as s:
            rows = [r for r in s.query(AuditLog).filter_by(action=moat.MEASURED_ACTION)]
        assert len(rows) == 1 and rows[0].detail["frame_sha256"] == sha
        # Read paths now show the recorded measurement and still pay nothing.
        read = moat.inventory(db, measure=False)["recognisable_without_model"]
        assert len(calls) == 1 and read["measured"] == ["throw"], read
        assert read["per_listing"]["throw"]["measured"]["recorded_at"]
    finally:
        gate.check, inspection.inspect_image = saved
    ok("the job measures and records; GET paths read the record and never pay")


def test_a_record_for_an_older_frame_is_not_this_frames_measurement():
    db = _db()
    _listing(db, "basket", "b" * 64)
    with db.session() as s:
        s.add(AuditLog(actor="orchestrator", action=moat.MEASURED_ACTION, artifact="basket",
                       detail={"status": "MEASURED", "recognisable": True,
                               "frame_sha256": "a" * 64}))
    got = moat.recorded_recognisability(db, "basket")
    assert got["status"] == "UNMEASURED" and got["frame_sha256"] == "b" * 64, got
    ok("a new hero frame needs its own measurement")


def test_launch_read_paths_ask_for_no_measurement():
    src = (ROOT / "src/brambleloop/app/main.py").read_text()
    assert src.count("measure_vision=False") >= 2, "GET /api/launch and the dashboard"
    packet = (ROOT / "src/brambleloop/launch/packet.py").read_text()
    assert "measure_vision=False" in packet
    ok("GET /api/launch, the dashboard and the launch packet read, never measure")


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
    print(f"{len(tests) - bad}/{len(tests)} passed")
    sys.exit(1 if bad else 0)
