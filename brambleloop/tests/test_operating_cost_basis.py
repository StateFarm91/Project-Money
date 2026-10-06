"""Hermetic operating-cost basis and listing exposure tests."""
import sys,os,tempfile
from pathlib import Path
from unittest.mock import patch
from datetime import datetime,timezone,timedelta
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT)]
from brambleloop.core.db import Database
from brambleloop.core.models import CostEntry,LedgerEntry
from brambleloop.finance import listing_costs as lc,reconcile
from brambleloop.finance.books import Books,ProfitAndLoss
from sqlalchemy import select

def dbnew():
    db=Database('sqlite:///'+str(Path(tempfile.mkdtemp())/'cost.db'));db.create_all();return db

def test_reservation_retries_restart_and_reconciliation_do_not_doublecount():
    db=dbnew()
    first=lc.reserve(db,listing_id='55',amount=.27,agent='store_operator',ceiling=1)
    db=Database(str(db.engine.url))
    assert lc.reserve(db,listing_id='55',amount=.27,agent='store_operator',ceiling=1)==first
    pl=Books(db).profit_and_loss()
    assert pl.operating_costs_cad==.27 and pl.operating_costs_by_basis=={'modelled':.27}
    entry={'entry_id':7,'ledger_type':'listing','reference_type':'listing','reference_id':'55',
           'amount':{'amount':-31,'divisor':100,'currency_code':'CAD'},'created_timestamp':int(datetime.now(timezone.utc).timestamp())}
    reconcile.apply(db,[entry]);reconcile.apply(db,[entry])
    with db.session() as s:
        assert len(list(s.scalars(select(LedgerEntry))))==1
        assert len(list(s.scalars(select(CostEntry))))==2
        assert s.get(CostEntry,first).amount_cad==.27
    pl=Books(db).profit_and_loss()
    assert pl.operating_costs_cad==.58,pl.to_dict()
    assert pl.unresolved_listing_exposure_cad==.27
    # rc1-ORD2: read through the unverified ledger mapping, the charged fee is not measured.
    assert pl.operating_costs_by_basis=={'unknown':.31,'modelled':.27},pl.operating_costs_by_basis
    tok='local-owner-test-token-32characters'
    with patch.dict(os.environ,{'BRAMBLELOOP_OPS_TOKEN':tok}):
        reconcile.record_mapping_verification(db,authorization=tok,by='owner',evidence='fixture')
        pl=Books(db).profit_and_loss()
        assert pl.operating_costs_by_basis=={'measured':.31,'modelled':.27}
    later={**entry,'entry_id':8,'amount':{'amount':-25,'divisor':100,'currency_code':'CAD'}}
    reconcile.apply(db,[entry,later]);reconcile.apply(db,[entry,later])
    assert Books(db).profit_and_loss().operating_costs_cad==.83
    with db.session() as s:
        assert s.get(CostEntry,first).amount_cad==.27
        assert len(list(s.scalars(select(CostEntry))))==3


def test_unknown_legacy_and_assumed_provider_costs_cannot_be_cash():
    db=dbnew()
    with db.session() as s:
        s.add(CostEntry(agent='a',kind='llm',amount_cad=1,detail={'price_basis':'assumed'}))
        s.add(CostEntry(agent='a',kind='hosting',amount_cad=2))
    pl=Books(db).profit_and_loss();pl.sales_reading='measured'
    assert pl.operating_costs_by_basis=={'modelled':1,'unknown':2}
    assert pl.to_dict()['all_figures_observed'] is False
    assert pl.cash_cad is None
    observed=ProfitAndLoss(period_start='x',period_end='x',cost_by_kind={'api':2},operating_costs_by_basis={'measured':2})
    assert observed.to_dict()['all_figures_observed'] is True

