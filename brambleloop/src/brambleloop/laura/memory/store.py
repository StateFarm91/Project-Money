"""Read/write for Laura's business memory, on the autonomy package's durable tables.

Layout in `company_memory` (reused, not duplicated):

* head row      key `laura:<tier>:<key>`        kind `laura.mem`      the current entry
* revision row  key `laura:<tier>:<key>#r<n>`   kind `laura.mem.rev`  immutable; never updated

Every write creates one revision row (who, which principal, when, value, sources, generated
or not) and moves the head. The revision rows are the audit trail; `history()` returns them.
Canonical changes and refused attempts are also appended to `company_timeline`. Event
summaries name the tier and key, never the value.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError

from ...autonomy import memory as company
from ...autonomy.models import CompanyMemory, ensure_tables
from . import provenance
from .errors import (CanonicalOverwriteRefused, MemoryError_, PermissionRefused,
                     ProvenanceRefused, SummaryOverwriteRefused)
from .principals import Principal, verify
from .tiers import (OWNER_APPROVED_PREFIXES, RELATIONSHIP_PREFIXES, TIERS, can_read,
                    can_write, category, check_tier, relationship_visible_to_department)

HEAD_KIND = "laura.mem"
REV_KIND = "laura.mem.rev"
MAX_KEY = 120
MAX_VALUE_BYTES = 32_768


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _head_key(tier: str, key: str) -> str:
    return f"laura:{tier}:{key}"


def _check_key(key: str) -> str:
    if not isinstance(key, str) or not key or len(key) > MAX_KEY:
        raise MemoryError_(f"key must be 1..{MAX_KEY} characters")
    if any(c in key for c in ("#", "\n", "\r", "\t")) or key != key.strip():
        raise MemoryError_("key may not contain '#', control characters or edge spaces")
    return key


def _refuse(db, principal, op: str, tier: str, key: str, exc: Exception) -> Exception:
    """Record a refused attempt on the timeline (deduplicated per minute), return exc."""
    try:
        minute = _now().strftime("%Y-%m-%dT%H:%M")
        who = getattr(principal, "label", "none")
        company.record_event(
            db, f"laura.mem.refused:{who}:{op}:{tier}:{key}:{minute}"[:200],
            kind="laura.memory.refused", department="executive",
            actor=str(who)[:64], severity="warn",
            summary=f"Laura memory {op} refused for {who} on {tier}/{key or '*'}: "
                    f"{type(exc).__name__}")
    except Exception:  # noqa: BLE001 - the refusal stands even if its audit row cannot be written
        pass
    return exc


def _entry(row: CompanyMemory) -> dict:
    b = row.body or {}
    return {
        "tier": b.get("tier"), "key": b.get("key"), "value": b.get("value"),
        "subject": row.subject, "sources": list(row.sources or []),
        "actor": b.get("actor"), "principal_kind": b.get("principal_kind"),
        "department": row.department, "category": b.get("category", ""),
        "generated": bool(b.get("generated")), "revision": b.get("revision"),
        "authority": ("canonical" if b.get("tier") == "canonical"
                      else "summary" if b.get("generated") else "fact"),
        "ref": f"laura_memory:{b.get('tier')}:{b.get('key')}",
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _exists(db, tier: str, key: str) -> bool:
    if tier not in TIERS or not key:
        return False
    with db.session() as s:
        return s.scalar(select(CompanyMemory.id).where(
            CompanyMemory.key == _head_key(tier, key),
            CompanyMemory.kind == HEAD_KIND)) is not None


def _authorise_write(principal: Principal, tier: str, key: str, existing, generated: bool,
                     supersede: bool) -> None:
    if tier == "canonical":
        if principal.kind != "owner":
            raise CanonicalOverwriteRefused(
                "canonical identity is owner-controlled and read-only to every agent")
        if generated:
            raise SummaryOverwriteRefused(
                "a generated summary can never be written as a canonical fact")
        if existing is not None and not supersede:
            raise CanonicalOverwriteRefused(
                "canonical fact exists; the owner must pass supersede=True to revise it")
    if not can_write(principal.kind, tier):
        raise PermissionRefused(f"{principal.kind} may not write the {tier} tier")
    if tier == "relationship":
        if not key.startswith(RELATIONSHIP_PREFIXES):
            raise PermissionRefused(f"relationship keys start with one of "
                                    f"{RELATIONSHIP_PREFIXES}")
        if key.startswith(OWNER_APPROVED_PREFIXES) and principal.kind != "owner":
            raise PermissionRefused("policies and preferences are owner-approved: owner only")
    if principal.kind == "department" and existing is not None \
            and existing.department != principal.id:
        raise PermissionRefused(
            f"{principal.id} may not overwrite an entry owned by "
            f"{existing.department or (existing.body or {}).get('principal_kind')}")
    if generated and existing is not None and not (existing.body or {}).get("generated"):
        raise SummaryOverwriteRefused(
            "a generated summary may not replace a recorded fact; write it under its own key")


def write(db, tier: str, key: str, value, source, actor: Principal, *,
          generated: bool = False, supersede: bool = False, subject: str = "",
          now: datetime | None = None) -> dict:
    """Write one entry. `source` is a reference string or a non-empty list of them.

    `actor` is the Principal performing the write. Raises a MemoryError_ subclass on refusal
    (and records the refusal on the company timeline)."""
    ensure_tables(db)
    now = now or _now()
    key_s = key if isinstance(key, str) else ""
    try:
        check_tier(tier)
        _check_key(key)
        verify(db, actor, now=now)
        try:
            blob = json.dumps(value, sort_keys=True)
        except (TypeError, ValueError):
            raise MemoryError_("value must be JSON-serialisable") from None
        if len(blob.encode()) > MAX_VALUE_BYTES:
            raise MemoryError_(f"value exceeds {MAX_VALUE_BYTES} bytes")
        sources = [source] if isinstance(source, str) else list(source or [])
        if not sources:
            raise ProvenanceRefused("every memory entry needs a source")
        with db.session() as s:
            existing = s.scalar(select(CompanyMemory).where(
                CompanyMemory.key == _head_key(tier, key), CompanyMemory.kind == HEAD_KIND))
            _authorise_write(actor, tier, key, existing, generated, supersede)
        self_ref = f"laura_memory:{tier}:{key}"
        if self_ref in sources:
            raise ProvenanceRefused("an entry cannot cite itself")
        resolved = [provenance.resolve(db, src, actor, entry_exists=lambda t, k: _exists(db, t, k))
                    for src in sources]
    except MemoryError_ as exc:
        raise _refuse(db, actor, "write", tier, key_s, exc) from None

    dept = actor.id if actor.kind == "department" else ""
    with db.session() as s:
        head = s.scalar(select(CompanyMemory).where(
            CompanyMemory.key == _head_key(tier, key), CompanyMemory.kind == HEAD_KIND))
        revision = int((head.body or {}).get("revision", 0)) + 1 if head else 1
        body = {"tier": tier, "key": key, "value": value, "actor": actor.label,
                "principal_kind": actor.kind, "generated": bool(generated),
                "category": category(tier, key), "revision": revision,
                "supersedes": revision - 1 if revision > 1 else None}
        try:
            with s.begin_nested():
                s.add(CompanyMemory(key=f"{_head_key(tier, key)}#r{revision}", kind=REV_KIND,
                                    department=dept or (head.department if head else ""),
                                    subject=(subject or key)[:200], state="recorded",
                                    body=body, sources=resolved, created_at=now,
                                    updated_at=now))
        except IntegrityError:
            raise MemoryError_("concurrent write to the same entry; re-read and retry") from None
        if head is None:
            head = CompanyMemory(key=_head_key(tier, key), kind=HEAD_KIND, department=dept,
                                 created_at=now)
            s.add(head)
        head.subject = (subject or key)[:200]
        head.state = "current"
        head.body = body
        head.sources = resolved
        head.updated_at = now
        s.flush()
        out = _entry(head)
    if tier == "canonical":
        company.record_event(
            db, f"laura.mem.canonical:{key}:r{revision}"[:200], kind="laura.memory.canonical",
            department="executive", actor=actor.label[:64], at=now,
            summary=f"Laura canonical identity fact {key} recorded (revision {revision})",
            refs=[f"company_memory:{_head_key(tier, key)}#r{revision}"])
    return out


def _matches(entry: dict, query) -> bool:
    if query is None:
        return True
    if isinstance(query, str):
        if query.startswith("~"):
            needle = query[1:].lower()
            return needle in (entry["key"] or "").lower() or needle in json.dumps(
                entry["value"], default=str).lower() or needle in (entry["subject"] or "").lower()
        if query.endswith("*"):
            return (entry["key"] or "").startswith(query[:-1])
        return entry["key"] == query
    if isinstance(query, dict):
        if "key" in query and entry["key"] != query["key"]:
            return False
        if "prefix" in query and not (entry["key"] or "").startswith(query["prefix"]):
            return False
        if "department" in query and entry["department"] != query["department"]:
            return False
        if "text" in query:
            return _matches(entry, "~" + str(query["text"]))
        return True
    raise MemoryError_("query is None, a string or a dict")


def _projections(db, query) -> list[dict]:
    """The company's existing lessons, read-only, as experience entries (reuse, F-920)."""
    out: list[dict] = []
    insp = inspect(db.engine)
    with db.session() as s:
        if insp.has_table("lessons"):
            from ...core.models import Lesson
            for r in s.scalars(select(Lesson).where(Lesson.superseded_by.is_(None))
                               .order_by(Lesson.id.desc()).limit(200)):
                out.append({"tier": "experience", "key": f"lesson/{r.id}",
                            "value": {"statement": r.statement, "subject": r.subject,
                                      "confidence": r.confidence},
                            "subject": r.subject, "sources": [f"lessons:{r.id}"]
                            + ([r.evidence_ref] if r.evidence_ref else []),
                            "actor": f"department:{r.origin_cell}", "principal_kind": "department",
                            "department": r.origin_cell, "category": "experience",
                            "generated": False, "revision": None, "authority": "projection",
                            "ref": f"lessons:{r.id}",
                            "created_at": r.at.isoformat() if r.at else None,
                            "updated_at": r.at.isoformat() if r.at else None})
        if insp.has_table("learn_policy_lessons"):
            from ...learn.models import LearnPolicyLesson
            for r in s.scalars(select(LearnPolicyLesson)
                               .order_by(LearnPolicyLesson.id.desc()).limit(200)):
                out.append({"tier": "experience", "key": f"policy_lesson/{r.id}",
                            "value": {"statement": r.statement, "loop": r.loop,
                                      "kind": r.kind, "metric_delta": r.metric_delta},
                            "subject": r.loop, "sources": [f"learn_policy_lessons:{r.id}"]
                            + ([r.evidence_ref] if r.evidence_ref else []),
                            "actor": "department:learn", "principal_kind": "department",
                            "department": "learn", "category": "experience",
                            "generated": False, "revision": None, "authority": "projection",
                            "ref": f"learn_policy_lessons:{r.id}",
                            "created_at": r.at.isoformat() if r.at else None,
                            "updated_at": r.at.isoformat() if r.at else None})
    return [e for e in out if _matches(e, query)]


