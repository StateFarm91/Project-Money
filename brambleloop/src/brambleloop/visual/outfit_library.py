"""The approved outfit library: complete outfits for Laura, as code (ENG-WARDROBE-SCENES).

The owner's visual standard (D-OWNER-CORE-FAMILIES §5, 2026-11-19, and D-W4-LAURA-OUTFIT):

* Laura's identity (`canonical.IDENTITY_ID`, laura-r2-a42aeac7) is locked. An outfit is
  styling, never identity.
* Each listing gets ONE complete outfit, the same in every frame of its gallery, and a
  DIFFERENT approved outfit from every other listing.
* The product stays the hero.

What this module adds to `outfits` (the durable registry and reservation) and `wardrobe` (the
similarity measure):

* **A library** of `LIBRARY_SIZE` complete outfits (`LIBRARY`). Each has a stable id, a text
  spec per garment slot, an arrangement of Laura's own hair (`HAIR_STYLINGS`), a palette of
  named colours with sRGB values, season and occasion tags, and a formality.
* **Library rules**, checked in code on every outfit (`outfit_problems`):
  - complete: a top or dress, a lower garment unless it is a dress, footwear;
  - no branded clothing, no logos or lettering (`BRAND_OR_LOGO`);
  - nothing revealing (`REVEALING`);
  - no knitted or crocheted garment (`laura_home.KNITTED_OR_CROCHETED`): a knitted cardigan
    next to a crochet product reads as part of it, and every frame states that no other
    crocheted or knitted item is in the scene;
  - every large garment names a palette colour (`COLOURS`), so harmony can be measured;
  - styling never names an identity feature (`outfits._IDENTITY_WORDS`), and the hair
    arrangement is a closed list that never changes colour, length, cut or texture.
* **Pairwise distinctness.** Every library outfit is below `wardrobe.MAX_SIMILARITY` against
  every other one and against the canonical references' clothing, so any two listings that
  hold library outfits are distinct by the registry's own measure.
* **Family compatibility** (`compatible`): how the product meets Laura decides what she can
  wear with it. A garment listing has Laura wearing the product, so the outfit is the base
  layer beneath it (no outerwear, no top layer of its own). A held product (blanket, baby,
  pillow, amigurumi) gets indoor clothes and, for baby items, no dangling necklace or bag.
* **Colour harmony** (`harmony`): the product's yarn colours against the outfit palette, in
  CIELAB. The product stays the hero:
  - CAMOUFLAGE: a large garment closer than `MIN_DELTA_E` to a yarn colour would merge with
    the product at its edges;
  - COMPETITION: an outfit colour more chromatic than the product's own most chromatic yarn
    plus `CHROMA_MARGIN` (or `CHROMA_FLOOR` for very quiet products) outshouts it.
  Only the large garments (top or dress, lower, outerwear) are measured: footwear and small
  accessories are too small a share of the frame to compete with or hide the product.
* **Claim** (`claim_for_listing`): the listing's held outfit if it has one (constant within a
  listing, any number of calls and restarts). Otherwise the first library outfit, in a stable
  per-listing order, that is compatible, harmonious, in season and not held by any other
  listing. It is registered, approved as a library outfit and reserved through
  `outfits.reserve`, which is the durable, unique reservation (`laura_outfits.listing`). An
  outfit is never reused while it is held, and a retired outfit stays bound to its listing.
* **Reference images** are never generated here. `reference_request` says what an outfit
  reference image would be and whether the owner's FLUX activation is live
  (`paid_provider_gate.activation_state`). It never calls a provider: with activation it
  hands the request to the existing producer, whose `enforce` is the only spend point.

Deterministic text and arithmetic. No model call, no network, CA$0.
"""
from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field

LIBRARY_VERSION = "outfit-library/1"
APPROVED_BY = "code:outfit_library/1"   # approved by the library's rules, not by the owner
ID_PREFIX = "wl"

# ---- palette -----------------------------------------------------------------------------
# Every colour word `wardrobe` parses, with an sRGB value. A garment's colour is the first of
# these its text names. The values are ordinary dyed-cloth shades, not brand colours.
COLOURS: dict[str, str] = {
    "ivory": "#F6F1E1", "cream": "#F3EBD3", "white": "#F7F7F4", "oatmeal": "#DDD2BC",
    "stone": "#B8AE9C", "beige": "#D4C3A3", "ecru": "#E2D7BD", "tan": "#C19A6B",
    "camel": "#B5875A", "brown": "#6A4A36", "rust": "#A0522D", "cognac": "#8B4A2B",
    "black": "#1E1E1E", "charcoal": "#3B3E42", "navy": "#1F2B47", "indigo": "#2F3B5C",
    "denim": "#4B6385", "blue": "#5A7BAE", "chambray": "#8EA3BF", "grey": "#8D8F93",
    "gray": "#8D8F93", "heather": "#A4A2A8", "sage": "#9DAE8B", "olive": "#6B6B3D",
    "green": "#4E7A50", "forest": "#2F4F3B", "red": "#A33A35", "burgundy": "#6B2535",
    "wine": "#6A2331", "rose": "#C08A8E", "pink": "#DDA7B2", "blush": "#E5C5BF",
    "mustard": "#C49E3E", "yellow": "#DDBF5A", "gold": "#C4A257", "silver": "#B9BDC2",
    "lilac": "#B8A7C8", "plum": "#5D3B57",
}

