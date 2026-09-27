"""Blinded head-to-head against a human catalogue, and the ways that measurement lies.

Requirement 94 asks for creative capability tracked through *blinded human/agent benchmark
comparisons*. Everything else it asks for -- field spread, survival rate, death causes, their
trends -- is computed deterministically in `tournament.scorecard()`. This is the half that
needs a judge, and it became possible on 2026-09-19 when the model gate opened from a
recorded successful call and the benchmark scan returned 438 real listings.

The human side is `MJsOffTheHookDesigns`: products designed by a person and proven by an
actual market. The agent side is this company's concepts. That is the comparison the owner
cares about, because *"a technically perfect but boring product is a failed product"* and the
creative gate has been reporting 0 of 11 survivors with emotional appeal as the dominant
failure. A number for "are ours as appealing as theirs" is the thing that turns that from an
opinion into a measurement.

Four ways this measurement lies, and the guard for each. The fourth is here because the
first live run found it, 11-1 to this catalogue with every other guard green -- which is the
best argument available that a measurement like this should be run early and distrusted.

**It is not blinded unless blinding is mechanical.** A comparison where one card says
"Hearthside Throw, heirloom winter warmth" and the other says "CROCHET PATTERN & VIDEO/ ..."
is not blind; the judge can see whose is whose from the punctuation alone. So both sides are
rendered into the *same* closed vocabulary, and `blind()` refuses a card that still carries a
tell. A blinding that is a promise rather than a check is not a blinding.

**A judge that prefers the first option is measuring order.** Position bias is the classic
failure of pairwise LLM evaluation and it produces a confident, stable, meaningless win rate.
Every pair is presented in a randomised order, the position of each side is recorded, and if
the winning position is lopsided the whole run is reported invalid rather than adjusted --
because a correction applied to a judge that was not really reading is a number with error
bars around nothing.

**A win rate from four pairs is not a capability.** Below a floor there is no rate, only
`unmeasured`, which is not the same as parity and very much not the same as losing. And a
run that cannot reach the floor is refused *before* it spends, because paying for a result
already known is worse than not measuring.

**A judge shown a blanket and a coaster picks the blanket.** The first live run scored 11-1
and named "throw" in nine of its twelve reasons, against opponents that were pillows,
coasters and wreaths. Our home decor is mostly rectangle throws and theirs is small accent
objects, so it measured which object is bigger -- a thing that is true whoever designed
either one. Pairing is therefore same-*form* as well as same-pod, which removes the confound
by construction and leaves far fewer pairs. That is the honest trade: this catalogue and this
benchmark barely overlap in what they make, and `form_overlap()` reports the empty side,
because that is a finding about the catalogue rather than a limitation of the tool.

Nothing here reads or reproduces a competitor's pattern instructions. It compares what a
product *is and promises* -- pod, form, occasion, recipient, feeling -- which is demand
and merchandising intelligence, and is the only thing the standing constraint allows.
"""
from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field

from ..intel import pods
from .concept import Concept

OURS = "agent"
THEIRS = "human"

# Below this many judged pairs there is no win rate. Chosen so that a single pod's comparison
# can still report, while a handful of pairs cannot become "we are ahead".
MIN_PAIRS = 12

# If more than this share of wins land on one presented position, the run measured order
# rather than quality. 0.5 would be perfect balance; this is the point past which the result
# is not worth reporting.
MAX_POSITION_SHARE = 0.70

# A card may not contain any of these. They are the tells that survive a careless render:
# the two shop names, the concept key prefix, and the format words that only ever appear on
# a marketplace listing.
_TELLS: tuple[str, ...] = (
    "brambleloop", "mjsoffthehookdesigns", "mjs", "etsy", "crochet pattern", "pdf",
    "digital download", "ebook", "pattern &", "video/", "©", "http",
)

# The closed vocabulary a card is rendered into. Every field here is one that *both* sides
# can fill from the same enumerated list, which is a harder constraint than it looks and the
# reason the card is short.
#
# A Concept carries free text in `motif`, `premise`, `palette_story` and `function`. A
# benchmark listing carries none of those, and inventing them would be fabrication. If our
# cards had evocative free text and theirs had terse keywords, the judge could separate the
# two by register alone and the run would measure prose. So the free-text fields are not on
# the card at all -- the comparison is over the *structural promise* of a product, which is
# what both sides genuinely state.
#
# What that leaves out is the photograph, and the photograph is most of why a listing sells.
# That half needs the browser/vision capability and is parked on it. This measurement is
# therefore a floor rather than the whole answer, and says so in its own output rather than
# in a caveat somebody skips.
CARD_FIELDS: tuple[str, ...] = ("pod", "form", "occasion", "recipient", "feeling")

# A bundle and a guidebook are not the same kind of object as a single product concept.
# Pairing against one measures format, not creativity.
NOT_COMPARABLE_PODS: tuple[str, ...] = ("collections", "education")


class BlindingFailed(ValueError):
    """A card that would tell the judge which side it came from."""


class NotComparable(ValueError):
    """A pairing that would not measure what it claims to."""


class Unreadable(ValueError):
    """A listing whose title does not state enough to describe it without inventing."""


@dataclass(frozen=True)
class Card:
    """One product idea, described so that both sides are describable the same way."""

    ref: str
    side: str
    pod: str
    form: str
    occasion: str
    recipient: str
    feeling: str

    def presented(self) -> dict:
        """What the judge sees. `side` and `ref` are not in it, which is the entire point."""
        return {f: str(getattr(self, f)).replace("_", " ") for f in CARD_FIELDS}


