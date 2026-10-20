"""The private store: encrypted owner-supplied facts and genuine interaction turns.

Provenance (spec/07 Ruling 2: "only facts actually supplied/authorised by the couple and
genuine interactions ... never invented history"):

* `owner_supplied` -- a fact the owner entered through a live private context. No sources.
* `interaction`    -- a fact quoted VERBATIM from turns that exist in this store. Every
                      cited turn must exist and decrypt, and the text must appear in one of
                      them; a paraphrase or summary is refused because it is generated text.
* Turns: an `owner` turn is what the owner typed. A `laura` turn is a reply that must answer
  an existing owner turn issued in the SAME live grant (the same open conversation), at most
  one reply per owner turn, and must name the model that produced it. That makes it
  impossible to backfill or bulk-import a conversation that never happened.
* Anything else -- "generated", "summary", "inferred", "imported", a model's recollection,
  caller-supplied timestamps -- is refused. There is no parameter for a past date.

Nothing here writes to `company_memory`, `company_timeline`, `audit_log`, notifications,
`cc_security_events` or Python logging. Values come back as `PrivateValue`s.
"""
from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError

from . import crypto
from .access import record_access, require
from .errors import (IntegrityRefused, KeyMismatch, KeyUnavailable, PrivateAccessRefused,
                     PrivateProvenanceRefused, PrivateRefused)
from .models import PrivateEntry, ensure_tables
from .values import PrivateRecord, PrivateValue

PROVENANCE = ("owner_supplied", "interaction")
ROLES = ("owner", "laura")
#: W4-LAURAONE (D-W4-LAURA-UNIFIED): a unified-thread turn's topic label, sealed in its payload.
LABELS = ("business", "private", "everyday", "mixed")
#: A crossing request's lifecycle (sealed; kind "xing").
CROSSING_STATUS = ("pending", "approved", "declined")
CROSSING_ORIGINS = ("owner_quote", "laura_draft")
MAX_TEXT = 16_384
MAX_KEY = 120
MAX_SOURCES = 20


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _aad(e: PrivateEntry) -> bytes:
    return "|".join([crypto.SCHEME, e.record_id, e.kind, e.provenance, e.key_index,
                     e.grant_ref, e.reply_to or "", e.created_at, e.key_id]).encode()


def _seal(keys, entry: PrivateEntry, payload: dict) -> None:
    entry.key_id, entry.scheme = keys.key_id, crypto.SCHEME
    entry.nonce, entry.ciphertext = crypto.seal(
        keys, json.dumps(payload, sort_keys=True).encode("utf-8"), _aad(entry))


def _open(keys, entry: PrivateEntry) -> dict:
    if entry.scheme != crypto.SCHEME:
        raise IntegrityRefused("private record failed authentication")
    raw = crypto.open_sealed(keys, entry.key_id, entry.nonce, entry.ciphertext, _aad(entry))
    try:
        return json.loads(raw.decode("utf-8"))
    except ValueError:
        raise IntegrityRefused("private record failed authentication") from None


def _text(value, limit: int, what: str) -> str:
    if type(value) is not str or not value.strip() or len(value) > limit:
        raise PrivateProvenanceRefused(f"{what} must be non-empty text of at most {limit} chars")
    return value


def _guarded(op: str):
    """Log refusals for op-level checks that run after `require` succeeded."""
    def wrap(fn):
        def inner(db, principal, *a, **kw):
            try:
                return fn(db, principal, *a, **kw)
            except PrivateRefused as exc:
                if not isinstance(exc, (PrivateAccessRefused, KeyUnavailable)):
                    record_access(db, op, "refused", type(exc).__name__, principal)
                raise
        inner.__name__ = fn.__name__
        inner.__doc__ = fn.__doc__
        return inner
    return wrap


def _new_entry(keys, grant, kind: str, provenance: str, index_text: str,
               reply_to: str | None = None) -> PrivateEntry:
    prefix = {"fact": "pf_", "turn": "pt_", "xing": "px_"}[kind]
    return PrivateEntry(record_id=prefix + secrets.token_hex(16),
                        kind=kind, provenance=provenance,
                        key_index=crypto.blind_index(keys, index_text),
                        grant_ref=crypto.blind_index(keys, "grant:" + grant.grant_id),
                        reply_to=reply_to, created_at=_iso())


