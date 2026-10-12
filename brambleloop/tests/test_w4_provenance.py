"""W4-PROVENANCE (F-718/F-733): the owner's canonical-model approval is held by the repository
(visual/approval_record.json, exported read-only from production) and compared with the
database's own model.frozen row; /api/model-identity serves the comparison."""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog  # noqa: E402
from brambleloop.visual import approval_record as ar, freeze  # noqa: E402

REC = ar.load()


def _db(freeze_detail=None):
    db = Database("sqlite://")
    db.create_all()
    if freeze_detail is not None:
        with db.session() as s:
            s.add(AuditLog(actor="creative_director", action="model.frozen",
                           detail={"freeze": freeze_detail}))
    return db


def test_the_record_pins_the_pack_the_code_approval_names():
    f = REC["freeze"]
    assert f["pack_version"] == freeze.OWNER_APPROVAL["approved_pack_version"]
    assert f["frozen"] is True and f["key"] == "brambleloop-canonical" and f["version"] == 1
    assert len(f["candidate_fingerprint"]) == 16
    assert REC["source"]["action"] == "model.frozen" and REC["source"]["audit_id"] == 5693


def test_the_record_carries_no_identity_description():
    assert "fields" not in REC["freeze"]
    assert set(REC["freeze"]) <= {"frozen", "key", "version", "approved_at", "pack_version",
                                  "built_at", "candidate_fingerprint"}


def test_a_matching_database_row_is_match():
    out = ar.compare(_db(dict(REC["freeze"], fields={"hair": "x"})))
    assert out["state"] == "MATCH" and out["mismatched_fields"] == []


def test_a_drifted_database_row_is_mismatch_and_names_the_field():
    out = ar.compare(_db(dict(REC["freeze"], candidate_fingerprint="0" * 16)))
    assert out["state"] == "MISMATCH" and out["mismatched_fields"] == ["candidate_fingerprint"]


def test_no_freeze_row_is_no_row_never_match():
    assert ar.compare(_db())["state"] == "NO_ROW"


def test_the_model_identity_route_serves_the_comparison():
    main = (ROOT / "src/brambleloop/app/main.py").read_text()
    assert '"approval_record": approval_record.compare(db)' in main


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
