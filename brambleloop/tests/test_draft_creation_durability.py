"""No-network remote-draft crash recovery, using real durable SQLite connections."""
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from sqlalchemy import select
from brambleloop.core.db import Database
from brambleloop.core.models import Listing, Incident, Phase
from brambleloop.integrations.etsy import EtsyClient, ListingPayload
from brambleloop.publish import draft_intent as intents
from brambleloop.runtime import pipeline

class Crash(RuntimeError):pass

class FakeRemote(EtsyClient):
    def __init__(self,db,fail):self.db=db;self.fail=fail;self.creates=0;self.uploads=0
    def refusal(self):return None
    def create_draft(self,payload):
        if self.fail=='before_create':raise Crash('before create request')
        self.creates+=1
        if self.fail=='after_create':raise Crash('remote created; response lost')
        return '777'
    def attach_file(self,listing_id,**kwargs):
        self.uploads+=1
        with self.db.session() as s:
            intent=s.get(intents.DraftIntent,intents.key_for('original','1'))
            listing=s.scalar(select(Listing))
            assert intent.remote_id==listing.etsy_listing_id=='777'
        raise Crash('upload interrupted after durable remote checkpoint')


def setup(path):
    db=Database('sqlite:///'+str(path),scratch=True);db.create_all()
    with db.session() as s:s.add(Listing(product_slug='original',version='1',title='Original pattern',description='Test fixture',release_hash='release-a'))
    return db


def ctx(db):return SimpleNamespace(db=db,job=SimpleNamespace(inputs={'slug':'original','version':'1','release':'release-a'}),phase=Phase.PRODUCTION,audit=lambda *a,**k:None)
def args():
    return dict(slug='original',version='1',release='release-a',payload=ListingPayload(title='Original pattern',description='Fixture',price=8,tags=[],materials=[]),docs={'US':SimpleNamespace(pdf_bytes=b'pdf'),'UK':SimpleNamespace(pdf_bytes=b'uk')},hash_check={'certified':{'US':'a'*64,'UK':'b'*64}},stored=SimpleNamespace(sha256='a'*64),stored_by_terminology={},listing_images={'images':[('image.png',b'fake')],'order':['hero'],'record_id':1})


def _crash_fixture_publish(*a, **kw):
    # Crash isolation only: fabricated hashes do not establish release approval.
    # Strict final missing-evidence refusals are tested in test_publish_execution_gate.
    with patch.object(pipeline, "_revalidate_publish_effect", return_value=None):
        return pipeline._publish_and_read_back(*a, **kw)


def crash_case(phase):
    with tempfile.TemporaryDirectory() as td:
        path=Path(td)/'state.db';db=setup(path);remote=FakeRemote(db,phase)
        try:
            try:_crash_fixture_publish(ctx(db),remote,**args())
            except Crash:pass
            else:raise AssertionError('failure injection not reached')
            expected=0 if phase=='before_create' else 1
            assert remote.creates==expected
            with db.session() as s:
                intent=s.get(intents.DraftIntent,intents.key_for('original','1'))
                assert intent.release=='release-a' and len(intent.content_digest)==64
                assert bool(intent.remote_id)==(phase=='after_checkpoint')
                assert s.scalar(select(Incident).where(Incident.halts_publication.is_(True))) is not None
            db.engine.dispose()
            # New Database object/pool is a process restart analogue; no in-memory lock.
            db=Database('sqlite:///'+str(path),scratch=True);remote.db=db
            try:_crash_fixture_publish(ctx(db),remote,**args())
            except intents.ReconciliationRequired:pass
            else:raise AssertionError('retry created another remote draft')
            assert remote.creates==expected
            if phase=='after_checkpoint':
                # Existing public handler must stop at the durable Listing.remote ID.
                # Capability gates are isolated fixtures here, not claimed production PASS.
                with patch.object(pipeline,'_listing_parity',return_value={'verdict':'pass','blocks_release':False}),patch.object(pipeline,'_release_gates',return_value={'blocks_release':False,'reasons':[]}),patch('brambleloop.integrations.etsy.EtsyClient',return_value=remote),patch('brambleloop.integrations.etsy.Credentials.from_env',return_value=None):
                    result=pipeline.handle_store_publish(ctx(db))
                assert result['published'] is False and result['etsy_listing_id']=='777'
                assert remote.creates==1
        finally:db.engine.dispose()


