"""Monthly Etsy statement archive (F-576): the original, its totals, and the reconciliation.

Etsy publishes no statement endpoint (`intel.etsy_surfaces` surface `monthly_statements`); the
statement is a download behind the seller login, and it is still the authority for what Etsy
charged. So the owner archives it:

* **The original is preserved.** Its bytes go to `durable_artifacts` keyed by sha256, so the
  file outlives a container restart and is the same file tomorrow. Archiving the same bytes
  again changes nothing. A different file for the same month is a new **version**; earlier
  versions are never overwritten or deleted (audit).
* **The totals are extracted** -- revenue, fees, tax, refunds, payouts, in CAD -- as the owner
  read them off the statement. Every one is required; a total that is not on the statement
  is entered as `null` and stays UNKNOWN, never zero.
* **They are reconciled** against the ledger's reconstruction of the same month
  (`views.accrual` for revenue, fees and refunds; payout statement lines for payouts). A
  difference is an accounting exception (`statement:<YYYY-MM>:<metric>`); where they differ
  the statement wins, and the exception says by how much. Tax has no ledger reconstruction
  (Etsy collects and remits marketplace tax), so it is archived and reported UNKNOWN.

Nothing here moves money, files anything or writes the journal.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone

from sqlalchemy import select

from . import exceptions as X
from .schema import ensure

ARCHIVED = "finance.statement_archived"
METRICS = ("revenue_cad", "fees_cad", "tax_cad", "refunds_cad", "payouts_cad")
TOLERANCE_CAD = 0.01
MAX_BYTES = 10 * 1024 * 1024
_PERIOD = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


class StatementRefused(ValueError):
    pass


def _period_bounds(period: str) -> tuple[datetime, datetime]:
    y, m = (int(x) for x in period.split("-"))
    start = datetime(y, m, 1, tzinfo=timezone.utc)
    end = datetime(y + (m == 12), 1 if m == 12 else m + 1, 1, tzinfo=timezone.utc)
    return start, end


def archive(db, *, period: str, original: bytes, content_type: str, totals: dict,
            recorded_by: str = "owner", now: datetime | None = None) -> dict:
    """Keep the statement's bytes and its totals. Idempotent on (period, sha256)."""
    from ...core.models import AuditLog, DurableArtifact

    now = now or datetime.now(timezone.utc)
    if not _PERIOD.match(str(period or "")):
        raise StatementRefused("period must be YYYY-MM")
    if _period_bounds(period)[0] > now:
        raise StatementRefused("a statement cannot be for a month that has not started")
    if not original:
        raise StatementRefused("the original statement file is required (it is the evidence)")
    if len(original) > MAX_BYTES:
        raise StatementRefused(f"statement file over {MAX_BYTES} bytes")
    missing = [k for k in METRICS if k not in (totals or {})]
    if missing:
        raise StatementRefused(f"totals missing {missing}; enter null for one the statement "
                               f"does not show")
    clean = {}
    for k in METRICS:
        v = totals[k]
        if v is not None and not isinstance(v, (int, float)):
            raise StatementRefused(f"totals.{k} must be a number or null")
        clean[k] = None if v is None else round(float(v), 2)
    digest = hashlib.sha256(original).hexdigest()
    db = ensure(db)
    with db.session() as s:
        prior = [r for r in s.scalars(select(AuditLog).where(AuditLog.action == ARCHIVED)
                                      .order_by(AuditLog.id))
                 if (r.detail or {}).get("period") == period]
        for r in prior:
            if r.detail.get("sha256") == digest:
                return {"archived": False, "replayed": True, "period": period,
                        "sha256": digest, "version": r.detail.get("version"),
                        "audit_id": r.id}
        if s.get(DurableArtifact, digest) is None:
            s.add(DurableArtifact(sha256=digest, content_type=str(content_type or
                                                                  "application/pdf")[:80],
                                  bytes_len=len(original), payload=original,
                                  why_kept=f"Etsy monthly statement {period} (F-576)"))
            s.flush()
        version = len(prior) + 1
        row = AuditLog(actor=recorded_by[:64], action=ARCHIVED, artifact=f"statement:{period}",
                       detail={"period": period, "sha256": digest, "bytes": len(original),
                               "content_type": content_type, "totals": clean,
                               "version": version,
                               "supersedes": prior[-1].detail.get("sha256") if prior else None,
                               "recorded_at": now.isoformat()})
        s.add(row)
        s.flush()
        audit_id = row.id
        held = s.get(DurableArtifact, digest) is not None
    return {"archived": True, "replayed": False, "period": period, "sha256": digest,
            "version": version, "audit_id": audit_id, "original_held": held,
            "reconciliation": reconcile(db, period, now=now)}


