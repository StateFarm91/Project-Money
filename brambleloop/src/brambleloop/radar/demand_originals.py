"""ENG-DEMAND-SUPPLY: original concepts from the top demand clusters, automatically.

The owner's instruction: "production agents should be automatically making things that
sell." The concept pool held flat décor and seasonal pieces because those were the shapes the
first engines could make. This module proposes ORIGINAL concepts (new animals and
characters, loveys, cushions, garments) in the owner's core families
(D-OWNER-CORE-FAMILIES) and clothing, ordered by the stored-evidence demand score
(`products.demand`). It runs at the start of every `radar.concept_intake` pass.

How a concept gets in. Nothing is approved here:

* **Evidence.** One research task per core family carries the family's demand reading as a
  dated internal source (benchmark_listings, serp_snapshots, the owner's teardown records) and
  a fact finding whose confidence follows the reading (MEASURED -> high, PARTIAL -> medium,
  UNKNOWN -> low). A family nobody observed therefore produces low-quality evidence, and
  intake refuses its concepts below its quality floor. Demand is never invented.
* **Originality.** Every title is ours: a house descriptor plus the subject. Before it is
  attached, a title that equals or overlaps an observed competitor title
  (`ideation.originality_reasons`) or an existing concept is dropped. Intake then runs its own
  dedupe, novelty-floor, anti-copy and children's checks, exactly as for any concept. No
  competitor title, character, wording or design is read into a proposal.
* **Engines.** A concept a certified engine builds is approved and goes to `radar.score` ->
  supply. A concept whose engine does not exist yet (a capybara, a lamb lovey, a frog-face
  cushion) is refused at intake with `construction_unsupported:<family>`, which is exactly the
  engine-demand record Mission Control ranks. The research trigger carries a digest of the
  engine table, so when an engine certifies the next pass re-proposes on fresh evidence and
  the concept is judged again, now buildable.

Deterministic, no model call, no network, CA$0.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone

from ..products import demand as D

TRIGGER_PREFIX = "demand_originals:"
DECISION_REF = "radar.concept_intake:demand_originals"
DOMAIN = "competitor_positioning"
PROPOSED = "demand.originals_proposed"
SKIPPED = "demand.originals_skipped"
# At most this many new originals are attached per pass, so research proposals keep intake
# slots (intake evaluates MAX_EVALUATIONS_PER_RUN per pass, highest demand first).
MAX_PER_RUN = 6
# A family is proposed for only when the market scans themselves observed it: the owner's
# teardown facts sharpen a reading, they never start one.
SCAN_SOURCES = frozenset({"benchmark_listings", "serp_snapshots"})


@dataclass(frozen=True)
class Original:
    slug: str
    title: str
    category: str
    family: str                 # products.demand core family
    form: str                   # creative.concept FORMS
    construction: str           # creative.concept CONSTRUCTIONS
    motif: str
    palette: str
    recipient: str
    occasion: str
    feeling: str
    function: str
    premise: str
    price_cad: float
    hours: tuple[float, float]
    design_hours: float = 10.0


def _toy(slug, title, motif, palette, premise, recipient, occasion, function, *,
         feeling="playful", ball=False, price=6.5, hours=(3.0, 6.0)):
    # A ball-body toy IS a sphere worked in the round; a shaped animal is a toy whose pieces
    # are shaped and joined. Declaring what each physically is keeps them apart honestly.
    form, construction = ("sphere", "in_the_round") if ball else ("toy", "amigurumi_shaping")
    return Original(slug, title, "amigurumi", D.AMIGURUMI, form, construction, motif, palette,
                    recipient, occasion, feeling, function, premise, price, hours)


def _lovey(slug, title, motif, palette, premise, recipient, occasion, function):
    return Original(slug, title, "baby", D.BABY, "toy", "amigurumi_shaping", motif, palette,
                    recipient, occasion, "tender", function, premise, 6.0, (3.0, 6.0))


def _cushion(slug, title, motif, palette, premise, recipient, occasion, function):
    return Original(slug, title, "pillow", D.PILLOW, "pillow", "flat_rows", motif, palette,
                    recipient, occasion, "cosy", function, premise, 7.0, (4.0, 8.0))


def _garment(slug, title, category, construction, recipient, occasion, function, premise, *,
             motif="stone", price=9.0):
    return Original(slug, title, category, D.GARMENT, "fitted_garment", construction, motif,
                    "oat", recipient, occasion, "serene", function, premise, price,
                    (10.0, 20.0), 14.0)


def _wearable(slug, title, category, form, construction, recipient, occasion, function,
              premise, *, motif="stone", palette="oat", price=7.5, family=None):
    """CLOTHING-E2E: a graded wearable (hat, romper, dress, tee, sock...) the ENG-GARMENT-2
    engines build (`products.wearables`). Its demand family is the one `products.demand`
    classifies its own title into, so the reading it is proposed on is the one it is ranked
    on. Baby wear is drafted on the baby table only when the recipient sizes it as baby
    (`new_parent`); the router checks the title and category say the same."""
    fam = family or D.classify(title, category=category).family
    return Original(slug, title, category, fam, form, construction, motif, palette,
                    recipient, occasion, "tender" if recipient == "new_parent" else "serene",
                    function, premise, price, (6.0, 14.0), 12.0)


# House-original designs. Titles are a house descriptor plus the subject; none is taken from
# an observed listing (checked at run time against every stored title, not trusted here).
# Each carries its own buyer (recipient, occasion, function): the novelty floor reads those,
# and two toys for the same buyer and moment would be the same idea in a new animal.
CATALOGUE: tuple[Original, ...] = (
    # -- amigurumi the certified ball-body engine builds today
    _toy("cosy-round-bear-amigurumi", "Cosy Round Bear Amigurumi", "plain round bear",
         "honey and cream", "A plain ball-body bear worked in one honey colour with an "
         "embroidered face and sewn round ears", "child", "birthday",
         "a first birthday keepsake to cuddle", ball=True),
    _toy("classic-ball-bunny-amigurumi", "Classic Ball Bunny Amigurumi", "plain round bunny",
         "oat and blush", "A plain ball-body bunny in oat yarn with long sewn ears, made "
         "to tuck into a spring basket", "grandparent", "easter",
         "an Easter basket companion", ball=True, feeling="tender"),
    _toy("simple-round-teddy-bear", "Simple Round Teddy Bear", "plain round teddy",
         "cocoa and cream", "A cocoa teddy ball as a first stuffed project for a maker "
         "learning spiral rounds", "self", "everyday",
         "a first stuffed project for learning spiral rounds", ball=True,
         feeling="nostalgic"),
    # -- new animals: the shapes the plush engine is being extended to build (engine demand)
    _toy("low-sew-puddle-frog-amigurumi", "Low-Sew Puddle Frog Amigurumi", "pond frog",
         "moss and cream", "A chunky low-sew frog with limbs worked into the body rounds, "
         "ready for puddle games", "child", "spring_refresh",
         "a rainy-day companion for puddle play"),
    _toy("riverbank-capybara-amigurumi", "Riverbank Capybara Amigurumi", "riverbank capybara",
         "toffee and bark", "An original calm capybara with tiny ears, joined legs and a "
         "sleepy embroidered smile", "friend_who_has_everything", "everyday",
         "a calm desk companion", feeling="serene"),
    _toy("low-sew-pond-axolotl-amigurumi", "Low-Sew Pond Axolotl Amigurumi", "pond axolotl",
         "petal pink and coral", "A low-sew axolotl with frilled gills worked into the head "
         "and a wide grin", "teen", "birthday", "a quirky shelf friend",
         feeling="whimsical"),
    _toy("chunky-marsh-duckling-plush", "Chunky Marsh Duckling Plush", "marsh duckling",
         "butter and marigold", "A duckling with a joined bill and wings worked into its "
         "body for a grandchild", "grandparent", "spring_refresh",
         "a spring gift for a grandchild"),
    _toy("low-sew-meadow-lamb-amigurumi", "Low-Sew Meadow Lamb Amigurumi", "meadow lamb",
         "cream and charcoal", "A meadow lamb with legs worked into the body and a "
         "stitched face for an Easter nursery shelf", "new_parent", "easter",
         "a nursery shelf toy", feeling="tender"),
    _toy("chunky-harbour-whale-plush", "Chunky Harbour Whale Plush", "harbour whale",
         "slate and sea glass", "A harbour whale in one closed body with a joined tail, "
         "sized to pack for a trip", "student", "summer_travel",
         "a travel companion for long journeys", feeling="serene"),
    _toy("low-sew-hedgerow-hedgehog-amigurumi", "Low-Sew Hedgerow Hedgehog Amigurumi",
         "hedgerow hedgehog", "acorn and cream", "A hedgehog with a textured back panel "
         "worked in and a stitched nose for an autumn mantel", "self", "winter_nesting",
         "a cosy autumn mantel friend", feeling="cosy"),
    _toy("chunky-riverstone-otter-plush", "Chunky Riverstone Otter Plush", "riverstone otter",
         "walnut and oat", "An otter with joined paws holding a little stone, a gift "
         "between sweethearts", "partner", "valentines", "a hand-holding sweetheart gift",
         feeling="romantic"),
    _toy("low-sew-clover-cow-amigurumi", "Low-Sew Clover Cow Amigurumi", "clover cow",
         "cream and cocoa", "A clover cow with colourwork patches and joined legs to "
         "watch over a farmhouse kitchen", "host", "housewarming",
         "a farmhouse kitchen mascot", feeling="folkloric"),
    _toy("chunky-tidepool-octopus-plush", "Chunky Tidepool Octopus Plush", "tidepool octopus",
         "coral and sand", "An octopus whose eight short legs grow from the body rounds, "
         "a classroom reading friend", "teacher", "graduation",
         "a classroom reading-corner mascot", feeling="whimsical"),
    _toy("low-sew-fernback-dinosaur-amigurumi", "Low-Sew Fernback Dinosaur Amigurumi",
         "fernback dinosaur", "fern and moss", "A fernback dinosaur with spikes worked "
         "into the back, a stocking surprise", "colleague", "christmas",
         "a holiday stocking surprise", feeling="bold"),
    # -- baby
    _lovey("cosy-bunny-lovey", "Cosy Bunny Lovey", "plain bunny head", "oat and cream",
           "A plain bunny head sewn to the centre of a soft square, embroidered face",
           "new_parent", "new_baby", "a soft square for naps"),
    _lovey("classic-bear-lovey", "Classic Bear Lovey", "plain bear head", "honey and cream",
           "A honey bear head on a comfort square for a first birthday", "grandparent",
           "birthday", "a first-birthday comfort square"),
    _lovey("sleepy-lamb-lovey", "Sleepy Lamb Lovey", "sleepy lamb head", "cream and dove",
           "A sleepy lamb head with closed stitched eyes, a gift that packs flat",
           "colleague", "easter", "a baby-shower gift that packs flat"),
    _lovey("little-fox-lovey", "Little Fox Lovey", "little fox head", "rust and cream",
           "A little fox head on a woodland square for a baby's first winter",
           "friend_who_has_everything", "christmas", "a baby's first Christmas gift"),
    # -- pillows and cushions
    _cushion("stoneware-envelope-cushion-cover", "Stoneware Envelope Cushion Cover",
             "stoneware rows", "stoneware grey", "A plain envelope cushion cover worked in "
             "stoneware grey rows with an overlapping back", "self", "spring_refresh",
             "fronts a sofa cushion for a quick room refresh"),
    _cushion("clay-lumbar-envelope-cushion-cover", "Clay Lumbar Envelope Cushion Cover",
             "clay rows", "terracotta clay", "A long lumbar cover in clay rows to dress a "
             "reading chair in a first home", "newlyweds", "housewarming",
             "dresses a reading chair"),
    _cushion("sleepy-frog-face-cushion", "Sleepy Frog Face Cushion", "sleepy frog face",
             "moss and cream", "A cushion front with an original sleepy frog face appliqué "
             "for a playroom floor", "child", "birthday", "a playroom floor cushion friend"),
    _cushion("dozy-bear-face-cushion", "Dozy Bear Face Cushion", "dozy bear face",
             "honey and cocoa", "A cushion front with an original dozy bear face appliqué "
             "for a dorm bed", "teen", "back_to_school", "a dorm bed cushion"),
    # -- garments (clothing)
    _garment("hearthstone-raglan-cardigan", "Hearthstone Raglan Cardigan", "cardigan",
             "top_down_yoke", "self", "winter_nesting", "a layer for cold evenings by the fire",
             "A relaxed raglan cardigan with a buttoned band to pull on for a cold evening "
             "by the fire"),
    _garment("pebble-path-baby-cardigan", "Pebble Path Baby Cardigan", "baby",
             "top_down_yoke", "new_parent", "new_baby", "a first layer for a newborn's walks",
             "A relaxed baby cardigan whose fronts meet edge to edge, nothing to fasten, for "
             "a first walk outside", motif="pebble", price=7.5),
    _garment("kite-day-kids-sweater", "Kite Day Kids Sweater", "sweater", "flat_rows",
             "child", "back_to_school", "a school-morning layer",
             "A relaxed kids sweater in one piece with built-in sleeves, for windy school "
             "mornings", motif="kite", price=8.0),
    _garment("long-weekend-sweater", "Long Weekend Sweater", "sweater", "flat_rows", "partner",
             "everyday", "a slow weekend layer",
             "A relaxed sweater in one piece with built-in sleeves and a slash neck for slow "
             "weekend mornings", motif="weekend"),
    _garment("orchard-side-to-side-vest", "Orchard Side-to-Side Vest", "vest",
             "side_to_side", "self", "spring_refresh", "a spring layer over a shirt",
             "A relaxed vest worked side to side for layering over a shirt in spring",
             motif="orchard"),
    _garment("fireside-drop-shoulder-pullover", "Fireside Drop-Shoulder Pullover", "sweater",
             "bottom_up", "grandparent", "christmas", "a holiday gift layer",
             "A relaxed drop-shoulder pullover knitted up as a holiday gift for a "
             "grandparent", motif="ember"),
    # -- graded wearables (ENG-GARMENT-2 engines): baby wear first, then clothing
    _wearable("thistledown-baby-beanie", "Thistledown Baby Beanie", "hat", "hat",
              "in_the_round", "new_parent", "new_baby", "a soft first hat for pram walks",
              "A soft cotton baby beanie with a turned rib brim and nothing sewn on, for a "
              "newborn's first walks in the pram", motif="thistledown"),
    _wearable("hayloft-baby-romper", "Hayloft Baby Romper", "baby", "fitted_garment",
              "bottom_up", "new_parent", "new_baby", "a pull-on layer for warm days",
              "A sleeveless pull-on baby romper in soft cotton with nothing to fasten, for "
              "warm summer days", motif="hayloft", price=8.0),
    _wearable("seedling-baby-dress", "Seedling Baby Dress", "baby", "fitted_garment",
              "bottom_up", "new_parent", "birthday", "a first birthday outfit",
              "A soft A-line baby dress in cotton that pulls on with nothing to fasten, for a "
              "first birthday party", motif="seedling", price=8.0),
    _wearable("fernleaf-baby-v-neck-cardigan", "Fernleaf Baby V-Neck Cardigan", "baby",
              "fitted_garment", "top_down_yoke", "new_parent", "winter_nesting",
              "a first-winter layer", "A soft open-front V-neck baby cardigan with nothing "
              "to fasten, for a baby's first winter", motif="fernleaf", price=8.5),
    _wearable("larchwood-kids-beanie", "Larchwood Kids Beanie", "hat", "hat", "in_the_round",
              "child", "back_to_school", "keeps ears warm at the bus stop",
              "A warm kids beanie with a turned rib brim for frosty mornings at the bus stop",
              motif="larchwood", price=6.0),
    _wearable("shoreline-boxy-tee", "Shoreline Boxy Tee", "top", "fitted_garment",
              "flat_rows", "self", "everyday", "a light layer for a seaside trip",
              "A boxy cotton tee with short sleeves to pack for a seaside trip",
              motif="shoreline", price=9.0),
    _wearable("tidemark-kids-tank", "Tidemark Kids Tank", "top", "fitted_garment",
              "flat_rows", "child", "birthday", "a summer birthday outfit",
              "A boxy cotton kids tank for a summer birthday in the garden", motif="tidemark",
              price=7.0),
    _wearable("woodsmoke-socks", "Woodsmoke Socks", "sock", "fitted_garment", "in_the_round",
              "friend_who_has_everything", "everyday", "warm feet on cold floors",
              "Soft merino socks with a ribbed cuff for slow mornings on cold floors",
              motif="woodsmoke", price=7.0),
)
assert len({o.slug for o in CATALOGUE}) == len(CATALOGUE)


def engine_signature() -> str:
    """A digest of every family's engine status: it changes when an engine certifies."""
    from ..creative.construction_families import FAMILIES

    body = sorted((k, f.status) for k, f in FAMILIES.items())
    return hashlib.sha256(json.dumps(body).encode()).hexdigest()[:10]


