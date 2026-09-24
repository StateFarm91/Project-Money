"""The children's audience: what it is, what it forbids, and what a pattern must say.

Research: `research/CHILDRENS_CATEGORY.md`, 2026-09-24.

Children's is not a pod. The pods in `pods.py` are **forms** -- a blanket, a soft toy, a
cardigan -- and a children's pod would fight the blankets pod for a baby blanket with neither
of them clearly winning. Children's is the other axis: the **recipient**. A baby blanket is a
blanket for an infant, a lovey is a soft toy for an infant, a toddler cardigan is a garment for
a toddler, and the thing they share is not construction. It is obligation.

That is the whole reason this module exists separately. Every constraint below attaches to the
*audience*, not to the form, so no form-based router can carry them, and a company that files
children's products under their forms will apply a blanket's rules to an object a nine-month-old
will put in its mouth.

Four commitments, each of which is a decision that could have gone the other way.

**A constraint names a source, and the source says how it was obtained.** `Source.retrieval`
distinguishes a page this build actually fetched from a policy quoted out of a search summary,
because `etsy.com` returns 403 to this environment and the Etsy prohibitions below are therefore
second-hand. That is a real weakness in evidence about products we refuse to publish, and it is
recorded as a field rather than as a sentence somebody might not read. `unfetched_sources()`
enumerates it; a test asserts the enumeration is not empty while the gap is open, so closing it
is visible too.

**A refusal is a refusal, not a warning.** Under three, a detachable applied part is not a
labelling problem that a sentence at the bottom of page one solves. `assess` returns
`REFUSE`, `publishable()` returns False, and there is no severity downgrade anywhere in this
module.

**An unrecognised applied part refuses.** The alternative -- treat what we do not recognise as
safe -- is the single most comfortable wrong answer available here, and it is wrong in exactly
the direction that hurts a child. `pods.py` files an unroutable listing under `unclassified`
for the same reason: a gap has to be visible, and the way to make this one visible is to make
it block.

**No demand number lives here.** Not one score, price or volume for a children's sub-category.
Those belong in `radar/opportunity.py`, they need evidence this department does not have, and an
invented 0.8 sitting beside a cited regulation makes the regulation look invented too. A test
asserts the absence.

None of this is legal advice, and the patterns it governs say so. It is this company's
conservative reading of public safety guidance, dated, with its sources attached so the reading
can be re-checked rather than argued about.
"""
from __future__ import annotations

from dataclasses import dataclass, fields

from .pods import POD_KEYS, signals

# The day this reading was compiled. A safety constraint with no date silently becomes a claim
# about the past -- the same failure `gates/platform_policy.py` is built around -- and the
# moment it matters is a listing that was compliant when it was written.
SNAPSHOT_DATE = "2026-09-24"


# ---- sources ---------------------------------------------------------------

# How a source reached us. The distinction is not pedantry: `search_summary` means nobody in
# this build has read the page, only a description of it, and three of the prohibitions below
# rest on that.
FETCHED = "fetched"                  # this build retrieved the page and read it
SEARCH_SUMMARY = "search_summary"    # quoted from a search result; the page itself refused us
REPOSITORY = "repository"            # already established and recorded in this repository

RETRIEVALS: dict[str, str] = {
    FETCHED: "retrieved and read by this build",
    SEARCH_SUMMARY: "quoted from a search result; the page itself was not retrievable",
    REPOSITORY: "already established in this repository, with its own provenance",
}


@dataclass(frozen=True)
class Source:
    """One piece of public guidance, with how and when we came by it."""

    key: str
    title: str
    url: str
    jurisdiction: str          # "US", "CA", "EU", "platform", "clinical", "industry"
    retrieval: str
    read_on: str = SNAPSHOT_DATE