def blind(card: Card) -> dict:
    """The judge's view of a card, refusing anything that gives its side away.

    Checked on the rendered text rather than the source object, because the tell always
    arrives through a field somebody added later and did not think of as identifying.
    """
    shown = card.presented()
    blob = " ".join(str(v) for v in shown.values()).lower()
    for tell in _TELLS:
        if tell in blob:
            raise BlindingFailed(
                f"the card for {card.ref!r} contains {tell!r}, so the comparison would not "
                f"be blind. A blinding that is a promise rather than a check is not one")
    missing = [f for f in CARD_FIELDS if not str(shown.get(f) or "").strip()]
    if missing:
        raise BlindingFailed(
            f"the card for {card.ref!r} leaves {missing} empty, and a card with holes in it "
            f"is identifiable by its holes")
    return shown


def from_concept(concept: Concept) -> Card:
    """Our side, straight from the closed vocabulary a Concept already uses."""
    if concept.pod in NOT_COMPARABLE_PODS:
        raise NotComparable(f"{concept.pod!r} is not a single-product pod")
    return Card(ref=concept.key, side=OURS, pod=concept.pod, form=concept.form,
                occasion=concept.occasion, recipient=concept.recipient,
                feeling=concept.feeling)


# Readings from an observed title into the *same* enumerations a Concept uses. Deliberately
# coarse and deliberately deterministic: a model could read a title more finely, and paying
# one to do it would put the benchmark side's description in a different register from ours,
# which is the tell this whole design exists to remove.

_FORM_WORDS: tuple[tuple[str, str], ...] = (
    ("stocking", "stocking"), ("ornament", "ornament"), ("bauble", "ornament"),
    ("garland", "garland"), ("wreath", "wreath"),
    ("blanket", "rectangle_throw"), ("throw", "rectangle_throw"), ("afghan", "rectangle_throw"),
    ("scarf", "scarf"), ("cowl", "scarf"),
    ("hat", "hat"), ("beanie", "hat"), ("toque", "hat"), ("headband", "hat"),
    ("basket", "basket"), ("tote", "bag"), ("purse", "bag"), ("bag", "bag"),
    ("pouch", "pouch"),
    ("pillow", "pillow"), ("cushion", "pillow"),
    ("coaster", "coaster"), ("runner", "runner"), ("wall hanging", "wall_hanging"),
    ("dishcloth", "flat_panel"), ("washcloth", "flat_panel"), ("facecloth", "flat_panel"),
    ("scrubby", "round_disc"), ("potholder", "flat_panel"), ("trivet", "round_disc"),
    ("cardigan", "fitted_garment"), ("sweater", "fitted_garment"),
    ("pullover", "fitted_garment"), ("hoodie", "fitted_garment"),
    ("skirt", "fitted_garment"), ("tank", "fitted_garment"), ("vest", "fitted_garment"),
    ("shawl", "draped_garment"), ("wrap", "draped_garment"), ("poncho", "draped_garment"),
    ("coverup", "draped_garment"),
    ("amigurumi", "toy"), ("plush", "toy"), ("lovey", "toy"), ("gnome", "toy"),
    ("snowman", "toy"), ("pumpkin", "toy"), ("mushroom", "toy"), ("acorn", "toy"),
    ("bunny", "toy"), ("owl", "toy"), ("doll", "toy"),
    ("cozy", "tube"), ("pouf", "sphere"),
)

_FEELING_WORDS: tuple[tuple[str, str], ...] = (
    ("heirloom", "heirloom"), ("timeless", "heirloom"), ("signature", "heirloom"),
    ("cozy", "cosy"), ("cosy", "cosy"), ("cottage", "cosy"),
    ("rustic", "folkloric"), ("farmhouse", "folkloric"), ("woodland", "folkloric"),
    ("chunky", "rugged"), ("bulky", "rugged"),
    ("festive", "festive"), ("holiday", "festive"), ("merry", "festive"),
    ("whimsical", "whimsical"), ("playful", "playful"),
    ("vintage", "nostalgic"), ("classic", "nostalgic"), ("granny", "nostalgic"),
    ("boho", "bold"), ("mosaic", "bold"),
    ("elegant", "quietly_luxurious"), ("lace", "quietly_luxurious"),
    ("star", "celebratory"), ("sparkle", "celebratory"),
    ("serene", "serene"), ("calm", "serene"), ("seaside", "serene"),
    ("romantic", "romantic"), ("rosy", "romantic"), ("blush", "romantic"),
    ("baby", "tender"), ("tender", "tender"),
)

_OCCASION_WORDS: tuple[tuple[str, str], ...] = (
    ("christmas", "christmas"), ("halloween", "halloween"), ("easter", "easter"),
    ("valentine", "valentines"), ("thanksgiving", "thanksgiving"),
    ("wedding", "wedding"), ("birthday", "birthday"), ("baby", "new_baby"),
    ("winter", "winter_nesting"), ("spring", "spring_refresh"), ("summer", "summer_travel"),
    ("beach", "summer_travel"), ("school", "back_to_school"),
)

_RECIPIENT_WORDS: tuple[tuple[str, str], ...] = (
    ("baby", "new_baby"), ("child", "child"), ("kid", "child"), ("teen", "teen"),
    ("men", "self"), ("women", "self"), ("host", "host"), ("teacher", "teacher"),
    ("student", "student"), ("pet", "pet_owner"),
)


def _read(words: frozenset[str], phrase: str,
          table: tuple[tuple[str, str], ...]) -> str:
    for term, value in table:
        if " " in term:
            if f" {term} " in phrase:
                return value
        elif term in words:
            return value
    return ""


