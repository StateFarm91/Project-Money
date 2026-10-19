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


# --------------------------------------------------------------------------------------------
# Alpha-edge restoration for a masked background edit (W4-VISREF).
#
# `protect`/`verify` above are unchanged: an exact copy of every nonzero-alpha pixel, alpha
# included. That output keeps partial alpha at a soft edge, and Etsy renders transparency
# black (research/final_build/w3/ETSY_REQUIREMENTS.md, "no transparency"), so it cannot be a
# listing master once the matte has yarn fuzz. This is a separately named mode with its own
# verifier, for one workflow: a provider regenerates the background around a qualified
# product reference, and the product layer is then restored deterministically.
#
# Assumptions, each enforced below:
#   * masked generation does NOT preserve pixels, whatever the provider's docs say; the
#     product layer is restored from the source after generation, as the last step;
#   * the alpha matte is authoritative: alpha 255 is product, 0 is not (including the true
#     holes of crochet lace), and 1..254 is a soft edge (fuzz, fringe) composited by the
#     integer alpha equation below, so a soft pixel is checked exactly, not "approximately";
#   * the provider image must already be the source's size; nothing is resampled;
#   * the export is opaque RGB, and its exact sha256 is what the certificate binds;
#   * none of this certifies construction or photorealism. Those need an independently
#     qualified reference and independent Product Truth (`lifestyle_evidence`).
# --------------------------------------------------------------------------------------------
import json as _json

RESTORE_VERSION = 'alpha-edge-restore/1'
CERT_VERSION = 'lifestyle-composite-cert/1'

# Provider mask polarity, from each provider's official API reference (read 2026-10-19):
# Ideogram 4.5 Precise Edit: "Black marks the area to edit and white the area to keep."
# Recraft generateBackground: "Pure white pixels (255) are regenerated and pure black
# pixels (0) stay unchanged."
MASK_POLARITY = {
    'ideogram-4.5-precise-edit': {'edit': 0, 'keep': 255},
    'recraft-v3-generate-background': {'edit': 255, 'keep': 0},
}


class RestoreRefused(ValueError):
    """The inputs cannot be restored truthfully (size, mode, polarity, empty matte)."""


def _png_bytes(img):
    buf = BytesIO(); img.save(buf, format='PNG'); return buf.getvalue()


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def blend(src, a, gen):
    """The one alpha equation, integer and deterministic: round(a*src + (255-a)*gen) / 255."""
    return (a * src + (255 - a) * gen + 127) // 255


def edit_mask(source_png, provider):
    """The provider's edit mask: every pixel with alpha > 0 is KEEP, every alpha-0 pixel
    (outside the product and inside its true holes) is EDIT, in that provider's polarity."""
    if provider not in MASK_POLARITY:
        raise RestoreRefused(f'{provider!r} has no documented mask polarity: {sorted(MASK_POLARITY)}')
    pol = MASK_POLARITY[provider]
    alpha = _rgba(source_png).getchannel('A')
    mask = alpha.point(lambda a: pol['keep'] if a else pol['edit'])
    values = set(mask.getdata())
    if len(values) != 2:
        raise RestoreRefused('a mask must contain both an edit and a keep region')
    return _png_bytes(mask.convert('L'))


def check_mask(mask_png, source_png, provider):
    """PASS only when the mask is the source's size, strictly binary, has both regions, and
    keeps exactly the matte's nonzero-alpha pixels in this provider's polarity."""
    if provider not in MASK_POLARITY:
        return {'status': 'UNKNOWN', 'why': f'no documented polarity for {provider!r}'}
    pol = MASK_POLARITY[provider]
    mask = Image.open(BytesIO(mask_png))
    source = _rgba(source_png)
    if mask.size != source.size:
        return {'status': 'FAIL', 'why': f'mask {mask.size} is not the source size {source.size}'}
    values = list(mask.convert('L').getdata())
    if set(values) - {0, 255}:
        return {'status': 'FAIL', 'why': 'mask is not strictly binary; a provider rounds grey'}
    if len(set(values)) != 2:
        return {'status': 'FAIL', 'why': 'mask has no edit region or no keep region'}
    wrong = sum(1 for v, a in zip(values, source.getchannel('A').getdata())
                if v != (pol['keep'] if a else pol['edit']))
    if wrong:
        return {'status': 'FAIL', 'why': f'{wrong} mask pixel(s) disagree with the matte in '
                                         f'{provider} polarity (inverted or shifted mask)'}
    return {'status': 'PASS', 'provider': provider, 'mask_sha256': _sha(mask_png)}


