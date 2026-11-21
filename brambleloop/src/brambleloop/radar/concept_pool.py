"""ENG-CONCEPTS-100: an evidence-backed pool of ORIGINAL concepts, generated at scale and
replenished continuously (P0 item 4).

The gap this closes. The research loop (watchlist scans -> coverage gaps -> research tasks ->
`proposal_writer` -> `radar.concept_intake` -> `radar.score` -> supply) wrote ONE concept per
validated gap, from a three-row table (`proposal_writer.POD_CONCEPTS`). With the 34-concept
section-33 POOL that is the whole idea supply, and most of it cannot be engineered. This
module turns every validated demand signal into several original concepts, in every
construction family, and keeps them visible whether or not the factory can build them yet.

    watchlist scan rows (BenchmarkListing: pod, price, favourites, season, last seen)
    + review themes (BenchmarkObservation) + the seasonal calendar
        -> demand signals per (shop, pod, demand facet), validated (fresh, >= 2 listings)
        -> LANES: a construction family x category x form, each with its own variants
           (motif x use context, written in OUR words from the closed vocabulary)
        -> every concept: premise + #88 storyboard, #108 qualifiers DERIVED by
           `creative.intake.qualifiers_for` (never typed), its construction family by
           `creative.construction_families.route`, its target size range, its evidence refs
        -> originality: never a competitor's title (whole-title and token overlap), never
           indistinguishable from an observed listing, never a near-clone of a POOL concept,
           a catalogue design or another pool concept (`creative.concept.distance`, the same
           MIN_NOVELTY floor the tournament and intake use)
        -> state: READY (admitted family, #108 passes), HELD (with the exact reason), or
           REFUSED (clone / copy)
        -> admission: READY concepts are attached, budget-bounded, as proposals to the
           answered research task behind their arena, and `radar.intake` judges them exactly
           as it judges every other proposal. Nothing here approves anything.

What this never does:

* copy a competitor. Competitor listing titles are read to CLASSIFY demand (facets) and to
  REFUSE copies; no title, description, tag, photo or instruction of a listing is stored on a
  concept or reaches a proposal. Concepts cite listing rows by id only. B-117 is untouched:
  this module never opens the quarantined benchmark library.
* fabricate a #108 qualifier. A premise word that would declare a qualifier the
  construction does not earn (`honesty_reasons`) refuses the concept: a plain striped panel
  is not a "motif composition" because a sentence says "motif".
* drop a concept it cannot build. Families that are not certified (amigurumi, garments,
  hats, mosaic, ...) are HELD with `construction_unsupported:<family>`, and generic forms
  with no earned qualifier are HELD by #108. Held concepts stay in the pool and in every
  count, with their reasons.
* spend. Generation is deterministic and CA$0 (no model call, no network). Admission hands a
  concept to work that can spend later (the vision verdict the pre-engineering gate waits
  for), so admission is bounded by the authorised monthly ceiling, open reservations and the
  pool's own monthly share (`admission_allowance`).
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import JSON, DateTime, Float, Integer, String, select
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base

JOB_TYPE = "radar.concept_pool"
GENERATED_ACTION = "concept_pool.generated"
ADMITTED_ACTION = "concept_pool.admitted"
CAPPED_ACTION = "concept_pool.admission_capped"

READY, HELD, REFUSED, ADMITTED, STALE = "ready", "held", "refused", "admitted", "stale"
STATES = (READY, HELD, REFUSED, ADMITTED, STALE)

TARGET_EVIDENCE_BACKED = 100
# A demand signal is validated when it rests on at least this many fresh observed listings.
MIN_SIGNAL_LISTINGS = 2
SIGNAL_FRESH_DAYS = 30
MAX_EVIDENCE_REFS = 8
# Admission is bounded per run (intake evaluates at most 10 per run of its own) ...
ADMIT_PER_RUN = 5
# ... and per month: the pool may commit at most this share of the authorised ceiling to the
# downstream judging its admissions will ask for.
POOL_SHARE_OF_CEILING = 0.10
# One admitted concept asks for one vision verdict (its board) before the pre-engineering
# gate decides; padding for the re-judge a changed board needs.
DOWNSTREAM_CALLS_PER_CONCEPT = 2

# D-OWNER-CORE-FAMILIES: research weighting.
PRIORITY_SHOP = "madeline_mae_co"
PRIORITY_SHOP_WEIGHT = 1.5
CORE_FACETS = ("baby", "stuffed_animal", "pillow")          # the owner's "huge hits"
WEIGHTED_FACETS = ("garment", "basket", "colourwork")
FACET_WEIGHT = {**{f: 1.5 for f in CORE_FACETS}, **{f: 1.25 for f in WEIGHTED_FACETS}}

# Demand facets, read off listing titles to CLASSIFY demand (never stored, never copied).
FACET_WORDS: dict[str, tuple[str, ...]] = {
    "baby": ("baby", "newborn", "nursery", "infant", "toddler", "stroller", "christening"),
    "stuffed_animal": ("amigurumi", "stuffed", "plush", "plushie", "softie", "stuffie",
                       "toy", "teddy"),
    "pillow": ("pillow", "cushion", "sham", "bolster"),
    "garment": ("cardigan", "sweater", "jumper", "top", "tee", "vest", "pullover",
                "dress", "shawl", "wrap", "poncho", "beanie", "hat"),
    "basket": ("basket", "bin", "storage"),
    "colourwork": ("tapestry", "mosaic", "colorwork", "colourwork", "c2c", "graphghan",
                   "intarsia", "fair isle", "jacquard", "pixel"),
}
_WORD = re.compile(r"[a-z0-9]+")


def facets_of(title: str) -> set[str]:
    words = " ".join(_WORD.findall(str(title or "").lower()))
    padded = f" {words} "
    return {f for f, needles in FACET_WORDS.items()
            if any(f" {n} " in padded or f" {n}s " in padded for n in needles)}


# ---- the generation grammar -------------------------------------------------------------
#
# A LANE is one thing the company could make: a category, a declared form and construction
# (closed vocabulary), the demand it answers (pod, facet), what the object is, how it is built
# (in words the engine honestly earns) and its variants. A VARIANT is a motif paired with a
# use context; within a lane both change together, because a recolour or a re-motif on the
# same use is the same idea (`creative.concept.distance`) and is refused as a clone.


@dataclass(frozen=True)
class Context:
    recipient: str
    occasion: str
    feeling: str


@dataclass(frozen=True)
class Motif:
    key: str
    title: str          # our own coined name, never a listing's words
    phrase: str         # what the buyer sees, in words the engine earns
    palette: str


@dataclass(frozen=True)
class Lane:
    key: str
    pod: str
    facet: str | None   # None: any listing in the pod supports it
    category: str
    form: str
    construction: str
    noun: str           # title noun
    what: str           # "a cushion cover"
    build: str          # how it is built, in words the engine earns
    motifs: tuple[Motif, ...]
    contexts: tuple[Context, ...]
    uses: tuple[str, ...]   # what each variant does for its owner (lane-specific)
    view: str = "laid flat from above"


HOME = (
    Context("self", "housewarming", "serene"),
    Context("host", "everyday", "cosy"),
    Context("newlyweds", "wedding", "romantic"),
    Context("friend_who_has_everything", "birthday", "quietly_luxurious"),
    Context("teen", "back_to_school", "bold"),
    Context("grandparent", "winter_nesting", "heirloom"),
)
NURSERY = (
    Context("new_parent", "new_baby", "tender"),
    Context("grandparent", "birthday", "heirloom"),
    Context("friend_who_has_everything", "everyday", "playful"),
    Context("self", "winter_nesting", "serene"),
)
TABLE = (
    Context("host", "housewarming", "bold"),
    Context("self", "everyday", "serene"),
    Context("grandparent", "mothers_day", "nostalgic"),
    Context("newlyweds", "wedding", "romantic"),
    Context("colleague", "birthday", "playful"),
)
CHARACTER = (
    Context("child", "birthday", "playful"),
    Context("teen", "back_to_school", "whimsical"),
    Context("self", "everyday", "tender"),
    Context("grandparent", "christmas", "nostalgic"),
    Context("friend_who_has_everything", "valentines", "celebratory"),
    Context("new_parent", "new_baby", "tender"),
    Context("student", "graduation", "celebratory"),
    Context("teacher", "summer_travel", "whimsical"),
    Context("colleague", "halloween", "playful"),
    Context("partner", "spring_refresh", "romantic"),
    Context("host", "housewarming", "whimsical"),
    Context("pet_owner", "thanksgiving", "playful"),
    Context("newlyweds", "wedding", "celebratory"),
)
WEAR = (
    Context("self", "winter_nesting", "cosy"),
    Context("partner", "valentines", "romantic"),
    Context("teen", "back_to_school", "bold"),
    Context("grandparent", "christmas", "heirloom"),
    Context("friend_who_has_everything", "birthday", "quietly_luxurious"),
    Context("student", "graduation", "bold"),
    Context("colleague", "everyday", "serene"),
)
STORAGE = (
    Context("self", "housewarming", "serene"),
    Context("host", "everyday", "cosy"),
    Context("new_parent", "new_baby", "tender"),
    Context("student", "back_to_school", "bold"),
    Context("pet_owner", "winter_nesting", "playful"),
)


def _m(key, title, phrase, palette):
    return Motif(key, title, phrase, palette)


STRIPES = (
    _m("tidewater", "Tidewater Band", "wide tonal bands", "three tones from the house palette"),
    _m("pinline", "Pinline Stripe", "fine contrast pinstripes",
       "a pale ground and one deep line"),
    _m("dusk", "Dusk Ombre", "graduated colour bands from light to deep",
       "a five-step gradient from the house palette"),
    _m("offset", "Offset Block", "offset blocks of stripe", "two contrasting house colours"),
    _m("horizon", "Lone Horizon", "a single deep band across a quiet ground",
       "a light ground and one deep accent"),
    _m("rainline", "Rainline Stripe", "irregular narrow and wide stripes",
       "cool greys and one warm accent"),
)
BABY_STRIPES = (
    _m("pastel", "Milk Pastel", "soft pastel bands", "three pale nursery tones"),
    _m("border", "Hem Line", "a narrow border of contrast rows", "cream with one soft accent"),
    _m("sage", "Sage Row", "alternating cream and sage rows", "cream and sage"),
    _m("deephem", "Deep Hem", "one deep hem band on a pale ground", "oat and dusty blue"),
)
CARDIGAN_MOTIFS = (
    _m("pocketless", "Long Line", "a long plain body with a deep ribless hem",
       "one heathered house colour"),
    _m("placket", "Contrast Placket", "a contrast front band", "a main colour and a contrast"),
    _m("marl", "Marl", "a marled body in two held strands", "two close house tones"),
    _m("yokestripe", "Shoulder Stripe", "stripes across the shoulders only",
       "a main colour and two stripes"),
    _m("sleeveband", "Sleeve Band", "single bands round each sleeve", "two house colours"),
)
BABY_GARMENT = (
    _m("tiny-plain", "First Week", "a plain body with a soft edging", "one pale nursery tone"),
    _m("tiny-band", "Cuff Band", "a contrast band at the cuffs", "cream and a soft accent"),
    _m("tiny-stripe", "Row Stripe", "fine tonal stripes", "two pale tones"),
    _m("tiny-block", "Two Tone", "a two-tone body and sleeves", "oat and sage"),
)
ANIMALS = (
    _m("hedgehog", "Bramble Hedgehog", "a round hedgehog with a pointed nose",
       "warm browns and cream"),
    _m("otter", "River Otter", "a long otter curled on its back", "chestnut and pale fawn"),
    _m("lamb", "Meadow Lamb", "a sitting lamb with folded legs", "cream and soft grey"),
    _m("whale", "Little Whale", "a plump whale with a curved fluke", "ocean blue and white"),
    _m("owl", "Barn Owl", "a heart-shaped barn owl perched upright", "honey and cream"),
    _m("bear", "Honey Bear", "a seated bear cub with round paws", "golden brown"),
)
SEA = (
    _m("octopus", "Tide Octopus", "an octopus with eight curling legs", "coral and cream"),
    _m("turtle", "Sea Turtle", "a domed sea turtle with wide flippers", "sea green and sand"),
    _m("seal", "Harbour Seal", "a dappled seal lying on its front", "dove grey and white"),
    _m("puffin", "Puffin", "an upright puffin with a striped beak", "black, white and orange"),
    _m("crab", "Shore Crab", "a wide crab with raised claws", "brick red and cream"),
)
GARDEN = (
    _m("bunny", "Garden Bunny", "a long-eared bunny sitting up", "oat and blush"),
    _m("frog", "Pond Frog", "a squat frog with wide feet", "leaf green and cream"),
    _m("snail", "Slow Snail", "a snail with a spiral shell", "moss and caramel"),
    _m("bee", "Bumble Bee", "a round bee with short wings", "gold and soft black"),
    _m("mouse", "Field Mouse", "a field mouse holding its tail", "fawn and pink"),
)
KITCHEN_STRIPES = (
    _m("ticking", "Ticking Stripe", "narrow ticking stripes", "blue on natural"),
    _m("market", "Market Row", "bold market-stall stripes", "tomato red and cream"),
    _m("sea-glass", "Sea Glass", "pale stripes in close tones", "three sea-glass greens"),
    _m("herb", "Herb Garden", "alternating herb-coloured rows", "sage, thyme and cream"),
    _m("hearth", "Hearth Band", "one warm band across a neutral cloth", "oat and rust"),
)
TAPESTRY_MOTIFS = (
    _m("diamond", "Diamond Tapestry", "a two-colour diamond band carried round the wall",
       "a natural ground and one deep contrast"),
    _m("check", "Checkerboard Tapestry",
       "a two-colour checkerboard band carried round the wall",
       "a natural ground and one deep contrast"),
    # Only two charts exist. This variant draws the diamond chart again under another name,
    # and the dedupe floor refuses it as a clone: one chart is one idea, whatever it is called.
    _m("geometric-diamond", "Geometric Diamond Tapestry",
       "a two-colour diamond band carried round the wall",
       "a natural ground and one deep contrast"),
)
GARMENT_MOTIFS = (
    _m("plain", "Quiet Morning", "a plain worked body with a neat edge",
       "one heathered house colour"),
    _m("banded", "Hem Band", "two contrast bands at hem and cuff",
       "a main colour and a contrast"),
    _m("tonal", "Tonal Line", "tonal body stripes", "two close house tones"),
    _m("colourblock", "Colour Field", "colour-blocked shoulders and body",
       "three house colours"),
    _m("speckle", "Speckled Oat", "a speckled yarn on a plain body",
       "one speckled house colour"),
)
COLOUR_CHARTS = (
    _m("terrace", "Terrace Step", "stepped geometric terraces",
       "two high-contrast house colours"),
    _m("lattice", "Lattice Window", "an interlocking geometric lattice",
       "a light and a deep colour"),
    _m("tile", "Kiln Tile", "repeating square tiles", "three house colours"),
    _m("wave", "Rolling Wave", "a rolling geometric wave", "a cool and a warm colour"),
    _m("star", "Compass Star", "an eight-point compass star repeat", "two winter tones"),
)
SMALL_GIFTS = (
    _m("snowflake", "Snowflake", "a six-armed snowflake", "white and ice blue"),
    _m("acorn", "Acorn", "a capped acorn", "oak brown and moss green"),
    _m("bell", "Sleigh Bell", "a round bell with a bow", "red and gold"),
    _m("heart", "Plump Heart", "a plump heart", "rose and blush"),
    _m("moon", "Crescent Moon", "a crescent moon", "pale gold and night blue"),
)


LANES: tuple[Lane, ...] = (
    # ---- admitted families (verified / physical_gate) ----
    Lane("cushion", "home_decor", "pillow", "pillow", "pillow", "flat_rows", "Cushion Cover",
         "a cushion cover", "worked flat in rows and seamed front to back", STRIPES, HOME,
         ("softens a reading chair in a new home", "dresses a guest bed before visitors",
          "marks a couple's first shared sofa", "finishes a friend's sitting room",
          "brightens a dorm bed for a first term away",
          "props a grandparent up in an armchair")),
    Lane("basket", "bags", "basket", "basket", "basket", "in_the_round", "Basket",
         "a storage basket", "worked in rounds up from a flat base", STRIPES, STORAGE,
         ("tidies yarn and hooks beside the sofa", "keeps spare towels in a guest bathroom",
          "keeps nappies beside a changing mat", "corrals chargers and pens on a desk",
          "keeps a dog's toys in one place", "sorts post on a hall table"),
         view="from a three-quarter angle"),
    Lane("tapestry-basket", "bags", "colourwork", "basket", "basket", "tapestry", "Basket",
         "a colourwork basket", "worked in rounds up from a flat base", TAPESTRY_MOTIFS,
         STORAGE, ("sits on an open shelf as the room's one bold object",
                   "keeps a plant pot out of sight on a windowsill",
                   "keeps folded muslins on a nursery shelf"),
         view="from a three-quarter angle"),
    Lane("wall-panel", "home_decor", None, "wall_decor", "wall_hanging", "flat_rows",
         "Wall Panel", "a hung panel", "worked flat in rows on a dowel", STRIPES, HOME,
         ("gives a bare hallway wall some colour", "warms a rented flat without nails",
          "hangs above a couple's bed", "fills the wall over a friend's desk",
          "sets the colour of a teenager's room", "brightens a grandparent's landing")),
    # Generic flat forms: admitted family, but #108 holds them honestly (no earned qualifier).
    Lane("baby-blanket", "blankets", "baby", "baby", "rectangle_throw", "flat_rows",
         "Baby Blanket", "a pram-sized blanket", "worked flat in rows", BABY_STRIPES, NURSERY,
         ("wraps a newborn on the first walks out",
          "is made by a grandparent to welcome a first grandchild",
          "rides along in a toddler's pushchair", "covers a lap during night feeds")),
    Lane("throw", "blankets", None, "blanket", "rectangle_throw", "flat_rows", "Sofa Throw",
         "a sofa throw", "worked flat in rows", STRIPES, HOME,
         ("lies folded over the end of a new sofa", "warms guests on a cold evening",
          "is the first blanket a couple owns", "drapes over a friend's reading chair",
          "comes along to a student flat", "covers a grandparent's knees in winter")),
    Lane("runner", "kitchen_bath", None, "runner", "runner", "flat_rows", "Table Runner",
         "a table runner", "worked flat in rows", STRIPES, TABLE,
         ("sets a bright table for a first dinner party", "calms a weekend breakfast table",
          "dresses a family table for a Sunday lunch", "lays a couple's first table",
          "cheers up a shared office kitchen")),
    Lane("placemat", "kitchen_bath", None, "placemat", "flat_panel", "flat_rows",
         "Placemat Pair", "a pair of placemats", "worked flat in rows", STRIPES, TABLE,
         ("lays two places for a first supper at home", "marks a breakfast spot by a window",
          "matches a grandparent's best plates", "sets a table for two after a wedding",
          "brightens a desk lunch at work")),
    Lane("dishcloth", "kitchen_bath", None, "dishcloth", "flat_panel", "flat_rows",
         "Dishcloth", "a square dishcloth", "worked flat in rows", KITCHEN_STRIPES, TABLE,
         ("wipes down a new kitchen counter", "washes up after a quiet supper",
          "is tucked into a hostess basket", "is a practical wedding-shower gift",
          "lives by the office kettle")),
    Lane("pet-mat", "home_decor", None, "pet", "flat_panel", "flat_rows", "Pet Mat",
         "a pet mat", "worked flat in rows", BABY_STRIPES[::-1], STORAGE,
         ("lines a cat's favourite windowsill", "goes in a dog's crate on car trips",
          "cushions a rescue pet's first bed", "lies under a food bowl")),
    Lane("scarf", "garments", "garment", "scarf", "scarf", "flat_rows", "Scarf",
         "a long scarf", "worked flat in rows", STRIPES, WEAR,
         ("wraps twice round on a windy walk", "is tucked into a coat for a date",
          "is worn to the bus stop", "is a grandparent's Sunday scarf",
          "goes on a trip to the mountains")),
    Lane("coaster", "kitchen_bath", None, "coaster", "coaster", "flat_rows", "Coaster Set",
         "a set of coasters", "worked flat in rows", STRIPES, TABLE,
         ("protects a new coffee table from mugs", "sits under a morning cup",
          "protects a polished sideboard from glasses", "goes with a couple's first mugs",
          "brightens a shared office desk")),
    # ---- held families (not certified yet): visible, with reasons, never dropped ----
    Lane("amigurumi", "amigurumi", "stuffed_animal", "amigurumi", "toy", "amigurumi_shaping",
         "Amigurumi", "a stuffed animal", "worked in spiral rounds with sculpted shaping",
         ANIMALS, CHARACTER,
         ("sits on a shelf as a birthday companion", "keeps a desk company through exams",
          "is a maker's own collectable for a shelf", "waits under the tree for a grandchild",
          "is the handmade present a friend did not expect",
          "watches over a nursery from a high shelf"),
         view="seated, facing the camera"),
    Lane("sea-amigurumi", "amigurumi", "stuffed_animal", "amigurumi", "toy",
         "amigurumi_shaping", "Amigurumi", "a stuffed sea animal",
         "worked in spiral rounds with sculpted shaping", SEA, CHARACTER,
         ("rides in a beach bag on holiday", "sits on a bathroom shelf",
          "is a seaside souvenir made at home", "is tucked into a grandchild's stocking",
          "is a keepsake from a first trip to the coast"),
         view="seated, facing the camera"),
    Lane("garden-amigurumi", "amigurumi", "stuffed_animal", "amigurumi", "toy",
         "amigurumi_shaping", "Amigurumi", "a stuffed garden animal",
         "worked in spiral rounds with sculpted shaping", GARDEN, CHARACTER,
         ("sits in an Easter basket", "lives on a classroom shelf", "perches on a potted plant",
          "is a spring present for a grandchild", "is a get-well present for a friend"),
         view="seated, facing the camera"),
    Lane("animal-cushion", "home_decor", "pillow", "pillow", "pillow", "amigurumi_shaping",
         "Animal Cushion", "an animal-shaped cushion",
         "worked in spiral rounds with sculpted shaping", ANIMALS[::-1], HOME,
         ("curls up in the corner of a reading chair", "greets guests from a spare bed",
          "sits between a couple on the sofa", "lounges on a friend's window seat",
          "props up a teenager doing homework in bed",
          "keeps a grandparent's armchair company")),
    Lane("cable-cushion", "home_decor", "pillow", "pillow", "pillow", "cable_panel",
         "Cable Cushion", "a cushion cover", "worked in crossed post stitches", COLOUR_CHARTS,
         HOME, ("adds relief to a plain linen sofa", "sits on a guest bed in deep winter",
                "sits on a wedding-gift armchair", "dresses a friend's window seat",
                "props up a teenager reading")),
    Lane("baby-cardigan", "garments", "baby", "garment", "fitted_garment", "top_down_yoke",
         "Baby Cardigan", "a baby cardigan", "worked top down from a yoke in graded sizes",
         BABY_GARMENT, NURSERY,
         ("is the first knitwear a newborn wears home",
          "is buttoned on for a first family photograph",
          "keeps a toddler warm at the park", "layers over a sleepsuit on cool mornings"),
         view="laid flat, front open"),
    Lane("yoke-sweater", "garments", "garment", "garment", "fitted_garment", "top_down_yoke",
         "Yoke Sweater", "a fitted sweater", "worked top down from a yoke in graded sizes",
         GARMENT_MOTIFS, WEAR,
         ("is the layer reached for on cold mornings", "is made to fit one person exactly",
          "goes back to class in a colour nobody else has",
          "is unwrapped and worn the same day", "ends up a friend's favourite thing to wear"),
         view="worn, front on"),
    Lane("cardigan", "garments", "garment", "garment", "fitted_garment", "bottom_up",
         "Cardigan", "a fitted cardigan", "worked bottom up in graded sizes",
         CARDIGAN_MOTIFS, WEAR,
         ("is thrown on over a shirt for the school run", "is worn open on spring evenings",
          "is worn to every lecture of the term", "keeps a grandparent warm at church",
          "goes over a dress at a summer wedding"),
         view="worn, front on"),
    Lane("beanie", "hats", "garment", "hat", "hat", "in_the_round", "Beanie",
         "a fitted beanie", "worked in the round from the crown", GARMENT_MOTIFS, WEAR,
         ("keeps ears warm on a dog walk", "is pulled on for a winter date",
          "is worn to the bus stop all term", "matches a grandparent's coat",
          "goes on a ski weekend"),
         view="worn, three-quarter"),
    Lane("mosaic-blanket", "blankets", "colourwork", "mosaic_blanket", "rectangle_throw",
         "mosaic_overlay", "Mosaic Throw", "a sofa throw", "worked in overlay mosaic rows",
         COLOUR_CHARTS, HOME,
         ("is the statement piece on a new sofa", "is laid over a guest bed",
          "is an anniversary blanket for two", "is a long project for a keen maker",
          "is folded at the foot of a student bed")),
    Lane("c2c-blanket", "blankets", "colourwork", "graphghan", "rectangle_throw",
         "corner_to_corner", "Corner Throw", "a sofa throw",
         "worked corner to corner in charted tiles", COLOUR_CHARTS[::-1], HOME,
         ("brightens a playroom sofa", "hangs over the back of a guest armchair",
          "is a wedding blanket for a couple", "is a gift for a friend's new flat",
          "covers a teenager's beanbag")),
    Lane("granny-blanket", "blankets", None, "blanket", "rectangle_throw", "granny_square",
         "Square Throw", "a sofa throw", "worked as squares sewn into a grid",
         COLOUR_CHARTS, HOME,
         ("uses up a stash of leftover yarn", "warms a porch swing in autumn",
          "is pieced by a family for a wedding", "travels in a camper van",
          "is a dorm blanket in loud colours")),
    Lane("tote", "bags", None, "bag", "bag", "in_the_round", "Market Tote", "a market tote",
         "worked in the round with straps", STRIPES, STORAGE,
         ("carries vegetables home from the market", "carries a towel to the beach",
          "carries nappies on a day out", "carries books to class",
          "carries a dog's lead and treats", "carries a library haul")),
    Lane("shawl", "garments", "garment", "shawl", "draped_garment", "flat_rows", "Shawl",
         "a triangle shawl", "worked flat from the neck point", STRIPES[::-1], WEAR,
         ("warms shoulders at an outdoor supper", "is wrapped round a partner at a concert",
          "is worn over a coat on cold walks to class",
          "is worn by a grandparent at a christening",
          "is the travel layer a friend packs every time")),
    Lane("stocking", "stockings", None, "stocking", "stocking", "flat_rows", "Stocking",
         "a holiday stocking", "worked flat in rows and seamed", COLOUR_CHARTS, HOME,
         ("hangs on the mantel of a first home", "waits by the fire for a visiting guest",
          "is a couple's first shared stocking", "hangs on a friend's bedpost",
          "hangs on a dorm door")),
    Lane("ornament", "ornaments", None, "ornament", "ornament", "in_the_round", "Ornament",
         "a hanging ornament", "worked in the round and stuffed lightly", SMALL_GIFTS,
         CHARACTER,
         ("hangs on a child's own branch of the tree", "hangs from a desk lamp",
          "goes on a maker's own tree every year", "is tied to a grandchild's present",
          "is a stocking filler for a friend"),
         view="hung against greenery"),
)
LANES_BY_KEY = {lane.key: lane for lane in LANES}


def variant_options(lane: Lane):
    """(motif, use, contexts to try in order): motif i with use i, trying context i + offset
    first, then the rest of the lane's bank in rotation. The generator takes the first
    context that is ORIGINAL against everything already in the pool; a motif with none is
    kept as the first option and refused as the clone it is."""
    offset = LANES.index(lane) if lane in LANES else 0
    n = min(len(lane.motifs), len(lane.uses))
    k = len(lane.contexts)
    for i in range(n):
        start = (i + offset) % k
        yield lane.motifs[i], lane.uses[i], [lane.contexts[(start + j) % k] for j in range(k)]


def variant_key(motif: Motif, ctx: Context) -> str:
    return f"{motif.key}-{ctx.recipient.replace('_', '-')}"


def lane_variants(lane: Lane):
    """(variant key, motif, context, use): motif i with use i and context i + offset, so
    within a lane motif, use and context all change together, and two lanes drawing on the
    same motif and context banks pair them differently (the offset is the lane's place)."""
    offset = LANES.index(lane) if lane in LANES else 0
    n = min(len(lane.motifs), len(lane.contexts), len(lane.uses))
    for i in range(n):
        m, c = lane.motifs[i], lane.contexts[(i + offset) % len(lane.contexts)]
        yield f"{m.key}-{c.recipient.replace('_', '-')}", m, c, lane.uses[i]


# ---- table --------------------------------------------------------------------------------


class ConceptPoolEntry(Base):
    """One generated concept and where it stands. Never deleted: a held or stale concept is a
    record of demand the factory cannot meet yet, which is information."""

    __tablename__ = "concept_pool_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    lane: Mapped[str] = mapped_column(String(40), index=True)
    pod: Mapped[str] = mapped_column(String(40), index=True)
    category: Mapped[str] = mapped_column(String(40), index=True)
    family: Mapped[str] = mapped_column(String(40), index=True)
    family_status: Mapped[str] = mapped_column(String(20), default="")
    state: Mapped[str] = mapped_column(String(12), index=True)
    reasons: Mapped[list] = mapped_column(JSON, default=list)
    title: Mapped[str] = mapped_column(String(200), default="")
    concept: Mapped[dict] = mapped_column(JSON, default=dict)
    brief: Mapped[dict] = mapped_column(JSON, default=dict)
    size_range: Mapped[dict] = mapped_column(JSON, default=dict)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    originality: Mapped[dict] = mapped_column(JSON, default=dict)
    facets: Mapped[list] = mapped_column(JSON, default=list)
    shops: Mapped[list] = mapped_column(JSON, default=list)
    priority: Mapped[float] = mapped_column(Float, default=0.0)
    research_task_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    admitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
                                                         nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(64), default="")