def form_of(listing: dict) -> str:
    """Just the product form a listing's title states, or "" when it states none.

    Separate from `from_listing` because the two questions have different standards of
    evidence. A blinded comparison needs a whole card -- a listing missing a feeling cannot
    be described without inventing one, and an invented field on one side is a tell. Counting
    what forms a department contains needs only the form, and refusing to count a plainly
    titled "Ribbed Cardigan Crochet Pattern" because its title has no mood word does not make
    the count more careful, it makes it wrong: the department loses a cardigan it demonstrably
    contains, and the pod reports as having no readable forms at all.
    """
    title = str(listing.get("title") or "")
    words, phrase = pods.signals(title)
    return _read(words, phrase, _FORM_WORDS)


def from_listing(listing: dict) -> Card:
    """Their side, from observed catalogue facts and nothing protected.

    Read: the pod, the product form, the occasion and the feeling the title itself states.
    Never read: instructions, charts, photography or any part of the pattern. The standing
    constraint is that competitor research is for demand and merchandising intelligence only,
    and a card is exactly that much.

    Raises `Unreadable` rather than filling a gap with a default. A default that appears only
    on one side is a tell, and a default that appears on both is a fabrication about one of
    them -- so a listing whose title does not say what it is simply does not become an
    opponent, and the share that could not be read is reported.
    """
    title = str(listing.get("title") or "")
    words, phrase = pods.signals(title)
    pod = listing.get("pod") or pods.route(title, str(listing.get("product_type") or ""))
    if pod in NOT_COMPARABLE_PODS or pod == pods.UNCLASSIFIED:
        raise Unreadable(f"{pod!r} is not a single-product pod")

    form = _read(words, phrase, _FORM_WORDS)
    feeling = _read(words, phrase, _FEELING_WORDS)
    if not form or not feeling:
        raise Unreadable(
            f"the title states {'no product form' if not form else 'no feeling'}, so this "
            f"listing cannot be described without inventing one")
    return Card(
        ref=str(listing.get("listing_ref") or ""), side=THEIRS, pod=pod, form=form,
        occasion=_read(words, phrase, _OCCASION_WORDS) or "everyday",
        recipient=_read(words, phrase, _RECIPIENT_WORDS) or "self",
        feeling=feeling)


# ---------------------------------------------------------------------------
# Pairing


@dataclass(frozen=True)
class Pairing:
    """One head-to-head, with which side was shown first recorded before the judging."""

    ours: Card
    theirs: Card
    first: str          # OURS or THEIRS -- the side presented as option A

    def options(self) -> dict:
        a, b = ((self.ours, self.theirs) if self.first == OURS
                else (self.theirs, self.ours))
        return {"A": blind(a), "B": blind(b)}

    def side_at(self, position: str) -> str:
        if position not in ("A", "B"):
            raise NotComparable(f"{position!r} is not a presented position")
        if position == "A":
            return self.first
        return THEIRS if self.first == OURS else OURS


def _coin(seed: str) -> bool:
    """Deterministic per pair, so a run is reproducible and a seed is not a hidden knob."""
    return hashlib.sha256(seed.encode()).digest()[0] % 2 == 0


def pair(ours: Card, theirs: Card, *, seed: str = "") -> Pairing:
    """One same-pod, same-form head-to-head, with the order decided before anything reads it.

    Same pod because a stocking beating a cardigan measures which department is easier to
    love. #168 makes that point about purchased benchmarks and it is the same mistake here.

    Same *form* for a reason the first live run taught, which no amount of reasoning about
    this design had produced. That run came back 11-1 to this catalogue, position share
    exactly 0.50, comfortably above the sample floor, `valid: true`, verdict `ahead`. It was
    worthless. The judge's own reasons said why: it named "throw" in nine of twelve, against
    opponents that were pillows, coasters and wreaths. Our home decor is mostly rectangle
    throws and theirs is small accent objects, so the run measured **which object is bigger**
    -- and a blanket beats a coaster on perceived value every time, whoever designed it.

    That is a third confound, alongside position bias and a thin sample, and the first two
    guards passed it without complaint. It cannot be corrected after the fact any more than
    position bias can, so it is removed by construction: a throw is judged against a throw.
    The cost is that far fewer pairs exist, and the run then honestly reports `unmeasured`
    instead of confidently reporting a number about nothing.
    """
    if ours.side != OURS or theirs.side != THEIRS:
        raise NotComparable("a pairing is one of ours against one of theirs")
    if ours.pod != theirs.pod:
        raise NotComparable(
            f"{ours.pod!r} against {theirs.pod!r} measures which department is easier to "
            f"love, not which idea is better. A comparison is same-pod or it is not one")
    if ours.form != theirs.form:
        raise NotComparable(
            f"{ours.form!r} against {theirs.form!r} measures which object is bigger. A "
            f"blanket beats a coaster on perceived value whoever designed it, and the first "
            f"live run scored 11-1 on exactly that and called itself valid")
    return Pairing(ours, theirs, OURS if _coin(seed or f"{ours.ref}|{theirs.ref}") else THEIRS)


