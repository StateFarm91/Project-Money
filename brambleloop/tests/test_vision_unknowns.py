"""VISION-UNKNOWNS: why faithful generated frames never reached PASS in production.

Production 19i30 (15f809bfb; counts from the readback, production rows and pixels NOT read here):
`fidelity_unknowns.by_check` `coaster:palette` 10 and `region_palette` 9; Laura identity UNKNOWN
on 6 of 6 frames, "no identity reading: an unconfirmed likeness is not Laura (unanswered:
image_vision ...)". The vision route in production is openai-vision (`image_vision_openai`):
the owner activated `openai-vision:vision`, and Anthropic vision is not activated.

Each cause is traced and reproduced below. The inputs are the owner's committed FLUX frames
(research/owner_assets/owner_method_2026-11-28) and the deterministic photographic coaster
fixture (test_image_fidelity_3). Every provider answer is a TEST FIXTURE in the shape the real
OpenAI chat-completions API returns: `OpenAIProvider._post` is replaced, so the request is
built, the paid gate is entered and the response is decoded by the real client code.
There is no network and no paid call.

1. Laura identity: the question was never asked. The second judge
   (`vision_judges._openai_second_judge`, OpenAI gpt-4.1) inherited `GatewayVisionJudge`'s gate,
   which is the Anthropic `image_vision` gate. Production has that gate closed, so both judges
   refused with nothing sent. Fix: the second judge answers on the owner's openai-vision
   activation, as D-ENG-VIS-IDENTITY-1 records. It now gives a real reading against the
   canonical laura-r2-a42aeac7 references. A different woman FAILs (REFUSE). A matching reading
   stays UNKNOWN (HOLD), because PASS still needs a second, different-vendor judge and an
   owner-qualified biometric floor. Neither exists, and neither is faked.
2. region_palette: the question was never asked in 19i30. The product region went to the
   adapters' `image_vision`-only judge. The fix (lifestyle-region/2, routed judge) is on this
   branch and NOT deployed. Proven here end to end on the owner's scene and Laura frames,
   through the real OpenAI client: faithful PASS, wrong stripe colour FAIL, no route UNKNOWN.
   The deterministic region step was ruled out: it holds on the owner frames under dim, warm
   and graded light.
3. coaster:palette: a deterministic step that bailed out on real light. One per-piece gain
   cannot correct light that varies ACROSS a coaster. Under a soft cast shadow, the shaded
   cream reads off-palette (UNKNOWN), and a deeper shadow drags the wine cluster brown (a
   false "substituted colour" FAIL). Fix (fidelity-checks/4): the light is measured on the
   table round the piece (`fidelity._light_field`) and applied only when the table shows it is
   uneven. Under even light nothing changes, and no palette tolerance moved.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_vision_unknowns.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702 - per-process temp sandbox, removed at exit
import base64
import hashlib
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

import test_image_fidelity_route as R  # noqa: E402  (its harness refuses the network)
import test_image_fidelity_3 as H  # noqa: E402  (deterministic photographic coasters)
import test_verify_refs as VR  # noqa: E402

from brambleloop.creative import failure_codes as FC  # noqa: E402
from brambleloop.products.vessels import build_basket  # noqa: E402
from brambleloop.visual import candidate_gates as CG  # noqa: E402
from brambleloop.visual import canonical  # noqa: E402
from brambleloop.visual import fidelity as F  # noqa: E402
from brambleloop.visual import identity  # noqa: E402
from brambleloop.visual import image_production as IP  # noqa: E402
from brambleloop.visual import vision_judges as VJ  # noqa: E402

OWNER = ROOT / "research" / "owner_assets" / "owner_method_2026-11-28"
SCENE, LAURA = OWNER / "owner_basket_scene.png", OWNER / "owner_basket_laura.png"
REL = "a" * 64
# Interior fabric rectangles of the basket wall, as a careful judge returns them (fractions).
SCENE_PATCHES = [[0.36, 0.50, 0.95, 0.73]]
LAURA_PATCHES = [[0.56, 0.48, 0.78, 0.58]]


# ---- harness ---------------------------------------------------------------------------------

class _Completion(R._Transport):
    """FIXTURE `OpenAIProvider._post`: a chat-completions body exactly as the API returns it,
    with the model's reply as `text` (fenced, as gpt-4.1 often answers). Records requests."""

    def __init__(self, text: str):
        super().__init__({})
        self.text, self.bodies = text, []

    def __call__(self, provider, body, headers, timeout):
        self.calls += 1
        self.bodies.append(json.loads(body))
        return 200, json.dumps({
            "id": f"chatcmpl-fixture-{self.calls}", "object": "chat.completion",
            "model": provider.model,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": self.text,
                                                 "refusal": None},
                         "logprobs": None, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 3400, "completion_tokens": 90, "total_tokens": 3490}})


