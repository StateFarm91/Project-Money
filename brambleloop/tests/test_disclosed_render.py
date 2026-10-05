"""D-FB-7 disclosed deterministic renders: producer, independent verifier, gate, disclosure.

No network, no model or image provider, no spend. Every adversarial control must come back
FAIL or UNKNOWN -- never PASS -- and every honest Launch-0 frame must PASS.
"""
from __future__ import annotations

import hashlib
import io
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
_TMP = tempfile.mkdtemp(prefix="disclosed_render_")
os.environ.setdefault("BRAMBLELOOP_ARTIFACT_DIR", os.path.join(_TMP, "artifacts"))

import numpy as np  # noqa: E402
from PIL import Image, ImageDraw, ImageFilter  # noqa: E402
from scipy import ndimage  # noqa: E402

from brambleloop.products import launch0  # noqa: E402
from brambleloop.visual import disclosed_render as D  # noqa: E402
from brambleloop.visual import render_contract as K  # noqa: E402
from brambleloop.visual import render_verification as V  # noqa: E402
from brambleloop.visual.product_authority import structural_floor  # noqa: E402

BUILDS = ("basket_small", "basket_medium", "basket_large", "hexagon_coasters",
          "cloudline_blanket")
_CACHE: dict = {}


def cir(build):
    return launch0.cir_for(build)


def frame(build, view):
    key = (build, view)
    if key not in _CACHE:
        _CACHE[key] = D.render(cir(build), view)
    return _CACHE[key]


def png(img) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def rgb(data: bytes):
    return Image.open(io.BytesIO(data)).convert("RGB")


def stitch_components(data: bytes, colour):
    """Connected regions of exactly one yarn colour in the product zone (test-side helper)."""
    arr = np.asarray(rgb(data), dtype=np.int32)
    x0, y0, x1, y1 = K.zone_px(K.PRODUCT_ZONE)
    mask = np.zeros(arr.shape[:2], bool)
    mask[y0:y1, x0:x1] = (np.abs(arr[y0:y1, x0:x1] - np.array(colour)).sum(axis=2) == 0)
    labels, n = ndimage.label(mask)
    return labels, n, ndimage.find_objects(labels)


def central(labels, objs):
    h, w = labels.shape
    best = min(range(len(objs)), key=lambda i: abs((objs[i][0].start + objs[i][0].stop) / 2 - h / 2.3)
               + abs((objs[i][1].start + objs[i][1].stop) / 2 - w / 2))
    return best + 1, objs[best]


def verdict(data, build, view):
    return V.verify(data, cir=cir(build), view=view)


# --------------------------------------------------------------------------- producer

def test_same_inputs_render_identical_bytes():
    for build in BUILDS:
        for view in ("hero", "scale", "detail"):
            a = D.render(cir(build), view)
            b = D.render(cir(build), view)
            assert a.png == b.png, (build, view)
            assert a.manifest == b.manifest
            assert a.manifest["image_sha256"] == hashlib.sha256(a.png).hexdigest()


def test_manifest_records_the_construction_it_claims():
    m = frame("cloudline_blanket", "hero").manifest
    c = cir("cloudline_blanket")
    assert m["kind"] == "disclosed_render" and m["renderer_version"] == D.RENDERER_VERSION
    assert m["cir_fingerprint"] == c.fingerprint and len(m["twin_digest"]) == 64
    assert len(m["colour_map_digest"]) == 64 and m["view"] == "hero"
    assert m["finished_dimensions_cm"] == {"width": 79.2, "height": 97.1}
    assert sum(m["stitch_counts"].values()) == 6930 and m["generated"] is False
    assert all(r["count"] == 99 for r in m["layout"]["rows"])
    assert m["disclosure"] == K.DISCLOSURE


def test_unsupported_constructions_are_refused_not_guessed():
    from dataclasses import replace

    c = cir("hexagon_coasters")
    two = replace(c, components=[c.components[0], replace(c.components[0], name="coaster_b")])
    try:
        D.render(two, "hero")
    except D.RenderRefused:
        pass
    else:
        raise AssertionError("a multi-component CIR was drawn as one piece")


# --------------------------------------------------------------------------- verifier

