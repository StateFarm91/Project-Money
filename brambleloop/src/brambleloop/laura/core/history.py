"""Laura's durable decision history, held in lane E's Laura memory (`brambleloop.laura.memory`).

Integrator ruling (wave 3): reuse `laura.memory` for her history rather than a new table. Each
real action is one entry in the **operational** tier, written by `Principal.laura()`:

    key    "decision/<sha256(decision key)[:20]>"   (bounded, deterministic, idempotent)
    value  {"decision_key", "at", "kind", "department", "subject", "reason", "evidence",
            "refs", "cognition", "identity_sha256"}
    source "company_timeline:<event key>" -- the timeline event recorded for the same act, so
           every entry resolves to a real row (laura.memory's provenance rule)

An entry is written once and never revised by this module; laura.memory keeps every revision of
an entry anyway, so any later rewrite would be visible in its audit trail. Reads go through
`laura.memory.read` with Laura's principal (public/customer principals are refused there).
"""
from __future__ import annotations

import hashlib
import time
from datetime import datetime

TIER = "operational"
PREFIX = "decision/"


def entry_key(decision_key: str) -> str:
    return PREFIX + hashlib.sha256(decision_key.encode("utf-8")).hexdigest()[:20]


def _laura():
    from ..memory import Principal

    return Principal.laura()


def exists(db, decision_key: str) -> bool:
    from ..memory.store import _exists

    return _exists(db, TIER, entry_key(decision_key))


def record(db, decision_key: str, *, kind: str, department: str, subject: str, reason: str,
           evidence: list, refs: list, cognition: dict, identity_sha256: str,
           at: datetime) -> bool:
    """Write one decision unless it exists. True when this call wrote it."""
    from ...autonomy import memory as company
    from .. import memory as lm

    decision_key = decision_key[:200]
    if exists(db, decision_key):
        return False
    event_key = f"laura.{kind}:{decision_key}"[:200]
    company.record_event(db, event_key, kind=f"laura.{kind}"[:40], department=department,
                         actor="laura",
                         severity="decision" if kind in ("blocked", "owner_action",
                                                         "escalation") else "info",
                         summary=f"Laura {kind}: {subject} -- {reason}"[:2000],
                         refs=[f"laura_memory:{TIER}:{entry_key(decision_key)}",
                               *(refs or [])][:10], at=at)
    lm.write(db, TIER, entry_key(decision_key),
             {"decision_key": decision_key, "at": at.isoformat(), "kind": kind,
              "department": department, "subject": subject[:300], "reason": reason[:4000],
              "evidence": list(evidence or [])[:20], "refs": list(refs or [])[:20],
              "cognition": cognition, "identity_sha256": identity_sha256,
              "seq": time.time_ns()},
             f"company_timeline:{event_key}", _laura(),
             subject=f"Laura {kind}: {subject}"[:200], now=at)
    return True


def all_decisions(db, *, limit: int = 100_000) -> list[dict]:
    """Every decision, newest first (dicts with the stored value plus the memory ref)."""
    from .. import memory as lm

    rows = lm.read(db, TIER, PREFIX + "*", _laura(), include_projections=False, limit=limit)
    out = []
    for e in rows:
        v = dict(e.get("value") or {})
        if not v.get("decision_key"):
            continue
        v["memory_ref"] = e["ref"]
        v["revision"] = e.get("revision")
        out.append(v)
    out.sort(key=lambda d: (d.get("at") or "", d.get("seq") or 0), reverse=True)
    return out
