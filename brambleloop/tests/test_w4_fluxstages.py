"""W4-FLUXAPI under D-W4-LAURA-FLUX3: product references 4/5/6, mandatory Laura, campaign set.

No network and no spend. The stages run on `StubRenderer`. The paid renderer
(`flux3_renderer` -> `images.generate`) runs on the mock BFL transport from `test_w4_fluxapi`,
which captures every outbound body.

Required tests covered here (spec 12, rule 11): the three canonical references are always
supplied; an invalid or missing reference is refused; product references come from the
correct pattern version; every required reference reaches the provider; product-only images
need no Laura references.

Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_w4_fluxstages.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import base64
import hashlib
import io
import json
import shutil
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
from brambleloop.creative import flux_prompt as FP  # noqa: E402
from brambleloop.creative import image_stages as S  # noqa: E402
from brambleloop.creative import pattern_refs as P  # noqa: E402
from brambleloop.gateway import anthropic as gw  # noqa: E402
from brambleloop.gateway import images as I  # noqa: E402
from brambleloop.gateway import prompts, routing  # noqa: E402
from brambleloop.products import garments as G  # noqa: E402
from brambleloop.products import launch0  # noqa: E402
from brambleloop.visual import canonical  # noqa: E402

from test_w4_fluxapi import ENV, Transport, _db, _reservations  # noqa: E402

_WORK = Path(tempfile.mkdtemp(prefix="w4-fluxstages-"))
CIR = launch0.cir_for("cloudline_blanket")
RELEASE_HASH = P.release_hash_of(CIR)
SPEC_PREFIXES = ("a42aeac7", "afe6191f", "f32bac68")     # spec 12, rule 1
OUTFIT = {"id": "outfit-07", "description": "an oatmeal linen dress, tan sandals, gold studs"}
SCENE = {"environment": "a sunlit nursery with pale oak floors",
         "pose": "Laura drapes the blanket over the crib rail",
         "framing": "three-quarter length, 4:5, eye level"}
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


def _canon_paths() -> list[str]:
    from brambleloop.visual import conditioning
    return [canonical.reference_file(f) for f in conditioning.FRAME_ORDER]


def _product(stub=None):
    return S.product_only(_release(), renderer=stub or S.StubRenderer(),
                          work_dir=str(_WORK / "po"))


def _pass(prod):
    return S.fidelity_verdict(prod, status="PASS", checker="test: flat-lay fidelity")


def _life(rel, prod, laura, outfit, **kw):
    kw.setdefault("fidelity", _pass(prod))
    return S.lifestyle(rel, prod, laura, outfit, **kw)


def _refused(fn, exc=S.StageRefused):
    try:
        fn()
    except exc:
        return True
    raise AssertionError(f"expected {exc.__name__}")


def _pieces_in_middle_row(path: str) -> int:
    """Runs of non-background pixels across the layout's vertical centre: drawn pieces."""
    with Image.open(path) as im:
        im = im.convert("RGB")
        y = im.size[1] // 2
        row = [im.getpixel((x, y)) for x in range(im.size[0])]
    runs, inside = 0, False
    for px in row:
        piece = px != P.BACKGROUND
        if piece and not inside:
            runs += 1
        inside = piece
    return runs