HAIR_STYLINGS: dict[str, str] = {
    # An arrangement of her canonical hair. Colour, length, cut and texture never change.
    "loose": "her own hair worn loose and natural",
    "tucked": "her own hair tucked behind her ears",
    "low_pony": "her own hair in a soft low ponytail",
    "low_bun": "her own hair in a loose low bun",
    "half_up": "her own hair half up, half down",
    "side_braid": "her own hair in a loose side braid",
}
HAIR_LOCK = ("her hair colour, length, cut and texture exactly as in the canonical "
             "references")
# A hair arrangement that names one of these changes her hair rather than arranging it.
_HAIR_CHANGE = re.compile(r"\b(blonde?|brunette|red|auburn|black|grey|gray|dyed?|highlights?|"
                          r"balayage|ombre|bob|pixie|fringe|bangs|short(?:er)?|long(?:er)?|"
                          r"curl(?:s|y|ed)?|straighten(?:ed)?|perm|wig|extensions?|shaved)\b",
                          re.I)

SEASONS = ("spring", "summer", "autumn", "winter")
OCCASIONS = ("at_home", "weekend", "gathering", "holiday", "outdoor", "crafting", "market")
FORMALITY = ("relaxed", "casual", "smart")

# ---- library rules -------------------------------------------------------------------------
BRAND_OR_LOGO = re.compile(
    r"\b(logo\w*|brand(?:ed)?|monogram\w*|slogan|lettering|graphic|printed text|wordmark|"
    r"designer|nike|adidas|puma|reebok|converse|vans|keds|superga|veja|levi'?s?|wrangler|"
    r"ugg?s?|birkenstocks?|crocs|dr\.? ?martens|docs|hunter|barbour|burberry|chanel|gucci|"
    r"prada|patagonia|north face|zara|h&m|uniqlo|lululemon|ray-?ban|timberland|clarks|"
    r"blundstones?)\b", re.I)
REVEALING = re.compile(
    r"\b(mini|micro|crop(?:ped)? (?:top|tee|tank|shirt|blouse)|sheer|see-?through|mesh|"
    r"low-?cut|plunging|deep v|strapless|backless|bodycon|bralette|bra|lingerie|bikini|"
    r"swim\w*|hot pants|shorts|slit|tube top|halter|spaghetti strap|bustier|corset|"
    r"tank top|camisole)\b", re.I)
_LARGE_SLOTS = ("top_or_dress", "lower", "outerwear")


@dataclass(frozen=True)
class Outfit:
    key: str
    top_or_dress: str
    lower: str
    shoes: str
    outerwear: str
    accessories: str
    hair: str
    seasons: tuple[str, ...]
    occasions: tuple[str, ...]
    formality: str
    extra: dict = field(default_factory=dict, compare=False)

    @property
    def outfit_id(self) -> str:
        return f"{ID_PREFIX}-{self.key}"

    @property
    def garments(self) -> dict:
        return {"top_or_dress": self.top_or_dress, "lower": self.lower, "shoes": self.shoes,
                "outerwear": self.outerwear or "none",
                "accessories": self.accessories or "none"}

    @property
    def is_dress(self) -> bool:
        t = self.top_or_dress.lower()
        # The registry's own rule (`outfits.register`): only a dress or pinafore has no lower.
        return "dress" in t or "pinafore" in t

    def palette(self) -> list[dict]:
        out = []
        for slot, text in self.garments.items():
            name = colour_of(text)
            if name:
                out.append({"slot": slot, "colour": name, "hex": COLOURS[name]})
        return out

    def text_spec(self) -> str:
        g = self.garments
        parts = [g["top_or_dress"]] + ([g["lower"]] if g["lower"] else []) + [g["shoes"]]
        if g["outerwear"] != "none":
            parts.append(g["outerwear"])
        if g["accessories"] != "none":
            parts.append(g["accessories"])
        return "; ".join(parts)

    def view(self) -> dict:
        return {"outfit_id": self.outfit_id, "library_version": LIBRARY_VERSION,
                "garments": self.garments, "hair_styling": self.hair,
                "hair_text": HAIR_STYLINGS.get(self.hair, ""), "palette": self.palette(),
                "seasons": list(self.seasons), "occasions": list(self.occasions),
                "formality": self.formality, "text_spec": self.text_spec(),
                "families": [f for f in FAMILIES if compatible(self, f)["ok"]]}


def colour_of(text: str) -> str | None:
    """The first palette colour a garment text names (word-bounded), else None."""
    t = " " + re.sub(r"[^a-z/ -]", " ", str(text or "").lower()) + " "
    best = None
    for name in COLOURS:
        m = re.search(rf"[ /-]{name}[ /-]", t)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), name)
    return best[1] if best else None


