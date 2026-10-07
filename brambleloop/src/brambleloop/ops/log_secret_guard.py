"""The secret-scan gate applied to the production runtime's own logs (F-159).

`tests/test_secret_scan.py` scans every tracked and generated file before release, but what
the deployed service *writes to its log* never passed through it: a credential that reaches
`log.info(...)`, an exception message carrying a connection string, a provider error that
echoes a bearer token -- all of it goes to the platform's log store, which this repository
cannot reach and nobody re-reads.

This module closes that in two places, with the same patterns as the release scan (the
parity test `tests/test_w4_fm2_log_secret_guard.py` holds them byte-identical):

* **in process** -- `install()` attaches `SecretLogGuard` to the root handlers and the web
  server's loggers at start-up (`app.access_log.install` for the web service, the worker and
  scheduler entrypoints for theirs). Every record is scanned *as formatted*; a match is
  replaced by `***<fingerprint>` before the line is emitted, so the secret never reaches the
  platform's log store. The guard never drops a record and never raises: a record it cannot
  scan is replaced wholesale rather than printed raw. Each catch is counted by pattern and
  fingerprint (never the value) for `summary()`.
* **at release** -- `python -m brambleloop.ops.log_secret_guard scan <exported-log-file>`
  scans a log window exported read-only from the deployed service and exits 1 on any finding,
  printing pattern, line and fingerprint only. That is the release step the deploy record
  cites; this module makes no network call.
"""
from __future__ import annotations

import hashlib
import logging
import re
import sys
import threading
from collections import Counter

# Built from fragments so this file does not match its own patterns when it is scanned.
# Must stay identical to tests/test_secret_scan.PATTERNS (parity test).
_SK = "sk" + "-"
PATTERNS: dict[str, re.Pattern] = {
    "anthropic_key": re.compile(_SK + r"ant-[a-z]+\d*-[A-Za-z0-9_\-]{20,}"),
    "openai_key": re.compile(_SK + r"(?!ant-)(?:proj-|svcacct-|admin-)?[A-Za-z0-9_\-]{20,}"
                             r"T3Blbk" + r"FJ[A-Za-z0-9_\-]{10,}|"
                             + _SK + r"(?:proj|svcacct|admin)-[A-Za-z0-9_\-]{40,}"),
    "aws_access_key_id": re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    "aws_secret_access_key": re.compile(
        r"(?i)aws_?secret_?access_?key[\"']?\s*[:=]\s*[\"']?[A-Za-z0-9/+=]{40}\b"),
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP |ENCRYPTED )?"
                              r"PRIVATE KEY(?: BLOCK)?-----"),
    "bearer_token": re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/\-]{24,}=*"),
    "etsy_oauth_token": re.compile(r"\b\d{5,12}\.[A-Za-z0-9_\-]{50,}"),
    "etsy_keystring": re.compile(r"(?i)(?:etsy[_\-]?(?:api[_\-]?)?key(?:string)?|keystring|"
                                 r"x-api-key)[\"']?\s*[:=]\s*[\"']?[a-z0-9]{24}\b"),
    "github_token": re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36}\b|"
                               r"\bgithub_pat_[A-Za-z0-9_]{50,}"),
    "stripe_live_key": re.compile(r"\b(?:sk|rk)_live_[A-Za-z0-9]{20,}"),
    "slack_token": re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{20,}"),
    "db_url_password": re.compile(r"\b(?:postgres(?:ql)?|mysql|redis|amqp)(?:\+\w+)?://"
                                  r"[^\s:/@\"'<>{}$*]+:[^\s@/\"'<>{}$*]{6,}@[\w.\-]+"),
}

#: Loggers that keep their own handlers in the processes this service runs.
SERVER_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access", "gunicorn.error",
                  "gunicorn.access", "hypercorn.error", "hypercorn.access")


