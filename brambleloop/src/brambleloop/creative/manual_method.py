"""ENG-MANUAL-METHOD: the owner's October 28 manual FLUX 3 method, generalised (manual_method/1).

The owner made commercially attractive basket images by hand on dashboard.bfl.ai
(`brambleloop/research/MANUAL-METHOD-COMPARISON.md` compares that method with the factory's,
request by request). What the hand method did differently, and what this module reproduces for
every product from the product's own certified CIR:

1. **Product master.** Pages of the certified pattern PDF as the references (no CIR diagram
   renders), and an art-directed prose specification: the shape, the size at the stated gauge,
   the fibre, hook and stitch, the colour sequence written out in order ("8 cream rounds, 2 wine
   rounds, ..."), the plain final round, explicit negatives, then an editorial composition
   (surface, backdrop, light, camera). Square. No person, no room.
2. **Correction.** A targeted EDIT of the failed candidate ("Edit image 1 only to fix X"), with
   the PDF pages after it, naming the defect from the fidelity gate's failure codes. Never a
   blind full regeneration.
3. **Lifestyle.** Laura's three canonical references first, then the ACCEPTED product master
   bytes (and, for a vessel, the accepted side view the gate judged with it), then an approved
   room or campaign reference when one exists. The outfit is the listing's reservation.
4. **Styled product-only scenes.** The accepted master plus the room/campaign reference, with
   props chosen for the product's category, scaled to its certified size.

Every prompt states a positional authority map ("Image 1 is ..."), as the hand prompts did.

Nothing here is basket-specific: every number, colour and word about the product comes from
`pattern_refs.technical_rules` of the exact certified release. Deterministic and free: no model,
no provider, no network. The gates that judge the output are unchanged.
"""
from __future__ import annotations

from typing import Mapping, Sequence

from ..gateway import prompts

MANUAL_METHOD = "manual_method/1"
BUILDER_VERSION = "flux3-manual-builder/1.0.0"
_IMG = dict(system="", output_schema=("image",), max_output_tokens=1)

STITCH_NAMES = {
    "sc": "single crochet", "inc": "single crochet increases", "dec": "single crochet "
    "decreases", "hdc": "half double crochet", "dc": "double crochet", "tr": "treble crochet",
    "sl st": "slip stitch", "slst": "slip stitch", "ch": "chain", "fpdc": "front post double "
    "crochet", "bpdc": "back post double crochet", "bob": "bobble", "puff": "puff stitch",
    "v": "V-stitch", "shell": "shell stitch", "cl": "clusters",
}
POLYGON = {3: "triangle", 4: "square", 5: "pentagon", 6: "hexagon", 7: "heptagon", 8: "octagon"}
POLYGON_ADJ = {3: "triangular", 4: "square", 5: "pentagonal", 6: "hexagonal", 7: "heptagonal",
               8: "octagonal"}

# Editorial surfaces and backdrops, chosen per palette: the first one far enough (CIE delta E)
# from every yarn colour that the piece's every edge and band separates from it (the gate's
# reason for a contrasting ground, kept), but light, natural and commercial rather than a
# diagnostic mid-grey. Same rule as `image_stages.flat_lay_surface`.
SURFACES: tuple[tuple[str, str], ...] = (
    ("light natural oak", "#C9A97E"), ("honey-toned oak", "#B08850"),
    ("pale warm stone", "#A79F94"), ("smoked walnut", "#6F4E37"), ("soft slate", "#5E6B78"))
BACKDROPS: tuple[tuple[str, str], ...] = (
    ("warm greige", "#B5ADA2"), ("soft clay", "#B89A84"), ("muted sage", "#8E9A86"),
    ("warm taupe", "#8A8178"), ("deep stone", "#4E4A45"))
MIN_DELTA_E = 25.0


class ManualMethodRefused(ValueError):
    """The prompt cannot be built honestly from the certified facts."""