# ---- the library ---------------------------------------------------------------------------
# (key, top or dress, lower, shoes, outerwear, accessories, hair, seasons, occasions,
#  formality). Woven and jersey cloth only: no knitwear, so nothing in the outfit reads as a
# second crochet or knitted piece beside the product.
S, U, A, W = "spring", "summer", "autumn", "winter"
_ROWS: tuple[tuple, ...] = (
    ("chambray-indigo-boots", "chambray button-down shirt", "dark indigo straight-leg jeans",
     "brown leather ankle boots", "", "small gold hoop earrings", "loose",
     (S, A, W), ("at_home", "weekend"), "casual"),
    ("navy-breton-stone-chinos", "navy striped breton tee", "stone cotton chinos",
     "white canvas sneakers", "", "leather-strap watch", "low_pony",
     (S, U), ("weekend", "outdoor", "market"), "casual"),
    ("olive-shirtdress-tan-sandal", "olive linen shirt dress", "",
     "tan leather sandals", "", "thin gold chain necklace", "half_up",
     (U,), ("weekend", "gathering", "market"), "casual"),
    ("charcoal-tee-camel-coat", "charcoal crew-neck tee", "black tailored wool trousers",
     "black leather loafers", "camel wool coat", "silver stud earrings", "low_bun",
     (A, W), ("outdoor", "holiday", "gathering"), "smart"),
    ("rust-blouse-denim-skirt", "rust cotton blouse", "denim midi skirt",
     "brown suede clogs", "", "tortoiseshell barrette", "tucked",
     (S, A), ("weekend", "market", "crafting"), "casual"),
    ("burgundy-wrap-navy-trouser", "burgundy wrap blouse", "navy wide-leg trousers",
     "tan suede ballet flats", "", "small gold stud earrings", "low_pony",
     (A, W, S), ("gathering", "holiday"), "smart"),
    ("sage-linen-shirt-white-jeans", "sage linen shirt", "white straight-leg jeans",
     "tan leather slides", "", "gold pendant necklace", "loose",
     (S, U), ("weekend", "outdoor", "gathering"), "casual"),
    ("mustard-tee-olive-cargo", "mustard cotton tee", "olive cargo trousers",
     "grey suede sneakers", "denim jacket", "leather belt", "low_pony",
     (S, A), ("outdoor", "market", "weekend"), "relaxed"),
    ("blue-poplin-charcoal-skirt", "blue poplin shirt", "charcoal pleated midi skirt",
     "black leather knee-high boots", "", "silver hoop earrings", "low_bun",
     (A, W), ("gathering", "holiday"), "smart"),
    ("forest-flannel-light-jeans", "forest checked flannel shirt", "light-wash blue wide-leg jeans",
     "brown leather lace-up boots", "quilted olive vest", "leather-strap watch", "side_braid",
     (A, W), ("outdoor", "weekend"), "relaxed"),
    ("blush-blouse-camel-trouser", "blush silk-look blouse", "camel tailored trousers",
     "white leather sneakers", "", "thin gold chain necklace", "half_up",
     (S, U, A), ("gathering", "weekend"), "smart"),
    ("grey-sweatshirt-black-legging", "heather grey fleece sweatshirt", "black leggings",
     "grey wool slippers", "", "none", "low_bun",
     (A, W), ("at_home", "crafting"), "relaxed"),
    ("white-tee-denim-jacket-skirt", "white crew-neck tee", "olive linen midi skirt",
     "white canvas plimsolls", "denim jacket", "woven straw bag", "loose",
     (S, U), ("market", "outdoor", "weekend"), "casual"),
    ("lilac-shirt-grey-trouser", "lilac cotton shirt", "grey tailored cropped trousers",
     "black leather loafers", "", "silver stud earrings", "low_pony",
     (S, U), ("gathering", "weekend"), "smart"),
    ("black-rollneck-rust-cord", "black jersey roll-neck top", "rust corduroy wide-leg trousers",
     "brown leather ankle boots", "", "gold hoop earrings", "loose",
     (A, W), ("at_home", "gathering", "holiday"), "casual"),
    ("stone-trench-navy-tee", "navy long-sleeve tee", "dark indigo slim jeans",
     "white canvas sneakers", "stone cotton trench coat", "leather crossbody bag", "low_pony",
     (S, A), ("outdoor", "market"), "casual"),
    ("charcoal-blazer-white-shirt", "white cotton shirt", "charcoal tailored trousers",
     "burgundy suede ballet flats", "charcoal wool blazer", "thin gold chain necklace", "low_bun",
     (S, A, W), ("gathering", "holiday"), "smart"),
    ("oatmeal-overshirt-black-jeans", "black cotton tee", "black straight-leg jeans",
     "olive suede clogs", "oatmeal cotton overshirt jacket", "silver ring", "tucked",
     (S, A), ("crafting", "weekend", "at_home"), "relaxed"),
    ("rose-blouse-indigo-culotte", "rose cotton blouse with puff sleeves", "indigo denim culottes",
     "brown leather sandals", "", "pearl drop earrings", "half_up",
     (S, U), ("gathering", "market"), "casual"),
    ("navy-quilted-jacket-cord", "cream oxford shirt", "olive corduroy straight trousers",
     "brown leather lace-up boots", "navy quilted jacket", "leather-strap watch", "side_braid",
     (A, W), ("outdoor", "weekend"), "casual"),
    ("indigo-smock-top-stone-skirt", "indigo cotton smock top", "stone cotton a-line skirt",
     "white leather sneakers", "", "silver hoop earrings", "tucked",
     (S, A), ("crafting", "weekend"), "casual"),
    ("grey-tee-green-coat", "grey cotton tee", "black wide-leg trousers",
     "black leather chelsea boots", "forest wool coat", "silver stud earrings", "loose",
     (A, W), ("outdoor", "holiday"), "smart"),
    ("white-blouse-navy-culotte", "white broderie cotton blouse", "navy linen culottes",
     "tan leather mules", "", "leather-strap watch", "loose",
     (U, S), ("gathering", "market"), "smart"),
    ("plum-tee-grey-jogger", "plum jersey long-sleeve tee", "grey cotton joggers",
     "grey felt slippers", "", "none", "low_pony",
     (A, W), ("at_home",), "relaxed"),
    ("olive-shirt-cream-trouser", "olive utility shirt", "cream wide-leg trousers",
     "brown leather loafers", "", "gold pendant necklace", "tucked",
     (S, A), ("weekend", "gathering"), "smart"),
    ("navy-gilet-blue-shirt", "blue oxford shirt", "stone cotton chinos",
     "navy suede sneakers", "navy quilted vest", "leather-strap watch", "low_pony",
     (S, A), ("outdoor", "weekend"), "casual"),
    ("grey-blazer-black-tee", "black jersey tee", "dark indigo straight-leg jeans",
     "black leather ballet flats", "grey wool blazer", "thin gold chain necklace", "low_bun",
     (S, A, W), ("gathering", "market"), "smart"),
    ("white-shirt-olive-skirt", "white linen shirt", "olive pleated midi skirt",
     "tan leather sandals", "", "woven straw bag", "low_pony",
     (U, S), ("market", "outdoor"), "casual"),
    ("navy-shirt-camel-coat-skirt", "navy silk-look blouse", "charcoal wool midi skirt",
     "black leather ankle boots", "camel wool wrap coat", "pearl drop earrings", "low_bun",
     (W,), ("holiday", "outdoor"), "smart"),
    ("lilac-tee-white-jeans", "lilac cotton tee", "white wide-leg jeans",
     "silver leather sandals", "", "silver hoop earrings", "loose",
     (U,), ("weekend", "gathering"), "casual"),
    ("brown-cord-jacket-tee", "white long-sleeve tee", "black straight trousers",
     "white leather sneakers", "brown corduroy jacket", "silver chain necklace", "tucked",
     (S, A), ("market", "weekend"), "casual"),
    ("black-dress-grey-coat", "black long-sleeve jersey midi dress", "",
     "black leather knee-high boots", "grey wool coat", "silver hoop earrings", "low_bun",
     (W,), ("holiday", "outdoor", "gathering"), "smart"),
    ("white-tee-rust-skirt", "white jersey tee", "rust corduroy midi skirt",
     "tan suede clogs", "", "gold hoop earrings", "half_up",
     (A,), ("crafting", "market"), "casual"),
    ("navy-henley-stone-trouser", "navy cotton henley", "stone wide-leg linen trousers",
     "tan leather slides", "", "silver ring", "loose",
     (U, S), ("at_home", "weekend"), "relaxed"),
    ("burgundy-tee-grey-skirt", "burgundy jersey long-sleeve tee", "grey wool midi skirt",
     "brown leather chelsea boots", "", "gold pendant necklace", "low_pony",
     (A, W), ("holiday", "at_home"), "casual"),
    ("stone-dress-navy-blazer", "stone linen midi dress with cap sleeves", "",
     "navy leather loafers", "navy wool blazer", "small pearl stud earrings", "tucked",
     (S,), ("gathering",), "smart"),
    ("plum-pinafore-tights-boots", "plum corduroy pinafore dress over a white long-sleeve tee", "black opaque tights",
     "black lace-up boots", "", "silver ring", "side_braid",
     (A, W), ("at_home", "crafting"), "casual"),
    ("brown-henley-grey-cord", "brown cotton henley", "grey corduroy straight trousers",
     "olive suede clogs", "", "silver chain necklace", "tucked",
     (A, W), ("at_home", "crafting"), "casual"),
    ("denim-shirtdress-gilet", "denim shirt dress with rolled sleeves", "",
     "tan suede ankle boots", "quilted olive vest", "leather belt", "half_up",
     (S, A), ("weekend", "outdoor"), "casual"),
    ("green-tea-dress-cord-jacket", "green cotton tea dress", "",
     "white leather sneakers", "brown corduroy jacket", "woven straw bag", "loose",
     (S, U), ("outdoor", "weekend"), "casual"),
    ("black-shirt-camel-skirt-loafer", "black cotton shirt", "camel corduroy a-line skirt",
     "brown leather loafers", "", "leather-strap watch", "low_bun",
     (A, W), ("gathering", "crafting"), "smart"),
    ("green-cord-shirt-black-legging", "green corduroy shirt", "black leggings",
     "brown suede knee-high boots", "", "tortoiseshell barrette", "half_up",
     (A, W), ("weekend", "crafting"), "casual"),
    ("pink-shirt-charcoal-trouser", "pink cotton shirt", "charcoal wide-leg trousers",
     "black canvas sneakers", "", "leather crossbody bag", "loose",
     (S,), ("weekend", "market"), "casual"),
    ("olive-jacket-navy-skirt", "white cotton shirt", "navy denim midi skirt",
     "brown leather loafers", "olive waxed-cotton jacket", "thin gold chain necklace", "low_bun",
     (A, S), ("outdoor", "market"), "casual"),
    ("mustard-blouse-navy-jeans", "mustard cotton blouse", "navy wide-leg jeans",
     "white canvas sneakers", "", "small gold hoop earrings", "loose",
     (A, S), ("weekend", "market"), "casual"),
    ("lilac-blouse-grey-skirt", "lilac cotton blouse", "grey wool midi skirt",
     "grey suede ankle boots", "", "silver hoop earrings", "low_pony",
     (A, W, S), ("gathering", "holiday"), "smart"),
    ("rose-tee-indigo-skirt", "rose jersey tee", "indigo denim a-line skirt",
     "tan leather sandals", "", "leather-strap watch", "half_up",
     (U, S), ("market", "outdoor"), "casual"),
    ("rust-shirt-black-legging-coat", "rust cotton shirt", "black leggings",
     "black leather chelsea boots", "camel wool coat", "none", "low_bun",
     (A, W), ("outdoor",), "casual"),
    ("stone-shirt-navy-culotte-vest", "stone cotton shirt", "navy culottes",
     "burgundy leather loafers", "quilted olive vest", "none", "tucked",
     (A, S), ("outdoor", "market"), "casual"),
    ("green-blouse-white-trouser", "green cotton blouse", "white tailored cropped trousers",
     "navy leather ballet flats", "", "pearl drop earrings", "low_bun",
     (S, U), ("gathering",), "smart"),
    ("heather-sweat-indigo-jean-coat", "heather fleece sweatshirt", "indigo straight-leg jeans",
     "white leather sneakers", "navy wool coat", "none", "loose",
     (W,), ("outdoor", "holiday"), "relaxed"),
    ("grey-tee-sage-chino-jacket", "grey cotton tee", "sage cotton chinos",
     "white canvas plimsolls", "navy quilted jacket", "leather-strap watch", "low_pony",
     (S, A), ("outdoor", "weekend"), "casual"),
    ("black-turtle-camel-legging", "black jersey roll-neck top", "camel ponte leggings",
     "black leather loafers", "grey wool blazer", "gold hoop earrings", "low_bun",
     (W, A), ("gathering", "holiday"), "smart"),
    ("red-tee-denim-jacket-black-jean", "red cotton tee", "black straight-leg jeans",
     "white canvas sneakers", "denim jacket", "none", "loose",
     (S, A), ("weekend", "outdoor"), "casual"),
    ("tan-blouse-charcoal-culotte", "tan cotton blouse", "charcoal wool culottes",
     "black leather knee-high boots", "", "gold pendant necklace", "low_pony",
     (A, W), ("gathering", "holiday"), "smart"),
    ("plum-shirt-navy-skirt-sneak", "plum cotton shirt", "navy denim a-line skirt",
     "white leather sneakers", "grey wool blazer", "none", "loose",
     (S, A), ("market", "weekend"), "casual"),
    ("blue-tee-black-cord-clog", "blue jersey tee", "black corduroy straight trousers",
     "tan leather clogs", "", "leather belt", "side_braid",
     (S, A), ("crafting", "at_home"), "casual"),
    ("white-blouse-burgundy-skirt-flat", "white cotton blouse", "burgundy pleated midi skirt",
     "black leather ballet flats", "", "leather belt", "tucked",
     (A, W, S), ("holiday", "gathering"), "smart"),
    ("forest-blouse-indigo-flare-loafer", "forest cotton blouse", "indigo flared jeans",
     "burgundy leather loafers", "", "silver hoop earrings", "half_up",
     (A, W), ("weekend", "holiday"), "casual"),
    ("tan-tee-black-culotte-sandal", "tan jersey tee", "black linen culottes",
     "black leather sandals", "", "leather crossbody bag", "loose",
     (U,), ("market", "outdoor"), "casual"),
    ("mustard-shirt-charcoal-cord-jacket", "mustard corduroy shirt", "charcoal straight-leg jeans",
     "black leather lace-up boots", "black cotton jacket", "none", "side_braid",
     (A, W), ("outdoor", "market"), "casual"),
    ("lilac-tee-navy-chino-loafer", "lilac jersey tee", "navy cotton chinos",
     "tan leather loafers", "denim jacket", "none", "loose",
     (S,), ("weekend", "market"), "casual"),
    ("grey-blouse-rust-legging-boot", "grey cotton blouse", "rust leggings",
     "brown suede ankle boots", "", "gold pendant necklace", "low_pony",
     (A, W), ("at_home", "holiday"), "casual"),
)
LIBRARY: tuple[Outfit, ...] = tuple(Outfit(*r) for r in _ROWS)
LIBRARY_SIZE = len(LIBRARY)
BY_ID: dict[str, Outfit] = {o.outfit_id: o for o in LIBRARY}

