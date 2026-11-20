"""The lifestyle scene library: where each gallery frame is taken (ENG-WARDROBE-SCENES).

The owner's visual standard: MJ-level trustworthy product presentation together with
beautiful lifestyle scenes -- attractive, lived-in rooms, natural light, realistic staging,
people, and more than one environment per gallery (D-OWNER-CORE-FAMILIES §5, 2026-11-19).

**Scenes.** `SCENES` holds `len(SCENES)` (>= 40) scenes. Each names:
* a place (`PLACES`): rooms of Laura's home, the porch and garden of the same house, and
  outdoor settings away from home;
* the seasons it can be photographed in;
* a lighting key (`LIGHTING`): morning window light, golden hour, warm lamp light, ...;
* a camera: angle (the closed vocabulary ENG-LEARN reads, `CAMERA_ANGLES`), focal length in
  mm and depth of field;
* the frame roles it can serve (`FRAME_ROLES`, the seven roles of the campaign standard);
* the product families it suits, whether Laura may be in it, and its props.

**Laura's home stays one house.** An indoor scene in one of `laura_home.ROOMS` carries that
room's architecture verbatim (D-W4-OWNER-LAURA-HOME): the room is the same room in every
photograph; the vantage, light, moment and props vary. The reading nook is a corner of the
living room, the porch and the garden belong to the same house, and the craft room is its
spare room. Outdoor settings away from home add the multiple environments the 2026-11-19
directive asks for. Every scene text passes `laura_home.check` (no showroom, luxury or
"staged" vocabulary, no claim of a photographed sample).

**Props never mislead** (`prop_problems`, `misleading_text`). A prop must never imply the
pattern includes it:
* KNITWEAR: no other crocheted or knitted item (the shared `NO_OTHER_TEXTILES` rule);
* DECOY: nothing of the product's own kind (`laura_home.DECOY_FOR_CATEGORY`);
* KIT: nothing that reads as supplied with a pattern -- yarn, hooks, notions, a printed
  pattern, packaging, gift boxes, labels or tags (`KIT_WORDS`);
* NOT_ALLOWED: only props the family allows (`FAMILY_PROPS`);
* and every assembled prompt states that props are styling and not part of the pattern.

Deterministic data and checks. No model call, no network, CA$0.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

SCENE_LIBRARY_VERSION = "scene-library/1"

# The campaign standard's seven frame roles (`shot_plans.campaign_standard`), each with the
# gallery job it carries (one job per frame, #65) and the shot_plans role key the producer and
# ENG-LEARN record (`shot_plans.ROLE_OF_JOB`). "extra" is family-dependent (`extra_job`).
FRAME_ROLES: tuple[str, ...] = ("hero", "flat_lay", "lifestyle", "alt_angle", "close_up",
                                "scale_in_use", "extra")

CAMERA_ANGLES = ("three_quarter", "overhead", "side", "front", "close", "full_length")
DOF = ("shallow", "medium", "deep")

LIGHTING: dict[str, str] = {
    # The phrase each key writes. ENG-LEARN's LIGHTING vocabulary reads these words:
    # daylight/window light -> "daylight", lamp -> "warm_lamp". Never "studio".
    "morning_window": "soft morning window light, natural daylight",
    "north_window": "even north-window daylight",
    "overcast": "bright overcast daylight, soft shadows",
    "golden_hour": "warm golden-hour sunlight, low and soft",
    "lamp_glow": "warm lamp light in the evening, a table lamp switched on",
    "winter_daylight": "cool winter daylight reflected off snow",
    "dappled_shade": "dappled daylight through leaves",
}
LEARN_LIGHTING = {"morning_window": "daylight", "north_window": "daylight",
                  "overcast": "daylight", "golden_hour": "daylight",
                  "lamp_glow": "warm_lamp", "winter_daylight": "daylight",
                  "dappled_shade": "daylight"}

# place -> (indoor, laura_home room key or None, phrase)
PLACES: dict[str, tuple[bool, str | None, str]] = {
    "living_room": (True, "living_room", ""),
    "reading_nook": (True, "living_room", "the reading corner by the built-in shelves"),
    "nursery": (True, "nursery", ""),
    "kitchen": (True, "kitchen", ""),
    "dining": (True, "dining", ""),
    "bedroom": (True, "bedroom", ""),
    "entry": (True, "entry", ""),
    "craft_room": (True, None, "the spare room upstairs used as a craft room: a wide pine "
                               "work table under a window, white-oak-look laminate floor, "
                               "warm off-white walls, a pegboard of household tools"),
    "porch": (False, None, "the covered front porch of the same house: painted grey "
                           "floorboards, white railings, two wooden chairs"),
    "garden": (False, None, "the back yard of the same house: a small lawn, a cedar fence, "
                            "raised vegetable beds and a weathered picnic table"),
    "park": (False, None, "a neighbourhood park: mature maple trees, a gravel path and a "
                          "wooden bench"),
    "lakeside": (False, None, "a quiet lakeside dock in Ontario cottage country, pine trees "
                              "on the far shore"),
    "forest_trail": (False, None, "a mixed-forest walking trail, birch and pine, leaf litter "
                                  "underfoot"),
    "market": (False, None, "a small-town Saturday farmers' market, wooden stalls and "
                            "produce crates"),
    "orchard": (False, None, "an apple orchard at a family farm, rows of low trees"),
    "snowy_street": (False, None, "a quiet residential street after fresh snow, porches "
                                  "and bare trees"),
}

# ---- props ------------------------------------------------------------------------------
PROPS: dict[str, str] = {
    "mug_tea": "a ceramic mug of tea", "coffee_cup": "a cup of coffee on a saucer",
    "teapot": "a stoneware teapot", "bread_loaf": "a crusty loaf of bread",
    "apples": "a few red apples", "fruit_bowl": "a wooden bowl of fruit",
    "dinner_plates": "two plain stoneware plates", "cutlery": "simple steel cutlery",
    "water_glass": "a glass of water", "candle": "an unlit pillar candle in a holder",
    "houseplant": "a houseplant in a terracotta pot", "flowers_jar": "garden flowers in a jar",
    "paperbacks": "a short stack of paperbacks", "open_book": "an open hardback book",
    "reading_glasses": "a pair of reading glasses", "board_book": "a children's board book",
    "wooden_blocks": "a few plain wooden blocks", "keys": "a set of house keys",
    "sunglasses": "a pair of sunglasses", "mail": "a few envelopes of mail",
    "phone": "a phone face down", "notebook": "a plain notebook and a pencil",
    "picnic_hamper": "a wicker picnic hamper", "lemonade": "a jug of lemonade",
    "pinecones": "a few pinecones", "evergreen_sprig": "a sprig of evergreen",
    "tree_lights": "warm string lights on the tree", "wooden_tray": "a plain wooden tray",
    "pumpkin": "a small orange pumpkin", "leaves": "a few fallen maple leaves",
    "produce": "fresh vegetables in a paper bag", "laptop": "a closed laptop",
    "camera_bag_none": "", "snow_boots": "a pair of winter boots on the mat",
    "kettle": "a stovetop kettle", "jam_jar": "a jar of homemade jam",
}
# Words that make a prop read as part of what a pattern buyer receives, or as product.
KIT_WORDS = re.compile(r"\b(yarn|skeins?|balls? of wool|wool balls?|crochet hooks?|"
                       r"knitting needles?|stitch markers?|notions|pattern (?:book|booklet|"
                       r"printout|sheet|pages?)|printed pattern|instructions|kit|packag\w*|"
                       r"gift ?box(?:es)?|gift[- ]wrap\w*|gift tags?|price tags?|swatch\w*)\b",
                       re.I)

# Props each family may show. A prop outside the family's set is NOT_ALLOWED.
_TABLE = {"mug_tea", "coffee_cup", "teapot", "water_glass", "candle", "houseplant",
          "flowers_jar", "paperbacks", "open_book", "notebook", "wooden_tray"}
_HOME = {"houseplant", "paperbacks", "open_book", "reading_glasses", "mug_tea", "candle",
         "flowers_jar"}
_OUT = {"sunglasses", "leaves", "pinecones", "picnic_hamper", "lemonade", "apples", "produce",
        "flowers_jar", "pumpkin", "snow_boots", "keys"}
FAMILY_PROPS: dict[str, frozenset[str]] = {
    "basket": frozenset(_TABLE | {"bread_loaf", "apples", "fruit_bowl", "keys", "mail",
                                  "produce", "jam_jar", "pinecones", "kettle", "phone",
                                  "sunglasses"}),
    "coaster": frozenset(_TABLE | {"open_book", "reading_glasses", "kettle", "jam_jar"}),
    "placemat": frozenset(_TABLE | {"dinner_plates", "cutlery", "bread_loaf", "fruit_bowl",
                                    "jam_jar"}),
    "ornament": frozenset(_HOME | {"tree_lights", "evergreen_sprig", "pinecones",
                                   "wooden_tray", "coffee_cup"}),
    "blanket": frozenset(_HOME | _OUT | {"coffee_cup", "teapot", "wooden_tray", "pumpkin"}),
    "baby": frozenset({"board_book", "wooden_blocks", "houseplant", "flowers_jar",
                       "open_book", "water_glass"}),
    "pillow": frozenset(_HOME | {"coffee_cup", "wooden_tray", "teapot"}),
    "amigurumi": frozenset({"board_book", "wooden_blocks", "houseplant", "paperbacks",
                            "flowers_jar"}),
    "garment": frozenset(_HOME | _OUT | {"coffee_cup", "teapot"}),
    "scarf": frozenset(_HOME | _OUT | {"coffee_cup"}),
    "hat": frozenset(_HOME | _OUT | {"coffee_cup"}),
    "shawl": frozenset(_HOME | _OUT | {"coffee_cup", "teapot"}),
    "bag": frozenset(_OUT | {"phone", "notebook", "keys", "paperbacks", "mail",
                             "coffee_cup"}),
}
NOT_INCLUDED = ("Every other object in the frame is an everyday styling prop and is not "
                "part of the pattern.")


def prop_problems(prop: str, family: str, *, text: str | None = None) -> list[str]:
    """Every reason this prop may not appear with this product family (empty means allowed).

    `prop` is a `PROPS` key; `text` checks free prop text (e.g. from a learned template)."""
    from .laura_home import DECOY_FOR_CATEGORY, KNITTED_OR_CROCHETED

    fam = str(family or "").lower()
    words = text if text is not None else PROPS.get(prop)
    out = []
    if words is None:
        return [f"UNKNOWN_PROP: {prop!r} is not in the prop registry"]
    if not words:
        return [f"EMPTY_PROP: {prop!r} has no description"]
    m = re.search(rf"\b(?:{KNITTED_OR_CROCHETED})", words, re.I)
    if m:
        out.append(f"KNITWEAR: {m.group(0)!r} is a crocheted or knitted item beside the "
                   f"product")
    decoy = DECOY_FOR_CATEGORY.get(fam)
    if decoy:
        m = re.search(rf"\b(?:{decoy})", words, re.I)
        if m:
            out.append(f"DECOY: {m.group(0)!r} is of the product's own kind")
    m = KIT_WORDS.search(words)
    if m:
        out.append(f"KIT: {m.group(0)!r} reads as supplied with the pattern")
    if text is None and prop not in FAMILY_PROPS.get(fam, frozenset()):
        out.append(f"NOT_ALLOWED: {prop!r} is not a {fam or 'unknown-family'} prop")
    return out


def misleading_text(text: str, family: str) -> list[str]:
    """The misleading-prop rule over free text (an assembled scene or a learned brief)."""
    return [p for p in prop_problems("free-text", family, text=text) if not
            p.startswith(("UNKNOWN", "EMPTY"))]


# ---- scenes -----------------------------------------------------------------------------

@dataclass(frozen=True)
class Scene:
    key: str
    place: str
    vantage: str               # what this frame sees, in this place
    seasons: tuple[str, ...]
    lighting: str
    angle: str
    focal_mm: int
    dof: str
    roles: tuple[str, ...]
    families: tuple[str, ...]
    laura: bool                # Laura may be in this frame
    props: tuple[str, ...] = ()

    @property
    def scene_id(self) -> str:
        return f"sc-{self.key}"

    @property
    def indoor(self) -> bool:
        return PLACES[self.place][0]

    def environment(self) -> str:
        """The place, its architecture where it is a room of Laura's home, and the vantage."""
        from .laura_home import HOME_ID, HOUSE, ROOMS

        indoor, room_key, phrase = PLACES[self.place]
        if room_key:
            room = ROOMS[room_key]
            where = f"{room.name} of Laura's home ({HOME_ID}): {room.structure}; {room.anchors}"
            if phrase:
                where = f"{phrase} in {where}"
        elif self.place in ("craft_room", "porch", "garden"):
            where = f"{phrase} ({HOME_ID}; {HOUSE.split(':')[0]})"
        else:
            where = phrase
        return f"{where}. {self.vantage}"

    def camera_text(self) -> str:
        from . import scene_library as _  # noqa: F401 - keeps the phrase table local

        angle = {"three_quarter": "seen from a three-quarter angle",
                 "overhead": "seen from directly above, a flat lay",
                 "side": "seen from the side", "front": "seen straight on",
                 "close": "a close detail view", "full_length": "full length"}[self.angle]
        return f"{angle}; {self.focal_mm}mm lens, {self.dof} depth of field"

    def view(self) -> dict:
        return {"scene_id": self.scene_id, "place": self.place, "indoor": self.indoor,
                "seasons": list(self.seasons), "lighting": self.lighting,
                "camera": {"angle": self.angle, "focal_mm": self.focal_mm, "dof": self.dof},
                "roles": list(self.roles), "families": list(self.families),
                "laura": self.laura, "props": list(self.props),
                "environment": self.environment()}