def test_inactive_activation_retains_only_modelled_exposure():
    from tests import test_etsy_readback_observe as f
    from brambleloop.ops import activation_authority as authority
    db=f._db();orig=f._gates_pass()
    try:
        with f.FakeEtsy() as fake,patch.dict(os.environ,{'BRAMBLELOOP_PUBLISH_AUTHORISED':'1','BRAMBLELOOP_OPS_TOKEN':'local-owner-test-token-32characters'}):
            p,lid=f._published(db,fake)
            content=authority.snapshot(db,p['slug'],p['version'])
            approval=authority.approve(db,authorization='local-owner-test-token-32characters',slug=p['slug'],version=p['version'],expected_digest=authority.digest(content),reason='review')
            def inactive(client,listing_id,**kw):
                with db.session() as s:
                    assert len(list(s.scalars(select(CostEntry).where(CostEntry.kind=='etsy_listing_fee'))))==1
                return {'state':'inactive'}
            with f._Patched(fake),patch.object(f.EtsyClient,'activate',inactive):
                job=f._run(db,'store.activate',{'slug':p['slug'],'version':p['version'],'owner_activation_approval_id':approval['approval_id']},agent='store_operator',phase=f.Phase.LIMITED_PRODUCTION)
            assert job.outputs['activated'] is False,job.outputs
            with db.session() as s:
                rows=list(s.scalars(select(CostEntry).where(CostEntry.kind=='etsy_listing_fee')))
                assert len(rows)==1 and rows[0].detail['basis']=='modelled'
            pl=Books(db).profit_and_loss();pl.sales_reading='measured'
            assert pl.cash_cad is None and not pl.to_dict()['all_figures_observed']
    finally:f._restore(orig)

def test_budget_ceiling_unchanged_and_unobserved_offsets_cannot_fake_observation():
    from brambleloop.agents.registry import BudgetExceeded
    db=dbnew()
    try:lc.reserve(db,listing_id='denied',amount=.27,agent='store_operator',ceiling=.20)
    except BudgetExceeded:pass
    else:raise AssertionError('ceiling bypass')
    with db.session() as s:
        assert not list(s.scalars(select(CostEntry)))
        s.add(CostEntry(agent='a',kind='api',amount_cad=1,detail={'basis':'unknown'}))
        s.add(CostEntry(agent='a',kind='api',amount_cad=-1,detail={'basis':'unknown'}))
    pl=Books(db).profit_and_loss();pl.sales_reading='measured'
    assert pl.operating_costs_cad==0 and pl.cash_cad is None

def test_concurrent_sqlite_reservation_same_listing_has_one_row():
    from concurrent.futures import ThreadPoolExecutor
    db=dbnew();url=str(db.engine.url)
    def claim(_):
        other=Database(url)
        return lc.reserve(other,listing_id='concurrent',amount=.27,agent='store_operator',ceiling=1)
    with ThreadPoolExecutor(max_workers=2) as pool:
        ids=list(pool.map(claim,range(2)))
    assert ids[0]==ids[1]
    with db.session() as s:assert len(list(s.scalars(select(CostEntry))))==1

def test_revoke_or_mutate_during_reservation_refuses_external_effect():
    from tests import test_etsy_readback_observe as f
    from brambleloop.ops import activation_authority as authority
    for mode in ('revoke','mutate','grant'):
        db=f._db();original=f._gates_pass();calls=[]
        try:
            with f.FakeEtsy() as fake,patch.dict(os.environ,{'BRAMBLELOOP_PUBLISH_AUTHORISED':'1','BRAMBLELOOP_OPS_TOKEN':'local-owner-test-token-32characters'}):
                p,lid=f._published(db,fake)
                content=authority.snapshot(db,p['slug'],p['version'])
                approval=authority.approve(db,authorization='local-owner-test-token-32characters',slug=p['slug'],version=p['version'],expected_digest=authority.digest(content),reason='review')
                original_reserve=lc.reserve
                def reserve_and_change(*args,**kwargs):
                    result=original_reserve(*args,**kwargs)
                    if mode=='revoke':
                        authority.revoke(db,authorization='local-owner-test-token-32characters',approval_id=approval['approval_id'])
                    elif mode=='grant':
                        os.environ['BRAMBLELOOP_PUBLISH_AUTHORISED']='0'
                    else:
                        with db.session() as session:
                            row=session.scalar(select(f.Listing));row.title+=' changed'
                    return result
                def forbidden(*args,**kwargs):
                    calls.append(True);raise AssertionError('external activation must not run')
                with f._Patched(fake),patch.object(lc,'reserve',reserve_and_change),patch.object(f.EtsyClient,'activate',forbidden):
                    job=f._run(db,'store.activate',{'slug':p['slug'],'version':p['version'],'owner_activation_approval_id':approval['approval_id']},agent='store_operator',phase=f.Phase.LIMITED_PRODUCTION)
                assert job.outputs['activated'] is False and not calls,job.outputs
                with db.session() as session:
                    assert len(list(session.scalars(select(CostEntry).where(CostEntry.kind=='etsy_listing_fee'))))==1
        finally:f._restore(original)