def build_pairs(concepts: list[Concept], listings: list[dict], *,
                per_pod: int = 3, seed: int = 0) -> list[Pairing]:
    """As many same-pod pairings as both sides can supply, bounded per pod.

    Bounded because a pod with 140 benchmark listings would otherwise drown a pod with four,
    and the overall win rate would become a statement about garments wearing the label of a
    statement about this company.
    """
    theirs_by_form: dict[tuple[str, str], list[Card]] = {}
    unreadable = 0
    for listing in listings:
        try:
            card = from_listing(listing)
        except (Unreadable, NotComparable):
            unreadable += 1
            continue
        if card.ref:
            theirs_by_form.setdefault((card.pod, card.form), []).append(card)

    rng = random.Random(seed)
    pairs: list[Pairing] = []
    for concept in concepts:
        try:
            ours = from_concept(concept)
        except NotComparable:
            continue
        pool = theirs_by_form.get((ours.pod, ours.form)) or []
        if not pool:
            continue
        for opponent in rng.sample(pool, min(per_pod, len(pool))):
            try:
                pairs.append(pair(ours, opponent))
            except (NotComparable, BlindingFailed):
                continue
    return pairs


def form_overlap(concepts: list[Concept], listings: list[dict]) -> dict:
    """Which pod-and-form slots both sides can field, which is what bounds the comparison.

    The interesting output is usually the empty side. This catalogue is eleven flat
    home-decor panels; the benchmark's home decor is pillows, wreaths and poufs. There is
    very little like-for-like to compare, and that is a finding about the catalogue rather
    than a limitation of the measurement.
    """
    mine: dict[tuple[str, str], int] = {}
    for concept in concepts:
        try:
            card = from_concept(concept)
        except NotComparable:
            continue
        mine[(card.pod, card.form)] = mine.get((card.pod, card.form), 0) + 1

    theirs: dict[tuple[str, str], int] = {}
    for listing in listings:
        try:
            card = from_listing(listing)
        except (Unreadable, NotComparable):
            continue
        theirs[(card.pod, card.form)] = theirs.get((card.pod, card.form), 0) + 1

    shared = sorted(set(mine) & set(theirs))
    return {
        "shared_slots": [{"pod": p, "form": f, "ours": mine[(p, f)],
                          "theirs": theirs[(p, f)]} for p, f in shared],
        "ours_only": [{"pod": p, "form": f, "ours": n}
                      for (p, f), n in sorted(mine.items()) if (p, f) not in theirs],
        "theirs_only_count": len([k for k in theirs if k not in mine]),
        "our_concepts_with_an_opponent": sum(mine[k] for k in shared),
        "our_concepts": sum(mine.values()),
    }


def _overlap_sentence(concepts: list[Concept], listings: list[dict]) -> str:
    overlap = form_overlap(concepts, listings)
    ours_only = ", ".join(f'{r["pod"]}/{r["form"]}' for r in overlap["ours_only"][:6])
    return (f'{overlap["our_concepts_with_an_opponent"]} of {overlap["our_concepts"]} '
            f'concepts have a like-for-like opponent at all'
            + (f'; this catalogue makes {ours_only}, which this benchmark does not.'
               if ours_only else '.'))


def readability(listings: list[dict]) -> dict:
    """How much of the benchmark catalogue can be described without inventing anything.

    Reported because refusing to describe an unreadable listing creates a selection bias:
    the opponents are the listings whose titles say the most, which are not a random sample
    of the shop. A bias that is measured and stated is a limitation; the same bias unstated
    is a wrong number.
    """
    usable, by_reason = 0, {}
    for listing in listings:
        try:
            from_listing(listing)
        except (Unreadable, NotComparable) as e:
            key = str(e).split(",")[0][:60]
            by_reason[key] = by_reason.get(key, 0) + 1
        else:
            usable += 1
    return {
        "listings": len(listings), "usable_as_opponents": usable,
        "share": round(usable / len(listings), 3) if listings else 0.0,
        "unreadable_by_reason": dict(sorted(by_reason.items(), key=lambda kv: -kv[1])),
        "note": ("Opponents are the listings whose titles state a form and a feeling, which "
                 "is not a random sample of the shop. Stated because an unstated selection "
                 "bias is a wrong number rather than a limitation."),
    }


# ---------------------------------------------------------------------------
# Tallying


@dataclass
class Judgement:
    """One returned verdict, recorded as a position so the bias is computable afterwards."""

    pairing: Pairing
    picked: str         # "A" or "B"
    reason: str = ""

    @property
    def winner(self) -> str:
        return self.pairing.side_at(self.picked)


@dataclass
class Tally:
    judged: int = 0
    ours: int = 0
    theirs: int = 0
    by_pod: dict = field(default_factory=dict)
    position_a_wins: int = 0

    def to_dict(self) -> dict:
        return {"judged": self.judged, "ours": self.ours, "theirs": self.theirs}