SOURCES: dict[str, Source] = {s.key: s for s in (
    Source("cpsc_childrens_product",
           "CPSC: what is a children's product (definition, CPC, testing, tracking labels)",
           "https://www.cpsc.gov/Business--Manufacturing/Business-Education/childrens-products",
           "US", FETCHED),
    Source("cpsc_small_parts",
           "CPSC: small parts ban and choking hazard labeling (16 CFR 1501, 1500.19)",
           "https://www.cpsc.gov/Business--Manufacturing/Business-Education/"
           "Business-Guidance/Small-Parts-for-Toys-and-Childrens-Products",
           "US", FETCHED),
    Source("cfr_1500_19",
           "16 CFR 1500.19: misbranded toys and other articles intended for use by children",
           "https://www.law.cornell.edu/cfr/text/16/1500.19",
           "US", FETCHED),
    Source("cpsc_astm_f963",
           "CPSC: ASTM F963 requirements chart (4.3.7 stuffing, 4.27 stuffed toys, 4.14 cords)",
           "https://www.cpsc.gov/Business--Manufacturing/Business-Education/"
           "Toy-Safety/ASTM-F-963-Chart",
           "US", FETCHED),
    Source("cfr_1120_drawstrings",
           "Substantial product hazard list: children's upper outerwear with drawstrings",
           "https://www.federalregister.gov/documents/2011/07/19/2011-17961/"
           "substantial-product-hazard-list-childrens-upper-outerwear-in-sizes-2t-to-12-"
           "with-neck-or-hood",
           "US", FETCHED),
    Source("cpsc_slings",
           "CPSC: sling carriers business guidance (16 CFR 1228, ASTM F2907-22)",
           "https://www.cpsc.gov/business--manufacturing/business-education/"
           "business-guidance/sling-carriers",
           "US", SEARCH_SUMMARY),
    Source("cpsc_crib_mobiles",
           "CPSC: strangulation risk from crib toys and mobiles; remove at 5 months or "
           "when the child can push up on hands and knees",
           "https://www.cpsc.gov/Newsroom/News-Releases/1989/"
           "Strangulation-Risk-Prompts-Warning-About-Crib-Kickers",
           "US", SEARCH_SUMMARY),
    Source("canada_toys_regulations",
           "Toys Regulations SOR/2011-17 (s.7 small parts, s.28 fastenings, s.29 stuffing, "
           "s.30 inserts, s.31 eyes and noses)",
           "https://laws-lois.justice.gc.ca/eng/regulations/SOR-2011-17/FullText.html",
           "CA", FETCHED),
    Source("canada_sleepwear",
           "Children's Sleepwear Regulations SOR/2016-169 (loose-fitting sleepwear, "
           "flammability, sizes to 14X)",
           "https://laws-lois.justice.gc.ca/eng/regulations/SOR-2016-169/FullText.html",
           "CA", SEARCH_SUMMARY),
    Source("health_canada_drawstrings",
           "Health Canada: remove cords and drawstrings from children's hoods, hats and "
           "jackets; CCPSA ss.7(a), 8(a)",
           "https://www.canada.ca/en/health-canada/services/consumer-product-safety/"
           "reports-publications/consumer-education/your-child-safe/is-your-child-safe.html",
           "CA", SEARCH_SUMMARY),
    Source("aap_safe_sleep",
           "AAP 2022: keep soft objects and loose bedding out of the infant sleep area "
           "(under 12 months)",
           "https://publications.aap.org/pediatrics/article/150/1/e2022057991/188305/"
           "Evidence-Base-for-2022-Updated-Recommendations-for",
           "clinical", SEARCH_SUMMARY),
    Source("etsy_children_policy",
           "Etsy Children and Baby Products policy, updated effective 2026-06-02; prohibits "
           "patterns, designs and instructions for making prohibited children and baby items",
           "https://www.etsy.com/legal/policy/children-and-baby-products-policy/239344787532",
           "platform", SEARCH_SUMMARY),
    Source("cyc_baby_sizes",
           "Craft Yarn Council: baby size chart",
           "https://www.craftyarncouncil.com/standards/baby-size-chart",
           "industry", FETCHED),
    Source("cyc_child_sizes",
           "Craft Yarn Council: child and youth size charts",
           "https://www.craftyarncouncil.com/standards/child-youth-sizes",
           "industry", FETCHED),
)}


def unfetched_sources() -> tuple[str, ...]:
    """Which constraints rest on a page nobody in this build has actually read.

    Measures: the count of sources whose retrieval is not `FETCHED`.
    Why: `etsy.com` returns HTTP 403 to this environment, so the platform prohibitions -- the
    strictest rules in this module -- are quoted from search summaries. A reader is entitled to
    know which refusals are backed by a page we read and which by a description of one, and a
    caveat in a docstring is not that. This is the list to shorten.
    """
    return tuple(sorted(k for k, s in SOURCES.items() if s.retrieval != FETCHED))


# ---- age bands -------------------------------------------------------------

# The regulatory line is 36 months and it is not a rounding of "toddler". Below it a small part
# is banned outright; at and above it the same part is permitted with a warning. Encoding the
# bands as months rather than as words keeps the boundary arithmetic rather than editorial.
UNDER_3 = "under_3"
THREE_TO_SIX = "three_to_six"
SIX_TO_TWELVE = "six_to_twelve"
OVER_TWELVE = "over_twelve"


@dataclass(frozen=True)
class AgeBand:
    key: str
    label: str
    from_months: int
    to_months: int | None      # exclusive; None means no upper bound
    why_the_boundary: str


AGE_BANDS: dict[str, AgeBand] = {b.key: b for b in (
    AgeBand(UNDER_3, "under 3 years", 0, 36,
            "16 CFR 1501 bans small parts outright below 36 months; SOR/2011-17 s.7(1) is the "
            "Canadian equivalent. Nothing here is satisfiable by a warning label."),
    AgeBand(THREE_TO_SIX, "3 to under 6 years", 36, 72,
            "16 CFR 1500.19 requires the choking cautionary statement on a toy or game with a "
            "small part in this band. The part is permitted; the silence is not."),
    AgeBand(SIX_TO_TWELVE, "6 to 12 years", 72, 156,
            "Still a children's product under CPSC's definition (12 and under), so the "
            "manufacturer obligations follow the finished object even where small parts do not."),
    AgeBand(OVER_TWELVE, "over 12 years", 156, None,
            "Outside CPSC's children's-product definition. Named so that 'not a children's "
            "product' is a stated band rather than an omission."),
)}


