"""Values that come out of the private store. Stdlib only.

A `PrivateValue` cannot silently become ordinary text: `str()`, `repr()`, f-strings and
`%`-formatting all render `[private]`, `json.dumps` refuses it (not serialisable), and pickling
is refused. The only way to the plaintext is an explicit `.reveal()`, which a static test
allows only inside `brambleloop.laura.private` and the Command Center's private view.

Both classes carry the `__brambleloop_private__` marker the firewall looks for.
"""
from __future__ import annotations

PRIVATE_MARKER = "__brambleloop_private__"
REDACTED = "[private]"


class PrivateValue:
    __slots__ = ("__value",)
    __brambleloop_private__ = True

    def __init__(self, value):
        object.__setattr__(self, "_PrivateValue__value", value)

    def __setattr__(self, name, value):
        raise AttributeError("PrivateValue is immutable")

    def reveal(self):
        """The plaintext. Call only on an owner-private surface."""
        return self.__value

    def __str__(self) -> str:
        return REDACTED

    __repr__ = __str__

    def __format__(self, spec: str) -> str:
        return REDACTED

    def __reduce__(self):
        raise TypeError("private values cannot be pickled or copied out of process")

    def __reduce_ex__(self, protocol):
        raise TypeError("private values cannot be pickled or copied out of process")

    def __eq__(self, other):
        return self is other

    def __hash__(self):
        return id(self)


class PrivateRecord:
    """Metadata plus a `PrivateValue`. Metadata here is non-content (ids, kinds, times)."""

    __slots__ = ("record_id", "kind", "provenance", "created_at", "role", "model_ref",
                 "reply_to", "key", "value", "sources")
    __brambleloop_private__ = True

    def __init__(self, **kw):
        for name in self.__slots__:
            object.__setattr__(self, name, kw.get(name))

    def __setattr__(self, name, value):
        raise AttributeError("PrivateRecord is immutable")

    def __repr__(self) -> str:
        return f"PrivateRecord({self.kind}, {self.record_id}, {REDACTED})"

    __str__ = __repr__

    def __reduce__(self):
        raise TypeError("private records cannot be pickled or copied out of process")

    def __reduce_ex__(self, protocol):
        raise TypeError("private records cannot be pickled or copied out of process")