def _fenced(obj) -> str:
    return "```json\n" + json.dumps(obj, indent=2) + "\n```"


def _sent_images(body: dict) -> list[bytes]:
    out = []
    for part in body["messages"][-1]["content"]:
        if part.get("type") == "image_url":
            url = part["image_url"]["url"]
            assert url.startswith("data:image/"), url[:40]
            out.append(base64.b64decode(url.split(",", 1)[1]))
    return out


def _png(arr) -> bytes:
    b = io.BytesIO()
    Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).save(b, "PNG")
    return b.getvalue()


# ---- 1. Laura identity -----------------------------------------------------------------------

def _laura_cand() -> dict:
    """The owner's Laura frame with a conditioning receipt naming all three canonical
    references (what `gateway.images.conditioning_receipt` records for a conditioned render)."""
    return {"data": LAURA.read_bytes(), "laura_present": True, "slug": "market-basket-medium",
            "identity_evidence": {
                "references": [{"sha256": h, "role": f"laura_{f}"}
                               for f, h in canonical.CURRENT_REFERENCE_HASHES.items()],
                "request": {"conditioning_proven": True}}}


def _person(reading: str) -> dict:
    out = {d: reading for d in identity.DRIFT_DIMENSIONS}
    out["people_in_photograph"] = 1
    return out


def test_1_laura_before_the_fix_both_identity_judges_refused_on_the_anthropic_gate():
    """The production reason, reproduced: the OpenAI second judge carried the `image_vision`
    gate, so with openai-vision activated and Anthropic not, nothing was sent."""
    db = R._db()
    R._production_vision(db)
    t = _Completion(_fenced(_person("same")))
    with R._Patched(t):
        old = CG.RealJudges(db, embedder=None)
        second = old.second_vision
        # the 19i30 behaviour: the inherited Anthropic gate
        second.gate_open = lambda: F.GatewayVisionJudge.gate_open(second)
        second.read = lambda *a, **k: F.GatewayVisionJudge.read(second, *a, **k)
        got = old.identity(_laura_cand())
    assert t.calls == 0, "nothing was sent"
    assert got["status"] == "UNKNOWN", got
    assert got["why"].startswith("no identity reading: an unconfirmed likeness is not Laura "
                                 "(unanswered: image_vision"), got["why"]
    assert "image_vision_openai" in got["why"] and "unfunded" in got["why"], got["why"]
    print("OK 1 reproduced: identity 'no identity reading', both judges refused, 0 sent")