def age_band_for_months(months: int) -> str:
    """Which band an age in months falls in.

    Measures: the band whose half-open interval contains `months`.
    Why: a pattern states an age, and every constraint here keys off the band rather than the
    number. Doing the lookup in one place stops 35 and 36 months being treated alike by
    whichever caller was written in a hurry.
    """
    if months < 0:
        raise ValueError(f"age in months cannot be negative: {months}")
    for band in AGE_BANDS.values():
        if band.from_months <= months and (band.to_months is None or months < band.to_months):
            return band.key
    raise ValueError(f"no band covers {months} months")   # pragma: no cover - bands are total


# ---- severities and constraints --------------------------------------------

REFUSE = "refuse"                       # the product is not published, in any form
REQUIRE_STATEMENT = "require_statement"  # publishable only with a named statement present
NOTE = "note"                           # true, recorded, and not blocking

SEVERITIES: tuple[str, ...] = (REFUSE, REQUIRE_STATEMENT, NOTE)


@dataclass(frozen=True)
class Constraint:
    """One rule, what it measures, why it exists, and where it comes from."""

    key: str
    measures: str
    why: str
    severity: str
    source: str
    jurisdictions: tuple[str, ...]


CONSTRAINTS: dict[str, Constraint] = {c.key: c for c in (
    Constraint(
        "small_parts_under_3",
        "whether a product stated for under 36 months instructs any applied part that could "
        "detach -- safety eyes, plastic noses, buttons, beads, bells, joint discs, pom-poms",
        "16 CFR 1501 bans small parts in products intended for under-threes, and SOR/2011-17 "
        "s.7(1) bans separable parts that enter the small parts cylinder at 4.45 N. A pattern "
        "that instructs one is instructing the maker to build a banned object. There is no "
        "label that fixes this, which is why the severity is refusal.",
        REFUSE, "cpsc_small_parts", ("US", "CA")),
    Constraint(
        "choking_statement_3_to_6",
        "whether a product stated for 3 to under 6 that contains a small part carries the "
        "16 CFR 1500.19 cautionary statement",
        "In this band the part is lawful and the silence is not. The buyer is choosing a gift "
        "for a specific child and the age boundary is the information they need.",
        REQUIRE_STATEMENT, "cfr_1500_19", ("US",)),
    Constraint(
        "face_construction",
        "whether an amigurumi or lovey pattern states how the face is made and offers an "
        "integral method as the default",
        "Safety eyes are the genre's visual signature and they are the part most likely to be "
        "pulled off by the youngest plausible recipient. Embroidered or crocheted-on features "
        "are worked into the fabric and cannot detach, which is why they are the default here "
        "rather than the alternative mentioned at the end.",
        REQUIRE_STATEMENT, "canada_toys_regulations", ("CA", "US")),
    Constraint(
        "neck_or_hood_drawstring",
        "whether a children's upper-outerwear pattern instructs a drawstring or tie at the "
        "hood or neck, in sizes 2T to 12",
        "16 CFR 1120 lists such a garment as a substantial product hazard, and Health Canada "
        "advises removing cords from children's hoods entirely after 16 Canadian incidents "
        "including three deaths. The mechanism is a playground slide, not misuse.",
        REFUSE, "cfr_1120_drawstrings", ("US", "CA")),
    Constraint(
        "waist_or_bottom_tie_length",
        "whether a waist or bottom tie in sizes 2T to 16 extends more than 3 inches outside "
        "its channel at full width, or ends in a toggle or knot",
        "ASTM F1816-97, incorporated by 16 CFR 1120. The hazard is a child dragged by a tie "
        "caught in a vehicle door, so the limit is on the free length rather than on the tie.",
        REFUSE, "cfr_1120_drawstrings", ("US",)),
    Constraint(
        "sleepwear_flammability",
        "whether the product is loose-fitting children's sleepwear in a regulated size",
        "SOR/2016-169 covers nightgowns, nightshirts, dressing gowns, bathrobes, housecoats, "
        "robes and pyjamas to size 14X, with flammability testing after laundering where the "
        "garment is not flame-retardant treated. Untreated crochet fabric is not flame "
        "resistant and a crocheted nightgown is loose-fitting by construction.",
        REFUSE, "canada_sleepwear", ("CA", "US")),
    Constraint(
        "infant_sleep_environment",
        "whether a soft product plausibly taken to a cot -- blanket, lovey, comforter, "
        "cushion -- states that it is for supervised, awake use and not for an unsupervised "
        "sleep space before 12 months",
        "AAP 2022 keeps soft objects and loose bedding out of the infant sleep area. The "
        "commercially awkward part is that the baby blanket is the audience's most merchandised "
        "object; the answer is to say so rather than to leave the buyer to assume.",
        REQUIRE_STATEMENT, "aap_safe_sleep", ("US", "CA")),
    Constraint(
        "mobile_removal",
        "whether a crib mobile pattern states removal at 5 months or when the child can push "
        "up on hands and knees, whichever comes first",
        "CPSC's long-standing crib-toy guidance. The hazard is entanglement in the loops the "
        "hanging cords form once the child can reach them, which is a date in the child's "
        "development rather than a property of the object.",
        REQUIRE_STATEMENT, "cpsc_crib_mobiles", ("US", "CA")),
    Constraint(
        "stuffing_containment",
        "whether a stuffed product states a stitch tension tight enough that stuffing cannot "
        "migrate through the fabric, and that seams and the closing round are secured",
        "ASTM F963 4.27 and SOR/2011-17 s.29 both treat escaping stuffing as the hazard rather "
        "than the stuffing itself. In a crocheted toy the safety property is the workmanship, "
        "so it belongs in the instructions and not in a warning.",
        REQUIRE_STATEMENT, "cpsc_astm_f963", ("US", "CA")),
    Constraint(
        "load_bearing_infant_containment",
        "whether the product carries the weight of an infant -- a sling, a wrap carrier, a "
        "hammock, a swing seat",
        "ASTM F2907-22 is mandatory at 16 CFR 1228 for sling carriers and requires a "
        "Children's Product Certificate. The failure mode of a crocheted sling is a dropped "
        "infant, and no instruction we could write would make it testable by the maker.",
        REFUSE, "cpsc_slings", ("US", "CA")),
    Constraint(
        "platform_prohibited_subject",
        "whether the subject of the pattern is an item whose instructions the marketplace "
        "prohibits, independently of whether we would sell the finished object",
        "Etsy's Children and Baby Products policy, updated effective 2026-06-02, reaches "
        "patterns, designs and instructions -- not only products. A shop can be actioned for a "
        "PDF. This is the constraint most likely to be missed, because it is the only one that "
        "binds a publisher who never touches a physical product.",
        REFUSE, "etsy_children_policy", ("platform",)),
    Constraint(
        "maker_who_sells_becomes_manufacturer",
        "whether the pattern tells a buyer who intends to sell finished items that they take "
        "on the manufacturer's obligations",
        "CPSC's definition attaches to the physical children's product, so the person who "
        "crochets the toy and sells it inherits third-party testing, the Children's Product "
        "Certificate and tracking labels. We are not their lawyer and we do not pretend to be; "
        "we are also not entitled to let them assume none of it exists.",
        REQUIRE_STATEMENT, "cpsc_childrens_product", ("US", "CA")),
)}