# ---- families ------------------------------------------------------------------------------
# How the product meets Laura. A family not named here is used near her (the default).
WORN, HELD, NEAR = "worn", "held", "near"
FAMILIES: tuple[str, ...] = ("basket", "coaster", "placemat", "ornament", "blanket", "baby",
                             "pillow", "amigurumi", "garment", "scarf", "hat", "shawl", "bag")
INTERACTION: dict[str, str] = {
    "garment": WORN, "scarf": WORN, "hat": WORN, "shawl": WORN,
    "blanket": HELD, "baby": HELD, "pillow": HELD, "amigurumi": HELD,
}


def interaction(family: str) -> str:
    return INTERACTION.get(str(family or "").lower(), NEAR)


def _cat(slot: str, text: str) -> str:
    from .wardrobe import parse_garment

    return parse_garment(slot, text)["category"]


def compatible(outfit: Outfit, family: str) -> dict:
    """Whether this outfit can be worn with this product family, and why not."""
    fam = str(family or "").lower()
    why: list[str] = []
    g = outfit.garments
    top = _cat("top_or_dress", g["top_or_dress"])
    outer = _cat("outerwear", g["outerwear"])
    acc = _cat("accessories", g["accessories"])
    if fam == "garment":
        # Laura wears the product as her top layer; the outfit is what is under and around it.
        if outer != "none":
            why.append("a worn garment is the top layer: the outfit has no outerwear")
        if top in ("cardigan", "jumper", "dress") or outfit.is_dress:
            why.append("a worn garment sits over a base layer, not over a dress or another "
                       "top layer")
    elif fam == "shawl":
        if outer != "none":
            why.append("a worn shawl is the outer layer: the outfit has no outerwear")
    elif fam == "scarf":
        if outer == "shawl" or acc == "necklace":
            why.append("a worn scarf covers the neckline: no necklace, no shawl")
    elif fam == "hat":
        if acc == "hair" or outfit.hair in ("low_bun", "half_up"):
            why.append("a worn hat needs her hair down or low, with no barrette")
    if interaction(fam) == HELD:
        if outer in ("coat", "jacket", "blazer"):
            why.append("a held product is photographed indoors: no coat, jacket or blazer")
    if fam in ("baby", "amigurumi"):
        if acc in ("necklace", "bag"):
            why.append("a baby or toy product is held close: no necklace or bag")
    return {"ok": not why, "family": fam, "interaction": interaction(fam), "why": why}