# ---- the pinned prompt templates -------------------------------------------------------------
PRODUCT = prompts.register(prompts.Prompt(
    name="image.flux3.manual.product", version="1", **_IMG, template=(
        "Create one photorealistic product visualization for Brambleloop Studio's crochet "
        "pattern listing. {reference_map} Use the attached pattern pages as the authoritative "
        "instructions for the finished item; never reproduce their page layout, text, charts "
        "or drawings in the image.\n\n"
        "{spec}\n\n{colours}\n\n{negatives}\n\n"
        "Photograph-style composition: {composition} Camera: {camera} Sharp fabric detail, "
        "realistic texture and depth, natural shadows. No person, hands, props, text, logo, "
        "watermark, collage or {second}. Output one square image. The product must "
        "faithfully represent the pattern rather than an embellished alternative.")))

CORRECTION = prompts.register(prompts.Prompt(
    name="image.flux3.manual.correction", version="1", **_IMG, template=(
        "Edit image 1 only, to fix: {defects}. {reference_map} The remaining attachments are "
        "the original pattern instructions and the authoritative product reference. Keep the "
        "camera, lighting, background, material, silhouette and all correct details of image "
        "1 unchanged. Preserve: {keep}. Do not add anything or redesign the item. Return one "
        "corrected product image, square.")))

LIFESTYLE = prompts.register(prompts.Prompt(
    name="image.flux3.manual.lifestyle", version="1", **_IMG, template=(
        "Create a photorealistic lifestyle photograph-style image for Brambleloop Studio.\n\n"
        "{reference_map} Preserve the appearance established by the three model references; "
        "do not redesign the model or copy the reference outfit. The product master controls "
        "the product's shape, size, colours, colour layout and crochet texture. {room_rule}\n\n"
        "{identity}\n\n"
        "Dress the model in {outfit}. Natural makeup and a relaxed expression. The outfit "
        "looks like everyday home styling. Preserve this outfit in every image of this "
        "listing.\n\n"
        "Scene: {environment}\n\n"
        "Action: {action} The {noun} remains clearly visible and in sharp focus; no fingers "
        "hide its colour layout. It is {size}: {scale}. Match the accepted product master; do "
        "not invent a different {noun}. {keep}\n\n"
        "Natural hand anatomy, realistic perspective and scale. Commercial home-and-lifestyle "
        "editorial photography, softly lit. No infant, no text, no logos, no watermark. One "
        "image.")))

STYLED = prompts.register(prompts.Prompt(
    name="image.flux3.manual.styled", version="1", **_IMG, template=(
        "Create a photorealistic product photograph-style image of the exact crochet {noun} "
        "in the product master. {reference_map} {room_rule} Keep the {noun} itself identical "
        "to the product master: {keep} It is {size}; props and furniture are scaled to "
        "it.\n\n"
        "{shot}\n\n"
        "{props} Keep the front and its colour layout unobstructed. No person, no hands, no "
        "child. {camera} Soft natural daylight, gentle background depth of field, a calm "
        "natural-home look. No text, watermark or logo. Output one square image.")))

SECTIONS = (PRODUCT, CORRECTION, LIFESTYLE, STYLED)


# ---- certified facts as art-directed prose ---------------------------------------------------
def _hexes(rules: Mapping) -> dict:
    return {c["id"]: c.get("hex") for c in rules.get("colours") or []}


def noun(rules: Mapping) -> str:
    """What the item is, in one or two plain words, from the certified title."""
    title = str(rules.get("title") or "item").lower()
    for word in ("basket", "coaster", "blanket", "throw", "runner", "placemat", "pillow",
                 "cushion", "ornament", "cardigan", "sweater", "hat", "beanie", "scarf",
                 "shawl", "bag", "tote", "stocking", "garland", "mat", "rug", "toy"):
        if word in title:
            n = int(rules.get("piece_count") or 1)
            return word + ("s" if n > 1 and word in ("coaster", "placemat", "ornament")
                           else "")
    return "crochet piece"


def _runs(seq: Sequence[str]) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    for c in seq:
        if out and out[-1][0] == c:
            out[-1] = (c, out[-1][1] + 1)
        else:
            out.append((c, 1))
    return out


def _phrase(run: tuple[str, int], unit: str) -> str:
    col, n = run
    return f"{n} {col} {unit}{'s' if n != 1 else ''}"


