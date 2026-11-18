"""Review 6980322299: the Store tab's "Shop authorised for" read the stored scope STRING as a
list of characters ("l, i, s, t, ...") and listed every scope as still needed.

The credential is saved through the real `oauth_store.save_refresh_token` with Etsy's own
space-separated scope string, then `etsy_connect.status` is read as the Store tab reads it.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_cc_etsy_connect_scopes.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
SEAL_KEY = "a-sealing-key-for-the-store-tab-scopes-test-1234567890"
os.environ["BRAMBLELOOP_SECRET_KEY"] = SEAL_KEY

from brambleloop.app.command_center import etsy_connect  # noqa: E402
from brambleloop.core import oauth_store  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402

GRANTED = "listings_r listings_w listings_d shops_r shops_w transactions_r"


def _db():
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='ccscopes_')}/s.sqlite")
    db.create_all()
    return db


def test_the_store_tab_reads_the_stored_scope_string_as_scopes():
    db = _db()
    oauth_store.save_refresh_token(db, "111.grant", scopes=GRANTED, new_grant=True,
                                   source="authorization-code grant",
                                   env={"BRAMBLELOOP_SECRET_KEY": SEAL_KEY})
    assert isinstance(oauth_store.credential_health(db).get("scopes"), str)   # the real shape
    grant = etsy_connect.status(db)["grant"]
    assert grant["stored"] is True
    assert grant["scopes"] == GRANTED.split(), grant["scopes"]
    # Every scope this company asks for is in that grant, so nothing reads as still needed.
    wanted = etsy_connect.status(db)["authorise"]["scopes"]
    assert set(wanted) <= set(GRANTED.split()), wanted
    assert grant["missing_scopes"] == [], grant["missing_scopes"]


def test_a_partial_grant_names_exactly_what_is_missing():
    db = _db()
    oauth_store.save_refresh_token(db, "111.partial", scopes="listings_r shops_r",
                                   new_grant=True, source="authorization-code grant",
                                   env={"BRAMBLELOOP_SECRET_KEY": SEAL_KEY})
    status = etsy_connect.status(db)
    grant = status["grant"]
    assert grant["scopes"] == ["listings_r", "shops_r"]
    wanted = status["authorise"]["scopes"]
    assert grant["missing_scopes"] == [s for s in wanted if s not in ("listings_r", "shops_r")]
    assert all(len(s) > 1 for s in grant["missing_scopes"])           # never characters


def test_no_stored_grant_reads_no_scopes_and_everything_missing():
    db = _db()
    status = etsy_connect.status(db)
    assert status["grant"]["scopes"] == []
    assert status["grant"]["missing_scopes"] == status["authorise"]["scopes"]


if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK   {name}")
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print(f"FAIL {name} {exc!r}"[:500])
                import traceback

                traceback.print_exc()
    print(f"{failed} failed")
    sys.exit(1 if failed else 0)