def unsourced_constraints() -> tuple[str, ...]:
    """Constraints naming a source that is not in the table.

    Measures: constraint keys whose `source` has no entry in SOURCES.
    Why: a rule whose citation has gone missing is a rule nobody can re-check, and it will
    survive a refactor looking exactly like a rule that can.
    """
    return tuple(sorted(k for k, c in CONSTRAINTS.items() if c.source not in SOURCES))


# ---- what a pattern has to say ---------------------------------------------

# Quoted from search results summarising 16 CFR 1500.19; the regulation renders the statement
# as an image, so the eCFR text does not give the string in prose. Confirm against a rendered
# copy of the rule before it goes on a live listing (research doc section 6, item 4).
CHOKING_WARNING = "WARNING: CHOKING HAZARD - Small parts. Not for children under 3 yrs."

STATEMENTS: dict[str, str] = {
    "age_suitability":
        "the age band the finished item is suitable for, stated as a band, rather than left "
        "to be inferred from the photograph",
    "choking_small_parts":
        "the 16 CFR 1500.19 cautionary statement, where an applied small part exists and the "
        "stated audience is 3 to under 6",
    "face_construction":
        "how the face is made: embroidered or crocheted-on as the default, with safety eyes "
        "named as a variant for 3 and over",
    "safe_sleep":
        "that the finished item is for supervised, awake use and does not belong in an "
        "unsupervised sleep space before 12 months",
    "supervision":
        "that a soft toy is for supervised play, in one sentence, without hedging",
    "construction_integrity":
        "the tension, seam and closing-round guidance that keeps stuffing inside and limbs "
        "attached, in the instructions rather than in a warning",
    "fibre_and_care":
        "fibre content and laundering, because washability is a hygiene property for this "
        "audience rather than a convenience",
    "mobile_removal":
        "that a mobile is removed at 5 months or when the child can push up on hands and "
        "knees, whichever comes first",
    "selling_finished_items":
        "that a buyer who sells finished items becomes the manufacturer, with a pointer to "
        "CPSC (US) and the CCPSA and Toys Regulations (Canada)",
    "not_legal_advice":
        "that this is not legal advice, and the date the safety guidance was compiled",
}


# ---- applied parts ---------------------------------------------------------

