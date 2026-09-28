"""Exact product-region preservation, separate from construction and photo quality.

A source RGBA image's entire nonzero alpha support is protected. Callers cannot supply
an empty/subset mask to conceal changed stitches. No resampling, relighting or occlusion
of protected pixels is permitted by this conservative composition implementation.
"""
import hashlib
from io import BytesIO
from PIL import Image


def _rgba(data):
    return Image.open(BytesIO(data)).convert('RGBA')


def verify(source_png, output_png):
    source, output = _rgba(source_png), _rgba(output_png)
    if source.size != output.size:
        return {'status': 'FAIL', 'why': 'product canvas dimensions changed'}
    protected = changed = 0
    for before, after in zip(source.getdata(), output.getdata()):
        if before[3] > 0:
            protected += 1
            changed += before != after
    if not protected:
        return {'status': 'UNKNOWN', 'why': 'empty authoritative product region'}
    return {'status': 'FAIL' if changed else 'PASS', 'protected_pixels': protected,
            'changed_pixels': changed, 'source_sha256': hashlib.sha256(source_png).hexdigest(),
            'output_sha256': hashlib.sha256(output_png).hexdigest(),
            'certifies_construction': False, 'certifies_photorealism': False}


def protect(source_png, background_png):
    """Copy exact authoritative RGBA pixels over a same-size presentation canvas."""
    source, background = _rgba(source_png), _rgba(background_png)
    if source.size != background.size:
        raise ValueError('same-size canvas required; no product resampling')
    output = background.copy()
    output.putdata([p if p[3] else b for p, b in zip(source.getdata(), background.getdata())])
    buf = BytesIO(); output.save(buf, format='PNG'); result = buf.getvalue()
    verdict = verify(source_png, result)
    if verdict['status'] != 'PASS':
        raise ValueError(verdict.get('why', 'product region not preserved'))
    return result, verdict
