"""A credential is not a capability, and Etsy says so more clearly than most.

The owner's condition when the developer application was approved on 2026-09-19: the gate
opens from a demonstrated successful read, never from the variables existing.

That is not a general principle applied defensively. Etsy v3 refuses the keystring alone with
"Shared secret is required in x-api-key header", so a half-configured credential returns 403
and looks exactly like a working one to anything that checks whether two environment
variables are set. The same lesson the model provider taught the same morning, with a
narrower and more likely failure.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.build2 import executor as E  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.intel import etsy_public as EP  # noqa: E402

CREDENTIAL = {"ETSY_API_KEY": "keystring", "ETSY_SHARED_SECRET": "secret"}


def _db() -> Database:
    tmp = tempfile.mkdtemp()
    db = Database(f"sqlite:///{tmp}/etsy.sqlite")
    db.create_all()
    return db


class _Response:
    def __init__(self, status: int, body: dict):
        self.status = status
        self.body = body
        self.headers: dict[str, str] = {}


class _Transport:
    """Stands in for the network, and records what was asked of it."""

    def __init__(self, response: _Response):
        self.response = response
        self.calls: list[str] = []
        self.headers: list[dict] = []

    def request(self, method, url, *, headers, body=None, timeout=20.0):
        self.calls.append(url)
        self.headers.append(headers)
        return self.response


# ---- the gate reads a read, not a variable --------------------------------


def test_variables_alone_do_not_open_the_gate():
    db = _db()

    assert E.GATE_BY_KEY["etsy_api"].open(db, CREDENTIAL) is False
    assert E.GATE_BY_KEY["benchmark_observation"].open(db, CREDENTIAL) is False


def test_a_successful_read_opens_both_gates():
    db = _db()
    transport = _Transport(_Response(200, {"application_id": 1516181443672}))

    record = EP.probe(db, transport=transport, env=CREDENTIAL)

    assert record["ok"] is True
    assert record["application_id"] == 1516181443672
    assert EP.usable(db) is True
    assert E.GATE_BY_KEY["etsy_api"].open(db, {}) is True
    assert E.GATE_BY_KEY["benchmark_observation"].open(db, {}) is True


def test_the_keystring_alone_is_the_failure_this_guards_against():
    """Etsy refuses it, and an environment-variable check cannot tell the difference."""
    db = _db()

    record = EP.probe(db, env={"ETSY_API_KEY": "keystring"})

    assert record["ok"] is False
    assert "Shared secret is required" in record["reason"]
    assert EP.usable(db) is False


def test_a_rejected_credential_leaves_the_gate_closed():
    db = _db()
    transport = _Transport(_Response(403, {"error": "invalid api key"}))

    record = EP.probe(db, transport=transport, env=CREDENTIAL)

    assert record["ok"] is False
    assert EP.usable(db) is False
    assert E.GATE_BY_KEY["benchmark_observation"].open(db, {}) is False


def test_no_probe_is_unknown_rather_than_unavailable():
    report = EP.capability(_db(), CREDENTIAL)

    assert report["last_probe"] is None
    assert report["demonstrated"] is False
    assert "not the same as unavailable" in report["note"]


# ---- the probe is the smallest thing that could demonstrate it ------------


def test_the_probe_reads_the_ping_and_nothing_about_anybody_s_shop():
    db = _db()
    transport = _Transport(_Response(200, {"application_id": 1}))

    EP.probe(db, transport=transport, env=CREDENTIAL)

    assert len(transport.calls) == 1
    assert transport.calls[0].endswith("/v3/application/openapi-ping")


def test_the_probe_sends_the_header_form_etsy_actually_requires():
    db = _db()
    transport = _Transport(_Response(200, {"application_id": 1}))

    EP.probe(db, transport=transport, env=CREDENTIAL)

    assert transport.headers[0]["x-api-key"] == "keystring:secret"


def test_nothing_about_the_credential_reaches_the_recorded_row():
    import json

    from sqlalchemy import select

    from brambleloop.core.models import AuditLog

    db = _db()
    EP.probe(db, transport=_Transport(_Response(200, {"application_id": 1})),
             env=CREDENTIAL)

    with db.session() as s:
        rows = [json.dumps(a.detail) for a in s.scalars(select(AuditLog))]

    blob = " ".join(rows)
    assert "keystring" not in blob
    assert "secret" not in blob


def test_a_failure_records_the_reason_rather_than_a_paraphrase():
    db = _db()
    transport = _Transport(_Response(404, {"error": "not found"}))

    EP.probe(db, transport=transport, env=CREDENTIAL)

    assert "404" in EP.last_probe(db)["reason"]


def _run() -> int:
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK   {name}")
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f"FAIL {name}: {exc}")
    return failures


if __name__ == "__main__":
    raise SystemExit(1 if _run() else 0)