def _compress(runs: list[tuple[str, int]], unit: str) -> list[str]:
    """Run-length phrases, a block repeated three or more times said once with its count."""
    out, i = [], 0
    while i < len(runs):
        best = (1, 1)
        for k in (1, 2, 3, 4):
            block = runs[i:i + k]
            if len(block) < k:
                break
            n = 1
            while runs[i + n * k:i + (n + 1) * k] == block:
                n += 1
            if n >= 3 and n * k > best[0] * best[1]:
                best = (k, n)
        k, n = best
        if n >= 3:
            inner = ", ".join(_phrase(r, unit) for r in runs[i:i + k])
            out.append(f"then ({inner}) repeated {n} times")
            i += k * n
        else:
            out.append(_phrase(runs[i], unit))
            i += 1
    return out


def colour_sequence(rules: Mapping) -> str:
    """The colour layout written out in working order, from the certified facts."""
    hexes = _hexes(rules)
    pal = ", ".join(f"{c['id']} {c['hex']}" if c.get("hex") else str(c["id"])
                    for c in rules.get("colours") or [])
    v = rules.get("vessel") or {}
    f = rules.get("fabric") or {}
    if v.get("wall_bands"):
        base = ", ".join(v.get("base_colours") or []) or "as charted"
        walls = ", ".join(_phrase((b["colour"], int(b["rounds"])), "round")
                          for b in v["wall_bands"])
        ground = v["wall_bands"][0]["colour"]
        stripes = [b for b in v["wall_bands"] if b["colour"] != ground]
        text = (f"The base is {base}. Reading the wall from bottom to top: {walls}. Colours "
                f"{pal}, and no others.")
        if stripes:
            text += (f" Exactly {len(stripes)} continuous {stripes[0]['colour']} "
                     f"band{'s' if len(stripes) != 1 else ''} running level all the way "
                     f"round; the {ground} is dominant.")
        return text
    if f.get("multi_component"):
        return (f"Each piece is coloured exactly as the pattern pages chart it, in {pal} and "
                f"no other colour.")
    layout = f.get("colour_layout")
    ground = f.get("ground_colour")
    if layout == "single_colour":
        g = f"{ground} {hexes.get(ground) or ''}".strip() if ground else "one colour"
        return f"Worked entirely in {g}: no stripes or colour blocks."
    unit = f.get("unit") or "row"
    total = int(f.get("rows") or 0)
    if layout != "stripes":
        text = (f"The colourwork is exactly as charted on the pattern pages, in {pal} and no "
                f"other colour.")
        if f.get("colour_bands") and total and ground:
            # Rows mixing stitch heights (mosaic, relief): the yarn order is certain, the
            # surface is the chart's -- said as such, never as plain stripes.
            text += (f" The {unit}s are worked in this colour order, from the first: "
                     f"{', '.join(_compress(_runs(_worked(f, ground, total)), unit))}; the "
                     f"textured stitches carry colour over earlier {unit}s, so the surface "
                     f"follows the chart rather than plain stripes.")
        return text
    if not total or not ground:
        raise ManualMethodRefused("striped fabric without a row count or ground colour")
    seq = _worked(f, ground, total)
    phrases = _compress(_runs(seq), unit)
    if unit == "round":
        lead = "Reading the rounds from the centre outward"
    else:
        lead = "Reading the rows from the starting edge to the finishing edge"
    n_bands = len(f.get("colour_bands") or [])
    return (f"{lead}: {', '.join(phrases)}. That is {n_bands} contrast "
            f"band{'s' if n_bands != 1 else ''} in total on a {ground} ground. Colours "
            f"{pal}, and no others.")


def _worked(f: Mapping, ground: str, total: int) -> list[str]:
    seq = [ground] * total
    for b in f.get("colour_bands") or []:
        lo, hi = b["span"]
        for r in range(int(lo), int(hi) + 1):
            if 1 <= r <= total:
                seq[r - 1] = b["colour"]
    return seq


def _size(rules: Mapping) -> str:
    gm = (rules.get("garment") or {}).get("measures_cm") if rules.get("garment") else None
    if gm:
        return "built measurements " + ", ".join(f"{k} {v} cm" for k, v in gm.items())
    note = str(rules.get("finished_size_note") or "")
    if note:
        first = note.split(". Computed")[0].split(". Lies flat")[0].rstrip(".")
        first = first.removesuffix(", at the stated gauge").removesuffix(" at the stated gauge")
        return first + " (computed at the stated gauge, not measured on a sample)"
    c = (rules.get("components") or [{}])[0]
    if c.get("width_cm") and c.get("height_cm"):
        return f"about {c['width_cm']} x {c['height_cm']} cm at the stated gauge"
    return "true to the pattern's stated finished size"