def _ensure(db) -> None:
    ConceptPoolEntry.__table__.create(bind=db.engine, checkfirst=True)


def _now(now=None) -> datetime:
    now = now or datetime.now(timezone.utc)
    return now if now.tzinfo else now.replace(tzinfo=timezone.utc)


def _aware(v):
    return None if v is None else (v if v.tzinfo else v.replace(tzinfo=timezone.utc))


# ---- demand signals -----------------------------------------------------------------------


def _watchlist_keys() -> dict[str, str]:
    from ..intel.watchlist import WATCHLIST

    return {m.key: m.shop_name for m in WATCHLIST}


def observed_listings(db, *, now: datetime) -> list[dict]:
    """Fresh watchlist listings as demand facts: id, shop, pod, facets, price, favourites,
    season, last seen. Titles are read here to classify, and are not returned."""
    from ..core.models import BenchmarkListing

    keys = _watchlist_keys()
    floor = now - timedelta(days=SIGNAL_FRESH_DAYS)
    out = []
    with db.session() as s:
        for r in s.scalars(select(BenchmarkListing).where(
                BenchmarkListing.benchmark_key.in_(tuple(keys)))):
            seen = _aware(r.last_seen)
            if seen is None or seen < floor:
                continue
            if str(r.audit_state or "") in ("withdrawn", "removed"):
                continue
            detail = dict(r.detail or {})
            out.append({"id": r.id, "shop": r.benchmark_key, "pod": str(r.pod or ""),
                        "facets": sorted(facets_of(r.title)),
                        "price_cad": float(r.price_cad or 0.0),
                        "favourites": int(detail.get("num_favorers") or 0),
                        "seasonal": str(r.seasonal or ""),
                        "seen": seen.date().isoformat()})
    return out