def _load(db, keys, record_id: str, kind: str):
    with db.session() as s:
        e = s.scalar(select(PrivateEntry).where(PrivateEntry.record_id == record_id,
                                                PrivateEntry.kind == kind))
    return (e, _open(keys, e)) if e is not None else (None, None)


@_guarded("remember")
def remember(db, principal, key: str, text: str, *, provenance: str = "owner_supplied",
             sources=(), generated: bool = False) -> str:
    """Store a fact. Returns its record id (random, non-content)."""
    keys, grant = require(db, principal, "remember")
    if generated:
        raise PrivateProvenanceRefused("generated text is never stored as private history")
    if provenance not in PROVENANCE:
        raise PrivateProvenanceRefused("provenance must be owner_supplied or interaction")
    key = _text(key, MAX_KEY, "key").strip()
    text = _text(text, MAX_TEXT, "text")
    sources = list(sources or [])
    if provenance == "owner_supplied" and sources:
        raise PrivateProvenanceRefused("an owner-supplied fact cites no other record")
    if provenance == "interaction":
        if not sources or len(sources) > MAX_SOURCES \
                or not all(isinstance(x, str) for x in sources):
            raise PrivateProvenanceRefused("an interaction fact cites the turns it quotes")
        quoted = False
        for rid in sources:
            entry, payload = _load(db, keys, rid, "turn")
            if entry is None:
                raise PrivateProvenanceRefused("a cited turn does not exist")
            quoted = quoted or text in payload["text"]
        if not quoted:
            raise PrivateProvenanceRefused(
                "an interaction fact must quote a cited turn verbatim (no generated summary)")
    ensure_tables(db)
    entry = _new_entry(keys, grant, "fact", provenance, "fact:" + key)
    _seal(keys, entry, {"key": key, "text": text, "sources": sources})
    with db.session() as s:
        s.add(entry)
    record_access(db, "remember", "ok", provenance, principal)
    return entry.record_id


@_guarded("turn")
def record_turn(db, principal, role: str, text: str, *, reply_to: str | None = None,
                model_ref: str | None = None, label: str | None = None,
                sensitive: bool = False) -> str:
    """Record one genuine interaction turn in the open private conversation.

    W4-LAURAONE: a unified-thread turn also carries its topic `label` (and a `sensitive` flag)
    INSIDE the sealed payload; without a label the payload is exactly as before."""
    keys, grant = require(db, principal, "turn")
    if role not in ROLES:
        raise PrivateProvenanceRefused("a turn's role is owner or laura")
    if label is not None and label not in LABELS:
        raise PrivateProvenanceRefused("a turn's label is fixed vocabulary")
    text = _text(text, MAX_TEXT, "text")
    if role == "owner":
        if reply_to is not None or model_ref is not None:
            raise PrivateProvenanceRefused("an owner turn is what the owner typed")
    else:
        model_ref = _text(model_ref, 120, "model_ref")
        if not isinstance(reply_to, str):
            raise PrivateProvenanceRefused("a laura turn answers an existing owner turn")
        entry, payload = _load(db, keys, reply_to, "turn")
        if entry is None or payload.get("role") != "owner":
            raise PrivateProvenanceRefused("a laura turn answers an existing owner turn")
        if entry.grant_ref != crypto.blind_index(keys, "grant:" + grant.grant_id):
            raise PrivateProvenanceRefused(
                "a reply belongs to the live conversation it answers (no backfilled history)")
    ensure_tables(db)
    entry = _new_entry(keys, grant, "turn", "interaction", "turn", reply_to=reply_to)
    payload = {"role": role, "text": text, "model_ref": model_ref}
    if label is not None:
        payload.update(label=label, sensitive=bool(sensitive), excluded=False)
    _seal(keys, entry, payload)
    try:
        with db.session() as s:
            s.add(entry)
    except IntegrityError:
        raise PrivateProvenanceRefused("that owner turn already has its reply") from None
    record_access(db, "turn", "ok", role, principal)
    return entry.record_id


