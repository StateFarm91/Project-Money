"""Read-only factory visibility in the readback evidence: counts and fixed vocabulary only."""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.ops import owner_directives as D  # noqa: E402
from brambleloop.ops import production_evidence as pe  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402

NOW = datetime(2026, 11, 21, 3, 0, tzinfo=timezone.utc)


def test_visibility_reports_jobs_activations_and_no_text():
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/v.db")
    db.create_all()
    JobQueue(db).enqueue("listing", "listing.package", {"cadence": "listing_package"})
    D.apply(db, now=NOW)
    v = pe.factory_visibility(db, now=NOW)
    assert v["readable"] and any(k.startswith("listing.package:") for k in v["jobs_24h"]), v
    assert v["paid_activations_active"] == {"flux-3-image:generation": True,
                                            "openai-vision:vision": True}, v
    assert v["image_runs_by_state"] == {}, v   # readable and empty, never an error dict
    assert v["owner_etsy_exercise"] == [], v
    assert v["parked_admission"] == [], v
    text = json.dumps(v)
    assert "inputs" not in text and "last_error" not in text
    ev = pe.evidence(db, now=NOW)
    assert "factory_visibility" in json.dumps(ev)


def test_parked_admission_reads_each_release_once_and_the_evidence_is_timed():
    """eng/halt-380-verify: one admission read per distinct release, however many parked runs
    share it; still one entry per run (same fields), and every section's wall time is named."""
    from brambleloop.visual import image_production as IP
    from brambleloop.visual.image_records import ImageProductionRun, ensure_tables

    db = Database(f"sqlite:///{tempfile.mkdtemp()}/v.db")
    db.create_all()
    ensure_tables(db)
    with db.session() as s:
        for k in range(5):
            s.add(ImageProductionRun(run_key=f"r{k}", slug="a" if k < 4 else "b",
                                     version="1.0.0", release="ab" * 8,
                                     status=IP.SALE_WAITING))
    calls = []
    real = IP.sale_admission
    IP.sale_admission = lambda db_, *a: (calls.append(a), real(db_, *a))[1]
    try:
        v = pe.factory_visibility(db, now=NOW)
    finally:
        IP.sale_admission = real
    assert sorted(calls) == [("a", "1.0.0", "ab" * 8), ("b", "1.0.0", "ab" * 8)], calls
    assert [r["run"] for r in v["parked_admission"]] == ["a@1.0.0"] * 4 + ["b@1.0.0"], v
    assert all(set(r) == {"run", "admitted", "blockers"} and r["admitted"] is False
               for r in v["parked_admission"]), v
    assert v["parked_runs"] == 5 and isinstance(v["parked_admission_ms"], int), v
    assert v["image_runs_by_state"] == {IP.SALE_WAITING: 5}, v
    ev = pe.evidence(db, now=NOW)
    t = ev["timing_ms"]
    assert set(pe.SECTIONS) | {"factory_visibility"} <= set(t), sorted(t)
    assert all(isinstance(x, int) and x >= 0 for x in t.values()), t


if __name__ == "__main__":
    test_visibility_reports_jobs_activations_and_no_text()
    print("OK   test_visibility_reports_jobs_activations_and_no_text")
    test_parked_admission_reads_each_release_once_and_the_evidence_is_timed()
    print("OK   test_parked_admission_reads_each_release_once_and_the_evidence_is_timed")
