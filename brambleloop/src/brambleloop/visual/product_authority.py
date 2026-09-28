"""Fail-closed product authority policy. Preservation is not construction proof.

No current production renderer has a qualified full-construction truth producer. Thus
neither motif LLM matches nor preserved schematic pixels confer structural PASS. This
module explicitly keeps that gate UNKNOWN until a reviewed producer is integrated.
"""


def redraw_refusal(slug):
    return {'made': False, 'generated': False, 'slug': slug,
            'usable_as_listing_asset': False, 'waiting_on': 'qualified_protected_product_renderer',
            'structural_truth': {'status': 'UNKNOWN'},
            'why': 'F-852: generative product redraw is prohibited; authoritative construction must be rendered and protected before presentation'}


def structural_floor(frame):
    if not isinstance(frame, dict):
        return {'status': 'UNKNOWN', 'why': 'invalid frame evidence'}
    motif = frame.get('motif') or {}
    if not isinstance(motif, dict):
        return {'status': 'UNKNOWN', 'why': 'invalid motif evidence'}
    if motif.get('verdict') == 'mismatch':
        return {'status': 'FAIL', 'why': 'observed product mismatch'}
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
