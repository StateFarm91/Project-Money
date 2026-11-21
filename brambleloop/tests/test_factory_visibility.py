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
    text = json.dumps(v)
    assert "inputs" not in text and "last_error" not in text
    ev = pe.evidence(db, now=NOW)
    assert "factory_visibility" in json.dumps(ev)


if __name__ == "__main__":
    test_visibility_reports_jobs_activations_and_no_text()
    print("OK   test_visibility_reports_jobs_activations_and_no_text")
