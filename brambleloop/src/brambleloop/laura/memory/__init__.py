"""Laura's durable BUSINESS memory (D-FB-13, spec/07 item 5) -- lane W3-E.

Public API (the contract lanes D and F build on)::

    from brambleloop.laura import memory as lm
    lm.write(db, tier, key, value, source=..., actor=principal, generated=False,
             supersede=False, subject="")                      -> dict (the new head entry)
    lm.read(db, tier, query=None, principal=...)                -> list[dict]
    lm.history(db, tier, key, principal=...)                    -> list[dict] (every revision)
    lm.context(db, principal, query=None, tiers=None)           -> dict (canonical wins)
    lm.ensure_canonical_seed(db)                                -> list[str] (keys written)
    lm.Principal.owner(session_public_id) / .laura() / .department(key)
                 / .public(surface) / .customer(ref)
    lm.principal_for_surface(name)                              -> Principal (never owner/laura)

Tiers: canonical, brand, operational, experience, relationship. There is no private tier
here: owner-private memory is out of this lane's scope and any other tier name is refused.

Storage is pure database state on existing infrastructure: entries and their immutable
revisions are rows in the autonomy package's `company_memory` table (kinds `laura.mem` and
`laura.mem.rev`); canonical changes and refused access attempts are appended to
`company_timeline`; the experience tier also projects the company's existing lessons
(`lessons`, `learn_policy_lessons`) read-only. Nothing lives in a model's context window, so
the memory survives process restarts, deploys and model/provider swaps unchanged.
"""
from .errors import (MemoryError_, PermissionRefused, ProvenanceRefused,  # noqa: F401
                     CanonicalOverwriteRefused, SummaryOverwriteRefused, TierRefused)
from .principals import Principal, principal_for_surface, SURFACES  # noqa: F401
from .tiers import TIERS, can_read, can_write  # noqa: F401
from .store import (write, read, history, context, ensure_canonical_seed,  # noqa: F401
                    CANONICAL_SEED)

__all__ = ["write", "read", "history", "context", "ensure_canonical_seed", "CANONICAL_SEED",
           "Principal", "principal_for_surface", "SURFACES", "TIERS", "can_read",
           "can_write", "MemoryError_", "PermissionRefused", "ProvenanceRefused",
           "CanonicalOverwriteRefused", "SummaryOverwriteRefused", "TierRefused"]