_CONFIDENCE = {D.MEASURED: "high", D.PARTIAL: "medium", D.UNKNOWN: "low"}


def _pod(o: Original) -> str:
    from ..intel import pods

    if o.family == D.GARMENT:
        return "garments"
    if o.family == D.AMIGURUMI:
        return "amigurumi"
    p = pods.route(o.title)
    return p if p in pods.POD_KEYS and p != pods.UNCLASSIFIED else "home_decor"


def ranked(ix: D.DemandIndex) -> list[tuple[Original, dict]]:
    """The catalogue with each original's demand reading, highest first (stable on slug)."""
    out = [(o, ix.score(o.title, category=o.category)) for o in CATALOGUE]
    return sorted(out, key=lambda t: (-t[1]["score"], t[0].slug))


def _task_for(db, family: str, reading: dict, sig: str, *, today: date) -> tuple[int, dict]:
    """The answered research task carrying this family's demand reading as evidence."""
    from ..intel import research

    trigger = f"{TRIGGER_PREFIX}{family}:{sig}"
    t = research.open_question(
        db, question=(f"Which original {family.replace('_', ' ')} designs does the observed "
                      f"market buy most, by stored demand evidence?"),
        trigger=trigger, decision_ref=DECISION_REF, domain=DOMAIN,
        query_terms=[family], evidence_needed=("stored benchmark listings, SERP snapshots and "
                                               "owner teardown records for the family"),
        stop_condition="the family's stored demand reading is recorded",
        if_unresolved="record the reading as UNKNOWN; no concept rests on it")
    tid = int(t["task"])
    with db.session() as s:
        row = s.get(research.ResearchTask, tid)
        state, refs = row.state, dict((row.detail or {}).get("demand_refs") or {})
    if state == research.ANSWERED and refs:
        return tid, refs
    conf = _CONFIDENCE[reading["status"]]
    src = research.add_source(
        db, tid, source="stored demand evidence (products.demand)",
        citation=(f"db:benchmark_listings+serp_snapshots+teardowns?family={family}"
                  f"&as_of={reading['as_of'][:10]}&readings={reading['observations']}"),
        retrieval="internal", read_on=today)
    sref = f"S{src}"
    fref = research.add_finding(
        db, tid, claim_class="fact", rests_on=[sref], confidence=conf,
        statement=(f"family {family}: demand score {reading['score']} ({reading['status']}, "
                   f"confidence {reading['confidence']}) from {reading['observations']} "
                   f"stored reading(s) across {len(reading.get('shops') or [])} source(s); "
                   f"core-family boost {reading['boost']}"))
    research.answer(
        db, tid, outcome=f"{family}: demand {reading['score']} ({reading['status']})",
        confidence=conf,
        effect={"kind": "constraint_established",
                "statement": f"the {family} family's stored demand reading is recorded"},
        conclusion={"alternatives": [], "constraints": [
            f"demand score {reading['score']} at confidence {reading['confidence']}"],
            "unresolved": [] if reading["status"] != D.UNKNOWN else
            ["no stored reading measures this family yet"], "next_test": {},
            "applicability": {"family": family}})
    refs = {"finding": fref, "source": sref}
    from sqlalchemy.orm.attributes import flag_modified

    with db.session() as s:
        row = s.get(research.ResearchTask, tid)
        d = dict(row.detail or {})
        d["demand_refs"] = refs
        row.detail = d
        flag_modified(row, "detail")
    return tid, refs