def short_size(rules: Mapping) -> str:
    c = (rules.get("components") or [{}])[0]
    if (rules.get("vessel") or {}).get("wall_bands") and c.get("width_cm"):
        return (f"a small item approximately {c['width_cm']} cm wide and "
                f"{c.get('height_cm')} cm tall")
    if c.get("width_cm") and c.get("height_cm"):
        return f"approximately {c['width_cm']} x {c['height_cm']} cm"
    return "the pattern's stated finished size"


def _shape(rules: Mapping) -> str:
    f = rules.get("fabric") or {}
    poly, kind = f.get("polygon"), f.get("piece_shape")
    if f.get("multi_component"):
        return "Each piece has the shape the pattern pages show."
    if poly:
        name = POLYGON.get(int(poly["sides"]), f"{poly['sides']}-sided polygon")
        if kind == "vessel":
            adj = POLYGON_ADJ.get(int(poly["sides"]), f"{poly['sides']}-sided")
            return (f"Its flat base and its rim have {poly['sides']} sides and {poly['sides']} "
                    f"corners ({name}); the wall is straight and upright and the top is open. "
                    f"Retain a visibly {adj} silhouette.")
        return f"Each piece is a flat {name} with exactly {poly['sides']} corners."
    if kind == "vessel":
        return "A flat base with straight upright walls and an open top."
    if kind:
        return f"Its shape is a flat {kind}, as the pattern pages draw it."
    return "Its shape is as the pattern pages draw it."


def _material(rules: Mapping) -> str:
    yarns = sorted({c.get("yarn") for c in rules.get("colours") or [] if c.get("yarn")})
    g = rules.get("gauge") or {}
    raw = list(rules.get("stitches") or [])
    shaping = [s for s in raw if s in ("inc", "dec")]
    st = [STITCH_NAMES.get(s, s) for s in raw if s not in shaping]
    if shaping:
        st = [", ".join(st) + " with " + " and ".join(
            STITCH_NAMES[s].split(" ")[-1] for s in shaping)] if st else [
            STITCH_NAMES[s] for s in shaping]
    hook = f" with a {g['hook_mm']:g} mm hook" if g.get("hook_mm") else ""
    fibre = " and ".join(yarns) or "the pattern's yarn"
    return (f"It is made from {fibre}{hook} in {', '.join(st) or 'the charted stitches'}, at "
            f"{g.get('stitches_per_10cm')} stitches and {g.get('rows_per_10cm')} rows per 10 "
            f"cm. Show compact, recognisable crochet stitches and believable matte yarn "
            f"fibres, not knitting, rope, plastic or woven wicker.")


def _edge(rules: Mapping) -> str:
    f = rules.get("fabric") or {}
    last = f.get("final_round") or {}
    unit = f.get("unit") or "row"
    if f.get("edging_declared"):
        return "The edging is exactly as the pattern charts it, nothing more."
    if last.get("plain"):
        where = "The top ends" if f.get("piece_shape") == "vessel" else "The piece ends"
        return (f"{where} in the pattern's ordinary {last.get('colour')} final {unit}: no "
                f"added rim, braid, roll, border or trim.")
    if last.get("colour"):
        return (f"The outer edge is the final {unit} in {last['colour']}, exactly as charted; "
                f"nothing is worked beyond it.")
    return "No edging the pattern does not chart."


def product_spec(rules: Mapping) -> str:
    """The art-directed prose specification, from the certified facts only."""
    for key in ("title", "slug", "version", "colours", "components"):
        if not rules.get(key):
            raise ManualMethodRefused(f"certified rules are missing {key!r}")
    n = int(rules.get("piece_count") or 1)
    what = (f"{n} pieces" if n > 1 else f"one {noun(rules)}")
    return (f"The finished item is {what}: {rules['title']}, version {rules['version']}. "
            f"{_shape(rules)} Approximate finished size: {_size(rules)}. {_material(rules)} "
            f"{_edge(rules)}")


