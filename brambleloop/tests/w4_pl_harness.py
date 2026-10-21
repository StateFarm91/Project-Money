"""Shared helpers for tests/test_w4_pl_*.py (Private Laura register; not a suite itself).

No network and no spend: `AnthropicProvider._send` is replaced by `Stub`, which records the
request it was handed and answers with a neutral sentinel. The provider key set while a test
runs is a dummy (`ANTHROPIC_API_KEY=test-dummy-not-a-key`) and is removed afterwards, so no
business path in the same process ever sees a configured provider. Neutral sentinels only
(PRIV-SENTINEL-...); the repository holds no intimate text.
"""
from __future__ import annotations

import contextlib
import json
import os

from brambleloop.gateway import anthropic as gw
from brambleloop.gateway import laura_register
from brambleloop.gateway.model_gateway import ModelResponse

from brambleloop.gateway import venice as _venice

REPLY = "PRIV-SENTINEL-REPLY-0001"
DUMMY_KEY = "test-dummy-not-a-key"
#: The model the private reply path uses in these suites (the pinned Venice default).
MODEL = _venice.MODEL
PROVIDER = _venice.NAME
# INTEG5 finding (2026-10-20, W4-LAURAONE freeze): the adult register `laura.private_reply@3`
# runs ONLY on Venice; any other private transport is refused (REGISTER_NEEDS_VENICE). These
# suites therefore exercise the one reply path over a STUBBED VENICE transport (they used the
# Anthropic transport before). `Stub.calls` keeps the request in the same shape the suites
# assert on ({model, max_tokens, system, messages}), translated from Venice's wire format, and
# the Anthropic transport now fails the test if anything reaches it.
ENABLE = {laura_register.REGISTER_SWITCH_ENV: "1", laura_register.DAILY_AUTH_ENV: "0.40",
          "VENICE_API_KEY": DUMMY_KEY, "BRAMBLELOOP_PRIVATE_PROVIDER": "venice",
          "ANTHROPIC_API_KEY": None, _venice.MODEL_ENV: None}


class Stub:
    """Stands in for the HTTP request. `answers` is consumed in order (then `REPLY`)."""

    def __init__(self, answers=None, *, model: str = MODEL, fail=None,
                 tokens=(120, 30)):
        self.calls: list[dict] = []
        self.wires: list[dict] = []          # the raw Venice request bodies
        self.answers = list(answers or [])
        self.model = model
        self.fail = fail
        self.tokens = tokens

    def __call__(self, provider, url, body: bytes, headers, timeout):
        """Stands in for `VeniceProvider._post`: records the request (Anthropic-shaped view),
        answers with Venice's documented chat-completion JSON."""
        wire = json.loads(body.decode("utf-8"))
        self.wires.append(wire)
        msgs = wire["messages"]
        self.calls.append({"model": wire["model"], "max_tokens": wire["max_completion_tokens"],
                           "system": msgs[0]["content"],
                           "messages": [{"role": "user", "content": msgs[1]["content"]}]})
        self.headers = dict(headers)
        if self.fail is not None:
            raise self.fail
        text = self.answers.pop(0) if self.answers else json.dumps({"text": REPLY})
        return 200, json.dumps({
            "id": "x", "object": "chat.completion", "model": self.model,
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": text}}],
            "usage": {"prompt_tokens": self.tokens[0], "completion_tokens": self.tokens[1],
                      "total_tokens": sum(self.tokens)}})


@contextlib.contextmanager
def enabled(stub: Stub | None = None, *, release_proven: bool | None = True, **overrides):
    """Owner switch + spend authorisation + dummy provider key, and the stubbed transport.

    INTEG3 (security review of 5f18d11, L3): replies now also require a proven, deployed
    release. A test process is never one, so the harness stands in for the boot guard's
    verdict (`release_proven=False` exercises the refusal; test_w4_integ3_secfixes).
    `release_proven=None` leaves the real check in place (a test that drives BOOT itself)."""
    env = {**ENABLE, **overrides}
    saved = {k: os.environ.get(k) for k in env}
    orig = gw.AnthropicProvider._send
    orig_post = _venice.VeniceProvider._post
    orig_release = laura_register.release_proven
    if release_proven is not None:
        laura_register.release_proven = lambda env=None, boot=None: {
            "met": bool(release_proven), "detail": "test harness stand-in for the boot guard",
            "commit_short": "test"}
    refused: list = []

    def _refuse(self, *a, **kw):
        # Integration review S-5: the reply path sanitises any exception into PROVIDER_ERROR,
        # so the attempt is ALSO recorded and the context fails the test on exit.
        refused.append(type(self).__name__)
        raise AssertionError("a model request was made where none may be")
    gw.AnthropicProvider._send = _refuse              # the private register never goes here
    if stub is not None:
        _venice.VeniceProvider._post = lambda self, url, body, headers, timeout: stub(
            self, url, body, headers, timeout)
    # With no stub, the Venice transport is left as the caller set it (test_w4_venice and
    # test_w4_laura_unified install their own Venice mocks); the harness refuses sockets.
    try:
        for k, v in env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        yield stub
    finally:
        gw.AnthropicProvider._send = orig
        _venice.VeniceProvider._post = orig_post
        if refused:
            raise AssertionError(f"a refused model transport was called: {refused}")
        laura_register.release_proven = orig_release
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def blocks(user: str) -> list[str]:
    """The PRIVATE DATA blocks of a user message, in order."""
    out, rest = [], user
    while "<<<PRIVATE DATA:" in rest:
        start = rest.index("<<<PRIVATE DATA:")
        end = rest.index(laura_register.DATA_CLOSE, start)
        out.append(rest[start:end + len(laura_register.DATA_CLOSE)])
        rest = rest[end + len(laura_register.DATA_CLOSE):]
    return out


def outside_blocks(user: str) -> str:
    for b in blocks(user):
        user = user.replace(b, "")
    return user


def table_dump(db) -> tuple[str, dict]:
    """Every business (Base) table's rows as text, and their counts."""
    from sqlalchemy import inspect, select

    from brambleloop.core import models  # noqa: F401
    from brambleloop.core.db import Base

    insp = inspect(db.engine)
    parts, counts = [], {}
    with db.session() as s:
        for t in Base.metadata.sorted_tables:
            if not insp.has_table(t.name):
                continue
            rows = s.execute(select(t)).all()
            counts[t.name] = len(rows)
            parts.append(t.name + json.dumps([list(r) for r in rows], default=str))
    return "\n".join(parts), counts


@contextlib.contextmanager
def sql_params(db):
    """Every SQL statement and its bound parameters, as text."""
    from sqlalchemy import event

    seen: list[str] = []

    def on_sql(conn, cursor, statement, params, context, executemany):
        seen.append(f"{statement} {params!r}")
    event.listen(db.engine, "before_cursor_execute", on_sql)
    try:
        yield seen
    finally:
        event.remove(db.engine, "before_cursor_execute", on_sql)
