"""ENG-AMIGURUMI-BREADTH: shaped, low-sew animal amigurumi composed from the plush primitives.

The ball-body bear or bunny (`fallback_constructions.amigurumi`) is one closed ball with two
sewn ears. Demand (`products.demand`, the owner's teardowns L1/L2) is for low-sew animals with a
head, limbs, ears and tails. This engine builds them from four primitives, every one of which
the compiler, the twin and the reverse compiler already validate or now validate:

* the closed spiral piece (`Component.stuff_at_round` / `closes`, `cir.closed_forms`): here the
  head and body are ONE piece worked from the top of the head down -- the head increases, an
  optional neck decreases, the body increases again, then decreases to a gathered closure;
* the magic-ring disc / tube (`products.moment_candidates._disc` and plain rounds): every
  appendage is a tube or cup worked from a magic ring;
* the flattened edge: an appendage's last round folds into two layers of half its stitches;
* the low-sew join (`Op.joins`, `cir.low_sew`): when the body reaches the round an appendage
  belongs to, the body stitches at the stated positions are worked through both layers of the
  appendage's flattened edge. Nothing is sewn on. The joined stitch counts are checked by the
  compiler (`LOW_SEW_*`), measured on the twin (`cir.assembly` records each as a join) and
  read back by the reverse compiler ("... through both layers of the leg").

Every construction and count here is Brambleloop's own (house design choices stated below);
no competitor pattern, chart, wording or geometry is used. The teardowns name only the
technique class (join-as-you-go), which is not a protected design.

Child safety is never weakened: features are embroidered with yarn only (no safety eye,
button, bead or any hard part), every appendage is a crocheted-in piece the small-parts
cylinder measures exactly like a sewn one (`gates.small_parts._sewn_on`), and an appendage
that fits or may fit the cylinder at the drafted yarn is refused at draft. A stuffed closed
form is risk class C: certification withholds for the physical sample and the child-safety
physical evidence (HELD, never PASS).

What is refused by name (each needs its own engine-modelled construction): textures (fur,
fleece, spines, chenille), accessories the toy holds or wears, colourwork patches, spikes and
frills, gills and other appendages too small to clear the small-parts cylinder, more than one
toy, a size word, "no sew" (the face is embroidered and the closure is sewn shut, so it is
low-sew, never no-sew).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..cir.model import CIR, Component, Material, Op, Repeat

FAMILY = "amigurumi_animal"
REFUSED = "refused"
PRIMITIVES = ("creative.animals.build", "products.moment_candidates._disc",
              "products.moment_candidates._decrease_to", "cir.closed_forms.check",
              "cir.low_sew.check")

HEAD_STITCHES = 36
NECK_STITCHES = 30
BODY_STITCHES = 42
STUFF_AT_STITCHES = 18          # the opening the body is stuffed through (>= 12, closed_forms)
CLOSE_STITCHES = 6              # the gathered closure (<= geometry.CLOSEABLE_STITCHES)
LIMB_STITCHES = 18              # a tube's widest round: clear of the small-parts cylinder at
EAR_STITCHES = 20               # worsted and heavier (gates.small_parts; checked at draft)
TAIL_STITCHES = 18
FLUKE_STITCHES = 24
OCTOPUS_LEG_STITCHES = 12       # chunky only: 12 sts at bulky gauge is about 40 mm across
FRONT_GAP = 6                   # sts between a front pair at the front centre
EAR_GAP = 6
# Yarn weights the engine drafts at. Finer yarn makes appendages that approach the small-parts
# cylinder; "chunky" in a title is drafted at bulky.
WEIGHTS = ("medium", "bulky", "super_bulky")     # publish.substitution keys (worsted = medium)
CHUNKY_WEIGHT = "bulky"


@dataclass(frozen=True)
class Part:
    name: str
    make: int
    widest: int
    wedges: int
    plain: int
    host: str               # "head" or "body": which plain section it is crocheted into
    at: int                 # the n-th plain round of that section (1-based)
    layout: str             # pair_front | pair_sides | single_front | single_back | ring
    colour: str = "main"    # main | contrast
    shape: str = "tube"     # tube | cup | point (how the rounds before the flattened edge go)
    note: str = ""


@dataclass(frozen=True)
class Animal:
    key: str
    head_plain: int
    neck: int | None
    body: int
    body_plain: int
    parts: tuple[Part, ...]
    contrast: str = ""      # "" | "lower" (the underside rounds in the contrast colour)
    chunky_only: bool = False
    head: int = HEAD_STITCHES


def _limbs(name: str, make: int, plain: int, front_at: int, back_at: int | None = None,
           colour: str = "main") -> tuple[Part, ...]:
    if make == 2:
        return (Part(name, 2, LIMB_STITCHES, 6, plain, "body", front_at, "pair_front",
                     colour),)
    # Four legs: one piece made 4 times, a front pair and a back pair on two body rounds.
    return (Part(name, 4, LIMB_STITCHES, 6, plain, "body", front_at, "pair_front", colour),
            Part(name, 4, LIMB_STITCHES, 6, plain, "body", back_at, "pair_front", colour))


def _ears(plain: int, colour: str = "main", at: int = 2, shape: str = "cup") -> Part:
    return Part("ear", 2, EAR_STITCHES, 5, plain, "head", at, "pair_front", colour, shape)


# House designs (stated design choices, not measurements). `at` counts plain rounds of the
# section, so every join lands on a plain sc round.
ANIMALS: dict[str, Animal] = {
    "frog": Animal("frog", 4, None, BODY_STITCHES, 9,
                   (Part("arm", 2, LIMB_STITCHES, 6, 4, "body", 2, "pair_front"),
                    Part("leg", 2, LIMB_STITCHES, 6, 6, "body", 8, "pair_front")),
                   contrast="lower"),
    "capybara": Animal("capybara", 5, NECK_STITCHES, BODY_STITCHES, 9,
                       (_ears(0, "contrast"),) + _limbs("leg", 4, 3, 2, 8)),
    "lamb": Animal("lamb", 4, NECK_STITCHES, BODY_STITCHES, 9,
                   (_ears(4, "contrast"),) + _limbs("leg", 4, 5, 2, 8, "contrast")),
    "duckling": Animal("duckling", 5, 24, BODY_STITCHES, 8,
                       (Part("bill", 1, LIMB_STITCHES, 6, 2, "head", 3, "single_front",
                             "contrast"),
                        Part("wing", 2, EAR_STITCHES, 5, 2, "body", 3, "pair_sides",
                             shape="cup"))),
    "whale": Animal("whale", 2, None, 48, 8,
                    (Part("fin", 2, LIMB_STITCHES, 6, 2, "body", 3, "pair_sides"),
                     Part("tail", 1, FLUKE_STITCHES, 6, 3, "body", 7, "single_back")),
                    contrast="lower"),
    "otter": Animal("otter", 4, NECK_STITCHES, BODY_STITCHES, 10,
                    (_ears(0),) + _limbs("leg", 4, 4, 2, 9)
                    + (Part("tail", 1, TAIL_STITCHES, 6, 8, "body", 10, "single_back"),),
                    contrast="lower"),
    "cow": Animal("cow", 4, NECK_STITCHES, BODY_STITCHES, 9,
                  (_ears(1),) + _limbs("leg", 4, 5, 2, 8, "contrast")
                  + (Part("tail", 1, TAIL_STITCHES, 6, 6, "body", 9, "single_back"),)),
    "dinosaur": Animal("dinosaur", 4, NECK_STITCHES, 48, 9,
                       _limbs("leg", 4, 4, 2, 8, "contrast")
                       + (Part("tail", 1, FLUKE_STITCHES, 6, 8, "body", 9, "single_back"),)),
    "octopus": Animal("octopus", 0, None, 72, 6,
                      (Part("leg", 8, OCTOPUS_LEG_STITCHES, 6, 8, "body", 6, "ring",
                            "contrast"),),
                      chunky_only=True, head=72),
}
_SYNONYMS = {"frog": "frog", "capybara": "capybara", "lamb": "lamb", "sheep": "lamb",
             "duckling": "duckling", "duck": "duckling", "whale": "whale", "otter": "otter",
             "cow": "cow", "dinosaur": "dinosaur", "dino": "dinosaur", "octopus": "octopus"}
# Animals whose defining feature no engine models yet: refused by name, never drafted plain.
_UNBUILT_ANIMALS = {
    "hedgehog": "a hedgehog's spines are a texture (loop or spike stitches with their own counts "
                "and yarn); no engine models one",
    "axolotl": "an axolotl's gills are six small appendages that do not clear the small-parts "
               "cylinder at any gauge this engine drafts; they need a small-parts assessment",
    "unicorn": "a horn is a stiffened cone this engine does not model",
}
# Words that name the toy or its yarn honestly on this engine.
_ALLOWED_WORDS = frozenset({"amigurumi", "crochet", "crocheted", "plush", "plushie", "toy",
                            "cosy", "cozy", "simple", "classic", "chunky", "low", "sew",
                            "sleepy"})
# House descriptors: place and mood words in our own titles. They name no shape, feature,
# texture or size, so they promise nothing the pattern does not make.
_DESCRIPTORS = frozenset({"puddle", "riverbank", "pond", "marsh", "meadow", "harbour",
                          "harbor", "hedgerow", "riverstone", "clover", "tidepool", "fernback",
                          "brook", "willow", "orchard", "moss", "fern", "meadowlark", "dune",
                          "tide", "garden", "woodland", "farmhouse", "sunny", "rainy"})
_TEXTURE = (r"\b(?:fluffy|fluff|fuzzy|furry|fur|faux[- ]fur|brushed|loop(?:y|ed|s)?|chenille|"
            r"velvet|shaggy|boucle|bouclé|fleece|fleecy|curly|spiky|spikes?|spines?|frill(?:s|ed|y)?|"
            r"textured|bobbles?|popcorn)\b")
_NO_SEW = r"\bno[- ]?sew\b|\bseamless\b"
_SIZE = r"\b(?:tiny|mini|little|small|medium|large|big|giant|huge|jumbo|xl|xxl|\d+)\b"
# Premise words naming something this engine does not make (an accessory the toy holds or
# wears, patches, a texture). Read by `construction_families.route` for this family.
_PREMISE_UNBUILT = (r"\b(?:holding|holds|hold|carr(?:y|ies|ying)|stones?|pebbles?|scarf|hat|"
                    r"bows?|ribbons?|flowers?|accessor(?:y|ies)|patch(?:es)?|spots?|spikes?|"
                    r"spines?|frill(?:s|ed|y)?|gills?|horns?|clothes|clothing|outfit|"
                    r"textured|fur|fleece|chenille|safety eyes?|buttons?|beads?)\b")


def names_an_animal(title: str | None) -> bool:
    """True when the title names an animal this engine builds or refuses by name."""
    from .fallback_constructions import fold_title

    words = set(re.findall(r"[a-z0-9]+", fold_title(title)))
    return bool(words & (set(_SYNONYMS) | set(_UNBUILT_ANIMALS)))


def premise_refusal(premise: str | None) -> str | None:
    """The first word in a premise naming what this engine does not build, else None."""
    from .fallback_constructions import fold_title

    hit = re.search(_PREMISE_UNBUILT, fold_title(premise))
    hit = hit or re.search(_TEXTURE, fold_title(premise))
    return hit.group(0) if hit else None


def route(title: str | None) -> dict:
    """{"family": FAMILY, "kind", "weight", "sleepy"} for a plain shaped animal, else REFUSED
    with what it needs."""
    from .fallback_constructions import fold_title

    folded = fold_title(title)
    if re.search(_NO_SEW, folded):
        return {"family": REFUSED, "needs": "a no-sew construction (the face is embroidered and "
                                            "the closure sewn shut, so this is low-sew)",
                "why": "the title says no-sew; the animal is low-sew, not no-sew"}
    tex = re.search(_TEXTURE, folded)
    if tex:
        return {"family": REFUSED, "needs": "an engine-modelled texture with its own counts and "
                                            "yarn quantity",
                "why": f"the title names {tex.group(0)!r}, a texture this engine does not model"}
    size = re.search(_SIZE, folded)
    if size:
        return {"family": REFUSED, "needs": "one stated design size per animal",
                "why": f"the title names the size {size.group(0)!r}; the animal has one size"}
    leftover = re.sub(r"[a-z0-9'\s\-]", "", folded)
    if leftover:
        return {"family": REFUSED, "needs": "a plain animal title, in words",
                "why": f"the title names {leftover!r}, which the animal engine does not make"}
    words = re.findall(r"[a-z0-9]+", folded)
    for w in words:
        if w in _UNBUILT_ANIMALS:
            return {"family": REFUSED, "needs": _UNBUILT_ANIMALS[w],
                    "why": f"the {w}'s defining feature is not modelled: {_UNBUILT_ANIMALS[w]}"}
    if len(set(words)) < len(words) or re.search(
            r"\b(?:\w+s and|set|pair|trio|duo|family|friends|animals|frogs|whales|lambs|cows|"
            r"otters|ducks|ducklings|dinosaurs|octopuses|octopi|capybaras)\b", folded):
        return {"family": REFUSED, "needs": "one certified release per toy, each listed alone",
                "why": "the title promises more than one toy; one draft is one toy"}
    if "low" in words or "sew" in words:
        if not re.search(r"\blow[- ]sew\b", folded):
            return {"family": REFUSED, "needs": "a plain animal title",
                    "why": "the title uses 'low' or 'sew' other than as 'low-sew'"}
    animals = [w for w in words if w in _SYNONYMS]
    if len({_SYNONYMS[a] for a in animals}) != 1:
        return {"family": REFUSED,
                "needs": f"one animal the engine builds ({', '.join(sorted(ANIMALS))})",
                "why": (f"the title {title!r} names "
                        + ("no animal this engine builds" if not animals
                           else f"more than one animal: {animals}"))}
    unknown = [w for w in words
               if w not in _SYNONYMS and w not in _ALLOWED_WORDS and w not in _DESCRIPTORS]
    if unknown:
        return {"family": REFUSED,
                "needs": (f"the shape, feature or size {' '.join(unknown)!r} names (its own "
                          f"pieces and a physical sample)"),
                "why": f"the title names {' '.join(unknown)!r}, which the animal engine does "
                       f"not make"}
    kind = _SYNONYMS[animals[0]]
    chunky = "chunky" in words
    if ANIMALS[kind].chunky_only and not chunky:
        return {"family": REFUSED, "needs": f"a chunky {kind} (drafted at {CHUNKY_WEIGHT})",
                "why": f"the {kind}'s appendages clear the small-parts cylinder only in chunky "
                       f"yarn; a title that does not say chunky would be drafted finer"}
    return {"family": FAMILY, "needs": "", "kind": kind, "chunky": chunky,
            "sleepy": "sleepy" in words,
            "why": (f"a low-sew {kind}: head and body in one closed piece, every appendage "
                    f"crocheted into its round")}


# ---- the drafting --------------------------------------------------------------------------


def _increase(rows, start: int, target: int, colour: str, wedges: int = 6) -> None:
    """Increase rounds from an existing `start` up to `target`, one inc per wedge per round,
    staggered on alternate rounds so the increases do not stack into corners."""
    count, k = start, 0
    while count < target:
        k += 1
        per = count // wedges
        if k % 2 == 0 and per > 1:
            before = (per - 1) // 2
            body = ([Op("sc", before)] if before else []) + [Op("inc")] + (
                [Op("sc", per - 1 - before)] if per - 1 - before else [])
        else:
            body = ([Op("sc", per - 1)] if per > 1 else []) + [Op("inc")]
        count += wedges
        rows.add([Repeat(body, times=wedges)], count, colour)


def _part_rows(part: Part, colour: str):
    from ..products.moment_candidates import _disc, _Rows

    rows = _Rows()
    if part.shape == "point":
        # A pointed ear: an increase round every other round, so it tapers to a tip.
        rows.add([Op("sc", part.wedges)], part.wedges, colour)
        count = part.wedges
        while count < part.widest:
            rows.add([Op("sc", count)], count, colour)
            per = count // part.wedges
            rows.add([Repeat(([Op("sc", per - 1)] if per > 1 else []) + [Op("inc")],
                             times=part.wedges)], count + part.wedges, colour)
            count += part.wedges
    else:
        _disc(rows, part.widest, colour, wedges=part.wedges)
    for _ in range(part.plain):
        rows.add([Op("sc", part.widest)], part.widest, colour)
    return rows.rows


def _placement(part: Part, count: int) -> list:
    """The host round's ops: plain sc with the part's flattened edge(s) crocheted in."""
    edge = part.widest // 2
    j = Op("sc", edge, joins=part.name)
    if part.layout == "ring":
        n = part.make
        if count % n or count // n <= edge:
            raise ValueError(f"{n} {part.name}s of {edge} sts do not fit evenly round {count}")
        return [Repeat([Op("sc", edge, joins=part.name), Op("sc", count // n - edge)], times=n)]
    if part.layout == "single_back":
        # The round starts at the centre back, so the part begins at the centre back.
        return [j, Op("sc", count - edge)]
    if part.layout == "single_front":
        before = (count - edge) // 2
        return [Op("sc", before), j, Op("sc", count - before - edge)]
    gap = FRONT_GAP if part.host == "body" else EAR_GAP
    if part.layout == "pair_sides":
        gap = count // 2 - edge
    before = count // 2 - gap // 2 - edge
    after = count - before - 2 * edge - gap
    if before < 1 or after < 1 or gap < 1:
        raise ValueError(f"two {edge}-st {part.name}s do not fit round {count}")
    return [Op("sc", before), j, Op("sc", gap), Op("sc", edge, joins=part.name),
            Op("sc", after)]


def _features_note(kind: str, sleepy: bool, head_rounds: tuple[int, int]) -> str:
    a, b = head_rounds
    eyes = ("two closed, sleepy eyes, each a curved line of 3 backstitches"
            if sleepy else "two eyes of 4 or 5 straight stitches over 1 st each")
    return (f"Embroider the face with yarn only: {eyes}, and a nose or mouth of 5 satin "
            f"stitches, worked through the front of the head between Rnds {a} and {b}, with "
            f"every knot pulled through to the inside")


def build(concept, *, version: str = "1.0.0", provenance=None) -> CIR:
    """A low-sew shaped animal: one closed head-and-body piece, appendages crocheted in."""
    from ..creative.prototype import gauge_for
    from ..gates import small_parts
    from ..products.moment_candidates import _decrease_to, _disc, _Rows
    from ..publish.substitution import normalise

    r = route(concept.title)
    if r["family"] != FAMILY:
        raise ValueError(f"{concept.slug}: {r['why']}")
    kind, spec = r["kind"], ANIMALS[r["kind"]]
    palette = list(dict.fromkeys(concept.colors or {}))
    if not palette:
        raise ValueError(f"{concept.slug}: a toy needs at least one colour")
    if len(palette) > 2:
        raise ValueError(f"{concept.slug}: the animal works at most two colours; the concept "
                         f"names {len(palette)}")
    main = palette[0]
    contrast = palette[1] if len(palette) > 1 else main
    uses_contrast = spec.contrast == "lower" or any(p.colour == "contrast" for p in spec.parts)
    if len(palette) > 1 and not uses_contrast:
        raise ValueError(f"{concept.slug}: the {kind} is worked in one colour; a second colour "
                         f"would be shown and never worked")
    weight = CHUNKY_WEIGHT if r["chunky"] else str(concept.yarn_weight or "")
    if (normalise(weight) or "") not in WEIGHTS:
        raise ValueError(f"{concept.slug}: the animal is drafted at {'/'.join(WEIGHTS)}; at "
                         f"{concept.yarn_weight!r} its appendages approach the small-parts "
                         f"cylinder")
    gauge = gauge_for(weight)

    body = _Rows()
    _disc(body, spec.head, main)
    head_plain = []
    for _ in range(spec.head_plain):
        head_plain.append(body.add([Op("sc", spec.head)], spec.head, main))
    if spec.neck is not None:
        _decrease_to(body, spec.head, spec.neck, main)
        neck_round = body.last
        _increase(body, spec.neck, spec.body, main)
    else:
        neck_round = None
        if spec.body > spec.head:
            _increase(body, spec.head, spec.body, main)
    body_plain = []
    lower_from = spec.body_plain // 2 + 1
    for i in range(spec.body_plain):
        colour = contrast if spec.contrast == "lower" and i + 1 >= lower_from else main
        body_plain.append(body.add([Op("sc", spec.body)], spec.body, colour))
    close_colour = contrast if spec.contrast == "lower" else main
    _decrease_to(body, spec.body, CLOSE_STITCHES, close_colour)
    widest = max(r.declared_count for r in body.rows)
    stuff_at = next(r.index for r in body.rows if r.index > body_plain[-1].index
                    and r.declared_count == STUFF_AT_STITCHES)
    body.rows[0].note = "work tightly, so the stuffing will not show between stitches"
    if neck_round is not None:
        body.rows[neck_round].note = ("stuff the head firmly through the neck now, then keep "
                                      "stuffing as the body grows")

    components: list[Component] = []
    joined_at: dict[int, list[str]] = {}
    seen: set[str] = set()
    for part in spec.parts:
        section = head_plain if part.host == "head" else body_plain
        if not 1 <= part.at <= len(section):
            raise ValueError(f"{kind}: the {part.name} is placed on plain {part.host} round "
                             f"{part.at}, which the {part.host} does not have")
        host_row = section[part.at - 1]
        ops = _placement(part, host_row.declared_count)
        if host_row.ops != [Op("sc", host_row.declared_count)]:
            raise ValueError(f"{kind}: two parts are placed on round {host_row.index}")
        host_row.ops = ops
        joined_at.setdefault(host_row.index, []).append(part.name)
        if part.name in seen:
            continue
        seen.add(part.name)
        colour = contrast if part.colour == "contrast" else main
        rows = _part_rows(part, colour)
        edge = part.widest // 2
        rounds = sorted(i for i, names in joined_at.items() if part.name in names)
        rows[-1].note = (f"fasten off and weave in the tail; flatten the last round so its "
                         f"{part.widest} sts lie in two layers of {edge}")
        components.append(Component(
            name=part.name, construction="spiral_rounds", rows=rows, foundation=0,
            foundation_kind="magic_ring", make=part.make,
            note=(f"Make {part.make}. Unstuffed. Not sewn on: its flattened edge is crocheted "
                  f"into the body in the round that names it.")))
    # Every part's placement is final; fix the notes on the joining rounds.
    for idx, names in joined_at.items():
        row = next(r for r in body.rows if r.index == idx)
        listed = " and ".join(f"{n}s" for n in dict.fromkeys(names))
        row.note = (f"the {listed} are crocheted in on this round: hold each flattened edge "
                    f"against the body with its opening up and work each joining stitch through "
                    f"both loops of the body stitch and both layers of the edge")
    head_span = (head_plain[0].index if head_plain else 1,
                 head_plain[-1].index if head_plain else spec.head // 6)
    face = _features_note(kind, r["sleepy"], head_span)
    first = " and ".join(f"{c.name}s" if c.make > 1 else f"the {c.name}" for c in components)
    # The body is the first piece (the document's hero and size); its pieces are made first.
    components.insert(0, Component(
        name="body", construction="spiral_rounds", rows=body.rows, foundation=0,
        foundation_kind="magic_ring", stuff_at_round=stuff_at, closes=True,
        note=(f"Before you begin, make the {first} below: each is crocheted into the body "
              f"in the round that names it, so nothing is sewn on. Head and body in one closed "
              f"piece, worked from the top of the head down. Mark the first stitch of every "
              f"round: the round begins at the centre back. " + face + ".")))

    around = widest / gauge.stitches_per_10cm * 10.0
    parts_text = ", ".join(f"{p.make} {p.name}{'s' if p.make > 1 else ''}"
                           for p in {p.name: p for p in spec.parts}.values())
    materials = [Material(name=f"{weight} acrylic", yarn_weight=weight, color_id=c)
                 for c in dict.fromkeys((main, contrast))]
    materials += [Material(name="new polyester fibrefill (toy stuffing)"),
                  Material(name=f"dark {weight} acrylic scrap for the embroidered face",
                           yarn_weight=weight)]
    cir = CIR(
        slug=concept.slug, title=concept.title, version=version,
        construction="spiral_rounds", risk_class="C", colors=dict(concept.colors),
        gauge=gauge, materials=materials, components=components, assembly=[],
        designer_notes=(f"{concept.category} concept drafted as a low-sew {kind}: head and body "
                        f"in one closed {widest}-st piece, stuffed after round {stuff_at} and "
                        f"closed at {CLOSE_STITCHES} sts; {parts_text} crocheted into their "
                        f"rounds through both layers of a flattened edge, nothing sewn on. "
                        f"Features embroidered with yarn only."),
        finished_size_note=(
            f"The body is about {around:.0f} cm around its widest round at the stated gauge. "
            f"Computed from the stitch counts, not yet measured on a worked sample; its height "
            f"depends on the stuffing and is measured on the sample."),
        provenance=provenance,
    )
    small = small_parts.blocking(cir)
    if small:
        raise ValueError(f"{concept.slug}: at {weight} gauge {'; '.join(small)} against the "
                         f"{small_parts.CYLINDER_MM:g} mm small-parts cylinder; this engine "
                         f"drafts a toy only where every crocheted-in piece is clear")
    return cir


def build_all_kinds(colours=None):   # pragma: no cover - a convenience for the report
    from types import SimpleNamespace

    out = {}
    for kind in ANIMALS:
        title = f"{'Chunky ' if ANIMALS[kind].chunky_only else ''}Low-Sew {kind.title()} Amigurumi"
        out[kind] = build(SimpleNamespace(slug=f"x-{kind}", title=title, category="amigurumi",
                                          colors=colours or {"MC": "#888888", "CC": "#DDDDDD"},
                                          yarn_weight="worsted"))
    return out

