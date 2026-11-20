"""Firewall for protected decisions: reject any input tagged private. Stdlib only.

Finance, Product Truth, security, authorization, spend and legal paths call
`reject_private(value, context=...)` (or decorate with `@guard(context)`) on anything that
could have originated outside their own deterministic inputs. Anything tagged private --
a `PrivateValue`/`PrivateRecord`, a private principal, or a mapping that declares itself
private -- is refused with `PrivateInputRefused`, wherever it is nested.

Fails closed: a structure nested deeper than `MAX_DEPTH`, or one whose inspection raises, is
refused as if it were private.

This module imports nothing from the private store, so calling it never loads the key, the
tables or the plaintext. Limitation (documented, by design): the firewall is tag-based. A
plaintext string obtained by an explicit `.reveal()` carries no tag; the control for that is
that `.reveal()` is allowed only on the owner-private surface (static test), and that protected
modules can never import the store (static + runtime test).
"""
from __future__ import annotations

import functools

from .values import PRIVATE_MARKER

PROTECTED_CONTEXTS = frozenset({
    "finance", "accounting", "product_truth", "security", "authorization", "spend", "legal",
    "compliance", "platform_policy", "publication", "activation",
})
PRIVATE_DECLARATIONS = {"privacy": "owner_private", "tier": "private"}
MAX_DEPTH = 12


class PrivateInputRefused(PermissionError, ValueError):
    """A protected decision path was handed private input."""


def _tagged(obj) -> bool:
    return bool(getattr(type(obj), PRIVATE_MARKER, False))


def _declares_private(mapping) -> bool:
    if mapping.get(PRIVATE_MARKER):
        return True
    return any(mapping.get(k) == v for k, v in PRIVATE_DECLARATIONS.items())


def is_private(obj, _depth: int = 0) -> bool:
    if _depth > MAX_DEPTH:
        return True
    try:
        if _tagged(obj):
            return True
        if isinstance(obj, (str, bytes, int, float, bool, type(None))):
            return False
        if isinstance(obj, dict):
            if _declares_private(obj):
                return True
            return any(is_private(k, _depth + 1) or is_private(v, _depth + 1)
                       for k, v in obj.items())
        if isinstance(obj, (list, tuple, set, frozenset)):
            return any(is_private(v, _depth + 1) for v in obj)
        state = getattr(obj, "__dict__", None)
        if isinstance(state, dict):
            return any(is_private(v, _depth + 1) for v in state.values())
        return False
    except Exception:  # noqa: BLE001 - uninspectable input is refused, never trusted
        return True


def reject_private(obj, *, context: str):
    """Return `obj` unchanged, or raise PrivateInputRefused. The message carries no content."""
    if is_private(obj):
        raise PrivateInputRefused(
            f"private owner context may not influence a protected decision ({context})")
    return obj


def guard(context: str):
    """Decorator: refuse the call if any positional or keyword argument is private."""
    def wrap(fn):
        @functools.wraps(fn)
        def inner(*args, **kwargs):
            reject_private(args, context=context)
            reject_private(kwargs, context=context)
            return fn(*args, **kwargs)
        return inner
    return wrap
