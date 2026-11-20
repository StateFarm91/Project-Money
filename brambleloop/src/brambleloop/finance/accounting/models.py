"""Accounting tables (F-903, F-904, F-910, F-912).

Amounts are stored as integer **micro-dollars** of CAD (1 CAD = 1_000_000). Model calls cost
fractions of a cent, and a journal that rounded each one to cents would neither balance
against `cost_entries` nor agree with the books; integers make "debits equal credits" an
exact statement rather than a tolerance.

Journal entries and postings are append-only. `before_update` / `before_delete` listeners
refuse any ORM change to them, and every entry is sealed into a hash chain
(`ledger.verify_chain`) so a raw-SQL edit is detected rather than believed. A correction is
a *reversing* entry plus a new entry, never an edit.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (JSON, BigInteger, Boolean, DateTime, ForeignKey, Integer, String,
                        Text, UniqueConstraint, event)
from sqlalchemy.orm import Mapped, mapped_column

from ...core.db import Base

MICRO = 1_000_000


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AcctJournalEntry(Base):
    __tablename__ = "acct_journal_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Idempotency key: `<rule>:<source_table>:<source_id>:v<n>` or `...:rev<n>`.
    entry_key: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    # The business date of the money event (accrual date). `period` is the accounting
    # period it is booked in -- the same month unless that month was locked, in which case
    # the entry is a late adjustment booked in the first open period.
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    period: Mapped[str] = mapped_column(String(7), index=True)
    source_period: Mapped[str] = mapped_column(String(7), default="")
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    rule: Mapped[str] = mapped_column(String(40), index=True)
    # `source_key` groups every version of the entries one source row produced.
    source_key: Mapped[str] = mapped_column(String(160), index=True)
    source_table: Mapped[str] = mapped_column(String(40), default="")
    source_id: Mapped[str] = mapped_column(String(80), default="")
    source_ref: Mapped[str] = mapped_column(String(200), default="")
    fingerprint: Mapped[str] = mapped_column(String(64), default="")
    kind: Mapped[str] = mapped_column(String(12), default="original")  # original|reversal
    reverses_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    memo: Mapped[str] = mapped_column(Text, default="")
    # Dimensions for profitability / attribution (F-906, F-907).
    product_slug: Mapped[str] = mapped_column(String(80), default="", index=True)
    release: Mapped[str] = mapped_column(String(120), default="")
    family: Mapped[str] = mapped_column(String(40), default="")
    channel: Mapped[str] = mapped_column(String(40), default="")
    department: Mapped[str] = mapped_column(String(40), default="")
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    prev_hash: Mapped[str] = mapped_column(String(64), default="")
    hash: Mapped[str] = mapped_column(String(64), default="")


class AcctPosting(Base):
    __tablename__ = "acct_postings"

    id: Mapped[int] = mapped_column(primary_key=True)
    entry_id: Mapped[int] = mapped_column(ForeignKey("acct_journal_entries.id"), index=True)
    line: Mapped[int] = mapped_column(Integer, default=0)
    account: Mapped[str] = mapped_column(String(8), index=True)
    debit_micros: Mapped[int] = mapped_column(BigInteger, default=0)
    credit_micros: Mapped[int] = mapped_column(BigInteger, default=0)
    # How the amount was obtained: measured | modelled | partial | unverified | unknown.
    basis: Mapped[str] = mapped_column(String(12), default="unknown")
    # The amount as the source stated it, before CAD normalisation.
    currency: Mapped[str] = mapped_column(String(3), default="CAD")
    amount_original: Mapped[float | None] = mapped_column(nullable=True)
    memo: Mapped[str] = mapped_column(String(200), default="")


class AcctPeriodLock(Base):
    __tablename__ = "acct_period_locks"

    id: Mapped[int] = mapped_column(primary_key=True)
    period: Mapped[str] = mapped_column(String(7), unique=True, index=True)
    locked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    locked_by: Mapped[str] = mapped_column(String(64), default="")
    trial_balance_hash: Mapped[str] = mapped_column(String(64), default="")
    checklist: Mapped[dict] = mapped_column(JSON, default=dict)


class AcctStatementLine(Base):
    """One line of an external statement: bank, Etsy payment account, processor.

    `state` is the reconciliation outcome: unmatched | matched | duplicate. A duplicate is
    kept (it is evidence) and never posted or matched.
    """

    __tablename__ = "acct_statement_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(24), index=True)   # bank|etsy_ledger|processor
    external_id: Mapped[str] = mapped_column(String(120))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    kind: Mapped[str] = mapped_column(String(20), index=True)     # payout|deposit|fee|refund|payment|charge|balance
    reference: Mapped[str] = mapped_column(String(120), default="", index=True)
    amount_micros: Mapped[int] = mapped_column(BigInteger, default=0)  # signed, CAD
    currency: Mapped[str] = mapped_column(String(3), default="CAD")
    amount_original: Mapped[float | None] = mapped_column(nullable=True)
    description: Mapped[str] = mapped_column(Text, default="")
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    state: Mapped[str] = mapped_column(String(12), default="unmatched", index=True)
    matched_to: Mapped[str] = mapped_column(String(200), default="")
    duplicate_of: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)

    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_acct_statement_line"),)


class AcctException(Base):
    """A difference or anomaly that needs a resolution, never a silent adjustment (F-904)."""

    __tablename__ = "acct_exceptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    severity: Mapped[str] = mapped_column(String(8), default="medium")
    period: Mapped[str] = mapped_column(String(7), default="", index=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution: Mapped[str] = mapped_column(Text, default="")


class AcctChallenge(Base):
    """Finance's verdict on a spend proposal (F-912 / F-919), kept as a durable record."""

    __tablename__ = "acct_challenges"

    id: Mapped[int] = mapped_column(primary_key=True)
    challenge_id: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    proposer: Mapped[str] = mapped_column(String(40), default="")
    amount_cad: Mapped[float] = mapped_column(default=0.0)
    verdict: Mapped[str] = mapped_column(String(12), index=True)  # cleared|blocked|escalated
    reasons: Mapped[list] = mapped_column(JSON, default=list)
    proposal: Mapped[dict] = mapped_column(JSON, default=dict)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)


TABLES = (AcctJournalEntry, AcctPosting, AcctPeriodLock, AcctStatementLine, AcctException,
          AcctChallenge)


class ImmutableLedgerError(RuntimeError):
    """An attempt to edit or delete a posted journal entry or posting."""


def _refuse(kind):
    def _listener(_mapper, _conn, target):
        raise ImmutableLedgerError(
            f"{type(target).__name__} {getattr(target, 'id', '?')}: posted accounting "
            f"records are immutable ({kind} refused). Correct with a reversing entry.")
    return _listener


for _cls in (AcctJournalEntry, AcctPosting, AcctPeriodLock):
    event.listen(_cls, "before_update", _refuse("update"))
    event.listen(_cls, "before_delete", _refuse("delete"))