def _taken(db) -> set[str]:
    from .ideation import _taken_titles

    return _taken_titles(db)


def proposal_for(o: Original, reading: dict, refs: dict) -> dict:
    return {
        "slug": o.slug, "title": o.title, "category": o.category, "price_cad": o.price_cad,
        "maker_hours": list(o.hours), "design_hours": o.design_hours, "evergreen": True,
        "rationale": (f"Demand cluster {reading['cluster']} scores {reading['score']} "
                      f"({reading['status']}, confidence {reading['confidence']}) from stored "
                      f"market readings, in the owner's core family {o.family}; this is an "
                      f"original house design that no observed listing names"),
        "concept": {"premise": o.premise, "pod": _pod(o), "form": o.form,
                    "construction": o.construction, "motif": o.motif,
                    "palette_story": o.palette, "recipient": o.recipient,
                    "occasion": o.occasion, "feeling": o.feeling, "function": o.function},
        "brief": {"thumbnail_storyboard": f"{o.title.lower()} in {o.palette} on a linen ground",
                  "silhouette_qualifiers": ["motif_composition"]},
        "evidence": [refs["finding"], refs["source"]],
    }


def run(db, *, audit, today: date | None = None, ix: D.DemandIndex | None = None) -> dict:
    """Attach every original not yet proposed to its family's evidence task, highest demand
    first. Idempotent: a proposal already attached under the same engine signature is not
    re-attached (intake's fingerprint would skip it anyway)."""
    from .ideation import observed_titles, originality_reasons
    from .intake import _norm, attach_proposal

    today = today or datetime.now(timezone.utc).date()
    ix = ix or D.index(db)
    sig = engine_signature()
    titles = observed_titles(db)
    taken = _taken(db)
    tasks: dict[str, tuple[int, dict]] = {}
    proposed, skipped = [], []
    scanned = {f["family"] for f in ix.families() if SCAN_SOURCES & set(f.get("sources") or ())}
    for o, reading in ranked(ix):
        if len(proposed) >= MAX_PER_RUN:
            break
        if o.family not in scanned:
            skipped.append({"slug": o.slug, "why": [f"no scanned market reading for family "
                                                     f"{o.family} yet (UNKNOWN)"]})
            continue
        why = originality_reasons(o.title, o.title.rsplit(" ", 1)[0], titles)
        if why:
            skipped.append({"slug": o.slug, "why": why[:2]})
            continue
        if o.family not in tasks:
            fam = next((f for f in ix.families() if f["family"] == o.family), None) or \
                {**D._score(None, o.family, 2), "family": o.family}
            fam = {**fam, "as_of": ix.as_of.isoformat(),
                   "cluster": f"{o.family}/*/*"}
            tasks[o.family] = _task_for(db, o.family, fam, sig, today=today)
        tid, refs = tasks[o.family]
        from ..intel import research

        with db.session() as s:
            have = {p.get("slug") for p in ((s.get(research.ResearchTask, tid).detail or {})
                                            .get("concept_proposals") or [])}
        if o.slug in have:
            continue
        if _norm(o.title) in taken:
            # Already a concept (approved, or the static pool): never proposed twice.
            skipped.append({"slug": o.slug, "why": ["already a POOL or approved concept"]})
            continue
        attach_proposal(db, tid, proposal_for(o, reading, refs))
        proposed.append({"slug": o.slug, "family": o.family, "demand": reading["score"],
                         "cluster": reading["cluster"], "task": tid})
    if proposed:
        audit(PROPOSED, detail={"proposed": proposed, "engine_signature": sig})
    if skipped:
        audit(SKIPPED, detail={"skipped": skipped[:40]})
    return {"proposed": proposed, "skipped": skipped, "engine_signature": sig,
            "catalogue": len(CATALOGUE)}
