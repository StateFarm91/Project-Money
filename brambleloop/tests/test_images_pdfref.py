"""ENG-IMAGES-PDFREF: the certified pattern PDF's pages as FLUX 3 reference images.

The owner's hand method ("PDF pages as images"), made deterministic: the release's certified
premium PDF is rasterised (cover, colour key, chart pages ...) and sent as FLUX 3 Image
references in the documented `images` field, after the four CIR renders, in a fixed order.

No network, no spend: the stub renderer, an injected CIR loader and an injected PDF loader. The
request body is built by the real `gateway.images._request_for` and checked against the
documented contract; the paid-call replay is the real `paid_calls` guard on a real job.

Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_images_pdfref.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import base64
import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

_WORK = Path(tempfile.mkdtemp(prefix="images-pdfref-"))
os.environ["BRAMBLELOOP_PDF_PAGE_CACHE"] = str(_WORK / "page-cache")

from brambleloop.creative import flux3_generator as FG  # noqa: E402
from brambleloop.creative import image_stages as S  # noqa: E402
from brambleloop.creative import pattern_refs as P  # noqa: E402
from brambleloop.creative import pdf_page_refs as PR  # noqa: E402
from brambleloop.gateway import flux_contract as F  # noqa: E402
from brambleloop.gateway import images as I  # noqa: E402
from brambleloop.products import launch0  # noqa: E402

CIR = launch0.cir_for("cloudline_blanket")
REL = P.release_hash_of(CIR)
SLUG, VER = CIR.slug, CIR.version
# A real certified-style Brambleloop pattern PDF (a basket) from the research build.
BASKET_PDF = (ROOT / "research/final_build/w4/customer_editions/market-basket-small-1.3.0/"
              "market-basket-small-1.3.0.pdf").read_bytes()


class _Capture(S.StubRenderer):
    """The stub renderer, also keeping each call's reference bytes and the exact FLUX 3 body
    `gateway.images._request_for` builds from them (the scratch dir is gone afterwards)."""

    def __call__(self, prompt, *, reference_urls, size, **kw):
        out = super().__call__(prompt, reference_urls=reference_urls, size=size, **kw)
        refs = list(reference_urls)
        provider = I.BY_KEY["flux-3-image"]
        url, headers, payload = I._request_for(provider, "dummy", prompt, refs, size)
        self.calls[-1].update(
            ref_sha256s=[hashlib.sha256(Path(r).read_bytes()).hexdigest() for r in refs],
            url=url, headers=headers, body=json.loads(payload),
            receipt=I.conditioning_receipt(provider, refs, payload))
        return out


def _gen(pdf=BASKET_PDF, renderer=None, loads=None):
    stub = renderer or _Capture()

    def load(slug, version, release):
        if loads is not None:
            loads.append((slug, version, release))
        return pdf
    g = FG.Flux3Generator(None, renderer=stub, cir_loader=lambda s, v: CIR,
                          anchor_lookup=lambda s, v, r: None, work_root=None,
                          pdf_loader=load)
    return g, stub


def _orchestrator_refs(prepared):
    """What image_production stores and hands back: kind, sha256, label and the bytes."""
    return [{"kind": r["kind"], "sha256": hashlib.sha256(r["data"]).hexdigest(),
             "label": r.get("label", ""), "data": r["data"]} for r in prepared]


def _texts(pdf):
    from brambleloop.visual.contents_frame import PDFIUM_LOCK, _pdfium

    pdfium = _pdfium()
    with PDFIUM_LOCK:
        doc = pdfium.PdfDocument(pdf)
        try:
            return PR._page_texts(doc)
        finally:
            doc.close()


# ----------------------------------------------------------------------------- page choice

def test_the_most_informative_pages_are_chosen_in_a_fixed_order():
    chosen = PR.select(_texts(BASKET_PDF))
    kinds = [c["kind"] for c in chosen]
    assert kinds[0] == "pdf_cover" and chosen[0]["index"] == 0
    assert kinds[1] == "pdf_colour_key"
    assert "pdf_chart" in kinds and len(chosen) <= PR.MAX_PAGES
    # the cover, the colour key (materials), the schematic and the round chart
    assert [c["index"] + 1 for c in chosen[:4]] == [1, 4, 3, 10], chosen
    assert len({c["index"] for c in chosen}) == len(chosen)            # no page twice
    assert PR.select(_texts(BASKET_PDF)) == chosen                     # pure


def test_a_word_in_a_paragraph_never_decides_a_page_kind():
    body = ("A long paragraph that mentions the chart and the palette and the materials "
            "in passing, as body text does, without being any of those pages at all.")
    assert PR.classify(3, f"HEADER\nTerms and support\n{body}") is None
    assert PR.classify(3, "HEADER\nCHART AND KEYS\nChart\n") == "pdf_chart"
    assert PR.classify(3, "HEADER\nChart symbols\n") == "pdf_chart_key"
    assert PR.classify(3, "HEADER\nWHAT YOU NEED\nMaterials\n") == "pdf_colour_key"


# ----------------------------------------------------------------------------- determinism

def test_the_same_pdf_gives_the_same_page_hashes():
    PR.clear_memo()
    shutil.rmtree(_WORK / "page-cache", ignore_errors=True)
    first = PR.pages_for(BASKET_PDF)
    assert first["cached"] is False
    fresh = PR._render(BASKET_PDF)                           # a second, independent render
    assert [p["sha256"] for p in fresh["pages"]] == [p["sha256"] for p in first["pages"]]
    assert [p["data"] for p in fresh["pages"]] == [p["data"] for p in first["pages"]]
    for p in first["pages"]:
        assert hashlib.sha256(p["data"]).hexdigest() == p["sha256"]
        assert max(p["px"]) == PR.LONG_SIDE_PX
        w, h = p["px"]
        lo, hi = F.EXACT_SIDE_PX
        assert lo <= min(w, h) and max(w, h) <= hi and w * h <= F.EXACT_MAX_PIXELS_WITH_REFERENCES
    assert first["pdf_sha256"] == hashlib.sha256(BASKET_PDF).hexdigest()


def test_pages_are_cached_per_pdf_hash_and_never_re_rendered():
    PR.clear_memo()
    shutil.rmtree(_WORK / "page-cache", ignore_errors=True)
    first = PR.pages_for(BASKET_PDF)
    real = PR._render
    try:
        PR._render = lambda pdf: (_ for _ in ()).throw(AssertionError("re-rendered"))
        again = PR.pages_for(BASKET_PDF)                     # in-process cache
        assert again["cached"] is True
        PR.clear_memo()
        disk = PR.pages_for(BASKET_PDF)                      # the on-disk cache, verified
        assert disk["cached"] is True
        assert [p["sha256"] for p in disk["pages"]] == [p["sha256"] for p in first["pages"]]
    finally:
        PR._render = real
    # a tampered cache file is discarded and re-rendered to the same bytes
    PR.clear_memo()
    d = PR._entry_dir(first["pdf_sha256"])
    victim = d / f"page-{first['pages'][0]['page']:03d}.png"
    victim.write_bytes(b"not the page")
    healed = PR.pages_for(BASKET_PDF)
    assert healed["cached"] is False
    assert [p["sha256"] for p in healed["pages"]] == [p["sha256"] for p in first["pages"]]
    man = json.loads((d / "manifest.json").read_text())
    assert man["pdf_sha256"] == first["pdf_sha256"] and man["render_version"] == PR.RENDER_VERSION


# ----------------------------------------------------------------------------- the request

def test_prepared_references_carry_the_pdf_pages_as_pattern_derived_provenance():
    g, _ = _gen()
    prepared = g.prepare_references(slug=SLUG, version=VER, release=REL)
    pages = [r for r in prepared if PR.is_page_ref(r)]
    cir = [r for r in prepared if not PR.is_page_ref(r)]
    assert len(cir) == len(S.PRODUCT_ROLES)
    assert pages and all(r["kind"] == "pattern_derived" for r in pages)
    entry = PR.pages_for(BASKET_PDF)
    assert [hashlib.sha256(r["data"]).hexdigest() for r in pages] == \
        [p["sha256"] for p in entry["pages"]]
    assert [r["label"].split("|")[0] for r in pages] == \
        [f"{p['kind']}:{p['page']}" for p in entry["pages"]]
    # what image_production records on the candidate: hash, kind, source, label
    from brambleloop.visual.image_production import _ref_provenance

    rows = [_ref_provenance(r) for r in _orchestrator_refs(prepared)]
    assert [r["sha256"] for r in rows if r.get("source") == PR.SOURCE] == \
        [p["sha256"] for p in entry["pages"]]
    assert all(r["kind"] == "pattern_derived" for r in rows if r.get("source"))
    # the CIR-reference gate still counts exactly the four CIR renders
    assert [r["sha256"] for r in rows if r["kind"] == "pattern_derived"
            and not PR.is_page_ref(r)] == [hashlib.sha256(r["data"]).hexdigest() for r in cir]


def test_the_request_carries_the_pages_in_the_documented_images_field_in_order():
    g, stub = _gen()
    refs = _orchestrator_refs(g.prepare_references(slug=SLUG, version=VER, release=REL))
    out = g.generate(stage="product_generation", role=FG.ANCHOR_ROLE, brief="", references=refs,
                     outfit=None, attempt=1)
    sent = stub.calls[0]["refs"]
    entry = PR.pages_for(BASKET_PDF)
    n_cir = len(S.PRODUCT_ROLES)
    want = [p["sha256"] for p in entry["pages"]][:F.MAX_REFERENCES - n_cir]
    assert stub.calls[0]["ref_sha256s"][n_cir:] == want
    assert len(sent) <= F.MAX_REFERENCES
    # the receipt names each page's position, kind, page number and field
    rec = out["identity_evidence"]
    assert [p["sha256"] for p in rec["pdf_reference_pages"]] == want
    assert [p["position"] for p in rec["pdf_reference_pages"]] == \
        list(range(n_cir + 1, n_cir + 1 + len(want)))
    assert [p["field"] for p in rec["pdf_reference_pages"]] == \
        [f"images[{i}]" for i in range(n_cir, n_cir + len(want))]
    assert rec["pdf_sha256"] == hashlib.sha256(BASKET_PDF).hexdigest()
    assert rec["input_sha256s"][n_cir:] == want
    # the prompt's reference map names the PDF pages by position
    prompt = stub.calls[0]["prompt"]
    assert f"image {n_cir + 1} = {PR.LABELS['pdf_cover']}" in prompt
    # the body the gateway actually builds for FLUX 3 Image: `images`, base64, in that order
    body = stub.calls[0]["body"]
    F.validate_request(body)
    assert not any(k.startswith("input_image") for k in body), sorted(body)
    imgs = body["images"]
    assert len(imgs) == len(sent) <= F.MAX_REFERENCES
    assert [hashlib.sha256(base64.b64decode(b)).hexdigest() for b in imgs[n_cir:]] == want
    receipt = stub.calls[0]["receipt"]
    assert receipt["proven"] and receipt["transmitted"] == len(sent)
    assert [r["field"] for r in receipt["references"]][n_cir:] == \
        [f"images[{i}]" for i in range(n_cir, len(sent))]


def test_the_order_is_deterministic_across_scratch_directories():
    a, sa = _gen()
    b, sb = _gen()
    for g in (a, b):
        refs = _orchestrator_refs(g.prepare_references(slug=SLUG, version=VER, release=REL))
        g.generate(stage="product_generation", role=FG.ANCHOR_ROLE, brief="", references=refs,
                   outfit=None, attempt=1)
    assert sa.calls[0]["ref_sha256s"] == sb.calls[0]["ref_sha256s"]
    assert sa.calls[0]["body"] == sb.calls[0]["body"]          # byte-identical request body
    assert sa.calls[0]["prompt"] == sb.calls[0]["prompt"]


def test_pages_never_displace_a_reference_or_exceed_the_provider_limit():
    g, stub = _gen(renderer=_Capture(reference_limit=6))
    refs = _orchestrator_refs(g.prepare_references(slug=SLUG, version=VER, release=REL))
    g.generate(stage="product_generation", role=FG.ANCHOR_ROLE, brief="", references=refs,
               outfit=None, attempt=1)
    sent = stub.calls[0]["refs"]
    assert len(sent) == 6
    cir = [r["sha256"] for r in refs if not PR.is_page_ref(r)]
    assert stub.calls[0]["ref_sha256s"][:4] == cir


def test_a_substituted_page_is_refused_before_anything_is_sent():
    g, stub = _gen()
    refs = _orchestrator_refs(g.prepare_references(slug=SLUG, version=VER, release=REL))
    i = next(k for k, r in enumerate(refs) if PR.is_page_ref(r))
    forged = b"\x89PNG not the certified page"
    refs[i] = {**refs[i], "data": forged, "sha256": hashlib.sha256(forged).hexdigest()}
    try:
        g.generate(stage="product_generation", role=FG.ANCHOR_ROLE, brief="", references=refs,
                   outfit=None, attempt=1)
    except FG.GeneratorRefused:
        pass
    else:
        raise AssertionError("a forged PDF page was accepted")
    assert stub.calls == []


def test_without_a_certified_pdf_the_request_is_the_cir_references_alone():
    g, stub = _gen(pdf=None)
    prepared = g.prepare_references(slug=SLUG, version=VER, release=REL)
    assert not any(PR.is_page_ref(r) for r in prepared)
    g.generate(stage="product_generation", role=FG.ANCHOR_ROLE, brief="",
               references=_orchestrator_refs(prepared), outfit=None, attempt=1)
    assert len(stub.calls[0]["refs"]) == len(S.PRODUCT_ROLES)


# ----------------------------------------------------------------------------- spend

def test_a_redrive_with_the_same_pages_in_another_scratch_dir_makes_no_second_paid_call():
    from brambleloop.agents.registry import Registry
    from brambleloop.core.db import Database
    from brambleloop.gateway import paid_calls
    from brambleloop.queue.durable import JobQueue

    db = Database("sqlite://")
    db.create_all()
    Registry(db).seed_defaults()
    job = JobQueue(db).enqueue("publishing", "visual.image_production", {},
                               idempotency_key="pdfref-redrive")
    entry = PR.pages_for(BASKET_PDF)
    provider = I.BY_KEY["flux-3-image"]
    calls = []

    def paid():
        calls.append(1)
        out = _WORK / f"render-{len(calls)}.png"
        out.write_bytes(entry["pages"][0]["data"])
        return {"path": str(out), "sha256": entry["pages"][0]["sha256"], "cad": 0.137}

    results = []
    for attempt in (1, 2):
        # each attempt is a re-execution of the same job, in its own scratch directory
        with paid_calls.job_scope(db, job):
            scratch = _WORK / f"attempt-{attempt}"
            files = PR.write_pages(entry, scratch / "pdf-pages")
            refs = [f["path"] for f in files]
            results.append(I._guarded_render(
                provider, "the same prompt", refs, S.PRODUCT_SIZE, None,
                str(scratch / "out"), {"estimate_cad": 0.137}, "publishing", {}, paid))
    assert len(calls) == 1, "a redrive bought the same render twice"
    assert results[1].get("replayed") is True and results[1]["cad"] == 0.0
    # the fingerprint is the references' content, not their paths
    fa = I._render_fp(provider, "p", [f["path"] for f in PR.write_pages(entry, _WORK / "x")],
                      S.PRODUCT_SIZE, None)
    fb = I._render_fp(provider, "p", [f["path"] for f in PR.write_pages(entry, _WORK / "y")],
                      S.PRODUCT_SIZE, None)
    assert fa == fb


def test_the_caps_and_the_regional_host_are_unchanged():
    from brambleloop.visual import image_production as IP

    assert F.DEFAULT_BFL_HOST == "api.us.bfl.ai"
    assert F.ENDPOINT == "https://api.us.bfl.ai/v1/flux-3-image"
    g, stub = _gen()
    refs = _orchestrator_refs(g.prepare_references(slug=SLUG, version=VER, release=REL))
    g.generate(stage="product_generation", role=FG.ANCHOR_ROLE, brief="", references=refs,
               outfit=None, attempt=1)
    url, headers = stub.calls[0]["url"], stub.calls[0]["headers"]
    assert url == "https://api.us.bfl.ai/v1/flux-3-image" and set(headers) == {"x-key"}
    assert IP.MAX_SPEND_CAD_PER_GALLERY == 6.00   # D-OWNER-PHOTO-BUDGET (was 2.00)
    from brambleloop.gateway import paid_provider_gate as G

    assert G.GALLERY_CAD_CAP == 6.00 and G.DAILY_IMAGE_CAP == 120 and G.GALLERY_IMAGE_CAP == 60
    # references are not charged on FLUX 3: the per-call price is the 2k tier, pages or not
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