S, U, A, W = "spring", "summer", "autumn", "winter"
ALL = (S, U, A, W)
HOME_GOODS = ("basket", "coaster", "placemat", "ornament")
SOFT = ("blanket", "baby", "pillow", "amigurumi")
WEAR = ("garment", "scarf", "hat", "shawl", "bag")
EVERY = HOME_GOODS + SOFT + WEAR

SCENES: tuple[Scene, ...] = (
    # ---- living room ----
    Scene("living-sofa-morning", "living_room", "The product on the sofa in the foreground.",
          ALL, "morning_window", "three_quarter", 35, "medium", ("hero", "lifestyle"),
          ("blanket", "baby", "pillow", "amigurumi", "basket", "shawl", "garment"), True,
          ("mug_tea", "paperbacks")),
    Scene("living-playmat", "living_room", "A play mat on the floor in front of the sofa, a "
          "quiet morning.", ALL, "morning_window", "three_quarter", 35, "medium",
          ("lifestyle", "scale_in_use"), ("baby", "amigurumi", "blanket"), True,
          ("board_book", "wooden_blocks")),
    Scene("living-mantel", "living_room", "Along the plain white mantel above the fireplace.",
          (A, W), "lamp_glow", "side", 50, "medium", ("alt_angle", "scale_in_use", "extra"),
          ("ornament", "pillow"), False, ("evergreen_sprig", "candle")),
    Scene("living-sofa-lamp", "living_room", "An evening on the sofa, the room dim beyond "
          "the lamp.", (A, W), "lamp_glow", "three_quarter", 50, "medium",
          ("lifestyle", "scale_in_use", "hero"), ("blanket", "pillow", "shawl", "garment"),
          True, ("coffee_cup", "open_book")),
    Scene("living-coffee-table", "living_room", "The low oak coffee table in the "
          "foreground, the sofa soft behind.", ALL, "overcast", "three_quarter", 50, "medium",
          ("hero", "alt_angle"), ("coaster", "basket", "ornament", "pillow"), False,
          ("mug_tea", "paperbacks", "candle")),
    Scene("living-floor-overhead", "living_room", "The product laid out on the light oak "
          "floor, seen from above.", ALL, "overcast", "overhead", 35, "deep", ("flat_lay",),
          ("blanket", "baby", "garment", "scarf", "shawl", "pillow"), False, ()),
    Scene("living-fireplace", "living_room", "Beside the plain white mantel, the fireplace "
          "lit.", (A, W), "lamp_glow", "side", 50, "medium", ("alt_angle", "lifestyle"),
          ("blanket", "pillow", "ornament", "shawl", "garment"), True,
          ("candle", "evergreen_sprig")),
    Scene("living-tree", "living_room", "The Christmas tree in the corner of the living "
          "room.", (W,), "lamp_glow", "three_quarter", 50, "shallow",
          ("hero", "lifestyle", "scale_in_use"), ("ornament",), True,
          ("tree_lights", "pinecones")),
    Scene("living-window-seat", "living_room", "By the wide front window, the street soft "
          "outside.", ALL, "north_window", "side", 85, "shallow", ("alt_angle",),
          ("blanket", "pillow", "garment", "scarf", "shawl", "amigurumi"), True,
          ("houseplant",)),
    # ---- reading nook ----
    Scene("nook-armchair", "reading_nook", "A worn armchair under a reading lamp.", ALL,
          "lamp_glow", "three_quarter", 35, "medium", ("lifestyle", "hero"),
          ("blanket", "shawl", "pillow", "garment", "amigurumi"), True,
          ("open_book", "reading_glasses", "mug_tea")),
    Scene("nook-shelf-detail", "reading_nook", "Close on the product against the book "
          "spines.", ALL, "north_window", "close", 100, "shallow", ("close_up",),
          ("blanket", "pillow", "shawl", "garment", "scarf", "amigurumi", "basket",
           "ornament"), False,
          ()),
    Scene("nook-window-morning", "reading_nook", "Morning in the reading corner, light "
          "across the chair arm.", (S, A, W), "morning_window", "front", 50, "medium",
          ("scale_in_use", "lifestyle"), ("blanket", "shawl", "garment", "scarf"), True,
          ("coffee_cup", "paperbacks")),
    # ---- nursery ----
    Scene("nursery-crib", "nursery", "The product draped over the white crib rail.", ALL,
          "morning_window", "three_quarter", 35, "medium", ("hero", "alt_angle"),
          ("baby", "amigurumi"), False, ("board_book",)),
    Scene("nursery-glider", "nursery", "In the glider chair in the corner, unhurried.", ALL,
          "north_window", "three_quarter", 35, "medium", ("lifestyle", "scale_in_use"),
          ("baby", "amigurumi", "pillow", "blanket"), True, ("board_book",)),
    Scene("nursery-window-chair", "nursery", "By the nursery window with the curtains open.",
          ALL, "morning_window", "front", 50, "medium", ("scale_in_use", "alt_angle"),
          ("baby", "amigurumi", "pillow"), True, ("flowers_jar",)),
    Scene("nursery-dresser", "nursery", "On top of the low white dresser.", ALL,
          "overcast", "side", 50, "medium", ("alt_angle", "extra"), ("amigurumi", "baby",
                                                                     "basket"), False,
          ("wooden_blocks", "houseplant")),
    Scene("nursery-floor-overhead", "nursery", "Laid out flat on the nursery floor rug, seen "
          "from above.", ALL, "north_window", "overhead", 35, "deep", ("flat_lay",),
          ("baby", "amigurumi", "blanket"), False, ()),
    Scene("nursery-macro", "nursery", "Close on the stitches in soft side light.", ALL,
          "morning_window", "close", 100, "shallow", ("close_up",), ("baby", "amigurumi"),
          False, ()),
    # ---- kitchen ----
    Scene("kitchen-table-breakfast", "kitchen", "Breakfast on the round pine table.", ALL,
          "morning_window", "three_quarter", 35, "medium", ("hero", "lifestyle"),
          ("coaster", "basket", "placemat"), True, ("mug_tea", "bread_loaf", "jam_jar")),
    Scene("kitchen-counter", "kitchen", "On the butcher-block counter by the window.", ALL,
          "overcast", "side", 50, "medium", ("alt_angle", "extra", "scale_in_use"),
          ("basket", "coaster"), False, ("kettle", "apples")),
    Scene("kitchen-table-overhead", "kitchen", "The pine table top seen from directly "
          "above.", ALL, "overcast", "overhead", 35, "deep", ("flat_lay",),
          ("coaster", "placemat", "basket", "ornament"), False, ()),
    Scene("kitchen-afternoon", "kitchen", "Late afternoon, light low across the table.",
          (A, W, S), "golden_hour", "front", 50, "medium", ("scale_in_use", "lifestyle"),
          ("coaster", "basket", "placemat"), True, ("mug_tea", "fruit_bowl")),
    Scene("kitchen-macro", "kitchen", "Close on the product's edge on the pine table.", ALL,
          "morning_window", "close", 90, "shallow", ("close_up",),
          ("coaster", "placemat", "basket"), False, ()),
    # ---- dining ----
    Scene("dining-set-for-two", "dining", "The oak table set for two.", ALL, "overcast",
          "three_quarter", 35, "medium", ("hero", "lifestyle", "scale_in_use"), ("placemat", "coaster"),
          True, ("dinner_plates", "cutlery", "water_glass")),
    Scene("dining-holiday", "dining", "A winter evening meal, candles on the table.", (W,),
          "lamp_glow", "three_quarter", 50, "shallow", ("lifestyle", "hero", "extra"),
          ("placemat", "ornament", "coaster", "basket"), True,
          ("candle", "evergreen_sprig", "dinner_plates")),
    Scene("dining-side", "dining", "Along the length of the table from the doorway.", ALL,
          "north_window", "side", 50, "medium", ("alt_angle", "scale_in_use"),
          ("placemat", "basket", "coaster"), False, ("fruit_bowl", "water_glass")),
    # ---- bedroom ----
    Scene("bedroom-bed", "bedroom", "The made bed, the product across the cream duvet.", ALL,
          "morning_window", "three_quarter", 35, "medium", ("hero", "alt_angle"),
          ("blanket", "baby", "pillow", "shawl", "garment"), False, ("open_book",)),
    Scene("bedroom-mirror", "bedroom", "Getting ready by the window, the bed behind.", ALL,
          "morning_window", "full_length", 50, "medium",
          ("hero", "scale_in_use", "lifestyle"), ("garment", "shawl", "scarf", "hat"), True,
          ()),
    Scene("bedroom-bed-overhead", "bedroom", "Laid flat on the cream duvet, seen from "
          "above.", ALL, "north_window", "overhead", 35, "deep", ("flat_lay",),
          ("garment", "scarf", "shawl", "hat", "bag", "blanket"), False, ()),
    Scene("bedroom-back-view", "bedroom", "From behind, facing the window light.", ALL,
          "north_window", "side", 50, "medium", ("alt_angle",),
          ("garment", "shawl", "scarf", "hat"), True, ()),
    # ---- entry ----
    Scene("entry-bench", "entry", "On the wooden coat bench by the front door.", ALL,
          "overcast", "three_quarter", 35, "medium", ("hero", "lifestyle", "scale_in_use"),
          ("basket", "bag", "hat", "scarf"), True, ("keys", "mail")),
    Scene("entry-leaving", "entry", "Heading out the front door.", (A, W, S), "overcast",
          "full_length", 35, "medium", ("lifestyle", "alt_angle"),
          ("hat", "scarf", "bag", "garment", "shawl"), True, ("keys", "snow_boots")),
    # ---- craft room ----
    Scene("craft-table", "craft_room", "On the wide pine work table under the window.",
          ALL, "north_window", "three_quarter", 50, "medium",
          ("hero", "alt_angle", "extra"), EVERY, False, ("notebook", "mug_tea")),
    Scene("craft-overhead", "craft_room", "The work table seen from directly above.", ALL,
          "north_window", "overhead", 35, "deep", ("flat_lay",), EVERY, False, ()),
    Scene("craft-macro", "craft_room", "Close on the stitches in raking window light.", ALL,
          "north_window", "close", 100, "shallow", ("close_up",), EVERY, False, ()),
    # ---- porch ----
    Scene("porch-chair", "porch", "In a wooden porch chair, the street beyond.", (S, U, A),
          "golden_hour", "three_quarter", 35, "medium", ("lifestyle", "hero", "scale_in_use"),
          ("blanket", "shawl", "garment", "scarf", "basket", "bag", "pillow"), True,
          ("coffee_cup", "pumpkin")),
    Scene("porch-steps", "porch", "On the porch steps.", (S, U, A), "overcast", "side", 50,
          "medium", ("alt_angle", "scale_in_use"), ("basket", "bag", "hat", "garment",
                                                    "blanket"), True, ("flowers_jar",)),
    Scene("porch-winter", "porch", "The porch after the first snow.", (W,),
          "winter_daylight", "full_length", 35, "medium", ("lifestyle", "hero"),
          ("hat", "scarf", "garment", "shawl", "basket", "ornament"), True,
          ("snow_boots", "evergreen_sprig")),
    # ---- garden ----
    Scene("garden-picnic-table", "garden", "On the weathered picnic table in the back yard.",
          (S, U), "dappled_shade", "three_quarter", 35, "medium",
          ("hero", "lifestyle", "scale_in_use"), ("basket", "placemat", "coaster", "blanket"),
          True, ("lemonade", "flowers_jar")),
    Scene("garden-lawn", "garden", "On the lawn by the raised beds.", (S, U, A),
          "golden_hour", "full_length", 50, "medium", ("lifestyle", "scale_in_use"),
          ("garment", "hat", "bag", "blanket", "shawl"), True, ("picnic_hamper",)),
    Scene("garden-harvest", "garden", "Picking from the raised vegetable beds.", (U, A),
          "overcast", "front", 35, "medium", ("scale_in_use", "lifestyle", "alt_angle"),
          ("basket", "bag", "hat"), True, ("produce",)),
    # ---- away from home ----
    Scene("park-bench", "park", "Sitting on the park bench under the maples.", (S, U, A),
          "dappled_shade", "three_quarter", 50, "shallow", ("lifestyle", "hero"),
          ("garment", "scarf", "hat", "shawl", "bag", "blanket"), True, ("coffee_cup",)),
    Scene("park-path", "park", "Walking the gravel path, mid-step.", (S, A), "golden_hour",
          "full_length", 85, "shallow", ("alt_angle", "lifestyle"),
          ("garment", "scarf", "hat", "bag", "shawl"), True, ("leaves",)),
    Scene("lakeside-dock", "lakeside", "On the end of the dock in the evening.", (U, S),
          "golden_hour", "three_quarter", 35, "medium", ("hero", "lifestyle"),
          ("blanket", "shawl", "garment", "hat", "bag"), True, ("sunglasses",)),
    Scene("lakeside-chair", "lakeside", "In a wooden deck chair facing the water.", (U, A),
          "golden_hour", "side", 50, "medium", ("alt_angle", "scale_in_use"),
          ("blanket", "shawl", "garment", "pillow"), True, ("mug_tea",)),
    Scene("trail-autumn", "forest_trail", "Pausing on the trail among the birches.", (A,),
          "dappled_shade", "full_length", 85, "shallow", ("lifestyle", "hero", "alt_angle"),
          ("garment", "scarf", "hat", "shawl"), True, ("leaves",)),
    Scene("trail-winter", "forest_trail", "A winter walk, snow on the pine boughs.", (W,),
          "winter_daylight", "full_length", 85, "shallow", ("lifestyle", "hero"),
          ("hat", "scarf", "garment", "shawl"), True, ()),
    Scene("market-stall", "market", "Browsing the produce crates at a market stall.",
          (S, U, A), "overcast", "three_quarter", 35, "medium",
          ("lifestyle", "scale_in_use", "hero"), ("bag", "basket", "hat", "scarf",
                                                  "garment"), True, ("produce", "apples")),
    Scene("orchard-ladder", "orchard", "Between rows of apple trees at picking time.",
          (A,), "golden_hour", "three_quarter", 50, "shallow",
          ("lifestyle", "hero", "scale_in_use"), ("basket", "bag", "garment", "hat",
                                                  "scarf", "shawl"), True, ("apples",)),
    Scene("snowy-street-walk", "snowy_street", "Walking home on the snowy street.", (W,),
          "winter_daylight", "full_length", 50, "medium", ("lifestyle", "alt_angle",
                                                          "scale_in_use"),
          ("hat", "scarf", "garment", "bag", "shawl"), True, ()),
    # ---- added for coverage: every family reaches seven distinct frames in every season ----
    Scene("living-shelves", "living_room", "On the built-in shelves beside the fireplace.",
          ALL, "north_window", "front", 50, "medium", ("scale_in_use", "extra", "alt_angle"),
          ("ornament", "amigurumi", "basket"), False, ("paperbacks", "houseplant")),
    Scene("kitchen-window", "kitchen", "Hanging in the window over the sink, the yard soft "
          "outside.", ALL, "morning_window", "front", 85, "shallow",
          ("hero", "scale_in_use", "lifestyle"), ("ornament",), True, ("houseplant",)),
    Scene("nook-chair-side", "reading_nook", "The armchair from the side, the shelves "
          "behind.", ALL, "north_window", "side", 50, "medium",
          ("scale_in_use", "alt_angle", "extra"), ("pillow", "amigurumi", "blanket", "shawl"),
          True, ("open_book",)),
    Scene("bedroom-reading", "bedroom", "Sitting up in bed with a book on a slow morning.",
          ALL, "morning_window", "three_quarter", 50, "medium", ("lifestyle", "scale_in_use"),
          ("pillow", "amigurumi", "shawl", "garment"), True, ("open_book", "coffee_cup")),
    Scene("entry-coat-hook", "entry", "Hanging from a coat hook by the front door.", ALL,
          "overcast", "front", 50, "medium", ("extra", "alt_angle", "scale_in_use"),
          ("bag", "hat", "scarf"), False, ("keys",)),
    Scene("craft-side", "craft_room", "The work table from the side, the window behind.",
          ALL, "north_window", "side", 50, "medium", ("extra", "alt_angle", "scale_in_use"),
          EVERY, False, ("notebook",)),
    Scene("dining-sideboard", "dining", "On the oak sideboard by the window.", ALL,
          "overcast", "front", 50, "medium", ("scale_in_use", "extra", "hero"),
          ("placemat", "basket", "ornament", "coaster"), False, ("flowers_jar", "candle")),
    Scene("garden-snow", "garden", "The back yard under fresh snow.", (W,),
          "winter_daylight", "front", 50, "medium",
          ("lifestyle", "scale_in_use", "alt_angle", "hero"),
          ("hat", "scarf", "garment", "shawl", "bag", "blanket"), True, ("snow_boots",)),
    Scene("living-sofa-arm", "living_room", "The sofa from its worn arm, snow light at the "
          "window.", (W, A), "winter_daylight", "side", 50, "medium",
          ("alt_angle", "scale_in_use"), ("blanket", "pillow", "shawl"), True,
          ("mug_tea",)),
)
BY_ID: dict[str, Scene] = {s.scene_id: s for s in SCENES}


