"""eng/evidence-perf: a read cache that lives for exactly one request, and nowhere else.

`GET /api/readback/evidence` took 45-91 s in production. Most of it was the same rows read
again and again by sections that each asked their own question: every product's release
history (with its CIR and certificate JSON) was loaded once per `lifecycle.derive`, and
`derive` ran once per product for the certification board and again per parked release for
the sale admission; `halted_releases` ran for two sections; and so on.

`scope()` opens a memo for the duration of one block; `memo(key, fn)` returns `fn()` once per
key inside it. Outside a scope `memo` simply calls `fn()`, so every other caller (the worker,
the publication guard, the stage handlers) reads live rows exactly as before -- nothing is
ever cached across requests, jobs or processes, and nothing a writer does is ever hidden
from it.

A failed read is never cached (the exception propagates and the next call reads again), and
each caller receives its own deep copy, so one section mutating what it was given cannot
change what another section sees.

The memo is a `ContextVar`, so concurrent requests (threads or tasks) never share one.
"""
from __future__ import annotations

import copy
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Callable, Hashable, TypeVar

T = TypeVar("T")

_MEMO: ContextVar[dict | None] = ContextVar("brambleloop_request_memo", default=None)


@contextmanager
def scope():
    """Open a request-scoped memo (re-entrant: an inner scope reuses the outer one)."""
    if _MEMO.get() is not None:
        yield
        return
    token = _MEMO.set({})
    try:
        yield
    finally:
        _MEMO.reset(token)


def active() -> bool:
    return _MEMO.get() is not None


def memo(key: Hashable, fn: Callable[[], T], *, copy_result: bool = True) -> T:
    """`fn()` once per key within the current scope; a plain call outside one.

    `copy_result=False` is for values the caller promises never to mutate (large, read-only
    structures), so they are not copied per reader."""
    m = _MEMO.get()
    if m is None:
        return fn()
    if key not in m:
        m[key] = fn()
    return copy.deepcopy(m[key]) if copy_result else m[key]
