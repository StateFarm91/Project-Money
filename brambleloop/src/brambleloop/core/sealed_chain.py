"""Hash-chained, sealed owner-authority rows (rc1-AUTH D1/D2).

A seal over a row's content proves the owner credential wrote that content. It does not prove
the row is *where* it was written: a database writer without the credential could copy an old
sealed row to the end of the table (replaying a superseded decision) or delete a row (an owner
revocation or rollback) and every remaining seal would still verify.

So each sealed row of an authority family also carries, inside its seal:

* ``seq``       -- 1 for the first row of a chain, then +1 per row (monotonic);
* ``prev_id``   -- the id of the row immediately before it in that family (None for the
                   first row ever);
* ``prev_seal`` -- that previous row's seal.

`walk` verifies the family in id order. A copied row names a predecessor that is no longer
the row before it; a deleted row leaves its successor naming a row that is not there; an
inserted unsealed row fails its seal. Each of those breaks the chain, and a broken chain is
never authority -- the callers fall back to their restrictive reading and raise an incident.

The only way past a broken chain is a **rebase** row written under the owner credential: a
sealed row with ``rebase: true``, ``seq`` 1, linked to whatever row is currently last. What a
rebase may assert is decided by the caller (the phase allows only a move down to shadow; a
grant family's rebase invalidates every earlier grant). Copying a rebase row later fails the
link check like any other copy.

Residual, stated rather than hidden: deleting the *newest* rows of a family (tail truncation)
leaves a shorter chain that still verifies. Nothing inside the database can detect that; the
mitigations are outside it -- the phase also needs ``BRAMBLELOOP_PHASE`` to agree, and grants
expire in 24 hours behind the environment kill-switch.
"""
from __future__ import annotations

from typing import Any, Callable, Iterable

CHAIN_KEYS = ("seq", "prev_id", "prev_seal")


def _int(value) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def walk(rows: Iterable[tuple[int, dict]], verify_seal: Callable[[dict], str | None], *,
         link_ok: Callable[[dict, dict], str | None] | None = None,
         rebase_ok: Callable[[dict], str | None] | None = None) -> dict:
    """Verify a family of rows given oldest first as (id, detail).

    Returns ``valid`` (the chain holds at its newest row), ``start_id`` (the first row of the
    current valid segment: the genesis row or the newest rebase), ``broken_at`` / ``why`` (the
    first row that broke the current segment), and ``rows``: per row, whether the chain was
    valid up to and including it.
    """
    valid = True
    start_id = None
    broken_at = None
    why = None
    per_row: list[tuple[int, bool, str | None]] = []
    prev_id = None
    prev: dict | None = None
    empty = True
    for rid, detail in rows:
        empty = False
        d = dict(detail or {})
        seal_why = verify_seal(d)
        seq = _int(d.get("seq"))
        row_why = None
        if prev is None:
            if seal_why is not None:
                row_why = seal_why
            elif seq != 1 or d.get("prev_id") is not None or d.get("rebase"):
                row_why = ("first recorded row is not a chain genesis (seq 1, no "
                           "predecessor): rows before it were deleted, or it predates chaining")
            if row_why is None:
                start_id = rid
            else:
                valid, broken_at, why = False, rid, row_why
        else:
            linked = (_int(d.get("prev_id")) == prev_id
                      and str(d.get("prev_seal", "")) == str(prev.get("seal", "")))
            if seal_why is not None:
                row_why = seal_why
            elif not linked:
                row_why = ("chain link broken: this row does not name the row before it "
                           "(a replayed/copied row, or a deleted predecessor)")
            elif d.get("rebase") is True:
                if seq != 1:
                    row_why = "rebase row must restart the sequence at 1"
                else:
                    row_why = rebase_ok(d) if rebase_ok else None
                if row_why is None:
                    # A sealed, linked rebase starts a new valid segment whatever came before.
                    valid, start_id, broken_at, why = True, rid, None, None
            elif not valid:
                row_why = why or "chain already broken"
            elif seq is None or seq != (_int(prev.get("seq")) or -10) + 1:
                row_why = "sequence is not monotonic (+1 per row)"
            elif link_ok is not None:
                row_why = link_ok(prev, d)
            if row_why is not None and (valid or d.get("rebase") is True):
                valid, broken_at, why = False, rid, row_why
        per_row.append((rid, valid, row_why))
        prev_id, prev = rid, d
    return {"valid": valid if not empty else True, "empty": empty, "start_id": start_id,
            "broken_at": broken_at, "why": why, "rows": per_row}