def _authorise_read(db, principal: Principal, tier: str, key: str = "") -> None:
    check_tier(tier)
    verify(db, principal)
    if not can_read(principal.kind, tier):
        raise PermissionRefused(f"{principal.kind} may not read Laura's {tier} memory")


def read(db, tier: str, query=None, principal: Principal | None = None, *,
         include_projections: bool = True, limit: int = 200) -> list[dict]:
    """Entries of one tier visible to `principal`, newest first.

    `query`: None (all), "exact-key", "prefix*", "~substring", or a dict with any of
    key/prefix/department/text. Public and customer principals are refused outright."""
    ensure_tables(db)
    try:
        _authorise_read(db, principal, tier)
    except MemoryError_ as exc:
        raise _refuse(db, principal, "read", tier if isinstance(tier, str) else "?", "",
                      exc) from None
    with db.session() as s:
        rows = list(s.scalars(select(CompanyMemory).where(
            CompanyMemory.kind == HEAD_KIND,
            CompanyMemory.key.like(f"laura:{tier}:%")).order_by(
            CompanyMemory.updated_at.desc(), CompanyMemory.id.desc())))
        entries = [_entry(r) for r in rows]
    if tier == "relationship" and principal.kind == "department":
        entries = [e for e in entries
                   if relationship_visible_to_department(e["key"], principal.id)]
    entries = [e for e in entries if _matches(e, query)]
    if tier == "experience" and include_projections:
        entries += _projections(db, query)
    return entries[:max(0, int(limit))]


