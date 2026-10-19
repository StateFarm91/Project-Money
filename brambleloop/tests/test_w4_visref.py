"""W4-VISREF: offline tests for masked background edit + deterministic product restoration.

Synthetic fixtures only; no network, no provider, no spend. The provider is simulated by an
image that deliberately repaints the product region too, because masked generation is
assumed NOT to preserve pixels.
"""
import hashlib
import sys
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from PIL import Image  # noqa: E402

from brambleloop.visual import compose as C  # noqa: E402

W = H = 64
CREAM, WINE, BG_OLD = (250, 246, 235), (110, 31, 42), (176, 186, 172)
IDEO, RECRAFT = 'ideogram-4.5-precise-edit', 'recraft-v3-generate-background'


def png(im, **kw):
    out = BytesIO(); im.save(out, format='PNG', **kw); return out.getvalue()


def decode(data):
    return Image.open(BytesIO(data))


def fixture():
    """Two pieces (a 'pair'). Piece A: wine border, cream body, a 3x3 wine motif, a 2x2 true
    hole, and a soft fringe hanging below. Piece B: same body with a fuzz halo of soft alpha."""
    im = Image.new('RGBA', (W, H), BG_OLD + (0,))
    for ox, oy in ((4, 6), (36, 6)):
        for y in range(oy, oy + 22):
            for x in range(ox, ox + 22):
                border = x in (ox, ox + 1, ox + 20, ox + 21) or y in (oy, oy + 1, oy + 20, oy + 21)
                im.putpixel((x, y), (WINE if border else CREAM) + (255,))
        for y in range(oy + 9, oy + 12):
            for x in range(ox + 9, ox + 12):
                im.putpixel((x, y), WINE + (255,))
    for y in (14, 15):                       # true crochet hole inside piece A
        for x in (8, 9):
            im.putpixel((x, y), BG_OLD + (0,))
    for x in range(6, 24, 3):                # fringe strands under piece A
        for i, y in enumerate(range(28, 34)):
            im.putpixel((x, y), CREAM + (200 - 30 * i,))
    for x in range(35, 59):                  # fuzz halo around piece B
        im.putpixel((x, 5), CREAM + (96,)); im.putpixel((x, 28), CREAM + (64,))
    for y in range(6, 28):
        im.putpixel((35, y), CREAM + (128,)); im.putpixel((58, y), CREAM + (32,))
    return png(im)


def provider_output(size=(W, H)):
    """A 'generated' scene that ALSO repaints the product (no pixel preservation)."""
    g = Image.new('RGB', size)
    g.putdata([((x * 3) % 256, (y * 5) % 256, (x + y) % 256)
               for y in range(size[1]) for x in range(size[0])])
    return png(g)


def restored():
    src, gen = fixture(), provider_output()
    out, verdict = C.restore(src, gen)
    return src, gen, out, verdict


# 1. mask polarity and dimensions ---------------------------------------------------------

def test_mask_polarity_matches_each_providers_documented_convention():
    src = fixture()
    alpha = decode(src).getchannel('A')
    for provider, keep, edit in ((IDEO, 255, 0), (RECRAFT, 0, 255)):
        mask = decode(C.edit_mask(src, provider))
        assert mask.size == (W, H) and mask.mode == 'L'
        assert mask.getpixel((10, 10)) == keep            # product body: keep
        assert mask.getpixel((8, 14)) == edit             # true hole: background shows through
        assert mask.getpixel((6, 30)) == keep             # soft fringe pixel: keep (restored)
        assert mask.getpixel((1, 1)) == edit              # background: edit
        assert all((m == keep) == bool(a) for m, a in zip(mask.getdata(), alpha.getdata()))
        assert C.check_mask(C.edit_mask(src, provider), src, provider)['status'] == 'PASS'