def negatives(rules: Mapping, extra: Sequence[str] = ()) -> str:
    negs = list(rules.get("negatives") or [])
    if not negs:
        raise ManualMethodRefused("certified rules carry no fabric negatives")
    negs += [n for n in extra if n not in negs]
    banned = "; ".join(rules.get("prohibited_additions") or [])
    return (f"It must not show: {'; '.join(negs)}. Never add: {banned}.")


def keep_line(rules: Mapping) -> str:
    """What every derivative keeps exactly, in one sentence."""
    return f"{_shape(rules)} {colour_sequence(rules)} {_edge(rules)}"


def _delta_e(a: str, b: str) -> float:
    from .image_stages import delta_e

    return delta_e(a, b)


def _pick(options, palette) -> tuple[str, str]:
    pal = [p for p in palette if p]
    for name, hx in options:
        if all(_delta_e(hx, p) >= MIN_DELTA_E for p in pal):
            return name, hx
    raise ManualMethodRefused(f"no editorial surface is {MIN_DELTA_E} delta E from every "
                              f"yarn colour {pal}")


def composition(rules: Mapping) -> dict:
    palette = [c.get("hex") for c in rules.get("colours") or []]
    s_name, s_hex = _pick(SURFACES, palette)
    b_name, b_hex = _pick(BACKDROPS, palette)
    return {"surface": s_name, "surface_hex": s_hex, "backdrop": b_name, "backdrop_hex": b_hex,
            "text": (f"the item alone on a {s_name} surface ({s_hex}) against a seamless "
                     f"{b_name} wall ({b_hex}), softly diffused window light, clean natural "
                     f"styling, centred, the entire item in frame with a margin on every "
                     f"side.")}


# The camera each gate-judged view needs. The fidelity gate reads these views; the camera is the
# gate's, the art direction is the hand method's.
CAMERA = {
    "flat": ("directly overhead, square to the item, every piece laid completely flat and "
             "unfolded with no folds, drape or tucked edges, so every edge and band is "
             "visible."),
    "top": ("straight down at 90 degrees over the centre of the opening of the empty item "
            "standing on its base, so the rim's whole outline and every corner are visible; "
            "nothing inside it."),
    "side": ("level with the middle of the wall, looking horizontally at one flat side of the "
             "empty item standing on its base; the top rim is seen edge-on as a straight line "
             "and the inside is not visible, so every colour band up the wall can be read."),
}


def _ref_map(roles: Sequence[str]) -> str:
    from .pdf_page_refs import LABELS

    labels = {
        "laura_face": "the canonical model face",
        "laura_torso": "the canonical model's natural upper-body proportions",
        "laura_body": "the canonical model's complete body proportions and silhouette",
        "product_master": "the accepted product master: the exact finished item to depict",
        "product_master_side": "the same accepted item from the side, standing",
        "correction_base": "the image to edit",
        "campaign_reference": ("the approved campaign image of this listing: use it only for "
                               "the location, light and styling, never for the product or the "
                               "person"),
        "scene_reference": ("the approved room: use it only for the location, never for the "
                            "product or the person"),
        "outfit": "the outfit (clothing only)"}
    labels.update({k: v.replace("page of the certified pattern PDF", "a page of the certified "
                                "pattern PDF") for k, v in LABELS.items()})
    return " ".join(f"Image {i + 1} is {labels.get(r.split(':')[0], r)}."
                    for i, r in enumerate(roles))


def _built(text: str, used, inputs: dict):
    from .flux_prompt import BuiltPrompt

    return BuiltPrompt(text=text.strip(), sections=tuple({"ref": p.ref, "sha256": p.sha256}
                                                         for p in used),
                       builder_version=BUILDER_VERSION, inputs=inputs)


