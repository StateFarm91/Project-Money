"""Fail-closed product authority policy. Preservation is not construction proof.

Neither motif LLM matches nor preserved schematic pixels confer structural PASS. The one
qualified whole-product construction producer is the disclosed deterministic renderer
(`visual.disclosed_render`, owner ruling D-FB-7), and even its frames pass only when the
independent pixel verifier (`visual.render_verification`) passes on the exact image bytes the
frame binds by sha256, against the authoritative CIR for the product the frame claims. The
producer's manifest is a claim that selects what to verify; it is never evidence. A photo,
a generated frame or a model-bearing frame gets nothing from that branch.
"""
import hashlib

# Renderers whose frames may be verified for structural truth. A version not listed here is
# UNKNOWN however good its manifest looks: qualification is of a producer/verifier pair.
# 1.0.0 is withdrawn: its frames carried unverified annotation text (PT-05).
QUALIFIED_RENDERERS = frozenset({"disclosed-render/2.0.0"})


def redraw_refusal(slug):
    return {'made': False, 'generated': False, 'slug': slug,
            'usable_as_listing_asset': False, 'waiting_on': 'qualified_protected_product_renderer',
            'structural_truth': {'status': 'UNKNOWN'},
            'why': 'F-852: generative product redraw is prohibited; authoritative construction must be rendered and protected before presentation'}


def _not_a_render(frame):
    """Evidence that a frame is a photograph, a generation or a composite, any of which
    excludes it from the disclosed-render branch whatever manifest it carries."""
    return (frame.get('generated') is not False or bool(frame.get('carries_model'))
            or bool(frame.get('protected_product')) or bool(frame.get('provider'))
            or frame.get('photographic_realism') is not None
            or frame.get('kind') != 'disclosed_render')


def disclosed_render_floor(frame):
    """Structural truth for a disclosed deterministic render: the verifier on the bound bytes."""
    manifest = frame.get('disclosed_render')
    if not isinstance(manifest, dict) or manifest.get('kind') != 'disclosed_render':
        return {'status': 'UNKNOWN', 'why': 'invalid disclosed-render manifest'}
    if _not_a_render(frame):
        return {'status': 'UNKNOWN', 'why': 'a photo, generated or composited frame cannot use '
                                            'the disclosed-render branch'}
    if manifest.get('renderer_version') not in QUALIFIED_RENDERERS:
        return {'status': 'UNKNOWN', 'why': f"renderer {manifest.get('renderer_version')!r} is not qualified"}
    image = frame.get('image') or {}
    actual = image.get('sha256') if isinstance(image, dict) else None
    if not actual or actual != manifest.get('image_sha256'):
        return {'status': 'FAIL', 'why': 'manifest is not bound to this image'}
    slug, version = frame.get('slug'), frame.get('version')
    if slug != manifest.get('slug') or (version and version != manifest.get('version')):
        return {'status': 'FAIL', 'why': 'frame and manifest name different products'}
    view = manifest.get('view')
    from .disclosed_render import VIEWS
    if view not in VIEWS or frame.get('role') != VIEWS[view]['role']:
        return {'status': 'FAIL', 'why': f'frame role {frame.get("role")!r} does not match view {view!r}'}
    from .render_verification import authoritative_cir, verify
    cir = authoritative_cir(slug, manifest.get('version'))
    if cir is None:
        return {'status': 'UNKNOWN', 'why': f'no authoritative CIR for {slug}@{manifest.get("version")}'}
    if cir.fingerprint != manifest.get('cir_fingerprint'):
        return {'status': 'FAIL', 'why': 'manifest is bound to a different design than the certified CIR'}
    from ..core.artifacts import ArtifactStore
    try:
        data = ArtifactStore(frame.get('artifact_dir') or None).get(actual)
    except (OSError, ValueError, RuntimeError):
        return {'status': 'UNKNOWN', 'why': 'bound image bytes unavailable'}
    if hashlib.sha256(data).hexdigest() != actual:
        return {'status': 'FAIL', 'why': 'stored bytes do not hash to the bound digest'}
    result = verify(data, cir=cir, view=view)
    return {'status': result['status'],
            'why': ('independent pixel verification against the certified CIR: '
                    + (', '.join(result['failed'] + result['unknown']) or 'every check passed')),
            'verification': {k: result.get(k) for k in ('verifier_version', 'checks', 'failed',
                                                         'unknown', 'px_per_cm', 'measured',
                                                         'image_sha256', 'cir_fingerprint')}}


def structural_floor(frame):
    if not isinstance(frame, dict):
        return {'status': 'UNKNOWN', 'why': 'invalid frame evidence'}
    motif = frame.get('motif') or {}
    if not isinstance(motif, dict):
        return {'status': 'UNKNOWN', 'why': 'invalid motif evidence'}
    if motif.get('verdict') == 'mismatch':
        return {'status': 'FAIL', 'why': 'observed product mismatch'}
    if frame.get('disclosed_render') is not None and not frame.get('protected_product'):
        return disclosed_render_floor(frame)
    proof = frame.get('protected_product') or {}
    if not isinstance(proof, dict):
        return {'status': 'UNKNOWN', 'why': 'invalid protection evidence'}
    preservation = {'status': 'UNKNOWN', 'why': 'no bound protected-product evidence'}
    if proof:
        from ..core.artifacts import ArtifactStore
        from .compose import verify
        source, output = proof.get('source_sha256'), proof.get('output_sha256')
        image = frame.get('image') or {}
        actual = image.get('sha256') if isinstance(image, dict) else None
        if not actual or actual != output:
            return {'status': 'FAIL', 'why': 'preservation evidence is not bound to this image'}
        if not all(isinstance(s, str) and len(s) == 64 and all(c in '0123456789abcdef' for c in s) for s in (source, output)):
            return {'status': 'UNKNOWN', 'why': 'valid content-addressed source/output required'}
        try:
            store = ArtifactStore()
            preservation = verify(store.get(source), store.get(output))
        except (OSError, ValueError, RuntimeError) as exc:
            return {'status': 'UNKNOWN', 'why': 'protected-product bytes unavailable or invalid'}
        if preservation['status'] == 'FAIL':
            return {'status': 'FAIL', 'why': 'authoritative product pixels changed', 'preservation': preservation}
    return {'status': 'UNKNOWN', 'why': 'no qualified whole-product construction/gauge evidence producer; motif/proxy/pixel preservation alone is insufficient',
            'preservation': preservation}
