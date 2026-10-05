"""Local evidence-basis controls: numeric budget comparators remain unchanged."""
import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT)]
from tests.test_operating_cost_basis import dbnew
from brambleloop.core.models import CostEntry,Listing
from brambleloop.finance import spend_report as sr,sustainability as su,unit_cost as uc
from datetime import datetime,timezone,timedelta


def test_variance_unknown_is_not_actual_and_still_detects_exposure_drift():
    db=dbnew()
    with db.session() as s:
        for _ in range(sr.DRIFT_MIN_CALLS):
            s.add(CostEntry(agent='a',kind='llm',purpose='legacy',amount_cad=2,estimated_cad=1))
    report=sr.estimate_drift(db);b=report['purposes_recorded']['legacy']
    assert b['actual_cad'] is None and b['ratio']==2 and b['under_estimated']
    assert b['comparison_basis']=='recorded_exposure_vs_reservation'
    assert report['degraded'] and 'legacy' not in report['purposes_measured']
    assert 'recorded CA$' in report['why']
    assert sr.what_it_bought(db)['cost_basis']['actual_cad'] is None
    json.dumps(report) # nullable values survive response serialization


def test_variance_measured_positive_and_unknown_offsets():
    rows=[CostEntry(kind='llm',purpose='p',amount_cad=1,estimated_cad=1,detail={'price_basis':'measured'})]
    b=sr.variance(rows)['by_purpose']['p']
    assert b['actual_cad']==1 and b['ratio']==1 and b['within_tolerance']
    rows += [CostEntry(kind='llm',purpose='p',amount_cad=x,estimated_cad=1) for x in (1,-1)]
    b=sr.variance(rows)['by_purpose']['p'];assert b['recorded_cad']==1 and b['actual_cad'] is None


def test_unit_cost_and_maintenance_preserve_unknown_and_measured_controls():
    for declared,expected in (({},'unknown'),({'price_basis':'assumed'},'modelled'),({'price_basis':'measured'},'measured')):
        db=dbnew();now=datetime.now(timezone.utc)
        with db.session() as s:
            s.add(Listing(product_slug='p',version='1',title='p',description='',price_cad=9,state='published',etsy_listing_id='1',created_at=now-timedelta(days=30)))
            s.add(CostEntry(agent='a',kind='llm',product_slug='p',amount_cad=2,detail=declared))
        unit=uc.unit_costs(db);maint=su.listing_maintenance_cost(db,now=now)
        assert unit['cost_basis']['reading']==maint['reading']==expected
        assert unit['operating_cost_cad']==maint['per_listing_month_cad']==2
        assert (maint['cost_basis']['actual_cad'] is not None)==(expected=='measured')
        assert su.split_costs(db)['cost_basis']['reading']==expected
        json.dumps(su.forecast(db))


if __name__=='__main__':
    tests=[v for k,v in list(globals().items()) if k.startswith('test_')]
    for test in tests:test();print('PASS',test.__name__)
    print(len(tests),'passed')