def build_product(rules: Mapping, roles: Sequence[str], *, view: str,
                  extra_negatives: Sequence[str] = ()):
    if view not in CAMERA:
        raise ManualMethodRefused(f"unknown product view {view!r}")
    comp = composition(rules)
    camera = CAMERA[view]
    second = f"second {noun(rules)}" if int(rules.get("piece_count") or 1) == 1 else "extra piece"
    text = PRODUCT.render(reference_map=_ref_map(roles), spec=product_spec(rules),
                          colours=colour_sequence(rules),
                          negatives=negatives(rules, extra_negatives),
                          composition=comp["text"], camera=camera, second=second)
    return _built(text, (PRODUCT,), {"roles": tuple(roles), "view": view,
                                     "release": rules["release_hash"], "method": MANUAL_METHOD,
                                     "surface": comp["surface_hex"]})


# The defect named for each failure code, filled from the certified facts.
def defects_for(rules: Mapping, codes: Sequence[str]) -> list[str]:
    seq = colour_sequence(rules).rstrip(".")
    f = rules.get("fabric") or {}
    poly = f.get("polygon") or {}
    out = []
    for c in codes:
        c = str(c)
        if c in ("WRONG_COLOUR_LAYOUT", "basket:wall_bands", "coaster:colour_layout"):
            out.append(f"the colour layout; it must read exactly: {seq}")
        elif c in ("OFF_PALETTE_COLOUR", "basket:palette", "coaster:palette"):
            out.append("a yarn colour outside the palette; use only " + ", ".join(
                f"{x['id']} {x.get('hex') or ''}".strip() for x in rules.get("colours") or []))
        elif c in ("WRONG_REPEAT_COUNT", "basket:sides", "coaster:sides") and poly:
            out.append(f"the outline; it has exactly {poly['sides']} sides and "
                       f"{poly['sides']} corners")
        elif c == "WRONG_REPEAT_COUNT":
            out.append("the repeat count; it must match the pattern pages exactly")
        elif c in ("INVENTED_EDGING", "INVENTED_END_BAND_TREATMENT"):
            out.append("an edging, rim or border the pattern does not have; " + _edge(rules)
                       .rstrip("."))
        elif c == "WRONG_CRAFT_TEXTURE":
            out.append("the fabric texture; it is crochet in "
                       + ", ".join(STITCH_NAMES.get(s, s) for s in rules.get("stitches") or [])
                       + ", never knitting or rope")
        elif c == "WRONG_ASPECT_RATIO":
            out.append(f"the proportions; the item is {_size(rules)}")
        elif c == "WRONG_PIECE_COUNT":
            out.append(f"the number of pieces; there are exactly "
                       f"{int(rules.get('piece_count') or 1)}")
        elif c == "UNVERIFIABLE_COUNT":
            out.append("visibility; show the whole item uncropped and unfolded")
    seen, uniq = set(), []
    for d in out:
        if d not in seen:
            seen.add(d)
            uniq.append(d)
    return uniq


def build_correction(rules: Mapping, roles: Sequence[str], *, codes: Sequence[str]):
    defects = defects_for(rules, codes)
    if not defects:
        raise ManualMethodRefused(f"no targeted defect can be named for codes {list(codes)}; "
                                  f"a correction must say what to fix")
    if not roles or roles[0] != "correction_base":
        raise ManualMethodRefused("a correction edits image 1, the failed candidate")
    text = CORRECTION.render(defects="; ".join(defects), reference_map=_ref_map(roles),
                             keep=keep_line(rules).rstrip("."))
    return _built(text, (CORRECTION,), {"roles": tuple(roles), "codes": tuple(codes),
                                        "release": rules["release_hash"],
                                        "method": MANUAL_METHOD})


def _outfit_text(outfit: Mapping) -> str:
    g = dict(outfit.get("garments") or {})
    parts = [str(v) for k, v in g.items() if v and str(v).lower() != "none"]
    return ", ".join(parts) or str(outfit.get("description") or "")


def build_lifestyle(rules: Mapping, roles: Sequence[str], *, outfit: Mapping, environment: str,
                    action: str, identity: str):
    if tuple(roles[:3]) != ("laura_face", "laura_torso", "laura_body") or \
            "product_master" not in roles:
        raise ManualMethodRefused("lifestyle sends the canonical three, then the accepted "
                                  "product master")
    o = _outfit_text(outfit)
    if not o:
        raise ManualMethodRefused("a Laura image needs the listing's reserved outfit")
    room = ("If an approved room or campaign image is attached, use it only for the location, "
            "never to alter the product or the model." if any(
                r in roles for r in ("campaign_reference", "scene_reference")) else "")
    n = noun(rules)
    text = LIFESTYLE.render(
        reference_map=_ref_map(roles), room_rule=room, identity=identity, outfit=o,
        environment=environment.strip(), action=(action or f"She uses the {n} naturally.")
        .strip().rstrip(".") + ".", noun=n, size=short_size(rules),
        scale="keep it at that real size against her hands and the furniture",
        keep=keep_line(rules))
    return _built(text, (LIFESTYLE,), {"roles": tuple(roles), "release": rules["release_hash"],
                                       "outfit": o, "method": MANUAL_METHOD})