def test_later_renewal_cannot_rewrite_old_period_or_escape_today_budget():
    from brambleloop.agents.registry import BudgetExceeded
    db=dbnew();now=datetime.now(timezone.utc);old=now-timedelta(days=40)
    first=lc.reserve(db,listing_id='55',amount=.27,agent='store_operator',ceiling=1)
    with db.session() as s:s.get(CostEntry,first).at=old
    before=Books(db).profit_and_loss(since=old-timedelta(days=1),until=old+timedelta(days=1))
    e={'kind':'listing_fee','reference_type':'listing','reference_id':'55',
       'entry_id':'later-renewal','at':now.isoformat(),'charge':1.50,'currency':'CAD'}
    # rc1-ORD2: a listing fee is `measured` only under the owner's sealed mapping
    # verification; this test is about periods and budgets, so it records one first.
    from brambleloop.finance import reconcile
    tok='local-owner-test-token-32characters'
    with patch.dict(os.environ,{'BRAMBLELOOP_OPS_TOKEN':tok}):
        reconcile.record_mapping_verification(db,authorization=tok,by='owner',evidence='fixture')
        lc.ingest_actual(db,[e]);lc.ingest_actual(Database(str(db.engine.url)),[e])
        after=Books(db).profit_and_loss(since=old-timedelta(days=1),until=old+timedelta(days=1))
        today=Books(db).profit_and_loss(since=now-timedelta(hours=1))
    assert before.operating_costs_cad==after.operating_costs_cad==.27
    assert today.operating_costs_cad==1.50 and today.operating_costs_by_basis=={'measured':1.50}
    try:lc.reserve(db,listing_id='66',amount=.27,agent='store_operator',ceiling=1)
    except BudgetExceeded:pass
    else:raise AssertionError('actual renewal absent from current daily budget')
    with db.session() as s:
        assert len(list(s.scalars(select(CostEntry))))==2
        assert s.get(CostEntry,first).amount_cad==.27
    # Actual fees without any initial reservation still consume the store budget.
    other=dbnew();lc.ingest_actual(other,[e])
    try:lc.reserve(other,listing_id='66',amount=.27,agent='store_operator',ceiling=1)
    except BudgetExceeded:pass
    else:raise AssertionError('unreserved actual fee absent from daily budget')


def test_unknown_fee_offsets_remain_unobserved():
    db=dbnew()
    with db.session() as s:
        for amount in (1,-1):s.add(LedgerEntry(category='expense',fees_cad=amount,fees_basis='unknown'))
    pl=Books(db).profit_and_loss();pl.sales_reading='measured'
    assert pl.platform_fees_cad==0 and pl.unobserved_fee_rows==2
    assert pl.cash_cad is None and not pl.all_observed

if __name__=='__main__':
    funcs=[v for k,v in list(globals().items()) if k.startswith('test_')]
    for fn in funcs:fn();print('OK  ',fn.__name__)
    print(len(funcs),'passed')