# ---- colour harmony -----------------------------------------------------------------------
MIN_DELTA_E = 20.0     # CIE76; below this a large garment merges with the yarn at its edges
CHROMA_MARGIN = 12.0   # an outfit colour may be at most this much more chromatic than the yarn
CHROMA_FLOOR = 34.0    # ...but a very quiet product still allows muted colour around it
HARMONY_RULE = "outfit_library.harmony/1"


def _lab(hexval: str) -> tuple[float, float, float]:
    h = str(hexval).lstrip("#")
    rgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    x = (0.4124 * lin[0] + 0.3576 * lin[1] + 0.1805 * lin[2]) / 0.95047
    y = (0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2])
    z = (0.0193 * lin[0] + 0.1192 * lin[1] + 0.9505 * lin[2]) / 1.08883

    def f(t: float) -> float:
        return t ** (1 / 3) if t > 216 / 24389 else (24389 / 27 * t + 16) / 116

    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def delta_e(a: str, b: str) -> float:
    la, lb = _lab(a), _lab(b)
    return round(math.dist(la, lb), 2)


def chroma(hexval: str) -> float:
    _l, a, b = _lab(hexval)
    return round(math.hypot(a, b), 2)


_HEX = re.compile(r"^#?[0-9a-fA-F]{6}$")