# -- product references 4/5/6 ----------------------------------------------------------------
def test_cloudline_refs_are_99x100_release_bound_fingerprinted_and_deterministic():
    m = P.build(CIR, release_hash=RELEASE_HASH, out_dir=_WORK / "a")
    m2 = P.build(CIR, release_hash=RELEASE_HASH, out_dir=_WORK / "a2")
    assert m["grid"]["stitches_across"] == 99 and m["grid"]["rows"] == 100
    assert m["grid"]["repeat"][0] == 9 and m["cost_cad"] == 0.0 and m["category"] == "flat"
    assert [r["role"] for r in m["references"]] == ["layout", "texture", "detail", "rules"]
    assert [r["sha256"] for r in m["references"]] == [r["sha256"] for r in m2["references"]]
    for r in m["references"]:
        raw = Path(r["path"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == r["sha256"] and RELEASE_HASH[:12] in r["path"]
    assert P.verify(m)["ok"] and m["release_hash"] == RELEASE_HASH
    lay = m["references"][0]
    assert abs(lay["height"] / lay["width"] - 96.4 / 79.2) < 0.02     # the twin's portrait
    stored = json.loads(next((_WORK / "a").glob("*-pattern-refs.json")).read_text())
    assert stored["manifest_sha256"] == m["manifest_sha256"]


def test_product_refs_come_only_from_the_exact_certified_version():
    assert _refused(lambda: P.build(CIR, release_hash="0" * 64, out_dir=_WORK / "x"),
                    P.PatternRefsRefused)
    assert _refused(lambda: P.build(CIR, release_hash=RELEASE_HASH, out_dir=_WORK / "x",
                                    version="1.1.0"), P.PatternRefsRefused)
    older = launch0.cir_for("cloudline_blanket", version="1.1.0")
    assert older.version == "1.1.0" and P.release_hash_of(older) != RELEASE_HASH
    # The older version's content with the current release hash: refused.
    assert _refused(lambda: P.build(older, release_hash=RELEASE_HASH, out_dir=_WORK / "x"),
                    P.PatternRefsRefused)
    assert _refused(lambda: S.release_from_cir(CIR, release_hash=RELEASE_HASH,
                                               out_dir=_WORK / "x", version="1.1.0"),
                    P.PatternRefsRefused)
    m = P.build(CIR, release_hash=RELEASE_HASH, out_dir=_WORK / "t")
    Path(m["references"][2]["path"]).write_bytes(b"\x89PNG tampered")
    assert P.verify(m)["problems"] == ["detail: bytes changed"]


def test_refs_adapt_multi_piece_round_and_garment_and_stay_in_flux_bounds():
    cases = {"hex": launch0.cir_for("hexagon_coasters"), "basket": launch0.cir_for(
        "basket_small"), "garment": G.harbour_pullover().build("M")}
    got = {}
    for name, cir in cases.items():
        m = P.build(cir, release_hash=P.release_hash_of(cir), out_dir=_WORK / name)
        got[name] = m
        assert len(m["references"]) == len(P.ROLES), name
        for r in m["references"]:
            assert min(r["width"], r["height"]) >= P.MIN_SIDE_PX, (name, r)
            assert r["width"] * r["height"] <= P.MAX_PIXELS, (name, r)
    hexm = got["hex"]
    assert hexm["category"] == "multi_piece" and hexm["technical_rules"]["piece_count"] == 4
    assert _pieces_in_middle_row(hexm["references"][0]["path"]) == 4   # all four coasters
    assert got["basket"]["category"] == "round"
    gm = got["garment"]
    rules = gm["technical_rules"]
    assert gm["category"] == "garment" and rules["piece_count"] == 4
    assert [c["name"] for c in rules["components"]] == ["body", "sleeve", "neckband"]
    assert rules["garment"]["size"] == "M" and rules["garment"]["measures_cm"]["chest"] > 0
    assert rules["assembly"] and _pieces_in_middle_row(gm["references"][0]["path"]) == 4


# -- mandatory Laura -------------------------------------------------------------------------
def test_canonical_laura_fingerprints_are_the_three_the_ruling_names():
    hashes = S.canonical_laura_hashes()
    assert tuple(h[:8] for h in hashes) == SPEC_PREFIXES
    paths = S.laura_references()
    assert [hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in paths] == list(hashes)


def test_every_laura_generation_supplies_all_three_canonical_references_first():
    rel = _release()
    stub = S.StubRenderer()
    prod = _product(stub)
    life = _life(rel, prod, None, OUTFIT, scene=SCENE, renderer=stub,
                       work_dir=str(_WORK / "ls"))
    var = S.variant(rel, life, "second_angle", outfit=OUTFIT, renderer=stub,
                    work_dir=str(_WORK / "ls"))
    for cand, call in ((life, stub.calls[1]), (var, stub.calls[2])):
        sent = [hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in call["refs"]]
        assert tuple(sent[:3]) == S.canonical_laura_hashes()
        assert cand.receipt["input_sha256s"] == sent and cand.features_laura
        n = len(S.CAMPAIGN_MINIMUM)
        assert [r["role"] for r in cand.receipt["references"]][:n] == list(S.CAMPAIGN_MINIMUM)
    assert [r["role"] for r in var.receipt["references"]][len(S.CAMPAIGN_MINIMUM)] == "base"


def test_an_invalid_missing_or_substituted_laura_reference_is_refused_before_any_call():
    rel = _release()
    stub = S.StubRenderer()
    prod = _product(stub)
    canon = _canon_paths()
    altered = _WORK / "altered.png"
    raw = bytearray(Path(canon[1]).read_bytes())
    raw[-1] ^= 0x01
    altered.write_bytes(bytes(raw))
    approved_lifestyle = _png("approved_lifestyle.png")
    bad_sets = {
        "two_only": canon[:2], "reordered": [canon[1], canon[0], canon[2]],
        "altered_torso": [canon[0], str(altered), canon[2]],
        "substituted_by_supplementary": [canon[0], approved_lifestyle, canon[2]],
        "four": canon + [approved_lifestyle], "missing_file": [canon[0], canon[1],
                                                              str(_WORK / "nope.png")]}
    before = len(stub.calls)
    assert len(bad_sets) == 6
    for name, refs in bad_sets.items():
        assert _refused(lambda: _life(rel, prod, refs, OUTFIT, renderer=stub,
                                            work_dir=str(_WORK / "bad"))), name
    saved = canonical.reference_file
    canonical.reference_file = lambda frame: ""                      # not on this disk
    try:
        assert _refused(lambda: _life(rel, prod, None, OUTFIT, renderer=stub,
                                            work_dir=str(_WORK / "bad")))
    finally:
        canonical.reference_file = saved
    assert len(stub.calls) == before                                 # nothing was sent


def test_supplementary_images_are_added_after_the_originals_never_instead():
    rel = _release()
    stub = S.StubRenderer()
    prod = _product(stub)
    extra = _png("approved_lifestyle2.png", (1, 2, 3))
    outfit = {**OUTFIT, "image": _png("outfit.png", (10, 200, 10))}
    c = _life(rel, prod, _canon_paths(), outfit, supplementary=[extra], renderer=stub,
                    work_dir=str(_WORK / "sup"))
    roles = [r["role"] for r in c.receipt["references"]]
    assert roles == list(S.CAMPAIGN_MINIMUM) + ["product_candidate", "outfit", "supplementary"]
    assert stub.calls[-1]["refs"][-1] == extra


def test_product_only_needs_no_laura_and_no_outfit():
    rel = _release()
    stub = S.StubRenderer()
    c = _product(stub)
    (call,) = stub.calls
    sent = {hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in call["refs"]}
    assert not sent & set(S.canonical_laura_hashes()) and not c.features_laura
    assert call["refs"] == list(rel.pattern_refs)
    assert "IDENTITY" not in call["prompt"] and "no person" in call["prompt"]
    assert _refused(lambda: S.product_only(rel, refs=[rel.pattern_refs[0]] * 3,
                                           renderer=stub, work_dir=str(_WORK / "po")))


def test_a_laura_image_requires_the_listings_outfit_and_a_matching_release():
    rel = _release()
    stub = S.StubRenderer()
    prod = _product(stub)
    assert _refused(lambda: _life(rel, prod, None, {}, renderer=stub,
                                        work_dir=str(_WORK / "o")))
    other = S.Candidate("product_only", "x", prod.path, prod.sha256, "f" * 64)
    assert _refused(lambda: S.lifestyle(rel, other, None, OUTFIT, renderer=stub,
                                        work_dir=str(_WORK / "o")))
    life = _life(rel, prod, None, OUTFIT, renderer=stub, work_dir=str(_WORK / "o"))
    assert _refused(lambda: S.variant(rel, life, "second_angle", renderer=stub,
                                      work_dir=str(_WORK / "o")))       # no outfit
    assert _refused(lambda: S.variant(rel, life, "make_it_pop", outfit=OUTFIT,
                                      renderer=stub, work_dir=str(_WORK / "o")))


# -- six-reference campaign set and the lower-limit fallback ---------------------------------
def test_all_campaign_references_reach_the_provider_payload():
    rel = _release()
    prod = _product()
    t = Transport()
    with t:
        c = _life(rel, prod, None, OUTFIT, scene=SCENE,
                        renderer=S.flux3_renderer(ENV), work_dir=str(_WORK / "pay"), db=_db())
    body = t.posts[0]["body"]
    expect = _canon_paths() + list(rel.pattern_refs) + [prod.path]
    assert body["images"] == [base64.standard_b64encode(Path(p).read_bytes()).decode()
                              for p in expect]
    assert body["aspect_ratio"] == "1:1" and body["resolution"] == "2k"
    r = c.receipt
    assert len(body["images"]) == 8 and len(S.CAMPAIGN_MINIMUM) == 7
    assert r["input_sha256s"][:7] == list(S.canonical_laura_hashes()) + list(
        rel.pattern_ref_sha256s)
    assert r["limitation"] is None and r["reference_limit"] == 10
    assert r["request"]["conditioning_proven"] is True and r["output_sha256"] == c.sha256
    assert r["task_id"] == "task-123" and r["provider_cost_credits"] == 4.8


def test_a_lower_provider_limit_merges_4_to_7_losslessly_and_reports_it():
    rel = _release()
    prod = _product()
    stub = S.StubRenderer(reference_limit=6)
    c = _life(rel, prod, None, OUTFIT, renderer=stub, work_dir=str(_WORK / "lim"))
    roles = [r["role"] for r in c.receipt["references"]]
    assert roles == ["laura_face", "laura_torso", "laura_body", "product_combined",
                     "product_candidate"]
    assert "merged losslessly" in c.receipt["limitation"]
    sheet = c.receipt["combined_sheet"]
    assert [s["sha256"] for s in sheet["sources"]] == list(rel.pattern_ref_sha256s)
    with Image.open(sheet["path"]) as im:
        im = im.convert("RGB")
        for src, box in zip(rel.pattern_refs, sheet["boxes"]):
            with Image.open(src) as orig:
                assert im.crop(tuple(box)).tobytes() == orig.convert("RGB").tobytes()
    assert "image 4 = certified product sheet" in stub.calls[-1]["prompt"]
    # Below what even the merged set needs: refused, nothing dropped.
    tiny = S.StubRenderer(reference_limit=4)
    assert _refused(lambda: _life(rel, prod, None, OUTFIT, renderer=tiny,
                                        work_dir=str(_WORK / "lim")))
    assert tiny.calls == []


# -- prompt ----------------------------------------------------------------------------------
def test_the_full_prompt_is_built_from_certified_data_and_pinned():
    rel = _release()
    stub = S.StubRenderer()
    prod = _product(stub)
    c = _life(rel, prod, None, OUTFIT, scene=SCENE, role="lifestyle_hero",
                    renderer=stub, work_dir=str(_WORK / "pr"))
    text = stub.calls[-1]["prompt"]
    for must in ("image 1 = canonical Laura face", "bust", "waist-to-hip", "freckles",
                 "cloudline-baby-blanket version 1.2.0", RELEASE_HASH[:16], "#FAF6EB",
                 "#1A2B3C", "Stitches: dc, sc", "79.2 x 96.4 cm", "Never add:",
                 "fringe", OUTFIT["description"], SCENE["environment"], SCENE["pose"],
                 SCENE["framing"], "lifestyle_hero", "AI-generated", "candidate only",
                 "anatomically correct hands"):
        assert must in text, must
    r = c.receipt
    assert r["builder_version"] == FP.BUILDER_VERSION
    assert [s["ref"] for s in r["sections"]] == [p.ref for p in FP.SECTIONS]
    assert r["prompt_text_sha256"] == hashlib.sha256(text.encode()).hexdigest()
    for p in FP.SECTIONS:
        assert prompts.get(p.ref) is p
    assert _refused(lambda: prompts.register(prompts.Prompt(
        name="image.flux3.identity", version="1", system="", template="edited",
        output_schema=("image",), max_output_tokens=1)), prompts.PromptIsImmutable)
    # The builder will not describe a product it has no certified images for.
    assert _refused(lambda: FP.build(rules=rel.rules, roles=["laura_face"], role="x"),
                    FP.PromptBuildRefused)


# -- attempts, spend --------------------------------------------------------------------------
def test_attempts_are_bounded_and_only_transient_failures_retry():
    rel = _release()
    stub = S.StubRenderer(fail_with=[TransientError("503"), TransientError("503")])
    assert _refused(lambda: S.product_only(rel, renderer=stub, work_dir=str(_WORK / "b"),
                                           max_attempts=2), TransientError)
    assert len(stub.calls) == 2
    stub = S.StubRenderer(fail_with=[TransientError("503")])
    c = S.product_only(rel, renderer=stub, work_dir=str(_WORK / "b"), max_attempts=2)
    assert c.receipt["attempts"] == 2 and len(c.receipt["attempt_errors"]) == 1
    for final in (I.ImagesRefused("Content Moderated"), I.QuotaUnavailable("402"),
                  gw.BudgetExceeded("ceiling")):
        stub = S.StubRenderer(fail_with=[final])
        assert _refused(lambda: S.product_only(rel, renderer=stub, work_dir=str(_WORK / "b"),
                                               max_attempts=3), type(final))
        assert len(stub.calls) == 1, type(final).__name__
    for n in (0, S.MAX_ATTEMPTS + 1):
        assert _refused(lambda: S.product_only(rel, renderer=S.StubRenderer(),
                                               work_dir=str(_WORK / "b"), max_attempts=n))


def test_product_only_through_flux3_reserves_first_and_sends_every_product_ref():
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
    body = t.posts[0]["body"]
    assert body["images"] == [base64.standard_b64encode(Path(p).read_bytes()).decode()
                              for p in rel.pattern_refs]
    assert body["aspect_ratio"] == "1:1" and body["resolution"] == "2k"
    cad = round(0.100 * I.USD_TO_CAD, 6)
    assert abs(c.receipt["cost_cad"] - cad) < 1e-9
    (row,) = _reservations(db)
    assert row.agent == S.AGENT and abs(row.amount_cad - cad) < 1e-9


def test_an_exhausted_budget_sends_nothing_from_a_stage():
    rel = _release()
    db = _db()
    with db.session() as s:
        s.add(CostEntry(agent="gateway", kind=routing.IMAGE_COST_KIND,
                        amount_cad=gw.monthly_ceiling_cad() - 0.01, purpose="renders"))
    t = Transport()
    with t:
        assert _refused(lambda: S.product_only(rel, renderer=S.flux3_renderer(ENV),
                                               work_dir=str(_WORK / "x"), db=db,
                                               max_attempts=3), gw.BudgetExceeded)
    assert t.posts == []


def test_gallery_cost_model_from_the_published_price():
    g = S.gallery_cost()
    assert g["usd_per_image"] == 0.100 and g["tier"] == "2k" and g["accepted_images"] == 6
    assert g["references_charged"] is False
    assert g["expected"]["renders"] == 12 and abs(g["expected"]["usd"] - 1.2) < 1e-9
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
    shutil.rmtree(_WORK, ignore_errors=True)
    sys.exit(bool(failures))