# Parts applied to the surface and held there by friction, a washer or a stitch. Every one of
# these can be separated from a crocheted object by a determined toddler.
DETACHABLE_APPLIED_PARTS: frozenset[str] = frozenset((
    "safety_eyes", "plastic_eyes", "glass_eyes", "googly_eyes", "safety_nose", "plastic_nose",
    "buttons", "beads", "bells", "sequins", "joint_discs", "pom_poms", "ribbon_bow",
    "plastic_rattle_insert", "squeaker", "wired_armature", "felt_shapes_glued",
))

# Features worked into the fabric, or sewn through it with yarn. They cannot detach without the
# fabric failing first, which is a different and much slower failure.
INTEGRAL_FEATURES: frozenset[str] = frozenset((
    "embroidered_eyes", "embroidered_nose", "embroidered_mouth", "crocheted_eyes",
    "crocheted_nose", "felt_shapes_sewn", "surface_slip_stitch", "colourwork_face",
))


def classify_part(part: str) -> str:
    """Whether a named part is detachable, integral, or unknown to this module.

    Measures: which of the two closed vocabularies a named part belongs to.
    Why: the third answer has to exist and has to be `unknown` rather than a guess. A part this
    module has never heard of is not safe by default; it is unassessed, and `assess` refuses it
    for that reason.
    """
    if part in DETACHABLE_APPLIED_PARTS:
        return "detachable"
    if part in INTEGRAL_FEATURES:
        return "integral"
    return "unknown"


# ---- subjects we do not publish instructions for ---------------------------

@dataclass(frozen=True)
class ProhibitedSubject:
    """A thing whose *instructions* we refuse to publish, and why."""

    slug: str
    terms: tuple[str, ...]
    why: str
    constraint: str


PROHIBITED_SUBJECTS: tuple[ProhibitedSubject, ...] = (
    ProhibitedSubject(
        "crib_bumper", ("crib bumper", "cot bumper", "crib liner", "cot liner",
                        "crib rail cover", "cot rail cover", "bumper pad"),
        "Banned in the US by the Safe Sleep for Babies Act of 2021 and prohibited on Etsy, "
        "whose policy reaches the pattern as well as the product.",
        "platform_prohibited_subject"),
    ProhibitedSubject(
        "infant_sleep_pillow", ("infant lounger", "baby lounger", "baby nest", "sleep nest",
                                "baby support pillow", "nap cushion", "baby pillow",
                                "newborn pillow", "sleep positioner"),
        "A soft surface an infant is placed on to sleep. Prohibited on Etsy and contrary to "
        "AAP safe-sleep guidance on every count.",
        "platform_prohibited_subject"),
    ProhibitedSubject(
        "inclined_sleeper", ("inclined sleeper", "baby recliner", "sleeper wedge"),
        "Banned in the US by the Safe Sleep for Babies Act of 2021.",
        "platform_prohibited_subject"),
    ProhibitedSubject(
        "infant_neck_float", ("neck float", "neck floatie", "baby neck ring"),
        "Named in Etsy's 2026-06-02 policy update as a prohibited example.",
        "platform_prohibited_subject"),
    ProhibitedSubject(
        "baby_sling", ("baby sling", "baby carrier", "sling carrier", "baby wrap carrier",
                       "ring sling", "baby hammock", "baby swing seat"),
        "Load-bearing infant containment under the mandatory standard at 16 CFR 1228 "
        "(ASTM F2907-22). The failure mode is a dropped infant.",
        "load_bearing_infant_containment"),
    ProhibitedSubject(
        "childrens_sleepwear", ("nightgown", "nightdress", "nightshirt", "dressing gown",
                                "housecoat", "bathrobe", "pyjama", "pajama", "sleep gown",
                                "sleep sack", "sleeping bag for baby"),
        "Loose-fitting children's sleepwear is flammability-regulated to size 14X under "
        "SOR/2016-169, and untreated crochet fabric is not flame resistant.",
        "sleepwear_flammability"),
)


def prohibited_subject(text: str) -> ProhibitedSubject | None:
    """The prohibition a product title or brief trips, if any.

    Measures: whether any prohibited subject's terms appear as whole words in the text.
    Why: matching is on words via `pods.signals`, not on substrings, for the reason that module
    already learned the hard way -- a substring test both misses "crib bumpers" against the
    keyword "crib bumper" and hits things it should not. Reusing the tokeniser keeps one
    definition of what a word is.
    """
    _, phrase = signals(text)          # already space-padded at both ends
    for subject in PROHIBITED_SUBJECTS:
        for term in subject.terms:
            _, needle = signals(term)
            if needle.strip() and needle in phrase:
                return subject
    return None


# ---- the sub-categories ----------------------------------------------------

# What we do with a sub-category. Deliberately five words rather than "yes/no", for the same
# reason BUILD_STATE has five requirement states: "avoid for now" and "never publish" are not
# the same decision and collapsing them loses the one that can change.
LEAD = "lead"            # enter here first
BUILD = "build"          # build it, with its statements
CAREFUL = "careful"      # buildable and slow: needs physical judgement we cannot yet make
AVOID = "avoid"          # not now; the risk is not worth the position
NEVER = "never"          # we do not publish instructions for this at all