def product_hexes(product_colours) -> list[tuple[str, str]]:
    """[(name, #hex)] from a CIR `colors` mapping or a list of names/hexes. A name with no
    hex and no palette match is dropped and reported by `harmony` as unmeasured."""
    out = []
    items = product_colours.items() if isinstance(product_colours, dict) else \
        [(c, c) for c in product_colours or ()]
    for name, val in items:
        v = str(val or "")
        if _HEX.match(v):
            out.append((str(name), "#" + v.lstrip("#").upper()))
        elif colour_of(f" {name} "):
            out.append((str(name), COLOURS[colour_of(f' {name} ')]))
    return out


def harmony(outfit: Outfit, product_colours) -> dict:
    """PASS when the outfit keeps the product the hero; FAIL with each reason; UNKNOWN when the
    product's colours cannot be measured (unknown is never PASS)."""
    yarns = product_hexes(product_colours)
    if not yarns:
        return {"status": "UNKNOWN", "rule": HARMONY_RULE,
                "why": "the product's yarn colours are not measurable", "problems": []}
    yarn_max = max(chroma(h) for _n, h in yarns)
    cap = max(yarn_max + CHROMA_MARGIN, CHROMA_FLOOR)
    problems = []
    for p in outfit.palette():
        if p["slot"] not in _LARGE_SLOTS:
            continue
        c = chroma(p["hex"])
        if c > cap:
            problems.append({"code": "COMPETITION", "slot": p["slot"], "colour": p["colour"],
                             "chroma": c, "cap": round(cap, 2)})
        if p["slot"] in _LARGE_SLOTS:
            for name, h in yarns:
                d = delta_e(p["hex"], h)
                if d < MIN_DELTA_E:
                    problems.append({"code": "CAMOUFLAGE", "slot": p["slot"],
                                     "colour": p["colour"], "yarn": name, "delta_e": d,
                                     "minimum": MIN_DELTA_E})
    return {"status": "FAIL" if problems else "PASS", "rule": HARMONY_RULE,
            "yarns": [{"name": n, "hex": h, "chroma": chroma(h)} for n, h in yarns],
            "chroma_cap": round(cap, 2), "problems": problems,
            "why": ("the outfit keeps the product the hero" if not problems else
                    "; ".join(f"{p['code']} {p['slot']} {p['colour']}" for p in problems))}


