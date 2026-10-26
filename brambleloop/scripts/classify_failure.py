#!/usr/bin/env python3
"""F-150: classify a failing suite's output before anyone reverts code for it.

F-150: "Classify ENOSPC/permissions/network/provider failures before reverting code."

`classify(text)` returns the environment class a failure belongs to -- `ENOSPC`,
`PERMISSION`, `NETWORK` or `PROVIDER` -- with the line that shows it, or None when nothing in
the output points outside the code (an assertion or a code error, which is a code failure).
`run_tests.sh` prints `ENVIRONMENT FAILURE (<class>)` for such a suite, beside the ordinary
FAIL lines, and totals them, so a disk that filled up is never read as a regression to revert.
The markers are literal strings the OS, Python and the providers print; nothing is guessed
from a test name.

  python3 scripts/classify_failure.py SUITE_OUTPUT_FILE   -> prints "<CLASS>\t<line>" or nothing
"""
from __future__ import annotations

import sys

MARKERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("ENOSPC", ("No space left on device", "ENOSPC", "Disk quota exceeded",
                "database or disk is full")),
    ("PERMISSION", ("Permission denied", "EACCES", "Operation not permitted", "EPERM",
                    "Read-only file system")),
    ("NETWORK", ("Temporary failure in name resolution", "Name or service not known",
                 "Network is unreachable", "Connection refused", "Connection reset by peer",
                 "ECONNREFUSED", "ECONNRESET", "getaddrinfo failed", "timed out connecting")),
    ("PROVIDER", ("overloaded_error", "rate_limit_error", "status code 529",
                  "credit balance is too low", "insufficient_quota", "HTTP 503 from provider")),
)


def classify(text: str) -> tuple[str, str] | None:
    for line in (text or "").splitlines():
        for cls, needles in MARKERS:
            if any(n in line for n in needles):
                return cls, line.strip()[:200]
    return None


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: classify_failure.py SUITE_OUTPUT_FILE", file=sys.stderr)
        return 2
    try:
        text = open(argv[1], encoding="utf-8", errors="replace").read()
    except OSError:
        return 0
    got = classify(text)
    if got:
        print(f"{got[0]}\t{got[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