def restore(source_png, generated_png):
    """Restore the product layer over a provider's output, as the final rendering step.

    Opaque product pixels are copied exactly; soft-edge pixels are the alpha equation of the
    source over the *generated* pixel; alpha-0 pixels (background and true holes) are the
    generated pixel. The export is opaque RGB PNG. No resampling: a size change refuses."""
    source = _rgba(source_png)
    generated = Image.open(BytesIO(generated_png)).convert('RGB')
    if source.size != generated.size:
        raise RestoreRefused(f'provider output {generated.size} is not the source size '
                             f'{source.size}; restoration never resamples the product')
    if not any(a for a in source.getchannel('A').getdata()):
        raise RestoreRefused('empty matte: there is no product layer to restore')
    out = Image.new('RGB', source.size)
    out.putdata([
        (s[0], s[1], s[2]) if s[3] == 255 else
        g if s[3] == 0 else
        (blend(s[0], s[3], g[0]), blend(s[1], s[3], g[1]), blend(s[2], s[3], g[2]))
        for s, g in zip(source.getdata(), generated.getdata())])
    result = _png_bytes(out)
    verdict = verify_restored(source_png, generated_png, result)
    if verdict['status'] != 'PASS':
        raise RestoreRefused(verdict['why'])
    return result, verdict


def verify_restored(source_png, generated_png, output_png):
    """Independent re-check of a restored export against the matte equation, pixel by pixel.
    It does not trust `restore`: it decodes the exported bytes and recomputes every pixel."""
    source = _rgba(source_png)
    out = Image.open(BytesIO(output_png))
    if out.mode not in ('RGB',):
        return {'status': 'FAIL', 'why': f'export mode {out.mode} is not opaque RGB; Etsy '
                                         f'renders transparency black'}
    generated = Image.open(BytesIO(generated_png)).convert('RGB')
    if not (source.size == out.size == generated.size):
        return {'status': 'FAIL', 'why': 'source, provider output and export sizes differ'}
    core = soft = holes_or_bg = core_changed = soft_changed = bg_changed = 0
    for s, g, o in zip(source.getdata(), generated.getdata(), out.getdata()):
        a = s[3]
        if a == 255:
            core += 1; core_changed += o != s[:3]
        elif a == 0:
            holes_or_bg += 1; bg_changed += o != g
        else:
            soft += 1
            soft_changed += o != tuple(blend(s[i], a, g[i]) for i in range(3))
    if not core and not soft:
        return {'status': 'UNKNOWN', 'why': 'empty authoritative product region'}
    failed = core_changed or soft_changed or bg_changed
    return {'status': 'FAIL' if failed else 'PASS',
            'why': ('every opaque product pixel is identical to the source, every soft-edge '
                    'pixel equals the alpha equation over the provider pixel'
                    if not failed else
                    f'{core_changed} opaque product pixel(s), {soft_changed} soft-edge '
                    f'pixel(s) and {bg_changed} background pixel(s) differ from the restoration'),
            'version': RESTORE_VERSION, 'core_pixels': core, 'soft_pixels': soft,
            'background_pixels': holes_or_bg, 'core_changed': core_changed,
            'soft_changed': soft_changed, 'background_changed': bg_changed,
            'source_sha256': _sha(source_png), 'generated_sha256': _sha(generated_png),
            'output_sha256': _sha(output_png),
            'certifies_construction': False, 'certifies_photorealism': False}


def matte_components(source_png, *, min_pixels=1):
    """Pieces in the matte: 8-connected regions of alpha > 0 (holes inside a piece do not
    split it). Deterministic; used to hold a composite to the CIR's piece count."""
    img = _rgba(source_png)
    w, h = img.size
    alpha = list(img.getchannel('A').getdata())
    seen = bytearray(w * h)
    sizes = []
    for start in range(w * h):
        if not alpha[start] or seen[start]:
            continue
        seen[start] = 1; stack = [start]; n = 0
        while stack:
            p = stack.pop(); n += 1
            x, y = p % w, p // w
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < w and 0 <= ny < h:
                        q = ny * w + nx
                        if alpha[q] and not seen[q]:
                            seen[q] = 1; stack.append(q)
        sizes.append(n)
    return len([s for s in sizes if s >= min_pixels])


def certificate(*, source_png, mask_png, generated_png, output_png, product, reference,
                provider):
    """The exact-hash certificate for one exported composite. A claim until
    `verify_certificate` re-hashes the exported bytes."""
    return {'version': CERT_VERSION, 'restore_version': RESTORE_VERSION,
            'product': {k: product.get(k) for k in ('slug', 'version', 'cir_fingerprint',
                                                     'pdf_sha256', 'pdf_version', 'pieces')},
            'reference': {k: reference.get(k) for k in ('class', 'sha256', 'product_version')},
            'provider': provider, 'source_sha256': _sha(source_png),
            'mask_sha256': _sha(mask_png), 'generated_sha256': _sha(generated_png),
            'output_sha256': _sha(output_png)}


