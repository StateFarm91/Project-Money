"""Failure memory: a fingerprinted, scoped registry of what was tried and failed.

Final Master F-378 (Failure Memory), F-427 (Negative Evidence), F-428 (Scope Discipline) and
F-706 (Learning Ledger). Before this module the company kept its failures -- rejected and
reverted improvements are durable rows, and the visual/provider dead ends are argued in
DECISION_LOG prose -- but nothing *read* them before a new proposal was accepted. The same
failed improvement could be proposed again months later and nothing would say "this was
measured and lost".

What counts as a failure, and why so narrowly:

* a REVERTED improvement (it was promoted, then measured worse, and rolled back with proof);
* a REJECTED improvement **with a measurement**: both a baseline and a result were recorded
  and the result lost. A rejection with no result -- "no baseline existed", a refusal, a
  proposal withdrawn -- is not evidence the idea fails. B-686 is the reason: a refusal read as
  "tried" once retired the strongest challenger on the evidence that an account had not been
  topped up. A failure memory that remembered refusals would do that permanently.
* a recorded negative finding (`record`) with its evidence ids and an explicit scope, such as
  the DECISION_LOG dead ends seeded below.

A matching proposal is refused **unless** it cites evidence ids the failure did not have, or
states a different premise. That is the whole rule: new evidence reopens a question, the same
evidence does not.

Scope discipline (F-428): every failure carries ``scope = {method, class, conditions}``. A
failure blocks only proposals inside that scope -- same method and class, and every condition
the failure was observed under also holds for the proposal. A failure under "provider X with an
empty balance" says nothing about provider X funded, and `generalise` refuses to widen a
recorded failure's scope without new evidence.

Fingerprint = sha256(cell | normalised hypothesis-or-method | sorted touches | premise digest).
Normalisation lowercases, drops punctuation and collapses whitespace but keeps digits: a
hypothesis that quotes different measured numbers is a different claim on different data.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Integer, String, Text, select
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base

REJECTED = "rejected"
REVERTED = "reverted"


class FailureRecord(Base):
    """One negative finding with its scope and evidence. Never updated in place."""

    __tablename__ = "failure_memory"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                         default=lambda: datetime.now(timezone.utc))
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    cell: Mapped[str] = mapped_column(String(40), index=True)
    method: Mapped[str] = mapped_column(String(200), index=True)
    scope: Mapped[dict] = mapped_column(JSON, default=dict)
    premise_digest: Mapped[str] = mapped_column(String(64), default="")
    evidence_ids: Mapped[list] = mapped_column(JSON, default=list)
    source: Mapped[str] = mapped_column(String(120), index=True)
    reason: Mapped[str] = mapped_column(Text, default="")


class FailureMemoryRefused(ValueError):
    """A record without scope or evidence, or a generalisation beyond the recorded scope."""


# ---- fingerprints ---------------------------------------------------------------------------

def normalise(text: str) -> str:
    t = re.sub(r"[^\w\s.]", " ", str(text or "").lower())
    t = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", t)  # keep decimal points, drop sentence dots
    return re.sub(r"\s+", " ", t).strip()


def premise_digest(premise: str) -> str:
    p = normalise(premise)
    return hashlib.sha256(p.encode()).hexdigest() if p else ""


def fingerprint(cell: str, claim: str, touches=(), premise: str = "") -> str:
    body = "|".join((str(cell or ""), normalise(claim),
                     ",".join(sorted(str(t).strip().lower() for t in touches or ())),
                     premise_digest(premise)))
    return hashlib.sha256(body.encode()).hexdigest()


def default_scope(cell: str, method: str, *, trial: str = "", metric: str = "") -> dict:
    conds = {k: v for k, v in (("trial", trial), ("metric", metric)) if v}
    return {"method": normalise(method), "class": cell, "conditions": conds}


def within(failure_scope: dict, proposal_scope: dict) -> bool:
    """True when the proposal sits inside the failure's scope (and may be blocked by it)."""
    f, p = failure_scope or {}, proposal_scope or {}
    if normalise(f.get("method", "")) != normalise(p.get("method", "")):
        return False
    if (f.get("class") or "") != (p.get("class") or ""):
        return False
    pc = p.get("conditions") or {}
    return all(pc.get(k) == v for k, v in (f.get("conditions") or {}).items())


def generalise(failure_scope: dict, to_scope: dict, *, new_evidence_ids=()) -> dict:
    """Widen a failure's scope only with new evidence. Narrowing is always allowed."""
    if within(failure_scope, to_scope):  # `to_scope` is no wider than what was observed
        return dict(to_scope)
    if not tuple(new_evidence_ids or ()):
        raise FailureMemoryRefused(
            "a failure observed under "
            f"{failure_scope.get('conditions') or 'no stated conditions'} for method "
            f"{failure_scope.get('method')!r} ({failure_scope.get('class')}) cannot be "
            f"generalised to {to_scope} without evidence observed in that wider scope")
    return dict(to_scope)