def test_inverted_resized_grey_and_unknown_masks_are_refused():
    src = fixture()
    ideo = decode(C.edit_mask(src, IDEO))
    assert C.check_mask(png(ideo.point(lambda v: 255 - v)), src, IDEO)['status'] == 'FAIL'
    assert C.check_mask(C.edit_mask(src, RECRAFT), src, IDEO)['status'] == 'FAIL'
    assert C.check_mask(png(ideo.resize((W * 2, H * 2))), src, IDEO)['status'] == 'FAIL'
    grey = ideo.copy(); grey.putpixel((0, 0), 128)
    assert C.check_mask(png(grey), src, IDEO)['status'] == 'FAIL'
    assert C.check_mask(png(Image.new('L', (W, H), 255)), src, IDEO)['status'] == 'FAIL'
    assert C.check_mask(C.edit_mask(src, IDEO), src, 'flux-2-pro')['status'] == 'UNKNOWN'
    full = png(Image.new('RGBA', (W, H), CREAM + (255,)))
    try:
        C.edit_mask(full, IDEO)
    except C.RestoreRefused:
        pass
    else:
        raise AssertionError('a mask with no edit region was produced')


# 2. exact preservation of protected regions after restoration -----------------------------

def test_restoration_overwrites_a_provider_that_repainted_the_product():
    src, gen, out, verdict = restored()
    s, g, o = decode(src).convert('RGBA'), decode(gen), decode(out)
    assert verdict['status'] == 'PASS' and verdict['core_changed'] == 0
    assert any(s.getpixel(p)[:3] != g.getpixel(p) for p in ((10, 10), (14, 16)))  # provider drifted
    core = [(x, y) for y in range(H) for x in range(W) if s.getpixel((x, y))[3] == 255]
    assert core and all(o.getpixel(p) == s.getpixel(p)[:3] for p in core)
    assert verdict['certifies_construction'] is False and verdict['certifies_photorealism'] is False


# 3. alpha at yarn fuzz, fringe and crochet holes -------------------------------------------

def test_soft_edges_follow_the_alpha_equation_and_holes_show_the_new_scene():
    src, gen, out, _ = restored()
    s, g, o = decode(src).convert('RGBA'), decode(gen), decode(out)
    assert o.mode == 'RGB'                                   # no transparency in the export
    for p in ((8, 14), (9, 15)):                             # hole: new scene, not old background
        assert o.getpixel(p) == g.getpixel(p) and o.getpixel(p) != BG_OLD
    soft = [(x, y) for y in range(H) for x in range(W) if 0 < s.getpixel((x, y))[3] < 255]
    assert len(soft) > 50
    for p in soft:
        sp, gp = s.getpixel(p), g.getpixel(p)
        assert o.getpixel(p) == tuple(C.blend(sp[i], sp[3], gp[i]) for i in range(3))


def test_existing_exact_copy_mode_keeps_partial_alpha_which_etsy_renders_black():
    """Characterises why the separate alpha-edge mode exists: `protect` (unchanged) copies
    soft pixels with their alpha, so its export is not opaque."""
    src = fixture()
    out, proof = C.protect(src, png(decode(provider_output()).convert('RGBA')))
    assert proof['status'] == 'PASS'
    alphas = set(decode(out).getchannel('A').getdata())
    assert any(0 < a < 255 for a in alphas)


# 4. motifs, borders, colours and piece counts --------------------------------------------

def _corrupt(out, fn):
    im = decode(out).convert('RGB'); fn(im); return png(im)


def test_motif_border_colour_and_piece_corruptions_are_rejected():
    src, gen, out, _ = restored()
    cases = {
        'motif removed': lambda im: [im.putpixel((x, y), CREAM) for x in range(13, 16) for y in range(15, 18)],
        'border recoloured': lambda im: [im.putpixel((x, 6), CREAM) for x in range(4, 26)],
        'colours swapped': lambda im: im.putdata([WINE if p == CREAM else CREAM if p == WINE else p for p in im.getdata()]),
        'piece omitted': lambda im: [im.putpixel((x, y), (1, 2, 3)) for x in range(36, 58) for y in range(6, 28)],
        'fringe pixel moved': lambda im: im.putpixel((6, 30), (0, 0, 0)),
        'hole filled': lambda im: [im.putpixel((x, y), CREAM) for x in (8, 9) for y in (14, 15)],
    }
    for name, fn in cases.items():
        verdict = C.verify_restored(src, gen, _corrupt(out, fn))
        assert verdict['status'] == 'FAIL', name