def next_link(rows: list[tuple[int, dict]], chain: dict | None = None) -> dict:
    """The chain fields for a new row appended after `rows` (oldest first).

    A continuation when the chain holds; a rebase (``rebase: true``) when it is broken -- the
    caller decides whether its row may be a rebase and refuses otherwise.
    """
    if not rows:
        return {"seq": 1, "prev_id": None, "prev_seal": ""}
    last_id, last = rows[-1]
    last = dict(last or {})
    if chain is not None and chain.get("valid"):
        return {"seq": (_int(last.get("seq")) or 0) + 1, "prev_id": last_id,
                "prev_seal": str(last.get("seal", ""))}
    return {"seq": 1, "prev_id": last_id, "prev_seal": str(last.get("seal", "")),
            "rebase": True}


def load(session, actions: Iterable[str]) -> list[tuple[int, dict]]:
    """Every row of the family, oldest first, as (id, detail)."""
    from sqlalchemy import select

    from .models import AuditLog

    acts = tuple(actions)
    return [(r.id, dict(r.detail or {})) for r in session.scalars(
        select(AuditLog).where(AuditLog.action.in_(acts)).order_by(AuditLog.id))]


def tamper_incident(db, *, signature: str, chain: dict, summary: str) -> None:
    """Open (or restate) a P1 tamper incident for a broken chain; resolve it when it holds.
    Never raises: incident bookkeeping must not widen any authority."""
    try:
        from ..ops import incident_lifecycle
        from .models import AuditLog

        with db.session() as s:
            if not chain.get("valid"):
                detail: dict[str, Any] = {"broken_at": chain.get("broken_at"),
                                          "why": chain.get("why")}
                _row, opened = incident_lifecycle.open_or_restate(
                    s, signature=signature, severity="P1",
                    summary=(summary + f": {chain.get('why')}")[:2000], detail=detail)
                if opened:
                    s.add(AuditLog(actor="system", action="authority.chain_tamper",
                                   artifact=signature, detail=detail))
            else:
                incident_lifecycle.resolve_signatures(
                    s, [signature], resolution="authority chain verifies end to end")
    except Exception:  # noqa: BLE001
        pass