def test_2_laura_the_second_judge_reads_her_against_the_canonical_references():
    db = R._db()
    R._production_vision(db)
    t = _Completion(_fenced(_person("same")))
    with R._Patched(t):
        got = CG.RealJudges(db, embedder=None).identity(_laura_cand())
    assert t.calls == 1, t.calls
    sent = _sent_images(t.bodies[0])
    assert t.bodies[0]["model"] == VJ.SECOND_JUDGE_MODEL == "gpt-4.1-2025-04-14"
    # the second judge's order (`person_prompt("photo_first")`): image 1 the frame, images 2-4
    # the canonical laura-r2-a42aeac7 references, verified by sha256, unmodified
    assert canonical.IDENTITY_ID == "laura-r2-a42aeac7"
    assert len(sent) == 4 and sent[0] == LAURA.read_bytes()
    assert [hashlib.sha256(b).hexdigest() for b in sent[1:]] == [
        canonical.CURRENT_REFERENCE_HASHES[f] for f in VJ.REF_ORDER], "canonical refs, in order"
    assert "Image 1 is a photograph" in t.bodies[0]["messages"][-1]["content"][0]["text"]
    # a real reading now: one judge answered, scored on every dimension
    assert got["judges"] == ["image_vision_openai:gpt-4.1-2025-04-14"], got["judges"]
    assert "no identity reading" not in got["why"], got["why"]
    answered = [r for r in got["readings"] if r["answered"]]
    assert len(answered) == 1 and set(answered[0]["scored"].values()) == {identity.MATCH}
    # ... and still not a PASS: one vendor is not a pair, and no biometric floor is qualified
    assert got["status"] == "UNKNOWN" and got["verdict"] == "HOLD", (got["status"],
                                                                      got["verdict"])
    assert "missing_judge_pair" in got["why"] and "biometric" in got["why"], got["why"]
    assert any("two must agree" in h for h in got["hold_reasons"]), got["hold_reasons"]
    assert any("not production-qualified" in h for h in got["hold_reasons"])
    print("OK 2 identity read against laura-r2-a42aeac7: UNKNOWN/HOLD (one judge, no floor)")


def test_3_laura_a_different_woman_is_refused():
    db = R._db()
    R._production_vision(db)
    with R._Patched(_Completion(_fenced(_person("different")))):
        got = CG.RealJudges(db, embedder=None).identity(_laura_cand())
    assert got["status"] == "FAIL" and got["verdict"] == "REFUSE", (got["status"],
                                                                     got["verdict"])
    assert got.get("code") == FC.IDENTITY_DRIFT and got["failed"], got
    print("OK 3 a different woman: identity FAIL / REFUSE, IDENTITY_DRIFT")


def test_4_laura_unanswered_stays_unknown_and_is_never_resent():
    # openai-vision not activated: nothing is sent, UNKNOWN, never PASS
    db = R._db()
    R._production_vision(db)
    db2 = R._db()            # no activation at all
    t = _Completion(_fenced(_person("same")))
    with R._Patched(t):
        got = CG.RealJudges(db2, embedder=None).identity(_laura_cand())
    assert t.calls == 0 and got["status"] == "UNKNOWN", (t.calls, got["status"])
    assert "no identity reading" in got["why"] and "openai-vision" in got["why"], got["why"]
    # an unparseable answer is unanswered (UNKNOWN), and the same bytes are not paid for twice
    t = _Completion("I think this is probably the same woman.")
    with R._Patched(t):
        a = CG.RealJudges(db, embedder=None).identity(_laura_cand())
        b = CG.RealJudges(db, embedder=None).identity(_laura_cand())
    assert t.calls == 1, f"one paid attempt per bytes and question, got {t.calls}"
    assert a["status"] == b["status"] == "UNKNOWN", (a["status"], b["status"])
    assert "did not answer with JSON" in a["why"], a["why"]
    # a kept good answer is replayed with nothing sent
    db3 = R._db()
    R._production_vision(db3)
    t = _Completion(_fenced(_person("same")))
    with R._Patched(t):
        CG.RealJudges(db3, embedder=None).identity(_laura_cand())
        again = CG.RealJudges(db3, embedder=None).identity(_laura_cand())
    assert t.calls == 1 and again["judges"] == ["image_vision_openai:gpt-4.1-2025-04-14"]
    print("OK 4 identity: no activation UNKNOWN (0 sent); bad JSON UNKNOWN once; replayed")


