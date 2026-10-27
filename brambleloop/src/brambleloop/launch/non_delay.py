"""F-515@v0.15 Launch Non-Delay Rule: once the floors pass, the launch list is frozen.

Criterion: "Once launch-critical quality floors pass, non-blocking improvements cannot
indefinitely delay launch."

`launch.readiness` blocks only on the requirements it declares, and nothing stopped the list
from growing: an improvement worth doing could be written in as a new requirement after the
floors passed, and launch would wait on it like any other. This module is the rule:

* `floors_pass(readiness)`: every requirement this company can satisfy itself (blocked_by
  `build`) is ready. What is left is the owner's, a tester's or an integration's -- outside the
  build's power to keep improving.
* `freeze()`: once the floors pass, the requirement keys are frozen (an audit row with their
  fingerprint). Refused before the floors pass: a list frozen early would let a missing floor
  through.
* `check()`: after a freeze, a requirement that was not on the frozen list and is not ready is
  an *addition*. It is reported by name and does not block launch (`effective_ready`) unless it
  was admitted with `admit()` -- only for a launch-critical category (safety, Product Truth,
  legal, policy, security, payments), with a reason. Everything else waits for after launch.
* A frozen requirement that regressed still blocks: the freeze stops new blockers, never a
  floor that broke.

Read-only over `launch.readiness`; it changes no requirement and publishes nothing.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

FREEZE_ACTION = "launch.list_frozen"
ADMIT_ACTION = "launch.blocker_admitted"
CRITICAL_CATEGORIES: tuple[str, ...] = ("safety", "product_truth", "legal", "policy",
                                        "security", "payments")


class NonDelayRefused(ValueError):
    """A freeze before the floors pass, or an admission that is not launch-critical."""


def _keys(readiness) -> list[str]:
    return sorted({r.key for r in readiness.requirements})


def floors_pass(readiness) -> bool:
    from .readiness import BLOCKED_BUILD

    return not [r for r in readiness.requirements if not r.ready
                and r.blocked_by == BLOCKED_BUILD]


# State lives in `operating_readings`, not the audit log: retention (`ops.retention`) prunes
# audit rows past their horizon, and a freeze or an admission must not be forgotten.
def _put(s, kind: str, detail: dict) -> None:
    import uuid

    from ..core.models import OperatingReading

    s.add(OperatingReading(kind=kind, period_key=uuid.uuid4().hex[:20], payload=detail,
                           at=datetime.now(timezone.utc)))


def _rows(s, kind: str) -> list:
    from sqlalchemy import select

    from ..core.models import OperatingReading

    return list(s.scalars(select(OperatingReading).where(OperatingReading.kind == kind)
                          .order_by(OperatingReading.id)))


def frozen(db) -> dict | None:
    with db.session() as s:
        rows = _rows(s, FREEZE_ACTION)
        return dict(rows[-1].payload or {}, at=rows[-1].at.isoformat()) if rows else None


def freeze(db, readiness, *, by: str, now: datetime | None = None) -> dict:
    """Freeze the launch list once the floors pass. Idempotent while a freeze stands."""
    existing = frozen(db)
    if existing is not None:
        return {**existing, "frozen": True, "new": False}
    if not floors_pass(readiness):
        build = sorted(r.key for r in readiness.buildable)
        raise NonDelayRefused(f"the launch-critical floors have not passed: {build} are still "
                              f"the build's to finish, so the list is not frozen")
    keys = _keys(readiness)
    detail = {"keys": keys, "by": by[:60],
              "fingerprint": hashlib.sha256(json.dumps(keys).encode()).hexdigest(),
              "frozen_at": (now or datetime.now(timezone.utc)).isoformat()}
    with db.session() as s:
        _put(s, FREEZE_ACTION, detail)
    return {**detail, "frozen": True, "new": True}


def admit(db, key: str, *, category: str, reason: str, by: str) -> dict:
    """Admit one requirement added after the freeze as a real blocker."""
    if category not in CRITICAL_CATEGORIES:
        raise NonDelayRefused(f"{category!r} is not launch-critical {CRITICAL_CATEGORIES}: "
                              f"a non-blocking improvement waits for after launch (F-515)")
    if len((reason or "").split()) < 4:
        raise NonDelayRefused("an admitted blocker says why launch must wait for it")
    detail = {"key": key, "category": category, "reason": reason[:500], "by": by[:60]}
    with db.session() as s:
        _put(s, ADMIT_ACTION, detail)
    return detail


def _admitted(db) -> dict[str, dict]:
    with db.session() as s:
        return {(r.payload or {})["key"]: dict(r.payload or {}) for r in _rows(s, ADMIT_ACTION)}


def check(db, readiness) -> dict:
    """Additions after the freeze, and whether launch is ready once they are set aside."""
    f = frozen(db)
    outstanding = [r for r in readiness.requirements if not r.ready]
    if f is None:
        return {"frozen": False, "floors_pass": floors_pass(readiness), "added": [],
                "admitted": [], "effective_ready": readiness.ready,
                "why": ("the floors pass; freeze the launch list" if floors_pass(readiness)
                        else "the floors have not passed; nothing is frozen yet")}
    listed = set(f["keys"])
    admitted = _admitted(db)
    added = [r for r in outstanding if r.key not in listed]
    blocking_added = [r.key for r in added if r.key in admitted]
    deferred = [r.key for r in added if r.key not in admitted]
    still = [r.key for r in outstanding if r.key in listed] + blocking_added
    return {"frozen": True, "frozen_at": f.get("frozen_at"), "floors_pass": floors_pass(readiness),
            "added": [r.key for r in added], "admitted": blocking_added,
            "deferred_after_launch": deferred, "blocking": sorted(still),
            "effective_ready": not still,
            "why": (f"{len(deferred)} requirement(s) added after the freeze are not "
                    f"launch-critical and do not delay launch" if deferred else
                    "no requirement was added after the freeze")}