def scene_problems(sc: Scene) -> list[str]:
    """Every library rule this scene breaks (empty means valid)."""
    from .laura_home import FORBIDDEN, KNITTED_OR_CROCHETED

    out = []
    if sc.place not in PLACES:
        out.append(f"place {sc.place!r} is not a known place")
        return out
    if sc.lighting not in LIGHTING:
        out.append(f"lighting {sc.lighting!r} is not a known lighting")
    if sc.angle not in CAMERA_ANGLES:
        out.append(f"angle {sc.angle!r} is not in {CAMERA_ANGLES}")
    if sc.dof not in DOF:
        out.append(f"depth of field {sc.dof!r} is not in {DOF}")
    if not (16 <= sc.focal_mm <= 200):
        out.append(f"focal length {sc.focal_mm}mm is not a household lens")
    if not sc.roles or set(sc.roles) - set(FRAME_ROLES):
        out.append(f"roles {sc.roles} are not frame roles")
    if not sc.seasons or set(sc.seasons) - set(ALL):
        out.append(f"seasons {sc.seasons} are not seasons")
    if not sc.families or set(sc.families) - set(EVERY):
        out.append(f"families {sc.families} are not known families")
    if "flat_lay" in sc.roles and sc.angle != "overhead":
        out.append("a flat-lay is seen from directly above")
    if "close_up" in sc.roles and (sc.angle != "close" or sc.dof != "shallow"):
        out.append("a close-up is a close view with shallow depth of field")
    if sc.angle in ("overhead", "close") and sc.laura:
        out.append("a flat-lay or close-up shows the product, not Laura")
    text = f"{sc.vantage} {PLACES[sc.place][2]} {LIGHTING.get(sc.lighting, '')}"
    m = FORBIDDEN.search(text)
    if m:
        out.append(f"{m.group(0)!r} is showroom or sample vocabulary (laura_home.FORBIDDEN)")
    m = re.search(rf"\b(?:{KNITTED_OR_CROCHETED})", text, re.I)
    if m:
        out.append(f"{m.group(0)!r} names a crocheted or knitted item in the scene")
    if re.search(r"\bstudio\b", text, re.I):
        out.append("'studio' reads as studio lighting, never a lived-in scene")
    for p in sc.props:
        if p not in PROPS or not PROPS[p]:
            out.append(f"prop {p!r} is not in the prop registry")
    return out