def tally(judgements: list[Judgement], *, min_pairs: int = MIN_PAIRS) -> dict:
    """The win rate, or an honest refusal to state one.

    Two conditions have to hold before a number means anything, and both are checked here
    rather than described in a caveat somebody skips.
    """
    if not judgements:
        return {
            "verdict": "unmeasured", "judged": 0,
            "reason": ("no pair has been judged, so nothing is known about how this "
                       "catalogue compares to a human one. Unmeasured is not parity"),
            "valid": False,
        }

    ours = sum(1 for j in judgements if j.winner == OURS)
    a_wins = sum(1 for j in judgements if j.picked == "A")
    judged = len(judgements)
    position_share = round(max(a_wins, judged - a_wins) / judged, 4)

    by_pod: dict[str, dict] = {}
    for j in judgements:
        row = by_pod.setdefault(j.pairing.ours.pod, {"judged": 0, "ours": 0})
        row["judged"] += 1
        row["ours"] += 1 if j.winner == OURS else 0
    for row in by_pod.values():
        row["win_rate"] = round(row["ours"] / row["judged"], 4)

    biased = position_share > MAX_POSITION_SHARE
    thin = judged < min_pairs
    out = {
        "judged": judged,
        "ours": ours,
        "theirs": judged - ours,
        "win_rate": round(ours / judged, 4),
        "by_pod": dict(sorted(by_pod.items())),
        "position_share": position_share,
        "position_bias_ceiling": MAX_POSITION_SHARE,
        "min_pairs": min_pairs,
        "valid": not (biased or thin),
    }
    if biased:
        out["verdict"] = "invalid"
        out["reason"] = (
            f"{position_share:.0%} of wins went to one presented position, so this run "
            f"measured order and not quality. The result is discarded rather than corrected: "
            f"a correction applied to a judge that was not really reading puts error bars "
            f"around nothing")
    elif thin:
        out["verdict"] = "unmeasured"
        out["reason"] = (
            f"{judged} pairs judged against a floor of {min_pairs}. A win rate from this many "
            f"is not a capability measurement, and reporting it as one is how a company "
            f"concludes it is ahead")
    else:
        rate = ours / judged
        out["verdict"] = ("ahead" if rate >= 0.60 else "behind" if rate <= 0.40 else "parity")
        out["reason"] = (
            f"{ours} of {judged} blinded same-pod pairs went to this catalogue against a "
            f"human one that a market has already paid for")
    return out


# ---------------------------------------------------------------------------
# Running it against the real provider and the real catalogue


# The task this run is priced and budgeted as. Declared in gateway.routing with a tier and a
# token estimate, so the monthly ceiling is checked before each call rather than discovered
# on an invoice.
TASK = "benchmark_challenge"

# The method this result was produced by. Version 1 matched on pod alone and scored 11-1 for
# this catalogue by comparing throws to coasters; version 2 matches on pod *and* form and
# refuses to spend below the sample floor. A stored run from an older method is not a data
# point about creative capability -- it is a data point about the older method, and
# `last_run()` says so rather than letting the dashboard carry a number nobody would defend.
METHOD_VERSION = 2

# A judged pair costs a DEEP-tier call. The cap is here rather than at the call site because
# a run with no cap is one loop away from the whole month's ceiling.
DEFAULT_MAX_PAIRS = 24


class RunRefused(RuntimeError):
    """The run could not be made honestly, for a reason worth reading."""


def benchmark_cards(db, *, benchmark_key: str = "", limit: int = 0) -> list[dict]:
    """The human side, from listings this company actually observed."""
    from sqlalchemy import select

    from ..core.models import BenchmarkListing
    from ..intel import benchmarks

    benchmark_key = benchmark_key or benchmarks.MJS_KEY
    with db.session() as s:
        rows = list(s.scalars(select(BenchmarkListing).where(
            BenchmarkListing.benchmark_key == benchmark_key)))
    out = [{"listing_ref": r.listing_ref, "title": r.title, "pod": r.pod,
            "product_type": r.product_type, "price_cad": r.price_cad}
           for r in rows if r.audit_state != "withdrawn"]
    return out[:limit] if limit else out


def run(db, concepts: list[Concept], *, gateway=None, agent: str = "creative_director",
        per_pod: int = 3, max_pairs: int = DEFAULT_MAX_PAIRS, seed: int = 0,
        benchmark_key: str = "") -> dict:
    """Judge as many pairs as the ceiling allows, and report what that bought.

    Stops on the ceiling rather than failing on it. A creative measurement that takes the
    whole month's model budget is a worse outcome than a measurement that reports
    `unmeasured` and says how many pairs it managed, so the partial run is kept and labelled.
    """
    from ..gateway import anthropic as gw
    from ..gateway import routing

    listings = benchmark_cards(db, benchmark_key=benchmark_key)
    if not listings:
        raise RunRefused(
            "no benchmark listing has been observed, so there is no human catalogue to "
            "compare against. An empty comparison is not a favourable one")
    if not concepts:
        raise RunRefused("no concept was supplied, so there is nothing of ours to judge")

    pairs = build_pairs(concepts, listings, per_pod=per_pod, seed=seed)[:max_pairs]
    if not pairs:
        raise RunRefused(
            "no concept shares a pod and a form with an observed listing, so every pairing "
            "would have compared departments or object sizes rather than ideas. "
            + _overlap_sentence(concepts, listings))
    if len(pairs) < MIN_PAIRS:
        # Refused before spending rather than after. A run that judges eight pairs reports
        # `unmeasured` by design, so buying it is paying real money for a result already
        # known -- and the ceiling is a maximum, not a target.
        raise RunRefused(
            f"only {len(pairs)} like-for-like pairs exist against a floor of {MIN_PAIRS}, so "
            f"this run would report `unmeasured` whatever the judge said. Refused before "
            f"spending: a measurement whose answer is already known costs nothing to skip. "
            + _overlap_sentence(concepts, listings))

    judgements: list[Judgement] = []
    problems: list[str] = []
    spent_start = routing.spent_this_month(db)
    stopped_on_ceiling = False

    for p in pairs:
        try:
            # The one mechanism: the month, this agent's daily permission and the live
            # reservations, rather than `routing.check`'s month-only arithmetic. The
            # reservation itself is taken by the gateway when it makes the call.
            task, tier = routing.route(TASK)
            gw.check_budget(db, model=tier.model, input_tokens=task.typical_input_tokens,
                            max_tokens=task.max_output_tokens, agent=agent, purpose=TASK,
                            reserve=False)
        except gw.BudgetExceeded as e:
            stopped_on_ceiling = True
            problems.append(str(e)[:200])
            break
        options = p.options()
        try:
            answer = gateway.complete_json(
                "creative.blinded_appeal@1", agent=agent,
                values={"option_a": options["A"], "option_b": options["B"]},
                required=("pick", "reason"))
        except Exception as e:  # noqa: BLE001 - a judge that fails is a skipped pair
            problems.append(f"{p.ours.ref} vs {p.theirs.ref}: {type(e).__name__}: {e}"[:200])
            continue
        pick = str(answer.get("pick") or "").strip().upper()
        if pick not in ("A", "B"):
            problems.append(f"{p.ours.ref}: {pick!r} is not a presented position")
            continue
        judgements.append(Judgement(p, pick, str(answer.get("reason") or "")[:300]))

    result = tally(judgements)
    result.update({
        "method_version": METHOD_VERSION,
        "pairs_built": len(pairs),
        "pairs_judged": len(judgements),
        "stopped_on_ceiling": stopped_on_ceiling,
        "cost_cad": round(routing.spent_this_month(db) - spent_start, 6),
        "problems": problems,
        "benchmark_listings": len(listings),
        "benchmark_readability": readability(listings),
        "form_overlap": form_overlap(concepts, listings),
        "reasons": [{"pod": j.pairing.ours.pod, "winner": j.winner, "why": j.reason}
                    for j in judgements[:20]],
        "note": ("Blinded, same-pod, presentation order randomised per pair and recorded "
                 "before judging. The human side is a catalogue a market has already paid "
                 "for; nothing about either side's origin reaches the judge (#94)."),
    })
    return result