# ---- library rules -------------------------------------------------------------------------

def outfit_problems(o: Outfit) -> list[str]:
    """Every library rule this outfit breaks (empty means it is a valid library outfit)."""
    from .laura_home import KNITTED_OR_CROCHETED
    from .outfits import _IDENTITY_WORDS, _ID

    out = []
    if not _ID.match(o.outfit_id):
        out.append(f"id {o.outfit_id!r} is not a registry id")
    g = o.garments
    if not g["top_or_dress"].strip() or not g["shoes"].strip():
        out.append("incomplete: names a top or dress and footwear")
    if not g["lower"].strip() and not o.is_dress:
        out.append("incomplete: names a lower garment unless it is a dress")
    text = " ".join(g.values())
    for rx, code in ((BRAND_OR_LOGO, "BRANDED"), (REVEALING, "REVEALING")):
        m = rx.search(text)
        if m:
            out.append(f"{code}: {m.group(0)!r}")
    m = re.search(rf"\b(?:{KNITTED_OR_CROCHETED})", text, re.I)
    if m:
        out.append(f"KNITWEAR: {m.group(0)!r} would read as a second crochet or knitted piece")
    m = _IDENTITY_WORDS.search(text)
    if m:
        out.append(f"IDENTITY: {m.group(0)!r} is part of Laura's locked identity")
    if o.hair not in HAIR_STYLINGS:
        out.append(f"hair arrangement {o.hair!r} is not in the closed list")
    elif _HAIR_CHANGE.search(HAIR_STYLINGS[o.hair]):
        out.append("the hair arrangement changes her hair")
    for slot in _LARGE_SLOTS + ("shoes",):
        if g[slot] and g[slot] != "none" and not colour_of(g[slot]):
            out.append(f"{slot} {g[slot]!r} names no palette colour")
    if not o.seasons or set(o.seasons) - set(SEASONS):
        out.append(f"seasons {o.seasons} are not in {SEASONS}")
    if not o.occasions or set(o.occasions) - set(OCCASIONS):
        out.append(f"occasions {o.occasions} are not in {OCCASIONS}")
    if o.formality not in FORMALITY:
        out.append(f"formality {o.formality!r} is not in {FORMALITY}")
    return out


def library_problems(library: tuple[Outfit, ...] = LIBRARY) -> list[str]:
    """Every rule the library as a whole breaks: per-outfit rules, unique ids and signatures,
    pairwise distinctness and distinctness from the canonical references' clothing."""
    from .outfits import signature
    from .wardrobe import MAX_SIMILARITY, REFERENCE_OUTFIT, similarity

    out = [f"{o.outfit_id}: {p}" for o in library for p in outfit_problems(o)]
    ids = [o.outfit_id for o in library]
    out += [f"duplicate id {i}" for i in sorted({i for i in ids if ids.count(i) > 1})]
    sigs: dict[str, str] = {}
    for o in library:
        s = signature(o.garments)
        if s in sigs:
            out.append(f"{o.outfit_id} is the same complete outfit as {sigs[s]}")
        sigs[s] = o.outfit_id
        if similarity(o.garments, REFERENCE_OUTFIT)["score"] >= MAX_SIMILARITY:
            out.append(f"{o.outfit_id} is too close to the canonical references' clothing")
    for i, a in enumerate(library):
        for b in library[i + 1:]:
            sc = similarity(a.garments, b.garments)["score"]
            if sc >= MAX_SIMILARITY:
                out.append(f"{a.outfit_id} ~ {b.outfit_id}: similarity {sc} >= "
                           f"{MAX_SIMILARITY}")
    return out


# ---- choosing and claiming --------------------------------------------------------------

def _order(listing: str) -> list[Outfit]:
    return sorted(LIBRARY, key=lambda o: hashlib.sha256(
        f"{LIBRARY_VERSION}|{listing}|{o.outfit_id}".encode()).hexdigest())


def candidates(listing: str, *, family: str, product_colours, season: str = "",
               exclude=()) -> list[dict]:
    """Every library outfit in this listing's stable order, with whether it may be used and
    why not. Pure: the registry is consulted only by `claim_for_listing`."""
    out = []
    ex = set(exclude)
    for o in _order(listing):
        why = []
        if o.outfit_id in ex:
            why.append("held by another listing")
        c = compatible(o, family)
        why += c["why"]
        h = harmony(o, product_colours)
        if h["status"] != "PASS":
            why.append(f"harmony {h['status']}: {h['why']}")
        if season and season not in o.seasons:
            why.append(f"not a {season} outfit")
        out.append({"outfit_id": o.outfit_id, "ok": not why, "why": why})
    return out