# ---- the registry -------------------------------------------------------------------------

def record(db, *, cell: str, method: str, scope: dict, evidence_ids, source: str,
           reason: str, touches=(), premise: str = "") -> int:
    """Record one negative finding. Idempotent on (fingerprint, source)."""
    ids = [str(e) for e in (evidence_ids or ()) if str(e).strip()]
    if not ids:
        raise FailureMemoryRefused("a failure without evidence ids is an opinion, not memory")
    if not scope or not scope.get("method") or not scope.get("class"):
        raise FailureMemoryRefused("a failure needs a scope: method and class at least (F-428)")
    fp = fingerprint(cell, method, touches, premise)
    with db.session() as s:
        existing = s.scalar(select(FailureRecord).where(FailureRecord.fingerprint == fp,
                                                        FailureRecord.source == source))
        if existing is not None:
            return existing.id
        row = FailureRecord(fingerprint=fp, cell=cell, method=normalise(method)[:200],
                            scope={"method": normalise(scope["method"]),
                                   "class": scope["class"],
                                   "conditions": dict(scope.get("conditions") or {})},
                            premise_digest=premise_digest(premise), evidence_ids=ids,
                            source=source[:120], reason=str(reason)[:2000])
        s.add(row)
        s.flush()
        return row.id


def _improvement_failures(db, cell: str) -> list[dict]:
    from ..core.models import Improvement

    out = []
    with db.session() as s:
        rows = list(s.scalars(select(Improvement).where(
            Improvement.cell == cell, Improvement.state.in_((REJECTED, REVERTED)))))
        for r in rows:
            ev = dict(r.evidence or {})
            measured = r.state == REVERTED or (r.baseline_value is not None
                                               and r.result_value is not None)
            if not measured:
                continue  # a refusal or a first measurement is not a failed experiment
            if (ev.get("superseded") or {}).get("reason"):
                continue  # F-126: a confounded or invalid result disproves nothing
            touches = tuple(ev.get("touches") or ())
            fp = ev.get("failure_fingerprint") or fingerprint(
                r.cell, r.hypothesis, touches, ev.get("premise") or "")
            trial = ev.get("sandbox_trial") or ""
            metric = r.metric if trial else ""
            out.append({
                "kind": "improvement", "id": r.id, "state": r.state, "fingerprint": fp,
                "method": ev.get("method") or "",
                "scope": ev.get("scope") or default_scope(r.cell, ev.get("method") or r.hypothesis,
                                                          trial=trial, metric=metric),
                "premise_digest": premise_digest(ev.get("premise") or ""),
                "evidence_ids": list(ev.get("evidence_ids") or []),
                "why": ev.get("reverted_because") or ev.get("why") or "",
                "source": f"improvements:{r.id}", "at": r.at})
    return out


def _recorded_failures(db, cell: str) -> list[dict]:
    ensure_seeded(db)
    with db.session() as s:
        return [{"kind": "record", "id": r.id, "fingerprint": r.fingerprint, "method": r.method,
                 "scope": r.scope or {}, "premise_digest": r.premise_digest,
                 "evidence_ids": list(r.evidence_ids or []), "why": r.reason,
                 "source": r.source, "at": r.at}
                for r in s.scalars(select(FailureRecord).where(FailureRecord.cell == cell))]


def check(db, *, cell: str, hypothesis: str, touches=(), premise: str = "",
          method: str = "", evidence_ids=(), scope: dict | None = None,
          trial: str = "", metric: str = "") -> dict | None:
    """The failure this proposal repeats, or None. A repeat is refused unless new evidence
    ids are cited or the premise differs; it must also sit inside the failure's scope."""
    fp = fingerprint(cell, hypothesis, touches, premise)
    claim = method or hypothesis
    pscope = scope or default_scope(cell, claim, trial=trial, metric=metric)
    cited = {str(e) for e in evidence_ids or ()}
    pd = premise_digest(premise)
    for f in _improvement_failures(db, cell) + _recorded_failures(db, cell):
        same_claim = f["fingerprint"] == fp or (
            method and f.get("method") and normalise(method) == normalise(f["method"]))
        if not same_claim:
            continue
        if not within(f["scope"], pscope):
            continue
        if pd and f.get("premise_digest") != pd:
            continue  # a stated, changed premise reopens the question (recorded on the row)
        if cited - set(f["evidence_ids"]):
            continue
        return {"failure": f["source"], "kind": f["kind"], "why": str(f["why"])[:300],
                "scope": f["scope"], "evidence_ids": f["evidence_ids"], "fingerprint": fp}
    return None


