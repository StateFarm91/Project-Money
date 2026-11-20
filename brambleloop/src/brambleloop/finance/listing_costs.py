"""Conservative listing-fee budget exposure, distinct from observed payment ledger fees."""
from contextlib import contextmanager
from datetime import datetime, timezone
from sqlalchemy import select, text, func
from ..core.models import CostEntry, LedgerEntry
from ..core import fx as _fx


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


# ENG-APPROVALS (owner directive D-OWNER-STANDING-INTERNAL, 2026-11-19): "I approve the opening
# catalogue's Etsy listing fees up to CA$6". A standing spend authorisation for listing /
# activation fees ONLY, bounded and cumulative: every reservation counts against it (and an
# observed listing fee for a listing that was never reserved counts too), it never resets, and
# it raises no other ceiling -- the agent's daily ceiling is still checked first, unchanged.
# It authorises no publication: store.activate still needs its gates, the Etsy grant path and
# Stage A or the per-product approval before it ever reaches `reserve`.
OPENING_CATALOGUE_FEE_BUDGET_CAD = 6.00
FEE_KINDS = ('etsy_listing_fee', 'etsy_listing_fee_actual')
_EPS = 1e-9


def _opening_used(session) -> tuple[float, int]:
    """(CA$ counted against the opening-catalogue budget, reservations). Reservations count in
    full; an observed fee counts only for a listing with no reservation (never twice)."""
    rows = list(session.execute(select(CostEntry.kind, CostEntry.amount_cad, CostEntry.detail)
                                .where(CostEntry.kind.in_(FEE_KINDS))))
    reserved = {str((d or {}).get('listing_id')) for k, _a, d in rows
                if k == 'etsy_listing_fee'}
    used = sum(float(a or 0.0) for k, a, _d in rows if k == 'etsy_listing_fee')
    used += sum(max(0.0, float(a or 0.0)) for k, a, d in rows
                if k == 'etsy_listing_fee_actual'
                and str((d or {}).get('listing_id')) not in reserved)
    return round(used, 6), len(reserved)


def opening_budget(db) -> dict:
    """The opening-catalogue listing-fee budget: total, used (reservations count), remaining."""
    with db.session() as s:
        used, n = _opening_used(s)
    return {'budget_cad': OPENING_CATALOGUE_FEE_BUDGET_CAD, 'used_cad': round(used, 2),
            'remaining_cad': round(max(0.0, OPENING_CATALOGUE_FEE_BUDGET_CAD - used), 2),
            'reservations': n, 'authority': 'D-OWNER-STANDING-INTERNAL',
            'covers': 'Etsy listing/activation fees only; authorises no publication',
            'cumulative': True}


def opening_budget_refusal(db, listing_id, amount) -> str | None:
    """Why a fee of `amount` for `listing_id` would exceed the opening budget, or None. A
    listing already reserved costs nothing more (the reservation is once per listing)."""
    with db.session() as s:
        if _exposure(s, listing_id) is not None:
            return None
        used, _n = _opening_used(s)
    return _budget_refusal(used, amount)


#: ENG-ETSY-PUBLISH: Etsy's listing fee is US$0.20 per listing. A single reservation above
#: that figure at the assumed rate (plus one cent of rounding) is refused, so a changed fee
#: schedule or a wrong amount can never spend the opening budget faster than one fee per
#: listing. At the assumed rate this caps the CA$6 budget at about 21 listings.
PER_LISTING_FEE_USD = 0.20


def per_listing_cap_cad() -> float:
    return round(PER_LISTING_FEE_USD / _fx.ASSUMED_USD_PER_CAD + 0.01, 4)