def test_matte_piece_count_is_held_to_the_cir():
    src = fixture()
    assert C.matte_components(src) == 2
    one = decode(src).convert('RGBA')
    for x in range(35, 59):
        for y in range(5, 29):
            one.putpixel((x, y), (0, 0, 0, 0))
    assert C.matte_components(png(one)) == 1
    ev = full_evidence(); ev['matte']['components'] = 1
    r = C.lifestyle_evidence(ev)
    assert r['status'] == 'FAIL' and any('piece_count' in f for f in r['failed'])


# 5/6. product + PDF version binding, exact certification of the exported image -----------

PRODUCT = {'slug': 'mosaic-placemat-pair', 'version': '1.3.0', 'cir_fingerprint': 'f' * 64,
           'pdf_sha256': 'a' * 64, 'pdf_version': '1.3.0', 'pieces': 2}


def full_evidence():
    src, gen, out, verdict = restored()
    mask = C.edit_mask(src, IDEO)
    ref = {'class': 'physical_product_photo', 'sha256': hashlib.sha256(src).hexdigest(),
           'product_version': '1.3.0', 'intake': {'may_use': True, 'bytes_present': True},
           'structural_truth': {'status': 'PASS'}}
    cert = C.certificate(source_png=src, mask_png=mask, generated_png=gen, output_png=out,
                         product=PRODUCT, reference=ref, provider=IDEO)
    return {'product': dict(PRODUCT), 'reference': ref,
            'matte': {'reviewed': True, 'components': C.matte_components(src)},
            'mask': C.check_mask(mask, src, IDEO), 'restoration': verdict,
            'product_truth': {'status': 'PASS'}, 'disclosure': {'status': 'PASS'},
            'certificate': cert, 'output_png': out}


def test_certificate_binds_the_exact_exported_bytes():
    ev = full_evidence()
    out, cert = ev['output_png'], ev['certificate']
    assert C.verify_certificate(cert, out)['status'] == 'PASS'
    # identical pixels, different encoding: a different file, so not the certified one
    reenc = png(decode(out), compress_level=1)
    assert decode(reenc).tobytes() == decode(out).tobytes() and reenc != out
    assert C.verify_certificate(cert, reenc)['status'] == 'FAIL'
    assert C.verify_certificate({}, out)['status'] == 'UNKNOWN'


def test_product_pdf_and_reference_versions_must_be_one_version():
    ev = full_evidence(); ev['product']['pdf_version'] = '1.2.0'
    assert C.lifestyle_evidence(ev)['status'] == 'FAIL'
    ev = full_evidence(); ev['product']['pdf_version'] = None
    assert C.lifestyle_evidence(ev)['status'] == 'UNKNOWN'
    ev = full_evidence(); ev['product']['cir_fingerprint'] = 'e' * 64
    r = C.lifestyle_evidence(ev)
    assert r['status'] == 'FAIL' and any('product_binding' in f for f in r['failed'])
    ev = full_evidence(); ev['product']['pdf_sha256'] = 'b' * 64
    assert C.lifestyle_evidence(ev)['status'] == 'FAIL'


# 7. photographic versus informational roles ----------------------------------------------

def test_informational_references_are_refused_and_lifestyle_frames_are_photographic():
    for cls in ('disclosed_render', 'chart', 'infographic', 'gallery_frame'):
        ev = full_evidence(); ev['reference']['class'] = cls
        r = C.lifestyle_evidence(ev)
        assert r['status'] == 'FAIL' and not r['publishable']
    ev = full_evidence(); ev['reference']['class'] = 'ai_generated_scene'
    assert C.lifestyle_evidence(ev)['status'] == 'UNKNOWN'
    from brambleloop.visual import frame_role as FR
    for cls in ('PHYSICAL_PRODUCT_PHOTO', 'AI_LIFESTYLE_CONCEPT'):
        assert FR.classify(SimpleNamespace(asset_class=cls, role='lifestyle')) == FR.PHOTOGRAPHIC
    assert FR.classify(SimpleNamespace(asset_class='DIGITAL_TWIN_RENDER', role='hero')) == FR.DISCLOSED_RENDER