# Category props: what is believably in, on or beside the item, at its scale. The house rule
# (`visual.laura_home.NO_OTHER_TEXTILES`) forbids any other crocheted or knitted item.
PROPS: dict[str, str] = {
    "basket": ("Style it realistically with a restrained arrangement of everyday things that "
               "fit inside it without stretching or enlarging it: a few rolled linen tea "
               "towels, a small wooden spoon and a folded cotton napkin."),
    "nursery": ("Style it realistically as small nursery storage with rolled white cloth "
                "nappies, folded cream or sage muslin cloths and one small wooden rattle; the "
                "contents fit within it without stretching or enlarging it."),
    "coaster": ("One coaster under a ceramic mug of tea, the others stacked neatly beside it, "
                "with a small plate and a teaspoon."),
    "placemat": "Set with a plain ceramic plate, a linen napkin and simple cutlery.",
    "runner": "Down the centre of a wooden table with a ceramic jug and a few candles.",
    "blanket": ("Folded loosely over the arm of a cream sofa with one corner falling so the "
                "edge and the colour layout are visible."),
    "garment": "Laid on a wooden hanger against the wall, with a pair of plain leather shoes.",
    "pillow": "On an oatmeal linen sofa beside a plain cushion.",
    "ornament": "Hung from a bare branch in a ceramic vase.",
}
SHOTS: dict[str, str] = {
    "hero": ("A three-quarter editorial composition, the item the clear subject in sharp focus "
             "and set where it lives."),
    "colour_context": ("Show the same item directly overhead on a plain natural surface, "
                       "every piece visible, no props or perspective distortion."),
    "angle": ("Show the exact same item from a different three-quarter angle with consistent "
              "materials, shape and colour layout. Do not redesign it."),
    "detail": ("A macro close-up of the same stitches: preserve the colour transitions and the "
               "final round, realistic yarn fibres, no knitted or rope texture."),
    "size": ("Show the same item beside everyday objects of known size so its real size is "
             "clear. No unsupported size label."),
}


def props_for(category: str, room: str) -> str:
    cat = str(category or "").lower()
    if room == "nursery" and cat in ("basket", "nursery"):
        return PROPS["nursery"]
    for key in (cat, room):
        if key in PROPS:
            return PROPS[key]
    for key in PROPS:
        if key in cat:
            return PROPS[key]
    return "Style it with a few plain everyday objects that suit where it lives."


def build_styled(rules: Mapping, roles: Sequence[str], *, role: str, brief: str,
                 category: str, room: str, room_cue: str):
    if not roles or roles[0] != "product_master":
        raise ManualMethodRefused("a styled scene sends the accepted product master first")
    has_room = any(r in roles for r in ("campaign_reference", "scene_reference"))
    room_rule = (f"Use the approved room or campaign image for the same setting ({room_cue}); "
                 f"it never changes the product." if has_room else
                 f"The setting: {room_cue}.")
    shot = SHOTS.get(role, SHOTS["hero"]) + (f" Brief: {brief.strip()}." if brief else "")
    camera = ("Camera: directly overhead." if role == "colour_context" else
              "Camera: a slightly elevated three-quarter view.")
    props = ("No props." if role in ("colour_context", "angle", "detail")
             else props_for(category, room))
    text = STYLED.render(noun=noun(rules), reference_map=_ref_map(roles), room_rule=room_rule,
                         keep=keep_line(rules), size=short_size(rules), shot=shot, props=props,
                         camera=camera)
    return _built(text, (STYLED,), {"roles": tuple(roles), "role": role,
                                    "release": rules["release_hash"], "method": MANUAL_METHOD})