def history(db, tier: str, key: str, principal: Principal | None = None) -> list[dict]:
    """Every revision of one entry, oldest first: the audit trail."""
    ensure_tables(db)
    try:
        _authorise_read(db, principal, tier)
        _check_key(key)
        if tier == "relationship" and principal.kind == "department" \
                and not relationship_visible_to_department(key, principal.id):
            raise PermissionRefused("not visible to this department")
    except MemoryError_ as exc:
        raise _refuse(db, principal, "history", str(tier), str(key), exc) from None
    with db.session() as s:
        rows = list(s.scalars(select(CompanyMemory).where(
            CompanyMemory.kind == REV_KIND,
            CompanyMemory.key.like(f"{_head_key(tier, key)}#r%"))))
        out = [_entry(r) for r in rows]
    return sorted(out, key=lambda e: e["revision"] or 0)


def context(db, principal: Principal, query=None, tiers=None) -> dict:
    """What `principal` may know, merged across tiers, with canonical facts winning.

    An entry in another tier whose key equals a canonical key is returned under `shadowed`,
    never as the answer: a generated or later summary cannot replace a canonical fact."""
    wanted = list(tiers or TIERS)
    visible = [t for t in wanted if t in TIERS and can_read(getattr(principal, "kind", ""), t)]
    if not visible:
        raise _refuse(db, principal, "context", ",".join(map(str, wanted))[:60], "",
                      PermissionRefused("no readable tier for this principal"))
    by_tier = {t: read(db, t, query, principal) for t in visible}
    canonical_keys = {e["key"]: e for e in by_tier.get("canonical", [])}
    shadowed = []
    for t in visible:
        if t == "canonical":
            continue
        keep = []
        for e in by_tier[t]:
            (shadowed if e["key"] in canonical_keys else keep).append(e)
        by_tier[t] = keep
    return {"principal": principal.label, "tiers": by_tier, "canonical": canonical_keys,
            "shadowed": shadowed,
            "sources": sorted({src for es in by_tier.values() for e in es
                               for src in e["sources"]})}