def last_run(db) -> dict | None:
    """The most recent blinded run, or None if the cadence has not come round yet."""
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    with db.session() as s:
        rows = list(s.scalars(select(AuditLog).where(AuditLog.action == "creative.blinded")
                              .order_by(desc(AuditLog.id)).limit(1)))
    if not rows:
        return None
    run = dict(rows[0].detail or {})
    version = int(run.get("method_version") or 1)
    if version < METHOD_VERSION:
        run["superseded"] = True
        run["valid"] = False
        run["superseded_reason"] = (
            f"produced by method version {version}; the current method is {METHOD_VERSION}. "
            f"Version 1 matched opponents on pod alone, so it compared rectangle throws "
            f"against coasters and pillows and scored 11-1 for this catalogue on object size "
            f"rather than on the idea. The verdict below is kept for the record and is not a "
            f"measurement of creative capability")
    return run


# ---------------------------------------------------------------------------
# The search-grid blind tournament (#126)
#
# #126 asks that concept boards or thumbnails be rendered into a simulated Etsy-style grid
# beside a current category-matched benchmark set, with seller and review signals hidden, and
# that independent judges rank attention, comprehension, desire and distinctiveness against a
# defined threshold. What follows builds the grid deterministically -- the cells, the blinding
# and the seeded interleaving -- and holds the judge fields empty until a judge fills them.
# It does not fill them itself, and a grid nobody has judged is a `fail`, because a
# threshold cleared by default is the brand favouritism the requirement forbids.

GRID_JUDGE_FIELDS: tuple[str, ...] = ("attention", "comprehension", "desire",
                                      "distinctiveness")
# The defined threshold: our cells must be ranked in the top half on every judge field, by
# judges who did not know which cells were ours. A mean below this fails.
GRID_THRESHOLD = 0.5
# A grid needs enough benchmark cells to be a search page rather than a pair.
MIN_GRID_BENCHMARKS = 6
GRID_COLUMNS = 4


class GridRefused(ValueError):
    """A grid that could not be built honestly: too few benchmarks, nothing of ours, or a leak."""


def _grid_cell_id(seed: int, index: int) -> str:
    return "c" + hashlib.sha256(f"{seed}:{index}".encode()).hexdigest()[:8]