REFUSAL_ACTION = "improve.repeat_refused"


def note_refusal(db, *, cell: str, proposed_by: str, repeat: dict) -> None:
    """Audit one refused repeat, so "repeated failures avoided" is a count of rows (F-399)."""
    from ..core.models import AuditLog

    with db.session() as s:
        s.add(AuditLog(actor=(proposed_by or "unattributed")[:60], action=REFUSAL_ACTION,
                       artifact=f"cell:{cell}",
                       detail={"failure": repeat["failure"], "kind": repeat["kind"],
                               "fingerprint": repeat["fingerprint"],
                               "scope": repeat["scope"]}))


def listing(db, *, cell: str | None = None) -> list[dict]:
    """Every remembered failure (F-427): improvement-derived and recorded, newest first."""
    from . import cells

    keys = [cell] if cell else list(cells.BY_KEY)
    rows = []
    for k in keys:
        for f in _improvement_failures(db, k) + _recorded_failures(db, k):
            rows.append({**{x: f[x] for x in ("kind", "source", "method", "scope",
                                               "evidence_ids", "why", "fingerprint")},
                         "cell": k, "at": f["at"].isoformat() if f.get("at") else None})
    return sorted(rows, key=lambda r: r["at"] or "", reverse=True)


# ---- seeds: dead ends already argued in DECISION_LOG -------------------------------------
# Each is a method the log records as measured-and-rejected, quoted closely, with the log
# entry as its evidence id and the conditions it was observed under as its scope. None is
# invented; a seed is only as wide as the entry that justifies it.

SEEDS: tuple[dict, ...] = (
    {"cell": "creative_assets", "method": "re-render the whole gallery sequence on any floor failure",
     "scope": {"method": "re-render the whole gallery sequence on any floor failure",
               "class": "creative_assets", "conditions": {"pipeline": "listing_gallery"}},
     "evidence_ids": ["DECISION_LOG:B-650"],
     "reason": "six independent floors asked to land in one draw: v8 and v10 each cleared "
               "different floors and no single draw cleared all; keep-what-passed replaces it"},
    {"cell": "creative_assets", "method": "label an image sent to a provider by its filename",
     "scope": {"method": "label an image sent to a provider by its filename",
               "class": "creative_assets", "conditions": {"store": "content_addressed"}},
     "evidence_ids": ["DECISION_LOG:B-634"],
     "reason": "extensionless content-addressed files were labelled image/png; the JPEG "
               "portrait was refused and the face comparison silently did not run"},
    {"cell": "creative_assets", "method": "describe the canonical face in the prompt text",
     "scope": {"method": "describe the canonical face in the prompt text",
               "class": "creative_assets", "conditions": {"subject": "canonical_model"}},
     "evidence_ids": ["DECISION_LOG:B-675"],
     "reason": "describing a face produces a different woman who matches the words; her "
               "appearance is carried by the reference image only"},
    {"cell": "runtime", "method": "count a provider refusal as a completed trial",
     "scope": {"method": "count a provider refusal as a completed trial",
               "class": "runtime", "conditions": {}},
     "evidence_ids": ["DECISION_LOG:B-686"],
     "reason": "402 credits-depleted read as tried retired the strongest challenger; tried "
               "now means made: True"},
    {"cell": "market_radar", "method": "compute remaining backlog by subtracting this run's judged count",
     "scope": {"method": "compute remaining backlog by subtracting this run's judged count",
               "class": "market_radar", "conditions": {"queue": "gallery_observation"}},
     "evidence_ids": ["DECISION_LOG:B-647"],
     "reason": "remaining fell by 25 per run while the backlog went 475 -> 476; progress must "
               "be counted, not computed"},
)

_SEEDED = "_brambleloop_failure_memory_seeded"


def ensure_seeded(db) -> int:
    """Write the DECISION_LOG seeds once per engine (idempotent per (fingerprint, source))."""
    eng = getattr(db, "engine", None)
    if eng is not None and getattr(eng, _SEEDED, False):
        return 0
    FailureRecord.__table__.create(bind=db.engine, checkfirst=True)
    n = 0
    for sd in SEEDS:
        record(db, cell=sd["cell"], method=sd["method"], scope=sd["scope"],
               evidence_ids=sd["evidence_ids"], source=sd["evidence_ids"][0],
               reason=sd["reason"])
        n += 1
    try:
        setattr(eng, _SEEDED, True)
    except Exception:  # noqa: BLE001
        pass
    return n