# ---- 2. region_palette -----------------------------------------------------------------------

def _basket():
    return build_basket("medium", version="1.2.0")


def _region(data: bytes, located: dict) -> dict:
    v = F.verify_lifestyle(data, _basket(), release_hash=REL,
                           anchor={"status": "PASS", "release_hash": REL},
                           product_region=located.get("patches") or None)
    return [c for c in v["checks"] if c["check"] == "region_palette"][0]


def _wine_to(data: bytes, rgb) -> bytes:
    """The frame with its wine stripes re-dyed `rgb` (luminance kept): a wrong product."""
    a = np.asarray(Image.open(io.BytesIO(data)).convert("RGB")).astype(float)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    wine = (r > g + 25) & (r > b + 15) & (r < 200)
    luma = a.mean(axis=2, keepdims=True) / 90.0
    out = a.copy()
    out[wine] = np.clip(np.array(rgb, float) * luma[wine], 0, 255)
    return _png(out)


def test_5_region_before_the_route_fix_the_question_never_reached_openai():
    db = R._db()
    R._production_vision(db)
    t = _Completion(_fenced({"item_visible": "yes", "patches": SCENE_PATCHES}))
    with R._Patched(t):
        old = CG.RealJudges(db, second_vision=None, embedder=None).adapters().product_region(
            {"data": SCENE.read_bytes()})            # the 19i30 locate callable
    assert t.calls == 0 and old["patches"] == [], old
    rc = _region(SCENE.read_bytes(), old)
    assert rc["status"] == "UNKNOWN" and "no product region" in rc["why"], rc
    print("OK 5 reproduced: region_palette UNKNOWN, the region question was never sent")


def test_6_region_faithful_owner_frames_pass_through_the_real_openai_client():
    for path, patches in ((SCENE, SCENE_PATCHES), (LAURA, LAURA_PATCHES)):
        db = R._db()
        R._production_vision(db)
        _j, seen = VR._captured_locate(db)
        t = _Completion(_fenced({"item_visible": "yes", "patches": patches}))
        with R._Patched(t):
            got = seen["locate"]({"data": path.read_bytes()})
        assert t.calls == 1 and got["judge"] == "image_vision_openai:gpt-4.1-2025-04-14", got
        assert "Find the handmade" in t.bodies[0]["messages"][-1]["content"][0]["text"]
        assert _sent_images(t.bodies[0]) == [path.read_bytes()]
        rc = _region(path.read_bytes(), got)
        assert rc["status"] == "PASS", (path.name, rc)
        assert rc["on_palette_share"] >= F.LIFESTYLE_ON_PALETTE, rc
    print("OK 6 owner scene and Laura frames: region_palette PASS via image_vision_openai")


