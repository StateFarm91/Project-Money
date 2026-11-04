"""An unsent draft or malformed timing cannot certify customer service."""
from datetime import datetime, timezone

import pytest

from brambleloop.core.db import Database
from brambleloop.core.models import LedgerEntry, SupportCase
from brambleloop.support import service


def _case(db, detail=None):
    with db.session() as session:
        case = SupportCase(customer_ref="fixture", question="fixture", answer="",
                           specialist="download", escalated=False, resolved=False,
                           sent=False, detail=detail or {})
        session.add(case)
        session.flush()
        return case.id


def test_held_draft_cannot_certify_delivered_service(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'support.db'}", scratch=True)
    db.create_all()
    sent, held = _case(db), _case(db)
    service.record_response(db, sent, minutes=2, from_canonical=True, measured_as="sent")
    service.record_response(db, held, minutes=1, from_canonical=True, measured_as="draft_ready")
    result = service.service_level(db, now=datetime.now(timezone.utc))
    assert result["timed"] == 1 and result["untimed"] == 1
    assert result["draft_ready"]["cases"] == 1
    assert result["meets_target"] is None
    service.record_response(db, held, minutes=3, from_canonical=True, measured_as="sent")
    result = service.service_level(db, now=datetime.now(timezone.utc))
    assert result["timed"] == 2 and result["untimed"] == 0
    assert result["meets_target"] is True


def test_invalid_timing_refused_and_legacy_invalid_data_remains_untimed(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'support.db'}", scratch=True)
    db.create_all()
    case = _case(db)
    for value in (-1, float("nan"), float("inf"), True, "2"):
        with pytest.raises(service.ServiceRefused):
            service.record_response(db, case, minutes=value, from_canonical=True)
    _case(db, {"response_minutes": "not-a-number", "response_measured_as": "sent"})
    result = service.service_level(db, now=datetime.now(timezone.utc))
    assert result["cases"] == 2 and result["timed"] == 0 and result["untimed"] == 2
    assert result["meets_target"] is None


def test_display_rounding_does_not_make_a_below_floor_result_pass(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'support.db'}", scratch=True)
    db.create_all()
    with db.session() as session:
        for index in range(2500):
            session.add(SupportCase(customer_ref=f"fixture-{index}", question="fixture",
                answer="", specialist="download", escalated=False, resolved=False, sent=False,
                detail={"response_minutes": 1 if index < 2249 else 10,
                        "response_measured_as": "sent"}))
    result = service.service_level(db, now=datetime.now(timezone.utc))
    assert result["canonical"]["within_target"] == 0.9  # displayed to three decimals
    assert result["meets_target"] is False  # 2249/2500 is below 90%


def test_sale_rows_do_not_prove_support_speed_caused_or_correlated_with_refunds(tmp_path, monkeypatch):
    db = Database(f"sqlite:///{tmp_path / 'support.db'}", scratch=True)
    db.create_all()
    with db.session() as session:
        # Both rows intentionally cite the same synthetic source: rows are not
        # necessarily distinct orders and no case-to-order comparison exists.
        session.add_all([
            LedgerEntry(category="sale", evidence_ref="fixture-sale", refunds_cad=1.0),
            LedgerEntry(category="sale", evidence_ref="fixture-sale", refunds_cad=float("inf")),
        ])
    result = service.refund_impact(db)
    assert result["measurable"] is False
    assert result["orders"] is None and result["refund_rate"] is None
    assert result["sale_rows"] == 2
    assert result["sale_rows_with_positive_recorded_refunds"] == 1
    assert result["sale_rows_with_invalid_refunds"] == 1
    assert result["service_level"]["meets_target"] is None
    # Exercise the actual reporting endpoint without lifespan startup or I/O.
    from fastapi.testclient import TestClient
    from brambleloop.core import opsauth

    monkeypatch.setenv("BRAMBLELOOP_DATABASE_URL", f"sqlite:///{tmp_path / 'support.db'}")
    monkeypatch.setenv(opsauth.TOKEN_VAR, "test-operator-token-for-fixtures-only")
    from brambleloop.app import main

    monkeypatch.setattr(main, "db", db)
    response = TestClient(main.app).get("/api/trust", headers={
        "Authorization": "Bearer test-operator-token-for-fixtures-only"})
    assert response.status_code == 200
    assert response.json()["refund_impact"]["measurable"] is False