def test_every_launch0_frame_verifies_against_its_cir():
    for build in BUILDS:
        for view in ("hero", "scale", "detail"):
            r = verdict(frame(build, view).png, build, view)
            assert r["status"] == "PASS", (build, view, r["failed"], r["unknown"])
            assert r["reads_manifest"] is False
            names = {c["check"] for c in r["checks"]}
            assert {"contract_palette", "disclosure_in_image", "scale_bar", "extent_cm",
                    "stitch_counts", "colour_placement", "stitch_pitch_cm"} <= names


def test_expected_values_are_recomputed_from_the_compiler():
    m = V.expected_model(cir("basket_small"))
    assert m["base_rounds"] == 10 and m["wall_rounds"] == 12 and m["sides"] == 6
    assert [len(r["seq"]) for r in m["rows"][:3]] == [6, 12, 18]
    b = V.expected_model(cir("cloudline_blanket"))
    assert len(b["rows"]) == 70 and all(len(r["seq"]) == 99 for r in b["rows"])
    assert sum(sum(r["raised"]) for r in b["rows"]) == 2376     # every dc, nothing else


# --------------------------------------------------------------------------- adversarial

def _not_pass(r, *checks):
    assert r["status"] in ("FAIL", "UNKNOWN"), r
    if checks:
        assert set(checks) & set(r["failed"] + r["unknown"]), (checks, r["failed"], r["unknown"])


def test_a_missing_stitch_fails():
    for build, view in (("cloudline_blanket", "hero"), ("basket_medium", "hero"),
                        ("hexagon_coasters", "detail")):
        data = frame(build, view).png
        cream = K.hex_rgb(cir(build).colors["cream"])
        labels, n, objs = stitch_components(data, cream)
        k, sl = central(labels, objs)
        arr = np.array(rgb(data))
        arr[sl] = K.GAP          # the whole glyph, raised post included
        _not_pass(verdict(png(Image.fromarray(arr)), build, view), "stitch_counts")


def test_two_stitches_merged_into_one_fails():
    build, view = "hexagon_coasters", "scale"
    data = frame(build, view).png
    cream = K.hex_rgb(cir(build).colors["cream"])
    img = rgb(data)
    arr = np.array(img)
    labels, n, objs = stitch_components(data, cream)
    k, sl = central(labels, objs)
    # Fill every gap pixel touching this stitch with its yarn: it swallows its neighbours.
    grown = ndimage.binary_dilation(labels == k, iterations=K.GAP_PX + 2)
    gap = (np.abs(arr.astype(int) - np.array(K.GAP)).sum(axis=2) == 0)
    arr[grown & gap] = cream
    _not_pass(verdict(png(Image.fromarray(arr)), build, view), "stitch_counts")


def test_wrong_colour_placement_fails():
    for build, view, src, dst in (("basket_small", "scale", "cream", "wine"),
                                  ("cloudline_blanket", "detail", "cream", "ink"),
                                  ("hexagon_coasters", "hero", "cream", "wine")):
        c = cir(build)
        data = frame(build, view).png
        labels, n, objs = stitch_components(data, K.hex_rgb(c.colors[src]))
        k, sl = central(labels, objs)
        arr = np.array(rgb(data))
        arr[labels == k] = K.hex_rgb(c.colors[dst])
        _not_pass(verdict(png(Image.fromarray(arr)), build, view), "colour_placement")


def test_a_raised_post_where_the_pattern_has_none_fails():
    build, view = "cloudline_blanket", "detail"
    c = cir(build)
    data = frame(build, view).png
    cream = K.hex_rgb(c.colors["cream"])
    labels, n, objs = stitch_components(data, cream)
    # the bottom border rows are all sc: put a post on one of them
    k = max(range(1, n + 1), key=lambda i: objs[i - 1][0].stop * 10000 - objs[i - 1][1].start)
    sl = objs[k - 1]
    img = rgb(data)
    d = ImageDraw.Draw(img)
    ys, xs = sl
    mid = (xs.start + xs.stop) // 2
    d.rectangle([mid - 6, ys.start + 4, mid + 6, ys.stop - 5], fill=K.relief(cream))
    _not_pass(verdict(png(img), build, view), "raised_stitch_placement")


