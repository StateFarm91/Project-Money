"""IMAGES-DIALIN: basket generation mirrors the owner's method, the vessel palette check is
illumination-corrected, and the Images page lists every product's runs and frames.

Pins:
- the FLUX 3 request for a basket's product-only frame: the deterministic pattern-derived
  layout reference (now with the wall's side elevation and the rim's true side count) is sent
  as the first `images` entry; the prompt states the exact palette (id -> hex), the wall bands
  bottom to top with rounds and shares, and the side count, all equal to the fidelity gate's
  own model (`visual.vessel.vessel_models`); the request is the 2k tier (>= 2000 px).
- the vessel side-view check under photographic light: a correctly coloured, shaded wall
  passes; the same light on the wrong colourway still fails; the uncorrected reading of the
  correct wall is below the floor (the defect that was fixed).
- `image_production.status_board` lists a listing outside LAUNCH0_SLUGS that has runs, every
  run and every candidate frame (thumbnail route, verdict, codes); the page JS unwraps GET
  envelopes.
Offline, deterministic, no paid call.

Run: cd brambleloop && PYTHONPATH=src python3 tests/test_images_dialin.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import base64
import hashlib
import io
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from brambleloop.creative import flux_prompt as FP  # noqa: E402
from brambleloop.creative import image_stages as S  # noqa: E402
from brambleloop.creative import pattern_refs as P  # noqa: E402
from brambleloop.gateway import images  # noqa: E402
from brambleloop.products import launch0  # noqa: E402
from brambleloop.visual import fidelity as F  # noqa: E402
from brambleloop.visual import vessel as V  # noqa: E402

BASKET = launch0.cir_for("basket_small")
KEY = launch0.cir_for("key_basket")
_WORK = Path(tempfile.mkdtemp(prefix="images-dialin-"))


def _release(cir):
    return S.release_from_cir(cir, release_hash=P.release_hash_of(cir),
                              out_dir=_WORK / cir.slug)


class _Capture:
    """A renderer that records the call and returns a 2048 px PNG; nothing is sent or spent."""

    def __init__(self):
        self.calls = []

    def __call__(self, prompt, *, reference_urls, size, work_dir, purpose, agent, db=None,
                 job_id=None, **_):
        self.calls.append({"prompt": prompt, "refs": list(reference_urls), "size": size})
        Path(work_dir).mkdir(parents=True, exist_ok=True)
        out = Path(work_dir) / f"out-{len(self.calls)}.png"
        Image.new("RGB", (2048, 2048), (120, 110, 100)).save(out)
        shas = [hashlib.sha256(Path(r).read_bytes()).hexdigest() for r in reference_urls]
        return {"path": str(out), "conditioning": {"reference_sha256s": shas},
                "provider": "flux-3-image", "model": "flux-3-image"}


def _request(cir, view="top"):
    rel = _release(cir)
    cap = _Capture()
    S.product_only(rel, renderer=cap, work_dir=str(_WORK / f"{cir.slug}-{view}"), view=view)
    call = cap.calls[0]
    prov = images.BY_KEY["flux-3-image"]
    _url, headers, raw = images._request_for(prov, "dummy-key", call["prompt"], call["refs"],
                                             call["size"])
    return rel, call, json.loads(raw)


def test_the_basket_request_carries_the_pattern_reference_palette_bands_sides_and_2k():
    model = V.vessel_models(BASKET)[0]
    for view in ("top", "side"):
        rel, call, body = _request(BASKET, view)
        # the deterministic pattern-derived reference is the first input image, byte for byte
        layout = Path(rel.pattern_refs[P.ROLES.index("layout")]).read_bytes()
        assert body["images"][0] == base64.b64encode(layout).decode(), "layout is images[0]"
        assert len(body["images"]) == len(P.ROLES)
        # resolution: the 2k tier, ~2048 px a side, meets the 2000 px listing floor
        assert call["size"] == S.PRODUCT_SIZE == "2048x2048"
        assert body["resolution"] == "2k" and body["aspect_ratio"] == "1:1"
        assert min(S.expected_px(call["size"])) >= S.LISTING_MIN_PX
        assert images.BFL3_TIER_USD["2k"] * 16 <= 2.50, "16 images at 2k fit the US$2.50 cap"
        p = body["prompt"]
        # palette, from the CIR, id -> hex
        for cid, hx in BASKET.colors.items():
            assert f"{cid} {hx}" in p, (cid, hx)
        assert "yarn colours exactly and only cream #FAF6EB, wine #6E1F2A" in p
        # sides: the gate counts six corners from above
        assert "exactly 6 flat sides and 6 corners" in p
        # wall bands bottom to top, rounds per band, equal to the gate's own model
        for cid, n in zip(model.wall_bands, model.wall_rows):
            assert f"{n} round{'s' if n != 1 else ''} of {cid} {BASKET.colors[cid]}" in p
        assert "4 rounds of cream" in p and p.index("4 rounds of cream") < p.index(
            "2 rounds of wine") < p.index("1 round of cream") < p.index("3 rounds of cream")
        assert "exactly 2 contrast bands" in p
        assert "in exactly 12 rounds" in p
    v = rel.rules["vessel"]
    assert [b["colour"] for b in v["wall_bands"]] == model.wall_bands
    assert [b["rounds"] for b in v["wall_bands"]] == model.wall_rows
    assert v["sides"] == model.sides == 6


def test_a_round_basket_is_told_it_is_round_with_its_bands():
    rel, call, body = _request(KEY)
    model = V.vessel_models(KEY)[0]
    p = body["prompt"]
    assert "seen from above the rim is a circle" in p
    assert f"in exactly {model.wall_total_rows} rounds" in p
    assert "exactly 4 contrast bands" in p, p
    assert body["resolution"] == "2k"


def test_the_layout_reference_shows_the_wall_bands_and_the_true_side_count():
    rel = _release(BASKET)
    img = np.asarray(Image.open(rel.pattern_refs[0]).convert("RGB"), dtype=float)
    h, w, _ = img.shape
    # left half: the side elevation -- its centre column reads the CIR's bands bottom to top
    col = img[:, int(w * 0.25)]
    lab = F._lab(col)
    pal = {k: F._lab(np.array([F._hex_rgb(v)], dtype=float))[0] for k, v in BASKET.colors.items()}
    labels = []
    for px in lab:
        d = {k: float(F._de(px, c)) for k, c in pal.items()}
        k = min(d, key=d.get)
        labels.append(k if d[k] < 10 else None)
    runs = []
    for lab_id in reversed(labels):
        if lab_id is None:
            continue
        if runs and runs[-1] == lab_id:
            continue
        runs.append(lab_id)
    assert runs == V.vessel_models(BASKET)[0].wall_bands, runs
    # right half: the top outline is a hexagon (six corners), not the rounds chart's circle
    top = Image.fromarray(img[:, w // 2:].astype(np.uint8))
    arr = np.asarray(top, dtype=float)
    mask = F._de(F._lab(arr), F._lab(np.array([P.BACKGROUND], dtype=float))[0]) > 5
    n, _m = V.corner_count(mask)
    assert n == 6, n


def _shaded_side(bands=None):
    import test_v2_vessel_fidelity as T

    raw = T.side_view(bands)
    im = np.asarray(Image.open(io.BytesIO(raw)).convert("RGB"), dtype=float)
    # photographic light: one stop-ish darker and warm, as a lamp-lit room reads
    lit = np.clip(im * np.array([0.80, 0.74, 0.66]), 0, 255).astype(np.uint8)
    buf = io.BytesIO()
    Image.fromarray(lit).save(buf, "PNG")
    return buf.getvalue()


def test_the_vessel_palette_is_judged_after_illumination_correction():
    model = V.vessel_models(BASKET)[0]
    data = _shaded_side()
    out = {c["check"].split(":")[-1]: c for c in V.verify_side(data, model)}
    assert out["palette"]["status"] == "PASS", out["palette"]
    assert out["wall_bands"]["status"] == "PASS", out["wall_bands"]
    assert out["palette"]["gain"] and out["palette"]["coverage"] >= V.PALETTE_COVERAGE_MIN
    # the defect: the same wall read raw (no correction, no mixes) is under the floor
    mask, lab, _ = V._product_mask(data)
    _ids, pal, _ = V._palette_arrays(model.palette)
    wall = V._wall_pixels(mask)
    raw = float((F._de(lab[wall][:, None, :], pal[None]).min(axis=1) <= F.OFF_PALETTE_DE).mean())
    assert raw < V.PALETTE_COVERAGE_MIN, raw


def test_the_correction_never_rescues_the_wrong_colourway():
    model = V.vessel_models(BASKET)[0]
    for wrong in ({"cream": "#E8C547", "wine": "#1F2A5A"},     # yellow and navy
                  {"cream": "#FAF6EB", "wine": "#2E6B3A"}):    # wine substituted by green
        data = _shaded_side([wrong[b] for b in model.wall_bands])
        v = V.verify_side(data, model)
        bad = [c for c in v if c["status"] == "FAIL"]
        assert bad and {c.get("code") for c in bad} & {"OFF_PALETTE_COLOUR",
                                                       "WRONG_COLOUR_LAYOUT"}, (wrong, v)


def test_the_images_board_lists_every_listing_with_runs_and_every_frame():
    from datetime import datetime, timezone

    from brambleloop.core.db import Database
    from brambleloop.visual import image_production as IP
    from brambleloop.visual.image_records import ImageCandidate, ImageProductionRun, ensure_tables

    tmp = tempfile.mkdtemp(prefix="images-board-")
    db = Database("sqlite:///" + str(Path(tmp) / "s.db"), scratch=True)
    db.create_all()
    ensure_tables(db)
    assert "market-basket-small" not in launch0.LAUNCH0_SLUGS
    now = datetime.now(timezone.utc)
    with db.session() as s:
        s.add(ImageProductionRun(run_key="mbs@1.3.0#r1", slug="market-basket-small",
                                 version="1.3.0", release="r1", listing="market-basket-small",
                                 stage="fidelity_gate", status="blocked",
                                 blocked_reason="product fidelity FAIL after 3 attempts",
                                 attempts_exhausted=True, updated_at=now))
        fid = {"status": "FAIL", "codes": ["OFF_PALETTE_COLOUR", "WRONG_COLOUR_LAYOUT"],
               "checks": [{"check": "basket:palette", "status": "FAIL"},
                          {"check": "basket:wall_bands", "status": "FAIL"},
                          {"check": "basket:rim", "status": "PASS"}]}
        for i in range(3):
            s.add(ImageCandidate(sha256=f"{i:064d}", run_key="mbs@1.3.0#r1",
                                 method="autonomous", provenance_kind="ai_generated",
                                 slug="market-basket-small", listing="market-basket-small",
                                 role="product_anchor", attempt=i + 1,
                                 technical_status="FAIL", outcome="rejected",
                                 checks={"product_truth": {"fidelity": fid}},
                                 failure_categories=["product_truth"], width=2048, height=2048))
        s.add(ImageCandidate(sha256="f" * 64, run_key="mbs@1.3.0#r1#owner", method="owner_manual",
                             provenance_kind="ai_generated_owner_submitted",
                             slug="market-basket-small", listing="market-basket-small",
                             role="hero", technical_status="UNKNOWN", outcome="unverified"))
        s.commit()
    board = IP.status_board(db)
    names = [p["listing"] for p in board["products"]]
    assert set(launch0.LAUNCH0_SLUGS) <= set(names)
    mbs = next(p for p in board["products"] if p["listing"] == "market-basket-small")
    assert mbs["state"] == "blocked" and mbs["frame_count"] == 4
    keys = [r["run_key"] for r in mbs["runs"]]
    assert keys == ["mbs@1.3.0#r1", "mbs@1.3.0#r1#owner"], keys
    frames = mbs["runs"][0]["frames"]
    assert len(frames) == 3
    f = frames[0]
    assert f["image_url"] == f"/api/cc/images/candidates/{f['candidate_id']}/image"
    assert f["technical_status"] == "FAIL"
    assert {"OFF_PALETTE_COLOUR", "WRONG_COLOUR_LAYOUT"} <= set(f["codes"])
    assert f["failed_checks"] == ["basket:palette", "basket:wall_bands"]
    assert mbs["runs"][1]["state"] == "owner_submitted"


def test_the_images_page_reads_the_body_not_the_get_envelope():
    views = ROOT / "src/brambleloop/app/command_center/static/js/views"
    page = (views / "images.js").read_text()
    studio = (views / "_visual_studio.js").read_text()
    api = (ROOT / "src/brambleloop/app/command_center/static/js/api.js").read_text()
    # api.get resolves an envelope; the page must unwrap it for every GET it reads
    assert "return { data: body, stale: false, fetchedAt }" in api
    assert "const board = body(boardRes);" in page
    assert "body(await api.imagesCard(" in page and "body(await api.experimentCard(" in page
    assert "v = body(await api.visualStudio())" in studio
    assert "body(await api.visualEvidence(" in studio
    # each run and every frame are shown, with verdict and codes
    assert "p.runs.map(runBlock)" in page and "frames.map(candidateThumb)" in page
    assert "f.codes.join" in page and "f.image_url" in page
    sw = (ROOT / "src/brambleloop/app/command_center/static/sw.js").read_text()
    assert 'const VERSION = "cc-shell-v48";' in sw, "shell JS changed: the cache version moves"


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                fails += 1
                print("FAIL", name, type(e).__name__, str(e)[:400])
                traceback.print_exc()
    print(f"{fails} failed")
    sys.exit(1 if fails else 0)
