"""W4-FLUXAPI: deterministic pattern references (Cloudline) and the three generation stages.

No network and no spend: the stages run on `StubRenderer`, and the paid renderer
(`flux3_renderer` -> `images.generate`) runs on the mock BFL transport from
`test_w4_fluxapi`, which captures every outbound body.

Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_w4_fluxstages.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import base64
import hashlib
import io
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from PIL import Image  # noqa: E402

from brambleloop.core.models import CostEntry  # noqa: E402
from brambleloop.core.resilience import TransientError  # noqa: E402
from brambleloop.creative import image_stages as S  # noqa: E402
from brambleloop.creative import pattern_refs as P  # noqa: E402
from brambleloop.gateway import anthropic as gw  # noqa: E402
from brambleloop.gateway import images as I  # noqa: E402
from brambleloop.gateway import prompts, routing  # noqa: E402
from brambleloop.products import launch0  # noqa: E402

from test_w4_fluxapi import ENV, Transport, _db, _reservations  # noqa: E402

_WORK = Path(tempfile.mkdtemp(prefix="w4-fluxstages-"))
CIR = launch0.cir_for("cloudline_blanket")
RELEASE_HASH = P.release_hash_of(CIR)
_RELEASE: list = []


def _release() -> S.Release:
    if not _RELEASE:
        _RELEASE.append(S.release_from_cir(CIR, release_hash=RELEASE_HASH,
                                           out_dir=_WORK / "refs"))
    return _RELEASE[0]


def _png(name: str, rgb=(200, 150, 120), px: int = 300) -> str:
    buf = io.BytesIO()
    Image.new("RGB", (px, px), rgb).save(buf, format="PNG")
    p = _WORK / name
    p.write_bytes(buf.getvalue())
    return str(p)


def _no_network():
    def refuse(*a, **k):
        raise AssertionError("no network in this test")
    saved = (I._post, I._get)
    I._post = I._get = refuse
    return saved


# -- pattern references ----------------------------------------------------------------------
def test_cloudline_pattern_refs_are_99x100_bound_to_the_release_and_fingerprinted():
    saved = _no_network()
    try:
        m = P.build(CIR, release_hash=RELEASE_HASH, out_dir=_WORK / "a")
    finally:
        I._post, I._get = saved
    assert m["slug"] == "cloudline-baby-blanket" and m["release_hash"] == RELEASE_HASH
    assert m["grid"]["stitches_across"] == 99 and m["grid"]["rows"] == 100
    assert m["grid"]["repeat"][0] == 9 and m["cost_cad"] == 0.0
    assert [r["role"] for r in m["references"]] == list(P.ROLES)
    for r in m["references"]:
        raw = Path(r["path"]).read_bytes()
        assert raw.startswith(b"\x89PNG") and hashlib.sha256(raw).hexdigest() == r["sha256"]
        assert RELEASE_HASH[:12] in Path(r["path"]).name
    assert P.verify(m)["ok"]
    stored = json.loads(next((_WORK / "a").glob("*-pattern-refs.json")).read_text())
    assert stored["manifest_sha256"] == m["manifest_sha256"]


def test_pattern_refs_are_deterministic_byte_for_byte():
    a = P.build(CIR, release_hash=RELEASE_HASH, out_dir=_WORK / "d1")
    b = P.build(CIR, release_hash=RELEASE_HASH, out_dir=_WORK / "d2")
    assert [r["sha256"] for r in a["references"]] == [r["sha256"] for r in b["references"]]
    assert a["manifest_sha256"] == b["manifest_sha256"]


def test_layout_has_the_twins_proportion_and_the_motif_is_enlarged():
    m = P.build(CIR, release_hash=RELEASE_HASH, out_dir=_WORK / "p")
    by = {r["role"]: r for r in m["references"]}
    w, h = by["layout"]["width"], by["layout"]["height"]
    assert abs(h / w - 96.4 / 79.2) < 0.01, (w, h)          # portrait, like the blanket
    mc, mr = m["grid"]["motif_block"]
    assert mc == 18 and by["motif"]["width"] >= mc * 40     # two repeats, big cells
    with Image.open(by["layout"]["path"]) as im:
        colours = {c for _n, c in im.convert("RGB").getcolors(1 << 20)}
    assert (0x1A, 0x2B, 0x3C) in colours and (0xFA, 0xF6, 0xEB) in colours


def test_a_release_hash_for_other_content_is_refused():
    for bad in ("", "0" * 64):
        try:
            P.build(CIR, release_hash=bad, out_dir=_WORK / "bad")
            raise AssertionError(bad)
        except P.PatternRefsRefused:
            pass


def test_verify_catches_changed_bytes():
    m = P.build(CIR, release_hash=RELEASE_HASH, out_dir=_WORK / "t")
    Path(m["references"][1]["path"]).write_bytes(b"\x89PNG tampered")
    v = P.verify(m)
    assert not v["ok"] and "motif: bytes changed" in v["problems"]


# -- stages on the stub ----------------------------------------------------------------------
def test_prompts_are_pinned_in_the_registry():
    for p in (S.PRODUCT_ONLY, S.LIFESTYLE, S.VARIANT):
        assert prompts.get(p.ref) is p and len(p.sha256) == 64
    try:
        prompts.register(prompts.Prompt(name="image.product_only", version="1", system="",
                                        template="edited", output_schema=("image",),
                                        max_output_tokens=1))
        raise AssertionError("a released image prompt must be immutable")
    except prompts.PromptIsImmutable:
        pass


def test_product_only_conditions_on_the_three_pattern_refs_and_returns_a_receipt():
    rel = _release()
    stub = S.StubRenderer()
    c = S.product_only(rel, renderer=stub, work_dir=str(_WORK / "po"))
    (call,) = stub.calls
    assert call["refs"] == list(rel.pattern_refs) and call["size"] == S.PRODUCT_SIZE
    assert call["agent"] == S.AGENT and call["purpose"] == "image.product_only"
    r = c.receipt
    assert r["input_sha256s"] == list(rel.pattern_ref_sha256s)
    assert r["prompt_ref"] == "image.product_only@1" and r["prompt_sha256"]
    assert r["release_hash"] == RELEASE_HASH == c.release_hash
    assert c.sha256 == hashlib.sha256(Path(c.path).read_bytes()).hexdigest()
    assert r["output_sha256"] == c.sha256 and r["attempts"] == 1
    for k in ("model", "task_id", "seed", "cost_cad", "latency_ms"):
        assert k in r, k
    assert "Cloudline" in call["prompt"] and "79 x 96 cm" in call["prompt"]


def test_lifestyle_orders_product_laura_outfit_and_refuses_bad_inputs():
    rel = _release()
    stub = S.StubRenderer()
    prod = S.product_only(rel, renderer=stub, work_dir=str(_WORK / "ls"))
    laura = [_png(f"laura{i}.png", (100 + i, 90, 80)) for i in range(3)]
    outfit = {"id": "outfit-07", "description": "an oatmeal linen dress",
              "image": _png("outfit.png", (10, 200, 10))}
    c = S.lifestyle(rel, prod, laura, outfit, renderer=stub, work_dir=str(_WORK / "ls"))
    call = stub.calls[-1]
    assert call["refs"] == [prod.path, *laura, outfit["image"]]
    assert "Images 2 to 4" in call["prompt"] and "outfit from image 5" in call["prompt"]
    assert c.role == "lifestyle:outfit-07" and len(c.receipt["input_sha256s"]) == 5
    for bad in ([], laura + [laura[0]]):
        try:
            S.lifestyle(rel, prod, bad, outfit, renderer=stub, work_dir=str(_WORK / "ls"))
            raise AssertionError(len(bad))
        except S.StageRefused:
            pass
    other = S.Candidate("product_only", "x", prod.path, prod.sha256, "f" * 64)
    try:
        S.lifestyle(rel, other, laura, outfit, renderer=stub, work_dir=str(_WORK / "ls"))
        raise AssertionError("cross-release candidate")
    except S.StageRefused:
        pass


def test_variant_is_a_single_reference_edit_with_a_closed_role():
    rel = _release()
    stub = S.StubRenderer()
    prod = S.product_only(rel, renderer=stub, work_dir=str(_WORK / "v"))
    v = S.variant(rel, prod, "detail_closeup", renderer=stub, work_dir=str(_WORK / "v"))
    assert stub.calls[-1]["refs"] == [prod.path] and v.receipt["prompt_ref"] == "image.variant@1"
    w = S.variant(rel, prod, "wardrobe_change", "a navy cardigan", renderer=stub,
                  work_dir=str(_WORK / "v"))
    assert "a navy cardigan" in stub.calls[-1]["prompt"] and w.role == "wardrobe_change"
    for role, text in (("make_it_pop", ""), ("wardrobe_change", ""),
                       ("detail_closeup", "x" * (S.MAX_EDIT_CHARS + 1))):
        try:
            S.variant(rel, prod, role, text, renderer=stub, work_dir=str(_WORK / "v"))
            raise AssertionError(role)
        except S.StageRefused:
            pass


def test_attempts_are_bounded_and_only_transient_failures_retry():
    rel = _release()
    stub = S.StubRenderer(fail_with=[TransientError("503"), TransientError("503")])
    try:
        S.product_only(rel, renderer=stub, work_dir=str(_WORK / "b"), max_attempts=2)
        raise AssertionError("two transient failures in two attempts must raise")
    except TransientError:
        pass
    assert len(stub.calls) == 2
    stub = S.StubRenderer(fail_with=[TransientError("503")])
    c = S.product_only(rel, renderer=stub, work_dir=str(_WORK / "b"), max_attempts=2)
    assert c.receipt["attempts"] == 2 and len(c.receipt["attempt_errors"]) == 1
    for final in (I.ImagesRefused("Content Moderated"), I.QuotaUnavailable("402"),
                  gw.BudgetExceeded("ceiling")):
        stub = S.StubRenderer(fail_with=[final])
        try:
            S.product_only(rel, renderer=stub, work_dir=str(_WORK / "b"), max_attempts=3)
            raise AssertionError(type(final).__name__)
        except type(final):
            pass
        assert len(stub.calls) == 1, type(final).__name__
    for n in (0, S.MAX_ATTEMPTS + 1):
        try:
            S.product_only(rel, renderer=S.StubRenderer(), work_dir=str(_WORK / "b"),
                           max_attempts=n)
            raise AssertionError(n)
        except S.StageRefused:
            pass


# -- stages on the paid renderer, with a mock transport --------------------------------------
def test_product_only_through_flux3_reserves_first_and_sends_every_pattern_ref():
    rel = _release()
    db = _db()
    events: list = []
    real = I.reserve_render

    def spy(*a, **k):
        events.append("reserve")
        return real(*a, **k)

    I.reserve_render = spy
    t = Transport(events=events)
    try:
        with t:
            c = S.product_only(rel, renderer=S.flux3_renderer(ENV), work_dir=str(_WORK / "f"),
                               db=db)
    finally:
        I.reserve_render = real
    assert events[:2] == ["reserve", "post"]
    (sent,) = t.posts
    assert sent["url"] == "https://api.bfl.ai/v1/flux-3-image"
    assert sent["body"]["images"] == [base64.standard_b64encode(Path(p).read_bytes()).decode()
                                      for p in rel.pattern_refs]
    assert sent["body"]["aspect_ratio"] == "1:1" and sent["body"]["resolution"] == "1k"
    r = c.receipt
    assert r["model"] == "flux-3-image" and r["task_id"] == "task-123"
    assert r["input_sha256s"] == list(rel.pattern_ref_sha256s)
    cad = round(0.048 * I.USD_TO_CAD, 6)
    assert abs(r["cost_cad"] - cad) < 1e-9 and r["provider_cost_credits"] == 4.8
    (row,) = _reservations(db)
    assert row.agent == S.AGENT and abs(row.amount_cad - cad) < 1e-9


def test_lifestyle_through_flux3_is_4x5_at_1k_with_five_references():
    rel = _release()
    stub = S.StubRenderer()
    prod = S.product_only(rel, renderer=stub, work_dir=str(_WORK / "fl"))
    laura = [_png(f"fl-laura{i}.png", (60 + i, 70, 80)) for i in range(3)]
    t = Transport()
    with t:
        c = S.lifestyle(rel, prod, laura, {"id": "o1", "image": _png("fl-outfit.png")},
                        renderer=S.flux3_renderer(ENV), work_dir=str(_WORK / "fl"), db=_db())
    body = t.posts[0]["body"]
    assert len(body["images"]) == 5 and body["aspect_ratio"] == "4:5"
    assert body["resolution"] == "1k" and c.receipt["price"]["tier"] == "1k"


def test_an_exhausted_budget_sends_nothing_from_a_stage():
    rel = _release()
    db = _db()
    with db.session() as s:
        s.add(CostEntry(agent="gateway", kind=routing.IMAGE_COST_KIND,
                        amount_cad=gw.monthly_ceiling_cad() - 0.01, purpose="renders"))
    t = Transport()
    with t:
        try:
            S.product_only(rel, renderer=S.flux3_renderer(ENV), work_dir=str(_WORK / "x"),
                           db=db, max_attempts=3)
            raise AssertionError("exhausted")
        except gw.BudgetExceeded:
            pass
    assert t.posts == []


def test_gallery_cost_model_from_the_published_price():
    g = S.gallery_cost()
    assert g["usd_per_image"] == 0.048 and g["accepted_images"] == 6
    assert g["expected"]["renders"] == 12 and abs(g["expected"]["usd"] - 0.576) < 1e-9
    assert g["worst_case_bounded"]["renders"] == 6 * S.MAX_ATTEMPTS
    assert g["galleries_per_month_at_expected"] == int(g["monthly_ceiling_cad"]
                                                       // g["expected"]["cad"])


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failures = 0
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
