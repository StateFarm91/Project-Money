"""ENG-WARDROBE-SCENES: outfit library, scene library, prompt assembly and gallery planner.

1. the outfit library: >= 60 complete, valid, pairwise-distinct outfits;
2. outfit uniqueness across listings, and the outfit constant within a listing (durable);
3. the colour-harmony rule;
4. the misleading-prop rule;
5. every family gets a valid seven-role plan, in every season;
6. prompt determinism, and the ENG-LEARN template interface;
7. no reference image without the owner's FLUX activation;
8. a mutation of each rule is caught by its test (`MUTANTS`).

Run: cd brambleloop && PYTHONPATH=src:tests $PY tests/test_wardrobe_scenes.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import os
import sys
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.pop("DATABASE_URL", None)
os.environ.pop("BRAMBLELOOP_REQUIRE_POSTGRES", None)

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.visual import gallery_planner as G  # noqa: E402
from brambleloop.visual import laura_home as H  # noqa: E402
from brambleloop.visual import outfit_library as OL  # noqa: E402
from brambleloop.visual import outfits as REG  # noqa: E402
from brambleloop.visual import prompt_assembly as PA  # noqa: E402
from brambleloop.visual import scene_library as SL  # noqa: E402
from brambleloop.visual import shot_plans as SP  # noqa: E402
from brambleloop.visual import wardrobe as WD  # noqa: E402

WINE = {"cream": "#FAF6EB", "wine": "#6E1F2A"}
SEASONS = ("", "spring", "summer", "autumn", "winter")


def _db() -> Database:
    db = Database("sqlite://")
    db.create_all()
    return db


def _product(family: str, colours=None, slug: str = "test-piece") -> PA.ProductRef:
    return PA.ProductRef(slug=slug, title="Test Piece", version="1.0.0",
                         fingerprint="abc123def456", family=family,
                         colours=tuple((colours or WINE).items()), components=("body",))


@contextmanager
def patched(obj, name, value):
    old = getattr(obj, name)
    setattr(obj, name, value)
    try:
        yield
    finally:
        setattr(obj, name, old)


# ---- 1. the outfit library -----------------------------------------------------------------

def test_the_library_has_at_least_sixty_outfits_and_no_rule_breaks():
    assert OL.LIBRARY_SIZE >= 60, OL.LIBRARY_SIZE
    assert OL.library_problems() == [], OL.library_problems()[:10]


def test_every_outfit_is_complete_with_season_occasion_palette_and_hair():
    assert len(OL.LIBRARY) >= 60
    for o in OL.LIBRARY:
        v = o.view()
        assert v["garments"]["top_or_dress"] and v["garments"]["shoes"], o.outfit_id
        assert v["garments"]["lower"] or o.is_dress, o.outfit_id
        assert v["seasons"] and v["occasions"] and v["formality"] in OL.FORMALITY
        assert v["palette"] and all(p["hex"].startswith("#") for p in v["palette"])
        assert v["hair_styling"] in OL.HAIR_STYLINGS and v["text_spec"]
        assert v["families"], o.outfit_id


def test_outfit_ids_are_stable_and_registry_valid():
    ids = [o.outfit_id for o in OL.LIBRARY]
    assert len(ids) == len(set(ids)) and len(ids) >= 60
    for i in ids:
        assert REG._ID.match(i) and i.startswith("wl-"), i
    # Stable: the id is the key, never a hash of mutable text or of the order.
    assert OL.BY_ID["wl-chambray-indigo-boots"].top_or_dress == "chambray button-down shirt"


def test_library_outfits_are_pairwise_distinct_by_the_registry_measure():
    lib = OL.LIBRARY
    assert len(lib) >= 60
    worst = max(WD.similarity(a.garments, b.garments)["score"]
                for i, a in enumerate(lib) for b in lib[i + 1:])
    assert worst < WD.MAX_SIMILARITY, worst
    ref = max(WD.similarity(o.garments, WD.REFERENCE_OUTFIT)["score"] for o in lib)
    assert ref < WD.MAX_SIMILARITY, ref


def test_branded_revealing_knitted_and_identity_outfits_are_refused():
    base = OL.BY_ID["wl-chambray-indigo-boots"]
    cases = {
        "BRANDED": dict(shoes="white converse sneakers"),
        "REVEALING": dict(top_or_dress="black crop top"),
        "KNITWEAR": dict(top_or_dress="sage cable-knit cardigan"),
        "IDENTITY": dict(accessories="gold hoops framing her face"),
    }
    assert len(cases) == 4
    for code, change in cases.items():
        o = OL.Outfit(**{**base.__dict__, **change})
        probs = OL.outfit_problems(o)
        assert any(p.startswith(code) for p in probs), (code, probs)
    logo = OL.Outfit(**{**base.__dict__, "top_or_dress": "navy tee with a logo"})
    assert any(p.startswith("BRANDED") for p in OL.outfit_problems(logo))
    assert OL.outfit_problems(base) == []


def test_hair_is_an_arrangement_never_a_change():
    assert len(OL.HAIR_STYLINGS) >= 4
    for key, text in OL.HAIR_STYLINGS.items():
        assert text.startswith("her own hair"), key
        assert not OL._HAIR_CHANGE.search(text), key
    bad = OL.Outfit(**{**OL.LIBRARY[0].__dict__, "hair": "short_bob"})
    assert any("closed list" in p for p in OL.outfit_problems(bad))
    with patched(OL, "HAIR_STYLINGS", {**OL.HAIR_STYLINGS, "loose": "her own hair dyed blonde"}):
        assert any("changes her hair" in p for p in OL.outfit_problems(OL.LIBRARY[0]))


def test_every_library_outfit_registers_in_the_durable_registry():
    db = _db()
    for o in OL.LIBRARY:
        row = REG.register(db, outfit_id=o.outfit_id, garments=o.garments,
                           description=o.text_spec(),
                           colours=[p["colour"] for p in o.palette()])
        assert row["outfit_id"] == o.outfit_id
    assert len(REG.registry(db)) == OL.LIBRARY_SIZE


def test_a_garment_listing_wears_the_product_over_a_base_layer():
    ok = [o for o in OL.LIBRARY if OL.compatible(o, "garment")["ok"]]
    assert len(ok) >= 10
    for o in ok:
        assert o.garments["outerwear"] == "none" and not o.is_dress, o.outfit_id
    coat = OL.BY_ID["wl-charcoal-tee-camel-coat"]
    assert not OL.compatible(coat, "garment")["ok"]
    assert not OL.compatible(coat, "blanket")["ok"]        # held indoors: no coat
    neck = OL.BY_ID["wl-olive-shirtdress-tan-sandal"]
    assert not OL.compatible(neck, "baby")["ok"]            # held close: no necklace
    assert OL.compatible(coat, "basket")["ok"]


# ---- 2. uniqueness across listings, constant within a listing ------------------------------

def test_outfit_unique_across_listings():
    db = _db()
    got = [OL.claim_for_listing(db, f"listing-{i}", family="basket", product_colours=WINE)
           for i in range(25)]
    assert len(got) == 25 and all(g["status"] == "PASS" for g in got), got[-1]
    ids = [g["outfit_id"] for g in got]
    assert len(set(ids)) == len(ids), ids
    held = {o["outfit_id"]: o["listing"] for o in REG.registry(db) if o["listing"]}
    assert len(held) == 25


def test_outfit_constant_within_a_listing_and_durable():
    db = _db()
    first = OL.claim_for_listing(db, "listing-a", family="blanket", product_colours=WINE)
    assert first["status"] == "PASS" and first["claimed"] is True
    for _ in range(5):
        again = OL.claim_for_listing(db, "listing-a", family="blanket", product_colours=WINE)
        assert again["status"] == "PASS" and again["claimed"] is False
        assert again["outfit_id"] == first["outfit_id"]
    # A different family or season asked later does not move the listing's outfit.
    other = OL.claim_for_listing(db, "listing-a", family="basket", product_colours=WINE,
                                 season="summer")
    assert other["outfit_id"] == first["outfit_id"]
    plan = G.plan_gallery("listing-a", product=_product("blanket"),
                          outfit=OL.BY_ID[first["outfit_id"]])
    laura = [f for f in plan["frames"] if f["laura"]]
    assert laura and {f["outfit_id"] for f in laura} == {first["outfit_id"]}
    assert plan["check"]["ok"], plan["check"]


def test_an_outfit_is_never_reused_while_held_even_when_retired():
    db = _db()
    a = OL.claim_for_listing(db, "listing-a", family="basket", product_colours=WINE)
    REG.replace(db, a["outfit_id"], "wl-does-not-exist", "listing-a")  # refused: kept
    with patched(OL, "choose", lambda *a_, **k: OL.BY_ID[a["outfit_id"]]):
        b = OL.claim_for_listing(db, "listing-b", family="basket", product_colours=WINE,
                                 max_tries=2)
    assert b["status"] == "UNKNOWN" and b.get("outfit_id") is None, b
    assert REG.reserve(db, a["outfit_id"], "listing-b")["status"] == "FAIL"


def test_check_gallery_refuses_two_outfits_or_a_laura_frame_without_one():
    o = OL.choose("listing-x", family="garment", product_colours=WINE)
    plan = G.plan_gallery("listing-x", product=_product("garment"), outfit=o)
    assert plan["check"]["ok"], plan["check"]
    laura = [f for f in plan["frames"] if f["laura"]]
    assert len(laura) >= 3
    laura[0]["outfit_id"] = "wl-some-other-outfit"
    kinds = [p["kind"] for p in G.check_gallery(plan)["problems"]]
    assert "more_than_one_outfit" in kinds, kinds
    laura[0]["outfit_id"] = None
    kinds = [p["kind"] for p in G.check_gallery(plan)["problems"]]
    assert "laura_without_outfit" in kinds, kinds


# ---- 3. colour harmony ------------------------------------------------------------------

def test_colour_harmony_rule():
    cream_top = OL.BY_ID["wl-navy-quilted-jacket-cord"]        # cream oxford shirt
    h = OL.harmony(cream_top, {"cream": "#FAF6EB"})
    assert h["status"] == "FAIL" and any(p["code"] == "CAMOUFLAGE" and p["slot"] ==
                                         "top_or_dress" for p in h["problems"]), h
    mustard = OL.BY_ID["wl-mustard-tee-olive-cargo"]
    h = OL.harmony(mustard, {"forest": "#244A3A", "cream": "#FAF6EB"})
    assert any(p["code"] == "COMPETITION" and p["colour"] == "mustard"
               for p in h["problems"]), h
    calm = OL.BY_ID["wl-chambray-indigo-boots"]
    assert OL.harmony(calm, WINE)["status"] == "PASS"
    assert OL.harmony(calm, {})["status"] == "UNKNOWN"          # unknown is never PASS
    assert OL.harmony(calm, ["mauve-ish"])["status"] == "UNKNOWN"
    # Small items never decide it: gold hoops beside forest yarn are fine.
    assert all(p["slot"] in OL._LARGE_SLOTS
               for o in OL.LIBRARY for p in OL.harmony(o, WINE)["problems"])


def test_harmony_is_enforced_by_the_claim():
    db = _db()
    pal = {"forest": "#244A3A", "cream": "#FAF6EB"}
    got = [OL.claim_for_listing(db, f"l{i}", family="blanket", product_colours=pal)
           for i in range(8)]
    assert len(got) == 8 and all(g["status"] == "PASS" for g in got)
    for g in got:
        assert OL.harmony(OL.BY_ID[g["outfit_id"]], pal)["status"] == "PASS"


def test_delta_e_and_chroma_are_measured():
    assert OL.delta_e("#FFFFFF", "#FFFFFF") == 0
    assert OL.delta_e("#000000", "#FFFFFF") > 99
    assert OL.chroma("#808080") < 1 and OL.chroma("#C49E3E") > 40


# ---- 4. misleading props ------------------------------------------------------------------

def test_misleading_prop_rule():
    assert SL.prop_problems("mug_tea", "coaster") == []
    codes = {
        "KIT": ("basket", "a ball of yarn and a crochet hook"),
        "KNITWEAR": ("coaster", "a knitted tea cosy"),
        "DECOY": ("basket", "a second wicker basket"),
    }
    assert len(codes) == 3
    for code, (fam, text) in codes.items():
        assert any(p.startswith(code) for p in SL.prop_problems("x", fam, text=text)), code
    assert any(p.startswith("NOT_ALLOWED") for p in SL.prop_problems("dinner_plates",
                                                                      "baby"))
    assert any(p.startswith("UNKNOWN") for p in SL.prop_problems("unicorn", "basket"))
    for key, text in SL.PROPS.items():
        if text:
            assert not SL.KIT_WORDS.search(text), key


def test_every_registered_prop_and_scene_is_clean_for_its_families():
    assert len(SL.SCENES) >= 40 and SL.library_problems() == []
    n = 0
    for sc in SL.SCENES:
        for fam in sc.families:
            keep, _dropped = SL.props_for(sc, fam)
            for p in keep:
                assert SL.prop_problems(p, fam) == [], (sc.scene_id, fam, p)
                n += 1
    assert n > 50


def test_assembled_prompts_carry_the_not_included_line_and_drop_bad_props():
    sc = SL.BY_ID["sc-market-stall"]          # "produce in a paper bag" beside a bag
    fr = PA.assemble(scene=sc, product=_product("bag"), frame_role="lifestyle", laura=True,
                     outfit=OL.choose("l", family="bag", product_colours=WINE))
    assert "produce" in [d["prop"] for d in fr["props_dropped"]]
    assert "paper bag" not in fr["sections"]["scene"]
    assert SL.NOT_INCLUDED in fr["sections"]["scene"]


def test_a_learned_brief_cannot_smuggle_a_misleading_prop():
    sc = SL.BY_ID["sc-kitchen-table-breakfast"]
    learned = {"prompt_version": "learn:7:1",
               "template": {"brief": "Hero: the basket with a skein of yarn tucked inside."}}
    try:
        PA.assemble(scene=sc, product=_product("basket"), frame_role="hero", laura=False,
                    learned=learned)
    except PA.PromptAssemblyRefused as e:
        assert "KIT" in str(e)
    else:
        raise AssertionError("a learned brief with yarn in the basket was accepted")


# ---- 5. every family gets a valid seven-role plan ------------------------------------------

def test_scene_library_covers_rooms_outdoors_seasons_lighting_and_cameras():
    places = {s.place for s in SL.SCENES}
    for need in ("living_room", "nursery", "kitchen", "bedroom", "reading_nook", "porch",
                 "craft_room"):
        assert need in places, need
    assert sum(1 for s in SL.SCENES if not s.indoor) >= 10
    assert {"morning_window", "golden_hour", "lamp_glow"} <= {s.lighting for s in SL.SCENES}
    assert set(SL.CAMERA_ANGLES) == {s.angle for s in SL.SCENES}
    assert len({s.focal_mm for s in SL.SCENES}) >= 4 and {s.dof for s in SL.SCENES} == set(
        SL.DOF)
    for s in SL.SCENES:
        H.check(s.environment())


def test_every_family_gets_a_valid_seven_role_plan():
    fams = SL.EVERY
    assert len(fams) >= 13
    checked = 0
    for fam in fams:
        for season in SEASONS:
            for i in range(12):
                listing = f"{fam}-{season or 'any'}-{i}"
                o = OL.choose(listing, family=fam, product_colours=WINE)
                plan = G.plan_gallery(listing, product=_product(fam), outfit=o, season=season)
                c = plan["check"]
                assert c["ok"], (listing, c["problems"])
                roles = [f["frame_role"] for f in plan["frames"]]
                assert roles[:6] == list(G.JOB_OF_FRAME), roles
                assert len(plan["frames"]) >= 7 and len(set(roles)) == len(roles)
                assert SP.campaign_standard(plan)["ok"], plan["roles"]
                assert len(c["places"]) >= G.MIN_PLACES
                if season:
                    for f in plan["frames"]:
                        if f["generate"]:
                            assert season in SL.BY_ID[f["scene_id"]].seasons, (listing, f)
                checked += 1
    assert checked == len(fams) * len(SEASONS) * 12


def test_every_launch0_listing_plans_and_claims_one_outfit():
    from brambleloop.products import launch0

    db = _db()
    slugs = list(launch0.LAUNCH0_SLUGS)
    assert slugs
    held = set()
    for slug in slugs:
        plan = G.plan_for_listing(db, slug)
        assert plan["check"]["ok"], (slug, plan["check"])
        assert plan["claim"]["status"] == "PASS"
        assert plan["outfit_id"] not in held
        held.add(plan["outfit_id"])
        again = G.plan_for_listing(db, slug)
        assert again["outfit_id"] == plan["outfit_id"]
        assert [f.get("prompt_sha256") for f in again["frames"]] == \
               [f.get("prompt_sha256") for f in plan["frames"]]


def test_laura_appears_where_the_family_puts_her():
    o = OL.choose("w", family="garment", product_colours=WINE)
    worn = G.plan_gallery("w", product=_product("garment"), outfit=o)
    on = {f["frame_role"] for f in worn["frames"] if f["laura"]}
    assert on == {"hero", "lifestyle", "alt_angle", "scale_in_use"}, on
    small = G.plan_gallery("s", product=_product("coaster"), outfit=o)
    assert {f["frame_role"] for f in small["frames"] if f["laura"]} == {"lifestyle"}
    for plan in (worn, small):
        assert len(plan["frames"]) >= 7
        for f in plan["frames"]:
            if f["frame_role"] in ("flat_lay", "close_up"):
                assert f["laura"] is False


def test_filler_and_repeats_are_refused():
    o = OL.choose("f", family="basket", product_colours=WINE)
    plan = G.plan_gallery("f", product=_product("basket"), outfit=o)
    assert plan["check"]["ok"]
    gen = [f for f in plan["frames"] if f["generate"]]
    assert len(gen) >= 6
    clone = {**plan, "frames": [dict(f) for f in plan["frames"]]}
    g2 = [f for f in clone["frames"] if f["generate"]]
    g2[1].update(scene_id=g2[0]["scene_id"], place=g2[0]["place"], angle=g2[0]["angle"],
                 variable_text=g2[0]["variable_text"])
    kinds = {p["kind"] for p in G.check_gallery(clone)["problems"]}
    assert {"duplicate_scene", "same_place_same_angle", "repetitive_filler"} <= kinds, kinds
    short = {**plan, "frames": plan["frames"][:6]}
    kinds = {p["kind"] for p in G.check_gallery(short)["problems"]}
    assert "campaign_below_standard" in kinds
    one_place = {**plan, "frames": [dict(f, place="kitchen", angle=f"a{i}")
                                    for i, f in enumerate(plan["frames"])]}
    assert "too_few_places" in {p["kind"] for p in G.check_gallery(one_place)["problems"]}


def test_the_product_is_identical_in_every_frame():
    o = OL.choose("p", family="pillow", product_colours=WINE)
    plan = G.plan_gallery("p", product=_product("pillow"), outfit=o)
    gen = [f for f in plan["frames"] if f["generate"]]
    assert len(gen) >= 6
    blocks = {f["sections"]["product"] for f in gen}
    assert len(blocks) == 1 and _product("pillow").block() in blocks
    gen[2]["product_digest"] = "0" * 64
    assert "product_not_invariant" in {p["kind"] for p in
                                       G.check_gallery(plan)["problems"]}


def test_no_distinct_scene_means_held_never_padded():
    with patched(SL, "SCENES", tuple(s for s in SL.SCENES if "close_up" not in s.roles)):
        try:
            G.plan_gallery("h", product=_product("coaster"), outfit=None)
        except G.GalleryRefused as e:
            assert "close_up" in str(e)
        else:
            raise AssertionError("a gallery with no close-up scene was planned")


# ---- 6. prompts: determinism and the ENG-LEARN interface -----------------------------------

def test_prompt_determinism():
    o = OL.choose("d", family="blanket", product_colours=WINE)
    a = G.plan_gallery("d", product=_product("blanket"), outfit=o, season="autumn")
    b = G.plan_gallery("d", product=_product("blanket"), outfit=o, season="autumn")
    sa = [f.get("prompt_sha256") for f in a["frames"]]
    assert sa == [f.get("prompt_sha256") for f in b["frames"]] and any(sa)
    for f in a["frames"]:
        if f["generate"]:
            assert PA.fingerprint(f) == PA.fingerprint(
                next(x for x in b["frames"] if x["position"] == f["position"]))
    # A different listing is a different gallery.
    c = G.plan_gallery("d2", product=_product("blanket"), outfit=o, season="autumn")
    assert [f.get("scene_id") for f in c["frames"]] != [f.get("scene_id") for f in a["frames"]]


def test_templates_are_versioned_and_named_on_every_frame():
    assert set(PA.CURRENT) == set(SL.FRAME_ROLES)
    for tid, t in PA.TEMPLATES.items():
        assert "@" in tid and t["role"] in SL.FRAME_ROLES and "none" in t["briefs"], tid
    o = OL.choose("v", family="garment", product_colours=WINE)
    plan = G.plan_gallery("v", product=_product("garment"), outfit=o)
    gen = [f for f in plan["frames"] if f["generate"]]
    assert len(gen) >= 6
    for f in gen:
        assert f["template_id"] == PA.CURRENT[f["frame_role"]] == f["prompt_version"]


def test_eng_learn_interface_shape_and_override():
    for role in SL.FRAME_ROLES:
        t = PA.learn_default_template("basket", role)
        assert set(t) >= {"brief", "camera", "lighting", "negatives"}
        assert t["camera"] in PA._LEARN_CAMERA and t["lighting"] == "daylight"
    # The shot_plans role keys ENG-LEARN records resolve too.
    assert PA.learn_default_template("basket", "detail")["camera"] == "close"
    sc = SL.BY_ID["sc-kitchen-table-breakfast"]
    learned = {"prompt_version": "learn:3:2",
               "template": {"brief": "Hero: the finished piece on the breakfast table.",
                            "camera": "front", "lighting": "warm_lamp",
                            "negatives": ["steam"]}}
    fr = PA.assemble(scene=sc, product=_product("basket"), frame_role="hero", laura=False,
                     learned=learned)
    assert fr["prompt_version"] == "learn:3:2"
    assert "seen straight on" in fr["prompt"] and "warm lamp light" in fr["prompt"]
    assert "steam" in fr["sections"]["negatives"]
    assert fr["sections"]["product"] == _product("basket").block()   # never learned
    assert PA.learn_scene(fr)["camera"] == "three_quarter" and \
        PA.learn_scene(fr)["lighting"] in ("daylight", "warm_lamp")


def test_laura_frames_lock_identity_and_name_the_outfit():
    o = OL.choose("i", family="scarf", product_colours=WINE)
    plan = G.plan_gallery("i", product=_product("scarf"), outfit=o)
    laura = [f for f in plan["frames"] if f["laura"]]
    assert len(laura) >= 3
    for f in laura:
        assert "laura-r2-a42aeac7" in f["sections"]["laura"]
        assert o.outfit_id in f["sections"]["laura"] and o.text_spec() in f["prompt"]
        assert f["flux_scene"]["outfit"]["outfit_id"] == o.outfit_id
    try:
        PA.assemble(scene=SL.BY_ID["sc-park-bench"], product=_product("scarf"),
                    frame_role="lifestyle", laura=True, outfit=None)
    except PA.PromptAssemblyRefused:
        pass
    else:
        raise AssertionError("a Laura frame without an outfit was assembled")


def test_no_prompt_names_a_knitted_item_or_showroom_words_outside_the_product():
    import re

    n = 0
    for fam in SL.EVERY:
        o = OL.choose(f"k-{fam}", family=fam, product_colours=WINE)
        plan = G.plan_gallery(f"k-{fam}", product=_product(fam), outfit=o)
        for f in plan["frames"]:
            if not f["generate"]:
                continue
            for key in ("scene", "laura"):
                text = f["sections"][key]
                assert not H.problems(text), (fam, key, text)
                assert not re.search(rf"\b(?:{H.KNITTED_OR_CROCHETED})", text, re.I), \
                    (fam, key, text)
            n += 1
    assert n >= 13 * 6


# ---- 7. reference images only with activation ---------------------------------------------

def test_reference_images_are_held_without_owner_activation_and_never_call():
    db = _db()
    calls = []
    from brambleloop.gateway import paid_provider_gate as gate

    with patched(gate, "enforce", lambda *a, **k: calls.append(1)):
        r = OL.reference_request(db, "wl-chambray-indigo-boots")
    assert r["status"] == "HELD" and r["provider_called"] is False and not calls
    from brambleloop.creative import image_stages

    assert OL.REFERENCE_PROVIDER == image_stages.MODEL


def test_reference_request_is_ready_only_under_an_active_activation():
    import _paid_activation as PAA

    db = _db()
    PAA.activate(db, OL.REFERENCE_PROVIDER, "generation")
    r = OL.reference_request(db, "wl-chambray-indigo-boots")
    assert r["status"] == "READY" and r["provider_called"] is False, r


# ---- 8. mutations: each rule's test catches a broken rule ----------------------------------

def _mut_uniqueness():
    return [patched(OL, "_held_elsewhere", lambda db, listing: set()),
            patched(REG, "reserve", lambda db, oid, listing: {"status": "PASS", "why": "x",
                                                              "outfit_id": oid})]


def _mut_constant():
    return [patched(REG, "reserved_for", lambda db, listing: None)]


def _mut_gallery_outfit_check():
    real = G.check_gallery

    def no_outfit_check(plan):
        out = real(plan)
        out["problems"] = [p for p in out["problems"]
                           if p["kind"] not in ("more_than_one_outfit",
                                                "laura_without_outfit")]
        out["ok"] = not out["problems"]
        return out
    return [patched(G, "check_gallery", no_outfit_check)]


def _mut_harmony():
    return [patched(OL, "MIN_DELTA_E", 0.0), patched(OL, "CHROMA_MARGIN", 999.0)]


def _mut_props():
    import re

    return [patched(SL, "KIT_WORDS", re.compile(r"(?!x)x"))]


def _mut_plan():
    jobs = dict(G.JOB_OF_FRAME)
    jobs.pop("close_up")
    return [patched(G, "JOB_OF_FRAME", jobs)]


def _mut_determinism():
    real = PA.assemble
    counter = [0]

    def drifting(**kw):
        counter[0] += 1
        out = real(**kw)
        out["prompt"] += f" [{counter[0]}]"
        import hashlib

        out["prompt_sha256"] = hashlib.sha256(out["prompt"].encode()).hexdigest()
        return out
    return [patched(PA, "assemble", drifting)]


def _mut_filler():
    return [patched(G, "MAX_SCENE_OVERLAP", 2.0), patched(G, "MIN_PLACES", 0)]


MUTANTS = (
    ("outfit uniqueness", _mut_uniqueness, test_outfit_unique_across_listings),
    ("outfit constant", _mut_constant, test_outfit_constant_within_a_listing_and_durable),
    ("one outfit per gallery", _mut_gallery_outfit_check,
     test_check_gallery_refuses_two_outfits_or_a_laura_frame_without_one),
    ("colour harmony", _mut_harmony, test_colour_harmony_rule),
    ("misleading props", _mut_props, test_misleading_prop_rule),
    ("seven-role plan", _mut_plan, test_every_family_gets_a_valid_seven_role_plan),
    ("prompt determinism", _mut_determinism, test_prompt_determinism),
    ("repetitive filler", _mut_filler, test_filler_and_repeats_are_refused),
)


def test_each_rule_mutation_is_caught():
    assert len(MUTANTS) >= 7
    survived = []
    for name, mutant, test in MUTANTS:
        patches = mutant()
        for p in patches:
            p.__enter__()
        try:
            try:
                test()
            except AssertionError:      # the rule's own assertion kills the mutant
                continue
            survived.append(name)
        finally:
            for p in reversed(patches):
                p.__exit__(None, None, None)
    assert survived == [], f"mutants survived: {survived}"
    # And the unmutated tests pass (the mutants were killed by the rule, not by breakage).
    for _name, _mutant, test in MUTANTS:
        test()


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e)[:3000])
    sys.exit(1 if fails else 0)