VERDICTS: tuple[str, ...] = (LEAD, BUILD, CAREFUL, AVOID, NEVER)


@dataclass(frozen=True)
class Subcategory:
    """A children's sub-category: which form owns it, and what it drags along with it.

    Note what is *not* a field: demand, competition, price, volume. Those are measurements this
    department does not have for the children's audience, and a plausible number beside a cited
    regulation would borrow the regulation's credibility for a guess.
    """

    slug: str
    label: str
    pod: str                        # the form pod in pods.py that owns the object
    audiences: tuple[str, ...]      # age bands a product here is plausibly stated for
    verdict: str
    why: str
    constraints: tuple[str, ...]
    statements: tuple[str, ...]


_BABY_STATEMENTS = ("age_suitability", "fibre_and_care", "selling_finished_items",
                    "not_legal_advice")
_TOY_STATEMENTS = _BABY_STATEMENTS + ("supervision", "construction_integrity",
                                      "face_construction")

SUBCATEGORIES: dict[str, Subcategory] = {s.slug: s for s in (
    Subcategory(
        "nursery_decor", "Nursery decor: wall hangings, buntings, baskets, cushions",
        "home_decor", (UNDER_3, THREE_TO_SIX),
        LEAD,
        "Decorates a room the child does not handle, so almost nothing attaches to it. The "
        "best risk-adjusted entry in the audience, and the price ceiling is the decor ceiling "
        "rather than the toy ceiling.",
        ("infant_sleep_environment",),
        _BABY_STATEMENTS + ("safe_sleep",)),
    Subcategory(
        "keepsake_blanket", "Milestone and keepsake blankets",
        "blankets", (UNDER_3,),
        LEAD,
        "Personalisation is motif placement and text, which is compiler work rather than "
        "physical testing, and the emotional price tolerance is the highest in the audience.",
        ("infant_sleep_environment",),
        _BABY_STATEMENTS + ("safe_sleep",)),
    Subcategory(
        "baby_blanket", "Baby blankets and afghans",
        "blankets", (UNDER_3,),
        BUILD,
        "Class A geometry, no fitted sizing, no applied parts. Carries the safe-sleep statement "
        "because it is the object most likely to end up in a cot.",
        ("infant_sleep_environment",),
        _BABY_STATEMENTS + ("safe_sleep",)),
    Subcategory(
        "baby_wearables", "Baby and child hats, booties and mittens",
        "hats", (UNDER_3, THREE_TO_SIX, SIX_TO_TWELVE),
        BUILD,
        "Head-circumference grading is arithmetic we already do, and sub-four-hour makes "
        "accumulate reviews faster than anything else we can publish.",
        ("small_parts_under_3",),
        _BABY_STATEMENTS),
    Subcategory(
        "lovey", "Lovey, comforter and security blanket",
        "amigurumi", (UNDER_3,),
        BUILD,
        "Small, fast and giftable, and sitting exactly on the safe-sleep line. Publishable only "
        "with the full statement set and an integral face.",
        ("small_parts_under_3", "face_construction", "infant_sleep_environment",
         "stuffing_containment"),
        _TOY_STATEMENTS + ("safe_sleep",)),
    Subcategory(
        "amigurumi_toy", "Amigurumi toys and plushies",
        "amigurumi", (UNDER_3, THREE_TO_SIX, SIX_TO_TWELVE),
        BUILD,
        "The highest-velocity shelf we can see and the most crowded one. Our differentiator is "
        "an integral face by default, which is the opposite of the genre's visual signature and "
        "a cost we are choosing to pay.",
        ("small_parts_under_3", "choking_statement_3_to_6", "face_construction",
         "stuffing_containment"),
        _TOY_STATEMENTS),
    Subcategory(
        "crib_mobile", "Crib mobiles",
        "home_decor", (UNDER_3,),
        CAREFUL,
        "Suspended over a sleeping infant on cords. Publishable with the removal statement and "
        "no detachable parts on the hanging elements.",
        ("small_parts_under_3", "mobile_removal", "stuffing_containment"),
        _BABY_STATEMENTS + ("mobile_removal", "supervision")),
    Subcategory(
        "childrens_garment", "Children's garments: cardigans, dresses, sweaters",
        "garments", (UNDER_3, THREE_TO_SIX, SIX_TO_TWELVE),
        CAREFUL,
        "Class C. The CYC tables make grading arithmetic rather than guesswork, but fit is not "
        "verifiable by compiler, and the drawstring rule bites on anything hooded.",
        ("neck_or_hood_drawstring", "waist_or_bottom_tie_length", "small_parts_under_3"),
        _BABY_STATEMENTS),
    Subcategory(
        "rattle_or_teether", "Rattles and teethers",
        "amigurumi", (UNDER_3,),
        AVOID,
        "A rattle contains a hard insert and a teether is mouthed by definition: the small-parts "
        "case at its most severe, on an object a nine-month-old is meant to chew.",
        ("small_parts_under_3", "stuffing_containment"),
        _TOY_STATEMENTS),
    Subcategory(
        "infant_sleep_accessory", "Infant sleep accessories: bumpers, liners, loungers, pillows",
        "home_decor", (UNDER_3,),
        NEVER,
        "Etsy prohibits the instructions, not only the product, and the US ban is statutory.",
        ("platform_prohibited_subject", "infant_sleep_environment"),
        ()),
    Subcategory(
        "baby_carrier", "Baby carriers, slings and wraps",
        "bags", (UNDER_3,),
        NEVER,
        "Load-bearing infant containment under the mandatory standard at 16 CFR 1228. Nothing "
        "we could write into a pattern would let the maker verify that their fabric holds.",
        ("load_bearing_infant_containment", "platform_prohibited_subject"),
        ()),
    Subcategory(
        "childrens_sleepwear", "Children's loose-fitting sleepwear",
        "garments", (UNDER_3, THREE_TO_SIX, SIX_TO_TWELVE),
        NEVER,
        "Flammability-regulated in both jurisdictions, and untreated crochet fabric is not "
        "flame resistant.",
        ("sleepwear_flammability", "platform_prohibited_subject"),
        ()),
)}


