"""Final H no-redraw enforcement: local adversarial tests, no provider calls."""
import hashlib
import os
import sys
import tempfile
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from PIL import Image
from brambleloop.visual.compose import protect, verify
from brambleloop.visual.product_authority import structural_floor


def png(im):
    out=BytesIO();im.save(out,format='PNG');return out.getvalue()


def source():
    im=Image.new('RGBA',(8,8),(0,0,0,0));im.putpixel((3,3),(200,30,80,255));im.putpixel((4,3),(200,30,80,120));return png(im)


def test_every_nonzero_alpha_pixel_is_protected_without_resampling():
    src=source();background=png(Image.new('RGBA',(8,8),(230,230,230,255)))
    output,proof=protect(src,background)
    assert proof['status']=='PASS' and proof['protected_pixels']==2
    assert proof['certifies_construction'] is False and proof['certifies_photorealism'] is False
    changed=Image.open(BytesIO(output)).convert('RGBA');changed.putpixel((4,3),(200,30,80,121))
    assert verify(src,png(changed))['status']=='FAIL'
    assert verify(src,png(changed.resize((16,16))))['status']=='FAIL'


def test_empty_region_cannot_protect_nothing_and_pass():
    empty=png(Image.new('RGBA',(8,8),(0,0,0,0)))
    assert verify(empty,empty)['status']=='UNKNOWN'
    try:protect(empty,empty)
    except ValueError:pass
    else:raise AssertionError('empty authority accepted')


def test_preserved_authoritative_pixels_never_certify_unknown_construction():
    from brambleloop.core.artifacts import ArtifactStore
    src=source();output,_=protect(src,png(Image.new('RGBA',(8,8),(255,255,255,255))))
    with tempfile.TemporaryDirectory() as td, patch('brambleloop.core.artifacts.DEFAULT_DIR',td):
        store=ArtifactStore(); a=store.put('source',src,'image/png');b=store.put('output',output,'image/png')
        frame={'image':{'sha256':b.sha256},'motif':{'verdict':'match'},'protected_product':{'source_sha256':a.sha256,'output_sha256':b.sha256}}
        result=structural_floor(frame)
        assert result['status']=='UNKNOWN' and result['preservation']['status']=='PASS'
        frame['image']['sha256']='a'*64
        assert structural_floor(frame)['status']=='FAIL'


def test_tampered_product_pixels_fail_even_if_motif_and_realism_pass():
    from brambleloop.core.artifacts import ArtifactStore
    src=source(); changed=Image.open(BytesIO(src)).convert('RGBA');changed.putpixel((3,3),(0,0,0,255));output=png(changed)
    with tempfile.TemporaryDirectory() as td, patch('brambleloop.core.artifacts.DEFAULT_DIR',td):
        store=ArtifactStore();a=store.put('source',src,'image/png');b=store.put('output',output,'image/png')
        assert structural_floor({'image':{'sha256':b.sha256},'motif':{'verdict':'match'},'protected_product':{'source_sha256':a.sha256,'output_sha256':b.sha256}})['status']=='FAIL'


def test_legacy_usable_flag_cannot_export_or_reuse_unqualified_frame():
    from brambleloop.publish import listing_asset, owned_photography, model_photography
    frame={'made':True,'usable_as_listing_asset':True,'version':'1','shot':'fit','motif':{'verdict':'match'}}
    assert not listing_asset.usable(frame)
    assert not listing_asset.usable({'made':True,'usable_as_listing_asset':True,'frames':[frame]})
    with patch.object(owned_photography,'assets_for',return_value=[frame]):
        assert owned_photography.usable_asset(None,slug='x',version='1') is None
    with patch.object(model_photography,'_frames',return_value=[frame]):
        assert model_photography.usable_asset(None,slug='x',version='1') is None
    with patch.object(model_photography,'_filed_frames',return_value=[frame]):
        assert model_photography._passing_frame(None,SimpleNamespace(slug='x',version='1'),shot='fit') is None


def test_product_redraw_entry_points_refuse_before_any_provider_or_chart():
    from brambleloop.publish import owned_photography, model_photography
    def forbidden(*args,**kwargs):raise AssertionError('provider invoked')
    cir=SimpleNamespace(slug='blind-original')
    for module in (owned_photography,model_photography):
        result=module.make(None,cir,None,generator=forbidden)
        assert result['made'] is False and result['generated'] is False
        assert result['structural_truth']['status']=='UNKNOWN'


def test_motif_match_and_self_asserted_construction_pass_do_not_clear_parity():
    from brambleloop.visual.parity import assess, PRODUCT_TRUTH
    frame={'role':'hero','motif':{'verdict':'match'},'structural_truth':{'status':'PASS'},'deterministic':True}
    out=assess([frame])
    assert out['dimensions'][PRODUCT_TRUTH]['verdict']=='unjudged'


def test_star_proxy_keeps_historical_thresholds_and_refuses_unknown_envelope():
    import numpy as np
    from brambleloop.visual.stitch_identity import BARS,diagnose,draw_star_fabric,draw_hdc_fabric
    assert BARS['row_pair_scale']==0.35 and BARS['star_pitch_scale']==0.35
    good=np.asarray(draw_star_fabric(480,400,24,43).convert('L'))
    args=dict(family='star',star_px_expected=24,pair_px_expected=43,flat_region=True)
    result=diagnose(good,**args)
    assert result['status']=='PASS' and result['certifies_product'] is False
    bad=np.asarray(draw_hdc_fabric(480,400,12,21.5).convert('L'))
    assert diagnose(bad,**args)['status']!='PASS'
    assert diagnose(good,family='cable',flat_region=True)['status']=='UNKNOWN'
    assert diagnose(good,family='star',flat_region=True)['status']=='UNKNOWN'
    assert diagnose(good,family='star',star_px_expected=float('nan'),pair_px_expected=43,flat_region=True)['status']=='UNKNOWN'


def test_missing_optional_diagnostic_dependency_is_unknown():
    from unittest.mock import patch
    from brambleloop.visual import stitch_identity
    with patch.object(stitch_identity, 'gaussian_filter', None):
        result = stitch_identity.diagnose(None, family='star', flat_region=True)
    assert result['status'] == 'UNKNOWN' and result['certifies_product'] is False


def test_malformed_evidence_is_unknown_not_pass_or_crash():
    for frame in (None, {'motif':'match'}, {'protected_product':'PASS'}, {'protected_product':{'source_sha256':'x'},'image':'fake'}):
        assert structural_floor(frame)['status'] in ('UNKNOWN','FAIL')


if __name__=='__main__':
    failures=0;tests=[(n,f) for n,f in list(globals().items()) if n.startswith('test_') and callable(f)]
    for name,test in tests:
        try:test();print('PASS',name)
        except Exception as exc:failures+=1;print('FAIL',name,type(exc).__name__,str(exc))
    print(f'{len(tests)-failures}/{len(tests)} passing');sys.exit(bool(failures))