def test_a_real_disclosed_render_is_an_opaque_diagram_whose_cutout_includes_its_captions():
    """Root cause, measured on a real certified product: the only qualified producer is an
    opaque RGB drawing, and `final_image_gate.product_cutout` counts its caption and scale bar
    as 'product', so it cannot be the foreground of a truthful lifestyle photograph."""
    from brambleloop.products import launch0
    from brambleloop.visual import disclosed_render as DR
    from brambleloop.visual.final_image_gate import product_cutout
    cir = launch0.cir_for(launch0.candidate('hexagon-coaster-set').variants[0].build)
    frame = DR.render(cir, 'hero')
    assert decode(frame.png).mode == 'RGB'
    cut = decode(product_cutout(frame.png)).getchannel('A')
    w, h = cut.size
    caption_band = [cut.getpixel((x, y)) for y in range(int(h * 0.85), h) for x in range(w)]
    assert any(a == 255 for a in caption_band)              # text/scale bar is "product"
    assert set(cut.getdata()) <= {0, 255}                    # binary matte: no fuzz, no holes


# 8. intentionally corrupted inputs ---------------------------------------------------------

def test_corrupted_or_mismatched_inputs_are_refused():
    src, gen, out, _ = restored()
    for bad_gen in (provider_output((W + 1, H)), provider_output((W * 2, H * 2))):
        try:
            C.restore(src, bad_gen)
        except C.RestoreRefused:
            pass
        else:
            raise AssertionError('a resized provider output was restored')
    try:
        C.restore(src, gen[:len(gen) // 2])
    except Exception:  # noqa: BLE001 - truncated bytes must not produce an image
        pass
    else:
        raise AssertionError('truncated provider bytes were restored')
    with_alpha = png(decode(out).convert('RGBA'))
    assert C.verify_restored(src, gen, with_alpha)['status'] == 'FAIL'
    empty = png(Image.new('RGBA', (W, H), (0, 0, 0, 0)))
    try:
        C.restore(empty, gen)
    except C.RestoreRefused:
        pass
    else:
        raise AssertionError('an empty matte was restored')
    assert C.verify_restored(empty, gen, png(decode(gen)))['status'] == 'UNKNOWN'


# 9. no publication without all required evidence -----------------------------------------

def test_only_complete_evidence_is_publishable_and_unknown_never_becomes_pass():
    full = full_evidence()
    passed = C.lifestyle_evidence(full)
    assert passed['status'] == 'PASS' and passed['publishable'], passed
    for key in ('reference', 'matte', 'mask', 'restoration', 'product_truth', 'disclosure',
                'certificate', 'output_png', 'product'):
        ev = full_evidence(); ev.pop(key)
        r = C.lifestyle_evidence(ev)
        assert r['status'] != 'PASS' and not r['publishable'], key
    for key in ('product_truth', 'restoration', 'mask', 'disclosure'):
        ev = full_evidence(); ev[key] = {'status': 'UNKNOWN'}
        assert C.lifestyle_evidence(ev)['status'] == 'UNKNOWN', key
    ev = full_evidence(); ev['reference']['structural_truth'] = {'status': 'UNKNOWN'}
    assert C.lifestyle_evidence(ev)['status'] == 'UNKNOWN'
    ev = full_evidence(); ev['reference']['intake'] = {'may_use': False, 'bytes_present': True}
    assert C.lifestyle_evidence(ev)['status'] == 'FAIL'
    ev = full_evidence(); ev['matte']['reviewed'] = False
    assert C.lifestyle_evidence(ev)['status'] == 'FAIL'
    assert C.lifestyle_evidence(None)['status'] != 'PASS'
    assert C.lifestyle_evidence(full)['certifies_photorealism'] is False


def test_owned_photography_still_refuses_and_final_gate_stays_unknown_without_a_source():
    from brambleloop.publish import owned_photography as OP
    from brambleloop.visual import final_image_gate as FIG
    r = OP.make(None, SimpleNamespace(slug='hexagon-coaster-set'), None)
    assert r['made'] is False and r['structural_truth']['status'] == 'UNKNOWN'
    assert FIG.evaluate({})['status'] == 'UNKNOWN'


if __name__ == '__main__':
    failures = 0
    tests = [(n, f) for n, f in list(globals().items()) if n.startswith('test_') and callable(f)]
    for name, test in tests:
        try:
            test(); print('OK  ', name)
        except Exception as exc:  # noqa: BLE001
            failures += 1; print('FAIL', name, type(exc).__name__, exc)
    print(f'{len(tests) - failures}/{len(tests)} passed')
    sys.exit(1 if failures else 0)
