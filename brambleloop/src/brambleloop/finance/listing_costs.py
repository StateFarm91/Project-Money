"""Conservative listing-fee budget exposure, distinct from observed payment ledger fees."""
from contextlib import contextmanager
from datetime import datetime, timezone
from sqlalchemy import select, text, func
from ..core.models import CostEntry, LedgerEntry


@contextmanager
def locked(db):
    # Serialize these accounting writes; never hold this lock during network activity.
    with db.session() as session:
        dialect = session.bind.dialect.name
        if dialect == 'sqlite':
            session.execute(text('BEGIN IMMEDIATE'))
        elif dialect == 'postgresql':
            session.execute(text('SELECT pg_advisory_xact_lock(734543609)'))
        else:
            raise RuntimeError('listing fee accounting requires a supported lock dialect')
        yield session


def _exposure(session, listing_id):
    return next((r for r in session.scalars(select(CostEntry).where(
        CostEntry.kind == 'etsy_listing_fee'))
        if str((r.detail or {}).get('listing_id')) == str(listing_id)), None)


def pending(db, listing_id, amount):
    with db.session() as s:
        return 0.0 if _exposure(s, listing_id) is not None else amount


def reserve(db, *, listing_id, amount, agent, ceiling, job_id=None):
    """Durable exposure once per initial listing activation, not a claim of paid cash."""
    from ..agents.registry import BudgetExceeded
    with locked(db) as s:
        row = _exposure(s, listing_id)
        if row is not None:
            return row.id
        since = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        spent = float(s.scalar(select(func.sum(CostEntry.amount_cad)).where(
            CostEntry.agent == agent, CostEntry.at >= since)) or 0.0)
        if spent + amount > ceiling:
            raise BudgetExceeded('listing fee exposure exceeds unchanged daily ceiling')
        row = CostEntry(agent=agent, job_id=job_id, kind='etsy_listing_fee',
                        amount_cad=amount, estimated_cad=amount,
                        detail={'listing_id': str(listing_id), 'basis': 'modelled',
                                'state': 'reserved_unreconciled', 'usd': 0.20,
                                'conversion': 'assumed CAD/USD 1.37; not payment evidence'})
        s.add(row);s.flush();return row.id


def ingest_actual(db, entries):
    """Durably ingest only listing-reference fees, retaining original amount and FX basis."""
    from .reconcile import _to_cad
    applied=[]
    with locked(db) as s:
        for e in entries:
            if e['kind'] != 'listing_fee' or e['reference_type'].lower() != 'listing':
                continue
            external=str(e['entry_id']);ref=f"etsy_listing:{e['reference_id']}"
            if s.scalar(select(LedgerEntry.id).where(LedgerEntry.source == 'etsy_listing_ledger', LedgerEntry.external_id == external)):
                continue
            at=datetime.fromisoformat(e['at']) if e.get('at') else datetime.now(timezone.utc)
            amount,rate_measured=_to_cad(e['charge'],e['currency'],at.date())
            s.add(LedgerEntry(at=at,category='expense',expense_cad=amount,
                             source='etsy_listing_ledger',external_id=external,
                             evidence_ref=ref,currency=e['currency'],amount_original=e['charge'],
                             classification='listing_fee',basis='measured' if rate_measured else 'modelled',
                             reconciliation_state='matched_etsy_ledger',
                             description='Payment-account listing fee; conversion basis retained'))
            # A listing ID identifies a product, not an activation/renewal event.
            # Never rewrite an older reservation or infer that this fee settles it.
            # This mirror feeds budget readers; Books counts its LedgerEntry only.
            s.add(CostEntry(at=at, agent='store_operator', kind='etsy_listing_fee_actual',
                            amount_cad=amount, detail={
                                'listing_id': str(e['reference_id']),
                                'basis': 'measured' if rate_measured else 'modelled',
                                'ledger_source': 'etsy_listing_ledger',
                                'ledger_external_id': external,
                                'role': 'budget_mirror',
                                'agent_attribution': 'listing fees belong to store_operator',
                                'event_match': 'initial activation reservation unresolved'}))
            applied.append(external)
    return applied


def cost_basis(row):
    detail=row.detail or {}
    if row.kind == 'etsy_listing_fee':
        return 'modelled'
    if detail.get('basis') in ('measured','modelled','unknown'):
        return detail['basis']
    if detail.get('price_basis') == 'assumed':
        return 'modelled'
    if detail.get('price_basis') == 'measured':
        return 'measured'
    return 'unknown'