def test_before_create_failure_refuses_blind_retry_even_if_remote_did_nothing():crash_case('before_create')
def test_after_create_lost_response_blocks_retry_without_invented_remote_id():crash_case('after_create')
def test_after_checkpoint_upload_crash_retains_id_and_public_handler_never_recreates():crash_case('after_checkpoint')


def test_checkpoint_failure_after_id_return_prevents_upload_and_retry():
    with tempfile.TemporaryDirectory() as td:
        db=setup(Path(td)/'state.db');remote=FakeRemote(db,'after_checkpoint')
        try:
            with patch.object(intents,'checkpoint',side_effect=Crash('checkpoint failure')):
                try:_crash_fixture_publish(ctx(db),remote,**args())
                except Crash:pass
                else:raise AssertionError('checkpoint failure not reached')
            assert remote.creates==1 and remote.uploads==0
            try:_crash_fixture_publish(ctx(db),remote,**args())
            except intents.ReconciliationRequired:pass
            else:raise AssertionError('blind retry allowed')
            assert remote.creates==1
        finally:db.engine.dispose()


def test_concurrent_connections_allow_only_one_committed_creation_owner():
    with tempfile.TemporaryDirectory() as td:
        path=Path(td)/'race.db';db=setup(path);db.engine.dispose()
        barrier=threading.Barrier(2)
        def attempt():
            connection=Database('sqlite:///'+str(path),scratch=True)
            try:
                barrier.wait()
                try:return ('winner',intents.claim(connection,slug='original',version='1',release='release-a',content_digest='a'*64))
                except intents.ReconciliationRequired:return ('refused',None)
            finally:connection.engine.dispose()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:attempt(),range(2)))
        assert sorted(r[0] for r in results)==['refused','winner']
        db=Database('sqlite:///'+str(path),scratch=True)
        try:
            # A changed release never resets the per-version protection.
            try:intents.claim(db,slug='original',version='1',release='mutated-release',content_digest='b'*64)
            except intents.ReconciliationRequired:pass
            else:raise AssertionError('changed release bypassed durable intent')
            with db.session() as s:assert s.get(intents.DraftIntent,intents.key_for('original','1')).release=='release-a'
        finally:db.engine.dispose()

def test_hard_process_exit_leaves_creating_intent_that_blocks_new_process():
    import subprocess
    with tempfile.TemporaryDirectory() as td:
        path=Path(td)/"crash.db";marker=Path(td)/"remote-created.txt"
        # Child exits from inside fake create_draft: no Python finally/except executes.
        script="import sys,runpy;sys.path[:0]="+repr(sys.path)+";sys.argv="+repr([str(Path(__file__).resolve()),"--crash-child",str(path),str(marker)])+";runpy.run_path(sys.argv[0],run_name='__main__')"
        child=subprocess.run([sys.executable,"-c",script],capture_output=True,text=True,timeout=45)
        assert child.returncode==23, (child.returncode,child.stderr)
        assert marker.read_text()=="one remote create"
        db=Database("sqlite:///"+str(path),scratch=True)
        remote=FakeRemote(db,"after_checkpoint")
        try:
            with db.session() as s:assert s.get(intents.DraftIntent,intents.key_for("original","1")).state=="CREATING"
            try:_crash_fixture_publish(ctx(db),remote,**args())
            except intents.ReconciliationRequired:pass
            else:raise AssertionError("hard process crash authorized duplicate creation")
            assert remote.creates==0 and marker.read_text()=="one remote create"
        finally:db.engine.dispose()


if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--crash-child':
        import os
        db=setup(Path(sys.argv[2]))
        remote=FakeRemote(db,'after_create')
        def die(payload):
            Path(sys.argv[3]).write_text('one remote create')
            os._exit(23)
        remote.create_draft=die
        _crash_fixture_publish(ctx(db),remote,**args())
        raise AssertionError('child failed to exit')
    failures=0;tests=[(n,f) for n,f in list(globals().items()) if n.startswith('test_') and callable(f)]
    for name,test in tests:
        try:test();print('OK  ',name)
        except Exception as exc:failures+=1;print('FAIL',name,type(exc).__name__,str(exc))
    print(f'{len(tests)-failures}/{len(tests)} passing');sys.exit(bool(failures))