def required_statements(subcategory: str, audience: str) -> tuple[str, ...]:
    """Every statement a pattern in this sub-category, for this audience, must carry.

    Measures: the sub-category's own statement set, plus the choking statement where the
    audience makes it applicable.
    Why: the statement set is the deliverable difference between a children's pattern and any
    other pattern we publish, and it should be computed rather than remembered.
    """
    sub = SUBCATEGORIES.get(subcategory)
    if sub is None:
        raise KeyError(f"unknown children's sub-category: {subcategory!r}")
    if audience not in AGE_BANDS:
        raise KeyError(f"unknown age band: {audience!r}")
    needed = set(sub.statements)
    if audience == THREE_TO_SIX and "choking_statement_3_to_6" in sub.constraints:
        needed.add("choking_small_parts")
    return tuple(sorted(needed))


# ---- assessment ------------------------------------------------------------

@dataclass(frozen=True)
class Concept:
    """A product idea, described in the terms the constraints are written about."""

    subject: str                                   # the working title or one-line brief
    subcategory: str
    audience: str                                  # an age band key
    applied_parts: tuple[str, ...] = ()
    neck_or_hood_drawstring: bool = False
    waist_tie_inches_outside_channel: float | None = None
    tie_ends_in_toggle_or_knot: bool = False
    stated_statements: tuple[str, ...] = ()


@dataclass(frozen=True)
class Finding:
    """One thing the assessment measured, and what it found."""

    code: str
    severity: str
    constraint: str
    measures: str
    detail: str
    source_url: str


def _finding(constraint_key: str, code: str, detail: str,
             severity: str | None = None) -> Finding:
    c = CONSTRAINTS[constraint_key]
    return Finding(code=code, severity=severity or c.severity, constraint=constraint_key,
                   measures=c.measures, detail=detail, source_url=SOURCES[c.source].url)


def assess(concept: Concept) -> list[Finding]:
    """Every constraint this concept trips, worst first.

    Measures: the concept's subject, sub-category, stated audience, applied parts, ties and
    stated statements against CONSTRAINTS.
    Why: the point of the module. These are all decidable before a stitch is designed, and the
    alternative is a person remembering ten rules at listing time, twice a week, for years.
    """
    if concept.audience not in AGE_BANDS:
        raise KeyError(f"unknown age band: {concept.audience!r}")
    out: list[Finding] = []

    sub = SUBCATEGORIES.get(concept.subcategory)
    if sub is None:
        raise KeyError(f"unknown children's sub-category: {concept.subcategory!r}")

    if sub.verdict == NEVER:
        out.append(_finding(sub.constraints[0], "SUBCATEGORY_NOT_PUBLISHED",
                            f"{sub.label}: {sub.why}", REFUSE))

    banned = prohibited_subject(concept.subject)
    if banned is not None:
        out.append(_finding(banned.constraint, "PROHIBITED_SUBJECT",
                            f"{concept.subject!r} reads as {banned.slug}. {banned.why}",
                            REFUSE))

    for part in concept.applied_parts:
        kind = classify_part(part)
        if kind == "unknown":
            out.append(_finding("small_parts_under_3", "UNRECOGNISED_PART",
                                f"{part!r} is in neither vocabulary, so nobody has decided "
                                f"whether it can detach. Unassessed is not safe.", REFUSE))
        elif kind == "detachable" and concept.audience == UNDER_3:
            out.append(_finding("small_parts_under_3", "SMALL_PART_UNDER_3",
                                f"{part!r} is an applied part that can separate, and the stated "
                                f"audience is under 36 months."))
        elif kind == "detachable" and concept.audience == THREE_TO_SIX:
            if "choking_small_parts" not in concept.stated_statements:
                out.append(_finding("choking_statement_3_to_6", "CHOKING_STATEMENT_MISSING",
                                    f"{part!r} is a small part and the audience is 3 to under "
                                    f"6, so the pattern must carry: {CHOKING_WARNING}"))

    if concept.neck_or_hood_drawstring:
        out.append(_finding("neck_or_hood_drawstring", "NECK_OR_HOOD_DRAWSTRING",
                            "the pattern instructs a tie or drawstring at the hood or neck of "
                            "a children's garment."))

    free = concept.waist_tie_inches_outside_channel
    if free is not None and free > 3.0:
        out.append(_finding("waist_or_bottom_tie_length", "TIE_TOO_LONG",
                            f"{free} inches outside the channel at full width; the limit is 3."))
    if concept.tie_ends_in_toggle_or_knot:
        out.append(_finding("waist_or_bottom_tie_length", "TIE_END_ATTACHMENT",
                            "a toggle or knot at the free end of a waist or bottom tie."))

    for statement in required_statements(concept.subcategory, concept.audience):
        if statement not in concept.stated_statements:
            constraint = _statement_constraint(statement, sub)
            out.append(_finding(constraint, "STATEMENT_MISSING",
                                f"the pattern does not state: {STATEMENTS[statement]}",
                                REQUIRE_STATEMENT))

    order = {REFUSE: 0, REQUIRE_STATEMENT: 1, NOTE: 2}
    return sorted(out, key=lambda f: (order[f.severity], f.code, f.detail))