def library_problems() -> list[str]:
    ids = [s.scene_id for s in SCENES]
    out = [f"duplicate scene id {i}" for i in sorted({i for i in ids if ids.count(i) > 1})]
    out += [f"{s.scene_id}: {p}" for s in SCENES for p in scene_problems(s)]
    return out


def props_for(sc: Scene, family: str) -> tuple[list[str], list[dict]]:
    """The scene's props that may appear with this family, and each one dropped with why."""
    keep, dropped = [], []
    for p in sc.props:
        why = prop_problems(p, family)
        if why:
            dropped.append({"prop": p, "why": why})
        else:
            keep.append(p)
    return keep, dropped


def suits(sc: Scene, family: str) -> bool:
    """A scene suits a family when the family is listed AND nothing in its whole environment
    text (the room's own architecture included) is a decoy, knitwear or kit for that family:
    a bedroom duvet is a decoy beside a blanket, so the bedroom is not a blanket scene."""
    return family in sc.families and not misleading_text(sc.environment(), family)


def scenes_for(family: str, role: str, *, season: str = "") -> list[Scene]:
    return [s for s in SCENES if role in s.roles and suits(s, family)
            and (not season or season in s.seasons)]


def coverage() -> dict:
    """family -> role -> number of scenes (the planner needs at least one per used role)."""
    return {f: {r: len(scenes_for(f, r)) for r in FRAME_ROLES} for f in EVERY}
