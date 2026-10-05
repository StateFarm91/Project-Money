"""Hermetic adversarial authority checks; no provider or production calls."""
import os, sys, tempfile
from pathlib import Path
from datetime import timedelta
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from brambleloop.core.db import Database
from brambleloop.core.models import AuditLog
from brambleloop.ops import activation_authority as a
from brambleloop.app.activation_authority_api import make_router
from fastapi import FastAPI
from fastapi.testclient import TestClient
TOKEN = 'local-test-operator-token-not-a-secret'
CONTENT = {'action': 'store.activate', 'listing_id': '123', 'slug': 'throw', 'version': '1', 'release': 'release-1', 'frames': [{'sha256': 'abc'}]}

def test_authority_lifecycle_and_adversarial_mutations():
    db = Database('sqlite:///' + str(Path(tempfile.mkdtemp()) / 'authority.db')); db.create_all()
    app = FastAPI(); app.include_router(make_router(db))
    def validate(ident):
        return a.validate(db, ident, slug='throw', version='1', listing_id='123', release='release-1')
    with patch.dict(os.environ, {'BRAMBLELOOP_OPS_TOKEN': TOKEN}), patch.object(a, 'snapshot', return_value=CONTENT):
        client = TestClient(app)
        body = {'slug': 'throw', 'version': '1', 'release': 'release-1', 'expected_digest': a.digest(CONTENT), 'reason': 'owner reviewed'}
        assert client.post('/api/owner/activation/approve', json=body).status_code == 403
        r = client.post('/api/owner/activation/approve', json=body, headers={'Authorization': f'Bearer {TOKEN}'})
        assert r.status_code == 200, r.text
        # Durable grant remains valid after reconstructing the database accessor.
        db = Database(str(db.engine.url))
        ident = r.json()['approval_id']; assert validate(ident) is None
        assert validate('L0-owner'); assert validate(999999)
        with patch.object(a, '_now', return_value=a._now() + timedelta(days=2)):
            assert 'expired' in validate(ident)
        for change in ({'action': 'other'}, {'listing_id': '999'}, {'release': 'other'}, {'frames': [{'sha256': 'changed'}]}):
            with patch.object(a, 'snapshot', return_value={**CONTENT, **change}):
                assert validate(ident)
        with patch.dict(os.environ, {'BRAMBLELOOP_OPS_TOKEN': TOKEN + 'rotated'}):
            assert validate(ident)
        assert client.post(f'/api/owner/activation/{ident}/revoke').status_code == 403
        assert client.post(f'/api/owner/activation/{ident}/revoke', headers={'Authorization': TOKEN}).status_code == 200
        assert 'revoked' in validate(ident)
        ident = client.post('/api/owner/activation/approve', json=body, headers={'Authorization': TOKEN}).json()['approval_id']
        with db.session() as s:
            row = s.get(AuditLog, ident); detail = dict(row.detail); detail['reason'] = 'tampered'; row.detail = detail
        assert validate(ident)

def test_actual_snapshot_and_worker_reject_magic_authority():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from tests import test_etsy_readback_observe as f
    db = f._db(); orig = f._gates_pass()
    try:
        with patch.dict(os.environ, {'BRAMBLELOOP_PUBLISH_AUTHORISED': '1', 'BRAMBLELOOP_OPS_TOKEN': TOKEN}):
            with f.FakeEtsy() as fake:
                product, lid = f._published(db, fake)
                content = a.snapshot(db, product['slug'], product['version'])
                ident = a.approve(db, authorization=TOKEN, slug=product['slug'], version=product['version'], expected_digest=a.digest(content), reason='reviewed')['approval_id']
                with f._Patched(fake):
                    job = f._run(db, 'store.activate', {'slug': product['slug'], 'version': product['version'], 'launch_authorisation': 'invented-owner-consent'}, agent='store_operator', phase=f.Phase.LIMITED_PRODUCTION)
                assert job.outputs['activated'] is False, job.outputs
                assert fake.listings[lid]['state'] == 'draft'
                # Revoke during execution after the first authority check. The second
                # boundary check must block the actual protected effect.
                original_spend = f.Registry.spend_today
                def revoke_during_budget(registry, agent):
                    a.revoke(db, authorization=TOKEN, approval_id=ident)
                    return original_spend(registry, agent)
                with f._Patched(fake), patch.object(f.Registry, 'spend_today', revoke_during_budget):
                    job = f._run(db, 'store.activate', {'slug': product['slug'], 'version': product['version'], 'owner_activation_approval_id': ident}, agent='store_operator', phase=f.Phase.LIMITED_PRODUCTION)
                assert job.outputs['activated'] is False, job.outputs
                assert fake.listings[lid]['state'] == 'draft'
                ident = a.approve(db, authorization=TOKEN, slug=product['slug'], version=product['version'], expected_digest=a.digest(content), reason='reviewed again')['approval_id']
                with db.session() as s:
                    listing = s.scalar(f.select(f.Listing).where(f.Listing.product_slug == product['slug'])); listing.title += ' mutated'
                assert a.validate(db, ident, slug=product['slug'], version=product['version'], listing_id=lid)
    finally:
        f._restore(orig)

if __name__ == '__main__':
    for fn in (test_authority_lifecycle_and_adversarial_mutations, test_actual_snapshot_and_worker_reject_magic_authority):
        fn(); print('PASS', fn.__name__)
    print('2 passed')