def test_7_region_wrong_stripes_fail_and_no_evidence_stays_unknown():
    db = R._db()
    R._production_vision(db)
    _j, seen = VR._captured_locate(db)
    for path, patches in ((SCENE, SCENE_PATCHES), (LAURA, LAURA_PATCHES)):
        for wrong in ((40, 60, 150), (40, 120, 60), (200, 160, 40), (120, 120, 120)):
            data = _wine_to(path.read_bytes(), wrong)      # navy, green, mustard, grey
            with R._Patched(_Completion(_fenced({"item_visible": "yes",
                                                 "patches": patches}))):
                got = seen["locate"]({"data": data})
            rc = _region(data, got)
            assert rc["status"] == "FAIL" and rc.get("code") == F.OFF_PALETTE_COLOUR, (
                path.name, wrong, rc)
            # 19i30's Lab-bin measure alone read these as one small group each (PASS)
            assert rc["largest_off_cluster"] < F.LIFESTYLE_EXTRA_CLUSTER, rc
            assert rc["largest_off_hue_group"] >= F.LIFESTYLE_EXTRA_CLUSTER, rc
    # a patch that runs onto the oak dresser is not a re-dyed stripe
    sloppy = _region(SCENE.read_bytes(), {"patches": [
        (int(0.36 * 896), int(0.50 * 1132), int(0.95 * 896), int(0.80 * 1132))]})
    assert sloppy["status"] == "PASS", sloppy
    # no route usable, item not visible, or a reply that is not the JSON object: UNKNOWN
    R._no_vision()
    dbx = R._db()
    _jx, seenx = VR._captured_locate(dbx)
    t = _Completion(_fenced({"item_visible": "yes", "patches": SCENE_PATCHES}))
    with R._Patched(t):
        none = seenx["locate"]({"data": SCENE.read_bytes()})
    assert t.calls == 0 and _region(SCENE.read_bytes(), none)["status"] == "UNKNOWN"
    for text in (_fenced({"item_visible": "unclear", "patches": SCENE_PATCHES}),
                 "The basket is in the lower half of the image."):
        dby = R._db()
        R._production_vision(dby)
        _jy, seeny = VR._captured_locate(dby)
        with R._Patched(_Completion(text)):
            got = seeny["locate"]({"data": SCENE.read_bytes()})
        assert _region(SCENE.read_bytes(), got)["status"] == "UNKNOWN", (text, got)
    print("OK 7 navy/green/mustard/grey stripes FAIL; no route / not visible / not JSON UNKNOWN")


# ---- 3. coaster:palette ----------------------------------------------------------------------

def _cast_shadow(data: bytes, depth: float, cx=0.62, cy=0.5, sx=0.12, sy=0.2) -> bytes:
    """A soft cast shadow (a plant or a mug out of frame) over part of the set, in linear light."""
    a = np.asarray(Image.open(io.BytesIO(data)).convert("RGB"), float)
    h, w = a.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    m = np.exp(-(((xx - cx * w) / (sx * w)) ** 2 + ((yy - cy * h) / (sy * h)) ** 2))
    return _png(H._srgb(F._lin(a) * (1 - depth * m)[..., None]))


def _no_light_field():
    saved = F._light_field

    class _Off:
        def __enter__(self):
            F._light_field = lambda *a, **k: (None, {"applied": False, "why": "disabled"})

        def __exit__(self, *exc):
            F._light_field = saved
    return _Off()


def test_8_coaster_before_the_fix_a_soft_shadow_reads_unknown():
    data = _cast_shadow(H.scene(table=H.HONEY), 0.5)
    with _no_light_field():
        v = H._verify(data)
    pals = H._palette(v)
    assert v["status"] == "UNKNOWN" and v["failed"] == [], (v["status"], v["failed"])
    assert v["unknown"] == ["coaster:palette"], v["unknown"]
    shaded = [p for p in pals if p["status"] == "UNKNOWN"]
    assert len(shaded) == 1 and shaded[0]["off_palette_share"] > F.OFF_GLOBAL_MAX, pals
    assert "occlusion, a prop or an invented motif" in shaded[0]["why"]
    # a deeper shadow: the shaded cream drags the wine cluster brown, a false FAIL
    with _no_light_field():
        deep = H._verify(_cast_shadow(H.scene(table=H.HONEY), 0.6))
    assert deep["status"] != "PASS", deep["status"]
    print("OK 8 reproduced: soft cast shadow -> coaster:palette UNKNOWN on a faithful set")


