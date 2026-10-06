"""Provenance: every source must resolve to a record or action that really exists.

No invented history (D-FB-13: "Her history is her real durable work"). A memory entry whose
source does not resolve is refused, so a model cannot write "I launched the autumn range in
2019" into Laura's memory -- there is no row to cite.

Accepted source forms (each checked against durable state at write time):

* `<table>:<pk>`       any table mapped on `core.db.Base` that exists in this database, by
                       primary key (for `company_memory`/`company_timeline`, `key` or id).
* `laura_memory:<tier>:<key>`  another entry in this memory.
* `decision:<ID>`      a DECISION_LOG entry (`D-FB-13`); resolved from the log file when it
                       ships, else from the rulings this module records verbatim below.
* `doc:<path>`         a file under the brambleloop root (no traversal).
* `owner_statement:<ref>`  only from a verified owner principal: the owner telling Laura
                       something is a real action, recorded as `owner_statement:<session>:<ref>`.
"""
from __future__ import annotations

import re
from pathlib import Path

from .errors import ProvenanceRefused

ROOT = Path(__file__).resolve().parents[4]          # .../brambleloop
DECISION_LOG = ROOT / "DECISION_LOG.md"
# Rulings this lane depends on, so `decision:` provenance resolves in a container that ships
# only src/ (the Dockerfile does not copy DECISION_LOG.md).
KNOWN_DECISIONS = frozenset({"D-FB-11", "D-FB-12", "D-FB-13"})
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def _decision_exists(ident: str) -> bool:
    if not _ID.match(ident):
        return False
    if ident in KNOWN_DECISIONS:
        return True
    try:
        text = DECISION_LOG.read_text(encoding="utf-8")
    except OSError:
        return False
    return re.search(rf"^#+\s+{re.escape(ident)}(\s|\(|$)", text, re.M) is not None


def _doc_exists(rel: str) -> bool:
    if not rel or rel.startswith("/") or ".." in Path(rel).parts:
        return False
    p = (ROOT / rel).resolve()
    return p.is_file() and ROOT.resolve() in p.parents


def _table_row_exists(db, table: str, ident: str) -> bool:
    from sqlalchemy import inspect, select

    from ...core.db import Base
    from ...core import models as _core  # noqa: F401 - register mappings
    from ...autonomy import models as _auto  # noqa: F401
    try:
        from ...learn import models as _learn  # noqa: F401
    except Exception:  # noqa: BLE001
        pass
    t = Base.metadata.tables.get(table)
    if t is None or not ident or not inspect(db.engine).has_table(table):
        return False
    with db.session() as s:
        if table in ("company_memory", "company_timeline"):
            if s.execute(select(t.c.id).where(t.c.key == ident)).first() is not None:
                return True
        pk = list(t.primary_key.columns)
        if len(pk) != 1:
            return False
        col = pk[0]
        try:
            value = int(ident) if col.type.python_type is int else ident
        except (ValueError, NotImplementedError):
            return False
        return s.execute(select(col).where(col == value)).first() is not None


def resolve(db, source: str, principal, *, entry_exists) -> str:
    """Return the normalised source string, or raise ProvenanceRefused."""
    if not isinstance(source, str) or ":" not in source or len(source) > 400:
        raise ProvenanceRefused(f"source {source!r} is not a record reference")
    scheme, _, rest = source.partition(":")
    rest = rest.strip()
    if scheme == "owner_statement":
        if principal.kind != "owner":
            raise ProvenanceRefused("only the owner can cite their own statement")
        if not rest:
            raise ProvenanceRefused("an owner statement names what was said or where")
        return f"owner_statement:{principal.id}:{rest[:200]}"
    if scheme == "laura_memory":
        tier, _, key = rest.partition(":")
        if entry_exists(tier, key):
            return source
        raise ProvenanceRefused(f"no memory entry {rest!r}")
    if scheme == "decision":
        if _decision_exists(rest):
            return source
        raise ProvenanceRefused(f"no recorded decision {rest!r}")
    if scheme == "doc":
        if _doc_exists(rest):
            return source
        raise ProvenanceRefused(f"no such document {rest!r}")
    if _table_row_exists(db, scheme, rest):
        return source
    raise ProvenanceRefused(f"source {source!r} does not resolve to a real record")
