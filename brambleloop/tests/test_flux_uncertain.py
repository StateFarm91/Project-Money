"""FLUX UNCERTAIN (19i19): a paid-provider call that provably was never accepted releases its
reservation; only a call that may have been billed stays UNCERTAIN.

Production: FLUX calls_in_window_by_status {UNCERTAIN: 9..30, BILLED: 21}; CA$4.90 of the
CA$5 daily ceiling held by UNCERTAIN reservations, most of them `403 not_authenticated` from
the submit endpoint, while BFL billed cents.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import io
import json
import os
import socket
import sys
import tempfile
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
_TMP = tempfile.mkdtemp(prefix="flux_uncertain_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'app.db')}"
os.environ.pop("DATABASE_URL", None)
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ["BRAMBLELOOP_EMBEDDED_WORKER"] = "0"
os.environ["BRAMBLELOOP_PHASE"] = "shadow"
for _k in list(os.environ):
    if _k.startswith(("ANTHROPIC_API", "OPENAI", "BRAMBLELOOP_IMAGE_KEY",
                      "BRAMBLELOOP_IMAGE_PROVIDER", "BRAMBLELOOP_MODEL_MONTHLY")):
        os.environ.pop(_k)


def _no_network(*_a, **_k):
    raise OSError("network refused by the FLUX-UNCERTAIN harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from sqlalchemy import select  # noqa: E402

import _paid_activation  # noqa: E402
from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.gateway import anthropic as gw  # noqa: E402
from brambleloop.gateway import images  # noqa: E402
from brambleloop.gateway import paid_provider_gate as G  # noqa: E402
from brambleloop.runtime import worker as W  # noqa: E402

FLUX = "flux-3-image"
KEY = "bfl_" + "k" * 40
ENV = {"BRAMBLELOOP_IMAGE_KEY_BFL": KEY, "BRAMBLELOOP_IMAGE_PROVIDER": FLUX}


def _db():
    db = Database(f"sqlite:///{tempfile.mkdtemp(dir=_TMP)}/t.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    G.ensure_tables(db)
    return db


def _rows(db):
    with db.session() as s:
        return [(r.status, r.error) for r in s.scalars(
            select(G.PaidProviderCall).order_by(G.PaidProviderCall.id))]


class _Resp:
    def __init__(self, body):
        self._b = json.dumps(body).encode()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self._b


class _Opener:
    """The transport under `images._post`/`_get`: scripted answers, nothing leaves."""

    def __init__(self, *answers):
        self.answers = list(answers)

    def open(self, request, timeout=None):
        a = self.answers.pop(0)
        if isinstance(a, BaseException):
            raise a
        return _Resp(a)


def _http(code, detail):
    return urllib.error.HTTPError("https://api.bfl.ai/v1/x", code, "err", {},
                                  io.BytesIO(json.dumps({"detail": detail}).encode()))


_N = [0]


def _render(db, opener):
    # a distinct request each time: the gate's per-request attempt limit is not the subject
    _N[0] += 1
    saved = images._no_redirect
    images._no_redirect = lambda: opener
    try:
        with tempfile.TemporaryDirectory(dir=_TMP) as wd:
            return images.generate(f"A plain grey swatch {_N[0]}, product photograph.", env=ENV,
                                   provider_key=FLUX, work_dir=wd, db=db,
                                   purpose="test.render")
    finally:
        images._no_redirect = saved


def _expect_fail(db, opener):
    try:
        _render(db, opener)
    except BaseException as exc:  # noqa: BLE001
        return exc
    raise AssertionError("the render did not fail")


def _env():
    saved = {k: os.environ.get(k) for k in ENV}
    os.environ.update(ENV)
    return saved


def _restore(saved):
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


# ---- the judge, on the strings the gate records ---------------------------------------------

def test_never_accepted_reads_only_proof_of_refusal():
    yes = {
        'ImagesRefused: flux-3-image 403: {"detail": "not_authenticated"}': "http_403",
        "ImagesRefused: flux-3-image 401: {}": "http_401",
        "ImagesRefused: flux-3-image 422: {\"detail\": [...]}": "http_422",
        "TransientError: flux-3-image 429: slow down": "http_429",
        "QuotaUnavailable: flux-3-image 402: no credit. This is the account's": "http_402",
        "TransientError: flux-3-image unreachable: [Errno -2] Name or service not known":
            "unreachable",
    }
    assert len(yes) == 6
    for err, why in yes.items():
        assert G.never_accepted(err) == why, err
    for err in ("TransientError: flux-3-image 503: busy",            # 5xx: may sit in front
                "TransientError: flux-3-image 502: bad gateway",
                "TimeoutError: The read operation timed out",       # sent, answer lost
                "ConnectionResetError: after possible send",
                "JSONDecodeError: Expecting value",                 # unreadable 2xx
                "TransientError: flux-3-image poll 403",              # after a task id
                "TransientError: flux-3-image poll unreachable: x",
                "TransientError: flux-3-image did not finish within 120s",
                "conflicting provider outcomes; reconciliation required",
                "invalid provider usage; counted at the reserved estimate", "", None):
        assert G.never_accepted(err) is None, err


# ---- live: the classifier at the call ------------------------------------------------------

def test_submit_403_releases_the_reservation_and_does_not_hold_the_ceiling():
    db = _db()
    _paid_activation.activate(db, FLUX, G.GENERATION, daily=5.0)
    saved = _env()
    try:
        for _ in range(3):
            _expect_fail(db, _Opener(_http(403, "not_authenticated")))
        rows = _rows(db)
        assert len(rows) == 3 and all(st == G.RELEASED for st, _e in rows), rows
        with db.session() as s:
            assert G.uncovered_company_exposure(s) == 0.0
    finally:
        _restore(saved)


def test_submit_4xx_and_unreachable_release_but_a_timeout_or_5xx_stays_uncertain():
    db = _db()
    _paid_activation.activate(db, FLUX, G.GENERATION, daily=5.0)
    saved = _env()
    try:
        for exc in (_http(401, "x"), _http(422, "bad"), _http(429, "rate"),
                    urllib.error.URLError(ConnectionRefusedError(111, "refused"))):
            _expect_fail(db, _Opener(exc))
        assert [st for st, _e in _rows(db)] == [G.RELEASED] * 4, _rows(db)
        for exc in (TimeoutError("The read operation timed out"), _http(503, "busy"),
                    ConnectionResetError("reset after send")):
            _expect_fail(db, _Opener(exc))
        assert [st for st, _e in _rows(db)][4:] == [G.UNCERTAIN] * 3, _rows(db)
    finally:
        _restore(saved)


def test_accepted_then_poll_failure_is_never_released():
    db = _db()
    _paid_activation.activate(db, FLUX, G.GENERATION, daily=5.0)
    saved = _env()
    real_sleep = images.time.sleep
    images.time.sleep = lambda *_a: None
    try:
        accepted = {"id": "task-1", "polling_url": "https://api.bfl.ai/v1/get_result?id=1"}
        _expect_fail(db, _Opener(accepted, _http(403, "not_authenticated")))
        _expect_fail(db, _Opener(accepted, urllib.error.URLError("unreachable")))
        rows = _rows(db)
        assert len(rows) == 2 and all(st == G.BILLED for st, _e in rows), rows
        assert G.reclassify_uncertain(db) == []
        assert [st for st, _e in _rows(db)] == [G.BILLED, G.BILLED]
    finally:
        images.time.sleep = real_sleep
        _restore(saved)


# ---- legacy rows: reclassified from the stored evidence ------------------------------------

def _legacy(db, error, *, actual=None, status=G.UNCERTAIN, estimate=0.1):
    with db.session() as s:
        row = G.PaidProviderCall(activation_id=1, provider=FLUX, scope=G.GENERATION,
                                 gallery="g", run_key="r", idem_key=os.urandom(8).hex(),
                                 fingerprint="f", estimate_cad=estimate, actual_cad=actual,
                                 status=status, error=error,
                                 at=datetime.now(timezone.utc) - timedelta(hours=3))
        s.add(row)
        s.flush()
        return row.id


def test_existing_uncertain_rows_are_reclassified_from_stored_evidence():
    db = _db()
    ids = {
        "403": _legacy(db, 'ImagesRefused: flux-3-image 403: {"detail": "not_authenticated"}'),
        "429": _legacy(db, "TransientError: flux-3-image 429: too many"),
        "dns": _legacy(db, "TransientError: flux-3-image unreachable: [Errno -2] no host"),
        "timeout": _legacy(db, "TimeoutError: The read operation timed out"),
        "503": _legacy(db, "TransientError: flux-3-image 503: busy"),
        "conflict": _legacy(db, "conflicting provider outcomes; reconciliation required"),
        "actual": _legacy(db, "ImagesRefused: flux-3-image 403: x", actual=0.07),
        "billed": _legacy(db, "ImagesRefused: flux-3-image 403: x", status=G.BILLED),
    }
    with db.session() as s:
        before = G.uncovered_company_exposure(s)
    out = G.reclassify_uncertain(db)
    assert sorted(r["id"] for r in out) == sorted([ids["403"], ids["429"], ids["dns"]]), out
    assert {r["reason"] for r in out} == {"http_403", "http_429", "unreachable"}
    with db.session() as s:
        by = {r.id: r for r in s.scalars(select(G.PaidProviderCall))}
        for k in ("403", "429", "dns"):
            assert by[ids[k]].status == G.RELEASED, k
            assert by[ids[k]].error.startswith("reclassified: never accepted"), k
        for k in ("timeout", "503", "conflict", "actual"):
            assert by[ids[k]].status == G.UNCERTAIN, k
        assert by[ids["billed"]].status == G.BILLED
        after = G.uncovered_company_exposure(s)
    assert after < before
    assert G.reclassify_uncertain(db) == [], "reclassification is idempotent"


def test_reclassification_runs_on_the_boot_tick():
    db = _db()
    rid = _legacy(db, 'ImagesRefused: flux-3-image 403: {"detail": "not_authenticated"}')
    W._BACKOFF_CLAMPED_AT_BOOT.discard(id(db))
    sched = W.Scheduler(db)
    sched.tick()
    assert [r["id"] for r in sched.uncertain_reclassified] == [rid], \
        sched.uncertain_reclassified
    assert _rows(db)[0][0] == G.RELEASED


if __name__ == "__main__":
    assert not gw.budget_lock_held()
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback
                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing")
    sys.exit(1 if fails else 0)