def verify_certificate(cert, output_png):
    if not isinstance(cert, dict) or cert.get('version') != CERT_VERSION:
        return {'status': 'UNKNOWN', 'why': 'no certificate of this version'}
    if cert.get('output_sha256') != _sha(output_png):
        return {'status': 'FAIL', 'why': 'certificate is not bound to these exported bytes'}
    return {'status': 'PASS', 'output_sha256': cert['output_sha256'],
            'digest': _sha(_json.dumps(cert, sort_keys=True).encode())}


# Reference classes. Only the first two can stand for the finished object in a lifestyle
# scene; everything else is informational (a deterministic drawing, chart or card) or
# generated, and is refused as a lifestyle reference however well it verifies as a diagram.
PHOTOGRAPHIC_REFERENCES = frozenset({'physical_product_photo', 'qualified_photoreal_render'})
INFORMATIONAL_REFERENCES = frozenset({'disclosed_render', 'chart', 'infographic',
                                      'pattern_preview', 'gallery_frame'})


def lifestyle_evidence(evidence):
    """Whether a restored lifestyle composite has every piece of evidence publication needs.

    PASS only when all of these are PASS on the same product version: a photographic
    reference (physical photo with bytes and rights on file, or a qualified photoreal render),
    its independent structural truth, a reviewed matte with the CIR's piece count, a mask in
    the provider's polarity, the restoration verifier, the exact-hash certificate on the
    exported bytes, product/PDF version binding, independent Product Truth on the export, and
    the disclosure. Anything missing is UNKNOWN, never PASS. This is evidence, not a gate
    bypass: every existing publication veto still applies on top of it."""
    ev = evidence if isinstance(evidence, dict) else {}
    failed, missing = [], []

    def need(name, ok, present=True, why=''):
        if not present:
            missing.append(name if not why else f'{name}: {why}')
        elif not ok:
            failed.append(name if not why else f'{name}: {why}')

    product = ev.get('product') or {}
    ref = ev.get('reference') or {}
    rclass = ref.get('class')
    if rclass in INFORMATIONAL_REFERENCES:
        failed.append(f'reference: {rclass!r} is informational (diagram/chart/card); it is not '
                      f'photographic truth and cannot stand for the finished object')
    elif rclass not in PHOTOGRAPHIC_REFERENCES:
        missing.append(f'reference: class {rclass!r} is not a qualified photographic reference')
    if rclass == 'physical_product_photo':
        intake = ref.get('intake') or {}
        need('reference.intake', bool(intake.get('may_use')) and bool(intake.get('bytes_present')),
             bool(intake), 'physical_upgrade.intake must show bytes on file and a rights basis')
    st = (ref.get('structural_truth') or {}).get('status')
    need('reference.structural_truth', st == 'PASS', st in ('PASS', 'FAIL'),
         'independent construction review of the reference against the CIR')
    matte = ev.get('matte') or {}
    need('matte.reviewed', matte.get('reviewed') is True, 'reviewed' in matte)
    pieces, counted = product.get('pieces'), matte.get('components')
    need('matte.piece_count', pieces == counted,
         isinstance(pieces, int) and isinstance(counted, int),
         f'matte has {counted} piece(s), the CIR makes {pieces}')
    for name in ('mask', 'restoration', 'product_truth', 'disclosure'):
        status = (ev.get(name) or {}).get('status')
        need(name, status == 'PASS', status in ('PASS', 'FAIL'))
    cert = ev.get('certificate')
    output = ev.get('output_png')
    if isinstance(output, (bytes, bytearray)) and cert:
        cv = verify_certificate(cert, bytes(output))
        need('certificate', cv['status'] == 'PASS', cv['status'] != 'UNKNOWN',
             cv['why'] if cv['status'] != 'PASS' else '')
        cp = cert.get('product') or {}
        bound = (cp.get('slug') == product.get('slug') and cp.get('version') == product.get('version')
                 and cp.get('cir_fingerprint') == product.get('cir_fingerprint')
                 and cp.get('pdf_sha256') == product.get('pdf_sha256'))
        need('certificate.product_binding', bound, True,
             'certificate names another product, version, CIR or PDF')
    else:
        missing.append('certificate or exported bytes')
    versions = {product.get('version'), product.get('pdf_version'), ref.get('product_version')}
    need('version_binding', len(versions) == 1, None not in versions,
         f'product, PDF and reference versions {sorted(map(str, versions))} must be one version')
    status = 'FAIL' if failed else 'UNKNOWN' if missing else 'PASS'
    return {'status': status, 'publishable': status == 'PASS', 'failed': failed,
            'missing': missing, 'certifies_photorealism': False}
