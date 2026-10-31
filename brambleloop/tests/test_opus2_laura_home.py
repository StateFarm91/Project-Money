"""OPUS2-P0: Laura's home (owner directive 2026-10-30 §14), one house for every lifestyle frame.

No network, no spend: the FLUX 3 generator runs on `StubRenderer`, exactly as
test_w4_flux3generator drives it, and the prompt it would send is read back.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_opus2_laura_home.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.creative import flux3_generator as FG  # noqa: E402
from brambleloop.creative import image_stages as S  # noqa: E402
from brambleloop.creative import pattern_refs as P  # noqa: E402
from brambleloop.products import launch0  # noqa: E402
from brambleloop.visual import canonical, conditioning, outfits, shot_plans  # noqa: E402
from brambleloop.visual import laura_home as H  # noqa: E402

CIR = launch0.cir_for("cloudline_blanket")
REL = P.release_hash_of(CIR)
OUTFIT = {"outfit_id": "o-3", "description": "an oatmeal linen dress, tan sandals",
          "setting": "a marble penthouse terrace"}


def _refused(fn, exc):
    try:
        fn()
    except exc:
        return True
    raise AssertionError(f"expected {exc}")


def test_every_assigned_category_names_a_room_and_unknown_goes_to_the_living_room():
    assert set(H.ROOM_FOR_CATEGORY.values()) <= set(H.ROOMS)
    assert {"kitchen", "living_room", "nursery"} <= set(H.ROOMS)
    room, why = H.room_for("basket")
    assert room.key == "kitchen" and "basket" in why
    room, why = H.room_for("a-category-nobody-assigned")
    assert room.key == H.DEFAULT_ROOM and "default" in why


def test_every_launch0_listing_has_a_room_in_the_one_house():
    for slug in launch0.LAUNCH0_SLUGS:
        scene = H.scene_for(slug)
        assert scene["room"] in H.ROOMS and scene["home"] == H.HOME_ID, (slug, scene)
        assert H.HOUSE in scene["environment"], slug
    assert H.scene_for("cloudline-baby-blanket")["room"] == "nursery"
    assert H.scene_for("market-basket-medium")["room"] == "kitchen"


def test_the_environment_is_deterministic_bounded_and_shares_the_house():
    a = H.environment(H.ROOMS["kitchen"], listing="hexagonal-bread-basket")
    b = H.environment(H.ROOMS["kitchen"], listing="hexagonal-bread-basket")
    assert a == b and len(a) <= H.MAX_ENVIRONMENT_CHARS
    texts = [H.environment(r, listing="x") for r in H.ROOMS.values()]
    assert all(H.HOUSE in t and H.HOME_ID in t for t in texts)
    assert len(set(texts)) == len(H.ROOMS)            # each room is its own room
    for r in H.ROOMS.values():
        assert len(H.cue(r)) <= H.MAX_CUE_CHARS


def test_the_home_never_describes_laura_or_claims_a_photographed_sample():
    for r in H.ROOMS.values():
        text = H.environment(r, listing="x")
        assert not outfits._IDENTITY_WORDS.search(text), (r.key, text)
        assert H.problems(text) == []
    for bad in ("a luxury showroom kitchen", "marble counters", "a staged show home",
                "a real sample on the table", "pristine white studio backdrop"):
        assert H.problems(bad), bad
        assert _refused(lambda: H.check(bad), H.HomeRefused)


def test_every_shot_plan_brief_is_inside_the_home_and_fits_with_its_cue():
    plans = shot_plans.all_plans()["plans"]
    assert plans
    for slug, plan in plans.items():
        cplan = shot_plans.campaign_plan(slug)
        room = H.ROOMS[H.scene_for(slug)["room"]]
        roles = list(plan.get("roles") or []) + list(cplan["roles"])
        assert roles, slug
        for r in roles:
            brief = str(r.get("brief") or "")
            assert H.problems(brief) == [], (slug, brief)
            assert len(f"{H.cue(room)}. {brief}") <= S.MAX_EDIT_CHARS or len(brief) > 250, (
                slug, brief)


def _gen():
    stub = S.StubRenderer()
    g = FG.Flux3Generator(None, renderer=stub, cir_loader=lambda s, v: CIR,
                          anchor_lookup=lambda s, v, r: None, work_root=None)
    return g, stub


def _refs(g):
    prepared = g.prepare_references(slug=CIR.slug, version=CIR.version, release=REL)
    return [{"kind": r["kind"], "sha256": hashlib.sha256(r["data"]).hexdigest(),
             "label": r.get("label", ""), "data": r["data"]} for r in prepared]


def _laura_refs():
    out = []
    for frame in conditioning.FRAME_ORDER:
        data = Path(canonical.reference_file(frame)).read_bytes()
        out.append({"kind": "laura_canonical", "sha256": hashlib.sha256(data).hexdigest(),
                    "frame": frame, "data": data})
    return out


def test_the_lifestyle_prompt_is_set_in_the_listings_room_not_the_outfits_setting():
    g, stub = _gen()
    refs = _refs(g)
    out = g.generate(stage="product_generation", role=FG.ANCHOR_ROLE, brief="flat",
                     references=refs, outfit=None, attempt=1)
    anchor = {"data": out["data"], "sha256": hashlib.sha256(out["data"]).hexdigest(),
              "status": "PASS", "checker": "stub judge"}
    g.anchor_lookup = lambda s, v, r: anchor
    g.generate(stage="lifestyle_generation", role="lifestyle", brief="Laura folds the blanket",
               references=refs + _laura_refs(), outfit=OUTFIT, attempt=1)
    prompt = stub.calls[-1]["prompt"]
    env = H.scene_for(CIR.slug)["environment"]
    assert env in prompt, prompt[:600]
    assert "the nursery" in prompt and "marble" not in prompt and "penthouse" not in prompt
    # Laura's canonical references still lead the request; the house changes nothing about her.
    life = g.generate(stage="lifestyle_generation", role="lifestyle", brief="again",
                      references=refs + _laura_refs(), outfit=OUTFIT, attempt=2)
    assert tuple(life["identity_evidence"]["input_sha256s"][:3]) == S.canonical_laura_hashes()
    assert stub.calls[-1]["prompt"].count(env) == 1


def test_a_product_only_styled_scene_carries_the_room_cue_within_the_cap():
    g, stub = _gen()
    refs = _refs(g)
    out = g.generate(stage="product_generation", role=FG.ANCHOR_ROLE, brief="flat",
                     references=refs, outfit=None, attempt=1)
    anchor = {"data": out["data"], "sha256": hashlib.sha256(out["data"]).hexdigest(),
              "status": "PASS", "checker": "stub judge"}
    g.anchor_lookup = lambda s, v, r: anchor
    g.generate(stage="role_generation", role="detail", brief="x" * 600, references=refs,
               outfit=None, attempt=1)
    call = stub.calls[-1]
    cue = H.scene_for(CIR.slug)["cue"]
    assert cue in call["prompt"], call["prompt"][:400]


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                fails += 1
                print("FAIL", name, repr(e))
                traceback.print_exc()
    print(f"{fails} failed")
    sys.exit(1 if fails else 0)