def fingerprint(text: str) -> str:
    """Same 12-hex fingerprint the release scan prints -- one secret, one identity."""
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def scan_text(text: str) -> list[tuple[int, str, str]]:
    """[(line number, pattern name, fingerprint)] -- never the matched text itself."""
    out = []
    for n, line in enumerate((text or "").splitlines(), 1):
        for name, pat in PATTERNS.items():
            for m in pat.finditer(line):
                out.append((n, name, fingerprint(m.group(0))))
    return out


def redact(text: str) -> tuple[str, list[tuple[str, str]]]:
    """The text with every match replaced by `***<fingerprint>`, and what was replaced."""
    hits: list[tuple[str, str]] = []
    for name, pat in PATTERNS.items():
        def sub(m: re.Match, _name=name) -> str:
            fp = fingerprint(m.group(0))
            hits.append((_name, fp))
            return f"***{fp}"
        text = pat.sub(sub, text)
    return text, hits


class SecretLogGuard(logging.Filter):
    """Rewrites a record whose formatted message carries a secret. Never drops one."""

    def __init__(self) -> None:
        super().__init__()
        self._lock = threading.Lock()
        self.caught: Counter = Counter()
        self.scanned = 0

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003 - logging's name
        try:
            message = record.getMessage()
            extra = ""
            if record.exc_info and record.exc_info[1] is not None:
                extra = f"{type(record.exc_info[1]).__name__}: {record.exc_info[1]}"
            clean, hits = redact(message)
            clean_extra, extra_hits = redact(extra) if extra else ("", [])
            with self._lock:
                self.scanned += 1
                for name, fp in hits + extra_hits:
                    self.caught[(name, fp, record.name)] += 1
            if hits:
                record.msg, record.args = clean, ()
            if extra_hits:
                # The traceback text is rendered by the handler from exc_info; the only safe
                # rendering of an exception that carries a secret is its redacted summary.
                record.exc_info, record.exc_text = None, None
                record.msg, record.args = (f"{record.msg} [exception redacted by F-159 "
                                           f"guard: {clean_extra}]"), ()
        except Exception:  # noqa: BLE001 - a guard must never take the service down
            record.msg, record.args = ("a log record could not be scanned for secrets and "
                                       "was suppressed rather than logged (F-159)"), ()
            record.exc_info, record.exc_text = None, None
        return True


GUARD = SecretLogGuard()


def install(extra_loggers: tuple[str, ...] = ()) -> list[str]:
    """Attach the guard to the root logger's handlers and every server logger. Idempotent."""
    attached: list[str] = []
    for name in ("",) + SERVER_LOGGERS + tuple(extra_loggers):
        logger = logging.getLogger(name)
        if GUARD not in logger.filters:
            logger.addFilter(GUARD)
        for handler in list(logger.handlers):
            if GUARD not in handler.filters:
                handler.addFilter(GUARD)
        attached.append(name or "root")
    return attached


def summary() -> dict:
    """What the guard has caught in this process: pattern, fingerprint, logger -- no values."""
    with GUARD._lock:
        caught = [{"pattern": p, "fingerprint": fp, "logger": lg, "count": n}
                  for (p, fp, lg), n in sorted(GUARD.caught.items())]
        scanned = GUARD.scanned
    return {"status": "CAUGHT" if caught else "CLEAN", "records_scanned": scanned,
            "caught": caught, "basis": "measured in process since start-up",
            "source": "ops.log_secret_guard"}


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2 or args[0] != "scan":
        print("usage: python -m brambleloop.ops.log_secret_guard scan <exported-log-file>")
        return 2
    try:
        with open(args[1], encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError as exc:
        print(f"UNREADABLE {args[1]}: {type(exc).__name__} -- an unscanned log is not clean")
        return 1
    findings = scan_text(text)
    for line, name, fp in findings:
        print(f"FINDING line {line}: {name} {fp}")
    print(f"{'SECRETS FOUND' if findings else 'CLEAN'}: {len(findings)} finding(s) in "
          f"{len(text.splitlines())} line(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