def latest(db, period: str) -> dict | None:
    from ...core.models import AuditLog

    db = ensure(db)
    with db.session() as s:
        rows = [r for r in s.scalars(select(AuditLog).where(AuditLog.action == ARCHIVED)
                                     .order_by(AuditLog.id.desc()))
                if (r.detail or {}).get("period") == period]
        return dict(rows[0].detail) | {"audit_id": rows[0].id} if rows else None


def original(db, sha256: str) -> bytes | None:
    from ...core.models import DurableArtifact

    db = ensure(db)
    with db.session() as s:
        row = s.get(DurableArtifact, sha256)
        return bytes(row.payload) if row is not None else None


def reconstruct(db, period: str) -> dict:
    """The ledger's figures for the month, each with its reading."""
    from . import views
    from .models import AcctStatementLine

    start, end = _period_bounds(period)
    acc = views.accrual(db, since=start, until=end)
    db = ensure(db)
    with db.session() as s:
        payout_lines = [l for l in s.scalars(select(AcctStatementLine).where(
            AcctStatementLine.source == "etsy_ledger", AcctStatementLine.kind == "payout",
            AcctStatementLine.state != "duplicate"))
            if start <= (l.at if l.at.tzinfo else l.at.replace(tzinfo=timezone.utc)) < end]
    payouts = round(sum(abs(l.amount_micros) for l in payout_lines) / 1_000_000, 2)
    return {"revenue_cad": acc.get("accrual_gross_sales_cad"),
            "fees_cad": acc.get("accrual_platform_fees_cad"),
            "refunds_cad": acc.get("accrual_refunds_cad"),
            "payouts_cad": payouts if payout_lines else None,
            "tax_cad": None,
            "sales_reading": acc.get("sales_reading")}


def reconcile(db, period: str, *, now: datetime | None = None) -> dict:
    """Statement vs ledger, per metric. A difference is an exception; the statement wins."""
    now = now or datetime.now(timezone.utc)
    st = latest(db, period)
    if st is None:
        return {"period": period, "state": "UNKNOWN", "why": "no statement archived"}
    led = reconstruct(db, period)
    out, differ = {}, []
    for k in METRICS:
        a, b = st["totals"].get(k), led.get(k)
        if a is None or b is None:
            out[k] = {"statement": a, "ledger": b, "state": "UNKNOWN",
                      "why": ("not on the statement" if a is None else
                              "no ledger reconstruction (Etsy collects and remits "
                              "marketplace tax)" if k == "tax_cad" else
                              "the ledger has no reading for this month")}
            continue
        diff = round(a - b, 2)
        state = "MATCH" if abs(diff) <= TOLERANCE_CAD else "DIFFER"
        out[k] = {"statement": a, "ledger": b, "difference_cad": diff, "state": state}
        if state == "DIFFER":
            differ.append(k)
            X.open_exception(db, key=f"statement:{period}:{k}", kind="statement_mismatch",
                             severity="high", period=period, now=now,
                             summary=(f"Etsy statement {period} {k} {a} vs ledger {b} "
                                      f"(difference {diff}); the statement wins"),
                             evidence={"sha256": st["sha256"], "version": st["version"],
                                       "statement": a, "ledger": b})
    overall = ("DIFFER" if differ else
               "MATCH" if all(v["state"] == "MATCH" for v in out.values()) else "PARTIAL")
    return {"period": period, "state": overall, "metrics": out, "differ": differ,
            "statement_sha256": st["sha256"], "version": st["version"]}