# ---- canonical seed: transcribed from recorded owner rulings, never from a model ----------

CANONICAL_SEED: tuple[tuple[str, object, str], ...] = (
    ("identity/name", "Laura", "decision:D-FB-11"),
    ("identity/role", "Founder/CEO of Brambleloop; a persistent AI person whose company "
                      "Brambleloop is, operationally", "decision:D-FB-13"),
    ("identity/visual_identity_id", "laura-v15-a42aeac7", "decision:D-FB-11"),
    ("identity/model_independence", "No LLM is Laura; models provide cognition. Identity, "
     "memory, history, role and policies persist in Brambleloop durable state across model "
     "swaps, restarts, deploys and context resets.", "decision:D-FB-13"),
    ("identity/public_truth", "Disclosed as an AI where relevant; never claimed to be "
     "biologically human; no fabricated human experiences, physical acts, legal ownership, "
     "signatures or consent.", "decision:D-FB-12"),
    ("identity/constitution", "Cannot override Product Truth, accounting truth, security, "
     "customer safety, evidence requirements, protected spend, legal/platform restrictions "
     "or owner-only authority; Finance, Product Truth and Security can challenge or block "
     "her.", "decision:D-FB-13"),
)


def ensure_canonical_seed(db, *, now: datetime | None = None) -> list[str]:
    """Write the canonical facts above when absent. Never overwrites; returns keys written.

    These are transcriptions of owner rulings already in DECISION_LOG (cited per fact), not
    agent-authored facts, so they enter under actor `owner_ruling:<decision>`. Anything the
    owner later changes goes through `write(..., actor=Principal.owner(...), supersede=True)`.
    """
    ensure_tables(db)
    now = now or _now()
    written = []
    for key, value, src in CANONICAL_SEED:
        if _exists(db, "canonical", key):
            continue
        provenance.resolve(db, src, Principal.laura(), entry_exists=lambda t, k: False)
        body = {"tier": "canonical", "key": key, "value": value,
                "actor": f"owner_ruling:{src.split(':', 1)[1]}", "principal_kind": "owner",
                "generated": False, "category": "canonical", "revision": 1,
                "supersedes": None}
        with db.session() as s:
            try:
                with s.begin_nested():
                    s.add(CompanyMemory(key=f"{_head_key('canonical', key)}#r1", kind=REV_KIND,
                                        subject=key, state="recorded", body=body,
                                        sources=[src], created_at=now, updated_at=now))
                    s.add(CompanyMemory(key=_head_key("canonical", key), kind=HEAD_KIND,
                                        subject=key, state="current", body=body,
                                        sources=[src], created_at=now, updated_at=now))
            except IntegrityError:
                continue
        written.append(key)
    if written:
        company.record_event(db, f"laura.mem.seed:{now.isoformat()}"[:200],
                             kind="laura.memory.canonical", department="executive",
                             actor="owner_ruling", at=now,
                             summary=f"Laura canonical identity seeded from owner rulings: "
                                     f"{len(written)} fact(s)",
                             refs=[f"decision:{d}" for d in ("D-FB-11", "D-FB-12", "D-FB-13")])
    return written
