"""ENG-MANUAL-METHOD: the owner's October 28 manual FLUX 3 method inside the factory.

research/MANUAL-METHOD-COMPARISON.md compares the hand method with the factory, request by
request. These tests pin the generalised method (manual_method/1) on three different products,
each from its OWN certified CIR and PDF: the hexagon basket (a vessel), the hexagon coaster set
(round, flat) and the Cloudline baby blanket (flat rows).

No network, no spend: the stub renderer, injected CIR/PDF loaders and anchor lookup. The FLUX 3
body is built by the real `gateway.images._request_for` and checked against the documented
contract.

Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_manual_method.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import hashlib
import json
import os
import shutil
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

_WORK = Path(tempfile.mkdtemp(prefix="manual-method-"))
os.environ["BRAMBLELOOP_PDF_PAGE_CACHE"] = str(_WORK / "page-cache")

from brambleloop.creative import flux3_generator as FG  # noqa: E402
from brambleloop.creative import image_stages as S  # noqa: E402
from brambleloop.creative import manual_method as MM  # noqa: E402
from brambleloop.creative import pattern_refs as P  # noqa: E402
from brambleloop.creative import pdf_page_refs as PR  # noqa: E402
from brambleloop.gateway import flux_contract as F  # noqa: E402
from brambleloop.gateway import images as I  # noqa: E402
from brambleloop.products import launch0  # noqa: E402
from brambleloop.visual import canonical  # noqa: E402
from brambleloop.visual import image_production as IP  # noqa: E402

_EDITIONS = ROOT / "research/final_build/w4/customer_editions"


def _blanket_pdf(cir) -> bytes:
    from brambleloop.publish.pdf import build_pattern_pdf

    return build_pattern_pdf(cir, terminology="US", released_on=date(2026, 10, 28)).pdf_bytes


# key -> (CIR, the certified-style PDF whose pages are sent)
_PRODUCTS: dict = {}


def _product(key: str):
    if key not in _PRODUCTS:
        if key == "basket":
            cir = launch0.cir_for("basket_small")
            pdf = (_EDITIONS / "market-basket-small-1.3.0/market-basket-small-1.3.0.pdf"
                   ).read_bytes()
        elif key == "coaster":
            cir = launch0.cir_for("hexagon_coasters")
            pdf = (_EDITIONS / "hexagon-coaster-set-1.2.1/hexagon-coaster-set-1.2.1.pdf"
                   ).read_bytes()
        else:
            cir = launch0.cir_for("cloudline_blanket")
            pdf = _blanket_pdf(cir)
        _PRODUCTS[key] = (cir, pdf)
    return _PRODUCTS[key]


class _Capture(S.StubRenderer):
    def __call__(self, prompt, *, reference_urls, size, **kw):
        out = super().__call__(prompt, reference_urls=reference_urls, size=size, **kw)
        refs = list(reference_urls)
        url, headers, payload = I._request_for(I.BY_KEY["flux-3-image"], "dummy", prompt, refs,
                                               size)
        body = json.loads(payload)
        F.validate_request(body)
        self.calls[-1].update(body=body, ref_sha256s=[
            hashlib.sha256(Path(r).read_bytes()).hexdigest() for r in refs])
        return out


def _gen(key: str, anchor=None):
    cir, pdf = _product(key)
    stub = _Capture()
    box = {"a": anchor}
    g = FG.Flux3Generator(None, renderer=stub, cir_loader=lambda s, v: cir,
                          anchor_lookup=lambda s, v, r, run_key=None: box["a"],
                          pdf_loader=lambda s, v, r: pdf)
    rel = P.release_hash_of(cir)
    refs = [{"kind": r["kind"], "sha256": hashlib.sha256(r["data"]).hexdigest(),
             "label": r.get("label", ""), "data": r["data"],
             **({"source": r["source"]} if r.get("source") else {})}
            for r in g.prepare_references(slug=cir.slug, version=cir.version, release=rel)]
    return g, stub, refs, box, cir


def _prior(label: str, data: bytes) -> dict:
    return {"kind": "prior_candidate", "label": label,
            "sha256": hashlib.sha256(data).hexdigest(), "data": data}


def _laura() -> list[dict]:
    out = []
    for frame, sha in canonical.CURRENT_REFERENCE_HASHES.items():
        data = Path(canonical.reference_file(frame)).read_bytes()
        out.append({"kind": "laura_canonical", "sha256": sha, "frame": frame, "data": data})
    return out


OUTFIT = {"outfit_id": "mm-outfit", "description": "a sage blouse and cream trousers",
          "garments": {"top_or_dress": "soft sage-green blouse",
                       "lower": "cream tailored trousers"}}


def _master(key: str, status: str = "PASS"):
    """A product master made by the method itself, then 'accepted' with `status`."""
    g, stub, refs, box, cir = _gen(key)
    out = g.generate(stage="product_generation", role=FG.ANCHOR_ROLE, brief="",
                     references=refs, outfit=None, attempt=1)
    return {"data": out["data"], "sha256": hashlib.sha256(out["data"]).hexdigest(),
            "status": status, "checker": "test"}, out


# ----------------------------------------------------------------------- product master

def test_the_product_master_conditions_on_the_pdf_pages_only_never_the_cir_diagrams():
    for key in ("basket", "coaster", "blanket"):
        g, stub, refs, _box, cir = _gen(key)
        out = g.generate(stage="product_generation", role=FG.ANCHOR_ROLE, brief="",
                         references=refs, outfit=None, attempt=1)
        call = stub.calls[-1]
        pages = [r["sha256"] for r in refs if PR.is_page_ref(r)]
        cir_refs = [r["sha256"] for r in refs if r["kind"] == "pattern_derived"
                    and not PR.is_page_ref(r)]
        assert len(cir_refs) == len(S.PRODUCT_ROLES)          # still handed in: they bind
        assert call["ref_sha256s"] == pages[:F.MAX_REFERENCES], key
        assert not set(call["ref_sha256s"]) & set(cir_refs), key
        assert call["body"]["aspect_ratio"] == "1:1" and call["body"]["resolution"] == "2k"
        assert "seed" not in call["body"] and "input_image" not in call["body"]
        ev = out["identity_evidence"]
        assert ev["method"] == MM.MANUAL_METHOD and ev["prompt_text"] == call["prompt"]
        assert out["prompt"] == call["prompt"]                   # the exact text is recorded
        assert ev["input_sha256s"] == call["ref_sha256s"]
        assert ev["output_sha256"] == hashlib.sha256(out["data"]).hexdigest()
        assert ev["aspect_ratio"] == "1:1" and ev["resolution"] == "2k" and "seed" in ev
        assert [p["position"] for p in ev["pdf_reference_pages"]] == list(
            range(1, len(call["ref_sha256s"]) + 1))
        text = call["prompt"]
        assert text.startswith("Create one photorealistic product visualization")
        assert "Image 1 is a page of the certified pattern PDF" in text
        assert "Laura" not in text and "No person, hands, props" in text
        assert "Output one square image" in text
        assert "certified product layout" not in text            # no diagram reference


def test_the_prose_spec_is_each_products_own_cir():
    rules = {k: S.release_from_cir(_product(k)[0], release_hash=P.release_hash_of(
        _product(k)[0]), out_dir=_WORK / k).rules for k in ("basket", "coaster", "blanket")}
    basket = MM.colour_sequence(rules["basket"])
    v = rules["basket"]["vessel"]
    want = ", ".join(f"{b['rounds']} {b['colour']} round{'s' if b['rounds'] != 1 else ''}"
                     for b in v["wall_bands"])
    assert f"Reading the wall from bottom to top: {want}." in basket
    coaster = MM.colour_sequence(rules["coaster"])
    assert coaster.startswith("Reading the rounds from the centre outward: 5 cream rounds, "
                              "1 wine round, 1 cream round."), coaster
    blanket = MM.colour_sequence(rules["blanket"])
    # mixed stitch heights: the surface is the chart's; the worked yarn order is still stated
    assert rules["blanket"]["fabric"]["colour_layout"] == "charted"
    assert blanket.startswith("The colourwork is exactly as charted on the pattern pages"), blanket
    assert ("worked in this colour order, from the first: 6 cream rows, then (2 ink rows, "
            "2 cream rows) repeated") in blanket, blanket
    assert "plain stripes" in blanket
    # nothing of one product leaks into another's spec
    assert "wall" not in coaster and "hexagon" not in MM.product_spec(rules["blanket"])
    assert "wine" not in blanket and "ink" not in basket
    spec = MM.product_spec(rules["coaster"])
    assert "4 pieces" in spec and "dk cotton" in spec and "5 mm hook" in spec
    assert "worsted cotton" in MM.product_spec(rules["basket"])
    # the surface is light and editorial, yet far from every yarn colour
    for k, r in rules.items():
        c = MM.composition(r)
        assert all(S.delta_e(c["surface_hex"], x["hex"]) >= MM.MIN_DELTA_E
                   for x in r["colours"] if x.get("hex")), k
    assert MM.composition(rules["basket"])["surface"] == "light natural oak"


def test_a_vessel_master_keeps_the_gates_two_views():
    g, stub, refs, _box, _cir = _gen("basket")
    g.generate(stage="product_generation", role=FG.ANCHOR_ROLE, brief="", references=refs,
               outfit=None, attempt=1)
    g.generate(stage="product_generation", role=FG.ANCHOR_SIDE_ROLE, brief="",
               references=refs, outfit=None, attempt=1)
    top, side = stub.calls[-2]["prompt"], stub.calls[-1]["prompt"]
    assert "straight down at 90 degrees" in top and "level with the middle of the wall" in side


# ----------------------------------------------------------------------- correction

def test_a_correction_edits_the_failed_candidate_naming_the_gates_defect():
    for key in ("basket", "coaster", "blanket"):
        g, stub, refs, _box, _cir = _gen(key)
        first = g.generate(stage="product_generation", role=FG.ANCHOR_ROLE, brief="",
                           references=refs, outfit=None, attempt=1)
        failed = _prior(FG.CORRECTION_LABEL, first["data"])
        out = g.generate(stage="product_generation", role=FG.ANCHOR_ROLE, brief="",
                         references=refs + [failed], outfit=None, attempt=2,
                         repair={"codes": ["WRONG_COLOUR_LAYOUT"], "directives": []})
        call = stub.calls[-1]
        assert call["ref_sha256s"][0] == failed["sha256"], key       # image 1 = the candidate
        pages = [r["sha256"] for r in refs if PR.is_page_ref(r)]
        assert call["ref_sha256s"][1:] == pages[:F.MAX_REFERENCES - 1]
        assert call["prompt"].startswith("Edit image 1 only, to fix: the colour layout"), key
        assert "Keep the camera, lighting, background" in call["prompt"]
        ev = out["identity_evidence"]
        assert ev["correction_of"] == failed["sha256"]
        assert ev["correction_codes"] == ["WRONG_COLOUR_LAYOUT"]


def test_a_correction_with_no_nameable_defect_is_a_fresh_master_not_a_blind_edit():
    g, stub, refs, _box, _cir = _gen("coaster")
    first = g.generate(stage="product_generation", role=FG.ANCHOR_ROLE, brief="",
                       references=refs, outfit=None, attempt=1)
    g.generate(stage="product_generation", role=FG.ANCHOR_ROLE, brief="",
               references=refs + [_prior(FG.CORRECTION_LABEL, first["data"])], outfit=None,
               attempt=2, repair={"codes": ["identity_drift"], "directives": []})
    assert stub.calls[-1]["prompt"].startswith("Create one photorealistic product")
    assert hashlib.sha256(first["data"]).hexdigest() not in stub.calls[-1]["ref_sha256s"]


# ----------------------------------------------------------------------- lifestyle / styled

def test_lifestyle_is_the_canonical_three_then_the_accepted_master_then_the_campaign():
    anchor, _ = _master("basket")
    g, stub, refs, box, _cir = _gen("basket", anchor)
    side = b"side-view-bytes-of-the-accepted-pair"
    side_png = _png(side)
    campaign_png = _png(b"campaign")
    laura = _laura()
    pf = _prior(FG.PRODUCT_FRAME_LABEL, anchor["data"])
    out = g.generate(stage="lifestyle_generation", role="lifestyle",
                     brief="she places a folded cloth into it", outfit=OUTFIT, attempt=1,
                     references=refs + laura + [pf, _prior(FG.PRODUCT_SIDE_LABEL, side_png),
                                                _prior(FG.CAMPAIGN_LABEL, campaign_png)])
    call = stub.calls[-1]
    want = [r["sha256"] for r in laura] + [anchor["sha256"],
                                           hashlib.sha256(side_png).hexdigest(),
                                           hashlib.sha256(campaign_png).hexdigest()]
    assert call["ref_sha256s"] == want
    assert tuple(call["ref_sha256s"][:3]) == S.canonical_laura_hashes()
    t = call["prompt"]
    assert "Image 4 is the accepted product master" in t and "Image 6 is the approved " \
        "campaign image" in t
    assert "soft sage-green blouse" in t and "Preserve this outfit" in t
    assert "Laura's own home" in t                    # the house rule (laura_home) still holds
    assert out["identity_evidence"]["accepted_product_frame_sha256"] == anchor["sha256"]
    # an anchor that is not accepted is refused before any request
    box["a"] = {**anchor, "status": "FAIL"}
    n = len(stub.calls)
    try:
        g.generate(stage="lifestyle_generation", role="lifestyle", brief="", outfit=OUTFIT,
                   attempt=1, references=refs + laura + [pf])
        raise AssertionError("a FAILed master conditioned a lifestyle frame")
    except FG.GeneratorRefused:
        pass
    assert len(stub.calls) == n


def _png(seed: bytes) -> bytes:
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (64, 64), tuple(hashlib.sha256(seed).digest()[:3])).save(buf, "PNG")
    return buf.getvalue()


def test_a_styled_frame_is_the_master_then_the_campaign_with_category_props():
    seen = {}
    for key in ("basket", "coaster"):
        anchor, _ = _master(key)
        g, stub, refs, _box, _cir = _gen(key, anchor)
        camp = _png(key.encode())
        g.generate(stage="remaining_roles", role="size", brief="beside everyday objects",
                   outfit=None, attempt=1,
                   references=refs + [_prior(FG.CAMPAIGN_LABEL, camp)])
        call = stub.calls[-1]
        assert call["ref_sha256s"] == [anchor["sha256"], hashlib.sha256(camp).hexdigest()]
        assert not set(call["ref_sha256s"]) & set(S.canonical_laura_hashes())
        assert "Image 1 is the accepted product master" in call["prompt"]
        assert "No person" in call["prompt"]
        seen[key] = call["prompt"]
    assert "tea towels" in seen["basket"] and "mug of tea" in seen["coaster"]
    assert "Reading the wall" in seen["basket"] and "Reading the wall" not in seen["coaster"]


# ----------------------------------------------------------------------- method version

def test_the_generation_method_version_names_the_manual_method():
    m = IP.generation_method()
    assert m["image_method"] == MM.MANUAL_METHOD == IP.MANUAL_METHOD_VERSION
    assert m["version"].endswith("|" + MM.MANUAL_METHOD)
    assert IP.current_method_version() == m["version"]
    # every run made before this method reads as an older method, so it is redriven once
    assert IP.candidate_method_version({IP.METHOD_KEY: {"version": m["version"].rsplit(
        "|", 1)[0]}}) != m["version"]
    assert FG.CORRECTION_LABEL == IP.CORRECTION_LABEL
    assert FG.PRODUCT_SIDE_LABEL == IP.PRODUCT_SIDE_LABEL
    assert FG.CAMPAIGN_LABEL == IP.CAMPAIGN_LABEL


def test_caps_are_unchanged():
    assert IP.MAX_SPEND_CAD_PER_GALLERY == 2.00 and IP.MAX_GENERATION_CALLS == 12
    assert IP.MAX_ATTEMPTS_PER_ROLE == 3
    g = _gen("coaster")[0]
    assert abs(g.max_cost_cad_per_call - round(I.BFL3_TIER_USD["2k"] * I.USD_TO_CAD, 6)) < 1e-9


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failures = 0
    for name, fn in tests:
        try:
            fn()
            print("OK  ", name)
        except Exception as exc:  # noqa: BLE001
            failures += 1
            import traceback

            traceback.print_exc()
            print("FAIL", name, type(exc).__name__, str(exc)[:500])
    print(f"{len(tests) - failures}/{len(tests)} passing")
    shutil.rmtree(_WORK, ignore_errors=True)
    sys.exit(bool(failures))
