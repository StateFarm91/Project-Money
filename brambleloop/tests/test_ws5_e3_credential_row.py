"""WS5 E3: "Etsy credential usable" means usable, not configured.

`etsy_public.health()["usable"]` is true whenever the keystring and secret are set, so the
readback row read PASS through the whole 403 period. The row now reads
`/api/etsy` `credential.usable`: a successful `etsy.probe` within 24 h, an OAuth grant this
deployment can open, and every needed scope (transactions_r included) granted. A refused or
stale read, a missing grant, or a missing scope is not usable, and the row reads WARN (never
PASS) without blocking a deploy.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_ws5_e3_credential_row.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT.parent / "ops"))

import readback  # noqa: E402

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog  # noqa: E402
from brambleloop.integrations import etsy_oauth  # noqa: E402
from brambleloop.intel import etsy_public as EP  # noqa: E402

NOW = datetime(2026, 11, 12, 7, 0, tzinfo=timezone.utc)
ENV = {"ETSY_API_KEY": "k" * 24, "ETSY_SHARED_SECRET": "s" * 12}


def _db():
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='ws5e3_')}/e.sqlite", scratch=True)
    db.create_all()
    return db


def _probe(db, *, ok, hours_ago=1, status=None):
    with db.session() as s:
        s.add(AuditLog(actor="market_radar", action="etsy.probe", artifact="ping", detail={
            "at": (NOW - timedelta(hours=hours_ago)).isoformat(), "ok": ok,
            **({"status": status, "reason": f"ping returned HTTP {status}"} if status else {})}))


def _oauth(openable=True, scopes=etsy_oauth.SCOPES_WANTED):
    return (patch("brambleloop.core.oauth_store.credential_health",
                  return_value={"openable": openable}),
            patch("brambleloop.core.oauth_store.stored_scopes", return_value=tuple(scopes)))


def _usable(db):
    a, b = _oauth()
    with a, b:
        return EP.credential_usable(db, env=ENV, now=NOW)


def test_configured_but_refused_is_not_usable_and_names_why():
    db = _db()
    _probe(db, ok=False, status=403)
    assert EP.health(ENV)["usable"] is True              # the old, configuration-only reading
    c = _usable(db)
    assert c["usable"] is False and c["refused"] is True and "etsy.probe" in c["why"], c


def test_a_recent_read_an_openable_grant_and_every_scope_is_usable():
    db = _db()
    _probe(db, ok=True, hours_ago=2)
    c = _usable(db)
    assert c["usable"] is True and c["why"] == "" and c["scopes_not_granted"] == [], c


def test_a_stale_read_a_missing_grant_or_a_missing_scope_is_not_usable():
    db = _db()
    _probe(db, ok=True, hours_ago=EP.PROBE_FRESH_HOURS + 1)
    assert _usable(db)["usable"] is False
    db = _db()
    _probe(db, ok=True)
    a, b = _oauth(openable=False)
    with a, b:
        assert EP.credential_usable(db, env=ENV, now=NOW)["usable"] is False
    a, b = _oauth(scopes=[s for s in etsy_oauth.SCOPES_WANTED if s != "transactions_r"])
    with a, b:
        c = EP.credential_usable(db, env=ENV, now=NOW)
    assert c["usable"] is False and c["scopes_not_granted"] == ["transactions_r"], c
    assert _usable(_db())["usable"] is False             # never probed: not usable


def test_the_readback_row_reads_the_judgement_and_warns_never_passes():
    row = next(r for r in readback.MANIFEST if r[0] == "Etsy credential usable")
    assert row[3] == "credential.usable" and row[6] == readback.WARN_ONLY, row
    body = {"usable": True, "credential": {"usable": False}}      # configured, not usable
    assert readback._dig(body, row[3]) is False
    assert row[5](readback._dig(body, row[3]), body) is False
    assert row[5](readback._dig({"credential": {"usable": True}}, row[3]), {}) is True


def test_api_etsy_carries_the_judgement():
    db = _db()
    _probe(db, ok=False, status=403)
    a, b = _oauth()
    with a, b:
        cap = EP.capability(db, env=ENV)
    assert cap["usable"] is True and cap["credential"]["usable"] is False, cap


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc()
                print("FAIL", name, repr(e))
    print(f"PASS: {fails} failing" if not fails else f"FAILED: {fails} failing")
    sys.exit(1 if fails else 0)