def _record(e: PrivateEntry, p: dict) -> PrivateRecord:
    return PrivateRecord(record_id=e.record_id, kind=e.kind, provenance=e.provenance,
                         created_at=e.created_at, role=p.get("role"),
                         model_ref=p.get("model_ref"), reply_to=e.reply_to,
                         key=PrivateValue(p["key"]) if "key" in p else None,
                         value=PrivateValue(p["text"]),
                         sources=(tuple(p.get("sources") or ()) if not p.get("source")
                                  else (p["source"],)),
                         label=p.get("label"), excluded=bool(p.get("excluded")),
                         sensitive=bool(p.get("sensitive")), status=p.get("status"))


@_guarded("read")
def facts(db, principal, key: str | None = None, *, history: bool = False) -> list:
    """Owner facts (latest per key unless history=True) as PrivateRecords."""
    keys, _ = require(db, principal, "read")
    ensure_tables(db)
    stmt = select(PrivateEntry).where(PrivateEntry.kind == "fact")
    if key is not None:
        stmt = stmt.where(PrivateEntry.key_index == crypto.blind_index(keys, "fact:" + key))
    with db.session() as s:
        rows = list(s.scalars(stmt.order_by(PrivateEntry.id.desc())))
    out, seen = [], set()
    for e in rows:
        if not history and e.key_index in seen:
            continue
        seen.add(e.key_index)
        out.append(_record(e, _open(keys, e)))
    record_access(db, "read", "ok", "facts", principal)
    return out


@_guarded("read")
def conversation(db, principal, *, limit: int = 50) -> list:
    """The most recent interaction turns, oldest first, as PrivateRecords."""
    keys, _ = require(db, principal, "read")
    ensure_tables(db)
    limit = max(1, min(int(limit), 500))
    with db.session() as s:
        rows = list(s.scalars(select(PrivateEntry).where(PrivateEntry.kind == "turn")
                              .order_by(PrivateEntry.id.desc()).limit(limit)))
    out = [_record(e, _open(keys, e)) for e in reversed(rows)]
    record_access(db, "read", "ok", "conversation", principal)
    return out


@_guarded("forget")
def forget(db, principal, record_id: str) -> int:
    """Delete a fact or turn (an owner turn takes its reply, and any crossing request quoting
    it, with it). Returns rows deleted."""
    keys, _ = require(db, principal, "forget")
    ensure_tables(db)
    with db.session() as s:
        xings = list(s.scalars(select(PrivateEntry).where(PrivateEntry.kind == "xing")))
    quoting = [e.record_id for e in xings if _open(keys, e).get("source") == record_id]
    with db.session() as s:
        n = 0
        if quoting:
            n += s.execute(delete(PrivateEntry).where(
                PrivateEntry.record_id.in_(quoting))).rowcount
        n += s.execute(delete(PrivateEntry).where(PrivateEntry.reply_to == record_id)).rowcount
        n += s.execute(delete(PrivateEntry).where(PrivateEntry.record_id == record_id)).rowcount
    record_access(db, "forget", "ok", "", principal)
    return int(n or 0)


@_guarded("export")
def sealed_export(db, principal) -> dict:
    """Owner-held backup: ciphertext and bound metadata only, verifiable with the key.

    Every row is authenticated before it is exported, so a backup never silently carries a
    tampered record. Restoring needs the same key (see `restore_sealed`).
    """
    keys, _ = require(db, principal, "export")
    ensure_tables(db)
    cols = [c.name for c in PrivateEntry.__table__.columns if c.name != "id"]
    with db.session() as s:
        rows = list(s.scalars(select(PrivateEntry).order_by(PrivateEntry.id)))
    for e in rows:
        _open(keys, e)
    record_access(db, "export", "ok", "", principal)
    return {"format": "brambleloop.laura.private.sealed.v1", "key_id": keys.key_id,
            "rows": [{c: getattr(e, c) for c in cols} for e in rows]}