def test_wrong_scale_or_dimensions_fail():
    build, view = "basket_large", "scale"
    data = frame(build, view).png
    img = rgb(data)
    d = ImageDraw.Draw(img)
    d.fontmode = "1"
    d.rectangle(K.zone_px(K.SCALE_ZONE), fill=K.BACKGROUND)
    u = frame(build, view).manifest["layout"]["px_per_cm"]
    D._scale_bar(d, u * 1.10)               # the bar now claims a 10 % smaller product
    _not_pass(verdict(png(img), build, view), "extent_cm")
    # And the product drawn 8 % too large against an honest bar.
    small = D.render(cir(build), view)
    shrunk = rgb(small.png)
    x0, y0, x1, y1 = K.zone_px(K.PRODUCT_ZONE)
    part = shrunk.crop((x0, y0, x1, y1))
    big = part.resize((int(part.width * 1.08), int(part.height * 1.08)), Image.NEAREST)
    canvas = shrunk.copy()
    canvas.paste(Image.new("RGB", part.size, K.BACKGROUND), (x0, y0))
    canvas.paste(big.crop((0, 0, part.width, part.height)), (x0, y0))
    _not_pass(verdict(png(canvas), build, view))


def test_a_swapped_product_fails():
    for shown, claimed, view in (("basket_medium", "basket_small", "hero"),
                                 ("basket_large", "basket_medium", "detail"),
                                 ("hexagon_coasters", "cloudline_blanket", "hero"),
                                 ("cloudline_blanket", "hexagon_coasters", "scale")):
        _not_pass(verdict(frame(shown, view).png, claimed, view))


def test_a_view_claimed_as_another_view_fails():
    # the elevation (scale) frame offered as the oblique hero: the camera does not match
    _not_pass(verdict(frame("basket_small", "scale").png, "basket_small", "hero"))


def test_generative_looking_redraws_fail():
    data = frame("hexagon_coasters", "hero").png
    img = rgb(data)
    blurred = img.filter(ImageFilter.GaussianBlur(1.2))
    _not_pass(verdict(png(blurred), "hexagon_coasters", "hero"), "contract_palette")
    rs = np.random.RandomState(7)
    noisy = np.clip(np.asarray(img, dtype=np.int16) + rs.randint(-9, 10, (2000, 2000, 3)), 0, 255)
    _not_pass(verdict(png(Image.fromarray(noisy.astype(np.uint8))), "hexagon_coasters", "hero"))
    resampled = img.resize((1400, 1400), Image.BICUBIC).resize((2000, 2000), Image.BICUBIC)
    _not_pass(verdict(png(resampled), "hexagon_coasters", "hero"), "contract_palette")
    jpeg = io.BytesIO()
    img.save(jpeg, format="JPEG", quality=92)
    _not_pass(verdict(jpeg.getvalue(), "hexagon_coasters", "hero"))


def test_disclosure_caption_removed_or_reworded_fails():
    data = frame("basket_small", "hero").png
    img = rgb(data)
    d = ImageDraw.Draw(img)
    y = round(K.CAPTION_TOP * K.CANVAS_PX)
    d.rectangle([0, y - 10, 1999, y + 60], fill=K.BACKGROUND)
    _not_pass(verdict(png(img), "basket_small", "hero"), "disclosure_in_image")
    d.fontmode = "1"
    d.text((420, y), "Digital rendering of the pattern's finished design", fill=K.CAPTION,
           font=K.font(K.CAPTION_PX))
    _not_pass(verdict(png(img), "basket_small", "hero"), "disclosure_in_image")


# --------------------------------------------------------------------------- the gate

def _stored(data: bytes, root: str) -> str:
    from brambleloop.core.artifacts import ArtifactStore

    return ArtifactStore(root).put("t.png", data, "image/png").sha256


def _frame_record(build, view, root, *, data=None, **over):
    f = frame(build, view)
    data = f.png if data is None else data
    sha = _stored(data, root)
    manifest = dict(f.manifest, image_sha256=sha)
    rec = {"kind": "disclosed_render", "generated": False, "made": True,
           "role": f.manifest["role"], "slug": f.manifest["slug"],
           "version": f.manifest["version"], "image": {"sha256": sha},
           "disclosed_render": manifest, "artifact_dir": root}
    rec.update(over)
    return rec


