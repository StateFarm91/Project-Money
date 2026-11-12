"""WS5 E4: one provenance flag on every learnable evidence row -- real or synthetic.

Synthetic data used to be excluded only by a source-name prefix: `commercial_lessons` trusted
any `owner_export:` row without the intake's round trip, the style and outcome learners read
every `ListingOutcome` row, and test fixtures were themselves `owner_export:fixture-1`. So a
fixture, a hand-inserted row or a half-written export could steer what the company makes next.

Now the row says what it is, in `detail["provenance"]`:

* `real`      -- written by the owner-export intake AND read back field-for-field (its round
                 trip matched). Nothing else in production sets it.
* `synthetic` -- a fixture, a rehearsal, a demonstration. Never learned from.

A row with no provenance is treated like a synthetic one: every learner reads only `real`
rows (`learnable`). Older rows written before the flag carry none and are therefore not
learned from until they are re-imported through the intake.
"""
from __future__ import annotations

KEY = "provenance"
REAL = "real"
SYNTHETIC = "synthetic"
VALUES = (REAL, SYNTHETIC)


def of(detail) -> str | None:
    """The row's provenance, or None when it has none (or carries an unknown value)."""
    value = (detail or {}).get(KEY) if isinstance(detail, dict) else None
    return value if value in VALUES else None


def learnable(detail) -> bool:
    """Only rows marked `real` may move a learner."""
    return of(detail) == REAL


def mark(detail, value: str) -> dict:
    if value not in VALUES:
        raise ValueError(f"provenance must be one of {VALUES}, not {value!r}")
    return {**dict(detail or {}), KEY: value}