class GrantLedger:
    """D2: an owner grant family (approvals, revocations, rebases) kept as one sealed chain.

    * a revocation is a sealed, chained row bound to the grant's own seal;
    * any revocation row naming a grant revokes it -- an unsealed or forged one included
      (fail closed) -- and, not being validly sealed in place, also breaks the chain;
    * a grant is usable only while the whole family chain verifies and the grant sits in the
      current valid segment (after the newest owner rebase). Deleting a revocation from the
      middle of the chain therefore refuses every grant instead of reviving one, and opens a
      P1 tamper incident;
    * the owner re-anchors a broken chain with `rebase`, which voids every earlier grant.
    """

    def __init__(self, *, approved: str, revoked: str, rebased: str, principal: str,
                 seal: Callable[[dict], str], signature: str, label: str) -> None:
        self.approved, self.revoked, self.rebased = approved, revoked, rebased
        self.actions = (approved, revoked, rebased)
        self.principal = principal
        self._seal = seal
        self.signature = signature
        self.label = label

    def verify_row(self, detail: dict) -> str | None:
        import hmac

        d = dict(detail or {})
        seal = d.pop("seal", "")
        try:
            expected = self._seal(d)
        except ValueError:
            return "owner credential unavailable, so no grant row can be verified"
        if not hmac.compare_digest(str(seal), expected):
            return f"{self.label} row seal invalid (edited, hand-inserted or credential rotated)"
        return None

    def _rebase_ok(self, detail: dict) -> str | None:
        if detail.get("event") in (self.revoked, self.rebased):
            return None
        return "only a revocation or an owner rebase may re-anchor a broken grant chain"

    def _walk(self, rows):
        return walk(rows, self.verify_row, rebase_ok=self._rebase_ok)

    def chain(self, db, *, record_incident: bool = True) -> dict:
        with db.session() as s:
            rows = load(s, self.actions)
        c = self._walk(rows)
        if record_incident:
            tamper_incident(db, signature=self.signature, chain=c,
                            summary=f"{self.label} chain does not verify (a grant or "
                                    f"revocation row was replayed, inserted or deleted); every "
                                    f"grant is refused until the owner rebases")
        return c

    def append(self, db, *, action: str, artifact: str, detail: dict) -> int:
        """Seal and append one row, chained to the current last row of the family."""
        from .models import AuditLog

        with db.session() as s:
            rows = load(s, self.actions)
            c = self._walk(rows)
            link = next_link(rows, c)
            if link.get("rebase") and action == self.approved:
                raise ValueError(f"the {self.label} chain does not verify ({c.get('why')}); "
                                 f"the owner must rebase it before any new grant")
            body = {**detail, "event": action, **link}
            body["seal"] = self._seal(body)
            row = AuditLog(actor=self.principal, action=action, artifact=artifact, detail=body)
            s.add(row)
            s.flush()
            return row.id

    def revoke(self, db, approval_id: int) -> int:
        from datetime import datetime, timezone

        from .models import AuditLog

        ident = int(approval_id)
        with db.session() as s:
            grant = s.get(AuditLog, ident)
            grant_seal = (str((grant.detail or {}).get("seal", ""))
                          if grant is not None and grant.action == self.approved else "")
        return self.append(db, action=self.revoked, artifact=str(ident),
                           detail={"principal": self.principal, "approval_id": ident,
                                   "grant_seal": grant_seal,
                                   "revoked_at": datetime.now(timezone.utc).isoformat()})

    def rebase(self, db, reason: str) -> int:
        from datetime import datetime, timezone

        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("owner decision reason required")
        from .models import AuditLog

        with db.session() as s:
            rows = load(s, self.actions)
            c = self._walk(rows)
            body = {"principal": self.principal, "event": self.rebased,
                    "reason": reason.strip(), "voids_grants_before": True,
                    "chain_was": {"valid": c["valid"], "why": c.get("why")},
                    "at": datetime.now(timezone.utc).isoformat(),
                    "seq": 1, "prev_id": rows[-1][0] if rows else None,
                    "prev_seal": str(rows[-1][1].get("seal", "")) if rows else "",
                    "rebase": bool(rows)}
            if not rows:
                body.pop("rebase")
            body["seal"] = self._seal(body)
            row = AuditLog(actor=self.principal, action=self.rebased, artifact="chain",
                           detail=body)
            s.add(row)
            s.flush()
            ident = row.id
        self.chain(db)  # resolves the tamper incident once the chain verifies again
        return ident

    def refusal(self, db, ident: int) -> str | None:
        """Chain-level reasons this grant id is not usable, or None. Fails closed."""
        from sqlalchemy import select

        from .models import AuditLog

        with db.session() as s:
            revocations = [dict(d or {}) for d in s.scalars(
                select(AuditLog.detail).where(AuditLog.action == self.revoked,
                                              AuditLog.artifact == str(int(ident))))]
        c = self.chain(db)
        if revocations:
            if any(self.verify_row(d) is not None for d in revocations):
                return (f"{self.label} revoked by a row that does not verify; treated as "
                        f"revoked and reported as tampering")
            return f"{self.label} revoked"
        if not c["valid"]:
            return f"{self.label} chain does not verify ({c.get('why')}); every grant refused"
        if c["start_id"] is None or int(ident) < int(c["start_id"]):
            return f"{self.label} predates the owner's latest chain rebase"
        flags = {rid: ok for rid, ok, _why in c["rows"]}
        if not flags.get(int(ident)):
            return f"{self.label} is not a verified link of the grant chain"
        return None