def test_structural_floor_passes_only_on_verified_bound_bytes():
    root = tempfile.mkdtemp()
    ok = _frame_record("hexagon_coasters", "hero", root)
    r = structural_floor(ok)
    assert r["status"] == "PASS", r
    assert r["verification"]["verifier_version"] == V.VERIFIER_VERSION
    # Image digest not the one the manifest binds.
    other = dict(ok, image={"sha256": "a" * 64})
    assert structural_floor(other)["status"] == "FAIL"
    # Bytes not in the store.
    missing = _frame_record("hexagon_coasters", "hero", root)
    missing["artifact_dir"] = tempfile.mkdtemp()
    assert structural_floor(missing)["status"] == "UNKNOWN"


def test_manifest_lie_with_another_products_correct_pixels_fails():
    root = tempfile.mkdtemp()
    # Pixels of the medium basket, honestly hashed, under the small basket's manifest.
    medium = frame("basket_medium", "hero").png
    lie = _frame_record("basket_small", "hero", root, data=medium)
    assert structural_floor(lie)["status"] == "FAIL"
    # A manifest naming the right slug with another design's fingerprint.
    fp = _frame_record("basket_small", "hero", root)
    fp["disclosed_render"] = dict(fp["disclosed_render"],
                                  cir_fingerprint=cir("basket_medium").fingerprint)
    assert structural_floor(fp)["status"] == "FAIL"
    # Frame says one product, manifest another.
    split = _frame_record("basket_small", "hero", root, slug="market-basket-medium")
    assert structural_floor(split)["status"] == "FAIL"
    # Role that does not match the view.
    role = _frame_record("basket_small", "hero", root, role="detail")
    assert structural_floor(role)["status"] == "FAIL"


def test_photos_and_generations_get_nothing_from_the_render_branch():
    root = tempfile.mkdtemp()
    for over in ({"generated": True}, {"carries_model": True}, {"provider": "some-model"},
                 {"photographic_realism": {"verdict": "clear"}}, {"kind": "owned_photo"}):
        r = structural_floor(_frame_record("cloudline_blanket", "detail", root, **over))
        assert r["status"] != "PASS", (over, r)
    # A composited frame (protected-product evidence) keeps the old semantics: never PASS.
    comp = _frame_record("cloudline_blanket", "detail", root,
                         protected_product={"source_sha256": "b" * 64, "output_sha256": "c" * 64})
    assert structural_floor(comp)["status"] != "PASS"
    # An unqualified renderer version.
    rec = _frame_record("cloudline_blanket", "detail", root)
    rec["disclosed_render"] = dict(rec["disclosed_render"], renderer_version="disclosed-render/9")
    assert structural_floor(rec)["status"] == "UNKNOWN"


def test_existing_refusals_hold_on_a_disclosed_frame():
    root = tempfile.mkdtemp()
    rec = _frame_record("hexagon_coasters", "scale", root, motif={"verdict": "mismatch"})
    assert structural_floor(rec)["status"] == "FAIL"
    tampered = np.array(rgb(frame("hexagon_coasters", "scale").png))
    tampered[700:760, 900:960] = K.hex_rgb(cir("hexagon_coasters").colors["wine"])
    bad = _frame_record("hexagon_coasters", "scale", root, data=png(Image.fromarray(tampered)))
    assert structural_floor(bad)["status"] == "FAIL"


# --------------------------------------------------------------------------- disclosure

def test_disclosure_is_enforced_in_image_alt_text_and_copy():
    from brambleloop.publish import disclosed_listing as DL

    root = tempfile.mkdtemp()
    c = cir("hexagon_coasters")
    rec = _frame_record("hexagon_coasters", "hero", root)
    rec["alt_text"] = DL.alt_text(rec["disclosed_render"], c)
    data = frame("hexagon_coasters", "hero").png
    assert rec["alt_text"].startswith(K.DISCLOSURE) and len(rec["alt_text"]) <= 500
    good = DL.export_check(rec, image_bytes=data, description="Pattern.\n" + DL.COPY_DISCLOSURE, cir=c)
    assert good["ok"], good
    no_copy = DL.export_check(rec, image_bytes=data, description="A lovely pattern.", cir=c)
    assert not no_copy["ok"] and any("copy" in p for p in no_copy["problems"])
    no_alt = DL.export_check(dict(rec, alt_text="Hexagon coasters"), image_bytes=data,
                             description=DL.COPY_DISCLOSURE, cir=c)
    assert not no_alt["ok"] and any("alt text" in p for p in no_alt["problems"])
    img = rgb(data)
    ImageDraw.Draw(img).rectangle([0, 1700, 1999, 1790], fill=K.BACKGROUND)
    stripped = png(img)
    rec2 = _frame_record("hexagon_coasters", "hero", root, data=stripped)
    rec2["alt_text"] = rec["alt_text"]
    no_cap = DL.export_check(rec2, image_bytes=stripped, description=DL.COPY_DISCLOSURE, cir=c)
    assert not no_cap["ok"] and any("caption" in p for p in no_cap["problems"])


