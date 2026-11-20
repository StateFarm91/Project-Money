"""W4-FM2 / F-159: the release secret-scan patterns also guard the production runtime's logs.

The release scan (`tests/test_secret_scan.py`) never saw what the deployed service writes to
its log. `ops.log_secret_guard` is attached at start-up of the web service
(`app.access_log.install`, run at `app.main` import), the worker and the scheduler; it redacts
any secret in a record before the line is emitted and counts the catch by fingerprint, and its
CLI scans an exported log window at release (exit 1 on a finding).

Every "secret" below is assembled at runtime from fragments and is fake.
Run: cd brambleloop && PYTHONPATH=src $PY tests/test_w4_fm2_log_secret_guard.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import io
import logging
import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from brambleloop.ops import log_secret_guard as G  # noqa: E402

# Fake, assembled so this file carries no secret-shaped literal.
FAKE_BEARER = "Bear" + "er " + "Q" * 30
FAKE_DB = "postgres" + "ql://svc:" + "x" * 12 + "@db.internal"
FAKE_GH = "gh" + "p_" + "A" * 36


def _logger(name: str):
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
    log = logging.getLogger(name)
    log.handlers[:] = [handler]
    log.propagate = False
    log.setLevel(logging.INFO)
    return log, handler, stream


def test_patterns_are_byte_identical_to_the_release_scan():
    import importlib.util

    spec = importlib.util.spec_from_file_location("secret_scan_mod",
                                                  ROOT / "tests" / "test_secret_scan.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.PATTERNS, "release scan has no patterns"
    assert set(mod.PATTERNS) == set(G.PATTERNS), set(mod.PATTERNS) ^ set(G.PATTERNS)
    for name, pat in mod.PATTERNS.items():
        assert G.PATTERNS[name].pattern == pat.pattern, name
        assert G.PATTERNS[name].flags == pat.flags, name


def test_a_secret_logged_by_the_service_never_reaches_the_handler():
    log, handler, stream = _logger("fm2.guard.case1")
    handler.addFilter(G.GUARD)
    log.info("provider said %s while connecting to %s", FAKE_BEARER, FAKE_DB)
    out = stream.getvalue()
    assert out, "nothing was logged"
    assert "Q" * 30 not in out and "x" * 12 not in out, out
    assert out.count("***") >= 2, out
    caught = {(c["pattern"], c["logger"]) for c in G.summary()["caught"]}
    assert ("bearer_token", "fm2.guard.case1") in caught, caught
    assert ("db_url_password", "fm2.guard.case1") in caught, caught
    assert "Q" * 30 not in str(G.summary()), "the summary must never carry the value"


def test_an_exception_carrying_a_secret_is_redacted_not_printed():
    log, handler, stream = _logger("fm2.guard.case2")
    handler.addFilter(G.GUARD)
    try:
        raise RuntimeError(f"auth failed for {FAKE_GH}")
    except RuntimeError:
        log.exception("call failed")
    out = stream.getvalue()
    assert "call failed" in out and "A" * 36 not in out, out
    assert "exception redacted by F-159 guard" in out, out


def test_a_clean_line_is_untouched_and_never_dropped():
    log, handler, stream = _logger("fm2.guard.case3")
    handler.addFilter(G.GUARD)
    log.info("published %d listings in %s", 3, "shadow")
    assert stream.getvalue().strip() == "INFO fm2.guard.case3 published 3 listings in shadow"


def test_an_unscannable_record_is_suppressed_rather_than_printed_raw():
    class Hostile:
        def __str__(self):
            raise ValueError("cannot render")

    rec = logging.LogRecord("fm2.guard.case4", logging.INFO, __file__, 1, "%s", (Hostile(),),
                            None)
    assert G.GUARD.filter(rec) is True
    assert "suppressed rather than logged" in rec.getMessage()


def test_install_is_idempotent_and_covers_root_and_server_loggers():
    first = G.install()
    second = G.install()
    assert first == second and "root" in first and "uvicorn.access" in first
    assert logging.getLogger().filters.count(G.GUARD) == 1
    assert logging.getLogger("uvicorn.access").filters.count(G.GUARD) == 1


def test_every_service_entrypoint_installs_the_guard():
    from brambleloop.app import access_log

    access_log.install()
    assert G.GUARD in logging.getLogger("uvicorn.access").filters
    for entry in ("app/worker_entry.py", "app/scheduler_entry.py"):
        src = (ROOT / "src" / "brambleloop" / entry).read_text()
        assert "log_secret_guard" in src and "_log_secret_guard.install()" in src, entry


def test_the_release_cli_fails_on_an_exported_log_window_with_a_secret():
    d = Path(tempfile.mkdtemp(prefix="fm2_logs_"))
    dirty, clean = d / "dirty.log", d / "clean.log"
    dirty.write_text(f"2026-10-07 INFO boot\n2026-10-07 ERROR {FAKE_BEARER}\n")
    clean.write_text("2026-10-07 INFO boot\n2026-10-07 INFO ok\n")
    assert G.main(["scan", str(dirty)]) == 1
    assert G.main(["scan", str(clean)]) == 0
    assert G.main(["scan", str(d / "missing.log")]) == 1, "an unread log is not clean"
    findings = G.scan_text(dirty.read_text())
    assert findings and findings[0][:2] == (2, "bearer_token"), findings


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]


def main() -> int:
    assert TESTS, "no tests collected"
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"OK   {t.__name__}")
        except Exception:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__}")
            traceback.print_exc()
    print(f"{len(TESTS) - failed}/{len(TESTS)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