def test_9_coaster_the_light_is_measured_on_the_table_and_a_faithful_set_passes():
    cases = [(t, d) for t in (H.HONEY, H.WALNUT, H.LIGHT_OAK) for d in (0.3, 0.4, 0.5)]
    cases += [(t, d) for t in (H.HONEY, H.WALNUT) for d in (0.55, 0.6)]
    for table, depth in cases:
        v = H._verify(_cast_shadow(H.scene(table=table), depth))
        pals = H._palette(v)
        assert v["status"] == "PASS", (table, depth, v["unknown"], v["failed"],
                                       [p["why"] for p in pals])
        if depth >= 0.5:      # a light shadow is within the per-piece gain already
            assert any(p["light_field"]["applied"] for p in pals), (table, depth)
        for p in pals:
            assert p["clusters"]["cream"]["de76"] < 8, (table, depth, p["clusters"])
    # also a shadow from the other side, and from above
    for cx, cy in ((0.3, 0.5), (0.5, 0.3)):
        v = H._verify(_cast_shadow(H.scene(table=H.HONEY), 0.5, cx=cx, cy=cy))
        assert v["status"] == "PASS", (cx, cy, v["unknown"], v["failed"])
    # KNOWN LIMIT, recorded not hidden: a shadow darker than ~0.55 peaking INSIDE a piece on a
    # pale (light oak) table is under-measured from the ring round it. It FAILed before this
    # change (palette) and still FAILs (colour layout); never PASS, never newly worse.
    for depth in (0.6, 0.7):
        data = _cast_shadow(H.scene(table=H.LIGHT_OAK), depth)
        with _no_light_field():
            before = H._verify(data)
        assert before["status"] == "FAIL" and H._verify(data)["status"] == "FAIL", depth
    print("OK 9 faithful coasters under a cast shadow: coaster:palette PASS (light measured)")


def test_10_coaster_wrong_colours_still_fail_under_the_shadow():
    for src in (H.recoloured(H.WINE, (31, 42, 110)),             # navy for wine
                H.recoloured(H.CREAM, (238, 205, 120)),          # mustard for cream
                H.recoloured(H.WINE, F._hex_rgb(H.CREAM))):      # the wine round missing
        v = H._verify(_cast_shadow(H.scene(table=H.HONEY, src=src), 0.5))
        assert v["status"] == "FAIL", (v["status"], v["unknown"])
        assert set(v["failed"]) & {"coaster:palette", "coaster:colour_layout"}, v["failed"]
    # a band in the shaded table's brown is still a band, not light
    v = H._verify(_cast_shadow(H.scene(table=H.HONEY, src=H.recoloured(H.WINE, (60, 38, 24))),
                               0.5))
    assert v["status"] != "PASS", v["status"]
    print("OK 10 navy / mustard / missing round FAIL under the shadow; table-brown band not PASS")


def test_11_even_light_reads_exactly_as_before_and_the_version_moves():
    for data in (H.scene(), H.scene(table=H.WALNUT), H.scene(hole_r=0)):
        new = H._verify(data)
        with _no_light_field():
            old = H._verify(data)
        assert new["status"] == old["status"] == "PASS", (new["status"], old["status"])
        for a, b in zip(H._palette(new), H._palette(old)):
            assert a["light_field"]["applied"] is False, a["light_field"]
            assert {k: a[k] for k in ("status", "clusters", "off_palette_share")} == \
                {k: b[k] for k in ("status", "clusters", "off_palette_share")}
    # no tolerance moved
    assert (F.OFF_PALETTE_DE, F.OFF_GLOBAL_MAX, F.CENTRE_DE_MAX, F.GAIN_RANGE) == \
        (22.0, 0.03, 15.0, (0.6, 1.6))
    assert (F.LIFESTYLE_ON_PALETTE, F.LIFESTYLE_EXTRA_CLUSTER) == (0.60, 0.15)
    assert F.FIDELITY_CHECK_VERSION == "fidelity-checks/4"
    assert IP.fidelity_check_version() == F.FIDELITY_CHECK_VERSION
    assert F.CHECKER == "visual.fidelity product-fidelity/1.0.0"
    print("OK 11 even light unchanged; tolerances unchanged; fidelity-checks/4")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    tests.sort(key=lambda f: int(f.__name__.split("_")[1]))
    for t in tests:
        t()
    print(f"ALL {len(tests)} OK")