def review_themes(db) -> dict[str, dict]:
    """The newest recurring complaint themes read per watchlist shop (counts only)."""
    from ..core.models import BenchmarkObservation

    keys = tuple(_watchlist_keys())
    out: dict[str, dict] = {}
    with db.session() as s:
        for o in s.scalars(select(BenchmarkObservation).where(
                BenchmarkObservation.benchmark_key.in_(keys))
                .order_by(BenchmarkObservation.id.desc())):
            rev = (o.detail or {}).get("reviews") if isinstance(o.detail, dict) else None
            if not isinstance(rev, dict) or o.benchmark_key in out:
                continue
            out[o.benchmark_key] = {"ref": f"benchmark_observation:{o.id}",
                                    "read": int(rev.get("reviews_read") or 0),
                                    "recurring": sorted((rev.get("recurring") or {}).keys())}
    return out


def _supports(lane: Lane, listing: dict) -> bool:
    if lane.facet is not None:
        return lane.facet in listing["facets"]
    return listing["pod"] == lane.pod


def upcoming_events(today: date, horizon_days: int = 120) -> list[str]:
    from .market import SEASONAL_EVENTS

    return [e.name for e in SEASONAL_EVENTS if 0 <= (e.date - today).days <= horizon_days]


def lane_signal(lane: Lane, listings: list[dict], themes: dict[str, dict],
                today: date) -> dict | None:
    """The validated demand behind one lane, or None when there is not enough of it."""
    support = [x for x in listings if _supports(lane, x)]
    if len(support) < MIN_SIGNAL_LISTINGS:
        return None
    support.sort(key=lambda x: (-x["favourites"], x["id"]))
    shops = Counter(x["shop"] for x in support)
    prices = sorted(x["price_cad"] for x in support if x["price_cad"] > 0)
    seasons = Counter(x["seasonal"] for x in support if x["seasonal"])
    facets = Counter(f for x in support for f in x["facets"])
    return {
        "listings": len(support), "shops": dict(sorted(shops.items())),
        "favourites": sum(x["favourites"] for x in support),
        "refs": [{"ref": f"benchmark_listing:{x['id']}", "shop": x["shop"], "seen": x["seen"],
                  "favourites": x["favourites"]} for x in support[:MAX_EVIDENCE_REFS]],
        "price_band_cad": ({"min": prices[0], "median": prices[len(prices) // 2],
                            "max": prices[-1], "n": len(prices)} if prices else None),
        "seasonal": dict(seasons), "facets": dict(facets),
        "upcoming_events": upcoming_events(today) if seasons else [],
        "review_themes": {k: themes[k] for k in sorted(shops) if k in themes},
        "newest_seen": max(x["seen"] for x in support),
        "oldest_seen": min(x["seen"] for x in support),
    }


def priority_of(lane: Lane, signal: dict) -> float:
    """Owner demand weighting (D-OWNER-CORE-FAMILIES): MadelineMaeCo first, core facets, then
    the weighted facets; strength from listings, shops and favourites."""
    strength = (math.log1p(signal["listings"]) + 0.5 * len(signal["shops"])
                + 0.25 * math.log1p(signal["favourites"]))
    facet_w = FACET_WEIGHT.get(lane.facet or "", 1.0)
    shop_w = PRIORITY_SHOP_WEIGHT if PRIORITY_SHOP in signal["shops"] else 1.0
    return round(strength * facet_w * shop_w, 3)


# ---- one concept --------------------------------------------------------------------------


def slug_for(lane: Lane, vkey: str) -> str:
    return f"pool-{lane.key}-{vkey}"[:60].rstrip("-")


def title_for(lane: Lane, motif: Motif) -> str:
    return f"{motif.title} {lane.noun}"


def premise_for(lane: Lane, motif: Motif, use: str) -> str:
    what = lane.what[0].upper() + lane.what[1:]
    return f"{what} {lane.build}, showing {motif.phrase}, that {use}"


def concept_fields(lane: Lane, motif: Motif, ctx: Context, use: str) -> dict:
    return {"premise": premise_for(lane, motif, use), "pod": lane.pod, "form": lane.form,
            "construction": lane.construction, "motif": motif.phrase,
            "palette_story": motif.palette, "recipient": ctx.recipient,
            "occasion": ctx.occasion, "feeling": ctx.feeling, "function": use}


def storyboard(lane: Lane, motif: Motif) -> str:
    """#88: what the thumbnail shows, derived from the object, its view, motif and palette."""
    return f"{lane.what} {lane.view} showing {motif.phrase} in {motif.palette}"


def as_concept(slug: str, title: str, fields: dict, make_lane: str = "SHORT"):
    from ..creative.concept import Concept

    return Concept(key=slug, title=title, make_lane=make_lane,
                   provenance="radar.concept_pool", **fields)


def honesty_reasons(concept) -> list[str]:
    """#108 honesty: the qualifiers a premise declares must be ones its construction earns.

    `qualifiers_for` reads qualifiers off premise words and the construction. A word in the
    premise ("motif", "panels", "holds") that declares a qualifier the construction does not
    build is a claim the object cannot carry, and is refused here before the gate sees it."""
    from ..creative.intake import qualifier_constructions, qualifiers_for

    got = set(qualifiers_for(concept))
    earned = set(qualifier_constructions({concept.construction}).values())
    extra = sorted(got - earned)
    return [f"#108 honesty: the premise declares {extra} that {concept.construction!r} "
            f"does not build; a sentence is not a silhouette"] if extra else []


def size_range(lane: Lane, family: str) -> dict:
    """The target size range, from the source each family honestly has."""
    from ..creative import construction_families as CF, size_truth

    fam = CF.FAMILIES.get(family)
    if lane.category in ("baby", "blanket"):
        cls = size_truth.BLANKET_CLASSES["baby" if lane.category == "baby" else "throw"]
        return {"sizes": [f"{cls['default'][0]:.0f} x {cls['default'][1]:.0f} cm"],
                "range_cm": {"short": list(cls["short"]), "long": list(cls["long"])},
                "source": cls["basis"]}
    if lane.category == "basket":
        from ..products.vessels import BASKET_SIZES

        return {"sizes": [f"{b.key}: {b.across_cm:.0f} cm across x {b.tall_cm:.0f} cm tall"
                          for b in BASKET_SIZES],
                "source": fam.size_source if fam else "products.vessels.BASKET_SIZES"}
    if lane.category == "pillow":
        return {"sizes": ["square 12-26 in", "lumbar 12 x 20 in to 14 x 24 in"],
                "source": size_truth.PILLOW_FORMS}
    if fam is not None:
        return {"sizes": list(fam.sizes), "source": fam.size_source}
    if lane.form in ("fitted_garment", "hat"):
        return {"sizes": "UNKNOWN", "source": "no graded body table is wired to this family "
                                              "on the radar path; sizes come with its engine"}
    return {"sizes": "UNKNOWN", "source": f"no engine binds sizes for {family!r} yet"}


def build(lane: Lane, vkey: str, motif: Motif, ctx: Context, use: str, signal: dict,
          research: dict | None) -> dict:
    """The concept record before judgement (pure)."""
    from ..creative import construction_families as CF
    from ..creative.intake import qualifiers_for
    from ..creative.preengineering import FAIL, _silhouette

    slug, title = slug_for(lane, vkey), title_for(lane, motif)
    fields = concept_fields(lane, motif, ctx, use)
    reasons: list[str] = []
    try:
        concept = as_concept(slug, title, fields)
    except Exception as exc:  # noqa: BLE001 - closed vocabulary refusal is a reason
        concept = None
        reasons.append(f"concept vocabulary: {exc}")
    qualifiers = qualifiers_for(concept) if concept is not None else []
    brief = {"thumbnail_storyboard": storyboard(lane, motif),
             "silhouette_qualifiers": qualifiers}
    sil = _silhouette(concept, brief) if concept is not None else {"status": FAIL,
                                                                   "reasons": []}
    route = CF.route(category=lane.category, title=title, form=lane.form,
                     construction=lane.construction, slug=slug, premise=fields["premise"])
    family = route["family"]
    if concept is not None:
        reasons += honesty_reasons(concept)
    if not route["admitted"]:
        reasons.append(route["reason"])
    if sil["status"] == FAIL:
        reasons += [f"#108 {r}" for r in (sil.get("reasons") or [])[:2]]
    return {
        "slug": slug, "lane": lane.key, "pod": lane.pod, "category": lane.category,
        "title": title, "family": family, "family_status": route["status"],
        "admitted_family": bool(route["admitted"]), "concept": fields, "brief": brief,
        "brief_provenance": {"thumbnail_storyboard": "lane.what, lane.view, motif, palette",
                             "silhouette_qualifiers": "creative.intake.qualifiers_for"},
        "silhouette": {"passes": sil["status"] != FAIL,
                       "generic_form": bool((sil.get("detail") or {}).get("generic_form"))},
        "size_range": size_range(lane, family),
        "facets": sorted({lane.facet} - {None}),
        "evidence": {**signal, "research": research}, "reasons": reasons,
        "_concept": concept,
    }


# ---- originality ---------------------------------------------------------------------------


def _specific(text: str) -> set[str]:
    from .intake import _specific_tokens

    return _specific_tokens(text)


def competitor_titles(db) -> list[tuple[str, set[str], str]]:
    from ..core.models import BenchmarkListing

    with db.session() as s:
        rows = s.execute(select(BenchmarkListing.id, BenchmarkListing.title)).all()
    from .intake import _norm

    return [(f"benchmark_listing:{i}", _specific(t), _norm(t)) for i, t in rows if t]


def copy_reasons(title: str, competitors) -> list[str]:
    """A competitor's title, whole or by its specific words, is never ours."""
    from .intake import _jaccard, _norm

    mine, norm = _specific(title), _norm(title)
    for ref, tokens, their_norm in competitors:
        if norm and norm == their_norm:
            return [f"copy: the title is {ref}'s title"]
        if mine and _jaccard(mine, tokens) >= 0.8:
            return [f"copy: the title restates {ref}'s title"]
    return []


def references(db) -> list:
    """What a new concept must be distinct from: the briefed catalogue and the POOL."""
    from ..creative.audit import briefed_catalogue_concepts
    from ..creative.concept import Concept, ConceptRefused

    out = list(briefed_catalogue_concepts()[0])
    from . import intake

    for r in intake.approved_rows(db):
        try:
            out.append(Concept(**{**r.concept, "key": r.slug,
                                  "title": (r.seed or {}).get("title", r.slug),
                                  "make_lane": (r.seed or {}).get("make_lane", "SHORT")}))
        except (ConceptRefused, TypeError):
            continue
    return out


def pool_titles_against_seeds(title: str, category: str) -> list[str]:
    """Intake refuses a title restating a POOL title in the same category; so do we, first."""
    from .intake import _jaccard, _norm
    from .opportunity import POOL

    out = []
    for s in POOL:
        if _norm(s.title) == _norm(title):
            out.append(f"duplicate: title is POOL concept {s.slug!r}")
        elif s.category == category and _jaccard(_specific(title), _specific(s.title)) >= 0.5:
            out.append(f"duplicate: restates POOL concept {s.slug!r} in the same category")
    return out


def originality(db, cand: dict, accepted: list, refs: list, competitors, cards_by_pod) -> dict:
    """Clone / copy refusals. `accepted` are the pool concepts already kept this pass."""
    from ..creative.concept import nearest
    from ..creative.prospecting import MIN_NOVELTY, _matches_a_listing

    concept = cand["_concept"]
    reasons = copy_reasons(cand["title"], competitors)
    reasons += pool_titles_against_seeds(cand["title"], cand["category"])
    detail: dict = {"min_novelty": MIN_NOVELTY}
    if concept is None:
        return {"reasons": reasons, "detail": detail}
    near, gap = nearest(concept, refs + accepted)
    detail.update(nearest=near.key if near else None, distance=gap)
    if near is not None and gap < MIN_NOVELTY:
        reasons.append(f"clone: {gap} from {near.key!r}, below the novelty floor "
                       f"{MIN_NOVELTY}")
    cards = cards_by_pod.get(cand["pod"])
    if cards is None:
        from ..creative.prospecting import watchlist_comparables

        cards = cards_by_pod[cand["pod"]] = watchlist_comparables(db, pod=cand["pod"])
    detail["benchmark_cards"] = len(cards)
    holds: list[str] = []
    if not cards:
        # No observed listings for the pod: the design-copy check cannot run, so originality
        # is UNKNOWN. UNKNOWN is never a pass: the concept is HELD until cards exist.
        holds.append(HELD_NO_CARDS)
        return {"reasons": reasons, "holds": holds, "detail": detail}
    twin = _matches_a_listing(concept, cards)
    if twin:
        reasons.append(f"copy: indistinguishable from observed listing {twin}")
    return {"reasons": reasons, "holds": holds, "detail": detail}


HELD_NO_CARDS = ("held: originality against observed listings is UNKNOWN (no benchmark cards "
                 "for pod)")


def classify(cand: dict, orig_reasons: list[str],
             orig_holds: list[str] = ()) -> tuple[str, list[str]]:
    """REFUSED for clones and copies; HELD for every other reason (an UNKNOWN originality
    check included); READY otherwise."""
    if orig_reasons:
        return REFUSED, orig_reasons + cand["reasons"]
    held = list(cand["reasons"]) + list(orig_holds)
    if held:
        return HELD, held
    return READY, []


# ---- research behind an arena --------------------------------------------------------------


def research_for_pod(db, pod: str, *, today: date) -> dict | None:
    """The answered research task behind a validated watchlist gap in this pod, with its
    fact-grade refs, or None. Intake's own evidence floor decides whether it is usable."""
    from ..core.models import CoverageGap
    from ..intel import coverage as C
    from . import intake
    from .proposal_writer import WATCHLIST_KEY

    with db.session() as s:
        gaps = [(g.id, g.state, dict(g.evidence or {})) for g in s.scalars(
            select(CoverageGap).where(CoverageGap.benchmark_key == WATCHLIST_KEY,
                                      CoverageGap.pod == pod).order_by(CoverageGap.id))]
    for gid, state, ev in gaps:
        if state not in (C.UNCOVERED, C.CONCEPTING):
            continue
        tid = ev.get("research_task_id")
        if not tid:
            continue
        refs = _task_refs(db, int(tid))
        if not refs:
            continue
        got = intake.research_evidence(db, int(tid), refs, today=today)
        if got.get("ok"):
            return {"task": int(tid), "gap": gid, "refs": refs,
                    "quality": got.get("quality"), "confidence": got.get("confidence")}
    return None


def _task_refs(db, task_id: int) -> list[str]:
    from ..intel import research

    research._ensure(db)
    with db.session() as s:
        t = s.get(research.ResearchTask, int(task_id))
        if t is None or t.state != research.ANSWERED:
            return []
        facts = [f for f in (t.findings or []) if f.get("claim_class") == "fact"
                 and f.get("ref")]
    refs = [f["ref"] for f in facts]
    for f in facts:
        refs += [r for r in f.get("rests_on") or [] if r not in refs]
    return refs


# ---- spend bound --------------------------------------------------------------------------


def unit_cost_cad() -> float | None:
    """The padded downstream estimate of one admitted concept: its vision verdicts, on the
    same estimator the pre-call ceiling uses. None when it cannot be computed (fail closed)."""
    try:
        from ..intel import vision

        return round(vision.per_image_estimate_cad() * DOWNSTREAM_CALLS_PER_CONCEPT, 6)
    except Exception:  # noqa: BLE001 - an unknown cost admits nothing
        return None


def admission_allowance(db, *, now: datetime, unit_cad: float | None = None) -> dict:
    """How many READY concepts may be admitted this run, and which bound binds.

    Three bounds: the per-run cap; the month's authorised ceiling less what was spent and
    what is reserved; the pool's own share of the month less what its admissions this month
    already committed. An unknown unit cost or an unreadable ledger admits nothing."""
    from ..finance import reservations, spend_policy, spend_report

    unit = unit_cost_cad() if unit_cad is None else unit_cad
    if not unit or unit <= 0:
        return {"units": 0, "binding": "unit_cost_unknown",
                "why": "the downstream cost of an admitted concept could not be estimated; "
                       "nothing is admitted on an unknown cost"}
    try:
        spent = float(spend_report.what_it_bought(db, now=now)["spent_cad"])
        held = float(reservations.outstanding_cad(db))
    except Exception as exc:  # noqa: BLE001 - an unreadable ledger is a stop
        return {"units": 0, "binding": "ledger_unreadable",
                "why": f"the spend ledger could not be read ({type(exc).__name__})"}
    ceiling = spend_policy.ceiling_cad()
    month_room = max(0.0, ceiling - spent - held)
    share = round(ceiling * POOL_SHARE_OF_CEILING, 4)
    committed = admitted_this_month(db, now=now) * unit
    share_room = max(0.0, share - committed)
    bounds = {"per_run": ADMIT_PER_RUN,
              "monthly_ceiling": int(month_room // unit),
              "pool_share": int(share_room // unit)}
    binding = min(bounds, key=bounds.get)
    return {"units": max(0, bounds[binding]), "binding": binding, "bounds": bounds,
            "unit_cost_cad": unit, "ceiling_cad": ceiling, "spent_month_cad": round(spent, 4),
            "reserved_cad": round(held, 4), "pool_share_cad": share,
            "committed_cad": round(committed, 4),
            "why": f"{bounds[binding]} admission(s) fit under the {binding.replace('_', ' ')}"}


def admitted_this_month(db, *, now: datetime) -> int:
    _ensure(db)
    start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    with db.session() as s:
        return len(list(s.scalars(select(ConceptPoolEntry.id).where(
            ConceptPoolEntry.admitted_at.is_not(None),
            ConceptPoolEntry.admitted_at >= start))))


# ---- the pass ----------------------------------------------------------------------------


def _fingerprint(rec: dict) -> str:
    body = {k: rec[k] for k in ("title", "concept", "brief", "family", "reasons")}
    body["evidence"] = [r["ref"] for r in rec["evidence"].get("refs") or []]
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()


def generate(db, *, now: datetime | None = None) -> list[dict]:
    """Every concept the current evidence supports, judged; nothing persisted (pure read)."""
    now = _now(now)
    today = now.date()
    listings = observed_listings(db, now=now)
    themes = review_themes(db)
    competitors = competitor_titles(db)
    refs = references(db)
    cards: dict = {}
    research_cache: dict = {}
    out, accepted = [], []
    plans = []
    for lane in LANES:
        sig = lane_signal(lane, listings, themes, today)
        if sig is None:
            continue
        plans.append((priority_of(lane, sig), lane, sig))
    # Highest-priority lanes claim novelty first, so a clone is refused in the weaker lane.
    plans.sort(key=lambda p: (-p[0], p[1].key))
    prior = _prior_contexts(db)
    for prio, lane, sig in plans:
        if lane.pod not in research_cache:
            research_cache[lane.pod] = research_for_pod(db, lane.pod, today=today)
        research = research_cache[lane.pod]
        for motif, use, options in variant_options(lane):
            # Stability: the context this motif already holds in the pool is tried first, so
            # an unchanged pool keeps its slugs.
            held = prior.get((lane.key, motif.key))
            options = sorted(options, key=lambda c: c.recipient != held)
            first = None
            for ctx in options:
                cand = build(lane, variant_key(motif, ctx), motif, ctx, use, sig, research)
                orig = originality(db, cand, accepted, refs, competitors, cards)
                if first is None:
                    first = (cand, orig)
                if not any(r.startswith("clone:") for r in orig["reasons"]):
                    break
            else:
                cand, orig = first
            state, reasons = classify(cand, orig["reasons"], orig.get("holds", ()))
            if state != REFUSED and cand["_concept"] is not None:
                accepted.append(cand["_concept"])
            cand.update(state=state, reasons=reasons, originality=orig["detail"],
                        priority=prio, shops=sorted(sig["shops"]))
            out.append(cand)
    return out


def _prior_contexts(db) -> dict[tuple[str, str], str]:
    _ensure(db)
    out = {}
    with db.session() as s:
        for lane, slug, concept in s.execute(select(ConceptPoolEntry.lane, ConceptPoolEntry.slug,
                                                    ConceptPoolEntry.concept)):
            lane_obj = LANES_BY_KEY.get(lane)
            if lane_obj is None:
                continue
            for m in lane_obj.motifs:
                if slug.startswith(f"pool-{lane}-{m.key}-"):
                    out[(lane, m.key)] = (concept or {}).get("recipient")
    return out


def replenish(db, *, now: datetime | None = None, audit=None, unit_cad: float | None = None,
              admit: bool = True) -> dict:
    """One pass: generate, upsert (never delete), mark concepts no fresh signal supports
    STALE, then admit READY concepts up to the spend allowance. Idempotent: an unchanged
    concept is not rewritten."""
    _ensure(db)
    now = _now(now)
    cands = generate(db, now=now)
    seen, new, changed = set(), [], []
    with db.session() as s:
        existing = {e.slug: e for e in s.scalars(select(ConceptPoolEntry))}
        for c in cands:
            seen.add(c["slug"])
            fp = _fingerprint(c)
            row = existing.get(c["slug"])
            values = dict(lane=c["lane"], pod=c["pod"], category=c["category"],
                          family=c["family"], family_status=c["family_status"],
                          title=c["title"], concept=c["concept"],
                          brief={**c["brief"], "provenance": c["brief_provenance"]},
                          size_range=c["size_range"], evidence=c["evidence"],
                          originality=c["originality"], facets=c["facets"], shops=c["shops"],
                          priority=c["priority"], fingerprint=fp)
            if row is None:
                s.add(ConceptPoolEntry(slug=c["slug"], state=c["state"], reasons=c["reasons"],
                                       generated_at=now, updated_at=now, **values))
                new.append(c["slug"])
                continue
            if row.fingerprint == fp and row.state != STALE:
                continue
            for k, v in values.items():
                setattr(row, k, v)
            row.updated_at = now
            if row.state != ADMITTED or c["state"] != READY:
                # An admitted concept stays admitted while it is still READY; anything that
                # now holds or refuses it is recorded (intake withdraws on its own evidence).
                row.state, row.reasons = c["state"], c["reasons"]
            changed.append(c["slug"])
        stale = []
        for slug, row in existing.items():
            if slug not in seen and row.state != STALE:
                row.reasons = list(row.reasons or []) + [
                    f"stale: no fresh validated signal supports it as of "
                    f"{now.date().isoformat()}"]
                row.state = STALE
                row.updated_at = now
                stale.append(slug)
    admitted = admit_ready(db, now=now, audit=audit, unit_cad=unit_cad) if admit else {
        "admitted": [], "allowance": None}
    if audit is not None:
        audit(GENERATED_ACTION, detail={"candidates": len(cands), "new": len(new),
                                        "changed": len(changed), "stale": len(stale),
                                        "admitted": admitted["admitted"]})
    return {"candidates": len(cands), "new": new, "changed": changed, "stale": stale,
            **admitted, "health": health(db, now=now), "network_calls": 0, "spend_cad": 0.0}


def proposal_from(row: ConceptPoolEntry, research: dict) -> dict:
    """The intake proposal for a pool entry: our words, the task's fact refs, no shop."""
    from statistics import median

    from .opportunity import POOL
    from .proposal_writer import QUALIFIER_RULE

    seeds = [s for s in POOL if s.category == row.category]
    band = (row.evidence or {}).get("price_band_cad") or {}
    price = (round(median(s.price_cad for s in seeds), 2) if seeds
             else round(min(float(band.get("median") or 9.0), 18.0), 2))
    hours = ([round(median(s.maker_hours[0] for s in seeds), 1),
              round(median(s.maker_hours[1] for s in seeds), 1)] if seeds else [3.0, 6.0])
    design = round(median(s.design_hours for s in seeds), 1) if seeds else 4.0
    ev = row.evidence or {}
    return {
        "slug": row.slug, "title": row.title, "category": row.category,
        "price_cad": price, "maker_hours": hours, "design_hours": design,
        "rationale": (f"{ev.get('listings', 0)} fresh listings across "
                      f"{len(ev.get('shops') or {})} watchlist shop(s) show demand in this "
                      f"arena, and research task {research['task']} answered that it is "
                      f"durable with {research.get('confidence')} confidence."),
        "evergreen": True, "bundle_ready": False, "concept": dict(row.concept or {}),
        "brief": {k: v for k, v in (row.brief or {}).items()
                  if k in ("thumbnail_storyboard", "silhouette_qualifiers")},
        "brief_provenance": {"silhouette_qualifiers": {"rule": QUALIFIER_RULE}},
        "evidence": list(research["refs"]), "pool_entry": row.id,
    }


def admit_ready(db, *, now: datetime, audit=None, unit_cad: float | None = None) -> dict:
    """Attach the highest-priority READY concepts to their arena's answered research task,
    up to the spend allowance. A READY concept with no usable research stays READY and is
    named in the research requests."""
    from . import intake

    allowance = admission_allowance(db, now=now, unit_cad=unit_cad)
    today = now.date()
    admitted, waiting = [], []
    with db.session() as s:
        ready = [(r.id, r.pod) for r in s.scalars(
            select(ConceptPoolEntry).where(ConceptPoolEntry.state == READY)
            .order_by(ConceptPoolEntry.priority.desc(), ConceptPoolEntry.slug))]
    cache: dict = {}
    for rid, pod in ready:
        if pod not in cache:
            cache[pod] = research_for_pod(db, pod, today=today)
        research = cache[pod]
        if research is None:
            waiting.append(rid)
            continue
        if len(admitted) >= allowance["units"]:
            continue
        with db.session() as s:
            row = s.get(ConceptPoolEntry, rid)
            proposal = proposal_from(row, research)
            slug = row.slug
        intake.attach_proposal(db, research["task"], proposal)
        with db.session() as s:
            row = s.get(ConceptPoolEntry, rid)
            row.state, row.admitted_at, row.research_task_id = ADMITTED, now, research["task"]
            row.updated_at = now
        admitted.append(slug)
    if audit is not None:
        if admitted:
            audit(ADMITTED_ACTION, detail={"admitted": admitted, "allowance": allowance})
        ready_left = len(ready) - len(admitted) - len(waiting)
        if ready_left > 0:
            audit(CAPPED_ACTION, detail={"left_ready": ready_left, "allowance": allowance})
    return {"admitted": admitted, "allowance": allowance,
            "waiting_on_research": len(waiting)}


# ---- readback ----------------------------------------------------------------------------


def _engineered(db, slugs: list[str]) -> set[str]:
    from ..core.models import Job

    if not slugs:
        return set()
    keys = [f"draft:{s}" for s in slugs]
    with db.session() as s:
        got = s.scalars(select(Job.idempotency_key).where(Job.idempotency_key.in_(keys)))
        return {k.split(":", 1)[1] for k in got if k}


def _intake_states(db, slugs: list[str]) -> dict[str, str]:
    from sqlalchemy import inspect

    from . import intake

    out: dict[str, str] = {}
    # Read-only: the readback never creates intake's table.
    if not slugs or not inspect(db.engine).has_table(intake.RadarConcept.__tablename__):
        return out
    with db.session() as s:
        for slug, state in s.execute(select(intake.RadarConcept.slug, intake.RadarConcept.state)
                                     .where(intake.RadarConcept.slug.in_(slugs))
                                     .order_by(intake.RadarConcept.id)):
            out[slug] = state
    return out


def evidence_backed(row) -> bool:
    ev = row.evidence or {}
    return (row.state not in (REFUSED, STALE) and bool(ev.get("refs"))
            and int(ev.get("listings") or 0) >= MIN_SIGNAL_LISTINGS)


def health(db, *, now: datetime | None = None) -> dict:
    """Pool health: per-shop and per-family counts, states, held reasons, research requests,
    and the counts Mission Control shows (evidence-backed, admitted, held, engineered)."""
    from sqlalchemy import inspect

    from ..creative.construction_families import hold_family
    from .opportunity import POOL

    now = _now(now)
    if not inspect(db.engine).has_table(ConceptPoolEntry.__tablename__):
        # Read-only: a pool that has never been generated is UNKNOWN, not empty.
        return {"as_of": now.isoformat(), "counts": None, "generated": False,
                "why": "the concept pool has not been generated yet (radar.concept_pool has "
                       "not run)"}
    with db.session() as s:
        rows = list(s.scalars(select(ConceptPoolEntry).order_by(ConceptPoolEntry.slug)))
        s.expunge_all()
    backed = [r for r in rows if evidence_backed(r)]
    slugs = [r.slug for r in rows]
    engineered = _engineered(db, slugs)
    intake_state = _intake_states(db, slugs)
    by_state = Counter(r.state for r in rows)
    by_family: dict[str, Counter] = defaultdict(Counter)
    by_shop: dict[str, Counter] = defaultdict(Counter)
    held_reasons: Counter = Counter()
    for r in rows:
        by_family[r.family][r.state] += 1
        if r in backed:
            for sh in r.shops or []:
                by_shop[sh]["evidence_backed"] += 1
                if r.state in (READY, ADMITTED):
                    by_shop[sh]["admissible"] += 1
        if r.state == HELD:
            first = str((r.reasons or [""])[0])
            fam = hold_family(first)
            held_reasons[f"construction_unsupported:{fam}" if fam else
                         ("#108 silhouette" if first.startswith("#108") else first[:60])] += 1
    names = _watchlist_keys()
    requests = []
    for pod, rs in sorted(_group(rows, lambda r: r.pod).items()):
        ready = [r for r in rs if r.state == READY]
        if ready:
            requests.append({"pod": pod, "ready_concepts": len(ready),
                             "priority": max(r.priority for r in ready),
                             "priority_shop": any(PRIORITY_SHOP in (r.shops or [])
                                                  for r in ready),
                             "needs": "an answered research task behind a validated "
                                      "watchlist gap in this arena"})
    requests.sort(key=lambda r: (not r["priority_shop"], -r["priority"], r["pod"]))
    counts = {
        "evidence_backed": len(backed),
        "target": TARGET_EVIDENCE_BACKED,
        "target_met": len(backed) >= TARGET_EVIDENCE_BACKED,
        "ready": by_state.get(READY, 0), "admitted": by_state.get(ADMITTED, 0),
        "held": by_state.get(HELD, 0), "refused_clone_or_copy": by_state.get(REFUSED, 0),
        "stale": by_state.get(STALE, 0),
        "intake_approved": sum(1 for v in intake_state.values() if v == "approved"),
        "engineered": len(engineered),
        "section_33_pool": len(POOL),
    }
    return {
        "as_of": now.isoformat(), "counts": counts,
        "by_family": {k: dict(v) for k, v in sorted(by_family.items())},
        "by_shop": {names.get(k, k): dict(v) for k, v in sorted(by_shop.items())},
        "shops_without_signal": sorted(n for k, n in names.items() if k not in by_shop),
        "held_reasons": dict(held_reasons.most_common()),
        "research_requests": requests,
        "engineered": sorted(engineered),
        "cadence": {"job_type": JOB_TYPE, "spend_cad_per_run": 0.0,
                    "admission_bound": "admission_allowance (per run, monthly ceiling less "
                                       "spend and reservations, pool share)"},
    }


def _group(rows, key):
    out: dict = defaultdict(list)
    for r in rows:
        out[key(r)].append(r)
    return out