def choose(listing: str, *, family: str, product_colours, season: str = "",
           exclude=()) -> Outfit | None:
    """The first usable library outfit for this listing, or None. Deterministic."""
    for c in candidates(listing, family=family, product_colours=product_colours,
                        season=season, exclude=exclude):
        if c["ok"]:
            return BY_ID[c["outfit_id"]]
    return None


class OutfitLibraryRefused(ValueError):
    pass


def _held_elsewhere(db, listing: str) -> set[str]:
    from . import outfits

    return {o["outfit_id"] for o in outfits.registry(db)
            if o.get("listing") and o["listing"] != listing}


def claim_for_listing(db, listing: str, *, family: str, product_colours, season: str = "",
                      max_tries: int = 8) -> dict:
    """ONE outfit for this listing, durable (the `laura_outfits` reservation) and idempotent.

    * The listing already holds an approved outfit: that outfit, unchanged.
    * Otherwise the first usable library outfit (`choose`) not held by another listing is
      registered, approved as a library outfit and reserved through `outfits.reserve`. A
      FAIL there (another listing reserved it first, or a legacy outfit it is too close to)
      moves to the next candidate; nothing is ever shared.
    * None usable: UNKNOWN, never a reused or clashing outfit."""
    from . import outfits

    listing = str(listing or "").strip()
    if not listing:
        return {"status": "UNKNOWN", "why": "no listing to claim an outfit for"}
    held = outfits.reserved_for(db, listing)
    if held is not None:
        lib = BY_ID.get(held["outfit_id"])
        return {"status": "PASS", "claimed": False, "outfit_id": held["outfit_id"],
                "outfit": lib.view() if lib else held,
                "why": f"listing {listing!r} already holds {held['outfit_id']}"}
    exclude = set(_held_elsewhere(db, listing))
    tried = []
    for _ in range(max_tries):
        o = choose(listing, family=family, product_colours=product_colours, season=season,
                   exclude=exclude)
        if o is None:
            break
        outfits.register(db, outfit_id=o.outfit_id, garments=o.garments,
                         description=o.text_spec(), colours=[p["colour"] for p in o.palette()],
                         concept={"library": LIBRARY_VERSION, "hair_styling": o.hair,
                                  "seasons": list(o.seasons), "occasions": list(o.occasions),
                                  "family": family})
        row = outfits.get(db, o.outfit_id) or {}
        if row.get("approval_state") == "proposed":
            outfits.approve(db, o.outfit_id, approved_by=APPROVED_BY)
        got = outfits.reserve(db, o.outfit_id, listing)
        if got["status"] == "PASS":
            return {"status": "PASS", "claimed": True, "outfit_id": o.outfit_id,
                    "outfit": o.view(), "why": got["why"], "skipped": tried}
        tried.append({"outfit_id": o.outfit_id, "why": got["why"]})
        exclude.add(o.outfit_id)
    return {"status": "UNKNOWN", "claimed": False, "skipped": tried,
            "why": (f"no usable library outfit is free for {listing!r} ({family}); add "
                    f"outfits to the library")}


# ---- outfit reference images (FLUX, only when activated) ------------------------------------
# The FLUX provider the image stages use (`creative.image_stages.MODEL`).
REFERENCE_PROVIDER = "flux-3-image"


def reference_request(db, outfit_id: str) -> dict:
    """What an outfit reference image would be, and whether it may be generated now.

    Never calls a provider. Without the owner's live generation activation for the FLUX
    provider the request is HELD and nothing is sent. With it, the request is READY for the
    existing producer (`image_production`), whose `paid_provider_gate.enforce` is the only
    point a paid call can leave from."""
    o = BY_ID.get(str(outfit_id or ""))
    if o is None:
        raise OutfitLibraryRefused(f"{outfit_id!r} is not a library outfit")
    spec = {"outfit_id": o.outfit_id, "kind": "outfit_reference",
            "brief": (f"Laura (canonical identity, unchanged) standing full length in soft "
                      f"daylight against a plain wall, wearing {o.text_spec()}; "
                      f"{HAIR_STYLINGS[o.hair]}, {HAIR_LOCK}. No product in frame."),
            "garments": o.garments}
    try:
        from ..gateway import paid_provider_gate as gate

        state = gate.activation_state(db, REFERENCE_PROVIDER, "generation")
        active = bool(state.get("active"))
        why = state.get("why") or state.get("reason") or ""
    except Exception as exc:  # noqa: BLE001 - no evidence of activation is not activation
        active, why = False, f"activation unreadable: {type(exc).__name__}"
    return {**spec, "status": "READY" if active else "HELD",
            "provider_called": False,
            "why": ("owner activation is live; hand to the image producer, whose gate "
                    "enforces spend" if active else
                    f"FLUX generation is not activated by the owner ({why or 'no active row'}); "
                    f"nothing was sent")}