@_guarded("restore")
def restore_sealed(db, principal, bundle: dict) -> int:
    """Restore a sealed export into this database (same key). Each row is authenticated."""
    keys, _ = require(db, principal, "restore")
    if not isinstance(bundle, dict) or bundle.get("format") != \
            "brambleloop.laura.private.sealed.v1":
        raise IntegrityRefused("not a sealed private export")
    if not crypto.tags_equal(bundle.get("key_id"), keys.key_id):
        raise KeyMismatch("sealed export was made under a different private key")
    ensure_tables(db)
    entries = [PrivateEntry(**r) for r in bundle.get("rows") or []]
    for e in entries:
        _open(keys, e)
    added = 0
    with db.session() as s:
        have = set(s.scalars(select(PrivateEntry.record_id)))
        for e in entries:
            if e.record_id not in have:
                s.add(e)
                added += 1
    record_access(db, "restore", "ok", "", principal)
    return added


@_guarded("rekey")
def rekey(db, principal, new_env) -> dict:
    """Rotate the private key: sealed_export (old key) -> re-seal -> the restore bundle.

    Key rotation through the existing backup path (handoff_PRIV open item; PRIVATE_LAURA_TRACE
    Step 5). The live principal proves the CURRENT key; `new_env` is a mapping holding the new
    `BRAMBLELOOP_PRIVATE_MEMORY_KEY` (never read from or written to os.environ here, never
    logged). Every row is authenticated under the old key (via `sealed_export`), decrypted,
    and re-sealed under the new key with the same record id, kind, provenance, timestamp and
    reply link; blind indexes are recomputed (a grant reference is re-bound through the grant
    table, and a row whose grant cannot be found refuses the whole rotation). The store is then
    replaced atomically -- same row count or nothing changes -- and every live grant is
    revoked, because grants were issued under the old key: the owner reopens the context
    under the new key. Returns non-content counts plus the re-sealed bundle (ciphertext only),
    which `restore_sealed` accepts under the new key.
    """
    bundle = sealed_export(db, principal)               # authenticates every row (old key)
    old, _ = require(db, principal, "rekey")
    new = crypto.load_keys(new_env)
    if crypto.tags_equal(old.key_id, new.key_id):
        raise KeyMismatch("the new private key is the current key")
    from .models import PrivateGrant

    with db.session() as s:
        grants = list(s.scalars(select(PrivateGrant.grant_id)))
    by_ref = {crypto.blind_index(old, "grant:" + g): g for g in grants}
    rows = []
    for raw in bundle["rows"]:
        e = PrivateEntry(**raw)
        payload = _open(old, e)
        gid = by_ref.get(e.grant_ref)
        if gid is None:
            raise IntegrityRefused("a private record's grant cannot be re-bound; not rotated")
        index_text = (("fact:" + payload["key"]) if e.kind == "fact"
                      else "xing" if e.kind == "xing" else "turn")
        n = PrivateEntry(record_id=e.record_id, kind=e.kind, provenance=e.provenance,
                         key_index=crypto.blind_index(new, index_text),
                         grant_ref=crypto.blind_index(new, "grant:" + gid),
                         reply_to=e.reply_to, created_at=e.created_at)
        _seal(new, n, payload)
        rows.append(n)
    cols = [c.name for c in PrivateEntry.__table__.columns if c.name != "id"]
    new_bundle = {"format": bundle["format"], "key_id": new.key_id,
                  "rows": [{c: getattr(n, c) for c in cols} for n in rows]}
    from sqlalchemy import func

    with db.session() as s:
        if s.scalar(select(func.count()).select_from(PrivateEntry)) != len(rows):
            raise IntegrityRefused("the private store changed during rotation; not rotated")
        # Replies first (they point at owner turns), then the rest; then the re-sealed rows
        # in their original order, so ids keep the conversation's order.
        s.execute(delete(PrivateEntry).where(PrivateEntry.reply_to.is_not(None)))
        s.execute(delete(PrivateEntry))
        s.flush()
        for n in [PrivateEntry(**r) for r in new_bundle["rows"]]:
            s.add(n)
        s.execute(update(PrivateGrant).where(PrivateGrant.revoked_at.is_(None)).values(
            revoked_at=datetime.now(timezone.utc), revoked_reason="rekeyed"))
    record_access(db, "rekey", "ok", "", principal)
    return {"rotated": len(rows), "old_key_id": old.key_id, "new_key_id": new.key_id,
            "grants_revoked": True, "bundle": new_bundle}