# Which constraint a missing statement is evidence against. Several statements have an obvious
# owner; the rest hang off the manufacturer-obligation constraint, which is the one that says a
# children's pattern has to be written differently at all.
_STATEMENT_OWNER: dict[str, str] = {
    "choking_small_parts": "choking_statement_3_to_6",
    "face_construction": "face_construction",
    "safe_sleep": "infant_sleep_environment",
    "mobile_removal": "mobile_removal",
    "construction_integrity": "stuffing_containment",
    "selling_finished_items": "maker_who_sells_becomes_manufacturer",
}


def _statement_constraint(statement: str, sub: Subcategory) -> str:
    owner = _STATEMENT_OWNER.get(statement)
    if owner and owner in sub.constraints:
        return owner
    return owner or "maker_who_sells_becomes_manufacturer"


def publishable(concept: Concept) -> bool:
    """Whether this concept can be published at all, statements aside.

    Measures: the absence of any REFUSE finding.
    Why: two different questions get asked of an assessment -- "may we publish this?" and "what
    must it say?" -- and answering them with one boolean is how a refusal turns into a to-do.
    """
    return not any(f.severity == REFUSE for f in assess(concept))


# ---- sizing ----------------------------------------------------------------

@dataclass(frozen=True)
class SizeRow:
    label: str
    chest_in: float
    chest_cm: float


# Craft Yarn Council baby size chart, read 2026-09-24. Chest only; the published chart also
# carries centre-back-neck-to-wrist, back waist length, cross back, arm length to underarm,
# upper arm, armhole depth, waist and hips, and those belong here when a garment needs them.
BABY_SIZES: tuple[SizeRow, ...] = (
    SizeRow("3 months", 16.0, 40.5),
    SizeRow("6 months", 17.0, 43.0),
    SizeRow("12 months", 18.0, 45.5),
    SizeRow("18 months", 19.0, 48.0),
    SizeRow("24 months", 20.0, 50.5),
)

# Craft Yarn Council child and youth size charts, read 2026-09-24.
CHILD_YOUTH_SIZES: tuple[SizeRow, ...] = (
    SizeRow("2", 21.0, 53.0),
    SizeRow("4", 23.0, 58.5),
    SizeRow("6", 25.0, 63.5),
    SizeRow("8", 26.5, 67.0),
    SizeRow("10", 28.0, 71.0),
    SizeRow("12", 30.0, 76.0),
    SizeRow("14", 31.5, 80.0),
    SizeRow("16", 32.5, 82.5),
)

SIZE_SOURCES: dict[str, str] = {
    "baby": "cyc_baby_sizes",
    "child_youth": "cyc_child_sizes",
}


def chest_for_size(label: str) -> SizeRow:
    """The CYC row for a size label.

    Measures: an exact match on the published size label.
    Why: grading a children's garment against a published standard is the difference between
    arithmetic and opinion, and it is the one part of the children's audience where a free
    industry standard removes the guesswork entirely.
    """
    for row in BABY_SIZES + CHILD_YOUTH_SIZES:
        if row.label == label:
            return row
    raise KeyError(f"no CYC size named {label!r}")


def carries_no_market_numbers() -> bool:
    """Whether the sub-category table is free of demand, price and competition numbers.

    Measures: the field names of `Subcategory` against the vocabulary of market estimation.
    Why: this module's authority comes from its citations. A score nobody measured, sitting in
    the same table as a regulation, spends that authority on a guess. The absence is asserted
    here so that adding one is a test failure rather than a quiet afternoon's work.
    """
    forbidden = ("demand", "competition", "score", "price", "volume", "revenue", "rank")
    names = [f.name for f in fields(Subcategory)]
    return not any(word in name for name in names for word in forbidden)