def render_grid(db, ours: list[dict], *, pod: str, seed: int = 0,
                benchmark_key: str = "", columns: int = GRID_COLUMNS,
                judgements: dict[str, dict] | None = None) -> dict:
    """A simulated search grid of benchmark thumbnails and our renders, blinded and seeded.

    `ours` are our frame records for products in `pod` -- what `listing_asset.frames_for`
    returns -- each carrying `slug` and an `image_ref` or `image`. Their side is every
    audited listing in the pod with a first gallery image on file, referenced by URL and
    never fetched, copied or stored here: a cell carries the URL as a pointer for a judge
    with a browser, and nothing else about the listing. Seller, price, favourites, reviews
    and title are all withheld, which is what "signals hidden" means.

    `judgements` maps cell id to ranks in 0..1 on the four judge fields. Without them every
    field is None and the verdict is `fail`, reported as unjudged rather than as a threshold
    miss, so the two are never confused and neither is a pass.
    """
    from sqlalchemy import select

    from ..core.models import BenchmarkListing
    from ..intel import benchmarks

    benchmark_key = benchmark_key or benchmarks.MJS_KEY
    with db.session() as s:
        rows = list(s.scalars(select(BenchmarkListing).where(
            BenchmarkListing.benchmark_key == benchmark_key,
            BenchmarkListing.pod == pod,
            BenchmarkListing.audit_state == "audited")))
        theirs = [{"side": THEIRS, "ref": r.listing_ref,
                   "thumbnail": ((r.detail or {}).get("image_urls") or [""])[0]}
                  for r in rows if ((r.detail or {}).get("image_urls") or [""])[0]]

    mine = [{"side": OURS, "ref": str(f.get("slug") or ""),
             "thumbnail": str(f.get("image_ref") or f.get("image") or "")}
            for f in ours if f.get("made", True) and (f.get("image_ref") or f.get("image"))]
    if len(theirs) < MIN_GRID_BENCHMARKS:
        raise GridRefused(
            f"{len(theirs)} benchmark thumbnail(s) on file for pod {pod!r}, below "
            f"{MIN_GRID_BENCHMARKS}. A grid of two is a pair, not a search page, and the "
            f"tournament would measure the pairing")
    if not mine:
        raise GridRefused(
            f"no render of ours in pod {pod!r} carries an image, so there is nothing to "
            f"place in the grid. An empty side is not a favourable one")

    rng = random.Random(seed)
    cells = theirs + mine
    rng.shuffle(cells)
    key: dict[str, dict] = {}
    presented = []
    for index, cell in enumerate(cells):
        cell_id = _grid_cell_id(seed, index)
        key[cell_id] = {"side": cell["side"], "ref": cell["ref"]}
        # What a judge sees: a position, a pointer to a picture, a pod. No side, no ref, no
        # seller, no price, no reviews, no title.
        presented.append({"cell": cell_id, "row": index // max(1, columns),
                          "col": index % max(1, columns), "thumbnail": cell["thumbnail"],
                          "pod": pod})
    for cell in presented:
        leak = [k for k in cell if k in ("side", "ref", "seller", "price", "reviews", "title")]
        if leak:
            raise GridRefused(f"grid cell leaks {leak}")

    judgements = judgements or {}
    ours_ids = [c for c, k in key.items() if k["side"] == OURS]
    scores: dict[str, float | None] = {}
    for field_name in GRID_JUDGE_FIELDS:
        got = [float(judgements[c][field_name]) for c in ours_ids
               if c in judgements and judgements[c].get(field_name) is not None]
        scores[field_name] = round(sum(got) / len(got), 4) if len(got) == len(ours_ids) else None
    unjudged = [f for f, v in scores.items() if v is None]
    below = [f for f, v in scores.items() if v is not None and v < GRID_THRESHOLD]
    verdict = "fail" if unjudged or below else "clear"
    return {
        "pod": pod,
        "seed": seed,
        "columns": columns,
        "cells": presented,
        "benchmark_cells": len(theirs),
        "our_cells": len(mine),
        "judge_fields": list(GRID_JUDGE_FIELDS),
        "threshold": GRID_THRESHOLD,
        "our_scores": scores,
        "unjudged": unjudged,
        "below_threshold": below,
        "verdict": verdict,
        "why": ("no judge has ranked the grid, and a threshold cleared by default is brand "
                "favouritism" if unjudged and not judgements else
                f"unjudged on {unjudged}" if unjudged else
                f"below {GRID_THRESHOLD} on {below}" if below else
                "our cells rank in the top half on every judge field, blinded"),
        # Held apart from the cells so a judge is handed `cells` and never `key`.
        "key": key,
        "hidden": ["seller", "price", "favourites", "reviews", "title", "side"],
        "note": ("Deterministic grid, seeded and blinded. Benchmark thumbnails are URL "
                 "pointers for a judge with a browser; none is fetched, copied or stored "
                 "here. The judges are still to be appointed; until they rank it, this "
                 "grid fails (#126)"),
    }


# ---------------------------------------------------------------------------
# #126: the grid's judges.
#
# `render_grid` refused to clear until somebody ranked it, and nobody was appointed, so the
# tournament could only ever fail -- honestly, but uselessly. These are the judges: several
# independent vision-model readings of the same blinded grid, each from a different buyer's
# point of view and each seeing the cells in its own shuffled order, so no single prompt's
# taste or position bias decides the verdict. A cell's score on a field is the MEDIAN across
# judges, and a cell a judge did not answer is unjudged -- never averaged over the ones that
# did. Every call is budget-checked and reserved before it is made, like gallery vision.

GRID_JUDGES: tuple[tuple[str, str], ...] = (
    ("browsing_shopper",
     "You are an Etsy shopper scrolling a search results page for crochet patterns on a phone. "
     "You glance at each thumbnail for about a second."),
    ("experienced_maker",
     "You are an experienced crocheter choosing your next pattern. You judge whether the "
     "finished object is clear and whether the design is worth making."),
    ("gift_buyer",
     "You are buying a crochet pattern to make a gift. You care whether the finished object "
     "looks desirable and different from what everyone else sells."),
)
GRID_JUDGE_TASK = "search_grid_tournament"
GRID_JUDGE_MAX_TOKENS = 700
GRID_JUDGE_AGENT = "creative_director"


class GridJudgeRefused(Exception):
    pass


def grid_judge_prompt(cells: list[dict]) -> str:
    labels = ", ".join(c["cell"] for c in cells)
    return (
        "The images are thumbnails from one simulated Etsy search results page, in this order: "
        f"{labels}. Seller, price, reviews and titles are hidden. For EACH image score, from 0 "
        "to 1 relative to the other images on this page: attention (would it stop your "
        "scroll), comprehension (is the finished object immediately clear), desire (do you "
        "want it) and distinctiveness (does it look different from the rest). Answer with JSON "
        'only: {"cells": [{"cell": "<label>", "attention": 0.0, "comprehension": 0.0, '
        '"desire": 0.0, "distinctiveness": 0.0}]}')


