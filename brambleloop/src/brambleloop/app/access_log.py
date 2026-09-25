"""Keep the authorization code out of the web server's own access log.

This is the leak that the rest of the OAuth work would not have closed. Every care can be
taken inside the application -- fingerprints instead of tokens, `Redactor` over every report,
nothing secret in an audit detail -- and then uvicorn writes:

    127.0.0.1:0 - "GET /api/etsy/oauth/callback?code=bftcubu-...&state=... HTTP/1.1" 200

because an access log logs the request line, and in an authorization-code flow the request
line *is* the credential. Nothing in this repository asked for that line to exist; it is the
default behaviour of the server the container runs, which is precisely why it would have
survived a careful review of the application code.

So the log line is rewritten before it is emitted: any query parameter whose name is one this
system treats as a secret has its value replaced with `***<fingerprint>`, the same eight hex
characters every other report uses for the same value. The path, the method and the status
are untouched, so the log still answers every operational question it answered before -- how
often the callback is hit, by whom, and with what result.

**Reuses Lane C's scrubber rather than inventing a second one.** The names come from
`integrations.http.SECRET_KEYS` and the fingerprint from `integrations.http.fingerprint`, so
a field added to that set is scrubbed here too and one secret has one identity everywhere.

**What this does not cover, stated rather than implied.** A reverse proxy or platform router
in front of this process keeps its own access log, and nothing in this repository can reach
it. The residual exposure there is bounded and worth writing down: an Etsy authorization code
is single-use, short-lived, and **useless without the PKCE verifier**, which never leaves this
service's database and is sealed inside it. A code lifted from a proxy log cannot be
exchanged.
"""
from __future__ import annotations

import logging
import re

from ..integrations.http import SECRET_KEYS, fingerprint

# The query parameter names whose values are scrubbed. `SECRET_KEYS` already holds `code`,
# `access_token`, `refresh_token`, `code_verifier` and the rest; `state` is added here and
# not there because it is not a secret in a response body -- it is a single-use value in a
# URL, and a URL is the one place it can still be replayed from.
SCRUBBED_QUERY_KEYS = frozenset(SECRET_KEYS) | {"state"}

# Deliberately tolerant about what a value looks like: an access log is not a URL parser and
# a malformed query is exactly the case a scrubber must not silently skip.
_PARAM = re.compile(r"([?&])([A-Za-z0-9_.\-]{1,64})=([^&\s\"']*)")

LOGGERS = ("uvicorn.access", "gunicorn.access", "hypercorn.access")


def scrub_query(text: str) -> str:
    """Replace the value of every sensitive query parameter in a request line."""
    if "?" not in text:
        return text

    def one(match: re.Match) -> str:
        sep, name, value = match.group(1), match.group(2), match.group(3)
        if name.strip().lower() not in SCRUBBED_QUERY_KEYS or not value:
            return match.group(0)
        return f"{sep}{name}=***{fingerprint(value)}"

    return _PARAM.sub(one, text)


class QueryStringRedaction(logging.Filter):
    """Rewrites a log record in place. Never drops one: a missing log line is its own fault.

    Both `record.args` -- which is where uvicorn puts the request path, because it formats
    lazily -- and an already-formatted `record.msg` are covered, because a server that
    formats eagerly would otherwise walk straight past this.
    """

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003 - logging's name
        try:
            if isinstance(record.args, tuple):
                record.args = tuple(
                    scrub_query(a) if isinstance(a, str) else a for a in record.args)
            elif isinstance(record.args, dict):
                record.args = {k: (scrub_query(v) if isinstance(v, str) else v)
                               for k, v in record.args.items()}
            if isinstance(record.msg, str):
                record.msg = scrub_query(record.msg)
        except Exception:  # noqa: BLE001 - a redactor must never take the server down
            # Failing closed here would mean losing the log line; failing open would mean
            # printing a secret. Neither: the line is replaced wholesale.
            record.args = ()
            record.msg = ("a request line could not be redacted and was suppressed rather "
                          "than logged")
        return True


_FILTER = QueryStringRedaction()


def install() -> list[str]:
    """Attach the filter to every access logger this container might be started with.

    Idempotent, and returns what it attached to so a startup record can say so. Called at
    import of `app.main`, which is after the server has configured logging and before it has
    served anything.
    """
    attached: list[str] = []
    for name in LOGGERS:
        logger = logging.getLogger(name)
        if _FILTER not in logger.filters:
            logger.addFilter(_FILTER)
        for handler in list(logger.handlers):
            if _FILTER not in handler.filters:
                handler.addFilter(_FILTER)
        attached.append(name)
    return attached
