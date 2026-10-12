"""W4-ETSY403: a refused probe records the credential's shape (booleans only), never a value.

Etsy answers one 403 for a deactivated app and for a mistyped value. Production 0417f35 kept
neither Etsy's text nor anything about the configuration, so a paste error and an Etsy-side
state were indistinguishable. Etsy's text is kept since W4-ETSYCOMM; this adds the shape.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_w4_etsy403.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import socket
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _no_network(*_a, **_k):
    raise OSError("network refused by the W4-ETSY403 harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.intel import etsy_public as ep  # noqa: E402

KEY, SECRET = "abc123def456ghi789jkl012", "zyx987wvu6"
REFUSED = "API key not found or not active, or incorrect shared secret for API key."


@dataclass
class _R:
    status: int
    body: dict
    headers: dict = field(default_factory=dict)


class _T:
    def __init__(self, status, body):
        self.status, self.body, self.sent = status, body, []

    def request(self, method, url, *, headers, body=None, timeout=20.0):
        self.sent.append((method, url, dict(headers)))
        return _R(self.status, self.body)


def _db():
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/e403.sqlite")
    db.create_all()
    return db


def test_the_probe_sends_exactly_what_etsys_docs_specify():
    t = _T(200, {"application_id": 1})
    rec = ep.probe(_db(), transport=t, env={ep.KEYSTRING_VAR: f" {KEY}\n",
                                            ep.SECRET_VAR: f"{SECRET}\n"})
    assert rec["ok"] is True and len(t.sent) == 1
    method, url, headers = t.sent[0]
    assert method == "GET" and url == "https://openapi.etsy.com/v3/application/openapi-ping"
    assert headers["x-api-key"] == f"{KEY}:{SECRET}"  # trimmed, one colon, nothing else
    assert "credential_shape" not in rec


def test_a_refused_probe_records_a_clean_shape_and_etsys_words_only():
    rec = ep.probe(_db(), transport=_T(403, {"error": REFUSED}),
                   env={ep.KEYSTRING_VAR: KEY, ep.SECRET_VAR: SECRET})
    shape = rec["credential_shape"]
    assert shape["keystring_alphanumeric"] and shape["secret_alphanumeric"]
    assert not any(shape[k] for k in ("colon_inside_a_value", "quotes_inside_a_value",
                                      "inner_whitespace", "etsy_keystring_differs"))
    assert rec["etsy_error"] == REFUSED
    assert KEY not in repr(rec) and SECRET not in repr(rec)
    assert all(isinstance(v, bool) for v in shape.values()), shape


def test_paste_errors_are_named_without_revealing_the_value():
    cases = [({ep.KEYSTRING_VAR: f"{KEY}:{SECRET}", ep.SECRET_VAR: SECRET},
              "colon_inside_a_value"),
             ({ep.KEYSTRING_VAR: f'"{KEY}"', ep.SECRET_VAR: SECRET}, "quotes_inside_a_value"),
             ({ep.KEYSTRING_VAR: KEY, ep.SECRET_VAR: "zyx 987"}, "inner_whitespace"),
             ({ep.KEYSTRING_VAR: KEY, ep.SECRET_VAR: SECRET,
               "ETSY_KEYSTRING": "otherkey000000000000000"}, "etsy_keystring_differs")]
    assert len(cases) == 4
    for env, flag in cases:
        assert env
        rec = ep.probe(_db(), transport=_T(403, {"error": REFUSED}), env=env)
        assert rec["credential_shape"][flag] is True, (flag, rec["credential_shape"])
        for v in env.values():
            assert v.strip('"') not in repr(rec["credential_shape"])


def test_a_server_fault_records_no_shape():
    rec = ep.probe(_db(), transport=_T(500, {}),
                   env={ep.KEYSTRING_VAR: KEY, ep.SECRET_VAR: SECRET})
    assert rec["ok"] is False and "credential_shape" not in rec


def _run() -> int:
    failures = 0
    tests = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        try:
            fn()
            print(f"OK   {name}")
        except Exception as exc:  # noqa: BLE001
            import traceback

            failures += 1
            print(f"FAIL {name}: {exc}")
            traceback.print_exc()
    print(f"{len(tests) - failures} passed, {failures} failed")
    return failures


if __name__ == "__main__":
    raise SystemExit(1 if _run() else 0)