def _parse_grid_answer(text: str, expected: set[str]) -> dict[str, dict]:
    import json as _json
    import re as _re

    match = _re.search(r"\{.*\}", text or "", _re.S)
    if not match:
        return {}
    try:
        data = _json.loads(match.group(0))
    except ValueError:
        return {}
    out: dict[str, dict] = {}
    for row in data.get("cells") or []:
        cell = str(row.get("cell") or "")
        if cell not in expected:
            continue
        scores = {}
        for field_name in GRID_JUDGE_FIELDS:
            try:
                v = float(row.get(field_name))
            except (TypeError, ValueError):
                v = None
            scores[field_name] = v if v is not None and 0.0 <= v <= 1.0 else None
        out[cell] = scores
    return out


def judge_grid(db, grid: dict, *, provider, judges: tuple[tuple[str, str], ...] = GRID_JUDGES,
               agent: str = GRID_JUDGE_AGENT, job_id: int | None = None,
               seed: int = 0) -> dict:
    """Rank a rendered grid with independent judges. Returns per-cell median judgements.

    The judges receive `grid["cells"]` only -- never `grid["key"]` -- so they cannot know
    which cells are ours. A call the budget refuses stops the tournament and is reported;
    the grid then stays unjudged and fails, which is the honest result of not looking.
    """
    from statistics import median

    from ..finance import spend_report
    from ..gateway import anthropic as gw

    cells = [c for c in grid.get("cells") or [] if c.get("thumbnail")]
    if not cells:
        raise GridJudgeRefused("the grid has no cells with a thumbnail to show a judge")
    if any(k in c for c in cells for k in ("side", "ref")):
        raise GridJudgeRefused("a cell handed to a judge carries its side or ref")
    expected = {c["cell"] for c in cells}
    per_judge: dict[str, dict[str, dict]] = {}
    problems: list[str] = []
    spent = 0.0
    stopped_by = ""
    batch = max(1, gw.MAX_IMAGES_PER_CALL)

    for j_index, (judge, persona) in enumerate(judges):
        order = list(cells)
        random.Random(f"{seed}:{judge}:{j_index}").shuffle(order)
        answers: dict[str, dict] = {}
        for start in range(0, len(order), batch):
            chunk = order[start:start + batch]
            prompt = grid_judge_prompt(chunk)
            try:
                reservation = gw.check_budget(
                    db, model=provider.model,
                    input_tokens=len(prompt) // 4 + gw.IMAGE_TOKENS_ESTIMATE * len(chunk),
                    max_tokens=GRID_JUDGE_MAX_TOKENS, uncommitted_cad=spent,
                    agent=agent, purpose=GRID_JUDGE_TASK, job_id=job_id)
            except gw.BudgetExceeded as exc:
                stopped_by = type(exc).__name__
                problems.append(f"{judge}: {str(exc)[:160]}")
                break
            held = reservation["reservation_id"]
            try:
                response = provider.see(persona, prompt, [c["thumbnail"] for c in chunk],
                                        max_tokens=GRID_JUDGE_MAX_TOKENS)
            except Exception as exc:  # noqa: BLE001 - a judge that fails leaves cells unjudged
                gw.release_reservation(db, held)
                problems.append(f"{judge}: {type(exc).__name__}: {str(exc)[:160]}")
                continue
            cost = round(response.input_tokens * provider.cost_per_1k_input_cad / 1000
                         + response.output_tokens * provider.cost_per_1k_output_cad / 1000, 8)
            gw.release_reservation(db, held, actual_cad=cost)
            spent += cost
            spend_report.record(db, agent=agent, amount_cad=cost, purpose=GRID_JUDGE_TASK,
                                provider=getattr(provider, "name", ""), model=provider.model,
                                estimated_cad=reservation.get("estimate_cad", 0.0),
                                tokens_in=response.input_tokens,
                                tokens_out=response.output_tokens, job_id=job_id)
            answers.update(_parse_grid_answer(response.text, {c["cell"] for c in chunk}))
        per_judge[judge] = answers
        if stopped_by:
            break

    judgements: dict[str, dict] = {}
    for cell in expected:
        row = {}
        for field_name in GRID_JUDGE_FIELDS:
            got = [per_judge[j][cell][field_name] for j, _ in judges
                   if j in per_judge and cell in per_judge[j]
                   and per_judge[j][cell].get(field_name) is not None]
            # Every judge must have answered: a median of the judges who happened to reply
            # is a smaller panel wearing the full panel's name.
            row[field_name] = round(median(got), 4) if len(got) == len(judges) else None
        judgements[cell] = row
    return {"judgements": judgements, "judges": [j for j, _ in judges],
            "judged_by": sorted(per_judge), "problems": problems, "stopped_by": stopped_by,
            "cost_cad": round(spent, 6), "method": "median of independent judges, each "
            "seeing its own shuffled order, blinded to side and seller"}


def grid_tournament(db, ours: list[dict], *, pod: str, provider, seed: int = 0,
                    benchmark_key: str = "", job_id: int | None = None) -> dict:
    """Render the blinded grid, have it judged, and re-render it with the judgements.

    The same seed is used both times, so the cell ids the judges scored are the cells the
    verdict reads. Refusals (too few benchmarks, nothing of ours) propagate as GridRefused.
    """
    grid = render_grid(db, ours, pod=pod, seed=seed, benchmark_key=benchmark_key)
    panel = judge_grid(db, grid, provider=provider, job_id=job_id, seed=seed)
    judged = render_grid(db, ours, pod=pod, seed=seed, benchmark_key=benchmark_key,
                         judgements=panel["judgements"])
    judged.pop("key", None)
    judged["panel"] = {k: v for k, v in panel.items() if k != "judgements"}
    return judged
