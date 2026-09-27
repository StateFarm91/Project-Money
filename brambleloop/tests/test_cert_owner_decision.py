"""Certification: the owner can answer an approval card through the running system.

The improvement loop raises owner cards for gate-tier changes and challenger promotions, and
they wait on `cells.record_owner_approval` / `league.record_owner_decision`. Before this
route nothing in the running system could make those calls, so every owner-tier card was a
dead end. The route records the decision only; it never promotes by itself.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

TOKEN = "cert-owner-decision-token-0123456789"


def _client():
    os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/app.sqlite"
    os.environ["BRAMBLELOOP_OPS_TOKEN"] = TOKEN
    from fastapi.testclient import TestClient

    from brambleloop.app import main
    return TestClient(main.app), main


def test_the_owner_decision_route_records_and_refuses_what_it_should():
    from brambleloop.core.models import Improvement
    from brambleloop.improve import cells

    client, main = _client()
    auth = {"authorization": f"Bearer {TOKEN}"}
    with client as c:
        db = main.db
        cells.record_capability(db, "creative_assets", 0.5, sample=5)
        iid = cells.propose(db, cell="creative_assets",
                            hypothesis=("replace the certified chart source used by the "
                                        "fabric renderer with the photo derived stitch map"),
                            expected_effect="fewer blocked assets", rollback_ref="render:v1",
                            touches=("product_truth",), proposed_by="asset_truth")
        body = {"kind": "improvement", "id": iid,
                "why": "reviewed the sandbox and the regression replay myself"}
        assert c.post("/api/owner/decision", json=body).status_code == 401
        assert c.post("/api/owner/decision", json={**body, "why": "ok"},
                      headers=auth).status_code == 400          # a label is not a reason
        assert c.post("/api/owner/decision", json={**body, "kind": "anything"},
                      headers=auth).status_code == 400
        ok = c.post("/api/owner/decision", json=body, headers=auth)
        assert ok.status_code == 200, ok.text
        with db.session() as s:
            row = s.get(Improvement, iid)
            assert row.evidence["owner_approval"]["by"] == "owner"
            # Recording is not promoting: the loop still has to run its own checks.
            assert row.state != cells.PROMOTED


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing")
    sys.exit(1 if fails else 0)