def _budget_refusal(used: float, amount: float) -> str | None:
    if float(amount) < 0:
        return 'a negative listing fee is not a reservation'
    if float(amount) > per_listing_cap_cad() + _EPS:
        return (f'a listing fee of CA${float(amount):.2f} is above the per-listing cap of '
                f'CA${per_listing_cap_cad():.2f} (US${PER_LISTING_FEE_USD:.2f} at the assumed '
                f'rate): refused rather than spending the opening budget faster')
    if used + float(amount) > OPENING_CATALOGUE_FEE_BUDGET_CAD + _EPS:
        return (f'the opening-catalogue listing-fee budget is CA$'
                f'{OPENING_CATALOGUE_FEE_BUDGET_CAD:.2f} in total (D-OWNER-STANDING-INTERNAL): '
                f'CA${used:.2f} already reserved + CA${float(amount):.2f} would exceed it')
    return None


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
        # Under the same lock as the write: two activations cannot both find the last room.
        over = _budget_refusal(_opening_used(s)[0], amount)
        if over:
            raise BudgetExceeded(over)
        row = CostEntry(agent=agent, job_id=job_id, kind='etsy_listing_fee',
                        amount_cad=amount, estimated_cad=amount,
                        detail={'listing_id': str(listing_id), 'basis': 'modelled',
                                'state': 'reserved_unreconciled', 'usd': 0.20,
                                'authority': 'D-OWNER-STANDING-INTERNAL',
                                'budget': 'opening_catalogue_listing_fees',
                                'conversion': f'assumed {_fx.ASSUMED_USD_PER_CAD:.4f} USD/CAD (core.fx); '
                                              'not payment evidence'})
        s.add(row);s.flush();return row.id


def ingest_actual(db, entries, *, verified=None):
    """Durably ingest only listing-reference fees, retaining original amount and FX basis.

    rc1-ORD2: a listing fee is read through the same unverified ledger type/unit mapping as
    the order fees, so it is `measured` only while the owner's sealed mapping verification
    holds (`reconcile.mapping_verified`); until then its basis is `unverified` (the ledger
    column's 12-character form of `unverified_mapping`) and `reconcile.sync_fee_bases` moves
    it either way when the verification changes. An assumed FX rate keeps it `modelled`.
    """
    from .reconcile import UNVERIFIED, UNVERIFIED_MAPPING, _to_cad, mapping_verified
    if verified is None:
        verified = mapping_verified(db)  # read before the write lock is taken
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
            basis=('modelled' if not rate_measured else 'measured' if verified else UNVERIFIED)
            cost_basis_=('modelled' if not rate_measured else
                         'measured' if verified else UNVERIFIED_MAPPING)
            s.add(LedgerEntry(at=at,category='expense',expense_cad=amount,
                             source='etsy_listing_ledger',external_id=external,
                             evidence_ref=ref,currency=e['currency'],amount_original=e['charge'],
                             classification='listing_fee',basis=basis,
                             reconciliation_state='matched_etsy_ledger',
                             description='Payment-account listing fee; conversion basis retained'))
            # A listing ID identifies a product, not an activation/renewal event.
            # Never rewrite an older reservation or infer that this fee settles it.
            # This mirror feeds budget readers; Books counts its LedgerEntry only.
            s.add(CostEntry(at=at, agent='store_operator', kind='etsy_listing_fee_actual',
                            amount_cad=amount, detail={
                                'listing_id': str(e['reference_id']),
                                'basis': cost_basis_,
                                'mapping': 'owner_verified' if verified else UNVERIFIED_MAPPING,
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


def basis_summary(pairs):
    """Summarize (amount, basis) without net-zero rows hiding missing evidence."""
    totals={};counts={}
    for amount,basis in pairs:
        basis=basis if basis in ('measured','modelled') else 'unknown'
        totals[basis]=totals.get(basis,0.0)+float(amount)
        counts[basis]=counts.get(basis,0)+1
    reading=next(iter(counts)) if len(counts)==1 else ('mixed' if counts else 'UNMEASURED')
    return {'reading':reading,'by_basis_cad':{k:round(v,6) for k,v in totals.items()},
            'rows_by_basis':counts,
            'actual_cad':round(sum(totals.values()),6) if reading=='measured' else None,
            'amount_semantics':'recorded exposure; modelled/unknown amounts are not observed charges'}
