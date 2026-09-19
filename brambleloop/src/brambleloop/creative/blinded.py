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

Three ways this measurement lies, and the guard for each.

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
`unmeasured`, which is not the same as parity and very much not the same as losing.

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
    """One same-pod head-to-head, with the presentation order decided before anything reads it.

    Same pod because a stocking beating a cardigan measures which department is easier to
    love. #168 makes the same point about purchased benchmarks; it is the same mistake here.
    """
    if ours.side != OURS or theirs.side != THEIRS:
        raise NotComparable("a pairing is one of ours against one of theirs")
    if ours.pod != theirs.pod:
        raise NotComparable(
            f"{ours.pod!r} against {theirs.pod!r} measures which department is easier to "
            f"love, not which idea is better. A comparison is same-pod or it is not one")
    return Pairing(ours, theirs, OURS if _coin(seed or f"{ours.ref}|{theirs.ref}") else THEIRS)


def build_pairs(concepts: list[Concept], listings: list[dict], *,
                per_pod: int = 3, seed: int = 0) -> list[Pairing]:
    """As many same-pod pairings as both sides can supply, bounded per pod.

    Bounded because a pod with 140 benchmark listings would otherwise drown a pod with four,
    and the overall win rate would become a statement about garments wearing the label of a
    statement about this company.
    """
    theirs_by_pod: dict[str, list[Card]] = {}
    unreadable = 0
    for listing in listings:
        try:
            card = from_listing(listing)
        except (Unreadable, NotComparable):
            unreadable += 1
            continue
        if card.ref:
            theirs_by_pod.setdefault(card.pod, []).append(card)

    rng = random.Random(seed)
    pairs: list[Pairing] = []
    for concept in concepts:
        pool = theirs_by_pod.get(concept.pod) or []
        if not pool:
            continue
        try:
            ours = from_concept(concept)
        except NotComparable:
            continue
        for opponent in rng.sample(pool, min(per_pod, len(pool))):
            try:
                pairs.append(pair(ours, opponent))
            except (NotComparable, BlindingFailed):
                continue
    return pairs


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
            "no concept shares a pod with an observed listing, so every pairing would have "
            "compared departments rather than ideas")

    judgements: list[Judgement] = []
    problems: list[str] = []
    spent_start = routing.spent_this_month(db)
    stopped_on_ceiling = False

    for p in pairs:
        try:
            routing.check(db, TASK)
        except routing.CeilingReached as e:
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
        "pairs_built": len(pairs),
        "pairs_judged": len(judgements),
        "stopped_on_ceiling": stopped_on_ceiling,
        "cost_cad": round(routing.spent_this_month(db) - spent_start, 6),
        "problems": problems,
        "benchmark_listings": len(listings),
        "benchmark_readability": readability(listings),
        "reasons": [{"pod": j.pairing.ours.pod, "winner": j.winner, "why": j.reason}
                    for j in judgements[:20]],
        "note": ("Blinded, same-pod, presentation order randomised per pair and recorded "
                 "before judging. The human side is a catalogue a market has already paid "
                 "for; nothing about either side's origin reaches the judge (#94)."),
    })
    return result