def test_policy_classification_writes_the_disclosure_into_the_copy():
    from brambleloop.gates import platform_policy as P
    from brambleloop.publish import disclosed_listing as DL

    frames = [{"kind": "disclosed_render", "generated": False, "role": r, "position": i,
               "image_ref": f"sha256:{i}", "disclosure": {"in_image": True, "in_alt_text": True}}
              for i, r in enumerate(("hero", "scale", "detail"), start=1)]
    c = P.classify_release([], [], disclosed=frames)
    assert c.ok, c.problems
    assert DL.COPY_DISCLOSURE in c.disclosures
    assert K.DISCLOSURE.lower() in P.disclosure_block(c).lower()
    unlabelled = [dict(frames[0], disclosure={"in_image": True, "in_alt_text": False})]
    assert not P.classify_release([], [], disclosed=unlabelled).ok
    try:
        P.classify_release([], [], disclosed=[dict(frames[0], generated=True)])
    except P.PolicyRefused:
        pass
    else:
        raise AssertionError("a generated frame was classified as a disclosed render")


# --------------------------------------------------------------------------- listing QA

def test_listing_sets_pass_every_qa_gate():
    from brambleloop.core.artifacts import ArtifactStore
    from brambleloop.publish import disclosed_listing as DL

    for build in ("basket_small", "hexagon_coasters", "cloudline_blanket"):
        rec = DL.build(cir(build), store=ArtifactStore(tempfile.mkdtemp()))
        assert rec["made"] and rec["usable_as_listing_asset"], (build, rec["launch_blocked"])
        qa = rec["qa"]
        assert qa["layout_qa"]["ok"] and qa["asset_truth"]["ok"] and qa["frame_set"]["ok"]
        assert qa["mobile"]["ok"] and qa["hero_thumbnail"]["ok"]
        for f in rec["frames"]:
            assert f["structural_truth"]["status"] == "PASS"
            assert f["readable_at_grid"] is True
            assert f["disclosure"] == {"in_image": True, "in_alt_text": True}
            assert qa["frames"][f["view"]]["legibility_340"]["ok"]


def test_340px_legibility_catches_a_lost_piece_and_a_vanished_colour():
    from brambleloop.publish import disclosed_listing as DL

    c = cir("hexagon_coasters")
    model = V.expected_model(c)
    hero = frame("hexagon_coasters", "hero").png
    assert DL._thumb_legibility(hero, model, 4)["ok"]
    assert not DL._thumb_legibility(hero, model, 3)["ok"]
    # The wine band thinned to one pixel in four: present at full size, gone at 340 px.
    arr = np.array(rgb(hero))
    wine = np.abs(arr.astype(int) - np.array(K.hex_rgb(c.colors["wine"]))).sum(axis=2) == 0
    sparse = np.zeros_like(wine)
    sparse[::2, ::2] = True
    arr[wine & ~sparse] = K.hex_rgb(c.colors["cream"])
    out = DL._thumb_legibility(png(Image.fromarray(arr)), model, 4)
    assert not out["ok"] and any("wine" in p for p in out["problems"]), out


if __name__ == "__main__":
    import time

    failures = 0
    tests = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
    for name, test in tests:
        started = time.time()
        try:
            test()
            print("OK  ", name, f"{time.time() - started:.1f}s")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            import traceback

            traceback.print_exc()
            print("FAIL", name, type(exc).__name__, str(exc)[:500])
    print(f"{len(tests) - failures}/{len(tests)} passing")
    sys.exit(bool(failures))
