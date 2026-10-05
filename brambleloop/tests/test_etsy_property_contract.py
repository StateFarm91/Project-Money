"""AB contract tests use only loopback FakeEtsy; no real provider calls."""
import os,sys
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT)]
from tests import test_etsy_readback_observe as f
from brambleloop.core.models import ListingSearchProfile
from brambleloop.runtime import etsy_ops
from brambleloop.ops import activation_authority as authority

def test_chosen_category_and_properties_reach_write_readback_and_approval():
    db=f._db();p=f._product(db)
    payload=etsy_ops.certified_payload(db,p['slug'],p['version'])
    assert payload.taxonomy_id==2114 and payload.properties[0]['property_id']==200
    with f.FakeEtsy() as fake:
        out,_=f._publish(db,fake,p)
        assert out['published'] is True,out
        lid=out['etsy_listing_id']
        assert int(fake.listings[lid]['taxonomy_id'])==2114
        assert fake.listings[lid]['properties'][0]['values']==['Beige']
        with patch.dict(os.environ,{'BRAMBLELOOP_OPS_TOKEN':'local-test-token-32-characters-long'}):
            content=authority.snapshot(db,p['slug'],p['version'])
            grant=authority.approve(db,authorization='local-test-token-32-characters-long',slug=p['slug'],version=p['version'],expected_digest=authority.digest(content),reason='review')
            with db.session() as s:
                row=s.scalar(f.select(ListingSearchProfile)); row.properties=[{'property_id':200,'value_ids':[2],'values':['Blue'],'scale_id':None}]
            assert authority.validate(db,grant['approval_id'],slug=p['slug'],version=p['version'],listing_id=lid)

def test_ignored_property_write_cannot_become_verified():
    db=f._db();p=f._product(db)
    with f.FakeEtsy() as fake:
        fake.ignore_property_writes=True
        out,_=f._publish(db,fake,p)
        assert out['published'] is False,out
        assert out['read_back_verified'] is False,out
        assert any('properties' in str(r) for r in out.get('problems', [])),out

def test_missing_search_profile_refuses_instead_of_default66():
    db=f._db();p=f._product(db)
    with db.session() as s:
        for row in s.scalars(f.select(ListingSearchProfile)):s.delete(row)
    try:etsy_ops.certified_payload(db,p['slug'],p['version'])
    except ValueError as e:assert 'UNKNOWN' in str(e)
    else:raise AssertionError('default taxonomy used')

def test_missing_property_blocks_activation_and_census_detects_drift():
    db=f._db();p=f._product(db);original=f._gates_pass()
    try:
        with f.FakeEtsy() as fake:
            out,_=f._publish(db,fake,p);lid=out['etsy_listing_id']
            fake.listings[lid]['properties']=[]
            client=f._client(fake,owner=True)
            full=etsy_ops.with_properties(client,lid,client.get_listing(lid))
            assert any('properties' in problem for problem in etsy_ops._field_drift(db,{'slug':p['slug'],'version':p['version']},full))
            with patch.dict(os.environ,{'BRAMBLELOOP_PUBLISH_AUTHORISED':'1'}),f._Patched(fake):
                job=f._run(db,'store.activate',{'slug':p['slug'],'version':p['version']},agent='store_operator',phase=f.Phase.LIMITED_PRODUCTION)
            assert job.outputs['activated'] is False,job.outputs
            assert any('properties' in r for r in job.outputs['reasons']),job.outputs
            assert fake.listings[lid]['state']=='draft'
    finally:f._restore(original)

if __name__=='__main__':
    funcs=[v for k,v in list(globals().items()) if k.startswith('test_')]
    for fn in funcs:fn();print('OK  ',fn.__name__)
    print(len(funcs),'passed')