# ---------------------------------------------------------------------------
# W4-LAURAONE (D-W4-LAURA-UNIFIED): owner privacy controls and boundary-crossing requests.


def _reseal(db, keys, entry: PrivateEntry, payload: dict) -> None:
    """Re-seal one row's payload under the current key; the bound metadata is unchanged."""
    with db.session() as s:
        row = s.scalar(select(PrivateEntry).where(PrivateEntry.record_id == entry.record_id))
        if row is None:
            raise PrivateProvenanceRefused("the record does not exist")
        _seal(keys, row, payload)


@_guarded("flags")
def set_turn_flags(db, principal, record_id: str, *, label: str | None = None,
                   excluded: bool | None = None) -> bool:
    """The owner's privacy controls on one turn: re-label it (e.g. mark it private) and/or
    exclude it from (or return it to) model context. Sealed; the text never changes."""
    keys, _ = require(db, principal, "flags")
    if label is not None and label not in LABELS:
        raise PrivateProvenanceRefused("a turn's label is fixed vocabulary")
    entry, payload = _load(db, keys, str(record_id or ""), "turn")
    if entry is None:
        return False
    if label is not None:
        payload["label"] = label
    if excluded is not None:
        payload["excluded"] = bool(excluded)
    _reseal(db, keys, entry, payload)
    record_access(db, "flags", "ok", "", principal)
    return True


@_guarded("xing")
def request_crossing(db, principal, source_turn_id: str, text: str, *,
                     sensitive: bool = False, origin: str = "owner_quote") -> str:
    """Seal a proposal to share `text` with the business side; nothing crosses until
    `resolve_crossing(approve=True)`. `origin` "owner_quote": quoted VERBATIM from the owner
    turn it cites. "laura_draft": a brief Laura drafted while answering that owner turn,
    shown to the owner word for word before anything is sent (never stored as history)."""
    keys, grant = require(db, principal, "xing")
    if origin not in CROSSING_ORIGINS:
        raise PrivateProvenanceRefused("a crossing request's origin is fixed vocabulary")
    text = _text(text, MAX_TEXT, "text")
    entry, payload = _load(db, keys, str(source_turn_id or ""), "turn")
    if entry is None or payload.get("role") != "owner" or (
            origin == "owner_quote" and text not in payload["text"]):
        raise PrivateProvenanceRefused("a crossing request quotes an existing owner turn")
    ensure_tables(db)
    x = _new_entry(keys, grant, "xing", "interaction", "xing")
    _seal(keys, x, {"text": text, "source": entry.record_id, "status": "pending",
                    "sensitive": bool(sensitive), "origin": origin})
    with db.session() as s:
        s.add(x)
    record_access(db, "xing", "ok", "requested", principal)
    return x.record_id


@_guarded("read")
def crossings(db, principal) -> list:
    """Every crossing request, oldest first, as PrivateRecords (status in `.status`)."""
    keys, _ = require(db, principal, "read")
    ensure_tables(db)
    with db.session() as s:
        rows = list(s.scalars(select(PrivateEntry).where(PrivateEntry.kind == "xing")
                              .order_by(PrivateEntry.id)))
    out = [_record(e, _open(keys, e)) for e in rows]
    record_access(db, "read", "ok", "crossings", principal)
    return out


@_guarded("xing")
def resolve_crossing(db, principal, crossing_id: str, *, approve: bool):
    """Approve or decline a PENDING request; returns its PrivateRecord (None if absent)."""
    keys, _ = require(db, principal, "xing")
    entry, payload = _load(db, keys, str(crossing_id or ""), "xing")
    if entry is None:
        return None
    if payload.get("status") != "pending":
        raise PrivateProvenanceRefused("a crossing request is resolved once")
    payload["status"] = "approved" if approve else "declined"
    _reseal(db, keys, entry, payload)
    record_access(db, "xing", "ok", payload["status"], principal)
    return _record(entry, payload)


def configured(env=None) -> bool:
    """Whether a usable key is configured. Non-content; safe for a status badge."""
    try:
        crypto.load_keys(env)
        return True
    except PrivateRefused:
        return False
