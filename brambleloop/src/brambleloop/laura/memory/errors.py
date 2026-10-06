"""Refusals. Each is a ValueError so callers that already catch input errors still do."""


class MemoryError_(ValueError):
    """Base class for every refusal raised by Laura's memory."""


class TierRefused(MemoryError_):
    """The tier does not exist (there is deliberately no private tier in this API)."""


class PermissionRefused(MemoryError_, PermissionError):
    """The principal may not read or write this tier/entry."""


class ProvenanceRefused(MemoryError_):
    """A write without a source that resolves to a real record or action."""


class CanonicalOverwriteRefused(MemoryError_):
    """Canonical identity is owner-controlled; agents and generated text cannot change it."""


class SummaryOverwriteRefused(MemoryError_):
    """A generated summary may not replace a canonical fact or a recorded fact."""
